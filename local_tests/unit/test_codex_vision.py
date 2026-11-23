"""Host vision route: real subprocess boundary, usage, cancellation and MCP broker."""
import base64
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import socket
import threading

import pytest
from PIL import Image

from services.controller.codex_vision import CodexVisionRouter, api_equivalent
from services.controller.formal_worker import Channel, RemoteGemini, serve_broker
from services.controller.gateway import Gateway
from services.controller.perception import perception_router
from test_controller_backend import Backend, configuration


def arguments():
    raw = io.BytesIO()
    Image.new('RGB', (16, 12), 'red').save(raw, format='PNG')
    return {'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'Name the color.'},
        {'type': 'image', 'mimeType': 'image/png', 'data': base64.b64encode(raw.getvalue()).decode()}]}]}


def fake_cli(tmp_path, *, behavior='success'):
    path = tmp_path/'fake-codex'
    path.write_text('#!/usr/bin/env python3\n' + '''
import json, os, sys, time
from pathlib import Path
args=sys.argv[1:]
assert '--ignore-user-config' in args and '--ephemeral' in args
assert args[args.index('--model')+1] == 'gpt-6-astra'
assert 'CODEX_HOME' not in os.environ and 'OPENAI_API_KEY' not in os.environ
assert '--image' in args and Path(args[args.index('--image')+1]).is_file()
prompt=sys.stdin.read()
assert 'Name the color.' in prompt
''' + ('''
Path('child.pid').write_text(str(os.getpid()))
time.sleep(60)
''' if behavior == 'timeout' else '''
Path(args[args.index('--output-last-message')+1]).write_text('{"content":"red"}')
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'red'}}))
print(json.dumps({'type':'turn.completed','usage':{'input_tokens':12000,'cached_input_tokens':2000,
 'cache_write_input_tokens':0,'output_tokens':100,'reasoning_output_tokens':80}}))
'''))
    path.chmod(0o700)
    return path


def test_cli_result_records_usage_without_double_counting_or_reading_auth(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', '/must-not-be-inherited')
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-be-inherited')
    router = CodexVisionRouter(tmp_path/'records', binary=fake_cli(tmp_path), proxy=False)
    payload, reserved = router.prepare(arguments())
    value, used = router.execute(payload, reserved)
    assert value['model'] == 'gpt-6-astra' and value['message']['content'] == 'red'
    assert used == 12100 and value['actual_cost_usd'] is None and value['cost_usd'] is None
    assert value['estimated_api_cost_usd'] == pytest.approx(.107)
    rows = [json.loads(s) for s in (router.root/'codex-vision-usage.jsonl').read_text().splitlines()]
    assert len(rows) == 2 and rows[-1]['status'] == 'completed'
    assert rows[0]['request_id'] == rows[1]['request_id']
    assert rows[-1]['usage']['reasoning_output_tokens'] == 80


def test_timeout_cleans_subprocess_and_records_unknown_usage(tmp_path):
    router = CodexVisionRouter(tmp_path/'records', binary=fake_cli(tmp_path, behavior='timeout'),
                               timeout=.2, proxy=False)
    import subprocess
    payload, reserved = router.prepare(arguments())
    with pytest.raises(subprocess.TimeoutExpired):
        router.execute(payload, reserved)
    row = json.loads((router.root/'codex-vision-usage.jsonl').read_text().splitlines()[-1])
    assert row['status'] == 'failed' and row['actual_cost_usd'] is None
    assert 'usage' not in row


def test_account_route_never_charges_gemini_ledger_and_brokers_to_formal_worker(tmp_path):
    router = CodexVisionRouter(tmp_path/'records', binary=fake_cli(tmp_path), proxy=False)
    class Parent:
        gemini = router
        def budget(self): return {'gemini_spend_usd': 0}
    left, right = socket.socketpair()
    thread = threading.Thread(target=serve_broker, args=(Parent(), left))
    thread.start()
    try:
        channel = Channel(right)
        remote = RemoteGemini(channel, provider='codex-account')
        def forbidden(*args): raise AssertionError('Must not charge/refund the Gemini ledger')
        audit = []
        gateway = Gateway(Backend(), remote, audit=audit.append, charge=forbidden,
                          refund=forbidden, budget=Parent().budget)
        token = gateway.acquire()
        reply = gateway.handle(token, {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': 'gemini_generate', 'arguments': arguments()}})
        assert 'error' not in reply, reply
        value = json.loads(reply['result']['content'][0]['text'])
        assert value['model'] == 'gpt-6-astra' and value['budget']['gemini_spend_usd'] == 0
        definition = next(t for t in gateway.definitions() if t['name'] == 'gemini_generate')
        assert 'GPT-6-Astra' in definition['description']
        assert 'tools' not in definition['inputSchema']['properties']
        assert audit[-1]['event'] == 'mcp_result'
    finally:
        right.shutdown(socket.SHUT_RDWR)
        right.close()
        thread.join(timeout=3)
    assert not thread.is_alive()


def test_opt_in_provider_and_inline_only_validation(tmp_path, monkeypatch):
    config = configuration(tmp_path)
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    assert perception_router(config) is None
    assert perception_router(replace(config, external_perception=False,
        external_perception_provider='codex-account')) is None
    router = perception_router(replace(config, external_perception_provider='codex-account'))
    assert isinstance(router, CodexVisionRouter)
    for extra in ({'temperature': 0}, {'tools': []}, {'reasoning': {'effort': 'high'}}):
        with pytest.raises(ValueError): router.prepare({**arguments(), **extra})
    request = {'messages': [{'role': 'user', 'content': [{'type': 'image_url',
                            'image_url': {'url': 'https://example.com/image.png'}}]}]}
    with pytest.raises(ValueError): router.prepare(request)


def test_api_estimate_cache_subsets_and_long_context():
    assert api_equivalent({'input_tokens': 100000, 'cached_input_tokens': 60000,
                          'cache_write_input_tokens': 10000, 'output_tokens': 1000}) == pytest.approx(.535)
    assert api_equivalent({'input_tokens': 300000, 'cached_input_tokens': 100000,
                          'output_tokens': 1000}) == pytest.approx(4.275)
