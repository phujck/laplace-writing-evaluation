import json
from pathlib import Path

from laplace.projects import library as wp
from laplace.writing import provider as writing_provider


def test_create_book_has_selected_editable_source_and_no_pipeline_lock(tmp_path):
    status, out = wp.create({"name": "field-notes", "title": "Field Notes", "kind": "book",
                             "purpose": "A careful draft.", "audience": "researchers"}, tmp_path)
    assert status == 201, out
    main = tmp_path / "synthetics papers" / "field-notes" / "manuscript" / "Field-Notes.tex"
    chapter = main.parent / "chapters" / "chapter-01.tex"
    assert "\\documentclass{book}" in main.read_text(encoding="utf-8")
    assert "\\input{chapters/chapter-01}" in main.read_text(encoding="utf-8")
    assert "\\bibliography{refs}" in main.read_text(encoding="utf-8")
    assert (main.parent / "refs.bib").is_file()
    assert "Draft" in chapter.read_text(encoding="utf-8")
    assert out["source"]["status"] == "resolved" and out["pipeline_locked"] is False
    row = json.loads((tmp_path / "registry_projects.json").read_text(encoding="utf-8"))["projects"][0]
    assert row["manifest"]["document"]["root"] == "Field-Notes.tex"
    assert row["manifest"]["writing"]["audience"] == "researchers"
    authoring = json.loads((main.parent / "authoring.json").read_text(encoding="utf-8"))
    assert authoring["framing"] == {"purpose": "A careful draft.", "audience": "researchers", "question": ""}


def test_import_registers_existing_source_without_changing_it(tmp_path):
    source = tmp_path / "existing" / "main.tex"; source.parent.mkdir(parents=True)
    source.write_text("\\documentclass{article}\n\\title{Existing}\n\\begin{document}Text.\\end{document}\n", encoding="utf-8")
    before = source.read_bytes()
    status, out = wp.import_source({"name": "existing-work", "title": "Existing", "root": "existing/main.tex"}, tmp_path)
    assert status == 201 and out["copied"] is False and out["rewritten"] is False
    assert out["read_only"] is True
    assert source.read_bytes() == before
    status, duplicate = wp.import_source({"name": "other", "title": "Other", "root": "existing/main.tex"}, tmp_path)
    assert status == 409 and "already registered" in duplicate["error"]


def test_import_preserves_readonly_source_and_refuses_foreign_tree_alias(tmp_path):
    foreign = tmp_path / "foreign"; foreign.mkdir()
    main = foreign / "main.tex"; main.write_text("\\documentclass{article}\n\\begin{document}Foreign.\\end{document}", encoding="utf-8")
    nested = foreign / "other.tex"; nested.write_text("\\documentclass{article}\n\\begin{document}Alias.\\end{document}", encoding="utf-8")
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "foreign-original", "kind": "conceptric", "project_dir": "writing_projects/foreign-original",
        "tex_root": "foreign", "manifest": {"document": {"root": "foreign/main.tex", "manuscript_dir": "foreign", "read_only": True, "state_dir": "writing_projects/foreign-original"}},
    }]}), encoding="utf-8")
    (tmp_path / "writing_projects" / "foreign-original").mkdir(parents=True)
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve("foreign-original", repo_root=tmp_path)
    assert source["read_only"] is True and source["storage_dir"] == "writing_projects/foreign-original"
    status, out = wp.import_source({"name": "laundered", "title": "Alias", "root": "foreign/other.tex", "editable": True}, tmp_path)
    assert status == 409 and "foreign/read-only" in out["error"]


def test_default_import_stores_authoring_state_outside_original_source(tmp_path):
    source = tmp_path / "source" / "main.tex"; source.parent.mkdir(parents=True)
    source.write_text("\\documentclass{article}\n\\begin{document}Original.\\end{document}", encoding="utf-8")
    status, _ = wp.import_source({"name": "readonly-import", "title": "Readonly", "root": "source/main.tex"}, tmp_path)
    assert status == 201
    from laplace.pipeline import authoring
    authoring.save("readonly-import", {"argument": "engine state only"}, repo_root=tmp_path)
    assert not (source.parent / "authoring.json").exists()
    assert (tmp_path / "writing_projects" / "readonly-import" / "authoring.json").is_file()


def test_discover_is_bounded_to_repository_manuscript_homes(tmp_path):
    manuscript = tmp_path / "synthetics papers" / "candidate" / "manuscript"; manuscript.mkdir(parents=True)
    (manuscript / "draft.tex").write_text("\\documentclass{article}\n\\begin{document}Draft words.\\end{document}", encoding="utf-8")
    out = wp.discover(tmp_path, limit=10)
    assert out["bounded"] is True
    assert out["candidates"] == [{"root": "synthetics papers/candidate/manuscript/draft.tex", "title": "draft", "status": "candidate", "manuscript_dir": "synthetics papers/candidate/manuscript"}]


def test_import_refuses_traversal_and_library_has_source_state(tmp_path):
    status, out = wp.import_source({"name": "bad", "title": "Bad", "root": "../outside.tex"}, tmp_path)
    assert status == 422
    status, _ = wp.create({"name": "paper-one", "title": "Paper One", "kind": "paper"}, tmp_path)
    assert status == 201
    library = wp._library(tmp_path)
    project = next(row for row in library["projects"] if row["name"] == "paper-one")
    assert project["status"] == "resolved"


