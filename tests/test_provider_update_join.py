from laplace.writing import records as record_owner
from laplace.representation import writing_bodies as bodies
import pytest
from laplace.writing import provider_updates as updates
from laplace.work import author_history_metrics as metrics
from laplace.native import tools as writing_tools
from laplace.writing import reads as reads_owner
from laplace.writing import session_reads
from laplace.writing import turn_control
from laplace.writing import child_hosts
from laplace.writing import turn_jobs
from laplace.writing.records import _fold as records_fold
from laplace.writing import mutation_attribution
from laplace.writing import turn_context
from laplace.pipeline import authoring
from laplace.writing import records
from test_authoring_core import _fixture

@pytest.fixture(autouse=True)
def clear():
    updates._PATHS.clear();metrics._INDEXES.clear();authoring._HISTORY_CACHE.clear();records_fold._CACHE.clear()
    yield
    updates._PATHS.clear();metrics._INDEXES.clear();authoring._HISTORY_CACHE.clear();records_fold._CACHE.clear()


def seed(root,monkeypatch):
    _fixture(root,monkeypatch)
    record_owner.bank(root,{'record':'writing-session','id':'WS-S','project':'p'})
    record_owner.bank(root,{'record':'writing-turn','id':'T','project':'p','session_id':'WS-S','selection':{'files':['sec_one.tex']},'consumed':{'corrections':[]}})
    return authoring.bank_correction('p',{'text':'Current author instruction','kind':'request','scope':'project','by':'author'},root)['correction']


def test_offer_metadata_warm_repeat_no_body_reads_or_rich_history(tmp_path,monkeypatch):
    instruction=seed(tmp_path,monkeypatch)
    first=updates.author_offer(tmp_path,'p','T')
    assert first['status']=='OFFERED_AT_TOOL_BOUNDARY' and first['updates'][0]['id']==instruction['id']
    monkeypatch.setattr(session_reads,'_records',lambda *a,**k:pytest.fail('rich history'))
    monkeypatch.setattr(authoring,'_read',lambda *a,**k:pytest.fail('authoring body parse'))
    monkeypatch.setattr(authoring,'_source',lambda *a,**k:pytest.fail('source resolution'))
    next_read=updates.author_offer(tmp_path,'p','T')
    assert next_read['status']=='AWAITING_EXACT_READ'
    updates.acknowledge(tmp_path,'p','T',instruction['id'])
    assert updates.author_offer(tmp_path,'p','T') is None
    assert updates.turn_scope(tmp_path,'p','T').get('consumed_correction_ids')==[] # ack does not claim consumption


def test_observation_history_wrong_project_and_unoffered_ack_do_not_instruct(tmp_path,monkeypatch):
    instruction=seed(tmp_path,monkeypatch)
    authoring.bank_correction('p',{'text':'Agent progress','kind':'note','scope':'project','by':'eigen:session'},tmp_path)
    # Existing role semantics keep plain observational history out of instruction selection.
    state,_,_=updates.correction_snapshot(tmp_path,'p')
    state['corrections'].append({'id':'OBS','status':'open','scope':'project','text':'Observation','context_role':'observation-only','by':'author'})
    assert [row['id'] for row in updates.author_offer(tmp_path,'p','T')['updates']]==[instruction['id']]
    assert updates.author_offer(tmp_path,'other','T') is None
    updates.acknowledge(tmp_path,'p','T','NOT-OFFERED')
    assert 'NOT-OFFERED' not in updates.turn_scope(tmp_path,'p','T')['author_update_acks']


@pytest.mark.parametrize('provider',['claude','codex'])
def test_existing_turn_mailbox_offer_is_pending_then_once_offered_and_never_retargeted(tmp_path,monkeypatch,provider):
    instruction=seed(tmp_path,monkeypatch)
    turn=updates.turn_scope(tmp_path,'p','T');turn['provider_settings']={'provider':provider}
    child_hosts._update_child_execution(tmp_path,'WS-S',{'state':'RUNNING','turn_id':'T','session_id':'WS-S','project':'p','host':child_hosts._process_identity(),'provider_inference_started':True})
    admitted=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Change attention now','delivery_mode':'project_tool_boundary'})
    assert admitted['delivery']=='PENDING'
    first=updates.turn_input_offer(tmp_path,'p','T')
    assert first['status']=='PUBLISHED_AT_TOOL_BOUNDARY' and first['inputs'][0]['message']=='Change attention now'
    assert updates.turn_input_offer(tmp_path,'p','T') is None
    rows=session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING',item_id=admitted['control_id'])
    assert rows[0]['payload']['text']=='Change attention now'
    updates.acknowledge_turn_input(tmp_path,'p','T',admitted['control_id'])
    assert session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING',item_id=admitted['control_id'])[0]['state']=='EXACT_SCOPED_CONTROL_READ'
    other=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Keep my pending draft','delivery_mode':'project_tool_boundary'})
    child_hosts._finish_child_execution(tmp_path,'WS-S','T','completed')
    assert updates.turn_input_offer(tmp_path,'p','T') is None
    receipt=session_reads._child_control_rows(tmp_path,'WS-S','T','FINISHED',item_id=other['control_id'])[0]
    assert receipt['state']=='FAILED' and receipt['payload']['text']=='Keep my pending draft'
    assert updates.turn_input_offer(tmp_path,'other','T') is None


def test_generic_technical_report_exact_actor_evidence_and_no_guidance_or_work_mutation(tmp_path,monkeypatch):
    from laplace.work import technical_friction as friction
    from laplace.pipeline import friction_consumer
    instruction=seed(tmp_path,monkeypatch)
    record_owner.bank(tmp_path,{'record':'writing-tool-failure','id':'FAIL-one','project':'p','turn_id':'T','operation':'source','error':'Observed technical failure'})
    request={'verb':'record','concept':'technical-friction@project','target':'p','expected':[],
        'payload':{'owning_layer':'writing-tools','value':'Missing capability observed','chain':['Project purpose','Current turn','source failed'],'tool_record_id':'FAIL-one'},'by':'author'}
    before=(tmp_path/'manuscript/authoring.json').read_bytes()
    result=writing_tools.call(tmp_path,'p','review',request,turn_id='T')
    record=result['owner_response']['record']
    assert result['outcome']=='recorded' and record['status']=='open' and record['by']=='eigen:session'
    assert record['evidence']['turn_id']=='T' and record['evidence']['tool_record_id']=='FAIL-one'
    assert record['node']=='authoring:p::T' and result['owner_response']['work_status_changed'] is False
    assert (tmp_path/'manuscript/authoring.json').read_bytes()==before
    assert result['owner_response']['call_receipt']['operation']=='corpus/friction-report'
    assert mutation_attribution._read_views('corpus/friction-read',{})==set()
    read=writing_tools.call(tmp_path,'p','review',result['owner_response']['read_handle']['native_request'])
    assert read['owner_response']['record']==record
    current=friction.read(tmp_path,'p',{})
    assert current['records'][0]['id']==record['id']
    with pytest.raises(ValueError,match='observed tool record'):
        friction.report(tmp_path,'p','T',{**request['payload'],'tool_record_id':'foreign'})
    with pytest.raises(ValueError,match='bound agent turn'):
        friction.report(tmp_path,'other','T',request['payload'])
    resolution=friction_consumer.make_friction_resolution(record['id'],evidence='fixture exact repair proof',project='p')
    from laplace.pipeline.ledger import append_jsonl
    append_jsonl(tmp_path/'corpus_friction/p.jsonl',resolution)
    assert friction.read(tmp_path,'p',{})['records']==[]
    assert friction.read(tmp_path,'p',{'view':'history'})['records'][0]['id']==record['id']


