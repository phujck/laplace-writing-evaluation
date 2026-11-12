"""Finite comment reviews through the existing Work/event/turn owners.

Only the provider boundary is deterministic. Origin, policy, reservation, session,
turn custody, terminal hook and qualified result handles are ordinary owners.
"""
import copy
import json
import os
import time
from pathlib import Path

import pytest

from laplace.pipeline import authoring
from laplace.work import feedback_route as route, project_work as work, work_delivery as delivery
from laplace.writing import provider, session_reads, turn_admission, turn_jobs, records
from test_feedback_origin import fixture as origin_fixture
from test_writing_dispatch import _StubTurn, CATALOGUE

HUMAN={'origin':'human'}


def retain(name,value):
    home=os.environ.get('FEEDBACK_ROUTE_EVIDENCE')
    if home:
        path=Path(home);path.mkdir(parents=True,exist_ok=True)
        (path/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2))


@pytest.fixture
def prepared(tmp_path,monkeypatch):
    import runtime_guard
    runtime_guard.arm(monkeypatch)
    payload=origin_fixture(tmp_path)
    voice=tmp_path/'profiles/voice/gerard-technical-v1.md';voice.parent.mkdir(parents=True)
    voice.write_text('Synthetic public fixture voice. Be concrete.\n')
    monkeypatch.setenv('LAPLACE_STATE',str(tmp_path/'state'))
    monkeypatch.setattr(provider,'capabilities',lambda *a,**k:copy.deepcopy(CATALOGUE))
    monkeypatch.setattr(provider,'WritingTurn',_StubTurn)
    monkeypatch.setattr(_StubTurn,'interrupt',lambda self:None,raising=False)
    monkeypatch.setattr(provider,'context_window_advertised',lambda *a,**k:None)
    monkeypatch.setattr(session_reads,'context_window_advertised',lambda *a,**k:None)
    monkeypatch.setattr(turn_jobs,'_CHILD_HOST',True)
    _StubTurn.instructions={};_StubTurn.observed=[]
    work.task('p',{'id':'review-claim','title':'Review this claim','goal':'Check assumptions and numerical boundary.',
        'review_obligations':[{'id':key,'label':label,'scope':'other','inputs':['p/manuscript/main.tex']}
                              for key,label in [('assumptions','Assumptions'),('boundary','Boundary')]]},tmp_path)
    pairs=[]
    for key in ('assumptions','boundary'):
        binding=delivery.bind(tmp_path,'p',{'work_id':'review-claim','expected_work_revision':guard(tmp_path),
            'kind':'app-owned','provider':'claude','model':'haiku','effort':'low','label':key},HUMAN)['binding']
        pairs.append({'obligation_id':key,'recipient_binding_id':binding['id']})
    policy={'mode':'manual','recipients':pairs,'limits':{'max_new_admissions':2,'max_attempts':2,'admission_seconds':60,'runtime_seconds':10}}
    saved=authoring.bank_correction('p',payload,tmp_path)
    return tmp_path,payload,saved,policy


def guard(root):return work._task_revision(work._tasks('p',root)['review-claim'])


LINE='A numerical claim requires a stated assumption.'


def writer_wire(root,label,request):
    """The EXISTING human approval owner (workflow_progression.approve_effect via work_delivery workflow-bind): exact current
    Work revision, stable request id, app-owned admission, approved provider/model/effort and a finite expiry."""
    return {'action':'workflow-bind','work_id':'review-claim','expected_work_revision':guard(root),'request_id':request,
            'kind':'app-owned','effect':'proposal-writer','provider':'claude','model':'haiku','effort':'low','label':label,'lifetime_s':600}


@pytest.fixture
def writer_prepared(prepared):
    """The CORRECT author route for a manuscript proposal: the human approves app-owned proposal writers through the existing
    workflow-bind owner. The independent review bindings of `prepared` stay read-only and are not relabelled or reused."""
    root,payload,saved,policy=prepared
    pairs=[]
    for key in ('assumptions','boundary'):
        approved=delivery.handle(root,'p',writer_wire(root,'writer-'+key,'approve-writer-'+key),HUMAN)
        assert approved['effect']=='approved' and approved['binding']['effect']=='proposal-writer' and approved['binding']['expires_at']
        pairs.append({'obligation_id':key,'recipient_binding_id':approved['binding']['id']})
    return root,payload,saved,{**policy,'recipients':pairs}


def http_apply(root,turn_id,version):
    """The actual human HTTP door POST /authoring/apply with the exact owner proposal identity."""
    from laplace.web import authoring_http
    code,_,raw=authoring_http.handle(root,'/authoring/apply',{},'POST',json.dumps({'project':'p','turn_id':turn_id,'proposal_version':version}).encode())
    return code,(json.loads(raw) if raw else {})


def test_actual_route_edges_join_no_proposal_explicitly_and_keep_disposition_separate(prepared):
    """Comment Save -> qualified origin -> admitted producers (stub provider returns no proposal): every admitted edge
    carries the owner join with an explicit NOT_PRODUCED and its exact saved-turn read, never success; the route keeps
    the comment disposition and the Work review reads as separate owner facts."""
    root,payload,saved,policy=prepared
    result=route.handle(root,'p',submit_payload(root,saved,policy,request='route-join-public-1'),HUMAN)
    complete=wait_result(root,result['route_id'])
    for edge in complete['edges']:
        tid=edge['event']['admitted']['turn_id'];join=edge['revision']
        assert join['schema_version']==route.JOIN_SCHEMA and join['state']=='NOT_PRODUCED' and join['turn_id']==tid
        assert join['links']=={'produced':False,'applied':False,'built':False,'incomplete_applications':0,'unattributed_applications':0}
        assert join['next_read']==join['turn_read'] and 'view=turn' in join['turn_read']['http']['url']
        assert 'never' in join['meaning'] and not join['proposals']
    summary=complete['revision']
    assert [row['state'] for row in summary['edges']]==['NOT_PRODUCED']*len(complete['edges'])
    assert summary['disposition']['comment_owner']=='correction_origin'
    assert summary['disposition']['review_reads']==[edge['review_read'] for edge in complete['edges']]
    assert 'never implies' in summary['disposition']['meaning']
    retain('revision-join-route',{'aggregate':complete})


def test_revision_join_proposal_application_effect_and_matching_build_with_adverse_controls(tmp_path):
    """An actual owner proposal turn -> exact proposal read -> application rows carrying owner source_effect receipts ->
    the build owner's dependency proof. Adverse: partial effect, later/other-selection builds, foreign project and an
    unattributed application never count as applied or built. Application rows are owner-shaped records here; the
    guarded application door itself is exercised by its own owner suites."""
    import hashlib
    from test_proposal_lifecycle import setup
    from laplace.manuscript import build_jobs, build_targets, projection_viewer as compiler, source_effects
    _md,tid,_edits,_context=setup(tmp_path)
    turn=session_reads._records(tmp_path)['turns'][tid]
    records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-feedback-join','turn_id':tid,'project':'fixture',
        'proposal':next(iter(turn['proposal_versions'].values()))})
    version=session_reads._records(tmp_path)['turns'][tid]['pending_proposal_version']
    produced=route.revision_join(tmp_path,'fixture',tid)
    assert produced['state']=='NOT_APPLIED' and produced['links']['produced'] and not produced['links']['applied']
    proposal=next(p for p in produced['proposals'] if p['version']==version)
    assert proposal['turn_proposal']=={'turn_id':tid,'proposal_version':version}
    assert proposal['read']['native_request']['payload']=={'id':tid,'proposal_version':version,'view':'summary'}
    assert produced['next_read']['native_request']['concept']=='proposal@paragraph'
    sha=lambda data:hashlib.sha256(data).hexdigest()
    rel='build-fixture/main.tex';sel='sha256:'+'a'*64;old,new=b'old line\n',b'new line\n'
    path=tmp_path/rel;path.parent.mkdir(parents=True);path.write_bytes(new)
    def receipt(*files):return source_effects.receipt('fixture',sel,[{'scope':'repository','path':name,'before_sha256':'sha256:'+sha(a),
        'after_sha256':'sha256:'+sha(b),'observed_after_sha256':'sha256:'+sha(c)} for name,a,b,c in files])
    document={'root':rel,'manuscript_dir':'build-fixture'}
    records.bank(tmp_path,{'record':'writing-application','id':'WA-feedback-1','turn_id':tid,'project':'fixture',
        'candidate_version':version,'complete':True,'document':document,'source_effect':receipt((rel,old,new,new))})
    records.bank(tmp_path,{'record':'writing-application','id':'WA-feedback-partial','turn_id':tid,'project':'fixture',
        'candidate_version':version,'complete':False,'document':document,
        'source_effect':receipt((rel,old,new,new),('build-fixture/other.tex',old,new,old))})
    records.bank(tmp_path,{'record':'writing-application','id':'WA-foreign','turn_id':tid,'project':'other',
        'candidate_version':version,'complete':True,'document':document,'source_effect':receipt((rel,old,new,new))})
    records.bank(tmp_path,{'record':'writing-application','id':'WA-legacy','turn_id':tid,'project':'fixture','complete':True})
    applied=route.revision_join(tmp_path,'fixture',tid)
    items={item['id']:item for p in applied['proposals'] for item in p['applications']}
    assert set(items)=={'WA-feedback-1','WA-feedback-partial'} and 'WA-foreign' not in str(applied['unattributed_applications'])
    assert [row['id'] for row in applied['unattributed_applications']]==['WA-legacy']
    good,partial=items['WA-feedback-1'],items['WA-feedback-partial']
    assert good['source_effect']['state']=='COMMITTED' and good['source_effect']['complete'] and good['source_effect']['recovery'] is None
    assert 'view=application' in good['read']['http']['url'] and 'item_id=WA-feedback-1' in good['read']['http']['url']
    assert partial['source_effect']['state']=='PARTIAL' and not partial['source_effect']['complete']
    assert partial['build']['state']=='NOT_APPLICABLE' and 'never repeat' in partial['source_effect']['recovery']
    assert applied['state']=='NOT_BUILT' and good['build']['state']=='NOT_BUILT'
    assert good['build']['next_read']==build_targets.read_handle('fixture') and applied['links']['incomplete_applications']==1
    job={'schema_version':'laplace.build-job/1','id':'BLD-'+'1'*32,'project':'fixture','root':rel,'target_kind':'manuscript',
         'selection_identity':sel,'input_revision':'sha256:'+'2'*64}
    compiler._write_recompile_status(path,{'state':'idle','ok':True,'build_job':job,'dependencies':{rel:sha(new)}})
    built=route.revision_join(tmp_path,'fixture',tid)
    shown=next(item for p in built['proposals'] for item in p['applications'] if item['id']=='WA-feedback-1')['build']
    assert built['state']=='BUILT' and shown['build_job']==job and shown['observation']=='current'
    assert shown['job_status_read']==build_jobs.handles(job)['job_status_read']==built['next_read']
    later={**job,'id':'BLD-'+'3'*32}
    compiler._write_recompile_status(path,{'state':'idle','ok':True,'build_job':later,'dependencies':{rel:sha(b'later\n')},
        'last_successful_build':{'build_job':job,'dependencies':{rel:sha(new)}}})
    retained=route.revision_join(tmp_path,'fixture',tid)
    assert retained['state']=='BUILT' and retained['next_read']==build_jobs.handles(job)['job_status_read']
    compiler._write_recompile_status(path,{'state':'idle','ok':True,'build_job':later,'dependencies':{rel:sha(b'later\n')}})
    stale=route.revision_join(tmp_path,'fixture',tid)
    assert stale['state']=='NOT_BUILT' and 'other bytes' in next(item for p in stale['proposals'] for item in p['applications']
                                                              if item['id']=='WA-feedback-1')['build']['reason']
    foreign={**job,'id':'BLD-'+'4'*32,'selection_identity':'sha256:'+'b'*64}
    compiler._write_recompile_status(path,{'state':'idle','ok':True,'build_job':foreign,'dependencies':{rel:sha(new)}})
    assert route.revision_join(tmp_path,'fixture',tid)['state']=='NOT_BUILT'
    assert route.revision_join(tmp_path,'other',tid)['state']=='UNAVAILABLE'
    retain('revision-join-owner',{'produced':produced,'applied':applied,'built':built,'stale':stale})