def test_registered_empty_project_can_start_without_replacing_its_old_source(tmp_path):
    from laplace.projects import library as writing_projects
    from laplace.manuscript import manuscript_source
    import json
    md=tmp_path/'synthetics papers/empty-project/manuscript';md.mkdir(parents=True)
    original='\\documentclass{article}\n\\begin{document}\n\\end{document}\n'
    (md/'main.tex').write_text(original)
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'empty-project',
        'kind':'conceptric','project_dir':'synthetics papers/empty-project','tex_root':'synthetics papers/empty-project/manuscript'}]}))
    status,out=writing_projects.start_manuscript({'project':'empty-project','title':'A new explanation','kind':'book'},tmp_path)
    assert status==201,out
    assert (md/'main.tex').read_text()==original
    assert manuscript_source.resolve('empty-project',repo_root=tmp_path)['status']=='resolved'
    assert 'working-draft/A-new-explanation.tex' in out['source']['root']
    assert writing_projects.start_manuscript({'project':'empty-project'},tmp_path)[0]==409


def test_general_project_is_source_optional_and_can_add_manuscript(tmp_path):
    from laplace.pipeline import registry, authoring
    status, out = wp.create({'name': 'company-work', 'title': 'Company Work', 'kind': 'company',
                             'purpose': 'Plan the next quarter'}, tmp_path)
    assert status == 201, out
    assert out['layout'] == 'project' and out['source_optional'] is True
    assert out['capabilities']['manuscript'] is False and out['capabilities']['start_manuscript'] is True
    record = registry.resolve('company-work', tmp_path)
    assert record.kind == 'project' and record.bib == '' and record.plan_path == ''
    assert not list(tmp_path.rglob('*.tex'))
    assert not (tmp_path / 'corpus_friction/work_orders.jsonl').exists()
    assert authoring.load('company-work', tmp_path)['framing']['purpose'] == 'Plan the next quarter'
    library = wp._library(tmp_path)['projects'][0]
    assert library['title'] == 'Company Work' and library['kind'] == 'company'
    assert library['layout'] == 'project' and library['source_optional'] is True
    status, draft = wp.start_manuscript({'project': 'company-work', 'title': 'Quarter Plan', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    assert draft['source']['status'] == 'resolved'
    assert registry.resolve('company-work', tmp_path).kind == 'project'
    assert wp.start_manuscript({'project': 'company-work'}, tmp_path)[0] == 409


def test_create_collision_is_scoped_and_concurrent(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from laplace.projects import project_creation
    payload = {'name': 'shared-name', 'title': 'Shared Name', 'kind': 'general'}
    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _: wp.create(payload, tmp_path)[0], range(4)))
    assert sorted(statuses) == [201, 409, 409, 409]
    assert project_creation.create_project('shared-name', 'conceptric', tmp_path)[0] == 409
    with ThreadPoolExecutor(max_workers=4) as pool:
        made = list(pool.map(lambda n: wp.create({**payload, 'name': 'work-' + str(n)}, tmp_path)[0], range(4)))
    assert made == [201] * 4
    assert len(json.loads((tmp_path / 'registry_projects.json').read_text())['projects']) == 5


def test_failed_general_creation_retains_truthful_registry_and_retry_refuses(tmp_path, monkeypatch):
    from laplace.pipeline import authoring
    monkeypatch.setattr(authoring, 'save', lambda *a, **kw: (_ for _ in ()).throw(ValueError('fixture failure')))
    payload = {'name': 'failed-work', 'title': 'Failed Work', 'kind': 'general'}
    status, out = wp.create(payload, tmp_path)
    assert status == 500 and out['retained_project'] is True
    row = wp._library(tmp_path)['projects'][0]
    assert row['creation'] == {'status': 'failed', 'error': 'fixture failure'}
    assert row['title'] == 'Failed Work' and row['status'] == 'missing'
    assert wp.create(payload, tmp_path)[0] == 409
    assert wp.create({'name': 3, 'title': 'Invalid'}, tmp_path)[0] == 422


def _general(tmp_path, name='consumer-work'):
    assert wp.create({'name': name, 'title': name, 'kind': 'general'}, tmp_path)[0] == 201
    return name


def _attach_repository(tmp_path, project, path='material.txt'):
    from laplace.projects import writing_sources
    target = {'owner': 'repository', 'repository': 'laplace', 'path': path}
    revision = writing_sources.reference_identity(tmp_path, target)['revision']
    return wp.change_material_reference(project, {'action': 'attach', 'target': target,
        'consumed_revision': revision, 'expected_revision': wp.metadata(project, tmp_path)['revision']}, tmp_path)


def test_native_material_handle_keeps_qualified_source_and_human_route(tmp_path):
    from urllib.parse import parse_qs, urlsplit
    from laplace.work import project_work_views
    from laplace.writing import operations
    project = _general(tmp_path, 'source-consumer')
    (tmp_path / 'criterion.md').write_text('Current criterion\n')
    target = {'owner': 'repository', 'repository': 'laplace', 'path': 'criterion.md'}
    native = operations._execute(tmp_path, project, 'discuss', 'material_references',
        {'view': 'preview', 'target': target, 'offset': 0, 'limit': 16000})
    human = native['human_read']
    assert human['kind'] == 'material-source' and human['project'] == project
    assert 'current owner bytes' in human['content_policy']
    assert native['currentness'] == 'UNBOUND' and native['consumed_revision'] is None
    route = native['restart_read']
    assert route['http']['method'] == 'GET' and route['http']['url'] == human['url']
    assert route['operation'] == 'material_references' and route['payload']['target'] == target
    status, _, raw = wp.handle('/projects/material-references', parse_qs(urlsplit(human['url']).query), 'GET', b'', tmp_path)
    assert status == 200 and json.loads(raw)['owner_result']['content'] == 'Current criterion\n'
    work = project_work_views.handle(project, {'view': 'detail', 'id': 'WORK-observed', 'limit': 1})
    q = parse_qs(urlsplit(work['http']['url']).query)
    assert q == {'project': [project], 'view': ['detail'], 'id': ['WORK-observed'], 'limit': ['1']}


def test_material_http_owner_rejects_duplicate_ambiguous_or_unknown_coordinates(tmp_path):
    project = _general(tmp_path)
    target = json.dumps({'owner': 'repository', 'repository': 'laplace', 'path': 'criterion.md'})
    normal = {'project': [project], 'view': ['preview'], 'target': [target]}
    for fields in [
        {**normal, 'project': [project, 'another']},
        {**normal, 'target': [target, target]},
        {**normal, 'id': ['MAT-ambiguous']},
        {**normal, 'write': ['1']},
        {**normal, 'target': ['{"owner":"repository","repository":"laplace","path":"one","path":"two"}']},
        {**normal, 'target': ['{"owner":"repository","repository":"laplace","path":"one","unknown":"field"}']},
        {**normal, 'offset': ['-1']},
        {**normal, 'limit': ['40001']},
    ]:
        status, _, raw = wp.handle('/projects/material-references', fields, 'GET', b'', tmp_path)
        assert status == 422 and json.loads(raw)['error'], fields


def test_repository_material_pins_changes_and_explicit_adoption(tmp_path):
    import pytest
    project = _general(tmp_path)
    source = tmp_path / 'material.txt'; source.write_text('Original owned material')
    attached = _attach_repository(tmp_path, project)
    first = wp.material_references(project, tmp_path)
    ref = first['references'][0]
    assert ref['currentness'] == 'CURRENT' and ref['write_permission'] is False
    assert ref['read_handle']['operation'] == 'material_references'
    assert ref['owner_read_handle']['operation'] == 'repository'
    assert 'content' not in ref and 'update_handle' not in ref
    source.write_text('Changed owned material')
    changed = wp.material_references(project, tmp_path)['references'][0]
    assert changed['currentness'] == 'CHANGED_INPUT'
    assert changed['consumed_revision'] == ref['consumed_revision']
    with pytest.raises(ValueError, match='source revision conflict'):
        wp.change_material_reference(project, {'action': 'adopt', 'id': ref['id'],
            'expected_revision': attached['revision'], 'consumed_revision': ref['consumed_revision']}, tmp_path)
    adopted = wp.change_material_reference(project, {'action': 'adopt', 'id': ref['id'],
        'expected_revision': attached['revision'], 'consumed_revision': changed['current_revision']}, tmp_path)
    assert wp.material_references(project, tmp_path)['references'][0]['currentness'] == 'CURRENT'
    with pytest.raises(ValueError, match='metadata revision conflict'):
        wp.change_material_reference(project, {'action': 'remove', 'id': ref['id'],
            'expected_revision': first['revision']}, tmp_path)
    source.unlink()
    missing = wp.material_references(project, tmp_path)['references'][0]
    assert missing['currentness'] == 'UNRESOLVED' and missing['consumed_revision'] == changed['current_revision']
    assert missing['current_revision'] is None
    wp.change_material_reference(project, {'action': 'remove', 'id': ref['id'],
        'expected_revision': adopted['revision']}, tmp_path)
    assert wp.material_references(project, tmp_path)['references'] == []


def test_artifact_material_preserves_owner_scope_and_content(tmp_path):
    from laplace.writing import operations
    producer, consumer = _general(tmp_path, 'producer-work'), _general(tmp_path)
    stored = operations._execute(tmp_path, producer, 'discuss', 'store_artifact',
        {'path': 'notes.txt', 'scope': 'project', 'before': None, 'content': 'Produced source material'})
    target = {'owner': 'artifact', 'project': producer, 'path': 'notes.txt', 'scope': 'project'}
    wp.change_material_reference(consumer, {'action': 'attach', 'target': target,
        'consumed_revision': stored['revision'], 'expected_revision': wp.metadata(consumer, tmp_path)['revision']}, tmp_path)
    ref = wp.material_references(consumer, tmp_path)['references'][0]
    assert ref['target'] == target and ref['currentness'] == 'CURRENT'
    assert ref['read_handle']['project'] == consumer
    assert ref['owner_read_handle']['project'] == producer
    assert not (tmp_path / 'writing_projects' / consumer / 'notes.txt').exists()
    assert (tmp_path / 'writing_projects' / producer / 'notes.txt').read_text() == 'Produced source material'
    assert 'update_handle' not in ref and ref['write_permission'] is False


def test_material_reference_escape_unavailable_and_digest_cache(tmp_path, monkeypatch):
    import pytest
    from laplace.projects import writing_sources as ws
    project = _general(tmp_path)
    source = tmp_path / 'material.txt'; source.write_text('Material')
    ws._file_revision.cache_clear()
    calls = []
    original = ws._identity
    def count(path):
        calls.append(path.stat().st_size)
        return original(path)
    monkeypatch.setattr(ws, '_identity', count)
    _attach_repository(tmp_path, project)
    for _ in range(10):
        assert wp.material_references(project, tmp_path)['references'][0]['currentness'] == 'CURRENT'
    assert calls == [len('Material')]
    assert ws._file_revision.cache_info().currsize == 1
    source.write_text('New material')
    assert wp.material_references(project, tmp_path)['references'][0]['currentness'] == 'CHANGED_INPUT'
    assert calls == [len('Material'), len('New material')]
    outside = tmp_path.parent / (tmp_path.name + '-outside.txt'); outside.write_text('Outside')
    (tmp_path / 'escape.txt').symlink_to(outside)
    with pytest.raises(ValueError, match='escapes'):
        ws.reference_identity(tmp_path, {'repository': 'laplace', 'path': 'escape.txt'})
    (tmp_path / 'profiles').mkdir()
    (tmp_path / 'profiles/writing_sources.json').write_text(json.dumps({'repositories': {'missing': 'absent'}}))
    row = wp.material_references(project, tmp_path)['references'][0]
    assert row['currentness'] == 'UNRESOLVED'


def test_material_reference_http_owner_errors_and_methods(tmp_path):
    project = _general(tmp_path)
    source = tmp_path / 'material.txt'; source.write_text('Material')
    attached = _attach_repository(tmp_path, project)
    status, _, body = wp.handle('/projects/material-references', {'project': [project]}, 'GET', b'', tmp_path)
    out = json.loads(body)
    assert status == 200 and out['references'][0]['currentness'] == 'CURRENT'
    payload = {'project': project, 'action': 'remove', 'id': attached['reference']['id'],
               'expected_revision': out['revision']}
    assert wp.handle('/projects/material-references', {}, 'POST', json.dumps(payload).encode(), tmp_path)[0] == 200
    assert wp.handle('/projects/material-references', {}, 'POST', b'[]', tmp_path)[0] == 422
    assert wp.handle('/projects/material-references', {}, 'DELETE', b'', tmp_path)[0] == 405


def test_material_reference_pagination_has_exact_continuation_without_storage_cap(tmp_path):
    project = _general(tmp_path)
    from laplace.projects import writing_sources
    bindings = []
    for index in range(105):
        path = f'material-{index}.txt'
        (tmp_path / path).write_text(f'Material {index}')
        target = {'owner': 'repository', 'repository': 'laplace', 'path': path}
        revision = writing_sources.reference_identity(tmp_path, target)['revision']
        bindings.append({'id': f'MAT-fixture-{index}', 'relation': 'uses-material', 'target': target,
                         'consumed_revision': revision, 'version_policy': 'pinned'})
    def fixture(rows):
        rows[0]['manifest']['material_references'] = bindings
    wp._registry_write(tmp_path, fixture)
    (tmp_path / 'additional.txt').write_text('One more reference')
    _attach_repository(tmp_path, project, 'additional.txt')
    first = wp.material_references(project, tmp_path, limit=100)
    assert first['total'] == 106 and len(first['references']) == 100 and first['next_offset'] == 100
    status, _, body = wp.handle('/projects/material-references',
        {'project': project, 'offset': '100', 'limit': '100'}, 'GET', b'', tmp_path)
    second = json.loads(body)
    assert status == 200 and second['offset'] == 100 and len(second['references']) == 6
    assert second['next_offset'] is None and second['total'] == 106
    assert {r['id'] for r in first['references']}.isdisjoint(r['id'] for r in second['references'])


def test_actual_http_general_and_reference_owner_round_trip_without_git(tmp_path, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.request import Request, urlopen
    from laplace.web import scanner
    from laplace.projects import writing_sources
    monkeypatch.setattr(scanner, '_repo_root', lambda: tmp_path)
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), scanner.make_handler())
    thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
    base = f'http://127.0.0.1:{httpd.server_address[1]}'
    def request(path, payload=None):
        req = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
            headers={'X-Laplace-Writing': '1', 'Content-Type': 'application/json'})
        with urlopen(req, timeout=5) as response:
            return response.status, json.loads(response.read())
    try:
        status, made = request('/projects/create', {'name': 'http-company', 'title': 'HTTP Company', 'kind': 'company'})
        assert status == 201 and made['source_optional'] is True and made['capabilities']['concepts'] is False
        source = tmp_path / 'shared-material.txt'; source.write_text('Shared material')
        target = {'owner': 'repository', 'repository': 'laplace', 'path': 'shared-material.txt'}
        _, refs = request('/projects/material-references?project=http-company')
        _, attach = request('/projects/material-references', {'project': 'http-company', 'action': 'attach',
            'expected_revision': refs['revision'], 'target': target,
            'consumed_revision': writing_sources.reference_identity(tmp_path, target)['revision']})
        source.write_text('Changed material')
        _, changed = request('/projects/material-references?project=http-company')
        assert changed['references'][0]['currentness'] == 'CHANGED_INPUT'
        assert changed['references'][0]['consumed_revision'] == attach['reference']['consumed_revision']
        request('/projects/material-references', {'project': 'http-company', 'action': 'adopt',
            'expected_revision': changed['revision'], 'id': attach['reference']['id'],
            'consumed_revision': changed['references'][0]['current_revision']})
        _, current = request('/projects/material-references?project=http-company')
        assert current['references'][0]['currentness'] == 'CURRENT'
        assert not (tmp_path / '.git').exists() and not list(tmp_path.rglob('*.tex'))
        assert source.read_text() == 'Changed material'
    finally:
        httpd.shutdown(); httpd.server_close(); thread.join(timeout=2)


