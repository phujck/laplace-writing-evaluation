"""B11b — A2's submission gate. Fixtures for each refusal class, plus the
tightness relation against B11a (imported HERE and nowhere in the organ)."""
from __future__ import annotations

import pytest

from laplace.research.superarc import bin_classifier as b11a
from laplace.research.superarc import submission_gate as sg
from laplace.research.superarc.submission_gate import GateDecision

# --------------------------------------------------------------------------- #
# Items
# --------------------------------------------------------------------------- #

FIB = "1,1,2,3,5,8,13,21,34,55"
POW2 = "1,2,4,8,16,32,64,128,256,512"
TRI = "0,1,3,6,10,15,21,28,36,45"
DOUBLE = "0,1,3,7,15,31,63,127,255,511"
BIN12 = "1,1,0,0,0,1,0,0,0,0,1,0"
BIN16 = "1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,0"
LONG = "90,203,212,235,270,324,398,495,617,766,944,1153"

# (label, answer, item) — every fixture is named by the class it belongs to.
GENUINE = [
    ("recurrence", "a(n) = a(n-1) + a(n-2), a(0)=1, a(1)=1", FIB),
    ("closed-form", "a(n) = 2**n", POW2),
    ("modular", "a(n) = 1 if n % 4 == 0 else 0", BIN16),
    ("polynomial", "def f(n): return n*(n+1)//2", TRI),
    ("domain-decl", "a(n) = a(n-1)*2 + 1 for n >= 1, a(0) = 0", DOUBLE),
    ("base-case", "a(n) = 1 if n < 2 else a(n-1) + a(n-2)", FIB),
]

PRINTS = [
    ("bare-copy", FIB, FIB),
    ("padded-copy", FIB + " " + "z" * 400, FIB),
    ("truncated-copy", "90,203,212,235,270,300,000,000", LONG),
    ("copy-with-rule", "a(n) = a(n-1)+a(n-2) with " + FIB, FIB),
]

LOOKUPS = [
    ("period-table", "a(n) = [1,1,0,0][n % 4]", BIN16),
    ("dict-table", "d = {0:1, 1:1, 2:2, 3:3}; a(n) = d[n]", FIB),
]

POSITIONAL = [
    ("membership", "s(n) = 1 if n in [0,1,5,10] else 0", BIN12),
    ("monomial-support", "x^11 + x^10 + x^5 + x^0", BIN12),
    ("exception-decoy", "a(n) = n mod 2 if n != 6 else 1", BIN12),
    ("equality-chain", "a(n) = 1 if n==0 or n==1 or n==5 or n==10 else 0", BIN12),
]

ALL_FIXTURES = (
    [(lbl, a, s) for lbl, a, s in GENUINE]
    + [(lbl, a, s) for lbl, a, s in PRINTS]
    + [(lbl, a, s) for lbl, a, s in LOOKUPS]
    + [(lbl, a, s) for lbl, a, s in POSITIONAL]
)


# --------------------------------------------------------------------------- #
# The four classes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("label,answer,item", GENUINE, ids=[f[0] for f in GENUINE])
def test_genuine_models_pass(label, answer, item):
    d = sg.gate(answer, item)
    assert d.admitted, (label, d.reason, d.clause, d.metrics)
    assert d.reason == "admitted"


@pytest.mark.parametrize("label,answer,item", PRINTS, ids=[f[0] for f in PRINTS])
def test_print_like_refused(label, answer, item):
    d = sg.gate(answer, item)
    assert not d.admitted, (label, d.metrics)
    assert d.reason == "literal-data"
    assert d.metrics["literal_cover"] > sg.LITERAL_COVER_MAX


@pytest.mark.parametrize("label,answer,item", LOOKUPS, ids=[f[0] for f in LOOKUPS])
def test_lookup_tables_refused(label, answer, item):
    d = sg.gate(answer, item)
    assert not d.admitted, (label, d.metrics)
    assert d.reason == "lookup-table"
    assert d.metrics["table"] and d.metrics["index_access"]


@pytest.mark.parametrize("label,answer,item", POSITIONAL, ids=[f[0] for f in POSITIONAL])
def test_positional_fits_refused(label, answer, item):
    d = sg.gate(answer, item)
    assert not d.admitted, (label, d.metrics)
    assert d.reason == "positional-fit"


def test_dict_lookup_is_caught_by_the_table_clause_not_the_fraction():
    """The clauses are independent: this table carries too little of the item to
    trip the literal fraction, and is still a lookup."""
    d = sg.gate("d = {0:1, 1:1, 2:2, 3:3}; a(n) = d[n]", FIB)
    assert d.metrics["literal_cover"] <= sg.LITERAL_COVER_MAX
    assert d.reason == "lookup-table"


