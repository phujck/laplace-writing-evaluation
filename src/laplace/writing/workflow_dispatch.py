"""Saved definitions prepared by the existing app dispatch/artifact/Work owners.

No run ledger or execution loop lives here. Request custody is the immutable plan
ART and its dispatch Work; execution and public content remain at their owners.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlencode

from laplace.projects import artifacts
from laplace.writing import records

SCHEMA = 'laplace.workflow-app-preparation/1'


def _definitions():
    from laplace.pipeline import workflow_definitions
    return workflow_definitions


def _digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _keys(project, request_id):
    suffix = _digest([project, request_id]).removeprefix('sha256:')[:32]
    return 'WORK-wdef-' + suffix, 'development/workflows/' + suffix + '/plan.json'


def admission(root, caller):
    D = _definitions()
    if caller.kind != 'project' or not isinstance(caller, D._NativeCaller):
        return {'permitted': False, 'code': 'APP_PREPARE_REQUIRES_NATIVE_AUTHOR'}
    fresh = D.native_caller(root, caller.namespace, caller.mode, caller.turn_id)
    if not D._can_save(fresh):
        return fresh.admission
    session = records.fold_records(root)['sessions'].get(fresh.admission['session_id']) or {}
    if session.get('dispatch_id'):
        return {'permitted': False, 'code': 'APP_PREPARE_REQUIRES_PARENT_SESSION'}
    return fresh.admission


def _admit(root, caller):
    value = admission(root, caller)
    if not value.get('permitted'):
        raise _definitions().Refused('NATIVE_WRITE_NOT_ADMITTED', admission=value)
    return value


def actions(root, caller, row):
    D = _definitions()
    scoped = row['scope']['kind'] == 'project'
    permitted = scoped and admission(root, caller).get('permitted', False)
    payload = {'action': 'prepare', 'profile': D.APP_PROFILE,
               'reference': D.reference(row['definition_id'], row['definition_revision'])}
    project = row['scope'].get('namespace')
    research=bool(D._body(root,row).get('run_policy'))
    required=['request_id','step_ids','goal','fan_out_max']+(['inputs'] if research else [])
    allowed=required+(['selection'] if research else [])
    return {
        'app_prepare': {'available': scoped, 'permitted': permitted,
            'reason': '' if permitted else 'Prepare inside a current admitted author parent conversation in this project',
            'native': {'operation': 'workflow_definition_change', 'payload': payload},
            'required_inputs': required, 'allowed_inputs': allowed},
        'use_in_conversation': {'available': scoped, 'permitted': scoped,
            'read': D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-compose'),
            'required_inputs': required, 'allowed_inputs': allowed,
            'label': 'Prepare in conversation', 'requires_role': 'author-parent',
            'send_required': True, 'http': {'method': 'POST', 'route': '/authoring/turn'},
            'project': project,
            'payload': {'project': project, 'mode': 'work',
                'text': 'Prepare an explicitly selected supported slice of this exact saved workflow through '
                        'workflow_definition_change with profile ' + D.APP_PROFILE + '. Inspect its owner read first: '
                        + json.dumps(D.scoped_handle(caller,row['definition_id'], row['definition_revision'])['native'], sort_keys=True)
                        + '. Ask for the selected step IDs, completion goal and explicit fan_out_max if absent. '
                          'Retain the exact stable request and effect receipt. Prepare only; do not launch.'},
            'meaning': 'Opens the existing composer. Only explicit Send admits a real parent turn; this read starts nothing.'}}


def _composer(project, payload, read, label):
    return {'available': True, 'permitted': True, 'label': label,
        'requires_role': 'author-parent', 'send_required': True, 'project': project,
        'http': {'method': 'POST', 'route': '/authoring/turn'}, 'payload': payload,
        'read': read,
        'project_url': '/project?' + urlencode({'workspace': 'writing', 'corpus': project,
            'workflow_action_read': json.dumps(read['request'], separators=(',', ':'))}),
        'meaning': 'Re-read this action in the existing project composer; explicit Send remains required.'}


def _continue_action(root, project, row, work, step_id, packet):
    from laplace.writing import dispatch_execution
    offer = dispatch_execution.continuation_offer(root, project, work, packet)
    action = {'available': offer['available'], 'permitted': offer['available'],
        'reason': offer.get('reason', ''), 'label': 'Prepare review continuation message',
        'read': _definitions().handle(row['definition_id'], row['definition_revision'],
            facet='app-continue-compose', work_id=work['id'], step_id=step_id),
        'required_inputs': ['request_id'], 'project': project, 'offer': offer}
    if offer['available']:
        action['native'] = {'operation': offer['operation'], 'payload': offer['payload']}
    return action


ACTION_CONTEXT_SCHEMA = 'laplace.workflow-action-context/1'
ACTION_KIND = 'failed-review-continuation'
_ACTION_IDENTITIES = {'project', 'definition_id', 'work_id', 'step_id', 'request_id', 'parent_session_id'}


def action_input(value):
    """Only an owner-qualified locator and its inspected basis enter admission."""
    if isinstance(value, dict) and (value.get('reference') or {}).get('kind') == 'research-workflow-start':
        from laplace.writing.workflow_progression import action_input as admit
        return admit(value)
    import re
    from laplace.core import identity
    if not isinstance(value, dict) or set(value) != {'reference', 'expected_basis'}:
        raise ValueError('Workflow action context requires only reference and expected_basis.')
    ref = value['reference']
    if (identity.reference_problems(ref) or set(ref) != {'schema_version', 'owner', 'kind', 'identity', 'version'}
            or ref['owner'] != 'pipeline.workflow' or ref['kind'] != ACTION_KIND
            or set(ref['identity']) != _ACTION_IDENTITIES
            or any(len(item) > 160 for item in ref['identity'].values())
            or set(ref['version']) != {'definition_revision'}
            or not isinstance(ref['version']['definition_revision'], str)
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', ref['version']['definition_revision'])
            or not isinstance(value['expected_basis'], str)
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', value['expected_basis'])):
        raise ValueError('Workflow action reference or expected basis is malformed.')
    return json.loads(json.dumps(value))


def resolve_action_context(root, project, value, *, session_id, mode, work_id, work_guards):
    if isinstance(value, dict) and (value.get('reference') or {}).get('kind') == 'research-workflow-start':
        from laplace.writing.workflow_progression import resolve_action_context as resolve
        return resolve(root, project, value, session_id=session_id, mode=mode, work_id=work_id, work_guards=work_guards)
    """Re-read one selected continuation before session or provider effects."""
    from laplace.work import owner_discovery
    value = action_input(value); ref = value['reference']; ident = ref['identity']
    if (project != ident['project'] or session_id != ident['parent_session_id']
            or mode != 'work' or work_id != ident['work_id']):
        raise ValueError('Workflow action requires its exact project, original parent and explicit Work.')
    D = _definitions()
    result = D.read(root, owner_discovery.project_scope(project, 'sdk'), {
        'definition_id': ident['definition_id'], 'version': ref['version']['definition_revision'],
        'facet': 'app-continue-compose', 'work_id': work_id, 'step_id': ident['step_id'],
        'request_id': ident['request_id'], 'expected_action_basis': value['expected_basis']})
    action = result.get('action') or {}; snapshot = action.get('action_context')
    if not snapshot or snapshot['reference'] != ref:
        raise D.Refused('ACTION_CONTEXT_UNAVAILABLE', action.get('reason', 'Inspect the selected continuation.'))
    target = action['work_target']
    if any(work_guards.get(key) != target[field] for key, field in (
            ('expected_work_scope_revision', 'work_scope_revision'),
            ('expected_dependency_revision', 'dependency_revision'))):
        raise D.Refused('ACTION_WORK_BASIS_CHANGED', next_reads=[snapshot['read']])
    return snapshot


def _continue_compose(root, caller, row, payload):
    from laplace.work import project_work
    from laplace.writing import dispatch_execution
    D = _definitions(); project = row['scope']['namespace']
    work = project_work._tasks(project, root).get(payload.get('work_id')) or {}
    _, pin, _ = _checked(root, project, work)
    if pin['reference'] != D.reference(row['definition_id'], row['definition_revision']):
        raise D.Refused('APP_RUN_NOT_IN_SCOPE')
    step = payload.get('step_id');packet = pin['step_packets'].get(step)
    if not packet:raise D.Refused('STEP_NOT_IN_PREPARED_SLICE')
    request_id = payload.get('request_id')
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 160:
        raise D.Refused('CONTINUATION_REQUEST_ID_REQUIRED')
    offered = _continue_action(root, project, row, work, step, packet)
    if not offered['available']:
        if 'expected_action_basis' in payload:
            raise D.Refused('ACTION_CONTEXT_UNAVAILABLE', offered.get('reason', 'Inspect the selected continuation.'),
                next_reads=[D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-continue-compose',
                    work_id=work['id'], step_id=step, request_id=request_id)])
        return {'action': offered}
    offer = offered['offer'];call = {**offered['native'], 'payload': {**offer['payload'], 'request_id': request_id}}
    detail = project_work.read(project, {'view': 'detail', 'id': work['id']}, root)['task']
    # Propagate the ordinary Work owner's observed message-target guards.
    target = {key: detail[key] for key in ('id', 'title', 'section_ids', 'work_scope_revision', 'dependency_revision')}
    from laplace.core import identity
    reference = identity.reference('pipeline.workflow', ACTION_KIND, {
        'project': project, 'definition_id': row['definition_id'], 'work_id': work['id'],
        'step_id': step, 'request_id': request_id, 'parent_session_id': offer['parent']['session_id']},
        version={'definition_revision': row['definition_revision']})
    basis = identity.canonical_digest({'native': call, 'project': project,
        'parent_session_id': offer['parent']['session_id'],
        'definition_reference': pin['reference'], 'work_target': {key: target[key] for key in (
            'id', 'work_scope_revision', 'dependency_revision')}})
    reinspection = D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-continue-compose',
        work_id=work['id'], step_id=step, request_id=request_id)
    if payload.get('expected_action_basis', basis) != basis:
        raise D.Refused('ACTION_CONTEXT_CHANGED', 'The selected continuation changed; inspect before choosing a new proposal.',
                        next_reads=[reinspection])
    leaf = {'reference': reference, 'expected_basis': basis}
    read = D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-continue-compose',
        work_id=work['id'], step_id=step, request_id=request_id, expected_action_basis=basis)
    body = D._body(root, row); selected = next(item for item in body['steps'] if item['id'] == step)
    snapshot = {'schema_version': ACTION_CONTEXT_SCHEMA, **leaf, 'native': call,
        'summary': {'step_id': step, 'step_title': (selected.get('title') or step)[:240],
            'workflow_title': body['title'][:240], 'definition_reference': pin['reference'],
            'work_id': work['id'], 'parent_session_id': offer['parent']['session_id'],
            'budget': offer['budget'], 'reused_outputs': offer['reused_outputs']}, 'read': read}
    turn_payload = {'project': project, 'session_id': offer['parent']['session_id'], 'mode': 'work',
        'work_id': target['id'], 'expected_work_scope_revision': target['work_scope_revision'],
        'expected_dependency_revision': target['dependency_revision'],
        'workspace_context': {'surface': 'project', 'workflow_action': leaf},
        'text': 'Continue ' + step + ' using the retained worker output. '
                'Keep the completed work and report anything still unresolved.'}
    action = _composer(project, turn_payload, read, offered['label'])
    action['work_target'] = target
    action['action_context'] = snapshot
    return {'action': action, 'continuation_payload': call['payload'], 'offer': offer}


def compose(root, caller, row, payload):
    D = _definitions()
    if row['scope']['kind'] != 'project':
        raise D.Refused('APP_RUN_NOT_IN_SCOPE')
    project = row['scope']['namespace']
    if payload['facet'] == 'app-continue-compose':
        return _continue_compose(root, caller, row, payload)
    if payload['facet'] == 'app-launch-compose':
        from laplace.work import project_work
        work = project_work._tasks(project, root).get(payload.get('work_id')) or {}
        if work:
            _plan, pin, _artifact = _checked(root, project, work)
            if pin.get('research_workflow'):
                from laplace.writing.workflow_progression import view
                return {'action': {'available':False,'permitted':False,
                    'reason':'Inspect the research workflow and select exact approved writer/reviewer bindings before preparing Start.',
                    'read':view(root,project,work['id'])['read']}}
        if (work.get('prepared_workflow') or {}).get('reference') != D.reference(row['definition_id'], row['definition_revision']):
            raise D.Refused('APP_RUN_NOT_IN_SCOPE')
        _, pin, _ = _checked(root, project, work)
        read = D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-launch-compose', work_id=work['id'])
        text = ('Inspect the exact prepared workflow dispatch through ' + json.dumps(
            D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-run', work_id=work['id'])['native'], sort_keys=True)
            + '. Explicitly start this already prepared dispatch once using dispatch_launch '
            + json.dumps({'id': work['id']}, sort_keys=True)
            + '. Preserve the original plan and session; do not create another dispatch or replay children. '
              'Consume its exact typed returns through the existing dispatch owner.')
        action = _composer(project, {'project': project, 'session_id': pin['prepared_by']['session_id'],
            'mode': 'work', 'text': text}, read, 'Start in original conversation')
        if work.get('dispatch_admitted'):
            action.update(permitted=False, reason='Already admitted; inspect the recorded parent continuation instead of starting again')
        return {'action': action, 'prepared_by': pin['prepared_by']}
    request = {key: payload[key] for key in ('request_id', 'step_ids', 'goal', 'fan_out_max', 'inputs', 'selection') if key in payload}
    request.update(action='prepare', profile=D.APP_PROFILE, reference=D.reference(row['definition_id'], row['definition_revision']))
    from jsonschema import Draft202012Validator
    error = next(Draft202012Validator(D.native_change_contract()).iter_errors(request), None)
    if error:
        raise D.Refused('INVALID_APP_PREPARATION', error.message)
    # Pure supported compilation exposes local obligations without live capability probes or effects.
    synthetic = D._NativeCaller('project', 'native', project)
    _compile(root, synthetic, row, D._body(root, row), {key: value for key, value in request.items() if key != 'action'},
             {'project': project, 'session_id': None, 'turn_id': None})
    read = D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-compose',
        **{key: request[key] for key in ('request_id', 'step_ids', 'goal', 'fan_out_max', 'inputs', 'selection') if key in request})
    action = _composer(project, {'project': project, 'mode': 'work',
        'text': 'Prepare only this exact saved workflow through workflow_definition_change using exactly this request: '
                + json.dumps(request, ensure_ascii=False, sort_keys=True)
                + '. Save the returned effect receipt and inspect its app-run. Do not launch or create another plan.'}, read,
        'Prepare in conversation')
    return {'action': action, 'prepare_payload': request}


def _compile(root, caller, row, body, payload, prepared_by):
    """Project the supported graph into the carrier's actual ordered dependencies."""
    if body.get('run_policy'):
        from laplace.writing.workflow_progression import compile_plan
        return compile_plan(root, caller, row, body, payload, prepared_by)
    if 'inputs' in payload or 'selection' in payload:
        raise _definitions().Refused('UNCONSUMED_PREPARATION_INPUT', 'The legacy dispatch profile does not consume selected-evidence inputs; no declaration was silently dropped.')
    D = _definitions()
    from laplace.work import project_work
    selected = payload['step_ids']
    steps = {step['id']: step for step in body['steps']}
    if len(set(selected)) != len(selected) or not set(selected) <= set(steps):raise D.Refused('UNSUPPORTED_SELECTION')
    from laplace.pipeline import workflow_operations as operations
    synthesis=operations.parent_synthesis(root,caller.namespace,body,selected,prepared_by)
    selected=[sid for sid in selected if steps[sid]['assignment']['role']!='synthesis']
    if not 2 <= len(selected) <= 8:
        raise D.Refused('UNSUPPORTED_SELECTION', 'Choose2–8distinct saved step IDs')
    settings, _ = D.resolve_settings(root, caller, body, edit_revision=row['definition_revision'])
    obligations = []
    deps = {sid: [] for sid in selected}
    for edge in body.get('edges', []):
        if synthesis and edge['to']==synthesis['step_id']:
            if edge['kind']!='control' or edge['from'] not in selected:obligations.append({'code':'UNSUPPORTED_SYNTHESIS_INPUT','edge_id':edge['id']})
            continue
        if edge['to'] not in selected:
            continue
        if edge['from'] not in selected:
            obligations.append({'step_id': edge['to'], 'edge_id': edge['id'], 'code': 'OPEN_SELECTED_INPUT'})
        elif edge['kind'] != 'control':
            obligations.append({'step_id': edge['to'], 'edge_id': edge['id'], 'code': 'UNSUPPORTED_' + edge['kind'].upper()})
        else:
            deps[edge['to']].append(edge['from'])
    for sid in selected:
        step, choice = steps[sid], settings[sid]
        if step['assignment']['role'] not in {'builder', 'adversary'}:
            obligations.append({'step_id': sid, 'code': 'UNSUPPORTED_ROLE', 'role': step['assignment']['role'],
                'message': 'Authored Synthesis is retained; automatic parent-consumes does not execute its instructions/settings'})
        if not step['assignment'].get('instructions', '').strip():
            obligations.append({'step_id': sid, 'code': 'INSTRUCTION_REQUIRED'})
        for field in ('inputs', 'outputs', 'targets'):
            if step.get(field):
                obligations.append({'step_id': sid, 'code': 'UNCONSUMED_DECLARATION', 'field': field})
        if choice.get('error'):
            obligations.append({'step_id': sid, 'code': 'UNSUPPORTED_SETTINGS', 'message': choice['error']})
        if choice.get('values', {}).get('input_policy') is not None:
            obligations.append({'step_id': sid, 'code': 'UNSUPPORTED_INPUT_POLICY'})
    ordered, pending = [], list(selected)
    while pending:
        ready = next((sid for sid in pending if set(deps[sid]) <= set(ordered)), None)
        if ready is None:
            obligations.append({'code': 'UNSUPPORTED_CONTROL_CYCLE', 'step_ids': pending})
            break
        ordered.append(ready); pending.remove(ready)
    _, path = _keys(caller.namespace, payload['request_id'])
    base = path.rsplit('/', 1)[0]
    # This carrier has a different packet grammar; stable definition IDs are never renamed.
    mapping = {sid: 'step-' + hashlib.sha256(sid.encode()).hexdigest()[:40] for sid in selected}
    if len(set(mapping.values())) != len(mapping):
        raise D.Refused('PACKET_ID_COLLISION')
    packets = [];deliveries={};earlier=[]
    for sid in ordered:
        role = steps[sid]['assignment']['role']
        values = settings[sid].get('values') or {}
        brief,delivery=operations.compiled_instruction(root,caller.namespace,body,sid,prepared_by)
        deliveries[sid]=delivery
        declared = list(dict.fromkeys(mapping[value] for value in deps[sid] if value in mapping))
        packets.append({'packet': mapping[sid], 'role': 'worker' if role == 'builder' else 'judge',
            'scope': 'project', 'brief': brief,
            'return_path': base + '/' + mapping[sid] + '-return.json',
            **{key: values[key] for key in ('provider', 'model', 'effort') if values.get(key) is not None},
            # A review of only some earlier builders carries its own inputs; one of every earlier builder keeps the original packet.
            **({'depends_on': declared} if role == 'adversary' and declared and set(declared) != set(earlier) else {})})
        if role == 'builder':earlier.append(mapping[sid])
    for sid, packet in zip(ordered, packets):
        try:actual = project_work.dispatch_dependencies(packets, packet['packet'])
        except ValueError:actual = None
        intended = list(dict.fromkeys(mapping[value] for value in deps[sid]))
        if actual is None or set(actual) != set(intended):
            obligations.append({'step_id': sid, 'code': 'UNSUPPORTED_CARRIER_DEPENDENCIES',
                                'declared': intended, 'carrier': actual})
    if obligations:
        raise D.Refused('UNSUPPORTED_APP_SLICE', obligations=obligations)
    consumed_settings = {sid: {key: value for key, value in settings[sid].items() if key != 'instruction'} for sid in selected}
    pin = {'schema_version': SCHEMA, 'project': caller.namespace, 'request_id': payload['request_id'],
        'intent_digest': _digest(payload), 'reference': payload['reference'], 'step_ids': list(selected),
        'step_packets': mapping, 'settings': consumed_settings,
        'settings_digest': _digest(consumed_settings), 'prepared_by': prepared_by,
        'context_delivery':deliveries,
        **({'synthesis':synthesis} if synthesis else {}),
        'parent_contract': {'kind': 'authored-original-parent' if synthesis else 'generated-parent-consumes',
            'instructions': 'The dispatching turn reads every return through dispatch_returns and says what they establish.',
            'authored_synthesis_consumed': bool(synthesis)}}
    plan = {'schema_version': 'laplace.dispatch-plan/1', 'fan_out_max': payload['fan_out_max'],
        'goal': payload['goal'], 'packets': packets, 'synthesis_return_path': base + '/parent-return.json',
        'workflow_definition': pin}
    return plan, pin


