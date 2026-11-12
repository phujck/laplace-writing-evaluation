"""read.py - THE READ: a frontier of ranges, decided by reductions, with a certificate.

What this is not, said first because it is what a capable model writes by default and what the
charter rejects by name: it is not a score, not a top-k, not a re-ordering of a similarity
ranking, and not a walk that opens a node because opening is easier than deciding. There is no
embedding in this file and no float that came from a model.

WHAT IT IS. A frontier is a cut level of one lens's whole refinement - every component's current
ranges, which TILE the rank space contiguously. Each round:

  1. ONE ``frontier_boundaries`` call describes the level.
  2. ONE reduction call per (row kind, column) of the question describes every range's face
     (``faces.frontier_face``) - not one call per node.
  3. ``ranges.admits`` gives each range {decided_in, excluded, open} per condition under the
     declared==0 rule, and the conditions are conjoined: decided_in is the AND, excluded the OR,
     open the rest.
  4. THE QUESTION'S TOLERANCE, not the lens's, decides whether an OPEN range still has to be
     opened: section_synthesis sec. 4's bound |answer error| <= sqrt(L_f(C)) sqrt(1/z - 1) with
     sqrt(L_f) the node's own measured task residual and z its own reference mass, both read off
     the persisted node table.
  5. Only the ranges still OPEN are replaced by their children; the decided ones stay exactly as
     they are, so the level always tiles and no range is ever visited twice.

It ends in one of two states, never in a third:

  A CERTIFICATE - every range of the final frontier is decided_in, excluded, or opened, so no
  unopened range's bound could change the answer at this tolerance. The certificate carries the
  worst bound it did not open.
  A REFUSAL with a RESOURCE STATEMENT - the rows the supplied ranges address cost more bytes
  than the question's declared byte budget. It says how many rows, how many bytes and what the
  budget was, and it never returns a partial answer as though it were an answer.

PARTIAL DOWN AGAINST WHOLE DOWN. ``supply='partial'`` pays the witness bytes of the rows that
actually satisfy the conditions; ``supply='whole'`` pays the bytes of every row of a supplied
range, which is what "opening a node" means when a node has no face to filter with. The J1
carried residual says graded was 0.1379/0.2931/0.6034 WORSE than flat at every LongMemEval
budget under whole supply; both disciplines run here, in this one read path, so the comparison
is a measurement of the same code rather than of two instruments.

THE ANSWER NAMES ITS CONTENT (WO-20260922-answers-name-their-content). Every answer carries the
B.2 identity and the witness span ADDRESS of every row it was drawn from, and for a range the
read decided WITHOUT opening it, the range handle (lens hash, component content address, lo, hi,
the condition digest) together with its expansion to row identities through the rank-order
postings. ``resolve_handles`` re-resolves either kind in any process from the record alone.

Complexity, M the lens's bound rows, F the frontier, C conditions, d the depth reached:
O(d * C) device calls, each one bucketize + one scatter over M; the answer is one gather plus
one reduction over the SUPPLIED positions, never over M.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import torch

from ..grading import ranges as R
from ..ids import chash
from ..record.columns import date_of_key
from ..record.identity import ids_of_words
from . import faces as FA
from .lift import lifted
from .question import CompiledQuestion

__all__ = ["ReadResult", "RowHandles", "RangeHandles", "Descent", "read",
           "read_supplies", "descend", "finish_read", "finish_read_supplies",
           "witness_byte_lengths", "row_gather", "evidence_of_a_supply",
           "positions_of_a_descent",
           "direct_answer",
           "packed_direct_control", "resolve_handles", "evidence_within_a_budget",
           "admission_axes", "admission_axis_rows"]

_OPEN, _IN, _EXCLUDED = 0, 1, 2

# THE LENS'S OWN CONSTANTS, HELD ONCE. Both numbers are reductions over the whole node table and
# neither depends on the question or on the supply, so computing them inside the read charged two
# O(N) passes and two device synchronisations per supply per question - measured at a fifth of a
# read on the engine's ledgers. Keyed by the lens's own content hash and its node count, so a
# different lens or a rebuilt one never reads another's.
_LENS_CONSTANTS: dict[tuple[str, int], dict[str, int]] = {}


def lens_constants(lens: FA.LoadedLens) -> dict[str, int]:
    """Two counters of the persisted node table, computed once per lens. O(N) once, O(1) after."""
    key = (lens.lens_hash, lens.nodes)
    held = _LENS_CONSTANTS.get(key)
    if held is None:
        priced = (lens.priced_rank != lens.capacity_rank).sum()
        over = (lens.rank > lens.priced_rank).sum()
        counted = torch.stack([priced, over]).tolist()
        held = {"nodes_where_the_priced_rank_differs_from_the_capacity_rank": int(counted[0]),
                "nodes_where_rank_exceeds_the_priced_rank": int(counted[1])}
        _LENS_CONSTANTS[key] = held
    return held


@dataclass(frozen=True, slots=True)
class RowHandles:
    """The handles of every row an answer was drawn from - AS A GATHER, never as a mint.

    THE AUTHOR, 2026-09-22: "Why would it need to be mounting handles on every fucking descent.
    Does reconstruct need an upfold before every execution?" It does not. A row's B.2 identity
    is a function of the row's own content, so it is minted once at ingestion
    (``record/identity.py``) and stored as a fixed-width column; its witness address is a row
    of the span table. So every field of this object is ONE ``index_select`` on the device, and
    what the read pays is three gathers whatever the answer's size.

    What is NOT here is any string. The hex identity and the blob handle are built in
    ``as_dicts``, which runs when a receipt is serialised - off the read's timed path. Before
    this, ``_row_handles`` called ``chash`` once per supplied row (5,084 calls per read,
    0.49-0.81 of the read's whole seconds, measured through the declared entry).
    """

    row_kind: str
    identity: torch.Tensor        # int64 [k, 4] - B.2, gathered from the record's own column
    global_ordinal: torch.Tensor  # int64 [k]
    address: torch.Tensor         # int64 [k, 3] - (blob ordinal, start, end)
    blob_handles: tuple[str, ...]  # the span table's handle list, indexed by address[:, 0]

    def __len__(self) -> int:
        return int(self.global_ordinal.numel())

    def as_dicts(self, limit: int | None = None) -> list[dict[str, Any]]:
        """The handle list as JSON. SERIALISATION: one host transfer, then one dict per row."""
        stop = len(self) if limit is None else min(limit, len(self))
        if stop <= 0:
            return []
        ids = ids_of_words(self.identity[:stop])
        ordinals = self.global_ordinal[:stop].tolist()
        address = self.address[:stop].cpu().numpy()
        return [{"row_id": row_id, "row_kind": self.row_kind,
                 "global_ordinal": int(ordinal),
                 "content_handle": self.blob_handles[int(row[0])],
                 "start": int(row[1]), "end": int(row[2]),
                 "bytes": int(row[2]) - int(row[1])}
                for row_id, ordinal, row in zip(ids, ordinals, address)]  # loop-ok: the reported handle list, bounded by `limit`


@dataclass(frozen=True, slots=True)
class RangeHandles:
    """The handles of the ranges the read decided WITHOUT opening them - constants of the tree.

    A.33(a)(4)/(5)'s discipline applied to a read: the thing that decided the answer is named by
    content address. A range's handle is (lens hash, component content address, lo, hi,
    condition) and every one of those is already a constant of the persisted tree, so the read
    stores four tensors and nothing else. The EXPANSION - the record rows inside the range,
    reachable without any scalar gate (C.16, F.17) - is a slice of ``rank_global`` computed when
    a handle is asked for it, not materialised as a Python tuple per range at read time.
    """

    lens_hash: str
    component: torch.Tensor           # int64 [F]
    lo: torch.Tensor                  # int64 [F]
    hi: torch.Tensor                  # int64 [F]
    condition_digest: str
    verdict: str
    component_address: tuple[str, ...]
    rank_global: torch.Tensor         # the lens's rank order; the expansion is a slice of it

    def __len__(self) -> int:
        return int(self.lo.numel())

    def rows_of(self, index: int) -> list[int]:
        """The record rows one decided range covers. O(hi - lo), one slice."""
        return self.rank_global[int(self.lo[index]):int(self.hi[index])].tolist()

    def as_dicts(self, limit: int | None = None, *, rows: int = 12) -> list[dict[str, Any]]:
        stop = len(self) if limit is None else min(limit, len(self))
        if stop <= 0:
            return []
        components = self.component[:stop].tolist()
        los, his = self.lo[:stop].tolist(), self.hi[:stop].tolist()
        return [{"lens_hash": self.lens_hash, "component": int(component),
                 "component_address": self.component_address[int(component)],
                 "lo": int(lo), "hi": int(hi), "condition_digest": self.condition_digest,
                 "verdict": self.verdict, "rows_in_the_range": int(hi) - int(lo),
                 "row_ordinals_sample": self.rank_global[int(lo):int(lo) + rows].tolist()}
                for component, lo, hi in zip(components, los, his)]  # loop-ok: the reported range list, bounded by `limit`


@dataclass(frozen=True, slots=True)
class ReadResult:
    """What one read returned, with every counter the claim rests on."""

    qid: str
    answer: Any
    certificate: dict[str, Any] | None
    refusal: dict[str, Any] | None
    tolerance: dict[str, Any]
    supply: str
    rounds: tuple[dict[str, Any], ...]
    executed: dict[str, Any]
    row_handles: RowHandles
    range_handles: RangeHandles
    evidence: dict[str, Any]
    seconds: float

    def as_dict(self, *, handles: int = 40) -> dict[str, Any]:
        return {
            "qid": self.qid, "answer": self.answer, "certificate": self.certificate,
            "refusal": self.refusal, "tolerance": self.tolerance, "supply": self.supply,
            "rounds": list(self.rounds), "executed": self.executed,
            "evidence": self.evidence, "seconds": self.seconds,
            "row_handles_total": len(self.row_handles),
            "row_handles": self.row_handles.as_dicts(handles),
            "range_handles_total": len(self.range_handles),
            "range_handles": self.range_handles.as_dicts(handles),
        }


# ------------------------------------------------------------------ positions and predicates
def _positions_of_ranges(lo: torch.Tensor, hi: torch.Tensor) -> torch.Tensor:
    """Every rank position covered by a set of ranges, vectorised (no loop over a range).

    One ``repeat_interleave`` of the starts plus the within-range offset, exactly the trick
    ``tree._cross_counts`` uses for leaf spans. O(total positions).
    """
    sizes = hi - lo
    keep = sizes > 0
    lo, sizes = lo[keep], sizes[keep]
    if not sizes.numel():
        return torch.empty(0, dtype=torch.int64, device=lo.device)
    starts = torch.repeat_interleave(lo, sizes)
    ends = torch.cumsum(sizes, 0)
    offsets = (torch.arange(int(sizes.sum()), dtype=torch.int64, device=lo.device)
               - torch.repeat_interleave(ends - sizes, sizes))
    return starts + offsets


def _satisfies(entry: Mapping[str, Any], values: torch.Tensor, null: int) -> torch.Tensor:
    """Does each of these positions' rows satisfy this ONE condition? Vectorised, O(k).

    The null conventions are the record's declared ones and they are stated here because this is
    the only place a read may interpret a sentinel: for a coded column a null row does not
    satisfy an equality or a membership (it asserts nothing); for a DAY INTERVAL a null bound
    reads as -infinity below and +infinity above (C.25's own convention, the toy's
    ``valid_from``/``valid_to``), so a row with no declared bound is inside every interval.
    """
    payload = entry["payload"]
    kind = payload["kind"]
    declared = values != null
    if kind == "equality":
        return declared & (values == int(payload["code"]))
    if kind == "membership":
        codes = torch.as_tensor(list(payload["codes"]), dtype=values.dtype,
                                device=values.device)
        return declared & torch.isin(values, codes)
    if kind == "count_threshold":
        return declared & (values == int(payload["code"]))
    if kind == "day":
        return declared & (values == int(payload["day"]))
    lo, hi = int(payload["lo_day"]), int(payload["hi_day"])
    inside = (values >= lo) & (values <= hi)
    return torch.where(declared, inside, torch.ones_like(inside))


def _condition_digest(compiled: CompiledQuestion) -> str:
    return chash({"qid": compiled.spec.qid,
                  "conditions": [c.as_dict() for c in compiled.spec.conditions],  # loop-ok: the question's own condition list
                  "payloads": compiled.payloads()})


_REACHED = "anchor_reached"


def _columns_for(opened: Any, lens: FA.LoadedLens,
                 columns: FA.RankedColumns | None) -> FA.RankedColumns:
    """The lens's ranked columns. The DOOR opens them once per (record, lens) and hands them
    down; a caller that supplies none gets a private set, and the read's own
    ``ranked_columns_built`` counter then says how many it had to gather itself. O(1)."""
    if columns is not None:
        return columns
    return FA.RankedColumns(opened.ingestion.store, lens)


def _entries(compiled: CompiledQuestion, columns: FA.RankedColumns) -> list[dict[str, Any]]:
    """The question's conditions, plus the derived anchor-reached condition when it has one.

    Each entry carries the ranked column it reads, looked up ONCE here rather than once per
    round, per supply discipline and per control.
    """
    entries: list[dict[str, Any]] = []
    for coded in compiled.coded:  # loop-ok: the question's own declared condition list
        ranked, null, table = columns.get(coded["row_kind"], coded["column"])
        entries.append({**coded, "ranked": ranked, "null": null, "table": table})
    reached = compiled.anchor.get("reached_rows")
    if reached is not None:
        kind = compiled.spec.row_kind
        ranked, null, table = columns.anchor_reached(
            f"{kind}/{compiled.spec.qid}/{_REACHED}", kind, reached)
        entries.append({"row_kind": kind, "column": _REACHED,
                        "payload": {"kind": "equality", "code": 1}, "condition": None,
                        "ranked": ranked, "null": null, "table": table})
    return entries


def _face_for(entry: Mapping[str, Any], columns: FA.RankedColumns, lens: FA.LoadedLens,
              boundaries: torch.Tensor) -> FA.FrontierFace:
    kind, column = entry["row_kind"], entry["column"]
    ranked = entry["ranked"]
    null = entry["null"]
    if column == _REACHED:
        ranges = _ranges_in(boundaries)
        counts, receipt = R.measured("kind_counts", R.kind_counts, ranked, boundaries, 2, null,
                                     _device=ranked.device, _rows=lens.rows, _ranges=ranges)
        return FA.FrontierFace(kind, column, "bool", "kind", "kind_counts", ranges,
                               R.declared_counts_from_kind_counts(counts), counts, None, None,
                               None, receipt)
    return FA.frontier_face(columns.store, lens, kind, column, boundaries, ranked=ranked)


def _ranges_in(boundaries: torch.Tensor) -> int:
    """F, the number of ranges a boundary tensor describes. O(1)."""
    return int(boundaries.numel()) - 1


# ------------------------------------------------------------------ the read
@dataclass(frozen=True, slots=True)
class Descent:
    """What ONE frontier descent left behind: the final frontier and what it cost.

    Split out of ``read`` so that the BATCHED descent of ``planner.py`` - one shared frontier for
    every tree-route question of a dataset, one reduction call per distinct (row kind, column)
    per round instead of one per question per condition per round - can produce exactly the same
    object and hand it to exactly the same answer, certificate and handle tail. Nothing here is
    per-route: a route that does not descend at all (postings, the packed scan, a cut reading)
    supplies its positions directly to ``finish_read``.
    """

    lo: torch.Tensor
    hi: torch.Tensor
    node: torch.Tensor
    state: torch.Tensor
    rounds: tuple[dict[str, Any], ...]
    reduction_calls: int
    reduction_seconds: float
    peak_reduction_bytes: int
    worst_decided_bound: float
    seconds: float


def descend(lens: FA.LoadedLens, entries: Sequence[Mapping[str, Any]],
            columns: FA.RankedColumns, *, tau: float) -> Descent:
    """THE FRONTIER DESCENT of one question: rounds of reductions until nothing is open.

    Complexity: O(depth * conditions) device calls, each O(M + F*V).
    """
    started = time.perf_counter()
    device = lens.rank_global.device
    node = lens.roots.clone()
    lo = lens.lo.index_select(0, node)
    hi = lens.hi.index_select(0, node)
    state = torch.zeros(node.numel(), dtype=torch.int8, device=device)
    rounds: list[dict[str, Any]] = []
    reduction_calls = 0
    reduction_seconds = 0.0
    peak_reduction_bytes = 0
    worst_decided_bound = 0.0

    while True:  # loop-ok: ONE round per LEVEL of the refinement (depth ~ log N); every round is one reduction call per condition over the WHOLE frontier
        if not bool((state == _OPEN).any()):
            break
        order = torch.argsort(lo)
        lo, hi, node, state = lo[order], hi[order], node[order], state[order]
        boundaries = R.frontier_boundaries(lo, hi)
        verdict_in = torch.ones(lo.numel(), dtype=torch.bool, device=device)
        verdict_ex = torch.zeros(lo.numel(), dtype=torch.bool, device=device)
        faces: list[dict[str, Any]] = []
        for entry in entries:  # loop-ok: the question's own declared condition list - ONE reduction call each for the WHOLE frontier, never one per node
            face = _face_for(entry, columns, lens, boundaries)
            admitted = FA.admits_over_frontier(entry["payload"], face)
            verdict_in = verdict_in & admitted.decided_in
            verdict_ex = verdict_ex | admitted.excluded
            reduction_calls += 1
            reduction_seconds += face.receipt.seconds
            peak_reduction_bytes = max(peak_reduction_bytes, face.receipt.peak_device_bytes)
            faces.append({"column": face.field, "form": face.form,
                          "verdict": admitted.as_summary()})

        # THE QUESTION'S TOLERANCE (section_synthesis sec. 4): a range still open after the
        # conditions is decided where it stands when its own error bound is at or below tau.
        mass = lens.mass.index_select(0, node).clamp(min=1e-30)
        residual = lens.task_residual.index_select(0, node).abs()
        bound = residual * torch.sqrt((1.0 / mass - 1.0).clamp(min=0.0))
        was_open = state == _OPEN
        still_open = was_open & ~verdict_in & ~verdict_ex
        within = still_open & (bound <= tau)
        state = torch.where(was_open & verdict_ex, torch.full_like(state, _EXCLUDED), state)
        state = torch.where(was_open & verdict_in, torch.full_like(state, _IN), state)
        state = torch.where(within, torch.full_like(state, _IN), state)
        if bool(within.any()):
            worst_decided_bound = max(worst_decided_bound, float(bound[within].max()))

        descending = torch.nonzero((state == _OPEN) & (lens.left.index_select(0, node) >= 0),
                                   as_tuple=False).flatten()
        rounds.append({"round": len(rounds), "ranges": int(lo.numel()),
                       "decided_in": int((state == _IN).sum()),
                       "excluded": int((state == _EXCLUDED).sum()),
                       "open": int((state == _OPEN).sum()),
                       "decided_by_the_tolerance": int(within.sum()),
                       "worst_bound_decided_by_the_tolerance": worst_decided_bound,
                       "descending": int(descending.numel()), "faces": faces})
        if not descending.numel():
            break
        keep = torch.ones(state.numel(), dtype=torch.bool, device=device)
        keep[descending] = False                   # every range stays except the descending
        parents = node.index_select(0, descending)
        children = torch.stack([lens.left.index_select(0, parents),
                                lens.right.index_select(0, parents)]).T.reshape(-1)
        node = torch.cat([node[keep], children])
        lo = torch.cat([lo[keep], lens.lo.index_select(0, children)])
        hi = torch.cat([hi[keep], lens.hi.index_select(0, children)])
        state = torch.cat([state[keep], state.new_zeros(children.numel())])

    return Descent(lo=lo, hi=hi, node=node, state=state, rounds=tuple(rounds),
                   reduction_calls=reduction_calls, reduction_seconds=reduction_seconds,
                   peak_reduction_bytes=peak_reduction_bytes,
                   worst_decided_bound=worst_decided_bound,
                   seconds=time.perf_counter() - started)


def positions_of_a_descent(lens: FA.LoadedLens,
                           descent: Descent) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """The three position sets a finished descent supplies: touched, opened, excluded.

    WHAT THE LENS OWES A ROW IT COULD NOT SEAT (the J1 carried residual, decided here because
    only the read can decide it): a declared carrier row with no counted witness has no node, so
    NO range can decide it and no tolerance can excuse it. It is supplied as an ALWAYS-OPEN range
    - opened, paid for in bytes, and counted separately in the certificate - because the
    alternative is a read that quietly answers over a smaller record than the one it was asked
    about. O(supplied positions), all vectorised.
    """
    lo, hi, state = descent.lo, descent.hi, descent.state
    device = lo.device
    in_mask = state == _IN
    leaf_open = state == _OPEN
    tree_positions = _positions_of_ranges(torch.cat([lo[in_mask], lo[leaf_open]]),
                                          torch.cat([hi[in_mask], hi[leaf_open]]))
    excluded_mask = state == _EXCLUDED
    excluded_positions = _positions_of_ranges(lo[excluded_mask], hi[excluded_mask])
    unseated = torch.arange(lens.rows, lens.rows + lens.unbound, dtype=torch.int64,
                            device=device)
    positions = torch.cat([tree_positions, unseated])
    opened_positions = torch.cat([_positions_of_ranges(lo[leaf_open], hi[leaf_open]), unseated])
    return positions, opened_positions, excluded_positions


def read(opened: Any, lens: FA.LoadedLens, compiled: CompiledQuestion, *,
         tolerance: Mapping[str, Any], supply: str = "partial",
         byte_budget: int | None = None,
         columns: FA.RankedColumns | None = None,
         entries: Sequence[Mapping[str, Any]] | None = None,
         descent: Descent | None = None) -> ReadResult:
    """One supply discipline of ``read_supplies``. O(depth * conditions) device calls."""
    return read_supplies(opened, lens, compiled, tolerance=tolerance, supplies=(supply,),
                         byte_budget=byte_budget, columns=columns, entries=entries,
                         descent=descent)[supply]


def read_supplies(opened: Any, lens: FA.LoadedLens, compiled: CompiledQuestion, *,
                  tolerance: Mapping[str, Any], supplies: Sequence[str] = ("partial",),
                  byte_budget: int | None = None,
                  columns: FA.RankedColumns | None = None,
                  entries: Sequence[Mapping[str, Any]] | None = None,
                  descent: Descent | None = None) -> dict[str, ReadResult]:
    """One question, one lens, one tolerance: descend the frontier and certify or refuse.

    ``entries`` and ``descent`` let the BATCHED planner hand in a descent it already ran on a
    frontier SHARED with the dataset's other tree-route questions; with neither, this descends on
    its own exactly as before.

    Complexity: O(depth * conditions) device calls, each O(M + F*V); the answer is one gather
    and one reduction over the SUPPLIED positions.
    """
    started = time.perf_counter()
    tau = float(tolerance["tau"])
    budget = int(byte_budget if byte_budget is not None else compiled.spec.byte_budget)
    columns = _columns_for(opened, lens, columns)
    built_before = columns.built_after_open
    derived_before = columns.derived_built
    if entries is None:
        entries = _entries(compiled, columns)
    if descent is None:
        descent = descend(lens, entries, columns, tau=tau)
    state = descent.state
    in_mask = state == _IN
    leaf_open = state == _OPEN
    positions, opened_positions, excluded_positions = positions_of_a_descent(lens, descent)
    certificate = {
        "certified": True, "route": "the lens tree frontier",
        "statement": ("every range of the final frontier is decided_in, excluded, or "
                      "opened: no unopened range's bound could change this answer at this "
                      "tolerance"),
        "ranges_final": int(descent.lo.numel()), "decided_in": int(in_mask.sum()),
        "excluded": int((state == _EXCLUDED).sum()),
        "opened_at_the_leaves": int(leaf_open.sum()),
        "rows_opened_because_the_lens_could_not_seat_them": lens.unbound,
        "worst_bound_not_opened": descent.worst_decided_bound, "tolerance": tau,
        "bound_form": ("sqrt(L_f(C)) * sqrt(1/z - 1), section_synthesis sec. 4, with "
                       "sqrt(L_f) the node's measured task residual and z its reference "
                       "mass, both read off the persisted node table"),
    }
    return finish_read_supplies(
        opened, lens, compiled, columns, entries,
        positions=positions, positions_opened=opened_positions,
        positions_excluded=int(excluded_positions.numel()), rounds=descent.rounds,
        tolerance=tolerance, supplies=supplies, budget=budget,
        route="the lens tree frontier", certificate=certificate,
        range_handles=_range_handles(lens, descent.lo[in_mask], descent.hi[in_mask],
                                     descent.node[in_mask], _condition_digest(compiled)),
        started=started, descent_seconds=descent.seconds,
        executed_extra={
            "reduction_calls": descent.reduction_calls,
            "reduction_seconds": descent.reduction_seconds,
            "peak_reduction_device_bytes": descent.peak_reduction_bytes,
            "ranges_visited": sum(r["ranges"] for r in descent.rounds),  # loop-ok: the rounds this read ran, depth ~ log N
            "ranges_final": int(descent.lo.numel()),
            "ranked_columns_built": columns.built_after_open - built_before,
            "ranked_columns_gathered_when_the_lens_was_opened": columns.built_at_open,
            "anchor_columns_built": columns.derived_built - derived_before,
        })


def finish_read(opened: Any, lens: FA.LoadedLens, compiled: CompiledQuestion,
                columns: FA.RankedColumns, entries: Sequence[Mapping[str, Any]], *,
                positions: torch.Tensor, positions_opened: torch.Tensor,
                positions_excluded: int, rounds: Sequence[Mapping[str, Any]],
                tolerance: Mapping[str, Any], supply: str, budget: int, route: str,
                certificate: dict[str, Any] | None, range_handles: RangeHandles,
                started: float, descent_seconds: float,
                executed_extra: Mapping[str, Any]) -> ReadResult:
    """One supply discipline of ``finish_read_supplies``. O(k)."""
    return finish_read_supplies(
        opened, lens, compiled, columns, entries, positions=positions,
        positions_opened=positions_opened, positions_excluded=positions_excluded,
        rounds=rounds, tolerance=tolerance, supplies=(supply,), budget=budget, route=route,
        certificate=certificate, range_handles=range_handles, started=started,
        descent_seconds=descent_seconds, executed_extra=executed_extra)[supply]


def finish_read_supplies(opened: Any, lens: FA.LoadedLens, compiled: CompiledQuestion,
                         columns: FA.RankedColumns, entries: Sequence[Mapping[str, Any]], *,
                         positions: torch.Tensor, positions_opened: torch.Tensor,
                         positions_excluded: int, rounds: Sequence[Mapping[str, Any]],
                         tolerance: Mapping[str, Any], supplies: Sequence[str], budget: int,
                         route: str, certificate: dict[str, Any] | None,
                         range_handles: RangeHandles, started: float, descent_seconds: float,
                         executed_extra: Mapping[str, Any]) -> dict[str, ReadResult]:
    """THE ONE TAIL EVERY ROUTE SHARES: the answer, the certificate or the byte refusal, the
    handles of the content the answer was drawn from, and the counters the claim rests on.

    A route decides WHICH rank positions it supplies and states its own certificate; everything
    downstream of that - the masks, the operator, the two supply disciplines, the budget refusal,
    the B.2 identities and witness addresses - is identical for the frontier descent, the
    postings route, the exact contraction, a cut reading and the packed scan. That is what makes
    the per-class measurement a comparison of ROUTES rather than of instruments.

    THE SUPPLY DISCIPLINES SHARE ONE COMPUTATION, which is this packet's own rule (anything that
    does not depend on the question is computed once) applied one level down: the masks, the
    operator, the answer and both disciplines' witness byte lengths do not depend on WHICH
    discipline is being paid for, so they are computed once here and only the budget arithmetic,
    the refusal sentence and the handle limit are done per supply. Before this, asking for
    partial and whole ran the whole tail twice.

    Complexity: O(k) over the supplied positions, all vectorised.
    """
    device = lens.rank_global.device
    universe = columns.universe
    tau = float(tolerance["tau"])
    opened_positions = positions_opened

    satisfied = torch.ones(positions.numel(), dtype=torch.bool, device=device)
    for entry in entries:  # loop-ok: the question's own condition list, one masked gather each
        satisfied = satisfied & _satisfies(entry, entry["ranked"].index_select(0, positions),
                                           entry["null"])
    answer_column = compiled.spec.operator.answer_column
    ranked_answer, answer_null, answer_table = columns.get(compiled.spec.row_kind, answer_column)
    values = ranked_answer.index_select(0, positions)
    mine = columns.mine(compiled.spec.row_kind).index_select(0, positions)
    admitted_positions = positions[satisfied & mine & (values != answer_null)]

    answer, answer_detail = _apply_operator(compiled, columns, admitted_positions, answer_table)
    answer_seconds = time.perf_counter() - started - descent_seconds

    partial_rows = universe.index_select(0, admitted_positions)
    whole_rows = universe.index_select(0, positions)
    lengths = witness_byte_lengths(opened, compiled.spec.row_kind, partial_rows, whole_rows)
    gathered = lengths["partial_gather"]
    # A REFUTATION NAMES ITS CONTENT TOO (WO-20260922-answers-name-their-content). When NO row is
    # admitted the answer is still drawn from something - the rows the route EXAMINED and found
    # not to satisfy the conditions - and an empty handle list would say the opposite. So the
    # handles of an empty answer are the examined set, within the same declared byte budget, and
    # the receipt says that is what they are. Measured on the toy: Q4 ("Did I ever live in
    # Leeds?", answer False) returned an answer with no handle of any kind.
    examined = None
    if not admitted_positions.numel() and whole_rows.numel():
        examined = row_gather(opened, compiled.spec.row_kind, whole_rows)
        if examined["lengths"].numel():
            running = torch.cumsum(examined["lengths"], 0)
            examined["fits"] = int((running <= budget).sum())
        else:
            examined["fits"] = 0
    evidence_seconds = time.perf_counter() - started - descent_seconds - answer_seconds

    out: dict[str, ReadResult] = {}
    for supply in supplies:  # loop-ok: the declared supply disciplines, partial and whole
        evidence = evidence_of_a_supply(lengths, budget=budget, supply=supply)
        refusal = None
        certified = certificate
        if evidence["bytes_needed"] > budget:
            refusal = {
                "refusal": "READ-BYTE-BUDGET-EXHAUSTED",
                "resource_statement": (
                    f"the supplied positions of the {route} route address "
                    f"{evidence['rows_needed']} rows and "
                    f"{evidence['bytes_needed']} witness bytes under {supply} supply; the "
                    f"question declared a byte budget of {budget}, which pays for "
                    f"{evidence['rows_supplied']} of them, and at tolerance {tolerance['name']} "
                    f"(tau = {tau}) {int(opened_positions.numel())} positions were opened"),
                "bytes_needed": evidence["bytes_needed"], "byte_budget": budget,
                "rows_needed": evidence["rows_needed"],
                "rows_paid_for": evidence["rows_supplied"],
                "positions_opened": int(opened_positions.numel()),
            }
            certified = None
        handles_started = time.perf_counter()
        if examined is not None:
            row_handles = _row_handles(opened, compiled.spec.row_kind, whole_rows,
                                       limit=int(examined["fits"]), gathered=examined)
        else:
            row_handles = _row_handles(opened, compiled.spec.row_kind, partial_rows,
                                       limit=evidence["rows_supplied"], gathered=gathered)
        handles_seconds = time.perf_counter() - handles_started
        out[supply] = _assembled(
            compiled, lens, columns, answer, answer_detail, certified, refusal, tolerance,
            supply, rounds, executed_extra, row_handles, range_handles, evidence, route,
            positions, opened_positions, positions_excluded, admitted_positions,
            descent_seconds, answer_seconds, evidence_seconds, handles_seconds, started,
            examined is not None)
    return out


def _assembled(compiled: CompiledQuestion, lens: FA.LoadedLens, columns: FA.RankedColumns,
               answer: Any, answer_detail: Mapping[str, Any],
               certificate: dict[str, Any] | None, refusal: dict[str, Any] | None,
               tolerance: Mapping[str, Any], supply: str, rounds: Sequence[Mapping[str, Any]],
               executed_extra: Mapping[str, Any], row_handles: RowHandles,
               range_handles: RangeHandles, evidence: Mapping[str, Any], route: str,
               positions: torch.Tensor, opened_positions: torch.Tensor,
               positions_excluded: int, admitted_positions: torch.Tensor,
               descent_seconds: float, answer_seconds: float, evidence_seconds: float,
               handles_seconds: float, started: float,
               examined_set: bool = False) -> ReadResult:
    """ONE ``ReadResult`` of one supply, from the shared computation. O(1)."""
    executed = {
        "route": route,
        "rounds": len(rounds), "reduction_calls": 0, "reduction_seconds": 0.0,
        # WHERE THE READ'S SECONDS GO, from its own clocks rather than from a profiler: the
        # DESCENT (every round's reduction and verdict, the part the packed direct scan is the
        # control for), the ANSWER (one gather and one reduction over the supplied positions),
        # the EVIDENCE (the two supply disciplines' byte sums) and the HANDLES (the B.2 identity
        # and witness address of every supplied row, plus every decided range's postings) - which
        # is work the scan does not do at all, because the scan returns an integer.
        "descent_seconds": descent_seconds, "answer_seconds": answer_seconds,
        "evidence_seconds": evidence_seconds, "handles_seconds": handles_seconds,
        "peak_reduction_device_bytes": 0,
        # WHAT THIS READ HAD TO BUILD THAT DID NOT DEPEND ON THE QUESTION. A ranked column is a
        # function of (record, lens) alone and is gathered when the lens is OPENED, so this
        # counter is zero on every question of a run through the front door; it is non-zero only
        # for a caller that supplied no opened column set, and then it says exactly what that
        # cost. The derived anchor-reached column DOES depend on the question, is built once for
        # all of that question's readers, and is counted separately.
        "ranked_columns_built": 0,
        "ranked_columns_gathered_when_the_lens_was_opened": columns.built_at_open,
        "anchor_columns_built": 0,
        "ranges_visited": 0,
        "ranges_final": int(len(range_handles)),
        "positions_touched": int(positions.numel()),
        # WHAT THE DESCENT ACTUALLY REFUSED, as a count of rank positions rather than of
        # ranges: the rows inside a range the CONDITIONS excluded, which the read never reads.
        # ``positions_touched`` alone cannot show pruning, because it also counts every range
        # the TOLERANCE decided where it stood and every row the lens could not seat (which is
        # always opened). These three numbers add up to the whole universe.
        "positions_excluded_by_the_conditions": int(positions_excluded),
        "positions_of_the_whole_universe": int(lens.rows + lens.unbound),
        "positions_opened_at_the_leaves": int(opened_positions.numel()),
        "rows_the_lens_could_not_seat_and_the_read_opened": lens.unbound,
        "rows_admitted": int(admitted_positions.numel()),
        "rows_of_the_lens": lens.rows,
        "fraction_of_the_lens_touched": (float(positions.numel())
                                         / max(lens.rows + lens.unbound, 1)),
        "components_regraded": 0, "faces_stored_on_a_node": 0,
        "handles_name_the_examined_set_because_nothing_was_admitted": bool(examined_set),
        **lens_constants(lens),
    }
    executed.update(answer_detail)
    executed.update(executed_extra)
    return ReadResult(qid=compiled.spec.qid, answer=answer, certificate=certificate,
                      refusal=refusal, tolerance=dict(tolerance), supply=supply,
                      rounds=tuple(rounds), executed=executed, row_handles=row_handles,
                      range_handles=range_handles, evidence=dict(evidence),
                      seconds=time.perf_counter() - started)


def _decode_one(table: Any, code: int, column: str) -> Any:
    """One code back to its declared value, through the column's own vocabulary. O(1)."""
    vocabulary = table.vocabulary(column)
    if vocabulary:
        return vocabulary[int(code)]
    arrow = table.spec.field(column).type
    if arrow == "date":
        return str(date_of_key(int(code)))
    if arrow == "bool":
        return bool(int(code))
    return int(code)


