"""Work review lifecycle repair1 (Sol review 2026-10-16, WR-R1..WR-R4): the controls of each finding.

WR-R1 a native turn cannot manufacture an independent external reviewer, and evidence is public repository bytes;
WR-R2 a review covers exactly its declared handed-off inputs and the Work's material intent, and the read cut moves;
WR-R3 a follow-up survives every partial landing through its own request, with original attribution and exact receipts;
WR-R4 the exact review door reads phases lazily, default reads stay in budget and never copy phase bodies.
Disposable synthetic fixtures only; no real private file is read.
"""
from __future__ import annotations

import json
import os

import pytest

from laplace.work import project_work as work, project_work_review as review, project_work_views as views
from test_work_review_lifecycle import (OBLIGATIONS, P, guard, handoff, native, post, reviewed, root, sha, state,  # noqa: F401
                                        turn, _status_guards)


def _external(root, name='Sol6.1', **extra):
    return {'origin': 'external', 'actor': name, 'evidence': [{'path': 'evidence/public.md', 'sha256': sha(root, 'evidence/public.md')}], **extra}


# ---------------------------------------------------------------------------------------------- WR-R1

def test_a_native_session_cannot_manufacture_an_independent_external_reviewer(root):
    first = handoff(root)
    alias = reviewed(root, first['phase']['id'], 'source', turn_id='WT-prod-2', request='req-alias-same', actor=_external(root, 'Self alias'))
    assert alias['phase']['independence'] == 'SELF' and alias['phase']['actor']['verified'] is False
    other = reviewed(root, first['phase']['id'], 'source', turn_id='WT-rev', request='req-alias-other', actor=_external(root, 'Other alias'))
    assert other['phase']['independence'] == 'UNKNOWN', 'a claim through another session is still unverified'
    row = next(item for item in other['review']['obligations'] if item['id'] == 'source')
    assert row['satisfied'] is False and row['reviewer_verified'] is False


def test_the_author_attests_an_external_reviewer_with_exact_qualifiers(root):
    first = handoff(root)
    code, body = post(root, {'id': 'parent', 'phase': 'review', 'request_id': 'req-attested-sol', 'expected_work_revision': guard(root),
                             'handoff_id': first['phase']['id'], 'obligation_id': 'source', 'verdict': 'ACCEPT',
                             'actor': _external(root, profile='Sol6.1/high', scope='independent source review')})
    assert code == 200, body
    actor = body['phase']['actor']
    assert actor['verified'] is True and actor['attestation'] == {'door': 'human', 'by': 'author'}
    assert (actor['actor'], actor['profile'], actor['scope']) == ('Sol6.1', 'Sol6.1/high', 'independent source review')
    assert body['phase']['independence'] == 'INDEPENDENT'
    assert next(item for item in body['review']['obligations'] if item['id'] == 'source')['satisfied'] is True


@pytest.mark.parametrize('case', ['private', 'runtime', 'secret', 'symlink', 'wrong-hash', 'missing'])
def test_evidence_and_pins_refuse_private_runtime_and_unowned_paths_before_hashing(root, case):
    if case == 'private':
        (root / 'soul').mkdir(); (root / 'soul/notes.txt').write_text('synthetic private bytes'); path = 'soul/notes.txt'
    elif case == 'runtime':
        (root / '.laplace-state').mkdir(); (root / '.laplace-state/x.json').write_text('{}'); path = '.laplace-state/x.json'
    elif case == 'secret':
        (root / 'auth.json').write_text('{}'); path = 'auth.json'
    elif case == 'symlink':
        os.symlink(root / 'evidence/public.md', root / 'evidence/linked.md'); path = 'evidence/linked.md'
    else:
        path = 'evidence/public.md' if case == 'wrong-hash' else 'evidence/absent.md'
    pin = sha(root, path) if (root / path).is_file() and case != 'wrong-hash' else 'sha256:' + '0' * 64
    with pytest.raises(ValueError, match='PRIVATE_OR_UNOWNED|CHANGED_INPUT'):
        handoff(root, request='req-evidence-' + case, evidence=[{'path': path, 'sha256': pin}])
    assert not any(row.get('record') == 'project-work-phase' for row in work._rows(root)), 'nothing recorded'


