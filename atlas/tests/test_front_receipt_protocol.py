"""Same retained semantic record: producer protocol tests, no new device/model execution."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from atlas.front import receipts as protocol
from atlas.front.receipts import (StageReceipt, FrontDoorReceipt, ReceiptProtocolError,
    serialize_dataset_run, verify_run, questions_of_run, primary_tree_of_run, recipe_of_run)

BASELINE=Path('/home/phujck/VScodeProjects/laplace/evidence/WRITING_JOINS_2026-10-04/codex-continuation/engine-consolidation-20261007/atlas-boundary/parent-evidence/source-run.json')
BASELINE_HASH='d5dcf2d27c6d46a11a6a5acf392bae100818aa78e23c401ff1fe1847033fa465'


@pytest.fixture
def legacy():
    raw=BASELINE.read_bytes();assert hashlib.sha256(raw).hexdigest()==BASELINE_HASH
    return json.loads(raw)['datasets']['toy']


def live(run):
    """A labelled serialization fixture; does not claim another actual execution."""
    rows=[];previous='';label=''
    for raw in run['receipt']['stages']:
        stage=StageReceipt(raw['stage'],label,previous,raw['emits'],copy.deepcopy(raw['executed']),
            raw['seconds'],raw['gate_seconds'],copy.deepcopy(raw['payload']),copy.deepcopy(raw.get('diagnostics',{})))
        rows.append(stage);previous=stage.address;label=stage.stage
    r=run['receipt'];return FrontDoorReceipt('atlas.front-door/1',r['dataset_id'],r['draw'],tuple(rows),r['seconds'])


def rechain(run):
    """Explicit fresh fixture identity, never a historical repair/accessor."""
    previous='';label=''
    for row in run['receipt']['stages']:
        row['consumes_address']=previous;row['consumes']=label
        row['address']=protocol._stage_address(row);previous=row['address'];label=row['stage']
    run['receipt']['chain']=[{k:r[k] for k in ('stage','consumes','consumes_address','address')} for r in run['receipt']['stages']]
    return run


def stage(run,name):return next(r for r in run['receipt']['stages'] if r['stage']==name)


def test_exact_baseline_round_trip_one_canonical_body_and_no_live_mutation(legacy):
    raw=copy.deepcopy(legacy);receipt=live(legacy);before=receipt.as_dict()
    compact=serialize_dataset_run('toy',receipt)
    assert receipt.as_dict()==before and legacy==raw
    assert compact['record']=='atlas.front-dataset-run/2' and compact['dataset']=='toy'
    assert compact['dataset_id']=='atlas-toy-corpus' and 'questions' not in compact
    assert verify_run(compact)
    assert questions_of_run(compact,expand=True)==legacy['questions']
    assert primary_tree_of_run(compact,expand=True)==stage(legacy,'tree')['payload']['per_lens'][0]
    old=len(json.dumps(legacy,separators=(',',':')).encode())
    new=len(json.dumps(compact,separators=(',',':')).encode())
    assert new<old*.75,(old,new)
    assert 'grading_receipt' not in stage(compact,'tree')['payload']
    assert set(stage(compact,'tree')['payload'])=={'primary_lens_id','per_lens'}
    assert 'cost_model' not in stage(compact,'read')['payload']
    assert 'cost_model_ref' in stage(compact,'read')['payload']


def test_legacy_known_locations_and_conflicting_copies_are_explicit(legacy):
    assert questions_of_run(legacy)==legacy['questions']
    inner=copy.deepcopy(legacy);inner.pop('questions');assert questions_of_run(inner)==legacy['questions']
    outer=copy.deepcopy(legacy);stage(outer,'read')['payload'].pop('questions');rechain(outer)
    assert questions_of_run(outer)==legacy['questions']
    bad=copy.deepcopy(legacy);bad['questions'][0]['text']='contradictory copy'
    with pytest.raises(ReceiptProtocolError,match='Ambiguous'):questions_of_run(bad)


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(record='atlas.front-dataset-run/99'),
    lambda r:r.update(dataset_id='wrong identity'),
    lambda r:r.update(questions=[]),
    lambda r:r['receipt']['stages'].append(copy.deepcopy(r['receipt']['stages'][-1])),
    lambda r:r['receipt']['stages'][-1]['payload'].update(terminal_corruption=True),
    lambda r:r['receipt']['stages'][-1].update(projection_version=99),
    lambda r:r['receipt'].update(chain_verified=False),
    lambda r:r['receipt']['chain'][-1].update(address='sha256:'+'f'*64),
])
def test_version_chain_terminal_and_envelope_corruption_refuse(legacy,mutation):
    r=serialize_dataset_run('toy',legacy);mutation(r)
    with pytest.raises(ReceiptProtocolError):verify_run(r)


def test_duplicate_question_lens_and_missing_stage_refs_refuse(legacy):
    for kind in ('question','lens','primary','read'):
        r=serialize_dataset_run('toy',legacy)
        if kind=='question':stage(r,'read')['payload']['questions'].append(copy.deepcopy(questions_of_run(r)[0]))
        elif kind=='lens':stage(r,'tree')['payload']['per_lens'].append(copy.deepcopy(stage(r,'tree')['payload']['per_lens'][0]))
        elif kind=='primary':stage(r,'tree')['payload']['primary_lens_id']='not present'
        else:r['receipt']['stages']=[s for s in r['receipt']['stages'] if s['stage']!='read']
        rechain(r)
        with pytest.raises(ReceiptProtocolError):verify_run(r)


@pytest.mark.parametrize('field,value',[
 ('stage','read'),('slot','unknown-slot'),('name','missing'),('basis_address','sha256:'+'f'*64)])
def test_wrong_contained_recipe_target_and_cycle_refuse(legacy,field,value):
    r=serialize_dataset_run('toy',legacy)
    ref=stage(r,'read')['payload']['cost_model_ref'];ref[field]=value;rechain(r)
    with pytest.raises(ReceiptProtocolError):verify_run(r)


def test_custom_recipe_meaning_is_not_overwritten_by_known_name(legacy):
    r=copy.deepcopy(legacy)
    for tolerance in stage(r,'question')['payload']['compiled'][0]['tolerances']:
        tolerance['derivation']='Custom independent recipe meaning.'
    r=rechain(r);r.pop('questions')
    compact=serialize_dataset_run('toy',r)
    first=stage(compact,'question')['payload']['compiled'][0]
    assert all('recipe_name' not in t and t['derivation']=='Custom independent recipe meaning.' for t in first['tolerances'])
    assert questions_of_run(compact,expand=True)==stage(r,'read')['payload']['questions']


def test_producer_diagnostic_variance_keeps_same_consumed_basis_and_manifest_pin(legacy):
    original=serialize_dataset_run('toy',live(legacy));changed=copy.deepcopy(legacy)
    stage(changed,'ingest')['payload']['ingest_receipt']['cut_seconds']+=99
    for lens in stage(changed,'tree')['payload']['per_lens']:
        lens['grading_receipt']['seconds']+=99
        lens['persist_receipt']['seconds']+=99
    stage(changed,'faces')['executed']['cost_model']['calibration_seconds']+=99
    stage(changed,'faces')['executed']['seconds_loading_this_lens']+=99
    for q in stage(changed,'read')['payload']['questions']:
        for supply in ('partial','whole'):
            q[supply]['seconds']+=99;q[supply]['executed']['answer_seconds']+=99
        q['plan']['planning_seconds']+=99
    modified=serialize_dataset_run('toy',live(changed))
    assert [r['address'] for r in modified['receipt']['stages']]==[r['address'] for r in original['receipt']['stages']]
    assert stage(modified,'tree')['payload']['per_lens'][0]['manifest_digest']==stage(original,'tree')['payload']['per_lens'][0]['manifest_digest']
    assert stage(modified,'read')['diagnostics']!=stage(original,'read')['diagnostics']
    assert questions_of_run(modified,expand=True)!=questions_of_run(original,expand=True)


@pytest.mark.parametrize('change',[
 lambda r:[model.update(launch_seconds=123.0) for model in
           (stage(r,'faces')['executed']['cost_model'],stage(r,'read')['payload']['cost_model'])],
 lambda r:[model.update(clock_resolution=123.0) for model in
           (stage(r,'faces')['executed']['cost_model'],stage(r,'read')['payload']['cost_model'])],
 lambda r:stage(r,'faces')['executed'].update(root_ranges=123),
 lambda r:stage(r,'tree')['payload']['per_lens'][0].update(manifest_digest='sha256:'+'f'*64),
 lambda r:stage(r,'read')['payload']['questions'][0]['partial'].update(answer='different'),
])
def test_decision_precision_count_source_and_answer_changes_remain_addressed(legacy,change):
    before=serialize_dataset_run('toy',live(legacy));changed=copy.deepcopy(legacy);change(changed)
    after=serialize_dataset_run('toy',live(changed))
    assert [r['address'] for r in before['receipt']['stages']]!=[r['address'] for r in after['receipt']['stages']]


def test_broken_admitted_live_chain_is_not_silently_repaired(legacy):
    receipt=live(legacy);receipt.stages[0].payload['declaration_hash']='changed after next stage consumed it'
    assert receipt.as_dict()['chain_verified'] is False
    with pytest.raises(ReceiptProtocolError,match='Broken admitted'):serialize_dataset_run('toy',receipt)


def test_hashes_are_reused_per_serialization_and_not_cached_across_mutation(legacy,monkeypatch):
    receipt=live(legacy);calls=[];actual=protocol.chash
    def counted(value):calls.append(value);return actual(value)
    monkeypatch.setattr(protocol,'chash',counted)
    receipt.as_dict();assert len(calls)==len(receipt.stages)
    calls.clear();serialize_dataset_run('toy',receipt)
    # Distinct original admitted and new v2 projection preimages, each once.
    assert len(calls)==2*len(receipt.stages)
    receipt.stages[0].payload['new']=1
    with pytest.raises(ReceiptProtocolError):serialize_dataset_run('toy',receipt)


def test_conditional_content_field_schema_parts_keep_quantities_without_execution():
    from atlas.record.content import content_build_parts
    from atlas.front.joint_section import joint_section_parts
    raw={'cut_seconds':1,'axis_seconds':{'axis':2},'token_seconds':3,'build_seconds':4,
         'leaves_built':5,'segmentation':{'hard_cap_tokens':512},'encoders':{'e':{'encode_seconds':6,'load_seconds':7,'texts_encoded':8}}}
    basis,diag=content_build_parts(raw)
    assert basis['leaves_built']==5 and basis['segmentation']==raw['segmentation']
    assert basis['encoders']['e']=={'texts_encoded':8} and diag['encoders']['e']['encode_seconds']==6
    section={'executed':{'encode_seconds':1,'descent_seconds':2,'seconds':3,'build_seconds':4,
                        'membership':{'quotient_seconds':5,'coupling_seconds':6,'rows':7},'encode_calls':8},'questions':{'Q':{'answer':9}}}
    basis,diag=joint_section_parts(section)
    assert basis['questions']==section['questions'] and basis['executed']['membership']=={'rows':7}
    assert basis['executed']['encode_calls']==8 and diag['executed']['membership']['coupling_seconds']==6


def _growth_fixture(legacy,count):
    fixture=copy.deepcopy(legacy);prototype=fixture['questions'][0]
    compiled=stage(fixture,'question')['payload']['compiled'][0]
    rows=[];compiled_rows=[]
    for index in range(count):
        qid=f'serialization-fixture:{index}';row=copy.deepcopy(prototype);row['qid']=qid
        row['plan']['qid']=qid
        for supply in ('partial','whole'):row[supply]['qid']=qid
        rows.append(row);item=copy.deepcopy(compiled);item['spec']['qid']=qid;compiled_rows.append(item)
    fixture['questions']=rows;stage(fixture,'read')['payload']['questions']=copy.deepcopy(rows)
    stage(fixture,'question')['payload']['compiled']=compiled_rows
    stage(fixture,'question')['diagnostics']['compiled_seconds']=[0.0]*count
    planner=stage(fixture,'read')['payload']['planner']
    planner['routes']={row['qid']:row['plan']['route'] for row in rows}
    planner['planning_seconds_per_question']={row['qid']:0.0 for row in rows}
    fixture['receipt']['draw']={'fixture_kind':'serialization_growth','questions':count,'not_device_execution':True}
    return rechain(fixture)


@pytest.mark.parametrize('count',[1,10,50])
def test_labelled_question_growth_keeps_fixed_recipe_once(legacy,count):
    fixture=_growth_fixture(legacy,count);compact=serialize_dataset_run('toy',fixture)
    assert len(questions_of_run(compact))==count
    assert len(stage(compact,'question')['payload']['tolerance_recipes'])==4
    text=json.dumps(compact,separators=(',',':'))
    for definition in stage(compact,'question')['payload']['tolerance_recipes'].values():
        assert text.count(json.dumps(definition['derivation'])[1:-1])==1
    assert len(text)<len(json.dumps(fixture,separators=(',',':')))


def test_outer_dataset_identity_and_raw_ref_shape_refuse(legacy):
    compact=serialize_dataset_run('toy',legacy)
    with pytest.raises(ReceiptProtocolError):verify_run({'record':'atlas.front-door-run/2','datasets':{'wrong':compact}})
    broken=copy.deepcopy(compact)
    stage(broken,'read')['payload']['cost_model_ref']['name']={'arbitrary':'pointer'};rechain(broken)
    with pytest.raises(ReceiptProtocolError):verify_run(broken)

@pytest.mark.parametrize('mutate',[
 lambda r:stage(r,'read')['diagnostics']['questions']['Q1']['partial']['executed'].update(rows_admitted=987654),
 lambda r:stage(r,'read')['diagnostics']['questions']['Q1']['flat_control'].update(answer='DIAGNOSTIC OVERRIDE'),
 lambda r:stage(r,'tree')['diagnostics']['per_lens'][stage(r,'tree')['payload']['primary_lens_id']]['persist_receipt'].update(persisted_bytes=987654),
 lambda r:stage(r,'read')['diagnostics']['questions'].update(wrong_identity={'partial':{'seconds':1.0}}),
 lambda r:stage(r,'read')['diagnostics']['questions']['Q1']['partial'].update(seconds='not a duration'),
])
def test_unaddressed_diagnostics_cannot_override_science_or_identity(legacy,mutate):
    r=serialize_dataset_run('toy',legacy);addresses=[row['address'] for row in r['receipt']['stages']]
    mutate(r);assert addresses==[row['address'] for row in r['receipt']['stages']]
    for reader in (verify_run,lambda run:questions_of_run(run,expand=True),lambda run:primary_tree_of_run(run,expand=True)):
        with pytest.raises(ReceiptProtocolError,match='diagnostic'):reader(r)


def test_root_version_cannot_wrap_other_dataset_version(legacy):
    compact=serialize_dataset_run('toy',legacy)
    with pytest.raises(ReceiptProtocolError,match='Mixed'):verify_run({'record':'atlas.front-door-run/1','datasets':{'toy':compact}})


def test_serializer_and_reader_use_same_identity_validation(legacy):
    receipt=live(legacy)
    from dataclasses import replace
    with pytest.raises(ReceiptProtocolError,match='dataset identity'):serialize_dataset_run('toy',replace(receipt,dataset_id='wrong identity'))
    mismatched=copy.deepcopy(legacy);stage(mismatched,'question')['payload']['compiled'][0]['spec']['qid']='wrong'
    with pytest.raises(ReceiptProtocolError,match='identities'):serialize_dataset_run('toy',live(mismatched))


def test_legacy_compiled_elapsed_is_retained_and_inline_reference_collision_refuses(legacy):
    r=copy.deepcopy(legacy);stage(r,'question')['payload']['compiled'][0]['seconds']=0.000587833987
    compact=serialize_dataset_run('toy',live(r))
    assert stage(compact,'question')['diagnostics']['compiled']['Q1']['seconds']==0.000587833987
    assert 'seconds' not in stage(compact,'question')['payload']['compiled'][0]
    for location in ('compiled','supply'):
        broken=copy.deepcopy(compact)
        if location=='compiled':stage(broken,'question')['payload']['compiled'][0]['tolerances'][0]['derivation']='inline contradiction'
        else:questions_of_run(broken)[0]['partial']['tolerance']['derivation']='inline contradiction'
        rechain(broken)
        with pytest.raises(ReceiptProtocolError,match='collision'):verify_run(broken)


def test_historical_conversion_and_readers_are_core_only(legacy):
    import subprocess,sys,os
    code=f"""import sys,importlib.abc,json
