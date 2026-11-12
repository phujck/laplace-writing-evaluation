"""Actual public owner capability and no-admission request custody; no inference."""
import copy,json
from pathlib import Path
import pytest
from laplace.pipeline import workflow_definitions as D,workflow_operations as F
from laplace.work import owner_discovery as O
from laplace.core.identity import canonical_digest

@pytest.fixture(autouse=True)
def passive_catalogue(monkeypatch):
    from laplace.writing import provider_catalogue
    monkeypatch.setattr(provider_catalogue,'provider_catalogue',lambda *a,**k:{'schema_version':'laplace.provider-catalogue/1','observed_at':99999999999,'providers':[{'id':'codex','available':False,'models':[]}]})

def body():
    return {'schema_version':D.SCHEMA,'title':'Public finite operation','description':'No inference.', 'settings':{},
        'steps':[{'id':'write','title':'Write','assignment':{'role':'builder','instructions':'Produce a public report.','settings':{}}},
                 {'id':'review','title':'Review','assignment':{'role':'adversary','instructions':'Judge the exact report independently.','settings':{}}}],
        'edges':[{'id':'write-review','from':'write','to':'review','kind':'control'}]}

def original():return {'request_id':'public-save-original','expected_revision':None,'definition':body()}
def withdrawal(value,operation='save'):
    return {'action':'withdraw','operation':operation,'request_id':value['request_id'],'intent_digest':canonical_digest(value),'original_request':copy.deepcopy(value)}

def test_owner_contract_keeps_all_facets_and_exact_compact_variants():
    from jsonschema import Draft202012Validator
    contract=F.read_contract();Draft202012Validator.check_schema(contract)
    assert {v['properties']['facet']['const'] for v in contract['oneOf']}==set(F.FACETS)
    for facet in F.FACETS:
        selected=F.read_contract(facet)
        assert selected['properties']['facet']=={'const':facet} and selected in contract['oneOf']

def test_pure_preview_scope_context_and_explicit_project_creation(tmp_path):
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'book','project_dir':'book','tex_root':'book','form':'book'}]}))
    scope=O.owned_workspace('sdk');draft=body()
    result=D.read(tmp_path,scope,{'facet':'execution-preview','definition':draft,'scope':{'kind':'project','namespace':'book'}})
    assert result['reference'] is None and result['execution_permitted'] is False
    assert result['support']=='SUPPORTED_CONFIGURATION' and result['definition_digest']==canonical_digest(draft)
    assert not (tmp_path/'contract/dispatches.jsonl').exists()
    assert result['declarations']['context']==F.context_contract()
    choices=D.read(tmp_path,scope,{'facet':'creation-choices'})
    assert [x['scope'] for x in choices['items']]==[{'kind':'owned-workspace'},{'kind':'project','namespace':'book'}]
    project=D.read(tmp_path,O.project_scope('book','native'),{'facet':'creation-choices'})
    assert len(project['items'])==1 and project['items'][0]['scope']['namespace']=='book'
    with pytest.raises(D.Refused,match='NOT_IN_SCOPE'):
        D.read(tmp_path,O.project_scope('foreign','native'),{'facet':'execution-preview','definition':draft,'scope':{'kind':'project','namespace':'book'}})
    draft['steps'][0]['assignment']['context']=[{'kind':'ancestor-instructions','step_id':'review'}]
    with pytest.raises(D.Refused,match='CONTEXT_NOT_AN_ANCESTOR'):D.validate(draft)

def test_withdrawal_wins_and_exact_replay_never_saves(tmp_path):
    scope=O.owned_workspace('sdk');wire=original();result=D.withdraw(tmp_path,scope,withdrawal(wire))
    assert result['status']==result['effect']=='NOT_ADMITTED' and result['terminal']
    assert D.withdraw(tmp_path,scope,withdrawal(wire))['replayed']
    assert D.save(tmp_path,scope,wire)['status']=='NOT_ADMITTED'
    assert D.read(tmp_path,scope,{'facet':'request','request_id':wire['request_id']})['reason']=='WITHDRAWN'
    assert D.read(tmp_path,scope,{})['total']==0
    changed={**wire,'definition':{**body(),'title':'Changed intent'}}
    with pytest.raises(D.Refused,match='REQUEST_CONFLICT'):D.save(tmp_path,scope,changed)
    assert len((tmp_path/'contract/dispatches.jsonl').read_text().splitlines())==1

def test_recorded_save_wins_without_undo_and_other_intent_refuses(tmp_path):
    scope=O.owned_workspace('sdk');wire=original();saved=D.save(tmp_path,scope,wire)
    result=D.withdraw(tmp_path,scope,withdrawal(wire))
    assert result['status']=='RECORDED' and result['withdrawal']=='ALREADY_RECORDED_NO_UNDO'
    assert result['version']==saved['version'] and D.read(tmp_path,scope,{})['total']==1
    changed={**wire,'definition':{**body(),'title':'Another intent'}}
    with pytest.raises(D.Refused,match='REQUEST_CONFLICT'):D.withdraw(tmp_path,scope,withdrawal(changed))

def test_withdrawal_bank_unknown_remains_recoverable_and_foreign_refuses(tmp_path,monkeypatch):
    scope=O.owned_workspace('sdk');wire=original();bank=D.W._bank
    def lost_ack(*args,**kwargs):bank(*args,**kwargs);raise OSError('controlled lost decision acknowledgement')
    monkeypatch.setattr(D.W,'_bank',lost_ack)
    result=D.withdraw(tmp_path,scope,withdrawal(wire));assert result['status']=='UNKNOWN' and not result['terminal']
    monkeypatch.setattr(D.W,'_bank',bank)
    assert D.read(tmp_path,scope,{'facet':'request','request_id':wire['request_id']})['status']=='NOT_ADMITTED'
    assert D.save(tmp_path,scope,wire)['status']=='NOT_ADMITTED'
    foreign={**original(),'scope':{'kind':'project','namespace':'book'}}
    with pytest.raises(D.Refused,match='NOT_IN_SCOPE'):D.withdraw(tmp_path,O.project_scope('foreign','sdk'),withdrawal(foreign))

def test_unadmitted_legacy_preparation_can_be_withdrawn_without_run(tmp_path):
    scope=O.owned_workspace('sdk');saved=D.save(tmp_path,scope,original())
    wire={'request_id':'public-preparation-original','reference':saved['reference'],'selected_steps':['write','review'],
        'profile':D.W.SPEC_SCHEMA,'node':'public.txt','goal':'No run','write_paths':[],'timeout':10}
    (tmp_path/'public.txt').write_text('Public selected input.')
    assert D.withdraw(tmp_path,scope,withdrawal(wire,'prepare'))['status']=='NOT_ADMITTED'
    assert D.prepare(tmp_path,scope,wire)['status']=='NOT_ADMITTED'
    assert not (tmp_path/'evidence/WORKFLOWS').exists()

def test_owner_prepares_decimal_intent_and_bounded_context_templates(tmp_path):
    from laplace.work import project_work_navigation as N
    scope=O.owned_workspace('sdk');wire=original();wire['definition']['layout']={'write':{'x':0.00001,'y':1.25}}
    prepared=D.read(tmp_path,scope,{'facet':'withdrawal-preview','operation':'save','original_request':wire,'request_token':'decimal-public'})
    assert prepared['effect']=='none' and prepared['request_token']=='decimal-public'
    assert prepared['intent_digest']==canonical_digest(wire)
    assert 'original_request' not in prepared['withdraw']['http']['payload']
    actual={**prepared['withdraw']['http']['payload'],'original_request':wire}
    assert D.withdraw(tmp_path,scope,actual)['status']=='NOT_ADMITTED'
    draft=body();draft['steps'][0]['assignment']['instructions']='Ω'*6000
    preview=D.read(tmp_path,scope,{'facet':'execution-preview','definition':draft,'step_ids':['write','review']})
    assert N.emitted(preview)<=N.line()
    role=preview['roles'][0];handle=role['context_read']
    assert handle['http']['method']=='POST' and handle['request']['step_id']=='write'
    assert handle['request']['step_ids']==['write','review'] and 'definition' not in handle['request']
    assert handle['required_inputs']==['definition'] and handle['definition_digest']==canonical_digest(draft)
    context=D.read(tmp_path,scope,{**handle['request'],'definition':draft})
    assert context['basis']==preview['basis'] and context['returned']<context['total_characters']
    assert context['next_read']['request']['step_ids']==['write','review']
    assert N.emitted(context)<=N.line()


