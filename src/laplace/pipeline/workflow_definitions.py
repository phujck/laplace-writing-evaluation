"""Reusable definitions owned by pipeline.workflow, in its existing ledger/body custody.

The trusted adapter supplies Scope. Save records immutable drafts, Prepare compiles a
supported selected slice into the existing carrier, and neither starts a provider.
Definition edit guards, consumed settings and exact historical versions are distinct.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import urlencode
import uuid

from filelock import FileLock
from laplace.core import identity, checkout
from laplace.pipeline import workflow as W
from laplace.representation import writing_bodies
from laplace.work import owner_discovery as O

SCHEMA = 'laplace.workflow-definition/1'
RECORD = 'workflow-definition'
OWNER = 'pipeline.workflow'
MAX_BODY = 200_000
LOCAL_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z')


def local_id_schema_pattern():
    """LOCAL_ID as an anchored JSON-schema pattern, for contracts that name a step by its id."""
    return '^' + LOCAL_ID.pattern.removesuffix('\\Z') + '$'

SETTINGS = {'provider', 'model', 'effort', 'input_policy'}
APP_PROFILE = 'laplace.app-dispatch/1'
RESEARCH_POLICY = 'laplace.research-review/1'
RESEARCH_POLICY_V2 = 'laplace.research-review/2'


def run_policy_contract():
    legacy={'type': 'object', 'additionalProperties': False,
        'required': ['profile', 'max_iterations', 'runtime_seconds', 'advance', 'apply'],
        'properties': {'profile': {'const': RESEARCH_POLICY},
            'max_iterations': {'type': 'integer', 'minimum': 1, 'maximum': 3},
            'runtime_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 3600},
            'advance': {'enum': ['automatic-review', 'manual']}, 'apply': {'const': 'human'}}}
    extended=copy.deepcopy(legacy)
    extended['properties']['profile']={'const':RESEARCH_POLICY_V2}
    # Exact JSON integer transport, not an unexplained new iteration ceiling.
    extended['properties']['max_iterations']={'type':'integer','minimum':1,'maximum':2**53-1}
    extended['properties'].update(max_admissions={'type':'integer','minimum':2,'maximum':2**53-1},
        deadline_seconds={'type':'integer','minimum':1,'maximum':2**53-1},
        continuation_criteria={'type':'string','minLength':1,'maxLength':4000},
        exit_criteria={'type':'string','minLength':1,'maxLength':4000})
    extended['required']+=['max_admissions','deadline_seconds','continuation_criteria','exit_criteria']
    return {'oneOf':[legacy,extended]}


def starter_definition():
    """A new, unsaved author choice; never migrate existing authored definitions."""
    return {'schema_version': SCHEMA, 'title': 'Draft, independent review, human Apply',
        'description': 'Develop a proposal from explicitly selected evidence; review independently and retain every attempt. A person applies the manuscript revision.',
        'settings': {}, 'run_policy': {'profile': RESEARCH_POLICY, 'max_iterations': 2,
            'runtime_seconds': 300, 'advance': 'automatic-review', 'apply': 'human'},
        'steps': [{'id': 'write', 'title': 'Draft proposal', 'assignment': {'role': 'builder',
            'instructions': 'Read the selected manuscript and evidence packet. Return a source-addressed edit proposal; do not apply changes.', 'settings': {}}},
            {'id': 'review', 'title': 'Independent evidence review', 'assignment': {'role': 'adversary',
            'instructions': 'Independently assess the exact proposal and selected evidence. Return a JSON object with verdict ACCEPT or REVISE and findings. State input limitations; this is evidence-informed review, not blind review.',
            'settings': {'input_policy': 'evidence-packet'}}}],
        'edges': [{'id': 'draft-review', 'from': 'write', 'to': 'review', 'kind': 'control'},
                  {'id': 'review-revision', 'from': 'review', 'to': 'write', 'kind': 'feedback'}]}


class Refused(ValueError):
    def __init__(self, code, message='', **facts):
        super().__init__(code + (': ' + message if message else ''))
        self.details = {'code': code, **copy.deepcopy(facts)}


@dataclass(frozen=True)
class _NativeCaller(O.Scope):
    mode: str = ''
    turn_id: str | None = None
    admission: dict | None = None


def native_caller(root, project, mode, turn_id):
    """Trusted native adapter context; request JSON cannot construct this authority."""
    from laplace.writing.turn_admission import native_write_admission
    return _NativeCaller('project', 'native', project, mode, turn_id,
                         native_write_admission(root, project, mode, turn_id))


def _can_save(caller):
    return caller.door != 'native' or (isinstance(caller, _NativeCaller) and bool((caller.admission or {}).get('permitted')))


def _admit_save(root, caller):
    if caller.door != 'native':
        return
    fresh = native_caller(root, caller.namespace, caller.mode, caller.turn_id) if isinstance(caller, _NativeCaller) else caller
    if not _can_save(fresh):
        raise Refused('NATIVE_WRITE_NOT_ADMITTED', admission=getattr(fresh, 'admission', None), next_reads=[handle()])


def native_save_contract():
    """One native Save shape. The full definition's semantic validator remains validate()."""
    return {'type': 'object', 'required': ['action', 'request_id', 'expected_revision', 'definition'],
            'properties': {'action': {'const': 'save'}, 'request_id': {'type': 'string', 'minLength': 1, 'maxLength': 120},
                           'definition_id': {'type': 'string'}, 'expected_revision': {'type': ['string', 'null']},
                           'definition': {'type': 'object'}, 'scope': {'type': 'object'}, 'derived_from': {'type': 'object'}},
            'additionalProperties': False}


def native_error_details(error):
    return _copy(error.details) if isinstance(error, Refused) else {}


def native_change_contract():
    """Save and app preparation share the definition owner; execution is another act."""
    prepare = {'type': 'object', 'additionalProperties': False,
        'required': ['action', 'profile', 'request_id', 'reference', 'step_ids', 'goal', 'fan_out_max'],
        'properties': {'action': {'const': 'prepare'}, 'profile': {'const': APP_PROFILE},
            'request_id': {'type': 'string', 'minLength': 1, 'maxLength': 120},
            'reference': {'type': 'object'},
            'step_ids': {'type': 'array', 'minItems': 2, 'maxItems': 8, 'uniqueItems': True,
                         'items': {'type': 'string'}},
            'goal': {'type': 'string', 'minLength': 1, 'maxLength': 2000},
            'fan_out_max': {'type': 'integer', 'minimum': 1, 'maximum': 8},
            'inputs': {'type': 'array', 'maxItems': 24, 'items': {'type': 'object'}},
            'selection': {'type': 'object'}}}
    from laplace.pipeline.workflow_operations import withdraw_contract
    return {'oneOf': [native_save_contract(), prepare, withdraw_contract()]}


def _copy(value):
    return json.loads(W.canonical(value))


def _root(root):
    return Path(root).resolve()


def _lock(root):
    path = _root(root) / 'contract' / 'workflow-definitions.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(path), timeout=20)


def _scope(scope):
    if scope == {'kind': 'owned-workspace'}:
        return scope
    if isinstance(scope, dict) and set(scope) == {'kind', 'namespace'} and scope['kind'] == 'project' and isinstance(scope['namespace'], str) and scope['namespace']:
        return scope
    raise Refused('INVALID_SCOPE')


def _admits(caller, scope):
    return caller.kind == 'owned-workspace' or scope == {'kind': 'project', 'namespace': caller.namespace}


def _scope_id(root, caller):
    return identity.canonical_digest({'root': str(_root(root)), 'kind': caller.kind, 'namespace': caller.namespace})


