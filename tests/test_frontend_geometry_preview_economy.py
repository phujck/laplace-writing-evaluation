"""Public bounded preview/read-frame controls; execution is withheld."""
import copy
import hashlib
import json
import os
import types
from pathlib import Path

import pytest

from test_research_workflow_runs import run_root, start_run
from test_feedback_route import prepared,submit_payload,HUMAN


@pytest.fixture(autouse=True)
def passive_catalogue(monkeypatch):
    from laplace.writing import provider,provider_catalogue
    from test_writing_dispatch import CATALOGUE
    monkeypatch.setattr(provider_catalogue,'provider_catalogue',lambda *a,**k:copy.deepcopy(CATALOGUE))
    monkeypatch.setattr(provider,'provider_catalogue',lambda *a,**k:copy.deepcopy(CATALOGUE))


def preview_request(s,intervention):
    from laplace.writing import workflow_progression as P
    view=P.view(s['root'],'book',s['work'])
    return {'action':'workflow-impact-preview','work_id':s['work'],
        'expected_work_revision':view['work']['revision'],'expected_run_revision':view['revision'],
        'expected_plan_generation':view['plan_generation'],'intervention':intervention}


def files(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in Path(root).rglob('*') if p.is_file() and not p.name.endswith('.lock')}


def test_pure_replan_preview_exact_confirmation_and_acknowledged_current_projection(run_root):
    from laplace.work import work_delivery as WD
    from laplace.writing import workflow_progression as P,records
    s=run_root;root=s['root'];wire=preview_request(s,{'action':'workflow-replan','reference':s['saved']['reference']})
    before=files(root);turns=len(records.fold_records(root)['turns']);launched=len(s['launches'])
    preview=WD.handle(root,'book',wire,{'origin':'human'})
    assert preview['state']=='READY' and preview['domain_effects']==[]
    assert files(root)==before and len(records.fold_records(root)['turns'])==turns and len(s['launches'])==launched
    assert preview['before']['inputs']==preview['after']['inputs']
    assert 'content' not in preview['after']['packet'] and preview['after']['packet']['measurements']
    confirm=preview['confirmation']['http']['payload']
    assert confirm['expected_impact_basis']==preview['impact_basis']
    result=WD.handle(root,'book',confirm,{'origin':'human'})
    assert result['plan_generation']!=wire['expected_plan_generation'] and len(s['launches'])==launched
    receipt=result['request_receipt']
    assert receipt['effect']=='RECORDED' and receipt['request_id']==confirm['request_id']
    assert receipt['receipt']['action']=='workflow-replan'
    assert result['current_projection']['basis']==result['revision']
    assert result['current_projection']['location']=='response-root'
    assert receipt['receipt']['run']['plan_generation']==result['plan_generation']
    after=files(root);replayed=WD.handle(root,'book',confirm,{'origin':'human'})
    assert replayed['request_receipt']['receipt']['phase_id']==receipt['receipt']['phase_id'] and files(root)==after
    (root/'pure-replan-preview-proof.json').write_text(json.dumps({'request':wire,'preview':preview,
        'confirmed':result,'replayed_receipt':replayed['request_receipt'],'domain_files_unchanged_by_preview':True},indent=2))


def test_future_readdress_preserves_actual_attempt_and_binding_drift_refuses_before_effect(run_root):
    from laplace.work import work_delivery as WD,project_work as W
    from laplace.writing import workflow_progression as P
    s=run_root;root=s['root'];start_run(s);writer=s['launches'][-1]
    approval={'action':'workflow-bind','request_id':'geometry-alternate-writer','work_id':s['work'],
        'expected_work_revision':W._task_revision(W._tasks('book',root)[s['work']]),'kind':'app-owned',
        'effect':'proposal-writer','provider':'codex','model':'public-model','effort':'low','label':'Alternate public writer','lifetime_s':600}
    approved=WD.handle(root,'book',approval,{'origin':'human'});alternate=approved['binding']
    assert approved['request_receipt']['receipt']['intent_sha256']==alternate['approval']['intent_sha256']
    wire=preview_request(s,{'action':'workflow-readdress','recipient':'writer','recipient_binding_id':alternate['id']})
    before=files(root);preview=WD.handle(root,'book',wire,{'origin':'human'})
    assert preview['state']=='READY' and files(root)==before
    retained=preview['retained_effects']['items'][0]
    assert retained['turn_id']==writer.turn_id and retained['captured_binding']['id']==s['recipients']['writer']
    assert preview['future'][0]['binding']['id']==alternate['id']
    confirm=preview['confirmation']['http']['payload']
    renewed=WD.handle(root,'book',{**approval,'request_id':'geometry-renew-alternate',
        'expected_binding_revision':alternate['revision']},{'origin':'human'})
    assert renewed['binding']['id']==alternate['id'] and renewed['binding']['revision']!=alternate['revision']
    before=files(root)
    with pytest.raises(W.WorkConflict,match='previewed intervention basis changed'):
        WD.handle(root,'book',confirm,{'origin':'human'})
    assert files(root)==before and len(s['launches'])==2
    fresh=WD.handle(root,'book',wire,{'origin':'human'});result=WD.handle(root,'book',fresh['confirmation']['http']['payload'],{'origin':'human'})
    assert result['attempts'][0]['turn_id']==writer.turn_id
    assert result['attempts'][0]['binding']['id']==s['recipients']['writer'] and len(s['launches'])==2
    replay=WD.handle(root,'book',approval,{'origin':'human'})
    assert replay['observation']=='ORIGINAL_APPROVAL_RECEIPT' and replay['binding']['revision']==alternate['revision']
    (root/'future-readdress-proof.json').write_text(json.dumps({'approval':approved,'request':wire,'preview':preview,
        'renewed':renewed,'fresh_preview':fresh,'confirmed':result,'historical_approval':replay},indent=2))


