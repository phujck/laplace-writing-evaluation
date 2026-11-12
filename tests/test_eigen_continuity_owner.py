"""Eigen continuity owner controls (B slice of Root e716/a6d0).

The actual-Scope continuity read, the genuine producer's immutable cumulative completion intent, peer proof as an
arrival fact, readiness derived from changed proof/source, and the complete review template with pure preflight.
Public synthetic session/turn rows exercise the real owners; no provider, model, network or live service runs here.
"""
import copy
import json

import pytest

from test_source_use_joins import source  # noqa: F401  (the public Source fixture)
from test_source_native_allowance import attached, _detached_setup
from laplace.work import development_source as D, project_work as W, project_work_review as R, project_work_continuity as C
from laplace.work.owner_discovery import project_scope
from laplace.writing import records, source_execution as X
from laplace.projects import artifacts

PRODUCER = {'origin': 'native', 'turn_id': 'WT-allowance'}
HUMAN = {'origin': 'human'}
REVIEWER = {'origin': 'native', 'turn_id': 'WT-review'}
POLICY = {'review_deadline_s': 3600, 'max_attempts': 1, 'parent_return': {'admit_idle': True, 'max_attempts': 1, 'max_depth': 2}}


def work(s):
    return W._tasks('public', s['root'])['work']


def produce(s):
    """Two committed effects of the opted-in grant (guide.md, then src/answer.py): cumulative inputs exceed the last candidate."""
    grant, account, _payload = attached(s, native=40)
    for path, old, new in (('guide.md', 'Public unchanged documentation.', 'Public continuity documentation.'),
                           ('src/answer.py', 'unique old', 'continuity owner')):
        made = D.candidate(s['root'], 'public', {'grant_id': grant['id'], 'files': [
            {'path': path, 'before_sha256': D._pin(s['checkout'] / path), 'edits': [{'old': old, 'new': new}]}]}, PRODUCER)
        assert D.apply(s['root'], 'public', {'candidate_id': made['candidate_id']}, PRODUCER)['effect']['state'] == 'COMMITTED'
    return grant, account, made['candidate_id']


STAGE = {'id': 'public-continuity-stage', 'pre_source_review': ['Public fixture: independent review of the whole cumulative subject.'],
         'post_adoption': ['Public fixture: ordinary app Source check after adoption.']}


def full_context(s, pins):
    """The genuine checked reading offer: whole-file windows of every pinned input, from its exact reader text."""
    return {'windows': [{'path': p, 'line_start': 1, 'line_end': len(D._reader_text((s['checkout'] / p).read_bytes().decode()).splitlines())}
                        for p in sorted(pins)]}


def arm_payload(s, grant, candidate, **over):
    pins = {path: D._pin(s['checkout'] / path) for path in ('src/answer.py', 'evaluator.py', 'guide.md')}
    payload = {'action': 'arm', 'grant_id': grant['id'], 'candidate_id': candidate, 'request_id': 'public-continuity-arm',
               'expected_work_revision': W._task_revision(work(s)), 'obligation_id': 'source', 'recipient_binding_id': s['binding']['id'],
               'pins': pins, 'proof_slots': [{'id': 'a-functional', 'label': 'Independent fixed-runtime functional proof'}],
               'return_policy': copy.deepcopy(POLICY)}
    payload.update(over)
    # A Source-scope obligation takes the full prepared route: the genuine checked reading offer and an explicit typed subject.
    # Guide/legacy arms and callers that pass either field themselves keep exactly what they pass.
    if payload['obligation_id'] == 'source' and 'source_context' not in over and 'source_subject' not in over:
        payload['source_context'] = full_context(s, payload['pins'])
        payload['source_subject'] = {'stage': copy.deepcopy(STAGE)}
    return payload


def end_producer(s, status='completed'):
    records.bank(s['root'], {'record': 'writing-reply', 'id': 'WR-producer-' + status, 'turn_id': 'WT-allowance', 'session_id': s['parent']['id'],
                             'project': 'public', 'status': status, 'text': 'Producer ended; no inference.'})


