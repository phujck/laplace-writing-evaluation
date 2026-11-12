"""walk_requests — the one reader for typed REQUEST rows the redline walk banks.

Synthetic feedback ledgers only (the ``_ledger`` fixture idiom mirrors
``tests/test_review_surface.py``'s ``_make``); the registry seam is exercised
either through an explicit ``ledger=`` path (bypassing ``project_context``
entirely — the cleanest seam for row-shape tests) or through a monkeypatched
``registry.project_context`` (for the "registered corpus, no ledger yet"
branch). No live corpus, no network, no LaTeX.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.manuscript import walk_requests as wr

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# fixtures — a synthetic feedback ledger
# ---------------------------------------------------------------------------

def _ledger(tmp_path: Path, rows: list[dict]) -> Path:
    fb = tmp_path / "manuscript" / "feedback"
    fb.mkdir(parents=True)
    path = fb / "feedback.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _rows() -> list[dict]:
    return [
        # find-refs, no rationale
        {"id": "FB-1", "ts": "2026-08-01T10:00:00", "by": "gerard",
         "comment": "request: find supporting references for this passage",
         "scope": "delivery",
         "anchor": {"section": "intro", "paragraph_id": "p3",
                    "quote": "some passage", "coarse": False, "grade": "paragraph"}},
        # find-refs, with rationale
        {"id": "FB-2", "ts": "2026-08-01T10:05:00", "by": "gerard",
         "comment": "request: find supporting references for this passage"
                    " — check arXiv too",
         "scope": "delivery",
         "anchor": {"section": "intro", "paragraph_id": "p4",
                    "quote": "another passage", "coarse": False, "grade": "paragraph"}},
        # remake-figure — the figure door: anchor carries figure + block
        {"id": "FB-3", "ts": "2026-08-01T10:10:00", "by": "gerard",
         "comment": "request: remake this figure (fig:spectrum)",
         "scope": "delivery",
         "anchor": {"section": "results", "figure": "fig:spectrum", "block": "blk-7",
                    "quote": "", "grade": "figure", "coarse": True}},
        # new-section — the ask's own text already carries one " — ", plus a typed note
        {"id": "FB-4", "ts": "2026-08-01T10:15:00", "by": "gerard",
         "comment": "request: a new section after §Discussion"
                    " — the note carries the proposal — add ablations",
         "scope": "structure",
         "anchor": {"section": "discussion", "grade": "section", "coarse": True}},
        # other-request — starts with "request:" but matches none of the three shapes
        {"id": "FB-5", "ts": "2026-08-01T10:20:00", "by": "gerard",
         "comment": "request: something unforeseen entirely",
         "anchor": {"section": "conclusion", "grade": "section", "coarse": True}},
        # a plain comment — excluded, does not start with "request:"
        {"id": "FB-6", "ts": "2026-08-01T10:25:00", "by": "gerard",
         "comment": "this passage is unclear", "kind": "comment",
         "anchor": {"section": "intro", "grade": "section"}},
        # a rewrite row — excluded, its comment is a rewrite summary, not a request
        {"id": "FB-7", "ts": "2026-08-01T10:30:00", "by": "gerard",
         "comment": "rewrote sec1:1-4", "kind": "author-rewrite",
         "anchor": {"section": "intro", "file": "sec1.tex", "grade": "rewrite"}},
        # the revoke: a resolution record superseding FB-1 (no "comment" field at all —
        # exactly the shape adjudicate.make_resolution mints; it must never be mistaken
        # for a request itself).
        {"id": "RES-1", "record": "resolution", "ts": "2026-08-01T11:00:00",
         "supersedes": "FB-1", "kind": "comment", "section": "intro",
         "status": "resolved", "source": "gerard",
         "text": "revoke finding 'FB-1'",
         "provenance": {"actor": "gerard", "verdict": "revoke-finding",
                        "round": 0, "ts": "2026-08-01T11:00:00"}},
    ]


# ---------------------------------------------------------------------------
# collect() — typed parsing, rationale split, exclusions, revoke, counts
# ---------------------------------------------------------------------------

def test_collect_types_and_fallback(tmp_path):
    path = _ledger(tmp_path, _rows())
    out = wr.collect("synthetic-corpus", ledger=path)
    assert out["corpus"] == "synthetic-corpus"
    assert out["ledger"] == str(path)
    by_id = {r["id"]: r for r in out["requests"]}
    assert set(by_id) == {"FB-1", "FB-2", "FB-3", "FB-4", "FB-5"}
    assert by_id["FB-1"]["type"] == "find-refs"
    assert by_id["FB-2"]["type"] == "find-refs"
    assert by_id["FB-3"]["type"] == "remake-figure"
    assert by_id["FB-4"]["type"] == "new-section"
    assert by_id["FB-5"]["type"] == "other-request"


def test_collect_rationale_split(tmp_path):
    path = _ledger(tmp_path, _rows())
    out = wr.collect("synthetic-corpus", ledger=path)
    by_id = {r["id"]: r for r in out["requests"]}
    assert by_id["FB-1"]["rationale"] == ""
    assert by_id["FB-2"]["rationale"] == "check arXiv too"
    assert by_id["FB-3"]["rationale"] == ""
    # only the FIRST " — " splits; the rest of the ask's own template text rides
    # along inside the rationale untouched.
    assert by_id["FB-4"]["rationale"] == "the note carries the proposal — add ablations"
    assert by_id["FB-4"]["text"] == (
        "request: a new section after §Discussion"
        " — the note carries the proposal — add ablations")


def test_collect_anchor_fields_whitelisted_and_normalised(tmp_path):
    path = _ledger(tmp_path, _rows())
    out = wr.collect("synthetic-corpus", ledger=path)
    by_id = {r["id"]: r for r in out["requests"]}
    # paragraph_id / coarse / grade are NOT in the whitelist; empty quote is dropped.
    assert by_id["FB-1"]["anchor"] == {"section": "intro", "quote": "some passage"}
    assert by_id["FB-3"]["anchor"] == {
        "section": "results", "figure": "fig:spectrum", "block": "blk-7"}
    assert by_id["FB-4"]["anchor"] == {"section": "discussion"}


def test_collect_scope_passthrough(tmp_path):
    path = _ledger(tmp_path, _rows())
    out = wr.collect("synthetic-corpus", ledger=path)
    by_id = {r["id"]: r for r in out["requests"]}
    assert by_id["FB-1"]["scope"] == "delivery"
    assert by_id["FB-4"]["scope"] == "structure"
    assert by_id["FB-5"]["scope"] == ""          # never banked with a scope — unscoped


def test_collect_excludes_non_requests_and_rewrites(tmp_path):
    path = _ledger(tmp_path, _rows())
    out = wr.collect("synthetic-corpus", ledger=path)
    ids = {r["id"] for r in out["requests"]}
    assert "FB-6" not in ids               # plain comment, no "request:" prefix
    assert "FB-7" not in ids               # rewrite row
    assert "RES-1" not in ids              # the revoke record itself is not a request


def test_collect_revoke_flags_without_dropping(tmp_path):
    path = _ledger(tmp_path, _rows())
    out = wr.collect("synthetic-corpus", ledger=path)
    by_id = {r["id"]: r for r in out["requests"]}
    assert by_id["FB-1"]["revoked"] is True
    for rid in ("FB-2", "FB-3", "FB-4", "FB-5"):
        assert by_id[rid]["revoked"] is False
    # append-only: the revoked row is KEPT, only flagged.
    assert "FB-1" in by_id


def test_collect_counts(tmp_path):
    path = _ledger(tmp_path, _rows())
    out = wr.collect("synthetic-corpus", ledger=path)
    assert out["counts"] == {
        "find-refs": 2, "remake-figure": 1, "new-section": 1, "other-request": 1,
        "total": 5, "revoked": 1,
    }


def test_pending_excludes_revoked(tmp_path):
    path = _ledger(tmp_path, _rows())
    pend = wr.pending("synthetic-corpus", ledger=path)
    ids = {r["id"] for r in pend}
    assert ids == {"FB-2", "FB-3", "FB-4", "FB-5"}
    assert all(not r["revoked"] for r in pend)


def test_ledger_relpath_against_repo_root(tmp_path):
    path = _ledger(tmp_path, _rows())
    out = wr.collect("synthetic-corpus", repo_root=tmp_path, ledger=path)
    assert out["ledger"] == "manuscript/feedback/feedback.jsonl"


# ---------------------------------------------------------------------------
# absent ledger / unknown corpus — never a raise, always an honest note
# ---------------------------------------------------------------------------

def test_collect_unknown_corpus_never_raises(tmp_path):
    out = wr.collect("definitely-not-a-registered-corpus-xyz", repo_root=tmp_path)
    assert out == {"corpus": "definitely-not-a-registered-corpus-xyz",
                    "ledger": None, "requests": [], "counts": {}, "note": out["note"]}
    assert out["note"]
    assert isinstance(out["note"], str)


def test_collect_registered_corpus_no_ledger_file_yet(tmp_path, monkeypatch):
    from laplace.pipeline import registry as reg

    class _Ctx:
        feedback_ledger = tmp_path / "manuscript" / "feedback" / "feedback.jsonl"

    monkeypatch.setattr(reg, "project_context", lambda name, repo_root=None: _Ctx())
    out = wr.collect("some-registered-corpus")
    assert out["corpus"] == "some-registered-corpus"
    assert out["ledger"] is None
    assert out["requests"] == []
    assert out["counts"] == {}
    assert "no feedback ledger" in out["note"]


def test_collect_registered_corpus_no_ledger_declared(tmp_path, monkeypatch):
    from laplace.pipeline import registry as reg

    class _Ctx:
        feedback_ledger = None

    monkeypatch.setattr(reg, "project_context", lambda name, repo_root=None: _Ctx())
    out = wr.collect("some-other-corpus")
    assert out["ledger"] is None
    assert out["requests"] == []
    assert out["counts"] == {}
    assert out["note"]


def test_pending_on_absent_ledger_is_empty_list(tmp_path):
    assert wr.pending("definitely-not-a-registered-corpus-xyz", repo_root=tmp_path) == []
