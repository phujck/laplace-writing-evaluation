"""The PLANTED-FAILURE CALIBRATION FIXTURE — the falsifiability gate before the
expensive H round (Phase 3 of the convergence-checklist end-to-end pass).

A disposable fixture manuscript with ONE instance of each key MECHANICAL failure
class planted. For each class the test proves, against the COMMITTED surfaces
(called, never re-implemented), that the plant is (1) DETECTED, (2) the right
kind/class, (3) mapped to the right node/section, (4) routed to the right owning
stage, and (5) — where assertable without a model — ABSENT after the fix
(revert-the-plant for the detection classes; a dismissal + staleness for the
suppression class). A negative control pins what a CLEAN fixture yields: no
false positives on the mechanical axes, no routed work.

Surfaces exercised (all committed):
  * the every-round PANEL      .claude/workflows/fixedpoint_mechround.py
  * the efficient ROUTE fixer  .claude/workflows/fixedpoint_route.py
  * verify.check_meta_leak / check_epistemic / check_crossref
  * pipeline.scaffold_wipe (caption + prose passes)
  * pipeline.equation_lifecycle.check_equation_lifecycle
  * pipeline.tex_template.lint_typography
  * pipeline.visual_gate.parse_overfull_boxes
  * pipeline.suppress (make/append/load/filter, content fingerprint)
  * pipeline.drift.drift_report
  * pipeline.candidate_lock.round_status / lock_eligible
  * pipeline.release.finalize (untitled fail; pdftitle disagreement)
  * propagate.intake_items (owning_stage stamping)
  * pipeline.schema.META_LEAK_PATTERNS / KIND_TO_WORK

Compile-driving tests skip on the tool binary exactly as the neighbouring
tests/test_release.py and tests/test_drift.py do; the fixtures build in tmp_path
and never touch a canonical tree. pdflatex/latexmk are installed here.
"""
from __future__ import annotations

import shutil
import subprocess

import planted_fixture as pf
import pytest

from laplace.pipeline import verify
from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline import candidate_lock as cl
from laplace.pipeline import convergence as C
from laplace.pipeline import drift, propagate, schema
from laplace.pipeline import release as R
from laplace.pipeline import scaffold_wipe as SW
from laplace.pipeline import suppress as S
from laplace.pipeline.equation_lifecycle import check_equation_lifecycle
from laplace.pipeline.tex_template import lint_typography
from laplace.pipeline.visual_gate import parse_overfull_boxes

HAS_LATEXMK = shutil.which("latexmk") is not None
HAS_PDFLATEX = shutil.which("pdflatex") is not None

MECH_LABELS = ["meta_leak", "caption", "apparatus", "claims", "house_style", "visual"]


# ===========================================================================
# module-scoped compiled fixtures (compile ONCE, reuse across tests)
# ===========================================================================

@pytest.fixture(scope="module")
def dirty_build(tmp_path_factory):
    """The planted manuscript, compiled once. Skips (never fails) without latexmk."""
    if not HAS_LATEXMK:
        pytest.skip("latexmk not installed")
    md = tmp_path_factory.mktemp("dirty")
    main = pf.write_dirty(md)
    out = pf.compile_latexmk(md)
    if not out["log"].is_file():
        pytest.skip("latexmk produced no log for the dirty fixture")
    return {"dir": md, "main": str(main), **out}


@pytest.fixture(scope="module")
def clean_build(tmp_path_factory):
    """The plant-free control manuscript, compiled once."""
    if not HAS_LATEXMK:
        pytest.skip("latexmk not installed")
    md = tmp_path_factory.mktemp("clean")
    main = pf.write_clean(md)
    out = pf.compile_latexmk(md)
    if not out["log"].is_file():
        pytest.skip("latexmk produced no log for the clean fixture")
    return {"dir": md, "main": str(main), **out}


# --- a small in-process route helper (real fixedpoint_route.py, throwaway proj) --

