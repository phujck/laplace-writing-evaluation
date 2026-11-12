"""CAMPAIGN MANUSCRIPT STATE HOME (2026-10-14): when a registered source-optional project starts (selects) its
first manuscript through the owner, its project-owned Research, references and research figures stay where
they are (the declared state home) with the same ids, pins and readable native and human links, while the
selected source, its edits and its compile root move to the new draft. Paper and read-only fences unchanged.
Disposable synthetic projects only; nothing is copied or relocated."""
import hashlib
import json
from urllib.parse import urlencode, urlsplit, parse_qs

from laplace.manuscript import manuscript_source, manuscript_structure
from laplace.research import references_surface
from laplace.web import research_surface
from laplace.projects import library as wp
from laplace.native import tools as writing_tools
from laplace.research import research_context
from laplace.research import research_records


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _campaign(root):
    """A source-optional project with an indexed result, a run output, a research figure and a local reference."""
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general', 'purpose': 'Audit the sources.'}, root)[0] == 201
    home = research_context.owner_home('campaign', root)
    assert home == (root / 'writing_projects' / 'campaign' / 'manuscript').resolve()
    (home / 'research_runs').mkdir()
    (home / 'research_runs' / 'run-1.result.json').write_text('{"recall": 0.75}')
    (home / 'figures').mkdir()
    (home / 'figures' / 'recall.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>recall 0.75</text></svg>')
    status, made = research_records.record('campaign', {'kind': 'result', 'id': 'result:recall', 'result': 'research_runs/run-1.result.json',
        'title': 'Recall', 'summary': 'A bounded synthetic measurement.', 'measures': [{'label': 'Recall', 'key': 'recall'}]}, root)
    assert status == 201, made
    paper = root / 'supplied-paper.pdf'
    paper.write_bytes(b'%PDF-1.4\n% synthetic reference\n%%EOF')
    imported = writing_tools.execute(root, 'campaign', 'work', 'literature_import',
        {'metadata': {'title': 'Synthetic reference'}, 'provenance': {'description': 'Supplied locally', 'path': str(paper)}})
    return home, imported['association']['key']


def _observe(root, key):
    """Everything a person or a native turn reads of the project's own evidence."""
    summary = json.loads(research_surface.handle('/research/state', {'project': ['campaign'], 'view': ['summary']}, 'GET', b'', repo_root=root)[2])
    exact = json.loads(research_surface.handle('/research/result', {'project': ['campaign'], 'id': ['result:recall']}, 'GET', b'', repo_root=root)[2])
    native = writing_tools.execute(root, 'campaign', 'work', 'research', {'view': 'result', 'id': 'result:recall'})
    artifacts = {}
    for path in ('research_runs/run-1.result.json', 'figures/recall.svg'):
        code, mime, body = research_surface.handle('/research/artifact', {'project': ['campaign'], 'scope': ['manuscript'], 'path': [path]}, 'GET', b'', repo_root=root)
        pinned = research_surface.handle('/research/artifact', {'project': ['campaign'], 'scope': ['manuscript'], 'path': [path],
                                                                'expected_sha256': [hashlib.sha256(body if isinstance(body, bytes) else body.encode()).hexdigest()]}, 'GET', b'', repo_root=root)
        artifacts[path] = (code, hashlib.sha256(body if isinstance(body, bytes) else body.encode()).hexdigest(), pinned[0])
    reference = writing_tools.execute(root, 'campaign', 'work', 'reference_source', {'key': key})
    code, mime, pdf = references_surface.handle('/references/source', {'project': ['campaign'], 'key': [key], 'format': ['pdf']}, 'GET', b'', repo_root=root)
    return {'results': [(row['id'], row['revision']) for row in summary['results']], 'exact': (exact['exact'], exact['result']['revision'], exact['result']['measurements']),
            'native': (native['result']['id'], native['result']['revision']), 'artifacts': artifacts,
            'reference': (reference['available'], reference['kind'], reference['pdf_url']), 'reference_pdf': (code, hashlib.sha256(pdf).hexdigest())}


