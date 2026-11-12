"""C8 — the rendered-prose notation-consistency gate (checklist cat 9).

The hardened peer of the advisory naked-term detector: instead of matching prose
against the conceptric's ``def:`` registry (``verify.check_glossary``, which runs
at fold time on the substrate), this runs on the *rendered prose* and asks
whether one term of art appears in two surface forms — the invent-and-reinvent
failure caught after projection.

* ``notation-inconsistent`` — a multi-word technical term that folds (case /
  hyphen / plural, via :func:`laplace.pipeline.verify._norm_term`) to one concept but
  surfaces in two literal spellings (``Gauss-Hermite`` vs ``Gauss–Hermite``,
  ``spectral surface`` vs ``spectral-surface``).

**Report-only fork (Gerard's, F33):** the British/American orthography split is
detected and REPORTED (``orthography-fork``, ``fix=None``) but never enforced —
the corpus is evidenced mixed within single files, so British-only enforcement is
not corpus-derived. This module surfaces the split; the resolution stays his
fork.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    finding, section_spans, section_of, summarise,
)

# A hyphenated technical compound (``Gauss-Hermite``, ``spectral-surface``). The
# consistency check keys on the lowercased word-pair, so a hyphenated form and a
# spaced form of the SAME pair are recognised as one term of art in two surfaces —
# the precise inconsistency the docstring promises, without the noise of a greedy
# noun-phrase matcher.
_HYPHEN_COMPOUND = re.compile(r"\b([A-Za-z]{2,})[-–]([A-Za-z]{2,})\b")

# British/American orthography pairs — REPORT ONLY (Gerard's F33 fork). The
# -ise/-ize stems are CURATED verbs, not a bare ``\w*ise`` (which would flag
# noise/size/precise and report a spurious split). Each pair is (British,
# American, label).
_ISE_STEMS = (
    "normalis", "characteris", "generalis", "parametris", "optimis", "minimis",
    "maximis", "discretis", "regularis", "summaris", "organis", "recognis",
    "realis", "utilis", "emphasis", "factoris", "diagonalis", "renormalis",
)
_ORTHO_PAIRS = [
    (re.compile(r"\b(?:" + "|".join(_ISE_STEMS) + r")(?:e[sd]?|ing|ation)\b", re.I),
     re.compile(r"\b(?:" + "|".join(s[:-2] + "iz" for s in _ISE_STEMS) + r")(?:e[sd]?|ing|ation)\b", re.I),
     "-ise/-ize"),
    (re.compile(r"\b(colour|behaviour|favour|neighbour|labour)s?\b", re.I),
     re.compile(r"\b(color|behavior|favor|neighbor|labor)s?\b", re.I), "-our/-or"),
    (re.compile(r"\b(centre|fibre|litre)s?\b", re.I),
     re.compile(r"\b(center|fiber|liter)s?\b", re.I), "-re/-er"),
    (re.compile(r"\b(modelling|labelling|signalling)\b", re.I),
     re.compile(r"\b(modeling|labeling|signaling)\b", re.I), "-ll-/-l-"),
]

# math/inline-code masking so a symbol like $Z_\tau$ is not read as a term
_MASK = re.compile(r"\$[^$]*\$|\\[A-Za-z]+(\{[^}]*\})?|\\begin\{.*?\}.*?\\end\{.*?\}", re.DOTALL)


def _mask(full: str) -> str:
    return _MASK.sub(lambda m: " " * len(m.group(0)), full)


def check_notation_consistency(target: Union[str, Path]) -> dict[str, Any]:
    """Audit rendered-prose term consistency + report the orthography fork."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    prose = _mask(full)
    spans = section_spans(full)

    # --- term consistency: hyphenated vs spaced (and case) variants ----------
    # For each hyphenated compound, record its literal surface forms; then look
    # for the SAME word-pair written spaced. A pair that appears both ways (or in
    # two cases) and recurs enough to be a term of art is an inconsistency.
    hyphen: dict[tuple[str, str], Counter] = {}
    first_pos: dict[tuple[str, str], int] = {}
    for m in _HYPHEN_COMPOUND.finditer(prose):
        w1, w2 = m.group(1), m.group(2)
        if f"{w1} {w2}".lower() in _STOP_TERMS:
            continue
        key = (w1.lower(), w2.lower())
        hyphen.setdefault(key, Counter())[m.group(0)] += 1
        first_pos.setdefault(key, m.start())

    findings: list[dict[str, Any]] = []
    for (lw1, lw2), surfaces in sorted(hyphen.items()):
        if len(lw1) + len(lw2) < 8:           # too short to be a named compound
            continue
        spaced = re.findall(rf"\b{re.escape(lw1)}\s+{re.escape(lw2)}\b", prose, re.I)
        total = sum(surfaces.values()) + len(spaced)
        n_forms = len(surfaces) + (1 if spaced else 0)
        # only a recurring compound with >1 surface form is a real inconsistency
        if n_forms > 1 and total >= 3 and sum(surfaces.values()) >= 2:
            variant_list = ", ".join(f"{v}×{c}" for v, c in surfaces.most_common())
            if spaced:
                variant_list += f", '{lw1} {lw2}'×{len(spaced)} (spaced)"
            canonical = surfaces.most_common(1)[0][0]
            slug, _t, _a = section_of(first_pos[(lw1, lw2)], spans)
            findings.append(finding(
                f"{slug or '?'}",
                f"one compound term in {n_forms} surface forms: {variant_list}",
                f"standardise on one form (most frequent: '{canonical}')",
                "notation-inconsistent"))

    # --- British/American fork (REPORT ONLY) ---------------------------------
    ortho_report: list[dict[str, Any]] = []
    for brx, arx, name in _ORTHO_PAIRS:
        brit = brx.findall(prose)
        amer = arx.findall(prose)
        if brit and amer:
            ortho_report.append(finding(
                "manuscript (global)",
                f"orthography split {name}: British forms ({len(brit)}) and American forms ({len(amer)}) both present",
                None,                          # REPORT ONLY — Gerard's fork, never auto-edited
                "orthography-fork"))
    findings += ortho_report

    return {
        "pass": not [f for f in findings if f["kind"] != "orthography-fork"],
        "n_inconsistent": len([f for f in findings if f["kind"] == "notation-inconsistent"]),
        "orthography_fork": ortho_report,      # surfaced, not enforced
        "findings": findings,
        "counts": summarise(findings),
    }


# common capitalised words that _TERM_RE would otherwise treat as term heads
_STOP_TERMS = {
    "the following", "as noted", "in this", "we show", "for example", "such that",
    "note that", "figure", "section", "table", "appendix", "panel",
}
