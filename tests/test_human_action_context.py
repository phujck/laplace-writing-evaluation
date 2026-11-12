"""One public failed-review action; execution is intercepted before any provider."""
import copy
import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from test_app_workflow_dispatch import prepared
from test_failed_review_continuation import partial
from laplace.core import identity, bodies
from laplace.pipeline import workflow_definitions as D
from laplace.work import owner_discovery as O, project_work as W
from laplace.projects import artifacts
from laplace.representation import writing_bodies
from laplace.writing import records, child_hosts, workflow_dispatch as A, turn_admission as T, session_reads
from laplace.web import authoring_http


def compose(case, **extra):
    root, ident, _, _ = case
    task = W._tasks('book', root)[ident]
    return D.read(root, O.project_scope('book', 'sdk'), {
        'reference': task['prepared_workflow']['reference'], 'facet': 'app-continue-compose',
        'work_id': ident, 'step_id': 'Review', 'request_id': 'child-continue-é', **extra})


def submission(case):
    value = compose(case)
    return {**value['action']['payload'], 'request_id': 'parent-submit-é'}, value


@pytest.fixture
def execution_seam(partial, monkeypatch):
    from laplace.writing import turn_execution, turn_jobs
    root = partial[0]
    child_hosts._finish_child_execution(root, 'WS-parent', 'prepare-turn', 'completed')
    records.bank(root, {'record': 'writing-session-settings', 'id': 'WSS-fixture', 'project': 'book',
        'session_id': 'WS-parent', 'provider': 'codex', 'model': 'fixture-model', 'effort': 'low', 'settings_revision': 1})
    captured = []
    monkeypatch.setattr(turn_execution, 'start', lambda launch: captured.append(launch))
    yield captured
    for launch in captured:
        turn_jobs._JOBS.pop(launch.turn_id, None)
        child_hosts._finish_child_execution(root, launch.session_id, launch.turn_id, 'completed')


def test_short_request_pinned_navigation_and_exact_resolution(partial):
    payload, value = submission(partial); action = value['action']; snapshot = action['action_context']
    assert len(payload['text']) < 200 and 'guard' not in payload['text']
    assert set(payload['workspace_context']['workflow_action']) == {'reference', 'expected_basis'}
    assert snapshot['native'] == {'operation': 'dispatch_continue', 'payload': value['continuation_payload']}
    assert snapshot['reference']['identity']['parent_session_id'] == 'WS-parent'
    assert snapshot['reference']['identity']['request_id'] != payload['request_id']
    reread = D.read(partial[0], O.project_scope('book', 'sdk'), action['read']['request'])
    assert reread['action']['action_context'] == snapshot
    resolved = A.resolve_action_context(partial[0], 'book', payload['workspace_context']['workflow_action'],
        session_id='WS-parent', mode='work', work_id=partial[1], work_guards=payload)
    assert resolved == snapshot
    assert session_reads.turn_request(partial[0], 'book', 'WS-parent', payload['request_id'])['effect'] == 'NONE'


