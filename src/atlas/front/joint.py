"""joint.py - EXACT JOINT COUNTS, from the lifted exact-count spine and never from descent.

must_achieve (13), verbatim: "Exact JOINT counts come from the lifted integer contraction, not
from descent." A frontier descent decides each range {decided_in, excluded, open} against the
question's tolerance; what it does NOT do, and must not be made to do, is infer how many rows
satisfy a CONJUNCTION of conditions it never opened. That number is exact or it is nothing, so
it comes from the two lifted exact-count routes, both of which run here on the SAME admission
axes the read and the packed control use (``read.admission_axis_rows``):

  1. THE INTEGER CONTRACTION (``integer_contraction.py`` over ``gpu_state.py``). The axes are
     binary categorical columns; ``gpu_state.build_state`` builds the exact conditional suffix-law
     quotient over them (never the product of cardinalities), ``build_integer_continuation``
     turns the quotient's rational edges into primitive INTEGER messages with a validated
     overflow bound, and one Triton program per query contracts them. The result is an exact
     integer count per query, certified by construction rather than by rounding a float.
  2. THE ROUTE-WEIGHTED COUPLING (``section_coupling.py``, which itself calls ``gpu_state``'s
     ``build_state`` and ``contract``). The lens's rows are the SOURCES, each routed to exactly
     one tuple of labels with numerator equal to the common denominator - a deterministic
     membership, which is what a typed condition is - and ``intersection_mass`` returns the
     certified integer routing mass of any batch of label masks. ``tuples_matching_mask`` plus
     ``reached_sources`` then walks the same object BACKWARDS, from a selected tuple to the
     source rows it was drawn from: the coupling's own answer to
     WO-20260922-answers-name-their-content, beside the read's row handles.

THE BUILD IS CHARGED ONCE, NOT ONCE PER QUESTION. The quotient is a property of the RECORD and
the DECLARED AXIS SET, not of the question that asks about it, and the Parallax result this
spine comes from is an AMORTISATION: about 60 microseconds per batch of 1,024 queries after one
build. Building it inside the per-question loop - which is what this module did - threw the
amortisation away and made the exact route cost more per question than the read it accompanies.
So ``JointBank`` takes the WHOLE dataset's compiled question list, reduces it to the distinct
binary axes those questions state (two questions that state the same typed condition, or answer
over the same row kind, ARE the same axis), builds ONE quotient and ONE coupling over a block of
those axes, and contracts every query of every question in the block in ONE launch. A question's
own counts are then a slice of that batch: the build it charges is zero.

A block is bounded by the packed comparator's own declared bound of 30 binary axes, and by the
device budget the continuation validates against: if the batched build REFUSES by name, the
block is split and rebuilt, which is recorded as executed work rather than hidden. A refusal is
still a result - ``build_integer_continuation`` refuses when the quotient width exceeds its
exact fused cap or the retained plan exceeds the declared device budget, and this module reports
the refusal instead of falling back to a float contraction, which would be the silent-baseline
move the charter forbids.

Complexity, N rows of the lens, d distinct axes in a block, Q queries in the batch: O(N log N +
d M) ONCE to build each quotient with M the distinct label rows (M <= 2^d here), then
O(Q * width) device work for the whole batch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import torch

from ..grading.ranges import _dense_kind_counts_budget_bytes
from .lift import lifted
from .question import CompiledQuestion
from .read import admission_axis_rows

__all__ = ["exact_joint_counts", "build_joint_bank", "JointBank", "JOINT_QUERY_BANK",
           "MAX_AXES_PER_BLOCK"]

JOINT_QUERY_BANK = (
    "every admission axis (the question's conditions AND the two the operator adds): the exact "
    "joint count the read's rows_admitted must equal",
    "the question's declared conditions alone, without the operator's two axes: the count the "
    "conditions by themselves admit",
    "each single axis on its own: the marginal of that axis, which is what makes the joint count "
    "joint rather than a product",
)

# The packed comparator's OWN declared bound on a boolean query's width (contraction_kernels'
# 1..30 binary axes), which is what bounds a block here. It is that module's constant, quoted,
# not a size chosen in this file.
MAX_AXES_PER_BLOCK = 30


@dataclass(frozen=True, slots=True)
class _Asked:
    """One question's place in the bank: its axes, by the key that identifies them globally."""

    qid: str
    keys: tuple[str, ...]
    names: tuple[str, ...]
    conditions: int


