"""Public owner fixtures; host handshake is deterministic, never provider inference."""
import copy
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_app_workflow_dispatch import prepared
from test_packet_return_lifecycle import judgement
from laplace.pipeline import workflow_definitions as D
from laplace.projects import artifacts
from laplace.work import project_work as W
from laplace.writing import records, child_hosts, dispatch_execution as E, dispatch_returns as R, dispatch_parent
from laplace.native import tools


@pytest.fixture
def partial(prepared):
    root, caller, payload, saved = prepared
    made = D.prepare(root, caller, payload)
    task = W._tasks('book', root)[made['work']['id']]
    plan, pin, art = __import__('laplace.writing.workflow_dispatch', fromlist=['_checked'])._checked(root, 'book', task)
    W.transition('book', {'id': task['id'], 'status': 'in-progress'}, root, dispatch_receipt={
        'dispatch_admitted': True, 'dispatch_parent_turn_id': 'prepare-turn', 'dispatch_launch_state': 'STARTED',
        'dispatch_plan_sha256': art['revision']})
    report = artifacts.store(root, 'book', {'path': 'development/report.md', 'before': None,
        'content': 'Exact retained public worker output.', 'reason': 'Public fixture.'}, 'prepare-turn')
    source = {'path': art['path'], 'sha256': art['revision']}
    output = {'path': report['path'], 'sha256': report['revision']}
    worker = {'schema_version': 'laplace.packet-return/2', 'packet': plan['packets'][0]['packet'],
        'role': 'build', 'status': 'COMPLETE', 'goal': plan['goal'], 'inputs': [source],
        'source': {'kind': 'artifacts', 'root': str(root), 'artifacts': [source, output]}, 'output': output,
        'files_written': [report['path']], 'summary': 'Exact retained public output.',
        'most_important': ['The declared bytes are retained.'], 'residuals': [], 'remaining_work': [], 'continuation': None,
        'scripted_check': {'kind': 'command', 'state': 'PASSED', 'command': 'fixture bytes', 'exit_code': 0, 'output_tail': 'Fixture bytes.'}}
    for index, item in enumerate(plan['packets']):
        session, turn = 'WS-child-' + str(index), 'WT-child-' + str(index)
        role = 'review' if item['role'] == 'judge' else 'author'
        records.bank(root, {'record': 'writing-session', 'id': session, 'project': 'book', 'role': role,
            'dispatch_id': task['id'], 'packet': item['packet'], 'provider': 'codex', 'model': 'fixture-model', 'effort': 'low'})
        records.bank(root, {'record': 'writing-turn', 'id': turn, 'session_id': session, 'project': 'book',
            'mode': 'review' if role == 'review' else 'work', 'dispatch_id': task['id'], 'parent_turn_id': 'prepare-turn'})
        if index == 0:
            artifacts.store(root, 'book', {'path': item['return_path'], 'before': None,
                'content': json.dumps(worker), 'reason': 'Public typed worker.'}, turn)
        records.bank(root, {'record': 'writing-reply', 'id': 'WR-child-' + str(index), 'project': 'book',
            'session_id': session, 'turn_id': turn, 'status': 'completed' if index == 0 else 'failed', 'text': 'Retained public fixture reply.'})
        child_hosts._begin_child_execution(root, session, {'state': 'FINISHED', 'turn_id': turn, 'session_id': session, 'project': 'book'})
    return root, task['id'], plan, worker


def offered(case):
    root, ident, plan, _ = case
    offer = E.continuation_offer(root, 'book', ident, plan['packets'][1]['packet'])
    assert offer['available'], offer
    return {**offer['payload'], 'request_id': 'continue-review-one'}


