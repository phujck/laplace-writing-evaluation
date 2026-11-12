from __future__ import annotations

import io
import json
import runpy
import subprocess
from pathlib import Path

import pytest
from atlas.ids import chash

from laplace.representation.attention import _chash, _exact_recovery_command, hook_response, project_attention_from_state

ROOT = Path(__file__).resolve().parents[1]


def _state() -> dict:
    assumption = "atlas rebuild"
    fibre = "s1"
    return {
        "active_context": {"assumption": assumption, "fibre": fibre},
        "event_count": 12,
        "head_event_id": "event:12",
        "seat_cursors": {
            "codex-seat": [
                {"assumption": assumption, "fibre": fibre, "cursor": 2}
            ]
        },
        "messages": {
            "message:pulled": {
                "status": "pulled",
                "assumption": assumption,
                "fibre": fibre,
                "message": {
                    "message_id": "message:pulled",
                    "sender_seat_id": "claude-seat",
                    "recipient_seat_id": "codex-seat",
                    "message_type": "audit",
                    "cursor": 2,
                    "expires_at": "2026-08-28T23:00:00+00:00",
                },
            },
            "message:queued": {
                "status": "queued",
                "assumption": assumption,
                "fibre": fibre,
                "message": {
                    "message_id": "message:queued",
                    "sender_seat_id": "claude-seat",
                    "recipient_seat_id": "codex-seat",
                    "message_type": "metric",
                    "cursor": 3,
                    "expires_at": "2026-08-28T23:00:00+00:00",
                },
            },
        },
        "reconstruction_proofs": {
            "event:proof": {
                "evaluation": {
                    "arguments": {"message_id": "message:pulled"},
                    "output_handles": ["handle:proof"],
                }
            }
        },
    }


def test_attention_epoch_covers_queued_and_reconstructed_unacknowledged_mail() -> None:
    projection = project_attention_from_state(
        _state(), seat_id="codex-seat", watcher={"lease_generation": "lease:1"}
    )

    assert projection["status"] == "PENDING"
    assert projection["pending_cursor_floor"] == 2
    assert projection["pending_cursor_ceiling"] == 3
    assert [(row["message_id"], row["state"]) for row in projection["pending"]] == [
        ("message:pulled", "reconstructed"),
        ("message:queued", "queued"),
    ]
    assert projection["pending"][0]["reconstruction_event_id"] == "event:proof"
    assert projection["pending"][0]["reconstruction_handle"] == "handle:proof"


def test_attention_hash_is_exactly_the_atlas_canonical_hash_law() -> None:
    value = {"unicode": "φ", "nested": [3, 2, 1]}
    assert _chash(value) == chash(value)


def test_unrelated_global_event_does_not_mint_a_new_attention_epoch() -> None:
    first = _state()
    second = _state()
    second["event_count"] = 99
    second["head_event_id"] = "event:unrelated"

    a = project_attention_from_state(
        first, seat_id="codex-seat", watcher={"lease_generation": "lease:1"}
    )
    b = project_attention_from_state(
        second, seat_id="codex-seat", watcher={"lease_generation": "lease:1"}
    )

    assert a["epoch_handle"] == b["epoch_handle"]
    assert a["caused_by_event_cursor"] != b["caused_by_event_cursor"]


def test_pretool_blocks_unrelated_work_but_allows_fabric_completion() -> None:
    projection = project_attention_from_state(_state(), seat_id="codex-seat")
    denied = hook_response(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q"},
        },
        projection,
    )
    allowed = hook_response(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "/usr/bin/python3 scripts/seat_fabric.py reconstruct --seat codex-seat"
            },
        },
        projection,
    )

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "additionalContext" in allowed["hookSpecificOutput"]
    assert "permissionDecision" not in allowed["hookSpecificOutput"]


