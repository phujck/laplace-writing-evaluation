"""BITE A1/A2/A4 — the planted-fixture drive of the WHOLE harnessed fixing pass.

Hermetic: NO LLM calls. The workflow's only model seam is the opus fixer; here it
is SIMULATED by a direct source edit at both branches. Every other stage is the
REAL driver (``harnessed_stage.py``) running the REAL built organs
(mechround/adjudicate/route) in-process over a throwaway project (the calibration
idiom), with a real ``latexmk`` compile and a real ``git`` repo for durability.

Two branches, both proven end-to-end:
  (a) a fixing pass that IMPROVES (removes the widening form + clears a fault) ->
      the re-detect gate reads improved, NOT regressed; no revert.
  (b) a fixing pass that REGRESSES — it "fixes" by ADDING a widening form (the
      detector-satisfying-object-worsening pathology) -> the gate reads regressed
      -> ``git revert`` of the pathspec-scoped fix commit FIRES and restores the
      pre-pass bytes (proven with git log + a source hash).

Also: the mechanical FIX BRIEF carries the verbatim math policy + the widening hit.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import planted_fixture as pf

pytestmark = pytest.mark.unit

_HAS_LATEXMK = shutil.which("latexmk") is not None
_HAS_GIT = shutil.which("git") is not None
requires_tools = pytest.mark.skipif(
    not (_HAS_LATEXMK and _HAS_GIT), reason="needs latexmk + git")


# ---------------------------------------------------------------------------
# the planted fixture: an orphan equation (a fault) + a font-shrunk table (a
# pre-existing WIDENING form — the r2 tab_dp-price reality)
# ---------------------------------------------------------------------------

_MAIN = ("\\documentclass{article}\n\\begin{document}\n"
         "\\input{N1}\n\\input{N2}\n\\end{document}\n")

_N1 = (r"\section{Method}\label{sec:method}" "\n"
       "The apparatus is measured against a fixed reference lattice throughout.\n"
       r"\begin{equation}\label{res:orphan}" "\n"
       "E = m c^2 .\n"
       r"\end{equation}" "\n"
       "The relation records the mass energy equivalence in plain words here.\n")

# N2 carries the widening form: a bare \small inside the table env (font-shrink).
_N2 = (r"\section{Results}" "\n"
       "The estimate established in the method holds across the sampled sizes.\n"
       r"\begin{table}" "\n"
       r"\caption{A compact results table for the reader.}" "\n"
       r"\small" "\n"
       r"\begin{tabular}{ll}" "\n"
       r"alpha & beta \\" "\n"
       r"gamma & delta \\" "\n"
       r"\end{tabular}" "\n"
       r"\end{table}" "\n")

_GITIGNORE = ("*.log\n*.pdf\n*.aux\n*.fls\n*.fdb_latexmk\n*.synctex.gz\n*.out\n"
              "*.bbl\n*.blg\nm/rounds/\nm/feedback/\n")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=False)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _build_repo(tmp_path: Path):
    """A scratch git repo with the planted manuscript at ``m/``; returns
    ``(repo, md, main_tex, feedback, proj)``. Volatile compile/ledger artifacts are
    gitignored so a durability commit is pathspec-clean (only the .tex sources)."""
    repo = tmp_path / "repo"
    md = repo / "m"
    md.mkdir(parents=True)
    (md / "main.tex").write_text(_MAIN, encoding="utf-8")
    (md / "N1.tex").write_text(_N1, encoding="utf-8")
    (md / "N2.tex").write_text(_N2, encoding="utf-8")
    (repo / ".gitignore").write_text(_GITIGNORE, encoding="utf-8")
    pf.write_plan(md / "plan.json", ["N1", "N2"])
    _git(repo, "init", "-q", "-b", "work")
    _git(repo, "config", "user.email", "eigen@laplace.test")
    _git(repo, "config", "user.name", "Eigen Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    proj = pf.make_project(plan_path=md / "plan.json", name=pf.THROWAWAY)
    return repo, md, str(md / "main.tex"), str(md / "feedback" / "feedback.jsonl"), proj


def _prepass(md, main_tex, feedback, repo, proj, monkeypatch, rnd=1):
    return pf.run_harnessed(
        "prepass", [main_tex, proj.name, "", feedback, str(repo), rnd, "-"],
        monkeypatch, proj)


def _redetect(md, main_tex, feedback, repo, proj, monkeypatch, pre_ev, rnd=2):
    return pf.run_harnessed(
        "redetect",
        [main_tex, proj.name, "", feedback, str(repo), rnd, "-", pre_ev, 1],
        monkeypatch, proj)


# ---------------------------------------------------------------------------
# the fix brief carries the policy + the widening hit
# ---------------------------------------------------------------------------

@requires_tools
def test_prepass_brief_carries_math_policy_and_widening_hit(tmp_path, monkeypatch):
    repo, md, main_tex, feedback, proj = _build_repo(tmp_path)
    ret = _prepass(md, main_tex, feedback, repo, proj, monkeypatch)
    brief = Path(ret["brief_path"]).read_text(encoding="utf-8")
    # the verbatim object-correct math policy (A2)
    assert ("overfull displays are SPLIT across lines (aligned/multline), never "
            "widened, never font-shrunk; tables rebuilt at correct width") in brief
    # the pre-existing widening form is named for removal
    assert "table-fontshrink" in brief
    assert ret["widening_n"] >= 1
    # the pre evidence file exists and records the widening count
    import json
    ev = json.loads(Path(ret["pre_evidence"]).read_text(encoding="utf-8"))
    assert ev["widening"]["n"] >= 1
    # the layout + tic ADVISORY evidence axis rode the detect (his hold-out review):
    # it is present, shaped, and never crashed detect. The tiny planted fixture is
    # tic-clean (a plain caption, no recurring disclaimer), so it carries no tic
    # findings — the point is that the axis is WIRED and additive, not a gate input.
    assert "layout_evidence" in ev
    assert ev["layout_evidence"].get("failed") is not True
    assert "counts" in ev["layout_evidence"]


# ---------------------------------------------------------------------------
# branch (a): an IMPROVING pass -> gate improved, no revert
# ---------------------------------------------------------------------------

@requires_tools
def test_improving_pass_reads_improved_not_regressed(tmp_path, monkeypatch):
    repo, md, main_tex, feedback, proj = _build_repo(tmp_path)
    pre = _prepass(md, main_tex, feedback, repo, proj, monkeypatch)
    assert pre["widening_n"] >= 1

    # SIMULATE the opus fixer, OBJECT-CORRECTLY: remove the \small (rebuild the table
    # at width) and reference the orphan equation (clear the fault). No widening added.
    (md / "N2.tex").write_text(_N2.replace("\\small\n", ""), encoding="utf-8")
    (md / "N1.tex").write_text(
        _N1 + "The result in \\ref{res:orphan} governs the estimate.\n",
        encoding="utf-8")

    post = _redetect(md, main_tex, feedback, repo, proj, monkeypatch,
                     pre["pre_evidence"])
    assert post["regressed"] is False
    assert post["improved"] is True
    assert post["widening_post"] < post["widening_pre"]     # 1 -> 0


# ---------------------------------------------------------------------------
# branch (b): a REGRESSING pass -> gate regressed -> git revert restores pre-pass
# ---------------------------------------------------------------------------

@requires_tools
def test_regressing_pass_fires_git_revert_and_restores(tmp_path, monkeypatch):
    repo, md, main_tex, feedback, proj = _build_repo(tmp_path)
    pre = _prepass(md, main_tex, feedback, repo, proj, monkeypatch)
    base_n2_sha = _sha(md / "N2.tex")                        # the pre-pass bytes

    # SIMULATE a REGRESSING fixer: "fix" the layout by ADDING a widening form —
    # wrap the tabular in \resizebox (the detector-satisfying-object-worsening move).
    regressed_n2 = _N2.replace(
        "\\begin{tabular}{ll}",
        "\\resizebox{\\linewidth}{!}{\\begin{tabular}{ll}").replace(
        "\\end{tabular}", "\\end{tabular}}")
    (md / "N2.tex").write_text(regressed_n2, encoding="utf-8")
    assert _sha(md / "N2.tex") != base_n2_sha               # the pass changed bytes

    # bank the fixing pass durably (the loop_commit idiom, pathspec-scoped); capture
    # the fix commit sha so a regression can revert exactly that pass.
    commit = pf.run_harnessed("commit", ["m", "harnessed-fix-r1", str(repo)],
                              monkeypatch, proj)
    assert commit["ok"] is True and commit["sha"]
    fix_sha = commit["sha"]
    n_commits_before = int(_git(repo, "rev-list", "--count", "HEAD").stdout.strip())

    # re-detect: the widening tell fires (1 -> 2), so the gate reads REGRESSED.
    post = _redetect(md, main_tex, feedback, repo, proj, monkeypatch,
                     pre["pre_evidence"])
    assert post["widening_post"] > post["widening_pre"]     # 1 -> 2
    assert post["regressed"] is True
    assert post["improved"] is False

    # the revert-on-regression path FIRES (git revert of the pathspec-scoped pass).
    rev = pf.run_harnessed("revert", [str(repo), fix_sha], monkeypatch, proj)
    assert rev["reverted"] is True
    assert rev["head_after"] != rev["head_before"]

    # PROOF 1 (git log): a revert commit was created on top of the fix.
    n_commits_after = int(_git(repo, "rev-list", "--count", "HEAD").stdout.strip())
    assert n_commits_after == n_commits_before + 1
    subj = _git(repo, "log", "-1", "--pretty=%s").stdout.strip()
    assert "Revert" in subj

    # PROOF 2 (source hash): N2.tex is byte-restored to the pre-pass state.
    assert _sha(md / "N2.tex") == base_n2_sha


# ---------------------------------------------------------------------------
# durability: the fix commit is pathspec-scoped (loop_commit reuse) — sources only
# ---------------------------------------------------------------------------

@requires_tools
def test_fix_commit_is_pathspec_scoped_to_sources(tmp_path, monkeypatch):
    repo, md, main_tex, feedback, proj = _build_repo(tmp_path)
    _prepass(md, main_tex, feedback, repo, proj, monkeypatch)
    (md / "N2.tex").write_text(_N2.replace("\\small\n", ""), encoding="utf-8")
    commit = pf.run_harnessed("commit", ["m", "harnessed-fix-r1", str(repo)],
                              monkeypatch, proj)
    assert commit["ok"] is True
    names = _git(repo, "show", "HEAD", "--name-only", "--format=").stdout
    assert "m/N2.tex" in names
    # gitignored volatile artifacts never ride the durability commit
    assert ".log" not in names and ".pdf" not in names
    assert "feedback/feedback.jsonl" not in names


# ---------------------------------------------------------------------------
# the per-axis convergence ratchet: a clean->fail flip on ONE axis is flagged
# EVEN inside an already-hard-failing aggregate (invisible to the open-count gate)
# ---------------------------------------------------------------------------

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "harnessed_stage", str(pf.WORKFLOWS / "harnessed_stage.py"))
_hs = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_hs)


def _round(*, no_meta_leak, meta_leak_clean):
    """A minimal banked round-json: two hard dims failing throughout (technical_support
    always False -> the aggregate is hard-failing), only ``no_meta_leak`` / the
    ``meta_leak`` panel cell flipped between rounds."""
    return {
        "round": 1,
        "hard_failing": True,
        "contract": {
            "hard": {"semantic_identity": True, "technical_support": False,
                     "structural_fulfilment": True, "artefact_integrity": True,
                     "provenance_integrity": True, "no_meta_leak": no_meta_leak},
            "soft": {"reader_reconstruction": 0.5, "prose_transparency": 0.5,
                     "authorial_fit": 0.5, "economy_of_attention": 0.5,
                     "rhythm": 0.5, "citation_coverage": 0.5,
                     "style_conformance": 1.0},
        },
        "panel": [{"label": "meta_leak", "clean": meta_leak_clean, "flags": []},
                  {"label": "caption", "clean": True, "flags": []}],
    }


def test_per_axis_ratchet_flags_flip_inside_hard_failing_aggregate():
    prior = _round(no_meta_leak=True, meta_leak_clean=True)   # r1: no_meta_leak CLEAN
    this = _round(no_meta_leak=False, meta_leak_clean=False)  # r2: no_meta_leak FAILS

    frontier = _hs._axis_frontier([prior])
    assert frontier["hard"]["no_meta_leak"] is True
    assert frontier["panel"]["meta_leak"] is True

    regs = _hs._axis_regressions(frontier, this)
    # the flip is named on BOTH its hard dim and its panel cell
    axes = {r["axis"] for r in regs}
    assert "hard.no_meta_leak" in axes
    assert "panel.meta_leak" in axes
    leak = next(r for r in regs if r["axis"] == "hard.no_meta_leak")
    assert leak["from"] is True and leak["to"] is False
    # technical_support failed in BOTH rounds -> never clean at the frontier -> not a
    # regression (the ratchet flags flips down FROM clean, not standing failures)
    assert not any("technical_support" in a for a in axes)

    # the aggregate _gate verdict is UNCHANGED: both rounds hard-fail, widening flat,
    # compile ok -> no aggregate regression, per-axis flip recorded ALONGSIDE it.
    pre = {"open_findings_n": 5, "widening": {"n": 0}, "hard_failing": True,
           "compile_ok": True}
    post = {"open_findings_n": 5, "widening": {"n": 0}, "hard_failing": True,
            "compile_ok": True}
    verdict = _hs._gate(pre, post, threshold=3, passes_done=1, max_passes=2)
    assert verdict["regressed"] is False
    assert verdict["improved"] is False


# ---------------------------------------------------------------------------
# C5.4 — the NET-AXIS ratchet: the coarse widening tell refined into a per-axis
# vote. `_round_axes` reads the {hard, soft, panel} contract from a phase's round
# json; when a dict carries no `round_file` it IS the round json (the unit-test
# path), so a single dict below carries both the aggregate _gate fields and the
# per-axis contract. Revert (regressed) fires iff net < 0 OR a non-offsettable
# catastrophic trigger (broken compile / clean->hard-fail) fired.
# ---------------------------------------------------------------------------

def _ev(*, hard_failing, compile_ok, widening_n, hard=None, soft=None, panel=None,
        open_n=5):
    """A detect-phase dict doubling as its own round-json: the aggregate gate fields
    (open/widening/hard_failing/compile_ok) PLUS the per-axis contract read by
    `_round_axes` (no `round_file` key -> the dict itself is the round json)."""
    return {
        "open_findings_n": open_n,
        "widening": {"n": widening_n},
        "hard_failing": hard_failing,
        "compile_ok": compile_ok,
        "contract": {"hard": dict(hard or {}), "soft": dict(soft or {})},
        "panel": [{"label": k, "clean": v} for k, v in (panel or {}).items()],
    }


def test_net_axis_improvement_offsets_noise_not_reverted():
    """(1) a pass IMPROVING technical_support while NUDGING prose noise is a one-for-one
    net (0) -> NOT reverted: an improvement on axis A is not reverted for axis-B noise."""
    pre = _ev(hard_failing=True, compile_ok=True, widening_n=0,
              hard={"technical_support": False}, soft={"prose_transparency": 0.60})
    post = _ev(hard_failing=False, compile_ok=True, widening_n=0,
               hard={"technical_support": True}, soft={"prose_transparency": 0.50})
    v = _hs._gate(pre, post, threshold=3, passes_done=1, max_passes=2)
    assert v["net_axis"]["n_improved"] == 1   # hard.technical_support up
    assert v["net_axis"]["n_regressed"] == 1  # soft.prose_transparency down > EPS
    assert v["net_axis"]["net"] == 0
    assert v["catastrophic"] is False
    assert v["regressed"] is False            # net 0 does NOT revert


def test_net_axis_two_regressions_outweigh_one_improvement_reverted():
    """(2) a pass REGRESSING two axes while IMPROVING one -> net -1 -> reverted, purely
    on the net vote (no catastrophic trigger: compile ok, no clean->hard-fail flip)."""
    pre = _ev(hard_failing=False, compile_ok=True, widening_n=0,
              soft={"reader_reconstruction": 0.50, "rhythm": 0.50, "authorial_fit": 0.50})
    post = _ev(hard_failing=False, compile_ok=True, widening_n=0,
               soft={"reader_reconstruction": 0.70, "rhythm": 0.30, "authorial_fit": 0.30})
    v = _hs._gate(pre, post, threshold=3, passes_done=1, max_passes=2)
    assert v["net_axis"]["n_improved"] == 1
    assert v["net_axis"]["n_regressed"] == 2
    assert v["net_axis"]["net"] == -1
    assert v["catastrophic"] is False
    assert v["regressed"] is True             # net < 0 reverts


def test_net_axis_hard_dim_regression_is_non_compensable():
    """THE SEVERITY LAW (the C5.4 judge's catch): one hard-dim clean->fail flip
    reverts REGARDLESS of the net — two soft improvements cannot outvote it, and
    the flip triggers even when the AGGREGATE hard_failing never moved (the per-dim
    flip the aggregate is blind to). The contract's hard block is
    convergence.HARD_DIMENSIONS: non-compensable by construction."""
    pre = _ev(hard_failing=False, compile_ok=True, widening_n=0,
              hard={"semantic_identity": True},
              soft={"rhythm": 0.40, "authorial_fit": 0.40})
    post = _ev(hard_failing=False, compile_ok=True, widening_n=0,
               hard={"semantic_identity": False},
               soft={"rhythm": 0.70, "authorial_fit": 0.70})
    v = _hs._gate(pre, post, threshold=3, passes_done=1, max_passes=2)
    assert v["net_axis"]["hard_regressed"] and \
        v["net_axis"]["hard_regressed"][0]["axis"] == "hard.semantic_identity"
    assert v["net_axis"]["net"] == 2          # the compensable vote is positive...
    assert v["catastrophic"] is True          # ...and it does not matter
    assert v["regressed"] is True             # one hard regression reverts


def test_net_axis_catastrophic_regression_is_not_offsettable():
    """(3) a broken compile (the un-revertable class of regression) STILL flags
    regressed=True even when the net axis vote is strongly positive — a catastrophic
    trigger cannot be masked by gains elsewhere, so the pass reaches the JS revert /
    HARD-STOP-before-lock path. This is the gate-side guardian of that invariant."""
    pre = _ev(hard_failing=False, compile_ok=True, widening_n=2,
              soft={"rhythm": 0.30, "authorial_fit": 0.30, "economy_of_attention": 0.30})
    post = _ev(hard_failing=False, compile_ok=False, widening_n=0,  # COMPILE BROKE
               soft={"rhythm": 0.90, "authorial_fit": 0.90, "economy_of_attention": 0.90})
    v = _hs._gate(pre, post, threshold=3, passes_done=1, max_passes=2)
    assert v["net_axis"]["net"] > 0           # the improvements are real...
    assert v["catastrophic"] is True          # ...but the compile broke
    assert v["regressed"] is True             # so the pass is NOT shippable


def test_net_axis_pure_improvement_and_pure_regression_unchanged():
    """(4) the pure cases behave as before the refinement. Pure improvement (widening
    drops, nothing else) -> not reverted, improved. Pure regression (widening rises,
    nothing else) -> reverted, exactly as the old coarse widening tell did."""
    pre = _ev(hard_failing=False, compile_ok=True, widening_n=2)
    post = _ev(hard_failing=False, compile_ok=True, widening_n=0)
    v = _hs._gate(pre, post, threshold=3, passes_done=1, max_passes=2)
    assert v["net_axis"]["net"] == 1
    assert v["regressed"] is False
    assert v["improved"] is True

    pre2 = _ev(hard_failing=False, compile_ok=True, widening_n=0)
    post2 = _ev(hard_failing=False, compile_ok=True, widening_n=2)
    v2 = _hs._gate(pre2, post2, threshold=3, passes_done=1, max_passes=2)
    assert v2["net_axis"]["net"] == -1
    assert v2["regressed"] is True


# ---------------------------------------------------------------------------
# A2 — the composed round-file emitter (pure inputs -> file) + the dispatch-switch
# source contracts (grep idiom: the JS actually reads the dial + gates on composed)
# ---------------------------------------------------------------------------

def _mech_round(*, eligible=True):
    """A mechround-shaped round record (what the harnessed redetect writes)."""
    return {
        "round": 2, "workflow": "project-fixedpoint", "target": "m/main.tex",
        "panel": [{"label": "meta_leak", "clean": True, "flags": []}],
        "compile_report": {"undefined": 0, "errors": 0, "log_is_real": True},
        "contract": {"hard": {"no_meta_leak": True}, "soft": {}},
        "hard_failing": [] if eligible else ["no_meta_leak"],
        "complete": True, "lock_eligible": bool(eligible),
    }


def test_emit_round_file_writes_the_pipeline_read_fields(tmp_path):
    src = tmp_path / "mech_r2.json"
    import json
    src.write_text(json.dumps(_mech_round(eligible=True)), encoding="utf-8")
    out = _hs.emit_round_file(str(tmp_path / "jr"), 1, str(src),
                              target="m/main.tex", project="p")
    assert Path(out).name == "harnessed_round1.json"
    doc = json.loads(Path(out).read_text(encoding="utf-8"))
    # the exact fields project-pipeline.js reads at CANDIDATE_LOCKED + the bundle
    for k in ("round", "hard_failing", "compile_report", "complete",
              "lock_eligible", "contract", "panel"):
        assert k in doc, k
    assert doc["round"] == 1                       # re-keyed to the pass ordinal
    assert doc["workflow"] == "project-harnessed"  # provenance re-stamped
    assert doc["target"] == "m/main.tex" and doc["project"] == "p"


def test_emit_round_file_follows_a_detect_evidence_pointer(tmp_path):
    """The redetect hands the emitter its DETECT-EVIDENCE json (simplified, no
    compile_report); the emitter must follow its ``round_file`` pointer to the mechround
    round json that actually carries the lock/bundle shape."""
    import json
    mech = tmp_path / "mech_r2.json"
    mech.write_text(json.dumps(_mech_round(eligible=True)), encoding="utf-8")
    ev = tmp_path / "detect_post_r2.json"
    ev.write_text(json.dumps({"phase": "post", "round": 2, "hard_failing": False,
                              "round_file": str(mech)}), encoding="utf-8")
    out = _hs.emit_round_file(str(tmp_path / "jr"), 1, str(ev))
    doc = json.loads(Path(out).read_text(encoding="utf-8"))
    assert doc["panel"] == [{"label": "meta_leak", "clean": True, "flags": []}]
    assert doc["compile_report"] == {"undefined": 0, "errors": 0, "log_is_real": True}
    assert doc["complete"] is True


def test_project_pipeline_reads_fix_mode_and_dispatches_both_organs():
    """The A1 dispatch switch is REAL in the driver: project-pipeline.js reads
    DIALS.loop.fix_mode and dispatches project-harnessed.js (composed) OR
    project-fixedpoint.js conditionally."""
    src = (pf.WORKFLOWS / "project-pipeline.js").read_text(encoding="utf-8")
    assert "DIALS.loop.fix_mode" in src                     # the dial is read
    assert "project-harnessed.js" in src                    # the harnessed organ
    assert "project-fixedpoint.js" in src                   # the old loop still reachable
    assert "FIX_MODE === 'harnessed'" in src                # the conditional dispatch
    assert "composed: true" in src                          # composed is passed on


def test_project_harnessed_gates_self_finalize_behind_composed():
    """The A2 composed mode is REAL: project-harnessed.js reads A.composed, gates its
    self-finalize behind !COMPOSED, and the round file is emitted IN-PROCESS by the
    redetect measurement (the live-proof finding, 2026-07-15, author-ratified: evidence
    is written at measure time by the measuring process — the post-hoc emit agent is
    banned and must not reappear)."""
    src = (pf.WORKFLOWS / "project-harnessed.js").read_text(encoding="utf-8")
    assert "A.composed" in src                              # the arg is read
    assert "if (!COMPOSED) {" in src                        # self-finalize gated off
    assert "harnessed_round" in src                         # the emitted round file
    assert "q(JUDGE_ROUNDS) : ''" in src                    # redetect carries the emit dir when composed
    assert "STAGE_PY} emit" not in src                      # the post-hoc emit agent is GONE
    assert "emit-round#" not in src                         # ...and its label with it
    assert "ret.composed = true" in src                     # composed return flag
