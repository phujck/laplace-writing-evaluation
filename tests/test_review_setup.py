"""Existing Work setup, exact approval renewal, and preserved delivery custody."""
import copy
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from laplace.work import project_work as work, work_delivery as delivery, review_setup as setup

HUMAN = {'origin':'human'}


def retain(name,value):
    home=os.environ.get('REVIEW_SETUP_EVIDENCE')
    if home:
        path=Path(home);path.mkdir(parents=True,exist_ok=True)
        (path/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False))


def tree(root):
    (root/'p/manuscript').mkdir(parents=True)
    (root/'p/manuscript/main.tex').write_text('Public numerical claim.\n')
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'conceptric','project_dir':'p','tex_root':'p/manuscript'}]}))
    voice=root/'profiles/voice/gerard-technical-v1.md';voice.parent.mkdir(parents=True)
    voice.write_text('Public synthetic fixture voice. Use concrete language.\n')
    work.task('p',{'id':'existing','title':'Review the numerical claim','goal':'Check the assumptions and boundary.'},root)
    return root


def guard(root):return work._task_revision(work._tasks('p',root)['existing'])


def binding(root,label='Assumptions',expired=False,kind='app-owned'):
    # An explicit synthetic old clock creates a genuinely expired first approval.
    import unittest.mock
    with unittest.mock.patch.object(delivery.time,'time',return_value=1_600_000_000) if expired else __import__('contextlib').nullcontext():
        return delivery.bind(root,'p',{'work_id':'existing','expected_work_revision':guard(root),'kind':kind,
            **({'provider':'claude','model':'haiku','effort':'low'} if kind=='app-owned' else {'external':{'actor':'Public external reviewer'}}),
            'label':label,'lifetime_s':60},HUMAN)['binding']


def renewal(root,old,request='renew-public-1'):
    return {'action':'renew','work_id':'existing','recipient_binding_id':old['id'],
        'expected_work_revision':guard(root),'expected_binding_revision':old['revision'],
        'request_id':request,'lifetime_s':3600}


def test_unmanaged_pure_setup_then_lossless_specialised_question_save(tmp_path):
    root=tree(tmp_path)
    before=(root/'corpus_friction/work_orders.jsonl').read_bytes()
    empty=delivery.handle(root,'p',{'action':'review-setup','work_id':'existing'},HUMAN)
    assert empty['review_obligations']==[] and empty['bindings']['total']==0
    assert empty['actions']['save_questions']['permitted'] and empty['actions']['bind']['permitted']
    assert empty['actions']['bind']['defaults']['effort']['value']=='medium'
    assert empty['actions']['bind']['defaults']['lifetime_s']['value']==604800
    assert (root/'corpus_friction/work_orders.jsonl').read_bytes()==before
    questions=[{'id':'assumptions','label':'Assumptions','scope':'other','required':False,'independent':True,'inputs':['p/manuscript/main.tex']},
        {'id':'closure','label':'Retain specialised closure','scope':'closure','required':True,'independent':False,'inputs':[],'closure_work_id':'retained-child'},
        {'id':'source','label':'Retain source contract','scope':'source','required':True,'independent':True,'inputs':[],
         'source_contract':{'owner':'public.owner','operation':'read','consumer':'public.native','segments':['schema']}}]
    from laplace.web import project_work_surface
    wire={**empty['actions']['save_questions']['payload'],'review_obligations':questions}
    code,_,body=project_work_surface.handle('/work/task',{},'POST',json.dumps(wire).encode(),repo_root=root)
    assert code==201,body
    complete=setup.prepare(root,'p',{'work_id':'existing'},HUMAN)
    assert complete['review_obligations']==questions
    assert complete['question_controls']['assumptions']['editable']
    assert not complete['question_controls']['closure']['editable'] and not complete['question_controls']['source']['editable']
    from laplace.core import admission
    from laplace.writing.schemas import SCHEMAS
    admission.admit_owner_payload('task',complete['actions']['save_questions']['payload'],SCHEMAS['task'],project='p')
    assert complete['work']['revision']!=empty['work']['revision']
    assert not (root/'contract/talk.jsonl').exists()
    retain('unmanaged-and-specialised',{'unmanaged':empty,'saved_result':json.loads(body),'complete':complete})


