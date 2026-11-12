"""THE EVOLUTION DESK (evolution_surface + read_ratify_queue + fitness_panel).

The judgment stage as a surface: the queue is a pure read; ratify is his word —
armed, attributed, transactional; hold is a typed DEFER; reject is a revocation
without apply. The draft-only law holds structurally: the ratify door is the one
apply path and it fail-closes on everything.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.web import evolution_surface as ev
from laplace.pipeline import adjudicate as adj
from laplace.pipeline import evolution_consumer as ec

CORPUS = "desk-fixture"


@pytest.fixture
def desk(tmp_path, monkeypatch):
    """A manuscript with one drafted contract + its open intent on the ledger."""
    md = tmp_path / "manuscript"
    (md / "feedback").mkdir(parents=True)
    intent = adj.make_conceptric_intent(
        "s", "content-missing", note="[ungrounded] a lost move",
        project=CORPUS, rec_id="CI-20260720-000000-000001")
    intent["gap"] = {"quote": "His lost sentence, verbatim.",
                     "context": "The paragraph around his lost sentence."}
    (md / "feedback" / "feedback.jsonl").write_text(
        json.dumps(intent) + "\n", encoding="utf-8")
    res = ec.draft_contract(intent, None, CORPUS, md / "evolution", repo_root=tmp_path)
    assert not res.get("escalated"), res
    monkeypatch.setattr(ev, "_resolve_md", lambda c: md if c == CORPUS else None)
    return md


def test_queue_reads_the_drafted_contract(desk):
    q = ec.read_ratify_queue(desk)
    assert q["present"] and q["counts"] == {"open": 1}
    row = q["queue"][0]
    assert row["status"] == "open"
    assert row["substance"] == "His lost sentence, verbatim."
    assert row["context_present"] and "paragraph around" in row["context"]


def test_ratify_fail_closes_unattributed_and_unarmed(desk):
    q = ec.read_ratify_queue(desk)
    iid = q["queue"][0]["intent_id"]
    st, obj = ev.ratify(CORPUS, iid, "", armed=True)
    assert st == 422 and "by required" in obj["error"]
    st, obj = ev.ratify(CORPUS, iid, "gerard", armed=False)
    assert st == 200 and obj["needs_arming"] is True
    # nothing applied, nothing banked — the queue is unchanged
    assert ec.read_ratify_queue(desk)["counts"] == {"open": 1}


def test_ratify_unknown_intent_404s(desk):
    st, obj = ev.ratify(CORPUS, "CI-nope", "gerard", armed=True)
    assert st == 404


def test_hold_banks_a_typed_defer(desk):
    iid = ec.read_ratify_queue(desk)["queue"][0]["intent_id"]
    st, obj = ev.hold(CORPUS, iid, "gerard", note="thinking")
    assert st == 200 and obj["status"] == "held"
    q = ec.read_ratify_queue(desk)
    assert q["counts"] == {"held": 1}
    # a second hold on a held intent refuses (not open)
    st, obj = ev.hold(CORPUS, iid, "gerard")
    assert st == 409


def test_reject_retires_without_apply(desk):
    iid = ec.read_ratify_queue(desk)["queue"][0]["intent_id"]
    st, obj = ev.reject(CORPUS, iid, "gerard", reason="not this claim")
    assert st == 200 and obj["status"] == "rejected"
    q = ec.read_ratify_queue(desk)
    assert q["counts"] == {"rejected": 1}
    assert "REJECTED at the evolution desk" in q["queue"][0]["hold_reason"]
    # the ledger record is append-only + attributed
    recs = [json.loads(l) for l in
            (desk / "feedback" / "feedback.jsonl").read_text().splitlines()]
    rev = [r for r in recs if r.get("record") == adj.INTENT_REVOKE]
    assert rev and rev[-1]["provenance"]["actor"] == "gerard"


def test_handle_routes_and_400s(desk):
    st, ctype, body = ev.handle("/evolution/queue", {"corpus": [CORPUS]}, "GET", b"")
    assert st == 200 and json.loads(body)["present"]
    st, _, body = ev.handle("/evolution/queue", {}, "GET", b"")
    assert st == 400
    st, _, body = ev.handle("/evolution/ratify", {}, "POST", b"not json")
    assert st == 400
    assert ev.handle("/not-ours", {}, "GET", b"") is None


def test_fitness_reader_degrades_honestly(tmp_path):
    from laplace.pipeline import fitness_panel as fp
    r = fp.read_fitness("no-such-corpus", tmp_path)
    assert r["present"] is False


# ── THE RATIFY-MODE DIAL + BULK DOOR (his 2026-07-21 ruling) ─────────────────────


def test_queue_payload_carries_mode_and_elsewhere(desk, monkeypatch):
    """GET /evolution/queue names the door shape AND every other project with
    open intents (the empty-panel pointer)."""
    monkeypatch.setattr(ev, "_elsewhere_counts", lambda c: {"other-corpus": 3})
    st, _, body = ev.handle("/evolution/queue", {"corpus": [CORPUS]}, "GET", b"")
    obj = json.loads(body)
    assert st == 200
    assert obj["ratify_mode"] in ("per-item", "bulk-arm")
    assert obj["elsewhere"] == {"other-corpus": 3}


def test_bulk_door_closed_under_per_item(desk, monkeypatch):
    """Under the default dial the bulk door REFUSES, naming the flip."""
    monkeypatch.setattr(ev, "_ratify_mode", lambda: "per-item")
    st, obj = ev.ratify_all(CORPUS, "gerard", armed=True)
    assert st == 409 and "ratify_mode" in obj["error"]


def test_bulk_unattributed_fail_closes(desk, monkeypatch):
    monkeypatch.setattr(ev, "_ratify_mode", lambda: "bulk-arm")
    st, obj = ev.ratify_all(CORPUS, "", armed=True)
    assert st == 422 and "by required" in obj["error"]


def test_bulk_arm_previews_every_open_application(desk, monkeypatch):
    """The unarmed POST is the informed second click: full per-intent preview,
    nothing applied, nothing banked."""
    monkeypatch.setattr(ev, "_ratify_mode", lambda: "bulk-arm")
    st, obj = ev.ratify_all(CORPUS, "gerard", armed=False)
    assert st == 200 and obj["needs_arming"] is True and obj["count"] == 1
    assert obj["preview"][0]["substance"] == "His lost sentence, verbatim."
    assert ec.read_ratify_queue(desk)["counts"] == {"open": 1}


def test_bulk_armed_applies_each_through_the_one_leg(desk, monkeypatch):
    monkeypatch.setattr(ev, "_ratify_mode", lambda: "bulk-arm")
    seen: list[str] = []

    def fake_apply(md, corpus, row, by, *, door=""):
        seen.append(row["intent_id"])
        return True, {"intent_id": row["intent_id"], "applied": "node-x",
                      "report": {}}
    monkeypatch.setattr(ev, "_apply_one", fake_apply)
    st, obj = ev.ratify_all(CORPUS, "gerard", armed=True)
    assert st == 200 and obj["ok"] and obj["count"] == 1 == len(seen)


def test_bulk_stops_on_first_failure_and_names_the_rest(desk, monkeypatch):
    """A failed apply STOPS the bulk: what landed is reported, the failure is
    named, the remainder stays open — no partial silence."""
    monkeypatch.setattr(ev, "_ratify_mode", lambda: "bulk-arm")
    monkeypatch.setattr(
        ev, "_apply_one",
        lambda md, corpus, row, by, door="": (False, {"intent_id": row["intent_id"],
                                                      "error": "apply failed — nothing banked"}))
    st, obj = ev.ratify_all(CORPUS, "gerard", armed=True)
    assert st == 422 and obj["applied"] == []
    assert obj["failed"]["intent_id"]
    assert obj["remaining"] == []


def test_ratify_mode_degrades_to_per_item_on_unreadable_dials(monkeypatch):
    import laplace.pipeline.dials as dials_mod
    monkeypatch.setattr(dials_mod, "load_dials",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert ev._ratify_mode() == "per-item"


# ── RETENTION AT THE DOORS (P3) ──────────────────────────────────────────────────
# The apply/reject doors bank a DOORED retention fate (source="door"); a hold banks
# NOTHING (a DEFER is not a fate). Telemetry never breaks a door.


def _capture_retention(monkeypatch):
    import laplace.engine.telemetry as tel
    calls: list[dict] = []
    monkeypatch.setattr(tel, "retention", lambda **k: calls.append(k) or {})
    return calls


def test_ratify_banks_a_doored_kept(desk, monkeypatch):
    """A successful ratify banks retention(fate='kept', source='door')."""
    import laplace.pipeline.evolve as evolve_mod
    monkeypatch.setattr(evolve_mod, "execute",
                        lambda *a, **k: {"ok": True, "round_trip_exact": True,
                                         "added": ["node-x"], "removed": []})
    calls = _capture_retention(monkeypatch)
    iid = ec.read_ratify_queue(desk)["queue"][0]["intent_id"]
    st, obj = ev.ratify(CORPUS, iid, "gerard", armed=True)
    assert st == 200 and obj["ok"]
    assert len(calls) == 1
    assert calls[0]["fate"] == "kept" and calls[0]["source"] == "door"
    assert calls[0]["artifact"] == f"{CORPUS}:{iid}"


def test_reject_banks_a_doored_bypassed(desk, monkeypatch):
    """A reject banks retention(fate='bypassed', source='door') — the real loss."""
    calls = _capture_retention(monkeypatch)
    iid = ec.read_ratify_queue(desk)["queue"][0]["intent_id"]
    st, obj = ev.reject(CORPUS, iid, "gerard", reason="not this claim")
    assert st == 200 and obj["status"] == "rejected"
    assert len(calls) == 1
    assert calls[0]["fate"] == "bypassed" and calls[0]["source"] == "door"


def test_hold_banks_no_retention(desk, monkeypatch):
    """A HOLD is a typed DEFER, not a fate — nothing is banked to retention."""
    calls = _capture_retention(monkeypatch)
    iid = ec.read_ratify_queue(desk)["queue"][0]["intent_id"]
    st, obj = ev.hold(CORPUS, iid, "gerard", note="thinking")
    assert st == 200 and obj["status"] == "held"
    assert calls == []


def test_retention_failure_never_breaks_the_apply(desk, monkeypatch):
    """A raising telemetry.retention must not sink a proven apply."""
    import laplace.pipeline.evolve as evolve_mod
    import laplace.engine.telemetry as tel
    monkeypatch.setattr(evolve_mod, "execute",
                        lambda *a, **k: {"ok": True, "round_trip_exact": True,
                                         "added": ["node-x"], "removed": []})
    monkeypatch.setattr(tel, "retention",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    iid = ec.read_ratify_queue(desk)["queue"][0]["intent_id"]
    st, obj = ev.ratify(CORPUS, iid, "gerard", armed=True)
    assert st == 200 and obj["ok"]


# ── THE FITNESS STAMP (P3) ───────────────────────────────────────────────────────
# fitness_at_draft rides the contract meta + the queue row; fitness_now rides the
# payload once per read. Fields only — no threshold, no ordering.


def test_fitness_stamp_rides_the_draft_and_the_queue(tmp_path, monkeypatch):
    from laplace.pipeline import fitness_panel as fp
    panel = {"present": True,
             "debt_trajectory": [{"at": "2026-07-20", "n": 9},
                                 {"at": "2026-07-21", "n": 4}],
             "freeze": {"pass": True, "mechanical_pass": True},
             "r10_clean": True}
    monkeypatch.setattr(fp, "read_fitness", lambda *a, **k: panel)

    md = tmp_path / "manuscript"
    (md / "feedback").mkdir(parents=True)
    intent = adj.make_conceptric_intent(
        "s", "content-missing", note="[ungrounded] a lost move",
        project="fitness-fixture", rec_id="CI-20260721-000000-000001")
    intent["gap"] = {"quote": "A lost sentence.", "context": "Its paragraph."}
    (md / "feedback" / "feedback.jsonl").write_text(
        json.dumps(intent) + "\n", encoding="utf-8")

    res = ec.draft_contract(intent, None, "fitness-fixture", md / "evolution",
                            repo_root=tmp_path)
    assert not res.get("escalated"), res
    # the drafted contract's meta carries the fitness AT DRAFT time
    plan = json.loads((Path(res["evolution_dir"]) / "evolution_plan.json").read_text())
    faf = plan["meta"]["fitness_at_draft"]
    assert faf == {"debt_n": 4, "freeze_pass": True, "r10_clean": True,
                   "at": "2026-07-21"}

    # the queue row carries fitness_at_draft; the payload carries fitness_now (once)
    q = ec.read_ratify_queue(md, "fitness-fixture")
    row = q["queue"][0]
    assert row["fitness_at_draft"] == faf
    assert q["fitness_now"] == faf


def test_fitness_now_absent_without_a_corpus(tmp_path, monkeypatch):
    """No corpus named → no fitness_now key (byte-compatible for the old callers)."""
    md = tmp_path / "manuscript"
    (md / "feedback").mkdir(parents=True)
    q = ec.read_ratify_queue(md)
    assert "fitness_now" not in q
