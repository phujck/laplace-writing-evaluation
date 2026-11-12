"""The Work review lifecycle: implementation handoff, scoped review, synthesis and linked follow-up.

Ownership
  This is a section of the project_work owner (WORK-editor-work-review-lifecycle-20261015). Its durable truth
  is rows of the same ledger (``corpus_friction/work_orders.jsonl``) written by ``project_work._append`` under
  ``project_work.dispatch_lock``; ``project_work`` folds them into each Work's ``phases`` (never into its
  specification), resolves the ``review`` facet below and gates final completion with
  ``completion_problem``. Views project the facet; ``writing_tools`` (native ``work_review``) and
  ``project_work_surface`` (``POST /work/review``) only admit. No scheduler, watcher, token owner or model call.

Opt-in obligations
  A Work becomes review-managed when its specification carries ``review_obligations`` (authored through the
  existing guarded ``task`` edit). Each obligation names a scope (source, owner-native-http, human-desktop,
  human-narrow, live, guide, closure, other), whether it is required, whether its review must be independent,
  and the repository paths it consumes. Legacy Work without the field keeps its hashes and completion meaning.

Phases (append-only ``project-work-phase`` rows; one stable id per request_id, so a replay never appends twice)
  handoff    an implementation handed off for review: the object (source profile, repository, base,
             checkpoint, aggregate), exact per-file pins, public evidence and the producing actor. It does not
             satisfy any obligation and launches nothing.
  review     one scoped disposition (ACCEPT/HOLD/REJECT) of one obligation on one handoff, with findings, pins
             and the reviewer. Independence is derived from the two actual actors: INDEPENDENT (both identified
             and different), SELF (the producer reviewing itself: a self-assessment, never independent
             acceptance) or UNKNOWN (identity unproved). A label or role string never decides it.
  synthesis  consumes exact handoff/review ids, records the outcome and the follow-ups it asks for.
  followup   creates or reuses ONE child per (parent, origin finding) through the existing task owner, then
             joins it by the chosen closure: optional (membership only), required (a closure obligation on the
             parent) or prerequisite (parent depends_on). A failed join is recorded as PENDING with the exact
             child; the same request completes it. Nothing is deleted or re-run.

Actors
  native    the caller's admitted writing turn of this project; its session is the identity (provider:model,
             turn and any dispatch lineage are recorded beside it);
  external  a named reviewer with pinned PUBLIC repository evidence (core.perimeter.public_repository_path),
             optional profile/scope qualifiers. Only the author at the human door can attest it (verified). Claimed
             through a native turn it stays an unverified claim of that session: SELF against the same session,
             UNKNOWN otherwise; a file hash proves bytes, never who reviewed them (repair1 WR-R1);
  human     the author at the human door.
  An external or native identity is never invented from a payload label.

Coverage and intent (repair1 WR-R2)
  A handoff pins every declared input of each obligation it covers (or states only an aggregate). A review covers
  exactly the obligation's declared handed-off inputs (all inputs when none are declared); an aggregate-only handoff
  gives a coarse (UNKNOWN) review. Each review records the Work's material intent (goal, kind, sections, logical
  target, anchor, reader basis, obligation id, and those of its containing Works); a later change of that intent
  makes the review STALE. Adding obligations or follow-up membership does not touch other reviews.

Follow-up custody (repair1 WR-R3)
  The phase row is written FIRST (PENDING, with the canonical request, its guard and the original actor), then the
  child, the join and a completion row. A replay compares every effect-bearing field and the original identity; a
  recovery may come from another admitted actor (recorded as recovered_by, the original actor stays) and is admitted
  only while the parent differs from its original guard by this operation's own join. Receipts are the owner's own
  combined append receipts when contiguous; otherwise none is fabricated.

Action templates (Eigen continuity, Root e716/a6d0)
  ``contract`` carries every lexical and size limit the recording validators enforce (request id, obligation id,
  summary/finding text, findings, evidence, pins); ``phase_schema`` is one phase's closed request; ``review_template``
  is the complete owner-filled review payload whose verdict stays null until the reviewer authors it; ``preflight``
  checks a whole proposed payload (schema, current guard, recorded handoff/obligation, exact pins) and records nothing.
  A proposed or pre-flighted verdict is not a recorded review.

Currentness
  Legacy pins are compared with canonical current file bytes on read. An explicit handoff source_basis selects
  a completed development Source candidate through its owner; reviews retain that exact qualified basis and their
  consumed pin subset, never a similarly named canonical file. Expired write authority does not erase historical
  evidence, but review admission still proves the actual Source holder/evaluator identity. A changed pin makes only the obligations whose reviews
  consumed it STALE; a changed obligation definition makes only that obligation STALE; recorded verdicts stay
  as history. A review with only an aggregate and no per-file pins is coarse: UNKNOWN, never CURRENT.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PHASE_RECORD = 'project-work-phase'
#: never 'work-order': the shared ledger's engine readers (engine_ledger.is_work_order) would list a phase as open work
PHASE_KIND = 'work-phase'
PHASES = ('handoff', 'review', 'synthesis', 'followup')
SCOPES = ('source', 'owner-native-http', 'human-desktop', 'human-narrow', 'live', 'guide', 'closure', 'other')
VERDICTS = ('ACCEPT', 'HOLD', 'REJECT')
CLOSURES = ('optional', 'required', 'prerequisite')
MAX_OBLIGATIONS, MAX_PINS, MAX_EVIDENCE, MAX_FINDINGS, MAX_TEXT = 24, 64, 8, 20, 2000
MAX_FINDING_ID = 80
MAX_OBJECT_TEXT, MAX_ACTOR_TEXT, MAX_ROLE_TEXT = 200, 160, 80   # handoff object fields; actor name/profile/scope; actor role
_REQUEST = re.compile(r'[A-Za-z0-9._:-]{8,96}')
_OBLIGATION = re.compile(r'[a-z0-9][a-z0-9._-]{0,47}')
_SHA = re.compile(r'sha256:[0-9a-f]{64}')
#: The closed limits the recording validators enforce, published once (contract, templates, preflight and help read it).
LIMITS = {'request_id': '^' + _REQUEST.pattern + '$', 'obligation_id': '^' + _OBLIGATION.pattern + '$', 'summary': MAX_TEXT,
          'findings': MAX_FINDINGS, 'finding_id': MAX_FINDING_ID, 'finding_summary': MAX_TEXT, 'evidence': MAX_EVIDENCE,
          'pins': MAX_PINS, 'obligations': MAX_OBLIGATIONS, 'verdicts': list(VERDICTS),
          'object_field': MAX_OBJECT_TEXT, 'actor': MAX_ACTOR_TEXT, 'actor_role': MAX_ROLE_TEXT, 'sha256': '^' + _SHA.pattern + '$'}


def _digest(value) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _text(value, field, *, required=False, limit=MAX_TEXT) -> str:
    if value is None and not required:
        return ''
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise ValueError('work_review %s must be text of at most %d characters%s.' % (field, limit, ' and not empty' if required else ''))
    return value.strip()


# ---------------------------------------------------------------------------------------------- obligations

def obligations(value) -> list[dict]:
    """Validate and normalise an authored ``review_obligations`` list (the specification field)."""
    if not isinstance(value, list) or len(value) > MAX_OBLIGATIONS:
        raise ValueError('review_obligations must be a list of at most %d obligations.' % MAX_OBLIGATIONS)
    out, seen = [], set()
    for item in value:
        if not isinstance(item, dict) or set(item) - {'id', 'scope', 'label', 'required', 'independent', 'inputs', 'closure_work_id', 'source_contract'}:
            raise ValueError('A review obligation has id, scope, label and optional required, independent, inputs, source_contract.')
        ident = item.get('id')
        if not isinstance(ident, str) or not _OBLIGATION.fullmatch(ident) or ident in seen:
            raise ValueError('Each review obligation needs a unique lowercase id.')
        if item.get('scope') not in SCOPES:
            raise ValueError('Review obligation scope must be one of ' + ', '.join(SCOPES) + '.')
        inputs = item.get('inputs', [])
        if not isinstance(inputs, list) or len(inputs) > MAX_PINS or any(not _safe_path(path) for path in inputs):
            raise ValueError('Review obligation inputs are repository-relative paths.')
        row = {'id': ident, 'scope': item['scope'], 'label': _text(item.get('label'), 'obligation label', required=True, limit=200),
               'required': item.get('required', True) is not False, 'independent': item.get('independent', True) is not False,
               'inputs': list(dict.fromkeys(inputs))}
        if item.get('closure_work_id') is not None:
            if not isinstance(item['closure_work_id'], str) or item['scope'] != 'closure':
                raise ValueError('closure_work_id belongs to a closure obligation.')
            row['closure_work_id'] = item['closure_work_id']
        if item.get('source_contract') is not None:
            # an optional typed binding to one declared consumer of an operation's source contract (shape only here; the
            # handoff that covers it resolves and publishes it, laplace.work.source_contracts)
            if item['scope'] != 'source':
                raise ValueError('A source_contract binding belongs to a source-scope review obligation.')
            from laplace.work import source_contracts
            row['source_contract'] = source_contracts.binding(item['source_contract'])
        seen.add(ident)
        out.append(row)
    return out


def _safe_path(path) -> bool:
    return isinstance(path, str) and bool(path) and not path.startswith('/') and '..' not in Path(path).parts and '\\' not in path


def _file_digest(root, path, cache=None):
    from laplace.work import project_work
    from laplace.core import perimeter
    try:
        target = perimeter.public_repository_path(root, path)
    except ValueError:
        return None
    if not target.is_file():
        return None
    return 'sha256:' + project_work._evidence_digest(target.resolve(), cache)   # the owner digest is bare hex; pins are prefixed


PIN_PREVIEW = 6   # names shown per category in a mismatch diagnostic; a display bound only, never an input limit


def _pin_mismatch(expected: dict, supplied) -> str:
    """Bounded diagnostic of an exact pin comparison that already failed: totals and every category's full count, with at
    most PIN_PREVIEW names each (stated as a preview). It reports; it never relaxes or decides the comparison."""
    given = supplied if isinstance(supplied, dict) else {}
    missing = sorted(set(expected) - set(given))
    extra = sorted(set(given) - set(expected))
    different = sorted(path for path in set(expected) & set(given) if given[path] != expected[path])

    def part(label, names):
        shown = names[:PIN_PREVIEW]
        return '%s %d%s' % (label, len(names), (' (' + ('first %d: ' % len(shown) if len(names) > len(shown) else '')
                                                + ', '.join(str(name)[:160] for name in shown) + ')') if names else '')
    shape = '' if isinstance(supplied, dict) else ' Supplied pins are not a {path: sha256} object (%s).' % type(supplied).__name__
    return ('Expected %d handed-off pin(s), supplied %d: %s; %s; %s.%s'
            % (len(expected), len(given), part('missing', missing), part('extra', extra), part('different digest', different), shape))


def _pins(root, value, field) -> dict:
    """Exact current per-file pins {path: sha256}; each must equal the file's bytes now."""
    if value is None:
        return {}
    if not isinstance(value, dict) or len(value) > MAX_PINS:
        raise ValueError('%s maps at most %d repository paths to sha256 digests.' % (field, MAX_PINS))
    from laplace.core import perimeter
    out = {}
    for path, digest in value.items():
        if not _safe_path(path) or not isinstance(digest, str) or not _SHA.fullmatch(digest):
            raise ValueError('%s entries are repository-relative paths with sha256:<64 hex> digests.' % field)
        perimeter.public_repository_path(root, path)   # private/runtime/symlink refused before hashing
        observed = _file_digest(root, path)
        if observed != digest:
            raise ValueError('CHANGED_INPUT: %s %s does not have the stated bytes now (observed %s).' % (field, path, observed or 'missing'))
        out[path] = digest
    return out