def test_both_native_project_tool_boundaries_offer_and_full_read_ack_distinct_consumption(tmp_path,monkeypatch):
    instruction=seed(tmp_path,monkeypatch)
    # A normal source operation is not needed to exercise the shared result seam.
    original=writing_tools.execute
    def fake(root,project,mode,operation,payload,turn_id=None,*,requested_by=""):
        assert requested_by==""
        if operation=='help':return {'project':project,'scope':'metadata'}
        if operation=='author_history':return authoring.history(project,payload,root)
        return original(root,project,mode,operation,payload,turn_id,requested_by=requested_by)
    monkeypatch.setattr(writing_tools,'execute',fake)
    offered=writing_tools.call(tmp_path,'p','work',{'operation':'help','payload':{}},turn_id='T')
    assert offered['author_updates']['correction_ids']==[instruction['id']]
    read=writing_tools.call(tmp_path,'p','work',offered['author_updates']['required_reads'][0]['native_request'],turn_id='T')
    assert read['owner_response']['item']['text']=='Current author instruction' and 'author_updates' not in read
    assert updates.turn_scope(tmp_path,'p','T')['author_update_acks'][instruction['id']]['status']=='EXACT_SCOPED_AUTHOR_HISTORY_READ'
    assert updates.turn_scope(tmp_path,'p','T')['consumed_correction_ids']==[]


def test_boundary_changes_attention_once_and_exact_reread_never_reprepares(tmp_path,monkeypatch):
    seed(tmp_path,monkeypatch);monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000)
    turn=updates.turn_scope(tmp_path,'p','T')
    child_hosts._update_child_execution(tmp_path,'WS-S',{'state':'RUNNING','turn_id':'T','session_id':'WS-S','project':'p','host':child_hosts._process_identity()})
    first=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Use the second passage',
        'delivery_mode':'project_tool_boundary','selection':{'files':['sec_two.tex'],'line_start':1,'line_end':2,'draft':{'status':'UNSAVED','format':'rendered','reason':'Still typing','text':'PRIVATE UNSAVED DRAFT','anchor':{'file':'sec_two.tex','line_start':1,'line_end':2}}},'workspace_context':{'surface':'manuscript'}})
    with pytest.raises(ValueError,match='awaiting publication'):
        turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Next instruction','delivery_mode':'project_tool_boundary'})
    offer=updates.turn_input_offer(tmp_path,'p','T')
    assert [row['control_id'] for row in offer['inputs']]==[first['control_id']]
    assert not offer['inputs'][0]['message_truncated'] and 'PRIVATE UNSAVED DRAFT' in offer['inputs'][0]['message']
    current=session_reads._records(tmp_path)['turns']['T']
    assert current['selection']['files']==['sec_two.tex'] and 'PRIVATE UNSAVED DRAFT' not in str(current['dependencies'])
    second=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Next instruction','delivery_mode':'project_tool_boundary'})
    saved=(tmp_path/'contract/talk.jsonl').read_bytes()
    monkeypatch.setattr(turn_control,'_prepare_steering_input',lambda *a,**k:pytest.fail('duplicate context preparation'))
    delivered=updates.acknowledge_turn_input(tmp_path,'p','T',first['control_id'])
    assert delivered['status']=='EXACT_SCOPED_CONTROL_READ' and 'PRIVATE UNSAVED DRAFT' in delivered['message']
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==saved
    again=updates.acknowledge_turn_input(tmp_path,'p','T',first['control_id'])
    assert again['status']=='ALREADY_READ' and (tmp_path/'contract/talk.jsonl').read_bytes()==saved
    assert session_reads.child_execution(tmp_path,'WS-S')['last_control']['control_id']==second['control_id']


def test_public_controls_omit_recovery_bodies_but_exact_inspection_and_recovery_keep_them(tmp_path,monkeypatch):
    import json
    seed(tmp_path,monkeypatch);monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000)
    turn=updates.turn_scope(tmp_path,'p','T')
    child_hosts._update_child_execution(tmp_path,'WS-S',{'state':'RUNNING','turn_id':'T',
        'session_id':'WS-S','project':'p','host':child_hosts._process_identity()})
    ids=[]
    for number in range(2):
        admitted=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p',
            'text':('Retained author request '+str(number)+' ')*1000,
            'delivery_mode':'project_tool_boundary','selection':{'files':['sec_two.tex']}})
        ids.append(admitted['control_id'])
        assert updates.turn_input_offer(tmp_path,'p','T')['status']=='PUBLISHED_AT_TOOL_BOUNDARY'
    mailbox=child_hosts._steer_mailbox(tmp_path,'WS-S')
    files={path:path.read_bytes() for path in mailbox.glob('*.json')}
    public=session_reads.child_execution(tmp_path,'WS-S',controls=True)
    raw=session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING')
    assert len(raw)==len(public['controls'])==2
    assert all('preparation' in row for row in raw)
    assert all('preparation' not in row and 'payload' not in row and 'result' not in row for row in public['controls'])
    assert public['last_control']==public['controls'][-1]
    assert len(json.dumps(public['controls']).encode())<6000
    assert len(json.dumps(raw).encode())>len(json.dumps(public['controls']).encode())*5
    assert child_hosts._child_execution_record(tmp_path,'WS-S')['last_control']['control_id']==ids[-1]
    assert {path:path.read_bytes() for path in files}==files
    exact_call=writing_tools.call(tmp_path,'p','work',public['controls'][0]['read_handle']['native_request'],turn_id='T')
    assert exact_call['owner_response']['items'][0]['preparation']==raw[0]['preparation']
    exact=session_reads.session_turn_detail(tmp_path,'p','T','controls',item_id=ids[0])['items'][0]
    assert exact['preparation']==raw[0]['preparation'] and exact['payload']['text'].startswith('Retained author request 0')
    receipt=child_hosts._read_host(next(mailbox.glob('*-'+ids[-1]+'.ack.json')))
    request=child_hosts._read_host(next(mailbox.glob('*-'+ids[-1]+'.request.json')))['payload']
    prepared,message=updates._retained_input(tmp_path,'p','T',receipt,request)
    assert prepared==raw[-1]['preparation'] and 'Retained author request 1' in message
    for state in ('FAILED','PUBLICATION_UNCONFIRMED','PUBLISHED_AT_TOOL_BOUNDARY'):
        observed={**raw[0],'state':state,'terminal':True,'publication':{'scope':'PREVIEW','text_complete':False,'parts':{'author_request':{'included_chars':2,'total_chars':3,'complete':False}}}}
        projected=child_hosts._public_control_receipt(observed,project='p',session_id='WS-S')
        assert projected['state']==state and projected['terminal'] is True
        assert projected['publication']==observed['publication'] and 'preparation' not in projected
    corrupt={**raw[0],'state':'PUBLICATION_UNCONFIRMED','terminal':True,
             'context_invalidation_unproved':'Retained rollback checksum changed.'}
    unscoped=child_hosts._public_control_receipt(corrupt,session_id='WS-S')
    assert 'read_handle' not in unscoped
    assert unscoped['context_invalidation_unproved']==corrupt['context_invalidation_unproved']
    assert unscoped['state']=='PUBLICATION_UNCONFIRMED' and unscoped['terminal'] is True


