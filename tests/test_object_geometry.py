"""Bounded owner geometry and request-local reuse on real synthetic owners."""
import copy,json
from urllib.parse import urlsplit,parse_qs
import pytest
from laplace import sdk
from laplace.core import identity
from laplace.work import project_work as W,owner_discovery as O,object_geometry as G,object_facets as F
from test_owner_discovery import workspace,NS_A,NS_B,NS_C,JOINS,GUIDE,EDITION,HARDEN,PRIVATE,PRIVATE_TITLE
from test_research_object_facets import scene
from test_research_workflow_runs import run_root


def offered(root,read):
    from laplace.web import project_work_surface as H
    target=urlsplit(read['http']['url'])
    status,_,raw=H.handle(target.path,parse_qs(target.query),'GET',repo_root=root)
    assert status==200,json.loads(raw)
    return json.loads(raw)


def test_actual_workspace_scope_issued_pages_and_privacy(workspace):
    root=workspace
    system=sdk.request({'facet':'neighbourhood','limit':3},root=root)
    assert system['focus']=={'reference':None,'coordinate':None}
    assert len(system['nodes'])==3 and system['pagination']['next_read']
    assert system['coverage']['atomic'] is False and system['coverage']['depth']==1
    page=offered(root,system['pagination']['next_read'])
    assert not ({x['key'] for x in page['nodes']} & {x['key'] for x in system['nodes']})
    ref=identity.reference('core.identity','subsystem',{'id':'adapter.desktop'})
    native=O.request(root,O.project_scope(NS_A,'native'),{'facet':'neighbourhood','reference':ref})
    wire=json.dumps(native)
    assert PRIVATE not in wire and PRIVATE_TITLE not in wire and NS_C not in wire
    assert any(x['kind']=='owner-binding' for x in native['edges'])
    assert all(x['source'] in {n['key'] for n in native['nodes']} and x['target'] in {n['key'] for n in native['nodes']} for x in native['edges'])
    assert offered(root,F.handle({'facet':'workspace','family':'work'}))['neighbourhood_read']
    (root/'geometry-system-sample.json').write_text(json.dumps({'system':system,'next':page,'project':native},indent=2))


def test_work_contains_requires_actual_history_cut_and_detachment(workspace):
    root=workspace;ref=O.work_reference(NS_A,GUIDE)
    original=W._tasks(NS_A,root)[GUIDE]
    W.task(NS_A,{'id':GUIDE,'title':original['title'],'goal':original['goal'],'depends_on':[HARDEN],'expected_work_revision':W._task_revision(original)},root)
    value=sdk.request({'facet':'neighbourhood','reference':ref},root=root)
    assert any(x['kind']=='contains' for x in value['edges'])
    assert any(x['kind']=='requires' for x in value['edges'])
    only=sdk.request({'facet':'neighbourhood','reference':ref,'relations':['contains']},root=root)
    assert all(x['kind']=='contains' for x in only['edges'])
    assert not any(n['reference']['identity'].get('id')==HARDEN for n in only['nodes'])
    assert len(only['frontier'])<=len(only['nodes'])+1
    child=next(x for x in value['nodes'] if x['reference']['identity'].get('id')==EDITION)
    assert child['detail_read'] and child['scope_read'] and child['timeline_read']
    history=offered(root,value['timeline_read'])
    assert history['events'] and history['events'][0]['kind']=='specification'
    old=history['pagination']['cut']
    raw=W._tasks(NS_A,root)[GUIDE]
    W.task(NS_A,{'id':GUIDE,'title':raw['title']+' updated','goal':raw['goal'],'expected_work_revision':W._task_revision(raw)},root)
    with pytest.raises(ValueError):O.request(root,O.owned_workspace('sdk'),{'facet':'timeline','reference':ref,'as_of':old})
    value['nodes'][0]['title']='MUTATED RETURN'
    assert 'MUTATED RETURN' not in json.dumps(sdk.request({'facet':'neighbourhood','reference':ref},root=root))
    selected=F.request(root,O.owned_workspace('sdk'),{'facet':'object','reference':ref})
    assert selected['neighbourhood_read'] and selected['scope_read'] and selected['timeline_read']
    (root/'geometry-work-sample.json').write_text(json.dumps({'map':value,'timeline':history,'object':selected},indent=2))


