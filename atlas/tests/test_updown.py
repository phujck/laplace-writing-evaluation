"""LOCAL KERNEL GATES for UP/DOWN — deliberately NOT the five-gate planted boundary.

These prove the pure kernel: known-cell promotion, degenerate eigenspace, cycle consistency
from RETAINED state, content-addressed identity, explicit-chi behaviour, representation-
residual-forced descent, declared-axis grade order. The acceptance boundary proper — placed
(not preselected) membership, G3 question routing with source-chain assemblage, store
content-address diffs — belongs to the history/runner layer and is NOT claimed here
(the codex acceptance-boundary audit, 2026-08-24).
"""

from __future__ import annotations

import math

import pytest

from atlas.errors import StateTransitionRefused
from atlas.updown import ChildLeaf, UpInputs, down, up


def _leaf(handle: str, text: str, vector: list[float]) -> ChildLeaf:
    return ChildLeaf(handle=handle, text=text, vector=tuple(vector))


def _planted_cluster(offset: float = 0.0) -> list[ChildLeaf]:
    """A known planted hierarchy cell: three leaves near one direction in R^4."""
    return [
        _leaf(f"sha256:leaf-a{offset}", "alpha wave notes", [1.0 + offset, 0.02, 0.0, 0.0]),
        _leaf(f"sha256:leaf-b{offset}", "alpha wave detail", [0.9 + offset, -0.03, 0.01, 0.0]),
        _leaf(f"sha256:leaf-c{offset}", "alpha wave source", [1.1 + offset, 0.0, -0.02, 0.0]),
    ]


def _inputs(children, chi=2, phi=0.2, **over) -> UpInputs:
    base = dict(
        assumption="planted-hierarchy-bench", fibre="test-fibre", axis="meaning",
        from_grade=0, to_grade=1, metric_version="unit-test-metric/1",
        grade_contract_id="grade-axis:meaning/test/1",
        chi=chi, phi=phi, coarse_to_fine=(1, 0), children=tuple(children),
    )
    base.update(over)
    return UpInputs(**base)


def test_planted_hierarchy_promotes_with_both_faces_and_full_membership():
    r = up(_inputs(_planted_cluster()))
    assert r.representation_sufficient and r.residual_within_phi
    node = r.node
    assert node.member_handles == tuple(c.handle for c in _planted_cluster())
    assert node.frame is not None and node.frame.chi_kept >= 1
    # both faces derive from the SAME children, atomically: the semantic face carries
    # verbatim child spans and names its sources; the frame carries the spectrum.
    assert "alpha wave" in node.semantic_face
    assert set(node.semantic_sources) <= set(node.member_handles)
    assert node.frame.truncation_residual == r.residual_value


def test_up_then_down_cycle_is_consistent():
    children = _planted_cluster()
    r = up(_inputs(children, chi=3, phi=0.5))
    d = down(r.node, children={c.handle: c for c in children})
    assert d.child_handles == r.node.member_handles          # exact handles, always
    # chi=3 over a rank<=3 cell reconstructs the children to numerical identity
    for c in children:
        got = d.reconstructions[c.handle]
        assert math.sqrt(sum((x - y) ** 2 for x, y in zip(c.vector, got, strict=True))) < 1e-6
    assert d.round_trip_residual < 1e-6


def test_untouched_subtree_hashes_are_identical():
    left, right = _planted_cluster(0.0), _planted_cluster(5.0)
    before = up(_inputs(right))
    _ = up(_inputs(left, chi=1, phi=0.9))                    # fold the OTHER branch
    after = up(_inputs(right))
    assert after.node.node_handle == before.node.node_handle  # content address unmoved


def test_idempotence_is_content_addressed_identity():
    a, b = up(_inputs(_planted_cluster())), up(_inputs(_planted_cluster()))
    assert a.act_handle == b.act_handle
    assert a.node.node_handle == b.node.node_handle


