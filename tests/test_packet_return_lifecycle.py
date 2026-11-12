"""Versioned truthful handoffs, current result identity and incomplete consumer standing."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest
from laplace.pipeline import workflow

TREE = Path(__file__).resolve().parents[1]
SCHEMAS = TREE / 'profiles/workflows'


def pin(path):
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


@pytest.fixture
def fixture(tmp_path):
    source, output = tmp_path / 'source.txt', tmp_path / 'output.txt'
    source.write_text('declared source bytes\n')
    output.write_text('retained result bytes\n')
    return {'schema_version': 'laplace.packet-return/2', 'packet': 'one', 'role': 'build',
            'status': 'COMPLETE', 'goal': 'Complete the declared fixture result',
            'inputs': [pin(source)],
            'source': {'kind': 'artifacts', 'root': str(tmp_path), 'artifacts': [pin(source)]},
            'output': pin(output), 'files_written': ['output.txt'],
            'summary': 'The fixture result is retained and its bytes are pinned',
            'most_important': ['Output and source are verified exact byte identities'],
            'scripted_check': {'kind': 'command', 'state': 'PASSED', 'command': 'read fixture bytes',
                               'exit_code': 0, 'output_tail': 'fixture bytes verified'},
            'residuals': [], 'remaining_work': [], 'continuation': None}


def partial(fixture, status):
    document = copy.deepcopy(fixture)
    document['status'] = status
    document['remaining_work'] = [{'work': 'Finish the remaining fixture step',
                                   'reason': 'Observed provider quota prevented the remaining step' if status == 'INTERRUPTED' else 'The declared dependency remains absent',
                                   'next_action': 'Read retained bytes and complete the fixture step'}]
    document['continuation'] = {'artifacts': document['inputs'],
                                'next_action': 'Inspect retained source before continuing',
                                'resume_condition': 'Provider quota is restored and retained bytes match' if status == 'INTERRUPTED' else 'The declared dependency is supplied and retained effects are inspected'}
    document['scripted_check'].update(state='NOT_RUN', exit_code=None, output_tail='The declared check was not run after the observed interruption')
    return document


def resolve_within(root):
    def resolve(path):
        value = Path(path)
        value = (value if value.is_absolute() else root / value).resolve()
        if value != root and root not in value.parents:
            raise ValueError('path escapes declared fixture scope')
        return value
    return resolve


def problems(document, root, **kwargs):
    return workflow.packet_return_problems(document, schema_directory=SCHEMAS,
                                           resolve_pin=resolve_within(root), **kwargs)


def distil(monkeypatch, root):
    spec = importlib.util.spec_from_file_location('return_lifecycle_distil', TREE / 'scripts/distil.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', str(root))
    return module


def legacy(fixture):
    document = copy.deepcopy(fixture)
    document['schema_version'] = 'laplace.packet-return/1'
    document['source'] = {'branch': 'codex/schema-fixture', 'base_commit': 'a' * 40,
                          'candidate': 'b' * 40, 'candidate_parent': 'a' * 40,
                          'candidate_tree': 'c' * 40, 'worktree': fixture['source']['root']}
    document['output'] = fixture['output']['path']
    document['scripted_check'].pop('state')
    document['scripted_check'].pop('kind')
    document.pop('remaining_work')
    document.pop('continuation')
    return document


def judgement(document, return_path):
    return {'schema_version': 'laplace.packet-judgement/2', 'packet': 'one',
            'round': 1, 'max_rounds': 2, 'accepted': True,
            'judged': {'kind': 'artifacts', 'return_artifact': pin(return_path),
                       'output': document['output'],
                       'review_context': {'kind': 'independent-session', 'session_id': 'judge-session', 'read_only': True}},
            'scripted_check': copy.deepcopy(document['scripted_check']),
            'checked': [{'item': 'retained result', 'how': 'Read source and output through declared owner'}],
            'accepted_subsets': [{'id': 'fixture-result', 'status': 'ACCEPTED', 'finding': 'Exact retained bytes match'}],
            'deficiencies': [],
            'own_observations': [{'kind': 'command', 'command': 'declared-owner read fixture output', 'exit_code': 0,
                                  'output_tail': 'Output bytes independently observed'}]}


def test_old_profile_bytes_and_receipt_validation_are_preserved(fixture, tmp_path):
    for name in ('packet-return.schema.json', 'packet-judgement.schema.json'):
        original = subprocess.check_output(['git', '-C', str(TREE), 'show',
                                            '42f3f3a84:profiles/workflows/' + name])
        assert (SCHEMAS / name).read_bytes() == original
    assert not problems(legacy(fixture), tmp_path)


def test_new_profiles_selected_without_replacing_old_versions(monkeypatch, tmp_path):
    module = distil(monkeypatch, tmp_path)
    assert module._current_schema_id(module.RETURN_FAMILY) == 'laplace.packet-return/2'
    assert module._current_schema_id(module.JUDGEMENT_FAMILY) == 'laplace.packet-judgement/2'
    assert module._schema_file('laplace.packet-return/1').endswith('packet-return.schema.json')
    assert module._schema_file('laplace.packet-judgement/1').endswith('packet-judgement.schema.json')


@pytest.mark.parametrize('status', ['INCOMPLETE', 'BLOCKED', 'INTERRUPTED'])
def test_noncomplete_return_has_meaningful_retained_continuation(fixture, tmp_path, status):
    document = partial(fixture, status)
    assert not problems(document, tmp_path)
    document['remaining_work'] = []
    assert problems(document, tmp_path)
    document = partial(fixture, status)
    document['continuation'] = None
    assert problems(document, tmp_path)


def test_noncomplete_can_retain_null_git_checkpoint_without_inventing_completion(fixture, tmp_path):
    document = partial(fixture, 'INTERRUPTED')
    document['source'] = {'kind': 'git', **legacy(fixture)['source']}
    for field in ('candidate', 'candidate_parent', 'candidate_tree'): document['source'][field] = None
    assert not problems(document, tmp_path)
    document.update(status='COMPLETE', remaining_work=[], continuation=None)
    document['scripted_check'].update(state='PASSED', exit_code=0)
    assert problems(document, tmp_path)


def test_complete_no_git_source_and_current_output_are_pinned(fixture, tmp_path):
    assert not (tmp_path / '.git').exists()
    assert not problems(fixture, tmp_path)
    assert problems(fixture, tmp_path, requires_git_checkpoint=True)
    Path(fixture['output']['path']).write_text('later changed bytes\n')
    assert any('output' in error for error in problems(fixture, tmp_path))


def test_source_root_does_not_authorize_out_of_scope_reads(fixture, tmp_path):
    fixture['source']['root'] = '/unrelated/provenance-only'
    assert not problems(fixture, tmp_path)
    fixture['source']['artifacts'][0]['path'] = '/unrelated/provenance-only/private.txt'
    assert any('scope' in error for error in problems(fixture, tmp_path))


def test_complete_never_accepts_remaining_work_or_unrun_check(fixture, tmp_path):
    fixture['scripted_check'].update(state='NOT_RUN', exit_code=None)
    assert problems(fixture, tmp_path)
    fixture = partial(fixture, 'INCOMPLETE')
    fixture.update(status='COMPLETE')
    assert problems(fixture, tmp_path)


def test_independent_artifact_judge_pins_return_and_output(fixture, tmp_path):
    returned = tmp_path / 'return.json'
    returned.write_text(json.dumps(fixture))
    document = judgement(fixture, returned)
    assert not problems(document, tmp_path, review_session_id='judge-session')
    assert problems(document, tmp_path, review_session_id='other-session')
    Path(fixture['output']['path']).write_text('changed output with unchanged return file\n')
    assert problems(document, tmp_path)


def test_judge_acceptance_cannot_certify_incomplete_builder(fixture, tmp_path):
    returned = tmp_path / 'return.json'
    incomplete = partial(fixture, 'INCOMPLETE')
    returned.write_text(json.dumps(incomplete))
    document = judgement(fixture, returned)
    assert any('COMPLETE' in error for error in problems(document, tmp_path))


def test_quota_before_authored_return_preserves_existing_interruption_rules():
    # The legacy run-local transport already distinguishes incomplete decisions;
    # /2 does not replace its frozen manifest/schema or turn it into a replay loop.
    assert 'incomplete' in workflow.RETURN_SCHEMA['properties']['decision']['enum']
    source = (TREE / 'src/laplace/pipeline/workflow.py').read_text()
    assert 'reconcile exact evidence before a new run; no writer replay' in source


def test_banker_keeps_incomplete_work_despite_accepted_legacy_judge(fixture, tmp_path, monkeypatch):
    module = distil(monkeypatch, tmp_path)
    (tmp_path / 'contract').mkdir()
    out = tmp_path / 'wave'
    (out / 'one').mkdir(parents=True)
    incomplete = partial(fixture, 'INCOMPLETE')
    (out / 'one/return.json').write_text(json.dumps(incomplete))
    judge = judgement(fixture, out / 'one/return.json')
    judge['schema_version'] = 'laplace.packet-judgement/1'
    judge['judged'] = {'candidate': 'b' * 40, 'review_checkout': str(tmp_path / 'review')}
    judge['scripted_check'].pop('state')
    judge['scripted_check'].pop('kind')
    judge['own_observations'][0].pop('kind')
    (out / 'one/verdict.r1.json').write_text(json.dumps(judge))
    plan = {'wave': 'return-lifecycle-fixture', 'plan_path': str(out / 'plan.json'), 'out_dir': str(out),
            'agents': [{'label': 'one', 'tier': 'deep', 'effort': 'high', 'output': fixture['output']['path']}]}
    (out / 'plan.json').write_text(json.dumps(plan))
    args = SimpleNamespace(from_dir=str(out), plan=str(out / 'plan.json'), wave=plan['wave'],
                           waves=None, partial=False, provider='codex', executor=None, sandbox=None)
    assert module.cmd_wave_rows(args) == 0
    rows = [json.loads(line) for line in (tmp_path / 'contract/dispatches.jsonl').read_text().splitlines()]
    result = [row for row in rows if row['record'] == 'workflow'][-1]
    assert result['status'] == 'INCOMPLETE' and result['accepted'] is False
    assert result['packets_not_accepted'] == ['one']


def test_stage_receipt_keeps_noncomplete_builder_unaccepted(fixture, tmp_path, monkeypatch):
    module = distil(monkeypatch, tmp_path)
    wave = 'stage-lifecycle-fixture'
    directory = tmp_path / 'waves' / wave
    directory.mkdir(parents=True)
    (directory / 'returns.json').write_text(json.dumps({'run_dir': str(directory), 'returns': [
        {'agentId': 'builder', 'result': partial(fixture, 'BLOCKED')}]}))
    contract = tmp_path / 'contract'
    contract.mkdir()
    (contract / 'judged_verdicts.jsonl').write_text(json.dumps({'subject': 'one (wave fixture)',
        'wave': wave, 'verdict': 'ACCEPTED', 'judge_context': 'independent-session', 'id': 'verdict-fixture'})+'\n')
    (tmp_path / 'corpus_friction').mkdir()
    (tmp_path / 'corpus_friction/campaign.jsonl').write_text('')
    monkeypatch.setattr(module, 'WAVES_DIR', str(tmp_path / 'waves'))
    monkeypatch.setattr(module, 'STAGE_EVIDENCE', str(tmp_path / 'stages'))
    monkeypatch.setattr(module, '_run_labels', lambda _: ({'builder': {'label': 'build:one'}}, 'fixture'))
    args = SimpleNamespace(stage='STAGE', from_wave=[wave], builder_context='builder-fixture')
    assert module.cmd_stage_receipt(args) == 0
    receipt = json.loads((tmp_path / 'stages/STAGE/acceptance.json').read_text())
    assert receipt['status'] == 'FAIL'
    assert any('BLOCKED' in reason for reason in receipt['why_not_pass'])


def test_real_owner_read_receipt_binds_without_invented_command_exit(fixture, tmp_path):
    from laplace.native import tools as writing_tools
    from laplace.writing import session_reads
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [
        {'name': 'one', 'kind': 'conceptric', 'project_dir': '.'}]}))
    contract = tmp_path / 'contract'
    contract.mkdir()
    rows = [{'record': 'writing-session', 'id': 'worker-session', 'project': 'one',
             'role': 'author', 'packet': 'one'},
            {'record': 'writing-turn', 'id': 'worker-turn', 'project': 'one',
             'session_id': 'worker-session', 'mode': 'work'}]
    (contract / 'talk.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    result = writing_tools.execute(tmp_path, 'one', 'work', 'read_artifact',
                                   {'path': 'output.txt'}, turn_id='worker-turn')
    receipt = result['read_receipt']
    check = {'kind': 'owner-read', 'state': 'PASSED', 'operation': 'read_artifact',
             'payload': {'path': 'output.txt'}, 'receipt_id': receipt['id'],
             'output_sha256': receipt['output_sha256'], 'ok': True,
             'output_tail': 'Exact retained output read through its declared owner'}
    fixture['scripted_check'] = check
    verifier = workflow.packet_owner_read_verifier(tmp_path)
    assert not problems(fixture, tmp_path, verify_owner_read=verifier)
    assert problems(fixture, tmp_path)
    assert problems(fixture, tmp_path, verify_owner_read=verifier, requires_command_check=True)
    check['receipt_id'] = 'READ-'+'f'*32
    assert problems(fixture, tmp_path, verify_owner_read=verifier)
    assert session_reads._records(tmp_path)['read_receipts'][receipt['id']]['turn_id'] == 'worker-turn'


def test_existing_declared_command_field_cannot_be_weakened(monkeypatch, tmp_path):
    module = distil(monkeypatch, tmp_path)
    assert module._requires_command_check({'check': 'python real_check.py', 'requires_command_check': False})
    assert module._requires_command_check({}, {'check_template': 'python real_check.py'})
    assert not module._requires_command_check({'requires_command_check': False})


def test_independent_owner_read_judge_uses_actual_receipt_and_preserves_superseded_ids(fixture, tmp_path):
    from laplace.native import tools as writing_tools
    from laplace.writing import session_reads
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [
        {'name': 'one', 'kind': 'conceptric', 'project_dir': '.'}]}))
    contract = tmp_path / 'contract'
    contract.mkdir()
    rows = [{'record': 'writing-session', 'id': 'judge-session', 'project': 'one',
             'role': 'review', 'packet': 'judge-one'},
            {'record': 'writing-turn', 'id': 'judge-turn', 'project': 'one',
             'session_id': 'judge-session', 'mode': 'review'}]
    (contract / 'talk.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    first = writing_tools.execute(tmp_path, 'one', 'review', 'read_artifact',
                                  {'path': 'output.txt'}, turn_id='judge-turn')['read_receipt']
    second = writing_tools.execute(tmp_path, 'one', 'review', 'read_artifact',
                                   {'path': 'output.txt'}, turn_id='judge-turn')['read_receipt']
    assert first['id'] != second['id'] and first['output_sha256'] == second['output_sha256']
    assert first['id'] in session_reads._records(tmp_path)['read_receipts']
    returned = tmp_path / 'return.json'
    returned.write_text(json.dumps(fixture))
    document = judgement(fixture, returned)
    check = {'kind': 'owner-read', 'state': 'PASSED', 'operation': 'read_artifact',
             'payload': {'path': 'output.txt'}, 'receipt_id': first['id'],
             'output_sha256': first['output_sha256'], 'ok': True,
             'output_tail': 'Independent owner read observed exact output bytes'}
    document['scripted_check'] = check
    observation = dict(check)
    observation.pop('state')
    document['own_observations'] = [observation]
    verifier = workflow.packet_owner_read_verifier(tmp_path)
    assert not problems(document, tmp_path, verify_owner_read=verifier, review_session_id='judge-session')
    document['own_observations'][0]['payload'] = {'path': 'source.txt'}
    assert problems(document, tmp_path, verify_owner_read=verifier)


def test_ledger_currentness_keeps_recorded_acceptance_but_detects_output_drift(fixture, tmp_path, monkeypatch):
    module = distil(monkeypatch, tmp_path)
    out = tmp_path / 'wave'
    (out / 'one').mkdir(parents=True)
    (tmp_path / 'contract').mkdir()
    (out / 'one/return.json').write_text(json.dumps(fixture))
    plan = {'wave': 'currentness-fixture', 'plan_path': str(out / 'plan.json'), 'out_dir': str(out),
            'agents': [{'label': 'one', 'tier': 'deep', 'effort': 'high', 'output': fixture['output']['path']}]}
    judge = judgement(fixture, out / 'one/return.json')
    (out / 'one/verdict.r1.json').write_text(json.dumps(judge))
    (out / 'plan.json').write_text(json.dumps(plan))
    args = SimpleNamespace(from_dir=str(out), plan=str(out / 'plan.json'), wave=plan['wave'],
                           waves=None, partial=False, provider='codex', executor=None, sandbox=None)
    module.cmd_wave_rows(args)
    rows = [json.loads(line) for line in (tmp_path / 'contract/dispatches.jsonl').read_text().splitlines()]
    row = [row for row in rows if row['record'] == 'workflow'][-1]
    run = tmp_path / 'evidence/WORKFLOWS' / row['id']
    before = workflow.inspect_run(run)
    assert before['accepted'] is True
    Path(fixture['output']['path']).write_text('later changed output without changed return bytes\n')
    after = workflow.inspect_run(run)
    assert after['status'] == 'RECORDED-ARTIFACTS-MOVED' and after['accepted'] is False
    assert after['recorded_accepted'] is True


@pytest.mark.parametrize('legacy_worker', [False, True])
def test_accepted_judgement_checks_worker_consumed_inputs(fixture, tmp_path, legacy_worker):
    dependency = tmp_path / 'dependency.txt'
    dependency.write_text('consumed input')
    fixture['inputs'].append(pin(dependency))
    document = legacy(fixture) if legacy_worker else fixture
    returned = tmp_path / 'builder.json'
    returned.write_text(json.dumps(document))
    verdict = judgement(fixture, returned)
    assert not problems(verdict, tmp_path)
    dependency.write_text('changed input')
    assert any('judged worker: inputs/' in error for error in problems(verdict, tmp_path))
