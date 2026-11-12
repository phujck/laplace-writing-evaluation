"""B11a — the scorer-side bin classifier, on fixtures only.

The authors' CSV is never committed (their repo carries no LICENSE, the article
is CC BY-NC-ND), so every case here is a hand-written fixture in their answer
FORMS, including the encoding damage those forms reached the CSV with. The
agreement run against the real hand labels is a separate, banked artefact
(``synthetics papers/superarc/preregistration/``), not a test.

The load-bearing test is :func:`test_index_only_interpolant_bins_ordinal` — the
memo's named trap. Every literal-overlap feature reads exactly 0.0 on a
minimized index-only interpolant, so a literal-fraction classifier bins it as
genuine abstraction and inflates ρ₁ tenfold in the direction of our own claim.
"""
from __future__ import annotations

import csv

import pytest

from laplace.research.superarc import bin_classifier as bc
from laplace.research.superarc.bin_classifier import Bin, Form

#: 1s at index 0,1,5,10 — the item every ordinal fixture below encodes.
BITS = "1,1,0,0,0,1,0,0,0,0,1,0"
EVENS = "2,4,6,8,10,12,14,16,18,20"
FACTORIONS = "1,2,145,40585"


def _naive_literal_fraction_bin(answer: str, sequence: str) -> Bin:
    """The classifier B11a exists to beat: bin by literal overlap alone. It can
    say PRINTS or not-PRINTS and nothing else, so every ordinal answer falls
    through into the genuine-abstraction bin."""
    if bc.literal_overlap(answer, sequence) >= bc.PRINT_COVER:
        return Bin.CORRECT_PRINTS
    return Bin.CORRECT_NONBOTH


# --------------------------------------------------------------------------- #
# The bins are the notebook's own slices
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "correct,ordinal,copy_seq,expected",
    [
        (True, False, False, Bin.CORRECT_NONBOTH),
        (True, True, False, Bin.CORRECT_ORDINAL),
        (True, False, True, Bin.CORRECT_PRINTS),
        (True, True, True, Bin.CORRECT_ORDINAL),
        (False, False, False, Bin.INCORRECT),
        (False, True, True, Bin.INCORRECT),
    ],
)
def test_hand_bin_transcribes_the_notebook_predicate(correct, ordinal, copy_seq, expected):
    assert bc.hand_bin(correct, ordinal, copy_seq) is expected


def test_bins_are_four_and_named_for_the_rho_vector():
    assert [b.value for b in Bin] == [
        "correct_non_both",
        "correct_ordinal",
        "correct_prints",
        "incorrect",
    ]


# --------------------------------------------------------------------------- #
# THE TRAP: literal-fraction features cannot see ordinal
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "answer",
    [
        # The minimized index-only interpolant, in every released surface form.
        "1 if n in {0,1,5,10} else 0",
        "f(n) = (n == 0 || n == 1 || n == 5 || n == 10)",
        "a(n) = [n in {0,1,5,10}] ? 1 : 0 for n=0..11,",
        "[int(i in [0,1,5,10]) for i in range(12)]",
        # The same support written as a polynomial — not one digit of the item
        # appears anywhere in it.
        "x^11 + x^10 + x^5 + x^0",
        "x^7",
    ],
)
def test_index_only_interpolant_bins_ordinal(answer):
    """The memo's named trap, asserted in both halves at once.

    An index-only interpolant carries none of the item's values, so its literal
    overlap is indistinguishable from a closed form's (``2n`` on the evens scores
    0.1) and far under any print threshold — the literal-fraction classifier
    therefore bins it CORRECT_NONBOTH and inflates ρ₁ tenfold, in exactly the
    direction of our own claim. B11a bins it CORRECT_ORDINAL."""
    assert bc.literal_overlap(answer, BITS) < bc.PRINT_COVER
    assert _naive_literal_fraction_bin(answer, BITS) is Bin.CORRECT_NONBOTH
    v = bc.classify(answer, BITS, correct=True)
    assert v.bin is Bin.CORRECT_ORDINAL, v
    assert v.form is Form.ORDINAL


def test_encoding_damaged_membership_forms_still_read_as_membership():
    """``∈`` reached the CSV as ``_`` in one model's rows and ``_`` stood in for
    spaces in another's. Both are the same test and must bin the same."""
    for answer in (
        "f_(n) = 1 if n _ {1,2,6,11}; else 0",
        "s(n)=1_if_n_in_[0,1,5,10]_else_0",
    ):
        assert bc.classify(answer, BITS, correct=True).bin is Bin.CORRECT_ORDINAL


def test_literal_table_under_an_index_argument_is_ordinal_not_prints():
    """A table keyed by the index is an index→value map — the ordinal class —
    even though its literal overlap with the item is total."""
    answer = "f3(n) = [1,1,0,0,0,1,0,0,0,0,1,0]"
    assert bc.literal_overlap(answer, BITS) == 1.0
    v = bc.classify(answer, BITS, correct=True)
    assert v.bin is Bin.CORRECT_ORDINAL
    assert v.rule == "R3:index-table"