def test_changed_and_unsupported_previews_refuse_without_domain_publication(run_root):
    from laplace.pipeline import workflow_definitions as D
    from laplace.work import owner_discovery as O,work_delivery as WD
    s=run_root;root=s['root'];wire=preview_request(s,{'action':'workflow-replan','reference':s['saved']['reference']})
    before=files(root)
    changed=WD.handle(root,'book',{**wire,'expected_work_revision':'sha256:'+'0'*64},{'origin':'human'})
    assert changed['state']=='CHANGED_INPUT' and 'confirmation' not in changed and files(root)==before
    body=copy.deepcopy(s['body']);body['title']='A saved but unsupported two-reviewer topology'
    body['steps'][0]['assignment']['role']='adversary'
    saved=D.save(root,O.project_scope('book','sdk'),{'request_id':'geometry-unsupported','expected_revision':None,'definition':body})
    before=files(root);refused=WD.handle(root,'book',{**wire,'intervention':{'action':'workflow-replan','reference':saved['reference']}},{'origin':'human'})
    assert refused['state']=='REFUSED' and 'confirmation' not in refused and files(root)==before
    (s['manuscript']/'main.tex').write_text((s['manuscript']/'main.tex').read_text().replace('Original prose.','Changed current source.'))
    before=files(root);stale=WD.handle(root,'book',wire,{'origin':'human'})
    assert stale['state']=='CHANGED_INPUT' and 'confirmation' not in stale and files(root)==before
    (root/'preview-refusals-proof.json').write_text(json.dumps({'changed':changed,'unsupported':refused,'source_changed':stale},indent=2))


