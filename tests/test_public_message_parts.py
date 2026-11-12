"""Selected public-message reads: exact custody, presentation and existing doors only."""
import json
import sys
from collections.abc import Mapping
from urllib.parse import urlsplit,parse_qs

import pytest

from laplace import sdk
from laplace.core import bodies,identity
from laplace.writing import records,session_reads as S,session_projection as P,tool_sessions,turn_context
from laplace.representation import writing_bodies
from laplace.web import authoring_http
from laplace.native import tools
from laplace.projects import library


def retain(root,value):
    raw=bodies.encode(value)
    return bodies.reference(writing_bodies.store(root).put(raw),writing_bodies.STORE,len(raw))


@pytest.fixture
def public(tmp_path):
    assert library.create({'name':'book','kind':'book','title':'Public message fixture'},tmp_path)[0]==201
    for sid in ('WS-a','WS-b'):
        records.bank(tmp_path,{'record':'writing-session','id':sid,'project':'book','role':'author'})
    for tid,sid in (('WT-a','WS-a'),('WT-current','WS-a'),('WT-b','WS-b')):
        records.bank(tmp_path,{'record':'writing-turn','id':tid,'session_id':sid,'project':'book','text':'PUBLIC '+tid,'mode':'work'})
    return tmp_path


def request(part='request',**kw):
    return {'project':'book','session_id':'WS-a','turn_id':'WT-a','part':part,**kw}


def http(root,handle):
    url=urlsplit(handle['http']['url'])
    status,_,raw=authoring_http.handle(root,url.path,parse_qs(url.query),'GET',b'')
    return status,json.loads(raw)


def replace_row(root,ident,**fields):
    path=root/'contract/talk.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        if row.get('id')==ident:row.update(fields)
    path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))


def test_short_unicode_and_exact_http_sdk_native_handles_without_rich_fold(public,monkeypatch):
    root=public;text='é中🌱e\u0301'+'x'*117
    assert len(text)==122
    replace_row(root,'WT-a',text=text)
    records.bank(root,{'record':'writing-reply','id':'WR-a','turn_id':'WT-a','session_id':'WS-a','project':'book','text':'PUBLIC REPLY'})
    real_fold=records.fold_records
    monkeypatch.setattr(records,'fold_records',lambda *_a,**_k:pytest.fail('Rich fold reached'))
    monkeypatch.setattr(S,'_records',lambda *_a,**_k:pytest.fail('Rich session fold reached'))
    value=S.public_message(root,request())
    assert value['content']==text and value['complete'] and value['limit']==2000
    assert value['total_characters']==122 and value['total_utf8_bytes']==len(text.encode())>122
    assert value['content_sha256']==identity.bytes_digest(text.encode())
    assert value['basis']!=value['content_sha256']!=value['source_row_sha256']
    assert http(root,value['page_read'])==(200,value)
    assert sdk.conversation_message(value['page_read']['sdk']['payload'],root=root)==value
    native=value['page_read']['native']
    # The native door's effect fence (workflow_progression.admit_operation, unchanged at d9b376f8) resolves the acting
    # turn's workflow context through the rich fold before any operation runs. That fence is not the message owner: the
    # owner stays fold-free (S._records stays forbidden) and the only fold permitted here is the fence's own.
    fences=[]
    def fence_fold(*a,**k):
        fences.append(sys._getframe(1).f_code.co_name);return real_fold(*a,**k)
    monkeypatch.setattr(records,'fold_records',fence_fold)
    got=tools.execute(root,'book','work',native['operation'],native['payload'],turn_id='WT-current')
    assert got['content']==text and got['basis']==value['basis']
    assert fences and set(fences)=={'admit_operation'}, fences
    monkeypatch.setattr(records,'fold_records',lambda *_a,**_k:pytest.fail('Rich fold reached'))
    reply=S.public_message(root,request('reply'))
    assert reply['content']=='PUBLIC REPLY' and reply['complete'] and reply['limit']==4000
    help_value=tools.help_response(root,'book','work',{'operation':'conversation_history'},turn_id='WT-current')
    assert 'expected_basis' in json.dumps(help_value) and 'message' in json.dumps(help_value)
    (root/'short-door-proof.json').write_text(json.dumps({'owner':value,'native_content':got['content'],
        'native_basis':got['basis'],'reply':reply,'message_owner_rich_fold_calls':0,'admission_fence_folds':len(fences),'actual_provider_calls':0},indent=2))