def proof(s, name='a-functional.json', body='{"proof": "public functional control"}'):
    saved = artifacts.store(s['root'], 'public', {'path': 'proofs/' + name, 'before': None, 'content': body, 'reason': 'public peer proof fixture'})
    return saved, {'id': saved['id'], 'expected_sha256': saved['revision']}


def completion(s, intent):
    return C.read(s['root'], project_scope('public', 'native'), 'public', 'work', {'part': 'completion', 'intent_id': intent['id']})


def summary(s, **request):
    return C.read(s['root'], project_scope('public', 'native'), 'public', 'work', {'part': 'summary', **request})


def judged(s, intent):
    tasks = W._tasks('public', s['root'])
    return C.readiness(s['root'], 'public', tasks, tasks['work'], C._intent(tasks['work'], intent['id']))


def test_only_the_genuine_active_producer_arms_one_immutable_cumulative_intent(source):
    s = source
    grant, account, candidate = produce(s)
    payload = arm_payload(s, grant, candidate)
    # human door, review turn, and an unattached turn of the same author session cannot arm on the producer's behalf
    for door in (HUMAN, REVIEWER, s['door']):
        with pytest.raises(ValueError):
            D.handle(s['root'], 'public', payload, door)
    # the last candidate alone is not the cumulative Source input: guide.md changed in an earlier committed effect
    short = arm_payload(s, grant, candidate, pins={p: D._pin(s['checkout'] / p) for p in ('src/answer.py', 'evaluator.py')})
    with pytest.raises(ValueError, match='Cumulative Source inputs'):
        D.handle(s['root'], 'public', short, PRODUCER)
    assert not [row for row in work(s).get('development') or () if row.get('kind') == C.INTENT]
    # Source scope: no reading offer and no explicit subject refuses BEFORE any write and names the exact Source review-preflight;
    # so do a context without a subject, a subject without its typed stage, an incomplete plan and an unknown prior grant
    ledger = W._ledger(s['root']).read_bytes()
    bare = {key: value for key, value in payload.items() if key not in ('source_context', 'source_subject')}
    with pytest.raises(ValueError, match='missing source_context, source_subject') as refused:
        D.handle(s['root'], 'public', bare, PRODUCER)
    assert 'review-preflight' in str(refused.value) and grant['id'] in str(refused.value) and candidate in str(refused.value)
    for label, broken, expected in (
            ('context only', {**bare, 'source_context': payload['source_context']}, 'missing source_subject'),
            ('stage absent', {**payload, 'source_subject': {}}, 'missing source_subject.stage'),
            ('incomplete plan', {**payload, 'source_context': {'windows': [{'path': 'src/answer.py', 'line_start': 1, 'line_end': 1}]}}, 'INCOMPLETE.*review-preflight'),
            ('unknown prior grant', {**payload, 'source_subject': {**payload['source_subject'], 'prior': {'grants': ['DG-absent-prior']}}}, 'invalid.*review-preflight'),
            # an ordinary truthy non-dict stage is refused by the existing Source validator before any row (no redundant guard)
            ('string stage', {**payload, 'source_subject': {'stage': 'not-a-stage'}}, 'invalid.*review-preflight')):
        with pytest.raises(ValueError, match=expected):
            D.handle(s['root'], 'public', broken, PRODUCER)
        assert W._ledger(s['root']).read_bytes() == ledger, label
    assert not [row for row in work(s).get('development') or () if row.get('kind') == C.INTENT]
    # the actual active arm composes the exact prepared reviewer request before any write: over the existing ceiling it
    # refuses with no intent, and the same producer then arms under the restored same ceiling
    from laplace.work import work_delivery as WD
    ceiling = WD.MAX_REVIEW_REQUEST_BYTES
    WD.MAX_REVIEW_REQUEST_BYTES = 512
    try:
        with pytest.raises(ValueError, match='cannot be composed within its bound.*nothing was armed'):
            D.handle(s['root'], 'public', payload, PRODUCER)
    finally:
        WD.MAX_REVIEW_REQUEST_BYTES = ceiling
    assert W._ledger(s['root']).read_bytes() == ledger and WD.MAX_REVIEW_REQUEST_BYTES == 64 * 1024
    assert not [row for row in work(s).get('development') or () if row.get('kind') == C.INTENT]
    # the same live producer then arms with the actual checked context and subject
    armed = D.handle(s['root'], 'public', payload, PRODUCER)
    intent = armed['intent']
    assert armed['ok'] and armed['reused'] is False and intent['state'] == 'ARMED'
    assert intent['origin']['turn_id'] == 'WT-allowance' and intent['origin']['session_id'] == s['parent']['id']
    assert intent['origin']['commission_id'] == account['commission_id']
    assert intent['production']['changed'] == ['guide.md', 'src/answer.py']
    assert set(intent['production']['pins']) == {'src/answer.py', 'evaluator.py', 'guide.md'} and len(intent['production']['effects']) == 2
    assert intent['policy']['planned'] == {'apps': 2, 'sessions': 1} and intent['policy']['recipient_binding_id'] == s['binding']['id']
    # the intent row joins the Source custody, not the review phases, and moves no Work specification revision
    assert not [p for p in work(s).get('phases') or () if p.get('kind') == C.INTENT]
    assert W._task_revision(work(s)) == payload['expected_work_revision']
    assert intent['production']['review_subject']['stage'] == STAGE['id']
    again = D.handle(s['root'], 'public', payload, PRODUCER)
    assert again['reused'] and again['intent']['id'] == intent['id']
    # an explicit guide (non-source) obligation keeps its deliberately legacy plan-less meaning
    guide = D.handle(s['root'], 'public', arm_payload(s, grant, candidate, request_id='public-continuity-guide', obligation_id='guide'), PRODUCER)['intent']
    assert 'review_subject' not in guide['production'] and judged(s, guide)['state'] == 'AWAITING_PROOF'
    with pytest.raises(ValueError, match='immutable'):
        D.handle(s['root'], 'public', arm_payload(s, grant, candidate, proof_slots=[{'id': 'other', 'label': 'Other'}]), PRODUCER)
    with pytest.raises(ValueError, match='one immutable intent'):
        D.handle(s['root'], 'public', arm_payload(s, grant, candidate, request_id='public-continuity-arm-2'), PRODUCER)
    end_producer(s)
    with pytest.raises(ValueError, match='already ended'):
        D.handle(s['root'], 'public', arm_payload(s, grant, candidate, request_id='public-continuity-arm-3', obligation_id='guide'), PRODUCER)
    assert len([row for row in work(s).get('development') or () if row.get('kind') == C.INTENT]) == 2


