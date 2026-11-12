"""Declaration admission precedes guard observations, baseline work and effects."""
import json
import subprocess
import sys

import pytest
from laplace.core import grammar as g
from laplace.native import declarations as d, tools as t, verbs as v
from laplace.writing import operations
from laplace.manuscript import proposal_preflight
from laplace.writing import turn_reads
from laplace.representation import writing_bodies
from laplace.writing import records as writing_records
from laplace.writing import session_reads
from test_tool_refusal_recovery import turn, failures


def semantic(operation,payload,by=''):
    route=v.routes_for(operation)[0]
    return {'verb':route.verb,'concept':route.concept,'target':v.target_for('p',route.concept,payload),
            'expected':[],'payload':payload,'by':by}


def test_named_and_semantic_bad_shape_stop_before_classify_baseline_or_owner(tmp_path,monkeypatch):
    turn(tmp_path)
    def forbidden(*args,**kwargs):raise AssertionError('shape performed owner/source work')
    for module,name in ((v,'classify'),(v,'account'),(turn_reads,'capture_turn_read_baselines'),(t,'_execute')):
        monkeypatch.setattr(module,name,forbidden)
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    with pytest.raises(d.PayloadAdmissionError) as caught:
        t.call(tmp_path,'p','review',{'operation':'run_status','payload':{'run_id':'wrong'}},turn_id='WT-r')
    answer=t.tool_failure(tmp_path,'p','review','run_status',{'run_id':'wrong'},caught.value,'WT-r')
    assert answer['refused']['kind']=='shape'
    value=t.call(tmp_path,'p','review',semantic('run_status',{'run_id':'wrong'},by='requested reviewer'),'WT-r')
    assert value['refused']['kind']=='shape'
    assert len(failures(tmp_path))==2 and failures(tmp_path)[1]['requested_by']['text']=='requested reviewer'
    assert not session_reads._records(tmp_path)['turns']['WT-r'].get('tool_reads')


def test_actual_mcp_named_refusal_vs_valid_unknown_target(tmp_path):
    turn(tmp_path)
    requests=[{'jsonrpc':'2.0','id':i,'method':'tools/call','params':{
        'name':'laplace_project','arguments':{'operation':'run_status','payload':payload}}}
        for i,payload in enumerate(({'run_id':'wrong'},{'id':'genuinely-unknown'}),1)]
    run=subprocess.run([sys.executable,'-m','laplace.native.tools','--root',str(tmp_path),
        '--project','p','--mode','review','--turn-id','WT-r'],input=''.join(json.dumps(row)+'\n' for row in requests),text=True,capture_output=True,check=True)
    returned=[json.loads(json.loads(line)['result']['content'][0]['text']) for line in run.stdout.splitlines()]
    assert returned[0]['refused']['kind']=='shape' and 'Payload rejected' in returned[0]['error']
    assert 'unknown run' in returned[1]['error']
    assert len(failures(tmp_path))==2


def test_complete_admission_is_once_before_classify_and_baseline(tmp_path,monkeypatch):
    events=[];real=d.validate_owner_payload
    monkeypatch.setattr(d,'validate_owner_payload',lambda *args,**kwargs:(events.append('admit'),real(*args,**kwargs))[1])
    monkeypatch.setattr(v,'classify',lambda *args,**kwargs:(events.append('classify'),v.Classified(None,None,None,False))[1])
    monkeypatch.setattr(operations,'_execute',lambda *args,**kwargs:(events.append('owner'),{'ok':False,'scientific_result':'FAIL'})[1])
    monkeypatch.setattr(v,'bank_every_path',lambda:False)
    result=t.call(tmp_path,'p','review',semantic('run_status',{'id':'x'}))
    assert events==['admit','classify','owner'] and result['owner_response']['scientific_result']=='FAIL'


