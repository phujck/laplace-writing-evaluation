"""Eigen continuity delivery controls (B slice of Root e716/a6d0).

Continue produces the existing handoff and Work delivery exactly once, with the original producer's provenance and a
separately recorded dispatcher, through the real Work delivery, Source account and turn-admission path. Only
turn_execution.start and provider capability discovery are stubbed (no provider, model or network); admission,
accounting, settlement and the once-only parent return are the real owners.
"""
import datetime as dt
import json

import pytest

from test_source_use_joins import source  # noqa: F401  (the public Source fixture)


def test_settled_notification_names_the_exact_same_project_reply_record_and_omits_an_ambiguous_one(tmp_path):
    """The continuation names the existing author_history exact record read; another project or a duplicate gets none."""
    import json
    from laplace.writing import records as writing_records
    from laplace.work import work_delivery as delivery
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-reviewer-1','session_id':'WS-reviewer-1','project':'book','mode':'review'})
    writing_records.bank(tmp_path,{'record':'writing-reply','id':'WR-reviewer-1','turn_id':'WT-reviewer-1','session_id':'WS-reviewer-1',
                                   'project':'book','status':'completed','text':'Scoped ACCEPT with two findings.'})
    read=delivery.exact_reply_read(tmp_path,'book','WT-reviewer-1')
    assert read['operation']=='author_history' and read['payload']=={'view':'record','id':'activity:journal:WR-reviewer-1'}
    assert 'presented message page is a separate view' in read['meaning']
    assert delivery.exact_reply_read(tmp_path,'other-project','WT-reviewer-1') is None
    row={'turn_id':'WT-reviewer-1','result':{'status':'completed'},'acceptance':{'status':'ACCEPTED','currentness':'CURRENT'}}
    text=delivery._continuation_text({'id':'WORK-x','project':'book'},{'id':'WD-1','recipient':{},'obligation_id':'source'},row,root=tmp_path)
    native=json.dumps({'operation':read['operation'],'payload':read['payload']},sort_keys=True)
    assert native in text and 'Scoped ACCEPT' not in text   # a read, never a copied reply body
    assert delivery._reply_target(tmp_path,'book',row)=={'exact_reply_read':{'operation':'author_history','payload':read['payload']}}
    writing_records.bank(tmp_path,{'record':'writing-reply','id':'WR-reviewer-2','turn_id':'WT-reviewer-1','session_id':'WS-reviewer-1',
                                   'project':'book','status':'completed','text':'A second reply.'})
    assert delivery.exact_reply_read(tmp_path,'book','WT-reviewer-1') is None
    assert 'Exact stored reply' not in delivery._continuation_text({'id':'WORK-x','project':'book'},{'id':'WD-1','recipient':{},'obligation_id':'source'},row,root=tmp_path)
from test_source_native_allowance import _codex_runtime
from test_eigen_continuity_owner import produce, arm_payload, end_producer, proof, work, completion, summary, judged, PRODUCER, HUMAN, REVIEWER
from laplace.work import development_source as D, project_work as W, project_work_review as R, work_delivery as WD, project_work_continuity as C
from laplace.writing import source_execution as X, turn_execution as T


def ready(s, **arm):
    grant, account, candidate = produce(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate, **arm), PRODUCER)['intent']
    end_producer(s)
    _saved, reference = proof(s)
    D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)
    state = completion(s, intent)['readiness']
    assert state['state'] == 'READY', state
    return grant, account, intent, state['basis']


def events(s):
    return [row for row in work(s).get('deliveries') or () if row.get('kind') == WD.EVENT]


def handoffs(s):
    return [row for row in work(s).get('phases') or () if row.get('phase') == 'handoff']


def cont(s, intent, basis, door=HUMAN):
    return WD.handle(s['root'], 'public', {'action': 'continue', 'intent_id': intent['id'], 'expected_basis': basis}, door)


def completion_native(intent_id, project='public', work_id='work'):
    """The exact completion owner's own native read, as the delivery owner must carry it (operation and payload only)."""
    read = C.handle(project, work_id, {'part': 'completion', 'intent_id': intent_id})
    return json.dumps({'operation': read['operation'], 'payload': read['payload']}, sort_keys=True)


def carried(launch, needle):
    """Whether the actually admitted provider launch (the real composed prompt the stub received) carries needle."""
    try:
        values = list(vars(launch).values())
    except TypeError:
        values = [getattr(launch, name, None) for name in dir(launch) if not name.startswith('_')]
    return any(needle in str(value) for value in values)


def verified(root, project, reference):
    """Follow a proof row through the real scoped Artifact owner with its exact pin."""
    from laplace.work.project_work_evidence import _artifact
    try:
        observed, _stamp = _artifact(root, project, reference, verify=True)
    except (ValueError, OSError, KeyError):
        return False
    return observed.get('integrity') == 'VERIFIED'


