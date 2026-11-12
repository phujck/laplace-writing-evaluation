"""Routing laws, planted frames, beam consumption and additive registration."""
import copy
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from test_bench_atlas_arm import folded
from atlas.bench.arms.atlas_arm import FACE_SCORE_LAWS, face_score
from atlas.bench.cost import ModelCounter, SpanReader
from atlas.bench.freeze import anchor_task
from atlas.errors import ProtocolViolation
from atlas.ids import hash_bytes
from atlas.tools.run_bench import routing_dials, validate_v2_law, validate_v3_law, build_arms

REG = Path(__file__).resolve().parents[1] / 'bench/instrument'


@pytest.mark.parametrize('law', FACE_SCORE_LAWS)
def test_planted_two_cluster_right_frame(law):
    q = np.array([0., 1., 0.])
    right = dict(centroid=[0., .5, 0.], frame={'basis': [[0., 1., 0.]]})
    left = dict(centroid=[1., 0., 0.], frame={'basis': [[0., 0., 1.]]})
    assert face_score(q, right, [0., 1., 0.], law) > face_score(q, left, [1., 0., 0.], law)
    if law == 'frame-residual':
        assert face_score(q, right, [0., 1., 0.], law) == pytest.approx(1)
        assert face_score(q, left, [1., 0., 0.], law) == pytest.approx(0)
        assert face_score(np.array(right['centroid']), right, [0., 0., 0.], law) == 1


@pytest.mark.parametrize('folded', [True], indirect=True)
@pytest.mark.parametrize('beam', [1, 2, 4, 8])
@pytest.mark.parametrize('law', ['equal-mean', 'sum-of-heat-through-the-nest'])
def test_beam_accounting_and_inherited_heat(folded, beam, law):
    arm, view, generation, _, _ = folded
    arm.protocol = replace(arm.protocol, beam=beam)
    arm.face_score_law = law
    task = anchor_task(view, 'beam', 'VERBATIM', 'run the widget sweep',
                       ['run the widget sweep'], None, 'HANDOFF.md', '2026-09-14')
    answer = arm.answer(task, SpanReader(view, max_spans_read=2), ModelCounter('atlas'))
    detail = answer.detail
    nodes = {c['node_handle']: c for c in generation.clusters}
    selected = [nodes[h] for h in detail['selected_branches']]
    leaves = [k for c in selected if not c['child_cluster_ids'] for k in c['member_logical_ids']]
    assert detail['visited'] == len(set(leaves)) == len(leaves)
    assert detail['visited'] + detail['omission_residual'] == detail['total']
    assert detail['reads'] == min(2, len(leaves))
    assert detail['coarse_scored'] == sum(map(len, detail['routing_trace']))
    scores = {r['node_handle']: r['score'] for step in detail['routing_trace'] for r in step}
    parent = {key: c for c in generation.clusters for key in c['child_cluster_ids']}
    q = arm.encoder.query(task.question)
    for step in detail['routing_trace']:
        assert sum(r['kept'] for r in step) == min(beam, len(step))
        for row in step:
            c = nodes[row['node_handle']]
            local = face_score(q, arm.state.graph_objects[c['spectral_object_id']].attributes,
                               arm.semantic_by_id[c['cluster_id']], law)
            p = parent.get(c['cluster_id'])
            heat = scores[p['node_handle']] if p and law == 'sum-of-heat-through-the-nest' else 1
            assert row['score'] == pytest.approx(local * heat)


def test_v3_preserves_v1_v2_and_consumes_registered_dials():
    old = json.loads((REG / 'qrc-two-mode-20260914.json').read_text())
    parent_path = REG / 'qrc-two-mode-20260914-v2.json'
    parent = json.loads(parent_path.read_text())
    reg = json.loads((REG / 'qrc-two-mode-20260914-v3.json').read_text())
    validate_v2_law(old, reg)
    validate_v3_law(parent, reg)
    assert reg['routing_v3']['parent_sha256'] == hash_bytes(parent_path.read_bytes())
    for k, v in parent.items():
        assert reg[k] == v
    for beam in reg['routing_v3']['beam']:
        for law in reg['routing_v3']['face_score']:
            arms = build_arms(1, 10, False, None, None, atlas_store=Path('unused'),
                              **routing_dials(reg, beam, law, 10))
            arm = next(a for a in arms if a.protocol.arm_id == 'atlas')
            assert (arm.protocol.beam, arm.face_score_law, arm.protocol.k) == (beam, law, 10)
    for args in [(3, 'equal-mean', 10), (1, 'unknown', 10), (1, 'equal-mean', 20)]:
        with pytest.raises(ProtocolViolation, match='UNREGISTERED_ROUTING_DIAL'):
            routing_dials(reg, *args)
    with pytest.raises(ProtocolViolation, match='UNREGISTERED_ROUTING_DIAL'):
        routing_dials(parent, 2)
    broken = copy.deepcopy(reg)
    broken['retrieval_k'] = 20
    with pytest.raises(ProtocolViolation, match='V2_LAW_DRIFT'):
        validate_v3_law(parent, broken)
