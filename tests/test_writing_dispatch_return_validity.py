"""Current project-scoped standing for canonical versioned packet returns."""
from __future__ import annotations
from laplace.writing import records as record_owner
from laplace.representation import writing_bodies as bodies
from work_read_helpers import guarded_transition, standing_payload
import hashlib,json
from pathlib import Path
import pytest
from laplace.work import project_work
from laplace.native import tools as writing_tools
from laplace.projects import artifacts as writing_artifacts
from laplace.writing import reads
from laplace.writing import dispatch_execution
from laplace.writing import session_reads
from laplace.writing.records import _fold as records_fold
from laplace.core import bodies as core_bodies
from test_writing_dispatch import tree as base_tree,_return_document,_settle
from test_writing_dispatch_lifecycle import _planned


@pytest.fixture
def tree(base_tree,monkeypatch):
    # These are read-owner validation fixtures: documents/receipts are injected AFTER
    # turn settlement. Real scheduling is exercised separately, without this override.
    monkeypatch.setattr(dispatch_execution,'_await_dispatch_dependencies',lambda *a,**k:None)
    return base_tree


def _pin(path):return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def _case(root,version=1):
    parent,ident=_planned(root)
    launched=dispatch_execution.launch_dispatch(root,'book',parent,{'id':ident});_settle(root,launched['children'])
    source=writing_artifacts.resolve_path(root,'book','dispatch/input.md');source.write_text('actual declared input')
    output=writing_artifacts.resolve_path(root,'book','dispatch/report.md');output.write_text('actual declared report')
    doc=json.loads(_return_document('worker-a','bounded work',str(source),_pin(source)['sha256'],str(output)))
    if version==2:
        doc.update(schema_version='laplace.packet-return/2',
            source={'kind':'artifacts','root':str(writing_artifacts.project_root(root,'book')),'artifacts':[_pin(source),_pin(output)]},
            output=_pin(output),remaining_work=[],continuation=None)
        doc['scripted_check'].update(kind='command',state='PASSED')
    returned=writing_artifacts.resolve_path(root,'book','dispatch/worker-a.return.json')
    return parent,ident,launched,source,output,returned,doc


def _child(root,ident):
    view=project_work.dispatch_view(project_work._tasks('book',root)[ident],'book',root)
    return next(row for row in view['children'] if row['packet']=='worker-a')


@pytest.mark.parametrize('version',[1,2])
@pytest.mark.parametrize('mutation',['synthesis','changed-input','missing-output'])
def test_complete_rejects_actual_role_input_and_report_defects(tree,version,mutation):
    _,ident,_,source,output,returned,doc=_case(tree,version)
    if mutation=='synthesis':doc['role']='synthesis'
    elif mutation=='changed-input':source.write_text('changed author source')
    else:output.unlink()
    returned.write_text(json.dumps(doc))
    row=_child(tree,ident)
    assert row['state']!='COMPLETE' and row['return_errors']
    expected={'synthesis':'role','changed-input':'input','missing-output':'output'}[mutation]
    assert any(expected in error for error in row['return_errors']),row


@pytest.mark.parametrize('version',[1,2])
def test_genuine_project_artifact_completion_stands_then_output_drift_is_observed(tree,version):
    _,ident,_,source,output,returned,doc=_case(tree,version)
    returned.write_text(json.dumps(doc))
    row=_child(tree,ident)
    assert row['state']=='COMPLETE' and not row['return_errors'],row
    if version==2:
        token=hashlib.sha256(returned.read_bytes()).hexdigest();output.write_text('changed report bytes')
        row=_child(tree,ident)
        assert row['state']!='COMPLETE' and row['return_errors']
        assert hashlib.sha256(returned.read_bytes()).hexdigest()==token
        with pytest.raises(ValueError,match='successful typed return'):
            guarded_transition('book',{'id':ident,'status':'done','evidence':[str(returned.relative_to(tree))]},tree)


