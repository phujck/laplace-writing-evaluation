"""Real profile consumers under tiny explicit roots; no shared manuscript/state."""
import json
import hashlib
from pathlib import Path

import pytest

from laplace.manuscript import writing_style
from laplace.writing import records
from laplace.pipeline import narrative
from laplace.manuscript import profiles
from laplace.writing import records


def fixture(root):
    manuscript = root / 'book/manuscript'
    manuscript.mkdir(parents=True)
    (manuscript / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}Text.\\end{document}\n')
    (manuscript / 'manuscript_spec.json').write_text(json.dumps({'manuscript': {'genre': 'article'}}))
    other = root / 'other/manuscript'
    other.mkdir(parents=True)
    (other / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}Other.\\end{document}\n')
    (other / 'manuscript_spec.json').write_text(json.dumps({'manuscript': {'genre': 'article'}}))
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [{
        'name': 'book', 'project_dir': 'book', 'tex_root': 'book/manuscript',
        'plan_path': 'book/manuscript/projection_plan.json', 'target_dir': 'book/manuscript',
        'manifest': {'document': {'root': 'book/manuscript/main.tex'}}}, {
        'name': 'other', 'project_dir': 'other', 'tex_root': 'other/manuscript',
        'manifest': {'document': {'root': 'other/manuscript/main.tex'}}}]}))
    voice = root / writing_style.DEFAULT_PROFILE
    voice.parent.mkdir(parents=True)
    voice.write_text('# Voice\nKeep the argument concrete.\n')
    records.bank(root, {'record': 'writing-turn', 'id': 'WT-profile-test', 'project': 'book',
        'session_id': 'WS-profile-test', 'status': 'running'})
    return manuscript, voice


def architecture_content(summary='Open with the question.', observation='Observed order.'):
    return json.dumps({'version': 'fixture-v1', 'profile': {'introduction_shape': {
        'summary': summary, 'evidence': {'sources': ['fixture-source'], 'observation': observation}},
        'section_rhythm': {'summary': 'Keep derivations explicit.'}}})


def propose(root, family='architecture', scope='workspace', change=None, actor=None):
    current = profiles.inspect('book', {'family': family, 'scope': scope}, root)
    return profiles.change('book', {'action': 'propose', 'family': family, 'scope': scope,
        'guards': {'profile_input_revision': current['revision']}, 'reason': 'Test scoped preference.',
        'change': change or {'content': architecture_content()}}, root, actor=actor)


def test_generated_architecture_is_exact_immutable_candidate_applied_by_actual_owner(tmp_path):
    fixture(tmp_path)
    before = narrative.architecture_status(tmp_path)
    candidate = propose(tmp_path, actor={'kind': 'agent', 'turn_id': 'WT-profile-test'})
    assert before['status'] == narrative.architecture_status(tmp_path)['status'] == 'ABSENT'
    ref = candidate['candidate_ref']
    assert candidate['author'] == {'kind': 'agent', 'turn_id': 'WT-profile-test'}
    assert 'content' not in candidate and 'content' not in candidate['apply_action']['payload']
    proposed = profiles.inspect('book', {'view': 'candidate', 'candidate_ref': ref, 'part': 'proposed'}, tmp_path)
    assert json.loads(proposed['content'])['profile']['introduction_shape']['summary'] == 'Open with the question.'
    result = profiles.change('book', {'action': 'apply', 'candidate_ref': ref}, tmp_path)
    assert result['application_id']
    assert narrative.architecture_profile(tmp_path)['introduction_shape']['summary'] == 'Open with the question.'
    assert not narrative.architecture_profile(tmp_path)['introduction_shape']['confirmed_his']
    retained = profiles.inspect('book', {'view': 'candidate', 'candidate_ref': ref, 'part': 'proposed'}, tmp_path)
    assert retained['content'] == proposed['content']
    assert records.index(tmp_path).turns.keys() == {'WT-profile-test'}
    with pytest.raises(ValueError, match='immutable'):
        profiles.inspect('book', {'view': 'candidate', 'candidate_ref': {**ref, 'version': 'sha256:' + '0' * 64}}, tmp_path)
    with pytest.raises(ValueError, match='missing|ambiguous'):
        profiles.inspect('other', {'view': 'candidate', 'candidate_ref': ref}, tmp_path)


