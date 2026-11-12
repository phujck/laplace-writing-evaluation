"""C1 — the equation lifecycle gate (checklist cat 3).

A numbered display equation earns its number by living a full lifecycle:
**introduced** (prose sets it up), **interpreted** (prose reads it out), and
**reused / referenced** (a later ``\\ref``/``\\eqref``, or a clear terminal role
as a stated result). An equation that is numbered but never referenced and never
interpreted is scaffolding the reader must carry for nothing — the construction
numbered it to break the prose, and the finished object should either reference
it or de-number it.

The check reconstructs its frame from the Phase-A graph (equation nodes carry a
``reading_order``; ``supported_by`` / ``references`` edges carry the apparatus)
plus the flattened prose, and emits four kinds:

* ``eq-unused``            — numbered, zero ``\\ref``/``\\eqref`` (triaged:
                             likely-terminal result vs candidate-to-de-number),
* ``eq-ref-before-intro``  — first reference precedes the equation's own
                             introduction (reading_order),
* ``eq-uninterpreted``     — the equation is stacked against another environment
                             or a section break with no prose to read it out,
* ``eq-duplicate``         — two labels carry the same relation under different
                             notation (same normalised body, or same LHS symbol).

The Phase-A run already surfaces 71 unreferenced SSG equations; this gate
confirms that set and triages it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.graph import CanonGraph, _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    finding, line_quote, section_spans, section_of, summarise,
)

_XREF_TARGET = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref)\{([^}]+)\}")
_ENV_OPEN = re.compile(r"\\begin\{(equation|align|gather|multline|eqnarray|flalign|displaymath)\*?\}")
# Sections whose role is to STATE results — an unreferenced equation there is
# plausibly a terminal result, not dead numbering.
_TERMINAL_ROLE = ("res:", "thm:")
_TERMINAL_SECTION = re.compile(r"\b(result|theorem|conclusion|main|summary)\b", re.I)


def _norm_body(latex: str) -> str:
    """Fold an equation body to a notation-insensitive signature for duplicate
    detection: drop labels/tags/spacing, collapse whitespace and left/right
    delimiters. Two equations that state the same relation under different
    *notation* still differ symbol-for-symbol, so this catches the exact-repeat
    and near-repeat case, not a semantic-equivalence claim (that is R3's)."""
    s = re.sub(r"\\label\{[^}]*\}", "", latex)
    s = re.sub(r"\\(?:notag|nonumber|qquad|quad|,|;|:|!|\s)", " ", s)
    s = re.sub(r"\\(?:left|right|big|Big|bigg|Bigg)\b", "", s)
    s = re.sub(r"[\s&]+", "", s)
    return s


def _lhs_symbol(latex: str) -> Optional[str]:
    """The left-hand side of the first relation in the body — the object the
    equation defines. Used to spot the same object numbered twice."""
    body = re.sub(r"\\label\{[^}]*\}", "", latex)
    m = re.search(r"(.+?)(?:&?\s*=|:=|\\equiv|\\coloneqq)", body)
    if not m:
        return None
    lhs = re.sub(r"[\s]+", "", m.group(1))
    return lhs or None


def check_equation_lifecycle(target: Union[str, Path]) -> dict[str, Any]:
    """Audit every numbered equation's lifecycle on a compiled manuscript."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    g = CanonGraph.from_manuscript(target)
    spans = section_spans(full)

    # Every cross-reference, by raw target label and by position.
    ref_at: dict[str, list[int]] = {}
    for m in _XREF_TARGET.finditer(full):
        for key in (k.strip() for k in m.group(1).split(",")):
            if key:
                ref_at.setdefault(key, []).append(m.start())

    # Environment openings, so "interpreted" can tell a stacked equation (another
    # \begin immediately after, with no prose between) from one the prose reads.
    env_open_at = sorted(m.start() for m in _ENV_OPEN.finditer(full))
    sec_at = sorted(s[0] for s in spans)

    findings: list[dict[str, Any]] = []
    eq_nodes = [n for n in g.nodes.values() if n.kind == "equation"]
    unreferenced = 0
    by_body: dict[str, list[str]] = {}
    by_lhs: dict[str, list[str]] = {}

    for n in eq_nodes:
        raw = n.meta.get("label", n.label)
        order = n.meta.get("reading_order", 0)
        slug, title, is_app = section_of(order, spans)
        where = f"{slug or '?'}:{raw}"
        refs = ref_at.get(raw, [])

        # --- reused / referenced --------------------------------------------
        if not refs:
            unreferenced += 1
            role = raw.split(":", 1)[0] + ":" if ":" in raw else ""
            terminal = role in _TERMINAL_ROLE and (
                title is not None and _TERMINAL_SECTION.search(title or "")
            )
            if terminal:
                issue = ("numbered equation never \\ref'd; sits in a results/"
                         "conclusion section under a res:/thm: role — plausibly a "
                         "terminal result, confirm it is stated as the section's payload")
                fix = "if terminal, keep the number and make the prose name it as the result; else de-number"
            else:
                issue = ("numbered equation never \\ref'd and not in a terminal-"
                         "result role — the number only breaks the prose")
                fix = "de-number (drop \\label / use equation*), or add the \\ref that reuses it"
            findings.append(finding(where, issue, fix, "eq-unused",
                                    quote=line_quote(full, order)))

        # --- referenced before introduced ------------------------------------
        elif min(refs) < order:
            first = min(refs)
            rslug, _, _ = section_of(first, spans)
            findings.append(finding(
                where,
                f"equation first \\ref'd in {rslug or '?'} before it is introduced in {slug or '?'}",
                "introduce the equation before the first reference, or forward-signpost the reference",
                "eq-ref-before-intro", quote=line_quote(full, first)))

        # --- interpreted (prose read-out) ------------------------------------
        # The equation env spans [order, next_env_or_section). If the very next
        # structural mark after this equation's own \end is another \begin{math}
        # or a \section with <1 sentence of prose in between, it is stacked and
        # unread.
        env_end = full.find(r"\end{", order)
        env_end = full.find("}", env_end) + 1 if env_end != -1 else order
        nxt_env = next((p for p in env_open_at if p > env_end), None)
        nxt_sec = next((p for p in sec_at if p > env_end), None)
        boundary = min(x for x in (nxt_env, nxt_sec, len(full)) if x is not None)
        gap = full[env_end:boundary]
        # Strip inline glue; a genuine read-out is a sentence of prose.
        prose = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?(\{[^}]*\})?", " ", gap)
        prose = re.sub(r"[^A-Za-z]", " ", prose)
        if len(prose.split()) < 4 and (nxt_env is not None and nxt_env <= (nxt_sec or len(full))):
            findings.append(finding(
                where,
                "equation is stacked directly against the next display environment with no prose read-out",
                "add a clause interpreting the equation before the next display block",
                "eq-uninterpreted", quote=line_quote(full, order)))

        # collect for duplicate detection
        latex = n.meta.get("latex")
        if latex:
            by_body.setdefault(_norm_body(latex), []).append(raw)
            lhs = _lhs_symbol(latex)
            if lhs and len(lhs) >= 3:
                by_lhs.setdefault(lhs, []).append(raw)

    # --- duplicate under different notation ----------------------------------
    for body, labels in by_body.items():
        uniq = sorted(set(labels))
        if len(uniq) > 1:
            findings.append(finding(
                f"{uniq[0]} == {', '.join(uniq[1:])}",
                "two numbered equations share an identical (notation-folded) body",
                "keep one numbered statement of the relation; reference it from the other site",
                "eq-duplicate"))
    for lhs, labels in by_lhs.items():
        uniq = sorted(set(labels))
        if len(uniq) > 1 and uniq[0] not in {l for b, ls in by_body.items() if len(set(ls)) > 1 for l in ls}:
            findings.append(finding(
                f"{', '.join(uniq)}",
                f"the same left-hand side ({lhs}) is defined by more than one numbered equation — possible re-definition under changed notation",
                "unify the notation and define the object once, or distinguish the two objects",
                "eq-duplicate"))

    return {
        "pass": not findings,
        "n_equations": len(eq_nodes),
        "n_unreferenced": unreferenced,
        "findings": findings,
        "counts": summarise(findings),
    }
