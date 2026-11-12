"""Agent-discoverable navigation and exact terminal candidate carrier joins."""
import json
import pytest
from laplace.writing import operating
from laplace.native import tools, declarations, verbs
from laplace.manuscript import proposal_navigation as nav
from laplace.writing import reads
from laplace.writing import records as writing_records
from laplace.writing import turn_execution
from laplace.writing import session_reads
from laplace.writing import turn_admission
from laplace.writing.records import _fold as records_fold
from laplace.manuscript import proposal_currentness
from laplace.writing import provider as writing_provider
from test_proposal_lifecycle import setup

@pytest.fixture(autouse=True)
def clear():
    from laplace.work import author_history_metrics
    records_fold._CACHE.clear();author_history_metrics._INDEXES.clear()
    yield
    records_fold._CACHE.clear();author_history_metrics._INDEXES.clear()


def test_same_read_home_is_bound_and_usable_in_kernel_compact_and_help(tmp_path):
    md,tid,edits,context=setup(tmp_path)
    brief=operating.build('fixture','revise',tmp_path)
    kernel=json.loads(operating.kernel(brief).split('\n',1)[1])
    home=kernel['capability_guidance']['read_homes'][0]
    assert home['native_request']['target']=='fixture'
    help=tools.execute(tmp_path,'fixture','revise','help',{'concept':home['concept']})
    assert help['read_navigation']['native_request']==home['native_request']
    bare=tools.execute(tmp_path,'fixture','revise','help',{})
    concept=next(x for x in bare['concepts'] if x['concept']==home['concept'])
    assert concept['read_navigation']['native_request']==home['native_request']
    compact=operating.tool_contract()['read_homes'][0]
    assert compact['native_request']['concept']==home['concept']
    assert 'authoring/proposals' not in reads.READS|reads.WRITES
    assert tools.call(tmp_path,'fixture','revise',home['native_request'])['owner_response']['proposals']
    assert operating.orientation_delta({'capability_guidance_revision':'old'},brief)['guidance']['capability_guidance']==brief['capability_guidance']


def test_native_proof_only_for_existing_coupled_http_reads():
    assert verbs.native_example('authoring/proposals',{},project='fixture')['available']
    assert verbs.native_example('authoring/proposal-preview',{'id':'WT-returned'},project='fixture')['available']
    assert not verbs.native_example('authoring/providers',{},project='fixture')['available']
    assert not verbs.native_example('authoring/proposal-decision',{'id':'WT-returned'},project='fixture')['available']


def bank_terminal(root,tid,candidate,answer='New terminal answer.'):
    emitted={**candidate,'answer':answer};raw=json.dumps(emitted,ensure_ascii=False)
    return writing_records.bank(root,{'record':'writing-reply','id':'WR-terminal','turn_id':tid,'project':'fixture','provider':'codex','by':'agent','text':raw,'status':'completed','proposal':emitted}),emitted,raw


@pytest.mark.parametrize('covered',[1,2])
def test_backend_terminal_summary_preserves_exact_application_coverage_without_new_candidate(tmp_path,covered):
    md,tid,edits,context=setup(tmp_path)
    turn=session_reads._records(tmp_path)['turns'][tid]
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-active','turn_id':tid,
        'project':'fixture','proposal':next(iter(turn['proposal_versions'].values()))})
    turn=session_reads._records(tmp_path)['turns'][tid];version=turn['pending_proposal_version']
    candidate=turn['proposal_versions'][version]
    from laplace.manuscript.manuscript_proposals import edit_id
    writing_records.bank(tmp_path,{'record':'writing-application','id':'WA-owned','turn_id':tid,
        'project':'fixture','candidate_version':version,'complete':True,
        'candidate_edit_ids':[edit_id(e) for e in candidate['edits'][:covered]]})
    writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-after-apply',
        'turn_id':tid,'project':'fixture','context_id':'CTX-later','dependencies':{}})
    turn=session_reads._records(tmp_path)['turns'][tid]
    result=turn_execution._finalize_provider_proposal(tmp_path,'fixture',turn,
        {'status':'completed','text':'Completed the work. Edits: []','proposal':None})
    assert result['proposal'] is None and 'proposal_validation' not in result
    carrier=result['proposal_carrier']
    assert carrier['candidate_version']==version and carrier['application_ids']==['WA-owned']
    assert carrier['complete']==(covered==2)
    assert len(carrier['covered_edit_ids'])==covered and len(carrier['remaining_edit_ids'])==2-covered
    writing_records.bank(tmp_path,{'record':'writing-reply','id':'WR-summary','turn_id':tid,'project':'fixture',**result})
    now=session_reads._records(tmp_path)['turns'][tid]
    assert len(now['proposal_versions'])==1 and now['pending_proposal_version']==version
    queue=nav.read(tmp_path,'fixture',{})['proposals']
    assert (queue[0]['edit_count'] if queue else 0)==2-covered
    assert now['reply']['text']=='Completed the work. Edits: []'
    from laplace.work.author_history_metrics import index
    assert index(tmp_path).by_id['WR-summary'][0]['proposal_carrier']==carrier


