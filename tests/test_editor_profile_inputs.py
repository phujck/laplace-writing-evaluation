"""Synthetic reader/editor profile inputs share effective values and exact identity."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from laplace.manuscript import manuscript_source, writing_style
from laplace.work import project_work
from laplace.writing import operating as writing_operating
from laplace.native import tools as writing_tools
from laplace.pipeline import dispatch, narrative, projection_spec


def fixture(root, *, documentclass='article', genre=''):
    manuscript = root / 'book/manuscript'
    manuscript.mkdir(parents=True)
    (manuscript / 'main.tex').write_text(
        '% \\documentclass{book}\n\\documentclass{' + documentclass + '}\n\\begin{document}\nText.\n\\end{document}\n')
    selected = 'profiles/voice/synthetic-selected.md'
    voice = root / selected
    voice.parent.mkdir(parents=True)
    voice.write_text('# Synthetic selected voice\n\n## Current runtime prompt\nUse connected examples.\n')
    (root / writing_style.DEFAULT_PROFILE).write_text('# Unselected default\nDo not substitute this profile.\n')
    (manuscript / 'manuscript_spec.json').write_text(json.dumps({'manuscript': {
        'genre': genre, 'voice_profile': selected}}))
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [{
        'name': 'book', 'kind': 'book', 'project_dir': 'book', 'tex_root': 'book/manuscript',
        'manifest': {'document': {'root': 'book/manuscript/main.tex'}}}]}))
    return manuscript, voice


def architecture(root, summary='Use an explicit explanatory sequence.'):
    path = root / narrative.ARCHITECTURE_PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('profile:\n  narrative_arc:\n    summary: ' + summary + '\n')
    return path


@pytest.mark.parametrize(('documentclass', 'effective'), [
    ('article', 'article'), ('revtex4-2', 'article'), ('memoir', 'book'),
    ('book', 'book'), ('scrreprt', 'report'), ('custom-journal', 'custom')])
def test_effective_genre_agrees_without_authoring_an_override(tmp_path, documentclass, effective):
    manuscript, _ = fixture(tmp_path, documentclass=documentclass)
    before = (manuscript / 'manuscript_spec.json').read_bytes()
    state = writing_style.inspect('book', {}, tmp_path)
    context = writing_style.context('book', tmp_path)
    form, origin = project_work._source_form('book', tmp_path)
    assert state['genre'] == context['authored_genre'] == ''
    assert state['effective_genre'] == context['genre'] == form == effective
    assert state['genre_resolution'] == context['genre_resolution']
    assert origin['origin'] == state['genre_resolution']['origin'] == 'selected-source'
    assert origin['documentclass'] == documentclass
    assert state['profile'] == context['selected_profile'] == 'profiles/voice/synthetic-selected.md'
    assert (manuscript / 'manuscript_spec.json').read_bytes() == before


def test_authored_genre_wins_and_blank_save_keeps_inheritance(tmp_path):
    manuscript, _ = fixture(tmp_path, genre='technical essay')
    first = writing_style.state('book', tmp_path)
    assert first['effective_genre'] == first['genre'] == 'technical essay'
    assert first['genre_resolution']['origin'] == 'manuscript-spec'
    saved = writing_style.save('book', {'profile': first['profile'], 'genre': '',
        'expected_revision': first['revision']}, tmp_path)
    assert saved['genre'] == '' and saved['effective_genre'] == 'article'
    assert json.loads((manuscript / 'manuscript_spec.json').read_text())['manuscript']['genre'] == ''


def test_disjoint_source_changes_keep_genre_identity_but_class_change_moves_it(tmp_path):
    manuscript, _ = fixture(tmp_path)
    first = writing_style.state('book', tmp_path)
    path = manuscript / 'main.tex'
    path.write_text(path.read_text().replace('Text.', 'Independent prose change.'))
    disjoint = writing_style.state('book', tmp_path)
    assert disjoint['revision'] == first['revision']
    assert disjoint['genre_resolution']['source_revision'] != first['genre_resolution']['source_revision']
    path.write_text(path.read_text().replace('{article}', '{book}'))
    changed = writing_style.state('book', tmp_path)
    assert changed['effective_genre'] == 'book' and changed['revision'] != first['revision']
    crossed = manuscript_source.resolve('book', repo_root=tmp_path)
    crossed['project'] = 'other'
    with pytest.raises(ValueError, match='another project'):
        writing_style.effective_genre('book', tmp_path, source=crossed)


def test_architecture_status_separates_absent_invalid_refused_and_available(tmp_path):
    fixture(tmp_path)
    missing = narrative.architecture_status(tmp_path)
    assert missing['status'] == 'ABSENT' and missing['currentness'] == 'UNAVAILABLE'
    assert missing['profile_revision'] is None and missing['field_refs'] == []
    path = architecture(tmp_path)
    summary = narrative.architecture_status(tmp_path)
    exact = narrative.architecture_status(tmp_path, include_content=True)
    assert summary['status'] == 'AVAILABLE' and summary['scope'] == 'workspace'
    assert summary['source'] == {'path': narrative.ARCHITECTURE_PROFILE_PATH, 'origin': 'repository'}
    assert summary['revision'] == exact['revision'] and 'fields' not in summary
    assert summary['read_more'] == {'operation': 'structure', 'payload': {'view': 'architecture-profile'}}
    assert exact['fields']['narrative_arc']['summary'] == 'Use an explicit explanatory sequence.'
    assert narrative.architecture_profile(tmp_path) == exact['fields']
    path.write_text('profile: {}\n')
    invalid = narrative.architecture_status(tmp_path)
    assert invalid['status'] == 'INVALID' and invalid['revision'] != missing['revision']
    assert narrative.architecture_profile(tmp_path) is None
    path.write_text('profile: [unterminated\n')
    assert narrative.architecture_status(tmp_path)['status'] == 'INVALID'
    path.write_text('x' * (narrative.MAX_ARCHITECTURE_BYTES + 1))
    refused = narrative.architecture_status(tmp_path)
    assert refused['status'] == 'REFUSED' and refused['profile_revision'] is None
    path.unlink()
    outside = tmp_path / 'outside.yaml'
    outside.write_text('profile: {}\n')
    path.symlink_to(outside)
    assert narrative.architecture_status(tmp_path)['status'] == 'REFUSED'


def test_architecture_change_has_one_existing_native_body_part_and_exact_read(tmp_path):
    fixture(tmp_path)
    path = architecture(tmp_path)
    before_files = {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    first = writing_operating.build('book', 'work', tmp_path)
    assert first['writing_style']['genre'] == 'article'
    assert first['writing_style']['selected_profile'] == 'profiles/voice/synthetic-selected.md'
    prior = first['architecture_prior']
    assert prior['status'] == 'AVAILABLE' and 'fields' not in prior
    first_part = next(row for row in writing_operating.body_parts(first)
                      if row['key'] == 'operating_brief.architecture_prior')
    assert first_part['read'] == prior['read_more']
    assert len(json.dumps(first_part).encode()) < 8000
    assert {path.relative_to(tmp_path): path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()} == before_files
    path.write_text('profile:\n  narrative_arc:\n    summary: Changed synthetic explanatory prior.\n')
    current = writing_operating.build('book', 'work', tmp_path)
    delta = writing_operating.orientation_delta(first, current)
    assert delta['guidance']['architecture_prior']['revision'] != prior['revision']
    assert 'writing_style' not in delta['guidance']
    changed_part = next(row for row in writing_operating.body_parts(current)
                        if row['key'] == 'operating_brief.architecture_prior')
    assert changed_part['token'] != first_part['token']
    held = writing_operating.body_already_delivered(current)
    assert next(row for row in held if row['part'] == changed_part['key'])['read'] == prior['read_more']
    assert current['architecture_prior']['editable']


@pytest.mark.parametrize('worker', ['structure', 'narrative'])
def test_legacy_planner_consumes_same_architecture_owner_with_explicit_receipt(tmp_path, monkeypatch, worker):
    fixture(tmp_path)
    path = architecture(tmp_path)
    plan = {'sections': [{'id': 'S1', 'job': 'Introduce the question.', 'nodes_in_order': [], 'beats': []}], 'appendices': []}
    project = SimpleNamespace(name='book', kind='book', read_plan=lambda root: plan)
    monkeypatch.setattr(dispatch.registry, 'resolve', lambda *args, **kwargs: project)
    monkeypatch.setattr(dispatch, 'kernel', lambda *args, **kwargs: 'Synthetic kernel')
    monkeypatch.setattr(dispatch, '_inject_form_channel', lambda *args, **kwargs: None)
    monkeypatch.setattr(dispatch, '_inject_standing_rulings', lambda *args, **kwargs: None)
    monkeypatch.setattr(dispatch, '_log_ridden', lambda *args, **kwargs: [])
    monkeypatch.setattr(dispatch.structural, 'seed_contracts', lambda *args, **kwargs: {})
    monkeypatch.setattr(dispatch.structural, 'compute_reader_state', lambda *args, **kwargs: {})
    monkeypatch.setattr(dispatch.structural, 'load_contracts', lambda *args, **kwargs: {'sections': {'S1': {'function': 'Introduce'}}})
    monkeypatch.setattr(projection_spec, 'load_spec', lambda *args, **kwargs: {'manuscript': {}})
    monkeypatch.setattr(projection_spec, 'effective_equation_ledger', lambda *args, **kwargs: {})
    compiled = dispatch._compile_dispatch_core('S1', 'Synthetic goal', worker, 'book', tmp_path)
    assert 'Use an explicit explanatory sequence.' in compiled['prompt']
    assert compiled['profile_inputs']['architecture'] == narrative.architecture_status(tmp_path)
    path.unlink()
    unavailable = dispatch._compile_dispatch_core('S1', 'Synthetic goal', worker, 'book', tmp_path)
    assert 'AUTHOR-ARCHITECTURE' not in unavailable['prompt']
    assert unavailable['profile_inputs']['architecture']['status'] == 'ABSENT'


def test_emitted_architecture_read_is_admitted_by_native_http_and_help(tmp_path):
    from laplace.web import project_work_surface
    from laplace.native import contracts as writing_contracts, verbs as writing_verbs
    fixture(tmp_path)
    architecture(tmp_path)
    observed = narrative.architecture_status(tmp_path)
    handle = observed['read_more']
    native = writing_tools.execute(tmp_path, 'book', 'work', handle['operation'], handle['payload'])
    assert native['profile_revision'] == observed['profile_revision']
    assert native['revision'] == observed['revision']
    assert native['fields']['narrative_arc']['summary'] == 'Use an explicit explanatory sequence.'
    example = writing_verbs.native_example(handle['operation'], handle['payload'], project='book', root=tmp_path)
    assert example['native_request']['payload']['view'] == 'architecture-profile'
    _route, request = writing_verbs.from_owner_call(handle['operation'], handle['payload'], project='book', root=tmp_path)
    generic = writing_tools.request(tmp_path, 'book', 'work', request)
    assert generic['outcome'] == 'read' and generic['owner_response'] == native
    code, _, raw = project_work_surface.handle('/work/structure', {
        'project': ['book'], 'view': ['architecture-profile']}, 'GET', repo_root=tmp_path)
    assert code == 200 and json.loads(raw) == native
    schema = writing_contracts.exact_contract('structure', permitted=True)['input']
    from jsonschema import Draft202012Validator
    assert not list(Draft202012Validator(schema).iter_errors(handle['payload']))
    with pytest.raises(ValueError, match='Additional properties|no selection or override'):
        writing_tools.execute(tmp_path, 'book', 'work', 'structure', {
            **handle['payload'], 'files': ['book/manuscript/main.tex']})


def test_architecture_semantic_revision_ignores_unconsumed_yaml_metadata(tmp_path):
    fixture(tmp_path)
    path = architecture(tmp_path)
    first = narrative.architecture_status(tmp_path)
    path.write_text('# Independent formatting note\nmetadata: another-source-description\n' + path.read_text())
    formatted = narrative.architecture_status(tmp_path)
    assert formatted['profile_revision'] != first['profile_revision']
    assert formatted['revision'] == first['revision']
    path.write_text(path.read_text().replace('explicit explanatory sequence', 'different explanatory sequence'))
    changed = narrative.architecture_status(tmp_path)
    assert changed['revision'] != first['revision']


def test_original_native_snapshot_does_not_announce_unchanged_prior_again(tmp_path):
    from laplace.writing import turn_context
    fixture(tmp_path)
    architecture(tmp_path)
    first = writing_operating.build('book', 'work', tmp_path)
    snapshot = turn_context._orientation_snapshot(first)
    assert snapshot['architecture_prior']['revision'] == first['architecture_prior']['revision']
    assert writing_operating.orientation_delta(snapshot, first) == {'changed': False, 'guidance': {}}


def test_authoring_prompt_uses_same_inherited_genre_as_profile_reader(tmp_path):
    from laplace.pipeline import authoring
    fixture(tmp_path)
    context = authoring.build_context('book', {'files': ['main.tex']}, tmp_path)
    assert 'Current manuscript genre: article' in context['prompt']
    assert context['consumed']['writing_style']['selected_profile'] == 'profiles/voice/synthetic-selected.md'


def test_profile_inheritance_does_not_discover_unrelated_source_candidates(tmp_path, monkeypatch):
    fixture(tmp_path)
    monkeypatch.setattr(manuscript_source, '_candidate_rows', lambda *args: pytest.fail('unrelated source discovery'))
    value = writing_style.inspect('book', {}, tmp_path)
    assert value['effective_genre'] == 'article'


def test_existing_voice_mutations_do_not_acquire_architecture_write_authority(tmp_path):
    _, voice = fixture(tmp_path)
    prior = architecture(tmp_path)
    before = {voice: voice.read_bytes(), prior: prior.read_bytes()}
    current = writing_style.state('book', tmp_path)
    with pytest.raises(ValueError, match='profiles/voice'):
        writing_style.save('book', {'profile': narrative.ARCHITECTURE_PROFILE_PATH,
            'expected_revision': current['revision']}, tmp_path)
    with pytest.raises(ValueError, match='currently selected profile'):
        writing_style.update_profile('book', {'profile': narrative.ARCHITECTURE_PROFILE_PATH,
            'content': '# A rejected cross-family edit', 'expected_profile_revision': current['profile_revision'],
            'basis': 'author_preference', 'reason': 'Synthetic scope check',
            'provenance_kind': 'structured-author-edit'}, tmp_path)
    assert {path: path.read_bytes() for path in before} == before
