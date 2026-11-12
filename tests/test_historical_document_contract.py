"""Exact historical reads and pinned current PDF are separate from source writes."""
import hashlib,json
from pathlib import Path
import pytest
from laplace.work import history as author_history
from laplace.web import authoring as authoring_surface, shared_ui
from laplace.manuscript import document_style, projection_viewer as pv
from laplace.native import tools as writing_tools
from laplace.manuscript import manuscript_versions
from laplace.manuscript import document
from laplace.core import checkout
from test_editor_document_contract import fixture,query


def setup(root,monkeypatch):
    md=fixture(root)
    monkeypatch.setattr(pv,'_repo_root',lambda:root)
    monkeypatch.setattr(checkout, 'repo_root',lambda:root)
    snap=md/'versions'/'snapshot-1';snap.mkdir(parents=True)
    (snap/'main.tex').write_text('Older snapshot αβγ.\n')
    (snap/'SNAPSHOT.json').write_text(json.dumps({'id':'snapshot-1','project':'paper','files':['main.tex']}))
    saved=pv.bank_editor_save(md,md/'body.tex','Exact saved αβγ.\n'.encode(),author='fixture',surface='test')
    return md,snap,saved


def test_version_rail_issues_exact_history_handles_and_http_native_reads_match(tmp_path,monkeypatch):
    md,snap,saved=setup(tmp_path,monkeypatch)
    versions=manuscript_versions.versions_payload('paper',tmp_path)
    assert {row['kind'] for row in versions['rows']}=={'editor-save','snapshot'}
    for row in versions['rows']:
        handle=row['source_read'];values=handle['query'];file=values['file']
        assert pv.handle('/projection/tex',query(corpus='paper',file=file,view='source'),'GET',b'')[0]==403
        code,_,raw=authoring_surface.handle(handle['route'],query(**values),'GET',b'')
        assert code==200
        human=json.loads(raw)
        native=writing_tools.execute(tmp_path,'paper','work','author_history',{k:v for k,v in values.items() if k!='project'})
        for key in ('schema_version','file','content','content_revision','archive_identity','complete','next_read'):
            assert native[key]==human[key]
        assert human['read_only'] and not {'expected_source_digest','selection_identity','save_handle'}&human.keys()
        assert human['archive_identity']['verification']==('VERIFIED' if row['kind']=='editor-save' else 'OBSERVED_ONLY')


def test_history_paging_is_pinned_and_drift_cannot_silently_change_comparison(tmp_path,monkeypatch):
    _,snap,_=setup(tmp_path,monkeypatch)
    values={'view':'source','kind':'snapshot','version_id':'snapshot-1','file':'paper/versions/snapshot-1/main.tex','limit':3}
    first=author_history.source('paper',values,tmp_path)
    assert first['content']=='Old' and not first['complete']
    second=author_history.source('paper',first['next_read']['query'],tmp_path)
    assert second['content']=='er ' and second['content_revision']==first['content_revision']
    (snap/'main.tex').write_text('Changed snapshot')
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        author_history.source('paper',first['next_read']['query'],tmp_path)


def test_historical_owner_rejects_crossed_project_path_and_corrupt_saved_occurrence(tmp_path,monkeypatch):
    md,_,saved=setup(tmp_path,monkeypatch)
    values={'view':'source','kind':'editor-save','version_id':saved['version_id'],'file':f"paper/editor_saves/{saved['version_id']}/body.tex"}
    good=author_history.source('paper',values,tmp_path);assert good['complete']
    for bad in ({**values,'file':'paper/body.tex'},{**values,'version_id':'../snapshot-1'}, {**values,'file':'../outside.tex'}):
        with pytest.raises(ValueError):author_history.source('paper',bad,tmp_path)
    with pytest.raises(ValueError):author_history.source('unknown',values,tmp_path)
    (md/'editor_saves'/saved['version_id']/'body.tex').write_text('Tampered historic bytes')
    with pytest.raises(ValueError,match='recorded identity'):
        author_history.source('paper',values,tmp_path)


def test_domain_document_and_style_compatibility_share_one_implementation(tmp_path,monkeypatch):
    fixture(tmp_path)
    marker={'delegated':True};calls=[]
    def current(*args,**kwargs):calls.append((args,kwargs));return marker
    monkeypatch.setattr(document,'current',current)
    assert document_style.current_status('paper',tmp_path,include_preview=False) is marker
    assert len(calls)==1 and calls[0][1]['include_preview'] is False


def test_current_pdf_handle_is_byte_pinned_and_preserves_observed_only_limit(tmp_path,monkeypatch):
    md=fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path)
    pdf=md/'main.pdf';pdf.write_bytes(b'%PDF-1.4 fixture bytes')
    observed=document.current('paper',tmp_path,include_preview=False)
    handle=observed['read_handles']['pdf']
    assert observed['pdf_identity']['verification']=='OBSERVED_ONLY'
    assert handle['query']['expected_content_revision']=='sha256:'+hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert pv.handle(handle['route'],query(**handle['query']),'GET',b'')[0]==200
    pdf.write_bytes(b'%PDF-1.4 changed fixture bytes')
    code,_,raw=pv.handle(handle['route'],query(**handle['query']),'GET',b'')
    assert code==409 and json.loads(raw)['reason']=='output-revision-conflict'


def test_explicit_help_exposes_actual_raw_and_historical_owner_contracts():
    from laplace.native import declarations
    from laplace.manuscript import manuscript_source
    get=declarations.http_help('/projection/tex','GET')
    post=declarations.http_help('/projection/tex','POST')
    history=declarations.http_help('/authoring/history','GET')
    assert get['source_protocol']==manuscript_source.source_protocol()
    assert post['input']==manuscript_source.source_protocol()['save_request']
    assert history['historical_source_protocol']==author_history.source_protocol()