def test_cross_layout_creates_claim_one_identity_without_orphan_home(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    payload = {'name': 'one-identity', 'title': 'One Identity'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda kind: wp.create({**payload, 'kind': kind}, tmp_path), ['general', 'paper']))
    assert sorted(status for status, _ in outcomes) == [201, 409]
    assert len(json.loads((tmp_path / 'registry_projects.json').read_text())['projects']) == 1
    homes = [tmp_path / 'writing_projects/one-identity', tmp_path / 'synthetics papers/one-identity']
    assert sum(path.exists() for path in homes) == 1


def test_failed_paper_creation_does_not_delete_partial_or_authored_source(tmp_path, monkeypatch):
    from laplace.pipeline import authoring
    def fail(project, payload, repo_root=None):
        source = tmp_path / 'synthetics papers/partial-paper/manuscript/Partial-Paper.tex'
        source.write_text(source.read_text() + '\n% Author annotation during setup\n')
        raise ValueError('framing fixture failure')
    monkeypatch.setattr(authoring, 'save', fail)
    status, result = wp.create({'name': 'partial-paper', 'title': 'Partial Paper', 'kind': 'paper'}, tmp_path)
    assert status == 500 and result['creation_status'] == 'failed'
    source = tmp_path / 'synthetics papers/partial-paper/manuscript/Partial-Paper.tex'
    assert 'Author annotation' in source.read_text()
    assert wp._library(tmp_path)['projects'][0]['creation']['status'] == 'failed'
    assert wp.create({'name': 'partial-paper', 'title': 'Retry', 'kind': 'paper'}, tmp_path)[0] == 409


