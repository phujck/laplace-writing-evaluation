"""The input publication inside the shared delivery boundary (shared-input-publication grant 2026-10-19; Root decision).

Real owners only: an admitted project-tool-boundary input on a RUNNING turn (provider_updates.turn_input_offer, its
retained preparation and inputs[] entries), a real author correction, a Work tree read through writing_tools.call and a
refusal through writing_tools.tool_failure. The page is selected beside the planned notices; the PREPARED->PUBLISHED
transition publishes only what fits and otherwise leaves the preparation, baseline, rows and frontier where they were.
Synthetic tmp roots only.
"""
from __future__ import annotations

import json

import pytest

from laplace.work import project_work as work
from laplace.writing import provider_updates as updates
from laplace.native import tools as writing_tools
from laplace.writing import turn_control
from laplace.writing import session_reads
from laplace.writing import child_hosts
from laplace.writing import records as writing_records
from laplace.pipeline import authoring
from laplace.writing import delivery
from laplace.manuscript import proposal_currentness
from test_provider_update_join import _running_input, clear, seed  # noqa: F401  (clear is the autouse cache fixture)

BOUND = 30000
PARENT = 'P' + 'x' * 1500


def _tree(root):
    work.task('p', {'id': PARENT, 'title': 'parent', 'goal': 'parent'}, root)
    for n in range(20):
        work.task('p', {'id': 'c%d' % n, 'title': '界' * 160, 'goal': '意' * 200, 'parent_work_id': PARENT}, root)


def _call(root, operation, payload):
    return writing_tools.call(root, 'p', 'work', {'operation': operation, 'payload': payload}, 'T')


def _rows(root):
    return [json.loads(line) for line in (root / 'contract/talk.jsonl').read_text().splitlines()]


def _input_rows(root):
    return [row['id'] for row in _rows(root) if row['id'].startswith(('WST-INPUT-', 'CTX-INPUT-', 'CTX-INPUT-INVALIDATED-'))
            or row.get('record') == 'writing-turn-context-baseline']


def _control(root, control_id):
    return session_reads._child_control_rows(root, 'WS-S', 'T', 'RUNNING', item_id=control_id)[0]


def _frontier(root):
    return session_reads.child_execution(root, 'WS-S').get('control_completed_sequence') or 0


def _counted_preparation(monkeypatch):
    calls, original = [], turn_control._prepare_steering_input
    monkeypatch.setattr(turn_control, '_prepare_steering_input', lambda *args: calls.append(1) or original(*args))
    return calls


def test_a_near_limit_page_and_a_short_full_input_publish_within_the_bound(tmp_path, monkeypatch):
    _turn, control = _running_input(tmp_path, monkeypatch)
    _tree(tmp_path)
    value = _call(tmp_path, 'project', {'view': 'branch', 'id': PARENT})
    assert delivery.emitted(value) <= BOUND and 'delivery_bound' not in value
    entry = value['turn_input']['inputs'][0]
    assert value['turn_input']['status'] == 'PUBLISHED_AT_TOOL_BOUNDARY' and entry['message'] == 'Short input'
    assert entry['message_truncated'] is False and entry['publication_parts']['author_request']['complete'] is True
    assert _control(tmp_path, control['control_id'])['state'] == 'PUBLISHED_AT_TOOL_BOUNDARY' and _frontier(tmp_path) == 1
    assert value['author_updates']['status'] == 'OFFERED_AT_TOOL_BOUNDARY' and value['author_updates']['updates']
    turn = session_reads._records(tmp_path)['turns']['T']
    read = next(row for row in turn['tool_reads'].values() if row['id'] == value['read_receipt']['id'])
    assert proposal_currentness._observe_read(tmp_path, turn, read, {}) is None             # the planned page replays CURRENT
    saved = _rows(tmp_path)
    work.task('p', {'id': 'c0', 'title': '変' * 160, 'expected_work_revision': work._task_revision(work._tasks('p', tmp_path)['c0'])}, tmp_path)
    assert proposal_currentness._observe_read(tmp_path, turn, read, {})['currentness'] == 'CHANGED'
    assert _rows(tmp_path) == saved, 'replay writes nothing'