def _route(tmp_path, monkeypatch, records, sections=("N1", "N2")):
    """Drive the real fixedpoint_route.py over ``records`` with a throwaway project
    whose plan has ``sections``. Returns the parsed ROUTE_JSON."""
    env = tmp_path / "route"
    env.mkdir()
    body = ("\\documentclass{article}\\begin{document}\n"
            + "".join(f"\\input{{{s}}}\n" for s in sections)
            + "\\end{document}\n")
    (env / "main.tex").write_text(body, encoding="utf-8")
    for s in sections:
        (env / f"{s}.tex").write_text(f"\\section{{{s}}}\nBody of {s}.\n", encoding="utf-8")
    plan = env / "plan.json"
    pf.write_plan(plan, list(sections))
    fb = pf.write_feedback(env / "feedback.jsonl", records)
    proj = pf.make_project(plan_path=plan)
    return pf.run_route(str(env / "main.tex"), str(fb), str(env), monkeypatch, proj)


# ===========================================================================
# CLASS 1 — overfull hbox past the 6pt floor → visual axis, scope=node, local-patch
# ===========================================================================

def test_class01_overfull_hbox_detected_past_floor(dirty_build):
    """Plant: a 128-char unbreakable token forcing an overfull \\hbox ≫ 6pt.
    Expected: parse_overfull_boxes reports an hbox past the 6pt floor, kind in the
    typography set (overfull-visual → render/document)."""
    over = [b for b in parse_overfull_boxes(dirty_build["log"]) if b["overflow_pt"] > 6.0]
    assert over, "no overfull box past the 6pt floor was detected"
    assert over[0]["box"] == "h" and over[0]["kind"] == "overfull-visual"
    # the mechanical floor the panel applies (visual_gate parity)
    assert over[0]["overflow_pt"] > 6.0
    # kind is in the typography/local-patch set (render → document), NOT a section regen
    assert schema.KIND_TO_WORK["overfull-visual"] == "render"
    assert schema.WORK_TO_LAYER["render"] == "document"


def test_class01_overfull_routes_to_local_patches_not_section_regen(tmp_path, monkeypatch):
    """Expected route: a scope=node overfull finding lands in ROUTE_JSON.local_patches
    and its section NEVER enters dirty_sections (a local in-place patch, never a
    builder regen)."""
    rec = pf.finding("overfull-visual", scope="node", section="N2", where="4--5")
    r = _route(tmp_path, monkeypatch, [rec])
    assert r["local_patches"], f"overfull did not route to local_patches: {r}"
    assert "N2" not in r["dirty_sections"]          # never a section regen
    assert r["figure_regens"] == []


# ===========================================================================
# CLASS 2 — undefined citation → lint undefined_citation (error), NOT a local patch
# ===========================================================================

def test_class02_undefined_citation_is_error_severity(dirty_build):
    """Plant: \\cite{ghost-key} with no matching entry.
    Expected: lint_typography flags category 'undefined_citation', severity 'error',
    token 'ghost-key' — a real apparatus/compile fault, unlike the overfull WARNING."""
    lt = lint_typography(dirty_build["log"].read_text(errors="replace"))
    cites = [f for f in lt["findings"] if f["category"] == "undefined_citation"]
    assert cites, "undefined citation not detected by lint_typography"
    assert cites[0]["severity"] == "error"
    assert cites[0].get("token") == "ghost-key"
    # the calibration contrast: overfull is a WARNING (a soft floor, node-scope local
    # patch); the undefined citation is an ERROR (a compile fault, section-scope).
    overfull = [f for f in lt["findings"] if f["category"] == "overfull_hbox"]
    assert overfull and overfull[0]["severity"] == "warning"


