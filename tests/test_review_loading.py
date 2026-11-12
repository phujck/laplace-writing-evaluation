"""Bounded same-owner review reads; no manuscript bodies from live projects."""
import json
from pathlib import Path
import pytest
from laplace.pipeline import authoring
from laplace.web import authoring as authoring_surface
from laplace.native import tools as writing_tools
from laplace.writing import records as writing_records
from laplace.writing import session_reads
from laplace.core import checkout
from test_authoring_core import _fixture


def _mixed(tmp_path,monkeypatch):
    _fixture(tmp_path,monkeypatch)
    path=tmp_path/'manuscript'/'authoring.json'
    huge='Generic exact source body.\n'*5000
    rows=[{'id':f'AC-{i}','kind':'note','scope':['passage','project','global'][i%3],
           'text':f'Note {i}. '+huge,'status':['open','resolved','dismissed','superseded'][i%4],
           'anchor':{'file':'sec_one.tex','lines':[1,2],'before':huge,'after':huge,'quote':huge},
           'before':huge,'after':huge,'reply_to':'AC-0' if i==39 else None}
          for i in range(40)]
    rows.append({'id':'AC-edit','kind':'source-edit','scope':'passage','text':'Applied change',
                 'status':'open','anchor':{'file':'sec_one.tex'},'before':huge,'after':huge})
    raw={**authoring._blank('fixture'),'revision':7,'corrections':rows,
         'contexts':[{'id':'old','structure':{'$laplace_context_blob':'sha256:missing'}}],
         'context_blobs':{'sha256:missing':{'private':'not needed'}}}
    path.write_text(json.dumps(raw));return path,rows


def test_lists_count_page_without_hydrating_bodies_exact_offpage_preserved(tmp_path,monkeypatch):
    path,rows=_mixed(tmp_path,monkeypatch)
    monkeypatch.setattr(authoring,'_context_blob_identity',lambda _:pytest.fail('Unrelated context blob hydrated'))
    monkeypatch.setattr(authoring,'_locked',lambda _:pytest.fail('Readonly history created a mutation lock'))
    before={str(p):p.stat().st_mtime_ns for p in tmp_path.rglob('*') if p.is_file()}
    first=authoring.history('fixture',{'order':'newest','limit':10},tmp_path)
    assert first['total']==41 and first['next_offset']==10 and first['omitted']==31
    assert first['items'][0]['id']=='AC-edit'
    assert rows[0]['before'] not in json.dumps(authoring._HISTORY_CACHE[str(path)][1])
    assert sum(sum(statuses.values()) for statuses in first['counts'].values())==41
    assert first['counts']['applied-edits']['open']==1
    page=first;ids=[]
    while True:
        ids += [row['id'] for row in page['items']]
        for row in page['items']:
            assert not {'before','after','hunks','quote'} & row.keys()
            assert not {'before','after','hunks','quote'} & row['anchor'].keys()
            assert len(row['text'])<=1200
        if page['next_offset'] is None:break
        page=authoring.history('fixture',{'order':'newest','limit':10,'offset':page['next_offset'],'as_of':first['as_of']},tmp_path)
    assert len(ids)==len(set(ids))==41
    exact=authoring.history('fixture',{'id':'AC-0','offset':30,'correction_category':'applied-edits'},tmp_path)
    assert exact['item']['text']==rows[0]['text'] and exact['item']['anchor']['before']==rows[0]['anchor']['before']
    parent=authoring.history('fixture',{'id':'AC-39'},tmp_path)['item']['reply_to']
    assert authoring.history('fixture',{'id':parent},tmp_path)['item']['id']=='AC-0'
    assert before=={str(p):p.stat().st_mtime_ns for p in tmp_path.rglob('*') if p.is_file()}


def test_filter_counts_closed_notes_and_cut_cover_external_feedback(tmp_path,monkeypatch):
    path,rows=_mixed(tmp_path,monkeypatch)
    first=authoring.history('fixture',{'correction_category':'notes','status':'closed','limit':25},tmp_path)
    assert first['total']==30 and all(row['correction_category']!='applied-edits' and row['status']!='open' for row in first['items'])
    ledger=path.parent/'feedback'/'feedback.jsonl';ledger.parent.mkdir()
    ledger.write_text(json.dumps({'id':'FB-external','record':'author-edit','by':'author','anchor':{'file':'sec_one.tex'},'before':'a','after':'b'})+'\n')
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        authoring.history('fixture',{'offset':first['next_offset'],'as_of':first['as_of']},tmp_path)
    current=authoring.history('fixture',{'correction_category':'applied-edits','order':'newest'},tmp_path)
    assert current['total']==2 and current['revision']==7 and current['as_of']!=first['as_of']
    raw=json.loads(path.read_text());raw['revision']=8;path.write_text(json.dumps(raw))
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        authoring.history('fixture',{'as_of':current['as_of']},tmp_path)


