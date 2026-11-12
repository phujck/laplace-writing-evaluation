"""extract.py - rung (b): deterministic extractors, item-local, no model anywhere.

The ladder (charter lean L3) says rung (b) is "deterministic extractors from maintained
packages", and the need for the rung is MEASURED before it is used. Packet I1 measured it: with
rung (a) alone, 0 of 100 LongMemEval questions resolve a single anchor, because the rung-(a)
anchor vocabulary is exactly the container's own identifiers and no question utters one. That
number is the licence for this module and it is re-run, unchanged, as the "before" arm of the
F2 measurement.

WHAT IS IN HERE AND WHAT IS DELIBERATELY NOT.

Every function below is a pure function of ONE item's text plus the declaration's own grammar
constants. None of them consults a corpus statistic - no document frequency, no corpus
vocabulary, no global entity count - because B.28 says an extractor that does is no longer a
function of one item's bytes and the per-item cache dies with it. That is also why nothing here
takes the store, the index or the other items as an argument: the type signature is the
guarantee.

None of them calls a model. B.34 names ``quantulum3`` for quantities and it is NOT used. The
refusal is about the RUNG, not about installability: quantulum3 resolves ambiguous units with a
TRAINED CLASSIFIER and ships a fixed unit vocabulary, so charter forbidden move 10 (a model
where a parser suffices) and forbidden move 1 (a vocabulary in construction code with no
declared row behind it) both refuse it at rung (b). Nothing here claims it could not be
installed: ``scripts/laplace_python.py`` puts ``<repo>/src`` (laplace and atlas) - both
inside this writable repository - on ``PYTHONPATH``, so a ``pip install --target`` into either
would be importable with no edit to the launcher, and the charter explicitly licenses adding a
package to the runtime and recording it. It is refused because it is the wrong rung. What
replaces it is a declared decimal-and-unit grammar whose unit is stored as the LOCATED SURFACE
rather than as a code from a vocabulary, so there is no vocabulary to tune and no classifier to
consult.

THE MAINTAINED PACKAGES USED, and why each is the right tool rather than a hand-roll:

* ``regex`` (2026.9.10, in the pinned runtime) for every grammar here, because the proper-noun
  rule is a Unicode CATEGORY question ("does this token start with an uppercase letter in any
  script") and ``\\p{Lu}`` answers it where a stdlib ``[A-Z]`` would silently make the extractor
  English-only in its character class as well as in its grammar.
* ``dateutil`` (python-dateutil 2.9, in the pinned runtime) for absolute dates, because month
  names, ordinals and the dozen written orders of a civil date are exactly what it maintains.
  Relative expressions are NOT given to it: ``dateutil`` would resolve them against the clock,
  and B.33 says a relative expression is resolved against the ROW's session date.

BYTE ADDRESSES ARE THE POINT. Every returned item carries (start, end) offsets into the item's
own decoded text, and ``Locator`` maps those onto absolute byte offsets in the blob, escapes and
multi-byte characters included. A row whose witness address did not decode back to its own
surface would fail B.4's check at mint time, which is how a mapping bug becomes a refusal rather
than a silent mis-address.

DECLARED GRAMMAR CONSTANTS. The grammars below contain closed terminal sets (the four temporal
units, the copulas, the negation particle, the one-character refusal). Each is declared in full
here, is hashed into the extractor roster, and is listed with its provenance and expiry in the
packet report's ``declared_literals``. None of them is a threshold and none was chosen by
looking at an outcome.

Complexity: every function is O(len(text)) with one compiled-regex pass, except
``alias_pairs`` which is O(n log n + P) in the number of surfaces of one item.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Iterable, Sequence

import regex

from ..ids import chash

__all__ = [
    "Located", "Locator", "locator_for_json_string",
    "PROPER_NOUN_ID", "REFERENCE_MARKER_ID", "QUANTITY_ID", "TEMPORAL_ID", "STATE_CLAIM_ID",
    "ALIAS_ID", "EXTRACTOR_ROSTER", "extractor_roster_hash",
    "proper_nouns", "reference_markers", "quantities", "temporal_expressions",
    "state_claims", "alias_pairs", "DATE_PRECISION", "POLARITY", "REFERENCE_KINDS",
    "TEMPORAL_UNITS",
]

PROPER_NOUN_ID = "proper-noun-grammar@v1"
REFERENCE_MARKER_ID = "reference-marker-grammar@v1"
QUANTITY_ID = "decimal-and-unit-grammar@v1"
TEMPORAL_ID = "temporal-expression-grammar@v1"
STATE_CLAIM_ID = "possessive-copula-claim-grammar@v1"
ALIAS_ID = "token-subsequence-alias@v1"


# --------------------------------------------------------------------------- byte addressing
@dataclass(frozen=True, slots=True)
class Located:
    """One extracted surface and the byte range of the item's text it was located in."""

    surface: str
    start: int          # char offset into the decoded text
    end: int            # char offset, exclusive