def test_pretool_treats_non_mapping_input_as_unrelated_instead_of_crashing() -> None:
    projection = project_attention_from_state(_state(), seat_id="codex-seat")
    denied = hook_response(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "opaque",
            "tool_input": "not-a-mapping",
        },
        projection,
    )

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_stop_continues_the_turn_until_attention_is_clear() -> None:
    pending = project_attention_from_state(_state(), seat_id="codex-seat")
    assert hook_response({"hook_event_name": "Stop"}, pending)["decision"] == "block"
    clear_state = _state()
    clear_state["messages"] = {}
    clear_state["reconstruction_proofs"] = {}
    clear = project_attention_from_state(clear_state, seat_id="codex-seat")
    assert hook_response({"hook_event_name": "Stop"}, clear) == {}


def test_codex_registers_attention_only_for_provider_prompt_arrival() -> None:
    config = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
    hooks = config["hooks"]
    assert set(hooks) == {"SessionStart", "UserPromptSubmit"}
    command = hooks["UserPromptSubmit"][0]["hooks"][0]["command"]
    assert "attention-boundary.mjs" in command


def test_live_attention_hook_is_valid_json_on_system_python() -> None:
    result = subprocess.run(
        ["/usr/bin/python3", str(ROOT / "scripts" / "attention_boundary.py")],
        input=json.dumps({"hook_event_name": "Stop", "stop_hook_active": False}),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    assert isinstance(json.loads(result.stdout), dict)


def test_production_hook_resolves_exact_provider_binding_without_snapshot(
    monkeypatch,
) -> None:
    module = runpy.run_path(str(ROOT / "scripts" / "attention_boundary.py"))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-superego")
    monkeypatch.delenv("LAPLACE_SEAT_ID", raising=False)
    calls = []

    def binding(**kwargs):
        calls.append(kwargs)
        return {
            "status": "BOUND",
            "seat_id": "superego-seat",
            "occupancy": {
                "current_provider_identity_generation": "lease:superego:1"
            },
        }

    monkeypatch.setattr(module["atlas_bridge"], "provider_seat_binding", binding)
    monkeypatch.setattr(
        module["codex_seat_watcher"],
        "projection",
        lambda _seat: {"status": "ACTIVE", "lease_generation": "lease:superego:1"},
    )
    monkeypatch.setattr(
        module["atlas_bridge"],
        "snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("global snapshot forbidden")),
    )

    assert module["_bound_seat_id"]() == "superego-seat"
    assert calls == [{"provider_session_ref": "codex:thread-superego"}]


@pytest.mark.parametrize(
    ("command", "denied"),
    (
        ("git status --short", True),
        (
            "/usr/bin/python3 -m laplace.engine.startup_mail_gate --seat superego-seat "
            "--function superego --goal renew",
            False,
        ),
    ),
)
def test_generation_drift_blocks_authoritative_tools_but_allows_exact_recovery(
    monkeypatch,
    capsys,
    command,
    denied,
) -> None:
    module = runpy.run_path(str(ROOT / "scripts" / "attention_boundary.py"))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-superego")
    monkeypatch.delenv("LAPLACE_SEAT_ID", raising=False)
    monkeypatch.setattr(
        module["atlas_bridge"],
        "provider_seat_binding",
        lambda **_kwargs: {
            "status": "BOUND",
            "seat_id": "superego-seat",
            "occupancy": {
                "current_provider_identity_generation": "lease:superego:1"
            },
        },
    )
    monkeypatch.setattr(
        module["codex_seat_watcher"],
        "projection",
        lambda _seat: {"status": "ACTIVE", "lease_generation": "lease:superego:2"},
    )
    monkeypatch.setattr(
        module["sys"],
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                }
            )
        ),
    )

    assert module["main"]() == 0

    response = json.loads(capsys.readouterr().out)
    output = response["hookSpecificOutput"]
    assert (output.get("permissionDecision") == "deny") is denied
    assert "watcher-generation renewal" in (
        output.get("permissionDecisionReason") or output.get("additionalContext")
    )