def test_marker_prose_is_historical_and_explicit_human_confirmation_pins_full_fields(tmp_path):
    fixture(tmp_path)
    candidate = propose(tmp_path, change={'content': architecture_content('HIS CORRECTION confirmed-his: open with the question.')})
    profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    current = profiles.inspect('book', {'family': 'architecture', 'scope': 'workspace'}, tmp_path)
    fields = narrative.architecture_profile(tmp_path)
    assert fields['introduction_shape']['historical_confirmation_assertion']
    assert not fields['introduction_shape']['confirmed_his']
    confirm = {'action': 'confirm', 'family': 'architecture', 'scope': 'workspace',
        'fields': ['introduction_shape'], 'guards': {'profile_input_revision': current['revision']}, 'reason': 'I confirm this field.'}
    with pytest.raises(ValueError, match='explicit human'):
        profiles.change('book', confirm, tmp_path, actor={'kind': 'agent', 'turn_id': 'WT-profile-test'})
    profiles.change('book', confirm, tmp_path)
    assert narrative.architecture_profile(tmp_path)['introduction_shape']['confirmed_his']
    assert not narrative.architecture_profile(tmp_path)['section_rhythm']['confirmed_his']
    # A generation cannot keep confirmation by repeating the same summary
    # while changing its evidence or qualification.
    before = profiles.inspect('book', {'family': 'architecture', 'scope': 'workspace', 'view': 'content'}, tmp_path)
    data = json.loads(before['content'])
    data['profile']['introduction_shape']['evidence']['observation'] = 'Different evidence.'
    changed = propose(tmp_path, change={'content': json.dumps(data)})
    profiles.change('book', {'action': 'apply', 'candidate_ref': changed['candidate_ref']}, tmp_path)
    assert not narrative.architecture_profile(tmp_path)['introduction_shape']['confirmed_his']


def test_unchanged_confirmed_field_survives_disjoint_profile_change(tmp_path):
    fixture(tmp_path)
    candidate = propose(tmp_path)
    profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    current = profiles.inspect('book', {'family': 'architecture', 'scope': 'workspace'}, tmp_path)
    profiles.change('book', {'action': 'confirm', 'family': 'architecture', 'scope': 'workspace',
        'fields': ['introduction_shape'], 'guards': {'profile_input_revision': current['revision']}, 'reason': 'Confirmed introduction.'}, tmp_path)
    data = json.loads(profiles.inspect('book', {'family': 'architecture', 'scope': 'workspace', 'view': 'content'}, tmp_path)['content'])
    data['profile']['section_rhythm']['summary'] = 'A different rhythm.'
    candidate = propose(tmp_path, change={'content': json.dumps(data)})
    profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    assert narrative.architecture_profile(tmp_path)['introduction_shape']['confirmed_his']
    assert not narrative.architecture_profile(tmp_path)['section_rhythm']['confirmed_his']


def test_concurrent_architecture_change_refuses_and_preserves_generated_draft(tmp_path):
    fixture(tmp_path)
    candidate = propose(tmp_path)
    path = tmp_path / narrative.ARCHITECTURE_PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(architecture_content('Concurrent preference.'))
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    retained = profiles.inspect('book', {'view': 'candidate', 'candidate_ref': candidate['candidate_ref'], 'part': 'proposed'}, tmp_path)
    assert 'Open with the question.' in retained['content']
    assert narrative.architecture_profile(tmp_path)['introduction_shape']['summary'] == 'Concurrent preference.'


def test_architecture_candidate_pins_exact_bytes_even_when_effective_fields_do_not_change(tmp_path):
    fixture(tmp_path)
    first = propose(tmp_path)
    profiles.change('book', {'action': 'apply', 'candidate_ref': first['candidate_ref']}, tmp_path)
    candidate = propose(tmp_path, change={'content': architecture_content('A revised opening.')})
    path = tmp_path / narrative.ARCHITECTURE_PROFILE_PATH
    effective = narrative.architecture_status(tmp_path)['revision']
    path.write_text('# Concurrent metadata comment.\n' + path.read_text())
    assert narrative.architecture_status(tmp_path)['revision'] == effective
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)


