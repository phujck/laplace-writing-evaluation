"""draw.py - THE DECLARED DRAWS, and the datasets each one names.

The J1 carried residual this closes, verbatim: "No declared draw for a wave: A1 measured at
10/30/100 haystacks, B1 at 6/10/30, this synthesis at 6, and QASPER at 20 papers. No two lanes
share a draw, so no two lanes' numbers are joinable at the measurement."

So the draw is a DECLARED ROW here, stated by the plan and not chosen by a caller: the engine's
own ledgers whole, the toy corpus whole (its ten rows are the contract's own fixture, C.25), and
LongMemEval haystacks 0-9 and QASPER dev papers 0-19 as the SMOKE of the two benchmarks - which
the plan says in as many words is NOT a measurement; the first measurement is the next packet.
Every number this packet reports comes from this draw, and a caller that wants another draw
changes this row and says so in its own receipt.

Each ``DatasetRun`` is the dataset's own declaration, ingester, lens and questions - four
functions, no policy. Cheap name discovery does not read inputs; selected
run construction can measure source vocabularies before later ingestion.

Complexity: name selection is O(requested names); construction pays only the
selected factories' input/metadata work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from collections.abc import Sequence

__all__ = ["DECLARED_DRAW", "DECLARED_DRAWS", "MEASURED_READ_DRAW", "PROFILE_SMALLEST_DRAW",
           "READ_PLANNER_DRAW", "CONTENT_LEAF_DRAW", "declared_draw", "DatasetRun",
           "runs_of_the_draw", "dataset_names", "DatasetSelectionRefused"]

DECLARED_DRAW: dict[str, Any] = {
    "draw_id": "J2-smoke",
    "declared_by": "atlas/programme/waves/J2-integration.plan.json, packet "
                   "J2-INTEGRATION-one-front-door-end-to-end (must_achieve 1 and 13)",
    "engine-ledgers": {"draw": "whole", "why": "the engine's own ledgers are the dataset this "
                                               "campaign exists for; they are small enough to "
                                               "take whole, so there is nothing to sample"},
    "atlas-toy-corpus": {"draw": "whole", "why": "C.25 freezes the fixture at 10 typed rows and "
                                                 "8 span-bearing rows; a sample of a fixture "
                                                 "would be a different fixture"},
    "longmemeval-s-rung-ab": {"draw": "haystacks 0-9", "histories": 10,
                              "why": "the SMOKE of the benchmark at the declared draw - the "
                                     "plan says in as many words that this is not a "
                                     "measurement; the first measurement is the next packet"},
    "qasper-v0.3-rung-ab": {"draw": "dev papers 0-19", "papers": 20,
                            "why": "the second benchmark's smoke at the declared draw, same "
                                   "reason"},
}


# THE SECOND DECLARED DRAW, and why there are now two. J1's carried residual was that no two
# lanes shared a draw; J2 fixed that with ONE draw and its own synthesis then found the other
# half of the defect - the run manifest's ``declared_draw`` named a plan file that contains no
# draw key at all, which is a reference that cannot be resolved. So a draw is a DECLARED ROW
# here, named by its id, and the manifest selects one by that id. The J2 smoke draw is kept
# verbatim (nothing accepted is thinned) and the measured-read draw is the one wave J3's
# ruling 4 asks for: "100 LongMemEval haystacks; the engine's ledgers whole", which is where
# the packed scan is doing work rather than paying launch latency.
MEASURED_READ_DRAW: dict[str, Any] = {
    "draw_id": "J3-measured-read",
    "declared_by": "atlas/programme/waves/J3-integration-continued.plan.json, packet "
                   "J3-INTEGRATION-continued-in-place, ruling 4",
    "engine-ledgers": {"draw": "whole", "why": "the ruling names the engine's ledgers whole"},
    "atlas-toy-corpus": {"draw": "whole", "why": "C.25 freezes the fixture; a sample of a "
                                                 "fixture would be a different fixture"},
    "longmemeval-s-rung-ab": {"draw": "haystacks 0-49", "histories": 50,
                              "why": "THE LARGEST DRAW THIS GPU ADMITS, measured and not "
                                     "chosen. The ruling asks for 100 haystacks and 100 does "
                                     "not run: the UP round's padded SVD batch asks the 3.68 "
                                     "GiB device for another 1.66 GiB on top of the 2.37 GiB "
                                     "the lens already holds and is refused "
                                     "(evidence/ATLAS_PROGRAMME/waves/"
                                     "J3-integration-continued/measured/"
                                     "oom_at_100_haystacks.log, the command and the whole "
                                     "traceback). The defect is in the grading organ, named "
                                     "in this packet's residuals, not in the draw; this row "
                                     "carries the largest size that does run, which is still "
                                     "five times the J2 smoke draw and enough for the packed "
                                     "scan to be doing arithmetic rather than paying kernel "
                                     "launch latency"},
    "qasper-v0.3-rung-ab": {"draw": "dev papers 0-19", "papers": 20,
                            "why": "unchanged from the smoke draw: the ruling names "
                                   "LongMemEval and the engine, so QASPER rides at its own "
                                   "declared size and its numbers stay joinable with J2's"},
}

# THE THIRD DECLARED DRAW, and why it exists. The strict gate asks for a PROFILE of the front
# door at three sizes, and the judge's finding on the first attempt was that three profiles of
# three DIFFERENT datasets carry no size signal at all: their wall seconds were 3.062 / 3.114 /
# 3.462 across a 3,300x change in rows, because what they measured was the interpreter starting.
# Three sizes of ONE dataset do carry it, and the two draws above give only two of them - so the
# smallest is declared here, as a row with a reason, rather than passed as a caller's number.
PROFILE_SMALLEST_DRAW: dict[str, Any] = {
    "draw_id": "J3-profile-smallest",
    "declared_by": "atlas/programme/waves/J3-integration-continued.plan.json, packet "
                   "J3-INTEGRATION-continued-in-place: the strict gate's profile at three sizes",
    "engine-ledgers": dict(DECLARED_DRAW["engine-ledgers"]),
    "atlas-toy-corpus": dict(DECLARED_DRAW["atlas-toy-corpus"]),
    "longmemeval-s-rung-ab": {"draw": "haystacks 0-1", "histories": 2,
                              "why": "the SMALLEST draw of the dataset the profile scales on, "
                                     "so that the three profiled sizes are 2 / 10 / 50 "
                                     "haystacks of ONE dataset and the door's own seconds move "
                                     "with the draw. It is a size, not a measurement: no "
                                     "headline number comes from this row"},
    "qasper-v0.3-rung-ab": dict(DECLARED_DRAW["qasper-v0.3-rung-ab"]),
}

# THE FOURTH DECLARED DRAW. Wave J4's ruling R2 asks for the measurement PER QUESTION CLASS at
# "100 LongMemEval haystacks (if the device refuses 100, the largest it admits, stated) and 20
# QASPER papers". The size the ruling names is declared HERE as its own row, so that the attempt
# at 100 is a run of a declared draw and not a caller's number; whether this device admits it is
# a measurement, recorded in the packet's report beside the command that took it. The engine's
# ledgers and the toy ride at their own whole sizes, unchanged, so this draw's engine numbers stay
# joinable with J3's.
READ_PLANNER_DRAW: dict[str, Any] = {
    "draw_id": "J4-read-planner",
    "declared_by": "atlas/programme/waves/J4-widenings.plan.json, packet "
                   "J4-READ-PLANNER-by-question-class, must_achieve 4",
    "engine-ledgers": {"draw": "whole", "why": "the ruling names the engine's ledgers whole"},
    "atlas-toy-corpus": {"draw": "whole", "why": "C.25 freezes the fixture; the toy's five known "
                                                 "answers are a gate of this packet"},
    "longmemeval-s-rung-ab": {"draw": "haystacks 0-49", "histories": 50,
                              "asked_for": 100,
                              "why": "THE RULING ASKS FOR 100 AND THIS DEVICE REFUSES 100, "
                                     "measured by this packet with its own command and not "
                                     "inherited: `scripts/laplace-python -m atlas.front "
                                     "evidence/ATLAS_PROGRAMME/waves/J4-widenings/measured/"
                                     "manifest-100.json` reaches the grading build and dies "
                                     "there - torch.OutOfMemoryError, 'Tried to allocate 1.66 "
                                     "GiB. GPU 0 has a total capacity of 3.68 GiB of which "
                                     "356.00 MiB is free', in the padded SVD batch of the UP "
                                     "round (evidence/ATLAS_PROGRAMME/waves/J4-widenings/"
                                     "measured/attempt_100_haystacks.log, the whole traceback). "
                                     "That is the same refusal J3 recorded, reproduced rather "
                                     "than quoted. The defect is in the grading organ and is "
                                     "named in this packet's residuals; this row carries the "
                                     "largest size that does run, which is what the ruling's "
                                     "own parenthesis asks for"},
    "qasper-v0.3-rung-ab": {"draw": "dev papers 0-19", "papers": 20,
                            "why": "the size the ruling names for the second benchmark"},
}

# THE FIFTH DECLARED DRAW: the same door, with the ingestion ladder's THIRD RUNG on. The author's
# ruling for wave J4 is that the light tier proposes on the development draw, so the rung is not a
# flag a caller passes - it is a property of a declared draw row, exactly as the haystack count is.
# BOTH BENCHMARKS CARRY IT (amended, continuation 1): the first cut of this row turned the rung on
# for LongMemEval alone, and the packet's judge ruled that this left the brief's measurement -
# "the same on 20 QASPER papers" - with no code path to run at all. The rung is now declared for
# QASPER's twenty dev papers too, under QASPER's own view of the closed grammar
# (record.propose.QASPER_GRAMMAR: entity and quantity rows, same_entity relations, a
# (section, paragraph) container), so the two halves of the measurement are two rows of ONE draw
# and each dataset's numbers stay separable - each carries its own proposer identity, its own
# per-item cache key and its own receipt. The rung FAILS CLOSED on both: running this draw without
# a reachable light tier refuses the ingest rather than quietly producing a rung-(ab) store under
# this row's name.
RUNG_C_DRAW: dict[str, Any] = {
    "draw_id": "J4-rung-c",
    "declared_by": "atlas/programme/waves/J4-widenings.plan.json, packet "
                   "J4-RUNG-C-the-light-tier-proposer (must_achieve 1 and 2)",
    "engine-ledgers": dict(DECLARED_DRAW["engine-ledgers"]),
    "atlas-toy-corpus": dict(DECLARED_DRAW["atlas-toy-corpus"]),
    "longmemeval-s-rung-ab": {
        "draw": "haystacks 0-9", "histories": 10, "rungs": "abc",
        "proposer": "record.propose.light_tier_proposer(): the light tier of MODEL_RANK, asked "
                    "ONCE per item about that item's measured residue",
        "why": "THE TEN-HAYSTACK RUNG-(c) DRAW, deliberately the J2 smoke size rather than the "
               "50-haystack measured-read size: the brief orders ten haystacks first and the "
               "development draw after, and a model call per item is the one cost in this system "
               "that is not recovered by a cache the first time it is paid. The rung's numbers "
               "are reported at this size with the cost per item beside them; the development "
               "draw is the next row, written when the first has been paid for once"},
    "qasper-v0.3-rung-ab": {
        "draw": "dev papers 0-19", "papers": 20, "rungs": "abc",
        "proposer": "record.propose.light_tier_proposer(QASPER_GRAMMAR): the same light tier, "
                    "asked ONCE per PAPER about that paper's measured residue paragraphs, under "
                    "the kinds this dataset's declaration carries",
        "why": "THE TWENTY DEV PAPERS THE BRIEF NAMES, unchanged in size from every earlier draw "
               "so the rung is the only thing that moved and the numbers stay joinable with J2's "
               "and J3's. The size is the brief's ('the same on 20 QASPER papers'); the rung is "
               "the author's ruling for this wave"},
}

# THE SIXTH DECLARED DRAW: THE SAME DOOR, WITH THE LEAF CARRYING ITS CONTENT. The content axis is
# not a flag a caller passes and not a constant inside an ingester - it is a property of a
# declared draw row, exactly as the haystack count and the ingestion rung already are. Every
# other row in this file names no ``content`` block, so every other draw declares no axis, hashes
# its declaration exactly as it did before this packet and runs the byte-identical path J3 and J4
# measured. That IS the ablation's OFF position, and without it lane F's identity audit could not
# void an arm that equals dense.
#
# THE DIALS AND WHY THEY ARE THESE. target_tokens 96: the extension measured its passages at <= 100
# tokens (the reconciliation, the_segmenter_is_declared_not_chosen) and that is the scale at which
# its lexical index and per-passage vectors worked - 25 of 42 LongMem and 182 of 235 QASPER, the
# numbers this campaign has to beat. hard_cap_tokens 256: half the encoder window, so a leaf at
# the cap is never truncated and ``tokens_dropped`` can be asserted zero rather than hoped for;
# the declaration refuses anything above 512 by name and ``content.build_content`` refuses a cap
# wider than the AXIS's own encoder window. Neither was swept and neither was fitted on an
# outcome: they are declared here with their provenance, which is what B.5 asks of a dial.
_CONTENT_BLOCK: dict[str, Any] = {
    "target_tokens": 96,
    "hard_cap_tokens": 256,
    "declared_by": "atlas/programme/waves/P1-the-leaf.plan.json, packet "
                   "P1-THE-LEAF-CARRIES-ITS-CONTENT; dials from the reconciliation's "
                   "the_leaf_and_the_multiscale_construction",
    "axes": [{
        "axis": "content",
        "encoder_id": "bge-small-en-v1.5/onnx-fp16/1",
        "dim": 384,
        "dtype": "int8",
        "tokens": True,
        "why": "ONE declared vector channel (D.5's lean A = 1) plus its exact-lexical token set. "
               "The encoder is the one the survey in src/atlas/encoders/span_encoder.py "
               "records and evidence/ATLAS_PROGRAMME/waves/P1-the-leaf/encoder_choice.json "
               "measures; it is admitted at its NATIVE dimension by D.4's second sentence and "
               "priced as a fixed-rank instrument, and int8 is D.7's default store.",
    }],
}

CONTENT_LEAF_DRAW: dict[str, Any] = {
    "draw_id": "P1-content-leaves",
    "declared_by": "atlas/programme/waves/P1-the-leaf.plan.json, packet "
                   "P1-THE-LEAF-CARRIES-ITS-CONTENT (must_achieve 1, 2 and 5)",
    "engine-ledgers": {**DECLARED_DRAW["engine-ledgers"], "content": _CONTENT_BLOCK},
    "atlas-toy-corpus": {**DECLARED_DRAW["atlas-toy-corpus"], "content": _CONTENT_BLOCK},
    "longmemeval-s-rung-ab": {**DECLARED_DRAW["longmemeval-s-rung-ab"],
                              "content": _CONTENT_BLOCK},
    "qasper-v0.3-rung-ab": {**DECLARED_DRAW["qasper-v0.3-rung-ab"], "content": _CONTENT_BLOCK},
}

# THE SEVENTH DECLARED DRAW: THE JOINT-SECTION READ (packet P3-THE-READ, steps C and D). Two
# things are declared here that no earlier row declares, and both are properties of the draw and
# not of a caller: the CONTENT LENS is the dataset's primary lens (so the door persists its tree,
# its frames and its memberships, and the relation lens rides beside it as the second), and the
# QUESTIONS are the BENCHMARK'S OWN, compiled through M1's preregistered C.22/C.23 mapping,
# instead of ``question.py``'s declared fixtures. The haystack count is the brief's: ten first,
# then thirty as its own row so the two sizes are two declared draws and never a caller's number.
_P3_LONGMEM: dict[str, Any] = {
    **DECLARED_DRAW["longmemeval-s-rung-ab"], "content": _CONTENT_BLOCK,
    "primary_lens": "content",
    "questions": "m1-c22",
    "why_the_content_lens_is_primary": (
        "the read this draw measures is the JOINT SECTION, whose first move is the content "
        "lens's certified descent from its roots; the relation lens is the second declared lens "
        "and supplies the MEMBERSHIPS the joint intersects. Both trees are persisted by the tree "
        "stage exactly as before - nothing is rebuilt per question and nothing per run"),
    "why_these_questions": (
        "the benchmark's own questions, through the preregistered mapping C.22/C.23 "
        "(evidence/ATLAS_PROGRAMME/waves/M1-first-measurement/m1_questions.py, kept): a question "
        "enters as its TYPE's declared row - jurisdiction, mask, anchor surfaces, operator - and "
        "nothing at run time chooses. question.py's fixtures are not this draw's source"),
}

P3_THE_READ_DRAW: dict[str, Any] = {
    "draw_id": "P3-the-read",
    "declared_by": "atlas/programme/waves/P3-the-read.plan.json, packet P3-THE-READ, steps C-D",
    "engine-ledgers": {**DECLARED_DRAW["engine-ledgers"], "content": _CONTENT_BLOCK},
    "atlas-toy-corpus": {**DECLARED_DRAW["atlas-toy-corpus"], "content": _CONTENT_BLOCK},
    "longmemeval-s-rung-ab": _P3_LONGMEM,
    "qasper-v0.3-rung-ab": {**DECLARED_DRAW["qasper-v0.3-rung-ab"], "content": _CONTENT_BLOCK},
}

P3_THE_READ_30_DRAW: dict[str, Any] = {
    **P3_THE_READ_DRAW,
    "draw_id": "P3-the-read-30",
    "longmemeval-s-rung-ab": {**_P3_LONGMEM, "draw": "haystacks 0-29", "histories": 30,
                              "why": "the second size the brief names for the census through "
                                     "the door; the same row otherwise, so the two sizes differ "
                                     "in the haystack count and in nothing else"},
}

# THE SMALLEST DECLARED DRAW OF THE SAME ROW, which governing ruling 3 requires to exist: "If
# the 10-haystack draw cannot complete, the same command completes on the smallest declared draw
# and the excess seconds at 10 are named inherent by arithmetic". The packet's own law is that a
# run waited on is a defect and the profile at the smallest size is the banked one, so the door
# has to have a size at which `distil.py profile -- <the door entry>` returns inside a couple of
# minutes. Two haystacks is that size: it is the same row in every other respect, so the two
# draws differ in the haystack count and in nothing else.
P3_THE_READ_2_DRAW: dict[str, Any] = {
    **P3_THE_READ_DRAW,
    "draw_id": "P3-the-read-2",
    "longmemeval-s-rung-ab": {**_P3_LONGMEM, "draw": "haystacks 0-1", "histories": 2,
                              "why": "the SMALLEST declared draw of this row - the size the "
                                     "door's profile is taken at, per governing ruling 3"},
}

DECLARED_DRAWS: dict[str, dict[str, Any]] = {
    "P3-the-read": P3_THE_READ_DRAW,
    "P3-the-read-2": P3_THE_READ_2_DRAW,
    "P3-the-read-30": P3_THE_READ_30_DRAW,
    "J2-smoke": DECLARED_DRAW,
    "J3-measured-read": MEASURED_READ_DRAW,
    "J3-profile-smallest": PROFILE_SMALLEST_DRAW,
    "J4-read-planner": READ_PLANNER_DRAW,
    "J4-rung-c": RUNG_C_DRAW,
    "P1-content-leaves": CONTENT_LEAF_DRAW,
}


def declared_draw(draw_id: str | None) -> dict[str, Any]:
    """The declared draw row of that id. Refuses an id no row declares. O(1)."""
    if draw_id is None:
        return DECLARED_DRAW
    row = DECLARED_DRAWS.get(str(draw_id))
    if row is None:
        raise KeyError(f"no declared draw with id {draw_id!r}; "
                       f"declared: {sorted(DECLARED_DRAWS)}")
    return row


@dataclass(frozen=True, slots=True)
class DatasetRun:
    """One dataset of the draw: how it declares, ingests, lenses and asks."""

    dataset_id: str
    draw: dict[str, Any]
    declaration: Callable[[], Any]
    ingest: Callable[[Any], Any]
    lens: Callable[[Any], Any]
    questions: Callable[[Any], Any]     # called with the OPENED record: a selective condition
                                        # is derived from the record, never hand-picked
    rung: int = 1
    can_open: bool = True
    second_lens: Callable[[Any], Any] | None = None
    second_lens_why: str = ""


def _engine_run(draw: dict[str, Any]) -> DatasetRun:
    from ..grading.lenses import engine_lenses
    from ..record.ingest import engine_rows
    from .question import engine_questions

    vocabularies = engine_rows.measure_vocabularies()
    # THE CONTENT BLOCK IS THE DRAW'S, NOT THE CALLER'S - the same rule as the rung. A row that
    # names no ``content`` declares no axis, and this dataset's declaration hash, segments and
    # answers are then what every earlier wave measured, bit for bit.
    content = draw["engine-ledgers"].get("content")

    def ingest(_store: Any) -> Any:
        # The engine ledgers' ingester takes no segment store, and it does not need one: the
        # PAIR of ledgers is ONE item (engine_rows.py:236-254 says why - the link relations and
        # the status fold both cross the two files), so there is nothing for a per-ITEM adoption
        # cache to skip. The store is written by ``store_ingestion`` afterwards like any other
        # dataset's and ``open_record`` reads it back: this run's ``can_open`` is TRUE.
        # CORRECTED 2026-09-22: the last clause of this comment used to say "it is why this
        # run's can_open is false", which contradicted the ``can_open=True`` three lines below
        # and was refuted by measurement -
        # evidence/ATLAS_PROGRAMME/waves/P1-the-leaf/toy_engine_persistence.py opens this
        # dataset's store with extractions 0, parses 0, source_reads 0 and every leaf rebuilt.
        return engine_rows.ingest(vocabularies=vocabularies, content=content)

    def lens(ingestion: Any) -> Any:
        fold = engine_rows._fold_status(ingestion)
        return engine_lenses(ingestion, fold.supersession_depth)["entity"]

    def revision(ingestion: Any) -> Any:
        fold = engine_rows._fold_status(ingestion)
        return engine_lenses(ingestion, fold.supersession_depth)["revision"]

    return DatasetRun(
        dataset_id="engine-ledgers", draw=draw["engine-ledgers"],
        declaration=lambda: engine_rows.declaration(vocabularies, content=content),
        ingest=ingest, lens=lens, questions=engine_questions, rung=0, can_open=True,
        second_lens=revision,
        second_lens_why=("TWO lenses over ONE record, so the FOURTH typed residual has a "
                         "production caller: ENTITY counts targets/absorbs and REVISION counts "
                         "supersedes/corrects/retracts, and their disagreement on the rows they "
                         "both group is the lateral incompatibility - a commutator, never fused "
                         "with closure, price or reconstruction error (charter four_residuals). "
                         "L1 could only measure it on 16 shared rows; here it is measured on "
                         "every row both lenses seat."))


def _toy_run(draw: dict[str, Any]) -> DatasetRun:
    from ..grading.lenses import toy_lens
    from ..record.ingest import toy
    from .question import toy_questions

    content = draw["atlas-toy-corpus"].get("content")   # the draw's, not the caller's

    def ingest(_store: Any) -> Any:
        return toy.ingest(content=content).ingestion

    return DatasetRun(
        dataset_id="atlas-toy-corpus", draw=draw["atlas-toy-corpus"],
        declaration=lambda: toy.declaration(content=content), ingest=ingest, lens=toy_lens,
        questions=toy_questions, rung=0, can_open=True)


def benchmark_questions(dataset: str, histories: int) -> Any:
    """The BENCHMARK'S OWN questions, through M1's preregistered C.22/C.23 mapping.

    The mapping is a row set, not a run-time decision, and it already exists - it is not
    re-authored here. ``m1_questions.py`` lives under ``evidence/`` (it is a measurement's own
    module, kept with its wave), so it is loaded by FILE LOCATION the way ``front/lift.py`` loads
    the extension's judged modules, and its ``longmem_specs`` is called with the drawn questions
    exactly as ``m1_measure.py`` calls it. A question whose type the mapping refuses is refused by
    name and carries no spec, which is C.9's fail-closed and not a silently dropped question.

    Complexity: O(drawn questions x question text).
    """
    import importlib.util
    from pathlib import Path

    here = Path(__file__).resolve().parents[3]   # the checkout (src/atlas/front/draw.py, R2)
    path = (here / "evidence" / "ATLAS_PROGRAMME" / "waves" / "M1-first-measurement"
            / "m1_questions.py")
    if not path.is_file():
        raise FileNotFoundError(f"C22-MAPPING-MISSING: {path}")
    import sys

    if "m1_questions" in sys.modules:
        return sys.modules["m1_questions"]
    spec = importlib.util.spec_from_file_location("m1_questions", path)
    module = importlib.util.module_from_spec(spec)          # type: ignore[arg-type]
    # registered under its plain name BEFORE it executes, exactly as ``lift.py`` registers the
    # extension's modules: its own frozen dataclasses resolve their annotations through
    # ``sys.modules[__module__]`` and a module absent from that table cannot be built at all
    sys.modules["m1_questions"] = module
    spec.loader.exec_module(module)                         # type: ignore[union-attr]
    return module


def _longmem_run(draw: dict[str, Any]) -> DatasetRun:
    from ..grading.lenses import content_lens, longmem_semantic_lens
    from ..record.ingest import longmem
    from ..record.propose import LONGMEM_GRAMMAR, light_tier_proposer
    from .question import longmem_questions

    histories = int(draw["longmemeval-s-rung-ab"]["histories"])
    # THE RUNG IS THE DRAW'S, NOT THE CALLER'S. A row that says 'abc' turns the ingestion ladder's
    # third rung on for this dataset and names the proposer; every other row is 'ab' and runs the
    # byte-identical path J3 accepted, so a widening cannot leak into a draw that did not declare
    # it. ``declaration`` follows the same string, so a rung-(c) store carries its own hash.
    rungs = str(draw["longmemeval-s-rung-ab"].get("rungs", "ab"))
    proposer = light_tier_proposer(LONGMEM_GRAMMAR) if "c" in rungs else None
    content = draw["longmemeval-s-rung-ab"].get("content")   # the draw's, not the caller's

    def ingest(store: Any) -> Any:
        return longmem.ingest(histories=histories, rungs=rungs, segments=store,
                              proposer=proposer, content=content)

    row = draw["longmemeval-s-rung-ab"]
    questions = longmem_questions
    if str(row.get("questions", "")) == "m1-c22":
        module = benchmark_questions("longmem", histories)

        def questions(opened: Any) -> tuple[Any, ...]:
            """The drawn haystacks' OWN questions, compiled by the preregistered mapping."""
            drawn = [{"question_id": case.member("question_id").text,
                      "question": case.member("question").text,
                      "question_type": case.member("question_type").text}
                     for _raw, case in longmem._cases(longmem.DATASET_PATH, histories)]  # loop-ok: the drawn haystacks
            compiled = module.longmem_specs(opened, drawn)
            return tuple(one.spec for one in compiled if one.spec is not None)  # loop-ok: the drawn question list

    if str(row.get("primary_lens", "")) == "content":
        # THE CONTENT LENS IS THIS DRAW'S PRIMARY LENS and the relation lens is the second: the
        # joint-section read descends the content lens and intersects the relation lens's
        # memberships, so both trees must be persisted and both loaded. The declaration is the
        # draw's, never a caller's.
        def primary(ingestion: Any) -> Any:
            return content_lens(ingestion, "turn", "question_id", "longmem-content",
                                answer_column="content_span",
                                generator_arm=str(row.get("generator_arm", "both")))

        return DatasetRun(
            dataset_id="longmemeval-s-rung-ab", draw=row,
            declaration=lambda: longmem.declaration(rungs, content=content), ingest=ingest,
            lens=primary, questions=questions, rung=1, can_open=True,
            second_lens=longmem_semantic_lens,
            second_lens_why=("the RELATION lens beside the content lens: its sections are the "
                             "MEMBERSHIPS the joint-section read intersects (step B), and the "
                             "commutator of the two lenses' projectors is the fourth typed "
                             "residual, measured on the rows both seat"))
    return DatasetRun(
        dataset_id="longmemeval-s-rung-ab", draw=row,
        declaration=lambda: longmem.declaration(rungs, content=content), ingest=ingest,
        lens=longmem_semantic_lens, questions=questions, rung=1, can_open=True)