def test_consumer_dereferences_producer_artifact_through_stored_binding(tmp_path):
    from laplace.writing import operations
    producer, consumer = _general(tmp_path, 'producer-work'), _general(tmp_path)
    def store(project, text, expected=None):
        guard = {'before': None} if expected is None else {'expected_revision': expected}
        return operations._execute(tmp_path, project, 'discuss', 'store_artifact',
            {'path': 'notes.txt', 'scope': 'project', 'content': text, **guard})
    owned = store(producer, 'Producer material')
    store(consumer, 'Consumer material at the same relative path')
    attached = wp.change_material_reference(consumer, {'action': 'attach',
        'target': {'owner': 'artifact', 'project': producer, 'path': 'notes.txt', 'scope': 'project'},
        'consumed_revision': owned['revision'], 'expected_revision': wp.metadata(consumer, tmp_path)['revision']}, tmp_path)
    handle = wp.material_references(consumer, tmp_path)['references'][0]['read_handle']
    assert handle['project'] == consumer and handle['operation'] == 'material_references'
    observed = wp.material_references(consumer, tmp_path, **handle['payload'], limit=8)
    assert observed['owner_result']['content'] == 'Producer' and observed['currentness'] == 'CURRENT'
    assert observed['target']['project'] == producer
    assert 'update_handle' not in observed['owner_result']
    remainder = wp.material_references(consumer, tmp_path, **observed['read_handle']['payload'])
    assert remainder['owner_result']['content'] == ' materia'
    assert wp.metadata(consumer, tmp_path)['revision'] == attached['revision']
    store(producer, 'Changed producer material', owned['revision'])
    current = wp.material_references(consumer, tmp_path, **handle['payload'])
    assert current['owner_result']['content'] == 'Changed producer material'
    assert current['currentness'] == 'CHANGED_INPUT'
    assert current['consumed_revision'] == owned['revision']
    status, _, data = wp.handle('/projects/material-references',
        {'project': consumer, 'id': attached['reference']['id'], 'view': 'source', 'limit': '7'}, 'GET', b'', tmp_path)
    assert status == 200 and json.loads(data)['owner_result']['content'] == 'Changed'
    (tmp_path / 'writing_projects/producer-work/notes.txt').unlink()
    assert wp.material_references(consumer, tmp_path, **handle['payload'])['currentness'] == 'UNRESOLVED'