def test_expired_binding_same_identity_renewal_and_exact_request_replay(tmp_path):
    root=tree(tmp_path);old=binding(root,expired=True)
    preview=setup.prepare(root,'p',{'work_id':'existing'},HUMAN)
    assert preview['bindings']['items'][0]['approval']['state']=='EXPIRED'
    assert preview['bindings']['items'][0]['actions']['renew']['permitted']
    wire=renewal(root,old);before=setup.request(root,'p',{'work_id':'existing','request_id':wire['request_id']})
    first=setup.renew(root,'p',wire,HUMAN)
    assert before['effect']=='NONE' and first['binding']['id']==old['id'] and first['binding']['revision']!=old['revision']
    assert first['previous_revision']==old['revision'] and first['binding']['expires_at']!=old['expires_at']
    assert setup.approval(first['binding'])['state']=='CURRENT'
    current=setup.prepare(root,'p',{'work_id':'existing'},HUMAN)
    assert current['bindings']['total']==1 and current['bindings']['items'][0]['binding']==first['binding']
    work.task('p',{'id':'existing','expected_work_revision':guard(root),'title':'Later title'},root)
    replay=setup.renew(root,'p',wire,HUMAN)
    assert replay['replayed'] and replay['binding']==first['binding']
    lookup=setup.request(root,'p',{'work_id':'existing','request_id':wire['request_id']})
    assert lookup['effect']=='RECORDED' and lookup['receipt']['binding']==first['binding']
    with pytest.raises(ValueError,match='another intent'):
        setup.renew(root,'p',{**wire,'lifetime_s':7200},HUMAN)
    assert binding(root)==first['binding']  # same settings do not extend expiry again
    intended={'kind':'app-owned','provider':'claude','model':'haiku','effort':'low','label':'Assumptions','lifetime_s':60}
    match=setup.prepare(root,'p',{'work_id':'existing','intended_binding':intended},HUMAN)
    assert match['matching_binding']['state']=='MATCHED' and match['matching_binding']['binding']==first['binding']
    assert not (root/'contract/talk.jsonl').exists()
    retain('expired-renewal',{'expired_setup':preview,'wire':wire,'before':before,'renewed':first,'current_setup':current,'replay_after_work_change':replay,'lookup':lookup,'matching':match})


def test_unique_binding_pagination_change_cut_and_external_visibility(tmp_path):
    root=tree(tmp_path)
    for i in range(19):binding(root,label='Reviewer '+str(i),expired=i==3)
    external=binding(root,label='External',kind='external')
    first=setup.prepare(root,'p',{'work_id':'existing','limit':7},HUMAN)
    assert first['bindings']['total']==20 and not first['bindings']['complete']
    pages=[first];ids=[]
    while True:
        page=pages[-1];ids.extend(item['binding']['id'] for item in page['bindings']['items'])
        if not page['bindings']['next_read']:break
        pages.append(delivery.handle(root,'p',page['bindings']['next_read']['payload'],HUMAN))
    assert len(ids)==len(set(ids))==20 and pages[-1]['bindings']['complete']
    unsupported=next(item for page in pages for item in page['bindings']['items'] if item['binding']['id']==external['id'])
    assert unsupported['approval']['state']=='UNSUPPORTED' and not unsupported['actions']['renew']['permitted']
    old=next(item['binding'] for item in first['bindings']['items'] if item['binding']['kind']=='app-owned')
    setup.renew(root,'p',renewal(root,old),HUMAN)
    with pytest.raises(work.WorkConflict) as changed:
        delivery.handle(root,'p',first['bindings']['next_read']['payload'],HUMAN)
    assert changed.value.details['field']=='cut' and changed.value.details['next_reads'][0]['payload']['action']=='review-setup'
    latest=setup.prepare(root,'p',{'work_id':'existing'},HUMAN)
    assert latest['bindings']['total']==20
    from laplace.work import feedback_route
    view=feedback_route.preview(root,'p',{'work_id':'existing'},HUMAN)
    assert len({row['id'] for row in view['bindings']})==len(view['bindings']) and view['bindings_coverage']['total']==20
    assert not view['bindings_coverage']['complete']
    retain('binding-pages',{'first':first,'pages':pages,'restart':latest,'route_preview':view,'changed_cut':changed.value.details})


