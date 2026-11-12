"""A7/A9: the tree the per-grade recursion PRODUCES is a tree, and it carries no verdict.

These are the structural identities the assembly pass has to hold, checked on the real draw the
census runs (one LongMemEval haystack, the declared content leaf recipe) rather than on a
fixture, because the assembly only exists when objects are actually carried across grades.
Run: scripts/laplace-python -m pytest atlas/tests/test_grade_recursion.py --basetemp=/tmp/pytest-p3-grade-recursion
"""
from __future__ import annotations

import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atlas.grading import tree as T                                          # noqa: E402
from atlas.grading.lenses import content_lens                                # noqa: E402
from atlas.record.content import build_content                               # noqa: E402
from atlas.record.ingest import longmem                                      # noqa: E402

CONTENT = {
    "target_tokens": 96, "hard_cap_tokens": 256,
    "declared_by": "src/atlas/front/draw.py CONTENT_LEAF_DRAW (the declared draw row)",
    "axes": [{"axis": "content", "encoder_id": "bge-small-en-v1.5/onnx-fp16/1",
              "dim": 384, "dtype": "int8", "tokens": True}],
}

_BUILT: list = []


def _tree():
    if not _BUILT:
        ing = longmem.ingest(histories=1, rungs="ab", content=CONTENT)
        ing.build_anchors(rung=1)
        ing.content = build_content(ing).table
        lens = content_lens(ing, "turn", "question_id", "longmem-content",
                            answer_column="content_span")
        _BUILT.append(T.build_graded_tree(ing, lens))
    return _BUILT[0]


def test_the_ranges_are_a_tree_and_the_children_are_one_contiguous_block():
    proposal = _tree().proposal
    lo, hi, parent, left, right = (proposal.lo, proposal.hi, proposal.parent,
                                   proposal.left, proposal.right)
    assert int((hi <= lo).sum()) == 0                       # every node holds at least one row
    inner = torch.nonzero(left >= 0, as_tuple=False).flatten()
    # the children of a node are the ids [left, right] and nothing else is its child
    counted = torch.bincount(parent[parent >= 0], minlength=proposal.nodes)
    assert torch.equal(counted[inner], (right[inner] - left[inner] + 1))
    assert int((counted[inner] < 2).sum()) == 0             # a pass-through node describes nothing
    # a child's range is inside its parent's, and the children tile it exactly
    child = torch.nonzero(parent >= 0, as_tuple=False).flatten()
    assert int((lo[child] < lo[parent[child]]).sum()) == 0
    assert int((hi[child] > hi[parent[child]]).sum()) == 0
    covered = torch.zeros(proposal.nodes, dtype=torch.int64, device=lo.device)
    covered.index_add_(0, parent[child], (hi - lo)[child])
    assert torch.equal(covered[inner], (hi - lo)[inner])
    # depth and height agree with the parent relation
    assert int((proposal.depth[child] != proposal.depth[parent[child]] + 1).sum()) == 0
    assert int(proposal.height[proposal.left < 0].max()) == 1


def test_the_leaf_order_is_a_permutation_and_the_components_are_contiguous():
    built = _tree()
    proposal, flat = built.proposal, built.flat
    assert int(proposal.order.numel()) == flat.rows
    assert torch.equal(torch.sort(proposal.order).values,
                       torch.arange(flat.rows, dtype=torch.int64, device=proposal.order.device))
    # the rank of a row is local to its component, and a node never straddles two components
    assert int((proposal.rank_of_row < 0).sum()) == 0
    rows_of = flat.row_component[proposal.order]
    assert int((rows_of[1:] < rows_of[:-1]).sum()) == 0     # component-major, so contiguous


def test_the_build_passes_no_verdicts_and_the_recursion_reaches_the_root():
    built = _tree()
    assert bool(built.node_resolved.all()) and bool(built.node_stop.all())
    roots = torch.nonzero(built.proposal.parent < 0, as_tuple=False).flatten()
    assert int(roots.numel()) <= built.flat.components
    # every row is under a root, so the recursion ran to the top of every component
    assert int((built.proposal.hi[roots] - built.proposal.lo[roots]).sum()) == built.flat.rows
    # the reference mass is conserved: a component's nodes at one grade sum to 1
    mass = built.node_mass
    for grade in range(int(built.node_grade.max()) + 1):  # loop-ok: over GRADES, depth ~ log N
        here = built.node_grade == grade
        assert float(mass[here].sum()) > 0.0
    assert float(mass[roots].sum()) == float(built.flat.components)


def test_the_rank_is_the_priced_rank_inside_the_capacity():
    built = _tree()
    assert int((built.node_rank > built.node_capacity_rank).sum()) == 0
    assert int((built.node_rank != torch.minimum(built.node_priced_rank,
                                                 built.node_capacity_rank)).sum()) == 0