def test_failure_response_boundary_offers_instruction_without_ack(tmp_path,monkeypatch):
    instruction=seed(tmp_path,monkeypatch)
    monkeypatch.setattr(writing_tools,'failure_response',lambda *a,**k:{'ok':False,'error':'original failure'})
    response=writing_tools.tool_failure(tmp_path,'p','work','source',{},ValueError('original failure'),'T')
    assert response['error']=='original failure' and response['author_updates']['correction_ids']==[instruction['id']]
    assert updates.turn_scope(tmp_path,'p','T')['author_update_acks']=={}


def test_shared_help_and_kernel_advertise_only_proven_technical_owner_actions(tmp_path,monkeypatch):
    from laplace.native import declarations
    from laplace.writing import operating
    seed(tmp_path,monkeypatch)
    help=writing_tools.execute(tmp_path,'p','review','help',{'concept':'technical-friction@project'})
    assert help['read_navigation']['native_request']['concept']=='technical-friction@project'
    actions=help['native_actions'];assert {row['verb'] for row in actions}=={'record','create'}
    from jsonschema import Draft202012Validator
    for row in actions:
        assert row['native_request']['target']=='p' and row['permission']['agent_bound_required'] is True
        assert not list(Draft202012Validator(row['payload']).iter_errors(row['native_request']['payload']))
    contracts=operating.tool_contract()
    assert {row['concept'] for row in contracts['generic_actions']}=={'technical-friction@project'}
    assert len(reads_owner.READS|reads_owner.WRITES)==86


def test_legacy_reserved_future_feedback_and_agent_claimed_author_are_not_updates(tmp_path,monkeypatch):
    instruction=seed(tmp_path,monkeypatch)
    path=tmp_path/'manuscript/authoring.json'
    import json
    value=json.loads(path.read_text())
    value['corrections'].append({'id':'FUTURE','text':'Unknown future feedback','status':'open','kind':'request','scope':'project','by':'author',
        'anchor':{'feedback_target':{'schema_version':'laplace.response-feedback-target/99'}}})
    path.write_text(json.dumps(value))
    writing_tools.execute(tmp_path,'p','review','note',{'text':'Agent pretending human','kind':'request','scope':'project'},turn_id='T',requested_by='author')
    offered=updates.author_offer(tmp_path,'p','T')
    assert offered['correction_ids']==[instruction['id']]
    assert offered['updates'][0]['human_actor_proof']=='unproven'


def test_attention_preparation_releases_global_admission_lock_and_closed_race_changes_no_basis(tmp_path,monkeypatch):
    from laplace.work import project_work
    from concurrent.futures import ThreadPoolExecutor
    seed(tmp_path,monkeypatch);turn=updates.turn_scope(tmp_path,'p','T')
    child_hosts._update_child_execution(tmp_path,'WS-S',{'state':'RUNNING','turn_id':'T','session_id':'WS-S','project':'p','host':child_hosts._process_identity()})
    control=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'New attention','delivery_mode':'project_tool_boundary'})
    def independent_admission():
        with project_work.dispatch_lock(tmp_path):return True
    pool=ThreadPoolExecutor(max_workers=1)
    def prepare(root,current,payload):
        assert pool.submit(independent_admission).result(timeout=1) is True
        child_hosts._finish_child_execution(root,'WS-S','T','interrupted')
        return {'message':'Prepared but never delivered','message_parts':{'context':[0,0],'author_request':[0,28]},'context':{'context_id':'CTX-must-not-bank'},'selection':{},'workspace':{},'unsaved_draft':None,'held':{}}
    monkeypatch.setattr(turn_control,'_prepare_steering_input',prepare)
    saved=(tmp_path/'contract/talk.jsonl').read_bytes()
    try:result=updates.turn_input_offer(tmp_path,'p','T')
    finally:pool.shutdown(wait=True)
    assert result['status']=='PUBLICATION_UNCONFIRMED' and (tmp_path/'contract/talk.jsonl').read_bytes()==saved
    assert updates.turn_scope(tmp_path,'p','T')['selection']['files']==['sec_one.tex']
    assert session_reads._child_control_rows(tmp_path,'WS-S','T','FINISHED',item_id=control['control_id'])[0]['payload']['text']=='New attention'


def test_provider_control_truth_and_explicit_unsupported_mode_refuse_without_retarget(tmp_path,monkeypatch):
    from laplace.writing.provider import WritingTurn
    for provider in ('claude','codex'):
        control=object.__new__(WritingTurn);control.provider=provider;control.project='p';control.conn=object();control.turn_id='native'
        capabilities=control.control_capabilities()
        assert capabilities['can_offer_input'] is True
        assert capabilities['can_steer'] is (provider=='codex')
        assert ('native_rpc' in capabilities['input_delivery_modes']) is (provider=='codex')
    seed(tmp_path,monkeypatch)
    class Unsupported:
        def control_capabilities(self):return {'can_steer':False,'can_offer_input':True}
    turn_jobs._JOBS['T']={'done':False,'provider':Unsupported()}
    try:
        for mode in ('invented','native_rpc'):
            with pytest.raises(ValueError,match='mode|native steering'):
                turn_control.steer_turn(tmp_path,{'turn_id':'T','text':'Preserve draft','delivery_mode':mode})
    finally:turn_jobs._JOBS.pop('T',None)
    assert not list(child_hosts._steer_mailbox(tmp_path,'WS-S').glob('*.request.json'))


