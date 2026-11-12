"""Bounded research phases in existing Work/WD custody and turn supervision.

This module selects the next admitted effect. It does not execute a model,
invent a run identity, apply a manuscript, or maintain another job/ledger.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import uuid
from pathlib import Path
from urllib.parse import urlencode

from laplace.core.identity import canonical_digest

SCHEMA = 'laplace.research-workflow-run/1'
KIND = 'workflow-run'
ACTIONS = ('workflow-preview', 'workflow-start', 'workflow-status', 'workflow-recover',
    'workflow-stop-before-next', 'workflow-resume', 'workflow-replan', 'workflow-readdress',
    'workflow-disposition', 'workflow-accept-boundary','workflow-bind','workflow-bind-request','workflow-request','workflow-compose-start','workflow-impact-preview',
    'workflow-stop-run','workflow-synthesis')
READS = ('workflow-preview', 'workflow-status','workflow-bind-request','workflow-request','workflow-compose-start','workflow-impact-preview')
EFFECTS = ('proposal-writer', 'independent-review', 'research-producer')
SETTLED = ('RESULT', 'STALE', 'UNCONFIRMED')


def _step_pattern():
    """A step id as the definition owner admits it (workflow_definitions.LOCAL_ID)."""
    from laplace.pipeline import workflow_definitions as D
    return D.local_id_schema_pattern()


def recipient_contract():
    """A recipient role, or (more than one pair) one pair step by its id."""
    return {'anyOf': [{'enum': ['writer', 'reviewer']}, {'type': 'string', 'pattern': _step_pattern()}]}


def contract_fields():
    from laplace.pipeline import workflow_operations as operations
    # Keys: the writer and reviewer approvals plus one per pair step, two steps for each of
    # the pairs one run takes (workflow_operations.research_pairs_per_run, which reads the
    # dispatch plan and prepare request contracts).
    recipient_keys = 2 * operations.research_pairs_per_run() + 2
    return {'expected_run_revision': {'type': 'string'}, 'expected_action_basis':{'type':'string'},
        'expected_plan_generation':{'type':'string'},'expected_impact_basis':{'type':'string'},
        'intervention':impact_intervention_contract(), 'reference': {'type': 'object'},
        'recipients': {'anyOf':[{'type': 'object', 'additionalProperties': {'type': 'string'},
            'properties': {'writer': {'type': 'string'}, 'reviewer': {'type': 'string'}},
            'propertyNames': {'pattern': _step_pattern()}, 'maxProperties': recipient_keys,
            'required': ['writer', 'reviewer'],
            'description': 'One writer and one reviewer approval; with more than one pair a step id names that step\'s own approval.'},{'type':'array','items':{'type':'object'}}]},
        'inputs': {'type': 'array', 'maxItems': 24, 'items': {'type': 'object'}},
        'selection': {'type': 'object'}, 'changed': {'type': 'object'},
        'runtime_seconds': {'type':'integer','minimum':1,'maximum':3600},
        'recipient': recipient_contract(), 'concern_id': {'type': 'string'},
        'subject': {'type': 'object'}, 'expected_basis': {'type': 'string'},
        'expected_concern_basis': {'type': 'string'},
        'disposition': {'enum': ['ACCEPT', 'REVISE', 'WITHDRAW', 'UNCHANGED']},
        'change_kind': {'enum': ['version', 'assumption']}, 'summary': {'type': 'string', 'maxLength': 2000},
        'evidence': {'type': 'array', 'maxItems': 24, 'items': {'type': 'object'}},
        'children': {'type': 'array', 'maxItems': 64, 'uniqueItems': True, 'items': {'type': 'string'}},
        'synthesis': {'type': 'object'}, 'consumed': {'type': 'array', 'maxItems': 64, 'items': {'type': 'object'}}}


def impact_intervention_contract():
    return {'oneOf':[
        {'type':'object','required':['action','reference'],'properties':{
            'action':{'const':'workflow-replan'},'reference':{'type':'object'},
            'inputs':{'type':'array','minItems':1,'maxItems':24,'items':{'type':'object'}},
            'selection':{'type':'object'}},'additionalProperties':False},
        {'type':'object','required':['action','recipient','recipient_binding_id'],'properties':{
            'action':{'const':'workflow-readdress'},'recipient':recipient_contract(),
            'recipient_binding_id':{'type':'string'}},'additionalProperties':False}]}


def preview_contract():
    return {'type':'object','required':['action','work_id','expected_work_revision','expected_run_revision','expected_plan_generation','intervention'],
        'properties':{'action':{'const':'workflow-impact-preview'},'work_id':{'type':'string'},
            'expected_work_revision':{'type':'string'},'expected_run_revision':{'type':'string'},'expected_plan_generation':{'type':'string'},
            'intervention':impact_intervention_contract()},'additionalProperties':False}


def _owners():
    from laplace.work import project_work as W, work_delivery as D
    return W, D


def _checked_plan(root,project,task,read_context=None):
    from laplace.writing import workflow_dispatch
    if read_context is None:return workflow_dispatch._checked(root,project,task)
    key=('workflow_progression.checked_plan',str(Path(root).resolve()),project,task['id'])
    if key not in read_context:read_context[key]=workflow_dispatch._checked(root,project,task)
    return read_context[key]


def work_facet(root,project,work_id,*,door=None,read_context=None):
    """Optional Work-owned run projection; no recursive object-facet call."""
    W,D=_owners();context={} if read_context is None else read_context
    task=D._read_tasks(root,project,context).get(work_id) or {}
    if not task.get('prepared_workflow'):return None
    try:_plan,pin,_artifact=_checked_plan(root,project,task,context)
    except (ValueError,OSError,KeyError) as error:
        return {'state':'UNAVAILABLE','reason':str(error),'read':read_handle(project,work_id)}
    if not pin.get('research_workflow'):return None
    return view(root,project,work_id,door=door,read_context=context)


def consumed_relations(root,project,*,read_context=None):
    """Bounded actual admitted evidence relations, separate from prepared intent."""
    W,D=_owners()
    from laplace.work import owner_discovery as O
    from laplace.writing import records
    context={} if read_context is None else read_context
    tasks=list(D._read_tasks(root,project,context).values());fold=D._read_fold(root,context);rows=[];unavailable=[];omitted=0
    for task in tasks[:128]:
        for event_id in dict.fromkeys(r['id'] for r in D._rows(task,D.EVENT) if r.get('workflow_execution')):
            history=D._history(task,event_id);intent=history[0]
            admitted=next((r for r in reversed(history) if r.get('turn_id')),None)
            if not admitted:continue  # preparation and reservation are not consumed model input
            turn=fold['turns'].get(admitted['turn_id']) or {};context=turn.get('workflow_execution') or {}
            if context.get('event_id')!=event_id:
                unavailable.append({'event_id':event_id,'state':'UNKNOWN'});continue
            for consumed in (context.get('input_packet') or {}).get('consumed_bases') or []:
                if len(rows)>=512:omitted+=1;continue
                rows.append({'dependent':O.work_reference(project,task['id']),**copy.deepcopy(consumed),
                    'relation':'admitted-evidence-packet','qualification':'PINNED',
                    'event_id':event_id,'turn_id':turn['id'],'effect':context['effect'],
                    'read':read_handle(project,task['id']),
                    'observation':'Exact evidence carried by the actual turn admission; model attention or scientific acceptance is not inferred.'})
    return {'items':rows,'coverage':{'state':'RECORDED_ADMISSIONS_ONLY','work_total':len(tasks),'work_inspected':min(128,len(tasks)),
        'work_omitted':max(0,len(tasks)-128),'relations_omitted':omitted,'unavailable':unavailable,
        'meaning':'Only actual admitted recipients are dependents here; no claim about unrecorded or merely prepared relationships.'}}


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_handle(project, work_id):
    payload = {'action': 'workflow-status', 'work_id': work_id}
    return {'native': {'operation': 'work_delivery', 'payload': payload},
        'http': {'method': 'GET', 'url': '/work/delivery?' + urlencode({'project': project, 'request':json.dumps(payload,separators=(',',':'))})}}


def _phase_rows(task):
    return [row for row in task.get('phases') or () if row.get('kind') == KIND]


ROLE_EFFECT = {'writer': 'proposal-writer', 'reviewer': 'independent-review'}
LANE_EXITS = ('AWAITING_HUMAN_APPLY', 'LIMIT_REACHED', 'PARTIAL')


def research_pairs_of(spec):
    """The prepared writer/reviewer pairs; a one-pair plan keeps its original writer/reviewer fields."""
    return copy.deepcopy(spec['pairs']) if spec.get('pairs') else [{'writer': spec['writer'], 'reviewer': spec['reviewer']}]


def research_obligations(spec, body=None):
    """The Work review obligations of a prepared research run: one per pair, the original one for one pair."""
    titles = {s['id']: s.get('title') or s['id'] for s in (body or {}).get('steps', [])}
    return [{'id': obligation_id(spec, pair['writer']), 'scope': 'other',
             'label': 'Independent proposal and selected-evidence review' + ('' if not spec.get('pairs') else ': ' + titles.get(pair['writer'], pair['writer'])),
             'required': True, 'independent': True, 'inputs': []} for pair in research_pairs_of(spec)]


def obligation_id(spec, writer):
    return 'independent-draft-review' if not spec.get('pairs') else 'independent-draft-review-' + writer


def _lanes(state, spec):
    """(pair, lane) per prepared pair. One pair's lane is the run row itself, so its shape is unchanged."""
    if not spec.get('pairs'):
        return [({'writer': spec['writer'], 'reviewer': spec['reviewer']}, state)]
    held = state.setdefault('pairs', {})
    return [(pair, held.setdefault(pair['writer'], {'writer': pair['writer'], 'reviewer': pair['reviewer'], 'next': 'writer', 'iteration': 1}))
            for pair in spec['pairs']]


def _lane_of(state, spec, step_id):
    for pair, lane in _lanes(state, spec):
        if step_id in (pair['writer'], pair['reviewer']):return pair, lane
    raise ValueError('This step belongs to no prepared writer/reviewer pair.')


def _lane_attempts(state, spec, pair):
    if not spec.get('pairs'):return list(state['attempts'])
    return [a for a in state['attempts'] if a.get('step_id') in (pair['writer'], pair['reviewer'])]


def _recipient_id(state, name, step):
    """A step's own approved recipient when one is selected for it, otherwise its role's."""
    recipients = state.get('recipients') or {}
    return recipients.get(step) or recipients.get(name)


def _check_recipients(root, project, task, pin, selected, only=None):
    """Start/readdress custody: every pair step resolves to a human-approved binding matching its settings."""
    spec = pin['research_workflow']; pairs = research_pairs_of(spec)
    steps = {pair[name] for pair in pairs for name in ROLE_EFFECT}
    if not isinstance(selected, dict) or (only is None and (not selected or not (set(selected) == {'writer', 'reviewer'} or (spec.get('pairs') and set(selected) <= {'writer', 'reviewer'} | steps)))):
        raise ValueError('Select exact writer and reviewer binding identities.')
    for pair in pairs:
        for name, effect in ROLE_EFFECT.items():
            if only is not None and only not in (name, pair[name]):continue
            ident = (selected.get(pair[name]) if spec.get('pairs') else None) or selected.get(name)
            if not ident:raise ValueError('Select an approved ' + name + ' for step ' + pair[name] + '.')
            _binding(root, project, task, ident, effect, pin['settings'][pair[name]]['values'])


def _recipient_names(pin):
    """Readdress targets: a role (every pair), or, with more than one pair, one pair step."""
    spec = pin['research_workflow']
    return ['writer', 'reviewer'] + ([pair[name] for pair in spec['pairs'] for name in ROLE_EFFECT] if spec.get('pairs') else [])


def _resumable(state, pin):
    """A retained run with a pending step in some pair and a recipient for every pair step."""
    spec = pin['research_workflow']; recipients = state.get('recipients') or {}
    if not spec.get('pairs'):
        return state.get('next') in {'writer', 'reviewer'} and set(recipients) == {'writer', 'reviewer'}
    lanes = _lanes(copy.deepcopy(state), spec)
    return (any(lane.get('next') in {'writer', 'reviewer'} for _, lane in lanes)
            and all(_recipient_id(state, name, pair[name]) for pair, _ in lanes for name in ROLE_EFFECT))


def _exit_lane(state, lane, spec, word, **extra):
    """A pair leaves the loop. One pair's exit is the run's state, as before; with more, the run ends when every pair has."""
    if not spec.get('pairs'):
        state.update(state=word, next=None, **extra);return
    lane.update(next=None, exit=word, **extra)
    lanes = [held for _, held in _lanes(state, spec)]
    if all(held.get('exit') in LANE_EXITS and held.get('next') is None for held in lanes):
        words = {held['exit'] for held in lanes}
        state['state'] = 'AWAITING_HUMAN_APPLY' if words == {'AWAITING_HUMAN_APPLY'} else 'PARTIAL' if 'PARTIAL' in words else 'LIMIT_REACHED'


def _load(root, project, work_id, *, read_context=None):
    W, D = _owners()
    task = D._read_tasks(root,project,read_context).get(work_id)
    if not task or not task.get('prepared_workflow'):
        raise ValueError('Select an existing prepared workflow Work of this project.')
    plan, pin, artifact = _checked_plan(root,project,task,read_context)
    if not pin.get('research_workflow'):
        raise ValueError('This saved workflow uses the existing dispatch profile, not the research review policy.')
    phases = _phase_rows(task)
    state = copy.deepcopy(phases[-1]['run']) if phases else {
        'state': 'PREPARED', 'iteration': 1, 'next': 'writer', 'attempts': [], 'interventions': [],
        'recipients': {}, 'plan_reference': pin['reference'], 'policy': pin['research_workflow']['policy']}
    if not phases and pin['research_workflow'].get('pairs'):
        # More than one pair: the next step and iteration are each pair's own.
        for key in ('iteration', 'next'):state.pop(key)
        _lanes(state, pin['research_workflow'])
    state.setdefault('plan_generation',canonical_digest({'id':artifact['id'],'sha256':artifact['sha256'] if 'sha256' in artifact else artifact.get('revision')}))
    if state.get('plan_artifact'):
        from laplace.projects import artifacts
        from laplace.projects.writing_sources import file_revision
        retained = state['plan_artifact'];target = artifacts._artifact_target(root, project, {'id':retained['id']})[0]
        if file_revision(target) != retained['sha256']:raise ValueError('Retained replanned workflow bytes changed.')
        plan = json.loads(target.read_text());pin = plan['workflow_definition'];artifact = retained
        if pin['reference'] != state['plan_reference']:raise ValueError('Replan reference custody changed.')
    return task, plan, pin, artifact, state


def _revision(task, pin):
    _, D = _owners()
    return canonical_digest({'reference': pin['reference'], 'plan': task['prepared_workflow'],
        'phases': [(r['id'], r.get('intent_sha256')) for r in _phase_rows(task)],
        'events': [(r['id'], r['state'], r.get('turn_id'), r.get('research_run_id'))
                   for r in D._rows(task, D.EVENT) if r.get('workflow_execution')]})