def _apply_operator(compiled: CompiledQuestion, columns: FA.RankedColumns,
                    admitted: torch.Tensor, table: Any) -> tuple[Any, dict[str, Any]]:
    """The five declared operators, each ONE reduction over the admitted positions. O(k log k)."""
    operator = compiled.spec.operator
    ranked_answer, _answer_null, _t = columns.get(compiled.spec.row_kind,
                                                  operator.answer_column)
    values = ranked_answer.index_select(0, admitted)
    detail: dict[str, Any] = {"operator": operator.name, "answer_rows": int(admitted.numel())}
    if operator.name == "exists":
        return bool(admitted.numel()), detail
    if not admitted.numel():
        return None, detail
    if operator.name in ("count_distinct", "distinct_values"):
        distinct = torch.unique(values)
        detail["distinct_codes"] = int(distinct.numel())
        if operator.name == "count_distinct":
            return int(distinct.numel()), detail
        codes = distinct.tolist()
        return sorted(_decode_one(table, code, operator.answer_column)
                      for code in codes), detail  # loop-ok: the answer's own distinct codes
    ranked_order, order_null, _to = columns.get(compiled.spec.row_kind, operator.order_column)
    keys = ranked_order.index_select(0, admitted).to(torch.int64)
    declared = keys != order_null
    if operator.name == "first_by":
        # A null order key is not a small integer: the sentinel is replaced by the declared
        # maximum so a row with no declared key can never win a FIRST by being INT_MIN.
        biggest = torch.iinfo(torch.int64).max
        picked = int(torch.argmin(torch.where(declared, keys, torch.full_like(keys, biggest))))
    else:
        smallest = torch.iinfo(torch.int64).min
        picked = int(torch.argmax(torch.where(declared, keys, torch.full_like(keys, smallest))))
    detail["order_key"] = int(keys[picked])
    detail["order_key_declared"] = bool(declared[picked])
    return _decode_one(table, int(values[picked]), operator.answer_column), detail


