"""Workflow capability, context and actual-use projections at existing owners.

No execution loop or new store lives here. Definition decisions use the existing
dispatch journal and definition/Work admission locks. Run events remain Work/WD
and writing-session facts, with explicit lazy body reads.
"""
from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path

from laplace.core.identity import canonical_digest
from laplace.work import owner_discovery as O

FACETS = ('execution-preview', 'uses', 'river', 'context', 'creation-choices','withdrawal-preview')
DECISION = 'workflow-request-decision'
SCHEMA = 'laplace.workflow-operation/1'
LOOP_SCHEMA = 'laplace.workflow-loop-decision/1'
STOP_SCHEMA = 'laplace.workflow-stop-composition/1'
SYNTHESIS_SCHEMA = 'laplace.workflow-research-synthesis/1'
# A prepared plan carries every field the run-owner synthesis publication
# consumes. Plans prepared without it are refused, never silently upgraded.
BRIDGE = 'laplace.workflow-synthesis-bridge/1'
SYNTHESIS_STATUSES = ('COMPLETE', 'BLOCKED', 'PARTIAL')
SYNTHESIS_DUE = frozenset({'LIMIT_REACHED', 'AWAITING_HUMAN_APPLY', 'APPLIED', 'PARTIAL', 'STOP_BEFORE_NEXT'})
SETTLED = ('RESULT', 'STALE', 'UNCONFIRMED')
# Raw page fields of read_artifact. Any other recorded selection (pointer,
# record, projection) is a legitimate read but never whole-input coverage.
WHOLE_READ_FIELDS = frozenset({'id', 'path', 'scope', 'expected_sha256', 'offset', 'limit', 'project'})
# Existing delivery bounds, named for consumers; not a new or raised cap.
DELIVERY_LIMITS = {'utf8_bytes': 100000, 'entries': 24}


def _D():
    from laplace.pipeline import workflow_definitions
    return workflow_definitions


def read_contract(facet=None):
    properties={'facet': {'enum': list(FACETS)}, 'reference': {'type': 'object'},
            'definition_id': {'type': 'string'}, 'version': {'type': 'string'},'project_lens':{'type':'string','minLength':1},
            'definition': {'type': 'object'}, 'scope': {'type': 'object'},
            'step_ids': {'type': 'array', 'maxItems': 64, 'uniqueItems': True, 'items': {'type': 'string'}},
            'work_id': {'type': 'string'}, 'versions': {'enum': ['selected', 'all']},
            'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 20},
            'as_of': {'type': 'string'}, 'step_id': {'type': 'string'},
            'request_token':{'type':'string','minLength':1,'maxLength':120},
            'operation':{'enum':['save','prepare']},'original_request':{'type':'object'}}
    identity={'reference','definition_id','version'};page={'offset','limit','as_of'}
    fields={'execution-preview':identity|page|{'definition','scope','step_ids'},
        'context':identity|page|{'definition','scope','step_ids','step_id'},
        'uses':identity|page|{'versions'},'river':identity|page|{'work_id'},
        'creation-choices':page,'withdrawal-preview':{'operation','original_request'}}
    result=[]
    for current,names in fields.items():
        variant={'type':'object','additionalProperties':False,'properties':{k:copy.deepcopy(properties[k]) for k in names|{'facet','project_lens','request_token'}},'required':['facet']}
        variant['properties']['facet']={'const':current}
        if current=='withdrawal-preview':variant['required']+=['operation','original_request']
        elif current!='creation-choices':
            variant['anyOf']=[{'required':[key]} for key in ('definition','reference','definition_id') if key in names]
            if current in {'execution-preview','context'}:variant['allOf']=[{'if':{'required':['definition']},'then':{'not':{'anyOf':[{'required':['reference']},{'required':['definition_id']},{'required':['version']}]}}}]
            if current=='river':variant['required'].append('work_id')
            if current=='context':variant['required'].append('step_id')
        result.append(variant)
    if facet is not None:return next(v for v in result if v['properties']['facet']['const']==facet)
    return {'oneOf':result}


def context_contract():
    return {'type': 'array', 'maxItems': 24, 'uniqueItems': True, 'items': {'oneOf': [
        {'type': 'object', 'additionalProperties': False, 'required': ['kind', 'step_id'],
         'properties': {'kind': {'enum': ['ancestor-instructions', 'upstream-return']}, 'step_id': {'type': 'string'}}},
        {'type': 'object', 'additionalProperties': False, 'required': ['kind'],
         'properties': {'kind': {'enum': ['selected-evidence', 'previous-review-findings', 'parent-message']}}}]}}


def handoff_contract():
    return {'type': 'object', 'additionalProperties': False,
        'properties': {'purpose': {'type': 'string', 'maxLength': 2000},
            'expected_output': {'type': 'string', 'maxLength': 4000},
            'downstream': {'type': 'array', 'maxItems': 64, 'uniqueItems': True, 'items': {'type': 'string'}}}}


def withdraw_contract():
    return {'type': 'object', 'additionalProperties': False,
        'required': ['action', 'operation', 'request_id', 'intent_digest', 'original_request'],
        'properties': {'action': {'const': 'withdraw'}, 'operation': {'enum': ['save', 'prepare']},
            'request_id': {'type': 'string', 'minLength': 1, 'maxLength': 120},
            'intent_digest': {'type': 'string', 'pattern': '^sha256:[a-f0-9]{64}$'},
            'original_request': {'type': 'object'}}}


def validate_declarations(body):
    from jsonschema import Draft202012Validator
    D = _D(); steps = {s['id']: s for s in body['steps']}
    for step in steps.values():
        assignment = step['assignment']
        for field, contract in (('context', context_contract()), ('handoff', handoff_contract())):
            if field in assignment and next(Draft202012Validator(contract).iter_errors(assignment[field]), None):
                raise D.Refused('INVALID_ROLE_DELIVERY', step_id=step['id'], field=field)
        for target in assignment.get('handoff', {}).get('downstream', []):
            if target not in steps: raise D.Refused('HANDOFF_TARGET_MISSING', step_id=step['id'])
        ancestors = set(); parent = step.get('parent_id')
        while parent is not None:
            ancestors.add(parent); parent = steps[parent].get('parent_id')
        for entry in assignment.get('context', []):
            if entry['kind'] == 'ancestor-instructions' and entry['step_id'] not in ancestors:
                raise D.Refused('CONTEXT_NOT_AN_ANCESTOR', step_id=step['id'])
            if entry['kind'] == 'upstream-return' and not any(
                    edge['from'] == entry['step_id'] and edge['to'] == step['id'] and edge['kind'] == 'control'
                    for edge in body.get('edges', [])):
                raise D.Refused('CONTEXT_NOT_AN_UPSTREAM_RETURN', step_id=step['id'])


def operation_handle(caller,payload,*,post=False):
    D=_D();payload=copy.deepcopy(payload)
    if not post and 'definition' not in payload:return D.scoped_handle(caller,**payload)
    definition=payload.pop('definition',None)
    if caller.kind=='project':payload['project_lens']=caller.namespace
    return {'http':{'method':'POST','url':'/work/workflow-definitions','payload':copy.deepcopy(payload)},
        'native':{'operation':'project','payload':{'view':'workflow-definitions','request':copy.deepcopy(payload)}},
        'sdk':{'method':'workflow_request','payload':copy.deepcopy(payload)},'request':payload,'read_only':True,
        **({'required_inputs':['definition'],'definition_digest':canonical_digest(definition)} if definition is not None else {})}


def preview_offer(caller):
    return {'read':operation_handle(caller,{'facet':'execution-preview'},post=True),
        'request_contract':read_contract('execution-preview'),'required_inputs':['definition','scope','step_ids'],
        'meaning':'Pure draft capability preview; no save, preparation, permission or run effect.'}


def withdrawal_offer(operation,caller):
    return {'prepare_read':operation_handle(caller,{'facet':'withdrawal-preview','operation':operation},post=True),
        'required_inputs':['original_request'],'request_contract':read_contract('withdrawal-preview'),
        'meaning':'Owner computes the exact original intent; do not guess cross-language JSON number canonicalisation. Reading starts or withdraws nothing.'}


def _withdrawal_handle(operation,caller,original,digest):
    payload={'action':'withdraw','operation':operation,'request_id':original['request_id'],'intent_digest':digest}
    from urllib.parse import urlencode
    url='/work/workflow-definitions/withdraw'+('?' + urlencode({'project_lens':caller.namespace}) if caller.kind=='project' else '')
    return {'http':{'method':'POST','url':url,'payload':payload},
        'native':{'operation':'workflow_definition_change','payload':copy.deepcopy(payload)},
        'sdk':{'method':'workflow_withdraw','payload':copy.deepcopy(payload)},
        'request_contract':withdraw_contract(),'required_inputs':['original_request'],
        'original_request_digest':digest,
        'permitted':_D()._can_save(caller),'meaning':'Use the exact original definition-owner request without adapter action/project. Receipt wins under the same admission lock; UNKNOWN is never cancellation.'}


def instruction(body, step_id):
    """Deterministic declared text only; delivery is separate from permission."""
    steps = {s['id']: s for s in body['steps']}; step = steps[step_id]; parts = []; origins = []
    for entry in step['assignment'].get('context', []):
        if entry['kind'] == 'ancestor-instructions':
            value = steps[entry['step_id']]['assignment'].get('instructions', '')
            parts.append('EXPLICIT GROUP INSTRUCTIONS (' + entry['step_id'] + ')\n' + value)
            origins.append({'kind': entry['kind'], 'step_id': entry['step_id'], 'sha256': canonical_digest(value), 'characters': len(value),
                'utf8_bytes': len(value.encode()), 'custody': 'definition-version-body'})
    local = step['assignment'].get('instructions', '')
    parts.append(local); origins.append({'kind': 'local-instructions', 'step_id': step_id, 'sha256': canonical_digest(local), 'characters': len(local),
        'utf8_bytes': len(local.encode()), 'custody': 'definition-version-body'})
    criteria = loop_criteria(body, step)
    if criteria is not None:
        parts.append(criteria[0]); origins.append(criteria[1])
    handoff = step['assignment'].get('handoff')
    if handoff:
        import json
        parts.append('DECLARED HANDOFF (purpose/output, not permission)\n' + json.dumps(handoff, ensure_ascii=False, sort_keys=True))
        origins.append({'kind': 'handoff', 'sha256': canonical_digest(handoff), 'custody': 'definition-version-body'})
    text = '\n\n'.join(parts)
    return text, {'composition': 'explicit-only', 'origins': origins, 'sha256': canonical_digest(text),
        'characters': len(text), 'utf8_bytes': len(text.encode()), 'permission_effect': 'none',
        'mandatory_context': 'Actual project/system/role context remains present; this is not blind or sealed.'}