def _evidence(root, value) -> list[dict]:
    """Public repository evidence: exact path + sha256, read through repository coordinates only."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_EVIDENCE or any(not isinstance(row, dict) or set(row) != {'path', 'sha256'} for row in value):
        raise ValueError('evidence lists at most %d exact {path, sha256} entries.' % MAX_EVIDENCE)
    pinned = _pins(root, {row['path']: row['sha256'] for row in value}, 'evidence')
    return [{'path': path, 'sha256': digest} for path, digest in pinned.items()]


# ---------------------------------------------------------------------------------------------- actors

def _actor(root, project, payload, door) -> dict:
    """The recording identity. ``door`` is what the admitting door proved: {'origin': 'native', 'turn_id'} or
    {'origin': 'human'}. An external actor is accepted only with pinned public evidence, attested by the door."""
    supplied = payload.get('actor')
    if supplied is not None and (not isinstance(supplied, dict) or set(supplied) - {'actor', 'role', 'origin', 'evidence', 'profile', 'scope'}):
        raise ValueError('actor has actor, role, origin and (external only) evidence, profile and scope.')
    supplied = supplied or {}
    role = _text(supplied.get('role'), 'actor role', limit=MAX_ROLE_TEXT) or ('reviewer' if payload.get('phase') == 'review' else 'producer')
    if door.get('origin') == 'native':
        turn = _native_turn(root, project, door.get('turn_id'))
        settings = turn.get('provider_settings') if isinstance(turn.get('provider_settings'), dict) else {}
        native = {'actor': '%s:%s' % (settings.get('provider') or 'unknown', settings.get('model') or 'unknown'),
                  'session_id': turn.get('session_id'), 'turn_id': turn['id'],
                  **{key: turn[key] for key in ('dispatch_id', 'parent_turn_id') if turn.get(key)}}
    else:
        native = None
    if supplied.get('origin') == 'external':
        name = _text(supplied.get('actor'), 'actor', required=True, limit=MAX_ACTOR_TEXT)
        evidence = _evidence(root, supplied.get('evidence'))
        if not evidence:
            raise ValueError('An external actor needs pinned public evidence of its work.')
        qualifiers = {key: _text(supplied.get(key), 'actor ' + key, limit=MAX_ACTOR_TEXT) for key in ('profile', 'scope') if supplied.get(key)}
        if native:
            # a native turn can only CLAIM an external reviewer: the claim belongs to that session, never verified
            attestation = {'door': 'native', 'by': native['actor'], 'session_id': native['session_id'], 'turn_id': native['turn_id']}
        else:
            attestation = {'door': 'human', 'by': 'author'}
        return {'actor': name, 'role': role, 'origin': 'external', 'evidence': evidence, **qualifiers,
                'attestation': attestation, 'verified': attestation['door'] == 'human'}
    if supplied.get('origin') not in (None, door.get('origin')) or supplied.get('actor') or supplied.get('evidence') \
            or supplied.get('profile') or supplied.get('scope'):
        raise ValueError('The actor identity comes from the admitting door; a native or external identity cannot be claimed by label.')
    if native:
        return {**native, 'role': role, 'origin': 'native'}
    return {'actor': 'author', 'role': role, 'origin': 'human'}


def _native_turn(root, project, turn_id) -> dict:
    from laplace.writing import records
    if not isinstance(turn_id, str) or not turn_id:
        raise ValueError('A native work_review needs the caller\'s admitted writing turn.')
    turn = records.index(root).turns.get(turn_id)
    if not turn or turn.get('project') != project:
        raise ValueError('The admitted writing turn does not belong to this project.')
    return turn


def independence(reviewer: dict, producer: dict | None) -> str:
    """INDEPENDENT, SELF or UNKNOWN from the two recorded identities (never from a role label or model name).

    A native identity is its writing session (the context boundary): the same session reviewing its own handoff is
    SELF; another session, a dispatched child included, is INDEPENDENT whatever model it runs. An external identity
    is its author-attested name with pinned public evidence; an external name claimed through a native turn proves
    only that session (SELF against it, UNKNOWN otherwise); the human door is the author."""
    if not producer or not reviewer:
        return 'UNKNOWN'
    left, right = identity(reviewer), identity(producer)
    if left is None or right is None:
        return 'UNKNOWN'
    if 'claim' in (left[0], right[0]):
        # an unverified claim made through a native session proves only that session: SELF against itself
        sessions = {left[1] if left[0] in {'claim', 'native'} else None, right[1] if right[0] in {'claim', 'native'} else None}
        return 'SELF' if len(sessions) == 1 and None not in sessions else 'UNKNOWN'
    return 'SELF' if left == right else 'INDEPENDENT'


def identity(actor):
    """The identity key of one recorded actor: ('native', session), ('external', name) when the author attested it,
    ('claim', session) for an external name claimed through a native turn, ('human', name); None when unproved."""
    if not isinstance(actor, dict):
        return None
    origin = actor.get('origin')
    if origin == 'external':
        attestation = actor.get('attestation') or {}
        if not actor.get('evidence'):
            return None
        if attestation.get('door') == 'human':
            return ('external', actor.get('actor'))
        if attestation.get('door') == 'native' and attestation.get('session_id'):
            return ('claim', attestation['session_id'])
        return None
    if origin == 'native':
        return ('native', actor.get('session_id')) if actor.get('turn_id') and actor.get('session_id') else None
    return ('human', actor.get('actor')) if origin == 'human' else None


# ---------------------------------------------------------------------------------------------- recording

#: THE PHASE DEFINITIONS (repair1 WI-R1): each phase's payload fields beyond the common envelope (required, optional), which
#: of them the owner fills from the inspected facet (basis) and what a person or agent authors (inputs: payload path, input
#: kind, label). The declared schema's oneOf (PHASE_FIELDS), the human recorder and the native preparation
#: (``preparation``) all derive from this one table; the frontend keeps no per-phase field or basis list of its own.
PHASE_SPEC = {
    'handoff': {'required': (), 'optional': ('obligations', 'object', 'pins', 'source_basis', 'source_context', 'source_subject'), 'basis': (),
                'title': 'Hand off for review',
                'says': 'Records the implementation and its exact file pins for scoped review. Nothing is launched, and a handoff satisfies no obligation.',
                'inputs': (('obligations', 'lines', 'Obligations handed off (ids, one per line)'), ('object.kind', 'text', 'What is handed off'),
                           ('object.base', 'text', 'Base'), ('object.checkpoint', 'text', 'Checkpoint'),
                           ('object.aggregate', 'text', 'Aggregate digest (when files are not pinned)'),
                           ('pins', 'pins', 'Exact file pins: "path sha256:<digest>" per line'))},
    'review': {'required': ('handoff_id', 'obligation_id', 'verdict'), 'optional': ('findings', 'pins'), 'basis': ('handoff_id',),
               'title': 'Record a scoped review',
               'says': 'Records one disposition of one obligation on the handed-off bytes. Independence comes from the recorded identities, never from a label.',
               'inputs': (('obligation_id', 'choice', 'Obligation'), ('verdict', 'choice', 'Disposition'),
                          ('findings', 'findings', 'Findings: "ID: summary" per line'))},
    'synthesis': {'required': ('consumes',), 'optional': (), 'basis': ('consumes',),
                  'title': 'Record the synthesis',
                  'says': 'Records the outcome over the exact handoff and review records. It does not complete the Work.', 'inputs': ()},
    'followup': {'required': ('finding', 'closure', 'child'), 'optional': ('synthesis_id',), 'basis': ('synthesis_id',),
                 'title': 'Create a linked follow-up',
                 'says': 'Creates or reuses one linked Work for a finding and joins it by its closure. Creating Work does not start a session.',
                 'inputs': (('finding', 'text', 'Finding'), ('closure', 'choice', 'Closure'), ('child.title', 'text', 'Follow-up title'),
                            ('child.goal', 'area', 'Follow-up completion condition'),
                            ('child.logical_target.kind', 'text', 'Follow-up target kind (optional, e.g. node)'),
                            ('child.logical_target.node_id', 'text', 'Follow-up target id (optional)'))}}
#: The follow-up child's optional logical_target (source-contract slice, 2026-10-21): the task owner's own field
#: (project_work.task keeps it; MATERIAL_INTENT consumes it), carried as task intent. It is never write authority or a
#: canonical owned reference. Omitted, the canonical request, its replay and its recovery are byte-identical to before.
CHILD_TARGET = {'type': 'object', 'additionalProperties': False, 'minProperties': 1,
                'properties': {'kind': {'type': 'string'}, 'node_id': {'type': 'string'}}}
CHILD_KEYS = ('id', 'title', 'goal', 'kind', 'section_ids', 'logical_target')
#: inputs every phase accepts
COMMON_INPUTS = (('summary', 'area', 'Summary'), ('evidence', 'evidence', 'Public evidence: "path sha256:<digest>" per line'))
VERDICT_LABELS = {'ACCEPT': 'Accept', 'HOLD': 'Hold', 'REJECT': 'Reject'}
CLOSURE_LABELS = {'optional': 'Optional · linked only', 'required': 'Required · the parent waits for it',
                  'prerequisite': 'Prerequisite · the parent depends on it'}
#: Each phase's required and optional fields beyond the common envelope (from PHASE_SPEC); the declared schema's oneOf states
#: them, so the native and HTTP doors refuse an unknown or misplaced field through the one admission (core.admission).
PHASE_FIELDS = {phase: (spec['required'], spec['optional']) for phase, spec in PHASE_SPEC.items()}


def contract() -> dict:
    sha = {'type': 'string', 'pattern': '^' + _SHA.pattern + '$'}
    pins = {'type': 'object', 'maxProperties': MAX_PINS, 'additionalProperties': sha}
    evidence = {'type': 'array', 'maxItems': MAX_EVIDENCE, 'items': {'type': 'object', 'required': ['path', 'sha256'], 'additionalProperties': False,
                'properties': {'path': {'type': 'string', 'minLength': 1}, 'sha256': sha}}}
    properties = {
                'project': {'type': 'string'}, 'id': {'type': 'string'}, 'phase': {'enum': list(PHASES)},
                'request_id': {'type': 'string', 'pattern': LIMITS['request_id']}, 'expected_work_revision': {'type': 'string'},
                'summary': {'type': 'string', 'maxLength': MAX_TEXT}, 'evidence': evidence, 'pins': pins,
                'source_basis': {'type': 'object', 'additionalProperties': False, 'required': ['grant_id', 'candidate_id'],
                                 'properties': {'grant_id': {'type': 'string', 'minLength': 1}, 'candidate_id': {'type': 'string', 'minLength': 1}}},
                'source_context': {'type': 'object', 'additionalProperties': False, 'required': ['windows'],
                                   'properties': {'windows': {'type': 'array', 'maxItems': 64, 'items': {
                                       'type': 'object', 'additionalProperties': False,
                                       'required': ['path', 'line_start', 'line_end'], 'properties': {
                                           'path': {'type': 'string', 'minLength': 1},
                                           'line_start': {'type': 'integer', 'minimum': 1},
                                           'line_end': {'type': 'integer', 'minimum': 1}}}}}},
                # The authored cumulative-subject request (closure contract 2026-11-02): an explicitly admitted READ-ONLY carry
                # manifest and the typed acceptance stage. The Source owner derives and validates the subject; never write authority.
                'source_subject': {'type': 'object', 'additionalProperties': False, 'minProperties': 1, 'properties': {
                    'carry': {'type': 'object'},
                    # F1: explicitly selected earlier production of separately attributed commissions of this Work and original
                    # parent, and the declared accepted base its change provenance is judged against. The Source owner validates both.
                    'prior': {'type': 'object', 'additionalProperties': False, 'required': ['grants'], 'properties': {
                        'grants': {'type': 'array', 'minItems': 1, 'maxItems': 16, 'uniqueItems': True, 'items': {'type': 'string', 'minLength': 1}}}},
                    'accepted_base': {'type': 'string', 'pattern': '^[0-9a-f]{40}([0-9a-f]{24})?$'},
                    'stage': {'type': 'object', 'additionalProperties': False, 'required': ['id', 'pre_source_review', 'post_adoption'], 'properties': {
                        'id': {'type': 'string', 'minLength': 1, 'maxLength': 96},
                        'pre_source_review': {'type': 'array', 'minItems': 1, 'maxItems': 16, 'items': {'type': 'string', 'minLength': 1, 'maxLength': 600}},
                        'post_adoption': {'type': 'array', 'maxItems': 16, 'items': {'type': 'string', 'minLength': 1, 'maxLength': 600}},
                        'authority': {'type': 'array', 'maxItems': 8, 'items': {'type': 'object', 'required': ['path', 'sha256'], 'additionalProperties': False,
                                      'properties': {'path': {'type': 'string', 'minLength': 1, 'maxLength': 400}, 'sha256': sha}}},
                        'summary': {'type': 'string', 'maxLength': 2000}}}}},
                'actor': {'type': 'object', 'additionalProperties': False, 'properties': {
                    'actor': {'type': 'string', 'maxLength': MAX_ACTOR_TEXT}, 'role': {'type': 'string', 'maxLength': MAX_ROLE_TEXT},
                    'origin': {'enum': ['native', 'external', 'human']}, 'evidence': evidence,
                    'profile': {'type': 'string', 'maxLength': MAX_ACTOR_TEXT}, 'scope': {'type': 'string', 'maxLength': MAX_ACTOR_TEXT}}},
                'obligations': {'type': 'array', 'maxItems': MAX_OBLIGATIONS, 'items': {'type': 'string', 'pattern': LIMITS['obligation_id']}},
                'object': {'type': 'object', 'additionalProperties': False, 'properties': {
                    key: {'type': 'string', 'maxLength': MAX_OBJECT_TEXT} for key in ('kind', 'profile', 'repository', 'base', 'checkpoint', 'aggregate')}},
                'handoff_id': {'type': 'string'}, 'obligation_id': {'type': 'string', 'pattern': LIMITS['obligation_id']}, 'verdict': {'enum': list(VERDICTS)},
                'findings': {'type': 'array', 'maxItems': MAX_FINDINGS, 'items': {'type': 'object', 'required': ['id', 'summary'], 'additionalProperties': False,
                             'properties': {'id': {'type': 'string', 'minLength': 1, 'maxLength': MAX_FINDING_ID},
                                            'summary': {'type': 'string', 'minLength': 1, 'maxLength': MAX_TEXT}}}},
                'consumes': {'type': 'array', 'items': {'type': 'string'}},
                'synthesis_id': {'type': 'string'}, 'finding': {'type': 'string'}, 'closure': {'enum': list(CLOSURES)},
                'child': {'type': 'object', 'additionalProperties': False, 'required': ['title', 'goal'], 'properties': {
                    'id': {'type': 'string'}, 'title': {'type': 'string'}, 'goal': {'type': 'string'}, 'kind': {'type': 'string'},
                    'section_ids': {'type': 'array', 'items': {'type': 'string'}}, 'logical_target': CHILD_TARGET}}}
    return {'type': 'object', 'required': ['id', 'phase', 'request_id', 'expected_work_revision'], 'additionalProperties': False,
            'properties': properties, 'dependentRequired': {'source_context': ['source_basis'], 'source_subject': ['source_basis', 'source_context']},
            'oneOf': [_phase_branch(phase, properties) for phase in PHASE_FIELDS]}


def _phase_branch(phase, properties):
    """One phase: its const, its required fields, its own fields (typed) and none of another phase's fields."""
    required, optional = PHASE_FIELDS[phase]
    own = {*required, *optional}
    foreign = sorted({name for other, fields in PHASE_FIELDS.items() if other != phase for name in (*fields[0], *fields[1])} - own)
    return {'required': list(required), 'properties': {'phase': {'const': phase}, **{name: properties[name] for name in (*required, *optional)}},
            'not': {'anyOf': [{'required': [name]} for name in foreign]}}


