"""The recurring-tic detectors — mechanical, text-level, cheap (his hold-out review,
2026-07-10: *other tics that are annoying and should in some way be caught*).

The figure-layout gates (:mod:`layout_gates`) catch defects that only exist in the
RENDERED object. These three detectors catch defects that live in the TEXT itself —
the annoying, recurring authorial tics the hold-out review surfaced on the r2 SSG
whitepaper, each cheap enough to ride every convergence round as EVIDENCE (advisory,
not a revert trigger — the figures/prose are inherited debt until re-authored):

  * **DEFENSIVE-CAPTION** — a caption that carries the whole defensive apparatus
    (what-it-shows + provenance/filenames/seeds + numerical conventions + the
    supported claim + the non-claims/disclaimers) is doing the manuscript's job.
    A caption should keep interpretation + conditions; provenance belongs in the
    manifest, the non-claims in the interpretation section. A caption presenting
    >= 4 of the five defensive facets is flagged ``caption-defensive``.

  * **DISCLAIMER-REPETITION** — the six disclaimer classes (no-hardness /
    no-advantage / no-hardware / exact-vs-finite-size / guide-not-law /
    reference-not-certification) counted document-wide. State a boundary once, label
    it at appearance, give the full boundary in one place (his §VII) — a class that
    recurs past the threshold (default 3) is flagged ``disclaimer-repetition`` with
    the count and the sections it recurs in.

  * **SENTENCE-DENSITY** — a sentence carrying claim + condition + exception + status
    + forward-reference at once is a split candidate. The mechanical proxy: more than
    two subordinate markers AND more than forty words. Flagged ``sentence-overloaded``.

Each detector is a ``check_*`` returning the pipeline's audit shape
(``{"pass", "clean", "findings", "counts"}``); findings carry ``{where, issue, fix,
kind}`` plus the load-bearing measurement (the facet set, the recurrence count + its
sections, the marker/word counts) and ``grade="evidence"`` (these are advisory panel
axes, never a hard blocker — they are inherited debt, not a revert trigger). The
detectors REUSE, never re-derive: the flattened comment-stripped manuscript text from
:mod:`laplace.pipeline.graph`, the section map from :mod:`apparatus_common`, and the
balanced-brace caption extraction from :mod:`caption_audit`. Read-only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline.graph import _gather_manuscript_text
from laplace.pipeline.apparatus_common import section_of, section_spans, summarise
from laplace.pipeline.caption_audit import _FLOAT_RE, _LABEL_RE, _extract_caption

# ---------------------------------------------------------------------------
# finding shape + routing (local vocabulary; evidence-grade, advisory — these
# kinds are NOT registered in schema.KIND_TO_WORK because they never pour to the
# fixer's worklist: they ride the harnessed round evidence as an advisory axis).
# ---------------------------------------------------------------------------

#: kind -> the surface a re-author would touch. ``figures`` for the caption tic
#: (a caption change), ``prose`` for the two prose tics. Carried on the finding so
#: an escalation view reads the owning surface without re-deriving it.
TIC_KIND_STAGE: dict[str, str] = {
    "caption-defensive":      "figures",
    "disclaimer-repetition":  "prose",
    "sentence-overloaded":    "prose",
}


def _finding(where: str, issue: str, fix: Optional[str], kind: str,
             quote: Optional[str] = None, **extra: Any) -> dict[str, Any]:
    """One finding in the pipeline's standard shape, graded ``evidence`` (advisory)
    and routed from :data:`TIC_KIND_STAGE`. ``extra`` carries the load-bearing
    measurement so a downstream reader reads the number, not the prose."""
    rec: dict[str, Any] = {"where": where}
    if quote:
        rec["quote"] = quote[:240]
    rec["issue"] = issue
    rec["fix"] = fix
    rec["kind"] = kind
    rec["route"] = TIC_KIND_STAGE.get(kind, "prose")
    rec["grade"] = "evidence"
    rec.update(extra)
    return rec


def _result(findings: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    """The audit-shape result. ``pass`` follows the Phase-C idiom; ``clean`` is the
    same value under the release idiom."""
    ok = not findings
    out: dict[str, Any] = {"pass": ok, "clean": ok, "findings": findings,
                           "counts": summarise(findings)}
    out.update(extra)
    return out


def _resolve_target(target: Union[str, Path]) -> Path:
    """The flatten target: ``<dir>/main.tex`` when ``target`` is a directory carrying
    one, else ``target`` itself (a .tex path or a directory the gatherer walks)."""
    target = Path(target)
    if target.is_dir() and (target / "main.tex").is_file():
        return target / "main.tex"
    return target


# ===========================================================================
# (a) DEFENSIVE-CAPTION — a caption carrying the whole defensive apparatus
# ===========================================================================

#: The five defensive facets. Each is a caption doing work that belongs elsewhere;
#: a caption keeps interpretation + conditions, so >= 4 facets present means the
#: caption has absorbed the manifest (provenance), the interpretation section
#: (non-claims) and the methods table (conventions) into itself.
_FACET_PATTERNS: dict[str, re.Pattern] = {
    # what the figure/panel shows — the legitimate core of a caption
    "what_shown": re.compile(
        r"\b(?:shows?|plots?|depicts?|displays?|illustrat\w+|reports?|traces?|"
        r"compares?|versus|\bvs\.?\b|panel\s*\(?[a-h]\)?|each\s+cell|the\s+highlighted|"
        r"measured|profile|curves?)\b", re.I),
    # provenance / filenames / seeds / data keys — belongs in the manifest
    "provenance": re.compile(
        r"\b(?:data\s+sources?|seeds?\b|generating\s+(?:command|script)|"
        r"computed\s+(?:exactly|inline)|instance\s+sequence|finite-shot\s+sampl\w+|"
        r"deterministic|run\s+\d+|[A-Z][A-Za-z]*-N?\d+[a-z]?|\.pdf\b|\.csv\b|\.npz\b)\b"),
    # numerical conventions / tolerances / thresholds — belongs in methods
    "conventions": re.compile(
        r"(?:\bconvention\b|\btolerance\b|\btruncation\b|discarded-weight|per-gate|"
        r"\$10\^|\bbond\s+dimension\b|reported\s+at\s+the|threshold\s+of|"
        r"\\chi_?\{?\\?(?:mathrm)?)", re.I),
    # the supported claim stated inside the caption
    "supported_claim": re.compile(
        r"\b(?:supports?|serves?\s+as\s+the|validation\s+logic|it\s+supports|"
        r"the\s+figure\s+supports|supports?\s+the\s+claim)\b", re.I),
    # the non-claims / disclaimers — belongs in the interpretation section
    "non_claims": re.compile(
        r"(?:does\s+not\s+(?:establish|settle|imply|claim|obtain)|not\s+hardness|"
        r"no\s+(?:worst-case\s+)?hardness|proof\s+of\s+principle|establishes?\s+nothing|"
        r"nothing\s+(?:in|about)[^.]*establish\w*|not\s+obtained\s+for\s+free|"
        r"not\s+a\s+property|no\s+separation|equally\s+fixes\s+what|"
        r"what\s+the\s+benchmark\s+is\s+not|is\s+not\s+a)", re.I),
}


def caption_facets(caption: str) -> list[str]:
    """The defensive facets a single caption carries (a subset of the five)."""
    return [name for name, pat in _FACET_PATTERNS.items() if pat.search(caption or "")]


def check_defensive_captions(target: Union[str, Path], *,
                             min_facets: int = 4) -> dict[str, Any]:
    """DEFENSIVE-CAPTION — flag every caption carrying ``>= min_facets`` of the five
    defensive facets {what-shown, provenance, conventions, supported-claim,
    non-claims}. A defensive caption has absorbed the manifest, the methods table and
    the interpretation section into itself; the fix is to keep interpretation +
    conditions in the caption and move provenance to the manifest, the non-claims to
    the interpretation section. Evidence-grade. Returns the audit shape plus a
    ``captions`` registry (label -> facets) so a caller sees every caption's load."""
    full = _gather_manuscript_text(_resolve_target(target))
    spans = section_spans(full)
    findings: list[dict[str, Any]] = []
    registry: list[dict[str, Any]] = []
    for m in _FLOAT_RE.finditer(full):
        env, _star, body = m.group(1), m.group(2), m.group(3)
        if env != "figure":
            continue                                   # a caption tic is a figure tic
        cap = _extract_caption(body) or ""
        cap = re.sub(r"\s+", " ", cap).strip()
        if not cap:
            continue
        lab_m = _LABEL_RE.search(body)
        label = lab_m.group(1) if lab_m else f"figure@{m.start()}"
        slug, _title, _app = section_of(m.start(), spans)
        facets = caption_facets(cap)
        registry.append({"label": label, "section": slug or "",
                         "facets": facets, "n_facets": len(facets)})
        if len(facets) >= min_facets:
            findings.append(_finding(
                label,
                f"caption carries {len(facets)} of 5 defensive facets {facets} — it "
                "has absorbed the manifest (provenance), the methods table "
                "(conventions) and the interpretation section (non-claims)",
                "keep interpretation + conditions in the caption; move provenance to "
                "the manifest and the non-claims to the interpretation section",
                "caption-defensive", quote=cap, section=slug or "",
                facets=facets, n_facets=len(facets), min_facets=min_facets))
    return _result(findings, captions=registry)


