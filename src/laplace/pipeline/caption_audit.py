"""C5 — the caption-completeness gate (checklist cat 6, mechanical).

Every float carries a caption that stands on its own: it is present, it names the
object it depicts, and it reads as a self-contained statement rather than a bare
title. The mechanical checks:

* ``caption-missing``    — a float (figure/table) with no ``\\caption``,
* ``caption-incomplete`` — a caption that does not name its object (carries no
  math symbol / defined quantity), or is a bare title fragment (too short, no
  sentence), or names no panel where the figure has panels.

This is the *completeness* floor, disjoint from two neighbours by design: the
"is the float referenced from the body" check belongs to C4 (figures) / C3
(crosslink); the *scaffold-wipe* of a caption — stripping the four generating
questions and evidence-taxonomy language — is Phase B's erasure pass. C5 only
asks whether what remains is a complete caption.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    finding, section_spans, section_of, summarise,
)

_FLOAT_RE = re.compile(r"\\begin\{(figure|table)(\*?)\}(.*?)\\end\{\1\2\}", re.DOTALL)
_CAPTION_CMD = re.compile(r"\\caption(?:\[[^\]]*\])?\{")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")


def _extract_caption(body: str) -> str | None:
    """The balanced-brace content of the first ``\\caption{...}`` in a float.
    A physics caption nests math braces several levels deep (``\\hat{Z}_{\\tau,m}``),
    so a fixed-depth regex miscounts it as missing — walk the braces instead."""
    m = _CAPTION_CMD.search(body)
    if not m:
        return None
    i = m.end()
    depth = 1
    while i < len(body) and depth:
        c = body[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    return body[m.end():i - 1].strip()
_MATH_RE = re.compile(r"\$[^$]+\$|\\[A-Za-z]+")
_PANEL_RE = re.compile(r"\b(panel|left|right|top|bottom|inset|\([a-e]\))\b", re.I)
_SUBFIG_RE = re.compile(r"\\subfloat|\\subfigure|\\begin\{subfigure\}|\\subcaptionbox")

_MIN_CAPTION_CHARS = 40


def check_caption_completeness(target: Union[str, Path]) -> dict[str, Any]:
    """Audit caption completeness on a compiled manuscript."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    spans = section_spans(full)

    findings: list[dict[str, Any]] = []
    n_floats = 0
    for m in _FLOAT_RE.finditer(full):
        env, star, body = m.group(1), m.group(2), m.group(3)
        n_floats += 1
        pos = m.start()
        fslug, _t, _a = section_of(pos, spans)
        lab_m = _LABEL_RE.search(body)
        label = lab_m.group(1) if lab_m else f"{env}@{pos}"
        where = f"{fslug or '?'}:{label}"

        caption = _extract_caption(body)
        if caption is None:
            findings.append(finding(
                where, f"{env} float has no \\caption",
                "add a caption that names the object and states the one thing to read",
                "caption-missing"))
            continue
        cap_text = re.sub(r"\s+", " ", caption)

        # too short / bare-title fragment
        if len(cap_text) < _MIN_CAPTION_CHARS:
            findings.append(finding(
                where, f"{env} caption is a bare fragment ({len(cap_text)} chars) — not self-contained",
                "expand to a self-contained caption naming the object and the one observation",
                "caption-incomplete", quote=cap_text))
            continue
        # names its object: a self-contained figure/table caption carries the
        # symbol or quantity it depicts.
        if not _MATH_RE.search(caption):
            findings.append(finding(
                where, f"{env} caption names no symbol or quantity — the reader cannot tell what is plotted",
                "name the plotted/tabulated object (its symbol or measured quantity) in the caption",
                "caption-incomplete", quote=cap_text[:200]))
        # multi-panel figure that never labels its panels
        if env == "figure" and _SUBFIG_RE.search(body) and not _PANEL_RE.search(caption):
            findings.append(finding(
                where, "multi-panel figure caption does not identify its panels",
                "label each panel (a)/(b)/… and say what each shows",
                "caption-incomplete", quote=cap_text[:200]))

    return {
        "pass": not findings,
        "n_floats": n_floats,
        "findings": findings,
        "counts": summarise(findings),
    }
