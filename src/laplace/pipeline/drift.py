"""The PDF drift report — local fix vs global artefact (Phase F hardening).

The plain conjugate of "minimum dirty set": a small semantic dirty-set does NOT
guarantee a small change to the rendered object. A one-word fix can reflow a
column, push a float onto the next page, and shift every page after it. This
module rasterises the incumbent and the candidate PDFs and reports what actually
moved on the page, so an expected-local fix that caused an unexpected-distant
reflow is made visible before the candidate is accepted.

The rasteriser is REUSED, not reinvented: ``visual_gate.rasterise_pdf`` already
proves the isolated ``uv run --with pypdfium2 --with pillow`` pattern (``pdftoppm``
/ ``gs`` / ``fitz`` are absent on this box). The parent process — which has Pillow
— does the per-page pixel diff in-process.

A page-count change is ALWAYS loud (``dials.drift.page_count_change``); more than
``dials.drift.page_change_warn`` changed pages is ``unexpected``.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional

from laplace.pipeline import dials as _dials_mod
from laplace.pipeline.visual_gate import DEFAULT_DPI, DEFAULT_UV, rasterise_pdf

#: per-pixel intensity delta (0-255 on the greyscale diff) below which two pixels
#: are "the same" — absorbs anti-aliasing jitter from the rasteriser.
_PIXEL_TOL = 16
#: fraction of a page's pixels that must differ (beyond ``_PIXEL_TOL``) before the
#: page counts as CHANGED — absorbs a handful of stray pixels, catches real reflow.
_AREA_TOL = 0.001


def _page_changed(png_a: str, png_b: str, pixel_tol: int = _PIXEL_TOL,
                  area_tol: float = _AREA_TOL) -> bool:
    """Whether two rendered pages differ materially. Different dimensions -> changed
    (a geometry change is a change). Otherwise: fraction of pixels whose greyscale
    delta exceeds ``pixel_tol`` must exceed ``area_tol``."""
    from PIL import Image, ImageChops
    with Image.open(png_a) as ia, Image.open(png_b) as ib:
        a = ia.convert("L")
        b = ib.convert("L")
        if a.size != b.size:
            return True
        diff = ImageChops.difference(a, b)
        hist = diff.histogram()                 # 256 buckets, count per intensity
        total = a.size[0] * a.size[1]
        if total == 0:
            return False
        changed = sum(hist[pixel_tol + 1:])     # pixels with delta > pixel_tol
        return (changed / total) > area_tol


def drift_report(incumbent_pdf: str | Path, candidate_pdf: str | Path, *,
                 out_dir: str | Path | None = None,
                 dirty_sections: Optional[list[str]] = None,
                 dials: dict[str, Any] | None = None,
                 dpi: float = DEFAULT_DPI, uv_bin: str = DEFAULT_UV) -> dict:
    """Rasterise both PDFs and report what moved on the page.

    Returns ``{page_count: {incumbent, candidate}, pages_changed: [ints],
    changed_count, unexpected: bool, notes: str}`` (1-based page numbers).

    ``unexpected`` is true when the page count changed (always loud) OR when
    ``changed_count`` exceeds ``dials.drift.page_change_warn``. A page present in
    one PDF but not the other counts as changed.

    ``dirty_sections`` is accepted for the G-phase refinement (classify each
    changed page as expected — it overlaps a dirty section — or unexpected). v1
    uses a simple COUNT heuristic only (``changed_count`` vs the warn threshold);
    the per-page classification against ``dirty_sections`` is a documented seam,
    not yet wired. When provided it is echoed into ``notes`` for the reviewer.

    Rasterisation is the only external hop; it raises ``RuntimeError`` if the
    isolated rasteriser is unavailable (a broken rasteriser is a loud signal,
    never a silently-empty drift report).
    """
    d = dials if dials is not None else _dials_mod.load_dials()
    drift_dials = d.get("drift") or {}
    warn = int(drift_dials.get("page_change_warn", 3))

    if out_dir is None:
        out_dir = Path(tempfile.mkdtemp(prefix="drift_"))
    out_dir = Path(out_dir)
    inc_renders = rasterise_pdf(incumbent_pdf, out_dir / "incumbent",
                                dpi=dpi, uv_bin=uv_bin)
    cand_renders = rasterise_pdf(candidate_pdf, out_dir / "candidate",
                                 dpi=dpi, uv_bin=uv_bin)

    inc_by = {r.index: r for r in inc_renders}
    cand_by = {r.index: r for r in cand_renders}
    n_inc, n_cand = len(inc_renders), len(cand_renders)
    count_changed = n_inc != n_cand

    pages_changed: list[int] = []
    for idx in sorted(set(inc_by) | set(cand_by)):
        if idx not in inc_by or idx not in cand_by:
            pages_changed.append(idx)           # added or removed page
        elif _page_changed(inc_by[idx].path, cand_by[idx].path):
            pages_changed.append(idx)
    changed_count = len(pages_changed)

    unexpected = bool(count_changed) or changed_count > warn

    parts: list[str] = []
    if count_changed:
        parts.append(
            f"PAGE COUNT CHANGED {n_inc} -> {n_cand} (loud): the artefact grew/"
            "shrank — a local fix caused a global reflow")
    if changed_count:
        parts.append(f"{changed_count} page(s) changed: {pages_changed}")
    else:
        parts.append("no rendered page changed")
    if changed_count > warn:
        parts.append(f"changed_count {changed_count} exceeds page_change_warn {warn}")
    if dirty_sections is not None:
        parts.append(
            f"dirty_sections={list(dirty_sections)} (v1 count-heuristic only; "
            "per-page dirty-vs-distant classification is a G-phase seam)")
    notes = "; ".join(parts)

    return {
        "page_count": {"incumbent": n_inc, "candidate": n_cand},
        "pages_changed": pages_changed,
        "changed_count": changed_count,
        "unexpected": unexpected,
        "notes": notes,
    }
