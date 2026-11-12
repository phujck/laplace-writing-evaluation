"""Only the reached selected-message HTTP declaration/issued-handle join."""
import json
from urllib.parse import parse_qs,urlsplit

import pytest
from jsonschema import Draft202012Validator

from test_public_message_parts import public,request,replace_row,http,COUNTEREXAMPLE_ANSWER,bank_counterexample,baseline_presentation
from laplace.writing import records,session_projection as P
from laplace.writing import session_reads as S
from laplace.native import declarations as D,tools
from laplace.web import writing_declared_http,authoring_http


def query(handle):
    result={key:values[0] for key,values in parse_qs(urlsplit(handle['http']['url']).query).items()}
    for key in ('offset','limit'):
        if key in result:result[key]=int(result[key])
    return result


def validator():return Draft202012Validator(D.HTTP_DECLARATIONS['authoring/session-turn'].payload)


def test_actual_issued_message_first_page_next_restart_and_generated_help_are_declared(public):
    root=public;replace_row(root,'WT-a',text='PUBLIC exact é中🌱 text and its retained tail')
    page=S.public_message(root,request(limit=7));seen=[]
    for name,handle in [('first',page['restart_read']),('same-page',page['page_read']),('next',page['next_read'])]:
        normalized=query(handle);validator().validate(normalized)
        status,value=http(root,handle);assert status==200 and value['schema_version']=='laplace.writing-message-part/1'
        seen.append({'kind':name,'query':normalized,'status':status,'content':value['content'],'basis':value['basis']})
    replace_row(root,'WT-a',ts='changed source identity; text remains')
    status,refused=http(root,page['next_read']);assert status==409
    assert refused['message_refusal']['code']=='CHANGED_MESSAGE' and 'content' not in refused
    restart=refused['message_refusal']['restart_read'];validator().validate(query(restart))
    status,current=http(root,restart);assert status==200 and current['basis']!=page['basis']
    help_value=tools.help_response(root,'book','work',{'route':'/authoring/session-turn','method':'GET'})['action']
    assert help_value['input']==D.HTTP_DECLARATIONS['authoring/session-turn'].payload
    for key,token in [('outputs','NO_SAVED_REPLY'),('errors','CHANGED_MESSAGE'),('recoverable','restart_read')]:
        assert token in json.dumps(help_value[key])
    assert all(key in help_value['response_sources'] for key in ('message','message-absence','message-changed'))
    absent=S.public_message(root,request('reply'));assert absent['state']=='ABSENT'
    validator().validate(query(absent['restart_read']))
    assert http(root,absent['restart_read'])[1]['reason']=='NO_SAVED_REPLY'
    (root/'HTTP-declaration-correction-proof.json').write_text(json.dumps({'issued_reads':seen,'refusal':refused,
        'explicit_restart':current,'absence':absent,'HTTP_help':help_value,'actual_provider_calls':0},indent=2))


def test_message_variant_remains_closed_bounded_and_legacy_variants_identical(public):
    schema=validator();value=query(S.public_message(public,request())['page_read'])
    schema.validate(value)
    for change in ({'session_id':''},{'part':'context'},{'offset':-1},{'limit':0},{'limit':40001},
                   {'limit':True},{'expected_basis':'sha256:'+'a'*64+'\n'},{'expected_basis':'wrong'},
                   {'request_id':'foreign'},{'manifest_id':'sha256:'+'a'*64},{'context':'unrelated'}):
        assert list(schema.iter_errors({**value,**change})),change
    for key in ('project','session_id','id','view','part'):
        assert list(schema.iter_errors({k:v for k,v in value.items() if k!=key})),key
    for legacy in ({'project':'book','id':'WT-a'},
                   {'project':'book','id':'WT-a','view':'turn'},
                   {'project':'book','id':'WT-a','view':'controls','offset':0,'limit':20,'item_id':'CONTROL-public'},
                   {'project':'book','session_id':'WS-a','request_id':'public-parent','view':'request'},
                   {'project':'book','request_id':'public-reader','manifest_id':'sha256:'+'b'*64,'view':'reader-request'}):
        schema.validate(legacy)
    url=urlsplit(S.public_message(public,request())['audit_read']['http']['url'])
    status,_,raw=authoring_http.handle(public,url.path,parse_qs(url.query),'GET',b'')
    assert status==200 and json.loads(raw)['turn']['id']=='WT-a'
    (public/'HTTP-closed-and-legacy-proof.json').write_text(json.dumps({'valid_message':value,
        'malformed_variants_refused':16,'legacy_variants_retained':5,'actual_legacy_Audit_status':status,
        'additionalProperties_broadened':False,'actual_provider_calls':0},indent=2))


def test_changed_presentation_refuses_its_old_declared_page_and_unaffected_bases_are_kept(public,monkeypatch):
    root=public;bank_counterexample(root)
    records.bank(root,{'record':'writing-reply','id':'WR-plain','turn_id':'WT-current','session_id':'WS-a','project':'book','text':'PLAIN PUBLIC REPLY'})
    monkeypatch.setattr(P,'reply_presentation',baseline_presentation)
    old=S.public_message(root,request('reply',limit=10))
    plain_old=S.public_message(root,request('reply',turn_id='WT-current'));request_old=S.public_message(root,request())
    monkeypatch.undo()
    validator().validate(query(old['next_read']))
    status,refused=http(root,old['next_read'])
    assert status==409 and refused['message_refusal']['code']=='CHANGED_MESSAGE' and 'content' not in refused
    restart=refused['message_refusal']['restart_read'];validator().validate(query(restart))
    status,current=http(root,restart)
    assert status==200 and current['presentation_origin']=='structured.answer' and current['offset']==0
    assert COUNTEREXAMPLE_ANSWER.startswith(current['content']) and current['source_row_sha256']==old['source_row_sha256']
    status,again=http(root,current['page_read']);assert status==200 and again['basis']==current['basis']
    plain=S.public_message(root,request('reply',turn_id='WT-current'))
    assert plain['content']=='PLAIN PUBLIC REPLY' and plain['basis']==plain_old['basis'], 'an unaffected reply keeps its basis'
    assert S.public_message(root,request())['basis']==request_old['basis'], 'a request part never consumes reply presentation'