def _append(root, project, task, request_id, action, state, intent):
    W, _ = _owners()
    ident = 'PHASE-' + canonical_digest([project, task['id'], request_id])[7:31]
    digest = canonical_digest(intent)
    old = next((r for r in _phase_rows(task) if r['id'] == ident), None)
    if old:
        if old['intent_sha256'] != digest or old['action'] != action:
            raise ValueError('Workflow request_id already has different intent.')
        return old
    row = {'record': 'project-work-phase', 'kind': KIND, 'id': ident, 'project': project,
        'work_id': task['id'], 'request_id': request_id, 'action': action, 'intent_sha256': digest,
        'run': copy.deepcopy(state), 'ts': _now()}
    try:
        return W._append(root, row)
    except Exception:
        # An acknowledgement fault cannot create a second generation.
        current = W._tasks(project, root).get(task['id'], {})
        found = [r for r in _phase_rows(current) if r['id'] == ident]
        if len(found) == 1 and found[0].get('intent_sha256') == digest:
            return found[0]
        raise


def _artifact_once(root, project, path, value, metadata, *, turn_id=None):
    from laplace.projects import artifacts
    from laplace.writing import records
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    raw = text.encode(); digest = canonical_digest(value)
    rows = [r for r in records.index(root).by_project.get(project, ())
        if r['record'] == 'writing-artifact' and r.get('artifact_path') == path and r.get('scope') == 'project']
    if rows:
        selected = rows[-1]
        original = records.raw_indexed_record(records.index(root), selected)
        if original.get('reader_metadata') != metadata:
            raise ValueError('Workflow artifact path belongs to another publication.')
        # The private caller already holds its run/admission authority. Its acting
        # turn reaches the same reserved-path check that guarded the first store.
        artifacts.recover_workflow_publication(root, project, selected['id'], original['sha256'], metadata,
            admit=lambda: None, turn_id=turn_id)
        target = artifacts.resolve_path(root, project, path, 'project')
        if target.read_bytes() != raw:
            raise ValueError('Workflow retained artifact differs from its original intended bytes.')
        result = {'id': selected['id'], 'path': str(target.relative_to(root)), 'artifact_path': path,
                  'revision': original['sha256']}
    else:
        result = artifacts.store(root, project, {'scope': 'project', 'path': path, 'before': None,
            'content': text, 'reason': 'Exact selected workflow input/proposal, separate from manuscript application'},
            turn_id, owner_metadata=metadata)
    return {'id': result['id'], 'path': result['path'], 'artifact_path': path, 'scope': 'project',
        'sha256': result['revision'], 'value_digest': digest,
        'read': {'native': {'operation': 'read_artifact', 'payload': {'id': result['id'], 'expected_sha256': result['revision']}},
                 'http': artifacts.human_read(project, path, 'project', result['revision'])['http']}}


def _retained_synthesis(root, project, path, request_id, prepared_by, composed):
    """The first durable synthesis for this exact request, or the newly composed one.

    A retry of the same request from a later genuine turn of the original parent
    session recomposes the same document except execution.turn_id. The retained
    first publication (its bytes, digest and original turn) is then completed as
    published. The current actor was already validated by synthesis_publication
    and is validated again by the reserved-path check during recovery. Any other
    difference keeps the composed document, which _artifact_once refuses.
    """
    from laplace.writing import records
    rows = [r for r in records.index(root).by_project.get(project, ())
        if r['record'] == 'writing-artifact' and r.get('artifact_path') == path and r.get('scope') == 'project']
    if not rows:
        return composed
    held = records.selected_journal_fields(project, rows[-1]['id'], root, fields=['id', 'after', 'reader_metadata'])
    metadata = held.get('reader_metadata') or {}
    after = held.get('after')
    if (not isinstance(after, str) or metadata.get('publication_kind') != 'research-synthesis'
            or metadata.get('request_id') != request_id or metadata.get('prepared_by') != prepared_by):
        return composed
    try:
        retained = json.loads(after)
    except ValueError:
        return composed
    def without_turn(value):
        value = copy.deepcopy(value)
        if isinstance(value, dict) and isinstance(value.get('execution'), dict):
            value['execution'].pop('turn_id', None)
        return value
    if (not isinstance(retained, dict) or canonical_digest(retained) != metadata.get('intent_digest')
            or json.dumps(retained, ensure_ascii=False, sort_keys=True, separators=(',', ':')) != after
            or without_turn(retained) != without_turn(composed)):
        return composed
    return retained


def capture_packet(root, project, entries, path, metadata, *, turn_id=None):
    from laplace.work import object_facets
    packet = object_facets.capture_inputs(root, project, {'entries': entries})
    from laplace.writing import records
    from laplace.projects import artifacts
    prior = [r for r in records.index(root).by_project.get(project, ())
             if r['record'] == 'writing-artifact' and r.get('artifact_path') == path]
    if prior:
        row = records.raw_indexed_record(records.index(root), prior[-1])
        if row.get('reader_metadata') != metadata:raise ValueError('Input packet request belongs to another intent.')
        artifacts.recover_workflow_publication(root, project, row['id'], row['sha256'], metadata, admit=lambda: None)
        held = json.loads(artifacts._artifact_target(root, project, {'id': row['id']})[0].read_text())
        if held['consumed_bases'] != packet['consumed_bases']:
            raise ValueError('Retained input packet basis changed; inspect the original preparation, do not replace it.')
        packet = held
    saved = _artifact_once(root, project, path, packet, metadata, turn_id=turn_id)
    return {**saved, 'consumed_bases': copy.deepcopy(packet['consumed_bases']),
            'entries': copy.deepcopy(entries), 'input_policy': 'evidence-packet'}


def compile_plan(root, caller, row, body, payload, prepared_by):
    """Compile only the executable, bounded proposal/review feedback shape."""
    from laplace.pipeline import workflow_definitions as D
    from laplace.writing import records
    from laplace.pipeline import authoring
    from laplace.pipeline import workflow_operations as operations
    selected = payload['step_ids'];steps = {s['id']:s for s in body['steps']}
    if len(set(selected))!=len(selected) or not set(selected)<=set(steps):raise D.Refused('UNSUPPORTED_RESEARCH_TOPOLOGY')
    synthesis=operations.parent_synthesis(root,caller.namespace,body,selected,prepared_by)
    selected=[sid for sid in selected if steps[sid]['assignment']['role']!='synthesis']
    if body['run_policy']['profile']==D.RESEARCH_POLICY_V2 and not synthesis:raise D.Refused('EXTENDED_POLICY_REQUIRES_PARENT_SYNTHESIS')
    pairs, issues = operations.research_pairs(body, selected, [synthesis['step_id']] if synthesis else [])
    if issues:
        first = dict(issues[0])
        if first['code'] == 'UNSUPPORTED_RESEARCH_TOPOLOGY': first['message'] = 'Only draft→review and bounded review→revision are executable here.'  # the base's prepare sentence
        raise D.Refused(first.pop('code'), **first)
    edges = [e for e in body.get('edges', []) if not (synthesis and e['to'] == synthesis['step_id']) and (e['from'] in selected or e['to'] in selected)]
    if body['run_policy']['max_iterations'] > 1:
        for writer, reviewer in pairs:
            if not any(e['kind'] == 'feedback' and (e['from'], e['to']) == (reviewer, writer) for e in edges):
                raise D.Refused('FEEDBACK_EDGE_REQUIRED', step_id=writer)
    single = len(pairs) == 1
    writers = [w for w, _ in pairs]; reviewers = [r for _, r in pairs]
    settings, _ = D.resolve_settings(root, caller, body, edit_revision=row['definition_revision'])
    for sid in selected:
        if settings[sid].get('error') or not steps[sid]['assignment'].get('instructions','').strip():
            raise D.Refused('RESEARCH_SETTINGS_OR_INSTRUCTIONS_UNAVAILABLE', step_id=sid)
        if any(steps[sid].get(k) for k in ('inputs','outputs','targets')):
            raise D.Refused('UNCONSUMED_STEP_DECLARATION', 'Select actual preparation inputs; graph labels are not effect grants.')
    for reviewer in reviewers:
        if settings[reviewer]['values'].get('input_policy') != 'evidence-packet':
            raise D.Refused('UNSUPPORTED_REVIEW_INPUT_POLICY', 'This executable loop uses explicit evidence-packet review. Target-only requires the separate qualified reader admission.', step_id=reviewer)
    for writer in writers:
        if settings[writer]['values'].get('input_policy') not in (None,'evidence-packet'):
            raise D.Refused('UNSUPPORTED_WRITER_INPUT_POLICY', step_id=writer)
    inputs = payload.get('inputs')
    if not isinstance(inputs,list) or not inputs:raise D.Refused('SELECTED_EVIDENCE_REQUIRED')
    parent = records.fold_records(root)['turns'].get(getattr(caller,'turn_id',None), {})
    selection = copy.deepcopy(payload.get('selection') or parent.get('selection') or {})
    manuscript_basis=_manuscript_basis(root,caller.namespace,selection)
    # One pair keeps its original packets; more pairs name each packet by its own step.
    mapping = {writers[0]:'write', reviewers[0]:'review'} if single else {
        sid: kind + '-' + hashlib.sha256(sid.encode()).hexdigest()[:16] for w, r in pairs for kind, sid in (('write', w), ('review', r))}
    if len(set(mapping.values())) != len(mapping):raise D.Refused('PACKET_ID_COLLISION')
    order = [sid for pair in pairs for sid in pair]
    delivered={sid:operations.compiled_instruction(root,caller.namespace,body,sid,prepared_by,research=True) for sid in selected}
    pin = {'schema_version':'laplace.workflow-app-preparation/1','project':caller.namespace,
        'request_id':payload['request_id'],'intent_digest':canonical_digest(payload),'reference':payload['reference'],
        'step_ids':list(selected),'step_packets':mapping,'settings':{sid:settings[sid] for sid in selected},
        'settings_digest':canonical_digest({sid:settings[sid]['values'] for sid in selected}), 'prepared_by':prepared_by,
        'parent_contract':{'kind':'authored-original-parent' if synthesis else 'bounded-research-review','authored_synthesis_consumed':bool(synthesis)},
        **({'synthesis':synthesis} if synthesis else {}),'context_delivery':{sid:value[1] for sid,value in delivered.items()},
        'research_workflow':{'policy':copy.deepcopy(body['run_policy']),
            **({'writer':writers[0],'reviewer':reviewers[0]} if single else {'pairs':[{'writer':w,'reviewer':r} for w, r in pairs]}),
            'selection':selection,'manuscript_basis':manuscript_basis,'inputs':copy.deepcopy(inputs),
            'instructions':{sid:value[0] for sid,value in delivered.items()}}}
    plan = {'schema_version':'laplace.dispatch-plan/1','fan_out_max':payload['fan_out_max'],'goal':payload['goal'],
        'packets':[{'packet':mapping[sid],'role':'worker' if sid in writers else 'judge','scope':'project',
            'brief':delivered[sid][0],'return_path':'development/workflows/research-'+
                canonical_digest([caller.namespace,payload['request_id']])[7:31]+'/'+mapping[sid]+'-unused.json',
            **{k:v for k,v in settings[sid]['values'].items() if k in ('provider','model','effort') and v is not None},
            # Each reviewer reads only its own writer; the one-pair plan is unchanged.
            **({} if single or sid in writers else {'depends_on':[mapping[writers[reviewers.index(sid)]]]})} for sid in order],
        'workflow_definition':pin}
    if synthesis:
        from laplace.writing.workflow_dispatch import _keys
        plan['synthesis_return_path']=_keys(caller.namespace,payload['request_id'])[1].rsplit('/',1)[0]+'/parent-return.json'
    problem=operations.bridge_problem(pin,plan)
    if problem:raise D.Refused('V2_BRIDGE_INCOMPLETE',problem)
    return plan,pin


def _manuscript_basis(root,project,selection,*,expected=None):
    from laplace.pipeline import authoring,workflow_definitions as D
    from laplace.manuscript import manuscript_source as M
    from laplace.core.identity import revision_matches
    physical={};inspected=authoring.inspect(project,selection=selection,repo_root=root,context_id='',_source_observation=physical)
    if not inspected.get('sources'):raise D.Refused('EXACT_MANUSCRIPT_SELECTION_REQUIRED')
    observed=M.observation(project,root,source=physical['document'],source_tree=physical['traversal'])
    actual={'selection_identity':observed['selection_identity'],
        'file_revisions':{row['file']:row['sha256'] for row in inspected['sources']}}
    asked=selection.get('source_observation') if isinstance(selection,dict) else None
    for basis in (asked,expected):
        if basis is None:continue
        if (not isinstance(basis,dict) or set(basis)!={'selection_identity','file_revisions'}
                or not isinstance(basis['file_revisions'],dict) or set(basis['file_revisions'])!=set(actual['file_revisions'])
                or not revision_matches(basis['selection_identity'],actual['selection_identity'])
                or any(not revision_matches(pin,actual['file_revisions'][file]) for file,pin in basis['file_revisions'].items())):
            raise D.Refused('MANUSCRIPT_SELECTION_CHANGED','Inspect the exact current document/section before new effects.')
    return actual


def _packet(root, project, pin, *, revalidate=False):
    from laplace.projects import artifacts
    selected = pin['research_workflow']['input_packet']
    path, _, _, _ = artifacts._artifact_target(root, project, {'id': selected['id']})
    from laplace.projects.writing_sources import file_revision
    if file_revision(path) != selected['sha256']:
        raise ValueError('The selected workflow evidence packet changed or is unavailable.')
    packet = json.loads(path.read_text())
    if revalidate:
        from laplace.work import object_facets
        now = object_facets.capture_inputs(root, project, {'entries': selected['entries']})
        if now['consumed_bases'] != selected['consumed_bases']:
            raise ValueError('Selected workflow inputs changed; inspect and explicitly replan.')
        held=pin['research_workflow'].get('manuscript_basis')
        if held is None:raise ValueError('Prepared manuscript basis is unavailable; inspect and explicitly replan.')
        _manuscript_basis(root,project,pin['research_workflow']['selection'],expected=held)
    return packet


def _binding(root, project, task, ident, effect, settings):
    _, D = _owners()
    problem = D._binding_problem(task, ident)
    row = D._latest(task, D.BINDING, ident)
    if problem or not row or row.get('recipient_kind')!='app-owned' or row.get('effect') != effect or row.get('approved_by') != 'human':
        raise ValueError('Select the exact human-approved ' + effect + ' binding: ' + str(problem or 'wrong effect/approval'))
    if effect != 'research-producer' and any(row.get(k) != settings.get(k) for k in ('provider', 'model', 'effort')):
        raise ValueError('Approved recipient settings differ from the consumed workflow settings.')
    return D._public_binding(row)


def _action(project, work, action, revision, *, permitted=True, reason='', extra=None):
    payload = {'action': action, 'work_id': work, 'expected_run_revision': revision, **(extra or {})}
    return {'available': True, 'permitted': permitted, 'reason': reason,
        'title':{'workflow-start':'Prepare start message','workflow-recover':'Check and recover this run',
            'workflow-stop-before-next':'Stop before next step','workflow-resume':'Resume pending step',
            'workflow-replan':'Use a revised saved plan','workflow-readdress':'Change future recipient',
            'workflow-disposition':'Record scientific disposition','workflow-accept-boundary':'Accept human Apply boundary',
            'workflow-stop-run':'Stop this run and its owned children','workflow-synthesis':'Publish original-parent synthesis'}.get(action,action),
        'required_inputs': ['request_id'], 'native': {'operation': 'work_delivery', 'payload': payload},
        'http': {'method': 'POST', 'url': '/work/delivery', 'payload': {'project': project, **payload}},
        'read': read_handle(project, work)}


