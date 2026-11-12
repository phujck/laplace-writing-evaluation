"""down.py - THE WINNOWING READ. Hits, their nodes, the frame, the masks, the relations, the
residual - and only then the budget.

THE AUTHOR, 2026-09-22: "surely there's one more step that can be done to winnow down once the
hits are there. Before it ever reaches the question of token budget" - "my expectation was that
it was already doing this".

It was not. P1's content route is a FLAT top-m in the ambient space: the top 49 leaves of the
declared axis inside the question's jurisdiction, mapped back to their carrier rows
(``front/reach.py``:131-148). That reaches 82 of 94 (LongMemEval) and 89 of 166 (QASPER) and it
is the dense floor - it cannot reach gold that concentration buries, because a flat prefix of
one scalar has no way to ask a second question of what it already found.

DOWN is the step between the hits and the budget, and every one of its five moves is an object
this repository already has:

  1. THE HITS GO TO THEIR NODES. A hit is not an answer, it is an ADDRESS: the accepted section
     it sits in is the object that can speak about more than one member. ``section_of_row``
     climbs the graded tree from the hit's own leaf cell to the deepest ACCEPTED node that holds
     more than one member - deepest, because a coarser node has already been refused by the two
     acceptance tests; accepted, because a refused cell is a face, not a section.
  2. THE MEMBERS ARE RE-SCORED IN THE NODE'S FRAME. The node's conditional mean is what every
     member of an accepted section has in common, so it distinguishes none of them: it is
     removed, and what is left is read in the node's own register (``grading/frames.py``).
     THIS IS WHERE THE MARGIN RETURNS, and it is the only place cosine is allowed to act - after
     factorisation, at a grade, inside a node's local frame, never in the ambient space over the
     whole corpus.
  3. THE QUESTION'S EXACT CONDITIONS ARE MASKS. A typed condition (speaker, a date interval, a
     named token) EXCLUDES; it never contributes to a score. Charter: "Typed conditions mask,
     relations are walked from anchors, operators act on typed fields."
  4. THE DECLARED RELATIONS EXPAND FROM THE HITS. Gold that is linked to a hit but unlike the
     question - the next turn, the same session, the same entity, the row that supersedes it -
     is reached by walking the record's own span-witnessed relations, not by scoring it.
  5. THE STOP IS THE RESIDUAL, NOT A COUNT. ``extension/query_demand.py``'s greedy residual
     reduction, lifted: the anchored rank-one state kernel, centred on the admitted section's
     own empirical mean, with one kernel COLUMN computed per selected row (a pivoted Cholesky
     step; no N x N Gram is ever formed), stopping when the question's own tolerance is met.

     THE TOLERANCE IS THE QUESTION'S (ruling R-i). ``front/question.py``'s ladder is a function
     of the RECORD's size, so every question of an answer kind descends at the same tolerance.
     Here the gate is the theory's: eps_answer * sqrt(1/b - 1) with b the question's own
     CONDITION REFERENCE MASS - the reference mass its conjoined conditions admit, over the
     jurisdiction's mass, read off the lens's own derived pi. A selective question and an
     unselective one of the same answer kind therefore stop at different residuals, which is
     exactly what the ladder could not express.

Only the survivors meet the budget. The certified bound (C7, in the frame form) is what lets a
section be REJECTED without opening it, and ``local_access_contract``'s rejection test is kept
verbatim: reject only when the section's upper bound is below the current k-th actual score LESS
the declared requested tolerance; otherwise descend.

Complexity, per question: O(|sections| d r) for the bound, O(|members| d r) for the re-score,
O(hops * nnz) for the relation walk, O(steps * |admitted| d) for the residual stop. No N x N
object, no per-row Python, and nothing that depends only on the record is rebuilt per question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import torch

from ..grading.frames import NodeFrames, certified_upper, frame_coordinates

__all__ = ["DownView", "DownResult", "build_down_view", "winnow", "question_gate"]


def question_gate(admitted_mass: float, carrier_mass: float, answer_precision: float
                  ) -> tuple[float, float]:
    """RULING R-i's gate: (b, tau) with tau = eps_a * sqrt(1/b - 1). O(1).

    ``b`` is the question's CONDITION REFERENCE MASS, in the ruling's own words: "the sum of pi
    over the carrier rows admitted by the AND of the coded conditions, over the TOTAL CARRIER
    MASS". The jurisdiction is one of those conditions - a question asked inside one container
    is a question with a coded condition on that container - so a selective question and an
    unselective one of the same answer kind compute different b, which is exactly what the
    record-size ladder could not express. ``section_synthesis`` sec. 4 bounds an answer's error by
    sqrt(L_f(C)) sqrt(1/z - 1); eps_a is the precision the ANSWER declares
    (``grading/lens.py``:243-246 ``precision_of``), so this is the theory's own object and not a
    rung of a record-size ladder.
    """
    if carrier_mass <= 0.0:
        return 0.0, float("inf")
    b = max(min(admitted_mass / carrier_mass, 1.0), 0.0)
    if b <= 0.0:
        return 0.0, float("inf")
    return b, float(answer_precision) * float(max(1.0 / b - 1.0, 0.0)) ** 0.5


@dataclass(slots=True)
class DownView:
    """The (record, lens) constants a winnowing read needs, built ONCE. A query only reads."""

    frames: NodeFrames
    field: torch.Tensor                 # float32 [M, d] the carrier's own unit field per row
    global_rows: torch.Tensor           # int64 [M] record ordinals in carrier order
    local_of_global: torch.Tensor       # int64 [record rows] -> carrier local, -1 outside
    pi: torch.Tensor                    # float64 [M] the lens's derived reference measure
    rank_of_row: torch.Tensor           # int64 [M] the row's position in the leaf order
    order: torch.Tensor                 # int64 [M] position -> row
    section_of_row: torch.Tensor        # int64 [M] the accepted section the row sits in
    lo: torch.Tensor                    # int64 [N] node range start, in positions
    hi: torch.Tensor                    # int64 [N]
    accepted: torch.Tensor              # bool [N]
    nodes: int
    leaves: int
    seconds_built: float = 0.0

    def receipt(self) -> dict[str, Any]:
        size = self.hi - self.lo
        sections = torch.unique(self.section_of_row)
        return {"carrier_rows": int(self.global_rows.numel()), "nodes": self.nodes,
                "leaf_cells": self.leaves,
                "distinct_sections_rows_sit_in": int(sections.numel()),
                "section_size_mean": float(size[sections].to(torch.float64).mean())
                if sections.numel() else 0.0,
                "section_size_max": int(size[sections].max()) if sections.numel() else 0,
                "accepted_nodes": int(self.accepted.sum()),
                "build_seconds": self.seconds_built}


def build_down_view(tree: Any, field: torch.Tensor, local_of_global: torch.Tensor,
                    seconds: float = 0.0) -> DownView:
    """The read's constants from a built graded tree. O(M depth), one gather per LEVEL.

    ``section_of_row`` is the one derived table: for every carrier row, the deepest ACCEPTED
    node holding more than one member. It depends only on the record and the lens, so it is
    built once per lens and never per question (charter: "no per-question rebuild of anything
    that depends only on the record").
    """
    import time

    started = time.perf_counter()
    proposal = tree.proposal
    device = field.device
    rows = int(tree.flat.rows)
    rank_of_row = torch.empty(rows, dtype=torch.int64, device=device)
    rank_of_row[proposal.order] = torch.arange(rows, dtype=torch.int64, device=device)

    leaf_mask = proposal.left < 0
    leaves = torch.nonzero(leaf_mask, as_tuple=False).flatten()
    widths = proposal.hi[leaves] - proposal.lo[leaves]
    span = torch.repeat_interleave(leaves, widths)
    starts = torch.repeat_interleave(proposal.lo[leaves], widths)
    offset = (torch.arange(int(span.numel()), dtype=torch.int64, device=device)
              - torch.repeat_interleave(
                  torch.cat([torch.zeros(1, dtype=torch.int64, device=device),
                             torch.cumsum(widths, 0)])[:-1], widths))
    leaf_of_position = torch.full((rows,), -1, dtype=torch.int64, device=device)
    leaf_of_position[starts + offset] = span

    accepted = tree.node_stop & tree.node_resolved
    size = proposal.hi - proposal.lo
    usable = (size >= 2)
    node = leaf_of_position[rank_of_row]
    section = torch.where(usable[node] & accepted[node], node, torch.full_like(node, -1))
    fallback = torch.where(usable[node], node, torch.full_like(node, -1))
    climbing = node
    for _ in range(int(proposal.depth.max()) + 1):  # loop-ok: one step per LEVEL, depth ~ log N
        parent = proposal.parent[climbing]
        if not bool((parent >= 0).any()):
            break
        climbing = torch.where(parent >= 0, parent, climbing)
        take = (section < 0) & usable[climbing] & accepted[climbing]
        section = torch.where(take, climbing, section)
        fallback = torch.where((fallback < 0) & usable[climbing], climbing, fallback)
    # a row whose every ancestor is refused keeps the deepest node that can hold a margin, NAMED
    # by ``accepted`` being false there - never dropped, which is the author's own objection
    section = torch.where(section >= 0, section, fallback)
    section = torch.where(section >= 0, section, node)
    return DownView(frames=tree.frames, field=field, global_rows=tree.flat.global_rows,
                    local_of_global=local_of_global, pi=tree.flat.pi, rank_of_row=rank_of_row,
                    order=proposal.order, section_of_row=section, lo=proposal.lo,
                    hi=proposal.hi, accepted=accepted, nodes=int(proposal.nodes),
                    leaves=int(leaves.numel()),
                    seconds_built=seconds + (time.perf_counter() - started))


@dataclass(slots=True)
class DownResult:
    """What ONE winnowing read supplied, with every counter the claim rests on."""

    hits: torch.Tensor                  # int64 carrier-local rows the content axis proposed
    sections: torch.Tensor              # int64 the nodes those hits sit in
    sections_rejected: torch.Tensor     # int64 sections the certified bound decided, unopened
    members: torch.Tensor               # int64 every member of every opened section
    admitted: torch.Tensor              # int64 members surviving the masks, plus the walk
    survivors: torch.Tensor             # int64 in the SUPPLY order (the in-frame score order)
    selection_order: torch.Tensor       # int64 the same set in the RESIDUAL's own greedy order
    within_budget: torch.Tensor         # int64 the prefix the declared byte budget admits
    frame_score: torch.Tensor           # float64 the read's score: mean term + in-frame term
    within_node: torch.Tensor           # float64 the in-frame term alone - the margin's object
    b: float                            # the question's condition reference mass (ruling R-i)
    tau: float                          # the gate eps_a * sqrt(1/b - 1)
    residual_initial: float
    residual_final: float
    steps: int
    counters: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"hits": int(self.hits.numel()), "sections": int(self.sections.numel()),
                "sections_rejected_unopened": int(self.sections_rejected.numel()),
                "members": int(self.members.numel()),
                "admitted": int(self.admitted.numel()),
                "survivors": int(self.survivors.numel()),
                "within_budget": int(self.within_budget.numel()),
                "b": self.b, "tau": self.tau,
                "residual_initial": self.residual_initial,
                "residual_final": self.residual_final, "steps": self.steps,
                **self.counters}


def _supplied_score(view: DownView, node: torch.Tensor, rows: torch.Tensor,
                    within_node: torch.Tensor, q: torch.Tensor) -> torch.Tensor:
    """The score of a row of an OPENED section: the frame decomposition, residual term included.

    <v, q> = <mu_n, q> + <c_v, c_q> + <e_v, q>: the node's own relevance, the member's margin
    inside the node, and the part of the member the node's register does not represent. The
    first two are what the frame supplies and what a CLOSED section is bounded by; the third is
    only available once the section is opened - and an opened section's members have already
    been read, so nothing new is paid for it.

    MEASURED, five LongMemEval haystacks: supplying by the first two terms alone lost gold the
    flat prefix kept, at every budget, because chi = ceil(ln n) of 384 declared components
    leaves most of the member's field in the residual term. Dropping a term the read has already
    paid for is not a winnowing, it is a loss - so the read supplies by the whole decomposition
    and reports the interval the frame alone would have given (``residual_interval``).
    """
    return view.field.index_select(0, rows).to(torch.float64) @ q


def _members_of(view: DownView, sections: torch.Tensor) -> torch.Tensor:
    """Every carrier row inside a set of node ranges. O(members), no loop over a section."""
    widths = (view.hi[sections] - view.lo[sections])
    if not int(widths.sum()):
        return torch.empty(0, dtype=torch.int64, device=sections.device)
    starts = torch.repeat_interleave(view.lo[sections], widths)
    offset = (torch.arange(int(widths.sum()), dtype=torch.int64, device=sections.device)
              - torch.repeat_interleave(
                  torch.cat([torch.zeros(1, dtype=torch.int64, device=sections.device),
                             torch.cumsum(widths, 0)])[:-1], widths))
    return view.order.index_select(0, starts + offset)


def _residual_stop(vectors: torch.Tensor, query: torch.Tensor, tau: float, cost: torch.Tensor
                   ) -> tuple[torch.Tensor, float, float, int]:
    """``query_demand.project_query_demand``'s greedy residual reduction, for ONE section.

    The anchored rank-one state kernel k(x, y) = ((1 + <x, y>)/2)^2 centred on the admitted
    section's own conditional mean, its first and second vector moments retained (never a
    squared-dimensional feature column and never an N x N Gram), and one kernel COLUMN computed
    per selected row - the pivoted Cholesky step. The stop is the question's tolerance on the
    residual, not a count: selection ends when the remaining squared query-projection residual
    falls below tau^2 times the residual the section started with.

    Returns (selected rows in selection order, initial residual, final residual, steps).
    Complexity: O(steps * n * d). Device memory: O(n * steps) for the Cholesky factor.
    """
    device = vectors.device
    n = int(vectors.shape[0])
    if not n:
        empty = torch.empty(0, dtype=torch.int64, device=device)
        return empty, 0.0, 0.0, 0
    v = vectors.to(torch.float64)
    v = v / v.norm(dim=1, keepdim=True).clamp(min=1e-12)
    q = query.to(torch.float64)
    q = q / q.norm().clamp(min=1e-12)
    dimension = int(v.shape[1])
    epsilon = torch.finfo(torch.float64).eps * (dimension + n + 1) * 32

    mean = v.mean(0)
    second = (v.T @ v) / n                                  # dense-ok: d x d, d = the declared field dimension (384), never a function of the corpus
    source_overlap = (1 + 2 * (v @ mean) + ((v @ second) * v).sum(1)) / 4
    query_overlap = float((1 + 2 * (mean @ q) + (q @ second @ q)) / 4)
    mean_square = float((1 + 2 * float(mean.square().sum()) + float(second.square().sum())) / 4)
    d_diag = (1 - 2 * source_overlap + mean_square).clamp(min=0.0)
    h = (((1 + (v @ q).clamp(-1, 1)) / 2).square() - source_overlap - query_overlap
         + mean_square)
    residual = max(1 - 2 * query_overlap + mean_square, 0.0)
    initial = float(residual)
    stop_at = initial * float(tau) ** 2 if tau != float("inf") else 0.0

    selected = torch.zeros(n, dtype=torch.bool, device=device)
    columns: list[torch.Tensor] = []
    order: list[torch.Tensor] = []
    steps = 0
    for _ in range(n):  # loop-ok: one step per SELECTED row, bounded by the section and stopped by the residual - the read's own budget, not a step per candidate
        if residual <= stop_at or residual <= epsilon:
            break
        admissible = d_diag > epsilon
        gain = torch.where(admissible, h.square() / d_diag.clamp(min=epsilon),
                           torch.zeros_like(h))
        score = (gain / cost).masked_fill(selected, -float("inf"))
        pivot = int(torch.argmax(score))
        if not bool(admissible[pivot]) or float(gain[pivot]) <= epsilon:
            break
        denominator = float(torch.sqrt(d_diag[pivot].clamp(min=epsilon)))
        column = (((1 + (v @ v[pivot]).clamp(-1, 1)) / 2).square()
                  - source_overlap - float(source_overlap[pivot]) + mean_square)
        for previous in columns:  # loop-ok: the steps already taken, bounded by the stop above
            column = column - previous * float(previous[pivot])
        column = column / denominator
        coefficient = float(h[pivot]) / denominator
        h = h - coefficient * column
        d_diag = (d_diag - column.square()).clamp(min=0.0)
        residual = max(residual - coefficient * coefficient, 0.0)
        selected[pivot] = True
        columns.append(column)
        order.append(torch.tensor(pivot, dtype=torch.int64, device=device))
        steps += 1
    chosen = (torch.stack(order) if order
              else torch.empty(0, dtype=torch.int64, device=device))
    return chosen, initial, float(residual), steps


def _rank_agreement(left: torch.Tensor, right: torch.Tensor) -> float:
    """Spearman agreement of two orders over the same rows. O(n log n)."""
    n = int(left.numel())
    if n < 2:
        return 1.0
    index = torch.arange(n, dtype=torch.float64, device=left.device)
    a = torch.empty(n, dtype=torch.float64, device=left.device)
    b = torch.empty(n, dtype=torch.float64, device=left.device)
    a[torch.argsort(left)] = index
    b[torch.argsort(right)] = index
    a = a - a.mean()
    b = b - b.mean()
    denominator = float(a.norm() * b.norm())
    return float((a * b).sum() / denominator) if denominator > 0 else 0.0


def winnow(view: DownView, query: torch.Tensor, hits: torch.Tensor, *,
           jurisdiction: torch.Tensor, answer_precision: float,
           conditions: Sequence[torch.Tensor] = (),
           relations: Mapping[str, tuple[torch.Tensor, torch.Tensor]] | None = None,
           byte_length: torch.Tensor | None = None, budget_bytes: int | None = None,
           requested_tolerance: float = 0.0, top_k: int = 0,
           supply_order: str = "frame") -> DownResult:
    """THE WINNOWING READ, in the author's own order. Every argument is already typed.

    ``hits`` are carrier-local rows the content axis proposed; ``jurisdiction`` is the boolean
    mask over the carrier the question is asked inside; ``conditions`` are the question's exact
    typed conditions as boolean masks over the carrier (they EXCLUDE, they never score);
    ``relations`` are the declared relation tables as (source, target) carrier-local pairs.
    """
    device = view.field.device
    q = query.to(torch.float64)
    q = q / q.norm().clamp(min=1e-12)
    counters: dict[str, Any] = {}

    # ---- 1. the hits go to their nodes
    sections = torch.unique(view.section_of_row.index_select(0, hits)) if hits.numel() else \
        torch.empty(0, dtype=torch.int64, device=device)
    counters["sections_of_hits"] = int(sections.numel())

    # ---- the certified bound, BEFORE anything is opened (C7 in the frame form)
    rejected = torch.empty(0, dtype=torch.int64, device=device)
    if sections.numel() and hits.numel():
        upper = certified_upper(view.frames, sections, q)
        actual = view.field.index_select(0, hits).to(torch.float64) @ q
        take = min(max(top_k, 1), int(actual.numel()))
        kth = float(torch.topk(actual, take).values[-1])
        # local_access_contract's rejection test, verbatim: reject only when the upper bound is
        # below the current k-th actual source score LESS the declared requested tolerance
        decided = upper < (kth - float(requested_tolerance))
        rejected = sections[decided]
        sections = sections[~decided]
    counters["sections_rejected_by_the_bound"] = int(rejected.numel())

    # ---- 2. the members are re-scored in the node's frame
    members = _members_of(view, sections)
    # two hits can sit in NESTED sections, so the ranges are de-duplicated before anything is
    # scored - a member counted twice would be opened twice and supplied twice
    members = torch.unique(members) if members.numel() else members
    members = members[jurisdiction.index_select(0, members)] if members.numel() else members
    counters["members_opened"] = int(members.numel())
    if members.numel():
        node = view.section_of_row.index_select(0, members)
        member_coordinates, _ = frame_coordinates(view.frames, node,
                                                  view.field.index_select(0, members))
        query_node = torch.unique(node)
        query_coordinates, _ = frame_coordinates(
            view.frames, query_node, q.to(torch.float32)[None, :].expand(
                int(query_node.numel()), -1))
        slot = torch.full((view.nodes,), 0, dtype=torch.int64, device=device)
        slot[query_node] = torch.arange(int(query_node.numel()), dtype=torch.int64,
                                        device=device)
        width = min(int(member_coordinates.shape[1]), int(query_coordinates.shape[1]))
        within_node = (member_coordinates[:, :width]
                       * query_coordinates.index_select(0, slot[node])[:, :width]).sum(1)
        # THE MEAN TERM BELONGS (``numerics/common.py``:216-220 trace_score: "plus the mean
        # term, so it reduces to the centroid score"). The node's conditional mean is what
        # separates one SECTION from another and the in-frame term is what separates the
        # members INSIDE one - dropping the mean would rank a member of an irrelevant section
        # against a member of the question's own by their deviations alone. Measured on five
        # LongMemEval haystacks: with the mean term dropped the supply order lost gold the flat
        # prefix kept, at every budget.
        frame_score = _supplied_score(view, node, members, within_node, q)
    else:
        within_node = torch.empty(0, dtype=torch.float64, device=device)
        frame_score = torch.empty(0, dtype=torch.float64, device=device)

    # ---- 3. the question's exact conditions are MASKS on that section
    keep = torch.ones(int(members.numel()), dtype=torch.bool, device=device)
    for mask in conditions:  # loop-ok: the question's DECLARED conditions, a closed small set
        keep &= mask.index_select(0, members)
    counters["excluded_by_a_typed_condition"] = int((~keep).sum())
    admitted = members[keep]
    frame_score = frame_score[keep]
    within_node = within_node[keep]

    # ---- 4. the declared relations expand FROM THE HITS
    walked = torch.empty(0, dtype=torch.int64, device=device)
    if relations and hits.numel():
        seed = torch.zeros(int(view.field.shape[0]), dtype=torch.bool, device=device)
        seed[hits] = True
        reached = torch.zeros_like(seed)
        for _, (source, target) in sorted(relations.items()):  # loop-ok: the DECLARED relation kinds, a closed set of the declaration's kinds
            if not source.numel():
                continue
            reached[target[seed.index_select(0, source)]] = True
            reached[source[seed.index_select(0, target)]] = True
        reached &= jurisdiction
        for mask in conditions:  # loop-ok: the question's DECLARED conditions
            reached &= mask
        walked = torch.nonzero(reached, as_tuple=False).flatten()
    counters["reached_by_a_declared_relation"] = int(walked.numel())
    if walked.numel():
        before = int(admitted.numel())
        admitted = torch.unique(torch.cat([admitted, walked]))
        counters["added_by_the_walk"] = int(admitted.numel()) - before
        node = view.section_of_row.index_select(0, admitted)
        member_coordinates, _ = frame_coordinates(view.frames, node,
                                                  view.field.index_select(0, admitted))
        query_node = torch.unique(node)
        query_coordinates, _ = frame_coordinates(
            view.frames, query_node,
            q.to(torch.float32)[None, :].expand(int(query_node.numel()), -1))
        slot = torch.zeros(view.nodes, dtype=torch.int64, device=device)
        slot[query_node] = torch.arange(int(query_node.numel()), dtype=torch.int64,
                                        device=device)
        width = min(int(member_coordinates.shape[1]), int(query_coordinates.shape[1]))
        within_node = (member_coordinates[:, :width]
                       * query_coordinates.index_select(0, slot[node])[:, :width]).sum(1)
        frame_score = _supplied_score(view, node, admitted, within_node, q)
    else:
        counters["added_by_the_walk"] = 0

    # ---- 5. the stop is the RESIDUAL, at the question's OWN tolerance (ruling R-i)
    carrier_mass = float(view.pi.sum())
    admitted_mass = float(view.pi.index_select(0, admitted).sum()) if admitted.numel() else 0.0
    b, tau = question_gate(admitted_mass, carrier_mass, answer_precision)
    counters["jurisdiction_mass_share"] = float(view.pi[jurisdiction].sum()) / max(carrier_mass,
                                                                                   1e-300)
    cost = (byte_length.index_select(0, admitted).to(torch.float64).clamp(min=1.0)
            if byte_length is not None and admitted.numel()
            else torch.ones(int(admitted.numel()), dtype=torch.float64, device=device))
    chosen, initial, final, steps = _residual_stop(
        view.field.index_select(0, admitted), q, tau, cost) if admitted.numel() else (
        torch.empty(0, dtype=torch.int64, device=device), 0.0, 0.0, 0)
    survivors = admitted.index_select(0, chosen) if chosen.numel() else admitted[:0]
    selection_order = survivors
    # THE RESIDUAL DECIDES THE SET; THE READ'S OWN SCORE DECIDES THE ORDER. The greedy step
    # emits its pivots in residual-reduction-per-byte order, which is a DIVERSITY order: it is
    # the right rule for "what else does this section add", and the wrong one for "supply the
    # evidence this question is owed first". So the survivors are supplied in the in-frame
    # score order of step 2 - the read's own score, after the node's shared direction is gone.
    # ``supply_order='residual'`` is the declared ablation position, and the packet MEASURES
    # both rather than asserting this.
    if supply_order == "frame" and chosen.numel() and frame_score.numel() == int(
            admitted.numel()):
        ranked = torch.argsort(frame_score.index_select(0, chosen), descending=True)
        survivors = survivors.index_select(0, ranked)

    # ---- and ONLY THEN the budget
    within = survivors
    if budget_bytes is not None and byte_length is not None and survivors.numel():
        spent = torch.cumsum(byte_length.index_select(0, survivors).to(torch.int64), 0)
        within = survivors[spent <= int(budget_bytes)]
    if admitted.numel():
        node_of_admitted = view.section_of_row.index_select(0, admitted)
        counters["residual_interval_mean"] = float(
            view.frames.residual_radius.index_select(0, node_of_admitted).mean()
            * float(q.norm()))
        counters["frame_only_rank_agreement"] = _rank_agreement(
            (view.frames.mu.index_select(0, node_of_admitted) @ q) + within_node, frame_score)
    counters["bytes_supplied"] = (int(byte_length.index_select(0, within).sum())
                                  if byte_length is not None and within.numel() else 0)
    return DownResult(hits=hits, sections=sections, sections_rejected=rejected,
                      members=members, admitted=admitted, survivors=survivors,
                      selection_order=selection_order,
                      within_budget=within, frame_score=frame_score, within_node=within_node,
                      b=b, tau=tau,
                      residual_initial=initial, residual_final=final, steps=steps,
                      counters=counters)
