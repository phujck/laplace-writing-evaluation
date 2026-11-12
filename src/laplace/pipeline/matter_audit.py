"""C6 — the front/back-matter coherence gate (checklist cat 12).

The COHERENCE question, deliberately distinct from Phase B's matter *erasure*
pass (which strips the abstract roadmap, the intro evidence-ledger, the appendix
dumping-ground). This module asks the conjugate question: does the object hold
together across its regions — do the intro's promises match the conclusion's
deliveries, is nothing over-claimed at the close, is every appendix reachable
from the body? Named ``check_matter_coherence`` so it never collides with the
erasure pass conceptually.

Checks (per region):

* ``matter-missing-abstract``     — no ``abstract`` environment before
  ``\\maketitle`` (a paper with no stated contribution up front),
* ``matter-title-uninformative``  — the title is a placeholder / too thin,
* ``matter-promise-undelivered``  — an introduction "we <verb>" promise with no
  echo in the conclusion,
* ``matter-conclusion-overclaim``  — a conclusion claim using a stronger verb
  than the intro/abstract ever used (escalation at the close),
* ``matter-appendix-unreachable`` — an appendix section never ``\\ref``'d from
  the body.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.graph import CanonGraph, _gather_manuscript_text
from laplace.pipeline.apparatus_common import (
    finding, section_spans, summarise, xref_positions,
)

_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
_TITLE_RE = re.compile(r"\\title\{((?:[^{}]|\{[^{}]*\})*)\}", re.DOTALL)
_APPENDIX_RE = re.compile(r"\\appendix\b")
_SECTION_RE = re.compile(r"\\(sub)?section\*?\{([^}]+)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")

# "we <verb>" promise/delivery verbs, graded by claim strength (weak → strong).
_CLAIM_VERBS = {
    "show", "present", "describe", "introduce", "define", "derive", "construct",
    "validate", "demonstrate", "observe", "report", "find", "measure", "compute",
    "bound", "characterise", "characterize", "analyse", "analyze",
}
_STRONG_VERBS = {"prove", "establish", "guarantee", "certify", "confirm", "resolve", "solve"}
_ALL_VERBS = _CLAIM_VERBS | _STRONG_VERBS
_WE_CLAIM = re.compile(r"\bwe\s+(" + "|".join(sorted(_ALL_VERBS)) + r")\b", re.I)
# The roadmap promise form: "Section~\ref{...} proves/derives/…" — a manuscript
# that stages its argument promises deliverables per section, not only with "we".
_ROADMAP_CLAIM = re.compile(
    r"\b(?:section|sec\.?|appendix|app\.?)\s*(?:~)?\s*(?:\\ref\{[^}]*\})?\s*"
    r"(" + "|".join(sorted(v + r"s?" for v in _ALL_VERBS)) + r")\b", re.I)
_TOP_SECTION_RE = re.compile(r"\\section\*?\{([^}]+)\}")

_INTRO_TITLE = re.compile(r"\b(introduction|overview)\b", re.I)
_CONCL_TITLE = re.compile(r"\b(conclusion|closing|summary|outlook|discussion)\b", re.I)


def _region_text(full: str, spans, matcher) -> str:
    for start, end, _slug, title, _app in spans:
        if matcher.search(title or ""):
            return full[start:end]
    return ""


def _claim_verbs(text: str) -> set[str]:
    """The set of claim verbs a region promises/delivers — both the first-person
    ("we derive") and the roadmap ("Sec.~\\ref{} derives") forms, stemmed to the
    bare verb so 'derives'/'derive' fold together."""
    out: set[str] = {m.group(1).lower() for m in _WE_CLAIM.finditer(text)}
    for m in _ROADMAP_CLAIM.finditer(text):
        out.add(m.group(1).lower().rstrip("s"))
    return out


def check_matter_coherence(target: Union[str, Path]) -> dict[str, Any]:
    """Audit front/back-matter coherence on a compiled manuscript."""
    target = Path(target)
    full = _gather_manuscript_text(target)
    spans = section_spans(full)
    g = CanonGraph.from_manuscript(target)
    refs = xref_positions(full)

    findings: list[dict[str, Any]] = []

    # --- abstract present, states a contribution -----------------------------
    abs_m = _ABSTRACT_RE.search(full)
    if not abs_m:
        findings.append(finding(
            "front-matter",
            "no abstract environment — the paper states no contribution before the body",
            "add an \\begin{abstract} stating the contribution (the result, not the process)",
            "matter-missing-abstract"))

    # --- title informative ---------------------------------------------------
    tm = _TITLE_RE.search(full)
    title = re.sub(r"\s+", " ", tm.group(1)).strip() if tm else ""
    if not title or len(title.split()) < 4 or re.search(r"\b(untitled|draft|todo|placeholder|title here)\b", title, re.I):
        findings.append(finding(
            "front-matter", f"title is thin or a placeholder: {title!r}",
            "state the object and the contribution in the title",
            "matter-title-uninformative", quote=title))

    # --- intro promises == conclusion delivers -------------------------------
    intro = _region_text(full, spans, _INTRO_TITLE)
    concl = _region_text(full, spans, _CONCL_TITLE)
    intro_verbs = _claim_verbs(intro)
    concl_verbs = _claim_verbs(concl)
    # The promise/delivery diff is a verb-set floor; it can only adjudicate when
    # the conclusion is itself claim-verb-structured. A declaratively written
    # conclusion ("SSG is fixed by its contract …") yields no verbs — matching
    # promise to that phrasing is R1/R4's semantic job, not this floor's, so the
    # diff stays quiet rather than flagging every promise as undelivered.
    if intro_verbs and concl_verbs:
        undelivered = intro_verbs - concl_verbs
        # a verb dropped by the conclusion may simply be phrased differently, so
        # this is a floor: the finding routes to the narrative reader.
        for v in sorted(undelivered):
            # find the promise sentence for the quote
            pm = re.search(r"[^.]*\bwe\s+" + v + r"\b[^.]*\.", intro, re.I)
            findings.append(finding(
                "intro↔conclusion",
                f"introduction promises to '{v}' but the conclusion never echoes it",
                "either deliver the promise in the conclusion or drop it from the intro",
                "matter-promise-undelivered",
                quote=(pm.group(0).strip() if pm else None)))

    # --- conclusion over-claim: a strong verb the intro/abstract never used ---
    if concl_verbs:
        abstract = abs_m.group(1) if abs_m else ""
        setup_strong = (intro_verbs | _claim_verbs(abstract)) & _STRONG_VERBS
        for v in sorted(concl_verbs & _STRONG_VERBS):
            if v not in setup_strong:
                pm = re.search(r"[^.]*\bwe\s+" + v + r"\b[^.]*\.", concl, re.I)
                findings.append(finding(
                    "conclusion",
                    f"conclusion claims to '{v}' (a strong verb) with no matching setup in the intro/abstract",
                    "match the claim strength to what the body earns, or set it up earlier",
                    "matter-conclusion-overclaim",
                    quote=(pm.group(0).strip() if pm else None)))

    # --- every appendix reachable from the body ------------------------------
    # One finding per top-level appendix (each \section after \appendix), not per
    # subsection: an appendix is reachable when some \ref from the BODY (before
    # \appendix) points at any label inside its span. A ref that lives in another
    # appendix does not count — "reachable from the body" is the checklist test.
    ap = _APPENDIX_RE.search(full)
    if ap:
        appendix_start = ap.start()
        marks = [(m.start(), re.sub(r"\s+", " ", m.group(1)).strip())
                 for m in _TOP_SECTION_RE.finditer(full) if m.start() >= appendix_start]
        from laplace.pipeline.apparatus_common import _slug
        for i, (start, title) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(full)
            labels = _LABEL_RE.findall(full[start:end])
            reachable = any(
                pos < appendix_start
                for lab in labels for pos in refs.get(lab, []))
            if not reachable:
                why = ("carries no \\label to reference it by" if not labels
                       else "is never \\ref'd from the body (only from other back matter, if at all)")
                findings.append(finding(
                    f"appendix:{_slug(title)}",
                    f"appendix '{title}' {why} — unreachable back matter",
                    "reference the appendix from the body at the point it is needed, or fold it in",
                    "matter-appendix-unreachable"))

    return {
        "pass": not findings,
        "has_abstract": bool(abs_m),
        "intro_promises": sorted(intro_verbs),
        "conclusion_delivers": sorted(concl_verbs),
        "findings": findings,
        "counts": summarise(findings),
    }