# ===========================================================================
# (b) DISCLAIMER-REPETITION — the six disclaimer classes counted document-wide
# ===========================================================================

#: The six disclaimer classes. Each pattern matches a DISCLAIMING statement (a
#: negated / scope-limiting boundary), not a bare mention of the topic — so a single
#: legitimate use of the word never counts, only the repeated boundary-restatement
#: the hold-out review flagged does. State the boundary once, label it at appearance,
#: give the full boundary in §VII.
_DISCLAIMER_CLASSES: dict[str, re.Pattern] = {
    "no-hardness": re.compile(
        r"(?:no\s+(?:worst-case\s+)?(?:np-)?hardness|neither\s+(?:asymptotic\s+)?hardness|"
        r"not\s+(?:by\s+itself\s+)?(?:a\s+)?hardness|hardness\s+of\s+any\s+kind|"
        r"does\s+not\s+(?:by\s+itself\s+)?(?:establish|settle|imply)[^.]{0,40}hardness|"
        r"establishes?\s+no[^.]{0,30}hardness|inherits?\s+no\s+(?:worst-case\s+)?"
        r"(?:np-)?hardness|never\s+a\s+hardness|growth,?\s+not\s+hardness|"
        r"neither\s+establishes\s+nor\s+rules\s+out[^.]{0,20}hardness|"
        r"no\s+hardness\s+(?:no-go|claim|argument)|makes?\s+no\s+hardness)", re.I),
    "no-advantage": re.compile(
        r"(?:no\s+(?:quantum\s+)?advantage|neither[^.]{0,40}advantage|nor\s+(?:quantum\s+)?"
        r"advantage|nor\s+an?\s+advantage|no\s+advantage\s+claim|not\s+an?\s+advantage|"
        r"(?:nothing|neither|no[a-z]*)[^.]{0,40}(?:asserts?|establish\w*)[^.]{0,20}"
        r"separation|no\s+separation|not\s+a\s+separation|makes?\s+no[^.]{0,20}advantage|"
        r"no\s+(?:quantum\s+)?speedup|not\s+a\s+speedup)", re.I),
    "no-hardware": re.compile(
        r"(?:no\s+(?:quantum\s+)?hardware\s+(?:data|counts?)|contains?\s+no\s+quantum\s+"
        r"hardware|no\s+quantum\s+hardware\s+data\s+(?:appears|exists)|not\s+hardware\s+"
        r"(?:feasibility|counts?)|no\s+statement\s+is\s+made\s+about[^.]{0,20}hardware|"
        r"needs?\s+no\s+hardware|makes?\s+no\s+hardware|not\s+a\s+hardware)", re.I),
    "exact-vs-finite-size": re.compile(
        r"(?:finite-size\s+(?:statement|observations?|compressibility|claim)|"
        r"proof\s+of\s+principle|tested\s+sizes|not\s+(?:an?\s+)?asymptotic|"
        r"asymptotic\s+scaling\s+law|no\s+asymptotic|a\s+finite-size\s+statement|"
        r"finite-window\s+statement|not\s+an\s+asymptotic\s+claim)", re.I),
    "guide-not-law": re.compile(
        r"(?:operating\s+envelope|guide,?\s+not\s+a\s+law|not\s+a\s+law|"
        r"a\s+heuristic\s+(?:guide|scale)|readable\s+(?:coupling\s+)?range|"
        r"envelope[^.]{0,20}not\s+a|indicativ\w+,?\s+not|a\s+guide\b)", re.I),
    "reference-not-certification": re.compile(
        r"(?:validation\s+reference|serves?\s+as\s+the\s+(?:validation\s+)?reference|"
        r"not\s+a\s+certification|reference,?\s+not\s+a\s+certification|"
        r"validation\s+logic|a\s+control,?\s+not|control\s+reference|"
        r"reference\s+(?:read|profile)\s+for)", re.I),
}