def test_monomial_fit_carries_no_literal_data():
    """The index-only interpolant the literal fraction cannot see."""
    d = sg.gate("x^11 + x^10 + x^5 + x^0", BIN12)
    assert d.metrics["literal_cover"] <= sg.LITERAL_COVER_MAX
    assert d.clause == "G4:monomial-support"


def test_monomial_shape_on_an_integer_item_is_not_a_fit():
    assert sg.gate("a(n) = n**2 + n**1", POW2).admitted


# --------------------------------------------------------------------------- #
# Normalization — the gate reads the normalized string, and padding cannot dilute
# --------------------------------------------------------------------------- #


def test_padding_cannot_dilute_the_literal_fraction():
    plain = sg.gate(FIB, FIB)
    padded = sg.gate(FIB + " " + "z" * 4000, FIB)
    assert plain.metrics["literal_cover"] == padded.metrics["literal_cover"] == 1.0
    assert not padded.admitted


def test_whitespace_and_comment_variants_decide_identically():
    a = sg.gate("a(n)  =\n  a(n-1)   +  a(n-2)", FIB)
    b = sg.gate("a(n) = a(n-1) + a(n-2)   # the seeds are 1, 1", FIB)
    assert a.admitted and b.admitted


def test_missing_answers_refused():
    for text in ("", "   ", "*not found", "N/A", "***"):
        d = sg.gate(text, FIB)
        assert not d.admitted and d.reason == "missing-answer", text


def test_bare_constant_has_no_generator():
    d = sg.gate("42", FIB)
    assert not d.admitted and d.reason == "no-index-variable"


def test_every_alternative_must_pass():
    good = 'a(n) = a(n-1) + a(n-2)'
    both = f'["{good}", "{FIB}"]'
    assert sg.gate(f'["{good}", "a(n) = 2*a(n-1)"]', FIB).admitted
    d = sg.gate(both, FIB)
    assert not d.admitted
    assert d.metrics["refused_index"] == 1
    assert "alternative=1" in d.evidence


# --------------------------------------------------------------------------- #
# The decision as data
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("label,answer,item", ALL_FIXTURES, ids=[f[0] for f in ALL_FIXTURES])
def test_decision_is_serializable_data(label, answer, item):
    decision = sg.gate(answer, item)
    assert isinstance(decision, GateDecision)
    rec = decision.as_record()
    assert rec["reason"] in sg.REASONS
    assert rec["gate_version"] == sg.GATE_VERSION
    assert isinstance(rec["evidence"], list) and isinstance(rec["metrics"], dict)
    assert rec["admitted"] == sg.admits(answer, item)


def test_refusals_name_a_clause_never_just_an_outcome():
    for label, answer, item in PRINTS + LOOKUPS + POSITIONAL:
        d = sg.gate(answer, item)
        assert d.clause.startswith("G") and ":" in d.clause, label
        assert d.evidence, label


# --------------------------------------------------------------------------- #
# The relation to B11a — separate organ, strictly tighter
# --------------------------------------------------------------------------- #


def test_gate_shares_no_decision_code_with_the_scorer():
    """The organs are separate by design: the gate imports the normalization law
    and nothing from B11a."""
    import ast

    tree = ast.parse(open(sg.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any("bin_classifier" in name for name in imported), sorted(imported)
    assert "sequence_exec.normalize_answer" in imported


@pytest.mark.parametrize("label,answer,item", ALL_FIXTURES, ids=[f[0] for f in ALL_FIXTURES])
def test_tighter_than_the_scorer(label, answer, item):
    """Everything the scorer bins PRINTS or ORDINAL, the gate refuses."""
    form = b11a.classify_form(answer, item).form
    if form in (b11a.Form.PRINTS, b11a.Form.ORDINAL):
        assert not sg.gate(answer, item).admitted, (label, form)


def test_strictly_tighter_witnesses():
    """…and the gate refuses candidates the scorer bins as genuine abstraction —
    which is what makes it STRICTLY tighter, and why the scorer can never be the
    optimization target."""
    witnesses = [
        ("seeded-copy", "a(n) = a(n-1) + a(n-2) + a(n-3) + a(n-4) "
                        "with a(0..3) = 90,203,212,235", LONG),
        ("period-table", "a(n) = [1,1,0,0][n % 4]", BIN16),
        ("exception-decoy", "a(n) = n mod 2 if n != 6 else 1", BIN12),
    ]
    for label, answer, item in witnesses:
        assert b11a.classify_form(answer, item).form is b11a.Form.ABSTRACTION, label
        assert not sg.gate(answer, item).admitted, label


def test_genuine_models_pass_both_organs():
    for label, answer, item in GENUINE:
        assert b11a.classify_form(answer, item).form is b11a.Form.ABSTRACTION, label
        assert sg.gate(answer, item).admitted, label