def test_class02_undefined_citation_blocks_candidate_lock(tmp_path, monkeypatch, dirty_build):
    """Routed section-scope, NOT a local patch: an undefined citation makes the
    compile UNclean, which blocks candidate-lock (candidate_lock owns the gate) —
    the mechanical statement of 'a real fault, not a tolerated local typography'.
    The whole dirty panel run confirms compile_ok is False and lock is denied."""
    clean, reasons = cl._compile_clean({"errors": 0, "undefined_cites": 1})
    assert clean is False and any("undefined_cites" in r for r in reasons)
    ok, why = cl.lock_eligible({"hard_failing": False},
                               {"errors": 0, "undefined_cites": 1}, round_complete=True)
    assert ok is False
    # end-to-end on the real panel: the compiled dirty fixture is not lock-eligible.
    proj = pf.make_project(target_dir=dirty_build["dir"])
    summary, doc = pf.run_mechround(
        dirty_build["main"], str(dirty_build["log"]), str(tmp_path / "r.json"),
        str(tmp_path / "fb.jsonl"), str(dirty_build["dir"]), monkeypatch, proj)
    assert summary["compile_ok"] is False and summary["lock_eligible"] is False
    # the undefined cite/ref surface in the visual axis but are NOT feedback kinds:
    # they land in flags_unrouted (compile lint, not a routed work item).
    unrouted = {u["kind"] for u in doc["flags_unrouted"]}
    assert {"undefined_citation", "undefined_reference"} <= unrouted


# ===========================================================================
# CLASS 3 — numbered-but-unused equation (semantic prefix) → eq-unused, right node
# ===========================================================================

def test_class03_unused_equation_detected_with_node_id(tmp_path):
    """Plant: \\begin{equation}\\label{res:orphan-eq} never \\ref/\\eqref'd.
    Expected: check_epistemic lists it as an orphan; equation_lifecycle emits the
    'eq-unused' kind against the right node id (res:orphan-eq)."""
    main = pf.write_dirty(tmp_path / "m")
    ep = verify.check_epistemic(_gather_manuscript_text(main))
    assert "res:orphan-eq" in ep["orphans"]
    el = check_equation_lifecycle(main)
    unused = [f for f in el["findings"] if f["kind"] == "eq-unused"]
    assert unused, "eq-unused not emitted by equation_lifecycle"
    assert any("res:orphan-eq" in f["where"] for f in unused)


def test_class03_eq_unused_routes_to_structural_section(tmp_path, monkeypatch):
    """Expected route: eq-unused is an epistemic/eq-lifecycle class owned by the
    STRUCTURAL stage, section-scope (dirty_sections), never a local patch."""
    items = propagate.intake_items(
        [pf.finding("eq-unused", section="N1", node_id="res:orphan-eq")],
        pf.write_plan(tmp_path / "plan.json", ["N1", "N2"]), {})
    assert items[0]["owning_stage"] == "structural"
    r = _route(tmp_path, monkeypatch,
               [pf.finding("eq-unused", section="N1", node_id="res:orphan-eq")])
    assert "N1" in r["dirty_sections"]
    assert r["local_patches"] == [] and r["figure_regens"] == []


# ===========================================================================
# CLASS 4 — stale cross-reference (\ref to a nonexistent label) → right section
# ===========================================================================

def test_class04_stale_xref_detected_in_right_section(tmp_path, dirty_build):
    """Plant: \\ref{sec:ghost-target} with no such label, in N2.
    Expected: check_crossref reports the broken ref attributed to N2; lint reports
    'undefined_reference' (error) on the compiled log."""
    main = pf.write_dirty(tmp_path / "m")
    cx = verify.check_crossref(main)
    assert any(b["ref"] == "sec:ghost-target" and "N2" in b["file"]
               for b in cx["broken_refs"]), cx["broken_refs"]
    lt = lint_typography(dirty_build["log"].read_text(errors="replace"))
    refs = [f for f in lt["findings"] if f["category"] == "undefined_reference"]
    assert refs and refs[0]["severity"] == "error"
    assert refs[0].get("token") == "sec:ghost-target"


def test_class04_stale_xref_routes_section_scope_structural(tmp_path, monkeypatch):
    """Expected route: the crossref class (crosslink-broken) is a real apparatus
    fault → STRUCTURAL, section-scope (dirty_sections), NOT a local patch."""
    assert schema.KIND_TO_WORK["crosslink-broken"] == "structure"
    r = _route(tmp_path, monkeypatch, [pf.finding("crosslink-broken", section="N2")])
    assert "N2" in r["dirty_sections"]
    assert r["local_patches"] == []


# ===========================================================================
# CLASS 5 — caption spec-debris (Q3 claim-support) → figure layer, sublayer=caption
# ===========================================================================

