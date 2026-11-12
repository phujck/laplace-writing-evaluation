"""Narrow real typed adapter/emission controls; no GPU tree or scientific run.

The same _question_stage is called by FrontDoor.answer_stage. Constructing an
already-compiled object here verifies that boundary, not ingestion/whole-front.
"""
import json
import copy
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys

import pytest
import torch

from atlas.front.door import FrontDoor
from atlas.front.question import (Condition, Operator, QuestionSpec, CompiledQuestion,
                                  as_query_plan, as_obligation_plan, toy_questions)
from atlas.front.receipts import Clock, FrontDoorReceipt, StageReceipt
from atlas.front.lift import lifted
from atlas.lifted import LiftSourceChanged

ROOT = Path(__file__).resolve().parents[2]


def compiled(conditions, payloads, *, text="Declared question", anchor=None, spec=None):
    spec = spec or QuestionSpec("Q-test", text, "controlled-record", "row",
        tuple(c for c in conditions if c.derived != "live_claims"), Operator("exists", "field"), 16384)
    coded = tuple({"condition": c, "row_kind": c.row_kind, "column": c.column,
                   "payload": payload, "codes": payload.get("codes", [payload["code"]]
                    if "code" in payload else None)} for c, payload in zip(conditions, payloads))
    return CompiledQuestion(spec, coded, (), anchor or {}, {}, 0.0)


def emission(value):
    door = FrontDoor.__new__(FrontDoor)
    door.stages = []
    return door, door._question_stage([value], Clock())


def fresh(code):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run([sys.executable, "-c", code], env=env, cwd=ROOT,
                          text=True, capture_output=True, timeout=30)


def test_existing_toy_q4_declarations_do_not_fabricate_english_claims():
    spec = next(q for q in toy_questions() if q.qid == "Q4")
    value = compiled(spec.conditions, [{"kind":"equality","code":i}
        for i in range(len(spec.conditions))], spec=spec)
    plan = as_query_plan(value)
    assert plan.version == "atlas.front.question/2" and not plan.claims
    assert len(plan.context_bindings) == len(spec.conditions)
    assert [c.surface for c in plan.lexical_candidates] == ["Leeds"]
    for candidate in plan.lexical_candidates:
        assert spec.text[candidate.span.start:candidate.span.end] == candidate.surface
        assert candidate.asserted_semantic_truth is False
    for index, binding in enumerate(plan.context_bindings):
        parsed = json.loads(binding.value)
        assert parsed["declaration"] == spec.conditions[index].as_dict()
        assert parsed["payload"] == value.payloads()[index]
        assert binding.field == "toy_row." + spec.conditions[index].column
    assert plan.evidence_obligations[0].context_binding_ids == tuple(b.id for b in plan.context_bindings)
    assert not plan.evidence_obligations[0].claim_ids


@pytest.mark.parametrize("condition,payload", [
    (Condition("equality","row","field",("absent",)), {"kind":"equality","code":7}),
    (Condition("equality","row","status",("rare",),derived="rarest declared status"),
     {"kind":"equality","code":9}),
    (Condition("membership","row","field",("first","second")), {"kind":"membership","codes":[3,5]}),
    (Condition("count_threshold","row","field",("first",),threshold=2,op=">="),
     {"kind":"count_threshold","code":3,"threshold":2,"op":">="}),
    (Condition("day","row","date",day="2026-10-08"), {"kind":"day","day":20734}),
    (Condition("day_interval","row","date",lo_day="2026-10-07",hi_day="2026-10-08"),
     {"kind":"day_interval","lo_day":20733,"hi_day":20734}),
])
def test_scalar_and_declared_list_round_trip_preserves_execution(condition,payload):
    value = compiled((condition,), (payload,), text="first then second then first")
    original = value.payloads()[0]
    plan = as_query_plan(value)
    restored = json.loads(json.loads(json.dumps(plan.to_dict()))["context_bindings"][0]["value"])
    assert restored == {"declaration":condition.as_dict(),"payload":payload}
    assert value.payloads()[0] is original
    if "code" in payload:assert value.as_dict()["coded"][0]["codes"] == [payload["code"]]
    assert value.spec.operator == Operator("exists","field") and value.spec.byte_budget == 16384
    for candidate in plan.lexical_candidates:
        assert value.spec.text[candidate.span.start:candidate.span.end] == candidate.surface


