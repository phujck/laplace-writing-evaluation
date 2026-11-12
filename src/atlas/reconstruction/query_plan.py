"""Conservative, typed compilation of English enquiries into evidence obligations.

This module is deliberately a finite grammar.  It records source/date bindings and
observable lexical demands; it does not claim to recover arbitrary English meaning.
When a binding is not licensed by the grammar, the resulting plan is ambiguous or
unsupported instead of silently becoming an unconstrained semantic query.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Iterable, Sequence


_MONTHS = {name: number for number, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"), 1)}
_DATE = re.compile(
    r"\b(" + "|".join(_MONTHS) +
    r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(20\d{2})\b", re.I)
_EVIDENCE_NOUN = r"(?:article|report|story|piece|coverage|dispatch)"
_SOURCE_WORD = r"[A-Z][\w&.'-]*(?:\s*\|\s*[A-Z][\w&.'-]*)?"
_UNKNOWN_SOURCE_PATTERNS = (
    re.compile(rf"(?P<name>{_SOURCE_WORD}(?:\s+{_SOURCE_WORD}){{0,5}})(?:'s)?\s+{_EVIDENCE_NOUN}\b"),
    re.compile(
        rf"\b{_EVIDENCE_NOUN}\s+(?:published\s+)?(?:from|by|in)\s+"
        rf"(?:an?\s+)?(?P<name>{_SOURCE_WORD}(?:\s+{_SOURCE_WORD}){{0,5}})"
        rf"(?=\s+(?:about|concerning|discussing|involving|on|published|dated|saying|that|which|and|while|whereas)|[,;?.]|$)"
    ),
)
_CLAUSE_CONNECTOR = re.compile(r"\b(?:while|whereas|than)\b", re.I)
_AND = re.compile(r"\band\b", re.I)
_ONE_OTHER = re.compile(
    r"(?:\bwith\s+)?\bone\b\s+(?P<one>.+?)\s+(?:and|while)\s+"
    r"(?:the\s+)?\bother\b\s+(?P<other>.+?)(?=[?.]|$)", re.I)
_NEGATION = re.compile(r"\b(?:does\s+not|did\s+not|is\s+not|are\s+not|was\s+not|were\s+not|never|no)\b", re.I)
_EXCLUSION = re.compile(r"\b(?:excluding|except(?:\s+for)?|other\s+than|without|not\s+including)\b", re.I)
_QUESTION_BOILERPLATE = {
    "after", "according", "among", "between", "considering", "does", "did",
    "how", "in", "is", "on", "the", "what", "when", "where", "which", "who", "why",
}


@dataclass(frozen=True, slots=True)
class TextSpan:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class SourceBinding:
    id: str
    surface: str
    canonical: str | None
    resolution: str  # resolved | unavailable
    span: TextSpan


@dataclass(frozen=True, slots=True)
class DateObligation:
    id: str
    surface: str
    iso_date: str
    role: str  # publication | event | unknown
    source_binding_id: str | None
    span: TextSpan


@dataclass(frozen=True, slots=True)
class ContextValue:
    """A dataset-supplied exact or unresolved coordinate; no domain is hardcoded."""
    namespace: str
    field: str
    value: str | None
    role: str = "exact"
    scope: str = "question"
    binding_key: str | None = None


@dataclass(frozen=True, slots=True)
class ContextBinding:
    id: str
    namespace: str
    field: str
    value: str | None
    role: str
    scope: str
    binding_key: str | None
    resolution: str  # provided | unresolved


@dataclass(frozen=True, slots=True)
class ClaimObligation:
    id: str
    text: str
    polarity: str  # required | negated | excluded
    span: TextSpan


@dataclass(frozen=True, slots=True)
class LexicalCandidate:
    id: str
    surface: str
    kind: str  # named_entity | rare_term
    source_binding_id: str | None
    asserted_semantic_truth: bool
    span: TextSpan


@dataclass(frozen=True, slots=True)
class EvidenceObligation:
    id: str
    facet_text: str
    source_binding_ids: tuple[str, ...]
    publication_date_ids: tuple[str, ...]
    event_date_ids: tuple[str, ...]
    context_binding_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    lexical_candidate_ids: tuple[str, ...]
    span: TextSpan


@dataclass(frozen=True, slots=True)
class LogicConstraint:
    id: str
    operator: str  # conjunction | disjunction | unknown
    member_ids: tuple[str, ...]
    cue: str
    span: TextSpan


@dataclass(frozen=True, slots=True)
class IdentityConstraint:
    id: str
    relation: str  # same_article | different_article
    member_ids: tuple[str, ...]
    witness_key: str
    verification: str  # required_unresolved | provided
    span: TextSpan


@dataclass(frozen=True, slots=True)
class BindingAlternative:
    id: str
    assignments: tuple[tuple[tuple[str, str], ...], ...]
    cue: str
    span: TextSpan


@dataclass(frozen=True, slots=True)
class QueryPlan:
    version: str
    question: str
    status: str  # supported | ambiguous | unsupported
    source_bindings: tuple[SourceBinding, ...]
    dates: tuple[DateObligation, ...]
    context_bindings: tuple[ContextBinding, ...]
    claims: tuple[ClaimObligation, ...]
    lexical_candidates: tuple[LexicalCandidate, ...]
    evidence_obligations: tuple[EvidenceObligation, ...]
    logic: tuple[LogicConstraint, ...]
    identity: tuple[IdentityConstraint, ...]
    binding_alternatives: tuple[BindingAlternative, ...]
    issues: tuple[str, ...]

    def to_dict(self) -> dict:
        """Return a JSON-safe, stable representation for downstream batching."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _Anchor:
    start: int
    end: int
    kind: str
    identifier: str