def test_late_proof_after_producer_end_is_an_arrival_fact_and_readiness_is_derived(source):
    s = source
    grant, account, candidate = produce(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    end_producer(s)
    # actual caller Scope is admitted before any lookup; labels or a foreign project scope are not scope
    for scope in (project_scope('other', 'native'), None, 'public'):
        with pytest.raises(ValueError, match='scope'):
            C.read(s['root'], scope, 'public', 'work', {'part': 'summary'})
    view = summary(s)
    assert view['subject']['qualified_id'] == 'public::work' and view['goal']
    assert {'lifecycle', 'readiness', 'current_acceptance', 'status'} <= set(view['standing'])
    [shown] = view['completion']['intents']
    assert shown['id'] == intent['id'] and shown['readiness']['state'] == 'AWAITING_PROOF'
    assert view['next']['kind'] == 'attach-proof' and view['next']['callable'] is False and view['next']['template']
    assert view['next']['action']['payload']['slot_id'] == 'a-functional'
    assert view['execution']['accounts'][0]['commission_id'] == account['commission_id']
    assert view['basis']['token'].startswith('sha256:') and 'remaining' not in json.dumps(view['basis'])
    ledger = W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError, match='artifact'):
        D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional',
                                       'reference': {'id': 'ART-doesnotexist', 'expected_sha256': '0' * 64}}, HUMAN)
    saved, reference = proof(s)
    with pytest.raises(ValueError, match='review turn'):
        D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, REVIEWER)
    with pytest.raises(ValueError, match='declared proof slot'):
        D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'undeclared', 'reference': reference}, HUMAN)
    assert W._ledger(s['root']).read_bytes() == ledger
    arrived = D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)
    assert arrived['ok'] and arrived['reused'] is False and arrived['proof']['meaning'].startswith('Arrival')
    assert arrived['proof']['attached_origin'] == 'human'
    assert D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)['reused']
    _other, other = proof(s, 'other.json', '{"proof": "a different report"}')
    with pytest.raises(ValueError, match='immutable'):
        D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': other}, HUMAN)
    ready = completion(s, intent)
    assert ready['readiness']['state'] == 'READY' and ready['next']['kind'] == 'continue' and ready['next']['callable']
    view = summary(s)
    assert view['next']['kind'] == 'continue' and view['next']['action']['payload'] == {
        'action': 'continue', 'intent_id': intent['id'], 'expected_basis': ready['readiness']['basis']}
    # arrival recorded no review, verdict or completion
    assert not [p for p in work(s).get('phases') or () if p.get('phase') in ('review', 'synthesis')]
    assert work(s).get('status') not in ('done', 'verified')
    # changed proof bytes and changed Source both hold readiness; restoring the exact bytes restores it
    target = s['root'] / saved['path']
    original = target.read_bytes()
    target.write_bytes(original + b'\n changed after arrival')
    held = judged(s, intent)
    assert held['state'] == 'HELD' and [row['code'] for row in held['reasons']] == ['PROOF_CHANGED']
    target.write_bytes(original)
    changed = s['checkout'] / 'src/answer.py'
    before = changed.read_bytes()
    changed.write_bytes(before + b'# drift\n')
    held = judged(s, intent)
    assert held['state'] == 'HELD' and any(row['code'].startswith('SOURCE_') for row in held['reasons'])
    changed.write_bytes(before)
    assert judged(s, intent)['state'] == 'READY'
    with pytest.raises(W.WorkConflict):
        summary(s, as_of='sha256:' + '0' * 64)
    # an already recorded, uncontinued Source-scope intent of the historical plan-less shape stays HELD with the exact
    # Source review-preflight recovery; nothing grafts a later plan onto it and Continue refuses without any effect
    from laplace.work import work_delivery as WD
    old = {key: value for key, value in copy.deepcopy(C._intent(work(s), intent['id'])).items()
           if not key.startswith('_') and key not in ('ts_claimed', 'owned_changes')}
    old.update(id='CI-' + '0' * 23 + '1', request_id='public-historical-plan-less', supersedes=None)
    for key in ('source_review_plan', 'source_context', 'source_subject'):
        old['production'].pop(key, None)
    W._append(s['root'], old)
    held = judged(s, old)
    assert held['state'] == 'HELD' and 'SOURCE_REVIEW_PLAN_ABSENT' in [row['code'] for row in held['reasons']]
    recovery = next(row for row in held['reasons'] if row['code'] == 'SOURCE_REVIEW_PLAN_ABSENT')['read']
    assert recovery['payload'] == {'action': 'review-preflight', 'work_id': 'work', 'grant_id': grant['id'], 'candidate_id': candidate}
    ledger = W._ledger(s['root']).read_bytes()
    with pytest.raises(ValueError, match='HELD'):
        WD.handle(s['root'], 'public', {'action': 'continue', 'intent_id': old['id'], 'expected_basis': held['basis']}, HUMAN)
    assert W._ledger(s['root']).read_bytes() == ledger and not [p for p in work(s).get('phases') or () if p.get('phase') == 'handoff']
    assert judged(s, intent)['state'] == 'READY' and judged(s, intent)['facts']['source_review_plan'] == 'COMPLETE'
    # recorded but malformed, pin-incomplete or subject-mismatched plans are a qualified HELD with the same recovery, never a raise
    full = C._intent(work(s), intent['id'])
    for suffix, change, code in (('2', lambda p: p['source_review_plan'].update(inputs='not-a-list'), {'SOURCE_REVIEW_PLAN_INVALID', 'SOURCE_REVIEW_PLAN_INCOMPLETE'}),
                                 ('3', lambda p: p['pins'].pop('evaluator.py'), {'SOURCE_REVIEW_PLAN_INCOMPLETE'}),
                                 ('4', lambda p: p['source_subject']['stage'].update(id='another-stage'), {'SOURCE_SUBJECT_MISMATCH'}),
                                 ('5', lambda p: p['source_subject'].update(accepted_base='0' * 40), {'SOURCE_SUBJECT_MISMATCH'}),
                                 ('6', lambda p: p.update(source_review_plan='not-a-plan'), {'SOURCE_REVIEW_PLAN_INVALID'}),
                                 ('7', lambda p: p['source_subject'].update(stage='not-a-stage'), {'SOURCE_REVIEW_PLAN_INVALID'}),
                                 ('8', lambda p: p['source_review_plan']['review_subject'].update(stage='not-a-stage'),
                                  {'SOURCE_REVIEW_PLAN_INVALID', 'SOURCE_SUBJECT_UNKNOWN'}),
                                 ('9', lambda p: p['source_review_plan']['review_subject'].update(readonly_carry='not-a-carry'),
                                  {'SOURCE_REVIEW_PLAN_INVALID', 'SOURCE_SUBJECT_UNKNOWN'})):
        bad = {key: value for key, value in copy.deepcopy(full).items() if not key.startswith('_') and key not in ('ts_claimed', 'owned_changes')}
        bad.update(id='CI-' + '0' * 23 + suffix, request_id='public-historical-bad-' + suffix, supersedes=None)
        change(bad['production'])
        W._append(s['root'], bad)
        state = judged(s, bad)
        assert state['state'] == 'HELD' and code & {row['code'] for row in state['reasons']}, (suffix, state['reasons'])
        assert all(row['read']['payload']['action'] == 'review-preflight' for row in state['reasons']
                   if row['code'] in ('SOURCE_REVIEW_PLAN_INVALID', 'SOURCE_REVIEW_PLAN_INCOMPLETE', 'SOURCE_SUBJECT_MISMATCH'))
        # the actual public projection of the retained row (selected completion), not only the readiness helper
        shown = completion(s, bad)
        assert shown['readiness']['state'] == 'HELD' and shown['intent']['id'] == bad['id'] and shown['next']['kind'] == 'inspect', suffix
        assert 'immutable' in json.dumps(shown['readiness']) or suffix != '1'
    view = summary(s)   # the whole summary projection over every retained shape stays bounded
    assert view['part'] == 'summary' and view['completion']['total'] >= 9
    assert all(item['readiness']['state'] in ('HELD', 'READY', 'AWAITING_PROOF', 'CLOSED') for item in view['completion']['intents'])


