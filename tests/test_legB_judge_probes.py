"""legB-judge — adversarial probes banked for B-1 (the G-surface landing view).

A FRESH judge re-derived, not re-read, the B-1 claims (commit 3735e06): the
dismissal-audit stratification math, the mass-revoke class semantics, the
agree->calibrate roundtrip through the EXISTING adjudicate door, and the graceful
degradation of the manuscript-locator + artefact resolver. These are the probes
that PASSED against HEAD; the ones that surfaced a defect (the esc() single-quote
attribute-injection sink, the un-confirmed mass revoke) are recorded as FINDINGS in
the verdict, not asserted here (a regression test for an unfixed defect would fail).

Pure-logic over synthetic trees (the internal functions take a Path directly), the
same idiom as test_review_surface.py — no browser, no LaTeX, no live tree touched.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.manuscript import review_surface as rv
from laplace.pipeline import suppress as S

pytestmark = pytest.mark.unit


def _manuscript(tmp_path, suppressions=(), other=(), *, s1_text="Original body.\n"):
    """A synthetic manuscript: main.tex -> S1.tex, a feedback ledger of the given
    suppression + other records. Returns the md Path."""
    md = tmp_path / "wp"
    (md / "feedback").mkdir(parents=True)
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\\input{S1}\\end{document}",
        encoding="utf-8")
    (md / "S1.tex").write_text(s1_text, encoding="utf-8")
    (md / "main.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    recs = list(other) + list(suppressions)
    (md / "feedback" / "feedback.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return md


# ---------------------------------------------------------------------------
# probe 4 — stratification math: the (kind, fingerprint) fold is exact
# ---------------------------------------------------------------------------

def test_stratification_folds_by_kind_and_fingerprint(tmp_path):
    # 5 suppressions: 3 share (eq-unused, "body-A"), 1 is (eq-unused, "body-B"),
    # 1 is (citation-uncited, "body-A") -> 3 distinct classes, 5 dismissals.
    supps = [
        S.make_suppression("def:a", "eq-unused", "body-A", reason="dup",
                           actor="machine", round=1, rec_id="S1"),
        S.make_suppression("def:b", "eq-unused", "body-A", reason="dup",
                           actor="machine", round=1, rec_id="S2"),
        S.make_suppression("def:c", "eq-unused", "body-A", reason="dup",
                           actor="machine", round=1, rec_id="S3"),
        S.make_suppression("def:d", "eq-unused", "body-B", reason="other",
                           actor="machine", round=1, rec_id="S4"),
        S.make_suppression("def:e", "citation-uncited", "body-A", reason="cit",
                           actor="machine", round=1, rec_id="S5"),
    ]
    md = _manuscript(tmp_path, supps)
    aud = rv.dismissal_audit(md)
    assert aud["counts"]["classes"] == 3
    assert aud["counts"]["dismissals"] == 5
    # the 3-suppression class is the biggest and sorts to the top
    assert aud["rows"][0]["count"] == 3
    assert aud["rows"][0]["kind"] == "eq-unused"


def test_no_suppression_double_counted_or_dropped(tmp_path):
    supps = [S.make_suppression(f"def:n{i}", "eq-unused", f"body-{i % 3}",
                                reason="r", actor="machine", round=1,
                                rec_id=f"S{i}") for i in range(12)]
    md = _manuscript(tmp_path, supps)
    aud = rv.dismissal_audit(md)
    ids = [sid for r in aud["rows"] for sid in r["suppression_ids"]]
    assert len(ids) == 12                      # nothing dropped
    assert len(set(ids)) == 12                 # nothing double-counted
    assert aud["counts"]["dismissals"] == sum(r["count"] for r in aud["rows"])


def test_revoked_suppression_absent_from_audit(tmp_path):
    supps = [
        S.make_suppression("def:a", "eq-unused", "body", reason="r",
                           actor="machine", round=1, rec_id="S1"),
        S.make_suppression("def:b", "eq-unused", "body", reason="r",
                           actor="machine", round=1, rec_id="S2"),
    ]
    md = _manuscript(tmp_path, supps)
    assert rv.dismissal_audit(md)["counts"]["dismissals"] == 2
    # revoke one through the existing door -> load_suppressions drops it, audit follows
    res = rv.adjudicate(md, "p", {"by": "author", "verb": "revoke", "supersedes": "S1"})
    assert res["ok"], res
    assert rv.dismissal_audit(md)["counts"]["dismissals"] == 1


# ---------------------------------------------------------------------------
# probe 5 — mass-revoke class semantics: one class covering N suppressions
# ---------------------------------------------------------------------------

def test_overrule_mass_revoke_reborns_the_whole_class(tmp_path):
    # a single (kind, fingerprint) class of THREE suppressions: the UI's overrule
    # loops one revoke per id -> ALL three reborn. This is the mass-revoke edge.
    supps = [S.make_suppression(f"def:{c}", "eq-unused", "shared body", reason="r",
                                actor="machine", round=1, rec_id=f"S{c}")
             for c in "abc"]
    md = _manuscript(tmp_path, supps)
    aud = rv.dismissal_audit(md)
    assert len(aud["rows"]) == 1 and aud["rows"][0]["count"] == 3
    row = aud["rows"][0]
    for sid in row["suppression_ids"]:         # exactly what bankAudit(overrule) does
        assert rv.adjudicate(md, "p", {"by": "author", "verb": "revoke", "supersedes": sid})["ok"]
    assert rv.dismissal_audit(md)["counts"]["dismissals"] == 0


def test_widen_class_is_flagged_no_agree(tmp_path):
    # a WILDCARD (widen) suppression: a kind-less class cannot be recalibrated ->
    # widen True (the UI withholds AGREE), only overrule applies.
    supps = [S.make_suppression("def:a", S.WILDCARD, "body", reason="silence all",
                                actor="author", round=1, rec_id="W1")]
    md = _manuscript(tmp_path, supps)
    row = rv.dismissal_audit(md)["rows"][0]
    assert row["widen"] is True


# ---------------------------------------------------------------------------
# probe 6 — agree -> calibrate roundtrip through the EXISTING adjudicate door
# ---------------------------------------------------------------------------

def test_agree_calibrate_lands_and_reflects_and_idempotent(tmp_path):
    supps = [S.make_suppression("def:a", "eq-unused", "body", reason="r",
                                actor="machine", round=1, rec_id="S1")]
    md = _manuscript(tmp_path, supps)
    assert rv.dismissal_audit(md)["rows"][0]["calibrated"] is False
    res = rv.adjudicate(md, "p", {"by": "author", "verb": "calibrate", "finding_kind": "eq-unused"})
    assert res["ok"] and res["record"]["record"] == "calibration-intent"
    # the audit row now reads calibrated (the AGREE button greys to "agreed")
    assert rv.dismissal_audit(md)["rows"][0]["calibrated"] is True
    # the substrate queue surfaces the new intent
    assert any(q["finding_kind"] == "eq-unused"
               for q in rv.substrate_queue(md)["queue"])
    # idempotent: a second agree does not double-deposit
    again = rv.adjudicate(md, "p", {"by": "author", "verb": "calibrate", "finding_kind": "eq-unused"})
    assert again["ok"] and again.get("idempotent") is True


# ---------------------------------------------------------------------------
# probe 4 — the stale edge: dismissed content since changed -> surfaced stale
# ---------------------------------------------------------------------------

def test_stale_fingerprint_surfaced(tmp_path):
    # dismiss on section stem S1 against OLD text, then the fragment changes:
    # the class is stale (already reborn) and the audit says so.
    supps = [S.make_suppression("S1", "eq-unused", "OLD TEXT", reason="r",
                                actor="machine", round=1, rec_id="S1")]
    md = _manuscript(tmp_path, supps, s1_text="TOTALLY NEW TEXT\n")
    aud = rv.dismissal_audit(md)
    assert aud["counts"]["stale"] >= 1
    assert aud["rows"][0]["stale"] is True


# ---------------------------------------------------------------------------
# probe 3 — graceful degradation: no traceback on bad params / missing finalize
# ---------------------------------------------------------------------------

def test_missing_finalize_gives_null_clean_not_error(tmp_path):
    md = _manuscript(tmp_path)                  # no release/finalize.json, no slug pdf
    art = rv.artefacts(md)
    assert art["clean"] is None                 # named tab simply absent
    assert art["candidate"]["name"] == "main.pdf"


def test_unknown_corpus_and_escaping_dir_resolve_to_none():
    assert rv.manuscript_dir("no-such-corpus-xyz", "") is None
    assert rv.manuscript_dir("", "../../etc") is None      # the repo-root fence


def test_dismissal_audit_empty_ledger_is_clean_zero(tmp_path):
    md = tmp_path / "wp"
    md.mkdir()
    (md / "main.tex").write_text("x", encoding="utf-8")
    aud = rv.dismissal_audit(md)
    assert aud["rows"] == []
    assert aud["counts"] == {"classes": 0, "dismissals": 0, "stale": 0,
                             "machine": 0, "author": 0}
