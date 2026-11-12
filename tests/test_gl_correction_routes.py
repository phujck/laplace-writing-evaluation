"""Replay emitted continuation handles and actual normalized source aliases."""
import json
import pytest
from laplace.manuscript import project_structure as structure
from laplace.native import tools as writing_tools
from laplace.research import references_surface as refs, literature
from test_project_structure import _fixture
from test_literature_joined_workflow import project,bind


@pytest.mark.parametrize('section_offset,expected',[(1,'inner'),(2,'N2')])
def test_later_nested_and_normal_member_handle_replays_exact_scoped_collection(tmp_path,section_offset,expected):
    md=_fixture(tmp_path)
    (md/'N1.tex').write_text('\\chapter{Opening}\nOpening prose.\n\\section{Inner}\nInner prose.\n')
    path=md/'projection_plan.json';plan=json.loads(path.read_text())
    plan['sections'][0].update(kind='chapter',source_file='N1.tex')
    plan['sections'].insert(1,{'id':'inner','title':'Inner','kind':'section','parent_id':'N1',
        'source_file':'N1.tex','nodes_in_order':['def:one','res:one'],'beats':[],'job':'Nested explanation.'})
    path.write_text(json.dumps(plan))
    offered=writing_tools.execute(tmp_path,'book','work','help',{'operation':'structure'})['action']['navigation_reads']['start']
    first=writing_tools.execute(tmp_path,'book','work',offered['operation'],{**offered['payload'],
        'section_offset':section_offset,'section_limit':1,'member_limit':1})
    section=first['sections']['items'][0];assert section['id']==expected
    next_read=section['members']['next_read']
    second=writing_tools.execute(tmp_path,'book','work',next_read['operation'],next_read['payload'])
    assert [row['id'] for row in second['sections']['items']]==[expected]
    assert second['sections']['offset']==0 and second['as_of']==first['as_of']
    assert second['sections']['items'][0]['members']['offset']==1
    assert len(second['sections']['items'][0]['members']['items'])==1
    assert next_read['payload']['section_ids']==[expected] and next_read['payload']['section_offset']==0


@pytest.mark.parametrize('claim',['result:first','result:second','claim:unassociated'])
def test_actual_registered_aliases_share_claim_scope_and_visible_counts(tmp_path,monkeypatch,claim):
    md,_,key,_=project(tmp_path,monkeypatch);bound=bind(tmp_path,key)
    (md/'chapters/chapter-01.tex').write_text('\\section{First claim}\n'+
        'Other \\cite{Other}.\n'*50+'One \\cite{FixtureSource}.\nTwo \\cite{FixtureSource}.\n')
    aliases=[key,'FixtureSource',bound['canonical_source']];results=[]
    for alias in aliases:
        _,item=literature.resolve_item('joined',alias,tmp_path)
        assert item['key']==key
        row=refs.literature_uses('joined',tmp_path,key=alias,claim_id=claim,citation_limit=10)
        visible=sum(len(use['manuscript_uses']) for use in row['uses'])+len(row['unassociated_uses'])
        expected=2 if claim=='result:first' else 0
        assert row['pagination']['citation_total']==expected and visible==expected
        assert row['pagination']['next_citation_offset'] is None
        results.append((row['pagination'],row['uses'],row['unassociated_uses'],row['citation_scope']['citekeys']))
    assert all(row==results[0] for row in results)


def test_genuinely_unbound_registered_source_key_and_citation_alias_remain_visible(tmp_path,monkeypatch):
    md,_,key,_=project(tmp_path,monkeypatch)
    (md/'chapters/chapter-01.tex').write_text('\\section{First claim}\nUnbound \\cite{FixtureSource}.\n')
    results=[]
    for alias in [key,'FixtureSource']:
        _,item=literature.resolve_item('joined',alias,tmp_path)
        assert item['key']==key and item['citation_key']=='FixtureSource'
        row=refs.literature_uses('joined',tmp_path,key=alias,citation_limit=10)
        assert row['pagination']['citation_total']==1
        assert sum(len(use['manuscript_uses']) for use in row['uses'])+len(row['unassociated_uses'])==1
        assert all(not use.get('claim_id') for use in row['uses'])
        results.append((row['pagination'],row['uses'],row['unassociated_uses'],row['citation_scope']['citekeys']))
    assert all(row==results[0] for row in results)