def test_class05_caption_spec_debris_detected(tmp_path):
    """Plant: a caption whose 2nd sentence is 'This figure supports the claim
    that…' (Q3 scaffold), after a legitimate what-shown sentence.
    Expected: scaffold_wipe's caption pass emits 'caption-scaffold' owned by the
    figures stage."""
    main = pf.write_dirty(tmp_path / "m")
    sw = SW.scaffold_wipe(main)
    caps = [f for f in sw["findings"] if f["kind"] == "caption-scaffold"]
    assert caps, "caption spec-debris not detected by scaffold_wipe"
    assert all(f["owning_stage"] == "figures" for f in caps)
    assert any("supports the claim" in f["quote"] for f in caps)


def test_class05_caption_routes_to_figure_caption_sublayer(tmp_path, monkeypatch):
    """Expected route: caption-scaffold routes to the FIGURE work-kind → it is
    DIVERTED into ROUTE_JSON.figure_regens with sublayer='caption' (the figure
    freeze scopes it), and its section never enters dirty_sections."""
    assert schema.KIND_TO_WORK["caption-scaffold"] == "figure"
    r = _route(tmp_path, monkeypatch,
               [pf.finding("caption-scaffold", section="N2", node_id="fig:gap")])
    assert r["figure_regens"], f"caption did not divert to the figure layer: {r}"
    assert r["figure_regens"][0]["sublayer"] == "caption"
    assert "N2" not in r["dirty_sections"]           # diverted, never a prose regen


# ===========================================================================
# CLASS 6 — evidence-ledger prose in the body → meta_leak HARD (stays hard)
# ===========================================================================

def test_class06_evidence_ledger_prose_is_meta_leak_hard(tmp_path, monkeypatch):
    """Plant: 'Every statement here is typed by evidence class…' in the body.
    Expected: check_meta_leak (the HARD gate) fails with the folded 'planning-object'
    class matching the evidence-ledger vocabulary; scaffold_wipe names it
    prose-scaffold → prose. His ruling: the evidence-ledger gate stays HARD."""
    md = tmp_path / "m"
    main = pf.write_dirty(md)
    proj = pf.make_project(target_dir=md)
    pf.install_resolve(monkeypatch, proj)
    res = verify.check_meta_leak(proj.name)
    assert res["pass"] is False
    hits_by_class = {}
    for h in res["hits"]:
        hits_by_class.setdefault(h["class"], []).append(h["match"])
    assert "planning-object" in hits_by_class
    assert any("evidence" in m for m in hits_by_class["planning-object"])
    # scaffold-wipe routes the same leak to the PROSE stage (owning-layer routing)
    ps = [f for f in SW.scaffold_wipe(main)["findings"] if f["kind"] == "prose-scaffold"]
    assert ps and all(f["owning_stage"] == "prose" for f in ps)
    assert schema.KIND_TO_WORK["prose-scaffold"] == "prose"


# ===========================================================================
# CLASS 7 — raw node-id in prose → the 'node-id' META_LEAK_PATTERNS class
# ===========================================================================

def test_class07_raw_node_id_in_prose_is_node_id_meta_leak(tmp_path, monkeypatch):
    """Plant: 'The bound def:main-bound then governs…' — a raw node-id in a
    sentence, outside \\label/\\ref.
    Expected: check_meta_leak flags class 'node-id' matching def:main-bound.
    (Coordination guard: skip-with-reason if the 'node-id' class has not landed in
    schema.META_LEAK_PATTERNS. It IS present in this tree.)"""
    if "node-id" not in schema.META_LEAK_PATTERNS:
        pytest.skip("the 'node-id' META_LEAK_PATTERNS class has not landed yet; "
                    "this test is written against class name 'node-id'")
    md = tmp_path / "m"
    pf.write_dirty(md)
    proj = pf.make_project(target_dir=md)
    pf.install_resolve(monkeypatch, proj)
    res = verify.check_meta_leak(proj.name)
    node_hits = [h for h in res["hits"] if h["class"] == "node-id"]
    assert node_hits, f"'node-id' class did not fire; hits={res['hits']}"
    assert any("def:main-bound" in h["match"] for h in node_hits)


# ===========================================================================
# CLASS 8 — wrong / missing title → finalize raises loud; pdftitle disagreement
# ===========================================================================