def _artifact_rows(root, project, relative):
    try:
        path = artifacts.resolve_path(root, project, relative).relative_to(Path(root)).as_posix()
    except ValueError:
        return []  # No registered project artifact home; no app ART can be selected here.
    return [row for row in records.index(root).by_project.get(project, [])
            if row.get('record') == 'writing-artifact' and row.get('path') == path]


def _saved_artifact(root, project, row):
    return {'id': row['id'], 'revision': row['sha256'], 'path': row['path'],
            'read_handle': {'operation': 'read_artifact', 'payload': {'id': row['id']}}}


def prepare(root, caller, payload):
    D = _definitions()
    from laplace.work import project_work
    from laplace.writing import dispatch_execution
    from jsonschema import Draft202012Validator
    value = {'action': 'prepare', **payload}
    error = next(Draft202012Validator(D.native_change_contract()).iter_errors(value), None)
    if error:
        raise D.Refused('INVALID_APP_PREPARATION', error.message)
    _admit(root, caller)
    root = Path(root).resolve(); project = caller.namespace
    ident, relative = _keys(project, payload['request_id'])
    intent = _digest(payload)
    saved = None
    with project_work.dispatch_lock(root), D._lock(root):
        admitted = _admit(root, caller)
        from laplace.pipeline import workflow_operations as operations
        blocked=operations.admission_decision(root,caller,payload,'prepare')
        if blocked is not None:return blocked
        row, _, _ = D._select(D._rows(root), caller, {'reference': payload['reference']})
        if row['scope'] != {'kind': 'project', 'namespace': project} or not payload['reference'].get('version'):
            raise D.Refused('EXACT_PROJECT_VERSION_REQUIRED')
        if any(item.get('request_id') == payload['request_id'] for item in D._rows(root)):
            raise D.Refused('REQUEST_CONFLICT', 'Request already names a saved definition')
        legacy, _ = D._preparation_requests(root)
        if any(item.get('preparation_request_id') == payload['request_id'] for item in legacy):
            raise D.Refused('REQUEST_CONFLICT', 'Request already names a legacy preparation')
        prior = project_work._tasks(project, root).get(ident)
        retained = _artifact_rows(root, project, relative)
        if retained:
            artifact = retained[-1]; pin = artifact.get('reader_metadata') or {}
            if pin.get('schema_version') != SCHEMA or pin.get('intent_digest') != intent:
                raise D.Refused('REQUEST_CONFLICT', 'Preparation path/request belongs to different intent')
            # Original authority is provenance, not renewed by a recovery caller.
            if pin['prepared_by']['session_id'] != admitted['session_id']:
                raise D.Refused('ORIGINAL_PARENT_SESSION_REQUIRED')
            try:
                saved = artifacts.recover_workflow_publication(root, project, artifact['id'], artifact['sha256'], pin,
                    admit=lambda: _admit(root, caller))
                plan = json.loads(artifacts.resolve_path(root, project, relative).read_text())
                if plan.get('workflow_definition') != pin:
                    raise ValueError('Plan provenance differs from its exact retained ART metadata')
            except (ValueError, OSError) as exc:
                raise D.Refused('APP_PREPARATION_UNAVAILABLE', str(exc), effect='partial',
                    request_id=payload['request_id'], artifact=_saved_artifact(root, project, artifact),
                    recovery=D.scoped_handle(caller,facet='request', request_id=payload['request_id'])) from exc
        else:
            if prior or artifacts.resolve_path(root, project, relative).exists():
                raise D.Refused('APP_PREPARATION_UNAVAILABLE', 'Foreign or unqualified preparation object', effect='unknown')
            body = D._body(root, row)
            prepared_by = {'project': project, 'session_id': admitted['session_id'], 'turn_id': caller.turn_id}
            parent_turn = records.fold_records(root)['turns'][caller.turn_id]
            if parent_turn.get('work_id'):
                if parent_turn['work_id'] not in project_work._tasks(project, root):
                    raise D.Refused('PARENT_WORK_UNAVAILABLE')
                prepared_by['work_id'] = parent_turn['work_id']
            plan, pin = _compile(root, caller, row, body, payload, prepared_by)
            dispatch_execution.launch_dispatch(root, project, caller.turn_id,
                {'plan': plan, 'plan_path': relative}, validate_only=True)
            if pin.get('research_workflow'):
                from laplace.writing import workflow_progression
                metadata = {'schema_version':SCHEMA,'request_id':payload['request_id'],
                    'intent_digest':intent,'prepared_by':prepared_by,'publication_kind':'selected-evidence'}
                packet = workflow_progression.capture_packet(root, project, pin['research_workflow'].pop('inputs'),
                    relative.rsplit('/',1)[0]+'/inputs.json', metadata, turn_id=caller.turn_id)
                pin['research_workflow']['input_packet'] = packet
            _admit(root, caller)
            witness = {}
            try:
                saved = artifacts.store(root, project, {'path': relative, 'scope': 'project', 'before': None,
                    'content': json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=1),
                    'reason': 'Prepare exact saved workflow; no session or provider starts'}, caller.turn_id,
                    owner_metadata=pin, publication_witness=witness)
            except Exception as exc:
                raise D.Refused('APP_PREPARATION_PARTIAL', str(exc), effect='partial' if witness.get('banked') else 'unknown',
                    request_id=payload['request_id'], publication=witness,
                    recovery=D.scoped_handle(caller,facet='request', request_id=payload['request_id'])) from exc
        binding = {'artifact_id': saved['id'], 'revision': saved['revision'], 'intent_digest': intent,
                   'request_id': payload['request_id'], 'reference': payload['reference'],
                   'prepared_by': pin['prepared_by']}
        if prior:
            if prior.get('prepared_workflow') != binding or (prior.get('evidence') or [None])[0] != saved['path']:
                raise D.Refused('APP_PREPARATION_UNAVAILABLE', 'Existing Work does not match exact prepared artifact', effect='partial')
        else:
            try:
                _admit(root, caller)
                project_work.task(project, {'id': ident, 'title': 'Workflow: ' + D._body(root, row)['title'],
                    'goal': payload['goal'], 'kind': 'dispatch', 'section_ids': [], 'evidence': [saved['path']],
                    **({'review_obligations':workflow_progression_obligations(pin, D._body(root, row))} if pin.get('research_workflow') else {}),
                    **({'parent_work_id': pin['prepared_by']['work_id']} if pin['prepared_by'].get('work_id') else {}),
                    'origin': 'workflow-preparation'}, root, prepared_workflow=binding)
            except Exception as exc:
                raise D.Refused('APP_PREPARATION_PARTIAL', str(exc), effect='partial', artifact=saved,
                    request_id=payload['request_id'], recovery=D.scoped_handle(caller,facet='request', request_id=payload['request_id'])) from exc
        try:
            _admit(root, caller)
            from laplace.writing.tool_work import join_dispatch_parent
            join_dispatch_parent(root, project, project_work._tasks(project, root)[ident], pin['prepared_by'].get('work_id'))
        except Exception as exc:
            raise D.Refused('APP_PREPARATION_PARTIAL', str(exc), effect='partial', artifact=saved,
                work_id=ident, request_id=payload['request_id'], recovery=D.scoped_handle(caller,facet='request', request_id=payload['request_id'])) from exc
        return _result(root, caller, row, ident, replayed=bool(retained))


