"""Parent observation and synthesis composition over existing dispatch owners.

Execution remains in the existing host record; tasks, artifacts and typed return
profiles retain their own authority. This module introduces no job ledger.
"""
from __future__ import annotations

import hashlib
import copy
import json
from pathlib import Path
import threading
import time
import uuid
import weakref
from collections import OrderedDict

PARENT_PACKET = 'parent-consumes'
RETURN_MARGIN_MS = 5000
MAX_NATIVE_TIMER_SECONDS = (2**31-1-RETURN_MARGIN_MS)//1000
_CONDITIONS=weakref.WeakValueDictionary()
_CONDITIONS_LOCK=threading.Lock()
_RESERVATIONS=OrderedDict()
_CONSUMPTION=OrderedDict()
_CACHE_LOCK=threading.RLock()
import contextlib
import contextvars
# The one exact owner composition currently being published for a research run.
_RESEARCH_PUBLISHING=contextvars.ContextVar('laplace_research_synthesis_publication',default=None)


def _condition(root, ident):
    key=(str(root),ident)
    with _CONDITIONS_LOCK:
        found=_CONDITIONS.get(key)
        if found is None:
            found=threading.Condition();_CONDITIONS[key]=found
        return found


def notify(root, ident):
    # Called after the existing dispatch lock is released; this transient local
    # notification is not durable truth and creates no observer/watch thread.
    condition=_condition(root,ident)
    with condition:condition.notify_all()


def observation_budget(value):
    if value is None:return None
    if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=MAX_NATIVE_TIMER_SECONDS:
        raise ValueError('connected_observation_seconds must be a positive integer within the native timer representation; it does not change the dispatch deadline.')
    return {'schema_version':'laplace.connected-observation/1','available':True,'admitted_seconds':value,
        'transport_timeout_ms':value*1000+RETURN_MARGIN_MS,'return_margin_ms':RETURN_MARGIN_MS,
        'basis':'Explicit original author-turn admission; one connected observation, no automatic paid resume.'}


def plan(task, root):
    relative=str((task.get('evidence') or [''])[0])
    path=(root/relative).resolve()
    if not relative or not path.is_relative_to(root) or not path.is_file():
        raise ValueError('The exact dispatch plan is unavailable.')
    raw=path.read_bytes()
    declared=json.loads(raw)
    if not isinstance(declared,dict) or declared.get('schema_version')!='laplace.dispatch-plan/1':
        raise ValueError('The exact dispatch plan is not its declared owner document.')
    return path,declared,'sha256:'+hashlib.sha256(raw).hexdigest()


def parent_actor(task, records, turn_id):
    original=records['turns'].get(task.get('dispatch_parent_turn_id')) or {}
    actor=records['turns'].get(turn_id) or {}
    session=records['sessions'].get(actor.get('session_id')) or {}
    if not original or actor.get('project')!=task.get('project') or actor.get('dispatch_id') or actor.get('mode')!='work':
        return False
    if actor.get('session_id')!=original.get('session_id') or session.get('role','author')!='author':return False
    if actor.get('id')==original.get('id'):return True
    # A recovered turn is a new explicit author admission in the same session,
    # with an inspected Work target. It is never an automatic restart.
    return actor.get('work_id') in {task.get('id'),task.get('parent_work_id')} - {None,''}


def selected_turn(root, project, turn_id):
    from laplace.writing import records
    return records.selected_journal_fields(project,turn_id,root,fields=[
        'id','project','session_id','dispatch_id','work_id','mode','connected_observation','provider_settings'])


def parent_lookup(task, project, root):
    """Exact receipt/actor rows only; never hydrate the global rich history."""
    from laplace.writing import records
    original=selected_turn(root,project,task['dispatch_parent_turn_id'])
    state={'turns':{original['id']:original},'sessions':{},'read_receipts':{}}
    def lookup(receipt_id):
        if receipt_id in state['read_receipts']:return state
        read=records.selected_journal_fields(project,receipt_id,root,fields=[
            'id','project','turn_id','operation','payload','output_sha256'])
        actor=selected_turn(root,project,read['turn_id'])
        session=records.selected_journal_fields(project,actor['session_id'],root,
            fields=['id','project','role','packet','dispatch_id'])
        state['turns'][actor['id']]=actor;state['sessions'][session['id']]=session
        state['read_receipts'][read['id']]=read
        return state
    return lookup


def _basis(task, turn, project, root):
    from laplace.work import project_work
    tasks=project_work._tasks(project,root)
    work_id=turn.get('work_id') or task.get('parent_work_id')
    work=tasks.get(work_id) if work_id else None
    if work_id and not work:raise ValueError('The original parent Work is unavailable.')
    path,declared,revision=plan(task,root)
    if not declared.get('synthesis_return_path'):
        raise ValueError('Connected observation requires an owner-declared synthesis_return_path; no third child is implied.')
    return {'work_id':work_id,'work_scope_revision':project_work._work_basis(tasks,work_id)[0]['scope_revision'] if work else None,
        'other_dependencies':[row for row in project_work._dependency_basis(work,tasks) if row['work_id']!=task['id']] if work else [],
        'dispatch_scope_revision':project_work._work_basis(tasks,task['id'])[0]['scope_revision'],
        'plan_path':path.relative_to(root).as_posix(),'plan_revision':revision,
        'packet_count':len(declared['packets']),
        'prepared_storyboard':work.get('prepared_storyboard') if work else None}


def guard(task, basis, project, root):
    from laplace.work import project_work
    tasks=project_work._tasks(project,root)
    work=tasks.get(basis.get('work_id'))
    if basis.get('work_id'):
        if not work or project_work._work_basis(tasks,work['id'])[0]['scope_revision']!=basis['work_scope_revision']:
            raise ValueError('The original parent Work scope or dependency set changed.')
        current=[row for row in project_work._dependency_basis(work,tasks) if row['work_id']!=task['id']]
        if current!=basis['other_dependencies']:
            raise ValueError('An unrelated prerequisite changed; no blanket dependency refresh was adopted.')
        if work.get('status') in {'withdrawn','cancelled'}:
            raise ValueError('The original parent Work was withdrawn or cancelled.')
    if task['id'] not in tasks or project_work._work_basis(tasks,task['id'])[0]['scope_revision']!=basis['dispatch_scope_revision']:
        raise ValueError('The admitted dispatch scope changed.')
    path,_,revision=plan(task,root)
    if path.relative_to(root).as_posix()!=basis['plan_path'] or revision!=basis['plan_revision']:
        raise ValueError('The admitted dispatch plan changed.')
    if basis.get('prepared_storyboard'):
        from laplace.writing import prepared_work
        if not prepared_work.observe(project,root,basis['prepared_storyboard'])['current']:
            raise ValueError('The admitted prepared source/reader inputs changed.')


