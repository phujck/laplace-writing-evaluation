"""Startup semantics only: capabilities, catalogue provenance and effective context."""
import copy
import io
import json

import pytest

from test_reader_qualification import case,selected_commission
from laplace.writing import sealed_reader as S,provider,turn_admission as T,turn_execution as E,operating,records
from laplace.representation import writing_bodies


def actual_shaped():
    return {'tools':[],'mcp_servers':[],'agents':['PUBLIC_UNKNOWN_AGENT'],
        'plugins':[{'name':'agents-md','path':'builtin','source':'agents-md@builtin','version':'1.0'},
            {'name':'PRIVATE_CUSTOM_PLUGIN','path':'/private/PATH_CANARY','source':'PRIVATE_MARKETPLACE'}],
        'slash_commands':[],'skills':[],'output_style':'default'}


def test_memory_paths_known_mapping_shape_preserves_missing_list_and_malformed_rules():
    base={'tools':[],'mcp_servers':[]}
    for value,count,state in (({},0,'OBSERVED_EMPTY'),([],0,'OBSERVED_EMPTY'),
            (['/private/MEMORY'],1,'UNSUPPORTED_EFFECTIVE_CONTEXT'),
            (None,None,'UNSUPPORTED_SCHEMA'),('PRIVATE_MEMORY',None,'UNSUPPORTED_SCHEMA'),
            (1,None,'UNSUPPORTED_SCHEMA')):
        result=S.observe_startup({**base,'memory_paths':value})
        assert result['effective_context']['memory_paths']==state
        assert result['counts']['memory_paths']==count
        assert result['state']==(S.STARTUP_STATE if state=='OBSERVED_EMPTY' else 'UNQUALIFIED')
    absent=S.observe_startup(base)
    assert absent['effective_context']['memory_paths']=='UNOBSERVED'
    assert absent['counts']['memory_paths'] is None and absent['state']==S.STARTUP_STATE
    for field in ('tools','mcp_servers','skills','hooks'):
        result=S.observe_startup({**base,field:{}})
        states=result['offered_capabilities'] if field in base else result['effective_context']
        assert states[field]=='UNSUPPORTED_SCHEMA' and result['state']=='UNQUALIFIED'


def test_memory_paths_nonempty_mapping_refuses_without_retaining_private_paths():
    memory={'/private/MEMORY_CANARY_'+str(i):'PRIVATE_BODY_'+str(i) for i in range(1000)}
    value={'tools':[],'mcp_servers':[],'memory_paths':memory}
    result=S.observe_startup(value)
    assert result['state']=='UNQUALIFIED'
    assert result['effective_context']['memory_paths']=='UNSUPPORTED_EFFECTIVE_CONTEXT'
    assert result['counts']['memory_paths']==1000
    assert result['effective_context_sha256']['memory_paths'].startswith('sha256:')
    text=json.dumps(result)
    assert len(text)<4000 and 'MEMORY_CANARY' not in text and 'PRIVATE_BODY' not in text
    reordered={**value,'memory_paths':dict(reversed(list(memory.items())))}
    assert S.observe_startup(reordered)['effective_context_sha256']==result['effective_context_sha256']


def test_catalogue_provenance_is_not_a_capability_or_context_verdict():
    value=actual_shaped();result=S.observe_startup(value,executable_sha256=S.STARTUP_PRODUCER_SHA)
    assert result['state']==S.STARTUP_STATE and result['offered_capabilities']=={'tools':'OBSERVED_EMPTY','mcp_servers':'OBSERVED_EMPTY'}
    assert result['catalogues']['plugins']['public_builtin_matches']=={'agents-md':1}
    assert result['catalogues']['plugins']['builtin_descriptor_shape_total']==1
    assert result['catalogues']['agents']['unknown_identifier_total']==1
    assert result['catalogues']['plugins']['unknown_identifier_total']==1
    assert result['effective_context']['memory_paths']=='UNOBSERVED'
    assert all(token not in json.dumps(result) for token in ('PRIVATE_CUSTOM_PLUGIN','/private/PATH_CANARY','PRIVATE_MARKETPLACE','PUBLIC_UNKNOWN_AGENT'))
    unverified=S.observe_startup(value,executable_sha256='0'*64)
    assert unverified['state']==S.STARTUP_STATE and not unverified['catalogues']['plugins']['public_builtin_matches']
    assert unverified['catalogues']['plugins']['producer_basis']=='UNVERIFIED_PRODUCER'


@pytest.mark.parametrize('field,value',[('tools',['Read']),('tools',None),('mcp_servers',{}),
    ('mcp_servers',[{'name':'PRIVATE_SERVER'}]),('skills',['PRIVATE_SKILL']),('slash_commands',['PRIVATE_COMMAND']),
    ('memory_paths',['/private/MEMORY']),('hooks',{'private':'context'}),('effective_context',['PRIVATE_CONTEXT']),
    ('output_style','PRIVATE_STYLE')])
