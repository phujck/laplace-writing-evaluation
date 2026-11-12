"""Typed profile candidates in the existing writing proposal/decision/application owners.

This is a family adapter, not a configuration store. Architecture bytes belong
to narrative; shared voice bytes and project selection belong to writing_style.
Generated candidates are immutable inputs to those same guarded consumers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import uuid
from urllib.parse import urlencode

SCHEMA = 'laplace.profile-candidate/1'
MAX_PART_BYTES = 8000
REF = {'type': 'object', 'required': ['id', 'version'], 'properties': {
    'id': {'type': 'string', 'pattern': '^PROP-[a-f0-9]{32}$'},
    'version': {'type': 'string', 'pattern': '^sha256:[a-f0-9]{64}$'}}, 'additionalProperties': False}


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def read_contract():
    return {'type': 'object', 'properties': {
        'family': {'enum': ['architecture', 'voice']}, 'scope': {'enum': ['workspace', 'project']},
        'view': {'enum': ['summary', 'content', 'candidate', 'candidates']},
        'profile': {'type': 'string'}, 'candidate_ref': REF,
        'part': {'enum': ['metadata', 'current', 'proposed']},
        'offset': {'type': 'integer', 'minimum': 0},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': MAX_PART_BYTES}},
        'additionalProperties': False, 'allOf': [
            {'if': {'required': ['view'], 'properties': {'view': {'const': 'candidate'}}},
             'then': {'required': ['candidate_ref'], 'not': {'anyOf': [{'required': [key]} for key in ('family', 'scope', 'profile')]}},
             'else': {'not': {'required': ['candidate_ref']}}},
            {'if': {'required': ['view'], 'properties': {'view': {'enum': ['candidate', 'candidates']}}},
             'else': {'required': ['family', 'scope']}},
            {'if': {'required': ['view'], 'properties': {'view': {'const': 'candidates'}}},
             'then': {'not': {'required': ['part']}}},
            {'if': {'required': ['profile']}, 'then': {'required': ['family', 'scope'],
                'properties': {'family': {'const': 'voice'}, 'scope': {'const': 'workspace'}}}},
            {'if': {'required': ['family'], 'properties': {'family': {'const': 'architecture'}}},
             'then': {'properties': {'scope': {'const': 'workspace'}}, 'not': {'required': ['profile']}}}]}


def change_contract():
    from laplace.pipeline import narrative
    text = {'type': 'string'}
    architecture = narrative.architecture_content_contract()
    guard = {'type': 'object', 'required': ['profile_input_revision'], 'properties': {
        'profile_input_revision': {'type': 'string', 'pattern': '^sha256:[a-f0-9]{64}$',
                                   'examples': ['sha256:' + '0' * 64]}}, 'additionalProperties': False}
    def propose(family, scope, change, *, shared_voice=False):
        properties = {'action': {'const': 'propose'}, 'family': {'const': family},
            'scope': {'const': scope}, 'change': change, 'guards': guard, 'reason': text}
        if shared_voice: properties['profile'] = text
        return {'type': 'object', 'required': ['action', 'family', 'scope', 'change', 'guards', 'reason'],
                'properties': properties, 'additionalProperties': False}
    return {'oneOf': [
        propose('architecture', 'workspace', {'type': 'object', 'required': ['content'],
            'properties': {'content': {'type': 'string', 'minLength': 1,
                'description': 'Serialize the complete YAML/JSON document under change.content; fields inside profile require summary. Preserve existing values. Read profile content_contract.delivery for whole-paper and conditional section coverage.', 'contentMediaType': 'application/yaml',
                'contentSchema': architecture['document_schema'],
                'examples': [json.dumps(architecture['example'])]}}, 'additionalProperties': False}),
        propose('voice', 'workspace', {'type': 'object', 'required': ['content'],
            'properties': {'content': text, 'basis': {'enum': ['reviewed_preference', 'source_calibration']},
                'expected_provenance_revision': text, 'source_handles': {'type': 'array', 'maxItems': 64,
                    'items': {'type': 'object', 'required': ['path', 'sha256'],
                        'properties': {'path': text, 'sha256': text}, 'additionalProperties': False}},
                'judgement': {'type': 'object'}}, 'additionalProperties': False,
            'allOf': [{'if': {'required': ['basis'], 'properties': {'basis': {'const': 'source_calibration'}}},
                'then': {'required': ['expected_provenance_revision', 'source_handles', 'judgement']}}]}, shared_voice=True),
        propose('voice', 'project', {'type': 'object', 'minProperties': 1,
            'properties': {'profile': text, 'guidance': text, 'genre': text}, 'additionalProperties': False}),
        {'type': 'object', 'required': ['action', 'candidate_ref'],
         'properties': {'action': {'const': 'apply'}, 'candidate_ref': REF}, 'additionalProperties': False},
        {'type': 'object', 'required': ['action', 'family', 'scope', 'fields', 'guards', 'reason'],
         'properties': {'action': {'const': 'confirm'}, 'family': {'const': 'architecture'},
             'scope': {'const': 'workspace'}, 'fields': {'type': 'array', 'minItems': 1, 'maxItems': 64,
                 'uniqueItems': True, 'items': text}, 'guards': guard, 'reason': text},
         'additionalProperties': False}]}


def http_contract(*, write=False):
    """Only routing metadata is added to the same owner contract."""
    import copy
    schema = copy.deepcopy(change_contract() if write else read_contract())
    for branch in schema['oneOf'] if write else [schema]:
        branch.setdefault('properties', {})['project'] = {'type': 'string'}
        if write: branch['required'] = ['project', *branch['required']]
    return schema


def _validate(payload, contract):
    from jsonschema import Draft202012Validator
    errors = sorted(Draft202012Validator(contract).iter_errors(payload), key=lambda error: str(error.path))
    if errors:
        error = errors[0]
        at = '.'.join(str(part) for part in error.path)[:200] or 'request shape'
        raise ValueError('Profile request does not match its declared contract (' + str(error.validator) + ' at ' + at + '). Inspect profile/profile_change help for exact fields.')


def handle(project, payload, *, write=False):
    """One action shape for HTTP and either provider; no candidate body in handles."""
    from laplace.core import grammar
    operation = 'profile_change' if write else 'profile'
    route = '/work/profiles/change' if write else '/work/profiles'
    concept = 'profile-candidate@project' if payload.get('candidate_ref') or payload.get('view') == 'candidates' else (
        'architecture-profile@project' if payload.get('family') == 'architecture' else
        'style-state@project' if payload.get('scope') == 'project' else 'style-profile@project')
    result = {'operation': operation, 'permitted': bool(project) if write else True,
        'payload': {**({'project': project} if project else {}), **payload},
        'http': {'method': 'POST' if write else 'GET', 'url': route if write else
            route + '?' + urlencode({**({'project': project} if project else {}), **{key: json.dumps(value, separators=(',', ':'))
                if isinstance(value, dict) else value for key, value in payload.items()}})},
        }
    if project:
        result['native_request'] = {'verb': 'change' if write else 'read', 'concept': concept,
            'target': project, 'expected': [], 'payload': grammar.to_payload(payload), 'by': ''}
    else:
        result['native_context_required'] = 'Choose an existing project conversation for native profile actions; workspace scope is unchanged.'
    return result


def _scope(family, scope):
    if family not in {'architecture', 'voice'} or scope not in {'workspace', 'project'}:
        raise ValueError('Choose an actual profile family and workspace/project scope.')
    if family == 'architecture' and scope != 'workspace':
        raise ValueError('Architecture preferences belong to the workspace; no project override exists.')


def snapshot(project, family, scope, root, profile=None):
    """Current bounded identities and effective values; no history or catalogue bodies."""
    from laplace.manuscript import writing_style
    from laplace.pipeline import narrative
    _scope(family, scope)
    if family == 'architecture':
        value = narrative.architecture_status(root, include_content=True)
        path = root / narrative.ARCHITECTURE_PROFILE_PATH
        data = None
        if value['status'] == 'AVAILABLE':
            with path.open('rb') as stream:
                raw = stream.read(narrative.MAX_ARCHITECTURE_BYTES + 1)
            if len(raw) > narrative.MAX_ARCHITECTURE_BYTES or 'sha256:' + hashlib.sha256(raw).hexdigest() != value['profile_revision']:
                raise ValueError('CHANGED_INPUT: architecture profile changed during inspection; read it again.')
            data = narrative.architecture_document(raw.decode('utf-8'))
        value['effective_revision'] = value['revision']
        value['revision'] = digest({'effective_revision': value['revision'],
            'profile_revision': value['profile_revision'], 'status': value['status']})
        value.update(profile=narrative.ARCHITECTURE_PROFILE_PATH, content=json.dumps(data, ensure_ascii=False, indent=2)
            if data is not None else '', effective_values=value.get('fields') or {}, defaults={}, overrides={})
        return value
    selected = writing_style._selection(root, project if scope == 'project' else None,
        str(profile or writing_style.DEFAULT_PROFILE) if scope == 'workspace' else None)
    provenance = writing_style._provenance_summary(selected['provenance'], root)
    inputs = {'profile': selected['selected'], 'profile_revision': selected['byte_revision'],
        'provenance_revision': provenance.get('revision')}
    if scope == 'project':
        inputs.update(guidance=selected['guidance'], genre=selected['genre'],
            effective_genre=writing_style.effective_genre(project, root, authored=selected['genre'])['effective'])
    return {'family': family, 'scope': scope, 'profile': selected['selected'], 'revision': digest(inputs),
        'profile_revision': inputs['profile_revision'], 'status': 'AVAILABLE',
        'editable': scope == 'project' or selected['origin'] == 'project',
        'source': {'path': selected['selected'], 'origin': selected['origin']},
        'purpose': 'Sentence voice and cadence preferences.' if scope == 'workspace' else
            'Project selection, genre and guidance; shared voice profile bytes are separate.',
        'provenance': provenance, 'inputs': inputs,
        'effective_values': {key: inputs[key] for key in ('profile', 'guidance', 'genre', 'effective_genre') if key in inputs},
        'defaults': {'profile': writing_style.DEFAULT_PROFILE, 'guidance': '', 'genre': 'selected document class'},
        'overrides': {key: inputs[key] for key in ('guidance', 'genre') if inputs.get(key)},
        'content': selected['content'] if scope == 'workspace' else json.dumps(
            {key: inputs[key] for key in ('profile', 'guidance', 'genre')}, ensure_ascii=False, indent=2)}


def _summary(value):
    result = {key: item for key, item in value.items() if key not in {'content', 'fields', 'runtime_content'}}
    if value.get('family') == 'architecture':
        result['effective_values'] = {name: {key: field[key] for key in
            ('field_revision', 'confirmed_his', 'historical_confirmation_assertion', 'author_confirmation') if key in field}
            for name, field in (value.get('effective_values') or {}).items()}
    return result


def _part(text, offset, limit):
    """Exact UTF-8 coverage; complete is whole text here, at_end ends the stream."""
    raw = text.encode('utf-8')
    if offset > len(raw):
        raise ValueError('Profile text offset exceeds the retained bytes.')
    try:
        raw[:offset].decode('utf-8')
    except UnicodeDecodeError as error:
        raise ValueError('Profile offset must be a UTF-8 boundary.') from error
    end = min(offset + limit, len(raw))
    while True:
        if end == offset and offset < len(raw):
            raise ValueError('The byte budget cannot hold one complete encoded profile text character.')
        try:
            content = raw[offset:end].decode('utf-8')
        except UnicodeDecodeError:
            end -= 1
            continue
        encoded_size = len(json.dumps(content, ensure_ascii=False).encode('utf-8'))
        if encoded_size <= limit or end == offset:
            break
        next_end = offset + max(1, (end - offset) * limit // encoded_size)
        if next_end >= end:
            raise ValueError('The byte budget cannot hold one complete encoded profile text character.')
        end = next_end
    return {'content': content, 'coverage': {'unit': 'utf8-bytes', 'start': offset, 'end': end,
        'total': len(raw), 'complete': offset == 0 and end == len(raw),
        'at_end': end == len(raw), 'has_more': end < len(raw),
        'sha256': 'sha256:' + hashlib.sha256(raw).hexdigest()},
        'read_instruction': 'Follow next_read while coverage.has_more is true. coverage.at_end ends the stream; coverage.complete means the whole text is in this one response.'}


def _candidate(root, project, ref):
    from laplace.writing import records
    row = records.selected_journal_fields(project, ref['id'], root, fields=['id', 'record', 'project',
        'candidate_kind', 'profile_family', 'profile_scope', 'profile_path',
        'proposal', 'proposal_instance_version', 'author', 'origin_turn_id'])
    from laplace.core.identity import require_schema_version
    require_schema_version(row.get('proposal'), (SCHEMA,), owner='Profile candidate')
    if (row.get('record') != 'writing-proposal' or row.get('candidate_kind') != 'profile-change'
            or row.get('proposal_instance_version') != ref['version']
            or digest(row.get('proposal')) != ref['version']):
        raise ValueError('Select the exact immutable profile candidate and inspected version.')
    return row


def candidate_summary(root, project, row):
    """Metadata hook for the existing candidate catalogue; does not open profile text."""
    from laplace.writing import records
    ref = {'id': row['id'], 'version': row['proposal_instance_version']}
    related = records.index(root).by_candidate.get(row['id'], [])
    application = next((item for item in reversed(related) if item.get('record') == 'writing-application'
        and item.get('complete') and item.get('candidate_version') == ref['version']), None)
    return {'id': row['id'], 'project': project, 'custody_project': project,
        'candidate_kind': 'profile-change', 'candidate_ref': ref,
        'family': row.get('profile_family'), 'scope': row.get('profile_scope'), 'profile': row.get('profile_path'),
        'status': 'APPLIED' if application else 'PROPOSED',
        'application_id': application.get('id') if application else None,
        'read_handle': handle(project, {'view': 'candidate', 'candidate_ref': ref})}


def inspect(project, payload, repo_root, *, actor=None):
    from laplace.writing import records
    root = Path(repo_root).resolve()
    _validate(payload, read_contract())
    view = payload.get('view', 'summary')
    if view == 'candidates':
        if project is None and payload.get('scope', 'workspace') != 'workspace':
            raise ValueError('Projectless candidate discovery is workspace-only; choose the actual project for project settings.')
        indexed = records.index(root)
        scope = indexed.profile_candidates_by_scope.get('workspace', []) if project is None else indexed.profile_candidates_by_project.get(project, [])
        rows = [row for row in scope
            if row.get('candidate_kind') == 'profile-change' and row.get('record') == 'writing-proposal'
            and (project is not None or row.get('profile_scope') == 'workspace')
            and (not payload.get('family') or row.get('profile_family') == payload['family'])
            and (not payload.get('profile') or row.get('profile_path') == payload['profile'])
            and (not payload.get('scope') or row.get('profile_scope') == payload['scope'])]
        rows.sort(key=lambda row: row['_order'], reverse=True)
        offset = payload.get('offset', 0); limit = min(payload.get('limit', 20), 20)
        return {'candidates': [candidate_summary(root, project or indexed.project(row), row) for row in rows[offset:offset + limit]],
            'coverage': {'whole_history_loaded': False, 'profile_bodies_loaded': 0},
            'pagination': {'offset': offset, 'returned': len(rows[offset:offset + limit]), 'total': len(rows)}}
    if view == 'candidate':
        if not payload.get('candidate_ref'):
            raise ValueError('Candidate inspection requires the exact candidate_ref.')
        row = _candidate(root, project, payload['candidate_ref']); candidate = row['proposal']
        current = snapshot(project, candidate['family'], candidate['scope'], root, candidate.get('profile'))
        matches = current['revision'] == candidate['expected_revision']
        summary = candidate_summary(root, project, row)
        related = records.index(root).by_candidate.get(row['id'], [])
        pending = next((item for item in reversed(related) if item.get('record') == 'writing-application'
            and item.get('status') == 'APPLYING' and item.get('candidate_version') == payload['candidate_ref']['version']), None)
        recoverable = False
        if pending and not summary.get('application_id'):
            intended = records.selected_journal_fields(project, pending['id'], root, fields=['intended_effect'])
            recoverable = intended.get('intended_effect') == _effect(current) and _recovery_inputs_current(candidate, current, root)
        currentness = 'CURRENT' if matches else 'CHANGED_INPUT'
        if summary.get('application_id'):
            completed = records.selected_journal_fields(project, summary['application_id'], root, fields=['after_revision'])
            currentness = 'APPLIED_CURRENT' if completed.get('after_revision') == current['revision'] else 'APPLIED_SUPERSEDED'
        result = {**summary, 'reason': candidate['reason'],
            'author': row.get('author'), 'current': _summary(current), 'expected_revision': candidate['expected_revision'],
            'currentness': currentness, 'candidate_retained': True,
            'application_tracking': 'COMPLETE' if summary.get('application_id') else 'INCOMPLETE' if pending else 'NOT_APPLIED',
            'recovery': 'Complete tracking without rewriting the observed exact intended effect.' if recoverable else None,
            'authority': 'Applied preference is separate from explicit personal author confirmation.',
            'affected_consumers': consumers(candidate['family'], candidate['scope']),
            'apply_action': {**handle(project, {'action': 'apply', 'candidate_ref': payload['candidate_ref']}, write=True),
                'permitted': (matches or recoverable) and not summary.get('application_id')},
            'text_reads': {part: handle(project, {'view': 'candidate', 'candidate_ref': payload['candidate_ref'], 'part': part})
                for part in ('current', 'proposed')}}
        if candidate['family'] == 'architecture':
            from laplace.pipeline import narrative
            result['delivery'] = narrative.architecture_delivery_contract()
        part = payload.get('part', 'metadata')
        if part != 'metadata':
            text = current['content'] if part == 'current' else candidate['change'].get('content') or json.dumps(candidate['change'], ensure_ascii=False, indent=2)
            chunk = _part(text, payload.get('offset', 0), payload.get('limit', MAX_PART_BYTES))
            result = {key: result[key] for key in ('candidate_ref', 'family', 'scope', 'profile', 'currentness', 'candidate_retained')}
            result.update(part=part, **chunk)
            if chunk['coverage']['end'] < chunk['coverage']['total']:
                result['next_read'] = handle(project, {**payload, 'offset': chunk['coverage']['end']})
        return result
    family = payload.get('family'); scope = payload.get('scope')
    if project is None and scope != 'workspace':
        raise ValueError('Project settings inspection requires the selected actual project.')
    current = snapshot(project, family, scope, root, payload.get('profile'))
    result = {**_summary(current), 'affected_consumers': consumers(family, scope),
        'content_read': handle(project, {'family': family, 'scope': scope, 'view': 'content',
            **({'profile': current['profile']} if family == 'voice' and scope == 'workspace' else {})}),
        'candidates_read': handle(project, {'family': family, 'scope': scope, 'view': 'candidates',
            **({'profile': current['profile']} if family == 'voice' and scope == 'workspace' else {})}),
        'generation': {'uses': 'existing project app session', 'operation': 'profile_change',
            'instruction': 'Inspect the current profile and explicitly selected source material. Propose a profile candidate with the inspected revision; do not apply it or claim personal author confirmation.'}}
    if family == 'architecture' and not payload.get('offset', 0):
        from laplace.pipeline import narrative
        result['content_contract'] = narrative.architecture_content_contract()
    basis = {'family': family, 'scope': scope, 'guards': {'profile_input_revision': current['revision']}}
    if family == 'voice' and scope == 'workspace':
        basis['profile'] = current['profile']
    result['propose_action'] = {**handle(project, {'action': 'propose', **basis}, write=True),
        'kind': 'action-template', 'complete': False, 'required_fields': ['change', 'reason']}
    if not current.get('editable'):
        result['propose_action'].update(permitted=False, reason='This profile input is unavailable or deployed read-only.')
    if family == 'architecture' and current['status'] == 'AVAILABLE':
        result['confirm_action'] = {**handle(project, {'action': 'confirm', **basis}, write=True),
            'kind': 'action-template', 'complete': False, 'required_fields': ['fields', 'reason'],
            'authority': 'explicit-human-action', 'permitted': bool(project) and (actor or {}).get('kind', 'human') == 'human'}
        if not result['confirm_action']['permitted']:
            result['confirm_action']['reason'] = 'Personal confirmation requires a human action in an explicit producing-project context.'
    if view == 'content':
        chunk = _part(current['content'], payload.get('offset', 0), payload.get('limit', MAX_PART_BYTES))
        result.update(chunk)
        if chunk['coverage']['end'] < chunk['coverage']['total']:
            result['next_read'] = handle(project, {**payload, 'offset': chunk['coverage']['end']})
    return result


def consumers(family, scope):
    if family == 'architecture':
        return ['whole-paper structure planner: all fields', 'section plans and reader basis: conditional known fields', 'taste retrieval: eligible fields, selection not guaranteed']
    return ['selected voice runtime prompt', 'prose dispatch', 'writing operating context', 'manuscript review/output currentness'] if scope == 'workspace' else [
        'project selected voice runtime prompt', 'project genre/guidance', 'prose dispatch', 'writing operating context', 'manuscript review/output currentness']


def _voice_payload(candidate, before):
    change = candidate['change']
    basis = change.get('basis', 'reviewed_preference')
    return {**change, 'profile': candidate['profile'], 'expected_profile_revision': before['profile_revision'],
        'basis': basis, 'reason': candidate['reason'],
        **({'provenance_kind': 'reviewed-profile-candidate'} if basis == 'reviewed_preference' else {})}


def change(project, payload, repo_root, *, actor=None):
    from laplace.manuscript import writing_style
    from laplace.writing import records as writing_records
    from laplace.pipeline import narrative, registry
    root = Path(repo_root).resolve()
    _validate(payload, change_contract())
    if registry.resolve(project, repo_root=root) is None:
        raise ValueError('Profile actions require the selected registered project for candidate custody.')
    actor = actor or {'kind': 'human'}
    if actor.get('kind') not in {'human', 'agent'}:
        raise ValueError('Profile actor must be human or agent.')
    if actor['kind'] == 'agent':
        from laplace.writing import records
        turn = records.index(root).turns.get(actor.get('turn_id'))
        if not turn or records.index(root).project(turn) != project:
            raise ValueError('An agent profile action requires its actual current project turn.')
        if turn.get('mode') == 'review' or actor.get('mode') == 'review':
            raise ValueError('Independent reviewers may inspect profiles; profile mutations belong to the authorised author session.')
        if payload['action'] == 'apply' and (turn.get('parent_turn_id') or turn.get('dispatch_id') or actor.get('dispatch_id')):
            raise ValueError('A dispatched child proposes profile candidates; the parent applies.')
    if payload['action'] == 'confirm':
        return _confirm(root, project, payload, actor)
    with writing_records.proposal_write_lock(root):
        if payload['action'] == 'propose':
            family, scope = payload['family'], payload['scope']
            if payload.get('profile') and (family != 'voice' or scope != 'workspace'):
                raise ValueError('A top-level profile path selects shared voice bytes only; project profile selection belongs inside change.')
            current = snapshot(project, family, scope, root, payload.get('profile'))
            if current['revision'] != payload['guards']['profile_input_revision']:
                raise ValueError('CHANGED_INPUT: inspect the current profile before proposing; authored content is unchanged.')
            if not current['editable']:
                raise ValueError('The selected deployed profile is read-only in this workspace.')
            reason = payload['reason'].strip(); change_value = dict(payload['change'])
            if not reason or len(reason.encode()) > 4000:
                raise ValueError('A bounded nonempty profile change reason is required.')
            candidate = {'schema_version': SCHEMA, 'family': family, 'scope': scope, 'profile': current['profile'],
                'expected_revision': current['revision'], 'inputs': current.get('inputs') or {'profile_revision': current['profile_revision']},
                'reason': reason, 'change': change_value}
            if family == 'architecture':
                if set(change_value) != {'content'}:
                    raise ValueError('Architecture changes require exactly typed profile content.')
                import yaml
                data = narrative.architecture_document(change_value['content'], max_input_bytes=4 * narrative.MAX_ARCHITECTURE_BYTES)
                data.pop('author_confirmation', None)
                narrative.architecture_document(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
                candidate['change'] = {'content': json.dumps(data, ensure_ascii=False, indent=2)}
            elif scope == 'workspace':
                if set(change_value) - {'content', 'basis', 'expected_provenance_revision', 'source_handles', 'judgement'} or 'content' not in change_value:
                    raise ValueError('Shared voice changes require content and optional exact calibration inputs.')
                writing_style._update_profile(None, _voice_payload(candidate, current), root,
                    global_profile=current['profile'], validate_only=True)
            else:
                if not change_value or set(change_value) - {'profile', 'guidance', 'genre'}:
                    raise ValueError('Project voice changes affect only profile selection, guidance and genre.')
                for key, value in change_value.items():
                    if not isinstance(value, str) or len(value.encode()) > (8000 if key == 'guidance' else 1000):
                        raise ValueError('Project voice settings require bounded text values.')
                selected, _ = writing_style._profile(root, change_value.get('profile', current['profile']))
                candidate['inputs']['selected_profile_revision'] = writing_style._file_digest(selected)
                candidate['inputs']['style_state_revision'] = writing_style.state(project, root)['revision']
            ident = 'PROP-' + uuid.uuid4().hex; version = digest(candidate)
            from laplace.representation import writing_bodies as bodies
            retained = bodies.retain_leaves(root, candidate, texts=('content',))
            writing_records.bank(root, {'record': 'writing-proposal', 'id': ident, 'project': project,
                'candidate_kind': 'profile-change', 'profile_family': family, 'profile_scope': scope,
                'profile_path': current['profile'], 'proposal': retained, 'proposal_instance_version': version,
                'proposal_content_sha256': version, 'author': actor, 'origin_turn_id': actor.get('turn_id')})
            return inspect(project, {'view': 'candidate', 'candidate_ref': {'id': ident, 'version': version}}, root)
        return _apply(root, project, payload['candidate_ref'], actor)


def _effect(current):
    """Exact consumer settings/content, independent of confirmation record pointers."""
    if current['family'] == 'architecture':
        from laplace.pipeline import narrative
        if current['status'] != 'AVAILABLE':
            return None
        data = narrative.architecture_document(current['content'], max_input_bytes=4 * narrative.MAX_ARCHITECTURE_BYTES)
        data.pop('author_confirmation', None)
        return digest(data)
    if current['scope'] == 'workspace':
        return digest(current['content'])
    return digest({key: current['inputs'][key] for key in ('profile', 'guidance', 'genre')})


def _intended_effect(candidate, current):
    if candidate['family'] == 'architecture':
        from laplace.pipeline import narrative
        data = narrative.architecture_document(candidate['change']['content'], max_input_bytes=4 * narrative.MAX_ARCHITECTURE_BYTES)
        data.pop('author_confirmation', None)
        return digest(data)
    if candidate['scope'] == 'workspace':
        return digest(candidate['change']['content'].replace('\r\n', '\n').replace('\r', '\n'))
    return digest({**{key: current['inputs'][key] for key in ('profile', 'guidance', 'genre')}, **candidate['change']})


def _recovery_inputs_current(candidate, current, root):
    """An observed postimage does not renew changed selection/calibration inputs."""
    from laplace.manuscript import writing_style
    if candidate['family'] != 'voice':
        return True
    if candidate['scope'] == 'project':
        return current['profile_revision'] == candidate['inputs']['selected_profile_revision']
    if candidate['change'].get('basis') == 'source_calibration':
        try:
            writing_style._update_profile(None, _voice_payload(candidate, current), root,
                global_profile=candidate['profile'], validate_only=True)
        except (ValueError, OSError):
            return False
    return True


def _apply(root, project, ref, actor):
    from laplace.manuscript import writing_style
    from laplace.writing import records as writing_records
    from laplace.pipeline import narrative
    from laplace.writing import records
    row = _candidate(root, project, ref); candidate = row['proposal']
    current = snapshot(project, candidate['family'], candidate['scope'], root, candidate['profile'])
    related = records.index(root).by_candidate.get(ref['id'], [])
    applications = [item for item in related if item.get('record') == 'writing-application'
        and item.get('candidate_version') == ref['version'] and item.get('complete')]
    if applications:
        return {**inspect(project, {'view': 'candidate', 'candidate_ref': ref}, root),
            'application_id': applications[-1]['id'], 'reused': True}
    pending = [item for item in related if item.get('record') == 'writing-application'
        and item.get('candidate_version') == ref['version'] and item.get('status') == 'APPLYING']
    if pending:
        intent = records.selected_journal_fields(project, pending[-1]['id'], root, fields=['id', 'intended_effect'])
        if intent.get('intended_effect') == _effect(current) and _recovery_inputs_current(candidate, current, root):
            application = writing_records.bank(root, {'record': 'writing-application', 'id': 'APP-' + uuid.uuid4().hex,
                'project': project, 'candidate_id': ref['id'], 'candidate_kind': 'profile-change',
                'candidate_version': ref['version'], 'profile_family': candidate['family'], 'profile_scope': candidate['scope'],
                'profile_path': candidate['profile'], 'actor': actor, 'intent_id': intent['id'], 'complete': True,
                'status': 'APPLIED', 'after_revision': current['revision'], 'recovery': 'Exact intended consumer effect observed; metadata completed without rewriting.',
                'authority_effect': 'preferences applied; personal author confirmation not asserted',
                'semantic_currentness': 'NOT_REASSERTED'})
            return {**inspect(project, {'view': 'candidate', 'candidate_ref': ref}, root),
                'application_id': application['id'], 'metadata_only': True}
    if current['revision'] != candidate['expected_revision']:
        raise ValueError('CHANGED_INPUT: profile inputs changed. The exact candidate is retained; inspect and propose a successor.')
    family, scope = candidate['family'], candidate['scope']; values = candidate['change']
    if family == 'voice' and scope == 'project':
        path, _ = writing_style._profile(root, values.get('profile', current['profile']))
        if writing_style._file_digest(path) != candidate['inputs']['selected_profile_revision']:
            raise ValueError('CHANGED_INPUT: the proposed selected voice profile changed; the candidate is retained.')
    intent = {'record': 'writing-application', 'id': 'APP-' + uuid.uuid4().hex, 'project': project,
        'candidate_id': ref['id'], 'candidate_kind': 'profile-change', 'candidate_version': ref['version'],
        'profile_family': family, 'profile_scope': scope, 'profile_path': candidate['profile'],
        'actor': actor, 'complete': False, 'status': 'APPLYING', 'before_revision': current['revision'],
        'intended_effect': _intended_effect(candidate, current)}
    writing_records.bank(root, intent)
    if family == 'architecture':
        result = narrative.update_architecture_profile(values['content'], current['profile_revision'], root)
    elif scope == 'workspace':
        result = writing_style.update_global_profile({**_voice_payload(candidate, current),
            'by': 'author' if actor['kind'] == 'human' else 'eigen:session'}, root,
            expected_current_provenance_revision=candidate['inputs']['provenance_revision'])
    else:
        # The real selection owner uses its own style-state identity, rather
        # than the profile adapter's intentionally smaller input identity.
        result = writing_style.save(project, {**values, 'expected_revision': candidate['inputs']['style_state_revision'],
            'by': 'author' if actor['kind'] == 'human' else 'eigen:session'}, root,
            selected_profile_revision=candidate['inputs']['selected_profile_revision'])
    after = snapshot(project, family, scope, root, candidate['profile'])
    application = writing_records.bank(root, {**intent, 'id': 'APP-' + uuid.uuid4().hex,
        'intent_id': intent['id'], 'complete': True, 'status': 'APPLIED', 'after_revision': after['revision'],
        'owner_record_id': result.get('record_id'), 'authority_effect': 'preferences applied; personal author confirmation not asserted'})
    writing_records.bank(root, {'record': 'writing-proposal-decision', 'id': 'DEC-' + uuid.uuid4().hex,
        'project': project, 'candidate_id': ref['id'], 'candidate_kind': 'profile-change',
        'proposal_version': ref['version'], 'decision': 'accepted', 'application_id': application['id'], 'actor': actor})
    return {**inspect(project, {'view': 'candidate', 'candidate_ref': ref}, root),
        'application_id': application['id'], 'effect': _summary(after)}


def _confirm(root, project, payload, actor):
    from laplace.writing import records as writing_records
    from laplace.pipeline import narrative
    if actor['kind'] != 'human':
        raise ValueError('Personal architecture confirmation requires an explicit human action; agents may propose or apply preferences.')
    with writing_records.proposal_write_lock(root):
        current = snapshot(project, 'architecture', 'workspace', root)
        if current['revision'] != payload['guards']['profile_input_revision']:
            raise ValueError('CHANGED_INPUT: inspect the current architecture fields before confirming them.')
        fields = current['effective_values']; chosen = payload['fields']
        if any(name not in fields for name in chosen):
            raise ValueError('Confirm only exact current architecture field identities.')
        if not payload['reason'].strip() or len(payload['reason'].encode()) > 4000:
            raise ValueError('An explicit bounded author confirmation reason is required.')
        confirmed = {name: value['field_revision'] for name, value in fields.items()
            if name in chosen or value.get('confirmed_his')}
        ident = 'DEC-' + uuid.uuid4().hex
        writing_records.bank(root, {'record': 'writing-proposal-decision', 'id': ident, 'project': project,
            'decision': 'confirm-profile', 'profile_family': 'architecture', 'profile_scope': 'workspace',
            'profile_path': narrative.ARCHITECTURE_PROFILE_PATH, 'actor': actor, 'confirmed_fields': confirmed,
            'reason': payload['reason'], 'before_revision': current['profile_revision']})
        narrative.update_architecture_profile(current['content'], current['profile_revision'], root,
            author_confirmation={'id': ident, 'project': project})
    return inspect(project, {'family': 'architecture', 'scope': 'workspace'}, root)