def test_tagged_and_legacy_actual_source_anchor_contract():
    anchor=proposal_preflight.source_anchor('One premise.\n',1,1)
    edit={'file':'main.tex','line_start':1,'line_end':1,'before':'One premise.','after':'New','source_anchor':anchor}
    for version in (None,*proposal_preflight.SOURCE_ANCHOR_SCHEMAS):
        value=dict(anchor)
        if version is None:value.pop('schema_version')
        else:value['schema_version']=version
        d.validate_owner_payload('propose_revision',{'edits':[{**edit,'source_anchor':value}]},project='p')
    with pytest.raises(d.PayloadAdmissionError):
        d.validate_owner_payload('propose_revision',{'edits':[{**edit,'source_anchor':{**anchor,'schema_version':'laplace.source-anchor/99'}}]},project='p')


def test_all_emitted_named_examples_and_finite_variants_share_admission(monkeypatch):
    monkeypatch.setattr(d,'expected_tokens',lambda *args,**kwargs:[])
    checked=[]
    for operation in d.DECLARATIONS:
        for name in (list(d.variants(operation)) or [None]):
            example=d.generated_example(operation,variant=name)
            try:d.validate_owner_payload(operation,example,project='p')
            except ValueError as error:checked.append((operation,name,str(error)))
    assert not checked,checked


def test_supplied_wrong_types_unknown_fields_and_history_conditions():
    for operation,payload in [('run_status',{'id':3}),('run_status',{'id':'x','unknown':1}),
        ('source',{'line_start':True}),('author_history',{'view':'activity','turn_id':'WT-x'})]:
        with pytest.raises(d.PayloadAdmissionError):d.validate_owner_payload(operation,payload,project='p')
    for payload in ({'view':'telemetry','projection':'trace','scope':'turn','turn_id':'WT-x'},
                    {'view':'record','id':'activity:journal:TOOLFAIL-x'}):
        d.validate_owner_payload('author_history',payload,project='p')


def test_outer_requested_by_never_injected_into_owner_and_receipts_remain_bounded(tmp_path,monkeypatch):
    turn(tmp_path);seen=[]
    monkeypatch.setattr(operations,'_execute',lambda root,project,mode,operation,payload,**kwargs:(seen.append(dict(payload)),{'known':'read'})[1])
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    requested='requested author '*1000
    result=t.call(tmp_path,'p','review',semantic('run_status',{'id':'x'},requested),'WT-r')
    assert seen==[{'id':'x'}]
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    row=next(row for row in rows if row.get('record')=='writing-tool-read')
    assert row['requested_by']['truncated'] and len(row['requested_by']['text'])==240
    assert 'by' not in row['payload'] and requested not in json.dumps(row)
    assert result['outcome']=='read'
    assert requested not in json.dumps(result)
    assert result['banked_row']['requested_by']==row['requested_by']
    assert result['owner_response']['read_receipt']['requested_by']==row['requested_by']


def test_literal_owner_by_codec_roundtrip_conflict_and_owner_admission():
    route,req=v.from_owner_call('project_metadata_change',{'title':'Title','expected_revision':'0'*64,'by':'owner label'},project='p')
    assert req.by=='' and req.payload['owner_by']=='owner label'
    operation,payload=v.to_owner_call(req,route=route,materialize=False)
    assert payload['by']=='owner label'
    d.validate_owner_payload(operation,payload,project='p')
    with pytest.raises(d.PayloadAdmissionError,match='conflicts'):
        d.validate_request_payload(g.Request(req.verb,req.concept,req.target,req.expected,req.payload,'different'),route,project='p')
    with pytest.raises(ValueError):g.to_owner_payload({'by':'one','owner_by':'two'})
    with pytest.raises(d.PayloadAdmissionError):d.validate_owner_payload('run_status',{'id':'x','by':'ignored before'},project='p')