def test_technical_report_cut_binding_and_unevidenced_resolution_keep_owner_truth(tmp_path,monkeypatch):
    from laplace.work import technical_friction as friction
    from laplace.pipeline import friction_consumer,ledger,adjudicate
    seed(tmp_path,monkeypatch)
    result=friction.report(tmp_path,'p','T',{'owning_layer':'tools','value':'Observed missing door','chain':['purpose','tool failure']})
    ident=result['record']['id'];first=friction.read(tmp_path,'p',{})
    ledger.append_jsonl(tmp_path/'corpus_friction/p.jsonl',{'record':adjudicate.RESOLUTION,'id':'INVALID-RESOLUTION','supersedes':ident,'evidence':''})
    assert friction.read(tmp_path,'p',{})['records'][0]['id']==ident
    with pytest.raises(ValueError,match='another scope'):
        friction.read(tmp_path,'other',{'as_of':first['as_of']})
    resolution=friction_consumer.make_friction_resolution(ident,evidence='Exact known repair proof',project='p')
    ledger.append_jsonl(tmp_path/'corpus_friction/p.jsonl',resolution)
    assert friction.read(tmp_path,'p',{})['records']==[]
    assert friction.read(tmp_path,'p',{'id':ident})['record']==result['record']
    historical=friction.read(tmp_path,'p',{'view':'history'})
    assert historical['records'][0]['id']==ident


@pytest.mark.parametrize('payload',[{'id':''},{'id':'unknown','cursor':'cut'},{'id':'unknown','view':'history'},{'view':99}])
def test_technical_detail_rejects_ignored_or_malformed_scope_before_io(tmp_path,monkeypatch,payload):
    from laplace.work import technical_friction as friction
    monkeypatch.setattr(metrics,'index',lambda *a,**k:pytest.fail('Invalid scope must refuse before owner I/O'))
    with pytest.raises(ValueError):friction.read(tmp_path,'p',payload)


def test_legacy_attempts_and_unqualified_ack_do_not_claim_current_delivery(tmp_path,monkeypatch):
    instruction=seed(tmp_path,monkeypatch)
    record_owner.bank(tmp_path,{'record':'writing-author-update-delivery','id':'OLD-ATTEMPT','project':'p','turn_id':'T',
        'correction_ids':[instruction['id']],'status':'ATTEMPTED'})
    record_owner.bank(tmp_path,{'record':'writing-author-update-ack','id':'OLD-ACK','project':'p','turn_id':'T',
        'correction_id':instruction['id'],'status':'EXACT_AUTHOR_HISTORY_READ'})
    offered=updates.author_offer(tmp_path,'p','T')
    assert offered['status']=='OFFERED_AT_TOOL_BOUNDARY' and offered['correction_ids']==[instruction['id']]
    assert len(session_reads._records(tmp_path)['turns']['T']['author_update_deliveries'])==2 # Legacy evidence preserved.


def _running_input(root, monkeypatch, payload=None):
    seed(root,monkeypatch);turn=updates.turn_scope(root,'p','T')
    child_hosts._update_child_execution(root,'WS-S',{'state':'RUNNING','turn_id':'T','session_id':'WS-S','project':'p','host':child_hosts._process_identity()})
    control=turn_control._queue_child_steering(root,turn,{'turn_id':'T','project':'p','text':'Short input','delivery_mode':'project_tool_boundary',**(payload or {})})
    return turn,control


def test_partial_context_complete_read_advances_once_and_late_old_read_preserves_newer_scope(tmp_path,monkeypatch):
    turn,first=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex'],'line_start':1,'line_end':2},'workspace_context':{'surface':'manuscript'}})
    (tmp_path/'manuscript/sec_two.tex').write_text('\\section{Consequence}\n'+'Concrete selected source. '*400+'\n')
    calls=[];original=turn_control._prepare_steering_input
    monkeypatch.setattr(turn_control,'_prepare_steering_input',lambda *args:(calls.append(args[2]['text']) or original(*args)))
    offer=updates.turn_input_offer(tmp_path,'p','T');item=offer['inputs'][0]
    assert item['text']=='Short input' and item['text_truncated'] is False and item['message_truncated'] is True
    assert item['context_delivery']['baseline_record_id'] is None
    assert session_reads._records(tmp_path)['turns']['T']['selection']['files']==['sec_one.tex']
    result=writing_tools.call(tmp_path,'p','work',{'operation':'conversation_history','payload':{'view':'controls','turn_id':'T','item_id':first['control_id']}},turn_id='T')
    complete=result['turn_input_read'];assert len(complete['message'])>updates._INPUT_MESSAGE_LIMIT
    assert 'Concrete selected source.' in complete['message'] and complete['context_read']['scope']=='CURRENT'
    assert complete['context_delivery']['baseline_record_id']
    assert session_reads._records(tmp_path)['turns']['T']['selection']['files']==['sec_two.tex']
    after=(tmp_path/'contract/talk.jsonl').read_bytes()
    assert updates.acknowledge_turn_input(tmp_path,'p','T',first['control_id'])['status']=='ALREADY_READ'
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==after and calls==['Short input']
    second=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Newer location','delivery_mode':'project_tool_boundary','selection':{'files':['sec_three.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000)
    assert updates.turn_input_offer(tmp_path,'p','T')['inputs'][0]['control_id']==second['control_id']
    newer=session_reads._records(tmp_path)['turns']['T']['context_basis_record_id']
    updates.acknowledge_turn_input(tmp_path,'p','T',first['control_id'])
    assert session_reads._records(tmp_path)['turns']['T']['context_basis_record_id']==newer
    assert session_reads._records(tmp_path)['turns']['T']['selection']['files']==['sec_three.tex']
    assert len(calls)==2


def test_late_first_complete_read_of_preview_never_retargets_newer_publication(tmp_path,monkeypatch):
    turn,first=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100)
    assert updates.turn_input_offer(tmp_path,'p','T')['inputs'][0]['message_truncated']
    second=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Newer','delivery_mode':'project_tool_boundary','selection':{'files':['sec_three.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);updates.turn_input_offer(tmp_path,'p','T')
    basis=session_reads._records(tmp_path)['turns']['T']['context_basis_record_id'];saved=(tmp_path/'contract/talk.jsonl').read_bytes()
    result=updates.acknowledge_turn_input(tmp_path,'p','T',first['control_id'])
    assert result['context_read']['scope']=='HISTORICAL' and result['context_read']['newer_scope_preserved']
    assert result['context_delivery']['baseline_record_id'] is None
    assert session_reads._records(tmp_path)['turns']['T']['context_basis_record_id']==basis
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==saved
    assert session_reads.child_execution(tmp_path,'WS-S')['last_control']['control_id']==second['control_id']


