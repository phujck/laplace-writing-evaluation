"""The delivery commitment of one native call (delivery-commit grant 2026-10-19; Root decision; Sol SD-R1, SD-R2).

Both offered spellings of a request, the named {operation, payload} and the semantic verb/concept form the resolver
publishes (writing_verbs.native_example), reach the one dispatch and carry the same delivery policy through planning,
the receipt, every addition and the final admission; the plan fixes which mutable offers belong to this delivery, and
offers arriving after it wait for the next boundary. Real owners in synthetic tmp roots: an admitted project-tool-boundary
input on a RUNNING turn, real author corrections, a Work tree read through writing_tools.call.
"""
from __future__ import annotations

import json

import pytest

from laplace.core import bodies as core_bodies
from laplace.work import project_work as work
from laplace.writing import provider_updates as updates
from laplace.native import tools as writing_tools, verbs as writing_verbs
from laplace.writing import operations
from laplace.writing import turn_control
from laplace.writing import child_hosts
from laplace.writing import session_reads
from laplace.pipeline import authoring
from laplace.writing import delivery
from laplace.manuscript import proposal_currentness
from laplace.projects.writing_sources import content_text
from test_provider_update_join import _running_input, clear, seed  # noqa: F401  (clear is the autouse cache fixture)
from test_shared_input_publication import BOUND, PARENT, _control, _frontier, _input_rows, _rows, _tree

BRANCH = {'view': 'branch', 'id': PARENT}


def _semantic(payload):
    example = writing_verbs.native_example('project', payload, project='p')
    assert example['available'], example
    return example['native_request']


def _spelled(spelling, payload):
    return {'operation': 'project', 'payload': payload} if spelling == 'named' else _semantic(payload)


def _owner(value):
    return value.get('owner_response', value)


def _running(root, monkeypatch):
    seed(root, monkeypatch)
    turn = updates.turn_scope(root, 'p', 'T')
    child_hosts._update_child_execution(root, 'WS-S', {'state': 'RUNNING', 'turn_id': 'T', 'session_id': 'WS-S', 'project': 'p', 'host': child_hosts._process_identity()})
    return turn


def _count_owner_calls(monkeypatch):
    calls, original = [], operations._execute
    monkeypatch.setattr(operations, '_execute', lambda *a, **k: calls.append(a[3]) or original(*a, **k))
    return calls


def _after_owner_read(monkeypatch, effect):
    """Run ``effect`` once, deterministically between the owner's return and the receipt/additions of the same call."""
    original, done = operations._execute, []

    def wrapped(*a, **k):
        result = original(*a, **k)
        if a[3] == 'project' and not done:
            done.append(effect())
        return result
    monkeypatch.setattr(operations, '_execute', wrapped)
    return done


# ---------------------------------------------------------------------------------------------------- SD-R1: one act

@pytest.mark.parametrize('spelling', ['named', 'semantic'])
def test_both_spellings_carry_one_policy_through_a_pending_full_input(tmp_path, monkeypatch, spelling):
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': '界' * 1500})
    _tree(tmp_path)
    calls = _count_owner_calls(monkeypatch)
    value = writing_tools.call(tmp_path, 'p', 'work', _spelled(spelling, BRANCH), 'T')
    assert calls == ['project'], 'one owner execution'
    assert delivery.emitted(value) <= BOUND and 'delivery_bound' not in value
    assert value['turn_input']['status'] == 'DEFERRED_AT_TOOL_BOUNDARY'
    assert _control(tmp_path, control['control_id'])['state'] == 'PREPARED_AT_TOOL_BOUNDARY' and _frontier(tmp_path) == 0 and _input_rows(tmp_path) == []
    owner = _owner(value)
    assert owner['pagination']['covered'] == len(owner['children']) and owner['read_receipt']['payload'] == {**BRANCH, 'project': 'p'}
    if spelling == 'semantic':
        assert value['ok'] is True and value['outcome'] == 'read' and value['banked_row']['verb'] == 'read'
        assert value['owner']['operation'] == 'project', 'the grammar receipt is kept exactly'