def test_voice_workspace_and_project_changes_reach_separate_real_consumers(tmp_path):
    manuscript, voice = fixture(tmp_path)
    project_before = (manuscript / 'manuscript_spec.json').read_bytes()
    candidate = propose(tmp_path, 'voice', 'workspace', {'content': '# Generated voice\nName concrete mechanisms.\n'},
        actor={'kind': 'agent', 'turn_id': 'WT-profile-test'})
    profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    assert 'Name concrete mechanisms.' in writing_style.context('book', tmp_path)['content']
    assert 'Name concrete mechanisms.' in writing_style.context('other', tmp_path)['content']
    assert (manuscript / 'manuscript_spec.json').read_bytes() == project_before
    profile_before = voice.read_bytes()
    candidate = propose(tmp_path, 'voice', 'project', {'guidance': 'Explain this book through worked examples.', 'genre': 'book'})
    profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    assert writing_style.state('book', tmp_path)['guidance'] == 'Explain this book through worked examples.'
    assert writing_style.state('book', tmp_path)['genre'] == 'book'
    assert writing_style.state('other', tmp_path)['guidance'] == ''
    assert writing_style.state('other', tmp_path)['genre'] == 'article'
    assert voice.read_bytes() == profile_before
    rows = [json.loads(line) for line in (tmp_path / 'contract/talk.jsonl').read_text().splitlines()]
    intents = [row for row in rows if row.get('record') == 'voice-profile-change-intent']
    assert intents[-1]['basis'] == 'reviewed_preference'
    assert intents[-1]['provenance_kind'] == 'reviewed-profile-candidate'
    assert all(row.get('decision') != 'confirm-profile' for row in rows)


