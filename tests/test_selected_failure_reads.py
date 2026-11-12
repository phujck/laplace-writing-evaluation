"""Selected failure custody/cut controls; deterministic public journal only."""
import json
from pathlib import Path

import pytest

from laplace.core import bodies
from laplace.core.records import capture
from laplace.representation import writing_bodies as wb
from laplace.writing import records, session_reads as S
from laplace.writing.records import _failures, _fold, _index


def seed(root):
    for project,sid,tid in [('p','WS','WT'),('other','WS-other','WT-other')]:
        records.bank(root,{'record':'writing-session','id':sid,'project':project})
        records.bank(root,{'record':'writing-turn','id':tid,'session_id':sid,'project':project})
    failure(root)
    records.bank(root,{'record':'writing-tool-failure','id':'FAIL-read','project':'p','turn_id':'WT',
        'operation':'repository','payload':{'path':'notes.txt'},'error':'source changed',
        'recovery':{'next_reads':[{'operation':'repository','payload':{'path':'notes.txt'}}]}})


def failure(root,**changes):
    records.bank(root,{'record':'writing-tool-failure','id':'FAIL','project':'p','turn_id':'WT',
        'operation':'edit','payload':{'file':'paper.tex'},'error':'changed',**changes})


def held(root,value):
    raw=bodies.encode(value)
    return bodies.reference(wb.store(root).put(raw),wb.STORE,len(raw))


def action(root,**changes):
    records.bank(root,{'record':'writing-tool-action','id':'ACTION','project':'p','turn_id':'WT',
        'operation':'edit','payload':{'file':'paper.tex'},'outcome':{'ok':True},**changes})


def read(root,**changes):
    records.bank(root,{'record':'writing-tool-read','id':'READ','project':'p','turn_id':'WT',
        'operation':'repository','payload':{'path':'notes.txt'},'output_sha256':'a'*64,**changes})


def rich(root):
    state=_fold._records(root)
    return S._turn_failure_rows(state['turns']['WT'],state)


def selected(root,**kwargs):
    return S.session_turn_detail(root,'p','WT','failures',**kwargs)


def test_exact_response_lazy_bodies_warm_append_and_paging(tmp_path,monkeypatch):
    seed(tmp_path)
    replacement=held(tmp_path,'SELECTED REPLACEMENT '*1000)
    unrelated=held(tmp_path,'UNRELATED PUBLIC TEXT '*6000)
    action(tmp_path,payload={'file':'paper.tex','edits':[{'file':'paper.tex','line_start':99,
        'replacement':replacement}]})
    action(tmp_path,id='OTHER',project='other',turn_id='WT-other',payload={'content':unrelated})
    action(tmp_path,id='FOREIGN-SCOPE',project='other',payload={'file':'paper.tex','content':unrelated})
    context=held(tmp_path,{'private_in_real_use':'PUBLIC CONTEXT '*1000})
    records.bank(tmp_path,{'record':'writing-turn-context-baseline','id':'CTX','turn_id':'WT-other',
        'consumed':context})
    records.bank(tmp_path,{'record':'writing-reply','id':'REPLY-other','turn_id':'WT-other',
        'text':unrelated,'proposal':context})
    expected=rich(tmp_path)
    _fold._CACHE.pop(str(tmp_path/'contract/talk.jsonl'))
    reads=[];original=wb.read_bytes
    def counted(ref,root):
        reads.append(ref['content_handle']);return original(ref,root)
    monkeypatch.setattr(wb,'read_bytes',counted)
    monkeypatch.setattr(S,'_records',lambda *a:pytest.fail('direct failures entered rich fold'))
    cold=selected(tmp_path);warm=selected(tmp_path)
    assert cold==warm and cold['items']==expected
    assert replacement['content_handle'] not in reads and unrelated['content_handle'] not in reads
    assert context['content_handle'] not in reads and str(tmp_path/'contract/talk.jsonl') not in _fold._CACHE
    assert len(reads)==6, 'two selected failures plus one outer action payload on each request'
    page=selected(tmp_path,offset=1,limit=1,item_id='ignored-existing-contract')
    assert page['items']==cold['items'][1:] and page['pagination']=={
        'offset':1,'limit':1,'total':2,'next_offset':None}
    read(tmp_path)
    after=selected(tmp_path)
    assert after['items'][1]['resolved_later'] and after['items'][1]['recovery_read']['read_id']=='READ'
    assert not after['items'][0]['resolved_later'] and after['items'][0]['related_action']['action_id']=='ACTION'
    assert after['items']==rich(tmp_path)


@pytest.mark.parametrize('collision',['foreign-action','cross-kind','unknown-kind','failure','read'])
def test_global_identity_collisions_do_not_renew_evidence(tmp_path,collision):
    seed(tmp_path);action(tmp_path);read(tmp_path)
    if collision=='foreign-action':action(tmp_path,project='other',turn_id='WT-other')
    elif collision=='cross-kind':read(tmp_path,id='ACTION')
    elif collision=='unknown-kind':records.bank(tmp_path,{'record':'public-fixture-unknown','id':'ACTION'})
    elif collision=='failure':failure(tmp_path,project='other',turn_id='WT-other')
    else:read(tmp_path,project='other',turn_id='WT-other')
    result=selected(tmp_path)['items']
    assert result==rich(tmp_path)
    if collision=='read':assert not result[1]['resolved_later']
    else:assert result[0]['related_action'] is None