# ---------------------------------------------------------------------------------------------- WR-R2

@pytest.mark.parametrize('case', ['unrelated', 'partial', 'extra'])
def test_a_review_covers_exactly_its_declared_handed_off_inputs(root, case):
    first = handoff(root)
    pins = {'unrelated': {'docs/guide.md': sha(root, 'docs/guide.md')}, 'partial': {'src/a.py': sha(root, 'src/a.py')},
            'extra': {'src/a.py': sha(root, 'src/a.py'), 'src/b.py': sha(root, 'src/b.py'), 'docs/guide.md': sha(root, 'docs/guide.md')}}[case]
    with pytest.raises(ValueError, match='covers exactly the handed-off declared inputs'):
        reviewed(root, first['phase']['id'], 'source', pins=pins, request='req-cover-' + case)


def test_an_aggregate_only_handoff_gives_a_coarse_review_and_a_pinned_handoff_pins_every_declared_input(root):
    with pytest.raises(ValueError, match='pins every declared input'):
        native(root, 'WT-prod', {'id': 'parent', 'phase': 'handoff', 'request_id': 'req-handoff-partial', 'expected_work_revision': guard(root),
                                 'object': {'kind': 'source'}, 'pins': {'src/a.py': sha(root, 'src/a.py')}})
    coarse = native(root, 'WT-prod', {'id': 'parent', 'phase': 'handoff', 'request_id': 'req-handoff-aggregate', 'expected_work_revision': guard(root),
                                      'object': {'aggregate': 'sha256:' + 'a' * 64}})
    with pytest.raises(ValueError, match='aggregate-only handoff'):
        reviewed(root, coarse['phase']['id'], 'source', pins={'src/a.py': sha(root, 'src/a.py'), 'src/b.py': sha(root, 'src/b.py')})
    plain = reviewed(root, coarse['phase']['id'], 'source', request='req-coarse-review')
    assert plain['phase']['coarse'] is True
    assert next(item for item in plain['review']['obligations'] if item['id'] == 'source')['currentness'] == 'UNKNOWN'


def test_a_changed_input_stales_only_its_scope_and_a_material_intent_change_stales_every_review(root):
    first = handoff(root)
    reviewed(root, first['phase']['id'], 'source'); reviewed(root, first['phase']['id'], 'guide')
    (root / 'src/a.py').write_text('a = 2\n')
    rows = {row['id']: row for row in state(root, view='detail', id='parent')[1]['task']['review']['obligations']}
    assert rows['source']['currentness'] == 'STALE' and rows['guide']['currentness'] == 'CURRENT'
    (root / 'src/a.py').write_text('a = 1\n')
    # adding an obligation (membership, not intent) keeps the disjoint reviews current
    extended = [*OBLIGATIONS, {'id': 'extra', 'scope': 'other', 'label': 'Extra', 'required': False}]
    work.task(P, {'id': 'parent', 'review_obligations': extended, 'expected_work_revision': guard(root)}, root)
    rows = {row['id']: row for row in state(root, view='detail', id='parent')[1]['task']['review']['obligations']}
    assert rows['source']['currentness'] == rows['guide']['currentness'] == 'CURRENT'
    # a different implementation intent is never silently adopted
    work.task(P, {'id': 'parent', 'goal': 'A different implementation intent', 'expected_work_revision': guard(root)}, root)
    rows = {row['id']: row for row in state(root, view='detail', id='parent')[1]['task']['review']['obligations']}
    assert rows['source']['currentness'] == rows['guide']['currentness'] == 'STALE'
    assert 'material intent' in rows['source']['currentness_reason']


