"""Provider-owned counter domains and actual app delivery, without model calls."""
from laplace.representation import writing_bodies as bodies
import json
import pytest
from laplace.writing import operating as wo, provider as wp
from laplace.writing.records import _bank as records_bank
from laplace.core import bodies as core_bodies
from laplace.core.identity import UnsupportedSchemaVersion


def code_counts(total=17):
    return {'input_tokens':10,'cached_input_tokens':3,'cache_write_input_tokens':0,
            'output_tokens':total-10,'reasoning_output_tokens':2,'total_tokens':total}


def test_duplicate_phases_and_claude_ids_do_not_sum(tmp_path):
    facts=wp._UsageFacts('claude',tmp_path,'WT','haiku');facts.bind('native')
    raw={'input_tokens':2,'cache_read_input_tokens':3,'cache_creation_input_tokens':0,
         'output_tokens':7,'output_tokens_details':{'thinking_tokens':4}}
    message={'id':'m','model':'actual','usage':raw}
    facts.claude_assistant(message);facts.claude_assistant(message)
    facts.claude_terminal({'usage':{**raw,'output_tokens':11},'modelUsage':{'actual':{
        'inputTokens':200,'outputTokens':99,'cacheReadInputTokens':3,'cacheCreationInputTokens':0,
        'costUSD':.01,'costBasis':'list'}}})
    view=facts.snapshot();assert len(view['observations'])==3
    assert view['selected']['logical_turn']['counts']['output']==11
    assert view['selected']['context_snapshot']['value']==5
    assert len(view['selected']['unselected_variants'])==1
    assert view['selected']['logical_turn']['counts']['reasoning_output']==4
    assert view['selected']['logical_turn']['counts']['total']==16 # reasoning subset
    assert view['observations'][-1]['reported_cost_estimate']['invoice'] is False
    assert view['model_observations'][0]['actual_reported_model']=='actual'
    assert view['model_observations'][0]['admitted_model']=='haiku'


def test_missing_counts_and_interrupted_scope_are_unknown(tmp_path):
    facts=wp._UsageFacts('claude',tmp_path,'WT')
    facts.claude_assistant({'id':'m','usage':{'output_tokens':4}})
    facts.claude_assistant({'id':'m','usage':{'output_tokens':9}})
    view=facts.snapshot()
    assert view['selected']['logical_turn'] is None
    assert view['selected']['context_snapshot']['value'] is None
    assert view['selected']['context_snapshot']['counts']['reasoning_output'] is None
    assert view['selected']['context_snapshot']['counts']['output']==9
    assert view['selected']['context_snapshot']['counts']['total'] is None
    assert view['coverage']['logical_turn_total']=='unknown'


def test_codex_last_is_not_turn_and_reset_invalidates_baseline(tmp_path):
    facts=wp._UsageFacts('codex',tmp_path,'WT');facts.bind('thread',fresh=True);facts.bind('thread','turn')
    raw={'last':{'inputTokens':10,'cachedInputTokens':3,'cacheWriteInputTokens':0,
                 'outputTokens':7,'reasoningOutputTokens':2,'totalTokens':17},
         'total':{'inputTokens':30,'cachedInputTokens':9,'cacheWriteInputTokens':0,
                  'outputTokens':21,'reasoningOutputTokens':6,'totalTokens':51}}
    facts.codex(raw);facts.codex(raw,'terminal')
    view=facts.snapshot();assert len(view['observations'])==2
    assert view['selected']['context_snapshot']['value']==10
    assert view['selected']['logical_turn']['counts']['total']==51
    assert view['selected']['logical_turn']['basis']=='codex.fresh_binding_cumulative'
    facts.codex({'last':raw['last'],'total':raw['last']})
    view=facts.snapshot();assert view['reset_epoch']==1
    assert view['selected']['logical_turn'] is None
    assert view['baseline']['kind']=='unknown'


def native_record(thread='thread',turn='turn'):
    return {'type':'token_usage_record','payload':{'thread_id':thread,'turn_id':turn,'response_id':'response',
        'usage':code_counts(17),'turn_token_usage':code_counts(51),'thread_token_usage':code_counts(101)}}


