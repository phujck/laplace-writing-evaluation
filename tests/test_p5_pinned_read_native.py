"""Read the actual owner-issued handles through native/grammar and Material."""
import json
import hashlib
import os
from pathlib import Path
from dataclasses import asdict
from urllib.parse import parse_qs,urlsplit
import pytest
from test_pinned_read_contract import sources
from laplace.projects import writing_sources,artifacts,library
from laplace.native import tools,verbs,declarations
from laplace.core import source_pin


def keep(name,value):
    home=os.environ.get('P5_PINNED_EVIDENCE')
    if home:
        directory=Path(home);directory.mkdir(parents=True,exist_ok=True)
        with (directory/(name+'.json')).open('x') as stream:json.dump(value,stream,indent=2,ensure_ascii=False)


def native(root,handle):
    return tools.call(root,'book','discuss',{'operation':handle['operation'],'payload':handle['payload']})


def grammar(root,handle):
    classified=verbs.classify(handle['operation'],handle['payload'],project='book',root=root)
    assert classified.exact and classified.owner_call==(handle['operation'],handle['payload'])
    result=tools.request(root,'book','discuss',asdict(classified.request))
    assert result.get('outcome')=='read',result
    return result['owner_response']


def test_plain_repository_handles_native_grammar_stale_restart_and_help(sources,monkeypatch):
    root,text,_=sources
    initial=writing_sources.reference_identity(root,{'repository':'public','path':'plain.txt'})
    assert 'expected_sha256' not in initial['read_handle']['payload']
    first=native(root,{**initial['read_handle'],'payload':{**initial['read_handle']['payload'],'limit':3}})
    assert first['content']==text[:3] and 'pointer' not in first['page_read']['payload']
    assert native(root,first['page_read'])['content']==first['content']
    assert grammar(root,first['read_handle'])['content']==text[3:6]
    counts={'identity':0,'compare':0};identify=writing_sources._identity;compare=source_pin.check
    def observed(path):counts['identity']+=1;return identify(path)
    def checked(sha,payload):counts['compare']+=1;return compare(sha,payload)
    monkeypatch.setattr(writing_sources,'_identity',observed);monkeypatch.setattr(source_pin,'check',checked)
    same=grammar(root,first['page_read']);assert counts=={'identity':1,'compare':1}
    (root/'inputs/plain.txt').write_text('New current source.🌱')
    with pytest.raises(ValueError,match='revision conflict'):native(root,first['read_handle'])
    current=native(root,first['restart_read']);assert current['content']=='New'
    for bad in ['wrong',None,True]:
        with pytest.raises(ValueError):native(root,{'operation':'repository','payload':{**initial['read_handle']['payload'],'expected_sha256':bad}})
    with pytest.raises(ValueError):native(root,{'operation':'repository','payload':{'action':'read','repository':'public','path':'absent.txt','expected_sha256':first['source']['sha256']}})
    help=tools.execute(root,'book','discuss','help',{'operation':'repository'})
    full=declarations.help_payload('repository',permitted=True,root=root,variant='read',full=True)
    assert 'complete raw source bytes' in json.dumps(full) and 'pointer presence' in json.dumps(full)
    keep('repository-native',{'first':first,'same':same,'explicit_restart':current,'read_work':{'identity':1,'compare':1},'help':help})


def test_JSON_pointer_empty_value_digest_and_exact_continuation_native(sources):
    root,_,raw=sources
    plain=native(root,{'operation':'repository','payload':{'action':'read','repository':'public','path':'data.json'}})
    whole=grammar(root,{'operation':'repository','payload':{'action':'read','repository':'public','path':'data.json','pointer':''}})
    assert plain['content']!=whole['content'] and json.loads(plain['content'])==json.loads(whole['content'])
    first=native(root,{'operation':'repository','payload':{'action':'read','repository':'public','path':'data.json','pointer':'/selected','limit':7}})
    assert native(root,first['page_read'])['content']==first['content']
    assert grammar(root,first['read_handle'])['offset']==7
    assert first['json_record']['source_sha256']!=first['json_record']['value_sha256']
    with pytest.raises(ValueError,match='revision conflict'):
        native(root,{'operation':'repository','payload':{**first['page_read']['payload'],'expected_sha256':first['json_record']['value_sha256']}})
    (root/'inputs/data.json').write_bytes(raw.replace(b'other": 1',b'other": 2'))
    with pytest.raises(ValueError,match='revision conflict'):native(root,first['read_handle'])
    restart=native(root,first['restart_read']);assert restart['json_record']['value_sha256']==first['json_record']['value_sha256']
    keep('JSON-native',{'plain':plain,'whole_JSON':whole,'selected':first,'explicit_restart':restart})


def test_artifact_byte_pages_and_Material_human_native_handles(sources):
    root,text,_=sources
    saved=artifacts.store(root,'book',{'path':'plain.txt','before':None,'content':text})
    first=native(root,{'operation':'read_artifact','payload':{'id':saved['id'],'limit':7}})
    assert native(root,first['page_read'])['content']==first['content']
    assert native(root,first['read_handle'])['offset']==first['next_offset']
    # Named owner handle is callable. Existing generic artifact route collision is reported separately to Root.
    assert first['next_offset']==len(first['content'].encode())
    assert 'expected_sha256' not in first['restart_read']['payload']
    with pytest.raises(ValueError):native(root,{'operation':'read_artifact','payload':{'path':'missing.txt','expected_sha256':first['revision']}})
    target={'owner':'repository','repository':'public','path':'plain.txt'}
    material=native(root,{'operation':'material_references','payload':{'view':'preview','target':target,'limit':3}})
    assert native(root,material['page_read'])['owner_result']['content']==text[:3]
    following=grammar(root,material['read_handle']);assert following['owner_result']['offset']==3
    route=urlsplit(material['human_read']['url']);code,_,body=library.handle(route.path,parse_qs(route.query,keep_blank_values=True),'GET',b'',repo_root=root)
    assert code==200 and json.loads(body)['owner_result']['content']==text[:3]
    (root/'inputs/plain.txt').write_text('Changed human source.')
    with pytest.raises(ValueError,match='revision conflict'):native(root,material['read_handle'])
    code,_,body=library.handle(route.path,parse_qs(route.query,keep_blank_values=True),'GET',b'',repo_root=root)
    assert code==409 and 'content' not in json.loads(body)
    current=native(root,material['restart_read']);assert current['currentness']=='UNBOUND' and current['owner_result']['content']=='Cha'
    full=declarations.help_payload('read_artifact',permitted=True,root=root,full=True)
    assert 'complete raw source bytes' in json.dumps(full)
    keep('artifact-Material-native',{'artifact':first,'material':material,'next':following,'explicit_restart':current,'stale_human_status':code})