class Locator:
    """Maps character offsets in a decoded JSON string onto absolute blob byte offsets.

    ``offsets[i]`` is the absolute byte offset of decoded character ``i``; ``offsets[len(text)]``
    is one past the last character's bytes. The common case - an ASCII string with no escapes -
    is the identity plus the opening quote, and is represented by ``None`` so that a 55 MB corpus
    never builds a per-character list.

    Complexity: O(1) construction on the fast path, O(len(raw)) otherwise; O(1) per lookup.
    """

    __slots__ = ("text", "_base", "_offsets")

    def __init__(self, text: str, base: int, offsets: Sequence[int] | None) -> None:
        self.text = text
        self._base = base
        self._offsets = offsets

    def at(self, index: int) -> int:
        if self._offsets is None:
            return self._base + index
        return self._base + self._offsets[index]

    def span(self, start: int, end: int) -> tuple[int, int]:
        """Absolute (start, end) byte offsets of ``text[start:end]``."""
        return self.at(start), self.at(end)


def locator_for_json_string(raw: bytes, base: int) -> Locator:
    """Decode a JSON string slice and return a locator onto the blob's bytes.

    ``raw`` is the span the scanner recorded, quotes INCLUDED (``json_spans``' declared span
    convention), and ``base`` is that span's absolute start. Complexity: O(len(raw)) worst case,
    O(1) when the slice is plain ASCII with no escape.
    """
    import json

    body = raw[1:-1]
    if b"\\" not in body and body.isascii():
        return Locator(body.decode("ascii"), base + 1, None)
    text = json.loads(raw.decode("utf-8"))
    # Walk the raw body once, recording where each decoded character begins. This is the slow
    # path and it runs only for items that actually carry an escape or a non-ASCII character.
    # Every step below consumes the bytes of exactly ONE decoded character: an escape (2 bytes),
    # a \uXXXX (6), a surrogate PAIR (12, which Python decodes as one character) or a UTF-8
    # sequence of 1 to 4 bytes.
    offsets: list[int] = []
    i = 0
    n = len(body)
    while i < n:
        offsets.append(i + 1)                       # +1: the opening quote is inside the span
        byte = body[i]
        if byte == 0x5C:                            # backslash
            if i + 1 < n and body[i + 1] == 0x75:   # \uXXXX, possibly a surrogate pair
                if (i + 11 < n and body[i + 6:i + 8] == b"\\u"
                        and 0xD800 <= int(body[i + 2:i + 6], 16) <= 0xDBFF):
                    i += 12
                else:
                    i += 6
            else:
                i += 2
        elif byte < 0x80:
            i += 1
        elif byte < 0xE0:
            i += 2
        elif byte < 0xF0:
            i += 3
        else:
            i += 4
    offsets.append(n + 1)
    if len(offsets) != len(text) + 1:
        # The walk and the decoder disagree: refuse rather than mis-address a span (B.4's rule
        # applied to the addressing itself). The caller treats this item as unindexed.
        raise ValueError(f"locator disagreed with the JSON decoder: "
                         f"{len(offsets) - 1} offsets for {len(text)} characters")
    return Locator(text, base, offsets)


# --------------------------------------------------------------------------- proper nouns
# The grammar, in full. A candidate is a maximal run of capitalised tokens. There is no name
# list, no gazetteer and no model: "is this token capitalised" is a Unicode category question.
# A token may carry an internal full stop ("U.S.A") but never a final one: a full stop followed
# by a space is a sentence end, and a run that swallowed it would join two sentences into one
# name ("New York University. It").
_TOKEN_TAIL = r"(?:[\p{L}\p{M}\p{Nd}'’\-]|\.(?=\p{L}))*"
_CAPITALISED = regex.compile(r"\p{Lu}" + _TOKEN_TAIL, regex.UNICODE)
_RUN = regex.compile(
    r"\p{Lu}" + _TOKEN_TAIL + r"(?:[  ]\p{Lu}" + _TOKEN_TAIL + r")*", regex.UNICODE)