# ------------------------------------------------------------------ the handles
def _row_handles(opened: Any, row_kind: str, rows: torch.Tensor, *, limit: int,
                 gathered: Mapping[str, torch.Tensor] | None = None) -> RowHandles:
    """THREE GATHERS: the answer's rows, their minted identities and their witness addresses.

    ``limit`` is the number of rows the question's own byte budget actually paid for, so the
    handle list is bounded by the query's declared budget rather than by a second invented cap.
    Nothing is hashed, decoded or serialised here - the identity column was minted at ingestion
    and the address is a row of the span table. Complexity: O(k), three ``index_select`` calls.
    """
    store = opened.ingestion.store
    table = store.table(row_kind)
    spans = opened.ingestion.spans
    empty = torch.zeros(0, dtype=torch.int64, device=rows.device)
    if not rows.numel() or limit <= 0:
        return RowHandles(row_kind=row_kind, identity=empty.reshape(0, 4),
                          global_ordinal=empty, address=empty.reshape(0, 3),
                          blob_handles=tuple(spans.handles()))
    held = gathered if gathered is not None else row_gather(opened, row_kind, rows)
    locals_ = held["locals"][:limit]
    if not locals_.numel():
        return RowHandles(row_kind=row_kind, identity=empty.reshape(0, 4),
                          global_ordinal=empty, address=empty.reshape(0, 3),
                          blob_handles=tuple(spans.handles()))
    return RowHandles(
        row_kind=row_kind,
        identity=table.identity.index_select(0, locals_),
        global_ordinal=table.global_ordinals.index_select(0, locals_),
        address=held["address"][:limit],
        blob_handles=tuple(spans.handles()))