def test_production_hook_refuses_stale_explicit_seat_over_canonical_binding(
    monkeypatch,
) -> None:
    module = runpy.run_path(str(ROOT / "scripts" / "attention_boundary.py"))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-superego")
    monkeypatch.setenv("LAPLACE_SEAT_ID", "ego-seat")
    monkeypatch.setattr(
        module["atlas_bridge"],
        "provider_seat_binding",
        lambda **_kwargs: {"status": "BOUND", "seat_id": "superego-seat"},
    )

    with pytest.raises(RuntimeError, match="conflicts with canonical"):
        module["_bound_seat_id"]()


def test_unbound_old_task_with_inherited_seat_and_valid_looking_token_is_blocked(
    monkeypatch, capsys
) -> None:
    module = runpy.run_path(str(ROOT / "scripts" / "attention_boundary.py"))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-retired")
    monkeypatch.setenv("LAPLACE_SEAT_ID", "superego-seat")
    monkeypatch.setattr(
        module["atlas_bridge"],
        "provider_seat_binding",
        lambda **_kwargs: {"status": "UNBOUND", "seat_id": None},
    )
    prompt = (
        "[Eigen Fabric watcher] scoped under laplace.provider-attention-contract/2: "
        "wake:" + "a" * 64
    )
    monkeypatch.setattr(
        module["codex_seat_watcher"],
        "attention_prompt_currentness",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("an unbound predecessor must not consult its inherited local receipt")
        ),
    )
    monkeypatch.setattr(module["sys"], "stdin", io.StringIO(json.dumps({
        "hook_event_name": "UserPromptSubmit", "prompt": prompt,
    })))

    assert module["main"]() == 0

    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "block"
    assert "UNBOUND-TASK-INERT" in response["reason"]


@pytest.mark.parametrize(
    ("command", "denied"),
    (
        ("pytest -q", True),
        (
            "/usr/bin/python3 -m laplace.engine.startup_mail_gate --seat superego-seat "
            "--function superego --goal recovery",
            False,
        ),
        (
            "/usr/bin/python3 scripts/seat_fabric.py consume-wake --seat superego-seat "
            "--thread thread-retired --token wake:" + "a" * 64,
            False,
        ),
    ),
)
def test_unbound_old_task_cannot_recover_authority_from_inherited_seat(
    monkeypatch, capsys, command, denied
) -> None:
    module = runpy.run_path(str(ROOT / "scripts" / "attention_boundary.py"))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-retired")
    monkeypatch.setenv("LAPLACE_SEAT_ID", "superego-seat")
    monkeypatch.setattr(
        module["atlas_bridge"],
        "provider_seat_binding",
        lambda **_kwargs: {"status": "UNBOUND", "seat_id": None},
    )
    monkeypatch.setattr(
        module["sys"],
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                }
            )
        ),
    )

    assert module["main"]() == 0

    response = json.loads(capsys.readouterr().out)
    output = response["hookSpecificOutput"]
    assert (output.get("permissionDecision") == "deny") is denied
    if denied:
        assert "no exact bound logical seat" in output["permissionDecisionReason"]
    else:
        assert "permissionDecision" not in output


def test_bound_successor_with_matching_live_generation_can_run_ordinary_tools(
    monkeypatch, capsys
) -> None:
    module = runpy.run_path(str(ROOT / "scripts" / "attention_boundary.py"))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-successor")
    monkeypatch.setenv("LAPLACE_SEAT_ID", "sensorium-seat")
    monkeypatch.setattr(
        module["atlas_bridge"],
        "provider_seat_binding",
        lambda **_kwargs: {
            "status": "BOUND",
            "seat_id": "sensorium-seat",
            "occupancy": {
                "current_provider_identity_generation": "lease:successor:1"
            },
        },
    )
    monkeypatch.setattr(
        module["codex_seat_watcher"],
        "projection",
        lambda _seat: {
            "status": "ACTIVE",
            "lease_generation": "lease:successor:1",
        },
    )
    monkeypatch.setattr(
        module["atlas_bridge"],
        "seat_mail_observation",
        lambda **_kwargs: {
            "status": "CURRENT",
            "seat_id": "sensorium-seat",
            "pending_messages": [],
            "mail_token": {"recipient_event_count": 0},
            "drift_token": {"cursor": 12},
            "read_metrics": {"rows_loaded": 0},
        },
    )
    monkeypatch.setattr(
        module["sys"],
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "git status --short"},
                }
            )
        ),
    )

    assert module["main"]() == 0

    response = json.loads(capsys.readouterr().out)
    assert response == {}