# --------------------------------------------------------------------------- #
# PRINTS — the two prongs, and what they must not swallow
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "answer,sequence",
    [
        ("1,1,0,0,0,1,0,0,0,0,1,0", BITS),
        ("[1,1,0,0,0,1,0,0,0,0,1,0]", BITS),
        ("a_n = 2,4,6,8,10,12,14,16,18,20", EVENS),
        # Prong 2: the truncated copy — opens on the item, then runs out.
        ("90,203,212,235,270,300,000,000,000,000", "90,203,212,235,270,324,342,352,371,417"),
    ],
)
def test_literal_reproduction_bins_prints(answer, sequence):
    assert bc.classify(answer, sequence, correct=True).bin is Bin.CORRECT_PRINTS


def test_literal_accompanied_by_a_rule_is_not_a_print():
    """A print is a print only when the literal IS the answer. ``n!`` generates
    the item; the digits beside it are illustration, not reproduction."""
    v = bc.classify("n! = 1 + 2 + 145 + 40585", FACTORIONS, correct=True)
    assert v.bin is Bin.CORRECT_NONBOTH
    assert v.rule == "R4:literal-with-rule"


def test_short_coincidental_run_is_not_a_print():
    assert bc.classify("[[1,1,0,0]*3][:12]", BITS, correct=True).bin is Bin.CORRECT_NONBOTH


def test_prefix_prong_cannot_fire_on_an_index_enumeration():
    """An index list is strictly increasing; a binary item cannot open on four
    strictly increasing terms. The prong is structurally unreachable here."""
    v = bc.classify("[int(i in [0,1,2,3,4,5]) for i in range(12)]", BITS, correct=True)
    assert v.bin is Bin.CORRECT_ORDINAL


# --------------------------------------------------------------------------- #
# ABSTRACTION — generative rules, including ones wearing positional clothes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "answer,sequence",
    [
        ("2n", EVENS),
        ("2*n", EVENS),
        ("a_n = 2n", EVENS),
        ("a_n = 2n,for n >= 1", EVENS),  # a domain is not a predicate
        ("2n for n in range(1,11)", EVENS),
        ("lambda n: 2n", EVENS),
        ("n+10", EVENS),
        ("n^2", "1,4,9,16,25,36,49,64,81,100"),
        ("2^(n-1)", "1,2,4,8,16,32,64,128,256,512"),
        ("Fibonacci(n)", "1,1,2,3,5,8,13,21,34,55"),
        ("a(n) = a(n-1) + a(n-2)", "1,1,2,3,5,8,13,21,34,55"),
        ("C(2n,n)", "1,2,6,20,70,252,924,3432,12870,48620"),
        ("f(n) = (n % 5 == 0) ? 1 : 0", BITS),
        ("y = 1 - |x mod 3 - 1|", BITS),
        # A generative rule with a positional exception is still generative.
        ("f(n) = (n + 1) mod 2 == 0 && n != 6", BITS),
        ("[int(bin(i).count(1)%2==1) for i in range(12)]", BITS),
    ],
)
def test_generative_rules_bin_non_both(answer, sequence):
    assert bc.classify(answer, sequence, correct=True).bin is Bin.CORRECT_NONBOTH


def test_monomial_support_clause_is_binary_only():
    """``n^2`` on an integer item is a closed form, not an index support set —
    the clause that reads ``x^7`` as position 7 must not reach it."""
    assert bc.classify_form("n^2", "1,4,9,16,25,36,49,64,81,100").form is Form.ABSTRACTION
    assert bc.classify_form("x^7", BITS).form is Form.ORDINAL


# --------------------------------------------------------------------------- #
# Correctness is an INPUT — the non-circularity invariant
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "answer",
    ["1,1,0,0,0,1,0,0,0,0,1,0", "1 if n in {0,1,5,10} else 0", "f(n) = (n+1) mod 2 == 0"],
)
def test_incorrect_answers_bin_incorrect_whatever_their_form(answer):
    v = bc.classify(answer, BITS, correct=False)
    assert v.bin is Bin.INCORRECT
    # The form survives — the bin is the product of form and correctness, and a
    # wrong answer's form is still evidence.
    assert v.form in (Form.PRINTS, Form.ORDINAL, Form.ABSTRACTION)


def test_form_is_independent_of_correctness():
    for answer in ("1,1,0,0,0,1,0,0,0,0,1,0", "2n", "1 if n in {0,1,5,10} else 0"):
        a = bc.classify(answer, BITS, correct=True).form
        b = bc.classify(answer, BITS, correct=False).form
        assert a is b


# --------------------------------------------------------------------------- #
# R0/R1 — alternatives and non-answers
# --------------------------------------------------------------------------- #


def test_first_alternative_binds():
    answer = (
        '["[int(i in [0,1,5,10]) for i in range(12)]","[[1,1,0,0]*3][:12]",'
        '"[int(i%5==0 or i<2) for i in range(12)]"],'
    )
    assert bc.select_alternative(answer) == "[int(i in [0,1,5,10]) for i in range(12)]"
    assert bc.classify(answer, BITS, correct=True).bin is Bin.CORRECT_ORDINAL