def test_long_unicode_pages_are_exact_contiguous_and_pinned(public):
    root=public;text=('é中🌱e\u0301\n```python\nprint("selected")\n```\nhttps://example.test/long/path\n'*210)+'TAIL_MARKER'
    replace_row(root,'WT-a',text=retain(root,text))
    value=S.public_message(root,request(limit=997));pages=[value];joined=value['content']
    while value['next_read']:
        status,value=http(root,value['next_read']);assert status==200
        assert value['basis']==pages[0]['basis'] and value['offset']==pages[-1]['end']
        assert value['content_sha256']==pages[0]['content_sha256']
        pages.append(value);joined+=value['content']
    assert joined==text and joined.endswith('TAIL_MARKER') and len(pages)>2
    assert all(page['page_utf8_bytes']==len(page['content'].encode()) for page in pages)
    assert S.public_message(root,request(limit=40000))['complete']
    assert not pages[0]['complete'] and pages[-1]['next_read'] is None
    (root/'long-page-proof.json').write_text(json.dumps({'pages':[{'offset':p['offset'],'end':p['end'],
        'page_utf8_bytes':p['page_utf8_bytes'],'basis':p['basis']} for p in pages],
        'total_characters':len(text),'total_utf8_bytes':len(text.encode()),'joined_sha256':identity.bytes_digest(joined.encode()),
        'exact_tail_retained':True},indent=2))


def test_changed_row_same_text_pin_refuses_and_explicit_restart_requalifies(public):
    root=public;first=S.public_message(root,request(limit=3))
    replace_row(root,'WT-a',ts='new captured row; text unchanged')
    status,refused=http(root,first['next_read'])
    assert status==409 and 'content' not in refused
    detail=refused['message_refusal'];assert detail['code']=='CHANGED_MESSAGE'
    status,current=http(root,detail['restart_read']);assert status==200
    assert current['content_sha256']==first['content_sha256'] and current['basis']!=first['basis']
    assert current['source_row_sha256']!=first['source_row_sha256']
    different=S.public_message(root,request(turn_id='WT-current'))
    with pytest.raises(S.MessagePartRefusal):S.public_message(root,request(turn_id='WT-current',expected_basis=first['basis']))
    assert different['basis']!=first['basis']
    (root/'changed-row-proof.json').write_text(json.dumps({'first':first,'refusal':refused,'explicit_restart':current},indent=2))


def test_absent_reply_stays_absent_even_with_saved_proposal(public):
    root=public
    records.bank(root,{'record':'writing-proposal','id':'PROP-a','turn_id':'WT-a','session_id':'WS-a','project':'book',
        'proposal':{'answer':'Not a final reply','edits':[]}})
    value=S.public_message(root,request('reply'))
    assert value['state']=='ABSENT' and value['reason']=='NO_SAVED_REPLY' and value['content'] is None
    assert value['basis'] is None and value['page_read'] is None and value['next_read'] is None
    with pytest.raises(S.MessagePartRefusal):S.public_message(root,request('reply',expected_basis='sha256:'+'a'*64))