def test_http_native_share_projection_and_read_cut(tmp_path,monkeypatch):
    _mixed(tmp_path,monkeypatch)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    payload={'order':'newest','correction_category':'project-notes','status':'open','limit':5}
    status,_,body=authoring_surface.handle('/authoring/history',{'project':['fixture'],**{k:[str(v)] for k,v in payload.items()}},'GET',b'')
    native=writing_tools.execute(tmp_path,'fixture','work','author_history',payload)
    assert status==200 and json.loads(body)==native
    summary_status,_,summary_body=authoring_surface.handle('/authoring/state',{'project':['fixture'],'view':['summary']},'GET',b'')
    summary=json.loads(summary_body)
    assert summary_status==200 and summary['revision']==7 and 'corrections' not in summary and 'contexts' not in summary


def test_session_summary_does_not_repeat_structured_source_bodies(tmp_path):
    huge='generic historical body'*2000
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-list','project':'fixture','provider':'codex'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-list','session_id':'WS-list','project':'fixture','text':'Inspect proposals','mode':'work'})
    proposal={'edits':[{'file':'a.tex','line_start':1,'line_end':1,'before':huge,'after':huge+'new'}]}
    writing_records.bank(tmp_path,{'record':'writing-reply','id':'WR-list','turn_id':'WT-list','session_id':'WS-list','project':'fixture','text':json.dumps(proposal),'proposal':proposal})
    page=session_reads.session_state(tmp_path,'WS-list',view='summary')
    assert huge not in json.dumps(page)
    assert page['turns'][0]['proposal_edit_count']==1
    exact=session_reads.session_turn_detail(tmp_path,'fixture','WT-list','turn')
    assert exact['turn']['reply']['proposal']['edits'][0]['before']==huge
    from laplace.manuscript.manuscript_proposals import proposal_version
    assert exact['turn']['proposal_version']==proposal_version(session_reads._records(tmp_path)['turns']['WT-list'])[0]


def test_compact_framing_reuses_raw_state_detaches_returns_and_separates_feedback(tmp_path,monkeypatch):
    path,rows=_mixed(tmp_path,monkeypatch);authoring._HISTORY_CACHE.clear()
    raw=json.loads(path.read_text());raw.update(argument='Raw premise.',framing={'question':'Raw question.'},section_ids=['section-one'])
    path.write_text(json.dumps(raw));opened=[];read_text=Path.read_text
    def observed(file,*a,**k):
        if file==path:opened.append(file)
        return read_text(file,*a,**k)
    monkeypatch.setattr(Path,'read_text',observed)
    first=authoring.summary('fixture',tmp_path);second=authoring.summary('fixture',tmp_path)
    assert first==second and len(opened)==1  # Cold parse remains; unchanged read does not parse history.
    first['framing']['question']='Caller edit';first['section_ids'].append('caller-section')
    assert authoring.summary('fixture',tmp_path)==second and len(opened)==1
    retained=json.dumps(authoring._HISTORY_CACHE[str(path)][1])
    assert rows[0]['before'] not in retained and 'context_blobs' not in retained
    feedback=path.parent/'feedback'/'feedback.jsonl';feedback.parent.mkdir(exist_ok=True)
    feedback.write_text(json.dumps({'record':'note','id':'FB-new','by':'author','text':'New exact feedback.'})+'\n')
    assert authoring.summary('fixture',tmp_path)==second and len(opened)==1
    history=authoring.history('fixture',{'limit':25,'order':'newest'},tmp_path)
    assert any(row['id']=='FB-new' for row in history['items']) and len(opened)==2
    assert authoring.summary('fixture',tmp_path)==second and len(opened)==2
    raw.update(revision=8,argument='Changed premise.');raw['framing']['question']='Changed question.'
    authoring._write(path,raw)
    changed=authoring.summary('fixture',tmp_path)
    assert changed['revision']==8 and changed['argument']=='Changed premise.' and len(opened)==3


def test_framing_equal_size_replacement_missing_and_invalid_state_do_not_reuse_header(tmp_path,monkeypatch):
    path,_=_mixed(tmp_path,monkeypatch);authoring._HISTORY_CACHE.clear()
    raw={**authoring._blank('fixture'),'revision':1,'argument':'A'};path.write_text(json.dumps(raw))
    assert authoring.summary('fixture',tmp_path)['argument']=='A'
    replacement=path.with_name('replacement.json');replacement.write_text(json.dumps({**raw,'argument':'B'}))
    assert replacement.stat().st_size==path.stat().st_size;replacement.replace(path)
    assert authoring.summary('fixture',tmp_path)['argument']=='B'
    path.unlink();assert authoring.summary('fixture',tmp_path)['revision']==0
    path.write_text(json.dumps({**raw,'argument':'C'}));assert authoring.summary('fixture',tmp_path)['argument']=='C'
    path.write_text('not JSON')
    with pytest.raises(ValueError,match='unreadable'):authoring.summary('fixture',tmp_path)
    path.write_text(json.dumps({**raw,'schema_version':'laplace.authoring/unknown'}))
    with pytest.raises(ValueError):authoring.summary('fixture',tmp_path)


