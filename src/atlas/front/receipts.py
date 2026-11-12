"""receipts.py - one frozen receipt per STAGE, chained by content address.

Each existing front stage records its counters and links to the preceding stage's
content address. Stages also use the FrontDoor's earlier record/lens/tree state;
this chain does not establish complete semantic dependency closure or current
implementation source. Source qualification is an explicit question-stage receipt
from the lifted owner. Historical chains remain readable without being promoted
into a current-source or numerical/scientific guarantee.

There is no measurement script anywhere in this package: the numbers are read off the tensors
and clocks of the code path that did the work, in the stage that did it (which is why
``record/measure.py``, ``record/f2_cli.py`` and ``grading/measure.py`` are deleted by this
packet - they were second readers of work they did not do).

Complexity: O(size of the payload) to hash; nothing here computes.
"""

from __future__ import annotations

import time
import copy
import math
from dataclasses import dataclass, field
from numbers import Real
from typing import Any

from ..ids import chash

__all__ = ["StageReceipt", "FrontDoorReceipt", "Clock", "ReceiptProtocolError",
           "serialize_dataset_run", "verify_run", "questions_of_run",
           "primary_tree_of_run", "recipe_of_run", "canonical_dataset_of_run",
           "FRONT_DOOR_RUN_RECORD", "inspect_dataset_run", "question_budget_evidence",
           "handle_identity_problem", "canonical_digest"]

# Current writer metadata is lightweight; it does not narrow known historical reads.
FRONT_DOOR_RUN_RECORD = 'atlas.front-door-run/2'


class Clock:
    """A stage's own clock, started BEFORE the expensive step (charter: "timers that start after
    the expensive step" are a forbidden move). O(1)."""

    __slots__ = ("started", "marks")

    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.marks: dict[str, float] = {}

    def mark(self, name: str) -> float:
        """Record the seconds since the clock started under ``name`` and return them."""
        value = time.perf_counter() - self.started
        self.marks[name] = value
        return value

    def since(self, at: float) -> float:
        return time.perf_counter() - at

    @property
    def seconds(self) -> float:
        return time.perf_counter() - self.started


@dataclass(frozen=True, slots=True)
class StageReceipt:
    """ONE stage: what it consumed, what it emitted, what work it EXECUTED, what its gate cost.

    ``diagnostics`` retains producer-owned timings outside the address, like
    ``seconds``/``gate_seconds``. Its absence preserves historical stage identities.
    ``executed`` holds only counters of work actually done (rows written, reduction calls made,
    positions opened, bytes read) - never a size that was merely declared. ``gate_seconds`` is
    the seconds this stage's own acceptance gate cost, separately from its work.
    """

    stage: str
    consumes: str                     # the name of the stage before it ("" for the first)
    consumes_address: str             # that stage's content address ("" for the first)
    emits: str                        # the typed object this stage hands on
    executed: dict[str, Any]
    seconds: float
    gate_seconds: float
    payload: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    projection_version: int = 1

    @property
    def address(self) -> str:
        """This receipt's content address, over its own payload AND its parent's address."""
        return _stage_address(_stage_fields(self))

    def as_dict(self) -> dict[str, Any]:
        return {**_stage_fields(self), "address": self.address}


@dataclass(frozen=True, slots=True)
class FrontDoorReceipt:
    """The whole path's receipt: the stages in order, chained, plus the one number each stage
    exists to produce. ``chain_verified`` is recomputed here, so a hand-edited stage payload
    breaks the chain rather than the report."""

    record: str
    dataset_id: str
    draw: dict[str, Any]
    stages: tuple[StageReceipt, ...]
    seconds: float

    def chain(self) -> list[dict[str, str]]:
        return [{"stage": s.stage, "consumes": s.consumes,
                 "consumes_address": s.consumes_address, "address": s.address}
                for s in self.stages]  # loop-ok: the declared stage list of the front door

    def chain_verified(self) -> bool:
        previous = ""
        for stage in self.stages:  # loop-ok: the declared stage list of the front door
            if stage.consumes_address != previous:
                return False
            previous = stage.address
        return True

    def as_dict(self) -> dict[str, Any]:
        # One observation, one hash per stage. No cache survives this call.
        stages=[_stage_fields(stage) for stage in self.stages]
        addresses=[_stage_address(stage) for stage in stages]
        try:_check_chain(stages,addresses);valid=True
        except ReceiptProtocolError:valid=False
        return {"record":self.record,"dataset_id":self.dataset_id,"draw":self.draw,
                "seconds":self.seconds,"chain_verified":valid,
                "chain":[{"stage":row['stage'],"consumes":row['consumes'],
                          "consumes_address":row['consumes_address'],"address":address}
                         for row,address in zip(stages,addresses)],
                "stages":[{**row,"address":address} for row,address in zip(stages,addresses)]}


