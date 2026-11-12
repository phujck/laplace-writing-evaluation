"""Closed receipt diagnostic families shared by producers and offline readers.

This leaf imports no numerical or orchestration implementation. It classifies only
explicit producer elapsed fields; unknown substance remains in basis. Rejoining
unaddressed diagnostics requires closed schema/type/identity validation first.
"""
from __future__ import annotations
import math
from numbers import Real

def read_execution_parts(value):
    fields=diagnostic_fields('read_execution')
    return ({k:v for k,v in value.items() if k not in fields},
            {k:value[k] for k in fields if k in value})


def read_result_parts(value):
    basis = dict(value); diagnostic = {}
    if 'seconds' in basis:diagnostic['seconds'] = basis.pop('seconds')
    basis['executed'], diagnostic['executed'] = read_execution_parts(value.get('executed',{}))
    return basis, diagnostic


def control_receipt_parts(value):
    # Direct/packed control durations never feed the answer or admission predicate.
    return ({k:v for k,v in value.items() if k != 'seconds'},
            {'seconds':value['seconds']} if 'seconds' in value else {})


def cost_model_parts(value):
    return ({k:v for k,v in value.items() if k != 'calibration_seconds'},
            {'calibration_seconds':value['calibration_seconds']} if 'calibration_seconds' in value else {})


def question_plan_parts(value):
    return ({k:v for k,v in value.items() if k != 'planning_seconds'},
            {'planning_seconds':value['planning_seconds']} if 'planning_seconds' in value else {})


def cut_counts_receipt_parts(value):
    fields=diagnostic_fields('cut_counts')
    basis = {k:v for k,v in value.items() if k not in fields}
    diagnostic = {k:value[k] for k in fields if k in value}
    for name in ('loaded','built'):
        if name in value:
            basis[name] = [{k:v for k,v in row.items() if k != 'seconds'} for row in value[name]]
            diagnostic[name] = [{'column':row.get('column'),'seconds':row['seconds']}
                                for row in value[name] if 'seconds' in row]
    if isinstance(value.get('warm_equals_cold'),dict):
        row=value['warm_equals_cold'];basis['warm_equals_cold']={k:v for k,v in row.items() if k!='rebuild_seconds'}
        if 'rebuild_seconds' in row:diagnostic['warm_equals_cold']={'rebuild_seconds':row['rebuild_seconds']}
    return basis, diagnostic


def planner_execution_parts(value):
    fields=diagnostic_fields('planner_execution')
    basis={k:v for k,v in value.items() if k not in fields};diagnostic={k:value[k] for k in fields if k in value}
    if 'cost_model' in value:basis['cost_model'],diagnostic['cost_model']=cost_model_parts(value['cost_model'])
    if 'cut_counts' in value:basis['cut_counts'],diagnostic['cut_counts']=cut_counts_receipt_parts(value['cut_counts'])
    if isinstance(value.get('cut_counts_warm_equals_cold'),dict):
        row=value['cut_counts_warm_equals_cold'];basis['cut_counts_warm_equals_cold']={k:v for k,v in row.items() if k!='rebuild_seconds'}
        if 'rebuild_seconds' in row:diagnostic['cut_counts_warm_equals_cold']={'rebuild_seconds':row['rebuild_seconds']}
    return basis, diagnostic


def six_readings_parts(value):
    basis=dict(value);diagnostic={}
    if 'seconds' in basis:diagnostic['seconds']=basis.pop('seconds')
    if isinstance(value.get('marginal'),dict):
        row=dict(value['marginal'])
        if 'seconds' in row:diagnostic['marginal']={'seconds':row.pop('seconds')}
        basis['marginal']=row
    return basis,diagnostic


def joint_bank_parts(value):
    fields=diagnostic_fields('joint_bank')
    return ({k:v for k,v in value.items() if k not in fields}, {k:value[k] for k in fields if k in value})


def joint_counts_parts(value):
    basis=dict(value);diagnostic={}
    fields=diagnostic_fields('joint_counts')
    for name in ('integer_contraction','section_coupling'):
        if name in value:
            row=value[name];basis[name]={k:v for k,v in row.items() if k not in fields}
            diagnostic[name]={k:row[k] for k in fields if k in row}
    return basis,diagnostic


