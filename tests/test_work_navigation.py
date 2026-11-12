"""Recursive Work navigation, the action/context descriptor, qualified activity and the observer token.

WORK-source-state-work-review-context-20261015 (Sol D2-A/B/D/E). Synthetic roots only: every Work, turn, child host
and observation below is created inside tmp_path or injected into the in-process registries for one test.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json

import pytest

from laplace.work import project_work as work, project_work_activity as activity, project_work_navigation as nav, project_work_review as review
from laplace.web import project_work_surface as http
from laplace.native import tools as writing_tools
from laplace.writing import reads as reads_owner
from laplace.writing import child_hosts, turn_jobs

P = 'p'
NOW = dt.datetime.now(dt.timezone.utc)


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    (tmp_path / 'contract').mkdir()
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [{'name': P, 'kind': 'general', 'project_dir': 'proj'},
                                                                              {'name': 'other', 'kind': 'general', 'project_dir': 'other'}]}))
    (tmp_path / 'proj').mkdir();(tmp_path / 'other').mkdir()
    (tmp_path / 'evidence').mkdir();(tmp_path / 'evidence' / 'status.md').write_text('actor status read\n')
    monkeypatch.setattr(child_hosts, 'active_child_hosts', lambda root=None: [])
    return tmp_path


def make(root, ident, project=P, **fields):
    return work.task(project, {'id': ident, 'title': 'Title ' + ident, 'goal': 'Goal of ' + ident, **fields}, root)


def state(root, **query):
    code, _, raw = http.handle('/work/state', {'project': [P], **{k: [str(v)] for k, v in query.items()}}, 'GET', repo_root=root)
    assert code == 200, raw[:400]
    return json.loads(raw)


def legacy(root, ident, **fields):
    """A historical specification row the guarded editor would refuse today (a prerequisite cycle or a missing
    prerequisite): appended raw, as older ledgers contain them."""
    spec = {key: value for key, value in work._tasks(P, root)[ident].items() if key != 'phases'}
    work._append(root, {**spec, **fields, 'record': 'project-work', 'id': ident, 'task_id': ident})


def follow(root, read):
    """Follow an owner-issued next_read through the HTTP door exactly as a client would."""
    from urllib.parse import urlsplit, parse_qs
    url = urlsplit(read['http']['url'])
    code, _, raw = http.handle(url.path, parse_qs(url.query), 'GET', repo_root=root)
    return code, json.loads(raw)


def done(root, ident, path):
    (root / path).write_text('result of ' + ident)
    guards = work.read(P, {'view': 'detail', 'id': ident}, root)['allowed_actions']['task_status']['payload']
    return work.transition(P, {**guards, 'status': 'done', 'evidence': [path]}, root)


def tree(root):
    """campaign C > branch B > nine tasks (sibling prerequisites, one cycle pair), plus 14 unfiled roots."""
    make(root, 'C');make(root, 'B', parent_work_id='C')
    for n in range(9):
        make(root, 'T%d' % n, parent_work_id='B')
    make(root, 'T1', parent_work_id='B', depends_on=['T5'], expected_work_revision=work._task_revision(work._tasks(P, root)['T1']))
    legacy(root, 'T7', depends_on=['T8']);legacy(root, 'T8', depends_on=['T7'])
    for n in range(14):
        make(root, 'U%02d' % n)


# ---------------------------------------------------------------------------------------------- navigation

def test_roots_page_every_root_with_complete_rollups_and_a_working_continuation(root):
    tree(root)
    first = state(root, view='roots')
    assert first['counts']['roots'] == 15 and first['counts']['campaigns'] == 1 and first['counts']['unfiled'] == 14
    assert [row['id'] for row in first['roots']][:2] == ['C', 'U00'] and len(first['roots']) == nav.NAV_PAGE
    campaign = first['roots'][0]
    assert campaign['grade'] == 'campaign' and campaign['rollup']['descendants'] == 10   # B and its nine tasks: not a page
    reads = first['row_reads']   # one owner read per row kind; inspect (detail) and open (branch) stay separate reads
    assert reads['detail']['payload'] == {'namespace': P, 'view': 'detail'} and reads['branch']['payload'] == {'namespace': P, 'view': 'branch'}
    assert 'read_handle' not in campaign and 'branch_read' not in campaign and campaign['qualified_id'] == P + '::C'
    code, rest = follow(root, first['pagination']['next_read'])
    assert code == 200 and [row['id'] for row in rest['roots']] == ['U11', 'U12', 'U13'] and rest['pagination']['next_read'] is None
    seen = [row['id'] for row in first['roots'] + rest['roots']]
    assert len(seen) == len(set(seen)) == 15
    make(root, 'U99')   # the cut moves: an old continuation is refused with exact next reads, never mixed
    code, refused = follow(root, first['pagination']['next_read'])
    assert code == 409 and refused['code'] == 'CHANGED_INPUT' and refused['next_reads']


def test_branch_orders_the_complete_sibling_set_names_cycles_and_qualifies_parallel_narrowly(root):
    tree(root)
    page = state(root, view='branch', id='B', limit=6)
    assert [crumb['id'] for crumb in page['breadcrumbs']] == ['C'] and page['node']['grade'] == 'branch'
    ids = [row['id'] for row in page['children']]
    assert ids.index('T5') < ids.index('T1')                     # a sibling prerequisite comes first
    assert page['order']['cyclic'] == ['T7', 'T8'] and page['pagination']['total'] == 9
    by_id = {row['id']: row for row in page['children']}
    assert by_id['T1']['needs'] == {'siblings': ['T5'], 'outside': 0, 'open': 1, 'needed_by_siblings': 0}
    assert 'parallel' not in by_id['T1'] and by_id['T0']['parallel']['code'] == 'no-open-prerequisite'
    assert 'not assessed' in page['parallel_says']
    code, rest = follow(root, page['pagination']['next_read'])
    assert code == 200 and len(rest['children']) == 3
    tail = {row['id']: row for row in rest['children']}
    assert set(tail) == {'T6', 'T7', 'T8'} and 'parallel' not in tail['T7'] and 'parallel' not in tail['T8']
    assert {row['id'] for row in page['children'] + rest['children']} == {'T%d' % n for n in range(9)}


def test_every_grade_is_inspectable_work_with_one_descriptor_shape(root):
    tree(root)
    grades = {}
    for ident in ('C', 'B', 'T0'):
        detail = state(root, view='detail', id=ident)
        context = detail['action_context']
        grades[ident] = context['grade']
        assert context['target']['id'] == ident and context['target']['work_revision'] == detail['task']['work_revision']
        assert {action['operation'] for action in context['actions']} >= {'task', 'task_status'}
        task_status = next(action for action in context['actions'] if action['operation'] == 'task_status')
        assert task_status['consumes'] == ['expected_dependency_revision', 'expected_work_scope_revision', 'expected_work_status_revision']
        carried = detail['allowed_actions'][task_status['name']]   # the one carrier the descriptor names
        assert set(task_status['consumes']) <= set(carried['payload']) and carried['effects'] and carried['recovery']['reads'][0]['payload']['id'] == ident
        assert context['observation']['http'] == {'method': 'POST', 'url': '/work/observation'}
        assert ('summary' in context) == (ident != 'T0')
    assert grades == {'C': 'campaign', 'B': 'branch', 'T0': 'task'}
    branch = state(root, view='branch', id='C')
    assert branch['node']['action_context']['relationships']['contains']['total'] == 1


def test_done_with_non_current_acceptance_stays_in_attention_never_settled(root):
    make(root, 'C');make(root, 'A', parent_work_id='C');make(root, 'S', parent_work_id='C')
    done(root, 'A', 'a.txt');done(root, 'S', 's.txt')
    (root / 'a.txt').write_text('changed after completion')
    roots = state(root, view='roots')
    assert [item['id'] for item in roots['attention']['items']] == ['A'] and roots['attention']['items'][0]['path'][0]['id'] == 'C'
    rollup = roots['roots'][0]['rollup']
    assert rollup['groups'] == {'attention': 1, 'settled': 1} and rollup['attention'] == 1 and rollup['first_attention'] == ['A']
    assert state(root, view='detail', id='A')['task']['standing']['facts'][0]['code'] == 'done-review-required'
    assert state(root, view='detail', id='S')['task']['standing']['group'] == 'settled'


# ---------------------------------------------------------------------------------------------- one group at every depth (wave 8)

def _mixed(root):
    """The tree plus every kind of standing at depth: done (settled), done with a changed basis (attention), declared
    in progress, waiting on a prerequisite, and ready subtasks three levels down."""
    tree(root)
    make(root, 'D', parent_work_id='T0');make(root, 'E', parent_work_id='D');make(root, 'F', parent_work_id='E')
    done(root, 'T2', 't2.txt');done(root, 'U03', 'u3.txt');done(root, 'E', 'e.txt');(root / 'e.txt').write_text('changed after completion')
    guards = work.read(P, {'view': 'detail', 'id': 'U04'}, root)['allowed_actions']['task_status']['payload']
    work.transition(P, {**guards, 'status': 'in-progress'}, root)


def _all_pages(root, **query):
    first = state(root, **query);rows = list(first['tasks']);page = first
    while page['pagination']['next_read']:
        code, page = follow(root, page['pagination']['next_read']);assert code == 200, page
        assert page['read_cut'] == first['read_cut'] and page['group'] == first['group']
        rows += page['tasks']
    return first, rows


def test_every_group_lists_exactly_the_work_standing_puts_in_it_at_any_depth_and_the_counts_add_up(root):
    _mixed(root)
    roots = state(root, view='roots')
    every = {ident: state(root, view='detail', id=ident)['task']['standing']['group'] for ident in work._tasks(P, root)}
    counts = roots['counts']['groups']
    assert sum(counts.values()) == roots['counts']['work'] == len(every)
    assert all(counts.values()) and set(counts) <= set(nav.GROUPS)
    assert counts.get('attention', 0) == roots['counts']['attention']
    seen = []
    for group in nav.GROUPS:
        first, rows = _all_pages(root, view='group', group=group, limit=4)
        listed = [row['id'] for row in rows]
        assert sorted(listed) == sorted(ident for ident, value in every.items() if value == group), group
        assert first['pagination']['total'] == counts.get(group, 0) == len(listed) == len(set(listed))
        assert all(row['standing']['group'] == group for row in rows)
        seen += listed
    assert sorted(seen) == sorted(every)
    ready = {row['id']: row for row in _all_pages(root, view='group', group='ready')[1]}
    assert 'F' in ready and [step['id'] for step in ready['F']['path']] == ['T0', 'D', 'E'] and ready['F']['path_omitted'] == 2
    assert {'T2', 'U03'} <= {row['id'] for row in _all_pages(root, view='group', group='settled')[1]}
    assert 'E' in {row['id'] for row in _all_pages(root, view='group', group='attention')[1]}


def test_the_group_read_pages_like_attention_inside_the_line_and_refuses_a_moved_cut(root):
    _mixed(root)
    first = state(root, view='group', group='ready', limit=5)
    assert first['view'] == 'group' and first['group'] == 'ready' and set(first) == {'project', 'view', 'group', 'read_cut', 'row_reads', 'scope', 'tasks', 'pagination'}
    attention = state(root, view='attention')
    assert set(first) - {'group'} == set(attention) and first['row_reads'] == attention['row_reads']
    page = first['pagination']
    assert page['limit'] == 5 and page['returned'] == 5 and page['next_offset'] == 5 and page['bounded_by'] == 'limit'
    assert page['next_read']['payload'] == {'namespace': P, 'view': 'group', 'group': 'ready', 'offset': 5, 'limit': 5, 'as_of': first['read_cut']['revision']}
    default = state(root, view='group', group='ready')
    assert default['pagination']['limit'] == nav.NAV_PAGE
    same = state(root, view='group', group='attention')
    assert [row['id'] for row in same['tasks']] == [row['id'] for row in attention['tasks']] and same['tasks'] == attention['tasks']
    goal = '目標：再現可能な数値結果と独立した査読を伴う完成条件。' * 20
    for n in range(80):
        make(root, 'W%02d' % n, parent_work_id='U05', title='研究課題 %d：量子系の可観測量と散逸' % n, goal=goal)
    code, _, raw = http.handle('/work/state', {'project': [P], 'view': ['group'], 'group': ['ready'], 'limit': ['100']}, 'GET', repo_root=root)
    assert code == 200 and len(raw) <= nav.CAP
    value = json.loads(raw)
    assert value['pagination']['bounded_by'] == 'bytes' and value['pagination']['next_read']
    make(root, 'U98')
    code, refused = follow(root, first['pagination']['next_read'])
    assert code == 409 and refused['code'] == 'CHANGED_INPUT' and refused['next_reads']


def test_group_belongs_to_view_group_only(root):
    tree(root)
    for query in ({'view': 'group'}, {'view': 'roots', 'group': 'ready'}, {'view': 'attention', 'group': 'attention'},
                  {'group': 'ready'}, {'view': 'group', 'group': 'unknown'}):
        code, _, raw = http.handle('/work/state', {'project': [P], **{k: [v] for k, v in query.items()}}, 'GET', repo_root=root)
        assert code == 422 and 'does not match its owner contract' in json.loads(raw)['error'], (query, raw[:200])
    from laplace import sdk
    assert sdk.work_read({'view': 'group', 'namespace': P, 'group': 'ready'}, root=root)['group'] == 'ready'


def test_the_attention_view_and_preview_keep_their_bytes(root, monkeypatch):
    """The attention view (and the roots preview it feeds) is composed exactly as before the group read: the base
    composition, written out literally here, gives the same bytes on the same ledger."""
    _mixed(root)

    def base_attention_page(index, project, cut, offset, limit, *, budget=None, wrap=None):
        ids = [ident for ident in index.by_id if index.standing(ident)['group'] == 'attention']
        return nav._compose(ids, offset, limit, lambda ident: nav._attention_row(index, ident, project),
                            wrap or (lambda rows, page: {**page, 'items': rows}), project, {'view': 'attention'}, cut, budget or nav.line(),
                            part='attention-preview' if wrap is None else 'page')

    def raw(**query):
        code, _, body = http.handle('/work/state', {'project': [P], **{k: [str(v)] for k, v in query.items()}}, 'GET', repo_root=root)
        assert code == 200
        return body
    now = [raw(view='attention'), raw(view='attention', limit=1), raw(view='roots')]
    monkeypatch.setattr(nav, 'attention_page', base_attention_page)
    base = [raw(view='attention'), raw(view='attention', limit=1), raw(view='roots')]
    assert now == base
    assert json.loads(now[0])['tasks'] and json.loads(now[1])['pagination']['next_read']


def test_relations_cover_needs_affects_and_contains_with_more_than_six_neighbours(root):
    make(root, 'hub')
    for n in range(8):
        make(root, 'need%d' % n);make(root, 'kid%d' % n, parent_work_id='hub');make(root, 'dep%d' % n, depends_on=['hub'])
    legacy(root, 'hub', depends_on=['need%d' % n for n in range(8)] + ['missing'])
    first = state(root, view='detail', id='hub', limit=6)
    assert first['requires']['total'] == 9 and first['children']['total'] == 8 and first['dependants']['total'] == 8
    assert all('standing' in row for row in first['requires']['items'] + first['children']['items'] + first['dependants']['items'])
    code, rest = follow(root, first['requires']['next_read'])
    assert code == 200
    assert [row['id'] for row in first['requires']['items'] + rest['requires']['items']][-1] == 'missing'
    assert rest['requires']['items'][-1]['available'] is False
    relations = first['action_context']['relationships']
    assert relations['needs'] == {**relations['needs'], 'total': 9, 'open': 9} and relations['affects']['total'] == 8


# ---------------------------------------------------------------------------------------------- composition

def test_the_followup_composition_names_exactly_the_primitives_the_owner_runs(root):
    (root / 'src').mkdir();(root / 'src' / 'a.py').write_text('a = 1\n')
    work.task(P, {'id': 'parent', 'title': 'Lifecycle', 'goal': 'Ship', 'review_obligations': [
        {'id': 'source', 'scope': 'source', 'label': 'Source review', 'inputs': ['src/a.py']}]}, root)
    composition = review.followup_composition()   # stated before the primitives are wrapped for tracing
    trace, depth = [], [0]

    def traced(patch, owner, name):
        original = getattr(owner, name)

        def call(*args, **kwargs):
            if depth[0] == 0:
                trace.append(original.__module__.rsplit('.', 1)[-1] + '.' + original.__qualname__)
            depth[0] += 1
            try:
                return original(*args, **kwargs)
            finally:
                depth[0] -= 1
        patch.setattr(owner, name, call)
    with pytest.MonkeyPatch.context() as patch:
        for owner, name in ((work, '_append'), (work, '_task'), (review, '_join'), (review, '_refuse_drift')):
            traced(patch, owner, name)
        guard = work._task_revision(work._tasks(P, root)['parent'])
        result = review.record(P, {'id': 'parent', 'phase': 'followup', 'request_id': 'req-follow-1', 'expected_work_revision': guard,
                                   'finding': 'F1', 'closure': 'prerequisite', 'child': {'title': 'Fix', 'goal': 'Fix F1'}}, root,
                               door={'origin': 'human'})
    assert result['status'] == 'JOINED'
    assert trace == [step['primitive'] for step in composition['steps']]
    detail = state(root, view='detail', id='parent')
    named = next(action for action in detail['action_context']['actions'] if action['operation'] == 'work_review')
    carried = detail['allowed_actions'][named['name']]
    assert named['consumes'] == ['expected_work_revision']
    assert carried['preparation']['phases']['followup']['composition'] == composition
    assert carried['preparation']['phases']['followup']['basis'] == {'expected_work_revision': work._task_revision(work._tasks(P, root)['parent'])}


# ---------------------------------------------------------------------------------------------- activity

def observation(**extra):
    return {'id': 'W', 'request_id': 'obs-req-0001', 'subject': {'kind': 'external-actor', 'actor': 'codex', 'session_id': 'thread-1'},
            'observed_state': 'running', 'observed_at': NOW.isoformat(), 'expires_at': (NOW + dt.timedelta(minutes=15)).isoformat(),
            'consumed_scope_revision': 'CURRENT', 'observer': 'root-coordinator', 'source': 'actor status read',
            'evidence': [{'path': 'evidence/status.md', 'sha256': 'sha256:' + hashlib.sha256(b'actor status read\n').hexdigest()}], **extra}


def _unminted(actions):
    """allowed_actions with the planning action's minted client request id replaced by one placeholder. backlog.action mints
    a new PLAN- request id on every read (the idempotency key of a next submission, never a guard or a basis), so two reads
    differ there by construction; every guard, basis, field and handle is still compared exactly."""
    rid = (((actions.get('planning') or {}).get('payload')) or {}).get('request_id')
    return json.loads(json.dumps(actions).replace(rid, 'PLAN-minted')) if rid else actions


def scope_of(root, ident):
    return work._work_basis(work._tasks(P, root), ident)[0]['scope_revision']


def post_observation(root, payload):
    if payload.get('consumed_scope_revision') == 'CURRENT':   # the Work's actual current scope, read from its owner
        payload = {**payload, 'consumed_scope_revision': scope_of(root, payload['id'])}
    code, _, raw = http.handle('/work/observation', {}, 'POST', json.dumps({'project': P, **payload}).encode(), repo_root=root)
    return code, json.loads(raw)


def test_external_observations_are_attested_bounded_replayed_once_and_complete_nothing(root):
    make(root, 'W')
    before = state(root, view='detail', id='W')
    code, recorded = post_observation(root, observation())
    assert code == 200 and recorded['status'] == 'RECORDED' and recorded['activity']['state'] == 'running'
    assert recorded['observation']['attestation'] == {'door': 'human', 'by': 'author'}
    assert post_observation(root, observation())[1]['status'] == 'REUSED'
    code, refused = post_observation(root, observation(summary='different'))
    assert code == 422 and 'different observation' in refused['error']
    assert post_observation(root, observation(request_id='obs-req-0002', observed_at=(NOW + dt.timedelta(minutes=10)).isoformat(),
                                              expires_at=(NOW + dt.timedelta(minutes=20)).isoformat()))[0] == 422   # future
    assert post_observation(root, observation(request_id='obs-req-0003', expires_at=(NOW + dt.timedelta(hours=7)).isoformat()))[0] == 422
    assert post_observation(root, {**{k: v for k, v in observation(request_id='obs-req-0004').items() if k != 'evidence'}})[0] == 422
    with pytest.raises(ValueError, match='human door'):
        activity.record(P, observation(request_id='obs-req-0005'), root, door={'origin': 'native', 'turn_id': 'WT-x'})
    assert 'work_observation' not in reads_owner.READS | reads_owner.WRITES   # no native write exists
    after = state(root, view='detail', id='W')
    assert after['read_cut']['revision'] == before['read_cut']['revision']        # not a Work record: no cut, guard or intent moves
    assert _unminted(after['allowed_actions']) == _unminted(before['allowed_actions'])   # only a new planning request id
    assert after['task']['standing']['group'] == 'active' and after['task']['activity']['observations'][0]['source'] == 'external'
    post_observation(root, observation(request_id='obs-req-0006', observed_state='completed',
                                       observed_at=(NOW + dt.timedelta(seconds=30)).isoformat()))
    finished = state(root, view='detail', id='W')['task']
    assert finished['status'] == 'ready' and finished['activity']['state'] == 'completed'
    assert finished['standing']['group'] == 'ready' and finished['standing']['facts'][0]['code'] == 'observed-completed'


def test_expiry_gives_unknown_and_an_older_event_never_renews_a_newer_basis(root):
    make(root, 'W')
    post_observation(root, observation(observed_state='waiting', observed_at=(NOW + dt.timedelta(seconds=60)).isoformat()))
    post_observation(root, observation(request_id='obs-req-late', observed_state='running',
                                       observed_at=(NOW - dt.timedelta(minutes=5)).isoformat()))   # arrives later, older
    current = activity.project_activity(P, root, now=NOW + dt.timedelta(minutes=2))['by_work']['W']
    assert current['state'] == 'waiting' and current['subjects_total'] == 1
    later = activity.project_activity(P, root, now=NOW + dt.timedelta(minutes=30))['by_work']['W']
    assert later['state'] == 'unknown' and later['observations'][0]['observed_state'] == 'waiting'   # last observation inspectable
    assert 'UNKNOWN now' in later['qualification']
    stamp = work._stamp(work._ledger(root))
    early = nav.observe(P, {'id': 'W'}, root, now=NOW + dt.timedelta(minutes=2))
    late = nav.observe(P, {'id': 'W', 'since': early['token']}, root, now=NOW + dt.timedelta(minutes=30))
    assert late['changes'] == ['activity'] and work._stamp(work._ledger(root)) == stamp   # expiry moved the token, nothing was written


def test_in_app_states_stay_distinct_and_partial_coverage_is_named(root, monkeypatch):
    for ident in ('A', 'B', 'C', 'D'):
        make(root, ident)
    monkeypatch.setitem(turn_jobs._STARTING_TURNS, 'tok', {'project': P, 'session_id': 'WS-1', 'work_id': 'A', 'label': 'x', 'provider': None})
    monkeypatch.setitem(turn_jobs._JOBS, 'WT-2', {'id': 'WT-2', 'project': P, 'session_id': 'WS-2', 'work_id': 'B', 'done': False})
    monkeypatch.setitem(turn_jobs._JOBS, 'WT-3', {'id': 'WT-3', 'project': P, 'session_id': 'WS-3', 'done': False})   # no Work target
    monkeypatch.setitem(turn_jobs._JOBS, 'WT-4', {'id': 'WT-4', 'project': 'other', 'session_id': 'WS-4', 'work_id': 'C', 'done': False})
    monkeypatch.setattr(child_hosts, 'active_child_hosts', lambda root=None: [
        {'project': P, 'session_id': 'WS-5', 'turn_id': 'WT-5', 'work_id': 'C', 'state': 'WAITING', 'dispatch_id': 'D1'},
        {'project': P, 'session_id': 'WS-6', 'turn_id': 'WT-6', 'work_id': 'D', 'state': 'ORPHANED'}])
    value = activity.project_activity(P, root)
    states = {ident: value['by_work'][ident]['state'] for ident in value['by_work']}
    assert states == {'A': 'starting', 'B': 'running', 'C': 'waiting', 'D': 'unknown'}
    assert value['coverage']['in_app']['untargeted'] == 1 and not value['coverage']['partial']
    groups = {row['id']: row['standing']['group'] for row in state(root, view='roots')['roots']}
    assert groups == {'A': 'active', 'B': 'active', 'C': 'active', 'D': 'ready'}
    bounded = activity.project_activity(P, root, in_app={**turn_jobs.work_activity(P, root, limit=2)})
    assert bounded['coverage']['partial'] and bounded['coverage']['in_app']['omitted'] == 2
    rows, _ = turn_jobs.active_work_projection()
    assert {row['work_id'] for row in rows if row['kind'] == 'turn' and row['project'] == P} == {'B', None, 'C', 'D'}


# ---------------------------------------------------------------------------------------------- token

def test_token_is_project_and_selection_scoped_and_idle_reads_write_nothing(root):
    make(root, 'A');make(root, 'B');make(root, 'X', project='other')
    first = state(root, view='observe', id='A')
    assert first['changed'] is None and first['token'].startswith('wo1.') and set(first['reads']) == {'catalogue', 'selected'}
    ledger = work._ledger(root);size = ledger.stat().st_size
    again = state(root, view='observe', id='A', since=first['token'])
    assert again['token'] == first['token'] and again['changed'] is False and ledger.stat().st_size == size
    make(root, 'Y', project='other')                                            # the ledger stat changed, this project did not
    unrelated = state(root, view='observe', id='A', since=first['token'])
    assert unrelated['token'] == first['token'] and unrelated['changed'] is False
    make(root, 'B', title='Renamed', expected_work_revision=work._task_revision(work._tasks(P, root)['B']))
    other_work = state(root, view='observe', id='A', since=first['token'])
    assert other_work['changes'] == ['records']                                  # the selected Work is unchanged
    make(root, 'A', title='Renamed', expected_work_revision=work._task_revision(work._tasks(P, root)['A']))
    selected = state(root, view='observe', id='A', since=other_work['token'])
    assert selected['changes'] == ['records', 'selected']
    assert state(root, view='observe', since='opaque-old')['changes'] == 'may-have-changed'
    code, _, raw = http.handle('/work/state', {'project': [P], 'view': ['roots'], 'since': ['x']}, 'GET', repo_root=root)
    assert code == 422


def test_native_and_http_share_the_navigation_reads(root):
    tree(root)
    journal_turn = {'record': 'writing-turn', 'id': 'WT-n', 'project': P, 'session_id': 'WS-n', 'mode': 'work', 'text': 'fixture'}
    from laplace.core.records import journal
    journal.bank_row('contract/talk.jsonl', journal_turn, root=root)
    for query in ({'view': 'roots'}, {'view': 'branch', 'id': 'B'}, {'view': 'attention'}, {'view': 'group', 'group': 'ready'}, {'view': 'observe', 'id': 'B'}):
        native = writing_tools.execute(root, P, 'work', 'project', dict(query), 'WT-n')
        served = state(root, **query)
        native.pop('review_read', None);native.pop('read_receipt', None)
        if query['view'] == 'observe':
            assert native['token'] == served['token']
        else:
            assert json.loads(json.dumps(native, default=str)) == {**served, **({'activity': native['activity']} if 'activity' in served else {})}


def test_navigation_pages_and_the_observer_stay_inside_their_byte_lines(root):
    """NAV rows carry purpose (at most 200 characters), standing and a complete rollup, so they are not LIST rows (1.3 KB);
    a navigation page keeps the summary page line (30,000 B, UTF-8) and the observer read stays small, measured on CJK."""
    goal = '目標：再現可能な数値結果と独立した査読を伴う完成条件。' * 20
    for n in range(14):
        make(root, 'R%02d' % n, title='研究課題 %d：量子系の可観測量と散逸' % n, goal=goal)
        for m in range(3):
            make(root, 'R%02dK%d' % (n, m), parent_work_id='R%02d' % n, goal=goal)
    for query in ({'view': 'roots'}, {'view': 'branch', 'id': 'R03'}):
        code, _, raw = http.handle('/work/state', {'project': [P], **{k: [v] for k, v in query.items()}}, 'GET', repo_root=root)
        assert code == 200 and len(raw) < 30000, (query, len(raw))
        assert all(len(row['purpose'].encode()) <= nav.PURPOSE_BYTES for row in json.loads(raw).get('roots') or json.loads(raw)['children'])
    code, _, raw = http.handle('/work/state', {'project': [P], 'view': ['observe'], 'id': ['R03']}, 'GET', repo_root=root)
    assert code == 200 and len(raw) < 2000


# ---------------------------------------------------------------------------------------------- over the retention cap

def _basis_token(detail):
    """The observer token the exact detail read consumed (its observe_basis)."""
    basis = detail['observe_basis']
    return '.'.join([nav.TOKEN_VERSION, basis['records'], basis['selected'], basis['activity']])


def _secondary(root):
    """What the navigation token memo and the activity cache hold for this fixture's ledger."""
    ledger = work._ledger(root)
    return {'token': sorted(project for path, project in nav._TOKEN_CACHE if path == str(ledger)), 'activity': ledger in activity._CACHE}


