"""Repair1 of the Work navigation/context packet (WORK-source-state-work-repair-20261019; Sol WI-R1, WI-R2, WI-R5 owner side).

Each test reproduces one independent adverse witness or acceptance check over a synthetic tmp root, through the real
owner doors (HTTP project_work_surface, native writing_tools, direct owner calls). No real project or history is read.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

import pytest

from laplace.core.records import journal
from laplace.work import project_work as work, project_work_activity as activity, project_work_navigation as nav, project_work_review as review
from laplace.web import project_work_surface as http
from laplace.native import tools as writing_tools
from laplace.writing import child_hosts

P = 'p'
NOW = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    (tmp_path / 'contract').mkdir()
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [{'name': P, 'kind': 'general', 'project_dir': 'proj'}]}))
    (tmp_path / 'proj').mkdir();(tmp_path / 'evidence').mkdir();(tmp_path / 'src').mkdir()
    (tmp_path / 'evidence' / 'status.md').write_text('actor status read\n');(tmp_path / 'src' / 'a.py').write_text('a = 1\n')
    monkeypatch.setattr(child_hosts, 'active_child_hosts', lambda root=None: [])
    journal.bank_row('contract/talk.jsonl', {'record': 'writing-turn', 'id': 'WT-n', 'project': P, 'session_id': 'WS-n', 'mode': 'work', 'text': 'x',
                                            'provider_settings': {'provider': 'codex', 'model': 'fixture'}}, root=tmp_path)
    journal.bank_row('contract/talk.jsonl', {'record': 'writing-turn', 'id': 'WT-r', 'project': P, 'session_id': 'WS-r', 'mode': 'review', 'text': 'x',
                                            'provider_settings': {'provider': 'codex', 'model': 'fixture'}}, root=tmp_path)
    return tmp_path


def make(root, ident, **fields):
    return work.task(P, {'id': ident, 'title': ident, 'goal': 'Goal of ' + ident, **fields}, root)


def get(root, **query):
    code, _, raw = http.handle('/work/state', {'project': [P], **{k: [str(v)] for k, v in query.items()}}, 'GET', repo_root=root)
    return code, raw, json.loads(raw)


def detail(root, ident, mode='human'):
    return work.read(P, {'view': 'detail', 'id': ident}, root, mode=mode) if mode == 'human' else writing_tools.execute(
        root, P, mode, 'project', {'view': 'detail', 'id': ident}, 'WT-r' if mode == 'review' else 'WT-n')


def scope_of(root, ident):
    return work._work_basis(work._tasks(P, root), ident)[0]['scope_revision']


# ---------------------------------------------------------------------------------------------- WI-R1 one decision

def test_the_disposition_preview_and_execution_are_one_owner_decision(root, monkeypatch):
    make(root, 'A');make(root, 'B', depends_on=['A'])
    status = detail(root, 'B')['allowed_actions']['task_status']
    assert 'done' not in status['statuses'] and status['refused']['done'] == 'blocked task cannot complete'
    with pytest.raises(ValueError, match='^blocked task cannot complete$'):
        work.transition(P, {**status['payload'], 'status': 'done'}, root)
    assert status['refused']['verified'].startswith('verified requires') and 'verified' not in status['statuses']
    # one changed owner condition changes the native preparation and the execution together, with no second rule edited
    real = work.disposition_policy

    def stricter(row, effective, repo_root=None, **kw):
        value = real(row, effective, repo_root, **kw)
        refused = {**value['refused'], 'in-progress': 'Work this fixture forbids starting.'}
        return {**value, 'refused': refused, 'statuses': [x for x in value['statuses'] if x not in refused]}
    monkeypatch.setattr(work, 'disposition_policy', stricter)
    native = detail(root, 'A', mode='work')['allowed_actions']['task_status']
    assert 'in-progress' not in native['statuses'] and native['refused']['in-progress'] == 'Work this fixture forbids starting.'
    with pytest.raises(ValueError, match='forbids starting'):
        work.transition(P, {**native['payload'], 'status': 'in-progress'}, root)


def test_role_phases_and_phase_preparation_come_from_the_owner_definition(root):
    make(root, 'R', review_obligations=[{'id': 'source', 'scope': 'source', 'label': 'Source review', 'inputs': ['src/a.py']}])
    human = detail(root, 'R')['allowed_actions']['work_review']
    agent = detail(root, 'R', mode='review')['allowed_actions']['work_review']
    assert human['phases'] == review.role_phases('human') == ['handoff', 'review', 'synthesis', 'followup']
    assert agent['phases'] == review.role_phases('review') == ['review', 'followup'] == list(agent['preparation']['phases'])
    prep = human['preparation']['phases']
    assert prep['review']['refused'].startswith('No handoff is recorded') and 'handoff_id' not in prep['review']['basis']
    assert prep['synthesis']['refused'].startswith('A synthesis consumes')
    assert [i['path'] for i in prep['followup']['inputs']][:4] == ['finding', 'closure', 'child.title', 'child.goal']
    assert {tuple(o) for o in next(i for i in prep['followup']['inputs'] if i['path'] == 'closure')['options']} == set(review.CLOSURE_LABELS.items())
    assert review.PHASE_FIELDS['review'] == (('handoff_id', 'obligation_id', 'verdict'), ('findings', 'pins'))   # the schema derives from PHASE_SPEC
    with pytest.raises(ValueError, match='Review mode records scoped reviews'):
        writing_tools.execute(root, P, 'review', 'work_review', {'id': 'R', 'phase': 'handoff', 'request_id': 'req-handoff-r',
                                                                 'expected_work_revision': human['payload']['expected_work_revision'], 'object': {'aggregate': 'x'}}, 'WT-r')
    sha = 'sha256:' + hashlib.sha256(b'a = 1\n').hexdigest()
    writing_tools.execute(root, P, 'work', 'work_review', {'id': 'R', 'phase': 'handoff', 'request_id': 'req-handoff-1',
                                                           'expected_work_revision': human['payload']['expected_work_revision'], 'pins': {'src/a.py': sha}}, 'WT-n')
    after = detail(root, 'R')['allowed_actions']['work_review']['preparation']['phases']
    assert 'refused' not in after['review'] and after['review']['basis']['handoff_id'].startswith('PHASE-')
    assert after['synthesis']['basis']['consumes'] == [after['review']['basis']['handoff_id']]


def test_a_partial_followup_join_is_prepared_and_recovered_through_the_same_owner_request(root, monkeypatch):
    make(root, 'R', review_obligations=[{'id': 'source', 'scope': 'source', 'label': 'Source review', 'inputs': ['src/a.py']}])
    guard = detail(root, 'R')['allowed_actions']['work_review']['payload']['expected_work_revision']
    real = work._task

    def failing(project, payload, repo_root=None, **kw):
        if payload.get('id') == 'R':
            raise OSError('disk full')
        return real(project, payload, repo_root, **kw)
    monkeypatch.setattr(work, '_task', failing)
    request = {'id': 'R', 'phase': 'followup', 'request_id': 'req-follow-pend', 'expected_work_revision': guard,
               'finding': 'F1 pending', 'closure': 'required', 'child': {'title': 'Pending', 'goal': 'Join later'}}
    assert review.record(P, request, root, door={'origin': 'human'})['status'] == 'PENDING_JOIN'
    monkeypatch.setattr(work, '_task', real)
    for mode in ('human', 'work'):
        prepared = detail(root, 'R', mode=mode)['allowed_actions']['work_review']
        pending = prepared['preparation']['phases']['followup']['recovery']['pending']
        assert [row['recover']['request_id'] for row in pending] == ['req-follow-pend']
    recover = {**pending[0]['recover'], 'expected_work_revision': prepared['payload']['expected_work_revision']}
    assert review.record(P, recover, root, door={'origin': 'human'})['status'] == 'RECOVERED'
    assert 'recovery' not in detail(root, 'R')['allowed_actions']['work_review']['preparation']['phases']['followup']


# ---------------------------------------------------------------------------------------------- WI-R1 references

def campaigns(root):
    """Two campaign contexts with the same short code R1 under different identities, a rename, a deep chain and a follow-up."""
    make(root, 'M5', title='M5 · Writing milestone')
    make(root, 'R5', title='R5 · Repair wave five')
    make(root, 'M5-R1', title='R1 · Refuse stale guards', parent_work_id='M5')
    make(root, 'R5-R1', title='R1 · Restore page bounds', parent_work_id='R5',
         review_obligations=[{'id': 'source', 'scope': 'source', 'label': 'Source review', 'inputs': ['src/a.py']}])
    make(root, 'R5-R1', title='R1 · Restore raw page bounds', expected_work_revision=work._task_revision(work._tasks(P, root)['R5-R1']))   # renamed
    guard = detail(root, 'R5-R1')['allowed_actions']['work_review']['payload']['expected_work_revision']
    review.record(P, {'id': 'R5-R1', 'phase': 'followup', 'request_id': 'req-follow-r5', 'expected_work_revision': guard, 'finding': 'F2 CJK page',
                      'closure': 'prerequisite', 'child': {'id': 'R5-R1-F2', 'title': 'F2 · Bound CJK rows', 'goal': 'Bound'},
                      'evidence': [{'path': 'evidence/status.md', 'sha256': 'sha256:' + hashlib.sha256(b'actor status read\n').hexdigest()}]},
                  root, door={'origin': 'human'})
    parent = 'R5-R1-F2'
    for depth in range(14):
        make(root, 'D%02d' % depth, title='D%02d · deep' % depth, parent_work_id=parent);parent = 'D%02d' % depth


def test_codes_resolve_to_qualified_identity_location_history_and_recorded_followups_per_campaign(root):
    campaigns(root)
    m5, r5 = detail(root, 'M5-R1')['reference'], detail(root, 'R5-R1')['reference']
    assert m5['title'].startswith('R1 · ') and r5['title'].startswith('R1 · ') and m5['qualified_id'] != r5['qualified_id']
    assert [c['id'] for c in m5['location']['path']] == ['M5'] and [c['id'] for c in r5['location']['path']] == ['R5']
    assert r5['history']['names'] == ['R1 · Restore page bounds', 'R1 · Restore raw page bounds'] and r5['history']['specification'] >= 2
    assert m5['origin'] == {'recorded': False, 'says': m5['origin']['says']} and 'No recorded follow-up origin' in m5['origin']['says']
    assert [(f['child']['id'], f['finding'], f['closure']) for f in r5['followups']] == [('R5-R1-F2', 'F2 CJK page', 'prerequisite')]
    child = detail(root, 'R5-R1-F2')['reference']
    assert child['origin']['recorded'] and child['origin']['parent']['id'] == 'R5-R1' and child['origin']['finding'] == 'F2 CJK page'
    code, _, phase = get(root, **{k: v for k, v in child['origin']['record']['payload'].items() if k != 'namespace'})
    assert code == 200 and phase['phase']['rows'][-1]['child_id'] == 'R5-R1-F2' and phase['phase']['rows'][0]['evidence'][0]['path'] == 'evidence/status.md'
    code, _, history = get(root, view='history', id='R5-R1')
    specs = [e for e in history['entries'] if e['record'] == 'specification']
    assert [e['title'] for e in specs] == ['R1 · Restore page bounds', 'R1 · Restore raw page bounds', 'R1 · Restore raw page bounds']
    assert [e['changed'] for e in specs] == [['created'], ['title'], ['depends_on']], 'the rename and the follow-up join, each as what changed'
    assert any(e['record'] == 'review-phase' and e.get('child_id') == 'R5-R1-F2' and e['read'] for e in history['entries'])
    deep = detail(root, 'D13')['reference']['location']
    assert deep['omitted'] == 4 and deep['root']['id'] == 'R5' and len(deep['path']) == nav.BREADCRUMBS
    code, _, branch = get(root, view='branch', id='D13')
    assert branch['breadcrumbs_omitted'] == 4 and branch['breadcrumbs_root']['id'] == 'R5'
    native = writing_tools.execute(root, P, 'work', 'project', {'view': 'detail', 'id': 'R5-R1'}, 'WT-n')
    assert native['reference'] == detail(root, 'R5-R1')['reference'], 'agent and person read the same reference carrier'
    code, _, roots = get(root, view='roots')
    assert [r['id'] for r in roots['roots']] == ['M5', 'R5'], 'one owner order for every reader'


# ---------------------------------------------------------------------------------------------- WI-R2 observations

def observation(root, ident='W', **extra):
    return {'id': ident, 'request_id': 'obs-req-0001', 'subject': {'kind': 'external-actor', 'actor': 'codex', 'session_id': 'thread-1'},
            'observed_state': 'running', 'observed_at': NOW.isoformat(), 'expires_at': (NOW + dt.timedelta(seconds=10)).isoformat(),
            'consumed_scope_revision': scope_of(root, ident), 'observer': 'root', 'source': 'actor status read',
            'evidence': [{'path': 'evidence/status.md', 'sha256': 'sha256:' + hashlib.sha256(b'actor status read\n').hexdigest()}], **extra}


def post(root, payload):
    code, _, raw = http.handle('/work/observation', {}, 'POST', json.dumps({'project': P, **payload}).encode(), repo_root=root)
    return code, json.loads(raw)


def test_unmatched_scope_is_refused_and_a_later_scope_edit_makes_an_observation_historical(root):
    make(root, 'W');make(root, 'V')
    code, refused = post(root, observation(root, consumed_scope_revision='sha256:' + '0' * 64))   # Sol WI-R2 witness 1
    assert code == 409 and refused['code'] == 'CHANGED_INPUT' and refused['field'] == 'consumed_scope_revision' and refused['next_reads']
    assert activity.project_activity(P, root, now=NOW)['by_work'] == {}
    assert post(root, observation(root, ident='W', expires_at=(NOW + dt.timedelta(minutes=30)).isoformat(),
                                  consumed_scope_revision=scope_of(root, 'V')))[0] == 409, 'another Work\'s scope is not this Work\'s'
    assert post(root, observation(root, expires_at=(NOW + dt.timedelta(minutes=30)).isoformat()))[1]['status'] == 'RECORDED'
    before = nav.observe(P, {'id': 'W'}, root, now=NOW)
    assert activity.project_activity(P, root, now=NOW)['by_work']['W']['state'] == 'running'
    make(root, 'W', goal='A changed goal', expected_work_revision=work._task_revision(work._tasks(P, root)['W']))
    value = activity.project_activity(P, root, now=NOW)['by_work']['W']
    item = value['observations'][0]
    assert value['state'] == 'unknown' and item['current'] is False and item['scope']['matches'] is False
    assert item['qualification'].startswith('HISTORICAL for the current Work')
    assert 'activity' in nav.observe(P, {'id': 'W', 'since': before['token']}, root, now=NOW)['changes']
    assert detail(root, 'W')['task']['standing']['group'] == 'ready'


def test_the_same_observed_event_cannot_be_extended_or_renamed_by_a_new_request(root):
    make(root, 'W')
    stamp = lambda: work._stamp(work._ledger(root))
    first = activity.record(P, observation(root), root, door={'origin': 'human'}, now=NOW)
    assert first['status'] == 'RECORDED'
    written = stamp()
    same = activity.record(P, observation(root, request_id='obs-req-0002'), root, door={'origin': 'human'}, now=NOW)
    assert same['status'] == 'REUSED' and same['observation']['id'] == first['observation']['id'] and stamp() == written
    later = NOW + dt.timedelta(seconds=11)
    with pytest.raises(ValueError, match='cannot extend or change it'):   # Sol WI-R2 witness 2
        activity.record(P, observation(root, request_id='obs-req-0003', expires_at=(NOW + dt.timedelta(hours=1)).isoformat()),
                        root, door={'origin': 'human'}, now=later)
    with pytest.raises(ValueError, match='cannot extend or change it'):
        changed = {k: v for k, v in observation(root, request_id='obs-req-0004').items() if k != 'evidence'}
        activity.record(P, {**changed, 'evidence_absent': 'none'}, root, door={'origin': 'human'}, now=later)
    assert stamp() == written and activity.work_activity(P, 'W', root, now=later)['state'] == 'unknown'
    assert activity.record(P, observation(root), root, door={'origin': 'human'}, now=later)['status'] == 'REUSED'   # exact replay
    older = activity.record(P, observation(root, request_id='obs-req-0005', observed_at=(NOW - dt.timedelta(seconds=5)).isoformat(),
                                           expires_at=(later + dt.timedelta(minutes=5)).isoformat()), root, door={'origin': 'human'}, now=later)
    assert older['status'] == 'RECORDED' and activity.work_activity(P, 'W', root, now=later)['state'] == 'unknown', 'an older event stays history'
    genuine = activity.record(P, observation(root, request_id='obs-req-0006', observed_at=later.isoformat(),
                                             expires_at=(later + dt.timedelta(minutes=5)).isoformat()), root, door={'origin': 'human'}, now=later)
    assert genuine['status'] == 'RECORDED' and activity.work_activity(P, 'W', root, now=later)['state'] == 'running'
    terminal = activity.record(P, observation(root, request_id='obs-req-0007', observed_state='completed', observed_at=(later + dt.timedelta(seconds=1)).isoformat(),
                                              expires_at=(later + dt.timedelta(minutes=5)).isoformat()), root, door={'origin': 'human'}, now=later + dt.timedelta(seconds=1))
    assert terminal['status'] == 'RECORDED' and activity.work_activity(P, 'W', root, now=later + dt.timedelta(seconds=2))['state'] == 'completed'
    assert detail(root, 'W')['task']['status'] == 'ready', 'an external completion completes no Work'


# ---------------------------------------------------------------------------------------------- WI-R5 page bounds

def test_the_long_cjk_roots_page_stays_under_its_line_and_continues_by_whole_rows(root):
    for n in range(12):   # Sol WI-R5 witness: 12 roots, title 界x160, goal 意x200, one ready child each with title 作x160
        make(root, 'C%d' % n, title='界' * 160, goal='意' * 200)
        make(root, 'C%d-K' % n, title='作' * 160, goal='意' * 200, parent_work_id='C%d' % n)
    code, raw, page = get(root, view='roots')
    assert code == 200 and len(raw) < 30000, len(raw)
    seen, value = [row['id'] for row in page['roots']], page
    while value['pagination']['next_read']:
        query = {k: v for k, v in value['pagination']['next_read']['payload'].items() if k != 'namespace'}
        code, raw, value = get(root, **query)
        assert code == 200 and len(raw) < 30000
        seen += [row['id'] for row in value['roots']]
    assert seen == ['C%d' % n for n in range(12)], 'every root once, in owner order, as whole rows'
    row = page['roots'][0]
    assert 'title_complete' not in row and row['title'] == '界' * 160, 'a 160-character title is whole'
    assert row['purpose_complete'] is False and len(row['purpose'].encode()) <= nav.PURPOSE_BYTES
    assert detail(root, 'C0')['task']['title'] == '界' * 160 and detail(root, 'C0')['task']['goal'] == '意' * 200, 'the whole values are the detail read'
    long_id = 'W-' + 'x' * 200
    make(root, long_id, title='界' * 300, goal='意' * 2000)
    code, raw, tail = get(root, view='roots', offset=12)
    assert code == 200 and len(raw) < 30000 and tail['roots'][0]['title_complete'] is False and tail['roots'][0]['qualified_id'] == P + '::' + long_id


def test_an_unchanged_observation_returns_only_the_token(root):
    make(root, 'W')
    code, raw, first = get(root, view='observe', id='W')
    code, raw, again = get(root, view='observe', id='W', since=first['token'])
    assert again == {'project': P, 'view': 'observe', 'token': first['token'], 'changed': False}
    assert len(raw) < 128, len(raw)


def test_the_byte_bound_ends_a_page_on_a_whole_row_and_its_continuation_covers_the_rest(root):
    parent = 'P-' + 'x' * 180
    make(root, parent, title='界' * 300, goal='意' * 2000)
    for n in range(40):
        make(root, 'K-%s-%03d' % ('y' * 180, n), title='作' * 300, goal='意' * 2000, parent_work_id=parent)
    seen, query = [], {'view': 'branch', 'id': parent, 'limit': 100}
    while True:
        code, raw, value = get(root, **query)
        assert code == 200 and len(raw) <= 30000, len(raw)
        seen += [row['id'] for row in value['children']]
        if not value['pagination']['next_read']:
            break
        assert value['pagination']['bounded_by'] == 'bytes' and value['pagination']['returned'] < 100
        query = {k: v for k, v in value['pagination']['next_read']['payload'].items() if k != 'namespace'}
    assert seen == ['K-%s-%03d' % ('y' * 180, n) for n in range(40)], 'every child once, in owner order'