class ReceiptProtocolError(ValueError):
    """A receipt is unavailable/ambiguous/corrupt; no current-source repair is attempted."""


_STAGE_ORDER=('declare','ingest','lens','tree','faces','question','read','evidence','update')
_DATASET_V2='atlas.front-dataset-run/2'


def _stage_fields(stage):
    row={"stage":stage.stage,"consumes":stage.consumes,"consumes_address":stage.consumes_address,
         "emits":stage.emits,"executed":stage.executed,"seconds":stage.seconds,
         "gate_seconds":stage.gate_seconds,"payload":stage.payload,"diagnostics":stage.diagnostics}
    if stage.projection_version!=1:row['projection_version']=stage.projection_version
    return row


def _stage_address(row):
    version=row.get('projection_version',1)
    if version not in (1,2):raise ReceiptProtocolError('Unknown stage projection version')
    basis={k:row[k] for k in ('stage','emits','executed','payload','consumes_address')}
    if version==2:basis.update(projection_version=2,consumes=row['consumes'])
    return chash(basis)


def _check_chain(rows,addresses):
    names=[r.get('stage') for r in rows]
    if len(set(names))!=len(names) or any(name not in _STAGE_ORDER for name in names):
        raise ReceiptProtocolError('Missing/duplicate/unknown stage identity')
    if names!=sorted(names,key=_STAGE_ORDER.index):raise ReceiptProtocolError('Stages out of order')
    previous='';label=''
    for row,address in zip(rows,addresses):
        if row.get('consumes_address')!=previous or row.get('consumes')!=label:
            raise ReceiptProtocolError('Broken admitted stage chain')
        previous=address;label=row['stage']


def _unique(rows,key,what):
    if not isinstance(rows,list):raise ReceiptProtocolError(what+' must be a list')
    ids=[r.get(key) for r in rows if isinstance(r,dict)]
    if len(ids)!=len(rows) or any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
        raise ReceiptProtocolError('Missing/duplicate '+what+' identity')
    return {r[key]:r for r in rows}


def _dataset(run,observed_addresses=None):
    if not isinstance(run,dict):raise ReceiptProtocolError('Dataset envelope must be a mapping')
    record=run.get('record')
    if record==_DATASET_V2:
        if set(run)!={'record','dataset','dataset_id','receipt'}:raise ReceiptProtocolError('Malformed v2 dataset envelope')
        if not isinstance(run.get('dataset_id'),str):raise ReceiptProtocolError('Missing dataset identity')
        version=2
    elif record is None and set(run)<= {'dataset','receipt','questions'} and 'receipt' in run:
        version=1
    else:raise ReceiptProtocolError('Unknown dataset envelope version')
    if not isinstance(run.get('dataset'),str) or not run['dataset']:raise ReceiptProtocolError('Missing dataset selector')
    receipt=run.get('receipt')
    if not isinstance(receipt,dict) or receipt.get('record')!=f'atlas.front-door/{version}':
        raise ReceiptProtocolError('Mismatched receipt envelope version')
    if version==2 and run['dataset_id']!=receipt.get('dataset_id'):raise ReceiptProtocolError('Mismatched dataset identity')
    rows=receipt.get('stages')
    if not isinstance(rows,list):raise ReceiptProtocolError('Missing stage list')
    addresses=[]
    if observed_addresses is not None and len(observed_addresses)!=len(rows):raise ReceiptProtocolError('Wrong address observation')
    for index,row in enumerate(rows):
        if not isinstance(row,dict):raise ReceiptProtocolError('Malformed stage')
        if version==2 and row.get('projection_version')!=2:raise ReceiptProtocolError('Missing v2 projection')
        if version==1 and row.get('projection_version',1)!=1:raise ReceiptProtocolError('Mixed legacy stage projection')
        try:address=_stage_address(row) if observed_addresses is None else observed_addresses[index]
        except (KeyError,TypeError) as error:raise ReceiptProtocolError('Malformed stage basis') from error
        if row.get('address')!=address:raise ReceiptProtocolError('Stored stage address does not match')
        addresses.append(address)
    _check_chain(rows,addresses)
    expected_chain=[{"stage":r['stage'],"consumes":r['consumes'],"consumes_address":r['consumes_address'],"address":a} for r,a in zip(rows,addresses)]
    if receipt.get('chain')!=expected_chain or receipt.get('chain_verified') is not True:raise ReceiptProtocolError('Stored chain summary disagrees')
    declared=next((r for r in rows if r['stage']=='declare'),None)
    if declared and declared['payload'].get('dataset_id')!=receipt.get('dataset_id'):
        raise ReceiptProtocolError('Declaration dataset identity disagrees')
    return version,{r['stage']:r for r in rows}