def test_a_bare_literal_list_is_not_an_alternative_list():
    assert bc.select_alternative("[1,1,0,0,0,1,0,0,0,0,1,0]") == "[1,1,0,0,0,1,0,0,0,0,1,0]"


@pytest.mark.parametrize("answer", ["", "   ", "***", "*not found", "*"])
def test_missing_answers_are_typed_not_guessed(answer):
    v = bc.classify_form(answer, BITS)
    assert v.form is Form.NO_ANSWER
    assert v.rule == "R1:missing"


# --------------------------------------------------------------------------- #
# The naive baseline, kept honest
# --------------------------------------------------------------------------- #


def test_literal_overlap_is_a_fraction_of_the_item():
    assert bc.literal_overlap("1,1,0,0,0,1,0,0,0,0,1,0", BITS) == 1.0
    assert bc.literal_overlap("2n", EVENS) == pytest.approx(0.1)
    assert bc.literal_overlap("nothing numeric", BITS) == 0.0


def test_longest_common_run_is_contiguous():
    assert bc.longest_common_run([1, 2, 3, 9, 4, 5], [1, 2, 3, 4, 5]) == 3
    assert bc.longest_common_run([], [1]) == 0


# --------------------------------------------------------------------------- #
# C-1 — the dialect an answer is typed in must not move it between bins
# --------------------------------------------------------------------------- #
#
# The adversarial calibration verdict's C-1: under b11a-1 ``_marker_text`` deleted
# every non-ASCII codepoint, which (a) destroyed ``≤ ≥ ≠`` so the interval
# predicate could not fire, and (b) manufactured a phantom ``index-coefficient``
# out of the gap (``8 ≤ n`` → ``8   n``). Both pushed toward the ×1 abstraction
# bin, and only one arm wrote that dialect.
#
# The eight rows below are the A1 pilot answers C-1 names — the evidence the
# instrument lacked dialect invariance, and now its regression fixtures. Each is
# the answer VERBATIM, paired with the spelling an ASCII-dialect author would
# have typed for the same formula. Preregistered as acceptance fixture D-1 in
# ``synthetics papers/superarc/preregistration/b11a2_threshold.md``.

#: (item id, sequence, Unicode spelling as banked, ASCII spelling of the same formula)
C1_ROWS: tuple[tuple[str, str, str, str], ...] = (
    (
        "dev-0-014", "0,0,0,0,0,0,0,0,1,1,0,1",
        "a(n) = [n ≥ 8] · [n ≠ 10]  (n = 0..11)",
        "a(n) = [n >= 8] * [n != 10]  (n = 0..11)",
    ),
    (
        "dev-0-038", "1,1,1,0,1,1,1,1,0,0,1,1",
        "a(n) = 1 − [n ∈ {3} ∪ {8,9}] = 1 − [n = 3] − [8 ≤ n ≤ 9]  (n = 0..11)",
        "a(n) = 1 - [n in {3} | {8,9}] = 1 - [n = 3] - [8 <= n <= 9]  (n = 0..11)",
    ),
    (
        "dev-1-010", "1,1,1,1,0,0,0,1,1,1,1,0",
        "run-length model, runs of (1,0,1,0) with lengths 4,3,4,1: "
        "a(n) = 1 − [4 ≤ n ≤ 6] − [n = 11]  (n = 0..11)",
        "run-length model, runs of (1,0,1,0) with lengths 4,3,4,1: "
        "a(n) = 1 - [4 <= n <= 6] - [n = 11]  (n = 0..11)",
    ),
    (
        "dev-1-022", "1,1,1,1,1,0,1,0,1,0,1,1",
        "a(n) = 1 − [5 ≤ n ≤ 9] · [n odd]  (n = 0..11)",
        "a(n) = 1 - [5 <= n <= 9] * [n odd]  (n = 0..11)",
    ),
    (
        "dev-1-028", "0,0,1,1,1,1,0,0,0,0,0,1",
        "run-length model (0,1,0,1) with lengths 2,4,5,1: "
        "a(n) = [2 ≤ n ≤ 5] + [n = 11]  (n = 0..11)",
        "run-length model (0,1,0,1) with lengths 2,4,5,1: "
        "a(n) = [2 <= n <= 5] + [n = 11]  (n = 0..11)",
    ),
    (
        "dev-2-018", "1,1,1,0,1,1,0,0,0,1,1,1",
        "a(n) = 1 − [n = 3] − [6 ≤ n ≤ 8]  (n = 0..11)",
        "a(n) = 1 - [n = 3] - [6 <= n <= 8]  (n = 0..11)",
    ),
    (
        "dev-2-030", "0,0,1,1,1,0,0,0,0,1,1,0",
        "run-length model (0,1,0,1,0) with lengths 2,3,4,2,1: "
        "a(n) = [2 ≤ n ≤ 4] + [9 ≤ n ≤ 10]  (n = 0..11)",
        "run-length model (0,1,0,1,0) with lengths 2,3,4,2,1: "
        "a(n) = [2 <= n <= 4] + [9 <= n <= 10]  (n = 0..11)",
    ),
    (
        "dev-2-036", "0,0,1,1,1,1,1,0,0,0,1,1",
        "run-length model (0,1,0,1) with lengths 2,5,3,2: "
        "a(n) = [2 ≤ n ≤ 6] + [n ≥ 10]  (n = 0..11)",
        "run-length model (0,1,0,1) with lengths 2,5,3,2: "
        "a(n) = [2 <= n <= 6] + [n >= 10]  (n = 0..11)",
    ),
)