def workflow_progression_obligations(pin, body):
    """One independent review obligation per prepared writer/reviewer pair."""
    from laplace.writing.workflow_progression import research_obligations
    return research_obligations(pin['research_workflow'], body)


def _checked(root, project, work):
    binding = work['prepared_workflow']
    candidates = [item for item in records.index(root).by_id.get(binding['artifact_id'], [])
                  if item.get('record') == 'writing-artifact' and item.get('project') == project]
    record = candidates[0] if len(candidates) == 1 else None
    if not record or record['sha256'] != binding['revision'] or record.get('reader_metadata', {}).get('intent_digest') != binding['intent_digest']:
        raise ValueError('Exact prepared ART custody is unavailable')
    path, _, _, _ = artifacts.target(root, project, {'id': binding['artifact_id']})
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding['revision'] or (work.get('evidence') or [None])[0] != path.relative_to(Path(root)).as_posix():
        raise ValueError('The immutable prepared plan changed or Work names another artifact')
    plan = json.loads(raw)
    pin = plan['workflow_definition']
    if (pin != record.get('reader_metadata') or pin['reference'] != binding['reference'] or pin['prepared_by'] != binding['prepared_by']
            or work.get('parent_work_id') != pin['prepared_by'].get('work_id')):
        raise ValueError('Prepared plan provenance differs from its retained Work/ART')
    return plan, pin, _saved_artifact(root, project, record)