def test_profile_byte_race_and_new_project_selection_race_are_refused(tmp_path):
    _, voice = fixture(tmp_path)
    workspace = propose(tmp_path, 'voice', 'workspace', {'content': '# Candidate\nNew preference.\n'})
    voice.write_text('# Concurrent\nPreserve this preference.\n')
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': workspace['candidate_ref']}, tmp_path)
    alternate = voice.with_name('alternate.md'); alternate.write_text('# Alternate\nWrite plainly.\n')
    project = propose(tmp_path, 'voice', 'project', {'profile': alternate.relative_to(tmp_path).as_posix()})
    alternate.write_text('# Changed alternate\nOther preference.\n')
    with pytest.raises(ValueError, match='selected voice profile changed'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': project['candidate_ref']}, tmp_path)


def test_candidate_application_recovers_tracking_failure_without_rewriting(tmp_path, monkeypatch):
    fixture(tmp_path)
    candidate = propose(tmp_path)
    bank = records.bank
    def fail_completion(root, row, **kwargs):
        if row.get('record') == 'writing-application' and row.get('complete'):
            raise OSError('Injected application tracking failure')
        return bank(root, row, **kwargs)
    monkeypatch.setattr(records, 'bank', fail_completion)
    with pytest.raises(OSError, match='tracking failure'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    path = tmp_path / narrative.ARCHITECTURE_PROFILE_PATH
    before = path.stat().st_mtime_ns
    monkeypatch.setattr(records, 'bank', bank)
    result = profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    assert result['metadata_only']
    assert path.stat().st_mtime_ns == before
    assert profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)['reused']


def test_large_candidate_parts_and_metadata_do_not_repeat_profile_body(tmp_path):
    fixture(tmp_path)
    text = '# Profile\n' + ('A concrete résumé.\n' * 2000)
    candidate = propose(tmp_path, 'voice', 'workspace', {'content': text})
    assert len(json.dumps(candidate).encode()) < 6000
    ref = candidate['candidate_ref']; combined = ''; offset = 0
    while True:
        chunk = profiles.inspect('book', {'view': 'candidate', 'candidate_ref': ref,
            'part': 'proposed', 'offset': offset}, tmp_path)
        assert len(chunk['content'].encode()) <= profiles.MAX_PART_BYTES
        combined += chunk['content']; offset = chunk['coverage']['end']
        if not chunk.get('next_read'): break
    assert combined == text


def test_profile_text_part_bounds_encoded_quotes_and_control_characters():
    text = ('"quoted"\tline\n' * 1000)
    offset = 0; chunks = []
    while offset < len(text.encode()):
        result = profiles._part(text, offset, profiles.MAX_PART_BYTES)
        assert len(json.dumps(result['content'], ensure_ascii=False).encode()) <= profiles.MAX_PART_BYTES
        assert result['coverage']['end'] > offset
        chunks.append(result['content']); offset = result['coverage']['end']
    assert ''.join(chunks) == text
    for atom in ('é', '"'):
        with pytest.raises(ValueError, match='byte budget'):
            profiles._part(atom, 0, 1)


def test_source_calibrated_candidate_preserves_real_ledger_and_source_guards(tmp_path):
    _, voice = fixture(tmp_path)
    source = tmp_path / 'voice_sources/excerpt.txt'
    source.parent.mkdir(); source.write_text('An exact calibration excerpt.\n')
    ledger = tmp_path / 'evidence/voice/reading.json'
    ledger.parent.mkdir(parents=True)
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    ledger.write_text(json.dumps({'read': [{'path': 'voice_sources/excerpt.txt', 'sha256': source_digest,
        'coverage': 'complete source', 'register': 'technical'}]}))
    content = '# Voice\n## Current runtime prompt\nUse explicit derivations.\nLedger `evidence/voice/reading.json`.\n'
    voice.write_text(content)
    provenance_revision = writing_style.inspect('book', {'view': 'provenance'}, tmp_path)['provenance']['revision']
    change = {'content': content.replace('explicit derivations', 'concrete derivations'), 'basis': 'source_calibration',
        'expected_provenance_revision': provenance_revision,
        'source_handles': [{'path': 'voice_sources/excerpt.txt', 'sha256': source_digest}],
        'judgement': {'summary': 'The excerpt supports concrete derivations.'}}
    candidate = propose(tmp_path, 'voice', 'workspace', change)
    source.write_text('A changed calibration excerpt.\n')
    with pytest.raises(ValueError, match='calibration source changed'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    assert voice.read_text() == content
    assert profiles.inspect('book', {'view': 'candidate', 'candidate_ref': candidate['candidate_ref']}, tmp_path)['candidate_retained']


def test_voice_writer_rechecks_original_provenance_after_candidate_read(tmp_path, monkeypatch):
    _, voice = fixture(tmp_path)
    ledger = tmp_path / 'evidence/voice/old.json'
    ledger.parent.mkdir(parents=True); ledger.write_text(json.dumps({'read': []}))
    voice.write_text('# Existing voice\nLedger `evidence/voice/old.json`.\n')
    candidate = propose(tmp_path, 'voice', 'workspace', {'content': '# New preference\nConcrete explanation.\n'})
    real_snapshot = profiles.snapshot
    def raced_snapshot(*args, **kwargs):
        current = real_snapshot(*args, **kwargs)
        ledger.write_text(json.dumps({'read': [], 'changed': 'during profile read'}))
        return current
    monkeypatch.setattr(profiles, 'snapshot', raced_snapshot)
    with pytest.raises(ValueError, match='current voice provenance changed'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    assert voice.read_text().startswith('# Existing voice')


def test_project_owner_refuses_spec_race_after_adapter_inspection(tmp_path, monkeypatch):
    manuscript, _ = fixture(tmp_path)
    candidate = propose(tmp_path, 'voice', 'project', {'guidance': 'Candidate guidance.'})
    real_save = writing_style.save
    def raced_save(project, payload, root, **kwargs):
        spec = manuscript / 'manuscript_spec.json'
        value = json.loads(spec.read_text()); value['manuscript']['style_guidance'] = 'Concurrent guidance.'
        spec.write_text(json.dumps(value))
        return real_save(project, payload, root, **kwargs)
    monkeypatch.setattr(writing_style, 'save', raced_save)
    with pytest.raises(ValueError, match='revision conflict'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    assert writing_style.state('book', tmp_path)['guidance'] == 'Concurrent guidance.'


def test_confirmation_resolves_at_actual_desk_narrative_and_taste_consumers(tmp_path):
    from laplace.web import desk
    from laplace.engine import taste_retrieval
    fixture(tmp_path)
    candidate = propose(tmp_path, change={'content': architecture_content('confirmed-his question opening.')})
    profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    assert desk.architecture_profile_render(tmp_path)['his_correction_count'] == 0
    rows = taste_retrieval._profile_candidates(tmp_path, {'question'})
    assert any('historical confirmation assertion' in row['quote'] for row in rows)
    current = profiles.inspect('book', {'family': 'architecture', 'scope': 'workspace'}, tmp_path)
    profiles.change('book', {'action': 'confirm', 'family': 'architecture', 'scope': 'workspace',
        'fields': ['introduction_shape'], 'guards': {'profile_input_revision': current['revision']}, 'reason': 'Explicitly confirmed.'}, tmp_path)
    assert desk.architecture_profile_render(tmp_path)['his_correction_count'] == 1
    rows = taste_retrieval._profile_candidates(tmp_path, {'question'})
    assert any('[confirmed-his]' in row['quote'] for row in rows)
    brief = narrative.architecture_brief_for_section(narrative.architecture_profile(tmp_path), 0, 3, 'introduce', False)
    assert len(brief['his_corrections']) == 1
    assert brief['fields']['introduction_shape']['author_confirmation']['id'].startswith('DEC-')


def test_scope_symlink_and_child_authority_refusals(tmp_path):
    fixture(tmp_path)
    with pytest.raises(ValueError, match='const at scope'):
        profiles.inspect('book', {'family': 'architecture', 'scope': 'project'}, tmp_path)
    external = tmp_path / 'external.md'; external.write_text('# External\n')
    link = tmp_path / 'profiles/voice/link.md'; link.symlink_to(external)
    with pytest.raises(ValueError, match='profiles/voice'):
        profiles.inspect('book', {'family': 'voice', 'scope': 'workspace', 'profile': 'profiles/voice/link.md'}, tmp_path)
    candidate = propose(tmp_path)
    records.bank(tmp_path, {'record': 'writing-turn', 'id': 'WT-child', 'project': 'book', 'parent_turn_id': 'WT-profile-test'})
    with pytest.raises(ValueError, match='parent applies'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path,
            actor={'kind': 'agent', 'turn_id': 'WT-child'})
    records.bank(tmp_path, {'record': 'writing-turn', 'id': 'WT-dispatch', 'project': 'book', 'dispatch_id': 'TASK-child'})
    with pytest.raises(ValueError, match='parent applies'):
        profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path,
            actor={'kind': 'agent', 'turn_id': 'WT-dispatch'})


def test_project_voice_reaches_section_paragraph_and_retrieval_with_legacy_override(tmp_path, monkeypatch):
    from laplace.pipeline import dispatch, registry
    from laplace.engine import taste_retrieval
    fixture(tmp_path)
    monkeypatch.setattr(registry, '_repo_root', lambda: tmp_path)
    alternate = tmp_path / 'profiles/voice/alternate.md'
    alternate.write_text('# Alternate\n## Current runtime prompt\nExplain concrete mechanisms.\n')
    legacy = alternate.with_name('legacy.md'); legacy.write_text('# Legacy\nExplicit legacy section voice.\n')
    proposal = propose(tmp_path, 'voice', 'project', {'profile': 'profiles/voice/alternate.md',
        'guidance': 'Use this project’s worked examples.', 'genre': 'book'})
    profiles.change('book', {'action': 'apply', 'candidate_ref': proposal['candidate_ref']}, tmp_path)
    packet = {'contract': {}, 'paragraphs': [{'paragraph_id': 'S-p1', 'input_nodes': []}],
        'objects': {}, 'equation_ledger': {}, 'citations': {}}
    monkeypatch.setattr(narrative, 'narrative_packet', lambda *args, **kwargs: packet)
    section = dispatch._compile_dispatch_core('S', 'Explain', 'prose', 'book', tmp_path)
    paragraph = dispatch.compile_paragraph_dispatch('book', 'S', 'S-p1', tmp_path)
    for value in (section, paragraph):
        assert 'error' not in value, value
        assert value['writing_style']['selected_profile'] == 'profiles/voice/alternate.md'
        assert 'Explain concrete mechanisms.' in value['prompt']
        assert 'Use this project’s worked examples.' in value['prompt']
        assert 'PROJECT GENRE\nbook' in value['prompt']
    rows = taste_retrieval._profile_candidates(tmp_path, {'concrete'}, 'book')
    voice = next(row for row in rows if row['ref'] == 'alternate')
    assert 'Explain concrete mechanisms.' in voice['text']
    assert 'Use this project’s worked examples.' in voice['text']
    packet['contract']['voice_profile'] = 'profiles/voice/legacy.md'
    section = dispatch._compile_dispatch_core('S', 'Explain', 'prose', 'book', tmp_path)
    assert section['writing_style']['selection_origin'] == 'explicit-section-contract'
    assert section['writing_style']['selected_profile'] == 'profiles/voice/legacy.md'
    assert 'Explicit legacy section voice.' in section['prompt']
    assert writing_style.context('book', tmp_path)['selected_profile'] == 'profiles/voice/alternate.md'


def test_general_and_unselected_voice_consumers_keep_workspace_default(tmp_path):
    from laplace.pipeline import dispatch
    from laplace.engine import taste_retrieval
    fixture(tmp_path)
    path = tmp_path / 'registry_projects.json'
    registry = json.loads(path.read_text())
    registry['projects'].append({'name': 'general', 'kind': 'project', 'project_dir': 'general'})
    path.write_text(json.dumps(registry)); (tmp_path / 'general').mkdir()
    for selected in ('general', None):
        context, prompt = dispatch._voice_dispatch_context(selected, tmp_path)
        assert context['selected_profile'] == writing_style.DEFAULT_PROFILE
        assert 'Keep the argument concrete.' in prompt
        rows = taste_retrieval._profile_candidates(tmp_path, {'concrete'}, selected)
        assert any(row['ref'] == 'gerard-technical-v1' and 'Keep the argument concrete.' in row['text'] for row in rows)


def test_owner_action_templates_keep_nested_input_guard_and_human_confirmation_authority(tmp_path):
    from laplace.core import grammar
    fixture(tmp_path)
    summary = profiles.inspect('book', {'family': 'architecture', 'scope': 'workspace'}, tmp_path)
    action = summary['propose_action']
    assert action['kind'] == 'action-template' and action['required_fields'] == ['change', 'reason']
    assert action['native_request']['concept'] == 'architecture-profile@project'
    payload = grammar.to_owner_payload(action['native_request']['payload'])
    assert 'expected_revision' not in payload
    assert payload['guards']['profile_input_revision'] == summary['revision']
    candidate = profiles.change('book', {**payload, 'change': {'content': architecture_content()}, 'reason': 'Scoped preference.'}, tmp_path)
    profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    human = profiles.inspect('book', {'family': 'architecture', 'scope': 'workspace'}, tmp_path)
    agent = profiles.inspect('book', {'family': 'architecture', 'scope': 'workspace'}, tmp_path, actor={'kind': 'agent'})
    assert human['confirm_action']['permitted'] and not agent['confirm_action']['permitted']
    global_read = profiles.inspect(None, {'family': 'architecture', 'scope': 'workspace'}, tmp_path)
    assert not global_read['propose_action']['permitted']
    assert 'native_request' not in global_read['propose_action']
    assert 'project' not in global_read['propose_action']['payload']


def test_retrieval_weld_register_consumes_project_voice_selection_and_guidance(tmp_path, monkeypatch):
    from laplace.pipeline import dispatch, registry, voice_retrieval
    manuscript, _ = fixture(tmp_path)
    monkeypatch.setattr(registry, '_repo_root', lambda: tmp_path)
    (manuscript / 'projection_plan.json').write_text(json.dumps({'sections': [{'id': 'S'}]}))
    (manuscript / 'S.tex').write_text('% PLAN:S\n% S-p1\nA synthetic neutral paragraph.\n')
    alternate = tmp_path / 'profiles/voice/alternate.md'; alternate.write_text('# Alternate\nConcrete voice register.\n')
    candidate = propose(tmp_path, 'voice', 'project', {'profile': 'profiles/voice/alternate.md', 'guidance': 'This project guidance.'})
    profiles.change('book', {'action': 'apply', 'candidate_ref': candidate['candidate_ref']}, tmp_path)
    monkeypatch.setattr(voice_retrieval, 'build_channel', lambda *args, **kwargs: (
        [{'paragraph_id': 'S-p1', 'exemplars': [{'text': 'Synthetic authored example.', 'source': 'fixture'}]}], {'status': 'synthetic'}))
    result = dispatch.compile_weld_dispatch('book', tmp_path, voice_on=True)
    assert 'error' not in result, result
    assert result['writing_style']['selected_profile'] == 'profiles/voice/alternate.md'
    assert 'Concrete voice register.' in result['prompt']
    assert 'This project guidance.' in result['prompt']
    assert '<!-- RETRIEVED-EXEMPLARS -->' in result['prompt']
