"""Recorded material discovery must share handles, fences and bounded pages."""
import json
import pytest
from laplace.native import tools as writing_tools, contracts as writing_contracts
from laplace.web import project_work_surface as surface
from laplace.writing import operations
from test_writing_controller import _import_project
from laplace.native.declarations import PayloadAdmissionError

def seed(root):
    _import_project(root)
    def save(path,content,before=None):
        return operations._execute(root,'fixture','work','store_artifact',{'path':path,'content':content,'before':before})
    first=save('notes/brief.md','first')
    latest=save('notes/brief.md','latest','first')
    second=save('notes/evidence.md','evidence')
    return first,latest,second

def test_catalogue_pages_latest_receipts_with_shared_read_handles(tmp_path):
    first,latest,second=seed(tmp_path)
    (tmp_path/'sources/fixture/unrecorded.txt').write_text('not a receipt')
    page=surface.materials('fixture',{'limit':1},tmp_path)
    assert page['pagination']=={'offset':0,'limit':1,'total':2,'next_offset':1}
    row=page['materials'][0]
    assert row['id']==latest['id'] and row['recorded_revision']==latest['revision']
    read=operations._execute(tmp_path,'fixture','work',**row['read_handle'])
    assert read['content']=='latest' and read['recorded_revision']==latest['revision']
    other=surface.materials('fixture',{'offset':1,'limit':1},tmp_path)
    assert other['materials'][0]['id']==second['id'] and other['pagination']['next_offset'] is None
    model=operations._execute(tmp_path,'fixture','work','materials',{'limit':1})
    assert model==page
    code,mime,body=surface.handle('/work/materials',{'project':['fixture'],'limit':['1']},'GET',repo_root=tmp_path)
    assert code==200 and json.loads(body)==page
    assert list(writing_contracts.compact_catalogue({'materials'}))[0]['operation']=='materials'

def test_missing_or_escaped_material_never_becomes_mutation_authority(tmp_path):
    first,latest,second=seed(tmp_path)
    target=tmp_path/'writing_projects/fixture/notes/brief.md'
    # Resolve the actual project path through the owner; imports use state workspace.
    from laplace.projects import artifacts as writing_artifacts
    target=writing_artifacts.resolve_path(tmp_path,'fixture','notes/brief.md')
    target.unlink()
    page=surface.materials('fixture',{},tmp_path)
    assert page['materials'][0]['availability']=='missing'
    outside=tmp_path.parent/(tmp_path.name+'-outside.txt');outside.write_text('outside')
    target.symlink_to(outside)
    escaped=surface.materials('fixture',{},tmp_path)
    assert escaped['gaps_total']==2 and all(row['path']!='notes/brief.md' for row in escaped['materials'])
    outside.unlink()

@pytest.mark.parametrize('payload',[{'offset':-1},{'offset':True},{'limit':0},{'limit':51},{'limit':True},{'path':'guessed'},[]])
def test_catalogue_refuses_invalid_bounds(tmp_path,payload):
    _import_project(tmp_path)
    with pytest.raises(ValueError):surface.materials('fixture',payload,tmp_path)

def test_catalogue_refuses_unknown_project(tmp_path):
    with pytest.raises(ValueError):surface.materials('unknown',{},tmp_path)

def test_store_and_read_artifacts_share_exact_project_file_history(tmp_path):
    from laplace.work import history as author_history
    from test_writing_controller import _seed_revision
    _import_project(tmp_path)
    turn=_seed_revision(tmp_path,'fixture',[],suffix='material-history')
    payload={'path':'notes/brief.md','before':None,'content':'history target'}
    with pytest.raises(PayloadAdmissionError,match="'reason' is a required property"):   # the reason is owed
        writing_tools.execute(tmp_path,'fixture','work','store_artifact',payload,turn_id=turn)
    assert not author_history.history('fixture',{'file':'notes/brief.md'},tmp_path)['items']
    stored=writing_tools.execute(tmp_path,'fixture','work','store_artifact',
        {**payload,'reason':'Keep the brief the history read is checked against.'},turn_id=turn)
    assert stored['path'].endswith('notes/brief.md')
    writing_tools.execute(tmp_path,'fixture','work','read_artifact',{'path':'notes/brief.md','scope':'project'},turn_id=turn)
    matching=author_history.history('fixture',{'file':stored['path']},tmp_path)
    assert {item['operation'] for item in matching['items']}=={'store_artifact','read_artifact'}
    for item in matching['items']:
        assert item['targets'][0]['kind']=='artifact'
        assert item['targets'][0]['file']==stored['path']
        assert item['targets'][0]['artifact_path']=='notes/brief.md'
        assert item['targets'][0]['scope']=='project'
    assert not author_history.history('fixture',{'file':'notes/unrelated.md'},tmp_path)['items']
    _import_project(tmp_path,name='other-project')
    assert not author_history.history('other-project',{'file':stored['path']},tmp_path)['items']
    forged={'operation':'store_artifact','outcome':{'artifact':{'id':stored['id']}}}
    assert author_history._journal_targets(forged,'other-project',tmp_path)==[]