def test_the_two_spellings_select_the_same_page_under_the_same_plan(tmp_path, monkeypatch):
    pages = {}
    for spelling in ('named', 'semantic'):
        root = tmp_path / spelling;root.mkdir()
        _running_input(root, monkeypatch, {'text': '界' * 1500});_tree(root)
        value = writing_tools.call(root, 'p', 'work', _spelled(spelling, BRANCH), 'T')
        turn = session_reads._records(root)['turns']['T']
        read = next(row for row in turn['tool_reads'].values() if row['id'] == _owner(value)['read_receipt']['id'])
        pages[spelling] = {'covered': read['projection']['page']['covered'], 'kinds': read['projection']['page']['kinds'],
                           'line': read['projection']['page']['line'], 'input': value['turn_input']['status']}
    assert pages['named']['covered'] == pages['semantic']['covered'] and pages['named']['kinds'] == pages['semantic']['kinds']
    assert pages['semantic']['line'] < pages['named']['line'], 'the semantic envelope is planned into the page line'
    assert pages['named']['input'] == pages['semantic']['input'] == 'DEFERRED_AT_TOOL_BOUNDARY'


def test_a_semantic_page_replays_current_and_a_genuine_change_replays_changed(tmp_path, monkeypatch):
    _running(tmp_path, monkeypatch)
    _tree(tmp_path)
    value = writing_tools.call(tmp_path, 'p', 'work', _semantic(BRANCH), 'T')
    turn = session_reads._records(tmp_path)['turns']['T']
    read = next(row for row in turn['tool_reads'].values() if row['id'] == _owner(value)['read_receipt']['id'])
    assert proposal_currentness._observe_read(tmp_path, turn, read, {}) is None
    saved = _rows(tmp_path)
    work.task('p', {'id': 'c0', 'title': '変' * 160, 'expected_work_revision': work._task_revision(work._tasks('p', tmp_path)['c0'])}, tmp_path)
    assert proposal_currentness._observe_read(tmp_path, turn, read, {})['currentness'] == 'CHANGED' and _rows(tmp_path) == saved


def test_a_semantic_refusal_is_admitted_with_the_act_profile(tmp_path, monkeypatch):
    _running(tmp_path, monkeypatch)
    big = 'B' + 'x' * 13999
    work.task('p', {'id': big, 'title': 'big', 'goal': 'big'}, tmp_path);work.task('p', {'id': 'child', 'title': 'child', 'goal': 'child', 'parent_work_id': big}, tmp_path)
    before = len(_rows(tmp_path))
    value = writing_tools.call(tmp_path, 'p', 'work', _semantic({'view': 'branch', 'id': big}), 'T')
    assert value['ok'] is False and 'refused' in value and delivery.emitted(value) <= BOUND
    assert 'exceeded' not in (value.get('delivery_bound') or {})
    assert [row['record'] for row in _rows(tmp_path)[before:]].count('writing-tool-failure') == 1
    assert value['failure_read']['payload']['id'].startswith('activity:journal:')


# ---------------------------------------------------------------------------------------------------- SD-R2: the cut

