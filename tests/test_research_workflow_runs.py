"""Public controlled lifecycle/effect tests; no provider inference or network."""
import copy
import json
import sys
import types
import hashlib
import pytest

from laplace.pipeline import workflow_definitions as D
from laplace.work import owner_discovery as O


def test_effective_lineage_starter_and_normalization_are_owner_results(tmp_path, monkeypatch):
    from laplace.writing import provider_catalogue
    catalogue = {'providers': [{'id':'codex','available':True,'models':[
        {'id':'public-model','supports_effort':False,'efforts':[]}]}]}
    monkeypatch.setattr(provider_catalogue, 'provider_catalogue', lambda *_:copy.deepcopy(catalogue))
    starter = D.read(tmp_path, O.owned_workspace('sdk'), {'facet':'starters'})
    body = starter['starters'][0]
    D.validate(body)
    body['settings'] = {'provider':'codex','model':'public-model','effort':'high'}
    body['steps'][1]['parent_id'] = 'write'
    body['steps'][0]['assignment']['settings'] = {'effort':'low'}
    result, _ = D.resolve_settings(tmp_path, O.owned_workspace('sdk'), body, edit_revision='public-version')
    reviewer = result['review']
    assert reviewer['values']['effort'] is None
    assert reviewer['effort']['lineage'][-1]['value'] is None
    assert reviewer['effort']['lineage'][-1]['selected']
    assert reviewer['effort']['lineage'][0]['origin']=='definition'
    assert reviewer['effort']['lineage'][1]['origin']=='assignment:write'
    assert reviewer['instruction']['origin']=='assignment:review'
    assert reviewer['instruction']['composition'].startswith('local exact')
    assert reviewer['edit_guard']=='public-version' and reviewer['consumed_settings_digest']
    assert body['run_policy']['apply']=='human'
    (tmp_path/'settings-and-starter-sample.json').write_text(json.dumps({'starter_read':starter,
        'effective_settings':result,'qualification':'Actual owner result with explicit synthetic passive catalogue; no provider availability claim.'},indent=2))


@pytest.fixture
def run_root(tmp_path, monkeypatch):
    from test_writing_operating import _project
    from laplace.writing import provider, provider_catalogue, turn_execution as X, turn_admission as T, records
    from laplace.writing import workflow_progression as P
    from laplace.work import project_work as W, work_delivery as WD
    manuscript = _project(tmp_path)
    catalogue = {'providers':[{'id':'codex','available':True,'models':[
        {'id':'public-model','supports_effort':True,'efforts':['low']}]}]}
    monkeypatch.setattr(provider,'capabilities',lambda *a,**k:copy.deepcopy(catalogue))
    monkeypatch.setattr(provider_catalogue,'provider_catalogue',lambda *a,**k:copy.deepcopy(catalogue))
    monkeypatch.setattr(provider,'context_window_advertised',lambda *a,**k:None)
    launches=[];monkeypatch.setattr(X,'start',launches.append)
    parent=T.start_turn(tmp_path,{'project':'book','mode':'work','provider':'codex','model':'public-model','effort':'low',
        'text':'Prepare a public reviewed draft from the selected source.','request_id':'public-author-preparation','selection':{'files':['main.tex']}})
    body=D.starter_definition();body['settings']={'provider':'codex','model':'public-model','effort':'low'}
    saved=D.save(tmp_path,O.project_scope('book','sdk'),{'request_id':'public-save-research','expected_revision':None,'definition':body})
    basis='sha256:'+hashlib.sha256((manuscript/'main.tex').read_bytes()).hexdigest()
    from laplace.work import object_facets
    reference=object_facets.ref('domain.projects','source-file',project='book',path='main.tex',scope='manuscript')
    entry=object_facets.request(tmp_path,O.project_scope('book','sdk'),{'facet':'object','reference':reference,'section':'body','offset':0,'limit':4000})['input_descriptor']
    caller=D.native_caller(tmp_path,'book','work',parent['turn_id'])
    prepared=D.prepare(tmp_path,caller,{'profile':D.APP_PROFILE,'request_id':'public-prepare-research','reference':saved['reference'],
        'step_ids':['write','review'],'goal':'A reviewed proposal, awaiting human manuscript Apply.','fan_out_max':2,
        'inputs':[entry],'selection':{'files':['main.tex']}})
    work=prepared['work']['id'];recipients={}
    for name,effect in [('writer','proposal-writer'),('reviewer','independent-review')]:
        recipients[name]=WD.handle(tmp_path,'book',{'action':'workflow-bind','request_id':'public-approve-'+name,'work_id':work,'expected_work_revision':W._task_revision(W._tasks('book',tmp_path)[work]),
            'kind':'app-owned','effect':effect,'provider':'codex','model':'public-model','effort':'low'}, {'origin':'human'})['binding']['id']
    yield {'root':tmp_path,'manuscript':manuscript,'parent':parent,'saved':saved,'prepared':prepared,'work':work,
        'recipients':recipients,'launches':launches,'caller':caller,'body':body,'entry':entry}
    for launch in launches:
        if not launch.job.get('done'):X._finish(launch,{'status':'interrupted'})


def start_run(s):
    from laplace.writing import workflow_progression as P
    from laplace.work import work_delivery as WD
    view=P.view(s['root'],'book',s['work'])
    return WD.handle(s['root'],'book',{'action':'workflow-start','work_id':s['work'],'request_id':'public-run-start',
        'expected_run_revision':view['revision'],'recipients':s['recipients']},{'origin':'native','turn_id':s['parent']['turn_id']})


def finish(launch,result):
    from laplace.writing import turn_execution as X
    X._bank_reply(launch,result);X._finish(launch,result)


def test_actual_proposal_review_revision_and_human_apply_boundary(run_root):
    from laplace.writing import workflow_progression as P,records
    from laplace.native import tools
    from laplace.work import work_delivery as WD
    from laplace.manuscript import source_application
    s=run_root;started=start_run(s)
    assert len(s['launches'])==2,started
    writer=s['launches'][-1]
    assert writer.mode=='revise' and writer.workflow_execution['effect']=='proposal-writer'
    with pytest.raises(ValueError,match='not permitted'):
        tools.execute(s['root'],'book','revise','apply_revision',{'edits':[]},turn_id=writer.turn_id)
    original=(s['manuscript']/'main.tex').read_text()
    def proposal(after):return {'answer':'Public scoped proposal.','edits':[{'file':'main.tex','line_start':3,'line_end':3,
        'before':'Original prose.','after':after,'reason':'Clarify the selected passage.'}]}
    finish(writer,{'status':'completed','text':'Public writer result.','proposal':proposal('Draft one.')})
    review=s['launches'][-1]
    assert review.mode=='review' and review.session_id!=writer.session_id, writer.job.get('delivery_settlement_error')
    finish(review,{'status':'completed','text':json.dumps({'verdict':'REVISE','findings':[{'id':'cutoff','summary':'State the cutoff assumption explicitly.'}]})})
    writer2=s['launches'][-1];assert writer2.mode=='revise' and writer2.turn_id!=writer.turn_id
    finish(writer2,{'status':'completed','text':'Public revised writer result.','proposal':proposal('Revised prose with explicit cutoff assumption.')})
    review2=s['launches'][-1]
    finish(review2,{'status':'completed','text':json.dumps({'verdict':'ACCEPT','findings':[]})})
    view=P.view(s['root'],'book',s['work'])
    assert view['state']=='AWAITING_HUMAN_APPLY' and len(view['attempts'])==4,view
    assert (s['manuscript']/'main.tex').read_text()==original
    accepted=WD.handle(s['root'],'book',{'action':'workflow-accept-boundary','work_id':s['work'],
        'request_id':'public-human-boundary','expected_run_revision':view['revision']},{'origin':'human'})
    assert (s['manuscript']/'main.tex').read_text()==original
    applied=source_application.apply_proposal(s['root'],{'project':'book','turn_id':writer2.turn_id,
        'proposal_version':view['proposal']['proposal_version']})
    assert applied['complete'] and 'Revised prose with explicit cutoff' in (s['manuscript']/'main.tex').read_text()
    (s['root']/'actual-proposal-review-loop-proof.json').write_text(json.dumps({'prepared':s['prepared'],'started':started,
        'reviewed':view,'boundary':accepted,'applied':applied,'qualification':'Actual A selected source/capture plus B owner/admission/preflight/review/apply; provider execution withheld, deterministic replies, no inference claim.'},indent=2))


