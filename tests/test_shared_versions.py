"""W3.1 — THE VERSIONS JOIN.

``GET /shared/versions?corpus=`` joins, per project, THREE kinds of banked evidence
into ONE ts-ordered history (each row ``{kind, id, ts, label, paths, state}``):
snapshots (``versions/``), rounds (BOTH layouts, via ``convergence_ledger``), and
release history (``finalize.json`` + ``bundle_r*.json`` + minted ``*-DATE-rN.pdf``).

The contract these tests fail-close on:
  * a fabricated project with all three kinds joins them with correct ts-ordering;
  * never-run => an HONEST empty (``rows=[]``, ``never_run=True``) — never a fabricated
    row; an EMPTIED versions dir is present-but-empty, DISTINCT from never-run (F10);
  * the payload obeys the golden law (≤16KB per project — page/truncate LOUDLY beyond);
  * paths are repo-relative, never absolute;
  * the endpoint is PURE READS (no subprocess, no writes) and 400/404 fail-close.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.web import shared_ui
from laplace.manuscript import manuscript_versions

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# fixture builders — a manuscript dir with fabricated history of each kind.
# ---------------------------------------------------------------------------

def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj) if not isinstance(obj, str) else obj, encoding="utf-8")


def _snapshot(md: Path, name: str) -> None:
    (md / "versions" / name).mkdir(parents=True, exist_ok=True)
    _write(md / "versions" / name / "main.tex", "x")


def _harnessed_round(md: Path, n: int, date: str, open_findings: int) -> None:
    h = md / "rounds" / "harnessed"
    _write(h / f"mech_r{n}.json", {"date": date, "contract": {"hard": {"a": True}}})
    _write(h / f"detect_post_r{n}.json", {"open_findings_n": open_findings})


def _finalize(md: Path, slug: str, title: str, created: str, pdf_name: str | None) -> None:
    _write(md / "release" / "finalize.json",
           {"pdf_path": pdf_name, "slug": slug, "title": title, "created": created})


# ---------------------------------------------------------------------------
# THE JOIN — all three kinds, correct ts-ordering.
# ---------------------------------------------------------------------------

def test_join_unites_three_kinds_ts_ordered(tmp_path: Path) -> None:
    root = tmp_path
    md = root / "proj" / "manuscript"
    md.mkdir(parents=True)

    _snapshot(md, "2026-07-01-early")                       # snapshot @ 07-01
    _harnessed_round(md, 1, "2026-07-05T12:00:00Z", 3)      # round   @ 07-05
    _harnessed_round(md, 2, "2026-07-06T12:00:00Z", 1)      # round   @ 07-06
    _finalize(md, "paper-r1", "The Paper", "2026-07-10T09:00:00", None)  # release @ 07-10
    _write(md / "paper-2026-07-11-r1.pdf", "%PDF")          # minted  @ 07-11

    out = manuscript_versions.versions_join(md, root)
    rows = out["rows"]

    kinds = {r["kind"] for r in rows}
    assert kinds == {"snapshot", "round", "release"}, kinds
    assert out["counts"] == {"snapshot": 1, "round": 2, "release": 2, "total": 5}
    assert out["never_run"] is False

    # ts-ordered, NEWEST FIRST — monotonically non-increasing.
    tss = [r["ts"] for r in rows]
    assert tss == sorted(tss, reverse=True), tss
    # newest is the minted pdf (07-11), oldest is the snapshot (07-01)
    assert rows[0]["kind"] == "release" and "2026-07-11" in rows[0]["ts"]
    assert rows[-1]["kind"] == "snapshot" and "2026-07-01" in rows[-1]["ts"]

    # every row carries the full contract; paths are repo-relative (never absolute).
    for r in rows:
        assert set(r) >= {"kind", "id", "ts", "label", "paths", "state"}
        for pth in r["paths"]:
            assert not pth.startswith("/"), f"absolute path leaked: {pth}"
            assert "manuscript" in pth


def test_round_both_layouts_and_econ_only(tmp_path: Path) -> None:
    root = tmp_path
    md = root / "proj" / "manuscript"
    md.mkdir(parents=True)
    # harnessed layout + an economics-only orphan round (cost banked, no record)
    _harnessed_round(md, 1, "2026-07-05T00:00:00Z", 2)
    _write(md / "rounds" / "economics.json", {"1": 1.23, "9": 4.56})
    _write(md / "rounds" / "lock_r1.json", {"locked": True})

    out = manuscript_versions.versions_join(md, root)
    rounds = [r for r in out["rows"] if r["kind"] == "round"]
    by_id = {r["id"]: r for r in rounds}
    assert by_id["r1"]["state"] == "locked"                 # a lock file => locked
    assert by_id["r9"]["state"] == "economics-only"         # orphan cost, labeled honestly
    assert "economics-only" in by_id["r9"]["label"]


def test_judge_rounds_layout(tmp_path: Path) -> None:
    root = tmp_path
    md = root / "proj" / "manuscript"
    md.mkdir(parents=True)
    _write(md / "judge_rounds" / "2026-07-03_round1.json",
           {"round": 1, "date": "2026-07-03T00:00:00Z", "panel": [{"flags": ["a", "b"]}]})
    out = manuscript_versions.versions_join(md, root)
    rounds = [r for r in out["rows"] if r["kind"] == "round"]
    assert len(rounds) == 1
    assert rounds[0]["state"] == "2 open"                   # panel flags => open count
    assert out["sources"]["rounds"]["layout"] == "judge_rounds"


# ---------------------------------------------------------------------------
# HONESTY — never-run vs the emptied dir (repair F10's THE distinction).
# ---------------------------------------------------------------------------

def test_never_run_is_honest_empty(tmp_path: Path) -> None:
    root = tmp_path
    md = root / "proj" / "manuscript"
    md.mkdir(parents=True)                                   # nothing else on disk
    out = manuscript_versions.versions_join(md, root)
    assert out["rows"] == []
    assert out["never_run"] is True
    assert out["counts"]["total"] == 0
    # no source ever touched
    assert out["sources"]["snapshots"]["present"] is False
    assert out["sources"]["rounds"]["present"] is False
    assert out["sources"]["release"]["present"] is False


def test_emptied_dir_distinct_from_never_run(tmp_path: Path) -> None:
    root = tmp_path
    md = root / "proj" / "manuscript"
    (md / "versions").mkdir(parents=True)                    # exists, but emptied
    out = manuscript_versions.versions_join(md, root)
    assert out["rows"] == []
    # the dir was TOUCHED — never_run is False; the story is present-but-empty.
    assert out["never_run"] is False
    assert out["sources"]["snapshots"]["present"] is True
    assert out["sources"]["snapshots"]["empty"] is True


# ---------------------------------------------------------------------------
# BOUNDED — the golden law, enforced not asserted (loud truncation).
# ---------------------------------------------------------------------------

def test_payload_bound_enforced_loudly(tmp_path: Path) -> None:
    root = tmp_path
    md = root / "proj" / "manuscript"
    md.mkdir(parents=True)
    # fabricate far more than 16KB of snapshot rows (dated names so ts sorts).
    for i in range(400):
        _snapshot(md, f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}-snap-{i:04d}-longnamefiller")

    out = manuscript_versions.versions_join(md, root)
    size = len(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    assert size <= manuscript_versions._VERSIONS_MAX_BYTES, size
    assert out["truncated"] is True                          # LOUD, never silent
    assert out["omitted"] > 0
    # counts stay the HONEST discovered totals (not the shed-down shown count)
    assert out["counts"]["snapshot"] == 400
    assert len(out["rows"]) + out["omitted"] == 400
    # the oldest were shed — the surviving rows are still newest-first
    tss = [r["ts"] for r in out["rows"]]
    assert tss == sorted(tss, reverse=True)


# ---------------------------------------------------------------------------
# THE ENDPOINT — corpus resolution + fail-closed status + pure reads.
# ---------------------------------------------------------------------------

def test_endpoint_requires_corpus() -> None:
    st, _, body = shared_ui.handle("/shared/versions", {})
    assert st == 400
    assert b"corpus" in body


def test_endpoint_unknown_corpus_404() -> None:
    st, _, _ = shared_ui.handle("/shared/versions", {"corpus": "no-such-project"})
    assert st == 404
    # a path-shaped name never resolves (traversal fence)
    st2, _, _ = shared_ui.handle("/shared/versions", {"corpus": "../etc"})
    assert st2 == 404


def test_endpoint_real_corpus_joins(tmp_path: Path) -> None:
    # subset-sum-itqde has hand-placed versions + judge_rounds on the real tree.
    out = manuscript_versions.versions_payload("subset-sum-itqde")
    assert out is not None
    assert out["corpus"] == "subset-sum-itqde"
    assert out["counts"]["snapshot"] >= 1                    # real banked snapshots
    for r in out["rows"]:
        for pth in r["paths"]:
            assert not pth.startswith("/")                   # repo-relative on the real tree


def test_endpoint_pure_reads_no_writes(tmp_path: Path, monkeypatch) -> None:
    # the join must never spawn a subprocess (PSU / pure-read law).
    import subprocess
    def _boom(*a, **k):
        raise AssertionError("versions join spawned a subprocess — not a pure read")
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    out = manuscript_versions.versions_payload("subset-sum-itqde")
    assert out is not None