def test_repository_material_source_reads_bound_content_without_body_copy(tmp_path):
    project = _general(tmp_path)
    source = tmp_path / 'material.txt'; source.write_text('π shared material')
    attached = _attach_repository(tmp_path, project)
    read = wp.material_references(project, tmp_path, id=attached['reference']['id'], view='source', limit=2)
    assert read['owner_result']['content'] == 'π ' and read['owner_result']['next_offset'] == 2
    assert read['units'].startswith('Unicode characters')
    assert read['owner_result']['source']['path'] == 'material.txt'
    assert read['owner_result']['source']['repository'] == 'laplace'
    assert not (tmp_path / 'writing_projects/consumer-work/material.txt').exists()
    remainder = wp.material_references(project, tmp_path, **read['read_handle']['payload'])
    assert remainder['owner_result']['content'] == 'sh'
    assert wp.metadata(project, tmp_path)['revision'] == attached['revision']


def test_active_consumer_tool_and_native_routes_read_producer_with_receipt(tmp_path):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    from laplace.native.contracts import CONTRACTS
    from laplace.native.declarations import HTTP_DECLARATIONS
    producer, consumer = _general(tmp_path, 'producer-work'), _general(tmp_path)
    stored = writing_tools.execute(tmp_path, producer, 'discuss', 'store_artifact',
        {'path': 'notes.txt', 'scope': 'project', 'before': None, 'content': 'Producer material', 'reason':'Owned material consumer fixture'})
    read = writing_tools.execute(tmp_path, consumer, 'discuss', 'material_references', {})
    changed = writing_tools.execute(tmp_path, consumer, 'discuss', 'material_reference_change',
        {'action': 'attach', 'target': {'owner': 'artifact', 'project': producer, 'path': 'notes.txt', 'scope': 'project'},
         'consumed_revision': stored['revision'], 'expected_revision': read['revision']})
    payload = {'view': 'source', 'id': changed['reference']['id'], 'limit': 8}
    result = writing_tools.execute(tmp_path, consumer, 'discuss', 'material_references', payload, turn_id='fixture-consumer-turn')
    assert result['owner_result']['content'] == 'Producer' and result['currentness'] == 'CURRENT'
    assert result['read_receipt']['project'] == consumer
    assert result['read_receipt']['operation'] == 'material_references'
    assert result['read_receipt']['id'].startswith('READ-')
    native = writing_tools.request(tmp_path, consumer, 'discuss', {'verb': 'read', 'concept': 'material-reference@project',
        'target': consumer + '::' + payload['id'], 'expected': [], 'payload': payload, 'by': 'author'}, turn_id='fixture-consumer-turn')
    assert native['ok'] is True, native
    native_read = native['owner_response']
    assert native_read['owner_result']['content'] == 'Producer'
    assert native_read['read_receipt']['project'] == consumer
    assert 'update_handle' not in native_read['owner_result']
    assert CONTRACTS['material_references']['input'] == wp.material_reference_contract()['read']
    assert CONTRACTS['material_reference_change']['input'] == wp.material_reference_contract()['write']
    assert HTTP_DECLARATIONS['projects/material-references'].payload == wp.material_reference_contract()['read']
    assert HTTP_DECLARATIONS['projects/material-reference-change'].payload == wp.material_reference_contract()['write']
    help_result = writing_tools.execute(tmp_path, consumer, 'discuss', 'help', {'operation': 'material_reference_change'})
    assert 'expected_revision' in json.dumps(help_result) and 'project-metadata' in json.dumps(help_result)
    catalogue = writing_tools.execute(tmp_path, consumer, 'discuss', 'help', {'concept': 'material-reference@project'})
    assert 'material_references' in json.dumps(catalogue) and 'material_reference_change' in json.dumps(catalogue)
    assert grammar.concept_object('material-reference@project') in grammar.HOME_KINDS
    from laplace.native import verbs as writing_verbs
    remove = {'action': 'remove', 'id': changed['reference']['id'], 'expected_revision': changed['revision']}
    act = writing_verbs.classify('material_reference_change', remove, project=consumer, root=tmp_path)
    removed = writing_tools.request(tmp_path, consumer, 'discuss', act.request, turn_id='fixture-consumer-turn')
    assert removed['ok'] is True, removed
    assert removed['owner_response']['action'] == 'remove'
    assert wp.material_references(consumer, tmp_path)['references'] == []