def test_multisurface_repeated_and_overlapping_occurrences_are_explicit():
    condition = Condition("membership","row","field",("aa","absent","other"))
    value = compiled((condition,), ({"kind":"membership","codes":[1,2,3]},),text="aaa other aa")
    plan = as_query_plan(value)
    assert [(c.surface,c.span.start,c.span.end) for c in plan.lexical_candidates] == [
        ("aa",0,2),("aa",1,3),("aa",10,12),("other",4,9)]
    assert len({c.id for c in plan.lexical_candidates}) == 4
    assert len(plan.context_bindings) == 1


def test_derived_codes_remain_live_only_and_stage_is_canonical_without_tensor_expansion(monkeypatch):
    declared = Condition("equality","row","field",("stated",))
    derived = Condition("membership","row","claim",derived="live_claims")
    codes = torch.arange(100_000, device="cpu")
    value = compiled((declared,derived), ({"kind":"equality","code":2},
                     {"kind":"membership","codes":codes}),text="stated")
    monkeypatch.setattr(torch.Tensor,"tolist",lambda *_:pytest.fail("runtime tensor expansion"))
    plan = as_query_plan(value)
    descriptor = json.loads(plan.context_bindings[1].value)["payload"]["codes"]
    assert descriptor == {"compiled_ref":{"dataset_id":"controlled-record","qid":"Q-test",
        "condition_index":1,"field":"payload.codes"},"availability":"live_compiled_question_only"}
    assert len(value.spec.conditions) == 1 and len(value.coded) == 2
    assert value.payloads()[1]["codes"] is codes
    # A JSON consumer receives a descriptor, not the actual set or a replay resolver.
    restored = json.loads(json.dumps(plan.to_dict()))
    assert json.loads(restored["context_bindings"][1]["value"])["payload"]["codes"] == descriptor
    assert isinstance(descriptor,dict) and not isinstance(descriptor,list)
    door, stage = emission(value)
    assert len(door.stages) == 1 and stage.address.startswith("sha256:")
    assert len(json.dumps(stage.as_dict())) < 16_384
    assert stage.payload["compiled"][0]["coded"][1]["codes"]["availability"] == "live_compiled_question_only"
    assert value.coded[1]["payload"]["codes"] is codes


def test_unresolved_anchor_keeps_existing_plan_postures_and_honest_spans():
    value = compiled((), (), text="Miso",anchor={"surfaces":["Miso"],"resolved":0})
    plan = as_query_plan(value); obligations = as_obligation_plan(value,plan)
    assert plan.status == "ambiguous" and obligations.status == "unsupported"
    assert plan.context_bindings[0].resolution == "unresolved"
    assert plan.lexical_candidates[0].surface == "Miso"
    assert obligations.attachments[0].recovery_text == "Miso"


@pytest.mark.parametrize("order", [("query_plan","query_obligations"),("query_obligations","query_plan")])
def test_real_consumer_load_orders_share_canonical_types(order):
    result = fresh(f"""from atlas.front.lift import lifted
from atlas.front.question import as_query_plan,as_obligation_plan,CompiledQuestion,QuestionSpec,Operator
for name in {order!r}:lifted(name)
q=CompiledQuestion(QuestionSpec('Q','plain','data','row',(),Operator('exists','field'),20),(),(),{{}},{{}},0)
p=as_query_plan(q);o=as_obligation_plan(q,p)
assert lifted('query_obligations').v1 is lifted('query_plan')
assert isinstance(p,lifted('query_obligations').v1.QueryPlan)
assert o.evidence_obligations[0] is p.evidence_obligations[0]
import sys
assert 'query_plan' not in sys.modules and 'query_obligations' not in sys.modules
print('single-canonical-owner')
""")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "single-canonical-owner"