from pathlib import Path
class Missing(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {{'torch','triton','cupy','fastembed'}}:raise ModuleNotFoundError('heavy dependency blocked',name=fullname)
sys.meta_path.insert(0,Missing())
from atlas.front.receipts import serialize_dataset_run,verify_run,questions_of_run,primary_tree_of_run
r=json.loads(Path({str(BASELINE)!r}).read_text())['datasets']['toy']
v=serialize_dataset_run('toy',r);verify_run(v)
assert questions_of_run(v,expand=True)==r['questions']
assert primary_tree_of_run(v,expand=True)==next(s for s in r['receipt']['stages'] if s['stage']=='tree')['payload']['per_lens'][0]
assert not any(n.split('.')[0] in {{'torch','triton','cupy','fastembed'}} for n in sys.modules)
print('core-only')
"""
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([sys.executable,'-c',code],env={**os.environ,'PYTHONPATH':str(root/'src')},cwd=root,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='core-only'



def test_canonical_owner_normalization_is_detached_idempotent_and_refuses_corruption(legacy):
    from atlas.front.receipts import canonical_dataset_of_run
    before=copy.deepcopy(legacy);normalized=canonical_dataset_of_run(legacy)
    assert legacy==before and normalized==canonical_dataset_of_run(normalized)
    snapshot=canonical_dataset_of_run(normalized)
    questions_of_run(snapshot)[0]['partial']['answer']='caller mutation'
    assert snapshot!=normalized
    assert canonical_dataset_of_run(legacy)==normalized
    for bad in (copy.deepcopy(normalized),copy.deepcopy(legacy)):
        bad['receipt']['stages'][-1]['payload']['corruption']=True
        with pytest.raises(ReceiptProtocolError):canonical_dataset_of_run(bad)


@pytest.mark.parametrize('input_kind',['historical','live'])
def test_direct_serializer_draw_metadata_is_detached(legacy,input_kind):
    # Draw is metadata, but a returned observation must not expose mutable input.
    legacy['receipt']['draw']['nested_probe']={'values':[1]}
    receipt=legacy if input_kind=='historical' else live(legacy)
    before=copy.deepcopy(legacy) if input_kind=='historical' else receipt.as_dict()
    output=serialize_dataset_run('toy',receipt)
    output['receipt']['draw']['nested_probe']['values'].append(2)
    output['receipt']['draw']['new_probe']=True
    after=legacy if input_kind=='historical' else receipt.as_dict()
    assert after==before
    assert output['receipt']['draw']['nested_probe']['values']==[1,2]


def test_current_writer_metadata_keeps_explicit_historical_reader_contract(legacy):
    from atlas.front.receipts import FRONT_DOOR_RUN_RECORD
    assert FRONT_DOOR_RUN_RECORD=='atlas.front-door-run/2'
    assert verify_run({'record':'atlas.front-door-run/1','datasets':{'toy':legacy}})
    assert verify_run({'record':FRONT_DOOR_RUN_RECORD,
                       'datasets':{'toy':serialize_dataset_run('toy',legacy)}})


def test_current_writer_metadata_import_is_core_only():
    import subprocess,sys
    code="""import sys,importlib.abc
class Missing(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'torch','triton','cupy','fastembed'}:raise ModuleNotFoundError('heavy dependency blocked',name=fullname)
sys.meta_path.insert(0,Missing())
from atlas.front.receipts import FRONT_DOOR_RUN_RECORD
assert FRONT_DOOR_RUN_RECORD=='atlas.front-door-run/2'
assert not any(n.split('.')[0] in {'torch','triton','cupy','fastembed'} for n in sys.modules)
print(FRONT_DOOR_RUN_RECORD)
"""
    result=subprocess.run([sys.executable,'-c',code],text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='atlas.front-door-run/2'


def test_current_writer_root_emission_uses_declared_metadata(tmp_path,monkeypatch):
    from atlas.front import door
    from atlas.front.receipts import FRONT_DOOR_RUN_RECORD
    manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'root':str(tmp_path/'state'),'datasets':['engine'],
                                    'declared_draw':'J2-smoke'}))
    calls=[]
    def selected(name,root,**kwargs):
        calls.append(name)
        return {'fixture':'emission_metadata_only'}
    monkeypatch.setattr(door,'run_dataset',selected)
    output=door.run_front_door(manifest)
    assert output['record']==FRONT_DOOR_RUN_RECORD
    assert calls==['engine']


@pytest.mark.parametrize('field',['launch_seconds','clock_resolution','derivation'])
def test_contradictory_planner_model_copies_refuse_before_normalization(legacy,field):
    from atlas.front.receipts import canonical_dataset_of_run
    changed=copy.deepcopy(legacy)
    stage(changed,'faces')['executed']['cost_model'][field]='contradiction' if field=='derivation' else 123.0
    rechain(changed)
    for call in (verify_run,canonical_dataset_of_run,questions_of_run):
        with pytest.raises(ReceiptProtocolError,match='Contradictory planner'):call(changed)
    with pytest.raises(ReceiptProtocolError,match='Contradictory planner'):
        serialize_dataset_run('toy',changed)
    with pytest.raises(ReceiptProtocolError,match='Contradictory planner'):
        serialize_dataset_run('toy',live(changed))
    compact=serialize_dataset_run('toy',legacy)
    reading=stage(compact,'read')['payload'];reading.pop('cost_model_ref')
    reading['cost_model']=copy.deepcopy(stage(compact,'faces')['payload']['planner_cost']['model'])
    reading['cost_model'][field]='contradiction' if field=='derivation' else 123.0
    rechain(compact)
    for call in (verify_run,canonical_dataset_of_run,questions_of_run):
        with pytest.raises(ReceiptProtocolError,match='Contradictory planner'):call(compact)


def test_one_model_edition_and_single_available_location_preserve_basis(legacy):
    changed=copy.deepcopy(legacy)
    for model in (stage(changed,'faces')['executed']['cost_model'],stage(changed,'read')['payload']['cost_model']):
        model['launch_seconds']=123.0
    rechain(changed);output=serialize_dataset_run('toy',changed)
    assert recipe_of_run(output,stage(output,'read')['payload']['cost_model_ref'])['launch_seconds']==123.0
    assert verify_run(output)
    single=copy.deepcopy(legacy);stage(single,'faces')['executed'].pop('cost_model');rechain(single)
    output=serialize_dataset_run('toy',single)
    assert stage(output,'read')['payload']['cost_model']=={
        k:v for k,v in stage(single,'read')['payload']['cost_model'].items() if k!='calibration_seconds'}
    assert 'cost_model_ref' not in stage(output,'read')['payload']


def test_inline_and_reference_planner_model_collision_refuses(legacy):
    output=serialize_dataset_run('toy',legacy)
    stage(output,'read')['payload']['cost_model']=copy.deepcopy(stage(output,'faces')['payload']['planner_cost']['model'])
    rechain(output)
    with pytest.raises(ReceiptProtocolError,match='planner cost collision'):verify_run(output)


@pytest.mark.parametrize('count',[10,50])
@pytest.mark.parametrize('version',[1,2])
def test_batch_observation_hashes_once_per_stage_not_question(legacy,count,version,monkeypatch):
    fixture=_growth_fixture(legacy,count)
    if version==2:fixture=serialize_dataset_run('toy',fixture)
    before=copy.deepcopy(fixture);calls=[];original=protocol.chash
    def observed(value):
        calls.append(len(json.dumps(value,sort_keys=True,separators=(',',':')).encode()))
        return original(value)
    monkeypatch.setattr(protocol,'chash',observed)
    view=protocol.inspect_dataset_run(fixture)
    assert len(calls)==(18 if version==1 else 9)
    assert len(view['questions'])==count and fixture==before
    assert view['availability']['primary_tree']['status']=='AVAILABLE'
    assert view['availability']['planner_cost']['status']=='AVAILABLE'
    assert view['planner_cost']['launch_seconds']==stage(legacy,'read')['payload']['cost_model']['launch_seconds']
    assert all('recipe_ref' not in q['partial']['tolerance'] for q in view['questions'])
    assert sum(calls)>count*1000  # Actual payload is charged; no uncharged verified cache.


def test_batch_views_are_detached_resolved_and_never_cached_after_edit(legacy):
    before=copy.deepcopy(legacy);view=protocol.inspect_dataset_run(legacy,expand=True)
    assert view['questions']==legacy['questions']
    assert view['primary_tree']==stage(legacy,'tree')['payload']['per_lens'][0]
    assert view['planner_cost']==stage(legacy,'read')['payload']['cost_model']
    assert view['recipes']['tolerance_recipes']
    view['questions'][0]['partial']['answer']='edited view'
    view['dataset']['receipt']['draw']['edited']=True
    assert legacy==before
    assert protocol.inspect_dataset_run(legacy,expand=True)['questions']==before['questions']
    stage(view['dataset'],'read')['payload']['questions'][0]['partial']['answer']='unaddressed edit'
    with pytest.raises(ReceiptProtocolError):protocol.inspect_dataset_run(view['dataset'])


def test_batch_absent_optional_basis_is_separate_from_questions(legacy):
    fixture=serialize_dataset_run('toy',legacy)
    # This explicit partial-history fixture retains inline tolerance meaning;
    # deleting an earlier stage changes downstream addresses, so old refs cannot ride along.
    stage(fixture,'read')['payload']['questions']=protocol.inspect_dataset_run(fixture)['questions']
    fixture['receipt']['stages']=[row for row in fixture['receipt']['stages'] if row['stage']!='tree']
    stage(fixture,'faces')['payload'].pop('planner_cost')
    stage(fixture,'read')['payload'].pop('cost_model_ref')
    rechain(fixture);view=protocol.inspect_dataset_run(fixture)
    assert view['questions'] and view['availability']['questions']['status']=='AVAILABLE'
    assert view['primary_tree'] is None and view['availability']['primary_tree']['status']=='ABSENT'
    assert view['planner_cost'] is None and view['availability']['planner_cost']['status']=='ABSENT'
    assert all(value['reason'] for value in view['availability'].values())


@pytest.mark.parametrize('model',[None,{},'not a model'])
def test_batch_malformed_advertised_model_never_becomes_optional(legacy,model):
    fixture=serialize_dataset_run('toy',legacy)
    stage(fixture,'read')['payload'].pop('cost_model_ref')
    stage(fixture,'read')['payload']['cost_model']=model
    rechain(fixture)
    for call in (verify_run,protocol.inspect_dataset_run):
        with pytest.raises(ReceiptProtocolError,match='Malformed planner'):call(fixture)


@pytest.mark.parametrize('field,value',[
 ('launch_seconds',None),('clock_resolution',0),('repeats_launch',True),
 ('seconds_per_position',float('inf')),('derivation',123)])
def test_advertised_model_types_refuse_even_when_duplicate_copies_agree(legacy,field,value):
    fixture=copy.deepcopy(legacy)
    for model in (stage(fixture,'faces')['executed']['cost_model'],stage(fixture,'read')['payload']['cost_model']):
        model[field]=value
    rechain(fixture)
    for call in (verify_run,protocol.inspect_dataset_run):
        with pytest.raises(ReceiptProtocolError,match='Malformed planner'):call(fixture)


@pytest.mark.parametrize('version',[1,2])
def test_root_verification_reuses_same_child_observation_and_refuses_bad_child(legacy,version,monkeypatch):
    fixture=legacy if version==1 else serialize_dataset_run('toy',legacy)
    root={'record':f'atlas.front-door-run/{version}','datasets':{'toy':fixture}}
    calls=[];original=protocol.chash
    def observed(value):calls.append(value);return original(value)
    monkeypatch.setattr(protocol,'chash',observed)
    assert verify_run(root) and len(calls)==9
    for other in (1,2):
        if other==version:continue
        wrong=copy.deepcopy(root);wrong['record']=f'atlas.front-door-run/{other}'
        with pytest.raises(ReceiptProtocolError,match='Mixed run'):verify_run(wrong)
    bad=copy.deepcopy(root);bad['datasets']['toy']['receipt']['stages'][-1]['payload']['unaddressed']=True
    with pytest.raises(ReceiptProtocolError):verify_run(bad)