T0='2026-10-30T00:00:00+00:00'

def at(seconds):
    import datetime as dt
    return (dt.datetime.fromisoformat(T0)+dt.timedelta(seconds=seconds)).isoformat()

def v2_body(**policy):
    value=body();value['steps'].append({'id':'synth','title':'Synthesis','assignment':{'role':'synthesis','instructions':'Synthesise every attempt.','settings':{}}})
    value['edges'].append({'id':'review-write','from':'review','to':'write','kind':'feedback'})
    value['run_policy']={'profile':D.RESEARCH_POLICY_V2,'max_iterations':3,'max_admissions':4,'deadline_seconds':600,'runtime_seconds':300,
        'advance':'automatic-review','apply':'human','continuation_criteria':'Material findings remain.','exit_criteria':'No material findings remain.',**policy}
    return value

def test_legacy_v1_policy_never_reaches_extended_scheduler():
    v1={'profile':D.RESEARCH_POLICY,'max_iterations':2,'runtime_seconds':300,'advance':'automatic-review','apply':'human'}
    state={'iteration':2,'attempts':[{}]*9,'loop_started_at':T0}
    assert F.loop_policy(v1) is None and F.loop_admission(v1,state,at(10**6)) is None
    assert F.loop_after_judgement(v1,state,'REVISE',at(10**6)) is None and F.step_seconds(v1,state,at(10**6))==300
    assert F.loop_summary(v1)['scheduler']=='legacy-v1' and F.loop_summary(None)['scheduler']=='none'
    with pytest.raises(D.Refused,match='INVALID_RUN_POLICY'):D.validate({**body(),'run_policy':{**v1,'max_iterations':4}})

def test_v2_schedules_one_next_step_from_actual_judgement_and_exits_on_each_budget():
    policy=v2_body()['run_policy']
    state={'iteration':1,'attempts':[{'event_id':'a'},{'event_id':'b'}],'loop_started_at':T0}
    step=F.loop_after_judgement(policy,state,'REVISE',at(30))
    assert step['decision']=='CONTINUE' and step['iteration']==2 and step['next']=='writer' and 'scheduled' in step
    exhausted={**state,'iteration':2,'attempts':[{}]*4}
    assert F.loop_after_judgement(policy,exhausted,'REVISE',at(30))['reason']=='ADMISSIONS_INSUFFICIENT_FOR_NEXT_ITERATION'
    assert F.loop_after_judgement(policy,{**state,'iteration':3},'REVISE',at(30))['reason']=='ITERATION_BUDGET_REACHED'
    late=F.loop_after_judgement(policy,state,'REVISE',at(600))
    assert late['reason']=='LOOP_DEADLINE_REACHED' and late['state']=='LIMIT_REACHED' and late['synthesis']=='DUE_AT_ORIGINAL_PARENT'
    accepted=F.loop_after_judgement(policy,state,'ACCEPT',at(30))
    assert accepted['reason']=='EXIT_CRITERIA_MET' and accepted['state']=='AWAITING_HUMAN_APPLY'
    with pytest.raises(D.Refused,match='UNKNOWN_REVIEW_VERDICT'):F.loop_after_judgement(policy,state,'MAYBE',at(30))

def test_v2_admission_gate_and_step_deadline_are_bounded_by_authored_limits():
    policy=v2_body()['run_policy']
    assert F.loop_admission(policy,{'attempts':[]},at(0)) is None and F.step_seconds(policy,{'attempts':[]},at(0))==300
    assert F.step_seconds(policy,{'attempts':[{}],'loop_started_at':T0},at(500))==100
    assert F.loop_admission(policy,{'attempts':[{}]*4,'loop_started_at':T0},at(1))['reason']=='ADMISSION_BUDGET_EXHAUSTED'
    stop=F.loop_admission(policy,{'attempts':[{}],'loop_started_at':T0,'iteration':1},at(601))
    assert stop['reason']=='LOOP_DEADLINE_REACHED' and stop['admissions_used']==1 and stop['elapsed_seconds']==601

def test_v2_preview_requires_parent_synthesis_and_delivers_criteria_only_to_reviewer(tmp_path):
    scope=O.owned_workspace('sdk');draft=v2_body();D.validate(draft)
    full=D.read(tmp_path,scope,{'facet':'execution-preview','definition':draft})
    # The research return bridge is integrated; per-run admission fences are tested on actual owners below.
    assert full['loop']['scheduler']=='incremental-bounded-review-revision' and full['loop']['executable'] is True
    assert full['loop']['bridge']==F.BRIDGE and 'V2_BRIDGE_INCOMPLETE' in full['loop']['admission_fence']
    assert not any(i['code']=='EXTENDED_POLICY_REQUIRES_PARENT_SYNTHESIS' for i in full['issues'])
    partial=D.read(tmp_path,scope,{'facet':'execution-preview','definition':draft,'step_ids':['write','review']})
    assert any(i['code']=='EXTENDED_POLICY_REQUIRES_PARENT_SYNTHESIS' for i in partial['issues'])
    review,receipt=F.instruction(draft,'review');write,_=F.instruction(draft,'write')
    assert 'No material findings remain.' in review and 'No material findings remain.' not in write
    assert 'loop-criteria' in [o['kind'] for o in receipt['origins']] and receipt['permission_effect']=='none'
    assert all(o.get('custody') for o in receipt['origins'])
    missing=v2_body();del missing['run_policy']['max_admissions']
    with pytest.raises(D.Refused,match='INVALID_RUN_POLICY'):D.validate(missing)

def test_original_parent_synthesis_refuses_incompatible_override_and_keeps_compatible(tmp_path,monkeypatch):
    from laplace.writing import records
    prepared={'turn_id':'WT-parent','session_id':'WS-parent'}
    monkeypatch.setattr(records,'fold_records',lambda root:{'turns':{'WT-parent':{'project':'book','session_id':'WS-parent',
        'provider_settings':{'provider':'claude','model':'opus','effort':'high'}}},'sessions':{'WS-parent':{}}})
    draft=v2_body();draft['steps'][2]['assignment']['settings']={'model':'opus'}
    result=F.parent_synthesis(tmp_path,'book',draft,['write','review','synth'],prepared)
    assert result['execution_location']=='original-parent' and result['admitted_settings']['model']=='opus' and result['mandatory_inputs']
    draft['steps'][2]['assignment']['settings']={'model':'another'}
    with pytest.raises(D.Refused,match='PARENT_SYNTHESIS_SETTINGS_CONFLICT'):F.parent_synthesis(tmp_path,'book',draft,['write','review','synth'],prepared)
    with pytest.raises(D.Refused,match='ORIGINAL_PARENT_SESSION_REQUIRED'):F.parent_synthesis(tmp_path,'foreign',v2_body(),['synth'],prepared)

def test_synthesis_coverage_requires_every_exact_attempt_judgement_and_pin():
    state={'attempts':[{'event_id':'WD-1'},{'event_id':'WD-2'}],
        'plan_history':[{'proposal':{'id':'ART-old','sha256':'sha256:'+'1'*64},'judgement':{'turn_id':'WT-r0','verdict':'REVISE','findings':['f']}}],
        'proposal':{'id':'ART-new','sha256':'sha256:'+'2'*64},'judgement':{'turn_id':'WT-r1','verdict':'REVISE','findings':['g','h']}}
    pin={'research_workflow':{'input_packet':{'id':'ART-packet','sha256':'sha256:'+'3'*64}}}
    required=F.synthesis_requirements(state,pin)
    assert {(r['kind'],r['id']) for r in required}=={('input-packet','ART-packet'),('attempt-result','WD-1'),('attempt-result','WD-2'),
        ('proposal','ART-old'),('proposal','ART-new'),('judgement','WT-r0'),('judgement','WT-r1')}
    assert next(r for r in required if r['id']=='WT-r1')['unresolved_findings']==2
    consumed=[{'kind':r['kind'],'id':r['id'],'sha256':r.get('sha256'),'read_receipt':'READ-'+r['id']} for r in required]
    assert F.synthesis_coverage(required,consumed)['status']=='COMPLETE'
    with pytest.raises(D.Refused,match='SYNTHESIS_INPUT_COVERAGE_INCOMPLETE'):F.synthesis_coverage(required,consumed[:-1])
    changed=copy.deepcopy(consumed);next(c for c in changed if c['id']=='ART-new')['sha256']='sha256:'+'9'*64
    with pytest.raises(D.Refused,match='SYNTHESIS_INPUT_COVERAGE_INCOMPLETE'):F.synthesis_coverage(required,changed)
    with pytest.raises(D.Refused,match='SYNTHESIS_CONSUMPTION_RECEIPT_REQUIRED'):F.synthesis_coverage(required,[{**consumed[0],'read_receipt':None}])

