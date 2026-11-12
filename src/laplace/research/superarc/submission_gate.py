"""submission_gate.py — B11b: A2's own gate on what the loop is allowed to submit.

This is NOT the scorer. :mod:`.bin_classifier` (B11a) is the scorer-side bin
classifier, authored from the skeptic's seat to replicate the authors' hand-label
semantics and applied identically to every arm. This module is A2's *submission*
gate: the loop asks it, before banking an answer, whether the candidate is a
generator at all. The two are separately authored and share no decision code —
importing B11a here would make the instrument that scores us the thing we
optimize against, which is the exact failure the split exists to prevent. The
only thing the two organs share is :func:`~.sequence_exec.normalize_answer`, the
one normalization law every arm is held to.

**The gate runs on the NORMALIZED string** (DESIGN_2026-08-04 §4/§5). Padding is
a named gaming vector: 400 appended characters saturate δ at 1.0 and *dilute* a
literal-data fraction taken over the answer's own length. So every fraction here
is denominated in the ITEM's terms, never the answer's length — padding cannot
move it.

Strictly tighter than B11a, on four axes, each deliberate:

  1. **Threshold.** Literal cover rejects above :data:`LITERAL_COVER_MAX` (0.30);
     B11a needs 0.80 to call an answer a print.
  2. **No literal-with-rule escape.** B11a keeps a literal-carrying answer in the
     abstraction bin when a rule accompanies it. Here a candidate carrying more
     than a third of the item as literal terms is refused whatever else it says.
  3. **Positional predicates are read even when a rule survives.** B11a lets a
     generative rule with a positional exception stand as abstraction. Here a
     predicate pinning any position outside the base-case window is a fit.
  4. **Alternatives are gated jointly.** B11a binds the first of a list of
     candidate answers; here every alternative must pass or the submission is
     refused.

The three refusal classes are the memo's, in the order they are read: a lookup
table under an index access, a literal-data fraction over threshold, and a
positional fit. What passes is a genuine recurrence or closed form — a rule that
computes a term from the index or from earlier terms.

The decision is DATA: :class:`GateDecision` carries the verdict, a reason from a
closed set, the clause that fired, its evidence and the measured metrics, so a
refusal is auditable in the ledger without re-running the gate.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from .sequence_exec import normalize_answer, parse_sequence

#: Frozen tag. A changed decision rule needs a NEW tag: the gate's verdicts are
#: banked in the ledger, and a silently moved threshold makes them unreadable.
GATE_VERSION: str = "b11b-1"

# --------------------------------------------------------------------------- #
# Bounds — named, never inline
# --------------------------------------------------------------------------- #

#: Refusal threshold on the literal-data fraction: the share of the ITEM's terms
#: covered by the longest contiguous run of item terms among the answer's integer
#: literals. Strictly exceeded to refuse — a candidate sitting exactly on the
#: line is admitted, so the boundary is stated once and not argued twice.
LITERAL_COVER_MAX: float = 0.30

#: Absolute floor under the fraction: a run this short is coincidence, not data.
#: Binary items make short runs free (three terms of a 0/1 string are ~3 bits).
LITERAL_FLOOR_TERMS: int = 3

#: A bracketed literal list of at least this many numbers is a TABLE. Two numbers
#: are a pair (a modulus and an offset, a coordinate); three begin to be data.
TABLE_MIN_TERMS: int = 3

#: Base-case window. A predicate on the index that pins only positions below this
#: is a recurrence's seed, not a fit — every recurrence has to say what a(0) is.
#: A predicate reaching position 3 or beyond is talking about the interior of the
#: item, which is fitting, not seeding.
BASE_CASE_HORIZON: int = 3

#: …and it may pin at most this many positions. Three covers a tribonacci-shaped
#: seed; a fourth pinned position is an enumeration getting started.
BASE_CASE_MAX_POSITIONS: int = 3

#: The paper's non-answer conventions (SI §6.1.1), normalized.
MISSING_ANSWERS: frozenset[str] = frozenset(
    {"", "*not found", "*notfound", "not found", "n/a", "none"})

#: The closed reason set. A reason outside it is a bug, not a new class: the
#: ledger's refusal counts are read per-class across the run.
REASONS: tuple[str, ...] = (
    "admitted",
    "missing-answer",
    "no-index-variable",
    "lookup-table",
    "literal-data",
    "positional-fit",
)

# --------------------------------------------------------------------------- #
# Surface
# --------------------------------------------------------------------------- #

#: The index variable, standing alone. The word-boundary guards are load-bearing:
#: without them the ``n`` in "sequence" and the ``i`` in "if" make every prose
#: answer look indexed.
_VAR = r"(?<![a-z0-9_])[nikjx](?![a-z0-9_])"

_INT_RE = re.compile(r"-?\d+")
_NON_ASCII_RE = re.compile(r"[^\x20-\x7e]+")
#: ``a_n`` is a subscripted term name; rewritten before ``_`` becomes a space, or
#: ``a_n = 2n`` reads as the positional test ``n = 2``.
_SUBSCRIPT_RE = re.compile(r"(?<![a-z0-9])([a-z])_([nikjx])(?![a-z0-9_])")
_UNDERSCORE_RE = re.compile(r"_")

# A domain declaration says where the index RUNS. It is stripped before any
# predicate is read, so "for n >= 1" is never a positional test.
_DOMAIN_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfor\s+" + _VAR + r"\b[^,;]*"),
    re.compile(r"\bwith\s+" + _VAR + r"\s*(?:>=|>|<=|<)\s*-?\d+"),
    re.compile(r"\bwhere\s+" + _VAR + r"\b[^,;]*"),
    re.compile(_VAR + r"\s*=\s*-?\d+\s*(?:\.\.|to)\s*-?\d+"),
    re.compile(r"\brange\s*\([^)]*\)"),
)

#: Membership of the index in a literal set of positions.
_MEMBERSHIP_RE = re.compile(
    _VAR + r"\s*(?:in|:)?\s*[\[{(]\s*(-?\d+(?:\s*,\s*-?\d+)*)\s*[\]})]")
#: A comparison of the index against a literal position. ``==`` before ``=`` and
#: ``<=`` before ``<`` — the alternation order is the parse.
_COMPARISON_RE = re.compile(_VAR + r"\s*(==|!=|<>|<=|>=|<|>|=)\s*(-?\d+)")

#: A literal table…
_TABLE_RE = re.compile(r"[\[{]\s*-?\d+(?:\s*[,:]\s*-?\d+){" + str(TABLE_MIN_TERMS - 1) + r",}\s*[\]}]")
#: …and an access into it by the index. Only a SUBSCRIPT counts: ``a(n)`` is a
#: function head over the index and appears in every genuine closed form.
_INDEX_SUBSCRIPT_RE = re.compile(r"\[[^\[\]]*" + _VAR + r"[^\[\]]*\]")
_INDEX_GET_RE = re.compile(r"\.\s*get\s*\(\s*" + _VAR)

#: Generative markers: the index (or an earlier term) used to COMPUTE a value.
#: Read in what remains after the positional predicates are excised, so a rule
#: is not credited to its own exception clause.
_GENERATIVE_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("self-reference", re.compile(r"[a-z][a-z0-9_]*\s*[\(\[]\s*" + _VAR + r"\s*[-+]\s*\d+")),
    ("modular", re.compile(r"\bmod\b|%")),
    ("named-generator", re.compile(
        r"\b(fib|fibonacci|prime|primes|catalan|binomial|binom|comb|choose|"
        r"factorial|lucas|triangular|sum|prod|product)\b")),
    ("factorial", re.compile(r"!")),
    ("index-power", re.compile(_VAR + r"\s*(?:\^|\*\*)")),
    ("index-in-exponent", re.compile(r"(?:\^|\*\*)\s*\(?\s*" + _VAR)),
    ("index-coefficient", re.compile(r"\d\s*\*?\s*" + _VAR)),
    ("index-arithmetic", re.compile(_VAR + r"\s*[-+*/]\s*(?:-?\d|" + _VAR + r")")),
    ("bit-op", re.compile(r"\bbin\s*\(|\bcount\s*\(|>>|<<")),
)

_MONOMIAL_TERM_RE = re.compile(r"^([a-z])\s*(?:\^|\*\*)\s*(\d+)$")


def _surface(text: str) -> str:
    """Lower-case, drop non-ASCII (the CSV's lossy ``in``/``!=`` glyphs), rewrite
    ``a_n`` to ``a(n)``, then read the remaining ``_`` as a space — one model's
    answers reached storage with every space underscored."""
    s = _NON_ASCII_RE.sub(" ", text.lower())
    s = _SUBSCRIPT_RE.sub(r"\1(\2)", s)
    return _UNDERSCORE_RE.sub(" ", s)


def alternatives(answer: str | None) -> list[str]:
    """Split an answer that is a JSON list of candidate models into its members.

    B11a binds the first and scores that. The gate does the tighter thing: it
    returns them all, and the submission is refused unless every one passes. A
    candidate offering three models is offering three, and the loop does not get
    to have the weakest of them carried by the strongest."""
    text = normalize_answer(answer).strip().rstrip(",")
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, list) and parsed and all(isinstance(x, str) for x in parsed):
            return [normalize_answer(x) for x in parsed]
    return [normalize_answer(answer)]


def item_terms(sequence: str | Sequence[Any]) -> list[str]:
    if isinstance(sequence, str):
        return parse_sequence(sequence)
    return [str(t).strip() for t in sequence]


def _as_ints(terms: Sequence[str]) -> list[int] | None:
    out: list[int] = []
    for t in terms:
        try:
            out.append(int(t))
        except (TypeError, ValueError):
            return None
    return out


def int_literals(text: str) -> list[int]:
    """Every integer literal in the answer, in order."""
    return [int(m.group()) for m in _INT_RE.finditer(text)]


def _longest_run(answer_ints: Sequence[int], want: Sequence[int]) -> int:
    """Longest contiguous run of the item's terms appearing, in item order, among
    the answer's literals."""
    if not answer_ints or not want:
        return 0
    prev = [0] * (len(want) + 1)
    best = 0
    for x in answer_ints:
        cur = [0] * (len(want) + 1)
        for j, y in enumerate(want, 1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def literal_cover(answer: str | None, sequence: str | Sequence[Any]) -> float:
    """The literal-data fraction: the longest run of the item's terms carried
    literally by the answer, over the item's term count.

    Denominated in the ITEM, so lengthening the answer cannot dilute it — the
    padding vector §4 names is closed here rather than mitigated."""
    want = _as_ints(item_terms(sequence))
    if not want:
        return 0.0
    return _longest_run(int_literals(_surface(normalize_answer(answer))), want) / len(want)


def _is_binary(terms: Sequence[str]) -> bool:
    return bool(terms) and all(t in ("0", "1") for t in terms)


def _monomial_support(text: str, length: int) -> tuple[int, ...] | None:
    """A sum of unit-coefficient powers of one variable with distinct exponents,
    every exponent inside the index range: a binary item's support set written as
    a polynomial (``x^11+x^10+x^5+x^0`` shares not one digit with the sequence it
    encodes). Gated on the item being binary by its caller — on an integer item
    the same shape is a real polynomial."""
    parts = [p.strip() for p in text.split("+")]
    if not parts:
        return None
    var: str | None = None
    exps: list[int] = []
    for part in parts:
        m = _MONOMIAL_TERM_RE.match(part)
        if not m:
            return None
        if var is None:
            var = m.group(1)
        elif m.group(1) != var:
            return None
        exps.append(int(m.group(2)))
    if len(set(exps)) != len(exps) or len(exps) > length:
        return None
    if any(e < 0 or e >= length for e in exps):
        return None
    return tuple(exps)


def _pinned(residue: str) -> tuple[list[str], set[int], bool, str]:
    """Read the positional predicates out of a domain-stripped answer.

    Returns the predicate names that fired, the index positions they pin, whether
    any predicate fired at all, and the residue with the predicates excised (so a
    generative marker is looked for in what the rule actually says, not in its
    exception clause).

    A LOWER bound (``n >= 2``) pins nothing: it declares a half-line, which is a
    domain, not a position. It still counts as a predicate — an answer that is
    nothing but a half-line test computes nothing."""
    fired: list[str] = []
    pinned: set[int] = set()
    out = residue
    for m in _MEMBERSHIP_RE.finditer(residue):
        fired.append("membership")
        pinned.update(int(t) for t in m.group(1).split(","))
    out = _MEMBERSHIP_RE.sub(" ", out)
    for m in _COMPARISON_RE.finditer(out):
        op, val = m.group(1), int(m.group(2))
        if op in ("==", "="):
            fired.append("equality")
            pinned.add(val)
        elif op in ("!=", "<>"):
            fired.append("exception")
            pinned.add(val)
        elif op == "<":
            fired.append("upper-bound")
            pinned.update(range(0, max(val, 0)))
        elif op == "<=":
            fired.append("upper-bound")
            pinned.update(range(0, max(val + 1, 0)))
        else:
            fired.append("lower-bound")
    out = _COMPARISON_RE.sub(" ", out)
    return fired, pinned, bool(fired), out


def _generative(text: str) -> list[str]:
    return [name for name, pat in _GENERATIVE_RES if pat.search(text)]


def _ceil(x: float) -> int:
    return -int(-x // 1)


# --------------------------------------------------------------------------- #
# The decision
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GateDecision:
    """One gate verdict, as data. ``reason`` is from :data:`REASONS`; ``clause``
    names the rule that fired, never the outcome, so two refusals of the same
    class stay distinguishable in the ledger."""

    admitted: bool
    reason: str
    clause: str
    evidence: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    gate_version: str = GATE_VERSION

    def as_record(self) -> dict[str, Any]:
        return {
            "admitted": self.admitted,
            "reason": self.reason,
            "clause": self.clause,
            "evidence": list(self.evidence),
            "metrics": dict(self.metrics),
            "gate_version": self.gate_version,
        }


def _refuse(reason: str, clause: str, evidence: Sequence[str],
            metrics: dict[str, Any]) -> GateDecision:
    if reason not in REASONS:  # pragma: no cover - guards the closed set
        raise ValueError(f"reason {reason!r} not in the closed set {REASONS}")
    return GateDecision(False, reason, clause, tuple(evidence), metrics)


def gate_one(answer: str | None, sequence: str | Sequence[Any]) -> GateDecision:
    """Gate a SINGLE candidate model string against its item.

    Clause order is fixed and load-bearing: a table under an index access is
    reported as a lookup even when its literals also break the cover threshold,
    because that is the more specific finding; the literal fraction is read next;
    the positional reading last, since it is the one clause that must survive the
    answer carrying no literal data at all."""
    text = normalize_answer(answer)
    marker = _surface(text)
    stripped = marker.strip()
    metrics: dict[str, Any] = {"item_terms": len(item_terms(sequence))}

    if stripped in MISSING_ANSWERS or set(stripped) <= {"*", " "}:
        return _refuse("missing-answer", "G1:missing", (), metrics)

    has_var = re.search(_VAR, marker) is not None
    metrics["has_index_variable"] = has_var

    terms = item_terms(sequence)
    want = _as_ints(terms)
    run = _longest_run(int_literals(marker), want) if want else 0
    cover = run / len(want) if want else 0.0
    metrics["literal_run"] = run
    metrics["literal_cover"] = round(cover, 4)

    # G2 — a lookup table: literal data plus an index access into it. Read before
    # the fraction because a table can be SHORT (a period, a delta list) and
    # still be a lookup — the cover threshold alone would let it through.
    table = _TABLE_RE.search(marker)
    access = _INDEX_SUBSCRIPT_RE.search(marker) or _INDEX_GET_RE.search(marker)
    metrics["table"] = bool(table)
    metrics["index_access"] = bool(access)
    if table and access:
        return _refuse("lookup-table", "G2:table-index",
                       (f"table={table.group().strip()}", f"access={access.group().strip()}"),
                       metrics)

    # G3 — the literal-data fraction, denominated in the item. No literal-with-a-
    # rule escape: a candidate carrying this much of the item is refused whatever
    # else it says, because at submission time a partial copy and a seeded
    # recurrence are the same object.
    if want and run >= LITERAL_FLOOR_TERMS and cover > LITERAL_COVER_MAX:
        return _refuse("literal-data", "G3:literal-cover",
                       (f"run={run}/{len(want)}", f"cover={cover:.2f}>{LITERAL_COVER_MAX}"),
                       metrics)

    # G4 — an index-only interpolant with no literal data at all: the binary
    # item's support set written as a polynomial. Carries zero cover by
    # construction, which is why G3 cannot see it.
    if _is_binary(terms):
        support = _monomial_support(marker, len(terms))
        if support is not None:
            metrics["monomial_support"] = list(support)
            return _refuse("positional-fit", "G4:monomial-support",
                           (f"exponents={list(support)}",), metrics)

    # G5 — the positional reading. Domains first, then the predicates, then what
    # the rule computes in the residue.
    residue = marker
    for pat in _DOMAIN_RES:
        residue = pat.sub(" ", residue)
    fired, pinned, any_pred, residue = _pinned(residue)
    generative = _generative(residue)
    metrics["predicates"] = sorted(set(fired))
    metrics["pinned_positions"] = sorted(pinned)
    metrics["generative"] = generative

    if any_pred:
        if not generative:
            # Positions and nothing else: an index→value map, whatever its shape.
            return _refuse("positional-fit", "G5:no-rule", tuple(sorted(set(fired))), metrics)
        outside = sorted(p for p in pinned if p >= BASE_CASE_HORIZON)
        if outside:
            return _refuse("positional-fit", "G5:interior-position",
                           tuple(sorted(set(fired)) + [f"positions={outside}"]), metrics)
        if len(pinned) > BASE_CASE_MAX_POSITIONS:
            return _refuse("positional-fit", "G5:pinned-count",
                           (f"pinned={sorted(pinned)}",), metrics)

    # G6 — a generator has to be indexed. A bare literal answer that survived G3
    # (a short item, a run under the floor) still is not a model.
    if not has_var:
        return _refuse("no-index-variable", "G6:no-index", (), metrics)

    return GateDecision(True, "admitted", "G7:generator", tuple(generative), metrics)


def gate(answer: str | None, sequence: str | Sequence[Any]) -> GateDecision:
    """The submission gate. Every alternative in the answer must pass.

    The refusal returned is the FIRST alternative's refusal, with the offending
    index in the evidence — the loop needs one reason to act on, and the first
    one it has to fix is the first one it wrote."""
    alts = alternatives(answer)
    if len(alts) == 1:
        return gate_one(alts[0], sequence)
    decisions = [gate_one(a, sequence) for a in alts]
    for i, d in enumerate(decisions):
        if not d.admitted:
            metrics = dict(d.metrics)
            metrics["alternatives"] = len(alts)
            metrics["refused_index"] = i
            return _refuse(d.reason, d.clause, tuple(d.evidence) + (f"alternative={i}",), metrics)
    metrics = dict(decisions[0].metrics)
    metrics["alternatives"] = len(alts)
    return GateDecision(True, "admitted", "G7:generator", decisions[0].evidence, metrics)


def admits(answer: str | None, sequence: str | Sequence[Any]) -> bool:
    """The boolean projection, for call sites that only branch on it."""
    return gate(answer, sequence).admitted