def _aliases(source: str) -> set[str]:
    values = {source.casefold().strip()}
    if "|" in source:
        values.add(source.split("|", 1)[0].casefold().strip())
    if source.casefold().startswith("the "):
        values.add(source[4:].casefold().strip())
    return {value for value in values if len(value) >= 2}


def _overlaps(span: TextSpan, spans: Iterable[TextSpan]) -> bool:
    return any(span.start < other.end and other.start < span.end for other in spans)


def _source_bindings(text: str, sources: Sequence[str]) -> tuple[SourceBinding, ...]:
    lower = text.casefold()
    found: list[tuple[int, int, str, str | None, str]] = []
    for source in sources:
        for alias in _aliases(source):
            for match in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", lower):
                found.append((match.start(), match.end(), text[match.start():match.end()], source, "resolved"))
    # Prefer the longest known name at an identical position and reject every overlap.
    found.sort(key=lambda row: (row[0], -(row[1] - row[0]), row[3] or ""))
    clean: list[tuple[int, int, str, str | None, str]] = []
    for row in found:
        if not any(row[0] < kept[1] and kept[0] < row[1] for kept in clean):
            clean.append(row)

    known_spans = [TextSpan(row[0], row[1]) for row in clean]
    for pattern in _UNKNOWN_SOURCE_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span("name")
            span = TextSpan(start, end)
            if _overlaps(span, known_spans):
                continue
            surface = match.group("name").strip().removesuffix("'s").strip()
            # Leading determiners are syntax, not part of the outlet name.
            surface = re.sub(r"^(?:A|An)\s+", "", surface)
            if not surface or surface.casefold() in _QUESTION_BOILERPLATE:
                continue
            clean.append((start, end, surface, None, "unavailable"))
            known_spans.append(span)

    clean.sort(key=lambda row: (row[0], row[1]))
    return tuple(SourceBinding(f"source:{index}", surface, canonical, resolution,
                               TextSpan(start, end))
                 for index, (start, end, surface, canonical, resolution) in enumerate(clean))


def _date_role(text: str, start: int, end: int) -> str:
    before = text[max(0, start - 80):start]
    after = text[end:min(len(text), end + 45)]
    if re.search(rf"\b{_EVIDENCE_NOUN}\b(?:\s+(?:published|dated|released|posted))?\s*(?:on\s+)?$", before, re.I):
        return "publication"
    if re.match(rf"\s*,?\s*{_EVIDENCE_NOUN}\b", after, re.I):
        return "publication"
    if re.search(r"\b(?:published|dated|released|posted)\s+(?:on\s+)?$", before, re.I):
        return "publication"
    if re.search(rf"\b{_EVIDENCE_NOUN}\s+(?:from|by)\s+[^,;?]{{1,60}}\s+on\s+$", before, re.I):
        return "publication"
    if re.search(r"\b(?:occurred|happened|began|ended|event|attack|game|meeting)\s+(?:on\s+)?$", before, re.I):
        return "event"
    # A naked date is observable, but its metadata role is not invented.
    return "unknown"


def _nearest_source(date_span: TextSpan, bindings: Sequence[SourceBinding], text: str) -> str | None:
    if not bindings:
        return None
    ranked = sorted(bindings, key=lambda binding: min(abs(date_span.start - binding.span.end),
                                                       abs(binding.span.start - date_span.end)))
    nearest = ranked[0]
    gap_start, gap_end = sorted((date_span.start, nearest.span.end))
    gap = text[gap_start:gap_end]
    if len(gap) <= 100 and not re.search(r"[;?]|\b(?:while|whereas|than)\b", gap, re.I):
        return nearest.id
    if len({binding.canonical or binding.surface.casefold() for binding in bindings}) == 1:
        return nearest.id
    return None