def test_completed_candidate_carrier_is_not_labelled_as_missing_terminal_reply(tmp_path):
 md,tid,edits,context=setup(tmp_path)
 turn=session_reads._records(tmp_path)['turns'][tid]
 writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-live-pilot','turn_id':tid,
     'project':'fixture','proposal':next(iter(turn['proposal_versions'].values()))})
 turn=session_reads._records(tmp_path)['turns'][tid]
 result=turn_execution._finalize_provider_proposal(tmp_path,'fixture',turn,
     {'status':'completed','text':'One saved proposal; no additional final edits.','proposal':None})
 assert result['proposal_carrier']['kind']=='terminal-candidate-summary'
 writing_records.bank(tmp_path,{'record':'writing-reply','id':'WR-pilot-complete','turn_id':tid,'project':'fixture',**result})
 records=session_reads._records(tmp_path);saved=records['turns'][tid]
 assert proposal_currentness.proposal_view(saved,records=records)['proposal_state']=='ready'
 assert session_reads._session_turn_summary(saved,records)['proposal_state']=='ready'
 assert nav.read(tmp_path,'fixture',{})['proposals'][0]['edit_count']==2
 without_reply={**saved,'reply':None}
 assert proposal_currentness.proposal_view(without_reply,records=None)['proposal_state']=='saved-without-final-reply'


def test_explicit_fresh_proposal_never_borrows_application_from_effect_hash(tmp_path):
    md,tid,edits,context=setup(tmp_path)
    turn=session_reads._records(tmp_path)['turns'][tid]
    writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-active','turn_id':tid,
        'project':'fixture','proposal':next(iter(turn['proposal_versions'].values()))})
    turn=session_reads._records(tmp_path)['turns'][tid];version=turn['pending_proposal_version']
    candidate=turn['proposal_versions'][version]
    writing_records.bank(tmp_path,{'record':'writing-application','id':'WA-old','turn_id':tid,
        'project':'fixture','candidate_version':version,'candidate_edit_ids':[],
        'complete':True,'edit_sha256':records_fold._proposal_effect_digest(candidate)})
    writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-fresh',
        'turn_id':tid,'project':'fixture','context_id':'CTX-fresh','dependencies':{}})
    turn=session_reads._records(tmp_path)['turns'][tid]
    result=turn_execution._finalize_provider_proposal(tmp_path,'fixture',turn,
        {'status':'completed','text':'A genuinely new proposal.','proposal':candidate})
    assert 'proposal_carrier' not in result and result['proposal_validation']['status']!='APPLIED'
    stored=writing_records.bank(tmp_path,{'record':'writing-reply','id':'WR-fresh','turn_id':tid,'project':'fixture',**result})
    assert stored['proposal_instance_version']!=version
    now=session_reads._records(tmp_path)['turns'][tid]
    assert proposal_currentness.proposal_view(now,records=session_reads._records(tmp_path))['proposal_state']!='applied'


def test_terminal_repetition_preserves_actor_raw_answer_history_and_one_candidate(tmp_path):
    md,tid,edits,context=setup(tmp_path)
    before=(md/'main.tex').read_bytes()
    turn=session_reads._records(tmp_path)['turns'][tid]
    version=list(turn['proposal_versions'])[0];candidate=turn['proposal_versions'][version]
    original_rows=(tmp_path/'contract/talk.jsonl').read_bytes()
    stored,emitted,raw=bank_terminal(tmp_path,tid,candidate)
    now=session_reads._records(tmp_path)['turns'][tid]
    assert set(now['proposal_versions'])=={version}
    assert now['reply']['text']==raw and now['reply']['by']=='agent'
    assert now['reply']['display_text']==emitted['answer']
    assert now['reply']['proposal_carrier']['candidate_version']==version
    assert now['reply']['proposal_carrier']['emitted_content_sha256']==records_fold._proposal_digest(emitted)
    assert {**now['reply']['proposal'],'answer':now['reply']['display_text']}==emitted
    assert now['proposal_versions'][version]==candidate
    assert (tmp_path/'contract/talk.jsonl').read_bytes().startswith(original_rows)
    assert len(nav.read(tmp_path,'fixture',{})['proposals'])==1
    summary=session_reads._session_turn_summary(now,session_reads._records(tmp_path))
    assert summary['reply']['display_text']==emitted['answer']
    assert summary['reply']['proposal_carrier']==now['reply']['proposal_carrier']
    assert (md/'main.tex').read_bytes()==before