@pytest.mark.parametrize('crash',['before-baseline','after-baseline','after-delivery','after-publication'])
def test_prepared_receipt_recovers_crash_points_without_repreparation_or_duplicate_rows(tmp_path,monkeypatch,crash):
    turn,control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000)
    prepare=turn_control._prepare_steering_input;calls=[]
    monkeypatch.setattr(turn_control,'_prepare_steering_input',lambda *args:(calls.append(1) or prepare(*args)))
    bank=record_owner.bank;write=child_hosts._write_host;update=child_hosts._update_child_execution;failed=False
    def fault_bank(root,row,**kwargs):
        nonlocal failed
        kind=row['record']
        if not failed and crash=='before-baseline' and row['id'].startswith('CTX-INPUT-'):
            failed=True;raise OSError('controlled crash before baseline')
        result=bank(root,row,**kwargs)
        if not failed and (crash=='after-baseline' and row['id'].startswith('CTX-INPUT-') or crash=='after-delivery' and row['id'].startswith('WST-INPUT-')):
            failed=True;raise OSError('controlled crash after exact row')
        return result
    def fault_update(root,session,patch,**kwargs):
        nonlocal failed
        if not failed and crash=='after-publication' and (patch.get('last_control') or {}).get('state')=='PUBLISHED_AT_TOOL_BOUNDARY':
            failed=True;raise OSError('controlled crash after publication receipt')
        return update(root,session,patch,**kwargs)
    monkeypatch.setattr(record_owner,'bank',fault_bank);monkeypatch.setattr(child_hosts,'_update_child_execution',fault_update)
    if crash in {'after-publication','after-baseline','after-delivery'}:
        retained=updates.turn_input_offer(tmp_path,'p','T')
        assert retained['status']=='PUBLISHED_AT_TOOL_BOUNDARY' and retained['inputs'][0]['control_id']==control['control_id']
        if crash=='after-publication':assert retained['maintenance_warning']['stage']=='execution-observation'
    else:
        assert updates.turn_input_offer(tmp_path,'p','T')['status']=='INPUT_FAILED'
    receipt=session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING',item_id=control['control_id'])[0]
    assert receipt['state']==('FAILED' if crash=='before-baseline' else 'PUBLISHED_AT_TOOL_BOUNDARY')
    assert isinstance(receipt['preparation']['message'],dict) # Existing verified body custody, not another full prompt copy.
    monkeypatch.setattr(record_owner,'bank',bank);monkeypatch.setattr(child_hosts,'_update_child_execution',update)
    recovered=updates.turn_input_offer(tmp_path,'p','T')
    assert recovered is None
    assert updates.turn_input_offer(tmp_path,'p','T') is None and len(calls)==1
    rows=[__import__('json').loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    assert sum(row['id'].startswith('CTX-INPUT-') for row in rows)==(0 if crash=='before-baseline' else 1)
    assert sum(row['id'].startswith('WST-INPUT-') for row in rows)==(0 if crash=='before-baseline' else 1)
    assert session_reads.child_execution(tmp_path,'WS-S')['control_completed_sequence']==1


def test_same_invocation_recovery_refuses_an_unrelated_same_id_row(tmp_path,monkeypatch):
    _turn,control=_running_input(tmp_path,monkeypatch);bank=record_owner.bank
    def substitute(root,row,**kwargs):
        bank(root,{'record':'writing-steer','id':row['id'],'project':'another','turn_id':'OTHER','text':'Unrelated'})
        raise OSError('append differs')
    monkeypatch.setattr(record_owner,'bank',substitute)
    assert updates.turn_input_offer(tmp_path,'p','T')['status']=='INPUT_FAILED'
    assert updates.turn_input_offer(tmp_path,'p','T') is None
    assert session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING',item_id=control['control_id'])[0]['state']=='FAILED'


def test_preparation_and_custody_failure_publish_nothing_and_leave_original_input(tmp_path,monkeypatch):
    turn,control=_running_input(tmp_path,monkeypatch,{'text':'Retained '*100})
    saved=(tmp_path/'contract/talk.jsonl').read_bytes()
    monkeypatch.setattr(bodies,'store',lambda *args:(_ for _ in ()).throw(OSError('body unavailable')))
    assert updates.turn_input_offer(tmp_path,'p','T')['status']=='PREPARATION_FAILED'
    receipt=session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING',item_id=control['control_id'])[0]
    assert receipt['state']=='FAILED' and receipt['custody_degradation']['failed_attempts']
    assert receipt['payload']['text']=='Retained '*100 and (tmp_path/'contract/talk.jsonl').read_bytes()==saved
    assert turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Explicit next input','delivery_mode':'project_tool_boundary'})['sequence']==2


def test_concurrent_admission_and_publication_use_one_pending_slot_and_one_preparation(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    seed(tmp_path,monkeypatch);turn=updates.turn_scope(tmp_path,'p','T')
    child_hosts._update_child_execution(tmp_path,'WS-S',{'state':'RUNNING','turn_id':'T','session_id':'WS-S','project':'p','host':child_hosts._process_identity()})
    barrier=threading.Barrier(2)
    def admit():
        barrier.wait()
        try:return turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'One slot','delivery_mode':'project_tool_boundary'})
        except ValueError as error:return str(error)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:admit(),range(2)))
    assert len([row for row in results if isinstance(row,dict)])==1
    original=turn_control._prepare_steering_input;count=[]
    monkeypatch.setattr(turn_control,'_prepare_steering_input',lambda *args:(count.append(1) or original(*args)))
    with ThreadPoolExecutor(max_workers=2) as pool:published=list(pool.map(lambda _:updates.turn_input_offer(tmp_path,'p','T'),range(2)))
    assert sum(item is not None for item in published)==1 and len(count)==1


def test_successful_complete_read_survives_later_publication_maintenance_error(tmp_path,monkeypatch):
    _turn,control=_running_input(tmp_path,monkeypatch,{'text':'Whole retained input '*200})
    updates.turn_input_offer(tmp_path,'p','T')
    monkeypatch.setattr(updates,'turn_input_offer',lambda *args:(_ for _ in ()).throw(OSError('later publication unavailable')))
    result=writing_tools.call(tmp_path,'p','work',{'operation':'conversation_history','payload':{'view':'controls','turn_id':'T','item_id':control['control_id']}},turn_id='T')
    assert result['turn_input_read']['message']==('Whole retained input '*200).strip()
    assert result['update_delivery_unavailable']['stage']=='turn_input'