def disclaimer_hits(full: str) -> dict[str, list[dict[str, Any]]]:
    """``class -> [{pos, section, quote}]`` — every disclaiming statement, per class,
    located in the flattened text (its section resolved for the recurrence report)."""
    spans = section_spans(full)
    out: dict[str, list[dict[str, Any]]] = {}
    for cls, pat in _DISCLAIMER_CLASSES.items():
        hits: list[dict[str, Any]] = []
        for m in pat.finditer(full):
            slug, _title, _app = section_of(m.start(), spans)
            hits.append({"pos": m.start(), "section": slug or "",
                         "quote": m.group(0).strip()[:120]})
        out[cls] = hits
    return out


def check_disclaimer_repetition(target: Union[str, Path], *,
                                threshold: int = 3) -> dict[str, Any]:
    """DISCLAIMER-REPETITION — count each of the six disclaimer classes document-wide
    and flag every class recurring past ``threshold`` with its count and the sections
    it recurs in. State the boundary once, label it at appearance, give the full
    boundary in one place; a class stated four+ times is scattering the boundary the
    reader should meet once. Evidence-grade. Returns the audit shape plus a
    ``by_class`` table (class -> {count, sections})."""
    full = _gather_manuscript_text(_resolve_target(target))
    hits = disclaimer_hits(full)
    findings: list[dict[str, Any]] = []
    by_class: dict[str, dict[str, Any]] = {}
    for cls, hs in hits.items():
        count = len(hs)
        sections = sorted({h["section"] for h in hs if h["section"]})
        by_class[cls] = {"count": count, "sections": sections}
        if count > threshold:
            findings.append(_finding(
                f"disclaimer:{cls}",
                f"the '{cls}' disclaimer recurs {count} times across "
                f"{len(sections)} sections {sections} (> {threshold}) — state it once, "
                "label it at appearance, give the full boundary in the limitations "
                "section",
                "state the boundary once at its natural appearance and consolidate the "
                "rest into the limitations/scope section",
                "disclaimer-repetition", count=count, threshold=threshold,
                sections=sections,
                locations=[{"section": h["section"], "quote": h["quote"]} for h in hs]))
    return _result(findings, by_class=by_class)