def test_route_edges_retain_authored_focus_and_legacy_focus_is_qualified_to_its_handed_phase(prepared):
    """feedback/comment a7: each admitted edge carries the obligation label/scope authored for its request; an edge
    recorded before snapshots existed is qualified to its exact handed phase and borrows no current question."""
    root,payload,saved,policy=prepared
    result=route.handle(root,'p',submit_payload(root,saved,policy,request='route-focus-public-1'),HUMAN)
    complete=wait_result(root,result['route_id'])
    focus={edge['obligation_id']:edge['obligation'] for edge in complete['edges']}
    assert focus=={'assumptions':{'state':'AUTHORED_SNAPSHOT','id':'assumptions','label':'Assumptions','scope':'other'},
                   'boundary':{'state':'AUTHORED_SNAPSHOT','id':'boundary','label':'Boundary','scope':'other'}}
    task=work._tasks('p',root)['review-claim'];row=route._route_for(task,result['route_id'])
    legacy=copy.deepcopy(row['review_edges'][0]);legacy.pop('obligation')
    view=route._edge_view(root,'p',task,legacy,row)
    assert view['obligation']['state']=='LEGACY_UNSNAPSHOTTED' and view['obligation']['label'] is None
    assert view['obligation']['next_read']==view['handoff_read'] and 'not the current Work question' in view['obligation']['reason']
    retain('route-focus-actual',{'edges':[edge['obligation'] for edge in complete['edges']],'legacy':view['obligation']})


def test_response_preview_is_the_public_message_owner_page_with_qualified_refusal_and_no_saved_reply(prepared,monkeypatch):
    """feedback/response a7: each admitted edge's <=300-character preview is session_reads.public_message's own first page
    at the admitted identity (content, basis, page/next reads); the Complete handle is unchanged. Owner-shaped stubs of the
    same reader, labelled: a changed message is a qualified refusal and an absent reply stays NO_SAVED_REPLY."""
    root,payload,saved,policy=prepared
    result=route.handle(root,'p',submit_payload(root,saved,policy,request='route-preview-public-1'),HUMAN)
    complete=wait_result(root,result['route_id'])
    for edge in complete['edges']:
        admitted=edge['event']['admitted'];shown=edge['event']['result']
        page=session_reads.public_message(root,{'project':'p','session_id':admitted['session_id'],'turn_id':admitted['turn_id'],'part':'reply','limit':300})
        assert shown['available'] and shown['state']=='AVAILABLE' and shown['text']==page['content'] and len(shown['text'])<=300
        assert shown['basis']==page['basis'] and shown['page_read']==page['page_read'] and shown['next_read']==page['next_read']
        assert edge['public_reply_read']['identity']==page['restart_read']['identity'] and edge['public_reply_read']['sdk']['payload']['limit']==4000
    real=session_reads.public_message
    def refused(root_,payload_):raise session_reads.MessagePartRefusal({**payload_,'offset':0},'sha256:'+'1'*64,'sha256:'+'2'*64)
    monkeypatch.setattr(session_reads,'public_message',refused)
    changed=route.aggregate(root,'p','review-claim',result['route_id'])
    for edge in changed['edges']:
        shown=edge['event']['result']
        assert shown['available'] is False and shown['state']=='REFUSED' and shown['refusal']['message_refusal']['code']=='CHANGED_MESSAGE'
        assert 'text' not in shown and shown['restart_read']==edge['public_reply_read']
    monkeypatch.setattr(session_reads,'public_message',lambda root_,payload_:{**real(root_,payload_),'state':'ABSENT','reason':'NO_SAVED_REPLY','content':None})
    absent=route.aggregate(root,'p','review-claim',result['route_id'])
    assert all(edge['event']['result']=={'status':edge['event']['result']['status'],'available':False,'state':'ABSENT','reason':'NO_SAVED_REPLY'}
               for edge in absent['edges'])
    retain('response-preview-actual',{'available':[edge['event']['result'] for edge in complete['edges']],
        'refused':[edge['event']['result'] for edge in changed['edges']],'absent':[edge['event']['result'] for edge in absent['edges']]})


def _request_recovery_export(root,monkeypatch):
    """The CURRENT owner's request comparison, association and settlement DTOs for the opened reader controller.

    Exported by the reader preset's existing same-scratch producer below. Every value is an actual owner reply for an exact
    original wire (origin Save, route submit, policy save); nothing is shaped or hashed here. Transport is not exercised:
    delivery._deliver is a no-op, so recorded routes hold their reservations only."""
    import runtime_guard
    runtime_guard.arm(monkeypatch)
    root.mkdir(parents=True,exist_ok=True)
    payload=origin_fixture(root);ledger=payload['source_basis']['ledger']
    monkeypatch.setenv('LAPLACE_STATE',str(root/'state'))
    monkeypatch.setattr(provider,'capabilities',lambda *a,**k:copy.deepcopy(CATALOGUE))
    monkeypatch.setattr(provider,'WritingTurn',_StubTurn)
    monkeypatch.setattr(delivery,'_deliver',lambda *a:None)
    work.task('p',{'id':'review-claim','title':'Review this claim','goal':'Check assumptions and numerical boundary.',
        'review_obligations':[{'id':'assumptions','label':'Assumptions','scope':'other','inputs':['p/manuscript/main.tex']}]},root)
    binding=delivery.bind(root,'p',{'work_id':'review-claim','expected_work_revision':guard(root),'kind':'app-owned',
        'provider':'claude','model':'haiku','effort':'low','label':'assumptions'},HUMAN)['binding']
    policy={'mode':'manual','recipients':[{'obligation_id':'assumptions','recipient_binding_id':binding['id']}],
            'limits':{'max_new_admissions':2,'max_attempts':1,'admission_seconds':60,'runtime_seconds':10}}
    def origin_view(sub):
        legacy=authoring.correction_request('p',sub['request_id'],root,ledger=ledger)
        return {'payload':copy.deepcopy(sub),'lookup':legacy['reconcile'],'legacy':legacy,
                'association':authoring.correction_request('p',sub['request_id'],root,ledger=ledger,submission=json.dumps(sub))}
    def delivery_view(wire,kind):
        read={'action':'route-status','work_id':'review-claim','request_id':wire['request_id'],**({'request_kind':'policy'} if kind=='policy' else {})}
        return {'payload':copy.deepcopy(wire),'lookup':route.handle_read('p',read),'legacy':route.handle(root,'p',dict(read),HUMAN),
                'association':route.handle(root,'p',{**read,'request_kind':kind,'submission':copy.deepcopy(wire)},HUMAN)}
    unsent={**payload,'request_id':'export-origin-unsent-1','text':'An unsent passage question kept as a draft.'}
    saved=authoring.bank_correction('p',payload,root)
    origin={'recorded':origin_view(payload),'absent':origin_view(unsent)}
    route_wire={'project':'p','action':'route-submit','work_id':'review-claim','expected_work_revision':guard(root),
                'request_id':'export-route-recorded-1','origin':saved['origin_ref'],'policy':policy}
    route.handle(root,'p',copy.deepcopy(route_wire),HUMAN)
    unsent_route={**route_wire,'request_id':'export-route-unsent-1'}
    routes={'recorded':delivery_view(route_wire,'route'),'absent':delivery_view(unsent_route,'route')}
    routes['settle_reply']=route.handle(root,'p',{**routes['absent']['association']['settle']['payload'],'submission':copy.deepcopy(unsent_route)},HUMAN)
    routes['settled']=delivery_view(unsent_route,'route')
    # An exact partial manual policy (route append interrupted): UNKNOWN with the owner's route-admission-only settle.
    real_record=route._record_route
    def interrupted(*a):raise OSError('route append interrupted (export)')
    partial_route={**route_wire,'request_id':'export-route-partial-1'}
    monkeypatch.setattr(route,'_record_route',interrupted)
    with pytest.raises(OSError):route.handle(root,'p',copy.deepcopy(partial_route),HUMAN)
    monkeypatch.setattr(route,'_record_route',real_record)
    routes['partial']=delivery_view(partial_route,'route')
    routes['partial_settle_reply']=route.handle(root,'p',{**routes['partial']['association']['settle']['payload'],'submission':copy.deepcopy(partial_route)},HUMAN)
    routes['partial_settled']=delivery_view(partial_route,'route')
    policy_wire={'project':'p','action':'policy-save','work_id':'review-claim','expected_work_revision':guard(root),
                 'request_id':'export-policy-recorded-1','policy':policy}
    route.handle(root,'p',copy.deepcopy(policy_wire),HUMAN)
    unsent_policy={**policy_wire,'request_id':'export-policy-unsent-1'}
    policies={'recorded':delivery_view(policy_wire,'policy'),'absent':delivery_view(unsent_policy,'policy')}
    policies['settle_reply']=route.handle(root,'p',{**policies['absent']['association']['settle']['payload'],'submission':copy.deepcopy(unsent_policy)},HUMAN)
    policies['settled']=delivery_view(unsent_policy,'policy')
    # A one-copy policy request whose original CAS is now stale (the Work moved on): its exact Retry cannot be admitted, so
    # the owner's request-settle is the author's escape. Its association, settle reply and settled association are the owner's.
    stale_policy={**policy_wire,'request_id':'export-policy-stale-1'}
    # an actual owner Work change after the original was retained: the task owner revises the Work, moving its revision on
    work.task('p',{'id':'review-claim','expected_work_revision':guard(root),'title':'Review this claim','goal':'Check assumptions and numerical boundary (revised).',
        'review_obligations':[{'id':'assumptions','label':'Assumptions','scope':'other','inputs':['p/manuscript/main.tex']}]},root)
    policies['stale_current_revision']=guard(root)
    assert stale_policy['expected_work_revision']!=policies['stale_current_revision']
    policies['stale']=delivery_view(stale_policy,'policy')
    policies['stale_settle_reply']=route.handle(root,'p',{**policies['stale']['association']['settle']['payload'],'submission':copy.deepcopy(stale_policy)},HUMAN)
    policies['stale_settled']=delivery_view(stale_policy,'policy')
    # The owner's actual route preview for the saved origin, so the opened editor paints its routing controls from it.
    preview=route.handle(root,'p',{'action':'route-preview','work_id':'review-claim','origin':saved['origin_ref'],'policy':policy,
        'request_id':'export-route-preview-1'},HUMAN)
    value={'schema':'laplace.feedback-request-recovery-vector/1','project':'p','ledger':ledger,'origin':origin,'route':routes,
           'policy':policies,'preview':preview}
    assert routes['partial']['association']['association']['state']=='UNKNOWN' and routes['partial']['association']['settle']['outcome_scope']=='route-admission-only'
    assert routes['partial_settle_reply']['settled'] and routes['partial_settled']['association']['preserved_effects']
    assert policies['settle_reply']['settled'] and policies['settled']['association']['effect']=='NOT_ADMITTED'
    assert [origin['recorded']['association']['association']['state'],origin['absent']['association']['association']['state']]==['MATCH','UNRECORDED']
    assert routes['recorded']['association']['association']['state']=='MATCH' and routes['absent']['association']['settle']['permitted']
    assert routes['settle_reply']['settled'] and routes['settled']['association']['effect']=='NOT_ADMITTED'
    assert value['policy']['recorded']['association']['association']['state']=='MATCH'
    stale=policies['stale']['association']
    assert stale['association']['state']=='UNRECORDED' and stale['settle']['permitted'] and stale['settle']['payload']['request_kind']=='policy'
    assert policies['stale_settle_reply']['settled'] and policies['stale_settled']['association']['effect']=='NOT_ADMITTED'
    assert preview['actions']['compose']['permitted'] and preview['work']['id']=='review-claim'
    assert preview['actions']['compose']['route_spec']['action']=='route-submit'
    return json.loads(json.dumps(value,default=str))