def test_stop_composition_never_reports_unobserved_children_as_stopped():
    gate={'run':{'state':'STOP_BEFORE_NEXT'}}
    children=[{'event_id':'WD-1','observed_state':'RESULT','control':None},
        {'event_id':'WD-2','observed_state':'RESERVED','control':{'status':'REQUESTED'}},
        {'event_id':'WD-3','observed_state':'RESERVED','control':None,'error':'owner unavailable'}]
    result=F.stop_composition(gate,children)
    assert result['future_admission']['effective'] and not result['run_stopped'] and result['outcome']=='FUTURE_GATED_CHILDREN_PENDING'
    assert [c['stop'] for c in result['children']]==['SETTLED','REQUESTED','UNKNOWN'] and result['unknown']==['WD-3']
    assert 'retained' in result['effects']
    assert F.stop_composition({'run':{'state':'RUNNING'}},children[:1])['outcome']=='NOT_GATED'
    assert F.stop_composition(gate,children[:1])['run_stopped'] is True
    offer=F.stop_offer({'workflow-stop-before-next':{'available':True}},[{'event_id':'WD-2','state':'RESERVED','turn_id':'WT-2'},{'event_id':'WD-1','state':'RESULT'}])
    assert offer['owned_children_total']==1 and offer['future_admission_gate']=={'available':True}

def test_context_delivery_carries_custody_size_and_origin_without_permission(tmp_path,monkeypatch):
    from laplace.writing import records
    monkeypatch.setattr(records,'selected_journal_fields',lambda project,turn,root,fields:{'id':turn,'project':'book','session_id':'WS-parent','text':'Original request.'})
    prepared={'turn_id':'WT-parent','session_id':'WS-parent'}
    draft=body();draft['steps'].insert(0,{'id':'group','title':'Group','assignment':{'role':'builder','instructions':'Group guidance.','settings':{}}})
    draft['steps'][1]['parent_id']='group'
    draft['steps'][1]['assignment']['context']=[{'kind':'ancestor-instructions','step_id':'group'},{'kind':'parent-message'}]
    text,receipt=F.compiled_instruction(tmp_path,'book',draft,'write',prepared)
    assert 'Group guidance.' in text and 'Original request.' in text
    origins={o['kind']:o for o in receipt['origins']}
    assert origins['parent-message']['custody']=='writing-session-turn-journal' and origins['parent-message']['utf8_bytes']==len(b'Original request.')
    assert origins['ancestor-instructions']['custody']=='definition-version-body' and receipt['permission_effect']=='none'
    assert receipt['utf8_bytes']==len(text.encode()) and receipt['limits']==F.DELIVERY_LIMITS
    draft['steps'][1]['assignment']['context']=[{'kind':'selected-evidence'}]
    with pytest.raises(D.Refused,match='CONTEXT_REQUIRES_EVIDENCE_PACKET_PROFILE'):F.compiled_instruction(tmp_path,'book',draft,'write',prepared)
    draft['steps'][1]['assignment']['context']=[];draft['steps'][1]['assignment']['instructions']='x'*(F.DELIVERY_LIMITS['utf8_bytes']+1)
    with pytest.raises(D.Refused,match='CONTEXT_DELIVERY_BOUND'):F.compiled_instruction(tmp_path,'book',draft,'write',prepared)

def test_river_loop_is_bounded_recorded_metadata_and_names_missing_packet():
    assert F.river_loop({},None)=={'observed':False,'reason':'NO_RECORDED_RUN_STATE'}
    policy=v2_body()['run_policy']
    state={'state':'LIMIT_REACHED','iteration':2,'policy':policy,'loop_started_at':T0,
        'attempts':[{'event_id':'WD-%d'%i} for i in range(30)],'loop_exit':{'reason':'ADMISSION_BUDGET_EXHAUSTED'}}
    view=F.river_loop(state,None)
    assert view['admissions_used']==30 and view['exit']['reason']=='ADMISSION_BUDGET_EXHAUSTED'
    assert view['synthesis_inputs']['total']==30 and len(view['synthesis_inputs']['items'])==24 and view['synthesis_inputs']['omitted']==6
    assert view['synthesis_inputs']['input_packet'].startswith('NOT_IN_THIS_RECORD') and view['policy']['executable'] is True
    state['attempts'][0]['event_id']='changed';assert view['synthesis_inputs']['items'][0]['id']=='WD-0'


# ---- Controlled real-owner routes. Deterministic replies pass through the actual
# preparation, admission, delivery, review, read-receipt and Work owners. There is
# no provider inference, network or paid run; these are not live-model evidence.
from test_research_workflow_runs import run_root, start_run, finish  # noqa: E402,F401


def _v2_body():
    value=D.starter_definition()
    for step in value['steps']:step['assignment']['settings'].update(provider='codex',model='public-model',effort='low')
    value['steps'].append({'id':'synth','title':'Original-parent synthesis','assignment':{'role':'synthesis',
        'instructions':'Synthesise every attempt, judgement and unresolved finding; state what remains open.','settings':{}}})
    value['run_policy']={'profile':D.RESEARCH_POLICY_V2,'max_iterations':2,'max_admissions':4,'deadline_seconds':3000,
        'runtime_seconds':300,'advance':'automatic-review','apply':'human',
        'continuation_criteria':'A material finding remains.','exit_criteria':'No material finding remains.'}
    return value


@pytest.fixture
def v2_root(tmp_path,monkeypatch):
    from test_writing_operating import _project
    from laplace.writing import provider,provider_catalogue,turn_execution as X,turn_admission as T
    from laplace.work import project_work as W,work_delivery as WD,object_facets
    manuscript=_project(tmp_path)
    catalogue={'providers':[{'id':'codex','available':True,'models':[{'id':'public-model','supports_effort':True,'efforts':['low']}]}]}
    monkeypatch.setattr(provider,'capabilities',lambda *a,**k:copy.deepcopy(catalogue))
    monkeypatch.setattr(provider_catalogue,'provider_catalogue',lambda *a,**k:copy.deepcopy(catalogue))
    monkeypatch.setattr(provider,'context_window_advertised',lambda *a,**k:None)
    launches=[];monkeypatch.setattr(X,'start',launches.append)
    parent=T.start_turn(tmp_path,{'project':'book','mode':'work','provider':'codex','model':'public-model','effort':'low',
        'text':'Prepare a bounded reviewed draft with original-parent synthesis.','request_id':'public-v2-author','selection':{'files':['main.tex']}})
    value=_v2_body()
    saved=D.save(tmp_path,O.project_scope('book','sdk'),{'request_id':'public-v2-save','expected_revision':None,'definition':value})
    reference=object_facets.ref('domain.projects','source-file',project='book',path='main.tex',scope='manuscript')
    entry=object_facets.request(tmp_path,O.project_scope('book','sdk'),{'facet':'object','reference':reference,'section':'body','offset':0,'limit':4000})['input_descriptor']
    caller=D.native_caller(tmp_path,'book','work',parent['turn_id'])
    with pytest.raises(ValueError,match='EXTENDED_POLICY_REQUIRES_PARENT_SYNTHESIS'):
        D.prepare(tmp_path,caller,{'profile':D.APP_PROFILE,'request_id':'public-v2-no-synthesis','reference':saved['reference'],
            'step_ids':['write','review'],'goal':'Refused without synthesis.','fan_out_max':2,'inputs':[entry],'selection':{'files':['main.tex']}})
    prepared=D.prepare(tmp_path,caller,{'profile':D.APP_PROFILE,'request_id':'public-v2-prepare','reference':saved['reference'],
        'step_ids':['write','review','synth'],'goal':'A bounded reviewed proposal with original-parent synthesis.','fan_out_max':2,
        'inputs':[entry],'selection':{'files':['main.tex']}})
    work=prepared['work']['id'];recipients={}
    for name,effect in [('writer','proposal-writer'),('reviewer','independent-review')]:
        recipients[name]=WD.handle(tmp_path,'book',{'action':'workflow-bind','request_id':'public-v2-approve-'+name,'work_id':work,
            'expected_work_revision':W._task_revision(W._tasks('book',tmp_path)[work]),'kind':'app-owned','effect':effect,
            'provider':'codex','model':'public-model','effort':'low'},{'origin':'human'})['binding']['id']
    yield {'root':tmp_path,'manuscript':manuscript,'parent':parent,'saved':saved,'prepared':prepared,'work':work,
        'recipients':recipients,'launches':launches,'caller':caller,'body':value,'entry':entry}
    for launch in launches:
        if not launch.job.get('done'):X._finish(launch,{'status':'interrupted'})


