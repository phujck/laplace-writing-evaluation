"""Actual existing owners and fresh data-only publication; no provider invocation."""
import copy
import json
from pathlib import Path
import pytest
import runtime_guard
from laplace.projects import library, artifacts, writing_sources
from laplace.projects import project_handover as H
from laplace.pipeline import workflow_definitions as D
from laplace.work import project_work, owner_discovery as O
from laplace.writing import records, session_reads

BUDGETS = dict(max_files=256, max_rows=512, max_bytes=4_000_000)


def write(root, rel, value):
    path = root / rel;path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if isinstance(value, (dict, list)) else value)
    return path


@pytest.fixture
def scene(tmp_path, monkeypatch):
    runtime_guard.arm(monkeypatch)
    monkeypatch.delenv('LAPLACE_CUSTODY_LIVE', raising=False)
    root = tmp_path / 'data';root.mkdir()
    write(root, 'registry_projects.json', {'projects': []})
    external = tmp_path / 'public-external';external.mkdir();(external / 'note.txt').write_text('Explicit public external dependency.\n')
    write(root, 'profiles/writing_sources.json', {'repositories': {'workspace': '.', 'external': str(external)}})
    write(root, '.laplace-cache/writing-provider-catalogue.json', {'schema_version': 'laplace.provider-catalogue/1', 'providers': [{'id': 'codex', 'available': False, 'models': []}]})
    code, created = library.create({'name': 'book', 'title': 'Data only public handover', 'kind': 'general'}, root)
    assert code == 201 and created['source_optional']
    project_work.task('book', {'id': 'WORK-one', 'title': 'Keep a complete handover', 'goal': 'Inspect the same identities in a fresh data home.'}, root)
    old = 'Public original full artifact body.\n' * 800
    new = 'Public current full artifact body.\n' * 900
    artifacts.store(root, 'book', {'path': 'note.txt', 'scope': 'project', 'before': None, 'content': old})
    artifacts.store(root, 'book', {'path': 'note.txt', 'scope': 'project', 'before': old, 'content': new})
    observed = artifacts.read(root, 'book', {'path': 'note.txt', 'scope': 'project'})
    member = library.change_material_reference('book', {'action': 'attach', 'expected_revision': library.metadata('book', root)['revision'], 'target': {'owner': 'artifact', 'project': 'book', 'path': 'note.txt', 'scope': 'project'}, 'consumed_revision': observed['revision']}, root)['reference']
    external_pin = writing_sources.reference_identity(root, {'repository': 'external', 'path': 'note.txt'})
    external_member = library.change_material_reference('book', {'action': 'attach', 'expected_revision': library.metadata('book', root)['revision'], 'target': {'owner': 'repository', 'repository': 'external', 'path': 'note.txt'}, 'consumed_revision': external_pin['revision']}, root)['reference']
    body = {'schema_version': D.SCHEMA, 'title': 'Portable definition', 'description': 'A complete public definition.', 'settings': {}, 'layout': {}, 'steps': [{'id': 'author', 'title': 'Author', 'parent_id': None, 'assignment': {'role': 'builder', 'instructions': 'Full public role instructions.\n' * 300, 'settings': {}}}], 'edges': []}
    first = D.save(root, O.project_scope('book', 'sdk'), {'request_id': 'save-first', 'expected_revision': None, 'definition': body})
    second_body = copy.deepcopy(body);second_body['title'] = 'Portable second version'
    second = D.save(root, O.project_scope('book', 'sdk'), {'request_id': 'save-second', 'definition_id': first['definition_id'], 'expected_revision': first['version'], 'definition': second_body})
    records.bank(root, {'record': 'writing-session', 'id': 'WS-public-history', 'project': 'book', 'role': 'author', 'provider': 'codex', 'model': 'public-fixture', 'effort': 'high'})
    records.bank(root, {'record': 'writing-turn', 'id': 'WT-public-history', 'project': 'book', 'session_id': 'WS-public-history', 'mode': 'discuss', 'text': 'Public saved question.\n' * 400})
    records.bank(root, {'record': 'writing-binding', 'id': 'WB-public-history', 'project': 'book', 'session_id': 'WS-public-history', 'native_id': 'public-foreign-native', 'tool_contract_digest': 'public-old-contract', 'native_registration_signature': 'public-old-registration'})
    records.bank(root, {'record': 'writing-reply', 'id': 'WR-public-history', 'project': 'book', 'session_id': 'WS-public-history', 'turn_id': 'WT-public-history', 'status': 'completed', 'text': 'Public full final reply.\n' * 500})
    # A different public namespace must not travel merely because its journal shares storage.
    library.create({'name': 'other', 'title': 'Other', 'kind': 'general'}, root)
    artifacts.store(root, 'other', {'path': 'other.txt', 'scope': 'project', 'before': None, 'content': 'FOREIGN_PUBLIC_SENTINEL'})
    return {'root': root, 'external': external, 'first': first, 'second': second, 'body': second_body, 'old': old, 'new': new, 'material': member, 'external_material': external_member}


