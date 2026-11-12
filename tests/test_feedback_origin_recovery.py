"""Quote custody and explicit original-request settlement; no provider effects."""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from test_feedback_origin import fixture, rows
from laplace.pipeline import authoring, correction_origin
from laplace.manuscript import manuscript_bridge
from laplace.core import identity_doors


MATH_LINE='The file \\texttt{observations.csv} contains $(x,y) = (0,0)$ and $(1,2)$ only.'


def retain(name,value):
    import os
    from pathlib import Path
    home=os.environ.get('COMMENT_MAPPING_EVIDENCE')
    if home:
        path=Path(home);path.mkdir(parents=True,exist_ok=True)
        (path/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2))


def math_fixture(tmp_path):
    payload=fixture(tmp_path)
    path=tmp_path/'p/manuscript/main.tex'
    path.write_bytes(path.read_bytes().replace(b'A numerical claim requires a stated assumption.',MATH_LINE.encode()))
    expected=list(identity_doors.identities(('prose','p::main.tex:3-3',MATH_LINE.encode())).values())
    return payload,path,expected


def selection(kind,start,end,display):
    return {'schema':correction_origin.SELECTION,'kind':kind,'units':'unicode-codepoints','start':start,'end':end,
            'display_quote':display}


def test_rendered_math_paragraph_whole_source_target_prepares_saves_once_and_reinspects(tmp_path):
    """The actual texttt/math paragraph: its rendered face is refused as a quote, while the typed whole-block raw
    target is owner-qualified at prepare, save and inspect; the raw source is unchanged and the replay saves nothing."""
    payload,path,expected=math_fixture(tmp_path)
    rendered='The file observations.csv contains (x,y)=(0,0) and (1,2) only.'
    base={'file':'main.tex','line_start':3,'line_end':3}
    with pytest.raises(ValueError,match='Displayed quote'):
        authoring.prepare_correction('p',{'anchor':{**base,'quote':rendered},'expected':expected},tmp_path)
    whole=selection('whole-block',0,len(MATH_LINE),rendered)
    prepared=authoring.prepare_correction('p',{'anchor':{**base,'source_selection':whole},'expected':expected},tmp_path)
    assert prepared['anchor']['quote']==MATH_LINE and prepared['anchor']['source_selection']==whole
    assert prepared['source_basis']['source_quote']==MATH_LINE
    raw=path.read_bytes();wire={**payload,**{key:prepared[key] for key in ('anchor','source_basis','base_revision')}}
    saved=authoring.bank_correction('p',wire,tmp_path)
    assert saved['effect']=='RECORDED' and path.read_bytes()==raw
    assert saved['correction']['anchor']['source_selection']==whole and saved['correction']['anchor']['quote']==MATH_LINE
    inspected=authoring.correction_origin('p',saved['origin_ref'],tmp_path)
    assert inspected['currentness']['state']=='CURRENT' and inspected['correction']['anchor']['source_selection']['display_quote']==rendered
    replay=authoring.bank_correction('p',wire,tmp_path)
    assert replay['origin_ref']==saved['origin_ref'] and sum('comment' in row for row in rows(tmp_path,payload))==1
    from laplace.manuscript import walk
    retain('owner-mapping',{'line':MATH_LINE,'pieces':walk.tex_pieces(MATH_LINE),'rendered':rendered,
        'prepared':prepared,'saved':saved,'inspected':inspected})