# A sentence boundary for the sentence-initial rule below. Terminator plus space, or a newline,
# or the start of the text. Nothing about this is tunable: it is the grammar of a sentence end.
_SENTENCE_START = regex.compile(r"(?:^|[.!?;:]['\"’”\)]*[  ]+|[\r\n]+[ \t]*)", regex.UNICODE)
_HAS_LETTER = regex.compile(r"\p{L}", regex.UNICODE)

# DECLARED CONSTANT (labelled assumption Q-E1-A1, see the packet report): a one-character
# candidate is refused. Without it the English first-person pronoun "I" becomes an entity in
# every second turn of LongMemEval and drowns the index. Expiry: a measured surface census
# showing one-character names in an admitted corpus.
_MIN_CANDIDATE_CHARACTERS = 2


def proper_nouns(text: str, masked: Sequence[tuple[int, int]] = ()) -> list[Located]:
    """Capitalised-token runs that are not sentence-initial single tokens. O(len(text)).

    The two refusals are grammar, not tuning: a single capitalised token that begins a sentence
    is explained by the sentence, not by being a name; and a candidate with no letter in it is
    not a name at all. A multi-token run is kept wherever it stands, because "New York is..."
    is evidence of a name even at a sentence start.

    ``masked`` is a list of character ranges already claimed by another declared grammar - the
    reference markers of B.34, which are capitalised and would otherwise be swallowed into the
    name beside them ("GE-FL BIBREF0"). They are blanked with spaces of EQUAL LENGTH so every
    offset the caller receives still addresses the same byte.
    """
    if masked:
        buffer = list(text)
        for start, end in masked:
            for i in range(max(start, 0), min(end, len(buffer))):
                buffer[i] = " "
        text = "".join(buffer)
    starts = {match.end() for match in _SENTENCE_START.finditer(text)}
    starts.add(0)
    out: list[Located] = []
    for match in _RUN.finditer(text):
        surface = match.group(0).rstrip(".")
        if not surface:
            continue
        end = match.start() + len(surface)
        if len(surface) < _MIN_CANDIDATE_CHARACTERS or not _HAS_LETTER.search(surface):
            continue
        single = len(_CAPITALISED.findall(surface)) == 1
        if single and match.start() in starts:
            continue
        out.append(Located(surface, match.start(), end))
    return out


# --------------------------------------------------------------------------- references
# B.34 asks for "a declared bracketed-reference grammar over regex". QASPER's own full_text does
# not carry brackets: the S2ORC pipeline that built it replaced every inline reference with a
# marker token, so the bracketed form the clause names does not occur in the bytes. The grammar
# below is the declared form for the corpus that exists, and it also admits the bracketed numeric
# form for a corpus that does keep it. The clause wording is patched in the packet report.
REFERENCE_KINDS = ("bibliography", "figure", "table", "equation", "section", "bracketed")
_MARKER = regex.compile(
    r"\b(?P<marker>(?P<tag>BIBREF|FIGREF|TABREF|EQREF|SECREF)(?P<index>\d+))\b"
    r"|(?P<bracket>\[\s*\d+(?:\s*[,-]\s*\d+)*\s*\])", regex.UNICODE)
_TAG_KIND = {"BIBREF": "bibliography", "FIGREF": "figure", "TABREF": "table",
             "EQREF": "equation", "SECREF": "section"}


def reference_markers(text: str) -> list[tuple[Located, str]]:
    """Located reference markers and their declared kind. O(len(text))."""
    out: list[tuple[Located, str]] = []
    for match in _MARKER.finditer(text):
        if match.group("marker") is not None:
            out.append((Located(match.group("marker"), match.start("marker"),
                                match.end("marker")), _TAG_KIND[match.group("tag")]))
        else:
            out.append((Located(match.group("bracket"), match.start("bracket"),
                                match.end("bracket")), "bracketed"))
    return out