def _questions(run,stages):
    reading=stages.get('read')
    nested=reading['payload'].get('questions') if reading else None
    outer=run.get('questions')
    if nested is None and outer is None:raise ReceiptProtocolError('Read questions are unavailable')
    if nested is not None and outer is not None and nested!=outer:raise ReceiptProtocolError('Ambiguous legacy question copies')
    rows=nested if nested is not None else outer
    _unique(rows,'qid','question')
    return rows


def _resolve_recipe(stages,ref,before):
    if not isinstance(ref,dict) or set(ref)!={'stage','slot','name','basis_address'}:
        raise ReceiptProtocolError('Malformed contained recipe reference')
    if any(not isinstance(ref[k],str) or not ref[k] for k in ref):raise ReceiptProtocolError('Malformed recipe identity')
    stage=ref['stage'];slot=ref['slot']
    if (stage,slot) not in {('question','tolerance_recipes'),('faces','planner_cost')}:
        raise ReceiptProtocolError('Unknown producing stage/slot')
    if stage not in stages or _STAGE_ORDER.index(stage)>=_STAGE_ORDER.index(before):
        raise ReceiptProtocolError('Recipe must name an earlier contained stage')
    row=stages[stage]
    if ref['basis_address']!=row['address']:raise ReceiptProtocolError('Wrong contained recipe basis')
    table=row['payload'].get(slot)
    if not isinstance(table,dict) or ref['name'] not in table:raise ReceiptProtocolError('Missing contained recipe')
    value=table[ref['name']]
    if stage=='faces':
        if ref['name']!='model':raise ReceiptProtocolError('Malformed planner cost basis')
        _planner_cost_basis(value)
    return value


def _planner_cost_basis(value):
    from ..receipt_diagnostics import cost_model_parts
    prices=('launch_seconds','seconds_per_position','seconds_per_position_reduced','seconds_per_position_gathered','clock_resolution')
    counts=('repeats_launch','repeats_scan','repeats_reduction','repeats_gather','positions','gather_positions')
    fields=set(prices+counts)|{'derivation'}
    if not isinstance(value,dict) or not fields<=set(value):raise ReceiptProtocolError('Malformed planner cost basis')
    if any(isinstance(value[k],bool) or not isinstance(value[k],Real) or not math.isfinite(value[k]) or value[k]<0 for k in prices):
        raise ReceiptProtocolError('Malformed planner cost price')
    if any(type(value[k]) is not int or value[k]<(1 if k.startswith('repeats_') else 0) for k in counts):
        raise ReceiptProtocolError('Malformed planner cost count')
    if value['clock_resolution']<=0 or not isinstance(value['derivation'],str) or not value['derivation']:
        raise ReceiptProtocolError('Malformed planner cost precision/derivation')
    return cost_model_parts(value)[0]


def _validate_refs(stages,questions):
    question_stage=stages.get('question')
    if question_stage:
        table=question_stage['payload'].get('tolerance_recipes',{})
        if not isinstance(table,dict) or any(not isinstance(k,str) or not isinstance(v,dict) or set(v)!={'derivation'} or not isinstance(v['derivation'],str) for k,v in table.items()):raise ReceiptProtocolError('Malformed tolerance recipe definitions')
        for row in question_stage['payload'].get('compiled',[]):
            for tolerance in row.get('tolerances',[]):
                if 'recipe_name' in tolerance and ('derivation' in tolerance or 'recipe_ref' in tolerance):raise ReceiptProtocolError('Inline/local recipe collision')
                name=tolerance.get('recipe_name')
                if name is not None and (not isinstance(table,dict) or name not in table):
                    raise ReceiptProtocolError('Missing local tolerance recipe')
    for question in questions:
        for supply in ('partial','whole'):
            result=question.get(supply)
            if isinstance(result,dict):
                if result.get('qid')!=question['qid'] or result.get('supply')!=supply:raise ReceiptProtocolError('Question/supply identity disagrees')
                tolerance=result.get('tolerance',{})
                if 'recipe_ref' in tolerance and ('derivation' in tolerance or 'recipe_name' in tolerance):raise ReceiptProtocolError('Inline/reference recipe collision')
                if 'recipe_ref' in tolerance:_resolve_recipe(stages,tolerance['recipe_ref'],'read')
    reading=stages.get('read')
    if reading and 'cost_model_ref' in reading['payload']:
        _resolve_recipe(stages,reading['payload']['cost_model_ref'],'read')