def admit_launch(root, project, work, parent_turn_id):
    """Deferred Start stays in its original session with fresh effect authority."""
    if not work.get('prepared_workflow'):
        return
    D = _definitions()
    plan, pin, _ = _checked(root, project, work)
    turn = records.fold_records(root)['turns'].get(parent_turn_id) or {}
    current = D.native_caller(root, project, turn.get('mode'), parent_turn_id)
    admitted = _admit(root, current)
    if admitted['session_id'] != pin['prepared_by']['session_id']:
        raise D.Refused('ORIGINAL_PARENT_SESSION_REQUIRED')
    return plan, pin


def _conversation(project, session_id, turn_id):
    return {'project': project, 'session_id': session_id, 'turn_id': turn_id,
        'project_url': '/project?' + urlencode({'workspace': 'writing', 'corpus': project, 'session': session_id, 'conversation': 'open'}),
        'session_read': {'http': {'method': 'GET', 'url': '/authoring/session?' + urlencode({'project': project, 'id': session_id, 'view': 'summary'})}},
        'public_content_read': {'http': {'method': 'GET', 'url': '/authoring/session-turn?' + urlencode({'project': project, 'id': turn_id, 'view': 'turn'})},
                                'native': {'operation': 'author_history', 'payload': {'view': 'record', 'id': 'activity:journal:' + turn_id}}},
        'controls_read': {'http': {'method': 'GET', 'url': '/authoring/session-turn?' + urlencode({'project': project, 'id': turn_id, 'view': 'controls'})}}}