def test_exact_compose_preview_and_reconciliation_sample(run_root):
    from laplace.writing import workflow_progression as P,turn_context,records
    from laplace.work import work_delivery as WD
    s=run_root
    composed=D.read(s['root'],O.project_scope('book','http'),{'facet':'app-compose','reference':s['saved']['reference'],
        'request_id':'public-compose-inputs','step_ids':['write','review'],'goal':'Review the exact selected source.','fan_out_max':2,
        'inputs':[s['entry']],'selection':{'files':['main.tex']}})
    assert composed['prepare_payload']['inputs']==[s['entry']]
    assert composed['action']['read']['request']['inputs']==[s['entry']]
    preview=P.view(s['root'],'book',s['work'])
    action=copy.deepcopy(preview['actions']['start']['http']['payload']);action['recipients']=s['recipients']
    start=WD.handle(s['root'],'book',action,{'origin':'human'})
    assert start['action']['payload']['session_id']==s['parent']['session_id']
    leaf=start['action']['payload']['workspace_context']['workflow_action']
    assert leaf['reference']['kind']=='research-workflow-start'
    parsed=P.action_input(leaf);assert parsed==leaf
    lookup=WD.handle(s['root'],'book',{'action':'workflow-request','work_id':s['work'],'request_id':action['request_id']},{'origin':'human'})
    assert lookup['effect']=='NONE' and len(s['launches'])==1
    (s['root']/'run-actions-and-compose-sample.json').write_text(json.dumps({'prepare_compose':composed,'preview':preview,
        'start_compose':start,'request_lookup':lookup,'qualification':'Actual pure owner metadata and original admitted parent; no execution or implied Start.'},indent=2))


def test_actual_selected_start_context_and_child_effect_fence(run_root):
    from laplace.writing import workflow_progression as P,turn_admission as T
    from laplace.native import tools
    s=run_root
    finish(s['launches'][0],{'status':'completed','text':'Prepared only.'})
    action=P.compose_start(s['root'],'book',{'work_id':s['work'],'request_id':'public-start-carrier','recipients':s['recipients']})['action']
    admitted=T.start_turn(s['root'],{**action['payload'],'request_id':'public-new-parent-start'})
    launch=s['launches'][-1];snapshot=launch.workspace_context['workflow_action'];assert snapshot['native']['payload']['request_id']=='public-start-carrier'
    with pytest.raises(ValueError,match='only its exact'):
        tools.execute(s['root'],'book','work','store_artifact',{'path':'unrelated.txt','content':'no','before':None,'reason':'Public negative.'},turn_id=admitted['turn_id'])
    call=snapshot['native'];tools.execute(s['root'],'book','work',call['operation'],call['payload'],turn_id=admitted['turn_id'])
    writer=s['launches'][-1];assert writer.workflow_execution['effect']=='proposal-writer'
    with pytest.raises(ValueError,match='not permitted'):
        tools.execute(s['root'],'book','revise','experiment_run',{'producer_id':'anything','mode':'smoke','args':{}},turn_id=writer.turn_id)
    assert writer.workflow_execution['input_policy']=='evidence-packet'


def test_bound_roles_target_only_and_input_drift_refuse_before_child(run_root):
    from laplace.writing import workflow_progression as P
    from laplace.work import work_delivery as WD
    s=run_root
    wrong={**s['recipients'],'writer':s['recipients']['reviewer']}
    with pytest.raises(ValueError,match='proposal-writer'):
        P.compose_start(s['root'],'book',{'work_id':s['work'],'request_id':'public-wrong-role','recipients':wrong})
    body=copy.deepcopy(s['body']);body['steps'][1]['assignment']['settings']['input_policy']='target-document-only'
    saved=D.save(s['root'],O.project_scope('book','sdk'),{'request_id':'public-sealed-saved','definition_id':s['saved']['definition_id'],
        'expected_revision':s['saved']['reference']['version']['definition_revision'],'definition':body})
    with pytest.raises(ValueError,match='UNSUPPORTED_REVIEW_INPUT_POLICY'):
        D.prepare(s['root'],s['caller'],{'profile':D.APP_PROFILE,'request_id':'public-sealed-prepare','reference':saved['reference'],
            'step_ids':['write','review'],'goal':'Not secretly informed.','fan_out_max':2,'inputs':[s['entry']],'selection':{'files':['main.tex']}})
    (s['manuscript']/'main.tex').write_text((s['manuscript']/'main.tex').read_text()+'\nNew assumption.\n')
    with pytest.raises(ValueError,match='changed|CHANGED'):
        start_run(s)
    assert len(s['launches'])==1


def test_stop_replan_retains_effects_and_exact_request_receipts(run_root):
    from laplace.writing import workflow_progression as P
    from laplace.work import work_delivery as WD,object_facets
    s=run_root;start_run(s);writer=s['launches'][-1]
    before=P.view(s['root'],'book',s['work'])
    stop={'action':'workflow-stop-before-next','work_id':s['work'],'request_id':'public-stop-before-review','expected_run_revision':before['revision']}
    WD.handle(s['root'],'book',stop,{'origin':'human'})
    finish(writer,{'status':'completed','text':'Scoped proposal.','proposal':{'answer':'Clarify.','edits':[{'file':'main.tex','line_start':3,'line_end':3,
        'before':'Original prose.','after':'Proposed prose.','reason':'Clarity.'}]}})
    stopped=P.view(s['root'],'book',s['work']);assert stopped['state']=='STOP_BEFORE_NEXT' and len(s['launches'])==2
    req=WD.handle(s['root'],'book',{'action':'workflow-request','work_id':s['work'],'request_id':stop['request_id']},{'origin':'human'})
    assert req['effect']=='RECORDED' and req['receipt']['action']=='workflow-stop-before-next'
    body=copy.deepcopy(s['body']);body['steps'][0]['assignment']['instructions']+=' Preserve all retained prior effects.'
    saved=D.save(s['root'],O.project_scope('book','sdk'),{'request_id':'public-replan-save','definition_id':s['saved']['definition_id'],
        'expected_revision':s['saved']['reference']['version']['definition_revision'],'definition':body})
    result=WD.handle(s['root'],'book',{'action':'workflow-replan','work_id':s['work'],'request_id':'public-new-plan-retained',
        'expected_run_revision':stopped['revision'],'reference':saved['reference'],'inputs':[s['entry']]},{'origin':'human'})
    assert result['state']=='STOP_BEFORE_NEXT' and len(result['attempts'])==1 and result['proposal']==stopped['proposal']
    assert result['plan_history'][0]['reference']==s['saved']['reference'] and len(s['launches'])==2
    binding=WD.handle(s['root'],'book',{'action':'workflow-bind-request','work_id':s['work'],'request_id':'public-approve-writer'},{'origin':'human'})
    assert binding['effect']=='RECORDED' and binding['receipt']['binding']['id']==s['recipients']['writer']
    (s['root']/'recorded-request-replan-sample.json').write_text(json.dumps({'bind_request':binding,'mutation_request':req,'replanned':result},indent=2))