@pytest.mark.parametrize('status',['INCOMPLETE','BLOCKED','INTERRUPTED'])
def test_resumable_v2_return_preserves_remaining_work_without_completion_or_replay(tree,status):
    _,ident,launched,source,output,returned,doc=_case(tree,2)
    doc.update(status=status,output=None,
       source={'kind':'artifacts','root':str(source.parent),'artifacts':[_pin(source)]},
       remaining_work=[{'work':'finish report','reason':'explicit pause','next_action':'resume exact retained input'}],
       continuation={'artifacts':[_pin(source)],'next_action':'continue from the retained input','resume_condition':'author resumes this packet'})
    doc['scripted_check'].update(state='NOT_RUN',exit_code=None)
    returned.write_text(json.dumps(doc))
    row=_child(tree,ident)
    assert row['state']==status and row['self_status']==status and not row['return_errors'],row
    assert row['remaining_work']==doc['remaining_work'] and row['continuation']==doc['continuation']
    before=set(session_reads._records(tree)['turns'])
    dispatch_execution.launch_dispatch(tree,'book','WT-parent',{'id':ident})
    assert set(session_reads._records(tree)['turns'])==before
    with pytest.raises(ValueError,match='successful typed return'):
        guarded_transition('book',{'id':ident,'status':'done','evidence':[str(returned.relative_to(tree))]},tree)


def test_existing_read_receipt_stays_exact_when_same_payload_is_read_again(tree):
    parent,_,_,source,_,_,_=_case(tree,1)
    payload={'path':'dispatch/input.md','scope':'project'}
    first=writing_tools.execute(tree,'book','work','read_artifact',payload,turn_id=parent)
    second=writing_tools.execute(tree,'book','work','read_artifact',payload,turn_id=parent)
    receipt=first['read_receipt'];assert receipt['id']!=second['read_receipt']['id']
    obs={'kind':'owner-read','operation':receipt['operation'],'payload':receipt['payload'],
         'receipt_id':receipt['id'],'output_sha256':receipt['output_sha256'],'ok':True,'output_tail':'actual project read'}
    assert not dispatch_execution.return_read_receipt_errors(tree,obs,project='book',turn_id=parent)
    assert reads.read_output_digest('read_artifact',first)==reads.read_output_digest('read_artifact',second)
    wrong={**obs,'output_sha256':'0'*64}
    assert dispatch_execution.return_read_receipt_errors(tree,wrong,project='book',turn_id=parent)


def test_v2_owner_read_check_binds_actual_worker_and_rejects_borrowed_receipt(tree):
    parent,ident,launched,source,output,returned,doc=_case(tree,2)
    worker=next(row for row in launched['children'] if row['packet']=='worker-a')
    own=writing_tools.execute(tree,'book','work','read_artifact',{'path':'dispatch/input.md'},turn_id=worker['turn_id'])['read_receipt']
    check={'kind':'owner-read','state':'PASSED','operation':own['operation'],'payload':own['payload'],
           'receipt_id':own['id'],'output_sha256':own['output_sha256'],'ok':True,'output_tail':'read the retained input'}
    doc['scripted_check']=check;returned.write_text(json.dumps(doc))
    assert _child(tree,ident)['state']=='COMPLETE'
    foreign=writing_tools.execute(tree,'book','work','read_artifact',{'path':'dispatch/input.md'},turn_id=parent)['read_receipt']
    doc['scripted_check'].update(receipt_id=foreign['id'],output_sha256=foreign['output_sha256'])
    returned.write_text(json.dumps(doc))
    child=_child(tree,ident)
    assert child['state']!='COMPLETE' and any('actual dispatch' in row for row in child['return_errors'])


def test_current_child_return_contract_is_generated_from_registered_schema_and_session(tree):
    parent,ident,launched,source,output,returned,doc=_case(tree,2)
    records=session_reads._records(tree)
    for child in launched['children']:
        contract=dispatch_execution._child_return_contract(tree,'book',child['session_id'],ident)
        assert contract['schema_id']==('laplace.packet-judgement/2' if child['role']=='judge' else 'laplace.packet-return/2')
        assert contract['schema']['$id']==contract['schema_id'] and contract['return_path']==child['return_path']
        if child['role']=='judge':assert contract['independent_session']=={'session_id':child['session_id'],'read_only':True}
        assert '"$schema"' not in records['turns'][child['turn_id']]['text']


