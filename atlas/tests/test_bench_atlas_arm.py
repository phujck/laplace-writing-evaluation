"""Exercise stored-face retrieval, exact frozen reads, exclusion and registration custody."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest
from bench_fixture import build_bundle, open_bundle
from test_blueprint import fixtures

from atlas.blueprint import DesignDocument, pour_blueprint
from atlas.bench.arms.atlas_arm import AtlasArm, AtlasFoldCost, face_score
from atlas.bench.cost import ModelCounter, SpanReader
from atlas.bench.draw import fingerprint
from atlas.bench.freeze import anchor_task, freeze_bundle
from atlas.bench.runner import run_bundle
from atlas.bench.universe import SnapshotView, FULL_UNIVERSE
from atlas.dataset import extra_authority_files
from atlas.errors import ProtocolViolation
from atlas.store import ConceptricStore
from atlas.tools.run_bench import applicable_arm_ids, instrument_summary, validate_v2_law, build_arms

REG = Path(__file__).resolve().parents[1] / 'bench/instrument'


@pytest.fixture
def folded(tmp_path, request):
    view = SnapshotView(open_bundle(build_bundle(tmp_path / 'snapshot')), FULL_UNIVERSE)
    root = tmp_path / 'sources'
    root.mkdir()
    documents = []
    for node in view.node_ids:
        path = root / node
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(view.node_text(node))
        documents.append(DesignDocument(node, 's1-design'))
    encoder, contract, metadata, _ = fixtures(root)
    if getattr(request, 'param', False):
        from dataclasses import replace
        from atlas.history import GradeAxisContract
        contract = replace(contract, cluster_count=1, leaf_max=1, branching=2, max_depth=5,
            grade_contract=GradeAxisContract('axis-contract:arm-recursive/1', 'source-detail',
                ('cluster', 'cluster:2', 'cluster:3', 'cluster:4', 'cluster:5', 'leaf')))
    authority = Path(__file__).resolve().parents[2]
    store_path = tmp_path / 'store'
    store = ConceptricStore(store_path, extra_authority_files=extra_authority_files(authority))
    generation = pour_blueprint(store, root, tuple(documents), (), encoder, contract, metadata,
                               segmentation={'target_tokens':384, 'hard_cap_tokens':512})
    # Finalize fixture writers before measuring the immutable reader.
    import gc
    del store
    gc.collect()
    before = fingerprint(store_path)
    arm = AtlasArm(store_path, k=2, encoder=encoder, authority_root=authority)
    arm.fold(view)
    return arm, view, generation, before, store_path


def test_tmp_store_ranked_handles_accounted_reads_without_source_or_blob_scoring(folded, monkeypatch):
    arm, view, generation, before, store_path = folded
    task = anchor_task(view, 'T', 'VERBATIM', 'run the widget sweep',
                       ['run the widget sweep'], None, 'HANDOFF.md', '2026-09-14')
    # Serve through reader only; store bodies are deliberately poisoned after fold.
    for c in generation.clauses:
        arm.state.graph_objects[c['object_id']].attributes['text'] = 'POISON'
    reader = SpanReader(view, max_spans_read=2)
    models = ModelCounter('atlas')
    answer = arm.answer(task, reader, models)
    assert models.calls == 1
    assert answer.retrieved and len(answer.retrieved) <= 2
    assert set(answer.retrieved) <= {c['content_handle'] for c in generation.clauses}
    assert answer.detail['reads'] == reader.spans_read == len(answer.retrieved)
    assert answer.detail['visited'] + answer.detail['omission_residual'] == answer.detail['total']
    assert answer.detail['total'] == len(generation.clauses)
    assert answer.detail['coarse_expanded'] == 1
    assert len(answer.detail['rejected_branches']) == len(generation.clusters) - 1
    assert 'POISON' not in answer.context
    assert fingerprint(store_path) == before


def test_runner_preserves_accounting_and_declared_denominator(folded):
    arm, view, _, _, _ = folded
    task = anchor_task(view, 'T', 'VERBATIM', 'run the widget sweep',
                       ['run the widget sweep'], None, 'HANDOFF.md', '2026-09-14')
    result = run_bundle(freeze_bundle(view, 'test', [task]), view, [arm])
    assert result.rows[0]['detail']['total'] > 0
    assert result.costs['atlas'].query_model_tokens == result.rows[0]['cost']['query_model_tokens'] > 0
    assert result.rows[0]['cost']['query_encoder_calls'] == 1
    assert result.manifest['encoder_bill']['atlas']['fold_calls_this_run'] == 1
    assert result.costs['atlas'].to_dict()['fold_amortized_per_query']['reference_query_count'] == 80


def test_frame_and_semantic_both_influence_score():
    q = np.array([0., 1.])
    narrow = dict(centroid=[1., 0.], frame={'basis': []})
    wide = dict(centroid=[1., 0.], frame={'basis': [[0., 1.]]})
    assert face_score(q, wide, [0., 1.]) > face_score(q, narrow, [0., 1.])
    assert face_score(q, wide, [0., 1.]) > face_score(q, wide, [1., 0.])


def test_missing_pour_bill_is_null_not_free():
    cost = AtlasFoldCost(wall_seconds=2, model_calls=1)
    assert cost.to_dict()['wall_seconds'] is None
    assert cost.to_dict()['retrieval_setup']['wall_seconds'] == 2
    assert cost.amortized(80)['wall_seconds_per_query'] is None
    assert cost.amortized(80)['retrieval_setup']['wall_seconds_per_query'] == .025


def test_every_constructed_arm_declares_applicability():
    for arm in build_arms(1, 10, True, None, None):
        assert arm.applicable_kinds


def test_applicability_excludes_tex_blind_arms_from_floor_and_pairs():
    reg = json.loads((REG / 'qrc-two-mode-20260914-v2.json').read_text())
    included, excluded = applicable_arm_ids(reg, ['tex'])
    assert included == ['bm25', 'dense_flat', 'atlas']
    assert [r['arm'] for r in excluded] == ['flat_read:B', 'flat_read:B+', 'grep_skilled']
    reg['draws_per_mode'] = 2
    rows = [dict(task=str(t), arm=a, correct=True) for t in range(2) for a in included]
    summary = instrument_summary(rows, reg, 'VERBATIM')
    assert summary['verdict'] == 'REFUSED_LEXICAL_TAUTOLOGY'
    assert len(summary['bootstrap']['pairwise']) == 3
    with pytest.raises(ProtocolViolation, match='INCOMPLETE_INSTRUMENT_ROWS'):
        instrument_summary(rows + [dict(task='0', arm='grep_skilled', correct=False)], reg, 'VERBATIM')


def test_v2_preserves_v1_law_bytes_and_frozen_draws():
    old_text = (REG / 'qrc-two-mode-20260914.json').read_text()
    new_text = (REG / 'qrc-two-mode-20260914-v2.json').read_text()
    old, new = json.loads(old_text), json.loads(new_text)
    validate_v2_law(old, new)
    for key in set(old) - set(new['amended_fields']):
        assert json.dumps(old[key], ensure_ascii=False) == json.dumps(new[key], ensure_ascii=False)
        # Scalar law strings and numbers survive as literal encoded tokens too.
        if isinstance(old[key], (str, float, int)):
            token = json.dumps(key) + ': ' + json.dumps(old[key])
            assert token in old_text and token in new_text
    from atlas.ids import hash_bytes
    for binding in new['frozen_draws']['bundles'].values():
        p = Path(binding['path'])
        assert hash_bytes(p.read_bytes()) == binding['tasks_sha256']
        assert hash_bytes((p.parent / 'freeze.json').read_bytes()) == binding['freeze_sha256']
    corrupt = copy.deepcopy(new)
    corrupt['verbatim_floor'] = .1
    with pytest.raises(ProtocolViolation, match='V1_LAW_DRIFT'):
        validate_v2_law(old, corrupt)
    corrupt['amended_fields'].append('verbatim_floor')
    with pytest.raises(ProtocolViolation, match='V1_LAW_AMENDMENT_SCOPE'):
        validate_v2_law(old, corrupt)


@pytest.mark.parametrize('folded', [True], indirect=True)
def test_arm_consumes_recursive_generation_through_all_selected_grades(folded):
    arm, view, generation, before, store_path = folded
    assert any(c.get('depth', 1) >= 3 for c in generation.clusters)
    reached = []
    for i, clause in enumerate(generation.clauses):
        span = arm.spans[clause['logical_id']]
        text = view.span_text(span)
        task = anchor_task(view, f'R{i}', 'VERBATIM', text, [text], None,
                           clause['source_path'], '2026-09-14')
        answer = arm.answer(task, SpanReader(view, max_spans_read=2), ModelCounter('atlas'))
        selected = answer.detail['selected_branches']
        last = next(c for c in generation.clusters if c['node_handle'] == selected[-1])
        assert not last['child_cluster_ids']
        assert answer.detail['visited'] == len(last['member_logical_ids'])
        reached.extend(answer.detail['grades_descended'])
    assert max(reached) >= 3
    assert fingerprint(store_path) == before