def test_pure_snapshot_one_fold_and_review_context_semantics(workspace,monkeypatch):
    root=workspace;calls=[];original=W._tasks
    def count(*a,**k):calls.append(a[0]);return original(*a,**k)
    monkeypatch.setattr(W,'_tasks',count);context={}
    raw=W.read_snapshot(NS_A,root,read_context=context,resolve=False)
    resolved=W.read_snapshot(NS_A,root,read_context=context)
    W.read(NS_A,{'view':'detail','id':GUIDE},root,read_context=context)
    assert raw is resolved and calls==[NS_A]
    from laplace.work import project_work_review as R
    task={'id':'test','project':NS_A,'title':'test','goal':'test','review_obligations':[{'id':'close','scope':'closure','label':'Closure','required':True,'independent':True,'inputs':[],'closure_work_id':'child'}]}
    digests={};done={'test':task,'child':{'id':'child','status':'done'}};pending={'test':task,'child':{'id':'child','status':'in-progress'}}
    a=R.facet(task,root,tasks=done,digests=digests,project=NS_A,read_context=context)
    again=R.facet(task,root,tasks=done,digests=digests,project=NS_A,read_context=context)
    b=R.facet(task,root,tasks=pending,digests=digests,project=NS_A,read_context=context)
    assert a==again and a!=b
    a['obligations'].clear()
    assert R.facet(task,root,tasks=done,digests=digests,project=NS_A,read_context=context)['obligations']
    metrics=context[('read-metrics',str(root.resolve()))]
    assert metrics['task_snapshots']==1 and metrics['review_facet_computations']==2
    (root/'geometry-read-economy-proof.json').write_text(json.dumps({'task_calls':calls,'metrics':metrics,'raw_vs_effective_distinct':True},indent=2))


def test_scientific_consumed_distinct_private_omission_no_source_reads(scene,monkeypatch):
    root,_=scene
    from laplace.research import concepts,object_context as R
    claim=R.reference('concept','logic','result:one');source=F.ref('domain.projects','source-file',project='logic',path='data/method.txt',scope='project')
    private=F.ref('domain.projects','source-file',project='logic',path='private/secret-name.txt',scope='project')
    from laplace.projects import artifacts
    private_art=artifacts.store(root,'logic',{'scope':'project','path':'private/hidden-artifact.txt','before':None,'content':'PRIVATE_ARTIFACT_SENTINEL','reason':'Public privacy fixture'})
    private_art_ref=F.ref('domain.projects','artifact',project='logic',id=private_art['id'])
    current=R.read(root,'logic',claim)
    R.change(root,'logic',{'reference':claim,'expected_basis':current['basis'],'request_id':'geometry-bind-public','operation':'bind-consumed',
        'consumed_bases':[{'reference':source,'basis':F._source(root,O.owned_workspace('sdk'),source)['basis']}]},admit=lambda *_:{'kind':'author','actor':'public'})
    net=concepts._network('logic',root);net=copy.deepcopy(net)
    node=net['nodes']['result:one'];node.setdefault('projection',{}).setdefault('consumed_bases',[]).append({'reference':private,'basis':'sha256:'+'f'*64})
    node['projection']['consumed_bases'].append({'reference':private_art_ref,'basis':private_art['revision']})
    monkeypatch.setattr(concepts,'_network',lambda *a:net)
    monkeypatch.setattr(concepts,'logical_plan',lambda *a,**k:(_ for _ in ()).throw(AssertionError('rich logical plan fanout')))
    from laplace.projects import project_data
    monkeypatch.setattr(project_data,'_file_record',lambda *a:(_ for _ in ()).throw(AssertionError('raw file hash')))
    value=sdk.request({'facet':'neighbourhood','reference':claim},root=root)
    edges=[e for e in value['edges'] if e['kind']=='consumed']
    assert len(edges)==1 and edges[0]['consumed_basis'] and edges[0]['qualification']=='PINNED'
    wire=json.dumps(value);assert 'secret-name' not in wire and 'PRIVATE_SENTINEL' not in wire and 'f'*64 not in wire
    assert private_art['id'] not in wire and 'hidden-artifact' not in wire and private_art['revision'] not in wire
    assert value['coverage'].get('privacy')
    (root/'geometry-science-sample.json').write_text(json.dumps(value,indent=2))


