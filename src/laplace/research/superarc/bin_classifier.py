"""bin_classifier.py — B11a: the scorer-side bin classifier.

The instrument that decides which of the paper's four bins an answer falls in:

  * ``CORRECT_NONBOTH``  — genuine abstraction   (ρ₁, weight ×1)
  * ``CORRECT_ORDINAL``  — index-mapped          (ρ₂, weight ×1/10)
  * ``CORRECT_PRINTS``   — literal reproduction  (ρ₃, weight ×1/100)
  * ``INCORRECT``        — ρ₄, weight 0

The bins are the released scoring notebook's own slices
(``correctness & ~ordinal & ~copy_seq`` / ``correctness & ordinal`` /
``correctness & copy_seq`` / ``~correctness``), so a bin decision is worth a
factor of 100 in φ. The authors never released the code that assigns them —
those columns arrive hand-labelled — which is why this organ exists and why it
is authored from the skeptic's seat, frozen, and preregistered before it was
ever scored (``synthetics papers/superarc/preregistration/b11a_threshold.md``).

TWO INVARIANTS, both load-bearing:

1. **Correctness is an input, never an output.** This module decides the FORM of
   an answer only. Correctness comes from execution and byte-compare (B10,
   :mod:`.sequence_exec`) for our arms, and from the authors' released
   ``-formula-correctness`` column when re-scoring theirs. A classifier that
   inferred correctness from surface features would let a formatting change move
   an answer between bins — the scorer would become the optimization target.

2. **ORDINAL is decided structurally, never by literal overlap.** An index-only
   minimized interpolant (``1 if n in {0,1,5,10} else 0``; ``x^11+x^10+x^5+x^0``)
   carries none of the sequence's values — its literals are index positions — so
   its literal overlap sits at the same near-zero level a closed form's does and
   a literal-fraction classifier can only bin it as genuine abstraction,
   inflating ρ₁ by a factor of 10 in precisely the direction of our own claim.
   Literal comparison is therefore allowed to decide PRINTS and nothing else;
   ORDINAL turns on what the index variable is USED FOR. :func:`literal_overlap`
   is exposed only as that naive baseline, to keep the trap demonstrable in the
   tests — no decision path outside the print filter reads it.

3. **A constant whose expansion IS the sequence is a print in integer clothing.**
   Added at ``b11a-3`` as rule **S-1**. ``a(n) = floor(1178 / 2^(11-n)) mod 2``
   carries no model of ``0,1,0,0,1,0,0,1,1,0,1,0`` — it carries the sequence
   itself, packed as an integer, plus a decoder. That is the paper's own
   ``copy_seq`` concept written in base 2, and ``b11a-2`` binned every such
   answer ×1 genuine abstraction because :func:`int_tokens` reads the packed
   constant as ONE integer and :func:`longest_common_run` therefore compares it
   against nothing. :func:`base_encoded_literal` closes that gap by comparing the
   constant's DIGIT EXPANSION against the item term-by-term. It is deliberately
   monotone — S-1 can only move a row DOWN, into the ×1/100 print bin, never up —
   and it is gated on the constant carrying at least half the item's symbols, so
   a modulus, a small coefficient or a seed shorter than the sequence is a
   genuine short constant and is not touched.

4. **The dialect an answer is typed in must not move it between bins.** Added at
   ``b11a-2`` as correction C-1 of the adversarial calibration verdict. The
   non-ASCII mathematical operators are transliterated to their ASCII spellings
   BEFORE any stripping (:func:`transliterate_math`), so ``[n ≥ 8] · [n ≠ 10]``
   and ``[n >= 8] * [n != 10]`` reduce to the same marker string. Under
   ``b11a-1`` the strip both destroyed the interval predicate and manufactured a
   phantom ``index-coefficient`` out of the gap it left, and the Unicode dialect
   binned ×1 abstraction where the ASCII dialect binned ×1/10 ordinal — a factor
   of ten in φ decided by a keystroke.

Where the released hand labels are mutually inconsistent between models for the
same answer form (they are — see the preregistration §5), the tie-break is fixed
AGAINST us: the reading that puts fewer answers in the genuine-abstraction bin
wins. The cost is paid in ``CORRECT_NONBOTH`` recall, knowingly.

This module is a pure decision function plus its agreement harness. It never
reads or writes the authors' data other than the caller-supplied path, and the
banked agreement output carries row ids and fired rules — never their answer
strings (their repo has no LICENSE; the article is CC BY-NC-ND).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence

from .sequence_exec import normalize_answer, parse_sequence

#: Frozen tag. Any change to a decision rule needs a NEW tag and a NEW
#: preregistration — a threshold is never moved after the numbers exist.
#:
#: The version ledger, newest last. Each tag names exactly one rule change and
#: the preregistration it was accepted under.
#:
#: ``b11a-1`` (2026-08-04) — the original freeze. R0–R4, thresholds in
#: ``preregistration/b11a_threshold.md``.
#:
#: ``b11a-2`` (2026-08-04) lands correction **C-1** of the adversarial
#: calibration verdict (``synthetics papers/superarc/pilot/skeptic_verdict.md``):
#: :func:`_marker_text` TRANSLITERATES the non-ASCII mathematical operators to
#: their ASCII spellings BEFORE anything is stripped. Preregistered under
#: ``synthetics papers/superarc/preregistration/b11a2_threshold.md``.
#:
#: ``b11a-3`` (2026-08-04) lands rule **S-1**, the base-encoded literal:
#: :func:`base_encoded_literal` + the S-1 clause in :func:`classify_form`. It is
#: the only rule change in the tag; R0–R4 and every b11a-2 threshold are carried
#: through untouched. Preregistered under
#: ``synthetics papers/superarc/preregistration/s1_rule.md``, written and applied
#: SYMMETRICALLY to the pilot arms and to the authors' released answers in the
#: same commit that lands it.
CLASSIFIER_VERSION: str = "b11a-3"

# --------------------------------------------------------------------------- #
# Bounds — named, never inline
# --------------------------------------------------------------------------- #

#: PRINTS prong 1 — fraction of the item's terms a contiguous literal run must
#: cover for the answer to read as a reproduction.
PRINT_COVER: float = 0.8

#: Absolute floor under PRINT_COVER: a run this short is coincidence, not a
#: reproduction (binary items make short runs cheap — 3 terms of a 12-term
#: 0/1 string carry ~3 bits).
PRINT_FLOOR_TERMS: int = 3

#: PRINTS prong 2 — the TRUNCATED copy. Several released answers begin by
#: reproducing the item and then run out (``90,203,212,235,270,300,000,000,…``
#: against ``90,203,212,235,270,324,…``), and the authors labelled those copies.
#: An answer whose literal stream OPENS on this many of the item's leading terms
#: started copying, whatever it did afterwards. Index enumerations cannot reach
#: this floor on a binary item: an index list is strictly increasing and a 0/1
#: sequence cannot open on four strictly increasing terms.
PRINT_PREFIX_TERMS: int = 4

#: …and the opening has to be a substantial share of the item, not a lucky
#: leading fragment. Without this, a COMPRESSED form whose expansion happens to
#: start right (``[[1,1,0,0]*3][:12]`` on a period-4 binary item) reads as a
#: truncated copy — which is the print bin swallowing a real abstraction.
PRINT_PREFIX_COVER: float = 0.4

# --------------------------------------------------------------------------- #
# S-1 bounds — the base-encoded literal
# --------------------------------------------------------------------------- #

#: S-1 prong — the constant's minimal expansion must carry at least this share of
#: the item's symbols. THE discriminating threshold: an 11-bit constant for a
#: 12-term binary item has stored the sequence, an 5-bit one has compressed it
#: better than 2:1 and is a genuine short constant (a modulus, a coefficient, a
#: seed). At 0.5 the packed-sequence answers in both corpora clear it and the
#: attested short constants — the modulus 29, the ECA rule numbers, the LFSR seed
#: 23, the rational denominators 87 and 59 — do not.
S1_MIN_DIGIT_SHARE: float = 0.5

#: …and S-1 does not run on short items at all. On a 4- or 5-term sequence a
#: two-digit constant matching by coincidence is ordinary, not evidence; the
#: released suite has two such rows and the campaign's own items are all 12.
S1_MIN_TERMS: int = 8

#: The bases an answer can pack a sequence into. Base 10 is the case B11a was
#: blindest to — a spelled-out bit string reaches :func:`int_tokens` as ONE
#: integer, so the print filter compares it against nothing.
S1_BASES: tuple[int, ...] = (2, 10, 16)

#: Digit alphabet for :func:`_to_base` and :func:`_target_digits`, lower-case to
#: match the marker surface.
_S1_DIGITS: str = "0123456789abcdef"

#: The paper's non-answer conventions (SI §6.1.1), normalized.
MISSING_ANSWERS: frozenset[str] = frozenset({"", "*not found", "*notfound", "not found", "n/a"})

#: Index-like variable names. Single letters only: the answers are one-line
#: formulas, and a multi-letter identifier in this corpus is a named generator
#: (``Fibonacci(n)``), which is a generative marker, not an index.
_VAR = r"[nikjx]"

# --------------------------------------------------------------------------- #
# The vocabulary
# --------------------------------------------------------------------------- #


class Form(str, Enum):
    """What an answer IS, independent of whether it is right."""

    PRINTS = "prints"
    ORDINAL = "ordinal"
    ABSTRACTION = "abstraction"
    NO_ANSWER = "no_answer"


class Bin(str, Enum):
    """The scorer's four bins — the notebook's slices, in its own order."""

    CORRECT_NONBOTH = "correct_non_both"
    CORRECT_ORDINAL = "correct_ordinal"
    CORRECT_PRINTS = "correct_prints"
    INCORRECT = "incorrect"


@dataclass(frozen=True)
class Verdict:
    """One classification, with the rule that fired. ``rule`` is what makes a
    disagreement auditable: it names the clause, not the outcome."""

    bin: Bin
    form: Form
    rule: str
    evidence: tuple[str, ...] = ()

    def as_record(self) -> dict[str, Any]:
        return {
            "bin": self.bin.value,
            "form": self.form.value,
            "rule": self.rule,
            "evidence": list(self.evidence),
        }


def hand_bin(correct: bool, ordinal: bool, copy_seq: bool) -> Bin:
    """The authors' own predicate, transcribed from ``11_S-ARC_ext.ipynb``.

    Their slices overlap by construction (a row both ordinal and copy_seq lands
    in two frames and is double-counted in ``tot_elements``); no released row is
    both, so the four bins partition the label set and the precedence below is
    never exercised on their data. It is fixed anyway: ordinal before prints,
    matching the ρ vector's order."""
    if not correct:
        return Bin.INCORRECT
    if ordinal:
        return Bin.CORRECT_ORDINAL
    if copy_seq:
        return Bin.CORRECT_PRINTS
    return Bin.CORRECT_NONBOTH