def _squash(s: str) -> str:
    """Whitespace runs are immaterial to every decision rule (they all match
    ``\\s*``); the transliteration of ``∈`` to `` in `` pads by one space."""
    return " ".join(s.split())


@pytest.mark.parametrize("item,sequence,unicode_form,ascii_form", C1_ROWS, ids=[r[0] for r in C1_ROWS])
def test_c1_rows_bin_the_same_in_both_dialects(item, sequence, unicode_form, ascii_form):
    """The C-1 fixture, both halves at once: the two spellings of one formula
    reduce to ONE marker string, and both bin ORDINAL — an index lookup with a
    positional predicate and no rule in the residue.

    Under b11a-1 the Unicode spelling binned CORRECT_NONBOTH (×1) and the ASCII
    spelling CORRECT_ORDINAL (×1/10): a factor of ten in φ decided by a keystroke,
    on eight of one arm's twenty rows."""
    assert _squash(bc._marker_text(unicode_form)) == _squash(bc._marker_text(ascii_form))
    uni = bc.classify(unicode_form, sequence, correct=True)
    asc = bc.classify(ascii_form, sequence, correct=True)
    assert uni.bin is asc.bin is Bin.CORRECT_ORDINAL, (item, uni, asc)
    assert uni.form is asc.form is Form.ORDINAL
    assert uni.rule == asc.rule == "R3:positional"


def test_c1_rows_are_not_reachable_by_literal_overlap():
    """These are formulas, not copies: the naive baseline sees nothing in them,
    so the bin they belong in can only be reached structurally."""
    for item, sequence, unicode_form, _ascii in C1_ROWS:
        assert bc.literal_overlap(unicode_form, sequence) < bc.PRINT_COVER, item
        assert _naive_literal_fraction_bin(unicode_form, sequence) is Bin.CORRECT_NONBOTH


@pytest.mark.parametrize(
    "unicode_form,ascii_form",
    [
        ("8 ≤ n ≤ 9", "8 <= n <= 9"),
        ("n ≥ 3", "n >= 3"),
        ("n ≠ 10", "n != 10"),
        ("2 · n", "2 * n"),
        ("2 × n", "2 * n"),
        ("11 − n", "11 - n"),
        ("n — 1", "n - 1"),
        ("⌊x / 2⌋", "floor(x / 2)"),
        ("⌈x / 2⌉", "ceil(x / 2)"),
        ("n ∈ {0,1,5}", "n in {0,1,5}"),
        ("x¹¹ + x¹⁰", "x^11 + x^10"),
        ("2ⁿ⁻¹", "2^(n-1)"),
        ("1178 = 010010011010₂", "1178 = 010010011010_2"),
    ],
)
def test_transliteration_is_the_ascii_spelling(unicode_form, ascii_form):
    assert _squash(bc.transliterate_math(unicode_form)) == _squash(ascii_form)


def test_transliteration_is_a_no_op_on_ascii():
    for s in ("a(n) = [n >= 8] * [n != 10]", "x^11 + x^10 + x^5 + x^0", "", "2n"):
        assert bc.transliterate_math(s) == s


def test_a_stripped_operator_manufactures_no_generative_marker():
    """C-1 clause (b). ``8 ≤ n`` became ``8   n`` under b11a-1, which IS the
    ``index-coefficient`` pattern ``\\d\\s*\\*?\\s*n\\b`` — the deletion invented a
    rule that was never written, and the invented rule outranked the predicate."""
    marker = bc._marker_text("a(n) = [8 ≤ n ≤ 9]")
    fired = [name for name, pat in bc._GENERATIVE_RES if pat.search(marker)]
    assert fired == [], marker
    v = bc.classify_form("a(n) = [8 ≤ n ≤ 9]", BITS)
    assert v.form is Form.ORDINAL
    assert v.rule == "R3:positional"


def test_not_equal_does_not_read_as_a_factorial():
    """The repair must not re-commit clause (b) in ASCII: ``≠`` transliterates to
    ``!=``, and an unguarded ``!`` marker would read that as a factorial."""
    for text in ("10 ≠ n", "10 != n"):
        marker = bc._marker_text(text)
        fired = [name for name, pat in bc._GENERATIVE_RES if pat.search(marker)]
        assert "factorial" not in fired, (text, marker, fired)
    # …while a real factorial still fires.
    assert bc.classify("n! = 1 + 2 + 145 + 40585", FACTORIONS, correct=True).rule == (
        "R4:literal-with-rule"
    )


def test_superscript_polynomial_support_is_still_the_ordinal_trap():
    """The preregistration's §7 fixture, in the superscript dialect. The
    transliteration must leave a bare-digit exponent unparenthesised or the
    monomial-support clause stops matching and the trap reopens."""
    for answer in ("x¹¹ + x¹⁰ + x⁵ + x⁰", "x^11 + x^10 + x^5 + x^0"):
        v = bc.classify(answer, BITS, correct=True)
        assert v.bin is Bin.CORRECT_ORDINAL, answer
        assert v.rule == "R3:monomial-support"