def test_resolved_successor_actual_reconciliation_application_and_matching_build_with_adverse_controls(tmp_path,monkeypatch):
    """feedback/comment/passage/response a7: an actual owner proposal turn -> the reconciliation owner's prepare and
    human apply-resolution (a separately authored current-source successor, its guarded application and source effect)
    -> revision_join's indexed exact predecessor lineage -> the build owner's proof for the successor's pins. The original
    version's direct applied=false stays; successor facts are separate. Deterministic boundary, labelled: no compiler
    runs, the build owner's status row is written for the exact observed after-pins, as a successful build leaves it.
    Adverse: a mismatched build, a wrong-version application row and a foreign project never count."""
    from test_proposal_lifecycle import setup
    from laplace.manuscript import build_jobs, manuscript_proposals, reconciliation, projection_viewer as compiler
    _md,tid,_edits,_context=setup(tmp_path)
    turn=session_reads._records(tmp_path)['turns'][tid]
    records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-feedback-successor','turn_id':tid,'project':'fixture',
        'proposal':next(iter(turn['proposal_versions'].values()))})
    turn=session_reads._records(tmp_path)['turns'][tid];version=turn['pending_proposal_version']
    edit=turn['proposal_versions'][version]['edits'][0];eid=manuscript_proposals.edit_id(edit)
    before=route.revision_join(tmp_path,'fixture',tid)
    assert before['state']=='NOT_APPLIED' and before['resolved_successors']['state']=='NONE'
    subject={'turn_id':tid,'proposal_version':version,'edit_id':eid}
    prepared=reconciliation.decide(tmp_path,'fixture',{'decision':'prepare-resolution',**subject})
    assert not prepared['target_required'],prepared.get('reason')
    current=prepared['current'];tail='\n' if current.endswith('\n') else ''
    resolved=current[:len(current)-len(tail)]+' Human-resolved current wording.'+tail
    applied=reconciliation.decide(tmp_path,'fixture',{'decision':'apply-resolution',**subject,
        'resolution_token':prepared['resolution_token'],'target':{key:prepared['target'][key] for key in reconciliation.TARGET_GUARDS},
        'input_observations':prepared['input_observations'],'resolved_after':resolved})
    assert applied.get('application') and applied['application'].get('complete'),applied.get('error')
    successor_ref=applied['candidate_ref']
    join=route.revision_join(tmp_path,'fixture',tid)
    assert join['state']=='NOT_APPLIED' and join['links']['applied'] is False and join['links']['built'] is False
    lineage=next(p for p in join['proposals'] if p['version']==version)['resolved_successors']
    assert lineage['state']=='COMPLETE' and lineage['total']==1 and lineage['omitted']==0
    succ=lineage['items'][0]
    assert succ['candidate_ref']==successor_ref and succ['predecessor']['edit_id']==eid and succ['predecessor']['turn_id']==tid
    assert succ['candidate']['state']=='READ' and succ['candidate']['proposal_state']=='applied'
    assert succ['candidate']['disposition']['status']=='RECORDED' and succ['deeper']['state']=='NONE'
    app=succ['applications'][0]
    assert app['id']==applied['application']['id'] and app['source_effect']['state'] in route._APPLIED and app['source_effect']['complete']
    assert succ['state']=='NOT_BUILT' and join['resolved_successors']=={**join['resolved_successors'],'state':'NOT_BUILT','total':1,'applied':1,'built':0}
    effect=app['source_effect'];rel=app['document_root']
    job={'schema_version':'laplace.build-job/1','id':'BLD-'+'5'*32,'project':'fixture','root':rel,'target_kind':'manuscript',
         'selection_identity':effect['selection_identity'],'input_revision':'sha256:'+'6'*64}
    pins={row['path']:row['observed_after_sha256'].removeprefix('sha256:') for row in effect['files']}
    compiler._write_recompile_status(tmp_path/rel,{'state':'idle','ok':True,'build_job':{**job,'id':'BLD-'+'7'*32},
        'dependencies':{path:'0'*64 for path in pins}})
    mismatched=route.revision_join(tmp_path,'fixture',tid)
    assert mismatched['resolved_successors']['state']=='NOT_BUILT'
    compiler._write_recompile_status(tmp_path/rel,{'state':'idle','ok':True,'build_job':job,'dependencies':pins})
    built=route.revision_join(tmp_path,'fixture',tid)
    shown=next(p for p in built['proposals'] if p['version']==version)['resolved_successors']['items'][0]
    assert shown['state']=='BUILT' and shown['applications'][0]['build']['build_job']==job
    assert shown['next_read']==build_jobs.handles(job)['job_status_read'] and built['resolved_successors']['state']=='BUILT'
    assert built['state']=='NOT_APPLIED' and built['links']=={**built['links'],'applied':False,'built':False}
    # every successor read is an actual owner read: GET it through the real HTTP door (review F0)
    from urllib.parse import urlsplit,parse_qs
    from laplace.web import authoring_http
    def get(handle):
        assert handle['http'].get('method','GET')=='GET';parsed=urlsplit(handle['http']['url'])
        code,_ctype,raw=authoring_http.handle(tmp_path,parsed.path,parse_qs(parsed.query),'GET',b'')
        assert code==200,(parsed.path,raw[:400]);return json.loads(raw)
    app_read=shown['applications'][0]['read']
    assert app_read['http']['url'].startswith('/authoring/history?') and 'session-turn' not in app_read['http']['url']
    record=get(app_read)
    assert applied['application']['id'] in json.dumps(record)
    for handle in (shown['read'],shown['next_read'],shown['applications'][0]['build']['job_status_read']):
        if handle and handle.get('http'):get(handle)
    records.bank(tmp_path,{'record':'writing-application','id':'WA-successor-wrong-version','project':'fixture',
        'candidate_id':successor_ref['id'],'candidate_version':'sha256:'+'0'*64,'complete':True})
    guarded=route.revision_join(tmp_path,'fixture',tid)
    item=next(p for p in guarded['proposals'] if p['version']==version)['resolved_successors']['items'][0]
    assert [row['id'] for row in item['mismatched_applications']]==['WA-successor-wrong-version']
    assert [row['id'] for row in item['applications']]==[applied['application']['id']] and item['state']=='BUILT'
    assert route.revision_join(tmp_path,'other',tid)['state']=='UNAVAILABLE'
    # F1 bounds. Labelled owner-shaped successor rows (the actual successor above stays first by index order): four more
    # resolutions of the same exact predecessor edit and one later resolution of the actual successor.
    for n in range(4):
        records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-%032x'%(n+1),'project':'fixture','candidate_kind':'current-source-resolution',
            'author':{'kind':'human','basis':'bound fixture'},'predecessor':{'turn_id':tid,'proposal_version':version,'edit_id':eid},
            'proposal':{'answer':'bound fixture %d'%n,'edits':[]},'proposal_instance_version':'sha256:%064x'%(n+1)})
    records.bank(tmp_path,{'record':'writing-proposal','id':'PROP-%032x'%99,'project':'fixture','candidate_kind':'current-source-resolution',
        'author':{'kind':'human','basis':'deeper fixture'},'predecessor':{'candidate_ref':dict(successor_ref),'edit_id':'deeper-edit'},
        'proposal':{'answer':'deeper fixture','edits':[]},'proposal_instance_version':'sha256:%064x'%99})
    cut=records.index(tmp_path).order
    bounded=route.revision_join(tmp_path,'fixture',tid);again=route.revision_join(tmp_path,'fixture',tid)
    assert records.index(tmp_path).order==cut and bounded['index_cut']==again['index_cut']==cut,'reading the join writes nothing'
    proposal=next(p for p in bounded['proposals'] if p['version']==version);lineage=proposal['resolved_successors']
    assert lineage['state']=='PARTIAL' and lineage['total']==5 and lineage['omitted']==1 and len(lineage['items'])==4
    assert lineage['continuation']['next_read']==proposal['read']
    first=lineage['items'][0]
    assert first['candidate_ref']==successor_ref and first['state']=='BUILT'
    assert first['deeper']=={**first['deeper'],'state':'PARTIAL','successors':1,'next_read':first['read']}
    assert all(item['state']=='NOT_APPLIED' and item['applications']==[] for item in lineage['items'][1:])
    assert bounded['resolved_successors']['partial'] is True and bounded['state']=='NOT_APPLIED' and bounded['links']['applied'] is False
    assert all(item['candidate']['state']=='UNAVAILABLE' for item in lineage['items'][1:]),'edit-less fixture rows are qualified, never rendered'
    assert first['candidate']['state']=='READ' and first['candidate']['proposal_state']=='applied'
    get(first['read'])
    for app in first['applications']:get(app['read'])
    get(lineage['continuation']['next_read']);get(first['deeper']['next_read'])
    retain('resolved-successor-bounds',{'bounded':bounded,'index_cut':cut})
    retain('resolved-successor-actual',{'schema':'laplace.feedback-route-vector/resolved-successor-actual/1',
        'turn_id':tid,'proposal_version':version,'edit_id':eid,'successor_ref':successor_ref,
        'before':before,'applied':join,'mismatched_build':mismatched,'built':built,'guarded':guarded,
        # the CURRENT owner's request comparison/association/settlement DTOs for the opened reader controller (same scratch)
        'request_recovery':_request_recovery_export(tmp_path/'request-recovery',monkeypatch)})