def test_without_room_the_prepared_input_waits_and_repeats_change_nothing(tmp_path, monkeypatch):
    calls = _counted_preparation(monkeypatch)
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': '界' * 1500})          # eligible for FULL (<= 2000 chars)
    _tree(tmp_path)
    first = _call(tmp_path, 'project', {'view': 'branch', 'id': PARENT})
    assert delivery.emitted(first) <= BOUND and 'delivery_bound' not in first
    assert first['turn_input'] == updates.pending_input_notice(tmp_path, 'p', 'T'), 'the delivered notice is the planned notice'
    assert first['turn_input']['status'] == 'DEFERRED_AT_TOOL_BOUNDARY' and first['turn_input']['inputs'][0]['control_id'] == control['control_id']
    prepared = _control(tmp_path, control['control_id'])
    assert prepared['state'] == 'PREPARED_AT_TOOL_BOUNDARY' and _frontier(tmp_path) == 0 and _input_rows(tmp_path) == []
    execution = session_reads.child_execution(tmp_path, 'WS-S')
    for _ in range(3):                                                                      # bounded repetition: nothing progresses
        again = _call(tmp_path, 'project', {'view': 'branch', 'id': PARENT})
        assert again['turn_input']['status'] == 'DEFERRED_AT_TOOL_BOUNDARY' and delivery.emitted(again) <= BOUND
    assert _control(tmp_path, control['control_id']) == prepared and session_reads.child_execution(tmp_path, 'WS-S') == execution
    assert _input_rows(tmp_path) == [] and calls == [1], 'no publication, baseline, frontier or re-preparation growth'
    published = _call(tmp_path, 'project', {'view': 'roots'})                                # a tool result with room
    entry = published['turn_input']['inputs'][0]
    assert published['turn_input']['status'] == 'PUBLISHED_AT_TOOL_BOUNDARY' and entry['message'] == '界' * 1500
    receipt = _control(tmp_path, control['control_id'])
    assert receipt['preparation_sha256'] == prepared['preparation_sha256'] and receipt['publication']['scope'] == 'FULL'
    assert calls == [1] and _frontier(tmp_path) == 1 and sum(row.startswith('WST-INPUT-') for row in _input_rows(tmp_path)) == 1
    assert delivery.emitted(published) <= BOUND
    assert 'turn_input' not in _call(tmp_path, 'project', {'view': 'roots'}), 'published once, never republished'


def test_the_deferred_exact_read_shows_the_request_and_adopts_nothing(tmp_path, monkeypatch):
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': '界' * 1500})
    _tree(tmp_path)
    notice = _call(tmp_path, 'project', {'view': 'branch', 'id': PARENT})['turn_input']
    read = notice['inputs'][0]['exact_read']
    assert read['native_request']['payload'] == read['payload'] and 'session_id' not in read['payload']
    value = writing_tools.execute(tmp_path, 'p', 'work', read['operation'], read['payload'], 'T')   # the read alone, no boundary
    assert value['items'][0]['payload']['text'] == '界' * 1500
    assert updates.acknowledge_turn_input(tmp_path, 'p', 'T', control['control_id']) is None, 'an unpublished input is never acknowledged'
    assert _control(tmp_path, control['control_id'])['state'] == 'PREPARED_AT_TOOL_BOUNDARY' and _input_rows(tmp_path) == []


def test_a_long_input_previews_where_it_fits_and_its_exact_read_acknowledges(tmp_path, monkeypatch):
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': '界' * 2500})          # beyond FULL: the retained plan is PREVIEW
    _tree(tmp_path)
    assert _call(tmp_path, 'project', {'view': 'branch', 'id': PARENT})['turn_input']['status'] == 'DEFERRED_AT_TOOL_BOUNDARY'
    preview = _call(tmp_path, 'project', {'view': 'roots'})
    entry = preview['turn_input']['inputs'][0]
    assert entry['message_truncated'] is True and len(entry['text']) == updates._INPUT_MESSAGE_LIMIT and entry['text_truncated'] is True
    assert entry['context_delivery']['baseline_record_id'] is None and delivery.emitted(preview) <= BOUND
    assert _control(tmp_path, control['control_id'])['publication']['scope'] == 'PREVIEW'
    read = writing_tools.call(tmp_path, 'p', 'work', entry['exact_read']['native_request'], 'T')
    assert read['turn_input_read']['status'] == 'EXACT_SCOPED_CONTROL_READ' and read['turn_input_read']['message'] == '界' * 2500