def test_selected_part_basis_matches_rich_fold_without_unrelated_history_body_reads(tmp_path,monkeypatch):
    turn,control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    record_owner.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-PARTS','project':'p','turn_id':'T','context_parts':{'known':'published-token'}})
    record_owner.bank(tmp_path,{'record':'writing-tool-read','id':'READ-EXTRA','project':'p','turn_id':'T','operation':'source','payload':{'files':['sec_one.tex']},'output_sha256':'sha256:'+'a'*64})
    record_owner.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-LATER','project':'p','turn_id':'T','selection':{'files':['sec_three.tex']}})
    rich=session_reads._records(tmp_path)['turns']['T']
    expected=(rich['context_parts'],rich['context_basis_record_id'])
    raw=record_owner._index._raw_indexed_record;reads=[]
    monkeypatch.setattr(record_owner._index,'_raw_indexed_record',lambda idx,meta:(reads.append(meta['id']) or raw(idx,meta)))
    monkeypatch.setattr(session_reads,'_records',lambda *args:pytest.fail('rich global fold'))
    current=updates._input_scope(tmp_path,'p',turn)
    assert (current['context_parts'],current['context_basis_record_id'])==expected
    assert reads==['CTX-LATER','CTX-PARTS']
    # Metadata index may scan its suffix, but no unrelated body is read/resolved.
    body=bodies.retain_leaves(tmp_path,{'message':'Unrelated body '*1000},('message',))['message']
    for number in range(200):record_owner.bank(tmp_path,{'record':'writing-turn','id':'OTHER-'+str(number),'project':'other','session_id':'WS-OTHER','dependencies':body})
    reads.clear();assert updates._input_scope(tmp_path,'p',turn)['context_parts']==expected[0]
    assert reads==['CTX-LATER','CTX-PARTS']
    assert updates.turn_input_offer(tmp_path,'p','T')['status']=='PUBLISHED_AT_TOOL_BOUNDARY'


@pytest.mark.parametrize('failure',['bank','custody'])
def test_successful_artifact_write_remains_success_when_following_input_publication_fails(tmp_path,monkeypatch,failure):
    from test_writing_operating import _project
    _project(tmp_path)
    record_owner.bank(tmp_path,{'record':'writing-session','id':'WS-S','project':'book'})
    record_owner.bank(tmp_path,{'record':'writing-turn','id':'T','project':'book','session_id':'WS-S'})
    turn=updates.turn_scope(tmp_path,'book','T')
    child_hosts._update_child_execution(tmp_path,'WS-S',{'state':'RUNNING','turn_id':'T','session_id':'WS-S','project':'book','host':child_hosts._process_identity()})
    text='Queued clarification '*200
    control=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'book','text':text,'delivery_mode':'project_tool_boundary'})
    if failure=='bank':monkeypatch.setattr(updates,'_bank_input_once',lambda *args,**kwargs:(_ for _ in ()).throw(OSError('controlled publication bank failure')))
    else:
        store=bodies.store
        class Store:
            def __init__(self,root):self.actual=store(root)
            def put(self,raw):
                if __import__('json').loads(raw)==text.strip():raise OSError('controlled prepared message custody failure')
                return self.actual.put(raw)
            def get(self,handle):return self.actual.get(handle)
        monkeypatch.setattr(bodies,'store',Store)
    result=writing_tools.call(tmp_path,'book','work',{'operation':'store_artifact','payload':{'path':'development/actual.md','before':None,'content':'Actual successful owner output.','reason':'Owned successful-effect fixture'}},turn_id='T')
    assert (tmp_path/result['path']).read_text()=='Actual successful owner output.'
    assert result['id'].startswith('ART-') and result['revision']==__import__('hashlib').sha256(b'Actual successful owner output.').hexdigest()
    assert result['saved']==result['path'] and result['owned_changes']['files']
    if failure=='bank':assert result['turn_input']['status']=='INPUT_FAILED'
    else:assert result['turn_input']['status']=='PREPARATION_FAILED'
    rows=[__import__('json').loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    assert sum(row['record']=='writing-artifact' for row in rows)==1
    assert not any(row['record']=='writing-tool-failure' for row in rows)
    assert session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING',item_id=control['control_id'])[0]['state']=='FAILED'


def test_reused_session_passes_historical_ordinal_without_replaying_old_turn_input(tmp_path,monkeypatch):
    turn,old=_running_input(tmp_path,monkeypatch)
    child_hosts._finish_child_execution(tmp_path,'WS-S','T','completed')
    record_owner.bank(tmp_path,{'record':'writing-turn','id':'T-NEW','project':'p','session_id':'WS-S'})
    child_hosts._begin_child_execution(tmp_path,'WS-S',{'state':'RUNNING','turn_id':'T-NEW','session_id':'WS-S','project':'p','host':child_hosts._process_identity()})
    new=turn_control._queue_child_steering(tmp_path,updates.turn_scope(tmp_path,'p','T-NEW'),{'turn_id':'T-NEW','project':'p','text':'Current input','delivery_mode':'project_tool_boundary'})
    assert new['sequence']==old['sequence']+1
    published=updates.turn_input_offer(tmp_path,'p','T-NEW')
    assert published['inputs'][0]['control_id']==new['control_id']
    assert session_reads._child_control_rows(tmp_path,'WS-S','T','FINISHED',item_id=old['control_id'])[0]['state']=='FAILED'
    rows=[__import__('json').loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    assert not any(row['record']=='writing-steer' and row['turn_id']=='T' for row in rows)


def test_full_publication_refuses_newer_real_context_landing_during_preparation(tmp_path,monkeypatch):
    _turn,control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);original=turn_control._prepare_steering_input
    def prepare(root,turn,payload):
        result=original(root,turn,payload)
        record_owner.bank(root,{'record':'writing-turn-context-baseline','id':'CTX-NEWER','project':'p','turn_id':'T','selection':{'files':['sec_three.tex']},'context_parts':{'newer':'published'}})
        return result
    monkeypatch.setattr(turn_control,'_prepare_steering_input',prepare)
    result=updates.turn_input_offer(tmp_path,'p','T')
    assert result['status']=='SCOPE_CHANGED' and 'inputs' not in result
    current=session_reads._records(tmp_path)['turns']['T']
    assert current['selection']['files']==['sec_three.tex'] and current['context_basis_record_id']=='CTX-NEWER'
    assert current['context_parts']=={'newer':'published'}
    assert session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING',item_id=control['control_id'])[0]['state']=='FAILED'


def test_full_recovery_never_restores_prepared_attention_over_newer_read(tmp_path,monkeypatch):
    _turn,control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);bank=record_owner.bank
    def crash(root,row,**kwargs):
        if row['id'].startswith('WST-INPUT-'):raise OSError('before delivery')
        return bank(root,row,**kwargs)
    monkeypatch.setattr(record_owner,'bank',crash)
    assert updates.turn_input_offer(tmp_path,'p','T')['status']=='INPUT_FAILED'
    monkeypatch.setattr(record_owner,'bank',bank)
    bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-NEWER','project':'p','turn_id':'T','selection':{'files':['sec_three.tex']},'context_parts':{'newer':'published'}})
    assert updates.turn_input_offer(tmp_path,'p','T') is None
    assert session_reads._records(tmp_path)['turns']['T']['context_basis_record_id']=='CTX-NEWER'