# ===========================================================================
# (c) SENTENCE-DENSITY — a sentence carrying claim+condition+exception+status+ref
# ===========================================================================

#: Subordinate / clause-joining markers. More than two in one sentence is the
#: mechanical proxy for a sentence stacking claim + condition + exception + status +
#: forward-reference — the overloaded sentence the hold-out review wanted split.
_SUBORDINATE_MARKERS = (
    "which", "that", "where", "while", "whereas", "although", "though", "because",
    "since", "unless", "until", "whenever", "provided", "given that", "so that",
    "such that", "in order to", "rather than", "as well as", "not by itself",
    "even though", "insofar as", "to the extent",
)
_MARKER_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(re.escape(m).replace(r"\ ", r"\s+")
                            for m in _SUBORDINATE_MARKERS) + r")(?!\w)", re.I)
#: em-dash / spaced-hyphen aside — the same clause-stacking move by punctuation.
_DASH_RE = re.compile(r"\s[-–—]\s|—")

# split flattened prose into sentence-ish units on ., ?, ! followed by whitespace,
# after stripping display math / commands that carry sentence-final dots of their own.
_SENT_SPLIT_RE = re.compile(r"(?<=[.?!])\s+")


def _prose_paragraphs(full: str) -> list[tuple[int, str]]:
    """(offset, paragraph_text) for body prose paragraphs — float environments and
    display-math blocks removed so their internal punctuation never fabricates a
    sentence. Offsets index into ``full`` for section attribution."""
    # blank out floats + displayed math so we count only running prose.
    scrub = full
    for pat in (_FLOAT_RE,
                re.compile(r"\\begin\{(equation|align|multline|gather|table)\*?\}"
                           r".*?\\end\{\1\*?\}", re.DOTALL),
                re.compile(r"\\\[.*?\\\]", re.DOTALL)):
        scrub = pat.sub(lambda mm: " " * (mm.end() - mm.start()), scrub)
    out: list[tuple[int, str]] = []
    for pm in re.finditer(r"[^\n](?:.*?)(?=\n\s*\n|\Z)", scrub, re.DOTALL):
        seg = pm.group(0)
        if seg.strip():
            out.append((pm.start(), seg))
    return out