def test_complete_review_template_and_pure_preflight_carry_the_actual_limits(source):
    s = source
    _grant, _account, handoff_id = _detached_setup(s)
    template = R.review_template(work(s), handoff_id, 'source', 'REVIEW-public-template')
    payload = template['payload']
    assert payload['verdict'] is None and template['author_fields'] == ['verdict', 'summary', 'findings']
    assert set(payload) == {'id', 'phase', 'request_id', 'expected_work_revision', 'handoff_id', 'obligation_id', 'verdict', 'summary', 'findings', 'pins'}
    assert set(payload['pins']) == {'src/answer.py', 'evaluator.py'}
    assert {key: template['limits'][key] for key in ('summary', 'findings', 'finding_id', 'evidence', 'pins')} == {
        'summary': 2000, 'findings': 20, 'finding_id': 80, 'evidence': 8, 'pins': 64}
    schema = template['schema']
    assert schema['additionalProperties'] is False and schema['properties']['summary']['maxLength'] == 2000
    assert schema['properties']['findings']['maxItems'] == 20 and schema['properties']['obligation_id']['pattern'] == R.LIMITS['obligation_id']
    assert 'consumes' not in schema['properties'] and 'source_basis' not in schema['properties']
    ledger = W._ledger(s['root']).read_bytes()
    unfilled = R.preflight('public', payload, s['root'])
    assert not unfilled['ok'] and unfilled['recorded'] is False and any(e['path'] == 'verdict' for e in unfilled['errors'])
    filled = {**payload, 'verdict': 'HOLD', 'summary': 'Public control summary.', 'findings': [{'id': 'F1', 'summary': 'A public finding.'}]}
    passed = R.preflight('public', filled, s['root'])
    assert passed['ok'] and passed['recorded'] is False and passed['template'] == payload
    wrong = {'summary': {**filled, 'summary': 'x' * 2001},
             'findings': {**filled, 'findings': [{'id': 'F%d' % n, 'summary': 's'} for n in range(21)]},
             'findings/0/id': {**filled, 'findings': [{'id': 'x' * 81, 'summary': 's'}]},
             'findings/0': {**filled, 'findings': [{'id': ' ', 'summary': 's'}]},
             'obligation_id': {**filled, 'obligation_id': 'x' * 49},
             'request_id': {**filled, 'request_id': 'short'},
             '(root)': {**filled, 'unknown': True},
             'pins': {**filled, 'pins': {'src/answer.py': payload['pins']['src/answer.py']}},
             'expected_work_revision': {**filled, 'expected_work_revision': 'sha256:' + '0' * 64}}
    for path, value in wrong.items():
        checked = R.preflight('public', value, s['root'])
        assert not checked['ok'] and checked['recorded'] is False and any(e['path'] == path for e in checked['errors']), (path, checked['errors'])
        assert checked['payload_bytes'] == len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())
        assert len(checked['errors']) <= 8
    assert W._ledger(s['root']).read_bytes() == ledger
    # the declared limit is the recording owner's limit: the same oversize payload is refused at admission
    with pytest.raises(ValueError):
        R.record('public', wrong['summary'], s['root'], door=REVIEWER, mode='review')
    assert W._ledger(s['root']).read_bytes() == ledger
    via = C.read(s['root'], project_scope('public', 'native'), 'public', 'work', {'part': 'preflight', 'payload': filled})
    assert via['ok'] and via['recorded'] is False and via['subject']['id'] == 'work'
    assert X.status(s['root'], _account)['state'] in ('ACTIVE', 'READY')


