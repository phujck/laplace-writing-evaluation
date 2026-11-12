"""The encoder-owned recipe consumes actual wires without effect or prose replay."""
import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest
from laplace.projects import writing_sources as source
from laplace.native import declarations
from laplace.writing import operating as writing_operating
from laplace.writing.provider import _CodexRpcConnection
from test_tool_refusal_recovery import turn

pytestmark=pytest.mark.skipif(shutil.which('node') is None,reason='Node runs the actual documented code-mode recipe')


def decoded(values):
    script='const samples='+json.dumps(values)+';'+source.PROJECT_RESPONSE_NORMALIZER+'''
const out=samples.map(raw=>{
 try {
  const result=normalizeProjectToolResult(raw);
  return {result, sameOwner:result.owner===raw,
   sameMedia:result.media.every(part=>(Array.isArray(raw)?raw:(raw.contentItems||raw.content||[])).includes(part))};
 } catch(error) {return {error:error.name,message:error.message};}
});process.stdout.write(JSON.stringify(out));'''
    return json.loads(subprocess.run(['node'],input=script,text=True,capture_output=True,check=True).stdout)


def actual_codex_callback(output=None,error=None):
    connection=_CodexRpcConnection.__new__(_CodexRpcConnection)
    connection.process=SimpleNamespace(stdout=io.StringIO(json.dumps({'id':7,'method':'item/tool/call','params':{'fixture':True}})+'\n'))
    connection.lock=threading.Lock();connection.pending={};connection.event=lambda event:None
    def handler(params):
        assert params=={'fixture':True}
        if error is not None:raise error
        return output
    connection.tool_handler=handler;finished=threading.Event();responses=[]
    connection.send=lambda value:(responses.append(value),finished.set())
    connection._read()
    assert finished.wait(3), 'actual adapter callback did not settle'
    assert len(responses)==1
    return responses[0]['result']


def test_actual_encoder_callback_and_mcp_shapes_keep_semantics_and_media():
    owner={'ok':False,'owner_response':{'status':'UNPROVED','text':'{"source prose":"keep as text"}'},
           'source_effect_retained':True,'_image_content':[{'mime_type':'image/png','data':'AAAA'}]}
    original=copy.deepcopy(owner)
    codex=actual_codex_callback(owner)
    mcp={'isError':True,'content':source.content_items(owner,'claude')}
    assert codex['success'] is True and 'structuredContent' not in codex and 'structuredContent' not in mcp
    assert len(codex['contentItems'])==2 and len(mcp['content'])==2
    expected={key:value for key,value in owner.items() if key!='_image_content'}
    samples=[expected,json.dumps(expected),codex,json.dumps(codex),codex['contentItems'],mcp,json.dumps(mcp),mcp['content']]
    out=decoded(samples)
    assert all(row['result']['owner']==expected for row in out)
    assert out[0]['sameOwner'] and out[2]['sameMedia'] and out[5]['sameMedia']
    assert out[2]['result']['transport']=={'success':True}
    assert out[5]['result']['transport']=={'isError':True}
    assert out[2]['result']['owner']['ok'] is False  # callback success is not owner success
    assert out[2]['result']['owner']['owner_response']['text']=='{"source prose":"keep as text"}'
    assert owner==original


@pytest.mark.parametrize('message',['plain transport failure','{"ok":true,"this":"is still error text"}'])
def test_actual_unexpected_callback_error_remains_plain_transport_text(message):
    callback=actual_codex_callback(error=RuntimeError(message))
    assert callback=={'success':False,'contentItems':[{'type':'inputText','text':message}]}
    result=decoded([callback,json.dumps(callback)])[0]['result']
    assert result['owner'] is None and result['transport']=={'success':False}
    assert result['transportError']==message and result['media']==[]


