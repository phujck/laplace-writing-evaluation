import base64
import json
from pathlib import Path
import shutil

import pytest

from laplace.projects import library as writing_projects, writing_sources
from laplace.native import tools as writing_tools, declarations as writing_declarations


@pytest.fixture
def roots(tmp_path):
    root = tmp_path / 'laplace'
    root.mkdir()
    paths = {'laplace': root, 'atlas': root / 'atlas',
             'eigenengine': tmp_path / 'eigenengine',
             'physics-paper-orchestra': tmp_path / 'physics_paper_orchestra'}
    for path in paths.values():
        path.mkdir(exist_ok=True)
        (path / 'source.md').write_text('First α line\nReflexive representation\nLast line\n')
    (root / 'profiles').mkdir()
    (root / 'profiles/writing_sources.json').write_text(json.dumps({
        'repositories': {key: str(path) for key, path in paths.items()}}))
    return root, paths


def test_all_authorised_repositories_are_readable_with_bounded_source_identity(roots):
    root, paths = roots
    result = writing_tools.execute(root, 'book', 'discuss', 'repository', {'action': 'list'})
    assert {r['id'] for r in result['repositories']} == set(paths)
    assert all(r['available'] and r['access'] == 'read-only' for r in result['repositories'])
    for key, path in paths.items():
        parts, offset = [], 0
        while True:
            read = writing_tools.execute(root, 'book', 'discuss', 'repository', {
                'action': 'read', 'repository': key, 'path': 'source.md', 'limit': 7, 'offset': offset})
            assert read['source']['path'] == str(path / 'source.md')
            assert len(read['source']['sha256']) == 64
            parts.append(read['content'])
            offset = read['next_offset']
            if offset is None:
                break
        assert ''.join(parts) == (path / 'source.md').read_text()


def test_repository_discovery_has_explicit_pagination_and_literal_search(roots):
    root, paths = roots
    for i in range(3):
        (paths['eigenengine'] / f'proof-{i}.md').write_text('A literal [claim].\n')
    query = {'action': 'files', 'repository': 'eigenengine', 'query': 'proof-', 'limit': 2}
    page = writing_sources.execute(root, query)
    assert len(page['matches']) == 2 and page['next_offset'] == 2
    last = writing_sources.execute(root, {**query, 'offset': 2})
    assert len(last['matches']) == 1 and last['next_offset'] is None
    matches = writing_sources.execute(root, {'action': 'search', 'repository': 'eigenengine',
        'query': '[claim]', 'glob': '*.md'})
    assert len(matches['matches']) == 3
    assert all(m['line'] == 1 and '[claim]' in m['text'] for m in matches['matches'])


@pytest.mark.parametrize('raw,expected', [
    (b'first\nsecond\n', 2),
    (b'first\nsecond', 2),
    (b'', 0),
    (b'first\r\nsecond\r\n', 2),
    (b'\n', 1),
    ('first\u2028second\n'.encode(), 2),
])
def test_text_total_lines_matches_source_resolver_before_character_pagination(roots, raw, expected):
    from laplace.research.mathematical_records import resolve_source
    root, paths = roots
    path = paths['atlas'] / 'lines.txt'
    path.write_bytes(raw)
    payload = {'action':'read', 'repository':'atlas', 'path':'lines.txt', 'limit':2}
    first = writing_sources.execute(root, payload)
    later = writing_sources.execute(root, {**payload, 'offset':4})
    assert first['total_lines'] == later['total_lines'] == expected
    assert expected == len(raw.decode().splitlines(keepends=True))
    locator = {'repository':'atlas', 'path':'lines.txt', 'line_start':1,
               'line_end':first['total_lines'], 'sha256':first['source']['sha256']}
    if expected:
        assert resolve_source('book', locator, root)['status'] == 'READ'
    assert resolve_source('book', {**locator, 'line_end':expected + 1}, root)['status'] == 'UNRESOLVED'


def test_repository_read_rejects_symlink_escape_and_does_not_authorise_writes(roots):
    root, paths = roots
    outside = root.parent / 'outside.md'
    outside.write_text('outside')
    (paths['atlas'] / 'escape.md').symlink_to(outside)
    for path in ['escape.md', '../../outside.md', str(outside)]:
        with pytest.raises(ValueError, match='escapes'):
            writing_sources.execute(root, {'action': 'read', 'repository': 'atlas', 'path': path})
    manuscript = root / 'book'
    manuscript.mkdir()
    (manuscript / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}X\\end{document}\n')
    code, _ = writing_projects.import_source({'name': 'book', 'title': 'Book', 'root': 'book/main.tex', 'editable': True}, root)
    assert code == 201
    with pytest.raises(ValueError, match='Research artifacts belong'):
        writing_tools.execute(root, 'book', 'work', 'store_artifact', {
            'path': str(paths['eigenengine'] / 'source.md'), 'before': None, 'content': 'overwrite','reason':'Attempted forbidden source overwrite'})
    assert 'Reflexive representation' in (paths['eigenengine'] / 'source.md').read_text()