def test_starting_a_manuscript_keeps_project_evidence_reachable_and_moves_only_the_selected_source(tmp_path):
    home, key = _campaign(tmp_path)
    before_files = {str(p.relative_to(tmp_path)): _sha(p) for p in home.rglob('*') if p.is_file()}
    before = _observe(tmp_path, key)
    assert before['results'] and before['exact'][0] is True and before['reference'][0] is True
    assert all(code == 200 and pinned == 200 for code, _sha256, pinned in before['artifacts'].values())
    # the real owner door the app's Home "Add manuscript" uses
    status, draft = wp.start_manuscript({'project': 'campaign', 'title': 'Audit report', 'kind': 'paper'}, tmp_path)
    assert status == 201, draft
    source = manuscript_source.resolve('campaign', repo_root=tmp_path)
    assert source['status'] == 'resolved' and source['root'].startswith('writing_projects/campaign/manuscript/working-draft/')
    assert source['manuscript_dir'] == 'writing_projects/campaign/manuscript/working-draft'
    assert manuscript_source.project_state_dir(source, tmp_path) == 'writing_projects/campaign/manuscript' == source['storage_dir']
    after = _observe(tmp_path, key)
    assert after == before, 'the same ids, revisions, pins, measurements and readable native/human links'
    assert {k: v for k, v in ((str(p.relative_to(tmp_path)), _sha(p)) for p in home.rglob('*') if p.is_file()) if k in before_files} == before_files, 'no evidence byte moved or changed'
    assert not (home / 'working-draft' / 'research_records.json').exists() and not list((home / 'working-draft').rglob('*.result.json')), 'nothing copied into the draft'
    # a new result lands in the same state home, beside the old ones
    (home / 'research_runs' / 'run-2.result.json').write_text('{"recall": 0.8}')
    assert research_records.record('campaign', {'kind': 'result', 'id': 'result:recall-2', 'result': 'research_runs/run-2.result.json', 'title': 'Recall 2'}, tmp_path)[0] == 201
    rows = json.loads(research_surface.handle('/research/state', {'project': ['campaign'], 'view': ['summary']}, 'GET', b'', repo_root=tmp_path)[2])['results']
    assert {row['id'] for row in rows} == {'result:recall', 'result:recall-2'}
    # selected-source edits and the compile root follow the draft
    root_file = tmp_path / source['root']
    chapter = manuscript_structure.create_chapter('campaign', 'Findings', tmp_path, expected_root_digest=_sha(root_file))
    assert (tmp_path / chapter['file']).is_relative_to(tmp_path / 'writing_projects/campaign/manuscript/working-draft')
    assert '\\input{' in root_file.read_text() and manuscript_source.resolve('campaign', repo_root=tmp_path)['root'] == source['root']
    assert not (home / 'chapters').exists(), 'the edit did not land in the state home'


def test_paper_and_read_only_layouts_keep_their_selected_coordinate(tmp_path):
    from test_manuscript_structure import _section_fixture
    _section_fixture(tmp_path)
    paper = manuscript_source.resolve('book', repo_root=tmp_path)
    assert manuscript_source.project_state_dir(paper, tmp_path) == paper['manuscript_dir'], 'a paper project is unchanged'
    for fenced in ({**paper, 'read_only': True}, {**paper, 'foreign': True}, {**paper, 'storage_dir': None}):
        assert manuscript_source.project_state_dir(fenced, tmp_path) == paper['manuscript_dir']
    campaign = {'project': 'campaign', 'manuscript_dir': 'a/draft', 'storage_dir': 'a', 'read_only': True}
    assert manuscript_source.project_state_dir(campaign, tmp_path) == 'a/draft', 'a read-only source keeps its existing fence'
    assert manuscript_source.project_state_dir(None, tmp_path) is None


# STATE-R1 (2026-10-14): a manuscript-scoped artifact stored after the first manuscript is selected is read by its
# owner-issued receipt link exactly as natively; the receipt is compared through the artifact owner, not through
# the Research state home, and every identity refusal stands.
def test_a_receipt_backed_manuscript_artifact_link_reads_the_same_bytes_as_native_after_a_manuscript_start(tmp_path):
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general'}, tmp_path)[0] == 201
    assert wp.start_manuscript({'project': 'campaign', 'title': 'Report', 'kind': 'paper'}, tmp_path)[0] == 201
    made = writing_tools.execute(tmp_path, 'campaign', 'work', 'store_artifact', {'path': 'notes/proof.json', 'scope': 'manuscript', 'before': None,
                                 'content': '{"x": "new selected draft"}', 'reason': 'synthetic receipt-link test'})
    state_home = research_context.owner_home('campaign', tmp_path)
    draft = tmp_path / manuscript_source.resolve('campaign', repo_root=tmp_path)['manuscript_dir']
    assert (draft / 'notes' / 'proof.json').is_file() and state_home != draft.resolve()
    (state_home / 'notes').mkdir(parents=True, exist_ok=True)
    (state_home / 'notes' / 'proof.json').write_text('{"x": "shadow at the state home"}')   # a same-name file at the other home
    native = writing_tools.execute(tmp_path, 'campaign', 'review', 'read_artifact', {'id': made['id']})
    query = parse_qs(urlsplit(native['human_read']['url']).query)
    def get(**changes):
        fields = {**{k: v[0] for k, v in query.items()}, **changes}
        fields = {k: [v] for k, v in fields.items() if v is not None}
        return research_surface.handle('/research/artifact', fields, 'GET', b'', repo_root=tmp_path)
    code, _, body = get()
    body = body if isinstance(body, bytes) else body.encode()
    assert code == 200 and body.decode() == native['content'] == '{"x": "new selected draft"}', 'the issued link reads the native bytes, not the shadow'
    assert hashlib.sha256(body).hexdigest() == native['revision']
    for changes, words in (({'artifact_id': 'ART-' + '0' * 32}, ''), ({'path': 'notes/other.json'}, 'does not identify this exact scoped path'),
                           ({'expected_sha256': '1' * 64}, 'differs from the exact artifact receipt'), ({'scope': 'project'}, 'different scope'),
                           ({'owner': 'someone-else'}, 'Unknown artifact reader owner')):
        code, _, refused = get(**changes)
        assert code == 422 and words in json.loads(refused)['error'], (changes, code, refused)
    # ordinary Research routes (no artifact owner) still read the durable state home
    code, _, plain = research_surface.handle('/research/artifact', {'project': ['campaign'], 'scope': ['manuscript'], 'path': ['notes/proof.json']}, 'GET', b'', repo_root=tmp_path)
    assert code == 200 and 'shadow at the state home' in (plain if isinstance(plain, str) else plain.decode())


