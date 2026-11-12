"""Isolated literature workflow: no live project or personal library writes."""
import json
from pathlib import Path
import pytest

from laplace.research import references_surface as rs, literature
from laplace.native import tools as writing_tools
from laplace.writing import operating as writing_operating
from laplace.writing import reads


def project(root):
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [{
        'name': 'fixture', 'kind': 'conceptric', 'project_dir': 'fixture', 'tex_root': 'fixture/manuscript'}]}))
    manuscript = root / 'fixture/manuscript'
    manuscript.mkdir(parents=True)
    (manuscript / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n\\bibliography{sources}\n\\end{document}\n')
    (manuscript / 'sources.bib').write_text('@book{unrelated, title={Keep exact human bytes}}\n')
    from laplace.research import corpus_ingest as ci
    net=ci.corpus_network(ci.resolve_corpus(root,'fixture'),repo_root=root,name='fixture')
    created=ci.rewire_add(root,'fixture',{'kind':'add-node','node':'claim:one','node_kind':'result',
        'essence':'The fixture claim','parent':net.get('root'),'by':'test-fixture'})
    assert created.get('ok'),created
    return manuscript


@pytest.fixture
def crossref(monkeypatch):
    metadata = {'DOI': '10.1234/test', 'title': ['Verified title'], 'author': [{'given': 'Ada', 'family': 'Author'}],
                'issued': {'date-parts': [[2024]]}, 'type': 'journal-article', 'container-title': ['Journal']}
    calls = []
    def fetch(**kwargs):
        calls.append(kwargs)
        return [metadata]
    monkeypatch.setattr(rs, '_crossref', fetch)
    return metadata, calls


def call(root, operation, payload):
    if operation=='literature_bind' and 'claim_revision' not in payload:
        from laplace.research import literature_support
        payload={**payload,'claim_revision':literature_support.meaning_revision('fixture',payload['claim_id'],root)}
    return writing_tools.execute(root, 'fixture', 'work', operation, payload)


def test_verified_import_exact_bibliography_dedup_and_saved_snapshot(tmp_path, crossref):
    manuscript = project(tmp_path)
    row, calls = crossref
    first = call(tmp_path, 'literature_import', {'doi': 'https://doi.org/10.1234/TEST', 'citekey': 'Author2024'})
    assert first['association']['key'] == 'doi:10.1234/test'
    assert calls == [{'doi': '10.1234/test'}]
    bib = (manuscript / 'sources.bib').read_text()
    assert 'laplace_key = {doi:10.1234/test}' in bib and 'zotero_key' not in bib
    assert bib.startswith('@book{unrelated, title={Keep exact human bytes}}\n')
    repeated = call(tmp_path, 'literature_import', {'doi': '10.1234/test', 'citekey': 'NewKey'})
    assert repeated['reused'] and repeated['association']['citekey'] == 'Author2024'
    assert (manuscript / 'sources.bib').read_text() == bib
    row['title'] = ['Changed provider metadata']
    saved = call(tmp_path, 'references_attached', {})
    assert saved['associations'][0]['metadata']['title'] == 'Verified title'
    assert call(tmp_path, 'reference_text', {'key': 'doi:10.1234/test'})['source_state'] == 'metadata-only'
    assert call(tmp_path, 'reference_refresh', {})['stale'] == ['doi:10.1234/test']
    assert call(tmp_path, 'reference_update', {'key': 'doi:10.1234/test'})['state'] == 'CURRENT'
    assert 'Changed provider metadata' in (manuscript / 'sources.bib').read_text()
    assert (manuscript / 'sources.bib').read_text().count('@article{Author2024') == 1


def test_wrong_doi_cannot_import_and_doi_in_local_metadata_rejected(tmp_path, crossref):
    manuscript = project(tmp_path)
    before = (manuscript / 'sources.bib').read_bytes()
    with pytest.raises(ValueError, match='requested DOI'):
        call(tmp_path, 'literature_import', {'doi': '10.1234/different'})
    # D3 (2026-10-15): a DOI inside LOCAL metadata is refused by its shape (the local metadata schema has no doi:
    # a DOI is only ever the verified provider record), before any provider work, separately from the wrong-DOI case
    _metadata, provider_calls = crossref
    asked = len(provider_calls)
    from laplace.native.declarations import PayloadAdmissionError
    with pytest.raises(PayloadAdmissionError, match=r"metadata: Additional properties are not allowed \('doi' was unexpected\)"):
        call(tmp_path, 'literature_import', {'metadata': {'title': 'Unverified', 'doi': '10.1234/test'}, 'provenance': {'description': 'manual'}})
    assert len(provider_calls) == asked, 'no provider work for a malformed local record'
    assert (manuscript / 'sources.bib').read_bytes() == before
    assert not (manuscript / 'references.json').exists()


def test_fulltext_http_error_preserves_import_and_does_not_blame_crossref(tmp_path,crossref,monkeypatch):
    import urllib.error
    manuscript=project(tmp_path)
    imported=call(tmp_path,'literature_import',{'doi':'10.1234/test'})
    key=imported['association']['key']
    before=(manuscript/'sources.bib').read_bytes()
    def no_lookup(**kwargs):raise AssertionError('Fetching an imported source must not reverify metadata')
    monkeypatch.setattr(rs,'_crossref',no_lookup)
    def denied(url):raise urllib.error.HTTPError(url,406,'Not Acceptable',{},None)
    monkeypatch.setattr(literature,'_download',denied)
    status,_,body=literature.handle('/references/fetch',{'project':['fixture']},'POST',
        json.dumps({'key':key,'url':'https://example.org/source.pdf'}).encode(),root=tmp_path)
    error=json.loads(body)
    assert status==502 and error['provider_status']==406
    assert error['error']=='Full-text retrieval failed (HTTP 406)'
    assert 'do not reimport' in error['recovery']
    assert (manuscript/'sources.bib').read_bytes()==before
    assert literature.resolve_item('fixture',key,tmp_path)[1]['key']==key


def test_local_book_import_read_bind_both_joins_and_exact_selected_uses(tmp_path, monkeypatch):
    manuscript = project(tmp_path)
    supplied = tmp_path / 'author-book.txt'
    supplied.write_text('A local unpublished book.\nThe measured result is conditional.\n')
    result = call(tmp_path, 'literature_import', {'metadata': {'title': 'Author book', 'creators': ['A. Author'], 'year': '2026', 'item_type': 'book'},
        'provenance': {'description': 'Author supplied unpublished book', 'path': 'author-book.txt'}, 'citekey': 'AuthorBook'})
    key = result['association']['key']
    assert key.startswith('local:')
    assert 'zotero_key' not in (manuscript / 'sources.bib').read_text()
    assert 'author-book.txt' in result['association']['metadata']['provenance']['path']
    passage = call(tmp_path, 'reference_text', {'key': key, 'limit': 1000})
    assert passage['text'].startswith('A local unpublished book') and passage['source_currentness'] == 'CURRENT'
    from laplace.research import concepts as concepts_surface
    monkeypatch.setattr(concepts_surface, 'logical_plan', lambda project, focus, **kw: {'selected': {'id': focus}} if focus == 'claim:one' else {'selected': None})
    payload = {'key': key, 'claim_id': 'claim:one', 'relation': 'supports', 'rationale': 'Conditional result, limited to stated setup', 'reading_status': 'partial', 'evidence': {'locator': 'line 2', 'excerpt': 'The measured result is conditional.'}}
    bound = call(tmp_path, 'literature_bind', payload)
    assert bound['association']['evidence_status'] == 'authored-passage'
    assert call(tmp_path, 'literature_bind', {**payload, 'relation': 'background'})['association']['relation'] == 'background'
    (manuscript / 'chapter.tex').write_text('Exact \\textcite[see][2]{AuthorBook,\nunknown}.\n% \\cite{AuthorBook}\n')
    (manuscript / 'main.tex').write_text('\\input{chapter}\n\\bibliography{sources}\n')
    (manuscript / 'not-selected.tex').write_text('\\cite{AuthorBook}\n')
    uses = call(tmp_path, 'literature_uses', {'key': key})
    assert uses['claim_sources']['claim:one'][0]['key'] == key
    assert uses['source_claims'][key][0]['claim_id'] == 'claim:one'
    claim = next(row for row in uses['uses'] if row.get('claim_id'))
    assert len(claim['manuscript_uses']) == 1
    span = claim['manuscript_uses'][0]
    assert span['line_start'] == 1 and span['line_end'] == 2 and span['file'].endswith('chapter.tex')
    assert span['text'] == '\\textcite[see][2]{AuthorBook,\nunknown}'
    # D3: a KEY-SCOPED read omits the unrelated unknown cite; the unfiltered read shows that occurrence
    assert not any(row.get('citekey') == 'unknown' for row in uses.get('unassociated_uses') or [])
    everything = call(tmp_path, 'literature_uses', {})
    unknown = [row for row in everything['unassociated_uses'] if row['citekey'] == 'unknown']
    assert len(unknown) == 1 and unknown[0]['file'].endswith('chapter.tex'), everything['unassociated_uses']
    assert claim['evidence_currentness'] == 'CURRENT'
    supplied.write_text('Changed source meaning.\n')
    assert call(tmp_path, 'reference_text', {'key': key})['source_currentness'] == 'STALE'
    assert call(tmp_path, 'reference_refresh', {})['stale'] == [key, key]
    call(tmp_path, 'reference_update', {'key': key, 'metadata': {'title': 'Revised author book'}})
    assert 'Revised author book' in (manuscript / 'sources.bib').read_text()
    uses = call(tmp_path, 'literature_uses', {'claim_id': 'claim:one'})
    assert uses['uses'][0]['evidence_currentness'] == 'STALE'
    assert call(tmp_path, 'reference_refresh', {})['stale'] == []
    with pytest.raises(ValueError, match='existing logical'):
        call(tmp_path, 'literature_bind', {**payload, 'claim_id': 'missing'})


def test_import_rolls_back_bibliography_on_association_commit_failure(tmp_path, monkeypatch, crossref):
    manuscript = project(tmp_path)
    before = (manuscript / 'sources.bib').read_bytes()
    original = Path.replace
    def fail(path, target):
        if path.name == 'references.tmp': raise OSError('simulated association rename failure')
        return original(path, target)
    monkeypatch.setattr(Path, 'replace', fail)
    status, _, body = rs.handle('/references/literature-import', {}, 'POST', json.dumps({'project': 'fixture', 'doi': '10.1234/test'}).encode(), repo_root=tmp_path)
    assert status == 409 and 'simulated' in json.loads(body)['error']
    assert (manuscript / 'sources.bib').read_bytes() == before
    assert not (manuscript / 'references.json').exists()


def test_existing_doi_identity_reuses_human_bibtex_key(tmp_path, crossref):
    manuscript = project(tmp_path)
    (manuscript / 'sources.bib').write_text('@article{HumanKey, title={Human metadata}, doi="https://doi.org/10.1234/TEST"}\n')
    result = call(tmp_path, 'literature_import', {'doi': '10.1234/test', 'citekey': 'NewKey'})
    assert result['association']['citekey'] == 'HumanKey'
    assert len(rs._bib_entries((manuscript / 'sources.bib').read_text())) == 1


def test_contract_index_and_resumed_digest_migration():
    from laplace.native.contracts import exact_contract
    for operation in ('literature_import', 'literature_lookup', 'literature_bind', 'literature_uses'):
        assert operation in reads.READS | reads.WRITES
        assert exact_contract(operation, permitted=True)['input']
    new = {'tool_contract_digest': 'new', 'exact_action_digests': {'literature_import':'new-action'},
           'action_catalogue_digest':'catalogue','role_permissions_digest':'permissions'}
    delta = writing_operating.orientation_delta({'tool_contract_digest': 'old',
        'exact_action_digests':{'literature_import':'old-action'},
        'action_catalogue_digest':'catalogue','role_permissions_digest':'permissions'}, new)
    assert delta['changed'] and delta['guidance']['contract_delta']['changed_actions'] == ['literature_import']
    assert 'operation_contract' not in delta['guidance'] and 'rules' not in delta['guidance']
    assert not writing_operating.orientation_delta(new, new)['changed']


def test_included_bibliography_consumer_and_bounded_citation_descent(tmp_path, crossref):
    manuscript = project(tmp_path)
    (manuscript / 'backmatter.tex').write_text('\\bibliography{sources}\n')
    (manuscript / 'main.tex').write_text('% \\bibliography{wrong}\n\\input{backmatter}\n' + '\\cite{Ref}\n' * 3)
    result = call(tmp_path, 'literature_import', {'doi': '10.1234/test', 'citekey': 'Ref'})
    assert result['association']['bib_path'].endswith('sources.bib')
    first = call(tmp_path, 'literature_uses', {'citation_limit': 1})
    assert len(first['uses'][0]['manuscript_uses']) == 1
    assert first['pagination']['next_citation_offset'] == 1
    second = call(tmp_path, 'literature_uses', {'citation_limit': 1, 'citation_offset': 1})
    assert second['uses'][0]['manuscript_uses'][0]['line_start'] == 4


def test_refresh_unavailable_source_is_unverified_not_current(tmp_path, crossref, monkeypatch):
    project(tmp_path)
    call(tmp_path, 'literature_import', {'doi': '10.1234/test'})
    def offline(**kwargs): raise OSError('public metadata offline')
    monkeypatch.setattr(rs, '_crossref', offline)
    result = call(tmp_path, 'reference_refresh', {})
    assert result['unverified'] == ['doi:10.1234/test']
    assert call(tmp_path, 'literature_uses', {})['uses'][0]['evidence_currentness'] == 'UNVERIFIED'


def test_reference_source_serves_only_resolved_local_pdf_and_reports_metadata_only(tmp_path, crossref):
    project(tmp_path)
    pdf=tmp_path/'author-paper.pdf';pdf.write_bytes(b'%PDF-1.4\n% isolated route fixture\n%%EOF')
    imported=call(tmp_path,'literature_import',{'metadata':{'title':'Author PDF'},'provenance':{'description':'Supplied locally','path':str(pdf)}})
    key=imported['association']['key']
    info=call(tmp_path,'reference_source',{'key':key})
    assert info['available'] and info['kind']=='pdf' and info['pdf_url'].startswith('/references/source?')
    status,mime,body=rs.handle('/references/source',{'project':['fixture'],'key':[key],'format':['pdf']},'GET',b'',repo_root=tmp_path)
    assert status==200 and mime=='application/pdf' and body==pdf.read_bytes()
    assert rs.handle('/references/source',{'project':['fixture'],'key':['../../author-paper.pdf'],'format':['pdf']},'GET',b'',repo_root=tmp_path)[0]==422
    call(tmp_path,'literature_import',{'doi':'10.1234/test'})
    info=call(tmp_path,'reference_source',{'key':'doi:10.1234/test'})
    assert not info['available'] and info['source_state']=='metadata-only' and info['pdf_url'] is None
    assert rs.handle('/references/source',{'project':['fixture'],'key':['doi:10.1234/test'],'format':['pdf']},'GET',b'',repo_root=tmp_path)[0]==404


def test_canonical_argument_sources_join_without_bibliography_or_read_time_writes(tmp_path, monkeypatch):
    manuscript=project(tmp_path)
    (manuscript/'original.tex').write_text('An original source with a stated limitation.\n')
    (manuscript/'reading.md').write_text('# Authored reading note\nThe argument is conditional.\n')
    from laplace.research import concepts as cs
    nodes={'cite:prior':{'kind':'citation','essence':'Previously read source, author context and limits.',
        'source':['original.tex','reading.md']},'claim:one':{'kind':'claim','essence':'Conditional claim'}}
    monkeypatch.setattr(cs,'_network',lambda *a,**kw:{'nodes':nodes})
    monkeypatch.setattr(cs,'_relations',lambda *a,**kw:([{'source':'claim:one','target':'cite:prior','rel':'support','rationale':'The source gives this premise.'}],[]))
    monkeypatch.setattr(cs,'logical_plan',lambda *a,**kw:{'selected':{'id':'claim:one'}})
    joined=call(tmp_path,'literature_uses',{})
    assert len(joined['uses'])==1
    source=joined['uses'][0]
    assert source['canonical_id']=='cite:prior' and source['bibliography_state']=='NOT_LINKED'
    assert source['claim_id']=='claim:one' and source['rationale']=='The source gives this premise.'
    assert source['metadata']['creators']==[] and not source.get('citekey')
    assert source['evidence_currentness']=='UNASSESSED'
    assert not (manuscript/'references.json').exists()
    info=call(tmp_path,'reference_source',{'key':'cite:prior','source_index':1})
    assert info['available'] and info['kind']=='text' and len(info['sources'])==2
    content=call(tmp_path,'reference_text',{'key':'cite:prior','source_index':1})
    assert 'Authored reading note' in content['text']
    # Explicitly add authored passage interpretation without inventing bibliography.
    bound=call(tmp_path,'literature_bind',{'key':'cite:prior','claim_id':'claim:one','relation':'supports',
        'rationale':'Read the limited premise','reading_status':'partial','evidence':{'locator':'reading note, paragraph 1'}})
    assert bound['association']['canonical_id']=='cite:prior' and not bound['association'].get('citekey')
    assert len([row for row in call(tmp_path,'literature_uses',{})['uses'] if row.get('claim_id')=='claim:one'])==1


def test_reference_source_serves_zotero_attachment_identity_not_user_path(tmp_path, monkeypatch):
    project(tmp_path)
    storage=tmp_path/'storage/PDF12345';storage.mkdir(parents=True)
    pdf=storage/'paper.pdf';pdf.write_bytes(b'%PDF-1.4\n%%EOF')
    class SQLite:
        path=tmp_path/'zotero.sqlite'
    class Library:
        sqlite=SQLite()
        def item(self,key):
            return 'sqlite', {'key':key,'title':'Zotero source','attachments':[{'key':'PDF12345','content_type':'application/pdf','path':'storage:paper.pdf'}]} if key=='ABCDEFGH' else None
    monkeypatch.setattr(rs,'Library',Library)
    status,mime,body=rs.handle('/references/source',{'project':['fixture'],'key':['ABCDEFGH'],'format':['pdf']},'GET',b'',repo_root=tmp_path)
    assert status==200 and mime=='application/pdf' and body==pdf.read_bytes()


def test_relied_source_relation_requires_reading_and_located_passage(tmp_path,crossref,monkeypatch):
    project(tmp_path);call(tmp_path,'literature_import',{'doi':'10.1234/test'})
    from laplace.research import concepts as cs
    monkeypatch.setattr(cs,'logical_plan',lambda *a,**kw:{'selected':{'id':'claim:one'}})
    with pytest.raises(ValueError,match='inspected passage'):
        call(tmp_path,'literature_bind',{'key':'doi:10.1234/test','claim_id':'claim:one','relation':'supports','rationale':'Only the title was seen'})
    background=call(tmp_path,'literature_bind',{'key':'doi:10.1234/test','claim_id':'claim:one','relation':'background','rationale':'Potential relevance; full text still unavailable'})
    assert background['association']['evidence_status']=='metadata-only'