def test_piece_span_selection_is_exact_and_atomic_stale_or_tampered_mappings_refuse(tmp_path):
    from laplace.manuscript import walk
    payload,path,expected=math_fixture(tmp_path)
    pieces=walk.tex_pieces(MATH_LINE);kinds=[piece['t'] for piece in pieces]
    assert kinds==['text','code','text','math','text','math','text']
    base={'file':'main.tex','line_start':3,'line_end':3};contains,math=pieces[2],pieces[3]
    lo,hi=contains['o_start']+1,math['o_end']
    span=selection('piece-span',lo,hi,'contains (x,y)=(0,0)')
    prepared=authoring.prepare_correction('p',{'anchor':{**base,'source_selection':span},'expected':expected},tmp_path)
    assert prepared['anchor']['quote']==MATH_LINE[lo:hi]=='contains $(x,y) = (0,0)$'
    refusals={}
    for name,anchor,match in [
        ('inside-math',{**base,'source_selection':selection('piece-span',lo,math['o_start']+3,'contains (x')},'inside a math'),
        ('inside-code',{**base,'source_selection':selection('piece-span',pieces[1]['o_start']+2,contains['o_end'],'x')},'inside a math'),
        ('out-of-range',{**base,'source_selection':selection('piece-span',lo,len(MATH_LINE)+4,'x')},'outside the inspected'),
        ('short-whole',{**base,'source_selection':selection('whole-block',0,len(MATH_LINE)-1,'x')},'complete inspected'),
        ('quote-mismatch',{**base,'quote':'contains (x,y)','source_selection':span},'differs from its qualified'),
        ('unknown-units',{**base,'source_selection':{**span,'units':'utf16'}},'closed origin contract')]:
        with pytest.raises(ValueError,match=match) as caught:
            authoring.prepare_correction('p',{'anchor':anchor,'expected':expected},tmp_path)
        refusals[name]=str(caught.value)
    wire={**payload,**{key:prepared[key] for key in ('anchor','source_basis','base_revision')}}
    tampered={**wire,'anchor':{**wire['anchor'],'source_selection':{**span,'end':math['o_start']+2}}}
    with pytest.raises(ValueError,match='inside a math|differs from its qualified'):
        authoring.bank_correction('p',{**tampered,'request_id':'comment-tampered-1'},tmp_path)
    path.write_bytes(path.read_bytes().replace(b'only.',b'only, revised.'))
    with pytest.raises(ValueError,match='Raw source changed'):authoring.bank_correction('p',wire,tmp_path)
    assert not rows(tmp_path,payload)
    retain('owner-piece-span',{'line':MATH_LINE,'pieces':pieces,'selection':span,'prepared':prepared,'refusals':refusals})


GAP_CANDIDATES=['A \\emph{numerical}~claim keeps its bound.','A claim\\label{c:one} keeps its bound.',
                'A claim\\index{claim} keeps its bound.','A claim{} keeps its bound.']
ESCAPE_LINE='Half of runs keep 50\\% of the bound.'
LINE_BASE={'file':'main.tex','line_start':3,'line_end':3}


def line_fixture(tmp_path,line):
    payload=fixture(tmp_path)
    path=tmp_path/'p/manuscript/main.tex'
    path.write_bytes(path.read_bytes().replace(b'A numerical claim requires a stated assumption.',line.encode()))
    return payload,path,list(identity_doors.identities(('prose','p::main.tex:3-3',line.encode())).values())


def test_span_into_a_hidden_wrapper_or_across_undisplayed_source_refuses_while_exact_spans_prepare(tmp_path,monkeypatch):
    """Review 276bdce0 F4: the owner tokenizer gives every source character a piece; a hidden wrapper (here the empty
    group in 'claim{}', which displays nothing) is its own piece, so a span whose boundary falls inside it refuses. A
    tokenizer result that leaves source undisplayed between pieces refuses as such. Exact spans that cover the hidden
    wrapper whole still prepare to the raw text, braces included."""
    from laplace.manuscript import walk
    for line in GAP_CANDIDATES:
        pieces=walk.tex_pieces(line)
        assert all(right['o_start']<=left['o_end'] for left,right in zip(pieces,pieces[1:])),('the owner tokenizer leaves no undisplayed source',line,pieces)
    line='A claim{} keeps its bound.';pieces=walk.tex_pieces(line);brace=line.index('{}')
    wrapper=[piece for piece in pieces if piece['t']=='group' and not piece.get('pieces')]
    assert wrapper and (wrapper[0]['o_start'],wrapper[0]['o_end'])==(brace,brace+2),('the empty group is its own hidden piece',pieces)
    payload,path,expected=line_fixture(tmp_path,line)
    refusals={}
    for name,lo,hi in [('ends-inside-hidden-wrapper',2,brace+1),('starts-inside-hidden-wrapper',brace+1,brace+8)]:
        with pytest.raises(ValueError,match='inside a math, citation or macro piece') as caught:
            authoring.prepare_correction('p',{'anchor':{**LINE_BASE,'source_selection':selection('piece-span',lo,hi,'x')},
                                             'expected':expected},tmp_path)
        refusals[name]=str(caught.value)
    exact=authoring.prepare_correction('p',{'anchor':{**LINE_BASE,'source_selection':selection('piece-span',2,brace+8,'claim keeps')},
                                           'expected':expected},tmp_path)
    assert exact['anchor']['quote']=='claim{} keeps'
    # The gap branch: a tokenizer result in which the hidden wrapper has no piece (its source is not displayed).
    original,hidden=walk.tex_pieces,[piece for piece in pieces if piece is not wrapper[0]]
    monkeypatch.setattr(walk,'tex_pieces',lambda raw:copy.deepcopy(hidden) if raw==line else original(raw))
    with pytest.raises(ValueError,match='spans source that is not displayed') as caught:
        authoring.prepare_correction('p',{'anchor':{**LINE_BASE,'source_selection':selection('piece-span',2,brace+8,'claim keeps')},
                                         'expected':expected},tmp_path)
    refusals['across-undisplayed-source']=str(caught.value)
    monkeypatch.undo()
    assert not rows(tmp_path,payload)
    retain('owner-hidden-wrapper',{'line':line,'pieces':pieces,'refusals':refusals,'prepared':exact['anchor']})