def test_selected_detail_issues_continuity_read_only_after_actual_scope(source):
    """A finding E1 / C entry: the selected Task detail issues the owner's continuity read for the exact namespace/id,
    only for the actual admitted caller Scope; following it reaches the same Work. Foreign, absent or promoted callers
    get no handle and no lookup."""
    from laplace.work import project_work_views as V
    from laplace.work.owner_discovery import owned_workspace
    s = source
    for scope, mode in ((project_scope('public', 'native'), 'work'), (owned_workspace('sdk'), 'human')):
        detail = V.read('public', {'view': 'detail', 'id': 'work'}, s['root'], mode=mode, native_caller=scope)
        issued = detail['continuity_read']
        assert detail['continuity_read_gap'] is None and issued == {**C.handle('public', 'work', {'part': 'summary'}), 'scope': scope.public()}
        assert issued['operation'] == 'project' and issued['payload'] == {
            'namespace': 'public', 'view': 'continuity', 'id': 'work', 'request': {'part': 'summary'}}
        assert issued['http']['url'].startswith('/work/state?') and 'view=continuity' in issued['http']['url']
        followed = V.read('public', issued['payload'], s['root'], mode=mode, native_caller=scope)
        assert followed['part'] == 'summary' and followed['next']['kind']
        assert (followed['subject']['namespace'], followed['subject']['id'], followed['subject']['qualified_id']) == ('public', 'work', 'public::work')
    for scope in (project_scope('other', 'native'), None, 'public'):
        detail = V.read('public', {'view': 'detail', 'id': 'work'}, s['root'], mode='work', native_caller=scope)
        assert detail['continuity_read'] is None and 'Scope' in detail['continuity_read_gap']
        with pytest.raises(ValueError, match='scope'):
            V.read('public', {'view': 'continuity', 'id': 'work', 'request': {'part': 'summary'}}, s['root'], mode='work', native_caller=scope)
    scope = project_scope('public', 'native')
    with pytest.raises(ValueError, match='unavailable'):
        V.read('public', {'view': 'detail', 'id': 'absent'}, s['root'], mode='work', native_caller=scope)
    with pytest.raises(ValueError, match='unavailable'):
        V.read('public', {'view': 'continuity', 'id': 'absent', 'request': {'part': 'summary'}}, s['root'], mode='work', native_caller=scope)
    # a payload namespace never promotes the caller: another namespace is refused before its lookup
    with pytest.raises(ValueError, match='scope'):
        V.read('public', {'view': 'continuity', 'namespace': 'other', 'id': 'work', 'request': {'part': 'summary'}}, s['root'], mode='work', native_caller=scope)