def prepare_observation(task, project, root, turn_id, started):
    from laplace.writing import records
    turn=selected_turn(root,project,turn_id)
    policy=turn.get('connected_observation')
    if not policy or policy!=observation_budget(policy.get('admitted_seconds')):
        raise ValueError('No original author connected observation budget was admitted. Use an explicit author Send; no implicit wait or paid resume is authorized.')
    session=records.selected_journal_fields(project,turn['session_id'],root,fields=['id','project','role','dispatch_id'])
    if turn.get('mode')!='work' or turn.get('dispatch_id') or session.get('role','author')!='author' or session.get('dispatch_id'):
        raise ValueError('Only the actual author parent can observe this dispatch.')
    host=child_hosts._child_execution_record(root,turn['session_id'])
    if host.get('turn_id')!=turn_id or host.get('state')!='RUNNING':
        raise ValueError('Connected observation belongs to the exact active parent call.')
    previous=host.get('parent_continuation')
    if previous and previous.get('turn_id')==turn_id:
        raise ValueError('This author turn already used its one connected observation; inspect the retained continuation, do not poll or renew its budget.')
    original=task.get('dispatch_parent_turn_id') or turn_id
    original_turn=selected_turn(root,project,original)
    if original!=turn_id and not parent_actor(task,{'turns':{original:original_turn,turn_id:turn},'sessions':{session['id']:session}},turn_id):
        raise ValueError('Recovery requires an explicitly admitted Work turn in the original parent session.')
    receipt=task.get('dispatch_parent_observation')
    if task.get('dispatch_admitted') and not receipt:
        raise ValueError('This dispatch admission did not retain connected wait intent. Inspect its passive status and synthesize explicitly; no later wait can silently adopt a fresh parent basis.')
    basis=receipt['basis'] if receipt else _basis(task,turn,project,root)
    guard(task,basis,project,root)
    return {'schema_version':'laplace.dispatch-continuation/1','project':project,
        'session_id':turn['session_id'],'turn_id':turn_id,
        'origin_parent_session_id':original_turn['session_id'],'origin_parent_turn_id':original,
        'generation':'DWAIT-'+uuid.uuid4().hex,'dispatch_id':task['id'],'work_id':basis['work_id'],
        'phase':'WAITING','connected_observation':policy,'observation_deadline_at':started+policy['admitted_seconds'],
        'child_custody':'detached-supervised','cancel_scope':'parent-observation',
        '_basis':basis}


def install_observation(root, observation):
    value={key:item for key,item in observation.items() if not key.startswith('_')}
    child_hosts._update_child_execution(root,value['session_id'],{'parent_continuation':value},expected_turn_id=value['turn_id'])


def final_receipt(root, session_id, turn_id, *, interrupted=False, author_stopped=False):
    """Bounded immutable reply witness; no process/control history is copied."""
    host=child_hosts._child_execution_record(root,session_id)
    value=host.get('parent_continuation')
    if not value or host.get('turn_id')!=turn_id or value.get('turn_id')!=turn_id:return None
    value=dict(value)
    if (author_stopped or interrupted) and value.get('phase') not in {'OBSERVATION_EXPIRED','STALE'}:
        value.update(phase='PARENT_STOPPED',reason='Parent observation stopped; detached dispatch child work remains supervised under its original deadline.')
        child_hosts._update_child_execution(root,session_id,{'parent_continuation':value},expected_turn_id=turn_id)
    from laplace.work.project_work_views import handle
    value['dispatch_read']=handle(value['project'],{'view':'detail','id':value['dispatch_id']})
    if value.get('work_id'):value['work_read']=handle(value['project'],{'view':'detail','id':value['work_id']})
    return value


def sync_job(root, job, emit):
    host=child_hosts._child_execution_record(root,job['session_id'])
    value=host.get('parent_continuation')
    if not value or host.get('turn_id')!=job['id']:return None
    key=json.dumps(value,sort_keys=True,separators=(',',':'))
    if job.get('_parent_continuation_cut')!=key:
        projected=public(root,job['project'],value)
        job['_parent_continuation_cut']=key
        job['parent_continuation']=projected
        job['progress']='Waiting for dispatch' if value['phase']=='WAITING' else value.get('reason') or value['phase']
        emit({'type':'dispatch-continuation','parent_continuation':projected})
    if value.get('phase')=='OBSERVATION_EXPIRED':return 'connected observation expired; parent paused for explicit recovery'
    if value.get('phase')=='STALE':return 'connected observation scope changed; parent paused for explicit inspection'
    return None


def recorded(root, project, task):
    from laplace.writing import records
    admission=task.get('dispatch_parent_observation')
    if not admission:return None
    origin=admission['origin_parent_session_id']
    host=child_hosts._child_execution_record(root,origin)
    value=host.get('parent_continuation')
    if value and value.get('dispatch_id')==task['id'] and value.get('turn_id')==host.get('turn_id') \
            and host.get('state') in {'STARTING','WAITING','RUNNING'} \
            and child_hosts._process_matches(host.get('host') or host.get('launcher') or {}):
        return value
    idx=records.index(root)
    turns=[row for row in idx.by_session.get(origin,[]) if row.get('record')=='writing-turn' and idx.project(row)==project]
    for turn in reversed(turns):
        replies=[row for row in idx.by_turn.get(turn['id'],[]) if row.get('record')=='writing-reply' and idx.project(row)==project]
        for reply in reversed(replies):
            value=records.selected_journal_fields(project,reply['id'],root,fields=['parent_continuation']).get('parent_continuation')
            if value and value.get('dispatch_id')==task['id'] and value.get('origin_parent_turn_id')==admission['origin_parent_turn_id']:
                return value
    # Missing original reply is not evidence that its executor settled.
    return {key:value for key,value in admission.items() if key!='basis'}|{
        'phase':'BLOCKED','reason':'The original parent has no exact final continuation reply; prior execution standing is UNKNOWN. Inspect retained Work before an explicit recovery.',
        'origin_execution':'UNKNOWN'}


def _file_identity(path):
    try:
        stat=path.stat();return (stat.st_ino,stat.st_size,stat.st_mtime_ns)
    except OSError:return None


def _cut(task, view, root):
    from laplace.work import project_work
    from laplace.projects import artifacts
    paths=[project_work._ledger(root),root/str((task.get('evidence') or [''])[0])]
    for child in (view or {}).get('children',[]):
        host=child_hosts._host_path(root,child['session_id'])
        paths.extend([host,host.parent/'finished'/host.name])
        if child.get('return_path'):paths.append(artifacts.resolve_path(root,task['project'],child['return_path']))
    return tuple((str(path),_file_identity(path)) for path in paths)