def test_span_boundary_on_an_escape_backslash_refuses_while_exact_text_prepares(tmp_path):
    """Review 276bdce0 F4: a span that ends on, or starts just after, a TeX escape backslash inside displayed text is not
    a deterministic source position; an exact span of plain displayed text in the same line prepares."""
    from laplace.manuscript import walk
    payload,path,expected=line_fixture(tmp_path,ESCAPE_LINE)
    pieces=walk.tex_pieces(ESCAPE_LINE);slash=ESCAPE_LINE.index('\\')
    holder=[piece for piece in pieces if piece['o_start']<=slash<piece['o_end']]
    assert holder and holder[0]['t']=='text' and holder[0]['o_end']>slash+1,('the escape sits inside one displayed text piece',pieces)
    holder=holder[0];refusals={}
    for name,lo,hi in [('ends-on-backslash',holder['o_start'],slash+1),('starts-after-backslash',slash+1,holder['o_end'])]:
        with pytest.raises(ValueError,match='not a deterministic source position') as caught:
            authoring.prepare_correction('p',{'anchor':{**LINE_BASE,'source_selection':selection('piece-span',lo,hi,'x')},
                                             'expected':expected},tmp_path)
        refusals[name]=str(caught.value)
    word=ESCAPE_LINE.index('of runs')
    exact=authoring.prepare_correction('p',{'anchor':{**LINE_BASE,'source_selection':selection('piece-span',word,word+len('of runs'),'of runs')},
                                           'expected':expected},tmp_path)
    assert exact['anchor']['quote']=='of runs'
    assert not rows(tmp_path,payload)
    retain('owner-escape-boundary',{'line':ESCAPE_LINE,'pieces':pieces,'refusals':refusals,'prepared':exact['anchor']})


def settlement(payload):
    return {'project':'p','request_id':payload['request_id'],'ledger':payload['source_basis']['ledger'],
            'submission':copy.deepcopy(payload)}


def test_quote_prepare_reuse_and_valid_partial_controlled_prose(tmp_path):
    payload=fixture(tmp_path)
    with pytest.raises(ValueError,match='Displayed quote'):
        authoring.prepare_correction('p',{**{k:payload[k] for k in ('source_basis','base_revision')},
            'anchor':{**payload['anchor'],'quote':'Outside this inspected extent'}},tmp_path)
    path=tmp_path/'p/manuscript/main.tex'
    source='A \\emph{numerical}~claim requires a stated assumption.'
    raw=path.read_bytes().replace(b'A numerical claim requires a stated assumption.',source.encode())
    path.write_bytes(raw)
    expected=list(identity_doors.identities(('prose','p::main.tex:3-3',source.encode())).values())
    anchor={'file':'main.tex','line_start':3,'line_end':3,'quote':'numerical  claim'}
    with pytest.raises(ValueError,match='Displayed quote'):
        authoring.prepare_correction('p',{'anchor':{**anchor,'quote':'Fabricated statement'},'expected':expected},tmp_path)
    prepared=authoring.prepare_correction('p',{'anchor':anchor,'expected':expected},tmp_path)
    assert prepared['anchor']['quote']==anchor['quote']
    saved=authoring.bank_correction('p',{**payload,**{k:prepared[k] for k in
        ('anchor','source_basis','base_revision')}},tmp_path)
    assert authoring.correction_origin('p',saved['origin_ref'],tmp_path)['currentness']['state']=='CURRENT'
    (tmp_path/'quote-partial-proof.json').write_text(json.dumps({'prepared':prepared,'saved':saved},ensure_ascii=False))