def _label_masks(masks: torch.Tensor, dimension: int) -> torch.Tensor:
    """The same query bank as ``[Q, F, 2]`` label masks, built with no Python loop over queries.

    Fibre ``f`` of query ``q`` allows label 1 always when the query constrains the axis (it
    demands TRUE), and allows BOTH labels when it does not. O(Q * F).
    """
    device = masks.device
    bits = torch.arange(dimension, dtype=torch.int32, device=device)
    constrained = (masks[:, None] >> bits[None, :]) & 1        # [Q, F]
    allow_false = (constrained == 0).to(torch.int64)
    allow_true = torch.ones_like(allow_false)
    return torch.stack([allow_false, allow_true], dim=2)       # [Q, F, 2]


def _block_of(asked: Sequence[_Asked], max_axes: int) -> list[list[_Asked]]:
    """Group the questions into blocks whose DISTINCT axis set fits the comparator's bound.

    Greedy in the declared question order: a question joins the open block when the union still
    fits, and opens a new one otherwise. One block is one quotient and one coupling. O(Q * d).
    """
    blocks: list[list[_Asked]] = []
    current: list[_Asked] = []
    union: dict[str, int] = {}
    for one in asked:  # loop-ok: the dataset's own declared question list
        merged = dict(union)
        for key in one.keys:  # loop-ok: this question's own axes, at most the comparator's bound
            merged.setdefault(key, len(merged))
        if current and len(merged) > max_axes:
            blocks.append(current)
            current, union = [], {}
            merged = {}
            for key in one.keys:  # loop-ok: this question's own axes
                merged.setdefault(key, len(merged))
        current.append(one)
        union = merged
    if current:
        blocks.append(current)
    return blocks


def _queries_of(block: Sequence[_Asked], index: Mapping[str, int],
                device: torch.device) -> tuple[torch.Tensor, dict[str, dict[str, Any]]]:
    """The whole block's query bank as ONE int32 mask vector, with each question's slice.

    A query is a mask of the axes it constrains; every query demands TRUE on them, because an
    admission axis is by construction the predicate "this row satisfies this part of the
    question". The bank per question is the declared one: all its axes, its conditions alone,
    and each of its axes on its own. O(sum of axes).
    """
    masks: list[int] = []
    slices: dict[str, dict[str, Any]] = {}
    for one in block:  # loop-ok: this block's own questions
        start = len(masks)
        bits = [1 << index[key] for key in one.keys]  # loop-ok: this question's own axes
        full = 0
        for bit in bits:  # loop-ok: this question's own axes
            full |= bit
        conditions = 0
        for bit in bits[:max(one.conditions, 1)]:  # loop-ok: this question's own condition axes
            conditions |= bit
        masks.append(full)
        masks.append(conditions)
        masks.extend(bits)
        slices[one.qid] = {"start": start, "stop": len(masks),
                           "names": ["all_axes", "conditions_only"]
                                    + [f"axis_{i}" for i in range(len(bits))]}  # loop-ok: this question's own axes
    return torch.tensor(masks, dtype=torch.int32, device=device), slices


class JointBank:
    """One build of the conditional-law quotient, contracted for every question of the run.

    Built by ``build_joint_bank``; read per question by ``for_question``. It holds no policy:
    the axes are ``read.admission_axis_rows``' own, the bound is the comparator's own and the
    device budget is the one ``ranges.py`` spends against.
    """

    __slots__ = ("record", "ran", "why", "executed", "_per_question")

    def __init__(self, *, ran: bool, why: str = "") -> None:
        self.record = "atlas.front.joint/2"
        self.ran = ran
        self.why = why
        self.executed: dict[str, Any] = {"quotients_built": 0, "couplings_built": 0,
                                         "blocks": 0, "blocks_split_after_a_refusal": 0,
                                         "questions": 0, "distinct_axes": 0,
                                         "queries_contracted": 0,
                                         "build_seconds": 0.0, "contraction_seconds": 0.0}
        self._per_question: dict[str, dict[str, Any]] = {}

    def for_question(self, compiled: CompiledQuestion, *,
                     rows_admitted: int | None = None) -> dict[str, Any]:
        """This question's block of both routes, with the one equality the packet rests on."""
        out = dict(self._per_question.get(compiled.spec.qid)
                   or {"record": self.record, "ran": False, "why": self.why})
        integer_full = (out.get("integer_contraction", {}).get("counts") or {}).get("all_axes")
        coupling_full = (out.get("section_coupling", {}).get("counts") or {}).get("all_axes")
        out["agreement"] = {
            "rows_admitted_by_the_frontier_read": rows_admitted,
            "exact_integer_contraction": integer_full,
            "exact_route_weighted_coupling": coupling_full,
            "all_three_agree": (rows_admitted is not None and integer_full is not None
                                and coupling_full is not None
                                and rows_admitted == integer_full == coupling_full),
        }
        return out


