"""R3 Apparatus — the mechanical apparatus spine, read as a reader (checklist cat 3/4/7/9).

The one reader that reads STRUCTURE, not the intention: it aggregates the Phase-C
mechanical gates into a single apparatus-reader verdict under the reader framing —
*every pointer resolves, every symbol carries one meaning, every numbered equation
is reused, no content repeats across surfaces*. It owns four of the thirteen
hard-failures:

    equation-not-reused   (#6)  ← equation_lifecycle
    claim-cite-unwired    (#8)  ← citation_audit   (the "is a cite WIRED at all" half;
                                   the "is the evidence SUFFICIENT" half is R2 Referee)
    notation-collision    (#9)  ← notation_audit + equation_lifecycle (duplicate LHS)
    cross-surface-repeat  (#10) ← equation_lifecycle (duplicate body) + crosslink_audit

Pure mechanical: it REUSES the Phase-C modules by import and runs every fixer round
(no model, no candidate-lock gate). It introduces no new finding-kind — it rides the
Phase-C kinds already routed in ``apparatus_common.FINDING_KIND_STAGE`` (which Phase F
wires via C's manifest). This module only re-frames and attributes them to R3, and
maps each finding onto the owned hard-failure it evidences.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.authored_closure import check_authored_closure
from laplace.pipeline.citation_audit import check_citation_audit
from laplace.pipeline.crosslink_audit import check_crosslink_audit
from laplace.pipeline.equation_lifecycle import check_equation_lifecycle
from laplace.pipeline.notation_audit import check_notation_consistency
from laplace.pipeline.readers.roster import READERS

# Each Phase-C finding-kind → the R3-owned hard-failure it evidences. Kinds not in
# an owned family (e.g. crosslink-vague, citation-cluster) are apparatus HYGIENE
# the reader still surfaces, mapped to ``None`` (no owned-failure claim).
_KIND_TO_OWNED: dict[str, Optional[str]] = {
    # #6 equation-not-reused
    "eq-unused": "equation-not-reused",
    "eq-uninterpreted": "equation-not-reused",
    "eq-ref-before-intro": "equation-not-reused",
    # #8 claim-cite-unwired
    "citation-uncited": "claim-cite-unwired",
    "citation-naked-reliance": "claim-cite-unwired",
    # #9 notation-collision
    "notation-inconsistent": "notation-collision",
    # #10 cross-surface-repeat
    "eq-duplicate": "cross-surface-repeat",
    # apparatus hygiene the reader surfaces but does not headline
    "citation-cluster": None,
    "citation-first-use": None,
    "crosslink-broken": None,
    "crosslink-vague": None,
    "crosslink-far": None,
    "unlinked-reliance": "cross-surface-repeat",
    "closure-roadmap-section": None,
    "closure-roadmap-empty": None,
    "closure-roadmap-missing": None,
    "closure-roadmap-order": None,
    "closure-roadmap-position": None,
    "closure-dependency-unlinked": "cross-surface-repeat",
    "closure-object-definition": "cross-surface-repeat",
    "closure-object-orphan": "equation-not-reused",
    "orthography-fork": None,          # F33 report-only fork
}


def read_apparatus(target: Union[str, Path],
                   corpus_path: Optional[Union[str, Path]] = None,
                   project: Optional[str] = None) -> dict[str, Any]:
    """Run the four Phase-C apparatus gates and aggregate them into the R3 verdict.

    Returns the reader shape:
      * ``reader`` / ``clean`` / ``failed`` — the panel entry fields (``clean`` is
        the reader's pass; ``failed`` marks an aggregation error so the loop scores
        it 0.5, never a free pass),
      * ``findings`` — every Phase-C finding, stamped ``reader='R3'`` and carrying
        the ``owned_failure`` it evidences (or ``None`` for hygiene),
      * ``by_module`` — per-gate pass/counts, so a caller can see which spine leg
        fired,
      * ``owned_failures`` — {hard-failure id → count} across the four R3 owns,
      * ``counts`` — findings by kind.

    ``corpus_path``/``project`` drive citation_audit's backward sweep; without them
    only its forward sweep runs (reported as ``manual`` there)."""
    target = Path(target)
    modules = {
        "equation_lifecycle": lambda: check_equation_lifecycle(target),
        "citation_audit": lambda: check_citation_audit(target, corpus_path, project),
        "crosslink_audit": lambda: check_crosslink_audit(target),
        "notation_audit": lambda: check_notation_consistency(target),
    }
    tex_root = target.parent if target.suffix == ".tex" else target
    closure_contract = tex_root / "closure_contract.json"
    if closure_contract.is_file():
        modules["authored_closure"] = lambda: check_authored_closure(
            target, closure_contract)

    findings: list[dict[str, Any]] = []
    by_module: dict[str, Any] = {}
    failed = False
    for name, run in modules.items():
        try:
            res = run()
        except Exception as e:  # noqa: BLE001 — an apparatus gate crash is a loud
            failed = True       # signal (silence never reads as pass), not swallowed
            by_module[name] = {"error": str(e)}
            continue
        by_module[name] = {"pass": res.get("pass"), "counts": res.get("counts", {})}
        for f in res.get("findings", []):
            kind = f.get("kind", "")
            findings.append({**f, "reader": "R3",
                             "owning_stage": f.get("route", "prose"),
                             "dimension": READERS["R3"].dimension,
                             "owned_failure": _KIND_TO_OWNED.get(kind)})

    owned: dict[str, int] = {hid: 0 for hid in READERS["R3"].owns}
    for f in findings:
        of = f.get("owned_failure")
        if of in owned:
            owned[of] += 1

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1

    # apparatus HYGIENE (crosslink-vague, clusters, …) is surfaced but does not, on
    # its own, fail the reader's OWNED question; the reader is "unclean" whenever it
    # emits any finding, but the panel/loop can weight owned vs hygiene via the
    # per-finding `owned_failure`. Keep `clean` strict (any finding = unclean) so
    # the reader never under-reports.
    return {
        "reader": "R3",
        "clean": (not failed) and (not findings),
        "failed": failed,
        "findings": findings,
        "by_module": by_module,
        "owned_failures": owned,
        "counts": counts,
        "dimension": READERS["R3"].dimension,
        "panel_label": READERS["R3"].panel_label,
    }


# ---------------------------------------------------------------------------
# The layout + tic EVIDENCE axis — the banked seam (his hold-out review, 2026-07-10:
# additional harnessing in the figure loop + the annoying tics, mechanically caught).
# ---------------------------------------------------------------------------
#
# The mechanical panel reads STRUCTURE (R3, above) as a HARD axis. The figure-layout
# gates (G1/G2/G3, :mod:`layout_gates`) and the recurring-tic detectors
# (:mod:`tics`) ride the SAME panel as an ADVISORY (evidence-grade) axis: each
# harnessed detect/redetect emits their findings into the round evidence so the loop
# SEES the layout debt and the authorial tics, but they are NOT revert triggers — the
# harnessed redetect defect-axes gate reads widening / hard-fail / broken-compile
# only, deliberately (the figures/prose are inherited debt until re-authored). G1's
# HARD teeth are at RELEASE (``release.layout_gate_results``), not the round panel; at
# the round cadence the cheap SOURCE+aux surfaces (G2 float placement, G3 panel
# agreement) and the text-level tics run every round, and the render-dependent G1 is
# opt-in (``size_gate``) so the round stays cheap.

_EVIDENCE_LAYOUT_KINDS = frozenset({
    # G2 semantic float
    "float-backlog", "float-orphan", "float-past-boundary",
    # G3 figure contract registry
    "figure-panel-uncovered", "figure-panel-body-mismatch", "figure-contract-orphan",
    # G1 final-size visual (only when size_gate is enabled at the panel)
    "layout-text-undersize", "layout-type3-font", "layout-clipped-glyph",
    "layout-text-unextractable", "layout-text-font-unmapped",
})


def read_layout_evidence(target: Union[str, Path], *,
                         pdf_path: Optional[Union[str, Path]] = None,
                         aux_path: Optional[Union[str, Path]] = None,
                         size_gate: bool = False,
                         resolve_asset_panels: bool = False,
                         disclaimer_threshold: int = 3,
                         caption_min_facets: int = 4) -> dict[str, Any]:
    """The layout + tic EVIDENCE axis for the mechanical panel — advisory, never a
    hard blocker at the round cadence. Runs the cheap SOURCE+aux figure-layout gates
    (G2 semantic float via section estimate, G3 figure-contract panel agreement from
    source) and the three text-level tic detectors (defensive-caption,
    disclaimer-repetition, sentence-density) over one manuscript, and — only when
    ``size_gate`` is set and a compiled PDF is available — the render-dependent G1
    final-size gate. Every finding is stamped ``grade='evidence'`` and
    ``owned_failure=None`` (it feeds no hard dim); G1's HARD enforcement stays at
    release. A gate/detector that RAISES is recorded as ``{error: ...}``, never a
    false clean. Returns ``{reader, clean, failed, findings, counts, layout, tics,
    grade, advisory}``."""
    from laplace.pipeline import layout_gates as LG
    from laplace.pipeline import tics as T

    target = Path(target)
    tex_root = target.parent if target.suffix == ".tex" else target
    if aux_path is None:
        cand = tex_root / "main.aux"
        aux_path = cand if cand.is_file() else None

    layout: dict[str, Any] = {}
    failed = False

    def _safe_gate(name: str, run):
        nonlocal failed
        try:
            layout[name] = run()
        except Exception as e:  # noqa: BLE001 — a gate crash is a loud advisory, not silence
            failed = True
            layout[name] = {"pass": False, "clean": False, "error": str(e),
                            "findings": [], "counts": {}}

    if size_gate and pdf_path is not None and Path(pdf_path).is_file():
        _safe_gate("size", lambda: LG.check_final_size_visual(
            pdf_path, aux_path=aux_path))
    # G2 float placement — section-estimate (pdf_path=None => no per-figure synctex
    # spawn, cheap enough for every round); G3 panel agreement from source only.
    _safe_gate("float", lambda: LG.check_semantic_float(
        tex_root, aux_path=aux_path, pdf_path=None))
    _safe_gate("contract", lambda: LG.check_figure_contract(
        tex_root, aux_path=aux_path, pdf_path=None,
        resolve_asset_panels=resolve_asset_panels))

    tics: dict[str, Any] = {}
    try:
        tics = T.run_tic_detectors(
            target, disclaimer_threshold=disclaimer_threshold,
            caption_min_facets=caption_min_facets)
    except Exception as e:  # noqa: BLE001
        failed = True
        tics = {"pass": False, "clean": False, "error": str(e),
                "findings": [], "counts": {}}

    findings: list[dict[str, Any]] = []
    for g in layout.values():
        for f in g.get("findings", []):
            findings.append({**f, "reader": "R3", "axis": "layout",
                             "grade": "evidence", "owned_failure": None})
    for f in tics.get("findings", []):
        findings.append({**f, "reader": "R3", "axis": "tic",
                         "grade": "evidence", "owned_failure": None})

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1

    return {
        "reader": "R3",
        "panel_label": "layout_evidence",
        # advisory axis: `clean` reports whether any evidence finding fired, but it
        # feeds NO hard dim — the round panel never blocks on it (inherited debt).
        "clean": (not failed) and (not findings),
        "failed": failed,
        "grade": "evidence",
        "advisory": True,
        "findings": findings,
        "counts": counts,
        "layout": layout,
        "tics": tics,
        "size_gate_ran": bool(size_gate and pdf_path is not None
                              and Path(pdf_path).is_file()),
    }