def _qasper_run(draw: dict[str, Any]) -> DatasetRun:
    from ..grading.lenses import qasper_semantic_lens
    from ..record.ingest import qasper
    from ..record.propose import QASPER_GRAMMAR, light_tier_proposer
    from .question import qasper_questions

    papers = int(draw["qasper-v0.3-rung-ab"]["papers"])
    # THE RUNG IS THE DRAW'S, NOT THE CALLER'S - the same rule as _longmem_run, and the reason the
    # string was hardwired here before: a row that says 'abc' turns the ingestion ladder's third
    # rung on for this dataset and names the proposer, and every other row is 'ab' and runs the
    # byte-identical path J3 accepted. ``declaration`` follows the same string, so a rung-(c) store
    # carries its own declaration hash and cannot be mistaken for the rung-(ab) one.
    rungs = str(draw["qasper-v0.3-rung-ab"].get("rungs", "ab"))
    proposer = light_tier_proposer(QASPER_GRAMMAR) if "c" in rungs else None
    content = draw["qasper-v0.3-rung-ab"].get("content")     # the draw's, not the caller's

    def ingest(store: Any) -> Any:
        return qasper.ingest(papers=papers, rungs=rungs, segments=store, proposer=proposer,
                             content=content)

    return DatasetRun(
        dataset_id="qasper-v0.3-rung-ab", draw=draw["qasper-v0.3-rung-ab"],
        declaration=lambda: qasper.declaration(rungs, content=content), ingest=ingest,
        lens=qasper_semantic_lens, questions=qasper_questions, rung=1, can_open=True)