def test_versioned_definition_local_coordinate_native_http_and_context(workspace):
    root=workspace
    from laplace.pipeline import workflow_definitions as D
    scope=O.project_scope(NS_A,'sdk')
    body={'schema_version':D.SCHEMA,'title':'Public method workflow','steps':[
        {'id':'write','title':'Write the proposal','assignment':{'role':'author','instructions':'PRIVATE_PROMPT_SENTINEL'}},
        {'id':'review','title':'Review the evidence','parent_id':'write','assignment':{'role':'reviewer','instructions':'Do not transport this prompt'}}],
        'edges':[{'id':'route','from':'write','to':'review','kind':'control'}]}
    result=D.save(root,scope,{'request_id':'geometry-definition-save','expected_revision':None,'definition':body})
    ref=result['reference'];coordinate={'kind':'workflow-step','id':'review'}
    root_map=sdk.request({'facet':'neighbourhood','reference':ref,'project_lens':NS_A},root=root)
    assert not any(n.get('coordinate')=={'kind':'workflow-step','id':'review'} for n in root_map['nodes'])
    with pytest.raises(ValueError):sdk.request({'facet':'semantic-scope','coordinate':{'kind':'workflow-step','id':'write'}},root=root)
    payload={'facet':'semantic-scope','reference':ref,'coordinate':coordinate,'project_lens':NS_A}
    value=sdk.request(payload,root=root);http=offered(root,F.handle(payload))
    assert http['nodes']==value['nodes'] and http['edges']==value['edges']
    selected=next(n for n in value['nodes'] if n['coordinate']==coordinate)
    assert selected['adapter']['step_id']=='review' and selected['reference']['version']
    assert any(e['kind']=='configured-route' and e['qualification']=='CONFIGURED_ONLY' for e in value['edges'])
    assert 'PRIVATE_PROMPT_SENTINEL' not in json.dumps(value) and 'Do not transport' not in json.dumps(value)
    context=F.resolve_object_context(root,NS_A,{'reference':ref,'coordinate':coordinate,'expected_basis':selected['basis']})
    assert context['summary']['title']=='Review the evidence' and context['coordinate']==coordinate
    assert selected['conversation']['available'] and selected['conversation']['project']==NS_A
    assert selected['conversation']['object_context']=={'reference':ref,'coordinate':coordinate,'expected_basis':selected['basis']}
    unversioned=D.reference(ref['identity']['id'])
    with pytest.raises(ValueError):sdk.request({**payload,'reference':unversioned},root=root)
    with pytest.raises(ValueError):sdk.request({**payload,'coordinate':{'kind':'workflow-step','id':'missing'}},root=root)
    from laplace.native import tools
    native=tools.execute(root,NS_A,'work','project',{'view':'discovery','request':payload})
    assert native['nodes']==value['nodes']
    (root/'geometry-definition-sample.json').write_text(json.dumps(value,indent=2))


def test_selected_work_phase_local_coordinate_and_record_history(workspace,scene):
    root=workspace
    # Existing attached phase row; the phase body remains at its canonical read.
    row={'record':'project-work-phase','id':'PHASE-public-geometry','project':NS_A,'work_id':GUIDE,'phase':'handoff',
        'state':'COMPLETE','request_id':'phase-geometry','ts':'2026-10-27T00:00:00Z','inputs':{},'actor':{'origin':'human'},'intent':'public'}
    W._append(root,row)
    ref=O.work_reference(NS_A,GUIDE);coord={'kind':'work-phase','id':row['id']}
    value=sdk.request({'facet':'semantic-scope','reference':ref,'coordinate':coord},root=root)
    node=next(n for n in value['nodes'] if n['coordinate']==coord)
    assert node['adapter']['kind']=='work-review-phase' and node['adapter']['phase_id']==row['id']
    assert node['detail_read']['native']['payload']['phase_id']==row['id']
    resolved=F.resolve_object_context(root,NS_A,node['conversation']['object_context'])
    assert resolved['coordinate']==coord
    science,_=scene
    from laplace.research import object_context as R
    record=R.reference('research-record','logic','R7')
    timeline=sdk.request({'facet':'timeline','reference':record},root=science)
    assert timeline['events'][-1]['kind']=='record-current' and timeline['observations'][0]['coverage']['source_currentness']=='NOT_CHECKED'
    (root/'geometry-local-phase-proof.json').write_text(json.dumps({'phase':value,'record_history':timeline},indent=2))