def test_accepted_v2_judge_binds_actual_independent_read_and_fails_on_output_drift(tree,monkeypatch):
    from test_packet_return_lifecycle import judgement
    parent,ident,launched,source,output,returned,doc=_case(tree,2)
    returned.write_text(json.dumps(doc))
    judge=next(row for row in launched['children'] if row['role']=='judge')
    first=writing_tools.execute(tree,'book','review','read_artifact',{'path':'dispatch/report.md'},turn_id=judge['turn_id'])['read_receipt']
    writing_tools.execute(tree,'book','review','read_artifact',{'path':'dispatch/report.md'},turn_id=judge['turn_id'])
    judged=judgement(doc,returned);judged['packet']='worker-a'
    judged['judged']['review_context']['session_id']=judge['session_id']
    check={'kind':'owner-read','state':'PASSED','operation':first['operation'],'payload':first['payload'],
           'receipt_id':first['id'],'output_sha256':first['output_sha256'],'ok':True,'output_tail':'actual independent report read'}
    judged['scripted_check']=check;judged['own_observations']=[{key:value for key,value in check.items() if key!='state'}]
    judge_return=writing_artifacts.resolve_path(tree,'book',judge['return_path']);judge_return.write_text(json.dumps(judged))
    from laplace.manuscript import manuscript_source
    resolved=[];source_owner=manuscript_source.resolve
    monkeypatch.setattr(manuscript_source,'resolve',lambda *a,**k:(resolved.append(a[0]),source_owner(*a,**k))[1])
    def current():
        resolved.clear()
        state=project_work.dispatch_view(project_work._tasks('book',tree)[ident],'book',tree)
        assert resolved==['book']  # Includes recursive judged-worker pin checks.
        return next(row for row in state['children'] if row['role']=='judge')
    assert current()['state']=='COMPLETE' and not current()['return_errors'],current()
    output.write_text('different current report')
    assert current()['state']!='COMPLETE' and current()['return_errors']


def test_declared_command_check_cannot_be_replaced_by_owner_read(tree):
    parent,ident,launched,source,output,returned,doc=_case(tree,2)
    worker=next(row for row in launched['children'] if row['packet']=='worker-a')
    read=writing_tools.execute(tree,'book','work','read_artifact',{'path':'dispatch/input.md'},turn_id=worker['turn_id'])['read_receipt']
    doc['scripted_check']={'kind':'owner-read','state':'PASSED','operation':read['operation'],'payload':read['payload'],
        'receipt_id':read['id'],'output_sha256':read['output_sha256'],'ok':True,'output_tail':'actual input read'}
    plan=json.loads(writing_artifacts.resolve_path(tree,'book','dispatch/plan.json').read_text())
    packets={item['packet']:item for item in plan['packets']}
    item={**packets['worker-a'],'check':'python declared-check.py'}
    errors=project_work._dispatch_return_errors(doc,item,packets,root=tree,project='book',
        session_id=worker['session_id'],dispatch_id=ident)
    assert any('command' in error for error in errors),errors