def test_actual_turn_run_banks_the_blocked_judge_failed_reply_through_its_own_producer(partial, monkeypatch):
    """B HOLD F4: the failed judge reply is produced by the ONE turn path, not prebanked. An actual continuation turn
    (continue_dispatch through the host seam) runs turn_execution.run: the real dependency wait observes the worker
    return missing (BLOCKED), raises before any capability probe or provider, and _failed_turn/_bank_reply/_finish bank
    the terminal pre-inference failed reply and settle the execution record. No provider is constructed."""
    import threading as _threading
    from types import SimpleNamespace
    from laplace.writing import turn_execution, turn_admission, provider as writing_provider
    root, ident, plan, _ = partial
    payload = offered(partial);host_seam(monkeypatch, partial)
    turn = E.continue_dispatch(root, 'book', 'prepare-turn', payload)['current_attempt']['turn_id']
    assert E._child_return_contract(root, 'book', 'WS-child-1', ident, turn_id=turn)['judged_workers']
    artifacts.resolve_path(root, 'book', plan['packets'][0]['return_path']).unlink()   # the worker return is now missing
    monkeypatch.setattr(writing_provider, 'WritingTurn', lambda *a, **k: pytest.fail('no provider may be constructed'))
    monkeypatch.setattr(turn_admission, 'effort_as_sent', lambda *a, **k: pytest.fail('no capability probe may run'))
    saved = records.fold_records(root)
    row = saved['turns'][turn]
    job = {'condition': _threading.Condition(), 'events': [], 'text': '', 'interrupt_requested': False}
    launch = SimpleNamespace(root=root, project='book', session_id='WS-child-1', turn_id=turn, job=job,
        dispatch={key: row[key] for key in ('dispatch_id', 'parent_turn_id') if row.get(key)},
        session=saved['sessions']['WS-child-1'], contract_digest='sha256:' + '0' * 64, registration_signature='sha256:' + '0' * 64,
        reader_profile=None, queued_requests=(), connected_observation=None, prompt='', mode='review',
        operating_brief={'digest': 'sha256:' + '0' * 64}, native_source_paths=())
    assert launch.dispatch.get('dispatch_id') == ident
    turn_execution.run(launch)
    assert job['done'] is True
    reply = records.fold_records(root)['turns'][turn]['reply']
    assert reply['status'] == 'failed' and reply['provider_stage'] == 'pre-inference'
    assert 'DEPENDENCY-INCOMPLETE' in reply['error']
    replies = [r for r in records.fold_records(root)['turns'].values() if r['id'] == turn]
    assert len(replies) == 1
    assert any(event.get('type') == 'progress' and 'review blocked' in event.get('text', '') for event in job['events'])
    assert any(event.get('type') == 'complete' for event in job['events'])
    execution = child_hosts.child_execution(root, 'WS-child-1')
    assert execution.get('turn_id') == turn and E.settled_judge_problem(execution, turn) is None, execution


def host_seam(monkeypatch, case, *, failure=None, gate=None):
    root, ident, plan, _ = case
    launches = []
    def start(selected_root, payload, *, dispatch):
        assert selected_root == root and payload['session_id'] == 'WS-child-1' and payload['mode'] == 'review'
        assert payload['text'] == plan['packets'][1]['brief']
        launches.append(copy.deepcopy(payload))
        if gate:gate()
        if failure == 'before':raise OSError('Unknown host handshake before acknowledgement')
        turn = E.continuation_turn_id(root, 'book', payload['session_id'], payload['request_id'], dispatch)
        records.bank(root, {'record': 'writing-turn', 'id': turn, 'session_id': payload['session_id'],
            'project': 'book', 'request_id': payload['request_id'], 'mode': 'review', **dispatch})
        child_hosts._begin_child_execution(root, payload['session_id'], {'state': 'RUNNING', 'turn_id': turn,
            'session_id': payload['session_id'], 'project': 'book', 'host': child_hosts._process_identity()})
        if failure == 'after':raise OSError('Lost exact WT acknowledgement')
        return {'turn_id': turn, 'session_id': payload['session_id']}
    monkeypatch.setattr(E.turn_admission, 'start_turn', start)
    return launches


def publish(case, turn, *, accepted=True):
    root, ident, plan, worker = case
    document = judgement(worker, artifacts.resolve_path(root, 'book', plan['packets'][0]['return_path']))
    document['packet'] = worker['packet'];document['judged']['review_context']['session_id'] = 'WS-child-1'
    read = tools.execute(root, 'book', 'review', 'read_artifact', {'path': 'development/report.md'}, turn_id=turn)['read_receipt']
    check = {'kind': 'owner-read', 'state': 'PASSED', 'operation': read['operation'], 'payload': read['payload'],
        'receipt_id': read['id'], 'output_sha256': read['output_sha256'], 'ok': True, 'output_tail': 'Exact retained report read.'}
    document['scripted_check'] = check;document['own_observations'] = [{k: v for k, v in check.items() if k != 'state'}]
    if not accepted:document.update(accepted=False,accepted_subsets=[],deficiencies=[{
        'id':'gap','item':'Public result','problem':'A substantive condition is absent.',
        'evidence':'The retained output lacks the declared condition.','done_looks_like':'Resolve that condition.'}])
    action = R.publication(root, 'book', plan['packets'][1]['return_path'], document=document)
    return artifacts.store(root, 'book', action['payload'], turn), document