def preview_read(project,work_id,work_revision,revision,generation,intervention):
    request={'action':'workflow-impact-preview','work_id':work_id,'expected_run_revision':revision,
        'expected_work_revision':work_revision,'expected_plan_generation':generation,'intervention':copy.deepcopy(intervention)}
    return {'native':{'operation':'work_delivery','payload':request},
        'http':{'method':'GET','url':'/work/delivery?'+urlencode({'project':project,
            'request':json.dumps(request,separators=(',',':'),ensure_ascii=False)})}}


def _impact_candidate(root,project,task,pin,state,intervention):
    """Existing compiler/read validation only: never publish the prospective plan."""
    W,D=_owners();spec=pin['research_workflow'];current={'reference':state['plan_reference'],
        'settings_digest':pin['settings_digest'],'settings':copy.deepcopy(pin['settings']),
        'inputs':copy.deepcopy(spec['input_packet']['consumed_bases']),
        'manuscript_basis':copy.deepcopy(spec.get('manuscript_basis')),'policy':copy.deepcopy(state['policy'])}
    if intervention['action']=='workflow-replan':
        if any(D._history(task,a['event_id'])[-1]['state'] not in {'RESULT','STALE','UNCONFIRMED'} for a in state['attempts']):
            raise ValueError('Stop before next and let the actual current recipient settle before replanning.')
        from laplace.pipeline import workflow_definitions as definitions
        from laplace.work import owner_discovery,object_facets
        reference=intervention['reference']
        if not isinstance(reference.get('version'),dict):raise ValueError('Replan selects an exact saved definition version.')
        caller=owner_discovery.project_scope(project,'sdk')
        row,_,_=definitions._select(definitions._rows(root),caller,{'reference':reference});body=definitions._body(root,row)
        if row['scope']!={'kind':'project','namespace':project} or not body.get('run_policy'):
            raise ValueError('Replacement must be a saved research-review definition of this project.')
        request={'action':'prepare','profile':definitions.APP_PROFILE,'reference':reference,
            'request_id':'preview-'+canonical_digest(intervention)[7:31],
            'goal':task['goal'],'fan_out_max':2*len(research_pairs_of(spec)),'step_ids':[*(pair[name] for pair in research_pairs_of(spec) for name in ROLE_EFFECT),
                *[s['id'] for s in body['steps'] if s['assignment']['role']=='synthesis']],
            'selection':intervention.get('selection',spec['selection']),
            'inputs':intervention.get('inputs',spec['input_packet']['entries'])}
        _plan,candidate=compile_plan(root,caller,row,body,request,pin['prepared_by'])
        packet=object_facets.capture_inputs(root,project,{'entries':candidate['research_workflow']['inputs']})
        prospective={'reference':reference,'settings_digest':candidate['settings_digest'],
            'settings':copy.deepcopy(candidate['settings']),'inputs':copy.deepcopy(packet['consumed_bases']),
            'manuscript_basis':copy.deepcopy(candidate['research_workflow']['manuscript_basis']),
            'policy':copy.deepcopy(candidate['research_workflow']['policy']),
            'packet':{'measurements':copy.deepcopy(packet.get('measurements')),'coverage':'EXACT_SELECTED_REPRESENTATIONS',
                'content_digest':canonical_digest(packet)}}
        selected=dict(state.get('recipients') or {});steps=candidate['research_workflow']
    else:
        _packet(root,project,pin,revalidate=True)
        selected={**(state.get('recipients') or {}),intervention['recipient']:intervention['recipient_binding_id']}
        steps=spec;candidate=pin;prospective=copy.deepcopy(current)
        if intervention['recipient'] not in _recipient_names(pin):raise ValueError('Choose the writer or reviewer recipient.')
        _check_recipients(root,project,task,pin,selected,only=intervention['recipient'])
    future=[];multi=bool(steps.get('pairs'))
    for pair in research_pairs_of(steps):
      for name,effect in ROLE_EFFECT.items():
        ident=(selected.get(pair[name]) if multi else None) or selected.get(name);entry={'recipient':name,'effect':effect,'step_id':pair[name],
            'settings':copy.deepcopy(candidate['settings'][pair[name]]['values']),
            'input_policy':'evidence-packet','admission':'NOT_ADMITTED_BY_PREVIEW'}
        try:
            if not ident:raise ValueError('Select an explicit human-approved recipient.')
            binding=_binding(root,project,task,ident,effect,entry['settings'])
            entry.update(standing='ELIGIBLE_AT_READ',binding={k:binding.get(k) for k in
                ('id','revision','label','provider','model','effort','expires_at')})
        except ValueError as error:
            entry.update(standing='NEEDS_APPROVAL_OR_READDRESS',binding_id=ident,reason=str(error))
        future.append(entry)
    changes={'definition':current['reference']!=prospective['reference'],
        'settings':current['settings_digest']!=prospective['settings_digest'],
        'inputs':current['inputs']!=prospective['inputs'],
        'manuscript':current['manuscript_basis']!=prospective['manuscript_basis'],
        'policy':current['policy']!=prospective['policy'],
        'recipient':intervention.get('recipient'),
        'binding_changed':intervention['action']=='workflow-readdress' and
            (state.get('recipients') or {}).get(intervention['recipient'])!=intervention['recipient_binding_id']}
    return {'before':current,'after':prospective,'changes':changes,'future':future}


def _impact_observation(root,project,payload):
    from jsonschema import Draft202012Validator
    if next(Draft202012Validator(preview_contract()).iter_errors(payload),None):
        raise ValueError('Select the closed workflow impact-preview request.')
    W,D=_owners();task,_plan,pin,_artifact,state=_load(root,project,payload['work_id'])
    observed={'work_revision':W._task_revision(task),'run_revision':_revision(task,pin),
        'plan_generation':state['plan_generation'],'recorded_phase_state':state['state'],
        'definition':copy.deepcopy(state['plan_reference'])}
    retained=[]
    for attempt in state['attempts']:
        history=D._history(task,attempt['event_id']);latest=history[-1];intent=history[0]
        admitted=next((row for row in reversed(history) if row.get('turn_id')),None)
        retained.append({'event_id':attempt['event_id'],'effect':attempt['effect'],'iteration':attempt['iteration'],
            'state':latest['state'],'session_id':admitted.get('session_id') if admitted else None,
            'turn_id':admitted.get('turn_id') if admitted else None,
            'captured_binding':{k:intent['recipient'].get(k) for k in ('id','revision','provider','model','effort')},
            'read':read_handle(project,task['id'])})
    result={'schema_version':'laplace.workflow-impact-preview/1','project':project,'work_id':task['id'],
        'work':{'id':task['id'],'title':task['title'],'revision':observed['work_revision']},
        'observed':observed,'intervention':copy.deepcopy(payload['intervention']),
        'prepared_parent':{'project':project,'session_id':pin['prepared_by']['session_id']},
        'retained_effects':{'items':retained[-20:],'coverage':{'known':len(retained),'omitted':max(0,len(retained)-20)},
            'meaning':'Already admitted effects and unconfirmed reservations retain their exact original identities; none are rewritten by this preview.'},
        'reinspection_read':read_handle(project,task['id']),
        'scope':{'supported':'bounded research proposal/review profile','future_only':True,'manuscript_apply':'separate human owner effect',
            'provider_capacity':'NOT_ESTABLISHED','authority':'revalidated by the actual effect owner on confirmation'},
        'domain_effects':[]}
    if (payload['expected_work_revision']!=observed['work_revision'] or payload['expected_run_revision']!=observed['run_revision']
            or payload['expected_plan_generation']!=observed['plan_generation']):
        return {**result,'state':'CHANGED_INPUT','reason':'The observed run or plan generation changed; inspect before a new preview.'}
    try:prospective=_impact_candidate(root,project,task,pin,state,payload['intervention'])
    except (ValueError,OSError,KeyError) as error:
        code=(getattr(error,'details',{}) or {}).get('code')
        changed=code in {'MANUSCRIPT_SELECTION_CHANGED','CHANGED_INPUT'} or str(error).startswith('CHANGED_INPUT:')
        return {**result,'state':'CHANGED_INPUT' if changed else 'REFUSED','reason':str(error)[:1000],
            'reason_code':code or 'INTERVENTION_UNAVAILABLE'}
    basis=canonical_digest({'observed':observed,'intervention':payload['intervention'],'prospective':prospective,
        'retained':retained})
    return {**result,'state':'READY','impact_basis':basis,**prospective}


def impact_preview(root,project,payload,*,door=None):
    """Pure prospective effect meaning; READY is never an execution promise."""
    result=_impact_observation(root,project,payload)
    if result['state']=='READY':
        intent=payload['intervention'];confirm=_action(project,payload['work_id'],intent['action'],
            payload['expected_run_revision'],extra={**{k:copy.deepcopy(v) for k,v in intent.items() if k!='action'},
                'request_id':'workflow-'+uuid.uuid4().hex,'expected_plan_generation':payload['expected_plan_generation'],
                'expected_work_revision':payload['expected_work_revision'],'expected_impact_basis':result['impact_basis']})
        try:
            actor=_admit_actor(root,project,door or {})
            if actor['kind']=='native' and actor.get('session_id')!=result['prepared_parent']['session_id']:
                raise ValueError('Confirmation requires the original author session or an explicit human action.')
        except (ValueError,KeyError) as error:confirm.update(permitted=False,reason=str(error))
        confirm['request_read']=request_handle(project,payload['work_id'],confirm['http']['payload']['request_id'])
        result['confirmation']=confirm
    return copy.deepcopy(result)


def request_handle(project, work_id, request_id, *, binding=False):
    payload={'action':'workflow-bind-request' if binding else 'workflow-request','work_id':work_id,'request_id':request_id}
    return {'native':{'operation':'work_delivery','payload':payload},'http':{'method':'GET','url':'/work/delivery?'+urlencode({
        'project':project,'request':json.dumps(payload,separators=(',',':'))})},
        'intent_projection':{'excluded_fields':['project'] if binding else ['project','expected_run_revision'],
            'algorithm':'sha256-canonical-json-utf8'}}


def request_status(root, project, payload, *, binding=False,read_context=None):
    W,D=_owners();task=D._read_tasks(root,project,read_context).get(payload['work_id'])
    if not task:raise ValueError('Select the original Work of this request.')
    if binding:
        matches=[r for r in D._rows(task,D.BINDING) if (r.get('approval') or {}).get('schema_version')=='laplace.effect-approval/1'
                 and r['approval'].get('request_id')==payload['request_id']]
    else:matches=[r for r in _phase_rows(task) if r.get('request_id')==payload['request_id']]
    result={'project':project,'work_id':task['id'],'request_id':payload['request_id'],
        'read':request_handle(project,task['id'],payload['request_id'],binding=binding)}
    if task.get('prepared_workflow'):
        from laplace.writing import workflow_dispatch
        try:
            _plan,pin,_artifact=_checked_plan(root,project,task,read_context)
            if pin.get('research_workflow'):result['run_read']=read_handle(project,task['id'])
        except (ValueError,OSError,KeyError):pass  # request custody remains independently inspectable
    if len(matches)>1:return {**result,'effect':'UNKNOWN','reason':'Ambiguous original request custody; retain exact wire.'}
    if matches:
        row=matches[0]
        return {**result,'effect':'RECORDED','receipt':{'request_id':payload['request_id'],
            'intent_sha256':(row.get('approval') or {}).get('intent_sha256',row.get('intent_sha256')),
            **({'binding':D._public_binding(row)} if binding else {'phase_id':row['id'],'action':row['action'],'run':copy.deepcopy(row['run'])})}}
    return {**result,'effect':'NONE','meaning':'No retained request at this cut; only explicit exact-wire retry is permitted. NONE is not a no-effect settlement.'}


def approve_effect(root, project, payload, door):
    W,D=_owners()
    if door.get('origin')!='human':raise ValueError('Effect approvals require the actual human author door.')
    if payload.get('kind')!='app-owned':raise ValueError('Effect approvals require the actual app-owned admission adapter.')
    if payload.get('effect') not in EFFECTS:raise ValueError('Select one supported effect.')
    request=payload.get('request_id')
    if not isinstance(request,str) or not 8<=len(request)<=96:raise ValueError('Retain the exact approval request_id.')
    lifetime=payload.get('lifetime_s',D.DEFAULT_BINDING_LIFETIME_S)
    if type(lifetime) is not int or not 60<=lifetime<=D.MAX_BINDING_LIFETIME_S:raise ValueError('Unsupported effect approval lifetime.')
    intent={k:copy.deepcopy(v) for k,v in payload.items() if k!='project'}
    with W.dispatch_lock(root):
        task=D._task_for(root,project,payload['work_id'])[1]
        prior=[r for r in D._rows(task,D.BINDING) if (r.get('approval') or {}).get('request_id')==request]
        if prior:
            if len(prior)!=1 or prior[0]['approval'].get('intent_sha256')!=canonical_digest(intent):raise ValueError('Effect approval request has different or ambiguous intent.')
            return _approved_result(project,task,prior[0],replayed=True)
        if payload.get('expected_work_revision')!=W._task_revision(task):raise W.WorkConflict('Inspect Work before approving its effect.',project,task['id'])
        content=D.binding_content(task['id'],{'kind':'app-owned',**payload})
        if payload['effect']!='research-producer':
            choice=W.session_choice(project,{k:payload.get(k) for k in ('provider','model','effort')},root,
                role='worker' if payload['effect']=='proposal-writer' else 'judge')
            content.update({k:choice[k] for k in ('provider','model','effort')})
        else:
            from laplace.research import research_context,research_runs,research_observation
            _item,home=research_context.project(project,Path(root));producer,problem=research_runs._producer(home,payload.get('producer_id')) if home else (None,'Research owner unavailable')
            if problem:raise ValueError(problem)
            _args,problem=research_runs._checked_args(producer,payload.get('producer_args') or {},payload.get('producer_mode'))
            if problem:raise ValueError(problem)
            argument=payload.get('feedback_argument')
            if argument is not None and (producer.get('allowed_args') or {}).get(argument)!='str':
                raise ValueError('An author comment may fill only an explicitly approved registered string argument.')
            content['producer_basis']=research_observation._object_digest(producer)
            ceiling=producer.get('timeout_seconds',900)
            if type(ceiling) is not int or not 1<=ceiling<=3600:raise ValueError('Registered producer has no supported finite running ceiling.')
            content['producer_timeout_seconds']=ceiling
        ident='RB-'+D._digest(content)[7:31];old=D._latest(task,D.BINDING,ident)
        if old and payload.get('expected_binding_revision')!=old['revision']:
            raise W.WorkConflict('Inspect the current effect approval before renewing it.',project,task['id'])
        if not old and payload.get('expected_binding_revision') is not None:raise ValueError('Initial approval has no previous binding revision.')
        meta={'schema_version':'laplace.effect-approval/1','request_id':request,'intent_sha256':canonical_digest(intent),
              'intent':intent,'lifetime_s':lifetime}
        expiry=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=lifetime)).isoformat()
        revision=D._digest(content) if not old else D._digest({'previous_revision':old['revision'],'approval':meta,'expires_at':expiry})
        row={'record':D.RECORD,'kind':D.BINDING,'id':ident,'project':project,'state':'APPROVED','revision':revision,
            **content,'approval':meta,'approved_by':'human','expires_at':expiry,'ts':_now(),
            'previous_revision':old['revision'] if old else None,'approval_generation':(old or {}).get('approval_generation',0)+1,
            'actor':{'actor':'author','origin':'human','role':'approval'},'attachment':'Explicit '+payload['effect']+' effect through existing admission'}
        try:W._append(root,row)
        except Exception:
            found=request_status(root,project,{'work_id':task['id'],'request_id':request},binding=True)
            if found['effect']!='RECORDED':raise
            row=found['receipt']['binding']
            return _approved_result(project,task,row,replayed=True)
    return _approved_result(project,task,row,replayed=False)