def test_unbound_preview_shares_native_http_owner_and_persists_no_membership(tmp_path):
    from laplace.native import tools as writing_tools
    from laplace.core import grammar
    consumer = _general(tmp_path)
    source = tmp_path / 'inspect-material.txt'; source.write_text('Inspect before adoption')
    target = {'owner': 'repository', 'repository': 'laplace', 'path': source.name}
    before = wp.metadata(consumer, tmp_path)
    preview = writing_tools.execute(tmp_path, consumer, 'discuss', 'material_references',
        {'view': 'preview', 'target': target, 'limit': 7})
    assert preview['currentness'] == 'UNBOUND' and preview['consumed_revision'] is None
    assert preview['owner_result']['content'] == 'Inspect'
    assert preview['revision'] == before['revision'] and preview['id'] is None
    native = writing_tools.request(tmp_path, consumer, 'discuss', {'verb': 'read', 'concept': 'material-reference@project',
        'target': consumer, 'expected': [], 'payload': grammar.to_payload({'view': 'preview', 'target': target, 'limit': 7}), 'by': 'author'})
    assert native['ok'] is True and native['owner_response']['currentness'] == 'UNBOUND'
    status, _, body = wp.handle('/projects/material-references',
        {'project': consumer, 'view': 'preview', 'target': json.dumps(target), 'limit': '7'}, 'GET', b'', tmp_path)
    assert status == 200 and json.loads(body)['current_revision'] == preview['current_revision']
    assert wp.material_references(consumer, tmp_path)['references'] == []
    assert wp.metadata(consumer, tmp_path)['revision'] == before['revision']
    linked = writing_tools.execute(tmp_path, consumer, 'discuss', 'material_reference_change',
        {'action': 'attach', 'target': target, 'consumed_revision': preview['current_revision'],
         'expected_revision': preview['revision']})
    assert linked['reference']['consumed_revision'] == preview['current_revision']
    assert source.read_text() == 'Inspect before adoption'


def test_general_project_metadata_capabilities_and_conversation_start_without_source(tmp_path, monkeypatch):
    from laplace.native import tools as writing_tools
    from laplace.writing import turn_admission
    from laplace.writing import turn_jobs
    from laplace.writing import session_reads
    project = _general(tmp_path)
    metadata = writing_tools.execute(tmp_path, project, 'discuss', 'project_metadata', {})
    library = wp._library(tmp_path)['projects'][0]
    assert metadata['capabilities'] == library['capabilities']
    assert metadata['source_optional'] is True and metadata['capabilities']['manuscript'] is False
    prompts = []
    class Provider:
        def __init__(self, *args, **kwargs): pass
        def run(self, prompt):
            prompts.append(prompt)
            return {'status': 'completed', 'text': 'The general project conversation is available.',
                    'turn_id': 'fixture-native-turn'}
    monkeypatch.setattr(writing_provider, 'WritingTurn', Provider)
    started = turn_admission.start_turn(tmp_path, {'project': project, 'provider': 'codex',
        'mode': 'discuss', 'text': 'Discuss this project purpose.'})
    job = turn_jobs._JOBS[started['turn_id']]
    with job['condition']:
        assert job['condition'].wait_for(lambda: job['done'], timeout=5)
    session = session_reads.session_state(tmp_path, started['session_id'])
    turn = next(row for row in session['turns'] if row['id'] == started['turn_id'])
    assert turn['reply']['text'] == 'The general project conversation is available.', turn
    assert prompts and 'Discuss this project purpose.' in prompts[0]
    assert not list(tmp_path.rglob('*.tex'))