# M5 P2 reached consumer (Root CUA, 2026-10-14): Material -> Recorded files -> Read of a manuscript-scoped artifact
# saved after Add manuscript rebuilt a bare path URL, reached the state-home shadow and failed its (correct) hash
# guard. The catalogue and History now issue the receipt's canonical human route; it reads the selected draft.
def _owned_after_start(root):
    from laplace.web import project_work_surface
    assert wp.create({'name': 'campaign', 'title': 'Campaign', 'kind': 'general'}, root)[0] == 201
    assert wp.start_manuscript({'project': 'campaign', 'title': 'Report', 'kind': 'paper'}, root)[0] == 201
    made = writing_tools.execute(root, 'campaign', 'work', 'store_artifact', {'path': 'notes/owned-after-start.json', 'scope': 'manuscript',
                                 'before': None, 'content': '{"which":"selected draft"}', 'reason': 'synthetic Material consumer test'})
    state_home = research_context.owner_home('campaign', root)
    (state_home / 'notes').mkdir(parents=True, exist_ok=True)
    (state_home / 'notes' / 'owned-after-start.json').write_text('{"which":"state-home decoy"}')
    code, _, raw = project_work_surface.handle('/work/materials', {'project': ['campaign']}, 'GET', b'', repo_root=root)
    assert code == 200
    row = next(item for item in json.loads(raw)['materials'] if item['path'] == 'notes/owned-after-start.json')
    return made, row


def _get_artifact(root, url):
    query = parse_qs(urlsplit(url).query)
    code, _, body = research_surface.handle('/research/artifact', query, 'GET', b'', repo_root=root)
    return code, body if isinstance(body, bytes) else body.encode()


def test_recorded_material_and_history_rows_open_the_receipt_route_and_read_the_selected_draft(tmp_path):
    from laplace.work import history as author_history
    made, row = _owned_after_start(tmp_path)
    native = writing_tools.execute(tmp_path, 'campaign', 'review', 'read_artifact', {'id': made['id']})
    assert row['id'] == made['id'] and row['scope'] == 'manuscript' and row['recorded_revision'] == native['revision']
    assert row['human_read'] == native['human_read'], 'the catalogue issues exactly the human route read_artifact issues'
    query = parse_qs(urlsplit(row['human_read']['url']).query)
    assert query['owner'] == ['writing-artifact'] and query['artifact_id'] == [made['id']] and query['expected_sha256'] == [native['revision']]
    code, body = _get_artifact(tmp_path, row['human_read']['url'])
    assert code == 200 and body == b'{"which":"selected draft"}' and hashlib.sha256(body).hexdigest() == native['revision']
    # the bare path URL the consumer used to rebuild reaches the shadow and is (correctly) refused by its pin
    bare = '/research/artifact?' + urlencode({'project': 'campaign', 'path': row['path'], 'scope': row['scope'], 'expected_sha256': row['recorded_revision']})
    assert _get_artifact(tmp_path, bare)[0] == 409, 'the identity guard still refuses the decoy'
    # History's artifact activity target carries the same receipt route
    items = author_history.history('campaign', {'limit': 50}, tmp_path)['items']
    targets = [target for item in items for target in item.get('targets') or [] if target.get('kind') == 'artifact']
    assert targets and targets[0]['human_read'] == native['human_read']
    # a receipt without a complete pin issues no partial route
    from laplace.projects import artifacts
    assert artifacts._receipt_human_read('campaign', 'x.json', 'project', None, made['id']) == {}
    assert artifacts._receipt_human_read('campaign', 'x.json', 'project', native['revision'], None) == {}