def verify_run(run):
    """Validate contained versions, all hashes including terminal, identities and refs offline."""
    if isinstance(run,dict) and 'datasets' in run:
        if run.get('record') not in ('atlas.front-door-run/1',FRONT_DOOR_RUN_RECORD):
            raise ReceiptProtocolError('Unknown front run version')
        if not isinstance(run['datasets'],dict):raise ReceiptProtocolError('Malformed dataset map')
        for key,value in run['datasets'].items():
            if not isinstance(value,dict) or value.get('dataset')!=key:raise ReceiptProtocolError('Outer dataset key disagrees')
            version,_,_=_validated_dataset(value)
            if version!=int(run['record'][-1]):raise ReceiptProtocolError('Mixed run versions')
        return True
    _validated_dataset(run)
    return True


def _validate_planner_cost_copies(version,stages):
    # ReadPlanner creates one frozen CostModel. Faces records it at opening and
    # read records the same model used for route decisions, not a recalibration.
    # Elapsed calibration diagnostics remain separately preserved at each site.
    faces=stages.get('faces',{})
    if version==1:face_site=faces.get('executed',{});face_key='cost_model'
    else:
        face_site=faces.get('payload',{}).get('planner_cost',{})
        if not isinstance(face_site,dict) or ('planner_cost' in faces.get('payload',{}) and 'model' not in face_site):
            raise ReceiptProtocolError('Malformed planner cost basis')
        face_key='model'
    reading=stages.get('read',{}).get('payload',{})
    if 'cost_model' in reading and 'cost_model_ref' in reading:
        raise ReceiptProtocolError('Inline/reference planner cost collision')
    face_basis=_planner_cost_basis(face_site[face_key]) if face_key in face_site else None
    read_basis=_planner_cost_basis(reading['cost_model']) if 'cost_model' in reading else None
    if face_basis is not None and read_basis is not None:
        if face_basis!=read_basis:
            raise ReceiptProtocolError('Contradictory planner cost copies')


def _validated_dataset(run,observed_addresses=None):
    version,stages=_dataset(run,observed_addresses)
    questions=_questions(run,stages)
    _validate_planner_cost_copies(version,stages)
    if version==2:
        compiled=stages.get('question',{}).get('payload',{}).get('compiled',[])
        qids=[r.get('spec',{}).get('qid') for r in compiled]
        if compiled and (any(not isinstance(q,str) or not q for q in qids) or len(set(qids))!=len(qids)):raise ReceiptProtocolError('Duplicate compiled question identity')
        if compiled and set(qids)!={q['qid'] for q in questions}:raise ReceiptProtocolError('Compiled/read question identities disagree')
        if 'read' not in stages:raise ReceiptProtocolError('v2 has no canonical read stage')
        _validate_refs(stages,questions)
        tree=stages.get('tree')
        if tree:
            lenses=_unique(tree['payload'].get('per_lens',[]),'lens_id','lens')
            if tree['payload'].get('primary_lens_id') not in lenses:raise ReceiptProtocolError('Unknown primary lens')
            if 'per_lens' in tree['executed']:
                counters=_unique(tree['executed']['per_lens'],'lens_id','executed lens')
                if set(counters)!=set(lenses):raise ReceiptProtocolError('Per-lens execution identity disagrees')
    if version==1 and 'tree' in stages and 'per_lens' in stages['tree']['payload']:
        payload=stages['tree']['payload'];lenses=_unique(payload['per_lens'],'lens_id','lens')
        primary=lenses.get(payload.get('lens_id'))
        if primary is None:raise ReceiptProtocolError('Unknown legacy primary lens')
        if any(payload.get(k)!=v for k,v in primary.items()):raise ReceiptProtocolError('Contradictory legacy primary lens copies')
    from ..receipt_diagnostics import validate_stage_diagnostics, DiagnosticContractError
    if version==2:
        try:
            for name,row in stages.items():validate_stage_diagnostics(name,row.get('diagnostics',{}),row['payload'],row['executed'])
        except (DiagnosticContractError,KeyError,TypeError) as error:raise ReceiptProtocolError('Invalid diagnostic contract: '+str(error)) from error
    return version,stages,questions