def test_continue_after_late_proof_runs_the_real_delivery_once_with_producer_origin(source, monkeypatch):
    s = source
    launches = []
    _codex_runtime(monkeypatch, launches)
    _grant, account, intent, basis = ready(s)
    before = X.status(s['root'], account)
    result = cont(s, intent, basis)
    event = result['event']
    assert result['reused'] is False and event['state'] == 'ADMITTED' and len(launches) == 1, event
    [submitted] = [row for row in events(s) if row['state'] == 'SUBMITTED']
    assert submitted['actor']['turn_id'] == 'WT-allowance' and submitted['actor']['session_id'] == s['parent']['id']
    assert submitted['dispatcher']['origin'] == 'human' and submitted['continuation']['parent_turn_id'] == 'WT-allowance'
    assert submitted['source_execution'] == account and submitted['prepared_completion']['intent_id'] == intent['id']
    assert event['dispatcher']['origin'] == 'human' and event['prepared_completion']['intent_id'] == intent['id']
    [handoff] = handoffs(s)
    assert handoff['actor']['turn_id'] == 'WT-allowance' and handoff['continuation_origin']['dispatcher']['origin'] == 'human'
    assert handoff['pins'] == intent['production']['pins'] and handoff['continuation_origin']['proofs'][0]['slot_id'] == 'a-functional'
    after = X.status(s['root'], account)
    assert (after['app_admissions'], after['sessions']) == (before['app_admissions'] + 1, before['sessions'] + 1)
    # the reviewer request carries the complete owner template: verdict null, closed limits and a pure preflight read
    text = WD._request_text(work(s), submitted, handoff, s['root'])
    assert '"verdict": null' in text and '"summary": 2000' in text and '"findings": 20' in text and "'part': 'preflight'" not in text
    assert '"part": "preflight"' in text and ('"request_id": "REVIEW-' + event['id'] + '"') in text
    # Source5: one body-free exact completion read, derived from the banked handoff and matching the event's prepared intent,
    # in the composed request AND in the prompt the reviewer launch actually received; proof bodies stay out
    native = completion_native(intent['id'])
    assert WD.prepared_completion_read(work(s), handoff, submitted) == json.loads(native)
    assert native in text and carried(launches[0], native) and text.count(native) == 1
    with pytest.raises(ValueError, match='does not match'):
        WD.prepared_completion_read(work(s), handoff, {**submitted, 'prepared_completion': {'intent_id': 'CI-' + '0' * 24}})
    view = completion(s, intent)
    [row] = view['proofs']
    assert row['slot_id'] == 'a-functional' and (view['readiness'].get('continued') or {}).get('event_id') == event['id']
    reference = {'path': row['path'], 'scope': row['scope'], 'expected_sha256': row['observed_sha256']}
    assert verified(s['root'], 'public', reference) and not verified(s['root'], 'other-project', reference)
    from laplace.projects import artifacts
    target = artifacts.resolve_path(s['root'], 'public', row['path'])
    body = target.read_bytes()
    assert body.decode('utf-8', 'replace')[:40] not in text   # a read coordinate, never the proof body
    target.write_bytes(body + b'\nchanged after arrival\n')
    assert not verified(s['root'], 'public', reference)   # a changed proof refuses; its arrival row is not rewritten
    target.write_bytes(body)
    assert verified(s['root'], 'public', reference)
    # replay, including a stale basis after commit, returns the same identities and admits nothing new
    again, stale = cont(s, intent, basis), cont(s, intent, 'sha256:' + '0' * 64)
    assert again['reused'] and stale['reused'] and again['event']['id'] == stale['event']['id'] == event['id']
    assert len(launches) == 1 and len(handoffs(s)) == 1 and X.status(s['root'], account)['app_admissions'] == after['app_admissions']
    assert judged(s, intent)['state'] == 'CONTINUED' and summary(s)['next']['kind'] == 'await-delivery'
    # the reviewer terminal returns ONCE into the ORIGINAL producer session on the same fixed account
    review = launches[0]
    reply = {'status': 'completed', 'text': 'Controlled reviewer terminal; no verdict recorded.'}
    T._bank_reply(review, reply)
    T._finish(review, reply)
    states = [row['state'] for row in events(s)]
    assert states.count('RESULT') == 1 and states[-1] == 'CONTINUED', states
    assert len(launches) == 2 and launches[1].session_id == s['parent']['id']
    assert carried(launches[1], native)   # the automatic original-parent prompt carries the same intact read
    [queued] = [t for t in W._tasks('public', s['root']).values()
                if (t.get('logical_target') or {}).get('event_id') == event['id'] and t.get('task_kind') == 'session-request']
    assert native in queued['goal'] and len(queued['goal']) <= 2000
    pending = WD.pending_continuations(s['root'], 'public', s['parent']['id'])
    assert [p['goal'] for p in pending if p['id'] == queued['id']] == [queued['goal']]
    assert X.status(s['root'], account)['app_admissions'] == before['app_admissions'] + 2
    WD.recover(s['root'], 'public', {'event_id': event['id']}, HUMAN)
    assert [row['state'] for row in events(s)] == states and len(launches) == 2
    # proof arrival plus a terminal reviewer turn is not semantic acceptance
    assert WD.status(s['root'], 'public', {'event_id': event['id']}, HUMAN)['event']['acceptance']['satisfied'] is False
    T._finish(launches[1], {'status': 'interrupted'})


