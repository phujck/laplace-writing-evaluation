"""EIGEN CONTINUITY (Root e716/a6d0, B owner slice, 2026-10-30): one selected Work's continuity projection, a prepared
Source completion intent armed by its genuine producer, late peer proof as an arrival fact, and one owner-issued
Continue that produces the existing handoff and Work delivery exactly once.

Ownership
  A section of the Work owner. Durable truth stays in the existing Work ledger (project_work._append under
  project_work.dispatch_lock): three project-work-phase kinds attached to the Work's existing ``development`` tuple
  (project_work._ATTACHED_KINDS), beside the Source grant/candidate/effect rows they qualify.
    source-completion-intent    ARMED and immutable: the producer's exact cumulative pins and qualified Source basis,
                                the original actor/session/turn/commission and parent coordinates, the approved
                                evaluator binding and return policy, the typed peer-proof slots and the planned
                                admission chain. Written only by the genuine ACTIVE Source producer (an author turn of
                                the grant's original parent session, attached to its commission, before that turn
                                ends). Nobody arms on its behalf afterwards.
    source-completion-proof     one exact project Artifact reference per declared slot, verified at arrival. An
                                arrival fact: it satisfies a routing prerequisite, never a review, ACCEPT or PASS.
    source-completion-continue  the one Continue: handoff phase id, Work delivery event id, the actual dispatcher and
                                the readiness basis it consumed.
  No new store, controller, runner or DSL. Readiness is derived on every read from its owners (Source currentness,
  Work scope and standing, recipient binding, producer Stop, the Writing account); the intent is not a cached verdict.
  Readiness also closes when the grant committed production after arming (the still-active producer may arm a
  superseding intent, history kept), when the obligation already has a review of the same bytes or another delivery
  of it is active, and when the producer's Stop is durable: the Writing selected-turn Stop owner's exact turn/generation
  request (read by source_execution.producer_origin) or a later write path's WITHDRAWN row.

Source-scope completion (Root scope38, 2026-11-04)
  For an obligation declared ``scope: source`` the arm requires BOTH the exact ``source_context`` reading offer and an
  explicit ``source_subject`` with its typed stage (and any selected prior grants, read-only carry and accepted base)
  before anything is appended; prior grants and carry are never inferred from the latest delta. Missing, incomplete or
  stale input is a bounded refusal naming the exact development_source review-preflight read, so the same live producer
  can arm again. An already recorded, uncontinued Source-scope intent without them is HELD (SOURCE_REVIEW_PLAN_ABSENT);
  nothing grafts a later plan onto an immutable intent and the CONTINUED replay branch is unchanged. Guide/non-source
  obligations keep the legacy plan-less meaning; parent_return null stays a review-only route. The exact prepared
  reviewer request (work_delivery._request_text, its existing ceiling and bounded re-rendering) is composed purely at
  arm, in readiness and again before the one handoff append (request_fit).

Continue
  An eligible actual operator (the human/admin door or an author-role native turn of this project; a review turn
  never) calls work_delivery {action: continue, intent_id, expected_basis}. Under the Work lock the owner recomputes
  readiness and compares the basis, appends the handoff phase (actor = the ORIGINAL producer; the dispatcher rides
  beside it in continuation_origin), the existing Work delivery intent through work_delivery.submit_prepared (actor,
  origin and parent coordinates = the original producer; the commission resolved again from the producer turn by
  source_execution.prepared_inheritance) and one continue row. Transport is the existing work_delivery.recover path
  (request-id reconciliation first). Every identity is deterministic, so a repeated call or a lost acknowledgement
  returns the same handoff and event and admits nothing new. The ordinary submit/_source_origin refusal of a human
  Source delivery is unchanged: this path trusts only its recorded intent.

Judgement boundary
  The independent reviewer records its own verdict through work_review; the original parent (or a separately named
  Root synthesis) consumes it. Nothing here records, infers or pre-fills a verdict and nothing here completes Work.

Continuity read
  ``read`` is the Work view ``continuity``. The caller's actual owner_discovery.Scope is admitted BEFORE any lookup;
  then one selected Work's goal, original lifecycle/readiness/current_acceptance (never merged into one status),
  production counts, completion intents with derived readiness, review and delivery standing, the live account
  observation (outside the basis token) and one owner-issued next action or an explicit reason. Bodies stay behind
  their exact reads; pages are bounded (INTENT_PAGE, EVENT_PAGE).
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import re

SCHEMA = 'laplace.work-continuity/1'
RECORD = 'project-work-phase'
INTENT = 'source-completion-intent'
PROOF = 'source-completion-proof'
CONTINUE = 'source-completion-continue'
KINDS = (INTENT, PROOF, CONTINUE)
MAX_SLOTS = 4
INTENT_PAGE = 4
EVENT_PAGE = 4
MAX_REASONS = 8
PARTS = ('summary', 'completion', 'preflight', 'subject')
_REQUEST = re.compile(r'[A-Za-z0-9._:-]{8,96}')
_SHA = '^sha256:[0-9a-f]{64}$'
_SLOT = '^[a-z0-9][a-z0-9._-]{0,47}$'
_INTENT_ID = '^CI-[0-9a-f]{24}$'
ARM_REQUIRED = ('grant_id', 'candidate_id', 'request_id', 'expected_work_revision', 'obligation_id',
                'recipient_binding_id', 'pins', 'proof_slots', 'return_policy')
ACTIVE_EVENT = ('SUBMITTED', 'RESERVED', 'DELIVERED', 'ADMITTED')


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _digest(value) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


# ------------------------------------------------------------------------------------------------ declared shapes

def slot_schema() -> dict:
    return {'type': 'array', 'minItems': 1, 'maxItems': MAX_SLOTS, 'items': {
        'type': 'object', 'required': ['id', 'label'], 'additionalProperties': False,
        'properties': {'id': {'type': 'string', 'pattern': _SLOT}, 'label': {'type': 'string', 'minLength': 1, 'maxLength': 200}}}}


def policy_schema() -> dict:
    from laplace.work import work_delivery as WD
    route = {'type': 'object', 'required': ['admit_idle', 'max_attempts', 'max_depth'], 'additionalProperties': False, 'properties': {
        'admit_idle': {'type': 'boolean'}, 'max_attempts': {'type': 'integer', 'minimum': 1, 'maximum': WD.MAX_RETURN_ATTEMPTS},
        'max_depth': {'type': 'integer', 'minimum': 1, 'maximum': WD.MAX_RETURN_DEPTH}}}
    return {'type': 'object', 'required': ['review_deadline_s', 'max_attempts', 'parent_return'], 'additionalProperties': False,
            'properties': {'review_deadline_s': {'type': 'integer', 'minimum': 60, 'maximum': WD.MAX_DEADLINE_S},
                           'max_attempts': {'type': 'integer', 'minimum': 1, 'maximum': WD.MAX_ATTEMPTS},
                           'parent_return': {'oneOf': [{'type': 'null'}, route]}}}


def source_fields() -> dict:
    """The arm/proof fields of the development_source contract (that door's one declared schema carries them)."""
    from laplace.work.project_work_evidence import artifact_reference_contract
    return {'obligation_id': {'type': 'string', 'pattern': _SLOT}, 'recipient_binding_id': {'type': 'string', 'minLength': 1},
            'pins': {'type': 'object', 'maxProperties': 64, 'additionalProperties': {'type': 'string', 'pattern': _SHA}},
            'proof_slots': slot_schema(), 'return_policy': policy_schema(),
            'intent_id': {'type': 'string', 'pattern': _INTENT_ID}, 'slot_id': {'type': 'string', 'pattern': _SLOT},
            'reference': artifact_reference_contract()}


def delivery_fields() -> dict:
    """The continue fields of the work_delivery contract."""
    return {'intent_id': {'type': 'string', 'pattern': _INTENT_ID}, 'expected_basis': {'type': 'string', 'pattern': _SHA}}


def contract() -> dict:
    """The closed request of the Work view ``continuity``."""
    return {'type': 'object', 'additionalProperties': False, 'properties': {
        'part': {'enum': list(PARTS)}, 'intent_id': {'type': 'string', 'pattern': _INTENT_ID},
        'as_of': {'type': 'string', 'pattern': _SHA}, 'payload': {'type': 'object'}},
        'allOf': [{'if': {'properties': {'part': {'const': 'completion'}}, 'required': ['part']}, 'then': {'required': ['intent_id']}},
                  {'if': {'properties': {'part': {'const': 'preflight'}}, 'required': ['part']}, 'then': {'required': ['payload']}},
                  {'if': {'properties': {'part': {'const': 'subject'}}, 'required': ['part']}, 'then': {'required': ['payload']}}]}


def handle(project, work_id, request=None) -> dict:
    """The exact continuity read (native project, HTTP /work/state and the SDK Work read share it)."""
    from laplace.work.project_work_views import handle as view
    return view(project, {'view': 'continuity', 'id': work_id, 'request': dict(request or {'part': 'summary'})})


def _validate(schema, value, what) -> None:
    from jsonschema import Draft202012Validator
    error = next(Draft202012Validator(schema).iter_errors(value), None)
    if error:
        where = '/'.join(map(str, error.absolute_path)) or '(root)'
        raise ValueError('%s does not match its closed owner contract at %s: %s' % (what, where, error.message[:300]))


def _required(payload, names, what) -> None:
    missing = [name for name in names if payload.get(name) in (None, '', [], {})]
    if missing:
        raise ValueError('%s requires %s.' % (what, ', '.join(missing)))


# ------------------------------------------------------------------------------------------------ ledger views

def _rows(task, kind) -> list:
    return [row for row in task.get('development') or () if row.get('kind') == kind]


def _intent(task, intent_id):
    found = None
    for row in _rows(task, INTENT):
        if row.get('id') == intent_id:
            found = row
    return found


def _find(tasks, intent_id):
    for task in tasks.values():
        row = _intent(task, intent_id)
        if row is not None:
            return task, row
    raise ValueError('Unknown completion intent %s in this project.' % intent_id)


def _fills(task, intent_id) -> dict:
    out = {}
    for row in _rows(task, PROOF):
        if row.get('intent_id') == intent_id:
            out.setdefault(row.get('slot_id'), row)
    return out


def _continued(task, intent_id):
    return next((row for row in _rows(task, CONTINUE) if row.get('intent_id') == intent_id), None)


def _current_intent(task, grant_id, obligation_id):
    """The latest intent of one grant and obligation (a superseding intent is appended after the one it replaces)."""
    found = None
    for row in _rows(task, INTENT):
        if row.get('grant_id') == grant_id and row.get('obligation_id') == obligation_id:
            found = row
    return _intent(task, found['id']) if found else None


def _successor(task, intent_id):
    return next((row['id'] for row in _rows(task, INTENT) if row.get('supersedes') == intent_id), None)


def _withdraw(root, intent, ready) -> None:
    """Record on the Work ledger, the first time a write path observes it, that the producer's Stop withdrew this intent.
    The Stop is durable without this row: the Writing selected-turn Stop owner banks its exact turn/generation request
    before reporting success (turn_control._publish_stop_request) and producer_origin reads it, so CLOSED does not revert
    when the shared marker is replaced or a completed reply races. A pure read never appends this row."""
    from laplace.work import project_work as W
    if intent.get('state') == 'WITHDRAWN' or not any(row['code'] == 'PRODUCER_STOPPED' for row in ready['reasons']):
        return
    W._append(root, {**{key: value for key, value in intent.items() if not key.startswith('_') and key not in ('ts', 'ts_claimed', 'owned_changes')},
                     'state': 'WITHDRAWN', 'ts': _now(), 'withdrawn': {'code': 'PRODUCER_STOPPED', 'basis': ready['basis']}})


def _require_template(task, handoff, intent) -> None:
    """The prepared path never admits a paid review without the complete owner review template, checked under the same
    request identity (REVIEW-<prepared delivery event id>) that the fitted and delivered request carries."""
    from laplace.work import project_work_review as R, work_delivery as WD
    try:
        event_id = WD.prepared_event(task, intent, handoff, intent['work']['scope_revision'])['id']
        R.review_template(task, handoff['id'], intent['obligation_id'], 'REVIEW-' + event_id)
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError('The complete owner review template is unavailable for this prepared handoff; nothing was handed off or '
                         'admitted: ' + str(error)[:300])


def _source_scope(task, obligation_id) -> bool:
    """A declared Source-scope obligation (review_obligations[].scope == 'source') takes the full prepared Source route."""
    obligation = next((row for row in task.get('review_obligations') or () if row.get('id') == obligation_id), {})
    return obligation.get('scope') == 'source'


#: a caller's explicitly selected source_subject is repeated inline in a recovery read only up to this size (compact JSON
#: characters); a larger one is named by an explicit reuse-original template instead, never dropped, cut or rewritten
PREFLIGHT_SUBJECT_INLINE_CHARS = 2000


def preflight_read(project, work_id, grant_id, candidate_id, source_subject=None, *, holder='caller',
                   inline_chars=PREFLIGHT_SUBJECT_INLINE_CHARS) -> dict:
    """The exact existing Source review-preflight read whose selected scaffold and subject complete a Source-scope arm.

    A caller's selected source_subject is preserved: inline when its ACTUALLY EMITTED (ASCII-escaped) JSON fits, else one
    bounded template. holder 'caller' (an arm or preflight refusal) still holds its original, so it is asked to resend it
    unchanged; holder 'retained' (a later reader of a retained intent) may not, and no owner issues a separate exact read of
    a retained subject, so that limitation is stated. A non-object is named as such. Nothing is minted, retained or widened."""
    payload = {'action': 'review-preflight', 'work_id': work_id, 'grant_id': grant_id, 'candidate_id': candidate_id}
    reuse = None
    if source_subject is not None:
        # measured as emitted by the native and HTTP doors: default ASCII-escaped JSON (an astral character is twelve)
        encoded = json.dumps(source_subject, sort_keys=True, default=str)
        if not isinstance(source_subject, dict):
            reuse = {'state': 'NOT_AN_OBJECT', 'field': 'payload.source_subject', 'received': type(source_subject).__name__,
                     'says': 'source_subject is one JSON object (stage, optional prior, carry and accepted_base); correct it, nothing is repeated here.'}
        elif len(encoded) <= inline_chars:
            payload['source_subject'] = copy.deepcopy(source_subject)
        elif holder == 'retained':
            reuse = {'state': 'RETAINED_UNAVAILABLE', 'field': 'payload.source_subject', 'chars': len(encoded),
                     'says': ('The retained subject of this intent is %d escaped characters, above the %d-character inline bound, and no '
                              'owner issues a separate exact read of it. Only its producer, holding the original, can resend it; the '
                              'completion read shows its subject summary.' % (len(encoded), PREFLIGHT_SUBJECT_INLINE_CHARS))}
        else:
            withheld = ('it exceeds the %d-character inline bound' % PREFLIGHT_SUBJECT_INLINE_CHARS if len(encoded) > PREFLIGHT_SUBJECT_INLINE_CHARS
                        else 'repeating it would not let the whole refusal fit the %d-character failure text' % FAILURE_TEXT_CHARS)
            reuse = {'state': 'REUSE_ORIGINAL', 'field': 'payload.source_subject', 'chars': len(encoded), 'complete': False,
                     'says': 'This read is incomplete until you add your original source_subject to its payload unchanged (%s). '
                             'The preflight then derives the same selected subject that arm validates.' % withheld}
    return {'operation': 'development_source', 'payload': payload,
            'http': {'method': 'POST', 'url': '/work/development', 'payload': {'project': project, **payload}},
            **({'source_subject_reuse': reuse} if reuse else {}),
            'meaning': 'Pure Source read for this Work, grant and candidate; distinct from the Work continuity part:preflight template validator.'}


def _recovery_text(project, work_id, grant_id, candidate_id, source_subject, inline_chars=PREFLIGHT_SUBJECT_INLINE_CHARS) -> str:
    """The bounded recovery read an arm refusal names: the same preflight with the caller's own selected subject."""
    read = preflight_read(project, work_id, grant_id, candidate_id, source_subject, inline_chars=inline_chars)
    return json.dumps({key: read[key] for key in ('operation', 'payload', 'source_subject_reuse') if key in read}, sort_keys=True)


#: the existing native failure formatter keeps str(error)[:4000] (native.tools.failure_response and its receipt note), and
#: the HTTP error body carries str(error) whole. A refusal naming a recovery read is composed WHOLE within these characters,
#: so its machine JSON is never cut. This mirrors the formatter's existing cut. It is not a new bound.
FAILURE_TEXT_CHARS = 4000


def _recovery_refusal(project, work_id, grant_id, candidate_id, source_subject, compose) -> ValueError:
    """The complete arm refusal compose(recovery), fitted whole to the failure formatter. The caller's own subject is repeated
    inline only while the WHOLE refusal still fits. Otherwise the read is the truthful incomplete caller-owned template
    (REUSE_ORIGINAL: the caller holds its original and resends it unchanged). If even that read cannot fit (very long escaped
    Work coordinates), no handle is shortened or cut: the refusal names the read in prose for the caller's own coordinates."""
    recovery = ''
    for inline_chars in (PREFLIGHT_SUBJECT_INLINE_CHARS, 0):
        recovery = _recovery_text(project, work_id, grant_id, candidate_id, source_subject, inline_chars)
        message = compose(recovery)
        if len(message) <= FAILURE_TEXT_CHARS:
            return ValueError(message)
    return ValueError(compose('development_source review-preflight for your own work_id, grant_id and candidate_id with your original '
                              'source_subject unchanged (that whole read is %d escaped characters, so this %d-character refusal does not '
                              'repeat it)' % (len(recovery), FAILURE_TEXT_CHARS)))


def _prospective(root, project, tasks, task, intent):
    """The actual handoff, staged Work and delivery event the ONE Continue would compose, without appending any of them."""
    from laplace.work import work_delivery as WD
    _request_id, phase_id = _handoff_id(project, task, intent)
    handoff, staged = next((row for row in task.get('phases') or () if row.get('id') == phase_id), None), task
    if handoff is None:
        handoff = _handoff_row(root, project, tasks, task, intent, {'actor': 'dispatcher'}, contracts=False)
        staged = {**task, 'phases': (*(task.get('phases') or ()), handoff)}
    event = WD.prepared_event(task, intent, handoff, intent['work']['scope_revision'])   # the one factory submit_prepared appends
    return staged, event, handoff


def request_fit(root, project, tasks, task, intent) -> dict:
    """Pure fit of the exact prepared reviewer request through the existing work_delivery composition (_request_text, its
    MAX_REVIEW_REQUEST_BYTES ceiling and bounded re-rendering) before the first irreversible append. Records nothing."""
    from laplace.work import project_work_review as R, work_delivery as WD
    try:
        staged, event, handoff = _prospective(root, project, tasks, task, intent)
    except (ValueError, KeyError, TypeError) as error:
        return {'state': 'UNFIT', 'reason': 'The prepared handoff and delivery cannot be composed: ' + str(error)[:300]}
    try:   # the ACTUAL complete owner template; the request's legacy fallback brief never counts as fitting
        R.review_template(staged, handoff['id'], intent['obligation_id'], 'REVIEW-' + event['id'])
    except ValueError as error:
        return {'state': 'UNFIT', 'reason': 'The complete owner review template is unavailable for this prepared handoff: ' + str(error)[:300]}
    try:
        text = WD._request_text(staged, event, handoff, root)
    except (ValueError, KeyError, TypeError) as error:
        return {'state': 'UNFIT', 'reason': str(error)[:300]}
    return {'state': 'FITS', 'bytes': len(text.encode('utf-8')), 'limit': WD.MAX_REVIEW_REQUEST_BYTES}


def public_intent(row) -> dict:
    origin, production = row.get('origin') or {}, row.get('production') or {}
    return copy.deepcopy({
        'id': row['id'], 'state': row.get('state'), 'work_id': row.get('work_id'), 'grant_id': row.get('grant_id'),
        'obligation_id': row.get('obligation_id'), 'request_id': row.get('request_id'), 'ts': row.get('ts'),
        'origin': {'actor': (origin.get('actor') or {}).get('actor'), 'session_id': origin.get('session_id'), 'turn_id': origin.get('turn_id'),
                   'commission_id': (origin.get('source_execution') or {}).get('commission_id'),
                   'depth': (origin.get('continuation') or {}).get('depth'),
                   'execution_generation': (origin.get('execution_generation') or {}).get('generation')},
        'production': {key: production.get(key) for key in ('candidate_id', 'effect_id', 'effects', 'changed', 'pins', 'effects_scope') if key in production or key != 'effects_scope'}
                      | ({'review_subject': _subject_summary(production)} if production.get('source_review_plan') else {}),
        'policy': row.get('policy'), 'proof_slots': row.get('proof_slots'), 'work': row.get('work'), 'meaning': row.get('meaning')})


def _subject_summary(production):
    """A bounded summary of the recorded subject; a malformed retained shape reads UNKNOWN instead of raising."""
    from laplace.work import development_source as D
    plan = production.get('source_review_plan')
    subject = plan.get('review_subject') if isinstance(plan, dict) else None
    if not isinstance(subject, dict):
        return {'state': 'UNKNOWN', 'reason': 'The retained Source reading plan has no readable review subject.'}
    try:
        return D.subject_summary(subject)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        return {'state': 'UNKNOWN', 'reason': 'The retained review subject cannot be summarised: ' + str(error)[:160]}


def public_proof(row) -> dict:
    return copy.deepcopy({key: row.get(key) for key in ('id', 'intent_id', 'slot_id', 'reference', 'artifact_id', 'path', 'scope',
                                                        'observed_sha256', 'ts', 'meaning')}
                         | {'attached_by': (row.get('attached_by') or {}).get('actor'), 'attached_origin': (row.get('attached_by') or {}).get('origin')})


def public_continue(row) -> dict:
    dispatcher = row.get('dispatcher') or {}
    return copy.deepcopy({key: row.get(key) for key in ('id', 'intent_id', 'handoff_id', 'event_id', 'basis', 'proofs', 'ts')}
                         | {'dispatcher': {key: dispatcher.get(key) for key in ('actor', 'origin', 'session_id', 'turn_id')}})


# ------------------------------------------------------------------------------------------------ arm (genuine producer)

def _arming_generation(root, session_id, turn_id) -> dict:
    """The producer's host generation when it arms, from turn_control.generation_custody (the function the Stop write and
    the Source read share): {state: BOUND|UNBOUND|UNREADABLE, generation: sha256|None}. Recorded on the intent so a Stop
    of THIS generation binds even after the same turn acquires a later host generation (review PHASE-0f221e76 F2)."""
    from laplace.writing import turn_control
    value = turn_control.generation_custody(root, session_id, turn_id)
    return {'state': value['state'], 'generation': value.get('generation')}


def arm(root, project, payload, door) -> dict:
    """Record ONE immutable completion intent while the genuine Source producer is still active (development_source arm)."""
    from laplace.work import development_source as D, project_work as W, project_work_review as R, work_delivery as WD
    from laplace.writing import source_execution as X
    _required(payload, ARM_REQUIRED, 'development_source arm')
    if not _REQUEST.fullmatch(str(payload['request_id'])):
        raise ValueError('arm request_id is a stable client id of 8-96 characters [A-Za-z0-9._:-].')
    _validate(slot_schema(), payload['proof_slots'], 'proof_slots')
    _validate(policy_schema(), payload['return_policy'], 'return_policy')
    slots = [{'id': slot['id'], 'label': slot['label'].strip()} for slot in payload['proof_slots']]
    if len({slot['id'] for slot in slots}) != len(slots) or any(not slot['label'] for slot in slots):
        raise ValueError('Proof slots have unique ids and non-blank labels.')
    acting = D._acting(root, project, door)
    if acting['kind'] != 'native' or acting.get('role') == 'review':
        raise ValueError('Only the genuine ACTIVE Source producer arms a completion intent: an author turn of the grant\'s original '
                         'parent session, attached to its commission. The human door, a review turn or a later operator cannot arm on its behalf.')
    with W.dispatch_lock(root):
        _task, grant = D._find_grant(root, project, payload['grant_id'])
        if not grant.get('native_allowance'):
            raise ValueError('A prepared completion requires an opted-in Source commission (native_allowance), so review and return stay on one fixed account.')
        if acting.get('session_id') != grant.get('parent_session_id'):
            raise ValueError('Only the grant\'s original parent session arms its completion; a delegate or another session cannot.')
        D._current(root, project, grant['id'], 'read', door)   # ACTIVE, unexpired, scope, base, evaluator and the attached turn
        origin = X.producer_origin(root, project, acting['turn_id'])
        expected = X.descriptor(project, grant['work_id'], grant['id'], grant['parent_session_id'], grant['native_allowance'])
        if any(origin['attachment'][key] != expected[key] for key in ('commission_id', 'allowance_revision', 'original_parent_session_id')):
            raise ValueError('The producer turn is attached to another Source commission.')
        if origin['terminal'] or origin['stop_requested']:
            raise ValueError('The producer turn has already ended (%s); a completion is armed before its producer ends.'
                             % (origin['terminal'] or 'Stop requested'))
        if (origin.get('stop_custody') or {}).get('state') == 'UNKNOWN':
            raise ValueError('The producer turn\'s durable Stop custody is UNKNOWN (%s); nothing is armed while a genuine Stop '
                             'request of it is unbound.' % origin['stop_custody'].get('code'))
        tasks = W._tasks(project, root)
        task = tasks[grant['work_id']]
        if payload['expected_work_revision'] != W._task_revision(task):
            raise W.WorkConflict('Read the exact Work before arming its completion.', project, task['id'],
                                 expected=payload['expected_work_revision'], observed=W._task_revision(task), field='expected_work_revision')
        obligation = next((row for row in task.get('review_obligations') or () if row.get('id') == payload['obligation_id']), None)
        if obligation is None:
            raise ValueError('Name a declared review obligation of this Work.')
        if _source_scope(task, obligation['id']):
            # the full prepared Source route: the reading offer AND the explicit typed subject, before any append
            selected = payload.get('source_subject')
            missing = [name for name in ('source_context', 'source_subject') if payload.get(name) is None]
            if not missing and not (isinstance(selected, dict) and selected.get('stage')):
                missing = ['source_subject.stage']
            if missing:
                raise _recovery_refusal(project, task['id'], grant['id'], payload['candidate_id'], payload.get('source_subject'), lambda recovery:
                                        'Obligation %s is Source-scope: a prepared completion needs the exact source_context reading offer and an '
                                 'explicit source_subject (its typed stage, plus any selected prior grants, read-only carry and accepted '
                                 'base); missing %s. Nothing was armed. While this producer is active, read %s, select its scaffold '
                                 'windows as source_context with the authorised subject, then arm again.'
                                 % (obligation['id'], ', '.join(missing), recovery))
        if payload['recipient_binding_id'] != grant.get('evaluator'):
            raise ValueError('The prepared review recipient is the grant\'s approved evaluator binding %s.' % grant.get('evaluator'))
        problem = WD._binding_problem(task, grant['evaluator'], grant.get('evaluator_revision'))
        if problem:
            raise ValueError('Evaluator binding: ' + problem)
        pins = dict(payload['pins'])
        D._review_pins(pins)
        # The SAME cumulative collector as the Source review subject (development_source._commission_chains): every
        # committed effect of this commission across its reissued grants. This grant's own changed paths and the
        # declared obligation inputs must still be pinned, exactly as before; the subject covers the rest.
        effects, chains = D._commission_chains(task, {row['id'] for row in D._commission_grants(task, grant)})
        changed = sorted(chains)
        own = sorted({path for path, chain in chains.items() if any(link['grant_id'] == grant['id'] for link in chain)})
        missing = [path for path in sorted(set(own) | set(obligation.get('inputs') or ())) if path not in pins]
        if missing:
            raise ValueError('Cumulative Source inputs are incomplete: every path changed by any committed effect of this grant and every '
                             'declared obligation input is pinned; missing ' + ', '.join(missing[:8]) + '.')
        basis = D.prepare_review_basis(root, project, task['id'], {'grant_id': grant['id'], 'candidate_id': payload['candidate_id']}, pins, door=door)
        if payload.get('source_subject') is not None and payload.get('source_context') is None:
            raise ValueError('A prepared cumulative subject (source_subject) needs its source_context reading offer.')
        plan = None
        if payload.get('source_context') is not None:
            # The Source owner derives the same cumulative subject, typed stage and read-only carry as an ordinary handoff.
            refusal = lambda compose: _recovery_refusal(project, task['id'], grant['id'], payload['candidate_id'], payload.get('source_subject'), compose)
            try:
                plan = D.prepare_review_plan(root, project, task['id'], basis, pins, payload['source_context'], payload.get('source_subject'))
            except ValueError as error:
                raise refusal(lambda recovery: 'The Source reading offer or subject is invalid (%s); nothing was armed. Read %s and arm again with its '
                                 'selected context and the authorised subject.' % (str(error)[:300], recovery))
            consumed = {path: pins[path] for path in (obligation.get('inputs') or pins)}
            offered = D.review_plan_for_inputs(plan, consumed)
            if offered['state'] != 'COMPLETE':
                raise refusal(lambda recovery: 'The offered Source reading plan is %s for this obligation (%s); nothing was armed. Read %s and select '
                                 'windows covering every change.' % (offered['state'], ', '.join(row['path'] for row in offered['inputs']
                                                                     if row['state'] != 'COMPLETE')[:300], recovery))
        policy = copy.deepcopy(payload['return_policy'])
        route = policy.get('parent_return')
        planned = {'apps': 1 + (1 if route and route.get('admit_idle') else 0), 'sessions': 1}
        standing, capacity, reason = X.account_capacity(root, origin['attachment'], apps=planned['apps'], sessions=planned['sessions'])
        if capacity != 'SUFFICIENT':
            raise X.AllowanceRefused('the account cannot carry the planned review/return chain: ' + str(reason), standing)
        continuation = WD._continuation_intent(root, project, acting, route)
        if route and int(continuation.get('depth') or 0) >= int(route['max_depth']):
            raise ValueError('The producer is already at continuation depth %d; max_depth %d admits no parent return.'
                             % (continuation.get('depth') or 0, route['max_depth']))
        identity = {'project': project, 'work_id': task['id'], 'grant_id': grant['id'], 'obligation_id': obligation['id'],
                    'request_id': payload['request_id']}
        ident = 'CI-' + _digest(identity)[7:31]
        request = {'candidate_id': payload['candidate_id'], 'pins': pins, 'proof_slots': slots, 'return_policy': policy,
                   'recipient_binding_id': grant['evaluator'], 'obligation_id': obligation['id']}
        for key in ('source_context', 'source_subject'):   # absent keys keep a legacy request digest byte-identical
            if payload.get(key) is not None:
                request[key] = copy.deepcopy(payload[key])
        digest = _digest(request)
        existing = _intent(task, ident)
        read = handle(project, task['id'], {'part': 'completion', 'intent_id': ident})
        if existing is not None:
            if existing.get('request_digest') != digest or (existing.get('origin') or {}).get('turn_id') != acting['turn_id']:
                raise ValueError('This request_id already armed a different completion intent (or from another turn); intents are immutable.')
            return {'ok': True, 'reused': True, 'intent': public_intent(existing), 'read': read}
        prior = _current_intent(task, grant['id'], obligation['id'])
        supersedes = None
        if prior is not None:
            if _continued(task, prior['id']) is not None:
                raise ValueError('Grant %s already continued completion intent %s for obligation %s; a later review uses the ordinary route.'
                                 % (grant['id'], prior['id'], obligation['id']))
            if (prior.get('production') or {}).get('effects') == [row['id'] for row in effects] and prior.get('state') != 'WITHDRAWN':
                raise ValueError('Grant %s already holds completion intent %s for obligation %s on this committed production: one immutable '
                                 'intent per grant, obligation and production.' % (grant['id'], prior['id'], obligation['id']))
            supersedes = prior['id']   # the still-active producer replaces its own outgrown or withdrawn intent; history is kept
        work_basis, _issue = W._work_basis(tasks, task['id'])
        row = {'record': RECORD, 'kind': INTENT, 'id': ident, 'work_id': task['id'], 'project': project, 'state': 'ARMED', 'ts': _now(),
               'grant_id': grant['id'], 'obligation_id': obligation['id'], 'request_id': payload['request_id'], 'request_digest': digest,
               'supersedes': supersedes,
               'origin': {'actor': D._actor(root, project, {}, door), 'session_id': acting['session_id'], 'turn_id': acting['turn_id'],
                          'source_execution': copy.deepcopy(origin['attachment']), 'continuation': continuation,
                          'execution_generation': _arming_generation(root, acting['session_id'], acting['turn_id'])},
               'production': {'candidate_id': payload['candidate_id'], 'effect_id': basis['effect_id'], 'effects': [row['id'] for row in effects],
                              'changed': changed, 'pins': pins, 'source_basis': basis, 'effects_scope': 'commission',
                              **({'source_review_plan': plan, 'source_context': copy.deepcopy(payload['source_context']),
                                  **({'source_subject': copy.deepcopy(payload['source_subject'])} if payload.get('source_subject') is not None else {})}
                                 if plan is not None else {})},
               'policy': {'recipient_binding_id': grant['evaluator'], 'recipient_binding_revision': grant.get('evaluator_revision'),
                          'return_policy': policy, 'planned': planned,
                          'planned_meaning': 'One app admission per hop (review, then the approved parent return) and one new review session. '
                                             'Delivery retries reuse the same reserved admission (reserve_app is idempotent per request id), '
                                             'so max_attempts adds none.'},
               'proof_slots': slots,
               'work': {'scope_revision': work_basis['scope_revision'], 'work_revision': W._task_revision(task),
                        'intent_digest': R.intent_digest(task, tasks)},
               'meaning': 'Prepared continuation only: one handoff and the approved review/return under this frozen basis. '
                          'It is not a review, acceptance or completion.'}
        fit = request_fit(root, project, tasks, task, row)
        if fit['state'] != 'FITS':
            raise ValueError('The exact prepared reviewer request of this completion cannot be composed within its bound (%s); '
                             'nothing was armed.' % fit['reason'])
        W._append(root, row)
    return {'ok': True, 'reused': False, 'intent': public_intent(row), 'read': read}


# ------------------------------------------------------------------------------------------------ late proof (arrival fact)

def attach_proof(root, project, payload, door) -> dict:
    """Attach one exact retained project Artifact to a declared slot (development_source proof). Arrival only."""
    from laplace.work import development_source as D, project_work as W
    from laplace.work.project_work_evidence import artifact_reference_contract, _artifact
    _required(payload, ('intent_id', 'slot_id', 'reference'), 'development_source proof')
    _validate(artifact_reference_contract(), payload['reference'], 'proof reference')
    acting = D._acting(root, project, door)
    if acting.get('role') == 'review':
        raise ValueError('A review turn cannot attach peer proof; it records its own review.')
    with W.dispatch_lock(root):
        tasks = W._tasks(project, root)
        task, intent = _find(tasks, payload['intent_id'])
        slot = next((item for item in intent['proof_slots'] if item['id'] == payload['slot_id']), None)
        if slot is None:
            raise ValueError('Name a declared proof slot of this intent: ' + ', '.join(item['id'] for item in intent['proof_slots']) + '.')
        if _continued(task, intent['id']) is not None:
            raise ValueError('This intent already continued; later proof is not attached to it.')
        reference = copy.deepcopy(payload['reference'])
        read = handle(project, task['id'], {'part': 'completion', 'intent_id': intent['id']})
        prior = _fills(task, intent['id']).get(slot['id'])
        if prior is not None and prior.get('reference') != reference:
            raise ValueError('Slot %s already holds another proof; a filled slot is immutable.' % slot['id'])
        try:
            observed, _stamp = _artifact(root, project, reference, verify=True)
        except (ValueError, OSError, KeyError) as error:
            raise ValueError('Peer proof is not an exact retained artifact of this project: ' + str(error)[:300])
        if observed.get('integrity') != 'VERIFIED':
            raise ValueError('Peer proof is %s, not its pinned bytes; nothing was attached.' % observed.get('availability'))
        if prior is not None:
            return {'ok': True, 'reused': True, 'proof': public_proof(prior), 'read': read}
        row = {'record': RECORD, 'kind': PROOF, 'id': 'CP-' + _digest([intent['id'], slot['id']])[7:31], 'work_id': task['id'],
               'project': project, 'intent_id': intent['id'], 'slot_id': slot['id'], 'reference': reference,
               'artifact_id': observed.get('artifact_id'), 'path': observed.get('path'), 'scope': observed.get('scope'),
               'observed_sha256': observed.get('observed_sha256'), 'ts': _now(),
               'attached_by': D._actor(root, project, {'actor': {'role': 'proof-arrival'}}, door),
               'meaning': 'Arrival of declared peer proof; not a review, acceptance or PASS. The attacher is recorded; the proof '
                          'author\'s independence is not verified here.'}
        W._append(root, row)
    return {'ok': True, 'reused': False, 'proof': public_proof(row), 'read': read}


# ------------------------------------------------------------------------------------------------ derived readiness

def readiness(root, project, tasks, task, intent, *, read_context=None) -> dict:
    """Whether ONE intent may continue now, derived from its owners; never stored. States: CONTINUED, READY,
    AWAITING_PROOF (only proof is absent), HELD (a changed or unknown fact may recover) and CLOSED (Stop, spent or
    expired account, cancelled Work or expired binding: nothing resumes it). A Stop binds the producer turn's recorded
    host generation (source_execution._exact_stop_request); a different later host generation of the same turn is not
    that Stop, and a missing, foreign or ambiguous generation gains no Stop authority. A genuine request that no single
    generation binds (unbound, ambiguous after both host records were replaced, unreadable) is PRODUCER_STOP_UNKNOWN:
    HELD, never READY and never inferred absent (Root 0709 B12)."""
    from laplace.work import development_source as D, project_work as W, work_delivery as WD
    from laplace.work.project_work_evidence import _artifact
    from laplace.writing import source_execution as X
    done = _continued(task, intent['id'])
    if done is not None:
        return {'state': 'CONTINUED', 'reasons': [], 'slots': [], 'facts': {}, 'account': None,
                'basis': _digest({'intent': intent['id'], 'continued': done['id']}), 'continued': public_continue(done)}
    closed, held, awaiting, facts, slots = [], [], [], {}, []
    fills = _fills(task, intent['id'])
    for slot in intent['proof_slots']:
        fill = fills.get(slot['id'])
        if fill is None:
            awaiting.append({'code': 'PROOF_ABSENT', 'slot_id': slot['id'], 'reason': 'Declared peer proof %s has not arrived.' % slot['id']})
            slots.append({**slot, 'filled': False, 'integrity': None})
            continue
        try:
            observed, _stamp = _artifact(root, project, fill['reference'], verify=True)
        except (ValueError, OSError, KeyError) as error:
            observed = {'integrity': 'UNKNOWN', 'availability': 'UNAVAILABLE: ' + str(error)[:160]}
        slots.append({**slot, 'filled': True, 'integrity': observed.get('integrity'), 'reference': copy.deepcopy(fill['reference'])})
        if observed.get('integrity') != 'VERIFIED':
            held.append({'code': 'PROOF_CHANGED', 'slot_id': slot['id'], 'reason': 'Attached proof %s is %s now.' % (slot['id'], observed.get('availability'))})
    production = intent['production']
    source = D.validate_review_basis(root, project, task['id'], production['source_basis'], consumed_pins=production['pins'], read_context=read_context)
    facts['source'] = source['status']
    if source['status'] != 'CURRENT':
        held.append({'code': 'SOURCE_' + source['status'], 'reason': source['reason']})
    armed_plan = production.get('source_review_plan')
    subject = armed_plan.get('review_subject') if isinstance(armed_plan, dict) else None
    if isinstance(subject, dict):   # the same owner currentness an ordinary cumulative handoff delivery rechecks
        try:
            observed = D.validate_review_subject(root, project, task['id'], production['source_basis'], subject)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            observed = {'status': 'UNKNOWN', 'reason': 'The recorded review subject cannot be validated: ' + str(error)[:200]}
        facts['source_subject'] = observed['status']
        if observed['status'] != 'CURRENT':
            held.append({'code': 'SOURCE_SUBJECT_' + observed['status'], 'reason': observed['reason']})
    work_basis, issue = W._work_basis(tasks, task['id'])
    facts['scope_revision'] = work_basis.get('scope_revision')
    if issue or work_basis.get('scope_revision') != intent['work']['scope_revision']:
        held.append({'code': 'WORK_SCOPE_CHANGED', 'reason': 'The Work material scope changed since the intent was armed.'})
    if task.get('status') in {'cancelled', 'withdrawn'}:
        closed.append({'code': 'WORK_' + task['status'].upper(), 'reason': 'The Work is ' + task['status'] + '.'})
    policy = intent['policy']
    problem = WD._binding_problem(task, policy['recipient_binding_id'], policy.get('recipient_binding_revision'))
    if problem:
        (closed if 'expired' in problem else held).append({'code': 'RECIPIENT_BINDING', 'reason': problem})
    origin = intent['origin']
    armed = (origin.get('execution_generation') or {}).get('generation')
    try:
        producer = X.producer_origin(root, project, origin['turn_id'], armed_generation=armed)
    except (ValueError, OSError) as error:
        producer = None
        held.append({'code': 'PRODUCER_CUSTODY_UNKNOWN', 'reason': str(error)[:200]})
    if producer is not None:
        # Only Stop is material; an ordinary producer end is expected (late proof) and never invalidates an offered Continue.
        stopped = bool(producer['terminal'] == 'interrupted' or producer['stop_requested'])
        custody = producer.get('stop_custody') or {'state': 'UNKNOWN', 'code': 'CUSTODY_ABSENT'}
        facts['producer_stopped'] = stopped
        facts['producer_stop_custody'] = 'STOPPED' if stopped else custody.get('state')
        if stopped:
            closed.append({'code': 'PRODUCER_STOPPED', 'reason': 'The original producer turn was stopped; its armed continuation is withdrawn.'})
        elif custody.get('state') == 'FOREIGN' and not armed:
            # Only a known arming generation proves a foreign-generation Stop is not the producer's own.
            held.append({'code': 'PRODUCER_STOP_UNKNOWN', 'custody': 'FOREIGN_WITHOUT_ARMING_GENERATION', 'requests_total': custody.get('requests_total'),
                         'reason': 'A genuine Stop request of the producer turn names a host generation other than the current one, and this '
                                   'intent recorded no arming generation, so whether it stopped the producer that armed is unknown.'})
        elif custody.get('state') == 'UNKNOWN':
            held.append({'code': 'PRODUCER_STOP_UNKNOWN', 'custody': custody.get('code'), 'requests_total': custody.get('requests_total'),
                         'reason': 'Genuine durable Stop requests of the original producer turn exist that no single host generation '
                                   'binds (%s); the Stop is neither absent nor proven, so nothing continues on it.' % custody.get('code')})
        if producer['attachment'] != origin['source_execution']:
            held.append({'code': 'PRODUCER_COMMISSION_CHANGED', 'reason': 'The producer turn no longer resolves to the recorded commission.'})
    planned = policy['planned']
    standing, capacity, reason = X.account_capacity(root, origin['source_execution'], apps=planned['apps'], sessions=planned['sessions'])
    facts['account'] = {'state': standing.get('state'), 'capacity': capacity}
    if capacity == 'UNKNOWN':
        held.append({'code': 'ACCOUNT_UNKNOWN', 'reason': reason})
    elif capacity != 'SUFFICIENT':
        closed.append({'code': 'ACCOUNT_CLOSED', 'reason': reason})
    if intent.get('state') == 'WITHDRAWN' and not any(row['code'] == 'PRODUCER_STOPPED' for row in closed):
        closed.append({'code': 'PRODUCER_STOPPED', 'reason': 'A Stop of the original producer was durably recorded; its armed continuation is withdrawn.'})
    successor = _successor(task, intent['id'])
    if successor:
        closed.append({'code': 'SUPERSEDED', 'successor': successor, 'reason': 'The producer armed superseding intent %s.' % successor})
    if production.get('effects_scope') == 'commission':
        armed_grant = next((row for row in D._latest_per_id(D.rows(task, 'grant')) if row.get('id') == intent['grant_id']), None)
        committed = ([row['id'] for row in D._commission_chains(task, {g['id'] for g in D._commission_grants(task, armed_grant)})[0]]
                     if armed_grant else [])
    else:   # a legacy intent keeps its original grant-only production meaning
        committed = [row['id'] for row in D._latest_per_id(D.rows(task, 'effect'))
                     if row.get('grant_id') == intent['grant_id'] and row.get('state') == 'COMMITTED']
    if not successor and committed != list(production.get('effects') or []):
        closed.append({'code': 'PRODUCTION_ADVANCED', 'reason': 'The grant committed %d further effect(s) after this intent was armed, so the armed '
                       'basis no longer describes the completion. While the producer is active it may arm a superseding intent; otherwise '
                       'use the ordinary handoff route.' % (len(committed) - len(production.get('effects') or []))})
    declared = next((row for row in task.get('review_obligations') or () if row.get('id') == intent['obligation_id']), {})
    wanted = {path: digest for path, digest in production['pins'].items() if not declared.get('inputs') or path in declared['inputs']}
    reviewed = next((row['id'] for row in reversed(task.get('phases') or ()) if row.get('phase') == 'review'
                     and row.get('obligation_id') == intent['obligation_id'] and row.get('pins') == wanted), None)
    if reviewed and source['status'] == 'CURRENT':
        closed.append({'code': 'ALREADY_REVIEWED', 'review_id': reviewed, 'reason': 'Obligation %s already has review %s of these exact '
                       'bytes; Continue would pay for a duplicate review.' % (intent['obligation_id'], reviewed)})
    for event_id in dict.fromkeys(row['id'] for row in WD._rows(task, WD.EVENT)):
        history = WD._history(task, event_id)
        if (history[0].get('obligation_id') == intent['obligation_id'] and history[-1]['state'] in ACTIVE_EVENT
                and (history[0].get('prepared_completion') or {}).get('intent_id') != intent['id']):
            held.append({'code': 'DELIVERY_ACTIVE', 'event_id': event_id,
                         'reason': 'Delivery %s of this obligation is still %s.' % (event_id, history[-1]['state'])})
    if _source_scope(task, intent['obligation_id']):
        # an uncontinued Source-scope intent is transportable only with its armed plan and explicit typed subject
        plan, chosen = production.get('source_review_plan'), production.get('source_subject')
        recovery = preflight_read(project, task['id'], intent['grant_id'], production.get('candidate_id'), production.get('source_subject'),
                                  holder='retained')
        if not plan or not isinstance(chosen, dict) or not chosen.get('stage'):
            held.append({'code': 'SOURCE_REVIEW_PLAN_ABSENT', 'read': recovery,
                         'reason': 'This immutable Source-scope intent was armed without its source_context plan and explicit source_subject, '
                                   'so it cannot take the full prepared Source route and no later plan is grafted onto it. It is not replaced '
                                   'on the same committed production: arm refuses a second intent for this grant, obligation and production, and '
                                   'only the still-active original producer whose grant committed further production (or whose intent a Stop '
                                   'withdrew) may arm a superseding one. Otherwise use a new bounded Source route; before any first arm, read '
                                   'this review-preflight and arm with its selected context and subject.'})
        elif not (isinstance(plan, dict) and isinstance(plan.get('review_subject'), dict) and isinstance(chosen.get('stage'), dict)
                  and isinstance(plan['review_subject'].get('stage') or {}, dict)):
            held.append({'code': 'SOURCE_REVIEW_PLAN_INVALID', 'read': recovery,
                         'reason': 'The armed Source plan or subject has a malformed shape (plan %s, subject %s, stage %s).'
                                   % (type(plan).__name__, type(plan.get('review_subject')).__name__ if isinstance(plan, dict) else 'absent',
                                      type(chosen.get('stage')).__name__)})
        else:
            wanted = list(declared.get('inputs') or production['pins'])
            unpinned = [path for path in wanted if path not in production['pins']]
            recorded_stage = (plan['review_subject'].get('stage') or {}).get('id')
            try:
                offered = {'state': 'INCOMPLETE'} if unpinned else D.review_plan_for_inputs(plan, {path: production['pins'][path] for path in wanted})
            except (ValueError, KeyError, TypeError, AttributeError) as error:
                offered = {'state': 'INVALID', 'error': str(error)[:200]}
            facts['source_review_plan'] = offered['state']
            if offered['state'] == 'INVALID':
                held.append({'code': 'SOURCE_REVIEW_PLAN_INVALID', 'read': recovery,
                             'reason': 'The armed Source reading plan cannot be projected onto this obligation: ' + offered['error']})
            elif offered['state'] != 'COMPLETE':
                held.append({'code': 'SOURCE_REVIEW_PLAN_INCOMPLETE', 'read': recovery, 'unpinned': unpinned[:8],
                             'reason': 'The armed Source reading plan is %s for this obligation.' % offered['state']})
            recorded_request = plan['review_subject'].get('request')
            # the WHOLE recorded subject request (stage, selected prior grants, carry, accepted base); a legacy subject without
            # a recorded request is compared on its stage identity only
            if (recorded_request != chosen) if recorded_request is not None else (recorded_stage != chosen['stage'].get('id')):
                held.append({'code': 'SOURCE_SUBJECT_MISMATCH', 'read': recovery,
                             'reason': 'The chosen source_subject (stage %s) is not the exact subject request the recorded plan was prepared '
                                       'from (stage %s).' % (chosen['stage'].get('id'), recorded_stage)})
    if not closed and not held:
        fit = request_fit(root, project, tasks, task, intent)
        facts['review_request'] = fit['state']
        if fit['state'] != 'FITS':
            held.append({'code': 'REVIEW_REQUEST_UNFIT', 'reason': 'The exact prepared reviewer request cannot be composed within its bound: ' + fit['reason']})
    state = 'CLOSED' if closed else 'HELD' if held else 'AWAITING_PROOF' if awaiting else 'READY'
    reasons = closed + held + awaiting
    token = _digest({'intent': intent['id'], 'state': state, 'codes': [row['code'] for row in reasons],
                     'fills': {key: value.get('reference') for key, value in sorted(fills.items())}, 'facts': facts})
    return {'state': state, 'reasons': reasons, 'slots': slots, 'facts': facts, 'basis': token, 'account': standing}


def _public_ready(ready) -> dict:
    return copy.deepcopy({key: ready.get(key) for key in ('state', 'basis', 'slots', 'facts', 'continued') if key in ready}
                         | {'reasons': (ready.get('reasons') or [])[:MAX_REASONS], 'reasons_total': len(ready.get('reasons') or [])})


# ------------------------------------------------------------------------------------------------ the owner-issued Continue

def _handoff_id(project, task, intent):
    from laplace.work import project_work_review as R
    request_id = 'CONT-HANDOFF-' + intent['id'][3:]
    return request_id, 'PHASE-' + R._digest([project, task['id'], 'handoff', request_id])[7:31]


def _handoff(root, project, tasks, task, intent, dispatcher) -> dict:
    """The ONE handoff phase of this intent: the original producer's recorded basis, actor and pins; dispatcher beside.
    Before its append the complete owner review template and the exact prepared reviewer request must compose in bound."""
    from laplace.work import project_work as W
    _request_id, phase_id = _handoff_id(project, task, intent)
    prior = next((row for row in task.get('phases') or () if row.get('id') == phase_id), None)
    if prior is not None:
        _require_template(task, prior, intent)
        return prior
    row = _handoff_row(root, project, tasks, task, intent, dispatcher)
    staged = {**task, 'phases': (*(task.get('phases') or ()), row)}
    _require_template(staged, row, intent)
    fit = request_fit(root, project, tasks, staged, intent)
    if fit['state'] != 'FITS':
        raise ValueError('The exact prepared reviewer request cannot be composed within its bound; nothing was handed off or admitted: '
                         + fit['reason'])
    W._append(root, row)
    return row


def _handoff_row(root, project, tasks, task, intent, dispatcher, *, contracts=True) -> dict:
    """The handoff row the ONE Continue appends; pure. contracts=False omits the published Source contracts, which the
    reviewer request does not render (request_fit)."""
    from laplace.work import project_work as W, project_work_review as R
    request_id, phase_id = _handoff_id(project, task, intent)
    work_basis, _issue = W._work_basis(tasks, task['id'])
    production = intent['production']
    fills = _fills(task, intent['id'])
    row = {'record': R.PHASE_RECORD, 'kind': R.PHASE_KIND, 'id': phase_id, 'work_id': task['id'], 'project': project, 'phase': 'handoff',
           'request_id': request_id, 'ts': _now(), 'basis': {'work_revision': work_basis['revision'], 'work_scope_revision': work_basis['scope_revision']},
           'actor': copy.deepcopy(intent['origin']['actor']),
           'summary': 'Prepared Source completion %s: the original producer\'s armed handoff, dispatched once after its declared peer proof arrived.' % intent['id'],
           'evidence': [], 'obligations': [intent['obligation_id']],
           'object': {'kind': 'source', 'repository': production['source_basis']['repository'], 'base': production['source_basis']['base'],
                      'checkpoint': production['source_basis']['effect_id']},
           'pins': copy.deepcopy(production['pins']), 'source_basis': copy.deepcopy(production['source_basis']),
           'continuation_origin': {'intent_id': intent['id'], 'dispatcher': copy.deepcopy(dispatcher),
                                   'proofs': [{'slot_id': key, 'proof_id': value['id'], 'reference': copy.deepcopy(value['reference'])}
                                              for key, value in sorted(fills.items())],
                                   'meaning': 'Peer proof arrival enabled this handoff; it is not independent review.'}}
    if production.get('source_review_plan'):
        # The armed cumulative subject, typed stage and reading offer travel unchanged into the ONE handoff; the latest
        # candidate stays its anchor. Delivery binds and revalidates them exactly as for an ordinary handoff.
        row.update(source_review_plan=copy.deepcopy(production['source_review_plan']), source_context=copy.deepcopy(production['source_context']),
                   **({'source_subject': copy.deepcopy(production['source_subject'])} if 'source_subject' in production else {}))
        row['summary'] = ('Prepared Source completion %s: the original producer\'s armed cumulative subject %s, dispatched once after its '
                          'declared peer proof arrived.' % (intent['id'], production['source_review_plan']['review_subject']['subject_id']))
    else:
        row['source_review_plan_absent'] = ('No Source reading plan was supplied for this non-Source (guide or legacy) obligation; the '
                                            'reviewer reads the full pinned inputs through the configured repository.')
    obligation = next((item for item in task.get('review_obligations') or () if item.get('id') == intent['obligation_id']), {})
    if contracts and obligation.get('source_contract'):
        from laplace.work import source_contracts
        row['source_contracts'] = {obligation['id']: source_contracts.publish(root, obligation['source_contract'])}
    return row


def continue_intent(root, project, payload, door) -> dict:
    """work_delivery continue: the existing handoff and Work delivery once, from a READY intent."""
    from laplace.work import development_source as D, project_work as W, work_delivery as WD
    _required(payload, ('intent_id', 'expected_basis'), 'work_delivery continue')
    acting = D._acting(root, project, door)
    if acting.get('role') == 'review':
        raise ValueError('A review turn cannot continue a delivery; it records its own review.')
    dispatcher = D._actor(root, project, {'actor': {'role': 'dispatcher'}}, door)
    with W.dispatch_lock(root):
        tasks = W._tasks(project, root)
        task, intent = _find(tasks, payload['intent_id'])
        done = _continued(task, intent['id'])
        replay = done is not None
        if not replay:
            ready = readiness(root, project, tasks, task, intent)
            if payload['expected_basis'] != ready['basis']:
                conflict = W.WorkConflict('The completion readiness changed since it was read; nothing was continued.', project, task['id'],
                                          expected=payload['expected_basis'], observed=ready['basis'], field='expected_basis')
                conflict.details['next_reads'] = [handle(project, task['id'], {'part': 'completion', 'intent_id': intent['id']})]
                conflict.details['readiness'] = _public_ready(ready)
                _withdraw(root, intent, ready)
                raise conflict
            if ready['state'] != 'READY':
                _withdraw(root, intent, ready)
                raise ValueError('Completion intent %s is %s: %s' % (intent['id'], ready['state'],
                                 '; '.join(row['reason'] for row in ready['reasons'][:4])))
            handoff = _handoff(root, project, tasks, task, intent, dispatcher)
            task = W._tasks(project, root)[task['id']]
            event_id = WD.submit_prepared(root, project, task, intent, handoff, dispatcher, basis=ready['basis'])
            done = {'record': RECORD, 'kind': CONTINUE, 'id': 'CC-' + _digest({'intent': intent['id']})[7:31], 'work_id': task['id'],
                    'project': project, 'intent_id': intent['id'], 'handoff_id': handoff['id'], 'event_id': event_id,
                    'dispatcher': dispatcher, 'basis': ready['basis'],
                    'proofs': [{'slot_id': row['id'], 'reference': row.get('reference')} for row in ready['slots']], 'ts': _now()}
            W._append(root, done)
    # the existing transport and its request-id reconciliation; a replay or lost acknowledgement admits nothing new
    WD.recover(root, project, {'event_id': done['event_id']}, door)
    task = W._tasks(project, root)[intent['work_id']]
    return {'ok': True, 'reused': replay, 'continued': public_continue(done),
            'event': WD._facet_event(root, project, task, done['event_id']),
            'read': handle(project, task['id'], {'part': 'completion', 'intent_id': intent['id']})}


# ------------------------------------------------------------------------------------------------ the continuity read

def _subject(project, task, tasks) -> dict:
    from laplace.work import project_work as W
    work_basis, issue = W._work_basis(tasks, task['id'])
    return {'namespace': project, 'id': task['id'], 'qualified_id': project + '::' + task['id'], 'work_revision': W._task_revision(task),
            'scope_revision': work_basis.get('scope_revision'), 'containment_issue': issue}


def _intent_next(project, intent, ready, mode='human'):
    if ready['state'] == 'READY':
        return {'kind': 'continue', 'callable': mode != 'review',
                **({'callable_reason': 'A review-role caller cannot continue a delivery; an author-role turn or the human door can.'}
                   if mode == 'review' else {}),
                'reason': 'Declared peer proof has arrived and every predicate holds: one owner Continue records the handoff and the approved delivery once.',
                'action': {'operation': 'work_delivery', 'payload': {'action': 'continue', 'intent_id': intent['id'], 'expected_basis': ready['basis']},
                           # the existing human door of the same owner action (work_delivery.handle via POST /work/delivery)
                           'http': {'method': 'POST', 'url': '/work/delivery', 'payload': {'project': project, 'action': 'continue',
                                    'intent_id': intent['id'], 'expected_basis': ready['basis']}}}}
    if ready['state'] == 'AWAITING_PROOF':
        slot = next(row['slot_id'] for row in ready['reasons'] if row['code'] == 'PROOF_ABSENT')
        payload = {'action': 'proof', 'intent_id': intent['id'], 'slot_id': slot, 'reference': {'id': '<ART-id>', 'expected_sha256': '<sha256>'}}
        return {'kind': 'attach-proof', 'callable': False, 'template': True, 'fill': ['payload.reference'],
                'reason': 'Waiting for declared peer proof %s; its exact retained Artifact is attached when it arrives (arrival only).' % slot,
                'action': {'operation': 'development_source', 'payload': payload,
                           'http': {'method': 'POST', 'url': '/work/development', 'payload': {'project': project, **payload}}}}
    return None


def _held_next(project, task, ready) -> dict:
    """No positive action derives from this intent (HELD, CLOSED or CONTINUED): its exact reason codes and the owner read
    whose standing can change them. A HELD intent recovers only when its owner fact recovers; nothing here retries it."""
    from laplace.work.project_work_views import handle as view
    reasons = ready.get('reasons') or []
    return {'kind': 'inspect', 'callable': False, 'reason': ready['state'], 'codes': [row['code'] for row in reasons][:MAX_REASONS],
            'detail': '; '.join(row['reason'] for row in reasons[:3]), 'read': view(project, {'view': 'detail', 'id': task['id']})}


def _events(task) -> tuple:
    from laplace.work import work_delivery as WD
    ids = list(dict.fromkeys(row['id'] for row in WD._rows(task, WD.EVENT)))[::-1]
    out = []
    for event_id in ids[:EVENT_PAGE]:
        history = WD._history(task, event_id)
        first, latest = history[0], history[-1]
        admitted = next((row for row in reversed(history) if row.get('turn_id')), None)
        out.append({'id': event_id, 'state': latest['state'], 'obligation_id': first.get('obligation_id'), 'handoff_id': first.get('handoff_id'),
                    'admitted': {'session_id': admitted.get('session_id'), 'turn_id': admitted.get('turn_id')} if admitted else None,
                    'prepared_completion': (first.get('prepared_completion') or {}).get('intent_id'),
                    'dispatcher_origin': (first.get('dispatcher') or {}).get('origin'), 'reason': latest.get('reason'),
                    'read': {'operation': 'work_delivery', 'payload': {'action': 'status', 'event_id': event_id}}})
    return out, len(ids)


def _next(project, task, row, judged, events, mode='human') -> dict:
    from laplace.work import project_work_review as R
    from laplace.work.project_work_views import handle as view
    for intent, ready in judged:
        found = _intent_next(project, intent, ready, mode) if ready['state'] == 'READY' else None
        if found:
            return found
    for intent, ready in judged:
        found = _intent_next(project, intent, ready, mode) if ready['state'] == 'AWAITING_PROOF' else None
        if found:
            return found
    active = next((event for event in events if event['state'] in ACTIVE_EVENT), None)
    if active:
        return {'kind': 'await-delivery', 'callable': False, 'read': active['read'],
                'reason': 'Delivery %s is %s; its recipient acts under its own identity and nothing needs another model turn to transfer it.'
                          % (active['id'], active['state'])}
    review = row.get('review') or {}
    upcoming = (review.get('next') or {}).get('kind')
    disposition = (review.get('next') or {}).get('disposition')
    if disposition and disposition.get('status') in ('HOLD', 'REJECTED') and disposition.get('currentness') == 'CURRENT':
        # The recorded verdict binds: the next step addresses its findings (revised handoff or follow-up), never a new paid review.
        return {'kind': 'address-review', 'callable': False, 'disposition': copy.deepcopy(disposition),
                'read': disposition.get('read') or view(project, {'view': 'review', 'id': task['id']}),
                'reason': review['next'].get('says') or 'The recorded review verdict stays binding until its findings are addressed.'}
    # A superseded intent is permanent history (its successor carries the production); it never masks the live next step.
    stopped = [(intent, ready) for intent, ready in judged if ready['state'] == 'HELD'
               or ready['state'] == 'CLOSED' and not any(r['code'] == 'SUPERSEDED' for r in ready['reasons'])]
    if stopped:
        intent, ready = stopped[0]
        return {'kind': 'inspect', 'callable': False, 'intent_id': intent['id'], 'state': ready['state'],
                'codes': [r['code'] for r in ready['reasons']][:MAX_REASONS], 'detail': '; '.join(r['reason'] for r in ready['reasons'][:3]),
                'read': handle(project, task['id'], {'part': 'completion', 'intent_id': intent['id']}),
                'reason': 'Completion intent %s is %s: %s' % (intent['id'], ready['state'], '; '.join(r['reason'] for r in ready['reasons'][:3]))}
    if upcoming in R.PHASES:
        preparation = R.preparation(review, [upcoming], row.get('work_revision'))['phases'].get(upcoming) or {}
        if not preparation.get('refused'):
            payload = {'id': task['id'], 'phase': upcoming, 'request_id': '<stable request id>', **(preparation.get('basis') or {})}
            return {'kind': 'record-' + upcoming, 'callable': False, 'template': True,
                    **({'disposition': copy.deepcopy(disposition)} if disposition else {}), 'fill': ['payload.request_id'] + [
                        'payload.' + item['path'] for item in preparation.get('inputs') or () if item.get('required')],
                    'reason': preparation.get('says') or 'The review lifecycle names this phase next.',
                    'action': {'operation': 'work_review', 'payload': payload}, 'preparation': preparation}
    return {'kind': 'inspect', 'callable': False, 'read': view(project, {'view': 'detail', 'id': task['id']}),
            'reason': 'No owner-issued positive action derives from the current records; the detail view carries every guarded action.'}


# ------------------------------------------------------------------------------------------------ bounded subject pages (F2)

#: Section -> page row bound of ONE recorded cumulative review subject. These pages are the exact continuations the
#: byte-bounded reviewer request (work_delivery) issues for every list it could not inline: the recorded rows in their
#: own order, never a read of a source file. Every page is also byte-bounded.
SUBJECT_SECTIONS = {'changed_files': 64, 'hunks': 256, 'readonly_carry': 256, 'effects': 256, 'inputs': 16, 'initial_reads': 64}
SUBJECT_PAGE_BYTES = 48 * 1024
_PROJECTED = ('inputs', 'initial_reads')


def subject_page_schema() -> dict:
    return {'type': 'object', 'additionalProperties': False, 'required': ['phase_id', 'section'], 'properties': {
        'phase_id': {'type': 'string', 'pattern': '^PHASE-[A-Za-z0-9._:-]{1,96}$'}, 'section': {'enum': list(SUBJECT_SECTIONS)},
        'path': {'type': 'string', 'minLength': 1, 'maxLength': 400}, 'obligation_id': {'type': 'string', 'minLength': 1, 'maxLength': 96},
        'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': max(SUBJECT_SECTIONS.values())},
        # issued continuations only: the section cut a page series is pinned to, and the exact row descent of a NOT_EXPANDED row
        'cut': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}, 'item_sha256': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'},
        'item_offset': {'type': 'integer', 'minimum': 0}},
        'allOf': [{'if': {'properties': {'section': {'const': 'hunks'}}, 'required': ['section']}, 'then': {'required': ['path']}},
                  {'if': {'properties': {'section': {'enum': list(_PROJECTED)}}, 'required': ['section']}, 'then': {'required': ['obligation_id']}},
                  {'if': {'required': ['item_offset']}, 'then': {'required': ['item_sha256']}},
                  {'if': {'required': ['item_sha256']}, 'then': {'required': ['item_offset']}}]}