@pytest.mark.parametrize('change',['reason','anchor','develops','evidence','basis','source_effect'])
def test_distinct_semantics_or_basis_remain_distinct(tmp_path,change):
    md,tid,edits,context=setup(tmp_path)
    turn=session_reads._records(tmp_path)['turns'][tid]
    candidate=json.loads(json.dumps(next(iter(turn['proposal_versions'].values()))))
    if change=='basis':
        writing_records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX-new-basis','turn_id':tid,'project':'fixture','context_id':'CTX-distinct','dependencies':{},'document':turn['document']})
    else:
        edit=candidate['edits'][0]
        if change=='reason':edit['reason']='Different authored reason.'
        elif change=='anchor':edit['source_anchor']['unique']=False
        elif change=='develops':edit['develops']=[{'id':'claim','content_revision':'different'}]
        elif change=='evidence':edit['evidence_refs']=[{'id':'result','revision':'different'}]
        else:edit['after']='Different proposed source.'
    bank_terminal(tmp_path,tid,candidate)
    assert len(session_reads._records(tmp_path)['turns'][tid]['proposal_versions'])==2


def test_explicit_proposal_and_terminal_carrier_create_one_active_copy(tmp_path):
    from test_writing_controller import _import_project,_seed_revision
    from laplace.pipeline import authoring
    from test_proposal_lifecycle import RAW
    from laplace.manuscript import proposal_preflight
    md,_=_import_project(tmp_path,files={'main.tex':RAW})
    context=authoring.build_context('fixture',{'files':['main.tex']},repo_root=tmp_path)
    tid=_seed_revision(tmp_path,'fixture',[],selection={'files':['main.tex']},context=context)
    payload={'answer':'Saved through the explicit proposal owner.','edits':[{'file':'main.tex','line_start':3,'line_end':3,'before':'First premise.','after':'A revised premise.','reason':'Clarify.','source_anchor':proposal_preflight.source_anchor(RAW,3,3)}]}
    result=tools.execute(tmp_path,'fixture','revise','propose_revision',payload,turn_id=tid)
    state=session_reads._records(tmp_path)['turns'][tid]
    candidate=state['proposal_versions'][result['proposal_version']]
    stored,emitted,raw=bank_terminal(tmp_path,tid,candidate)
    current=nav.read(tmp_path,'fixture',{})
    assert len(current['proposals'])==1
    assert current['proposals'][0]['proposal_version']==result['proposal_version']
    now=session_reads._records(tmp_path)['turns'][tid]
    assert now['reply']['text']==raw and now['reply']['display_text']==emitted['answer']
    assert now['reply']['proposal_carrier']['candidate_record_id']==result['proposal_record_id']
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    assert any(row.get('id')==result['proposal_record_id'] for row in rows)
    assert any(row.get('id')=='WR-terminal' for row in rows)


def test_matching_candidate_in_other_turn_cannot_be_a_carrier(tmp_path):
    md,tid,edits,context=setup(tmp_path)
    first=session_reads._records(tmp_path)['turns'][tid]
    candidate=next(iter(first['proposal_versions'].values()))
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-other','project':'fixture','session_id':'WS-other',
                           'mode':'revise','context_id':first['context_id'],'dependencies':first['dependencies'],
                           'document':first['document'],'selection':first['selection']})
    bank_terminal(tmp_path,'WT-other',candidate)
    other=session_reads._records(tmp_path)['turns']['WT-other']
    assert not other['reply'].get('proposal_carrier')


def test_unsealed_legacy_candidate_is_not_retroactively_collapsed(tmp_path):
    md,tid,edits,context=setup(tmp_path)
    candidate=next(iter(session_reads._records(tmp_path)['turns'][tid]['proposal_versions'].values()))
    path=tmp_path/'contract/talk.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        if row.get('turn_id')==tid and row.get('proposal'):
            row.pop('proposal_basis',None);row.pop('proposal_instance_version',None)
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    records_fold._CACHE.clear()
    bank_terminal(tmp_path,tid,candidate)
    now=session_reads._records(tmp_path)['turns'][tid]
    assert not now['reply'].get('proposal_carrier')
    assert len(now['proposal_versions'])==2


