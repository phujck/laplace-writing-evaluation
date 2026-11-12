"""Shared document/source admission, dependency witnesses and exact effects."""
import json
from pathlib import Path
import pytest
from laplace.manuscript import manuscript_source as ms, projection_viewer as pv, document_style, tex_dependencies
from laplace.core import checkout


def fixture(root, *, readonly=False):
    md=root/'paper';md.mkdir()
    (root/'assets').mkdir()
    (root/'assets/custom.cls').write_text('\\ProvidesClass{custom}\n\\LoadClass{article}\n')
    (root/'assets/refs.bst').write_text('% bibliography style fixture\n')
    (md/'refs.bib').write_text('@book{key,title={Fixture},author={A},year={2026}}\n')
    (md/'main.tex').write_text('\\documentclass{../assets/custom}\n\\begin{document}\n\\input{body}\n\\bibliographystyle{../assets/refs}\n\\bibliography{refs}\n\\end{document}\n')
    (md/'body.tex').write_text('Original science in this selected manuscript.\n')
    (md/'old.tex').write_text('Historical draft is not current manuscript source.\n')
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'paper','project_dir':'paper','tex_root':'paper','manifest':{'document':{'root':'main.tex','edition':'v1','read_only':readonly}}}]}))
    return md


def query(**values):return {key:[value] for key,value in values.items()}
def read(root,file='paper/body.tex'):
    code,_,body=pv.handle('/projection/tex',query(corpus='paper',file=file,view='source'),'GET',b'')
    return code,json.loads(body)
def save(observed,text,**override):
    fields={**observed['save_handle']['query'],'author':'fixture','surface':'test',**override}
    code,_,body=pv.handle('/projection/tex',query(**fields),'POST',text.encode())
    return code,json.loads(body)


def test_document_http_native_owner_is_bounded_and_returns_exact_source_handles(tmp_path,monkeypatch):
    from laplace.web import authoring as authoring_surface
    fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path);monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    original_read=Path.read_text
    def bounded_read(path,*args,**kwargs):
        assert path != tmp_path/'paper/old.tex', 'Document read hydrated unrelated source candidate'
        return original_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',bounded_read)
    doc=document_style.current_status('paper',tmp_path)
    code,_,body=authoring_surface.handle('/authoring/document',query(project='paper'),'GET',b'')
    served=json.loads(body)
    assert code==200 and served==doc
    assert doc['selected_source']['root']=='paper/main.tex'
    assert doc['template']['class_name']=='../assets/custom'
    assert doc['template']['class_file']=='assets/custom.cls'
    files={row['file']:row for row in doc['files']}
    assert files['paper/body.tex']['save_handle']['query']['expected_selection']==doc['selection_identity']
    assert files['assets/custom.cls']['read_only'] and files['assets/custom.cls']['save_handle'] is None
    assert files['assets/refs.bst']['role']=='bibliography-style'
    assert 'paper/old.tex' not in files
    assert 'content' not in json.dumps(doc) and 'corrections' not in doc


def test_selected_source_guard_save_noop_and_refusal_preserve_history(tmp_path,monkeypatch):
    md=fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path)
    code,observed=read(tmp_path);assert code==200
    before=(md/'body.tex').stat().st_mtime_ns
    code,no_op=save(observed,observed['content'])
    assert code==200 and no_op['changed'] is False and no_op['invalidated']==[]
    assert (md/'body.tex').stat().st_mtime_ns==before and not (md/'editor_saves').exists()
    code,saved=save(observed,'Revised science in this selected manuscript.\n')
    assert code==200 and saved['source_committed'] and saved['version_id']
    assert saved['selection_identity']==observed['selection_identity']
    count=len(json.loads((md/'editor_saves/index.json').read_text())['saves'])
    code,refused=save(observed,'Stale draft must survive locally.')
    assert code==409 and refused['reason']=='source-revision-conflict'
    assert len(json.loads((md/'editor_saves/index.json').read_text())['saves'])==count
    assert (md/'body.tex').read_text()=='Revised science in this selected manuscript.\n'


