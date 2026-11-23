"""The interactive CLI uses the same visible binary and lifecycle as RAX's launcher."""
import errno
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import gzip
import json
import threading
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import termios
import time

import pytest

from test_bundle_sandbox import sandbox_runtime
from test_controller_backend import configuration
from harness import agent_host
from harness.codex_cli.auto_research import (
    agent_command, agent_environment, deploy, end_process, open_frontend_log, start_frontend,
)


@pytest.mark.parametrize('interactive', [False, True])
@pytest.mark.parametrize('resume', [False, True])
def test_only_interactive_commands_disable_the_shared_daemon(tmp_path, interactive, resume):
    deployed = {'codex': Path('/usr/bin/codex'), 'workspace': tmp_path,
                'resume_session': 'fixture-thread' if resume else None}
    command = agent_command(None, deployed, prompt='fixture prompt',
                            interactive=interactive, json_output=not interactive)
    assert ('--no-daemon' in command) is interactive
    assert ('exec' in command) is not interactive
    assert ('--skip-git-repo-check' in command) is not interactive
    assert ('resume' in command) is resume
    assert command[-1] == 'fixture prompt'
    if resume:
        assert command[-2] == 'fixture-thread'
    if interactive and resume:
        assert command.index('--no-daemon') < command.index('resume')


@pytest.fixture
def tui_model_stub():
    """A loopback-only Responses service: the TUI never calls a real model."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            assert self.headers.get('Authorization') == 'Bearer fixture-private-secret'
            raw = self.rfile.read(int(self.headers['Content-Length']))
            if self.headers.get('Content-Encoding') == 'gzip':
                raw = gzip.decompress(raw)
            request = json.loads(raw)
            requests.append(request)
            message = {'id': 'msg_tui_fixture', 'type': 'message', 'role': 'assistant',
                       'status': 'completed', 'content': [{'type': 'output_text',
                           'text': 'tui-bootstrap-ready', 'annotations': []}]}
            response = {'id': 'resp_tui_fixture', 'object': 'response', 'created_at': 1,
                        'status': 'completed', 'model': request['model'], 'output': [message],
                        'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
            events = [
                {'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
                {'type': 'response.output_item.added', 'output_index': 0,
                 'item': {**message, 'status': 'in_progress', 'content': []}},
                {'type': 'response.output_item.done', 'output_index': 0, 'item': message},
                {'type': 'response.completed', 'response': response}]
            data = ''.join('event: '+e['type']+'\ndata: '+json.dumps(e)+'\n\n' for e in events).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_real_tui_bootstrap_loads_instructions_without_a_private_daemon(sandbox_runtime, tui_model_stub):
    """Run the actual terminal UI through thread/start and a local fake response."""
    root = sandbox_runtime
    model_server, requests = tui_model_stub
    codex = shutil.which('codex')
    if not codex:
        pytest.skip('Codex CLI required')
    provider = root / 'provider'
    provider.mkdir()
    (provider / 'openrouter.config.toml').write_text(
        'model_provider="openrouter"\n'
        '[model_providers.openrouter]\n'
        'name="Offline bootstrap fixture"\n'
        f'base_url="http://127.0.0.1:{model_server.server_port}"\n'
        'wire_api="responses"\n'
        'request_max_retries=0\n'
        'stream_max_retries=0\n')
    secret = root / 'test-key'
    secret.write_text('fixture-private-secret')
    secret.chmod(0o600)
    config = configuration(root)
    deployed = deploy(config, provider_home=provider, codex=codex, key_file=secret)
    workspace, home = deployed['workspace'], deployed['codex_home']
    socket = agent_host.socket_path(config.root)
    instructions = workspace / 'AGENTS.md'
    instructions.write_text(instructions.read_text() + '\nRAX_TUI_MOUNT_REGRESSION: fixture instruction.\n')
    command = agent_command(config, deployed, prompt='Local infrastructure check; do not start robot episodes.',
                            interactive=True)
    environment = agent_environment(config, deployed, socket)
    environment.update(TERM='xterm-256color', COLUMNS='140', LINES='40')
    output = bytearray()
    transcripts = []
    pid = fd = server = None
    reaped = False
    with open_frontend_log(config.root) as log:
        try:
            server = start_frontend(config, deployed, socket, log, key_file=None)
            pid, fd = pty.fork()
            if pid == 0:
                try:
                    os.chdir(workspace)
                    os.execve(command[0], command, environment)
                except BaseException:
                    os._exit(127)  # Never run the parent's fixture cleanup in the child.
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 140, 0, 0))
            deadline = time.monotonic() + 45
            ready_at = None
            while time.monotonic() < deadline:
                readable, _, _ = select.select([fd], [], [], .1)
                if readable:
                    try:
                        chunk = os.read(fd, 65536)
                    except OSError as exc:
                        if exc.errno == errno.EIO:
                            break
                        raise
                    if not chunk:
                        break
                    output.extend(chunk)
                    if b'\x1b[6n' in chunk:
                        os.write(fd, b'\x1b[1;1R')
                    if b'\x1b[c' in chunk:
                        os.write(fd, b'\x1b[?1;2c')
                ended, status = os.waitpid(pid, os.WNOHANG)
                if ended:
                    reaped = True
                    break
                transcripts = list((home / 'sessions').rglob('rollout-*.jsonl'))
                completed = any('tui-bootstrap-ready' in path.read_text() for path in transcripts)
                if completed and requests and ready_at is None:
                    ready_at = time.monotonic()
                if ready_at is not None and time.monotonic() - ready_at >= 1:
                    break
            rendered = output.decode(errors='replace')
            (root / 'tui-bootstrap.log').write_text(rendered)
            assert transcripts, rendered[-5000:]
            assert not reaped, rendered[-5000:]
            assert 'thread/start failed' not in rendered
            assert 'fs sandbox helper failed' not in rendered
            assert not (home / 'packages/app-server-daemon').exists()
            events = [json.loads(line) for path in transcripts for line in path.read_text().splitlines()]
            assert any(e.get('type') == 'session_meta' for e in events)
            assert any(e.get('type') == 'turn_context' for e in events)
            assert requests
            assert 'RAX_TUI_MOUNT_REGRESSION' in json.dumps(requests)
            assert 'tui-bootstrap-ready' in json.dumps(events)
            state = json.loads((config.root / 'state.json').read_text())
            assert state['exploration_started'] == 0
        finally:
            if pid and not reaped:
                os.killpg(pid, signal.SIGTERM)
                stop_deadline = time.monotonic() + 5
                while time.monotonic() < stop_deadline:
                    ended, _ = os.waitpid(pid, os.WNOHANG)
                    if ended:
                        reaped = True
                        break
                    time.sleep(.05)
                if not reaped:
                    os.killpg(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)
            if fd is not None:
                os.close(fd)
            if server is not None:
                end_process(server, 10)
