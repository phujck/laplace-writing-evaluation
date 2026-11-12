"""Alias policy is authored; its citation follows the actual normalization."""
from pathlib import Path
import runpy

import pytest


def _check(tmp_path, text):
    owner = tmp_path / 'owner.py'
    owner.write_text(text)
    code = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'tools/writing_verbs/gen_routes.py'))
    return code['check_aliases'](tmp_path, {('section_change', 'create-section'):('create', 'owner.py:change')})


_OWNER = "def change(payload):\n    operation = {'create-section': 'create'}.get(operation, operation)\n"


def test_alias_citation_follows_line_shift_and_ignores_nearby_other_owner(tmp_path):
    first = _check(tmp_path, _OWNER)
    assert first[('section_change', 'create-section')] == ('create', 'owner.py:2')
    nearby = "def other(payload):\n    operation = {'create-section': 'create'}.get(operation, operation)\n\n"
    shifted = _check(tmp_path, nearby + '\n\n' + _OWNER)
    assert shifted[('section_change', 'create-section')] == ('create', 'owner.py:7')


@pytest.mark.parametrize('text', [
    "def change(payload):\n    text = {'create-section': 'create'}.get(operation, operation)\n",
    "def change(payload):\n    if operation == 'elsewhere':\n        operation = {'create-section': 'create'}.get(operation, operation)\n",
    _OWNER.replace("'create'", "'delete'"),
    _OWNER.replace("'create'", 'dynamic_value'),
    _OWNER.replace('operation, operation', 'operation, fallback'),
    _OWNER + "    operation = {'create-section': 'create'}.get(operation, operation)\n",
    _OWNER.replace("'create-section': 'create'", "'create-section': 'create', 'create-section': 'create'"),
])
def test_alias_missing_false_branch_drift_and_ambiguity_refuse(tmp_path, text):
    with pytest.raises(AssertionError):
        _check(tmp_path, text)
