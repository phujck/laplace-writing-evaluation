"""Every part withheld by the transport must still deliver changes on a resume."""
import copy
import json

import pytest

from laplace.writing import operating
from laplace.writing import turn_context
from test_writing_operating import _project


@pytest.mark.parametrize("key", operating.BODY_MEMBERS)
@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_body_change_reaches_resumed_provider_once(tmp_path, key, provider):
    _project(tmp_path)
    before = operating.build("book", "work", tmp_path)
    first = turn_context.without_already_delivered(
        [], {}, brief_delta=(None, before), body_delivered=True)
    blocks = operating.process_instructions(before, provider, resumed=False)
    first_wire = blocks['session_slot'] + blocks['turn_prefix'] + first['prompt']
    # The adapter gives the body once; the controller banks its tokens, not its bytes.
    assert 'LAPLACE OPERATING BRIEF — CHANGED PROJECT STATE' not in first_wire
    assert {part['key'] for part in operating.body_parts(before)} <= set(first['held'])

    after = copy.deepcopy(before)
    if key == 'project_protocol':
        after[key]['documents'] = [{'role': 'instructions', 'text': 'NEW-BODY-CONTENT'}]
    else:
        after[key]['probe'] = 'NEW-BODY-CONTENT'
    delivery = turn_context.without_already_delivered(
        [], first['held'], brief_delta=(turn_context._orientation_snapshot(before), after))
    blocks = operating.process_instructions(after, provider, resumed=True)
    wire = blocks['session_slot'] + blocks['turn_prefix'] + delivery['prompt']
    assert wire.count('NEW-BODY-CONTENT') == 1
    assert 'operating_brief.' + key not in {r['part'] for r in delivery['withheld']}
    assert len(delivery['withheld']) == len(operating.BODY_MEMBERS) - 1

    unchanged = turn_context.without_already_delivered(
        [], delivery['held'], brief_delta=(turn_context._orientation_snapshot(after), after))
    assert 'NEW-BODY-CONTENT' not in unchanged['prompt']
    assert len(unchanged['withheld']) == len(operating.BODY_MEMBERS)


def test_legacy_resume_without_body_tokens_delivers_current_body(tmp_path):
    _project(tmp_path)
    brief = operating.build('book', 'work', tmp_path)
    delivery = turn_context.without_already_delivered(
        [], {}, brief_delta=(turn_context._orientation_snapshot(brief), brief))
    assert delivery['withheld'] == []
    assert len(delivery['held']) == len(operating.BODY_MEMBERS)
    assert set(delivery['delta']['changed']) == set(operating.BODY_MEMBERS)
    assert delivery['prompt'].count(operating.DELTA_HEADER) == 1