def _doors(root, ident):
    """Detail and observe through the HTTP door, the native project read and the SDK work_read of the issued handle."""
    from laplace import sdk
    from laplace.work import project_work_views as views
    detail = state(root, view='detail', id=ident)
    served = state(root, view='observe', id=ident)
    native = writing_tools.execute(root, P, 'work', 'project', {'view': 'observe', 'id': ident}, 'WT-n')
    local = sdk.work_read(views.handle(P, {'view': 'observe', 'id': ident})['payload'], root=root)
    return detail, served, native, local


def _devsrc(root):
    """The existing tiny scratch Source checkout (tests/test_development_source_recipient.py _commit/_checkout, lines 90-112):
    one commit through dulwich's repository API with its shell hooks cleared (no git or hook process), registered as devsrc."""
    from dulwich.repo import Repo
    devsrc = root / 'devsrc'
    (devsrc / 'src').mkdir(parents=True)
    (devsrc / 'src' / 'a.py').write_text('def answer():\n    return 41\n')
    (devsrc / 'README.md').write_text('fixture checkout\n')
    repo = Repo.init(str(devsrc))
    repo.hooks.clear()
    worktree = repo.get_worktree()
    worktree.stage([b'src/a.py', b'README.md'])
    worktree.commit(b'base', committer=b'fixture <fixture@example.invalid>', author=b'fixture <fixture@example.invalid>', no_verify=True)
    repo.close()
    (root / 'profiles').mkdir(exist_ok=True)
    (root / 'profiles' / 'writing_sources.json').write_text(json.dumps({'repositories': {'devsrc': 'devsrc'}}))
    return devsrc


