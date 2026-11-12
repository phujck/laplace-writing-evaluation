"""Actual asynchronous owner flow; only the provider boundary is a deterministic stub."""
from work_read_helpers import guarded_transition, standing_payload
import json
import threading
import time

import pytest

from laplace.work import project_work
from laplace.native import tools as writing_tools
from laplace.projects import artifacts as writing_artifacts
from laplace.writing import dispatch_execution
from laplace.writing import records as writing_records
from laplace.writing import child_hosts
from laplace.writing import turn_control
from laplace.writing import session_reads
from laplace.writing import turn_jobs
from laplace.writing import provider as writing_provider
from test_writing_dispatch import tree, _StubTurn, _settle
from test_writing_dispatch_lifecycle import _planned, _status, _wait
from test_packet_return_lifecycle import pin, judgement, partial

# Live publication outcomes observed by the fixture worker: the Artifact prewrite guard's actual refusals.
REFUSALS = []


def setup(root, monkeypatch, *, interleaved=False, mutation=None):
    REFUSALS.clear()
    packets=[{'packet':'worker-a','role':'worker'}, {'packet':'judge-a','role':'judge'}]
    if interleaved:packets += [{'packet':'worker-b','role':'worker'}, {'packet':'judge-b','role':'judge'}]
    for item in packets:
        item.update(scope='project',return_path='dispatch/'+item['packet']+'.json',brief='Read exact declared input and bank the typed return at your own declared path.')
    plan={'schema_version':'laplace.dispatch-plan/1','wave':'readiness','goal':'Read the declared input and retain independently reviewed result',
          'fan_out_max':len(packets),'packets':packets}
    source=writing_artifacts.resolve_path(root,'book','dispatch/input.md');source.parent.mkdir(parents=True,exist_ok=True);source.write_text('declared input bytes')
    release={row['packet']:threading.Event() for row in packets if row['role']=='worker'}
    published={key:threading.Event() for key in release};constructed=[];observed=[]

    class Controlled(_StubTurn):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw)
            self.packet=session_reads._records(root)['sessions'][self.session_id]['packet']
            constructed.append(self.packet)

        def call(self,operation,payload):
            return writing_tools.execute(root,'book',self.mode,operation,payload,turn_id=self.turn_id)

        def run(self,prompt):
            self.inference_started=True
            own=next(item for item in packets if item['packet']==self.packet)
            if own['role']=='worker':
                self.call('read_artifact',{'path':'dispatch/input.md'})
                output=self.call('store_artifact',{'path':'dispatch/'+self.packet+'.md','scope':'project','before':None,'reason':'fixture result','content':'declared result bytes'})
                path=writing_artifacts.resolve_path(root,'book','dispatch/'+self.packet+'.md')
                doc={'schema_version':'laplace.packet-return/2','packet':self.packet,'role':'build','status':'COMPLETE',
                     'goal':plan['goal'],'inputs':[pin(source)],'source':{'kind':'artifacts','root':str(source.parent),'artifacts':[pin(source)]},
                     'output':pin(path),'files_written':[str(path)],'summary':'Retained exact fixture result',
                     'most_important':['The declared output is available for independent inspection'],
                     'scripted_check':{'kind':'command','state':'PASSED','command':'fixture exact bytes','exit_code':0,'output_tail':'Exact fixture bytes retained'},
                     'residuals':[],'remaining_work':[],'continuation':None}
                if mutation in {'INCOMPLETE','BLOCKED','INTERRUPTED'}:doc=partial(doc,mutation)
                if mutation=='no-output':doc=partial(doc,'BLOCKED');doc['output']=None
                publish=lambda document:self.call('store_artifact',{'path':own['return_path'],'scope':'project','before':None,'reason':'fixture result','content':json.dumps(document)})
                if mutation in {'invalid','corrected'}:
                    # A wrong reserved typed return is refused by the Artifact owner before any write.
                    try:publish({**doc,'packet':'wrong-worker'})
                    except Exception as error:REFUSALS.append({'packet':self.packet,'error':str(error),
                        'exists':writing_artifacts.resolve_path(root,'book',own['return_path']).exists()})
                    else:REFUSALS.append({'packet':self.packet,'error':None})
                    if mutation=='corrected':publish(doc)   # the same live worker corrects through its exact contract
                elif mutation!='missing':publish(doc)
                published[self.packet].set()
                if not release[self.packet].wait(15):raise AssertionError('fixture worker not released')
                return {'status':'failed' if mutation=='provider-failed' else 'completed','text':'Fixture worker settled'}
            target=self.packet.replace('judge-','worker-')
            returned=next(item for item in packets if item['packet']==target)
            read=self.call('read_artifact',{'path':returned['return_path']})
            doc=json.loads(read['content'])
            result=self.call('read_artifact',{'path':'dispatch/'+target+'.md'})
            record=judgement(doc,writing_artifacts.resolve_path(root,'book',returned['return_path']))
            record['packet']=target;record['judged']['review_context']['session_id']=self.session_id
            receipt=result['read_receipt']
            check={'kind':'owner-read','state':'PASSED','operation':receipt['operation'],'payload':receipt['payload'],
                   'receipt_id':receipt['id'],'output_sha256':receipt['output_sha256'],'ok':True,'output_tail':'Actual independent result read'}
            record['scripted_check']=check;record['own_observations']=[{key:value for key,value in check.items() if key!='state'}]
            if doc['status']!='COMPLETE' or mutation=='reject':
                record['accepted']=False;record['accepted_subsets']=[]
                record['deficiencies']=[{'id':'remaining','item':target,'problem':'Declared worker remains incomplete','evidence':'Read the exact retained non-COMPLETE worker return','done_looks_like':'Complete the retained remaining work and obtain independent acceptance'}]
            observed.append({'packet':self.packet,'dependencies':session_reads.child_execution(root,self.session_id)['dependencies'],
                             'dependency_state':session_reads.child_execution(root,self.session_id)['dependency_state']})
            self.call('store_artifact',{'path':own['return_path'],'scope':'project','before':None,'reason':'fixture result','content':json.dumps(record)})
            return {'status':'completed','text':'Fixture independent judgement settled'}

    monkeypatch.setattr(writing_provider, 'WritingTurn',Controlled)
    parent,ident=_planned(root,plan)
    started=dispatch_execution.launch_dispatch(root,'book',parent,{'id':ident})
    return ident,started,release,published,constructed,observed