def test_an_em_dash_gloss_does_not_move_a_generative_answer():
    """The only non-ASCII the loop arms wrote is an em dash in a prose gloss.
    It transliterates to a hyphen and the answer stays what it was.

    The gloss carries a constant (``rule 110``) and a base power (``2^…``) — the
    two surfaces S-1's decode excision touches — so this fixture is also the
    check that S-1 does not reach an answer whose constant is a RULE NUMBER
    rather than the item packed."""
    for text in (
        "a(n) = ECA rule 110 on a cyclic 12-cell ring, index 2^(l) — read after 2 generations.",
        "a(n) = ECA rule 110 on a cyclic 12-cell ring, index 2^(l) - read after 2 generations.",
    ):
        assert bc.base_encoded_literal(text, BITS) is None
        assert bc.classify(text, BITS, correct=True).bin is Bin.CORRECT_NONBOTH


def test_classifier_version_is_the_s1_refreeze():
    """The freeze tag is load-bearing: every banked number names the tag it was
    scored under, and a rule change without a new tag is the failure the
    preregistration exists to prevent. ``b11a-3`` is S-1 and nothing else."""
    assert bc.CLASSIFIER_VERSION == "b11a-3"


# --------------------------------------------------------------------------- #
# S-1 — the base-encoded literal (b11a-3)
# --------------------------------------------------------------------------- #
#
# The rule: an answer whose load-bearing content is a constant whose DIGIT
# EXPANSION is the target sequence is a print in integer clothing — the paper's
# own ``copy_seq`` written in base 2. ``b11a-2`` binned every such answer ×1
# genuine abstraction, because ``int_tokens`` reads the packed constant as ONE
# integer and ``longest_common_run`` compares it against nothing.
#
# Preregistered in ``synthetics papers/superarc/preregistration/s1_rule.md``,
# written and applied SYMMETRICALLY — to the pilot's three arms and to the
# authors' released answers — in the same commit that lands it.
#
# The eight A1 pilot rows below are the acceptance fixture: the report's own
# §6 limitation probe (``sensitivity_S1_base_encoded_literal``) named exactly
# these eight and declined to apply the rebin, because applying it post hoc to
# lower a comparator arm is the metric gaming SR-1 forbids. They are here as a
# preregistered rule instead.

#: (item id, sequence, the A1 answer verbatim, the packed constant)
S1_A1_ROWS: tuple[tuple[str, str, str, int], ...] = (
    ("dev-0-008", "0,1,0,0,1,0,0,1,1,0,1,0",
     "a(n) = floor(1178 / 2^(11−n)) mod 2 (n = 0..11; 1178 = 010010011010₂)", 1178),
    ("dev-0-020", "0,0,0,0,0,0,1,0,0,1,1,0",
     "a(n) = floor(38 / 2^(11−n)) mod 2 (n = 0..11; 38 = 000000100110₂)", 38),
    ("dev-0-026", "0,0,0,0,1,0,1,1,0,1,0,0",
     "a(n) = floor(180 / 2^(11−n)) mod 2 (n = 0..11; 180 = 000010110100₂)", 180),
    ("dev-0-032", "0,0,1,0,1,0,0,0,0,0,1,0",
     "a(n) = floor(642 / 2^(11−n)) mod 2 (n = 0..11; 642 = 001010000010₂)", 642),
    ("dev-1-004", "0,0,1,0,1,1,1,0,1,0,1,0",
     "a(n) = floor(746 / 2^(11−n)) mod 2 (n = 0..11; 746 = 001011101010₂)", 746),
    ("dev-1-016", "0,0,1,1,0,0,0,0,0,0,1,0",
     "a(n) = floor(770 / 2^(11−n)) mod 2 (n = 0..11; 770 = 001100000010₂)", 770),
    ("dev-2-000", "0,1,1,0,0,1,1,1,0,1,1,0",
     "a(n) = floor(1654 / 2^(11−n)) mod 2 (n = 0..11; 1654 = 011001110110₂)", 1654),
    ("dev-2-006", "0,1,0,1,1,1,1,0,0,0,1,0",
     "a(n) = floor(1506 / 2^(11−n)) mod 2 (n = 0..11; 1506 = 010111100010₂)", 1506),
)


@pytest.mark.parametrize(
    "item,sequence,answer,constant", S1_A1_ROWS, ids=[r[0] for r in S1_A1_ROWS]
)
def test_s1_pilot_fixtures_bin_prints(item, sequence, answer, constant):
    """The acceptance fixture. Each answer carries the whole item inside one
    decimal constant plus a decoder, and nothing else; under ``b11a-2`` all eight
    binned ×1 genuine abstraction."""
    hit = bc.base_encoded_literal(answer, sequence)
    assert hit is not None, item
    assert hit.value == constant
    assert hit.base == 2
    v = bc.classify(answer, sequence, correct=True)
    assert v.bin is Bin.CORRECT_PRINTS, (item, v)
    assert v.form is Form.PRINTS
    assert v.rule == "S1:base-encoded-literal"