def test_renewal_concurrent_prior_revision_and_actual_schema_bounds(tmp_path):
    root=tree(tmp_path);old=binding(root,expired=True)
    wires=[renewal(root,old,'concurrent-renew-'+str(i)) for i in range(2)]
    def attempt(wire):
        try:return setup.renew(root,'p',wire,HUMAN)
        except work.WorkConflict as error:return {'conflict':error.details}
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(attempt,wires))
    assert sum(value.get('effect')=='renewed' for value in out)==1
    assert sum('conflict' in value for value in out)==1
    successful=next(value for value in out if value.get('effect'))
    current=successful['binding'];wire=renewal(root,current,'next-valid-renew')
    for value in (0,-1,59,True,delivery.MAX_BINDING_LIFETIME_S+1):
        with pytest.raises(ValueError):setup.renew(root,'p',{**wire,'lifetime_s':value},HUMAN)
    for changed in ({'expected_binding_revision':old['revision']},{'expected_work_revision':'sha256:'+'a'*64}):
        with pytest.raises(work.WorkConflict):setup.renew(root,'p',{**wire,**changed},HUMAN)
    with ThreadPoolExecutor(max_workers=2) as pool:same=list(pool.map(lambda _:setup.renew(root,'p',wire,HUMAN),range(2)))
    assert same[0]['binding']==same[1]['binding'] and sum(bool(row['replayed']) for row in same)==1
    rows=work._tasks('p',root)['existing']['deliveries']
    assert len([row for row in rows if row.get('approval')])==2
    retain('concurrent-renewal',{'outcomes':out,'same_request':same,'current':setup.prepare(root,'p',{'work_id':'existing'},HUMAN)})


def test_native_read_is_passive_with_no_mutation_permission_and_renew_remains_write(tmp_path):
    root=tree(tmp_path);old=binding(root,expired=True)
    from laplace.native import tools
    from laplace.writing.reads import effect
    before=(root/'corpus_friction/work_orders.jsonl').read_bytes()
    read=tools.execute(root,'p','review','work_delivery',{'action':'review-setup','work_id':'existing'},turn_id=None)
    assert effect('work_delivery',{'action':'review-setup'})=='read'
    assert effect('work_delivery',{'action':'renew-request'})=='read'
    assert effect('work_delivery',{'action':'renew'})=='write'
    assert not read['actions']['save_questions']['permitted'] and not read['actions']['bind']['permitted']
    assert not read['bindings']['items'][0]['actions']['renew']['permitted']
    looked=tools.execute(root,'p','review','work_delivery',{'action':'renew-request','work_id':'existing','request_id':'native-pure-read'},turn_id=None)
    assert looked['effect']=='NONE'
    with pytest.raises(ValueError):tools.execute(root,'p','review','work_delivery',renewal(root,old),turn_id=None)
    with pytest.raises(ValueError,match='Only the human author'):
        setup.renew(root,'p',renewal(root,old),{'origin':'native','turn_id':'not-a-turn'})
    assert (root/'corpus_friction/work_orders.jsonl').read_bytes()==before
    from laplace.writing import records
    assert not records.index(root).sessions and not records.index(root).turns
    retain('native-read-control',{'setup':read,'lookup':looked})


