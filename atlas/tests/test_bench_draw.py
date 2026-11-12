"""Exercise random-query minting, planted tautology, timing and paired intervals."""
import dataclasses
import json
from pathlib import Path

import pytest
from bench_fixture import LAW, build_bundle, open_bundle

from atlas.bench.arms.base import ArmAnswer
from atlas.bench.arms.bm25 import Bm25Arm
from atlas.bench.draw import assert_registered_before, displaced_population, draw, unique_atoms
from atlas.bench.freeze import anchor_task, freeze_bundle
from atlas.bench.runner import run_bundle
from atlas.bench.stats import bootstrap_totals
from atlas.bench.universe import BENCH_FILTERED, FULL_UNIVERSE, SnapshotView
from atlas.errors import ProtocolViolation
from atlas.snapshot import load_snapshot
from atlas.tools.run_bench import instrument_summary

REG = Path(__file__).resolve().parents[1] / 'bench/instrument/qrc-two-mode-20260914.json'


def registration():
    return json.loads(REG.read_text())


def test_duplicate_span_atoms_are_excluded_by_real_find_anchor(tmp_path):
    view = SnapshotView(open_bundle(build_bundle(tmp_path / 'snap', doc=LAW)), BENCH_FILTERED)
    atoms, report = unique_atoms(view)
    assert report['excluded_reasons']['ambiguous'] >= 2
    assert report['atoms_before'] == report['atoms_after_uniqueness'] + report['excluded_count']
    assert all(s.node_id not in ('HANDOFF.md', 'STANDING_LAW.md') for s, _, _ in atoms)


def test_qrc_sibling_mapping_excludes_target_and_matches_parent():
    snap = load_snapshot(Path(registration()['snapshot_dir']))
    view = SnapshotView(snap, FULL_UNIVERSE)
    atoms, _ = unique_atoms(view)
    population, excluded = displaced_population(view, snap.spans, atoms)
    assert population and excluded['missing_or_invalid_parent'] > 0
    for span, atom, anchor, sibling, query in population:
        assert span.parent_span == sibling.parent_span
        assert span.span_id != sibling.span_id == snap.spans[sibling.span_id].span_id
        assert anchor.span_id == span.span_id
        assert query == view.span_text(sibling)
        assert atom not in query


class TautologicalArm(Bm25Arm):
    def answer(self, task, reader, models):
        return ArmAnswer(context=task.question, rounds=1)


def test_planted_tautological_arms_compute_refusal(tmp_path):
    view = SnapshotView(open_bundle(build_bundle(tmp_path / 'snap')), BENCH_FILTERED)
    task = anchor_task(view, 'T', 'VERBATIM', 'run the widget sweep',
                       ['run the widget sweep'], None, 'HANDOFF.md', '2026-09-14')
    bundle = freeze_bundle(view, 'test', [task])
    arms = [TautologicalArm(), TautologicalArm()]
    arms[1].protocol = dataclasses.replace(arms[1].protocol, arm_id='dense_flat')
    result = run_bundle(bundle, view, arms, segmentation_id='test')
    reg = registration()
    reg.update(arms=['bm25', 'dense_flat'], draws_per_mode=1)
    summary = instrument_summary(result.rows, reg, 'VERBATIM')
    assert summary['verdict'] == summary['floor_verdict'] == 'REFUSED_LEXICAL_TAUTOLOGY'
    result.rows[0]['correct'] = False
    assert instrument_summary(result.rows, reg, 'VERBATIM')['verdict'] == 'FLOOR_NOT_TRIGGERED'


@pytest.mark.parametrize('registered,started', [
    ('2026-09-14T20:00:00+00:00', '2026-09-14T20:00:00+00:00'),
    ('2026-09-14T21:00:00+00:00', '2026-09-14T20:00:00+00:00'),
    ('bad', '2026-09-14T20:00:00+00:00'),
    ('2026-09-14T19:00:00', '2026-09-14T20:00:00+00:00'),
])
def test_registration_must_strictly_precede_start(registered, started):
    with pytest.raises(ProtocolViolation):
        assert_registered_before(registered, started)