@pytest.mark.parametrize('reply,text,origin',[
    ({'display_text':'','proposal':{'answer':'IGNORE'},'text':'IGNORE'},'','display_text'),
    ({'display_text':'DISPLAY','proposal':{'answer':'IGNORE'},'text':'IGNORE'},'DISPLAY','display_text'),
    ({'proposal':{'answer':'AUTHORED','edits':[{}]},'text':'{"edits":[{}]}'},'AUTHORED','proposal.answer'),
    ({'proposal':{'answer':{'invalid':'answer'}},'text':'PLAIN'},'PLAIN','text'),
    ({'text':'{"edits":[{"before":"RAW","after":"EDIT"}]}'},'Proposed manuscript changes are available for review.','structured-edit-fallback'),
    # The baseline expectation here claimed proposed changes for an empty edits list: the observed defect.
    ({'text':'```json\n{"proposal":{"edits":[]}}\n```'},'','structured-empty'),
    ({'text':'{"edits":[{}]}'},'','structured-empty'),
    ({'text':'{"edits":[]}','error':'PUBLIC ERROR'},'PUBLIC ERROR','error'),
    ({'text':'{"answer":"Refused: the y-values have mean 3.","edits":[]}'},'Refused: the y-values have mean 3.','structured.answer'),
    ({'text':'{"answer":"Replaced one sentence.","edits":[{"before":"RAW","after":"EDIT"}]}'},'Replaced one sentence.','structured.answer'),
    ({'text':'```json\n{"answer":"Fenced é中🌱","edits":[]}\n```'},'Fenced é中🌱','structured.answer'),
    ({'text':'{"proposal":{"answer":"Nested answer","edits":[]}}'},'Nested answer','structured.answer'),
    ({'text':'{"answer":"","edits":[{"before":"RAW","after":"EDIT"}]}'},'Proposed manuscript changes are available for review.','structured-edit-fallback'),
    ({'proposal':{'answer':'AUTHORED'},'text':'{"answer":"RAW ANSWER","edits":[]}'},'AUTHORED','proposal.answer'),
    ({'display_text':'','text':'{"answer":"RAW ANSWER","edits":[]}'},'','display_text'),
    ({'text':'{"answer":"unterminated","edits":['},'{"answer":"unterminated","edits":[','text'),
    ({'text':'{"result":"plain JSON"}'},'{"result":"plain JSON"}','text'),
    ({'status':'interrupted','text':'PARTIAL'},'PARTIAL','text'),
    ({'error':'PUBLIC ERROR'},'PUBLIC ERROR','error'),
])
def test_shared_public_presentation_precedence_summary_history_and_owner(public,reply,text,origin):
    root=public
    records.bank(root,{'record':'writing-reply','id':'WR-a','turn_id':'WT-a','session_id':'WS-a','project':'book',**reply})
    assert P.reply_presentation(reply)=={'text':text,'origin':origin}
    assert S.public_message(root,request('reply'))['content']==text
    saved=records.fold_records(root)
    summary=S._session_turn_summary(saved['turns']['WT-a'],saved,bounded=True)
    assert summary['reply']['display_text']==text or summary['reply'].get('display_text_truncated')
    history=tool_sessions.conversation_history(root,'book',{'limit':6},'WT-current')
    assert next(row['answer'] for row in history['turns'] if row['id']=='WT-a')==text
    migration=turn_context._migration_history(saved,'WS-a')
    assert json.dumps(text,ensure_ascii=False) in migration


def test_only_presentation_dependency_bodies_open_not_context_edits_or_other_history(public,monkeypatch):
    root=public
    irrelevant=retain(root,'UNRELATED_CONTEXT_EDIT_OR_TOOL\n'*15000)
    raw_text=retain(root,'UNUSED RAW REPLY\n'*5000)
    answer=retain(root,'EXACT SELECTED ANSWER é中🌱')
    proposal=retain(root,{'answer':answer,'edits':irrelevant,'extra':irrelevant})
    replace_row(root,'WT-a',workspace_context=irrelevant,dependencies=irrelevant)
    replace_row(root,'WT-b',text=irrelevant)
    records.bank(root,{'record':'writing-reply','id':'WR-a','turn_id':'WT-a','session_id':'WS-a','project':'book',
        'text':raw_text,'proposal':proposal,'provider_issues':irrelevant})
    reads=[];original=writing_bodies.read_bytes
    def measured(ref,*a,**kw):reads.append(ref['content_handle']);return original(ref,*a,**kw)
    monkeypatch.setattr(writing_bodies,'read_bytes',measured)
    monkeypatch.setattr(S,'_records',lambda *_a,**_k:pytest.fail('Rich fold reached'))
    with bodies.budget() as cost:value=S.public_message(root,request('reply'))
    assert value['content']=='EXACT SELECTED ANSWER é中🌱'
    assert reads==[proposal['content_handle'],answer['content_handle']]
    assert value['presentation_dependencies']==['proposal','proposal.answer']
    assert cost['reads']==2
    (root/'selective-body-proof.json').write_text(json.dumps({'value':value,'actual_body_reads':reads,
        'forbidden_body_refs':[irrelevant,raw_text],'budget':cost,'unrelated_bodies_opened':0},indent=2))


