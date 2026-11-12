"""C4 — the figure-system gate (checklist cat 5, the mechanical part).

The mechanical apparatus of a figure, not its visual judgement (one-principal-
function and visual hierarchy are Phase D2 / E's rasteriser job). For every float
that draws a graphic:

* ``figure-unreferenced`` — the float carries a ``\\label`` but nothing ``\\ref``s
  it; the reader meets it with no prose hook,
* ``figure-misplaced``    — the float sits far (many sections) from its first
  textual mention,
* ``figure-oversized``    — the graphic's width does not match its column class:
  ``\\textwidth`` inside a single-column ``figure`` (overflows the column), or
  ``\\linewidth`` inside a spanning ``figure*`` (under-fills the page). Mirrors
  the layout flag in :func:`laplace.pipeline.verify.check_voice`.

Both ``\\includegraphics`` figures and bare ``tikzpicture`` figures are audited
for the reference/placement checks; the width check applies where a graphic
width is stated.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    finding, line_quote, section_spans, section_of, summarise, xref_positions,
)

_FLOAT_RE = re.compile(r"\\begin\{(figure|table)(\*?)\}(.*?)\\end\{\1\2\}", re.DOTALL)
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_GRAPHIC_RE = re.compile(r"\\includegraphics(\[[^\]]*\])?\{([^}]+)\}")
_TIKZ_RE = re.compile(r"\\begin\{tikzpicture\}")
_WIDTH_RE = re.compile(r"width\s*=\s*([\d.]*\\?[a-zA-Z]+)")


def check_figure_system(target: Union[str, Path]) -> dict[str, Any]:
    """Audit the mechanical figure apparatus of a compiled manuscript."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    spans = section_spans(full)
    refs = xref_positions(full)
    sec_order = {slug: i for i, (_s, _e, slug, _t, _a) in enumerate(spans)}

    findings: list[dict[str, Any]] = []
    n_figs = 0
    for m in _FLOAT_RE.finditer(full):
        env, star, body = m.group(1), m.group(2), m.group(3)
        if env == "table":
            continue                          # tables are C7's domain
        graphic = _GRAPHIC_RE.search(body)
        tikz = _TIKZ_RE.search(body)
        if not (graphic or tikz):
            continue
        n_figs += 1
        pos = m.start()
        fslug, _t, _a = section_of(pos, spans)
        lab_m = _LABEL_RE.search(body)
        label = lab_m.group(1) if lab_m else None
        where = f"{fslug or '?'}:{label or f'figure@{pos}'}"

        # --- referenced in text ---------------------------------------------
        ref_pos = refs.get(label, []) if label else []
        if not label:
            findings.append(finding(
                where, "figure float has no \\label, so no prose can \\ref it",
                "add a \\label and reference the figure at its first mention",
                "figure-unreferenced", quote=line_quote(full, pos)))
        elif not ref_pos:
            findings.append(finding(
                where, f"figure '{label}' is never \\ref'd in the body",
                "reference the figure at the point the prose first invokes it",
                "figure-unreferenced", quote=line_quote(full, pos)))
        else:
            # --- placed near first mention ----------------------------------
            first_ord = sec_order.get(section_of(min(ref_pos), spans)[0])
            fig_ord = sec_order.get(fslug)
            if first_ord is not None and fig_ord is not None and abs(fig_ord - first_ord) >= 2:
                findings.append(finding(
                    where,
                    f"figure sits {abs(fig_ord - first_ord)} sections from its first mention ({section_of(min(ref_pos), spans)[0]})",
                    "move the float toward its first mention, or add a nearer reference",
                    "figure-misplaced", quote=line_quote(full, min(ref_pos))))

        # --- sized to column ------------------------------------------------
        if graphic and graphic.group(1):
            wm = _WIDTH_RE.search(graphic.group(1))
            if wm:
                w = wm.group(1)
                spanning = star == "*"
                if not spanning and "textwidth" in w:
                    findings.append(finding(
                        where,
                        r"\includegraphics width=\textwidth in a single-column figure overflows the column",
                        r"use \columnwidth/\linewidth in a single-column figure, or promote it to figure*",
                        "figure-oversized", quote=graphic.group(0)))
                elif spanning and "linewidth" in w:
                    findings.append(finding(
                        where,
                        r"\includegraphics width=\linewidth in a spanning figure* under-fills the page width",
                        r"use \textwidth in a figure* to fill the two-column span",
                        "figure-oversized", quote=graphic.group(0)))

    return {
        "pass": not findings,
        "n_figures": n_figs,
        "findings": findings,
        "counts": summarise(findings),
    }