def await_observation(root, project, observation):
    """One connected native call, observing states; no model-driven polling."""
    from laplace.work import project_work
    condition=_condition(root,observation['dispatch_id'])
    cached=None;cut=None;task=None;task_cut=None;plan_cut=None
    while True:
        with project_work.dispatch_lock(root):
            host=child_hosts._child_execution_record(root,observation['session_id'])
            current=host.get('parent_continuation') or {}
            if host.get('turn_id')!=observation['turn_id'] or current.get('generation')!=observation['generation']:
                return {**{key:value for key,value in observation.items() if not key.startswith('_')},
                    'phase':'PARENT_STOPPED','reason':'The original parent call ended or was replaced; no late result was delivered to a new turn.'}
            if host.get('state')!='RUNNING' or current.get('phase')=='PARENT_STOPPED':
                return {**current,'phase':'PARENT_STOPPED','reason':'Parent observation stopped; detached child work retains its original custody/deadline.'}
        # Observed: a nested child host failed 'dispatch-launch.lock could not be acquired' before inference while
        # its parent awaited. The ledger read, guard and whole dispatch_view fold below are owner READS that take
        # seconds per changed cut (any ledger append changes it); running them under the shared project dispatch
        # lock every 0.25 s starved child hosts, whose 30 s acquisitions share that lock. Observe outside it; the
        # lock covers only the host-record check above and the guarded host-record write below.
        observed_task_cut=_file_identity(project_work._ledger(root))
        observed_plan_cut=_file_identity(root/observation['_basis']['plan_path'])
        changed=task is None or observed_task_cut!=task_cut or observed_plan_cut!=plan_cut
        active=[];settled=False;torn=False
        try:
            if changed:
                task=project_work._tasks(project,root).get(observation['dispatch_id']);task_cut=observed_task_cut;plan_cut=observed_plan_cut
                guard(task,observation['_basis'],project,root)
        # Observed: the Work ledger is appended in place, so an unlocked read can end inside a half-written row;
        # it escaped from _tasks or became a false final STALE from guard. Such a read observed nothing.
        except (json.JSONDecodeError,UnicodeDecodeError):torn=True
        except (ValueError,KeyError,TypeError) as error:
            phase,reason='STALE',str(error)
        else:
            observed_cut=_cut(task,cached,root)
            if cached is None or changed or observed_cut!=cut:
                # Observed: a child that settled during the fold was read RUNNING while its settled files were stamped,
                # so no later tick refolded and a finished dispatch expired. Stamp what was seen before the fold (a path
                # it first names is unobserved, forcing one more fold); a re-read task is a changed fold input.
                before=dict(observed_cut);ledger=project_work._ledger(root);ledger_before=_file_identity(ledger)
                # Observed: the fold reads the Work ledger itself; a row read half-written there became a judge return
                # error and a false BLOCKED (project_work.py:782, caught at workflow.py:171) or escaped the fold
                # (required_inputs). Keep a fold only if it raised no torn read and the ledger stood still across it.
                try:fresh=project_work.dispatch_view(task,project,root)
                except (json.JSONDecodeError,UnicodeDecodeError):torn=True
                torn=torn or _file_identity(ledger)!=ledger_before
                if not torn:cached=fresh;cut=tuple((path,before.get(path,'UNOBSERVED')) for path,_ in _cut(task,cached,root))
            if not torn:
                active=[row for row in cached['children'] if row.get('execution',{}).get('state') in {'STARTING','WAITING','RUNNING','ORPHANED','UNKNOWN-OWNERSHIP'}]
                settled=len(cached['children'])==observation['_basis']['packet_count'] and not active
                if time.time()>=observation['observation_deadline_at']:
                    phase,reason='OBSERVATION_EXPIRED','The admitted connected observation ended; child work continues under its original deadline. Explicit parent recovery is required.'
                elif settled:
                    phase,reason='READY','Child execution settled; inspect exact returns and synthesize the separate review standing.'
                elif cached['execution_state'] in {'FAILED','CANCELLED','BLOCKED'}:
                    phase,reason='BLOCKED','Dispatch needs attention; active child custody and missing evidence remain explicit.'
                elif task.get('dispatch_deadline_at') and time.time()>=task['dispatch_deadline_at']:
                    phase,reason='BLOCKED','The original dispatch deadline ended; child cleanup/retained evidence remains inspectable. Observation did not extend that deadline.'
                else:
                    phase,reason='WAITING','Waiting for the exact admitted dispatch state; no model polling or new provider turn.'
                if phase!='WAITING':
                    try:guard(task,observation['_basis'],project,root)
                    except (json.JSONDecodeError,UnicodeDecodeError):torn=True
                    except ValueError as error:phase,reason='STALE',str(error)
        if torn:
            # Re-read the ledger next tick and publish nothing; a ledger that never reads whole ends at the deadline.
            task_cut=None
            if time.time()<observation['observation_deadline_at']:
                with condition:condition.wait(timeout=.25)
                continue
            phase,reason='OBSERVATION_EXPIRED','The admitted connected observation ended; child work continues under its original deadline. Explicit parent recovery is required.'
        with project_work.dispatch_lock(root):
            # Re-read the host record under the lock and publish only to the same still-running parent
            # generation; a stop or replacement seen here is reported, under the lock, at the top of the loop.
            host=child_hosts._child_execution_record(root,observation['session_id'])
            current=host.get('parent_continuation') or {}
            if (host.get('turn_id')!=observation['turn_id'] or current.get('generation')!=observation['generation']
                    or host.get('state')!='RUNNING' or current.get('phase')=='PARENT_STOPPED'):
                continue
            patch={**current,'phase':phase,'reason':reason}
            if cached:
                patch.update(execution_state=cached['execution_state'],review_state=cached['review_state'],
                    execution_settled=settled,children_active=len(active),dispatch_deadline_at=task.get('dispatch_deadline_at'))
            child_hosts._update_child_execution(root,observation['session_id'],{'parent_continuation':patch},expected_turn_id=observation['turn_id'])
        if phase!='WAITING':return patch
        # Local in-process terminal hooks notify; detached hosts are observed by
        # cheap file identities at the existing judge-gate control interval.
        # Never hold the dispatch lock while waiting on a condition.
        with condition:condition.wait(timeout=.25)


def artifact_metadata(root, project, relative):
    from laplace.projects import artifacts
    from laplace.writing import records
    read=artifacts.read(root,project,{'path':relative,'scope':'project','limit':1})
    matches=[row for row in records.index(root).by_project.get(project,[])
        if row.get('record')=='writing-artifact' and row.get('project')==project
        and row.get('path')==read['path'] and row.get('sha256')==read['revision']]
    if not matches:raise ValueError('The exact current artifact has no immutable ART publication receipt.')
    receipt=matches[-1]
    exact=artifacts.read(root,project,{'id':receipt['id'],'limit':1})
    return {'id':receipt['id'],'path':read['path'],'revision':exact['revision'],'read_handle':{'operation':'read_artifact','payload':{'id':receipt['id']}},
        'human_read':exact['human_read'],'turn_id':receipt.get('turn_id')}