def test_a_changed_reviewed_file_moves_the_cut_and_refuses_old_continuations_while_disjoint_changes_keep_it(root):
    first = handoff(root)
    reviewed(root, first['phase']['id'], 'source'); reviewed(root, first['phase']['id'], 'guide')
    for index in range(3):
        work.task(P, {'id': 'child-%d' % index, 'title': 'Child %d' % index, 'goal': 'g', 'parent_work_id': 'parent'}, root)
    page = state(root, view='summary', limit=1)[1]
    cut = page['read_cut']['revision']
    # another project's work does not move this project's cut
    work.task('other-project', {'id': 'elsewhere', 'title': 'Elsewhere', 'goal': 'g'}, root)
    assert state(root, view='summary', limit=1, offset=1, as_of=cut)[1]['read_cut']['revision'] == cut
    (root / 'docs/guide.md').write_text('# Guide changed\n')
    for query in ({'view': 'summary', 'limit': 1, 'offset': 1}, {'view': 'detail', 'id': 'parent', 'limit': 1, 'offset': 1},
                  {'view': 'graph', 'parent_work_id': 'parent', 'limit': 1, 'offset': 1}):
        with pytest.raises(work.WorkConflict) as refusal:
            work.read(P, {**query, 'as_of': cut}, root)
        assert refusal.value.details['next_reads'], 'canonical reinspection is offered'


# ---------------------------------------------------------------------------------------------- WR-R3

def _request(root, **extra):
    return {'id': 'parent', 'phase': 'followup', 'request_id': 'req-follow-exact', 'expected_work_revision': guard(root),
            'finding': 'F1 guard', 'closure': 'required', 'child': {'title': 'Add the guard', 'goal': 'Refuse stale input'}, **extra}


def _children(root):
    tasks = work._tasks(P, root)
    return [ident for ident, row in tasks.items() if row.get('followup_origin')], tasks


@pytest.mark.parametrize('stage', ['child', 'join', 'receipt'])
def test_every_partial_landing_is_completed_by_the_same_request_with_one_child_and_one_closure(root, monkeypatch, stage):
    handoff(root)
    request = _request(root)
    real_append, real_task = work._append, work._task
    def failing_task(project, payload, repo_root=None, **kw):
        if (stage == 'child' and payload.get('id', '').startswith('WORK-followup')) or (stage == 'join' and payload.get('id') == 'parent'):
            raise OSError('synthetic ' + stage + ' failure')
        return real_task(project, payload, repo_root, **kw)
    def failing_append(repo_root, row):
        if stage == 'receipt' and row.get('record') == 'project-work-phase' and row.get('state') != 'PENDING':
            raise OSError('synthetic receipt failure')
        return real_append(repo_root, row)
    monkeypatch.setattr(work, '_task', failing_task); monkeypatch.setattr(work, '_append', failing_append)
    try:
        first = native(root, 'WT-prod', request)
    except OSError:
        first = {'status': 'RAISED'}
    monkeypatch.setattr(work, '_task', real_task); monkeypatch.setattr(work, '_append', real_append)
    assert first['status'] in {'RAISED', 'PENDING_JOIN', 'PENDING_RECEIPT'}
    again = native(root, 'WT-prod', request)      # the ORIGINAL request, original guard
    assert again['status'] == 'RECOVERED', again
    children, tasks = _children(root)
    assert len(children) == 1
    assert sum(1 for item in tasks['parent']['review_obligations'] if item.get('closure_work_id') == children[0]) == 1
    assert native(root, 'WT-prod', request)['status'] == 'REUSED', 'acknowledgement loss: the completed request is reused'
    assert len(_children(root)[0]) == 1


@pytest.mark.parametrize('field,value', [('finding', 'another finding'), ('closure', 'optional'), ('child', {'title': 'Other', 'goal': 'Refuse stale input'}),
                                         ('child', {'title': 'Add the guard', 'goal': 'Different intent'}),
                                         ('child', {'title': 'Add the guard', 'goal': 'Refuse stale input', 'kind': 'review'}),
                                         ('child', {'title': 'Add the guard', 'goal': 'Refuse stale input', 'section_ids': ['s1']}),
                                         ('summary', 'different summary')])
def test_a_replay_must_repeat_every_effect_bearing_field(root, field, value):
    handoff(root)
    request = _request(root)
    assert native(root, 'WT-prod', request)['status'] == 'JOINED'
    with pytest.raises(ValueError, match='different follow-up'):
        native(root, 'WT-prod', {**request, field: value})


