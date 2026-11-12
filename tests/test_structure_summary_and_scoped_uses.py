"""Scoped navigation and citation paging over the existing truth owners."""
import json
from pathlib import Path
import pytest
from laplace.manuscript import project_structure as structure
from laplace.web import project_work_surface
from laplace.native import tools as writing_tools
from laplace.research import corpus_ingest
from laplace.writing import operations
from laplace.research import references_surface as refs, literature, literature_support
from test_project_structure import _fixture,_hashes


def test_scoped_summary_preserves_detail_guards_and_reads_no_scientific_bodies(tmp_path,monkeypatch):
    _fixture(tmp_path)
    full=structure.state('book',tmp_path);before=_hashes(tmp_path)
    with monkeypatch.context() as m:
        m.setattr(literature_support,'for_node',lambda *a,**k:pytest.fail('navigation hydrated scientific support'))
        from laplace.web import research_surface
        from laplace.research import research_records   # the owner the code path reads (research family R1)
        m.setattr(research_records,'result_bindings',lambda *a,**k:pytest.fail('navigation hydrated result bodies'))
        summary=writing_tools.execute(tmp_path,'book','work','structure',{'view':'summary','section_ids':['N1']})
        code,_,raw=project_work_surface.handle('/work/structure',{'project':['book'],'view':['summary'],'section_ids':['["N1"]']},'GET',b'',repo_root=tmp_path)
    assert code==200 and json.loads(raw)==summary
    assert summary['support_assessment'].startswith('NOT_ASSESSED')
    assert 'plan:book' not in summary['identities']
    assert summary['identities']['plan-file:book']==full['identities']['plan-file:book']
    assert summary['identities']['selected-edition:book']==full['identities']['selected-edition:book']
    row=summary['sections']['items'][0]
    assert summary['sections']['total']==1 and row['precision']==full['sections'][0]['source']['precision'] and row['binding_status']==full['sections'][0]['source']['status']
    assert 'source' not in row and 'members' not in row and 'source_reads' not in row and 'clearing_action' not in row,'the list row carries the mark and one detail handle'
    hint=summary['sections']['items'][0]['detail_read']
    detail=writing_tools.execute(tmp_path,'book','work',hint['operation'],hint['payload'])
    assert detail==structure.context('book',{'section_ids':['N1']},tmp_path)
    guard=writing_tools.execute(tmp_path,'book','work',summary['full_guard_read']['operation'],summary['full_guard_read']['payload'])
    assert guard==full
    assert writing_tools.execute(tmp_path,'book','work','structure',{})['revision']==full['revision']
    assert {k:v for k,v in _hashes(tmp_path).items() if not k.startswith("contract/")}==before


def test_summary_paging_readcut_and_invalid_query_are_exact(tmp_path):
    md=_fixture(tmp_path)
    first=structure.read('book',{'view':'summary','section_limit':1,'object_limit':1},tmp_path)
    second=structure.read('book',first['sections']['next_read']['payload'],tmp_path)
    assert first['sections']['total']==second['sections']['total']==2
    assert [s['id'] for s in first['sections']['items']+second['sections']['items']]==['N1','N2']
    assert second['as_of']==first['as_of']
    objects=structure.read('book',first['logical_objects']['next_read']['payload'],tmp_path)
    assert objects['logical_objects']['offset']==1
    path=md/'projection_plan.json';plan=json.loads(path.read_text());plan['sections'][0]['job']='An authored plan change.';path.write_text(json.dumps(plan))
    with pytest.raises(ValueError,match='CHANGED_INPUT'):structure.read('book',first['sections']['next_read']['payload'],tmp_path)
    for query in [{'view':'summary','section_ids':['missing']},{'view':'summary','object_limit':201},{'view':'summary','section_offset':True},{'view':'full','section_ids':['N1']}]:
        with pytest.raises(ValueError):structure.read('book',query,tmp_path)


def test_missing_plan_summary_retains_inventory_paging_without_fake_plan_guard(tmp_path):
    md=_fixture(tmp_path);(md/'projection_plan.json').unlink()
    value=structure.read('book',{'view':'summary','object_limit':1},tmp_path)
    assert value['status']=='MISSING' and 'plan:book' not in value['identities']
    assert value['logical_objects']['total']>=4 and value['logical_objects']['next_read']


@pytest.mark.parametrize('count',[2,20,100])
def test_summary_work_and_payload_do_not_grow_with_scientific_body_copies(tmp_path,monkeypatch,count):
    md=_fixture(tmp_path)
    path=md/'projection_plan.json';plan=json.loads(path.read_text());template=plan['sections'][0]
    plan['sections']=[{**template,'id':'section-'+str(i),'source_file':'N1.tex','source_title':'Opening','title':'Topic '+str(i)} for i in range(count)]
    path.write_text(json.dumps(plan))
    calls=[];body='Generic scientific support sentence. '*1500
    def support(project,ident,*args,**kwargs):
        calls.append(ident);return {'node':ident,'sources':[{'excerpt':body}],'gaps':[]}
    monkeypatch.setattr(literature_support,'for_node',support)
    full=structure.state('book',tmp_path);full_calls=len(calls);calls.clear()
    value=structure.read('book',{'view':'summary','section_limit':2,'object_limit':2,'gap_limit':2},tmp_path)
    assert calls==[] and full_calls==len(set(template['nodes_in_order']+template['beats']))
    encoded=json.dumps(value).encode();assert len(encoded)<12000 and body not in encoded.decode()
    assert value['sections']['total']==count
    assert len(json.dumps(full).encode())>len(encoded)*5


