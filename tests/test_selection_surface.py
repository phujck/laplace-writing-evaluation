"""THE SELECTION DESK (selection_surface) — heredity's ratify stage as a door.

Record-only: a selection ruling banks his verdict (promote/hold/retire) against ONE
scored generation and mutates NO artifact. The draft-only spirit holds — the door
fail-closes on a bad verdict, an unattributed word, an unknown generation, and a
generation that already carries a ruling (contested by a later record, never mutated).

The two frozen P1/P2 interfaces (the generation ledger, the selection sheet) land in
parallel, so these tests exercise the surface's OWN idioms: a hand-built
``generations.jsonl`` stands in for the ledger, and ``_draft_preview`` is monkeypatched
to stand in for the sheet.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.web import selection_surface as sel
from laplace.pipeline import adjudicate as adj

CORPUS = "selection-fixture"
GEN = "GEN-20260721-000001"


@pytest.fixture
def desk(tmp_path, monkeypatch):
    """A manuscript with a hand-built generations ledger (one scored generation) and
    an empty feedback ledger. ``_resolve_md`` and ``_draft_preview`` are monkeypatched
    so the surface never reaches the not-yet-landed P1/P2 modules."""
    md = tmp_path / "manuscript"
    (md / "feedback").mkdir(parents=True)
    row = {"id": GEN, "record": "generation", "n": 3, "corpus": CORPUS,
           "stamped_at": "2026-07-21T00:00:00",
           "debt": [12, 4], "freeze_pass": True, "r10_clean": True}
    (md / "generations.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(sel, "_resolve_md", lambda c: md if c == CORPUS else None)
    # the live draft the sheet would carry for this generation — the REAL sheet-row
    # shape (dict draft_verdict + the sheet's computed numbers), so the digest path
    # under test is the production one, not a convenience stub.
    sheet_row = {"id": GEN, "debt_before": 12, "debt_after": 4,
                 "freeze": {"pass": True}, "r10": {"clean": True},
                 "draft_verdict": {"verdict": "promote", "draft": True}}
    monkeypatch.setattr(sel, "_draft_preview",
                        lambda c, g: ("promote", "psi-v1", sheet_row))
    return md


def _sel_records(md: Path) -> list[dict]:
    p = md / "feedback" / "feedback.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()
            and json.loads(l).get("record") == adj.SELECTION_RULING]


def test_bad_verdict_400s(desk):
    st, obj = sel.rule(CORPUS, GEN, "sideways", "gerard", armed=True)
    assert st == 400 and "verdict must be one of" in obj["error"]
    assert _sel_records(desk) == []


def test_unattributed_422s(desk):
    st, obj = sel.rule(CORPUS, GEN, "promote", "", armed=True)
    assert st == 422 and "by required" in obj["error"]
    assert _sel_records(desk) == []


def test_unknown_generation_404s(desk):
    st, obj = sel.rule(CORPUS, "GEN-nope", "promote", "gerard", armed=True)
    assert st == 404 and "no scored generation" in obj["error"]
    assert _sel_records(desk) == []


def test_no_manuscript_dir_404s(desk):
    st, obj = sel.rule("no-such-corpus", GEN, "promote", "gerard", armed=True)
    assert st == 404 and "no manuscript dir" in obj["error"]


def test_unarmed_preview_banks_nothing(desk):
    st, obj = sel.rule(CORPUS, GEN, "retire", "gerard", armed=False)
    assert st == 200 and obj["needs_arming"] is True
    # the informed second click: the draft it would override + the readings it rests on
    assert obj["draft_verdict"] == "promote"
    assert obj["readings_digest"] == {"debt": [12, 4], "freeze_pass": True,
                                      "r10_clean": True}
    # NOTHING banked
    assert _sel_records(desk) == []


def test_armed_banks_typed_record_overriding_the_draft(desk):
    """verdict != live draft ('promote') → overrode_draft True, one typed record."""
    st, obj = sel.rule(CORPUS, GEN, "retire", "gerard", armed=True, reason="collapsed")
    assert st == 200 and obj["ok"] and obj["overrode_draft"] is True
    recs = _sel_records(desk)
    assert len(recs) == 1
    r = recs[0]
    assert r["record"] == adj.SELECTION_RULING
    assert r["verdict"] == "retire" and r["draft_verdict"] == "promote"
    assert r["overrode_draft"] is True and r["rule_version"] == "psi-v1"
    assert r["generation_id"] == GEN and r["target"] == GEN
    assert r["status"] == "resolved"                    # an action, off every worklist
    assert r["provenance"]["actor"] == "gerard"
    assert r["readings_digest"]["debt"] == [12, 4]
    assert r["reason"] == "collapsed"


def test_armed_agreeing_with_the_draft_does_not_override(desk):
    """verdict == live draft ('promote') → overrode_draft False."""
    st, obj = sel.rule(CORPUS, GEN, "promote", "gerard", armed=True)
    assert st == 200 and obj["ok"] and obj["overrode_draft"] is False
    r = _sel_records(desk)[0]
    assert r["verdict"] == "promote" and r["overrode_draft"] is False


def test_duplicate_ruling_409s(desk):
    st, _ = sel.rule(CORPUS, GEN, "promote", "gerard", armed=True)
    assert st == 200
    # a second armed ruling on the same generation is refused — contest via a later
    # record, never a second live ruling
    st, obj = sel.rule(CORPUS, GEN, "retire", "gerard", armed=True)
    assert st == 409 and "already carries a selection ruling" in obj["error"]
    assert len(_sel_records(desk)) == 1


def test_handle_get_sheet_400s_without_corpus(desk):
    st, _, body = sel.handle("/selection/sheet", {}, "GET", b"")
    assert st == 400 and "corpus required" in json.loads(body)["error"]


def test_handle_get_sheet_404s_without_manuscript(desk):
    st, _, body = sel.handle("/selection/sheet", {"corpus": ["no-such-corpus"]},
                             "GET", b"")
    assert st == 404


def test_handle_routes_rule_and_returns_none_for_foreign_paths(desk):
    st, _, body = sel.handle("/selection/rule", {},
                             "POST", json.dumps({"corpus": CORPUS, "generation_id": GEN,
                                                 "verdict": "promote", "by": "gerard",
                                                 "armed": True}).encode())
    assert st == 200 and json.loads(body)["ok"]
    # bad json → 400; foreign path → None
    st, _, body = sel.handle("/selection/rule", {}, "POST", b"not json")
    assert st == 400
    assert sel.handle("/not-ours", {}, "GET", b"") is None


def test_handle_armed_is_strict_true_never_truthy(desk):
    """The arming gate fail-closes on malformed input: only JSON true arms —
    "yes"/"false"/1 read as UNARMED (the second click is the law at this door)."""
    for bad in ("yes", "false", 1, "true"):
        st, _, body = sel.handle("/selection/rule", {},
                                 "POST", json.dumps({"corpus": CORPUS,
                                                     "generation_id": GEN,
                                                     "verdict": "promote",
                                                     "by": "gerard",
                                                     "armed": bad}).encode())
        obj = json.loads(body)
        assert st == 200 and obj.get("needs_arming") is True, bad
    assert _sel_records(desk) == []


def test_concurrent_armed_rulings_bank_exactly_one(desk):
    """The 409 duplicate guard holds under the scanner's threading: N parallel armed
    calls on one generation bank EXACTLY ONE ruling (check-then-append is one
    critical section — the lockless door was proven racy, 2026-07-21 verifier)."""
    import threading
    results: list[int] = []

    def fire():
        st, _ = sel.rule(CORPUS, GEN, "promote", "gerard", armed=True)
        results.append(st)

    threads = [threading.Thread(target=fire) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(_sel_records(desk)) == 1
    assert results.count(200) == 1 and results.count(409) == 15


# ── THE REAL P2↔P3 SEAM (no _draft_preview stub): the door against the sheet the
# generation ledger and selection_sheet actually produce. The 2026-07-21 verifiers
# caught the door coded to a shape the sheet never emits — overrode_draft banked
# True on every agreeing ruling; this fixture is the regression fence. ────────────


@pytest.fixture
def real_seam(tmp_path, monkeypatch):
    """A REAL manuscript: dated reprojection artifacts, an R10 reader-report, a
    generation stamped through generation_ledger, and the sheet read by the real
    selection_sheet — only registry resolution is patched."""
    from laplace.pipeline import generation_ledger as gl
    md = tmp_path / "manuscript"
    (md / "feedback").mkdir(parents=True)
    (md / "reprojection").mkdir()
    (md / "reprojection" / "run_record_2026-07-20.json").write_text(json.dumps(
        {"at": "2026-07-20T00:00:00", "source_delta_before": {"n": 12},
         "source_delta_after": {"n": 4}}), encoding="utf-8")
    (md / "reprojection" / "freeze_verdict_2026-07-20.json").write_text(json.dumps(
        {"pass": True, "substance_pass": True, "mechanical_pass": True}),
        encoding="utf-8")
    (md / "feedback" / "feedback.jsonl").write_text(json.dumps(
        {"id": "RR-1", "record": "reader-report", "reader": "R10", "clean": True,
         "findings": []}) + "\n", encoding="utf-8")
    res = gl.stamp_generation(md, CORPUS, by="test")
    assert "error" not in res, res
    gen_id = res["id"]
    monkeypatch.setattr(sel, "_resolve_md", lambda c: md if c == CORPUS else None)
    from laplace.pipeline import registry

    class _P:
        name = CORPUS
        manuscript_dir = "manuscript"

        def path(self, _m, _r):
            return md
    monkeypatch.setattr(registry, "resolve",
                        lambda name: _P() if name == CORPUS else None)
    return md, gen_id


def test_real_seam_preview_carries_the_sheets_verdict(real_seam):
    md, gen_id = real_seam
    verdict, version, row = sel._draft_preview(CORPUS, gen_id)
    assert verdict in ("promote", "hold", "retire"), verdict
    from laplace.pipeline import dials as _d
    expected = (_d.load_dials().get("selection") or {}).get("draft_psi", "draft-psi-v1")
    assert version == expected
    assert row is not None and row.get("id") == gen_id


def test_real_seam_agreeing_ruling_never_lies_about_override(real_seam):
    """The HIGH finding's regression fence: rule with the sheet's own draft verdict
    → overrode_draft False, rule_version real, digest carrying real numbers."""
    md, gen_id = real_seam
    draft, version, _row = sel._draft_preview(CORPUS, gen_id)
    from laplace.pipeline import dials as _d
    expected = (_d.load_dials().get("selection") or {}).get("draft_psi", "draft-psi-v1")
    st, obj = sel.rule(CORPUS, gen_id, draft, "gerard", armed=True)
    assert st == 200 and obj["ok"]
    assert obj["overrode_draft"] is False
    assert obj["rule_version"] == expected
    assert obj["readings_digest"]["debt"] == [12, 4]
    assert obj["readings_digest"]["freeze_pass"] is True
    assert obj["readings_digest"]["r10_clean"] is True
    r = _sel_records(md)[0]
    assert r["overrode_draft"] is False and r["rule_version"] == expected
    assert r["readings_digest"]["debt"] == [12, 4]