def test_s1_pilot_fixtures_are_invisible_to_the_print_filter_that_preceded_it():
    """Why the clause had to be written at all: R2 compares INTEGER TOKENS, and
    a packed constant is one token. The naive literal baseline reads these as
    abstraction too — the whole point is that no literal-overlap feature can see
    them."""
    for item, sequence, answer, _k in S1_A1_ROWS:
        assert bc.literal_overlap(answer, sequence) < bc.PRINT_COVER, item
        assert bc.longest_common_run(bc.int_tokens(answer), [int(t) for t in sequence.split(",")]) < 3
        assert _naive_literal_fraction_bin(answer, sequence) is Bin.CORRECT_NONBOTH


def test_s1_does_not_touch_a_genuine_short_constant():
    """THE discriminating case, and the one the threshold exists for. A modulus
    is a real model: ``29`` compresses a twelve-term item better than 2:1, and no
    reading of its five bits is the item. S-1 must leave it exactly where the
    rest of the classifier put it."""
    seq = "1,0,0,1,1,0,1,0,0,1,1,0"
    answer = "a(n) = 1 if (n^2 mod 29) < 17 else 0  (n = 0..11)"
    assert bc.base_encoded_literal(answer, seq) is None
    v = bc.classify(answer, seq, correct=True)
    assert v.bin is Bin.CORRECT_NONBOTH
    assert v.rule != "S1:base-encoded-literal"


@pytest.mark.parametrize(
    "answer,sequence",
    [
        # a modulus, on the item the pilot's own A1 wrote it against
        ("a(n) = [n ≥ 3] · [n mod 3 = 0] (n = 0..11)", "0,0,0,1,0,0,1,0,0,1,0,0"),
        # ECA rule numbers — the mint set, and the numbers A2/A3 answered with
        ("a(n) = ECA rule 30 on a cyclic 12-cell ring, seed = cell 11 set, after 20 generations",
         "0,0,1,0,1,1,1,0,1,0,1,0"),
        ("a(n) = ECA rule 110, cyclic on 12 cells, 2 steps", "0,0,1,1,0,0,0,0,0,0,1,0"),
        # an LFSR seed and a rational denominator: short constants, real models
        ("a(n) = bit n of an LFSR with seed 23, taps 12 and 7", "0,1,0,0,1,0,0,1,1,0,1,0"),
        ("a(n) = n-th binary digit of 1/87", "0,0,1,0,1,0,0,0,0,0,1,0"),
        ("a(n) = floor(n * 59 / 100) mod 2", "0,1,1,0,0,1,1,1,0,1,1,0"),
    ],
)
def test_s1_leaves_the_attested_short_constants_alone(answer, sequence):
    """The corpus's real constants, none of them touched. Two independent
    reasons, and the test asserts the outcome rather than the reason: `29`,
    `30`, `23` are shorter than half their item's symbols and die on the length
    gate; `110`, `150`, `87`, `59` clear the gate and die on the match, because
    their expansions are not the item. The gate is what stops a SHORT expansion
    matching by accident; the match is what stops a long one that is not the
    item."""
    assert bc.base_encoded_literal(answer, sequence) is None


def test_s1_reads_the_constant_as_written_when_it_is_spelled_out():
    """A spelled-out bit string is the case B11a was blindest to: it reaches
    ``int_tokens`` as ONE integer. Leading zeros are part of what was written, so
    the length gate sees twelve symbols and not six."""
    seq = "0,0,0,0,0,0,1,0,0,1,1,0"
    hit = bc.base_encoded_literal("a(n) = the n-th digit of 000000100110", seq)
    assert hit is not None
    assert (hit.base, hit.reading, hit.digits) == (10, "written", "000000100110")
    # …and the same constant delivered as a program's print statement — the form
    # three of the authors' released models used.
    hit = bc.base_encoded_literal('print("000000100110")', seq)
    assert hit is not None and hit.reading == "written"


def test_s1_tolerates_the_little_endian_reading():
    """``(K >> n) & 1`` walks the constant LSB-first. It is the same packing with
    the bits read the other way, and it is the form the authors' released
    ``gemini_2.5_pro`` programs are written in."""
    hit = bc.base_encoded_literal(
        "print(', '.join(str((1059 >> i) & 1) for i in range(12)))", BITS
    )
    assert hit is not None
    assert (hit.value, hit.orientation) == (1059, "reversed")
    assert bc.classify_form(
        "print(', '.join(str((1059 >> i) & 1) for i in range(12)))", BITS
    ).rule == "S1:base-encoded-literal"