def synthesis_view(task, project, root, *, view=None):
    from laplace.projects import artifacts
    _,declared,_=plan(task,root)
    relative=declared.get('synthesis_return_path')
    if not relative:return {'required':False,'status':'NOT_REQUIRED'}
    if _research(declared):return research_synthesis_view(task,project,root,declared)
    path=artifacts.resolve_path(root,project,relative)
    if not path.is_file():return {'required':True,'status':'MISSING','return_path':relative}
    try:
        document=json.loads(path.read_bytes())
        metadata=artifact_metadata(root,project,relative)
        errors=(return_errors(document,task,project,root,view=view,actor_turn_id=metadata['turn_id'])
            if metadata.get('turn_id') and task.get('dispatch_admitted')
            else ['The original admitted parent synthesis publication actor is unavailable.'])
        from laplace.work import project_work
        tasks=project_work._tasks(project,root);parent=tasks.get(task.get('parent_work_id')) or task
        target=path.relative_to(root).as_posix()
        attached=any(row.get('path')==target and str(row.get('sha256')).removeprefix('sha256:')==metadata['revision'].removeprefix('sha256:')
                     for owner in (parent,task) for row in owner.get('evidence_receipts') or [])
        result={'required':True,'status':'INVALID' if errors else 'VALID','return_path':relative,
            'retained_status':document.get('status'),'artifact':metadata,'errors':errors,
            'attachment':'ATTACHED' if attached else 'MISSING'}
        if not errors and not attached:
            target_task=task if document.get('status')=='COMPLETE' else parent
            basis,_=project_work._work_basis(tasks,target_task['id'])
            from laplace.work.project_work_views import handle
            result['attach_action']={'operation':'task_status','project':project,
                'permitted':target_task.get('status') not in {'withdrawn','cancelled'} and (document.get('status')!='COMPLETE' or target_task.get('status')!='blocked'),
                'http':{'method':'POST','url':'/work/transition'},
                'target_work_read':handle(project,{'view':'detail','id':target_task['id']}),'payload':{
                'project':project,
                'id':target_task['id'],'status':'done' if document.get('status')=='COMPLETE' else 'blocked',
                'expected_work_scope_revision':basis['scope_revision'],
                'expected_work_status_revision':project_work._standing_revision(target_task),
                'expected_dependency_revision':project_work._dependency_revision(target_task,tasks),
                'evidence':[target],'summary':document['summary']}}
        return result
    except (ValueError,OSError,KeyError) as error:
        return {'required':True,'status':'INVALID','return_path':relative,'errors':[str(error)]}


def _research(declared):
    """A research-workflow plan publishes through its run owner, not packet-return/2."""
    return isinstance((declared.get('workflow_definition') or {}).get('research_workflow'),dict)


@contextlib.contextmanager
def research_publication(work_id, text):
    """Scope one exact run-owner publication; nothing else may write the reserved path."""
    token=_RESEARCH_PUBLISHING.set({'work_id':work_id,'sha256':hashlib.sha256(text.encode()).hexdigest()})
    try:yield
    finally:_RESEARCH_PUBLISHING.reset(token)


def research_contract(task, project, root, declared):
    from laplace.writing import workflow_progression
    from laplace.pipeline import workflow_operations
    return {'required':True,'profile':workflow_operations.SYNTHESIS_SCHEMA,'return_path':declared['synthesis_return_path'],
        'publish_action':'workflow-synthesis','read_contract':workflow_progression.read_handle(project,task['id']),
        'policy':'Read the run status synthesis section, read every ART-backed input completely in the original parent session, then use its exact workflow-synthesis action with those read receipt IDs. The owner carries attempt outcomes and every finding and refuses wrong, stale, foreign or missing receipts.'}


def research_synthesis_view(task, project, root, declared):
    """Only the run owner's own recorded publication at the reserved path qualifies."""
    from laplace.projects import artifacts
    from laplace.pipeline import workflow_operations
    from laplace.work import project_work
    relative=declared['synthesis_return_path'];base=research_contract(task,project,root,declared)
    path=artifacts.resolve_path(root,project,relative)
    if not path.is_file():return {**base,'status':'MISSING'}
    try:
        document=json.loads(path.read_bytes());metadata=artifact_metadata(root,project,relative)
        runs=[row.get('run') or {} for row in task.get('phases') or () if row.get('kind')=='workflow-run']
        published=((runs[-1] if runs else {}).get('synthesis') or {}).get('artifact') or {}
        errors=[]
        if document.get('schema_version')!=workflow_operations.SYNTHESIS_SCHEMA or document.get('work_id')!=task['id']:
            errors.append('The reserved path does not hold this run typed synthesis.')
        if (published.get('id')!=metadata['id']
                or str(published.get('sha256')).removeprefix('sha256:')!=str(metadata['revision']).removeprefix('sha256:')):
            errors.append('The reserved synthesis was not published by this run owner; a direct artifact write does not qualify.')
        if document.get('status') not in workflow_operations.SYNTHESIS_STATUSES:errors.append('Unknown synthesis status.')
        tasks=project_work._tasks(project,root);parent=tasks.get(task.get('parent_work_id')) or task
        target=path.relative_to(root).as_posix()
        attached=any(row.get('path')==target and str(row.get('sha256')).removeprefix('sha256:')==str(metadata['revision']).removeprefix('sha256:')
                     for owner in (parent,task) for row in owner.get('evidence_receipts') or [])
        result={**base,'status':'INVALID' if errors else 'VALID','retained_status':document.get('status'),
            'artifact':metadata,'errors':errors,'attachment':'ATTACHED' if attached else 'MISSING'}
        if not errors and not attached:
            target_task=task if document.get('status')=='COMPLETE' else parent
            basis,_=project_work._work_basis(tasks,target_task['id'])
            from laplace.work.project_work_views import handle
            result['attach_action']={'operation':'task_status','project':project,
                'permitted':target_task.get('status') not in {'withdrawn','cancelled'} and (document.get('status')!='COMPLETE' or target_task.get('status')!='blocked'),
                'http':{'method':'POST','url':'/work/transition'},
                'target_work_read':handle(project,{'view':'detail','id':target_task['id']}),'payload':{
                'project':project,'id':target_task['id'],'status':'done' if document.get('status')=='COMPLETE' else 'blocked',
                'expected_work_scope_revision':basis['scope_revision'],
                'expected_work_status_revision':project_work._standing_revision(target_task),
                'expected_dependency_revision':project_work._dependency_revision(target_task,tasks),
                'evidence':[target],'summary':(document.get('synthesis') or {}).get('summary','')}}
        return result
    except (ValueError,OSError,KeyError,TypeError) as error:
        return {**base,'status':'INVALID','errors':[str(error)]}