def test_session_creation_lost_ack_recovers_exact_event_once(run_root,monkeypatch):
    from laplace.writing import workflow_progression as P,turn_admission as T,records
    from laplace.work import work_delivery as WD
    s=run_root;real=T.new_session;created=[]
    def lose(*a,**k):
        value=real(*a,**k);created.append(value['id']);raise OSError('public lost WS acknowledgement')
    monkeypatch.setattr(T,'new_session',lose)
    with pytest.raises(OSError,match='lost WS'):start_run(s)
    assert len(created)==1 and len(s['launches'])==1
    monkeypatch.setattr(T,'new_session',real)
    result=WD.handle(s['root'],'book',{'action':'workflow-recover','work_id':s['work'],'request_id':'public-recover-original'},{'origin':'human'})
    assert len(s['launches'])==2 and s['launches'][-1].session_id==created[0]
    WD.handle(s['root'],'book',{'action':'workflow-recover','work_id':s['work'],'request_id':'public-recover-original'},{'origin':'human'})
    assert len(s['launches'])==2 and result['attempts'][0]['turn_id']==s['launches'][-1].turn_id


def research_delivery(s, *, ident='public-research-effect', sleep=False):
    from laplace.research import research_runs
    from laplace.work import project_work as W, project_work_review as R,work_delivery as WD
    root=s['root'];md=s['manuscript'];p=md/'public_producer.py'
    p.write_text("import argparse,json,time\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()\nprint('PUBLIC_PARTIAL_RESULT',flush=True)\n"+
        ("time.sleep(20)\n" if sleep else "Path(a.result).write_text(json.dumps({'value':7,'meaning':'public bounded result'}))\n"))
    spec={'id':'public-method','executable':p.name,'scope':'manuscript','modes':['smoke'],'allowed_args':{},'timeout_seconds':3}
    code,registered=research_runs.register_producer('book',spec,root);assert code==201,registered
    rel=p.relative_to(root).as_posix()
    W.task('book',{'id':ident,'title':'Check the declared public method','goal':'Observe the registered method result separately from scientific judgement.',
        'review_obligations':[{'id':'method','label':'Registered method result','scope':'other','inputs':[rel]}]},root)
    def guard():return W._task_revision(W._tasks('book',root)[ident])
    h=R.record('book',{'id':ident,'phase':'handoff','request_id':'public-method-handoff','expected_work_revision':guard(),
        'obligations':['method'],'pins':{rel:'sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()},'object':{'kind':'registered-method'}},root)
    binding=WD.handle(root,'book',{'action':'workflow-bind','request_id':'public-method-approval','work_id':ident,
        'expected_work_revision':guard(),'kind':'app-owned','effect':'research-producer','producer_id':'public-method',
        'producer_mode':'smoke','producer_args':{},'label':'Public registered method'}, {'origin':'human'})['binding']
    wire={'action':'submit','work_id':ident,'expected_work_revision':guard(),'handoff_id':h['phase']['id'],
        'obligation_id':'method','recipient_binding_id':binding['id'],'runtime_seconds':1}
    return wire,binding,p


def test_registered_research_effect_real_owner_supervision_and_exact_recovery(run_root):
    import os,time
    from laplace.work import work_delivery as WD,project_work as W
    from laplace.research import research_runs
    s=run_root;wire,binding,path=research_delivery(s)
    result=WD.handle(s['root'],'book',wire,{'origin':'human'})
    event=result['event'];ident=event['admitted']['research_run_id']
    end=time.monotonic()+8
    while time.monotonic()<end:
        code,run=research_runs.run_status_read('book',ident,s['root'])
        if (run.get('supervision') or {}).get('phase')=='TERMINAL':break
        time.sleep(.025)
    assert run['state']=='COMPLETE' and run['cleanup']['status']=='VERIFIED',run
    # Observe/reap this test's exact admitted launcher after its own verified terminal receipt.
    try:os.waitpid(run['pid'],0)
    except ChildProcessError:pass
    recovered=WD.handle(s['root'],'book',{'action':'recover','event_id':event['id']},{'origin':'human'})['event']
    assert recovered['result']['available'] and recovered['admitted']['research_run_id']==ident
    assert recovered['acceptance']['satisfied'] is False
    assert WD.handle(s['root'],'book',wire,{'origin':'human'})['event']['admitted']['research_run_id']==ident
    assert len([p for p in (s['manuscript']/'research_runs').glob('run-*.json') if p.name.count('.')==1])==1  # one job, separately retained receipt and result
    (s['root']/'registered-research-effect-proof.json').write_text(json.dumps({'submitted':result,'run':run,'recovered':recovered,
        'qualification':'Actual registered Python producer, Research admit/supervisor/cleanup and Work delivery. No model/provider/network.'},indent=2))


def test_registered_research_timeout_reaps_owned_process_and_keeps_partial(run_root):
    import time
    from laplace.work import work_delivery as WD
    from laplace.research import research_runs
    s=run_root;wire,binding,path=research_delivery(s,sleep=True)
    result=WD.handle(s['root'],'book',wire,{'origin':'human'});ident=result['event']['admitted']['research_run_id']
    end=time.monotonic()+8
    while time.monotonic()<end:
        code,run=research_runs.run_status_read('book',ident,s['root'])
        if (run.get('supervision') or {}).get('phase')=='TERMINAL':break
        time.sleep(.025)
    assert run['state']!='COMPLETE' and run['cleanup']['status']=='VERIFIED' and not run.get('cleanup_unresolved'),run
    assert 'PUBLIC_PARTIAL_RESULT' in (s['manuscript']/'research_runs'/(ident+'.stdout.log')).read_text()
    event=WD.handle(s['root'],'book',{'action':'recover','event_id':result['event']['id']},{'origin':'human'})['event']
    assert event['result']['available'] and not event['acceptance']['satisfied']
    assert research_runs.launch('book',{'producer_id':'public-method','mode':'smoke','args':{},'runtime_seconds':4,'request_id':'public-unsupported-cap'},s['root'])[0]==422
    (s['root']/'research-timeout-proof.json').write_text(json.dumps({'run':run,'event':event},indent=2))


def test_canonical_scientific_concern_template_and_human_disposition(run_root):
    from laplace.research import corpus_ingest as CI,object_context as R
    from laplace.work import object_facets as F,work_delivery as WD
    from laplace.writing import workflow_progression as P
    from laplace.core.identity import canonical_digest
    s=run_root;root=s['root'];project='book'
    made=CI.rewire_add(root,project,{'kind':'add-node','node':'result:public','node_kind':'result','essence':'The construction assumes a finite cutoff.','by':'public fixture'})
    assert made.get('ok'),made
    claim=R.reference('concept',project,'result:public');current=R.read(root,project,claim)
    R.change(root,project,{'reference':claim,'expected_basis':current['basis'],'request_id':'public-bind-consumed',
        'operation':'bind-consumed','consumed_bases':[{'reference':s['entry']['reference'],'basis':s['entry']['expected_basis']}]},
        admit=lambda *a:{'kind':'author','actor':'public fixture','authority':'explicit public setup'})
    entry=F.request(root,O.project_scope(project,'sdk'),{'facet':'object','reference':claim})['input_descriptor']
    prepared=D.prepare(root,s['caller'],{'profile':D.APP_PROFILE,'request_id':'public-prepare-concern','reference':s['saved']['reference'],
        'step_ids':['write','review'],'goal':'Assess a recorded scientific assumption.','fan_out_max':2,'inputs':[s['entry'],entry],
        'selection':{'files':['main.tex']}})
    work=prepared['work']['id'];view=P.view(root,project,work)
    mark={'action':'workflow-disposition','work_id':work,'request_id':'public-mark-concern','expected_run_revision':view['revision'],
        'subject':claim,'expected_basis':R.read(root,project,claim)['basis'],'concern_id':'cutoff-question',
        'changed':{'reference':s['entry']['reference'],'basis':s['entry']['expected_basis']},'change_kind':'assumption','summary':'Does the cutoff assumption remain justified?'}
    marked=WD.handle(root,project,mark,{'origin':'human'})
    action=next(v for k,v in marked['actions'].items() if k.startswith('disposition_'))
    assert set(f['name'] for f in action['fields'])=={'disposition','summary'}
    assert 'UNCHANGED' not in action['fields'][0]['choices']
    wire=action['http']['payload'];original_pointer=marked['interventions'][-1]['receipt']['concern']['reference']
    with pytest.raises(ValueError,match='scientific assumption'):
        WD.handle(root,project,{**wire,'request_id':'public-invalid-unchanged','disposition':'UNCHANGED','summary':'Same bytes.'},{'origin':'human'})
    with pytest.raises(ValueError,match='bound judgement'):
        WD.handle(root,project,{**wire,'request_id':'public-producer-no-clear','disposition':'REVISE','summary':'Producer cannot clear an assumption.'},
            {'origin':'native','turn_id':s['parent']['turn_id']})
    cleared=WD.handle(root,project,{**wire,'disposition':'REVISE','summary':'Revise the scientific claim to state the finite cutoff.'},{'origin':'human'})
    receipt=cleared['interventions'][-1]['receipt'];assert receipt['concern']['reference']==original_pointer
    canonical=R.read(root,project,original_pointer)
    assert canonical['value']['state']=='DISPOSED' and canonical['value']['disposition']=='REVISE'
    assert receipt['concern']['basis']==canonical['basis']
    assert not any('cleared' in key for key in cleared)
    (root/'canonical-concern-run-proof.json').write_text(json.dumps({'marked':marked,'cleared':cleared,'canonical':canonical},indent=2))


def test_stopped_parent_prevents_next_admission_but_keeps_completed_proposal(run_root):
    from laplace.writing import workflow_progression as P
    s=run_root;start_run(s);writer=s['launches'][-1]
    finish(s['launches'][0],{'status':'interrupted','text':'Author stopped the original parent.'})
    finish(writer,{'status':'completed','text':'Retained proposal.','proposal':{'answer':'Preserved.','edits':[{'file':'main.tex','line_start':3,'line_end':3,
        'before':'Original prose.','after':'Preserved proposed prose.','reason':'Clarity.'}]}})
    view=P.view(s['root'],'book',s['work'])
    assert view['proposal'] and len(s['launches'])==2
    assert 'parent was stopped' in writer.job.get('delivery_settlement_error',''),writer.job
    with pytest.raises(ValueError,match='parent was stopped'):P.advance(s['root'],'book',s['work'])
    assert len(s['launches'])==2


def test_actual_feedback_writer_effect_and_legacy_recipient_array(run_root):
    from laplace.pipeline import authoring
    from laplace.work import project_work as W,work_delivery as WD,feedback_route as F
    from laplace.core import identity_doors
    s=run_root;root=s['root'];ident='public-comment-proposal'
    W.task('book',{'id':ident,'title':'Clarify this authored passage','goal':'Return a proposal for the author comment.',
        'anchor':{'file':'main.tex'},'review_obligations':[{'id':'clarity','label':'Clarify this passage','scope':'other',
        'inputs':[(s['manuscript']/'main.tex').relative_to(root).as_posix()]}]},root)
    guard=lambda:W._task_revision(W._tasks('book',root)[ident])
    binding=WD.handle(root,'book',{'action':'workflow-bind','work_id':ident,'expected_work_revision':guard(),
        'request_id':'public-comment-writer-approval','kind':'app-owned','effect':'proposal-writer','provider':'codex','model':'public-model','effort':'low'},{'origin':'human'})['binding']
    expected=list(identity_doors.identities(('prose','book::main.tex:3-3',b'Original prose.')).values())
    prepared=authoring.prepare_correction('book',{'anchor':{'file':'main.tex','line_start':3,'line_end':3,'quote':'Original prose.'},'expected':expected},root)
    saved=authoring.bank_correction('book',{'project':'book','request_id':'public-author-comment','text':'State the finite cutoff explicitly.',
        'kind':'note','scope':'passage','by':'author',**{k:prepared[k] for k in ('anchor','source_basis','base_revision')}},root)
    policy={'mode':'manual','recipients':[{'obligation_id':'clarity','recipient_binding_id':binding['id']}],
        'limits':{'max_new_admissions':1,'max_attempts':2,'admission_seconds':60,'runtime_seconds':5}}
    # Existing top-level selected-recipient array remains valid, distinct from new run writer/reviewer map.
    wire={'action':'route-submit','work_id':ident,'expected_work_revision':guard(),'request_id':'public-route-writer',
        'origin':saved['origin_ref'],'policy':policy,'recipients':policy['recipients']}
    result=WD.handle(root,'book',wire,{'origin':'human'});aggregate=F.aggregate(root,'book',ident,result['route_id'])
    assert len(s['launches'])==2,aggregate
    launch=s['launches'][-1];assert launch.mode=='revise' and launch.workflow_execution['effect']=='proposal-writer'
    assert 'Author-requested manuscript proposal' in launch.prompt
    assert 'Record your verdict with work_review' not in launch.prompt
    finish(launch,{'status':'completed','text':'Unapplied author proposal.','proposal':{'answer':'State the cutoff.','edits':[{
        'file':'main.tex','line_start':3,'line_end':3,'before':'Original prose.','after':'Prose with explicit finite cutoff.','reason':'Author requested qualification.'}]}})
    complete=F.aggregate(root,'book',ident,result['route_id']);event=complete['edges'][0]['event']
    assert event['effect']=='proposal-writer' and event['proposal_read'] and event['acceptance']['satisfied'] is False
    assert 'Original prose.' in (s['manuscript']/'main.tex').read_text()
    assert WD.handle(root,'book',wire,{'origin':'human'})['replayed'] and len(s['launches'])==2
    (root/'feedback-writer-effect-proof.json').write_text(json.dumps({'saved':saved,'route':complete},indent=2))


def test_actual_http_native_exact_start_read_and_submission_replay(run_root):
    from urllib.parse import urlsplit,parse_qs
    from laplace.web import project_work_surface as H
    from laplace.native import tools
    from laplace.writing import workflow_progression as P,turn_admission as T
    s=run_root;root=s['root']
    read=P.read_handle('book',s['work']);url=urlsplit(read['http']['url'])
    code,_,raw=H.handle(url.path,parse_qs(url.query),'GET',repo_root=root);assert code==200,json.loads(raw)
    preview=json.loads(raw);assert preview['actions']['bind_writer']['permitted']
    assert not tools.execute(root,'book','review','work_delivery',{'action':'workflow-preview','work_id':s['work']})['actions']['bind_writer']['permitted']
    offered=P.compose_start(root,'book',{'work_id':s['work'],'request_id':'public-exact-start-inspect','recipients':s['recipients']})
    exact=offered['action']['read'];url=urlsplit(exact['http']['url'])
    code,_,raw=H.handle(url.path,parse_qs(url.query),'GET',repo_root=root);assert code==200,json.loads(raw)
    http=json.loads(raw);assert http['action']['action_context']==offered['action']['action_context']
    native=tools.execute(root,'book','review',exact['native']['operation'],exact['native']['payload'])
    assert native['action']['payload']==http['action']['payload']
    finish(s['launches'][0],{'status':'completed','text':'Prepared.'})
    wire={**offered['action']['payload'],'request_id':'public-exact-parent-submission'}
    admitted=T.start_turn(root,wire);assert admitted['action_submission']['request_id']==wire['request_id']
    call=offered['native_start'];native_result=tools.execute(root,'book','work',call['operation'],call['payload'],turn_id=admitted['turn_id'])
    replay=T.start_turn(root,wire);assert replay['turn_id']==admitted['turn_id'] and replay['reused']
    with pytest.raises(ValueError,match='different|changed|intent'):
        T.start_turn(root,{**wire,'text':wire['text']+' Changed intent.'})
    assert len(s['launches'])==3
    (root/'actual-http-native-start-proof.json').write_text(json.dumps({'preview':preview,'offered':offered,'http':http,
        'native_start_result':native_result,'admitted':admitted,'replay':replay},indent=2))


def test_object_context_validates_exact_pointer_without_body_injection(run_root):
    from laplace.projects import artifacts
    from laplace.work import object_facets as F
    from laplace.writing import turn_admission as T,records
    s=run_root;root=s['root'];saved=artifacts.store(root,'book',{'scope':'project','path':'public-object.txt','before':None,
        'content':'ONLY_SELECTED_OBJECT_BODY_CANARY','reason':'Public pointer-only control.'})
    ref=F.ref('domain.projects','artifact',project='book',id=saved['id'])
    value=F.request(root,O.project_scope('book','http'),{'facet':'object','reference':ref})
    leaf=value['conversation']['object_context'];finish(s['launches'][0],{'status':'completed','text':'Prepared.'})
    result=T.start_turn(root,{'project':'book','session_id':s['parent']['session_id'],'mode':'work','text':'Discuss this exact object.',
        'request_id':'public-object-context-parent','workspace_context':{'surface':'research','object_context':leaf}})
    launch=s['launches'][-1];assert launch.workspace_context['object_context']==leaf
    assert 'ONLY_SELECTED_OBJECT_BODY_CANARY' not in launch.prompt
    changed=copy.deepcopy(leaf);changed['expected_basis']='sha256:'+'0'*64
    finish(launch,{'status':'completed','text':'Pointer inspected.'})
    before=len(records.fold_records(root)['turns'])
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        T.start_turn(root,{'project':'book','session_id':result['session_id'],'mode':'work','text':'Old pointer.',
            'request_id':'public-object-stale-parent','workspace_context':{'surface':'research','object_context':changed}})
    assert len(records.fold_records(root)['turns'])==before


def test_actual_workflow_runtime_stops_only_owned_public_child(run_root):
    import subprocess,threading,time
    from laplace.work import project_work as W,work_delivery as WD
    from laplace.writing import workflow_progression as P,child_hosts,turn_execution as X
    s=dict(run_root);root=s['root'];body=copy.deepcopy(s['body']);body['run_policy']['runtime_seconds']=2
    saved=D.save(root,O.project_scope('book','sdk'),{'request_id':'public-runtime-definition','expected_revision':None,'definition':body})
    prepared=D.prepare(root,s['caller'],{'profile':D.APP_PROFILE,'request_id':'public-runtime-preparation','reference':saved['reference'],
        'step_ids':['write','review'],'goal':'Bound the actual owned fixture process.','fan_out_max':2,'inputs':[s['entry']],'selection':{'files':['main.tex']}})
    s.update(work=prepared['work']['id'],saved=saved);s['recipients']={}
    for name,effect in [('writer','proposal-writer'),('reviewer','independent-review')]:
        s['recipients'][name]=WD.handle(root,'book',{'action':'workflow-bind','request_id':'runtime-approve-'+name,'work_id':s['work'],
            'expected_work_revision':W._task_revision(W._tasks('book',root)[s['work']]),'kind':'app-owned','effect':effect,
            'provider':'codex','model':'public-model','effort':'low'},{'origin':'human'})['binding']['id']
    start_run(s);launch=s['launches'][-1]
    script=root/'public_producer.py';script.write_text('import time\ntime.sleep(20)\n')
    process=subprocess.Popen([sys.executable,str(script)],start_new_session=True)
    done=threading.Event();reasons=[];monitor=None
    try:
        child_hosts._register_child_process(root,launch.session_id,launch.turn_id,process,'public-runtime-control')
        monitor=threading.Thread(target=X._govern,args=(launch,None,done,reasons,{}),daemon=True);monitor.start()
        process.wait(timeout=5)
        assert process.returncode is not None and reasons==['workflow-recipient-runtime-exceeded'],reasons
    finally:
        done.set()
        if monitor:monitor.join(timeout=2)
        if process.poll() is None:
            child_hosts.terminate_child_processes(child_hosts._child_execution_record(root,launch.session_id));process.wait(timeout=3)
    finish(launch,{'status':'interrupted','text':'PUBLIC_PARTIAL_WORKFLOW_RESULT','error':reasons[0]})
    assert P.view(root,'book',s['work'])['state']=='PARTIAL'
    assert len(s['launches'])==2 and not s['launches'][0].job.get('interrupt_requested')
    (root/'actual-workflow-runtime-proof.json').write_text(json.dumps({'turn_id':launch.turn_id,'session_id':launch.session_id,
        'deadline':launch.workflow_execution['runtime_deadline_at'],'pid':process.pid,'returncode':process.returncode,
        'reasons':reasons,'retained_reply':launch.job.get('text'),'qualification':'Actual existing governor and registered harmless Python process, no provider/model.'},indent=2))


def test_exact_research_request_uncertainty_never_reactivates(run_root,monkeypatch):
    from laplace.research import research_runs
    s=run_root;wire,binding,path=research_delivery(s)
    calls=[]
    def lose(admission):calls.append(admission.job['id']);raise OSError('Public activation acknowledgement is unknown.')
    monkeypatch.setattr(research_runs,'activate',lose)
    payload={'producer_id':'public-method','mode':'smoke','args':{},'request_id':'public-activation-unknown','runtime_seconds':1}
    with pytest.raises(OSError,match='acknowledgement'):research_runs.launch('book',payload,s['root'])
    observed=research_runs.inspect_request('book',payload,s['root']);assert observed['effect']=='RECORDED'
    code,reply=research_runs.launch('book',payload,s['root']);assert code==200 and reply['reused'] and len(calls)==1
    assert research_runs.inspect_request('book',{**payload,'runtime_seconds':2},s['root'])['effect']=='CONFLICT'
    assert len(calls)==1


def test_recipient_session_settings_drift_refuses_before_new_turn(run_root,monkeypatch):
    from laplace.writing import turn_admission as T,workflow_progression as P,records
    from laplace.work import work_delivery as WD
    s=run_root;real=T.new_session
    def changed(*a,**k):
        session=real(*a,**k)
        records.bank(s['root'],{'record':'writing-session-settings','session_id':session['id'],'model':'another-public-model',
            'provider':'codex','effort':'low','project':'book'})
        return session
    monkeypatch.setattr(T,'new_session',changed)
    with pytest.raises(ValueError,match='approved settings'):start_run(s)
    assert len(s['launches'])==1
    view=P.view(s['root'],'book',s['work']);assert view['attempts'][0]['turn_id'] is None


def test_same_definition_replan_has_distinct_admission_generation(run_root):
    from laplace.writing import workflow_progression as P
    from laplace.work import work_delivery as WD
    s=run_root;start_run(s);writer=s['launches'][-1]
    view=P.view(s['root'],'book',s['work']);old_generation=view['plan_generation'];old_event=view['attempts'][0]['event_id']
    WD.handle(s['root'],'book',{'action':'workflow-stop-before-next','work_id':s['work'],'request_id':'public-same-version-stop',
        'expected_run_revision':view['revision']},{'origin':'human'})
    finish(writer,{'status':'completed','text':'Proposal retained.','proposal':{'answer':'Clarity.','edits':[{'file':'main.tex','line_start':3,'line_end':3,
        'before':'Original prose.','after':'Scoped proposed prose.','reason':'Clarity.'}]}})
    view=P.view(s['root'],'book',s['work'])
    planned=WD.handle(s['root'],'book',{'action':'workflow-replan','work_id':s['work'],'request_id':'public-same-definition-replan',
        'expected_run_revision':view['revision'],'reference':s['saved']['reference'],'inputs':[s['entry']]},{'origin':'human'})
    assert planned['reference']==view['reference'] and planned['plan_generation']!=old_generation
    resumed=WD.handle(s['root'],'book',{'action':'workflow-resume','work_id':s['work'],'request_id':'public-resume-new-generation',
        'expected_run_revision':planned['revision']},{'origin':'human'})
    assert len(s['launches'])==3 and s['launches'][-1].turn_id!=writer.turn_id
    assert resumed['attempts'][-1]['event_id']!=old_event and len(resumed['attempts'])==2
    assert resumed['proposal']==view['proposal']
    second=s['launches'][-1]
    finish(second,{'status':'completed','text':'Replanned proposal.','proposal':{'answer':'Retain lineage.','edits':[{'file':'main.tex','line_start':3,'line_end':3,'before':'Original prose.','after':'A new plan proposal.','reason':'Explicit replan.'}]}})
    current=P.view(s['root'],'book',s['work'])
    assert current['proposal']['id']!=view['proposal']['id'] and len(s['launches'])==4,second.job.get('delivery_settlement_error')
    (s['root']/'same-definition-new-generation-proof.json').write_text(json.dumps({'old':view,'replanned':planned,'resumed':resumed},indent=2))


def test_work_facets_and_impact_use_only_actual_admitted_input_relations(run_root):
    from laplace.writing import workflow_progression as P
    from laplace.work import work_delivery as WD,owner_discovery as O
    from laplace.core import identity
    s=run_root;root=s['root']
    assert P.consumed_relations(root,'book')['items']==[]
    offered=P.work_facet(root,'book',s['work'],door={'origin':'human'})
    assert offered['state']=='PREPARED' and offered['actions']['bind_writer']['permitted']
    with pytest.raises(ValueError,match='unconsumed fields'):
        WD.handle(root,'book',{'action':'workflow-start','work_id':s['work'],'request_id':'public-unsupported-start-limit',
            'expected_run_revision':offered['revision'],'recipients':s['recipients'],'runtime_seconds':1},
            {'origin':'native','turn_id':s['parent']['turn_id']})
    assert len(s['launches'])==1
    start_run(s);view=P.view(root,'book',s['work']);relations=P.consumed_relations(root,'book')
    assert len(relations['items'])==1 and relations['coverage']['work_omitted']==0
    relation=relations['items'][0]
    assert relation['dependent']==O.work_reference('book',s['work']) and relation['reference']==s['entry']['reference']
    assert relation['basis']==s['entry']['expected_basis'] and relation['turn_id']==s['launches'][-1].turn_id
    assert relation['qualification']=='PINNED' and relation['relation']=='admitted-evidence-packet'
    assert P.work_facet(root,'book','not-a-work') is None
    (root/'run-consumed-relations-proof.json').write_text(json.dumps({'view':view,'relations':relations},indent=2))


# Independent reviewer regressions; private context is not an author-message payload.
from laplace.writing import workflow_progression as P, records
from laplace.work import work_delivery as WD, project_work as W, object_facets as F

def proposal():
 return {'answer':'Independent public proposal','edits':[{'file':'main.tex','line_start':3,'line_end':3,'before':'Original prose.','after':'Scoped public revision.','reason':'Clarify the selected passage.'}]}


def test_nonobject_review_reply_settles_as_invalid_without_stuck_admission(run_root):
 s=run_root;start_run(s);writer=s['launches'][-1]
 finish(writer,{'status':'completed','text':'Public writer result','proposal':proposal()})
 review=s['launches'][-1];assert review.mode=='review'
 error=None
 try:finish(review,{'status':'completed','text':'[]'})
 except Exception as exc:error=repr(exc)
 value=P.view(s['root'],'book',s['work']);events=[(x['id'],x.get('state')) for x in value['attempts']]
 proof={'run':value,'review_turn':review.turn_id,'review_job_done':review.job.get('done'),'terminal_hook_error':error,'job_errors':{k:v for k,v in review.job.items() if 'error' in k},'events':events}
 (s['root']/'nonobject-review-proof.json').write_text(json.dumps(proof,indent=2,default=str))
 assert value['state']=='PARTIAL' and value.get('next') is None and value['attempts'][-1]['state']=='RESULT',proof


def test_large_selected_packet_is_not_editor_message_cap_and_no_orphan_session(run_root):
 s=run_root;root=s['root'];entries=[]
 for n in range(3):
  path=s['manuscript']/('selected-'+str(n)+'.txt');path.write_text(chr(65+n)*35000)
  ref=F.ref('domain.projects','source-file',project='book',path=path.name,scope='manuscript')
  value=F.request(root,O.project_scope('book','sdk'),{'facet':'object','reference':ref,'section':'body','offset':0,'limit':40000})
  entries.append(value['input_descriptor'])
 made=D.prepare(root,s['caller'],{'profile':D.APP_PROFILE,'request_id':'independent-large-packet','reference':s['saved']['reference'],'step_ids':['write','review'],'goal':'Read the complete selected public evidence.','fan_out_max':2,'inputs':entries,'selection':{'files':['main.tex']}})
 work=made['work']['id'];recipients={}
 for label,effect in [('writer','proposal-writer'),('reviewer','independent-review')]:
  recipients[label]=WD.handle(root,'book',{'action':'workflow-bind','request_id':'independent-large-'+label,'work_id':work,'expected_work_revision':W._task_revision(W._tasks('book',root)[work]),'kind':'app-owned','effect':effect,'provider':'codex','model':'public-model','effort':'low'},{'origin':'human'})['binding']['id']
 before=len(records.fold_records(root)['sessions']);error=None
 try:WD.handle(root,'book',{'action':'workflow-start','work_id':work,'request_id':'independent-start-large','expected_run_revision':P.view(root,'book',work)['revision'],'recipients':recipients},{'origin':'native','turn_id':s['parent']['turn_id']})
 except Exception as exc:error=repr(exc)
 value=P.view(root,'book',work);after=len(records.fold_records(root)['sessions'])
 proof={'before_sessions':before,'after_sessions':after,'error':error,'run':value,'selected_characters':105000}
 (root/'large-packet-admission-proof.json').write_text(json.dumps(proof,indent=2,default=str))
 assert error is None,proof
 assert after==before+1 and len(s['launches'])==2
 delivered=s['launches'][-1].prompt
 assert all(delivered.count(chr(65+n)*35000)==1 for n in range(3))
 assert len(s['launches'][-1].job.get('request_text',''))<1000
 actual=records.fold_records(root)['turns'][s['launches'][-1].turn_id]
 assert len(actual['text'])<1000 and actual['workflow_input']['characters']>105000


def test_known_precreation_refusal_keeps_no_new_session_and_partial_phase(run_root,monkeypatch):
 from laplace.writing import turn_admission as T
 with pytest.raises(ValueError,match='membership'):T.prepare_request({'project':'book','text':'No caller input override.','workflow_input':{'text':'forged'}})
 s=run_root;before=len(records.fold_records(s['root'])['sessions']);real=P.private_input
 monkeypatch.setattr(P,'private_input',lambda *a,**k:(_ for _ in ()).throw(ValueError('Public selected packet cannot be resolved.')))
 with pytest.raises(ValueError,match='cannot be resolved'):start_run(s)
 view=P.view(s['root'],'book',s['work']);attempt=view['attempts'][-1]
 assert len(records.fold_records(s['root'])['sessions'])==before and len(s['launches'])==1
 assert view['state']=='PARTIAL' and attempt['state']=='STALE' and attempt['known_refusal']
 assert attempt['refusal_stage']=='BEFORE_NEW_SESSION_OR_TURN' and not view['actions']['resume']['permitted']
 monkeypatch.setattr(P,'private_input',real)
 (s['root']/'known-precreation-proof.json').write_text(json.dumps(view,indent=2))


def test_observed_manuscript_choice_and_prepared_basis_survive_only_exact_source(run_root):
 from laplace.manuscript import manuscript_source as M
 from laplace.projects import artifacts
 from laplace.work import object_facets as F
 from laplace.writing import workflow_progression as P,records
 s=run_root;root=s['root'];observed=M.observation('book',root)
 file=next(iter(observed['file_revisions']));selection={'files':[file],'source_observation':{
  'selection_identity':observed['selection_identity'],'file_revisions':{file:observed['file_revisions'][file]}}}
 artifact=artifacts.store(root,'book',{'scope':'project','path':'independent-evidence.txt','before':None,'content':'PUBLIC_STABLE_EVIDENCE','reason':'Independent selected input.'})
 ref=F.ref('domain.projects','artifact',project='book',id=artifact['id']);entry=F.request(root,O.project_scope('book','sdk'),{'facet':'object','reference':ref})['input_descriptor']
 bad=copy.deepcopy(selection);bad['source_observation']['file_revisions'][file]='0'*64
 payload={'profile':D.APP_PROFILE,'request_id':'public-observed-prepare','reference':s['saved']['reference'],'step_ids':['write','review'],
  'goal':'Use exact observed manuscript and stable separate evidence.','fan_out_max':2,'inputs':[entry],'selection':selection}
 with pytest.raises(ValueError,match='MANUSCRIPT_SELECTION_CHANGED'):D.prepare(root,s['caller'],{**payload,'request_id':'public-bad-observation','selection':bad})
 prepared=D.prepare(root,s['caller'],payload);work=prepared['work']['id'];view=P.view(root,'book',work)
 assert view['manuscript_basis']==selection['source_observation']
 (s['manuscript']/'unrelated.txt').write_text('Unrelated source is not this consumed selection.')
 _,_,pin,_,_=P._load(root,'book',work);P._packet(root,'book',pin,revalidate=True)
 before=len(records.fold_records(root)['sessions'])
 (root/file).write_text((root/file).read_text().replace('Original prose.','Changed manuscript prose.'))
 with pytest.raises(ValueError,match='MANUSCRIPT_SELECTION_CHANGED'):P._packet(root,'book',pin,revalidate=True)
 assert len(records.fold_records(root)['sessions'])==before
 (root/'observed-manuscript-basis-proof.json').write_text(json.dumps({'selection':selection,'prepared':prepared,'view':view,'sessions_unchanged':True},indent=2))


def test_fast_reviewer_reply_settles_after_delivery_lock_before_next_admission(run_root,monkeypatch):
 from laplace.writing import workflow_progression as P,turn_execution as X,records
 from laplace.work import work_delivery as WD,project_work as W
 s=run_root;root=s['root'];start_run(s);writer=s['launches'][-1]
 real_lock=WD._event_lock
 def short_lock(*args):
  lock=real_lock(*args);lock.timeout=.2;return lock
 monkeypatch.setattr(WD,'_event_lock',short_lock)
 checked=[]
 def immediate(launch):
  s['launches'].append(launch)
  if launch.mode=='review':
   finish(launch,{'status':'completed','text':json.dumps({'verdict':'REVISE','findings':[]})})
  else:
   task=W._tasks('book',root)[s['work']]
   for attempt in P.view(root,'book',s['work'])['attempts'][:-1]:
    with short_lock(root,attempt['event_id']):checked.append(attempt['event_id'])
 monkeypatch.setattr(X,'start',immediate)
 finish(writer,{'status':'completed','text':'Public fast-result proposal.','proposal':{'answer':'Clarify.',
  'edits':[{'file':'main.tex','line_start':3,'line_end':3,'before':'Original prose.','after':'Draft one.','reason':'Clarify.'}]}})
 view=P.view(root,'book',s['work']);review=s['launches'][-2]
 assert len(view['attempts'])==3 and view['iteration']==2 and s['launches'][-1].mode=='revise',view
 assert 'delivery_settlement_error' not in review.job and checked
 task=W._tasks('book',root)[s['work']];event=review.workflow_execution['event_id']
 assert WD._history(task,event)[-1]['state']=='RESULT'
 assert sum(row.get('request_id')=='settled-'+event for row in P._phase_rows(task))==1
 assert records.fold_records(root)['turns'][review.turn_id]['reply']['text']==json.dumps({'verdict':'REVISE','findings':[]})
 (root/'fast-reply-lock-proof.json').write_text(json.dumps({'run':view,'review_turn':review.turn_id,'released_prior_events':checked},indent=2))


def test_retained_reviewer_reply_recovery_and_concurrent_callback_settle_once(run_root,monkeypatch):
 import threading
 from laplace.writing import workflow_progression as P,turn_execution as X,records
 from laplace.work import work_delivery as WD,project_work as W
 s=run_root;root=s['root'];start_run(s);writer=s['launches'][-1]
 finish(writer,{'status':'completed','text':'Public proposal.','proposal':{'answer':'Clarify.',
  'edits':[{'file':'main.tex','line_start':3,'line_end':3,'before':'Original prose.','after':'Draft one.','reason':'Clarify.'}]}})
 review=s['launches'][-1];event=review.workflow_execution['event_id'];real_settle=P.settle_event
 monkeypatch.setattr(P,'settle_event',lambda *a,**k:(_ for _ in ()).throw(ValueError('Retained interrupted settlement.')))
 finish(review,{'status':'completed','text':json.dumps({'verdict':'REVISE','findings':[]})})
 before=records.fold_records(root);turn_count=len(before['turns']);reply=copy.deepcopy(before['turns'][review.turn_id]['reply'])
 task=W._tasks('book',root)[s['work']];intent=WD._history(task,event)[0]
 W._append(root,{**WD._history(task,event)[-1],'state':'SUBMITTED','last_error':'Retained fast-reply lock failure.'})
 real_lock=WD._event_lock
 def short_lock(*args):
  lock=real_lock(*args);lock.timeout=.2;return lock
 monkeypatch.setattr(WD,'_event_lock',short_lock)
 entered=threading.Event();barrier=threading.Barrier(2);errors=[]
 def settle(*args):
  with short_lock(root,event):pass
  entered.set();barrier.wait(timeout=3)
  return real_settle(*args)
 monkeypatch.setattr(P,'settle_event',settle)
 def call(fn):
  try:fn()
  except BaseException as error:errors.append(repr(error))
 recovery=threading.Thread(target=call,args=(lambda:WD._deliver(root,'book',event),))
 recovery.start();assert entered.wait(3)
 callback=threading.Thread(target=call,args=(lambda:WD.settle_turn(root,'book',review.session_id,review.turn_id,reply),))
 callback.start();recovery.join(5);callback.join(5)
 assert not recovery.is_alive() and not callback.is_alive() and not errors,errors
 view=P.view(root,'book',s['work']);after=records.fold_records(root)
 assert after['turns'][review.turn_id]['reply']==reply
 assert len(after['turns'])==turn_count+1 and len(view['attempts'])==3
 task=W._tasks('book',root)[s['work']];history=WD._history(task,event)
 assert history[-1]['state']=='RESULT' and history[-1]['turn_id']==review.turn_id
 assert sum(row.get('request_id')=='settled-'+event for row in P._phase_rows(task))==1
 assert len([turn for turn in after['turns'].values() if turn.get('request_id')==event])==1
 (root/'retained-reply-concurrent-recovery-proof.json').write_text(json.dumps({'original_turn':review.turn_id,
  'original_reply':reply,'event_history':history,'run':view,'additional_turns':1,'errors':errors},indent=2))


def test_registered_launch_action_and_pure_original_request_receipt(run_root,monkeypatch):
 from laplace.research import research_runs as R,research_catalogue as C
 from urllib.parse import urlsplit,parse_qs
 s=run_root;root=s['root'];p=s['manuscript']/'public_request_method.py'
 p.write_text('print("Not executed by this request-custody control.")\n')
 spec={'id':'public-request-method','executable':p.name,'scope':'manuscript','modes':['smoke'],
  'allowed_args':{'cutoff':'int'},'timeout_seconds':3}
 assert R.register_producer('book',spec,root)[0]==201
 summary=C.state_read('book',root,view='summary')[1]
 action=next(row for row in summary['producers'] if row['id']==spec['id'])['launch_action']
 assert action['fields'][1]=={'name':'args.cutoff','label':'cutoff','type':'integer','required':False}
 wire={**action['http']['payload'],'args':{'cutoff':7},'runtime_seconds':3}
 assert 'project' not in wire and parse_qs(urlsplit(action['http']['url']).query)=={'project':['book']}
 initial=R.inspect_request('book',wire,root)
 assert initial['effect']=='NONE' and initial['original_request']==wire
 assert json.loads(parse_qs(urlsplit(initial['read']['http']['url']).query)['request'][0])==wire
 activations=[]
 def withheld(admission):
  activations.append(admission.job['id']);return 202,{'run':admission.job,'qualification':'Supervisor activation withheld in this request-custody control.'}
 monkeypatch.setattr(R,'activate',withheld)
 code,admitted=R.launch('book',wire,root);assert code==202
 found=R.inspect_request('book',wire,root)
 assert found['effect']=='RECORDED' and found['original_request']==wire and found['run']['id']==admitted['run']['id']
 assert found['run_read']['native']['payload']=={'id':found['id']}
 assert R.launch('book',wire,root)[1]['reused'] and len(activations)==1
 assert R.inspect_request('book',{**wire,'args':{'cutoff':8}},root)['effect']=='CONFLICT'
 found['original_request']['args']['cutoff']=99
 assert R.inspect_request('book',wire,root)['original_request']==wire
 (root/'registered-request-action-proof.json').write_text(json.dumps({'action':action,'wire':wire,'initial':initial,
  'recorded':R.inspect_request('book',wire,root),'activation_count':len(activations)},indent=2))


def test_actual_complete_run_record_action_renewal_and_lost_ack_request_custody(run_root,monkeypatch):
 import os,time
 from laplace.research import research_runs as R,research_records as RR
 from laplace.core.records import journal
 s=run_root;root=s['root'];_wire,_binding,source=research_delivery(s)
 def complete(request):
  code,value=R.launch('book',{'producer_id':'public-method','mode':'smoke','args':{},'runtime_seconds':3,'request_id':request},root)
  assert code==202,value
  end=time.monotonic()+10
  while time.monotonic()<end:
   code,run=R.run_status_read('book',value['run']['id'],root)
   if run.get('state')!='RUNNING':break
   time.sleep(.025)
  assert run['state']=='COMPLETE' and run['cleanup']['status']=='VERIFIED',run
  try:os.waitpid(run['pid'],0)
  except ChildProcessError:pass
  return run
 first=complete('public-record-first-run')
 action=first['record_result']['new'];wire=copy.deepcopy(action['http']['payload'])
 wire['record'].update(title='Seven included public unit weights',summary='The actual public calculation returned seven.',limitations='Deterministic fixture; no scientific acceptance.')
 assert RR.inspect_request('book',wire,root)['effect']=='NONE'
 real_response=RR._record_response
 monkeypatch.setattr(RR,'_record_response',lambda *a,**k:(_ for _ in ()).throw(OSError('Lost post-publication response.')))
 with pytest.raises(OSError,match='Lost post-publication'):RR.record('book',wire,root)
 monkeypatch.setattr(RR,'_record_response',real_response)
 observed=RR.inspect_request('book',wire,root);assert observed['effect']=='RECORDED'
 first_record=copy.deepcopy(observed['record']);assert first_record['run_id']==first['id']
 assert RR.record('book',wire,root)[1]['replayed']
 source.write_text(source.read_text().replace("'value':7","'value':8"))
 second=complete('public-record-second-run')
 choice=next(x for x in second['record_result']['existing']['items'] if x['reference']['identity']['id']==first_record['id'])
 renewal=copy.deepcopy(choice['action']['http']['payload'])
 assert renewal['expected_revision']==first_record['revision']
 renewal['record'].update(title='Eight included public unit weights',summary='The changed public calculation returned eight.',limitations='Changed declared input/code; reconsider scientific use separately.')
 real_bank=journal.bank_row
 monkeypatch.setattr(journal,'bank_row',lambda *a,**k:(_ for _ in ()).throw(OSError('Lost post-publication journal projection.')))
 with pytest.raises(OSError,match='journal projection'):RR.record('book',renewal,root)
 monkeypatch.setattr(journal,'bank_row',real_bank)
 current=RR.inspect_request('book',renewal,root)
 assert current['effect']=='RECORDED' and current['record']['run_id']==second['id']
 assert current['record']['result']!=first_record['result'] and RR.record('book',renewal,root)[1]['replayed']
 historical=RR.inspect_request('book',wire,root)
 assert historical['historical'] and historical['record']==first_record
 assert RR.record('book',wire,root)[1]['record']==first_record  # replay before stale CAS/run/source checks
 changed=copy.deepcopy(renewal);changed['record']['summary']='A different intent under the original identity.'
 assert RR.record('book',changed,root)[0]==409
 assert len(RR._renewal_history(s['manuscript'])[first_record['id']])==1
 (root/'actual-complete-record-action-proof.json').write_text(json.dumps({'first_run':first,'first_wire':wire,
  'first_record':first_record,'second_run':second,'renewal_wire':renewal,'renewed':current,'historical':historical,
  'qualification':'Actual supervised public processes and canonical owner record/replay; no browser/model or inferred scientific acceptance.'},indent=2))