def test_class08a_untitled_manuscript_finalize_raises_loud(tmp_path):
    """Plant: a manuscript with NO title macro.
    Expected: release.finalize raises a loud ValueError (front-matter route) BEFORE
    spending a compile."""
    md = tmp_path / "u"
    md.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\nNo title here at all.\n"
        "\\end{document}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="front-matter"):
        R.finalize(md)


@pytest.mark.skipif(not HAS_LATEXMK, reason="latexmk not installed")
def test_class08b_pdftitle_disagreement_is_reported(tmp_path):
    """Plant: a titled manuscript whose hyperref pdftitle DISAGREES with \\title.
    Expected: finalize's title_check reports title_agrees True, pdftitle_agrees
    False — reported, never edited (the source stays untouched)."""
    md = tmp_path / "t"
    md.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\n\\usepackage{hyperref}\n"
        "\\hypersetup{pdftitle={A Different pdftitle}}\n"
        "\\title{The Planted Manuscript}\n\\author{T. Ester}\n"
        "\\begin{document}\\maketitle\n\\section{Intro}\\label{sec:intro}\n"
        "A sentence of body text.\n\\end{document}\n", encoding="utf-8")
    res = R.finalize(md)
    assert res["title_check"]["title_agrees"] is True
    assert res["title_check"]["pdftitle_agrees"] is False
    assert "A Different pdftitle" in (md / "main.tex").read_text()   # untouched


# ===========================================================================
# CLASS 9 — suppression staleness: dismissed → dropped → mutate → STALE (reborn)
# ===========================================================================

def test_class09_suppression_goes_stale_on_content_change(tmp_path):
    """Plant a fault, DISMISS it (a fingerprinted suppression on the node), confirm
    filter_findings drops it before the fixer spends a token; then MUTATE the node's
    text and confirm the suppression goes STALE — the finding is judgeable again,
    never silently suppressed. Suppression can never hide a reborn fault."""
    node, kind = "res:main", "meta-leak"
    original = "This equation is a terminal result; leave it."
    rec = S.make_suppression(node, kind, original, reason="terminal result",
                             actor="g", round=1, rec_id="SUP-1")
    fb = tmp_path / "feedback.jsonl"
    S.append_suppression(fb, rec)
    supps = S.load_suppressions(fb)
    fnd = pf.finding(kind, node_id=node)
    # (1) DETECTED then DISMISSED → dropped before routing.
    out = S.filter_findings([fnd], supps, {node: original})
    assert out["suppressed"] == [fnd] and out["kept"] == [] and out["stale"] == []
    # (2) the node's text is MUTATED → the fingerprint no longer matches → STALE,
    #     and the finding is returned as judgeable again (kept), not suppressed.
    mutated = original + " Now it also carries a leaked contract note."
    out2 = S.filter_findings([fnd], supps, {node: mutated})
    assert out2["suppressed"] == []
    assert out2["kept"] == [fnd]
    assert [r["id"] for r in out2["stale"]] == ["SUP-1"]


# ===========================================================================
# CLASS 10 — cross-section dependency dispatch (THE OPEN QUESTION, documented)
# ===========================================================================

def test_class10_cross_section_dependency_boundary(tmp_path, monkeypatch):
    """Plant: a section-scope SUBSTANCE finding on section A (N1); section B (N2)
    relies on A. Question: does B reach dirty_sections?

    ACTUAL BEHAVIOUR (asserted, not fixed): NO. fixedpoint_route classifies the
    dirty-set from the INTAKE ITEMS (propagate.intake_items), not from the
    worklist's dependency-synthesis — BY DESIGN (route lines 163-174): the
    worklist's synthesised prose re-runs are section-scope and would mis-promote a
    render-only cheap section into a builder regen. So A regenerates and B does not,
    even though B relies on A.

    DOCUMENTED VERDICT / trade-off: a dependent section B is NOT auto-regenerated by
    the route. To re-run B the reviewer files a finding on B, or — in a populated
    substrate — the worklist's depth-1 ancestry rule fires with B's own prose item.
    The route deliberately does not propagate a worklist-synthesised re-run into the
    dirty-set. This test pins the boundary; it does NOT force a fix."""
    r = _route(tmp_path, monkeypatch, [pf.finding("missing-content", section="N1")])
    assert "N1" in r["dirty_sections"]           # A carries section work → regenerates
    assert "N2" not in r["dirty_sections"]        # B is NOT auto-promoted (the boundary)
    # the worklist DID run (it synthesises A's own prose re-run), proving the route
    # computed the DAG yet still classified dirty_sections from intake, not synthesis.
    assert r["worklist_n"] >= 1


