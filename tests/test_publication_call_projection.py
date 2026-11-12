"""Direct callable publisher envelopes over real public owners, without inference."""
import copy
import json
import os
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
from laplace.native import tools
from laplace.writing import dispatch_returns,dispatch_parent,operating,records
from laplace.projects import artifacts
from laplace.work import project_work
from test_dispatch_plan_contract import parent
from test_dispatch_parent import synthesis_case


def retain(name,value):
    destination=os.environ.get('PUBLICATION_PROJECTION_EVIDENCE')
    if not destination:return
    target=Path(destination);target.mkdir(exist_ok=True)
    (target/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')


@pytest.mark.parametrize('index,mode',[(0,'work'),(1,'review')])
def test_worker_and_judge_exact_publisher_envelope_runs_through_native_owner(parent,index,mode):
    task,_,_=synthesis_case(parent)
    result=tools.call(parent,'book',mode,{'operation':'session_settings','payload':{'view':'return-contract'}},turn_id=f'WT-child-{index}')
    contract=result['return_contract'];action=copy.deepcopy(contract['publish_action']);context=contract['publication_context']
    assert set(action)=={'operation','payload'} and context['project']=='book' and context['permitted'] is True
    assert 'payload' not in context and 'operation' not in context
    Draft202012Validator(tools.INPUT_SCHEMA).validate(action)
    action['payload']['content']=artifacts.resolve_path(parent,'book',action['payload']['path']).read_text()
    saved=tools.call(parent,'book',mode,action,turn_id=f'WT-child-{index}')
    assert saved['id'] and saved['revision']
    retain('worker' if index==0 else 'judge',{'offered_action':action,'publication_context':context,'result':saved})


def test_parent_exact_publisher_preserves_one_content_copy_and_native_size_bound(parent):
    task,_,_=synthesis_case(parent)
    result=tools.call(parent,'book','work',{'operation':'dispatch_status','payload':{'id':task['id'],'view':'return-contract'}},turn_id='WT-parent')
    contract=result['parent_return_contract'];action=copy.deepcopy(contract['publish_action'])
    assert set(action)=={'operation','payload'} and contract['publication_context']['permitted'] is True
    assert 'scaffold' not in contract and 'schema' not in contract
    def count_content(value):
        if isinstance(value,dict):return sum((1 if key=='content' else 0)+count_content(item) for key,item in value.items())
        return sum(map(count_content,value)) if isinstance(value,list) else 0
    assert count_content(contract)==1
    document=json.loads(action['payload']['content']);document.update(summary='The exact retained reviewed report supports this bounded result.',most_important=['Required inputs were consumed through this actual parent owner.'],status='COMPLETE',remaining_work=[],continuation=None)
    action['payload']['content']=json.dumps(document)
    saved=tools.call(parent,'book','work',action,turn_id='WT-parent')
    assert dispatch_parent.synthesis_view(task,'book',parent)['status']=='VALID'
    from laplace.projects.writing_sources import content_items
    sizes={provider:len(content_items(result,provider)[0]['text'].encode()) for provider in ('codex','claude')}
    assert all(size<12000 for size in sizes.values())
    retain('parent',{'offered_action':action,'publication_context':contract['publication_context'],'result':saved,'delivered_bytes':sizes})


def test_context_metadata_is_not_a_native_call_or_reviewer_authority(parent):
    task,_,_=synthesis_case(parent)
    contract=tools.call(parent,'book','review',{'operation':'session_settings','payload':{'view':'return-contract'}},turn_id='WT-child-1')['return_contract']
    action=copy.deepcopy(contract['publish_action'])
    with pytest.raises(ValueError,match='offered contract'):
        tools.call(parent,'book','review',{**action,**contract['publication_context']},turn_id='WT-child-1')
    records.bank(parent,{'record':'writing-session','id':'WS-ordinary-review','project':'book','role':'review'})
    records.bank(parent,{'record':'writing-turn','id':'WT-ordinary-review','session_id':'WS-ordinary-review','project':'book','mode':'review'})
    action['payload']['content']=artifacts.resolve_path(parent,'book',action['payload']['path']).read_text()
    with pytest.raises(ValueError,match='Independent review'):
        tools.call(parent,'book','review',action,turn_id='WT-ordinary-review')
    foreign=copy.deepcopy(action);foreign['payload']={key:value for key,value in foreign['payload'].items() if key!='expected_revision'}
    foreign['payload'].update(path='development/not-a-return.md',before=None,content='No capability from metadata.')
    with pytest.raises(ValueError,match='Independent review'):
        tools.call(parent,'book','review',foreign,turn_id='WT-child-1')
    assert not artifacts.resolve_path(parent,'book','development/not-a-return.md').exists()


def test_parent_context_false_and_actual_original_parent_guard_agree(parent):
    task,_,_=synthesis_case(parent)
    records.bank(parent,{'record':'writing-session','id':'WS-foreign-parent','project':'book','role':'author'})
    records.bank(parent,{'record':'writing-turn','id':'WT-foreign-parent','session_id':'WS-foreign-parent','project':'book','mode':'work'})
    result=tools.call(parent,'book','work',{'operation':'dispatch_status','payload':{'id':task['id'],'view':'return-contract'}},turn_id='WT-foreign-parent')
    contract=result['parent_return_contract'];assert contract['publication_context']['permitted'] is False
    action=copy.deepcopy(contract['publish_action']);document=json.loads(action['payload']['content']);document.update(summary='Foreign metadata cannot admit the caller.',most_important=['No original parent authority.'])
    action['payload']['content']=json.dumps(document)
    with pytest.raises(ValueError,match='original|parent|consumed'):
        tools.call(parent,'book','work',action,turn_id='WT-foreign-parent')


def test_shared_projection_help_frames_and_metadata_do_not_duplicate_content(parent):
    task,_,_=synthesis_case(parent)
    marker='One retained publication body. '*300
    qualified=dispatch_returns.publication(parent,'book','development/projection-only.json',document={'summary':marker})
    projected=dispatch_returns.publication_projection(qualified)
    assert projected['publish_action']['payload'] is qualified['payload']
    assert json.dumps(projected).count('One retained publication body.')==300
    assert 'content' not in projected['publication_context'] and qualified['project']=='book'
    help=tools.call(parent,'book','review',{'operation':'help','payload':{'operation':'store_artifact'}},turn_id='WT-child-1')['action']
    frame=operating.build('book','review',parent,session_id='WS-child-1',dispatch_id=task['id'])
    session=tools.call(parent,'book','review',{'operation':'session_settings','payload':{}},turn_id='WT-child-1')
    assert set(help['publish_action'])=={'operation','payload'} and help['publication_context']['project']=='book'
    assert frame['scoped_permissions'][0]['publish_action']==help['publish_action']
    assert frame['scoped_permissions'][0]['publication_context']==help['publication_context']
    assert session['scoped_permissions']==[{'publication_context':session['return_contract']['publication_context']}]
    assert 'store_artifact' in frame['permissions']