def _start_v2(s,request='public-v2-start'):
    from laplace.writing import workflow_progression as P
    from laplace.work import work_delivery as WD
    return WD.handle(s['root'],'book',{'action':'workflow-start','work_id':s['work'],'request_id':request,
        'expected_run_revision':P.view(s['root'],'book',s['work'])['revision'],'recipients':s['recipients']},
        {'origin':'native','turn_id':s['parent']['turn_id']})


def _proposal(after):
    return {'answer':'Public scoped proposal.','edits':[{'file':'main.tex','line_start':3,'line_end':3,
        'before':'Original prose.','after':after,'reason':'Clarify the selected passage.'}]}


def _judgement(verdict,*findings):
    return {'status':'completed','text':json.dumps({'verdict':verdict,'findings':[{'id':f,'summary':'Public finding '+f+'.'} for f in findings]})}


RESERVED_GUARD='published only by its run owner action workflow-synthesis'


def _read_all(root,turn_id,payload):
    """Actual native reads in one turn; returns the exact banked receipt IDs."""
    from laplace.native import tools
    from laplace.writing import records
    receipts=[];offset=None
    while True:
        before={r['id'] for r in records.index(root).by_turn.get(turn_id,[]) if r.get('record')=='writing-tool-read'}
        out=tools.execute(root,'book','work','read_artifact',{**payload,**({'offset':offset} if offset else {})},turn_id=turn_id)
        out=json.loads(out) if isinstance(out,str) else out
        new=[r['id'] for r in records.index(root).by_turn.get(turn_id,[]) if r.get('record')=='writing-tool-read' and r['id'] not in before]
        assert len(new)==1,out
        receipts+=new;offset=out.get('next_offset')
        if not offset:return receipts


def test_v2_preparation_fences_bridge_and_refuses_incompatible_parent_override(v2_root,monkeypatch):
    from laplace.writing import workflow_progression as P
    s=v2_root;root=s['root']
    task,plan,pin,artifact,state=P._load(root,'book',s['work'])
    assert pin['synthesis']['bridge']==F.BRIDGE and pin['synthesis']['execution_location']=='original-parent'
    assert pin['synthesis']['declared_settings']=={} and isinstance(plan['synthesis_return_path'],str)
    assert F.bridge_problem(pin,plan) is None
    broken=copy.deepcopy(pin);del broken['synthesis']['bridge']
    assert F.bridge_problem(broken,plan)
    exit_=F.loop_admission(pin['research_workflow']['policy'],{'attempts':[]},at(0),pin=broken,plan=plan)
    assert exit_['reason']=='V2_BRIDGE_INCOMPLETE' and exit_['state']=='PARTIAL'
    assert F.loop_admission(pin['research_workflow']['policy'],{'attempts':[]},at(0),pin=pin,plan=plan) is None
    value=copy.deepcopy(s['body']);value['steps'][2]['assignment']['settings']={'model':'another-model'}
    saved=D.save(root,O.project_scope('book','sdk'),{'request_id':'public-v2-override-save','definition_id':s['saved']['definition_id'],
        'expected_revision':s['saved']['reference']['version']['definition_revision'],'definition':value})
    with pytest.raises(ValueError,match='PARENT_SYNTHESIS_SETTINGS_CONFLICT'):
        D.prepare(root,s['caller'],{'profile':D.APP_PROFILE,'request_id':'public-v2-override-prepare','reference':saved['reference'],
            'step_ids':['write','review','synth'],'goal':'Refuse an incompatible parent override.','fan_out_max':2,
            'inputs':[s['entry']],'selection':{'files':['main.tex']}})
    # A plan whose bridge marker is not the integrated one never starts a child.
    monkeypatch.setattr(F,'BRIDGE','laplace.workflow-synthesis-bridge/not-integrated')
    with pytest.raises(ValueError,match='V2_BRIDGE_INCOMPLETE'):_start_v2(s)
    assert len(s['launches'])==1 and P.view(root,'book',s['work'])['state']=='PREPARED'