def subject_page_handle(project, work_id, phase_id, section, offset=0, *, path=None, obligation_id=None, cut=None,
                        item_sha256=None, item_offset=None) -> dict:
    """The ONE exact read of a subject page; the bounded request, each page's next (pinned to its section cut) and the
    exact descent of a NOT_EXPANDED row (item_sha256/item_offset) all use it."""
    payload = {'phase_id': phase_id, 'section': section, 'offset': offset}
    if path is not None:
        payload['path'] = path
    if obligation_id is not None:
        payload['obligation_id'] = obligation_id
    if cut is not None:
        payload['cut'] = cut
    if item_sha256 is not None:
        payload.update(item_sha256=item_sha256, item_offset=item_offset or 0)
    return handle(project, work_id, {'part': 'subject', 'payload': payload})


def subject_rows(plan, section, path=None, hunk_read=None) -> list:
    """The rows of one section of a recorded reading plan and its cumulative subject, in recorded order. The bounded
    request lists a prefix of exactly these rows (or a same-order projection) and pages continue at its offset."""
    from laplace.work import work_delivery as WD
    subject = plan.get('review_subject') or {}
    if section == 'changed_files':
        return [{**{key: value for key, value in row.items() if key != 'geometry'},
                 'geometry': {key: value for key, value in row['geometry'].items() if key != 'hunks'}} for row in subject.get('changed_files') or ()]
    if section == 'hunks':
        row = next((item for item in subject.get('changed_files') or () if item['path'] == path), None)
        if row is None:
            raise ValueError('This review subject changed no file %s.' % path)
        return list(row['geometry']['hunks'])
    if section == 'readonly_carry':
        return list((subject.get('readonly_carry') or {}).get('members') or ())
    if section == 'effects':
        return list(subject.get('effects') or ())
    if section == 'initial_reads':
        return [WD.native_initial_read(read) for item in plan.get('inputs') or () for read in item.get('initial_reads') or ()]
    rows = []
    for item in plan.get('inputs') or ():
        geometry = (item.get('cumulative_change') or {}).get('geometry') or {}
        rows.append({'path': item['path'], 'state': item.get('state'), 'changed': item.get('changed'),
                     'verified_edits': len((item.get('verified_edits') or {}).get('edits') or ()),
                     'geometry': geometry.get('state'), 'hunks': geometry.get('hunks_total'),
                     'uncovered_hunk_ids': item.get('uncovered_hunk_ids'), 'uncovered_edit_ids': item.get('uncovered_edit_ids'),
                     'uninspected_extents': item.get('uninspected_extents'),
                     'hunks_read': hunk_read(item['path']) if hunk_read and geometry.get('hunks_total') else None})
    return rows


