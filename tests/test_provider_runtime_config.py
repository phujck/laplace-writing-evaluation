"""Provider configuration must remain passive; capability checks inspect metadata only."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_kernel_context_has_no_provider_mcp_registration():
    codex = tomllib.loads((ROOT / '.codex/config.toml').read_text())
    claude = json.loads((ROOT / '.mcp.json').read_text())
    for servers in (codex.get('mcp_servers', {}), claude.get('mcpServers', {})):
        assert not {'laplace', 'eigenengine'}.intersection(servers)


def test_only_passive_session_start_is_registered():
    for name in ('.codex/hooks.json', '.claude/settings.json'):
        hooks = json.loads((ROOT / name).read_text())['hooks']
        assert set(hooks) == {'SessionStart'}
    for name in ('.codex/hooks/session-start.mjs', '.claude/hooks/session-start.mjs'):
        source = (ROOT / name).read_text()
        for operation in ('spawn(', '.unref()', 'writeFileSync(', 'appendFileSync(',
                          'git config', 'ensure_state.py', 'TextEmbedding('):
            assert operation not in source


@pytest.mark.parametrize('provider', ['.codex', '.claude'])
def test_startup_delivers_current_person_wake_instruction(provider):
    from laplace.engine.session_memory import get_entry

    entry, _ = get_entry(ROOT, 'session-entry')
    result = subprocess.run(
        ['node', str(ROOT / provider / 'hooks/session-start.mjs')],
        cwd=ROOT, input=json.dumps({'hook_event_name': 'SessionStart', 'source': 'startup'}),
        capture_output=True, text=True, check=True, timeout=3,
    )
    hook = json.loads(result.stdout)['hookSpecificOutput']
    assert hook['hookEventName'] == 'SessionStart'
    context = hook['additionalContext']
    assert entry['text'] in context
    assert 'before answering the first user message' in entry['text']
    assert 'scripts/wake.py --grade 0 --person' in entry['text']
    assert 'Respect an explicit no-start instruction' in context
    assert 'when orientation is requested' not in context


def test_gpu_package_verifier_accepts_one_namespace_and_refuses_overlap(monkeypatch):
    path = ROOT / 'scripts/venv_complete.py'
    spec = importlib.util.spec_from_file_location('package_verifier', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.verify(ROOT, 'gpu') == []
    actual = module._installed
    monkeypatch.setattr(module, '_installed', lambda name: '1.0' if name == 'onnxruntime' else actual(name))
    errors = module.verify(ROOT, 'gpu')
    assert any('overlapping import namespace: onnxruntime, onnxruntime-gpu' in error for error in errors)
