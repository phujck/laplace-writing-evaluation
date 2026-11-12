"""What a QUESTION is allowed to cost: the three repeats the orchestrator found, asserted.

THE AUTHOR, 2026-09-22, reading the J2 front door: "Why would it need to be mounting handles on
every fucking descent. Does reconstruct need an upfold before every execution?" The answer is
no, and the rule it became is this packet's: anything that depends only on (record, lens,
declared axes) is computed when the lens is opened and held for the run; a question touches only
what depends on the question.

Three properties, all on the ENGINE'S OWN LEDGERS - the dataset with two declared lenses, so the
fourth typed residual has a caller - and all on the REOPENED door, which is where every headline
number of this wave is taken:

  S1  a question builds NO ranked column. They are gathered once, when the lens is opened.
  S2  the whole question list charges ONE build of the conditional-law quotient and ONE of the
      route-weighted coupling, not one per question, and every question's exact counts still
      equal what the frontier read admitted.
  S3  the lateral residual is MEASURED on a door that opened its trees, and reads exactly what
      the door that built them read - because the second lens is loaded, never rebuilt.

Run with ``--basetemp=/tmp/pytest-<something unique>``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atlas.front.door import FrontDoor                      # noqa: E402
from atlas.front.draw import runs_of_the_draw               # noqa: E402


def _stages(door: FrontDoor) -> dict:
    return {receipt.stage: receipt for receipt in door.stages}  # loop-ok: the nine stages of one run


@pytest.fixture(scope="module")
def engine_pair(tmp_path_factory):
    """The engine's ledgers through the front door twice: built, then REOPENED."""
    root = tmp_path_factory.mktemp("j3-per-question-path")
    cold = FrontDoor(runs_of_the_draw(names=("engine",))["engine"], root)
    cold.run_path()
    warm = FrontDoor(runs_of_the_draw(names=("engine",))["engine"], root)
    warm.run_path()
    return cold, warm


def test_a_question_builds_no_ranked_column(engine_pair):
    """S1. The ranked columns are a function of (record, lens); the question is not."""
    _cold, warm = engine_pair
    faces = _stages(warm)["faces"].executed
    assert faces["ranked_columns_gathered_at_open"] > 0, faces
    assert faces["row_kind_masks_built_at_open"] > 0, faces
    for row in warm.results:  # loop-ok: the engine's own declared questions
        for supply in ("partial", "whole"):  # loop-ok: the two declared supply disciplines
            executed = row[supply]["executed"]
            assert executed["ranked_columns_built"] == 0, (row["qid"], supply, executed)
            assert (executed["ranked_columns_gathered_when_the_lens_was_opened"]
                    == faces["ranked_columns_gathered_at_open"])


def test_the_quotient_is_built_once_for_the_whole_question_list(engine_pair):
    """S2. One build, one contraction, every question a slice of the same batch."""
    _cold, warm = engine_pair
    if not warm.joint.ran:
        pytest.skip(warm.joint.why)
    executed = _stages(warm)["read"].executed
    questions = executed["questions_read"]
    assert questions > 1, executed
    assert executed["joint_quotients_built_for_the_whole_question_list"] == 1, executed
    assert executed["joint_couplings_built_for_the_whole_question_list"] == 1, executed
    for row in warm.results:  # loop-ok: the engine's own declared questions
        spine = row["exact_joint_counts"]
        assert spine["ran"], row["qid"]
        assert spine["integer_contraction"]["ran"], (row["qid"], spine["integer_contraction"])
        assert spine["agreement"]["all_three_agree"], (row["qid"], spine["agreement"])
        # the build this question charged, in its own block: none
        assert spine["integer_contraction"]["seconds"] == 0.0, row["qid"]
        assert row["qid"] in spine["built_once_for_the_block"]["block_questions"]


def test_the_lateral_residual_is_measured_on_the_reopened_door(engine_pair):
    """S3. Both lenses are persisted, so the fourth typed residual survives the reopen."""
    cold, warm = engine_pair
    assert _stages(warm)["tree"].executed["lenses_persisted"] == 2
    assert _stages(warm)["tree"].executed["path"] == "load_tree"
    assert warm.loaded_other is not None
    assert warm.loaded_other.executed["components_regraded"] == 0
    before = _stages(cold)["faces"].payload["lateral_residual"]
    after = _stages(warm)["faces"].payload["lateral_residual"]
    assert after["measured"] is True, after
    assert after["both_lenses_were_loaded_not_rebuilt"] is True
    assert after["shared_carrier_rows"] == before["shared_carrier_rows"]
    assert after["commutator_frobenius"] == pytest.approx(before["commutator_frobenius"],
                                                          rel=1e-12)