def cancel_action(task, project, root):
    """The ONE guarded 'Cancel dispatched work' action of a dispatch Work (parent continuation and app-run share it): the
    existing task_status transition to cancelled under the Work's current scope/status/dependency guards.

    Distinct from a selected-turn Stop (turn_control: one exact turn generation) and from a research-loop Stop: it records
    the dispatch Work as cancelled, which running children observe at their own control check
    (dispatch_execution._child_control_reason). It terminates no provider by itself and proves no settlement."""
    from laplace.work import project_work
    from laplace.work.project_work_views import _actions, handle
    tasks=project_work._tasks(project,root);basis,_=project_work._work_basis(tasks,task['id'])
    action=_actions({**task,'work_revision':basis['revision'],'work_scope_revision':basis['scope_revision'],
        'dependency_revision':project_work._dependency_revision(task,tasks),
        'work_status_revision':project_work._standing_revision(task)},project,'work')['task_status']
    return {**action,'permitted':action['permitted'] and task.get('status') not in {'done','verified','cancelled','withdrawn'},
        'target_work_read':handle(project,{'view':'detail','id':task['id']}),'payload':{**action['payload'],'project':project,'status':'cancelled'},
        'distinct_from':['selected-turn Stop','research-loop Stop'],
        'cancellation_meaning':('Records this dispatch Work as cancelled; its running children observe that at their own control check. '
            'It terminates no provider by itself and proves no settlement: read each child host and reply for that.')}


def public(root, project, continuation, *, task=None, view=None):
    from laplace.work import project_work
    from laplace.work.project_work_views import handle
    from laplace.projects import artifacts
    if not continuation:return None
    value={key:item for key,item in continuation.items() if not key.startswith('_')}
    host=child_hosts._child_execution_record(root,value['session_id'])
    job=turn_jobs._JOBS.get(value['turn_id'])
    value['parent_active']=host.get('turn_id')==value['turn_id'] and (
        host.get('state') in {'STARTING','WAITING','RUNNING','ORPHANED','UNKNOWN-OWNERSHIP'}
        and child_hosts._process_matches(host.get('host') or host.get('launcher') or {})
        or bool(job and not job.get('done')))
    task=task or project_work._tasks(project,root).get(value['dispatch_id'])
    if not task:return {**value,'phase':'STALE','reason':'The addressed dispatch is unavailable.'}
    try:declared=plan(task,root)[1]
    except (ValueError,OSError) as error:declared={};value.update(reason=str(error))
    view=view if view is not None else project_work.dispatch_view(task,project,root,_include_parent=False)
    children=view.get('children') or []
    outcomes=[]
    for child in children:
        outcome={key:child.get(key) for key in ('packet','role','state','session_id','turn_id','reply_status','return_path','return_exists','terminal_error','failure_count','failure_summary','reply_excerpt','publication_read') if key in child}
        outcome['return_errors']=[str(error)[:500] for error in (child.get('return_errors') or [])[:4]]
        outcomes.append(outcome)
    active=[row for row in children if row.get('execution',{}).get('state') in {'STARTING','WAITING','RUNNING','ORPHANED','UNKNOWN-OWNERSHIP'}]
    returns=[]
    for child in children:
        if child.get('return_exists'):
            try:returns.append({'packet':child['packet'],'role':child['role'],
                'artifact':artifact_metadata(root,project,child['return_path'])})
            except (ValueError,OSError) as error:
                returns.append({'packet':child['packet'],'role':child['role'],
                    'return_path':child['return_path'],'status':'UNAVAILABLE','reason':str(error)[:1000]})
    try:required,missing=required_inputs(task,project,root,view=view)
    except (ValueError,OSError,KeyError) as error:
        required,missing=[],[]
        value.update(phase='STALE' if value.get('phase') not in {'PARENT_STOPPED','OBSERVATION_EXPIRED'} else value['phase'],reason=str(error))
    value.update(execution_state=view.get('execution_state','UNKNOWN'),review_state=view.get('review_state','PENDING'),
        execution_settled=bool(declared) and len(children)==len(declared.get('packets') or []) and not active,children_active=len(active),
        dispatch_deadline_at=task.get('dispatch_deadline_at'),
        dispatch_read=handle(project,{'view':'detail','id':task['id']}),readable_returns=returns,child_outcomes=outcomes,
        synthesis=synthesis_view(task,project,root,view=view) if declared else {'required':True,'status':'INVALID','errors':['Declared plan is unavailable.']},
        parent_return_contract=contract_summary(task,project,root,turn_id=value['turn_id'],view=view) if declared else None,
        recovery={'mode':'explicit-parent-send','session_id':value['origin_parent_session_id'],
            'origin_parent_turn_id':value['origin_parent_turn_id'],'automatic':False,
            'reason':'Use the existing inspected Work run_action to compose a new author turn in the same parent session; nothing is replayed or charged automatically.'})
    value['dispatch_cancel_action']=cancel_action(task,project,root)
    if value.get('work_id'):value['work_read']=handle(project,{'view':'detail','id':value['work_id']})
    return value