def test_unknown_shapes_refuse_small_without_recursive_parsing_or_fabricated_owner():
    values=[None,3,True,'not JSON','"nested serialized JSON string"',[],['{"ok":true}'],
        {'contentItems':'not-array','success':True},
        {'content':[],'contentItems':[]},
        {'content':[{'type':'audio','data':'not emitted'}]},
        {'content':[{'type':'text','text':'{"ok":true}'},{'type':'text','text':'{"ok":false}'}]},
        {'content':[{'type':'text','text':'source prose, not owner JSON'}]},
        {'content':[{'type':'text','text':'false'}]},
        {'structuredContent':{'ok':True},'content':[{'type':'text','text':'{"ok":true}'}]}]
    result=decoded(values)
    assert all(row['error']=='ProjectResponseShapeError' for row in result)
    assert all(len(row['message'])<300 for row in result)
    assert all('never repeat an effect' in row['message'] for row in result)


def test_recipe_bounded_emit_keeps_large_source_and_media_local():
    owner={'content':'{"looks_like_json":"'+('X'*200000)+'"}',
           '_image_content':[{'mime_type':'image/png','data':'A'*200000}]}
    raw={'content':source.content_items(owner,'claude')}
    script='const raw='+json.dumps(raw)+';const outputs=[];'+'''
new Function('r','text', '''+json.dumps(source.PROJECT_RESPONSE_RECIPE)+''')(raw,value=>outputs.push(value));
process.stdout.write(JSON.stringify(outputs));'''
    result=subprocess.run(['node'],input=script,text=True,capture_output=True,check=True)
    assert len(result.stdout)<1500 and 'data:image' not in result.stdout and 'X'*100 not in result.stdout
    emitted=json.loads(result.stdout)
    assert emitted[0]['owner_keys']==['content'] and emitted[0]['media_count']==1


@pytest.mark.parametrize('extra_keys',[0,25])
def test_production_recipe_bounds_key_previews_without_changing_owner(extra_keys):
    long_key='K'*200000
    owner={long_key:'retained original',**{f'field-{i}':i for i in range(extra_keys)}}
    raw={'content':source.content_items(owner,'claude')}
    script='const raw='+json.dumps(raw)+';const owner='+json.dumps(owner)+';const outputs=[];'+'''
const result=new Function('r','text', '''+json.dumps(source.PROJECT_RESPONSE_RECIPE+'\nreturn normalized;')+''')(raw,value=>outputs.push(value));
const direct=new Function('r','text', '''+json.dumps(source.PROJECT_RESPONSE_RECIPE+'\nreturn normalized;')+''')(owner,()=>{});
process.stdout.write(JSON.stringify({outputs,unchanged:JSON.stringify(result.owner)===JSON.stringify(owner),
 sameObject:direct.owner===owner,originalValue:result.owner['K'.repeat(200000)]}));'''
    result=subprocess.run(['node'],input=script,text=True,capture_output=True,check=True)
    assert len(result.stdout)<2500 and 'K'*81 not in result.stdout
    value=json.loads(result.stdout);emitted=value['outputs'][0]
    assert value['unchanged'] and value['sameObject'] and value['originalValue']=='retained original'
    assert emitted['owner_keys'][0]=='K'*80
    assert emitted['owner_keys_total']==extra_keys+1
    assert emitted['owner_keys_omitted']==max(0,extra_keys+1-20)
    assert emitted['owner_key_previews_truncated']==1
    assert all(len(key)<=80 for key in emitted['owner_keys'])


