"""Tests THIS packet wrote for src/atlas/grading/tree.py. Run with a unique --basetemp:

    scripts/laplace-python -m pytest atlas/tests/test_grading_tree.py \
        --basetemp=/tmp/pytest-grading-tree-j1 -q

Three kinds of test, and no decoration:

  ACCEPTANCE EVIDENCE - the five checks ``augmented_grade_execution.md`` names under "First
  acceptance evidence", lifted from
  ``synthetics papers/corpus-as-a-state/reconstruction/test_section_augmented.py`` and run
  against THIS register, plus a direct agreement check against the dense oracle
  ``section_augmented.build_object_grade``, which is REUSED AS IS and never re-authored.

  TRUE BY CONSTRUCTION, PROVED ONCE - the range algebra (a face folded from children equals the
  face folded from rows), the transport identities and the cocycle. Nothing here runs at build
  time: the build's own gate is the cheap orthonormality/reference check on the diff.

  FALSIFIABLE - each mutates its input and asserts the verdict flips, or asserts the refusal by
  name. The tests that matter most assert that a refusal MARKS: no node is ever deleted.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import torch

from atlas.grading import tree as T
from atlas.grading.blocks import build_task_columns, derive_tolerances
from atlas.grading.generator import build_lens_generator
from atlas.grading.lens import LensRefusal, RegisterDeclaration
from atlas.grading.lenses import engine_lenses, toy_lens
from atlas.record.ingest import engine_rows, toy
from atlas.store import CompressedHive

pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="the numeric core is GPU")

RECONSTRUCTION = (Path(__file__).resolve().parents[2]
                  / "synthetics papers" / "corpus-as-a-state" / "reconstruction")


def _oracle():
    """``section_augmented`` - the DENSE oracle, reused as is (inventory verdict REUSE_AS_IS)."""
    if str(RECONSTRUCTION) not in sys.path:
        sys.path.insert(0, str(RECONSTRUCTION))
    import section_augmented
    return section_augmented


def _register(cap: int, price: float = 0.0) -> RegisterDeclaration:
    """A declared register with a fixture's own provenance - never a bare literal."""
    return RegisterDeclaration(
        hidden_rank_cap=cap,
        rank_cap_derivation=f"declared by this fixture as the rank the example needs ({cap}); "
                            "the example's own construction is the provenance",
        task_family_weight=1.0, law_family_weight=1.0,
        family_weight_derivation="1:1, ruling L11",
        support_floor_eps_multiple=64.0,
        support_floor_derivation="scale-relative float64 support floor",
        tie_relative_tolerance=1e-7, tie_derivation="ties are recorded, never broken",
        rank_price_lambda=price,
        rank_price_derivation=(
            f"lambda = {price} declared by this acceptance fixture: the known answer is about "
            "the REGISTER (what a rank-r coordinate carries and transports), so the fixture "
            "declares description free (lambda = 0) unless it is the fixture FOR the price, "
            "which declares its own rate and says what it buys."))


def _reset_law(n: int, gamma: float = 1.7):
    """The reversible reset law of augmented_grade_execution.md's first acceptance example."""
    pi = torch.full((n,), 1 / n, device="cuda", dtype=torch.float64)
    root = torch.sqrt(pi)
    operator = gamma * (root[:, None] * root[None, :]
                        - torch.eye(n, device="cuda", dtype=torch.float64))
    return operator, root


def _one_round(operator, reference, tasks, labels, rank, *, horizon=1):
    state, columns, tolerances = T.dense_state(operator, reference, tasks,
                                               walk_horizon=horizon)
    return state, T.up_round(state, labels, register=_register(rank), horizon=horizon,
                             columns=columns, tolerances=tolerances, rank=rank)


# ===================================================================== ACCEPTANCE EVIDENCE 1
def test_reset_law_bare_mean_loses_one_half_and_a_rank_one_register_is_exact():
    """"bare mean has test RMS 1/2, a retained contrast has zero loss, and the register evolves
    at the correct rate" - augmented_grade_execution.md, First acceptance evidence."""
    operator, root = _reset_law(2)
    physical = torch.tensor([[1.0], [0.0]], device="cuda", dtype=torch.float64)
    tasks = root[:, None] * physical
    labels = torch.zeros(2, device="cuda", dtype=torch.int64)

    _, bare = _one_round(operator, root, tasks, labels, 0)
    torch.testing.assert_close(bare["task_rms"][0],
                               torch.tensor([0.5], device="cuda", dtype=torch.float64))

    _, augmented = _one_round(operator, root, tasks, labels, 1)
    assert float(augmented["task_rms"].max()) < 1e-10
    assert float(augmented["closure"].max()) < 1e-10
    # the register evolves at the correct rate: the signed coordinate's own diagonal is -gamma
    state = augmented["state"]
    diagonal = state.l_val[state.l_row == state.l_col]
    register_row = state.coord_mode[state.l_row[state.l_row == state.l_col]] == 1
    torch.testing.assert_close(diagonal[register_row],
                               torch.tensor([-1.7], device="cuda", dtype=torch.float64))


# ===================================================================== ACCEPTANCE EVIDENCE 2
def test_two_grades_transport_every_register_and_satisfy_the_cocycle():
    """"Two grades transport the register, preserve the reference, and agree with the direct
    composite task readout and law-defect cocycle." D_02 = U_2^T D_01 + D_12 U_1^T."""
    operator, root = _reset_law(4, gamma=0.8)
    physical = torch.tensor([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]],
                            device="cuda", dtype=torch.float64)
    tasks = root[:, None] * physical
    labels = torch.tensor([0, 0, 1, 1], device="cuda", dtype=torch.int64)

    state0, first = _one_round(operator, root, tasks, labels, 1)
    u1 = T.dense_isometry(state0, first["map"], first["state"].coordinates)
    state1 = first["state"]
    assert state1.coordinates == 4                     # every child register travelled

    second = T.up_round(state1, torch.zeros(2, device="cuda", dtype=torch.int64),
                        register=_register(1), horizon=1,
                        columns=T.dense_state(operator, root, tasks)[1],
                        tolerances=T.dense_state(operator, root, tasks)[2], rank=1)
    u2 = T.dense_isometry(state1, second["map"], second["state"].coordinates)

    def dense(state, size=None):
        size = size or state.coordinates
        out = torch.zeros((size, size), device="cuda", dtype=torch.float64)  # dense-ok: the FIXTURE's own [coordinates, coordinates] L, a handful of rows, never a corpus
        out.index_put_((state.l_row, state.l_col), state.l_val, accumulate=True)
        return out

    l0, l1, l2 = dense(state0), dense(state1), dense(second["state"])
    torch.testing.assert_close(l1, u1.T @ l0 @ u1, atol=1e-12, rtol=0)
    torch.testing.assert_close(l2, u2.T @ l1 @ u2, atol=1e-12, rtol=0)

    # the reference is preserved: U^T s at the constant coordinate is sqrt(parent mass)
    torch.testing.assert_close(state1.s, u1.T @ state0.s, atol=1e-12, rtol=0)

    # THE COCYCLE, exactly: D_02 = U_2^T D_01 + D_12 U_1^T  (A.18 / A.19)
    d01 = u1.T @ l0 - l1 @ u1.T
    d12 = u2.T @ l1 - l2 @ u2.T
    u02 = u1 @ u2
    d02 = u02.T @ l0 - l2 @ u02.T
    torch.testing.assert_close(d02, u2.T @ d01 + d12 @ u1.T, atol=1e-12, rtol=0)

    # and the build's own per-parent number is the Frobenius norm of that stage defect
    torch.testing.assert_close(second["closure"],
                               torch.linalg.matrix_norm(d12, "fro").reshape(1),
                               atol=1e-10, rtol=0)


