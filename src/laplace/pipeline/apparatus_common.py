"""Shared substrate for the Phase-C coherence / apparatus gates.

Phase C sits on the Phase-A apparatus substrate (:mod:`laplace.pipeline.graph`): a
manuscript is the same node/edge model sourced from ``.tex`` — sections in
reading order, equations and claims carrying a ``reading_order`` (their source
position in ``\\input`` order), the ``supported_by`` / ``cites`` / ``references``
edges. Every Phase-C module reconstructs its minimal frame from that graph plus
the flattened prose (``_gather_manuscript_text``), never by re-parsing the whole
manuscript from scratch.

This module is the small common floor the nine audit modules share: the finding
shape, the section-span map, paragraph iteration, and the cross-reference index.
Each audit module owns one coherence question and emits findings of the shape::

    {"where": ..., "quote": <optional>, "issue": ..., "fix": ..., "kind": ...}

``kind`` is the routing handle Phase F wires into ``schema.KIND_TO_WORK``; the
manifest of Phase-C kinds → owning stage lives in :data:`FINDING_KIND_STAGE`.
"""

from __future__ import annotations

import re
from typing import Any, Iterator, Optional

# The cross-reference commands a manuscript uses to point at a numbered object.
_XREF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|pageref)\{([^}]+)\}")
_SECTION_RE = re.compile(r"\\(sub)?section\*?\{([^}]+)\}")
_APPENDIX_RE = re.compile(r"\\appendix\b")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")

#: Phase-C finding kinds → the pipeline stage that owns their resolution. This is
#: the manifest Phase F folds into ``schema.KIND_TO_WORK`` / ``WORK_TO_LAYER``;
#: every kind an audit module emits appears here, so an unrouted kind is caught
#: at the door. A "/" names a split — the mechanical floor flags it, the semantic
#: reader (Phase E R2/R3) decides which side of the split it falls on.
FINDING_KIND_STAGE: dict[str, str] = {
    # C1 — equation lifecycle
    "eq-unused": "structural",              # numbered but never referenced
    "eq-ref-before-intro": "structural",    # referenced before it is introduced
    "eq-uninterpreted": "prose",            # stacked math, no prose lead-in/read-out
    "eq-duplicate": "projection",           # same relation under two notations
    # C2 — citation apparatus + coverage
    "citation-uncited": "prose",            # external-fact tell near no \cite (fwd)
    "citation-naked-reliance": "prose",     # ledger-declared reliance not cited (bwd)
    "citation-cluster": "prose",            # end-of-paragraph cite-everything cluster
    "citation-first-use": "prose",          # key first appears in a cluster, not at use
    # C3 — apparatus crosslink
    "crosslink-broken": "structural",       # \ref/\eqref resolves to nothing
    "crosslink-vague": "prose",             # "above/below" where a \ref exists
    "crosslink-far": "structural",          # referenced long before it appears
    "unlinked-reliance": "prose",           # cross-section reliance with no \ref
    # project-declared authored closure
    "closure-roadmap-section": "structural",
    "closure-roadmap-empty": "narrative",
    "closure-roadmap-missing": "narrative",
    "closure-roadmap-order": "narrative",
    "closure-roadmap-position": "narrative",
    "closure-dependency-unlinked": "prose",
    "closure-object-definition": "projection",
    "closure-object-orphan": "structural",
    # C4 — figure system
    "figure-unreferenced": "structural",    # float never \ref'd in the body
    "figure-misplaced": "structural",       # float far from its first mention
    "figure-oversized": "document",         # width does not match its column class
    # C5 — caption completeness
    "caption-missing": "figures",           # float with no \caption
    "caption-incomplete": "figures",        # caption does not name / self-contain its object
    # C6 — front/back matter coherence
    "matter-missing-abstract": "narrative",
    "matter-promise-undelivered": "narrative",   # intro promise with no conclusion echo
    "matter-conclusion-overclaim": "prose",      # conclusion claim with no intro setup
    "matter-appendix-unreachable": "structural", # appendix never \ref'd from the body
    "matter-title-uninformative": "narrative",
    # C7 — tables / algorithms
    "table-uncaptioned": "figures",
    "table-unreferenced": "structural",
    "table-malformed": "document",          # column count vs \begin{tabular} spec
    # C8 — notation consistency
    "notation-inconsistent": "prose",       # one term-of-art, two surface forms
    "orthography-fork": None,               # F33 British/American — REPORT ONLY (Gerard's fork)
    # C9 — proportionality
    "proportionality": "prose",             # claim strength exceeds evidence class
}