def _prepared_dependencies(pin, dependencies):
    """Qualify the carrier relation through its immutable selected-step mapping."""
    result = {'status': 'UNAVAILABLE', 'edges': [], 'source': 'project_work.dispatch_view'}
    selected, mapping = pin.get('step_ids'), pin.get('step_packets')
    if (not isinstance(selected, list) or not all(isinstance(sid, str) for sid in selected)
            or len(set(selected)) != len(selected) or not isinstance(mapping, dict)
            or set(mapping) != set(selected)
            or not all(isinstance(packet, str) and packet for packet in mapping.values())
            or len(set(mapping.values())) != len(mapping)):
        return {**result, 'reason': 'Prepared step-to-packet mapping is incomplete or ambiguous.'}
    by_packet = {packet: sid for sid, packet in mapping.items()}
    if not isinstance(dependencies, dict) or set(dependencies) != set(by_packet):
        return {**result, 'reason': 'Canonical dependencies do not cover exactly the prepared packets.'}
    edges = []
    for packet, prerequisites in dependencies.items():
        if (not isinstance(prerequisites, list)
                or not all(isinstance(value, str) and value in by_packet for value in prerequisites)
                or len(set(prerequisites)) != len(prerequisites)):
            return {**result, 'reason': 'Canonical dependency endpoints are unavailable or ambiguous.'}
        edges.extend({'prerequisite_step_id': by_packet[value], 'dependent_step_id': by_packet[packet]}
                     for value in prerequisites)
    return {**result, 'status': 'AVAILABLE',
            'edges': sorted(edges, key=lambda edge: (edge['dependent_step_id'], edge['prerequisite_step_id']))}