def uses_fixture(root,monkeypatch,*,extra_claim=False,unattached=False):
    main=root/'main.tex';main.write_text('\\documentclass{article}\\begin{document}Fixture.\\end{document}\n')
    rows=[] if unattached else [{'key':'local:K','claim_id':'claim:C','citekey':'K','metadata':{},'relation':'supports'}]
    if extra_claim:rows.append({'key':'local:J','claim_id':'claim:C','citekey':'J','metadata':{},'relation':'contradicts'})
    spans=[{'citekey':'Other','file':'main.tex','line_start':i+1,'line_end':i+1,'text':'\\cite{Other}'} for i in range(50)]+[{'citekey':'K','file':'main.tex','line_start':51+i,'line_end':51+i,'text':'\\cite{K}'} for i in range(2)]
    if extra_claim:spans.append({'citekey':'J','file':'main.tex','line_start':53,'line_end':53,'text':'\\cite{J}'})
    monkeypatch.setattr(refs,'_manuscript',lambda *a,**k:root)
    monkeypatch.setattr(refs,'citation_spans',lambda *a,**k:({'root':'main.tex','revision':'source-fixture'},spans,{'diagnostics':[]}))
    monkeypatch.setattr(refs,'_load_associations',lambda *a,**k:rows)
    monkeypatch.setattr(literature,'resolve_item',lambda *a,**k:('local',{'key':'local:K','citation_key':'K'}))
    monkeypatch.setattr(literature,'canonical_rows',lambda *a,**k:[])
    monkeypatch.setattr(literature,'bibliography_projection',lambda *a,**k:{'state':'fixture'})
    monkeypatch.setattr(literature_support,'network',lambda *a,**k:{'nodes':{},'relations':[]})


def test_scoped_key_claim_matches_are_filtered_before_page_and_unfiltered_stays_global(tmp_path,monkeypatch):
    uses_fixture(tmp_path,monkeypatch)
    scoped=refs.literature_uses('fixture',tmp_path,key='K',claim_id='claim:C',limit=6,citation_limit=10)
    assert scoped['pagination']['citation_total']==2 and scoped['pagination']['next_citation_offset'] is None
    assert len(scoped['uses'][0]['manuscript_uses'])==2 and scoped['unassociated_uses']==[]
    assert scoped['citation_scope']['kind']=='query' and 'entailment is not assessed' in scoped['citation_scope']['attribution']
    global_page=refs.literature_uses('fixture',tmp_path,citation_limit=10)
    assert global_page['pagination']['citation_total']==52 and global_page['pagination']['next_citation_offset']==10
    assert len(global_page['unassociated_uses'])==10 and global_page['citation_scope']['kind']=='project'
    page=refs.literature_uses('fixture',tmp_path,key='K',citation_offset=1,citation_limit=1)
    assert len(page['uses'][0]['manuscript_uses'])==1 and page['pagination']['citation_total']==2


def test_claim_scope_citation_page_uses_full_query_not_only_association_page(tmp_path,monkeypatch):
    uses_fixture(tmp_path,monkeypatch,extra_claim=True)
    first=refs.literature_uses('fixture',tmp_path,claim_id='claim:C',limit=1,citation_limit=1)
    assert first['pagination']['total']==2 and first['pagination']['citation_total']==3
    assert first['citation_scope']['citekeys']==['J','K']
    assert first['pagination']['next_offset']==1 and first['pagination']['next_citation_offset']==1


def test_unattached_key_reports_its_literal_uses_without_invented_binding(tmp_path,monkeypatch):
    uses_fixture(tmp_path,monkeypatch,unattached=True)
    result=refs.literature_uses('fixture',tmp_path,key='K',citation_limit=10)
    assert result['uses']==[] and result['pagination']['citation_total']==2 and len(result['unassociated_uses'])==2


def test_scoped_uses_http_and_native_delegate_same_owner(tmp_path,monkeypatch):
    uses_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(refs,'_root',lambda:tmp_path)
    payload={'key':'K','claim_id':'claim:C','limit':6,'citation_limit':10}
    direct=refs.literature_uses('fixture',tmp_path,**payload)
    code,_,raw=refs.handle('/references/literature-uses',{'project':['fixture'],**{k:[str(v)] for k,v in payload.items()}},'GET',b'',repo_root=tmp_path)
    assert code==200 and json.loads(raw)==direct
    assert operations._execute(tmp_path,'fixture','work','literature_uses',payload)==direct