def test_structured_refusal_owner_survives_export_and_foreign_references_stay_fenced(scene, tmp_path):
    root = scene['root']
    content = json.dumps({'recovery': {'refused': {'owner': {
        'operation': 'authoring/proposal-preview',
        'owner': 'manuscript_proposals.preview(root project turn_id)',
        'site': 'src/laplace/web/authoring_http.py:89', 'raised': None, 'chain': []}}},
        'related': {'owner': 'artifact', 'project': 'other', 'path': 'other.txt'}})
    artifacts.store(root, 'book', {'path': 'refusal.json', 'scope': 'project',
                                  'before': None, 'content': content})
    value = H.plan(root, 'book', **BUDGETS)
    assert any(item['kind'] == 'foreign-artifact' and item['copy_permission'] is False
               for item in value['dependencies'])
    destination = tmp_path / 'structured-owner-export'
    H.export(root, destination, value)
    assert (destination / 'writing_projects/book/refusal.json').read_text() == content
    assert not (destination / 'writing_projects/other').exists()
    assert H.inspect_handover(destination)['status'] == 'INSPECTED'


def test_complete_owned_data_fresh_reopen_and_explicit_external_rebind(scene, tmp_path, capsys):
    root = scene['root'];value = H.plan(root, 'book', **BUDGETS)
    assert not (root / 'pyproject.toml').exists() and not list(root.rglob('*.tex'))
    assert len(value['workflow_definitions'][0]['versions']) == 2
    destination = tmp_path / 'fresh'
    result = H.export(root, destination, value)
    assert result['status'] == 'EXPORTED'
    assert value['counts']['planned_output'] == result['counts']
    seen = H.inspect_handover(destination)
    assert seen['status'] == 'INSPECTED' and seen['providers_started'] == 0
    assert H.main(['inspect', '--root', str(destination)]) == 0
    assert json.loads(capsys.readouterr().out)['status'] == 'INSPECTED'
    assert not any((destination / p).exists() for p in ['src', 'scripts', '.codex', '.laplace-state', '.laplace-cache'])
    assert [r['name'] for r in json.loads((destination / 'registry_projects.json').read_text())['projects']] == ['book']
    assert not (destination / 'writing_projects/other').exists()
    for rel in {r['file'] for r in value['rows']}:
        kept = [raw for number, raw in enumerate((root / rel).read_bytes().splitlines(keepends=True), 1) if number in {r['line'] for r in value['rows'] if r['file'] == rel}]
        assert (destination / rel).read_bytes().startswith(b''.join(kept))
    for row in value['files']:
        assert (root / row['path']).read_bytes() == (destination / row['path']).read_bytes()
    assert project_work._task_revision(project_work._tasks('book', root)['WORK-one']) == project_work._task_revision(project_work._tasks('book', destination)['WORK-one'])
    assert artifacts.read(destination, 'book', {'path': 'note.txt', 'scope': 'project', 'limit': 40000})['content'] == scene['new']
    assert D.read(destination, O.project_scope('book', 'sdk'), {'definition_id': scene['first']['definition_id'], 'facet': 'export'}) == value['workflow_definitions'][0]
    history = session_reads.session_state(destination, 'WS-public-history', view='full')
    assert history['session']['native_id'] is None and history['session']['imported_history']
    assert 'native_registration_signature' not in history['session'] and history['active'] is None
    assert history['turns'][0]['text'] == 'Public saved question.\n' * 400
    assert history['turns'][0]['reply']['text'] == 'Public full final reply.\n' * 500
    from laplace.representation import writing_bodies
    original_artifacts = [json.loads(line) for line in (destination / 'contract/talk.jsonl').read_text().splitlines() if json.loads(line).get('record') == 'writing-artifact']
    assert [writing_bodies.resolve_fields(row, destination)['after'] for row in original_artifacts] == [scene['old'], scene['new']]
    assert any(r['status'] == 'UNBOUND' for r in value['dependencies'])
    with pytest.raises(ValueError, match='UNBOUND'):
        writing_sources.qualified_file(destination, {'repository': 'external', 'path': 'note.txt'})
    # Explicit trusted-host configuration only: authorised exact public target, no history rewrite.
    before = (destination / 'contract/talk.jsonl').read_bytes()
    original_config = (destination / 'profiles/writing_sources.json').read_bytes()
    config = json.loads(original_config)
    config['unbound_repositories'].pop('external');config['repositories']['external'] = str(scene['external'])
    write(destination, 'profiles/writing_sources.json', config)
    observed = writing_sources.reference_identity(destination, {'repository': 'external', 'path': 'note.txt'})
    assert observed['revision'] == scene['external_material']['consumed_revision']
    assert (destination / 'contract/talk.jsonl').read_bytes() == before
    (destination / 'profiles/writing_sources.json').write_bytes(original_config)
    assert H.inspect_handover(destination)['status'] == 'INSPECTED'
    write(tmp_path, 'handover-proof.json', {'plan': value, 'export': result, 'inspect': seen, 'explicit_rebind': observed, 'provider_starts': 0})