def test_a_receipt_without_a_complete_pin_reads_current_selected_bytes_through_its_owner_and_says_so(tmp_path):
    """P2 repair1 (Sol P2-R1): an older ART receipt whose pin is missing, null or malformed. The catalogue issues no
    receipt route; the consumer's owner+id request (artifactReaderOptions) reads the CURRENT bytes at the receipt's exact
    selected-draft path and marks the historical identity unavailable. The bare path still reaches the state-home
    decoy, so it is never used; without the owner the old refusal stands."""
    from laplace.core.records import journal
    from laplace.projects import artifacts
    assert wp.create({'name': 'legacy', 'title': 'Legacy', 'kind': 'general'}, tmp_path)[0] == 201
    assert wp.start_manuscript({'project': 'legacy', 'title': 'Draft', 'kind': 'paper'}, tmp_path)[0] == 201
    draft = tmp_path / manuscript_source.resolve('legacy', repo_root=tmp_path)['manuscript_dir']
    home = research_context.owner_home('legacy', tmp_path)
    cases = {'missing': {}, 'null': {'sha256': None}, 'malformed': {'sha256': 'sha256:not-a-digest'}}
    for n, (name, pin) in enumerate(cases.items()):
        for folder, text in [(draft, 'SELECTED DRAFT ' + name), (home, 'STATE-HOME DECOY ' + name)]:
            (folder / 'notes').mkdir(exist_ok=True); (folder / 'notes' / f'{name}.txt').write_text(text)
        journal.bank_row('contract/talk.jsonl', {'record': 'writing-artifact', 'id': 'ART-' + str(n) * 32, 'project': 'legacy',
            'path': (draft / 'notes' / f'{name}.txt').relative_to(tmp_path).as_posix(), 'artifact_path': f'notes/{name}.txt',
            'scope': 'manuscript', **pin}, root=tmp_path)
    rows = {row['path']: row for row in artifacts.catalogue(tmp_path, 'legacy')['materials']}
    for n, name in enumerate(cases):
        row, ident = rows[f'notes/{name}.txt'], 'ART-' + str(n) * 32
        assert row['id'] == ident and 'human_read' not in row, 'no receipt route without a complete pin'
        native = writing_tools.execute(tmp_path, 'legacy', 'review', 'read_artifact', {'id': ident})
        assert native['content'] == 'SELECTED DRAFT ' + name
        coordinates = {'project': 'legacy', 'path': row['path'], 'scope': row['scope'], 'artifact_id': ident, 'owner': 'writing-artifact'}
        code, body = _get_artifact(tmp_path, '/research/artifact?' + urlencode({**coordinates, 'format': 'json'}))
        page = json.loads(body)
        assert code == 200 and page['content'] == 'SELECTED DRAFT ' + name and page['receipt_identity'] == 'unavailable', (name, page)
        assert page['sha256'] == native['revision'], 'the current bytes native read_artifact reads'
        # the reader's inspected-bytes guard (download) checks CURRENT bytes only; another pin is refused
        assert _get_artifact(tmp_path, '/research/artifact?' + urlencode({**coordinates, 'download': 1, 'expected_sha256': page['sha256']})) == (200, ('SELECTED DRAFT ' + name).encode())
        assert _get_artifact(tmp_path, '/research/artifact?' + urlencode({**coordinates, 'expected_sha256': '0' * 64}))[0] == 409
        # unchanged refusals: an id without the explicit owner, a receipt for another scope or path
        assert _get_artifact(tmp_path, '/research/artifact?' + urlencode({k: v for k, v in coordinates.items() if k != 'owner'}))[0] == 422
        assert _get_artifact(tmp_path, '/research/artifact?' + urlencode({**coordinates, 'scope': 'project'}))[0] == 422
        assert _get_artifact(tmp_path, '/research/artifact?' + urlencode({**coordinates, 'path': 'notes/other.txt'}))[0] == 422
        # why the consumer must never rebuild a bare path: it reaches the same-named state-home file
        bare = _get_artifact(tmp_path, '/research/artifact?' + urlencode({'project': 'legacy', 'path': row['path'], 'scope': 'manuscript', 'format': 'json'}))
        assert json.loads(bare[1])['content'] == 'STATE-HOME DECOY ' + name