def _approved_result(project,task,row,*,replayed):
    """An exact publisher/replay receipt; old approvals are not current grants."""
    _,D=_owners();binding=D._public_binding(row);request=row['approval']['request_id']
    read=request_handle(project,task['id'],request,binding=True)
    receipt={'project':project,'work_id':task['id'],'request_id':request,'effect':'RECORDED','read':read,
        'receipt':{'request_id':request,'intent_sha256':row['approval']['intent_sha256'],'binding':copy.deepcopy(binding)}}
    if task.get('prepared_workflow'):receipt['run_read']=read_handle(project,task['id'])
    return {'effect':'approved','binding':binding,'replayed':replayed,'request_read':read,'request_receipt':receipt,
        'observation':'ORIGINAL_APPROVAL_RECEIPT' if replayed else 'AT_APPROVAL_PUBLICATION',
        'meaning':'Approval acknowledgement is exact to this request; captured approval never replaces current admission checks.'}


def view(root, project, work_id, *, door=None,read_context=None):
    context={} if read_context is None else read_context
    task, plan, pin, artifact, state = _load(root,project,work_id,read_context=context)
    W, D = _owners(); revision = _revision(task, pin)
    human=(door or {}).get('origin')=='human'
    author=False
    if (door or {}).get('origin')=='native':
        try:
            actor=_admit_actor(root,project,door)
            author=actor.get('session_id')==pin['prepared_by']['session_id']
        except (ValueError,KeyError):pass
    attempts = []
    for attempt in state['attempts']:
        history = D._history(task, attempt['event_id'])
        if history:
            attempts.append(event_view(root, project, task, history[0], history[-1],read_context=context))
    choices = {effect: [D._public_binding(r) for r in D.latest_bindings(task).values()
        if r.get('effect') == effect] for effect in EFFECTS}
    actions = {name.removeprefix('workflow-'): _action(project, work_id, name, revision)
        for name in ACTIONS if name not in READS and name!='workflow-bind'}
    actions['start']['required_inputs'] += ['recipients']
    actions['start']['fields']=[{'name':'recipients.'+name,'label':'Proposal writer' if name=='writer' else 'Independent evidence reviewer',
        'type':'select','required':True,'choices':[{'value':r['id'],'label':r.get('label') or (
            ('Proposal writer' if name=='writer' else 'Independent reviewer')+' · '+str(r.get('provider'))+' / '+str(r.get('model')))} for r in choices[effect]
        if r['state']=='APPROVED' and not D._binding_problem(task,r['id'])]} for name,effect in [('writer','proposal-writer'),('reviewer','independent-review')]]
    spec=pin['research_workflow'];pairs=research_pairs_of(spec);binds=[(name,effect,pairs[0][name],'bind_'+name) for name,effect in ROLE_EFFECT.items()]
    # More than one pair: a step whose settings differ from the first pair's needs its own approval.
    binds+=[(name,effect,pair[name],'bind_'+pair[name]) for pair in pairs[1:] for name,effect in ROLE_EFFECT.items()
        if pin['settings'][pair[name]]['values']!=pin['settings'][pairs[0][name]]['values']]
    for name,effect,step,key in binds:
        values=pin['settings'][step]['values'];request='approve-'+uuid.uuid4().hex
        binding_payload={'action':'workflow-bind','work_id':work_id,'effect':effect,'kind':'app-owned',
            'expected_work_revision':W._task_revision(task),'request_id':request,
            **{k:v for k,v in values.items() if k in ('provider','model','effort') and v is not None},
            'label':name,'lifetime_s':D.DEFAULT_BINDING_LIFETIME_S}
        actions[key]={'available':True,'permitted':True,'reason':'Explicit human approval; no delivery starts.',
            'title':'Approve proposal writer' if name=='writer' else 'Approve independent reviewer',
            'read':read_handle(project,work_id),'run_read':read_handle(project,work_id),
            'http':{'method':'POST','url':'/work/delivery','payload':{'project':project,**binding_payload}},
            'fields':[{'name':'label','label':'Reviewer name' if name=='reviewer' else 'Writer name','type':'text','required':False},
                      {'name':'lifetime_s','label':'Approval duration (seconds)','type':'number','required':True,'minimum':60,'maximum':D.MAX_BINDING_LIFETIME_S}],
            'request_read':request_handle(project,work_id,request,binding=True)}
    for name,action in actions.items():
        if 'native' in action:
            request='workflow-'+uuid.uuid4().hex
            action['native']['payload']['request_id']=request;action['http']['payload']['request_id']=request
            action['request_read']=request_handle(project,work_id,request)
    actions['replan']['fields']=[{'name':'reference','label':'Exact saved replacement definition','type':'reference','required':True},
        {'name':'inputs','label':'Explicitly inspected replacement inputs','type':'inputs','required':False}]
    actions['readdress']['fields']=[{'name':'recipient','label':'Recipient role','type':'select','required':True,'choices':_recipient_names(pin)},
        {'name':'recipient_binding_id','label':'Exact approved recipient','type':'binding','required':True}]
    for name in ('replan','readdress'):
        intervention={'action':'workflow-'+name}
        if name=='replan':intervention['reference']=copy.deepcopy(state['plan_reference'])
        actions[name]['preview_read']={'title':'Preview replacement plan' if name=='replan' else 'Preview future recipient change',
            'http':{'method':'GET','url':'/work/delivery?'+urlencode({'project':project})},'query_field':'request',
            'request':{'action':'workflow-impact-preview','work_id':work_id,'expected_run_revision':revision,
                'expected_work_revision':W._task_revision(task),'expected_plan_generation':state['plan_generation'],'intervention':intervention},
            'fields':[{**copy.deepcopy(field),'name':'intervention.'+field['name']} for field in actions[name]['fields']],
            'meaning':'Pure prospective scope only. Confirmation is a separate exact owner-issued effect and revalidates its observed bases.'}
        if name=='readdress':
            field=actions[name]['preview_read']['fields'][1];field['recipient_field']='intervention.recipient';field['choices']=[]
            for role in _recipient_names(pin):
                kind=role if role in ROLE_EFFECT else next(n for pair in pairs for n in ROLE_EFFECT if pair[n]==role);effect=ROLE_EFFECT[kind]
                for row in choices[effect]:
                    try:_check_recipients(root,project,task,pin,{role:row['id']},only=role);binding=_binding(root,project,task,row['id'],effect,
                        pin['settings'][pairs[0][kind] if role in ROLE_EFFECT else role]['values'])
                    except ValueError:continue
                    field['choices'].append({'value':binding['id'],'label':binding.get('label') or effect.replace('-',' '),
                        'recipient':role,'basis':binding['revision']})
    actions['disposition'].update(available=False,permitted=False,
        reason='Inspect an actual recorded scientific concern; its owner supplies the exact subject and concern basis.')
    actions.update(_concern_actions(root,project,work_id,revision,pin))
    for key,action in actions.items():
        if key.startswith('bind_') or key=='accept-boundary' or key.startswith('disposition_'):
            action['permitted']=bool(action.get('permitted') and human)
        elif key!='start':action['permitted']=bool(action.get('permitted') and (human or author))
        if not action.get('permitted') and not action.get('reason'):
            action['reason']='Use the exact original admitted author or explicit human action; reading grants no mutation authority.'
    from laplace.pipeline import workflow_operations as operations
    owned=[a['event_id'] for a in attempts if a.get('state') not in SETTLED]
    if not author:
        actions['synthesis'].update(permitted=False,reason='Only a current admitted turn of the original parent session publishes its authored synthesis.')
    gates={
        'recover':state['state']!='PREPARED',
        'stop-before-next':state['state'] in {'RUNNING','AWAITING_ADVANCE','PARTIAL'},
        'stop-run':state['state'] in {'RUNNING','AWAITING_ADVANCE','PARTIAL'} or (state['state']=='STOP_BEFORE_NEXT' and bool(owned)),
        'synthesis':bool(pin.get('synthesis')) and not state.get('synthesis') and state['state'] in operations.SYNTHESIS_DUE and not owned,
        'resume':state['state'] in {'STOP_BEFORE_NEXT','AWAITING_ADVANCE','PARTIAL'} and _resumable(state,pin)
            and not state.get('admission_refused_event_id')
            and not state.get('synthesis'),
        'accept-boundary':state['state']=='AWAITING_HUMAN_APPLY',
        'replan':all(r.get('state') in {'RESULT','STALE','UNCONFIRMED'} for r in attempts)}
    for key,ready in gates.items():
        if not ready:actions[key].update(permitted=False,reason='This action is not available at the observed phase; inspect the retained run.')
    for carrier in ('native','http'):actions['stop-run'][carrier]['payload']['children']=list(owned)
    actions['stop-run']['coverage']={'owned_children':list(owned),'complete':True,
        'meaning':'Exact current owned children of this run. The owner refuses a changed set, gates future admission first and controls each child through its own turn or producer owner.'}
    actions['synthesis']['required_inputs']=['request_id','synthesis','consumed']
    if state['state'] != 'PREPARED':
        actions['start'].update(permitted=False, reason='This exact run already has an original launch; recover it.')
    # Human Start prepares the existing composer; only an admitted original
    # parent can execute the exact native start. This POST itself is a pure read.
    actions['start']['title']='Prepare start message'
    actions['start']['http']['payload']['action']='workflow-compose-start'
    actions['start']['http']['payload'].pop('expected_run_revision',None)
    multi=bool(spec.get('pairs'));lanes=_lanes(state,spec)
    for pair,lane in lanes:
        if not lane.get('proposal'):continue
        from laplace.writing import records
        from laplace.manuscript import source_effects,manuscript_proposals
        turn=D._read_fold(root,context)['turns'].get(lane['proposal']['turn_id']) or {}
        version=lane['proposal']['proposal_version']
        candidate=(turn.get('proposal_versions') or {}).get(version) or {}
        ids={manuscript_proposals.edit_id(e) for e in candidate.get('edits') or []}
        covered=set().union(*(set(a.get('candidate_edit_ids') or []) for a in source_effects.applications(turn)
            if a.get('complete') and a.get('candidate_version')==version))
        if ids and ids<=covered:lane['applied' if multi else 'state']='APPLIED'
        permitted=human and state['state']=='AWAITING_HUMAN_APPLY' and bool(state.get('human_boundary')) and not lane.get('applied')
        # Each pair's reviewed proposal is its own separate human Apply.
        actions['human_apply' if not multi else 'human_apply_'+pair['writer']]={'available':True,'permitted':permitted,
            'reason':'' if permitted else 'Explicitly accept the human boundary after independent review; inspect the exact current proposal.',
            'title':'Apply reviewed manuscript proposal','http':{'method':'POST','url':'/authoring/apply','payload':{
                'project':project,'turn_id':lane['proposal']['turn_id'],'proposal_version':version}},
            'read':lane['proposal']['read'],'meaning':'Existing manuscript owner revalidates all source/consumed guards. This is a separate human effect.'}
    from laplace.work.project_work_views import handle as work_read
    return {'schema_version': SCHEMA, 'work': {'id': work_id, 'project': project,'title':task['title'],'revision':W._task_revision(task),
        'read': work_read(project,{'view':'detail','id':work_id})},
        'reference': state['plan_reference'], 'plan_generation':state['plan_generation'], 'plan_artifact':artifact,
        'revision': revision, 'state': state['state'],
        # More than one pair: the run's round is the furthest pair's; each pair's own round is in pairs.
        'policy': state['policy'], 'iteration': state['iteration'] if not multi else max(lane.get('iteration') or 1 for _, lane in lanes), 'next': state.get('next'),
        **({'pairs': [{'writer': pair['writer'], 'reviewer': pair['reviewer'], 'obligation_id': obligation_id(spec, pair['writer']),
            **{k: copy.deepcopy(lane.get(k)) for k in ('next', 'iteration', 'exit', 'applied', 'reason', 'proposal', 'judgement', 'loop_decision', 'loop_exit')}}
            for pair, lane in lanes]} if multi else {}),
        'prepared_dependencies': {'status': 'AVAILABLE', 'source': 'workflow_progression.research_workflow',
            'edges': [{'prerequisite_step_id': pair['writer'], 'dependent_step_id': pair['reviewer']} for pair, _ in lanes]},
        'input_packet': pin['research_workflow']['input_packet'], 'manuscript_basis':copy.deepcopy(pin['research_workflow'].get('manuscript_basis')), 'attempts': attempts,
        'plan_history': copy.deepcopy(state.get('plan_history', [])), 'launched_by':copy.deepcopy(state.get('launched_by')),
        'interventions': copy.deepcopy(state.get('interventions', [])),
        'proposal': copy.deepcopy(state.get('proposal')), 'judgement': copy.deepcopy(state.get('judgement')),
        'human_boundary':copy.deepcopy(state.get('human_boundary')),
        'synthesis':_synthesis_section(state,plan,pin,artifact,gates['synthesis'],owned),
        'stop_request':copy.deepcopy(state.get('stop_request')),'loop_exit':copy.deepcopy(state.get('loop_exit')),
        'loop_decision':copy.deepcopy(state.get('loop_decision')),
        'recipient_choices': choices, 'settings': copy.deepcopy(pin['settings']), 'actions': actions,
        'read': read_handle(project, work_id), 'application_boundary': 'Separate human manuscript Apply; no development Source authority'}


def _concern_actions(root,project,work_id,revision,pin):
    """Current canonical concerns only; Work never manufactures clearance truth."""
    from laplace.research import object_context
    result={}
    for entry in pin['research_workflow']['input_packet']['consumed_bases']:
        ref=entry['reference']
        if ref.get('owner')!='domain.research' or ref.get('kind')!='concept':continue
        try:current=object_context.read(root,project,ref)
        except (ValueError,OSError,KeyError):continue
        for concern in current.get('concerns') or []:
            if concern.get('state')!='OPEN':continue
            pointer=object_context.concern_reference(project,ref['identity']['node'],concern['id'])
            request='workflow-'+uuid.uuid4().hex
            action=_action(project,work_id,'workflow-disposition',revision,extra={
                'subject':ref,'expected_basis':current['basis'],'concern_id':concern['id'],
                'expected_concern_basis':canonical_digest(concern),'request_id':request})
            action.update(title='Record scientific disposition',concern={'reference':pointer,'basis':canonical_digest(concern)},
                fields=[{'name':'disposition','label':'Disposition','type':'select','required':True,
                    'choices':['ACCEPT','REVISE','WITHDRAW'] if concern['change_kind']=='assumption' else ['ACCEPT','REVISE','WITHDRAW','UNCHANGED']},
                    {'name':'summary','label':'Reason and remaining uncertainty','type':'textarea','required':True}],
                request_read=request_handle(project,work_id,request))
            result['disposition_'+canonical_digest(pointer)[7:23]]=action
    return result