# --------------------------------------------------------------------------- #
# Surface handling
# --------------------------------------------------------------------------- #

_MOJIBAKE_RE = re.compile(r"[^\x20-\x7e]+")
_INT_RE = re.compile(r"-?\d+")

# --------------------------------------------------------------------------- #
# C-1 — TRANSLITERATION, and why it runs before the strip
# --------------------------------------------------------------------------- #
#
# ``_MOJIBAKE_RE`` deletes every non-ASCII codepoint. On an answer written in the
# Unicode maths dialect that does two things at once, and both push toward the
# ×1 abstraction bin:
#
#   (a) it DESTROYS the operator, so ``8 ≤ n ≤ 9`` cannot fire the ``interval``
#       positional predicate — the answer stops looking like an index lookup;
#   (b) it MANUFACTURES a generative marker out of the hole it left: ``8 ≤ n``
#       becomes ``8   n``, which is exactly the ``index-coefficient`` pattern
#       ``\d\s*\*?\s*n\b``. The answer starts looking like a rule.
#
# One arm writing ``≤`` and another writing ``<=`` therefore landed in different
# bins for the same formula — a factor of ten in φ decided by a keystroke. The
# repair is to spell the operator in ASCII first, so the two spellings of one
# formula reduce to the SAME marker string and can only bin the same way.
#
# Every entry below is either named in the verdict's C-1 or attested in the two
# corpora this instrument reads (the pilot arms and the authors' released
# answers). Nothing is here on speculation. Glyphs outside the table are still
# stripped by ``_MOJIBAKE_RE``: deletion can lose a marker but cannot invent one,
# and inventing one is what C-1 forbids.
_MATH_ASCII: dict[str, str] = {
    # comparison — the operators C-1 names, and the ones the interval predicate
    # is written with.
    "≤": "<=",   # ≤  attested: A1 ×18
    "≥": ">=",   # ≥  attested: A1 ×4
    "≠": "!=",   # ≠  attested: A1 ×1
    # multiplication. C-1 names the multiplication sign and the middle dot.
    "×": "*",    # ×
    "·": "*",    # ·  attested: A1 ×3
    "⋅": "*",    # ⋅
    # minus and the dashes. An en/em dash is a dash, not a hole.
    "−": "-",    # −  attested: A1 ×16
    "–": "-",    # –
    "—": "-",    # —  attested: A2 ×2, A3 ×1
    "‐": "-",    # ‐
    "‑": "-",    # ‑
    # floor and ceiling brackets, in the ASCII spelling A1 itself uses elsewhere
    # (``floor(1178 / 2^(11-n))``).
    "⌊": "floor(",  # ⌊
    "⌋": ")",       # ⌋
    "⌈": "ceil(",   # ⌈
    "⌉": ")",       # ⌉
    # set operators. ``∈`` is the membership predicate's own sign; the campaign
    # already reads the lossy ``_`` spelling of it as membership.
    "∈": " in ",      # ∈  attested: A1 ×1
    "∉": " not in ",  # ∉
    "∪": "|",         # ∪  attested: A1 ×1
    "∩": "&",         # ∩
}
_MATH_TRANSLATION: dict[int, str] = {ord(k): v for k, v in _MATH_ASCII.items()}