def test_pending_return_waits_without_provider_then_interleaved_exact_coverage_completes(tree,monkeypatch):
    ident,started,release,published,constructed,observed=setup(tree,monkeypatch,interleaved=True)
    try:
        assert all(event.wait(5) for event in published.values())
        _wait(lambda:all(session_reads.child_execution(tree,row['session_id'])['state']=='WAITING' for row in started['children'] if row['role']=='judge'))
        assert set(constructed)=={'worker-a','worker-b'}
        assert _status(tree,ident)['dependencies']=={'worker-a':[],'judge-a':['worker-a'],'worker-b':[],'judge-b':['worker-a','worker-b']}
        release['worker-a'].set()
        _wait(lambda:'judge-a' in constructed)
        assert 'judge-b' not in constructed
        release['worker-b'].set();_settle(tree,started['children'])
        status=_status(tree,ident)
        assert status['execution_state']=='COMPLETE' and status['review_state']=='ACCEPTED',status
        assert status['accepted_workers']==['worker-a','worker-b'] and not status['uncovered_workers']
        judge=started['children'][-1]
        writing_records.bank(tree,{'record':'writing-turn','id':'WT-later','session_id':judge['session_id'],'project':'book','mode':'review','text':'A later independent conversation turn'})
        writing_records.bank(tree,{'record':'writing-reply','id':'WR-later','turn_id':'WT-later','session_id':judge['session_id'],'project':'book','status':'failed','text':'Later fixture failure','usage':{'input':999}})
        unchanged=_status(tree,ident)
        assert unchanged['execution_state']=='COMPLETE' and unchanged['review_state']=='ACCEPTED'
        assert unchanged['cost']==status['cost']  # later turn cannot replace exact child completion/cost
        for later_state in ('RUNNING','FAILED','BLOCKED'):
            child_hosts._update_child_execution(tree,judge['session_id'],{'turn_id':'WT-later','state':later_state,
                'host':child_hosts._process_identity(),'dependency_state':'BLOCKED','provider_processes':[]})
            retained=_status(tree,ident)
            assert retained['execution_state']=='COMPLETE' and retained['review_state']=='ACCEPTED',retained
            exact=next(row for row in retained['children'] if row['turn_id']==judge['turn_id'])
            assert exact['execution']['observation']=='saved-exact-turn-reply'
            assert 'host' not in exact['execution'] and 'active_provider_processes' not in exact['execution']
            with pytest.raises(ValueError,match='another turn'):
                turn_control.interrupt_turn(tree,{'project':'book','turn_id':judge['turn_id']})
        child_hosts._update_child_execution(tree,judge['session_id'],{'turn_id':'WT-later','state':'RUNNING','dependency_state':None})
        assert turn_control.interrupt_turn(tree,{'project':'book','turn_id':'WT-later'})['turn_ids']==['WT-later']
        assert child_hosts._read_host(child_hosts._host_path(tree,judge['session_id']).with_suffix('.cancel.json'))['turn_id']=='WT-later'
        child_hosts._finish_child_execution(tree,judge['session_id'],'WT-later','failed')
        evidence=[str(writing_artifacts.resolve_path(tree,'book',row['return_path']).relative_to(tree)) for row in started['children']]
        guarded_transition('book',{'id':ident,'status':'done','evidence':evidence},tree)
        assert project_work._tasks('book',tree)[ident]['status']=='done'
        task=project_work._tasks('book',tree)[ident]
        assert task['evidence'][0]==status['plan_artifact']  # plan home cannot be replaced by first caller return
        writing_artifacts.resolve_path(tree,'book','dispatch/input.md').write_text('changed consumed input')
        resolved=next(row for row in project_work._resolved_tasks(project_work._tasks('book',tree),tree) if row['id']==ident)
        assert resolved['recorded_status']=='done' and resolved['status']=='blocked'
        assert resolved['currentness']['status']=='STALE'
    finally:
        for event in release.values():event.set()


