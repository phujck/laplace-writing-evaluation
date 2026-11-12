"""Offline reader assurance and import safety over a pinned retained execution.

No numerical/device run or historical builder effects occur. Writer main is
called only under effect traps to observe pre-effect protocol refusal. Labelled
fixture mutations test assurance, not renewed scientific measurements.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASE = "7eb7cfd2e"
WRITERS = (
    "evidence/ATLAS_PROGRAMME/waves/J3-integration-continued/j3_report.py",
    "evidence/ATLAS_PROGRAMME/waves/J3-integration-continued/profile_three_sizes.py",
    "evidence/ATLAS_PROGRAMME/waves/P3-the-read/update_report_c1.py",
)


@pytest.mark.parametrize("relative", WRITERS)
def test_historical_writer_import_has_no_report_io_process_or_path_mutation(monkeypatch, relative):
    def refuse(*args, **kwargs):
        pytest.fail("Historical writer import attempted a filesystem/process effect")
    for name in ("read_text", "read_bytes", "write_text", "write_bytes", "mkdir", "unlink"):
        monkeypatch.setattr(Path, name, refuse)
    for name in ("run", "Popen", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, refuse)
    before = list(sys.path)
    name = "historical_import_probe_" + Path(relative).stem
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert sys.path == before
    assert callable(module.main)
    assert "Historical reproduction only" in module.__doc__


def _body_without_doc(tree):
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        body.pop(0)
    return body


def _dump(nodes):
    return ast.dump(ast.Module(body=nodes, type_ignores=[]), include_attributes=False)


@pytest.mark.parametrize("relative", WRITERS)
def test_historical_execution_statement_order_is_preserved(relative):
    # Reading exactly these original tracked source blobs is not writer execution.
    original = ast.parse(subprocess.check_output(["git", "show", BASE + ":" + relative],
        cwd=ROOT, text=True))
    current = ast.parse((ROOT / relative).read_text())
    old, new = _body_without_doc(original), _body_without_doc(current)
    if relative.endswith("j3_report.py"):
        main = next(n for n in new if isinstance(n, ast.FunctionDef) and n.name == "main")
        main.body = main.body[2:]  # Public metadata refusal precedes original operations.
        assert _dump(new) == _dump(old)  # It already had a guard; only notice changed.
    elif relative.endswith("profile_three_sizes.py"):
        mutation = next(n for n in old if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                        and ast.unparse(n.value.func) == "sys.path.insert")
        old.remove(mutation)
        main = next(n for n in new if isinstance(n, ast.FunctionDef) and n.name == "main")
        # The pre-effect public-metadata guard is the only added execution gate.
        main.body = main.body[2:]
        assert ast.dump(main.body.pop(0), include_attributes=False) == ast.dump(mutation, include_attributes=False)
        assert _dump(new) == _dump(old)
    else:
        start = next(i for i, n in enumerate(old) if isinstance(n, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "d" for target in n.targets))
        main = next(n for n in new if isinstance(n, ast.FunctionDef) and n.name == "main")
        assert _dump(main.body[:-1]) == _dump(old[start:])
        assert isinstance(main.body[-1], ast.Return) and main.body[-1].value.value == 0
        assert _dump(new[:len(old[:start])]) == _dump(old[:start])
        assert isinstance(new[-1], ast.If) and ast.unparse(new[-1].test) == "__name__ == '__main__'"


@pytest.mark.parametrize("relative", WRITERS[:2])
def test_historical_runtime_refuses_current_or_missing_metadata_before_effects(monkeypatch, relative, capsys):
    from atlas.front import receipts  # Selected lightweight owner, before effect traps.
    name = "historical_runtime_probe_" + Path(relative).stem
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def refuse(*args, **kwargs):
        pytest.fail("Unsupported historical writer reached a read/write/process effect")
    for attr in ("read_text", "read_bytes", "write_text", "write_bytes", "mkdir"):
        monkeypatch.setattr(Path, attr, refuse)
    monkeypatch.setattr(subprocess, "run", refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    before = list(sys.path)
    assert module.main() == 2
    assert "atlas.historical-writer-refusal/1" in capsys.readouterr().out
    assert sys.path == before
    monkeypatch.delattr(receipts, "FRONT_DOOR_RUN_RECORD")
    assert module.main() == 2
    assert "unavailable" in capsys.readouterr().out
    assert sys.path == before

# These are explicitly labelled mutations of a retained execution, not fresh
# numerical/scientific observations or repairs of historical bytes.
import copy
import json
from test_front_receipt_protocol import legacy, rechain, stage
from atlas.front.receipts import serialize_dataset_run
from atlas.front.comparison import compare_observations, compare_cold_warm, compare_ablation


def _root(legacy, change=None, *, warm=False, canonical=True):
    run = copy.deepcopy(legacy)
    if warm:
        stage(run, 'ingest')['payload']['open_receipt'] = {
            'digests': copy.deepcopy(stage(run, 'ingest')['payload']['content_digests'])}
    if change:
        change(run)
    # The legacy redundant copy is kept deliberately consistent in fixtures.
    run['questions'] = copy.deepcopy(stage(run, 'read')['payload']['questions'])
    rechain(run)
    return {'record': 'atlas.front-door-run/2' if canonical else 'atlas.front-door-run/1', 'datasets': {
        'toy': serialize_dataset_run('toy', run) if canonical else run}, 'seconds': 1.0}


def _q(run):
    return stage(run, 'read')['payload']['questions'][0]


def _script(relative):
    spec = importlib.util.spec_from_file_location('reader_' + Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_complete_retained_comparison_and_cli_summary_use_canonical_questions(legacy):
    from atlas.front.__main__ import summarize_run
    root = _root(legacy)
    comparison = compare_observations(root, root)
    assert comparison['status'] == 'EQUIVALENT'
    assert comparison['coverage'] == {'toy': ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']}
    assert all(c['status'] == 'EQUIVALENT' for c in comparison['clauses'].values())
    summary = summarize_run(root)
    assert len(summary['datasets']['toy']['questions']) == 5
    assert summary['datasets']['toy']['chain_verified'] is True
    assert 'questions' not in root['datasets']['toy']


@pytest.mark.parametrize('change', [
    lambda r: r.update(record='atlas.front-door-run/99'),
    lambda r: r.update(datasets={}),
    lambda r: r['datasets'].update(other=r['datasets'].pop('toy')),
    lambda r: r['datasets']['toy']['receipt']['stages'][-1]['payload'].update(corruption=True),
    lambda r: r['datasets']['toy']['receipt']['chain'][-1].update(address='sha256:'+'0'*64),
    lambda r: r['datasets']['toy']['receipt']['stages'][-1].update(projection_version=99),
    lambda r: r['datasets'].update(toy=[]),
])
def test_malformed_version_terminal_chain_and_dataset_coverage_cannot_succeed(legacy, change):
    left = _root(legacy);right = copy.deepcopy(left);change(right)
    assert compare_observations(left, right)['status'] == 'UNPROVED'
    assert compare_cold_warm(left, right)['status'] == 'UNPROVED'


@pytest.mark.parametrize('change', [
    lambda r: stage(r, 'read')['payload'].update(questions=[]),
    lambda r: stage(r, 'read')['payload']['questions'].pop(),
    lambda r: stage(r, 'read')['payload']['questions'].append(copy.deepcopy(_q(r))),
    lambda r: _q(r)['partial'].pop('answer'),
    lambda r: _q(r)['partial'].pop('certificate'),
    lambda r: _q(r)['partial'].pop('refusal'),
    lambda r: _q(r)['whole']['executed'].pop('rows_admitted'),
    lambda r: _q(r)['partial'].pop('row_handles_total'),
    lambda r: _q(r)['partial'].update(row_handles_total=40),
    lambda r: _q(r)['partial'].update(range_handles_total=40),
    lambda r: _q(r)['partial']['row_handles'][0].update(row_id='truncated'),
])
def test_missing_required_fields_nonempty_exact_qids_and_truncated_identity_refuse(legacy, change):
    left = _root(legacy)
    right = _root(legacy, change, canonical=False)
    assert compare_observations(left, right)['status'] == 'UNPROVED'


def test_missing_is_distinct_from_explicit_null_and_real_count_or_identity_change(legacy):
    def nulls(run):
        for supply in ('partial', 'whole'):
            _q(run)[supply].update(answer=None, certificate=None, refusal=None)
        _q(run)['known_answer'] = None
        _q(run)['answer_equals_the_known_answer'] = None
    root = _root(legacy, nulls)
    assert compare_observations(root, root)['status'] == 'EQUIVALENT'
    counted = _root(legacy, lambda r: _q(r)['partial']['executed'].update(rows_admitted=123))
    assert compare_observations(_root(legacy), counted)['clauses']['admitted_counts']['status'] == 'DIFFERENT'
    changed = _root(legacy, lambda r: _q(r)['partial']['row_handles'][0].update(content_handle='sha256:'+'f'*64))
    assert compare_observations(_root(legacy), changed)['clauses']['represented_identity']['status'] == 'DIFFERENT'


def test_answer_equivalence_is_separate_from_planner_and_occurrence_claims(legacy):
    left = _root(legacy)
    def calibration(run):
        stage(run, 'faces')['executed']['cost_model']['launch_seconds'] = 123.0
        stage(run, 'read')['payload']['cost_model']['launch_seconds'] = 123.0
    right = _root(legacy, calibration)
    result = compare_observations(left, right)
    assert result['status'] == 'EQUIVALENT'
    assert result['clauses']['planner_decisions']['status'] == 'DIFFERENT'
    assert compare_cold_warm(left, right)['status'] == 'DIFFERENT'
    ordinal = _root(legacy, lambda r: _q(r)['partial']['row_handles'][0].update(global_ordinal=123))
    result = compare_observations(left, ordinal)
    assert result['status'] == 'EQUIVALENT'
    assert result['clauses']['represented_identity']['status'] == 'EQUIVALENT'
    assert result['clauses']['exact_occurrence']['status'] == 'DIFFERENT'


def test_timers_only_same_consumed_basis_and_decision_seconds_retained(legacy):
    left = _root(legacy)
    timing = _root(legacy, lambda r: _q(r)['partial']['executed'].update(answer_seconds=99.0))
    assert compare_cold_warm(left, timing)['status'] == 'EQUIVALENT'
    decision = _root(legacy, lambda r: _q(r)['plan']['costs'][0].update(seconds_predicted=99.0))
    assert compare_cold_warm(left, decision)['clauses']['planner_decisions']['status'] == 'DIFFERENT'


def test_normalize_once_per_dataset_each_arm_without_mutating_inputs(legacy, monkeypatch):
    import atlas.front.comparison as owner
    arms = [_root(legacy), _root(legacy), _root(legacy, warm=True), _root(legacy, warm=True)]
    before = copy.deepcopy(arms);calls = [];actual = owner.inspect_dataset_run
    def counted(run):
        calls.append(run)
        return actual(run)
    monkeypatch.setattr(owner, 'inspect_dataset_run', counted)
    result = compare_ablation(*arms)
    assert result['status'] == 'EQUIVALENT'
    assert len(calls) == 4 and arms == before
    assert result['source_basis']['toy']['record_digests'][0] == result['source_basis']['toy']['record_digests'][2]
    assert result['ingest_counts']['toy']['rows'] == [10]*4


@pytest.mark.parametrize('change,expected', [
    (lambda r: stage(r, 'ingest')['payload']['open_receipt']['digests'].update(record='sha256:'+'f'*64), 'DIFFERENT'),
    (lambda r: stage(r, 'ingest')['payload']['open_receipt']['digests'].pop('record'), 'UNPROVED'),
    (lambda r: stage(r, 'ingest')['executed'].update(relations=123), 'DIFFERENT'),
    (lambda r: stage(r, 'ingest')['executed'].pop('rows'), 'UNPROVED'),
    (lambda r: stage(r, 'declare')['payload'].pop('declaration_hash'), 'UNPROVED'),
    (lambda r: stage(r, 'read')['payload']['questions'].pop(), 'UNPROVED'),
])
def test_four_arm_p1_cold_warm_digest_and_required_ingest_counts_enter_verdict(legacy, change, expected):
    arms = [_root(legacy), _root(legacy), _root(legacy, warm=True), _root(legacy, change, warm=True, canonical=False)]
    assert compare_ablation(*arms)['status'] == expected


def test_cli_summary_refuses_corrupted_stored_success_and_missing_answer(legacy):
    from atlas.front.__main__ import summarize_run
    from atlas.front.receipts import ReceiptProtocolError
    broken = _root(legacy);broken['datasets']['toy']['receipt']['stages'][-1]['payload']['bad'] = True
    with pytest.raises(ReceiptProtocolError):summarize_run(broken)
    missing = _root(legacy, lambda r: _q(r)['partial'].pop('answer'))
    with pytest.raises(ReceiptProtocolError):summarize_run(missing)


@pytest.mark.parametrize('relative,function', [
    ('evidence/ATLAS_PROGRAMME/waves/J3-integration-continued/synthesis/compare_runs.py', 'compare_observations'),
    ('evidence/ATLAS_PROGRAMME/waves/J4-widenings/compare_cold_warm.py', 'compare_cold_warm'),
])
def test_arbitrary_input_wrappers_use_shared_owner_and_scoped_exit_codes(legacy, tmp_path, capsys, relative, function):
    module = _script(relative)
    left = tmp_path/'left.json';right = tmp_path/'right.json'
    left.write_text(json.dumps(_root(legacy)));right.write_text(left.read_text())
    assert module.main([str(left), str(right)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'EQUIVALENT'
    right.write_text(json.dumps({'record': 'atlas.front-door-run/99', 'datasets': {}}))
    assert module.main([str(left), str(right)]) == 2
    assert json.loads(capsys.readouterr().out)['status'] == 'UNPROVED'
    assert getattr(module, function).__module__ == 'atlas.front.comparison'


def test_fixed_output_wrappers_refuse_overwrite_before_input_and_p3_stays_unproved(tmp_path, capsys):
    output = tmp_path/'retained.json';output.write_text('retained bytes')
    p1 = _script('evidence/ATLAS_PROGRAMME/waves/P1-the-leaf/ablation_off_is_today.py')
    assert p1.main(['--on', 'absent', '--off', 'absent', '--on-warm', 'absent', '--off-warm', 'absent', '--out', str(output)]) == 2
    assert 'overwrit' in capsys.readouterr().out.lower()
    p3 = _script('evidence/ATLAS_PROGRAMME/waves/P3-the-read/door_census.py')
    assert p3.main(['--receipt', 'absent', '--out', str(output)]) == 2
    assert output.read_text() == 'retained bytes'
    result = p3.census_of_run({'record': 'atlas.front-door-run/2', 'datasets': {}})
    assert result['status'] == 'UNPROVED' and 'reach_fraction' not in result


def test_p1_all_empty_missing_digests_and_truncated_counts_are_not_equivalence(legacy):
    empty = {'record': 'atlas.front-door-run/2', 'datasets': {}}
    assert compare_ablation(empty, empty, empty, empty)['status'] == 'UNPROVED'
    arms = [_root(legacy), _root(legacy), _root(legacy, warm=True), _root(legacy, warm=True)]
    def missing_digest(run):
        stage(run, 'ingest')['payload']['content_digests'].pop('record')
    arms[0] = _root(legacy, missing_digest)
    assert compare_ablation(*arms)['status'] == 'UNPROVED'
    arms[0] = _root(legacy, lambda r: _q(r)['partial'].update(row_handles_total=40))
    assert compare_ablation(*arms)['status'] == 'UNPROVED'


def test_p1_wrapper_retains_fresh_scoped_result_and_p3_no_current_ingestion(legacy, tmp_path, capsys):
    arms = [_root(legacy), _root(legacy), _root(legacy, warm=True), _root(legacy, warm=True)]
    paths = []
    for index, arm in enumerate(arms):
        path = tmp_path/f'arm-{index}.json';path.write_text(json.dumps(arm));paths.append(str(path))
    output = tmp_path/'new-comparison.json'
    module = _script('evidence/ATLAS_PROGRAMME/waves/P1-the-leaf/ablation_off_is_today.py')
    args = [part for flag, path in zip(('--on', '--off', '--on-warm', '--off-warm'), paths) for part in (flag, path)]
    assert module.main(args + ['--out', str(output)]) == 0
    result = json.loads(output.read_text())
    assert result['status'] == 'EQUIVALENT' and result['record'] == 'atlas.p1.ablation/2'
    assert result['source_basis']['toy']['declaration_hashes']
    capsys.readouterr()
    census = _script('evidence/ATLAS_PROGRAMME/waves/P3-the-read/door_census.py')
    old = copy.deepcopy(legacy);old['dataset'] = 'longmem';rechain(old)
    root = {'record': 'atlas.front-door-run/1', 'datasets': {'longmem': old}}
    observed = census.census_of_run(root)
    assert observed['status'] == 'UNPROVED' and observed['questions_in_receipt'] == 5
    assert observed['required_work'] == 'WORK-atlas-census-evidence-20261008'
    assert not any(name in observed for name in ('reach_fraction', 'rows_got', 'rows_needed'))


def test_cli_summary_empty_or_missing_controls_refuse_instead_of_null_success(legacy):
    from atlas.front.__main__ import summarize_run
    from atlas.front.receipts import ReceiptProtocolError
    with pytest.raises(ReceiptProtocolError, match='nonempty dataset'):
        summarize_run({'record': 'atlas.front-door-run/2', 'datasets': {}, 'seconds': 1.0})
    missing = _root(legacy, lambda r: _q(r).pop('answer_equals_the_flat_control'))
    with pytest.raises(ReceiptProtocolError, match='control agreement'):
        summarize_run(missing)
    explicit_null = _root(legacy, lambda r: _q(r).update(known_answer=None, answer_equals_the_known_answer=None))
    assert summarize_run(explicit_null)['datasets']['toy']['questions'][0]['equals_the_known_answer'] is None


def _growth_root(legacy, count):
    """Retained fixture projection only; repeated tasks are not new science."""
    fixture = copy.deepcopy(legacy);prototype = _q(fixture)
    compiled = stage(fixture, 'question')['payload']['compiled'][0]
    rows = [];compiled_rows = []
    for index in range(count):
        qid = f'comparison-cost-fixture:{index}'
        row = copy.deepcopy(prototype);row['qid'] = qid;row['plan']['qid'] = qid
        for supply in ('partial', 'whole'):row[supply]['qid'] = qid
        rows.append(row);item = copy.deepcopy(compiled);item['spec']['qid'] = qid;compiled_rows.append(item)
    stage(fixture, 'read')['payload']['questions'] = rows
    stage(fixture, 'question')['payload']['compiled'] = compiled_rows
    stage(fixture, 'question')['diagnostics']['compiled_seconds'] = [0.0]*count
    planner = stage(fixture, 'read')['payload']['planner']
    planner['routes'] = {row['qid']: row['plan']['route'] for row in rows}
    planner['planning_seconds_per_question'] = {row['qid']: 0.0 for row in rows}
    fixture['receipt']['draw'] = {'fixture_kind': 'comparison_cost_growth', 'questions': count, 'not_device_execution': True}
    return _root(fixture)


def test_batched_comparison_hash_calls_depend_on_stages_not_question_count(legacy, monkeypatch):
    from atlas.front import receipts
    from atlas import ids
    import atlas.front.comparison as owner
    actual = receipts.chash;sha = ids.hashlib.sha256
    counts = {'calls': 0, 'bytes': 0, 'inside': False, 'observations': 0}
    inspection = owner.inspect_dataset_run
    def inspected(run):
        counts['observations'] += 1
        return inspection(run)
    def hashed_bytes(data=b'', *args, **kwargs):
        if counts['inside']:counts['bytes'] += len(data)
        return sha(data, *args, **kwargs)
    def hashed(value):
        counts['calls'] += 1;counts['inside'] = True
        try:return actual(value)
        finally:counts['inside'] = False
    monkeypatch.setattr(owner, 'inspect_dataset_run', inspected)
    observations = []
    for size in (10, 50):
        root = _growth_root(legacy, size)
        counts.update(calls=0, bytes=0, observations=0)
        with monkeypatch.context() as scope:
            scope.setattr(receipts, 'chash', hashed)
            scope.setattr(ids.hashlib, 'sha256', hashed_bytes)
            assert compare_observations(root, root)['status'] == 'EQUIVALENT'
        observations.append(dict(counts))
    assert observations[0]['calls'] == observations[1]['calls'] <= 36
    assert observations[0]['observations'] == observations[1]['observations'] == 2
    assert observations[0]['bytes'] < observations[1]['bytes'] <= 6*observations[0]['bytes']


def test_same_qid_is_not_same_task_and_oracle_description_is_separate(legacy):
    left = _root(legacy)
    def operation(run):
        stage(run, 'question')['payload']['compiled'][0]['spec']['operator']['name'] = 'different_declared_operation'
    result = compare_observations(left, _root(legacy, operation))
    assert result['status'] == 'UNPROVED'
    assert result['clauses']['task_basis']['status'] == 'DIFFERENT'
    assert result['clauses']['answers_and_controls']['status'] == 'EQUIVALENT'
    def oracle(run):
        stage(run, 'question')['payload']['compiled'][0]['spec']['known_answer_source'] = 'different fixture oracle description'
        _q(run)['known_answer_source'] = 'different fixture oracle description'
    result = compare_observations(left, _root(legacy, oracle))
    assert result['status'] == 'EQUIVALENT'
    assert result['clauses']['task_basis']['status'] == 'EQUIVALENT'
    assert result['clauses']['oracle_basis']['status'] == 'DIFFERENT'


def test_declared_condition_and_dataset_identity_scope_differ_even_with_equal_outputs(legacy):
    left = _root(legacy)
    def condition(run):
        stage(run, 'question')['payload']['compiled'][0]['spec']['conditions'][0]['surfaces'] = ['different logical condition']
    assert compare_observations(left, _root(legacy, condition))['status'] == 'UNPROVED'
    def dataset(run):
        run['receipt']['dataset_id'] = 'different-record'
        stage(run, 'declare')['payload']['dataset_id'] = 'different-record'
        for row in stage(run, 'question')['payload']['compiled']:row['spec']['dataset_id'] = 'different-record'
    result = compare_observations(left, _root(legacy, dataset))
    assert result['status'] == 'UNPROVED'
    assert result['clauses']['task_basis']['status'] == 'DIFFERENT'


def test_digest_spelling_is_normalized_for_semantic_handle_identity(legacy):
    left = _root(legacy)
    def bare(run):
        for supply in ('partial', 'whole'):
            for row in _q(run)[supply]['row_handles']:
                for key in ('row_id', 'content_handle'):row[key] = row[key].removeprefix('sha256:')
            for row in _q(run)[supply]['range_handles']:
                for key in ('lens_hash', 'component_address', 'condition_digest'):row[key] = row[key].removeprefix('sha256:')
    result = compare_observations(left, _root(legacy, bare))
    assert result['status'] == 'EQUIVALENT'
    assert result['clauses']['represented_identity']['status'] == 'EQUIVALENT'


def test_resolved_tolerance_recipe_difference_remains_substantive(legacy):
    left = _root(legacy)
    def tolerance(run):
        for row in stage(run, 'question')['payload']['compiled']:
            for value in row['tolerances']:
                if value['name'] == 'one_row_of_the_answering_kind':value['derivation'] = 'Different independently authored precision recipe.'
        for row in stage(run, 'read')['payload']['questions']:
            for supply in ('partial', 'whole'):
                if row[supply]['tolerance']['name'] == 'one_row_of_the_answering_kind':
                    row[supply]['tolerance']['derivation'] = 'Different independently authored precision recipe.'
    right = _root(legacy, tolerance)
    result = compare_observations(left, right)
    assert result['status'] == 'EQUIVALENT'
    assert result['clauses']['tolerance_meaning']['status'] == 'DIFFERENT'
    assert compare_cold_warm(left, right)['status'] == 'DIFFERENT'


def test_owner_observation_is_detached_and_new_observation_revalidates(legacy):
    from atlas.front.receipts import inspect_dataset_run, ReceiptProtocolError
    root = _root(legacy);original = root['datasets']['toy']
    view = inspect_dataset_run(original)
    before = copy.deepcopy(view)
    stage(original, 'read')['payload']['questions'][0]['partial']['answer'] = 'changed after observation'
    assert view == before
    with pytest.raises(ReceiptProtocolError):inspect_dataset_run(original)
    fresh = _root(legacy, lambda r: _q(r)['partial'].update(answer='new retained answer'))
    current = inspect_dataset_run(fresh['datasets']['toy'])
    assert current['questions'][0]['partial']['answer'] == 'new retained answer'
    assert view['questions'][0]['partial']['answer'] != 'new retained answer'


def test_missing_numeric_precision_is_unproved_for_decision_scope(legacy):
    left = _root(legacy)
    right = _root(legacy, lambda r: _q(r)['partial']['tolerance'].pop('tau'))
    result = compare_observations(left, right)
    assert result['status'] == 'EQUIVALENT'
    assert result['clauses']['tolerance_meaning']['status'] == 'UNPROVED'
    assert compare_cold_warm(left, right)['status'] == 'UNPROVED'


def test_no_oracle_is_not_asserted_but_missing_or_present_oracle_evidence_refuses(legacy):
    from atlas.front.__main__ import summarize_run
    from atlas.front.receipts import ReceiptProtocolError
    def no_oracle(run):
        _q(run)['known_answer'] = None
        _q(run).pop('answer_equals_the_known_answer')
        stage(run, 'question')['payload']['compiled'][0]['spec']['known_answer'] = None
    absent = _root(legacy, no_oracle)
    result = compare_observations(absent, absent)
    assert result['status'] == 'EQUIVALENT'
    assert result['clauses']['oracle_basis']['not_asserted']['left']['toy'] == ['Q1']
    assert summarize_run(absent)['datasets']['toy']['questions'][0]['equals_the_known_answer'] is None
    for change in (
        lambda r: _q(r).pop('known_answer'),
        lambda r: _q(r).pop('answer_equals_the_known_answer'),
        lambda r: _q(r).update(answer_equals_the_known_answer=None),
        lambda r: _q(r).update(known_answer=None, answer_equals_the_known_answer=True),
    ):
        missing = _root(legacy, change)
        assert compare_observations(missing, missing)['status'] == 'UNPROVED'
        with pytest.raises(ReceiptProtocolError):summarize_run(missing)
    false = _root(legacy, lambda r: _q(r).update(answer_equals_the_known_answer=False))
    assert compare_observations(false, false)['status'] == 'EQUIVALENT'
    assert summarize_run(false)['datasets']['toy']['questions'][0]['equals_the_known_answer'] is False