def test_v2_actual_route_bounded_iterations_and_original_parent_synthesis(v2_root,monkeypatch):
    from laplace.writing import workflow_progression as P,turn_admission as T,dispatch_parent
    from laplace.work import work_delivery as WD,project_work as W
    from laplace.projects import artifacts
    s=v2_root;root=s['root']
    _start_v2(s);writer=s['launches'][-1]
    assert writer.workflow_execution['effect']=='proposal-writer' and len(s['launches'])==2
    early=P.view(root,'book',s['work'])
    assert early['synthesis']['required'] and early['synthesis']['bridge']==F.BRIDGE and not early['synthesis']['due']
    with pytest.raises(ValueError,match='SYNTHESIS_NOT_DUE'):
        WD.handle(root,'book',{'action':'workflow-synthesis','work_id':s['work'],'request_id':'public-v2-early-synthesis',
            'expected_run_revision':early['revision'],'synthesis':{'status':'BLOCKED','summary':'Too early.','remaining_work':['Wait.']},
            'consumed':[]},{'origin':'native','turn_id':s['parent']['turn_id']})
    finish(writer,{'status':'completed','text':'Public writer result.','proposal':_proposal('Draft one.')})
    review=s['launches'][-1];assert review.mode=='review'
    finish(review,_judgement('REVISE','cutoff'))
    writer2=s['launches'][-1];assert writer2.mode=='revise' and writer2.turn_id!=writer.turn_id
    middle=P.view(root,'book',s['work'])
    assert middle['loop_decision']['decision']=='CONTINUE' and middle['iteration']==2
    finish(writer2,{'status':'completed','text':'Public revised result.','proposal':_proposal('Revised prose.')})
    review2=s['launches'][-1];assert review2.mode=='review' and review2.turn_id!=review.turn_id
    finish(review2,_judgement('REVISE','units'))
    ended=P.view(root,'book',s['work'])
    assert ended['state']=='LIMIT_REACHED' and ended['loop_exit']['reason']=='ITERATION_BUDGET_REACHED'
    assert len(ended['attempts'])==4 and len(s['launches'])==5,ended['attempts']
    section=ended['synthesis'];assert section['due'] and section['pending_children']==[] and section['inputs_omitted']==0
    kinds=[(i['kind'],i['coverage']) for i in section['inputs']]
    assert kinds.count(('judgement','OWNER_READ_RECEIPT_REQUIRED'))==2 and kinds.count(('proposal','OWNER_READ_RECEIPT_REQUIRED'))==2
    assert kinds.count(('attempt-result','OWNER_CARRIED_RECORD'))==4
    assert ('plan','OWNER_READ_RECEIPT_REQUIRED') in kinds and ('input-packet','OWNER_READ_RECEIPT_REQUIRED') in kinds
    # The original parent continues in its own session through a new admitted turn.
    finish(s['launches'][0],{'status':'completed','text':'Prepared and started.'})
    turn=T.start_turn(root,{'project':'book','mode':'work','session_id':s['parent']['session_id'],
        'text':'Synthesise the bounded run from its exact inputs.','request_id':'public-v2-synthesis-turn'})['turn_id']
    door={'origin':'native','turn_id':turn}
    reading=[i for i in section['inputs'] if i['coverage']=='OWNER_READ_RECEIPT_REQUIRED']
    consumed=[{'kind':i['kind'],'id':i['id'],'read_receipts':_read_all(root,turn,i['read']['payload'])} for i in reading]
    judged=[i['id'] for i in reading if i['kind']=='judgement']
    authored={'status':'BLOCKED','summary':'Two bounded iterations are retained; the units finding is unresolved.',
        'conclusions':['The cutoff assumption is now explicit.'],'remaining_work':['Resolve the units finding before Apply.'],
        'findings':[{'judgement_id':judged[0],'finding_id':'cutoff','disposition':'ADDRESSED','note':'Revised in iteration two.'},
                    {'judgement_id':judged[1],'finding_id':'units','disposition':'UNRESOLVED'}]}
    def publish(request,actor=None,**change):
        current=P.view(root,'book',s['work'])
        return WD.handle(root,'book',{'action':'workflow-synthesis','work_id':s['work'],'request_id':request,
            'expected_run_revision':current['revision'],'synthesis':authored,'consumed':consumed,**change},actor or door)
    with pytest.raises(ValueError,match='ORIGINAL_PARENT_SESSION_REQUIRED'):publish('public-v2-human',actor={'origin':'human'})
    with pytest.raises(ValueError,match='SYNTHESIS_INPUT_COVERAGE_INCOMPLETE'):publish('public-v2-missing',consumed=consumed[:-1])
    fabricated=copy.deepcopy(consumed);fabricated[0]['read_receipts']=['READ-'+'0'*32]
    with pytest.raises(ValueError,match='SYNTHESIS_READ_RECEIPT_UNKNOWN'):publish('public-v2-fabricated',consumed=fabricated)
    wrong=copy.deepcopy(consumed);wrong[1]['read_receipts']=list(consumed[0]['read_receipts'])
    with pytest.raises(ValueError,match='SYNTHESIS_READ_RECEIPT_WRONG_INPUT'):publish('public-v2-wrong',consumed=wrong)
    other=T.start_turn(root,{'project':'book','mode':'work','provider':'codex','model':'public-model','effort':'low',
        'text':'Another conversation reads the same plan.','request_id':'public-v2-foreign-reader'})['turn_id']
    foreign=copy.deepcopy(consumed);foreign[0]['read_receipts']=_read_all(root,other,reading[0]['read']['payload'])
    with pytest.raises(ValueError,match='SYNTHESIS_READ_RECEIPT_FOREIGN'):publish('public-v2-foreign',consumed=foreign)
    extra=[*consumed,{'kind':'proposal','id':'ART-'+'f'*32,'read_receipts':consumed[0]['read_receipts']}]
    with pytest.raises(ValueError,match='SYNTHESIS_INPUT_NOT_REQUIRED'):publish('public-v2-extra',consumed=extra)
    with pytest.raises(ValueError,match='SYNTHESIS_COMPLETE_NOT_SUPPORTED'):
        publish('public-v2-complete',synthesis={**authored,'status':'COMPLETE','remaining_work':[]})
    # Controlled settings double: a changed parent setting refuses an explicit declaration.
    task,_plan,pin,artifact,state=P._load(root,'book',s['work'])
    declared=copy.deepcopy(pin);declared['synthesis']['declared_settings']={'model':'public-model'}
    real=F._turn_settings;monkeypatch.setattr(F,'_turn_settings',lambda *a:{'provider':'codex','model':'changed-model','effort':'low'})
    with pytest.raises(D.Refused,match='PARENT_SYNTHESIS_SETTINGS_CONFLICT'):
        F.synthesis_publication(root,'book',task,P._checked_plan(root,'book',task)[0],declared,artifact,state,
            lambda ident:[],{'request_id':'public-v2-settings','synthesis':authored,'consumed':consumed},
            {'kind':'native','session_id':s['parent']['session_id'],'turn_id':turn})
    monkeypatch.setattr(F,'_turn_settings',real)
    # Corrupt custody: judgement ART bytes change after they were read.
    jart=next(i for i in reading if i['kind']=='judgement')['artifact']['id']
    target=artifacts.target(root,'book',{'id':jart})[0];held=target.read_bytes();target.write_bytes(held+b' ')
    with pytest.raises(ValueError,match='SYNTHESIS_READ_RECEIPT_STALE|SYNTHESIS_INPUT_CUSTODY_UNAVAILABLE'):publish('public-v2-stale')
    target.write_bytes(held)
    published=publish('public-v2-synthesis')
    record=published['synthesis']['published']
    assert record['status']=='BLOCKED' and record['inputs']==len(reading) and record['turn_id']==turn
    assert len(s['launches'])==7  # parent, four children, synthesis turn, foreign reader; no new child
    document=json.loads(artifacts.target(root,'book',{'id':record['artifact']['id']})[0].read_bytes())
    assert document['schema_version']==F.SYNTHESIS_SCHEMA and len(document['attempts'])==4
    assert {f['finding']['id']:f['synthesis_disposition'] for f in document['findings']}=={'cutoff':'ADDRESSED','units':'UNRESOLVED'}
    assert all(i['coverage']=='COMPLETE_EXACT_OWNER_READS' for i in document['inputs'])
    assert document['execution']['session_id']==s['parent']['session_id'] and document['execution']['turn_id']==turn
    assert publish('public-v2-synthesis')['synthesis']['published']==record
    with pytest.raises(ValueError,match='SYNTHESIS_ALREADY_PUBLISHED'):publish('public-v2-late-second')
    view=dispatch_parent.synthesis_view(W._tasks('book',root)[s['work']],'book',root)
    assert view['status']=='VALID' and view['retained_status']=='BLOCKED' and view['attach_action']['payload']['status']=='blocked'
    assert P.view(root,'book',s['work'])['actions']['resume']['permitted'] is False


def test_stop_run_gates_future_admission_and_controls_exact_owned_children(run_root):
    from laplace.writing import workflow_progression as P
    from laplace.work import work_delivery as WD
    s=run_root;root=s['root'];start_run(s);writer=s['launches'][-1]
    before=P.view(root,'book',s['work'],door={'origin':'human'})
    action=before['actions']['stop-run'];owned=action['coverage']['owned_children']
    assert action['permitted'] and owned==[writer.workflow_execution['event_id']]
    payload=copy.deepcopy(action['native']['payload']);assert payload['children']==owned
    with pytest.raises(Exception,match='STOP_CHILD_COVERAGE_MISMATCH'):WD.handle(root,'book',{**payload,'children':[]},{'origin':'human'})
    assert P.view(root,'book',s['work'])['state']=='RUNNING'
    stopped=WD.handle(root,'book',payload,{'origin':'human'});stop=stopped['stop']
    assert stop['future_admission']['effective'] and stop['coverage']['complete'] and stop['controls_issued_now']
    assert stop['children'][0]['event_id']==owned[0] and stop['children'][0]['stop'] in {'REQUESTED','UNKNOWN','SETTLED'}
    assert stopped['state']=='STOP_BEFORE_NEXT' and stopped['stop_request']['children']==owned
    if stop['children'][0]['stop']!='SETTLED':assert stop['run_stopped'] is False
    finish(writer,{'status':'interrupted'})
    assert len(s['launches'])==2  # the gate admitted no reviewer
    replay=WD.handle(root,'book',payload,{'origin':'human'})['stop']
    assert not replay['controls_issued_now'] and replay['children'][0]['stop']=='SETTLED' and replay['outcome']=='STOPPED'
    assert replay['children'][0]['control']==stop['children'][0]['control'] and len(s['launches'])==2