def _dates(text: str, bindings: Sequence[SourceBinding]) -> tuple[DateObligation, ...]:
    rows = []
    for index, match in enumerate(_DATE.finditer(text)):
        iso = f"{int(match[3]):04d}-{_MONTHS[match[1].casefold()]:02d}-{int(match[2]):02d}"
        span = TextSpan(match.start(), match.end())
        role = _date_role(text, match.start(), match.end())
        rows.append(DateObligation(f"date:{index}", match.group(0), iso, role,
                                   _nearest_source(span, bindings, text), span))
    return tuple(rows)


def _anchors(bindings: Sequence[SourceBinding], dates: Sequence[DateObligation]) -> list[_Anchor]:
    result = [_Anchor(binding.span.start, binding.span.end, "source", binding.id)
              for binding in bindings]
    result += [_Anchor(date.span.start, date.span.end, "date", date.id)
               for date in dates if date.role == "publication"]
    return sorted(result, key=lambda item: (item.start, item.end))


def _split_spans(text: str, anchors: Sequence[_Anchor]) -> list[TextSpan]:
    cuts: list[tuple[int, int]] = []
    # Select one defensible boundary between each adjacent pair of anchors.  A
    # global "split every and" rule destroys coordinated noun phrases inside a
    # source clause ("sleep quality and brain recovery") and outlet names.
    for left, right in zip(anchors, anchors[1:]):
        if left.end >= right.start:
            continue
        gap = text[left.end:right.start]
        # "Source A and Source B" is a shared source list, not evidence that
        # the surrounding claim has two different semantic clauses.
        if (left.kind == right.kind == "source" and
                re.fullmatch(r"\s*,?\s*(?:and|or)\s+", gap, re.I)):
            continue
        strong = [match for match in _CLAUSE_CONNECTOR.finditer(gap)
                  if not (match.group(0).casefold() == "than" and
                          re.search(r"\bother\s*$", gap[:match.start()], re.I))]
        if strong:
            chosen = strong[-1]
            cuts.append((left.end + chosen.start(), left.end + chosen.end()))
            continue
        coordinated = list(_AND.finditer(gap))
        if coordinated:
            chosen = coordinated[-1]
            cuts.append((left.end + chosen.start(), left.end + chosen.end()))
    cuts = sorted(set(cuts))
    spans: list[TextSpan] = []
    start = 0
    for cut_start, cut_end in cuts:
        if cut_start > start:
            spans.append(TextSpan(start, cut_start))
        start = cut_end
    if start < len(text):
        spans.append(TextSpan(start, len(text)))
    trimmed = []
    for span in spans:
        raw = text[span.start:span.end]
        left = len(raw) - len(raw.lstrip(" ,;:?"))
        right = len(raw.rstrip(" ,;:?"))
        if right > left:
            trimmed.append(TextSpan(span.start + left, span.start + right))
    return trimmed or [TextSpan(0, len(text))]


def _span_contains(outer: TextSpan, inner: TextSpan) -> bool:
    return outer.start <= inner.start and inner.end <= outer.end


def _claim(text: str, span: TextSpan, index: int) -> ClaimObligation:
    value = text[span.start:span.end].strip()
    polarity = "excluded" if _EXCLUSION.search(value) else "negated" if _NEGATION.search(value) else "required"
    return ClaimObligation(f"claim:{index}", value, polarity, span)


def _lexical_candidates(text: str, bindings: Sequence[SourceBinding]) -> tuple[LexicalCandidate, ...]:
    blocked = [binding.span for binding in bindings]
    candidates: list[tuple[int, int, str, str]] = []
    entity = re.compile(r"\b[A-Z][\w'-]*(?:\s+(?:[A-Z][\w'-]*|Inc\.|Corp\.|Ltd\.))+")
    rare = re.compile(r"\b(?:[A-Z]{2,}[A-Z0-9-]*|[A-Za-z]+(?:-[A-Za-z0-9]+)+|[A-Za-z]*\d[A-Za-z0-9-]*)\b")
    for match in entity.finditer(text):
        span = TextSpan(*match.span())
        if not _overlaps(span, blocked) and match.group(0).split()[0].casefold() not in _QUESTION_BOILERPLATE:
            candidates.append((*match.span(), match.group(0), "named_entity"))
    for match in rare.finditer(text):
        span = TextSpan(*match.span())
        if not _overlaps(span, blocked) and not any(span.start < row[1] and row[0] < span.end for row in candidates):
            candidates.append((*match.span(), match.group(0), "rare_term"))
    candidates.sort(key=lambda row: (row[0], row[1]))
    out = []
    for index, (start, end, surface, kind) in enumerate(candidates):
        nearest = _nearest_source(TextSpan(start, end), bindings, text)
        out.append(LexicalCandidate(f"lexical:{index}", surface, kind, nearest, False,
                                    TextSpan(start, end)))
    return tuple(out)