# --------------------------------------------------------------------------- quantities
# A decimal literal followed by a unit surface. The unit is stored as the LOCATED SURFACE, never
# as a code from a unit vocabulary, which is what keeps this a grammar rather than a dictionary.
#
# THE UNIT SURFACE HAS NO LENGTH BOUND, deliberately. An earlier form of this grammar capped the
# unit tail at ``{0,15}``; that was a size in construction code with no derivation behind it, and
# it was load-bearing in the wrong direction - a longer following token was silently TRUNCATED
# into the row and into its witness span, so the stored surface was not the surface that was
# located. The bound is REMOVED rather than declared, because the tail rule already decides where
# the unit ends: it stops at the first character that is not a unit character (anything outside
# letter / mark / '-' / '/', and a full stop only when a letter follows it). The ``*`` is linear -
# one pass, no backtracking, because the two alternatives inside the tail are disjoint on the next
# character.
#
# The digit-group counts in ``value`` are the GRAMMAR of a comma-grouped decimal (1-3 digits, then
# groups of exactly 3), not thresholds: they are what a thousands separator means.
_QUANTITY = regex.compile(
    r"(?<![\p{L}\p{Nd}])(?P<value>[-+]?\p{Nd}{1,3}(?:,\p{Nd}{3})*(?:\.\p{Nd}+)?|[-+]?\p{Nd}+(?:\.\p{Nd}+)?)"
    r"(?P<gap>[  ]?)(?P<unit>%|°[CF]?|\p{L}(?:[\p{L}\p{M}\-/]|\.(?=\p{L}))*)",
    regex.UNICODE)


@dataclass(frozen=True, slots=True)
class Quantity:
    """One located quantity: the exact decimal as a scaled integer, and the unit surface."""

    located: Located
    value_scaled: int       # the decimal's digits as an integer
    value_scale: int        # number of fractional digits; value = value_scaled / 10**value_scale
    unit_surface: str


def quantities(text: str) -> list[Quantity]:
    """Located decimal-and-unit quantities. O(len(text)).

    The value is stored EXACTLY, as (scaled integer, scale), because the store has no float
    column and because a float would make two equal decimals compare unequal at the 17th digit -
    which is the kind of thing a typed ``compare`` operator must never do.
    """
    out: list[Quantity] = []
    for match in _QUANTITY.finditer(text):
        raw = match.group("value").replace(",", "")
        if "." in raw:
            whole, fraction = raw.split(".", 1)
            scale = len(fraction)
            sign = -1 if whole.startswith("-") else 1
            scaled = sign * int(whole.lstrip("+-") + fraction)
        else:
            scale, scaled = 0, int(raw)
        out.append(Quantity(
            Located(match.group(0), match.start(), match.end()),
            scaled, scale, match.group("unit")))
    return out


# --------------------------------------------------------------------------- temporal
DATE_PRECISION = ("day", "week", "month", "year")
# The closed terminal set of the relative grammar, declared in full (B.5). English only, per the
# charter's decided author-card item ("English-only now").
TEMPORAL_UNITS = ("day", "week", "month", "year")
_UNIT_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}
_NAMED_OFFSET = {"yesterday": -1, "today": 0, "tomorrow": 1}

_ABSOLUTE = regex.compile(
    r"\b(?P<iso>\p{Nd}{4}-\p{Nd}{2}-\p{Nd}{2})\b"
    r"|\b(?P<named>(?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)[  ]+\p{Nd}{1,2}(?:st|nd|rd|th)?(?:,[  ]*\p{Nd}{4})?)"
    r"|\b(?P<dmy>\p{Nd}{1,2}[  ]+(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)(?:[  ]+\p{Nd}{4})?)\b", regex.UNICODE)
_RELATIVE = regex.compile(
    r"\b(?P<named>yesterday|today|tomorrow)\b"
    r"|\b(?P<ago>\p{Nd}{1,3}|a|an)[  ]+(?P<ago_unit>day|week|month|year)s?[  ]+ago\b"
    r"|\b(?P<rel>last|next|this)[  ]+(?P<rel_unit>day|week|month|year)\b",
    regex.IGNORECASE | regex.UNICODE)


@dataclass(frozen=True, slots=True)
class TemporalExpression:
    """One located time expression and the date it resolves to against a declared reference."""

    located: Located
    resolved: _dt.datetime
    precision: str
    relative: bool


