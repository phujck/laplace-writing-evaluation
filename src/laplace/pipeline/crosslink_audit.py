"""C3 — the apparatus crosslink gate (checklist cat 7).

Two conjugate sweeps over the manuscript's reference apparatus.

**Forward** — every ``\\ref``/``\\eqref`` that exists resolves and is meaningful:
* ``crosslink-broken`` — the target label is defined nowhere (a dangling edge in
  the Phase-A graph),
* ``crosslink-vague`` — the prose says "above/below/earlier/previous" about a
  numbered object where a semantic ``\\ref`` should carry the pointer,
* ``crosslink-far`` — a numbered object is referenced many sections before it
  appears (the reader is sent forward a long way).

**Backward** (the new sweep) — every paragraph's *reliance* on out-of-section
information is explicitly linked. Mechanism (uses the Phase-A equation nodes +
reading order): each numbered equation defines a distinctive object (its
left-hand-side symbol). A paragraph in a *different* section whose math uses that
symbol, with no ``\\ref``/``\\eqref`` pointing back to the defining equation (or
any label in its section), is relying on a result established elsewhere without
linking it — ``unlinked-reliance``. The check is a mechanical floor: it requires
a distinctive multi-character symbol (a subscripted or macro'd object, not a bare
``s`` or ``t``) so ubiquitous notation does not flood the report.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.graph import CanonGraph, _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    finding, iter_paragraphs, line_quote, section_of, section_spans, summarise,
    xref_positions,
)

_XREF_RE = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|pageref)\{([^}]+)\}")
# Vague locational words that stand in for a semantic \ref, when they point at a
# numbered object noun.
_VAGUE_RE = re.compile(
    r"\b(above|below|earlier|previous|preceding|the following|as noted|as discussed)\b"
    r"[^.;\n]{0,40}?\b(equation|eq\.|section|sec\.|figure|fig\.|table|result|theorem|lemma|"
    r"definition|identity|expression|derivation)\b", re.I)
_OBJECT_BEFORE = re.compile(
    r"\b(equation|section|figure|table|result|theorem|lemma|identity|expression)\b"
    r"[^.;\n]{0,25}?\b(above|below|earlier|previously)\b", re.I)
# A distinctive symbol: a macro'd/subscripted object, not a lone latin letter.
_SYMBOL_RE = re.compile(r"\\?[A-Za-z]+(?:_\{[^}]+\}|_[A-Za-z0-9])|\\(?:hat|tilde|bar|vec|mathcal|mathbf)\{[^}]+\}")


def _lhs_symbol(latex: str) -> Optional[str]:
    body = re.sub(r"\\label\{[^}]*\}", "", latex)
    m = re.search(r"(.+?)(?:&?\s*=|:=|\\equiv|\\coloneqq)", body)
    if not m:
        return None
    lhs = m.group(1).strip()
    sym = _SYMBOL_RE.search(lhs)
    return sym.group(0) if sym else None


# A single latin letter with a pure-index subscript (p_j, E_j, c_k, s_1, a_i) is
# ubiquitous notation, not a traceable object — its LHS-definition landing in some
# equation does not mean every use "relies on" that equation. Exclude it.
_GENERIC_SYMBOL = re.compile(r"^\\?[A-Za-z]_(?:\{[ijklmn0-9,\s]+\}|[ijklmn0-9])$")


def _distinctive(sym: str) -> bool:
    """Keep only symbols specific enough to trace a cross-section reliance: a
    decorating macro (``\\hat{Z}``), a named subscript (``t_{\\max}``,
    ``Z_\\tau``), or a multi-letter name (``\\Phi``). Drop generic
    index-subscripted single letters (``p_j``) and bare single letters."""
    if _GENERIC_SYMBOL.match(sym):
        return False
    if any(m in sym for m in (r"\hat", r"\tilde", r"\bar", r"\vec", r"\mathcal", r"\mathbf")):
        return True
    if "_" in sym:
        return True
    core = sym.lstrip("\\")
    return len(core) >= 3


def check_crosslink_audit(target: Union[str, Path]) -> dict[str, Any]:
    """Both crosslink sweeps on a compiled manuscript."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    g = CanonGraph.from_manuscript(target)
    spans = section_spans(full)
    refs = xref_positions(full)

    findings: list[dict[str, Any]] = []

    # --- forward: broken refs (Phase-A dangling edges) -----------------------
    for e in g.edges:
        if e.rel == "dangling":
            miss = g.nodes.get(e.dst)
            lab = miss.label if miss else e.dst
            findings.append(finding(
                f"{e.src}",
                f"\\ref/\\eqref points at '{lab}', which is defined by no \\label",
                "define the target label, or correct the reference key",
                "crosslink-broken", quote=e.evidence))

    # --- forward: vague locational cross-references --------------------------
    for p_start, _p_end, para in iter_paragraphs(full):
        if re.match(r"\s*\\(begin|includegraphics|input)\b", para):
            continue
        for rx in (_VAGUE_RE, _OBJECT_BEFORE):
            for m in rx.finditer(para):
                # a \ref in the same clause means the pointer is already semantic
                clause = para[max(0, m.start() - 60):m.end() + 60]
                if _XREF_RE.search(clause):
                    continue
                pos = p_start + m.start()
                slug, _t, _a = section_of(pos, spans)
                findings.append(finding(
                    f"{slug or '?'}",
                    f"vague locational reference '{m.group(0).strip()}' to a numbered object with no \\ref",
                    "replace with a semantic \\ref/\\eqref to the specific object",
                    "crosslink-vague", quote=line_quote(para, m.start())))

    # --- forward: referenced far before it appears ---------------------------
    # section ordinal, so "far" means several sections upstream of the target.
    sec_order = {slug: i for i, (_s, _e, slug, _t, _a) in enumerate(spans)}
    label_owner_order: dict[str, int] = {}
    # map each defined label to the ordinal of the section it is defined in
    for m in re.finditer(r"\\label\{([^}]+)\}", full):
        slug, _t, _a = section_of(m.start(), spans)
        if slug in sec_order:
            label_owner_order[m.group(1)] = sec_order[slug]
    for lab, poss in refs.items():
        # A forward reference to a later SECTION is normal roadmap signposting
        # ("we bound this in Sec.~\ref{sec:N4}"), not a defect — only a numbered
        # object (equation/figure/table) referenced far ahead is a smell.
        if lab.startswith(("sec:", "app:")):
            continue
        tgt_ord = label_owner_order.get(lab)
        if tgt_ord is None:
            continue
        for pos in poss:
            rslug, _t, _a = section_of(pos, spans)
            r_ord = sec_order.get(rslug)
            if r_ord is not None and tgt_ord - r_ord >= 3:
                findings.append(finding(
                    f"{rslug or '?'}→{lab}",
                    f"'{lab}' is referenced {tgt_ord - r_ord} sections before it is defined",
                    "move the object earlier, or forward-signpost why the reader is sent ahead",
                    "crosslink-far", quote=line_quote(full, pos)))

    # --- backward: unlinked cross-section reliance ---------------------------
    # Each equation's LHS symbol → its defining section + label.
    eq_defs: list[tuple[str, str, str, int]] = []   # (symbol, defining_slug, label, order)
    for n in g.nodes.values():
        if n.kind != "equation":
            continue
        latex = n.meta.get("latex")
        if not latex:
            continue
        sym = _lhs_symbol(latex)
        if not sym or not _distinctive(sym):
            continue
        slug, _t, _a = section_of(n.meta.get("reading_order", 0), spans)
        if slug:
            eq_defs.append((
                sym,
                slug,
                n.meta.get("label", n.label),
                int(n.meta.get("reading_order", 0)),
            ))
    # first defining section per symbol (a symbol may be re-stated; the earliest
    # defines it) — dedupe so one symbol reports one home.
    home: dict[str, tuple[str, str, int]] = {}
    for sym, slug, lab, order in eq_defs:
        home.setdefault(sym, (slug, lab, order))

    # label → its defining section slug, so a paragraph that links ANY label in
    # the defining section counts the reliance as wired (not only the exact eq).
    label_home: dict[str, str] = {}
    for m in re.finditer(r"\\label\{([^}]+)\}", full):
        slug, _t, _a = section_of(m.start(), spans)
        if slug:
            label_home.setdefault(m.group(1), slug)

    seen_pairs: set[tuple[int, str]] = set()
    for p_idx, (p_start, _p_end, para) in enumerate(iter_paragraphs(full)):
        if re.match(r"\s*\\(begin|includegraphics|input)\b", para):
            continue
        pslug, _t, _a = section_of(p_start, spans)
        if not pslug:
            continue
        # labels this paragraph already links, and the sections they land in
        linked = {k.strip() for m in _XREF_RE.finditer(para) for k in m.group(1).split(",")}
        linked_sections = {label_home.get(k) for k in linked}
        # math this paragraph carries
        math = " ".join(re.findall(r"\$[^$]+\$|\\\[[^\]]*\\\]", para))
        for sym, (dslug, dlab, dorder) in home.items():
            if dorder > p_start:
                continue
            if dslug == pslug:
                continue                      # same section — no cross-link owed
            if sym not in math:
                continue                      # symbol not used here
            if dlab in linked or dslug in linked_sections:
                continue                      # already linked to the definition/section
            pair = (p_idx, dslug)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            findings.append(finding(
                f"{pslug}",
                f"paragraph uses '{sym}', defined by {dlab} in {dslug}, with no \\ref linking that definition",
                f"add a \\ref/\\eqref to {dlab} (or its section) where the symbol is relied on",
                "unlinked-reliance", quote=line_quote(para, math.find(sym) if sym in math else 0)))

    return {
        "pass": not findings,
        "findings": findings,
        "counts": summarise(findings),
    }