def test_actual_route_producer_proposal_guarded_application_and_matching_build(writer_prepared,monkeypatch):
    """The acknowledged whole route loop, driven through the actual route. Deterministic boundaries, labelled exactly:
    (1) the provider is a stub standing where WritingTurn stands that drives the REAL writing door under each admitted
    producer's own turn (source read -> propose_revision); (2) no compiler runs: the build owner's recorded status row
    is written for the exact observed after-pins of the real application, as a successful build leaves it. Everything
    else is the actual owner: route submit/admission, the saved proposal version, the guarded
    source_application.apply_proposal door and its source_effect receipt, build_jobs.source_observation through
    revision_join, and route.aggregate. Root's later paid model and real compiler build are not claimed here."""
    import test_writing_dispatch as dispatch_fixture
    from laplace.manuscript import build_jobs, source_application, projection_viewer as compiler
    from laplace.writing import operating as writing_operating
    line='A numerical claim requires a stated assumption.'
    failures,seen=[],[]

    class Producer(_StubTurn):
        def run(self,prompt):
            self.emit({'type':'session','native_id':'stub-'+str(self.session_id),'provider':self.provider,'model':self.model,
                       'process':{'cwd':str(writing_operating.session_workspace(self.session_id)),'tools':[],'mcp':'ok'}})
            self.inference_started=True
            seen.append(self.turn_id);tag=chr(64+len(seen))   # each producer proposes DIFFERENT bytes (review F4)
            for operation,body in (('source',{'files':['main.tex']}),
                                   ('propose_revision',{'answer':'State the assumption.','edits':[{'file':'main.tex','line_start':3,'line_end':3,
                                    'before':line,'after':line[:-1]+': a bounded step size ('+tag+').','reason':'The comment asks for the assumption.'}]})):
                try:
                    dispatch_fixture.writing_tools.execute(self.root,self.project,self.mode,operation,dict(body),turn_id=self.turn_id)
                except Exception as exc:   # recorded, never swallowed
                    failures.append({'turn':self.turn_id,'operation':operation,'error':repr(exc)[:400]})
            return {'status':'completed','text':'Proposed one edit for the comment.','native_id':'stub-'+str(self.session_id)}
    monkeypatch.setattr(provider,'WritingTurn',Producer)
    root,payload,saved,policy=writer_prepared
    result=route.handle(root,'p',submit_payload(root,saved,policy,request='route-loop-public-1'),HUMAN)
    complete=wait_result(root,result['route_id'])
    assert not failures,failures
    # The approved writer is admitted through the ordinary author/revise route; nothing relabels a reviewer.
    folded=records.fold_records(root)
    for edge in complete['edges']:
        turn=folded['turns'][edge['event']['admitted']['turn_id']]
        assert turn['mode']=='revise' and folded['sessions'][turn['session_id']].get('role','author')=='author'
    task=work._tasks('p',root)['review-claim']
    intents=[row for row in delivery._rows(task,delivery.EVENT) if row.get('state')=='SUBMITTED' and (row.get('recipient') or {}).get('effect')=='proposal-writer']
    assert len(intents)==2 and all(row.get('effect_selection') and row.get('feedback_execution') for row in intents)
    first,other=complete['edges'][0],complete['edges'][1]
    tid=first['event']['admitted']['turn_id'];join=first['revision']
    assert join['turn_id']==tid and join['state']=='NOT_APPLIED' and join['links']['produced'] and not join['links']['applied']
    version=join['proposals'][0]['version']
    assert join['proposals'][0]['turn_proposal']=={'turn_id':tid,'proposal_version':version}
    # the genuine guarded application door for that exact saved version
    code,applied=http_apply(root,tid,version)   # the real human HTTP door, exact owner proposal identity
    assert code==200 and applied.get('complete') is True,(code,applied)   # review F3: the receipt itself, not the absence of a refusal key
    assert (root/'p/manuscript/main.tex').read_bytes().count(b'a bounded step size')==1
    with records.index_lock:
        idx=records.index(root)
        rows=[row for row in idx.by_turn.get(tid,()) if row.get('record')=='writing-application' and idx.project(row)=='p']
    assert len(rows)==1,rows
    fields=records.selected_journal_fields('p',rows[0]['id'],root,fields=['source_effect','document'],expected_row_sha256=rows[0]['_hash'])
    effect,document=fields['source_effect'],fields['document']
    mid=next(e for e in route.aggregate(root,'p','review-claim',result['route_id'])['edges'] if e['edge_id']==first['edge_id'])['revision']
    item=mid['proposals'][0]['applications'][0]
    assert mid['state']=='NOT_BUILT' and item['id']==rows[0]['id'] and item['source_effect']['complete'] and item['build']['state']=='NOT_BUILT'
    assert item['source_effect']['state']=='COMMITTED'
    # deterministic compiler boundary: the build owner's status row exactly as a successful build of these bytes leaves it
    rel=document['root'];sel=effect['selection_identity']
    receipt_pins={row['path']:row['observed_after_sha256'].removeprefix('sha256:') for row in effect['files']}
    # review F2: the build owner's own dependency snapshot of the applied root, not the receipt copied into the sidecar;
    # a key-format, digest-spelling or root drift between source_application and the build owner fails here
    from laplace.manuscript import tex_dependencies
    deps=tex_dependencies.snapshot(root/rel,root)
    assert all(deps.get(name)==digest for name,digest in receipt_pins.items()),(deps,receipt_pins)
    job={'schema_version':'laplace.build-job/1','id':'BLD-'+'7'*32,'project':'p','root':rel,'target_kind':'manuscript',
         'selection_identity':sel,'input_revision':'sha256:'+'5'*64}
    compiler._write_recompile_status(root/rel,{'state':'idle','ok':True,'build_job':job,'dependencies':deps})
    built=route.aggregate(root,'p','review-claim',result['route_id'])
    final=next(e for e in built['edges'] if e['edge_id']==first['edge_id'])['revision']
    assert final['state']=='BUILT' and final['proposals'][0]['applications'][0]['build']['build_job']==job
    assert final['next_read']==build_jobs.handles(job)['job_status_read']
    # the sibling producer's own proposal was not applied: its join never borrows this application
    sibling=next(e for e in built['edges'] if e['edge_id']==other['edge_id'])['revision']
    assert sibling['turn_id']!=tid and sibling['state']=='NOT_APPLIED'
    # review F4: the sibling's own proposal is now stale against the applied bytes; the guarded door must not apply it
    sibling_turn,sibling_version=other['event']['admitted']['turn_id'],sibling['proposals'][0]['version']
    current_bytes=(root/'p/manuscript/main.tex').read_bytes()
    code,refused=http_apply(root,sibling_turn,sibling_version)
    assert refused.get('complete') is not True,(code,refused)
    with records.index_lock:
        idx=records.index(root)
        assert not [row for row in idx.by_turn.get(sibling_turn,()) if row.get('record')=='writing-application' and row.get('complete')]
    assert (root/'p/manuscript/main.tex').read_bytes()==current_bytes
    again=next(e for e in route.aggregate(root,'p','review-claim',result['route_id'])['edges'] if e['edge_id']==other['edge_id'])['revision']
    assert again['state'] in ('NOT_APPLIED','APPLICATION_INCOMPLETE'),again['state']
    # disposition stays separate: produced/applied/built never becomes the comment status or a review verdict
    assert built['revision']['disposition']['comment_owner']=='correction_origin' and 'never implies' in built['revision']['disposition']['meaning']
    assert built['origin']['correction'].get('status')==complete['origin']['correction'].get('status')
    # a later build of other bytes is not this application
    compiler._write_recompile_status(root/rel,{'state':'idle','ok':True,'build_job':{**job,'id':'BLD-'+'8'*32},'dependencies':{name:'0'*64 for name in deps}})
    later=next(e for e in route.aggregate(root,'p','review-claim',result['route_id'])['edges'] if e['edge_id']==first['edge_id'])['revision']
    assert later['state']=='NOT_BUILT'
    retain('revision-join-route-loop',{'produced':complete,'built':built})


def test_independent_review_recipients_stay_read_only_and_bank_no_proposal(prepared,monkeypatch):
    """Adverse control kept from the counterexample: an independent-review recipient's propose_revision is refused by the
    writing door; no proposal, application or manuscript byte results."""
    import test_writing_dispatch as dispatch_fixture
    from laplace.writing import operating as writing_operating
    failures=[]

    class Reviewer(_StubTurn):
        def run(self,prompt):
            self.emit({'type':'session','native_id':'stub-'+str(self.session_id),'provider':self.provider,'model':self.model,
                       'process':{'cwd':str(writing_operating.session_workspace(self.session_id)),'tools':[],'mcp':'ok'}})
            self.inference_started=True
            try:
                dispatch_fixture.writing_tools.execute(self.root,self.project,self.mode,'propose_revision',{'answer':'x','edits':[{'file':'main.tex',
                    'line_start':3,'line_end':3,'before':LINE,'after':LINE[:-1]+' (reviewer).','reason':'Not permitted.'}]},turn_id=self.turn_id)
            except Exception as exc:
                failures.append(repr(exc)[:300])
            return {'status':'completed','text':'Reviewed only.','native_id':'stub-'+str(self.session_id)}
    monkeypatch.setattr(provider,'WritingTurn',Reviewer)
    root,payload,saved,policy=prepared
    before=(root/'p/manuscript/main.tex').read_bytes()
    result=route.handle(root,'p',submit_payload(root,saved,policy,request='route-review-readonly-1'),HUMAN)
    complete=wait_result(root,result['route_id'])
    assert len(failures)==len(complete['edges'])==2,failures
    assert all(edge['revision']['state']=='NOT_PRODUCED' and not edge['revision']['proposals'] for edge in complete['edges'])
    assert (root/'p/manuscript/main.tex').read_bytes()==before