SUBJECT_PAGE_MEANING = ('Exact rows of the cumulative review subject recorded on this handoff, in its own order: review scope, not a read of any '
                        'source file. Pins identify bytes; read a file through its pinned repository read. Currentness is the delivery owner\'s guard. '
                        'A page holding fewer rows than requested_limit omits nothing: next continues at the next row, pinned to this section '
                        'cut. A row with expanded:false is delivered by its exact detail_read pages (canonical row JSON, row_sha256).')
SUBJECT_ITEM_UNITS = 'Unicode characters of the canonical row JSON (sort_keys, compact separators, unescaped UTF-8)'


def _subject_refusal(project, task, message, field, expected, observed, restart):
    from laplace.work import project_work as W
    conflict = W.WorkConflict(message, project, task['id'], expected=expected, observed=observed, field=field)
    conflict.details['next_reads'] = [copy.deepcopy(restart)]
    conflict.details['restart_read'] = copy.deepcopy(restart)   # the exact typed restart of this section series
    return conflict


def subject_page(project, task, payload, wrap=None) -> dict:
    """One bounded page of the cumulative review subject recorded on ONE handoff of this Work (F2). Input sections are
    the same projection onto the named obligation's consumed inputs that its delivery request renders.

    The WHOLE composed response wrap(page) (the continuity envelope, every handle and the meaning) fits the shared delivery
    line (writing.delivery owner_line, which already reserves the native receipts and envelope; else the navigation line
    nav.CAP) in the largest encoding any door emits (development_source._encoded). Pages hold the largest fitting ordered
    prefix; a row that alone exceeds the line becomes a NOT_EXPANDED header whose detail_read pages its exact canonical
    JSON. Nothing is clipped, dropped or capped; every page advances; continuations pin the section cut."""
    from laplace.work import development_source as D, project_work_navigation as nav, work_delivery as WD
    from laplace.writing import delivery
    _validate(subject_page_schema(), payload, 'Subject page request')
    phase = next((row for row in task.get('phases') or () if row.get('id') == payload['phase_id'] and row.get('phase') == 'handoff'), None)
    plan = (phase or {}).get('source_review_plan') or {}
    subject = plan.get('review_subject')
    if subject is None:
        raise ValueError('This handoff records no cumulative review subject.')
    if subject.get('subject_id') != 'DRS-' + D._digest({key: value for key, value in subject.items() if key != 'subject_id'})[7:]:
        raise ValueError('The recorded review subject identity does not match its content.')
    section = payload['section']
    if section in _PROJECTED:
        plan = D.review_plan_for_inputs(plan, WD._source_consumed_pins(task, {'obligation_id': payload['obligation_id']}, phase))
    rows = subject_rows(plan, section, payload.get('path'),
                        hunk_read=lambda path: subject_page_handle(project, task['id'], payload['phase_id'], 'hunks', 0, path=path))
    wrap = wrap or (lambda page: page)
    phase_id, total = payload['phase_id'], len(rows)
    keys = {'path': payload.get('path'), 'obligation_id': payload.get('obligation_id')}
    pinned = _digest({'subject': subject['subject_id'], 'phase': phase_id, 'section': section, **keys, 'rows': rows})
    restart = subject_page_handle(project, task['id'], phase_id, section, 0, **keys)
    if payload.get('cut') and payload['cut'] != pinned:
        raise _subject_refusal(project, task, 'The rows of this subject section changed since its pages were issued; old pages were not '
                               'mixed. restart_read is the exact restart of this section.', 'cut', payload['cut'], pinned, restart)
    offset = payload.get('offset', 0)
    if offset > total:
        raise _subject_refusal(project, task, 'Offset %d is beyond the %d recorded rows of this subject section.' % (offset, total),
                               'offset', total, offset, restart)
    line = delivery.owner_line()
    line = nav.CAP if line is None else line
    fits = lambda value: D._encoded(value) <= line
    after = lambda at: subject_page_handle(project, task['id'], phase_id, section, at, **keys, cut=pinned) if at < total else None
    base = {'phase_id': phase_id, 'review_subject_id': subject['subject_id'], 'section': section, **keys, 'cut': pinned, 'offset': offset}
    if 'item_sha256' in payload:
        return _subject_item(project, task, payload, rows, base, wrap, fits, after, restart, line)
    requested = min(payload.get('limit', SUBJECT_SECTIONS[section]), SUBJECT_SECTIONS[section])

    def header(index):
        row, digest = rows[index], D._row_sha(rows[index])
        return {'index': index, **({'path': row['path']} if isinstance(row.get('path'), str) else {}), 'expanded': False,
                'row_sha256': digest, 'row_chars': len(D._row_text(row)),
                'counts': {key: len(value) for key, value in sorted(row.items()) if isinstance(value, (list, tuple, dict))},
                'detail_read': subject_page_handle(project, task['id'], phase_id, section, index, **keys, cut=pinned, item_sha256=digest, item_offset=0)}

    def build(count, compact=False):
        items = [header(offset)] if compact else copy.deepcopy(rows[offset:offset + count])
        return wrap({**base, 'returned': len(items), 'total': total, 'requested_limit': requested, 'items': items,
                     'next': after(offset + len(items)), 'meaning': SUBJECT_PAGE_MEANING})
    count = min(requested, total - offset)
    page = build(count)
    if count > 1 and not fits(page):
        low, high = 1, count - 1
        while low < high:
            middle = (low + high + 1) // 2
            if fits(build(middle)):
                low = middle
            else:
                high = middle - 1
        count, page = low, build(low)
    compact = bool(count) and not fits(page)
    if compact:
        page = build(1, compact=True)
    delivery.record_projection('subject', {'section': section, 'offset': offset, 'returned': min(count, 1) if compact else count,
                                           'requested_limit': requested, 'not_expanded': [offset] if compact else []})
    return page