def reference(ident, version=None):
    return identity.reference(OWNER, 'workflow-definition', {'id': ident},
                              version={'definition_revision': version} if version else None)


def handle(ident=None, version=None, **extra):
    payload = {**({'definition_id': ident} if ident else {}), **({'version': version} if version else {}), **extra}
    # One canonical issued URI per meaning: structured values (a reference, step ids) are serialised with sorted keys, so a
    # reference loaded from a pin and one built by the factory issue the same HTTP read. The request payload is unchanged.
    query = {key: json.dumps(value, separators=(',', ':'), sort_keys=True) if isinstance(value, (list, dict)) else value for key, value in payload.items()}
    url = '/work/workflow-definitions' + ('?' + urlencode(query) if query else '')
    return {'http': {'method': 'GET', 'url': url}, 'request': payload,
            'native': {'operation': 'project', 'payload': {'view': 'workflow-definitions', 'request': payload}}}


def scoped_handle(caller, ident=None, version=None, **extra):
    """Retain a narrowed library context without changing definition custody."""
    if caller.kind=='project':extra={**extra,'project_lens':caller.namespace}
    return handle(ident,version,**extra)


def _rows(root):
    path = _root(root) / W.LEDGER
    if not path.exists():
        return []
    result = []
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line, object_pairs_hook=W._unique)
            if row.get('record') == RECORD:
                result.append(row)
    return result


CANDIDATE_LIMIT = 64


def _candidates(root):
    """A bounded best-effort read, never a global completeness gate for definitions."""
    result, failures, inspected, limited = [], [], 0, False
    paths = (_root(root) / 'evidence' / 'WORKFLOWS').glob('WORKFLOW-*/run.json')
    for run_file in paths:
        if inspected >= CANDIDATE_LIMIT:
            limited = True
            break
        inspected += 1
        try:
            candidate = W._load(run_file)
            if not isinstance(candidate, dict):
                raise ValueError('manifest is not an object')
            rid = candidate.get('preparation_request_id')
            if rid is None:
                continue  # Ordinary legacy run, not a definition preparation request.
            pin = candidate.get('definition_pin')
            if candidate.get('schema_version') != W.SPEC_SCHEMA or not isinstance(rid, str) or not rid or len(rid) > 120 or not isinstance(pin, dict) or not isinstance(pin.get('definition_id'), str) or not re.fullmatch(r'WDEF-[0-9a-f]{32}', pin['definition_id']) or not isinstance(pin.get('definition_revision'), str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', pin['definition_revision']) or not isinstance(candidate.get('preparation_intent_digest'), str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', candidate['preparation_intent_digest']):
                raise ValueError('unsupported preparation candidate metadata')
            result.append((run_file.parent, candidate))
        except (OSError, ValueError, W.WorkflowRefused) as exc:
            if len(failures) < 8:
                failures.append({'run_path': str(run_file.parent.relative_to(_root(root))), 'reason': type(exc).__name__})
    coverage = {'status': 'PARTIAL' if failures or limited else 'COMPLETE', 'candidate_limit': CANDIDATE_LIMIT,
                'inspected': inspected, 'unavailable': failures, 'remaining': 'UNKNOWN' if limited else 'none omitted',
                'meaning': 'Candidate recovery coverage is not proof of no prior effect'}
    return result, coverage


def _public_coverage(caller, coverage):
    if caller.kind == 'owned-workspace':
        return _copy(coverage)
    # Even an unavailable filename/count could disclose a foreign/private run.
    return {'status': 'LIMITED', 'meaning': 'Only admitted request matches are disclosed; no workspace candidate coverage claim'}


def _preparation_requests(root):
    """Existing typed declarations and readable candidates reserve request identity."""
    path = _root(root) / W.LEDGER
    result = []
    if path.exists():
        with path.open(encoding='utf-8') as stream:
            result = [row for line in stream if line.strip() for row in [json.loads(line)]
                      if row.get('record') == 'workflow' and row.get('phase') == 'declared' and row.get('preparation_request_id')]
    candidates, coverage = _candidates(root)
    result.extend(candidate for _, candidate in candidates)
    return result, coverage