def test_source_refusal_settlement_then_explicit_new_selection_creates_one_comment(tmp_path):
    payload=fixture(tmp_path)
    path=tmp_path/'p/manuscript/main.tex'
    quote='A revised numerical claim keeps its boundary explicit.'
    path.write_bytes(path.read_bytes().replace(b'A numerical claim requires a stated assumption.',quote.encode()))
    with pytest.raises(ValueError,match='Raw source changed'):authoring.bank_correction('p',payload,tmp_path)
    terminal=authoring.settle_correction('p',settlement(payload),tmp_path)
    assert terminal['effect']=='NOT_ADMITTED' and terminal['terminal'] and terminal['receipt'] is None
    assert authoring.bank_correction('p',payload,tmp_path)==terminal
    expected=list(identity_doors.identities(('prose','p::main.tex:3-3',quote.encode())).values())
    prepared=authoring.prepare_correction('p',{'anchor':{'file':'main.tex','line_start':3,'line_end':3,
        'quote':'revised numerical claim'},'expected':expected,'request_id':'comment-public-2'},tmp_path)
    new={**payload,'request_id':'comment-public-2',**{k:prepared[k] for k in ('anchor','source_basis','base_revision')}}
    saved=authoring.bank_correction('p',new,tmp_path)
    assert saved['effect']=='RECORDED'
    raw=rows(tmp_path,payload)
    assert len(raw)==2 and sum(row.get('record')==correction_origin.SETTLEMENT_RECORD for row in raw)==1
    assert sum('comment' in row for row in raw)==1
    control=next(row for row in raw if row.get('record')==correction_origin.SETTLEMENT_RECORD)
    assert not {'comment','text','anchor','node_id'} & set(control)
    assert payload['text'] not in json.dumps(control,ensure_ascii=False)
    assert manuscript_bridge.feedback_list(tmp_path,'p',ledger=tmp_path/payload['source_basis']['ledger'])['n']==1
    assert [row['id'] for row in authoring.history('p',{},tmp_path)['items']]==[saved['correction']['id']]
    from laplace.writing import records
    from laplace.work.author_history_metrics import _feedback_metadata
    idx=records.index(tmp_path,path=payload['source_basis']['ledger'],extractor=_feedback_metadata)
    assert [row['id'] for row in idx.rows]==[saved['correction']['feedback_id']]
    with pytest.raises(ValueError,match='different intent'):
        authoring.bank_correction('p',{**payload,'text':'Changed intent'},tmp_path)
    with pytest.raises(ValueError,match='original request'):
        authoring.settle_correction('p',{**settlement(payload),'ledger':'p/other/feedback/feedback.jsonl'},tmp_path)
    (tmp_path/'settlement-readdress-proof.json').write_text(json.dumps(
        {'original_submission':payload,'terminal':terminal,'new_preparation':prepared,'saved':saved,'canonical_rows':raw},ensure_ascii=False))