def test_native_message_fence_and_closed_validation_do_not_adopt_child_control_exception(public):
    root=public;value=S.public_message(root,request());native=value['page_read']['native']
    for caller in ('WT-b',None):
        with pytest.raises(ValueError):tools.execute(root,'book','work',native['operation'],native['payload'],turn_id=caller)
    records.bank(root,{'record':'writing-session','id':'WS-child','project':'book','role':'review','dispatch_id':'WORK-public'})
    records.bank(root,{'record':'writing-turn','id':'WT-child','session_id':'WS-child','parent_turn_id':'WT-current','project':'book','text':'CHILD'})
    child=S.public_message(root,request(session_id='WS-child',turn_id='WT-child'))
    with pytest.raises(ValueError):tools.execute(root,'book','work','conversation_history',child['page_read']['native']['payload'],turn_id='WT-current')
    for change in ({'project':'foreign'},{'session_id':'WS-b'},{'turn_id':'WT-b'},{'part':'context'},
                   {'offset':True},{'limit':40001},{'limit':False},{'offset':-1},{'expected_basis':'X'*10000},{'pointer':'/context'}):
        with pytest.raises(ValueError):S.public_message(root,request(**change))
    raw=urlsplit(value['page_read']['http']['url']);query=parse_qs(raw.query);query['part']=['request','reply']
    status,_,_=authoring_http.handle(root,raw.path,query,'GET',b'');assert status==409


def test_unavailable_selected_body_and_ambiguous_reply_do_not_claim_complete(public):
    root=public;selected=retain(root,'EXACT SELECTED REQUEST')
    replace_row(root,'WT-a',text={**selected,'bytes':selected['bytes']+1})
    with pytest.raises(ValueError):S.public_message(root,request())
    replace_row(root,'WT-a',text=selected)
    for ident in ('WR-one','WR-two'):
        records.bank(root,{'record':'writing-reply','id':ident,'turn_id':'WT-a','session_id':'WS-a','project':'book','text':'SAME'})
    with pytest.raises(ValueError,match='ambiguous'):S.public_message(root,request('reply'))


def test_actual_verb_door_preserves_message_pin_refusal_and_legacy_namespace(public):
    from laplace.native import verbs
    root=public
    records.bank(root,{'record':'writing-reply','id':'WR-legacy','turn_id':'WT-a','project':None,'session_id':None,'text':'PUBLIC LEGACY'})
    value=S.public_message(root,request('reply'));native=value['page_read']['native']
    classified=verbs.classify(native['operation'],native['payload'],project='book',root=root)
    assert classified.exact and classified.verb_door and classified.owner_call==(native['operation'],native['payload'])
    result=tools.request(root,'book','work',classified.request,turn_id='WT-current')
    assert result['outcome']=='read' and result['owner_response']['basis']==value['basis']
    replace_row(root,'WR-legacy',ts='changed source row only')
    refused=tools.request(root,'book','work',classified.request,turn_id='WT-current')
    assert refused['ok'] is False and refused['message_refusal']['code']=='CHANGED_MESSAGE'
    assert 'content' not in refused
    status,restarted=http(root,refused['message_refusal']['restart_read'])
    assert status==200 and restarted['content']=='PUBLIC LEGACY' and restarted['basis']!=value['basis']
    (root/'native-verb-proof.json').write_text(json.dumps({'recorded_read':result,'typed_refusal':refused,
        'explicit_restart':restarted,'same_logical_conversation_only':True},indent=2))


