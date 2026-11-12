"""Shared HTTP/native source observations; fixture build results, no provider run."""
import json

from laplace.web import authoring as authoring_surface
from laplace.manuscript import document_style, projection_viewer, walk, manuscript_source
from laplace.native import tools as writing_tools
from laplace.writing import records as writing_records
from laplace.core import checkout
from test_manuscript_source import _project


def test_existing_http_summary_native_document_and_full_reader_share_source_basis(tmp_path,monkeypatch):
    _project(tmp_path,{'document':{'root':'main.tex'}})
    md=tmp_path/'synthetics papers/book/manuscript'
    (md/'main.tex').write_text('\\documentclass{book}\n\\begin{document}\n\\input{chapter}\n\\end{document}')
    (md/'chapter.tex').write_text('\\chapter{One}\nIncluded prose.')
    # This is a fixture observation of the existing build owner, not a compile proof.
    monkeypatch.setattr(projection_viewer,'recompile_status',lambda *a,**k:{
        'state':'done','ok':True,'fresh':True,'running':False,'finished':'fixed',
        'pdf':'fixture.pdf','log_tail':'large compiler details '*1000,
        'input_revisions':manuscript_source.observation('book',tmp_path)['file_revisions']})
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    monkeypatch.setattr(writing_records,'fold_records',lambda *a,**k:(_ for _ in ()).throw(AssertionError('status must not read history')))   # the owner
    code,_,raw=authoring_surface.handle('/authoring/build',{'project':['book'],'view':['summary']},'GET',b'')
    assert code==200
    head=json.loads(raw)
    assert head['project']=='book' and head['document_status']=='READY'
    assert 'log_tail' not in head and len(raw)<4000
    native=writing_tools.execute(tmp_path,'book','review','document',{})
    assert native['status']=='READY' and native['style_preview']['status']=='NOT_BUILT'
    assert native['current_revision']==head['current_revision']
    from laplace.manuscript import review_surface
    monkeypatch.setattr(walk,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(review_surface,'manuscript_dir',lambda *a,**k:md)
    monkeypatch.setattr(review_surface,'_project_name',lambda *a,**k:'book')
    body=walk.doc(corpus='book')
    assert body['project']=='book' and body['current_revision']==head['current_revision']
    assert body['source_observation']==head['source_observation']
    (md/'chapter.tex').write_text('\\chapter{Two}\nChanged included prose.')
    changed=document_style.current_status('book',tmp_path,include_preview=False)
    assert changed['current_revision']!=body['current_revision']
    assert walk.doc(corpus='book')['current_revision']==changed['current_revision']