@pytest.mark.parametrize('include_counter',[True,False])
def test_native_direct_counter_survives_omitted_trace_prefix(tmp_path,include_counter):
    path=tmp_path/'native-thread.jsonl';path.write_bytes(b'')
    stat=path.stat();stamp=(stat.st_dev,stat.st_ino)
    with path.open('ab') as stream:
        stream.write(json.dumps({'type':'message','body':'x'*3_000_000}).encode()+b'\n')
        stream.write(json.dumps(native_record(turn='other')).encode()+b'\n')
        if include_counter:stream.write(json.dumps(native_record()).encode()+b'\n')
    facts=wp._UsageFacts('codex',tmp_path,'WT');facts.bind('thread','turn')
    facts.native_codex(str(path),0,stamp);view=facts.snapshot()
    assert view['coverage']['native_metadata']['omitted_before']>0
    assert view['coverage']['native_metadata']['trace_coverage']=='partial'
    selected=view['selected']['logical_turn']
    if include_counter:
        assert selected['basis']=='codex.native.turn_token_usage'
        assert selected['counts']['total']==51
        assert selected['completeness']=='complete_for_reported_scope'
    else:assert selected is None


def test_native_refuses_unadmitted_or_foreign_file(tmp_path):
    path=tmp_path/'native-other.jsonl';path.write_text(json.dumps(native_record())+'\n')
    facts=wp._UsageFacts('codex',tmp_path);facts.bind('thread','turn')
    stat=path.stat();facts.native_codex(str(path),0,(stat.st_dev,stat.st_ino))
    assert facts.snapshot()['selected']['logical_turn'] is None
    owned=tmp_path/'native-thread.jsonl';owned.write_text(path.read_text())
    facts.native_codex(str(owned),None,None)
    assert facts.snapshot()['selected']['logical_turn'] is None


def test_header_projection_and_existing_custody_are_closed(tmp_path):
    facts=wp._UsageFacts('claude',tmp_path,'WT');facts.bind('native')
    for i in range(20):facts.claude_assistant({'id':str(i),'usage':{'output_tokens':i}})
    value=facts.snapshot()
    stored=records_bank.prepare_custody_row(tmp_path,{'record':'writing-reply','id':'WR','turn_id':'WT',
        'usage_facts':value})
    assert stored['usage_facts']['schema_version']==core_bodies.REFERENCE_SCHEMA
    header=stored['usage_facts_projection'];assert 'observations' not in header
    assert header['logical_turn_id']=='WT';assert header['selected']['logical_turn'] is None
    restored=json.loads(bodies.read_bytes(stored['usage_facts'],tmp_path))
    assert restored==value
    for observation in value['observations']:
        raw=bodies.read_bytes(observation['raw_observation_ref'],tmp_path)
        assert json.loads(raw)['output_tokens']>=0


def test_metadata_gate_rejects_unsupported_or_dangling_selection(tmp_path):
    with pytest.raises(UnsupportedSchemaVersion):wo.validate_provider_metadata({'usage_facts':{'schema_version':'laplace.provider-usage-facts/2'}})
    facts=wp._UsageFacts('claude',tmp_path).snapshot()
    facts['selected']['logical_turn']={'observation_id':'missing'}
    with pytest.raises(ValueError,match='saved observation'):wo.usage_facts_projection(facts)
    assert wo.validate_provider_metadata({'usage':{'provider':'old','output':2}})['usage']['output']==2


def test_common_delivery_meaning_and_resumed_withheld_parts(tmp_path):
    from test_writing_operating import _project
    _project(tmp_path);brief=wo.build('book','review',tmp_path)
    receipts=[wo.delivery_receipt(brief,p,'Same commission') for p in ('codex','claude')]
    assert receipts[0]['app_semantic_digest']==receipts[1]['app_semantic_digest']
    assert receipts[0]['channels']['kernel']=='baseInstructions'
    assert receipts[0]['native_inventory']['state']=='UNOBSERVABLE'
    assert all(r['parts']['task']['state']=='PREPARED' for r in receipts)
    for provider in ('codex','claude'):
        blocks=wo.process_instructions(brief,provider,resumed=False)
        assert wo.body(brief) in blocks['turn_prefix']
        assert wo.body(brief) not in blocks['session_slot']
        receipt=wo.delivery_receipt(brief,provider,'New task',resumed=True)
        assert receipt['parts']['body']['state']=='WITHHELD'
        assert receipt['withheld_reads']
        assert receipt['provider_retention']['state']=='UNOBSERVABLE'


def test_future_metadata_is_not_interpreted_by_tolerant_history(tmp_path):
    row={'record':'writing-reply','id':'WR','usage':{'output':9},
         'usage_facts':{'schema_version':'laplace.provider-usage-facts/2'},
         'usage_facts_projection':{'schema_version':wo.USAGE_FACTS_VERSION}}
    resolved=bodies.resolve_fields(row,tmp_path,strict=False)
    assert resolved['_custody_errors']
    assert 'usage_facts' not in resolved and 'usage_facts_projection' not in resolved
    assert row['usage_facts']['schema_version'].endswith('/2') # original is retained
    with pytest.raises(ValueError,match='unsupported'):bodies.resolve_fields(row,tmp_path)