def test_lost_acknowledgement_after_commit_recovers_the_same_handoff_and_event(source, monkeypatch):
    s = source
    launches = []
    _codex_runtime(monkeypatch, launches)
    _grant, account, intent, basis = ready(s)
    real, calls = WD.recover, []

    def lost(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise OSError('fixture: the Continue commit happened but its acknowledgement was lost')
        return real(*args, **kwargs)
    monkeypatch.setattr(WD, 'recover', lost)
    with pytest.raises(OSError):
        cont(s, intent, basis)
    assert len(handoffs(s)) == 1 and [row['state'] for row in events(s)] == ['SUBMITTED'] and not launches
    assert judged(s, intent)['state'] == 'CONTINUED'
    second = cont(s, intent, basis)
    assert second['reused'] and second['event']['state'] == 'ADMITTED' and len(launches) == 1 and len(handoffs(s)) == 1
    assert [row['state'] for row in events(s)].count('SUBMITTED') == 1 and len({row['id'] for row in events(s)}) == 1
    assert X.status(s['root'], account)['app_admissions'] == 2
    T._finish(launches[0], {'status': 'interrupted'})


@pytest.mark.parametrize('case', ['expired', 'unknown', 'spent', 'stopped'])
def test_closed_or_unknown_account_and_stopped_producer_withhold_continue_without_effects(source, monkeypatch, case):
    s = source
    launches = []
    _codex_runtime(monkeypatch, launches)
    grant, account, candidate = produce(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    end_producer(s, 'interrupted' if case == 'stopped' else 'completed')
    _saved, reference = proof(s)
    D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)
    if case == 'expired':
        later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=2)
        monkeypatch.setattr(X, '_now', lambda: later)
    elif case == 'unknown':
        X.stop(s['root'], account, 'CLAIM_PUBLICATION_UNKNOWN')
    elif case == 'spent':
        for n in range(X.status(s['root'], account)['app_remaining']):
            X.reserve_app(s['root'], account, 'public-spend-%d' % n, session_id=s['parent']['id'], role='parent')
    state = completion(s, intent)['readiness']
    expected = {'expired': 'CLOSED', 'unknown': 'HELD', 'spent': 'CLOSED', 'stopped': 'CLOSED'}[case]
    code = {'expired': 'ACCOUNT_CLOSED', 'unknown': 'ACCOUNT_UNKNOWN', 'spent': 'ACCOUNT_CLOSED', 'stopped': 'PRODUCER_STOPPED'}[case]
    assert state['state'] == expected and code in [row['code'] for row in state['reasons']], state
    ledger = W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError, match=expected):
        cont(s, intent, state['basis'])
    assert not launches and not events(s) and not handoffs(s)
    if case == 'stopped':   # review F5: the observed Stop is now durable; nothing else was written
        assert C._intent(work(s), intent['id'])['state'] == 'WITHDRAWN'
    else:
        assert W._ledger(s['root']).read_bytes() == ledger
    assert summary(s)['next']['kind'] == 'inspect'


def test_changed_basis_and_foreign_dispatch_refuse_while_ordinary_human_source_delivery_stays_refused(source, monkeypatch):
    s = source
    launches = []
    _codex_runtime(monkeypatch, launches)
    grant, account, intent, basis = ready(s)
    evaluator = s['checkout'] / 'evaluator.py'
    original = evaluator.read_bytes()
    evaluator.write_bytes(original + b'# changed after arming\n')
    with pytest.raises(W.WorkConflict):
        cont(s, intent, basis)
    held = completion(s, intent)['readiness']
    assert held['state'] == 'HELD'
    with pytest.raises(ValueError, match='HELD'):
        cont(s, intent, held['basis'])
    evaluator.write_bytes(original)
    with pytest.raises(ValueError, match='review turn'):
        cont(s, intent, basis, REVIEWER)
    assert not events(s) and not handoffs(s) and not launches
    # the ordinary door is unchanged: a human Source delivery without the original attached parent is refused
    ordinary = R.record('public', {'id': 'work', 'phase': 'handoff', 'request_id': 'public-ordinary-handoff',
                                   'expected_work_revision': W._task_revision(work(s)), 'obligations': ['source'],
                                   'source_basis': {'grant_id': grant['id'], 'candidate_id': intent['production']['candidate_id']},
                                   'pins': intent['production']['pins']}, s['root'], door=HUMAN)['phase']
    with pytest.raises(ValueError, match='trusted original'):
        WD.submit(s['root'], 'public', {'action': 'submit', 'work_id': 'work', 'expected_work_revision': W._task_revision(work(s)),
                                        'handoff_id': ordinary['id'], 'obligation_id': 'source', 'recipient_binding_id': s['binding']['id']}, HUMAN)
    assert not events(s) and not launches
    # the prepared path dispatches on the restored basis; a native author dispatcher is recorded apart from the producer
    fresh = completion(s, intent)['readiness']
    assert fresh['state'] == 'READY'
    result = cont(s, intent, fresh['basis'], s['door'])
    [submitted] = [row for row in events(s) if row['state'] == 'SUBMITTED']
    assert result['event']['state'] == 'ADMITTED' and len(launches) == 1
    assert submitted['dispatcher']['turn_id'] == 'WT-parent' and submitted['actor']['turn_id'] == 'WT-allowance'
    assert submitted['source_execution'] == account
    T._finish(launches[0], {'status': 'interrupted'})