def test_original_order_and_provider_issue_final_reply_legacy_join(tmp_path,monkeypatch):
    seed(tmp_path);action(tmp_path);read(tmp_path)
    issue={'id':'ISSUE','operation':'repository','payload':{'path':'other.txt'},'reason':'unreadable'}
    duplicate={'id':'DUP','operation':'edit','payload':{'file':'paper.tex'},'error':'changed'}
    unused=held(tmp_path,'UNSELECTED REPLY/PROPOSAL '*2000)
    records.bank(tmp_path,{'record':'writing-reply','id':'OLD','turn_id':'WT','session_id':'WS',
        'provider_issues':[{'id':'OLD-ISSUE','reason':'overwritten'}],'text':unused})
    # Native-ID fallback does not apply while WT already has a reply; direct
    # reply chronology still selects the final provider-issue occurrence.
    records.bank(tmp_path,{'record':'writing-reply','id':'LATEST','turn_id':'WT','session_id':'WS',
        'provider_issues':[issue,duplicate],'text':unused,'proposal':unused})
    expected=rich(tmp_path);seen=[];real=wb.read_bytes
    monkeypatch.setattr(wb,'read_bytes',lambda ref,root:(seen.append(ref['content_handle']),real(ref,root))[1])
    assert selected(tmp_path)['items']==expected
    assert [row['record']['id'] for row in expected]==['FAIL','FAIL-read','ISSUE']
    assert unused['content_handle'] not in seen
    # A second public root isolates the actual legacy native-turn fallback.
    root=tmp_path/'legacy';seed(root)
    records.bank(root,{'record':'writing-reply','id':'LEGACY','turn_id':'native-id','session_id':'WS',
        'provider_issues':[issue],'text':unused})
    assert selected(root)['items']==rich(root)
    assert selected(root)['items'][-1]['record']['id']=='ISSUE'


def test_only_original_later_reads_and_actions_supply_evidence(tmp_path):
    records.bank(tmp_path,{'record':'writing-session','id':'WS','project':'p'})
    records.bank(tmp_path,{'record':'writing-turn','id':'WT','session_id':'WS','project':'p'})
    action(tmp_path);read(tmp_path)
    failure(tmp_path)
    failure(tmp_path,id='FAIL-read',operation='repository',payload={'path':'notes.txt'},
        recovery={'next_reads':[{'operation':'repository','payload':{'path':'notes.txt'}}]})
    read(tmp_path,id='BASELINE',record='writing-tool-read-baseline')
    result=selected(tmp_path)['items']
    assert result==rich(tmp_path)
    assert all(not row['resolved_later'] and row['related_action'] is None for row in result)
    read(tmp_path,id='LATER');action(tmp_path,id='LATER-ACTION')
    result=selected(tmp_path)['items']
    assert result==rich(tmp_path)
    assert result[1]['recovery_read']['read_id']=='LATER'
    assert result[0]['related_action']['action_id']=='LATER-ACTION'


@pytest.mark.parametrize('identity',['turn','session'])
def test_selected_actor_ambiguity_refuses(tmp_path,identity):
    seed(tmp_path)
    records.bank(tmp_path,{'record':'writing-turn' if identity=='turn' else 'writing-session',
        'id':'WT' if identity=='turn' else 'WS','project':'other'})
    with pytest.raises(ValueError,match='ambiguous'):selected(tmp_path)


@pytest.mark.parametrize('change',['row','replacement','truncation'])
def test_captured_change_never_combines_new_source_with_old_selection(tmp_path,monkeypatch,change):
    seed(tmp_path);action(tmp_path)
    path=tmp_path/'contract/talk.jsonl';before=path.read_bytes()
    real=_index._raw_indexed_record;changed=False
    def changing(idx,meta):
        nonlocal changed
        if meta['record']=='writing-tool-failure' and not changed:
            changed=True
            if change=='row':path.write_bytes(before.replace(b'FAIL-read',b'FAIL-xxxx'))
            elif change=='replacement':
                other=path.with_suffix('.replacement');other.write_bytes(before);other.replace(path)
            else:path.write_bytes(before[:meta['_offset']])
        return real(idx,meta)
    monkeypatch.setattr(_index,'_raw_indexed_record',changing)
    with pytest.raises(capture.CapturedRowChanged):selected(tmp_path)
    monkeypatch.setattr(_index,'_raw_indexed_record',real)
    if change=='replacement':assert selected(tmp_path)['items']==rich(tmp_path)


def test_append_during_body_read_keeps_one_cut_then_observes_new_ambiguity(tmp_path,monkeypatch):
    seed(tmp_path);action(tmp_path)
    before=selected(tmp_path)
    real=wb.read_bytes;appended=False
    def append(ref,root):
        nonlocal appended
        if not appended:
            appended=True
            records.bank(root,{'record':'public-fixture-unknown','id':'ACTION'})
        return real(ref,root)
    monkeypatch.setattr(wb,'read_bytes',append)
    assert selected(tmp_path)==before
    assert selected(tmp_path)['items'][0]['related_action'] is None
