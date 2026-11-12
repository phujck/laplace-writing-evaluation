"""Proposed declaration closure over tiny explicit roots, never old .fls authority."""
from pathlib import Path
import hashlib

from laplace.manuscript import tex_dependencies as owner


def write(root,path,content):
    file=root/path;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(content);return file


def source(root):
    write(root,'paper/main.tex',r'\documentclass{article}\input{old}')
    write(root,'paper/old.tex','Old input.')
    return {'root':'paper/main.tex','selection_identity':'sha256:'+'0'*64}


def test_proposed_root_recursive_class_and_new_inputs_replace_old_recorder_graph(tmp_path):
    selected=source(tmp_path)
    write(tmp_path,'paper/new.tex',r'New input.\input nested')
    write(tmp_path,'paper/nested.tex','Nested input.')
    write(tmp_path,'paper/custom.cls',r'\LoadClass{article}\RequirePackage{local}')
    write(tmp_path,'paper/local.sty',r'\input{defs}')
    write(tmp_path,'paper/defs.tex','Definitions.')
    write(tmp_path,'paper/main.fls','INPUT old.tex\n')
    proposed=r'\documentclass{custom}\input{new}'
    closure=owner.prepare_closure('book',tmp_path,selected,{'paper/main.tex':proposed})
    assert closure['status']=='COMPLETE'
    assert {row['path'] for row in closure['members']}=={'paper/main.tex','paper/new.tex','paper/nested.tex','paper/custom.cls','paper/local.sty','paper/defs.tex'}
    assert closure['installed_requests']==[{'role':'class','name':'article','status':'INSTALLED_TEX_REQUEST_UNVERIFIED'}]
    assert not owner.closure_changes(closure,tmp_path)


def test_bst_and_transitive_aliases_are_exact_private_stage_geometry(tmp_path):
    selected=source(tmp_path)
    write(tmp_path,'material/style-real.bst','Exact BST.')
    (tmp_path/'paper/style.bst').symlink_to('../material/style-real.bst')
    write(tmp_path,'material/custom.cls',r'\RequirePackage{local}')
    (tmp_path/'paper/custom.cls').symlink_to('../material/custom.cls')
    write(tmp_path,'paper/local.sty','Local package.')
    closure=owner.prepare_closure('book',tmp_path,selected,{'paper/main.tex':r'\documentclass{custom}\bibliographystyle{style}'})
    assert closure['status']=='COMPLETE'
    assert closure['aliases']['paper/style.bst']=='../material/style-real.bst'
    assert {'paper/custom.cls','material/custom.cls','paper/style.bst','material/style-real.bst'}<={row['path'] for row in closure['members']}
    (tmp_path/'paper/style.bst').unlink();(tmp_path/'paper/style.bst').symlink_to('../material/custom.cls')
    assert 'alias:paper/style.bst' in owner.closure_changes(closure,tmp_path)


def test_missing_dynamic_and_escaping_inputs_stay_unproved_without_fallback(tmp_path):
    selected=source(tmp_path)
    closure=owner.prepare_closure('book',tmp_path,selected,{'paper/main.tex':r'\input{missing}\input{\chosen}\input{../../../outside}'})
    assert closure['status']=='UNPROVED'
    assert {'MISSING_DECLARATION','DYNAMIC_DECLARATION','ESCAPING_DECLARATION'}<={row['code'] for row in closure['diagnostics']}
    assert [row['path'] for row in closure['members']]==['paper/main.tex']
    write(tmp_path,'paper/missing.tex','A later new input.')
    assert 'absence:paper/missing.tex' in owner.closure_changes(closure,tmp_path)


def test_same_proposal_reuses_identity_and_explicit_archive_witness_does_not_install(tmp_path):
    selected=source(tmp_path);text='Class bytes.';write(tmp_path,'paper/custom.cls',text)
    witness={'path':None,'content':text,'sha256':'sha256:'+hashlib.sha256(text.encode()).hexdigest(),'source':{'repository':'declared','path':'template.zip','member':'custom.cls'}}
    args=('book',tmp_path,selected,{'paper/main.tex':r'\documentclass{custom}'},[witness])
    first=owner.prepare_closure(*args);second=owner.prepare_closure(*args)
    assert first==second and first['status']=='COMPLETE'
    assert first['template_witnesses'][0]['matched_paths']==['paper/custom.cls']
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob('*') if path.is_file())==['paper/custom.cls','paper/main.tex','paper/old.tex']