#: Superscript and subscript digit runs. ``x¹¹`` is ``x^11`` and ``a₂`` is
#: ``a_2``; deleting the run leaves ``x`` and ``a``, which loses the exponent
#: (an ``index-power`` marker) and the subscript alike.
_SUPERSCRIPTS: dict[str, str] = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁺": "+", "⁻": "-", "⁽": "(", "⁾": ")",
    "ⁿ": "n", "ⁱ": "i",
}
_SUBSCRIPTS: dict[str, str] = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "₊": "+", "₋": "-", "₍": "(", "₎": ")",
    "ₙ": "n", "ᵢ": "i", "ⱼ": "j", "ₖ": "k", "ₓ": "x",
}
_SUPERSCRIPT_RUN_RE = re.compile("[" + "".join(_SUPERSCRIPTS) + "]+")
_SUBSCRIPT_RUN_RE = re.compile("[" + "".join(_SUBSCRIPTS) + "]+")


def _sup_repl(m: re.Match[str]) -> str:
    """``x¹¹`` → ``x^11``; ``2ⁿ⁻¹`` → ``2^(n-1)``.

    Bare digits are NOT parenthesised: ``x^11`` is the form
    :data:`_MONOMIAL_TERM_RE` reads as an index-support monomial, and the
    polynomial spelling of an index enumeration must survive transliteration
    intact. Anything else is parenthesised, because ``2^n-1`` and ``2^(n-1)``
    are not the same formula."""
    body = "".join(_SUPERSCRIPTS[c] for c in m.group())
    return "^" + body if body.isdigit() else "^(" + body + ")"


def _sub_repl(m: re.Match[str]) -> str:
    """``a₂`` → ``a_2``, ``aₙ`` → ``a_n`` — the campaign's own subscript
    spelling, which :data:`_SUBSCRIPT_RE` already understands."""
    return "_" + "".join(_SUBSCRIPTS[c] for c in m.group())


def transliterate_math(text: str) -> str:
    """C-1. Rewrite the non-ASCII mathematical operators as ASCII, changing
    nothing else. Idempotent on text that is already ASCII."""
    if text.isascii():
        return text
    out = text.translate(_MATH_TRANSLATION)
    out = _SUPERSCRIPT_RUN_RE.sub(_sup_repl, out)
    return _SUBSCRIPT_RUN_RE.sub(_sub_repl, out)


def _ascii_text(text: str) -> str:
    """Transliterate FIRST, lower-case, then strip whatever non-ASCII is left.
    The one surface every decision rule reads."""
    return _MOJIBAKE_RE.sub(" ", transliterate_math(text).lower())


_UNDERSCORE_SEP_RE = re.compile(r"_")
#: ``a_n`` is a subscripted term name, not the index standing alone. Rewritten to
#: ``a(n)`` BEFORE ``_`` becomes a separator, otherwise ``a_n = 2n`` reads as the
#: positional predicate ``n = 2`` and a closed form is binned ordinal. The word
#: boundary keeps it off ``n_in_[0,1,5,10]``, where ``_`` really is a space.
_SUBSCRIPT_RE = re.compile(r"\b([a-z])_(" + "[nikjx]" + r")\b")
#: An explicit index argument — a function head over the index, or a subscript by
#: it. Matched on the raw text, never on the ``a_n`` rewrite, so a bare
#: ``a_n = 1,2,4,8`` stays a print.
_INDEX_WRAPPER_RE = re.compile(r"[a-z][a-z0-9_]*\s*\(\s*[nikjx]\s*\)|\[\s*[nikjx]\s*\]")


def select_alternative(answer: str | None) -> str:
    """R0 — bind the FIRST candidate when an answer is a list of alternatives.

    The paper's prompt asks for one model or formula per sequence; some models
    answered with a JSON array of up to three (with a trailing comma, as stored).
    Binding the first is preregistered precisely because "which alternative" is
    the kind of choice that could otherwise be tuned once the numbers exist."""
    text = normalize_answer(answer).strip().rstrip(",")
    if not (text.startswith("[") and text.endswith("]")):
        return normalize_answer(answer)
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return normalize_answer(answer)
    if isinstance(parsed, list) and parsed and all(isinstance(x, str) for x in parsed):
        return normalize_answer(parsed[0])
    return normalize_answer(answer)