def test_one_judge_attempt_preserves_worker_plan_and_current_counts(partial, monkeypatch):
    root, ident, plan, _ = partial
    unchanged = [root / W._tasks('book', root)[ident]['evidence'][0],
        artifacts.resolve_path(root, 'book', plan['packets'][0]['return_path']), artifacts.resolve_path(root, 'book', 'development/report.md')]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in unchanged}
    payload = offered(partial);launches = host_seam(monkeypatch, partial)
    result = E.continue_dispatch(root, 'book', 'prepare-turn', payload)
    assert result['effect'] == 'RECORDED' and len(launches) == 1
    turn = result['current_attempt']['turn_id'];assert turn != 'WT-child-1'
    assert E._child_return_contract(root,'book','WS-child-1',ident) is None
    assert E._child_return_contract(root,'book','WS-child-1',ident,turn_id=turn)['judged_workers']
    assert E.continue_dispatch(root, 'book', 'prepare-turn', payload)['replayed'] and len(launches) == 1
    stored, document = publish(partial, turn)
    records.bank(root, {'record': 'writing-reply', 'id': 'WR-continued', 'project': 'book', 'session_id': 'WS-child-1',
        'turn_id': turn, 'status': 'completed', 'text': 'Retained new judgement.'})
    child_hosts._finish_child_execution(root, 'WS-child-1', turn, 'completed')
    view = W.dispatch_view(W._tasks('book', root)[ident], 'book', root)
    assert len(view['children']) == 2 and view['execution_state'] == 'COMPLETE' and view['review_state'] == 'ACCEPTED'
    assert view['cost']['turns_total'] == view['cost']['turns_replied'] == 3
    judge = next(row for row in view['children'] if row['role'] == 'judge')
    assert judge['turn_id'] == turn and judge['attempt_history'][0]['turn_id'] == 'WT-child-1'
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in unchanged} == before
    assert len(records.fold_records(root)['sessions']) == 3
    assert not E.continuation_offer(root, 'book', ident, payload['packet'])['available']
    (root / 'continuation-proof.json').write_text(json.dumps({'result': result, 'view': view, 'stored': stored, 'unchanged': before}, indent=2))


@pytest.mark.parametrize('failure,effect', [('before', 'UNKNOWN'), ('after', 'RECORDED')])
def test_unknown_handshake_replay_never_starts_again(partial, monkeypatch, failure, effect):
    payload = offered(partial);launches = host_seam(monkeypatch, partial, failure=failure)
    first = E.continue_dispatch(partial[0], 'book', 'prepare-turn', payload)
    assert first['effect'] == effect
    assert E.continue_dispatch(partial[0], 'book', 'prepare-turn', payload)['effect'] == effect and len(launches) == 1
    assert len(W.dispatch_view(W._tasks('book', partial[0])[partial[1]], 'book', partial[0])['children']) == 2
    with pytest.raises(ValueError, match='intent changed'):
        E.continue_dispatch(partial[0], 'book', 'prepare-turn', {**payload, 'budget': {}})


def test_concurrent_identical_intent_has_one_host(partial, monkeypatch):
    payload = offered(partial);entered = threading.Event();release = threading.Event()
    def gate():entered.set();assert release.wait(5)
    launches = host_seam(monkeypatch, partial, gate=gate)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(E.continue_dispatch, partial[0], 'book', 'prepare-turn', payload)
        assert entered.wait(5)
        again = E.continue_dispatch(partial[0], 'book', 'prepare-turn', payload)
        assert again['replayed'] and again['effect'] == 'UNKNOWN'
        release.set();assert first.result()['effect'] == 'RECORDED'
    assert len(launches) == 1