def test_registration_compares_instants_not_timestamp_strings():
    assert_registered_before('2026-09-14T21:00:00+02:00', '2026-09-14T20:00:00+00:00')


def test_runner_refuses_future_registration_before_building_arms(tmp_path, monkeypatch, capsys):
    from atlas.tools import run_bench
    snapshot = build_bundle(tmp_path / 'snap')
    view = SnapshotView(open_bundle(snapshot), BENCH_FILTERED)
    task = anchor_task(view, 'T', 'VERBATIM', 'run the widget sweep',
                       ['run the widget sweep'], None, 'HANDOFF.md', '2026-09-14')
    bundle = freeze_bundle(view, 'test', [task])
    bundle_path = tmp_path / 'tasks.json'
    bundle_path.write_text(json.dumps(bundle.to_dict()))
    reg = registration()
    reg['registered_ts'] = '2999-01-01T00:00:00+00:00'
    stop = tmp_path / 'stop.json'
    stop.write_text(json.dumps(reg))
    def forbidden(*args, **kwargs):
        pytest.fail('arm constructed before timestamp refusal')
    monkeypatch.setattr(run_bench, 'build_arms', forbidden)
    assert run_bench.main([str(snapshot), '--bundle', str(bundle_path), '--out', str(tmp_path / 'out'),
                           '--stop-condition', str(stop)]) == 1
    assert 'registration must precede' in capsys.readouterr().err
    assert not (tmp_path / 'out').exists()


def test_bootstrap_constant_difference_and_perfect_pairing():
    rows = [dict(task=str(i), arm=a, correct=value)
            for i in range(8) for a, value in [('one', True), ('zero', False), ('twin', True)]]
    result = bootstrap_totals(rows)
    pair = {(p['arm_a'], p['arm_b']): p for p in result['pairwise']}
    assert (pair['one', 'zero']['ci_low'], pair['one', 'zero']['ci_high']) == (8, 8)
    assert (pair['one', 'twin']['ci_low'], pair['one', 'twin']['ci_high']) == (0, 0)
    varied = [dict(task=str(i), arm=a, correct=i % 2 == 0) for i in range(8) for a in ('a', 'b')]
    p = bootstrap_totals(varied)['pairwise'][0]
    assert p['ci_low'] == p['ci_high'] == 0


def test_draw_freezes_paired_random_bundles_and_refuses_small_population(tmp_path):
    reg = registration()
    path = tmp_path / 'registration.json'
    reg['minimum_population'] = 10000
    path.write_text(json.dumps(reg))
    with pytest.raises(ProtocolViolation, match='INSUFFICIENT_UNIQUE_POPULATION'):
        draw(path, tmp_path / 'small')
    assert not (tmp_path / 'small/bundles').exists()
    path.write_text(REG.read_text())
    result = draw(path, tmp_path / 'ok')
    a, b = [json.loads(Path(result['bundles'][m]).read_text()) for m in ('VERBATIM', 'DISPLACED')]
    assert len(a['tasks']) == len(b['tasks']) == reg['draws_per_mode']
    for x, y in zip(a['tasks'], b['tasks']):
        assert x['anchors'] == y['anchors'] and x['atoms'] == y['atoms']
        assert x['question'] == x['atoms'][0] and x['question'] != y['question']
    for bundle_path in result['bundles'].values():
        freeze = json.loads((Path(bundle_path).parent / 'freeze.json').read_text())
        assert freeze['sampling']['kind'] == 'random-query'
        assert freeze['sampling']['random_query_instrument'] is True


def test_missing_or_duplicate_arm_task_cells_refuse():
    reg = registration()
    rows = [dict(task=str(i), arm=a, correct=True) for i in range(reg['draws_per_mode']) for a in reg['arms']]
    with pytest.raises(ProtocolViolation, match='INCOMPLETE_INSTRUMENT_ROWS'):
        instrument_summary(rows[:-1], reg, 'VERBATIM')
    with pytest.raises(ProtocolViolation, match='INCOMPLETE_INSTRUMENT_ROWS'):
        instrument_summary(rows + [rows[0]], reg, 'VERBATIM')