def _pdf(path):
    stream = b'BT /F1 14 Tf 30 100 Td (Original source figure) Tj ET\n'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 160] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'endstream']
    result = b'%PDF-1.4\n'
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result += str(i).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(result)
    result += b'xref\n0 6\n0000000000 65535 f \n'
    result += b''.join(f'{o:010} 00000 n \n'.encode() for o in offsets[1:])
    result += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    path.write_bytes(result)


@pytest.mark.skipif(not all(shutil.which(x) for x in ['pdfinfo', 'pdftotext', 'pdftoppm']), reason='Poppler required')
def test_pdf_text_and_visual_are_original_source_reads_with_native_image_blocks(roots):
    root, paths = roots
    pdf = paths['physics-paper-orchestra'] / 'paper.pdf'
    _pdf(pdf)
    payload = {'repository': 'physics-paper-orchestra', 'path': 'paper.pdf', 'page': 1}
    text = writing_sources.execute(root, {**payload, 'action': 'read', 'page_count': 4})
    assert 'Original source figure' in text['content']
    assert text['pdf_total_pages'] == text['pdf_page_start'] == text['pdf_page_end'] == 1
    assert 'total_lines' not in text
    view = writing_sources.execute(root, {**payload, 'action': 'view'})
    assert view['source'] == text['source']
    assert base64.b64decode(view['_image_content'][0]['data']).startswith(b'\x89PNG')
    codex = writing_sources.content_items(view, 'codex')
    mcp = writing_sources.content_items(view, 'claude')
    assert codex[1]['type'] == 'inputImage' and codex[1]['imageUrl'].startswith('data:image/png;base64,')
    assert mcp[1]['type'] == 'image' and mcp[1]['mimeType'] == 'image/png'
    assert 'base64' not in codex[0]['text']
    with pytest.raises(ValueError, match='page must'):
        writing_sources.execute(root, {**payload, 'action': 'read', 'page': 2})


def test_binary_source_is_reported_honestly_and_raster_view_is_read_only(roots):
    from PIL import Image
    root, paths = roots
    image = paths['atlas'] / 'diagram.png'
    Image.new('RGB', (16, 16), 'red').save(image)
    payload = {'repository': 'atlas', 'path': 'diagram.png'}
    binary = writing_sources.execute(root, {**payload, 'action': 'read'})
    assert binary['content'] is None and 'Binary file' in binary['note']
    view = writing_sources.execute(root, {**payload, 'action': 'view'})
    assert view['source'] == binary['source']
    assert view['_image_content'][0]['mime_type'] == 'image/png'


def _two_page_pdf(path):
    streams=[b'1 0 0 rg 25 25 100 100 re f 0 0 0 rg BT /F1 16 Tf 20 160 Td (FIRST PAGE TOKEN) Tj ET',
             b'0 0 1 rg 25 25 100 100 re f 0 0 0 rg BT /F1 16 Tf 20 160 Td (SECOND PAGE TOKEN) Tj ET']
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 220 200] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>',
        b'<< /Length '+str(len(streams[0])).encode()+b' >>\nstream\n'+streams[0]+b'\nendstream',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 220 200] /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>',
        b'<< /Length '+str(len(streams[1])).encode()+b' >>\nstream\n'+streams[1]+b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    content=b'%PDF-1.4\n';offsets=[0]
    for index,body in enumerate(objects,1):
        offsets.append(len(content));content+=str(index).encode()+b' 0 obj\n'+body+b'\nendobj\n'
    xref=len(content);content+=b'xref\n0 8\n0000000000 65535 f \n'
    content+=b''.join(f'{offset:010} 00000 n \n'.encode() for offset in offsets[1:])
    content+=f'trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    path.write_bytes(content)


