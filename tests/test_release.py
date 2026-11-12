"""The release organ: the bundle (round-trip + per-field drift), the state
machine (every illegal transition raises; a bundle-bound transition REOPENs on a
byte change), the figure freeze (a prose kind never regenerates an accepted
figure; a figure kind scopes to its sub-layer), and finalize (fails loud on the
untitled fixture, names the PDF by slug on the titled one).

Hand-built tiny manuscript fixtures; pdflatex/latexmk are installed.
"""
import importlib.util as _ilu
import json
import logging
import shutil
from pathlib import Path

import pytest

from laplace.pipeline import release as R
from laplace.pipeline import suppress

# the harnessed round-file emitter lives in the workflows dir (not an installed
# package); load it the way test_harnessed_flow.py does, so the A2 seam contract —
# a harnessed-emitted round file drives CANDIDATE_LOCKED exactly as a fixedpoint one —
# is pinned right beside the state machine it must satisfy.
_WORKFLOWS = Path(__file__).resolve().parents[1] / ".claude" / "workflows"
_hs_spec = _ilu.spec_from_file_location("harnessed_stage",
                                        str(_WORKFLOWS / "harnessed_stage.py"))
_hs = _ilu.module_from_spec(_hs_spec)
_hs_spec.loader.exec_module(_hs)


# ---------------------------------------------------------------------------
# fixtures — tiny real manuscripts
# ---------------------------------------------------------------------------

_MAIN_TITLED = r"""\documentclass[11pt]{article}
\usepackage{hyperref}
\hypersetup{pdftitle={The Test Manuscript}}
\title{The Test Manuscript}
\author{T. Ester}
\begin{document}
\maketitle
\input{S1}
\bibliographystyle{plain}
\bibliography{references}
\end{document}
"""

_S1 = r"""\section{Introduction}
A sentence that leans on prior work~\cite{key1}.
"""

_BIB = r"""@article{key1,
  author = {A. Nother},
  title = {A Prior Result},
  journal = {J. Tests},
  year = {2020},
}
"""

_MAIN_UNTITLED = r"""\documentclass[11pt]{article}
\begin{document}
No title macro here at all.
\end{document}
"""


def _make_manuscript(tmp_path, *, titled=True, with_pdf=True):
    """A tiny manuscript dir: main.tex (+ S1 input), references.bib, a figures/
    asset, a feedback/feedback.jsonl carrying one suppression, and (optionally) a
    stand-in main.pdf so the bundle has a final_pdf_hash without a compile.

    The ledger sits at ``<md>/feedback/feedback.jsonl`` — THE PRODUCTION LOCATION
    (WO-20260817-release-feedback-path). These two writes used to land one level up,
    at ``<md>/feedback.jsonl``, matching release.py's own wrong resolver: the test
    passed while every real manuscript hashed the empty set. A guarding test must
    exercise where the writers actually write."""
    md = tmp_path / ("titled" if titled else "untitled")
    md.mkdir()
    (md / "main.tex").write_text(_MAIN_TITLED if titled else _MAIN_UNTITLED,
                                 encoding="utf-8")
    if titled:
        (md / "S1.tex").write_text(_S1, encoding="utf-8")
        (md / "references.bib").write_text(_BIB, encoding="utf-8")
    figs = md / "figures"
    figs.mkdir()
    (figs / "F1.png").write_bytes(b"\x89PNG\r\n\x1a\n-fake-figure-one")
    (figs / "F2.pdf").write_bytes(b"%PDF-1.5-fake-figure-two")
    if with_pdf:
        (md / "main.pdf").write_bytes(b"%PDF-1.5 stand-in final pdf bytes")
    # one active suppression on S1
    rec = suppress.make_suppression("S1", "voice", _S1, reason="terminal phrasing",
                                    actor="tester", round=1, project="t")
    suppress.append_suppression(md / "feedback" / "feedback.jsonl", rec)
    return md


@pytest.fixture
def manuscript(tmp_path):
    return _make_manuscript(tmp_path, titled=True)


# ---------------------------------------------------------------------------
# the bundle — round-trip + drift per field
# ---------------------------------------------------------------------------

def test_bundle_round_trip_clean(manuscript):
    b = R.build_bundle(manuscript, dials=None, gate_results={"connectivity": "pass"},
                       judge_results={"R1": "clean"})
    # written to release/bundle_r1.json
    assert (manuscript / "release" / "bundle_r1.json").is_file()
    assert b["revision"] == 1
    assert b["final_pdf_hash"] is not None          # main.pdf stand-in bound
    assert b["gate_results"] == {"connectivity": "pass"}
    res = R.verify_bundle(manuscript, b)
    assert res == {"clean": True, "drifted": []}


def test_bundle_revision_increments(manuscript):
    R.build_bundle(manuscript)
    b2 = R.build_bundle(manuscript)
    assert b2["revision"] == 2
    assert (manuscript / "release" / "bundle_r2.json").is_file()


def test_drift_source_tree_hash_isolated_by_orphan(manuscript):
    """An orphan .tex (present in the tree but NOT reached by main.tex's \\input
    assembly) drifts source_tree_hash alone: the byte-level source guard sees a file
    the reading-order assembly never does."""
    b = R.build_bundle(manuscript)
    (manuscript / "notes.tex").write_text("Scratch notes, not \\input anywhere.\n",
                                          encoding="utf-8")
    res = R.verify_bundle(manuscript, b)
    assert res["drifted"] == ["source_tree_hash"]      # ONLY the tree hash


def test_drift_final_tex_hash_on_content(manuscript):
    b = R.build_bundle(manuscript)
    (manuscript / "S1.tex").write_text(_S1 + "New substantive sentence.\n",
                                       encoding="utf-8")
    res = R.verify_bundle(manuscript, b)
    assert "final_tex_hash" in res["drifted"]       # assembly changed
    assert "source_tree_hash" in res["drifted"]     # bytes changed too


def test_drift_bibliography_hash(manuscript):
    b = R.build_bundle(manuscript)
    (manuscript / "references.bib").write_text(_BIB + "\n% edited\n", encoding="utf-8")
    res = R.verify_bundle(manuscript, b)
    assert res["drifted"] == ["bibliography_hash"]


def test_drift_final_pdf_hash(manuscript):
    b = R.build_bundle(manuscript)
    (manuscript / "main.pdf").write_bytes(b"%PDF-1.5 DIFFERENT bytes now")
    res = R.verify_bundle(manuscript, b)
    assert "final_pdf_hash" in res["drifted"]


def test_drift_suppression_set_version(manuscript):
    b = R.build_bundle(manuscript)
    rec = suppress.make_suppression("S1", "naked-claim", _S1, reason="ok",
                                    actor="tester", round=2, project="t")
    suppress.append_suppression(manuscript / "feedback" / "feedback.jsonl", rec)
    res = R.verify_bundle(manuscript, b)
    assert res["drifted"] == ["suppression_set_version"]


def test_drift_figure_asset_modified(manuscript):
    b = R.build_bundle(manuscript)
    (manuscript / "figures" / "F1.png").write_bytes(b"\x89PNG changed pixels")
    res = R.verify_bundle(manuscript, b)
    assert res["drifted"] == ["figure_assets"]


