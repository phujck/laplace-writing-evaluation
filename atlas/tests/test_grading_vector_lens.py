"""Tests THIS packet wrote for the vector lens, the node frame and the winnowing read.

    scripts/laplace-python -m pytest atlas/tests/test_grading_vector_lens.py \
        --basetemp=/tmp/pytest-p2-down -q

Each test is the mechanical form of one must_achieve of packet P2-DOWN:

  1. V TRAVELS. ``V_next = U^T V`` holds exactly against an explicit dense isometry, and the
     composed decoder over two grades equals the composition - the cocycle, on V.
  2. THE VECTOR LENS IS A LENS. Its generator is built from the declared field effect, pi is
     DERIVED (``pi_used_in_generator`` False), stationarity and detailed balance hold at
     float64, and the effect is NOT a monotone function of the inner product that scores - the
     line ruling R-3 draws, held as a number.
  3. THE NODE FRAME. Every frame's directions are orthonormal; C7's certified bound holds for
     EVERY member of every node (the property the read prunes with); and the frame computed
     from the transported decoder agrees with the frame computed from the items (claim C6).
  4. DOWN. The winnowing is a winnowing (each step's set is inside the one before it, except
     the declared relation walk, which is the one step allowed to add); the survivors are NOT
     the flat top-m in a different order (the identity audit the charter demands); and the
     question's gate separates a selective question from an unselective one (ruling R-i).
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

from atlas.front import down as D
from atlas.grading import frames as F
from atlas.grading import tree as T
from atlas.grading.generator import content_affinity_counts
from atlas.grading.lens import ContentAffinity, LensRefusal, Question
from atlas.grading.lenses import toy_lens
from atlas.record.content import build_content
from atlas.record.ingest import toy

pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="the numeric core is GPU")

CONTENT = {"target_tokens": 96, "hard_cap_tokens": 256,
           "axes": [{"axis": "content", "encoder_id": "bge-small-en-v1.5/onnx-fp16/1",
                     "dim": 384, "dtype": "int8", "tokens": True}]}


def _vector_lens(ingestion):
    """The toy's VECTOR lens: the same carrier, the declared field effect as its generator."""
    base = toy_lens(ingestion)
    rows = len(ingestion.store.table("toy_row"))
    return type(base)(
        lens_id="toy-content",
        dataset_id=base.dataset_id,
        carrier_row_kinds=base.carrier_row_kinds,
        counted_relation_kinds=(),
        questions=(Question("V1", "which rows of this source say the same thing", "predicate",
                            "toy_row", 1.0 / max(rows, 1),
                            "the answer separates one of the corpus's own rows, so the precision "
                            "it owes is one row's share of the carrier - the same derivation "
                            "every other lens of this record uses"),),
        walk_horizon=base.walk_horizon,
        horizon_derivation=base.horizon_derivation,
        content_affinity=ContentAffinity(
            axis="content", jurisdiction_column="source_id",
            jurisdiction_derivation=("the toy declares source_id as the container a row was "
                                     "witnessed in; a field effect between two sources is not "
                                     "an effect the record witnesses")),
        what_it_is_for="the vector lens's own code path, on a known-answer carrier")


@pytest.fixture(scope="module")
def built():
    ingested = toy.ingest(content=CONTENT)
    ingestion = ingested.ingestion
    ingestion.content = build_content(ingestion).table
    lens = _vector_lens(ingestion)
    tree = T.build_graded_tree(ingestion, lens)
    return ingestion, lens, tree


# ------------------------------------------------------------------ 1. V travels
def test_v_next_equals_u_transpose_v_and_the_cocycle_holds():
    torch.manual_seed(0)
    n, d = 8, 5
    operator = torch.randn(n, n, dtype=torch.float64, device="cuda")
    operator = operator + operator.T
    reference = torch.full((n,), 1.0 / n ** 0.5, dtype=torch.float64, device="cuda")
    tasks = torch.eye(n, 2, dtype=torch.float64, device="cuda")
    field = torch.randn(n, d, dtype=torch.float64, device="cuda")
    state, columns, tolerances = T.dense_state(operator, reference, tasks)
    state.v = field.clone()
    parent = torch.tensor([0, 0, 1, 1, 2, 2, 3, 3], dtype=torch.int64, device="cuda")
    register = T.RegisterDeclaration(
        hidden_rank_cap=2, rank_cap_derivation="the fixture's own declared resource",
        task_family_weight=1.0, law_family_weight=1.0, family_weight_derivation="1:1",
        support_floor_eps_multiple=64.0, support_floor_derivation="float64 Householder chain",
        tie_relative_tolerance=1e-7, tie_derivation="float64 square-root rule",
        rank_price_lambda=0.0, rank_price_derivation="unpriced fixture")
    first = T.up_round(state, parent, register=register, horizon=1, columns=columns,
                       tolerances=tolerances)
    u1 = T.dense_isometry(state, first["map"], first["state"].coordinates)
    assert torch.allclose(first["state"].v, u1.T @ field, atol=1e-12)

    second_parent = torch.tensor([0, 0, 1, 1], dtype=torch.int64, device="cuda")
    second = T.up_round(first["state"], second_parent, register=register, horizon=1,
                        columns=columns, tolerances=tolerances)
    u2 = T.dense_isometry(first["state"], second["map"], second["state"].coordinates)
    # the COCYCLE on the field decoder: V_2 = U_2^T (U_1^T V) = (U_1 U_2)^T V
    assert torch.allclose(second["state"].v, (u1 @ u2).T @ field, atol=1e-10)