def phase_schema(phase) -> dict:
    """ONE phase's closed request schema: the common envelope plus exactly that phase's own fields, carrying every limit
    the recording validators enforce. Derived from contract() and PHASE_FIELDS; there is no second field list."""
    if phase not in PHASE_FIELDS:
        raise ValueError('work_review phase is one of ' + ', '.join(PHASES) + '.')
    base = contract()
    properties = base['properties']
    owned = {name for fields in PHASE_FIELDS.values() for group in fields for name in group}
    required, optional = PHASE_FIELDS[phase]
    names = [name for name in properties if name not in owned] + [name for name in (*required, *optional)]
    schema = {'type': 'object', 'additionalProperties': False, 'required': [*base['required'], *required],
              'properties': {**{name: properties[name] for name in names}, 'phase': {'const': phase}}}
    if phase == 'handoff':
        schema['dependentRequired'] = dict(base['dependentRequired'])
    return schema


def review_template(task, handoff_id, obligation_id, request_id, *, project=None) -> dict:
    """The complete owner-filled review payload for one recorded handoff and covered obligation: identity, current guard,
    exact pins and request id filled; verdict null and summary/findings empty until the reviewer authors them."""
    from laplace.work import project_work
    handoff = next((row for row in task.get('phases') or () if row.get('id') == handoff_id and row.get('phase') == 'handoff'), None)
    obligation = next((row for row in task.get('review_obligations') or () if row.get('id') == obligation_id), None)
    if handoff is None or obligation is None or obligation_id not in (handoff.get('obligations') or ()):
        raise ValueError('A review template names a recorded handoff of this Work and an obligation it covers.')
    handed = handoff.get('pins') or {}
    pins = {path: digest for path, digest in sorted(handed.items()) if not obligation.get('inputs') or path in obligation['inputs']}
    payload = {'id': task['id'], 'phase': 'review', 'request_id': request_id, 'expected_work_revision': project_work._task_revision(task),
               'handoff_id': handoff_id, 'obligation_id': obligation_id, 'verdict': None, 'summary': '', 'findings': [],
               **({'pins': pins} if pins else {})}
    from laplace.work.project_work_continuity import handle as continuity
    preflight_read = continuity(project or task.get('project'), task['id'], {'part': 'preflight', 'payload': {}})
    return {'payload': payload, 'author_fields': ['verdict', 'summary', 'findings'], 'verdicts': list(VERDICTS),
            'schema': phase_schema('review'), 'limits': dict(LIMITS),
            'preflight': {**preflight_read, 'fill': 'request.payload = the whole work_review payload you intend to send'},
            'meaning': 'Template only: the verdict stays null until the reviewer authors it; a proposed verdict is not a recorded review '
                       'until work_review returns RECORDED.'}


def preflight(project, payload, root, *, tasks=None) -> dict:
    """Pure whole-request check of one proposed work_review payload before any paid admission: the closed phase schema
    with every actual limit, the current Work guard and the recorded handoff/obligation/pins it names. Records nothing."""
    from jsonschema import Draft202012Validator
    from laplace.work import project_work
    errors, template = [], None
    size = len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) if isinstance(payload, dict) else None
    phase = payload.get('phase') if isinstance(payload, dict) else None
    schema = phase_schema(phase) if phase in PHASE_FIELDS else contract()
    for error in sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda item: [str(part) for part in item.absolute_path]):
        errors.append({'path': '/'.join(str(part) for part in error.absolute_path) or '(root)', 'message': error.message[:300]})
    if isinstance(payload, dict) and isinstance(payload.get('id'), str):
        tasks = tasks if tasks is not None else project_work._tasks(project, root)
        task = tasks.get(payload['id'])
        if task is None:
            errors.append({'path': 'id', 'message': 'Not a Work of this project.'})
        else:
            if payload.get('expected_work_revision') != project_work._task_revision(task):
                errors.append({'path': 'expected_work_revision', 'message': 'Not the current Work specification guard; read the Work again.'})
            if phase == 'review':
                try:
                    template = review_template(task, payload.get('handoff_id'), payload.get('obligation_id'),
                                               payload.get('request_id') or '', project=project)
                except ValueError as error:
                    errors.append({'path': 'handoff_id', 'message': str(error)})
                else:
                    expected = template['payload'].get('pins') or {}
                    if payload.get('pins') and payload['pins'] != expected:
                        errors.append({'path': 'pins', 'message': 'Pins differ from the exact handed-off inputs of this obligation. ' + _pin_mismatch(expected, payload['pins'])})
                for index, item in enumerate(payload.get('findings') or []):
                    if isinstance(item, dict) and any(not str(item.get(key) or '').strip() for key in ('id', 'summary')):
                        errors.append({'path': 'findings/%d' % index, 'message': 'Finding id and summary are non-blank text.'})
    return {'schema_version': 'laplace.work-review-preflight/1', 'ok': not errors, 'recorded': False, 'errors': errors[:8],
            'errors_total': len(errors), 'payload_bytes': size, 'limits': dict(LIMITS),
            'template': template['payload'] if template else None,
            'meaning': 'Pure check: nothing was recorded or admitted. A valid proposed verdict is still not a recorded review.'}


ROLE_PHASES = {'review': {'review', 'followup'}}   # review mode records reviews and follow-ups, never handoffs/synthesis


def role_phases(mode) -> list:
    """The phases a role may record, in lifecycle order: the one rule _record enforces and allowed_actions publishes."""
    return [phase for phase in PHASES if mode not in ROLE_PHASES or phase in ROLE_PHASES[mode]]