def test_drift_figure_asset_added(manuscript):
    b = R.build_bundle(manuscript)
    (manuscript / "figures" / "F3.png").write_bytes(b"\x89PNG a new figure")
    res = R.verify_bundle(manuscript, b)
    assert res["drifted"] == ["figure_assets"]


def test_acceptance_change_is_not_source_drift(manuscript):
    """GERARD'S LAW protects source and PDF BYTES; a figure's acceptance metadata
    is provenance, not source — flipping it does not drift the bundle."""
    b = R.build_bundle(manuscript)
    R.set_figure_acceptance(manuscript, "figures/F1.png", "accepted")
    res = R.verify_bundle(manuscript, b)
    assert res == {"clean": True, "drifted": []}


def test_plan_hash_drift_when_plan_changes(tmp_path):
    md = _make_manuscript(tmp_path, titled=True)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"target": "t"}), encoding="utf-8")
    b = R.build_bundle(md, plan_path=plan)
    assert b["plan_hash"] is not None
    assert R.verify_bundle(md, b)["clean"] is True
    plan.write_text(json.dumps({"target": "t2"}), encoding="utf-8")
    assert "plan_hash" in R.verify_bundle(md, b)["drifted"]


def test_build_bundle_missing_plan_is_loud(manuscript):
    with pytest.raises(FileNotFoundError):
        R.build_bundle(manuscript, plan_path=manuscript / "no_such_plan.json")


# ---------------------------------------------------------------------------
# the state machine — forward-only, lock gate, bundle binding
# ---------------------------------------------------------------------------

def _eligible_evidence():
    return {"round_eval": {"hard_failing": []},
            "compile_report": {"ok": True, "errors": 0, "undefined_cites": 0,
                               "undefined_refs": 0},
            "round_complete": True}


def test_current_state_absent_is_staged(manuscript):
    assert R.current_state(manuscript) == "STAGED"


