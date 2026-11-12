"""Leg A1 ADVERSARIAL JUDGE probes — a FRESH judge refuting the harnessed organ.

These pin behaviours the builder's own suite did not assert, at the seams a
refutation attacks: the regression gate's EQUALITY case, the durability commit on a
NO-OP fixer pass, commit-grain revert across TWO files, the A2 tell's
false-positive shyness, the idempotence guard under a machine-DISMISSAL and under
supersede→repour→supersede, the harnessed self-compile argv index, and the
``_open_findings`` filter's agreement with the real route.

Every test here is GREEN. The judge's two actionable findings have since been FIXED
in the organ, and the two probes that once CHARACTERISED those defects now assert the
FIXED behaviour:
  * FINDING A — ``_open_findings`` now reuses the route's suppress-first + defer
    primitives, so a machine-DISMISSED finding is ABSENT from the harnessed view,
    the brief, and the gate count (was: the dismissed finding was re-surfaced).
  * FINDING B — ``project-harnessed.js`` now gates ``fixSha`` on ``commit.committed``,
    so a no-op pass + a regression signal reverts NO innocent history (was: it would
    ``git revert`` the prior commit); ``cmd_revert`` records the no-op durably.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from laplace.pipeline import ledger as L
from laplace.pipeline import suppress as S
from laplace.pipeline import adjudicate as ADJ
from laplace.pipeline import schema
from laplace.pipeline import math_layout_tell as W

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_WF = _REPO / ".claude" / "workflows"
_HAS_GIT = shutil.which("git") is not None
requires_git = pytest.mark.skipif(not _HAS_GIT, reason="needs git")


def _load_harnessed_stage():
    spec = importlib.util.spec_from_file_location(
        "harnessed_stage_probe", _WF / "harnessed_stage.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HS = _load_harnessed_stage()


def _git(repo: Path, *a: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *a],
                          capture_output=True, text=True, check=False)


def _seed_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    md = repo / "m"
    md.mkdir(parents=True)
    (md / "N1.tex").write_text("N1 original\n", encoding="utf-8")
    (md / "N2.tex").write_text("N2 original\n", encoding="utf-8")
    (repo / ".gitignore").write_text("*.log\n*.pdf\nm/rounds/\nm/feedback/\n",
                                     encoding="utf-8")
    _git(repo, "init", "-q", "-b", "work")
    _git(repo, "config", "user.email", "judge@laplace.test")
    _git(repo, "config", "user.name", "Judge")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")
    return repo, md


def _run_cmd(fn, argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn(argv)
    line = next(l for l in buf.getvalue().splitlines()
               if l.startswith("HARNESSED_JSON:"))
    return json.loads(line[len("HARNESSED_JSON:"):]), rc


# ===========================================================================
# PROBE 2b — the regression GATE's EQUALITY case (same counts pre/post)
# ===========================================================================

def _ev(open_n, wid_n, hard=False, comp=True):
    return {"open_findings_n": open_n, "widening": {"n": wid_n},
            "hard_failing": hard, "compile_ok": comp}


def test_gate_equality_is_neither_regressed_nor_improved():
    # a pass that changed nothing the panel measures: strictly-equal counts.
    v = HS._gate(_ev(4, 1), _ev(4, 1), threshold=3, passes_done=1, max_passes=2)
    assert v["regressed"] is False           # no strict growth -> not reverted
    assert v["improved"] is False            # no strict reduction -> no credit
    assert v["second_pass"] is False         # second pass needs improved


def test_gate_equality_flow_accepts_and_proceeds_to_lock():
    # DELIBERATE per the JS control-flow: regressed=False => accepted=true, no
    # revert; improved=False => second_pass=False => converged, proceed to lock.
    v = HS._gate(_ev(0, 0), _ev(0, 0), threshold=3, passes_done=1, max_passes=2)
    accepted = not v["regressed"]
    proceeds_to_lock = accepted and not v["second_pass"]
    assert accepted and proceeds_to_lock


def test_gate_widening_swap_is_invisible_to_a_count_gate():
    # a fixer that removes one widening form AND adds another (net wid equal) reads
    # as an equality pass — a known BLIND SPOT of count-based gating (banked, not a
    # regression the gate can see).
    v = HS._gate(_ev(2, 1), _ev(2, 1), threshold=3, passes_done=1, max_passes=2)
    assert v["regressed"] is False and v["improved"] is False


# ===========================================================================
# PROBE 2c / FINDING B — the durability COMMIT on a NO-OP (empty) fixer pass
# ===========================================================================

@requires_git
def test_empty_pass_commit_reports_committed_false_with_prior_sha(tmp_path):
    # the fixer edited nothing; loop_commit finds a clean tree. cmd_commit returns
    # ok=True (no git error) but committed=False, and `sha` is the PRIOR HEAD.
    repo, _md = _seed_repo(tmp_path)
    seed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    out, rc = _run_cmd(HS.cmd_commit, ["m", "harnessed-fix-r1", str(repo)])
    assert out["ok"] is True
    assert out["committed"] is False, "an empty pass did not commit"
    assert out["sha"] == seed, "sha on a no-op is the PRIOR commit, not this pass"
    # FINDING B (FIXED): project-harnessed.js now gates `fixSha = commit.committed ===
    # true && commit.sha`, so on a no-op pass fixSha is '' (never the innocent prior
    # commit). The regression path then takes cmd_revert's documented NO-OP branch —
    # proven in test_noop_pass_regression_reverts_no_innocent_history below — instead
    # of git-reverting real history. The guard keys on `committed`, not `sha`.


@requires_git
def test_noop_pass_regression_reverts_no_innocent_history(tmp_path):
    # FINDING B end-to-end: a NO-OP fixer pass + a regression signal must NEVER revert
    # the innocent prior commit. Reproduce the JS gate in Python: fixSha is '' when the
    # commit did not commit, so the regression branch calls `revert <repo> - <dir>`,
    # which does NO git op and writes an explicit evidence note.
    repo, md = _seed_repo(tmp_path)
    seed = _git(repo, "rev-parse", "HEAD").stdout.strip()
    # the no-op fixer pass: nothing edited -> loop_commit finds a clean tree.
    commit, _ = _run_cmd(HS.cmd_commit, ["m", "harnessed-fix-r1p1", str(repo)])
    assert commit["ok"] is True and commit["committed"] is False
    # the JS gate (project-harnessed.js): fixSha = committed===true ? sha : ''.
    fix_sha = commit["sha"] if commit["committed"] is True else ""
    assert fix_sha == "", "a no-op pass yields an EMPTY fix sha (never prior HEAD)"
    # a regression is signalled; the revert stage is driven with the empty sentinel.
    rev, rc = _run_cmd(HS.cmd_revert, [str(repo), fix_sha or "-", str(md), "r1p1"])
    assert rc == 0                                 # a documented no-op is success
    assert rev["reverted"] is False and rev["no_op"] is True
    assert rev["head_before"] == rev["head_after"] == seed
    # HEAD is byte-for-byte the innocent seed: NO revert commit was created.
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == seed
    # and the no-op is durably noted in an evidence file.
    ev = Path(rev["evidence_path"])
    assert ev.exists() and ev.name.startswith("revert_noop_")
    note = json.loads(ev.read_text(encoding="utf-8"))
    assert note["no_op"] is True and note["reverted"] is False
    assert "no revert" in note["note"].lower()


# ===========================================================================
# PROBE 2a — commit-grain REVERT restores ALL files the pass touched (two files)
# ===========================================================================

@requires_git
def test_two_file_fix_commit_reverts_both_files(tmp_path):
    repo, md = _seed_repo(tmp_path)
    n1_pre = hashlib.sha256((md / "N1.tex").read_bytes()).hexdigest()
    n2_pre = hashlib.sha256((md / "N2.tex").read_bytes()).hexdigest()
    # a pass that edits BOTH fragments
    (md / "N1.tex").write_text("N1 CHANGED\n", encoding="utf-8")
    (md / "N2.tex").write_text("N2 CHANGED\n", encoding="utf-8")
    commit, _ = _run_cmd(HS.cmd_commit, ["m", "harnessed-fix-r1", str(repo)])
    assert commit["ok"] is True and commit["committed"] is True
    rev, _ = _run_cmd(HS.cmd_revert, [str(repo), commit["sha"]])
    assert rev["reverted"] is True
    # commit-grain revert => BOTH files byte-restored (no leak of the second file)
    assert hashlib.sha256((md / "N1.tex").read_bytes()).hexdigest() == n1_pre
    assert hashlib.sha256((md / "N2.tex").read_bytes()).hexdigest() == n2_pre


# ===========================================================================
# PROBE 2d / FINDING F2 (FIXED) — the durability pathspec covers every
# \input-reachable fragment, including one ACROSS a directory boundary
# ===========================================================================

@requires_git
def test_cross_boundary_input_fragment_is_banked_by_the_accept_commit(tmp_path):
    """F2 (judge): the eigenengine run's accepted object edit lived in an \\input
    fragment OUTSIDE the manuscript dir (paper_eigen/_experiments/), and the loop's
    manuscript-dir-scoped accept commit never reached it — the fix shipped UNCOMMITTED.
    THE FIX: cmd_commit derives the \\input graph from main_tex and WIDENS the
    durability pathspec to every cross-boundary fragment, so an accepted edit outside
    the manuscript dir can never ship unbanked."""
    repo = tmp_path / "repo"
    md = repo / "proj" / "manuscript"        # the <project>/manuscript/ convention
    ext = repo / "proj" / "_experiments"     # a SIBLING dir the manuscript \inputs from
    md.mkdir(parents=True)
    ext.mkdir(parents=True)
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\n"
        "\\input{../_experiments/appendix.tex}\n\\end{document}\n", encoding="utf-8")
    (ext / "appendix.tex").write_text(
        "\\begin{table}\\small\\begin{tabular}{clrr}a&b\\\\\\end{tabular}\\end{table}\n",
        encoding="utf-8")
    (repo / ".gitignore").write_text("*.log\n*.pdf\n", encoding="utf-8")
    _git(repo, "init", "-q", "-b", "work")
    _git(repo, "config", "user.email", "judge@laplace.test")
    _git(repo, "config", "user.name", "Judge")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed")

    # the accepted fixer edits the CROSS-BOUNDARY fragment (the \\small->p{} rebuild).
    (ext / "appendix.tex").write_text(
        "\\begin{table}\\begin{tabular}{c p{6cm} r r}a&b\\\\\\end{tabular}\\end{table}\n",
        encoding="utf-8")

    main_tex = str(md / "main.tex")
    out, rc = _run_cmd(HS.cmd_commit,
                       ["proj/manuscript", "harnessed-fix-r1", str(repo), main_tex])
    assert out["ok"] is True and out["committed"] is True
    # the durability pathspec REACHED the cross-boundary fragment.
    assert "proj/_experiments/appendix.tex" in out.get("input_fragments", []), \
        "the \\input graph did not surface the cross-boundary fragment"
    names = _git(repo, "show", "HEAD", "--name-only", "--format=").stdout
    assert "proj/_experiments/appendix.tex" in names, \
        "the accept commit did NOT bank the cross-boundary \\input fragment (F2)"
    # ONE commit banks the whole accepted edit (the single-sha revert invariant holds):
    # the tree is clean for the fragment now, nothing left unbanked.
    assert "appendix.tex" not in _git(repo, "status", "--porcelain").stdout


@requires_git
def test_no_cross_boundary_fragment_keeps_loop_commit_path(tmp_path):
    """F2 regression guard: with NO cross-boundary \\input (or no main_tex), cmd_commit
    delegates to loop_commit.py UNCHANGED — the base pathspec is the manuscript dir,
    and the durability contract (committed/sha/no-op) is byte-for-byte as before."""
    repo, md = _seed_repo(tmp_path)
    (md / "N1.tex").write_text("N1 changed in place\n", encoding="utf-8")
    # main_tex whose \input tree stays INSIDE m/ -> no external fragment.
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\\input{N1}\\end{document}\n",
        encoding="utf-8")
    out, rc = _run_cmd(HS.cmd_commit,
                       ["m", "harnessed-fix-r1", str(repo), str(md / "main.tex")])
    assert out["ok"] is True and out["committed"] is True
    assert out.get("pathspecs") == ["m"], "no external fragment -> manuscript-dir pathspec only"
    names = _git(repo, "show", "HEAD", "--name-only", "--format=").stdout
    assert "m/N1.tex" in names


# ===========================================================================
# PROBE 5 — the A2 widening tell is FALSE-POSITIVE SHY
# ===========================================================================

def test_resizebox_around_a_figure_is_not_flagged():
    src = (r"\begin{figure}" "\n"
           r"\resizebox{\linewidth}{!}{\includegraphics{plot.pdf}}" "\n"
           r"\end{figure}" "\n")
    assert W.detect_widening(src) == []          # a scaled figure is A3's concern


def test_fontkey_small_in_a_tikz_node_is_not_flagged():
    src = (r"\begin{tikzpicture}" "\n"
           r"\node[font=\small] at (0,0) {label};" "\n"
           r"\end{tikzpicture}" "\n")
    assert W.detect_widening(src) == []          # font=\small pgfkey is legitimate


def test_bare_small_around_prose_is_not_flagged():
    src = ("An ordinary paragraph of running prose here.\n"
           r"{\small a fine-print aside, not near any display or table.}" "\n"
           "More ordinary prose after it.\n")
    assert W.detect_widening(src) == []          # prose sizing is not this pathology


def test_commented_out_small_in_a_table_is_not_flagged():
    src = (r"\begin{table}" "\n"
           r"% \small  <- deliberately disabled, must not trip" "\n"
           r"\begin{tabular}{ll}a&b\\\end{tabular}" "\n"
           r"\end{table}" "\n")
    assert W.detect_widening(src) == []


def test_true_positive_forms_still_fire():
    # the tell must still catch the real pathologies (guard against over-shy tuning).
    tab = (r"\begin{table}" "\n" r"\small" "\n"
           r"\begin{tabular}{ll}a&b\\\end{tabular}" "\n" r"\end{table}" "\n")
    resz = r"\resizebox{\linewidth}{!}{\begin{tabular}{ll}a&b\\\end{tabular}}" "\n"
    rule = r"\rule{\linewidth}{0.4pt}" "\n"
    assert any(h["kind"] == "table-fontshrink" for h in W.detect_widening(tab))
    assert any(h["kind"] == "table-scalebox" for h in W.detect_widening(resz))
    assert any(h["kind"] == "rule-width-separator" for h in W.detect_widening(rule))


# ===========================================================================
# PROBE 4 — idempotence semantics under DISMISSAL and supersede churn
# ===========================================================================

def _finding(**over):
    f = {"reader": "R1", "kind": "imprecise", "section": "N2",
         "anchor": {"section": "N2"}, "where": "N2-p1 a vague phrase",
         "issue": "vague"}
    f.update(over)
    return f


def _n_findings(fb):
    # count only actual FINDING records (the suppression record shares the kind, so
    # filter it out by its record type).
    return sum(1 for r in L.read_jsonl(fb)
               if r.get("kind") == "imprecise" and r.get("record") != S.RECORD_KIND)


def test_dismissed_finding_repour_is_a_noop_not_a_resurrection(tmp_path):
    # a machine DISMISSAL is a SUPPRESSION (fingerprint-keyed); it does NOT supersede
    # the finding id, so the original stays LIVE per the idempotence guard and a
    # re-pour returns the twin (no second live record). The dismissed finding is not
    # resurrected THROUGH the door.
    fb = tmp_path / "fb.jsonl"
    a = L.pour_finding(fb, _finding(), project="p")
    L.append_jsonl(fb, S.make_suppression("N2", "imprecise", "node body",
                                          reason="ruled not a fault", actor="machine",
                                          round=1, section="N2"))
    b = L.pour_finding(fb, _finding(), project="p")
    assert a["id"] == b["id"]
    assert _n_findings(fb) == 1, "re-pour after dismissal must be a no-op"


def test_supersede_then_repour_then_supersede_leaves_no_live_zombie(tmp_path):
    fb = tmp_path / "fb.jsonl"
    x = L.pour_finding(fb, _finding(), project="p")
    L.append_jsonl(fb, ADJ.make_resolution(x["id"], project="p"))   # supersede
    y = L.pour_finding(fb, _finding(), project="p")                 # recur -> re-opens
    assert y["id"] == x["id"]
    assert _n_findings(fb) == 2                                     # a spent + a fresh
    L.append_jsonl(fb, ADJ.make_resolution(x["id"], project="p"))   # supersede again
    recs = L.read_jsonl(fb)
    superseded = {r.get("supersedes") for r in recs if r.get("supersedes")}
    live = [r for r in recs if r.get("kind") == "imprecise"
            and r.get("record") != S.RECORD_KIND
            and r.get("id") not in superseded
            and (r.get("status") or "open") != "resolved"]
    # a supersede keyed on the id retires EVERY same-id copy at once -> no zombie.
    assert live == [], "no live record with a superseded id may survive"


# ===========================================================================
# PROBE 8 — the harnessed self-compile LANDS `compile` at the gated argv index
# ===========================================================================

def test_harnessed_detect_places_compile_at_the_gated_argv_index(tmp_path, monkeypatch):
    # fixedpoint_mechround.py gates its atomic self-compile on sys.argv[13]=='compile'
    # (len>13). The harnessed driver MUST land `compile` there or the central "ONE
    # compile" claim silently would not fire. Capture the exact tail the driver hands
    # to the stage (runpy sets sys.argv = [script] + tail, so tail[12] == argv[13]).
    main_tex = tmp_path / "m" / "main.tex"
    main_tex.parent.mkdir(parents=True)
    main_tex.write_text("x", encoding="utf-8")
    captured = {}

    def fake_drive(script, tail):
        captured["script"] = script
        captured["tail"] = list(tail)
        return 'MECH_JSON:{"hard_failing": false, "compile_ok": true}'

    monkeypatch.setattr(HS, "_drive", fake_drive)
    HS._run_detect(str(main_tex), "proj", "", "-", str(tmp_path), 1, "-",
                   compile_it=True)
    assert captured["script"] == HS.MECH_PY
    tail = captured["tail"]
    # sys.argv would be [script] + tail; the gate reads sys.argv[13] => tail[12].
    assert tail[12] == "compile", "the harnessed self-compile must sit at argv[13]"
    assert len(tail) == 13


def test_mechround_gate_reads_argv_index_13():
    # ground the friction in the real source: the gate literally requires index 13,
    # and the OLD loop (project-fixedpoint.js) passes `compile` at index 12 (len==13),
    # so `len(sys.argv) > 13` is False there — the demoted loop's self-compile never
    # fires (banked friction). The harnessed path lands it at 13 (test above).
    mech = (_WF / "fixedpoint_mechround.py").read_text(encoding="utf-8")
    assert 'len(sys.argv) > 13 and sys.argv[13] == "compile"' in mech


# ===========================================================================
# FINDING A (FIXED) — `_open_findings` now applies the route's suppress-first
#             filter, so a machine-DISMISSED finding is ABSENT from the harnessed
#             view, the brief, and the gate count. (Was: the probe proved the
#             DEFECT — the dismissed finding was re-surfaced to the strong fixer;
#             inverted to green against the fixed behaviour.)
# ===========================================================================

def _seed_dismissed_manuscript(tmp_path):
    """A minimal manuscript whose N2 fragment is EXACTLY the node body the machine
    dismissal was fingerprinted on, plus a feedback ledger carrying one routable
    finding on N2 and a matching-fingerprint machine dismissal of it. Returns
    (main_tex, feedback_path, node_body)."""
    schema.register_component_kinds()
    md = tmp_path / "m"
    md.mkdir()
    node_body = "the node body used for the dismissal fingerprint"
    (md / "main.tex").write_text(r"\input{N2}" + "\n", encoding="utf-8")
    (md / "N2.tex").write_text(node_body + "\n", encoding="utf-8")
    fb = md / "feedback.jsonl"
    # one routable finding on node N2
    L.append_jsonl(fb, {"id": "F1", "kind": "imprecise", "scope": "node",
                        "section": "N2", "node_id": "N2", "where": "N2.tex:5",
                        "anchor": {"section": "N2"}, "text": "vague", "round": 1})
    # a MACHINE DISMISSAL of exactly that (node, kind) with a matching fingerprint
    L.append_jsonl(fb, S.make_suppression("N2", "imprecise", node_body,
                                          reason="ruled not a fault", actor="machine",
                                          round=1, section="N2"))
    return md / "main.tex", fb, node_body


def test_open_findings_applies_the_suppress_first_filter_route_applies(tmp_path):
    main_tex, fb, node_body = _seed_dismissed_manuscript(tmp_path)

    # the harnessed brief/gate view now reuses the route's suppress-first + defer:
    open_hs = HS._open_findings(str(fb), str(main_tex), "-")

    # the REAL route view = the same base filter THEN suppress-first:
    from laplace.pipeline.ledger import read_jsonl, live_findings
    from laplace.pipeline import edits as E
    recs = live_findings(read_jsonl(str(fb)))
    superseded = {r.get("supersedes") for r in recs if r.get("supersedes")}
    non_finding = ADJ.ADJ_RECORD_KINDS | {S.RECORD_KIND, S.REVOKE_KIND, E.RECORD_KIND}
    base = [r for r in recs if r.get("record") not in non_finding
            and (r.get("status") or "open") != "resolved"
            and r.get("id") not in superseded
            and r.get("kind") in schema.KIND_TO_WORK]
    filt = S.filter_findings(base, S.load_suppressions(str(fb)), {"N2": node_body})

    # THE FIX: the harnessed view now AGREES with the route — the dismissed finding
    # is dropped by both. fixedpoint_route.py's own contract (L125-128): reading the
    # raw ledger without suppress-first "re-litigates a dismissed finding — the exact
    # spend suppress-first exists to prevent." The harnessed view is that same
    # router kept-set, so it never re-litigates.
    assert len(open_hs) == 0                      # harnessed view: dismissed finding DROPPED
    assert len(filt["kept"]) == 0                 # route view: dismissed finding dropped
    assert len(filt["suppressed"]) == 1
    assert open_hs == filt["kept"]                # by construction, the SAME kept-set


def test_dismissed_finding_absent_from_the_harnessed_brief_and_gate_count(tmp_path):
    # the same dismissal, now proven ABSENT from the two consumers the finding names:
    # the FIX BRIEF and the gate's open_findings_n (both built off _open_findings).
    main_tex, fb, _body = _seed_dismissed_manuscript(tmp_path)
    # a route that WANTS to rebuild N2 (dirty) — the brief would list N2's findings
    # under it, but the only N2 finding was dismissed, so no finding line appears.
    md, stats = HS._compile_brief(str(main_tex), "p", "", str(fb), str(tmp_path),
                                  1, "-", {"dirty_sections": ["N2"]}, [])
    assert stats["findings_n"] == 0               # gate/brief count: dismissed excluded
    assert "vague" not in md                       # the dismissed finding's text is absent
    # guard against over-filtering: a NON-dismissed finding (a different node, with no
    # suppression) still surfaces — the filter drops only what was actually dismissed.
    L.append_jsonl(fb, {"id": "F2", "kind": "imprecise", "scope": "node",
                        "section": "N3", "node_id": "N3", "where": "N3.tex:9",
                        "anchor": {"section": "N3"}, "text": "still-open phrase",
                        "round": 1})
    md2, stats2 = HS._compile_brief(str(main_tex), "p", "", str(fb), str(tmp_path),
                                    1, "-", {"dirty_sections": ["N3"]}, [])
    assert stats2["findings_n"] == 1 and "still-open phrase" in md2