def test_river_and_uses_keep_identity_cut_scope_and_current_versus_recorded(run_root):
    s=run_root;root=s['root'];start_run(s)
    scope=O.project_scope('book','sdk');ref=s['saved']['reference']
    uses=D.read(root,scope,{'facet':'uses','reference':ref})
    assert uses['total']==1 and uses['items'][0]['admission']=='ADMITTED' and uses['items'][0]['recorded_run']['state']=='RUNNING'
    river=D.read(root,scope,{'facet':'river','reference':ref,'work_id':s['work']})
    row=river['items'][0];event=row['event_id']
    assert river['run_identity']['work_id']==s['work'] and river['run_identity']['plan_generation']
    from laplace.work import project_work_navigation as N
    assert N.emitted(river)<=N.line() and river['row_projection']['detail_read']==river['run_read']
    assert row['iteration']==1 and row['session_id'] and row['turn_id'] and row['reads']['reply']
    assert row['settings']['prepared']['model']=='public-model' and all(set(a)=={'name','title','permitted','reason'} for a in river['actions'])
    assert river['current_observation']['items'][event]['observed'] and river['stop']['coverage']=='COMPLETE'
    # wave 11: current liveness is also keyed by the row's turn (an app-dispatch row has no event_id), outside the cut
    assert river['current_observation']['by_turn'][row['turn_id']]==river['current_observation']['items'][event]
    assert 'session_read' not in row['reads'].get('conversation',{}) or row['reads']['conversation']['session_read']['http']['url'].startswith('/authoring/session?')
    assert river['body_inspection']=='NOT_REQUESTED' and river['loop']['synthesis_inputs']['input_packet']=='INCLUDED'
    assert D.read(root,scope,{'facet':'river','reference':ref,'work_id':s['work'],'as_of':river['cut']})['cut']==river['cut']
    with pytest.raises(D.Refused,match='WORKFLOW_USES_CHANGED'):
        D.read(root,scope,{'facet':'river','reference':ref,'work_id':s['work'],'as_of':'sha256:'+'0'*64})
    with pytest.raises(D.Refused,match='APP_RUN_NOT_IN_SCOPE'):
        D.read(root,scope,{'facet':'river','reference':ref,'work_id':'WORK-not-this-run'})
    with pytest.raises(ValueError):D.read(root,O.project_scope('foreign','sdk'),{'facet':'river','reference':ref,'work_id':s['work']})
    changed=copy.deepcopy(ref);changed['version']['definition_revision']='sha256:'+'1'*64
    with pytest.raises(ValueError):D.read(root,scope,{'facet':'river','reference':changed,'work_id':s['work']})


def test_river_row_carries_turn_times_and_tool_call_identities_never_bodies():
    """Wave 11 (ruling 2, option b): a river row with a recorded turn carries that turn's start and reply times, the
    provider settings recorded on it and each tool call's kind, operation, status and time; no message, payload or
    output crosses. A row without a turn, or a turn the records do not hold, carries no turn facts."""
    turn={'id':'WT-1','ts':'2026-11-06T14:01:02.000Z','text':'BODY','provider_settings':{'provider':'claude','model':'m','effort':'low','secret':'x'},
        'reply':{'status':'completed','ts':'2026-11-06T14:01:32.000Z','text':'REPLY BODY'},
        'tool_reads':{'k1':{'id':'READ-1','operation':'project','ts':'2026-11-06T14:01:10.000Z','payload':{'view':'x'}},
                      'k2':{'id':'READ-1','operation':'project','ts':'2026-11-06T14:01:10.000Z','payload':{'alias':True}}},
        'tool_actions':[{'id':'ACTION-1','operation':'proposal_submit','ts':'2026-11-06T14:01:20.000Z','payload':{'body':'P'},'outcome':{'status':'RECORDED'}}],
        'tool_failures':[{'id':'FAIL-1','operation':'apply_revision','ts':'2026-11-06T14:01:05.000Z','code':'REFUSED_SCOPE','error':'long'}]}
    step={'step_id':'draft','title':'Draft','state':'NO-RETURN','assignment_role':'builder','replied':True,'reply_status':'completed',
        'session_id':'WS-1','turn_id':'WT-1','conversation':{'project':'p','session_id':'WS-1','turn_id':'WT-1','project_url':'/project?x',
        'session_read':{'http':{'method':'GET','url':'/authoring/session?project=p&id=WS-1&view=summary'}},'public_content_read':{'http':{}}}}
    row=F._river_row(step,{'WT-1':turn})
    assert row['assignment_role']=='builder' and row['replied'] is True and row['reply_status']=='completed'
    facts=row['turn']
    assert facts['started_at']=='2026-11-06T14:01:02.000Z' and facts['replied_at']=='2026-11-06T14:01:32.000Z' and facts['reply_status']=='completed' and facts['reply_error'] is None
    failed=F._river_row(step,{'WT-1':{**turn,'reply':{'status':'failed','ts':'2026-11-06T14:01:33.000Z','error':'DEPENDENCY-INCOMPLETE: '+'x'*400}}})['turn']
    assert failed['reply_status']=='failed' and failed['reply_error'].startswith('DEPENDENCY-INCOMPLETE: ') and len(failed['reply_error'])==300
    assert facts['provider_settings']=={'provider':'claude','model':'m','effort':'low'}
    assert [(c['kind'],c['id'],c['operation'],c['status'],c['at']) for c in facts['tool_calls']]==[
        ('failure','FAIL-1','apply_revision','REFUSED_SCOPE','2026-11-06T14:01:05.000Z'),
        ('read','READ-1','project',None,'2026-11-06T14:01:10.000Z'),
        ('action','ACTION-1','proposal_submit','RECORDED','2026-11-06T14:01:20.000Z')] and facts['tool_calls_total']==3
    assert 'BODY' not in json.dumps(row) and 'payload' not in json.dumps(facts) and 'public_content_read' not in row['reads']['conversation']
    assert row['reads']['conversation']['session_read']['http']['url'].endswith('view=summary')
    assert 'turn' not in F._river_row(step,{}) and 'turn' not in F._river_row({**step,'turn_id':None}, {'WT-1':turn}) and 'turn' not in F._river_row(step)
    many={**turn,'tool_reads':{str(i):{'id':'R'+str(i),'operation':'project','ts':'2026-11-06T14:02:%02d.000Z'%i} for i in range(20)},'tool_actions':[],'tool_failures':[]}
    capped=F._river_row(step,{'WT-1':many})['turn'];assert len(capped['tool_calls'])==F._TURN_CALL_LIMIT and capped['tool_calls_total']==20


def test_withdrawal_race_has_one_winner_and_contradictory_custody_refuses(tmp_path):
    import threading,datetime as dt
    scope=O.owned_workspace('sdk');wire=original();results={};barrier=threading.Barrier(2)
    def run(name,call):
        barrier.wait()
        try:results[name]=call()
        except Exception as error:results[name]=error
    threads=[threading.Thread(target=run,args=('save',lambda:D.save(tmp_path,scope,wire))),
        threading.Thread(target=run,args=('withdraw',lambda:D.withdraw(tmp_path,scope,withdrawal(wire))))]
    for thread in threads:thread.start()
    for thread in threads:thread.join(60)
    assert all(isinstance(v,dict) for v in results.values()) and len(results)==2,results
    total=D.read(tmp_path,scope,{})['total']
    if results['withdraw']['status']=='NOT_ADMITTED':assert total==0 and results['save']['status']=='NOT_ADMITTED'
    else:assert total==1 and results['withdraw']['withdrawal']=='ALREADY_RECORDED_NO_UNDO'
    other={**original(),'request_id':'public-contradiction'};D.save(tmp_path,scope,other)
    D.W._bank(D._root(tmp_path),{'record':F.DECISION,'operation':'save','scope':{'kind':'owned-workspace'},'request_id':other['request_id'],
        'intent_digest':canonical_digest(other),'decision':'WITHDRAWN','ts':dt.datetime.now(dt.timezone.utc).isoformat()})
    with pytest.raises(D.Refused,match='REQUEST_CUSTODY_CONTRADICTORY'):D.save(tmp_path,scope,other)
    with pytest.raises(D.Refused,match='REQUEST_CUSTODY_CONTRADICTORY'):D.withdraw(tmp_path,scope,withdrawal(other))
    try:observed=D.read(tmp_path,scope,{'facet':'request','request_id':other['request_id']})
    except D.Refused as error:assert 'CONTRADICTORY' in str(error)
    else:assert observed.get('reason')!='WITHDRAWN'