def questions_of_run(run,*,expand=False):
    """One canonical compact list; expansion is explicit, transient and never banked."""
    version,stages,rows=_validated_dataset(run)
    return _question_view(stages,rows,expand=expand)


def _question_view(stages,rows,*,expand=False,resolve=False):
    if not expand and not resolve:return rows
    rows=copy.deepcopy(rows)
    diagnostic=stages.get('read',{}).get('diagnostics',{}).get('questions',{})
    for question in rows:
        diag=diagnostic.get(question['qid'],{}) if expand else {}
        for key in ('plan','flat_control','packed_direct_control'):
            if key in question:question[key].update(diag.get(key,{}))
        if 'exact_joint_counts' in question:
            for key in ('integer_contraction','section_coupling'):
                if key in question['exact_joint_counts']:question['exact_joint_counts'][key].update(diag.get('exact_joint_counts',{}).get(key,{}))
        for supply in ('partial','whole'):
            result=question.get(supply)
            if expand and isinstance(result,dict):
                details=diag.get(supply,{})
                if 'seconds' in details:result['seconds']=details['seconds']
                result.setdefault('executed',{}).update(details.get('executed',{}))
            if isinstance(result,dict) and 'recipe_ref' in result.get('tolerance',{}):
                tolerance=result['tolerance'];ref=tolerance.pop('recipe_ref')
                tolerance['derivation']=_resolve_recipe(stages,ref,'read')['derivation']
    return rows


def primary_tree_of_run(run,*,expand=False):
    version,stages,_=_validated_dataset(run)
    return _primary_tree_view(version,stages,expand=expand)


def _primary_tree_view(version,stages,*,expand=False):
    if 'tree' not in stages:raise ReceiptProtocolError('Tree stage unavailable')
    payload=stages['tree']['payload']
    if version==1:
        if 'per_lens' in payload:
            lenses=_unique(payload['per_lens'],'lens_id','lens');key=payload.get('lens_id')
            if key not in lenses:raise ReceiptProtocolError('Ambiguous legacy primary lens')
            for field,value in lenses[key].items():
                if payload.get(field)!=value:raise ReceiptProtocolError('Contradictory legacy primary lens copies')
            return copy.deepcopy(lenses[key]) if expand else lenses[key]
        return copy.deepcopy(payload) if expand else payload
    lenses=_unique(payload['per_lens'],'lens_id','lens')
    result=lenses.get(payload['primary_lens_id'])
    if result is None:raise ReceiptProtocolError('Primary lens unavailable')
    if not expand:return result
    result=copy.deepcopy(result);diag=stages['tree'].get('diagnostics',{}).get('per_lens',{}).get(payload['primary_lens_id'],{})
    if 'persist_receipt' in result:result['persist_receipt'].update(diag.get('persist_receipt',{}))
    if 'grading_receipt' in result:
        details=dict(diag.get('grading_receipt',{}));spectra=details.pop('grade_spectra',[])
        result['grading_receipt'].update(details)
        indexed={r['grade']:r['proposal_seconds'] for r in spectra}
        for row in result['grading_receipt'].get('grade_spectra',[]):
            if row.get('grade') in indexed:row['proposal_seconds']=indexed[row['grade']]
    return result


def recipe_of_run(run,ref):
    _,stages,_=_validated_dataset(run)
    return _resolve_recipe(stages,ref,'read')