def preparation(facet, phases, guard) -> dict:
    """What recording each allowed phase needs now, from the owner's facet (repair1 WI-R1): per phase its title and consequence,
    the basis the owner fills (the Work guard and the exact handoff/review/synthesis records the phase names), the inputs a
    person or agent authors (payload path, kind, label, options, default), why the phase is unavailable when its basis is
    missing, the pending recovery requests and, for a follow-up, its composition. The native allowed action and the human
    recorder both carry this object; neither re-derives a phase's fields or basis."""
    facet = facet or {}
    handoff, synthesis = facet.get('handoff'), facet.get('synthesis')
    obligations = [row for row in facet.get('obligations') or () if not row.get('closure_work_id')]
    covered = [row for row in obligations if not handoff or row['id'] in (handoff.get('obligations') or [])]
    nxt = facet.get('next') or {}
    out, schema = {}, contract()

    def required(path, top):
        # an input is required only when every step of its path is required in the one declared schema
        head, *rest = path.split('.')
        node = schema['properties'].get(head) if head in top else None
        for name in rest:
            if node is None or name not in (node.get('required') or ()):
                return False
            node = node['properties'][name]
        return node is not None
    for phase in phases:
        spec = PHASE_SPEC[phase]
        basis = {'expected_work_revision': guard}
        refused = None
        if phase == 'review':
            if handoff:
                basis['handoff_id'] = handoff['id']
            else:
                refused = 'No handoff is recorded yet; a review names the handoff it reviews.'
        elif phase == 'synthesis':
            consumes = ([handoff['id']] if handoff else []) + [row['review_id'] for row in facet.get('obligations') or () if row.get('review_id')]
            if consumes:
                basis['consumes'] = consumes
            else:
                refused = 'A synthesis consumes recorded handoff and review records; none is recorded yet.'
        elif phase == 'followup' and synthesis:
            basis['synthesis_id'] = synthesis['id']
        inputs = []
        for path, kind, label in spec['inputs'] + COMMON_INPUTS:
            item = {'path': path, 'name': path.rsplit('.', 1)[-1], 'input': kind, 'label': label,
                    'required': required(path, spec['required'])}
            if path == 'obligations':
                item['default'] = '\n'.join(row['id'] for row in obligations)
            elif path == 'object.kind':
                item['default'] = 'source'
            elif path == 'obligation_id':
                item.update(options=[[row['id'], row['label']] for row in covered], default=nxt.get('obligation_id') or '')
            elif path == 'verdict':
                item['options'] = [[key, label] for key, label in VERDICT_LABELS.items()]
            elif path == 'closure':
                item['options'] = [[key, label] for key, label in CLOSURE_LABELS.items()]
            inputs.append(item)
        entry = {'title': spec['title'], 'says': spec['says'], 'basis': basis, 'inputs': inputs}
        if refused:
            entry['refused'] = refused
        if phase == 'followup':
            entry['composition'] = followup_composition()
            pending = [{'child_id': row['child_id'], 'finding': row['finding'], 'closure': row['closure'], 'state': row.get('state'),
                        'read': row.get('read'), 'recover': row.get('recover')} for row in facet.get('pending_joins') or ()]
            if pending:
                entry['recovery'] = {'pending': pending, 'says': 'Complete each pending join with its original request and the current guard; nothing is re-run.'}
        out[phase] = entry
    initial = nxt.get('kind') if nxt.get('kind') in phases else (phases[0] if phases else None)
    return {'phases': out, 'initial': initial}


def record(project, payload, repo_root=None, *, door=None, mode='work'):
    """Admit and append one phase (see the module text). Returns the phase receipt and the Work's review facet as a
    caller-owned copy: the folded phase rows are the shared fold cache's own, never handed out by reference."""
    from laplace.work import project_work
    return project_work._deep(_record(project, payload, repo_root, door=door, mode=mode))


def _record(project, payload, repo_root, *, door, mode):
    from laplace.work import project_work
    from laplace.core import admission
    # the one admission of both doors (and of any direct caller): this owner's contract, its per-phase field sets
    admission.admit_owner_payload('work_review', payload, contract(), project=project)
    phase = payload['phase']
    if phase not in role_phases(mode):
        raise ValueError('Review mode records scoped reviews and follow-ups; handoff and synthesis belong to the producing or parent role.')
    request = payload.get('request_id')
    if not isinstance(request, str) or not _REQUEST.fullmatch(request):
        raise ValueError('work_review request_id is a stable client id of 8-96 characters [A-Za-z0-9._:-].')
    door = door or {'origin': 'human'}
    root = project_work._root(repo_root)
    with project_work.dispatch_lock(repo_root):
        tasks = project_work._tasks(project, repo_root)
        ident = payload.get('id')
        task = tasks.get(ident) if isinstance(ident, str) else None
        if task is None:
            raise ValueError('work_review names an existing Work id of this project.')
        phase_id = 'PHASE-' + _digest([project, ident, phase, request])[7:31]
        if phase == 'followup':
            replay = _followup_replay(project, payload, root, repo_root, task, phase_id, door)
            if replay is not None:   # recognised by its request before the guard: its own join changed the parent
                return replay
        if payload.get('expected_work_revision') != project_work._task_revision(task):
            raise project_work.WorkConflict('Read the exact Work before recording its review lifecycle.', project, ident,
                expected=payload.get('expected_work_revision'), observed=project_work._task_revision(task), field='expected_work_revision')
        if phase == 'followup':
            return _followup(project, payload, root, repo_root, tasks, task, door, phase_id)
        if not task.get('review_obligations'):
            raise ValueError('This Work has no review obligations; author them with its guarded task edit first.')
        prior = next((row for row in task.get('phases') or [] if row.get('id') == phase_id), None)
        row = _phase_row(project, payload, root, task, phase, phase_id, door, tasks, prior=prior)
        if prior is not None:
            if _content(prior) != _content(row) or identity(prior.get('actor')) != identity(row.get('actor')):
                raise ValueError('This request_id already recorded a different %s (or by another identity); use a new request_id.' % phase)
            tasks = project_work._tasks(project, repo_root)
            return {'status': 'REUSED', 'phase': project_work._deep(prior) if 'source_review_plan' in prior else prior, 'review': facet(tasks[ident], root, tasks=tasks),
                    **_reads(project, ident, phase_id, root=root, planned='source_review_plan' in prior), 'owned_changes_inexact': 'nothing was written: the request was already recorded'}
        appended = project_work._append(repo_root, row)
        tasks = project_work._tasks(project, repo_root)
        return {'status': 'RECORDED', 'phase': row, 'review': facet(tasks[ident], root, tasks=tasks),
                **_reads(project, ident, phase_id, root=root, planned='source_review_plan' in row), **_receipt([appended])}


RECORD_ACK_INLINE_BYTES = 16000


def bounded_ack(project, result):
    """The default native/HTTP recording and replay acknowledgement (Root goal items 2 and 4). The recorded row is
    returned unchanged when it fits; a large row (a whole-subject Source plan) is acknowledged by its bounded semantic
    header, NOT_EXPANDED, and the exact owner phase read (header plus phase_revision-pinned body pages). The stored row,
    its identity and request replay are untouched, and direct owner callers of record() keep the whole row."""
    import json
    phase = result.get('phase') if isinstance(result, dict) else None
    if not isinstance(phase, dict) or len(json.dumps(phase).encode('utf-8')) <= RECORD_ACK_INLINE_BYTES:
        return result
    from laplace.work.project_work_views import _phase_header
    out = {key: value for key, value in result.items() if key not in ('phase', 'detail_read')}
    out['phase'] = {'id': phase.get('id'), 'rows_state': 'NOT_EXPANDED', 'header': _phase_header(project, phase.get('work_id'), phase),
                    'read': result.get('phase_read'),
                    'meaning': 'The recorded row is stored whole and unchanged; read it through the exact phase read '
                               '(bounded header and phase_revision-pinned body pages).'}
    return out


def delivery_profile(payload):
    """writing.delivery.PROFILE_OWNERS: every recording/replay acknowledgement is bounded to the shared line."""
    from laplace.work import project_work_navigation as nav
    return {'bound': nav.CAP, 'owner': 'project_work_review.ack'} if isinstance(payload, dict) else None


def _reads(project, ident, phase_id, *, root, planned=False):
    """The exact owner reads of what was just recorded: the phase (whole row) and the Work detail."""
    from laplace.work.project_work_views import handle
    from laplace.work import project_work
    phase = phase_read(project_work._tasks(project,root)[ident],root,phase_id,project=project)
    return {'phase_read': phase, 'read_handle': handle(project, {'view': 'detail', 'id': ident}),
            **({'detail_read': phase} if planned else {})}


def feedback_handoff(root,project,work_id,edge,route_id,door):
    """Trusted delivery composition of a normal handoff plus its verified origin.

    These members are not public work_review payload authority. The route owner
    has already reserved the exact relation in the same Work phase ledger.
    """
    from laplace.work import project_work,feedback_route
    with project_work.dispatch_lock(root):
        tasks=project_work._tasks(project,root);task=tasks[work_id]
        feedback_route._origin(root,project,edge['origin'],current=True)
        payload={'id':work_id,'phase':'handoff','request_id':edge['handoff_request'],
            'expected_work_revision':project_work._task_revision(task),'obligations':[edge['obligation_id']],
            'pins':edge['pins'],'object':edge['object'],'summary':'Review the exact anchored author comment and declared material.'}
        phase=_phase_row(project,payload,root,task,'handoff',edge['handoff_id'],door,tasks)
        phase['feedback_origin']=edge['origin']
        phase['feedback_route']={'route_id':route_id,'edge_id':edge['edge_id'],'generation':edge['generation']}
        prior=next((r for r in task.get('phases') or () if r['id']==phase['id']),None)
        if prior:
            if _content(prior)!=_content(phase):raise ValueError('Feedback handoff identity has conflicting content.')
            return prior
        project_work._append(root,phase)
        return phase


def _receipt(appended):
    """The owner's own append receipts, combined only when they form one contiguous chain on the Work ledger (each
    before is the previous after); otherwise no exact receipt is claimed (a foreign append interleaved)."""
    receipts = [row.get('owned_changes') for row in appended if isinstance(row, dict)]
    if not receipts or any(not isinstance(item, dict) or len(item.get('files') or []) != 1 for item in receipts):
        return {'owned_changes_inexact': 'an owner append returned no exact receipt'}
    files = [item['files'][0] for item in receipts]
    if any(files[i]['path'] != files[0]['path'] or files[i]['before_sha256'] != files[i - 1]['after_sha256']
           for i in range(1, len(files))):
        return {'owned_changes_inexact': 'another writer appended between this operation\'s own appends'}
    from laplace.core.receipts import bundle
    combined = dict(files[0], after_sha256=files[-1]['after_sha256'], observed_after_sha256=files[-1]['observed_after_sha256'])
    return {'owned_changes': bundle(files=[combined], objects=[obj for item in receipts for obj in item.get('objects') or []],
                                    views=[view for item in receipts for view in item.get('views') or []])}


#: not request content: the owner's stamp, the journal's demotion of a row's own ts (journal.stamp) and the actor
#: (compared by identity)
_VOLATILE = ('ts', 'ts_claimed', 'actor')


def _content(row):
    return {key: value for key, value in row.items() if key not in _VOLATILE and not key.startswith('_')}


#: The Work's material intent a review is bound to (its own and every containing Work's); review_obligations,
#: depends_on, title and membership are NOT intent, so adding an obligation or a follow-up keeps other reviews.
MATERIAL_INTENT = ('goal', 'task_kind', 'section_ids', 'logical_target', 'anchor', 'reader_basis', 'obligation_id')


def intent_digest(task, tasks) -> str:
    """The material intent a review consumed: its own and its consumed containing Works'. A containing
    ``programme`` Work (project_work.PROGRAMME) is containment, not consumed intent (laplace.core.scoped):
    it contributes its identity only, so widening a programme goal does not restale reviews below it."""
    from laplace.work.project_work import PROGRAMME
    chain, seen, current = [], set(), task
    while isinstance(current, dict) and current.get('id') not in seen:
        seen.add(current.get('id'))
        contained = current is not task and current.get('task_kind') == PROGRAMME
        chain.append({'contains': current.get('id')} if contained else {key: current.get(key) for key in MATERIAL_INTENT})
        parent = current.get('parent_work_id')
        current = (tasks or {}).get(parent) if parent else None
    return _digest(chain)


