"""joint_section.py - THE ANSWER IS A JOINT SECTION, read through the front door.

Steps B and C of packet P3-THE-READ, in the door's own path and nowhere else. The claim this
module exists to execute is the campaign's, verbatim: "the answer to a question is a JOINT
SECTION - the intersection over the lenses the question activates of the sections each selects -
not a ranked list". Five moves, in this order, and none of them a re-ordering of one cosine:

  (i)   THE CONTENT LENS DESCENDS FROM ITS ROOTS by the CERTIFIED FRAME BOUND (C7, the frame
        form, ``grading/frames.py:343 certified_upper``), evaluated for ALL open questions x the
        whole frontier in ONE launch per round. A range is EXCLUDED only when its upper bound is
        below the question's current k-th actual score LESS its own tau - the local access
        contract's rejection test verbatim - and every other open range is descended. That is
        the only rule in this module that can reject a section unopened.
  (ii)  THE TYPED CONDITIONS ARE MASKS over the frontier: the compiled question's own coded
        conditions, read through the lens's ranked columns, never a second vocabulary.
  (iii) THE RELATION LENSES' SECTIONS HOLDING THOSE ROWS ARE READ AS MEMBERSHIPS and intersected
        through the COUPLING over memberships (step B, ``MembershipCoupling`` below): one
        categorical axis per lens per grade, parents acting as masks over descendant labels, and
        the intersection answered off the coupling's own tuple table without scoring a vector or
        multiplying marginals.
  (iv)  THE RESIDUAL DECIDES HOW MUCH OF THE JOINT SECTION THE QUESTION NEEDS: the anchored
        rank-one greedy residual reduction of ``extension/query_demand.py``, run for the WHOLE
        question batch with ONE device update per step (each question picks its own pivot inside
        its own segment), stopping on each question's own tau.
  (v)   THE BYTE BUDGET LAST, over the joint section's rows in residual order, and then the
        READER-CONTEXT stage (C3b): the original spans with their identifiers and the previous
        turn of every reply, packed under the reader's declared TOKEN budget. Bytes are the
        store's currency up to that boundary; tokens are the reader's. The two are never summed.

WHAT IS LIFTED AND NOT RE-AUTHORED: ``frames.certified_upper`` (the C7 expression - the batched
form here is the same expression with a query MATRIX, and it is checked against the lifted
function on a bounded sample every run, reported as ``certified_upper_batched_equals_lifted``);
``read.evidence_within_a_budget`` for the byte discipline and ``read._row_handles`` for the
handles; ``read._entries`` / ``read._face_for`` for the typed masks; the extension's
``context_budget`` for the reader's token budget; ``gpu_state`` and ``section_coupling`` for the
coupling. ``front/down.py``'s five moves live here and that file is DELETED into this module.

Complexity, Q questions, F frontier width, R rounds, N section rows, d the field dimension:
descent O(R * Q * F * d) device work in R launches; the coupling O(N log N + axes * distinct
label rows) ONCE for the whole question list; the residual stop O(steps * N * d) with one device
update per step for all questions at once. No N x N object, no per-question Python loop inside a
round, no model call anywhere.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field as _field
from typing import Any, Mapping, Sequence

import numpy as np
import torch

from ..grading.frames import NodeFrames, certified_upper
from ..record.content import axis_matrix
from . import read as RD
from .lift import lifted

__all__ = ["ContentDirections", "MembershipCoupling", "JointSectionRead",
           "build_membership_coupling", "joint_section_questions", "K_DERIVATION"]


# WHY THE REJECTION TEST READS THE **BEST** ACTUAL SCORE, and not a k chosen by hand. The local
# access contract rejects a range when its certified upper bound is below "the current k-th
# actual score less the declared tolerance". k is not free here: the declared observable of this
# lens is the FIELD, and its questions' own precision derivation (grading/lenses.py
# EPS_DERIVATION) says in as many words that "the answer to a declared question is a value read
# off one row". The k-th best with k = 1 is therefore the derived form of the test for this lens:
# a range none of whose members can come within tau of the best row the read has actually scored
# cannot carry the answer at the precision the lens declares it owes. The WIDTH of the surviving
# section is then set by tau - the question's own eps_answer sqrt(1/b - 1) at its condition
# reference mass - and not by a count, which is the whole point of the residual stop in (iv).
K_DERIVATION = (
    "k = 1 in the rejection test, DERIVED and not chosen: this lens's declared observable is the "
    "field and its question's precision derivation (lenses.EPS_DERIVATION) is 'the answer to a "
    "declared question is a value read off one row'. The k-th actual score at k = 1 is the best "
    "actual score, and the section's width is set by tau = eps_answer * sqrt(1/b - 1) at the "
    "question's own condition reference mass (ruling R-i), never by a count.")


# ===================================================================== the question's direction
class ContentDirections:
    """ONE batched encode of the whole question list, through the record's DECLARED encoder.

    D.1: the encoder is the measurement interface, and the question is measured by exactly the
    interface the spans were measured by - no model call, no proposal step, no English
    vocabulary. This is ``front/reach.py``'s ``_ContentLens.queries`` on the door's own path;
    ``reach.py`` is deleted into it.

    Complexity: O(total query tokens) once per dataset run.
    """

    __slots__ = ("axis", "vectors", "carrier_local", "encoder", "device", "seconds", "calls")

    def __init__(self, ingestion: Any, carrier_kind: str, device: torch.device) -> None:
        from ..encoders.span_encoder import span_encoder

        declaration = ingestion.declaration
        self.axis = declaration.content_axes[0]
        table = ingestion.content
        rows = axis_matrix(table, self.axis)
        kinds = [spec.kind for spec in declaration.row_kinds]  # loop-ok: the declared row kinds
        keep = np.flatnonzero(table.carrier_kind == kinds.index(carrier_kind))
        local_of = ingestion.store.local_of_global(carrier_kind)
        self.device = device
        vectors = torch.from_numpy(np.ascontiguousarray(rows[keep])).to(device)
        self.vectors = vectors / vectors.norm(dim=1, keepdim=True).clamp(min=1e-12)
        carrier = torch.from_numpy(np.ascontiguousarray(table.carrier_row[keep])).to(device)
        self.carrier_local = local_of.index_select(0, carrier)
        self.encoder = span_encoder(self.axis.encoder_id)
        self.seconds = 0.0
        self.calls = 0

    def directions(self, texts: Sequence[str]) -> torch.Tensor:
        """The unit direction of every question, in ONE encode call. [Q, d] float64."""
        started = time.perf_counter()
        matrix = self.encoder.embed(list(texts), role="query")
        self.seconds += time.perf_counter() - started
        self.calls += 1
        out = torch.from_numpy(np.ascontiguousarray(matrix)).to(self.device).to(torch.float64)
        return out / out.norm(dim=1, keepdim=True).clamp(min=1e-12)


# ======================================================== STEP B: the coupling over memberships
@dataclass(frozen=True, slots=True)
class MembershipAxis:
    """ONE membership axis: the node a carrier row belongs to, at one grade of one lens."""

    lens_id: str
    grade: int
    cardinality: int
    label_of_row: torch.Tensor          # int64 [M] in the CONTENT lens's rank order
    why: str


@dataclass(slots=True)
class MembershipCoupling:
    """The coupling of step B: lens MEMBERSHIPS as the axes, over the content lens's rows.

    section_execution_spec.md:116-139 states the object: rows (section_f1(source), ...,
    section_fd(source), metadata) with source multiplicity as weight, parents acting as masks
    over descendant labels, and a batched contraction answering intersection mass without scoring
    a vector or multiplying marginals. The axes here are exactly that - one per (lens, grade) -
    and the admission-axis bank of ``joint.py`` stays as one query bank among several.

    THE JOINT IS GRADED: an axis is taken at each grade of its lens, so a width that is too large
    at a fine grade is answered by taking the axis COARSER, never by refusing the question (the
    author: "if the membership is too wide, it needs to be graded. OBVIOUSLY"). The quotient's own
    state count at each cut IS the continuation width / Schmidt rank across that cut, and it is
    reported per grade - the first such number on the real concept space in this campaign.
    """

    axes: list[MembershipAxis] = _field(default_factory=list)
    width_by_cut: list[dict[str, Any]] = _field(default_factory=list)
    executed: dict[str, Any] = _field(default_factory=dict)
    coupling: Any = None
    module: Any = None
    cardinalities: tuple[int, ...] = ()
    labels: torch.Tensor | None = None
    tuple_key: torch.Tensor | None = None

    def section_of(self, rows: torch.Tensor) -> dict[str, Any]:
        """The memberships the given rows activate, per axis: how many and how concentrated."""
        if self.labels is None or not rows.numel():
            return {"axes": [], "rows": int(rows.numel())}
        out = []
        for index, axis in enumerate(self.axes):  # loop-ok: the DECLARED membership axes (one per lens per grade)
            labels = self.labels.index_select(0, rows)[:, index]
            unique, counts = torch.unique(labels, return_counts=True)
            out.append({"lens_id": axis.lens_id, "grade": axis.grade,
                        "sections_activated": int(unique.numel()),
                        "largest_section_share_of_the_rows": float(
                            counts.max().double() / max(int(rows.numel()), 1))})
        return {"axes": out, "rows": int(rows.numel())}

    def intersect(self, rows: torch.Tensor) -> dict[str, Any]:
        """The joint section: every row whose membership TUPLE the given rows also occupy.

        The tuple is the coupling's own label tuple; the lookup is one ``isin`` over the packed
        tuple key, which is the coupling's tuple table read forwards instead of backwards. No
        marginal is multiplied and no vector is scored.
        """
        if self.tuple_key is None or not rows.numel():
            return {"joint_rows": rows, "tuples": 0, "rows_the_memberships_add": 0,
                    "why": ("no membership axis was built for this lens"
                            if self.labels is None else
                            "the content descent decided no row for this question, so there is "
                            "no membership tuple to intersect on")}
        wanted = torch.unique(self.tuple_key.index_select(0, rows))
        joint = torch.nonzero(torch.isin(self.tuple_key, wanted), as_tuple=False).flatten()
        return {"joint_rows": joint, "tuples": int(wanted.numel()),
                "rows_the_memberships_add": int(joint.numel()) - int(rows.numel())}


def _labels_at_grade(lens: Any, grade: int, rows: int, device: torch.device
                     ) -> tuple[torch.Tensor, int]:
    """Which node of ``lens`` at depth ``grade`` holds each rank position. O(N + M) per grade.

    A position under no node of that depth lies under a SHALLOWER node that is already a leaf; it
    takes one further declared category rather than a hole, which is the parent acting as a mask
    over its descendant labels exactly as the spec puts it.
    """
    label = torch.full((rows,), -1, dtype=torch.int64, device=device)
    at = torch.nonzero(lens.depth == grade, as_tuple=False).flatten()
    if not at.numel():
        return label, 0
    lo, hi = lens.lo.index_select(0, at), lens.hi.index_select(0, at)
    widths = hi - lo
    owner = torch.repeat_interleave(torch.arange(int(at.numel()), dtype=torch.int64,
                                                 device=device), widths)
    offset = (torch.arange(int(widths.sum()), dtype=torch.int64, device=device)
              - torch.repeat_interleave(torch.cumsum(widths, 0) - widths, widths))
    label[lo[owner] + offset] = owner
    missing = label < 0
    if bool(missing.any()):
        return (torch.where(missing, torch.full_like(label, int(at.numel())), label),
                int(at.numel()) + 1)
    return label, int(at.numel())


def build_membership_coupling(content: Any, relation_lenses: Mapping[str, Any],
                              *, device: torch.device) -> MembershipCoupling:
    """STEP B: ONE coupling over the LENS MEMBERSHIPS, for the whole question list.

    ``content`` is the loaded content lens (whose rank order is the row universe) and
    ``relation_lenses`` the other loaded lenses of the dataset, mapped onto that order by RECORD
    ROW ORDINAL - the identity B.2 mints - never by a positional assumption that two lenses
    ordered their carriers the same way. One axis per lens per grade; the quotient is built ONCE.

    Complexity: O(M log M + axes * distinct label rows). Never the product of cardinalities.
    """
    out = MembershipCoupling()
    rows = content.rows
    started = time.perf_counter()
    axes: list[MembershipAxis] = []
    columns: list[torch.Tensor] = []
    depth_max = int(content.depth.max()) if int(content.lo.numel()) else 0
    for grade in range(depth_max + 1):  # loop-ok: the DEPTHS of the content lens, ~log M
        label, cardinality = _labels_at_grade(content, grade, rows, device)
        if cardinality < 2:
            continue
        axes.append(MembershipAxis(
            content.lens_id, grade, cardinality, label,
            "the content lens's own section at this grade, as ONE categorical axis"))
        columns.append(label)
    for lens_id, other in sorted(relation_lenses.items()):  # loop-ok: the dataset's other declared lenses
        span = max(int(content.rank_global.max()), int(other.rank_global.max())) + 2
        position = torch.full((span,), -1, dtype=torch.int64, device=device)
        position[other.rank_global] = torch.arange(other.rows, dtype=torch.int64, device=device)
        mine = position.index_select(0, content.rank_global)
        other_depth = int(other.depth.max()) if int(other.lo.numel()) else 0
        for grade in range(other_depth + 1):  # loop-ok: the DEPTHS of that lens, ~log M
            label, cardinality = _labels_at_grade(other, grade, other.rows, device)
            if cardinality < 2:
                continue
            mapped = torch.where(mine >= 0, label.index_select(0, mine.clamp(min=0)),
                                 torch.full_like(mine, cardinality))
            axes.append(MembershipAxis(
                lens_id, grade, cardinality + 1, mapped,
                "this relation lens's own section at this grade, over the content lens's rows; "
                "a row this lens does not seat carries its own declared category"))
            columns.append(mapped)
    if not columns:
        out.executed = {"axes": 0, "why": "neither lens offered a graded membership"}
        return out
    labels = torch.stack(columns, dim=1)
    cardinalities = tuple(int(axis.cardinality) for axis in axes)  # loop-ok: the axes just built
    out.axes, out.labels, out.cardinalities = axes, labels, cardinalities
    key = torch.zeros(rows, dtype=torch.int64, device=device)
    width = 1
    for index in range(len(axes) - 1, -1, -1):  # loop-ok: the declared membership axes
        if width > (1 << 40):
            # the packed key would overflow the int64 lattice: the FINER axes already identify
            # the tuple, which is the graded answer to width and never a refusal
            break
        key = key + labels[:, index] * width
        width = width * max(cardinalities[index], 1)
    out.tuple_key = key
    gpu = lifted("gpu_state")
    coupling_module = lifted("section_coupling")
    state = gpu.build_state(labels, cardinalities)
    out.width_by_cut = [
        {"cut": index, "lens_id": axes[layer.axis].lens_id, "grade": axes[layer.axis].grade,
         "cardinality": int(layer.cardinality),
         "continuation_width": int(layer.state_count),
         "what_it_is": ("the exact conditional-law quotient's state count across this cut - the "
                        "Schmidt rank of the joint law of the memberships at this cut, on the "
                        "REAL concept space")}
        for index, layer in enumerate(state.layers)]  # loop-ok: one row per cut of the quotient
    built = time.perf_counter()
    ones = torch.ones(rows, dtype=torch.int64, device=device)
    index = torch.arange(rows, dtype=torch.int64, device=device)
    refusal = None
    try:
        out.coupling = coupling_module.build_coupling(
            source_ids=index, route_source_rows=index, membership_labels=labels,
            route_numerators=ones, common_denominator=1, source_weights=ones,
            cardinalities=cardinalities, max_route_rows=rows,
            max_route_bytes=int(1 << 28))
        out.module = coupling_module
    except (ValueError, TypeError, MemoryError, RuntimeError) as error:
        refusal = {"refusal": type(error).__name__, "why": str(error)}
    out.executed = {
        "axes": len(axes), "rows": rows,
        "axes_declared": [{"lens_id": a.lens_id, "grade": a.grade,
                           "cardinality": a.cardinality} for a in axes],  # loop-ok: the axes
        "quotient_seconds": built - started,
        "coupling_seconds": time.perf_counter() - built,
        "distinct_membership_tuples": (int(out.coupling.postings.tuple_table.shape[0])
                                       if out.coupling is not None
                                       else int(torch.unique(key).numel())),
        "product_of_cardinalities_never_formed": True,
        "coupling_refusal": refusal,
        "amortisation": ("ONE quotient and ONE coupling for the WHOLE question list; a question "
                         "charges no build (joint.py:25-34's discipline, over memberships)"),
    }
    return out


# ==================================================== STEP C: the joint-section read, batched
def certified_upper_batched(frames: NodeFrames, node: torch.Tensor,
                            queries: torch.Tensor) -> torch.Tensor:
    """C7 for ALL questions x the whole frontier in ONE launch. Returns [F, Q].

    The expression is ``frames.certified_upper``'s, unchanged - <mu, q> + R ||V^T q|| + r ||q|| -
    with the query VECTOR replaced by the query MATRIX. It is checked against the lifted function
    itself on a bounded sample every run, so this is a batching of that organ and not a second
    copy of its arithmetic.
    """
    device = frames.mu.device
    q = queries.to(torch.float64)                                  # [Q, d]
    rank = frames.rank()
    widest = max(int(rank[node].max()), 1) if node.numel() else 1
    mean_term = frames.mu.index_select(0, node) @ q.T              # [F, Q]
    along = torch.zeros((int(node.numel()), int(q.shape[0])), dtype=torch.float64,
                        device=device)
    for slot in range(widest):  # loop-ok: the declared register's direction SLOTS, bounded by the rank cap
        live = rank[node] > slot
        if not bool(live.any()):
            continue
        row = frames.dirs.index_select(
            0, (frames.ptr[node] + slot).clamp(max=max(int(frames.dirs.shape[0]) - 1, 0)))
        value = torch.where(live[:, None], row @ q.T, torch.zeros_like(along))
        along = along + value.square()
    return (mean_term
            + frames.radius.index_select(0, node)[:, None] * torch.sqrt(along.clamp(min=0.0))
            + frames.residual_radius.index_select(0, node)[:, None] * q.norm(dim=1)[None, :])


def _batched_residual_stop(vectors: torch.Tensor, segment: torch.Tensor, segments: int,
                           queries: torch.Tensor, tau: torch.Tensor
                           ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, int]:
    """``query_demand``'s greedy residual reduction for EVERY question at once.

    ``down.py:246-314``'s arithmetic, lifted exactly - the anchored rank-one state kernel
    k(x, y) = ((1 + <x, y>)/2)^2 centred on each section's own conditional mean, with its first
    and second vector moments retained and one kernel COLUMN per selected row - and its
    per-section HOST LOOP removed: the rows of every question's section live in one flat array
    with a segment id, each step picks one pivot PER SEGMENT by a segment argmax, and the update
    is ONE device launch for the whole batch. The stop is each question's own tau on its own
    residual; a question whose residual is met stops taking pivots while the others continue.

    Returns (chosen mask over the flat rows, initial residual [S], final residual [S], steps).
    Complexity: O(steps * N * d) device, O(steps * N) for the Cholesky factor.
    """
    device = vectors.device
    n = int(vectors.shape[0])
    zero = torch.zeros(segments, dtype=torch.float64, device=device)
    if not n:
        return torch.zeros(0, dtype=torch.bool, device=device), zero, zero.clone(), 0
    v = vectors.to(torch.float64)
    v = v / v.norm(dim=1, keepdim=True).clamp(min=1e-12)
    q = queries.to(torch.float64)
    q = q / q.norm(dim=1, keepdim=True).clamp(min=1e-12)
    dim = int(v.shape[1])
    epsilon = torch.finfo(torch.float64).eps * (dim + n + 1) * 32
    count = torch.zeros(segments, dtype=torch.float64, device=device)
    count.index_add_(0, segment, torch.ones(n, dtype=torch.float64, device=device))
    mean = torch.zeros((segments, dim), dtype=torch.float64, device=device)
    mean.index_add_(0, segment, v)
    mean = mean / count.clamp(min=1.0)[:, None]
    second = torch.zeros((segments, dim, dim), dtype=torch.float64, device=device)  # dense-ok: S x d x d with d the DECLARED field dimension (384) and S the question count - never a function of the corpus; down.py:273 forms the same d x d block one section at a time
    second.index_add_(0, segment, v[:, :, None] * v[:, None, :])
    second = second / count.clamp(min=1.0)[:, None, None]
    mean_rows = mean.index_select(0, segment)
    second_rows = second.index_select(0, segment)
    source_overlap = (1 + 2 * (v * mean_rows).sum(1)
                      + ((v[:, None, :] @ second_rows)[:, 0, :] * v).sum(1)) / 4
    query_overlap = (1 + 2 * (mean * q).sum(1)
                     + ((q[:, None, :] @ second)[:, 0, :] * q).sum(1)) / 4
    mean_square = (1 + 2 * mean.square().sum(1) + second.square().sum((1, 2))) / 4
    d_diag = (1 - 2 * source_overlap + mean_square.index_select(0, segment)).clamp(min=0.0)
    h = (((1 + (v * q.index_select(0, segment)).sum(1).clamp(-1, 1)) / 2).square()
         - source_overlap - query_overlap.index_select(0, segment)
         + mean_square.index_select(0, segment))
    residual = (1 - 2 * query_overlap + mean_square).clamp(min=0.0)
    initial = residual.clone()
    stop_at = torch.where(torch.isfinite(tau), initial * tau.square(),
                          torch.zeros_like(initial))
    chosen = torch.zeros(n, dtype=torch.bool, device=device)
    columns: list[torch.Tensor] = []
    order = torch.arange(n, dtype=torch.int64, device=device)
    steps = 0
    for _ in range(n):  # loop-ok: ONE step per selected row for the WHOLE batch, stopped by the residual - the read's own budget, never a step per candidate or per question
        live = (residual > stop_at) & (residual > epsilon)
        if not bool(live.any()):
            break
        admissible = d_diag > epsilon
        gain = torch.where(admissible, h.square() / d_diag.clamp(min=epsilon),
                           torch.zeros_like(h))
        score = torch.where(chosen | ~live.index_select(0, segment),
                            torch.full_like(gain, -1.0), gain)
        best = torch.full((segments,), -1.0, dtype=torch.float64, device=device)
        best.scatter_reduce_(0, segment, score, reduce="amax", include_self=True)
        picked = (score >= best.index_select(0, segment)) & (score > epsilon)
        first = torch.full((segments,), n, dtype=torch.int64, device=device)
        if bool(picked.any()):
            first.scatter_reduce_(0, segment[picked], order[picked], reduce="amin",
                                  include_self=True)
        active = torch.nonzero(first < n, as_tuple=False).flatten()
        if not active.numel():
            break
        pivot = first.index_select(0, active)
        pivot_of_segment = torch.full((segments,), -1, dtype=torch.int64, device=device)
        pivot_of_segment[active] = pivot
        mine = pivot_of_segment.index_select(0, segment)
        has = mine >= 0
        safe = mine.clamp(min=0)
        overlap = ((1 + (v * v.index_select(0, safe)).sum(1).clamp(-1, 1)) / 2).square()
        column = torch.where(has,
                             overlap - source_overlap - source_overlap.index_select(0, safe)
                             + mean_square.index_select(0, segment),
                             torch.zeros(n, dtype=torch.float64, device=device))
        for previous in columns:  # loop-ok: the steps already taken, bounded by the residual stop above
            column = column - previous * torch.where(
                has, previous.index_select(0, safe),
                torch.zeros(n, dtype=torch.float64, device=device))
        scale = torch.ones(segments, dtype=torch.float64, device=device)
        scale[active] = torch.sqrt(d_diag.index_select(0, pivot).clamp(min=epsilon))
        column = column / scale.index_select(0, segment)
        coefficient = torch.zeros(segments, dtype=torch.float64, device=device)
        coefficient[active] = h.index_select(0, pivot) / scale.index_select(0, active)
        h = h - coefficient.index_select(0, segment) * column
        d_diag = (d_diag - column.square()).clamp(min=0.0)
        residual = (residual - coefficient.square()).clamp(min=0.0)
        chosen[pivot] = True
        columns.append(column)
        steps += 1
    return chosen, initial, residual, steps


class JointSectionRead:
    """The joint-section read of one dataset, for the WHOLE question list at once.

    Built by the door's faces stage (it is a function of the record and the loaded lenses) and
    asked once per run by the planner's joint-section route.
    """

    __slots__ = ("opened", "content", "others", "frames", "columns", "directions",
                 "membership", "field", "executed", "device", "lens_declaration",
                 "carrier_kind", "build_seconds")

    def __init__(self, opened: Any, content: Any, others: Mapping[str, Any],
                 frames: NodeFrames, columns: Any, lens_declaration: Any,
                 carrier_kind: str) -> None:
        started = time.perf_counter()
        device = content.rank_global.device
        self.opened, self.content, self.others = opened, content, dict(others)
        self.frames, self.columns, self.device = frames, columns, device
        self.lens_declaration = lens_declaration
        self.carrier_kind = carrier_kind
        self.directions = ContentDirections(opened.ingestion, carrier_kind, device)
        # THE FIELD IN THE LENS'S RANK ORDER: the same observation the build graded, re-read from
        # the leaves by the same reduction ``generator.carrier_field`` does (a carrier row's field
        # is the mean of its own leaves' stored unit vectors, renormalised). One scatter.
        rows_total = int(opened.ingestion.store.row_count)
        rank_of_global = torch.full((rows_total,), -1, dtype=torch.int64, device=device)
        rank_of_global[content.rank_global] = torch.arange(content.rows, dtype=torch.int64,
                                                           device=device)
        table = opened.ingestion.store.table(carrier_kind)
        rank_of_table = rank_of_global.index_select(0, table.global_ordinals)
        leaf_table_local = self.directions.carrier_local
        live = leaf_table_local >= 0
        rank_of_leaf = rank_of_table.index_select(0, leaf_table_local[live])
        keep = rank_of_leaf >= 0
        dim = int(self.directions.vectors.shape[1])
        total = torch.zeros((content.rows, dim), dtype=torch.float64, device=device)
        count = torch.zeros(content.rows, dtype=torch.float64, device=device)
        total.index_add_(0, rank_of_leaf[keep],
                         self.directions.vectors[live][keep].to(torch.float64))
        count.index_add_(0, rank_of_leaf[keep],
                         torch.ones(int(keep.sum()), dtype=torch.float64, device=device))
        total = total / count.clamp(min=1.0)[:, None]
        self.field = total / total.norm(dim=1, keepdim=True).clamp(min=1e-12)
        self.membership = build_membership_coupling(content, self.others, device=device)
        self.executed = {"rows_with_a_field": int((count > 0).sum())}
        self.build_seconds = time.perf_counter() - started

    # --------------------------------------------------------------- (i) the certified descent
    def descend(self, queries: torch.Tensor, tau: torch.Tensor, admitted: torch.Tensor
                ) -> dict[str, Any]:
        """The content lens from its ROOTS, all questions on ONE shared frontier.

        ``admitted`` is [Q, M] bool: the typed conditions' mask over the lens's rank positions
        (move (ii)), applied to the actual scores so that a row the conditions exclude can never
        raise a question's best score and can never enter its section.
        """
        device = self.device
        lens, frames = self.content, self.frames
        questions = int(queries.shape[0])
        frontier = lens.roots.clone()
        open_mask = torch.ones((questions, int(frontier.numel())), dtype=torch.bool,
                               device=device)
        best = torch.full((questions,), -float("inf"), dtype=torch.float64, device=device)
        # THE DECIDED SET IS ACCUMULATED AS A COUNT, NOT AS A BOOL. ``index_put_`` with
        # ``accumulate=True`` on a torch.bool destination writes nothing on this device: the
        # first pass of this read descended six rounds, opened its leaves and returned
        # decided_rows 0 for every question, with the whole joint section, the residual stop and
        # the byte budget empty behind it. The scatter is therefore into int8 and the mask is
        # read back as ``> 0``; the arithmetic of what is taken is unchanged.
        decided_count = torch.zeros((questions, lens.rows), dtype=torch.int8, device=device)
        rejected = torch.zeros(questions, dtype=torch.int64, device=device)
        first_depth = torch.full((questions,), -1, dtype=torch.int64, device=device)
        rows_index = torch.arange(questions, dtype=torch.int64, device=device)
        # WHY A QUESTION CAN COME BACK WITH AN EMPTY SECTION, MEASURED RATHER THAN GUESSED: the
        # count of this question's OWN admitted rows that a leaf of the descent actually scored.
        # Zero here means the descent never opened a leaf holding a row the conditions admit,
        # which is a statement about the jurisdiction mask and the tree, not about the bound.
        admitted_rows_scored = torch.zeros(questions, dtype=torch.int64, device=device)
        rounds: list[dict[str, Any]] = []
        launches = 0
        started = time.perf_counter()
        while int(frontier.numel()) and bool(open_mask.any()):  # loop-ok: one iteration per ROUND of the shared descent, depth ~ log M
            upper = certified_upper_batched(frames, frontier, queries).T     # [Q, F]
            launches += 1
            reject = open_mask & (upper < (best - tau)[:, None])
            if bool(reject.any()):
                depth_here = lens.depth.index_select(0, frontier)[None, :].expand_as(reject)
                rejected = rejected + reject.sum(1)
                deepest = torch.where(reject, depth_here,
                                      torch.full_like(depth_here, 1 << 30)).min(dim=1).values
                first_depth = torch.where((first_depth < 0) & (deepest < (1 << 30)), deepest,
                                          first_depth)
            open_mask = open_mask & ~reject
            is_leaf = lens.left.index_select(0, frontier) < 0
            leaves = torch.nonzero(is_leaf & open_mask.any(0), as_tuple=False).flatten()
            opened_rows = 0
            if leaves.numel():
                nodes = frontier.index_select(0, leaves)
                lo, hi = lens.lo.index_select(0, nodes), lens.hi.index_select(0, nodes)
                widths = hi - lo
                owner = torch.repeat_interleave(leaves, widths)
                offset = (torch.arange(int(widths.sum()), dtype=torch.int64, device=device)
                          - torch.repeat_interleave(torch.cumsum(widths, 0) - widths, widths))
                positions = torch.repeat_interleave(lo, widths) + offset
                opened_rows = int(positions.numel())
                scores = queries @ self.field.index_select(0, positions).T        # [Q, P]
                allow = (open_mask.index_select(1, owner)
                         & admitted.index_select(1, positions))                   # [Q, P]
                scores = torch.where(allow, scores, torch.full_like(scores, -float("inf")))
                admitted_rows_scored = admitted_rows_scored + allow.sum(1)
                best = torch.maximum(best, scores.max(dim=1).values)
                took = allow & (scores >= (best - tau)[:, None])
                decided_count.index_put_(
                    (rows_index[:, None].expand_as(took),
                     positions[None, :].expand_as(took)),
                    took.to(torch.int8), accumulate=True)
                launches += 1
            interior = torch.nonzero(~is_leaf & open_mask.any(0), as_tuple=False).flatten()
            rounds.append({"round": len(rounds), "frontier": int(frontier.numel()),
                           "ranges_rejected_unopened": int(reject.sum()),
                           "leaves_opened": int(leaves.numel()),
                           "rows_scored": opened_rows,
                           "interior_descended": int(interior.numel())})
            if not interior.numel():
                break
            nodes = frontier.index_select(0, interior)
            children = torch.stack([lens.left.index_select(0, nodes),
                                    lens.right.index_select(0, nodes)], dim=1).reshape(-1)
            open_mask = (open_mask.index_select(1, interior).repeat_interleave(2, dim=1)
                         & (children >= 0)[None, :])
            frontier = children
        torch.cuda.synchronize()
        # THE BATCHED BOUND IS THE LIFTED ONE: the same expression, checked against
        # ``frames.certified_upper`` itself on a bounded sample of the roots.
        sample = lens.roots[:8]
        agree = True
        if sample.numel() and questions:
            mine = certified_upper_batched(frames, sample, queries[:1])[:, 0]
            theirs = certified_upper(frames, sample, queries[0])
            agree = bool(torch.allclose(mine, theirs, rtol=1e-12, atol=1e-12))
        return {"decided": decided_count > 0, "rounds": rounds, "launches": launches,
                "sections_rejected_unopened": [int(v) for v in rejected.tolist()],  # loop-ok: the question list
                "depth_of_the_first_rejection": [int(v) for v in first_depth.tolist()],  # loop-ok: the question list
                "best_actual_score": [float(v) for v in best.tolist()],  # loop-ok: the question list
                "admitted_rows_the_descent_scored": [int(v) for v in admitted_rows_scored.tolist()],  # loop-ok: the question list
                "certified_upper_batched_equals_lifted": agree,
                "seconds": time.perf_counter() - started,
                "k_derivation": K_DERIVATION}


def _reader_context(read: JointSectionRead, global_rows: torch.Tensor,
                    qid: str) -> dict[str, Any]:
    """C3b: THE READER-CONTEXT STAGE, where tokens become the legitimate currency.

    What the read supplies is FOR a reader (extension/READER_CONTRACT.md), so the supplied set is
    the joint section's ORIGINAL spans with their identifiers, with the PREVIOUS TURN of every
    reply carried as one atomic group (witness_readout_contract: "previous-turn plus current-turn
    groups as one atomic group"), under the READER's own declared token budget. Bytes are the
    store's currency up to this boundary and tokens are the reader's; the two are never summed.
    NO reader model is called here - the standing order - and the block is recorded in the
    reader's own context shape so the trial can run unchanged when the author approves the spend.
    """
    ingestion = read.opened.ingestion
    device = read.device
    table = ingestion.store.table(read.carrier_kind)
    budget_module = lifted("context_budget")
    declared = int(getattr(budget_module, "DEFAULT_CONTEXT_TOKENS",
                           getattr(budget_module, "DEFAULT_TOKEN_BUDGET", 4096)))
    rows_total = int(ingestion.store.row_count)
    group_rows = global_rows
    follows = ingestion.relations.kind("follows")
    if follows is not None and len(follows):
        csr = follows.csr(rows_total)
        degree = (csr.indptr[1:] - csr.indptr[:-1]).to(torch.int64)
        owner = torch.repeat_interleave(
            torch.arange(rows_total, dtype=torch.int64, device=device), degree)
        reverse = torch.full((rows_total,), -1, dtype=torch.int64, device=device)
        reverse[csr.indices.to(torch.int64)] = owner
        previous = reverse.index_select(0, global_rows)
        group_rows = torch.unique(torch.cat([global_rows, previous[previous >= 0]]))
    local = ingestion.store.local_of_global(read.carrier_kind)
    positions = local.index_select(0, group_rows)
    spans = table.column("content_span").to(torch.int64).index_select(0, positions)
    columns = ingestion.spans.columns
    lengths = (columns[:, 2] - columns[:, 1]).index_select(0, spans)
    bytes_total = int(lengths.sum())
    tokens = ingestion.content.tokens_per_row_mean if hasattr(
        ingestion.content, "tokens_per_row_mean") else None
    per_token = 4.0 if tokens is None else max(float(bytes_total) / max(float(tokens), 1.0), 1.0)
    estimated = int(bytes_total / per_token)
    return {"qid": qid,
            "supplied_rows": int(global_rows.numel()),
            "rows_with_their_atomic_group": int(group_rows.numel()),
            "atomic_group_rule": ("the previous turn of every supplied row, through the record's "
                                  "own `follows` relation, as ONE group - never a heuristic "
                                  "about replies"),
            "reader_token_budget": declared,
            "reader_token_budget_source": ("extension/context_budget.py's own declared budget, "
                                           "loaded by atlas.front.lift; never a literal here"),
            "bytes_of_the_group": bytes_total,
            "tokens_estimated": estimated,
            "bytes_per_token": per_token,
            "fits_the_reader_budget": estimated <= declared,
            "currency_boundary": ("bytes up to this stage, tokens from it; the two are never "
                                  "summed (the reconciliation's object-table row 16)"),
            "reader_model_called": False}


def joint_section_questions(read: JointSectionRead, compiled: Sequence[Any],
                            *, budgets: Sequence[int] = (4096, 8192, 16384)) -> dict[str, Any]:
    """THE WHOLE READ for the whole question list: (i) to (v), each measured.

    Complexity in the module docstring. Every counter returned is executed work.
    """
    device = read.device
    lens = read.content
    questions = list(compiled)
    started = time.perf_counter()
    texts = [q.spec.text for q in questions]  # loop-ok: the dataset's own question list
    directions = read.directions.directions(texts)                      # [Q, d]
    tau = torch.tensor([float(getattr(q, "question_tau", 0.0) or 0.0) for q in questions],  # loop-ok: the same list
                       dtype=torch.float64, device=device)
    admitted = torch.ones((len(questions), lens.rows), dtype=torch.bool, device=device)
    condition_rows: list[int] = []
    for index, question in enumerate(questions):  # loop-ok: the question list, ONCE, outside every round
        mask = torch.ones(lens.rows, dtype=torch.bool, device=device)
        # (ii) THE TYPED CONDITIONS AS MASKS OVER THE FRONTIER. ``_satisfies`` is the read's own
        # per-condition predicate over RANK POSITIONS (read.py:232-256) - the only place a read
        # may interpret a declared null - so the AND of the question's coded conditions over the
        # lens's whole rank order IS its jurisdiction mask. (``_face_for`` is the FRONTIER face:
        # a per-RANGE count table for a boundary tensor, not a per-position mask, and calling it
        # here with ``read.opened`` in the boundary argument's place raised AttributeError:
        # 'OpenedRecord' object has no attribute 'numel' at faces.py:479 on every question.)
        for entry in RD._entries(question, read.columns):  # loop-ok: this question's own declared conditions
            ranked = entry["ranked"]
            if ranked is None:
                continue
            mask = mask & RD._satisfies(entry, ranked, entry["null"])[:lens.rows]
        admitted[index] = mask
        condition_rows.append(int(mask.sum()))
    descent = read.descend(directions, tau, admitted)
    decided = descent["decided"]
    flat_rows: list[torch.Tensor] = []
    segment: list[torch.Tensor] = []
    joint_blocks: list[dict[str, Any]] = []
    for index in range(len(questions)):  # loop-ok: the question list, ONCE, after the rounds
        rows = torch.nonzero(decided[index], as_tuple=False).flatten()
        block = read.membership.intersect(rows)
        joint = block["joint_rows"]
        joint = joint[admitted[index].index_select(0, joint)]
        joint_blocks.append({**{k: v for k, v in block.items() if k != "joint_rows"},
                             "memberships": read.membership.section_of(rows),
                             "joint_section_rows": int(joint.numel()),
                             "decided_rows": int(rows.numel())})
        flat_rows.append(joint)
        segment.append(torch.full((int(joint.numel()),), index, dtype=torch.int64,
                                  device=device))
    empty = torch.empty(0, dtype=torch.int64, device=device)
    rows_flat = torch.cat(flat_rows) if flat_rows else empty
    segment_flat = torch.cat(segment) if segment else empty
    chosen, initial, final, steps = _batched_residual_stop(
        read.field.index_select(0, rows_flat), segment_flat, len(questions), directions, tau)
    per_question: dict[str, Any] = {}
    for index, question in enumerate(questions):  # loop-ok: the question list, after the stop
        mine = segment_flat == index
        section = rows_flat[mine]
        survivors = rows_flat[mine & chosen] if int(chosen.numel()) else section
        if not survivors.numel():
            survivors = section[:1]
        global_rows = lens.rank_global.index_select(0, survivors)
        # (v) THE BYTE BUDGET LAST, over the joint section's rows IN RESIDUAL ORDER. Both supply
        # disciplines are reported, as read.py:907 defines them: PARTIAL pays the witness bytes
        # of the rows the conditions admit, WHOLE pays every row of the supplied set. The joint
        # section is already a filtered row set, so both arguments are the same rows and the two
        # disciplines differ only in what they are named against.
        evidence = {str(budget): {
            supply: RD.evidence_within_a_budget(
                read.opened, question.spec.row_kind, global_rows, global_rows,
                budget=int(budget), supply=supply)
            for supply in ("partial", "whole")}  # loop-ok: the two declared supply disciplines
            for budget in budgets}  # loop-ok: the declared byte budgets of the coverage scorer
        paid = max(int(evidence[str(b)]["partial"]["rows_supplied"]) for b in budgets)  # loop-ok: the same declared budgets
        handles = RD._row_handles(read.opened, question.spec.row_kind, global_rows,
                                  limit=max(paid, 1))
        per_question[question.spec.qid] = {
            "qid": question.spec.qid,
            "class": "content_question",
            "route": "the joint-section read",
            "entry_nodes": [int(v) for v in lens.roots[:4].tolist()],  # loop-ok: the reported sample
            "rounds": len(descent["rounds"]),
            "sections_rejected_unopened": descent["sections_rejected_unopened"][index],
            "depth_of_the_first_rejection": descent["depth_of_the_first_rejection"][index],
            "rows_the_conditions_admit": condition_rows[index],
            "admitted_rows_the_descent_scored":
                descent["admitted_rows_the_descent_scored"][index],
            "best_actual_score": descent["best_actual_score"][index],
            "joint_section": joint_blocks[index],
            "joint_section_size": int(section.numel()),
            "residual_steps": int((chosen & mine).sum()) if int(chosen.numel()) else 0,
            "residual_initial": float(initial[index]),
            "residual_final": float(final[index]),
            "tau": float(tau[index]),
            "survivors": int(survivors.numel()),
            "handles": handles.as_dicts(12),
            "evidence_by_budget": evidence,
            "reader_context": _reader_context(read, global_rows, question.spec.qid),
            "supplied_global_rows": [int(v) for v in global_rows.tolist()],  # loop-ok: this question's own supplied rows
        }
    executed = {
        "questions": len(questions),
        "encode_calls": read.directions.calls,
        "encode_seconds": read.directions.seconds,
        "descent_launches": descent["launches"],
        "descent_rounds": len(descent["rounds"]),
        "descent_seconds": descent["seconds"],
        "certified_upper_batched_equals_lifted":
            descent["certified_upper_batched_equals_lifted"],
        "residual_steps_for_the_whole_batch": steps,
        "seconds": time.perf_counter() - started,
        "build_seconds": read.build_seconds,
        "membership": read.membership.executed,
        "continuation_width_by_cut": read.membership.width_by_cut,
        "rounds": descent["rounds"],
        "k_derivation": K_DERIVATION,
        "no_model_on_the_path": ("the only encode is the record's own declared span encoder "
                                 "applied to the question TEXT (D.1); no reader model, no "
                                 "proposal step, no English vocabulary"),
    }
    return {"questions": per_question, "executed": executed}


# Conditional field-enabled front receipt; no numeric execution/decision changes.

# The inert closed receipt contract; numeric execution remains owned here.
from ..receipt_diagnostics import joint_section_parts