def test_lost_save_acknowledgement_is_recorded_and_never_withdrawn(tmp_path,monkeypatch):
    scope=O.owned_workspace('sdk');wire={**original(),'request_id':'public-late-save'};bank=D.W._bank
    def lost(*args,**kwargs):bank(*args,**kwargs);raise OSError('controlled lost save acknowledgement')
    monkeypatch.setattr(D.W,'_bank',lost)
    with pytest.raises(OSError):D.save(tmp_path,scope,wire)
    monkeypatch.setattr(D.W,'_bank',bank)
    result=D.withdraw(tmp_path,scope,withdrawal(wire))
    assert result['status']=='RECORDED' and result['withdrawal']=='ALREADY_RECORDED_NO_UNDO'
    assert D.read(tmp_path,scope,{})['total']==1


def test_pointer_receipt_never_counts_as_whole_input_and_reserved_path_refuses_direct_write(v2_root):
    """Retains the independent pointer adversary: a real scalar-pointer receipt is a read, not whole coverage."""
    from laplace.writing import workflow_progression as P,records
    from laplace.native import tools
    from laplace.projects import artifacts
    s=v2_root;root=s['root'];turn=s['parent']['turn_id'];session=s['parent']['session_id']
    task,plan,pin,artifact,state=P._load(root,'book',s['work'])
    item=next(x for x in F.synthesis_inputs(state,pin,artifact) if x['kind']=='plan')
    key=next(k for k,v in plan.items() if isinstance(v,str))
    pointer='/'+key.replace('~','~0').replace('/','~1')
    before={r['id'] for r in records.index(root).by_turn.get(turn,[]) if r.get('record')=='writing-tool-read'}
    tools.execute(root,'book','work','read_artifact',{**item['read']['payload'],'pointer':pointer,'limit':1000},turn_id=turn)
    pointed=[r['id'] for r in records.index(root).by_turn.get(turn,[]) if r.get('record')=='writing-tool-read' and r['id'] not in before]
    assert len(pointed)==1
    with pytest.raises(D.Refused,match='SYNTHESIS_READ_RECEIPT_NOT_WHOLE_INPUT'):F.verify_consumption(root,'book',session,item,pointed)
    whole=_read_all(root,turn,item['read']['payload'])
    covered=F.verify_consumption(root,'book',session,item,whole)
    assert covered['coverage']=='COMPLETE_EXACT_OWNER_READS' and covered['unit']=='raw-artifact-pages' and covered['read_receipts']==whole
    with pytest.raises(D.Refused,match='SYNTHESIS_READ_RECEIPT_NOT_WHOLE_INPUT'):F.verify_consumption(root,'book',session,item,[*whole,*pointed])
    # A direct write to the reserved research path is refused at write time, not only disqualified later.
    reserved=P._checked_plan(root,'book',task)[0]['synthesis_return_path']
    content=json.dumps({'schema_version':F.SYNTHESIS_SCHEMA,'work_id':s['work'],'status':'COMPLETE'})
    with pytest.raises(ValueError,match=RESERVED_GUARD):
        artifacts.store(root,'book',{'scope':'project','path':reserved,'before':None,'reason':'Direct write must not qualify.',
            'content':content},turn)
    target=artifacts.resolve_path(root,'book',reserved);assert not target.exists()
    # Controls on the same owner check, without writing: only the run owner's held exact bytes, from the
    # original parent session, pass. Other bytes in that scope, another session, no turn or no scope refuse.
    from laplace.writing import dispatch_parent,turn_admission as T
    foreign=T.start_turn(root,{'project':'book','mode':'work','provider':'codex','model':'public-model','effort':'low',
        'text':'Foreign conversation.','request_id':'public-v2-foreign-publisher'})['turn_id']
    with dispatch_parent.research_publication(s['work'],content):
        dispatch_parent.validate_publication(root,'book',target,content,turn)
        with pytest.raises(ValueError,match=RESERVED_GUARD):dispatch_parent.validate_publication(root,'book',target,content+' ',turn)
        with pytest.raises(ValueError,match=RESERVED_GUARD):dispatch_parent.validate_publication(root,'book',target,content,foreign)
        with pytest.raises(ValueError,match=RESERVED_GUARD):dispatch_parent.validate_publication(root,'book',target,content,None)
    with pytest.raises(ValueError,match=RESERVED_GUARD):dispatch_parent.validate_publication(root,'book',target,content,turn)
    assert not target.exists()


def _due_synthesis(s,request):
    """Run the controlled v2 route to ACCEPT and read every required input in a fresh original-parent turn."""
    from laplace.writing import workflow_progression as P,turn_admission as T
    from laplace.projects import artifacts
    root=s['root'];_start_v2(s)
    finish(s['launches'][-1],{'status':'completed','text':'Controlled writer result.','proposal':_proposal('Reviewed public revision.')})
    finish(s['launches'][-1],_judgement('ACCEPT'))
    view=P.view(root,'book',s['work']);assert view['state']=='AWAITING_HUMAN_APPLY' and view['synthesis']['due']
    finish(s['launches'][0],{'status':'completed','text':'Original preparation finished.'})
    turn=T.start_turn(root,{'project':'book','mode':'work','session_id':s['parent']['session_id'],
        'text':'Publish the exact reviewed synthesis.','request_id':request+'-parent'})['turn_id']
    consumed=[{'kind':i['kind'],'id':i['id'],'read_receipts':_read_all(root,turn,i['read']['payload'])}
              for i in view['synthesis']['inputs'] if i['coverage']=='OWNER_READ_RECEIPT_REQUIRED']
    task=P._load(root,'book',s['work'])[0]
    reserved=artifacts.resolve_path(root,'book',P._checked_plan(root,'book',task)[0]['synthesis_return_path'])
    payload={'action':'workflow-synthesis','work_id':s['work'],'request_id':request,
        'expected_run_revision':P.view(root,'book',s['work'])['revision'],
        'synthesis':{'status':'COMPLETE','summary':'The exact public proposal is independently accepted; human Apply remains separate.',
            'conclusions':['Controlled recovery witness.'],'remaining_work':[],'findings':[]},'consumed':consumed}
    return turn,payload,{'origin':'native','turn_id':turn},reserved


def _publications(root,reserved):
    from laplace.writing import records
    path=reserved.relative_to(root).as_posix()
    return [r for r in records.index(root).by_project.get('book',[]) if r.get('record')=='writing-artifact' and r.get('path')==path]


def _assert_published_once(s,reserved,payload,door,turn,art_id,recovered_by=None):
    """One durable ART, its exact bytes at the reserved path, one owner run.synthesis and an idempotent replay."""
    from laplace.writing import workflow_progression as P,records,dispatch_parent
    from laplace.work import work_delivery as WD,project_work as W
    from laplace.projects import artifacts
    root=s['root'];rows=_publications(root,reserved);assert [r['id'] for r in rows]==[art_id]
    # The journal row carries a typed body reference; the records owner hydrates the exact text.
    held=records.selected_journal_fields('book',art_id,root,fields=['id','after','sha256']);raw=held['after'].encode('utf-8')
    assert reserved.read_bytes()==raw and artifacts.revision(raw)==held['sha256']
    state=P._load(root,'book',s['work'])[4];recorded=state['synthesis']
    assert recorded['artifact']['id']==art_id and recorded['artifact']['sha256']==held['sha256']
    assert recorded['turn_id']==turn and recorded['request_id']==payload['request_id'] and recorded['status']=='COMPLETE'
    assert recorded.get('recovered_by_turn_id')==recovered_by and json.loads(raw)['execution']['turn_id']==turn
    view=dispatch_parent.synthesis_view(W._tasks('book',root)[s['work']],'book',root)
    assert view['status']=='VALID' and view['retained_status']=='COMPLETE',view
    published=P.view(root,'book',s['work'])['synthesis']['published'];assert published['artifact']['id']==art_id
    assert WD.handle(root,'book',copy.deepcopy(payload),door)['synthesis']['published']==published
    assert [r['id'] for r in _publications(root,reserved)]==[art_id] and reserved.read_bytes()==raw
    assert P._load(root,'book',s['work'])[4]['synthesis']==recorded


