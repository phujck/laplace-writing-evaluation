"""Regenerate tests/fixtures/shell/owner-answers.json: the real HTTP owners' answers on a disposable synthetic
book project (tests/test_manuscript_structure._section_fixture), for the shell render-coverage harness.
Run: scripts/laplace-python tests/fixtures/shell/generate_owner_answers.py"""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, 'tests')
from test_manuscript_structure import _section_fixture
from laplace.web import authoring as authoring_surface, project_work_surface

out = {}
with tempfile.TemporaryDirectory(prefix='shell-owners-') as raw:
    root = Path(raw)
    _section_fixture(root)
    authoring_surface._root = lambda: root
    def http(handler, path, query, **kw):
        code, _, body = handler(path, {k: [v] for k, v in query.items()}, 'GET', b'', **kw)
        assert code == 200, (path, query, code, body[:300])
        return json.loads(body)
    out['document'] = http(authoring_surface.handle, '/authoring/document', {'project': 'book'})
    out['document_derived'] = http(authoring_surface.handle, '/authoring/document', {'project': 'book', 'target_kind': 'derived'})
    out['outline'] = http(project_work_surface.handle, '/work/structure', {'project': 'book', 'view': 'outline', 'limit': '25'}, repo_root=root)
    # campaign research visibility (2026-10-14): a source-optional general project, empty and then with one
    # canonical result recorded through the Research owner (no manuscript)
    from laplace.projects import library as writing_projects; from laplace.web import research_surface
    from laplace.research import research_context
    from laplace.research import research_records
    assert writing_projects.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general', 'purpose': 'Audit the sources.'}, root)[0] == 201
    out['campaign_metadata'] = http(writing_projects.handle, '/projects/metadata', {'project': 'campaign'}, repo_root=root)
    out['campaign_research_empty'] = http(research_surface.handle, '/research/state', {'project': 'campaign', 'view': 'summary'}, repo_root=root)
    home = research_context.owner_home('campaign', root)
    (home / 'audit.json').write_text('{"sources_checked": 63}')
    status, made = research_records.record('campaign', {'kind': 'result', 'id': 'result:source-audit', 'result': 'audit.json', 'title': 'Source audit',
        'question': 'Which shared sources were checked?', 'summary': 'A historical diagnostic audit of the shared sources.',
        'limitations': 'Diagnostic only; no new experiment.', 'measures': [{'label': 'Sources checked', 'key': 'sources_checked'}]}, root)
    assert status == 201, made
    out['campaign_research_result'] = http(research_surface.handle, '/research/state', {'project': 'campaign', 'view': 'summary'}, repo_root=root)
    out['campaign_research_exact'] = http(research_surface.handle, '/research/result', {'project': 'campaign', 'id': 'result:source-audit'}, repo_root=root)
    # M5 P2 reached Material consumer: a manuscript-scoped artifact saved after Add manuscript, with a same-path
    # decoy in the state home; the materials answer, the owner page of its receipt route, and the bare-path refusal
    from laplace.native import tools as writing_tools; from laplace.web import project_work_surface
    assert writing_projects.create({'name': 'drafted', 'title': 'Drafted', 'kind': 'general'}, root)[0] == 201
    assert writing_projects.start_manuscript({'project': 'drafted', 'title': 'Report', 'kind': 'paper'}, root)[0] == 201
    writing_tools.execute(root, 'drafted', 'work', 'store_artifact', {'path': 'notes/owned-after-start.json', 'scope': 'manuscript',
        'before': None, 'content': '{"which":"selected draft"}', 'reason': 'synthetic Material consumer fixture'})
    decoy = research_context.owner_home('drafted', root) / 'notes'
    decoy.mkdir(parents=True, exist_ok=True); (decoy / 'owned-after-start.json').write_text('{"which":"state-home decoy"}')
    out['drafted_materials'] = http(project_work_surface.handle, '/work/materials', {'project': 'drafted'}, repo_root=root)
    row = next(item for item in out['drafted_materials']['materials'] if item['path'] == 'notes/owned-after-start.json')
    from urllib.parse import parse_qs, urlsplit
    receipt = {key: value[0] for key, value in parse_qs(urlsplit(row['human_read']['url']).query).items()}
    page_query = {**receipt, 'format': 'json', 'offset': '0', 'limit': '32768'}
    out['drafted_receipt_page'] = http(research_surface.handle, '/research/artifact', page_query, repo_root=root)
    code, _, body = research_surface.handle('/research/artifact', {key: [value] for key, value in {
        'project': 'drafted', 'path': row['path'], 'scope': row['scope'], 'format': 'json', 'offset': '0', 'limit': '32768',
        'expected_sha256': row['recorded_revision']}.items()}, 'GET', b'', repo_root=root)
    assert code == 409, (code, body[:200])
    out['drafted_bare_refusal'] = {'status': code, 'body': json.loads(body)}
    # P2 repair1: older receipts whose pin is missing, null or malformed, in the same draft/state-home split: the
    # materials answer, the owner's current-bytes page for owner+id (the consumer's request) and the bare-path answer,
    # which reaches the state-home decoy (200) and must never be requested
    from laplace.manuscript import manuscript_source
    from laplace.core.records import journal
    draft = root / manuscript_source.resolve('drafted', repo_root=root)['manuscript_dir']
    legacy = {'missing': {}, 'null': {'sha256': None}, 'malformed': {'sha256': 'sha256:not-a-digest'}}
    for n, (name, pin) in enumerate(legacy.items()):
        (draft / 'notes' / f'legacy-{name}.txt').write_text(f'selected draft {name}'); (decoy / f'legacy-{name}.txt').write_text(f'state-home decoy {name}')
        journal.bank_row('contract/talk.jsonl', {'record': 'writing-artifact', 'id': 'ART-' + 'abc'[n] * 32, 'project': 'drafted',
            'path': (draft / 'notes' / f'legacy-{name}.txt').relative_to(root).as_posix(), 'artifact_path': f'notes/legacy-{name}.txt',
            'scope': 'manuscript', **pin}, root=root)
    out['drafted_legacy_materials'] = http(project_work_surface.handle, '/work/materials', {'project': 'drafted'}, repo_root=root)
    page = {'format': 'json', 'offset': '0', 'limit': '32768'}
    out['drafted_legacy_pages'] = {row['id']: http(research_surface.handle, '/research/artifact', {'project': 'drafted', 'path': row['path'],
        'scope': row['scope'], 'artifact_id': row['id'], 'owner': 'writing-artifact', **page}, repo_root=root)
        for row in out['drafted_legacy_materials']['materials'] if row['path'].startswith('notes/legacy-')}
    out['drafted_legacy_bare'] = {row['path']: http(research_surface.handle, '/research/artifact', {'project': 'drafted', 'path': row['path'],
        'scope': row['scope'], **page}, repo_root=root) for row in out['drafted_legacy_materials']['materials'] if row['path'].startswith('notes/legacy-')}
text = json.dumps(out, indent=1, ensure_ascii=False).replace(str(root), '<root>')
Path('tests/fixtures/shell/owner-answers.json').write_text(text + '\n')
print({k: len(json.dumps(v)) for k, v in out.items()})