def _marker_text(text: str) -> str:
    """Transliterate, lower-case, de-mojibake, and treat ``_`` as a separator.

    Answers reached the CSV through a lossy encoding: ``∈`` survives as ``_`` in
    one model's rows (``f_(n) = 1 if n _ {1,2,6,11}``) and as literal underscores
    standing in for spaces in another (``s(n)=1_if_n_in_[0,1,5,10]_else_0``).
    Both are the same membership test and must read as one.

    C-1 (``b11a-2``): the operators are spelled in ASCII BEFORE anything is
    stripped, so ``[n ≥ 8] · [n ≠ 10]`` and ``[n >= 8] * [n != 10]`` reduce to
    one string. Under ``b11a-1`` the first lost its interval predicates to the
    strip and gained a phantom ``index-coefficient`` from the gap, and the two
    spellings of one formula binned a factor of ten apart in φ."""
    s = _SUBSCRIPT_RE.sub(r"\1(\2)", _ascii_text(text))
    return _UNDERSCORE_SEP_RE.sub(" ", s)


def int_tokens(text: str) -> list[int]:
    """Every integer literal in order. Decimal points split (``7.21E+28`` reads
    as 7, 21, 28) — that is correct here: no item's terms are decimals, so a
    decimal answer cannot be a reproduction of one."""
    return [int(m.group()) for m in _INT_RE.finditer(text)]


def sequence_terms(sequence: str | Sequence[Any]) -> list[str]:
    if isinstance(sequence, str):
        return parse_sequence(sequence)
    return [str(t).strip() for t in sequence]


def _as_ints(terms: Iterable[str]) -> list[int] | None:
    out: list[int] = []
    for t in terms:
        try:
            out.append(int(t))
        except (TypeError, ValueError):
            return None
    return out