def test_same_request_synthesis_recovers_after_durable_art_before_file(v2_root,monkeypatch):
    """F1: the ART is banked, then the pending file write fails. The same original-parent request recovers it once."""
    from laplace.writing import workflow_progression as P,turn_admission as T,records,dispatch_parent
    from laplace.work import work_delivery as WD
    from laplace.projects import artifacts
    s=v2_root;root=s['root']
    turn,payload,door,reserved=_due_synthesis(s,'controlled-same-synthesis-recovery');wire=copy.deepcopy(payload)
    write=Path.write_bytes
    def fail_pending(path,data):
        if path.parent==reserved.parent and path.name.startswith(reserved.name+'.') and path.name.endswith('.pending'):
            raise OSError('CONTROLLED_AFTER_DURABLE_ART_BEFORE_PENDING_FILE')
        return write(path,data)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'write_bytes',fail_pending)
        with pytest.raises(OSError,match='CONTROLLED_AFTER_DURABLE_ART_BEFORE_PENDING_FILE'):WD.handle(root,'book',payload,door)
    rows=_publications(root,reserved);assert len(rows)==1 and not reserved.exists() and payload==wire
    assert not P.view(root,'book',s['work'])['synthesis']['published']
    held=records.selected_journal_fields('book',rows[0]['id'],root,fields=['id','after','sha256','reader_metadata'])
    assert isinstance(held['after'],str)
    # The owner recovery check keeps its authority: no anonymous, foreign, unscoped or other-bytes recovery.
    foreign=T.start_turn(root,{'project':'book','mode':'work','provider':'codex','model':'public-model','effort':'low',
        'text':'Foreign parent.','request_id':'controlled-wrong-parent'})['turn_id']
    def recover(actor):
        return artifacts.recover_workflow_publication(root,'book',held['id'],held['sha256'],held['reader_metadata'],
            admit=lambda:None,turn_id=actor)
    with dispatch_parent.research_publication(s['work'],held['after']):
        for actor in (None,foreign):
            with pytest.raises(ValueError,match=RESERVED_GUARD):recover(actor)
    with dispatch_parent.research_publication(s['work'],held['after']+' '):
        with pytest.raises(ValueError,match=RESERVED_GUARD):recover(turn)
    with pytest.raises(ValueError,match=RESERVED_GUARD):recover(turn)
    with pytest.raises(ValueError,match='original author session|ORIGINAL_PARENT_SESSION_REQUIRED'):
        WD.handle(root,'book',copy.deepcopy(payload),{'origin':'native','turn_id':foreign})
    assert len(_publications(root,reserved))==1 and not reserved.exists()
    assert not P.view(root,'book',s['work'])['synthesis']['published']
    WD.handle(root,'book',copy.deepcopy(payload),door)
    _assert_published_once(s,reserved,payload,door,turn,rows[0]['id'])


def test_same_request_synthesis_recovers_after_file_before_run_phase_save(v2_root,monkeypatch):
    """The ART and its file exist, then the run phase save fails. The same request records that one publication."""
    from laplace.writing import workflow_progression as P
    from laplace.work import work_delivery as WD,project_work as W
    s=v2_root;root=s['root']
    turn,payload,door,reserved=_due_synthesis(s,'controlled-run-save-recovery')
    append=W._append
    def fail_synthesis_phase(*args,**kwargs):
        row=args[1] if len(args)>1 else kwargs.get('row')
        if isinstance(row,dict) and row.get('action')=='workflow-synthesis':
            raise OSError('CONTROLLED_AFTER_FILE_BEFORE_RUN_PHASE')
        return append(*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(W,'_append',fail_synthesis_phase)
        with pytest.raises(OSError,match='CONTROLLED_AFTER_FILE_BEFORE_RUN_PHASE'):WD.handle(root,'book',copy.deepcopy(payload),door)
    rows=_publications(root,reserved);assert len(rows)==1 and reserved.is_file()
    assert not P.view(root,'book',s['work'])['synthesis']['published']
    WD.handle(root,'book',copy.deepcopy(payload),door)
    _assert_published_once(s,reserved,payload,door,turn,rows[0]['id'])


def test_same_request_synthesis_recovers_from_a_later_original_parent_turn(v2_root,monkeypatch):
    """A later genuine turn of the original session completes the first durable publication exactly, keeping its turn."""
    from laplace.writing import workflow_progression as P,turn_admission as T
    from laplace.work import work_delivery as WD
    s=v2_root;root=s['root']
    turn,payload,door,reserved=_due_synthesis(s,'controlled-later-turn-recovery')
    write=Path.write_bytes
    def fail_pending(path,data):
        if path.parent==reserved.parent and path.name.startswith(reserved.name+'.') and path.name.endswith('.pending'):
            raise OSError('CONTROLLED_AFTER_DURABLE_ART_BEFORE_PENDING_FILE')
        return write(path,data)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'write_bytes',fail_pending)
        with pytest.raises(OSError,match='CONTROLLED_AFTER_DURABLE_ART_BEFORE_PENDING_FILE'):WD.handle(root,'book',copy.deepcopy(payload),door)
    rows=_publications(root,reserved);assert len(rows)==1 and not reserved.exists()
    finish(next(x for x in s['launches'] if x.turn_id==turn),{'status':'completed','text':'Interrupted publication turn ended.'})
    later=T.start_turn(root,{'project':'book','mode':'work','session_id':s['parent']['session_id'],
        'text':'Recover the same retained request.','request_id':'controlled-later-turn-recovery-retry'})['turn_id']
    later_door={'origin':'native','turn_id':later};assert later!=turn
    foreign=T.start_turn(root,{'project':'book','mode':'work','provider':'codex','model':'public-model','effort':'low',
        'text':'Foreign parent.','request_id':'controlled-later-turn-foreign'})['turn_id']
    with pytest.raises(ValueError,match='original author session|ORIGINAL_PARENT_SESSION_REQUIRED'):
        WD.handle(root,'book',copy.deepcopy(payload),{'origin':'native','turn_id':foreign})
    # A changed request under the same request_id never adopts the retained publication.
    changed=copy.deepcopy(payload);changed['synthesis']['summary']='A different conclusion under the same request.'
    with pytest.raises(ValueError,match='belongs to another publication'):WD.handle(root,'book',changed,later_door)
    assert len(_publications(root,reserved))==1 and not reserved.exists()
    assert not P.view(root,'book',s['work'])['synthesis']['published']
    WD.handle(root,'book',copy.deepcopy(payload),later_door)
    _assert_published_once(s,reserved,payload,later_door,turn,rows[0]['id'],recovered_by=later)


def test_parent_continuation_names_the_exact_review_phase_read(tmp_path):
    """The parent return names the existing guarded phase read that carries the verdict and every finding."""
    from laplace.work import work_delivery as WD,project_work_review as R
    task={'id':'WORK-public-review','project':'book','phases':[{'id':'PHASE-public-review','kind':'review','verdict':'HOLD',
        'findings':[{'id':'F1','summary':'Public finding.'}]}]}
    intent={'id':'WD-public-event','obligation_id':'public-obligation','recipient':{'effect':'independent-review'}}
    row={'turn_id':'WT-public-reviewer','result':{'status':'completed'},
        'acceptance':{'status':'HOLD','currentness':'CURRENT','review_id':'PHASE-public-review','by_this_delivery':True}}
    read=R.phase_read(task,tmp_path,'PHASE-public-review')
    text=WD._continuation_text(task,intent,row,root=tmp_path)
    assert json.dumps({'operation':read['operation'],'payload':read['payload']},sort_keys=True) in text and len(text)<=4000
    assert read['payload']['phase_revision'].startswith('sha256:') and 'work_delivery {action: status, event_id: WD-public-event}' in text
    for missing in ({**row['acceptance'],'review_id':None},{**row['acceptance'],'review_id':'PHASE-absent'}):
        assert 'phase_revision' not in WD._continuation_text(task,intent,{**row,'acceptance':missing},root=tmp_path)