@pytest.mark.parametrize('mutation',['invalid','corrected','missing','changed-input','provider-failed','no-output','INCOMPLETE','BLOCKED','INTERRUPTED','reject'])
def test_settled_failure_blocks_or_is_explicit_readable_failure_review(tree,monkeypatch,mutation):
    ident,started,release,published,constructed,observed=setup(tree,monkeypatch,mutation=mutation)
    assert published['worker-a'].wait(5)
    if mutation in {'invalid','corrected'}:
        # the live wrong return was refused before publication: a named refusal, no file, no Artifact receipt
        assert len(REFUSALS)==1 and REFUSALS[0]['error'] and 'refused before publication' in REFUSALS[0]['error'],REFUSALS
        assert 'dispatch/worker-a.json' in REFUSALS[0]['error'] and REFUSALS[0]['exists'] is False
    if mutation=='changed-input':writing_artifacts.resolve_path(tree,'book','dispatch/input.md').write_text('changed consumed input bytes')
    release['worker-a'].set();_settle(tree,started['children'])
    status=_status(tree,ident)
    if mutation=='corrected':
        # the same worker's corrected publication is the one the independent judge reads and accepts
        assert status['execution_state']=='COMPLETE' and status['review_state']=='ACCEPTED',status
        assert status['accepted_workers']==['worker-a'] and not status['uncovered_workers']
        return
    if mutation in {'invalid','missing','changed-input','provider-failed','no-output'}:
        assert constructed==['worker-a'] and status['children'][-1]['state']=='BLOCKED',status
        assert status['execution_state']=='BLOCKED'
    else:
        assert observed[0]['dependency_state']==('READY' if mutation=='reject' else 'FAILURE-REVIEW')
        assert status['review_state']=='REJECTED',status
        if mutation=='reject':assert status['execution_state']=='COMPLETE'
        assert not status['accepted_workers']
    with pytest.raises(ValueError):guarded_transition('book',{'id':ident,'status':'done'},tree)