def _project_stage(row,earlier):
    # Explicit closed producer schemas; this dispatch never scrubs arbitrary keys.
    payload=row['payload'];executed=row['executed'];diagnostic=copy.deepcopy(row.get('diagnostics',{}))
    name=row['stage']
    if name=='ingest':
        from ..receipt_diagnostics import ingest_receipt_parts,open_receipt_parts
        from ..receipt_diagnostics import content_build_parts
        for key,parts in (('ingest_receipt',ingest_receipt_parts),('open_receipt',open_receipt_parts),('content_build',content_build_parts)):
            if key in payload:payload[key],diagnostic[key]=parts(payload[key])
    elif name=='tree':
        from ..receipt_diagnostics import grading_receipt_parts,persist_receipt_parts
        lenses=payload.get('per_lens') or [dict(payload)]
        primary=payload.get('lens_id')
        _unique(lenses,'lens_id','lens')
        projected=[];diagnostic['per_lens']={}
        for lens in lenses:
            item=dict(lens);diag={}
            for key,parts in (('grading_receipt',grading_receipt_parts),('persist_receipt',persist_receipt_parts)):
                if key in item:item[key],diag[key]=parts(item[key])
            projected.append(item);diagnostic['per_lens'][item['lens_id']]=diag
        payload={'primary_lens_id':primary,'per_lens':projected}
    elif name=='faces':
        from ..receipt_diagnostics import opening_execution_parts,coarse_counts_parts
        executed,diagnostic['executed']=opening_execution_parts(executed)
        if 'cost_model' in executed:
            payload['planner_cost']={'model':executed.pop('cost_model')}
        if 'coarse_relation_counts' in payload:payload['coarse_relation_counts'],diagnostic['coarse_relation_counts']=coarse_counts_parts(payload['coarse_relation_counts'])
    elif name=='question':
        from ..receipt_diagnostics import compiled_question_parts
        from .question import TOLERANCE_LADDER
        recipes=dict(TOLERANCE_LADDER);used={};rows=[]
        diagnostic.setdefault('compiled',{})
        for compiled in payload.get('compiled',[]):
            item,diag=compiled_question_parts(compiled);tolerances=[]
            if diag:diagnostic['compiled'][item['spec']['qid']]=diag
            for tolerance in item.get('tolerances',[]):
                tolerance=dict(tolerance);key=tolerance.get('name')
                if key in recipes and tolerance.get('derivation')==recipes[key]:
                    used[key]={'derivation':tolerance.pop('derivation')};tolerance['recipe_name']=key
                tolerances.append(tolerance)
            item['tolerances']=tolerances;rows.append(item)
        payload['compiled']=rows;payload['tolerance_recipes']=used
    elif name=='read':
        from ..receipt_diagnostics import planner_execution_parts,question_plan_parts,six_readings_parts,cost_model_parts
        from ..receipt_diagnostics import read_result_parts,control_receipt_parts
        from ..receipt_diagnostics import joint_bank_parts,joint_counts_parts
        from ..receipt_diagnostics import joint_section_parts
        executed,diagnostic['executed']=planner_execution_parts(executed)
        for key,parts in (('planner',planner_execution_parts),('joint_bank',joint_bank_parts),('joint_section',joint_section_parts),('six_readings',six_readings_parts)):
            if key in payload:payload[key],diagnostic[key]=parts(payload[key])
        for key in ('joint_build_seconds','joint_contraction_seconds'):
            if key in executed:diagnostic['executed'][key]=executed.pop(key)
        questions=[];diagnostic['questions']={}
        for question in payload.get('questions',[]):
            item=dict(question);diag={}
            for key,parts in (('plan',question_plan_parts),('exact_joint_counts',joint_counts_parts),('flat_control',control_receipt_parts),('packed_direct_control',control_receipt_parts),('partial',read_result_parts),('whole',read_result_parts)):
                if key in item:item[key],diag[key]=parts(item[key])
            for supply in ('partial','whole'):
                if isinstance(item.get(supply),dict):
                    tolerance=dict(item[supply].get('tolerance',{}));key=tolerance.get('name');q=earlier.get('question')
                    if q and key in q['payload'].get('tolerance_recipes',{}) and tolerance.get('derivation')==q['payload']['tolerance_recipes'][key]['derivation']:
                        tolerance.pop('derivation');tolerance['recipe_ref']={'stage':'question','slot':'tolerance_recipes','name':key,'basis_address':q['address']}
                        item[supply]['tolerance']=tolerance
            questions.append(item);diagnostic['questions'][item['qid']]=diag
        payload['questions']=questions
        if 'cost_model' in payload:
            model,diagnostic['cost_model']=cost_model_parts(payload['cost_model']);faces=earlier.get('faces')
            if faces and faces['payload'].get('planner_cost',{}).get('model')==model:
                payload.pop('cost_model');payload['cost_model_ref']={'stage':'faces','slot':'planner_cost','name':'model','basis_address':faces['address']}
            else:payload['cost_model']=model
    row.update(payload=payload,executed=executed,diagnostics=diagnostic,projection_version=2)
    return row


