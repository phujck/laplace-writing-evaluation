"""Historical failed operations and exact related actions, without task inference."""
import copy
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from laplace.native import tools
from laplace.web import authoring
from laplace.writing import records, session_reads
from laplace.representation import writing_bodies
from test_tool_refusal_recovery import turn, seed_recovery, read


def failure(root, ident='FAIL-claim', **changes):
    row={'record':'writing-tool-failure','id':ident,'project':'p','turn_id':'WT-r',
         'operation':'edit','payload':{'file':'paper.tex','edits':[
             {'file':'paper.tex','line_start':10,'line_end':10,'replacement':'Correct a numerical claim.'}]},
         'error':'source changed'}
    records.bank(root,{**row,**changes})


def action(root, ident='ACTION-bibliography', **changes):
    row={'record':'writing-tool-action','id':ident,'project':'p','turn_id':'WT-r',
         'operation':'edit','payload':{'file':'paper.tex','edits':[
             {'file':'paper.tex','line_start':99,'line_end':99,'replacement':'Correct bibliography punctuation.'}]},
         'outcome':{'ok':True}}
    records.bank(root,{**row,**changes})


def item(root):
    return session_reads.session_turn_detail(root,'p','WT-r','failures')['items'][0]


def test_claim_failure_and_unrelated_same_file_edit_is_linked_not_recovered_across_owners(tmp_path,monkeypatch):
    turn(tmp_path);failure(tmp_path);action(tmp_path)
    before=(tmp_path/'contract/talk.jsonl').read_bytes()
    row=item(tmp_path);related=row['related_action']
    assert row['record']['id']=='FAIL-claim' and not row['resolved_later'] and row['recovery_read'] is None
    assert set(related)=={'action_id','operation','target','read_handle','basis'}
    assert related['action_id']=='ACTION-bibliography' and related['target']=='paper.tex'
    assert related['operation']=='edit' and related['basis']=='same_operation_target'
    summary=session_reads.session_turn_detail(tmp_path,'p','WT-r','summary')['turn']
    assert tuple(summary[k] for k in ('failure_count','read_recovery_count','related_action_count','resolved_count','unresolved_count'))==(1,0,1,0,1)
    assert 'tool_failures' not in summary and 'related_action' not in summary
    for exact in (session_reads.session_state(tmp_path,'WS-r')['turns'][0],
                  session_reads.session_turn_detail(tmp_path,'p','WT-r','turn')['turn']):
        assert exact['tool_failures'][0]['related_action']==related and not exact['tool_failures'][0]['resolved_later']
    monkeypatch.setattr(authoring,'_root',lambda:tmp_path)
    status,_,raw=authoring.handle('/authoring/session-turn',{'project':['p'],'id':['WT-r'],'view':['failures']},'GET',b'')
    assert status==200 and json.loads(raw)['items'][0]['related_action']==related
    handle=related['read_handle'];query=parse_qs(urlsplit(handle['http']['url']).query)
    assert query=={'project':['p'],'view':['record'],'id':['activity:journal:ACTION-bibliography']}
    status,_,raw=authoring.handle(urlsplit(handle['http']['url']).path,query,'GET',b'')
    native=tools.execute(tmp_path,'p','review',handle['operation'],handle['payload'])
    assert status==200 and json.loads(raw)['record']==native['record']
    assert native['record']['payload']['edits'][0]['line_start']==99
    after=(tmp_path/'contract/talk.jsonl').read_bytes()
    assert after.startswith(before), 'inspection preserves original immutable attempts'
    appended=[json.loads(line) for line in after[len(before):].splitlines()]
    assert appended and all(row['record']=='writing-tool-read' for row in appended)
    (tmp_path/'followthrough-proof.json').write_text(json.dumps({'failure':row,'summary':summary,
        'exact_action_read':native,'provider_calls':0},ensure_ascii=False))


@pytest.mark.parametrize('kind',['different-target','earlier','cross-project','cross-turn','failed-action','duplicate-action','duplicate-failure','cross-kind'])
def test_no_false_related_action_for_scope_order_outcome_or_ambiguous_identity(tmp_path,kind):
    turn(tmp_path)
    if kind=='earlier':action(tmp_path)
    failure(tmp_path)
    if kind=='different-target':action(tmp_path,payload={'file':'other.tex'})
    elif kind=='cross-project':action(tmp_path,project='other')
    elif kind=='cross-turn':
        records.bank(tmp_path,{'record':'writing-turn','id':'WT-other','project':'p','session_id':'WS-r'})
        action(tmp_path,turn_id='WT-other')
    elif kind=='failed-action':action(tmp_path,outcome={'ok':False,'status':'FAILED'})
    elif kind in {'duplicate-action','duplicate-failure','cross-kind'}:
        action(tmp_path)
        if kind=='duplicate-action':action(tmp_path)
        elif kind=='duplicate-failure':failure(tmp_path)
        else:records.bank(tmp_path,{'record':'writing-tool-read','id':'ACTION-bibliography','project':'p','turn_id':'WT-r','operation':'edit','payload':{'file':'paper.tex'},'output_sha256':'a'*64})
    rows=session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items']
    assert rows and all(row['related_action'] is None and not row['resolved_later'] for row in rows)