# ===================================================================== ACCEPTANCE EVIDENCE 3
def test_a_change_of_register_basis_moves_coordinates_not_the_projected_object():
    """"A change of local register basis preserves the projected object and changes
    decoder/operator coordinates covariantly." """
    operator, root = _reset_law(4)
    physical = torch.tensor([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]],
                            device="cuda", dtype=torch.float64)
    tasks = root[:, None] * physical
    labels = torch.zeros(4, device="cuda", dtype=torch.int64)
    state, grade = _one_round(operator, root, tasks, labels, 2)
    u = T.dense_isometry(state, grade["map"], grade["state"].coordinates)

    angle = torch.tensor(0.37, device="cuda", dtype=torch.float64)
    gauge = torch.eye(3, device="cuda", dtype=torch.float64)
    gauge[1:, 1:] = torch.stack((
        torch.stack((torch.cos(angle), -torch.sin(angle))),
        torch.stack((torch.sin(angle), torch.cos(angle)))))
    moved = u @ gauge
    torch.testing.assert_close(moved @ moved.T, u @ u.T, atol=1e-12, rtol=0)
    l0 = torch.zeros((4, 4), device="cuda", dtype=torch.float64)
    l0.index_put_((state.l_row, state.l_col), state.l_val, accumulate=True)
    torch.testing.assert_close(gauge.T @ (u.T @ l0 @ u) @ gauge, moved.T @ l0 @ moved,
                               atol=1e-12, rtol=0)


# ===================================================================== ACCEPTANCE EVIDENCE 4
def test_a_hidden_unequal_coupling_produces_a_defect_and_refuses_at_inadequate_rank():
    """"A hidden unequal coupling produces a nonzero augmented defect and triggers the stated
    refusal when rank is inadequate." The rank-0 grade must NOT close."""
    weights = torch.zeros((4, 4), device="cuda", dtype=torch.float64)
    weights[0, 2] = weights[2, 0] = 1.0
    weights[1, 3] = weights[3, 1] = 3.0
    weights[0, 1] = weights[1, 0] = 0.2
    weights[2, 3] = weights[3, 2] = 0.2
    operator = weights - torch.diag(weights.sum(0))
    root = torch.full((4,), 0.5, device="cuda", dtype=torch.float64)
    tasks = torch.zeros((4, 1), device="cuda", dtype=torch.float64)
    labels = torch.tensor([0, 0, 1, 1], device="cuda", dtype=torch.int64)

    _, bare = _one_round(operator, root, tasks, labels, 0)
    assert float(bare["closure"].max()) > 0.1
    _, richer = _one_round(operator, root, tasks, labels, 1)
    assert float(richer["closure"].max()) < float(bare["closure"].max())


# ===================================================================== ACCEPTANCE EVIDENCE 5
def test_rare_conditioning_multiplies_the_task_error_by_the_changed_measure_norm():
    """"Rare conditioning multiplies task error by the correct changed-measure norm" -
    |answer error| <= sqrt(L_f) sqrt(1/z - 1), section_synthesis sec 4."""
    oracle = _oracle()
    operator, root = _reset_law(2)
    tasks = root[:, None] * torch.tensor([[1.0], [0.0]], device="cuda", dtype=torch.float64)
    labels = torch.zeros(2, device="cuda", dtype=torch.int64)
    _, bare = _one_round(operator, root, tasks, labels, 0)
    bound = oracle.changed_measure_task_bound(bare["task_rms"][0], event_mass=0.01)
    torch.testing.assert_close(bound, bare["task_rms"][0] * (99 ** 0.5))
    assert float(bound) > float(bare["task_rms"][0])


# ===================================================================== ACCEPTANCE EVIDENCE 6
def test_a_second_grade_must_retain_the_child_register_not_only_the_child_means():
    """The defect the whole packet exists to prevent: both child means are 1/2, so a mean-only
    recurrence reports zero new loss while deleting the child contrasts costs RMS 1/2."""
    gamma = 1.3
    block = gamma * torch.tensor([[-0.5, 0.5], [0.5, -0.5]], device="cuda", dtype=torch.float64)
    operator = torch.zeros((4, 4), device="cuda", dtype=torch.float64)
    operator[:2, :2] = block
    operator[2:, 2:] = block
    root = torch.full((4,), 0.5, device="cuda", dtype=torch.float64)
    physical = torch.tensor([0.0, 1.0, 0.0, 1.0], device="cuda", dtype=torch.float64)
    tasks = root[:, None] * physical[:, None]

    state0, first = _one_round(operator, root, tasks,
                               torch.tensor([0, 0, 1, 1], device="cuda", dtype=torch.int64), 1)
    assert float(first["task_rms"].max()) < 1e-10
    columns, tolerances = T.dense_state(operator, root, tasks)[1:]
    labels = torch.zeros(2, device="cuda", dtype=torch.int64)
    dropped = T.up_round(first["state"], labels, register=_register(0), horizon=1,
                         columns=columns, tolerances=tolerances, rank=0)
    torch.testing.assert_close(dropped["task_rms"][0],
                               torch.tensor([0.5], device="cuda", dtype=torch.float64),
                               atol=1e-10, rtol=0)
    retained = T.up_round(first["state"], labels, register=_register(1), horizon=1,
                          columns=columns, tolerances=tolerances, rank=1)
    assert float(retained["task_rms"].max()) < 1e-10
    assert float(retained["closure"].max()) < 1e-10