def joint_section_parts(value):
    basis=dict(value);diagnostic={}
    if 'executed' not in value:return basis,diagnostic
    fields=diagnostic_fields('joint_section')
    row=value['executed']
    executed={k:v for k,v in row.items() if k not in fields};diagnostic['executed']={k:row[k] for k in fields if k in row}
    if isinstance(row.get('membership'),dict):
        item=row['membership'];timers=diagnostic_fields('membership')
        executed['membership']={k:v for k,v in item.items() if k not in timers}
        diagnostic['executed']['membership']={k:item[k] for k in timers if k in item}
    basis['executed']=executed
    return basis,diagnostic


def opening_execution_parts(value):
    basis,diagnostic=planner_execution_parts(value)
    fields=diagnostic_fields('opening')
    for key in fields:
        if key in basis:diagnostic[key]=basis.pop(key)
    return basis,diagnostic


def coarse_counts_parts(value):
    basis=dict(value);diagnostic={}
    for name in ('sparse','dense'):
        if name in value:
            row=dict(value[name])
            if 'seconds' in row:diagnostic[name]={'seconds':row.pop('seconds')}
            basis[name]=row
    return basis,diagnostic


def compiled_question_parts(value):
    return ({k:v for k,v in value.items() if k != 'seconds'},
            {'seconds':value['seconds']} if 'seconds' in value else {})


def grading_receipt_parts(value):
    fields=diagnostic_fields('grading')
    basis={k:v for k,v in value.items() if k not in fields};diagnostic={k:value[k] for k in fields if k in value}
    if 'grade_spectra' in value:
        basis['grade_spectra']=[{k:v for k,v in row.items() if k!='proposal_seconds'} for row in value['grade_spectra']]
        diagnostic['grade_spectra']=[{'grade':row.get('grade'),'proposal_seconds':row['proposal_seconds']}
                                    for row in value['grade_spectra'] if 'proposal_seconds' in row]
    return basis,diagnostic


def persist_receipt_parts(value):
    fields=diagnostic_fields('persist')
    return ({k:v for k,v in value.items() if k not in fields}, {k:value[k] for k in fields if k in value})


def ingest_receipt_parts(value):
    fields=diagnostic_fields('ingest')
    basis={k:v for k,v in value.items() if k not in fields};diagnostic={k:value[k] for k in fields if k in value}
    if value.get('content'):basis['content'],diagnostic['content']=content_build_parts(value['content'])
    return basis,diagnostic


def open_receipt_parts(value):
    fields=diagnostic_fields('open')
    return ({k:v for k,v in value.items() if k not in fields}, {k:value[k] for k in fields if k in value})


def content_build_parts(value):
    fields=diagnostic_fields('content')
    basis={k:v for k,v in value.items() if k not in fields};diagnostic={k:value[k] for k in fields if k in value}
    if 'encoders' in value:
        basis['encoders']={};diagnostic['encoders']={}
        for name,row in value['encoders'].items():
            basis['encoders'][name],diagnostic['encoders'][name]=encoder_counter_parts(row)
    return basis,diagnostic


def encoder_counter_parts(value):
    fields=diagnostic_fields('encoder')
    return ({k:v for k,v in value.items() if k not in fields}, {k:value[k] for k in fields if k in value})

# The closed producer contracts. Duration names here are authoritative; producers
# choose their explicit family, never infer roles from key suffixes.
DURATION_FIELDS = {
 'read_execution': ('reduction_seconds','descent_seconds','answer_seconds','evidence_seconds','handles_seconds','postings_lookup_seconds','contraction_lookup_seconds','cut_counts_build_seconds_charged_to_the_first_question','cut_counts_seconds'),
 'cost_model': ('calibration_seconds',), 'question_plan': ('planning_seconds',),
 'cut_counts': ('load_seconds','build_seconds','seconds','rebuild_seconds'),
 'planner_execution': ('postings_seconds','seconds_opening_the_planner','planning_seconds','planning_seconds_per_question','planning_seconds_median_per_question','cut_counts_first_use_build_seconds_at_this_open','cut_counts_load_seconds','read_questions_seconds','reduction_seconds','batched_seconds','unbatched_seconds'),
 'read_stage_executed': ('joint_build_seconds','joint_contraction_seconds'),
 'joint_bank': ('build_seconds','contraction_seconds'),
 'joint_counts': ('seconds','block_build_seconds','block_contraction_seconds'),
 'joint_section': ('encode_seconds','descent_seconds','seconds','build_seconds'),
 'membership': ('quotient_seconds','coupling_seconds'),
 'opening': ('seconds_loading_this_lens','seconds_loading_the_second_lens','seconds_gathering_the_ranked_columns','seconds_opening_the_read_planner','seconds_loading_the_node_frames','seconds_building_the_joint_section_read','seconds_coarse_relation_counts','seconds_lateral_residual'),
 'grading': ('seconds','generator_seconds','proposal_seconds','up_seconds','gate_seconds'),
 'persist': ('serialise_seconds','encode_and_write_seconds','durability_seconds','seconds'),
 'ingest': ('extraction_seconds','load_seconds','cut_seconds','write_seconds','gate_seconds'),
 'open': ('read_seconds','project_seconds','anchor_seconds','gate_seconds'),
 'content': ('cut_seconds','axis_seconds','token_seconds','build_seconds'),
 'encoder': ('encode_seconds','load_seconds'), 'seconds': ('seconds',),
}