def _admit_actor(root, project, door, *, human=False):
    _, D = _owners(); acting = D._acting(root, project, door)
    if human:
        if acting['kind'] != 'human':raise ValueError('This disposition is an explicit human action.')
    elif acting.get('role') == 'review':
        raise ValueError('An independent reviewer cannot launch or control another recipient.')
    if acting['kind'] == 'native':
        from laplace.writing import turn_admission, source_execution, records
        row = turn_admission.native_write_admission(root, project,
            records.fold_records(root)['turns'][acting['turn_id']]['mode'], acting['turn_id'])
        if not row['permitted']:raise ValueError('Workflow intervention requires current admitted author authority.')
        if source_execution.for_turn(root, project, acting['turn_id']):
            raise ValueError('An opted-in development Source commission cannot launch an ordinary research workflow.')
    return acting


def action_input(value):
    from laplace.core import identity
    import re
    fields={'project','work_id','request_id','parent_session_id','writer_binding_id','reviewer_binding_id'}
    if not isinstance(value,dict) or set(value)!={'reference','expected_basis'}:
        raise ValueError('Research workflow action requires exact reference and expected_basis.')
    reference=value['reference']
    if (identity.reference_problems(reference) or reference.get('owner')!='pipeline.workflow'
            or set(reference)!={'schema_version','owner','kind','identity','version'}
            or reference.get('kind')!='research-workflow-start' or set(reference.get('identity') or {})!=fields
            or any(not isinstance(item,str) or not 1<=len(item)<=160 for item in reference['identity'].values())
            or set(reference.get('version') or {})!={'definition_revision'}
            or not isinstance(reference['version']['definition_revision'],str)
            or not re.fullmatch(r'sha256:[0-9a-f]{64}',reference['version']['definition_revision'])
            or not isinstance(value['expected_basis'],str) or not re.fullmatch(r'sha256:[0-9a-f]{64}',value['expected_basis'])):
        raise ValueError('Research workflow Start reference is malformed.')
    return copy.deepcopy(value)


def compose_start(root, project, payload):
    from laplace.core import identity
    from laplace.writing import workflow_dispatch
    W,_=_owners();task,_plan,pin,_artifact,state=_load(root,project,payload['work_id'])
    if state['state']!='PREPARED':raise ValueError('This run already has a launch; inspect its actual recovery route.')
    _packet(root,project,pin,revalidate=True)
    request=payload.get('request_id');selected=payload.get('recipients') or {}
    if not isinstance(selected,dict) or set(selected)!={'writer','reviewer'}:raise ValueError('Select exact writer and reviewer binding identities.')
    if not isinstance(request,str) or not 8<=len(request)<=96:raise ValueError('Retain the exact Start submission request_id.')
    # The selected Start carries one writer and one reviewer approval; with more pairs they serve every pair whose settings they match.
    _check_recipients(root,project,task,pin,selected)
    target=W.read(project,{'view':'detail','id':task['id']},root)['task']
    native={'operation':'work_delivery','payload':{'action':'workflow-start','work_id':task['id'],
        'request_id':request,'expected_run_revision':_revision(task,pin),'recipients':copy.deepcopy(selected)}}
    reference=identity.reference('pipeline.workflow','research-workflow-start',{'project':project,'work_id':task['id'],
        'request_id':request,'parent_session_id':pin['prepared_by']['session_id'],
        'writer_binding_id':selected['writer'],'reviewer_binding_id':selected['reviewer']},
        version=pin['reference']['version'])
    basis=canonical_digest({'native':native,'work_scope':target['work_scope_revision'],
        'dependency':target['dependency_revision'],'reference':pin['reference']})
    exact={'action':'workflow-compose-start','work_id':task['id'],'request_id':request,'recipients':copy.deepcopy(selected)}
    def action_read(value):
        return {'native':{'operation':'work_delivery','payload':value},'request':copy.deepcopy(value),
            'http':{'method':'GET','url':'/work/delivery?'+urlencode({'project':project,'request':json.dumps(value,separators=(',',':'))})}}
    if payload.get('expected_action_basis',basis)!=basis:
        from laplace.pipeline.workflow_definitions import Refused
        raise Refused('ACTION_CONTEXT_CHANGED','Inspect the exact current Start before selecting a new action.',next_reads=[action_read(exact)])
    read=action_read({**exact,'expected_action_basis':basis})
    leaf={'reference':reference,'expected_basis':basis}
    snapshot={'schema_version':workflow_dispatch.ACTION_CONTEXT_SCHEMA,**leaf,'native':native,
        'summary':{'workflow_title':task['title'],'work_id':task['id'],'input_policy':'evidence-packet',
            'application_boundary':'human','policy':state['policy']},'read':read}
    turn={'project':project,'session_id':pin['prepared_by']['session_id'],'mode':'work',
        'text':'Start this configured proposal and independent evidence review. Keep every result; stop at the human manuscript Apply boundary.',
        'work_id':task['id'],'expected_work_scope_revision':target['work_scope_revision'],
        'expected_dependency_revision':target['dependency_revision'],
        'workspace_context':{'surface':'project','workflow_action':leaf}}
    action={'available':True,'permitted':True,'send_required':True,'label':'Prepare start message','project':project,
        'requires_role':'original-author-parent','payload':turn,'http':{'method':'POST','route':'/authoring/turn'},
        'action_context':snapshot,'work_target':{'id':task['id'],'work_scope_revision':target['work_scope_revision'],
            'dependency_revision':target['dependency_revision']},
        'project_url':'/project?'+urlencode({'workspace':'writing','corpus':project,'session':pin['prepared_by']['session_id']}),
        'read':read}
    return {'action':action,'compose_action':action,'native_start':native,'read':read,'run_read':read_handle(project,task['id'])}


def resolve_action_context(root, project, value, *, session_id, mode, work_id, work_guards):
    value=action_input(value);ref=value['reference'];ident=ref['identity']
    if project!=ident['project'] or session_id!=ident['parent_session_id'] or work_id!=ident['work_id'] or mode!='work':
        raise ValueError('Selected research Start requires its exact project, original author session and Work.')
    current=compose_start(root,project,{'work_id':work_id,'request_id':ident['request_id'],
        'recipients':{'writer':ident['writer_binding_id'],'reviewer':ident['reviewer_binding_id']}})['action']
    snapshot=current['action_context'];target=current['work_target']
    if snapshot['reference']!=ref or snapshot['expected_basis']!=value['expected_basis']:
        raise ValueError('ACTION_CONTEXT_CHANGED: inspect the current Start and retain the unsent request.')
    if any(work_guards.get(k)!=target[field] for k,field in [('expected_work_scope_revision','work_scope_revision'),('expected_dependency_revision','dependency_revision')]):
        raise ValueError('ACTION_WORK_BASIS_CHANGED: inspect this exact workflow Work before Start.')
    return snapshot


def handle(root, project, payload, door):
    W, D = _owners(); work_id = payload['work_id']; action = payload['action']
    base={'project','action','work_id'}
    extras={
        'workflow-bind':{'request_id','expected_work_revision','kind','effect','provider','model','effort','label','lifetime_s',
            'expected_binding_revision','producer_id','producer_mode','producer_args','feedback_argument'},
        'workflow-compose-start':{'request_id','recipients','expected_action_basis'},
        'workflow-bind-request':{'request_id'},'workflow-request':{'request_id'},
        'workflow-impact-preview':{'expected_work_revision','expected_run_revision','expected_plan_generation','intervention'},
        'workflow-preview':set(),'workflow-status':set(),
        'workflow-start':{'recipients'},'workflow-stop-run':{'children'},'workflow-synthesis':{'synthesis','consumed'},'workflow-replan':{'reference','inputs','selection','expected_work_revision','expected_plan_generation','expected_impact_basis'},
        'workflow-readdress':{'recipient','recipient_binding_id','expected_work_revision','expected_plan_generation','expected_impact_basis'},
        'workflow-disposition':{'subject','expected_basis','expected_concern_basis','concern_id','changed','change_kind','disposition','summary','evidence'}}
    allowed=base|extras.get(action,set())|(set() if action in READS or action=='workflow-bind' else {'request_id','expected_run_revision'})
    if set(payload)-allowed:raise ValueError('This workflow action contains unconsumed fields; no requested policy or ceiling was silently dropped.')
    if action=='workflow-bind':return approve_effect(root,project,payload,door)
    if action in ('workflow-bind-request','workflow-request'):
        return request_status(root,project,payload,binding=action=='workflow-bind-request')
    if action=='workflow-compose-start':return compose_start(root,project,payload)
    if action=='workflow-impact-preview':return impact_preview(root,project,{k:v for k,v in payload.items() if k!='project'},door=door)
    if action in READS:return view(root, project, work_id,door=door)
    if not isinstance(payload.get('request_id'), str) or not 8 <= len(payload['request_id']) <= 96:
        raise ValueError('Workflow mutations retain one stable 8–96 character request_id.')
    acting = _admit_actor(root, project, door, human=action == 'workflow-accept-boundary')
    with W.dispatch_lock(root):
        task, plan, pin, artifact, state = _load(root, project, work_id)
        if acting['kind'] == 'native' and acting['session_id'] != pin['prepared_by']['session_id']:
            raise ValueError('Workflow control requires the original author session or explicit human action.')
        intent = {k: copy.deepcopy(v) for k, v in payload.items() if k not in {'expected_run_revision','project'}}
        prior = next((r for r in _phase_rows(task) if r.get('request_id') == payload['request_id']), None)
        if prior:
            if prior['intent_sha256'] != canonical_digest(intent):raise ValueError('Workflow request intent changed.')
        else:
            if action != 'workflow-recover' and payload.get('expected_run_revision') != _revision(task, pin):
                raise W.WorkConflict('Workflow changed; inspect before the next action.', project, work_id)
            if payload.get('expected_plan_generation') is not None and payload['expected_plan_generation']!=state['plan_generation']:
                raise W.WorkConflict('The selected plan generation changed; inspect before confirming.',project,work_id)
            if payload.get('expected_work_revision') is not None and payload['expected_work_revision']!=W._task_revision(task):
                raise W.WorkConflict('The previewed Work specification changed; inspect before confirming.',project,work_id)
            if payload.get('expected_impact_basis') is not None:
                intervention={k:copy.deepcopy(payload[k]) for k in ('reference','inputs','selection') if k in payload} if action=='workflow-replan' else {
                    k:copy.deepcopy(payload[k]) for k in ('recipient','recipient_binding_id') if k in payload}
                impact=_impact_observation(root,project,{'action':'workflow-impact-preview','work_id':work_id,
                    'expected_work_revision':payload.get('expected_work_revision'),
                    'expected_run_revision':payload['expected_run_revision'],
                    'expected_plan_generation':payload.get('expected_plan_generation'),'intervention':{'action':action,**intervention}})
                if impact['state']!='READY' or impact['impact_basis']!=payload['expected_impact_basis']:
                    raise W.WorkConflict('The previewed intervention basis changed; inspect before confirming.',project,work_id)
            if action == 'workflow-start':
                if state['state'] != 'PREPARED' or acting['kind'] != 'native' or acting['session_id'] != pin['prepared_by']['session_id']:
                    raise ValueError('Start requires a fresh admitted turn in the original prepared author session.')
                selected = payload.get('recipients') or {}
                _check_recipients(root, project, task, pin, selected)
                from laplace.pipeline import workflow_operations as operations
                problem = operations.bridge_problem(pin, plan)
                if problem:raise ValueError('V2_BRIDGE_INCOMPLETE: ' + problem)
                _packet(root, project, pin, revalidate=True)
                state.update(state='RUNNING', recipients=copy.deepcopy(selected), launched_by=copy.deepcopy(acting))
            elif action == 'workflow-stop-before-next':
                if state['state'] not in {'RUNNING','AWAITING_ADVANCE','PARTIAL'}:raise ValueError('No pending admitted phase to stop before next.')
                state['state'] = 'STOP_BEFORE_NEXT'
            elif action == 'workflow-resume':
                if state['state'] not in {'STOP_BEFORE_NEXT', 'AWAITING_ADVANCE', 'PARTIAL'}:
                    raise ValueError('Only a retained pending phase may explicitly resume.')
                if not _resumable(state, pin):
                    raise ValueError('No executable pending phase remains; inspect and explicitly replan.')
                if state.get('admission_refused_event_id'):raise ValueError('Inspect and explicitly replan after the known admission refusal.')
                if state.get('synthesis'):raise ValueError('SYNTHESIS_ALREADY_PUBLISHED: this run is closed by its original-parent synthesis.')
                from laplace.pipeline import workflow_operations as operations
                problem = operations.bridge_problem(pin, plan)
                if problem:raise ValueError('V2_BRIDGE_INCOMPLETE: ' + problem)
                _packet(root, project, pin, revalidate=True);state['state'] = 'RUNNING'
            elif action == 'workflow-accept-boundary':
                if state['state'] != 'AWAITING_HUMAN_APPLY':raise ValueError('Independent review has not reached the human Apply boundary.')
                state['human_boundary'] = {'actor': 'author', 'request_id': payload['request_id'], 'accepted_at': _now()}
            elif action == 'workflow-readdress':
                name = payload.get('recipient')
                if name not in _recipient_names(pin):raise ValueError('Choose the writer or reviewer recipient.')
                _check_recipients(root, project, task, pin, {**state['recipients'], name: payload.get('recipient_binding_id')}, only=name)
                state['recipients'][name] = payload['recipient_binding_id']
            elif action == 'workflow-replan':
                state = _replan(root, project, task, pin, state, payload, acting)
            elif action == 'workflow-disposition':
                state = _disposition(root, project, state, payload, acting)
            elif action == 'workflow-stop-run':
                owned = [a['event_id'] for a in state['attempts'] if ((D._history(task, a['event_id']) or [{}])[-1]).get('state') not in SETTLED]
                asked = payload.get('children')
                if not isinstance(asked, list) or len(set(asked)) != len(asked) or set(asked) != set(owned):
                    raise W.WorkConflict('STOP_CHILD_COVERAGE_MISMATCH: name exactly the current owned children ' + json.dumps(owned) + '; inspect the run again.', project, work_id)
                if state['state'] not in {'RUNNING', 'AWAITING_ADVANCE', 'PARTIAL', 'STOP_BEFORE_NEXT'}:
                    raise ValueError('No running or gated phase remains to stop.')
                if state['state'] == 'STOP_BEFORE_NEXT' and not owned:
                    raise ValueError('Future admission is already gated and no owned child remains.')
                state['state'] = 'STOP_BEFORE_NEXT'
                state['stop_request'] = {'request_id': payload['request_id'], 'children': list(owned), 'requested_at': _now(),
                    'actor': {k: acting.get(k) for k in ('kind', 'turn_id', 'session_id')}}
            elif action == 'workflow-synthesis':
                from laplace.pipeline import workflow_operations as operations
                original, _plan_pin, _plan_artifact = _checked_plan(root, project, task)
                document = operations.synthesis_publication(root, project, task, original, pin, artifact, state,
                    lambda ident: D._history(task, ident), payload, acting)
                # A byte-identical retry from a later genuine turn of the original parent session
                # completes the first durable publication exactly, keeping its original provenance.
                document = _retained_synthesis(root, project, original['synthesis_return_path'], payload['request_id'],
                    pin['prepared_by'], document)
                meta = {'schema_version': 'laplace.workflow-app-preparation/1', 'request_id': payload['request_id'],
                    'intent_digest': canonical_digest(document), 'prepared_by': pin['prepared_by'], 'publication_kind': 'research-synthesis'}
                from laplace.writing import dispatch_parent
                # Exactly the bytes _artifact_once will store; the reserved path accepts nothing else.
                text = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                with dispatch_parent.research_publication(task['id'], text):
                    saved = _artifact_once(root, project, original['synthesis_return_path'], document, meta, turn_id=acting.get('turn_id'))
                published_by = (document.get('execution') or {}).get('turn_id')
                state['synthesis'] = {'artifact': {k: saved[k] for k in ('id', 'path', 'artifact_path', 'sha256', 'read')},
                    'request_id': payload['request_id'], 'turn_id': published_by, 'status': document['status'],
                    'inputs': len(document['inputs']), 'findings': len(document['findings']), 'published_at': _now(),
                    **({'recovered_by_turn_id': acting.get('turn_id')} if published_by != acting.get('turn_id') else {})}
            elif action != 'workflow-recover':raise ValueError('Unsupported workflow action.')
            _append(root, project, task, payload['request_id'], action, state, intent)
    if action in ('workflow-start', 'workflow-resume', 'workflow-recover'):
        advance(root, project, work_id)
    stop = _stop_children(root, project, work_id, payload['request_id']) if action == 'workflow-stop-run' else None
    response_context={}
    result=view(root,project,work_id,door=door,read_context=response_context)
    exact=request_status(root,project,{'work_id':work_id,'request_id':payload['request_id']},read_context=response_context)
    return {**result,**({'stop':stop} if stop is not None else {}),'request_receipt':exact,'detail_read':exact['read']['native'],
        'current_projection':{'schema_version':'laplace.current-projection/1','kind':'workflow-run',
            'project':project,'work_id':work_id,'basis':result['revision'],'plan_generation':result['plan_generation'],
            'location':'response-root','observation':'AT_OWNER_RESPONSE'},
        'receipt_projection':'Original decision receipt (including receipt.run) is historical; response-root is the current owner observation.'}