# ==================================================== AGREEMENT WITH THE DENSE ORACLE
def test_the_lifted_register_agrees_with_the_dense_oracle():
    """``section_augmented.build_object_grade`` is the oracle; this register is the lifted,
    sparse, bucket-batched form of the same construction and must agree where both are exact."""
    oracle = _oracle()
    operator, root = _reset_law(4, gamma=0.8)
    physical = torch.tensor([[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]],
                            device="cuda", dtype=torch.float64)
    tasks = root[:, None] * physical
    labels = torch.tensor([0, 0, 1, 1], device="cuda", dtype=torch.int64)
    initial = oracle.initial_retained_state(operator, root, tasks, tasks)
    dense = oracle.build_object_grade(initial, labels, hidden_rank=(1, 1),
                                      task_tolerance=1e-9, law_tolerance=1e-9)

    state, mine = _one_round(operator, root, tasks, labels, 1)
    u = T.dense_isometry(state, mine["map"], mine["state"].coordinates)
    # the register is a GAUGE: what must agree is the projected object, not the coordinates
    torch.testing.assert_close(u @ u.T, dense.local_isometry @ dense.local_isometry.T,
                               atol=1e-10, rtol=0)
    torch.testing.assert_close(mine["new_task_squared"][:, 0].sum(),
                               dense.new_task_squared.sum(), atol=1e-12, rtol=0)
    torch.testing.assert_close(
        mine["closure"].square().sum().sqrt(),
        torch.linalg.matrix_norm(dense.stage_law_defect, "fro"), atol=1e-10, rtol=0)
    assert tuple(mine["rank"].tolist()) == tuple(dense.ranks_per_parent)
    assert u.shape[1] == dense.local_isometry.shape[1]


# ======================================================== the sqrt(3/8) lateral known answer
def test_the_three_state_lateral_known_answer_is_sqrt_three_eighths():
    """The contract's known answer for the FOURTH typed quantity, kept as its own number and
    never fused with closure (charter four_residuals). Reuses the verified organ."""
    pi = torch.full((3,), 1 / 3, device="cuda", dtype=torch.float64)
    reading = T.lateral_residual(torch.tensor([0, 0, 1], device="cuda"), pi,
                               torch.tensor([0, 1, 1], device="cuda"), pi)
    assert abs(reading["commutator_frobenius"] - (3 / 8) ** 0.5) < 1e-14


# ======================================================== TRUE BY CONSTRUCTION, PROVED ONCE
def test_a_face_folded_from_children_equals_the_face_folded_from_rows():
    """A.34's closure, by CONSTRUCTION rather than by a run-time check: every face reduction of
    atlas.interface/2 is associative over concatenated ranges, so a node's reduction over
    [lo, hi) is the reduction of its two children's ranges. Proved once, here, never at run
    time - which is what makes the interface's "no face stored per node" free."""
    ingestion = toy.ingest().ingestion
    lens = toy_lens(ingestion)
    tree = T.build_graded_tree(ingestion, lens)
    proposal = tree.proposal
    codes = tree.columns.value_of_row[proposal.order]
    mass = tree.flat.pi[proposal.order]
    internal = torch.nonzero(proposal.left >= 0, as_tuple=False).flatten()
    for node in internal.tolist():   # loop-ok: a FIXTURE may walk the node table; the build may not
        left, right = int(proposal.left[node]), int(proposal.right[node])
        assert int(proposal.lo[left]) == int(proposal.lo[node])
        assert int(proposal.hi[left]) == int(proposal.lo[right])
        assert int(proposal.hi[right]) == int(proposal.hi[node])
        whole = torch.bincount(codes[proposal.lo[node]:proposal.hi[node]].clamp(min=0),
                               minlength=tree.columns.n_values + 1)
        folded = (torch.bincount(codes[proposal.lo[left]:proposal.hi[left]].clamp(min=0),
                                 minlength=tree.columns.n_values + 1)
                  + torch.bincount(codes[proposal.lo[right]:proposal.hi[right]].clamp(min=0),
                                   minlength=tree.columns.n_values + 1))
        assert torch.equal(whole, folded)
        assert abs(float(mass[proposal.lo[node]:proposal.hi[node]].sum())
                   - float(mass[proposal.lo[left]:proposal.hi[left]].sum())
                   - float(mass[proposal.lo[right]:proposal.hi[right]].sum())) < 1e-12


def test_the_flat_tolerances_are_the_organs_own_arithmetic():
    """``flat_tolerances`` must be ``blocks.derive_tolerances``, number for number, vectorised
    over components. If it drifts, the tree is judged against a different tolerance from the
    one the verified organ derives."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["entity"]
    flat = T.build_flat_carrier(ingestion, lens)
    columns = T.flat_task_columns(ingestion, lens, flat)
    mine = T.flat_tolerances(lens, flat, columns)
    generator = build_lens_generator(ingestion, lens)
    largest = max(generator.components, key=lambda c: c.n)
    # find the flat component holding the same rows
    member = int(flat.row_component[
        (flat.global_rows == int(largest.global_rows[0])).nonzero()[0, 0]])
    theirs = derive_tolerances(lens, build_task_columns(ingestion, lens, largest))
    assert abs(float(mine.b_min[member]) - theirs.b_min) < 1e-15
    assert abs(float(mine.chi2_max[member]) - theirs.chi2_max) < 1e-9
    torch.testing.assert_close(mine.tau_observable[member], theirs.tau_observable,
                               atol=1e-12, rtol=1e-12)
    assert abs(float(mine.tau_closure[member]) - theirs.tau_closure) < 1e-12


# ================================================================= TESTS MARK, NEVER DELETE
def test_no_cell_is_deleted_and_a_refusal_is_kept_with_its_residuals():
    """The whole point. ``blocks.descend`` returned only the final labels; here every node is in
    the table with its measured closure and task residual, and no grade passes a verdict."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["entity"]
    tree = T.build_graded_tree(ingestion, lens)
    proposal = tree.proposal
    sizes = tree.size()
    # every bound row lies under exactly one leaf, and the leaves tile every component
    leaves = torch.nonzero(proposal.left < 0, as_tuple=False).flatten()
    assert int(sizes[leaves].sum()) == tree.flat.rows
    # a node has as many children as its spectrum named (not two): "nothing dropped" is that every
    # inner node's rows are exactly its children's rows (children are a contiguous id block, so a
    # prefix sum over sizes gives each block's total) and that there is one root per component
    prefix = torch.cat([sizes.new_zeros(1), sizes.cumsum(0)])
    inner = proposal.left >= 0
    assert bool((prefix[proposal.right[inner] + 1] - prefix[proposal.left[inner]] == sizes[inner]).all())
    assert int((proposal.parent < 0).sum()) == tree.flat.components
    # THE BUILD PASSES NO VERDICT (packet P3-THE-READ, the author 2026-09-22: "There's no such
    # thing as unresolved - that's why you descend"), so this assertion is now about the
    # QUANTITIES every node carries instead of about a refusal count that no longer exists.
    assert bool(torch.isfinite(tree.node_closure).all())
    assert bool(torch.isfinite(tree.node_task_residual).all())
    assert bool((sizes >= 1).all())
    assert int(tree.receipt.nodes_meeting_their_own_tolerance_at_the_priced_rank) <= proposal.nodes
    assert set(tree.receipt.carried_quantities) >= {
        "task_residual_median", "closure_defect_median", "node_mass_sum",
        "captured_spectral_benefit_at_the_priced_rank"}