def test_writer_approval_is_exact_human_replayable_and_ordinary_bind_refuses_effects(prepared):
    root,payload,saved,policy=prepared
    wire=writer_wire(root,'writer-guard','approve-writer-guard-1')
    first=delivery.handle(root,'p',dict(wire),HUMAN)
    assert first['effect']=='approved' and not first['replayed'] and first['binding']['effect']=='proposal-writer'
    again=delivery.handle(root,'p',dict(wire),HUMAN)
    assert again['replayed'] and again['binding']['id']==first['binding']['id']
    with pytest.raises(ValueError):   # the same request id with another intent
        delivery.handle(root,'p',{**wire,'label':'changed'},HUMAN)
    with pytest.raises((ValueError,work.WorkConflict)):   # a stale Work revision
        delivery.handle(root,'p',{**wire,'request_id':'approve-writer-guard-3','expected_work_revision':'sha256:'+'0'*64},HUMAN)
    with pytest.raises(ValueError):   # the ordinary binding owner never mints effect recipients
        delivery.bind(root,'p',{'work_id':'review-claim','expected_work_revision':guard(root),'kind':'app-owned',
                                'provider':'claude','model':'haiku','effort':'low','effect':'proposal-writer'},HUMAN)
    with pytest.raises(ValueError):   # approval is a human-door effect only
        from laplace.writing import workflow_progression
        workflow_progression.approve_effect(root,'p',{**wire,'request_id':'approve-writer-guard-4'},{'origin':'native','turn_id':'WT-none'})
    # the existing review bindings are unchanged by the approvals
    task=work._tasks('p',root)['review-claim']
    for pair in policy['recipients']:
        assert delivery._latest(task,delivery.BINDING,pair['recipient_binding_id']).get('effect') is None


def submit_payload(root,saved,policy,request='route-public-1'):
    return {'action':'route-submit','work_id':'review-claim','expected_work_revision':guard(root),
            'request_id':request,'origin':saved['origin_ref'],'policy':policy}


def wait_result(root,route_id):
    until=time.monotonic()+12
    while time.monotonic()<until:
        value=route.aggregate(root,'p','review-claim',route_id)
        if value['state']=='response_ready' and all(e.get('recipient_ack')=='TERMINAL' for e in value['edges']):return value
        time.sleep(.02)
    raise AssertionError(value)


def test_two_reviews_exact_replay_lookup_and_full_handles(prepared):
    root,payload,saved,policy=prepared
    preview=route.handle(root,'p',{'action':'route-preview','work_id':'review-claim','origin':saved['origin_ref'],
        'policy':policy,'request_id':'route-public-1'},HUMAN)
    assert not preview['issues'] and preview['actions']['compose']['permitted']
    assert preview['selected_recipients']==policy['recipients']
    result=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    complete=wait_result(root,result['route_id'])
    assert complete['allowance']=={'max_new_admissions':2,'reserved':2,'admitted':2,'unconfirmed':0,
        'basis':'Admitted is retained WD coordinates; unconfirmed reservations are not zero use.','remaining':0}
    assert len({e['event']['admitted']['turn_id'] for e in complete['edges']})==2
    assert all(e['event']['continuation'] is None and e['recipient_ack']=='TERMINAL' for e in complete['edges'])
    assert all(e['event']['result']['preview'] and not e['event']['result']['complete'] for e in complete['edges'])
    assert all('http' in e['public_reply_read'] and e['exact_reply_read'] for e in complete['edges'])
    replay=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    assert replay['replayed'] and replay['route_id']==result['route_id']
    assert len([t for t in records.fold_records(root)['turns'].values() if t.get('request_id','').startswith('WD-')])==2
    lookup=route.status(root,'p',{'work_id':'review-claim','request_id':'route-public-1'})
    assert lookup['effect']=='RECORDED' and lookup['aggregate']['route_id']==result['route_id']
    assert route.status(root,'p',{'work_id':'review-claim','origin':saved['origin_ref']})['route_id']==result['route_id']
    retain('owner-samples',{'preview':preview,'submitted':result,'aggregate':complete,'request_recorded':lookup,
        'request_none':route.status(root,'p',{'work_id':'review-claim','request_id':'unknown-public-1'})})


