"""W0.3 — THE VERSIONS JOIN, REPAIRED to the two-root truth + the current-artefact weld.

The disease this fails-closed on (measured live): the version rail walked ONLY the
manuscript dir, so for subset-sum-itqde — whose ``versions/`` + ``judge_rounds/`` live
under the manuscript dir but whose harnessed rounds + release + minted PDFs live under
``whitepaper/`` (the resolved target dir) — the rail showed 5 snapshots + the judge
rounds and MISSED every harnessed round and the entire release history. And
``corpus_ingest.project_context`` resolved the CORPORA tex root (``tex/main.tex``, a
35-line STUB) while /review showed ``whitepaper/main.pdf`` (the real 20-page paper):
the paper vanished between nav clicks.

Two standing gates:

  (1) REVISION-COUNT PARITY — enumerate the disk truth (versions/* dirs, the
      rounds/harnessed round artifacts, judge_rounds/*round*.json, the release minted
      PDFs) and assert the JOIN carries every one — and specifically that the harnessed
      rounds + release rows NOW appear (the two halves that were invisible).

  (2) CURRENT-ARTEFACT AGREEMENT (the J3 server half) — ``corpus_ingest.project_context``
      and ``registry.project_context`` name the SAME pdf/tex, and for subset-sum-itqde
      that is the whitepaper artefact, never the tex stub.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.web import shared_ui
from laplace.manuscript import manuscript_versions
from laplace.pipeline import registry

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_CORPUS = "subset-sum-itqde"
_MINTED_PDF_RE = re.compile(r".+-\d{4}-\d{2}-\d{2}-r\d+\.pdf$")


def _ctx():
    ctx = registry.project_context(_CORPUS, _REPO)
    if ctx is None or ctx.manuscript_dir is None or not ctx.manuscript_dir.is_dir():
        pytest.skip(f"{_CORPUS} not on disk in this checkout")
    return ctx


def _rel(p: Path) -> str:
    return p.resolve().relative_to(_REPO.resolve()).as_posix()


def _disk_truth(ctx) -> dict[str, set[str]]:
    """The banked evidence on disk, by category — the parity target."""
    md, td = ctx.manuscript_dir, ctx.target_dir
    snaps = {_rel(d) for d in (md / "versions").glob("*") if d.is_dir()}
    harnessed = {_rel(f) for f in (td / "rounds" / "harnessed").glob("mech_r*.json")}
    judge = {_rel(f) for f in (md / "judge_rounds").glob("*round*.json")}
    minted = {_rel(f) for f in td.glob("*.pdf") if _MINTED_PDF_RE.match(f.name)}
    return {"snapshots": snaps, "harnessed": harnessed, "judge": judge, "minted": minted}


# ── GATE 1: revision-count parity ─────────────────────────────────────────────

def test_join_carries_every_disk_artifact():
    """Every versions/* dir, every harnessed mech round, every judge round file, and
    every minted release PDF on disk appears in SOME row's paths — the join is a
    complete cover of the banked truth, not a partial walk of one root."""
    ctx = _ctx()
    out = manuscript_versions.versions_payload(_CORPUS, _REPO)
    assert out is not None
    row_paths = {p for r in out["rows"] for p in r["paths"]}

    truth = _disk_truth(ctx)
    disk_all = set().union(*truth.values())
    assert disk_all, "no banked evidence enumerated — the gate would prove nothing"
    missing = sorted(d for d in disk_all if d not in row_paths)
    assert not missing, f"disk artifacts absent from the join: {missing}"


def test_harnessed_rounds_and_release_now_appear():
    """The two halves the manuscript-only walk MISSED are present: at least one round
    row carries a rounds/harnessed path, and the release history (minted PDFs) is
    joined — before the repair both were invisible for subset-sum-itqde."""
    ctx = _ctx()
    truth = _disk_truth(ctx)
    if not truth["harnessed"]:
        pytest.skip("no harnessed rounds banked for this corpus")
    out = manuscript_versions.versions_payload(_CORPUS, _REPO)
    rows = out["rows"]

    round_paths = {p for r in rows if r["kind"] == "round" for p in r["paths"]}
    assert truth["harnessed"] & round_paths, "harnessed rounds still missing from the join"

    release_rows = [r for r in rows if r["kind"] == "release"]
    assert release_rows, "the release history did not appear in the join"
    rel_paths = {p for r in release_rows for p in r["paths"]}
    assert truth["minted"] <= rel_paths, (
        f"minted release PDFs absent from release rows: {sorted(truth['minted'] - rel_paths)}")

    # both round layouts are named honestly in the sources block.
    layouts = set(out["sources"]["rounds"].get("layouts") or [])
    assert {"judge_rounds", "harnessed"} <= layouts, f"a round layout was dropped: {layouts}"


def test_join_rows_are_repo_relative_and_extant():
    """Every emitted path is repo-relative (never absolute) and resolves on disk — a
    rail row pointing at a path not on disk is a lie the join forbids."""
    _ctx()
    out = manuscript_versions.versions_payload(_CORPUS, _REPO)
    for r in out["rows"]:
        for p in r["paths"]:
            assert not p.startswith("/"), f"absolute path leaked: {p}"
            assert (_REPO / p).exists(), f"row path not on disk: {p}"


def test_snapshot_rows_carry_openable_artefacts_or_say_so():
    """A snapshot row carries its openable main.pdf/main.tex when one is banked (so W2
    can open the state, not just name its dir); a snapshot with none carries only its
    dir — an honest detail, never a fabricated openable path."""
    ctx = _ctx()
    out = manuscript_versions.versions_payload(_CORPUS, _REPO)
    snaps = [r for r in out["rows"] if r["kind"] == "snapshot"]
    assert snaps, "no snapshot rows on the real tree"
    opened = 0
    for r in snaps:
        for p in r["paths"]:
            if p.endswith((".pdf", ".tex")):
                assert (_REPO / p).is_file(), f"snapshot names a non-file artefact: {p}"
                opened += 1
    assert opened > 0, "no snapshot exposed an openable artefact — enrichment did nothing"


def test_join_obeys_the_golden_budget():
    """≤16KB per project, enforced not asserted — the join carries all 3 kinds and still
    fits (loud truncation only when it genuinely overflows)."""
    _ctx()
    out = manuscript_versions.versions_payload(_CORPUS, _REPO)
    import json
    size = len(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    assert size <= manuscript_versions._VERSIONS_MAX_BYTES, size


# ── GATE 2: current-artefact agreement (the J3 server half) ───────────────────

def test_corpus_ingest_and_registry_name_the_same_artefact():
    """``corpus_ingest.project_context`` and ``registry.project_context`` resolve the
    SAME pdf/tex — one server-canonical fact, never two roots disagreeing."""
    _ctx()
    ci_ctx = ci.project_context(_REPO, _CORPUS)
    reg_art = registry.project_context(_CORPUS, _REPO).current_artefact
    assert ci_ctx["main_tex"] == reg_art["tex"], (ci_ctx["main_tex"], reg_art["tex"])
    assert ci_ctx["pdf"] == reg_art["pdf"], (ci_ctx["pdf"], reg_art["pdf"])


def test_projection_bootstrap_names_the_whitepaper_not_the_stub():
    """The two-root repair, dead: /projection's bootstrap resolves the REAL current
    artefact (whitepaper/main.tex) and never the 35-line tex stub."""
    _ctx()
    ci_ctx = ci.project_context(_REPO, _CORPUS)
    assert ci_ctx["main_tex"] is not None
    assert "whitepaper" in ci_ctx["main_tex"], ci_ctx["main_tex"]
    assert "/tex/" not in ci_ctx["main_tex"], f"still resolving the tex stub: {ci_ctx['main_tex']}"
    assert (_REPO / ci_ctx["main_tex"]).is_file()
    # the resolved tex is the real paper, not the stub (the stub is ~35 lines).
    assert (_REPO / ci_ctx["main_tex"]).stat().st_size > 3000, "resolved a stub-sized tex"


def test_registry_artefact_kind_is_honest():
    """The current-artefact fact carries the {pdf, tex, version_id, kind} shape, and for
    a project mid-convergence (not released) the kind is a candidate/clean build."""
    _ctx()
    art = registry.project_context(_CORPUS, _REPO).current_artefact
    assert set(art) == {"pdf", "tex", "version_id", "kind"}
    assert art["kind"] in ("candidate", "clean", "release")
    assert art["pdf"] and art["pdf"].endswith(".pdf")
    assert art["tex"] and art["tex"].endswith(".tex")