def _disposition(root, project, state, payload, acting):
    from laplace.research import object_context
    def admit(change, current):
        return {'actor': copy.deepcopy(acting), 'authority': 'existing admitted author or explicit human',
                'kind': 'judgement' if acting['kind'] == 'human' else 'revalidation'}
    change = {'reference': payload['subject'], 'expected_basis': payload['expected_basis'],
        'request_id': payload['request_id'], 'concern_id': payload['concern_id'], 'summary':payload.get('summary','')}
    if payload.get('disposition'):
        change.update(operation='clear-reconsideration', disposition=payload['disposition'], evidence=payload.get('evidence',[]),
                      expected_concern_basis=payload['expected_concern_basis'])
    else:
        change.update(operation='mark-reconsideration', changed=payload['changed'], change_kind=payload['change_kind'])
    value = object_context.change(root, project, change, admit=admit)
    # The responsible owner alone records and projects concern/clearance state.
    state['interventions'].append({'request_id': payload['request_id'], 'kind': 'disposition',
        'subject':copy.deepcopy(payload['subject']), 'concern_id':payload['concern_id'], 'receipt': value})
    return state


def _replan(root, project, task, pin, state, payload, acting):
    from laplace.pipeline import workflow_definitions as D
    from laplace.work import owner_discovery as O
    _, delivery = _owners()
    if any(delivery._history(task,a['event_id'])[-1]['state'] not in {'RESULT','STALE','UNCONFIRMED'} for a in state['attempts']):
        raise ValueError('Stop before next and let the actual current recipient settle before replanning.')
    reference = payload.get('reference')
    if not isinstance(reference,dict) or not reference.get('version'):raise ValueError('Replan selects one exact saved definition version.')
    caller = O.project_scope(project,'sdk')
    row,_,_ = D._select(D._rows(root),caller,{'reference':reference})
    body = D._body(root,row)
    if row['scope'] != {'kind':'project','namespace':project} or not body.get('run_policy'):
        raise ValueError('Replan requires a saved research-review definition in this same project.')
    spec = pin['research_workflow']
    request = {'action':'prepare','profile':D.APP_PROFILE,'reference':reference,'request_id':payload['request_id'],
        'goal':task['goal'],'fan_out_max':2*len(research_pairs_of(spec)),'step_ids':[*(pair[name] for pair in research_pairs_of(spec) for name in ROLE_EFFECT),
            *[s['id'] for s in body['steps'] if s['assignment']['role']=='synthesis']],
        'selection':payload.get('selection',spec['selection']), 'inputs':payload.get('inputs',spec['input_packet']['entries'])}
    plan,new_pin = compile_plan(root,caller,row,body,request,pin['prepared_by'])
    base = spec['input_packet']['artifact_path'].rsplit('/',1)[0]+'/replan-'+canonical_digest(payload['request_id'])[7:23]
    metadata = {'schema_version':'laplace.workflow-app-preparation/1','request_id':payload['request_id'],
        'intent_digest':canonical_digest(payload),'prepared_by':pin['prepared_by'],'publication_kind':'replan-inputs'}
    new_pin['research_workflow']['input_packet'] = capture_packet(root,project,new_pin['research_workflow'].pop('inputs'),
        base+'-inputs.json',metadata,turn_id=acting.get('turn_id'))
    saved = _artifact_once(root,project,base+'-plan.json',plan,
        {**metadata,'publication_kind':'replan'},turn_id=acting.get('turn_id'))
    state.setdefault('plan_history',[]).append({'reference':state['plan_reference'],'proposal':copy.deepcopy(state.get('proposal')),
        'judgement':copy.deepcopy(state.get('judgement')), 'attempt_event_ids':[a['event_id'] for a in state['attempts']],
        **({'pairs':copy.deepcopy(state['pairs'])} if state.get('pairs') else {})})
    state.update(plan_reference=reference,plan_artifact=saved,plan_generation=canonical_digest({'id':saved['id'],'sha256':saved['sha256']}),policy=copy.deepcopy(body['run_policy']),
        iteration=1,next='writer',state='STOP_BEFORE_NEXT')
    state.pop('pairs',None)
    if new_pin['research_workflow'].get('pairs'):
        # A replacement plan of more than one pair starts every pair again from its writer.
        for key in ('iteration','next','proposal','judgement'):state.pop(key,None)
        _lanes(state,new_pin['research_workflow'])
    state.pop('admission_refused_event_id',None)
    return state


def _stop_children(root, project, work_id, request_id):
    """The durable gate is already recorded; control each exact owned child once.

    Only each child's own turn or producer owner is used. A retried request
    re-observes the retained control receipts instead of repeating them.
    """
    W, D = _owners()
    from laplace.pipeline import workflow_operations as operations
    from laplace.writing import records
    task = W._tasks(project, root)[work_id]
    phase = next((r for r in _phase_rows(task) if r.get('request_id') == request_id), None)
    selected = list(((((phase or {}).get('run') or {}).get('stop_request')) or {}).get('children') or [])
    held = (_phase_rows(task)[-1]['run'].get('stop_controls') or {}).get(request_id)
    issued = held is None
    if issued:
        held = []
        for event_id in selected:
            latest = (D._history(task, event_id) or [{}])[-1]; control = None
            owner = 'research_runs.cancel' if latest.get('research_run_id') else 'turn_control.interrupt_turn'
            try:
                if latest.get('state') in SETTLED:
                    control = None
                elif latest.get('research_run_id'):
                    from laplace.research import research_runs
                    code, body = research_runs.cancel(project, {'id': latest['research_run_id']}, Path(root))
                    control = {'owner': owner, 'status': 'REQUESTED' if code < 400 else 'REFUSED', 'http_status': code,
                        'error': None if code < 400 else str((body or {}).get('error'))[:400]}
                elif latest.get('turn_id'):
                    from laplace.writing import turn_control
                    result = turn_control.interrupt_turn(Path(root), {'turn_id': latest['turn_id'], 'project': project})
                    control = {'owner': owner, 'status': 'REQUESTED', 'turn_ids': list(result.get('turn_ids') or []),
                        'settled': copy.deepcopy(result.get('settled'))}
            except ValueError as error:
                text = str(error)
                control = {'owner': owner, 'status': 'NO_ACTIVE_TURN' if 'no active provider turn' in text.lower() else 'REFUSED', 'error': text[:400]}
            except Exception as error:  # an owner fault is an unknown effect, never a stop
                control = {'owner': owner, 'status': 'UNKNOWN', 'error': str(error)[:400]}
            held.append({'event_id': event_id, 'turn_id': latest.get('turn_id'), 'research_run_id': latest.get('research_run_id'), 'control': control})
        with W.dispatch_lock(root):
            current = W._tasks(project, root)[work_id]; run = copy.deepcopy(_phase_rows(current)[-1]['run'])
            run.setdefault('stop_controls', {})[request_id] = held
            _append(root, project, current, 'stop-controls-' + request_id, 'stop-controls', run, {'request_id': request_id, 'controls': held})
    task = W._tasks(project, root)[work_id]; state = _phase_rows(task)[-1]['run']; fold = records.fold_records(root)
    controls = {row['event_id']: row.get('control') for row in held}; children = []
    for event_id in selected:
        latest = (D._history(task, event_id) or [{}])[-1]; turn = fold['turns'].get(latest.get('turn_id')) or {}
        reply = turn.get('reply') if isinstance(turn.get('reply'), dict) else None
        if latest.get('state') in SETTLED or reply is not None:observed = 'RESULT'
        elif latest.get('state') == 'SUBMITTED' and not latest.get('turn_id') and not latest.get('research_run_id'):observed = 'NOT_ADMITTED'
        else:observed = latest.get('state') or 'UNKNOWN'
        children.append({'event_id': event_id, 'observed_state': observed, 'recorded_state': latest.get('state'),
            'turn_id': latest.get('turn_id'), 'reply_status': (reply or {}).get('status'), 'control': copy.deepcopy(controls.get(event_id))})
    gate = {'state': state['state'], 'effective': state['state'] != 'RUNNING', 'request_id': request_id,
        'basis': 'Advance admits a next child only from RUNNING; Resume is a separate explicit author decision.'}
    return {**operations.stop_composition(gate, children), 'request_id': request_id, 'controls_issued_now': issued,
        'coverage': {'owned_children': len(selected), 'observed': len(children), 'complete': len(children) == len(selected)},
        'observed_at': _now(), 'read': read_handle(project, work_id)}


def _synthesis_section(state, plan, pin, artifact, due, owned):
    from laplace.pipeline import workflow_operations as operations
    authored = pin.get('synthesis')
    if not authored:return {'required': False}
    required = operations.synthesis_inputs(state, pin, artifact); limit = operations.DELIVERY_LIMITS['entries']
    problem = operations.bridge_problem(pin, plan) or (None if authored.get('bridge') == operations.BRIDGE else 'Prepared before the synthesis bridge; prepare again.')
    return {'required': True, 'schema_version': operations.SYNTHESIS_SCHEMA, 'bridge': authored.get('bridge'), 'bridge_problem': problem,
        'step_id': authored.get('step_id'), 'title': authored.get('title'), 'execution_location': authored.get('execution_location'),
        'session_id': authored.get('session_id'), 'admitted_settings': copy.deepcopy(authored.get('admitted_settings')),
        'declared_settings': copy.deepcopy(authored.get('declared_settings')), 'due': bool(due), 'pending_children': list(owned),
        'inputs': copy.deepcopy(required[:limit]), 'inputs_total': len(required), 'inputs_omitted': max(0, len(required) - limit),
        'published': copy.deepcopy(state.get('synthesis')), 'publish_action': 'actions.synthesis',
        'meaning': 'In the original parent session read every OWNER_READ_RECEIPT_REQUIRED input completely, then publish once with its read receipt IDs. The owner carries attempt outcomes and every finding; coverage is not acceptance.'}


def _event_id(project, work_id, iteration, effect, generation, step_id=None):
    """One admission's identity; a run of more than one pair carries the step id, one pair keeps its original id."""
    parts = [project, work_id, iteration, effect, generation] + ([step_id] if step_id is not None else [])
    return 'WD-' + canonical_digest(parts)[7:31]


def advance(root, project, work_id):
    """Admit the pending step of every running pair; each settles on its own."""
    W, D = _owners(); deliver = []
    with W.dispatch_lock(root):
        task, plan, pin, artifact, state = _load(root, project, work_id)
        if state['state'] != 'RUNNING':return
        spec = pin['research_workflow']; multi = bool(spec.get('pairs'))
        from laplace.pipeline import workflow_operations as _loop
        for pair, lane in _lanes(state, spec):
            mine = _lane_attempts(state, spec, pair)
            if mine:
                history = D._history(task, mine[-1]['event_id'])
                if history and history[-1]['state'] != 'RESULT':
                    deliver.append(mine[-1]['event_id']);continue
            if lane.get('next') not in ('writer', 'reviewer'):continue
            stop = _loop.loop_admission(state['policy'], state, _now(), pin=pin, plan=plan)
            if stop is not None:
                # Extended v2 only: the authored finite budget, run-wide, refuses this admission.
                if multi:
                    for _pair, held in _lanes(state, spec):held['next'] = None
                    state.update(state=stop['state'], loop_exit=stop)
                else:state.update(state=stop['state'], next=None, loop_exit=stop)
                _append(root, project, W._tasks(project, root)[work_id],
                    'loop-exit-' + canonical_digest([state['plan_generation'], len(state['attempts']), stop['reason']])[7:31],
                    'loop-exit', state, {'reason': stop['reason'], 'admissions_used': stop['admissions_used']})
                return
            if _loop.loop_policy(state['policy']) is not None:state.setdefault('loop_started_at', _now())
            _packet(root, project, pin, revalidate=True)
            name = lane['next']; step = pair[name]; effect = ROLE_EFFECT[name]
            recipient = _binding(root, project, task, _recipient_id(state, name, step), effect, pin['settings'][step]['values'])
            event_id = _event_id(project, work_id, lane['iteration'], effect, state['plan_generation'], step if multi else None)
            old = D._history(task, event_id)
            if not old:
                basis, issue = W._work_basis(W._tasks(project, root), work_id)
                if issue:raise ValueError(issue)
                intent = {'record': D.RECORD, 'kind': D.EVENT, 'id': event_id, 'project': project, 'work_id': work_id,
                    'state': 'SUBMITTED', 'ts': _now(), 'attempts': 0, 'max_attempts': 3,
                    'deadline_at': (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=_loop.step_seconds(state['policy'], state, _now()))).isoformat(),
                    'handoff_id': (lane.get('proposal') or {}).get('handoff_id', ''), 'obligation_id': obligation_id(spec, pair['writer']),
                    'recipient': recipient, 'actor': copy.deepcopy(state['launched_by']), 'continuation': None,
                    'work_scope_revision': basis['scope_revision'], 'content_pin': canonical_digest(spec['input_packet']),
                    'workflow_execution': {'schema_version': SCHEMA, 'work_id': work_id, 'effect': effect,
                        'iteration': lane['iteration'], 'step_id': step, 'plan_reference': state['plan_reference'],
                        'plan_generation':state['plan_generation'],
                        'prepared_settings':copy.deepcopy(pin['settings'][step]),
                        'input_policy': 'evidence-packet', 'input_packet': spec['input_packet'],
                        'proposal': copy.deepcopy(lane.get('proposal')), 'judgement': copy.deepcopy(lane.get('judgement'))}}
                W._append(root, intent)
            if not any(a['event_id'] == event_id for a in state['attempts']):
                state['attempts'].append({'event_id': event_id, 'effect': effect, 'iteration': lane['iteration'], **({'step_id': step} if multi else {})})
                _append(root, project, W._tasks(project, root)[work_id], 'admit-' + event_id, 'admit-phase', state, {'event_id': event_id})
            deliver.append(event_id)
    # Never acquire an event lock while retaining the global Work lock.
    for event_id in deliver:D._deliver(root, project, event_id)