def test_s1_tolerates_an_offset_and_a_hex_spelling():
    """Spare digits either side of the item, and the same constant in base 16.
    ``0x386`` is 902 is ``001110000110`` — one of the pilot's own A3 answers
    spells it both ways in the same sentence."""
    seq = "0,0,1,1,1,0,0,0,0,1,1,0"
    hit = bc.base_encoded_literal("a(n) = floor(902 / 2^(11-n)) mod 2 (0x386)", seq)
    assert hit is not None and hit.value == 902
    # base 16 is admissible in its own right, on an item whose terms are all
    # single hex digits.
    hexseq = "1,0,15,3,0,0,0,0,1,2,10,12"
    hexhit = bc.base_encoded_literal("a(n) = digit n of 0x10f3000012ac", hexseq)
    assert hexhit is not None and hexhit.base == 16
    # an offset window: the item sits inside a longer expansion
    off = bc.base_encoded_literal("a(n) = digits 1..12 of 11001110110011", "1,0,0,1,1,1,0,1,1,0,0,1")
    assert off is not None and off.offset > 0


def test_s1_does_not_run_on_a_short_item():
    """On a four- or five-term sequence a two-digit constant matching is
    ordinary, not evidence. The released suite has two such items."""
    assert bc.base_encoded_literal("a(n) = bit n of 13", "1,1,0,1") is None
    assert bc.base_encoded_literal("a(n) = bit n of 26", "1,1,0,1,0") is None


def test_s1_spares_a_constant_that_compresses_better_than_two_to_one():
    """The threshold is a threshold, and it is stated in both directions: ``13``
    on an item whose whole content is four trailing bits is a real 3:1
    compression and S-1 does not touch it, even though the DECODER is identical
    to the eight fixtures above. The authors' released corpus contains exactly
    this case (``gemini_2.5_pro`` row 7, constant 7) and it is spared there too.
    A rule that hit it would be a rule about the decoder, not about the
    constant."""
    seq = "0,0,0,0,0,0,0,0,1,1,0,1"
    answer = "a(n) = floor(13 / 2^(11-n)) mod 2 (the 12-bit expansion of 13)"
    assert bc.base_encoded_literal(answer, seq) is None
    assert bc.classify(answer, seq, correct=True).bin is Bin.CORRECT_NONBOTH


def test_s1_does_not_reach_a_literal_that_is_not_the_target():
    """An ECA seed is a twelve-bit literal that is NOT the item: it is the input
    to a named one-step rule, and the answer's content is the rule. Four A3
    pilot rows are of this form, and S-1 is strictly narrower than the skeptic's
    K2 regime precisely here."""
    seq = "1,1,1,0,1,1,0,0,0,1,1,1"
    answer = (
        "Elementary cellular automaton rule 90 (a_i = s_{i-1} XOR s_{i+1}) applied for "
        "1 step with cyclic boundary to the 12-cell seed 110001111100."
    )
    assert bc.base_encoded_literal(answer, seq) is None
    assert bc.classify(answer, seq, correct=True).bin is Bin.CORRECT_NONBOTH


def test_s1_does_not_fire_when_a_real_rule_survives_the_decoder_excision():
    """The escape, and its blast radius. The decode machinery — the base power,
    the extracting mod/mask/shift, the truncating wrapper, the prose naming an
    expansion — is excised ONLY inside the S-1 clause and only on an answer
    already proven to carry the whole item in one constant. A generative marker
    that survives that excision is a real rule, and the answer is not a copy."""
    seq = "0,0,0,0,0,0,1,0,0,1,1,0"
    packed = "a(n) = floor(38 / 2^(11-n)) mod 2"
    assert bc.classify_form(packed, seq).rule == "S1:base-encoded-literal"
    for extra in (" + n^2", " XOR Fibonacci(n)", " XOR prime(n)"):
        with_rule = packed + extra
        # the constant is still there — it is the RESIDUE that changes the bin
        assert bc.base_encoded_literal(with_rule, seq) is not None, extra
        assert bc.classify_form(with_rule, seq).rule != "S1:base-encoded-literal", extra


def test_s1_over_excision_is_bounded_by_correctness_being_an_input():
    """Stated rather than hidden: the excision is coarse, and a SECOND modular
    term is swallowed with the extracting one (``… mod 2 XOR [n mod 5]`` reads as
    a bare copy). The blast radius is nil for one reason only — if the constant
    already IS the item, an answer that then XORs something else does not
    reproduce the item, so the executor calls it wrong and it bins ρ₄ whatever
    its form. Correctness is an input; S-1 cannot promote a wrong answer."""
    seq = "0,0,0,0,0,0,1,0,0,1,1,0"
    over = "a(n) = floor(38 / 2^(11-n)) mod 2 XOR [n mod 5]"
    assert bc.classify_form(over, seq).rule == "S1:base-encoded-literal"
    assert bc.classify(over, seq, correct=False).bin is Bin.INCORRECT