def test_explicit_chi_cuts_rank_and_grows_residual():
    spread = [
        _leaf("sha256:s1", "x axis", [1.0, 0.0, 0.0, 0.0]),
        _leaf("sha256:s2", "y axis", [0.0, 1.0, 0.0, 0.0]),
        _leaf("sha256:s3", "z axis", [0.0, 0.0, 1.0, 0.0]),
        _leaf("sha256:s4", "w axis", [0.0, 0.0, 0.0, 1.0]),
    ]
    wide = up(_inputs(spread, chi=3, phi=1.0))
    narrow = up(_inputs(spread, chi=1, phi=1.0))
    assert narrow.node.frame.chi_kept == 1 < wide.node.frame.chi_kept
    assert narrow.residual_value > wide.residual_value
    # chi is never padded past the available rank
    assert up(_inputs(_planted_cluster(), chi=50, phi=1.0)).node.frame.chi_kept <= 3


def test_high_residual_forces_descent_and_cannot_claim_sufficient():
    spread = [
        _leaf("sha256:f1", "one", [1.0, 0.0, 0.0, 0.0]),
        _leaf("sha256:f2", "two", [0.0, 1.0, 0.0, 0.0]),
        _leaf("sha256:f3", "three", [0.0, 0.0, 1.0, 0.0]),
    ]
    r = up(_inputs(spread, chi=1, phi=0.05))
    assert not r.representation_sufficient and not r.residual_within_phi
    assert r.forced_descent is not None and r.node.node_handle in r.forced_descent


def test_degenerate_eigenspace_cut_is_declared_never_smoothed():
    tied = [
        _leaf("sha256:d1", "east", [1.0, 0.0, 0.0, 0.0]),
        _leaf("sha256:d2", "west", [-1.0, 0.0, 0.0, 0.0]),
        _leaf("sha256:d3", "north", [0.0, 1.0, 0.0, 0.0]),
        _leaf("sha256:d4", "south", [0.0, -1.0, 0.0, 0.0]),
    ]
    r = up(_inputs(tied, chi=1, phi=1.0))                    # the cut lands inside the tie
    assert r.node.frame.degenerate_cut is True
    untied = up(_inputs(_planted_cluster(), chi=1, phi=1.0))
    assert untied.node.frame.degenerate_cut is False


def test_chi_and_phi_are_declared_or_refused_never_defaulted():
    with pytest.raises(TypeError):
        UpInputs(assumption="a", fibre="f", axis="meaning", from_grade=0, to_grade=1,
                 metric_version="m/1", coarse_to_fine=(1, 0))  # no children at all
    with pytest.raises(StateTransitionRefused):
        _inputs(_planted_cluster(), chi=0)
    with pytest.raises(StateTransitionRefused):
        _inputs(_planted_cluster(), phi=0.0)
    with pytest.raises(StateTransitionRefused):
        _inputs(_planted_cluster(), to_grade=0)              # promotion must move the grade


def test_adjoint_scope_is_fibre_local_and_descent_refuses_partial_resolution():
    r = up(_inputs(_planted_cluster()))
    assert r.adjoint_scope == "(planted-hierarchy-bench | test-fibre | unit-test-metric/1)"
    children = {c.handle: c for c in _planted_cluster()[:2]}  # one member unresolved
    with pytest.raises(StateTransitionRefused, match="unresolved member"):
        down(r.node, children=children)


# --- the four blocking defects (codex updown-first-math-audit, 2026-08-24) --------------
# Written to FAIL the pre-repair code, per the audit's demand, then cured.

def test_defect1_down_prolongs_from_retained_state_not_originals():
    """DOWN must reconstruct from centroid+basis+stored coordinates; originals only verify."""
    children = _planted_cluster()
    r = up(_inputs(children, chi=3, phi=0.5))
    d = down(r.node)                                          # no originals supplied at all
    for c in children:
        got = d.reconstructions[c.handle]
        assert math.sqrt(sum((x - y) ** 2 for x, y in zip(c.vector, got, strict=True))) < 1e-6