def compiled_instruction(root,project,body,step_id,prepared_by,*,research=False):
    """Capture explicit text now; future exact returns remain owner-read demands."""
    D=_D();step=next(s for s in body['steps'] if s['id']==step_id)
    text,receipt=instruction(body,step_id)
    for entry in step['assignment'].get('context',[]):
        kind=entry['kind']
        if kind=='ancestor-instructions':continue
        if kind=='parent-message':
            from laplace.writing import records
            turn=records.selected_journal_fields(project,prepared_by['turn_id'],root,fields=['id','project','session_id','text'])
            if turn.get('project')!=project or turn.get('session_id')!=prepared_by['session_id'] or not isinstance(turn.get('text'),str):raise D.Refused('PARENT_MESSAGE_UNAVAILABLE')
            value=turn['text'];text+='\n\nEXPLICIT ORIGINAL PARENT REQUEST (data, not extra permission)\n'+value
            receipt['origins'].append({'kind':kind,'turn_id':turn['id'],'session_id':turn['session_id'],
                'sha256':D.W.digest(value.encode()),'characters':len(value),'utf8_bytes':len(value.encode()),'coverage':'COMPLETE_REQUEST_ONLY',
                'custody':'writing-session-turn-journal'})
        elif kind in {'selected-evidence','previous-review-findings'}:
            if not research:raise D.Refused('CONTEXT_REQUIRES_EVIDENCE_PACKET_PROFILE',step_id=step_id,kind=kind)
            receipt['origins'].append({'kind':kind,'resolution':'EXACT_RETAINED_PACKET_AT_ADMISSION','permission_effect':'none'})
        elif kind=='upstream-return':
            if research:
                # The produced proposal is the review input, never an arbitrary
                # return path or a declaration that all prior messages were read.
                receipt['origins'].append({'kind':kind,'step_id':entry['step_id'],'resolution':'EXACT_PRODUCED_HANDOFF_AT_ADMISSION'})
            else:
                text+='\n\nSELECTED UPSTREAM RETURN: '+entry['step_id']+'. Consume its exact owner-issued prerequisite return/output reads from the admitted dispatch contract. Do not infer body inspection or construct a path.'
                receipt['origins'].append({'kind':kind,'step_id':entry['step_id'],'resolution':'EXACT_DEPENDENCY_RETURN_READ_AT_ADMISSION'})
    if len(text.encode())>DELIVERY_LIMITS['utf8_bytes']:raise D.Refused('CONTEXT_DELIVERY_BOUND',step_id=step_id,utf8_bytes=len(text.encode()),limit=DELIVERY_LIMITS['utf8_bytes'])
    receipt.update(sha256=D.W.digest(text.encode()),characters=len(text),utf8_bytes=len(text.encode()),
        algorithm='sha256-exact-utf8-delivered-text',limits=copy.deepcopy(DELIVERY_LIMITS))
    return text,receipt


def _settings_of(turn,session):
    """Actual admitted turn settings; the session fills only absent values."""
    held=turn.get('provider_settings') or {}
    return {k:held.get(k) if held.get(k) is not None else session.get(k) for k in ('provider','model','effort')}


def _turn_settings(root,project,turn_id,session_id):
    from laplace.writing import records
    fold=records.fold_records(root)
    return _settings_of(fold['turns'].get(turn_id) or {},fold['sessions'].get(session_id) or {})


def parent_synthesis(root,project,body,selected,prepared_by):
    D=_D();steps={s['id']:s for s in body['steps']};synthesis=[steps[s] for s in selected if steps[s]['assignment']['role']=='synthesis']
    if len(synthesis)>1:raise D.Refused('ONE_ORIGINAL_PARENT_SYNTHESIS')
    if not synthesis:return None
    step=synthesis[0];sid=step['id']
    if not step['assignment'].get('instructions','').strip():raise D.Refused('SYNTHESIS_INSTRUCTION_REQUIRED')
    from laplace.writing import records
    fold=records.fold_records(root);turn=fold['turns'].get(prepared_by['turn_id']) or {};session=fold['sessions'].get(prepared_by['session_id']) or {}
    if turn.get('project')!=project or turn.get('session_id')!=prepared_by['session_id']:raise D.Refused('ORIGINAL_PARENT_SESSION_REQUIRED')
    actual=_settings_of(turn,session)
    declarations=dict(body.get('settings',{}));chain=[];cursor=step
    while cursor is not None:chain.append(cursor);cursor=steps.get(cursor.get('parent_id'))
    for ancestor in reversed(chain):declarations.update(ancestor['assignment'].get('settings',{}))
    for field in ('provider','model','effort'):
        if field in declarations and declarations[field]!=actual.get(field):
            raise D.Refused('PARENT_SYNTHESIS_SETTINGS_CONFLICT','Change the initiating conversation setting or remove the incompatible synthesis override; the original parent does not become another executor.',field=field,required=declarations[field],actual=actual.get(field))
    if declarations.get('input_policy') not in (None,'evidence-packet'):raise D.Refused('PARENT_SYNTHESIS_INPUT_POLICY_UNSUPPORTED')
    text,delivery=compiled_instruction(root,project,body,sid,prepared_by,research=bool(body.get('run_policy')))
    return {'step_id':sid,'title':step.get('title') or sid,'instructions':text,'delivery':delivery,
        'handoff':copy.deepcopy(step['assignment'].get('handoff',{})),
        'execution_location':'original-parent','session_id':prepared_by['session_id'],'prepared_by_turn_id':prepared_by['turn_id'],
        'admitted_settings':actual,'declared_settings':{k:declarations[k] for k in ('provider','model','effort') if k in declarations},'bridge':BRIDGE,'model_constraint':'No override of an already admitted parent. Actual initiating-session settings govern.',
        'mandatory_inputs':'Every exact produced child return/proposal, independent judgement and unresolved finding; no selected subset replaces complete required evidence.'}


def _selected(root, caller, payload, *, body=True):
    from laplace.pipeline import workflow_definition_records as R
    D = _D(); R._admit(caller)
    if 'definition' in payload:
        scope = D._scope(payload.get('scope', {'kind': 'owned-workspace'} if caller.kind == 'owned-workspace' else {'kind': 'project', 'namespace': caller.namespace}))
        if not D._admits(caller, scope): raise D.Refused('NOT_IN_SCOPE')
        value = copy.deepcopy(payload['definition']); D.validate(value)
        return None, scope, value, None
    frame = R.select(root, caller, payload, detach=False)
    row, _ = R.raw(frame, frame['selected']); value = R.body(frame,row) if body else None
    if body:
        D.validate(value)
        if D.W.digest(D.W.canonical(D._revision_payload(row,value)))!=row['definition_revision']:raise D.Refused('INVALID_EXPORT_CHAIN')
    R.finish(frame)
    return row, row['scope'], value, D.reference(row['definition_id'], row['definition_revision'])


def _fit(value):
    from laplace.work import project_work_navigation as N
    if N.emitted(value) > N.line(): raise _D().Refused('WORKFLOW_OPERATION_DELIVERY_BOUND')
    return value


def research_pairs_per_run(synthesis=()):
    """How many writer/reviewer pairs one run carries: two child packets per pair within the
    dispatch plan contract's packet list and fan-out (the parent synthesis is no packet), and
    every selected step, the synthesis included, within the prepare request's step list."""
    from laplace.work import project_work as W
    from laplace.pipeline import workflow_definitions as D
    plan = W.dispatch_plan_contract()['properties']
    request = next(c for c in D.native_change_contract()['oneOf'] if c['properties'].get('action', {}).get('const') == 'prepare')
    return min(plan['packets']['maxItems'], plan['fan_out_max']['maximum'], request['properties']['step_ids']['maxItems'] - len(synthesis)) // 2