def _subject_item(project, task, payload, rows, base, wrap, fits, after, restart, line):
    """ONE page of the exact canonical JSON of one NOT_EXPANDED subject row, pinned to its row_sha256, paged in Unicode
    characters, fitted (whole composed response) to the same line; at its end the page continues with the next row page."""
    from laplace.work import development_source as D
    from laplace.writing import delivery
    index = base['offset']
    if index >= len(rows):
        raise _subject_refusal(project, task, 'Row %d is beyond the %d recorded rows of this subject section.' % (index, len(rows)),
                               'offset', len(rows), index, restart)
    text, digest = D._row_text(rows[index]), D._row_sha(rows[index])
    if payload['item_sha256'] != digest:
        raise _subject_refusal(project, task, 'Row %d of this subject section no longer has the pinned row_sha256; restart_read is the '
                               'exact restart of this section.' % index, 'item_sha256', payload['item_sha256'], digest, restart)
    start = payload['item_offset']
    if start > len(text):
        raise _subject_refusal(project, task, 'item_offset %d is beyond the %d characters of row %d.' % (start, len(text), index),
                               'item_offset', len(text), start, restart)

    def build(end):
        return wrap({**base, 'returned': 0, 'total': len(rows), 'items': [],
                     'item': {'index': index, 'expanded': False, 'row_sha256': digest, 'row_chars': len(text), 'units': SUBJECT_ITEM_UNITS,
                              'offset': start, 'end_offset': end, 'content': text[start:end], 'eof': end == len(text),
                              'next_read': (subject_page_handle(project, task['id'], base['phase_id'], base['section'], index, path=base['path'],
                                                                obligation_id=base['obligation_id'], cut=base['cut'], item_sha256=digest,
                                                                item_offset=end) if end < len(text) else None)},
                     'next': after(index + 1) if end == len(text) else None, 'meaning': SUBJECT_PAGE_MEANING})
    end = min(len(text), start + line)
    page = build(end)
    while end - start > 1 and not fits(page):   # every page advances by at least one character, never an empty NEXT
        end = start + max(1, (end - start) * 3 // 4)
        page = build(end)
    delivery.record_projection('subject', {'section': base['section'], 'offset': index, 'item_offset': start, 'item_end': end})
    return page


def completion_line() -> int:
    """The line a WHOLE completion response fits: the shared delivery plan's owner line (writing.delivery owner_line, the
    declared Work continuity bound minus the exact native receipts, envelope and late forms that plan reserves), else, for
    the HTTP and direct readers that add nothing around the owner result, the same navigation line (nav.CAP). A completion
    beyond it is an exact bounded projection, never cut or silently dropped. No reserve is guessed here."""
    from laplace.work import project_work_navigation as nav
    from laplace.writing import delivery
    line = delivery.owner_line()
    return nav.CAP if line is None else line


def _completion_bytes(value) -> int:
    """The largest encoding any door emits for value (development_source._encoded: native text, escaped and UTF-8 JSON)."""
    from laplace.work import development_source as D
    return D._encoded(value)


def _bounded_completion(response) -> dict:
    """dd039/b02: four valid long multibyte path-form proofs exceeded the completion line on READY and CONTINUED. Level 1
    names each duplicated proof reference once, at its proof row. Level 2 reads each long proof through its exact Artifact
    id and pin instead of repeating its path. Every slot, proof identity, scope and pin stays; a short response is
    unchanged; if even level 2 cannot fit, the read refuses honestly rather than drop a proof."""
    limit = completion_line()
    if _completion_bytes(response) <= limit:
        return response
    out = copy.deepcopy(response)
    ready = out.get('readiness') or {}
    for slot in ready.get('slots') or ():
        if 'reference' in slot:
            slot.pop('reference'); slot['reference_at'] = 'proofs[slot_id=%s].reference' % slot.get('id')
    for item in (ready.get('continued') or {}).get('proofs') or ():
        if 'reference' in item:
            item.pop('reference'); item['reference_at'] = 'proofs[slot_id=%s].reference' % item.get('slot_id')
    for row in out.get('proofs') or ():
        reference = row.get('reference') or {}
        if reference.get('path') is not None and reference.get('path') == row.get('path'):
            row['reference'] = {**{key: value for key, value in reference.items() if key != 'path'}, 'path_at': 'path'}
    projection = {'state': 'BOUNDED', 'level': 1, 'limit_bytes': limit,
                  'says': 'Each duplicated proof reference is named once, at its proof row; every slot, proof identity, scope and pin is kept.'}
    out['projection'] = projection
    if _completion_bytes(out) <= limit:
        return out
    for row in out.get('proofs') or ():
        if row.get('artifact_id') and row.get('path') is not None:
            row['path_chars'] = len(row.pop('path'))
            row['reference'] = {key: value for key, value in (row.get('reference') or {}).items() if key != 'path_at'}
            row['read'] = {'operation': 'read_artifact', 'payload': {'id': row['artifact_id'], 'offset': 0, 'limit': 16000,
                           'expected_sha256': 'sha256:' + str(row.get('observed_sha256') or '').removeprefix('sha256:')}}
    projection.update(level=2, says='Each long proof path is read through its exact Artifact id and pin (its read); identity, scope and pin stay here.')
    if _completion_bytes(out) <= limit:
        return out
    raise ValueError('This completion read cannot fit the %d-byte delivery line without dropping a proof; read each proof Artifact directly.'
                     % limit)


def read(root, scope, project, work_id, request, *, mode='human', read_context=None) -> dict:
    """The Work view ``continuity`` (see module text): actual Scope first, then one selected Work."""
    from laplace.work.owner_discovery import Scope
    if not isinstance(scope, Scope) or not scope.admits(project):
        raise ValueError('Continuity is outside the actual caller scope.')
    _validate(contract(), request, 'Continuity request')
    from laplace.work import development_source as D, project_work as W, project_work_views as V, work_delivery as WD
    from laplace.writing import source_execution as X
    context = {} if read_context is None else read_context
    snapshot = V.read_snapshot(project, W._root(root), read_context=context)
    tasks, by_id = snapshot['raw'], snapshot['by_id']
    task, row = tasks.get(work_id), by_id.get(work_id)
    if task is None or row is None:
        raise ValueError('Exact Work identity is unavailable in this namespace.')
    subject = _subject(project, task, tasks)
    part = request.get('part', 'summary')
    if part == 'preflight':
        from laplace.work import project_work_review as R
        return {'schema_version': SCHEMA, 'part': part, 'subject': subject, **R.preflight(project, request['payload'], root, tasks=tasks)}
    if part == 'subject':
        # the page is fitted as this WHOLE composed response, not as its items alone
        return subject_page(project, task, request['payload'], wrap=lambda page: {'schema_version': SCHEMA, 'part': part, 'subject': subject, **page})
    if part == 'completion':
        intent = _intent(task, request['intent_id'])
        if intent is None:
            raise ValueError('This completion intent is not recorded on this Work.')
        ready = readiness(root, project, tasks, task, intent, read_context=context)
        return _bounded_completion({'schema_version': SCHEMA, 'part': part, 'subject': subject, 'intent': public_intent(intent), 'readiness': _public_ready(ready),
                'proofs': [public_proof(item) for _slot, item in sorted(_fills(task, intent['id']).items())],
                'next': _intent_next(project, intent, ready, mode) or _held_next(project, task, ready),
                'execution': {'account': copy.deepcopy(ready.get('account')), 'observed_at': _now(),
                              'qualification': 'Live account observation; it is not part of the readiness basis beyond its state and capacity.'}})
    intents = _rows(task, INTENT)[::-1]
    judged = [(intent, readiness(root, project, tasks, task, intent, read_context=context)) for intent in intents[:INTENT_PAGE]]
    events, events_total = _events(task)
    development = task.get('development') or ()
    effects = D._latest_per_id(D.rows(task, 'effect'))
    checks = D.rows(task, 'check')
    basis = {'work_revision': subject['work_revision'], 'scope_revision': subject['scope_revision'], 'dependency_revision': row.get('dependency_revision'),
             'development_cut': D.cut(task, root) if development else None,
             'delivery_cut': WD.cut(task, root, read_context=context) if task.get('deliveries') else None}
    token = _digest({'basis': basis, 'intents': [(intent['id'], ready['state'], ready['basis']) for intent, ready in judged],
                     'events': [(event['id'], event['state']) for event in events]})
    if request.get('as_of') and request['as_of'] != token:
        conflict = W.WorkConflict('Continuity changed since it was read; old observations were not mixed.', project, work_id,
                                  expected=request['as_of'], observed=token, field='as_of')
        conflict.details['next_reads'] = [handle(project, work_id, {'part': 'summary'})]
        raise conflict
    accounts, seen = [], set()
    for intent, _ready in judged:
        attachment = (intent.get('origin') or {}).get('source_execution')
        if attachment and attachment.get('commission_id') not in seen:
            seen.add(attachment['commission_id'])
            accounts.append(X.status(root, attachment))
    for grant in D._latest_per_id(D.rows(task, 'grant')):
        if len(accounts) >= INTENT_PAGE or not grant.get('native_allowance'):
            continue
        attachment = X.descriptor(project, grant['work_id'], grant['id'], grant['parent_session_id'], grant['native_allowance'])
        if attachment['commission_id'] not in seen:
            seen.add(attachment['commission_id'])
            accounts.append(X.status(root, attachment))
    review = row.get('review') or {}
    from laplace.work.project_work_views import handle as view
    return {'schema_version': SCHEMA, 'part': 'summary', 'subject': subject, 'title': task.get('title'), 'goal': task.get('goal'),
            'standing': {key: copy.deepcopy(row.get(key)) for key in ('status', 'recorded_status', 'lifecycle', 'readiness', 'current_acceptance')},
            'basis': {**basis, 'token': token},
            'production': {'grants': len(D._latest_per_id(D.rows(task, 'grant'))), 'candidates': len(D.rows(task, 'candidate')),
                           'effects': {'total': len(effects), 'committed': sum(item.get('state') == 'COMMITTED' for item in effects)},
                           'checks': {'total': len(checks), 'states': dict(sorted(collections_count(item.get('state') for item in checks).items())),
                                      # recorded stage disposition per check; a check with no recorded outcome is UNKNOWN
                                      'cleanup': dict(sorted(collections_count((item.get('stage_cleanup') or {}).get('state') or 'UNKNOWN'
                                                                               for item in checks).items()))},
                           'read': {'operation': 'development_source', 'payload': {'action': 'status', 'work_id': task['id']}}},
            'completion': {'total': len(intents), 'intents': [{**public_intent(intent), 'readiness': _public_ready(ready)} for intent, ready in judged]},
            'review': {'obligations': [{key: item.get(key) for key in ('id', 'status', 'currentness', 'satisfied', 'review_id', 'findings', 'review_read')}
                                       for item in review.get('obligations') or ()],
                       'remaining': len(review.get('remaining') or ()), 'next': (review.get('next') or {}).get('kind'),
                       'read': view(project, {'view': 'review', 'id': task['id']}) if task.get('review_obligations') else None},
            'closeout': closeout(task, row),
            'delivery': {'total': events_total, 'events': events},
            'execution': {'accounts': accounts, 'observed_at': _now(),
                          'qualification': 'Live account observation outside the basis token; recorded admissions and current host execution are separate.'},
            'next': _next(project, task, row, judged, events, mode),
            'reads': {'detail': view(project, {'view': 'detail', 'id': task['id']}),
                      'development': {'operation': 'development_source', 'payload': {'action': 'status', 'work_id': task['id']}},
                      'delivery': {'operation': 'work_delivery', 'payload': {'action': 'status', 'work_id': task['id']}}},
            'coverage': {'intents_selected': len(judged), 'intents_omitted': max(0, len(intents) - len(judged)),
                         'events_selected': len(events), 'events_omitted': max(0, events_total - len(events)),
                         'meaning': 'Selected owner metadata only; no message bodies, transcripts or unrelated Work were read.'},
            'mode': mode}


def closeout(task, row) -> dict:
    """The durable closeout header from existing records only: the latest handoff, the recorded review verdicts, the latest
    same-Work synthesis and the Work standing. Recorded verdicts stay history beside current standing. Adoption is the
    Work's development lane adoption as its lane row records it (development_adoption.closeout), else NOT_RECORDED. This
    owner records no live service or publication, so those are NOT_RECORDED here, never inferred from a verdict, a
    retained version or a provider FINISHED. Observing it executes no cleanup."""
    from laplace.work import development_adoption
    phases = task.get('phases') or ()
    pick = lambda kind: [item for item in phases if item.get('phase') == kind]
    handoffs, reviews, syntheses = pick('handoff'), pick('review'), pick('synthesis')
    # The next/held meaning is the review owner's CURRENT decision (project_work_review.facet on the resolved row), never
    # inferred from which phases exist: a HOLD, or a new handoff after an old completed cycle, stays visibly unresolved.
    review = row.get('review') or {}
    obligations = review.get('obligations') or ()
    # A Work with no review obligations has no review cycle to continue: NOT_REQUIRED, never an invented handoff.
    required = 'REQUIRED' if obligations else 'NOT_REQUIRED'
    nxt = (review.get('next') or {}).get('kind') if obligations else None
    return {'handoff': handoffs[-1]['id'] if handoffs else None, 'handoffs_total': len(handoffs),
            'reviews': [{key: item.get(key) for key in ('id', 'verdict', 'obligation_id', 'handoff_id')} for item in reviews[-8:]],
            'reviews_total': len(reviews), 'synthesis': syntheses[-1]['id'] if syntheses else None, 'syntheses_total': len(syntheses),
            'work': {key: copy.deepcopy(row.get(key)) for key in ('status', 'recorded_status')},
            'current_acceptance': (row.get('current_acceptance') or {}).get('status'),
            'adoption': development_adoption.closeout(task), 'live': 'NOT_RECORDED', 'publication': 'NOT_RECORDED', 'missing_next': nxt, 'review_required': required,
            'remaining': list(review.get('remaining') or ())[:24],
            'held': [item.get('id') for item in obligations if item.get('status') == 'HOLD'][:24],
            'latest_synthesis_covers_latest_handoff': bool(handoffs and syntheses and handoffs[-1]['id'] in (syntheses[-1].get('consumes') or ())),
            'meaning': ('Recorded handoff/review/synthesis identities and verdicts are history; current applicability is the review '
                        'facet and Work standing. Adoption is the lane row\'s adoption (development_adoption); live service and publication '
                        'are owned elsewhere and are not inferred.')}


def collections_count(values) -> dict:
    out = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return out