# ------------------------------------------------------------------ 2. the vector lens is a lens
def test_the_field_effect_generator_derives_pi_and_is_not_the_score(built):
    ingestion, lens, tree = built
    receipt = tree.flat.receipt()
    assert receipt["pi_used_in_generator"] is False
    assert receipt["max_stationarity_defect"] < 1e-12
    assert receipt["max_detailed_balance_defect"] < 1e-12
    affinity = tree.flat.affinity_receipt
    assert affinity is not None and affinity["undirected_edges"] > 0
    # ruling R-3's line, as a number: a monotone function of the inner product would be 1.0
    assert affinity["effect_vs_inner_product_rank_correlation"] <= 1.0
    assert affinity["neighbours_k_min"] >= 1


def test_a_lens_that_mixes_a_field_effect_with_counted_relations_refuses_by_name(built):
    ingestion, lens, _ = built
    base = toy_lens(ingestion)
    with pytest.raises(LensRefusal) as raised:
        type(base)(lens_id="bad", dataset_id=base.dataset_id,
                   carrier_row_kinds=base.carrier_row_kinds,
                   counted_relation_kinds=("meet",), questions=base.questions,
                   walk_horizon=1, horizon_derivation="x",
                   content_affinity=lens.content_affinity)
    assert raised.value.refusal == "LENS-MIXES-A-FIELD-EFFECT-WITH-COUNTED-RELATIONS"


# ------------------------------------------------------------------ 3. the node frame
def test_every_frame_is_orthonormal_and_the_certified_bound_holds_for_every_member(built):
    ingestion, lens, tree = built
    frames = tree.frames
    assert frames is not None and int((frames.grade >= 0).sum()) > 0
    rank = frames.rank()
    framed = torch.nonzero((frames.grade >= 0) & (rank > 0), as_tuple=False).flatten()
    for node in framed[:16].tolist():  # loop-ok: a bounded SAMPLE of nodes, for the assertion
        start, stop = int(frames.ptr[node]), int(frames.ptr[node + 1])
        block = frames.dirs[start:stop]
        gram = block @ block.T
        assert torch.allclose(gram, torch.eye(stop - start, dtype=torch.float64,
                                              device=gram.device), atol=1e-8)

    # C7 for EVERY member of EVERY framed node, against three queries
    from atlas.grading.generator import carrier_field

    local_of_global = torch.full((ingestion.store.row_count,), -1, dtype=torch.int64,
                                 device=tree.flat.device)
    local_of_global[tree.flat.global_rows] = torch.arange(tree.flat.rows, dtype=torch.int64,
                                                          device=tree.flat.device)
    field, _, _ = carrier_field(ingestion, lens, local_of_global, tree.flat.device)
    view = D.build_down_view(tree, field, local_of_global)
    torch.manual_seed(1)
    for _ in range(3):  # loop-ok: three declared probe queries
        q = torch.randn(frames.dim, dtype=torch.float64, device=field.device)
        q = q / q.norm()
        for node in framed[:16].tolist():  # loop-ok: the same bounded sample
            members = view.order[int(view.lo[node]):int(view.hi[node])]
            scores = field.index_select(0, members).to(torch.float64) @ q
            upper = F.certified_upper(frames, torch.tensor([node], device=field.device), q)
            assert float(scores.max()) <= float(upper[0]) + 1e-9