def test_framing_changed_read_retries_then_refuses_without_old_header(tmp_path,monkeypatch):
    path,_=_mixed(tmp_path,monkeypatch);authoring._HISTORY_CACHE.clear()
    raw={**authoring._blank('fixture'),'revision':1,'argument':'A'};path.write_text(json.dumps(raw))
    read_text=Path.read_text;calls=[];continual=False
    def racing(file,*a,**k):
        body=read_text(file,*a,**k)
        if file==path:
            calls.append(file)
            if len(calls)==1 or continual:
                changed=json.loads(body);changed['revision']+=1;changed['argument']=str(changed['revision'])
                file.write_text(json.dumps(changed))
        return body
    monkeypatch.setattr(Path,'read_text',racing)
    first=authoring.summary('fixture',tmp_path)
    assert first['revision']==2 and len(calls)==2
    path.write_text(json.dumps({**raw,'revision':3}));calls.clear();continual=True
    with pytest.raises(ValueError,match='CHANGED_INPUT'):authoring.summary('fixture',tmp_path)
    assert len(calls)==3
    continual=False;fresh=authoring.summary('fixture',tmp_path)
    assert fresh['revision']>3


def test_framing_cache_bounds_existing_root_and_path_lifetimes(tmp_path,monkeypatch):
    authoring._HISTORY_CACHE.clear()
    monkeypatch.setattr(authoring,'_state_path',lambda project,root,**kw:(Path(root)/project/'authoring.json',{}))
    def read(root,project):
        file=root/project/'authoring.json';file.parent.mkdir(parents=True,exist_ok=True)
        if not file.exists():file.write_text(json.dumps(authoring._blank(project)))
        return authoring.summary(project,root)
    base=tmp_path/'first-root'
    for i in range(70):assert read(base,str(i))['project']==str(i)
    assert len(authoring._HISTORY_CACHE)<=64
    for i in range(6):assert read(tmp_path/f'root-{i}','p')['project']=='p'
    roots={value[1]['_cache_root'] for value in authoring._HISTORY_CACHE.values()}
    assert len(roots)<=4 and str(base) not in roots
    assert read(base,'0')['project']=='0'  # Eviction changes cost, never canonical data.



def test_framing_storage_switch_and_unreadable_change_cannot_borrow_prior_header(tmp_path,monkeypatch):
    path,_=_mixed(tmp_path,monkeypatch);authoring._HISTORY_CACHE.clear()
    raw={**authoring._blank('fixture'),'argument':'Original storage.'};path.write_text(json.dumps(raw))
    assert authoring.summary('fixture',tmp_path)['argument']=='Original storage.'
    source={**authoring._source('fixture',tmp_path),'storage_dir':'other-storage','read_only':True}
    other=tmp_path/'other-storage'/'authoring.json';other.parent.mkdir()
    other.write_text(json.dumps({**raw,'argument':'New storage.'}))
    assert authoring.summary('fixture',tmp_path,_source=source)['argument']=='New storage.'
    other.write_text(json.dumps({**raw,'argument':'Unreadable new state.'}))
    read_text=Path.read_text
    def unavailable(file,*a,**k):
        if file==other:raise PermissionError('Controlled unavailable file')
        return read_text(file,*a,**k)
    monkeypatch.setattr(Path,'read_text',unavailable)
    with pytest.raises(ValueError,match='unreadable'):authoring.summary('fixture',tmp_path,_source=source)
    assert authoring.summary('fixture',tmp_path)['argument']=='Original storage.'



def test_framing_root_lru_tracks_latest_path_touch(tmp_path,monkeypatch):
    authoring._HISTORY_CACHE.clear()
    monkeypatch.setattr(authoring,'_state_path',lambda project,root,**kw:(Path(root)/project/'authoring.json',{}))
    def read(root,project):
        file=root/project/'authoring.json';file.parent.mkdir(parents=True,exist_ok=True)
        if not file.exists():file.write_text(json.dumps(authoring._blank(project)))
        return authoring.summary(project,root)
    first=tmp_path/'first';read(first,'older-path');read(first,'newer-path')
    others=[tmp_path/f'other-{i}' for i in range(3)]
    for root in others:read(root,'p')
    read(first,'newer-path')  # Its older path must not make this hot root oldest.
    read(tmp_path/'next','p')
    roots={value[1]['_cache_root'] for value in authoring._HISTORY_CACHE.values()}
    assert str(first) in roots and str(others[0]) not in roots and len(roots)==4
