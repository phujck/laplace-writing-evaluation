"""The graded-node known-answer, run as a test.

The fixture itself is `graded_node_known_answer.py` beside this file, and it is runnable with no
pytest at all (`scripts/laplace-python atlas/tests/graded_node_known_answer.py`) because a judge
in a different context has to be able to reproduce every number in clauses A.33, A.34, A.35 and
B.36 by one command with no store, no device and no dataset. These tests are the same run, with
each identity surfaced as its own test id so a break names itself.
"""

from __future__ import annotations

import pytest

from graded_node_known_answer import (
    FoldRefused,
    LENS_PARTITION,
    down,
    fold_faces,
    grade_up,
    restrict,
    run,
    toy,
    up,
)

REPORT = run()


def test_the_known_answer_passes_as_a_whole():
    assert REPORT["verdict"] == "PASS", REPORT["checks_failed"]
    assert REPORT["checks_run"] == 30


@pytest.mark.parametrize("row", REPORT["checks"], ids=[r["check"] for r in REPORT["checks"]])
def test_each_identity(row):
    assert row["pass"], row


def test_the_fold_rule_max_breaks_the_block_sum():
    """The clause's own falsifier: change the admitted fold rule and the check must FAIL."""
    truth, _ = grade_up(toy(), LENS_PARTITION)
    broken, _ = grade_up(toy(), LENS_PARTITION, fold_rule="MAX")

    def counts(g):
        out = {}
        for w in g["witnesses"]:
            key = tuple(sorted(w["ends"]))
            out[key] = out.get(key, 0) + 1
        return out

    assert counts(broken) != counts(truth)
    assert counts(truth)[("s1", "s2")] == 6
    assert counts(broken)[("s1", "s2")] == 3  # max(1, 2, 3) - v2's rule, and it is wrong


def test_up_refuses_a_bag():
    with pytest.raises(FoldRefused) as exc:
        up({"members": ["t1", "t2"], "vectors": [[0.1], [0.2]]})
    assert exc.value.code == "FLAT-FINER-LEVEL-NOT-A-CONCEPTRIC"


def test_a_prose_summary_is_not_a_face():
    with pytest.raises(FoldRefused) as exc:
        fold_faces([{"f": {"kind": "summary", "text": "these turns are about Miso"}}])
    assert exc.value.code == "FACE-FIELD-KIND-NOT-ADMITTED"


def test_down_then_up_is_the_identity_on_every_node():
    g2 = toy()
    record = {g2["handle"]: g2}
    _, nodes = grade_up(g2, LENS_PARTITION, record=record)
    for name, node in sorted(nodes.items()):
        finer = down(node, record)
        assert finer["grade"] == 2, name
        assert up(finer)["id"] == node["id"], name
        assert restrict(g2, LENS_PARTITION[name])["handle"] == node["finer"], name