def parent_return_contract(task, project, root, *, turn_id, view=None):
    """Existing /2 profile with owner-filled mechanical fields and exact actions."""
    from laplace.work import project_work
    from laplace.projects import artifacts
    from laplace.writing import dispatch_returns
    from urllib.parse import urlencode
    path,declared,_=plan(task,root);relative=declared.get('synthesis_return_path')
    if not relative:return {'required':False,'policy':'Legacy dispatch: no reserved synthesis profile was admitted.'}
    if _research(declared):return research_contract(task,project,root,declared)
    view=view if view is not None else project_work.dispatch_view(task,project,root,_include_parent=False)
    required,missing=required_inputs(task,project,root,view=view)
    base=artifacts.project_root(root,project)
    reads=[{**pin,'read':{'operation':'read_artifact','payload':{
        'path':(root/pin['path']).relative_to(base).as_posix(),'scope':'project','limit':40000}}} for pin in required]
    check=dispatch_returns.owner_check(root,project,turn_id,paths={root/pin['path'] for pin in required})
    remaining=[{'work':'Recover declared packet '+packet,
        'reason':'No typed return is available from this exact declared packet.',
        'next_action':'Inspect its exact saved child turn and retained effects; use explicit recovery without relaunching completed children.'} for packet in missing]
    if not remaining:remaining=[{'work':'Author and qualify the parent synthesis',
        'reason':'The parent has not yet authored its conclusion from the retained worker and review evidence.',
        'next_action':'Read every required input, author the conclusion and choose the supported standing using this exact profile.'}]
    outputs=[]
    for child in view.get('children',[]):
        if not child.get('return_exists') or child.get('role')!='worker':continue
        try:
            document=json.loads(artifacts.resolve_path(root,project,child['return_path']).read_bytes())
            output=document.get('output')
            if isinstance(output,dict) and isinstance(output.get('path'),str):
                physical=project_work._dispatch_pin_path(root,project,output['path'],artifact_only=True)
                current=artifacts.read(root,project,{'path':physical.relative_to(base).as_posix(),'limit':1})
                if str(output.get('sha256')).removeprefix('sha256:')==current.get('revision'):
                    outputs.append({'pin':output,'read':{'operation':'read_artifact','payload':{
                        'path':physical.relative_to(base).as_posix(),'scope':'project'}},
                        'meaning':'Exact retained worker report; choose it only if it is the report your authored synthesis actually establishes.'})
        except (OSError,ValueError,KeyError,TypeError):continue
    scaffold={'schema_version':'laplace.packet-return/2','packet':PARENT_PACKET,'role':'synthesis','status':'BLOCKED',
        'goal':declared.get('goal') or task['goal'],'inputs':required,
        'source':{'kind':'artifacts','root':str(base),'artifacts':required},
        'output':outputs[0]['pin'] if len(outputs)==1 else None,
        'files_written':[artifacts.resolve_path(root,project,relative).relative_to(root).as_posix()],
        'summary':'','most_important':[''],'scripted_check':check,'residuals':[],
        'remaining_work':remaining,'continuation':{'artifacts':required,
            'next_action':'Inspect the exact retained evidence and explicitly recover the unresolved Work.',
            'resume_condition':'Original parent Work/plan/dependency guards remain current and required evidence has been consumed.'}}
    publish=dispatch_returns.publication(root,project,relative,document=scaffold)
    try:
        from laplace.writing import records
        actor=selected_turn(root,project,turn_id);original=selected_turn(root,project,task['dispatch_parent_turn_id'])
        session=records.selected_journal_fields(project,actor['session_id'],root,fields=['id','role'])
        publish['permitted']=parent_actor(task,{'turns':{actor['id']:actor,original['id']:original},
            'sessions':{session['id']:session}},turn_id)
    except (ValueError,KeyError,OSError):publish['permitted']=False
    return {**dispatch_returns.profile(root,'laplace.packet-return/'),
        'schema_version':'laplace.packet-return/2','packet':PARENT_PACKET,'role':'synthesis','return_path':relative,
        'required_inputs':required,'required_reads':reads,'missing_packets':missing,'retained_outputs':outputs,
        'authored_synthesis':({k:copy.deepcopy(v) for k,v in (declared.get('workflow_definition') or {}).get('synthesis',{}).items() if k!='instructions'} or None),
        'scaffold':scaffold,**dispatch_returns.publication_projection(publish),
        'schema_read':{'operation':'dispatch_status','payload':{'id':task['id']}},
        'publication_read':{'http':{'method':'GET','url':'/authoring/help?'+urlencode({
            'project':project,'turn_id':turn_id,'operation':'dispatch_status','context':json.dumps({'id':task['id']},separators=(',',':'))})}},
        'authored_fields':['summary','most_important','remaining_work reasons/next actions and supported conclusion'],
        'policy':'Use required_reads, retaining complete byte coverage, then refresh dispatch_status once for an exact actual read-check scaffold. Fill authored_fields before publication; preserve owner pins/path/guard. A successful owner READ stays PASSED even when its evidence says FAILED, REJECTED or BLOCKED. BLOCKED/INCOMPLETE/INTERRUPTED require remaining_work and continuation object, with residuals:[]; fixable gaps are not demonstrated impossibility. COMPLETE requires accepted current child evidence, a current exact report output, remaining_work:[], continuation:null and residuals:[]. Never invent hashes or null a blocked continuation. Pass publish_action itself to the native tool; publication_context is qualification metadata, not tool arguments or authority. Then use the exact task_status attachment.'}


def contract_summary(task, project, root, *, turn_id, view=None):
    from urllib.parse import urlencode
    _,declared,_=plan(task,root)
    if not declared.get('synthesis_return_path'):return {'required':False}
    if _research(declared):return research_contract(task,project,root,declared)
    required,missing=required_inputs(task,project,root,view=view)
    payload={'id':task['id'],'view':'return-contract'}
    return {'required':True,'schema_id':'laplace.packet-return/2','return_path':declared['synthesis_return_path'],
        'required_input_count':len(required),'missing_packets':missing,
        'read_contract':{'operation':'dispatch_status','payload':payload},
        'schema_read':{'operation':'dispatch_status','payload':{'id':task['id'],'view':'return-schema'}},
        'publication_read':{'http':{'method':'GET','url':'/authoring/help?'+urlencode({
            'project':project,'turn_id':turn_id,'operation':'dispatch_status','context':json.dumps(payload,separators=(',',':'))})}}}


def native_status(task, project, root, *, turn_id, selected='status'):
    """Small explicit views over one dispatch; no inaccessible native spill file."""
    from laplace.work import project_work
    from laplace.writing import dispatch_returns
    if selected=='return-schema':
        return {'dispatch_id':task['id'],'caller_turn_id':turn_id,**dispatch_returns.profile(root,'laplace.packet-return/')}
    view=project_work.dispatch_view(task,project,root,_include_parent=False)
    if selected=='return-contract':
        contract=parent_return_contract(task,project,root,turn_id=turn_id,view=view)
        # The serialized publish content is the one editable scaffold. Its schema
        # has an explicit view; never copy either body into another response field.
        return {'dispatch_id':task['id'],'caller_turn_id':turn_id,'parent_return_contract':{
            **{key:value for key,value in contract.items() if key not in {'schema','scaffold','required_inputs','retained_outputs','publication_read','schema_read'}},
            'schema_read':{'operation':'dispatch_status','payload':{'id':task['id'],'view':'return-schema'}}},
            'schema_read':{'operation':'dispatch_status','payload':{'id':task['id'],'view':'return-schema'}},
            'after_publication_read':{'operation':'dispatch_status','payload':{'id':task['id']}}}
    if selected=='detail':
        return {'dispatch_id':task['id'],'caller_turn_id':turn_id,**view,
            'parent_return_contract':contract_summary(task,project,root,turn_id=turn_id,view=view)}
    children=[]
    for child in view['children']:
        row={key:child.get(key) for key in ('packet','role','state','session_id','turn_id','reply_status','return_exists','return_path','failure_count')}
        if child.get('terminal_error'):row['terminal_error']=str(child['terminal_error'])[:300]
        if child.get('failure_summary'):row['failure_summary']=child['failure_summary'][:300]
        if child.get('return_errors'):row['return_errors']=[str(child['return_errors'][0])[:300]]
        children.append(row)
    result={key:view.get(key) for key in ('status','execution_state','review_state','accepted_workers','rejected_workers','uncovered_workers','cost','deadline_seconds','deadline_exceeded')}
    result.update(dispatch_id=task['id'],caller_turn_id=turn_id,children=children,
        parent_return_contract=contract_summary(task,project,root,turn_id=turn_id,view=view),
        detail_read={'operation':'dispatch_status','payload':{'id':task['id'],'view':'detail'}})
    synthesis=synthesis_view(task,project,root,view=view)
    if synthesis.get('errors'):synthesis={**synthesis,'errors':[str(error)[:400] for error in synthesis['errors'][:4]]}
    result['synthesis']=synthesis
    continuation=recorded(root,project,task)
    if continuation:result['parent_continuation']={key:continuation.get(key) for key in (
        'phase','reason','origin_parent_turn_id','turn_id','dispatch_id','work_id','child_custody','cancel_scope')}
    return result