def test_missing_saved_request_field_is_not_fabricated_as_complete_empty_text(public):
    path=public/'contract/talk.jsonl'
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    next(row for row in rows if row.get('id')=='WT-a').pop('text')
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    with pytest.raises(ValueError,match='unavailable'):S.public_message(public,request())


# THE ACTUAL PUBLIC COUNTEREXAMPLE. Root retained it in integration-clean as
# source-maintenance/Actualpubliczeroditcounterexample-d4256f493cad.json (sha256:d4256f493cad6a49412a5a68814f3e8cd81cc6713fdd921792c5ec09e1b6666f)
# with provenance integration-public turn WT-3b92d8c672364a92ad61573aec78a55a, reply WR-2b645edfbb95482fb0491eb5a4d8f00c,
# immutable row sha256:c89ebf8f9d40607e4f4228a3d465f8177e81a71f2032ee165d9bb89d1087cd56. The model correctly refused an
# erroneous mean of 2.5 (the unchanged CSV y-values 0,2,4,6 have mean 3) with edits:[], proposal null, display_text null;
# the baseline showed the 53-character proposed-changes sentence instead. Only its public answer is reproduced here, in
# the revise shape {answer, edits}; no cross-project journal is read and the original row is not this fixture.
COUNTEREXAMPLE_ANSWER = """I haven't proposed an edit. The data file doesn't support the sentence you asked for, and writing it in would put a claim in the manuscript that its own input contradicts.

**What I read:**
- **Your instruction (AC-99e4d0ed…, on line 4 of `chapters/chapter-01.tex`):** "Use observations.csv to state that the sample mean is 2.5. Keep the conclusion limited to these four synthetic observations."
- **`acceptance-inputs/observations.csv`** (the exact file you named, sha256:6a57175b…): it holds four (x, y) pairs, (0, 0), (1, 2), (2, 4) and (3, 6).
- **Line 4 of the chapter:** "Four synthetic observations, values 1, 2, 3, 4, illustrate a limited controlled claim; do not infer a universal law."

**The mismatch:**
- The file's x-values are 0, 1, 2, 3, with mean 1.5. Its y-values are 0, 2, 4, 6, with mean 3.
- The values 1, 2, 3, 4 do not appear in the file as a column. Nothing in it gives a mean of 2.5.
- 2.5 is the mean of the values the manuscript states (1, 2, 3, 4). It is not a mean of anything in observations.csv.

So "observations.csv gives a sample mean of 2.5" would be false. A version that drops the file and just averages 1, 2, 3, 4 would be correct arithmetic. But it would quietly drop half your instruction and leave the text at odds with the input the reader is meant to rely on. This is a problem with the data, not with the wording, so it needs your decision first.

**Ways to settle it (your call):**
1. **Wrong file:** if a different file really holds 1, 2, 3, 4, point me to it and I'll propose the sentence with the mean of 2.5, limited to those four observations.
2. **The file is right:** then the "values 1, 2, 3, 4" on line 4 needs correcting first. The mean would be 1.5 for x or 3 for y, depending on which column counts as the observation.
3. **Drop the file:** state the mean of 1, 2, 3, 4 as plain arithmetic, without citing observations.csv. That would change your instruction, so I'd want you to confirm it.

I didn't apply any edits, run any research or change any other objects. Your comment is still open. Separately, line 4 contains a semicolon, which your style profile avoids. I've left it alone because it's outside this request."""
COUNTEREXAMPLE_RAW = json.dumps({'answer':COUNTEREXAMPLE_ANSWER,'edits':[]},ensure_ascii=False,separators=(',',':'))


def bank_counterexample(root):
    records.bank(root,{'record':'writing-reply','id':'WR-zero-edit','turn_id':'WT-a','session_id':'WS-a','project':'book',
        'status':'completed','text':COUNTEREXAMPLE_RAW,'edits':[],'proposal':None,'display_text':None})