def test_actual_question_emission_names_only_consumed_typed_closure():
    value = compiled((),())
    door,stage = emission(value)
    assert set(stage.payload["lifts"]["requested"]) == {"query_plan","query_obligations"}
    assert len(stage.payload["lifts"]["requested"]) == 2
    assert set(stage.payload["lifts"]["closure"]) == {"query_plan","query_obligations"}
    assert stage.payload["source_currentness"]["status"] == "CURRENT"
    assert stage.executed["typed_plan_objects"] == 1
    assert stage.payload["lifted_plan_shape"]["adapter_version"] == "atlas.front.question/2"
    chain = FrontDoorReceipt("fixture","controlled",{},tuple(door.stages),0).as_dict()
    historical = json.loads(json.dumps(chain));assert historical["chain_verified"] is True
    assert historical["stages"][0]["payload"]["lifts"]["modules"]


def test_simulated_changed_observation_refuses_question_emission_and_preserves_history(monkeypatch):
    """Caller integration only; A owns real disk mutation in a disposable prefix."""
    from atlas import lifted as owner
    value = compiled((),())
    _,stage = emission(value)
    historical = json.dumps(stage.as_dict(),sort_keys=True)
    source = Path(lifted("query_plan").__file__).resolve()
    original_observe = owner._observe
    def changed(path,work):
        result = original_observe(path,work)
        if Path(path).resolve()==source:
            result={**result,"sha256":"sha256:"+"f"*64}
        return result
    with monkeypatch.context() as scope:
        scope.setattr(owner,"_observe",changed)
        door = FrontDoor.__new__(FrontDoor);door.stages=[]
        with pytest.raises(LiftSourceChanged) as exc:
            door._question_stage([value],Clock())
        assert not door.stages and "query_plan" in str(exc.value)
        assert json.dumps(stage.as_dict(),sort_keys=True)==historical
    # Restoring the observation seam reuses the same genuine unmodified source.
    _,current=emission(value)
    assert current.payload["source_currentness"]["status"]=="CURRENT"


def test_preimported_unproved_source_cannot_emit_current_question_receipt():
    result=fresh("""import atlas.reconstruction.query_plan
from atlas.front.question import CompiledQuestion,QuestionSpec,Operator
from atlas.front.door import FrontDoor
from atlas.front.receipts import Clock
from atlas.lifted import LiftSourceChanged
q=CompiledQuestion(QuestionSpec('Q','plain','data','row',(),Operator('exists','field'),20),(),(),{}, {},0)
d=FrontDoor.__new__(FrontDoor);d.stages=[]
try:d._question_stage([q],Clock())
except LiftSourceChanged:assert not d.stages;print('unproved-refused')
else:raise AssertionError('unproved start basis accepted')
""")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "unproved-refused"


def test_core_front_metadata_and_help_import_no_heavy_optional_dependencies():
    result=fresh("""import sys
import atlas.front as front
assert 'FrontDoor' in dir(front)
assert front.StageReceipt.__module__=='atlas.front.receipts'
assert front.QuestionSpec.__module__=='atlas.front.question'
assert front.CompiledQuestion.__module__=='atlas.front.question'
from atlas.front.__main__ import main
try:main(['--help'])
except SystemExit as exc:assert exc.code==0
assert not any(n.split('.')[0] in {'torch','triton','cupy','fastembed'} for n in sys.modules)
print('core-help-only')
""")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("core-help-only")


def test_missing_numeric_capability_refuses_existing_cli_before_record_state(tmp_path):
    state=tmp_path/'record-root';manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({"root":str(state),"datasets":["toy"]}))
    result=fresh(f"""import importlib.abc,sys
class Missing(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {{'torch','triton'}}:raise ModuleNotFoundError('controlled absent dependency',name=fullname)
sys.meta_path.insert(0,Missing())
from atlas.front.__main__ import main
assert main([{str(manifest)!r}])==2
""")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "REFUSED"
    assert not state.exists()