def test_selected_drift_missing_body_and_existing_destination_refuse(scene, tmp_path):
    root = scene['root'];value = H.plan(root, 'book', **BUDGETS)
    target = tmp_path / 'occupied';target.mkdir();write(target, 'keep.txt', 'preserve')
    with pytest.raises(H.Refused, match='FRESH_DESTINATION'):H.export(root, target, value)
    assert (target / 'keep.txt').read_text() == 'preserve'
    artifact = root / 'writing_projects/book/note.txt';original = artifact.read_bytes();artifact.write_text('Changed outside its owner')
    with pytest.raises((H.Refused, ValueError)):H.export(root, tmp_path / 'drift', value)
    assert not (tmp_path / 'drift').exists();artifact.write_bytes(original)
    body = next(row for row in value['files'] if row['path'].startswith('contract/writing_bodies/'))
    path = root / body['path'];raw = path.read_bytes();path.unlink()
    with pytest.raises((H.Refused, ValueError)):H.export(root, tmp_path / 'missing', value)
    assert not (tmp_path / 'missing').exists();path.write_bytes(raw)


def test_unrelated_append_does_not_stale_selected_cut_and_publication_never_replaces(scene, tmp_path, monkeypatch):
    root = scene['root'];value = H.plan(root, 'book', **BUDGETS)
    records.bank(root, {'record': 'writing-session', 'id': 'WS-other-only', 'project': 'other', 'role': 'author'})
    assert H.plan(root, 'book', **BUDGETS) == value
    target = tmp_path / 'raced'
    original = H._publish
    def racing(stage, destination):
        destination.mkdir();write(destination, 'keep.txt', 'raced owner')
        return original(stage, destination)
    monkeypatch.setattr(H, '_publish', racing)
    with pytest.raises(H.Refused, match='DESTINATION_OCCUPIED'):H.export(root, target, value)
    assert (target / 'keep.txt').read_text() == 'raced owner'
    assert not (target / H.MANIFEST).exists()


def test_bounds_path_escape_symlink_and_conflicting_identity(scene, tmp_path):
    root = scene['root']
    with pytest.raises(H.Refused, match='POSITIVE_BUDGETS'):H.plan(root, 'book', max_files=0, max_rows=5, max_bytes=200)
    with pytest.raises((H.Refused, ValueError)):H.plan(root, 'book', max_files=1, max_rows=512, max_bytes=4_000_000)
    with pytest.raises(ValueError, match='row budget|ROW_BUDGET') as bounded:H.plan(root, 'book', max_files=256, max_rows=1, max_bytes=4_000_000)
    assert bounded.value.details['budgets']['max_rows'] == 1 and bounded.value.details['counts']['complete'] is False
    home = root / 'writing_projects/book';(home / 'escape').symlink_to(scene['external'], target_is_directory=True)
    with pytest.raises(ValueError, match='symlink'):H.plan(root, 'book', **BUDGETS)
    (home / 'escape').unlink()
    records.bank(root, {'record': 'writing-session', 'id': 'WS-public-history', 'project': 'book', 'role': 'review'})
    with pytest.raises(H.Refused, match='AMBIGUOUS_HISTORY_ID'):H.plan(root, 'book', **BUDGETS)


