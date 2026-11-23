"""Bounded image/text inference through the operator's supported Codex CLI login.

Only the host launches Codex. Frozen programs receive JSON over the existing MCP
broker, never account files, a shell, network access, or an agent session. The
legacy tool name gemini_generate is retained for controller API compatibility;
its description and returned model identify the actual provider.
"""
from __future__ import annotations

import base64
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import uuid

from .gemini import GeminiRouter

MODEL = 'gpt-6-astra'
EFFORT = 'medium'
TIMEOUT = 240
BILLING_MODE = 'codex_account'
DESCRIPTION = (
    'External visual inference using GPT-6-Astra via the operator\'s ChatGPT-authenticated '
    'Codex CLI (legacy tool name gemini_generate; Gemini is not used). Available to the '
    'developing agent AND frozen controller.py during rehearsals and formal evaluation. '
    'Send inline PNG/JPEG images plus a precise prompt for names, pixel coordinates or '
    'bounding boxes; the image origin is the top-left. No paths or remote URLs. '
    'Returns message.content, actual CLI token usage, and a separately labelled hypothetical '
    'API-price estimate; subscription charges are unknown. Stateless requests, fixed medium '
    'reasoning, no shell/web/robot tools, 240-second request deadline. '
    'Supports text or response_format json_schema (all fields required and '
    'additionalProperties:false). No client function calls, temperature or reasoning '
    'overrides. max_tokens is a response-length instruction, not a CLI billing cap. '
    'The vision process sees only the supplied messages and images, not task files, '
    'simulator state, exploration memory or previous requests.'
)


def api_equivalent(usage):
    """Standard GPT-6-Astra API-price estimate; never an account charge.

    Token fields cached_input/cache_write are subsets of input; reasoning is a
    subset of output. >272k prompt uses the documented long-context multipliers.
    """
    prompt = usage['input_tokens']
    cached = usage.get('cached_input_tokens', 0)
    write = usage.get('cache_write_input_tokens', 0)
    long = prompt > 272000
    return ((prompt-cached-write)*10 + cached + write*12.5) * (2 if long else 1)/1e6 + (
        usage['output_tokens']*50*(1.5 if long else 1)/1e6)