def test_recipe_parses_only_known_wire_layers_and_preserves_owner_objects():
    owner={'content':'{"source":"ordinary prose remains text"}',
           'owner_response':{'value':'{"nested":"not another wire"}'},'success':False}
    wrapper={'content':source.content_items(owner,'claude')}
    script='const owner='+json.dumps(owner)+';const wrapper='+json.dumps(wrapper)+';'+source.PROJECT_RESPONSE_NORMALIZER+'''
const originalParse=JSON.parse;let parses=0;JSON.parse=(...args)=>{parses++;return originalParse(...args)};
const objectResult=normalizeProjectToolResult(owner);const objectParses=parses;
parses=0;const wrappedResult=normalizeProjectToolResult(wrapper);const wrapperParses=parses;
parses=0;const stringResult=normalizeProjectToolResult(JSON.stringify(wrapper));const stringParses=parses;
process.stdout.write(JSON.stringify({same:objectResult.owner===owner,objectParses,wrapperParses,stringParses,
 content:stringResult.owner.content,nested:wrappedResult.owner.owner_response.value}));'''
    result=json.loads(subprocess.run(['node'],input=script,text=True,capture_output=True,check=True).stdout)
    assert result=={'same':True,'objectParses':0,'wrapperParses':1,'stringParses':2,
                    'content':owner['content'],'nested':owner['owner_response']['value']}


def test_projection_is_one_shared_guide_and_explicit_full_help_recipe():
    assert writing_operating.CAPABILITY_GUIDANCE['project_tool_responses']==source.PROJECT_RESPONSE_GUIDANCE
    help_contract=declarations.help_payload('help',permitted=True,with_tokens=False)
    assert help_contract['response_wire']==source.response_wire_contract()
    assert 'normalizeProjectToolResult' in help_contract['response_wire']['normalization_recipe']
    repository=declarations.help_payload('repository',permitted=True,with_tokens=False)
    assert repository['code_mode_image_recipe']==source.CODE_MODE_IMAGE_RECIPE
    assert 'response_wire' not in repository  # no full recipe echoed on each operation


def test_guidance_cutover_changes_help_digest_not_gateway_or_wire(monkeypatch):
    current=writing_operating.tool_contract()
    original=declarations.help_payload
    def previous_projection(*args,**kwargs):
        value=original(*args,**kwargs)
        value.pop('response_wire',None)
        return value
    monkeypatch.setattr(declarations,'help_payload',previous_projection)
    previous=writing_operating.tool_contract()
    assert previous['digest']!=current['digest']
    assert previous['native_registration']==current['native_registration']
    assert previous['provider_session_policy']==current['provider_session_policy']
    assert [key for key in current['exact_action_digests']
            if current['exact_action_digests'][key]!=previous['exact_action_digests'][key]]==['help']


def test_readonly_actual_mcp_code_mode_probe_decodes_once_with_bounded_emission(tmp_path):
    turn(tmp_path)
    request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{
        'name':'laplace_project','arguments':{'operation':'help','payload':{'operation':'run_status'}}}}
    run=subprocess.run([sys.executable,'-m','laplace.native.tools','--root',str(tmp_path),
        '--project','p','--mode','review','--turn-id','WT-r'],input=json.dumps(request)+'\n',text=True,capture_output=True,check=True)
    response=json.loads(run.stdout)['result']
    assert 'content' in response and 'structuredContent' not in response
    # Emulate the observed code-mode serialized outer return; execute the exact
    # owner recipe, then inspect only the chosen readonly contract fields.
    script='const r='+json.dumps(json.dumps(response))+';'+source.PROJECT_RESPONSE_NORMALIZER+'''
const normalized=normalizeProjectToolResult(r);
const value=normalized.owner;
process.stdout.write(JSON.stringify({requested_operation:value.requested_operation,
 required:value.action.input.required,transport:normalized.transport,media_count:normalized.media.length}));'''
    probed=subprocess.run(['node'],input=script,text=True,capture_output=True,check=True)
    assert len(probed.stdout)<500
    assert json.loads(probed.stdout)['required']==['id']
    rows=[json.loads(line) for line in (tmp_path/'contract/talk.jsonl').read_text().splitlines()]
    assert len([row for row in rows if row.get('record')=='writing-tool-read'])==1
    assert not any(row.get('record') in {'writing-tool-action','writing-tool-failure'} for row in rows)