def _valid_definition_record(row):
    required = {'record', 'definition_id', 'previous_revision', 'scope', 'request_id', 'intent_digest',
                'derived_from', 'definition_revision', 'body_handle', 'receipt'}
    if not isinstance(row, dict) or not required <= set(row) or set(row) - required - {'ts', 'ts_claimed'}:
        raise Refused('INVALID_EXPORT_RECORD')
    if row['record'] != RECORD or not isinstance(row['definition_id'], str) or not re.fullmatch(r'WDEF-[0-9a-f]{32}', row['definition_id']):
        raise Refused('INVALID_EXPORT_RECORD')
    _scope(row['scope'])
    _request({'request_id': row['request_id']}, {'request_id'})
    for key in ('definition_revision', 'body_handle', 'intent_digest'):
        if not isinstance(row[key], str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', row[key]):
            raise Refused('INVALID_EXPORT_RECORD')
    if row['previous_revision'] is not None and (not isinstance(row['previous_revision'], str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', row['previous_revision'])):
        raise Refused('INVALID_EXPORT_RECORD')
    expected = {'operation': 'save', 'request_id': row['request_id'], 'definition_id': row['definition_id'],
                'definition_revision': row['definition_revision'], 'body_handle': row['body_handle']}
    if row['receipt'] != expected:
        raise Refused('INVALID_EXPORT_RECEIPT')
    ref = row['derived_from']
    if ref is not None and (identity.reference_problems(ref) or ref.get('owner') != OWNER or ref.get('kind') != 'workflow-definition' or set(ref.get('identity', {})) != {'id'} or set(ref.get('version', {})) != {'definition_revision'}):
        raise Refused('INVALID_EXPORT_DERIVATION')
    for key in ('ts', 'ts_claimed'):
        if key in row and not isinstance(row[key], str):
            raise Refused('INVALID_EXPORT_RECORD')


def _body(root, row, *, with_raw=False):
    from laplace.representation.writing_representation import BodyMissing, BodyHashMismatch
    try:
        raw = writing_bodies.store(_root(root)).get(row['body_handle'], max_bytes=MAX_BODY)
        body = json.loads(raw)
        if W.digest(raw) != row['body_handle'] or W.digest(W.canonical(_revision_payload(row, body))) != row['definition_revision']:
            raise ValueError('definition revision mismatch')
        validate(body)
        return (body,raw) if with_raw else body
    except (OSError, ValueError, KeyError, BodyMissing, BodyHashMismatch) as exc:
        raise Refused('UNAVAILABLE_VERSION', 'Exact saved body is unavailable or corrupt') from exc


def _revision_payload(row, body):
    return {'definition_id': row['definition_id'], 'previous_revision': row.get('previous_revision'),
            'scope': row['scope'], 'definition': body, 'derived_from': row.get('derived_from')}


def _selector(payload, *, strict=False):
    ident, version = payload.get('definition_id'), payload.get('version')
    if 'reference' in payload:
        ref = payload['reference']
        if identity.reference_problems(ref) or ref.get('owner') != OWNER or ref.get('kind') != 'workflow-definition' or set(ref.get('identity', {})) != {'id'}:
            raise Refused('UNSUPPORTED_REFERENCE')
        declared = ref.get('version', {})
        if declared and set(declared) != {'definition_revision'}:
            raise Refused('UNSUPPORTED_VERSION')
        if ident is not None and ident != ref['identity']['id'] or version is not None and version != declared.get('definition_revision'):
            raise Refused('CONFLICTING_REFERENCE')
        ident, version = ref['identity']['id'], declared.get('definition_revision')
    if strict and (not isinstance(ident,str) or not re.fullmatch(r'WDEF-[0-9a-f]{32}',ident)
            or version is not None and (not isinstance(version,str) or not re.fullmatch(r'sha256:[0-9a-f]{64}',version))):
        raise Refused('UNSUPPORTED_REFERENCE')
    return ident,version


def _select(rows, caller, payload):
    ident,version=_selector(payload)
    available = [row for row in rows if row['definition_id'] == ident and _admits(caller, row['scope'])]
    if not available:
        raise Refused('NOT_IN_SCOPE', 'Definition is absent or outside the admitted scope')
    selected = next((row for row in reversed(available) if row['definition_revision'] == version), None) if version else available[-1]
    if selected is None:
        raise Refused('UNAVAILABLE_VERSION', 'Requested version is not available; current was not substituted')
    return selected, available[-1], available


def _settings(value):
    if not isinstance(value, dict) or set(value) - SETTINGS:
        raise Refused('INVALID_SETTINGS')
    if any(not isinstance(v, str) or not v.strip() or len(v) > 8000 for v in value.values()):
        raise Refused('INVALID_SETTINGS', 'Omit an unset key; explicit values are nonempty text')
    if 'provider' in value and value['provider'] not in {'codex', 'claude'}:
        raise Refused('INVALID_PROVIDER')
    if 'effort' in value and value['effort'] not in {'low', 'medium', 'high', 'xhigh', 'max', 'ultra'}:
        raise Refused('INVALID_EFFORT')


def validate(body):
    if not isinstance(body, dict) or body.get('schema_version') != SCHEMA:
        raise Refused('UNSUPPORTED_SCHEMA')
    if set(body) - {'schema_version', 'title', 'description', 'settings', 'layout', 'steps', 'edges', 'run_policy'}:
        raise Refused('UNKNOWN_DEFINITION_FIELD')
    if 'run_policy' in body:
        from jsonschema import Draft202012Validator
        error = next(Draft202012Validator(run_policy_contract()).iter_errors(body['run_policy']), None)
        if error:
            raise Refused('INVALID_RUN_POLICY', error.message)
    if not isinstance(body.get('title'), str) or not body['title'].strip() or len(body['title']) > 400:
        raise Refused('TITLE_REQUIRED')
    if not isinstance(body.get('description', ''), str) or not isinstance(body.get('layout', {}), dict):
        raise Refused('INVALID_DESCRIPTION_OR_LAYOUT')
    _settings(body.get('settings', {}))
    steps, edges = body.get('steps'), body.get('edges', [])
    if not isinstance(steps, list) or len(steps) > 64 or not isinstance(edges, list) or len(edges) > 256:
        raise Refused('DEFINITION_BOUND', 'At most64steps and256edges')
    by_id = {}
    for step in steps:
        if not isinstance(step, dict) or set(step) - {'id', 'title', 'parent_id', 'assignment', 'targets', 'inputs', 'outputs'}:
            raise Refused('INVALID_STEP')
        sid = step.get('id')
        if not isinstance(sid, str) or not LOCAL_ID.fullmatch(sid) or sid in by_id:
            raise Refused('STEP_ID_INVALID_OR_DUPLICATE')
        if not isinstance(step.get('title', ''), str):
            raise Refused('INVALID_STEP_TITLE')
        assignment = step.get('assignment')
        if not isinstance(assignment, dict) or set(assignment) - {'role', 'instructions', 'settings', 'context', 'handoff'}:
            raise Refused('INVALID_ASSIGNMENT')
        if not isinstance(assignment.get('role'), str) or not isinstance(assignment.get('instructions', ''), str):
            raise Refused('INVALID_ASSIGNMENT')
        _settings(assignment.get('settings', {}))
        for key in ('targets', 'inputs', 'outputs'):
            if not isinstance(step.get(key, []), list) or len(step.get(key, [])) > 64:
                raise Refused('INVALID_STEP_REFERENCES')
            if key in {'inputs', 'outputs'} and any(not isinstance(item, (str, dict)) for item in step.get(key, [])):
                raise Refused('INVALID_STEP_REFERENCES')
        by_id[sid] = step
    for step in steps:
        path, sid = set(), step['id']
        while sid is not None:
            if sid in path:
                raise Refused('CONTAINMENT_CYCLE')
            if sid not in by_id:
                raise Refused('CONTAINMENT_PARENT_MISSING')
            path.add(sid)
            sid = by_id[sid].get('parent_id')
    seen = set()
    for edge in edges:
        if not isinstance(edge, dict) or set(edge) != {'id', 'from', 'to', 'kind'}:
            raise Refused('INVALID_EDGE')
        if not isinstance(edge['id'], str) or not LOCAL_ID.fullmatch(edge['id']) or edge['id'] in seen or edge['from'] not in by_id or edge['to'] not in by_id or edge['kind'] not in {'control', 'feedback', 'data'}:
            raise Refused('INVALID_EDGE')
        seen.add(edge['id'])
    from laplace.pipeline.workflow_operations import validate_declarations
    validate_declarations(body)
    if len(W.canonical(body)) > MAX_BODY:
        raise Refused('DEFINITION_BODY_TOO_LARGE')
    return by_id


def resolve_settings(root, caller, body, *, edit_revision=None):
    """Only declared nesting is inheritance. Full instructions are local, never concatenated."""
    from laplace.writing import provider_catalogue as catalogue
    from laplace.work.project_work import resolve_session_settings
    providers = catalogue.provider_catalogue(_root(root))
    rows = {row['id']: row for row in providers['providers']}
    steps = {step['id']: step for step in body['steps']}
    result = {}
    for sid, step in steps.items():
        path, parent = [], step
        while parent is not None:
            path.append(parent)
            parent = steps.get(parent.get('parent_id'))
        values = dict(body.get('settings', {}))
        origins = {key: 'definition' for key in values}
        for ancestor in reversed(path):
            for key, value in ancestor['assignment'].get('settings', {}).items():
                values[key], origins[key] = value, 'assignment:' + ancestor['id']
        declarations = [('definition', body.get('settings', {}))] + [
            ('assignment:' + ancestor['id'], ancestor['assignment'].get('settings', {})) for ancestor in reversed(path)]
        provider = values.get('provider', 'codex')
        role = 'judge' if step['assignment']['role'] == 'adversary' else 'worker'
        try:
            effective = resolve_session_settings(rows.get(provider, {'id': provider, 'models': []}), values, role=role, strict=False)
            effective = {key: effective[key] for key in ('provider', 'model', 'effort')}
            effective['input_policy'] = values.get('input_policy')
            facts = {key: {'value': value, 'origin': origins.get(key, 'worker-tier-default' if key != 'input_policy' else 'unset'),
                           'editable': _can_save(caller), 'authority_ceiling': caller.public(),
                           'admitted_override': 'definition settings only; no execution/source/tool grant'} for key, value in effective.items()}
            for key, fact in facts.items():
                declared = [{'origin': name, 'value': item[key], 'definition_revision': edit_revision,
                             'kind': 'declared', 'selected': name == origins.get(key)}
                            for name, item in declarations if key in item]
                fact['lineage'] = declared or [{'origin': fact['origin'], 'value': fact['value'],
                    'kind': 'resolved-role-default' if key != 'input_policy' else 'unset',
                    'definition_revision': edit_revision, 'selected': True}]
                winner = next((item for item in reversed(fact['lineage']) if item['selected']), None)
                if winner and winner['value'] != fact['value']:
                    winner['selected'] = False
                    fact['lineage'].append({'origin': 'existing-session-resolver', 'kind': 'normalization',
                        'value': fact['value'], 'selected': True,
                        'meaning': 'Existing provider alias/effort capability normalization; not another default resolver'})
                fact['application_boundary'] = 'next preparation; never changes an admitted attempt'
                fact['observation'] = 'definition-resolution; actual sent settings are separate turn facts'
            result[sid] = {'values': effective, **facts, 'origin': origins,
                           'instruction': {'value': step['assignment'].get('instructions', ''), 'origin': 'assignment:' + sid,
                                           'composition': 'local exact text; group instructions are not implicitly concatenated',
                                           'lineage': [{'origin': 'assignment:' + sid, 'definition_revision': edit_revision,
                                               'selected': True, 'kind': 'declared-local'}],
                                           'application_boundary': 'next preparation'},
                           'consumed_settings_digest': W.digest(W.canonical(effective)), 'edit_guard': edit_revision,
                           'unavailable_scopes': ['global/subsystem policy mutation', 'project conversation preferences (not consumed by workers)']}
        except ValueError as exc:
            result[sid] = {'error': str(exc), 'edit_guard': edit_revision, 'values': values,
                           'consumed_settings_digest': None}
        result[sid]['title'] = step.get('title') or sid
    return result, providers


def _targets(root, caller, body, *, enforce_current=False, selected=None):
    obligations = []
    for step in body['steps']:
        if selected is not None and step['id'] not in selected:
            continue
        for target in step.get('targets', []):
            ref = target.get('reference') if isinstance(target, dict) else None
            mode = target.get('mode', 'historical') if isinstance(target, dict) else 'historical'
            try:
                if mode not in {'historical', 'current-action'} or ref is None:
                    raise ValueError('Target requires reference and historical/current-action mode')
                if mode == 'historical':
                    raise ValueError('Historical target execution is not supported by this profile; exact declaration retained')
                if not ref.get('version'):
                    raise ValueError('Current-action target requires exact requested version')
                O.admit_reference(root, caller, ref)
            except (O.DiscoveryRefusal, ValueError) as exc:
                code = getattr(exc, 'details', {}).get('code', 'UNRESOLVED_TARGET')
                if enforce_current and code == 'STALE_VERSION':
                    raise Refused('STALE_TARGET', str(exc)) from exc
                obligations.append({'step_id': step['id'], 'code': code, 'message': str(exc), 'target': _copy(target)})
    return obligations


def _action(operation, payload, caller):
    if operation=='save' and caller.kind=='project' and not payload.get('definition_id'):
        payload={**payload,'scope':{'kind':'project','namespace':caller.namespace}}
    available = caller.door != 'native' or operation == 'save'
    permitted = _can_save(caller) if operation == 'save' else caller.door != 'native'
    reason = '' if permitted else ('Native Save requires a current admitted author turn in this project'
                                   if operation == 'save' else 'Native preparation is unavailable; saving never prepares or starts a run')
    result = {'available': available, 'permitted': permitted, 'reason': reason,
              'http': {'method': 'POST', 'url': '/work/workflow-definitions/' + operation+
                  ('?'+urlencode({'project_lens':caller.namespace}) if caller.kind=='project' else '')}, 'payload': _copy(payload)}
    if caller.door == 'native' and operation == 'save':
        result['native'] = {'operation': 'workflow_definition_change', 'payload': {'action': 'save', **_copy(payload)}}
        result['admission'] = _copy(getattr(caller, 'admission', None) or {'permitted': False, 'code': 'NATIVE_ADMISSION_REQUIRED'})
    if operation in {'save','prepare'}:
        from laplace.pipeline.workflow_operations import withdrawal_offer
        result['withdrawal']=withdrawal_offer(operation,caller)
    return result


def _pins(root, ident):
    path = _root(root) / W.LEDGER
    pins = []
    if path.exists():
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                pin = row.get('definition_pin')
                if row.get('record') == 'workflow' and row.get('phase') == 'declared' and isinstance(pin, dict) and pin.get('definition_id') == ident:
                    # Declaration alone is preparation evidence, never a running claim.
                    pins.append({'run_id': row['id'], 'run_path': row['run_path'], 'definition_pin': pin,
                                 'status': 'DECLARED', 'activity': 'UNKNOWN; inspect existing run owner'})
    return pins


def capture_export(root, caller, reference_, *, max_rows=None, max_bytes=None, read_context=None, transfer_project=None):
    """Private selected raw-row custody plus unchanged public export package."""
    from laplace.pipeline import workflow_definition_records as records
    return records.export(root,caller,reference_,max_rows=max_rows,max_bytes=max_bytes,transfer_project=transfer_project)


def _capture_stats(root):
    from laplace.pipeline import workflow_definition_records as records
    return records.stats(root)


def _view(root, caller, row, head, history, *, captured=None):
    from laplace.writing import workflow_dispatch
    from laplace.pipeline import workflow_definition_records as records
    body = _body(root, row) if captured is None else records.body(captured,row)
    settings, providers = resolve_settings(root, caller, body, edit_revision=row['definition_revision'])
    version, ident = row['definition_revision'], row['definition_id']
    current = version == head['definition_revision']
    obligations = _targets(root, caller, body)
    obligations.extend({'step_id': step['id'], 'code': 'INSTRUCTION_REQUIRED_FOR_PREPARE'} for step in body['steps']
                       if step['assignment']['role'] != 'group' and not step['assignment'].get('instructions', '').strip())
    obligations.extend({'step_id': step['id'], 'code': 'INPUT_OUTPUT_DECLARATION_UNCOMPILED',
                        'field': key, 'message': 'Declaration retained; this profile has no executable binding'}
                       for step in body['steps'] for key in ('inputs', 'outputs') if step.get(key))
    read_handle = scoped_handle(caller,ident, version)
    app_actions = workflow_dispatch.actions(root, caller, row)
    return {'schema_version': SCHEMA, 'definition_id': ident, 'version': version, 'edit_revision': row['definition_revision'], 'head_revision': head['definition_revision'],
            'reference': reference(ident, version), 'definition': body, 'scope': _copy(row['scope']), 'scope_id': _scope_id(root, caller),
            'currentness': 'CURRENT' if current else 'HISTORICAL', 'is_current': current,
            'read': read_handle, 'read_handle': read_handle, 'current_read_handle': scoped_handle(caller,ident),
            'effective_settings': settings, 'providers': providers, 'obligations': obligations,
            'permissions': {'scope': caller.public(), 'save': _can_save(caller), 'prepare': caller.door != 'native',
                            'app_prepare': app_actions['app_prepare']['permitted'],
                            'start': False, 'reason': 'Definition role labels grant no execution, source or tool authority'},
            'pins': {'saved': reference(ident, version), 'prepared': _pins(root, ident) if captured is None else records.pins(captured), 'running': 'UNKNOWN; existing run owner'},
            'history': [{'version': h['definition_revision'], 'read': scoped_handle(caller,ident, h['definition_revision'])} for h in reversed(history[-32:])],
            'history_read':scoped_handle(caller,ident,head['definition_revision'],facet='history-page',selected_version=version),
            'lineage_read':scoped_handle(caller,ident,version,facet='lineage'),
            # Recorded agent runs exist only for project-owned designs (workflow_dispatch.actions uses the same test);
            # a reusable workspace design is offered no project-only read, and the app-run guard is unchanged.
            'app_runs_read': scoped_handle(caller,ident, version, facet='app-runs') if row['scope']['kind'] == 'project' else None,
            'execution_preview_read':scoped_handle(caller,ident,version,facet='execution-preview'),
            'uses_read':scoped_handle(caller,ident,version,facet='uses'),
            'actions': {'save': _action('save', {'definition_id': ident, 'expected_revision': row['definition_revision']}, caller),
                        'prepare': _action('prepare', {'reference': reference(ident, version), 'profile': W.SPEC_SCHEMA}, caller),
                        **app_actions},
            'derived_from': row.get('derived_from')}


def read(root, caller, payload=None):
    payload = _copy(payload or {})
    if payload.get('facet') in {'history-page','lineage','lineage-page','saved-version'} and not isinstance(caller,O.Scope):raise Refused('NOT_IN_SCOPE')
    lens=payload.pop('project_lens',None)
    if lens is not None and (caller.kind!='project' or lens!=caller.namespace):
        raise Refused('PROJECT_LENS_NOT_IN_SCOPE')
    from laplace.pipeline import workflow_operations as operations
    if payload.get('facet') in operations.FACETS:
        return operations.read(root,caller,payload)
    from laplace.pipeline import workflow_definition_history as history_reads
    if payload.get('facet') in history_reads.FACETS:
        return history_reads.read(root,caller,payload)
    allowed = {'definition_id', 'version', 'reference', 'facet', 'offset', 'limit', 'request_id', 'work_id', 'step_id',
               'step_ids', 'goal', 'fan_out_max', 'expected_action_basis', 'inputs', 'selection'}
    if set(payload) - allowed:
        raise Refused('UNKNOWN_READ_FIELD')
    if any(key in payload for key in ('inputs', 'selection')) and payload.get('facet') != 'app-compose':
        raise Refused('PREPARATION_INPUTS_ONLY_ON_COMPOSE')
    if 'expected_action_basis' in payload and payload.get('facet') != 'app-continue-compose':
        raise Refused('ACTION_BASIS_ONLY_ON_CONTINUATION')
    exact=('definition_id' in payload or 'reference' in payload) and payload.get('facet') not in {'starters','request'}
    rows=[] if exact else _rows(root)
    if payload.get('facet') == 'starters':
        return {'schema_version': SCHEMA, 'scope': caller.public(), 'starters': [starter_definition()],
                'read': scoped_handle(caller,facet='starters'),
                'meaning': 'Unsaved templates only; author Save and separate execution approval remain required.'}
    if payload.get('facet') == 'request':
        return _recover_request(root, caller, payload, rows)
    if 'request_id' in payload and payload.get('facet') not in {'app-compose', 'app-continue-compose'}:
        raise Refused('REQUEST_ID_ONLY_ON_RECOVERY')
    if 'definition_id' not in payload and 'reference' not in payload:
        latest = {}
        for row in rows:
            if _admits(caller, row['scope']):
                latest[row['definition_id']] = row
        offset, limit = payload.get('offset', 0), payload.get('limit', 20)
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 50:
            raise Refused('INVALID_PAGE')
        items = list(latest.values())
        _, providers = resolve_settings(root, caller, {'steps': [], 'settings': {}})
        return {'schema_version': SCHEMA, 'scope': caller.public(), 'scope_id': _scope_id(root, caller), 'providers': providers,
                'library_read': scoped_handle(caller), 'starters_read': scoped_handle(caller,facet='starters'),
                'creation_choices_read': scoped_handle(caller,facet='creation-choices'),
                'execution_preview': operations.preview_offer(caller),
                'definitions': [{'definition_id': row['definition_id'], 'title': _body(root, row)['title'],
                                 'scope': _copy(row['scope']),
                                 'version': row['definition_revision'], 'read': scoped_handle(caller,row['definition_id']),
                                 'history_read':scoped_handle(caller,row['definition_id'],row['definition_revision'],facet='history-page')} for row in items[offset:offset+limit]],
                'offset': offset, 'total': len(items), 'next': scoped_handle(caller,offset=offset+limit, limit=limit) if offset+limit < len(items) else None,
                'actions': {'create': _action('save', {'expected_revision': None}, caller),
                            'inspect_request': {**scoped_handle(caller,facet='request'),'request_field': 'request_id'}},
                'recovery': scoped_handle(caller,facet='request')}
    from laplace.pipeline import workflow_definition_records as captured_records
    captured=captured_records.select(root,caller,payload)
    row,_=captured_records.raw(captured,captured['selected']);head=captured['head'];history=captured['history']
    facet = payload.get('facet', 'inspect')
    if facet in {'app-runs', 'app-run', 'app-compose', 'app-launch-compose', 'app-continue-compose'}:
        from laplace.writing import workflow_dispatch
        result=_copy(workflow_dispatch.read(root, caller, row, payload))
        captured_records.finish(captured,check_head=True)
        return result
    if facet not in {'inspect', 'history', 'settings', 'export'}:
        raise Refused('UNKNOWN_FACET')
    if facet == 'export':
        return capture_export(root,caller,reference(row['definition_id'],row['definition_revision']))['package']
    result=_copy(_view(root,caller,row,head,history,captured=captured))
    captured_records.finish(captured,check_head=True)
    return result


def native_saved_projection(result):
    """Bounded effect evidence for the native transport; full body stays at the exact read."""
    fields = ('effect', 'receipt', 'replayed', 'definition_id', 'version', 'scope', 'read', 'observation', 'request_coverage')
    return {**{key: _copy(result[key]) for key in fields if key in result},
            'next_read': _copy(result['read']['native']), 'full_response_omitted': True}


def native_change_projection(result):
    if result.get('effect') == 'saved':
        return native_saved_projection(result)
    fields = ('effect', 'status', 'profile', 'receipt', 'replayed', 'provider_started',
              'definition', 'scope', 'work', 'plan', 'parent', 'read', 'observation', 'recovery')
    return {**{key: _copy(result[key]) for key in fields if key in result},
            'next_read': _copy(result['read']['native']), 'full_response_omitted': True}


def _saved_result(root, caller, row, head, history, *, replayed):
    result = {'effect': 'saved', 'receipt': _copy(row['receipt']), 'replayed': replayed,
              'definition_id': row['definition_id'], 'version': row['definition_revision'], 'scope': _copy(row['scope']),
              'read': scoped_handle(caller,row['definition_id'], row['definition_revision'])}
    try:
        return {**_view(root, caller, row, head, history), **result}
    except Exception as exc:
        # The immutable effect has already happened. Projection failures cannot turn
        # its receipt into a no-effect/refused answer.
        return {**result, 'observation': {'status': 'UNAVAILABLE', 'error': str(exc)}}


def _recover_request(root, caller, payload, rows):
    if set(payload) != {'facet', 'request_id'} or not isinstance(payload['request_id'], str) or not payload['request_id'] or len(payload['request_id']) > 120:
        raise Refused('INVALID_RECOVERY_REQUEST')
    rid = payload['request_id']
    from laplace.pipeline import workflow_operations as operations
    decision=operations.decision(root,caller,rid)
    if decision is not None:return operations.decision_result(root,caller,decision)
    matches = []
    for row in reversed(rows):
        if row.get('request_id') == rid and _admits(caller, row['scope']):
            _, head, history = _select(rows, caller, {'definition_id': row['definition_id']})
            matches.append({'status': 'RECORDED', 'request_id': rid, **_saved_result(root, caller, row, head, history, replayed=True)})
    from laplace.writing import workflow_dispatch
    app = workflow_dispatch.inspect_request(root, caller, rid)
    if app is not None:
        matches.extend(app.get('matches', [app]) if app.get('status') == 'AMBIGUOUS' else [app])
    admitted = {row['definition_id']: row for row in rows if _admits(caller, row['scope'])}
    path = _root(root) / W.LEDGER
    declared_paths = set()
    if path.exists():
        for record in reversed(list(map(json.loads, path.read_text().splitlines()))):
            pin = record.get('definition_pin') or {}
            if record.get('record') == 'workflow' and record.get('phase') == 'declared' and record.get('preparation_request_id') == rid and pin.get('definition_id') in admitted:
                declared_paths.add(record['run_path'])
                row, _, _ = _select(rows, caller, {'definition_id': pin['definition_id'], 'version': pin['definition_revision']})
                run_dir = _root(root) / record['run_path']
                try:
                    manifest = W._manifest(run_dir)
                    result = _preparation_result(root, row, payload, run_dir, manifest, replayed=True)
                    matches.append({**result, 'status': 'RECORDED', 'execution_status': result['status'], 'request_id': rid})
                except (OSError, ValueError, W.WorkflowRefused) as exc:
                    matches.append({'status': 'UNAVAILABLE', 'request_id': rid, 'effect': 'unknown', 'error': str(exc),
                                    'run_path': record['run_path'], 'read': scoped_handle(caller,row['definition_id'], row['definition_revision'])})
    candidates, coverage = _candidates(root)
    for run_dir, manifest in candidates:
        pin = manifest.get('definition_pin') or {}
        relative = str(run_dir.relative_to(_root(root)))
        if manifest.get('preparation_request_id') == rid and pin.get('definition_id') in admitted and relative not in declared_paths:
            matches.append({'status': 'PREPARATION_UNCERTAIN', 'effect': 'unknown', 'request_id': rid,
                    'run_path': str(run_dir.relative_to(_root(root))),
                    'request_coverage': _public_coverage(caller, coverage),
                    'read': scoped_handle(caller,pin['definition_id'], pin['definition_revision']),
                    'message': 'An immutable preparation candidate exists without a completed declaration; preserve this request ID for recovery'})
    if matches:
        return request_resolution(rid, matches)
    # Absence is bounded owner evidence, not proof that a lost request had no effect.
    return {'status': 'NOT_RECORDED', 'effect': 'unknown', 'request_id': rid,
            'scope_id': _scope_id(root, caller), 'request_coverage': _public_coverage(caller, coverage),
            'message': 'No completed request is recorded in this admitted scope; no request was replayed'}


def request_resolution(request_id, matches):
    """One admitted request observation; contradictory history has no precedence."""
    distinct = {}
    for result in matches:
        key = W.digest(W.canonical({name: result.get(name) for name in
            ('effect', 'profile', 'receipt', 'artifact', 'run_path', 'definition_id', 'version', 'read')}))
        distinct.setdefault(key, result)
    values = list(distinct.values())
    if len(values) == 1:
        return values[0]
    fields = ('status', 'effect', 'profile', 'receipt', 'definition_id', 'version', 'read', 'definition_read',
              'artifact', 'run_path', 'work', 'scope', 'recovery')
    return {'status': 'AMBIGUOUS', 'effect': 'unknown', 'request_id': request_id,
        'matches': [{key: _copy(result[key]) for key in fields if key in result} for result in values[:32]],
        'matches_complete': len(values) <= 32,
        'message': 'Contradictory admitted request effects/reservations exist; no effect was replayed or selected by precedence'}


def _request(payload, allowed):
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise Refused('UNKNOWN_WRITE_FIELD')
    rid = payload.get('request_id')
    if not isinstance(rid, str) or not rid.strip() or len(rid) > 120:
        raise Refused('REQUEST_ID_REQUIRED')
    return W.digest(W.canonical(payload))


def save(root, caller, payload):
    payload = _copy(payload)
    intent = _request(payload, {'request_id', 'definition_id', 'expected_revision', 'definition', 'scope', 'derived_from'})
    _admit_save(root, caller)
    body = payload.get('definition')
    validate(body)
    from laplace.work import project_work
    work_path = project_work._ledger(root)
    work_path.parent.mkdir(parents=True, exist_ok=True)
    # Existing Work writers lock this exact file. Always Work first, definition second.
    with project_work.dispatch_lock(root), FileLock(str(work_path) + '.lock', timeout=20), _lock(root):
        _admit_save(root, caller)
        from laplace.pipeline import workflow_operations as operations
        blocked=operations.admission_decision(root,caller,payload,'save')
        if blocked is not None:return blocked
        from laplace.writing import workflow_dispatch
        if workflow_dispatch.inspect_request(root, caller, payload['request_id']) is not None:
            raise Refused('REQUEST_CONFLICT', 'This request ID already names an app preparation')
        rows = _rows(root)
        preparation_requests, coverage = _preparation_requests(root)
        if any(row.get('preparation_request_id') == payload['request_id'] for row in preparation_requests):
            raise Refused('REQUEST_CONFLICT', 'This request ID already names a preparation')
        prior = next((row for row in rows if row.get('request_id') == payload['request_id']), None)
        if prior:
            if not _admits(caller, prior['scope']):
                raise Refused('NOT_IN_SCOPE')
            if prior['intent_digest'] != intent:
                raise Refused('REQUEST_CONFLICT')
            row, head, history = _select(rows, caller, {'definition_id': prior['definition_id'], 'version': prior['definition_revision']})
            return {**_saved_result(root, caller, row, head, history, replayed=True),
                    'request_coverage': _public_coverage(caller, coverage)}
        ident = payload.get('definition_id')
        if ident:
            _, head, history = _select(rows, caller, {'definition_id': ident})
            scope = head['scope']
            if 'scope' in payload and payload['scope'] != scope:
                raise Refused('SCOPE_CHANGE_NOT_ADMITTED')
            if payload.get('expected_revision') != head['definition_revision']:
                raise Refused('STALE_EDIT', current_read_handle=handle(ident))
            previous = head['definition_revision']
        else:
            if 'expected_revision' not in payload or payload['expected_revision'] is not None:
                raise Refused('NEW_DEFINITION_REQUIRES_NULL_GUARD')
            scope = _scope(payload.get('scope', {'kind': 'owned-workspace'} if caller.kind == 'owned-workspace' else {'kind': 'project', 'namespace': caller.namespace}))
            if not _admits(caller, scope):
                raise Refused('NOT_IN_SCOPE')
            ident, previous, history = 'WDEF-' + uuid.uuid4().hex, None, []
        _targets(root, caller, body, enforce_current=True)
        derived = payload.get('derived_from')
        if derived is not None:
            _select(rows, caller, {'reference': derived})
            if previous is not None:
                raise Refused('FORK_ONLY_ON_CREATE')
        row = {'record': RECORD, 'definition_id': ident, 'previous_revision': previous, 'scope': scope,
               'request_id': payload['request_id'], 'intent_digest': intent, 'derived_from': derived}
        row['definition_revision'] = W.digest(W.canonical(_revision_payload(row, body)))
        row['body_handle'] = writing_bodies.store(_root(root)).put(W.canonical(body))
        row['receipt'] = {'operation': 'save', 'request_id': payload['request_id'], 'definition_id': ident,
                          'definition_revision': row['definition_revision'], 'body_handle': row['body_handle']}
        W._bank(_root(root), row)
        return {**_saved_result(root, caller, row, row, history + [row], replayed=False),
                'request_coverage': _public_coverage(caller, coverage)}


def _stage_ids(body):
    """Stable owner identities stay intact; this adapter alone names legacy packets.

    Reserve every already legal ID first, including unselected steps. Opaque IDs
    map deterministically, with an explicit collision check against both families.
    """
    ids = [step['id'] for step in body['steps']]
    result = {sid: sid for sid in ids if W._ID.fullmatch(sid)}
    occupied = set(result.values())
    for sid in sorted(set(ids) - set(result)):
        nonce = 0
        while True:
            raw = sid if nonce == 0 else sid + '\0' + str(nonce)
            candidate = 'step-' + W.digest(raw.encode()).removeprefix('sha256:')[:40]
            if candidate not in occupied:
                break
            nonce += 1
        result[sid] = candidate
        occupied.add(candidate)
    return result


def _compile(body, settings, selected):
    if any(s['assignment'].get('context') or s['assignment'].get('handoff') for s in body['steps'] if s['id'] in selected):
        raise Refused('EXPLICIT_DELIVERY_PROFILE_REQUIRED')
    steps = {step['id']: step for step in body['steps']}
    if not isinstance(selected, list) or not 2 <= len(selected) <= 16 or len(set(selected)) != len(selected) or not set(selected) <= set(steps):
        raise Refused('UNSUPPORTED_SELECTION', 'Choose2–16distinct executable steps')
    stage_ids = _stage_ids(body)
    deps = {sid: [] for sid in selected}
    for edge in body.get('edges', []):
        if edge['to'] in selected:
            if edge['from'] not in selected:
                raise Refused('UNSUPPORTED_OPEN_INPUT', 'Selected slice consumes a step outside the selection')
            if edge['kind'] == 'feedback':
                raise Refused('UNSUPPORTED_FEEDBACK', 'Definition retained; this legacy profile cannot execute feedback')
            deps[edge['to']].append(edge['from'])
    ordered = []
    pending = list(selected)
    while pending:
        ready = next((sid for sid in pending if set(deps[sid]) <= set(ordered)), None)
        if ready is None:
            raise Refused('UNSUPPORTED_CONTROL_CYCLE')
        ordered.append(ready)
        pending.remove(ready)
    stages = []
    for sid in ordered:
        step, choice = steps[sid], settings[sid]
        if choice.get('error'):
            raise Refused('UNSUPPORTED_SETTINGS', choice['error'])
        if choice['values']['provider'] != 'codex':
            raise Refused('UNSUPPORTED_PROVIDER_PROFILE', 'Claude settings are retained; use its existing admitted session/dispatch owner')
        if choice['values'].get('input_policy') is not None:
            raise Refused('UNSUPPORTED_INPUT_POLICY', 'This profile cannot enforce a custom declared input/tool policy')
        stages.append({'id': stage_ids[sid], 'role': step['assignment']['role'], 'instruction': step['assignment'].get('instructions', ''),
                       'depends_on': [stage_ids[dependency] for dependency in dict.fromkeys(deps[sid])], 'executor': {'provider': 'codex-cli',
                       'model': choice['values']['model'], 'effort': choice['values']['effort']}, 'worker': 'derive'})
    spec = {'schema_version': W.SPEC_SCHEMA, 'stages': stages}
    try:
        W.validate_spec(spec)
    except W.WorkflowRefused as exc:
        raise Refused('UNSUPPORTED_PROFILE_SLICE', str(exc)) from exc
    return spec, {sid: stage_ids[sid] for sid in selected}


def _preparation_result(root, row, payload, run_dir, manifest, *, replayed):
    stage_rows = W._records(_root(root), manifest['run_id'])
    started = any(item.get('record') == 'workflow-stage' and item.get('phase') == 'start' for item in stage_rows)
    status = W.inspect_run(run_dir)['status'] if started else 'NOT_STARTED'
    pin = manifest['definition_pin']
    receipt = {'operation': 'prepare', 'request_id': payload['request_id'], 'run_id': manifest['run_id'],
               'definition_id': row['definition_id'], 'definition_revision': row['definition_revision'],
               'manifest_handle': W._file_hash(run_dir / 'run.json'), 'step_stage_ids': pin['step_stage_ids']}
    run = {'run_id': manifest['run_id'], 'run_path': str(run_dir.relative_to(_root(root))), 'status': status,
           'definition_pin': pin, 'settings_pin': pin['consumed_settings_digest']}
    return {'effect': 'prepared', 'receipt': receipt, 'run': run, **run,
            'read': handle(row['definition_id'], row['definition_revision']), 'replayed': replayed}


def withdraw(root,caller,payload):
    from laplace.pipeline.workflow_operations import withdraw as decide
    return decide(root,caller,payload)


def prepare(root, caller, payload):
    payload = _copy(payload)
    if payload.get('profile') == APP_PROFILE:
        from laplace.writing import workflow_dispatch
        return workflow_dispatch.prepare(root, caller, payload)
    intent = _request(payload, {'request_id', 'reference', 'selected_steps', 'profile', 'node', 'goal', 'write_paths', 'timeout'})
    if caller.door == 'native':
        raise Refused('NATIVE_WRITE_NOT_ADMITTED')
    if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in ('node', 'goal')) or not isinstance(payload.get('write_paths'), list) or any(not isinstance(path, str) for path in payload['write_paths']) or type(payload.get('timeout', 300)) is not int:
        raise Refused('INVALID_PREPARATION_INPUTS', 'Name node, goal and an explicit write_paths list')
    if payload.get('profile') != W.SPEC_SCHEMA:
        raise Refused('UNSUPPORTED_PROFILE')
    if not isinstance(payload.get('reference'), dict) or not payload['reference'].get('version'):
        raise Refused('EXACT_SAVED_VERSION_REQUIRED')
    from laplace.work import project_work
    work_path = project_work._ledger(root)
    work_path.parent.mkdir(parents=True, exist_ok=True)
    with project_work.dispatch_lock(root), FileLock(str(work_path) + '.lock', timeout=20), _lock(root):
        from laplace.pipeline import workflow_operations as operations
        blocked=operations.admission_decision(root,caller,payload,'prepare')
        if blocked is not None:return blocked
        definition_rows = _rows(root)
        from laplace.writing import workflow_dispatch
        if workflow_dispatch.inspect_request(root, caller, payload['request_id']) is not None:
            raise Refused('REQUEST_CONFLICT', 'This request ID already names an app preparation')
        if any(item.get('request_id') == payload['request_id'] for item in definition_rows):
            raise Refused('REQUEST_CONFLICT', 'This request ID already names a definition save')
        row, head, history = _select(definition_rows, caller, {'reference': payload['reference']})
        if caller.kind != 'owned-workspace':
            raise Refused('UNSUPPORTED_PROJECT_EXECUTION_SCOPE')
        path = _root(root) / W.LEDGER
        declared = []
        if path.exists():
            declared = [r for r in map(json.loads, path.read_text().splitlines()) if r.get('record') == 'workflow' and r.get('phase') == 'declared' and r.get('preparation_request_id') == payload['request_id']]
        if declared:
            saved = declared[-1]
            if saved.get('preparation_intent_digest') != intent:
                raise Refused('REQUEST_CONFLICT')
            run_dir = _root(root) / saved['run_path']
            try:
                manifest = W._manifest(run_dir)
                return _preparation_result(root, row, payload, run_dir, manifest, replayed=True)
            except (OSError, ValueError, W.WorkflowRefused) as exc:
                raise Refused('PREPARATION_UNCERTAIN', str(exc), effect='unknown', run_path=saved['run_path']) from exc
        # A crash after writing immutable run files but before declaring them must not
        # create a second run. Recover the exact complete candidate, or report uncertainty.
        observed, coverage = _candidates(root)
        candidates = [(run_dir, candidate) for run_dir, candidate in observed
                      if candidate.get('preparation_request_id') == payload['request_id']]
        if candidates:
            if len(candidates) != 1 or candidates[0][1].get('preparation_intent_digest') != intent:
                raise Refused('PREPARATION_UNCERTAIN', effect='unknown', candidates=[str(item[0].relative_to(_root(root))) for item in candidates])
            run_dir, manifest = candidates[0]
            try:
                if manifest['root'] != str(_root(root)) or manifest['spec_handle'] != W.digest(W.canonical(manifest['spec'])) or manifest['return_schema_handle'] != W.digest(W.canonical(W._load(run_dir / 'return.schema.json'))):
                    raise ValueError('Incomplete or changed preparation')
                W.validate_spec(manifest['spec'])
                W._bank(_root(root), {'record': 'workflow', 'id': manifest['run_id'], 'phase': 'declared',
                    'run_path': str(run_dir.relative_to(_root(root))), 'manifest_handle': W._file_hash(run_dir / 'run.json'),
                    'spec_handle': manifest['spec_handle'], 'authority_effect': 'none', 'definition_pin': manifest['definition_pin'],
                    'preparation_request_id': payload['request_id'], 'preparation_intent_digest': intent})
                manifest = W._manifest(run_dir)
            except (OSError, ValueError, KeyError, TypeError, W.WorkflowRefused) as exc:
                raise Refused('PREPARATION_UNCERTAIN', str(exc), effect='unknown', run_path=str(run_dir.relative_to(_root(root)))) from exc
            return _preparation_result(root, row, payload, run_dir, manifest, replayed=True)
        body = _body(root, row)
        settings, _ = resolve_settings(root, caller, body, edit_revision=row['definition_revision'])
        selected = payload.get('selected_steps')
        spec, stage_ids = _compile(body, settings, selected)
        obligations = _targets(root, caller, body, enforce_current=True, selected=selected)
        for step in body['steps']:
            if step['id'] in selected and (step.get('inputs') or step.get('outputs')):
                obligations.append({'step_id': step['id'], 'code': 'UNSUPPORTED_INPUT_OUTPUT_BINDING',
                                    'message': 'Declared input/output labels are retained; this profile has no binding for them'})
        if obligations:
            raise Refused('UNSUPPORTED_TARGETS', obligations=obligations)
        pin = {'definition_id': row['definition_id'], 'definition_revision': row['definition_revision'],
               'body_handle': row['body_handle'], 'selected_steps': selected, 'step_stage_ids': stage_ids,
               'consumed_settings_digest': W.digest(W.canonical({sid: settings[sid]['values'] for sid in selected})),
               'consumed_semantics_digest': W.digest(W.canonical(spec))}
        run_dir = None
        try:
            run_dir = W.create_run(_root(root), spec, node=payload.get('node', ''), goal=payload.get('goal', ''),
                                   model=spec['stages'][0]['executor']['model'], effort=spec['stages'][0]['executor']['effort'],
                                   state=checkout.state_root(), write_paths=payload.get('write_paths', []), timeout=payload.get('timeout', 300),
                                   definition_pin=pin, preparation_request_id=payload['request_id'], preparation_intent_digest=intent)
            manifest = W._manifest(run_dir)
        except W.WorkflowRefused as exc:
            if run_dir is not None:
                raise Refused('PREPARATION_UNCERTAIN', str(exc), effect='unknown', run_path=str(run_dir.relative_to(_root(root)))) from exc
            raise Refused('PREPARATION_REFUSED', str(exc), effect='none') from exc
        except (OSError, ValueError) as exc:
            raise Refused('PREPARATION_UNCERTAIN', str(exc), effect='unknown', recovery='Reinspect this exact preparation request; do not send a new request ID') from exc
        return {**_preparation_result(root, row, payload, run_dir, manifest, replayed=False),
                'request_coverage': _public_coverage(caller, coverage)}


def validate_export(payload):
    """Pure, detached full-package validation, shared by export and transfer consumers.

    No scope admission, root, ledger or body store is consulted. Values and owner
    timestamps are preserved verbatim; validation grants no restore authority.
    """
    package = _copy(payload)
    if set(package) != {'schema_version', 'definition_id', 'versions'} or package['schema_version'] != 'laplace.workflow-definition-export/1' or not isinstance(package['versions'], list) or not 1 <= len(package['versions']) <= 32 or len(W.canonical(package)) > 1_000_000:
        raise Refused('INVALID_EXPORT')
    ident, previous = package['definition_id'], None
    if not isinstance(ident, str) or not re.fullmatch(r'WDEF-[0-9a-f]{32}', ident):
        raise Refused('INVALID_EXPORT_ID')
    request_ids = set()
    for item in package['versions']:
        if not isinstance(item, dict) or set(item) != {'row', 'definition'}:
            raise Refused('INVALID_EXPORT_RECORD')
        previous=validate_lineage_version(item['row'],item['definition'],ident,previous,request_ids)
    return package


def validate_lineage_version(row,body,ident,previous,request_ids):
    """One exact version; shared by unchanged v1 and streamed complete v2 chains.

    request_ids and previous are caller-held traversal state, never authority.
    """
    _valid_definition_record(row)
    if row['request_id'] in request_ids:raise Refused('INVALID_EXPORT_REQUEST_DUPLICATE')
    request_ids.add(row['request_id']);validate(body);_scope(row['scope'])
    if row.get('record')!=RECORD or row.get('definition_id')!=ident or row.get('previous_revision')!=previous or W.digest(W.canonical(body))!=row.get('body_handle') or W.digest(W.canonical(_revision_payload(row,body)))!=row.get('definition_revision') or 'workflow_id' in row:
        raise Refused('INVALID_EXPORT_CHAIN')
    return row['definition_revision']


def restore(root, caller, payload):
    """Restore exact owner identity/history to existing custody. Root authority only; no grant transfer."""
    if caller.kind != 'owned-workspace' or caller.door == 'native':
        raise Refused('RESTORE_NOT_ADMITTED')
    package = validate_export(payload)
    ident = package['definition_id']
    clean = [(item['row'], item['definition']) for item in package['versions']]
    request_ids = {row['request_id'] for row, _ in clean}
    with _lock(root):
        destination_rows = _rows(root)
        from laplace.writing import workflow_dispatch
        if any(workflow_dispatch.inspect_request(root, caller, request_id) is not None for request_id in request_ids):
            raise Refused('RESTORE_REQUEST_CONFLICT', 'Imported request already names an app preparation')
        existing = [row for row in destination_rows if row['definition_id'] == ident]
        preparation_requests, coverage = _preparation_requests(root)
        if any(row['request_id'] in request_ids and row['definition_id'] != ident for row in destination_rows) or any(row.get('preparation_request_id') in request_ids for row in preparation_requests):
            raise Refused('RESTORE_REQUEST_CONFLICT')
        if existing:
            if [row['definition_revision'] for row in existing] != [row['definition_revision'] for row, _ in clean[:len(existing)]]:
                raise Refused('RESTORE_IDENTITY_CONFLICT')
            for destination, (incoming, _) in zip(existing, clean):
                if {key: value for key, value in destination.items() if key not in {'ts', 'ts_claimed'}} != {key: value for key, value in incoming.items() if key not in {'ts', 'ts_claimed'}}:
                    raise Refused('RESTORE_IDENTITY_CONFLICT')
        for row, body in clean[len(existing):]:
            writing_bodies.store(_root(root)).put(W.canonical(body))
            imported = {key: value for key, value in row.items() if key != 'ts'}
            if 'ts_claimed' not in imported and row.get('ts'):
                imported['ts_claimed'] = row['ts']
            # The journal stamps this custody event; retain the oldest imported
            # owner timestamp without overwriting it on a later custody transfer.
            W._bank(_root(root), imported)
    return {**read(root, caller, {'definition_id': ident}),
            'request_coverage': _public_coverage(caller, coverage)}