class CodexVisionRouter:
    description = DESCRIPTION

    def __init__(self, root, *, binary=None, timeout=TIMEOUT, proxy=None):
        self.root = Path(root)
        self.binary = str(binary or Path.home()/'.local/bin/codex')
        self.timeout = timeout
        candidate = Path.home()/'.local/bin/basal-proxy'
        self.proxy = str(candidate) if proxy is None and candidate.is_file() else proxy

    def prepare(self, arguments):
        if not isinstance(arguments, dict) or set(arguments)-{'messages', 'max_tokens', 'response_format'}:
            raise ValueError('Codex vision accepts messages, max_tokens and response_format only')
        payload, reservation = GeminiRouter.prepare(arguments)  # Pure bounded-byte validation.
        if any(m['role'] == 'tool' or set(m)-{'role', 'content', 'name'} for m in payload['messages']):
            raise ValueError('Codex vision accepts text/image messages, not client tool history')
        payload['model'] = MODEL
        payload.pop('provider')
        payload['_rax_billing_mode'] = BILLING_MODE
        return payload, reservation

    def _record(self, record):
        self.root.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.root/'codex-vision-usage.jsonl', os.O_WRONLY|os.O_CREAT|os.O_APPEND, 0o600)
        with os.fdopen(fd, 'a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(json.dumps(record, allow_nan=False)+'\n')
            stream.flush()
            os.fsync(stream.fileno())

    @staticmethod
    def _stop(process):
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)

    def execute(self, payload, reservation):
        if payload.get('model') != MODEL or payload.get('_rax_billing_mode') != BILLING_MODE:
            raise ValueError('Unexpected Codex vision provider')
        ident = uuid.uuid4().hex
        record = {'request_id': ident, 'call_id': payload.get('_rax_call_id'),
                  'model': MODEL, 'reasoning_effort': EFFORT, 'started_at': time.time(),
                  'actual_cost_usd': None, 'billing_mode': BILLING_MODE, 'status': 'started'}
        self._record(record)
        started = time.monotonic()
        process = None
        try:
            # Account auth remains in the operator's normal home. No login files are
            # opened, copied, serialized, or mounted by RAX or this adapter.
            with tempfile.TemporaryDirectory(prefix='rax-codex-vision-') as temporary:
                directory = Path(temporary)
                images, messages = [], []
                for message in payload['messages']:
                    content = message.get('content', '')
                    if isinstance(content, str):
                        messages.append({'role': message['role'], 'text': content})
                        continue
                    texts = []
                    for part in content:
                        if part['type'] == 'text':
                            texts.append(part['text'])
                        else:
                            url = part['image_url']['url']
                            header, data = url.split(',', 1)
                            suffix = '.png' if 'image/png' in header else '.jpg'
                            path = directory/f'image-{len(images)+1}{suffix}'
                            path.write_bytes(base64.b64decode(data, validate=True))
                            images.append(path)
                            texts.append(f'[attached image {len(images)}]')
                    messages.append({'role': message['role'], 'text': '\n'.join(texts)})
                fmt = payload.get('response_format', {'type': 'text'})
                direct = fmt['type'] == 'json_schema'
                schema = fmt['json_schema']['schema'] if direct else {
                    'type': 'object', 'properties': {'content': {'type': 'string'}},
                    'required': ['content'], 'additionalProperties': False}
                (directory/'schema.json').write_text(json.dumps(schema))
                instruction = (
                    'You are a stateless visual inference service. Analyze only the supplied '
                    'messages and attached images. Do not call tools, run commands, access files '
                    'or fetch information. Return the requested inference only. Image coordinates '
                    'are pixels measured from the top-left unless the caller explicitly specifies '
                    'another convention. Keep the answer within approximately '
                    f"{payload['max_tokens']} output tokens. "
                    + ('Return JSON matching the supplied output schema. ' if direct else
                       'Put your answer in the content string of the supplied output schema. ')
                    + ('That string must contain a JSON object. ' if fmt['type'] == 'json_object' else '')
                    + '\nSUPPLIED MESSAGES:\n' + json.dumps(messages, ensure_ascii=False)
                )
                command = [self.binary, 'exec', '--ignore-user-config', '--ephemeral',
                           '--skip-git-repo-check', '--sandbox', 'read-only', '--model', MODEL,
                           '--cd', str(directory), '--json',
                           '-c', f'model_reasoning_effort="{EFFORT}"',
                           '-c', 'web_search="disabled"',
                           '--output-schema', str(directory/'schema.json'),
                           '--output-last-message', str(directory/'answer.json')]
                for feature in ('shell_tool', 'multi_agent', 'apps', 'hooks', 'remote_plugin'):
                    command += ['--disable', feature]
                for path in images:
                    command += ['--image', str(path)]
                command.append('-')
                if self.proxy:
                    command.insert(0, self.proxy)
                environment = os.environ.copy()
                # Never inherit a research agent's private home/provider override.
                for name in ('CODEX_HOME', 'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'CODEX_API_KEY',
                             'OPENROUTER_API_KEY', 'RAX_AGENT_SOCKET'):
                    environment.pop(name, None)
                with (directory/'events.jsonl').open('w+') as events, (directory/'stderr.log').open('w+') as errors:
                    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=events, stderr=errors,
                                               cwd=directory, env=environment, start_new_session=True, text=True)
                    try:
                        process.communicate(instruction, timeout=self.timeout)
                    finally:
                        self._stop(process)
                    events.seek(0)
                    completions, unexpected = [], []
                    for line in events:
                        event = json.loads(line)
                        if event.get('type') == 'turn.completed':
                            completions.append(event['usage'])
                        if event.get('type') == 'item.completed' and event.get('item', {}).get('type') not in (
                                'reasoning', 'agent_message'):
                            unexpected.append(event['item']['type'])
                    if completions:
                        record['usage'] = {k: sum(row.get(k, 0) for row in completions) for k in (
                            'input_tokens', 'cached_input_tokens', 'cache_write_input_tokens',
                            'output_tokens', 'reasoning_output_tokens')}
                        record['estimated_api_cost_usd'] = sum(api_equivalent(row) for row in completions)
                    if process.returncode or len(completions) != 1 or unexpected:
                        raise RuntimeError(f'Codex vision failed (exit {process.returncode}, '
                                           f'completed turns {len(completions)}, unexpected tools {unexpected})')
                    answer = (directory/'answer.json').read_text()
                    if len(answer.encode()) > 256*1024:
                        raise ValueError('Codex vision response exceeds 256 KiB')
                    parsed = json.loads(answer)
                    import jsonschema
                    jsonschema.validate(parsed, schema)
                    content = json.dumps(parsed, ensure_ascii=False) if direct else parsed['content']
                    if fmt['type'] == 'json_object' and not isinstance(json.loads(content), dict):
                        raise ValueError('Codex vision response is not a JSON object')
            record['status'] = 'completed'
            usage = record['usage']
            tokens = usage['input_tokens'] + usage['output_tokens']
            return {'model': MODEL, 'message': {'role': 'assistant', 'content': content},
                    'finish_reason': 'stop', 'usage': {**usage, 'total_tokens': tokens},
                    'cost_usd': None, 'actual_cost_usd': None, 'billing_mode': BILLING_MODE,
                    'estimated_api_cost_usd': record['estimated_api_cost_usd'],
                    'request_id': ident, 'reasoning_effort': EFFORT}, tokens
        except BaseException as exc:
            record.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            self._stop(process)
            record.update(finished_at=time.time(), elapsed_seconds=time.monotonic()-started)
            self._record(record)