@pytest.mark.parametrize('fault', ['cancelled', 'foreign-parent', 'expired-parent', 'worker', 'active-host', 'changed-plan', 'changed-output', 'expired-deadline'])
def test_guarded_refusals_before_launch(partial, monkeypatch, fault):
    root, ident, plan, _ = partial;payload = offered(partial);launches = host_seam(monkeypatch, partial)
    if fault == 'cancelled':W.transition('book', {'id': ident, 'status': 'cancelled'}, root, dispatch_receipt={'dispatch_test_disposition': True})
    elif fault == 'foreign-parent':
        with pytest.raises(ValueError):E.continue_dispatch(root, 'book', 'foreign-turn', payload)
        assert not launches;return
    elif fault == 'expired-parent':child_hosts._finish_child_execution(root, 'WS-parent', 'prepare-turn', 'completed')
    elif fault == 'worker':payload['packet'] = plan['packets'][0]['packet']
    elif fault == 'active-host':child_hosts._begin_child_execution(root, 'WS-child-1', {'state': 'RUNNING', 'turn_id': 'WT-child-1', 'host': child_hosts._process_identity()})
    elif fault == 'changed-plan':(root / W._tasks('book', root)[ident]['evidence'][0]).write_text('{}')
    elif fault == 'changed-output':artifacts.resolve_path(root, 'book', 'development/report.md').write_text('Changed bytes')
    else:W.transition('book', {'id': ident, 'status': 'in-progress'}, root, dispatch_receipt={'dispatch_deadline_at': 1})
    with pytest.raises((ValueError, D.Refused)):E.continue_dispatch(root, 'book', 'prepare-turn', payload)
    assert not launches and not W._tasks('book', root)[ident].get('dispatch_review_continuations')


def test_invalid_return_supersession_keeps_history_and_blocks_old_turn(partial, monkeypatch):
    root, ident, plan, _ = partial
    old = artifacts.store(root, 'book', {'path': plan['packets'][1]['return_path'], 'before': None,
        'content': '{"invalid":"retained old body"}', 'reason': 'Public failed return.'}, 'WT-child-1')
    payload = offered(partial);host_seam(monkeypatch, partial)
    result = E.continue_dispatch(root, 'book', 'prepare-turn', payload);turn = result['current_attempt']['turn_id']
    assert R.child_permission(root, 'book', 'WS-child-1', ident, turn_id='WT-child-1') is None
    action = R.publication(root, 'book', plan['packets'][1]['return_path'], document={'invalid': 'late'})
    with pytest.raises(ValueError, match='selected continuation'):
        artifacts.store(root, 'book', action['payload'], 'WT-child-1')
    stored, document = publish(partial, turn)
    record = records.selected_journal_fields('book',stored['id'],root,fields=['before','before_sha256'])
    assert record['before'] == '{"invalid":"retained old body"}' and record['before_sha256'] == old['revision']
    assert records.selected_journal_fields('book',old['id'],root,fields=['after'])['after'] == record['before']
    with pytest.raises(ValueError, match='revision changed'):
        artifacts.store(root, 'book', {**action['payload'], 'content': json.dumps(document)}, turn)


def test_changed_prerequisite_after_admission_refuses_new_return(partial, monkeypatch):
    payload = offered(partial);host_seam(monkeypatch, partial)
    result = E.continue_dispatch(partial[0], 'book', 'prepare-turn', payload)
    artifacts.resolve_path(partial[0], 'book', 'development/report.md').write_text('Changed after admission')
    with pytest.raises(ValueError, match='prerequisite'):
        publish(partial, result['current_attempt']['turn_id'])


@pytest.mark.parametrize('accepted',[True,False])
def test_valid_judgement_including_negative_never_reruns(partial,monkeypatch,accepted):
    publish(partial,'WT-child-1',accepted=accepted)
    launches=host_seam(monkeypatch,partial)
    offer=E.continuation_offer(partial[0],'book',partial[1],partial[2]['packets'][1]['packet'])
    assert not offer['available'] and 'valid judgement' in offer['reason'] and not launches


