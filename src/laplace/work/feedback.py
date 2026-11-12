"""Exact feedback targets for existing feedback/correction owners, not a new ledger."""
from __future__ import annotations

from laplace.writing import records as writing_records
import re
from pathlib import Path

TARGET_SCHEMA = 'laplace.feedback-target/1'
EFFECTS = ('observation_only', 'instruction')
TARGET_FIELDS = ('schema_version', 'kind', 'project', 'session_id', 'turn_id',
                 'reply_record_id', 'response_sha256')


def target_schema():
    return {'type': 'object', 'required': list(TARGET_FIELDS), 'properties': {
        'schema_version': {'enum': [TARGET_SCHEMA]}, 'kind': {'enum': ['response']},
        **{key: {'type': 'string', 'minLength': 1} for key in TARGET_FIELDS[2:]}},
        'additionalProperties': False}


def validate_target(project, target, root):
    from laplace.core.identity import require_schema_version
    from laplace.writing.records import index as index, index_lock as _LOCK
    if not isinstance(target, dict): raise ValueError('feedback_target must be an exact response target object.')
    require_schema_version(target, (TARGET_SCHEMA,), owner='Feedback target')
    if set(target) != set(TARGET_FIELDS) or target.get('kind') != 'response':
        raise ValueError('Response feedback requires exactly project/session/turn/reply/hash identities.')
    if any(not isinstance(target.get(key), str) or not target[key] for key in TARGET_FIELDS):
        raise ValueError('Response feedback target fields must be nonempty strings.')
    if target['project'] != project: raise ValueError('Response feedback belongs to another project.')
    if not re.fullmatch(r'[a-f0-9]{64}', target['response_sha256']):
        raise ValueError('Response feedback requires the exact saved response SHA256.')
    with _LOCK:
        idx = index(Path(root))
        rows = [row for row in idx.by_id.get(target['reply_record_id'], []) if row.get('record') == 'writing-reply']
        if len(rows) != 1: raise ValueError('Response feedback reply ID is missing or ambiguous.')
        row = rows[0]; turn = idx.turns.get(target['turn_id']) or {}
        if (idx.project(row) != project or idx.project(turn) != project
                or row.get('turn_id') != target['turn_id']
                or turn.get('session_id') != target['session_id']
                or row.get('session_id') not in (None, target['session_id'])
                or row.get('response_sha256') != target['response_sha256']):
            raise ValueError('Response feedback identities/hash do not match the saved owner response.')
        return dict(target)


def validate_feedback(project, payload, root):
    anchor = payload.get('anchor') if isinstance(payload.get('anchor'), dict) else {}
    # One owner value across HTTP/native top-level and retained anchor forms.
    # Explicit null is a schema error, never a way to hide an anchored declaration.
    values = {}
    for field in ('feedback_target', 'feedback_effect'):
        present = [(home, home[field]) for home in (payload, anchor) if field in home]
        if any(value is None for _home, value in present):
            raise ValueError(field + ' cannot be null; omit an optional declaration.')
        if len(present) == 2 and present[0][1] != present[1][1]:
            raise ValueError('Conflicting top-level and anchor ' + field + ' declarations.')
        values[field] = present[0][1] if present else None
    target, effect = values['feedback_target'], values['feedback_effect']
    if target is None and effect is None: return None, None
    if effect is None: effect = 'observation_only'
    if effect == 'observation_only' and payload.get('supersedes'):
        raise ValueError('Observation feedback cannot retire an instruction.')
    if effect not in EFFECTS: raise ValueError('feedback_effect must be observation_only or instruction.')
    if target is None: raise ValueError('Explicit response feedback requires its exact target.')
    return validate_target(project, target, root), effect