# ===========================================================================
# CLASS 11 — drift: a page-reflowing edit vs an identical compile
# ===========================================================================

def _compile_doc(texdir, name, body):
    tex = texdir / f"{name}.tex"
    tex.write_text(body, encoding="utf-8")
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", str(tex)],
        cwd=str(texdir), capture_output=True, timeout=120)
    return texdir / f"{name}.pdf"


@pytest.fixture(scope="module")
def drift_pdfs(tmp_path_factory):
    """Two single-page PDFs — a base and a content-reflowed variant — built once;
    skip (never fail) without pdflatex or the isolated rasteriser (matches
    tests/test_drift.py)."""
    if not HAS_PDFLATEX:
        pytest.skip("pdflatex not installed")
    d = tmp_path_factory.mktemp("drift_pdfs")
    base = _compile_doc(d, "base",
                        r"\documentclass{article}\begin{document}"
                        r"Page one alpha content here.\end{document}")
    mod = _compile_doc(d, "mod",
                       r"\documentclass{article}\begin{document}"
                       r"Page one COMPLETELY DIFFERENT content now.\end{document}")
    for p in (base, mod):
        if not p.is_file():
            pytest.skip("pdflatex failed to build a drift fixture PDF")
    try:
        from laplace.pipeline.visual_gate import rasterise_pdf
        rasterise_pdf(str(base), str(d / "_probe"))
    except RuntimeError as exc:
        pytest.skip(f"isolated rasteriser unavailable: {exc}")
    return {"base": str(base), "mod": str(mod)}


def test_class11_drift_identical_clean_reflow_flagged(drift_pdfs, tmp_path):
    """Expected: identical compiles → no page changed, not unexpected; a reflowing
    edit → pages_changed non-empty; and under a tightened dial the same reflow reads
    as unexpected (drift is calibratable, not a buried constant)."""
    same = drift.drift_report(drift_pdfs["base"], drift_pdfs["base"], out_dir=tmp_path / "a")
    assert same["pages_changed"] == [] and same["unexpected"] is False
    changed = drift.drift_report(drift_pdfs["base"], drift_pdfs["mod"], out_dir=tmp_path / "b")
    assert changed["pages_changed"] == [1] and changed["changed_count"] == 1
    tight = drift.drift_report(
        drift_pdfs["base"], drift_pdfs["mod"], out_dir=tmp_path / "c",
        dials={"drift": {"page_change_warn": 0, "page_count_change": "loud"}})
    assert tight["unexpected"] is True and "exceeds page_change_warn 0" in tight["notes"]


# ===========================================================================
# CLASS 12 — round-incomplete: a missing panel label → not lock-eligible
# ===========================================================================

def test_class12_round_incomplete_blocks_lock_even_when_hard_passes(tmp_path):
    """Plant: a panel missing one expected mechanical label (house_style, a SOFT
    dim — so the hard dims still pass).
    Expected: candidate_lock.round_status reports the round INCOMPLETE, and
    lock_eligible is False even though the hard dims pass and the compile is clean —
    a missing verdict is never a pass (silence → not-lock)."""
    panel = [{"label": lab, "clean": True, "flags": []}
             for lab in ["meta_leak", "caption", "apparatus", "claims", "visual"]]
    st = cl.round_status(panel, expected=MECH_LABELS)
    assert st["complete"] is False and "house_style" in st["missing"]
    # hard dims pass on the present clean labels, yet the incomplete round cannot lock
    round_eval = C.evaluate_round(panel)
    assert cl._hard_pass(round_eval) is True
    ok, reasons = cl.lock_eligible(round_eval, {"errors": 0, "undefined": 0},
                                   round_complete=st["complete"])
    assert ok is False and any("round incomplete" in r for r in reasons)