@pytest.mark.skipif(not all(shutil.which(x) for x in ['pdfinfo','pdftotext','pdftoppm']),reason='Poppler required')
def test_pdf_page_selection_renders_distinct_pages_and_reads_the_requested_range(roots):
    root,paths=roots;pdf=paths['atlas']/'two-pages.pdf';_two_page_pdf(pdf)
    payload={'repository':'atlas','path':'two-pages.pdf'}
    first=writing_tools.execute(root,'book','work','repository',{**payload,'action':'view','page':1})
    second=writing_tools.execute(root,'book','work','repository',{**payload,'action':'view','page':2})
    assert (first['pdf_page'],second['pdf_page'],second['pdf_total_pages'])==(1,2,2)
    assert first['source']==second['source']
    assert first['_image_content'][0]['data']!=second['_image_content'][0]['data']
    import io
    from PIL import Image
    rendered=[Image.open(io.BytesIO(base64.b64decode(result['_image_content'][0]['data']))) for result in (first,second)]
    assert rendered[0].getpixel((rendered[0].width//3,rendered[0].height//2))[:3]==(255,0,0)
    assert rendered[1].getpixel((rendered[1].width//3,rendered[1].height//2))[:3]==(0,0,255)
    text=writing_sources.execute(root,{**payload,'action':'read','page':2,'page_count':1})
    assert 'SECOND PAGE TOKEN' in text['content'] and 'FIRST PAGE TOKEN' not in text['content']
    both=writing_sources.execute(root,{**payload,'action':'read','page':1,'page_count':2})
    assert 'FIRST PAGE TOKEN' in both['content'] and 'SECOND PAGE TOKEN' in both['content']
    with pytest.raises(ValueError,match='page must'):
        writing_sources.execute(root,{**payload,'action':'view','page':0})
    with pytest.raises(ValueError,match='page must'):
        writing_sources.execute(root,{**payload,'action':'view','page':3})


@pytest.mark.parametrize('extra',[{'offset':0},{'offset':3},{'limit':4},{'page_count':2}])
def test_pdf_view_rejects_ignored_pagination_before_rendering(roots,monkeypatch,extra):
    root,paths=roots;pdf=paths['atlas']/'two-pages.pdf';_two_page_pdf(pdf)
    monkeypatch.setattr(writing_sources,'_run',lambda *args:(_ for _ in ()).throw(AssertionError('invalid view must not render')))
    with pytest.raises(writing_declarations.PayloadAdmissionError,match='Payload rejected'):
        writing_tools.execute(root,'book','work','repository',{'action':'view','repository':'atlas','path':'two-pages.pdf',**extra})


def test_repository_action_validation_preserves_project_routing_and_rejects_wrong_units(roots):
    root,paths=roots
    assert writing_sources.execute(root,{'action':'list','project':'book'})['repositories']
    for payload in ({'action':'list','offset':0}, {'action':'files','repository':'atlas','page':2},
                    {'action':'read','repository':'atlas','path':'source.md','glob':'*.md'},
                    {'action':'read','repository':'atlas','path':'source.md','page':2},
                    {'action':'search','repository':'atlas','query':True}):
        with pytest.raises(ValueError):writing_sources.execute(root,payload)


def test_repository_help_and_error_contract_publish_action_specific_units(roots):
    import jsonschema
    from laplace.native import contracts as writing_contracts
    from laplace.native import declarations as writing_declarations
    root,_=roots;contract=writing_contracts.exact_contract('repository',permitted=True)
    # `source_locator_recipe` is carried as its clauses, because the whole string was 349
    # characters and a published line is capped at 159 (harness/holder_census.py:44). The
    # facts are the same facts; they are just addressable one at a time.
    recipe=' '.join(contract['source_locator_recipe'])
    assert 'line_end:result.total_lines' in recipe
    assert 'result.source.sha256 programmatically' in recipe
    assert 'total_lines is omitted' in contract['action_units']['read']
    # Six variants, so help serves the index; each one's GENERATED example is validated
    # against its own variant schema and against the owner's own payload validator.
    variants=writing_declarations.variants('repository')
    for name,schema in variants.items():
        example=writing_declarations.generated_example('repository',variant=name)
        jsonschema.Draft202012Validator(schema).validate(example)
        writing_sources._validate_payload({**example,'project':'book'})
    assert 'page' in variants['view']['properties'] and 'offset' not in variants['view']['properties']
    assert 'page_count' in variants['read']['properties']
    error=writing_tools.failure_response(root,'book','work','repository',{'action':'view','offset':3},ValueError('view requires page'))
    assert error['contract']['input']['properties']['action']['const']=='view'
    assert error['contract']['selected_variant']=='view'
    assert 'one-based' in error['contract']['action_units']['view']


def test_interface_projection_is_bounded_hash_bearing_and_exactly_continuable():
    from laplace.native import declarations as writing_declarations
    root=Path(__file__).resolve().parents[1]
    first=writing_sources.execute(root,{'action':'interface','repository':'laplace','limit':1},interface=writing_declarations.interface_projection)
    assert first['schema_version']=='laplace.http-interface-projection/1'
    assert len(first['items'])==1 and first['next_offset']==1
    assert first['continuation']['payload']=={
        'action':'interface','repository':'laplace','offset':1,'limit':1}
    assert first['revision'].startswith('sha256:')
    assert 'source_set_revision' not in first
    assert 'schema_sha256' not in json.dumps(first)
    item=first['items'][0]
    contract=writing_declarations.http_help(
        item['route'],item['methods'][0],item['operation'])
    assert item['request']['version']==contract['version']
    assert first['sources'] and all(len(row['sha256'])==64 for row in first['sources'])
    first_sites={first['items'][0]['owner'],*first['items'][0]['consumers'].values(),
                 *first['items'][0]['response_sources'].values()}
    assert {source['site'] for source in first['sources']}==first_sites
    for source in first['sources']:
        assert source['read']['payload']['offset']>=0
        reached=writing_sources.execute(root,source['read']['payload'])
        assert reached['source']['sha256']==source['sha256']
        assert reached['content']
    second=writing_sources.execute(root,first['continuation']['payload'],interface=writing_declarations.interface_projection)
    assert second['offset']==1 and second['revision']==first['revision']
    assert {row['operation'] for row in first['items']}.isdisjoint(
        {row['operation'] for row in second['items']})
    second_sites={second['items'][0]['owner'],*second['items'][0]['consumers'].values(),
                  *second['items'][0]['response_sources'].values()}
    assert {source['site'] for source in second['sources']}==second_sites
    assert {source['site'] for source in first['sources']}.isdisjoint(
        {source['site'] for source in second['sources']})


def test_interface_revision_uses_canonical_contract_version_and_full_source_set(monkeypatch):
    from dataclasses import replace
    from laplace.native import declarations as writing_declarations
    root=Path(__file__).resolve().parents[1]
    first=writing_declarations.interface_projection(root,'laplace',limit=1)
    operation=first['items'][0]['operation']
    declaration=writing_declarations.HTTP_DECLARATIONS[operation]
    nested={**declaration.payload,'properties':{
        **(declaration.payload.get('properties') or {}),
        'fixture_nested_change':{'type':'string'}}}
    monkeypatch.setitem(writing_declarations.HTTP_DECLARATIONS,operation,
                        replace(declaration,payload=nested))
    contract_changed=writing_declarations.interface_projection(root,'laplace',limit=1)
    item=contract_changed['items'][0]
    assert item['operation']==operation
    assert item['request']['version']==writing_declarations.http_help(
        item['route'],item['methods'][0],operation)['version']
    assert item['request']['version']!=first['items'][0]['request']['version']
    assert contract_changed['revision']!=first['revision']

    monkeypatch.setitem(writing_declarations.HTTP_DECLARATIONS,operation,declaration)
    real_projection=writing_declarations._site_projection
    changed_site=first['sources'][0]['site']
    def changed_source(*args,**kwargs):
        source=real_projection(*args,**kwargs)
        return {**source,'sha256':'0'*64} if source['site']==changed_site else source
    monkeypatch.setattr(writing_declarations,'_site_projection',changed_source)
    source_changed=writing_declarations.interface_projection(root,'laplace',limit=1)
    assert source_changed['revision']!=first['revision']


def test_interface_projection_refuses_source_bytes_from_another_tree(tmp_path):
    from laplace.native import declarations as writing_declarations
    path=tmp_path/'src/laplace';path.mkdir(parents=True)
    (path/'writing_declared_http.py').write_text('different source\n')
    with pytest.raises(ValueError,match='identity differs'):
        writing_declarations._site_projection(
            tmp_path,'laplace','src/laplace/writing_declared_http.py:1')


def test_interface_checks_each_file_once_per_request_and_rechecks_next_request(monkeypatch):
    from collections import Counter
    from laplace.native import declarations as writing_declarations
    root=Path(__file__).resolve().parents[1]
    reads=Counter()
    read_bytes=Path.read_bytes
    def observed(path):
        reads[path]+=1
        return read_bytes(path)
    monkeypatch.setattr(Path,'read_bytes',observed)
    first=writing_declarations.interface_projection(root,'laplace',limit=1)
    # Selected and serving bytes are each checked once per file, even when many
    # source ranges refer to it. Paging still verifies the entire cited source set.
    assert reads and set(reads.values())=={2}
    first_reads=reads.copy()
    second=writing_declarations.interface_projection(root,'laplace',limit=1)
    assert second==first and reads==Counter({path:n*2 for path,n in first_reads.items()})
    # A later request must compare fresh bytes, not an earlier digest. Simulate a
    # selected-file mismatch without changing source files in the test checkout.
    changed=next(iter(first_reads))
    mismatch=False
    def changed_once(path):
        nonlocal mismatch
        value=read_bytes(path)
        if path==changed and not mismatch:
            mismatch=True
            return value+b'\nchanged\n'
        return value
    monkeypatch.setattr(Path,'read_bytes',changed_once)
    with pytest.raises(ValueError,match='identity differs'):
        writing_declarations.interface_projection(root,'laplace',limit=1)
