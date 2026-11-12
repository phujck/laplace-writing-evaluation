"""The Node lifecycle adapter must never turn child failure into hook success."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / ".codex" / "hooks" / "attention-boundary.mjs"


def _adapter_cases() -> list[dict]:
    javascript = f"""
import {{ attentionAdapterResponse }} from {json.dumps(ADAPTER.as_uri())};
const watcher = JSON.stringify({{
  hook_event_name: 'UserPromptSubmit',
  prompt: '[Eigen Fabric watcher] delayed retired token wake:' + 'a'.repeat(64),
}});
const human = JSON.stringify({{hook_event_name: 'UserPromptSubmit', prompt: 'hello'}});
const pending = {{hookSpecificOutput: {{
  hookEventName: 'UserPromptSubmit',
  additionalContext: 'ATLAS ATTENTION BOUNDARY: canonical logical-seat work is pending',
}}}};
const blocked = {{decision: 'block', reason: 'ATLAS ATTENTION CLASSIFICATION: STALE-INERT'}};
const cases = {{
  timeout: attentionAdapterResponse(watcher, {{status: null, stdout: '', error: {{code: 'ETIMEDOUT'}}}}),
  nonzero: attentionAdapterResponse(watcher, {{status: 7, stdout: '{{}}', signal: null}}),
  invalid: attentionAdapterResponse(watcher, {{status: 0, stdout: 'not json', signal: null}}),
  empty: attentionAdapterResponse(watcher, {{status: 0, stdout: '{{}}', signal: null}}),
  unrelated: attentionAdapterResponse(watcher, {{status: 0, stdout: JSON.stringify({{systemMessage: 'hi'}}), signal: null}}),
  pending: attentionAdapterResponse(watcher, {{status: 0, stdout: JSON.stringify(pending), signal: null}}),
  blocked: attentionAdapterResponse(watcher, {{status: 0, stdout: JSON.stringify(blocked), signal: null}}),
  human: attentionAdapterResponse(human, {{status: 0, stdout: '', signal: null}}),
}};
process.stdout.write(JSON.stringify(cases));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", javascript],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    return json.loads(completed.stdout)


def test_timeout_nonzero_and_invalid_json_block_watcher_prompt_before_model_act():
    cases = _adapter_cases()

    for name in ("timeout", "nonzero", "invalid"):
        response = cases[name]
        assert response["decision"] == "block"
        assert "WATCHER-PROMPT-INERT" in response["reason"]


def test_ordinary_human_prompt_child_failure_injects_unknown_without_blocking():
    human = _adapter_cases()["human"]

    assert human["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "TURN RECONSTRUCTION: UNKNOWN" in human["hookSpecificOutput"]["additionalContext"]


def test_watcher_prompt_requires_block_or_exact_pending_context_not_just_json():
    cases = _adapter_cases()

    for name in ("empty", "unrelated"):
        assert cases[name]["decision"] == "block"
        assert "invalid watcher response shape" in cases[name]["reason"]
    assert cases["pending"]["hookSpecificOutput"]["additionalContext"].startswith(
        "ATLAS ATTENTION BOUNDARY:"
    )
    assert cases["blocked"] == {
        "decision": "block",
        "reason": "ATLAS ATTENTION CLASSIFICATION: STALE-INERT",
    }


def test_actual_adapter_emits_block_before_the_registered_outer_timeout(tmp_path):
    config = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    outer_seconds = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]["timeout"]
    sleeper = tmp_path / "sleeping_attention_child.py"
    sleeper.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    event = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "[Eigen Fabric watcher] delayed retired token wake:" + "c" * 64,
    }
    env = dict(os.environ)
    env.update({
        "LAPLACE_TEST_PROCESS": "1",
        "LAPLACE_TEST_ATTENTION_CHILD": str(sleeper),
        "LAPLACE_TEST_ATTENTION_CHILD_TIMEOUT_MS": "50",
    })

    started = time.monotonic()
    completed = subprocess.run(
        ["node", str(ADAPTER)],
        cwd=ROOT,
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=True,
        timeout=outer_seconds,
        env=env,
    )
    elapsed = time.monotonic() - started
    response = json.loads(completed.stdout)

    assert elapsed < outer_seconds
    assert response["decision"] == "block"
    assert "WATCHER-PROMPT-INERT" in response["reason"]


def test_inner_child_budget_has_strict_margin_below_outer_hook_budget():
    config = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    outer_ms = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]["timeout"] * 1000
    source = ADAPTER.read_text(encoding="utf-8")

    assert "CHILD_TIMEOUT_MS = 1_500" in source
    assert 1500 <= outer_ms - 1000


def test_actual_ordinary_prompt_injects_the_child_turn_reconstruction(tmp_path):
    child = tmp_path / "turn_child.py"
    child.write_text(
        "import json,sys\n"
        "json.load(sys.stdin)\n"
        "print(json.dumps({'hookSpecificOutput': {"
        "'hookEventName': 'UserPromptSubmit', "
        "'additionalContext': 'TURN RECONSTRUCTION: exact-current'}}))\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.update({
        "LAPLACE_TEST_PROCESS": "1",
        "LAPLACE_TEST_ATTENTION_CHILD": str(child),
        "LAPLACE_TEST_ATTENTION_CHILD_TIMEOUT_MS": "1000",
    })

    started = time.monotonic()
    completed = subprocess.run(
        ["node", str(ADAPTER)],
        cwd=ROOT,
        input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "hello"}),
        text=True,
        capture_output=True,
        check=True,
        timeout=1,
        env=env,
    )

    assert time.monotonic() - started < 0.5
    response = json.loads(completed.stdout)
    assert response["hookSpecificOutput"]["additionalContext"] == (
        "TURN RECONSTRUCTION: exact-current"
    )