def test_phase1_does_not_materialize_bad_carriers_tokens_or_nested_versions(tmp_path,monkeypatch):
    turn(tmp_path)
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    def forbidden(*args,**kwargs):raise AssertionError('invalid shape observed source')
    monkeypatch.setattr(v,'_span_bytes',forbidden);monkeypatch.setattr(v,'_counter_for',forbidden)
    monkeypatch.setattr(v,'account',forbidden);monkeypatch.setattr(v,'classify',forbidden)
    route=next(r for r in v.routes_for('store_artifact') if r.verb=='change')
    base={'verb':route.verb,'concept':route.concept,'target':'p::a.txt','expected':[],
          'payload':{'path':'a.txt',v.CARRIERS['text']:42,'content':'new','reason':'change'},'by':'reviewer'}
    result=t.call(tmp_path,'p','review',base,'WT-r')
    assert result['refused']['kind']=='shape'
    bad={**base,'expected':['not-a-token']}
    with pytest.raises(d.PayloadAdmissionError) as caught:t.call(tmp_path,'p','review',bad,'WT-r')
    answer=t.tool_failure(tmp_path,'p','review',None,bad['payload'],caught.value,'WT-r')
    assert answer['refused']['kind']=='shape' and len(failures(tmp_path))==2
    saved=writing_bodies.resolve_fields(failures(tmp_path)[-1],tmp_path,strict=True)
    assert saved['payload']['expected']==['not-a-token'] and saved['requested_by']['text']=='reviewer'


def test_direct_corpus_and_proposal_shape_refuse_before_their_owners(tmp_path,monkeypatch):
    from laplace.work import technical_friction
    from laplace.manuscript import proposal_navigation
    turn(tmp_path)
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    def forbidden(*args,**kwargs):raise AssertionError('direct owner reached before admission')
    monkeypatch.setattr(technical_friction,'report',forbidden)
    monkeypatch.setattr(proposal_navigation,'read',forbidden)
    for fields in ({'verb':'record','concept':'technical-friction@project','target':'p','expected':[],
                    'payload':{'owning_layer':'fixture','value':'bad','chain':['x']*9},'by':'reviewer'},
                   {'verb':'read','concept':'proposal@paragraph','target':'p','expected':[],
                    'payload':{'unexpected':True},'by':'reviewer'}):
        result=t.call(tmp_path,'p','review',fields,'WT-r')
        assert result['refused']['kind']=='shape'
    assert len(failures(tmp_path))==2


def test_phase1_guard_materialization_is_deferred_only_for_valid_exact_carrier():
    route=next(r for r in v.routes_for('store_artifact') if r.verb=='change')
    token=str(g.mint('artifact','p::a.txt','0'*64))
    req=g.Request(route.verb,route.concept,'p::a.txt',(token,),{'path':'a.txt','content':'new','reason':'change'})
    d.validate_request_payload(req,route,project='p')
    # Complete validation cannot invent missing source text before translation.
    with pytest.raises(d.PayloadAdmissionError):d.validate_owner_payload('store_artifact',req.payload,project='p')
    wrong=g.Request(route.verb,route.concept,'p::a.txt',(str(g.mint('plan','p','0'*64)),),req.payload)
    with pytest.raises(d.PayloadAdmissionError,match='home not declared'):
        d.validate_request_payload(wrong,route,project='p')


