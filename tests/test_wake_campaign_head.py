"""The campaign head of the grade-0 person wake (Atlas F1, packet C2).

ONE standalone file, by the packet's brief: the author has ruled the historical wake suites
useless and slow (2026-09-21), so this packet's own two tests live here and run on their own
in a fraction of a second. Nothing in this file monkeypatches the wake, the fabric or the
account; the one environment variable it clears is the suite-wide custody override, which is
what lets the byte and time measurements below be the ones a cold session actually pays.
"""
from __future__ import annotations

import json
from pathlib import Path

from laplace.engine import wake

ROOT = Path(__file__).resolve().parents[1]


def test_the_person_wake_answers_the_four_cold_campaign_questions(capsys, monkeypatch):
    """The projection half of the rows seam (Atlas F1, packet C2).

    The rows were correct and the wake still could not be read: a cold session was told
    ``{"ATLAS-P0": "OPEN"}`` and nothing else, so 'what does the programme build', 'what does
    its gate say is missing' and 'which wave last returned' had no answer in the doorway text.
    Four bounded fields, for the NEXT ACT ONLY, each from a store this wake already reads -
    never a markdown summary, which would make the render the source."""
    # CLI-EQUIVALENT, MEASURED: tests/conftest.py forces LAPLACE_CUSTODY_LIVE=1 for every test
    # (its own comment invites a test that exercises the OFF path to clear it, as
    # tests/test_custody_mode.py does). The repository's live custody row is OFF
    # (contract/custody_mode.jsonl, CUSTODY-OFF-20260919T182856Z), so `scripts/wake.py` itself
    # runs with the flag absent. Measured in one process, same store, 2026-09-21:
    # flag absent -> 19,597 chars in 1.16 s; flag forced -> 43,535 chars in 15.19 s (the whole
    # seat fabric rides). This test measures the doorway a cold session actually reads.
    monkeypatch.delenv("LAPLACE_CUSTODY_LIVE", raising=False)
    rc = wake.main(["--grade", "0", "--person"])
    assert rc == 0
    text = capsys.readouterr().out
    payload = json.loads(text)
    camp = payload["verdict_layer"]["campaign_rows"]

    assert camp["next_act"], "which stage is next"
    assert isinstance(camp["next_act_title"], str) and camp["next_act_title"], "what it builds"
    residuals = camp["next_act_gate_residuals"]
    assert residuals, "what the gate says is missing"
    assert isinstance(residuals, (list, dict))
    assert isinstance(camp["next_act_refs"], list), "what has happened inside the stage"
    wave = camp["last_wave_returned"]
    assert isinstance(wave, dict) and ("wave" in wave or "absent" in wave), "which wave last returned"

    # THE PROJECTION LAW IS NOT TRADED FOR THE FIELDS: the absolute cap the campaign quotes
    # (24,000 chars) holds on this CLI-equivalent run, and so does the payload's own declared cap.
    assert len(text) <= 24_000, "the campaign's quoted projection cap"
    assert len(text) <= payload["wake_projection"]["cap_chars"]
    assert len(json.dumps(camp)) < 4_000, "the campaign head is a head, not the campaign"


def test_the_campaign_head_carries_no_body_and_no_new_store():
    """Bounded, and from the rows: the four fields are heads and refs, never bodies, and the
    gate's residuals come from the banked verdict row - a truncated gate head is reported as
    itself, never as an empty list (absence and a dropped field must not read the same)."""
    assert wake._gate_residuals(None) is None
    assert wake._gate_residuals({"output_head": ""}) is None
    truncated = wake._gate_residuals({"output_head": '{"stage": "X", "residuals": ["a'})
    assert "gate_output_head" in truncated and "truncated" in truncated["note"]
    assert wake._gate_residuals({"output_head": '{"residuals": ["one", "two"]}'}) == ["one", "two"]
    assert wake._gate_residuals({"output_head": '{"stage": "X"}'})["note"].startswith("the gate printed no")

    camp = wake.campaign(ROOT, run_gates=False)
    assert camp["next_act_title"] == next(s["title"] for s in camp["stages"]
                                          if s["id"] == camp["next_act"]), "the row's own title"
    last = wake._last_wave_returned(ROOT)
    assert set(last) <= {"wave", "run_id", "status", "accepted", "at", "descend", "returns",
                         "chosen_from", "absent"}
    assert len(json.dumps(last)) < 600, "a head, not the run"