def baseline_presentation(reply):
    """reply_presentation exactly as at d9b376f8 (the owner that produced the observed defect), for basis comparison only."""
    reply=reply or {}
    displayed=reply.get('display_text')
    if displayed is not None:return {'text':str(displayed),'origin':'display_text'}
    proposal=reply.get('proposal')
    answer=proposal.get('answer') if isinstance(proposal,Mapping) else None
    if isinstance(answer,str) and answer:return {'text':answer,'origin':'proposal.answer'}
    text=reply.get('text')
    if isinstance(text,str):
        raw=text.strip()
        if raw.startswith('```') and raw.endswith('```'):
            raw=raw.partition('\n')[2].rsplit('```',1)[0]
        try:structured=json.loads(raw)
        except (TypeError,ValueError):structured=None
        if isinstance(structured,Mapping) and (isinstance(structured.get('edits'),list)
                or isinstance(structured.get('proposal'),Mapping) and isinstance(structured['proposal'].get('edits'),list)):
            return {'text':'Proposed manuscript changes are available for review.','origin':'structured-edit-fallback'}
    if text:return {'text':str(text),'origin':'text'}
    error=reply.get('error')
    return {'text':str(error or ''),'origin':'error' if error else 'empty'}


def test_actual_zero_edit_refusal_presents_its_answer_in_every_consumer_and_stales_the_old_basis(public,monkeypatch):
    root=public;bank_counterexample(root)
    journal=root/'contract/talk.jsonl';saved_bytes=journal.read_bytes()
    monkeypatch.setattr(P,'reply_presentation',baseline_presentation)
    old=S.public_message(root,request('reply',limit=20))
    monkeypatch.undo()
    assert old['presentation_origin']=='structured-edit-fallback' and old['total_characters']==53 and old['next_read']
    assert P.reply_presentation({'text':COUNTEREXAMPLE_RAW,'edits':[],'proposal':None,'display_text':None})=={
        'text':COUNTEREXAMPLE_ANSWER,'origin':'structured.answer'}
    status,refused=http(root,old['next_read'])
    assert status==409 and refused['message_refusal']['code']=='CHANGED_MESSAGE' and 'content' not in refused
    status,restarted=http(root,refused['message_refusal']['restart_read'])
    assert status==200 and restarted['offset']==0 and COUNTEREXAMPLE_ANSWER.startswith(restarted['content'])
    current=S.public_message(root,request('reply',limit=40000))
    assert current['complete'] and current['content']==COUNTEREXAMPLE_ANSWER and current['presentation_origin']=='structured.answer'
    assert 'with mean 3.' in current['content'] and P.STRUCTURED_EDIT_FALLBACK not in current['content']
    assert current['basis']!=old['basis'] and current['source_row_sha256']==old['source_row_sha256'], 'same saved row; only its presentation changed'
    assert journal.read_bytes()==saved_bytes, 'no consumer rewrites the saved reply row'
    saved=records.fold_records(root)
    single=S._session_turn_summary(saved['turns']['WT-a'],saved)
    assert single['reply']['display_text']==COUNTEREXAMPLE_ANSWER and single['reply']['text']==COUNTEREXAMPLE_ANSWER
    row=S._session_turn_summary(saved['turns']['WT-a'],saved,bounded=True)
    assert COUNTEREXAMPLE_ANSWER.startswith(row['reply']['display_text']) and row['reply']['display_text_chars']==len(COUNTEREXAMPLE_ANSWER)
    history=tool_sessions.conversation_history(root,'book',{'limit':6},'WT-current')
    answer=next(item['answer'] for item in history['turns'] if item['id']=='WT-a')
    assert answer.startswith("I haven't proposed an edit.") and P.STRUCTURED_EDIT_FALLBACK not in answer
    migration=turn_context._migration_history(saved,'WS-a')
    assert "I haven't proposed an edit." in migration and P.STRUCTURED_EDIT_FALLBACK not in migration
    assert journal.read_bytes()==saved_bytes
