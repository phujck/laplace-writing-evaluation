"""Public Source→Work reading offers; paid execution is withheld, not simulated as review."""
import copy
import json
from urllib.parse import parse_qs, urlsplit
import pytest
from laplace.work import project_work as W, project_work_review as R, development_source as D, work_delivery as WD
from laplace.native import tools
from laplace.projects import library
from laplace.web import project_work_surface as HTTP
from laplace.writing import records
from test_source_use_joins import source, candidate
from test_work_review_source_basis_actual import ready, guard
from test_source_delivery_qualified import transport, submit


def native_phase(s, result):
    if not result.get('full_response_omitted'):
        return result
    # Consume the actual compact acknowledgement's exact owner read, not a
    # reconstructed phase ID, canonical lookup or a raised response-size bound.
    read = result['next_read']
    page = tools.execute(s['root'], 'public', 'work', read['operation'], read['payload'], turn_id='WT-parent')
    assert page['view'] == 'review' and page['phase']['id'] == read['payload']['phase_id']
    return {'status': result['status'], 'phase': page['phase']['rows'][0], 'phase_read': read,
            'native_acknowledgement': result, 'native_exact_read': page}


def offer(s, *, windows=None, request='public-planned-handoff', http=False):
    selection, pins = ready(s)
    payload = {'id': 'work', 'phase': 'handoff', 'request_id': request,
               'expected_work_revision': guard(s), 'source_basis': selection, 'pins': pins,
               'source_context': {'windows': windows if windows is not None else [
                   {'path': 'src/answer.py', 'line_start': 1, 'line_end': 4},
                   {'path': 'evaluator.py', 'line_start': 1, 'line_end': 1},
                   {'path': 'guide.md', 'line_start': 1, 'line_end': 1}]}}
    if http:
        code, _, raw = HTTP.handle('/work/review', {}, 'POST', json.dumps({'project': 'public', **payload}).encode(), s['root'])
        assert code == 200, raw
        return json.loads(raw), payload
    return native_phase(s, tools.execute(s['root'], 'public', 'work', 'work_review', payload, turn_id='WT-parent')), payload


def test_native_handoff_immutable_offer_replay_and_existing_exact_http_reader(source, monkeypatch):
    s = source; h, payload = offer(s); plan = copy.deepcopy(h['phase']['source_review_plan'])
    assert plan['state'] == 'COMPLETE' and h['phase']['source_context'] == payload['source_context']
    assert h['native_acknowledgement']['full_response_omitted'] and h['native_acknowledgement']['next_read'] == h['phase_read']
    monkeypatch.setattr(D, 'prepare_review_plan', lambda *a, **k: (_ for _ in ()).throw(AssertionError('recomputed replay')))
    replay = native_phase(s, tools.execute(s['root'], 'public', 'work', 'work_review', {**payload, 'expected_work_revision': guard(s)}, turn_id='WT-parent'))
    assert replay['status'] == 'REUSED' and replay['phase']['source_review_plan'] == plan
    replay['phase']['source_review_plan']['inputs'][0]['state'] = 'caller mutation'
    assert W._tasks('public', s['root'])['work']['phases'][-1]['source_review_plan'] == plan
    changed = {**payload, 'expected_work_revision': guard(s), 'source_context': {'windows': []}}
    with pytest.raises(ValueError, match='different.*Source reading plan'):
        tools.execute(s['root'], 'public', 'work', 'work_review', changed, turn_id='WT-parent')
    handle = h['phase_read']; code, _, raw = HTTP.handle('/work/state', parse_qs(urlsplit(handle['http']['url']).query), 'GET', repo_root=s['root'])
    assert code == 200 and json.loads(raw)['phase']['rows'][0]['source_review_plan'] == plan
    summary = R.facet(W._tasks('public', s['root'])['work'], s['root'])['handoff']['source_review_plan']
    assert summary['offered_not_observed'] and summary['semantic_adequacy'] == 'UNASSESSED'
    (s['root']/'plan-handoff-proof.json').write_text(json.dumps({'handoff': h, 'payload': payload, 'summary': summary}, indent=2)+'\n')