def test_reserved_turn_enters_normal_admission_and_prompt_without_inference(partial,monkeypatch):
    from laplace.writing import turn_jobs
    root,ident,plan,_=partial;payload=offered(partial);admitted=[]
    def start(selected_root,request,*,dispatch):
        launch=E.turn_admission.admit(root,request,E.turn_admission.prepare_request(request),records.fold_records(root),dispatch)
        admitted.append(launch)
        return {'turn_id':launch.turn_id,'session_id':launch.session_id}
    monkeypatch.setattr(E.turn_admission,'start_turn',start)
    try:
        result=E.continue_dispatch(root,'book','prepare-turn',payload)
        assert result['effect']=='RECORDED',result
        launch=admitted[0];assert launch.turn_id==result['receipt']['planned_turn_id']
        assert 'store_artifact' in launch.operating_brief['permissions'] and 'publish_action' in launch.prompt
        assert plan['packets'][1]['brief'] in launch.prompt and '"continuation"' in launch.prompt
        assert launch.session_id=='WS-child-1' and launch.dispatch['dispatch_id']==ident
    finally:
        for launch in admitted:
            turn_jobs._JOBS.pop(launch.turn_id,None)
            child_hosts._finish_child_execution(root,launch.session_id,launch.turn_id,'completed')


def test_settled_current_turn_cannot_publish_after_end(partial,monkeypatch):
    payload=offered(partial);host_seam(monkeypatch,partial)
    result=E.continue_dispatch(partial[0],'book','prepare-turn',payload);turn=result['current_attempt']['turn_id']
    child_hosts._finish_child_execution(partial[0],'WS-child-1',turn,'completed')
    assert R.child_permission(partial[0],'book','WS-child-1',partial[1],turn_id=turn) is None
    with pytest.raises(ValueError,match='not admitted'):publish(partial,turn)


def test_original_parent_binding_cannot_change_after_admission(partial,monkeypatch):
    payload=offered(partial);host_seam(monkeypatch,partial)
    result=E.continue_dispatch(partial[0],'book','prepare-turn',payload)
    W.transition('book',{'id':partial[1],'status':'in-progress'},partial[0],
        dispatch_receipt={'dispatch_parent_turn_id':'unrelated-turn'})
    with pytest.raises(ValueError,match='parent binding changed'):
        publish(partial,result['current_attempt']['turn_id'])


@pytest.mark.parametrize('field,value',[('model','different-supported-model'),('effort','high')])
def test_actual_admission_refuses_session_settings_drift(partial,monkeypatch,field,value):
    """The actual continuation admission refuses a judge session whose settings drifted from the immutable plan, never
    coercing them back. Since the carried A20 owner, configure_session itself refuses to change an admitted recipient's
    settings (an earlier, stronger guard; peer proof ART-a2bc12ee reproduced that on fd461), so the drift here reaches
    the journal through another writer: the same negative assertion, now actually exercised at admission."""
    from laplace.writing import provider
    root,ident,plan,_=partial;payload=offered(partial);admitted=[]
    catalogue=provider.capabilities(root)
    catalogue['providers'][0]['models'].append({'id':'different-supported-model','default_effort':'low','efforts':['low']})
    catalogue['providers'][0]['models'][0]['efforts'].append('high')
    def start(selected_root,request,*,dispatch):
        records.bank(root,{'record':'writing-session','id':'WS-child-1','project':'book','role':'review','dispatch_id':ident,
            'packet':plan['packets'][1]['packet'],'provider':'codex','model':'fixture-model','effort':'low',field:value})
        launch=E.turn_admission.admit(root,request,E.turn_admission.prepare_request(request),records.fold_records(root),dispatch)
        admitted.append(launch)
        return {'turn_id':launch.turn_id,'session_id':launch.session_id}
    monkeypatch.setattr(E.turn_admission,'start_turn',start)
    result=E.continue_dispatch(root,'book','prepare-turn',payload)
    assert result['effect']=='UNKNOWN' and not admitted
    assert 'settings changed' in result['receipt']['launch_error']
    assert result['receipt']['planned_turn_id'] not in records.fold_records(root)['turns']
    assert records.fold_records(root)['sessions']['WS-child-1'][field]==value  # never coerced back
    assert E.continue_dispatch(root,'book','prepare-turn',payload)['replayed'] and not admitted