def test_the_node_size_distribution_is_a_receipt_field_and_cannot_be_invisible():
    """The r2 judge's finding must never be invisible again (atlas.interface/2 receipt fields)."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["entity"]
    tree = T.build_graded_tree(ingestion, lens)
    payload = tree.receipt.as_dict()
    for field in ("nodes_of_size_one", "nodes_of_size_two_or_more", "largest_node",
                  "rows_under_a_node_of_size_two_or_more", "carried_quantities",
                  "nodes_meeting_their_own_tolerance_at_the_priced_rank",
                  "nodes_by_depth", "objects_per_grade", "rank_distribution", "responses",
                  "peak_device_bytes", "gate_seconds", "rows_unbound"):
        assert field in payload, field
    sizes = tree.size()
    assert payload["nodes_of_size_one"] == int((sizes == 1).sum())
    assert payload["largest_node"] == int(sizes.max())


# =============================================================== the cross counts are B.36
def test_the_cross_counts_between_two_children_equal_a_direct_recount():
    """B.36's block sum, by TWO routes: the LCA walk over ranges, and a direct recount.

    A node now has as many children as its spectrum named, so the quantity compared is the
    node's TOTAL cross count per kind - every edge whose two endpoints lie under the node but
    in DIFFERENT children (its lowest common ancestor is the node) - summed over both recorded
    directions. The per-child-pair block that a join over n children needs is not carried yet
    (banked as a residue for the P3 continuation)."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["entity"]
    tree = T.build_graded_tree(ingestion, lens)
    proposal, flat = tree.proposal, tree.flat
    rank = torch.empty(flat.rows, dtype=torch.int64, device=flat.device)
    rank[proposal.order] = torch.arange(flat.rows, dtype=torch.int64, device=flat.device)
    internal = torch.nonzero(proposal.left >= 0, as_tuple=False).flatten()
    a, b = rank[flat.kind_src], rank[flat.kind_dst]
    checked = 0
    for node in internal[:40].tolist():   # loop-ok: a FIXTURE may walk the node table; the build may not
        children = torch.arange(int(proposal.left[node]), int(proposal.right[node]) + 1, device=flat.device)
        under = (a >= proposal.lo[node]) & (a < proposal.hi[node]) & (b >= proposal.lo[node]) & (b < proposal.hi[node])
        in_a = (a[:, None] >= proposal.lo[children]) & (a[:, None] < proposal.hi[children])
        in_b = (b[:, None] >= proposal.lo[children]) & (b[:, None] < proposal.hi[children])
        same_child = (in_a & in_b).any(dim=1)
        for kind in range(len(flat.kind_names)):
            direct = int(flat.kind_count[under & ~same_child & (flat.kind_id == kind)].sum())
            assert int(tree.node_cross[node, kind].sum()) == direct, (node, kind)
            checked += 1
    assert checked > 0


# ======================================================== BATCHED IS IDENTICAL TO SERIAL
def test_one_padded_batch_is_identical_to_one_component_at_a_time():
    """The batching is a RESOURCE decision: it changes cost, never the accepted set. Driving
    the same build with a one-block share forces the chunk loop to run one block at a time."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["revision"]
    batched = T.build_graded_tree(ingestion, lens)
    original = T.BATCH_SHARE_BYTES
    try:
        T.BATCH_SHARE_BYTES = 8                          # one padded block per chunk
        serial = T.build_graded_tree(ingestion, lens)
    finally:
        T.BATCH_SHARE_BYTES = original
    assert torch.equal(batched.proposal.order, serial.proposal.order)
    assert torch.equal(batched.proposal.lo, serial.proposal.lo)
    assert torch.equal(batched.proposal.hi, serial.proposal.hi)
    assert torch.equal(batched.node_rank, serial.node_rank)
    assert torch.equal(batched.node_stop, serial.node_stop)
    assert torch.equal(batched.node_resolved, serial.node_resolved)
    torch.testing.assert_close(batched.node_closure, serial.node_closure, atol=1e-12, rtol=0)


# ======================================= THE DEMAND TABLE IS GROUPED, NEVER THE WHOLE LENS
def test_parent_groups_bound_the_demand_table_and_change_nothing():
    """The demand table and the two sorts it feeds WERE the peak - the size of the lens, while
    every block of arithmetic downstream was bounded by the declared share. Its entries
    partition by the parent of their ROW, so it is built per parent GROUP. Driving the same
    build with a one-entry budget forces one group per parent, and the node table, the ranks,
    the marks and the closure come out the same numbers."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["revision"]
    original_bytes, original_build = T._DEMAND_ENTRY_BYTES, T._build_register
    counted: list[int] = []

    def counting(*args, **kwargs):
        counted.append(1)
        return original_build(*args, **kwargs)

    try:
        T._build_register = counting
        whole = T.build_graded_tree(ingestion, lens)
        rounds = len(counted)
        counted.clear()
        T._DEMAND_ENTRY_BYTES = T.BATCH_SHARE_BYTES      # budget = ONE demand entry per group
        grouped = T.build_graded_tree(ingestion, lens)
        passes = len(counted)
    finally:
        T._DEMAND_ENTRY_BYTES, T._build_register = original_bytes, original_build
    assert rounds > 0 and passes > rounds                # the grouped path really did split
    assert torch.equal(whole.proposal.order, grouped.proposal.order)
    assert torch.equal(whole.proposal.lo, grouped.proposal.lo)
    assert torch.equal(whole.node_rank, grouped.node_rank)
    assert torch.equal(whole.node_priced_rank, grouped.node_priced_rank)
    assert torch.equal(whole.node_stop, grouped.node_stop)
    assert torch.equal(whole.node_resolved, grouped.node_resolved)
    torch.testing.assert_close(whole.node_closure, grouped.node_closure, atol=1e-12, rtol=0)
    torch.testing.assert_close(whole.node_task_residual, grouped.node_task_residual,
                               atol=1e-12, rtol=0)