def test_http_offer_and_real_delivery_use_only_obligation_extents_with_owner_reads(transport):
    s, launches = transport
    h, _ = offer(s, http=True, windows=[{'path': 'src/answer.py', 'line_start': 1, 'line_end': 4},
                                      {'path': 'evaluator.py', 'line_start': 1, 'line_end': 1}])
    assert h['phase']['source_review_plan']['state'] == 'INCOMPLETE'  # guide is outside this review
    event = submit(s, h)['event']; assert event['state'] == 'ADMITTED' and len(launches) == 1
    plan = event['source_review_plan']; original = copy.deepcopy(plan)
    projection = D.review_plan_for_inputs(plan, {p: h['phase']['pins'][p] for p in ['src/answer.py', 'evaluator.py']})
    assert projection['state'] == 'COMPLETE' and 'guide.md' in projection['outside_consumed_inputs']
    request = records.fold_records(s['root'])['turns'][launches[0].turn_id]['text']
    assert request.index('Purpose:') < request.index('What changed') and 'Review question: Source' in request
    assert 'do not automatically continue to EOF' in request and 'follow each owner-issued next page' not in request
    assert 'Public unchanged documentation.' not in request and 'semantic adequacy' in request
    pages = []
    for item in projection['inputs']:
        for excerpt in item['initial_reads']:
            read = excerpt['read']; native = tools.execute(s['root'], 'public', 'review', read['operation'], read['payload'], turn_id=launches[0].turn_id)
            q = {k: v[0] for k, v in parse_qs(urlsplit(read['http']['url']).query).items()}
            for key in ['offset', 'limit']: q[key] = int(q[key])
            q['target'] = json.loads(q['target']); project = q.pop('project')
            human = library.material_references(project, s['root'], **q)
            assert native['content'] == human['owner_result']['content']
            assert len(native['content']) == excerpt['chars'] and excerpt['offset']+excerpt['chars'] == excerpt['stop_before_offset']
            pages.append({'extent': excerpt, 'native': native, 'human': human})
    event['source_review_plan']['inputs'][0]['state'] = 'caller mutation'
    assert WD.status(s['root'], 'public', {'event_id': event['id']}, s['door'])['event']['source_review_plan'] == original
    # Declared guide drift does not invalidate this obligation's consumed inputs.
    (s['checkout']/'guide.md').write_text('unrelated later guide')
    task = W._tasks('public', s['root'])['work']; intent = next(r for r in task['deliveries'] if r.get('id') == event['id'])
    assert WD._revalidate(s['root'], 'public', task, intent) is None
    (s['root']/'plan-delivery-proof.json').write_text(json.dumps({'handoff': h, 'event': WD.status(s['root'], 'public', {'event_id': event['id']}, s['door'])['event'], 'request': request, 'pages': pages, 'qualification': 'Actual admission and read owners; turn_execution.start withheld, no inference'}, indent=2)+'\n')


def test_explicit_incomplete_plan_is_retained_but_never_launches_full_file_fallback(transport):
    s, launches = transport; h, _ = offer(s, windows=[])
    assert h['phase']['source_review_plan']['state'] != 'COMPLETE'
    before = len(records.index(s['root']).sessions)
    event = submit(s, h)['event']
    assert event['state'] == 'STALE' and 'reading plan' in event['reason']
    assert not launches and len(records.index(s['root']).sessions) == before
    assert event['source_review_plan'] == h['phase']['source_review_plan'] and not event.get('admitted')


def test_plan_context_closed_phase_contract_and_content_identity(source):
    from laplace.core.admission import admit_owner_payload
    basic = {'id': 'work', 'phase': 'handoff', 'request_id': 'public-context-schema', 'expected_work_revision': guard(source), 'source_context': {'windows': []}}
    with pytest.raises(ValueError): admit_owner_payload('work_review', basic, R.contract(), project='public')
    with pytest.raises(ValueError): admit_owner_payload('work_review', {**basic, 'phase': 'review'}, R.contract(), project='public')
    h, _ = offer(source); old = {'pins': h['phase']['pins'], 'object': h['phase']['object'], 'source_basis': h['phase']['source_basis']}
    assert WD._content_pin(old) == WD._digest(old)
    changed = copy.deepcopy(h['phase']); changed['source_review_plan']['plan_id'] = 'different-plan'
    assert WD._content_pin(changed) != WD._content_pin(h['phase'])


def test_planned_lost_ack_recovery_keeps_original_event_and_parent_read_route(transport, monkeypatch):
    from laplace.writing import turn_execution
    s, launches = transport; h, _ = offer(s); real_append = W._append
    def lose_ack(root, row):
        if row.get('kind') == WD.EVENT and row.get('state') == 'ADMITTED':
            raise RuntimeError('public planned admission acknowledgement lost')
        return real_append(root, row)
    monkeypatch.setattr(W, '_append', lose_ack)
    with pytest.raises(RuntimeError, match='acknowledgement lost'): submit(s, h)
    monkeypatch.setattr(W, '_append', real_append)
    task = W._tasks('public', s['root'])['work']; event_id = next(r['id'] for r in task['deliveries'] if r.get('kind') == WD.EVENT)
    event = WD.recover(s['root'], 'public', {'event_id': event_id}, s['door'])['event']
    assert len(launches) == 1 and event['admitted']['turn_id'] == launches[0].turn_id and event['admitted']['recovered']
    assert event['source_review_plan'] == h['phase']['source_review_plan']
    launch = launches[0]
    tools.execute(s['root'], 'public', 'review', 'work_review', {'id': 'work', 'phase': 'review',
        'request_id': 'public-planned-result', 'expected_work_revision': guard(s), 'handoff_id': h['phase']['id'],
        'obligation_id': 'source', 'verdict': 'ACCEPT'}, turn_id=launch.turn_id)
    result = {'status': 'completed', 'text': 'Public deterministic result supplied at withheld execution boundary.'}
    turn_execution._bank_reply(launch, result); turn_execution._finish(launch, result)
    current = WD.status(s['root'], 'public', {'event_id': event_id}, s['door'])['event']
    assert current['state'] == 'CONTINUED' and len(launches) == 2
    assert current['source_review_plan'] == h['phase']['source_review_plan']
    assert launches[1].session_id == s['parent']['id'] and current['acceptance']['satisfied']
    assert WD.recover(s['root'], 'public', {'event_id': event_id}, s['door'])['event']['id'] == event_id and len(launches) == 2
    (s['root']/'plan-recovery-proof.json').write_text(json.dumps({'event': current, 'qualification': 'Real recovery/admission/review/terminal owners; both execution starts withheld; deterministic result is not model evidence'}, indent=2)+'\n')