def test_a_completed_request_is_reused_only_by_its_original_identity(root):
    handoff(root)
    request = _request(root)
    native(root, 'WT-prod', request)
    with pytest.raises(ValueError, match='another identity'):
        native(root, 'WT-rev', request)


def test_a_material_edit_while_pending_refuses_recovery_and_an_unchanged_recovery_keeps_the_original_actor(root, monkeypatch):
    handoff(root)
    request = _request(root)
    real = work._task
    def failing(project, payload, repo_root=None, **kw):
        if payload.get('id') == 'parent':
            raise OSError('synthetic failed join')
        return real(project, payload, repo_root, **kw)
    monkeypatch.setattr(work, '_task', failing)
    assert native(root, 'WT-prod', request)['status'] == 'PENDING_JOIN'
    monkeypatch.setattr(work, '_task', real)
    original = work._tasks(P, root)['parent']
    work.task(P, {'id': 'parent', 'goal': 'Materially different parent intent', 'expected_work_revision': guard(root)}, root)
    with pytest.raises(work.WorkConflict, match='not only by its own join'):
        native(root, 'WT-rev', request)
    # put the original specification back (an explicit author edit), then another admitted actor recovers
    work.task(P, {'id': 'parent', 'goal': original['goal'], 'expected_work_revision': guard(root)}, root)
    recovered = native(root, 'WT-rev', request)
    assert recovered['status'] == 'RECOVERED'
    assert recovered['phase']['actor']['session_id'] == 'WS-prod', 'the original producer is retained'
    assert recovered['phase']['recovered_by']['session_id'] == 'WS-rev', 'the recovering identity is recorded separately'


def test_native_phase_and_follow_up_writes_return_exact_owner_receipts_and_a_foreign_append_stays_inexact(root, monkeypatch):
    from laplace.native import tools as writing_tools
    writing_tools.execute(root, P, 'work', 'project', {}, 'WT-prod')
    first = handoff(root)
    assert first['action_receipt']['mutation_attribution']['exact'] is True
    assert first['phase_read']['payload'] == {'namespace': P, 'view': 'review', 'id': 'parent', 'phase_id': first['phase']['id']}
    followed = native(root, 'WT-prod', _request(root, request_id='req-follow-receipt'))
    assert followed['action_receipt']['mutation_attribution']['exact'] is True, followed['action_receipt']['mutation_attribution']
    real = work._append
    def foreign_between(repo_root, row):
        receipt = real(repo_root, row)
        if row.get('state') == 'PENDING':
            real(repo_root, {'record': 'project-work', 'kind': 'work-order', 'id': 'FOREIGN', 'task_id': 'FOREIGN', 'project': 'other',
                             'title': 'Foreign', 'goal': 'g', 'ts': '2026-10-16T00:00:00Z'})
        return receipt
    monkeypatch.setattr(work, '_append', foreign_between)
    raced = native(root, 'WT-prod', _request(root, request_id='req-follow-raced', finding='F2'))
    assert 'owned_changes' not in raced and 'another writer appended' in raced['owned_changes_inexact']
    assert raced['action_receipt']['mutation_attribution']['exact'] is False


# ---------------------------------------------------------------------------------------------- WR-R4