def test_existing_selected_manuscript_export_carries_only_its_owned_definitions(tmp_path):
    from test_writing_eval_manifest import fixture, m
    from test_writing_evaluation_export import exporter
    root = tmp_path / 'legacy';root.mkdir();fixture(root)
    write(root, 'projects/first/text/references.json', {'sources': []})
    body = {'schema_version': D.SCHEMA, 'title': 'Selected manuscript definition', 'description': '', 'settings': {}, 'layout': {}, 'steps': [{'id': 'one', 'title': 'One', 'parent_id': None, 'assignment': {'role': 'builder', 'instructions': 'Preserve all these instructions.', 'settings': {}}}], 'edges': []}
    own = D.save(root, O.project_scope('first', 'sdk'), {'request_id': 'first-def', 'expected_revision': None, 'definition': body})
    foreign = D.save(root, O.project_scope('second', 'sdk'), {'request_id': 'second-def', 'expected_revision': None, 'definition': body})
    value = m.build(root, 'first')
    assert [p['definition_id'] for p in value['workflow_definitions']] == [own['definition_id']]
    destination = tmp_path / 'legacy-export';exporter.export(root, destination, 'first')
    rows = D._rows(destination)
    assert [r['definition_id'] for r in rows] == [own['definition_id']]
    assert not any(r['definition_id'] == foreign['definition_id'] for r in rows)
    exported = D.read(destination, O.project_scope('first', 'sdk'), {'definition_id': own['definition_id'], 'facet': 'export'})
    assert exported == value['workflow_definitions'][0]


def test_consumer_uses_pure_owner_validator_and_refuses_broken_packages(scene, monkeypatch):
    package = H.plan(scene['root'], 'book', **BUDGETS)['workflow_definitions'][0]
    def forbidden(*a, **k):raise AssertionError('pure transfer validation touched custody')
    monkeypatch.setattr(D, '_root', forbidden);monkeypatch.setattr(D, '_rows', forbidden)
    monkeypatch.setattr(D.writing_bodies, 'store', forbidden)
    detached = D.validate_export(package)
    assert detached == package and detached is not package
    detached['versions'][0]['definition']['title'] = 'caller mutation'
    assert package['versions'][0]['definition']['title'] != 'caller mutation'
    broken = copy.deepcopy(package);broken['versions'][0]['definition']['title'] = 'different bytes'
    with pytest.raises(D.Refused, match='INVALID_EXPORT_CHAIN'):D.validate_export(broken)
    duplicate = copy.deepcopy(package);duplicate['versions'][1]['row']['request_id'] = duplicate['versions'][0]['row']['request_id']
    duplicate['versions'][1]['row']['receipt']['request_id'] = duplicate['versions'][0]['row']['request_id']
    with pytest.raises(D.Refused, match='INVALID_EXPORT_REQUEST_DUPLICATE'):D.validate_export(duplicate)
    with pytest.raises(D.Refused, match='RESTORE_NOT_ADMITTED'):D.restore(scene['root'], O.project_scope('book', 'sdk'), package)


def test_empty_registered_project_retains_home_without_fabricating_a_manuscript(tmp_path):
    root = tmp_path / 'empty-source';root.mkdir()
    write(root, 'registry_projects.json', {'projects': [{'name': 'empty', 'kind': 'project', 'project_dir': 'writing_projects/empty', 'manifest': {}}]})
    write(root, 'profiles/writing_sources.json', {'repositories': {'workspace': '.'}})
    (root / 'writing_projects/empty').mkdir(parents=True)
    value = H.plan(root, 'empty', **BUDGETS);destination = tmp_path / 'empty-export'
    H.export(root, destination, value)
    assert (destination / 'writing_projects/empty/.writing-project-home.json').is_file()
    assert not (destination / 'writing_projects/empty/manuscript').exists()
    assert H.inspect_handover(destination)['status'] == 'INSPECTED'


def test_missing_owned_material_without_artifact_history_is_not_externalised(scene):
    root = scene['root'];path = write(root, 'writing_projects/book/loose.txt', 'Owned current material')
    observed = artifacts.read(root, 'book', {'path': 'loose.txt', 'scope': 'project'})
    library.change_material_reference('book', {'action': 'attach', 'expected_revision': library.metadata('book', root)['revision'], 'target': {'owner': 'artifact', 'project': 'book', 'path': 'loose.txt', 'scope': 'project'}, 'consumed_revision': observed['revision']}, root)
    path.unlink()
    with pytest.raises(H.Refused, match='OWNED_MATERIAL_UNAVAILABLE'):H.plan(root, 'book', **BUDGETS)


