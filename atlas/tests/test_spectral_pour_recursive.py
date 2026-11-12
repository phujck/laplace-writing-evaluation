"""Recursive UP consumes the planted synthetic substrate, including negative propagation."""
from dataclasses import replace
import math
import json

import pytest

from atlas.history import GradeAxisContract
from atlas.ids import chash
from atlas.spectral_pour import (PourLeaf, bank_spectral_pour, repair_spectral_pour,
                                 derive_recursive_placement, recursive_split_stop)
from atlas.errors import StateTransitionRefused
from atlas.store import ConceptricStore
from test_spectral_pour import CONTRACT, META


def recursive_contract(depth=5, leaf_max=2):
    return replace(CONTRACT, grade_contract=GradeAxisContract(
        'axis-contract:recursive-test/1', 'source-detail',
        ('cluster',) + tuple(f'cluster:{i}' for i in range(2, depth + 1)) + ('leaf',)),
        leaf_max=leaf_max, branching=2, max_depth=depth)


def planted_leaves(n=32):
    return tuple(PourLeaf(str(i), f'leaf:{i}:v1', chash({'i':i}), f'planted leaf {i}',
                  (math.cos(i * 1.5 / n), math.sin(i * 1.5 / n)), (chash({'i':i}),))
                 for i in range(n))


def test_three_grade_changed_row_moves_exactly_its_ancestors(tmp_path):
    contract = recursive_contract()
    store = ConceptricStore(tmp_path / 'propagation')
    leaves = planted_leaves()
    first = bank_spectral_pour(store, contract, leaves, META)
    all_nodes = [n for root in first.receipt.placement for n in root.walk()]
    target = max(all_nodes, key=lambda n: n.depth).member_logical_ids[0]
    ancestors = {n.cluster_id for n in all_nodes if target in n.member_logical_ids}
    assert len(ancestors) >= 3
    replacement = replace(next(leaf for leaf in leaves if leaf.logical_id == target),
                          object_id=f'leaf:{target}:v2', content_handle=chash({'changed':target}),
                          text='changed row; membership frozen', vector=(.999, .02))
    changed = tuple(replacement if leaf.logical_id == target else leaf for leaf in leaves)
    second = bank_spectral_pour(store, contract, changed, META, placement=first.receipt.placement)
    moved = {key for key in first.nodes if first.nodes[key].node_handle != second.nodes[key].node_handle}
    assert moved == ancestors
    assert set(first.nodes) - moved  # negative half is nonempty
    for key in set(first.nodes) - moved:
        assert first.promotions[key] == second.promotions[key]
    state = store.replay()
    for key in ancestors:
        assert second.promotions[key].coarse_object_id in state.graph_objects
    assert state.grade_axis_contracts[contract.grade_contract.contract_id] == contract.grade_contract
    assert first.receipt.to_dict()['placement'][0]['children']
    with pytest.raises(StateTransitionRefused, match='RECURSIVE_REPAIR_REQUIRED'):
        repair_spectral_pour(store, first, replacement, META)
    print(json.dumps(dict(propagation_grades=len(ancestors), changed=len(moved),
                         unchanged=len(first.nodes)-len(moved), exactly_own_ancestors=True)))


def test_indistinguishable_cluster_is_typed_decline(tmp_path):
    leaves = tuple(replace(leaf, vector=(1., 0.)) for leaf in planted_leaves(12))
    contract = recursive_contract()
    banked = bank_spectral_pour(ConceptricStore(tmp_path / 'decline'), contract, leaves, META)
    root = banked.receipt.placement[0]
    assert root.stop_reason == 'indistinguishable_members'
    assert not root.children
    assert root.overflow == 10
    assert banked.receipt.to_dict()['depth_policy']['leaf_max'] == 2
    assert root.to_dict()['stop_kind'] == 'cut_decline'
    print(json.dumps(dict(type='cut_decline', reason=root.stop_reason, held=len(leaves),
                         leaf_max=contract.leaf_max, overflow=len(leaves)-contract.leaf_max, grade=root.depth)))


def test_depth_is_safety_not_cut_decline():
    contract = recursive_contract(depth=1)
    roots = derive_recursive_placement(planted_leaves(), contract)
    assert all(r.stop_reason == 'depth_cap' and r.to_dict()['stop_kind'] == 'safety' for r in roots)


def test_missing_recursive_dials_refuses():
    with pytest.raises(StateTransitionRefused, match='branching'):
        replace(recursive_contract(), branching=None)


def test_manifest_carries_depth_and_per_grade_dials():
    from atlas.dataset import spectral_contract
    core = dict(encoder={'spec': CONTRACT.encoder_spec.to_dict()}, spectral=dict(
        assumption='synthetic', fibre='synthetic', grade_contract_id='axis:synthetic', axis='detail',
        lens_id='test', metric_version='cosine', cluster_count=2, chi=1, phi=.5,
        placement_operator=CONTRACT.placement_operator, entry_role='test',
        leaf_max=2, branching=[2, 3], max_depth=3, grade_chi=[1, 2, 3], grade_phi=[.5, .6, .7]))
    contract = spectral_contract(core)
    assert contract.grade_contract.coarse_to_fine == ('cluster', 'cluster:2', 'cluster:3', 'leaf')
    assert contract.branching == (2, 3)
    assert contract.grade_chi == (1, 2, 3)
