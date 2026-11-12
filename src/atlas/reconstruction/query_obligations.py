"""Finite query-obligation grammar layered over the immutable v1 compiler.

The grammar exposes syntactically requested distinctions.  It does not infer
facts, resolve arbitrary English, or treat lexical occurrence as entailment.
Unsupported attachment is explicit and the original query remains recoverable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Sequence

from . import query_plan as v1


@dataclass(frozen=True, slots=True)
class AttachmentConstraint:
    id: str
    relation: str
    member_ids: tuple[str, ...]
    status: str  # licensed | unresolved
    cue: str
    shared_text: tuple[str, ...]
    recovery_text: str


@dataclass(frozen=True, slots=True)
class ObligationPlan:
    version: str
    question: str
    status: str
    source_bindings: tuple
    dates: tuple
    context_bindings: tuple
    claims: tuple
    lexical_candidates: tuple
    evidence_obligations: tuple
    logic: tuple
    identity: tuple
    binding_alternatives: tuple
    attachments: tuple[AttachmentConstraint, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _Part:
    text: str
    span: v1.TextSpan


@dataclass(frozen=True, slots=True)
class _Decomposition:
    parts: tuple[_Part, ...]
    operator: str
    cue: str
    relation: str
    shared_text: tuple[str, ...]
    attachment_status: str = "licensed"


_CONNECTOR = re.compile(r"\b(?:and|or|versus|vs\.?|while|whereas|but)\b", re.I)
_INDEPENDENT = re.compile(
    r"\b(?:and|while|whereas)\b\s+(?=(?:what|which|when|where|who|how|why|"
    r"did|does|do|is|are|was|were|has|have|had|can|could|will|would|should)\b)", re.I)
_AUXILIARY = r"(?:am|is|are|was|were|has|have|had|do|does|did|can|could|will|would|should)"
_PRONOUN = re.compile(r"\b(?:he|she|they|it|this|that|these|those|his|her|their|its)\b", re.I)
_CAPITALIZED = re.compile(r"\b[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*\b")
_NEGATED = re.compile(r"\b(?:not|never|no)\b", re.I)
_EXCLUDED = re.compile(r"\b(?:except(?:\s+for)?|excluding|without|other\s+than)\b", re.I)


def _protected_spans(text: str, legacy: v1.QueryPlan) -> list[v1.TextSpan]:
    spans = [binding.span for binding in legacy.source_bindings]
    spans.extend(date.span for date in legacy.dates)
    for pattern in (r'"[^"\n]+"', r"'[^'\n]+'"):  # exact quoted compounds
        spans.extend(v1.TextSpan(*match.span()) for match in re.finditer(pattern, text))
    # A title-cased pair is protected only when it has an explicit compound
    # head before a following word ("Research and Development team publish").
    # Bare people such as "Alice and Bob" are not declared a compound.
    for match in re.finditer(
            r"\b[A-Z][\w'-]*\s+and\s+[A-Z][\w'-]*\s+[a-z][\w'-]+(?=\s+[a-z])", text):
        spans.append(v1.TextSpan(*match.span()))
    for match in re.finditer(r"\bbetween\s+\d+(?:\.\d+)?\s+and\s+\d+(?:\.\d+)?\b", text, re.I):
        spans.append(v1.TextSpan(*match.span()))
    month = (r"(?:January|February|March|April|May|June|July|August|September|"
             r"October|November|December)")
    for match in re.finditer(
            rf"\bbetween\s+{month}\s+20\d{{2}}\s+and\s+{month}\s+20\d{{2}}\b",
            text, re.I):
        spans.append(v1.TextSpan(*match.span()))
    return spans


def _inside(position: int, spans: Sequence[v1.TextSpan]) -> bool:
    return any(span.start <= position < span.end for span in spans)


def _trim_part(text: str, start: int, end: int) -> _Part | None:
    raw = text[start:end]
    left = len(raw) - len(raw.lstrip(" ,;:?"))
    right = len(raw.rstrip(" ,;:?"))
    if right <= left:
        return None
    span = v1.TextSpan(start + left, start + right)
    return _Part(text[span.start:span.end], span)


def _comma_alternatives(text: str, protected) -> _Decomposition | None:
    cues = [match for match in re.finditer(r"\b(?:or|versus|vs\.?)\b", text, re.I)
            if not _inside(match.start(), protected)]
    if not cues:
        return None
    cue = cues[-1]
    commas = [index for index, char in enumerate(text[:cue.start()])
              if char == "," and not _inside(index, protected)]
    if not commas:
        return None
    boundary = commas[-1]
    a = _trim_part(text, boundary + 1, cue.start())
    b = _trim_part(text, cue.end(), len(text))
    if not a or not b:
        return None
    prefix = text[:boundary].strip()
    return _Decomposition(
        (_Part(f"{prefix}: {a.text}", a.span), _Part(f"{prefix}: {b.text}", b.span)),
        "conjunction", cue.group(0), "comparison_members", (prefix,))


def _between(text: str, protected) -> _Decomposition | None:
    match = re.search(
        r"\bbetween\b\s+(?P<a>.+?)\s+\band\b\s+(?P<b>.+?)(?:,\s*(?P<tail>.+?))?\??$",
        text, re.I)
    if not match or _inside(text.casefold().find("and", match.start("a")), protected):
        return None
    a = _trim_part(text, *match.span("a")); b = _trim_part(text, *match.span("b"))
    if not a or not b:
        return None
    tail = (match.group("tail") or "").strip(" ?")
    parts = (a, b) if not tail else (
        _Part(f"{a.text}; {tail}", a.span), _Part(f"{b.text}; {tail}", b.span))
    return _Decomposition(parts, "conjunction", "between ... and",
                          "comparison_members", ((tail,) if tail else ()))


def _either_or(text: str, protected) -> _Decomposition | None:
    match = re.search(r"\beither\b\s+(?P<a>.+?)\s+\bor\b\s+(?P<b>.+?)\??$", text, re.I)
    if not match or _inside(match.start(), protected) or _inside(text.casefold().find("or", match.start("a")), protected):
        return None
    a = _trim_part(text, *match.span("a")); b = _trim_part(text, *match.span("b"))
    if not a or not b:
        return None
    prefix = text[:match.start()].strip(" ,")
    return _Decomposition(
        (_Part(f"{prefix} {a.text}".strip(), a.span),
         _Part(f"{prefix} {b.text}".strip(), b.span)),
        "disjunction", "either ... or", "explicit_alternatives", ((prefix,) if prefix else ()))


def _independent_clauses(text: str, protected) -> _Decomposition | None:
    cuts = [match for match in _INDEPENDENT.finditer(text)
            if not _inside(match.start(), protected)]
    if not cuts:
        return None
    parts = []
    start = 0
    for match in cuts:
        part = _trim_part(text, start, match.start())
        if part: parts.append(part)
        start = match.end()
    final = _trim_part(text, start, len(text))
    if final: parts.append(final)
    if len(parts) < 2:
        return None
    # Pronouns are not assigned an antecedent by this finite grammar. Repeated
    # explicit subjects remain licensed; every pronoun attachment is recoverable.
    ambiguous = any(_PRONOUN.search(part.text) for part in parts[1:])
    return _Decomposition(
        tuple(parts), "conjunction", "separately asked clauses",
        "shared_context_or_subject", (), "unresolved" if ambiguous else "licensed")


def _coordinated_objects(text: str, protected) -> _Decomposition | None:
    match = re.match(
        rf"^(?P<wh>What|Which)\s+(?P<a>.{{1,60}}?)\s+and\s+(?P<b>.{{1,60}}?)\s+"
        rf"(?P<predicate>{_AUXILIARY}\s+.+?)\??$", text, re.I)
    if not match or _inside(text.casefold().find("and", match.start("a")), protected):
        return None
    a_text, b_text = match.group("a").strip(), match.group("b").strip()
    if len(a_text.split()) > 6 or len(b_text.split()) > 6:
        return None
    # A title-cased coordination is treated as one named compound.
    if a_text[:1].isupper() and b_text[:1].isupper():
        return None
    a = _Part(f"{match.group('wh')} {a_text} {match.group('predicate')}",
              v1.TextSpan(*match.span("a")))
    b = _Part(f"{match.group('wh')} {b_text} {match.group('predicate')}",
              v1.TextSpan(*match.span("b")))
    return _Decomposition((a, b), "conjunction", "coordinated objects",
                          "shared_predicate", (match.group("predicate"),))


def _coordinated_actions(text: str, protected) -> _Decomposition | None:
    patterns = (
        re.compile(
            rf"^(?P<prefix>How many\s+.+?)\s+"
            rf"(?P<a>{_AUXILIARY}\s+.+?)\s+(?P<cue>and|or)\s+"
            rf"(?P<b>{_AUXILIARY}\s+.+?)\??$", re.I),
        re.compile(
            r"^(?P<prefix>(?:What|Which|How|When|Where)\s+"
            r"(?:did|does|do|has|have|had|can|could|will|would|should)\s+\w+)\s+"
            r"(?P<a>.+?)\s+(?P<cue>and|or)\s+(?P<b>.+?)\??$", re.I),
    )
    for pattern_index, pattern in enumerate(patterns):
        match = pattern.match(text)
        if not match or _inside(match.start("cue"), protected):
            continue
        if pattern_index == 1:
            subject = match.group("prefix").split()[-1]
            if not (subject[:1].isupper() or subject.casefold() in
                    {"i", "you", "he", "she", "we", "they"}):
                continue
        a = _trim_part(text, *match.span("a")); b = _trim_part(text, *match.span("b"))
        if not a or not b:
            continue
        prefix = match.group("prefix").strip()
        operator = "disjunction" if match.group("cue").casefold() == "or" else "conjunction"
        return _Decomposition(
            (_Part(f"{prefix} {a.text}", a.span), _Part(f"{prefix} {b.text}", b.span)),
            operator, match.group("cue"), "coordinated_actions", (prefix,))
    return None


def _but_not(text: str, protected) -> _Decomposition | None:
    match = re.search(r"\bbut\s+not\b\s+(?P<right>.+?)\??$", text, re.I)
    if not match or _inside(match.start(), protected):
        return None
    left = _trim_part(text, 0, match.start()); right = _trim_part(text, *match.span("right"))
    if not left or not right:
        return None
    return _Decomposition((left, _Part("not " + right.text, right.span)),
                          "conjunction", "but not", "contrast_polarity", (), "unresolved")


def _decompose(text: str, legacy: v1.QueryPlan) -> _Decomposition | None:
    protected = _protected_spans(text, legacy)
    for parser in (_between, _comma_alternatives, _either_or, _independent_clauses,
                   _but_not, _coordinated_actions, _coordinated_objects):
        parsed = parser(text, protected)
        if parsed is not None:
            return parsed
    return None


def _polarity(text: str) -> str:
    if _EXCLUDED.search(text):
        return "syntactic_exclusion"
    if _NEGATED.search(text):
        return "syntactic_negation"
    return "required"


def _observational_claims(claims):
    return tuple(v1.ClaimObligation(
        claim.id, claim.text,
        ("syntactic_negation" if claim.polarity == "negated"
         else "syntactic_exclusion" if claim.polarity == "excluded"
         else claim.polarity),
        claim.span) for claim in claims)


def compile_query(question: str, sources: Sequence[str] = (), *,
                  context: Sequence[v1.ContextValue] = ()) -> ObligationPlan:
    legacy = v1.compile_query(question, sources, context=context)
    text = legacy.question
    parsed = _decompose(text, legacy)
    issues = list(legacy.issues)
    attachments = []
    if parsed is None:
        unhandled = [match.group(0) for match in _CONNECTOR.finditer(text)
                     if not _inside(match.start(), _protected_spans(text, legacy))]
        status = legacy.status
        if unhandled and len(legacy.evidence_obligations) == 1:
            issues.append("unsupported attachment retained without decomposition: " + ", ".join(unhandled))
            attachments.append(AttachmentConstraint(
                "attachment:0", "unparsed_coordination", ("evidence:0",),
                "unresolved", ", ".join(unhandled), (), text))
            if status == "supported": status = "ambiguous"
        return ObligationPlan(
            "typed-query-obligations-v2", text, status, legacy.source_bindings,
            legacy.dates, legacy.context_bindings, _observational_claims(legacy.claims),
            legacy.lexical_candidates, legacy.evidence_obligations, legacy.logic,
            legacy.identity, legacy.binding_alternatives, tuple(attachments),
            tuple(dict.fromkeys(issues)))

    protected = _protected_spans(text, legacy)
    residual_connectors = []
    for part in parsed.parts:
        for match in _CONNECTOR.finditer(text, part.span.start, part.span.end):
            if not _inside(match.start(), protected):
                residual_connectors.append(match.group(0))
    if residual_connectors:
        parsed = _Decomposition(
            parsed.parts, parsed.operator, parsed.cue, parsed.relation,
            parsed.shared_text, "unresolved")
        issues.append(
            "residual coordination remains unresolved after bounded decomposition: "
            + ", ".join(residual_connectors))

    distinct_sources = {binding.canonical or binding.surface.casefold()
                        for binding in legacy.source_bindings}
    sole_source = legacy.source_bindings[0].id if len(distinct_sources) == 1 else None
    shared_publication = tuple(date.id for date in legacy.dates if date.role == "publication")
    shared_blob = " ".join(parsed.shared_text).casefold()
    shared_sources = tuple(
        binding.id for binding in legacy.source_bindings
        if binding.surface.casefold() in shared_blob
        or (binding.canonical and binding.canonical.casefold() in shared_blob))
    shared_dates = tuple(date.id for date in legacy.dates
                         if date.surface.casefold() in shared_blob)
    claims = []
    obligations = []
    for index, part in enumerate(parsed.parts):
        claim = v1.ClaimObligation(f"claim:{index}", part.text, _polarity(part.text), part.span)
        claims.append(claim)
        source_ids = tuple(binding.id for binding in legacy.source_bindings
                           if part.span.start <= binding.span.start and binding.span.end <= part.span.end)
        source_ids = tuple(dict.fromkeys((*source_ids, *shared_sources)))
        if not source_ids and sole_source is not None:
            source_ids = (sole_source,)
        local_dates = tuple(date for date in legacy.dates
                            if part.span.start <= date.span.start and date.span.end <= part.span.end)
        publication = tuple(date.id for date in local_dates if date.role == "publication")
        publication = tuple(dict.fromkeys((
            *publication, *(date_id for date_id in shared_dates
                            if next(date for date in legacy.dates if date.id == date_id).role == "publication"))))
        if not publication and len(shared_publication) == 1:
            publication = shared_publication
        event = tuple(date.id for date in local_dates if date.role != "publication")
        event = tuple(dict.fromkeys((
            *event, *(date_id for date_id in shared_dates
                      if next(date for date in legacy.dates if date.id == date_id).role != "publication"))))
        lexical = tuple(candidate.id for candidate in legacy.lexical_candidates
                        if candidate.surface.casefold() in part.text.casefold())
        obligations.append(v1.EvidenceObligation(
            f"evidence:{index}", part.text, source_ids, publication, event,
            tuple(binding.id for binding in legacy.context_bindings),
            (claim.id,), lexical, part.span))
    member_ids = tuple(obligation.id for obligation in obligations)
    logic = (v1.LogicConstraint(
        "logic:0", parsed.operator, member_ids, parsed.cue, v1.TextSpan(0, len(text))),)
    attachments.append(AttachmentConstraint(
        "attachment:0", parsed.relation, member_ids, parsed.attachment_status,
        parsed.cue, parsed.shared_text, text))
    status = legacy.status
    if parsed.attachment_status == "unresolved" and status != "unsupported":
        status = "ambiguous"
        issues.append("attachment/support relation unresolved; original query retained")
    identity = tuple(v1.IdentityConstraint(
        item.id, item.relation,
        (member_ids if set(item.member_ids) & {row.id for row in legacy.evidence_obligations}
         else item.member_ids),
        item.witness_key, item.verification, item.span)
        for item in legacy.identity)
    return ObligationPlan(
        "typed-query-obligations-v2", text, status, legacy.source_bindings,
        legacy.dates, legacy.context_bindings, tuple(claims),
        legacy.lexical_candidates, tuple(obligations), logic, identity,
        legacy.binding_alternatives, tuple(attachments), tuple(dict.fromkeys(issues)))


__all__ = ["AttachmentConstraint", "ObligationPlan", "compile_query"]