def _range_handles(lens: FA.LoadedLens, lo: torch.Tensor, hi: torch.Tensor,
                   node: torch.Tensor, condition_digest: str) -> RangeHandles:
    """The decided ranges as CONSTANTS OF THE TREE: one gather of their components. O(F)."""
    return RangeHandles(
        lens_hash=lens.lens_hash, component=lens.node_component.index_select(0, node),
        lo=lo, hi=hi, condition_digest=condition_digest, verdict="decided_in",
        component_address=lens.component_address, rank_global=lens.rank_global)


def resolve_handles(opened: Any, handles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Resolve an answer's handles against a record opened in ANY process: identity -> bytes.

    The pattern ``atlas/tests/test_record_persistence.py:183`` establishes for rows and
    relations, applied to an ANSWER's handles: find the row of that identity in THIS process,
    read the bytes its witness address names, and report whether identity, address and bytes
    agree. Complexity: O(rows of the kind * columns) once per kind, then O(k).
    """
    store = opened.ingestion.store
    blobs = opened.ingestion.blobs
    by_kind: dict[str, dict[str, int]] = {}
    checked = []
    for handle in handles:  # loop-ok: the handle list under test
        kind = str(handle["row_kind"])
        if kind not in by_kind:
            # THE MINTED COLUMN, READ BACK - not re-hashed. ``ids_of_words`` is the hex form of
            # the identity the row has carried since ingestion.
            identities = ids_of_words(store.table(kind).identity)
            by_kind[kind] = {identity: index
                             for index, identity in enumerate(identities)}  # loop-ok: one pass over the kind's identities, built once per kind
        index = by_kind[kind].get(str(handle["row_id"]), -1)
        row: dict[str, Any] = {"row_id": handle["row_id"], "row_kind": kind,
                               "resolved": index >= 0}
        if index >= 0:
            table = store.table(kind)
            span = table.witness_span[index:index + 1]
            address = opened.ingestion.spans.addresses(span)[0]
            row["address_equal"] = (str(address[0]) == str(handle["content_handle"])
                                    and int(address[1]) == int(handle["start"])
                                    and int(address[2]) == int(handle["end"]))
            data = blobs.read(str(address[0]), int(address[1]), int(address[2]))
            row["bytes"] = len(data)
            row["text"] = data.decode("utf-8", "replace")
            row["digest"] = chash({"bytes": row["text"]})
        checked.append(row)
    return {"handles": len(checked),
            "resolved": sum(1 for r in checked if r["resolved"]),  # loop-ok: the handle list under test
            "address_equal": sum(1 for r in checked if r.get("address_equal")),  # loop-ok: the handle list under test
            "rows": checked}


# ------------------------------------------------------------------ evidence within a budget
def row_gather(opened: Any, row_kind: str, rows: torch.Tensor) -> dict[str, torch.Tensor]:
    """ONE gather of a row set: its local ordinals, its witness ADDRESSES and its byte lengths.

    The evidence accounting and the handles both index ``local_of``, ``witness_span`` and the
    span table's columns over the SAME rows, and each was doing its own three gathers. They are
    one pass here, which is the same rule as everywhere else in this packet applied one level
    down: nothing that two callers share is computed twice. O(k), three gathers.
    """
    store = opened.ingestion.store
    table = store.table(row_kind)
    device = table.witness_span.device
    empty = torch.zeros(0, dtype=torch.int64, device=device)
    if not rows.numel():
        return {"locals": empty, "address": empty.reshape(0, 3), "lengths": empty}
    locals_ = store.local_of_global(row_kind).index_select(0, rows)
    locals_ = locals_[locals_ >= 0]
    if not locals_.numel():
        return {"locals": empty, "address": empty.reshape(0, 3), "lengths": empty}
    witness = table.witness_span.index_select(0, locals_)
    address = opened.ingestion.spans.columns.index_select(0, witness)
    return {"locals": locals_, "address": address,
            "lengths": (address[:, 2] - address[:, 1]).to(torch.int64)}


def witness_byte_lengths(opened: Any, row_kind: str, partial_rows: torch.Tensor,
                         whole_rows: torch.Tensor) -> dict[str, torch.Tensor]:
    """The witness byte length of every row of BOTH supply disciplines, in one pass each."""
    partial = row_gather(opened, row_kind, partial_rows)
    whole = row_gather(opened, row_kind, whole_rows)
    return {"partial": partial["lengths"], "whole": whole["lengths"],
            "partial_gather": partial}


def evidence_of_a_supply(lengths: Mapping[str, torch.Tensor], *, budget: int,
                         supply: str) -> dict[str, Any]:
    """One discipline's budget arithmetic over the shared byte lengths. O(k), one cumsum."""
    partial, whole = lengths["partial"], lengths["whole"]
    chosen = partial if supply == "partial" else whole
    fits = 0
    supplied = 0
    partial_bytes = 0
    whole_bytes = 0
    chosen_bytes = 0
    if partial.numel() or whole.numel():
        # EVERY SCALAR THIS BLOCK NEEDS IN ONE TRANSFER. Each ``int(tensor)`` is a device
        # synchronisation; there were five here and two supplies asked for them, which on the
        # engine's ledgers was more than the whole descent cost.
        running = (torch.cumsum(chosen, 0) if chosen.numel()
                   else torch.zeros(1, dtype=torch.int64, device=partial.device))
        seats = (running <= budget).sum()
        last = running.index_select(0, (seats - 1).clamp(min=0))
        counted = torch.stack([partial.sum(), whole.sum(), chosen.sum(), seats,
                               torch.where(seats > 0, last,
                                           torch.zeros_like(last)).reshape(())]).tolist()
        partial_bytes, whole_bytes, chosen_bytes = (int(counted[0]), int(counted[1]),
                                                    int(counted[2]))
        fits = int(counted[3]) if chosen.numel() else 0
        supplied = int(counted[4]) if chosen.numel() else 0
    return {
        "supply": supply, "byte_budget": budget,
        "partial_rows": int(partial.numel()), "partial_bytes": partial_bytes,
        "whole_rows": int(whole.numel()), "whole_bytes": whole_bytes,
        "rows_needed": int(chosen.numel()), "bytes_needed": chosen_bytes,
        "rows_supplied": fits, "bytes_supplied": supplied,
        "partial_over_whole_bytes": (partial_bytes / whole_bytes if whole_bytes else None),
    }


def evidence_within_a_budget(opened: Any, row_kind: str, partial_rows: torch.Tensor,
                             whole_rows: torch.Tensor, *, budget: int,
                             supply: str) -> dict[str, Any]:
    """The bytes the two supply disciplines pay, and what fits the declared budget.

    PARTIAL pays the witness bytes of the rows that satisfy the conditions; WHOLE pays every row
    of a supplied range, which is what supplying a node means when the node has no face to
    filter with. The budget is spent in SUPPLY ORDER, which is the rank order - the only order a
    range handle can be expanded in - so the rows a budget pays for are a prefix of the ranges
    the read decided, not a scored selection.

    Complexity: O(k), two gathers, two sums and one cumsum.
    """
    store = opened.ingestion.store
    table = store.table(row_kind)
    local_of = store.local_of_global(row_kind)
    columns = opened.ingestion.spans.columns

    def byte_lengths(rows: torch.Tensor) -> torch.Tensor:
        if not rows.numel():
            return torch.zeros(0, dtype=torch.int64, device=table.witness_span.device)
        locals_ = local_of.index_select(0, rows)
        locals_ = locals_[locals_ >= 0]
        if not locals_.numel():
            return torch.zeros(0, dtype=torch.int64, device=table.witness_span.device)
        spans = table.witness_span.index_select(0, locals_)
        return (columns[spans, 2] - columns[spans, 1]).to(torch.int64)

    partial = byte_lengths(partial_rows)
    whole = byte_lengths(whole_rows)
    chosen = partial if supply == "partial" else whole
    fits = 0
    supplied = 0
    if chosen.numel():
        running = torch.cumsum(chosen, 0)
        fits = int((running <= budget).sum())
        supplied = int(running[fits - 1]) if fits else 0
    return {
        "supply": supply, "byte_budget": budget,
        "partial_rows": int(partial.numel()), "partial_bytes": int(partial.sum()),
        "whole_rows": int(whole.numel()), "whole_bytes": int(whole.sum()),
        "rows_needed": int(chosen.numel()), "bytes_needed": int(chosen.sum()),
        "rows_supplied": fits, "bytes_supplied": supplied,
        "partial_over_whole_bytes": (float(partial.sum()) / float(whole.sum())
                                     if int(whole.sum()) else None),
    }


# ------------------------------------------------------------------ the admission axes
def admission_axis_rows(opened: Any, lens: FA.LoadedLens, compiled: CompiledQuestion,
                        columns: FA.RankedColumns | None = None
                        ) -> list[tuple[str, str, torch.Tensor]]:
    """Every admission axis as (KEY, name, mask), the key naming the axis across questions.

    The key is what lets a batch of questions share ONE conditional-law quotient: two questions
    that state the same typed condition, or that answer over the same row kind, are the same
    binary axis and are built and contracted once (``joint.JointBank``). It is a property of the
    declared condition, never of the question that happens to carry it.
    """
    columns = _columns_for(opened, lens, columns)
    entries = _entries(compiled, columns)
    rows: list[tuple[str, str, torch.Tensor]] = []
    for entry in entries:  # loop-ok: the question's own declared condition list, one binary axis each
        payload = entry["payload"]
        name = f"{entry['row_kind']}.{entry['column']}:{payload['kind']}"
        # the DERIVED anchor axis is a function of this question's own resolved anchor set, so
        # it is keyed by the question; a DECLARED condition is keyed by what it states, so two
        # questions stating it share one axis and one build.
        key = (f"{entry['row_kind']}.{_REACHED}:{compiled.spec.qid}"
               if entry["column"] == _REACHED
               else f"{name}:{chash({'payload': str(sorted(payload.items(), key=str))})[7:23]}")
        rows.append((key, name, _satisfies(entry, entry["ranked"], entry["null"])))
    row_kind = compiled.spec.row_kind
    answer_column = compiled.spec.operator.answer_column
    ranked_answer, answer_null, _answer_table = columns.get(row_kind, answer_column)
    rows.append((f"kind:{row_kind}", f"row_kind_is_{row_kind}", columns.mine(row_kind)))
    rows.append((f"declared:{row_kind}.{answer_column}", f"{answer_column}_is_declared",
                 ranked_answer != answer_null))
    return rows


def admission_axes(opened: Any, lens: FA.LoadedLens, compiled: CompiledQuestion,
                   columns: FA.RankedColumns | None = None
                   ) -> tuple[list[torch.Tensor], list[str]]:
    """EVERY binary axis a row must satisfy to be admitted to this answer, over the whole lens.

    This is the one place the admission is stated, so that the frontier read, the flat control,
    the packed direct scan and the exact integer contraction are all counting THE SAME SET. The
    J1 residual this packet owns is "every sentence of a receipt is built from the value it
    quotes, computed once"; a control that packed only the condition axes was counting a
    different set by construction, which is exactly that residual recreated one function over.

    The axes are the question's declared conditions, and then the two the operator adds and no
    condition states: the row must be OF THE ANSWERING KIND (a lens seats several row kinds in
    one rank order) and it must DECLARE the answer column (a null answers nothing). Each is a
    bool tensor over ``lens.rank_global_all`` - the lens's own rank order followed by the rows it
    could not seat - so an axis is a whole-array mask, never a per-row test.

    Complexity: O(M * conditions), all vectorised; the ranked columns are the lens's own, opened
    once per (record, lens) and handed in.
    """
    rows = admission_axis_rows(opened, lens, compiled, columns)
    return [axis for _key, _name, axis in rows], [name for _key, name, _axis in rows]  # loop-ok: this question's own axes


# ------------------------------------------------------------------ the controls
def direct_answer(opened: Any, lens: FA.LoadedLens, compiled: CompiledQuestion,
                  columns: FA.RankedColumns | None = None) -> dict[str, Any]:
    """THE FLAT CONTROL, and the independent recount every answer is checked against.

    No tree, no frontier, no reduction: mask every row of the lens with the same conditions and
    apply the same operator. It is the identity audit's own route (a second, independent way to
    the same value) and the honest baseline for the read's executed work - it touches M
    positions where the read touches only the supplied ones.

    Complexity: O(M * conditions), all vectorised.
    """
    started = time.perf_counter()
    device = lens.rank_global.device
    columns = _columns_for(opened, lens, columns)
    entries = _entries(compiled, columns)
    universe = lens.rows + lens.unbound
    positions = torch.arange(universe, dtype=torch.int64, device=device)
    satisfied = torch.ones(universe, dtype=torch.bool, device=device)
    for entry in entries:  # loop-ok: the question's own condition list
        satisfied = satisfied & _satisfies(entry, entry["ranked"], entry["null"])
    ranked_answer, answer_null, answer_table = columns.get(compiled.spec.row_kind,
                                                           compiled.spec.operator.answer_column)
    mine = columns.mine(compiled.spec.row_kind)
    admitted = positions[satisfied & mine & (ranked_answer != answer_null)]
    answer, detail = _apply_operator(compiled, columns, admitted, answer_table)
    return {"answer": answer, "rows_admitted": int(admitted.numel()),
            "positions_touched": universe, "seconds": time.perf_counter() - started,
            "detail": detail}


def packed_direct_control(opened: Any, lens: FA.LoadedLens, compiled: CompiledQuestion,
                          columns: FA.RankedColumns | None = None) -> dict[str, Any]:
    """THE MANDATORY CONTROL, kept VERBATIM: ``contraction_kernels``' packed direct scan.

    The lifted module is used exactly as it stands (``lift.lifted('contraction_kernels')``): one
    32-bit packed code per row, one boolean product query, bounded block partials, never a
    Q-by-N materialisation. Its binary axes are ``admission_axes`` - EVERY axis a row must
    satisfy to be admitted, the question's conditions AND the two the operator adds (the row is
    of the answering kind; the answer column is declared) - so the scan counts the SAME SET the
    frontier read's ``rows_admitted`` counts, over every row of the lens instead of over the
    supplied ones. The equality is therefore an assertion this packet makes and prints, not a
    claim: ``count == rows_admitted`` on every question of the declared draw.

    An earlier form of this function packed only the condition axes and its docstring claimed the
    same equality; on the engine it counted 782 where the read admitted 47, because the read
    additionally masks to the answering kind and drops the answer column's null. The two masks
    are now IN the control, which is the fix - the alternative, withdrawing the claim, would have
    left the mandatory control timing a different question than the read answers.

    Complexity: O(M * queries / block) on the device, one kernel launch plus one reduction.
    """
    device = lens.rank_global.device
    if device.type != "cuda":
        return {"control": "packed_direct_scan", "ran": False,
                "why": "the packed comparator is a CUDA kernel and this lens is on the host"}
    kernels = lifted("contraction_kernels")
    axes, names = admission_axes(opened, lens, compiled, columns)
    if not axes:
        return {"control": "packed_direct_scan", "ran": False,
                "why": "this question has no binary axis to pack"}
    rows = torch.stack(axes, dim=1).to(torch.int32)
    started = time.perf_counter()
    codes = kernels.pack_binary_rows(rows)
    dimension = int(rows.shape[1])
    mask = torch.full((1,), (1 << dimension) - 1, dtype=torch.int32, device=device)
    queries = kernels.prepare_boolean_queries(mask, mask.clone(), dimension=dimension)
    plan = kernels.prepare_direct(codes, queries, max_bytes=1 << 28)
    count = kernels.packed_direct_count(plan)
    torch.cuda.synchronize(device)
    seconds = time.perf_counter() - started
    return {"control": "packed_direct_scan", "ran": True,
            "rows_scanned": int(lens.rank_global_all.numel()),
            "axes": dimension, "axis_names": names, "count": int(count[0].item()),
            "seconds": seconds,
            "retained_bytes": int(plan.retained_bytes),
            "workspace_bytes": int(plan.workspace_bytes),
            "kept_verbatim": ("synthetics papers/corpus-as-a-state/reconstruction/extension/"
                              "contraction_kernels.py, loaded by atlas.front.lift")}


# Front v2 receipt projection only; live read decisions and raw as_dict stay unchanged.





# The inert closed receipt contract; numeric execution remains owned here.
from ..receipt_diagnostics import read_execution_parts, read_result_parts, control_receipt_parts