def _context_bindings(values: Sequence[ContextValue]) -> tuple[ContextBinding, ...]:
    bindings = []
    for index, value in enumerate(values):
        if not isinstance(value, ContextValue):
            raise TypeError("context values must be ContextValue instances")
        if not value.namespace.strip() or not value.field.strip():
            raise ValueError("context namespace and field must be nonempty")
        resolution = "provided" if value.value is not None and str(value.value).strip() else "unresolved"
        bindings.append(ContextBinding(
            f"context:{index}", value.namespace, value.field, value.value,
            value.role, value.scope, value.binding_key, resolution))
    return tuple(bindings)


def _one_other_plan(text: str, match: re.Match[str], bindings: Sequence[SourceBinding],
                    dates: Sequence[DateObligation], lexical: Sequence[LexicalCandidate],
                    context: Sequence[ContextBinding]):
    claim_spans = [TextSpan(*match.span("one")), TextSpan(*match.span("other"))]
    claims = tuple(_claim(text, span, i) for i, span in enumerate(claim_spans))
    obligations = []
    for i, (span, claim) in enumerate(zip(claim_spans, claims)):
        lexical_ids = tuple(item.id for item in lexical if _span_contains(span, item.span))
        obligations.append(EvidenceObligation(
            f"evidence:{i}", claim.text, (), (), (), tuple(item.id for item in context),
            (claim.id,), lexical_ids, span))
    alternatives: tuple[BindingAlternative, ...] = ()
    issues = []
    if len(bindings) == 2:
        assignments = (
            ((obligations[0].id, bindings[0].id), (obligations[1].id, bindings[1].id)),
            ((obligations[0].id, bindings[1].id), (obligations[1].id, bindings[0].id)),
        )
        alternatives = (BindingAlternative("alternative:0", assignments,
                                           "one ... other has no licensed alignment",
                                           TextSpan(*match.span())),)
        issues.append("ambiguous one/other source alignment retained as two alternatives")
    else:
        issues.append("one/other construction does not have exactly two source bindings")
    logic = (LogicConstraint("logic:0", "conjunction", tuple(o.id for o in obligations),
                             "one ... other", TextSpan(*match.span())),)
    return claims, tuple(obligations), logic, alternatives, tuple(issues)


