"""Only explicit transport proxy settings reach the native Codex process."""
import json
from pathlib import Path

import pytest

from harness import agent_host
from harness.codex_cli.auto_research import agent_environment
from test_controller_backend import configuration

PROXIES = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
           'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')


@pytest.mark.parametrize('mode', ['unset', 'upper', 'lower', 'both'])
def test_codex_inherits_only_explicit_proxy_settings(tmp_path, monkeypatch, mode):
    for name in PROXIES:
        monkeypatch.delenv(name, raising=False)
    expected = {}
    for name in PROXIES:
        selected = mode == 'both' or mode == 'upper' and name.isupper() or mode == 'lower' and name.islower()
        if selected:
            value = 'localhost,127.0.0.1,::1' if name.lower() == 'no_proxy' else 'http://127.0.0.1:17890'
            monkeypatch.setenv(name, value)
            expected[name] = value
    monkeypatch.setenv('UNRELATED_PRIVATE_TOKEN', 'must-not-reach-codex')
    monkeypatch.setenv('OPENAI_API_KEY', 'must-not-replace-session-login')
    monkeypatch.setenv('RAX_MODEL_KEY', 'must-not-override-session-key')
    monkeypatch.setenv('PYTHONPATH', '/untrusted/python')
    config = configuration(tmp_path)
    login = tmp_path / 'login.json'
    login.write_text(json.dumps({'model': 'fixture', 'chatgpt_auth': str(tmp_path / 'auth.json')}))
    workspace = config.root / 'agent-workspace'
    deployed = {'workspace': workspace, 'codex_home': config.root / 'codex-home',
                'codex': Path('/usr/bin/true'), 'login': login}
    environment = agent_environment(config, deployed, tmp_path / 'mcp.sock')
    assert {name: environment[name] for name in PROXIES if name in environment} == expected
    assert not {'UNRELATED_PRIVATE_TOKEN', 'OPENAI_API_KEY', 'RAX_MODEL_KEY'} & environment.keys()
    assert environment['PYTHONPATH'] == str(workspace.resolve())
    assert environment['CODEX_HOME'] == str(deployed['codex_home'].resolve())
    # Other CLIs and the shared host environment retain their original filtering.
    shared = agent_host.environment(home=workspace, workspace=workspace, socket=tmp_path / 'mcp.sock',
                                    cpus=config.training.cpus, binary=deployed['codex'])
    assert not set(PROXIES) & shared.keys()