# ================================================================== PERSISTED AND RE-READ
def test_a_second_process_reproduces_the_tree_byte_for_byte_with_no_re_grading(tmp_path):
    """"a second PROCESS loads a lens's grades and reproduces them byte for byte with no
    re-grading". The child imports the hive and the reader, never the grading build."""
    ingestion = toy.ingest().ingestion
    lens = toy_lens(ingestion)
    tree = T.build_graded_tree(ingestion, lens)
    hive = CompressedHive(tmp_path / "hive")
    ids = ingestion.store.identity_by_global()
    manifest = T.persist_tree(tree, hive, ids)
    assert manifest["persisted_bytes"] > 0
    first = T.serialise_component(tree, 0, ids)
    child = subprocess.run(  # pool-once: this ONE fixture spawns exactly one child process, to prove a SECOND process reads the hive back
        [sys.executable, "-c",
         "import sys, hashlib, json;"
         f"sys.path.insert(0, {str(Path(__file__).resolve().parents[2] / 'src')!r});"
         "from atlas.store import CompressedHive;"
         "from atlas.grading.tree import deserialise_component, _pack;"
         f"hive = CompressedHive({str(tmp_path / 'hive')!r});"
         f"blob = hive.get({manifest['components'][0]['address']!r});"
         "read = deserialise_component(blob);"
         "print(json.dumps({'sha': hashlib.sha256(blob).hexdigest(),"
         " 'nodes': read['header']['nodes'], 'rows': read['header']['rows'],"
         " 'repack': hashlib.sha256(_pack(read['arrays'],"
         "  {k: v for k, v in read['header'].items() if k != 'arrays'})).hexdigest()}))"],
        capture_output=True, text=True, check=True)
    import hashlib
    import json as _json
    out = _json.loads(child.stdout.strip().splitlines()[-1])
    assert out["sha"] == hashlib.sha256(first).hexdigest()
    assert out["repack"] == out["sha"]                  # the reader re-emits the same bytes
    assert out["nodes"] == int((tree.proposal.component == 0).sum())
    # and the reader never re-graded: it imported no proposal and no register
    assert "build_graded_tree" not in child.stdout


def test_a_persisted_component_stores_no_face_and_only_ranges():
    """atlas.interface/2: "NO typed face is stored per node". The node table is integers."""
    ingestion = toy.ingest().ingestion
    tree = T.build_graded_tree(ingestion, toy_lens(ingestion))
    read = T.deserialise_component(
        T.serialise_component(tree, 0, ingestion.store.identity_by_global()))
    names = {entry["name"] for entry in read["header"]["arrays"]}
    assert {"lo", "hi", "parent", "left", "right", "cut_mode", "closure", "stop",
            "cross", "rank"} <= names
    assert not any("face" in name or "histogram" in name for name in names)
    assert read["header"]["face_storage"].startswith("NONE")
    assert read["arrays"]["lo"].dtype == torch.int32
    assert read["arrays"]["closure"].dtype == torch.float32