def required_inputs(task, project, root, *, view=None):
    from laplace.work import project_work
    from laplace.projects import artifacts
    path,declared,revision=plan(task,root)
    if not declared.get('synthesis_return_path'):return [],[]
    if _research(declared):return [],[]  # research synthesis inputs belong to its run owner
    if task.get('dispatch_plan_sha256') and revision.removeprefix('sha256:')!=task['dispatch_plan_sha256']:
        raise ValueError('The admitted dispatch plan changed; no current plan was silently adopted.')
    inputs=[{'path':path.relative_to(root).as_posix(),'sha256':revision}]
    missing=[]
    tasks=project_work._tasks(project,root)
    parent=tasks.get(task.get('parent_work_id')) or {}
    binding=parent.get('prepared_storyboard') or {}
    if binding:
        prepared=artifacts.read(root,project,{'id':binding['artifact_id']})
        if prepared['revision']!=binding['revision']:raise ValueError('The admitted prepared input artifact changed.')
        inputs.append({'path':prepared['path'],'sha256':prepared['revision']})
    view=view if view is not None else project_work.dispatch_view(task,project,root)
    children={child['packet']:child for child in (view or {}).get('children',[])}
    for item in declared['packets']:
        child=children.get(item['packet']) or {'packet':item['packet']}
        if child.get('return_exists') and child.get('return_token'):
            returned=artifacts.resolve_path(root,project,child['return_path'])
            inputs.append({'path':returned.relative_to(root).as_posix(),
                'sha256':'sha256:'+str(child['return_token']).removeprefix('sha256:')})
        else:missing.append(child['packet'])
    return inputs,missing


def return_errors(document, task, project, root, *, view=None, records_lookup=None, actor_turn_id=None):
    from laplace.work import project_work
    from laplace.core.identity import revision_matches
    _,declared,_=plan(task,root)
    if not declared.get('synthesis_return_path'):return []
    if _research(declared):return ['Research workflow synthesis is published only through its run owner action workflow-synthesis.']
    if not isinstance(document,dict) or document.get('schema_version')!='laplace.packet-return/2':
        return ['parent synthesis must use the existing laplace.packet-return/2 profile']
    if actor_turn_id is not None:
        from laplace.writing import records
        actor=selected_turn(root,project,actor_turn_id)
        original=selected_turn(root,project,task['dispatch_parent_turn_id'])
        session=records.selected_journal_fields(project,actor['session_id'],root,fields=['id','role'])
        if not parent_actor(task,{'turns':{actor['id']:actor,original['id']:original},
                'sessions':{session['id']:session}},actor_turn_id):
            return ['Only the original or explicitly recovered parent Work session can publish this synthesis.']
    view=view if view is not None else project_work.dispatch_view(task,project,root)
    item={'packet':PARENT_PACKET,'role':'parent','parent_task':task}
    errors=project_work._dispatch_return_errors(document,item,{},root=root,project=project,
        dispatch_id=task['id'],_records_lookup=records_lookup or parent_lookup(task,project,root))
    required,missing=required_inputs(task,project,root,view=view)
    offered={}
    for pin in document.get('inputs') or []:
        if not isinstance(pin,dict):continue
        try:physical=project_work._dispatch_pin_path(root,project,pin.get('path'),repository=pin.get('repository'))
        except ValueError:continue
        offered[physical]=pin.get('sha256')
    for pin in required:
        physical=project_work._dispatch_pin_path(root,project,pin['path'],repository=pin.get('repository'))
        if not revision_matches(offered.get(physical),pin['sha256']):
            errors.append('parent synthesis omits or changes required admitted input: '+pin['path'])
    errors.extend(consumption_errors(task,project,root,required,actor_turn_id=actor_turn_id))
    if document.get('status')=='COMPLETE' and ((view or {}).get('execution_state')!='COMPLETE' or (view or {}).get('review_state')!='ACCEPTED'):
        errors.append('parent COMPLETE cannot override unsettled, failed, rejected or unverified dispatch evidence')
    if missing:
        remainder=json.dumps(document.get('remaining_work') or [],ensure_ascii=False)
        for packet in missing:
            if packet not in remainder:errors.append('missing packet return must be explicit remaining work: '+packet)
    return errors


def consumption_errors(task, project, root, required, *, actor_turn_id=None):
    """Prove complete exact owner reads of every derived input, including rejections.

    The existing read receipts hold the consulted result digest. Reconstruct only
    their selected payloads and bounded artifact slices; never hydrate replies.
    """
    from laplace.projects import artifacts
    from laplace.writing import dispatch_returns, reads, records
    idx=records.index(root);original=selected_turn(root,project,task['dispatch_parent_turn_id'])
    original_session=original['session_id'];coverage={}
    eligible=[]
    for row in idx.by_session.get(original_session,[]):
        if row.get('record')!='writing-turn' or idx.project(row)!=project:continue
        if actor_turn_id is not None and row['id']!=actor_turn_id:continue
        actor=selected_turn(root,project,row['id'])
        session=records.selected_journal_fields(project,original_session,root,fields=['id','role'])
        if parent_actor(task,{'turns':{original['id']:original,actor['id']:actor},
                'sessions':{original_session:session}},actor['id']):eligible.append(actor['id'])
    required_paths={str(root/pin['path']) for pin in required}
    def relevant(row):
        if row.get('operation')=='dispatch_returns':return row.get('dispatch_id') in {None,task['id']}
        if row.get('artifact_path'):
            try:return str(artifacts.resolve_path(root,project,row['artifact_path'],row.get('artifact_scope','project'),allow_read_only=True)) in required_paths
            except ValueError:return False
        return True  # Older receipts resolve their exact selected payload below.
    receipts=[row for turn_id in eligible for row in idx.by_turn.get(turn_id,[])
        if row.get('record')=='writing-tool-read' and row.get('operation') in {'read_artifact','dispatch_returns'}]
    receipts=[row for row in receipts if relevant(row)]
    # Cached read coverage does not establish that the required current bytes
    # still match. Recheck bounded-memory hashes before reusing any success.
    # These are owner-derived inputs, never authority for an escaping path.
    for pin in required:
        path=(root/pin['path']).resolve()
        if not path.is_relative_to(Path(root).resolve()) or not path.is_file():
            return ['parent synthesis required input is unavailable inside this workspace: '+pin['path']]
        observed=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(65536),b''):observed.update(chunk)
        if observed.hexdigest()!=pin['sha256'].removeprefix('sha256:'):
            return ['parent synthesis required current input changed: '+pin['path']]
    cut=(str(root),project,task['id'],actor_turn_id,tuple((pin['path'],pin['sha256']) for pin in required),
        tuple((row['id'],row['_hash']) for row in receipts))
    with _CACHE_LOCK:
        if cut in _CONSUMPTION:
            _CONSUMPTION.move_to_end(cut);return list(_CONSUMPTION[cut])
    def covered():
        for pin in required:
            end=0
            for start,stop in sorted(coverage.get((pin['path'],pin['sha256'].removeprefix('sha256:')),[])):
                if start>end:break
                end=max(end,stop)
            if end<(root/pin['path']).stat().st_size or not coverage.get((pin['path'],pin['sha256'].removeprefix('sha256:'))):return False
        return True
    for row in reversed(receipts):
            read=records.selected_journal_fields(project,row['id'],root,
                fields=['operation','payload','output_sha256'])
            payload=read['payload'];op=read['operation']
            try:
                chunks=[]
                if op=='read_artifact':
                    physical=artifacts.target(root,project,payload,allow_read_only=True)[0]
                    if str(physical) not in required_paths:continue
                    result=artifacts.read(root,project,payload);chunks=[result]
                elif payload.get('id')==task['id']:
                    declared=plan(task,root)[1]
                    result=dispatch_returns.dispatch_returns_projection(root,project,task['id'],declared,payload)
                    chunks=[item['return'] for item in result['returns']]
                else:continue
                if reads.read_output_digest(op,result)!=read['output_sha256']:continue
                for chunk in chunks:
                    if not chunk.get('exists'):continue
                    key=(chunk['path'],chunk['revision'])
                    end=chunk['next_offset'] if chunk['next_offset'] is not None else chunk['size_bytes']
                    coverage.setdefault(key,[]).append((chunk['offset'],end))
                if covered():break
            except (ValueError,KeyError,OSError):continue
    errors=[]
    for pin in required:
        path=root/pin['path'];end=0
        for start,stop in sorted(coverage.get((pin['path'],pin['sha256'].removeprefix('sha256:')),[])):
            if start>end:break
            end=max(end,stop)
        if end<path.stat().st_size or (path.stat().st_size==0 and not coverage.get((pin['path'],pin['sha256'].removeprefix('sha256:')))):
            errors.append('parent synthesis requires consumed exact owner-read receipts for: '+pin['path'])
    with _CACHE_LOCK:
        _CONSUMPTION[cut]=tuple(errors);_CONSUMPTION.move_to_end(cut)
        while len(_CONSUMPTION)>64:_CONSUMPTION.popitem(last=False)
    return errors