def test_question_identity_ignores_only_separate_diagnostics_and_preserves_legacy_address():
    _, stage = emission(compiled((),()))
    changed = replace(stage, seconds=stage.seconds+4, gate_seconds=stage.gate_seconds+5,
                      diagnostics={"controlled_hash_seconds":999.0,"compiled_seconds":[11.0]})
    assert changed.address == stage.address
    assert changed.as_dict()["diagnostics"] != stage.as_dict()["diagnostics"]
    for section,field,value in [("source_currentness","status","UNPROVED")]:
        payload=copy.deepcopy(stage.payload);payload[section][field]=value
        assert replace(stage,payload=payload).address != stage.address
    payload=copy.deepcopy(stage.payload);payload["lifts"]["hash_work"]["bytes"]+=1
    assert replace(stage,payload=payload).address != stage.address
    executed={**stage.executed,"questions":stage.executed["questions"]+1}
    assert replace(stage,executed=executed).address != stage.address
    payload=copy.deepcopy(stage.payload)
    module=payload["lifts"]["modules"][0]
    module["first_adapter"]["sha256"]="sha256:"+"e"*64
    assert replace(stage,payload=payload).address != stage.address
    legacy=StageReceipt('legacy','','','typed',{'rows':2},3.0,4.0,{'item':'retained'})
    assert legacy.diagnostics=={}
    assert legacy.address=='sha256:490054f2035d6d8a3f4741c54480cff6ddfceb427ad02c06b02425daa5b44e1b'


@pytest.mark.parametrize("entry", ["dataset","front"])
def test_declared_toy_input_guard_precedes_record_tree_publication(tmp_path,monkeypatch,entry):
    from atlas.front.door import run_dataset,run_front_door,FrontInputUnavailable
    from atlas.record.ingest import toy
    absent=tmp_path/'absent-fixture.py';monkeypatch.setattr(toy,'FIXTURE_PATH',absent)
    state=tmp_path/'uncreated-state'
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({"root":str(state),"datasets":["toy"]}))
    with pytest.raises(FrontInputUnavailable) as exc:
        if entry=="dataset":run_dataset("toy",state)
        else:run_front_door(manifest)
    assert not state.exists()
    assert exc.value.result["reason"] == "FRONT-TOY-INPUT-UNAVAILABLE"
    assert exc.value.result["path"] == str(absent)
    assert exc.value.result["publication"] == "NOT_STARTED"
    assert "manifest.root" in exc.value.result["resolution"]


def test_genuine_absent_source_toy_input_returns_named_cli_refusal(tmp_path):
    from atlas.record.ingest import toy
    if toy.FIXTURE_PATH.is_file():
        pytest.skip("Tracked source fixture present; exact installed-prefix absent-input control belongs to parent")
    state=tmp_path/'uncreated-state';manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({"root":str(state),"datasets":["toy"]}))
    result=fresh(f"from atlas.front.__main__ import main;assert main([{str(manifest)!r}])==2")
    assert result.returncode==0,result.stderr
    refused=json.loads(result.stdout)
    assert refused["reason"]=="FRONT-TOY-INPUT-UNAVAILABLE"
    assert refused["input"]["path"]==str(toy.FIXTURE_PATH)
    assert refused["input"]["publication"]=="NOT_STARTED" and not state.exists()


@pytest.mark.parametrize("names", [("toy","missing"),("toy","toy"),"toy",{"toy":"value"},{"toy"},{}])
def test_selection_validation_refuses_whole_list_before_factories(names,monkeypatch,tmp_path):
    from atlas.front import draw
    from atlas.front.door import run_front_door
    calls=[]
    for name in draw.dataset_names():
        monkeypatch.setitem(draw._RUN_FACTORIES,name,lambda value,n=name:calls.append(n))
    with pytest.raises(draw.DatasetSelectionRefused):draw.runs_of_the_draw("J2-smoke",names=names)
    assert calls==[]
    state=tmp_path/'no-state';manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({"root":str(state),"datasets":names if not isinstance(names,set) else {"toy":"value"},"declared_draw":"J2-smoke"}))
    with pytest.raises(draw.DatasetSelectionRefused):run_front_door(manifest)
    assert calls==[] and not state.exists()


def test_cheap_names_default_all_and_explicit_selection_share_one_factory_owner(monkeypatch):
    from atlas.front import draw
    calls=[];expected={}
    for name in draw.dataset_names():
        expected[name]=object()
        def make(value,n=name):
            assert value is draw.DECLARED_DRAW
            calls.append(n);return expected[n]
        monkeypatch.setitem(draw._RUN_FACTORIES,name,make)
    assert draw.dataset_names()==tuple(expected) and not calls
    assert draw.runs_of_the_draw("J2-smoke")==expected
    assert calls==list(expected)
    calls.clear();assert draw.runs_of_the_draw("J2-smoke",names=[])==expected
    assert calls==list(expected)
    calls.clear();selected=draw.runs_of_the_draw("J2-smoke",names=("qasper","toy"))
    assert list(selected)==["qasper","toy"] and calls==["qasper","toy"]
    assert selected=={name:expected[name] for name in ("qasper","toy")}