def test_a_correction_arriving_after_the_plan_waits_for_the_next_boundary_without_acknowledgement(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    first = updates.author_offer(tmp_path, 'p', 'T');updates.acknowledge(tmp_path, 'p', 'T', first['correction_ids'][0])
    parent = 'P' + 'x' * 900
    work.task('p', {'id': parent, 'title': 'parent', 'goal': 'parent'}, tmp_path)
    for n in range(20):
        work.task('p', {'id': 'c%d' % n, 'title': '界' * 160, 'goal': '意' * 200, 'parent_work_id': parent}, tmp_path)
    late = _after_owner_read(monkeypatch, lambda: authoring.bank_correction(
        'p', {'text': 'Late author instruction. ' * 60, 'kind': 'request', 'scope': 'project', 'by': 'author'}, tmp_path)['correction']['id'])
    value = writing_tools.call(tmp_path, 'p', 'work', {'operation': 'project', 'payload': {'view': 'branch', 'id': parent}}, 'T')
    assert late and delivery.emitted(value) <= BOUND and 'delivery_bound' not in value
    assert 'author_updates' not in value, 'the late correction is outside the cut'
    scope = updates.turn_scope(tmp_path, 'p', 'T')
    assert [row['correction_ids'] for row in scope['author_update_deliveries']] == [first['correction_ids']]
    assert set(scope['author_update_acks']) == set(first['correction_ids'])
    after = writing_tools.call(tmp_path, 'p', 'work', {'operation': 'project', 'payload': {'view': 'roots'}}, 'T')
    assert after['author_updates']['correction_ids'] == late and after['author_updates']['status'] == 'OFFERED_AT_TOOL_BOUNDARY'
    assert delivery.emitted(after) <= BOUND


def test_an_input_admitted_after_the_plan_is_neither_prepared_nor_published_until_the_next_boundary(tmp_path, monkeypatch):
    turn = _running(tmp_path, monkeypatch)
    _tree(tmp_path)
    calls = []
    original = turn_control._prepare_steering_input
    monkeypatch.setattr(turn_control, '_prepare_steering_input', lambda *a: calls.append(1) or original(*a))
    late = _after_owner_read(monkeypatch, lambda: turn_control._queue_child_steering(
        tmp_path, turn, {'turn_id': 'T', 'project': 'p', 'text': 'Short input', 'delivery_mode': 'project_tool_boundary'}))
    value = writing_tools.call(tmp_path, 'p', 'work', {'operation': 'project', 'payload': BRANCH}, 'T')
    control = late[0]['control_id']
    assert 'turn_input' not in value and delivery.emitted(value) <= BOUND and 'delivery_bound' not in value
    assert _control(tmp_path, control)['state'] == 'PENDING' and calls == [] and _frontier(tmp_path) == 0 and _input_rows(tmp_path) == []
    assert updates.acknowledge_turn_input(tmp_path, 'p', 'T', control) is None
    after = writing_tools.call(tmp_path, 'p', 'work', {'operation': 'project', 'payload': {'view': 'roots'}}, 'T')
    assert after['turn_input']['status'] == 'PUBLISHED_AT_TOOL_BOUNDARY' and after['turn_input']['inputs'][0]['control_id'] == control
    assert calls == [1] and _frontier(tmp_path) == 1 and delivery.emitted(after) <= BOUND


def test_an_eligible_input_cancelled_before_the_commit_publishes_nothing_and_the_next_waits(tmp_path, monkeypatch):
    turn, control = _running_input(tmp_path, monkeypatch, {'text': 'Short input'})
    _tree(tmp_path)
    request = next(child_hosts._steer_mailbox(tmp_path, 'WS-S').glob('*-' + control['control_id'] + '.request.json'))
    ack = request.with_name(request.name.replace('.request.json', '.ack.json'))

    def cancel():
        child_hosts._write_host(ack, {**child_hosts._read_host(ack), 'state': 'FAILED', 'terminal': True, 'error': 'cancelled by its owner'})
        return turn_control._queue_child_steering(tmp_path, turn, {'turn_id': 'T', 'project': 'p', 'text': 'Next input', 'delivery_mode': 'project_tool_boundary'})
    late = _after_owner_read(monkeypatch, cancel)
    value = writing_tools.call(tmp_path, 'p', 'work', {'operation': 'project', 'payload': BRANCH}, 'T')
    assert 'turn_input' not in value and delivery.emitted(value) <= BOUND
    assert _control(tmp_path, control['control_id'])['state'] == 'FAILED' and _input_rows(tmp_path) == []
    assert _control(tmp_path, late[0]['control_id'])['state'] == 'PENDING', 'the next control is outside the cut'
    after = writing_tools.call(tmp_path, 'p', 'work', {'operation': 'project', 'payload': {'view': 'roots'}}, 'T')
    assert after['turn_input']['inputs'][0]['control_id'] == late[0]['control_id'] and _frontier(tmp_path) == 2


# ---------------------------------------------------------------------------------- the bounded late answers are planned

def test_a_failed_commit_answers_within_the_reserved_form(tmp_path, monkeypatch):
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': 'Short input'})
    _tree(tmp_path)
    monkeypatch.setattr(updates, '_bank_input_once', lambda *a, **k: (_ for _ in ()).throw(OSError('é' * 3000)))
    value = writing_tools.call(tmp_path, 'p', 'work', {'operation': 'project', 'payload': BRANCH}, 'T')
    answer = value['turn_input']
    assert answer['status'] == 'INPUT_FAILED' and len(content_text(answer['error']).encode('utf-8')) - 2 <= 500
    assert delivery.emitted(value) <= BOUND and 'delivery_bound' not in value
    assert _control(tmp_path, control['control_id'])['state'] == 'FAILED' and _frontier(tmp_path) == 1


def test_a_published_input_keeps_room_for_its_maintenance_warning(tmp_path, monkeypatch):
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': 'Short input'})
    _tree(tmp_path)
    update, failed = child_hosts._update_child_execution, []

    def fault(root, session, patch, **kwargs):
        if not failed and (patch.get('last_control') or {}).get('state') == 'PUBLISHED_AT_TOOL_BOUNDARY':
            failed.append(1);raise OSError('ü' * 3000)
        return update(root, session, patch, **kwargs)
    monkeypatch.setattr(child_hosts, '_update_child_execution', fault)
    value = writing_tools.call(tmp_path, 'p', 'work', {'operation': 'project', 'payload': BRANCH}, 'T')
    assert value['turn_input']['status'] == 'PUBLISHED_AT_TOOL_BOUNDARY' and value['turn_input']['maintenance_warning']['stage'] == 'execution-observation'
    assert len(content_text(value['turn_input']['maintenance_warning']['error']).encode('utf-8')) - 2 <= 500
    assert delivery.emitted(value) <= BOUND and 'delivery_bound' not in value
    assert _control(tmp_path, control['control_id'])['state'] == 'PUBLISHED_AT_TOOL_BOUNDARY'


def test_the_reserved_forms_are_the_largest_of_their_owners():
    from laplace.representation import writing_bodies as bodies
    big = 'x' * 500
    receipt = {'control_id': 'c' * 32, 'sequence': 1}
    turn = {'id': 'T', 'session_id': 'WS-S'}
    forms = updates.input_forms('p', turn, receipt)
    assert {form['status'] for form in forms} == {'DEFERRED_AT_TOOL_BOUNDARY', 'PREPARATION_FAILED', 'PUBLICATION_UNCONFIRMED', 'SCOPE_CHANGED', 'INPUT_FAILED'}
    real = updates._input_failed_answer(receipt, OSError('ü' * 3000), {'status': 'UNPROVED_INVALIDATED', 'record_id': 'CTX-INPUT-INVALIDATED-' + 'c' * 32,
                                                                       'error': delivery.bounded_text('ü' * 3000)})   # as invalidate_unpublished_input bounds it
    assert delivery.emitted(real) <= max(delivery.emitted(form) for form in forms)
    custody = {**core_bodies.degradation(), 'failed_attempts': 3, 'inline_bytes': 120, 'identities': [{'reason': 'r', 'content_handle': 'sha256:' + 'a' * 64}] * 8, 'identities_omitted': 1}
    projected = delivery._project_custody({'custody_degradation': custody}, [])['custody_degradation']
    assert delivery.emitted(projected) <= delivery.emitted(writing_tools._custody_form())
    assert delivery.bounded_text('é' * 3000) == 'é' * 250 and delivery.bounded_text(big + 'y') == big