def test_dispatch_read_uses_one_cut_and_no_unrelated_rich_bodies(tree,monkeypatch):
    from laplace.work import author_history_metrics as metadata
    _,ident,launched,_,_,returned,doc=_case(tree,2)
    worker=next(row for row in launched['children'] if row['packet']=='worker-a')
    read=writing_tools.execute(tree,'book','work','read_artifact',{'path':'dispatch/input.md'},turn_id=worker['turn_id'])['read_receipt']
    doc['scripted_check']={'kind':'owner-read','state':'PASSED','operation':read['operation'],
        'payload':read['payload'],'receipt_id':read['id'],'output_sha256':read['output_sha256'],
        'ok':True,'output_tail':'actual retained input read'}
    returned.write_text(json.dumps(doc))
    # Increase unrelated history without adding any consumed rows or CAS reads.
    path=tree/'contract/talk.jsonl'
    observed=[];opened=[];charged=[]
    cut_owner=record_owner._index._dispatch_metadata_cut;raw_owner=record_owner._index._raw_indexed_record
    def cut(*args):observed.append(args);return cut_owner(*args)
    def raw(idx,row):
        opened.append((row['id'],row['record']))
        charged.append(row['_end']-row['_offset'])
        return raw_owner(idx,row)
    monkeypatch.setattr(record_owner._index,'_dispatch_metadata_cut',cut)
    monkeypatch.setattr(record_owner._index,'_raw_indexed_record',raw)
    monkeypatch.setattr(session_reads,'_records',lambda *a:pytest.fail('dispatch read entered global rich history'))
    custody_owner=bodies.read_bytes
    def custody(value,root):
        assert value.get('content_handle')!='missing-body', 'unrelated custody body opened'
        return custody_owner(value,root)
    monkeypatch.setattr(bodies,'read_bytes',custody)
    task=project_work._tasks('book',tree)[ident];costs=[]
    for growth in (0,100,900):
        with path.open('a') as stream:
            for n in range(growth):
                stream.write(json.dumps({'id':f'OTHER-{growth}-{n}','record':'writing-reply','project':'elsewhere',
                    'turn_id':'not-selected','text':{'schema_version':core_bodies.REFERENCE_SCHEMA,
                    'store':'contract/writing_bodies','content_handle':'missing-body','bytes':1000000}})+'\n')
        observed.clear();opened.clear();charged.clear();context={
            ('dispatch-work-scope',str(tree.resolve()),'book'):frozenset({ident,'another-dispatch'})}
        first=project_work.dispatch_view(task,'book',tree,read_context=context)
        second=project_work.dispatch_view({**task,'id':'another-dispatch'},'book',tree,read_context=context)
        assert next(row for row in first['children'] if row['packet']=='worker-a')['state']=='COMPLETE'
        assert second['children']==[] and len(observed)==1
        assert len([item for item in opened if item[0]==read['id']])==1
        assert all(not row_id.startswith('OTHER-') for row_id,_ in opened)
        assert {kind for _,kind in opened}=={'writing-session','writing-binding','writing-turn','writing-reply','writing-tool-read'}
        costs.append((len(opened),sum(charged)))
    assert len(set(costs))==1  # Selected exact row IO is independent of unrelated growth.


@pytest.mark.parametrize('contents',[None,'not json','[]'])
def test_invalid_dispatch_plan_does_not_observe_history(tree,monkeypatch,contents):
    _,ident=_planned(tree)
    task=project_work._tasks('book',tree)[ident]
    path=tree/task['evidence'][0]
    if contents is None:path.unlink()
    else:path.write_text(contents)
    monkeypatch.setattr(records_fold,'_dispatch_records',lambda *a,**k:pytest.fail('invalid plan opened history'))
    monkeypatch.setattr(session_reads,'_records',lambda *a:pytest.fail('invalid plan opened rich history'))
    assert not project_work.dispatch_view(task,'book',tree)['children']


def test_dispatch_cut_does_not_adopt_later_session_turn_or_read(tree):
    from laplace.work import author_history_metrics as metadata
    _,ident,launched,_,_,_,_=_case(tree,2)
    worker=next(row for row in launched['children'] if row['packet']=='worker-a')
    state,lookup=records_fold._dispatch_records(tree,'book',ident)
    # Advance/reset of the shared index cannot replace this request's maps.
    old=metadata.index(tree);old.by_id.clear();old.by_session.clear();old.by_turn.clear();old.turns.clear()
    assert worker['turn_id'] in state['turns']
    with (tree/'contract/talk.jsonl').open('a') as stream:
        stream.write(json.dumps({'id':'LATER-READ','record':'writing-tool-read','project':'book',
            'turn_id':worker['turn_id'],'operation':'read_artifact','payload':{},'output_sha256':'0'*64})+'\n')
    assert 'LATER-READ' not in lookup('LATER-READ')['read_receipts']


