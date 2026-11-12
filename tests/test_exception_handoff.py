"""The exception-to-failure handoff keeps the admitted act (exception-handoff grant 2026-10-19; Sol DC-R1, DC-N1).

An ordinary owner exception that escapes writing_tools.call carries the invocation's admitted act, cut and reserved
forms on itself; the transport's existing tool_failure (the Codex adapter's handoff, replicated here line for line)
finishes that act, whatever spelling it caught the exception under. The author offer banks the original authoring
cut as its provenance. Real owners in synthetic tmp roots.
"""
from __future__ import annotations

import json

import pytest

from laplace.writing import provider_updates as updates
from laplace.native import tools as writing_tools, verbs as writing_verbs
from laplace.writing import operations
from laplace.writing import delivery
from test_provider_update_join import _running_input, clear, seed  # noqa: F401  (clear is the autouse cache fixture)
from test_shared_input_publication import BOUND, PARENT, _control, _frontier, _input_rows, _rows, _tree

BRANCH = {'view': 'branch', 'id': PARENT}


def _spelled(spelling, payload):
    if spelling == 'named':
        return {'operation': 'project', 'payload': payload}
    example = writing_verbs.native_example('project', payload, project='p')
    assert example['available'], example
    return example['native_request']


def _adapter_handoff(root, fields, turn_id):
    """writing_provider's tool_call handoff (src/laplace/writing/provider.py: call, then tool_failure with the fields it
    caught the exception under), without a provider."""
    operation, payload = fields.get('operation'), fields.get('payload') or {}
    try:
        return writing_tools.call(root, 'p', 'work', fields, turn_id=turn_id), None
    except Exception as exc:   # noqa: BLE001  (the adapter catches everything the same way)
        return None, writing_tools.tool_failure(root, 'p', 'work', operation, payload, exc, turn_id, provider='codex')


def _owner_raises(monkeypatch, error):
    original = operations._execute

    def failing(*a, **k):
        if a[3] == 'project':
            raise error
        return original(*a, **k)
    monkeypatch.setattr(operations, '_execute', failing)
@pytest.mark.parametrize('spelling', ['named', 'semantic'])
def test_an_owner_oserror_finishes_the_same_admitted_act_under_both_spellings(tmp_path, monkeypatch, spelling):
    _running_input(tmp_path, monkeypatch, {'text': '界' * 1500})
    _tree(tmp_path)
    _owner_raises(monkeypatch, OSError('disk gone during the read'))
    before = len(_rows(tmp_path))
    result, recovery = _adapter_handoff(tmp_path, _spelled(spelling, BRANCH), 'T')
    assert result is None and recovery['ok'] is False and recovery['operation'] == 'project'
    assert 'disk gone during the read' in recovery['error']
    rows = [row for row in _rows(tmp_path)[before:] if row['record'] == 'writing-tool-failure']
    assert len(rows) == 1 and rows[0]['operation'] == 'project' and rows[0]['error_type'] == 'OSError' and rows[0]['provider'] == 'codex'
    assert recovery['failure_read'] == {'operation': 'author_history', 'payload': {'view': 'record', 'id': 'activity:journal:' + rows[0]['id']}}
    assert delivery.emitted(recovery) <= BOUND and 'exceeded' not in (recovery.get('delivery_bound') or {})
    assert recovery['turn_input']['status'] in {'PUBLISHED_AT_TOOL_BOUNDARY', 'DEFERRED_AT_TOOL_BOUNDARY'}
    read = writing_tools.execute(tmp_path, 'p', 'work', recovery['failure_read']['operation'], recovery['failure_read']['payload'], 'T')
    assert PARENT in json.dumps(read, ensure_ascii=False), 'the exact failure read returns the admitted request'


def test_the_two_spellings_bank_the_same_failure_identity_and_profile(tmp_path, monkeypatch):
    seen = {}
    for spelling in ('named', 'semantic'):
        root = tmp_path / spelling;root.mkdir()
        seed(root, monkeypatch);_tree(root)
        _owner_raises(monkeypatch, OSError('disk gone'))
        _result, recovery = _adapter_handoff(root, _spelled(spelling, BRANCH), 'T')
        row = next(r for r in _rows(root) if r['record'] == 'writing-tool-failure')
        seen[spelling] = {'operation': row['operation'], 'error_type': row['error_type'], 'recovery_operation': recovery['operation'],
                          'bounded': delivery.emitted(recovery) <= BOUND, 'failure_read': recovery['failure_read']['operation'],
                          'verb': row.get('verb'), 'concept': row.get('concept')}
    assert seen['named'] == seen['semantic'] and seen['named']['operation'] == 'project'


def test_a_handled_valueerror_still_returns_the_refusal_without_a_handoff(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch);_tree(tmp_path)
    _owner_raises(monkeypatch, ValueError('owner says no'))
    result, recovery = _adapter_handoff(tmp_path, _spelled('semantic', BRANCH), 'T')
    assert recovery is None and result['ok'] is False and 'refused' in result and result['failure_read']['operation'] == 'author_history'
    assert sum(r['record'] == 'writing-tool-failure' for r in _rows(tmp_path)) == 1 and delivery.emitted(result) <= BOUND


def test_a_failed_read_offers_only_the_cut_it_carried(tmp_path, monkeypatch):
    _turn, control = _running_input(tmp_path, monkeypatch, {'text': 'Short input'})
    _tree(tmp_path)
    _owner_raises(monkeypatch, OSError('disk gone'))
    _result, recovery = _adapter_handoff(tmp_path, _spelled('semantic', BRANCH), 'T')
    assert delivery.carried(OSError('x')) is None
    assert recovery['turn_input']['status'] == 'PUBLISHED_AT_TOOL_BOUNDARY' and recovery['turn_input']['inputs'][0]['control_id'] == control['control_id']
    assert _control(tmp_path, control['control_id'])['state'] == 'PUBLISHED_AT_TOOL_BOUNDARY' and _frontier(tmp_path) == 1


def test_an_exception_outside_any_call_carries_nothing_and_the_act_does_not_leak(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch);_tree(tmp_path)
    _owner_raises(monkeypatch, OSError('disk gone'))
    _result, recovery = _adapter_handoff(tmp_path, _spelled('semantic', BRANCH), 'T')
    assert recovery['operation'] == 'project'
    assert delivery.current_act() is None and delivery.carried(OSError('fresh')) is None
    plain = writing_tools.tool_failure(tmp_path, 'p', 'work', 'project', {'view': 'roots'}, OSError('direct'), 'T')
    assert plain['operation'] == 'project' and plain['ok'] is False


def test_the_author_offer_banks_the_original_authoring_cut(tmp_path, monkeypatch):
    seed(tmp_path, monkeypatch)
    _state, _source, cut = updates.correction_snapshot(tmp_path, 'p')
    offer = updates.author_offer(tmp_path, 'p', 'T', bank=False)
    banked = updates.author_offer(tmp_path, 'p', 'T', eligible=offer['correction_ids'])
    rows = [row for row in _rows(tmp_path) if row.get('record') == 'writing-author-update-delivery']
    assert banked['correction_ids'] == offer['correction_ids'] and len(rows) == 1
    assert rows[0]['authoring_cut'] == cut and rows[0]['authoring_cut'] != sorted(offer['correction_ids']), 'the snapshot cut, not the eligibility set'