def test_selection_identity_changes_only_for_authority_not_unrelated_source_bytes(tmp_path,monkeypatch):
    md=fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path)
    _,observed=read(tmp_path)
    (md/'main.tex').write_text((md/'main.tex').read_text()+'% separate root edit\n')
    assert read(tmp_path)[1]['selection_identity']==observed['selection_identity']
    registry=tmp_path/'registry_projects.json';data=json.loads(registry.read_text());data['projects'][0]['manifest']['document']['edition']='v2';registry.write_text(json.dumps(data))
    code,refused=save(observed,'Do not apply old-edition draft.')
    assert code==409 and refused['reason']=='selection-revision-conflict'
    assert (md/'body.tex').read_text()==observed['content']


def test_readonly_dependency_wrong_project_and_unscoped_paths_cannot_be_written(tmp_path,monkeypatch):
    md=fixture(tmp_path,readonly=True);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path)
    code,observed=read(tmp_path);assert code==200 and observed['save_handle'] is None
    original=(md/'body.tex').read_bytes()
    fields={'file':'paper/body.tex','expected_source_digest':observed['expected_source_digest'],'corpus':'paper','author':'fixture','expected_selection':observed['selection_identity']}
    code,_,body=pv.handle('/projection/tex',query(**fields),'POST',b'forbidden')
    assert code==403 and json.loads(body)['reason']=='source-not-writable'
    fields.pop('corpus');code,_,body=pv.handle('/projection/tex',query(**fields),'POST',b'forbidden')
    assert code==409 and json.loads(body)['reason']=='source-project-required'
    assert (md/'body.tex').read_bytes()==original
    assert read(tmp_path,'paper/old.tex')[0]==403
    assert read(tmp_path,'assets/custom.cls')[1]['read_only']
    code,_,_=pv.handle('/projection/tex',query(corpus='other',file='paper/body.tex',view='source'),'GET',b'')
    assert code==404


def test_bibliography_style_is_a_consumed_dependency_before_and_after_recorder(tmp_path):
    md=fixture(tmp_path)
    for recorded in (False,True):
        if recorded:(md/'main.fls').write_text('INPUT '+str(md/'main.tex')+'\nINPUT '+str(md/'body.tex')+'\n')
        first=tex_dependencies.snapshot(md/'main.tex',tmp_path)
        assert 'assets/refs.bst' in first
        (tmp_path/'assets/refs.bst').write_text('% changed style '+str(recorded))
        second=tex_dependencies.snapshot(md/'main.tex',tmp_path)
        assert first['assets/refs.bst']!=second['assets/refs.bst']


def test_custom_class_preset_refuses_without_mutating_settings(tmp_path):
    md=fixture(tmp_path)
    with pytest.raises(ValueError,match='custom document class'):
        document_style.preview('paper',{'preset':'book'},tmp_path,wait=True)
    assert not (md/'document_style.json').exists()
    assert not (tmp_path/'.laplace-cache/writing-style/paper/latest.json').exists()


def test_native_source_and_document_share_selection_basis_and_handles(tmp_path,monkeypatch):
    from laplace.writing import operations
    fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path)
    doc=operations._execute(tmp_path,'paper','work','document',{})
    source=operations._execute(tmp_path,'paper','work','source',{'files':['paper/body.tex']})
    human=read(tmp_path)[1]
    assert source['selection_identity']==human['selection_identity']==doc['selection_identity']
    assert doc['files'][0]['read_handle']['route']=='/projection/tex'