def test_selected_immutable_receipt_corruption_refuses_after_cut(tree):
    _,ident,launched,_,_,_,_=_case(tree,2)
    worker=next(row for row in launched['children'] if row['packet']=='worker-a')
    read=writing_tools.execute(tree,'book','work','read_artifact',{'path':'dispatch/input.md'},turn_id=worker['turn_id'])['read_receipt']
    _,lookup=records_fold._dispatch_records(tree,'book',ident)
    path=tree/'contract/talk.jsonl';lines=path.read_bytes().splitlines(keepends=True)
    for n,line in enumerate(lines):
        raw=json.loads(line)
        if raw.get('id')==read['id']:
            value=raw['output_sha256'].encode();replacement=b'0'*len(value)
            lines[n]=line.replace(value,replacement,1);break
    else:pytest.fail('fixture immutable receipt missing')
    path.write_bytes(b''.join(lines))
    with pytest.raises(ValueError,match='selected journal row changed'):lookup(read['id'])


def test_metadata_suffix_read_detects_replaced_larger_same_inode_journal(tmp_path):
    from laplace.work import author_history_metrics as metadata
    path=tmp_path/'contract/talk.jsonl';path.parent.mkdir()
    old={'id':'OLD','record':'writing-turn','project':'book','dispatch_id':'OLD-DISPATCH'}
    path.write_text(json.dumps(old)+'\n')
    first=metadata.index(tmp_path);inode=path.stat().st_ino
    new={'id':'NEW','record':'writing-turn','project':'book','dispatch_id':'NEW-DISPATCH','mode':'work'}
    # A rewrite in place retains the inode and grows past the previous offset.
    path.write_text(json.dumps(new)+'\n')
    assert path.stat().st_ino==inode and path.stat().st_size>first.offset
    current=metadata.index(tmp_path)
    assert set(current.turns)=={'NEW'}
    assert current.stats['scans']==2
    with path.open('a') as stream:stream.write(json.dumps({**new,'id':'APPENDED'})+'\n')
    appended=metadata.index(tmp_path)
    assert set(appended.turns)=={'NEW','APPENDED'} and appended.stats['scans']==2


@pytest.mark.parametrize('field',['session-role','turn-mode','turn-dispatch'])
def test_selected_middle_metadata_mutation_refuses_before_role_or_lifecycle(tree,field):
    from laplace.work import author_history_metrics as metadata
    _,ident,launched,_,_,_,_=_case(tree,2)
    worker=next(row for row in launched['children'] if row['packet']=='worker-a')
    path=tree/'contract/talk.jsonl'
    padding=json.dumps({'id':'PAD','record':'writing-tool-action','project':'elsewhere','padding':'x'*10000}).encode()+b'\n'
    path.write_bytes(padding+path.read_bytes()+padding.replace(b'"PAD"',b'"END"'))
    context={};records_fold._dispatch_records(tree,'book',ident,read_context=context)
    cut=context[('dispatch-metadata-cut',str(tree.resolve()),'book')]
    target=worker['session_id'] if field=='session-role' else worker['turn_id']
    row=next(row for row in cut.by_id[target] if row['record']==('writing-session' if field=='session-role' else 'writing-turn'))
    key={'session-role':'role','turn-mode':'mode','turn-dispatch':'dispatch_id'}[field]
    raw=path.read_bytes();assert row['_offset']>4096 and row['_end']<len(raw)-4096
    line=raw[row['_offset']:row['_end']];value=json.loads(line)[key]
    changed=line.replace(json.dumps(value).encode(),json.dumps('x'*len(value)).encode(),1)
    assert len(changed)==len(line) and changed!=line
    path.write_bytes(raw[:row['_offset']]+changed+raw[row['_end']:])
    with pytest.raises(ValueError,match='selected journal row changed'):
        records_fold._dispatch_records(tree,'book',ident,read_context=context)