def test_multiple_failures_count_related_actions_without_additional_body_reads_in_projection(tmp_path,monkeypatch):
    turn(tmp_path)
    failure(tmp_path);failure(tmp_path,'FAIL-second')
    huge='SOURCE_BODY_MUST_STAY_LAZY '*80000
    action(tmp_path,payload={'file':'paper.tex','edits':[{'file':'paper.tex','line_start':99,'replacement':huge}]})
    # Existing cold rich fold resolves recorded payloads; the changed projection
    # consumes that captured fold without any additional body read or list-body copy.
    session_reads._records(tmp_path)
    loaded=[];original=writing_bodies.read_bytes
    def selected(ref,*args,**kwargs):
        loaded.append(ref['content_handle']);return original(ref,*args,**kwargs)
    monkeypatch.setattr(writing_bodies,'read_bytes',selected)
    summary=session_reads.session_state(tmp_path,'WS-r',view='summary')['turns'][0]
    assert summary['failure_count']==2 and summary['related_action_count']==2
    assert not summary.get('read_recovery_count') and not summary.get('resolved_count')
    assert 'SOURCE_BODY_MUST_STAY_LAZY' not in json.dumps(summary)
    assert not loaded, 'follow-through projection adds no saved edit-content read'
    rows=session_reads.session_turn_detail(tmp_path,'p','WT-r','failures',limit=1)
    assert rows['pagination']['total']==2 and rows['pagination']['next_offset']==1
    assert rows['items'][0]['related_action']['action_id']=='ACTION-bibliography'


def test_exact_read_recovery_and_help_inspection_are_distinct_from_related_mutation(tmp_path):
    seed_recovery(tmp_path);read(tmp_path)
    failure(tmp_path);action(tmp_path)
    failure(tmp_path,'FAIL-write',operation='store_artifact',payload={'path':'note.md'},
            recovery={'help':{'operation':'help','payload':{'operation':'store_artifact'}}})
    read(tmp_path,'READ-help',payload={'operation':'store_artifact'})
    rows=session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items']
    by_id={row['record']['id']:row for row in rows}
    assert by_id['FAIL-help']['resolved_later'] and by_id['FAIL-help']['related_action'] is None
    assert by_id['FAIL-write']['recovery_read'] and not by_id['FAIL-write']['resolved_later']
    assert not by_id['FAIL-write']['recovery_read']['recovers_read_goal']
    summary=session_reads.session_turn_detail(tmp_path,'p','WT-r','summary')['turn']
    assert (summary['failure_count'],summary['read_recovery_count'],summary['related_action_count'])==(3,1,1)


def test_captured_cut_is_detached_and_provider_failure_uses_same_meaning(tmp_path):
    turn(tmp_path);failure(tmp_path)
    held=session_reads._records(tmp_path);source=held['turns']['WT-r'];cut=session_reads._failure_read_cut(held,[source])
    old=copy.deepcopy(session_reads._turn_failure_rows(source,cut));action(tmp_path)
    assert session_reads._turn_failure_rows(source,cut)==old and old[0]['related_action'] is None
    records.bank(tmp_path,{'record':'writing-reply','id':'WR-issues','project':'p','turn_id':'WT-r','session_id':'WS-r',
        'text':'Public failure report','provider_issues':[{'id':'PROVIDER-fail','project':'p','turn_id':'WT-r',
            'operation':'edit','payload':{'file':'paper.tex'},'error':'different public issue'}]})
    # An issue without its own unambiguous journal occurrence cannot claim later action order.
    rows=session_reads.session_turn_detail(tmp_path,'p','WT-r','failures')['items']
    assert rows[0]['related_action']['action_id']=='ACTION-bibliography'
    assert rows[1]['origin']=='provider' and rows[1]['related_action'] is None and not rows[1]['resolved_later']


@pytest.mark.parametrize('payload',[{'edits':[]},{'edits':[{}]},{'edits':[1]},
                                  {'edits':[{'file':'paper.tex','line_start':2,'line_end':2}]}])
def test_edits_only_target_is_compact_and_unknown_locations_cannot_conflate(tmp_path,payload):
    turn(tmp_path);failure(tmp_path,payload=payload);action(tmp_path,payload=payload)
    row=item(tmp_path)
    assert not row['resolved_later']
    if payload=={'edits':[{'file':'paper.tex','line_start':2,'line_end':2}]}:
        assert row['related_action']['target']=='paper.tex'
    else:assert row['related_action'] is None


def test_current_owner_help_names_history_read_recovery_and_related_action_separately(tmp_path):
    turn(tmp_path)
    help_reply=tools.execute(tmp_path,'p','review','help',{'operation':'author_history'})
    text=json.dumps(help_reply)
    assert 'read_recovery_count' in text and 'related_action_count' in text
    assert 'not a successful retry or repaired task' in text