def _integer_route(bank: JointBank, X: torch.Tensor, masks: torch.Tensor,
                   budget: int, device: torch.device) -> dict[str, Any]:
    """ONE quotient, ONE integer plan, ONE launch for the whole block's query bank."""
    gpu = lifted("gpu_state")
    ic = lifted("integer_contraction")
    kernels = lifted("contraction_kernels")
    dimension = int(X.shape[1])
    started = time.perf_counter()
    state = gpu.build_state(X, (2,) * dimension)
    continuation = ic.build_integer_continuation(state, max_bytes=budget)
    built = time.perf_counter()
    base = kernels.prepare_boolean_queries(masks, masks.clone(), dimension=dimension)
    exact = ic.prepare_exact_queries(base)
    plan = ic.prepare_integer_execution(continuation, exact, max_bytes=budget)
    counts = ic.integer_boolean_count(plan)
    torch.cuda.synchronize(device)
    bank.executed["quotients_built"] += 1
    bank.executed["build_seconds"] += built - started
    bank.executed["contraction_seconds"] += time.perf_counter() - built
    return {"counts": [int(v) for v in counts.tolist()],  # loop-ok: the block's own query bank
            "build_seconds": built - started,
            "contraction_seconds": time.perf_counter() - built,
            "retained_bytes": int(plan.retained_bytes),
            "quotient_width": int(continuation.width),
            "distinct_label_rows": (int(state.layers[0].children.numel())
                                    if state.layers else 0),
            "work": ic.integer_work(plan)}


def _coupling_route(bank: JointBank, X: torch.Tensor, masks: torch.Tensor,
                    budget: int, device: torch.device) -> dict[str, Any]:
    """ONE coupling over the block's axes; every query's routing mass in ONE contraction."""
    coupling_module = lifted("section_coupling")
    dimension = int(X.shape[1])
    n = int(X.shape[0])
    started = time.perf_counter()
    ones = torch.ones(n, dtype=torch.int64, device=device)
    rows = torch.arange(n, dtype=torch.int64, device=device)
    coupling = coupling_module.build_coupling(
        source_ids=rows, route_source_rows=rows, membership_labels=X,
        route_numerators=ones, common_denominator=1, source_weights=ones,
        cardinalities=(2,) * dimension, max_route_rows=n, max_route_bytes=budget)
    built = time.perf_counter()
    mass = coupling_module.intersection_mass(coupling, _label_masks(masks, dimension))
    torch.cuda.synchronize(device)
    bank.executed["couplings_built"] += 1
    bank.executed["build_seconds"] += built - started
    bank.executed["contraction_seconds"] += time.perf_counter() - built
    return {"coupling": coupling, "module": coupling_module,
            "counts": [int(v) for v in mass.routing_numerator.tolist()],  # loop-ok: the block's own query bank
            "build_seconds": built - started,
            "contraction_seconds": time.perf_counter() - built,
            "tuples_total": int(coupling.postings.tuple_table.shape[0])}


def _way_back(block_result: Mapping[str, Any], lens: Any, mask: int,
              dimension: int, device: torch.device) -> dict[str, Any]:
    """From the tuples the full admission selects, BACK to the source rows they were drawn from.

    This is the only part of route 2 that depends on the question, so it is the only part run
    per question: the coupling itself is the block's. O(tuples + reached rows).
    """
    module = block_result["module"]
    coupling = block_result["coupling"]
    one = torch.tensor([mask], dtype=torch.int32, device=device)
    selection = module.tuples_matching_mask(coupling, _label_masks(one, dimension)[0])
    reached = module.reached_sources(coupling, selection.tuple_indices)
    global_rows = lens.rank_global_all.index_select(0, reached.source_rows.to(torch.int64))
    return {"tuples_matching_the_full_admission": int(selection.tuple_indices.numel()),
            "decode": selection.support_mode,
            "sources_reached": int(global_rows.numel()),
            "sources_reached_sample": [int(v) for v in global_rows[:8].tolist()]}  # loop-ok: the reported sample, bounded at 8