def test_first_bind_matching_is_standing_not_request_and_post_save_guard_is_required(tmp_path):
    root=tree(tmp_path);before=setup.prepare(root,'p',{'work_id':'existing'},HUMAN)
    intended={'kind':'app-owned','provider':'claude','model':'haiku','label':'Explicit reviewer'}
    assert setup.prepare(root,'p',{'work_id':'existing','intended_binding':intended},HUMAN)['matching_binding']['state']=='NONE'
    edited={**before['actions']['save_questions']['payload'],'review_obligations':[{'id':'ordinary','label':'Read the claim','scope':'other'}]}
    work.task('p',edited,root)
    with pytest.raises(work.WorkConflict):delivery.handle(root,'p',{**before['actions']['bind']['payload'],**intended},HUMAN)
    inspected=setup.prepare(root,'p',{'work_id':'existing'},HUMAN)
    result=delivery.handle(root,'p',{**inspected['actions']['bind']['payload'],**intended},HUMAN)
    observed=setup.prepare(root,'p',{'work_id':'existing','intended_binding':intended},HUMAN)
    assert observed['matching_binding']['state']=='MATCHED' and observed['matching_binding']['binding']==result['binding']
    assert 'does not attribute' in observed['matching_binding']['meaning']
    assert observed['review_obligations'][0]['required'] is True and observed['review_obligations'][0]['independent'] is True
    assert result['binding']['effort']=='medium'
    assert not (root/'contract/talk.jsonl').exists()
    retain('first-bind-standing',{'before':before,'inspected':inspected,'bound':result,'matching':observed})


from test_feedback_route import prepared  # deterministic provider seam, real origin/WD/turn owners


def routed_renewal(root,old,request):
    task=work._tasks('p',root)['review-claim']
    return {'action':'renew','work_id':task['id'],'recipient_binding_id':old['id'],
        'expected_work_revision':work._task_revision(task),'expected_binding_revision':old['revision'],
        'request_id':request,'lifetime_s':3600}


def test_renewal_never_rebinds_pending_delivery_or_refills_original_route(prepared,monkeypatch):
    from laplace.work import feedback_route
    from test_feedback_route import submit_payload,wait_result
    from laplace.writing import records
    root,payload,saved,policy=prepared;policy={**policy,'recipients':policy['recipients'][:1]}
    actual=delivery._deliver;monkeypatch.setattr(delivery,'_deliver',lambda *a:None)
    first=feedback_route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    old_event=first['aggregate']['edges'][0]['event'];old=first['aggregate']['edges'][0]['recipient']
    renewed=setup.renew(root,'p',routed_renewal(root,old,'pending-renew-public-1'),HUMAN)
    assert renewed['binding']['id']==old['id']
    monkeypatch.setattr(delivery,'_deliver',actual)
    refused=delivery.recover(root,'p',{'event_id':old_event['id']},HUMAN)['event']
    assert refused['state']=='STALE' and 'admitted' not in refused and refused['deadline_at']==old_event['deadline_at']
    assert not records.index(root).sessions and not records.index(root).turns
    fresh=feedback_route.handle(root,'p',submit_payload(root,saved,policy,'fresh-after-renew-1'),HUMAN)
    assert fresh['route_id']==first['route_id']
    value=fresh['aggregate']
    assert value['allowance']['reserved']==2 and value['allowance']['remaining']==0
    assert value['edges'][0]['event']['recipient']['revision']==old['revision']
    assert value['edges'][1]['event']['recipient']['revision']==renewed['binding']['revision']
    # Wait only for the new actually admitted event, not the intentionally stale old one.
    tid=value['edges'][1]['event']['admitted']['turn_id']
    from laplace.writing import turn_jobs
    job=turn_jobs._JOBS[tid]
    with job['condition']:assert job['condition'].wait_for(lambda:job['done'],timeout=12)
    retain('pending-original-allocation',{'first':first,'renewed':renewed,'old_recovery':refused,
        'new_preparation':feedback_route.aggregate(root,'p','review-claim',fresh['route_id'])})