def test_oversized_boundary_row_append_keeps_bounded_anchor_io(tmp_path):
    from laplace.work import author_history_metrics as metadata
    path=tmp_path/'contract/talk.jsonl';path.parent.mkdir()
    big={'id':'BIG','record':'writing-tool-action','project':'other','text':'x'*100000}
    path.write_text(json.dumps(big)+'\n')
    idx=metadata.index(tmp_path);initial=idx.stats['bytes_read']
    added=json.dumps({'id':'NEW','record':'writing-turn','project':'book'})+'\n'
    with path.open('a') as stream:stream.write(added)
    idx=metadata.index(tmp_path)
    assert idx.stats['scans']==1 and idx.stats['suffix_reads']==1
    assert idx.stats['index_anchor_bytes']<=8192 and idx.stats['index_anchor_reads']<=2
    assert idx.stats['bytes_read']-initial==len(added.encode())
    assert set(idx.turns)=={'NEW'}


def test_failed_middle_row_cut_recovers_once_without_invalidating_new_generation(tmp_path):
    from laplace.work import author_history_metrics as metadata
    path=tmp_path/'contract/talk.jsonl';path.parent.mkdir()
    pad=lambda ident:json.dumps({'id':ident,'record':'writing-tool-action','project':'elsewhere','text':'x'*10000})+'\n'
    middle=json.dumps({'id':'WT','record':'writing-turn','project':'book','mode':'author','dispatch_id':'D'})+'\n'
    path.write_text(pad('HEAD')+middle+pad('TAIL'))
    old=record_owner._index._dispatch_metadata_cut(tmp_path,'book',{'D'});meta=old.by_id['WT'][0]
    path.write_text(path.read_text().replace('"author"','"review"'))
    appended=json.dumps({'id':'NEW','record':'writing-turn','project':'book'})+'\n'
    with path.open('a') as stream:stream.write(appended)
    advanced=metadata.index(tmp_path)
    assert advanced.stats['scans']==1  # Middle edit lies outside replacement windows.
    with pytest.raises(ValueError,match='selected journal row changed'):record_owner._index._raw_indexed_record(old,meta)
    fresh=record_owner._index._dispatch_metadata_cut(tmp_path,'book',{'D'})
    assert fresh.turns['WT']['mode']=='review' and fresh.stats['scans']==2
    assert record_owner._index._raw_indexed_record(fresh,fresh.by_id['WT'][0])['mode']=='review'
    # Retrying the refused old cut cannot retire the newer rebuilt generation.
    with pytest.raises(ValueError,match='selected journal row changed'):record_owner._index._raw_indexed_record(old,meta)
    before=metadata.index(tmp_path).stats['scans']
    with path.open('a') as stream:stream.write(appended.replace('"NEW"','"NEXT"'))
    latest=metadata.index(tmp_path)
    assert latest.stats['scans']==before==2 and latest.turns['NEXT']['id']=='NEXT'