def _row_counts(value):
    from collections import Counter
    return Counter((r['file'], r['row_sha256']) for r in value['rows'])


def test_repeated_handover_retains_proven_store_lineage_after_edits_without_old_root_reads(scene, tmp_path):
    from laplace.projects import project_data as C
    root = scene['root'];first = H.plan(root, 'book', **BUDGETS)
    fresh = tmp_path / 'first-fresh';H.export(root, fresh, first)
    untouched = root.with_name('original-source-unreachable');root.rename(untouched)
    assert not root.exists()
    reopened = H.plan(fresh, 'book', **BUDGETS)
    assert not (_row_counts(first) - _row_counts(reopened))
    assert len(reopened['rows']) == len(first['rows']) + 1  # original rows plus retained import
    original_banks = {r['row_sha256'] for r in first['rows'] if r['file'] == 'contract/journal.jsonl' and r['record'] == 'bank' and r['id'] is None}
    # Ordinary owner edits/appends and a deliberate external rebind do not invalidate historical proof.
    artifacts.store(fresh, 'book', {'path': 'note.txt', 'scope': 'project', 'before': scene['new'], 'content': 'New local revision after import.\n' * 200})
    project_work.task('book', {'id': 'WORK-one', 'title': 'Keep a complete handover', 'goal': 'Updated after import.', 'expected_work_revision': project_work._task_revision(project_work._tasks('book', fresh)['WORK-one'])}, fresh)
    config = json.loads((fresh / 'profiles/writing_sources.json').read_text())
    config['unbound_repositories'].pop('external');config['repositories']['external'] = str(scene['external'])
    write(fresh, 'profiles/writing_sources.json', config)
    # A prior root is not a general alias authorising new/unrelated rows with that address.
    foreign = {'record': 'bank', 'act_id': 'UNRELATED-OLD-ROOT', 'store': str(root / 'corpus_friction/work_orders.jsonl'), 'row_id': 'WORK-one', 'phase': 'done'}
    with (fresh / 'contract/journal.jsonl').open('a') as stream:stream.write(json.dumps(foreign) + '\n')
    second = H.plan(fresh, 'book', **BUDGETS)
    assert not (_row_counts(first) - _row_counts(second))
    assert second['history_lineage'] and all(a['project'] == 'book' for a in second['history_lineage'])
    assert all(a['source_store'].startswith(str(root)) for a in second['history_lineage'])
    selected = C.select_history(fresh, 'book', additional=C.collect_definitions(fresh, 'book')[0])
    assert not any(r[3].get('act_id') == 'UNRELATED-OLD-ROOT' for r in selected)
    next_fresh = tmp_path / 'second-fresh';H.export(fresh, next_fresh, second)
    third = H.plan(next_fresh, 'book', **BUDGETS)
    assert not (_row_counts(first) - _row_counts(third)) and not (_row_counts(second) - _row_counts(third))
    assert H.inspect_handover(next_fresh)['status'] == 'INSPECTED'
    write(tmp_path, 'repeated-lineage-proof.json', {'first': first, 'second': second, 'third': third,
        'old_source_unavailable': True, 'original_bank_hashes': sorted(original_banks), 'no_unrelated_old_address_rows': True, 'provider_calls': 0})