def test_restore_cannot_bypass_selected_readonly_authority(tmp_path,monkeypatch):
    md=fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path)
    _,before=read(tmp_path)
    saved=pv.bank_editor_save(md,md/'body.tex',b'Old author source.\n',author='fixture',surface='test')
    registry=tmp_path/'registry_projects.json';value=json.loads(registry.read_text());value['projects'][0]['manifest']['document']['read_only']=True;registry.write_text(json.dumps(value))
    refused=pv.restore_editor_save('paper','paper/body.tex',saved['version_id'],before['expected_source_digest'],before['selection_identity'])
    assert refused['status']==409 and refused['reason']=='selection-revision-conflict'
    assert (md/'body.tex').read_text()==before['content']


def test_visual_request_refuses_root_switch_even_when_shared_include_bytes_match(tmp_path,monkeypatch):
    from laplace.manuscript import review_surface as review
    md=fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path);monkeypatch.setattr(review,'_repo_root',lambda:tmp_path)
    basis=ms.observation('paper',tmp_path)
    before=(md/'body.tex').read_text().rstrip('\n')
    request={'verb':'rewrite','by':'fixture','file':'body.tex','line_start':1,'line_end':1,
             'before':before,'after':'A reviewed new sentence.','expected_selection':basis['selection_identity']}
    (md/'other.tex').write_text('\\documentclass{article}\n\\begin{document}\n\\input{body}\n\\end{document}\n')
    path=tmp_path/'registry_projects.json';config=json.loads(path.read_text());config['projects'][0]['manifest']['document']['root']='other.tex';path.write_text(json.dumps(config))
    refused=review.adjudicate(md,'paper',request,repo_root=tmp_path)
    assert refused['status']==409 and refused['reason']=='selection-revision-conflict'
    assert (md/'body.tex').read_text().rstrip('\n')==before and not (md/'feedback').exists()
    # Only an explicit new source observation supplies the changed basis.
    current=ms.observation('paper',tmp_path)
    applied=review.adjudicate(md,'paper',{**request,'expected_selection':current['selection_identity']},repo_root=tmp_path)
    assert applied['ok'] and (md/'body.tex').read_text().startswith(request['after'])


def test_visual_no_guard_is_refused_but_unregistered_legacy_scope_remains_explicit(tmp_path,monkeypatch):
    from laplace.manuscript import review_surface as review
    md=fixture(tmp_path);monkeypatch.setattr(review,'_repo_root',lambda:tmp_path)
    body=(md/'body.tex').read_text().rstrip('\n')
    request={'verb':'rewrite','by':'fixture','file':'body.tex','line_start':1,'line_end':1,'before':body,'after':'New words.'}
    refused=review.adjudicate(md,'paper',request,repo_root=tmp_path)
    assert refused['reason']=='selection-revision-conflict'
    bypass=review.adjudicate(md,'unregistered-name',request,repo_root=tmp_path)
    assert bypass['reason']=='source-project-required' and (md/'body.tex').read_text().rstrip('\n')==body
    legacy=tmp_path/'legacy';legacy.mkdir();(legacy/'fragment.tex').write_text('Legacy source.')
    applied=review.adjudicate(legacy,'unregistered-fixture',{**request,'file':'fragment.tex','before':'Legacy source.'},repo_root=tmp_path)
    assert applied['ok'] and (legacy/'fragment.tex').read_text()=='New words.'


def test_acknowledged_source_effect_survives_history_followup_failure(tmp_path,monkeypatch):
    md=fixture(tmp_path);monkeypatch.setattr(pv,'_repo_root',lambda:tmp_path)
    _,observed=read(tmp_path)
    def unavailable(*args,**kwargs):raise OSError('controlled snapshot failure')
    monkeypatch.setattr(pv,'bank_editor_save',unavailable)
    code,result=save(observed,'The source effect is real despite unavailable snapshot.\n')
    assert code==200 and result['source_committed'] and result['changed']
    assert result['snapshot_status']=='UNPROVED' and result['maintenance_warnings']
    assert result['consumed_source_digest']==observed['expected_source_digest']
    assert (md/'body.tex').read_text()=='The source effect is real despite unavailable snapshot.\n'