def test_terminal_answer_same_in_summary_agent_history_and_binding_reseed(tmp_path,monkeypatch):
    from test_writing_operating import _wait
    md,tid,edits,context=setup(tmp_path)
    old=session_reads._records(tmp_path)['turns'][tid]
    candidate=next(iter(old['proposal_versions'].values()))
    stored,emitted,raw=bank_terminal(tmp_path,tid,candidate,answer='New terminal presentation, preserved everywhere.')
    old=session_reads._records(tmp_path)['turns'][tid]
    assert session_reads._session_turn_summary(old,session_reads._records(tmp_path))['reply']['display_text']==emitted['answer']
    before_brief=operating.build('fixture','work',tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-binding','id':'WB-answer-reseed','session_id':old['session_id'],
        'native_id':'old-native','tool_contract_digest':before_brief['tool_contract_digest'],
        'native_registration_signature':before_brief['native_registration_signature']})
    captured=[]
    class Provider:
        def __init__(self,cwd,provider,model,effort,native_id,event,mode,**kwargs):
            self.native_id=native_id;self.event=event
        def run(self,prompt):
            captured.append(prompt)
            self.event({'type':'session','native_id':'replacement','model':'actual','provider':'codex'})
            return {'status':'completed','text':'A later ordinary response.'}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)
    started=turn_admission.start_turn(tmp_path,{'project':'fixture','session_id':old['session_id'],
        'text':'Continue after the connection update.','mode':'work','request_id':'answer-reseed'})
    current=_wait(tmp_path,started)
    assert current['native_contract_migration']
    block=captured[-1].split('SAVED CONVERSATION CONTEXT AFTER A CONNECTION UPDATE\n',1)[1]
    assert emitted['answer'] in block
    assert '\"answer\": \"proposal\"' not in block
    history=tools.execute(tmp_path,'fixture','work','conversation_history',{'limit':6},turn_id=current['id'])
    assert next(row for row in history['turns'] if row['id']==tid)['answer']==emitted['answer']
    exact=session_reads._records(tmp_path)['turns'][tid]['reply']
    assert exact['text']==raw and exact['proposal']['answer']==candidate['answer']


@pytest.mark.parametrize('applied',[False,True])
def test_session_summary_links_exact_saved_candidate_including_terminal_applied(tmp_path,applied):
    md,tid,edits,context=setup(tmp_path)
    records=session_reads._records(tmp_path);turn=records['turns'][tid]
    if applied:
        writing_records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-summary-pin','turn_id':tid,
            'project':'fixture','proposal':turn['reply']['proposal']})
        turn=session_reads._records(tmp_path)['turns'][tid]
    version=turn['pending_proposal_version'] if applied else turn['reply']['proposal_instance_version']
    basis=turn['proposal_bases'][version]
    if applied:
        from laplace.manuscript.manuscript_proposals import edit_id
        writing_records.bank(tmp_path,{'record':'writing-application','id':'WA-summary','turn_id':tid,'project':'fixture',
            'candidate_version':version,'candidate_edit_ids':[edit_id(e) for e in edits],'complete':True})
        turn=session_reads._records(tmp_path)['turns'][tid]
        terminal=turn_execution._finalize_provider_proposal(tmp_path,'fixture',turn,{'status':'completed','text':'Complete','proposal':None})
        writing_records.bank(tmp_path,{'record':'writing-reply','id':'WR-summary-pin','turn_id':tid,'project':'fixture',**terminal})
    records=session_reads._records(tmp_path);summary=session_reads._session_turn_summary(records['turns'][tid],records)
    assert summary['proposal_version']==version and summary['proposal_turn_id']==tid
    request=summary['proposal_read_handle']['native_request']
    assert request['target']=='fixture::'+tid
    assert request['payload']=={'id':tid,'record_id':basis['record_id'],'proposal_version':version,'view':'summary'}
    selected=nav.read(tmp_path,'fixture',request['payload'])
    assert selected['proposal_version']==version and selected['read_handle']==summary['proposal_read_handle']


@pytest.mark.parametrize('defect',['missing-record','ambiguous','contradictory-carrier'])
def test_session_summary_never_invents_legacy_or_conflicting_candidate_pin(tmp_path,defect):
    import copy
    _,tid,_,_=setup(tmp_path);records=session_reads._records(tmp_path)
    turn=copy.deepcopy(records['turns'][tid]);version=turn['reply']['proposal_instance_version']
    basis=turn['proposal_bases'][version]
    if defect=='missing-record':basis.pop('record_id',None)
    elif defect=='ambiguous':basis['ambiguous_legacy_basis']=True
    else:turn['reply']['proposal_carrier']={'candidate_version':'other','candidate_record_id':basis['record_id']}
    summary=session_reads._session_turn_summary(turn,records)
    assert summary['proposal_version'] is None and summary['proposal_read_handle'] is None and summary['proposal_turn_id'] is None