def test_remote_exact_producer_stop_closes_readiness_and_other_generation_markers_do_not(source):
    """A finding E2: an actual exact-turn Stop published by another controller (the shared cancel marker, with no local
    job) withdraws the armed continuation; a marker for another turn, or for another host generation of this turn, does not."""
    from laplace.work import work_delivery as WD
    from laplace.writing import child_hosts, turn_control, turn_jobs
    s = source
    grant, _account, candidate = produce(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    _saved, reference = proof(s)
    D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)
    assert judged(s, intent)['state'] == 'READY'
    turn_jobs._JOBS.pop('WT-allowance', None)   # the remote-controller branch: no in-process job for the producer
    child_hosts._begin_child_execution(s['root'], s['parent']['id'], {'state': 'RUNNING', 'turn_id': 'WT-allowance', 'project': 'public',
                                       'host': child_hosts._process_identity(), 'provider_inference_started': True, 'remote_steering': True})
    marker = child_hosts._host_path(s['root'], s['parent']['id']).with_suffix('.cancel.json')
    for foreign in ({'turn_id': 'WT-other', 'requested_at': 1.0},
                    {'turn_id': 'WT-allowance', 'host': {'pid': 1, 'created_at': 'another-generation'}, 'requested_at': 1.0}):
        child_hosts._write_host(marker, foreign)
        assert judged(s, intent)['state'] == 'READY', foreign
    stop = turn_control.interrupt_turn(s['root'], {'project': 'public', 'turn_id': 'WT-allowance'})
    assert stop['interrupted'] and child_hosts._read_host(marker)['turn_id'] == 'WT-allowance'
    closed = completion(s, intent)['readiness']
    assert closed['state'] == 'CLOSED' and 'PRODUCER_STOPPED' in [row['code'] for row in closed['reasons']]
    assert closed['facts']['producer_stopped'] is True
    with pytest.raises(ValueError, match='CLOSED'):
        WD.handle(s['root'], 'public', {'action': 'continue', 'intent_id': intent['id'], 'expected_basis': closed['basis']}, HUMAN)
    # review F5: the refused Continue durably records the observed Stop; no delivery or handoff was written
    assert C._intent(work(s), intent['id'])['state'] == 'WITHDRAWN'
    assert not [r for r in work(s).get('deliveries') or () if r.get('kind') == WD.EVENT]
    assert not [p for p in work(s).get('phases') or () if p.get('phase') == 'handoff']
    with pytest.raises(ValueError, match='already ended'):
        D.handle(s['root'], 'public', arm_payload(s, grant, candidate, request_id='public-after-remote-stop', obligation_id='guide'), PRODUCER)
    # the volatile marker is later overwritten by another turn's Stop: CLOSED does not revert
    child_hosts._write_host(marker, {'turn_id': 'WT-other', 'requested_at': 2.0})
    after = judged(s, intent)
    assert after['state'] == 'CLOSED' and 'PRODUCER_STOPPED' in [row['code'] for row in after['reasons']]
    child_hosts._finish_child_execution(s['root'], s['parent']['id'], 'WT-allowance', 'interrupted')