def build_joint_bank(opened: Any, lens: Any, compiled: Sequence[CompiledQuestion], *,
                     columns: Any = None) -> JointBank:
    """ONE build of the quotient over the declared axis set; every question contracted against it.

    Complexity in the module docstring. Every counter on the returned bank is executed work.
    """
    device = lens.rank_global.device
    if device.type != "cuda":
        return JointBank(ran=False,
                         why="both exact routes are CUDA kernels and this lens is on the host")
    budget = _dense_kind_counts_budget_bytes(device)
    bank = JointBank(ran=True)
    axis_of_key: dict[str, torch.Tensor] = {}
    asked: list[_Asked] = []
    for one in compiled:  # loop-ok: the dataset's own declared question list
        rows = admission_axis_rows(opened, lens, one, columns)
        dimension = len(rows)
        if dimension < 1 or dimension > MAX_AXES_PER_BLOCK:
            bank._per_question[one.spec.qid] = {
                "record": bank.record, "ran": False,
                "why": (f"the packed comparator's own bound is 1..{MAX_AXES_PER_BLOCK} binary "
                        f"axes; this question has {dimension}")}
            continue
        keys = []
        names = []
        for key, name, axis in rows:  # loop-ok: this question's own axes
            axis_of_key.setdefault(key, axis)
            keys.append(key)
            names.append(name)
        asked.append(_Asked(qid=one.spec.qid, keys=tuple(keys), names=tuple(names),
                            conditions=dimension - 2))
    bank.executed["questions"] = len(asked)
    bank.executed["distinct_axes"] = len(axis_of_key)
    for block in _block_of(asked, MAX_AXES_PER_BLOCK):  # loop-ok: the blocks the axis bound cut the question list into
        _run_block(bank, block, axis_of_key, lens, budget, device)
    return bank


