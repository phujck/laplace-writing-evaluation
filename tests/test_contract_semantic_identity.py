"""Source coordinates help inspection without becoming session semantics."""
import dataclasses

from laplace.native import declarations
from laplace.writing import operating as writing_operating


def test_location_only_change_preserves_operating_contract(monkeypatch):
    before_help = declarations.help_payload('source', permitted=True, with_tokens=False)
    before = writing_operating.tool_contract()
    original_site = declarations.dispatch_site
    monkeypatch.setattr(declarations, 'dispatch_site',
                        lambda operation: original_site(operation).rsplit(':', 1)[0] + ':9999')
    after_help = declarations.help_payload('source', permitted=True, with_tokens=False)
    after = writing_operating.tool_contract()
    assert after_help['handler'] != before_help['handler']
    assert before['exact_action_digests'] == after['exact_action_digests']
    assert before['digest'] == after['digest']
    assert before['native_registration_signature'] == after['native_registration_signature']


def test_rule_location_changes_preserve_semantics_but_meaning_changes_do_not(monkeypatch):
    original = declarations.DECLARATIONS['dispatch_plan']
    before = writing_operating.tool_contract()
    moved = dataclasses.replace(original, rules=tuple(
        dataclasses.replace(rule, door='src/laplace/authoring_surface.py:9999')
        for rule in original.rules))
    monkeypatch.setitem(declarations.DECLARATIONS, 'dispatch_plan', moved)
    assert writing_operating.tool_contract()['digest'] == before['digest']
    changed = dataclasses.replace(moved, rules=moved.rules + (
        declarations.Rule('scope', says='The fixture requires a distinct return authority.'),))
    monkeypatch.setitem(declarations.DECLARATIONS, 'dispatch_plan', changed)
    assert writing_operating.tool_contract()['digest'] != before['digest']


def test_source_line_fields_in_operation_inputs_remain_semantic():
    base = {'handler': 'owner.py:1', 'input': {'properties': {'line_start': {'const': 1}}}}
    changed = {'handler': 'owner.py:2', 'input': {'properties': {'line_start': {'const': 2}}}}
    assert declarations.contract_semantics(base) != declarations.contract_semantics(changed)
