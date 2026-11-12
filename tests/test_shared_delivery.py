"""The shared delivery boundary (shared-delivery grant 2026-10-19; Root decision, Sol repair3 R3-P1).

A receipted read binds the semantic projection its owner consulted, and every pure replay reproduces that projection:
a fresh native page whose line differs from the default replays CURRENT, a genuine owner change replays CHANGED. The
complete success or refusal passes one final admission that projects only parts with an exact existing recovery and
says so. Synthetic tmp roots only.
"""
from __future__ import annotations

import json

import pytest

from laplace.core import bodies as core_bodies
from laplace.work import project_work as work
from laplace.native import tools as writing_tools
from laplace.writing import operations
from laplace.writing import reads
from laplace.writing import records as writing_records
from laplace.writing import turn_reads
from laplace.writing import session_reads
from laplace.writing import delivery
from laplace.manuscript import proposal_currentness
from test_work_repair2 import P, LINE, make, native, root  # noqa: F401  (root is the fixture)


def _tree(root, parent):
    make(root, parent, title='parent', goal='parent')
    for n in range(20):
        make(root, 'c%d' % n, title='界' * 160, goal='意' * 200, parent_work_id=parent)


def _consumed(root, value):
    turn = session_reads._records(root)['turns']['WT-n']
    return turn, next(row for row in turn['tool_reads'].values() if row['id'] == value['read_receipt']['id'])


def _talk(root):
    return [json.loads(line) for line in (root / 'contract/talk.jsonl').read_text().splitlines()]


# ------------------------------------------------------------------------------------------------ the receipted projection

def test_a_fresh_native_page_replays_current_and_a_genuine_change_replays_changed(root):
    parent = 'P' + 'x' * 1500                                            # Sol R3-P1: native 5 rows, default line 6
    _tree(root, parent)
    value = native(root, view='branch', id=parent)
    turn, read = _consumed(root, value)
    assert read['projection']['page']['covered'] == len(value['children']) == 5
    default = operations._execute(root, P, 'work', 'project', read['payload'], turn_id='WT-n')
    assert len(default['children']) == 6, 'the default line still differs: the witness is live'
    replayed = operations.replay_read(root, P, 'work', read, 'WT-n')
    assert replayed == {k: v for k, v in value.items() if k not in {'review_read', 'read_receipt'}} | {'review_read': value['review_read']}
    assert reads.read_output_digest('project', replayed) == read['output_sha256']
    assert proposal_currentness._observe_read(root, turn, read, {}) is None                      # production: CURRENT
    prior = work._tasks(P, root)['c0']
    make(root, 'c0', title='変' * 160, expected_work_revision=work._task_revision(prior))          # a guarded owner edit
    assert proposal_currentness._observe_read(root, turn, read, {})['currentness'] == 'CHANGED'


def test_a_legacy_read_row_without_a_projection_replays_with_the_owner_default(root):
    parent = 'P' + 'x' * 1500
    _tree(root, parent)
    value = native(root, view='branch', id=parent)
    _turn, read = _consumed(root, value)
    legacy = {k: v for k, v in read.items() if k != 'projection'}
    assert operations.replay_read(root, P, 'work', legacy, 'WT-n') == \
        operations._execute(root, P, 'work', 'project', read['payload'], turn_id='WT-n')


def test_the_replay_banks_nothing(root):
    parent = 'P' + 'x' * 1500
    _tree(root, parent)
    turn, read = _consumed(root, native(root, view='branch', id=parent))
    before = _talk(root)
    operations.replay_read(root, P, 'work', read, 'WT-n');proposal_currentness._observe_read(root, turn, read, {})
    assert _talk(root) == before


def test_the_roots_page_records_its_attention_preview_as_its_own_part(root):
    for n in range(8):
        make(root, 'r%d' % n, title='界' * 200, goal='意' * 200)
    value = native(root, view='roots')
    turn, read = _consumed(root, value)
    assert set(read['projection']) == {'page', 'attention-preview'}
    assert proposal_currentness._observe_read(root, turn, read, {}) is None


# ------------------------------------------------------------------------------------------------ the final admission

def test_a_native_success_through_call_is_admitted_whole(root):
    parent = 'P' + 'x' * 1500
    _tree(root, parent)
    value = writing_tools.call(root, P, 'work', {'operation': 'project', 'payload': {'view': 'branch', 'id': parent}}, 'WT-n')
    assert delivery.emitted(value) <= LINE and 'delivery_bound' not in value


def test_the_long_identity_refusal_is_admitted_with_its_exact_recovery_and_one_failure_append(root):
    big = 'B' + 'x' * 13999                                              # Sol: 30,550 B through tool_failure before
    make(root, big);make(root, 'child', parent_work_id=big)
    payload = {'view': 'branch', 'id': big}
    try:
        native(root, **payload)
    except Exception as error:   # noqa: BLE001  (the owner refusal)
        refused = error
    before = len(_talk(root))
    value = writing_tools.tool_failure(root, P, 'work', 'project', payload, refused, 'WT-n')
    rows = _talk(root)[before:]
    assert [row['record'] for row in rows] == ['writing-tool-failure'], 'exactly one failure append'
    assert delivery.emitted(value) <= LINE
    assert value['delivery_bound']['projected'] == ['contract'] and 'exceeded' not in value['delivery_bound']
    assert set(value['contract']['omitted']['fields']) <= {'example', 'native'}
    assert value['failure_read'] == {'operation': 'author_history', 'payload': {'view': 'record', 'id': 'activity:journal:' + rows[0]['id']}}
    assert value['failure_receipt']['row_id'] == rows[0]['id']
    recovered = writing_tools.execute(root, P, 'work', value['failure_read']['operation'], value['failure_read']['payload'], 'WT-n')
    assert big in json.dumps(recovered, ensure_ascii=False), 'the exact failure read returns the whole banked request'
    assert value['ok'] is False and 'cannot be delivered within its' in value['error']