def research_pairs(body, executing, synthesis=()):
    """Disjoint writer/reviewer pairs of a research selection, and the issues that refuse it.

    A writer and a reviewer are a pair when the writer's control arrows reach only that
    reviewer and the reviewer's only come from that writer; a writer with no control arrow
    to a reviewer pairs with the one reviewer whose feedback arrows reach only it (that pair
    still needs its control arrow). Within a pair any number of control arrows forward and
    feedback arrows back are admitted, as for the one pair. A control arrow from a selected
    step into the selected original-parent synthesis is admitted. Any other arrow is refused:
    RESEARCH_EDGE_CROSSES_PAIRS when its two ends are in different pairs, nothing more when
    an end is an unpaired step of the right role (that step's own issue names it), and
    UNSUPPORTED_RESEARCH_TOPOLOGY, once, otherwise. No writer and no reviewer keeps the
    original code; another role is named by its step; unequal writer and reviewer counts
    say each writer needs its own reviewer; more pairs than one run carries are refused.
    """
    steps = {s['id']: s for s in body['steps']}; role = lambda sid: steps[sid]['assignment']['role']
    builders = [s for s in executing if role(s) == 'builder']; judges = [s for s in executing if role(s) == 'adversary']
    if not builders and not judges:
        return [], [{'code': 'RESEARCH_REQUIRES_ONE_WRITER_AND_REVIEWER'}]
    other = [{'code': 'UNSUPPORTED_ROLE', 'step_id': s} for s in executing if role(s) not in {'builder', 'adversary'}]
    if other: return [], other
    if len(builders) != len(judges): return [], [{'code': 'RESEARCH_REVIEWER_PER_WRITER'}]
    bound = research_pairs_per_run(synthesis)
    if len(builders) > bound:
        return [], [{'code': 'RESEARCH_PAIRS_PER_RUN', 'max_pairs': bound, 'pairs': len(builders), 'message': 'One run takes at most %d writer and reviewer pairs%s; this selection has %d.' % (
            bound, ' beside its synthesis' if synthesis else '', len(builders))}]
    edges = [e for e in body['edges'] if e['from'] in executing and e['to'] in executing]
    links = lambda kind, ends: {(e['from'], e['to']) for e in edges if e['kind'] == kind and (role(e['from']), role(e['to'])) == ends}
    forward = links('control', ('builder', 'adversary')); back = {(w, r) for r, w in links('feedback', ('adversary', 'builder'))}
    def unique(relation, writers, reviewers):
        out = lambda w: {r for x, r in relation if x == w and r in reviewers}; into = lambda r: {w for w, x in relation if x == r and w in writers}
        return [(w, r) for w in writers for r in out(w) if out(w) == {r} and into(r) == {w}]
    pairs = unique(forward, builders, judges)
    loose_writers = [w for w in builders if not any(x == w for x, _ in forward)]; loose_reviewers = [r for r in judges if not any(x == r for _, x in forward)]
    unlinked = unique(back, loose_writers, loose_reviewers); pairs += unlinked
    pairs.sort(key=lambda pair: builders.index(pair[0]))
    pair_of = {sid: index for index, pair in enumerate(pairs) for sid in pair}
    issues = [{'code': 'DRAFT_REVIEW_EDGE_REQUIRED', 'step_id': w} for w, _ in unlinked]
    issues += [{'code': 'DRAFT_REVIEW_EDGE_REQUIRED', 'step_id': w} for w in loose_writers if w not in pair_of]
    drafted = bool(issues)
    for sid in executing:
        if sid in pair_of or (role(sid) == 'builder' and sid in loose_writers): continue
        if role(sid) == 'adversary' and sid in loose_reviewers and drafted: continue  # the writer's missing arrow is the cure
        issues.append({'code': 'RESEARCH_STEP_UNPAIRED', 'step_id': sid})
    topology = False
    for edge in body['edges']:
        source, target, kind = edge['from'], edge['to'], edge['kind']
        if target in synthesis:
            if kind != 'control' or source not in executing: issues.append({'code': 'UNSUPPORTED_SYNTHESIS_INPUT', 'edge_id': edge['id'], 'step_id': target})
            continue
        if source not in executing and target not in executing: continue
        shaped = (source, target) in forward if kind == 'control' else (target, source) in back if kind == 'feedback' else False
        if shaped and source in pair_of and pair_of[source] == pair_of.get(target): continue
        if source in pair_of and target in pair_of and pair_of[source] != pair_of[target]:
            issues.append({'code': 'RESEARCH_EDGE_CROSSES_PAIRS', 'edge_id': edge['id'], 'step_id': target}); continue
        if shaped: continue  # an end is an unpaired step; its own issue names it
        topology = True
    if topology: issues.append({'code': 'UNSUPPORTED_RESEARCH_TOPOLOGY'})
    return ([(w, r) for w, r in pairs] if not issues else []), issues


def _preview(body, payload):
    D = _D(); selected = payload.get('step_ids', [s['id'] for s in body['steps']]); steps = {s['id']: s for s in body['steps']}
    issues = []
    if not set(selected) <= set(steps): raise D.Refused('STEP_NOT_IN_DEFINITION')
    synthesis = [sid for sid in selected if steps[sid]['assignment']['role'] == 'synthesis']
    executing = [sid for sid in selected if sid not in synthesis]
    if len(synthesis) > 1: issues.append({'code': 'ONE_ORIGINAL_PARENT_SYNTHESIS', 'step_ids': synthesis})
    profile = body.get('run_policy', {}).get('profile', D.APP_PROFILE)
    if body.get('run_policy'):
        issues.extend(research_pairs(body, executing, synthesis)[1])
        if loop_policy(body['run_policy']) is not None and not synthesis: issues.append({'code': 'EXTENDED_POLICY_REQUIRES_PARENT_SYNTHESIS'})
        requirements = ['Exact selected evidence', 'Editable manuscript target', 'Current original author session', 'Approved writer/reviewer bindings', 'Explicit Send/Start']
    else:
        if not 2 <= len(executing) <= 8: issues.append({'code': 'SELECT_TWO_TO_EIGHT_CHILD_ROLES'})
        prior = []; intended = {sid: [] for sid in executing}
        for edge in body['edges']:
            if edge['to'] not in executing: continue
            if edge['from'] not in executing or edge['kind'] != 'control': issues.append({'code': 'UNSUPPORTED_CLOSED_CONTROL_INPUT', 'edge_id': edge['id']})
            else: intended[edge['to']].append(edge['from'])
        remaining = list(executing); ordered = []
        while remaining:
            ready = next((sid for sid in remaining if set(intended[sid]) <= set(ordered)), None)
            if ready is None: issues.append({'code': 'UNSUPPORTED_CONTROL_CYCLE'}); break
            ordered.append(ready); remaining.remove(ready)
        for sid in ordered:
            role = steps[sid]['assignment']['role']
            if role not in {'builder', 'adversary'}: issues.append({'code': 'UNSUPPORTED_ROLE', 'step_id': sid})
            # A review reads its own declared builders (dispatch_dependencies honours them), so it may run beside other steps.
            elif (role == 'adversary' and not (intended[sid] and set(intended[sid]) <= set(prior))) or (role == 'builder' and intended[sid]): issues.append({'code': 'UNSUPPORTED_CARRIER_DEPENDENCIES', 'step_id': sid})
            if role == 'builder': prior.append(sid)
        requirements = ['Project-owned saved version', 'Current admitted original author', 'Exact supported child slice/fan-out', 'Separate explicit Start']
    roles = []
    for sid in selected:
        step = steps[sid]; text, delivery = instruction(body, sid)
        if not body.get('run_policy'):
            for entry in step['assignment'].get('context',[]):
                if entry['kind'] in {'selected-evidence','previous-review-findings'}:issues.append({'code':'CONTEXT_REQUIRES_EVIDENCE_PACKET_PROFILE','step_id':sid,'kind':entry['kind']})
        if not step['assignment'].get('instructions', '').strip(): issues.append({'code': 'INSTRUCTION_REQUIRED', 'step_id': sid})
        if any(step.get(k) for k in ('targets', 'inputs', 'outputs')): issues.append({'code': 'UNCONSUMED_STEP_DECLARATION', 'step_id': sid})
        roles.append({'step_id': sid, 'title': step.get('title') or sid, 'role': step['assignment']['role'],
            'execution_location': 'original-parent' if sid in synthesis else 'admitted-child',
            'context': copy.deepcopy(step['assignment'].get('context', [])), 'handoff': copy.deepcopy(step['assignment'].get('handoff', {})),
            'delivery': delivery, 'instruction_read': {'step_id': sid, 'characters': len(text)}, 'parent_id': step.get('parent_id')})
    return {'profile': profile, 'support': 'SUPPORTED_CONFIGURATION' if not issues else 'REFUSED_CONFIGURATION', 'issues': issues,
        'roles': roles, 'required_admission': requirements, 'execution_permitted': False, 'loop': loop_summary(body.get('run_policy')),
        'meaning': 'Pure capability preview. Saving does not mean runnable; actual Prepare revalidates all input/settings/authority/resource guards.',
        'nesting': 'Organisation and explicit settings/context inheritance only; no spawned subworkflow or multiplied allowance.',
        'mandatory_context': 'Project/system/role context remains mandatory; delivered data never grants read/tool/source permission.'}


