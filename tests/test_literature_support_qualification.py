"""Source observations qualify the exact authored claim, not a future reinterpretation."""
from pathlib import Path
import pytest
from laplace.research import concepts as concepts_surface, corpus_ingest, literature_support
from laplace.native import tools as writing_tools
from test_literature_joined_workflow import project,bind,execute


def test_later_claim_change_invalidates_source_qualification_in_both_views(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    linked=bind(tmp_path,key)
    assert linked['support']['sources'][0]['qualification']=='PASSAGE_OBSERVED'
    before=concepts_surface.state('joined','result:first',root=tmp_path)
    execute(tmp_path,'concept_change',{'operation':'edit_node','node':'result:first','base_revision':before['revision'],
        'value':'A stronger proposition which is not the previously qualified claim.'})
    changed=literature_support.for_node('joined','result:first',tmp_path)
    assert changed['sources'][0]['qualification']=='CLAIM_CHANGED'
    uses=execute(tmp_path,'literature_uses',{'claim_id':'result:first'})
    assert uses['uses'][0]['evidence_currentness']=='STALE'
    assert uses['uses'][0]['source_qualification']=='CLAIM_CHANGED'
    with pytest.raises(ValueError,match='claim meaning changed'):
        execute(tmp_path,'literature_bind',{'key':key,'claim_id':'result:first','claim_revision':linked['association']['claim_revision'],
            'relation':'supports','rationale':'An old rationale','reading_status':'partial','evidence':{'locator':'Old observed passage'}})


def test_reader_placement_does_not_rewrite_claim_meaning_revision(tmp_path,monkeypatch):
    project(tmp_path,monkeypatch)
    before=literature_support.meaning_revision('joined','result:first',tmp_path)
    net=literature_support.network('joined',tmp_path)
    value={**net['nodes']['result:first'].get('projection',{}),'section_ref':'second'}
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'set-projection','node':'result:first','value':value}).get('ok')
    assert literature_support.meaning_revision('joined','result:first',tmp_path)==before


def test_help_misnamed_field_and_cross_project_payload_are_actionable(tmp_path):
    with pytest.raises(ValueError,match='help selector rejected.*use one selector axis'):
        writing_tools.execute(tmp_path,'selected','work','help',{'request':'source'})
    # D3: a payload naming another project is refused against the BOUND project (current pure admission wording),
    # and nothing is written anywhere
    before=sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*'))
    with pytest.raises(ValueError,match='Payload project conflicts with the bound project'):
        writing_tools.execute(tmp_path,'selected','work','help',{'operation':'source','project':'wrong'})
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*'))==before