def test_delivery_neighbourhood_admitted_coordinates_and_selected_timeline(run_root,monkeypatch):
    from test_research_workflow_runs import start_run
    from laplace.writing import records
    s=run_root;root=s['root'];start_run(s)
    def forbidden(*a,**k):raise AssertionError('Geometry must not open recipient reply bodies.')
    monkeypatch.setattr(records,'fold_records',forbidden)
    ref=O.work_reference('book',s['work'])
    value=sdk.request({'facet':'neighbourhood','reference':ref,'relations':['admitted-route']},root=root)
    assert len(value['edges'])==1 and value['edges'][0]['kind']=='admitted-route'
    node=next(n for n in value['nodes'] if n['kind']=='delivery-event')
    assert node['standing']['admission_observation']=='VERIFIED_WRITING_TURN'
    local=sdk.request({'facet':'timeline','reference':ref,'coordinate':node['coordinate'],'lane':'delivery-events'},root=root)
    assert len(local['events'])==1 and local['events'][0]['coordinate']==node['coordinate']
    assert all(e['coordinate']==node['coordinate'] for e in local['events'])
    (root/'geometry-delivery-sample.json').write_text(json.dumps({'map':value,'selected_timeline':local},indent=2))


def test_shared_preview_read_doors_and_changed_manuscript_confirmation_refusal(run_root):
    from laplace.writing import workflow_progression as P,reads
    from laplace.native import tools
    from laplace.writing.schemas import SCHEMAS
    from laplace.web import project_work_surface as H,writing_declared_http
    from laplace.native.declarations import HTTP_DECLARATIONS
    from jsonschema import Draft202012Validator
    from urllib.parse import urlencode
    import hashlib
    s=run_root;root=s['root'];view=P.view(root,'book',s['work'])
    wire={'action':'workflow-impact-preview','work_id':s['work'],'expected_work_revision':view['work']['revision'],
        'expected_run_revision':view['revision'],'expected_plan_generation':view['plan_generation'],
        'intervention':{'action':'workflow-replan','reference':s['saved']['reference']}}
    assert Draft202012Validator(SCHEMAS['work_delivery']).is_valid(wire)
    assert reads.effect('work_delivery',wire)=='read'
    query={'project':['book'],'request':[json.dumps(wire)]}
    status,_,raw=H.handle('/work/delivery',query,'GET',repo_root=root)
    assert status==200,json.loads(raw)
    human=json.loads(raw);assert human['state']=='READY' and human['domain_effects']==[]
    native=tools.execute(root,'book','work','work_delivery',wire)
    assert native['state']=='READY' and native['impact_basis']==human['impact_basis']
    assert human['confirmation']['permitted'] and not native['confirmation']['permitted']
    # Same projection, but a read without an admitted original author cannot
    # borrow the human door's confirmation authority.
    geometry={'facet':'semantic-scope','reference':O.work_reference('book',s['work']),'relations':['contains','admitted-route']}
    assert Draft202012Validator(HTTP_DECLARATIONS['work/object-discovery'].payload).is_valid(geometry)
    assert {'coordinate','relations'}<=set(HTTP_DECLARATIONS['work/object-discovery'].extras['json_query_fields'])
    (s['manuscript']/'main.tex').write_text((s['manuscript']/'main.tex').read_text()+'\nChanged scientific premise.\n')
    def domain_files():return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and not p.name.endswith('.lock')}
    before=domain_files();confirm=human['confirmation']['http']['payload']
    status,_,refused=H.handle('/work/delivery',{},'POST',json.dumps(confirm).encode(),root)
    assert status==409,json.loads(refused)
    assert domain_files()==before and len(s['launches'])==1
    (root/'geometry-preview-shared-door-proof.json').write_text(json.dumps({'request':wire,'human':human,'native':native,
        'changed_input_refusal':json.loads(refused),'domain_files_unchanged_after_refusal':True},indent=2))
