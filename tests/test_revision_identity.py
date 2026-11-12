"""SHA-256 formatting is not a content change; different identities remain stale."""
import pytest
from laplace.core.identity import revision_matches
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.research import concepts as concepts_surface, literature_support
from laplace.manuscript import project_structure, proposal_basis
from laplace.pipeline import formal_verification

A='1a'*32
B='2b'*32


@pytest.mark.parametrize('expected,actual',[(A,A),('sha256:'+A,A),(A,'sha256:'+A),('sha256:'+A,'sha256:'+A),(A.upper(),'sha256:'+A)])
def test_same_sha256_identity_accepts_only_equivalent_spellings(expected,actual):
    assert revision_matches(expected,actual)


@pytest.mark.parametrize('expected,actual',[(B,A),('sha256:'+B,A),('sha512:'+A,A),('md5:'+A,A),('sha256:arbitrary','arbitrary'),('arbitrary',A),('sha256:'+A+':extra',A),(None,None),(1,1),('sha256:'+A,'sha512:'+A)])
def test_different_hash_algorithm_or_arbitrary_prefix_cannot_match(expected,actual):
    assert not revision_matches(expected,actual)


def make_project(root):
    status,out=writing_projects.create({'name':'hash-audit','title':'Revision identity fixture','kind':'paper','purpose':'Isolated guard test','audience':'Test'},root)
    assert status==201,out
    return out


def test_live_logical_and_concept_guards_accept_prefix_without_changing_outputs(tmp_path):
    make_project(tmp_path)
    def execute(op,payload):return writing_tools.execute(tmp_path,'hash-audit','work',op,payload)
    logical=execute('logical_plan',{});assert len(logical['revision'])==64
    node='result:guard-audit'
    assert execute('logical_plan_change',{'operation':'add_object','base_revision':'sha256:'+logical['revision'],'node':node,'kind':'result','meaning':'A limited fixture claim.'})['ok']
    concept=concepts_surface.state('hash-audit',node,root=tmp_path)
    assert execute('concept_change',{'operation':'edit_node','base_revision':'sha256:'+concept['revision'],'node':node,'value':'The same fixture, clarified.'})['ok']
    current=execute('logical_plan',{})
    wrong_owner=execute('structure',{})['revision']
    assert not revision_matches(wrong_owner,current['revision'])
    with pytest.raises(ValueError,match='revision conflict'):
        execute('logical_plan_change',{'operation':'edit_meaning','base_revision':wrong_owner,'node':node,'meaning':'Must not apply.'})
    assert len(execute('logical_plan',{})['revision'])==64


def test_selected_source_structure_guard_compares_hash_identity(tmp_path):
    make_project(tmp_path)
    state=project_structure.state('hash-audit',tmp_path)
    payload={'operation':'initialize','expected_revision':state['revision'].removeprefix('sha256:'),
             'expected_source_revision':'sha256:'+state['selected_source']['revision'],
             'sections':[{'id':'intro','title':'Introduction','kind':'section','file':'chapters/chapter-01.tex'}]}
    with pytest.raises(ValueError,match='selected source revision conflict'):
        project_structure.change('hash-audit',{**payload,'expected_source_revision':'sha256:'+B},tmp_path)
    assert project_structure.change('hash-audit',payload,tmp_path)['status']=='CURRENT'


def test_claim_and_declared_content_guards_keep_canonical_stored_revision(tmp_path,monkeypatch):
    from test_literature_joined_workflow import project,execute
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    concept=concepts_surface.state('joined','result:first',root=tmp_path)
    basis=proposal_basis.assess(tmp_path,'joined',{'file':'chapters/chapter-01.tex','line_start':2,'line_end':2,
        'develops':[{'id':'result:first','content_revision':concept['content_revision'].removeprefix('sha256:')}]})
    assert basis['errors']==[]
    read=execute(tmp_path,'reference_text',{'key':key})
    revision=literature_support.meaning_revision('joined','result:first',tmp_path)
    linked=execute(tmp_path,'literature_bind',{'key':key,'claim_id':'result:first','claim_revision':revision.removeprefix('sha256:'),
        'relation':'supports','rationale':'The observed source supports the bounded fixture statement.','reading_status':'partial',
        'reading_id':read['reading_receipt']['id'],'evidence':{'locator':read['reading_receipt']['locator']}})
    assert linked['association']['claim_revision']==revision


def test_formal_target_guards_preserve_exact_owner_spelling(monkeypatch,tmp_path):
    target={'kind':'concept','id':'result:fixture','revision':'sha256:'+A,'source_revision':'sha256:'+B,'binding_ready':True,
            'handle':'fixture','label':'Fixture','statement_tex':'x=x','domain':'fixture','assumptions':[],'source_locations':[]}
    monkeypatch.setattr(formal_verification,'concept_target',lambda *args,**kwargs:target)
    bound=formal_verification._concept('fixture','result:fixture',A,B,tmp_path)
    assert bound['revision']=='sha256:'+A and bound['source_revision']=='sha256:'+B
    with pytest.raises(ValueError,match='concept_revision is stale'):
        formal_verification._concept('fixture','result:fixture',B,B,tmp_path)
    with pytest.raises(ValueError,match='source_revision is stale'):
        formal_verification._concept('fixture','result:fixture',A,'sha512:'+B,tmp_path)
