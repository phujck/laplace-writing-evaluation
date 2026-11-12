"""witness.py - B.4: the mechanical witness check, and failing closed.

Every row and every relation names a ``witness_predicate_id`` in this frozen registry. A
predicate is a pure function of (the bytes at the witness address, the declared field values,
the declaration) - deterministic, no model, no network, no randomness. Admission runs it at mint
time; re-verification re-runs it over the stored bytes and must agree.

Failing closed, in the clause's own words: a candidate whose check returns False "is NOT stored,
is NOT downgraded to a weaker kind, and is NOT retried with a looser predicate". It is counted
as a refused proposal with its extractor and rung. There is no third outcome, so there is no
place for the fallback the charter's forbidden move 2 is about.

The predicates here are the rung-(a) family. Each answers one question mechanically:

``surfaces_located@v1``   do the row's declared surface fields actually occur in its witness
                          bytes? Principal fields ('self') are matched through the surface set
                          schema, so 'I' counts in a user turn and 'you' in an assistant turn.
``json_member_equals@v1`` does the witness span decode as JSON whose named members equal the
                          row's declared field values?
``spans_nest@v1``         for a structural relation, does the witness pair stand in the declared
                          byte relation (the child's range inside the parent's, or two ranges
                          adjacent in their parent's declared order)?
``typed_field_predicate@v1`` for a relation derived from declared fields (the toy's ``corrects``),
                          does the declared boolean still hold over the endpoints' fields, and
                          are those fields still located in their own witness bytes?
``link_member_equals@v1`` for a link relation, does the source item's named JSON member decode
                          to exactly the target row's declared id?

Host cost. A check reads bytes, so it is O(witness bytes) per candidate and the whole pass is
O(admitted bytes) - that is the dominant host cost of ingestion and it is measured in the
packet report rather than hidden. It is not a numeric-core loop: no tensor is touched here.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from .content_blob import ContentBlobStore
from .errors import UnknownPredicate
from .spans import SpanTable

__all__ = ["WitnessCandidate", "WitnessPredicate", "PREDICATES", "register_predicate",
           "check_candidates", "tokens_of", "phrase_present"]

# Host normalisation, the same shape as reconstruction/extension/lexical_index.py:28-34
# (NFKC + casefold + a Unicode word regex). Reused deliberately: two different notions of "the
# same surface" in one engine is how an anchor silently stops resolving.
_WORD = re.compile(r"\w+", re.UNICODE)


def tokens_of(text: str) -> tuple[str, ...]:
    """NFKC-normalised, casefolded word tokens. Complexity: O(len(text))."""
    return tuple(_WORD.findall(unicodedata.normalize("NFKC", text).casefold()))


def phrase_present(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """Is ``needle`` a contiguous subsequence of ``haystack``? O(len(haystack) * len(needle)).

    Token-level, never substring: a substring test would find 'Ana' inside 'Banana' and mint an
    anchor to a row that never named her.
    """
    n = len(needle)
    if n == 0:
        return False
    first = needle[0]
    for i in range(len(haystack) - n + 1):
        if haystack[i] == first and tuple(haystack[i:i + n]) == tuple(needle):
            return True
    return False


_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})|\\(.)")
_SHORT = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", '"': '"', "\\": "\\", "/": "/"}


def _unescape(raw: str) -> str:
    """Apply JSON's own escape grammar to a FRAGMENT of a document. O(len(raw)).

    ``json.loads`` cannot be used here because the witness address may point at part of a string
    (no quotes) or at a whole object (inner quotes of its own). What is needed is only the
    character-level grammar, and applying it to either shape is what stops a name written as
    ``\\u2013`` being refused for a reason that has nothing to do with whether it is located.
    """
    return _ESCAPE.sub(
        lambda match: (chr(int(match.group(1), 16)) if match.group(1) is not None
                       else _SHORT.get(match.group(2), match.group(2))), raw)


@dataclass(frozen=True, slots=True)
class WitnessCandidate:
    """One proposed row or relation, before admission."""

    fields: Mapping[str, Any]
    spans: tuple[int, ...]                       # span ordinals; one for a row, 1..m for an edge
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WitnessPredicate:
    predicate_id: str
    version: str
    check: Callable[[ContentBlobStore, SpanTable, Sequence[WitnessCandidate], Mapping[str, Any]],
                    list[bool]]
    doc: str = ""


PREDICATES: dict[str, WitnessPredicate] = {}

# A member that is present but cannot be parsed by its declared rule. Never equal to anything.
_PARSE_FAILED = object()

# Declared value parsers: a surface in the bytes, and the typed value the declaration says it
# denotes. Registered here so a predicate can compare a TYPED field against a surface without a
# dataset's parsing rule leaking into a generic predicate.
VALUE_PARSERS: dict[str, Any] = {}


def register_parser(parser_id: str, parser: Callable[[Any], Any]) -> None:
    VALUE_PARSERS[parser_id] = parser


def register_predicate(predicate: WitnessPredicate) -> WitnessPredicate:
    PREDICATES[predicate.predicate_id] = predicate
    return predicate


def check_candidates(predicate_id: str, blobs: ContentBlobStore, spans: SpanTable,
                     candidates: Sequence[WitnessCandidate],
                     options: Mapping[str, Any] | None = None) -> list[bool]:
    """Run a registry predicate over a batch. Refuses an unregistered id (B.4, B.9)."""
    predicate = PREDICATES.get(predicate_id)
    if predicate is None:
        raise UnknownPredicate("witness predicate is not in the frozen registry",
                               predicate_id=predicate_id, registered=sorted(PREDICATES))
    if not candidates:
        return []
    return predicate.check(blobs, spans, candidates, options or {})


def _bytes_of(blobs: ContentBlobStore, spans: SpanTable, span_ord: int) -> bytes:
    handle, start, end = spans.address(span_ord)
    return blobs.read(handle, start, end)


def _text_of(blobs: ContentBlobStore, spans: SpanTable, span_ord: int) -> str:
    return _bytes_of(blobs, spans, span_ord).decode("utf-8", "replace")


# --------------------------------------------------------------- surfaces_located@v1
def _surfaces_located(blobs, spans, candidates, options) -> list[bool]:
    """Every declared surface field of the row occurs as a token phrase in its witness bytes.

    ``options`` carries ``must_appear`` (the columns checked), ``principals`` (field values that
    denote a declared principal rather than a literal surface), ``principal_surfaces``
    (condition -> surfaces, from the surface set schema) and ``condition_field`` (the column
    whose value selects the condition - ``speaker`` for a transcript).
    """
    must_appear: tuple[str, ...] = tuple(options.get("must_appear", ()))
    principals: frozenset[str] = frozenset(options.get("principals", ()))
    principal_surfaces: Mapping[str, tuple[str, ...]] = options.get("principal_surfaces", {})
    condition_field: str | None = options.get("condition_field")
    strip_json_string: bool = bool(options.get("strip_json_string", False))
    # ``decode_escapes``: the witness address points INSIDE a JSON string, so its bytes may be
    # the escape form of the character ("\\u0531" for Ա). Unescaping by the container's own
    # grammar before locating the surface is the difference between a check and a mojibake test;
    # without it every non-Latin name in the corpus is refused for the wrong reason.
    decode_escapes: bool = bool(options.get("decode_escapes", False))
    verdicts: list[bool] = []
    cache: dict[int, tuple[str, ...]] = {}
    for candidate in candidates:
        span_ord = int(candidate.spans[0])
        witness = cache.get(span_ord)
        if witness is None:
            raw = _text_of(blobs, spans, span_ord)
            if strip_json_string and raw.startswith('"') and raw.endswith('"'):
                raw = json.loads(raw)
            elif decode_escapes and "\\" in raw:
                raw = _unescape(raw)
            witness = tokens_of(raw)
            cache[span_ord] = witness
        ok = True
        for column in must_appear:
            value = candidate.fields.get(column)
            if value is None:
                continue                                  # a null field asserts nothing
            text = str(value)
            if text in principals:
                condition = (f"{condition_field}={candidate.fields.get(condition_field)}"
                             if condition_field else "*")
                options_for_principal = principal_surfaces.get(condition)
                if options_for_principal is None:
                    ok = False                            # E.0: refuse rather than guess
                    break
                if not any(phrase_present(witness, tokens_of(surface))
                           for surface in options_for_principal):
                    ok = False
                    break
                continue
            if not phrase_present(witness, tokens_of(text)):
                ok = False
                break
        verdicts.append(ok)
    return verdicts


register_predicate(WitnessPredicate(
    "surfaces_located@v1", "1", _surfaces_located,
    doc="row's declared surface fields are located as token phrases in its witness bytes"))


# ------------------------------------------------------------- json_member_equals@v1
def _json_member_equals(blobs, spans, candidates, options) -> list[bool]:
    """The witness span decodes as JSON whose named members equal the row's declared values.

    ``options['members']`` maps a column name to the JSON member path (a tuple of keys) inside
    the witness value. ``options['coerce']`` names columns compared after a declared coercion
    (``'str'`` for an id written as a number, ``'json'`` for a list compared structurally, or a
    parser id from ``VALUE_PARSERS`` for a surface the declaration types by a declared rule).
    ``options['spans_at']`` additionally requires a ``span_ref`` column to address EXACTLY the
    bytes of a named member - the check that a stored span really is the text it claims.
    """
    members: Mapping[str, tuple[str, ...]] = options.get("members", {})
    coerce: Mapping[str, str] = options.get("coerce", {})
    spans_at: Mapping[str, tuple[str, ...]] = options.get("spans_at", {})
    verdicts: list[bool] = []
    for candidate in candidates:
        raw = _bytes_of(blobs, spans, int(candidate.spans[0]))
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            verdicts.append(False)
            continue
        ok = True
        for column, path in members.items():
            declared = candidate.fields.get(column)
            found = _at_path(value, path)
            rule = coerce.get(column)
            if rule == "str" and found is not None:
                found = str(found)
            elif rule in VALUE_PARSERS and found is not None:
                try:
                    found = VALUE_PARSERS[rule](found)
                except (ValueError, TypeError):
                    # A member that is PRESENT but unparseable is not the same as an absent one.
                    # It must not compare equal to a null declared field, or a row whose typed
                    # date could not be read would be admitted with a silent null (B.4).
                    found = _PARSE_FAILED
            if declared is None:
                ok = found is None
            elif rule == "json":
                ok = json.dumps(found, sort_keys=True) == str(declared)
            else:
                ok = found == declared
            if not ok:
                break
        if ok:
            for column, path in spans_at.items():
                span_ord = candidate.fields.get(column)
                if span_ord is None:
                    ok = False
                    break
                try:
                    quoted = _bytes_of(blobs, spans, int(span_ord)).decode("utf-8")
                    ok = json.loads(quoted) == _at_path(value, path)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    ok = False
                if not ok:
                    break
        verdicts.append(ok)
    return verdicts


def _at_path(value: Any, path: Sequence[str]) -> Any:
    for key in path:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


register_predicate(WitnessPredicate(
    "json_member_equals@v1", "1", _json_member_equals,
    doc="row's declared fields equal the named JSON members of its witness value"))


# --------------------------------------------------------------------- spans_nest@v1
def _spans_nest(blobs, spans, candidates, options) -> list[bool]:
    """A structural relation's witness pair stands in the declared byte relation.

    ``options['relation']`` is 'inside' (the source span lies within the target span) or
    'disjoint_ordered' (the two spans do not overlap and the source begins after the target,
    which is what ``follows`` means at the byte level for an ordered container).
    """
    mode = options.get("relation", "inside")
    verdicts: list[bool] = []
    table = spans.columns
    for candidate in candidates:
        if len(candidate.spans) < 2:
            verdicts.append(False)
            continue
        source = table[int(candidate.spans[0])].tolist()
        target = table[int(candidate.spans[1])].tolist()
        if source[0] != target[0]:                     # different blobs: not a structural pair
            verdicts.append(False)
            continue
        if mode == "inside":
            verdicts.append(target[1] <= source[1] and source[2] <= target[2])
        else:
            verdicts.append(target[2] <= source[1])
    return verdicts


register_predicate(WitnessPredicate(
    "spans_nest@v1", "1", _spans_nest,
    doc="structural relation: the witness spans nest, or are disjoint in the declared order"))


# ---------------------------------------------------------------- span_in_witness@v1
def _span_in_witness(blobs, spans, candidates, options) -> list[bool]:
    """Every declared ``span_ref`` column addresses bytes inside the row's witness span.

    The predicate a row needs when its container has no object wrapper to compare members
    against - a QASPER paragraph is a bare string inside an array, so ``json_member_equals@v1``
    has no member to name. What CAN be checked mechanically is the addressing itself: the span
    the row stores must lie in the same blob as its witness, inside it, and (where
    ``decodes_as='json_string'``) decode as a JSON string. An off-by-one in a byte offset breaks
    the quoting and the row is refused, which is how an addressing bug becomes a refusal rather
    than a span that silently points at the wrong text.

    ``options['spans']`` names the columns checked; ``options['decodes_as']`` is 'json_string'
    or absent. Complexity: O(bytes of the named spans).
    """
    columns: tuple[str, ...] = tuple(options.get("spans", ()))
    decodes_as: str | None = options.get("decodes_as")
    table = spans.columns
    verdicts: list[bool] = []
    for candidate in candidates:
        witness = table[int(candidate.spans[0])].tolist()
        ok = True
        for column in columns:
            value = candidate.fields.get(column)
            if value is None:
                ok = False
                break
            row = table[int(value)].tolist()
            if row[0] != witness[0] or row[1] < witness[1] or row[2] > witness[2]:
                ok = False
                break
            if decodes_as == "json_string":
                try:
                    decoded = json.loads(_bytes_of(blobs, spans, int(value)).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    ok = False
                    break
                if not isinstance(decoded, str):
                    ok = False
                    break
        verdicts.append(ok)
    return verdicts


register_predicate(WitnessPredicate(
    "span_in_witness@v1", "1", _span_in_witness,
    doc="the row's declared span columns address bytes inside its witness span, and decode"))


# ------------------------------------------------------------ typed_field_predicate@v1
def _typed_field_predicate(blobs, spans, candidates, options) -> list[bool]:
    """A relation derived from declared fields: the declared boolean still holds.

    ``options['equal_fields']`` must agree between the endpoints, ``options['field_values']``
    fixes a column to a literal value on each side, and ``options['order_field']`` requires the
    source's value to exceed the target's. Every operand is a DECLARED column of a row that has
    already passed its own witness check, so no new bytes are trusted here.
    """
    equal_fields: tuple[str, ...] = tuple(options.get("equal_fields", ()))
    source_values: Mapping[str, Any] = options.get("source_values", {})
    target_values: Mapping[str, Any] = options.get("target_values", {})
    order_field: str | None = options.get("order_field")
    # ``reverse_order_field``: the same declared comparison with the source on the EARLIER side.
    # ``supersedes`` reads later-over-earlier and ``precedes`` reads earlier-before-later; both
    # are one declared inequality on one declared column, and giving the second its own option
    # is cheaper in clauses than inventing a second relation direction convention.
    reverse_order_field: str | None = options.get("reverse_order_field")
    successor_field: str | None = options.get("successor_field")
    verdicts: list[bool] = []
    for candidate in candidates:
        source = candidate.context.get("source_fields", {})
        target = candidate.context.get("target_fields", {})
        ok = all(source.get(name) == target.get(name) for name in equal_fields)
        ok = ok and all(source.get(k) == v for k, v in source_values.items())
        ok = ok and all(target.get(k) == v for k, v in target_values.items())
        if ok and order_field is not None:
            ok = source.get(order_field) is not None and target.get(order_field) is not None \
                and source[order_field] > target[order_field]
        if ok and reverse_order_field is not None:
            ok = source.get(reverse_order_field) is not None \
                and target.get(reverse_order_field) is not None \
                and source[reverse_order_field] < target[reverse_order_field]
        if ok and successor_field is not None:
            ok = source.get(successor_field) is not None \
                and target.get(successor_field) is not None \
                and source[successor_field] == target[successor_field] + 1
        verdicts.append(bool(ok))
    return verdicts


register_predicate(WitnessPredicate(
    "typed_field_predicate@v1", "1", _typed_field_predicate,
    doc="relation from declared fields: the declared boolean over the endpoints' columns holds"))


# ----------------------------------------------------------------- argument_link@v1
def _argument_link(blobs, spans, candidates, options) -> list[bool]:
    """A walk edge: the source's argument surface is in its witness bytes and names the target.

    Both halves are needed and neither is a similarity. The BYTE half (the surface occurs in the
    span the source row was read from) is what makes the edge located; the FIELD half (the
    target row carries that surface in a declared anchor column) is what makes it resolved.
    ``context`` carries ``argument`` and ``target_surfaces``; ``options`` carries the principal
    surface sets so a first-person argument is matched the way the declaration says.
    """
    principals: frozenset[str] = frozenset(options.get("principals", ()))
    principal_surfaces: Mapping[str, tuple[str, ...]] = options.get("principal_surfaces", {})
    verdicts: list[bool] = []
    cache: dict[int, tuple[str, ...]] = {}
    for candidate in candidates:
        argument = candidate.context.get("argument")
        target_surfaces = candidate.context.get("target_surfaces", ())
        if argument is None or argument not in target_surfaces:
            verdicts.append(False)
            continue
        span_ord = int(candidate.spans[0])
        witness = cache.get(span_ord)
        if witness is None:
            witness = tokens_of(_text_of(blobs, spans, span_ord))
            cache[span_ord] = witness
        if argument in principals:
            condition = str(candidate.context.get("condition", "*"))
            forms = principal_surfaces.get(condition)
            verdicts.append(bool(forms) and any(phrase_present(witness, tokens_of(f))
                                                for f in forms))
        else:
            verdicts.append(phrase_present(witness, tokens_of(str(argument))))
    return verdicts


register_predicate(WitnessPredicate(
    "argument_link@v1", "1", _argument_link,
    doc="walk edge: the source's argument surface is located in its witness and names the target"))


# ------------------------------------------------------------- link_member_equals@v1
def _link_member_equals(blobs, spans, candidates, options) -> list[bool]:
    """The source item's named JSON member resolves to exactly the target row's declared id.

    B.32's link rule. ``options['link_field']`` is the member; ``context['target_id']`` is the
    id the edge claims to reach. A list-valued member is admitted when the target id is one of
    its elements, because ``supersedes`` is written both ways in the engine's own ledgers.
    """
    link_field = options["link_field"]
    verdicts: list[bool] = []
    cache: dict[int, Any] = {}
    for candidate in candidates:
        span_ord = int(candidate.spans[0])
        value = cache.get(span_ord)
        if value is None:
            try:
                value = json.loads(_bytes_of(blobs, spans, span_ord).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                verdicts.append(False)
                continue
            cache[span_ord] = value
        found = value.get(link_field) if isinstance(value, dict) else None
        target_id = candidate.context.get("target_id")
        if isinstance(found, list):
            verdicts.append(target_id in found)
        else:
            verdicts.append(found == target_id)
    return verdicts


register_predicate(WitnessPredicate(
    "link_member_equals@v1", "1", _link_member_equals,
    doc="link relation: the source item's named member holds the target row's id"))