def test_no_parent_policy_keeps_the_return_explicitly_absent_and_pays_no_metadata_turn(source, monkeypatch):
    s = source
    launches = []
    _codex_runtime(monkeypatch, launches)
    _grant, account, intent, basis = ready(s, return_policy={'review_deadline_s': 3600, 'max_attempts': 1, 'parent_return': None})
    assert intent['policy']['planned'] == {'apps': 1, 'sessions': 1}
    assert cont(s, intent, basis)['event']['state'] == 'ADMITTED' and len(launches) == 1
    reply = {'status': 'completed', 'text': 'Controlled reviewer terminal; no verdict recorded.'}
    T._bank_reply(launches[0], reply)
    T._finish(launches[0], reply)
    last = events(s)[-1]
    assert last['state'] == 'PARENT_REFUSED' and 'no approved parent route' in last['reason'] and len(launches) == 1
    assert X.status(s['root'], account)['app_admissions'] == 2


def test_prepared_continue_refuses_before_any_effect_without_the_complete_template(source, monkeypatch):
    """Review F4: the prepared path never pays for a review whose complete owner template cannot be built."""
    s = source
    launches = []
    _codex_runtime(monkeypatch, launches)
    _grant, account, intent, basis = ready(s)

    real_template = R.review_template

    def broken(*args, **kwargs):
        raise ValueError('fixture: template owner unavailable')
    monkeypatch.setattr(R, 'review_template', broken)
    ledger = W._ledger(s['root']).read_bytes()
    # readiness itself requires the ACTUAL complete template (the request's legacy fallback brief does not count as fitting)
    unfit = completion(s, intent)['readiness']
    assert unfit['state'] == 'HELD' and [row['code'] for row in unfit['reasons']] == ['REVIEW_REQUEST_UNFIT'], unfit
    assert 'complete owner review template' in unfit['reasons'][0]['reason']
    for expected in (basis, unfit['basis']):
        with pytest.raises(ValueError):
            cont(s, intent, expected)
    assert W._ledger(s['root']).read_bytes() == ledger and not handoffs(s) and not events(s) and not launches
    # and the handoff path keeps its own pre-append template guard (defence in depth on a direct call)
    tasks = W._tasks('public', s['root'])
    with pytest.raises(ValueError, match='complete owner review template'):
        C._handoff(s['root'], 'public', tasks, tasks['work'], C._intent(tasks['work'], intent['id']), {'actor': 'dispatcher', 'origin': 'human'})
    assert W._ledger(s['root']).read_bytes() == ledger and not handoffs(s) and not events(s) and not launches
    assert X.status(s['root'], account)['app_admissions'] == 1
    # The exact prepared reviewer request is composed before the first irreversible append, through the existing
    # work_delivery ceiling: exactly at the cap it fits; an unfittable one holds READY back and Continue writes nothing.
    monkeypatch.setattr(R, 'review_template', real_template)
    tasks = W._tasks('public', s['root'])
    fit = C.request_fit(s['root'], 'public', tasks, tasks['work'], C._intent(tasks['work'], intent['id']))
    assert fit['state'] == 'FITS' and 0 < fit['bytes'] <= WD.MAX_REVIEW_REQUEST_BYTES == 64 * 1024
    # the pure prospective fit measures the same completion read the real request will carry (staged handoff, no event field)
    staged, prospective_event, staged_handoff = C._prospective(s['root'], 'public', tasks, tasks['work'], C._intent(tasks['work'], intent['id']))
    prospective = WD._request_text(staged, prospective_event, staged_handoff, s['root'])
    assert completion_native(intent['id']) in prospective and len(prospective.encode('utf-8')) == fit['bytes']
    assert W._ledger(s['root']).read_bytes() == ledger
    monkeypatch.setattr(WD, 'MAX_REVIEW_REQUEST_BYTES', fit['bytes'])
    assert completion(s, intent)['readiness']['state'] == 'READY'
    monkeypatch.setattr(WD, 'MAX_REVIEW_REQUEST_BYTES', 512)
    held = completion(s, intent)['readiness']
    assert held['state'] == 'HELD' and [row['code'] for row in held['reasons']] == ['REVIEW_REQUEST_UNFIT'], held
    assert held['facts']['review_request'] == 'UNFIT'
    for expected in (basis, held['basis']):
        with pytest.raises(ValueError):
            cont(s, intent, expected)
    assert W._ledger(s['root']).read_bytes() == ledger and not handoffs(s) and not events(s) and not launches
    monkeypatch.setattr(WD, 'MAX_REVIEW_REQUEST_BYTES', 64 * 1024)
    assert completion(s, intent)['readiness']['state'] == 'READY'