def test_production_after_arming_closes_the_intent_and_the_active_producer_can_supersede_it(source):
    """Review F1/F2/F7: production the grant commits after arming is never left unreviewed under a READY intent; the
    still-active producer replaces its own outgrown intent (history kept); a review-role reader is never offered Continue."""
    from laplace.work import work_delivery as WD
    s = source
    grant, _account, candidate = produce(s)
    first = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    _saved, reference = proof(s)
    D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': first['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)
    ready = completion(s, first)['readiness']
    assert ready['state'] == 'READY'
    as_reviewer = C.read(s['root'], project_scope('public', 'native'), 'public', 'work', {'part': 'summary'}, mode='review')
    assert as_reviewer['next']['kind'] == 'continue' and as_reviewer['next']['callable'] is False and 'review-role' in as_reviewer['next']['callable_reason']
    issued = summary(s)['next']
    assert issued['callable'] is True
    # the human door is the existing owner action itself: same payload plus the bound project, no new route or authority
    assert issued['action']['http'] == {'method': 'POST', 'url': '/work/delivery',
                                        'payload': {'project': 'public', **issued['action']['payload']}}
    extra = D.candidate(s['root'], 'public', {'grant_id': grant['id'], 'files': [{'path': 'src/extra.py', 'before_sha256': None, 'content': 'later = True\n'}]}, PRODUCER)
    assert D.apply(s['root'], 'public', {'candidate_id': extra['candidate_id']}, PRODUCER)['effect']['state'] == 'COMMITTED'
    advanced = completion(s, first)['readiness']
    assert advanced['state'] == 'CLOSED' and 'PRODUCTION_ADVANCED' in [row['code'] for row in advanced['reasons']]
    assert 'SOURCE_SUBJECT_CHANGED' in [row['code'] for row in advanced['reasons']]   # the armed whole subject moved too
    ledger = W._ledger(s['root']).read_bytes()
    for basis in (ready['basis'], advanced['basis']):
        with pytest.raises(ValueError):
            WD.handle(s['root'], 'public', {'action': 'continue', 'intent_id': first['id'], 'expected_basis': basis}, HUMAN)
    assert W._ledger(s['root']).read_bytes() == ledger
    with pytest.raises(ValueError, match='Cumulative'):
        D.handle(s['root'], 'public', arm_payload(s, grant, extra['candidate_id'], request_id='public-continuity-arm-2'), PRODUCER)
    pins = {**arm_payload(s, grant, candidate)['pins'], 'src/extra.py': D._pin(s['checkout'] / 'src/extra.py')}
    second = D.handle(s['root'], 'public', arm_payload(s, grant, extra['candidate_id'], request_id='public-continuity-arm-2', pins=pins), PRODUCER)['intent']
    assert second['id'] != first['id'] and len(second['production']['effects']) == 3
    assert C._intent(work(s), second['id'])['supersedes'] == first['id']
    old = completion(s, first)['readiness']
    assert old['state'] == 'CLOSED' and [row['code'] for row in old['reasons']].count('SUPERSEDED') == 1
    assert completion(s, second)['readiness']['state'] == 'AWAITING_PROOF'