def compile_query(question: str, sources: Sequence[str] = (), *,
                  context: Sequence[ContextValue] = ()) -> QueryPlan:
    """Compile a question without corpus traversal, embeddings, or answer access.

    Known source names are resolved against ``sources``.  A syntactically explicit
    source absent from that vocabulary is retained with ``resolution=unavailable``.
    Publication dates alone are eligible for exact metadata conditioning; event and
    unknown-role dates remain semantic evidence obligations.
    """
    text = question.strip()
    context_bindings = _context_bindings(context)
    if not text:
        return QueryPlan(
            version="typed-query-plan-v1", question=text, status="unsupported",
            source_bindings=(), dates=(), context_bindings=context_bindings, claims=(),
            lexical_candidates=(), evidence_obligations=(), logic=(), identity=(),
            binding_alternatives=(), issues=("empty enquiry",))
    bindings = _source_bindings(text, tuple(sources))
    dates = _dates(text, bindings)
    lexical = _lexical_candidates(text, bindings)
    issues: list[str] = []

    one_other = _ONE_OTHER.search(text)
    if one_other:
        claims, obligations, logic, alternatives, local_issues = _one_other_plan(
            text, one_other, bindings, dates, lexical, context_bindings)
        issues.extend(local_issues)
    else:
        spans = _split_spans(text, _anchors(bindings, dates))
        claims = tuple(_claim(text, span, index) for index, span in enumerate(spans))
        obligations_list = []
        distinct_sources = {binding.canonical or binding.surface.casefold() for binding in bindings}
        sole_binding = bindings[0].id if len(distinct_sources) == 1 and bindings else None
        for index, (span, claim) in enumerate(zip(spans, claims)):
            source_ids = tuple(binding.id for binding in bindings if _span_contains(span, binding.span))
            if not source_ids and sole_binding is not None:
                source_ids = (sole_binding,)
            local_dates = tuple(date for date in dates if _span_contains(span, date.span))
            publication = tuple(date.id for date in local_dates if date.role == "publication")
            event = tuple(date.id for date in local_dates if date.role != "publication")
            lexical_ids = tuple(item.id for item in lexical if _span_contains(span, item.span))
            obligations_list.append(EvidenceObligation(
                f"evidence:{index}", claim.text, source_ids, publication, event,
                tuple(item.id for item in context_bindings), (claim.id,), lexical_ids, span))
        obligations = tuple(obligations_list)
        alternatives = ()
        logic_list = []
        if len(obligations) > 1:
            operator = "disjunction" if re.search(r"\beither\b.+\bor\b", text, re.I | re.S) else "conjunction"
            cue = "either ... or" if operator == "disjunction" else "separated clauses"
            logic_list.append(LogicConstraint("logic:0", operator, tuple(o.id for o in obligations),
                                              cue, TextSpan(0, len(text))))
        if not logic_list:
            disjunction = re.search(r"\b(?:either\b.+?\bor|or)\b", text, re.I | re.S)
            if disjunction:
                logic_list.append(LogicConstraint(
                    "logic:0", "disjunction", tuple(claim.id for claim in claims),
                    disjunction.group(0), TextSpan(*disjunction.span())))
            elif len(bindings) > 1 and len(obligations) == 1:
                logic_list.append(LogicConstraint(
                    "logic:0", "conjunction", tuple(binding.id for binding in bindings),
                    "multiple required source bindings", TextSpan(0, len(text))))
        logic = tuple(logic_list)

    identity: list[IdentityConstraint] = []
    same = re.search(
        r"\b(?:the\s+)?same(?:\s+(?!article\b|report\b|story\b|piece\b)[\w&|.'-]+){0,6}"
        r"\s+(?:article|report|story|piece)\b", text, re.I)
    different = re.search(r"\b(?:a\s+)?different\s+(?:article|report|story|piece)\b", text, re.I)
    if same:
        identity.append(IdentityConstraint("identity:0", "same_article",
                                           tuple(o.id for o in obligations), "theta:article:0",
                                           "required_unresolved", TextSpan(*same.span())))
    if different:
        identity.append(IdentityConstraint(f"identity:{len(identity)}", "different_article",
                                           tuple(o.id for o in obligations), "theta:article:0",
                                           "required_unresolved", TextSpan(*different.span())))
    same_entity = re.search(r"\b(?:the\s+)?same\s+(?:person|company|organisation|organization|entity)\b", text, re.I)
    if same_entity:
        identity.append(IdentityConstraint(f"identity:{len(identity)}", "same_entity",
                                           tuple(o.id for o in obligations), "theta:entity:0",
                                           "required_unresolved", TextSpan(*same_entity.span())))

    unavailable = [binding for binding in bindings if binding.resolution == "unavailable"]
    unknown_dates = [date for date in dates if date.role == "unknown"]
    unresolved_context = [item for item in context_bindings if item.resolution == "unresolved"]
    if unavailable:
        issues.extend(f"requested source unavailable in corpus vocabulary: {binding.surface}"
                      for binding in unavailable)
    if unknown_dates:
        issues.extend(f"date role is not syntactically licensed: {date.surface}"
                      for date in unknown_dates)
        logic = logic + tuple(
            LogicConstraint(f"logic:{len(logic) + index}", "unknown", (date.id,),
                            "publication/event role unresolved", date.span)
            for index, date in enumerate(unknown_dates)
        )
    if unresolved_context:
        issues.extend(f"provided context binding is unresolved: {item.namespace}.{item.field}"
                      for item in unresolved_context)
        logic = logic + tuple(
            LogicConstraint(f"logic:{len(logic) + index}", "unknown", (item.id,),
                            "external context value unresolved", TextSpan(0, len(text)))
            for index, item in enumerate(unresolved_context)
        )
    if unavailable:
        status = "unsupported"
    elif alternatives or unresolved_context:
        status = "ambiguous"
    elif not obligations:
        status = "unsupported"
    elif any(len(o.source_binding_ids) == 0 for o in obligations) and len(bindings) > 1:
        status = "ambiguous"
        issues.append("at least one clause cannot be bound uniquely to the mentioned sources")
    else:
        status = "supported"

    return QueryPlan(
        version="typed-query-plan-v1", question=text, status=status,
        source_bindings=bindings, dates=dates, context_bindings=context_bindings,
        claims=claims, lexical_candidates=lexical, evidence_obligations=obligations,
        logic=logic, identity=tuple(identity), binding_alternatives=alternatives,
        issues=tuple(dict.fromkeys(issues)))