def test_binding_unavailable_cannot_collapse_to_benign_unbound(
    monkeypatch, capsys
) -> None:
    module = runpy.run_path(str(ROOT / "scripts" / "attention_boundary.py"))
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-retired")
    monkeypatch.delenv("LAPLACE_SEAT_ID", raising=False)
    monkeypatch.setattr(
        module["atlas_bridge"],
        "provider_seat_binding",
        lambda **_kwargs: {"status": "UNAVAILABLE"},
    )
    with pytest.raises(RuntimeError, match="binding is unavailable"):
        module["_bound_seat_id"]()

    prompt = (
        "[Eigen Fabric watcher] scoped under laplace.provider-attention-contract/2: "
        "wake:" + "b" * 64
    )
    monkeypatch.setattr(module["sys"], "stdin", io.StringIO(json.dumps({
        "hook_event_name": "UserPromptSubmit", "prompt": prompt,
    })))
    assert module["main"]() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["decision"] == "block"
    assert "BINDING-UNAVAILABLE-INERT" in response["reason"]


def test_legacy_watcher_prompt_is_inert_and_grants_no_delivery_authority() -> None:
    response = hook_response(
        {"hook_event_name": "UserPromptSubmit"},
        {"status": "LEGACY-PROMPT-INERT"},
    )

    assert response["decision"] == "block"
    assert "LEGACY-INERT" in response["reason"]
    assert "grants no work or delivery authority" in response["reason"]


def test_stale_token_prompt_is_blocked_before_it_can_create_a_model_act() -> None:
    response = hook_response(
        {"hook_event_name": "UserPromptSubmit"},
        {"status": "STALE-PROMPT-INERT", "attention_classification": "STALE-INERT"},
    )

    assert response["decision"] == "block"
    assert "STALE-INERT" in response["reason"]


def test_unclaimed_provider_allows_only_startup_gate_before_binding() -> None:
    projection = {"status": "UNCLAIMED"}
    denied = hook_response(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q"},
        },
        projection,
    )
    allowed = hook_response(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {
                "command": "/usr/bin/python3 -m laplace.engine.startup_mail_gate"
            },
        },
        projection,
    )

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "permissionDecision" not in allowed["hookSpecificOutput"]


def test_unavailable_attention_fails_closed_for_unrelated_tools() -> None:
    denied = hook_response(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "pytest -q"},
        },
        {"status": "UNAVAILABLE", "reason": "binding conflict"},
    )

    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "binding conflict" in denied["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "git status # scripts/seat_fabric.py",
        "/usr/bin/python3 scripts/seat_fabric.py status --message x; pytest -q",
        "pytest -q | /usr/bin/python3 scripts/seat_fabric.py status --message x",
        "pytest -q && /usr/bin/python3 scripts/seat_fabric.py status --message x",
        "`pytest -q` /usr/bin/python3 scripts/seat_fabric.py status --message x",
        "$(pytest -q) /usr/bin/python3 scripts/seat_fabric.py status --message x",
        "pytest -q /usr/bin/python3 scripts/seat_fabric.py status --message x",
        "python3 scripts/seat_fabric.py status --message x",
        "/usr/bin/python3 other/scripts/seat_fabric.py status --message x",
    ],
)
def test_recovery_capability_rejects_shell_smuggling(command) -> None:
    assert _exact_recovery_command(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "/usr/bin/python3 scripts/seat_fabric.py consume-wake --seat ego-seat "
        "--thread task --token wake:" + "a" * 64,
        "/usr/bin/python3 -m laplace.engine.startup_mail_gate --seat ego-seat "
        "--function ego --goal recovery",
        "/usr/bin/python3 scripts/wake.py --fabric",
    ],
)
def test_recovery_capability_accepts_exact_single_commands(command) -> None:
    assert _exact_recovery_command(command) is True