def test_actual_admission_prompt_custody_lookup_and_replay_before_changed_basis(partial, execution_seam):
    root = partial[0]; payload, value = submission(partial)
    payload['text'] = 'Continue Critic using Author’s retained output. é中🌱'
    answer = T.start_turn(root, payload); assert len(execution_seam) == 1
    launch = execution_seam[0]; snapshot = value['action']['action_context']
    assert launch.workspace_context['workflow_action'] == snapshot
    assert launch.prompt.count('SELECTED WORKFLOW ACTION') == 1
    assert launch.prompt.count(json.dumps(snapshot['native'], ensure_ascii=False)) == 1
    assert payload['text'] in launch.prompt
    stored = records.fold_records(root)['turns'][answer['turn_id']]
    assert stored['workspace_context']['workflow_action'] == snapshot
    raw = next(json.loads(line) for line in (root/'contract/talk.jsonl').read_text().splitlines()
               if json.loads(line).get('id') == answer['turn_id'])
    assert bodies.is_reference(raw['workspace_context'])
    assert identity.canonical_bytes(snapshot['native']) not in identity.canonical_bytes(raw)
    pure = session_reads.turn_request(root, 'book', 'WS-parent', payload['request_id'])
    assert pure['effect'] == 'RECORDED' and pure['receipt']['turn_id'] == answer['turn_id']
    assert pure['receipt']['intent_sha256'] == T.submission_intent(payload)
    parts = urlsplit(answer['action_submission']['read']['http']['url'])
    code, _, data = authoring_http.handle(root, parts.path, parse_qs(parts.query), 'GET', b'')
    assert code == 200 and json.loads(data)['receipt'] == pure['receipt']
    exact = session_reads.session_turn_detail(root, 'book', answer['turn_id'], 'turn')
    assert exact['turn']['workspace_context']['workflow_action'] == snapshot
    # Lost acknowledgement: original input replays without resolving changed inputs.
    artifacts.resolve_path(root, 'book', 'development/report.md').write_text('Changed after admission.')
    replay = T.start_turn(root, copy.deepcopy(payload))
    assert replay['reused'] and replay['turn_id'] == answer['turn_id'] and len(execution_seam) == 1
    for changed in ({**payload, 'text': 'Edited text'}, {**payload, 'session_id': 'WS-child-1'},
                    {**payload, 'provider': 'claude'}, {**payload, 'selection': None}):
        with pytest.raises(ValueError, match='intent changed'):
            T.start_turn(root, changed)
    proof = {'answer': answer, 'lookup': pure, 'replay': replay, 'snapshot': snapshot,
        'wire_intent': {k:v for k,v in payload.items() if k != 'request_id'},
        'intent_sha256': T.submission_intent(payload), 'prompt_chars': len(launch.prompt),
        'request_chars': len(payload['text']), 'snapshot_utf8_bytes': len(identity.canonical_bytes(snapshot)),
        'native_call_prompt_copies': 1, 'native_call_journal_copies': 0, 'provider_execution_seams': 1, 'provider_calls': 0}
    (root/'action-admission-proof.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2))


@pytest.mark.parametrize('fault', ['output', 'settings', 'parent', 'project', 'mode', 'snapshot'])
def test_changed_or_forged_action_refuses_before_admission_effects(partial, monkeypatch, fault):
    root = partial[0]; payload, value = submission(partial)
    if fault == 'output':artifacts.resolve_path(root, 'book', 'development/report.md').write_text('Changed prerequisite.')
    if fault == 'settings':records.bank(root, {'record': 'writing-session-settings', 'id': 'WSS-changed',
        'project': 'book', 'session_id': 'WS-child-1', 'provider': 'codex', 'model': 'different', 'effort': 'low'})
    if fault == 'parent':payload['session_id'] = 'WS-child-0'
    if fault == 'project':payload['project'] = 'foreign'
    if fault == 'mode':payload['mode'] = 'review'
    if fault == 'snapshot':payload['workspace_context']['workflow_action']['native'] = value['action']['action_context']['native']
    before = (root/'contract/talk.jsonl').read_bytes()
    monkeypatch.setattr(T, 'admit_session', lambda *a, **k: pytest.fail('Reached session effects'))
    with pytest.raises(ValueError):T.start_turn(root, payload)
    assert (root/'contract/talk.jsonl').read_bytes() == before
    if fault in {'output', 'settings'}:
        with pytest.raises(D.Refused) as error:
            compose(partial, expected_action_basis=value['action']['action_context']['expected_basis'])
        assert error.value.details['next_reads'][0]['request']['request_id'] == 'child-continue-é'


@pytest.mark.parametrize('padding', [0, 1000])
def test_exact_action_body_custody_and_bounded_thread_projection(partial, padding):
    root = partial[0]
    # A normal and a larger valid Work standing are part of the real owner guard.
    if padding:
        detail = W.read('book', {'view':'detail', 'id':partial[1]}, root)['task']
        W.transition('book', {'id': partial[1], 'status': 'in-progress', 'summary': 'Public standing. ' * padding,
            **{'expected_' + key:detail[key] for key in ('work_scope_revision','dependency_revision','work_status_revision')}}, root)
    payload, value = submission(partial); snapshot = value['action']['action_context']
    row = {'record': 'writing-turn', 'id': 'WT-custody', 'project': 'book', 'session_id': 'WS-parent',
        'text': payload['text'], 'mode': 'work', 'workspace_context': {'surface':'project', 'workflow_action':snapshot}}
    encoded = writing_bodies.prepare_row(root, row)
    assert bodies.is_reference(encoded['workspace_context'])
    assert writing_bodies.resolve_fields(encoded, root)['workspace_context'] == row['workspace_context']
    records.bank(root, row)
    from laplace.writing import session_projection
    bounded = session_reads.session_state(root, 'WS-parent', view='summary')
    turn = next(item for item in bounded['turns'] if item['id'] == 'WT-custody')
    assert 'workspace_context' not in turn and 'dispatch_continue' not in json.dumps(turn)


def test_unicode_json_wire_intent_vector_and_scoped_absence(partial):
    payload, _ = submission(partial); payload['text'] = ' é中🌱 action\n'
    wire = json.loads(json.dumps(payload, ensure_ascii=False))
    expected = hashlib.sha256(json.dumps({k:v for k,v in wire.items() if k != 'request_id'},
        sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    assert T.submission_intent(wire) == 'sha256:' + expected
    assert session_reads.turn_request(partial[0], 'book', 'WS-parent', 'not-admitted')['effect'] == 'NONE'
    with pytest.raises(ValueError):session_reads.turn_request(partial[0], 'foreign', 'WS-parent', 'not-admitted')
    (partial[0]/'wire-intent-proof.json').write_text(json.dumps({'wire':wire,'intent_sha256':'sha256:'+expected},ensure_ascii=False,indent=2))


def test_changed_standing_http_refusal_and_explicit_reinspection(partial, monkeypatch):
    root = partial[0]; payload, old = submission(partial)
    detail = W.read('book', {'view':'detail', 'id':partial[1]}, root)['task']
    W.transition('book', {'id':partial[1], 'status':'in-progress', 'summary':'A newly recorded standing.',
        **{'expected_' + key:detail[key] for key in ('work_scope_revision','dependency_revision','work_status_revision')}}, root)
    monkeypatch.setattr(T, 'admit_session', lambda *a, **k: pytest.fail('Reached session effects'))
    code, _, raw = authoring_http.handle(root, '/authoring/turn', {}, 'POST', json.dumps(payload).encode())
    assert code == 409
    refusal = json.loads(raw)['refused']; assert refusal['code'] == 'ACTION_CONTEXT_CHANGED'
    fresh = D.read(root, O.project_scope('book','sdk'), refusal['next_reads'][0]['request'])
    assert fresh['action']['action_context']['expected_basis'] != old['action']['action_context']['expected_basis']
    assert fresh['action']['action_context']['reference'] == old['action']['action_context']['reference']


def test_declared_request_read_and_legacy_intent_custody_unchanged(partial):
    from jsonschema import Draft202012Validator
    from laplace.web import writing_declared_http
    from laplace.native.declarations import HTTP_DECLARATIONS
    shape = HTTP_DECLARATIONS['authoring/session-turn'].payload
    Draft202012Validator(shape).validate({'project':'book','session_id':'WS-parent','request_id':'unseen','view':'request'})
    Draft202012Validator(shape).validate({'project':'book','id':'prepare-turn','view':'turn'})
    assert list(Draft202012Validator(shape).iter_errors({'project':'book','view':'request','id':'prepare-turn'}))
    legacy = {'project':'book','text':'Same ordinary request','mode':'work','request_id':'legacy-one'}
    request = T.prepare_request(legacy)
    assert 'action_submission_intent_sha256' not in request
    old = {'id':'WT-legacy','project':'book','mode':'work','request_id':'legacy-one','session_id':'WS-parent'}
    assert T.reused_turn({'turns':{'WT-legacy':old},'sessions':{'WS-parent':{'role':'author'}}},request) == {
        'turn_id':'WT-legacy','session_id':'WS-parent','reused':True}
    row = {'record':'writing-turn','id':'WT-normal','workspace_context':{'surface':'project'}}
    assert writing_bodies.prepare_row(partial[0], row) == row