def _phase_row(project, payload, root, task, phase, phase_id, door, tasks=None, *, prior=None):
    from laplace.work import project_work
    import datetime as dt
    tasks = tasks if tasks is not None else project_work._tasks(project, root)
    basis, _issue = project_work._work_basis(tasks, task['id'])
    row = {'record': PHASE_RECORD, 'kind': PHASE_KIND, 'id': phase_id, 'work_id': task['id'], 'project': project, 'phase': phase,
           'request_id': payload['request_id'], 'ts': dt.datetime.now(dt.timezone.utc).isoformat(),
           'basis': {'work_revision': basis['revision'], 'work_scope_revision': basis['scope_revision']},
           'actor': _actor(root, project, payload, door), 'summary': _text(payload.get('summary'), 'summary'),
           'evidence': _evidence(root, payload.get('evidence'))}
    known = {item['id']: item for item in task['review_obligations']}
    phases = {item['id']: item for item in task.get('phases') or []}
    if phase == 'handoff':
        named = payload.get('obligations') or list(known)
        if not isinstance(named, list) or any(item not in known for item in named):
            raise ValueError('A handoff names obligations of this Work.')
        obj = payload.get('object') or {}
        if not isinstance(obj, dict) or set(obj) - {'kind', 'profile', 'repository', 'base', 'checkpoint', 'aggregate'}:
            raise ValueError('A handoff object has kind, profile, repository, base, checkpoint and aggregate.')
        if 'source_basis' in payload:
            from laplace.work import development_source
            selection, pins = payload['source_basis'], payload.get('pins') or {}
            if prior is not None:
                held = prior.get('source_basis')
                if not held or selection != {key: held.get(key) for key in ('grant_id', 'candidate_id')} or pins != prior.get('pins'):
                    raise ValueError('This request_id already recorded a different handoff source basis or pins.')
                _require_source_current(root, project, task['id'], held, pins, door=door)
                row['source_basis'] = project_work._deep(held)
            else:
                row['source_basis'] = development_source.prepare_review_basis(root, project, task['id'], selection, pins, door=door)
            pins = project_work._deep(row['source_basis']['pins'])
        else:
            pins = _pins(root, payload.get('pins'), 'pins')
        row.update(obligations=named, object={key: _text(value, 'object ' + key, limit=MAX_OBJECT_TEXT) for key, value in obj.items()},
                   pins=pins)
        # a source-bound obligation is handed off as its owner's retained declaration segments (the canonical version)
        bound = {ident: known[ident]['source_contract'] for ident in named if known[ident].get('source_contract')}
        if bound:
            from laplace.work import source_contracts
            row['source_contracts'] = {ident: source_contracts.publish(root, value) for ident, value in bound.items()}
        if not row['pins'] and not row['object'].get('aggregate') and not bound:
            raise ValueError('A handoff pins its files, states an aggregate or publishes a bound source contract.')
        if row['pins'] or any(known[ident]['inputs'] for ident in bound):
            # a pinned handoff pins EVERY declared input of each obligation it covers (or it is aggregate-only)
            unpinned = sorted({path for ident in named for path in known[ident]['inputs']} - set(row['pins']))
            if unpinned:
                raise ValueError('A pinned handoff pins every declared input of the obligations it covers; missing: '
                                 + ', '.join(unpinned[:6]))
        if 'source_context' in payload:
            # The Source owner resolves this authored offer once. A replay keeps the
            # original geometry/identity, never a fresh plan over the current files.
            if prior is not None:
                if payload['source_context'] != prior.get('source_context') or payload.get('source_subject') != prior.get('source_subject') \
                        or not prior.get('source_review_plan'):
                    raise ValueError('This request_id already recorded a different or unavailable Source reading plan.')
                row['source_review_plan'] = project_work._deep(prior['source_review_plan'])
            else:
                row['source_review_plan'] = development_source.prepare_review_plan(
                    root, project, task['id'], row['source_basis'], row['pins'], payload['source_context'], payload.get('source_subject'))
            row['source_context'] = project_work._deep(payload['source_context'])
            if 'source_subject' in payload:
                row['source_subject'] = project_work._deep(payload['source_subject'])
    elif phase == 'review':
        handoff = phases.get(payload.get('handoff_id'))
        if handoff is None or handoff.get('phase') != 'handoff':
            raise ValueError('A review names a handoff of this Work.')
        if handoff.get('feedback_origin'):
            from laplace.work.feedback_route import _origin
            _origin(root,project,handoff['feedback_origin'],current=True)
            row['feedback_origin']=handoff['feedback_origin']
        obligation = known.get(payload.get('obligation_id'))
        if obligation is None or obligation['id'] not in handoff.get('obligations', []):
            raise ValueError('A review names an obligation that its handoff covers.')
        if payload.get('verdict') not in VERDICTS:
            raise ValueError('A review verdict is ACCEPT, HOLD or REJECT.')
        findings = payload.get('findings') or []
        if not isinstance(findings, list) or len(findings) > MAX_FINDINGS or any(
                not isinstance(item, dict) or set(item) != {'id', 'summary'} for item in findings):
            raise ValueError('Findings are at most %d {id, summary} entries.' % MAX_FINDINGS)
        # a review covers EXACTLY the obligation's declared handed-off inputs (all handed-off pins when none are
        # declared); unrelated, partial or added pins refuse; an aggregate-only handoff gives a coarse review
        handed = handoff.get('pins') or {}
        # the referenced handoff must STILL cover the CURRENT obligation (repair2 WR-R2-R1): an input added or replaced
        # after the handoff was never handed off, so a review of it cannot become current through the old pins
        uncovered = sorted(set(obligation['inputs']) - set(handed)) if handed else []
        if uncovered:
            raise ValueError('The referenced handoff does not pin the current declared input(s) of this obligation: '
                             + ', '.join(uncovered[:6]) + '. Record a fresh handoff that covers them, then review it.')
        expected = {path: digest for path, digest in handed.items() if not obligation['inputs'] or path in obligation['inputs']}
        source_basis, qualified_source = handoff.get('source_basis'), 'source_basis' in handoff
        # A typed Source basis never falls back to the canonical repository's similarly named files.
        supplied = (payload.get('pins') or {}) if qualified_source else _pins(root, payload.get('pins'), 'pins')
        if not handed and supplied:
            raise ValueError('An aggregate-only handoff has no pinned files; its review cannot add pins and stays coarse.')
        if supplied and supplied != expected:
            raise ValueError('A review covers exactly the handed-off declared inputs of its obligation; unrelated, partial or '
                             'different pins are refused. ' + _pin_mismatch(expected, supplied))
        if qualified_source:
            _require_source_current(root, project, task['id'], source_basis, expected, door=door)
            row['source_basis'] = project_work._deep(source_basis)
        else:
            for path, digest in expected.items():
                if _file_digest(root, path) != digest:
                    raise ValueError('CHANGED_INPUT: %s changed since the handoff; review the handed-off bytes or hand off again.' % path)
        pins = expected
        bound = obligation.get('source_contract')
        if bound:
            # the review consumes EXACTLY the handed version: owner, operation, consumer and segment bases come only from
            # the handoff row; a binding changed since then (or a handoff without it) cannot be reviewed against it
            held = (handoff.get('source_contracts') or {}).get(obligation['id'])
            if not held:
                raise ValueError('The referenced handoff does not publish this obligation\'s source contract; record a handoff that covers it.')
            if {key: held[key] for key in ('owner', 'operation', 'consumer')} != {key: bound[key] for key in ('owner', 'operation', 'consumer')} \
                    or ('segments' in bound and sorted(bound['segments']) != sorted(held['segments'])):
                raise ValueError('The obligation\'s source_contract binding changed since its handoff; hand off again, then review.')
            row['source_contract'] = {'owner': held['owner'], 'operation': held['operation'], 'consumer': held['consumer'],
                                      'version': held['version'], 'segments': {name: value['basis'] for name, value in held['segments'].items()}}
        row.update(handoff_id=handoff['id'], obligation_id=obligation['id'], scope=obligation['scope'], verdict=payload['verdict'],
                   findings=[{'id': _text(item['id'], 'finding id', required=True, limit=MAX_FINDING_ID),
                              'summary': _text(item['summary'], 'finding summary', required=True)} for item in findings],
                   pins=pins, obligation_digest=_digest(obligation), coarse=not pins and not bound,
                   intent_digest=intent_digest(task, tasks),
                   independence=independence(row['actor'], handoff.get('actor')))
    else:
        consumes = payload.get('consumes') or []
        if not consumes or not isinstance(consumes, list) or any(phases.get(item, {}).get('phase') not in {'handoff', 'review'} for item in consumes):
            raise ValueError('A synthesis consumes exact handoff and review ids of this Work.')
        row.update(consumes=list(dict.fromkeys(consumes)))
    return row



def _require_source_current(root, project, work_id, basis, pins, *, door):
    from laplace.work import development_source
    observed = development_source.validate_review_basis(root, project, work_id, basis, consumed_pins=pins, door=door)
    if observed['status'] != 'CURRENT':
        raise ValueError(('CHANGED_INPUT: ' if observed['status'] == 'CHANGED' else 'SOURCE_UNAVAILABLE: ') + observed['reason'])
    return observed


def _name(function) -> str:
    return function.__module__.rsplit('.', 1)[-1] + '.' + function.__qualname__


def followup_composition() -> dict:
    """THE FOLLOW-UP COMPOSITION (D2-E): this owner's one compound transition, stated beside the primitives that run it.

    project_work_navigation.action_context unfolds it for human and native readers instead of either re-describing the
    mechanics. ``steps`` name the primitives ``_followup`` and ``_followup_effects`` actually call, in order
    (tests/test_work_navigation.py traces them), so the description cannot drift from the execution. It executes nothing.
    """
    from laplace.work import project_work
    return {'operation': 'work_review', 'phase': 'followup',
            'admission': {'primitive': _name(_record), 'says': 'One declared schema for both doors; the stable request_id names '
                          'the phase, and a replay is recognised before the Work guard.'},
            'request': {'primitive': _name(_followup_request), 'fields': ['finding', 'closure', 'child', 'synthesis_id', 'summary', 'evidence'],
                        'child': list(CHILD_KEYS), 'optional_child': ['logical_target'],
                        'says': 'The canonical effect-bearing content a replay must repeat exactly; the child id derives from (parent, finding). '
                                'An omitted optional child field is absent from the request, never defaulted.'},
            'steps': [
                {'id': 'pending', 'primitive': _name(project_work._append), 'object': 'parent phases',
                 'effect': 'PENDING phase row: the request, its guard (basis_revision) and the original actor.'},
                {'id': 'child', 'primitive': _name(project_work._task), 'object': 'child Work', 'guard': _name(_refuse_drift),
                 'effect': 'Create the child once per (parent, finding) with followup_origin; an existing child must still match the request.'},
                {'id': 'join', 'primitive': _name(_join), 'object': 'parent specification',
                 'effect': 'Apply the closure once; an existing join is reused.'},
                {'id': 'complete', 'primitive': _name(project_work._append), 'object': 'parent phases',
                 'effect': 'COMPLETE or PENDING_JOIN phase row; recovered_by names another admitted actor that completed it.'}],
            'shared_effects': {'primitive': _name(_followup_effects), 'says': 'The same effect sequence serves the first request and every recovery.'},
            'closures': {'optional': 'membership only: the child is contained by the parent',
                         'required': 'a closure obligation on the parent: its completion waits for the child',
                         'prerequisite': 'the parent depends on the child'},
            'guards': ['expected_work_revision of the parent', 'child drift (' + _name(_refuse_drift) + ')',
                       'recovery only while the parent differs by this request\'s own join (' + _name(_own_change_only) + ')'],
            'recovery': 'Repeat the same request: review.pending_joins[].recover with the current expected_work_revision. Nothing is deleted or re-run.',
            'evidence': 'Phase rows (view:review phase_id) and the owner\'s combined append receipt when contiguous.',
            'authority': {'native': 'the admitted writing turn; review mode records reviews and follow-ups only', 'human': 'the author'}}