def longest_common_run(a: Sequence[int], b: Sequence[int]) -> int:
    """Longest contiguous run shared by two integer streams."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            if x == y:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def literal_overlap(answer: str | None, sequence: str | Sequence[Any]) -> float:
    """The naive baseline — the feature this classifier refuses to decide ORDINAL
    with. Fraction of the item's terms covered by the longest contiguous literal
    run in the answer. On an index-only interpolant it sits at the same near-zero
    level a closed form reaches, which is the whole trap: no decision path in
    this module consults it for anything but PRINTS, and the tests assert the
    gap against a literal-fraction classifier."""
    terms = sequence_terms(sequence)
    want = _as_ints(terms)
    if not want:
        return 0.0
    return longest_common_run(int_tokens(select_alternative(answer)), want) / len(want)


# --------------------------------------------------------------------------- #
# R3 — the structural ordinal reading
# --------------------------------------------------------------------------- #

# A domain is not a predicate. ``for i in range(12)``, ``for n=0..11``,
# ``for n >= 1`` declare where the index runs; stripping them first is what stops
# a domain declaration from being read as a positional test.
_DOMAIN_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfor\s+" + _VAR + r"\b[^,;]*"),
    re.compile(r"\bwhere\s+" + _VAR + r"\b[^,;]*"),
    re.compile(r"\b" + _VAR + r"\s*=\s*-?\d+\s*(?:\.\.|to)\s*-?\d+"),
    re.compile(r"\brange\s*\([^)]*\)"),
)

# Positional predicates: the index used as a POSITION LOOKUP rather than as the
# argument of a rule. Membership in a literal index set, equality against an
# index constant, an interval on the index, or a literal table subscripted by it.
_PREDICATE_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "membership",
        re.compile(r"\b" + _VAR + r"\s*(?:in|:)?\s*[\[{]\s*-?\d+(?:\s*,\s*-?\d+)*\s*[\]}]"),
    ),
    ("equality", re.compile(r"\b" + _VAR + r"\s*(?:==|=)\s*-?\d+")),
    ("interval", re.compile(r"\b" + _VAR + r"\s*(?:<=|>=|!=|<>|<|>)\s*-?\d+")),
    (
        "table",
        re.compile(r"[\[{]\s*-?\d+(?:\s*,\s*-?\d+)+\s*[\]}]\s*\[\s*" + _VAR + r"\s*\]"),
    ),
)

# Generative markers: an index used to COMPUTE a value. Searched in what remains
# after the positional predicates are excised, so a rule with a positional
# exception (``(n+1) mod 2 == 0 && n != 6``) stays ABSTRACTION — the rule is
# still generative and the exception does not make it a lookup.
_GENERATIVE_RES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("modular", re.compile(r"\bmod\b|%")),
    (
        "named-generator",
        re.compile(
            r"\b(fib|fibonacci|prime|primes|catalan|binomial|binom|comb|choose|"
            r"factorial|lucas|triangular|sum|prod|product)\b"
        ),
    ),
    # ``!`` is the factorial, but ``!=`` is not-equal — and C-1's transliteration
    # of ``≠`` spells it exactly that way. Without the lookahead the repair would
    # manufacture the very kind of marker it exists to stop manufacturing (and
    # the ASCII dialect's own ``n != 6`` carried the same phantom under b11a-1
    # whenever the interval predicate did not consume it).
    ("factorial", re.compile(r"!(?!=)")),
    ("index-power", re.compile(_VAR + r"\s*(?:\^|\*\*)")),
    ("index-in-exponent", re.compile(r"(?:\^|\*\*)\s*\(?\s*" + _VAR)),
    ("index-coefficient", re.compile(r"\d\s*\*?\s*" + _VAR + r"\b")),
    ("index-arithmetic", re.compile(_VAR + r"\s*[-+*/]\s*(?:-?\d|" + _VAR + r")")),
    ("bit-op", re.compile(r"\bbin\s*\(|\bcount\s*\(|>>|<<")),
)

_MONOMIAL_TERM_RE = re.compile(r"^([a-z])\s*(?:\^|\*\*)\s*(\d+)$")


def _monomial_support(text: str, length: int) -> tuple[int, ...] | None:
    """A sum of unit-coefficient powers of ONE variable, distinct integer
    exponents, all inside the index range: the support set of a BINARY item
    written as a polynomial. Returns the exponents, or None.

    This is the zero-literal-overlap case in its purest form — ``x^11 + x^10 +
    x^5 + x^0`` shares not one digit with ``1,1,0,0,0,1,0,0,0,0,1,0``.

    A single term counts (``x^7`` is the one-position support). The clause is
    gated on the item being binary by its caller, which is what keeps a real
    closed form like ``n^2`` on an integer item out of it."""
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


def _is_binary(terms: Sequence[str]) -> bool:
    return bool(terms) and all(t in ("0", "1") for t in terms)


# --------------------------------------------------------------------------- #
# S-1 — the base-encoded literal (b11a-3)
# --------------------------------------------------------------------------- #
#
# The gap this closes, stated as the instrument saw it: R2 decides PRINTS by
# comparing the answer's INTEGER TOKENS against the item's terms. An answer that
# packs the whole item into one constant — ``floor(1178 / 2^(11-n)) mod 2``, or
# the same thing spelled ``010010011010`` — presents that constant as a single
# token, so ``longest_common_run`` compares one integer against twelve and
# returns 0. The answer with the LEAST abstraction in it scored the highest
# possible bin. The paper's own ``copy_seq`` is exactly this concept in base 10.
#
# The discriminating test, in full:
#
#   Let the item have L terms, L >= S1_MIN_TERMS, at least two distinct terms.
#   For each integer literal in the answer, in each admissible reading —
#     * AS WRITTEN, in the base its notation declares (a bare decimal run in base
#       10, ``0x…`` in 16, ``0b…`` in 2), leading zeros KEPT;
#     * AS A VALUE, expanded into each base in S1_BASES, leading zeros dropped
#   — call the resulting digit string E, and let T be the item written as a digit
#   string in that base (defined only when every term is one digit in it).
#   S-1 fires iff, for some reading,
#     (i)  len(E) >= ceil(S1_MIN_DIGIT_SHARE * L)          — the length gate, and
#     (ii) E == T, or E == T with its leading zeros stripped   — big-endian; or
#          the same two against reverse(T)                     — little-endian; or
#          T (or reverse(T)) occurs as a CONTIGUOUS WINDOW of E — offset.
#
# (i) is what keeps genuine short constants out. A modulus, a coefficient or a
# seed that is shorter than half the item cannot be the item in disguise: it has
# compressed by better than 2:1, and whatever else that is, it is not a copy.
# ``a(n) = 1 if n^2 mod 29 < 17 else 0`` has 29 -> ``11101``, five bits of a
# twelve-term item, and is not touched — nor is ``13`` on the item whose whole
# content is four trailing bits, which is a real (if thin) 3:1 compression.
#
# (ii)'s three tolerances are the three ways one formula can be written down: a
# constant zero-padded to the item's width (``38`` for ``000000100110``), a
# constant read LSB-first (``(K >> n) & 1``), and a constant with spare digits
# either side of the item.

_S1_LITERAL_RE = re.compile(r"0x[0-9a-f]+|0b[01]+|\d+")

# Decode machinery — excised from the residue BEFORE the generative-marker escape
# is applied, and ONLY inside the S-1 clause. The b11a-1 lesson one level up: a
# reader is not a rule. ``floor``, ``mod 2``, ``2^(11-n)``, ``>> n``, ``& 1`` and
# the words for a digit expansion describe how the constant is UNPACKED; counting
# them as generative markers is how ``b11a-2`` let every packed answer through
# R4. The blast radius is contained: this excision runs only on an answer already
# proven to carry the entire item inside one constant.
_S1_DECODE_RES: tuple[re.Pattern[str], ...] = (
    # a power of a base, with or without a bracketed exponent: 2^(11-n), 2**n,
    # 16^i, 10^(n+1). Written before the integers are stripped, because stripping
    # them first would leave a bare ``^n`` that reads as index-in-exponent.
    re.compile(r"\b(?:2|8|10|16)\s*(?:\^|\*\*)\s*\(?[^)\s]*\)?"),
    # the extracting modulus and the extracting mask/shift
    re.compile(r"\bmod\s*\d+"),
    re.compile(r"%\s*\d+"),
    re.compile(r"(?:>>|<<)\s*\(?\s*[nikjx]?"),
    re.compile(r"&\s*1\b"),
    # truncating division wrappers
    re.compile(r"\b(?:floor|int|trunc|ceil)\b"),
    re.compile(r"//"),
    # the prose that names an expansion. Attested in both corpora: "12-bit binary
    # expansion", "most significant bit first", "big-endian", "the n-th bit of".
    re.compile(
        r"\b(?:bit|bits|binary|digit|digits|decimal|hex|hexadecimal|base|"
        r"expansion|expansions|endian|big-endian|little-endian|significant|"
        r"msb|lsb|packed|encoded)\b"
    ),
)


@dataclass(frozen=True)
class BaseEncoded:
    """One firing of S-1: which literal, read in which base and which direction."""

    literal: str
    value: int
    base: int
    reading: str      # "written" | "value"
    orientation: str  # "big-endian" | "reversed"
    offset: int
    digits: str

    @property
    def evidence(self) -> str:
        return (
            f"base{self.base}:{self.reading}:{self.orientation}"
            f"{'' if self.offset == 0 else f':offset{self.offset}'}={self.literal}"
        )


def _to_base(value: int, base: int) -> str:
    """Minimal digit expansion, most significant first, no leading zeros."""
    if value == 0:
        return "0"
    out: list[str] = []
    while value:
        value, rem = divmod(value, base)
        out.append(_S1_DIGITS[rem])
    return "".join(reversed(out))


def _target_digits(terms: Sequence[str], base: int) -> str | None:
    """The item as a digit string in ``base`` — None unless every term is exactly
    one digit in it. A 90-item integer sequence with a term ``29`` is not a base-2
    or base-10 digit string and S-1 cannot read it as one."""
    out: list[str] = []
    for t in terms:
        try:
            v = int(t)
        except (TypeError, ValueError):
            return None
        if v < 0 or v >= base:
            return None
        out.append(_S1_DIGITS[v])
    return "".join(out)


def _s1_match(expansion: str, target: str) -> tuple[str, int] | None:
    """(ii). Returns (orientation, offset) or None."""
    for orientation, want in (("big-endian", target), ("reversed", target[::-1])):
        if expansion == want or expansion == (want.lstrip("0") or "0"):
            return orientation, 0
        if len(expansion) > len(want):
            at = expansion.find(want)
            if at >= 0:
                return orientation, at
    return None


def base_encoded_literal(
    answer: str | None, sequence: str | Sequence[Any]
) -> BaseEncoded | None:
    """S-1. The first literal in the answer whose digit expansion IS the item.

    Pure and side-effect free, exposed so the rule can be tested and audited on
    its own — the classifier's clause is three lines around this call."""
    terms = sequence_terms(sequence)
    length = len(terms)
    if length < S1_MIN_TERMS or len(set(terms)) < 2:
        return None
    need = max(1, _ceil(S1_MIN_DIGIT_SHARE * length))
    targets = {b: _target_digits(terms, b) for b in S1_BASES}
    if not any(targets.values()):
        return None

    marker = _marker_text(select_alternative(answer))
    for m in _S1_LITERAL_RE.finditer(marker):
        token = m.group()
        if token.startswith("0x"):
            written, written_base, value = token[2:], 16, int(token, 16)
        elif token.startswith("0b"):
            written, written_base, value = token[2:], 2, int(token, 2)
        else:
            written, written_base, value = token, 10, int(token, 10)
        for base in S1_BASES:
            target = targets[base]
            if not target:
                continue
            readings = [("value", _to_base(value, base))]
            if base == written_base:
                # leading zeros are part of what was WRITTEN: an answer that
                # spells ``000000100110`` has spelled the item out, and the
                # length gate must see twelve symbols, not six.
                readings.insert(0, ("written", written))
            for reading, expansion in readings:
                if len(expansion) < need:
                    continue
                hit = _s1_match(expansion, target)
                if hit is None:
                    continue
                orientation, offset = hit
                return BaseEncoded(
                    literal=token,
                    value=value,
                    base=base,
                    reading=reading,
                    orientation=orientation,
                    offset=offset,
                    digits=expansion,
                )
    return None