def serialize_dataset_run(dataset,receipt):
    """Project this validated observation only; raw live/history objects are never mutated."""
    if not isinstance(dataset,str) or not dataset:raise ReceiptProtocolError('Exact dataset selector required')
    if isinstance(receipt,FrontDoorReceipt):
        if receipt.record not in ('atlas.front-door/1','atlas.front-door/2'):raise ReceiptProtocolError('Unknown live receipt version')
        raw=[copy.deepcopy(_stage_fields(s)) for s in receipt.stages]
        original_addresses=[_stage_address(s) for s in raw]
        _check_chain(raw,original_addresses)
        dataset_id=receipt.dataset_id;draw=receipt.draw;seconds=receipt.seconds
    elif isinstance(receipt,dict):
        verify_run(receipt)
        if receipt.get('record')==_DATASET_V2:raise ReceiptProtocolError('Already canonical v2; no reprojection')
        if receipt['dataset']!=dataset:raise ReceiptProtocolError('Dataset selector differs')
        item=receipt['receipt'];raw=copy.deepcopy(item['stages']);dataset_id=item['dataset_id'];draw=item['draw'];seconds=item['seconds']
    else:raise ReceiptProtocolError('Expected live receipt or exact legacy dataset envelope')
    return _serialize_observation(dataset,dataset_id,draw,seconds,raw)[0]


def _serialize_observation(dataset,dataset_id,draw,seconds,raw):
    stages=[];earlier={};previous='';label=''
    for row in raw:
        row=_project_stage(row,earlier);row.update(consumes_address=previous,consumes=label)
        row['address']=_stage_address(row);stages.append(row);earlier[row['stage']]=row
        previous=row['address'];label=row['stage']
    canonical={'record':_DATASET_V2,'dataset':dataset,'dataset_id':dataset_id,
               'receipt':{'record':'atlas.front-door/2','dataset_id':dataset_id,'draw':copy.deepcopy(draw),
                          'seconds':seconds,'chain_verified':True,
                          'chain':[{k:s[k] for k in ('stage','consumes','consumes_address','address')} for s in stages],
                          'stages':stages}}
    observation=_validated_dataset(canonical,[row['address'] for row in stages])
    return canonical,observation


def canonical_dataset_of_run(run):
    """One detached, verified per-call canonical observation; never cache verification.

    Known legacy input uses this same projection. Existing v2 addresses and
    diagnostics are copied unchanged. Readers normalize once per dataset.
    """
    return _canonical_observation(run)[0]


def _canonical_observation(run):
    snapshot=copy.deepcopy(run)
    observation=_validated_dataset(snapshot)
    if observation[0]==2:return snapshot,observation
    receipt=snapshot['receipt']
    return _serialize_observation(snapshot['dataset'],receipt['dataset_id'],
                                  receipt['draw'],receipt['seconds'],receipt['stages'])


def inspect_dataset_run(run,*,expand=False):
    """One detached verified observation and fixed resolved views, no science verdict.

    Hash/validate once per dataset, then resolve every view from the same private
    stage observation. Questions always resolve contained recipe meaning; only
    expand=True restores elapsed diagnostics. Optional absent tree/planner basis
    is named separately; malformed advertised data refuses. Returned values may
    share this new snapshot but never caller input, and are never cached as verified.
    """
    snapshot,(version,stages,rows)=_canonical_observation(run)
    questions=_question_view(stages,rows,expand=expand,resolve=True)
    tree=_primary_tree_view(version,stages,expand=expand) if 'tree' in stages else None
    reading=stages['read']['payload'];model=None
    if 'cost_model_ref' in reading:model=_resolve_recipe(stages,reading['cost_model_ref'],'read')
    elif 'cost_model' in reading:model=reading['cost_model']
    if expand and model is not None:
        model=copy.deepcopy(model)
        model.update(stages['read'].get('diagnostics',{}).get('cost_model',{}))
    recipes=stages.get('question',{}).get('payload',{}).get('tolerance_recipes',{})
    def availability(present,reason):
        return {'status':'AVAILABLE' if present else 'ABSENT','reason':reason}
    return {'dataset':snapshot,'questions':questions,'primary_tree':tree,
            'planner_cost':model,'recipes':{'tolerance_recipes':recipes},
            'availability':{'questions':availability(True,'Canonical read question list'),
                            'primary_tree':availability(tree is not None,'Primary tree basis' if tree is not None else 'No retained tree stage'),
                            'planner_cost':availability(model is not None,'Read-consumed planner model' if model is not None else 'No retained read planner model')}}


_BUDGET_COUNTERS = ('rows_supplied', 'bytes_supplied', 'rows_needed', 'bytes_needed')
_HANDLE_FIELDS = ('row_id', 'row_kind', 'global_ordinal', 'content_handle', 'start', 'end', 'bytes')
_IDENTITY_FIELDS = ('row_id', 'row_kind', 'content_handle', 'start', 'end')