def test_prepared_completion_read_survives_the_parent_and_queued_bounds_and_ordinary_text_is_unchanged(tmp_path, monkeypatch):
    """The automatic parent text keeps its 4000-character bound by cutting prose, never the trailing machine reads; a
    nonprepared Source delivery carries no completion line."""
    ident = 'CI-' + 'a' * 24
    native = completion_native(ident, 'book', 'WORK-x')
    monkeypatch.setattr(WD, '_review_phase_line', lambda *a, **k: 'é漢' * 900 + '\n')
    monkeypatch.setattr(WD, '_source_description', lambda basis: {'repository': 'fixture'})
    intent = {'id': 'WD-1', 'recipient': {}, 'obligation_id': 'source', 'handoff_id': 'PHASE-1', 'source_basis': {'grant_id': 'DG-1'},
              'prepared_completion': {'intent_id': ident}}
    row = {'turn_id': 'WT-1', 'result': {'status': 'completed'}, 'acceptance': {'status': 'HOLD', 'currentness': 'CURRENT'}}
    task = {'id': 'WORK-x', 'project': 'book'}
    text = WD._continuation_text(task, intent, row, root=tmp_path)
    assert len(text) <= 4000 and native in text and text.endswith('complete the queued continuation request with task_status when done.')
    plain = WD._continuation_text(task, {k: v for k, v in intent.items() if k != 'prepared_completion'}, row, root=tmp_path)
    assert 'Prepared Source completion' not in plain and len(plain) <= 4000
    assert WD.prepared_completion_read(task, None, {'id': 'WD-2'}) is None
    # a valid but long Work id: the whole read cannot fit, so the exact delivery-status descent replaces it; no read is cut
    long_task = {'id': 'WORK-' + 'x' * 3600, 'project': 'book'}
    long_text = WD._continuation_text(long_task, intent, row, root=tmp_path)
    assert len(long_text) <= WD.PARENT_TEXT_CHARS and '"operation"' not in long_text
    assert 'follow them from the delivery status read below' in long_text and long_text.endswith('task_status when done.')
    short_goal = WD._continuation_goal('S' * 3000, json.loads(native), 'WD-1')
    assert len(short_goal) <= WD.QUEUED_GOAL_CHARS and short_goal.endswith(native)
    long_goal = WD._continuation_goal('S' * 3000, json.loads(completion_native(ident, 'book', long_task['id'])), 'WD-1')
    assert len(long_goal) <= WD.QUEUED_GOAL_CHARS and '"event_id": "WD-1"' in long_goal and long_task['id'] not in long_goal


def test_completion_read_with_four_long_multibyte_proofs_is_a_bounded_exact_projection():
    """dd039/b02: four valid long non-BMP path-form proofs exceeded the 30000-byte completion line on READY and CONTINUED.
    The owner names each duplicated reference once and, only if still needed, reads each long proof through its exact
    Artifact id and pin; every slot, proof identity, scope and pin stays. A short response is unchanged; five slots refuse."""
    long_path = 'proofs/' + '\U0001F9EA' * 690 + '.json'   # about 2770 UTF-8 bytes each
    proofs, slots, continued = [], [], []
    for n in range(4):
        path = long_path.replace('.json', '-%d.json' % n)
        ref = {'path': path, 'scope': 'project', 'expected_sha256': 'sha256:' + str(n) * 64}
        proofs.append({'id': 'CP-%024d' % n, 'intent_id': 'CI-' + 'a' * 24, 'slot_id': 'slot-%d' % n, 'reference': ref, 'artifact_id': 'ART-%d' % n,
                       'path': path, 'scope': 'project', 'observed_sha256': str(n) * 64, 'ts': 'now', 'meaning': 'arrival',
                       'attached_by': 'x', 'attached_origin': 'native'})
        slots.append({'id': 'slot-%d' % n, 'label': 'L', 'filled': True, 'integrity': 'VERIFIED', 'reference': ref})
        continued.append({'slot_id': 'slot-%d' % n, 'reference': ref})
    for state, ready in (('READY', {'state': 'READY', 'slots': slots}),
                         ('CONTINUED', {'state': 'CONTINUED', 'slots': [], 'continued': {'id': 'CC-1', 'proofs': continued}})):
        response = {'schema_version': C.SCHEMA, 'part': 'completion', 'intent': {'id': 'CI-' + 'a' * 24}, 'readiness': ready, 'proofs': proofs}
        assert C._completion_bytes(response) > C.completion_line(), state   # the counterexample scale
        bounded = C._bounded_completion(response)
        assert C._completion_bytes(bounded) <= C.completion_line() and bounded['projection']['state'] == 'BOUNDED'
        assert [(p['id'], p['slot_id'], p['artifact_id'], p['scope'], p['observed_sha256'], p['reference']['expected_sha256']) for p in bounded['proofs']] == \
               [(p['id'], p['slot_id'], p['artifact_id'], p['scope'], p['observed_sha256'], p['reference']['expected_sha256']) for p in proofs]
        for kept, original in zip(bounded['proofs'], proofs):
            assert kept.get('path') == original['path'] or kept['read'] == {'operation': 'read_artifact', 'payload': {
                'id': original['artifact_id'], 'offset': 0, 'limit': 16000, 'expected_sha256': 'sha256:' + original['observed_sha256']}}
        assert response['proofs'][0]['reference']['path'] == proofs[0]['path']   # the owner's own rows are never mutated
    small = {'schema_version': C.SCHEMA, 'part': 'completion', 'proofs': proofs[:1]}
    assert C._bounded_completion(small) == small
    with pytest.raises(ValueError):
        C._validate(C.slot_schema(), [{'id': 'slot-%d' % n, 'label': 'L'} for n in range(5)], 'proof_slots')