def test_admitted_result_and_lost_ack_recovery_keep_original_approval_after_renew(prepared,monkeypatch):
    from laplace.work import feedback_route
    from laplace.writing import records,turn_admission,turn_jobs,session_reads
    from test_feedback_route import submit_payload,wait_result
    root,payload,saved,policy=prepared;policy={**policy,'recipients':policy['recipients'][:1]}
    actual=turn_admission.start_work_delivery_turn;admitted=[]
    def lost(root,wire,event):
        value=actual(root,wire,event);admitted.append(value)
        raise OSError('public admission acknowledgement lost')
    monkeypatch.setattr(turn_admission,'start_work_delivery_turn',lost)
    first=feedback_route.handle(root,'p',submit_payload(root,saved,policy),HUMAN)
    assert len(admitted)==1
    old=first['aggregate']['edges'][0]['recipient'];old_event=first['aggregate']['edges'][0]['event']
    renewed=setup.renew(root,'p',routed_renewal(root,old,'admitted-renew-public-1'),HUMAN)
    monkeypatch.setattr(turn_admission,'start_work_delivery_turn',lambda *a:pytest.fail('recovery must not start another turn'))
    recovered=feedback_route.recover(root,'p',{'work_id':'review-claim','route_id':first['route_id']},HUMAN)
    complete=wait_result(root,first['route_id']);event=complete['edges'][0]['event']
    assert event['admitted']['turn_id']==admitted[0]['turn_id'] and event['recipient']['revision']==old['revision']
    assert event['deadline_at']==old_event['deadline_at'] and event['admitted']['recipient_ack']=='TERMINAL'
    assert complete['allowance']['reserved']==1 and complete['allowance']['remaining']==1
    assert len(records.index(root).turns)==1
    page=delivery.status(root,'p',{'work_id':'review-claim'},HUMAN)['deliveries']
    observed=page['events'][0]
    assert observed['public_reply_read']['identity']['turn_id']==admitted[0]['turn_id']
    assert observed['exact_reply_read'] and observed['turn_read']
    read=session_reads.public_message(root,observed['public_reply_read']['sdk']['payload'])
    assert read['content']=='wrote the return this packet declared'
    current=setup.prepare(root,'p',{'work_id':'review-claim'},HUMAN)
    assert next(item['binding'] for item in current['bindings']['items'] if item['binding']['id']==old['id'])['revision']==renewed['binding']['revision']
    retain('admitted-original-approval',{'before':first,'renewed':renewed,'recovered':recovered,
        'complete':complete,'status_page':page,'full_reply':read,'current_setup':current})



def test_issued_unmanaged_work_entry_http_setup_renew_and_request_reads(tmp_path):
    from urllib.parse import urlsplit,parse_qs
    from laplace.web import project_work_surface
    root=tree(tmp_path);old=binding(root,expired=True)
    def http(handle,body=None):
        h=handle['http'];url=urlsplit(h['url'])
        code,_,raw=project_work_surface.handle(url.path,parse_qs(url.query),h['method'],
            json.dumps(body).encode() if body is not None else b'',repo_root=root)
        return code,json.loads(raw)
    code,detail=http({'http':{'method':'GET','url':'/work/state?project=p&view=detail&id=existing'}})
    assert code==200
    entry=detail['allowed_actions']['review_setup']
    code,prepared=http(entry)
    assert code==200 and prepared['review_obligations']==[]
    action=prepared['bindings']['items'][0]['actions']['renew']
    wire={**action['payload'],'request_id':'http-renew-public-1','lifetime_s':3600}
    code,renewed=http(action,wire)
    assert code==200 and renewed['effect']=='renewed'
    lookup=setup.read_handle('p',{'action':'renew-request','work_id':'existing','request_id':wire['request_id']})
    code,found=http(lookup)
    assert code==200 and found['effect']=='RECORDED' and found['receipt']['binding']==renewed['binding']
    # GET remains a pure read fence, despite sharing one existing operation.
    wrong=setup.read_handle('p',wire)
    code,refused=http(wrong)
    assert code==422 and 'inspection only' in refused['error']
    retain('http-issued-setup',{'entry':entry,'prepared':prepared,'wire':wire,'renewed':renewed,'lookup':found,'effect_get_refusal':refused})