def test_an_unbounded_operation_is_never_projected():
    huge = {'contract': {'example': 'x' * 40000}, 'ok': False}
    assert delivery.admit(huge, delivery.profile('source', {'file': 'main.tex'})) is huge
    assert delivery.admit(huge, delivery.profile('project', {'view': 'detail', 'id': 'W'})) is huge


def test_admission_projects_the_production_custody_identities_and_says_so():
    from laplace.representation import writing_bodies as bodies
    custody = {**core_bodies.degradation(), 'status': 'DEGRADED', 'failed_attempts': 3, 'inline_bytes': 120,
               'identities': ['sha256:' + '%064x' % n for n in range(8)], 'identities_omitted': 2}
    receipt = {'id': 'READ-' + 'a' * 32, 'operation': 'project'}
    value = {'children': ['c'] * 10, 'read_receipt': receipt, 'custody_degradation': custody}
    admitted = delivery.admit(value, {'bound': delivery.emitted(value) - 200})
    kept = admitted['custody_degradation']
    assert admitted['delivery_bound']['projected'] == ['custody_degradation'] and 'exceeded' not in admitted['delivery_bound']
    assert 'identities' not in kept and kept['identities_omitted'] == 10 and kept['status'] == 'DEGRADED' and kept['failed_attempts'] == 3
    assert admitted['read_receipt'] == receipt and admitted['children'] == value['children']
    assert admitted['delivery_bound']['emitted'] == delivery.emitted(admitted)


def test_decided_input_and_context_are_never_trimmed_afterwards():
    entry = {'control_id': 'c' * 32, 'sequence': 1, 'message': '界' * 2000, 'message_truncated': False,
             'publication_parts': {'author_request': {'included_chars': 2000, 'total_chars': 2000, 'complete': True}}}
    turn_input = {'status': 'PUBLISHED_AT_TOOL_BOUNDARY', 'delivery_mode': 'project_tool_boundary', 'inputs': [entry]}
    context = {'refreshed': True, 'prompt': 'p' * 3000}
    value = delivery.admit({'ok': True, 'turn_input': turn_input, 'context_refresh': context}, {'bound': 2000})
    assert value['turn_input'] == turn_input and value['context_refresh'] == context
    note = value['delivery_bound']
    assert note['exceeded'] is True and set(note['mandatory']) == {'turn_input', 'context_refresh'} and note['emitted'] == delivery.emitted(value)
    assert not delivery.admissible({'ok': True, 'turn_input': turn_input}, {'bound': 2000})
    assert delivery.fits({'ok': True}, 'turn_input', {'status': 'DEFERRED_AT_TOOL_BOUNDARY'}, {'bound': 2000})


def test_the_planned_refresh_notice_has_the_exact_size_of_any_real_one():
    from laplace.writing import turn_reads
    planned = turn_reads.deferred_refresh('CTX-' + '0' * 32)
    assert delivery.emitted(planned) == delivery.emitted(turn_reads.deferred_refresh('CTX-' + 'f' * 32))


# ------------------------------------------------------------------------------------------------ the context allowance

def test_a_refresh_that_does_not_fit_is_not_adopted_and_banks_nothing(tmp_path, monkeypatch):
    from test_writing_controller import _import_project, _seed_revision
    from laplace.pipeline import authoring
    _import_project(tmp_path)
    turn = _seed_revision(tmp_path, 'fixture', [], selection={'files': ['main.tex']}, context={'context_id': 'CTX-fixture'}, suffix='allow')
    target = {'id': 'AC-target', 'status': 'open'}
    writing_records.bank(tmp_path, {'record': 'writing-tool-read', 'id': 'READ-author-target', 'turn_id': turn, 'project': 'fixture',
                                       'operation': 'author_history', 'payload': {'id': 'AC-target'}, 'output_sha256': reads.output_digest(target)})
    monkeypatch.setattr(authoring, 'inspect', lambda *a, **k: {'stale': [{'context_id': 'CTX-fixture', 'reasons': ['correction-unconsumed:AC-target']}]})
    monkeypatch.setattr(operations, '_execute', lambda *a, **k: target)
    monkeypatch.setattr(operations, '_execute', lambda *a, **k: target)   # the owner call of every replay (the one operation table)
    monkeypatch.setattr(authoring, 'build_context', lambda *a, **k: {'context_id': 'CTX-current', 'dependencies': {}, 'document': {},
                                                                    'consumed': {}, 'science_context_digest': 'science', 'prompt': 'CURRENT'})
    baselines = lambda: [row for row in _talk(tmp_path) if row.get('record') == 'writing-turn-context-baseline' and row.get('cause') == 'explicit-current-reads']
    seen = []
    deferred = turn_reads.refresh_context_after_read(tmp_path, 'fixture', turn, 'author_history', fits=lambda value: seen.append(value) or False)
    assert deferred['refreshed'] is False and deferred['deferred'] is True and baselines() == []
    assert seen and seen[0]['refreshed'] is True, 'the allowance is asked about the exact refresh before anything is banked'
    adopted = turn_reads.refresh_context_after_read(tmp_path, 'fixture', turn, 'author_history', fits=lambda value: True)
    assert adopted == seen[0] and len(baselines()) == 1