def _count(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def canonical_digest(value):
    """A canonical content address: 'sha256:' and 64 lowercase hex digits."""
    return (isinstance(value, str) and len(value) == 71 and value.startswith('sha256:')
            and all(char in '0123456789abcdef' for char in value[7:]))


def handle_identity_problem(row, *, with_ordinal=False, with_bytes=True):
    """None when `row` is a complete typed row identity, else what is wrong (M5 S3): a canonical row id and
    content handle, a nonempty row kind, a span 0 <= start < end and, when present, bytes == end - start.
    Presence is not identity: a field of the wrong type or value refuses."""
    if not isinstance(row, dict):
        return 'not a mapping'
    names = _IDENTITY_FIELDS + (('global_ordinal',) if with_ordinal else ()) + (('bytes',) if with_bytes else ())
    missing = [name for name in names if name not in row]
    if missing:
        return 'missing ' + ','.join(missing)
    if not canonical_digest(row['row_id']):
        return 'row_id is not a canonical digest'
    if not canonical_digest(row['content_handle']):
        return 'content_handle is not a canonical digest'
    if not isinstance(row['row_kind'], str) or not row['row_kind'] or len(row['row_kind']) > 64:
        return 'row_kind is not a bounded nonempty string'
    if not _count(row['start']) or not _count(row['end']) or row['start'] >= row['end']:
        return 'span is not 0 <= start < end'
    if with_ordinal and not _count(row['global_ordinal']):
        return 'global_ordinal is not a count'
    if with_bytes and (not _count(row['bytes']) or row['bytes'] != row['end'] - row['start']):
        return 'bytes is not end - start'
    return None


def question_budget_evidence(question):
    """One question's joint-read evidence per byte budget, normalized for representation only (M5 S3).

    The current producer nests each budget as evidence_by_budget[budget] = {'partial': {...}, 'whole': {...}};
    that shape is returned as 'nested-partial-whole/1' with its counters and the bounded identity list the read
    retained (handles, supplied_global_rows). Any other shape - a historical flat budget map, a missing or
    malformed counter, a handle without its identity fields - is refused, never coerced. Counts are copied as
    recorded: this accessor states what the receipt says, not which rows a budget paid for or whether any of
    them is gold (no ordered paid-row identities are part of this receipt shape).
    """
    if not isinstance(question, dict) or not isinstance(question.get('qid'), str) or not question['qid']:
        raise ReceiptProtocolError('Question identity is missing')
    joint = question.get('joint_section_read')
    if not isinstance(joint, dict):
        raise ReceiptProtocolError('Question has no joint-section read evidence')
    by_budget = joint.get('evidence_by_budget')
    if not isinstance(by_budget, dict) or not by_budget:
        raise ReceiptProtocolError('Joint-section read has no per-budget evidence')
    budgets = {}
    for key, value in by_budget.items():
        if not isinstance(key, str) or not key.isdigit() or str(int(key)) != key or int(key) in budgets:
            raise ReceiptProtocolError('Budget key is not one canonical byte budget')
        budget = int(key)
        if not isinstance(value, dict) or set(value) != {'partial', 'whole'}:
            raise ReceiptProtocolError('Budget evidence is not the nested partial/whole shape; it is not coerced')
        rows = {}
        for supply in ('partial', 'whole'):
            entry = value[supply]
            if (not isinstance(entry, dict) or entry.get('supply') != supply or entry.get('byte_budget') != budget
                    or any(not _count(entry.get(name)) for name in _BUDGET_COUNTERS)):
                raise ReceiptProtocolError('Malformed ' + supply + ' evidence for budget ' + str(budget))
            rows[supply] = {name: entry[name] for name in _BUDGET_COUNTERS}
        budgets[budget] = rows
    handles = joint.get('handles', [])
    if not isinstance(handles, list):
        raise ReceiptProtocolError('Joint-section handles are malformed')
    seen = set()
    for row in handles:
        problem = handle_identity_problem(row, with_ordinal=True)
        if problem:
            raise ReceiptProtocolError('Joint-section handle refused: ' + problem)
        if row['row_id'] in seen:
            raise ReceiptProtocolError('Joint-section handle repeats a row identity')
        seen.add(row['row_id'])
    supplied = joint.get('supplied_global_rows', [])
    if not isinstance(supplied, list) or any(not _count(value) for value in supplied):
        raise ReceiptProtocolError('Supplied rows are malformed')
    return {'qid': question['qid'], 'shape': 'nested-partial-whole/1', 'budgets': dict(sorted(budgets.items())),
            'handles': [{name: row[name] for name in _HANDLE_FIELDS} for row in handles],
            'supplied_global_rows': list(supplied)}