def test_a_finished_execution_drops_the_pending_input_and_publishes_nothing(tmp_path, monkeypatch):
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': '界' * 1500})
    _tree(tmp_path)
    assert _call(tmp_path, 'project', {'view': 'branch', 'id': PARENT})['turn_input']['status'] == 'DEFERRED_AT_TOOL_BOUNDARY'
    child_hosts._update_child_execution(tmp_path, 'WS-S', {'state': 'FINISHED'}, expected_turn_id='T')
    assert updates.pending_input_notice(tmp_path, 'p', 'T') is None
    value = _call(tmp_path, 'project', {'view': 'roots'})
    assert 'turn_input' not in value and _input_rows(tmp_path) == []
    assert _control(tmp_path, control['control_id'])['state'] == 'PREPARED_AT_TOOL_BOUNDARY'


def test_a_bounded_refusal_with_a_pending_input_is_admitted_whole_with_one_failure_append(tmp_path, monkeypatch):
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': '界' * 1500})
    big = 'B' + 'x' * 13999
    work.task('p', {'id': big, 'title': 'big', 'goal': 'big'}, tmp_path)
    work.task('p', {'id': 'child', 'title': 'child', 'goal': 'child', 'parent_work_id': big}, tmp_path)
    payload = {'view': 'branch', 'id': big}
    with pytest.raises(Exception) as refused:
        writing_tools.execute(tmp_path, 'p', 'work', 'project', payload, 'T')
    before = len(_rows(tmp_path))
    value = writing_tools.tool_failure(tmp_path, 'p', 'work', 'project', payload, refused.value, 'T')
    appended = [row['record'] for row in _rows(tmp_path)[before:]]
    assert appended.count('writing-tool-failure') == 1 and delivery.emitted(value) <= BOUND
    assert value['turn_input']['status'] in {'PUBLISHED_AT_TOOL_BOUNDARY', 'DEFERRED_AT_TOOL_BOUNDARY'}
    published = value['turn_input']['status'] == 'PUBLISHED_AT_TOOL_BOUNDARY'
    assert _frontier(tmp_path) == (1 if published else 0)
    assert value['ok'] is False and value['failure_read']['payload']['id'].startswith('activity:journal:')


def test_author_bodies_without_room_are_the_owner_notice_and_only_the_exact_read_acknowledges(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    long = authoring.bank_correction('p', {'text': '界' * 4000, 'kind': 'request', 'scope': 'project', 'by': 'author'}, tmp_path)['correction']
    _tree(tmp_path)
    value = _call(tmp_path, 'project', {'view': 'branch', 'id': PARENT})
    offer = value['author_updates']
    assert delivery.emitted(value) <= BOUND and 'updates' not in offer and offer['updates_omitted']['count'] == 2
    assert long['id'] in offer['correction_ids'] and [r['payload']['id'] for r in offer['required_reads']] == offer['correction_ids']
    turn = updates.turn_scope(tmp_path, 'p', 'T')
    assert [row['correction_ids'] for row in turn['author_update_deliveries']] == [offer['correction_ids']] and turn['author_update_acks'] == {}
    read = next(r for r in offer['required_reads'] if r['payload']['id'] == long['id'])
    _call(tmp_path, 'author_history', read['payload'])
    assert long['id'] in updates.turn_scope(tmp_path, 'p', 'T')['author_update_acks']


def test_a_newer_context_landing_while_deferred_refuses_the_stale_full_publication(tmp_path, monkeypatch):
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': '界' * 1500, 'selection': {'files': ['sec_two.tex']},
                                                            'workspace_context': {'surface': 'manuscript'}})
    monkeypatch.setattr(updates, '_INPUT_MESSAGE_LIMIT', 100_000)                            # FULL with a context baseline
    _tree(tmp_path)
    assert _call(tmp_path, 'project', {'view': 'branch', 'id': PARENT})['turn_input']['status'] == 'DEFERRED_AT_TOOL_BOUNDARY'
    assert _control(tmp_path, control['control_id'])['preparation']['baseline'] is not None and _input_rows(tmp_path) == []
    writing_records.bank(tmp_path, {'record': 'writing-turn-context-baseline', 'id': 'CTX-NEWER', 'project': 'p', 'turn_id': 'T',
                             'selection': {'files': ['sec_three.tex']}, 'context_parts': {'newer': 'published'}})
    value = _call(tmp_path, 'project', {'view': 'roots'})
    assert value['turn_input']['status'] == 'SCOPE_CHANGED' and 'inputs' not in value['turn_input']
    assert session_reads._records(tmp_path)['turns']['T']['context_basis_record_id'] == 'CTX-NEWER'
    assert _control(tmp_path, control['control_id'])['state'] == 'FAILED'
    assert not any(row.startswith(('CTX-INPUT-', 'WST-INPUT-')) for row in _input_rows(tmp_path))
