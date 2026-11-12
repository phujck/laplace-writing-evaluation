"""Research evidence files show each input in its declared scope (WORK-editor-research-evidence-scope-20261016).

Reached case: result dd-memory-reader-controls declares data_scope=project and its producer snapshot agrees, but the
evidence-files view listed the same input twice: a MISSING manuscript "Input data" and a PRESENT project "Producer
input". The view now reads research_records.dependency_rows, the scope currentness already uses. Archived result
bytes are not touched and nothing is executed. Disposable fixtures only.
"""
from __future__ import annotations

import json

from laplace.research import research_records
from laplace.research import research_catalogue
from test_research_surface import _project


def _record(tmp_path, **fields):
    status, created = research_records.record('fixture', {'kind': 'result', 'id': 'result:scoped', 'result': 'result.json',
                                           'summary': 'Scoped inputs.', **fields}, tmp_path)
    assert status == 201, created
    return next(row for row in research_catalogue.state_payload('fixture', tmp_path)['results'] if row['id'] == 'result:scoped')


def _files(shown):
    return [(row['role'], row['path'], row['scope'], row.get('availability')) for row in shown['evidence_files']]


def test_a_project_scoped_input_is_shown_present_in_its_own_scope_not_missing_in_the_manuscript(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"ok": true}')
    (tmp_path / 'fixture' / 'inputs').mkdir()
    (tmp_path / 'fixture' / 'inputs' / 'controls.json').write_text('[1]')
    shown = _record(tmp_path, data=['inputs/controls.json'], data_scope='project')
    assert ('Input data', 'inputs/controls.json', 'project', 'PRESENT') in _files(shown)
    assert not [row for row in _files(shown) if row[1] == 'inputs/controls.json' and row[3] == 'MISSING']
    assert shown['currentness'] == 'CURRENT'


def test_mixed_scopes_keep_true_missing_and_present_distinctions(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"ok": true}')
    (tmp_path / 'fixture' / 'shared.json').write_text('[2]')
    shown = _record(tmp_path, data=['shared.json'], data_scope='project', config='config.json', config_scope='manuscript')
    files = _files(shown)
    assert ('Input data', 'shared.json', 'project', 'PRESENT') in files
    assert ('Configuration', 'config.json', 'manuscript', 'PRESENT') in files
    (tmp_path / 'fixture' / 'shared.json').unlink()
    files = _files(next(row for row in research_catalogue.state_payload('fixture', tmp_path)['results'] if row['id'] == 'result:scoped'))
    assert ('Input data', 'shared.json', 'project', 'MISSING') in files, 'a genuinely missing project input stays missing'


def test_records_without_field_scopes_keep_their_record_scope(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"ok": true}')
    shown = _record(tmp_path, data=['data.json'])
    assert ('Input data', 'data.json', 'manuscript', 'PRESENT') in _files(shown)


def test_each_field_takes_its_own_scope_over_the_record_default(tmp_path):
    """config/source/result each read <field>_scope (not only data): a project-scoped configuration is shown present
    in the project, never as a missing manuscript file."""
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"ok": true}')
    (tmp_path / 'fixture' / 'settings.json').write_text('{"n": 3}')
    shown = _record(tmp_path, config='settings.json', config_scope='project')
    files = _files(shown)
    assert ('Configuration', 'settings.json', 'project', 'PRESENT') in files
    assert not [row for row in files if row[1] == 'settings.json' and row[2] == 'manuscript']


def test_a_result_home_is_obtained_through_its_research_catalogue_owner(tmp_path):
    """core.grammar's result home reads its one owner, research_catalogue.state_payload (the /research door re-exports
    nothing since 2026-10-21): the obtained token is the owner's own published revision, and an id the owner does
    not publish is refused rather than minted."""
    import pytest
    from laplace.core import grammar as g
    manuscript = _project(tmp_path)
    (manuscript / 'result.json').write_text('{"ok": true}')
    row = _record(tmp_path)
    assert g.OWNER_READS['result'].module == 'laplace.research.research_catalogue'
    token = g.identity(g.Home('result', 'fixture::result:scoped'), project='fixture', root=tmp_path)
    assert token == g.mint('result', 'fixture::result:scoped', row['revision'])
    with pytest.raises(ValueError, match='does not exist in this project'):
        g.identity(g.Home('result', 'fixture::result:absent'), project='fixture', root=tmp_path)


def test_every_owner_read_names_a_callable_owner_binding():
    """Every dynamic owner read the grammar resolves by (module, function) names a real callable binding, so no
    home can fail at obtain time on a retired facade export."""
    import importlib
    from laplace.core import grammar as g
    missing = [(kind, spec.module, spec.func) for kind, spec in sorted(g.OWNER_READS.items())
               if not callable(getattr(importlib.import_module(spec.module), spec.func, None))]
    assert missing == [] and len(g.OWNER_READS) >= 31