class DiagnosticContractError(ValueError):
    """Unaddressed data cannot masquerade as an accepted quantity or identity."""


def diagnostic_fields(family):
    if family not in DURATION_FIELDS:raise DiagnosticContractError('Unknown diagnostic family')
    return DURATION_FIELDS[family]


def _mapping(value,keys):
    if not isinstance(value,dict) or any(key not in keys for key in value):
        raise DiagnosticContractError('Unknown diagnostic field or shape')


def _elapsed(value):
    if isinstance(value,bool) or not isinstance(value,Real) or not math.isfinite(value):
        raise DiagnosticContractError('Diagnostic elapsed value must be a finite number')


def _durations(value,family):
    _mapping(value,diagnostic_fields(family))
    for key,item in value.items():
        if key in ('axis_seconds','planning_seconds_per_question'):
            if not isinstance(item,dict) or any(not isinstance(k,str) for k in item):raise DiagnosticContractError('Invalid timing identity map')
            for elapsed in item.values():_elapsed(elapsed)
        else:_elapsed(item)


def _family(value,family,basis):
    """Validate only named nested composition, not arbitrary tree traversal."""
    nested={
      'read_result':{'executed':'read_execution'},
      'planner_execution':{'cost_model':'cost_model','cut_counts':'cut_counts','cut_counts_warm_equals_cold':'warm_check'},
      'read_stage_executed':{'cost_model':'cost_model','cut_counts':'cut_counts','cut_counts_warm_equals_cold':'warm_check'},
      'opening':{'cost_model':'cost_model','cut_counts':'cut_counts','cut_counts_warm_equals_cold':'warm_check'},
      'cut_counts':{'loaded':'column_times','built':'column_times','warm_equals_cold':'warm_check'},
      'grading':{'grade_spectra':'grade_times'},
      'ingest':{'content':'content'}, 'content':{'encoders':'encoder_map'},
      'joint_section':{'executed':'section_execution'},
      'section_execution':{'membership':'membership'},
      'joint_counts':{'integer_contraction':'joint_count_times','section_coupling':'joint_count_times'},
      'coarse_counts':{'sparse':'seconds','dense':'seconds'},
      'six_readings':{'marginal':'seconds'},
    }
    plain={'read_result':'seconds','warm_check':None,'section_execution':'joint_section',
           'joint_count_times':'joint_counts','coarse_counts':None,'six_readings':'seconds'}.get(family,family)
    allowed=set(diagnostic_fields(plain)) if plain else set()
    if family=='warm_check':allowed={'rebuild_seconds'}
    if family in ('opening','read_stage_executed'):allowed|=set(diagnostic_fields('planner_execution'))
    children=nested.get(family,{})
    _mapping(value,allowed|set(children))
    direct={k:v for k,v in value.items() if k in allowed}
    if plain and family not in ('opening','read_stage_executed'):_durations(direct,plain)
    else:
        for key,item in direct.items():
            if key=='planning_seconds_per_question':
                qids=basis.get('routes',{}).keys()
                if not isinstance(item,dict) or any(q not in qids for q in item):raise DiagnosticContractError('Timing question identity disagrees')
                for elapsed in item.values():_elapsed(elapsed)
            else:_elapsed(item)
    if 'planning_seconds_per_question' in direct and any(q not in basis.get('routes',{}) for q in direct['planning_seconds_per_question']):raise DiagnosticContractError('Timing question identity disagrees')
    for key,child in children.items():
        if key not in value:continue
        if child in ('column_times','grade_times'):
            rows=value[key];original=basis.get(key,[]);identity='column' if child=='column_times' else 'grade'
            if not isinstance(rows,list):raise DiagnosticContractError('Timing rows must be a list')
            ids=[row.get(identity) for row in rows if isinstance(row,dict)]
            known=[row.get(identity) for row in original]
            if len(ids)!=len(rows) or len(set(ids))!=len(ids) or any(i not in known for i in ids):raise DiagnosticContractError('Timing row identity disagrees')
            elapsed_key='seconds' if child=='column_times' else 'proposal_seconds'
            for row in rows:_mapping(row,{identity,elapsed_key});_elapsed(row[elapsed_key])
        elif child=='encoder_map':
            if not isinstance(value[key],dict) or any(name not in basis.get(key,{}) for name in value[key]):raise DiagnosticContractError('Encoder timing identity disagrees')
            for name,row in value[key].items():_family(row,'encoder',basis[key][name])
        else:_family(value[key],child,basis.get(key,{}))