def _run_block(bank: JointBank, block: Sequence[_Asked], axis_of_key: Mapping[str, torch.Tensor],
               lens: Any, budget: int, device: torch.device) -> None:
    """Build the block's quotient and coupling once and contract the whole bank; on a named
    refusal, split the block and rebuild - which is recorded, never silent. O(block)."""
    ic = lifted("integer_contraction")
    gpu = lifted("gpu_state")
    index: dict[str, int] = {}
    for one in block:  # loop-ok: this block's own questions
        for key in one.keys:  # loop-ok: this question's own axes
            index.setdefault(key, len(index))
    ordered = sorted(index, key=lambda key: index[key])
    X = torch.stack([axis_of_key[key] for key in ordered], dim=1).to(torch.int64)  # loop-ok: this block's own distinct axes
    masks, slices = _queries_of(block, index, device)
    dimension = len(ordered)
    bank.executed["blocks"] += 1
    bank.executed["queries_contracted"] += int(masks.numel())

    integer: dict[str, Any] | None = None
    integer_refusal: dict[str, Any] | None = None
    try:
        integer = _integer_route(bank, X, masks, budget, device)
    except (ic.IntegerPlanRefusal, gpu.ExactMassRequired, MemoryError) as refusal:
        integer_refusal = {"refusal": type(refusal).__name__, "why": str(refusal)}
    coupling: dict[str, Any] | None = None
    coupling_refusal: dict[str, Any] | None = None
    try:
        coupling = _coupling_route(bank, X, masks, budget, device)
    except (ValueError, TypeError, MemoryError, RuntimeError) as refusal:
        coupling_refusal = {"refusal": type(refusal).__name__, "why": str(refusal)}

    if (integer is None or coupling is None) and len(block) > 1:
        # A refusal at this width is a statement about the BLOCK, not about the questions: the
        # block is halved and rebuilt, so a question that can be answered exactly still is.
        bank.executed["blocks_split_after_a_refusal"] += 1
        half = len(block) // 2
        _run_block(bank, block[:half], axis_of_key, lens, budget, device)
        _run_block(bank, block[half:], axis_of_key, lens, budget, device)
        return

    shared = {"block_questions": [one.qid for one in block],  # loop-ok: this block's own questions
              "block_axes": ordered, "block_dimension": dimension,
              "queries_in_the_batch": int(masks.numel()),
              "what_this_is": ("the quotient and the coupling of this block of the DECLARED axis "
                               "set, built ONCE and contracted for every question in it; a "
                               "question charges no build")}
    for one in block:  # loop-ok: this block's own questions
        cut = slices[one.qid]
        names = cut["names"]
        out: dict[str, Any] = {"record": bank.record, "ran": True,
                               "axes": list(one.names), "queries": names,
                               "declared_device_budget_bytes": int(budget),
                               "budget_derivation": (
                                   "the same declared device budget ranges.py spends against "
                                   "(_dense_kind_counts_budget_bytes: a fraction of the device's "
                                   "own total memory), never a literal in this file"),
                               "built_once_for_the_block": shared}
        if integer is not None:
            counts = integer["counts"][cut["start"]:cut["stop"]]
            out["integer_contraction"] = {
                "ran": True, "counts": dict(zip(names, counts)),
                "seconds": 0.0,
                "why_zero": ("the quotient of this block was built once and contracted once for "
                             "every question in it; this question charged no build and no "
                             "launch of its own"),
                "block_build_seconds": integer["build_seconds"],
                "block_contraction_seconds": integer["contraction_seconds"],
                "retained_bytes": integer["retained_bytes"],
                "quotient_width": integer["quotient_width"],
                "distinct_label_rows": integer["distinct_label_rows"],
                "work": integer["work"],
                "kept_verbatim": ("synthetics papers/corpus-as-a-state/reconstruction/extension/"
                                  "integer_contraction.py over reconstruction/gpu_state.py, "
                                  "loaded by atlas.front.lift")}
        else:
            out["integer_contraction"] = {
                "ran": False, **(integer_refusal or {}), "seconds": 0.0,
                "this_is_a_result": ("the exact route REFUSES by name rather than contracting in "
                                     "floating point: a float joint count that cannot be "
                                     "certified as an integer is not an exact joint count")}
        if coupling is not None:
            counts = coupling["counts"][cut["start"]:cut["stop"]]
            started = time.perf_counter()
            back = _way_back(coupling, lens, int(_mask_at(masks, cut["start"])), dimension,
                             device)
            out["section_coupling"] = {
                "ran": True, "counts": dict(zip(names, counts)),
                "seconds": time.perf_counter() - started,
                "what_the_seconds_are": ("the way BACK only: the coupling itself was built once "
                                         "for the block and every query's routing mass came out "
                                         "of one contraction"),
                "block_build_seconds": coupling["build_seconds"],
                "block_contraction_seconds": coupling["contraction_seconds"],
                "tuples_total": coupling["tuples_total"], **back,
                "what_this_is": ("the way BACK: a selected tuple's CSR range gathered to the "
                                 "source rows it was drawn from, which is the coupling's own "
                                 "answer to WO-20260922-answers-name-their-content"),
                "kept_verbatim": ("synthetics papers/corpus-as-a-state/reconstruction/"
                                  "section_coupling.py, loaded by atlas.front.lift")}
        else:
            out["section_coupling"] = {"ran": False, **(coupling_refusal or {}),
                                       "seconds": 0.0}
        bank._per_question[one.qid] = out


def _mask_at(masks: torch.Tensor, position: int) -> int:
    """The query mask at one position of the block's bank. O(1), one host read."""
    return int(masks[position].item())


def exact_joint_counts(opened: Any, lens: Any, compiled: CompiledQuestion, *,
                       rows_admitted: int | None = None,
                       bank: JointBank | None = None,
                       columns: Any = None) -> dict[str, Any]:
    """Both exact routes to the joint counts of ONE question's admission axes.

    With a ``bank``, this is a lookup: the quotient was built once for the run. Without one -
    a caller that has a single question and no run - a bank of exactly this question is built,
    which is the old per-call behaviour and is stated as such in the returned block.
    """
    if bank is None:
        bank = build_joint_bank(opened, lens, [compiled], columns=columns)
    return bank.for_question(compiled, rows_admitted=rows_admitted)


# Exact counts/agreements stay substantive; elapsed build/back-route work is diagnostic.



# The inert closed receipt contract; numeric execution remains owned here.
from ..receipt_diagnostics import joint_bank_parts, joint_counts_parts