def _reply_read(project, session_id, turn_id):
    """The issued public reply read of one exact turn (identity project/session_id/turn_id/part=reply): the same message
    handle the research run and feedback edges use. A handle only; nothing is fetched."""
    from laplace.writing import session_reads
    try:
        message = session_reads._message_handle({'project': project, 'session_id': session_id, 'turn_id': turn_id,
                                                 'part': 'reply', 'limit': 4000}, offset=0)
    except Exception:
        return None
    return {key: message[key] for key in ('identity', 'http', 'sdk') if key in message} if isinstance(message, dict) else None


def _observation_reads(caller, pin, work):
    """The existing same-scope workflow-operation reads of this exact saved version: its recorded uses and this run's
    observed river. Handles only; nothing is read here, and planned edges (prepared_dependencies) stay planned."""
    D = _definitions()
    try:
        return {'uses': D.scoped_handle(caller, facet='uses', reference=pin['reference']),
                'river': D.scoped_handle(caller, facet='river', reference=pin['reference'], work_id=work['id']),
                'meaning': 'Recorded uses and observed message flow come only from run receipts; a missing receipt is unknown, not absent.'}
    except Exception as error:
        return {'status': 'UNAVAILABLE', 'reason': str(error)[:200]}


def _parent_synthesis(root, project, work, plan, pin, observed):
    """Authored synthesis executes in the ORIGINAL parent conversation, never as a child step. Map it to that parent's
    actual state and reads (its reserved typed return and the recorded parent continuation), so it is not presented as an
    unselected step. The parent's admitted settings govern; nothing here judges or publishes the synthesis."""
    authored = pin.get('synthesis') if isinstance(pin.get('synthesis'), dict) else {}
    continuation = observed.get('parent_continuation') if isinstance(observed.get('parent_continuation'), dict) else {}
    relative = plan.get('synthesis_return_path')
    value = {'authored': bool(authored), 'consumed': bool((pin.get('parent_contract') or {}).get('authored_synthesis_consumed')),
             'kind': (pin.get('parent_contract') or {}).get('kind'), 'execution_location': 'original-parent',
             'parent_session_id': pin['prepared_by']['session_id'], 'launched_by_turn_id': work.get('dispatch_parent_turn_id'),
             'step_id': authored.get('step_id'), 'title': authored.get('title'), 'continuation_phase': continuation.get('phase'),
             'meaning': 'The original parent reads every return and publishes the typed synthesis at the reserved path; it is not a child run.'}
    if not relative:
        return {**value, 'status': 'NOT_DECLARED'}
    value.update(return_path=relative, return_read={'native': {'operation': 'read_artifact', 'payload': {'path': relative, 'scope': 'project'}}})
    if not work.get('dispatch_admitted'):
        return {**value, 'status': 'NOT_ADMITTED'}
    from laplace.writing import dispatch_parent
    try:
        state = continuation.get('synthesis') if isinstance(continuation.get('synthesis'), dict) else dispatch_parent.synthesis_view(work, project, root, view=observed)
    except Exception as error:
        state = {'status': 'UNKNOWN', 'errors': [str(error)[:300]]}
    value.update(status=state.get('status'), errors=[str(item)[:300] for item in (state.get('errors') or [])[:4]])
    for key in ('attachment', 'attach_action', 'retained_status'):
        if state.get(key) is not None:
            value[key] = state[key]
    return value