def _word_count(sentence: str) -> int:
    """Words in a sentence, math and commands stripped to a single token each so a
    long ``$...$`` or ``\\command`` does not inflate the count."""
    s = re.sub(r"\$[^$]*\$", " X ", sentence)
    s = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?", " X ", s)
    return len(re.findall(r"[A-Za-z0-9]+", s))


def check_sentence_density(target: Union[str, Path], *,
                           max_markers: int = 2, max_words: int = 40) -> dict[str, Any]:
    """SENTENCE-DENSITY — flag every prose sentence carrying more than ``max_markers``
    subordinate / dash-aside markers AND more than ``max_words`` words: the mechanical
    proxy for a sentence stacking claim + condition + exception + status + forward
    reference at once. Evidence-grade; each finding is a split candidate carrying the
    marker and word counts and the sentence quote. Returns the audit shape plus the
    ``scanned`` sentence total."""
    full = _gather_manuscript_text(_resolve_target(target))
    spans = section_spans(full)
    findings: list[dict[str, Any]] = []
    scanned = 0
    for off, para in _prose_paragraphs(full):
        cursor = off
        for sent in _SENT_SPLIT_RE.split(para):
            start = full.find(sent[:24].strip(), cursor) if sent.strip() else -1
            pos = start if start >= 0 else cursor
            cursor = pos + max(1, len(sent))
            s = sent.strip()
            if not s:
                continue
            scanned += 1
            markers = len(_MARKER_RE.findall(s)) + len(_DASH_RE.findall(s))
            words = _word_count(s)
            if markers > max_markers and words > max_words:
                slug, _title, _app = section_of(pos, spans)
                findings.append(_finding(
                    (slug or "prose"),
                    f"sentence stacks {markers} subordinate/aside markers across "
                    f"{words} words (> {max_markers} markers, > {max_words} words) — "
                    "a claim+condition+exception+status+forward-ref pile-up",
                    "split into a claim sentence and its conditions/exceptions",
                    "sentence-overloaded", quote=s, section=slug or "",
                    markers=markers, words=words))
    return _result(findings, scanned=scanned)


# ===========================================================================
# the aggregator — run all three tic detectors over one manuscript
# ===========================================================================

def run_tic_detectors(target: Union[str, Path], *,
                      disclaimer_threshold: int = 3,
                      caption_min_facets: int = 4,
                      sentence_max_markers: int = 2,
                      sentence_max_words: int = 40) -> dict[str, Any]:
    """Run the three recurring-tic detectors over one manuscript and return a combined
    evidence result ``{clean, pass, tics: {caption, disclaimer, sentence}, findings,
    counts}`` — advisory (evidence-grade), fit to ride the harnessed round evidence as
    a panel axis. A detector that RAISES is recorded as ``{error: ...}`` rather than
    dropped, never a false clean."""
    target = _resolve_target(target)
    tics: dict[str, Any] = {}

    def _run(name: str, fn):
        try:
            tics[name] = fn()
        except Exception as e:  # noqa: BLE001 — a tic crash is a loud advisory, not silence
            tics[name] = {"pass": False, "clean": False, "error": str(e),
                          "findings": [], "counts": {}}

    _run("caption", lambda: check_defensive_captions(
        target, min_facets=caption_min_facets))
    _run("disclaimer", lambda: check_disclaimer_repetition(
        target, threshold=disclaimer_threshold))
    _run("sentence", lambda: check_sentence_density(
        target, max_markers=sentence_max_markers, max_words=sentence_max_words))

    all_findings: list[dict[str, Any]] = []
    for t in tics.values():
        all_findings += t.get("findings", [])
    clean = all(t.get("pass", t.get("clean", False)) for t in tics.values())
    return {"clean": clean, "pass": clean, "tics": tics,
            "findings": all_findings, "counts": summarise(all_findings)}