def source_contract() -> dict:
    """THE FOLLOW-UP SOURCE CONTRACT (laplace.work.source_contracts): this operation's segments, each computed from the
    declaration the code runs (contract(), PHASE_SPEC, followup_composition(), MATERIAL_INTENT), and the explicit
    consumers that rest on them. ``location`` qualifies where a consumer lives; it is not evidence of what it consumes."""
    from laplace.work import source_contracts
    schema, composition, spec = contract(), followup_composition(), PHASE_SPEC['followup']
    branch = next(row for row in schema['oneOf'] if row['properties']['phase'] == {'const': 'followup'})
    here, ui = 'src/laplace/work/project_work_review.py', 'src/laplace/web/static_shared/workspace-work-review.mjs'
    relate = lambda consumer, relation, segments, location, says: {'consumer': consumer, 'relation': relation, 'segments': segments,
                                                                    'location': location, 'says': says}
    return source_contracts.validate(source_contracts.detached({
        'schema': source_contracts.SCHEMA, 'owner': 'domain.work', 'operation': 'work_review.followup',
        'purpose': {'text': 'Create or resume one child Work for one finding and join it to the parent by its closure, keeping the '
                            'original actor, request and basis, any partial effect and the owner recovery.',
                    'assumptions': ['A child logical_target is task intent carried to the task owner, never write authority or a '
                                    'canonical owned reference.', 'Creating Work starts no session.'],
                    'authored_by': 'source-contract slice 2026-10-21 under Root synthesis sha256:7787fedd'},
        'segments': {'purpose': {'title': spec['title'], 'says': spec['says']},
                     'admission': {'branch': branch, 'child': schema['properties']['child'], 'closure': schema['properties']['closure']},
                     'request': composition['request'],
                     'inputs': [list(row) for row in spec['inputs']],
                     'steps': {key: composition[key] for key in ('steps', 'shared_effects', 'closures', 'guards', 'recovery')},
                     'authority': composition['authority'],
                     'review-intent': list(MATERIAL_INTENT)},
        'relations': [
            relate('kernel.declared-source', 'projects', ['purpose','admission','request','inputs','steps','authority','review-intent'], 'src/laplace/engine/source_kernel_input.py', 'Explicit retained Work publications feed typed kernel inputs; preparation grants no knowledge or execution authority.'),
            relate('work.project_work_review._followup_request', 'implements', ['admission', 'request'], here, 'admits the child and builds the canonical request'),
            relate('work.project_work_review._followup_effects', 'implements', ['request', 'steps'], here, 'runs child, join and completion'),
            relate('work_review.followup', 'contains', ['steps'], here, 'the compound operation contains its constituent steps'),
            relate('web.workspace-work-review.phaseRecorder', 'projects', ['inputs', 'admission'], ui, 'the human recorder renders the owner inputs'),
            relate('web.workspace-work-review.composition', 'explains', ['steps', 'purpose'], ui, 'the step-by-step disclosure'),
            relate('work.project_work_navigation.action_context', 'projects', ['inputs', 'steps'], 'src/laplace/work/project_work_navigation.py', 'carries the preparation'),
            relate('native.work_review', 'projects', ['admission'], 'src/laplace/native/declared.py', 'the native tool payload schema'),
            relate('native.help.work_review', 'explains', ['admission', 'purpose'], 'src/laplace/native/declared.py', 'rendered agent help'),
            relate('tests.work_review_lifecycle.followup', 'evaluates', ['admission', 'request', 'steps'], 'tests/test_work_review_lifecycle.py', 'follow-up effects and recovery'),
            relate('tests.work_navigation.composition', 'evaluates', ['steps'], 'tests/test_work_navigation.py', 'traces the primitives the owner runs'),
            relate('work.project_work_review.intent_digest', 'consumes', ['review-intent'], here, 'review currentness over the task intent')],
        'steps': [{**row, 'closures': composition['closures']} if row['id'] == 'join' else row for row in composition['steps']],
        'authority': composition['authority'], 'recovery': composition['recovery']}))


def _followup_request(payload, parent, project):
    """The canonical effect-bearing content of one follow-up request (every field a replay must repeat exactly)."""
    finding = _text(payload.get('finding'), 'finding', required=True, limit=160)
    closure = payload.get('closure')
    if closure not in CLOSURES:
        raise ValueError('A follow-up closure is optional, required or prerequisite.')
    child = payload.get('child')
    if not isinstance(child, dict) or set(child) - set(CHILD_KEYS):
        raise ValueError('A follow-up child has title, goal and optional id, kind, section_ids, logical_target.')
    target = child.get('logical_target')
    if 'logical_target' in child and (not isinstance(target, dict) or not target or set(target) - {'kind', 'node_id'}
                                      or not all(isinstance(value, str) and value.strip() for value in target.values())):
        raise ValueError('A follow-up child logical_target is {kind, node_id} text: task intent, not an owned reference or authority.')
    synthesis = payload.get('synthesis_id')
    if synthesis is not None and not any(row.get('id') == synthesis and row.get('phase') == 'synthesis' for row in parent.get('phases') or []):
        raise ValueError('synthesis_id names a synthesis of this Work.')
    child_id = child.get('id') or 'WORK-followup-' + _digest([project, parent['id'], finding])[7:27]
    return {'finding': finding, 'closure': closure, 'synthesis_id': synthesis,
            'child': {'id': child_id, 'title': _text(child.get('title'), 'child title', required=True, limit=200),
                      'goal': _text(child.get('goal'), 'child goal', required=True),
                      'kind': child.get('kind') or 'execution', 'section_ids': list(child.get('section_ids') or []),
                      **({'logical_target': dict(target)} if 'logical_target' in child else {})},
            'summary': _text(payload.get('summary'), 'summary'), 'evidence': payload.get('evidence') or []}


def _followup_rows(parent, phase_id):
    return [row for row in parent.get('phases') or () if row.get('id') == phase_id]


def _followup_replay(project, payload, root, repo_root, parent, phase_id, door):
    """A replay of an already-received follow-up request. The request must repeat every effect-bearing field
    exactly. A complete one is REUSED only for its original identity; an incomplete one (pending receipt or join)
    is recovered by the owner, possibly by another admitted actor (recorded separately), only while the parent
    differs from the original guard by this operation's own join. None when the request is new."""
    from laplace.work import project_work
    prior = _followup_rows(parent, phase_id)
    if not prior:
        return None
    first, last = prior[0], prior[-1]
    request = _followup_request(payload, parent, project)
    if request != first.get('request'):
        raise ValueError('This request_id already created a different follow-up; use a new request_id.')
    actor = _actor(root, project, payload, door)
    if last.get('state') == 'COMPLETE' and last.get('joined'):
        if identity(actor) != identity(first.get('actor')):
            raise ValueError('This follow-up was recorded by another identity; a new identity uses a new request_id.')
        tasks = project_work._tasks(project, repo_root)
        return {'status': 'REUSED', 'phase': last, 'child_id': last['child_id'], 'child_created': False, 'joined': True,
                'review': facet(tasks[parent['id']], root, tasks=tasks), **_reads(project, parent['id'], phase_id,root=root),
                'owned_changes_inexact': 'nothing was written: the request was already recorded'}
    tasks = project_work._tasks(project, repo_root)
    current = tasks[parent['id']]
    if not _own_change_only(current, first, request['child']['id']):
        raise project_work.WorkConflict('The Work changed after this follow-up began (not only by its own join); '
                                        'read the Work and record a new follow-up.', project, parent['id'],
                                        expected=first.get('basis_revision'), observed=project_work._task_revision(current),
                                        field='expected_work_revision')
    return _followup_effects(project, root, repo_root, tasks, current, first, actor, recovering=True)


def _followup(project, payload, root, repo_root, tasks, parent, door, phase_id):
    """Write the PENDING phase (canonical request, guard, original actor) first, then the child, the join and the
    completion row; any partial landing is recovered by the same request (module text)."""
    from laplace.work import project_work
    import datetime as dt
    request = _followup_request(payload, parent, project)
    child_id = request['child']['id']
    origin = {'parent_work_id': parent['id'], 'finding': request['finding'], 'closure': request['closure']}
    existing = tasks.get(child_id)
    if existing is not None and existing.get('followup_origin') != origin:
        raise ValueError('Work %s already exists with another origin; a follow-up never adopts unrelated Work.' % child_id)
    if existing is not None:
        # a conflict KNOWN before publication refuses with nothing written (repair3 WR-R3-R2): no PENDING phase, no
        # child, no join, and the request id stays unconsumed; the effect-time check below still guards races/recovery
        _refuse_drift(project, existing, request['child'], parent['id'])
    actor = _actor(root, project, payload, door)
    pending = {'record': PHASE_RECORD, 'kind': PHASE_KIND, 'id': phase_id, 'work_id': parent['id'], 'project': project,
               'phase': 'followup', 'state': 'PENDING', 'request_id': payload['request_id'], 'request': request,
               'synthesis_id': request['synthesis_id'], 'finding': request['finding'], 'closure': request['closure'],
               'child_id': child_id, 'joined': False, 'actor': actor, 'summary': request['summary'],
               'evidence': _evidence(root, request['evidence']), 'basis_revision': project_work._task_revision(parent),
               'ts': dt.datetime.now(dt.timezone.utc).isoformat()}
    appended = project_work._append(repo_root, pending)
    return _followup_effects(project, root, repo_root, project_work._tasks(project, repo_root), parent, pending, actor,
                             recovering=False, appended=[appended])


def _followup_effects(project, root, repo_root, tasks, parent, pending, actor, *, recovering, appended=None):
    from laplace.work import project_work
    import datetime as dt
    appended = list(appended or [])
    request, child_id = pending['request'], pending['child_id']
    origin = {'parent_work_id': parent['id'], 'finding': request['finding'], 'closure': request['closure']}
    created = False
    if child_id not in tasks:
        appended.append(project_work._task(project, {'id': child_id, 'title': request['child']['title'], 'goal': request['child']['goal'],
                                                     'kind': request['child']['kind'], 'section_ids': request['child']['section_ids'],
                                                     'parent_work_id': parent['id'], 'origin': pending['actor']['actor'],
                                                     **({'logical_target': request['child']['logical_target']} if 'logical_target' in request['child'] else {})},
                                           repo_root, followup_origin=origin))
        created = True
    elif tasks[child_id].get('followup_origin') != origin:
        raise ValueError('Work %s already exists with another origin; a follow-up never adopts unrelated Work.' % child_id)
    else:
        # the landed child must still BE the requested correction (repair2 WR-R3-R1): a child edited after it landed,
        # or one that changed between admission and effect, is never joined as the one requested
        _refuse_drift(project, tasks[child_id], request['child'], parent['id'])
    joined, problem, join_receipt = _join(project, repo_root, parent, child_id, request['closure'], request['finding'])
    if join_receipt is not None:
        appended.append(join_receipt)
    completion = {**{key: pending[key] for key in ('record', 'kind', 'id', 'work_id', 'project', 'phase', 'request_id', 'request',
                                                   'synthesis_id', 'finding', 'closure', 'child_id', 'actor', 'summary', 'evidence',
                                                   'basis_revision')},
                  'state': 'COMPLETE' if joined else 'PENDING_JOIN', 'joined': joined, 'child_created': created,
                  'ts': dt.datetime.now(dt.timezone.utc).isoformat()}
    if recovering:
        completion['recovered_by'] = actor
    if problem:
        completion['join_problem'] = problem
    try:
        appended.append(project_work._append(repo_root, completion))
    except OSError as error:   # the child and join are real; the same request completes the receipt
        return {'status': 'PENDING_RECEIPT', 'child_id': child_id, 'child_created': created, 'joined': joined, 'error': str(error),
                **_reads(project, parent['id'], pending['id'],root=root), **_receipt(appended)}
    fresh = project_work._tasks(project, repo_root)
    return {'status': ('RECOVERED' if recovering else 'JOINED') if joined else 'PENDING_JOIN', 'phase': completion,
            'child_id': child_id, 'child_created': created, 'joined': joined,
            'review': facet(fresh[parent['id']], root, tasks=fresh), **_reads(project, parent['id'], pending['id'],root=root), **_receipt(appended)}