# This is the existing four-way construction table, shared with cheap discovery.
# A selected consumer must not construct another dataset to discover its name.
_RUN_FACTORIES = {"toy": _toy_run, "engine": _engine_run,
                  "longmem": _longmem_run, "qasper": _qasper_run}


class DatasetSelectionRefused(ValueError):
    """Invalid selection is refused before any factory or state publication."""

    def __init__(self, names, issue):
        self.result = {"reason": "FRONT-DATASET-SELECTION-REFUSED", "requested": names,
                       "available": list(_RUN_FACTORIES), "issue": issue,
                       "publication": "NOT_STARTED"}
        super().__init__(self.result["reason"] + ": " + issue)


def dataset_names(names: Sequence[str] | None = None, *,
                  fallback: Sequence[str] | None = None) -> tuple[str, ...]:
    """Validate selection without IO: empty override falls back, then default-all.

    A malformed override is refused even when falsy. Nonempty valid overrides
    win without consulting an unused fallback. No factory runs during selection.
    """
    def validated(value):
        if value is None:
            return ()
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise DatasetSelectionRefused(str(value), "Supply a sequence of dataset names")
        selected = tuple(value)
        if any(not isinstance(name, str) or name not in _RUN_FACTORIES for name in selected):
            raise DatasetSelectionRefused(list(selected), "Unknown dataset in selection")
        if len(set(selected)) != len(selected):
            raise DatasetSelectionRefused(list(selected), "Duplicate dataset in selection")
        return selected
    selected = validated(names)
    if not selected:
        selected = validated(fallback)
    return selected or tuple(_RUN_FACTORIES)


def runs_of_the_draw(draw_id: str | None = None, *,
                     names: Sequence[str] | None = None) -> dict[str, DatasetRun]:
    """Construct only validated selected runs, once each; default-all is deliberate.

    Construction may read selected dataset inputs/metadata. Merely discovering
    names uses dataset_names, which does no dataset IO. Selection order is retained.
    """
    draw = declared_draw(draw_id)
    selected = dataset_names(names)
    return {name: _RUN_FACTORIES[name](draw) for name in selected}