# ===========================================================================
# THE PANEL, end to end — the real every-round mechanical panel on both fixtures
# ===========================================================================

@pytest.mark.skipif(not HAS_LATEXMK, reason="latexmk not installed")
def test_panel_dirty_fixture_flags_every_planted_axis(dirty_build, tmp_path, monkeypatch):
    """The real fixedpoint_mechround.py panel over the compiled planted fixture:
    meta_leak / caption / visual all read UNCLEAN, the round is COMPLETE (every
    label present) but NOT lock-eligible (hard dims fail + unclean compile), and the
    typed findings pour through the one feedback door."""
    proj = pf.make_project(target_dir=dirty_build["dir"])
    summary, doc = pf.run_mechround(
        dirty_build["main"], str(dirty_build["log"]), str(tmp_path / "round.json"),
        str(tmp_path / "fb.jsonl"), str(dirty_build["dir"]), monkeypatch, proj)
    labels = summary["labels"]
    assert labels["meta_leak"] is False           # evidence-ledger + node-id (classes 6,7)
    assert labels["caption"] is False             # Q3 spec-debris (class 5)
    assert labels["visual"] is False              # overfull + undefined ref/cite (1,2,4)
    assert summary["complete"] is True            # every expected label present
    assert summary["lock_eligible"] is False
    assert summary["hard_failing"] is True and summary["compile_ok"] is False
    assert summary["flags_routed"] >= 1
    # the visual axis carries the overfull past the floor AND the undefined ref/cite
    vis = next(p for p in doc["panel"] if p["label"] == "visual")
    vkinds = {f.get("kind") for f in vis["flags"]}
    assert "overfull-visual" in vkinds
    assert {"undefined_citation", "undefined_reference"} <= vkinds
    # the meta_leak axis carries the evidence-ledger scaffold and the raw node-id
    ml = next(p for p in doc["panel"] if p["label"] == "meta_leak")
    blob = " ".join((f.get("quote", "") + " " + f.get("issue", "")) for f in ml["flags"])
    assert ml["flags"] and ("evidence" in blob.lower() or "def:main-bound" in blob)


@pytest.mark.skipif(not HAS_LATEXMK, reason="latexmk not installed")
def test_negative_control_panel_is_clean_and_pins_every_axis(clean_build, tmp_path, monkeypatch):
    """THE CALIBRATION CONTROL — the plant-free fixture. The panel is CLEAN on the
    mechanical axes (meta_leak / caption / visual) with zero false positives; on
    this tiny fixture apparatus / claims / house_style are ALSO clean, no gate
    crashed (no FAILED label), the round is complete and lock-eligible, and nothing
    routed. The false-positive rate on the clean fixture is zero — pinned."""
    proj = pf.make_project(target_dir=clean_build["dir"])
    summary, doc = pf.run_mechround(
        clean_build["main"], str(clean_build["log"]), str(tmp_path / "round.json"),
        str(tmp_path / "fb.jsonl"), str(clean_build["dir"]), monkeypatch, proj)
    labels = summary["labels"]
    assert labels["meta_leak"] is True            # no evidence-ledger / node-id
    assert labels["caption"] is True              # no caption spec-debris
    assert labels["visual"] is True               # no overfull / undefined ref/cite
    # pinned tiny-fixture yield: all axes clean, nothing FAILED, complete, nothing routed
    assert labels["apparatus"] is True and labels["claims"] is True
    assert labels["house_style"] is True
    assert "FAILED" not in list(labels.values())
    assert summary["complete"] is True
    assert summary["flags_routed"] == 0
    assert doc["gate_errors"] == {}


def test_negative_control_route_yields_no_work(tmp_path, monkeypatch):
    """The clean control through the ROUTE fixer: no findings → no local_patches, no
    figure_regens, no dirty_sections, nothing blocked. No false-positive routing."""
    r = _route(tmp_path, monkeypatch, [])
    assert r["local_patches"] == []
    assert r["figure_regens"] == []
    assert r["dirty_sections"] == []
    assert r["figure_blocked"] == []