def reservation(task, root, project):
    from laplace.projects import artifacts
    path,declared,revision=plan(task,root)
    relative=declared.get('synthesis_return_path')
    if not relative:return None
    return {'path':artifacts.resolve_path(root,project,relative).relative_to(root).as_posix(),
        'plan_path':path.relative_to(root).as_posix(),'plan_revision':revision}


def publication_task(root, project, path):
    from laplace.work import project_work
    key=(str(root),project);cut=_file_identity(project_work._ledger(root))
    # Disposable reverse lookup over existing Work metadata. Reservations were
    # derived from the exact validated plan at creation/admission, never guessed
    # by rescanning plan bodies or silently transferred after out-of-band drift.
    with _CACHE_LOCK:
        cached=_RESERVATIONS.get(key)
        if cached is None or cached[0]!=cut:
            mapping={}
            for task in project_work._tasks(project,root).values():
                retained=task.get('dispatch_synthesis_reservation')
                if task.get('task_kind')=='dispatch' and retained:
                    target=(root/retained['path']).resolve()
                    if target in mapping:raise ValueError('Multiple Work admissions claim the same reserved synthesis path; inspect the exact dispatches.')
                    mapping[target]=task
            cached=(cut,mapping);_RESERVATIONS[key]=cached
        _RESERVATIONS.move_to_end(key)
        while len(_RESERVATIONS)>16:_RESERVATIONS.popitem(last=False)
        return cached[1].get(path)


def validate_publication(root, project, path, content, turn_id):
    from laplace.writing.dispatch_returns import validate_child_publication,validate_continuation_publication
    validate_continuation_publication(root,project,path,content,turn_id)
    # An admitted child's reserved typed return is validated before the write: wrong output, actor or document refuse here.
    validate_child_publication(root,project,path,content,turn_id)
    task=publication_task(root,project,path)
    if task is None:return
    if reservation(task,root,project)!=task.get('dispatch_synthesis_reservation'):
        raise ValueError('The original declared plan or synthesis reservation changed; its reserved path cannot be transferred by drift.')
    declared=plan(task,root)[1]
    if _research(declared):
        # A research run is never dispatch-admitted; its reserved path accepts only
        # the exact document its run owner is composing, from the original session.
        held=_RESEARCH_PUBLISHING.get();prepared=(declared.get('workflow_definition') or {}).get('prepared_by') or {}
        actor=selected_turn(root,project,turn_id) if turn_id else {}
        if (not held or held['work_id']!=task['id'] or held['sha256']!=hashlib.sha256(content.encode()).hexdigest()
                or actor.get('project')!=project or actor.get('session_id')!=prepared.get('session_id')):
            raise ValueError('A research workflow synthesis is published only by its run owner action workflow-synthesis in the original parent session.')
        return
    if not task.get('dispatch_admitted'):raise ValueError('The declared parent synthesis is reserved until its dispatch is admitted.')
    if not turn_id:raise ValueError('The declared parent synthesis requires its actual original or recovered author turn.')
    admission=task.get('dispatch_parent_observation')
    if admission:guard(task,admission['basis'],project,root)
    errors=return_errors(json.loads(content),task,project,root,actor_turn_id=turn_id)
    if errors:raise ValueError('Parent synthesis refused: '+'; '.join(errors))


def transition_evidence(task, tasks, status, evidence, project, root):
    """Existing Work transitions mechanically consume the reserved synthesis.

    Publication and attachment are separate recoverable acts. The immutable ART
    remains readable if this transition conflicts, and the same exact task_status
    attachment can be composed again after inspection without republishing.
    """
    if status not in {'done','blocked'}:return evidence,False
    dispatches=([task] if task.get('task_kind')=='dispatch' else [row for row in tasks.values()
        if row.get('task_kind')=='dispatch' and row.get('parent_work_id')==task['id']
        and row.get('status') not in {'withdrawn','cancelled'}])
    added=[]
    for dispatch in dispatches:
        relative=plan(dispatch,root)[1].get('synthesis_return_path')
        if not relative:continue
        from laplace.projects import artifacts
        target=artifacts.resolve_path(root,project,relative).relative_to(root).as_posix()
        view=synthesis_view(dispatch,project,root)
        if view['status']!='VALID':
            if status=='done' or target in evidence:
                raise ValueError('Work requires its exact valid parent synthesis: '+
                    '; '.join(view.get('errors') or [view['status']])+'; inspect dispatch '+dispatch['id'])
            continue
        if status=='done' and view['retained_status']!='COMPLETE':
            raise ValueError('Blocked, rejected or incomplete parent synthesis cannot qualify Work completion.')
        admission=dispatch.get('dispatch_parent_observation')
        if admission:guard(dispatch,admission['basis'],project,root)
        added.append(target)
    return list(dict.fromkeys(evidence+added)),bool(added)

from laplace.writing import child_hosts, turn_jobs  # noqa: E402  (the owners it names; cycle-safe: imported last)