def read(root, caller, payload):
    from jsonschema import Draft202012Validator
    from laplace.work import project_work as W
    D = _D()
    if next(Draft202012Validator(read_contract()).iter_errors(payload), None): raise D.Refused('INVALID_OPERATION_READ')
    facet = payload['facet']
    if facet=='withdrawal-preview':
        from laplace.pipeline import workflow_definition_records as R
        R._admit(caller);original=copy.deepcopy(payload['original_request']);operation=payload['operation']
        scope=_original_scope(root,caller,original,operation)
        digest=canonical_digest(original)
        return _fit({'schema_version':SCHEMA,'view':facet,'scope':copy.deepcopy(scope),'scope_id':D._scope_id(root,caller),
            'request_token':payload.get('request_token'),'request_id':original['request_id'],'operation':operation,'intent_digest':digest,
            'withdraw':_withdrawal_handle(operation,caller,original,digest),'read_only':True,'effect':'none',
            'meaning':'Pure exact-original request preparation. No admission or withdrawal. Use the same retained original_request with this owner-issued digest.'})
    if facet=='creation-choices':
        from laplace.pipeline import registry,workflow_definition_records as R
        R._admit(caller)
        if set(payload)-{'facet','offset','limit','as_of'}:raise D.Refused('INVALID_CREATION_CHOICE')
        choices=[]
        if caller.kind=='owned-workspace':
            choices.append({'scope':{'kind':'owned-workspace'},'title':'Reusable workspace design',
                'create':D._action('save',{'expected_revision':None,'scope':{'kind':'owned-workspace'}},caller),
                'library_read':D.scoped_handle(caller)})
        projects=registry.all_projects(repo_root=root)
        for name in sorted(projects):
            if not caller.admits(name):continue
            scope={'kind':'project','namespace':name}
            item=projects[name]
            title=(item.manifest or {}).get('display_name') or name
            choices.append({'scope':scope,'name':name,'title':title,'create':D._action('save',{'expected_revision':None,'scope':scope},caller),
                'library_read':D.handle(project_lens=name),
                'meaning':'Project-owned definition. Saving starts nothing; current author admission is separately required for execution.'})
        cut=canonical_digest({'scope_id':D._scope_id(root,caller),'choices':[x['scope'] for x in choices]})
        if payload.get('as_of',cut)!=cut:raise D.Refused('CREATION_CHOICES_CHANGED')
        offset=payload.get('offset',0);limit=payload.get('limit',20);page=choices[offset:offset+limit]
        envelope=lambda page:{'schema_version':SCHEMA,'view':facet,'scope_id':D._scope_id(root,caller),'caller_scope':caller.public(),
            'items':page,'total':len(choices),'offset':offset,'cut':cut,'read_only':True,
            'request_token':payload.get('request_token'),
            'next_read':D.scoped_handle(caller,facet=facet,offset=offset+len(page),limit=limit,as_of=cut) if offset+len(page)<len(choices) else None}
        from laplace.work import project_work_navigation as N
        while page and N.emitted(envelope(page))>N.line():page=page[:-1]
        if not page and offset<len(choices):raise D.Refused('WORKFLOW_OPERATION_DELIVERY_BOUND')
        return _fit(envelope(page))
    row, scope, body, reference = _selected(root, caller, payload, body=facet in {'execution-preview', 'context'})
    base = {'schema_version': SCHEMA, 'view': facet, 'scope': copy.deepcopy(scope), 'caller_scope': caller.public(),
        'scope_id': D._scope_id(root, caller), 'reference': reference, 'read_only': True,'request_token':payload.get('request_token')}
    if facet in {'execution-preview', 'context'}:
        preview = _preview(body, payload); basis = canonical_digest({'body': body, 'scope': scope, 'step_ids': payload.get('step_ids')})
        if facet == 'execution-preview':
            if payload.get('as_of',basis)!=basis:raise D.Refused('PREVIEW_CHANGED')
            for role in preview['roles']:
                role['context_read']=operation_handle(caller,{'facet':'context',**{k:copy.deepcopy(v) for k,v in payload.items() if k in {'definition','scope','reference','definition_id','version','step_ids'}},'step_id':role['step_id'],'as_of':basis})
            offset=payload.get('offset',0);limit=payload.get('limit',20);roles=preview.pop('roles');issues=preview.pop('issues');size=limit
            def envelope(size):
                end=min(offset+size,max(len(roles),len(issues)))
                next_read=operation_handle(caller,{**{k:copy.deepcopy(v) for k,v in payload.items() if k not in {'offset','as_of'}},'offset':end,'as_of':basis}) if end<max(len(roles),len(issues)) else None
                return {**base, **preview, 'basis': basis,'roles':roles[offset:offset+size],'issues':issues[offset:offset+size],
            'role_coverage':{'known':len(roles),'offset':offset,'returned':len(roles[offset:offset+size])},
            'issue_coverage':{'known':len(issues),'offset':offset,'returned':len(issues[offset:offset+size])},'next_read':next_read,
            'definition_digest':canonical_digest(body),'selected_step_ids':payload.get('step_ids',[s['id'] for s in body['steps']]),
            'declarations':{'context':context_contract(),'handoff':handoff_contract(),'run_policy':D.run_policy_contract()},
            'context_read':{'read':operation_handle(caller,{'facet':'context',**{k:copy.deepcopy(v) for k,v in payload.items() if k in {'definition','scope','reference','definition_id','version','step_ids'}}}),'required_inputs':['step_id']}}
            from laplace.work import project_work_navigation as N
            while size>1 and N.emitted(envelope(size))>N.line():size=max(1,size//2)
            return _fit(envelope(size))
        sid = payload.get('step_id')
        if sid not in {s['id'] for s in body['steps']}: raise D.Refused('STEP_NOT_IN_DEFINITION')
        text, receipt = instruction(body, sid); offset = payload.get('offset', 0); limit = payload.get('limit', 20) * 200
        if payload.get('as_of', basis) != basis: raise D.Refused('CONTEXT_CHANGED')
        end = min(len(text), offset + limit)
        more = operation_handle(caller,{'facet':'context',**{k: copy.deepcopy(v) for k, v in payload.items() if k not in {'facet', 'offset', 'as_of'}},'offset':end,'as_of':basis}) if end < len(text) else None
        return _fit({**base, 'basis': basis, 'step_id': sid, 'content': text[offset:end], 'offset': offset,
            'returned': end - offset, 'total_characters': len(text), 'at_end': end == len(text), 'next_read': more,
            'delivery': receipt, 'qualification': 'Declared instruction composition only. Actual evidence/proposal/parent message is resolved at admission, never inferred by this read.'})
    if scope['kind'] != 'project': return _fit({**base, 'items': [], 'total': 0, 'coverage': 'NO_PROJECT_EXECUTION_BINDING', 'next_read': None})
    project = scope['namespace']; tasks = W._tasks(project, root); ident = row['definition_id']; version = row['definition_revision']
    matches = [t for t in tasks.values() if (t.get('prepared_workflow', {}).get('reference', {}).get('identity') or {}).get('id') == ident
        and (payload.get('versions') == 'all' or t['prepared_workflow']['reference'].get('version', {}).get('definition_revision') == version)]
    cut = canonical_digest({'reference': reference, 'versions': payload.get('versions', 'selected'),
        'works': [(t['id'], W._task_revision(t), t.get('status'), t.get('dispatch_admitted')) for t in matches]})
    if facet == 'uses':
        from laplace.work.project_work_views import handle as work_read
        rows = [{'work_id': t['id'], 'title': t['title'], 'recorded_status': t['status'],
            'admission': 'ADMITTED' if t.get('dispatch_admitted') or any(p.get('kind') == 'workflow-run' and (p.get('run') or {}).get('launched_by') for p in t.get('phases', [])) else 'PREPARED',
            'reference': copy.deepcopy(t['prepared_workflow']['reference']), 'work_read': work_read(project, {'view': 'detail', 'id': t['id']}),
            'river_read': D.scoped_handle(caller, facet='river', reference=t['prepared_workflow']['reference'], work_id=t['id']),
            **_recorded_run(t)} for t in matches]
    else:
        from laplace.writing import workflow_dispatch
        task = next((t for t in matches if t['id'] == payload['work_id']), None)
        if task is None: raise D.Refused('APP_RUN_NOT_IN_SCOPE')
        observed = workflow_dispatch.run(root, caller, row, task); rows = []
        runs = [p.get('run') for p in task.get('phases', []) if p.get('kind') == 'workflow-run' and isinstance(p.get('run'), dict)]
        from laplace.writing import records as turn_records
        turns = turn_records.fold_records(root)['turns']
        for step in observed.get('steps', observed.get('attempts', [])):
            rows.append(_river_row(step, turns))
        base.update(work_id=task['id'], run_read=observed.get('read'), observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            observation=copy.deepcopy(observed.get('observation', {'state': observed.get('state'), 'qualification': 'Recorded WD projection; inspect actual child host through its conversation.'})),
            prepared_dependencies=copy.deepcopy(observed.get('prepared_dependencies')), actions=_action_summary(observed.get('actions', {})),
            row_projection={'kind':'COMPACT_IDENTITY_AND_HANDLES','detail_read':copy.deepcopy(observed.get('read')),
                'meaning':'Rows keep identity, recorded state, compact settings and issued read handles. Full settings, conversation and exact action payloads are in the issued run detail read; nothing was hydrated.'},
            deadline=copy.deepcopy(observed.get('deadline')), parent=copy.deepcopy(observed.get('parent')), stop=stop_offer(observed.get('actions', {}), rows),
            loop=river_loop(runs[-1] if runs else {}, {'research_workflow':{'input_packet':observed['input_packet']}} if observed.get('input_packet') else None),
            run_identity={'work_id':task['id'],'definition_id':ident,'version':version,'plan_reference':copy.deepcopy(observed.get('reference')),
                'plan_generation':observed.get('plan_generation'),'run_revision':observed.get('revision'),'recorded_state':observed.get('state')},
            synthesis={k:copy.deepcopy(observed['synthesis'].get(k)) for k in ('required','bridge','bridge_problem','due','pending_children','inputs_total','published')} if isinstance(observed.get('synthesis'),dict) else None,
            current_observation={'items':{r['event_id']:_liveness(root,r) for r in rows if r.get('event_id')},
                'by_turn':{r['turn_id']:_liveness(root,r) for r in rows if r.get('turn_id')},
                'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                'meaning':'Current child host observation, outside the recorded cut. Recorded row state and current liveness are different facts; NO_ADMITTED_TURN is not proof that nothing ran.'})
        cut = canonical_digest({'query': cut, 'work_id': task['id'], 'rows': rows})
    if payload.get('as_of', cut) != cut: raise D.Refused('WORKFLOW_USES_CHANGED', restart_read=D.scoped_handle(caller, facet=facet, reference=reference, **({'work_id':payload['work_id']} if facet=='river' else {})))
    offset = payload.get('offset', 0); limit = payload.get('limit', 20)
    page = rows[offset:offset + limit]
    handle = lambda at: D.scoped_handle(caller, facet=facet, reference=reference, **{k: v for k, v in payload.items() if k in {'work_id', 'versions'}}, offset=at, limit=limit, as_of=cut)
    from laplace.work import project_work_navigation as N
    envelope=lambda page:{**base, 'items':page, 'total':len(rows), 'offset':offset,'returned':len(page),'cut':cut,
        'next_read':handle(offset+len(page)) if offset+len(page)<len(rows) else None,
        'coverage':'RECORDED_MATCHES_ONLY','body_inspection':'NOT_REQUESTED',
        'meaning':'Prepared, admitted, observed-live and returned are separate. No message/tool body fanout or inferred usage/price; follow exact issued reads.'}
    while page and N.emitted(envelope(page))>N.line():page=page[:-1]
    if not page and offset < len(rows): raise D.Refused('WORKFLOW_OPERATION_DELIVERY_BOUND')
    return _fit(envelope(page))


_ROW_IDENTITY=('step_id','title','role','assignment_role','state','effect','event_id','session_id','turn_id','iteration','recipient_ack',
    'known_refusal','refusal_stage','current_attempt','packet','replied','reply_status')
_TURN_CALL_LIMIT=12


def _turn_facts(turn):
    """Times and tool-call identities of one exact recorded turn (operation, status, time; never a body)."""
    if not isinstance(turn,dict):return None
    reply=turn.get('reply') if isinstance(turn.get('reply'),dict) else {}
    calls,seen=[],set()
    for kind,rows in (('read',list((turn.get('tool_reads') or {}).values())),('action',turn.get('tool_actions') or []),
                      ('failure',turn.get('tool_failures') or [])):
        for item in rows:
            if not isinstance(item,dict) or item.get('id') in seen:continue
            seen.add(item.get('id'))
            outcome=item.get('outcome') if isinstance(item.get('outcome'),dict) else {}
            calls.append({'kind':kind,'id':item.get('id'),'operation':item.get('operation'),
                'status':outcome.get('status') or item.get('code'),'at':item.get('ts')})
    calls.sort(key=lambda call:str(call.get('at') or ''))
    settings=turn.get('provider_settings')
    return {'started_at':turn.get('ts'),'replied_at':reply.get('ts'),'reply_status':reply.get('status'),
        'reply_error':str(reply['error'])[:300] if reply.get('error') else None,
        'provider_settings':{k:settings.get(k) for k in ('provider','model','effort')} if isinstance(settings,dict) else None,
        'tool_calls':calls[:_TURN_CALL_LIMIT],'tool_calls_total':len(calls),
        'source':'writing records: the turn and its writing-tool-read, writing-tool-action and writing-tool-failure rows'}


def _river_row(step, turns=None):
    """Compact recorded identity plus issued reads; bodies and full payloads stay behind their reads."""
    row={k:copy.deepcopy(step[k]) for k in _ROW_IDENTITY if k in step}
    if step.get('turn_id') and isinstance(turns,dict):
        facts=_turn_facts(turns.get(step['turn_id']))
        if facts:row['turn']=facts
    if step.get('error'):row['error']=str(step['error'])[:300]
    result=step.get('result')
    if isinstance(result,dict):row['result']={k:copy.deepcopy(result[k]) for k in ('status','available') if k in result}
    settings=step.get('settings')
    if isinstance(settings,dict):
        pick=lambda v:{k:v.get(k) for k in ('provider','model','effort')} if isinstance(v,dict) else None
        prepared=settings.get('prepared')
        prepared=prepared.get('values',prepared) if isinstance(prepared,dict) else prepared
        row['settings']={'prepared':pick(prepared),'admitted':pick(settings.get('admitted')),'sent':pick(settings.get('sent'))}
    reads={}
    for key,name in (('public_reply_read','reply'),('proposal_read','proposal'),('typed_return_read','typed_return'),('research_run_read','research_run')):
        value=step.get(key)
        if isinstance(value,dict):reads[name]={k:copy.deepcopy(value[k]) for k in ('identity','native','http') if k in value}
    conversation=step.get('conversation')
    if isinstance(conversation,dict):reads['conversation']={k:copy.deepcopy(conversation.get(k)) for k in ('project','session_id','turn_id','project_url','session_read') if k in conversation}
    if reads:row['reads']=reads
    return row


def _action_summary(actions):
    items=actions.items() if isinstance(actions,dict) else enumerate(actions or [])
    return [{'name':str(name),'title':a.get('title'),'permitted':a.get('permitted'),'reason':str(a.get('reason') or '')[:200]}
        for name,a in items if isinstance(a,dict)][:DELIVERY_LIMITS['entries']]


def _liveness(root,row):
    """Current host observation for one recorded child; never inferred from records."""
    sid,tid=row.get('session_id'),row.get('turn_id')
    if not sid or not tid:return {'observed':'NO_ADMITTED_TURN'}
    try:
        from laplace.writing import child_hosts
        execution=child_hosts.child_execution(Path(root),sid) or {}
    except (OSError,ValueError,KeyError,TypeError) as error:return {'observed':'UNKNOWN','reason':str(error)[:200]}
    if execution.get('turn_id')!=tid:return {'observed':'NOT_THE_CURRENT_EXECUTION','session_execution_turn_id':execution.get('turn_id')}
    return {'observed':execution.get('state') or 'UNKNOWN'}


def _recorded_run(task):
    runs=[p.get('run') for p in task.get('phases') or [] if p.get('kind')=='workflow-run' and isinstance(p.get('run'),dict)]
    if not runs:return {'recorded_run':None}
    run=runs[-1]
    return {'recorded_run':{'state':run.get('state'),'iteration':run.get('iteration'),'attempts':len(run.get('attempts') or []),
        'plan_generation':run.get('plan_generation'),'synthesis':(run.get('synthesis') or {}).get('status'),
        'qualification':'Recorded Work phase only; read the river for current child observation.'}}


def validate_decision(row):
    import re
    required={'record','request_id','operation','scope','intent_digest','decision','ts'}
    if not required<=set(row) or set(row)-required-{'ts_claimed'} or row['record']!=DECISION or row['operation'] not in {'save','prepare'} or row['decision']!='WITHDRAWN':raise ValueError('Invalid workflow request decision.')
    if not isinstance(row['request_id'],str) or not 1<=len(row['request_id'])<=120 or not re.fullmatch('sha256:[a-f0-9]{64}',str(row['intent_digest'])):raise ValueError('Invalid request identity.')
    _D()._scope(row['scope'])
    if not isinstance(row['ts'],str):raise ValueError('Invalid request timestamp.')
    if 'ts_claimed' in row and not isinstance(row['ts_claimed'],str):raise ValueError('Invalid claimed timestamp.')


def _decisions(root,rid):
    from laplace.pipeline import workflow_definition_records as R
    if not R._path(root).exists():return []
    with R._LOCK:
        index=R._index(root)
        result=[]
        for meta in index.request_decisions.get(rid,()):
            import json
            from laplace.core.records import capture
            _,raw=capture.read_captured_row(index.path,meta['offset'],meta['end'],meta['hash'])
            row=json.loads(raw,object_pairs_hook=_D().W._unique)
            validate_decision(row)
            if row!=meta['row']:raise _D().Refused('SELECTED_REQUEST_DECISION_CHANGED')
            result.append(copy.deepcopy(row))
        return result


def _recorded_effect(root,caller,rid):
    """Any recorded save or preparation under this request ID in admitted custody."""
    D=_D()
    if any(r.get('request_id')==rid and D._admits(caller,r['scope']) for r in D._rows(root)):return True
    from laplace.writing import workflow_dispatch
    if workflow_dispatch.inspect_request(root,caller,rid) is not None:return True
    rows,_=D._preparation_requests(root)
    return any(r.get('preparation_request_id')==rid for r in rows)


def decision(root,caller,rid):
    from laplace.pipeline import workflow_definition_records as R
    R._admit(caller);matches=[r for r in _decisions(root,rid) if _D()._admits(caller,r['scope'])]
    if len(matches)>1:raise _D().Refused('REQUEST_CUSTODY_AMBIGUOUS',effect='unknown')
    if matches and _recorded_effect(root,caller,rid):
        raise _D().Refused('REQUEST_CUSTODY_CONTRADICTORY','A withdrawal decision and a recorded effect both exist; nothing is selected by precedence.',effect='unknown')
    return matches[0] if matches else None


def decision_result(root,caller,row):
    return {'schema_version':'laplace.workflow-request-decision/1','status':'NOT_ADMITTED','effect':'NOT_ADMITTED',
        'terminal':True,'request_id':row['request_id'],'operation':row['operation'],'intent_digest':row['intent_digest'],
        'scope':copy.deepcopy(row['scope']),'scope_id':_D()._scope_id(root,caller),'reason':'WITHDRAWN',
        'read':_D().scoped_handle(caller,facet='request',request_id=row['request_id']),
        'meaning':'The exact request was withdrawn before admission. No recorded effect was undone.'}


def admission_decision(root,caller,payload,operation):
    rows=_decisions(root,payload['request_id'])
    if not rows:return None
    if len(rows)!=1:raise _D().Refused('REQUEST_CUSTODY_AMBIGUOUS',effect='unknown')
    row=rows[0]
    if not _D()._admits(caller,row['scope']):raise _D().Refused('NOT_IN_SCOPE')
    if row['operation']!=operation or row['intent_digest']!=canonical_digest(payload):raise _D().Refused('REQUEST_CONFLICT')
    if _recorded_effect(root,caller,payload['request_id']):
        raise _D().Refused('REQUEST_CUSTODY_CONTRADICTORY','A withdrawal decision and a recorded effect both exist; nothing is selected by precedence.',effect='unknown')
    return decision_result(root,caller,row)


def _original_scope(root,caller,original,operation):
    from jsonschema import Draft202012Validator
    from laplace.pipeline import workflow_definition_records as R
    D=_D();R._admit(caller)
    if 'action' in original or 'project' in original:raise D.Refused('INVALID_ORIGINAL_REQUEST','Retain the original definition-owner payload, without adapter action/project fields.')
    D._request(original,set(original))
    if operation=='save':
        issue=next(Draft202012Validator(D.native_save_contract()).iter_errors({'action':'save',**original}),None)
        if issue:raise D.Refused('INVALID_ORIGINAL_REQUEST')
        D.validate(original['definition'])
    elif original.get('profile')==D.APP_PROFILE:
        issue=next(Draft202012Validator(D.native_change_contract()).iter_errors({'action':'prepare',**original}),None)
        if issue:raise D.Refused('INVALID_ORIGINAL_REQUEST')
    else:
        D._request(original,{'request_id','reference','selected_steps','profile','node','goal','write_paths','timeout'})
        if original.get('profile')!=D.W.SPEC_SCHEMA:raise D.Refused('UNSUPPORTED_PROFILE')
    # Exact original target admission precedes request metadata lookup.
    if operation=='prepare' or original.get('definition_id'):
        selector={'reference':original['reference']} if operation=='prepare' else {'definition_id':original['definition_id']}
        frame=R.select(root,caller,selector,detach=False);scope=frame['selected']['row']['scope'];R.finish(frame)
        if operation=='save' and 'scope' in original and original['scope']!=scope:raise D.Refused('SCOPE_CHANGE_NOT_ADMITTED')
    else:
        scope=D._scope(original.get('scope',{'kind':'owned-workspace'} if caller.kind=='owned-workspace' else {'kind':'project','namespace':caller.namespace}))
        if not D._admits(caller,scope):raise D.Refused('NOT_IN_SCOPE')
    return scope


def withdraw(root,caller,payload):
    from jsonschema import Draft202012Validator
    from laplace.pipeline import workflow_definition_records as R
    from laplace.work import project_work as W
    D=_D();R._admit(caller)
    if next(Draft202012Validator(withdraw_contract()).iter_errors(payload),None):raise D.Refused('INVALID_WITHDRAWAL')
    D._admit_save(root,caller);original=copy.deepcopy(payload['original_request']);operation=payload['operation']
    if original.get('request_id')!=payload['request_id'] or canonical_digest(original)!=payload['intent_digest']:raise D.Refused('WITHDRAWAL_INTENT_MISMATCH')
    scope=_original_scope(root,caller,original,operation)
    with W.dispatch_lock(root),D._lock(root):
        D._admit_save(root,caller)
        prior=admission_decision(root,caller,original,operation)
        if prior is not None:return {**prior,'replayed':True}
        observed=D._recover_request(root,caller,{'facet':'request','request_id':payload['request_id']},D._rows(root))
        if observed.get('status')=='RECORDED':
            receipt=observed.get('receipt') or {}
            recorded=receipt.get('intent_digest') or (observed.get('run') or {}).get('intent_digest')
            if operation=='save':
                saved=next((r for r in D._rows(root) if r.get('request_id')==payload['request_id'] and D._admits(caller,r['scope'])),None)
                recorded=saved.get('intent_digest') if saved else recorded
            if recorded and recorded!=payload['intent_digest']:raise D.Refused('REQUEST_CONFLICT')
            return {**observed,'withdrawal':'ALREADY_RECORDED_NO_UNDO','intent_digest':payload['intent_digest'],'withdrawal_operation':operation}
        if observed.get('status')!='NOT_RECORDED':return {'schema_version':'laplace.workflow-request-decision/1','status':'UNKNOWN','effect':'UNKNOWN','terminal':False,'request_id':payload['request_id'],'read':D.scoped_handle(caller,facet='request',request_id=payload['request_id']), 'reason':'Original custody is partial, unavailable or ambiguous; nothing was withdrawn.'}
        _,coverage=D._candidates(root)
        if coverage.get('status')!='COMPLETE' or coverage.get('unavailable'):
            return {'status':'UNKNOWN','effect':'UNKNOWN','terminal':False,'request_id':payload['request_id'],'reason':'Original preparation candidate custody is incomplete; nothing was withdrawn.'}
        row={'record':DECISION,'operation':operation,'scope':scope,'request_id':payload['request_id'],
            'intent_digest':payload['intent_digest'],'decision':'WITHDRAWN','ts':dt.datetime.now(dt.timezone.utc).isoformat()}
        try:D.W._bank(D._root(root),row)
        except Exception:
            return {'status':'UNKNOWN','effect':'UNKNOWN','terminal':False,'request_id':payload['request_id'],'reason':'Decision publication is uncertain; retain the original wire and inspect.'}
        return decision_result(root,caller,row)


def loop_policy(policy):
    """Finite authored v2 limits; None keeps the unchanged legacy v1 path."""
    D=_D()
    if not isinstance(policy,dict) or policy.get('profile')!=D.RESEARCH_POLICY_V2:return None
    return {k:policy[k] for k in ('max_iterations','max_admissions','deadline_seconds','runtime_seconds','continuation_criteria','exit_criteria')}


def bridge_problem(pin,plan):
    """Actual per-run fence: an extended run executes only with the complete synthesis bridge."""
    policy=((pin or {}).get('research_workflow') or {}).get('policy')
    if loop_policy(policy) is None:return None
    synthesis=(pin or {}).get('synthesis')
    if not isinstance(synthesis,dict) or synthesis.get('bridge')!=BRIDGE:
        return 'The prepared plan has no authored original-parent synthesis bridge; prepare it again from the saved version.'
    if not isinstance(synthesis.get('declared_settings'),dict) or synthesis.get('execution_location')!='original-parent':
        return 'The prepared synthesis settings custody is incomplete.'
    if plan is not None and not isinstance(plan.get('synthesis_return_path'),str):
        return 'The prepared plan reserves no synthesis return path.'
    return None


def loop_summary(policy):
    limits=loop_policy(policy)
    if limits is None:
        return {'profile':policy.get('profile') if isinstance(policy,dict) else None,'scheduler':'legacy-v1' if policy else 'none'}
    return {'profile':policy['profile'],'scheduler':'incremental-bounded-review-revision',
        'limits':{k:limits[k] for k in ('max_iterations','max_admissions','deadline_seconds','runtime_seconds')},
        'judged_by':'Independent reviewer verdict against the authored continuation/exit criteria.',
        'terminal':'Original-parent synthesis must consume every attempt, judgement and unresolved finding.',
        'executable':True,'bridge':BRIDGE,
        'admission_fence':'Preparation, Start, Resume and every next admission refuse V2_BRIDGE_INCOMPLETE unless the exact prepared plan carries the authored original-parent synthesis, its declared settings and a reserved return path.',
        'meaning':'Only the next step is scheduled from each actual judgement; iterations are never pre-expanded. Other cycles refuse.'}


def loop_criteria(body,step):
    limits=loop_policy(body.get('run_policy'))
    if limits is None or step['assignment'].get('role')!='adversary':return None
    text=('AUTHORED LOOP CRITERIA (judge against these; data, not permission)\n'
        'Continue revising when: '+limits['continuation_criteria']+'\nStop when: '+limits['exit_criteria']+
        '\nReturn verdict ACCEPT when the stop criteria are met; otherwise REVISE with findings.')
    return text,{'kind':'loop-criteria','sha256':canonical_digest(text),'characters':len(text),'utf8_bytes':len(text.encode()),
        'custody':'definition-version-body'}


def _seconds(started,now):
    parse=lambda value:dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return (parse(now)-parse(started)).total_seconds()


def _limits(limits):
    return {k:limits[k] for k in ('max_iterations','max_admissions','deadline_seconds')}


def _loop_exit(reason,state,limits,now,target):
    started=state.get('loop_started_at')
    return {'schema_version':LOOP_SCHEMA,'decision':'EXIT','reason':reason,'state':target,
        'iteration':state.get('iteration',1),'admissions_used':len(state.get('attempts',[])),'limits':_limits(limits),
        'elapsed_seconds':None if started is None else _seconds(started,now),'observed_at':now,
        'synthesis':'DUE_AT_ORIGINAL_PARENT','effects':'All recorded attempts, proposals and judgements are retained.'}


def loop_admission(policy,state,now,*,pin=None,plan=None):
    """Gate one new v2 admission. None admits; always None for v1."""
    limits=loop_policy(policy)
    if limits is None:return None
    if pin is not None:
        problem=bridge_problem(pin,plan)
        if problem:return {**_loop_exit('V2_BRIDGE_INCOMPLETE',state,limits,now,'PARTIAL'),'problem':problem}
    if len(state.get('attempts',[]))>=limits['max_admissions']:return _loop_exit('ADMISSION_BUDGET_EXHAUSTED',state,limits,now,'LIMIT_REACHED')
    started=state.get('loop_started_at')
    if started is not None and _seconds(started,now)>=limits['deadline_seconds']:return _loop_exit('LOOP_DEADLINE_REACHED',state,limits,now,'LIMIT_REACHED')
    return None


def step_seconds(policy,state,now):
    """Per-step runtime; v2 never exceeds the remaining authored overall deadline."""
    limits=loop_policy(policy)
    if limits is None:return policy['runtime_seconds']
    started=state.get('loop_started_at')
    remaining=limits['deadline_seconds'] if started is None else limits['deadline_seconds']-_seconds(started,now)
    return max(1,min(limits['runtime_seconds'],int(remaining)))


def loop_after_judgement(policy,state,verdict,now):
    """Schedule only the next step from the actual typed judgement."""
    limits=loop_policy(policy)
    if limits is None:return None
    if verdict not in {'ACCEPT','REVISE','REJECT'}:raise _D().Refused('UNKNOWN_REVIEW_VERDICT')
    if verdict=='ACCEPT':return _loop_exit('EXIT_CRITERIA_MET',state,limits,now,'AWAITING_HUMAN_APPLY')
    if state.get('iteration',1)>=limits['max_iterations']:return _loop_exit('ITERATION_BUDGET_REACHED',state,limits,now,'LIMIT_REACHED')
    if len(state.get('attempts',[]))+2>limits['max_admissions']:return _loop_exit('ADMISSIONS_INSUFFICIENT_FOR_NEXT_ITERATION',state,limits,now,'LIMIT_REACHED')
    started=state.get('loop_started_at')
    if started is not None and _seconds(started,now)>=limits['deadline_seconds']:return _loop_exit('LOOP_DEADLINE_REACHED',state,limits,now,'LIMIT_REACHED')
    return {'schema_version':LOOP_SCHEMA,'decision':'CONTINUE','reason':'CONTINUATION_BY_REVIEW','verdict':verdict,
        'iteration':state.get('iteration',1)+1,'next':'writer','admissions_used':len(state.get('attempts',[])),
        'limits':_limits(limits),'observed_at':now,
        'scheduled':'Next writer admission only; later steps are decided from later actual results.'}


def _sha(value):
    return str(value).removeprefix('sha256:') if value else None


def synthesis_requirements(state,pin):
    """Every exact input the original-parent synthesis must consume; never a subset."""
    required=[];packet=((pin or {}).get('research_workflow') or {}).get('input_packet') or {}
    if packet.get('id'):required.append({'kind':'input-packet','id':packet['id'],'sha256':packet.get('sha256')})
    for attempt in state.get('attempts',[]):required.append({'kind':'attempt-result','id':attempt['event_id'],'sha256':None})
    seen=set()
    for entry in _entries(state):
        proposal=entry.get('proposal') or {}
        if proposal.get('id') and ('proposal',proposal['id']) not in seen:
            seen.add(('proposal',proposal['id']));required.append({'kind':'proposal','id':proposal['id'],'sha256':proposal.get('sha256')})
        judgement=entry.get('judgement') or {}
        if judgement.get('turn_id') and ('judgement',judgement['turn_id']) not in seen:
            seen.add(('judgement',judgement['turn_id']))
            required.append({'kind':'judgement','id':judgement['turn_id'],
                'sha256':canonical_digest({'verdict':judgement.get('verdict'),'findings':judgement.get('findings',[])}),
                'verdict':judgement.get('verdict'),'unresolved_findings':len(judgement.get('findings') or [])})
    return required


def synthesis_coverage(required,consumed):
    """Refuse authored synthesis unless every exact required input carries a read receipt."""
    D=_D();held={}
    for row in consumed:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not row.get('read_receipt'):raise D.Refused('SYNTHESIS_CONSUMPTION_RECEIPT_REQUIRED')
        held.setdefault((row.get('kind'),row['id']),[]).append(row)
    missing=[];changed=[]
    for item in required:
        rows=held.get((item['kind'],item['id']),[])
        if not rows:missing.append({'kind':item['kind'],'id':item['id']})
        elif item.get('sha256') and not any(_sha(r.get('sha256'))==_sha(item['sha256']) for r in rows):
            changed.append({'kind':item['kind'],'id':item['id'],'expected':item['sha256']})
    if missing or changed:
        raise D.Refused('SYNTHESIS_INPUT_COVERAGE_INCOMPLETE','Synthesis must consume every exact required child return, judgement and evidence pin.',missing=missing,changed=changed)
    return {'status':'COMPLETE','required':len(required),'consumed':len(consumed),
        'meaning':'Every exact required input carries a read receipt. Coverage is not acceptance of any claim.'}


def _art(value):
    return {'id':value['id'],'sha256':'sha256:'+_sha(value.get('sha256') or value.get('revision'))}


def _entries(state):
    """Every recorded proposal/judgement entry; a two-pair run adds each pair's own history."""
    entries=[*(state.get('plan_history') or []),*(state.get('loop_history') or []),
        {'proposal':state.get('proposal'),'judgement':state.get('judgement')}]
    for lanes in [*(entry.get('pairs') or {} for entry in state.get('plan_history') or []),state.get('pairs') or {}]:
        for lane in lanes.values():
            entries+=[*(lane.get('loop_history') or []),{'proposal':lane.get('proposal'),'judgement':lane.get('judgement')}]
    return entries


def synthesis_inputs(state,pin,artifact):
    """Exact required inputs of one run's original-parent synthesis.

    ART-backed inputs need actual owner read receipts from the original parent
    session. Attempt outcomes are Work custody that the owner carries itself.
    """
    items=[]
    def add(kind,ident,art,**extra):
        row={'kind':kind,'id':ident,**extra}
        if isinstance(art,dict) and art.get('id') and (art.get('sha256') or art.get('revision')):
            exact=_art(art)
            row.update(sha256=exact['sha256'],artifact=exact,coverage='OWNER_READ_RECEIPT_REQUIRED',
                read={'operation':'read_artifact','payload':{'id':exact['id'],'expected_sha256':exact['sha256']}})
        else:row.update(sha256=None,artifact=None,coverage='CUSTODY_UNAVAILABLE')
        items.append(row)
    if artifact:add('plan',artifact['id'],artifact,meaning='Prepared plan, including the authored synthesis instructions.')
    packet=((pin or {}).get('research_workflow') or {}).get('input_packet') or {}
    if packet.get('id'):add('input-packet',packet['id'],packet)
    seen=set()
    for entry in _entries(state):
        proposal=entry.get('proposal') or {}
        if proposal.get('id') and ('proposal',proposal['id']) not in seen:
            seen.add(('proposal',proposal['id']));add('proposal',proposal['id'],proposal,turn_id=proposal.get('turn_id'))
        judgement=entry.get('judgement') or {}
        if judgement.get('turn_id') and ('judgement',judgement['turn_id']) not in seen:
            seen.add(('judgement',judgement['turn_id']))
            add('judgement',judgement['turn_id'],judgement.get('artifact'),verdict=judgement.get('verdict'),
                unresolved_findings=len(judgement.get('findings') or []))
    for attempt in state.get('attempts',[]):
        items.append({'kind':'attempt-result','id':attempt['event_id'],'sha256':None,'artifact':None,
            'effect':attempt.get('effect'),'iteration':attempt.get('iteration'),'coverage':'OWNER_CARRIED_RECORD'})
    return items


def _receipt_rows(root,project,session_id,receipt_ids):
    """Exact recorded read receipts of the original parent session; no caller string is trusted."""
    from laplace.writing import records
    D=_D();rows=[]
    for rid in receipt_ids:
        if not isinstance(rid,str) or not rid.startswith('READ-'):raise D.Refused('SYNTHESIS_READ_RECEIPT_UNKNOWN',receipt=rid)
        try:
            read=records.selected_journal_fields(project,rid,root,fields=['id','project','turn_id','operation','payload','output_sha256'])
            turn=records.selected_journal_fields(project,read['turn_id'],root,fields=['id','project','session_id'])
        except (KeyError,ValueError,OSError,TypeError,LookupError):
            raise D.Refused('SYNTHESIS_READ_RECEIPT_UNKNOWN',receipt=rid) from None
        if (not isinstance(read,dict) or read.get('id')!=rid or read.get('operation')!='read_artifact'
                or not isinstance(read.get('payload'),dict) or not read.get('output_sha256')):
            raise D.Refused('SYNTHESIS_READ_RECEIPT_UNKNOWN',receipt=rid)
        if not isinstance(turn,dict) or turn.get('project') not in (None,project) or turn.get('session_id')!=session_id:
            raise D.Refused('SYNTHESIS_READ_RECEIPT_FOREIGN','Only reads by the original parent session count as synthesis consumption.',receipt=rid)
        rows.append(read)
    return rows


def verify_consumption(root,project,session_id,item,receipt_ids):
    """Re-execute each recorded owner read; it must reproduce its digest and cover the exact input."""
    from laplace.projects import artifacts
    from laplace.writing import reads
    D=_D();art=item['artifact']
    try:required=artifacts.target(root,project,{'id':art['id']})[0]
    except (ValueError,KeyError,OSError):raise D.Refused('SYNTHESIS_INPUT_CUSTODY_UNAVAILABLE',kind=item['kind'],id=item['id']) from None
    pages=[];size=None;used=[]
    for read in _receipt_rows(root,project,session_id,receipt_ids):
        payload=read['payload']
        selected=sorted(set(payload)-WHOLE_READ_FIELDS)
        if selected:
            raise D.Refused('SYNTHESIS_READ_RECEIPT_NOT_WHOLE_INPUT','A selected projection is a real read but does not cover the whole required input; read its raw pages.',
                receipt=read['id'],kind=item['kind'],id=item['id'],selection=selected)
        try:physical=artifacts.target(root,project,payload)[0]
        except (ValueError,KeyError,OSError):physical=None
        if physical!=required:
            raise D.Refused('SYNTHESIS_READ_RECEIPT_WRONG_INPUT',receipt=read['id'],kind=item['kind'],id=item['id'])
        try:result=artifacts.read(root,project,payload)
        except (ValueError,KeyError,OSError):result=None
        if (not isinstance(result,dict) or not result.get('exists',True) or _sha(result.get('revision'))!=_sha(art['sha256'])
                or reads.read_output_digest('read_artifact',result)!=read['output_sha256']):
            raise D.Refused('SYNTHESIS_READ_RECEIPT_STALE','The recorded read no longer reproduces the exact required bytes.',receipt=read['id'],kind=item['kind'],id=item['id'])
        offset=result.get('offset',0);following=result.get('next_offset')
        if (any(result.get(k) is not None for k in ('pointer','selected_total_characters'))
                or isinstance(offset,bool) or not isinstance(offset,int) or offset<0
                or (following is not None and (isinstance(following,bool) or not isinstance(following,int) or following<=offset))):
            raise D.Refused('SYNTHESIS_READ_RECEIPT_NOT_WHOLE_INPUT','The re-executed read is not a raw page of the whole input.',receipt=read['id'],kind=item['kind'],id=item['id'])
        size=result.get('size_bytes');pages.append((offset,following));used.append(read['id'])
    # Coverage in the reader's own page unit: contiguous raw pages from 0 to the source end.
    cursor=0;complete=False
    for offset,following in sorted(pages,key=lambda page:page[0]):
        if offset>cursor:break
        if following is None:complete=True;break
        cursor=max(cursor,following)
    if not complete:
        raise D.Refused('SYNTHESIS_READ_COVERAGE_INCOMPLETE','Read every raw page of the exact required input.',kind=item['kind'],id=item['id'],covered_to=cursor,unit='reader-page-offset')
    return {'kind':item['kind'],'id':item['id'],'sha256':art['sha256'],'artifact_id':art['id'],'read_receipts':used,
        'coverage':'COMPLETE_EXACT_OWNER_READS','unit':'raw-artifact-pages','pages':len(pages),'size_bytes':size}


def _authored(value,judgements):
    D=_D()
    if not isinstance(value,dict) or set(value)-{'status','summary','conclusions','findings','remaining_work'}:raise D.Refused('INVALID_SYNTHESIS')
    if value.get('status') not in SYNTHESIS_STATUSES:raise D.Refused('INVALID_SYNTHESIS_STATUS',allowed=list(SYNTHESIS_STATUSES))
    summary=value.get('summary')
    if not isinstance(summary,str) or not summary.strip() or len(summary)>20000:raise D.Refused('SYNTHESIS_SUMMARY_REQUIRED')
    conclusions=value.get('conclusions',[]);remaining=value.get('remaining_work',[]);findings=value.get('findings',[])
    for name,rows in (('conclusions',conclusions),('remaining_work',remaining)):
        if not isinstance(rows,list) or len(rows)>64 or any(not isinstance(r,str) or not r.strip() or len(r)>4000 for r in rows):
            raise D.Refused('INVALID_SYNTHESIS',field=name)
    if not isinstance(findings,list) or len(findings)>256:raise D.Refused('INVALID_SYNTHESIS',field='findings')
    for row in findings:
        if (not isinstance(row,dict) or set(row)-{'judgement_id','finding_id','disposition','note'} or row.get('judgement_id') not in judgements
                or ('finding_id' in row and row['finding_id'] not in judgements[row['judgement_id']])
                or row.get('disposition') not in {'ADDRESSED','UNRESOLVED','DISPUTED'}
                or not isinstance(row.get('note',''),str) or len(row.get('note',''))>4000):
            raise D.Refused('INVALID_SYNTHESIS_FINDING','Each disposition names an exact required judgement and finding.',finding=copy.deepcopy(row) if isinstance(row,dict) else None)
    if value['status']!='COMPLETE' and not remaining:raise D.Refused('SYNTHESIS_REMAINING_WORK_REQUIRED')
    return {'status':value['status'],'summary':summary,'conclusions':list(conclusions),'findings':copy.deepcopy(findings),'remaining_work':list(remaining)}


def synthesis_publication(root,project,task,plan,pin,artifact,state,history,payload,acting):
    """Validate one original-parent synthesis and compose its exact owner document.

    plan is the original reserved plan; history(event_id) returns recorded event
    history. Nothing here admits, changes or accepts a child result.
    """
    import json
    D=_D();synthesis=pin.get('synthesis')
    if not synthesis:raise D.Refused('NO_AUTHORED_PARENT_SYNTHESIS')
    problem=bridge_problem(pin,plan)
    if problem is None and (synthesis.get('bridge')!=BRIDGE or not isinstance((plan or {}).get('synthesis_return_path'),str)):
        problem='The prepared plan has no complete synthesis bridge.'
    if problem:raise D.Refused('V2_BRIDGE_INCOMPLETE',problem)
    session=pin['prepared_by']['session_id']
    if acting.get('kind')!='native' or acting.get('session_id')!=session or not acting.get('turn_id'):
        raise D.Refused('ORIGINAL_PARENT_SESSION_REQUIRED','The authored synthesis executes in the original parent session.')
    actual=_turn_settings(root,project,acting['turn_id'],session)
    for field,required in (synthesis.get('declared_settings') or {}).items():
        if actual.get(field)!=required:
            raise D.Refused('PARENT_SYNTHESIS_SETTINGS_CONFLICT','The publishing parent turn no longer has the declared synthesis setting; restore it or prepare again.',field=field,required=required,actual=actual.get(field))
    if (state.get('synthesis') or {}).get('artifact'):raise D.Refused('SYNTHESIS_ALREADY_PUBLISHED',artifact=copy.deepcopy(state['synthesis']['artifact']))
    pending=[a['event_id'] for a in state.get('attempts',[]) if ((history(a['event_id']) or [{}])[-1]).get('state') not in SETTLED]
    if state.get('state') not in SYNTHESIS_DUE or pending:
        raise D.Refused('SYNTHESIS_NOT_DUE','Synthesis follows the loop exit or a settled stop; every attempt must be settled first.',state=state.get('state'),pending=pending)
    required=synthesis_inputs(state,pin,artifact)
    unavailable=[{'kind':r['kind'],'id':r['id']} for r in required if r['coverage']=='CUSTODY_UNAVAILABLE']
    if unavailable:raise D.Refused('SYNTHESIS_INPUT_CUSTODY_UNAVAILABLE',missing=unavailable)
    consumed=payload.get('consumed')
    if not isinstance(consumed,list) or len(consumed)>64:raise D.Refused('SYNTHESIS_CONSUMPTION_RECEIPT_REQUIRED')
    reading=[r for r in required if r['coverage']=='OWNER_READ_RECEIPT_REQUIRED'];known={(r['kind'],r['id']):r for r in reading}
    rows={}
    for row in consumed:
        if (not isinstance(row,dict) or set(row)-{'kind','id','read_receipts'} or not isinstance(row.get('read_receipts'),list)
                or not 1<=len(row['read_receipts'])<=32):
            raise D.Refused('SYNTHESIS_CONSUMPTION_RECEIPT_REQUIRED')
        key=(row.get('kind'),row.get('id'))
        if key not in known:raise D.Refused('SYNTHESIS_INPUT_NOT_REQUIRED',kind=key[0],id=key[1])
        if key in rows:raise D.Refused('SYNTHESIS_CONSUMPTION_DUPLICATE',kind=key[0],id=key[1])
        rows[key]={'kind':key[0],'id':key[1],'sha256':known[key]['sha256'],'read_receipt':row['read_receipts'][0],'read_receipts':list(row['read_receipts'])}
    synthesis_coverage(reading,list(rows.values()))
    coverage=[verify_consumption(root,project,session,item,rows[(item['kind'],item['id'])]['read_receipts']) for item in reading]
    judgements={}
    for entry in _entries(state):
        j=entry.get('judgement') or {}
        if j.get('turn_id'):judgements[j['turn_id']]=j
    authored=_authored(payload.get('synthesis'),{k:{f.get('id') for f in (v.get('findings') or []) if isinstance(f,dict)} for k,v in judgements.items()})
    latest=state.get('judgement') or {}
    # More than one pair: every pair's latest judgement is ACCEPT.
    verdicts=[(lane.get('judgement') or {}).get('verdict') for lane in state['pairs'].values()] if state.get('pairs') else [latest.get('verdict')]
    if authored['status']=='COMPLETE' and (any(v!='ACCEPT' for v in verdicts) or state.get('state') not in {'AWAITING_HUMAN_APPLY','APPLIED'}):
        raise D.Refused('SYNTHESIS_COMPLETE_NOT_SUPPORTED','COMPLETE needs the latest independent judgement ACCEPT at the human Apply boundary; publish BLOCKED or PARTIAL with remaining work.',verdict=latest.get('verdict') if not state.get('pairs') else verdicts,state=state.get('state'))
    findings=[]
    for ident,j in judgements.items():
        for f in j.get('findings') or []:
            fid=f.get('id') if isinstance(f,dict) else None
            chosen=next((x['disposition'] for x in authored['findings'] if x['judgement_id']==ident and x.get('finding_id',fid)==fid),'NOT_ADDRESSED_BY_SYNTHESIS')
            findings.append({'judgement_id':ident,'verdict':j.get('verdict'),'finding':copy.deepcopy(f),'synthesis_disposition':chosen})
    attempts=[]
    for attempt in state.get('attempts',[]):
        last=(history(attempt['event_id']) or [{}])[-1]
        attempts.append({'event_id':attempt['event_id'],'effect':attempt.get('effect'),'iteration':attempt.get('iteration'),
            'recorded_state':last.get('state'),'session_id':last.get('session_id'),'turn_id':last.get('turn_id'),
            'result':copy.deepcopy(last.get('result')),'error':last.get('last_error'),'custody':'work-delivery-event-history'})
    delivery=synthesis.get('delivery') or {}
    document={'schema_version':SYNTHESIS_SCHEMA,'work_id':task['id'],'project':project,'request_id':payload['request_id'],
        'plan_reference':copy.deepcopy(state.get('plan_reference')),'plan_generation':state.get('plan_generation'),
        'authored_synthesis':{'step_id':synthesis.get('step_id'),'title':synthesis.get('title'),'instructions_sha256':delivery.get('sha256'),
            'instructions_characters':delivery.get('characters'),'instructions_read':'The exact text is in the required plan input.'},
        'execution':{'location':'original-parent','session_id':session,'turn_id':acting['turn_id'],
            'prepared_settings':copy.deepcopy(synthesis.get('admitted_settings')),'declared_settings':copy.deepcopy(synthesis.get('declared_settings')),
            'actual_settings':actual},
        'run':{'state':state.get('state'),'iteration':state.get('iteration'),'admissions_used':len(state.get('attempts',[])),
            'loop_exit':copy.deepcopy(state.get('loop_exit')),'stop_request':copy.deepcopy(state.get('stop_request'))},
        'attempts':attempts,'inputs':coverage,'findings':findings,'status':authored['status'],'synthesis':authored,
        'meaning':'Original-parent synthesis over complete exact owner-read inputs. Read coverage and synthesis are not scientific acceptance or manuscript application.'}
    if len(json.dumps(document,ensure_ascii=False).encode())>4*DELIVERY_LIMITS['utf8_bytes']:raise D.Refused('SYNTHESIS_DOCUMENT_BOUND')
    return document


def _offered(actions,name):
    if isinstance(actions,dict):
        if name in actions:return copy.deepcopy(actions[name])
        actions=list(actions.values())
    for item in actions or []:
        if isinstance(item,dict) and ((item.get('native') or {}).get('payload') or {}).get('action')==name:return copy.deepcopy(item)
    return None


def _compact_action(action):
    """Exact native payload and standing of an issued action; transport variants stay in the detail read."""
    if not isinstance(action,dict):return action
    return {k:copy.deepcopy(action[k]) for k in ('available','permitted','reason','title','native','required_inputs','coverage') if k in action}


def stop_offer(actions,rows):
    """Compose existing controls for one selected run; this read starts and stops nothing."""
    owned=[{k:row.get(k) for k in ('step_id','event_id','session_id','turn_id','state')} for row in rows
        if row.get('event_id') and row.get('state') not in (None,*SETTLED)]
    complete=len(owned)<=DELIVERY_LIMITS['entries']
    return {'schema_version':STOP_SCHEMA,'future_admission_gate':_compact_action(_offered(actions,'workflow-stop-before-next')),
        'stop_run':_compact_action(_offered(actions,'workflow-stop-run')) if complete else None,'coverage':'COMPLETE' if complete else 'INCOMPLETE',
        'owned_children':owned[:DELIVERY_LIMITS['entries']],'owned_children_total':len(owned),
        'child_control':'Each owned child is stopped only through its own existing turn/producer owner; no PID, thread or parent-only stop.',
        'compose':'Gate future admission first, then control each owned child; report every child result exactly.'}


def stop_composition(gate,children):
    """Truthful aggregate of actual owner results; nothing unobserved is reported stopped."""
    gate=copy.deepcopy(gate) if isinstance(gate,dict) else {}
    observed=(gate.get('run') or {}).get('state',gate.get('state'))
    effective=bool(gate['effective']) if 'effective' in gate else observed=='STOP_BEFORE_NEXT';rows=[];unknown=[]
    for child in children:
        control=child.get('control')
        if child.get('observed_state')=='RESULT':stop='SETTLED'
        elif child.get('observed_state')=='NOT_ADMITTED' and effective:stop='GATED_NOT_ADMITTED'
        elif child.get('error'):stop='UNKNOWN'
        elif control is None:stop='NOT_REQUESTED'
        elif control.get('status') in {'UNKNOWN','NO_ACTIVE_TURN'} or control.get('effect')=='UNKNOWN':stop='UNKNOWN'
        elif control.get('status')=='REFUSED':stop='REFUSED'
        else:stop='REQUESTED'
        if stop=='UNKNOWN':unknown.append(child.get('event_id'))
        rows.append({'event_id':child.get('event_id'),'observed_state':child.get('observed_state'),'stop':stop,
            'control':copy.deepcopy(control),'error':child.get('error')})
    stopped=effective and all(r['stop'] in {'SETTLED','GATED_NOT_ADMITTED'} for r in rows)
    return {'schema_version':STOP_SCHEMA,'future_admission':{'observed_state':observed,'effective':effective,'owner_result':gate},
        'children':rows,'unknown':unknown,'run_stopped':stopped,
        'outcome':'STOPPED' if stopped else 'FUTURE_GATED_CHILDREN_PENDING' if effective else 'NOT_GATED',
        'effects':'Recorded effects, proposals and returns are retained; nothing is undone or refunded.',
        'meaning':'Labels describe this composition only. REQUESTED is not settled; settlement needs an observed RESULT.'}


def river_loop(state,pin):
    """Bounded recorded loop/synthesis metadata for one selected run; no body fanout."""
    if not state:return {'observed':False,'reason':'NO_RECORDED_RUN_STATE'}
    required=synthesis_requirements(state,pin);packet=any(r['kind']=='input-packet' for r in required)
    return {'observed':True,'run_state':state.get('state'),'iteration':state.get('iteration'),
        'admissions_used':len(state.get('attempts',[])),'started_at':state.get('loop_started_at'),
        'policy':loop_summary(state.get('policy')),'decision':copy.deepcopy(state.get('loop_decision')),'exit':copy.deepcopy(state.get('loop_exit')),
        'synthesis_inputs':{'total':len(required),'items':copy.deepcopy(required[:24]),'omitted':max(0,len(required)-24),
            'input_packet':'INCLUDED' if packet else 'NOT_IN_THIS_RECORD; read the prepared plan before synthesis'},
        'qualification':'Recorded run state only; no body read, attention or liveness is inferred.'}