def test_observe_reuses_the_captured_fold_cold_warm_evicted_and_over_the_retention_cap(root, monkeypatch):
    """A ledger the owner deliberately does not retain (a fixture-only lower cap over a tiny valid ledger) is still read
    whole: observe agrees with the exact detail basis through HTTP, native and SDK, an idle repeat is unchanged, guarded
    planning, a recipient binding and the actual Source grant row move the right components, external activity stays qualified until its
    observed expiry, reads write no Work row, and neither secondary cache keeps anything for that ledger."""
    from laplace.core.records import journal
    from laplace.work import backlog, work_delivery
    make(root, 'A');make(root, 'B');make(root, 'X', project='other')
    journal.bank_row('contract/talk.jsonl', {'record': 'writing-turn', 'id': 'WT-n', 'project': P, 'session_id': 'WS-n', 'mode': 'work',
                                             'text': 'fixture'}, root=root)
    assert post_observation(root, observation(id='A'))[0] == 200
    ledger = work._ledger(root)

    def agree(label):
        stamp = work._stamp(ledger)
        detail, served, native, local = _doors(root, 'A')
        token = _basis_token(detail)
        assert served['token'] == native['token'] == local['token'] == token, label
        assert token.split('.')[2] != 'absent' and served['reads']['selected']['payload']['id'] == 'A', label
        selected = served['activity']['selected']
        assert selected['state'] == 'running' and selected['source'] == 'external', label
        assert selected['qualification'].startswith('External running'), label        # qualified, never HISTORICAL
        seen = detail['task']['activity']['observations'][0]
        assert seen['current'] is True and seen['scope']['matches'] is True, label
        again = state(root, view='observe', id='A', since=token)
        assert again == {'project': P, 'view': 'observe', 'token': token, 'changed': False,
                         'expires_next_at': served['expires_next_at']}, label
        assert work._stamp(ledger) == stamp, label                                    # reads wrote no Work row
        return token

    warm = agree('warm')
    assert work.fold_cache_state(root) is not None and _secondary(root) == {'token': [P], 'activity': True}   # normal caching kept
    assert agree('warm repeat') == warm
    work._FOLD_CACHE.pop(ledger, None);nav._TOKEN_CACHE.pop((str(ledger), P), None);activity._CACHE.pop(ledger, None)   # cold
    assert agree('cold') == warm
    second = root / 'second' / 'corpus_friction';second.mkdir(parents=True)
    (second / 'work_orders.jsonl').write_text(ledger.read_text(encoding='utf8').split('\n', 1)[0] + '\n', encoding='utf8')
    monkeypatch.setattr(work, 'FOLD_CACHE_MAX_ENTRIES', 1)
    work._fold(root / 'second')                                                       # another ledger takes the only slot
    assert work.fold_cache_state(root) is None
    assert agree('evicted') == warm

    monkeypatch.setattr(work, 'FOLD_CACHE_MAX_LEDGER_BYTES', 64)                     # fixture-only: this ledger is over the cap
    assert ledger.stat().st_size > work.FOLD_CACHE_MAX_LEDGER_BYTES
    plan = backlog.inspect_planning(P, 'B', root)['actions']['planning']['payload']
    planned = backlog.change(P, {**plan, 'planning': {**plan['planning'], 'priority': 7}}, root)
    assert planned['effect'] == 'RECORDED' and work.fold_cache_state(root) is None   # served, never retained
    over = agree('over the cap')
    assert over.split('.')[1] != warm.split('.')[1] and over.split('.')[2:] == warm.split('.')[2:]   # a sibling's plan: records only
    assert work.fold_cache_state(root) is None and _secondary(root) == {'token': [], 'activity': False}
    assert agree('over the cap, repeat') == over

    guard = work._task_revision(work._tasks(P, root)['A'])
    bound = work_delivery.bind(root, P, {'action': 'bind', 'work_id': 'A', 'expected_work_revision': guard, 'kind': 'app-owned',
                                         'provider': 'claude', 'model': 'haiku', 'effort': 'low'}, {'origin': 'human'})
    assert bound['ok'] and work.fold_cache_state(root) is None                      # an attached carrier row of the selected Work
    carried = agree('over the cap after a carrier row')
    assert carried.split('.')[1] != over.split('.')[1] and carried.split('.')[2] != over.split('.')[2]
    assert carried.split('.')[3] == over.split('.')[3]                               # scope and activity unchanged

    from laplace.work import development_source
    from laplace.writing import turn_admission
    _devsrc(root)
    author = turn_admission.new_session(root, P, 'claude', 'opus', 'high')              # author session metadata only, no turn
    assert not any(job.get('session_id') == author['id'] for job in turn_jobs._JOBS.values())
    assert agree('over the cap after the author session') == carried                   # not a Work row
    issued = development_source.grant(root, P, {
        'action': 'grant', 'request_id': 'grant-observer-1', 'work_id': 'A', 'expected_work_revision': work._task_revision(work._tasks(P, root)['A']),
        'repository': 'devsrc', 'paths': ['src/*.py'], 'operations': ['read'], 'lifetime_s': 600,
        'parent_session_id': author['id'], 'evaluator': bound['binding']['id']}, {'origin': 'human'})['grant']
    assert work.fold_cache_state(root) is None
    assert [(row['kind'], row['id']) for row in work._tasks(P, root)['A']['development']] == [('development-grant', issued['id'])]
    granted = agree('over the cap after the Source grant')
    assert granted.split('.')[1] != carried.split('.')[1] and granted.split('.')[2] != carried.split('.')[2]   # the grant row itself
    assert granted.split('.')[3] == carried.split('.')[3]
    assert not any(job.get('session_id') == author['id'] for job in turn_jobs._JOBS.values())   # no model started

    stamp = work._stamp(ledger)
    sibling = state(root, view='observe', id='B')
    assert sibling['token'] == _basis_token(state(root, view='detail', id='B')) and sibling['activity']['selected'] is None
    assert sibling['token'].split('.')[1] == granted.split('.')[1]
    foreign = state(root, view='observe', id='X')                                     # Work of another namespace: absent here
    assert foreign['token'].split('.')[1:3] == [granted.split('.')[1], 'absent'] and 'selected' not in foreign['reads']
    assert nav.observe('empty', {'id': 'A'}, root)['token'].split('.')[1:3] == ['0' * 12, 'absent']
    other = nav.observe('other', {'id': 'X'}, root)['token'].split('.')
    assert other[1] not in {'0' * 12, granted.split('.')[1]} and other[2] != 'absent'
    early = nav.observe(P, {'id': 'A'}, root, now=NOW + dt.timedelta(minutes=2))
    assert early['activity']['selected']['state'] == 'running'
    late = nav.observe(P, {'id': 'A', 'since': early['token']}, root, now=NOW + dt.timedelta(minutes=30))
    assert late['changes'] == ['activity'] and late['expires_next_at'] is None
    assert late['activity']['selected']['state'] == 'unknown' and 'UNKNOWN now' in late['activity']['selected']['qualification']
    assert work._stamp(ledger) == stamp and _secondary(root) == {'token': [], 'activity': False}


def test_the_captured_project_fold_keeps_task_copies_and_exact_absence(root, monkeypatch):
    make(root, 'A');make(root, 'X', project='other')
    retained, fold = work._captured(P, root)
    assert work._retained(root, retained) and set(fold) == {'A'}
    monkeypatch.setattr(work, 'FOLD_CACHE_MAX_LEDGER_BYTES', 64)
    work._FOLD_CACHE.pop(work._ledger(root), None)                                  # uncached and now over the fixture cap
    entry, fold = work._captured(P, root)
    assert not work._retained(root, entry) and work.fold_cache_state(root) is None and set(fold) == {'A'}
    assert work._captured(P, root, entry)[1] is fold                                  # one capture, never a second lookup
    mine = work._tasks(P, root)['A'];mine['title'] = 'mutated';mine.setdefault('depends_on', []).append('Z')
    assert work._captured(P, root)[1]['A']['title'] == 'Title A' and 'Z' not in (work._tasks(P, root)['A'].get('depends_on') or [])
    assert work._tasks(P, root)['A'] is not work._tasks(P, root)['A']
    assert work._captured('nobody', root)[1] == {} and set(work._captured('other', root)[1]) == {'X'}