def run(root, caller, row, work, step_id=None):
    D = _definitions()
    from laplace.work import project_work
    project = row['scope']['namespace']
    plan, pin, artifact = _checked(root, project, work)
    if pin.get('research_workflow'):
        from laplace.writing.workflow_progression import view
        result = view(root, project, work['id'],door={'origin':'native','turn_id':getattr(caller,'turn_id',None)}
            if caller.door=='native' else {'origin':'human'})
        return {**result,'profile':D.APP_PROFILE,'definition_read':D.scoped_handle(caller,row['definition_id'],row['definition_revision']),
            'parent':{'prepared_by':pin['prepared_by'],'launched_by':result.get('launched_by')},
            'settings_digest':pin['settings_digest'],
            'plan':artifact,'settings_source':'PINNED_PREPARATION','read':D.scoped_handle(caller,row['definition_id'],row['definition_revision'],facet='app-run',work_id=work['id']),
            'observation_reads':_observation_reads(caller,pin,work)}
    if pin['reference'] != D.reference(row['definition_id'], row['definition_revision']):
        raise D.Refused('APP_RUN_NOT_IN_SCOPE')
    observed = project_work.dispatch_view(work, project, root)
    body = D._body(root, row)
    saved_steps = {step['id']: step for step in body['steps']}
    _, head, _ = D._select(D._rows(root), caller, {'reference': pin['reference']})
    children = {item['packet']: item for item in observed['children']}
    mapping = pin.get('step_packets') if isinstance(pin.get('step_packets'), dict) else {}
    steps = []
    for sid in pin['step_ids']:
        packet = mapping.get(sid)
        mapped = isinstance(packet, str) and bool(packet) and list(mapping.values()).count(packet) == 1
        child = children.get(packet) if mapped else None
        item = {'step_id': sid, 'title': saved_steps[sid].get('title') or sid,
                'assignment_role': saved_steps[sid]['assignment']['role'],
                'packet': packet, 'state': child['state'] if child else 'NOT_STARTED' if mapped else 'UNAVAILABLE',
                'read': D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-run', work_id=work['id'], step_id=sid)}
        if child:
            item.update({key: child[key] for key in ('session_id', 'turn_id', 'role', 'replied', 'reply_status', 'execution', 'verdict', 'return_errors')})
            if child.get('turn_id'):
                item['conversation'] = _conversation(project, child['session_id'], child['turn_id'])
                item['public_reply_read'] = _reply_read(project, child['session_id'], child['turn_id'])
                item['typed_return_read'] = {'native': {'operation': 'read_artifact', 'payload': {'path': child['return_path'], 'scope': 'project'}},
                    **({'http': artifacts.human_read(project, child['return_path'], 'project', child['return_token'])['http']}
                       if child.get('return_token') else {}),
                    'availability': 'OBSERVED' if child.get('return_token') else 'UNAVAILABLE'}
        else:
            item['binding'] = {'status': 'UNAVAILABLE', 'reason': 'No actual child turn is recorded for this packet'
                               if mapped else 'Prepared step-to-packet mapping is unavailable or ambiguous'}
        if child:
            receipt = child.get('continuation') if isinstance(child.get('continuation'), dict) else {}
            item['current_attempt'] = {'session_id': child.get('session_id'), 'turn_id': child.get('turn_id'),
                'observed': bool(child.get('turn_id')), 'request_id': receipt.get('request_id'),
                'phase': receipt.get('phase', 'RECORDED')}
            item['attempt_history'] = [{**entry, 'conversation': _conversation(project, entry['session_id'], entry['turn_id'])}
                for entry in child.get('attempt_history', []) if entry.get('session_id') and entry.get('turn_id')]
            if receipt.get('request_id'):
                from laplace.writing import dispatch_execution
                item['continuation_request'] = dispatch_execution.continuation_request(root, project, work, receipt['request_id'])
            if not child.get('turn_id'):
                item['binding'] = child.get('binding') or {'status': 'UNAVAILABLE', 'reason': 'No exact current attempt is observed'}
        retained = ((item.get('continuation_request') or {}).get('receipt') or {}).get('guard', {}).get('prerequisites', [])
        if mapped:
            item['continue_action'] = _continue_action(root, project, row, work, sid, packet)
            retained = item['continue_action']['offer'].get('reused_outputs', retained)
        item['reused_outputs'] = []
        for prerequisite in retained:
            value = dict(prerequisite)
            retained_step = next((saved_steps[sid] for sid, label in mapping.items() if label == prerequisite['packet']), {})
            value['title'] = retained_step.get('title') or prerequisite['packet']
            for kind in ('return', 'output'):
                output = dict(value[kind])
                if output.get('exists') and output.get('revision'):
                    output['read'] = {'native': {'operation': 'read_artifact', 'payload': (
                        {'id': output['id']} if output.get('id') else {'path': output['artifact_path'], 'scope': 'project'})},
                        'http': artifacts.human_read(project, output['artifact_path'], 'project', output['revision'])['http']}
                value[kind] = output
            item['reused_outputs'].append(value)
        steps.append(item)
    if step_id is not None and step_id not in pin['step_ids']:
        raise D.Refused('STEP_NOT_IN_PREPARED_SLICE')
    read = D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-run', work_id=work['id'])
    parent = {'prepared_by': pin['prepared_by'], 'launched_by': None,
        'conversation': _conversation(project, pin['prepared_by']['session_id'], pin['prepared_by']['turn_id'])}
    if work.get('dispatch_parent_turn_id'):
        parent['launched_by'] = {'turn_id': work['dispatch_parent_turn_id'], 'session_id': pin['prepared_by']['session_id']}
    cancel = None
    if work.get('dispatch_admitted'):
        from laplace.writing import dispatch_parent
        try:
            cancel = dispatch_parent.cancel_action(work, project, root)
        except Exception as error:
            cancel = {'available': False, 'permitted': False, 'reason': 'Cancel dispatched work is unavailable: ' + str(error)[:200]}
    return {'profile': D.APP_PROFILE, 'work_id': work['id'], 'request_id': pin['request_id'],
        'parent_synthesis': _parent_synthesis(root, project, work, plan, pin, observed),
        'observation_reads': _observation_reads(caller, pin, work),
        'definition_read': D.scoped_handle(caller,row['definition_id'], row['definition_revision']), 'reference': pin['reference'],
        'definition_currentness': 'CURRENT' if row['definition_revision'] == head['definition_revision'] else 'HISTORICAL',
        'plan_currentness': 'CURRENT', 'settings_source': 'PINNED_PREPARATION',
        'work': {'id': work['id'], 'project': project, 'read': project_work.read(project, {'view': 'detail', 'id': work['id']}, root)['task']['read_handle']},
        'plan': artifact, 'parent': parent, 'step_packets': pin['step_packets'], 'settings': pin['settings'],
        'settings_digest': pin['settings_digest'], 'carrier': {'profile': 'laplace.dispatch-plan/1', 'parent_contract': pin['parent_contract']},
        'observation': {'source': 'project_work.dispatch_view', 'observed_at': time.time(),
            'execution_state': observed['execution_state'], 'review_state': observed['review_state'], 'recorded_status': work['status'],
            'meaning': 'Recorded admission is separate from current child-host liveness and review evidence'},
        'deadline': {'seconds': observed.get('deadline_seconds'), 'at': work.get('dispatch_deadline_at'),
                     'exceeded': observed.get('deadline_exceeded')},
        'parent_continuation': observed.get('parent_continuation'),
        'actions': {'use_in_conversation': compose(root, caller, row, {'facet': 'app-launch-compose', 'work_id': work['id']})['action'],
                    **({'cancel_dispatch': cancel} if cancel else {})},
        'prepared_dependencies': _prepared_dependencies(pin, observed.get('dependencies')),
        'steps': steps, 'step_detail': next((item for item in steps if item['step_id'] == step_id), None), 'read': read}


def _result(root, caller, row, ident, *, replayed):
    D = _definitions()
    from laplace.work import project_work
    work = project_work._tasks(row['scope']['namespace'], root)[ident]
    binding = work['prepared_workflow']
    from laplace.work.project_work_views import handle as work_handle
    receipt = {'operation': 'prepare', 'profile': D.APP_PROFILE, 'request_id': binding['request_id'],
        'intent_digest': binding['intent_digest'], 'work_id': ident, 'artifact_id': binding['artifact_id'], 'plan_revision': binding['revision']}
    result = {'effect': 'prepared', 'status': 'NOT_STARTED' if not work.get('dispatch_admitted') else 'ALREADY_ADMITTED',
        'profile': D.APP_PROFILE, 'receipt': receipt, 'replayed': replayed, 'provider_started': False,
        'scope': row['scope'],
        'definition': {'reference': binding['reference'], 'read': D.scoped_handle(caller,row['definition_id'], row['definition_revision'])},
        'work': {'id': ident, 'project': row['scope']['namespace'],
                 'read': work_handle(row['scope']['namespace'], {'view': 'detail', 'id': ident})},
        'plan': {'id': binding['artifact_id'], 'revision': binding['revision'], 'path': (work.get('evidence') or [None])[0],
                 'read_handle': {'operation': 'read_artifact', 'payload': {'id': binding['artifact_id']}}},
        'parent': {'prepared_by': binding['prepared_by'],
                   'launched_by': {'turn_id': work['dispatch_parent_turn_id'], 'session_id': binding['prepared_by']['session_id']}
                       if work.get('dispatch_parent_turn_id') else None},
        'read': D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-run', work_id=ident)}
    parent_id = binding['prepared_by'].get('work_id')
    if parent_id and ident not in (project_work._tasks(row['scope']['namespace'], root).get(parent_id, {}).get('depends_on') or []):
        result.update(effect='partial', status='PENDING_PARENT_JOIN',
            recovery=D.scoped_handle(caller,facet='request', request_id=binding['request_id']))
    try:
        projected = run(root, caller, row, work)
        result.update(run=projected, **{key: projected[key] for key in ('work', 'plan', 'parent')})
    except Exception as exc:
        result['observation'] = {'status': 'UNAVAILABLE', 'error': str(exc)}
    return result


def inspect_request(root, caller, request_id):
    D = _definitions()
    from laplace.work import project_work
    projects = [caller.namespace] if caller.kind == 'project' else sorted({row['scope'].get('namespace') for row in D._rows(root) if row['scope']['kind'] == 'project'})
    matches = []
    for project in projects:
        ident, relative = _keys(project, request_id)
        work = project_work._tasks(project, root).get(ident)
        retained = _artifact_rows(root, project, relative)
        pin = (work or {}).get('prepared_workflow') or ((retained[-1].get('reader_metadata') or {}) if retained else {})
        if not pin:
            continue
        try:
            row, _, _ = D._select(D._rows(root), caller, {'reference': pin['reference']})
            if work and work.get('prepared_workflow'):
                result = _result(root, caller, row, ident, replayed=True)
                matches.append({**result, 'status': 'RECORDED' if result['effect'] == 'prepared' else 'PARTIAL', 'execution_status': result['status']})
                continue
            matches.append({'status': 'PARTIAL', 'effect': 'partial', 'profile': D.APP_PROFILE,
                'request_id': request_id, 'artifact': _saved_artifact(root, project, retained[-1]),
                'definition_read': D.scoped_handle(caller,row['definition_id'], row['definition_revision']),
                'message': 'Retain original request/content; explicit same-request Prepare may recover its exact ART and Work'})
        except (ValueError, OSError, KeyError) as exc:
            matches.append({'status': 'UNAVAILABLE', 'effect': 'unknown', 'profile': D.APP_PROFILE,
                    'request_id': request_id, 'message': str(exc)})
    return D.request_resolution(request_id, matches) if matches else None


def read(root, caller, row, payload):
    D = _definitions()
    from laplace.work import project_work
    if row['scope']['kind'] != 'project':
        raise D.Refused('APP_RUN_NOT_IN_SCOPE')
    project = row['scope']['namespace']; tasks = project_work._tasks(project, root)
    if payload['facet'] in {'app-compose', 'app-launch-compose', 'app-continue-compose'}:
        return compose(root, caller, row, payload)
    expected = D.reference(row['definition_id'], row['definition_revision'])
    if payload['facet'] == 'app-run':
        work = tasks.get(payload.get('work_id')) or {}
        if (work.get('prepared_workflow') or {}).get('reference') != expected:
            raise D.Refused('APP_RUN_NOT_IN_SCOPE')
        return run(root, caller, row, work, payload.get('step_id'))
    offset, limit = payload.get('offset', 0), payload.get('limit', 20)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 20:
        raise D.Refused('INVALID_PAGE')
    matches = [work for work in tasks.values() if (work.get('prepared_workflow') or {}).get('reference') == expected]
    items = [{'work_id': work['id'], 'request_id': work['prepared_workflow']['request_id'],
        'recorded_status': work['status'], 'read': D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-run', work_id=work['id']),
        'river_read': D.scoped_handle(caller, facet='river', reference=expected, work_id=work['id'])}
        for work in matches[offset:offset+limit]]
    return {'profile': D.APP_PROFILE, 'reference': expected, 'definition_read': D.scoped_handle(caller,row['definition_id'], row['definition_revision']),
        'uses_read': D.scoped_handle(caller, facet='uses', reference=expected),
        'items': items, 'total': len(matches), 'offset': offset,
        'next': D.scoped_handle(caller,row['definition_id'], row['definition_revision'], facet='app-runs', offset=offset+limit, limit=limit)
            if offset+limit < len(matches) else None}