def temporal_expressions(text: str, reference: _dt.datetime) -> list[TemporalExpression]:
    """Absolute and relative time expressions, resolved against ``reference``. O(len(text)).

    B.33: "relative expressions resolved against the row's session date". The reference is passed
    in by the caller from the ROW's declared typed time; nothing here reads a clock, so the same
    bytes resolve to the same date in any year the extractor is re-run - which is what makes the
    per-item cache and B.4's re-verification mean anything.
    """
    from dateutil import parser as _parser

    out: list[TemporalExpression] = []
    for match in _ABSOLUTE.finditer(text):
        surface = match.group(0)
        try:
            resolved = _parser.parse(surface, default=reference, fuzzy=False)
        except (ValueError, OverflowError):
            continue
        precision = "day"
        out.append(TemporalExpression(
            Located(surface, match.start(), match.end()), resolved, precision, False))
    for match in _RELATIVE.finditer(text):
        surface = match.group(0)
        if match.group("named"):
            days = _NAMED_OFFSET[match.group("named").lower()]
            resolved, precision = reference + _dt.timedelta(days=days), "day"
        elif match.group("ago"):
            head = match.group("ago").lower()
            count = 1 if head in ("a", "an") else int(head)
            unit = match.group("ago_unit").lower()
            resolved = reference - _dt.timedelta(days=count * _UNIT_DAYS[unit])
            precision = unit if unit in DATE_PRECISION else "day"
        else:
            unit = match.group("rel_unit").lower()
            direction = {"last": -1, "next": 1, "this": 0}[match.group("rel").lower()]
            resolved = reference + _dt.timedelta(days=direction * _UNIT_DAYS[unit])
            precision = unit
        out.append(TemporalExpression(
            Located(surface, match.start(), match.end()), resolved, precision, True))
    return out


# --------------------------------------------------------------------------- state claims
POLARITY = ("asserted", "negated")
# The possessive-copula grammar. Every terminal in it is a FUNCTION word - the possessive
# determiner, the four copula forms, the negation particle - so the grammar carries no content
# vocabulary that could be extended until a question compiles.
#
# ITS TWO SIZES ARE LABELLED ASSUMPTIONS, declared here and in the packet report beside
# Q-E1-A1, because neither is derived from the grammar the way the unit tail is:
#
#   Q-E1-A2  the attribute phrase is at most THREE tokens (``{0,2}`` after the head).
#            Provenance: an English possessive attribute phrase is a small nominal - 'my cat',
#            'my blood pressure', 'my youngest daughter's name'. Without a bound the phrase
#            swallows the copula's own subject complement in a long clause.
#            Expiry: a measured census of attribute-phrase token lengths on an admitted corpus,
#            which replaces the bound with the measured shape or with a clause-level parse.
#   Q-E1-A3  the value runs at most EIGHTY characters (``{1,80}``) inside a clause the character
#            class has already bounded at sentence punctuation.
#            Provenance: the value is the complement of one copula, not a paragraph; the class
#            ``[^.!?;\r\n]`` ends it at the sentence, and the 80 ends a run-on clause that a
#            comma keeps alive. It TRUNCATES rather than refuses, which is the same defect the
#            unit tail had, and it is declared here rather than removed because removing it
#            changes what ``supersedes`` compares (the value surface) and that comparison is
#            measured in this packet - a change to it is a new extractor id, not a tidy-up.
#            Known imprecision, stated rather than discovered later: the value is GREEDY to
#            the clause end, so a second claim conjoined in the same sentence ('my cat is
#            Pepper and my blood pressure is 120/80') is absorbed into the first claim's
#            value instead of being minted as its own row. The row is still exactly
#            located and its witness re-reads; what it costs is recall, which is what the
#            supersedes count in the packet report measures.
#            Expiry: a measured census of value lengths, or the first question class that
#            needs a value longer than one clause.
_CLAIM = regex.compile(
    r"\bmy[  ]+(?P<attribute>\p{L}[\p{L}\p{M}\-]*(?:[  ]\p{L}[\p{L}\p{M}\-]*){0,2})"
    r"[  ]+(?P<copula>is|are|was|were)(?P<negation>[  ]+not|n't)?"
    r"[  ]+(?P<value>[^.!?;\r\n]{1,80})", regex.IGNORECASE | regex.UNICODE)


@dataclass(frozen=True, slots=True)
class StateClaim:
    """A located (subject, attribute, value, polarity) claim. The subject is the declared self."""

    located: Located
    attribute: str
    value: str
    polarity: str


def state_claims(text: str) -> list[StateClaim]:
    """Possessive-copula claims: ``my <attribute> is <value>``. O(len(text))."""
    out: list[StateClaim] = []
    for match in _CLAIM.finditer(text):
        value = match.group("value").strip().rstrip(",")
        if not value:
            continue
        out.append(StateClaim(
            Located(match.group(0), match.start(), match.end()),
            match.group("attribute").strip().casefold(), value,
            "negated" if match.group("negation") else "asserted"))
    return out