def admission_context(root, project, event_id, session_id):
    _, D = _owners();task = D._task_of_event(root, project, event_id);history = D._history(task, event_id)
    intent, latest = history[0], history[-1]
    if latest['state'] != 'RESERVED' or latest.get('session_id') != session_id:
        raise ValueError('Workflow effect requires its exact durable recipient reservation.')
    from laplace.writing import records
    session=records.fold_records(root)['sessions'].get(session_id) or {}
    if (session.get('project')!=project or session.get('workflow_event_id')!=event_id
            or any(session.get(key)!=intent['recipient'].get(key) for key in ('provider','model','effort'))):
        raise ValueError('The actual recipient session differs from the original approved settings/event.')
    if not intent.get('workflow_execution'):
        _validate_general_effect(root,project,task,intent)
        if intent.get('feedback_execution'):
            from laplace.work.feedback_route import admit_execution
            runtime=admit_execution(root,project,event_id,session_id)['runtime_deadline_at']
        else:
            runtime=latest.get('effect_runtime_deadline_at')
            if not runtime:
                runtime=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=intent['effect_runtime_seconds'])).isoformat()
                W,_=_owners();W._append(root,{**latest,'effect_runtime_deadline_at':runtime,'ts':_now()})
        return {'schema_version':'laplace.effect-recipient/1','work_id':task['id'],'event_id':event_id,
            'effect':'proposal-writer','runtime_deadline_at':runtime,'input_policy':'anchored-author-comment' if intent.get('feedback_execution') else 'declared-Work-source-scope'}
    _validate_event(root, project, task, intent)
    return {**copy.deepcopy(intent['workflow_execution']), 'event_id': event_id,
            'runtime_deadline_at': intent['deadline_at']}


def _validate_general_effect(root,project,task,intent):
    _,D=_owners();recipient=intent['recipient']
    if recipient.get('effect') not in {'proposal-writer','research-producer'} or recipient.get('approved_by')!='human':
        raise ValueError('No human-approved effect-specific recipient is recorded.')
    problem=D._revalidate(root,project,task,intent)
    if problem:raise ValueError(problem)
    if recipient['effect']=='proposal-writer' and not intent.get('effect_selection'):
        raise ValueError('No exact source scope was approved for this proposal writer.')


def _validate_event(root, project, task, intent):
    _, _, pin, _, state = _load(root, project, task['id'])
    W, D = _owners();context = intent['workflow_execution']
    current,issue=W._work_basis(W._tasks(project,root),task['id'])
    if issue or current.get('scope_revision')!=intent['work_scope_revision'] or task.get('status') in {'cancelled','withdrawn'}:
        raise ValueError('The original workflow Work scope or standing changed.')
    actor=state.get('launched_by') or {}
    from laplace.writing import records,turn_jobs,child_hosts
    original=records.fold_records(root)['turns'].get(actor.get('turn_id')) or {}
    if (original.get('project')!=project or original.get('session_id')!=pin['prepared_by']['session_id']):
        raise ValueError('Original author turn/session custody is unavailable.')
    marker=child_hosts._read_host(child_hosts._host_path(root,original['session_id']).with_suffix('.cancel.json'))
    if ((original.get('reply') or {}).get('status')=='interrupted'
            or (turn_jobs._JOBS.get(original['id']) or {}).get('interrupt_requested')
            or marker.get('turn_id')==original['id']):
        raise ValueError('The original parent was stopped; no later recipient is automatically admitted.')
    if state['state'] != 'RUNNING' or context['plan_reference'] != state['plan_reference']:
        raise ValueError('Workflow is stopped or this attempt belongs to a retained earlier plan.')
    if (context.get('plan_generation',state['plan_generation'] if not state.get('plan_artifact') else None)
            !=state['plan_generation']):
        raise ValueError('This attempt belongs to an earlier exact plan generation.')
    if context['effect'] not in EFFECTS or context['input_policy'] != 'evidence-packet':
        raise ValueError('Unsupported workflow effect/input policy.')
    if dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(intent['deadline_at']):
        raise ValueError('This workflow phase admission/runtime window expired.')
    recipient=_binding(root, project, task, intent['recipient']['id'], context['effect'], pin['settings'][context['step_id']]['values'])
    if recipient['revision']!=intent['recipient']['revision']:
        raise ValueError('The original effect approval revision changed before admission.')
    _packet(root, project, pin, revalidate=True)


def _research_request(root, project, intent):
    recipient=intent['recipient'];args=copy.deepcopy(recipient.get('producer_args') or {})
    argument=recipient.get('feedback_argument')
    if argument:
        from laplace.work import feedback_route
        task=_owners()[1]._task_of_event(root,project,intent['id'])
        handoff=next(r for r in task.get('phases') or [] if r.get('id')==intent['handoff_id'])
        if not handoff.get('feedback_origin'):raise ValueError('The approved comment argument requires an exact retained author origin.')
        origin=feedback_route._origin(root,project,handoff['feedback_origin'],current=False)
        args[argument]=origin['correction']['text']
    return {'producer_id':recipient['producer_id'],'mode':recipient['producer_mode'],'args':args,
            'request_id':intent['id'],'runtime_seconds':intent['effect_runtime_seconds']}


def _validate_research_effect(root, project, task, intent, payload):
    from laplace.research import research_context,research_runs,research_observation
    _validate_general_effect(root,project,task,intent)
    if dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(intent['deadline_at']):
        raise ValueError('The original research admission window expired.')
    item,home=research_context.project(project,Path(root))
    if home is None:raise ValueError('Registered Research home unavailable.')
    try:producer,_mode,_args,base,path,deps=research_runs._launch_producer(Path(root),project,payload,item,home)
    except research_runs._LaunchRefused as error:raise ValueError(error.body.get('error')) from error
    if research_observation._object_digest(producer)!=intent['recipient'].get('producer_basis'):
        raise ValueError('Registered producer changed after the exact effect approval.')
    obligation=next((r for r in task.get('review_obligations') or [] if r['id']==intent['obligation_id']),None)
    required={path.relative_to(root).as_posix(),*((base/d['path']).relative_to(root).as_posix() for d in deps)}
    if not obligation or not required<=set(obligation.get('inputs') or []):
        raise ValueError('This obligation does not explicitly cover the registered producer and all declared inputs.')


def deliver_research_event(root, project, task, intent, latest):
    """Existing Research job/request custody, never a model or replacement runner."""
    W,D=_owners()
    from laplace.research import research_runs
    payload=_research_request(root,project,intent)
    observed=research_runs.inspect_request(project,payload,Path(root))
    if observed['effect'] in {'UNKNOWN','CONFLICT'}:
        raise ValueError(observed['reason'])
    run=observed.get('run')
    if run is None:
        if latest['state'] in D.TERMINAL:return
        _validate_research_effect(root,project,task,intent,payload)
        attempts=latest.get('attempts',0)
        if attempts>=intent['max_attempts']:raise ValueError('Research delivery attempts exhausted; no new admission.')
        W._append(root,{**intent,'state':'RESERVED','attempts':attempts+1,'research_request_id':intent['id'],'ts':_now()})
        if intent.get('feedback_execution'):
            from laplace.work.feedback_route import admit_research_execution
            admit_research_execution(root,project,intent['id'])
        code,reply=research_runs.launch(project,payload,Path(root))
        # A durable job is meaningful even when activation or its ACK fails.
        observed=research_runs.inspect_request(project,payload,Path(root))
        run=observed.get('run')
        if run is None:
            W._append(root,{**intent,'state':'SUBMITTED','attempts':attempts+1,'last_error':str(reply.get('error') or observed.get('reason') or 'Research admission unconfirmed')[:400],'ts':_now()})
            raise ValueError('Research admission was not confirmed; inspect the same event/request.')
    if intent.get('feedback_execution'):
        from laplace.work.feedback_route import record_research_execution
        record_research_execution(root,project,intent['id'],run)
    terminal=_research_terminal(run)
    row={**intent,'state':'RESULT' if terminal else 'ADMITTED','research_run_id':run['id'],
        'attempts':D._history(W._tasks(project,root)[task['id']],intent['id'])[-1].get('attempts',0),
        'result':{'status':run.get('state'),'read':research_run_read(project,run['id'])},
        'acceptance':D._acceptance(root,project,task,intent,None),'recipient_ack':'TERMINAL' if terminal else None,'ts':_now()}
    if terminal and (intent.get('continuation') or {}).get('parent_session_id'):
        row['turn_id']=None
        with W.dispatch_lock(root):row['continuation_work_id']=D._continuation_row(root,project,task,intent,row,intent['continuation'])
    if latest.get('state')!=row['state'] or latest.get('research_run_id')!=run['id']:
        W._append(root,row)
    if terminal and row.get('continuation_work_id'):D._return_to_parent(root,project,intent['id'])


def research_run_read(project, ident):
    return {'native':{'operation':'run_status','payload':{'id':ident}},
            'http':{'method':'GET','url':'/research/run/status?'+urlencode({'project':project,'id':ident})}}


def _research_terminal(run):
    return bool(run and (run.get('supervision') or {}).get('phase')=='TERMINAL'
        and (run.get('cleanup') or {}).get('status')=='VERIFIED' and not run.get('cleanup_unresolved'))


def research_event_view(root, project, task, intent, latest, *, read_context=None):
    from laplace.research import research_runs
    from laplace.work.feedback_route import handle_read
    ident=latest.get('research_run_id');run=None
    if ident:
        code,run=research_runs.run_status_read(project,ident,Path(root))
        if code!=200:run=None
    terminal=_research_terminal(run)
    return {'id':intent['id'],'work_id':task['id'],'state':latest['state'],'effect':'research-producer',
        'recipient':copy.deepcopy(intent['recipient']),'obligation_id':intent['obligation_id'],
        'attempts':latest.get('attempts',0),'max_attempts':intent['max_attempts'],'deadline_at':intent['deadline_at'],
        'admitted':{'research_run_id':ident,'recipient_ack':'TERMINAL' if terminal else None} if ident else None,
        'research_run_read':research_run_read(project,ident) if ident else None,
        'result':{'available':terminal,'status':run.get('state') if run else 'UNCONFIRMED','read':research_run_read(project,ident) if ident else None},
        'acceptance':_owners()[1]._acceptance(root,project,task,intent,None,read_context=read_context),
        'meaning':'Registered producer result and cleanup only; no scientific acceptance is inferred.',
        'read':handle_read(project,{'action':'status','event_id':intent['id']})}


def private_input(root,project,event_id):
    """Complete owner-selected context, separate from the editable author task.

    Only a private actual event locator reaches here. No public request can
    substitute the body, bypass raw ART checks, or relabel this as sealed input.
    """
    from laplace.core.identity import bytes_digest
    _,D=_owners();task=D._task_of_event(root,project,event_id);intent=D._history(task,event_id)[0]
    context=intent.get('workflow_execution')
    if not context or context.get('schema_version')!=SCHEMA:raise ValueError('No selected workflow input is admitted for this event.')
    _validate_event(root,project,task,intent)
    _,_,pin,_,_=_load(root,project,task['id']);spec=pin['research_workflow'];packet=_packet(root,project,pin)
    text=spec['instructions'][context['step_id']]+'\n\nINPUT POLICY: evidence-packet; project-informed, not blind or sealed.\n'
    text+=json.dumps({'selected_evidence':packet,'proposal':context.get('proposal'),'previous_judgement':context.get('judgement')},ensure_ascii=False)
    if context['effect']=='independent-review':text+='\nReturn JSON only: {"verdict":"ACCEPT|REVISE|REJECT","findings":[{"id":"...","summary":"..."}]}. This is scoped independent judgement, not author acceptance or a truth certificate.'
    else:text+='\nReturn an edit proposal only. All manuscript/source application and unrelated mutations are refused.'
    return {'text':text,'receipt':{'schema_version':'laplace.workflow-input-delivery/1','event_id':event_id,
        'input_policy':'evidence-packet','part_sha256':bytes_digest(text.encode()),'characters':len(text),'utf8_bytes':len(text.encode()),
        'packet':copy.deepcopy(context['input_packet']),'coverage':'COMPLETE_SELECTED_PACKET',
        'validation':{'custody':'VERIFIED_RAW_ART','representation':'COMPLETE_SERIALIZABLE_SELECTED_CONTEXT'},
        'sizing':{'fit':'UNMEASURED','capacity':'provider-owned','packet_truncated':False},
        'qualification':'Complete exact selected representations in retained prompt; no model attention, semantic acceptance or token-fit assertion.'}}


def deliver_event(root, project, task, intent, latest):
    """Reserve/admit once, then settle outside the event reservation lock."""
    _, D = _owners()
    with D._event_lock(root, intent['id']):
        task = D._task_of_event(root, project, intent['id'])
        history = D._history(task, intent['id'])
        intent, latest = history[0], history[-1]
        retained = _deliver_event_locked(root, project, task, intent, latest)
    if retained:
        admitted, reply = retained
        settle_event(root, project, task, intent, admitted, reply)


