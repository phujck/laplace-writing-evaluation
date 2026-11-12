from __future__ import annotations

import json
from pathlib import Path

from laplace.manuscript import walk_verdicts


def _accept(stage: str, row_id: str, *, actor: str = "gerard") -> dict:
    return {
        "record": "walk-verdict",
        "id": row_id,
        "stage": f"front-door-{stage}",
        "verdict": "accepted",
        "actor": actor,
        "via": "front-door",
        "ts": "2026-08-25T12:00:00Z",
    }


def test_retraction_id_containing_walked_can_never_satisfy_the_gate() -> None:
    forged = "RES-front-door-m4-walked"
    rows = [
        _accept("m4", forged),
        {
            "record": "walk-verdict-retraction",
            "id": "RETRACT-front-door-m4-walked-not-his",
            "retracts": forged,
            "stage": "front-door-m4",
        },
    ]

    result = walk_verdicts.fold_walk_verdicts(rows, ("m4",))

    assert result["missing_stages"] == ["m4"]
    assert result["state"]["m4"]["retracted"] is True
    assert result["state"]["m4"].get("walked") is not True


def test_exact_retraction_does_not_erase_a_different_valid_acceptance() -> None:
    rows = [
        _accept("m1", "RES-real-front-door-m1-walked"),
        _accept("m1", "RES-forged-front-door-m1-walked"),
        {
            "record": "walk-verdict-retraction",
            "id": "RETRACT-forged",
            "retracts": "RES-forged-front-door-m1-walked",
        },
    ]

    result = walk_verdicts.fold_walk_verdicts(rows, ("m1",))

    assert result["missing_stages"] == []
    assert result["state"]["m1"]["row"] == "RES-real-front-door-m1-walked"


def test_handle_prose_and_non_author_actor_are_not_authority() -> None:
    rows = [
        {"record": "note", "id": "front-door-m1-walked", "text": "accepted"},
        _accept("m1", "RES-seat-front-door-m1-walked", actor="interface-seat"),
    ]

    result = walk_verdicts.fold_walk_verdicts(rows, ("m1",))

    assert result["missing_stages"] == ["m1"]


def test_gate_fails_closed_on_a_poisoned_ledger(tmp_path) -> None:
    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    store.parent.mkdir()
    good = _accept("m1", "RES-real-front-door-m1-walked")
    store.write_text(json.dumps(good) + "\n{poisoned\n", encoding="utf-8")

    result = walk_verdicts.evaluate_front_door_program(tmp_path, ("m1",))

    assert result["integrity"]["cracked"] is True
    assert result["passed"] is False


def test_gate_fails_closed_when_the_authoritative_ledger_is_missing(tmp_path) -> None:
    result = walk_verdicts.evaluate_front_door_program(tmp_path, ("m1",))
    assert result["integrity"]["cracked"] is True
    assert result["integrity"]["residuals"][0]["defect"] == "store-unreadable"
    assert result["passed"] is False


def test_live_campaign_row_uses_the_typed_gate() -> None:
    repo_root = Path(__file__).parents[1]
    rows = [json.loads(line) for line in (
        repo_root / "corpus_friction" / "campaign.jsonl"
    ).read_text(encoding="utf-8").splitlines() if line.strip()]
    stage = [
        row for row in rows
        if row.get("record") == "stage" and row.get("id") == "CAMP-R3-front-door-program"
    ][-1]

    assert stage["gate"]["stages"] == ["m1", "m2", "m3", "m4"]
    assert "front_door_walk_gate.py" in stage["gate"]["cmd"]
    assert "txt=open" not in stage["gate"]["cmd"]