def test_selected_dispatch_scope_and_source_context_are_shared_but_closed(tree,monkeypatch):
    from laplace.work import author_history_metrics as metadata
    from laplace.manuscript import manuscript_source
    from test_writing_dispatch import _plan
    parent,first,_,_,_,_,_=_case(tree,2)
    plan=_plan(tree)
    for packet in plan['packets']:packet['return_path']=packet['return_path'].replace('dispatch/','second/')
    planned=writing_tools.execute(tree,'book','work','dispatch_plan',{
        'title':'Second bounded work','goal':'Second bounded work','path':'second/plan.json','plan':plan},turn_id=parent)
    second=planned['dispatch_id'];launched=dispatch_execution.launch_dispatch(tree,'book',parent,{'id':second})
    _settle(tree,launched['children'])
    counts=[];source=manuscript_source.resolve;cut=record_owner._index._dispatch_metadata_cut
    monkeypatch.setattr(manuscript_source,'resolve',lambda *a,**k:(counts.append(a[0]),source(*a,**k))[1])
    selected=[]
    def observe(*args,**kwargs):
        value=cut(*args,**kwargs);selected.append(value);return value
    monkeypatch.setattr(record_owner._index,'_dispatch_metadata_cut',observe)
    shared={}
    result=project_work.read('book',{'view':'summary'},tree,read_context=shared)
    dispatches={row['id'] for row in result['tasks'] if row.get('task_kind')=='dispatch'}
    assert {first,second}<=dispatches
    # The lightweight summary stays cheap: one source observation and no rich dispatch cut.
    assert counts==['book'] and selected==[]
    assert shared[('dispatch-work-scope',str(tree.resolve()),'book')]=={first,second}
    # The two explicit rich reads of the same request share one exact cut and the same source observation.
    views=[project_work.dispatch_view(project_work._tasks('book',tree)[ident],'book',tree,read_context=shared)
           for ident in (first,second)]
    assert all(len(view['children'])==3 for view in views)
    assert counts==['book'] and len(selected)==1 and selected[0].dispatch_ids=={first,second}
    assert len(selected[0].turns)==6 and len(selected[0].sessions)==6
    owners=[row.get('dispatch_id') for row in selected[0].turns.values()]
    assert owners.count(first)==3 and owners.count(second)==3
    context={('dispatch-work-scope',str(tree.resolve()),'book'):frozenset({first})}
    records_fold._dispatch_records(tree,'book',first,read_context=context)
    with pytest.raises(ValueError,match='outside this captured Work request'):
        records_fold._dispatch_records(tree,'book',second,read_context=context)


def test_unrelated_same_project_history_never_enlarges_selected_cut(tree):
    from laplace.work import author_history_metrics as metadata
    _,ident,_,_,_,_,_=_case(tree,2)
    before=record_owner._index._dispatch_metadata_cut(tree,'book',{ident})
    path=tree/'contract/talk.jsonl'
    with path.open('a') as stream:
        for row in [{'id':'UNRELATED-S','record':'writing-session','project':'book'},
                    {'id':'UNRELATED-T','record':'writing-turn','project':'book','session_id':'UNRELATED-S'}]:
            stream.write(json.dumps(row)+'\n')
        for n in range(1000):
            stream.write(json.dumps({'id':f'UNRELATED-{n}','record':'writing-reply','project':'book',
                'turn_id':'UNRELATED-T','text':'Unrequested source history.'})+'\n')
    after=record_owner._index._dispatch_metadata_cut(tree,'book',{ident})
    assert [(row['id'],row['_hash']) for row in after.rows]==[(row['id'],row['_hash']) for row in before.rows]
    assert len(after.turns)==len(before.turns)==3 and len(after.sessions)==len(before.sessions)==3


def test_selected_receipt_identity_collision_outside_selected_actor_still_refuses(tree):
    _,ident,launched,_,_,returned,doc=_case(tree,2)
    worker=next(row for row in launched['children'] if row['packet']=='worker-a')
    read=writing_tools.execute(tree,'book','work','read_artifact',{'path':'dispatch/input.md'},turn_id=worker['turn_id'])['read_receipt']
    doc['scripted_check']={'kind':'owner-read','state':'PASSED','operation':read['operation'],'payload':read['payload'],
        'receipt_id':read['id'],'output_sha256':read['output_sha256'],'ok':True,'output_tail':'Exact selected read.'}
    returned.write_text(json.dumps(doc))
    with (tree/'contract/talk.jsonl').open('a') as stream:
        for row in [{'id':'OUTSIDE-S','record':'writing-session','project':'book'},
                    {'id':'OUTSIDE-T','record':'writing-turn','session_id':'OUTSIDE-S'},
                    {'id':read['id'],'record':'writing-tool-read','turn_id':'OUTSIDE-T',
                     'operation':read['operation'],'payload':read['payload'],'output_sha256':read['output_sha256']}]:
            stream.write(json.dumps(row)+'\n')
    current=_child(tree,ident)
    assert current['state']!='COMPLETE' and any('ambiguous' in error for error in current['return_errors'])