def test_forward_walk_to_candidate_lock(manuscript):
    R.transition(manuscript, "WELDED", evidence={})
    R.transition(manuscript, "UNDER_CONVERGENCE", evidence={})
    R.transition(manuscript, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    assert R.current_state(manuscript) == "CANDIDATE_LOCKED"


def test_backward_transition_raises(manuscript):
    R.transition(manuscript, "WELDED", evidence={})
    with pytest.raises(ValueError, match="forward-only"):
        R.transition(manuscript, "STAGED", evidence={})


def test_unknown_state_raises(manuscript):
    with pytest.raises(ValueError, match="unknown target state"):
        R.transition(manuscript, "SHIPPED", evidence={})


def test_transition_to_reopened_is_rejected(manuscript):
    with pytest.raises(ValueError, match="call reopen"):
        R.transition(manuscript, "REOPENED", evidence={})


def test_candidate_lock_requires_evidence_keys(manuscript):
    with pytest.raises(ValueError, match="requires evidence"):
        R.transition(manuscript, "CANDIDATE_LOCKED", evidence={"round_complete": True})


def test_candidate_lock_hard_fail_raises(manuscript):
    ev = _eligible_evidence()
    ev["round_eval"] = {"hard_failing": ["no_meta_leak"]}
    with pytest.raises(ValueError, match="not eligible"):
        R.transition(manuscript, "CANDIDATE_LOCKED", evidence=ev)


def test_candidate_lock_unclean_compile_raises(manuscript):
    ev = _eligible_evidence()
    ev["compile_report"] = {"ok": True, "errors": 3}
    with pytest.raises(ValueError, match="not eligible"):
        R.transition(manuscript, "CANDIDATE_LOCKED", evidence=ev)


def test_candidate_lock_incomplete_round_raises(manuscript):
    ev = _eligible_evidence()
    ev["round_complete"] = False
    with pytest.raises(ValueError, match="not eligible"):
        R.transition(manuscript, "CANDIDATE_LOCKED", evidence=ev)


def test_reopen_before_lock_raises(manuscript):
    R.transition(manuscript, "WELDED", evidence={})
    with pytest.raises(ValueError, match="nothing is locked"):
        R.reopen(manuscript, "premature")


def test_author_reviewed_requires_bundle_path(manuscript):
    R.transition(manuscript, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    with pytest.raises(ValueError, match="bundle_path"):
        R.transition(manuscript, "AUTHOR_REVIEWED", evidence={})


def test_released_requires_final_gates_passed(manuscript):
    R.transition(manuscript, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    b = R.build_bundle(manuscript)
    R.transition(manuscript, "AUTHOR_REVIEWED", evidence={"bundle_path": b["bundle_path"]})
    with pytest.raises(ValueError, match="FINAL_GATES_PASSED"):
        R.transition(manuscript, "RELEASED", evidence={"bundle_path": b["bundle_path"]})


def test_happy_path_to_released(manuscript):
    R.transition(manuscript, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    b = R.build_bundle(manuscript)
    ev = {"bundle_path": b["bundle_path"]}
    for st in ("AUTHOR_REVIEWED", "FINAL_CLEAN_BUILD", "FINAL_GATES_PASSED",
               "AUTHOR_ACCEPTED", "RELEASED"):
        R.transition(manuscript, st, evidence=ev)
    assert R.current_state(manuscript) == "RELEASED"


def test_automated_chain_path_skips_author_reviewed(manuscript):
    """The machine chain (project-pipeline.js) has no human review step: it drives
    CANDIDATE_LOCKED -> FINAL_CLEAN_BUILD -> FINAL_GATES_PASSED -> RELEASED, binding
    the finalized bundle at every FINAL_* state. AUTHOR_REVIEWED (G's human bar) is
    skipped by a forward jump."""
    R.transition(manuscript, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    b = R.build_bundle(manuscript)                 # bundle pins the finalized bytes
    ev = {"bundle_path": b["bundle_path"]}
    R.transition(manuscript, "FINAL_CLEAN_BUILD", evidence=ev)   # skips AUTHOR_REVIEWED
    R.transition(manuscript, "FINAL_GATES_PASSED", evidence=ev)
    R.transition(manuscript, "RELEASED", evidence=ev)
    assert R.current_state(manuscript) == "RELEASED"


def test_bundle_bound_transition_reopens_on_byte_change(manuscript):
    """AUTHOR_REVIEWED bound a bundle; a source byte then changes; the next
    bundle-bound transition RAISES and auto-REOPENs (GERARD'S LAW)."""
    R.transition(manuscript, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    b = R.build_bundle(manuscript)
    ev = {"bundle_path": b["bundle_path"]}
    R.transition(manuscript, "AUTHOR_REVIEWED", evidence=ev)
    # a byte changes under the review
    (manuscript / "S1.tex").write_text(_S1 + "Sneaky late edit.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="REOPENED"):
        R.transition(manuscript, "FINAL_CLEAN_BUILD", evidence=ev)
    assert R.current_state(manuscript) == "REOPENED"
    sidecar = json.loads((manuscript / "release" / "state.json").read_text())
    assert sidecar["reopened"]["prior_state"] == "AUTHOR_REVIEWED"


def test_reopened_resumes_at_under_convergence(manuscript):
    R.transition(manuscript, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    R.reopen(manuscript, "manual")
    assert R.current_state(manuscript) == "REOPENED"
    # re-converge is reachable; un-welding is not
    with pytest.raises(ValueError, match="forward-only"):
        R.transition(manuscript, "WELDED", evidence={})
    R.transition(manuscript, "UNDER_CONVERGENCE", evidence={})
    assert R.current_state(manuscript) == "UNDER_CONVERGENCE"


# ---------------------------------------------------------------------------
# the figure freeze
# ---------------------------------------------------------------------------

def test_figure_assets_join_acceptance(manuscript):
    R.set_figure_acceptance(manuscript, "figures/F1.png", "accepted")
    assets = {a["path"]: a for a in R.figure_assets(manuscript)}
    assert assets["figures/F1.png"]["acceptance"] == "accepted"
    assert assets["figures/F2.pdf"]["acceptance"] == "draft"
    assert all(a["sha256"] for a in assets.values())


def test_set_figure_acceptance_rejects_unknown_state(manuscript):
    with pytest.raises(ValueError, match="unknown figure state"):
        R.set_figure_acceptance(manuscript, "figures/F1.png", "blessed")


def test_draft_figure_regen_unrestricted(manuscript):
    ok, reason = R.figure_regen_allowed(manuscript, "figures/F1.png", "voice")
    assert ok is True
    assert "draft" in reason


def test_frozen_figure_blocks_prose_kind(manuscript):
    R.set_figure_acceptance(manuscript, "figures/F1.png", "accepted")
    ok, reason = R.figure_regen_allowed(manuscript, "figures/F1.png", "voice")
    assert ok is False
    assert "not a figure-layer kind" in reason


def test_frozen_figure_scopes_figure_kind(manuscript):
    R.set_figure_acceptance(manuscript, "figures/F1.png", "frozen")
    ok, reason = R.figure_regen_allowed(manuscript, "figures/F1.png", "caption-missing")
    assert ok is True
    assert "caption" in reason                    # scoped to the caption sub-layer


def test_frozen_figure_scopes_composition(manuscript):
    R.set_figure_acceptance(manuscript, "figures/F1.png", "accepted")
    ok, reason = R.figure_regen_allowed(manuscript, "figures/F1.png",
                                        "figure-not-singular")
    assert ok is True
    assert "composition" in reason


def test_non_figure_kind_mentioning_figure_still_blocked(manuscript):
    """figure-misplaced routes to the STRUCTURE layer, not figures — it must not
    regenerate a frozen figure."""
    R.set_figure_acceptance(manuscript, "figures/F1.png", "accepted")
    ok, _ = R.figure_regen_allowed(manuscript, "figures/F1.png", "figure-misplaced")
    assert ok is False


# ---------------------------------------------------------------------------
# finalize — the naming contract
# ---------------------------------------------------------------------------

def test_finalize_fails_loud_on_untitled(tmp_path):
    md = _make_manuscript(tmp_path, titled=False, with_pdf=False)
    with pytest.raises(ValueError, match="front-matter"):
        R.finalize(md)


def test_resolve_title_prefers_plan_spec(tmp_path):
    md = _make_manuscript(tmp_path, titled=False, with_pdf=False)
    (md / "projection_plan.json").write_text(
        json.dumps({"title": "Planned Working Title"}), encoding="utf-8")
    # no \title in the doc, but the plan supplies one -> resolves, no raise
    assert R._resolve_title(md, None, None) == "Planned Working Title"


def test_finalize_title_check_reports_disagreement(tmp_path):
    """A title/pdftitle mismatch is REPORTED, never edited (read-only source)."""
    md = _make_manuscript(tmp_path, titled=True, with_pdf=False)
    src = (md / "main.tex").read_text()
    (md / "main.tex").write_text(src.replace("pdftitle={The Test Manuscript}",
                                             "pdftitle={A Different pdftitle}"))
    if not shutil.which("latexmk"):
        pytest.skip("latexmk not installed")
    res = R.finalize(md)
    assert res["title_check"]["title_agrees"] is True
    assert res["title_check"]["pdftitle_agrees"] is False
    # source untouched
    assert "A Different pdftitle" in (md / "main.tex").read_text()


# ---------------------------------------------------------------------------
# Leg C bite C1 — REVTeX title extraction + the metadata stamp
# ---------------------------------------------------------------------------

_REVTEX_MAIN = (
    "\\documentclass[aps,prx,twocolumn]{revtex4-2}\n"
    "\\usepackage{hyperref}\n"
    "\\hypersetup{pdftitle={A Sensing Grade Result},"
    "pdfsubject={REVISION-NEUTRAL},pdfkeywords={REVISION-NEUTRAL}}\n"
    "\\begin{document}\n"
    "\\title{A Sensing Grade Result}\n"          # REVTeX: title AFTER begin{document}
    "\\author{T. Ester}\n"
    "\\maketitle\n"
    "Body prose that leans on prior work.\n"
    "\\end{document}\n"
)


def test_extract_doc_title_finds_revtex_title_after_begin_document():
    """The bite-zero A false-negative: a REVTeX \\title sits after
    \\begin{document}; reading only the preamble missed it."""
    title, macro = R._extract_doc_title(_REVTEX_MAIN)
    assert title == "A Sensing Grade Result" and macro == "title"


def test_metadata_pretex_stamps_slug_and_revision():
    pre = R._metadata_pretex("a-sensing-grade-result", 4)
    assert "pdfsubject" in pre and "pdfkeywords" in pre
    assert "a-sensing-grade-result" in pre and "revision 4" in pre and "r4" in pre
    assert pre.startswith(r"\AtBeginDocument")   # applies AFTER hyperref loads


def test_finalize_stamps_pdf_metadata_and_reads_revtex_title(tmp_path, monkeypatch):
    """finalize resolves the REVTeX title (title_agrees), and the latexmk command
    carries the pdfsubject/pdfkeywords stamp with slug + revision — proved without
    a real compile by capturing the argv."""
    md = tmp_path / "rev"
    md.mkdir()
    (md / "main.tex").write_text(_REVTEX_MAIN, encoding="utf-8")

    captured: dict = {}

    def _fake_run(cmd, **kw):
        captured["cmd"] = cmd
        slug = next(a.split("=", 1)[1] for a in cmd if a.startswith("-jobname="))
        (md / f"{slug}.pdf").write_bytes(b"%PDF-1.5 fake final")
        (md / f"{slug}.log").write_text(
            f"This is pdfTeX\nOutput written on {slug}.pdf (1 page).\n", encoding="utf-8")

        class _P:
            returncode = 0
        return _P()

    monkeypatch.setattr(R.subprocess, "run", _fake_run)
    res = R.finalize(md)

    # (1) the REVTeX title (after \begin{document}) is found and agrees
    assert res["title_check"]["title_present"] is True
    assert res["title_check"]["title_agrees"] is True

    # (2) the metadata stamp rides the latexmk command with slug + revision, and
    # APPENDS to the manuscript's base hypersetup values rather than replacing them
    # (the reviewer polish: a filename slug must not clobber the author's subject).
    pre = next(a for a in captured["cmd"] if a.startswith("-usepretex="))
    assert "pdfsubject" in pre and "pdfkeywords" in pre
    assert res["slug"] in pre and f"r{res['revision']}" in pre
    assert "REVISION-NEUTRAL" in res["pdf_subject"]        # base preserved, not replaced
    assert "REVISION-NEUTRAL" in res["pdf_keywords"]
    assert res["pdf_subject"].endswith(f"{res['slug']} revision {res['revision']}")
    assert res["pdf_keywords"].endswith(f"{res['slug']}, r{res['revision']}")
    # (3) source is untouched (read-only): the revision-neutral strings still stand
    assert "REVISION-NEUTRAL" in (md / "main.tex").read_text()


@pytest.mark.skipif(not shutil.which("latexmk"), reason="latexmk not installed")
def test_finalize_names_pdf_by_slug_and_resolves_cites(tmp_path):
    md = _make_manuscript(tmp_path, titled=True, with_pdf=False)
    res = R.finalize(md)
    assert res["slug"] == "the-test-manuscript"
    assert res["pdf_path"] == "the-test-manuscript.pdf"
    assert (md / "the-test-manuscript.pdf").is_file()      # NAMED, not main.pdf
    assert res["compile_report"]["ok"] is True
    assert res["compile_report"]["undefined_cites"] == 0   # bibtex resolved \cite
    assert res["title_check"]["title_agrees"] is True
    assert res["title_check"]["pdftitle_agrees"] is True
    # finalize handed the PDF to build_bundle via the sidecar
    assert (md / "release" / "finalize.json").is_file()
    b = R.build_bundle(md)
    assert b["final_pdf_path"] == "the-test-manuscript.pdf"
    assert R.verify_bundle(md, b)["clean"] is True


def test_ensure_at_least_is_reentry_aware(tmp_path):
    # H bite 3: a resumed tex-mode entry re-asserts WELDED on a sidecar already
    # at UNDER_CONVERGENCE - ensure_at_least no-ops instead of raising, advances
    # when genuinely behind, and never moves backward.
    from laplace.pipeline import release as R
    d = tmp_path / "ms"
    d.mkdir()
    r1 = R.ensure_at_least(d, "WELDED", evidence={"note": "entry"})
    assert r1 == {"state": "WELDED", "advanced": True}
    r2 = R.ensure_at_least(d, "UNDER_CONVERGENCE", evidence={"note": "converge"})
    assert r2["advanced"] is True
    # re-entry: already past WELDED -> no-op, no exception, state preserved
    r3 = R.ensure_at_least(d, "WELDED", evidence={"note": "re-entry"})
    assert r3 == {"state": "UNDER_CONVERGENCE", "advanced": False}
    assert R.current_state(d) == "UNDER_CONVERGENCE"


# ---------------------------------------------------------------------------
# W3.2 — bank_snapshot: the ONE writer into versions_dir (Fork 7 / Q6)
# ---------------------------------------------------------------------------

_SNAP_MAIN = r"""\documentclass{article}
\title{A Banked Manuscript}
\begin{document}
\maketitle
\input{S1}
\end{document}
"""
_SNAP_S1 = "\\section{Intro}\nBody text~\\cite{k1}.\n"
_SNAP_BIB = "@article{k1, author={A}, title={T}, journal={J}, year={2020}}\n"


def _make_registered_manuscript(repo_root, *, project="eigenengine", with_pdf=False):
    """Lay a tiny manuscript at a REGISTERED project's on-disk path under a tmp
    repo_root, so ``registry.resolve(project).path(..., repo_root)`` resolves into
    it. Returns the manuscript dir."""
    from laplace.pipeline import registry
    proj = registry.resolve(project)
    md = proj.path(proj.manuscript_dir, Path(repo_root))
    md.mkdir(parents=True, exist_ok=True)
    (md / "main.tex").write_text(_SNAP_MAIN, encoding="utf-8")
    (md / "S1.tex").write_text(_SNAP_S1, encoding="utf-8")
    (md / "refs.bib").write_text(_SNAP_BIB, encoding="utf-8")
    if with_pdf:
        (md / "main.pdf").write_bytes(b"%PDF-1.5 stand-in")
    return md


def test_bank_snapshot_writes_one_snapshot_and_one_provenance_row(tmp_path):
    md = _make_registered_manuscript(tmp_path)
    rec = R.bank_snapshot("eigenengine", "author reviewed r3", by="author",
                          repo_root=tmp_path)
    vdir = md / "versions"
    snap_dirs = [d for d in vdir.iterdir() if d.is_dir()]
    assert len(snap_dirs) == 1                      # exactly one snapshot
    snap = snap_dirs[0]
    assert (snap / "SNAPSHOT.json").is_file()
    assert snap.name == rec["id"]
    # exactly one provenance row, the state-machine history idiom
    ledger = json.loads((md / "release" / "snapshots.json").read_text(encoding="utf-8"))
    assert len(ledger["snapshots"]) == 1
    assert ledger["snapshots"][0]["id"] == rec["id"]
    # a second bank appends one more of each — the door is monotone, not a rewrite
    R.bank_snapshot("eigenengine", "a later state", by="author", repo_root=tmp_path)
    assert len([d for d in vdir.iterdir() if d.is_dir()]) == 2
    ledger2 = json.loads((md / "release" / "snapshots.json").read_text(encoding="utf-8"))
    assert len(ledger2["snapshots"]) == 2


def test_bank_snapshot_manifest_schema(tmp_path):
    _make_registered_manuscript(tmp_path)
    rec = R.bank_snapshot("eigenengine", "schema check", by="author",
                          repo_root=tmp_path)
    snap = next(d for d in (Path(rec["path"]),) if d.is_dir())
    man = json.loads((snap / "SNAPSHOT.json").read_text(encoding="utf-8"))
    for field in R._SNAPSHOT_MANIFEST_FIELDS:
        assert field in man, f"manifest missing schema field {field!r}"
    assert man["by"] == "author"
    assert man["project"] == "eigenengine"
    assert man["label"] == "schema check"
    # the source it froze: the tex fragments + the bib, manuscript-relative
    assert set(man["files"]) == {"main.tex", "S1.tex", "refs.bib"}
    assert man["source_tree_hash"]


def test_bank_snapshot_refuses_unregistered_project(tmp_path):
    with pytest.raises(ValueError, match="unregistered project"):
        R.bank_snapshot("not-a-real-project", "x", by="author", repo_root=tmp_path)
    # a path-shaped name is fenced too (registry.resolve -> None)
    with pytest.raises(ValueError, match="unregistered project"):
        R.bank_snapshot("../escape", "x", by="author", repo_root=tmp_path)


def test_bank_snapshot_requires_actor(tmp_path):
    _make_registered_manuscript(tmp_path)
    # blank actor RAISES before any write (the actor law)
    with pytest.raises(ValueError, match="actor"):
        R.bank_snapshot("eigenengine", "x", by="   ", repo_root=tmp_path)
    # and `by` is keyword-only with no default: omitting it is a TypeError
    with pytest.raises(TypeError):
        R.bank_snapshot("eigenengine", "x", repo_root=tmp_path)  # type: ignore[call-arg]


def test_bank_snapshot_is_atomic_no_partial_on_crash(tmp_path, monkeypatch):
    md = _make_registered_manuscript(tmp_path)
    vdir = md / "versions"

    def _boom(*a, **k):
        raise OSError("disk full mid-copy")

    monkeypatch.setattr("shutil.copy2", _boom)
    with pytest.raises(OSError):
        R.bank_snapshot("eigenengine", "will crash", by="author", repo_root=tmp_path)
    # NO partial snapshot dir under versions/ (tmp+rename: <id>/ only appears whole)
    assert not vdir.exists() or not [d for d in vdir.iterdir() if d.is_dir()]
    # NO tmp residue leaked into the rail's store (tmp lives release-side + cleaned)
    if vdir.exists():
        assert not list(vdir.glob(".tmp-*"))
    # NO provenance row for the failed write
    prov = md / "release" / "snapshots.json"
    if prov.is_file():
        assert json.loads(prov.read_text(encoding="utf-8"))["snapshots"] == []


def test_bank_snapshot_store_not_counted_as_source_drift(tmp_path):
    # versions/ is release-INTERNAL: banking a snapshot (which copies .tex/.bib
    # bytes under versions/) must NOT change source_tree_hash or reopen a bundle.
    md = _make_registered_manuscript(tmp_path, with_pdf=True)
    before = R.source_tree_hash(md)
    b = R.build_bundle(md)
    R.bank_snapshot("eigenengine", "snap after bundle", by="author", repo_root=tmp_path)
    assert R.source_tree_hash(md) == before          # the snapshot is not source
    assert R.verify_bundle(md, b)["clean"] is True    # bundle stays clean


def _assert_one_snapshot(md, *, by, expect_id=None):
    """One snapshot dir + one provenance row, SNAPSHOT.json schema-valid, banked
    in ``by``'s name — the shared assertion for the two ruled firing points."""
    vdir = md / "versions"
    snaps = [d for d in vdir.iterdir() if d.is_dir()]
    assert len(snaps) == 1, f"expected exactly one banked snapshot, got {snaps}"
    man = json.loads((snaps[0] / "SNAPSHOT.json").read_text(encoding="utf-8"))
    for field in R._SNAPSHOT_MANIFEST_FIELDS:
        assert field in man, f"SNAPSHOT.json missing schema field {field!r}"
    assert man["by"] == by
    ledger = json.loads((md / "release" / "snapshots.json").read_text(encoding="utf-8"))
    assert len(ledger["snapshots"]) == 1
    assert ledger["snapshots"][0]["id"] == man["id"]
    if expect_id is not None:
        assert man["id"] == expect_id
    return man


def test_transition_author_reviewed_banks_one_snapshot(tmp_path):
    """Fork-7 ruled firing point #1: the transition to AUTHOR_REVIEWED banks exactly
    one snapshot + one provenance row (SNAPSHOT.json schema-valid), attributed to the
    threaded actor and recorded on the history row."""
    md = _make_registered_manuscript(tmp_path, with_pdf=True)
    R.transition(md, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    b = R.build_bundle(md)
    side = R.transition(md, "AUTHOR_REVIEWED",
                        evidence={"bundle_path": b["bundle_path"]}, by="author")
    assert side["state"] == "AUTHOR_REVIEWED"
    entry = side["history"][-1]
    assert entry["to"] == "AUTHOR_REVIEWED"
    assert "snapshot_error" not in entry
    man = _assert_one_snapshot(md, by="author", expect_id=entry["snapshot"])
    assert man["label"] == "AUTHOR_REVIEWED"


@pytest.mark.skipif(not shutil.which("latexmk"), reason="latexmk not installed")
def test_finalize_banks_one_release_snapshot(tmp_path):
    """Fork-7 ruled firing point #2: finalize banks exactly one release snapshot +
    one provenance row (SNAPSHOT.json schema-valid), attributed to the threaded
    actor and recorded on the finalize result + sidecar."""
    md = _make_registered_manuscript(tmp_path)
    res = R.finalize(md, by="author")
    assert res.get("snapshot") and not res.get("snapshot_error")
    man = _assert_one_snapshot(md, by="author", expect_id=res["snapshot"])
    assert man["label"].startswith("release ")
    # the finalize.json sidecar records the banked id too (the compose-seam trail)
    fin = json.loads((md / "release" / "finalize.json").read_text(encoding="utf-8"))
    assert fin["snapshot"] == res["snapshot"] and fin["snapshot_error"] is None


def test_author_reviewed_snapshot_failure_is_loud_but_not_corrupting(
        tmp_path, monkeypatch, caplog):
    """The ruled failure posture: a bank_snapshot failure at AUTHOR_REVIEWED is LOUD
    (ERROR log + snapshot_error on the history row) but does NOT corrupt the
    transition — the advance still commits and persists, and the fail-closed door
    leaves no snapshot in the rail's store."""
    md = _make_registered_manuscript(tmp_path, with_pdf=True)
    R.transition(md, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    b = R.build_bundle(md)

    def _boom(*a, **k):
        raise OSError("versions store unwritable mid-bank")

    monkeypatch.setattr(R, "bank_snapshot", _boom)
    with caplog.at_level(logging.ERROR):
        side = R.transition(md, "AUTHOR_REVIEWED",
                            evidence={"bundle_path": b["bundle_path"]}, by="author")
    # the advance STANDS — committed in memory and durably persisted
    assert side["state"] == "AUTHOR_REVIEWED"
    assert R.current_state(md) == "AUTHOR_REVIEWED"
    persisted = json.loads((md / "release" / "state.json").read_text(encoding="utf-8"))
    assert persisted["state"] == "AUTHOR_REVIEWED"
    # LOUD — ERROR logged and recorded on the history row, no success id
    assert any("bank_snapshot FAILED" in r.getMessage() for r in caplog.records)
    entry = side["history"][-1]
    assert "snapshot_error" in entry and "snapshot" not in entry
    # NOT corrupting — no snapshot appears in the rail's store
    vdir = md / "versions"
    assert not vdir.exists() or not [d for d in vdir.iterdir() if d.is_dir()]


def test_author_reviewed_missing_actor_refused_at_door_not_corrupting(tmp_path, caplog):
    """No default actor is invented: when the caller supplies no ``by``, the door's
    own actor-law refusal stands — surfaced through the SAME loud-but-not-corrupting
    path (snapshot_error on the row), the transition still advancing."""
    md = _make_registered_manuscript(tmp_path, with_pdf=True)
    R.transition(md, "CANDIDATE_LOCKED", evidence=_eligible_evidence())
    b = R.build_bundle(md)
    with caplog.at_level(logging.ERROR):
        side = R.transition(md, "AUTHOR_REVIEWED",
                            evidence={"bundle_path": b["bundle_path"]})  # no by=
    assert side["state"] == "AUTHOR_REVIEWED"
    entry = side["history"][-1]
    assert "snapshot" not in entry
    assert "actor" in entry.get("snapshot_error", "")
    vdir = md / "versions"
    assert not vdir.exists() or not [d for d in vdir.iterdir() if d.is_dir()]


# ---------------------------------------------------------------------------
# A2 — the harnessed organ is composable: its emitted round file drives
# CANDIDATE_LOCKED exactly as a fixedpoint round file does
# ---------------------------------------------------------------------------

def _harnessed_source_round(*, eligible=True):
    """A mechround-shaped round record — the shape ``fixedpoint_mechround.py`` writes
    and the harnessed redetect produces (it drives that same mechround). ``hard_failing``
    is the empty list when eligible / a non-empty list when not (candidate_lock reads it
    via ``not round_eval['hard_failing']``; a real mechround emits a bool, both handled)."""
    return {
        "round": 7, "date": "2026-07-15", "workflow": "project-fixedpoint",
        "target": "m/main.tex",
        "panel": [{"label": "meta_leak", "clean": True, "flags": []},
                  {"label": "apparatus", "clean": bool(eligible), "flags": []}],
        # compile_report shaped for candidate_lock.lock_eligible (no 'ok' key, as the
        # mechround emits: 0 errors / 0 undefined => clean)
        "compile_report": {"undefined": 0, "errors": 0, "overfull": 0,
                           "log_is_real": True},
        "contract": {"hard": {"no_meta_leak": True, "technical_support": bool(eligible)},
                     "soft": {"style_conformance": 1.0}},
        "hard_failing": [] if eligible else ["technical_support"],
        "complete": True,
        "lock_eligible": bool(eligible),
        "flags_routed": 0, "flags_unrouted": [],
    }


def _pipeline_lock_evidence(doc):
    """The CANDIDATE_LOCKED evidence, built from a converge-leg round file EXACTLY as
    project-pipeline.js's lockCmd builds it — the seam under test."""
    return {"round_eval": {"hard_failing": doc.get("hard_failing")},
            "compile_report": doc.get("compile_report") or {},
            "round_complete": bool(doc.get("complete"))}


def test_harnessed_round_file_satisfies_candidate_lock(tmp_path, manuscript):
    """An eligible harnessed-shaped round file, written by the emitter into judge_rounds,
    drives the CANDIDATE_LOCKED transition through — the A2 seam (composable organ)."""
    src = tmp_path / "mech_r8.json"
    src.write_text(json.dumps(_harnessed_source_round(eligible=True)), encoding="utf-8")
    jr = tmp_path / "judge_rounds"
    rf = _hs.emit_round_file(str(jr), 1, str(src),
                             target=str(manuscript / "main.tex"), project="t")
    assert Path(rf).name == "harnessed_round1.json"       # the name pipeline globs
    doc = json.loads(Path(rf).read_text(encoding="utf-8"))
    R.transition(manuscript, "WELDED", evidence={})
    R.transition(manuscript, "UNDER_CONVERGENCE", evidence={})
    side = R.transition(manuscript, "CANDIDATE_LOCKED",
                        evidence=_pipeline_lock_evidence(doc))
    assert side["state"] == "CANDIDATE_LOCKED"


def test_harnessed_round_file_ineligible_is_refused(tmp_path, manuscript):
    """An ineligible harnessed round file (hard_failing non-empty) is REFUSED at the
    CANDIDATE_LOCKED gate — the honest non-convergence signal, same as fixedpoint's."""
    src = tmp_path / "mech_r8.json"
    src.write_text(json.dumps(_harnessed_source_round(eligible=False)), encoding="utf-8")
    jr = tmp_path / "judge_rounds"
    rf = _hs.emit_round_file(str(jr), 2, str(src))
    doc = json.loads(Path(rf).read_text(encoding="utf-8"))
    R.transition(manuscript, "WELDED", evidence={})
    R.transition(manuscript, "UNDER_CONVERGENCE", evidence={})
    with pytest.raises(ValueError, match="not eligible"):
        R.transition(manuscript, "CANDIDATE_LOCKED",
                     evidence=_pipeline_lock_evidence(doc))


def test_harnessed_emitter_carries_the_lock_and_bundle_fields_verbatim(tmp_path):
    """The emitter copies the union of fields project-pipeline reads at BOTH seams —
    the CANDIDATE_LOCKED evidence (hard_failing/compile_report/complete) and the bundle
    (round/hard_failing/lock_eligible/contract/panel) — verbatim from the source round
    file, so a harnessed round file is byte-for-byte substitutable for a fixedpoint one."""
    src_doc = _harnessed_source_round(eligible=True)
    src = tmp_path / "mech.json"
    src.write_text(json.dumps(src_doc), encoding="utf-8")
    rf = _hs.emit_round_file(str(tmp_path / "jr"), 3, str(src))
    doc = json.loads(Path(rf).read_text(encoding="utf-8"))
    # the CANDIDATE_LOCKED evidence is identical whichever organ produced the round file
    assert _pipeline_lock_evidence(doc) == _pipeline_lock_evidence(src_doc)
    # the bundle-read fields carry through untouched
    assert doc["contract"] == src_doc["contract"]
    assert doc["panel"] == src_doc["panel"]
    assert doc["lock_eligible"] == src_doc["lock_eligible"]
    assert doc["round"] == 3                               # re-keyed to the pass ordinal
    assert doc["workflow"] == "project-harnessed"          # provenance re-stamped


def test_versions_store_has_exactly_one_writer():
    """The grep-level ONE-DOOR guard (W0.1 idiom): no module other than
    release.bank_snapshot WRITES into a project's versions/ snapshot store, and no
    module other than release + candidate_lock (the rounds store) WRITES a
    SNAPSHOT.json. A future ad-hoc writer that would fork the store the version
    rail reads is caught HERE, before it can."""
    repo = Path(__file__).resolve().parents[1]
    src = repo / "src" / "laplace"
    scripts = repo / "scripts"
    write_prims = (".mkdir(", ".write_text(", ".write_bytes(", "shutil.copy",
                   "shutil.copytree(", "os.replace(", "os.rename(", "open(")
    release_py = (src / "pipeline" / "release.py").resolve()
    candidate_lock_py = (src / "pipeline" / "candidate_lock.py").resolve()
    versions_offenders = []
    snapshot_offenders = []
    for py in sorted(src.rglob("*.py")) + sorted(scripts.glob("*.py")):
        rp = py.resolve()
        text = py.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            has_write = any(w in line for w in write_prims)
            if not has_write:
                continue
            names_versions = ('"versions"' in line or "'versions'" in line
                              or "versions_dir" in line)
            if names_versions and rp != release_py:
                versions_offenders.append((py.name, i, line.strip()))
            if "SNAPSHOT.json" in line and rp not in (release_py, candidate_lock_py):
                snapshot_offenders.append((py.name, i, line.strip()))
    assert not versions_offenders, (
        "ad-hoc writer into the versions store (only release.bank_snapshot may "
        f"write it): {versions_offenders}")
    assert not snapshot_offenders, (
        "ad-hoc SNAPSHOT.json writer (only release + candidate_lock may write one): "
        f"{snapshot_offenders}")


# ---------------------------------------------------------------------------
# the promise-materialisation leg — figures organ + bibliography stage COMPOSED
# (the July-17 fix-round catch: both organs shipped but NO orchestrator invoked
# them, so a pipeline rerun did not mint the figures or the References — an
# operator had to run the two CLIs by hand). These lock the call-site: discovery
# by convention, composition, the ok verdict, and reproducibility.
# ---------------------------------------------------------------------------

_GEN_SCRIPT_REAL = '''\
"""Two data figures for the fixture manuscript.

fig_witness   - the protocol's verification: flag behaviour vs the commutator
                prediction and the quiet-branch error scaling.
fig_resources - the resource estimate and its sweep tradeoff levers.
"""


def save(fig, name):
    pass


def fig_witness():
    save(object(), "fig_witness")


def fig_resources():
    save(object(), "fig_resources")
'''


def _materialize_project(tmp_path, *, with_figures=True):
    """A tiny project tree mirroring the real layout: ``<root>/manuscript`` beside
    ``<root>/numerics/<name>_figures.py``. main.tex \\inputs the sections the
    figures organ places into (s6/s8) and the promise-site appendix; refs.bib
    defines every cited key so the bibliography resolves clean."""
    root = tmp_path / "proj"
    md = root / "manuscript"
    md.mkdir(parents=True)
    (md / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\input{s6}\n\\input{s8}\n\\input{appendix_c}\n"
        "\\end{document}\n", encoding="utf-8")
    (md / "s6.tex").write_text("% s6\n% NODES: n6\nResources here.\n", encoding="utf-8")
    (md / "s8.tex").write_text("% s8\n% NODES: n8\nWitness here~\\cite{k1}.\n", encoding="utf-8")
    (md / "appendix_c.tex").write_text(
        "% appendix\nThe sweep-tradeoff plot and the witness-scaling plot are "
        "registered TODOs, with neither rendered in this version.\n",
        encoding="utf-8")
    (md / "refs.bib").write_text(
        "@article{k1, author={A. N. Other}, title={T}, journal={J}, year={2020}}\n",
        encoding="utf-8")
    if with_figures:
        num = root / "numerics"
        num.mkdir()
        (num / "falqon_figures.py").write_text(_GEN_SCRIPT_REAL, encoding="utf-8")
        # pretend the generator already produced the artefacts (run_generators=False
        # in the test avoids the matplotlib subprocess); the sibling figures/ dir is
        # where run_generators would drop them and where placement copies from.
        figs = root / "figures"
        figs.mkdir()
        (figs / "fig_witness.pdf").write_bytes(b"%PDF-1.5 witness")
        (figs / "fig_resources.pdf").write_bytes(b"%PDF-1.5 resources")
    return md


def test_discover_generator_script_by_convention(tmp_path):
    md = _materialize_project(tmp_path)
    got = R._discover_generator_script(md)
    assert got is not None and got.name == "falqon_figures.py"


def test_discover_generator_script_absent(tmp_path):
    md = _materialize_project(tmp_path, with_figures=False)
    assert R._discover_generator_script(md) is None


def test_materialize_composes_both_organs(tmp_path):
    md = _materialize_project(tmp_path)
    # run_generators/probe off: hermetic (no matplotlib subprocess, no latexmk),
    # but placement + wiring + reconciliation + resolution all fire.
    res = R.materialize_promised_assets(md, run_generators=False, probe=False)
    assert res["ok"] is True
    # figures: both promises matched, floats placed, promise site reconciled
    assert res["figures"]["matched_count"] == 2
    assert res["figures"]["unmatched_count"] == 0
    assert "appendix_c.tex" in res["reconciled_sites"]
    assert "\\label{fig:resources}" in (md / "s6.tex").read_text(encoding="utf-8")
    assert "\\label{fig:witness}" in (md / "s8.tex").read_text(encoding="utf-8")
    ap = (md / "appendix_c.tex").read_text(encoding="utf-8")
    assert "registered TODO" not in ap and "neither rendered" not in ap
    # bibliography: the one cited key resolves, nothing dangles, wired
    assert res["bibliography"]["dangling"] == []
    assert res["bibliography"]["wired"] is True


def test_materialize_bibliography_only_when_no_generator(tmp_path):
    md = _materialize_project(tmp_path, with_figures=False)
    res = R.materialize_promised_assets(md, run_generators=False, probe=False)
    # a figureless project still materialises its bibliography; figures is a
    # reported no-op, not a raise
    assert res["figures"].get("skipped")
    assert res["bibliography"]["wired"] is True
    assert res["ok"] is True


def test_materialize_is_reproducible_and_byte_stable(tmp_path):
    md = _materialize_project(tmp_path)

    def texhash(d):
        import hashlib
        h = hashlib.sha256()
        for p in sorted(d.glob("*.tex")):
            h.update(p.read_bytes())
        return h.hexdigest()

    R.materialize_promised_assets(md, run_generators=False, probe=False)
    once = texhash(md)
    R.materialize_promised_assets(md, run_generators=False, probe=False)
    assert texhash(md) == once           # idempotent re-run

    # a fresh project from the same inputs mints the SAME tex tree
    md2 = _materialize_project(tmp_path / "second")
    R.materialize_promised_assets(md2, run_generators=False, probe=False)
    assert texhash(md2) == once


# ---------------------------------------------------------------------------
# the FINISHED-ARTEFACT resolver (WO-20260820-r10-binds-the-wrong-pdf)
#
# The live defect these pin: SSG's plan declares
# meta.target_dir = '.../manuscript/whitepaper', the whitepaper's PDFs live there,
# and the manuscript dir itself holds exactly ONE top-level PDF — FIGURE_REVIEW.pdf,
# a figure-review audit. _discover_final_pdf's sole-top-level fall-through therefore
# certified the AUDIT as the finished paper, and the whole-artefact reader has never
# once read the whitepaper.
# ---------------------------------------------------------------------------

def _plan(**meta):
    return {"meta": meta, "sections": []}


def _pdf(p: Path, body=b"%PDF-1.5 x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)
    return p


def _ssg_shaped(tmp_path: Path) -> Path:
    """The live SSG layout in miniature: a manuscript whose ONLY top-level PDF is a
    figure-review audit, with the real artefact one directory down under the plan's
    declared target_dir."""
    md = tmp_path / "proj" / "manuscript"
    _pdf(md / "FIGURE_REVIEW.pdf")
    wp = md / "whitepaper"
    _pdf(wp / "main.pdf")
    _pdf(wp / "the-paper-2026-07-14-r1.pdf")
    (wp / "release").mkdir(parents=True, exist_ok=True)
    (wp / "release" / "finalize.json").write_text(
        json.dumps({"pdf_path": "the-paper-2026-07-14-r1.pdf"}), encoding="utf-8")
    _pdf(wp / "release" / "the-paper-2026-07-11-r6-voiced.pdf")
    return md


def test_head_behaviour_the_defect_itself(tmp_path):
    """HEAD's shared resolver still binds the audit sheet — pinned so the fix is
    visibly a NEW resolver and not a silent change under the release machine."""
    md = _ssg_shaped(tmp_path)
    assert R._discover_final_pdf(md) == "FIGURE_REVIEW.pdf"


def test_artefact_binds_inside_the_declared_target_dir(tmp_path):
    md = _ssg_shaped(tmp_path)
    plan = _plan(target_dir="whitepaper")
    b = R.artefact_pdf_binding(md, plan=plan)
    assert b["pdf"] == "whitepaper/the-paper-2026-07-14-r1.pdf"   # the finalize record
    assert b["source"] == "finalize.json"
    assert Path(b["target_dir"]).name == "whitepaper"
    assert (md / b["pdf"]).is_file()                 # md / pdf IS the file, by contract


def test_target_dir_resolves_repo_relative_not_only_manuscript_relative(tmp_path):
    """SSG's plan declares the target dir REPO-relative ('synthetics papers/…/
    whitepaper'), not manuscript-relative. Both authorings resolve, nearest-first."""
    md = _ssg_shaped(tmp_path)
    rel = md.relative_to(tmp_path).as_posix() + "/whitepaper"     # 'proj/manuscript/whitepaper'
    b = R.artefact_pdf_binding(md, plan=_plan(target_dir=rel))
    assert b["pdf"] == "whitepaper/the-paper-2026-07-14-r1.pdf"
    assert R.resolve_target_dir(md, rel) == (md / "whitepaper")
    assert R.resolve_target_dir(md, str(md / "whitepaper")) == (md / "whitepaper")  # absolute
    assert R.resolve_target_dir(md, "no-such-dir") is None


def test_declared_target_dir_never_falls_through_to_the_manuscript_audit_pdf(tmp_path):
    """The load-bearing refusal: a target dir that yields NOTHING binds NOTHING. The
    manuscript's own top-level PDF is not a fall-through — that fall-through is the
    defect."""
    md = _ssg_shaped(tmp_path)
    empty = md / "empty_target"
    empty.mkdir()
    b = R.artefact_pdf_binding(md, plan=_plan(target_dir="empty_target"))
    assert b["pdf"] is None
    assert "no bindable artefact PDF" in b["reason"]
    assert "FIGURE_REVIEW" not in (b["pdf"] or "")


def test_declared_target_dir_that_resolves_nowhere_is_loud_not_a_fallback(tmp_path):
    md = _ssg_shaped(tmp_path)
    b = R.artefact_pdf_binding(md, plan=_plan(target_dir="ghost/dir"))
    assert b["pdf"] is None and "resolves to no directory" in b["reason"]


def test_release_deposit_is_the_last_rung_inside_the_target_dir(tmp_path):
    """A target dir with no finalize record / slug / main.pdf still binds — the newest
    release deposit — so a project that only ships releases is not left unreadable."""
    md = tmp_path / "m"
    _pdf(md / "FIGURE_REVIEW.pdf")
    _pdf(md / "t" / "release" / "paper-r1.pdf")
    b = R.artefact_pdf_binding(md, plan=_plan(target_dir="t"))
    assert b["pdf"] == "t/release/paper-r1.pdf" and b["source"] == "release-dir"


def test_finalize_record_outranks_a_stale_release_deposit(tmp_path):
    """At candidate lock the object under judgement is the CURRENT compiled candidate,
    never the object released a month ago."""
    md = _ssg_shaped(tmp_path)
    b = R.artefact_pdf_binding(md, plan=_plan(target_dir="whitepaper"))
    assert "release/" not in b["pdf"]
    assert b["pdf"].endswith("the-paper-2026-07-14-r1.pdf")


def test_no_target_dir_refuses_an_audit_pdf_on_the_guessed_rung(tmp_path):
    """With no target dir declared the shared ladder runs — but the GUESS (the sole
    top-level PDF) may not certify an audit sheet. Nothing binds, loudly."""
    md = tmp_path / "m"
    _pdf(md / "FIGURE_REVIEW.pdf")
    b = R.artefact_pdf_binding(md)                       # no plan at all
    assert b["pdf"] is None and b["refused"] == "FIGURE_REVIEW.pdf"
    assert "audit-named" in b["reason"]
    assert R.discover_artefact_pdf(md) is None


def test_an_authored_binding_is_never_second_guessed_by_name(tmp_path):
    """The refusal touches the GUESSED rung only: if a finalize record names a PDF,
    that is the author speaking and the resolver takes it at its word."""
    md = tmp_path / "m"
    _pdf(md / "FIGURE_REVIEW.pdf")
    (md / "release").mkdir(parents=True, exist_ok=True)
    (md / "release" / "finalize.json").write_text(
        json.dumps({"pdf_path": "FIGURE_REVIEW.pdf"}), encoding="utf-8")
    b = R.artefact_pdf_binding(md)
    assert b["pdf"] == "FIGURE_REVIEW.pdf" and b["source"] == "finalize.json"


def test_audit_name_table(tmp_path):
    for name in ("FIGURE_REVIEW.pdf", "figure-review.pdf", "figure review.pdf",
                 "judge_rounds.pdf", "calibration.pdf", "x/FIGURE_AUDIT.pdf"):
        assert R.is_audit_pdf(name), name
    for name in ("main.pdf", "ssg-whitepaper-2026-07-11-r6.pdf", "review-of-figures.pdf",
                 "the-figure-of-merit.pdf"):
        assert not R.is_audit_pdf(name), name


def test_plan_is_auto_read_from_the_committed_convention(tmp_path):
    """plan=None reads <manuscript>/projection_plan.json — the same file the compare
    phase opens, so the two phases can never disagree about the project."""
    md = _ssg_shaped(tmp_path)
    (md / "projection_plan.json").write_text(
        json.dumps(_plan(target_dir="whitepaper")), encoding="utf-8")
    b = R.artefact_pdf_binding(md)
    assert b["pdf"] == "whitepaper/the-paper-2026-07-14-r1.pdf"
    assert b["plan_path"].endswith("projection_plan.json")


def test_a_malformed_plan_refuses_to_bind_by_guess(tmp_path):
    md = _ssg_shaped(tmp_path)
    (md / "projection_plan.json").write_text("{not json", encoding="utf-8")
    b = R.artefact_pdf_binding(md)
    assert b["pdf"] is None and "does not parse" in b["reason"]


def test_plan_may_be_a_path(tmp_path):
    md = _ssg_shaped(tmp_path)
    p = tmp_path / "elsewhere_plan.json"
    p.write_text(json.dumps(_plan(target_dir="whitepaper")), encoding="utf-8")
    assert R.discover_artefact_pdf(md, plan=p) == "whitepaper/the-paper-2026-07-14-r1.pdf"
    assert R.discover_artefact_pdf(md, plan=str(p)) == "whitepaper/the-paper-2026-07-14-r1.pdf"


def test_target_dir_equal_to_the_manuscript_dir_is_the_plain_ladder(tmp_path):
    md = tmp_path / "m"
    _pdf(md / "main.pdf")
    b = R.artefact_pdf_binding(md, plan=_plan(target_dir="."))
    assert b["pdf"] == "main.pdf" and b["source"] == "main.pdf"


def test_the_release_machines_own_resolver_is_untouched(manuscript):
    """The four release-machine callers (bundle drift surface, snapshot, layout gates)
    keep byte-identical semantics: the plan-aware resolver is a SECOND function, and
    _discover_final_pdf answers exactly as it did."""
    md = manuscript
    rel = R._discover_final_pdf(md)
    assert rel == "main.pdf"
    bundle = R.build_bundle(md)
    assert bundle["final_pdf_path"] == rel          # build_bundle still binds THAT pdf
    # and a plan declaring a target dir does NOT reach into the release machine
    (md / "projection_plan.json").write_text(
        json.dumps(_plan(target_dir="whitepaper")), encoding="utf-8")
    _pdf(md / "whitepaper" / "main.pdf")
    assert R._discover_final_pdf(md) == "main.pdf"                 # unchanged
    assert R.discover_artefact_pdf(md) == "whitepaper/main.pdf"    # the reader's answer