def test_actual_manifest_selection_reaches_only_real_toy_factory_without_unrelated_io(tmp_path,monkeypatch):
    """Stops at numeric execution: real entry/factory/state wiring, no fake receipt."""
    from atlas.front import draw
    from atlas.front.door import run_front_door
    from atlas.record.ingest import toy
    if not toy.FIXTURE_PATH.is_file():
        pytest.skip("Exact source fixture needed for actual manifest selection; parent materializes it")
    calls=[];io=[];actual_toy=draw._RUN_FACTORIES["toy"]
    baseline=actual_toy(draw.DECLARED_DRAW).declaration().declaration_hash
    def selected(value):calls.append("toy");return actual_toy(value)
    monkeypatch.setitem(draw._RUN_FACTORIES,"toy",selected)
    def forbidden(value):pytest.fail("unrequested dataset factory constructed")
    for name in ("engine","longmem","qasper"):monkeypatch.setitem(draw._RUN_FACTORIES,name,forbidden)
    original_read=Path.read_bytes
    def observed(path):
        if "corpus_friction" in path.parts or "longmemeval" in str(path).lower() or "qasper" in str(path).lower():
            io.append(str(path));pytest.fail("unrequested input read")
        return original_read(path)
    monkeypatch.setattr(Path,"read_bytes",observed)
    class BeforeNumericExecution(Exception):pass
    def stop(door,**kwargs):
        assert door.run.dataset_id=="atlas-toy-corpus"
        assert door.run.declaration().declaration_hash==baseline
        raise BeforeNumericExecution
    monkeypatch.setattr(FrontDoor,"run_path",stop)
    state=tmp_path/'isolated-state';manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({"root":str(state),"datasets":["toy"],"declared_draw":"J2-smoke"}))
    with pytest.raises(BeforeNumericExecution):run_front_door(manifest)
    assert calls==["toy"] and io==[]
    assert not (state/'engine').exists() and not (state/'longmem').exists() and not (state/'qasper').exists()


@pytest.mark.parametrize("override,manifest_names", [
    ([],["toy"]),(None,["toy"]),(["toy"],["engine"]),
])
def test_actual_entry_empty_override_falls_through_and_nonempty_override_wins(tmp_path,monkeypatch,override,manifest_names):
    from atlas.front import draw
    from atlas.front.door import run_front_door
    from atlas.record.ingest import toy
    if not toy.FIXTURE_PATH.is_file():pytest.skip("Exact source fixture required")
    calls=[];actual=draw._RUN_FACTORIES["toy"]
    def selected(value):calls.append("toy");return actual(value)
    monkeypatch.setitem(draw._RUN_FACTORIES,"toy",selected)
    for name in ("engine","longmem","qasper"):
        monkeypatch.setitem(draw._RUN_FACTORIES,name,lambda value:pytest.fail("unrequested factory"))
    class StopBeforeNumeric(Exception):pass
    monkeypatch.setattr(FrontDoor,"run_path",lambda *_args,**_kwargs:(_ for _ in ()).throw(StopBeforeNumeric()))
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({"root":str(tmp_path/'state'),"datasets":manifest_names}))
    with pytest.raises(StopBeforeNumeric):run_front_door(manifest,datasets=override)
    assert calls==["toy"]


@pytest.mark.parametrize("override", [{},"",["toy","toy"]])
def test_malformed_override_cannot_fall_through_to_valid_manifest(tmp_path,override):
    from atlas.front.draw import DatasetSelectionRefused
    from atlas.front.door import run_front_door
    state=tmp_path/'no-state';manifest=tmp_path/'manifest.json'
    manifest.write_text(json.dumps({"root":str(state),"datasets":["toy"]}))
    with pytest.raises(DatasetSelectionRefused):run_front_door(manifest,datasets=override)
    assert not state.exists()