def test_baseline_writer_serializes_with_publication_without_holding_global_admission(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from laplace.work import project_work
    import threading
    _turn,_control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);entered=threading.Event();release=threading.Event();original=turn_control._prepare_steering_input
    def prepare(*args):entered.set();assert release.wait(2);return original(*args)
    def independent():
        with records_fold._LOCK:
            with project_work.dispatch_lock(tmp_path):return True
    monkeypatch.setattr(turn_control,'_prepare_steering_input',prepare)
    with ThreadPoolExecutor(max_workers=3) as pool:
        publication=pool.submit(updates.turn_input_offer,tmp_path,'p','T');assert entered.wait(2)
        ordinary=pool.submit(record_owner.bank,tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-ORDINARY','project':'p','turn_id':'T','selection':{'files':['sec_three.tex']},'context_parts':{'later':'published'}})
        assert pool.submit(independent).result(timeout=1) is True
        assert not ordinary.done();release.set();assert publication.result(timeout=3)['status']=='PUBLISHED_AT_TOOL_BOUNDARY';ordinary.result(timeout=3)
    current=session_reads._records(tmp_path)['turns']['T'];assert current['selection']['files']==['sec_three.tex'] and current['context_basis_record_id']=='CTX-ORDINARY'


def test_actual_project_updates_retains_constructed_input_after_sidecar_failure(tmp_path,monkeypatch):
    _turn,control=_running_input(tmp_path,monkeypatch);update=child_hosts._update_child_execution
    def fail(root,session,patch,**kwargs):
        if (patch.get('last_control') or {}).get('state')=='PUBLISHED_AT_TOOL_BOUNDARY':raise OSError('sidecar maintenance unavailable')
        return update(root,session,patch,**kwargs)
    monkeypatch.setattr(child_hosts,'_update_child_execution',fail)
    result=writing_tools._project_updates(tmp_path,'p','T',{'ok':True,'owned_result':'preserve this'}, {'operation':'source'})
    assert result['ok'] is True and result['owned_result']=='preserve this'
    assert result['turn_input']['inputs'][0]['control_id']==control['control_id']
    assert result['turn_input']['inputs'][0]['message']=='Short input'
    assert result['turn_input']['maintenance_warning']['stage']=='execution-observation'
    assert updates.turn_input_offer(tmp_path,'p','T') is None # No duplicate context/message replay.


def test_unconfirmed_publication_never_leaves_undelivered_part_tokens_held(tmp_path,monkeypatch):
    _turn,control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);write=child_hosts._write_host
    def refuse(path,value):
        if value.get('state')=='PUBLISHED_AT_TOOL_BOUNDARY':raise OSError('publication record unavailable')
        return write(path,value)
    monkeypatch.setattr(child_hosts,'_write_host',refuse)
    result=updates.turn_input_offer(tmp_path,'p','T')
    assert result['status']=='PUBLICATION_UNCONFIRMED' and 'inputs' not in result
    current=session_reads._records(tmp_path)['turns']['T'];assert current['context_parts']=={}
    assert current['context_basis_record_id']=='CTX-INPUT-INVALIDATED-'+control['control_id']
    assert updates.turn_input_offer(tmp_path,'p','T') is None


def test_append_landed_then_raise_still_returns_constructed_input_before_turn_ends(tmp_path,monkeypatch):
    _turn,control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);bank=record_owner.bank
    def after(root,row,**kwargs):
        result=bank(root,row,**kwargs)
        if row['id'].startswith('CTX-INPUT-'):raise OSError('append landed, adapter failed')
        return result
    monkeypatch.setattr(record_owner,'bank',after)
    result=writing_tools._project_updates(tmp_path,'p','T',{'ok':True,'actual_result':'retained'}, {'operation':'source'})
    assert result['actual_result']=='retained' and result['turn_input']['inputs'][0]['control_id']==control['control_id']
    monkeypatch.setattr(record_owner,'bank',bank);child_hosts._finish_child_execution(tmp_path,'WS-S','T','completed')
    assert session_reads._child_control_rows(tmp_path,'WS-S','T','FINISHED',item_id=control['control_id'])[0]['state']=='PUBLISHED_AT_TOOL_BOUNDARY'