def test_inconsistent_counter_is_retained_without_accepting_turn_total(tmp_path):
    facts=wp._UsageFacts('codex',tmp_path,'WT');facts.bind('thread',fresh=True)
    facts.codex({'total':{'inputTokens':10,'cachedInputTokens':0,'cacheWriteInputTokens':0,
        'outputTokens':4,'reasoningOutputTokens':9,'totalTokens':14}})
    view=facts.snapshot()
    assert view['observations'][0]['completeness']=='inconsistent_reported_counts'
    assert view['selected']['logical_turn'] is None
    assert view['selected']['binding_cumulative']['counts']['reasoning_output']==9


def test_custody_failure_keeps_filtered_inline_metadata(tmp_path,monkeypatch):
    class Broken:
        def put(self,raw):raise OSError('fixture storage refusal')
    monkeypatch.setattr(bodies,'store',lambda root:Broken())
    facts=wp._UsageFacts('claude',tmp_path)
    item=facts.observe({'output_tokens':4,'content':'must not retain'},'last_request','fixture')
    assert item['raw_observation']=={'output_tokens':4}
    assert item['raw_observation_ref'] is None
    assert 'fixture storage refusal' in item['raw_custody_error']
    wo.validate_provider_metadata({'usage_facts':facts.snapshot()})


def test_native_file_replacement_refused(tmp_path):
    path=tmp_path/'native-thread.jsonl';path.write_bytes(b'')
    stat=path.stat();stamp=(stat.st_dev,stat.st_ino)
    replacement=tmp_path/'replacement';replacement.write_text(json.dumps(native_record())+'\n');replacement.replace(path)
    facts=wp._UsageFacts('codex',tmp_path);facts.bind('thread','turn')
    facts.native_codex(str(path),0,stamp)
    assert facts.snapshot()['selected']['logical_turn'] is None
    assert facts.snapshot()['coverage']['native_metadata']['state']=='unavailable'


