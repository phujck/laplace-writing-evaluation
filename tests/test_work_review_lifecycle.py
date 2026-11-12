"""The Work review lifecycle (WORK-editor-work-review-lifecycle-20261015, WL-T1..T5; M5 2026-10-16).

An implementation handoff, scoped reviews, synthesis and linked follow-up are append-only phases of the SAME Work
owner (project_work_review over the project Work ledger). These tests drive the two real doors: native through an
admitted writing turn (writing_tools.execute) and HTTP (project_work_surface.handle /work/review), then read the
owner's projection through /work/state. Disposable fixture files only.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from laplace.work import project_work as work, project_work_review as review
from laplace.web import project_work_surface as http
from laplace.native import tools as writing_tools
from laplace.core.records import journal

P = 'p'


def sha(root, rel):
    return 'sha256:' + hashlib.sha256((root / rel).read_bytes()).hexdigest()


def turn(root, ident, session, **extra):
    journal.bank_row('contract/talk.jsonl', {'record': 'writing-turn', 'id': ident, 'project': P, 'session_id': session, 'mode': 'work',
                                             'text': 'fixture', 'provider_settings': {'provider': 'codex', 'model': 'fixture-model', 'effort': 'low'},
                                             **extra}, root=root)


OBLIGATIONS = [{'id': 'source', 'scope': 'source', 'label': 'Source review', 'inputs': ['src/a.py', 'src/b.py']},
               {'id': 'guide', 'scope': 'guide', 'label': 'Guide review', 'inputs': ['docs/guide.md']},
               {'id': 'narrow', 'scope': 'human-narrow', 'label': 'Narrow check', 'required': False, 'independent': False}]


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    (tmp_path / 'contract').mkdir()
    (tmp_path / 'registry_projects.json').write_text(json.dumps({'projects': [{'name': P, 'kind': 'general', 'project_dir': 'proj'}]}))
    (tmp_path / 'proj').mkdir()
    for rel, text in (('src/a.py', 'a = 1\n'), ('src/b.py', 'b = 2\n'), ('docs/guide.md', '# Guide\n'), ('evidence/public.md', 'Reviewed é\n')):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding='utf-8')
    turn(tmp_path, 'WT-prod', 'WS-prod')
    turn(tmp_path, 'WT-prod-2', 'WS-prod')                                   # the producer's own session again
    turn(tmp_path, 'WT-rev', 'WS-rev', dispatch_id='D1', parent_turn_id='WT-prod')   # a dispatched child reviewer
    work.task(P, {'id': 'parent', 'title': 'Lifecycle', 'goal': 'Ship the change', 'review_obligations': OBLIGATIONS}, tmp_path)
    work.task(P, {'id': 'legacy', 'title': 'Legacy', 'goal': 'Unchanged'}, tmp_path)
    return tmp_path


def guard(root, ident='parent'):
    return work._task_revision(work._tasks(P, root)[ident])


def native(root, turn_id, payload, mode='work'):
    return writing_tools.execute(root, P, mode, 'work_review', payload, turn_id)


def post(root, payload):
    code, _, raw = http.handle('/work/review', {}, 'POST', json.dumps({'project': P, **payload}).encode(), repo_root=root)
    return code, json.loads(raw)


def state(root, **query):
    code, _, raw = http.handle('/work/state', {'project': [P], **{k: [str(v)] for k, v in query.items()}}, 'GET', repo_root=root)
    assert code == 200, raw[:300]
    return raw, json.loads(raw)


def handoff(root, request='req-handoff-1', **extra):
    return native(root, 'WT-prod', {'id': 'parent', 'phase': 'handoff', 'request_id': request, 'expected_work_revision': guard(root),
                                    'object': {'kind': 'source', 'base': '3b2c0454', 'checkpoint': 'W'},
                                    'pins': {rel: sha(root, rel) for rel in ('src/a.py', 'src/b.py', 'docs/guide.md')}, **extra})


def reviewed(root, handoff_id, obligation, verdict='ACCEPT', turn_id='WT-rev', request=None, **extra):
    return native(root, turn_id, {'id': 'parent', 'phase': 'review', 'request_id': request or 'req-review-' + obligation + '-' + turn_id,
                                  'expected_work_revision': guard(root), 'handoff_id': handoff_id, 'obligation_id': obligation,
                                  'verdict': verdict, **extra}, mode='review')


# ---------------------------------------------------------------------------------------------- WL-T1

def test_native_and_http_doors_admit_the_same_declared_shape_and_review_mode_is_scoped(root):
    """WL-T1: native child/role parity. The same schema refuses the same malformed payloads on both doors before
    any row; review mode records reviews and follow-ups, never handoffs; the owner action names the HTTP door."""
    before = work._ledger(root).read_bytes()
    bad = [{'id': 'parent', 'phase': 'handoff', 'request_id': 'short', 'expected_work_revision': guard(root)},
           {'id': 'parent', 'phase': 'handoff', 'request_id': 'req-unknown-1', 'expected_work_revision': guard(root), 'verdict': 'ACCEPT'},
           {'id': 'parent', 'phase': 'review', 'request_id': 'req-missing-1', 'expected_work_revision': guard(root)},
           {'id': 'parent', 'phase': 'launch', 'request_id': 'req-unknown-2', 'expected_work_revision': guard(root)},
           {'id': 'parent', 'phase': 'synthesis', 'request_id': 'req-extra-123', 'expected_work_revision': guard(root), 'consumes': ['x'], 'by': 'me'}]
    for payload in bad:
        with pytest.raises(ValueError):
            native(root, 'WT-prod', payload)
        code, body = post(root, payload)
        assert code >= 400 and body.get('error'), payload
    assert work._ledger(root).read_bytes() == before, 'a refused shape writes nothing'
    with pytest.raises(ValueError, match='Review mode'):
        native(root, 'WT-rev', {'id': 'parent', 'phase': 'handoff', 'request_id': 'req-role-1', 'expected_work_revision': guard(root)}, mode='review')
    _, detail = state(root, view='detail', id='parent')
    action = detail['allowed_actions']['work_review']
    assert action['http'] == {'method': 'POST', 'url': '/work/review'} and action['payload'] == {'id': 'parent', 'expected_work_revision': guard(root)}
    assert action['phases'] == ['handoff', 'review', 'synthesis', 'followup']
    _, legacy = state(root, view='detail', id='legacy')
    assert 'work_review' not in legacy['allowed_actions'] and 'review' not in legacy['task']


def test_native_identity_comes_from_the_admitted_turn_and_never_from_a_label(root):
    """WL-T1/T3: the producer is the admitted turn's session (provider:model and dispatch lineage recorded); a payload
    cannot claim a native identity; an external identity needs pinned public evidence and is attested by the door."""
    first = handoff(root)
    assert first['status'] == 'RECORDED'
    actor = first['phase']['actor']
    assert actor == {'actor': 'codex:fixture-model', 'session_id': 'WS-prod', 'turn_id': 'WT-prod', 'role': 'producer', 'origin': 'native'}
    child = reviewed(root, first['phase']['id'], 'guide')['phase']['actor']
    assert child['dispatch_id'] == 'D1' and child['parent_turn_id'] == 'WT-prod' and child['role'] == 'reviewer'
    with pytest.raises(ValueError, match='cannot be claimed by label'):
        handoff(root, request='req-handoff-claim', actor={'actor': 'sol', 'origin': 'native'})
    with pytest.raises(ValueError, match='pinned public evidence'):
        reviewed(root, first['phase']['id'], 'source', actor={'actor': 'Sol6.1', 'origin': 'external'}, request='req-ext-none')
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        reviewed(root, first['phase']['id'], 'source', request='req-ext-bad',
                 actor={'actor': 'Sol6.1', 'origin': 'external', 'evidence': [{'path': 'evidence/public.md', 'sha256': 'sha256:' + '0' * 64}]})
    external = reviewed(root, first['phase']['id'], 'source', request='req-ext-good',
                        actor={'actor': 'Sol6.1', 'origin': 'external', 'evidence': [{'path': 'evidence/public.md', 'sha256': sha(root, 'evidence/public.md')}]})
    # repair1 WR-R1: a native turn only CLAIMS an external reviewer; the claim is that session's, never verified
    assert external['phase']['actor']['attestation'] == {'by': 'codex:fixture-model', 'door': 'native', 'session_id': 'WS-rev', 'turn_id': 'WT-rev'}
    assert external['phase']['actor']['verified'] is False and external['phase']['independence'] == 'UNKNOWN'
    code, human = post(root, {'id': 'parent', 'phase': 'review', 'request_id': 'req-human-narrow', 'expected_work_revision': guard(root),
                              'handoff_id': first['phase']['id'], 'obligation_id': 'narrow', 'verdict': 'ACCEPT'})
    assert code == 200 and human['phase']['actor'] == {'actor': 'author', 'role': 'reviewer', 'origin': 'human'}


# ---------------------------------------------------------------------------------------------- WL-T2 / WL-T3

def test_a_handoff_or_self_assessment_never_satisfies_and_final_acceptance_needs_independent_current_reviews(root):
    first = handoff(root)
    facet = first['review']
    assert facet['remaining'] == ['source', 'guide'] and facet['next']['kind'] == 'review'
    with pytest.raises(ValueError, match='a self-assessment does not satisfy'):
        work.transition(P, {'id': 'parent', 'status': 'done', **_status_guards(root)}, root)
    own = reviewed(root, first['phase']['id'], 'source', turn_id='WT-prod-2')        # the producer's session reviews itself
    assert own['phase']['independence'] == 'SELF'
    row = next(item for item in own['review']['obligations'] if item['id'] == 'source')
    assert row['status'] == 'ACCEPTED' and row['satisfied'] is False, 'a self-assessment is history, never acceptance'
    _, detail = state(root, view='detail', id='parent')
    assert 'done' not in detail['allowed_actions']['task_status']['statuses']
    reviewed(root, first['phase']['id'], 'source')
    last = reviewed(root, first['phase']['id'], 'guide')
    assert last['review']['remaining'] == [] and last['review']['next']['kind'] == 'synthesis'
    unknown = review.independence({'origin': 'native', 'actor': 'x'}, first['phase']['actor'])
    assert unknown == 'UNKNOWN', 'an identity without its turn and session is unproved'
    done = work.transition(P, {'id': 'parent', 'status': 'done', 'evidence': ['evidence/public.md'], **_status_guards(root)}, root)
    assert work._tasks(P, root)['parent']['status'] == 'done' and done


def _status_guards(root):
    tasks = work._tasks(P, root)
    return {'expected_work_scope_revision': work._work_basis(tasks, 'parent')[0]['scope_revision'],
            'expected_dependency_revision': work._dependency_revision(tasks['parent'], tasks),
            'expected_work_status_revision': work._standing_revision(tasks['parent'])}


def test_a_review_must_cover_its_handoff_and_review_the_handed_off_bytes(root):
    first = handoff(root, obligations=['source'])
    with pytest.raises(ValueError, match='its handoff covers'):
        reviewed(root, first['phase']['id'], 'guide')
    with pytest.raises(ValueError, match='names a handoff'):
        reviewed(root, 'PHASE-missing', 'source')
    (root / 'src/a.py').write_text('a = 3\n')
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        reviewed(root, first['phase']['id'], 'source')


# ---------------------------------------------------------------------------------------------- WL-T4

def test_followup_creates_one_child_once_replays_and_joins_by_its_closure(root):
    first = handoff(root)
    rejected = reviewed(root, first['phase']['id'], 'source', verdict='REJECT', findings=[{'id': 'F1', 'summary': 'Missing guard'}])
    assert rejected['review']['obligations'][0]['status'] == 'REJECTED'
    request = {'id': 'parent', 'phase': 'followup', 'request_id': 'req-follow-F1', 'expected_work_revision': guard(root),
               'finding': 'F1 missing guard', 'closure': 'required', 'child': {'title': 'Add the guard', 'goal': 'Refuse stale input'}}
    made = native(root, 'WT-rev', request, mode='review')
    assert made['status'] == 'JOINED' and made['child_created'] is True
    child = made['child_id']
    tasks = work._tasks(P, root)
    assert tasks[child]['followup_origin'] == {'parent_work_id': 'parent', 'finding': 'F1 missing guard', 'closure': 'required'}
    assert tasks[child]['parent_work_id'] == 'parent'
    closure = [item for item in tasks['parent']['review_obligations'] if item.get('closure_work_id') == child]
    assert len(closure) == 1 and closure[0]['scope'] == 'closure'
    # the same request again (its own join moved the parent guard): reused, nothing duplicated
    again = native(root, 'WT-rev', request, mode='review')
    assert again['status'] == 'REUSED' and again['child_id'] == child and again['child_created'] is False
    assert sum(1 for t in work._tasks(P, root).values() if t.get('followup_origin')) == 1
    assert len([i for i in work._tasks(P, root)['parent']['review_obligations'] if i.get('closure_work_id')]) == 1
    with pytest.raises(ValueError, match='different follow-up'):
        native(root, 'WT-rev', {**request, 'finding': 'another finding'}, mode='review')
    # a second request for the same finding reuses the one child (identity is parent + finding)
    other = native(root, 'WT-rev', {**request, 'request_id': 'req-follow-F1b', 'expected_work_revision': guard(root)}, mode='review')
    assert other['child_id'] == child and other['child_created'] is False
    # the parent cannot complete while the required follow-up is open
    assert 'closure-' in ' '.join(other['review']['remaining'])
    # the follow-up origin is minted by this door only
    with pytest.raises(ValueError, match='not authored'):
        work.task(P, {'title': 'Forged', 'goal': 'x', 'followup_origin': {'parent_work_id': 'parent', 'finding': 'F2', 'closure': 'optional'}}, root)


def test_prerequisite_and_optional_closures_and_a_pending_join_recovers_with_the_same_request(root, monkeypatch):
    handoff(root)
    pre = native(root, 'WT-prod', {'id': 'parent', 'phase': 'followup', 'request_id': 'req-follow-pre', 'expected_work_revision': guard(root),
                                   'finding': 'needs data', 'closure': 'prerequisite', 'child': {'title': 'Data', 'goal': 'Collect'}})
    assert pre['joined'] and pre['child_id'] in work._tasks(P, root)['parent']['depends_on']
    opt = native(root, 'WT-prod', {'id': 'parent', 'phase': 'followup', 'request_id': 'req-follow-opt', 'expected_work_revision': guard(root),
                                   'finding': 'nice to have', 'closure': 'optional', 'child': {'title': 'Polish', 'goal': 'Tidy'}})
    assert opt['joined'] and opt['child_id'] not in work._tasks(P, root)['parent'].get('depends_on', [])
    # a join that fails is recorded PENDING with its exact child; the same request completes it
    real = work._task
    def failing(project, payload, repo_root=None, **kw):
        if payload.get('id') == 'parent':
            raise OSError('disk full')
        return real(project, payload, repo_root, **kw)
    monkeypatch.setattr(work, '_task', failing)
    request = {'id': 'parent', 'phase': 'followup', 'request_id': 'req-follow-pend', 'expected_work_revision': guard(root),
               'finding': 'pending join', 'closure': 'required', 'child': {'title': 'Pending', 'goal': 'Join later'}}
    pending = native(root, 'WT-prod', request)
    assert pending['status'] == 'PENDING_JOIN' and pending['joined'] is False
    assert pending['review']['pending_joins'][0]['child_id'] == pending['child_id']
    assert pending['review']['next']['kind'] == 'recover-join'
    issued = pending['review']['pending_joins'][0]['recover']
    assert {key: issued[key] for key in ('request_id', 'finding', 'closure')} == {key: request[key] for key in ('request_id', 'finding', 'closure')}
    assert issued['child'] == {'id': pending['child_id'], 'title': 'Pending', 'goal': 'Join later', 'kind': 'execution',
                               'section_ids': []}, 'the owner issues the exact canonical recovery request'
    monkeypatch.setattr(work, '_task', real)
    recovered = native(root, 'WT-prod', request)
    assert recovered['status'] == 'RECOVERED' and recovered['child_id'] == pending['child_id'] and recovered['child_created'] is False
    assert recovered['review']['pending_joins'] == []


# ---------------------------------------------------------------------------------------------- WL-T5

def test_currentness_is_per_obligation_and_a_changed_definition_reopens_only_itself(root):
    first = handoff(root)
    reviewed(root, first['phase']['id'], 'source')
    reviewed(root, first['phase']['id'], 'guide')
    (root / 'docs/guide.md').write_text('# Guide changed\n')
    facet = state(root, view='detail', id='parent')[1]['task']['review']
    rows = {row['id']: row for row in facet['obligations']}
    assert rows['guide']['currentness'] == 'STALE' and 'docs/guide.md' in rows['guide']['currentness_reason']
    assert rows['source']['currentness'] == 'CURRENT' and rows['source']['satisfied'] is True
    assert facet['remaining'] == ['guide']
    # revising one obligation's definition makes only that obligation STALE; the verdict stays as history
    revised = [dict(item) for item in OBLIGATIONS]
    revised[0]['label'] = 'Source review (revised)'
    work.task(P, {'id': 'parent', 'review_obligations': revised, 'expected_work_revision': guard(root)}, root)
    rows = {row['id']: row for row in work.read(P, {'view': 'detail', 'id': 'parent'}, root)['task']['review']['obligations']}
    assert rows['source']['currentness'] == 'STALE' and rows['source']['status'] == 'ACCEPTED'
    # a coarse review (aggregate only, no per-file pins) is never CURRENT
    coarse = native(root, 'WT-prod', {'id': 'parent', 'phase': 'handoff', 'request_id': 'req-handoff-coarse', 'expected_work_revision': guard(root),
                                      'object': {'aggregate': 'sha256:' + 'a' * 64}, 'obligations': ['narrow']})
    narrow = reviewed(root, coarse['phase']['id'], 'narrow', request='req-review-coarse')
    row = next(item for item in narrow['review']['obligations'] if item['id'] == 'narrow')
    assert row['currentness'] == 'UNKNOWN' and narrow['phase']['coarse'] is True


def test_legacy_work_keeps_its_hashes_rows_and_list_bytes_and_managed_rows_meet_the_budgets(root):
    legacy = work._tasks(P, root)['legacy']
    assert 'review_obligations' not in legacy and 'phases' not in legacy
    keys = ('id', 'title', 'goal', 'task_kind', 'parent_work_id', 'depends_on', 'section_ids', 'anchor', 'obligation_id', 'logical_target')
    expected = work._task_revision({key: legacy.get(key) for key in keys} | {'id': 'legacy'})
    assert work._task_revision(legacy) == expected, 'absent lifecycle fields never enter the legacy identity'
    first = handoff(root)
    for index in range(12):
        reviewed(root, first['phase']['id'], 'source', verdict='HOLD', request='req-review-hold-%02d' % index,
                 findings=[{'id': 'F%02d' % i, 'summary': 'é finding "quoted" \\ %d' % i} for i in range(20)])
    home, summary = state(root, view='summary', limit=12)
    assert len(home) <= 30000
    rows = {row['id']: row for row in summary['tasks']}
    assert 'review' not in rows['legacy']
    assert rows['parent']['review'] == {'remaining': 2, 'obligations': 3, 'next': 'review', 'pending_joins': 0}
    for row in summary['tasks']:
        assert len(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode()) <= 1300, row['id']
    detail_raw, detail = state(root, view='detail', id='parent')
    assert len(home) + len(detail_raw) <= 50000, (len(home), len(detail_raw))
    assert 'phases' not in detail['task'], 'phase bodies are not inlined in the detail read'