def _s1_decode_residue(marker: str) -> str:
    """What is left of the answer once the packed constant's DECODER is taken
    out: base powers, the extracting modulus/mask/shift, the truncating wrappers,
    and the prose naming an expansion — then every integer, exactly as R2's own
    escape does it. A generative marker surviving this is a real rule and the
    answer is not a copy."""
    residue = marker
    for pat in _S1_DECODE_RES:
        residue = pat.sub(" ", residue)
    return _INT_RE.sub(" ", residue)


# --------------------------------------------------------------------------- #
# The classifier
# --------------------------------------------------------------------------- #


def classify_form(answer: str | None, sequence: str | Sequence[Any]) -> Verdict:
    """Decide the FORM of an answer. ``bin`` on the returned verdict is the
    correct-answer projection; :func:`classify` applies correctness."""
    terms = sequence_terms(sequence)
    text = select_alternative(answer)
    marker = _marker_text(text)

    # R1 — no answer. The empty string, the paper's stated conventions, and a
    # bare run of asterisks (the '*not found' convention as it reached the CSV).
    stripped = marker.strip()
    if stripped in MISSING_ANSWERS or set(stripped) <= {"*", " "}:
        return _form_verdict(Form.NO_ANSWER, "R1:missing")

    # S-1 — the base-encoded literal, checked before R2 because the constant it
    # looks for is invisible to R2's integer comparison by construction.
    #
    # MONOTONE BY CONSTRUCTION: this clause either returns PRINTS or falls
    # through. It never returns a bin above the one the rest of the classifier
    # would have reached, so applying S-1 to a corpus can only move rows into the
    # ×1/100 bin — which is what makes its effect on any arm a subtraction that
    # can be counted, and never a rebalancing that has to be argued about.
    encoded = base_encoded_literal(text, terms)
    if encoded is not None:
        generative = [
            name for name, pat in _GENERATIVE_RES if pat.search(_s1_decode_residue(marker))
        ]
        if not generative:
            return _form_verdict(Form.PRINTS, "S1:base-encoded-literal", (encoded.evidence,))

    # R2 — the two-pronged print filter, first, and the only clause allowed to
    # read literal overlap. A literal match alone is not enough: the literal has
    # to BE the answer. If a rule accompanies it the answer is not a copy, and if
    # the literal is delivered as a table under an index argument the answer is
    # an index→value map, which is the ordinal class, not the print class.
    want = _as_ints(terms)
    if want:
        got = int_tokens(text)
        run = longest_common_run(got, want)
        need = max(PRINT_FLOOR_TERMS, _ceil(PRINT_COVER * len(want)))
        opening = 0
        for a, b in zip(got, want):
            if a != b:
                break
            opening += 1
        prefix_need = max(PRINT_PREFIX_TERMS, _ceil(PRINT_PREFIX_COVER * len(want)))
        prong = ""
        if run >= need:
            prong = f"run={run}/{len(want)}"
        elif opening >= min(prefix_need, len(want)):
            prong = f"prefix={opening}/{len(want)}"
        if prong:
            residue = _INT_RE.sub(" ", marker)
            generative = [name for name, pat in _GENERATIVE_RES if pat.search(residue)]
            if generative:
                return _form_verdict(
                    Form.ABSTRACTION, "R4:literal-with-rule", tuple([prong] + generative)
                )
            if _INDEX_WRAPPER_RE.search(_ascii_text(text)):
                return _form_verdict(Form.ORDINAL, "R3:index-table", (prong,))
            return _form_verdict(Form.PRINTS, "R2:literal", (prong,))

    # R3 — ORDINAL, structural.
    support = _monomial_support(marker, len(terms)) if _is_binary(terms) else None
    if support is not None:
        return _form_verdict(
            Form.ORDINAL, "R3:monomial-support", (f"exponents={list(support)}",)
        )

    residue = marker
    for pat in _DOMAIN_RES:
        residue = pat.sub(" ", residue)
    fired: list[str] = []
    for name, pat in _PREDICATE_RES:
        if pat.search(residue):
            fired.append(name)
            residue = pat.sub(" ", residue)
    if fired:
        generative = [name for name, pat in _GENERATIVE_RES if pat.search(residue)]
        if not generative:
            return _form_verdict(Form.ORDINAL, "R3:positional", tuple(fired))
        return _form_verdict(
            Form.ABSTRACTION, "R4:generative-residue", tuple(fired + generative)
        )

    # R4 — everything else.
    return _form_verdict(Form.ABSTRACTION, "R4:default")