# ============================================================================== O(diff)
def test_a_change_reranks_only_the_components_it_touches():
    """B.29 at component granularity: the rank is (component, local), so a change re-ranks the
    components it touches and no others. The claim is measured, never assumed."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["entity"]
    tree = T.build_graded_tree(ingestion, lens)
    one = tree.flat.global_rows[0:1]
    reading = tree.reranked_components(one) if hasattr(tree, "reranked_components") \
        else T.reranked_components(tree, one)
    assert reading["components_reranked"] >= 1
    assert reading["components_reranked"] < reading["components_total"]
    assert reading["nodes_reranked"] < reading["nodes_total"]
    whole = T.reranked_components(tree, tree.flat.global_rows)
    assert whole["components_reranked"] == whole["components_total"]


# ============================================================================== refusals
def test_a_register_declaration_without_a_derivation_is_refused_by_name():
    with pytest.raises(LensRefusal) as caught:
        RegisterDeclaration(1, "", 1.0, 1.0, "w", 64.0, "s", 1e-7, "t", 0.5, "p")
    assert caught.value.refusal == "REGISTER-ROW-UNDERIVED"
    with pytest.raises(LensRefusal) as caught:
        RegisterDeclaration(-1, "d", 1.0, 1.0, "w", 64.0, "s", 1e-7, "t", 0.5, "p")
    assert caught.value.refusal == "REGISTER-RANK-CAP-NEGATIVE"
    with pytest.raises(LensRefusal) as caught:
        RegisterDeclaration(1, "d", 1.0, 1.0, "w", 64.0, "s", 1e-7, "t", 0.5, "")
    assert caught.value.refusal == "REGISTER-ROW-UNDERIVED"
    with pytest.raises(LensRefusal) as caught:
        RegisterDeclaration(1, "d", 1.0, 1.0, "w", 64.0, "s", 1e-7, "t", -1.0, "p")
    assert caught.value.refusal == "REGISTER-RANK-PRICE-NEGATIVE"


def test_the_rank_cap_is_a_declared_row_carrying_its_own_provenance():
    ingestion = toy.ingest().ingestion
    declared = toy_lens(ingestion).register_declaration()
    assert declared.hidden_rank_cap == len(toy_lens(ingestion).task_columns())
    assert "OVERTURNED BY" in declared.rank_cap_derivation
    assert "L11" in declared.family_weight_derivation


# ============================================================== THE RANK IS PRICED, NOT CAPPED
def _priced_demand(sigmas: tuple[float, ...]):
    """A one-parent state whose demand spectrum IS the given singular values, exactly.

    The law-boundary demand of a whole reversible component against its own constant is zero
    (L root = 0), so the demand block is the task block alone: three whitened task columns made
    orthonormal in the reference metric and then scaled, which puts the declared numbers on the
    diagonal of the local demand Gram with nothing to interpret.
    """
    n = 4
    operator, root = _reset_law(n, gamma=0.9)
    base = torch.tensor([[1.0, 0.0, 1.0], [-1.0, 0.0, 1.0],
                         [0.0, 1.0, -1.0], [0.0, -1.0, -1.0]],
                        device="cuda", dtype=torch.float64)
    columns = root[:, None] * base                       # whitened, each column zero-mean
    columns = columns / columns.norm(dim=0, keepdim=True)
    tasks = columns * torch.tensor(sigmas, device="cuda", dtype=torch.float64)[None, :]
    labels = torch.zeros(n, device="cuda", dtype=torch.int64)
    return operator, root, tasks, labels


def _priced_round(sigmas, price):
    operator, root, tasks, labels = _priced_demand(sigmas)
    state, columns, tolerances = T.dense_state(operator, root, tasks, walk_horizon=1)
    return T.up_round(state, labels, register=_register(len(sigmas), price), horizon=1,
                      columns=columns, tolerances=tolerances, rank=None)


def test_the_priced_rank_is_the_argmin_of_remaining_demand_plus_the_cost_table():
    """section_synthesis sec 5: c(r) selects the MINIMUM of Jbar(0) - 1/2 sum eta_i + c(r).

    sigma = (1, 1/2, 1/5), so the remaining demand is (1.29, 0.29, 0.04, 0) at r = 0..3 and
    c(r) = lambda log r is (0, 0, 0.6931 lambda, 1.0986 lambda). Every expected rank below is
    that argmin computed by hand. The singular values are the declared ones to machine
    precision, so this is arithmetic, not a threshold.
    """
    sigmas = (1.0, 0.5, 0.2)
    free = _priced_round(sigmas, 0.0)
    torch.testing.assert_close(free["singular"][0],
                               torch.tensor(sigmas, device="cuda", dtype=torch.float64))
    assert int(free["retained"][0]) == 3                 # the capacity bound alone
    assert int(free["priced"][0]) == 3                   # description free: the price binds not
    assert int(free["rank"][0]) == 3                     # rank=None takes the PRICED rank

    assert int(_priced_round(sigmas, 0.15)["priced"][0]) == 2
    assert int(_priced_round(sigmas, 0.3)["priced"][0]) == 2
    assert int(_priced_round(sigmas, 0.6)["priced"][0]) == 1
    # the capacity bound never moves with the price: it is the device's bound, not taste
    assert int(_priced_round(sigmas, 0.6)["retained"][0]) == 3


def test_the_price_is_monotone_and_halving_or_doubling_lambda_moves_the_rank_one_way():
    """Doubling the exchange rate can only remove directions; halving can only add them."""
    sigmas = (1.0, 0.5, 0.2)
    ladder = [(0.0, 3), (0.001, 3), (0.15, 2), (0.3, 2), (0.6, 1), (2.0, 1)]
    seen = [int(_priced_round(sigmas, price)["priced"][0]) for price, _ in ladder]
    assert seen == [rank for _, rank in ladder]
    assert all(later <= earlier for earlier, later in zip(seen, seen[1:]))


def test_the_total_cost_argmin_is_the_document_and_it_differs_from_a_greedy_per_direction_test():
    """WHERE THE BRIEF AND THE DOCUMENTS DISAGREE, THE DOCUMENTS WIN - demonstrated.

    The brief's addendum reads the rule per direction ("the r-th direction is retained while
    its captured demand exceeds lambda log r"). section_synthesis sec 5 states it as the argmin
    of the TOTAL cost, and the two differ whenever a later direction is cheap at the margin
    (log(r/(r-1)) shrinks with r) while the greedy test has already stopped. At lambda = 0.05
    with sigma = (1, 1/2, 1/5) the greedy reading stops at 2 - 0.04 < 0.05 log 3 = 0.0549 - and
    the document's argmin takes 3, because the total 0 + 0.0549 beats 0.04 + 0.0347.
    """
    import math
    sigmas = (1.0, 0.5, 0.2)
    energy = [s * s for s in sigmas]
    price = 0.05

    greedy = 0
    for r in (1, 2, 3):
        if not energy[r - 1] > price * math.log(r):
            break
        greedy += 1
    total = sum(energy)
    objective = [total - sum(energy[:r]) + price * math.log(max(r, 1)) for r in range(4)]
    argmin = min(range(4), key=lambda r: objective[r])
    assert greedy == 2 and argmin == 3          # the two readings genuinely disagree here
    assert int(_priced_round(sigmas, price)["priced"][0]) == argmin

    # and everywhere else the built rank IS that argmin, computed by hand from the spectrum
    for price in (0.0, 0.15, 0.3, 0.6, 2.0):
        objective = [total - sum(energy[:r]) + price * math.log(max(r, 1)) for r in range(4)]
        expected = min(range(4), key=lambda r: objective[r])
        assert int(_priced_round(sigmas, price)["priced"][0]) == expected


def test_the_rank_price_is_a_declared_row_read_off_the_lens_own_answer_precision():
    import math
    lens = toy_lens(toy.ingest().ingestion)
    declared = lens.register_declaration()
    epsilon = min(q.answer_precision for q in lens.questions)
    assert declared.rank_price_lambda == pytest.approx(epsilon ** 2 / math.log(2.0))
    assert "log r" in declared.rank_price_derivation
    assert "OVERTURNED BY" in declared.rank_price_derivation
    # the cap is only the capacity bound, and says so
    assert "capacity bound" in declared.rank_price_derivation
    # re-declaring the rate moves the LENS HASH: two rates are two declarations
    doubled = lens.priced_at(2.0, "the sensitivity of the stopping rule, reported by B1")
    assert doubled.register_declaration().rank_price_lambda == 2 * declared.rank_price_lambda
    assert doubled.lens_hash() != lens.lens_hash()


def test_the_receipt_carries_the_price_and_what_it_did_to_the_ranks():
    ingestion = toy.ingest().ingestion
    lens = toy_lens(ingestion)
    tree = T.build_graded_tree(ingestion, lens)
    receipt = tree.receipt.as_dict()
    assert receipt["rank_price_lambda"] == lens.register_declaration().rank_price_lambda
    assert sum(receipt["priced_rank_distribution"].values()) == receipt["nodes_total"]
    assert sum(receipt["capacity_rank_distribution"].values()) == receipt["nodes_total"]
    # every node's kept rank is its priced rank unless the TOLERANCE bought more, and never
    # more than the capacity bound
    bought = tree.node_rank > tree.node_priced_rank
    assert int(bought.sum()) == receipt["nodes_where_the_tolerance_bought_rank_above_the_price"]
    assert bool((tree.node_rank <= tree.node_capacity_rank).all())
    assert int((tree.node_priced_rank < tree.node_capacity_rank).sum()) == \
        receipt["nodes_the_price_held_below_capacity"]


def test_pricing_the_rank_never_deletes_a_node_it_only_moves_the_mark():
    """The whole point of the wave: a refusal MARKS. Pricing must not shrink the tree."""
    ingestion = toy.ingest().ingestion
    lens = toy_lens(ingestion)
    cheap = T.build_graded_tree(ingestion, lens.priced_at(0.0, "description free"))
    dear = T.build_graded_tree(ingestion, lens.priced_at(1e6, "description ruinous"))
    assert cheap.receipt.nodes_total == dear.receipt.nodes_total
    assert cheap.receipt.rows_bound == dear.receipt.rows_bound
    torch.testing.assert_close(cheap.proposal.lo, dear.proposal.lo)
    torch.testing.assert_close(cheap.proposal.hi, dear.proposal.hi)
    assert int(dear.node_priced_rank.max()) <= int(cheap.node_priced_rank.max())
    # and a node the price refuses to widen is KEPT, with its measured residuals: the build
    # deletes no node and marks none, so every node of the tree carries its quantities
    assert dear.receipt.nodes_total == int(dear.node_closure.numel())
    assert float(dear.receipt.carried_quantities["node_mass_sum"]) > 0.0


# ============================== TWO DEFECTS OF THE FIRST PASS, DEMONSTRATED AND THEN CLOSED
def test_a_mode_entry_at_ulp_scale_cannot_decide_a_cut_and_the_sign_is_canonical():
    """The proposal must be a property of the OPERATOR, not of the batch the solver saw.

    An eigenvector carries two things the operator does not fix: its overall sign, and the side
    an entry of size ulp falls on. Both reached the node table through ``side = vector >= 0``,
    and both move with the batch - measured on the LongMemEval semantic lens, where one padded
    batch and one block at a time gave 960 and 962 nodes. Here: the mode's largest entry is
    positive, entries below the DECLARED support floor are exactly zero, and a real distinction
    is nowhere near that floor.
    """
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["entity"]
    flat = T.build_flat_carrier(ingestion, lens)
    declared = lens.register_declaration()
    floor_multiple = declared.support_floor_eps_multiple
    modes, _, count, _, tied = T._component_modes(
        flat, 1.0 / lens.walk_horizon, floor_multiple, declared.tie_relative_tolerance)

    absolute = modes.abs()
    width = modes.shape[1]
    index = flat.row_component[:, None].expand(flat.rows, width)
    peak = torch.zeros((flat.components, width), dtype=torch.float64, device=modes.device)
    peak.scatter_reduce_(0, index, absolute, reduce="amax", include_self=True)
    live = peak[flat.row_component] > 0
    # the FIRST largest entry of every mode is POSITIVE (a tie takes the lowest position):
    # the sign is the operator's, not the solver's
    positions = torch.arange(flat.rows, device=modes.device)[:, None].expand(flat.rows, width)
    first = torch.full((flat.components, width), flat.rows, dtype=torch.int64,
                       device=modes.device)
    first.scatter_reduce_(0, index,
                          torch.where(live & (absolute >= peak[flat.row_component])
                                      & (absolute > 0), positions,
                                      torch.full_like(positions, flat.rows)),
                          reduce="amin", include_self=True)
    chosen = first < flat.rows
    assert bool(chosen.any())
    assert bool((modes.gather(0, first.clamp(max=flat.rows - 1))[chosen] > 0).all())
    # nothing survives inside the floor, and nothing real is anywhere near it
    floor = floor_multiple * torch.finfo(torch.float64).eps
    kept = absolute[absolute > 0]
    assert float(kept.min()) >= floor
    assert float(kept.min()) > 1e3 * floor    # the gap the floor sits in, on this record
    raw, _, _, _, _ = T._component_modes(flat, 1.0 / lens.walk_horizon, 0.0,
                                        declared.tie_relative_tolerance)
    raw_absolute = raw.abs()
    assert int(((raw_absolute > 0) & (raw_absolute < floor)).sum()) > 0   # it did have noise


def test_the_grades_are_proposed_from_the_transported_operator_at_every_grade():
    """A9: the recursion proposes EACH GRADE's cells from that grade's own transported operator.

    WHAT THIS REPLACES, and why the old test is deleted rather than repaired:
    ``test_response_two_replaces_one_level_and_does_not_collapse_the_subtree`` asserted the
    behaviour of ``propose_ranges`` and of the sign-pattern bisection with a per-level recut
    override. Packet P3-THE-READ's step A9 REJECTS that proposal shape by name ("a binary
    sign-pattern bisection ... is REJECTED as the proposal shape") and removed the function, so
    its assertions are assertions about a construction this campaign has ruled against. They are
    deleted with their reason rather than kept as a file that calls a symbol no longer in the
    tree (packet P3-THE-READ, D9).

    What replaces them is the property A9 actually asks for: the cell COUNT at each grade is set
    by that grade's own surviving spectrum, so the grades' node counts FALL and the sizes RISE,
    and no grade is a doubling of the one below it.
    """
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["provenance"]
    tree = T.build_graded_tree(ingestion, lens)
    grades = tree.node_grade
    sizes = tree.size()
    counts = []
    means = []
    for grade in range(int(grades.max()) + 1):  # loop-ok: the GRADES of this lens, ~log M
        at = grades == grade
        if not int(at.sum()):
            continue
        counts.append(int(at.sum()))
        means.append(float(sizes[at].double().mean()))
    assert len(counts) >= 2, counts
    # the recursion climbs: each grade holds fewer, larger objects than the one below it
    assert counts == sorted(counts, reverse=True), counts
    assert means == sorted(means), means
    # and the tree is whole: every row lies under exactly one leaf
    leaves = torch.nonzero(tree.proposal.left < 0, as_tuple=False).flatten()
    assert int(sizes[leaves].sum()) == tree.flat.rows
    # the bisection is gone: no symbol of it remains on the module
    assert not hasattr(T, "propose_ranges")
    assert hasattr(T, "propose_grade_cells")


# ==================================== THE DECLARED ARITHMETIC AND THE BOUNDS IT LIVES UNDER
def test_the_arithmetic_of_the_device_is_a_declared_row_with_its_own_provenance():
    """The SVD driver and the deterministic kernels are a resource ROW, not a call-site kwarg:
    an undeclared driver made two processes on the same rows accept different node sets. The
    row carries its own reason, provenance and the measurement that forced it, and the receipt
    of every grading run reports it - so a reader of a persisted grading can see which
    arithmetic produced it."""
    row = T.DEVICE_ARITHMETIC
    assert row.svd_driver == "gesvd"                     # the QR driver: no iteration to fail
    assert row.deterministic_algorithms is True
    for field in ("because", "provenance", "measured"):
        assert len(getattr(row, field)) > 40, field
    assert row.hashed().startswith("sha256:")
    applied = T.pin_device_arithmetic()
    assert applied["svd_driver"] == row.svd_driver
    assert applied["declaration"] == row.hashed()
    assert torch.are_deterministic_algorithms_enabled()
    ingestion = toy.ingest().ingestion
    receipt = T.build_graded_tree(ingestion, toy_lens(ingestion)).receipt.as_dict()
    assert receipt["device_arithmetic"]["declaration"] == row.hashed()


def test_two_processes_grade_one_lens_to_the_same_last_digit():
    """"does a regrade reproduce" - across PROCESSES, which is the only reading that matters
    for a record. Two children grade the engine's revision lens from the record and print the
    acceptance, the ranks and the float64 sums with repr, so the comparison includes the last
    digit. Before the declared arithmetic this test failed on the entity lens with 302 against
    314 accepted nodes."""
    driver = (Path(__file__).resolve().parents[1].parent / "evidence" / "ATLAS_PROGRAMME"
              / "waves" / "J1-join" / "B1" / "reproduces.py")
    assert driver.is_file()
    readings = []
    for _ in range(2):  # loop-ok: the two declared processes of this check
        child = subprocess.run(  # pool-once: two children, one per declared reading, in this one fixture
            [sys.executable, str(driver), "--one", "engine/revision"],
            capture_output=True, text=True, check=True)
        readings.append(child.stdout.strip().splitlines()[-1])
    assert readings[0] == readings[1], readings
    import json as _json
    first = _json.loads(readings[0])
    assert (first["nodes_meeting_their_own_tolerance_at_the_priced_rank"] >= 0
            and first["nodes_total"] > 0)
    assert first["device_arithmetic"]["svd_driver"] == T.DEVICE_ARITHMETIC.svd_driver


def test_the_bounded_sort_sums_by_key_exactly_as_unique_and_index_add_do():
    """The reduction every expansion chunk ends in. One sort and a segment reduction hold 40
    bytes an entry where ``unique(return_inverse=True)`` plus ``index_add_`` hold 113; the
    partition must be the SAME partition, and the values must agree to float64 rounding."""
    device = torch.device("cuda")
    generator = torch.Generator(device=device).manual_seed(11)
    key = torch.randint(0, 997, (200_000,), dtype=torch.int64, device=device,
                        generator=generator)
    value = torch.rand(200_000, dtype=torch.float64, device=device, generator=generator)
    mine, summed = T._sum_by_key(key, value)
    unique, inverse = torch.unique(key, sorted=True, return_inverse=True)
    reference = torch.zeros(unique.numel(), dtype=torch.float64, device=device)
    reference.index_add_(0, inverse, value)
    assert torch.equal(mine, unique)
    torch.testing.assert_close(summed, reference, atol=1e-11, rtol=0)


def test_the_defect_row_blocks_and_the_chunk_merge_change_nothing():
    """The stage defect is the largest table of a round - one L_next entry expands into as many
    entries as its column's parent owns coordinates - and its ROWS are cut into blocks of the
    declared share, sized by the expansion counted exactly. Driving the same build with a
    one-entry share forces one block per row and the smallest possible chunk, and the node
    table, the ranks, the marks and the closure come out the same numbers."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["provenance"]
    whole = T.build_graded_tree(ingestion, lens)
    original = T.EXPANSION_ENTRY_BYTES
    try:
        # a share of 4,096 entries instead of 3.7 million: many blocks and many chunks per
        # block, which is the condition under test. A share of ONE entry would also be correct
        # arithmetic and is not used, because a per-entry sort is the very thing this file
        # refuses to write - a test must not measure a path no run can take.
        T.EXPANSION_ENTRY_BYTES = T.DENSE_SHARE_BYTES // 4096
        blocked = T.build_graded_tree(ingestion, lens)
    finally:
        T.EXPANSION_ENTRY_BYTES = original
    assert torch.equal(whole.proposal.lo, blocked.proposal.lo)
    assert torch.equal(whole.node_rank, blocked.node_rank)
    assert torch.equal(whole.node_resolved, blocked.node_resolved)
    assert torch.equal(whole.node_stop, blocked.node_stop)
    torch.testing.assert_close(whole.node_closure, blocked.node_closure, atol=1e-11, rtol=0)