def test_actual_metadata_actor_role_and_guard_stay_owner_bound(tmp_path,monkeypatch):
    turn(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-work','session_id':'WS-r','project':'p','mode':'work'})
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    current=t.execute(tmp_path,'p','work','project_metadata',{})
    _route,req=v.from_owner_call('project_metadata_change',{'title':'New title','expected_revision':current['revision']},project='p',root=tmp_path)
    fields={**vars(req),'expected':list(req.expected),'by':'caller requested label'}
    result=t.call(tmp_path,'p','work',fields,'WT-work')
    assert result['outcome']=='applied'
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    intent=next(row for row in rows if row.get('record')=='project-metadata-change-intent')
    assert intent['by']=='eigen:session'
    action=next(row for row in rows if row.get('record')=='writing-tool-action')
    assert action['requested_by']['text']=='caller requested label' and 'by' not in action['payload']
    before=(tmp_path/'registry_projects.json').read_bytes()
    stale=t.call(tmp_path,'p','work',{**fields,'by':'another label'},'WT-work')
    assert stale['ok'] is False and (tmp_path/'registry_projects.json').read_bytes()==before
    fresh=t.execute(tmp_path,'p','work','project_metadata',{})
    _route,req=v.from_owner_call('project_metadata_change',{'title':'Review cannot edit','expected_revision':fresh['revision']},project='p',root=tmp_path)
    refused=t.call(tmp_path,'p','review',{**vars(req),'expected':list(req.expected),'by':'pretend author'},'WT-r')
    assert refused['ok'] is False and (tmp_path/'registry_projects.json').read_bytes()==before


def test_literal_by_diagnostic_is_current_declaration_projection():
    assert d.by_at('project_metadata_change')[0]=='overwritten'
    assert d.by_at('writing_style_change')[0]=='overwritten'
    assert d.by_at('run_status')[0]=='refused'
    assert d.by_at('note')[0]=='refused'  # Outer attribution remains accepted separately.
    assert d.by_at('app_settings')[0]=='declared'


def test_shared_research_owner_alternatives_preserve_typed_legacy_inputs():
    record={'kind':'result','id':'result:x','summary':'Declared result'}
    for value in (record,{'record':record}):d.validate_owner_payload('research_record',value,project='p')
    with pytest.raises(d.PayloadAdmissionError):d.validate_owner_payload('research_record',{'record':record,**record},project='p')
    producer={'id':'p','executable':'code.py','modes':['smoke'],'allowed_args':{}}
    for value in (producer,{'producer':producer}):d.validate_owner_payload('research_producer',value,project='p')
    with pytest.raises(d.PayloadAdmissionError):d.validate_owner_payload('research_producer',{'producer':producer,**producer},project='p')
    with pytest.raises(d.PayloadAdmissionError):d.validate_owner_payload('research_producer',{**producer,'dependencies':'inferred'},project='p')


def test_literal_task_origin_label_does_not_override_review_or_permission(tmp_path,monkeypatch):
    from laplace.work import project_work
    turn(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-work','session_id':'WS-r','project':'p','mode':'work'})
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    first=t.call(tmp_path,'p','work',{'operation':'task','payload':{
        'id':'work-literal','title':'Task','goal':'Measure','by':'origin label'}},'WT-work')
    assert first['origin']=='origin label'
    reviewed=t.call(tmp_path,'p','review',{'operation':'task','payload':{
        'id':'review-literal','title':'Review task','goal':'Inspect','by':'pretend author'}},'WT-r')
    assert reviewed['origin']=='eigen:review'
    with pytest.raises(d.PayloadAdmissionError):
        t.call(tmp_path,'p','review',{'operation':'task_status','payload':{
            'id':'review-literal','status':'verified','by':'pretend author'}},'WT-r')
    assert project_work._tasks('p',tmp_path)['review-literal']['status']!='verified'


def test_phase1_cannot_overwrite_a_supplied_selector_or_wrong_parent_type():
    route=next(r for r in v.routes_for('structure_change') if ('op.kind','set-serves') in r.lift)
    for payload in ({'operation':'spine','op':{}},{'op':7},{'op':{'kind':None}},{'op':{'kind':'remove-node'}}):
        req=g.Request(route.verb,route.concept,'p',(),payload)
        with pytest.raises(d.PayloadAdmissionError,match='selector'):
            d.validate_request_payload(req,route,project='p')


def test_actual_selected_result_creation_and_renewal_guard_parity(tmp_path):
    from test_writing_consumers import _import
    manuscript,_=_import(tmp_path)
    record={'kind':'result','id':'result:guard','summary':'Fixture fact only'}
    path=manuscript/'research_records.json'
    wrong=str(g.mint('result','fixture::result:guard','0'*64))
    for guard in ({'expected':[wrong]},{'expected_revision':'0'*64}):
        with pytest.raises(operations.OwnerError,match='no existing selected record'):
            t.execute(tmp_path,'fixture','work','research_record',{'record':record,**guard})
        assert not path.exists()
    created=t.execute(tmp_path,'fixture','work','research_record',{'record':record,'expected':[]})
    value=created['record']
    token=str(g.mint('result','fixture::result:guard',value['revision']))
    renewed=t.execute(tmp_path,'fixture','work','research_record',{'record':{**record,'summary':'Renewed fixture'},'expected':[token]})
    assert renewed['record']['summary']=='Renewed fixture'
    before=path.read_bytes()
    with pytest.raises(operations.OwnerError):
        t.execute(tmp_path,'fixture','work','research_record',{'record':record,'expected':[token]})
    assert path.read_bytes()==before


def test_current_owner_forced_actor_diagnostics_are_checked_against_gateway():
    import ast,inspect,textwrap
    tree=ast.parse(textwrap.dedent(inspect.getsource(operations._execute)))
    groups=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.If) or not isinstance(node.test,ast.Compare):continue
        test=node.test
        if not isinstance(test.left,ast.Name) or test.left.id!='operation':continue
        if any(isinstance(item,ast.Assign) and isinstance(item.value,ast.Constant) and item.value.value=='eigen:session' for item in node.body):
            groups.extend(ast.literal_eval(test.comparators[0]))
    assert set(groups)=={'concept_change','logical_plan_change','writing_style_change','writing_style_profile_change'}
    assert all(d.by_at(name)[0]=='overwritten' for name in groups)


def test_unencodable_new_attribution_fails_before_effect_and_keeps_refusal(tmp_path,monkeypatch):
    turn(tmp_path)
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    monkeypatch.setattr(operations,'_execute',lambda *args,**kwargs:pytest.fail('attribution validation followed owner effect'))
    result=t.call(tmp_path,'p','review',semantic('run_status',{'id':'x'},'\ud800'),'WT-r')
    assert result['refused']['kind']=='shape' and 'UTF-8' in result['error']
    assert result['failure_receipt']['row_id'] is None and 'unavailable' in result['failure_receipt']['note']


def test_required_canonical_guard_coverage_order_and_supplied_legacy_type():
    source=str(g.mint('source-file','p::main.tex','1'*64))
    plan=str(g.mint('plan','p','2'*64))
    # convert's non-identity fields (title, the exact replacement paragraph) are supplied so admission reaches coverage
    payload={'operation':'convert','source_file':'main.tex','line_start':1,'kind':'section','title':'Converted',
             'replacement':{'line_start':1,'line_end':1,'before':'A whole prose paragraph.'},'expected':[source,plan]}
    before=json.dumps(payload)
    d.validate_owner_payload('section_change',payload,project='p')
    assert json.dumps(payload)==before and payload['expected']==[source,plan]
    # missing REQUIRED canonical coverage is refused at admission: the source-file home is required on every
    # section_change route; the plan home is declared optional there (writing_verbs guards ... True) because the
    # owner requires it only when a reader plan exists (manuscript_structure._check_plan_guard gates it then)
    with pytest.raises(d.PayloadAdmissionError,match='coverage'):
        d.validate_owner_payload('section_change',{**payload,'expected':[plan]},project='p')
    assert [(name,optional) for name,_homes,_form,optional in v.routes_for('section_change')[0].guards]==[
        ('expected_plan_revision',True),('expected_source_digest',False)]
    d.validate_owner_payload('section_change',{**payload,'expected':[source]},project='p')   # plan optional at admission
    with pytest.raises(d.PayloadAdmissionError):
        d.validate_owner_payload('section_change',{**payload,'expected_source_digest':None},project='p')


def test_large_real_artifact_attempt_uses_existing_payload_custody_once(tmp_path,monkeypatch):
    turn(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-work','session_id':'WS-r','project':'p','mode':'work'})
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    content='α'*12000
    _route,req=v.from_owner_call('store_artifact',{'path':'notes/large.md','before':None,'content':content,'reason':'Owned fixture'},project='p')
    result=t.call(tmp_path,'p','work',{**vars(req),'expected':list(req.expected),'by':'requested fixture label'},'WT-work')
    assert result['outcome']=='applied'
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    actions=[row for row in rows if row.get('record')=='writing-tool-action']
    assert len(actions)==1
    action=actions[0]
    assert isinstance(action['payload'],dict) and 'content_handle' in action['payload']
    assert content not in json.dumps(action,ensure_ascii=False)
    resolved=writing_bodies.resolve_fields(action,tmp_path,strict=True)
    assert resolved['payload']['content']==content and 'request' not in resolved
    assert action['requested_by']['text']=='requested fixture label'
    assert 'by' not in resolved['payload']
    assert (tmp_path/'proj/notes/large.md').read_text()==content


def test_valid_counter_materializes_once_and_stale_comparison_keeps_exact_cure(tmp_path,monkeypatch):
    from test_writing_consumers import _import
    from laplace.pipeline import authoring
    _import(tmp_path)
    path,_=authoring._state_path('fixture',tmp_path)
    path.parent.mkdir(parents=True,exist_ok=True)
    state=authoring._blank('fixture');path.write_text(json.dumps(state))
    token=str(g.identity(g.Home('authoring-state','fixture'),project='fixture',root=tmp_path))
    route=v.routes_for('argument')[0]
    req=g.Request(route.verb,route.concept,v.target_for('fixture',route.concept,{}),(token,),{'argument':'A guarded fixture argument'})
    real=v._counter_for;calls=[]
    monkeypatch.setattr(v,'_counter_for',lambda *args:(calls.append(1),real(*args))[1])
    d.validate_request_payload(req,route,project='fixture')
    assert calls==[]
    result=t.request(tmp_path,'fixture','work',req)
    assert result['outcome']=='applied' and calls==[1]
    assert authoring.load('fixture',tmp_path)['argument']=='A guarded fixture argument'
    before=path.read_bytes()
    monkeypatch.setattr(v,'classify',lambda *args,**kwargs:pytest.fail('stale bridge reclassified'))
    monkeypatch.setattr(v,'account',lambda *args,**kwargs:pytest.fail('stale bridge reread for cure'))
    refused=t.request(tmp_path,'fixture','work',req)
    assert refused['refused']['kind']=='identity-stale' and calls==[1,1]
    assert refused['refused']['needed']['expected']!=[token] and path.read_bytes()==before


def test_semantic_help_name_and_context_failures_keep_static_existing_cure(tmp_path,monkeypatch):
    turn(tmp_path)
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    for name in ('account','classify','_counter_for','_span_bytes'):
        monkeypatch.setattr(v,name,lambda *args,**kwargs:pytest.fail('shape cure observed source'))
    route=v.routes_for('help')[0]
    for payload in ({'operation':'not-deployed'}, {'operation':'run_status','context':{'file':'wrong axis'}}):
        req=g.Request(route.verb,route.concept,'p',(),payload)
        result=t.request(tmp_path,'p','review',req,'WT-r')
        assert result['refused']['kind']=='shape'
        if payload['operation']=='run_status':assert result['help']=={'operation':'help','payload':{'operation':'run_status'}}
    assert len(failures(tmp_path))==2


def test_named_nonobject_payload_refuses_without_coercion_and_exact_receipt_keeps_it(tmp_path,monkeypatch):
    turn(tmp_path)
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    monkeypatch.setattr(operations,'_execute',lambda *args,**kwargs:pytest.fail('malformed envelope executed'))
    original='{"id":"this is still text, not an object"}'
    with pytest.raises(d.PayloadAdmissionError) as caught:
        t.call(tmp_path,'p','review',{'operation':'run_status','payload':original},'WT-r')
    answer=t.tool_failure(tmp_path,'p','review','run_status',original,caught.value,'WT-r')
    assert answer['refused']['kind']=='shape'
    saved=writing_bodies.resolve_fields(failures(tmp_path)[0],tmp_path,strict=True)
    assert saved['payload']==original and isinstance(saved['payload'],str)


@pytest.mark.parametrize('verb,payload,kind',[
    ('read',{},'writing-tool-read'),
    ('record',{'owning_layer':'fixture','value':'Exact current test observation','chain':['owned fixture']},'writing-tool-action')])
def test_actual_direct_corpus_success_attribution_return_matches_durable_receipt(tmp_path,monkeypatch,verb,payload,kind):
    turn(tmp_path)
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    fields={'verb':verb,'concept':'technical-friction@project','target':'p',
            'expected':[],'payload':payload,'by':'requested reviewer'}
    result=t.call(tmp_path,'p','review',fields,'WT-r')
    returned=result['owner_response']['call_receipt']
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    durable=next(row for row in rows if row.get('id')==returned['id'])
    assert durable['record']==kind and durable['by']=='eigen:session'
    assert durable['requested_by']==returned['requested_by']==result['banked_row']['requested_by']
    assert durable['requested_by']['text']=='requested reviewer'
    assert durable['project']==returned['project']=='p' and durable['turn_id']==returned['turn_id']=='WT-r'
    assert 'by' not in durable['payload']


def test_an_empty_canonical_guard_beside_valid_legacy_guards_never_reaches_owner_work(tmp_path,monkeypatch):
    """D1 (2026-10-15): `expected: []` (or null) beside a valid legacy guard is a malformed guard. It is refused at shared
    admission before classification, read baselines or the owner, and nothing is written; legacy alone still reaches
    the owner, so the refusal is the malformed canonical presence and not the legacy guard."""
    turn(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-work','session_id':'WS-r','project':'p','mode':'work'})
    owner=[]
    def forbidden(*args,**kwargs):raise AssertionError('a malformed guard performed owner/source work')
    for module,name in ((v,'classify'),(v,'account'),(turn_reads,'capture_turn_read_baselines')):
        monkeypatch.setattr(module,name,forbidden)
    monkeypatch.setattr(operations,'_execute',lambda *args,**kwargs:owner.append(args) or {'ok':True})
    monkeypatch.setattr(t,'_project_updates',lambda root,project,tid,result,fields:result)
    files=lambda:sorted((str(p.relative_to(tmp_path)),p.stat().st_size) for p in tmp_path.rglob('*') if p.is_file() and 'talk.jsonl' not in p.name)
    before=files()
    for malformed in ([],None):
        payload={'title':'New title','expected':malformed,'expected_revision':'r'*64}
        with pytest.raises(d.PayloadAdmissionError):
            d.validate_owner_payload('project_metadata_change',payload,project='p')
        with pytest.raises(d.PayloadAdmissionError):
            t.call(tmp_path,'p','work',{'operation':'project_metadata_change','payload':payload},turn_id='WT-work')
    assert owner==[] and files()==before, 'no owner call and no file written'
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    assert not [row for row in rows if row.get('record')=='writing-tool-action'], 'no action recorded'
    # the same request with legacy guards alone is admitted (the refusal was the malformed canonical presence)
    d.validate_owner_payload('project_metadata_change',{'title':'New title','expected_revision':'r'*64},project='p')


@pytest.mark.parametrize('operation',['work_review','development_source','work_delivery'])
def test_an_owner_admitting_its_own_contract_is_the_native_doors_admission(operation, tmp_path):
    """The Work owners admit through core.admission over their own contract(), not back through this table. That is the
    same admission exactly while the facts it rests on hold: the composed schema is the owner's contract, the
    declaration takes caller expected, and no route of the operation accepts canonical expected tokens."""
    from laplace.work import project_work_review
    from laplace.core import admission
    from laplace.work import development_source, work_delivery
    owner = {'work_review': project_work_review, 'development_source': development_source, 'work_delivery': work_delivery}[operation]
    assert d.owner_input_schema(operation) == owner.contract()
    assert d.DECLARATIONS[operation].caller_expected
    assert not any(v.owner_accepts_expected(route) for route in v.routes_for(operation))
    for payload in (None, {}, {'project': 'other'}, {'by': 'me'}, {'expected': ['work:x']}, {'action': 'nope', 'phase': 'nope'}):
        with pytest.raises(d.PayloadAdmissionError) as native:
            d.validate_owner_payload(operation, payload, project='p')
        with pytest.raises(admission.AdmissionRefused) as core:
            admission.admit_owner_payload(operation, payload, owner.contract(), project='p')
        assert str(core.value) == str(native.value) and core.value.operation == native.value.operation


def test_the_operation_tables_field_check_reads_the_same_contract_the_native_door_composes():
    """writing.operations checks unknown/missing fields of these operations against writing_schemas.SCHEMAS directly;
    that is the native door's composed contract exactly while no variant or guard alternative is composed onto them."""
    from laplace.native.contracts import CONTRACTS
    from laplace.writing.schemas import SCHEMAS
    for operation in ('storage','storage_prune','literature_scope','literature_lookup','literature_discover','literature_import',
                      'literature_bind','literature_uses','reference_source','reference_text','reference_fetch','proposal_supersede'):
        assert CONTRACTS[operation]['input'] == SCHEMAS[operation] == d.owner_input_schema(operation), operation