def test_scope_has_no_phantom_acquisition_intents_for_qualified_sources(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    bind(tmp_path,key)
    scope=literature_support.scope('joined',tmp_path,node='result:first')
    assert any(gap['kind']=='not-yet-cited' for gap in scope['gaps'])
    assert scope['intents']==[]


def test_scope_without_claims_explains_why_completion_is_unavailable(tmp_path,monkeypatch):
    from laplace.projects import library as writing_projects
    from laplace.manuscript import storyboard
    monkeypatch.setattr(storyboard,'_repo_root',lambda:tmp_path)
    status,out=writing_projects.create({'name':'empty-scope','title':'Empty scope','kind':'paper','purpose':'Fixture','audience':'Test'},tmp_path)
    assert status==201,out
    scope=literature_support.scope('empty-scope',tmp_path)
    assert not scope['ready_for_completion']
    assert scope['gaps'][0]['kind']=='no-canonical-claims'


def _engineering_fixture(root):
    """Real source/rewire/work owners under one small isolated registry root."""
    import hashlib, json
    from test_concepts_surface import _nested_fixture, _change
    from test_project_work import guarded_task, guarded_transition
    from laplace.work import project_work
    from laplace.manuscript import project_protocol
    from laplace.pipeline import projection_spec
    _nested_fixture(root)
    source=root/'atlas/src/atlas/store.py';source.parent.mkdir(parents=True)
    source.write_text('def put(data):\n    return data\n')
    test=root/'tests/custody.py';test.parent.mkdir();test.write_text('assert put(b"x") == b"x"\n')
    result=root/'evidence/custody-result.json';result.parent.mkdir();result.write_text('{"normal":true,"corrupt_refused":true}\n')
    node='res:retention-and-projection'
    _change(root,operation='add_node',node=node,node_kind='result',essence='Scoped custody observation.')
    pin=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    _change(root,operation='set_source',node=node,value=[{'path':str(source.relative_to(root)),
        'sha256':pin(source),'line_start':1,'line_end':2}])
    guide=root/'graph/BACKGROUND.md';guide.write_text('[Custody support](/concepts/state?project=graph&node='+node+')\n')
    projection_spec.write_spec('graph',{'manuscript':{'working_guides':[{'path':'BACKGROUND.md','role':'background'}]}},root)
    task=guarded_task('graph',{'id':'check','title':'Observe custody','goal':'Observe this exact limited behavior.',
                              'kind':'engineering'},root)
    validation=root/'evidence/validation.json'
    def complete():
        meaning=literature_support.meaning_revision('graph',node,root)
        data={'schema_version':'laplace.engineering-validation/1','claim_id':node,
            'meaning_revision':meaning,'covered_scope':'Public body custody only',
            'inputs':[{'path':str(p.relative_to(root)),'sha256':pin(p),'role':role} for p,role in [(source,'source'),(test,'test')]],
            'outcome':'PASS','checks':[{'name':'Normal and corrupt custody paths','passed':True}],
            'result_evidence':{'path':str(result.relative_to(root)),'sha256':pin(result)}}
        validation.write_text(json.dumps(data))
        guarded_transition('graph',{'id':'check','status':'done','evidence':[
            str(p.relative_to(root)) for p in [source,test,result,validation]]},root)
        current=project_work.observe_core('graph',['check'],root)['tasks']['check']
        return {'work_id':'check','completion_revision':current['completion_revision'],
            'meaning_revision':meaning,'covered_scope':data['covered_scope'],
            'validation_path':'evidence/validation.json'}
    return {'node':node,'source':source,'test':test,'result':result,'validation':validation,
            'complete':complete,'guide':guide}


def _adopt_engineering(root, fixture, binding, guard=None):
    from laplace.research import concepts as cs
    current=cs.state('graph',fixture['node'],root=root)
    return cs.change({'project':'graph','operation':'set_projection','node':fixture['node'],
        'base_revision':guard or current['revision'],'value':{'engineering_support':[binding]},'by':'author'},root=root)


def test_engineering_adoption_is_stable_and_code_drift_reaches_claim_and_guide(tmp_path):
    from laplace.research import concepts as cs
    from laplace.manuscript import project_protocol
    from laplace.work import project_work
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']()
    before=literature_support.meaning_revision('graph',fixture['node'],tmp_path)
    code,out=_adopt_engineering(tmp_path,fixture,binding)
    assert code==200,out
    assert literature_support.meaning_revision('graph',fixture['node'],tmp_path)==before
    state=cs.context('graph',fixture['node'],tmp_path)
    assert state['source_support']['engineering_support']['status']=='CURRENT'
    guide=project_protocol.read('graph',{'path':'BACKGROUND.md'},tmp_path)
    assert guide['engineering_support']['status']=='CURRENT'
    current_work=project_work.observe_core('graph',['check'],tmp_path)['tasks']['check']
    assert current_work['completion_revision']==binding['completion_revision']
    assert all(x['path']!='graph/BACKGROUND.md' for x in current_work['evidence_receipts'])
    fixture['source'].write_text('def put(data):\n    raise ValueError(data)\n')
    changed=cs.context('graph',fixture['node'],tmp_path)
    engineering=changed['source_support']['engineering_support']
    assert engineering['status']=='REVIEW_REQUIRED'
    assert engineering['bindings'][0]['status']=='STALE'
    assert engineering['bindings'][0]['work_currentness']['kind']=='EVIDENCE_CHANGED'
    assert changed['source_support']['qualification']=='OPEN'
    assert changed['source_locations'][0]['status']=='UNRESOLVED'
    assert project_protocol.read('graph',{'path':'BACKGROUND.md'},tmp_path)['engineering_support']['status']=='REVIEW_REQUIRED'
    assert project_work.observe_core('graph',['check'],tmp_path)['tasks']['check']['status']=='blocked'


def test_renewed_work_requires_explicit_reack_and_meaning_requires_revalidation(tmp_path):
    from laplace.research import concepts as cs
    from laplace.manuscript import project_protocol
    from test_concepts_surface import _change
    fixture=_engineering_fixture(tmp_path);old=fixture['complete']();assert _adopt_engineering(tmp_path,fixture,old)[0]==200
    newer=fixture['complete']()
    assert newer['completion_revision']!=old['completion_revision']
    observed=cs.context('graph',fixture['node'],tmp_path)['source_support']['engineering_support']
    assert observed['bindings'][0]['status']=='ACK_REQUIRED'
    import json
    handle=observed['adoption_handle']
    assert handle['operation']=='concept_change' and handle['payload']['project']=='graph'
    code,ctype,raw=cs.handle(handle['http']['url'],{},'POST',json.dumps(handle['payload']).encode(),tmp_path)
    assert code==200,json.loads(raw)
    assert json.loads(raw)['state']['source_support']['engineering_support']['status']=='CURRENT'
    _change(tmp_path,operation='edit_node',node=fixture['node'],value='A stronger custody assertion.')
    state=cs.context('graph',fixture['node'],tmp_path)
    assert state['source_support']['engineering_support']['status']=='REVIEW_REQUIRED'
    assert 'current claim meaning' in state['source_support']['engineering_support']['bindings'][0]['reason']
    assert _adopt_engineering(tmp_path,fixture,newer)[0]==422
    renewed=fixture['complete']()
    assert _adopt_engineering(tmp_path,fixture,renewed)[0]==200
    assert project_protocol.read('graph',{'path':'BACKGROUND.md'},tmp_path)['engineering_support']['status']=='CURRENT'


@pytest.mark.parametrize('field,value',[('completion_revision','sha256:'+'f'*64),
    ('meaning_revision','sha256:'+'e'*64),('covered_scope','Unobserved scope'),
    ('validation_path','evidence/missing.json')])
def test_engineering_forged_or_missing_adoption_is_refused(tmp_path,field,value):
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']()
    code,out=_adopt_engineering(tmp_path,fixture,{**binding,field:value})
    assert code==422,out
    assert 'engineering_support' not in literature_support.network('graph',tmp_path)['nodes'][fixture['node']].get('projection',{})


def test_engineering_ack_uses_canonical_guard_and_test_pin(tmp_path):
    from laplace.research import concepts as cs
    from test_concepts_surface import _change
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']()
    guard=cs.state('graph',fixture['node'],root=tmp_path)['revision']
    _change(tmp_path,operation='add_node',node='unrelated',node_kind='definition',essence='Unrelated.')
    assert _adopt_engineering(tmp_path,fixture,binding,guard)[0]==409
    fixture['test'].write_text('assert False\n')
    code,out=_adopt_engineering(tmp_path,fixture,binding)
    assert code==422 and 'evidence changed' in out['error']


def test_engineering_producer_refuses_mutable_guide_evidence(tmp_path):
    import hashlib,json
    from test_project_work import guarded_transition
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']()
    value=json.loads(fixture['validation'].read_text())
    value['inputs'].append({'role':'source','path':'graph/BACKGROUND.md','sha256':hashlib.sha256(fixture['guide'].read_bytes()).hexdigest()})
    fixture['validation'].write_text(json.dumps(value))
    guarded_transition('graph',{'id':'check','status':'done','evidence':[
        'atlas/src/atlas/store.py','tests/custody.py','evidence/custody-result.json','evidence/validation.json','graph/BACKGROUND.md']},tmp_path)
    from laplace.work import project_work
    binding['completion_revision']=project_work.observe_core('graph',['check'],tmp_path)['tasks']['check']['completion_revision']
    code,out=_adopt_engineering(tmp_path,fixture,binding)
    assert code==422 and 'mutable acknowledgement' in out['error']


def test_engineering_core_shared_diamond_visits_each_evidence_once_and_no_literature_recursion(tmp_path,monkeypatch):
    from laplace.work import project_work
    from laplace.research import engineering_support
    from test_project_work import guarded_task,guarded_transition
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']()
    assert _adopt_engineering(tmp_path,fixture,binding)[0]==200
    for ident in ['left','right']:
        guarded_task('graph',{'id':ident,'title':ident,'goal':ident,'kind':'engineering','depends_on':['check']},tmp_path)
        guarded_transition('graph',{'id':ident,'status':'done','evidence':['evidence/custody-result.json']},tmp_path)
    guarded_task('graph',{'id':'diamond','title':'Diamond','goal':'Both paths','kind':'engineering','depends_on':['left','right']},tmp_path)
    guarded_transition('graph',{'id':'diamond','status':'done','evidence':['evidence/custody-result.json']},tmp_path)
    guarded_task('graph',{'id':'unrelated-literature','title':'Unrelated','goal':'No eager enrichment','kind':'literature-acquisition'},tmp_path)
    # A historical completed specialized task exists, but is outside this required closure.
    project_work._append(tmp_path,{'record':'project-work-transition','project':'graph',
        'id':'unrelated-literature','task_id':'unrelated-literature','status':'done'})
    calls=[];original=project_work._tasks
    monkeypatch.setattr(project_work,'_tasks',lambda *a:(calls.append(a),original(*a))[1])
    monkeypatch.setattr(literature_support,'scope',lambda *a,**k:pytest.fail('core entered literature scope'))
    context={}
    one=project_work.observe_core('graph',['diamond'],tmp_path,read_context=context)
    two=project_work.observe_core('graph',['check'],tmp_path,read_context=context)
    assert len(calls)==1
    assert one['read_metrics']['required_work_count']==4
    assert one['read_metrics']['unique_evidence_visits']==4
    assert two['read_metrics']['unique_evidence_visits']==4
    # Every evidence file is accounted once: bytes hashed in this request plus bytes whose
    # digest was reused by stat identity (the receipts hashed them moments earlier).
    metrics=two['read_metrics']
    assert metrics['hashed_bytes']+metrics['digest_cache_bytes']==sum(p.stat().st_size for p in [fixture['source'],fixture['test'],fixture['result'],fixture['validation']])
    assert metrics['digest_cache_bytes']>0 and metrics['hashed_bytes']==0
    net=literature_support.network('graph',tmp_path)
    first=engineering_support.observe('graph',fixture['node'],tmp_path,net,declarations=[binding],read_context=context)
    second=engineering_support.observe('graph',fixture['node'],tmp_path,net,declarations=[binding],read_context=context)
    assert first['status']==second['status']=='CURRENT'
    assert second['read_metrics']['unique_evidence_visits']==4
    from laplace.manuscript import project_protocol
    guide=project_protocol.support_for_path('graph',fixture['guide'],tmp_path,read_context=context)
    assert guide['status']=='CURRENT'
    shared={'support_by_node':{},'engineering_read_context':context,
            'relations_by_source':{},'associations_by_source':{}}
    claim=literature_support.for_node('graph',fixture['node'],tmp_path,net=net,associations=[],support_context=shared)
    assert claim['engineering_support']['read_metrics']['unique_evidence_visits']==4
    assert len(calls)==1
    fixture['source'].unlink()
    stale=project_work.observe_core('graph',['diamond'],tmp_path)
    assert stale['tasks']['diamond']['status']=='blocked'


def test_guide_artifact_annotation_is_current_historical_and_project_qualified(tmp_path):
    import json
    from laplace.web import research_surface
    from laplace.manuscript import project_protocol
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']()
    assert _adopt_engineering(tmp_path,fixture,binding)[0]==200
    query={'project':['graph'],'path':['BACKGROUND.md'],'scope':['project'],'format':['json']}
    status,ctype,raw=research_surface.handle('/research/artifact',query,'GET',b'',tmp_path)
    page=json.loads(raw)
    assert status==200,page
    assert page['engineering_support']['status']=='CURRENT'
    assert project_protocol.support_for_path('graph',fixture['guide'],tmp_path,historical=True)['status']=='HISTORICAL_ARTIFACT'
    other=tmp_path/'graph/UNCONFIGURED.md';other.write_text(fixture['guide'].read_text())
    assert project_protocol.support_for_path('graph',other,tmp_path) is None
    assert project_protocol.support_for_path('another',fixture['guide'],tmp_path) is None
    fixture['test'].unlink()
    status,ctype,raw=research_surface.handle('/research/artifact',query,'GET',b'',tmp_path)
    assert json.loads(raw)['engineering_support']['status']=='REVIEW_REQUIRED'
    query['expected_sha256']=['0'*64]
    status,ctype,raw=research_surface.handle('/research/artifact',query,'GET',b'',tmp_path)
    assert status==409


def test_engineering_stale_does_not_void_independent_historical_passage(tmp_path):
    import hashlib
    from test_concepts_surface import _change
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']()
    assert _adopt_engineering(tmp_path,fixture,binding)[0]==200
    _change(tmp_path,operation='add_node',node='ref:history',node_kind='citation',essence='Historical passage.')
    _change(tmp_path,operation='add_edge',node=fixture['node'],target='ref:history',rel='support')
    history=tmp_path/'retained-passage.txt';history.write_text('The limited historical custody observation.\n')
    association={'canonical_id':'ref:history','key':'history','claim_id':fixture['node'],
        'claim_revision':binding['meaning_revision'],'binding_state':'BOUND','citekey':'History',
        'reading_receipt':{'source_path':str(history),'source_sha256':'sha256:'+hashlib.sha256(history.read_bytes()).hexdigest(),
            'offset':0,'length':len(history.read_text()),'total_characters':len(history.read_text())}}
    fixture['source'].write_text('def put(data):\n    raise ValueError(data)\n')
    support=literature_support.for_node('graph',fixture['node'],tmp_path,associations=[association])
    assert support['sources'][0]['qualification']=='PASSAGE_OBSERVED'
    assert support['engineering_support']['status']=='REVIEW_REQUIRED'
    assert support['qualification']=='OPEN'



def test_unrequested_background_support_is_not_evaluated_by_operating_build(tmp_path,monkeypatch):
    from laplace.research import engineering_support
    from laplace.writing import operating as writing_operating
    from laplace.manuscript import project_protocol
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']()
    assert _adopt_engineering(tmp_path,fixture,binding)[0]==200
    original=engineering_support.guide_support
    monkeypatch.setattr(engineering_support,'guide_support',lambda *a,**k:pytest.fail('Unrequested background assurance was eagerly observed'))
    brief=writing_operating.build('graph','work',tmp_path)
    background=brief['project_protocol']['documents'][0]
    assert 'engineering_support' not in background and 'content' not in background
    assert background['engineering_support_read']['operation']=='project_guidance'
    monkeypatch.setattr(engineering_support,'guide_support',original)
    assert project_protocol.read('graph',{'path':'BACKGROUND.md'},tmp_path)['engineering_support']['status']=='CURRENT'
    fixture['source'].unlink()
    assert project_protocol.read('graph',{'path':'BACKGROUND.md'},tmp_path)['engineering_support']['status']=='REVIEW_REQUIRED'


def _engineering_recomplete(root, fixture, *, extra=(), dependencies=None, parent=None):
    from laplace.work import project_work
    from test_project_work import guarded_task, guarded_transition
    if dependencies is not None or parent is not None:
        changes={'id':'check','title':'Observe custody','goal':'Observe this exact limited behavior.','kind':'engineering'}
        if dependencies is not None:changes['depends_on']=dependencies
        if parent is not None:changes['parent_work_id']=parent
        guarded_task('graph',changes,root)
    evidence=['atlas/src/atlas/store.py','tests/custody.py','evidence/custody-result.json','evidence/validation.json',*extra]
    guarded_transition('graph',{'id':'check','status':'done','evidence':evidence},root)
    task=project_work.observe_core('graph',['check'],root)['tasks']['check']
    import json
    validation=json.loads(fixture['validation'].read_text())
    return {'work_id':'check','completion_revision':task['completion_revision'],
        'meaning_revision':validation['meaning_revision'],'covered_scope':validation['covered_scope'],
        'validation_path':'evidence/validation.json'}


def test_current_custody_facet_does_not_qualify_the_broad_proposition(tmp_path):
    from laplace.research import concepts as cs
    from test_concepts_surface import _change
    fixture=_engineering_fixture(tmp_path)
    _change(tmp_path,operation='edit_node',node=fixture['node'],
        value='Bodies are safely retained, all projections replay correctly, literature is complete, and history is constant cost.')
    binding=fixture['complete']();assert _adopt_engineering(tmp_path,fixture,binding)[0]==200
    read=cs.context('graph',fixture['node'],tmp_path)
    assert read['source_support']['engineering_support']['status']=='CURRENT'
    assert read['source_support']['qualification']=='OPEN'
    assert any(gap['kind']=='unsupported' for gap in read['source_support']['gaps'])


@pytest.mark.parametrize('extra',['graph/BACKGROUND.md','corpus_friction/graph.jsonl','corpus_friction/work_orders.jsonl'])
def test_actual_completion_cannot_consume_acknowledgement_inputs(tmp_path,extra):
    from laplace.research import concepts as cs
    fixture=_engineering_fixture(tmp_path);fixture['complete']()
    binding=_engineering_recomplete(tmp_path,fixture,extra=[extra])
    before=cs.state('graph',fixture['node'],root=tmp_path)['revision']
    code,result=_adopt_engineering(tmp_path,fixture,binding)
    assert code==422 and 'mutable acknowledgement' in result['error']
    assert cs.state('graph',fixture['node'],root=tmp_path)['revision']==before


def test_consumed_prerequisite_is_checked_but_containing_attachments_are_not(tmp_path):
    from laplace.work import project_work
    from laplace.research import concepts as cs
    from test_project_work import guarded_task,guarded_transition
    fixture=_engineering_fixture(tmp_path);fixture['complete']()
    guarded_task('graph',{'id':'container','title':'Containing goal','goal':'Keep scope separate','kind':'campaign'},tmp_path)
    guarded_transition('graph',{'id':'container','status':'done','evidence':['graph/BACKGROUND.md']},tmp_path)
    positive=_engineering_recomplete(tmp_path,fixture,parent='container')
    assert _adopt_engineering(tmp_path,fixture,positive)[0]==200
    assert project_work.observe_core('graph',['check'],tmp_path)['tasks']['check']['status']=='done'
    guarded_task('graph',{'id':'prerequisite','title':'Required evidence','goal':'Consumer guide in producer','kind':'engineering'},tmp_path)
    guarded_transition('graph',{'id':'prerequisite','status':'done','evidence':['graph/BACKGROUND.md']},tmp_path)
    negative=_engineering_recomplete(tmp_path,fixture,dependencies=['prerequisite'])
    before=cs.state('graph',fixture['node'],root=tmp_path)['revision']
    code,result=_adopt_engineering(tmp_path,fixture,negative)
    assert code==422 and 'mutable acknowledgement' in result['error']
    assert cs.state('graph',fixture['node'],root=tmp_path)['revision']==before


def test_validation_receipt_stays_pinned_but_cannot_reference_itself(tmp_path):
    import hashlib,json
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']()
    assert _adopt_engineering(tmp_path,fixture,binding)[0]==200
    value=json.loads(fixture['validation'].read_text())
    value['result_evidence']={'path':'evidence/validation.json','sha256':hashlib.sha256(fixture['validation'].read_bytes()).hexdigest()}
    fixture['validation'].write_text(json.dumps(value))
    binding=_engineering_recomplete(tmp_path,fixture)
    code,out=_adopt_engineering(tmp_path,fixture,binding)
    assert code==422 and 'own receipt' in out['error']


@pytest.mark.parametrize('change',['omit','roleless','source_only','same_resolved'])
def test_source_test_roles_are_required_distinct_and_never_inferred(tmp_path,change):
    import json
    fixture=_engineering_fixture(tmp_path);fixture['complete']()
    value=json.loads(fixture['validation'].read_text())
    if change=='omit':value['inputs']=value['inputs'][:1]
    elif change=='roleless':
        for row in value['inputs']:row.pop('role')
    elif change=='source_only':
        for row in value['inputs']:row['role']='source'
    else:
        value['inputs'][1]={**value['inputs'][0],'role':'test'}
    fixture['validation'].write_text(json.dumps(value))
    binding=_engineering_recomplete(tmp_path,fixture)
    code,out=_adopt_engineering(tmp_path,fixture,binding)
    assert code==422,out
    assert 'source/test' in out['error'] or 'source and test' in out['error']


def test_consumer_alias_and_sanitized_own_concept_ledger_are_resolved(tmp_path):
    import json
    from laplace.research import concepts as cs, corpus_ingest
    from laplace.work import project_work
    from test_project_work import guarded_task,guarded_transition
    fixture=_engineering_fixture(tmp_path);fixture['complete']()
    alias=tmp_path/'guide-alias.txt';alias.symlink_to(fixture['guide'])
    binding=_engineering_recomplete(tmp_path,fixture,extra=['guide-alias.txt'])
    assert _adopt_engineering(tmp_path,fixture,binding)[0]==422
    registry=tmp_path/'registry_projects.json';record=json.loads(registry.read_text())
    record['projects'].append({**record['projects'][0],'name':'graph.alias'});registry.write_text(json.dumps(record))
    project='graph.alias';node='res:alias';current=cs.state(project,root=tmp_path)
    code,out=cs.change({'project':project,'base_revision':current['revision'],'operation':'add_node',
        'node':node,'node_kind':'result','essence':'Alias-scoped custody observation.'},root=tmp_path);assert code==200,out
    current=cs.state(project,node,root=tmp_path)
    code,out=cs.change({'project':project,'base_revision':current['revision'],'operation':'set_source','node':node,
        'value':[{'path':'atlas/src/atlas/store.py','sha256':__import__('hashlib').sha256(fixture['source'].read_bytes()).hexdigest(),'line_start':1,'line_end':2}]},root=tmp_path);assert code==200,out
    value=json.loads(fixture['validation'].read_text());value.update(claim_id=node,
        meaning_revision=literature_support.meaning_revision(project,node,tmp_path))
    fixture['validation'].write_text(json.dumps(value))
    guarded_task(project,{'id':'alias-check','title':'Alias','goal':'Exact alias owner','kind':'engineering'},tmp_path)
    own=corpus_ingest._rewire_path(tmp_path,project).relative_to(tmp_path).as_posix()
    assert own=='corpus_friction/graph_alias.jsonl'
    guarded_transition(project,{'id':'alias-check','status':'done','evidence':[
        'atlas/src/atlas/store.py','tests/custody.py','evidence/custody-result.json','evidence/validation.json',own]},tmp_path)
    task=project_work.observe_core(project,['alias-check'],tmp_path)['tasks']['alias-check']
    binding={'work_id':'alias-check','completion_revision':task['completion_revision'],
        'meaning_revision':value['meaning_revision'],'covered_scope':value['covered_scope'],'validation_path':'evidence/validation.json'}
    before=cs.state(project,node,root=tmp_path)['revision']
    code,out=cs.change({'project':project,'base_revision':before,'operation':'set_projection','node':node,
        'value':{'engineering_support':[binding]}},root=tmp_path)
    assert code==422 and 'mutable acknowledgement' in out['error']
    assert cs.state(project,node,root=tmp_path)['revision']==before


def test_ordinary_claim_and_shared_source_observe_bytes_once_per_request(tmp_path,monkeypatch):
    import hashlib
    from laplace.research import concepts as cs, mathematical_records
    from laplace.projects import writing_sources
    from test_concepts_surface import _change
    fixture=_engineering_fixture(tmp_path)
    fixture['source'].write_text('def put(data):\n    return data\n'+('# realistic code body\n'*19000))
    _change(tmp_path,operation='set_source',node=fixture['node'],value=[{'path':'atlas/src/atlas/store.py',
        'sha256':hashlib.sha256(fixture['source'].read_bytes()).hexdigest(),'line_start':1,'line_end':2}])
    binding=fixture['complete']();assert _adopt_engineering(tmp_path,fixture,binding)[0]==200
    _change(tmp_path,operation='add_node',node='res:second',node_kind='result',essence='Second separately scoped observation.')
    locator={'path':'atlas/src/atlas/store.py','sha256':hashlib.sha256(fixture['source'].read_bytes()).hexdigest(),'line_start':1,'line_end':1}
    _change(tmp_path,operation='set_source',node='res:second',value=[locator])
    target=fixture['source'].resolve();opens=[];original=Path.open
    def observed_open(path,*args,**kwargs):
        if path.resolve()==target:opens.append(str(path))
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',observed_open)
    shared={};first=cs.context('graph',fixture['node'],tmp_path,read_context=shared)
    second=cs.context('graph','res:second',tmp_path,read_context=shared)
    assert first['source_support']['engineering_support']['status']=='CURRENT'
    assert second['source_locations'][0]['line_end']==1
    assert len(opens)==1
    facts=writing_sources.observation_state(shared)
    assert facts['files'][target]['sha256']==hashlib.sha256(fixture['source'].read_bytes()).hexdigest()
    assert facts['retained_bytes']<=writing_sources.SOURCE_OBSERVATION_RETAIN_LIMIT
    count=len(opens)
    wrong=mathematical_records.resolve_source('graph',{**locator,'sha256':'0'*64},tmp_path,read_context=shared)
    invalid=mathematical_records.resolve_source('graph',{**locator,'line_start':999999,'line_end':999999},tmp_path,read_context=shared)
    assert wrong['status']=='UNRESOLVED' and 'SHA-256 changed' in wrong['error']
    assert invalid['status']=='UNRESOLVED' and 'outside the file' in invalid['error']
    assert len(opens)==count
    opens.clear();ordinary=cs.context('graph',fixture['node'],tmp_path)
    assert ordinary['source_support']['engineering_support']['status']=='CURRENT' and len(opens)==1
    status,ctype,body=cs.handle('/concepts/state',{'project':['graph'],'node':[fixture['node']]},'GET',b'',tmp_path)
    assert status==200 and len(opens)==2


def test_native_exact_help_exposes_live_receipt_schema_and_only_its_action_digest_moves(tmp_path,monkeypatch):
    import copy,json
    from jsonschema import Draft202012Validator
    from laplace.research import engineering_support
    from laplace.native import tools as writing_tools, contracts as writing_contracts
    from laplace.writing import operating as writing_operating
    fixture=_engineering_fixture(tmp_path)
    # D2: the default help names the exact section read; the schema itself is served by that read only
    default=writing_tools.execute(tmp_path,'graph','work','help',{'operation':'concept_change'})['action']
    assert 'engineering_validation_schema' not in default
    section_read={'operation':'concept_change','section':'engineering_validation_schema'}
    assert default['sections']['read']=={'operation':'help','payload':{'operation':'concept_change','section':'<name>'}}
    assert default['sections']['chars']['engineering_validation_schema']>0
    help0=writing_tools.execute(tmp_path,'graph','work','help',section_read)
    schema=help0['action']['value']
    assert schema==engineering_support.validation_schema()
    fixture['complete']();receipt=json.loads(fixture['validation'].read_text())
    assert not list(Draft202012Validator(schema).iter_errors(receipt))
    invalid=copy.deepcopy(receipt);invalid['inputs'][1].pop('role')
    assert list(Draft202012Validator(schema).iter_errors(invalid))
    fixture['validation'].write_text(json.dumps(invalid));binding=_engineering_recomplete(tmp_path,fixture)
    assert _adopt_engineering(tmp_path,fixture,binding)[0]==422
    before=writing_contracts.exact_action_digests(['concept_change','source'])
    original=engineering_support.validation_schema
    def updated_schema():
        value=original();value['properties']['checks']['maxItems']=63;return value
    monkeypatch.setattr(engineering_support,'validation_schema',updated_schema)
    help1=writing_tools.execute(tmp_path,'graph','work','help',section_read)
    after=writing_contracts.exact_action_digests(['concept_change','source'])
    assert help1['action']['value']==updated_schema()
    assert after['concept_change']!=before['concept_change'] and after['source']==before['source']
    brief=writing_operating.instruction_members(writing_operating.build('graph','work',tmp_path))
    assert 'engineering_validation_schema' not in brief


def test_consulted_engineering_digest_ignores_only_measured_io_order(tmp_path):
    import copy
    from laplace.research import concepts as concepts_surface
    from laplace.work import project_work
    from laplace.writing import reads
    from test_project_work import guarded_task,guarded_transition
    fixture=_engineering_fixture(tmp_path);binding=fixture['complete']();assert _adopt_engineering(tmp_path,fixture,binding)[0]==200
    extra=tmp_path/'evidence/unrelated.json';extra.write_text('{"other":1}')
    guarded_task('graph',{'id':'unrelated','title':'Other','goal':'Not consumed','kind':'engineering'},tmp_path)
    guarded_transition('graph',{'id':'unrelated','status':'done','evidence':['evidence/unrelated.json']},tmp_path)
    first=concepts_surface.context('graph',fixture['node'],tmp_path)
    shared={};project_work.observe_core('graph',['unrelated'],tmp_path,read_context=shared)
    second=concepts_surface.context('graph',fixture['node'],tmp_path,read_context=shared)
    assert first['source_support']['engineering_support']['read_metrics']!=second['source_support']['engineering_support']['read_metrics']
    assert reads.read_output_digest('concept',first)==reads.read_output_digest('concept',second)
    for operation in ['concept','project_guidance','read_artifact']:
        original={'engineering_support':first['source_support']['engineering_support']} if operation!='concept' else first
        changed=copy.deepcopy(original)
        support=(changed.get('source_support') or changed)['engineering_support']
        support['bindings'][0]['current_completion_revision']='sha256:'+'f'*64
        assert reads.read_output_digest(operation,original)!=reads.read_output_digest(operation,changed)
        support['bindings'][0]['status']='STALE';support['status']='REVIEW_REQUIRED'
        assert reads.read_output_digest(operation,original)!=reads.read_output_digest(operation,changed)