# ============================================ PERSISTENCE: THE BARRIER, NOT THE ADDRESS
def test_batching_the_durability_keeps_every_content_address_and_one_barrier(tmp_path):
    """Persistence cost 15.7x the grading it stored, and all of it was fsync: the hive's own
    ``put`` makes each blob durable on its own (store.py:141 and :143, two fsyncs a blob). The
    CONTENT ADDRESS per component is the unit of change and is kept; only the BARRIER moves to
    one per lens. The two modes must agree address for address and byte for byte, and every
    blob must still read back through the hive's own verified ``get``."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["provenance"]
    tree = T.build_graded_tree(ingestion, lens)
    ids = ingestion.store.identity_by_global()
    batched = T.persist_tree(tree, CompressedHive(tmp_path / "b"), ids, durability="batched")
    per_blob = T.persist_tree(tree, CompressedHive(tmp_path / "p"), ids, durability="per-blob")
    assert ([entry["address"] for entry in batched["components"]]
            == [entry["address"] for entry in per_blob["components"]])
    assert batched["persisted_bytes"] == per_blob["persisted_bytes"]
    assert batched["persist_receipt"]["durable_syncs"] == 1
    assert per_blob["persist_receipt"]["fsync_calls"] == 2 * tree.flat.components
    hive = CompressedHive(tmp_path / "b")
    index = T._persist_index(tree)
    for entry in batched["components"]:  # loop-ok: every component of this small lens, which is the point of the check
        assert hive.get(entry["address"]) == T.serialise_component(
            tree, entry["component"], ids, index=index)


def test_the_persist_index_is_the_same_bytes_as_the_per_component_scan(tmp_path):
    """``serialise_component`` used to scan the whole lens for each component it wrote. The
    grouping is built once; the bytes must not move."""
    ingestion = engine_rows.ingest()
    lens = engine_lenses(ingestion, ingestion.fold.supersession_depth)["revision"]
    tree = T.build_graded_tree(ingestion, lens)
    index = T._persist_index(tree)
    ids = ingestion.store.identity_by_global()
    for component in (0, 1, tree.flat.components - 1):  # loop-ok: three declared components
        assert (T.serialise_component(tree, component, ids, index=index)
                == T.serialise_component(tree, component, ids))
    assert int(index.node_ptr[-1]) == tree.proposal.nodes