def test_the_exact_review_door_reads_whole_phases_and_refuses_wrong_coordinates(root):
    first = handoff(root, evidence=[{'path': 'evidence/public.md', 'sha256': sha(root, 'evidence/public.md')}])
    review_row = reviewed(root, first['phase']['id'], 'source', findings=[{'id': 'F1', 'summary': 'Specific finding é "quoted" \\ path'}])
    detail = state(root, view='detail', id='parent')[1]
    handle = next(item for item in detail['task']['review']['obligations'] if item['id'] == 'source')['review_read']
    raw, exact = state(root, **{k: v for k, v in handle['payload'].items() if k != 'namespace'})
    row = exact['phase']['rows'][0]
    assert row['findings'] == [{'id': 'F1', 'summary': 'Specific finding é "quoted" \\ path'}]
    assert row['pins'] == {'src/a.py': sha(root, 'src/a.py'), 'src/b.py': sha(root, 'src/b.py')}
    assert row['actor']['session_id'] == 'WS-rev' and row['basis']['work_revision']
    handoff_read = detail['task']['review']['handoff']['read']['payload']
    assert state(root, **{k: v for k, v in handoff_read.items() if k != 'namespace'})[1]['phase']['rows'][0]['evidence'][0]['path'] == 'evidence/public.md'
    obligation = state(root, view='review', id='parent', obligation_id='source')[1]
    assert obligation['obligation']['inputs'] == ['src/a.py', 'src/b.py'] and obligation['history']['total'] == 2
    for bad in ({'id': 'legacy'}, {'id': 'parent', 'phase_id': 'PHASE-unknown'}, {'id': 'parent', 'obligation_id': 'nope'}):
        with pytest.raises(ValueError):
            work.read(P, {'view': 'review', **bad}, root)
    with pytest.raises(work.WorkConflict):
        work.read(P, {'view': 'review', 'id': 'parent', 'phase_id': review_row['phase']['id'], 'phase_revision': 'sha256:' + '0' * 64}, root)
    with pytest.raises(ValueError):
        work.read('another', {'view': 'review', 'id': 'parent'}, root)


def test_declared_obligations_at_their_ceiling_keep_every_read_inside_its_budget(root):
    inputs = ['src/' + 'é"界' * 10 + 'p' * 30 + str(i) + '.py' for i in range(64)]   # a backslash is not a repository path
    obligations = [{'id': 'o%d' % i, 'scope': 'source', 'label': 'Scoped review é "%d"' % i, 'inputs': inputs} for i in range(24)]
    work.task(P, {'id': 'parent', 'review_obligations': obligations, 'expected_work_revision': guard(root)}, root)
    raw, detail = state(root, view='detail', id='parent')
    assert len(raw) <= 50000, len(raw)
    home, summary = state(root, view='summary', limit=12)
    assert len(home) <= 30000 and all(len(json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode()) <= 1300 for row in summary['tasks'])
    assert len(state(root, view='graph', limit=50)[0]) <= 30000
    exact = state(root, view='review', id='parent', obligation_id='o23')[1]
    assert exact['obligation']['inputs'] == inputs, 'every declared input on the deliberate read'


def test_reading_many_phases_never_copies_their_bodies(root, monkeypatch):
    first = handoff(root)
    for index in range(40):
        reviewed(root, first['phase']['id'], 'source', verdict='HOLD', request='req-cost-%02d' % index,
                 findings=[{'id': 'F%d' % j, 'summary': 'Recorded finding ' + '界"\\' * 60} for j in range(20)])
    copied = []
    real = work._deep
    monkeypatch.setattr(work, '_deep', lambda value: (copied.append(1), real(value))[1])
    for _ in range(2):
        copied.clear()
        state(root, view='summary', limit=12)
        assert len(copied) < 200, 'specifications only; the 41 phase bodies are never deep-copied'


def test_a_review_that_recorded_no_material_intent_is_never_current(root, monkeypatch):
    first = handoff(root)
    with monkeypatch.context() as legacy:
        legacy.setattr(review, 'intent_digest', lambda *args: None)
        reviewed(root, first['phase']['id'], 'source')
    row = next(item for item in state(root, view='detail', id='parent')[1]['task']['review']['obligations'] if item['id'] == 'source')
    assert row['currentness'] == 'UNKNOWN' and 'no material Work intent' in row['currentness_reason'] and row['satisfied'] is False


def test_a_review_write_never_refreshes_a_concept_or_literature_read_that_shares_the_work_id():
    from laplace.writing import mutation_attribution
    for operation in ('concept', 'literature_scope'):
        read = {'operation': operation, 'payload': {'node': 'parent'}}
        assert mutation_attribution._read_relevant_to_action('work_review', {'id': 'parent', 'phase': 'review'}, read) is False
        assert mutation_attribution._read_relevant_to_action('concept_change', {'id': 'parent'}, read) is True, 'the control: a node write does'