def classify(
    answer: str | None,
    sequence: str | Sequence[Any],
    correct: bool,
) -> Verdict:
    """The bin. ``correct`` is supplied by the executor (B10) or read from the
    authors' column — never inferred here (see the module docstring)."""
    v = classify_form(answer, sequence)
    if not correct:
        return Verdict(Bin.INCORRECT, v.form, v.rule, v.evidence)
    return Verdict(_BIN_OF_FORM[v.form], v.form, v.rule, v.evidence)


_BIN_OF_FORM: dict[Form, Bin] = {
    Form.PRINTS: Bin.CORRECT_PRINTS,
    Form.ORDINAL: Bin.CORRECT_ORDINAL,
    Form.ABSTRACTION: Bin.CORRECT_NONBOTH,
    # A verified-correct non-answer cannot exist; if the executor ever hands one
    # over, it is not abstraction being claimed — but the bin has to be defined.
    Form.NO_ANSWER: Bin.CORRECT_NONBOTH,
}


def _form_verdict(form: Form, rule: str, evidence: tuple[str, ...] = ()) -> Verdict:
    return Verdict(_BIN_OF_FORM[form], form, rule, evidence)


def _ceil(x: float) -> int:
    return -int(-x // 1)


# --------------------------------------------------------------------------- #
# The agreement harness — reads the fetched benchmark at run time
# --------------------------------------------------------------------------- #

#: Split by a content hash of the row id: dev is burnt (rules may be refined
#: against it), eval is read once, after the freeze.
DEV_MODULUS: int = 4


@dataclass(frozen=True)
class LabelPair:
    model: str
    row: int
    sequence: str
    answer: str
    correct: bool
    ordinal: bool
    copy_seq: bool

    @property
    def row_id(self) -> str:
        return f"{self.model}#{self.row}"

    @property
    def bin(self) -> Bin:
        return hand_bin(self.correct, self.ordinal, self.copy_seq)

    @property
    def stratum(self) -> str:
        digest = hashlib.sha1(self.row_id.encode("utf-8")).digest()
        return "dev" if digest[0] % DEV_MODULUS == 0 else "eval"


def load_label_set(csv_path: str | Path) -> list[LabelPair]:
    """Every ``(model, row)`` pair carrying a hand label. A pair whose
    correctness cell is empty is not a label and is dropped — an unanswered item
    is missing data, not a judgement (``gpt_o1`` rows 100–189)."""
    path = Path(csv_path)
    with path.open(newline="", encoding="utf-8", errors="replace") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return []
    models = sorted(
        c[: -len("-formula")]
        for c in rows[0]
        if c.endswith("-formula") and f"{c[:-len('-formula')]}-formula-correctness" in rows[0]
    )
    out: list[LabelPair] = []
    for model in models:
        for i, r in enumerate(rows):
            raw = (r.get(f"{model}-formula-correctness") or "").strip()
            if raw == "":
                continue
            out.append(
                LabelPair(
                    model=model,
                    row=i,
                    sequence=r.get("sequence") or "",
                    answer=r.get(f"{model}-formula") or "",
                    correct=raw == "True",
                    ordinal=(r.get(f"{model}-formula-ordinal") or "").strip() == "True",
                    copy_seq=(r.get(f"{model}-formula-copy_seq") or "").strip() == "True",
                )
            )
    return out


def inadmissible_copy_columns(pairs: Sequence[LabelPair]) -> dict[str, list[str]]:
    """Label columns that are UNFILLED rather than judged.

    Mechanical, and deliberately not a judgement call: a model's ``copy_seq``
    column is inadmissible if it is all-False while at least one of that model's
    answers is byte-identical to its item's sequence under the campaign's shared
    normalization. Byte identity cannot be steered by this classifier, so the
    audit cannot be steered by it either. Returns model → the row ids that prove
    the column unfilled."""
    by_model: dict[str, list[LabelPair]] = defaultdict(list)
    for p in pairs:
        by_model[p.model].append(p)
    out: dict[str, list[str]] = {}
    for model, ps in by_model.items():
        if any(p.copy_seq for p in ps):
            continue
        proof = [
            p.row_id
            for p in ps
            if normalize_answer(p.answer) and normalize_answer(p.answer) == normalize_answer(p.sequence)
        ]
        if proof:
            out[model] = proof
    return out


def _bin_stats(pairs: Sequence[LabelPair], verdicts: Sequence[Verdict]) -> dict[str, Any]:
    hand = Counter(p.bin.value for p in pairs)
    pred = Counter(v.bin.value for v in verdicts)
    hit = Counter(p.bin.value for p, v in zip(pairs, verdicts) if p.bin is v.bin)
    stats = {}
    for b in Bin:
        n = hand[b.value]
        stats[b.value] = {
            "n_hand": n,
            "n_predicted": pred[b.value],
            "n_agree": hit[b.value],
            "recall": (hit[b.value] / n) if n else None,
            "precision": (hit[b.value] / pred[b.value]) if pred[b.value] else None,
        }
    total = len(pairs)
    stats["_overall"] = {
        "n": total,
        "agreement": (sum(hit.values()) / total) if total else None,
    }
    return stats


def agreement_report(csv_path: str | Path) -> dict[str, Any]:
    """The evaluation cell. Runs the frozen classifier over the full hand-label
    set and returns every number the preregistration commits to, plus the
    complete disagreement enumeration.

    The enumeration carries row ids, bins and fired rules — never the authors'
    answer strings. Their repo has no LICENSE and the article is CC BY-NC-ND, so
    the banked artefact must be auditable without republishing their data."""
    pairs = load_label_set(csv_path)
    verdicts = [classify(p.answer, p.sequence, p.correct) for p in pairs]
    inadmissible = inadmissible_copy_columns(pairs)

    strata: dict[str, list[int]] = {"dev": [], "eval": []}
    for idx, p in enumerate(pairs):
        strata[p.stratum].append(idx)
    admissible_eval = [i for i in strata["eval"] if pairs[i].model not in inadmissible]

    def sub(idxs: Sequence[int]) -> dict[str, Any]:
        return _bin_stats([pairs[i] for i in idxs], [verdicts[i] for i in idxs])

    per_model: dict[str, Any] = {}
    by_model: dict[str, list[int]] = defaultdict(list)
    for idx, p in enumerate(pairs):
        by_model[p.model].append(idx)
    for model, idxs in sorted(by_model.items()):
        per_model[model] = sub(idxs)["_overall"] | {
            "recall": {
                b.value: sub(idxs)[b.value]["recall"]
                for b in Bin
                if sub(idxs)[b.value]["n_hand"]
            }
        }

    disagreements = [
        {
            "row_id": pairs[i].row_id,
            "model": pairs[i].model,
            "row": pairs[i].row,
            "stratum": pairs[i].stratum,
            "hand_bin": pairs[i].bin.value,
            "predicted_bin": verdicts[i].bin.value,
            "form": verdicts[i].form.value,
            "rule": verdicts[i].rule,
            "evidence": list(verdicts[i].evidence),
            "admissible": pairs[i].model not in inadmissible,
            # The naive baseline, banked so a reader can see which disagreements
            # a literal-fraction classifier would ALSO have made.
            "literal_overlap": round(literal_overlap(pairs[i].answer, pairs[i].sequence), 3),
        }
        for i in range(len(pairs))
        if pairs[i].bin is not verdicts[i].bin
    ]

    return {
        "classifier_version": CLASSIFIER_VERSION,
        "label_file": str(Path(csv_path)),
        "label_file_md5": hashlib.md5(Path(csv_path).read_bytes()).hexdigest(),
        "module_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "n_pairs": len(pairs),
        "inadmissible_copy_columns": {m: len(v) for m, v in sorted(inadmissible.items())},
        "inadmissible_proof_row_ids": {m: sorted(v) for m, v in sorted(inadmissible.items())},
        "strata": {
            "dev": sub(strata["dev"]),
            "eval_full": sub(strata["eval"]),
            "eval_admissible": sub(admissible_eval),
            "all": sub(list(range(len(pairs)))),
        },
        "per_model": per_model,
        "n_disagreements": len(disagreements),
        "disagreements": disagreements,
    }


def render_report(report: dict[str, Any]) -> str:
    """Markdown for the banked artefact — the numbers a reader checks against
    the preregistration, in its order."""
    lines: list[str] = []
    a = lines.append
    a("# B11a agreement — evaluation output")
    a("")
    a(f"Classifier `{report['classifier_version']}`, module sha256 "
      f"`{report['module_sha256'][:16]}…`")
    a(f"Label file `{Path(report['label_file']).name}` md5 `{report['label_file_md5']}`, "
      f"{report['n_pairs']} labelled pairs.")
    a("")
    a(f"Preregistration: `{report['classifier_version'].replace('-', '')}_threshold.md` — "
      "PRIMARY ≥ 0.90 per-bin recall on the admissible")
    a("EVAL stratum; SECONDARY ≥ 0.85 per-bin recall on the full EVAL stratum.")
    a("")
    for name, title in (
        ("eval_admissible", "PRIMARY — admissible EVAL stratum"),
        ("eval_full", "SECONDARY — full EVAL stratum"),
        ("dev", "DEV stratum (burnt)"),
        ("all", "All labelled pairs"),
    ):
        s = report["strata"][name]
        a(f"## {title}")
        a("")
        a(f"n = {s['_overall']['n']}, overall agreement = {s['_overall']['agreement']:.4f}")
        a("")
        a("| bin | n (hand) | agree | recall | precision |")
        a("|---|---:|---:|---:|---:|")
        for b in Bin:
            row = s[b.value]
            rec = "—" if row["recall"] is None else f"{row['recall']:.4f}"
            pre = "—" if row["precision"] is None else f"{row['precision']:.4f}"
            a(f"| `{b.value}` | {row['n_hand']} | {row['n_agree']} | {rec} | {pre} |")
        a("")
    a("## Per model (all pairs)")
    a("")
    a("| model | n | agreement |")
    a("|---|---:|---:|")
    for model, s in report["per_model"].items():
        a(f"| {model} | {s['n']} | {s['agreement']:.4f} |")
    a("")
    a("## Inadmissible `copy_seq` columns")
    a("")
    if report["inadmissible_copy_columns"]:
        a("All-False columns with at least one answer byte-identical to its sequence:")
        a("")
        for m, n in report["inadmissible_copy_columns"].items():
            a(f"- `{m}` — {n} byte-identical answers, all labelled not-a-copy")
    else:
        a("None.")
    a("")
    a(f"## Disagreements — {report['n_disagreements']} of {report['n_pairs']}")
    a("")
    a("Row ids only: the authors' answer strings are not republished here.")
    a("`literal_overlap` is the naive baseline feature, banked so a reader can see")
    a("which disagreements a literal-fraction classifier would also have made.")
    a("")
    a("| row id | stratum | hand | predicted | rule | evidence | lit.overlap |")
    a("|---|---|---|---|---|---|---:|")
    for d in report["disagreements"]:
        adm = "" if d["admissible"] else " *(inadmissible)*"
        a(
            f"| `{d['row_id']}`{adm} | {d['stratum']} | `{d['hand_bin']}` | "
            f"`{d['predicted_bin']}` | {d['rule']} | {','.join(d['evidence']) or '—'} | "
            f"{d['literal_overlap']:.2f} |"
        )
    a("")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="B11a agreement against the released hand labels")
    ap.add_argument("csv", help="path to seriesWithLLMs_ext.csv (fetched, never committed)")
    ap.add_argument("--out", required=True, help="directory to bank the output in")
    args = ap.parse_args(argv)

    report = agreement_report(args.csv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Version-tagged, so a re-freeze never overwrites the artefact the previous
    # tag was accepted on. ``b11a-2`` banks ``b11a2_agreement.*``; the ``b11a-1``
    # files stay exactly as they were read.
    stem = CLASSIFIER_VERSION.replace("-", "")
    (out / f"{stem}_agreement.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    (out / f"{stem}_agreement.md").write_text(render_report(report), encoding="utf-8")
    print(json.dumps(
        {k: report["strata"][k]["_overall"] for k in ("dev", "eval_full", "eval_admissible")},
        indent=1,
    ))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