def _child_spec(task, consumed=()):
    return {'title': task.get('title'), 'goal': task.get('goal'), 'kind': task.get('task_kind') or 'execution',
            'section_ids': list(task.get('section_ids') or []), 'parent_work_id': task.get('parent_work_id'),
            **{key: task.get(key) for key in consumed}}


def _child_drift(task, requested, parent_id) -> list:
    """The material fields in which a landed follow-up child differs from its requested specification. An optional field
    (logical_target) is compared only when the request consumed it, so a request that omitted it keeps its old meaning."""
    consumed = tuple(key for key in ('logical_target',) if key in requested)
    landed, wanted = _child_spec(task, consumed), {**{key: requested.get(key) for key in ('title', 'goal', 'kind', *consumed)},
                                                   'section_ids': list(requested.get('section_ids') or []), 'parent_work_id': parent_id}
    return [key for key in ('title', 'goal', 'kind', 'section_ids', 'parent_work_id', *consumed) if landed[key] != wanted[key]]


def _refuse_drift(project, task, requested, parent_id):
    from laplace.work import project_work
    drift = _child_drift(task, requested, parent_id)
    if drift:
        raise project_work.WorkConflict(
            'Follow-up Work %s no longer matches the requested correction (%s changed); it is kept as it is and '
            'not joined. Read that Work, then reconcile it or record a new follow-up.' % (task['id'], ', '.join(drift)),
            project, task['id'], expected=_digest(requested), observed=_digest(_child_spec(task, tuple(key for key in ('logical_target',) if key in requested))), field='child')


def _closure_row(child_id, finding):
    return {'id': 'closure-' + child_id.lower()[-24:].strip('-'), 'scope': 'closure',
            'label': 'Required follow-up: ' + finding[:160], 'closure_work_id': child_id, 'inputs': []}


def _own_change_only(current, pending, child_id) -> bool:
    """Is the parent exactly its original guarded specification, or that plus THIS operation's own join?"""
    from laplace.work import project_work
    basis = pending.get('basis_revision')
    if project_work._task_revision(current) == basis:
        return True
    closure = pending.get('closure')
    if closure == 'prerequisite':
        without = {**current, 'depends_on': [item for item in current.get('depends_on') or [] if item != child_id]}
        return project_work._task_revision(without) == basis
    if closure == 'required':
        kept = [item for item in current.get('review_obligations') or [] if item.get('closure_work_id') != child_id]
        variants = [{**current, 'review_obligations': kept}] + ([{k: v for k, v in current.items() if k != 'review_obligations'}] if not kept else [])
        return any(project_work._task_revision(variant) == basis for variant in variants)
    return False


def _join(project, repo_root, parent, child_id, closure, finding):
    """Apply the closure to the parent once; an existing join is reused. Returns (joined, problem, receipt)."""
    from laplace.work import project_work
    if closure == 'optional':
        return True, None, None
    tasks = project_work._tasks(project, repo_root)
    current = tasks[parent['id']]
    if closure == 'prerequisite':
        if child_id in (current.get('depends_on') or []):
            return True, None, None
        change = {'depends_on': [*(current.get('depends_on') or []), child_id]}
    else:
        obligations_now = list(current.get('review_obligations') or [])
        if any(item.get('closure_work_id') == child_id for item in obligations_now):
            return True, None, None
        change = {'review_obligations': obligations_now + [_closure_row(child_id, finding)]}
    try:
        receipt = project_work._task(project, {'id': parent['id'], 'expected_work_revision': project_work._task_revision(current), **change}, repo_root)
    except (ValueError, OSError) as error:
        return False, str(error), None
    return True, None, receipt


# ---------------------------------------------------------------------------------------------- projection

def _latest(phases, kind):
    rows = [row for row in phases if row.get('phase') == kind]
    return rows[-1] if rows else None


def facet(task, root, *, tasks=None, digests=None, project=None, read_context=None) -> dict | None:
    """Reuse only identical consumed review facts within one pure read request."""
    if read_context is None:return _facet(task,root,tasks=tasks,digests=digests,project=project)
    if not isinstance(read_context,dict):raise TypeError('A pure read context is an internal dict.')
    from laplace.work.project_work import _root,_deep
    root=_root(root);project=project or task.get('project')
    if digests is None:digests=read_context.setdefault(('work-evidence',str(root)),{})
    closures=tuple((item.get('closure_work_id'),((tasks or {}).get(item.get('closure_work_id')) or {}).get('status'))
        for item in task.get('review_obligations') or [] if item.get('closure_work_id'))
    # Phase objects come from the one captured task fold. Their identity avoids
    # hydrating/re-serialising retained phase bodies merely to memoise a read.
    key=('review-facet',str(root),project,task['id'],intent_digest(task,tasks),
         tuple(id(row) for row in task.get('phases') or ()),closures,id(digests))
    if key not in read_context:
        read_context[key]=_facet(task,root,tasks=tasks,digests=digests,project=project,read_context=read_context)
        metrics=read_context.setdefault(('read-metrics',str(root)),{})
        metrics['review_facet_computations']=metrics.get('review_facet_computations',0)+1
    return _deep(read_context[key])


def observe_fact_input(root,read_context,key,value):
    """Private opt-in read set, never authority or public body data."""
    if read_context is not None and read_context.get(('review-evidence-observe',str(Path(root).resolve()))):
        read_context.setdefault(('review-evidence-inputs',str(Path(root).resolve())),{})[_digest(key)]=value


def facts(task,root,*,tasks=None,digests=None,project=None,read_context=None):
    """The single local review decision path, without rich handles or support copying."""
    declared=task.get('review_obligations')
    if not declared:return None
    project=project or task.get('project');phases=task.get('phases') or ()
    handoffs=[row for row in phases if row.get('phase')=='handoff']
    reviews=[row for row in phases if row.get('phase')=='review']
    followups={row['id']:row for row in phases if row.get('phase')=='followup'}
    intent=intent_digest(task,tasks);rows=[]
    for item in declared:
        latest=next((row for row in reversed(reviews) if row.get('obligation_id')==item['id']),None)
        entry={key:item[key] for key in ('id','scope','label','required','independent') if key in item}
        entry['inputs_total']=len(item.get('inputs') or [])
        if item.get('closure_work_id'):
            child=(tasks or {}).get(item['closure_work_id']);done=bool(child) and child.get('status') in {'done','verified'}
            entry.update(closure_work_id=item['closure_work_id'],status='SATISFIED' if done else 'PENDING_CLOSURE',currentness='CURRENT' if done else 'UNKNOWN',satisfied=done)
            observe_fact_input(root,read_context,['closure',item['closure_work_id']],{'present':child is not None,'status':(child or {}).get('status')})
            latest=None
        elif latest is None:
            entry.update(status='AWAITING_REVIEW' if handoffs else 'AWAITING_HANDOFF',currentness='UNKNOWN',satisfied=False)
        else:
            judged=decision(latest,item,root,intent=intent,digests=digests,read_context=read_context)
            if read_context is not None:
                metrics=read_context.setdefault(('read-metrics',str(Path(root).resolve())),{})
                metrics['review_decisions']=metrics.get('review_decisions',0)+1
            entry.update(status={'ACCEPT':'ACCEPTED','HOLD':'HOLD','REJECT':'REJECTED'}[latest['verdict']],currentness=judged['currentness'],
                currentness_reason=judged['reason'],independence=latest.get('independence'),review_id=latest['id'],reviewer=latest['actor'].get('actor'),
                reviewer_verified=latest['actor'].get('origin')!='external' or bool(latest['actor'].get('verified')),findings=len(latest.get('findings') or []),satisfied=judged['satisfied'])
            if judged['changed_segments']:entry['changed_segments']=judged['changed_segments']
            if judged['coverage'] is not None:entry['coverage']=judged['coverage']
        rows.append({'definition':item,'latest':latest,'standing':entry})
    return {'project':project,'intent':intent,'obligations':rows,'handoffs':handoffs,'reviews':reviews,'followups':followups}


def phase_read(task,root,phase_id,*,project=None,read_context=None):
    """Guard exactly the currently captured same-ID rowset, not historical reconstruction."""
    from laplace.work.project_work_views import handle
    rows=[row for row in task.get('phases') or () if row.get('id')==phase_id]
    if not rows:raise ValueError('Phase rowset unavailable in captured Work.')
    key=('work-phase-revision',id(task.get('phases')),phase_id)
    cache={} if read_context is None else read_context
    if key not in cache:
        cache[key]=_digest(rows)
        if read_context is not None:
            metrics=read_context.setdefault(('read-metrics',str(Path(root).resolve())),{})
            metrics['phase_revision_computations']=metrics.get('phase_revision_computations',0)+1
    return handle(project or task['project'],{'view':'review','id':task['id'],'phase_id':phase_id,'phase_revision':cache[key]})


def _facet(task, root, *, tasks=None, digests=None, project=None, read_context=None) -> dict | None:
    """The owner's review projection of one review-managed Work; None for legacy Work. Phase rows are read in place
    (never copied); every row names its exact owner read (view:review) for the lazy evidence door."""
    from laplace.work.project_work import _deep as work_deep   # the few nested fields served from the cached rows
    from laplace.work.project_work_views import handle
    observed = facts(task, root, tasks=tasks, digests=digests, project=project, read_context=read_context)
    if observed is None:return None
    project=observed['project'];phases=task.get('phases') or ()
    handoffs=observed['handoffs'];reviews=observed['reviews'];followups=observed['followups']
    read = lambda **extra: phase_read(task,root,extra['phase_id'],project=project,read_context=read_context) if extra.get('phase_id') else handle(project, {'view':'review','id':task['id'],**extra})
    rows=[]
    for fact in observed['obligations']:
        entry=work_deep(fact['standing']);item=fact['definition']
        if item.get('source_contract'):entry['source_contract']=work_deep(item['source_contract'])
        entry['read']=read(obligation_id=item['id'])
        if fact['latest'] is not None:entry['review_read']=read(phase_id=fact['latest']['id'])
        rows.append(entry)
    remaining = [row['id'] for row in rows if row.get('required') and not row['satisfied']]
    handoff = handoffs[-1] if handoffs else None
    synthesis = _latest(phases, 'synthesis')
    pending = [{'child_id': row['child_id'], 'closure': row['closure'], 'finding': row['finding'], 'request_id': row['request_id'],
                'state': row.get('state'), 'read': read(phase_id=row['id']),
                **({'recover': recover} if (recover := _recover_request(task, row)) else {})}
               for row in followups.values() if not (row.get('joined') and row.get('state', 'COMPLETE') == 'COMPLETE')]
    return {'managed': True, 'remaining': remaining, 'obligations': rows,
            'handoff': {key: work_deep(handoff.get(key)) for key in ('id', 'ts', 'object', 'obligations')} | {'producer': handoff['actor'].get('actor'),
                        'producer_origin': handoff['actor'].get('origin'), 'pins_total': len(handoff.get('pins') or {}),
                        'evidence_total': len(handoff.get('evidence') or []), 'read': read(phase_id=handoff['id']),
                        **({'source_review_plan': source_plan_summary(handoff['source_review_plan'])} if 'source_review_plan' in handoff else {})} if handoff else None,
            'synthesis': {key: work_deep(synthesis.get(key)) for key in ('id', 'ts', 'consumes', 'summary')} | {'read': read(phase_id=synthesis['id'])}
                         if synthesis else None,
            'followups': [{'child_id': row['child_id'], 'closure': row['closure'], 'finding': row['finding'], 'joined': bool(row.get('joined'))}
                          for row in list(followups.values())[:12]],
            'phases_total': len(phases), 'phases_read': read(),
            'pending_joins': pending, 'reviews_recorded': len(reviews), 'next': _next(rows, handoff, synthesis, pending)}