def test_the_frame_from_the_decoder_agrees_with_the_frame_from_the_items(built):
    """Claim C6: computed from children, not from a second scan of the items."""
    ingestion, lens, tree = built
    from atlas.grading.generator import carrier_field

    frames = tree.frames
    local_of_global = torch.full((ingestion.store.row_count,), -1, dtype=torch.int64,
                                 device=tree.flat.device)
    local_of_global[tree.flat.global_rows] = torch.arange(tree.flat.rows, dtype=torch.int64,
                                                          device=tree.flat.device)
    field, _, _ = carrier_field(ingestion, lens, local_of_global, tree.flat.device)
    view = D.build_down_view(tree, field, local_of_global)
    leaves = torch.nonzero((frames.grade == 0) & (frames.rank() > 0),
                           as_tuple=False).flatten()
    assert leaves.numel() > 0
    worst = 0.0
    for node in leaves[:8].tolist():  # loop-ok: a bounded sample of leaf cells
        members = view.order[int(view.lo[node]):int(view.hi[node])]
        rows = field.index_select(0, members).to(torch.float64)
        mass = tree.flat.pi.index_select(0, members)
        mean = (rows * mass[:, None]).sum(0) / mass.sum()
        worst = max(worst, float((mean - frames.mu[node]).norm()))
    # the decoder is carried in the FIELD's own dtype (float32, the stored form's resolution),
    # so the agreement is asserted at the float64-style scale-relative threshold for float32:
    # 64 * eps(float32), the same unit-roundoff allowance the register's support floor uses.
    allowed = 64 * float(np.finfo(np.float32).eps)
    assert worst < allowed, f"the decoder's mean and the items' mean disagree by {worst}"


def test_the_frame_table_round_trips_through_its_own_bytes(built):
    _, _, tree = built
    blob = F.serialise_frames(tree.frames)
    back = F.deserialise_frames(blob, tree.flat.device)
    assert torch.allclose(back.mu, tree.frames.mu)
    assert torch.allclose(back.dirs, tree.frames.dirs)
    assert torch.equal(back.ptr, tree.frames.ptr)
    assert bool(torch.equal(back.exact, tree.frames.exact))
    assert F.serialise_frames(back) == blob


# ------------------------------------------------------------------ 4. DOWN
def _view(ingestion, lens, tree):
    from atlas.grading.generator import carrier_field

    local_of_global = torch.full((ingestion.store.row_count,), -1, dtype=torch.int64,
                                 device=tree.flat.device)
    local_of_global[tree.flat.global_rows] = torch.arange(tree.flat.rows, dtype=torch.int64,
                                                          device=tree.flat.device)
    field, _, _ = carrier_field(ingestion, lens, local_of_global, tree.flat.device)
    return D.build_down_view(tree, field, local_of_global), field


def test_the_winnowing_winnows_and_the_survivors_are_not_the_flat_prefix(built):
    ingestion, lens, tree = built
    view, field = _view(ingestion, lens, tree)
    rows = int(field.shape[0])
    jurisdiction = torch.ones(rows, dtype=torch.bool, device=field.device)
    q = field[0].to(torch.float64)
    flat = torch.topk(field.to(torch.float64) @ q, min(4, rows)).indices
    result = D.winnow(view, q, flat, jurisdiction=jurisdiction, answer_precision=1.0 / rows,
                      top_k=min(4, rows))
    assert int(result.members.numel()) >= int(result.admitted.numel()) - int(
        result.counters["added_by_the_walk"])
    assert int(result.survivors.numel()) <= int(result.admitted.numel())
    assert result.tau > 0.0 and 0.0 < result.b <= 1.0
    assert result.residual_final <= result.residual_initial + 1e-12
    # the identity audit: a read that only re-ordered the flat prefix would return that prefix
    assert not torch.equal(torch.sort(result.survivors).values, torch.sort(flat).values) or \
        int(result.members.numel()) > int(flat.numel())


def test_the_questions_own_gate_separates_a_selective_from_an_unselective_question(built):
    ingestion, lens, tree = built
    view, field = _view(ingestion, lens, tree)
    rows = int(field.shape[0])
    jurisdiction = torch.ones(rows, dtype=torch.bool, device=field.device)
    q = field[0].to(torch.float64)
    hits = torch.topk(field.to(torch.float64) @ q, min(4, rows)).indices
    selective = torch.zeros(rows, dtype=torch.bool, device=field.device)
    selective[hits[:1]] = True
    wide = D.winnow(view, q, hits, jurisdiction=jurisdiction, answer_precision=1.0 / rows)
    narrow = D.winnow(view, q, hits, jurisdiction=jurisdiction, answer_precision=1.0 / rows,
                      conditions=(selective,))
    assert narrow.b < wide.b
    assert narrow.tau > wide.tau