def _deliver_event_locked(root, project, task, intent, latest):
    W, D = _owners()
    from laplace.writing import records, turn_admission
    request = {'project': project, 'request_id': intent['id'], 'mode': 'revise' if intent['workflow_execution']['effect'] == 'proposal-writer' else 'review'}
    found = turn_admission.reused_turn(records.fold_records(root), request)
    if found:
        turn = records.fold_records(root)['turns'][found['turn_id']]
        if (turn.get('workflow_execution') or {}).get('event_id') != intent['id']:
            raise ValueError('Workflow request already belongs to another admission; no new recipient allowed.')
        if latest['state'] not in ('ADMITTED', 'RESULT'):
            W._append(root, {**intent, 'state': 'ADMITTED', 'session_id': found['session_id'], 'turn_id': found['turn_id'], 'ts': _now(), 'recovered': True})
        if turn.get('reply') and latest['state'] != 'RESULT':return {**latest, **found}, turn['reply']
        return
    if latest['state'] in D.TERMINAL:return
    attempts=latest.get('attempts',0)
    if attempts>=intent['max_attempts']:
        W._append(root,{**intent,'state':'UNCONFIRMED','attempts':attempts,'session_id':latest.get('session_id'),
            'reason':'Finite delivery attempts exhausted; retained effects/request remain inspectable.','ts':_now()})
        return
    # Pure complete input/known request validation precedes any new WS. This
    # does not turn the author's editable-message limit into a packet limit.
    text='Review the complete selected evidence and proposal in the owned workflow context.' if request['mode']=='review' else 'Prepare a manuscript proposal from the complete selected workflow evidence.'
    try:
        private_input(root,project,intent['id'])
        turn_admission.prepare_request({**request,'text':text})
    except (ValueError,OSError,KeyError) as error:
        W._append(root,{**intent,'state':'STALE','attempts':attempts,'session_id':latest.get('session_id'),
            'known_refusal':True,'refusal_stage':'BEFORE_NEW_SESSION_OR_TURN','last_error':str(error)[:400],
            'session_creation_attempted':bool(latest.get('session_creation_attempted')),'ts':_now()})
        with W.dispatch_lock(root):
            current,_plan,_pin,_artifact,state=_load(root,project,task['id'])
            state.update(state='PARTIAL',admission_refused_event_id=intent['id'],reason='Known admission refusal before any new session or turn: '+str(error)[:300])
            _append(root,project,current,'refused-'+intent['id'],'admission-refused',state,
                {'event_id':intent['id'],'refusal_stage':'BEFORE_NEW_SESSION_OR_TURN'})
        raise
    try:
        _validate_event(root, project, task, intent)
        recipient = intent['recipient'];sid = latest.get('session_id')
        if not sid:
            matches = [s for s in records.fold_records(root)['sessions'].values()
                       if s.get('project') == project and s.get('workflow_event_id') == intent['id']]
            if len(matches) > 1:raise ValueError('Workflow session creation custody is ambiguous; no new session permitted.')
            if matches:sid = matches[0]['id']
        if not sid:
            if latest.get('session_creation_attempted'):
                raise ValueError('Workflow session creation is UNKNOWN; retain this exact event for inspection.')
            W._append(root, {**intent, 'state': 'RESERVED', 'attempts':attempts+1,'session_creation_attempted': True, 'ts': _now()})
            session = turn_admission.new_session(root, project, recipient['provider'], recipient['model'], recipient.get('effort'),
                role='author' if request['mode'] == 'revise' else 'review', model_role='worker' if request['mode'] == 'revise' else 'judge',
                workflow_event_id=intent['id'])
            sid = session['id']
        W._append(root, {**intent, 'state': 'RESERVED', 'attempts':attempts+1,'session_id': sid, 'ts': _now()})
        _, _, pin, _, _ = _load(root, project, task['id'])
        context = intent['workflow_execution'];spec = pin['research_workflow']
        admitted = turn_admission.start_workflow_turn(root, {**request, 'session_id': sid, 'text': text,
            'selection': spec['selection'], **D._source_work_fields(root, project, task['id'])}, intent['id'])
        actual = D._history(W._tasks(project, root)[task['id']], intent['id'])[-1]
        if actual['state'] != 'RESULT':
            W._append(root, {**intent, 'state': 'ADMITTED', 'attempts':attempts+1,'session_id': admitted['session_id'], 'turn_id': admitted['turn_id'], 'ts': _now()})
        turn = records.fold_records(root)['turns'].get(admitted['turn_id']) or {}
        if turn.get('reply') and actual['state'] != 'RESULT':
            return {**latest, **admitted}, turn['reply']
    except Exception as error:
        W._append(root, {**intent, 'state': 'SUBMITTED', 'attempts':attempts+1,'session_id': locals().get('sid'),
            'session_creation_attempted': True, 'last_error': str(error)[:400], 'ts': _now()})
        raise


def settle_event(root, project, task, intent, latest, result):
    W, D = _owners()
    from laplace.writing import records
    with D._event_lock(root, intent['id']), W.dispatch_lock(root):
        task, _, pin, _, state = _load(root, project, task['id'])
        current = D._history(task, intent['id'])[-1]
        if current['state'] == 'RESULT':return
        turn_id = latest['turn_id'];turn = records.fold_records(root)['turns'][turn_id]
        if (turn.get('workflow_execution') or {}).get('event_id') != intent['id']:
            raise ValueError('Only the actually admitted recipient can settle this workflow effect.')
        already = next((r for r in _phase_rows(task) if r.get('request_id') == 'settled-' + intent['id']), None)
        if already:
            W._append(root, {**intent, 'state': 'RESULT', 'session_id': turn['session_id'], 'turn_id': turn_id,
                'recipient_ack': 'TERMINAL', 'result': {'status': result.get('status')}, 'ts': _now()})
            return
        context = intent['workflow_execution'];spec = pin['research_workflow'];multi = bool(spec.get('pairs'))
        # Only the pair whose step this admission names is changed by its result.
        pair, lane = _lane_of(state, spec, context['step_id'])
        if result.get('status') != 'completed':
            _exit_lane(state, lane, spec, 'PARTIAL')
        elif context['effect'] == 'proposal-writer':
            proposal = result.get('proposal');validation = result.get('proposal_validation') or {}
            if not isinstance(proposal, dict) or not proposal.get('edits') or not validation.get('valid'):
                _exit_lane(state, lane, spec, 'PARTIAL', reason='No valid source-addressed proposal was retained.')
            else:
                from laplace.work import project_work_review as R
                base = spec['input_packet']['artifact_path'].rsplit('/', 1)[0]
                meta = {'schema_version': 'laplace.workflow-app-preparation/1', 'request_id': intent['id'],
                    'intent_digest': canonical_digest(proposal), 'prepared_by': pin['prepared_by']}
                saved = _artifact_once(root, project, base + '/proposal-' + intent['id'] + '.json', proposal, meta, turn_id=turn_id)
                packet = spec['input_packet']
                h = R.record(project, {'id': task['id'], 'phase': 'handoff', 'request_id': 'handoff-' + intent['id'],
                    'expected_work_revision': W._task_revision(W._tasks(project, root)[task['id']]),
                    'obligations': [obligation_id(spec, pair['writer'])], 'pins': {
                        saved['path']: 'sha256:' + saved['sha256'].removeprefix('sha256:'),
                        packet['path']: 'sha256:' + packet['sha256'].removeprefix('sha256:')},
                    'object': {'kind': 'manuscript-proposal', 'aggregate': saved['value_digest']}}, root, door={'origin': 'native', 'turn_id': turn_id})
                from laplace.manuscript import proposal_navigation, proposal_currentness
                proposal_view = proposal_currentness.proposal_view(turn, records=records.fold_records(root))
                version = proposal_view.get('proposal_version') or next(reversed(turn.get('proposal_versions') or {}), None)
                lane.update(proposal={**saved, 'turn_id': turn_id, 'handoff_id': h['phase']['id'],
                    'proposal_version': version,
                    'read': proposal_navigation.handle(project, {'view': 'preview', 'id': turn_id, 'proposal_version': version})}, next='reviewer')
        else:
            from laplace.work import project_work_review as R
            try:
                judgement = json.loads(str(result.get('text') or ''))
                if not isinstance(judgement,dict):raise ValueError('Independent judgement must be a JSON object.')
                if judgement.get('verdict') not in {'ACCEPT', 'REVISE', 'REJECT'}:raise ValueError('Unknown judgement')
                verdict = 'ACCEPT' if judgement['verdict'] == 'ACCEPT' else 'HOLD' if judgement['verdict'] == 'REVISE' else 'REJECT'
                recorded = R.record(project, {'id': task['id'], 'phase': 'review', 'request_id': 'review-' + intent['id'],
                    'expected_work_revision': W._task_revision(W._tasks(project, root)[task['id']]),
                    'handoff_id': lane['proposal']['handoff_id'], 'obligation_id': obligation_id(spec, pair['writer']),
                    'verdict': verdict, 'findings': judgement.get('findings', [])}, root, door={'origin': 'native', 'turn_id': turn_id})
                lane['judgement'] = {'verdict': judgement['verdict'], 'phase_read': recorded['phase_read'],
                    'findings': copy.deepcopy(judgement.get('findings', [])), 'turn_id': turn_id}
                from laplace.pipeline import workflow_operations as _loop
                if _loop.loop_policy(state['policy']) is not None:
                    # Extended v2 only: the judgement becomes exact ART custody the
                    # original-parent synthesis must read; every iteration is kept.
                    base = spec['input_packet']['artifact_path'].rsplit('/', 1)[0]
                    value = {'event_id': intent['id'], 'iteration': lane['iteration'], 'turn_id': turn_id,
                        'verdict': judgement['verdict'], 'findings': copy.deepcopy(judgement.get('findings', [])),
                        'handoff_id': lane['proposal']['handoff_id'], 'phase_read': recorded['phase_read']}
                    saved = _artifact_once(root, project, base + '/judgement-' + intent['id'] + '.json', value,
                        {'schema_version': 'laplace.workflow-app-preparation/1', 'request_id': intent['id'],
                         'intent_digest': canonical_digest(value), 'prepared_by': pin['prepared_by'],
                         'publication_kind': 'review-judgement'}, turn_id=turn_id)
                    lane['judgement']['artifact'] = {k: saved[k] for k in ('id', 'path', 'artifact_path', 'sha256', 'read')}
                    lane.setdefault('loop_history', []).append({'iteration': lane['iteration'],
                        'proposal': copy.deepcopy(lane.get('proposal')), 'judgement': copy.deepcopy(lane['judgement'])})
                # The run-wide authored budget counts every pair's admissions; the iteration is this pair's.
                decision = _loop.loop_after_judgement(state['policy'], {**state, 'iteration': lane['iteration']} if multi else state, judgement['verdict'], _now())
                if decision is not None:
                    # Extended v2: schedule only the next step from this actual judgement.
                    lane['loop_decision'] = decision
                    if decision['decision'] == 'CONTINUE':lane.update(iteration=decision['iteration'], next='writer')
                    else:_exit_lane(state, lane, spec, decision['state'], loop_exit=decision)
                elif verdict == 'ACCEPT':_exit_lane(state, lane, spec, 'AWAITING_HUMAN_APPLY')
                elif lane['iteration'] >= state['policy']['max_iterations']:_exit_lane(state, lane, spec, 'LIMIT_REACHED')
                else:lane.update(iteration=lane['iteration'] + 1, next='writer')
            except (ValueError, TypeError, KeyError) as error:
                _exit_lane(state, lane, spec, 'PARTIAL', reason='No valid independent judgement: ' + str(error)[:300])
        if state['state'] == 'RUNNING' and state['policy']['advance'] == 'manual':state['state'] = 'AWAITING_ADVANCE'
        _append(root, project, W._tasks(project, root)[task['id']], 'settled-' + intent['id'], 'recipient-result', state,
            {'event_id': intent['id'], 'turn_id': turn_id, 'reply_id': (turn.get('reply') or {}).get('id')})
        W._append(root, {**intent, 'state': 'RESULT', 'session_id': turn['session_id'], 'turn_id': turn_id,
            'recipient_ack': 'TERMINAL', 'result': {'status': result.get('status')}, 'ts': _now()})
    if state['state'] == 'RUNNING':advance(root, project, task['id'])


def event_view(root, project, task, intent, latest, *, read_context=None):
    from laplace.writing import workflow_dispatch, records,session_reads
    context = intent['workflow_execution'];turn_id = latest.get('turn_id');sid = latest.get('session_id')
    turn = _owners()[1]._read_fold(root,read_context)['turns'].get(turn_id, {}) if turn_id else {}
    message=session_reads._message_handle({'project':project,'session_id':sid,'turn_id':turn_id,'part':'reply','limit':4000},offset=0) if turn_id else None
    proposal_read=None
    if turn_id and context['effect']=='proposal-writer':
        from laplace.manuscript import manuscript_proposals,proposal_navigation
        version,_candidate=manuscript_proposals.proposal_version(turn)
        if version:proposal_read=proposal_navigation.handle(project,{'view':'preview','id':turn_id,'proposal_version':version})
    return {'event_id': intent['id'], 'id': intent['id'], 'state': latest['state'], 'effect': context['effect'], 'step_id': context.get('step_id'),
        'iteration': context['iteration'], 'binding': copy.deepcopy(intent['recipient']), 'session_id': sid, 'turn_id': turn_id,
        'input_policy': context['input_policy'], 'consumed_bases': copy.deepcopy(context['input_packet']['consumed_bases']),
        'settings': {'prepared':copy.deepcopy(context.get('prepared_settings')),
            'admitted':copy.deepcopy(turn.get('provider_settings')),
            'sent':copy.deepcopy((turn.get('reply') or {}).get('settings_as_sent')),
            'sent_observation':(turn.get('reply') or {}).get('settings_observation','UNOBSERVED; no actual adapter-settings receipt is recorded')},
        'result': copy.deepcopy(latest.get('result')),
        'error': latest.get('last_error'), 'recipient_ack': latest.get('recipient_ack'),
        'known_refusal':bool(latest.get('known_refusal')),'refusal_stage':latest.get('refusal_stage'),
        'public_reply_read':{key:message[key] for key in ('identity','http','sdk')} if message else None,
        'proposal_read':proposal_read,
        'conversation': workflow_dispatch._conversation(project, sid, turn_id) if turn_id else None,
        'read': read_handle(project, task['id'])}


def admit_operation(root, project, turn_id, operation, payload):
    """Real effect fence, resolved from actual admitted event; role labels grant nothing."""
    from laplace.writing import records, reads
    turn = records.fold_records(root)['turns'].get(turn_id) or {}
    selected=(turn.get('workspace_context') or {}).get('workflow_action') or {}
    if (selected.get('reference') or {}).get('kind')=='research-workflow-start' and reads.effect(operation,payload)=='write':
        expected=selected.get('native') or {}
        if operation!=expected.get('operation') or {k:v for k,v in payload.items() if k!='project'}!=expected.get('payload'):
            raise ValueError('This selected Start turn admits only its exact research workflow action; manuscript Apply is a separate human effect.')
    context = turn.get('workflow_execution')
    if not context or reads.effect(operation, payload) != 'write':return
    _, D = _owners(); task = D._task_of_event(root, project, context['event_id'])
    history = D._history(task, context['event_id']);intent, latest = history[0], history[-1]
    same=(intent.get('workflow_execution') == {k:v for k,v in context.items() if k not in {'event_id','runtime_deadline_at'}}
          if context.get('schema_version')==SCHEMA else intent['recipient'].get('effect')==context.get('effect')
          and context.get('schema_version')=='laplace.effect-recipient/1')
    if (turn.get('reply') or latest['state'] not in {'RESERVED','ADMITTED'}
            or latest.get('session_id') != turn['session_id'] or latest.get('turn_id') not in (None,turn_id) or not same):
        raise ValueError('Workflow effect is not this actual admitted active recipient.')
    if dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(context['runtime_deadline_at']):
        raise ValueError('Workflow recipient runtime has expired.')
    permitted = {'propose_revision'} if context['effect'] == 'proposal-writer' else {'note', 'note_status', 'work_review'}
    if operation not in permitted:
        raise ValueError('This actual workflow recipient is admitted only for ' + context['effect'] + '; ' + operation + ' is not permitted.')
    if operation=='work_review' and (payload.get('id')!=task['id'] or payload.get('phase')!='review'
            or payload.get('handoff_id')!=(intent.get('workflow_execution') or {}).get('proposal',{}).get('handoff_id')
            or payload.get('obligation_id')!=intent['obligation_id']):
        raise ValueError('Independent review records only its exact delivered Work/handoff/obligation.')
