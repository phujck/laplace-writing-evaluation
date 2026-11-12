"""The meta-leak scrub — the existing ``no_meta_leak`` gate wired over a paper's
converge path, extended to catch the source-tier typing vocabulary leaking into
body prose (his corrected rejection, ARMING_2026-07-16 / PV-20260717T005612Z: the
orchestrator's own read of falqon found *meta-vocabulary in body text* — the
engine's internal epistemic-typing language, ``SCENARIO-tier`` / ``trust=unverified``
/ ``TO-VERIFY`` / ``DERIVED-tier``, narrated in the prose the reader sees).

Why an EXTENSION, not just a call to :func:`verify.check_meta_leak`: the core gate's
lexicon (``schema.META_LEAK_PATTERNS``) catches the machine's PROCESS vocabulary
(plan/fork/node/adjudicate) but was never taught the SOURCE-TIER labels a physics
projection legitimately uses in an ASSUMPTION TABLE — and so must NOT use as running
prose. His V1 draft keeps the tiers in the assumption table (a column header:
``SCENARIO`` / ``DERIVED`` / ``LITERATURE``); the projection LEAKED them into
sentences (*"This is a SCENARIO-tier choice"*, *"carrying trust=unverified"*). The
scrub charges the tier vocabulary ONLY in body prose, and ONLY the hyphenated /
predicate forms that are unambiguously the machine's typing register — a bare
``SCENARIO`` inside a table row is never charged (the table is where the tier
BELONGS).

This organ composes:

  1. the core gate (:func:`verify.check_meta_leak`) — process-vocabulary + policy
     echo, unchanged; and
  2. the SOURCE-TIER scrub (this module) — the epistemic-typing leak, typed by
     class, each hit carrying the verbatim line as its primary record + the
     ``trust`` stamp the arming names.

It runs read-only: :func:`scrub_project` reads the compiled ``.tex`` and returns the
violation list; it writes nothing. Banking (to a paper's evidence/rounds dir) is the
caller's, so the gate over the converge path never mutates the artefact it audits.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

# --- the source-tier typing vocabulary, as body-text leaks -------------------
# Each class -> the patterns that are the machine's epistemic-typing register when
# they appear in a PROSE sentence. Hyphenated ``*-tier`` and predicate forms only:
# a bare tier word in a table cell is legitimate and must not fire (see
# _is_table_line). ``trust=…`` / ``TO-VERIFY`` are pure machine tokens — always a
# leak in prose.
SOURCE_TIER_PATTERNS: dict[str, tuple[str, ...]] = {
    # the hyphenated tier label narrated as prose ("a SCENARIO-tier choice")
    "tier-label": (
        r"\b(?:SCENARIO|DERIVED|LITERATURE|TEXTBOOK|MODEL)-tier\b",
        r"\bsource[- ]tier\b",
        r"\bat (?:a |an )?(?:SCENARIO|DERIVED|LITERATURE|TEXTBOOK)[- ]tier\b",
    ),
    # the trust predicate — a machine field surfaced verbatim in prose
    "trust-predicate": (
        r"\btrust\s*=\s*unverified\b",
        r"\bcarr(?:y|ies|ying) trust\b",
        r"\bmarked (?:as )?unverified\b",
    ),
    # the verification-status token (a ledger tag, not prose)
    "verify-token": (
        r"\bTO-VERIFY\b",
        r"\bflagged TO-VERIFY\b",
    ),
    # the tier word used as a predicate on a choice ("is SCENARIO-tier",
    # "a SCENARIO estimate", "a SCENARIO assumption") — the typing register, prose
    "tier-predicate": (
        r"\b(?:is|as|a|an) (?:SCENARIO|DERIVED|LITERATURE|TEXTBOOK)\b"
        r"(?=\s+(?:choice|estimate|assumption|target|value|input|tier|constant|"
        r"parameter|figure|modelling))",
    ),
}

#: the class -> the trust stamp the arming asks banked with each violation.
_CLASS_TRUST = {
    "tier-label": "unverified",
    "trust-predicate": "unverified",
    "verify-token": "unverified",
    "tier-predicate": "unverified",
}

_COMMENT_RE = re.compile(r"^\s*%")
# a markdown/LaTeX table row (pipe-delimited or a tabular cell) — the tier BELONGS
# here; only prose lines are charged.
_TABLE_RE = re.compile(r"(?:^\s*\|)|(?:&.*\\\\)|(?:\\\\\s*$)|(?:\btabular\b)")


def _compile() -> dict[str, list[re.Pattern]]:
    return {cls: [re.compile(p) for p in pats]   # case-SENSITIVE: the tokens are caps
            for cls, pats in SOURCE_TIER_PATTERNS.items()}


def _is_table_line(line: str) -> bool:
    return bool(_TABLE_RE.search(line))


def scrub_text(tex_name: str, text: str) -> list[dict[str, Any]]:
    """Scan one .tex body for source-tier leaks. Comment lines and table rows are
    excluded (the tier belongs in the assumption table). Returns one typed hit per
    match, each carrying the verbatim line (primary record) + the trust stamp."""
    compiled = _compile()
    hits: list[dict[str, Any]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if _COMMENT_RE.match(line):
            continue
        body = line.split("%", 1)[0]
        if _is_table_line(body):
            continue
        for cls, pats in compiled.items():
            for pat in pats:
                m = pat.search(body)
                if m:
                    hits.append({
                        "file": tex_name,
                        "line": lineno,
                        "class": cls,
                        "match": m.group(0),
                        "trust": _CLASS_TRUST[cls],
                        "quote": body.strip()[:240],       # verbatim primary record
                        "where": f"{tex_name}:{lineno}",
                        "issue": f"source-tier typing vocabulary '{m.group(0)}' "
                                 "leaked into body prose (belongs in the assumption "
                                 "table, not the running argument)",
                        "kind": "meta-leak-source-tier",
                    })
                    break                    # one hit per (line, class)
    return hits


def scrub_tex_dir(tex_dir: Union[str, Path]) -> list[dict[str, Any]]:
    """Scrub every ``*.tex`` under a compiled manuscript dir. Read-only."""
    tex_dir = Path(tex_dir)
    hits: list[dict[str, Any]] = []
    for tex in sorted(tex_dir.glob("*.tex")):
        try:
            text = tex.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        hits.extend(scrub_text(tex.name, text))
    return hits


def scrub_project(project: str,
                  *, tex_dir: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """Run the FULL scrub over a project's converge path, READ-ONLY: the core
    ``no_meta_leak`` gate (process vocabulary + policy echo) COMPOSED with the
    source-tier body-prose scrub. Returns
    ``{pass, core, source_tier, hits, n, by_class}`` where ``hits`` is the merged
    violation list — the primary record a strong pass consumes. Writes nothing.

    ``tex_dir`` overrides the project's resolved target dir (for tests / a bundle
    read); otherwise the project registry resolves it."""
    from laplace.pipeline import verify

    core = verify.check_meta_leak(project)
    core_hits = list(core.get("hits") or [])

    if tex_dir is None:
        try:
            from laplace.pipeline import registry
            proj = registry.resolve(project)
            resolved = proj.resolved_target_dir() if proj else None
            tex_dir = resolved
        except Exception:
            tex_dir = None
    tier_hits = scrub_tex_dir(tex_dir) if tex_dir else []

    merged = (
        [dict(h, source="core", kind=h.get("class", "meta-leak")) for h in core_hits]
        + tier_hits)
    by_class: dict[str, int] = {}
    for h in merged:
        c = h.get("class", "?")
        by_class[c] = by_class.get(c, 0) + 1
    return {
        "pass": not merged,
        "project": project,
        "core": {"pass": core.get("pass"), "n": len(core_hits)},
        "source_tier": {"pass": not tier_hits, "n": len(tier_hits)},
        "hits": merged,
        "n": len(merged),
        "by_class": by_class,
    }


def to_findings(scrub: dict[str, Any], *, round: int = 0,
                actor: str = "meta_leak_scrub") -> list[dict[str, Any]]:
    """Shape the scrub's hits as panel-style findings for the strong pass — each
    at trust=unverified, SCENARIO-tier body leaks routed to ``prose`` (the leak is
    re-worded in prose, the tier moved to the table). The verbatim line rides as
    ``quote`` (primary record)."""
    out: list[dict[str, Any]] = []
    for h in scrub.get("hits") or []:
        out.append({
            "where": h.get("where") or f"{h.get('file','')}:{h.get('line','')}",
            "kind": h.get("kind", "meta-leak"),
            "route": "prose",
            "class": h.get("class"),
            "trust": h.get("trust", "unverified"),
            "issue": h.get("issue", "meta-leak"),
            "quote": h.get("quote", h.get("match", "")),
            "fix": "re-word the sentence without the typing token; the source tier "
                   "lives in the assumption table, not the running prose",
            "source": actor,
            "round": round,
        })
    return out


def finding_kinds_manifest() -> list[dict[str, str]]:
    """kind -> owning stage, folded into ``schema.KIND_TO_WORK``. The source-tier
    leak routes to ``prose`` (re-worded there)."""
    return [{"kind": "meta-leak-source-tier", "stage": "prose"}]