def _completion_of(value):
    """The continuity completion response inside whatever door envelope carries it."""
    if isinstance(value, dict):
        if value.get('part') == 'completion' and 'proofs' in value:
            return value
        value = list(value.values())
    if isinstance(value, list):
        for item in value:
            found = _completion_of(item)
            if found is not None:
                return found
    return None


def _followed(root, payload):
    """Follow one issued Artifact descriptor through the actual native read door to its end: (bytes, pages)."""
    from laplace.native import tools
    body, pages = b'', 0
    while True:
        page = tools.execute(root, 'public', 'work', 'read_artifact', payload, turn_id='WT-parent')
        assert page.get('ok', True) is not False and isinstance(page.get('content'), str), str(page)[:600]
        body += page['content'].encode('utf-8')
        pages += 1
        if page.get('next_offset') is None:
            return body, pages
        payload = {**payload, 'offset': page['next_offset']}


def test_four_long_multibyte_proof_slots_through_the_actual_doors_follow_every_issued_descriptor(source, monkeypatch):
    """Source6 (adapted from the f336 probe): an eligible producer arms four slots, four legal nested long multibyte
    Artifacts are stored and attached (ART-id and path forms), and READY then CONTINUED are read through tools.execute and
    project_work_surface.handle within the delivery line. Every issued descriptor is followed to its end with pages and
    hashes, no proof body reaches an envelope or the reviewer prompt, a fifth slot refuses through the actual owner with
    no append, and foreign, changed and wrong-hash reads refuse. The raw byte maxima are recorded."""
    import hashlib
    from urllib.parse import parse_qs, urlsplit
    from laplace.native import tools
    from laplace.projects import artifacts
    from laplace.web import project_work_surface
    from laplace.writing import delivery
    s = source
    root = s['root']
    launches = []
    _codex_runtime(monkeypatch, launches)
    grant, _account, candidate = produce(s)
    slots = [{'id': 'slot-%d' % n, 'label': 'Independent proof %d' % n} for n in range(4)]
    intent = D.handle(root, 'public', arm_payload(s, grant, candidate, proof_slots=slots), PRODUCER)['intent']
    end_producer(s)
    marker = 'BODY_NOT_IN_ENVELOPE_'
    stored, names = {}, {}
    for n, slot in enumerate(slots):
        name = '/'.join([('ж\U0001F331' * 30) + str(part) for part in range(15)] + ['proof-%d-α\U0001F331.txt' % n])
        saved, reference = proof(s, name, marker + str(n) + ' ' + 'é漢\U0001F331' * 6000)
        if n % 2:
            reference = {'path': 'proofs/' + name, 'scope': saved.get('scope') or 'project', 'expected_sha256': saved['revision']}
        D.handle(root, 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': slot['id'], 'reference': reference}, HUMAN)
        stored[slot['id']], names[slot['id']] = saved, 'proofs/' + name
    handle = C.handle('public', 'work', {'part': 'completion', 'intent_id': intent['id']})
    maxima = {'native_emitted': 0, 'http_raw': 0}

    def doors(expected):
        native = tools.execute(root, 'public', 'work', handle['operation'], handle['payload'], turn_id='WT-parent')
        url = urlsplit(handle['http']['url'])
        code, _kind, raw = project_work_surface.handle(url.path, parse_qs(url.query), handle['http']['method'], b'', root)
        assert code == 200, raw[:600]
        views = [_completion_of(native), _completion_of(json.loads(raw))]
        for view in views:
            assert view is not None and view['readiness']['state'] == expected, str(native)[:600]
            assert sorted(row['slot_id'] for row in view['proofs']) == [slot['id'] for slot in slots]
        maxima['native_emitted'] = max(maxima['native_emitted'], delivery.emitted(native))
        maxima['http_raw'] = max(maxima['http_raw'], len(raw))
        assert not (native.get('delivery_bound') or {}).get('exceeded') and max(maxima.values()) <= 30000, maxima
        assert marker not in json.dumps(native, ensure_ascii=False) and marker not in raw.decode('utf-8')   # no proof body
        return views

    def follow(view):
        for row in view['proofs']:
            saved, pin = stored[row['slot_id']], str(row['observed_sha256']).removeprefix('sha256:')
            payload = dict(row['read']['payload']) if 'read' in row else {
                'path': row['path'], 'scope': row['scope'], 'offset': 0, 'limit': 16000, 'expected_sha256': 'sha256:' + pin}
            body, pages = _followed(root, payload)
            assert pages > 1 and hashlib.sha256(body).hexdigest() == pin == str(saved['revision']).removeprefix('sha256:'), row['slot_id']
            assert body.decode('utf-8').startswith(marker + row['slot_id'][-1])

    assert completion(s, intent)['readiness']['state'] == 'READY'
    for view in doors('READY'):
        follow(view)
    basis = completion(s, intent)['readiness']['basis']
    assert cont(s, intent, basis)['event']['state'] == 'ADMITTED' and len(launches) == 1
    assert not carried(launches[0], marker)   # the reviewer prompt carries reads, never a proof body
    views = doors('CONTINUED')
    for view in views:
        follow(view)
    # a fifth slot refuses through the actual owner and appends nothing
    ledger = W._ledger(root).read_bytes()
    with pytest.raises(ValueError):
        D.handle(root, 'public', arm_payload(s, grant, candidate, request_id='public-five-slot-arm',
                                             proof_slots=slots + [{'id': 'slot-4', 'label': 'Fifth proof'}]), PRODUCER)
    assert W._ledger(root).read_bytes() == ledger
    # foreign, wrong-hash and changed reads refuse
    row = views[1]['proofs'][0]
    path, saved = names[row['slot_id']], stored[row['slot_id']]
    reference = {'path': path, 'scope': row['scope'], 'expected_sha256': saved['revision']}
    assert verified(root, 'public', reference) and not verified(root, 'other-project', reference)
    with pytest.raises(Exception):
        artifacts.read(root, 'public', {'path': path, 'scope': row['scope'], 'expected_sha256': 'sha256:' + '0' * 64})
    target = artifacts.resolve_path(root, 'public', path)
    original = target.read_bytes()
    target.write_bytes(original + b'\nchanged after arrival\n')
    try:
        assert not verified(root, 'public', reference)
        with pytest.raises(Exception):
            artifacts.read(root, 'public', {'path': path, 'scope': row['scope'], 'expected_sha256': saved['revision']})
    finally:
        target.write_bytes(original)
    assert verified(root, 'public', reference) and W._ledger(root).read_bytes() == ledger
    print('raw byte maxima', json.dumps(maxima, sort_keys=True))
    T._finish(launches[0], {'status': 'interrupted'})


def test_stale_pre_lock_recover_loses_to_the_winning_terminal_settlement(source, monkeypatch):
    """Source6: recover reads its pre-lock history while the event is ADMITTED and is held by a barrier just before the
    event lock. The reviewer's terminal settlement then wins (RESULT, then the once-only parent return). Resumed, recover
    refreshes under the lock: no RESULT to ADMITTED, one RESULT, no extra turn and no second return."""
    import threading
    s = source
    launches = []
    _codex_runtime(monkeypatch, launches)
    _grant, _account, intent, basis = ready(s)
    event = cont(s, intent, basis)['event']
    assert event['state'] == 'ADMITTED' and len(launches) == 1
    real_lock, entered, release, holder, errors = WD._event_lock, threading.Event(), threading.Event(), {}, []

    def gated(root, event_id):
        if threading.current_thread() is holder.get('thread') and not entered.is_set():
            entered.set()
            assert release.wait(30)
        return real_lock(root, event_id)
    monkeypatch.setattr(WD, '_event_lock', gated)

    def run():
        try:
            WD.recover(s['root'], 'public', {'event_id': event['id']}, HUMAN)
        except BaseException as error:   # surfaced below
            errors.append(error)
    thread = threading.Thread(target=run)
    holder['thread'] = thread
    thread.start()
    assert entered.wait(30)   # recover holds its stale pre-lock read and waits just before the event lock
    reply = {'status': 'completed', 'text': 'Controlled reviewer terminal; no verdict recorded.'}
    T._bank_reply(launches[0], reply)
    T._finish(launches[0], reply)
    won = [row['state'] for row in events(s)]
    assert won.count('RESULT') == 1 and won[-1] == 'CONTINUED' and len(launches) == 2, won
    release.set()
    thread.join(30)
    assert not thread.is_alive() and not errors, errors
    states = [row['state'] for row in events(s)]
    assert states == won and 'ADMITTED' not in states[states.index('RESULT'):], states
    assert len(launches) == 2 and states.count('CONTINUED') == 1
    T._finish(launches[1], {'status': 'interrupted'})


def test_deliver_replays_an_already_found_terminal_turn_once_and_refuses_foreign_custody(source, monkeypatch):
    """Source6: the reviewer admission commits at the turn owner but its ADMITTED publication is lost, and the reviewer's
    terminal reply banks while the event has no admitted coordinates. A replay under a mismatched Source custody refuses
    and appends nothing. The genuine replay publishes one recovered ADMITTED, settles the saved reply once (one RESULT,
    one parent return) and repeats change nothing."""
    s = source
    launches = []
    _codex_runtime(monkeypatch, launches)
    _grant, account, intent, basis = ready(s)
    real_append = W._append

    def lost(root, row, **kwargs):
        if row.get('kind') == WD.EVENT and row.get('state') == 'ADMITTED' and not row.get('recovered'):
            raise OSError('fixture: the admission committed at the turn owner but its ADMITTED publication was lost')
        return real_append(root, row, **kwargs)
    monkeypatch.setattr(W, '_append', lost)
    with pytest.raises(OSError):
        cont(s, intent, basis)
    monkeypatch.setattr(W, '_append', real_append)
    assert len(launches) == 1 and 'ADMITTED' not in [row['state'] for row in events(s)]
    event_id = events(s)[0]['id']
    reply = {'status': 'completed', 'text': 'Controlled reviewer terminal; no verdict recorded.'}
    T._bank_reply(launches[0], reply)
    T._finish(launches[0], reply)
    assert 'RESULT' not in [row['state'] for row in events(s)]   # the terminal hook found no admitted coordinates
    real_for_turn, ledger = X.for_turn, W._ledger(s['root']).read_bytes()
    monkeypatch.setattr(X, 'for_turn', lambda *args, **kwargs: {**account, 'commission_id': 'SC-' + 'f' * 24})
    with pytest.raises(ValueError, match='different commission custody'):
        WD._deliver(s['root'], 'public', event_id)
    assert W._ledger(s['root']).read_bytes() == ledger and len(launches) == 1
    monkeypatch.setattr(X, 'for_turn', real_for_turn)
    assert WD._deliver(s['root'], 'public', event_id) is None
    states = [row['state'] for row in events(s)]
    [admitted] = [row for row in events(s) if row['state'] == 'ADMITTED']
    assert admitted['recovered'] and admitted['reused'] and states.count('RESULT') == 1 and states[-1] == 'CONTINUED', states
    assert len(launches) == 2 and launches[1].session_id == s['parent']['id']
    WD._deliver(s['root'], 'public', event_id)
    WD.recover(s['root'], 'public', {'event_id': event_id}, HUMAN)
    assert [row['state'] for row in events(s)] == states and len(launches) == 2
    T._finish(launches[1], {'status': 'interrupted'})


@pytest.mark.parametrize('window', ['after-handoff', 'after-submitted'])
def test_crash_windows_inside_continue_recover_to_one_handoff_and_one_delivery(source, monkeypatch, window):
    """Review F8: a process lost after the handoff append, or after SUBMITTED but before the continue row, recovers to
    exactly one handoff, one delivery and one admission when the same Continue is repeated."""
    s = source
    launches, calls = [], []
    _codex_runtime(monkeypatch, launches)
    _grant, account, intent, basis = ready(s)
    if window == 'after-handoff':
        real = WD.submit_prepared

        def cut(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise OSError('fixture: process lost after the handoff append')
            return real(*args, **kwargs)
        monkeypatch.setattr(WD, 'submit_prepared', cut)
    else:
        real = W._append

        def cut(root, row, **kwargs):
            if row.get('kind') == C.CONTINUE and not calls:
                calls.append(1)
                raise OSError('fixture: process lost after SUBMITTED, before the continue row')
            return real(root, row, **kwargs)
        monkeypatch.setattr(W, '_append', cut)
    with pytest.raises(OSError):
        cont(s, intent, basis)
    assert len(handoffs(s)) == 1 and not launches
    assert [row['state'] for row in events(s)] == ([] if window == 'after-handoff' else ['SUBMITTED'])
    assert completion(s, intent)['readiness']['state'] == 'READY'
    again = cont(s, intent, basis)
    assert again['event']['state'] == 'ADMITTED' and len(launches) == 1 and len(handoffs(s)) == 1
    assert len({row['id'] for row in events(s)}) == 1 and [row['state'] for row in events(s)].count('SUBMITTED') == 1
    assert X.status(s['root'], account)['app_admissions'] == 2
    T._finish(launches[0], {'status': 'interrupted'})