def test_feedback_pure_read_frame_reuses_origin_fold_and_review_and_stays_detached(prepared,monkeypatch):
    from laplace.work import feedback_route as F,work_delivery as WD,project_work as W,project_work_review as R,object_geometry
    from laplace.pipeline import authoring
    from laplace.writing import turn_execution as X,records
    root,_payload,saved,policy=prepared;launches=[];monkeypatch.setattr(X,'start',launches.append)
    submitted=F.handle(root,'p',submit_payload(root,saved,policy,'geometry-public-two-edge'),HUMAN)
    assert len(launches)==2
    task=W._tasks('p',root)['review-claim'];event=next(r for r in reversed(task['deliveries']) if r.get('turn_id')==launches[0].turn_id)
    handoff=next(r for r in task['phases'] if r['id']==event['handoff_id'])
    R.record('p',{'id':task['id'],'phase':'review','request_id':'geometry-public-verdict',
        'expected_work_revision':W._task_revision(task),'handoff_id':handoff['id'],
        'obligation_id':event['obligation_id'],'verdict':'ACCEPT','pins':handoff['pins']},root,
        door={'origin':'native','turn_id':launches[0].turn_id})
    X._bank_reply(launches[0],{'status':'completed','text':'Retained public review response.'})
    X._finish(launches[0],{'status':'completed'})
    query={'action':'route-status','work_id':'review-claim','origin':saved['origin_ref']}
    def measure(base=False):
        counts={name:0 for name in ('origin','tasks','review','writing_fold')}
        with monkeypatch.context() as patch:
            patch.setattr(object_geometry,'request',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Context handles must not eagerly assemble geometry.')))
            baseline=os.environ.get('GEOMETRY_BASE_READ_FUNCTIONS')
            if base:
                stored=json.loads(Path(baseline).read_text())
                for module,name in [(F,'feedback_route'),(WD,'work_delivery'),(R,'project_work_review')]:
                    env=dict(module.__dict__);exec(compile(stored[name],str(Path(baseline)), 'exec'),env)
                    for fname in stored[name+'_names']:
                        original=env[fname];fn=types.FunctionType(original.__code__,module.__dict__,fname,original.__defaults__,original.__closure__)
                        fn.__kwdefaults__=original.__kwdefaults__;patch.setattr(module,fname,fn)
            for module,name,label in [(authoring,'correction_origin','origin'),(W,'_tasks','tasks'),
                                      (R,'facet','review'),(records,'fold_records','writing_fold')]:
                real=getattr(module,name)
                def counted(*a,_real=real,_label=label,**k):
                    counts[_label]+=1;return _real(*a,**k)
                patch.setattr(module,name,counted)
            value=F.status(root,'p',query)
        return value,counts
    before=files(root);baseline=None
    if os.environ.get('GEOMETRY_BASE_READ_FUNCTIONS'):baseline=measure(True)
    value,counts=measure()
    assert value['state']=='partial' and counts=={'origin':1,'tasks':1,'review':1,'writing_fold':1},counts
    assert files(root)==before
    prior_shape={k:v for k,v in value.items() if k!='review_context'}
    if baseline:assert baseline[0]==prior_shape and baseline[1]['origin']==4 and baseline[1]['review']==2
    context_read=value['review_context']
    assert context_read['association']=={'kind':'recorded-route','route_id':submitted['route_id'],'origin_ref':saved['origin_ref']}
    assert context_read['reference']['identity']=={'namespace':'p','id':'review-claim'}
    assert context_read['basis']==value['work']['revision'] and context_read['basis_kind']=='work-specification'
    for name,facet in [('neighbourhood_read','neighbourhood')]:
        request=context_read[name]['native']['payload']['request']
        assert request=={'facet':facet,'reference':context_read['reference'],'project_lens':'p'}
    context={};snapshot=F.status(root,'p',query,read_context=context);original=copy.deepcopy(snapshot)
    snapshot['policy']['limits']['max_new_admissions']=999
    snapshot['origin']['correction']['text']='Caller-local change.'
    snapshot['edges'][0]['event']['recipient']['label']='Caller-local label.'
    assert F.status(root,'p',query,read_context=context)==original
    (root/'p/manuscript/main.tex').write_text('Changed public source after the retained review.\n')
    fresh=F.status(root,'p',query)
    completed=next(e for e in fresh['edges'] if e['event']['result'].get('available'))
    assert completed['event']['acceptance']['currentness']=='STALE' and completed['event']['result']['available']
    (root/'request-local-economy-proof.json').write_text(json.dumps({'request':query,'value':value,'counts':counts,
        'baseline_counts':baseline[1] if baseline else None,'same_output_except_additive_review_context':baseline[0]==prior_shape if baseline else None,
        'fresh_after_source_change':fresh,'domain_files_unchanged_by_pure_reads':True,
        'measurement':'Owner accessor/facet invocation counts on one public read, not physical I/O, latency or general speedup.'},indent=2))
    for launch in launches:
        if not launch.job.get('done'):X._finish(launch,{'status':'interrupted'})


def test_delivery_geometry_uses_indexed_admission_and_no_recipient_body_fold(run_root,monkeypatch):
    from laplace.work import work_delivery as WD,project_work as W
    from laplace.writing import records
    s=run_root;root=s['root'];start_run(s);writer=s['launches'][-1]
    actual_index=records.index(root)
    def no_fold(*a,**k):raise AssertionError('Geometry must not fold/hydrate recipient replies.')
    monkeypatch.setattr(records,'fold_records',no_fold)
    before=files(root);value=WD.geometry_observation(root,'book',s['work'])
    assert files(root)==before and value['events'][0]['admitted']
    assert value['events'][0]['turn_id']==writer.turn_id
    rows=[dict(r) for r in actual_index.by_project['book']]
    for row in rows:
        if row.get('id')==writer.turn_id:row['session_id']='WS-not-the-durable-reservation'
    monkeypatch.setattr(records,'index',lambda *_:types.SimpleNamespace(by_project={'book':rows}))
    wrong=WD.geometry_observation(root,'book',s['work'])
    assert not wrong['events'][0]['admitted'] and wrong['events'][0]['admission_observation'].startswith('UNCONFIRMED')
    # Public metadata fixture: later pending intents push the actual old event
    # outside the normal page; selecting its parent-local coordinate stays exact.
    captured=copy.deepcopy(W._tasks('book',root)[s['work']]);event_id=value['events'][0]['id']
    captured['deliveries']=list(captured['deliveries'])
    intent=WD._history(captured,event_id)[0]
    for n in range(WD.PAGE+1):
        row=copy.deepcopy(intent);row.update(id='WD-public-pending-'+str(n),state='SUBMITTED')
        captured['deliveries'].append(row)
    monkeypatch.setattr(records,'index',lambda *_:actual_index)
    monkeypatch.setattr(WD,'_task_for',lambda *a,**k:({s['work']:captured},captured))
    page=WD.geometry_observation(root,'book',s['work'])
    assert event_id not in [r['id'] for r in page['events']] and page['coverage']['omitted']==2
    selected=WD.geometry_observation(root,'book',s['work'],event_id=event_id)
    assert len(selected['events'])==1 and selected['events'][0]['id']==event_id and selected['events'][0]['admitted']
    with pytest.raises(ValueError,match='Unknown delivery event'):
        WD.geometry_observation(root,'book',s['work'],event_id='WD-not-selected')
    (root/'delivery-geometry-metadata-proof.json').write_text(json.dumps({'actual':value,'wrong_session':wrong,
        'older_selected':selected,'normal_page':page,'later_pending_rows':'Explicit metadata-only projection fixture; no synthetic admissions.',
        'rich_reply_fold_calls':0,'domain_files_unchanged':True},indent=2))