def validate_stage_diagnostics(stage,diagnostic,payload,executed):
    """Closed stage composition, using exact addressed qid/lens/grade identities."""
    families={
      'ingest':{'ingest_receipt':'ingest','open_receipt':'open','content_build':'content'},
      'faces':{'executed':'opening','coarse_relation_counts':'coarse_counts'},
      'read':{'executed':'read_stage_executed','planner':'planner_execution','joint_bank':'joint_bank','joint_section':'joint_section','six_readings':'six_readings','cost_model':'cost_model'},
    }
    allowed=set(families.get(stage,{}))
    if stage=='tree':allowed={'per_lens'}
    if stage=='question':allowed={'lifts','source_currentness','compiled_seconds','compiled'}
    if stage=='read':allowed.add('questions')
    _mapping(diagnostic,allowed)
    for key,family in families.get(stage,{}).items():
        if key in diagnostic:_family(diagnostic[key],family,executed if key=='executed' else payload.get(key,{}))
    if stage=='tree' and 'per_lens' in diagnostic:
        lenses={r['lens_id']:r for r in payload.get('per_lens',[])}
        _mapping(diagnostic['per_lens'],set(lenses))
        for name,row in diagnostic['per_lens'].items():
            _mapping(row,{'grading_receipt','persist_receipt'})
            for key,family in (('grading_receipt','grading'),('persist_receipt','persist')):
                if key in row:_family(row[key],family,lenses[name].get(key,{}))
    if stage=='read' and 'questions' in diagnostic:
        questions={r['qid']:r for r in payload.get('questions',[])}
        _mapping(diagnostic['questions'],set(questions))
        for qid,row in diagnostic['questions'].items():
            types={'plan':'question_plan','exact_joint_counts':'joint_counts','flat_control':'seconds','packed_direct_control':'seconds','partial':'read_result','whole':'read_result'}
            _mapping(row,set(types))
            for key,value in row.items():_family(value,types[key],questions[qid].get(key,{}))
    if stage=='question':
        qids=[r.get('spec',{}).get('qid') for r in payload.get('compiled',[])]
        if 'compiled_seconds' in diagnostic:
            if not isinstance(diagnostic['compiled_seconds'],list) or len(diagnostic['compiled_seconds'])!=len(qids):raise DiagnosticContractError('Compiled timing count disagrees')
            for item in diagnostic['compiled_seconds']:_elapsed(item)
        if 'compiled' in diagnostic:
            _mapping(diagnostic['compiled'],set(qids))
            for row in diagnostic['compiled'].values():_family(row,'seconds',{})
        # Existing lift owner guarantees these exact duration-only diagnostic keys.
        lift_keys={'hash_work_seconds','first_adapter_hash_work_seconds','first_adapter_file_hash_seconds','provenance_first_adapter_hash_seconds','package_first_adapter_hash_seconds','current_file_hash_seconds'}
        for name in ('lifts','source_currentness'):
            if name not in diagnostic:continue
            row=diagnostic[name];_mapping(row,lift_keys)
            known=set(payload.get('lifts',{}).get('closure',[]))|{'_provenance','__init__'}
            for key,value in row.items():
                if key.endswith('file_hash_seconds'):
                    _mapping(value,known)
                    for item in value.values():_elapsed(item)
                else:_elapsed(value)
