"""Real owner recipes for the two provider refusals; no provider/network required."""
import hashlib
import json

import pytest

from laplace.core import grammar
from laplace.manuscript import manuscript_structure, review_surface
from laplace.writing import operations
from laplace.native import declarations, tools as writing_tools, verbs as writing_verbs
from laplace.pipeline import authoring
from test_manuscript_structure import _section_fixture
from test_writing_controller import _import_project, _seed_revision


def _edit():
    return {'edits': [{'file': 'main.tex', 'line_start': 3, 'line_end': 3,
                      'before': 'Original prose.', 'after': 'Revised prose.'}]}


@pytest.mark.parametrize('wrapped', [False, True])
def test_native_expected_refuses_before_owner_and_does_not_drop_token(tmp_path, monkeypatch, wrapped):
    proposal = _edit()
    payload = {'proposal': proposal} if wrapped else proposal
    payload['expected'] = [str(grammar.mint('source-file', 'fixture::main.tex', 'a' * 64))]
    monkeypatch.setattr(operations, '_execute', lambda *a, **kw: pytest.fail('owner reached'))
    with pytest.raises(declarations.PayloadAdmissionError, match='recorded current-turn source reads'):
        writing_tools.execute(tmp_path, 'fixture', 'work', 'apply_revision', payload)
    help_value = declarations.help_payload('apply_revision', permitted=True)
    assert 'expected' not in help_value
    schema_section = declarations.help_payload('apply_revision', permitted=True, section='input')   # compact help: the schema is a sectioned read
    assert '"expected"' not in json.dumps(schema_section['value'])
    assert help_value['source_write_recipe']['caller_expected'] is False


def test_unified_expected_refuses_before_codec(tmp_path, monkeypatch):
    route = writing_verbs.BY_OPERATION['apply_revision'][0]
    request = grammar.Request(verb=route.verb, concept=route.concept, target='fixture',
        expected=(str(grammar.mint('prose', 'fixture::main.tex:3-3', 'a' * 64)),), payload=_edit())
    monkeypatch.setattr(writing_verbs, 'to_owner_call', lambda *a, **kw: pytest.fail('codec reached'))
    with pytest.raises(declarations.PayloadAdmissionError, match='recorded current-turn source reads'):
        declarations.validate_request_payload(request, route, project='fixture')


@pytest.mark.parametrize('stale', [False, True])
def test_read_recipe_expected_free_unified_apply_preserves_consumed_basis(tmp_path, monkeypatch, stale):
    source, _ = _import_project(tmp_path)
    proposal = _edit()
    turn = _seed_revision(tmp_path, 'fixture', proposal['edits'], selection={'files': ['main.tex']})
    monkeypatch.setattr(review_surface, '_repo_root', lambda: tmp_path)
    read = writing_tools.execute(tmp_path, 'fixture', 'work', 'source', {'files': ['main.tex']}, turn_id=turn)
    assert read['source_write_recipe'] == declarations.source_write_guidance()
    assert read['sources'][0]['identities']  # Provenance remains, even though apply consumes reads.
    if stale:
        (source / 'main.tex').write_text((source / 'main.tex').read_text().replace('Original prose.', 'External prose.'))
    route, request = writing_verbs.from_owner_call('apply_revision', proposal, project='fixture', root=tmp_path)
    assert not request.expected
    result = writing_tools.request(tmp_path, 'fixture', 'work', request, turn_id=turn)
    if stale:
        assert result.get('ok') is False or result.get('status') == 'refused', result
        assert 'External prose.' in (source / 'main.tex').read_text()
        assert 'Revised prose.' not in (source / 'main.tex').read_text()
    else:
        assert result['owner_response']['source_effect']['state'] == 'COMMITTED', result
        assert result['owner_response']['source_effect']['complete']
        assert 'Revised prose.' in (source / 'main.tex').read_text()


@pytest.mark.parametrize('operation,value', [
    ('section_change', 'convert'), ('section_change', 'insert-heading'),
    ('block_change', 'insert-at-caret'), ('block_change', 'undo'),
    ('project_guidance_change', 'configure'), ('project_guidance_change', 'write'),
])
def test_recovery_resolver_uses_declared_outer_discriminator(operation, value):
    result = declarations.supported_suboperation(operation, {'operation': value})
    assert result['supported'] and value in result['choices']
    assert not declarations.supported_suboperation(operation, {'nested': {'operation': value}})['supported']
    bad = declarations.supported_suboperation(operation, {'operation': 'made-up'})
    assert not bad['supported'] and value in bad['choices']


