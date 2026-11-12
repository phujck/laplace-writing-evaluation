"""Pure existing-Work review setup and explicit author approval renewal.

Definitions remain in Work; approvals/requests remain recipient-binding phase
rows. The Work dispatch lock serializes renewal replay and the two CAS guards.
No service, reviewer session, policy, delivery deadline or allowance is changed.
"""
from __future__ import annotations
import copy
import datetime as dt

ACTIONS = ('review-setup', 'renew', 'renew-request')


def _owners():
    from laplace.work import project_work, work_delivery
    return project_work, work_delivery


def _request(value):
    from laplace.work.project_work_review import _REQUEST
    if not isinstance(value, str) or not _REQUEST.fullmatch(value):
        raise ValueError('Retain a request_id of 8..96 letters, digits or ._:-.')
    return value


def _admit(project, payload, action, fields, required):
    from laplace.core import admission
    if not isinstance(payload, dict) or payload.get('action', action) != action:
        raise ValueError('Choose one exact review setup action.')
    if set(payload) - {'action', 'project', *fields} or set(required) - set(payload):
        raise ValueError('Review setup action does not match its closed owner contract.')
    admission.admit_owner_payload('work_delivery', {'action': action, **payload},
        _owners()[1].contract(), project=project)


def read_handle(project, payload):
    from laplace.work.feedback_route import handle_read
    return handle_read(project, payload)


def _action(project, payload, permitted, reason='', requires=()):
    properties = _owners()[1].contract()['properties']
    return {'operation': 'work_delivery', 'permitted': permitted, 'reason': reason,
        'http': {'method': 'POST', 'url': '/work/delivery'},
        'payload': {'project': project, **payload}, 'requires': list(requires),
        'fields': {key: copy.deepcopy(properties[key]) for key in requires},
        'fields_origin': 'work_delivery.contract'}


def _permission(root, project, door):
    if door.get('origin') == 'human':
        return {'permitted': True, 'kind': 'human', 'reason': ''}
    from laplace.writing import records, turn_admission
    turn = records.index(root).turns.get(door.get('turn_id')) or {}
    admitted = turn_admission.native_write_admission(root, project, turn.get('mode'), door.get('turn_id'))
    return {'permitted': bool(admitted['permitted']), 'kind': 'native',
        'reason': '' if admitted['permitted'] else admitted['code']}


def approval(binding, now=None):
    if binding.get('kind') != 'app-owned':
        return {'state': 'UNSUPPORTED', 'reason': 'External approvals are retained; this setup form configures app-owned reviewers only.'}
    if binding.get('state') != 'APPROVED':
        return {'state': 'UNAVAILABLE', 'reason': 'This reviewer approval is unavailable.'}
    try:
        expiry = dt.datetime.fromisoformat(binding['expires_at'])
        if expiry.tzinfo is None: raise ValueError('unqualified expiry')
    except (KeyError, TypeError, ValueError):
        return {'state': 'UNAVAILABLE', 'reason': 'Approval expiry is unavailable.'}
    expired = expiry <= (now or dt.datetime.now(dt.timezone.utc))
    return {'state': 'EXPIRED' if expired else 'CURRENT',
        'reason': 'Author approval expired.' if expired else 'Author-approved settings; provider readiness is separate.'}


def _renewals(task, request_id):
    return [row for row in task.get('deliveries') or ()
        if row.get('kind') == _owners()[1].BINDING
        and isinstance(row.get('approval'), dict) and row['approval'].get('request_id') == request_id]


def _receipt(row, replayed=False):
    delivery = _owners()[1]; meta = row['approval']
    intent = meta.get('intent')
    if (meta.get('schema_version') != 'laplace.review-approval/1' or meta.get('action') != 'renew'
            or meta.get('by') != 'author' or not isinstance(intent, dict)
            or delivery._digest(intent) != meta.get('intent_sha256')
            or intent.get('project') != row['project'] or intent.get('work_id') != row['work_id']
            or intent.get('recipient_binding_id') != row['id'] or intent.get('request_id') != meta.get('request_id')
            or intent.get('expected_binding_revision') != row.get('previous_revision')
            or intent.get('lifetime_s') != meta.get('lifetime_s')
            or row['revision'] != delivery._digest({'previous_revision': row['previous_revision'],
                'intent_sha256': meta['intent_sha256'], 'expires_at': row['expires_at']})):
        raise ValueError('Renewal custody does not match the retained approval and request.')
    return {'effect': 'renewed', 'project': row['project'], 'work_id': row['work_id'],
        'request_id': meta['request_id'], 'intent_sha256': meta['intent_sha256'],
        'previous_revision': row['previous_revision'], 'binding': delivery._public_binding(row),
        'replayed': replayed,
        'read': read_handle(row['project'], {'action': 'review-setup', 'work_id': row['work_id']}),
        'request_read': read_handle(row['project'], {'action': 'renew-request',
            'work_id': row['work_id'], 'request_id': meta['request_id']})}