def test_an_existing_review_of_the_same_bytes_prevents_a_duplicate_paid_review(source):
    """Review F3: once the obligation has a review of exactly these bytes, proof arrival does not make a second paid
    review READY; Continue refuses with no delivery."""
    from laplace.work import work_delivery as WD
    s = source
    grant, _account, candidate = produce(s)
    intent = D.handle(s['root'], 'public', arm_payload(s, grant, candidate), PRODUCER)['intent']
    _saved, reference = proof(s)
    D.handle(s['root'], 'public', {'action': 'proof', 'intent_id': intent['id'], 'slot_id': 'a-functional', 'reference': reference}, HUMAN)
    assert completion(s, intent)['readiness']['state'] == 'READY'
    handoff = R.record('public', {'id': 'work', 'phase': 'handoff', 'request_id': 'public-ordinary-review-handoff',
                                  'expected_work_revision': W._task_revision(work(s)), 'obligations': ['source'],
                                  'source_basis': {'grant_id': grant['id'], 'candidate_id': candidate}, 'pins': intent['production']['pins']},
                       s['root'], door=HUMAN)['phase']
    R.record('public', {'id': 'work', 'phase': 'review', 'request_id': 'public-ordinary-review', 'expected_work_revision': W._task_revision(work(s)),
                        'handoff_id': handoff['id'], 'obligation_id': 'source', 'verdict': 'HOLD', 'summary': 'Public control review of the same bytes.',
                        'findings': [{'id': 'F1', 'summary': 'Control finding.'}]}, s['root'], door=HUMAN)
    closed = completion(s, intent)['readiness']
    assert closed['state'] == 'CLOSED' and 'ALREADY_REVIEWED' in [row['code'] for row in closed['reasons']]
    with pytest.raises(ValueError, match='CLOSED'):
        WD.handle(s['root'], 'public', {'action': 'continue', 'intent_id': intent['id'], 'expected_basis': closed['basis']}, HUMAN)
    assert not [r for r in work(s).get('deliveries') or () if r.get('kind') == WD.EVENT]