@pytest.mark.parametrize('newer',[False,True])
@pytest.mark.parametrize('prior_parts',[{}, {'prior':'exact-delivered-token'}])
def test_real_process_death_before_publication_terminalizes_without_undelivered_attention(tmp_path,monkeypatch,newer,prior_parts):
    _turn,control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    if prior_parts:record_owner.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-PRIOR','project':'p','turn_id':'T','context_parts':prior_parts})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);bank=record_owner.bank
    class Death(BaseException):pass
    def dead(root,row,**kwargs):
        result=bank(root,row,**kwargs)
        if row['id'].startswith('CTX-INPUT-'):raise Death()
        return result
    monkeypatch.setattr(record_owner,'bank',dead)
    with pytest.raises(Death):updates.turn_input_offer(tmp_path,'p','T')
    monkeypatch.setattr(record_owner,'bank',bank)
    if newer:bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-NEWER','turn_id':'T','project':'p','selection':{'files':['sec_three.tex']},'context_parts':{'newer':'provided'}})
    child_hosts._finish_child_execution(tmp_path,'WS-S','T','completed')
    current=session_reads._records(tmp_path)['turns']['T']
    assert current['selection']['files']==(['sec_three.tex'] if newer else ['sec_one.tex'])
    assert current['context_parts']==({'newer':'provided'} if newer else prior_parts)
    if not newer:
        rows=[__import__('json').loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
        restored=next(row for row in rows if row.get('id')=='CTX-INPUT-INVALIDATED-'+control['control_id'])
        assert 'context_parts' in restored and restored['context_parts']==prior_parts
        delivery=turn_context.without_already_delivered([{'key':'new','token':'new-token','text':'Fresh source context','read':{'operation':'source','payload':{}}}],current['context_parts'])
        assert delivery['withheld_chars']==0 and 'Fresh source context' in delivery['prompt']
    assert session_reads._child_control_rows(tmp_path,'WS-S','T','FINISHED',item_id=control['control_id'])[0]['state']=='UNCONFIRMED'
    assert updates.turn_input_offer(tmp_path,'p','T') is None


def test_definite_prepublication_failure_is_terminal_and_only_explicit_new_admission_progresses(tmp_path,monkeypatch):
    turn,control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);bank=record_owner.bank;prepare=turn_control._prepare_steering_input;calls=[]
    monkeypatch.setattr(turn_control,'_prepare_steering_input',lambda *args:(calls.append(1) or prepare(*args)))
    def fail(root,row,**kwargs):
        if row['id'].startswith('WST-INPUT-'):raise OSError('delivery row unavailable')
        return bank(root,row,**kwargs)
    monkeypatch.setattr(record_owner,'bank',fail)
    result=writing_tools._project_updates(tmp_path,'p','T',{'ok':True,'actual_result':'retained'}, {'operation':'source'})
    assert result['actual_result']=='retained' and result['turn_input']['status']=='INPUT_FAILED'
    current=session_reads._records(tmp_path)['turns']['T'];assert current['selection']['files']==['sec_one.tex'] and current['context_parts']=={}
    saved=(tmp_path/'contract/talk.jsonl').read_bytes()
    for _ in range(3):assert updates.turn_input_offer(tmp_path,'p','T') is None
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==saved and len(calls)==1
    second=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Explicit second','selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'},'delivery_mode':'project_tool_boundary'})
    assert updates.turn_input_offer(tmp_path,'p','T')['status']=='INPUT_FAILED'
    monkeypatch.setattr(record_owner,'bank',bank)
    assert updates.turn_input_offer(tmp_path,'p','T') is None
    third=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Explicit third','selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'},'delivery_mode':'project_tool_boundary'})
    published=updates.turn_input_offer(tmp_path,'p','T');assert published['status']=='PUBLISHED_AT_TOOL_BOUNDARY'
    assert published['inputs'][0]['control_id']==third['control_id'] and len(calls)==3
    assert session_reads._records(tmp_path)['turns']['T']['context_basis_record_id']==published['inputs'][0]['context_delivery']['baseline_record_id']
    assert session_reads._records(tmp_path)['turns']['T']['selection']['files']==['sec_two.tex']
    rows=[__import__('json').loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    ids=[row['id'] for row in rows];assert len(ids)==len(set(ids))
    assert sum(row['record']=='writing-steer' for row in rows)==1
    assert not any('RESUMED' in row['id'] for row in rows)


@pytest.mark.parametrize('newer',[False,True])
@pytest.mark.parametrize('damage',['snapshot','message-body','request','missing-preparation'])
def test_terminal_restoration_verifies_snapshot_request_and_body_without_fabricating_scope(tmp_path,monkeypatch,newer,damage):
    _turn,control=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);bank=record_owner.bank
    class Death(BaseException):pass
    def dead(root,row,**kwargs):
        result=bank(root,row,**kwargs)
        if row['id'].startswith('CTX-INPUT-'):raise Death()
        return result
    monkeypatch.setattr(record_owner,'bank',dead)
    with pytest.raises(Death):updates.turn_input_offer(tmp_path,'p','T')
    monkeypatch.setattr(record_owner,'bank',bank)
    request=next(child_hosts._steer_mailbox(tmp_path,'WS-S').glob('*-'+control['control_id']+'.request.json'))
    ack=request.with_name(request.name.replace('.request.json','.ack.json'));receipt=child_hosts._read_host(ack)
    if damage=='snapshot':
        receipt['preparation']['previous_context']['selection']={'files':['sec_three.tex']};child_hosts._write_host(ack,receipt)
    elif damage=='message-body':
        handle=receipt['preparation']['message']['content_handle'].removeprefix('sha256:')
        files=[p for p in (tmp_path/'contract/writing_bodies').rglob('*') if p.is_file() and p.name==handle]
        assert len(files)==1;files[0].write_bytes(b'corrupt body')
    elif damage=='request':
        command=child_hosts._read_host(request);command['payload']['text']='Changed request';child_hosts._write_host(request,command)
    else:
        receipt.pop('preparation');child_hosts._write_host(ack,receipt)
    if newer:bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-NEWER','project':'p','turn_id':'T','selection':{'files':['sec_three.tex']},'context_parts':{'newer':'provided'}})
    child_hosts._finish_child_execution(tmp_path,'WS-S','T','completed')
    current=session_reads._records(tmp_path)['turns']['T']
    assert current['selection']==({'files':['sec_three.tex']} if newer else None)
    assert current['context_parts']==({'newer':'provided'} if newer else {})
    if not newer:
        rows=[__import__('json').loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
        restored=next(row for row in rows if row.get('id')=='CTX-INPUT-INVALIDATED-'+control['control_id'])
        assert 'context_parts' in restored and restored['context_parts']=={}
    observed=session_reads._child_control_rows(tmp_path,'WS-S','T','FINISHED',item_id=control['control_id'])[0]
    assert observed['state']=='UNCONFIRMED' and observed.get('context_invalidation_unproved')
    saved=(tmp_path/'contract/talk.jsonl').read_bytes();child_hosts._finish_child_execution(tmp_path,'WS-S','T','completed')
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==saved


def test_terminal_uncertain_publication_releases_slot_and_next_explicit_input_publishes(tmp_path,monkeypatch):
    turn,first=_running_input(tmp_path,monkeypatch,{'selection':{'files':['sec_two.tex']},'workspace_context':{'surface':'manuscript'}})
    monkeypatch.setattr(updates,'_INPUT_MESSAGE_LIMIT',100_000);write=child_hosts._write_host
    def fail(path,value):
        if value.get('state')=='PUBLISHED_AT_TOOL_BOUNDARY':raise OSError('publication receipt uncertain')
        return write(path,value)
    monkeypatch.setattr(child_hosts,'_write_host',fail)
    assert updates.turn_input_offer(tmp_path,'p','T')['status']=='PUBLICATION_UNCONFIRMED'
    old=session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING',item_id=first['control_id'])[0]
    assert old['terminal'] is True and old['state']=='PUBLICATION_UNCONFIRMED'
    monkeypatch.setattr(child_hosts,'_write_host',write)
    second=turn_control._queue_child_steering(tmp_path,turn,{'turn_id':'T','project':'p','text':'Explicit next input','selection':{'files':['sec_three.tex']},'workspace_context':{'surface':'manuscript'},'delivery_mode':'project_tool_boundary'})
    result=updates.turn_input_offer(tmp_path,'p','T')
    assert result['inputs'][0]['control_id']==second['control_id'] and second['sequence']==first['sequence']+1
    assert session_reads.child_execution(tmp_path,'WS-S')['control_completed_sequence']==second['sequence']
    assert session_reads._records(tmp_path)['turns']['T']['selection']['files']==['sec_three.tex']
    assert session_reads._child_control_rows(tmp_path,'WS-S','T','RUNNING',item_id=first['control_id'])[0]['state']=='PUBLICATION_UNCONFIRMED'
    assert updates.turn_input_offer(tmp_path,'p','T') is None