def request(root, project, payload):
    _admit(project, payload, 'renew-request', {'work_id', 'request_id'}, {'work_id', 'request_id'})
    _request(payload['request_id'])
    work, delivery = _owners()
    with work.dispatch_lock(root):
        task = delivery._task_for(root, project, payload['work_id'])[1]
        matches = _renewals(task, payload['request_id'])
        common = {'schema_version': 'laplace.review-approval-request/1', 'project': project,
            'work_id': task['id'], 'request_id': payload['request_id'],
            'read': read_handle(project, {'action': 'renew-request', 'work_id': task['id'], 'request_id': payload['request_id']})}
        if len(matches) > 1:
            return {**common, 'effect': 'UNKNOWN', 'reason': 'Conflicting renewal custody; retain the original wire.'}
        if matches:
            try: receipt = _receipt(matches[0], replayed=True)
            except (KeyError, TypeError, ValueError):
                return {**common, 'effect': 'UNKNOWN', 'reason': 'Renewal receipt unavailable; retain the original wire.'}
            return {**common, 'effect': 'RECORDED', 'receipt': receipt}
        return {**common, 'effect': 'NONE', 'receipt': None,
            'meaning': 'No recorded renewal at this Work cut. Explicit retry keeps the exact original request and wire.'}


def renew(root, project, payload, door):
    fields = {'work_id', 'recipient_binding_id', 'expected_work_revision',
        'expected_binding_revision', 'request_id', 'lifetime_s'}
    _admit(project, payload, 'renew', fields, fields)
    if door.get('origin') != 'human':
        raise ValueError('Only the human author may renew a reviewer approval.')
    request_id = _request(payload['request_id'])
    work, delivery = _owners()
    intent_value = {'project': project, **{key: payload[key] for key in sorted(fields)}}
    intent = delivery._digest(intent_value)
    with work.dispatch_lock(root):
        task = delivery._task_for(root, project, payload['work_id'])[1]
        matches = _renewals(task, request_id)
        if matches:
            if len(matches) != 1 or matches[0]['approval']['intent_sha256'] != intent:
                raise ValueError('Renewal request_id already has another intent or ambiguous effect.')
            return _receipt(matches[0], replayed=True)
        if payload['expected_work_revision'] != work._task_revision(task):
            raise work.WorkConflict('Inspect the Work before renewing approval.', project, task['id'],
                expected=payload['expected_work_revision'], observed=work._task_revision(task), field='expected_work_revision')
        old = delivery._latest(task, delivery.BINDING, payload['recipient_binding_id'])
        if old is None or old.get('recipient_kind') != 'app-owned' or old.get('role') != 'review' or old.get('state') != 'APPROVED':
            raise ValueError('Renew an existing app-owned review binding of this Work.')
        if old['revision'] != payload['expected_binding_revision']:
            raise work.WorkConflict('Reviewer approval changed; inspect its current revision.', project, task['id'],
                expected=payload['expected_binding_revision'], observed=old['revision'], field='expected_binding_revision')
        now = dt.datetime.now(dt.timezone.utc)
        expiry = (now + dt.timedelta(seconds=payload['lifetime_s'])).isoformat()
        meta = {'schema_version': 'laplace.review-approval/1', 'action': 'renew',
            'request_id': request_id, 'intent_sha256': intent, 'intent': intent_value,
            'lifetime_s': payload['lifetime_s'], 'by': 'author'}
        row = {key: copy.deepcopy(old[key]) for key in ('record', 'kind', 'id', 'project', 'work_id',
            'role', 'recipient_kind', 'provider', 'model', 'effort', 'label', 'external', 'attachment') if key in old}
        row.update(state='APPROVED', revision=delivery._digest({'previous_revision': old['revision'],
            'intent_sha256': intent, 'expires_at': expiry}), previous_revision=old['revision'],
            approval_generation=old.get('approval_generation', 1) + 1, approval=meta,
            expires_at=expiry, ts=now.isoformat(), actor=delivery._actor(root, project, payload, door), approved_by='human')
        work._append(root, row)
        return _receipt(row)