def test_defect2_identity_binds_the_complete_payload():
    """Same handles, different content behind one handle -> identities MUST differ."""
    base = [
        _leaf("sha256:p1", "alpha near", [1.0, 0.0, 0.0, 0.0]),
        _leaf("sha256:p2", "alpha close", [0.9, 0.1, 0.0, 0.0]),
        _leaf("sha256:p3", "alpha kin", [1.1, -0.1, 0.0, 0.0]),
        _leaf("sha256:p4", "far outlier", [0.0, 0.0, 0.0, 3.0]),
    ]
    changed = [base[0], base[1], base[2],
               _leaf("sha256:p4", "DIFFERENT text behind the same handle", [0.0, 0.0, 0.0, 3.0])]
    a = up(_inputs(base, chi=2, phi=1.0))
    b = up(_inputs(changed, chi=2, phi=1.0))
    assert a.node.node_handle != b.node.node_handle
    assert a.inputs_handle != b.inputs_handle


def test_defect3_degenerate_cut_forces_insufficiency():
    """A chi cut through a tied singular block is basis-unstable: never sufficient."""
    tied = [
        _leaf("sha256:t1", "east", [1.0, 0.0, 0.0, 0.0]),
        _leaf("sha256:t2", "west", [-1.0, 0.0, 0.0, 0.0]),
        _leaf("sha256:t3", "north", [0.0, 1.0, 0.0, 0.0]),
        _leaf("sha256:t4", "south", [0.0, -1.0, 0.0, 0.0]),
    ]
    r = up(_inputs(tied, chi=1, phi=1.0))
    assert r.node.frame.degenerate_cut is True
    assert r.representation_sufficient is False
    assert r.forced_descent is not None and "chi" in r.forced_descent


def test_defect4_grade_order_is_proven_against_the_declared_axis():
    """A mislabeled DOWN (from coarser to finer) must be refused, not accepted as UP."""
    with pytest.raises(StateTransitionRefused, match="finer"):
        _inputs(_planted_cluster(), from_grade=1, to_grade=0, coarse_to_fine=(1, 0))
    with pytest.raises(StateTransitionRefused, match="axis"):
        _inputs(_planted_cluster(), from_grade=0, to_grade=2, coarse_to_fine=(1, 0))


# --- pinned executable counterexamples (codex updown-counterexample-receipt) ------------

def test_pinned_square_chi1_is_never_representation_sufficient():
    square = [
        _leaf("sha256:q1", "e1+", [1.0, 0.0]), _leaf("sha256:q2", "e1-", [-1.0, 0.0]),
        _leaf("sha256:q3", "e2+", [0.0, 1.0]), _leaf("sha256:q4", "e2-", [0.0, -1.0]),
    ]
    r = up(_inputs(square, chi=1, phi=0.6))
    assert r.node.frame.degenerate_cut is True
    assert r.representation_sufficient is False
    assert r.forced_descent is not None


def test_pinned_collinear_e1_vs_e2_never_share_identity():
    handles_text = [("sha256:c1", "a"), ("sha256:c2", "b"),
                    ("sha256:c3", "c"), ("sha256:c4", "d")]
    e1 = [_leaf(h, t, [s_ * 1.0, 0.0]) for (h, t), s_ in zip(handles_text, (1, -1, 1, -1), strict=True)]
    e2 = [_leaf(h, t, [0.0, s_ * 1.0]) for (h, t), s_ in zip(handles_text, (1, -1, 1, -1), strict=True)]
    a, b = up(_inputs(e1, chi=1, phi=1.0)), up(_inputs(e2, chi=1, phi=1.0))
    assert a.node.node_handle != b.node.node_handle


# --- residual honesty + named grade contract (codex updown-residual-honesty-fix) --------

def test_unverified_down_never_reports_a_measured_residual():
    """No originals -> no measured round trip: None + verified=False, never a clean 0.0."""
    children = _planted_cluster()
    r = up(_inputs(children, chi=3, phi=0.5))
    bare = down(r.node)
    assert bare.verified is False and bare.round_trip_residual is None
    checked = down(r.node, children={c.handle: c for c in children})
    assert checked.verified is True
    assert isinstance(checked.round_trip_residual, float)


def test_grade_contract_is_named_and_bound_to_identity():
    """The axis order rides a NAMED contract id the history adapter can resolve."""
    a = up(_inputs(_planted_cluster()))
    b = up(_inputs(_planted_cluster(), grade_contract_id="grade-axis:meaning/other/9"))
    assert a.inputs_handle != b.inputs_handle
    with pytest.raises(StateTransitionRefused, match="contract"):
        _inputs(_planted_cluster(), grade_contract_id="  ")