# --------------------------------------------------------------------------- aliases
_TOKEN = regex.compile(r"[\p{L}\p{M}\p{Nd}'’]+", regex.UNICODE)


def alias_pairs(surfaces: Iterable[str]) -> list[tuple[str, str]]:
    """Declared alias rule: a shorter surface that is a contiguous token subsequence of a longer.

    This is the ONLY same-entity rule, and it is item-local by construction: the caller passes
    the surfaces of ONE item, so the pair's witness tuple never leaves the item and B.29's
    byte-computable bound survives (see the packet report's same_entity finding). Returns
    (short, long) pairs, deduplicated and sorted. Complexity: O(n * m) in tokens for n surfaces.
    """
    tokenised = {s: tuple(t.casefold() for t in _TOKEN.findall(s)) for s in surfaces}
    # Index every contiguous token n-gram of every surface once: O(sum of L^2) over surfaces of L
    # tokens (a mention is a few tokens), then each surface is ONE lookup of its own token tuple.
    # The quadratic loop this replaces was 59% of ingestion (profiled 2026-09-22).
    holders: dict[tuple[str, ...], set[str]] = {}
    for surface, tokens in tokenised.items():
        length = len(tokens)
        for n in range(1, length):            # n-grams strictly shorter than the surface itself
            for i in range(length - n + 1):
                holders.setdefault(tokens[i:i + n], set()).add(surface)
    pairs: set[tuple[str, str]] = set()
    for short, short_tokens in tokenised.items():
        if not short_tokens:
            continue
        for long in holders.get(short_tokens, ()):   # loop-ok: only the surfaces that contain this token tuple
            if long != short and len(short_tokens) < len(tokenised[long]):
                pairs.add((short, long))
    return sorted(pairs)


# --------------------------------------------------------------------------- roster
EXTRACTOR_ROSTER: tuple[tuple[str, str], ...] = (
    (PROPER_NOUN_ID, "capitalised-token runs, sentence-initial singletons refused"),
    (REFERENCE_MARKER_ID, "BIBREF/FIGREF/TABREF/EQREF/SECREF markers and bracketed numerics"),
    (QUANTITY_ID, "decimal literal plus located unit surface, value as (scaled, scale)"),
    (TEMPORAL_ID, "absolute dates via dateutil; relative forms against the row's declared time"),
    (STATE_CLAIM_ID, "possessive-copula claims: my <attribute> is|was [not] <value>"),
    (ALIAS_ID, "a shorter surface that is a contiguous token subsequence of a longer one"),
)


def extractor_roster_hash() -> str:
    """B.27's ``extractor_roster_hash`` over the rung-(b) roster, its grammars and constants.

    THE GRAMMAR SOURCES ARE IN THE HASH. Every bound, terminal and character class of every
    pattern below is part of what the extractors ARE, so changing one - removing the unit tail's
    old ``{0,15}`` cap, say - must change this hash, or the hash names a roster and not a
    construction and a store minted under two different grammars carries one id.
    """
    return chash({
        "roster": [list(entry) for entry in EXTRACTOR_ROSTER],
        "grammars": {
            PROPER_NOUN_ID: [_CAPITALISED.pattern, _RUN.pattern, _SENTENCE_START.pattern,
                             _HAS_LETTER.pattern, _TOKEN_TAIL],
            REFERENCE_MARKER_ID: [_MARKER.pattern],
            QUANTITY_ID: [_QUANTITY.pattern],
            TEMPORAL_ID: [_ABSOLUTE.pattern, _RELATIVE.pattern],
            STATE_CLAIM_ID: [_CLAIM.pattern],
            ALIAS_ID: [_TOKEN.pattern],
        },
        "reference_kinds": list(REFERENCE_KINDS),
        "date_precision": list(DATE_PRECISION),
        "temporal_units": list(TEMPORAL_UNITS),
        "unit_days": dict(sorted(_UNIT_DAYS.items())),
        "named_offset": dict(sorted(_NAMED_OFFSET.items())),
        "tag_kind": dict(sorted(_TAG_KIND.items())),
        "polarity": list(POLARITY),
        "min_candidate_characters": _MIN_CANDIDATE_CHARACTERS,
    })