def _matching(root, project, task, intended):
    from laplace.core import admission
    allowed = {'kind', 'provider', 'model', 'effort', 'label', 'lifetime_s'}
    if not isinstance(intended, dict) or set(intended) - allowed or intended.get('kind') != 'app-owned':
        raise ValueError('Inspect exact app-owned reviewer settings.')
    work, delivery = _owners()
    wire = {'action': 'bind', 'work_id': task['id'], 'expected_work_revision': work._task_revision(task), **intended}
    admission.admit_owner_payload('work_delivery', wire, delivery.contract(), project=project)
    if not intended.get('provider') or not intended.get('model'):
        raise ValueError('Reviewer settings need explicit provider and model.')
    content = delivery.binding_content(task['id'], intended)
    ident = 'RB-' + delivery._digest(content)[7:31]
    row = delivery._latest(task, delivery.BINDING, ident)
    return {'state': 'MATCHED' if row else 'NONE', 'binding': delivery._public_binding(row) if row else None,
        'approval': approval(delivery._public_binding(row)) if row else None,
        'meaning': 'Current desired settings standing only; this does not attribute a lost bind to the caller.'}


def prepare(root, project, payload, door):
    fields = {'work_id', 'offset', 'limit', 'cut', 'intended_binding'}
    _admit(project, payload, 'review-setup', fields, {'work_id'})
    from laplace.work import project_work_review as review
    from laplace.work.project_work_views import handle as work_read
    work, delivery = _owners()
    with work.dispatch_lock(root):
        task = delivery._task_for(root, project, payload['work_id'])[1]
        definitions = review.obligations(copy.deepcopy(list(task.get('review_obligations') or [])))
        revision = work._task_revision(task)
        permission = _permission(root, project, door)
        latest = delivery.latest_bindings(task)
        now = dt.datetime.now(dt.timezone.utc)
        rows = [{'binding': delivery._public_binding(row), 'approval': approval(delivery._public_binding(row), now)}
            for row in sorted(latest.values(), key=lambda row: row['id'])]
        cut = delivery._digest({'work_revision': revision, 'bindings': rows})
        if payload.get('cut') and payload['cut'] != cut:
            conflict = work.WorkConflict('Reviewer approvals changed between pages; inspect one new cut.',
                project, task['id'], expected=payload['cut'], observed=cut, field='cut')
            conflict.details['next_reads'] = [read_handle(project, {'action': 'review-setup', 'work_id': task['id']})]
            raise conflict
        offset, limit = payload.get('offset', 0), payload.get('limit', delivery.PAGE)
        if offset > len(rows): raise ValueError('Reviewer page begins beyond this setup cut.')
        common = {'action': 'review-setup', 'work_id': task['id'], 'limit': limit}
        own = read_handle(project, {**common, 'offset': offset, 'cut': cut})
        human = permission['kind'] == 'human'
        for entry in rows[offset:offset + limit]:
            binding = entry['binding']; can = human and binding['kind'] == 'app-owned'
            action = _action(project, {'action': 'renew', 'work_id': task['id'], 'recipient_binding_id': binding['id'],
                'expected_work_revision': revision, 'expected_binding_revision': binding['revision']}, can,
                '' if can else 'Renewal is available only to the author for app-owned reviewers.', ('request_id', 'lifetime_s'))
            action['request_read'] = {**read_handle(project, {'action': 'renew-request', 'work_id': task['id']}),
                'requires': ['request_id'], 'request_field': 'request'}
            entry['actions'] = {'renew': action}
        controls = {row['id']: {'editable': not (row.get('scope') == 'closure' or 'closure_work_id' in row or 'source_contract' in row),
            'reason': 'Specialised closure/source-contract question; preserve its complete definition.' if row.get('scope') == 'closure' or 'closure_work_id' in row or 'source_contract' in row else '',
            'read': work_read(project, {'view': 'review', 'id': task['id'], 'obligation_id': row['id']})}
            for row in definitions}
        save = {'permitted': permission['permitted'], 'reason': permission['reason'], 'operation': 'task',
            'http': {'method': 'POST', 'url': '/work/task'}, 'payload': {'project': project, 'id': task['id'],
                'title': task['title'], 'goal': task['goal'], 'expected_work_revision': revision,
                'review_obligations': copy.deepcopy(definitions)}, 'read': own,
            'recovery': 'Inspect and compare exact definitions. Matching standing does not attribute a lost write; explicit author adoption is required.'}
        bind = _action(project, {'action': 'bind', 'work_id': task['id'], 'expected_work_revision': revision,
            'kind': 'app-owned'}, permission['permitted'], permission['reason'], ('provider', 'model', 'effort', 'label', 'lifetime_s'))
        bind['defaults'] = {'effort': {'value': delivery.DEFAULT_BINDING_EFFORT, 'origin': 'work_delivery.bind'},
            'lifetime_s': {'value': delivery.DEFAULT_BINDING_LIFETIME_S, 'minimum': 60,
                'maximum': delivery.MAX_BINDING_LIFETIME_S, 'origin': 'work_delivery.bind'},
            'provider': {'value': None, 'origin': 'explicit author choice'}, 'model': {'value': None, 'origin': 'explicit author choice'}}
        result = {'schema_version': 'laplace.review-setup/1', 'project': project,
            'work': {'id': task['id'], 'title': task['title'], 'goal': task['goal'], 'revision': revision},
            'review_obligations': definitions, 'question_controls': controls,
            'question_contract': {'scopes': list(review.SCOPES),
                'ordinary_scopes': [scope for scope in review.SCOPES if scope != 'closure'],
                'maximum': review.MAX_OBLIGATIONS,
                'id_pattern': review._OBLIGATION.pattern, 'max_inputs': review.MAX_PINS,
                'defaults': {'required': {'value': True, 'origin': 'project_work_review.obligations'},
                    'independent': {'value': True, 'origin': 'project_work_review.obligations'},
                    'inputs': {'value': [], 'origin': 'project_work_review.obligations'}},
                'ordinary_fields': ['id', 'label', 'scope', 'required', 'independent', 'inputs'],
                'specialised_fields': ['closure_work_id', 'source_contract'],
                'fields': {'id': {'type': 'string', 'pattern': review._OBLIGATION.pattern, 'stable': True},
                    'label': {'type': 'string', 'minLength': 1, 'maxLength': 200},
                    'scope': {'enum': list(review.SCOPES), 'requires_explicit_choice': True},
                    'required': {'type': 'boolean', 'default': True},
                    'independent': {'type': 'boolean', 'default': True},
                    'inputs': {'type': 'array', 'maxItems': review.MAX_PINS, 'items': {'type': 'string', 'format': 'repository-relative-path'}}},
                'origin': 'project_work_review.obligations'},
            'bindings': {'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset, 'limit': limit,
                'cut': cut, 'complete': offset + limit >= len(rows),
                'next_read': read_handle(project, {**common, 'offset': offset + limit, 'cut': cut}) if offset + limit < len(rows) else None,
                'restart_read': read_handle(project, common)},
            'actions': {'save_questions': save, 'bind': bind,
                'inspect_binding': {**read_handle(project, common), 'requires': ['intended_binding'], 'request_field': 'request'}},
            'provider_catalogue_read': {'http': {'method': 'GET', 'url': '/authoring/providers'}},
            'review_read': work_read(project, {'view': 'review', 'id': task['id']}) if definitions else None,
            'events_read': read_handle(project, {'action': 'status', 'work_id': task['id']}), 'read': own}
        if 'intended_binding' in payload:
            result['matching_binding'] = _matching(root, project, task, payload['intended_binding'])
        return result


def handle(root, project, payload, door):
    action = payload.get('action')
    if action == 'review-setup': return prepare(root, project, payload, door)
    if action == 'renew-request': return request(root, project, payload)
    if action == 'renew': return renew(root, project, payload, door)
    raise ValueError('Unknown review setup action.')
