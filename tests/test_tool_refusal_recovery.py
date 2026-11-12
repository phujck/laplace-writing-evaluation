"""Exact returned-refusal receipts and original-read recovery observations."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from laplace.core import admission
from laplace.web import authoring as a
from laplace.native import tools, declarations as d
from laplace.writing import session_reads
from laplace.writing import records as writing_records
from laplace.representation import writing_bodies


def turn(root):
    (root/'contract').mkdir();md=root/'proj'/'manuscript';md.mkdir(parents=True)
    (md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}Fixture.\\end{document}\n')
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{
        'name':'p','kind':'conceptric','project_dir':'proj','tex_root':'proj/manuscript/main.tex'}]}))
    writing_records.bank(root,{'record':'writing-session','id':'WS-r','project':'p','provider':'claude'})
    writing_records.bank(root,{'record':'writing-turn','id':'WT-r','session_id':'WS-r','project':'p','mode':'review'})


def friction():
    return {'verb':'record','concept':'technical-friction@project','target':'p','expected':[],
        'payload':{'owning_layer':'fixture','value':'Invalid nine-item request',
                   'chain':[str(n) for n in range(9)]},'by':''}


def failures(root):
    return [json.loads(line) for line in (root/'contract/talk.jsonl').read_text().splitlines()
            if json.loads(line).get('record')=='writing-tool-failure']


def test_semantic_owner_refusal_banks_once_without_update_recursion_and_recovers_exact_row(tmp_path,monkeypatch):
    turn(tmp_path);updates=[]
    monkeypatch.setattr(tools,'_project_updates',lambda root,project,tid,result,fields:(updates.append(1),result)[1])
    result=tools.call(tmp_path,'p','review',friction(),turn_id='WT-r')
    assert result['ok'] is False and 'too long' in result['refused']['said']
    rows=failures(tmp_path);assert len(rows)==1 and updates==[1]
    saved=writing_bodies.resolve_fields(rows[0],tmp_path,strict=True)
    assert saved['operation']=='corpus/friction-report' and len(saved['payload']['chain'])==9
    assert result['failure_receipt']['row_id']==rows[0]['id']
    inspected=tools.call(tmp_path,'p','review',result['failure_read'],turn_id='WT-r')
    assert inspected['record']['id']==rows[0]['id'] and inspected['record']['error_type']=='PayloadAdmissionError'
    assert not (tmp_path/'corpus_friction/p.jsonl').exists()
    again=tools.call(tmp_path,'p','review',friction(),turn_id='WT-r')
    assert len(failures(tmp_path))==2 and again['failure_receipt']['row_id']!=rows[0]['id']


def test_actual_mcp_named_and_semantic_paths_have_one_failure_per_invocation(tmp_path):
    turn(tmp_path)
    requests=[{'jsonrpc':'2.0','id':number,'method':'tools/call','params':{
        'name':'laplace_project','arguments':fields}} for number,fields in enumerate([
        {'operation':'help','payload':{'concept':'technical-friction@project','verb':'record'}},
        friction(),friction()],1)]
    run=subprocess.run([sys.executable,'-m','laplace.native.tools','--root',str(tmp_path),
        '--project','p','--mode','review','--turn-id','WT-r'],
        input=''.join(json.dumps(row)+'\n' for row in requests),text=True,capture_output=True,check=True)
    returned=[json.loads(line)['result'] for line in run.stdout.splitlines()]
    assert returned[0]['isError'] is True
    assert 'isError' not in returned[1]  # Existing structured refusal envelope preserved.
    assert len(failures(tmp_path))==3 and len({row['id'] for row in failures(tmp_path)})==3
    replies=[json.loads(row['content'][0]['text']) for row in returned]
    assert {row['failure_receipt']['row_id'] for row in replies}=={row['id'] for row in failures(tmp_path)}
    assert all(row['failure_read']['payload']['id']=='activity:journal:'+row['failure_receipt']['row_id'] for row in replies)
    assert [row['operation'] for row in failures(tmp_path)]==['help','corpus/friction-report','corpus/friction-report']
    assert not (tmp_path/'corpus_friction/p.jsonl').exists()


def test_logging_failure_and_wrong_binding_preserve_refusal_without_fabricated_receipt(tmp_path,monkeypatch):
    turn(tmp_path)
    result=tools.call(tmp_path,'other','review',friction(),turn_id='WT-r')
    assert not result['ok'] and result['failure_receipt']['row_id'] is None
    assert not failures(tmp_path)
    monkeypatch.setattr(tools,'_bank_talk_row',lambda *args,**kwargs:(_ for _ in ()).throw(OSError('receipt unavailable')))
    result=tools.call(tmp_path,'p','review',friction(),turn_id='WT-r')
    assert not result['ok'] and result['failure_receipt']['row_id'] is None
    assert 'receipt unavailable' in result['failure_receipt']['note'] and 'failure_read' not in result


def test_scientific_fail_and_arbitrary_owner_false_are_not_transport_failures(tmp_path,monkeypatch):
    turn(tmp_path)
    monkeypatch.setattr(tools,'execute',lambda *args,**kwargs:{'ok':False,'status':'FAIL','scientific_result':'negative'})
    request={'verb':'read','concept':'contract@project','target':'p','expected':[],'payload':{},'by':''}
    result=tools.call(tmp_path,'p','review',request,turn_id='WT-r')
    assert result['owner_response']['status']=='FAIL' and not failures(tmp_path)


def seed_recovery(root):
    turn(root)
    failure={'record':'writing-tool-failure','id':'FAIL-help','project':'p','turn_id':'WT-r',
        'operation':'help','payload':{'concept':'technical-friction@project','verb':'record'},
        'error':'selector refused','recovery':{'contract':{'operation':'help','input':copy.deepcopy(d.DECLARATIONS['help'].payload)}}}
    writing_records.bank(root,failure)
    return failure


def read(root,ident='READ-good',**changes):
    row={'record':'writing-tool-read','id':ident,'project':'p','turn_id':'WT-r',
         'operation':'help','payload':{'concept':'technical-friction@project','project':'p'},
         'output_sha256':'a'*64}
    writing_records.bank(root,{**row,**changes})


def test_help_recovery_is_original_later_read_and_all_public_views_agree(tmp_path):
    seed_recovery(tmp_path);original=(tmp_path/'contract/talk.jsonl').read_bytes();read(tmp_path)
    detail=session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]
    assert detail['resolved_later'] is True and detail['recovery_read']['read_id']=='READ-good'
    assert detail['recovery_read']['task_completion_inferred'] is False
    assert session_reads.session_state(tmp_path,'WS-r',view='summary')['turns'][0]['resolved_count']==1
    assert session_reads.session_state(tmp_path,'WS-r')['turns'][0]['tool_failures'][0]['recovery_read']==detail['recovery_read']
    assert session_reads.session_turn_detail(tmp_path,'p','WT-r','turn')['turn']['tool_failures'][0]['resolved_later'] is True
    assert (tmp_path/'contract/talk.jsonl').read_bytes().startswith(original)


@pytest.mark.parametrize('changes',[
    {'project':'other'}, {'turn_id':'other'}, {'payload':{'concept':'another@project'}},
    {'payload':{'concept':'technical-friction@project','operation':'source'}},
    {'payload':{'concept':'technical-friction@project','verb':'record'}},
    {'output_sha256':None}, {'record':'writing-tool-read-baseline'},
])
def test_unrelated_unproved_or_baseline_read_cannot_resolve(tmp_path,changes):
    seed_recovery(tmp_path);read(tmp_path,**changes)
    item=session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]
    assert not item['resolved_later'] and item['recovery_read'] is None


def test_earlier_read_duplicate_identity_and_conflicting_failure_selector_remain_unproved(tmp_path):
    turn(tmp_path);read(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-tool-failure','id':'FAIL-help','project':'p','turn_id':'WT-r',
        'operation':'help','payload':{'concept':'technical-friction@project','verb':'record'},
        'error':'selector refused','recovery':{'contract':{'operation':'help','input':copy.deepcopy(d.DECLARATIONS['help'].payload)}}})
    assert not session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]['resolved_later']
    read(tmp_path)  # Same immutable ID is ambiguous, not a later occurrence.
    assert not session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]['resolved_later']
    assert admission.selector_scope({'concept':'x','operation':'help'},d.DECLARATIONS['help'].payload) is None


def test_write_recovery_read_is_inspection_not_success(tmp_path,monkeypatch):
    turn(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-tool-failure','id':'FAIL-write','project':'p','turn_id':'WT-r',
        'operation':'store_artifact','payload':{'path':'note.md'},'error':'read current revision',
        'recovery':{'next_reads':[{'operation':'read_artifact','payload':{'path':'note.md'}}]}})
    read(tmp_path,operation='read_artifact',payload={'path':'note.md','project':'p'})
    item=session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]
    assert item['recovery_read']['read_id']=='READ-good' and item['resolved_later'] is False
    assert item['recovery_read']['recovers_read_goal'] is False
    from urllib.parse import urlsplit,parse_qs
    handle=item['recovery_read']['read_handle']
    assert handle['operation']=='author_history' and handle['payload']=={'view':'record','id':'activity:journal:READ-good'}
    assert handle['http']['method']=='GET' and urlsplit(handle['http']['url']).path=='/authoring/history'
    assert parse_qs(urlsplit(handle['http']['url']).query)=={'project':['p'],'view':['record'],'id':['activity:journal:READ-good']}
    before=(tmp_path/'contract/talk.jsonl').read_bytes()
    monkeypatch.setattr(a,'_root',lambda:tmp_path)
    code,_,body=a.handle('/authoring/history',parse_qs(urlsplit(handle['http']['url']).query),'GET',b'')
    assert code==200 and json.loads(body)['record']['id']=='READ-good'
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==before
    assert session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]['resolved_later'] is False


def test_activity_turn_selector_and_unknown_fields_refuse_before_read_with_real_routes(tmp_path,monkeypatch):
    from laplace.work import history
    from laplace.writing.schemas import SCHEMAS
    from jsonschema import Draft202012Validator
    turn(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-other','session_id':'WS-r','project':'p'})
    for tid in ('WT-r','WT-other'):
        writing_records.bank(tmp_path,{'record':'writing-tool-failure','id':'FAIL-'+tid,'project':'p','turn_id':tid,
            'operation':'source','payload':{},'error':'fixture'})
    values={'view':'activity','turn_id':'WT-r','outcome':'failed','limit':5}
    assert list(Draft202012Validator(SCHEMAS['author_history']).iter_errors(values))
    original=history._indexed
    monkeypatch.setattr(history,'_indexed',lambda *args,**kwargs:pytest.fail('read before admission'))
    with pytest.raises(ValueError,match='projection=trace'):
        tools.execute(tmp_path,'p','review','author_history',values)
    monkeypatch.setattr(a,'_root',lambda:tmp_path)
    status,_,raw=a.handle('/authoring/history',{'project':['p'],**{key:[str(value)] for key,value in values.items()}},'GET',b'')
    assert status==409 and 'projection=trace' in json.loads(raw)['error']
    status,_,raw=a.handle('/authoring/history',{'corpus':['p'],'view':['activity'],'unknown':['selector']},'GET',b'')
    assert status==409 and 'unknown' in json.loads(raw)['error']
    monkeypatch.setattr(history,'_indexed',original)
    native=tools.execute(tmp_path,'p','review','author_history',{
        'view':'telemetry','projection':'trace','scope':'turn','turn_id':'WT-r','outcome':'failed'})
    assert native['items'] and {row['turn_id'] for row in native['items']}=={'WT-r'}
    status,_,raw=a.handle('/authoring/session-turn',{'project':['p'],'id':['WT-r'],'view':['failures']},'GET',b'')
    assert status==200 and {row['record']['turn_id'] for row in json.loads(raw)['items']}=={'WT-r'}
    payload={'view':'activity','session_id':'WS-r','outcome':'failed','limit':5}
    native=tools.execute(tmp_path,'p','review','author_history',payload)
    status,_,raw=a.handle('/authoring/history',{'corpus':['p'],**{key:[str(value)] for key,value in payload.items()}},'GET',b'')
    assert status==200 and json.loads(raw)['items']==native['items']


class CountOriginalReads(dict):
    def __init__(self,*args):
        super().__init__(*args);self.passes=0;self.visits=0
    def items(self):
        self.passes+=1
        for item in super().items():self.visits+=1;yield item


def recovery_page(unrelated,with_failures):
    reads=CountOriginalReads({f'FOREIGN-{i}':{'id':f'FOREIGN-{i}','project':'foreign',
        'turn_id':'foreign','record':'writing-tool-read','_order':i} for i in range(unrelated)})
    turns={};orders={}
    for i in range(20):
        tid=f'WT-page-{i}';failure_id=f'FAIL-page-{i}';read_id=f'READ-page-{i}'
        turns[tid]={'id':tid,'project':'p','session_id':'WS-page','text':'Fixture',
            'mode':'review','reply':{'text':'Saved reply','status':'completed'}}
        if with_failures:
            turns[tid]['tool_failures']=[{'id':failure_id,'project':'p','turn_id':tid,
                'operation':'help','payload':{'concept':'technical-friction@project','verb':'record'},
                'error':'selector refused','recovery':{'contract':{'operation':'help','input':d.DECLARATIONS['help'].payload}}}]
            orders[failure_id]=unrelated+2*i
            turns[tid]['tool_failures'][0]['_recovery_order']=orders[failure_id]
            reads[read_id]={'id':read_id,'record':'writing-tool-read','project':'p','turn_id':tid,
                'operation':'help','payload':{'concept':'technical-friction@project'},
                'output_sha256':'a'*64,'_order':unrelated+2*i+1}
    return {'sessions':{'WS-page':{'id':'WS-page','project':'p','provider':'claude'}},
        'turns':turns,'orders':orders,'read_receipts':reads,'artifact_records':{},'artifact_ambiguities':set()}


@pytest.mark.parametrize('unrelated',[1000,10000])
@pytest.mark.parametrize('with_failures',[False,True])
def test_twenty_turn_page_has_zero_or_one_original_read_pass(tmp_path,monkeypatch,unrelated,with_failures):
    records=recovery_page(unrelated,with_failures);reads=records['read_receipts']
    monkeypatch.setattr(session_reads,'_records',lambda *args:records)
    result=session_reads.session_state(tmp_path,'WS-page',view='summary',limit=20)
    assert len(result['turns'])==20
    assert reads.passes==int(with_failures)
    assert reads.visits==(unrelated+20 if with_failures else 0)
    # D4: a compact row omits a KNOWN zero count (absence is the glance's zero); a known one is present
    for row in result['turns']:
        if with_failures:
            assert (row['failure_count'],row['resolved_count'])==(1,1) and 'unresolved_count' not in row
        else:
            assert not {'failure_count','resolved_count','unresolved_count'}&set(row)
    assert '_failure_read_groups' not in records  # Never attached to the persisted fold/cache.
    # ...and only the compact row: the exact single-turn summary keeps every count explicit, zero included
    exact=session_reads.session_turn_detail(tmp_path,'p','WT-page-0','summary')['turn']
    assert (exact['failure_count'],exact['resolved_count'],exact['unresolved_count'])==((1,1,0) if with_failures else (0,0,0))
    assert '_failure_read_groups' not in records


def test_exact_turn_uses_same_cut_once_and_does_not_substitute_baselines(tmp_path,monkeypatch):
    records=recovery_page(10000,True);reads=records['read_receipts']
    records['turns']['WT-page-0']['tool_reads']={'baseline':{'record':'writing-tool-read-baseline',
        'project':'p','turn_id':'WT-page-0','operation':'help','payload':{'concept':'different'}}}
    reads['READ-page-0']['ambiguous']=True
    monkeypatch.setattr(session_reads,'_records',lambda *args:records)
    result=session_reads.session_turn_detail(tmp_path,'p','WT-page-0','failures')
    assert reads.passes==1 and reads.visits==10020
    assert not result['items'][0]['resolved_later'] and result['items'][0]['recovery_read'] is None
    assert '_failure_read_groups' not in records


@pytest.mark.parametrize('unrelated',[100,2000])
def test_failure_rich_turn_validates_only_matching_help_selector(tmp_path,monkeypatch,unrelated):
    records=recovery_page(0,False);tid='WT-page-0';selected=records['turns'][tid]
    selected['tool_failures']=[{'id':f'FAIL-{i}','project':'p','turn_id':tid,'operation':'help',
        'payload':{'concept':'technical-friction@project','verb':'record'},'error':'selector refused',
        'recovery':{'contract':{'operation':'help','input':d.DECLARATIONS['help'].payload}}} for i in range(10)]
    records['orders']={f'FAIL-{i}':i for i in range(10)}
    for row in selected['tool_failures']:row['_recovery_order']=records['orders'][row['id']]
    reads=CountOriginalReads({f'READ-other-{i}':{'id':f'READ-other-{i}','record':'writing-tool-read',
        'project':'p','turn_id':tid,'operation':'help','payload':{'concept':f'unrelated-{i}@project'},
        'output_sha256':'a'*64,'_order':i+20} for i in range(unrelated)})
    reads['READ-matching']={'id':'READ-matching','record':'writing-tool-read','project':'p','turn_id':tid,
        'operation':'help','payload':{'concept':'technical-friction@project'},'output_sha256':'a'*64,'_order':unrelated+30}
    records['read_receipts']=reads;monkeypatch.setattr(session_reads,'_records',lambda *args:records)
    original=admission.selector_scope;calls=[]
    def validate(*args,**kwargs):calls.append(1);return original(*args,**kwargs)
    monkeypatch.setattr(admission,'selector_scope',validate)
    result=session_reads.session_turn_detail(tmp_path,'p',tid,'failures')
    assert reads.passes==1 and reads.visits==unrelated+1
    assert len(calls)==20  # Ten retained intents plus ten actual matching reads.
    assert all(item['resolved_later'] and item['recovery_read']['read_id']=='READ-matching' for item in result['items'])


def test_held_recovery_cut_detaches_actual_later_duplicate_and_candidate_appends(tmp_path):
    seed_recovery(tmp_path);read(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-tool-failure','id':'FAIL-write','project':'p','turn_id':'WT-r',
        'operation':'store_artifact','payload':{'path':'note.md'},'error':'stale'})
    records=session_reads._records(tmp_path);source=records['turns']['WT-r'];held=session_reads._failure_read_cut(records,[source])
    before=session_reads._turn_failure_rows(source,held)
    assert [item['resolved_later'] for item in before]==[True,False]
    assert held['_failure_read_groups'][('p','WT-r')]['READ-good'] is not records['read_receipts']['READ-good']
    read(tmp_path)  # Real duplicate in immutable journal, then actual cache refresh.
    writing_records.bank(tmp_path,{'record':'writing-tool-failure','id':'FAIL-later','project':'p','turn_id':'WT-r',
        'operation':'help','payload':{},'error':'later failure'})
    writing_records.bank(tmp_path,{'record':'writing-tool-action','id':'ACTION-later','project':'p','turn_id':'WT-r',
        'operation':'store_artifact','payload':{'path':'note.md','content':'Unneeded public body'},
        'outcome':{'status':'SUCCEEDED','body':'Unneeded result body'}})
    fresh=session_reads._records(tmp_path)
    assert session_reads._turn_failure_rows(fresh['turns']['WT-r'],held)==before
    assert len(session_reads._turn_failure_view(fresh['turns']['WT-r'],held)['tool_failures'])==2
    latest=session_reads._turn_failure_rows(fresh['turns']['WT-r'],session_reads._failure_read_cut(fresh,[fresh['turns']['WT-r']]))
    assert len(latest)==3 and [item['resolved_later'] for item in latest][:2]==[False,False]
    assert latest[1]['related_action']['action_id']=='ACTION-later'
    assert held['_failure_orders'] is not fresh['orders']


def test_snapshot_existing_lock_blocks_concurrent_fold_until_small_cut_is_detached(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    seed_recovery(tmp_path);read(tmp_path);records=session_reads._records(tmp_path)
    entered=Event();release=Event();updated=Event();original=session_reads._recovery_candidate
    def pause(*args,**kwargs):
        entered.set();assert release.wait(3);return original(*args,**kwargs)
    monkeypatch.setattr(session_reads,'_recovery_candidate',pause)
    def append():read(tmp_path);session_reads._records(tmp_path);updated.set()
    with ThreadPoolExecutor(max_workers=2) as pool:
        capture=pool.submit(session_reads._failure_read_cut,records,[records['turns']['WT-r']])
        assert entered.wait(2);writer=pool.submit(append)
        assert not updated.wait(.05);release.set();held=capture.result(timeout=3);writer.result(timeout=3)
    assert session_reads._turn_failure_rows(records['turns']['WT-r'],held)[0]['resolved_later']
    assert not session_reads._turn_failure_rows(records['turns']['WT-r'],session_reads._failure_read_cut(records,[records['turns']['WT-r']]))[0]['resolved_later']


def test_help_read_validation_preserves_boolean_versus_integer_types(tmp_path):
    seed_recovery(tmp_path)
    raw=session_reads._records(tmp_path)['turns']['WT-r']['tool_failures'][0]
    raw['payload']['context']={'line_start':1};raw['payload'].pop('concept')
    raw['payload']['operation']='source'
    read(tmp_path,payload={'operation':'source','context':{'line_start':True}})
    # Python dictionary equality alone cannot establish schema-compatible types.
    assert {'line_start':True}=={'line_start':1}
    item=session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]
    assert not item['resolved_later'] and item['recovery_read'] is None


def test_recovery_cut_does_not_clone_unrelated_source_context_or_effect_bodies():
    class NoClone:
        def __deepcopy__(self,memo):raise AssertionError('unrelated body copied')
    records=recovery_page(10,True);source=records['turns']['WT-page-0']
    source.update(proposal={'body':NoClone()},dependencies={'body':NoClone()},context_parts={'body':NoClone()})
    source['tool_actions']=[{'id':'ACTION-body','project':'p','turn_id':source['id'],
        'operation':'store_artifact','payload':{'path':'note.md','content':NoClone()},
        'outcome':{'status':'SUCCEEDED','body':NoClone()}}]
    source['tool_failures'][0]['recovery']['unrelated_context']=NoClone()
    held=session_reads._failure_read_cut(records,[source])
    assert session_reads._turn_failure_rows(source,held)[0]['resolved_later']
    selected=held['_failure_turns'][('p',source['id'])]
    assert 'proposal' not in selected and 'context_parts' not in selected
    assert 'content' not in selected['tool_actions'][0]['payload']
    assert 'body' not in selected['tool_actions'][0]['outcome']


def test_original_action_occurrence_cannot_move_after_failure_via_reused_id(tmp_path):
    turn(tmp_path)
    action={'record':'writing-tool-action','id':'ACTION-repeat','project':'p','turn_id':'WT-r',
            'operation':'edit','payload':{'file':'a.tex'},'outcome':{'ok':True}}
    failure={'record':'writing-tool-failure','id':'FAIL-edit','project':'p','turn_id':'WT-r',
             'operation':'edit','payload':{'file':'a.tex'},'error':'refused'}
    writing_records.bank(tmp_path,action);writing_records.bank(tmp_path,failure)
    assert not session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]['resolved_later']
    writing_records.bank(tmp_path,{**action,'payload':{'file':'unrelated.tex'}})
    records=session_reads._records(tmp_path)
    assert records['orders']['ACTION-repeat']>records['orders']['FAIL-edit']  # General map unchanged.
    assert not session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]['resolved_later']
    writing_records.bank(tmp_path,{**action,'id':'ACTION-unique-later'})
    assert session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]['related_action']['action_id']=='ACTION-unique-later'


@pytest.mark.parametrize('duplicate_kind',['writing-tool-failure','writing-tool-read','writing-tool-action'])
def test_recovery_rejects_duplicate_failure_and_cross_kind_candidate_ids(tmp_path,duplicate_kind):
    turn(tmp_path)
    failure={'record':'writing-tool-failure','id':'FAIL-reused','project':'p','turn_id':'WT-r',
             'operation':'edit','payload':{'file':'a.tex'},'error':'refused'}
    writing_records.bank(tmp_path,failure)
    writing_records.bank(tmp_path,{'record':'writing-tool-action','id':'ACTION-good','project':'p','turn_id':'WT-r',
        'operation':'edit','payload':{'file':'a.tex'},'outcome':{'ok':True}})
    assert session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]['related_action']['action_id']=='ACTION-good'
    writing_records.bank(tmp_path,{'record':duplicate_kind,'id':'FAIL-reused','project':'p','turn_id':'WT-r',
        'operation':'edit','payload':{'file':'unrelated.tex'},'error':'duplicate','output_sha256':'a'*64})
    assert all(not item['resolved_later'] and item['related_action'] is None for item in session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'])


def test_review_mode_failure_recovery_keeps_original_error_and_real_routes(tmp_path):
    """The real review-mode failure path: failure_response's local suggestion list once shadowed the imported reads
    module, so `reads.effect` raised UnboundLocalError on EVERY review-mode failure (other modes short-circuit before
    it). The original refusal, its classification, the review permission routes and the read handles must survive."""
    turn(tmp_path)
    # a write review cannot perform: original error, not permitted, review routes, exact help
    write = tools.failure_response(tmp_path, 'p', 'review', 'store_artifact', {'path': 'x.md', 'content': 'y'},
                                   ValueError('original store refusal'), turn_id='WT-r')
    assert write['error'] == 'original store refusal' and write['ok'] is False
    assert write['review_routes']['findings']['operation'] == 'note' and write['help'] == {'operation': 'help', 'payload': {'operation': 'store_artifact'}}
    # a review-permitted act: no permission routes, and its useful read handle is offered
    review = tools.failure_response(tmp_path, 'p', 'review', 'work_review', {'phase': 'review'},
                                    ValueError('original review refusal'), turn_id='WT-r')
    assert review['error'] == 'original review refusal' and 'review_routes' not in review
    assert {'operation': 'project', 'payload': {}} in review['next_reads']
    # the actual adapter route (native.tools main -> tool_failure -> _tool_failure -> failure_response) for an owner
    # refusal: before the repair the shadowing surfaced here as recovery_unavailable 'UnboundLocalError: ...'
    refusal = ValueError('original owner refusal: the review names no handed-off obligation')
    result = tools.tool_failure(tmp_path, 'p', 'review', 'work_review', {'id': 'missing', 'phase': 'review'}, refusal, 'WT-r')
    assert result['ok'] is False and result['error'] == str(refusal)
    assert 'recovery_unavailable' not in result and 'UnboundLocalError' not in json.dumps(result, default=str)
    assert 'review_routes' not in result and {'operation': 'project', 'payload': {}} in result['next_reads']
    assert result['failure_receipt']['row_id'] and failures(tmp_path)[-1]['error'] == str(refusal)


def test_later_wrong_target_and_cross_kind_action_reuse_do_not_resolve(tmp_path):
    turn(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-tool-action','id':'ACTION-before','project':'p','turn_id':'WT-r',
        'operation':'edit','payload':{'file':'a.tex'},'outcome':{'ok':True}})
    writing_records.bank(tmp_path,{'record':'writing-tool-failure','id':'FAIL-a','project':'p','turn_id':'WT-r',
        'operation':'edit','payload':{'file':'a.tex'},'error':'refused'})
    writing_records.bank(tmp_path,{'record':'writing-tool-action','id':'ACTION-wrong','project':'p','turn_id':'WT-r',
        'operation':'edit','payload':{'file':'other.tex'},'outcome':{'ok':True}})
    writing_records.bank(tmp_path,{'record':'writing-tool-read','id':'ACTION-before','project':'p','turn_id':'WT-r',
        'operation':'edit','payload':{'file':'other.tex'},'output_sha256':'a'*64})
    assert not session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items'][0]['resolved_later']