def blocked_before_inference(root, *, finish=True, **extra):
    """The judge host's own lifecycle, not a fixture-forced FINISHED: the dependency wait records BLOCKED, the host raises
    before any provider exists and child_hosts._finish_child_execution archives the terminal BLOCKED record. The terminal
    failed reply the offer also requires is banked on that raise by the turn's own reply producer (turn_execution
    sha256:7cc78063: _provider_turn raises -> _failed_turn -> _bank_reply); this public fixture banks the equivalent
    WR-child-1 row directly, so that reply path is cited here, not exercised (review PHASE-0f221e76 F4)."""
    child_hosts._begin_child_execution(root, 'WS-child-1', {'state': 'WAITING', 'turn_id': 'WT-child-1', 'session_id': 'WS-child-1',
        'project': 'book', 'host': child_hosts._process_identity(), **extra})
    child_hosts._update_child_execution(root, 'WS-child-1', {'state': 'BLOCKED', 'dependency_state': 'BLOCKED', 'dependencies': []},
        expected_turn_id='WT-child-1')
    if finish:
        child_hosts._finish_child_execution(root, 'WS-child-1', 'WT-child-1', 'failed')


def test_terminal_pre_inference_blocked_judge_continues_through_its_actual_host_lifecycle(partial, monkeypatch):
    root, ident, plan, _ = partial
    blocked_before_inference(root)
    settled = child_hosts.child_execution(root, 'WS-child-1')
    assert settled['state'] == 'BLOCKED' and settled['finished_at'] and settled['result_status'] == 'failed'
    assert E.settled_judge_problem(settled, 'WT-child-1') is None
    sessions = len(records.fold_records(root)['sessions'])
    payload = offered(partial)
    launches = host_seam(monkeypatch, partial)   # the seam calls continuation_turn_id: the actual admission predicate
    result = E.continue_dispatch(root, 'book', 'prepare-turn', payload)
    assert result['effect'] == 'RECORDED' and len(launches) == 1
    guard = result['receipt']['guard']
    assert guard['prior_attempt'] == {'session_id': 'WS-child-1', 'turn_id': 'WT-child-1'}
    assert guard['origin_parent_turn_id'] == 'prepare-turn' and result['budget']['max_child_launches'] == 1
    assert [row['packet'] for row in guard['prerequisites']] == [plan['packets'][0]['packet']]   # retained, never rerun
    assert E.continue_dispatch(root, 'book', 'prepare-turn', payload)['replayed'] and len(launches) == 1
    assert len(records.fold_records(root)['sessions']) == sessions   # the same judge session; no new worker or session


@pytest.mark.parametrize('case', ['unfinished', 'inference-started', 'provider-recorded', 'live-provider', 'live-auxiliary'])
def test_blocked_judge_that_is_not_terminal_pre_inference_still_refuses(partial, monkeypatch, case):
    root, ident, plan, _ = partial
    live = child_hosts._process_identity()
    extra = {'inference-started': {'provider_inference_started': True},
             'provider-recorded': {'provider_processes': [{'pid': 1, 'created_at': 'another-birth'}]},
             'live-provider': {'provider_processes': [live]}, 'live-auxiliary': {'auxiliary_processes': [live]}}.get(case, {})
    blocked_before_inference(root, finish=case != 'unfinished', **extra)
    launches = host_seam(monkeypatch, partial)
    offer = E.continuation_offer(root, 'book', ident, plan['packets'][1]['packet'])
    assert not offer['available'] and 'not safely settled' in offer['reason'], offer
    assert not launches and not W._tasks('book', root)[ident].get('dispatch_review_continuations')


def test_selected_admission_snapshot_cannot_hide_drift(partial,monkeypatch):
    payload=offered(partial);host_seam(monkeypatch,partial,failure='before')
    E.continue_dispatch(partial[0],'book','prepare-turn',payload)
    task=W._tasks('book',partial[0])[partial[1]];receipt=task['dispatch_review_continuations'][payload['request_id']]
    selected=copy.deepcopy(records.fold_records(partial[0])['sessions']['WS-child-1']);selected['model']='changed-snapshot'
    with pytest.raises(ValueError,match='settings changed'):
        E.guard_continuation_inputs(partial[0],'book',task,receipt,admitted_session=selected)