def finding(where: str, issue: str, fix: Optional[str], kind: str,
            quote: Optional[str] = None) -> dict[str, Any]:
    """One finding, in the Phase-C shape. ``quote`` is the load-bearing line of
    prose/LaTeX when there is one; ``fix`` is ``None`` for report-only kinds
    (the orthography fork). ``route`` is the owning stage, stamped from the
    manifest so a caller never has to re-derive it."""
    rec: dict[str, Any] = {"where": where}
    if quote:
        rec["quote"] = quote[:240]
    rec["issue"] = issue
    rec["fix"] = fix
    rec["kind"] = kind
    rec["route"] = FINDING_KIND_STAGE.get(kind, "prose")
    return rec


def section_spans(full: str) -> list[tuple[int, int, str, str, bool]]:
    """The section map of a flattened manuscript, in reading order.

    Returns ``(start, end, slug, title, is_appendix)`` per ``\\section`` /
    ``\\subsection``, matching :func:`laplace.pipeline.graph.CanonGraph.from_manuscript`'s
    own span logic so a Phase-C module attributes an equation/claim/paragraph to
    the same section the graph does. ``is_appendix`` is true once ``\\appendix``
    has been seen — the reachability audit (C6) needs to tell body from back
    matter."""
    appendix_at = None
    ap = _APPENDIX_RE.search(full)
    if ap:
        appendix_at = ap.start()
    marks = [(m.start(), m.group(2)) for m in _SECTION_RE.finditer(full)]
    spans: list[tuple[int, int, str, str, bool]] = []
    seen: set[str] = set()
    for i, (start, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(full)
        slug = _slug(name)
        if slug in seen:
            slug = f"{slug}_{i}"
        seen.add(slug)
        is_app = appendix_at is not None and start >= appendix_at
        spans.append((start, end, slug, name, is_app))
    return spans


def section_of(pos: int, spans: list[tuple[int, int, str, str, bool]]
               ) -> tuple[Optional[str], Optional[str], bool]:
    """The ``(slug, title, is_appendix)`` of the section a position sits in."""
    for start, end, slug, title, is_app in spans:
        if start <= pos < end:
            return slug, title, is_app
    return None, None, False


def line_quote(full: str, pos: int, width: int = 200) -> str:
    """The single line of prose a position sits on, trimmed — the evidence line,
    same shape as :func:`laplace.pipeline.graph._line_at`."""
    start = full.rfind("\n", 0, pos) + 1
    end = full.find("\n", pos)
    if end == -1:
        end = len(full)
    return full[start:end].strip()[:width]


def xref_positions(full: str) -> dict[str, list[int]]:
    """Every cross-reference target → the positions it is invoked at. Multi-key
    ``\\cref{a,b}`` splits into each key."""
    out: dict[str, list[int]] = {}
    for m in _XREF_RE.finditer(full):
        for key in (k.strip() for k in m.group(1).split(",")):
            if key:
                out.setdefault(key, []).append(m.start())
    return out


def iter_paragraphs(full: str) -> Iterator[tuple[int, int, str]]:
    """Yield ``(start, end, text)`` per prose paragraph of the flattened
    manuscript. Comments (the ``% <sid>-pN`` markers) are already blanked by the
    gatherer, so paragraphs separate on blank lines. A block that is purely a
    LaTeX environment (a figure/equation float with no prose) still yields — the
    caller decides whether it is prose."""
    for m in re.finditer(r"(?s).+?(?:\n\s*\n|\Z)", full):
        text = m.group(0)
        if text.strip():
            yield m.start(), m.end(), text


# Sentence split that keeps abbreviations and inline math intact enough for a
# tell-scan (Eq., Sec., Fig., Ref., e.g., i.e., et al. do not end a sentence).
_ABBREV = r"(?<!\bEq)(?<!\bEqs)(?<!\bSec)(?<!\bFig)(?<!\bFigs)(?<!\bRef)(?<!\bApp)(?<!\bNo)(?<!\be\.g)(?<!\bi\.e)(?<!\bcf)(?<!\bal)"
_SENT_SPLIT = re.compile(_ABBREV + r"(?<=[.!?])\s+(?=[A-Z\\$])")


def iter_sentences(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(offset_within_text, sentence)`` for a prose block. Offsets are
    relative to ``text`` so the caller can lift them to an absolute position."""
    pos = 0
    for part in _SENT_SPLIT.split(text):
        if part.strip():
            off = text.find(part, pos)
            if off < 0:
                off = pos
            yield off, part
            pos = off + len(part)


def _slug(s: str) -> str:
    """The same slug :mod:`laplace.pipeline.graph` uses, re-stated so this module does not
    reach into a private helper."""
    s = re.sub(r"[:/\s\-]+", "_", s.strip())
    s = re.sub(r"[^A-Za-z0-9_]", "", s)
    return (s[:60] or "x").lower()


def summarise(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Count findings by kind — the per-module acceptance line."""
    out: dict[str, int] = {}
    for f in findings:
        out[f["kind"]] = out.get(f["kind"], 0) + 1
    return out