def test_registered_source_real_citation_spans_resolve_scoped_aliases(tmp_path,monkeypatch):
    from test_literature_joined_workflow import project,bind,execute
    md,source,key,_=project(tmp_path,monkeypatch)
    bind(tmp_path,key)
    chapter=md/'chapters/chapter-01.tex'
    chapter.write_text('\\section{First claim}\n'+('Unrelated citation \\cite{Other}.\n'*50)+
        'A saved source \\cite{FixtureSource}.\nAnother \\cite{FixtureSource}.\n')
    read=execute(tmp_path,'literature_uses',{'key':'FixtureSource','claim_id':'result:first','citation_limit':10})
    assert read['pagination']['citation_total']==2 and read['pagination']['next_citation_offset'] is None
    assert len(read['uses'][0]['manuscript_uses'])==2
    canonical=execute(tmp_path,'literature_uses',{'key':key,'claim_id':'result:first','citation_limit':10})
    assert canonical['uses']==read['uses']


def test_native_http_contracts_expose_summary_and_preserve_strict_legacy_shape():
    from laplace.writing.schemas import SCHEMAS
    from jsonschema import Draft202012Validator
    native=Draft202012Validator(SCHEMAS['structure'])
    assert not list(native.iter_errors({'view':'summary','section_ids':['a'],'object_limit':1}))
    assert list(native.iter_errors({'view':'summary','unknown':True}))
    assert list(native.iter_errors({'unknown':True}))
    assert not list(native.iter_errors({'section_ids':['a']}))
    http=Draft202012Validator(structure.http_read_contract())
    assert not list(http.iter_errors({'project':'book','view':'summary','section_ids':['a']}))
    assert list(http.iter_errors({'project':'book','view':'full','section_ids':['a']}))
    assert not list(http.iter_errors({'project':'book'}))


def test_offered_navigation_recipe_and_paginated_members_are_usable(tmp_path):
    md=_fixture(tmp_path)
    from laplace.native import declarations as writing_declarations
    from laplace.writing import operating as writing_operating
    help_value=writing_tools.execute(tmp_path,'book','work','help',{'operation':'structure'})['action']
    recipe=help_value['navigation_reads']
    first=writing_tools.execute(tmp_path,'book','work',recipe['start']['operation'],recipe['start']['payload'])
    chosen=first['sections']['items'][0]['id']
    assert first['sections']['items'][0]['member_count']==3 and 'members' not in first['sections']['items'][0]
    request={**recipe['section_detail']['payload'],'section_ids':[chosen],'member_limit':1}
    selected=writing_tools.execute(tmp_path,'book','work','structure',request)
    member_page=selected['sections'][0]['members']
    assert len(member_page['items'])==1 and member_page['total']==3 and member_page['items'][0]['detail_read']['operation']=='concept'
    next_page=writing_tools.execute(tmp_path,'book','work','structure',member_page['next_read']['payload'])
    assert next_page['sections'][0]['members']['offset']==1 and next_page['sections'][0]['id']==chosen
    assert 'node_ids' not in writing_tools.execute(tmp_path,'book','work','structure',{**recipe['selected_sections']['payload'],'section_ids':[chosen]})['sections']['items'][0]
    legacy=writing_tools.execute(tmp_path,'book','work','structure',{})
    assert legacy['reader_plan']['sections'][0]['node_ids']==['res:one','def:one']
    discovery=next(row for row in writing_operating.tool_contract()['action_catalogue'] if row['operation']=='structure')
    assert 'view:summary' in discovery['does']


def test_wide_membership_is_paged_and_ordered_without_inaccessible_ids(tmp_path):
    md=_fixture(tmp_path)
    path=md/'projection_plan.json';plan=json.loads(path.read_text())
    ids=['node:'+str(i) for i in range(600)]
    plan['sections'][0]['nodes_in_order']=ids;plan['sections'][0]['beats']=[]
    path.write_text(json.dumps(plan))
    listing=structure.read('book',{'view':'summary','section_ids':['N1']},tmp_path)
    assert listing['sections']['items'][0]['member_count']==600 and 'members' not in listing['sections']['items'][0] and len(json.dumps(listing['sections']['items']).encode())<1200,'the list row does not grow with membership'
    # a section too wide for the detail's reader hydration pages its members on an EXPLICIT scoped summary request
    with pytest.raises(ValueError,match='exceeds 80 canonical objects'):structure.read('book',{'view':'detail','section_ids':['N1'],'member_limit':20},tmp_path)
    first=structure.read('book',{'view':'summary','section_ids':['N1'],'member_limit':20},tmp_path)
    members=first['sections']['items'][0]['members']
    assert members['total']==600 and len(members['items'])==20
    assert [x['id'] for x in members['items']]==ids[:20]
    second=structure.read('book',members['next_read']['payload'],tmp_path)
    assert [x['id'] for x in second['sections']['items'][0]['members']['items']]==ids[20:40]
    assert len(json.dumps(first).encode())<18000