@pytest.mark.parametrize('operation', ['create', 'convert'])
@pytest.mark.parametrize('plan_home', ['plan', 'plan-file'])
def test_generated_section_example_executes_with_observed_plan_and_source(tmp_path, operation, plan_home):
    manuscript, chapter, _ = _section_fixture(tmp_path)
    # A separated whole prose paragraph is a supported conversion target.
    chapter.write_text('\\chapter{First}\n\nWhole prose paragraph.\n\nFollowing prose.\n')
    path = chapter.relative_to(tmp_path).as_posix()
    state = manuscript_structure._structure_state('book', tmp_path)
    digest = 'sha256:' + hashlib.sha256(chapter.read_bytes()).hexdigest()
    payload = declarations.generated_example('section_change', variant=operation,
        project='book', root=tmp_path, payload={'source_file': path})
    payload.update(title='New heading', kind='section', source_file=path)
    if operation == 'create':
        payload.update(after_line=1, after_before='\\chapter{First}')
    else:
        payload['replacement'] = {'line_start': 3, 'line_end': 3, 'before': 'Whole prose paragraph.'}
    # Both published plan identities are accepted; never substitute one for source.
    plan_digest = state['revision'] if plan_home == 'plan' else state['authority']['plan_revision']
    payload.pop('expected_source_digest', None)
    payload.pop('expected_plan_revision', None)
    payload['expected'] = [str(grammar.mint('source-file', 'book::' + path, digest)),
                           str(grammar.mint(plan_home, 'book', plan_digest))]
    declarations.validate_owner_payload('section_change', payload, project='book')
    result = writing_tools.execute(tmp_path, 'book', 'work', 'section_change', payload)
    assert result['source_effect']['complete'], result
    assert '\\section{' in chapter.read_text()


def test_planned_create_missing_plan_guard_refuses_and_source_only_needs_none(tmp_path):
    planned = tmp_path / 'planned'; planned.mkdir()
    _, chapter, _ = _section_fixture(planned)
    payload = {'operation': 'create', 'kind': 'section', 'title': 'New heading',
               'source_file': chapter.relative_to(planned).as_posix(), 'after_line': 0,
               'expected_source_digest': hashlib.sha256(chapter.read_bytes()).hexdigest()}
    before = chapter.read_bytes()
    declarations.validate_owner_payload('section_change', payload, project='book')
    with pytest.raises(ValueError, match='plan|revision|guard'):
        writing_tools.execute(planned, 'book', 'work', 'section_change', payload)
    assert chapter.read_bytes() == before

    unbound = tmp_path / 'source-only'; unbound.mkdir()
    source, _ = _import_project(unbound)
    payload.update(source_file='sources/fixture/main.tex',
                   expected_source_digest=hashlib.sha256((source / 'main.tex').read_bytes()).hexdigest(),
                   after_line=2, after_before='\\begin{document}')
    result = writing_tools.execute(unbound, 'fixture', 'work', 'section_change', payload)
    assert result['source_effect']['complete'], result


def test_existing_heading_is_not_convert_and_help_recipe_is_current(tmp_path):
    _, chapter, _ = _section_fixture(tmp_path)
    state = manuscript_structure._structure_state('book', tmp_path)
    payload = {'operation': 'convert', 'kind': 'chapter', 'title': 'Renamed',
               'source_file': chapter.relative_to(tmp_path).as_posix(),
               'expected_source_digest': hashlib.sha256(chapter.read_bytes()).hexdigest(),
               'expected_plan_revision': state['revision'],
               'replacement': {'line_start': 1, 'line_end': 1, 'before': '\\chapter{First}'}}
    with pytest.raises(ValueError, match='whole prose paragraph') as failed:
        writing_tools.execute(tmp_path, 'book', 'work', 'section_change', payload)
    response = writing_tools.failure_response(tmp_path, 'book', 'work', 'section_change', payload, failed.value)
    assert response['contract']['selected_variant'] == 'convert'
    assert 'unknown_suboperation' not in response['contract']
    assert 'apply_revision' in response['contract']['does']


def test_source_read_and_both_help_recipes_publish_same_schema_derived_envelope(tmp_path):
    _import_project(tmp_path)
    source = writing_tools.execute(tmp_path, 'fixture', 'work', 'source', {'files': ['main.tex']})
    source_help = writing_tools.execute(tmp_path, 'fixture', 'work', 'help', {'operation': 'source'})
    apply_help = writing_tools.execute(tmp_path, 'fixture', 'work', 'help', {'operation': 'apply_revision'})
    recipe = source['source_write_recipe']
    assert recipe == source_help['action']['source_write_recipe']
    assert recipe == apply_help['action']['source_write_recipe']
    write = recipe['write']
    assert write['operation'] == 'apply_revision'
    assert write['payload'] == declarations.generated_example('apply_revision')
    assert set(write['payload']) == {'edits'}
    assert set(write['payload']['edits'][0]) == {'file', 'line_start', 'line_end', 'before', 'after'}
    assert 'expected' not in write['payload']
    declarations.validate_owner_payload('apply_revision', write['payload'], project='fixture')
    with pytest.raises(declarations.PayloadAdmissionError):
        declarations.validate_owner_payload('apply_revision', write['payload']['edits'][0], project='fixture')
