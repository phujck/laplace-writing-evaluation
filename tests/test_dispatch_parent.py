"""One admitted parent observation and typed synthesis, without a new scheduler."""
import json
import time

import pytest

from laplace.work import project_work
from laplace.writing import provider as writing_provider
from laplace.native import tools as writing_tools
from laplace.writing import records
from laplace.writing import child_hosts
from laplace.writing import turn_control
from laplace.writing import turn_admission
from laplace.writing import session_reads
from laplace.writing import dispatch_execution
from laplace.writing import turn_jobs
from laplace.writing import provider as writing_provider
from laplace.writing import dispatch_parent
from test_dispatch_plan_contract import parent, example


def synthesis_case(root, *, accepted=True, consumed=True):
    """Real plan, typed child returns, owner READs and ART receipts, no provider."""
    import hashlib
    from laplace.projects import artifacts
    from test_packet_return_lifecycle import judgement
    plan=example();plan['synthesis_return_path']='development/parent-return.json'
    made=writing_tools.execute(root,'book','work','dispatch_plan',{
        'title':'Finite synthesis','goal':plan['goal'],'path':'development/connected-plan.json','plan':plan},turn_id='WT-parent')
    ident=made['dispatch_id'];path=root/made['plan_artifact']
    project_work.transition('book',{'id':ident,'status':'in-progress'},root,dispatch_receipt={
        'dispatch_admitted':True,'dispatch_parent_turn_id':'WT-parent',
        'dispatch_plan_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'dispatch_launch_state':'STARTED'})
    report=writing_tools.execute(root,'book','work','store_artifact',{
        'path':'development/report.md','before':None,'reason':'Retain exact fixture evidence.','content':'Exact child result.'},turn_id='WT-parent')
    pin={'path':made['plan_artifact'],'sha256':made['plan_revision']}
    output={'path':report['path'],'sha256':report['revision']}
    worker={'schema_version':'laplace.packet-return/2','packet':plan['packets'][0]['packet'],
        'role':'build','status':'COMPLETE','goal':plan['goal'],'inputs':[pin],
        'source':{'kind':'artifacts','root':str(root),'artifacts':[pin,output]},'output':output,
        'files_written':[report['path']],'summary':'Exact result is retained.',
        'most_important':['The result bytes match the admitted input.'],
        'scripted_check':{'kind':'command','state':'PASSED','command':'fixture exact bytes',
            'exit_code':0,'output_tail':'Exact bytes observed.'},'residuals':[],'remaining_work':[],'continuation':None}
    for index,item in enumerate(plan['packets']):
        session=f'WS-child-{index}';turn=f'WT-child-{index}'
        role='review' if item['role']=='judge' else 'author'
        records.bank(root,{'record':'writing-session','id':session,'project':'book',
            'role':role,'dispatch_id':ident,'packet':item['packet'],'provider':'claude','model':'haiku','effort':'low'})
        records.bank(root,{'record':'writing-turn','id':turn,'session_id':session,'project':'book',
            'mode':'review' if role=='review' else 'work','dispatch_id':ident,'parent_turn_id':'WT-parent'})
        if role=='author':document=worker
        else:
            returned=artifacts.resolve_path(root,'book',plan['packets'][0]['return_path'])
            document=judgement(worker,returned);document['packet']=worker['packet']
            document['judged']['review_context']['session_id']=session
            receipt=writing_tools.execute(root,'book','review','read_artifact',{'path':'development/report.md'},turn_id=turn)['read_receipt']
            check={'kind':'owner-read','state':'PASSED','operation':receipt['operation'],'payload':receipt['payload'],
                'receipt_id':receipt['id'],'output_sha256':receipt['output_sha256'],'ok':True,'output_tail':'Observed exact report.'}
            document['scripted_check']=check;document['own_observations']=[{k:v for k,v in check.items() if k!='state'}]
            if not accepted:
                document.update(accepted=False,accepted_subsets=[],deficiencies=[{
                    'id':'gap','item':'Declared result','problem':'A substantive condition remains unmet.',
                    'evidence':'The retained report omits the condition.','done_looks_like':'Resolve the declared condition.'}])
        writing_tools.execute(root,'book','review' if role=='review' else 'work','store_artifact',{
            'path':item['return_path'],'before':None,'reason':'Retain exact fixture evidence.','content':json.dumps(document)},turn_id=turn)
        records.bank(root,{'record':'writing-reply','id':f'WR-child-{index}',
            'project':'book','session_id':session,'turn_id':turn,'status':'completed','text':'Retained result.'})
    task=project_work._tasks('book',root)[ident]
    view=project_work.dispatch_view(task,'book',root)
    required,missing=dispatch_parent.required_inputs(task,'book',root,view=view)
    assert not missing
    if consumed:
        for entry in required:
            target=root/entry['path'];relative=target.relative_to(artifacts.project_root(root,'book')).as_posix()
            writing_tools.execute(root,'book','work','read_artifact',{'path':relative,'limit':40000},turn_id='WT-parent')
    synthesis={**worker,'packet':'parent-consumes','role':'synthesis','inputs':required}
    if not accepted:
        synthesis.update(status='BLOCKED',remaining_work=[{'work':'Resolve rejected worker result',
            'reason':'The independent judge rejected the condition.','next_action':'Inspect and repair exact retained result.'}],
            continuation={'artifacts':required,'next_action':'Inspect the rejection.','resume_condition':'Explicit parent recovery.'})
    return task,synthesis,view


@pytest.mark.parametrize('value',[True,False,0,-1,1.5,'300',{},2147479])
def test_invalid_observation_budget_refuses_before_session_effect(parent,value):
    with pytest.raises(ValueError,match='connected_observation_seconds'):
        turn_admission.start_turn(parent,{'project':'book','mode':'work','text':'Observe once.',
            'connected_observation_seconds':value})


def test_observation_budget_is_not_a_task_deadline_and_has_explicit_return_margin():
    assert dispatch_parent.observation_budget(None) is None
    policy=dispatch_parent.observation_budget(300)
    assert policy['admitted_seconds']==300 and policy['transport_timeout_ms']==305000
    assert policy['return_margin_ms']==5000 and 'deadline_seconds' not in policy


@pytest.mark.parametrize('role,dispatch_id',[('review',None),('author','WORK-child-dispatch')])
def test_actual_child_or_reviewer_cannot_admit_parent_budget(parent,role,dispatch_id):
    records.bank(parent,{'record':'writing-session','id':'WS-protected','project':'book',
        'provider':'claude','model':'haiku','effort':'low','role':role,
        **({'dispatch_id':dispatch_id} if dispatch_id else {})})
    with pytest.raises(ValueError,match='actual author parent'):
        turn_admission.start_turn(parent,{'project':'book','session_id':'WS-protected','mode':'work',
            'text':'Observe once.','connected_observation_seconds':300})


def test_explicit_parent_budget_is_persisted_before_provider_and_omission_stays_absent(parent,monkeypatch):
    admitted=[]
    class Turn:
        def __init__(self,*args,**kwargs):self.native_id=None;self.inference_started=False
        def run(self,prompt):admitted.append(getattr(self,'connected_observation',None));return {'status':'completed','text':'Finite fixture reply.'}
        def interrupt(self):return {}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Turn)
    for supplied in (None,300):
        value={'project':'book','session_id':'WS-parent','mode':'work','text':'Explicit finite observation.'}
        if supplied is not None:value['connected_observation_seconds']=supplied
        started=turn_admission.start_turn(parent,value)
        until=time.monotonic()+5
        while not turn_jobs._JOBS[started['turn_id']]['done'] and time.monotonic()<until:time.sleep(.01)
        assert turn_jobs._JOBS[started['turn_id']]['done']
        row=session_reads._records(parent)['turns'][started['turn_id']]
        if supplied is None:assert 'connected_observation' not in row
        else:assert row['connected_observation']==admitted[-1] and admitted[-1]['admitted_seconds']==300


def test_claude_timeout_is_invocation_local_and_matches_original_admission(parent,monkeypatch):
    import subprocess
    captured=[]
    class Stopped(Exception):pass
    def capture(argv,**kwargs):captured.append((argv,kwargs));raise Stopped
    monkeypatch.setattr(subprocess,'Popen',capture)
    monkeypatch.setattr(writing_provider.shutil,'which',lambda name:'/fixture/claude' if name=='claude' else None)
    turn=writing_provider.WritingTurn(parent,'claude','haiku',None,None,lambda event:None,
        mode='work',project='book',logical_turn_id='WT-parent',session_id='WS-parent')
    turn.supports_effort=False;turn.connected_observation=dispatch_parent.observation_budget(300)
    with pytest.raises(Stopped):turn.run('Observe the finite admitted dispatch once.')
    argv,_=captured[0];config=json.loads(argv[argv.index('--mcp-config')+1])
    assert config['mcpServers']['laplace']['timeout']==305000


def test_optional_parent_return_path_is_reserved_without_changing_legacy_plan(parent):
    plan=example()
    assert 'synthesis_return_path' not in plan
    assert dispatch_execution.launch_dispatch(parent,'book','WT-parent',{'plan':plan},validate_only=True)['validated']
    plan['synthesis_return_path']=plan['packets'][0]['return_path']
    with pytest.raises(ValueError,match='distinct return path'):
        dispatch_execution.launch_dispatch(parent,'book','WT-parent',{'plan':plan},validate_only=True)
    plan['synthesis_return_path']='development/parent-return.json'
    assert dispatch_execution.launch_dispatch(parent,'book','WT-parent',{'plan':plan},validate_only=True)['validated']


@pytest.mark.parametrize('accepted',[True,False])
def test_synthesis_owner_attaches_exact_accepted_or_rejected_evidence_and_detects_drift(parent,accepted):
    from laplace.projects import artifacts
    from work_read_helpers import guarded_transition
    task,document,view=synthesis_case(parent,accepted=accepted)
    assert view['execution_state']=='COMPLETE' and view['review_state']==('ACCEPTED' if accepted else 'REJECTED'),json.dumps(view,indent=1)
    assert not dispatch_parent.return_errors(document,task,'book',parent,actor_turn_id='WT-parent')
    stored=writing_tools.execute(parent,'book','work','store_artifact',{'path':'development/parent-return.json',
        'before':None,'reason':'Retain exact fixture evidence.','content':json.dumps(document)},turn_id='WT-parent')
    observed=dispatch_parent.synthesis_view(task,'book',parent)
    assert observed['status']=='VALID' and observed['artifact']['id']==stored['id']
    action=observed['attach_action']
    assert action['http']=={'method':'POST','url':'/work/transition'} and action['permitted']
    writing_tools.execute(parent,'book','work','task_status',action['payload'],turn_id='WT-parent')
    retained=project_work._tasks('book',parent)[task['id']]
    assert retained['status']==('done' if accepted else 'blocked')
    assert any(row['path']==stored['path'] and row['sha256']==stored['revision'] for row in retained['evidence_receipts'])
    assert dispatch_parent.synthesis_view(retained,'book',parent)['attachment']=='ATTACHED'
    artifacts.resolve_path(parent,'book','development/report.md').write_text('Changed report.')
    assert dispatch_parent.synthesis_view(retained,'book',parent)['status']=='INVALID'
    if accepted:
        detail=project_work.read('book',{'view':'detail','id':task['id']},parent)['task']
        assert detail['status']!='done' or not detail.get('completion_current',True),detail
    else:
        with pytest.raises(ValueError):guarded_transition('book',{'id':task['id'],'status':'done'},parent)


def test_synthesis_requires_complete_consumed_input_set_and_parent_actor(parent):
    task,document,_=synthesis_case(parent,consumed=False)
    with pytest.raises(ValueError,match='consumed exact owner-read'):
        writing_tools.execute(parent,'book','work','store_artifact',{'path':'development/parent-return.json',
            'before':None,'reason':'Retain exact fixture evidence.','content':json.dumps(document)},turn_id='WT-parent')
    assert not (parent/task['evidence'][0]).with_name('parent-return.json').exists()
    from laplace.projects import artifacts
    for pin in document['inputs']:
        relative=(parent/pin['path']).relative_to(artifacts.project_root(parent,'book')).as_posix()
        writing_tools.execute(parent,'book','work','read_artifact',{'path':relative,'limit':40000},turn_id='WT-parent')
    omitted={**document,'inputs':document['inputs'][:-1]}
    with pytest.raises(ValueError,match='omits or changes required'):
        artifacts.store(parent,'book',{'path':'development/parent-return.json','before':None,'reason':'Retain exact fixture evidence.','content':json.dumps(omitted)},'WT-parent')
    with pytest.raises(ValueError,match='original or explicitly recovered'):
        artifacts.store(parent,'book',{'path':'development/parent-return.json','before':None,'reason':'Retain exact fixture evidence.','content':json.dumps(document)},'WT-child-0')
    with pytest.raises(ValueError,match='cannot overwrite'):
        writing_tools.execute(parent,'book','work','store_artifact',{'path':'development/parent-return.json',
            'before':None,'reason':'Retain exact fixture evidence.','content':json.dumps(document)},turn_id='WT-child-0')


def test_publication_survives_attachment_failure_with_exact_idempotent_recovery(parent,monkeypatch):
    from laplace.projects import artifacts
    from laplace.writing import records
    task,document,_=synthesis_case(parent)
    stored=artifacts.store(parent,'book',{'path':'development/parent-return.json',
        'before':None,'reason':'Retain exact fixture evidence.','content':json.dumps(document)},'WT-parent')
    action=dispatch_parent.synthesis_view(task,'book',parent)['attach_action']
    original=project_work._append
    with monkeypatch.context() as patch:
        patch.setattr(project_work,'_append',lambda *a:(_ for _ in ()).throw(OSError('Work storage unavailable')))
        with pytest.raises(OSError,match='storage unavailable'):
            project_work.transition('book',action['payload'],parent)
    observed=dispatch_parent.synthesis_view(task,'book',parent)
    assert observed['artifact']['id']==stored['id'] and observed['attachment']=='MISSING'
    project_work.transition('book',observed['attach_action']['payload'],parent)
    assert dispatch_parent.synthesis_view(project_work._tasks('book',parent)[task['id']],'book',parent)['attachment']=='ATTACHED'
    assert len([row for row in records.index(parent).by_project['book'] if row.get('record')=='writing-artifact'
        and row.get('path')==stored['path']])==1


def observation_case(root, *, work=False, started=None):
    import hashlib
    from work_read_helpers import guarded_transition
    work_id=None
    if work:
        prerequisite=project_work.task('book',{'title':'Unrelated prerequisite','goal':'Retain independent standing'},root)
        work_id=project_work.task('book',{'title':'Parent goal','goal':'Finish joined execution',
            'depends_on':[prerequisite['id']]},root)['id']
    turn='WT-observer'
    records.bank(root,{'record':'writing-turn','id':turn,'session_id':'WS-parent','project':'book',
        'mode':'work','connected_observation':dispatch_parent.observation_budget(1),
        **({'work_id':work_id} if work_id else {})})
    plan=example();plan['synthesis_return_path']='development/observed-parent-return.json'
    made=writing_tools.execute(root,'book','work','dispatch_plan',{'title':'Observed dispatch','goal':plan['goal'],
        'path':'development/observed-plan.json','plan':plan},turn_id=turn)
    task=project_work._tasks('book',root)[made['dispatch_id']]
    if work_id:
        rows=project_work._tasks('book',root);parent_task=rows[work_id]
        project_work.task('book',{'id':task['id'],'expected_work_revision':project_work._task_revision(task),
            'parent_work_id':work_id},root)
        task=project_work._tasks('book',root)[task['id']]
        project_work.task('book',{'id':work_id,'expected_work_revision':project_work._task_revision(parent_task),
            'depends_on':list(dict.fromkeys(parent_task['depends_on']+[task['id']]))},root)
    child_hosts._begin_child_execution(root,'WS-parent',{'state':'RUNNING','turn_id':turn,
        'session_id':'WS-parent','project':'book','host':child_hosts._process_identity()})
    observation=dispatch_parent.prepare_observation(task,'book',root,turn,started if started is not None else time.time())
    admission={k:v for k,v in observation.items() if not k.startswith('_')};admission['basis']=observation['_basis']
    project_work.transition('book',{'id':task['id'],'status':'in-progress'},root,dispatch_receipt={
        'dispatch_admitted':True,'dispatch_parent_turn_id':turn,'dispatch_parent_observation':admission,
        'dispatch_plan_sha256':hashlib.sha256((root/made['plan_artifact']).read_bytes()).hexdigest(),
        'dispatch_deadline_at':time.time()+120,'dispatch_launch_state':'STARTED'})
    dispatch_parent.install_observation(root,observation)
    return project_work._tasks('book',root)[task['id']],observation


def observed_view(task, *, execution='COMPLETE',review='ACCEPTED',active=False):
    return {'execution_state':execution,'review_state':review,'children':[
        {'packet':label,'role':role,'session_id':f'WS-wait-{index}',
         'execution':{'state':'RUNNING' if active else 'FINISHED'}}
        for index,(label,role) in enumerate([('develop','worker'),('review','judge')])]}


@pytest.mark.parametrize('execution,review',[('COMPLETE','ACCEPTED'),('COMPLETE','REJECTED'),('FAILED','PENDING')])
def test_settled_success_rejection_or_failure_wakes_same_parent_with_separate_standing(parent,monkeypatch,execution,review):
    task,observation=observation_case(parent)
    monkeypatch.setattr(project_work,'dispatch_view',lambda *a,**k:observed_view(task,execution=execution,review=review))
    result=dispatch_parent.await_observation(parent,'book',observation)
    assert result['phase']=='READY' and result['review_state']==review and result['execution_state']==execution
    assert child_hosts._child_execution_record(parent,'WS-parent')['state']=='RUNNING'
    with pytest.raises(ValueError,match='already used its one'):
        dispatch_parent.prepare_observation(task,'book',parent,'WT-observer',time.time())


def test_expiry_precedes_late_settlement_and_never_renews_budget_or_child_deadline(parent,monkeypatch):
    task,observation=observation_case(parent,started=time.time()-2)
    monkeypatch.setattr(project_work,'dispatch_view',lambda *a,**k:observed_view(task))
    result=dispatch_parent.await_observation(parent,'book',observation)
    assert result['phase']=='OBSERVATION_EXPIRED'
    assert project_work._tasks('book',parent)[task['id']]['dispatch_deadline_at']==task['dispatch_deadline_at']
    assert dispatch_parent.final_receipt(parent,'WS-parent','WT-observer',interrupted=True)['phase']=='OBSERVATION_EXPIRED'


def test_missing_immutable_parent_reply_remains_unknown_after_host_cleanup(parent):
    task,observation=observation_case(parent)
    child_hosts._update_child_execution(parent,'WS-parent',{'parent_continuation':{
        **{key:value for key,value in observation.items() if not key.startswith('_')},'phase':'READY'}},
        expected_turn_id='WT-observer')
    child_hosts._finish_child_execution(parent,'WS-parent','WT-observer','completed')
    retained=dispatch_parent.recorded(parent,'book',task)
    assert retained['origin_execution']=='UNKNOWN' and retained['phase']=='BLOCKED'
    public=session_reads.child_execution(parent,'WS-parent')['parent_continuation']
    assert public['origin_execution']=='UNKNOWN' and not public['parent_active']


def retained_execution_case(parent):
    from laplace.writing import prepared_work
    task,observation=observation_case(parent,work=True)
    original=dispatch_parent.final_receipt(parent,'WS-parent','WT-observer',author_stopped=True)
    records.bank(parent,{'record':'writing-reply','id':'WR-retained-origin','project':'book',
        'session_id':'WS-parent','turn_id':'WT-observer','status':'interrupted','parent_continuation':original})
    child_hosts._finish_child_execution(parent,'WS-parent','WT-observer','interrupted')
    records.bank(parent,{'record':'writing-turn','id':'WT-no-new-wait','project':'book','session_id':'WS-parent',
        'work_id':observation['work_id'],'mode':'work'})
    child_hosts._begin_child_execution(parent,'WS-parent',{'project':'book','session_id':'WS-parent',
        'turn_id':'WT-no-new-wait','state':'RUNNING','host':child_hosts._process_identity()})
    records.bank(parent,{'record':'writing-reply','id':'WR-no-new-wait','project':'book',
        'session_id':'WS-parent','turn_id':'WT-no-new-wait','status':'interrupted'})
    child_hosts._finish_child_execution(parent,'WS-parent','WT-no-new-wait','interrupted')
    result=prepared_work.executions('book',parent,observation['work_id'])
    owned=project_work.read('book',{'view':'detail','id':observation['work_id']},parent)['task']
    action=prepared_work.run_action('book',owned,{'current':True},result)
    return {'execution':result,'task':owned,'run_action':action,'dispatch_id':task['id']}


def test_prepared_execution_retains_exact_dispatch_after_newer_recovery_without_wait(parent):
    case=retained_execution_case(parent);result=case['execution'];action=case['run_action']
    assert 'parent_continuation' not in result['items'][-1]
    assert result['parent_continuation']['dispatch_id']==case['dispatch_id'] and len(result['retained_dispatches'])==1
    assert action['payload']['session_id']=='WS-parent' and case['dispatch_id'] in action['payload']['text']
    assert 'create a dispatch_plan' not in action['payload']['text']


def test_parent_stop_and_new_generation_do_not_cancel_children_or_revive_old_observation(parent,monkeypatch):
    task,observation=observation_case(parent)
    monkeypatch.setattr(project_work,'dispatch_view',lambda *a,**k:observed_view(task,active=True,execution='RUNNING',review='PENDING'))
    turn_control.interrupt_turn(parent,{'project':'book','turn_id':'WT-observer'})
    assert dispatch_parent.await_observation(parent,'book',observation)['phase']=='PARENT_STOPPED'
    assert project_work._tasks('book',parent)[task['id']]['status']=='in-progress'
    receipt=dispatch_parent.final_receipt(parent,'WS-parent','WT-observer',author_stopped=True)
    records.bank(parent,{'record':'writing-reply','id':'WR-observer','project':'book',
        'turn_id':'WT-observer','session_id':'WS-parent','status':'interrupted','parent_continuation':receipt})
    child_hosts._finish_child_execution(parent,'WS-parent','WT-observer','interrupted')
    child_hosts._begin_child_execution(parent,'WS-parent',{'state':'RUNNING','turn_id':'WT-newer','session_id':'WS-parent',
        'project':'book','host':child_hosts._process_identity()})
    assert dispatch_parent.await_observation(parent,'book',observation)['phase']=='PARENT_STOPPED'
    assert child_hosts._child_execution_record(parent,'WS-parent')['turn_id']=='WT-newer'
    assert dispatch_parent.recorded(parent,'book',task)['turn_id']=='WT-observer'


def test_unrelated_prerequisite_drift_refuses_without_refreshing_waited_dispatch_basis(parent):
    task,observation=observation_case(parent,work=True)
    from work_read_helpers import guarded_transition
    work=project_work._tasks('book',parent)[observation['work_id']]
    unrelated=next(ident for ident in work['depends_on'] if ident!=task['id'])
    guarded_transition('book',{'id':unrelated,'status':'blocked','summary':'Changed prerequisite.'},parent)
    result=dispatch_parent.await_observation(parent,'book',observation)
    assert result['phase']=='STALE' and 'unrelated prerequisite' in result['reason']


def test_partial_launch_names_unstarted_packets_and_does_not_claim_settlement(parent,monkeypatch):
    task,observation=observation_case(parent)
    view=observed_view(task);view['children']=view['children'][:1];view['execution_state']='FAILED'
    required,missing=dispatch_parent.required_inputs(task,'book',parent,view=view)
    assert missing==['develop','review']
    monkeypatch.setattr(project_work,'dispatch_view',lambda *a,**k:view)
    public=dispatch_parent.public(parent,'book',observation,task=task,view=view)
    assert not public['execution_settled'] and public['parent_return_contract']['missing_packets']==missing


def test_exact_same_session_recovery_publishes_after_newer_turn_without_borrowing_original_reads(parent):
    from laplace.projects import artifacts
    task,document,_=synthesis_case(parent)
    records.bank(parent,{'record':'writing-turn','id':'WT-recovery','session_id':'WS-parent','project':'book',
        'mode':'work','work_id':task['id']})
    with pytest.raises(ValueError,match='consumed exact owner-read'):
        artifacts.store(parent,'book',{'path':'development/parent-return.json','before':None,
            'content':json.dumps(document)},'WT-recovery')
    for pin in document['inputs']:
        relative=(parent/pin['path']).relative_to(artifacts.project_root(parent,'book')).as_posix()
        writing_tools.execute(parent,'book','work','read_artifact',{'path':relative,'limit':40000},turn_id='WT-recovery')
    stored=artifacts.store(parent,'book',{'path':'development/parent-return.json','before':None,
        'content':json.dumps(document)},'WT-recovery')
    assert dispatch_parent.synthesis_view(task,'book',parent)['artifact']['id']==stored['id']


def test_historical_continuation_uses_only_exact_session_metadata_and_reply(parent,monkeypatch):
    from laplace.writing import records
    task,observation=observation_case(parent)
    receipt=dispatch_parent.final_receipt(parent,'WS-parent','WT-observer',author_stopped=True)
    records.bank(parent,{'record':'writing-reply','id':'WR-origin','project':'book','session_id':'WS-parent',
        'turn_id':'WT-observer','status':'interrupted','parent_continuation':receipt})
    for index in range(100):
        records.bank(parent,{'record':'writing-turn','id':f'WT-unrelated-{index}',
            'session_id':f'WS-unrelated-{index}','project':'book','mode':'work'})
    child_hosts._begin_child_execution(parent,'WS-parent',{'state':'RUNNING','turn_id':'WT-newer',
        'session_id':'WS-parent','project':'book','host':child_hosts._process_identity()})
    idx=records.index(parent)
    class ExactOnly(dict):
        def values(self):pytest.fail('Global turn-map traversal during exact reply recovery.')
    monkeypatch.setattr(idx,'turns',ExactOnly(idx.turns))
    opened=[];original=records.selected_journal_fields
    def selected(project,ident,root,**kwargs):opened.append(ident);return original(project,ident,root,**kwargs)
    monkeypatch.setattr(records,'selected_journal_fields',selected)
    assert dispatch_parent.recorded(parent,'book',task)['origin_parent_turn_id']=='WT-observer'
    assert opened==['WR-origin']


def test_synthesis_consumption_reuses_exact_validation_cut_and_dispatch_returns_producer(parent,monkeypatch):
    from laplace.projects import artifacts
    task,document,_=synthesis_case(parent,consumed=False)
    pin=document['inputs'][0]
    relative=(parent/pin['path']).relative_to(artifacts.project_root(parent,'book')).as_posix()
    writing_tools.execute(parent,'book','work','read_artifact',{'path':relative,'limit':40000},turn_id='WT-parent')
    writing_tools.execute(parent,'book','work','dispatch_returns',{'id':task['id'],'limit':40000},turn_id='WT-parent')
    assert not dispatch_parent.return_errors(document,task,'book',parent,actor_turn_id='WT-parent')
    original=artifacts.read;opened=[]
    def read(*args,**kwargs):opened.append(args[2]);return original(*args,**kwargs)
    monkeypatch.setattr(artifacts,'read',read)
    assert not dispatch_parent.return_errors(document,task,'book',parent,actor_turn_id='WT-parent')
    assert not opened,'Same exact immutable validation cut re-read artifact bodies.'


def test_reserved_path_lookup_reuses_unchanged_plan_files(parent,monkeypatch):
    from laplace.projects import artifacts
    task,document,_=synthesis_case(parent)
    target=artifacts.resolve_path(parent,'book','development/unreserved.md')
    dispatch_parent.publication_task(parent,'book',target)
    original=dispatch_parent.plan;opened=[]
    def read_plan(*args):opened.append(args[0]['id']);return original(*args)
    monkeypatch.setattr(dispatch_parent,'plan',read_plan)
    for index in range(10):assert dispatch_parent.publication_task(parent,'book',target) is None
    assert not opened,'Unrelated artifact writes reread every unchanged dispatch plan.'


def test_many_unrelated_dispatches_have_constant_warm_reservation_lookup(parent,monkeypatch):
    from laplace.projects import artifacts
    for index in range(40):
        declared=example();declared['synthesis_return_path']=f'development/reserved-{index}.json'
        path=f'development/plan-{index}.json'
        stored=artifacts.store(parent,'book',{'path':path,'before':None,'content':json.dumps(declared)},'WT-parent')
        project_work.task('book',{'title':f'Unrelated dispatch {index}','goal':'Retain exact reservation.',
            'kind':'dispatch','evidence':[stored['path']]},parent)
    target=artifacts.resolve_path(parent,'book','development/unreserved.md')
    dispatch_parent.publication_task(parent,'book',target)
    original=dispatch_parent._file_identity;observed=[]
    def identity(path):observed.append(path);return original(path)
    monkeypatch.setattr(dispatch_parent,'_file_identity',identity)
    monkeypatch.setattr(dispatch_parent,'plan',lambda *a:pytest.fail('Warm unrelated write read a plan body.'))
    for index in range(5):assert dispatch_parent.publication_task(parent,'book',target) is None
    assert observed==[project_work._ledger(parent)]*5


def test_out_of_band_plan_drift_cannot_transfer_original_synthesis_reservation(parent):
    from laplace.projects import artifacts
    task,document,_=synthesis_case(parent)
    path=parent/task['evidence'][0];declared=json.loads(path.read_bytes())
    declared['synthesis_return_path']='development/drifted-reservation.json';path.write_text(json.dumps(declared))
    with pytest.raises(ValueError,match='reservation changed'):
        artifacts.store(parent,'book',{'path':'development/parent-return.json','before':None,
            'content':json.dumps(document)},'WT-parent')
    assert dispatch_parent.publication_task(parent,'book',artifacts.resolve_path(parent,'book','development/drifted-reservation.json')) is None


@pytest.mark.parametrize('stop',[False,True])
def test_actual_parent_governor_banks_final_receipt_before_host_finish_without_child_cancel(parent,monkeypatch,stop):
    import threading
    entered=threading.Event();interrupted=threading.Event();observed={}
    class Provider:
        def __init__(self,*args,**kwargs):
            self.turn_id=kwargs['logical_turn_id'];self.inference_started=True;self.native_id=None
        def run(self,prompt):
            declared=example();declared['synthesis_return_path']='development/governed-synthesis.json'
            planned=writing_tools.execute(parent,'book','work','dispatch_plan',{
                'title':'Governed dispatch','goal':declared['goal'],'path':'development/governed-plan.json',
                'plan':declared},turn_id=self.turn_id)
            observed['dispatch_id']=planned['dispatch_id'];entered.set()
            result=writing_tools.execute(parent,'book','work','dispatch_launch',{
                'id':planned['dispatch_id'],'await_completion':True},turn_id=self.turn_id)
            observed['native_result']=result
            assert interrupted.wait(3),'Connected parent governor did not end inference.'
            return {'status':'interrupted','text':'The exact parent observation ended.'}
        def interrupt(self):interrupted.set();return {}
    monkeypatch.setattr(writing_provider, 'WritingTurn',Provider)
    monkeypatch.setattr(dispatch_execution, '_start_dispatch_children',lambda *a,**k:{'started':True,'dispatch_id':a[3],'children':[]})
    started=turn_admission.start_turn(parent,{'project':'book','session_id':'WS-parent','mode':'work',
        'text':'Observe the exact dispatch once.','connected_observation_seconds':5 if stop else 1})
    assert entered.wait(3)
    until=time.monotonic()+3
    while time.monotonic()<until:
        host=child_hosts._child_execution_record(parent,'WS-parent')
        if host.get('parent_continuation'):break
        time.sleep(.01)
    assert host['state']=='RUNNING' and host['parent_continuation']['phase']=='WAITING'
    if stop:turn_control.interrupt_turn(parent,{'project':'book','turn_id':started['turn_id']})
    until=time.monotonic()+6
    while not turn_jobs._JOBS[started['turn_id']]['done'] and time.monotonic()<until:time.sleep(.01)
    assert turn_jobs._JOBS[started['turn_id']]['done']
    reply=session_reads._records(parent)['turns'][started['turn_id']]['reply']
    assert reply['parent_continuation']['phase']==('PARENT_STOPPED' if stop else 'OBSERVATION_EXPIRED')
    assert project_work._tasks('book',parent)[observed['dispatch_id']]['status']=='in-progress'
    summary=session_reads.session_state(parent,'WS-parent',view='summary')
    assert summary['turns'][-1]['parent_continuation']['phase']==reply['parent_continuation']['phase']


def waited_children(root, task, running):
    for index in range(2):
        session=f'WS-wait-{index}'
        child_hosts._begin_child_execution(root,session,{'state':'RUNNING','turn_id':f'WT-wait-{index}','session_id':session,
            'project':'book','dispatch_id':task['id'],'host':child_hosts._process_identity()})
        if index not in running:child_hosts._finish_child_execution(root,session,f'WT-wait-{index}','completed')


def host_view(root, task):
    """A dispatch_view stand-in that reads the real child host records and follows the task row's standing."""
    children=[{'packet':label,'role':role,'session_id':f'WS-wait-{index}',
        'execution':{'state':child_hosts._child_execution_record(root,f'WS-wait-{index}').get('state')}}
        for index,(label,role) in enumerate([('develop','worker'),('review','judge')])]
    active=any(row['execution']['state']=='RUNNING' for row in children)
    return {'execution_state':'CANCELLED' if task.get('status')=='cancelled' else 'RUNNING' if active else 'COMPLETE',
        'review_state':'PENDING' if active else 'ACCEPTED','children':children}


@pytest.mark.parametrize('settles',[{1:[0]},{1:[1],2:[0]}],ids=['in-first-fold','in-first-and-second-fold'])
def test_child_settling_during_unlocked_fold_is_refolded_to_ready(parent,monkeypatch,settles):
    import threading
    task,observation=observation_case(parent)
    waited_children(parent,task,{index for indexes in settles.values() for index in indexes})
    folds=[];landed=[]
    def fold(task_arg,project,root,**kwargs):
        folds.append(1);view=host_view(parent,task_arg)   # the fold has read the host records ...
        for index in settles.get(len(folds),[]):          # ... when a child finishes, under the real lock, before it returns
            finisher=threading.Thread(target=child_hosts._finish_child_execution,args=(parent,f'WS-wait-{index}',f'WT-wait-{index}','completed'))
            finisher.start();finisher.join(timeout=5);landed.append(not finisher.is_alive())
        return view
    monkeypatch.setattr(project_work,'dispatch_view',fold)
    result=dispatch_parent.await_observation(parent,'book',observation)
    assert result['phase']=='READY' and result['execution_settled'] and not result['children_active'],(result['phase'],len(folds),landed)
    assert all(landed) and len(landed)==sum(map(len,settles.values()))


def test_work_write_between_task_read_and_cut_stamp_is_refolded(parent,monkeypatch):
    from work_read_helpers import guarded_transition
    task,observation=observation_case(parent)
    waited_children(parent,task,{0,1})
    folds=[];guards=[];real_guard=dispatch_parent.guard
    def fold(task_arg,project,root,**kwargs):
        folds.append(task_arg['status'])
        if len(folds)==1:project_work.task('book',{'title':'Unrelated write','goal':'Changes the ledger cut'},parent)
        return host_view(parent,task_arg)
    def guard(*args):
        real_guard(*args);guards.append(1)
        if len(guards)==2:   # lands after this tick's task read, before its cut is stamped
            guarded_transition('book',{'id':task['id'],'status':'cancelled','summary':'Cancelled while observed.'},parent)
    monkeypatch.setattr(project_work,'dispatch_view',fold);monkeypatch.setattr(dispatch_parent,'guard',guard)
    result=dispatch_parent.await_observation(parent,'book',observation)
    assert result['phase']=='BLOCKED' and result['execution_state']=='CANCELLED',(result['phase'],folds)


def torn_row(root, cut):
    """A real non-ASCII Work row taken back off the ledger end, split at an ASCII byte or inside a UTF-8 character."""
    project_work.task('book',{'title':'Réplique','goal':'An unrelated Work write'},root)
    ledger=project_work._ledger(root);data=ledger.read_bytes();start=data.rindex(b'\n',0,len(data)-1)+1
    row=data[start:];at=row.index('é'.encode())+1 if cut=='utf8' else row.index(b'"title"')+3
    ledger.write_bytes(data[:start])
    return row[:at],row[at:]


@pytest.mark.parametrize('cut',['json','utf8'])
@pytest.mark.parametrize('site',[0,1,2],ids=['tasks-read','guard','terminal-guard'])
def test_half_written_ledger_row_is_reread_never_fatal_or_stale(parent,monkeypatch,site,cut):
    task,observation=observation_case(parent)
    ledger=project_work._ledger(parent);head,tail=torn_row(parent,cut)
    guards=[];torn=[];real_guard=dispatch_parent.guard;real_tasks=project_work._tasks
    def append(data):
        with ledger.open('ab') as handle:handle.write(data)
    def guard(*args):
        guards.append(1)
        if len(guards)==site:append(head)   # a writer is mid-append when this guard reads the ledger ...
        return real_guard(*args)
    def tasks(*args):
        try:return real_tasks(*args)
        except ValueError as error:          # ... and completes its row after the torn read
            torn.append((len(guards),type(error).__name__));append(tail);raise
    if site==0:append(head)
    monkeypatch.setattr(dispatch_parent,'guard',guard);monkeypatch.setattr(project_work,'_tasks',tasks)
    monkeypatch.setattr(project_work,'dispatch_view',lambda *a,**k:observed_view(task))
    result=dispatch_parent.await_observation(parent,'book',observation)
    assert torn==[(site,'JSONDecodeError' if cut=='json' else 'UnicodeDecodeError')]
    assert result['phase']=='READY',(result['phase'],result['reason'])


def test_permanently_malformed_ledger_sleeps_between_reads_and_ends_at_deadline(parent,monkeypatch):
    task,observation=observation_case(parent)
    with project_work._ledger(parent).open('ab') as handle:handle.write(b'{"record": "work", "id": "never-completed')
    reads=[];real_tasks=project_work._tasks
    def tasks(*args):reads.append(time.time());return real_tasks(*args)
    monkeypatch.setattr(project_work,'_tasks',tasks)
    monkeypatch.setattr(project_work,'dispatch_view',lambda *a,**k:observed_view(task))
    result=dispatch_parent.await_observation(parent,'book',observation)
    assert result['phase']=='OBSERVATION_EXPIRED' and time.time()>=observation['observation_deadline_at']
    assert child_hosts._child_execution_record(parent,'WS-parent')['parent_continuation']['phase']=='OBSERVATION_EXPIRED'
    assert 1<=len(reads)<=8 and all(later-earlier>=.2 for earlier,later in zip(reads,reads[1:])),reads


def real_observation_case(root, *, judge_running):
    """observation_case's admitted dispatch carried to typed child returns, with owner READs, that the real fold accepts."""
    from laplace.projects import artifacts
    from test_packet_return_lifecycle import judgement
    task,observation=observation_case(root);basis=observation['_basis']
    plan=json.loads((root/basis['plan_path']).read_text(encoding='utf8'))
    report=writing_tools.execute(root,'book','work','store_artifact',{'path':'development/report.md','before':None,
        'reason':'Retain exact fixture evidence.','content':'Exact child result.'},turn_id='WT-observer')
    pin={'path':basis['plan_path'],'sha256':basis['plan_revision']};output={'path':report['path'],'sha256':report['revision']}
    worker={'schema_version':'laplace.packet-return/2','packet':plan['packets'][0]['packet'],'role':'build','status':'COMPLETE',
        'goal':plan['goal'],'inputs':[pin],'source':{'kind':'artifacts','root':str(root),'artifacts':[pin,output]},'output':output,
        'files_written':[report['path']],'summary':'Exact result is retained.','most_important':['The result bytes match the admitted input.'],
        'scripted_check':{'kind':'command','state':'PASSED','command':'fixture exact bytes','exit_code':0,'output_tail':'Exact bytes observed.'},
        'residuals':[],'remaining_work':[],'continuation':None}
    for index,item in enumerate(plan['packets']):
        session=f'WS-child-{index}';turn=f'WT-child-{index}';role='review' if item['role']=='judge' else 'author'
        records.bank(root,{'record':'writing-session','id':session,'project':'book','role':role,'dispatch_id':task['id'],
            'packet':item['packet'],'provider':'claude','model':'haiku','effort':'low'})
        records.bank(root,{'record':'writing-turn','id':turn,'session_id':session,'project':'book',
            'mode':'review' if role=='review' else 'work','dispatch_id':task['id'],'parent_turn_id':'WT-observer'})
        document=worker
        if role=='review':
            document=judgement(worker,artifacts.resolve_path(root,'book',plan['packets'][0]['return_path']));document['packet']=worker['packet']
            document['judged']['review_context']['session_id']=session
            receipt=writing_tools.execute(root,'book','review','read_artifact',{'path':'development/report.md'},turn_id=turn)['read_receipt']
            check={'kind':'owner-read','state':'PASSED','operation':receipt['operation'],'payload':receipt['payload'],
                'receipt_id':receipt['id'],'output_sha256':receipt['output_sha256'],'ok':True,'output_tail':'Observed exact report.'}
            document['scripted_check']=check;document['own_observations']=[{k:v for k,v in check.items() if k!='state'}]
        writing_tools.execute(root,'book','review' if role=='review' else 'work','store_artifact',{'path':item['return_path'],
            'before':None,'reason':'Retain exact fixture evidence.','content':json.dumps(document)},turn_id=turn)
        if role=='review' and judge_running:   # the judge stored its return and has not yet finished its turn
            child_hosts._begin_child_execution(root,session,{'state':'RUNNING','turn_id':turn,'session_id':session,
                'project':'book','dispatch_id':task['id'],'host':child_hosts._process_identity()})
        else:records.bank(root,{'record':'writing-reply','id':f'WR-child-{index}','project':'book','session_id':session,
            'turn_id':turn,'status':'completed','text':'Retained result.'})
    observation['observation_deadline_at']=time.time()+6   # the fixture's own setup must not spend the 1 s budget
    return project_work._tasks('book',root)[task['id']],observation


@pytest.mark.parametrize('judge_running',[True,False],ids=['judge-still-running','every-child-replied'])
def test_half_written_ledger_row_read_inside_the_real_fold_publishes_nothing(parent,monkeypatch,judge_running):
    import sys
    task,observation=real_observation_case(parent,judge_running=judge_running)
    ledger=project_work._ledger(parent);head,tail=torn_row(parent,'json')
    assert project_work.dispatch_view(task,'book',parent)['execution_state']==('RUNNING' if judge_running else 'COMPLETE')
    folding=[];torn=[];real_view=project_work.dispatch_view;real_tasks=project_work._tasks
    def append(data):
        with ledger.open('ab') as handle:handle.write(data)
    def view(*args,**kwargs):
        folding.append(1)
        try:return real_view(*args,**kwargs)
        finally:folding.pop()
    def tasks(*args):
        if not folding or torn:return real_tasks(*args)
        append(head)                           # a Work write is mid-append while the REAL fold reads the ledger ...
        try:return real_tasks(*args)
        except ValueError as error:torn.append((sys._getframe(1).f_code.co_name,type(error).__name__));raise
        finally:
            append(tail)                       # ... it completes, and the judge then finishes its turn
            if judge_running:
                records.bank(parent,{'record':'writing-reply','id':'WR-child-1','project':'book','session_id':'WS-child-1',
                    'turn_id':'WT-child-1','status':'completed','text':'Retained result.'})
                child_hosts._finish_child_execution(parent,'WS-child-1','WT-child-1','completed')
    monkeypatch.setattr(project_work,'dispatch_view',view);monkeypatch.setattr(project_work,'_tasks',tasks)
    result=dispatch_parent.await_observation(parent,'book',observation)
    assert torn==[('verify_read','JSONDecodeError')]   # project_work.py:782, caught at workflow.py:171 as a return error
    assert (result['phase'],result['execution_state'],result['review_state'])==('READY','COMPLETE','ACCEPTED'),result['reason']


def test_row_begun_before_the_fold_and_finished_after_it_publishes_nothing(parent,monkeypatch):
    task,observation=real_observation_case(parent,judge_running=False)
    ledger=project_work._ledger(parent);head,tail=torn_row(parent,'json')
    writer=['idle'];folding=[];guards=[];real_view=project_work.dispatch_view;real_tasks=project_work._tasks;real_guard=dispatch_parent.guard
    def append(data):
        with ledger.open('ab') as handle:handle.write(data)
    def guard(*args):
        real_guard(*args);guards.append(1)
        if len(guards)==1:append(head);writer[0]='begun'   # a writer begins its row after this tick's task read ...
    def view(*args,**kwargs):
        folding.append(1)
        try:return real_view(*args,**kwargs)
        finally:folding.pop()
    def tasks(*args):
        if folding and writer[0]=='begun':writer[0]='read-in-fold'   # ... stays half-written through the whole fold ...
        elif not folding and writer[0]=='read-in-fold':append(tail);writer[0]='finished'   # ... and finishes after it
        return real_tasks(*args)
    monkeypatch.setattr(dispatch_parent,'guard',guard);monkeypatch.setattr(project_work,'dispatch_view',view)
    monkeypatch.setattr(project_work,'_tasks',tasks)
    result=dispatch_parent.await_observation(parent,'book',observation)
    assert writer[0]=='finished'
    assert (result['phase'],result['execution_state'],result['review_state'])==('READY','COMPLETE','ACCEPTED'),result['reason']


def test_settled_dispatch_reaches_ready_while_work_appends_keep_landing(parent,monkeypatch):
    import threading
    task,observation=real_observation_case(parent,judge_running=False)
    observation['observation_deadline_at']=time.time()+20
    ledger=project_work._ledger(parent);real_view=project_work.dispatch_view
    folds=[];appends=[];bursting=threading.Event();stop=threading.Event()
    def identity():
        stat=ledger.stat();return stat.st_size,stat.st_mtime_ns
    def stream():   # far denser than the live ledger (median gap 5.4 s): four rows 0.05 s apart every 1.25 s
        while not stop.is_set():
            bursting.set()
            for _ in range(4):
                project_work.task('book',{'title':f'Unrelated {len(appends)}','goal':'Keeps the ledger moving'},parent)
                appends.append(time.time());stop.wait(.05)
            bursting.clear();stop.wait(1)
    def view(*args,**kwargs):
        if not folds:bursting.wait(5)   # the first fold overlaps a burst
        before=identity();time.sleep(.5);result=real_view(*args,**kwargs)   # a fold half as slow as the live one
        folds.append(identity()!=before);return result
    monkeypatch.setattr(project_work,'dispatch_view',view)
    writer=threading.Thread(target=stream);writer.start()
    try:
        began=time.time();result=dispatch_parent.await_observation(parent,'book',observation);seconds=time.time()-began
    finally:stop.set();writer.join()
    print('B1-STREAM folds',folds,'appends',len(appends),'seconds',round(seconds,2))
    assert (result['phase'],result['execution_state'],result['review_state'])==('READY','COMPLETE','ACCEPTED'),result['reason']
    assert folds[0] and not folds[-1] and len(folds)<=8 and seconds<10,(folds,seconds)