def test_request_artifact_context_keeps_fences_and_new_request_observes_selection(tree):
    from laplace.pipeline import registry
    _,_,_,_,_,_,_=_case(tree,2)
    context={};observed=project_work._work_artifact_context(tree,'book',context)
    root=tree/observed['source']['root'];alternate=root.with_name('alternate.tex')
    alternate.write_text(root.read_text())
    registry.set_document('book',{'root':alternate.relative_to(tree).as_posix(),
        'manuscript_dir':observed['source']['manuscript_dir'],'edition':'second'},repo_root=tree)
    assert project_work._work_artifact_context(tree,'book',context) is observed
    fresh=project_work._work_artifact_context(tree,'book',{})
    assert fresh['source']['root']==alternate.relative_to(tree).as_posix()
    assert fresh['source']['edition']=='second' and fresh['source']!=observed['source']
    from laplace.manuscript import document_style
    from laplace.pipeline import authoring
    wrong={**fresh['source'],'project':'another-project'}
    for operation in (lambda:document_style.load('book',tree,_observed_source=wrong),
                      lambda:authoring.summary('book',tree,_source=wrong)):
        with pytest.raises(ValueError,match='another project'):operation()
    with pytest.raises(ValueError,match='inside the selected project'):
        writing_artifacts.resolve_path(tree,'book','../escape.json',context=fresh)
    with pytest.raises(ValueError,match='canonical-record operation'):
        writing_artifacts.resolve_path(tree,'book','authoring.json',context=fresh)
    outside=tree/'outside-file';outside.write_text('outside')
    link=fresh['base']/'linked.json';link.parent.mkdir(parents=True,exist_ok=True);link.symlink_to(outside)
    if not outside.is_relative_to(fresh['base']):
        with pytest.raises(ValueError,match='escapes the selected project'):
            writing_artifacts.resolve_path(tree,'book','linked.json',context=fresh)


def test_later_ordinary_turn_in_the_worker_session_cannot_replace_its_reserved_return(tree):
    """F3: a real later author turn of the settled worker session, exact current CAS and valid typed bytes, is refused."""
    from test_writing_dispatch import _StubTurn
    from laplace.writing import turn_admission,dispatch_returns
    _,ident,launched,_,_,returned,doc=_case(tree,2)
    returned.write_text(json.dumps(doc));before=returned.read_bytes()
    assert _child(tree,ident)['state']=='COMPLETE'
    worker=next(row for row in launched['children'] if row['packet']=='worker-a')
    current=writing_artifacts.read(tree,'book',{'path':worker['return_path'],'scope':'project','limit':1})['revision']
    rows=lambda:sum(1 for row in record_owner.index(tree).by_project.get('book',[]) if row.get('record')=='writing-artifact')
    banked=rows()
    _StubTurn.instructions[worker['session_id']]=[('store_artifact',{'path':worker['return_path'],'scope':'project',
        'expected_revision':current,'reason':'Replace the retained return.','content':json.dumps(doc)})]
    later=turn_admission.start_turn(tree,{'project':'book','session_id':worker['session_id'],'mode':'work',
        'text':'Continue in this conversation.'})
    _settle(tree,[later])
    observed=next(row for row in _StubTurn.observed if row['turn_id']==later['turn_id'])
    assert [failure['operation'] for failure in observed['tool_failures']]==['store_artifact'],observed
    assert 'Field: actor' in observed['tool_failures'][0]['error']
    assert returned.read_bytes()==before and rows()==banked
    assert _child(tree,ident)['state']=='COMPLETE'
    # the settled original child turn is refused as well; an ordinary unreserved artifact is untouched by this guard
    target=writing_artifacts.resolve_path(tree,'book',worker['return_path'])
    with pytest.raises(ValueError,match='Field: actor'):
        dispatch_returns.validate_child_publication(tree,'book',target,json.dumps(doc),worker['turn_id'])
    assert dispatch_returns.validate_child_publication(tree,'book',writing_artifacts.resolve_path(tree,'book','dispatch/later-note.md'),
        'x',later['turn_id']) is None
    assert returned.read_bytes()==before