@pytest.mark.parametrize('fault', ['canonical', 'row-bytes', 'row-order', 'import-boundary', 'foreign-association', 'missing-manifest'])
def test_changed_or_unverifiable_retained_lineage_refuses_before_publication(scene, tmp_path, fault):
    from laplace.core.identity import canonical_digest
    root = scene['root'];first = H.plan(root, 'book', **BUDGETS)
    fresh = tmp_path / 'first';H.export(root, fresh, first)
    if fault == 'foreign-association':
        second = H.plan(fresh, 'book', **BUDGETS);new = tmp_path / 'second';H.export(fresh, new, second);fresh = new
    manifest = fresh / H.MANIFEST
    receipt = json.loads(manifest.read_text())
    if fault == 'missing-manifest':
        manifest.unlink()
    elif fault == 'canonical':
        receipt['plan']['project_dir'] += '-changed';write(fresh, H.MANIFEST, receipt)
    elif fault in {'row-bytes', 'row-order'}:
        path = fresh / 'contract/journal.jsonl';lines = path.read_bytes().splitlines(keepends=True)
        if fault == 'row-bytes':
            row = json.loads(lines[0]);row['phase'] = 'changed';lines[0] = (json.dumps(row) + '\n').encode()
        else:lines[0], lines[1] = lines[1], lines[0]
        path.write_bytes(b''.join(lines))
    elif fault == 'import-boundary':
        path = fresh / 'contract/talk.jsonl';path.write_bytes(b''.join(l for l in path.read_bytes().splitlines(keepends=True) if json.loads(l).get('record') != 'writing-session-import'))
    else:
        value = receipt['plan'];old = value['manifest_digest'];value['history_lineage'][0]['project'] = 'other'
        value['manifest_digest'] = canonical_digest({k:v for k,v in value.items() if k != 'manifest_digest'})
        # Even a locally re-hashed claim/import cannot widen project-qualified association.
        path = fresh / 'contract/talk.jsonl';lines = path.read_bytes().splitlines(keepends=True)
        for i, raw in enumerate(lines):
            row = json.loads(raw)
            if row.get('record') == 'writing-session-import' and row.get('source_manifest_sha256') == old:
                row['source_manifest_sha256'] = value['manifest_digest']
                import hashlib
                row['id'] = 'IMPORT-' + hashlib.sha256((value['manifest_digest'] + row['session_id']).encode()).hexdigest()[:24]
                lines[i] = H.encoded(row)
        path.write_bytes(b''.join(lines));write(fresh, H.MANIFEST, receipt)
    destination = tmp_path / 'must-not-publish'
    with pytest.raises(ValueError, match='lineage'):
        H.export(fresh, destination, H.plan(fresh, 'book', **BUDGETS))
    assert not destination.exists()


@pytest.mark.parametrize('projects', [['first'], ['first', 'second']], ids=['single', 'multi'])
def test_legacy_selected_export_uses_same_verified_retained_lineage_after_work_append(tmp_path, projects):
    from test_writing_eval_manifest import fixture, m
    from test_writing_evaluation_export import exporter
    root = tmp_path / 'legacy-source';root.mkdir();fixture(root)
    write(root, 'projects/first/text/references.json', {'sources': []})
    project_work.task('first', {'id': 'WORK-portable', 'title': 'Portable history', 'goal': 'Retain exact banks.'}, root)
    first = m.build(root, 'first');fresh = tmp_path / 'legacy-first';exporter.export_projects(root, fresh, projects)
    root.rename(tmp_path / 'old-source-unreachable')
    project_work.task('first', {'id': 'WORK-portable', 'title': 'Portable history', 'goal': 'An ordinary post-import update.', 'expected_work_revision': project_work._task_revision(project_work._tasks('first', fresh)['WORK-portable'])}, fresh)
    second = m.build(fresh, 'first')
    assert not (_row_counts({'rows': first['selected_rows']}) - _row_counts({'rows': second['selected_rows']}))
    assert second['history_lineage']
    target = tmp_path / 'legacy-second';exporter.export(fresh, target, 'first')
    third = m.build(target, 'first')
    assert not (_row_counts({'rows': second['selected_rows']}) - _row_counts({'rows': third['selected_rows']}))