def test_returned_phase_and_facet_data_are_caller_owned_never_the_fold_cache(root):
    # the owner's direct return (no transport round trip): a REUSED replay is served from the folded, cached row
    payload = {'id': 'parent', 'phase': 'handoff', 'request_id': 'req-handoff-direct', 'expected_work_revision': guard(root),
               'object': {'kind': 'source'}, 'pins': {rel: sha(root, rel) for rel in ('src/a.py', 'src/b.py', 'docs/guide.md')}}
    first = review.record(P, dict(payload), root)
    again = review.record(P, dict(payload, expected_work_revision=guard(root)), root)
    assert again['status'] == 'REUSED'
    for body in (first, again):
        body['phase']['obligations'].append('TAMPERED'); body['phase']['pins'].clear()
        body['review']['handoff']['obligations'].append('TAMPERED'); body['review']['handoff']['object']['kind'] = 'TAMPERED'
    detail = state(root, view='detail', id='parent')[1]['task']['review']
    assert 'TAMPERED' not in detail['handoff']['obligations'] and detail['handoff']['object'].get('kind') != 'TAMPERED'
    detail['handoff']['obligations'].append('TAMPERED-2')
    phase = state(root, view='review', id='parent', phase_id=first['phase']['id'])[1]['phase']['rows'][0]
    assert 'TAMPERED' not in phase['obligations'] and phase['pins'], 'the folded rows are unchanged'
    assert 'TAMPERED-2' not in state(root, view='detail', id='parent')[1]['task']['review']['handoff']['obligations']
    # an in-process owner read (the native door, no JSON round trip) is caller-owned too
    served = views.read(P, {'view': 'detail', 'id': 'parent'}, root)['task']['review']['handoff']
    served['obligations'].append('TAMPERED-3'); served['object']['kind'] = 'TAMPERED-3'
    reread = views.read(P, {'view': 'detail', 'id': 'parent'}, root)['task']['review']['handoff']
    assert 'TAMPERED-3' not in reread['obligations'] and reread['object'].get('kind') != 'TAMPERED-3'
    assert isinstance(work._tasks(P, root)['parent']['phases'], tuple), 'the fold keeps phases as its read-only tuple'


def test_an_acknowledgement_lost_phase_is_reused_by_its_same_request_and_never_recorded_twice(root):
    first = handoff(root)
    assert handoff(root)['status'] == 'REUSED'
    once = reviewed(root, first['phase']['id'], 'source', request='req-review-retry')
    again = reviewed(root, first['phase']['id'], 'source', request='req-review-retry')
    assert once['status'] == 'RECORDED' and again['status'] == 'REUSED' and again['phase']['id'] == once['phase']['id']
    assert again['review']['reviews_recorded'] == 1


def test_served_synthesis_and_issued_recovery_requests_are_caller_owned(root, monkeypatch):
    first = handoff(root)
    reviews = [reviewed(root, first['phase']['id'], ident)['phase']['id'] for ident in ('source', 'guide')]
    native(root, 'WT-prod', {'id': 'parent', 'phase': 'synthesis', 'request_id': 'req-synth-owned', 'expected_work_revision': guard(root),
                             'consumes': [first['phase']['id'], *reviews]})
    real = work._task
    monkeypatch.setattr(work, '_task', lambda project, payload, repo_root=None, **kw: (_ for _ in ()).throw(OSError('disk full'))
                        if payload.get('id') == 'parent' else real(project, payload, repo_root, **kw))
    native(root, 'WT-prod', {'id': 'parent', 'phase': 'followup', 'request_id': 'req-follow-owned', 'expected_work_revision': guard(root),
                             'finding': 'owned', 'closure': 'required', 'child': {'title': 'Owned', 'goal': 'Join later'}})
    monkeypatch.setattr(work, '_task', real)
    served = views.read(P, {'view': 'detail', 'id': 'parent'}, root)['task']['review']
    served['synthesis']['consumes'].append('TAMPERED'); served['pending_joins'][0]['recover']['child']['section_ids'].append('TAMPERED')
    reread = views.read(P, {'view': 'detail', 'id': 'parent'}, root)['task']['review']
    assert 'TAMPERED' not in reread['synthesis']['consumes'] and reread['pending_joins'][0]['recover']['child']['section_ids'] == []