def test_policy_request_reconciliation_and_automatic_requires_saved_policy(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    policy={**policy,'mode':'automatic'}
    preview=route.preview(root,'p',{'work_id':'review-claim','policy':policy,'request_id':'policy-public-1'},HUMAN)
    assert preview['issues'] and not preview['actions']['compose']['permitted']
    wire={'action':'policy-save','work_id':'review-claim','expected_work_revision':guard(root),
        'request_id':'policy-public-1','policy':policy}
    before=route.status(root,'p',{'work_id':'review-claim','request_kind':'policy','request_id':'policy-public-1'})
    result=route.handle(root,'p',wire,HUMAN)
    found=route.status(root,'p',{'work_id':'review-claim','request_kind':'policy','request_id':'policy-public-1'})
    assert before['effect']=='NONE' and found['effect']=='RECORDED' and found['policy']==result['policy']
    assert route.handle(root,'p',wire,HUMAN)['replayed']
    with pytest.raises(ValueError,match='another intent'):
        route.handle(root,'p',{**wire,'policy':{**policy,'limits':{**policy['limits'],'max_new_admissions':3}}},HUMAN)
    ready=route.preview(root,'p',{'work_id':'review-claim','policy_id':result['policy']['id'],
        'request_id':'route-auto-public-1'},HUMAN)
    assert ready['actions']['compose']['permitted'] and not ready['actions']['submit']['permitted']
    retain('policy-samples',{'before':before,'saved':result,'request_status':found,'preview':ready})


def test_partial_transport_keeps_reservation_and_same_request_recovers(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    real=turn_admission.start_work_delivery_turn;calls=[]
    def transport(root,wire,event):
        calls.append(event)
        if len(calls)==2:raise OSError('synthetic lost transport before admission')
        return real(root,wire,event)
    monkeypatch.setattr(turn_admission,'start_work_delivery_turn',transport)
    result=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    until=time.monotonic()+10
    while time.monotonic()<until:
        partial=route.aggregate(root,'p','review-claim',result['route_id'])
        if partial['state']=='partial':break
        time.sleep(.02)
    assert partial['allowance']['reserved']==2 and partial['allowance']['remaining']==0
    assert partial['allowance']['admitted']==1
    recovered=route.recover(root,'p',{'work_id':'review-claim','route_id':result['route_id']},HUMAN)
    complete=wait_result(root,result['route_id'])
    assert len(calls)==3 and len(set(calls))==2 and complete['allowance']['admitted']==2
    retain('partial-recovery',{'partial':partial,'recovered':recovered,'complete':complete,'transport_events':calls})


def test_changed_source_or_policy_never_renews_allowance_and_completed_reads_survive(prepared):
    root,payload,saved,policy=prepared
    wire=submit_payload(root,saved,policy)
    result=route.handle(root,'p',wire,HUMAN);before=wait_result(root,result['route_id'])
    (root/'p/manuscript/main.tex').write_text('Changed source.\n')
    assert route.handle(root,'p',wire,HUMAN)['replayed']
    observed=route.aggregate(root,'p','review-claim',result['route_id'])
    assert observed['origin']['currentness']['state']=='CHANGED' and observed['allowance']['reserved']==2
    assert all(e['event']['result']['available'] for e in observed['edges'])
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        route.handle(root,'p',{**wire,'request_id':'new-source-public-1'},HUMAN)
    with pytest.raises(ValueError,match='another exact intent'):
        route.handle(root,'p',{**wire,'recipients':policy['recipients'][:1]},HUMAN)


def test_unsupported_caps_and_forged_supervision_have_no_route_effect(prepared):
    root,payload,saved,policy=prepared
    bad={**policy,'limits':{**policy['limits'],'max_cost_usd':.01}}
    with pytest.raises(ValueError,match='UNSUPPORTED_LIMIT'):
        route.handle(root,'p',submit_payload(root,saved,bad),HUMAN)
    assert not route.status(root,'p',{'work_id':'review-claim'})['routes']
    with pytest.raises(ValueError,match='closed owner contract'):
        route.handle(root,'p',{**submit_payload(root,saved,policy),'runtime_deadline_at':'2099'},HUMAN)
    with pytest.raises(ValueError,match='cannot carry feedback_execution'):
        turn_admission.start_turn(root,{'project':'p','text':'forged','feedback_execution':{'runtime_seconds':2}})


def test_policy_and_binding_generation_cannot_refill_original_comment_account(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    monkeypatch.setattr(delivery,'_deliver',lambda *a:None)
    first=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    binding=delivery.bind(root,'p',{'work_id':'review-claim','expected_work_revision':guard(root),'kind':'app-owned',
        'provider':'claude','model':'haiku','effort':'low','label':'new approved reviewer'},HUMAN)['binding']
    changed=copy.deepcopy(policy);changed['recipients'][0]['recipient_binding_id']=binding['id']
    with pytest.raises(ValueError,match='ALLOCATION_EXHAUSTED'):
        route.handle(root,'p',submit_payload(root,saved,changed,'new-policy-public-1'),HUMAN)
    # A status/display edit is not a new origin, generation or allowance.
    authoring.correction_status('p',{'id':saved['correction']['id'],'status':'resolved','base_revision':saved['revision']},root)
    replay=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    assert replay['route_id']==first['route_id'] and replay['aggregate']['allowance']['reserved']==2
    assert len(replay['aggregate']['edges'])==2


def test_lost_admitted_ack_reconciles_before_new_effect_guards(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    real=turn_admission.start_work_delivery_turn;calls=[]
    def lost_ack(root,wire,event):
        value=real(root,wire,event);calls.append(value)
        raise OSError('synthetic response lost after actual WT bank')
    monkeypatch.setattr(turn_admission,'start_work_delivery_turn',lost_ack)
    first=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    assert len(calls)==2
    # Actual admitted coordinates survive later source drift. Recovery observes
    # those effects instead of starting replacement sessions or replenishing.
    (root/'p/manuscript/main.tex').write_text('Later source changes.\n')
    monkeypatch.setattr(turn_admission,'start_work_delivery_turn',lambda *a:pytest.fail('must reconcile before transport'))
    recovered=route.recover(root,'p',{'work_id':'review-claim','route_id':first['route_id']},HUMAN)
    value=recovered['aggregate']
    assert value['allowance']['admitted']==2 and value['allowance']['reserved']==2
    assert {e['event']['admitted']['turn_id'] for e in value['edges']}=={c['turn_id'] for c in calls}
    assert all(any(r.get('state')=='ADMITTED' and r.get('recovered') for r in delivery._history(
        work._tasks('p',root)['review-claim'],e['event']['id'])) for e in value['edges'])
    retain('lost-admission-ack',{'original':first,'recovered':recovered,'actual_turns':calls})


def test_actual_synthetic_owned_process_timeout_retains_partial_and_reaps(prepared,monkeypatch):
    import subprocess
    import sys
    from laplace.writing import child_hosts
    root,payload,saved,policy=prepared
    helper=Path(os.environ.get('FEEDBACK_ROUTE_PROCESS_HELPER') or root/'public_review.py')
    helper.write_text("import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nprint('ready',flush=True)\ntime.sleep(30)\n")
    children=[]
    class SleepingReview(_StubTurn):
        def run(self,prompt):
            self.inference_started=True
            self.emit({'type':'delta','text':'Public partial result before the deadline.'})
            self.process=subprocess.Popen([sys.executable,'-S',str(helper)],stdout=subprocess.PIPE,text=True)
            self.on_spawn(self.process,'synthetic-review')
            assert self.process.stdout.readline().strip()=='ready'
            children.append(self.process)
            self.process.wait(timeout=15)
            return {'status':'interrupted','text':'Public partial result before the deadline.'}
        def interrupt(self):
            if getattr(self,'process',None) and self.process.poll() is None:self.process.terminate()
    monkeypatch.setattr(provider,'WritingTurn',SleepingReview)
    policy={**policy,'recipients':policy['recipients'][:1],'limits':{**policy['limits'],'runtime_seconds':.5}}
    started=time.monotonic()
    result=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    value=wait_result(root,result['route_id'])
    edge=value['edges'][0];tid=edge['event']['admitted']['turn_id'];sid=edge['event']['admitted']['session_id']
    job=turn_jobs._JOBS[tid]
    with job['condition']:assert job['condition'].wait_for(lambda:job['done'],timeout=10)
    reply=records.fold_records(root)['turns'][tid]['reply']
    assert children and all(p.poll() is not None for p in children)
    assert reply['status']=='interrupted' and reply['text']=='Public partial result before the deadline.'
    assert reply['feedback_execution']['limit_reason']=='feedback-review-runtime-exceeded'
    assert reply['feedback_execution']['partial_result_retained']
    assert time.monotonic()-started<12
    execution=child_hosts._child_execution_record(root,sid)
    assert all(not child_hosts._process_matches(identity) for identity in execution['provider_processes'])
    retain('owned-timeout',{'aggregate':value,'reply':reply,'execution':execution,
        'processes':[{'pid':p.pid,'returncode':p.returncode} for p in children],'elapsed_seconds':time.monotonic()-started,'job_done':job['done']})


def test_actual_native_parent_is_retained_when_human_recovers_reserved_route(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    policy={**policy,'parent_return':{'admit_idle':False,'max_attempts':1,'max_depth':1}}
    approved=route.policy_save(root,'p',{'work_id':'review-claim','expected_work_revision':guard(root),
        'request_id':'native-policy-public-1','policy':policy},HUMAN)['policy']
    wire={'action':'route-submit','work_id':'review-claim','expected_work_revision':guard(root),'request_id':'native-route-public-1',
        'origin':saved['origin_ref'],'policy_id':approved['id'],'expected_policy_revision':approved['revision']}
    advance=route._advance
    monkeypatch.setattr(route,'_advance',lambda *a:None)
    parent=turn_admission.new_session(root,'p','claude','haiku','low')
    _StubTurn.instructions[parent['id']]=[('work_delivery',wire)]
    started=turn_admission.start_turn(root,{'project':'p','session_id':parent['id'],'mode':'work','text':'Request the saved author review policy.','request_id':'parent-public-1'})
    job=turn_jobs._JOBS[started['turn_id']]
    with job['condition']:assert job['condition'].wait_for(lambda:job['done'],timeout=12)
    observed=next(r for r in _StubTurn.observed if r['turn_id']==started['turn_id'])
    assert not observed['tool_failures'] and observed['calls'][0]['operation']=='work_delivery'
    lookup=route.status(root,'p',{'work_id':'review-claim','request_id':wire['request_id']})
    assert lookup['effect']=='RECORDED'
    monkeypatch.setattr(route,'_advance',advance)
    recovered=route.recover(root,'p',{'work_id':'review-claim','route_id':lookup['aggregate']['route_id']},HUMAN)
    aggregate=recovered['aggregate']
    assert all(e['event']['continuation']['parent_session_id']==parent['id'] and
               e['event']['continuation']['parent_turn_id']==started['turn_id'] for e in aggregate['edges'])
    assert all(e['submitted_by']['turn_id']==started['turn_id'] for e in aggregate['edges'])
    retain('native-parent',{'parent':started,'observed':observed,'lookup':lookup,'recovered':recovered})


def test_actual_http_reads_and_long_public_reply_paging(prepared,monkeypatch):
    from urllib.parse import urlsplit,parse_qs
    from laplace.web import project_work_surface
    root,payload,saved,policy=prepared
    full='A public bounded review.\n'+('Evidence applies only to this exact claim.\n'*220)+'FULL PUBLIC END'
    class LongReview(_StubTurn):
        def run(self,prompt):
            result=super().run(prompt)
            return {**result,'text':full}
    monkeypatch.setattr(provider,'WritingTurn',LongReview)
    def http(method,url,wire=None):
        parsed=urlsplit(url)
        code,_ctype,body=project_work_surface.handle(parsed.path,parse_qs(parsed.query),method,
            json.dumps(wire).encode() if wire is not None else b'',repo_root=root)
        return code,json.loads(body)
    wire=submit_payload(root,saved,policy)
    code,value=http('POST','/work/delivery',{'project':'p',**wire})
    assert code==200
    value=wait_result(root,value['route_id'])
    code,read=http('GET',value['read']['http']['url'])
    assert code==200 and read['route_id']==value['route_id']
    for edge in read['edges']:
        assert len(edge['event']['result']['text'])==300 and edge['event']['result']['complete'] is False
        handle=edge['public_reply_read'];parts=[]
        while handle:
            page=session_reads.public_message(root,handle['sdk']['payload']);parts.append(page['content']);handle=page['next_read']
        assert ''.join(parts)==full
    code,refused=http('GET','/work/delivery?project=p&request='+__import__('urllib.parse',fromlist=['quote']).quote(json.dumps(wire)))
    assert code!=200 and 'inspection only' in refused['error']
    retain('http-full-reply',{'aggregate':read,'complete_reply_characters':len(full),'last_page':page,'get_mutation_refusal':refused})


def test_policy_published_route_interrupted_is_unknown_until_exact_retry(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    real=route._record_route
    monkeypatch.setattr(route,'_record_route',lambda *a:(_ for _ in ()).throw(OSError('route append interrupted')))
    wire=submit_payload(root,saved,policy)
    with pytest.raises(OSError,match='interrupted'):route.handle(root,'p',wire,HUMAN)
    partial=route.status(root,'p',{'work_id':'review-claim','request_id':wire['request_id']})
    assert partial['effect']=='UNKNOWN' and partial['policy']['approved_by']=='author'
    monkeypatch.setattr(route,'_record_route',real)
    result=route.handle(root,'p',wire,HUMAN)
    value=wait_result(root,result['route_id'])
    assert value['allowance']['reserved']==2 and value['allowance']['admitted']==2
    retain('route-publication-uncertainty',{'lookup':partial,'recovered':result,'aggregate':value})


def test_actual_reviewer_verdict_and_origin_currentness_remain_separate(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    class ReviewingTurn(_StubTurn):
        def run(self,prompt):
            task=work._tasks('p',self.root)['review-claim']
            event=next(r for r in reversed(task['deliveries']) if r.get('session_id')==self.session_id)
            handoff=next(r for r in task['phases'] if r['id']==event['handoff_id'])
            _StubTurn.instructions[self.session_id]=[('author_history',{'id':saved['origin_ref']['correction_id']}),('work_review',{'id':task['id'],'phase':'review',
                'request_id':'review-'+self.session_id,'expected_work_revision':guard(self.root),
                'handoff_id':handoff['id'],'obligation_id':event['obligation_id'],'verdict':'ACCEPT','pins':handoff['pins']})]
            return super().run(prompt)
    monkeypatch.setattr(provider,'WritingTurn',ReviewingTurn)
    result=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    value=wait_result(root,result['route_id'])
    assert all(not row['tool_failures'] for row in _StubTurn.observed)
    assert all(e['event']['acceptance']['satisfied'] and e['event']['acceptance']['by_this_delivery'] for e in value['edges'])
    original=authoring.correction_origin('p',saved['origin_ref'],root)
    assert original['correction']['status']=='open' and work._tasks('p',root)['review-claim']['status']!='done'
    (root/'p/manuscript/main.tex').write_text('Changed source after review.\n')
    observed=route.aggregate(root,'p','review-claim',result['route_id'])
    assert all(e['event']['acceptance']['currentness']=='STALE' and e['event']['result']['available'] for e in observed['edges'])
    retain('actual-review-verdict',{'current':value,'after_source_change':observed,'calls':_StubTurn.observed})


def test_cancel_reconciles_lost_wt_ack_without_transport_and_reviewer_cannot_enlarge(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    real=turn_admission.start_work_delivery_turn;actual=[]
    def lose(root,wire,event):
        value=real(root,wire,event);actual.append(value)
        raise OSError('lost actual acknowledgement')
    monkeypatch.setattr(turn_admission,'start_work_delivery_turn',lose)
    result=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    monkeypatch.setattr(turn_admission,'start_work_delivery_turn',lambda *a:pytest.fail('cancel must never transport'))
    cancelled=route.cancel(root,'p',{'work_id':'review-claim','route_id':result['route_id']},HUMAN)
    assert cancelled['aggregate']['state']=='cancelled' and cancelled['aggregate']['allowance']['admitted']==2
    assert len(actual)==2
    with pytest.raises(ValueError,match='stopped'):
        route.handle(root,'p',submit_payload(root,saved,policy,'after-cancel-public-1'),HUMAN)
    review_actor={'origin':'native','turn_id':actual[0]['turn_id']}
    with pytest.raises(ValueError,match='Only the author'):
        route.policy_save(root,'p',{'work_id':'review-claim','expected_work_revision':guard(root),'request_id':'forged-policy-public-1','policy':policy},review_actor)
    with pytest.raises(ValueError,match='Reviewers cannot'):
        route.recover(root,'p',{'work_id':'review-claim','route_id':result['route_id']},review_actor)


def test_expired_one_binding_refuses_only_that_reserved_edge(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    actual=delivery._deliver
    monkeypatch.setattr(delivery,'_deliver',lambda *a:None)
    result=route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    task=work._tasks('p',root)['review-claim']
    old=delivery._latest(task,delivery.BINDING,policy['recipients'][0]['recipient_binding_id'])
    work._append(root,{**old,'expires_at':'2000-01-01T00:00:00+00:00'})
    monkeypatch.setattr(delivery,'_deliver',actual)
    value=route.recover(root,'p',{'work_id':'review-claim','route_id':result['route_id']},HUMAN)['aggregate']
    assert value['allowance']['reserved']==2 and value['allowance']['admitted']==1 and value['allowance']['remaining']==0
    first,second=value['edges']
    assert first['event']['state']=='STALE' and not first['event'].get('admitted')
    assert second['event']['admitted'] and first['event']['id']!=second['event']['id']
    retain('binding-locality',value)


def test_pending_edge_keeps_its_own_policy_basis_after_new_generation(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    old=route.policy_save(root,'p',{'work_id':'review-claim','expected_work_revision':guard(root),
        'request_id':'old-policy-public-1','policy':policy},HUMAN)['policy']
    wire={'action':'route-submit','work_id':'review-claim','expected_work_revision':guard(root),'request_id':'old-route-public-1',
        'origin':saved['origin_ref'],'policy_id':old['id'],'expected_policy_revision':old['revision']}
    actual=delivery._deliver;monkeypatch.setattr(delivery,'_deliver',lambda *a:None)
    first=route.handle(root,'p',wire,HUMAN)
    route.policy_save(root,'p',{'work_id':'review-claim','expected_work_revision':guard(root),
        'request_id':'old-policy-update-1','policy_id':old['id'],'expected_policy_revision':old['revision'],
        'policy':{**policy,'limits':{**policy['limits'],'runtime_seconds':12}}},HUMAN)
    new=route.policy_save(root,'p',{'work_id':'review-claim','expected_work_revision':guard(root),
        'request_id':'new-policy-public-1','policy':{**policy,'recipients':policy['recipients'][:1],
        'limits':{**policy['limits'],'max_new_admissions':3,'runtime_seconds':15}}},HUMAN)['policy']
    monkeypatch.setattr(delivery,'_deliver',actual)
    second=route.handle(root,'p',{**wire,'request_id':'new-route-public-1','policy_id':new['id'],
        'expected_policy_revision':new['revision']},HUMAN)['aggregate']
    assert second['route_id']==first['route_id'] and second['allowance']['reserved']==3
    assert second['allowance']['admitted']==1
    assert all(edge['event']['state']=='STALE' and edge['policy_basis']['id']==old['id'] for edge in second['edges'][:2])
    assert second['edges'][2]['policy_basis']=={'id':new['id'],'revision':new['revision']}
    assert second['edges'][2]['execution_limits']['runtime_seconds']==15
    retain('per-edge-policy-basis',second)


# ---------------------------------------------------------------- exact original-request association and settlement

def policy_wire(root,policy,request):
    return {'action':'policy-save','work_id':'review-claim','expected_work_revision':guard(root),'request_id':request,'policy':policy}


def compare(root,wire,kind='route',door=HUMAN,request=None):
    return route.handle(root,'p',{'action':'route-status','work_id':'review-claim','request_id':request or wire['request_id'],
                                  'request_kind':kind,'submission':copy.deepcopy(wire)},door)


def settle_wire(wire,kind='route'):
    return {'action':'request-settle','work_id':'review-claim','request_kind':kind,'request_id':wire['request_id'],
            'submission':copy.deepcopy(wire)}


def settlements(root):
    return [row for row in work._tasks('p',root)['review-claim'].get('deliveries') or () if row.get('kind')==route.SETTLEMENT]


def raw_sha(wire):
    import hashlib
    return 'sha256:'+hashlib.sha256(json.dumps(wire,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _thread(outcome,key,fn):
    import threading
    def run():
        try:outcome[key]=fn()
        except Exception as error:outcome[key]=error
    worker=threading.Thread(target=run);worker.start()
    return worker


def test_request_association_is_owner_domain_pure_and_refuses_foreign_kind_and_changed_intent(prepared,monkeypatch):
    from urllib.parse import urlsplit,parse_qs
    from laplace.web import project_work_surface
    root,payload,saved,policy=prepared
    calls=[];monkeypatch.setattr(delivery,'_deliver',lambda *a:calls.append(a))
    wire=submit_payload(root,saved,policy,request='assoc-route-public-1')
    rows_before=len(work._tasks('p',root)['review-claim'].get('deliveries') or ())
    legacy=route.status(root,'p',{'work_id':'review-claim','request_id':wire['request_id']})
    assert legacy['effect']=='NONE' and legacy['compare']['requires']==['submission'] and legacy['compare']['field']=='submission'
    assert legacy['compare']['read']['payload']=={'action':'route-status','work_id':'review-claim','request_id':wire['request_id'],'request_kind':'route'}
    absent=compare(root,wire)
    assert absent['effect']=='NONE' and absent['association']=={'schema_version':route.ASSOCIATION,'kind':'route','project':'p',
        'context':'review-claim','request_id':wire['request_id'],'state':'UNRECORDED','intent_sha256':route._request_intent(wire)}
    assert absent['association']['intent_sha256']!=raw_sha(wire)
    assert absent['settle']['permitted'] and absent['settle']['requires']==['submission'] and absent['settle']['authority']=='human'
    assert absent['settle']['payload']=={'project':'p','action':'request-settle','work_id':'review-claim','request_kind':'route','request_id':wire['request_id']}
    assert len(work._tasks('p',root)['review-claim'].get('deliveries') or ())==rows_before and not calls
    result=route.handle(root,'p',copy.deepcopy(wire),HUMAN)
    transported=len(calls)
    recorded=compare(root,wire)
    assert recorded['effect']=='RECORDED' and recorded['association']['state']=='MATCH' and recorded['route_id']==result['route_id']
    assert not recorded['settle']['permitted'] and 'cannot cancel' in recorded['settle']['reason']
    changed={**wire,'recipients':policy['recipients'][:1]}
    mismatch=compare(root,changed)
    assert mismatch['effect']=='MISMATCH' and mismatch['association']['state']=='MISMATCH' and 'route_id' not in mismatch and 'aggregate' not in mismatch
    assert mismatch['association']['intent_sha256']==route._request_intent(changed) and not mismatch['settle']['permitted']
    with pytest.raises(ValueError,match='nothing was settled'):route.handle(root,'p',settle_wire(changed),HUMAN)
    for forged in ({**wire,'work_id':'other-work'},{**wire,'project':'q'},{**wire,'request_id':'assoc-route-public-2'}):
        with pytest.raises(ValueError,match='another project'):compare(root,forged,request=wire['request_id'])
    with pytest.raises(ValueError,match='closed owner contract'):compare(root,wire,kind='policy')
    with pytest.raises(ValueError,match='closed owner contract'):compare(root,{**wire,'by':'author'})
    pwire=policy_wire(root,policy,'assoc-policy-public-1')
    none=compare(root,pwire,'policy')
    assert none['association']['state']=='UNRECORDED' and none['association']['intent_sha256']==delivery._digest(policy)!=raw_sha(pwire)
    kept=route.handle(root,'p',copy.deepcopy(pwire),HUMAN)['policy']
    match=compare(root,pwire,'policy')
    assert match['effect']=='RECORDED' and match['association']['state']=='MATCH' and match['policy']['id']==kept['id']
    other=compare(root,{**pwire,'policy':{**policy,'limits':{**policy['limits'],'max_new_admissions':3}}},'policy')
    assert other['association']['state']=='MISMATCH' and 'policy' not in other
    template=legacy['compare'];url=urlsplit(template['read']['http']['url']);query=parse_qs(url.query)
    issued=json.loads(query['request'][0]);issued[template['field']]=wire;query['request']=[json.dumps(issued)]
    code,_ctype,body=project_work_surface.handle(url.path,query,'GET',b'',repo_root=root)
    assert code==200 and json.loads(body)['association']==recorded['association']
    assert len(calls)==transported   # pure comparisons never transported anything
    retain('request-association',{'legacy':legacy,'absent':absent,'recorded':recorded,'mismatch':mismatch,'policy':match})


def test_settled_original_request_fences_late_submit_and_policy_before_stale_cas_without_effects(prepared,monkeypatch):
    from urllib.parse import urlsplit
    from laplace.web import project_work_surface
    root,payload,saved,policy=prepared
    calls=[];monkeypatch.setattr(delivery,'_deliver',lambda *a:calls.append(a))
    unrelated=route.handle(root,'p',submit_payload(root,saved,policy,request='unrelated-route-public-1'),HUMAN)
    before=len(calls);task=work._tasks('p',root)['review-claim']
    reservations=copy.deepcopy(route._route_for(task,unrelated['route_id'])['reservations'])
    stale={**submit_payload(root,saved,policy,request='settle-route-public-1'),'expected_work_revision':'sha256:'+'0'*64}
    with pytest.raises(ValueError,match='CHANGED_INPUT'):route.handle(root,'p',copy.deepcopy(stale),HUMAN)
    observed=compare(root,stale)
    assert observed['association']['state']=='UNRECORDED' and observed['settle']['outcome_scope']=='request'
    settled=route.handle(root,'p',settle_wire(stale),HUMAN)
    assert settled['effect']=='NOT_ADMITTED' and settled['terminal'] and settled['settled'] and settled['association']['state']=='MATCH'
    assert settled['settlement']['outcome_scope']=='request' and settled['preserved_effects']==[] and settled['settlement']['by']=='author'
    [row]=settlements(root)
    assert row['intent_sha256']==route._request_intent(stale) and row['actor']['origin']=='human' and row['record']=='project-work-phase'
    late=route.handle(root,'p',copy.deepcopy(stale),HUMAN)
    assert late['effect']=='NOT_ADMITTED' and late['terminal'] and late['replayed'] and late['settlement']['id']==row['id']
    task=work._tasks('p',root)['review-claim']
    assert all(stale['request_id'] not in r.get('requests',{}) for r in route._rows(task,route.ROUTE))
    assert route._route_for(task,unrelated['route_id'])['reservations']==reservations and len(calls)==before
    manual='manual:'+delivery._digest(stale['request_id'])[7:39]
    assert not [r for r in route._rows(task,route.POLICY) if r.get('request_id')==manual]
    again=route.handle(root,'p',settle_wire(stale),HUMAN)
    assert again['effect']=='NOT_ADMITTED' and not again['settled'] and len(settlements(root))==1
    with pytest.raises(ValueError,match='another exact intent'):route.handle(root,'p',{**stale,'recipients':policy['recipients'][:1]},HUMAN)
    assert route.status(root,'p',{'work_id':'review-claim','request_id':stale['request_id']})['effect']=='NOT_ADMITTED'
    pwire={**policy_wire(root,policy,'settle-policy-public-1'),'expected_work_revision':'sha256:'+'0'*64}
    action=compare(root,pwire,'policy')['settle'];url=urlsplit(action['http']['url'])
    code,_ctype,body=project_work_surface.handle(url.path,{},action['http']['method'],
        json.dumps({**action['payload'],'submission':pwire}).encode(),repo_root=root)
    http=json.loads(body)
    assert code==200 and http['effect']=='NOT_ADMITTED' and http['settled'] and http['association']['kind']=='policy',http
    late_policy=route.handle(root,'p',copy.deepcopy(pwire),HUMAN)
    assert late_policy['effect']=='NOT_ADMITTED' and late_policy['terminal']
    assert not [r for r in route._rows(work._tasks('p',root)['review-claim'],route.POLICY) if r.get('request_id')==pwire['request_id']]
    with pytest.raises(ValueError,match='another exact intent'):
        route.handle(root,'p',{**pwire,'policy':{**policy,'limits':{**policy['limits'],'runtime_seconds':11}}},HUMAN)
    retain('request-settlement-fence',{'settled':settled,'late':late,'policy_http':http,'late_policy':late_policy})


def test_submit_wins_the_shared_dispatch_lock_and_settlement_reports_recorded(prepared,monkeypatch):
    import threading
    root,payload,saved,policy=prepared
    monkeypatch.setattr(delivery,'_deliver',lambda *a:None)
    wire=submit_payload(root,saved,policy,request='race-submit-public-1')
    inside,release,outcome=threading.Event(),threading.Event(),{}
    real=route._record_route
    def paused(root_,row):
        if wire['request_id'] in row.get('requests',{}) and not inside.is_set():
            inside.set();assert release.wait(10)
        return real(root_,row)
    monkeypatch.setattr(route,'_record_route',paused)
    submitter=_thread(outcome,'submit',lambda:route.handle(root,'p',copy.deepcopy(wire),HUMAN))
    assert inside.wait(10)
    settler=_thread(outcome,'settle',lambda:route.handle(root,'p',settle_wire(wire),HUMAN))
    time.sleep(.4)
    assert settler.is_alive() and 'settle' not in outcome   # the shared dispatch lock holds settlement out
    release.set();submitter.join(15);settler.join(15)
    assert outcome['submit']['effect']=='route_recorded' and outcome['settle']['effect']=='RECORDED',outcome
    assert not outcome['settle']['settled'] and outcome['settle']['association']['state']=='MATCH' and not settlements(root)
    row=route._route_for(work._tasks('p',root)['review-claim'],outcome['submit']['route_id'])
    assert wire['request_id'] in row['requests'] and len(row['reservations'])==2


def test_settlement_wins_the_shared_dispatch_lock_and_late_original_submit_has_no_effect(prepared,monkeypatch):
    import threading
    root,payload,saved,policy=prepared
    calls=[];monkeypatch.setattr(delivery,'_deliver',lambda *a:calls.append(a))
    wire=submit_payload(root,saved,policy,request='race-settle-public-1')
    inside,release,outcome=threading.Event(),threading.Event(),{}
    real=work._append
    def paused(root_,row,**kwargs):
        if row.get('kind')==route.SETTLEMENT and not inside.is_set():
            inside.set();assert release.wait(10)
        return real(root_,row,**kwargs)
    monkeypatch.setattr(work,'_append',paused)
    settler=_thread(outcome,'settle',lambda:route.handle(root,'p',settle_wire(wire),HUMAN))
    assert inside.wait(10)
    submitter=_thread(outcome,'submit',lambda:route.handle(root,'p',copy.deepcopy(wire),HUMAN))
    time.sleep(.4)
    assert submitter.is_alive() and 'submit' not in outcome   # held out by the same dispatch lock
    release.set();settler.join(15);submitter.join(15)
    assert outcome['settle']['settled'] and outcome['submit']['effect']=='NOT_ADMITTED' and outcome['submit']['terminal'],outcome
    task=work._tasks('p',root)['review-claim']
    assert not route._rows(task,route.ROUTE) and not route._rows(task,route.POLICY) and not delivery._rows(task,delivery.EVENT) and not calls


def test_partial_manual_policy_settles_route_admission_only_preserving_policy_and_ambiguity_stays_unknown(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    calls=[];monkeypatch.setattr(delivery,'_deliver',lambda *a:calls.append(a))
    real=route._record_route
    def interrupted(*a):raise OSError('route append interrupted')
    def partial(request):
        wire=submit_payload(root,saved,policy,request=request)
        monkeypatch.setattr(route,'_record_route',interrupted)
        with pytest.raises(OSError,match='interrupted'):route.handle(root,'p',copy.deepcopy(wire),HUMAN)
        monkeypatch.setattr(route,'_record_route',real)
        manual='manual:'+delivery._digest(request)[7:39]
        return wire,next(r for r in route._rows(work._tasks('p',root)['review-claim'],route.POLICY) if r['request_id']==manual)
    wire,kept=partial('partial-route-public-1')
    legacy=route.status(root,'p',{'work_id':'review-claim','request_id':wire['request_id']})
    assert legacy['effect']=='UNKNOWN' and legacy['policy']['id']==kept['id']
    observed=compare(root,wire)
    assert observed['effect']=='UNKNOWN' and observed['association']['state']=='UNKNOWN' and observed['settle']['permitted']
    assert observed['settle']['outcome_scope']=='route-admission-only'
    assert [(e['kind'],e['id'],e['revision']) for e in observed['preserved_effects']]==[(route.POLICY,kept['id'],kept['revision'])]
    changed={**wire,'policy':{**policy,'limits':{**policy['limits'],'runtime_seconds':11}}}
    assert compare(root,changed)['association']['state']=='MISMATCH'
    with pytest.raises(ValueError,match='nothing was settled'):route.handle(root,'p',settle_wire(changed),HUMAN)
    settled=route.handle(root,'p',settle_wire(wire),HUMAN)
    assert settled['effect']=='NOT_ADMITTED' and settled['settled'] and settled['settlement']['outcome_scope']=='route-admission-only'
    assert settled['preserved_effects']==observed['preserved_effects'] and 'preserved_effects' in settled['meaning']
    task=work._tasks('p',root)['review-claim']
    assert route._latest(task,route.POLICY,kept['id'])==kept   # the partial policy is preserved, never deleted or refunded
    late=route.handle(root,'p',copy.deepcopy(wire),HUMAN)
    assert late['effect']=='NOT_ADMITTED' and late['preserved_effects']==settled['preserved_effects']
    assert not route._rows(work._tasks('p',root)['review-claim'],route.ROUTE) and not calls
    other,row=partial('partial-route-public-2')
    work._append(root,{**row,'id':'FP-forged-ambiguous-1','revision':'sha256:'+'f'*64,'ts':delivery._now()})
    ambiguous=compare(root,other)
    assert ambiguous['effect']=='UNKNOWN' and ambiguous['association']['state']=='UNKNOWN' and not ambiguous['settle']['permitted']
    held=route.handle(root,'p',settle_wire(other),HUMAN)
    assert held['effect']=='UNKNOWN' and not held['settled'] and len(settlements(root))==1
    retain('partial-policy-settlement',{'observed':observed,'settled':settled,'late':late,'ambiguous':ambiguous})


def test_settlement_without_confirmed_readback_stays_unknown_and_a_written_row_is_confirmed(prepared,monkeypatch):
    root,payload,saved,policy=prepared
    wire=submit_payload(root,saved,policy,request='readback-route-public-1')
    real=work._append
    def refused(root_,row,**kwargs):
        if row.get('kind')==route.SETTLEMENT:raise OSError('ledger unavailable')
        return real(root_,row,**kwargs)
    monkeypatch.setattr(work,'_append',refused)
    held=route.handle(root,'p',settle_wire(wire),HUMAN)
    assert held['effect']=='UNKNOWN' and not held['settled'] and 'ledger unavailable' in held['reason'] and not settlements(root)
    def lost(root_,row,**kwargs):
        value=real(root_,row,**kwargs)
        if row.get('kind')==route.SETTLEMENT:raise OSError('acknowledgement lost')
        return value
    monkeypatch.setattr(work,'_append',lost)
    confirmed=route.handle(root,'p',settle_wire(wire),HUMAN)
    assert confirmed['effect']=='NOT_ADMITTED' and confirmed['settled'] and len(settlements(root))==1


def test_actual_native_reviewer_and_producer_inspect_purely_and_neither_can_settle(prepared,monkeypatch):
    from laplace.writing import reads
    root,payload,saved,policy=prepared
    probe=submit_payload(root,saved,policy,request='role-probe-public-1')
    inspect={'action':'route-status','work_id':'review-claim','request_id':probe['request_id'],'request_kind':'route','submission':probe}
    class Inspecting(_StubTurn):
        def run(self,prompt):
            _StubTurn.instructions[self.session_id]=[('work_delivery',copy.deepcopy(inspect)),('work_delivery',settle_wire(probe))]
            return super().run(prompt)
    monkeypatch.setattr(provider,'WritingTurn',Inspecting)
    result=route.handle(root,'p',submit_payload(root,saved,policy,request='role-route-public-1'),HUMAN)
    wait_result(root,result['route_id'])
    parent=turn_admission.new_session(root,'p','claude','haiku','low')
    started=turn_admission.start_turn(root,{'project':'p','session_id':parent['id'],'mode':'work','text':'Inspect and try to settle.','request_id':'role-parent-public-1'})
    job=turn_jobs._JOBS[started['turn_id']]
    with job['condition']:assert job['condition'].wait_for(lambda:job['done'],timeout=12)
    # Each actual turn (two review-mode reviewers, one work-mode producer) ran both calls: the pure association
    # succeeded and the settlement was refused (review-role effect gate or the owner's human-only door).
    turns=[r for r in _StubTurn.observed if r.get('calls') or r.get('tool_failures')]
    assert len(turns)==3 and started['turn_id'] in {r['turn_id'] for r in turns},_StubTurn.observed
    assert sorted(r['mode'] for r in turns)==['review','review','work']
    for observed in turns:
        assert len(observed['tool_failures'])==1 and len(observed['calls'])>=1,observed
        refusal=json.dumps(observed['tool_failures'],default=str)
        expected='Independent review can save findings' if observed['mode']=='review' else 'Only the author may settle'
        assert expected in refusal and observed['tool_failures'][0]['operation']=='work_delivery',observed
    assert not settlements(root)
    assert reads.effect('work_delivery',inspect)=='read'
    assert all(reads.effect('work_delivery',{'action':a})=='write' for a in ('request-settle','route-submit','policy-save','route-recover','route-cancel'))
    for forged in ({**settle_wire(probe),'by':'human'},{**settle_wire(probe),'actor':{'origin':'human'}}):
        with pytest.raises(ValueError,match='closed owner contract'):route.handle(root,'p',forged,HUMAN)
    with pytest.raises(ValueError,match='Only the author'):route.settle(root,'p',settle_wire(probe),{'origin':'native','turn_id':started['turn_id']})
    contract=delivery.contract()
    assert 'request-settle' in contract['properties']['action']['enum'] and contract['properties']['submission']=={'type':'object'}
    retain('request-settlement-roles',{'turns':turns})