def test_settlement_wins_after_save_last_read_without_delayed_comment_or_route(tmp_path,monkeypatch):
    from laplace.web import authoring_http
    from laplace.work import work_delivery
    payload={**fixture(tmp_path),'review_route':{'work_id':'PUBLIC-WORK'}}
    entered=threading.Event();release=threading.Event();real=manuscript_bridge.append_feedback_record;calls=[]
    def paused(path,row,**kwargs):
        if row.get('authoring_origin'):
            entered.set();assert release.wait(10)
        return real(path,row,**kwargs)
    monkeypatch.setattr(manuscript_bridge,'append_feedback_record',paused)
    monkeypatch.setattr(work_delivery,'compose_origin',lambda *a,**k:calls.append(1),raising=False)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(authoring_http.handle,tmp_path,'/authoring/correction',{},'POST',json.dumps(payload).encode())
        try:
            assert entered.wait(10)
            terminal=authoring.settle_correction('p',settlement(payload),tmp_path)
            assert terminal['effect']=='NOT_ADMITTED'
        finally:release.set()
        status,_,raw=future.result()
    assert status==200 and json.loads(raw)==terminal
    assert not calls and len(rows(tmp_path,payload))==1
    assert not authoring.load('p',tmp_path)['corrections']
    (tmp_path/'settlement-wins-proof.json').write_text(json.dumps({'terminal':terminal,'delayed_save':json.loads(raw)}))