def test_material_owner_choices_are_declared_aliases_and_bound_source_carries_guard(tmp_path):
    project = _general(tmp_path)
    profiles = tmp_path / 'profiles'; profiles.mkdir()
    source_home = tmp_path / 'external'; source_home.mkdir()
    (source_home / 'notes.txt').write_text('Declared source material')
    (profiles / 'writing_sources.json').write_text(json.dumps({'repositories': {'declared-owner': 'external', 'offline-owner': 'not-present'}}))
    listed = wp.material_references(project, tmp_path)
    choices = listed['owners']['repositories']
    assert [row['id'] for row in choices] == ['declared-owner', 'offline-owner']
    assert choices[0]['available'] is True and choices[1]['available'] is False
    target = {'owner': 'repository', 'repository': 'declared-owner', 'path': 'notes.txt'}
    preview = wp.material_references(project, tmp_path, view='preview', target=target)
    changed = wp.change_material_reference(project, {'action': 'attach', 'target': target,
        'expected_revision': preview['revision'], 'consumed_revision': preview['current_revision']}, tmp_path)
    read = wp.material_references(project, tmp_path, view='source', id=changed['reference']['id'])
    assert read['revision'] == changed['revision']
    caps = wp.metadata(project, tmp_path)['capabilities']
    # campaign research visibility (2026-10-14): the Research owner serves a source-optional project, so
    # Research is visible; the manuscript-specific readers stay off without a manuscript
    assert caps['research'] is True and caps['review'] is False and caps['presentation'] is False


def _follow_material_http(root, handle):
    from urllib.parse import urlsplit, parse_qs
    parts=urlsplit(handle['http']['url'])
    assert handle['http']['method']=='GET'
    code,_,raw=wp.handle(parts.path,parse_qs(parts.query),'GET',b'',repo_root=root)
    assert code==200, raw
    return json.loads(raw)


def test_unicode_preview_and_workspace_source_have_identical_http_native_continuation(tmp_path):
    project=_general(tmp_path)
    text='π🌱é中 successive source pages';(tmp_path/'material.txt').write_text(text)
    target={'owner':'repository','repository':'laplace','path':'material.txt'}
    preview=wp.material_references(project,tmp_path,view='preview',target=target,limit=2)
    content='';page=preview
    while True:
        content+=page['owner_result']['content']
        handle=page.get('read_handle')
        if not handle:break
        assert handle['payload']['target']==target and handle['payload']['limit']==2
        assert handle['payload']['offset']==len(content)
        page=wp.material_references(project,tmp_path,**handle['payload'])
        assert page==_follow_material_http(tmp_path,handle)
    assert content==text and preview['currentness']=='UNBOUND'
    attached=_attach_repository(tmp_path,project)
    page=wp.material_references('',tmp_path,view='workspace-source',consumer=project,id=attached['reference']['id'],limit=2)
    handle=page['read_handle']
    assert handle['project']==project and handle['payload']['consumer']==project
    assert handle['payload']['view']=='workspace-source' and handle['payload']['id']==attached['reference']['id']
    assert wp.material_references('',tmp_path,**handle['payload'])==_follow_material_http(tmp_path,handle)
    assert page['restart_read']['payload']['consumer']==project
    assert page['restart_read']['payload']['view']=='workspace-source'


def test_artifact_continuation_retains_byte_units(tmp_path):
    from laplace.native import tools as writing_tools
    project=_general(tmp_path)
    writing_tools.execute(tmp_path,project,'work','store_artifact',{'path':'bytes.txt','scope':'project','before':None,'content':'πabc','reason':'Owned byte continuation fixture'})
    page=wp.material_references(project,tmp_path,view='preview',target={'owner':'artifact','project':project,'scope':'project','path':'bytes.txt'},limit=2)
    assert page['owner_result']['content']=='π' and page['units'].startswith('UTF-8 byte')
    handle=page['read_handle'];assert handle['payload']['offset']==2
    assert _follow_material_http(tmp_path,handle)['owner_result']['content']=='ab'


def test_pdf_source_continuation_preserves_range_then_advances_pages(tmp_path,monkeypatch):
    from laplace.projects import writing_sources
    project=_general(tmp_path);(tmp_path/'pages.pdf').write_bytes(b'pdf fixture')
    def run(argv):
        if argv[0]=='pdfinfo':return b'Pages: 5\n'
        assert argv[0]=='pdftotext'
        return 'π🌱abcd'.encode()
    monkeypatch.setattr(writing_sources,'_tool',lambda name:name)
    monkeypatch.setattr(writing_sources,'_run',run)
    target={'owner':'repository','repository':'laplace','path':'pages.pdf'}
    first=wp.material_references(project,tmp_path,view='preview',target=target,page=2,page_count=2,limit=2)
    handle=first['read_handle'];assert handle['payload']['page']==2 and handle['payload']['page_count']==2
    assert handle['payload']['offset']==2 and _follow_material_http(tmp_path,handle)['owner_result']['content']=='ab'
    last=wp.material_references(project,tmp_path,**{**handle['payload'],'offset':4})
    next_page=last['read_handle']['payload']
    assert next_page['page']==4 and next_page['page_count']==2 and next_page['offset']==0 and next_page['limit']==2
    assert _follow_material_http(tmp_path,last['read_handle'])['owner_result']['pdf_page_end']==5
    assert first['restart_read']['payload']['page']==2 and first['restart_read']['payload']['page_count']==2