def test_readonly_artifact_selected_handover_preserves_namespace_and_portable_link(tmp_path,monkeypatch):
    """The read capability never widens selected export's project namespace."""
    from urllib.parse import urlsplit,parse_qs
    from laplace.manuscript import manuscript_source
    from laplace.web import research_artifact_read
    from test_manuscript_structure import _section_fixture
    from test_reader_plan_owner import _imported_reader
    runtime_guard.arm(monkeypatch)
    disjoint=tmp_path/'disjoint';disjoint.mkdir()
    imported,_=_imported_reader(disjoint)
    denied=artifacts.store(disjoint,'book',{'path':'decisions/handover.json','scope':'manuscript',
        'before':None,'content':'{"decision":"retain"}','reason':'Actual imported owner artifact'})
    manifest=artifacts.store(disjoint,'book',{'path':'manifest.json','scope':'project',
        'before':None,'content':json.dumps({'schema_version':'laplace.research-handover/1','entries':[]}),
        'reason':'Actual selected closure manifest'})
    reg=disjoint/'registry_projects.json';declared=json.loads(reg.read_text())
    declared['projects'][0]['manifest']['document']['read_only']=True
    reg.write_text(json.dumps(declared))
    selection={'files':[],'artifact_ids':[manifest['id'],denied['id']],'definitions':[],
        'manifest_id':manifest['id'],'manifest_sha256':manifest['revision']}
    with pytest.raises(H.Refused,match='SELECTED_ARTIFACT_NOT_PERMITTED'):
        H.plan(disjoint,'book',selection=selection,**BUDGETS)
    assert artifacts.read(disjoint,'book',{'id':denied['id'],'expected_sha256':denied['revision']})['exists']

    # Separate permitted ordinary layout. State home is explicitly unchanged,
    # before and after changing ONLY its declared readonly policy.
    root=tmp_path/'permitted';root.mkdir()
    write(root,'profiles/writing_sources.json',{'repositories':{'workspace':'.'}})
    manuscript,_,_=_section_fixture(root)
    source=manuscript_source.resolve('book',repo_root=root)
    reg=root/'registry_projects.json';declared=json.loads(reg.read_text())
    from laplace.pipeline import registry
    project_dir=registry.resolve('book',repo_root=root).project_dir
    declared['projects'][0]['project_dir']=project_dir
    declared['projects'][0].setdefault('manifest',{}).setdefault('document',{}).update(
        root=source['root'],state_dir=project_dir)
    reg.write_text(json.dumps(declared))
    saved=artifacts.store(root,'book',{'path':'decisions/proof.json','scope':'manuscript','before':None,
        'content':json.dumps({'decision':'retain','method':'actual owner artifact'}),'reason':'Portable owned proof'})
    manifest=artifacts.store(root,'book',{'path':'manifest.json','scope':'project','before':None,
        'content':json.dumps({'schema_version':'laplace.research-handover/1','entries':[]}),
        'reason':'Actual selected closure manifest'})
    observed=artifacts.read(root,'book',{'id':saved['id']})
    library.change_material_reference('book',{'action':'attach',
        'expected_revision':library.metadata('book',root)['revision'],
        'target':{'owner':'artifact','project':'book','path':saved['artifact_path'],'scope':'manuscript'},
        'consumed_revision':observed['revision']},root)
    declared=json.loads(reg.read_text())
    declared['projects'][0]['manifest']['document']['read_only']=True
    reg.write_text(json.dumps(declared))
    assert artifacts.context(root,'book')['base']==root/project_dir
    whole=H.plan(root,'book',**BUDGETS)
    assert any(row['path']==saved['path'] for row in whole['files'])
    # Transport source files through explicitly selected, in-project coordinates
    # so the ordinary receiving source reader can resolve the same manuscript.
    selected_files=[{'path':p.relative_to(root).as_posix(),'sha256':writing_sources.file_revision(p)}
        for p in manuscript.rglob('*.tex')]
    selection={'files':selected_files,'artifact_ids':[manifest['id'],saved['id']],'definitions':[],
        'manifest_id':manifest['id'],'manifest_sha256':manifest['revision']}
    selected=H.plan(root,'book',selection=selection,**BUDGETS)
    destination=tmp_path/'portable'
    assert H.export(root,destination,selected)['status']=='EXPORTED'
    # Reuse the ORIGINAL owner URL; no rebasing, substitute ID or provider.
    query=parse_qs(urlsplit(saved['human_read']['url']).query)
    status,_,body=research_artifact_read.read('book',query,'GET',repo_root=destination)
    assert status==200 and body==(root/saved['path']).read_bytes()
    assert artifacts.read(destination,'book',{'id':saved['id'],'expected_sha256':saved['revision']})['revision']==saved['revision']
    bad=copy.deepcopy(selection);bad['manifest_sha256']='0'*64
    with pytest.raises(H.Refused,match='SELECTED_MANIFEST_CHANGED'):
        H.plan(root,'book',selection=bad,**BUDGETS)
    bad=copy.deepcopy(selection);bad['files'].append({'path':'../outside.json','sha256':'0'*64})
    with pytest.raises(H.Refused,match='SELECTED_FILE_NOT_OWNED_OR_PERMITTED'):
        H.plan(root,'book',selection=bad,**BUDGETS)
    (root/saved['path']).write_bytes(body+b' ')
    with pytest.raises(H.Refused,match='SELECTED_ARTIFACT_CHANGED'):
        H.plan(root,'book',selection=selection,**BUDGETS)