def test_exact_history_preserves_nested_observation_handles_and_export_closure(tmp_path):
    import importlib.util
    from pathlib import Path
    facts=wp._UsageFacts('claude',tmp_path,'WT');facts.claude_assistant({'id':'m','usage':{'output_tokens':4}})
    row=records_bank.prepare_custody_row(tmp_path,{'record':'writing-reply','usage_facts':facts.snapshot()})
    resolved=bodies.resolve_fields(row,tmp_path)
    assert resolved['usage_facts']['observations'][0]['raw_observation_ref']['schema_version']==core_bodies.REFERENCE_SCHEMA
    assert resolved['usage_facts_projection']==row['usage_facts_projection']
    wo.validate_provider_metadata(resolved)
    spec=importlib.util.spec_from_file_location('writing_eval_manifest',Path(__file__).parents[1]/'scripts/writing_eval_manifest.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bodies,missing,unresolved=module._body_closure(tmp_path,[row])
    assert len(bodies)==1 and missing==unresolved==[]


def test_adapter_refuses_changed_resume_identity_before_accepting_counts(tmp_path,monkeypatch):
    from test_writing_operating import _project
    from test_session_contract import _codex_connection, _claude_process
    _project(tmp_path);calls=[]
    class Foreign(_codex_connection(calls)):
        def request(self,method,params):
            if method=='thread/resume':return {'thread':{'id':'foreign'},'model':'stub-codex'}
            return super().request(method,params)
    monkeypatch.setattr(wp,'CodexConnection',Foreign)
    turn=wp.WritingTurn(tmp_path,'codex','stub-codex','high','admitted',lambda event:None,'review',project='book')
    with pytest.raises(wp.ProviderError,match='admitted binding'):turn.run('Read source')
    assert not any(method=='turn/start' for method,params in calls)
    monkeypatch.setattr(wp.shutil,'which',lambda name:'/fixture/claude')
    monkeypatch.setattr(wp.subprocess,'Popen',_claude_process([]))
    turn=wp.WritingTurn(tmp_path,'claude','','high','admitted',lambda event:None,'review',project='book')
    with pytest.raises(wp.ProviderError,match='admitted session'):turn.run('Read source')
    assert turn.usage_facts.snapshot()['observations']==[]


@pytest.mark.parametrize('malformed',[None,{},['wrong']])
def test_current_tag_does_not_make_malformed_counter_metadata_valid(malformed):
    with pytest.raises(ValueError):wo.validate_provider_metadata({'usage_facts':{
        'schema_version':wo.USAGE_FACTS_VERSION,'observations':malformed}})


def test_terminal_cost_variant_remains_separate_from_model_and_usage_domains(tmp_path):
    facts=wp._UsageFacts('claude',tmp_path)
    facts.claude_terminal({'usage':{'input_tokens':2,'cache_read_input_tokens':0,'cache_creation_input_tokens':0,'output_tokens':3},
        'total_cost_usd':.02,'duration_api_ms':200,'modelUsage':{'model':{'costUSD':.01,'costBasis':'list'}}})
    view=facts.snapshot()
    assert view['selected']['logical_turn']['counts']['total']==5
    variants=view['selected']['unselected_variants'];assert len(variants)==2
    assert [row['reported_cost_estimate']['value'] for row in variants]==[.02,.01]
    assert all(row['counter_domain']=='unknown' for row in variants)
    assert all(row['reported_cost_estimate']['invoice'] is False for row in variants)


def test_nested_nonmetadata_never_enters_raw_counter_custody(tmp_path):
    sentinel='PRIVATE_NONMETADATA_BODY_SENTINEL'
    facts=wp._UsageFacts('claude',tmp_path)
    row=facts.observe({'output_tokens':7,'output_tokens_details':{'thinking_tokens':4,'text':sentinel},
        'cache_creation':{'ephemeral_5m_input_tokens':3,'auth':sentinel},
        'server_tool_use':{'web_search_requests':2,'content':sentinel},
        'iterations':[{'output_tokens':4,'text':sentinel,'output_tokens_details':{'thinking_tokens':2,'content':sentinel}}]},'last_request','fixture')
    raw=bodies.read_bytes(row['raw_observation_ref'],tmp_path).decode()
    assert sentinel not in raw
    assert json.loads(raw)['output_tokens_details']=={'thinking_tokens':4}
    assert json.loads(raw)['cache_creation']=={'ephemeral_5m_input_tokens':3}
    assert json.loads(raw)['iterations'][0]['output_tokens_details']=={'thinking_tokens':2}
    assert row['raw_metadata_coverage']['omitted_bytes']>0


def test_last_request_cannot_be_promoted_to_logical_total(tmp_path):
    facts=wp._UsageFacts('codex',tmp_path);facts.bind('thread','turn')
    observation=facts.observe(code_counts(),'last_request','codex.appserver.last')
    value=facts.snapshot();value['selected']['logical_turn']={**facts._selection(observation),'counter_scope':'logical_turn'}
    with pytest.raises(ValueError,match='promote'):wo.validate_provider_metadata({'usage_facts':value})


@pytest.mark.parametrize('broken',['binding','epoch','counts','boolean_zero'])
def test_fresh_binding_derivation_requires_exact_baseline(tmp_path,broken):
    facts=wp._UsageFacts('codex',tmp_path);facts.bind('thread',fresh=True)
    facts.codex({'total':{'inputTokens':10,'cachedInputTokens':3,'cacheWriteInputTokens':0,'outputTokens':7,'totalTokens':17}})
    value=facts.snapshot();wo.validate_provider_metadata({'usage_facts':value})
    if broken=='binding':value['baseline']['native_binding_id']='other'
    elif broken=='epoch':value['baseline']['reset_epoch']=7
    elif broken=='counts':value['baseline']['value']['total']=1
    else:value['baseline']['value']['total']=False
    with pytest.raises(ValueError,match='baseline'):wo.validate_provider_metadata({'usage_facts':value})


def test_context_proxy_requires_exact_request_value(tmp_path):
    facts=wp._UsageFacts('claude',tmp_path);facts.claude_assistant({'id':'m','usage':{'input_tokens':2,'cache_read_input_tokens':3,'cache_creation_input_tokens':0,'output_tokens':4}})
    value=facts.snapshot();value['selected']['context_snapshot']['value']=999
    with pytest.raises(ValueError,match='exact request'):wo.validate_provider_metadata({'usage_facts':value})


def test_init_visibility_is_observed_metadata_not_effective_instructions():
    value=wp._claude_init_customizations({'output_style':'Explanatory','skills':['one'],'agents':['Explore','Plan'],'slash_commands':['help']})
    assert value['source']=='claude.system/init'
    assert value['fields']['output_style']['value']=='Explanatory'
    assert value['fields']['skills']['shape']=='array' and value['fields']['skills']['value']==['one']
    assert value['fields']['agents']['reported_count']==2
    assert value['fields']['slash_commands']['value']==['help']
    assert value['effective_customization_closure']=='UNPROVEN'
    assert value['fields']['output_style']['effective_instruction_contents']=='UNOBSERVABLE'
    assert wp._claude_init_customizations({})['fields']['skills']['state']=='UNKNOWN'
    omitted=wp._claude_init_customizations({'skills':['x'*9000],'agents':{'custom':'uninterpreted'}})
    assert omitted['fields']['skills']['value'] is None and omitted['fields']['skills']['omitted_bytes']>0
    assert omitted['fields']['agents']['shape']=='object' and omitted['fields']['agents']['value'] is None