# CAMPAIGN RESEARCH VISIBILITY (2026-10-14): a registered source-optional project shows Research exactly when the
# Research owner serves it from inside the project's own home; create, library and metadata project the same
# capability; manuscript-specific capabilities are unchanged; a result recorded through the owner is in its catalogue.
def _caps_everywhere(root, project, created=None):
    library = next(row for row in wp._library(root)['projects'] if row['name'] == project)
    code, _, raw = wp.handle('/projects/metadata', {'project': [project]}, 'GET', b'', repo_root=root)
    assert code == 200
    rows = [library['capabilities'], wp.metadata(project, root)['capabilities'], json.loads(raw)['capabilities']] + ([created['capabilities']] if created else [])
    assert all(row == rows[0] for row in rows), rows
    return rows[0]


def test_an_empty_source_optional_project_shows_its_research_catalogue_and_nothing_manuscript_specific(tmp_path):
    from laplace.web import research_surface
    from laplace.research import research_context
    status, created = wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general', 'purpose': 'Audit the sources.'}, tmp_path)
    assert status == 201 and created['source_optional'] is True
    caps = _caps_everywhere(tmp_path, 'campaign', created)
    assert caps['research'] is True
    assert {key: caps[key] for key in ('manuscript', 'reader_plan', 'concepts', 'review', 'presentation')} == dict.fromkeys(('manuscript', 'reader_plan', 'concepts', 'review', 'presentation'), False)
    assert caps['start_manuscript'] is True and caps['work'] and caps['materials']
    home = research_context.owner_home('campaign', tmp_path)
    assert home.is_relative_to((tmp_path / 'writing_projects' / 'campaign').resolve())
    code, _, raw = research_surface.handle('/research/state', {'project': ['campaign'], 'view': ['summary']}, 'GET', b'', repo_root=tmp_path)
    value = json.loads(raw)
    assert code == 200 and value['results'] == [] and value['read_only'] is False
    assert not list(tmp_path.rglob('*.tex')), 'no manuscript was invented'


def test_a_result_recorded_through_the_research_owner_is_in_the_campaign_catalogue(tmp_path):
    from laplace.web import research_surface
    from laplace.research import research_context
    from laplace.research import research_records
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general'}, tmp_path)[0] == 201
    home = research_context.owner_home('campaign', tmp_path)
    (home / 'audit.json').write_text('{"sources_checked": 63}')
    status, made = research_records.record('campaign', {'kind': 'result', 'id': 'result:source-audit', 'result': 'audit.json', 'title': 'Source audit',
        'summary': 'A historical diagnostic audit.', 'measures': [{'label': 'Sources checked', 'key': 'sources_checked'}]}, tmp_path)
    assert status == 201, made
    assert _caps_everywhere(tmp_path, 'campaign')['research'] is True
    summary = json.loads(research_surface.handle('/research/state', {'project': ['campaign'], 'view': ['summary']}, 'GET', b'', repo_root=tmp_path)[2])
    assert [row['id'] for row in summary['results']] == ['result:source-audit']
    exact = json.loads(research_surface.handle('/research/result', {'project': ['campaign'], 'id': ['result:source-audit']}, 'GET', b'', repo_root=tmp_path)[2])
    assert exact['exact'] is True and exact['result']['measurements'] == [{'label': 'Sources checked', 'key': 'sources_checked', 'value': 63}]
    assert not list(tmp_path.rglob('*.tex'))


def test_research_is_not_shown_through_the_owners_repository_root_manuscript_fallback(tmp_path):
    import shutil
    from laplace.research import research_context
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general'}, tmp_path)[0] == 201
    shutil.rmtree(tmp_path / 'writing_projects' / 'campaign' / 'manuscript')
    (tmp_path / 'manuscript').mkdir()
    # the owner's legacy fallback would serve the repository-root manuscript; that is not this project's research
    assert research_context.owner_home('campaign', tmp_path) == (tmp_path / 'manuscript').resolve()
    assert _caps_everywhere(tmp_path, 'campaign')['research'] is False


def test_manuscript_specific_capabilities_are_unchanged_when_a_campaign_starts_a_manuscript(tmp_path):
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general'}, tmp_path)[0] == 201
    before = _caps_everywhere(tmp_path, 'campaign')
    status, draft = wp.start_manuscript({'project': 'campaign', 'title': 'Audit report', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    after = _caps_everywhere(tmp_path, 'campaign')
    assert before['research'] is True and after['research'] is True
    assert after['manuscript'] is True and after['review'] is True and after['presentation'] is True and after['start_manuscript'] is False
    # M5 bootstrap: Add manuscript is the human door of the project lifecycle, so the same source-optional project
    # now owns its reader/argument plan; a manuscript started WITHOUT plan ownership keeps concepts off
    # (tests/test_json_record_reads.py availability test) until the guarded start_authoring
    assert after['concepts'] is True and after['reader_plan'] is True and after['start_planning'] is False