def test_s1_is_monotone_it_can_only_move_a_row_down():
    """The property that makes symmetric application countable rather than
    arguable: the clause either returns PRINTS or falls through, so applying S-1
    to a corpus subtracts from the ×1 and ×1/10 bins and never adds to them.
    Checked over every fixture in this module that S-1 fires on."""
    corpus = [(a, s) for _i, s, a, _k in S1_A1_ROWS]
    corpus += [
        ("a(n) = [n ≥ 8] · [n ≠ 10]  (n = 0..11)", "0,0,0,0,0,0,0,0,1,1,0,1"),
        ("x^11 + x^10 + x^5 + x^0", BITS),
        ("a(n) = 1 if (n^2 mod 29) < 17 else 0", "1,0,0,1,1,0,1,0,0,1,1,0"),
        ("1,1,0,0,0,1,0,0,0,0,1,0", BITS),
    ]
    order = {Bin.CORRECT_NONBOTH: 3, Bin.CORRECT_ORDINAL: 2, Bin.CORRECT_PRINTS: 1}
    real = bc.base_encoded_literal
    try:
        for answer, sequence in corpus:
            after = bc.classify(answer, sequence, correct=True)
            bc.base_encoded_literal = lambda _a, _s: None  # b11a-2, exactly
            before = bc.classify(answer, sequence, correct=True)
            bc.base_encoded_literal = real
            assert order[after.bin] <= order[before.bin], (answer, before, after)
    finally:
        bc.base_encoded_literal = real


def test_s1_never_infers_correctness():
    """Invariant 1 holds through the new clause: a packed constant that the
    executor calls wrong is INCORRECT, not a print."""
    item, sequence, answer, _k = S1_A1_ROWS[0]
    assert bc.classify(answer, sequence, correct=False).bin is Bin.INCORRECT
    assert bc.classify_form(answer, sequence).form is Form.PRINTS


# --------------------------------------------------------------------------- #
# The agreement harness — on a synthetic label set, never theirs
# --------------------------------------------------------------------------- #


def _write_label_csv(path, rows):
    cols = [
        "sequence",
        "alpha-formula",
        "alpha-formula-correctness",
        "alpha-formula-copy_seq",
        "alpha-formula-ordinal",
        "beta-formula",
        "beta-formula-correctness",
        "beta-formula-copy_seq",
        "beta-formula-ordinal",
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def _row(seq, a, a_c, a_p, a_o, b, b_c, b_p, b_o):
    return {
        "sequence": seq,
        "alpha-formula": a,
        "alpha-formula-correctness": a_c,
        "alpha-formula-copy_seq": a_p,
        "alpha-formula-ordinal": a_o,
        "beta-formula": b,
        "beta-formula-correctness": b_c,
        "beta-formula-copy_seq": b_p,
        "beta-formula-ordinal": b_o,
    }


def test_load_label_set_drops_unanswered_pairs(tmp_path):
    path = _write_label_csv(
        tmp_path / "labels.csv",
        [
            _row(EVENS, "2n", "True", "False", "False", "", "", "", ""),
            _row(BITS, BITS, "True", "True", "False", "2n", "False", "False", "False"),
        ],
    )
    pairs = bc.load_label_set(path)
    assert {p.row_id for p in pairs} == {"alpha#0", "alpha#1", "beta#1"}
    assert {p.stratum for p in pairs} <= {"dev", "eval"}


def test_inadmissible_copy_column_needs_byte_identical_proof(tmp_path):
    """An all-False ``copy_seq`` column is only INADMISSIBLE when the model
    actually emitted a byte-identical copy. Byte identity is not a judgement
    call, so the audit cannot be steered by the classifier it protects."""
    path = _write_label_csv(
        tmp_path / "labels.csv",
        [
            # alpha copied the item verbatim and was labelled not-a-copy.
            _row(BITS, BITS, "True", "False", "True", "2n", "True", "False", "False"),
            _row(EVENS, "2n", "True", "False", "False", "4n", "False", "False", "False"),
        ],
    )
    inad = bc.inadmissible_copy_columns(bc.load_label_set(path))
    assert list(inad) == ["alpha"]
    assert inad["alpha"] == ["alpha#0"]


def test_agreement_report_enumerates_every_disagreement(tmp_path):
    path = _write_label_csv(
        tmp_path / "labels.csv",
        [
            _row(BITS, BITS, "True", "True", "False", "2n", "False", "False", "False"),
            # beta's closed form is hand-labelled ordinal — a real disagreement.
            _row(EVENS, "2n", "True", "False", "False", "2n", "True", "False", "True"),
        ],
    )
    report = bc.agreement_report(path)
    assert report["classifier_version"] == bc.CLASSIFIER_VERSION
    assert report["n_pairs"] == 4
    assert report["n_disagreements"] == len(report["disagreements"]) == 1
    d = report["disagreements"][0]
    assert d["row_id"] == "beta#1"
    assert d["hand_bin"] == "correct_ordinal"
    assert d["predicted_bin"] == "correct_non_both"
    # Row ids and rules only — the answer string is never republished.
    assert "answer" not in d
    assert set(report["strata"]) == {"dev", "eval_full", "eval_admissible", "all"}
    assert report["strata"]["all"]["_overall"]["n"] == 4
    assert bc.render_report(report).startswith("# B11a agreement")


def test_strata_split_is_stable_and_content_addressed(tmp_path):
    path = _write_label_csv(
        tmp_path / "labels.csv",
        [_row(EVENS, "2n", "True", "False", "False", "4n", "True", "False", "False")],
    )
    first = {p.row_id: p.stratum for p in bc.load_label_set(path)}
    second = {p.row_id: p.stratum for p in bc.load_label_set(path)}
    assert first == second