def source_plan_summary(plan):
    """Offered structural coverage only; no observed reading or review standing."""
    subject = plan.get('review_subject')
    if subject is not None:
        from laplace.work import development_source
        return {'plan_id': plan['plan_id'], 'state': plan['state'], 'review_subject': development_source.subject_summary(subject),
                'changed_file_count': len(subject['changed_files']),
                'latest_delta_file_count': sum(bool(row.get('changed')) for row in plan['candidate_files']),
                'input_count': len(plan['inputs']), 'excerpt_count': sum(len(row['initial_reads']) for row in plan['inputs']),
                'offered_not_observed': True, 'semantic_adequacy': 'UNASSESSED'}
    return {'plan_id': plan['plan_id'], 'state': plan['state'],
            'changed_file_count': sum(bool(row.get('changed')) for row in plan['candidate_files']),
            'input_count': len(plan['inputs']),
            'excerpt_count': sum(len(row['initial_reads']) for row in plan['inputs']),
            'offered_not_observed': True, 'semantic_adequacy': 'UNASSESSED'}


def _recover_request(task, row):
    """The exact original follow-up request (its recorded canonical content and request_id) that completes a pending
    receipt or join; the caller adds the current expected_work_revision from allowed_actions."""
    request = row.get('request')
    if not isinstance(request, dict):
        return None
    from laplace.work.project_work import _deep
    return _deep({'id': task['id'], 'phase': 'followup', 'request_id': row['request_id'], 'finding': request['finding'],
            'closure': request['closure'], 'child': request['child'],
            **({'synthesis_id': request['synthesis_id']} if request.get('synthesis_id') else {}),
            **({'summary': request['summary']} if request.get('summary') else {}),
            **({'evidence': request['evidence']} if request.get('evidence') else {})})


def decision(review, obligation, root, *, intent=None, digests=None, read_context=None) -> dict:
    """THE review decision of one recorded review against its obligation now (the facet's satisfied/next/completion and
    the source-contract reader both use it): verdict, recorded independence, currentness (obligation, material intent,
    every declared raw input pinned and unchanged, and for a source-contract-bound review its handed segment bases
    against the registered declaration) and whether it satisfies the obligation. Local satisfaction (``satisfied``, under
    the Work's authored independent flag) is reported apart from the actual recorded independence and, for a bound review,
    its actual segment coverage; neither is implied by the other."""
    current = _currentness(review, obligation, root, digests, intent, read_context=read_context)
    independent_ok = not obligation.get('independent', True) or review.get('independence') == 'INDEPENDENT'
    # coverage of a bound review: only the handed segment BODIES it consumed; the publication's other bases identify the
    # version and prove nothing reviewed. The consumer's whole requirement comes from the current declaration.
    bound, coverage = review.get('source_contract'), None
    if bound:
        from laplace.work import source_contracts
        try:
            required = source_contracts.consumed_segments(source_contracts.declaration(bound['owner'], bound['operation']), bound['consumer'])
            observe_fact_input(root,read_context,['source-requirement',bound['owner'],bound['operation'],bound['consumer']],{'available':True,'required':required})
        except ValueError:
            required = []
            observe_fact_input(root,read_context,['source-requirement',bound['owner'],bound['operation'],bound['consumer']],{'available':False})
        covered = sorted(bound.get('segments') or ())
        coverage = {'required': required, 'covered': covered, 'missing': sorted(set(required) - set(covered))}
    return {'verdict': review.get('verdict'), 'independence': review.get('independence'), 'currentness': current['status'],
            'reason': current['reason'], 'changed_segments': current.get('changed_segments', []),
            'independent_ok': independent_ok,                                      # the Work's authored (local) requirement
            'independent_actual': review.get('independence') == 'INDEPENDENT',     # the recorded fact, whatever the Work allows
            'coverage': coverage,
            'satisfied': review.get('verdict') == 'ACCEPT' and current['status'] == 'CURRENT' and independent_ok}


def _currentness(review, obligation, root, digests, intent=None, *, read_context=None) -> dict:
    if review.get('feedback_origin'):
        from laplace.work.feedback_route import _origin
        try:origin=_origin(root,review['project'],review['feedback_origin'],read_context=read_context)
        except ValueError as error:
            observe_fact_input(root,read_context,['feedback',review.get('feedback_origin')],{'available':False,'reason':str(error)})
            return {'status':'UNKNOWN','reason':'Reviewed comment origin unavailable: '+str(error)}
        observe_fact_input(root,read_context,['feedback',review['feedback_origin']],origin)
        if origin['currentness']['state']!='CURRENT':
            return {'status':'STALE','reason':'The reviewed comment/source changed; verdict stays as history.'}
    if review.get('obligation_digest') != _digest(obligation):
        return {'status': 'STALE', 'reason': 'The obligation was revised after this review; the verdict stays as history.'}
    if not review.get('intent_digest'):
        return {'status': 'UNKNOWN', 'reason': 'This review recorded no material Work intent; it cannot be current.'}
    if intent is not None and review['intent_digest'] != intent:
        return {'status': 'STALE', 'reason': 'The Work\'s material intent (goal or scope) changed after this review.'}
    pins, bound = review.get('pins') or {}, review.get('source_contract')
    if not pins and not bound:
        return {'status': 'UNKNOWN', 'reason': 'This review states no per-file pins (coarse); it cannot be current.'}
    unpinned = sorted(set(obligation.get('inputs') or []) - set(pins))
    if unpinned:
        return {'status': 'UNKNOWN', 'reason': 'This review does not pin every current declared input (' + ', '.join(unpinned[:4])
                + '); it cannot be current.'}
    if 'source_basis' in review:
        from laplace.work import development_source
        try:
            observed = development_source.validate_review_basis(root, review['project'], review['work_id'], review['source_basis'], consumed_pins=pins, read_context=read_context)
            observe_fact_input(root,read_context,['qualified-source',review['id']],observed)
        except (ValueError, OSError) as error:
            return {'status': 'UNKNOWN', 'reason': 'Reviewed Source basis unavailable: ' + str(error)}
        if observed['status'] != 'CURRENT':
            return {'status': 'STALE' if observed['status'] == 'CHANGED' else 'UNKNOWN', 'reason': observed['reason']}
    else:
        observed_pins={path:_file_digest(root,path,digests) for path in pins}
        observe_fact_input(root,read_context,['review-pins',review['id']],observed_pins)
        changed = [path for path, digest in pins.items() if observed_pins[path] != digest]
        if changed:
            return {'status': 'STALE', 'reason': 'Reviewed input changed: ' + ', '.join(changed[:4])}
    if bound:
        from laplace.work import source_contracts
        try:
            now = source_contracts.bases(source_contracts.declaration(bound['owner'], bound['operation']))
        except ValueError:
            observe_fact_input(root,read_context,['source-bases',bound['owner'],bound['operation'],review['id']],{'available':False})
            return {'status': 'UNKNOWN', 'reason': 'The reviewed source contract %s:%s is no longer declared.' % (bound['owner'], bound['operation'])}
        observe_fact_input(root,read_context,['source-bases',bound['owner'],bound['operation'],review['id']],{'available':True,'consumed':{name:now.get(name) for name in bound['segments']}})
        moved = sorted(name for name, basis in bound['segments'].items() if now.get(name) != basis)
        if moved:
            return {'status': 'STALE', 'reason': 'Reviewed source-contract segment changed: ' + ', '.join(moved), 'changed_segments': moved}
        return {'status': 'CURRENT', 'reason': 'The reviewed source-contract segments' + (' and every reviewed pin' if pins else '') + ' are current.'}
    return {'status': 'CURRENT', 'reason': 'Every reviewed pin matches current bytes.'}


def _next(rows, handoff, synthesis, pending) -> dict:
    if pending:
        return {'kind': 'recover-join', 'says': 'Recover the pending follow-up join with the same request.'}
    if handoff is None:
        return {'kind': 'handoff', 'says': 'Submit the implementation for scoped review (metadata only; nothing is launched).'}
    waiting = [row for row in rows if row.get('required') and not row.get('closure_work_id') and not row['satisfied']]
    if waiting:
        row = waiting[0]
        step = {'kind': 'review', 'obligation_id': row['id'], 'says': 'Record the %s review of "%s".' % (row['scope'], row['label'])}
        if row.get('review_id') and row.get('status') in ('HOLD', 'REJECTED'):
            # A recorded HOLD/REJECT is the actual disposition: name it, its findings and its exact read, never a fresh nudge.
            step['disposition'] = {key: row.get(key) for key in ('review_id', 'status', 'currentness', 'currentness_reason', 'findings', 'independence')}
            if row.get('review_read'):
                step['disposition']['read'] = row['review_read']
            if row.get('currentness') == 'CURRENT':
                step['says'] = ('Review %s recorded %s with %s finding(s) on the current bytes of "%s": address them through a revised '
                                'handoff or a follow-up; this verdict stays binding until a new review of changed bytes.'
                                % (row['review_id'], row['status'], row.get('findings', 0), row['label']))
            else:
                step['says'] = ('Review %s recorded %s on bytes that are now %s (%s). Record the %s review of "%s".'
                                % (row['review_id'], row['status'], row.get('currentness'), row.get('currentness_reason') or 'unknown', row['scope'], row['label']))
        return step
    if synthesis is None:
        return {'kind': 'synthesis', 'says': 'Record the synthesis of the handoff and its reviews.'}
    closures = [row for row in rows if row.get('closure_work_id') and not row['satisfied']]
    if closures:
        return {'kind': 'closure', 'work_id': closures[0]['closure_work_id'], 'says': 'Complete the required follow-up Work.'}
    return {'kind': 'complete', 'says': 'Every required obligation is satisfied: record completion with its guards.'}


def completion_problem(task, root, tasks) -> str | None:
    """Why a review-managed Work cannot be recorded done (None when every required obligation is satisfied)."""
    value = facts(task, root, tasks=tasks)
    remaining=[] if value is None else [r['standing']['id'] for r in value['obligations'] if r['standing'].get('required') and not r['standing']['satisfied']]
    if not remaining:
        return None
    return ('Review-managed Work completes only when every required obligation is satisfied; remaining: '
            + ', '.join(remaining) + '. An implementation handoff or a self-assessment does not satisfy one.')


def compact(task) -> dict | None:
    """LIST-altitude counts (no bodies)."""
    declared = task.get('review_obligations')
    if not declared:
        return None
    phases = task.get('phases') or ()
    latest = {row['id']: row for row in phases if row.get('phase') == 'followup'}
    return {'managed': True, 'obligations': len(declared), 'reviews': sum(1 for row in phases if row.get('phase') == 'review'),
            'pending_joins': sum(1 for row in latest.values() if not (row.get('joined') and row.get('state', 'COMPLETE') == 'COMPLETE'))}