def test_actual_capability_and_effective_context_guard_stays_strict(field,value):
    init=actual_shaped();init[field]=value
    result=S.observe_startup(init,executable_sha256=S.STARTUP_PRODUCER_SHA)
    assert result['state']=='UNQUALIFIED'
    assert all(token not in json.dumps(result) for token in ('PRIVATE_SERVER','PRIVATE_SKILL','PRIVATE_COMMAND','/private/MEMORY','PRIVATE_CONTEXT','PRIVATE_STYLE'))


def test_catalogue_schema_unknowns_and_many_descriptors_stay_bounded_nonblocking():
    init=actual_shaped();init['agents']=['PRIVATE_AGENT_'+str(i) for i in range(5000)]
    init['plugins']=[{'name':'PRIVATE_PLUGIN_'+str(i),'path':'/private/'+str(i),'source':'custom'} for i in range(5000)]
    first=S.observe_startup(init,executable_sha256=S.STARTUP_PRODUCER_SHA)
    assert first['state']==S.STARTUP_STATE and first['catalogues']['agents']['total']==5000
    assert len(json.dumps(first).encode())<5000
    assert all(token not in json.dumps(first) for token in ('PRIVATE_AGENT_','PRIVATE_PLUGIN_','/private/'))
    reordered=copy.deepcopy(init);reordered['plugins'][0]={key:init['plugins'][0][key] for key in reversed(init['plugins'][0])}
    assert S.observe_startup(reordered,executable_sha256=S.STARTUP_PRODUCER_SHA)['catalogues']==first['catalogues']
    for catalogues in ({'agents':None,'plugins':{}},{'agents':[{}],'plugins':['PRIVATE_UNKNOWN']}):
        observed=S.observe_startup({**init,**catalogues},executable_sha256=S.STARTUP_PRODUCER_SHA)
        assert observed['state']==S.STARTUP_STATE
        assert all(token not in json.dumps(observed) for token in ('PRIVATE_UNKNOWN',))
    missing=S.observe_startup({'tools':[],'mcp_servers':[]})
    assert missing['state']==S.STARTUP_STATE and missing['catalogues']['agents']['state']=='UNOBSERVED'
    assert S.observe_startup({'mcp_servers':[]})['state']=='UNQUALIFIED'


@pytest.mark.parametrize('tool_attempt',[False,True])
def test_semantic_state_through_existing_adapter_delivery_reply_and_exact_read(case,monkeypatch,tool_attempt):
    root,_,_,_=case;selected,value=selected_commission(case);launches=[]
    monkeypatch.setattr(E,'start',lambda launch:launches.append(launch));answer=T.start_reader_qualification(root,value);launch=launches[0]
    init={'type':'system','subtype':'init','session_id':'PUBLIC_NATIVE','model':'fixture-reader',**actual_shaped()}
    messages=[init]
    if tool_attempt:messages.append({'type':'assistant','message':{'content':[{'type':'tool_use','name':'Read','input':{}}]}})
    messages.append({'type':'result','subtype':'success','result':'PUBLIC SEMANTIC REPORT'})
    class Input(io.StringIO):
        def close(self):pass
    class Process:
        pid=999999999
        def __init__(self,*args,**kwargs):self.stdin=Input();self.stdout=iter(json.dumps(row)+'\n' for row in messages)
        def poll(self):return 0
        def wait(self,timeout=None):return 0
    monkeypatch.setattr(provider.subprocess,'Popen',Process)
    live=provider.WritingTurn(root,'claude','fixture-reader','low',None,lambda event:None,'review',project='book',session_id=launch.session_id)
    live.reader_profile=launch.reader_profile;live.operating_brief=launch.operating_brief
    if tool_attempt:
        with pytest.raises(provider.ProviderError):live.run(launch.prompt)
        assert live.delivery['reader']['state']=='UNQUALIFIED'
        return
    result=live.run(launch.prompt);assert result['delivery_receipt']['reader']['state']==S.STARTUP_STATE
    assert result['delivery_receipt']['native_inventory']['state']=='OBSERVED'
    E._bank_reply(launch,result);E._finish(launch,result)
    exact=S.request(root,{'project':'book','view':'result','input':selected['input'],'turn_id':answer['turn_id']})
    receipt=exact['turn']['reply']['delivery_receipt']
    assert receipt['reader']['state']==S.STARTUP_STATE
    assert receipt['reader']['catalogues']['plugins']['unknown_identifier_total']==2
    operating.validate_provider_metadata({'delivery_receipt':receipt})
    assert operating.delivery_receipt_projection(receipt)['native_inventory']['tool_count']==0
    old={'schema_version':operating.DELIVERY_RECEIPT_VERSION,'reader':{'state':'UNQUALIFIED','counts':{'agents':4,'plugins':3}}}
    assert writing_bodies.resolve_fields({'record':'writing-reply','delivery_receipt':old},root)['delivery_receipt']==old
    assert S.support(root,'book')['state']=='CANDIDATE'
    (root/'semantic-delivery-proof.json').write_text(json.dumps({'exact':exact,'observer':receipt['reader'],
        'historical_receipt_unchanged':old,'actual_provider_calls':0,'fake_process_only':True},indent=2))