def test_existing_event_history_next_read_has_exact_http_carrier(tmp_path,monkeypatch):
    from urllib.parse import urlsplit,parse_qs
    from laplace.web import project_work_surface
    from laplace.work import project_work_review as review
    root=tree(tmp_path)
    work.task('p',{'id':'existing','expected_work_revision':guard(root),'review_obligations':[
        {'id':'q','scope':'other','label':'Question','inputs':['p/manuscript/main.tex']}]},root)
    approved=binding(root);monkeypatch.setattr(delivery,'_deliver',lambda *a:None)
    for i in range(9):
        handoff=review.record('p',{'id':'existing','phase':'handoff','expected_work_revision':guard(root),
            'request_id':'public-handoff-'+str(i),'obligations':['q'],
            'pins':{'p/manuscript/main.tex':review._file_digest(root,'p/manuscript/main.tex')},
            'object':{'kind':'public fixture'}},root,door=HUMAN,mode='work')['phase']
        delivery.submit(root,'p',{'work_id':'existing','expected_work_revision':guard(root),'handoff_id':handoff['id'],
            'obligation_id':'q','recipient_binding_id':approved['id']},HUMAN)
    first=delivery.status(root,'p',{'work_id':'existing'},HUMAN)['deliveries']
    assert first['events_total']==9 and len(first['events'])==8
    read=first['next_read'];url=urlsplit(read['http']['url'])
    code,_,raw=project_work_surface.handle(url.path,parse_qs(url.query),'GET',repo_root=root)
    value=json.loads(raw)
    assert code==200 and len(value['deliveries']['events'])==1 and value['deliveries']['next_read'] is None
    assert read['payload']=={'action':'status','work_id':'existing','offset':8,'limit':8,'cut':first['cut']}
    from laplace.writing import records
    assert not records.index(root).sessions and not records.index(root).turns
    retain('event-http-page',{'first':first,'next':read,'second':value})


def test_public_approval_projections_cannot_mutate_retained_request_intent(tmp_path):
    root=tree(tmp_path);old=binding(root,expired=True);wire=renewal(root,old,'detached-public-1')
    renewed=setup.renew(root,'p',wire,HUMAN)
    expected=copy.deepcopy(renewed['binding'])
    ledger=root/'corpus_friction/work_orders.jsonl';raw=ledger.read_bytes()
    view=setup.prepare(root,'p',{'work_id':'existing'},HUMAN)
    found=setup.request(root,'p',{'work_id':'existing','request_id':wire['request_id']})
    canonical=delivery.latest_bindings(work._tasks('p',root)['existing'])[old['id']]
    # Setup, renewal receipt, pure lookup and shared preview projection all use this owner boundary.
    public=[view['bindings']['items'][0]['binding'],renewed['binding'],found['receipt']['binding'],
        delivery._public_binding(canonical)]
    for item in public:
        item['approval']['intent']['lifetime_s']=7200
        item['approval']['by']='caller-local'
        looked=setup.request(root,'p',{'work_id':'existing','request_id':wire['request_id']})
        assert looked['effect']=='RECORDED' and looked['receipt']['binding']==expected
    assert canonical['approval']['intent']['lifetime_s']==3600
    assert canonical['approval']['by']=='author' and ledger.read_bytes()==raw
    replay=setup.renew(root,'p',wire,HUMAN)
    assert replay['replayed'] and replay['binding']==expected and ledger.read_bytes()==raw
    retain('detached-approval',{'expected':expected,'replay':replay,'lookup':looked,'ledger_unchanged':True})