def test_save_wins_before_state_write_and_settlement_keeps_original_origin(tmp_path,monkeypatch):
    payload=fixture(tmp_path);entered=threading.Event();release=threading.Event();real=authoring._write
    def paused(*args):
        entered.set();assert release.wait(10);return real(*args)
    monkeypatch.setattr(authoring,'_write',paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(authoring.bank_correction,'p',payload,tmp_path)
        try:
            assert entered.wait(10)
            settled=authoring.settle_correction('p',settlement(payload),tmp_path)
            assert settled['effect']=='RECORDED'
        finally:release.set()
        saved=future.result()
    assert settled['receipt']==saved and len(rows(tmp_path,payload))==1
    assert rows(tmp_path,payload)[0].get('record')!=correction_origin.SETTLEMENT_RECORD
    (tmp_path/'save-wins-proof.json').write_text(json.dumps({'saved':saved,'settled':settled},ensure_ascii=False))


@pytest.mark.parametrize('publication',['complete-lost-response','incomplete'])
def test_settlement_publication_is_reconciled_not_guessed(tmp_path,monkeypatch,publication):
    from laplace.web import authoring_http
    payload=fixture(tmp_path);real=manuscript_bridge._append_jsonl
    def broken(path,row,**kwargs):
        if publication=='complete-lost-response':real(path,row,**kwargs)
        else:
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{incomplete settlement\n')
        raise OSError('public settlement response lost')
    monkeypatch.setattr(manuscript_bridge,'_append_jsonl',broken)
    status,_,raw=authoring_http.handle(tmp_path,'/authoring/correction-settle',{},'POST',json.dumps(settlement(payload)).encode())
    assert status==500
    observed=authoring.correction_request('p',payload['request_id'],tmp_path,ledger=payload['source_basis']['ledger'])
    if publication=='complete-lost-response':
        assert observed['effect']=='NOT_ADMITTED' and observed['terminal']
        assert authoring.bank_correction('p',payload,tmp_path)==observed
    else:assert observed['effect']=='UNKNOWN' and not observed.get('terminal')
    (tmp_path/'settlement-publication-proof.json').write_text(json.dumps({'post_status':status,
        'post_raw':raw.decode(),'lookup':observed},ensure_ascii=False))


def test_invalid_optional_work_read_does_not_erase_recorded_origin(tmp_path,monkeypatch):
    from laplace.work import work_delivery
    payload={**fixture(tmp_path),'review_route':{'work_id':'PUBLIC-WORK'}}
    def read(project,ref,spec):
        return {'operation':'work_delivery','payload':{'action':'route-status','work_id':spec['work_id'],'origin':ref}}
    monkeypatch.setattr(work_delivery,'origin_route_read',read,raising=False)
    saved=authoring.bank_correction('p',payload,tmp_path)
    assert saved['review_route_read']['payload']['origin']==saved['origin_ref']
    monkeypatch.setattr(work_delivery,'origin_route_read',lambda *a:(_ for _ in ()).throw(ValueError('retained route is unavailable')))
    observed=authoring.settle_correction('p',settlement(payload),tmp_path)
    assert observed['effect']=='RECORDED' and observed['receipt']['review_route_read_unavailable']


def test_issued_settlement_action_and_read_match_actual_http_declaration(tmp_path):
    from laplace.web import authoring_http
    from laplace.native.declarations import HTTP_DECLARATIONS
    import laplace.web.writing_declared_http
    from jsonschema import Draft202012Validator
    from urllib.parse import urlsplit,parse_qs
    payload=fixture(tmp_path)
    observed=authoring.correction_request('p',payload['request_id'],tmp_path,ledger=payload['source_basis']['ledger'])
    action=observed['settle']['http'];wire={**action['body'],'submission':payload}
    assert not list(Draft202012Validator(HTTP_DECLARATIONS['authoring/correction-settle'].payload).iter_errors(wire))
    status,_,raw=authoring_http.handle(tmp_path,action['url'],{},action['method'],json.dumps(wire).encode())
    terminal=json.loads(raw)
    assert status==200 and terminal['effect']=='NOT_ADMITTED' and terminal['terminal']
    read=terminal['reconcile']['http'];url=urlsplit(read['url'])
    status,_,raw=authoring_http.handle(tmp_path,url.path,parse_qs(url.query),read['method'],b'')
    assert status==200 and json.loads(raw)==terminal
    (tmp_path/'issued-settlement-http-proof.json').write_text(json.dumps(
        {'action':action,'submitted':wire,'terminal':terminal,'reread':json.loads(raw)},ensure_ascii=False))


def test_origin_association_is_owner_intent_pure_and_refuses_foreign_or_changed_copies(tmp_path):
    import hashlib
    from laplace.web import authoring_http
    from laplace.native.declarations import HTTP_DECLARATIONS
    import laplace.web.writing_declared_http
    from jsonschema import Draft202012Validator
    from urllib.parse import urlsplit,parse_qs
    payload=fixture(tmp_path);ledger=payload['source_basis']['ledger']
    legacy=authoring.correction_request('p',payload['request_id'],tmp_path,ledger=ledger)
    assert legacy['effect']=='NONE' and 'association' not in legacy
    assert legacy['compare']['requires']==['submission'] and legacy['compare']['carrier']=='query-json' and legacy['compare']['kind']=='origin'
    intent=correction_origin._intent('p',payload)
    absent=authoring.correction_request('p',payload['request_id'],tmp_path,ledger=ledger,submission=json.dumps(payload))
    assert absent['association']=={'schema_version':correction_origin.ASSOCIATION,'kind':'origin','project':'p','context':ledger,
        'request_id':payload['request_id'],'state':'UNRECORDED','intent_sha256':intent}
    assert intent!='sha256:'+hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert not rows(tmp_path,payload)
    saved=authoring.bank_correction('p',payload,tmp_path)
    match=authoring.correction_request('p',payload['request_id'],tmp_path,ledger=ledger,submission=copy.deepcopy(payload))
    assert match['effect']=='RECORDED' and match['association']['state']=='MATCH' and match['receipt']['origin_ref']==saved['origin_ref']
    changed={**payload,'text':payload['text']+' Changed.'}
    mismatch=authoring.correction_request('p',payload['request_id'],tmp_path,ledger=ledger,submission=json.dumps(changed))
    assert mismatch['effect']=='MISMATCH' and mismatch['association']['state']=='MISMATCH'
    assert 'receipt' not in mismatch and 'settle' not in mismatch and payload['text'] not in json.dumps(mismatch)
    for forged in ({**payload,'request_id':'other-public-request-1'},{**payload,'project':'q'},
                   {**payload,'source_basis':{**payload['source_basis'],'ledger':'q/manuscript/feedback/feedback.jsonl'}}):
        with pytest.raises(ValueError,match='another project'):
            authoring.correction_request('p',payload['request_id'],tmp_path,ledger=ledger,submission=forged)
    with pytest.raises(ValueError,match='exact JSON'):
        authoring.correction_request('p',payload['request_id'],tmp_path,ledger=ledger,submission='{not json')
    template=legacy['compare'];url=urlsplit(template['read']['http']['url']);query=parse_qs(url.query)
    query[template['field']]=[json.dumps(payload)]
    assert not list(Draft202012Validator(HTTP_DECLARATIONS['authoring/correction-request'].payload).iter_errors({k:v[0] for k,v in query.items()}))
    status,_,raw=authoring_http.handle(tmp_path,url.path,query,'GET',b'')
    assert status==200 and json.loads(raw)['association']==match['association']
    retain('origin-association',{'legacy':legacy,'absent':absent,'match':match,'mismatch':mismatch})
