"""Stateless Gemini CLI image inference through the operator's private BASAL bridge."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

PROVIDER = 'basal-gemini-cli'
DESCRIPTION = ('BASAL Gemini CLI visual inference. Send inline PNG/JPEG images and text. '
               'Returns message.content; supports text, json_object or json_schema. '
               'No tools or previous conversation. Billing is recorded by BASAL.')
PROJECT = Path(__file__).resolve().parents[2]


def bridge():
    path = Path.home() / '.config/basal-a800-cli/config.yaml'
    stat = path.stat()
    if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        raise ValueError('Expected private user-owned BASAL configuration')
    config = json.loads(path.read_text())
    if config['server']['host'] != '127.0.0.1':
        raise ValueError('Expected loopback BASAL bridge')
    return config


class BasalGeminiCliRouter:
    description = DESCRIPTION

    def prepare(self, arguments):
        from .gemini import GeminiRouter
        if not isinstance(arguments, dict) or set(arguments) - {'messages', 'max_tokens', 'response_format'}:
            raise ValueError('Gemini CLI supports messages, max_tokens and response_format')
        payload, reservation = GeminiRouter.prepare(arguments)
        if any(m['role'] == 'tool' or set(m) - {'content', 'role', 'name'} for m in payload['messages']):
            raise ValueError('Tool conversations are unsupported')
        payload.pop('provider', None)
        payload['model'] = bridge()['api-keys']['openai-compatibility'][0]['models'][0]['alias']
        payload['_rax_billing_mode'] = PROVIDER
        return payload, reservation

    def execute(self, payload, reservation):
        if payload.get('_rax_billing_mode') != PROVIDER:
            raise ValueError('Unexpected visual provider')
        result = subprocess.run([sys.executable, '-I', __file__], input=json.dumps(payload),
                                text=True, capture_output=True, timeout=180)
        if result.returncode:
            raise RuntimeError('BASAL Gemini CLI failed: ' + result.stderr.strip()[-400:])
        answer = json.loads(result.stdout)
        content = answer['content']
        fmt = payload.get('response_format', {}).get('type', 'text')
        if fmt != 'text':
            import jsonschema
            parsed = json.loads(content)
            if fmt == 'json_schema':
                jsonschema.validate(parsed, payload['response_format']['json_schema']['schema'])
            elif not isinstance(parsed, dict):
                raise ValueError('Gemini CLI did not return a JSON object')
        usage = answer.get('usage', {})
        tokens = usage.get('totalTokens')
        measured = isinstance(tokens, int) and tokens > 0
        return {'model': payload['model'], 'message': {'role': 'assistant', 'content': content},
                'finish_reason': 'stop', 'usage': usage if measured else None,
                'usage_status': 'reported' if measured else 'unavailable',
                'cost_usd': None, 'billing_mode': PROVIDER}, tokens if measured else None


def prompts(payload):
    parts = [{'type': 'text', 'text': 'Answer the supplied visual question. Use only the inline inputs.'}]
    for message in payload['messages']:
        parts.append({'type': 'text', 'text': 'Message role: ' + message['role']})
        content = message['content']
        if isinstance(content, str):
            parts.append({'type': 'text', 'text': content})
            continue
        for part in content:
            if part['type'] == 'text':
                parts.append({'type': 'text', 'text': part['text']})
            else:
                header, data = part['image_url']['url'].split(',', 1)
                parts.append({'type': 'image', 'mimeType': header[5:].split(';')[0], 'data': data})
    fmt = payload.get('response_format') or {'type': 'text'}
    instruction = 'Keep the reply within about %d tokens.' % payload['max_tokens']
    if fmt['type'] != 'text':
        instruction += ' Output only JSON without Markdown fences.'
    if fmt['type'] == 'json_schema':
        instruction += ' Required schema: ' + json.dumps(fmt['json_schema']['schema'])
    parts.append({'type': 'text', 'text': instruction})
    return parts


def acp_request(process, ident, method, params, chunks):
    def send(value):
        process.stdin.write(json.dumps(value) + '\n')
        process.stdin.flush()
    send({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params})
    while True:
        line = process.stdout.readline(1024 * 1024 + 1)
        if not line or len(line) > 1024 * 1024:
            raise RuntimeError('Gemini CLI connection ended or response exceeded limit')
        event = json.loads(line)
        if event.get('id') == ident and 'method' not in event:
            if 'error' in event:
                raise RuntimeError('%s returned ACP error %s' % (method, event['error'].get('code')))
            return event['result']
        if 'id' in event and 'method' in event:
            send({'jsonrpc': '2.0', 'id': event['id'],
                  'error': {'code': -32601, 'message': 'Client tools unavailable'}})
        update = event.get('params', {}).get('update', {})
        if update.get('sessionUpdate') == 'agent_message_chunk':
            chunks.append(update['content']['text'])
            if sum(map(len, chunks)) > 256 * 1024:
                raise ValueError('Visual reply exceeded limit')
        elif update.get('sessionUpdate') in ('tool_call', 'tool_call_update'):
            raise RuntimeError('Unexpected tool request in visual inference')


def infer(payload):
    c = bridge()
    model = c['api-keys']['openai-compatibility'][0]['models'][0]['alias']
    if model != payload['model']:
        raise ValueError('BASAL model changed after request preparation')
    tools = Path.home()/'.local/share/basal-a800-tools'
    env = {'HOME': '/home/vision', 'PATH': '/client/node-v24.14.1-linux-x64/bin:/usr/bin:/bin',
           'LANG': 'C.UTF-8', 'GEMINI_API_KEY': c['access']['api-keys'][0], 'GEMINI_MODEL': model,
           'GOOGLE_GEMINI_BASE_URL': 'http://127.0.0.1:%d' % c['server']['port'],
           'NO_PROXY': '127.0.0.1,localhost'}
    with tempfile.TemporaryDirectory(prefix='rax-basal-vision-') as temp:
        settings, policy = Path(temp)/'settings.json', Path(temp)/'deny.toml'
        settings.write_text(json.dumps({'security': {'auth': {'selectedType': 'gemini-api-key'}},
                                        'telemetry': {'enabled': False}, 'hooksConfig': {'enabled': False}}))
        policy.write_text('[[rule]]\ntoolName = "*"\ndecision = "deny"\npriority = 900\n')
        cmd = [str(PROJECT/'runtime/envs/host/bin/bwrap'), '--die-with-parent', '--unshare-pid',
               '--unshare-ipc', '--unshare-uts', '--new-session', '--ro-bind', '/usr', '/usr',
               '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
               '--symlink', 'usr/bin', '/bin', '--dev', '/dev', '--proc', '/proc',
               '--tmpfs', '/tmp', '--dir', '/home/vision/.gemini', '--dir', '/work',
               '--ro-bind', str(settings), '/home/vision/.gemini/settings.json',
               '--ro-bind', str(policy), '/policy.toml', '--ro-bind', str(tools), '/client',
               '--chdir', '/work', '/client/node-v24.14.1-linux-x64/bin/node',
               '/client/clients/node_modules/@google/gemini-cli/bundle/gemini.js',
               '--acp', '--admin-policy', '/policy.toml', '-m', model]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, env=env)
        chunks = []
        try:
            caps = acp_request(proc, 1, 'initialize', {'protocolVersion': 1, 'clientCapabilities': {}}, chunks)
            if not caps.get('agentCapabilities', {}).get('promptCapabilities', {}).get('image'):
                raise RuntimeError('Gemini CLI does not advertise image support')
            acp_request(proc, 2, 'authenticate', {'methodId': 'gemini-api-key'}, chunks)
            session = acp_request(proc, 3, 'session/new', {'cwd': '/work', 'mcpServers': []}, chunks)
            result = acp_request(proc, 4, 'session/prompt', {'sessionId': session['sessionId'],
                                 'prompt': prompts(payload)}, chunks)
            if result.get('stopReason') != 'end_turn' or not chunks:
                raise RuntimeError('Gemini CLI did not complete a reply')
            return {'content': ''.join(chunks), 'usage': result.get('usage') or {}}
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == '__main__':
    try:
        print(json.dumps(infer(json.load(sys.stdin))))
    except Exception as error:
        sys.exit('Visual request failed (%s)' % type(error).__name__)