def test_stop_waiting_child_has_no_provider_and_remains_active_until_terminal(tree,monkeypatch):
    ident,started,release,published,constructed,_=setup(tree,monkeypatch)
    try:
        assert published['worker-a'].wait(5)
        judge=started['children'][-1]
        _wait(lambda:session_reads.child_execution(tree,judge['session_id'])['state']=='WAITING')
        assert any(row['turn_id']==judge['turn_id'] for row in child_hosts.active_child_hosts(tree))
        turn_control.interrupt_turn(tree,{'project':'book','turn_id':judge['turn_id']})
        _wait(lambda:turn_jobs._JOBS[judge['turn_id']]['done'])
        assert constructed==['worker-a']
        assert session_reads._records(tree)['turns'][judge['turn_id']]['reply']['status']=='interrupted'
        release['worker-a'].set();_settle(tree,started['children'])
    finally:
        for event in release.values():event.set()


def test_judge_contract_names_own_identity_separately_and_actual_prior_worker_reads(tree,monkeypatch):
    ident,started,release,published,_,_=setup(tree,monkeypatch,interleaved=True)
    try:
        for child in started['children']:
            contract=dispatch_execution._child_return_contract(tree,'book',child['session_id'],ident)
            assert contract['own_packet']==child['packet']
            if child['role']=='judge':
                assert 'packet' not in contract
                for target in contract['judged_workers']:
                    assert target['read']['payload']['path']==target['return_path']
                    assert target['packet'].startswith('worker-')
        for event in release.values():event.set()
        _settle(tree,started['children'])
    finally:
        for event in release.values():event.set()


def test_waiting_owner_fold_is_reused_without_provider_polling(tree,monkeypatch):
    ident,started,release,published,constructed,_=setup(tree,monkeypatch)
    try:
        assert published['worker-a'].wait(5)
        judge=started['children'][-1]
        _wait(lambda:session_reads.child_execution(tree,judge['session_id'])['state']=='WAITING')
        calls=[];original=project_work.dispatch_dependency_state
        def read(*a,**k):calls.append(1);return original(*a,**k)
        monkeypatch.setattr(project_work,'dispatch_dependency_state',read)
        time.sleep(.9)
        assert len(calls)<=2 and constructed==['worker-a']
        release['worker-a'].set();_settle(tree,started['children'])
    finally:
        for event in release.values():event.set()


def test_launcher_crash_ends_wait_before_provider_construction(tree,monkeypatch):
    ident,started,release,published,constructed,_=setup(tree,monkeypatch)
    try:
        assert published['worker-a'].wait(5)
        judge=started['children'][-1]
        _wait(lambda:session_reads.child_execution(tree,judge['session_id'])['state']=='WAITING')
        guarded_transition('book',{'id':ident,'status':'in-progress'},tree,dispatch_receipt={
            'dispatch_launch_state':'STARTING','dispatch_launcher':{'pid':99999999,'created_at':1}})
        _wait(lambda:turn_jobs._JOBS[judge['turn_id']]['done'])
        assert constructed==['worker-a']
        reply=session_reads._records(tree)['turns'][judge['turn_id']]['reply']
        assert reply['status']=='interrupted' and reply['error']=='launcher exited before dispatch start completed'
        assert session_reads.child_execution(tree,judge['session_id'])['dependency_wait_ended']==reply['error']
        release['worker-a'].set();_settle(tree,started['children'])
    finally:
        for event in release.values():event.set()
