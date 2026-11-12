"""WORK DELIVERY (in-harness join; causal correction J-R4/J-R5, 2026-10-20): a handed-off Work obligation reaches its
independent recipient as ONE event-wide admitted request, and the recipient's terminal result returns to the parent
that submitted it through an authorised, bounded, app-owned continuation.

RECIPIENT BINDING (project-work-phase, kind recipient-binding): author-approved for the review role of one Work with a
finite lifetime: an app-owned reviewer (provider, model, effort; the app opens its review session) or an external
participant (author door only; a native producer cannot mint an external identity). A review-role turn binds nothing.

DELIVERY EVENT: one immutable identity (handoff phase id, binding id and revision, obligation, the Work's material
scope revision, the handoff's content pin). Its rows:
  SUBMITTED   the intent, durable before any transport, with the submitting identity and, for a native author turn,
              the parent coordinates the result is authorised to return to (continuation)
  RESERVED    the event-wide reservation: under the event's own lock the consumption is REVALIDATED (binding approved
              and unexpired, Work scope unchanged, handoff pins still current, Work standing not cancelled, attempts
              and deadline left) and ONE review session is reserved for the event, before transport; a concurrent
              or repeated caller waits on the lock and then finds the reservation, never a second session
  DELIVERED   the app-owned transport admitted the request (request_id = event id)
  ADMITTED    the exact admitted coordinates are RETAINED (session, turn, request id): admission evidence. The
              recipient's acknowledgement is a separate fact (recipient_ack UNKNOWN until its terminal result)
  RESULT      the admitted turn's terminal result reached the ledger through the real turn path
              (turn_execution._bank_reply -> settle_turn); recipient_ack becomes TERMINAL
  STALE       revalidation failed: explicit terminal, with the reason; a new handoff or binding is a new event
  UNSUPPORTED an external binding without a real attachment adapter: explicit pending, nothing cloned
  UNCONFIRMED attempts or deadline exhausted without admitted coordinates: explicit, recoverable by hand
Qualified Source handoffs opt in through their typed source_basis: it is bound in the content pin and retained on
this event. Consumption validates only this obligation's Source pins and its original evaluator binding through
the Source owner; canonical-root twins are never substituted. Ordinary handoffs keep their original pin identity.
The reviewer reads the configured repository at the retained full pins; terminal facts and parent/recovery routes
keep the same event and Source identity without turning recorded evidence into a renewed write grant.

Recovery: the admission request id IS the event id, so a lost acknowledgement (a crash after admission) recovers the
SAME turn through turn_admission.reused_turn; a reservation without a turn continues with its reserved session.

CONTINUATION (J-R4; residual closure J-R4-R1, Root decision PARENT_RETURN): when the admitted turn ends, settle_turn
appends RESULT and, when the intent carries parent coordinates, records ONE bounded session-request Work row
addressed to that parent session. With an explicitly approved route (`parent_return` on submit: admit_idle, finite
max_attempts and max_depth) the owner then ADMITS at most one authorised continuation turn in the SAME idle parent
session through the existing turn owner (turn_admission.start_turn with the stable request id CONT-<event>): no new
session, no model poll, no external send. While the parent is active the event stays PENDING_PARENT (notification:
the pending fact is on the event, the queued row on the Work) and the parent's own terminal path
(turn_execution._finish -> admit_pending_continuations) admits it once the parent is idle. Admission refuses and
retains the pending event when parent authority, quiescence, scope currentness, cancellation, depth or attempts
prevent it; a human-door submission has no parent and stays inspect-only. The cost profile of the continuation is
the parent session's own (provider, model, effort), recorded on the CONTINUED row.

PREPARED COMPLETION (Eigen continuity, Root e716/a6d0): `continue` (project_work_continuity.continue_intent) submits the
existing event for a handoff its original Source producer armed before it ended. submit_prepared is the one narrow
trusted-origin path: actor, origin and parent coordinates are the producer's recorded ones, the commission is resolved
again from the producer turn (source_execution.prepared_inheritance) and checked by the ordinary _source_origin, and the
actual dispatcher is retained separately and grants nothing. Ordinary submit still refuses a human Source delivery. The
reviewer receives the complete owner record template (project_work_review.review_template) with its closed limits and a
pure preflight read; the verdict is never pre-filled.

ACCEPTANCE is never decided here: the facet projects the Work's canonical review obligation status from
project_work_review.facet (status, currentness, independence, satisfied) and says whether that review was recorded by
this delivery's admitted turn. There is no second ACCEPT rule.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import time
from pathlib import Path
from typing import Any

RECORD = 'project-work-phase'
BINDING = 'recipient-binding'
EVENT = 'work-delivery'
KINDS = ('app-owned', 'external')
MAX_ATTEMPTS = 3
MAX_DEADLINE_S = 24 * 3600
MAX_BINDING_LIFETIME_S = 30 * 24 * 3600
DEFAULT_BINDING_LIFETIME_S = 7 * 24 * 3600
DEFAULT_BINDING_EFFORT = 'medium'
TERMINAL = ('UNSUPPORTED', 'UNCONFIRMED', 'ADMITTED', 'RESULT', 'STALE', 'PENDING_PARENT', 'CONTINUED', 'PARENT_REFUSED')
SETTLED = ('RESULT', 'PENDING_PARENT', 'CONTINUED', 'PARENT_REFUSED')
MAX_RETURN_ATTEMPTS = 2
MAX_RETURN_DEPTH = 2
MAX_RETURN_DEFERRALS = 3
PAGE = 8
MAX_CONTINUATIONS = 5
CONTINUATION_KIND = 'work-delivery'


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _digest(value: Any) -> str:
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def contract() -> dict:
    string = {'type': 'string'}
    ident = {'type': 'string', 'minLength': 8, 'maxLength': 96}
    from laplace.work import feedback_route, review_setup
    from laplace.writing import workflow_progression
    from laplace.work import project_work_continuity
    return {'schema_version': 'laplace.work-delivery-contract/2', 'type': 'object', 'required': ['action'], 'additionalProperties': False,
            'properties': {'project': string, 'action': {'enum': ['bind', 'submit', 'recover', 'status', 'continue',*feedback_route.ACTIONS,*review_setup.ACTIONS,*workflow_progression.ACTIONS]},
                           'request_id':string,'origin':{'type':'object'},'policy':feedback_route.policy_schema(),
                           'request_kind':{'enum':['route','policy']},'submission':{'type':'object'},
                           'expected_binding_revision':string,'intended_binding':{'type':'object'},
                           'policy_id':string,'expected_policy_revision':string,'recipients':{'type':'array','items':{'type':'object'}},'route_id':string,
                           'work_id': string, 'expected_work_revision': string, 'kind': {'enum': list(KINDS)}, 'role': {'enum': ['review']},
                           'effect': {'enum': ['proposal-writer', 'independent-review', 'research-producer']},
                           'producer_id': string, 'producer_mode': {'enum': ['smoke', 'full']}, 'producer_args': {'type': 'object'},
                           'feedback_argument':string,
                           **workflow_progression.contract_fields(),
                           'provider': {'enum': ['codex', 'claude']}, 'model': string, 'effort': string, 'label': {'type': 'string', 'maxLength': 160},
                           'lifetime_s': {'type': 'integer', 'minimum': 60, 'maximum': MAX_BINDING_LIFETIME_S},
                           'external': {'type': 'object', 'additionalProperties': False, 'properties': {
                               'actor': {'type': 'string', 'maxLength': 160}, 'evidence': string, 'profile': string, 'scope': string}},
                           'handoff_id': string, 'obligation_id': string, 'recipient_binding_id': ident,
                           'deadline_s': {'type': 'integer', 'minimum': 60, 'maximum': MAX_DEADLINE_S},
                           'max_attempts': {'type': 'integer', 'minimum': 1, 'maximum': MAX_ATTEMPTS},
                           'parent_return': {'type': 'object', 'additionalProperties': False, 'properties': {
                               'admit_idle': {'type': 'boolean'}, 'max_attempts': {'type': 'integer', 'minimum': 1, 'maximum': MAX_RETURN_ATTEMPTS},
                               'max_depth': {'type': 'integer', 'minimum': 1, 'maximum': MAX_RETURN_DEPTH}}},
                           **project_work_continuity.delivery_fields(),
                           'event_id': ident, 'cut': string, 'offset': {'type': 'integer', 'minimum': 0}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 64}},
            'description': 'bind (work_id, expected_work_revision, kind[, provider, model, effort, label, lifetime_s, external]); '
                           'submit (work_id, expected_work_revision, handoff_id, obligation_id, recipient_binding_id[, deadline_s, max_attempts, '
                           'parent_return {admit_idle, max_attempts, max_depth}: once-only return into the idle parent session]); '
                           'recover (event_id); status (event_id | work_id[, offset, limit, cut]); '
                           'review-setup (work_id[, offset, limit, cut, intended_binding]) reads complete definitions and latest approval pages; '
                           'renew (work_id, recipient_binding_id, expected_work_revision, expected_binding_revision, request_id, lifetime_s) is author-only; '
                           'renew-request (work_id, request_id) reads the original renewal outcome; '
                           'route-status (work_id, request_id[, request_kind, submission]) purely compares one exact ORIGINAL route/policy request; '
                           'request-settle (work_id, request_kind, request_id, submission) is the human-only terminal of that exact unadmitted request; '
                           'continue (intent_id, expected_basis) records the handoff and this delivery once from a READY prepared Source completion '
                           '(human door or author turn; original producer provenance, dispatcher recorded separately).'}


REQUIRED = {'bind': ('work_id', 'expected_work_revision', 'kind'), 'submit': ('work_id', 'expected_work_revision', 'handoff_id', 'obligation_id', 'recipient_binding_id'),
            'recover': ('event_id',), 'status': (), 'continue': ('intent_id', 'expected_basis')}


def _require(payload: dict, action: str) -> None:
    missing = [key for key in REQUIRED[action] if payload.get(key) in (None, '', [], {})]
    if missing:
        raise ValueError('work_delivery %s requires %s.' % (action, ', '.join(missing)))


# ------------------------------------------------------------------------------------------------ ledger views

def _rows(task: dict, kind: str) -> list[dict]:
    return [row for row in task.get('deliveries') or () if row.get('kind') == kind]


def _latest(task: dict, kind: str, ident: str) -> dict | None:
    found = None
    for row in _rows(task, kind):
        if row.get('id') == ident:
            found = row
    return found


def _history(task: dict, event_id: str) -> list[dict]:
    return [row for row in _rows(task, EVENT) if row.get('id') == event_id]


def _acting(root, project, door) -> dict:
    from laplace.work import development_source
    return development_source._acting(root, project, door)


def _actor(root, project, payload, door) -> dict:
    from laplace.work import project_work_review
    return project_work_review._actor(root, project, {k: v for k, v in payload.items() if k == 'actor'} | {'phase': 'handoff'}, door)


def _read_tasks(root,project,read_context=None):
    """Private pure-read frame; mutation/admission callers pass no frame."""
    from laplace.work import project_work
    if read_context is None:return project_work._tasks(project,root)
    key=('work_delivery.tasks',str(Path(root).resolve()),project)
    if key not in read_context:
        snapshot=getattr(project_work,'read_snapshot',None)
        read_context[key]=(snapshot(project,root,read_context=read_context,resolve=False)['raw']
            if callable(snapshot) else project_work._tasks(project,root))
    return read_context[key]


def _read_fold(root,read_context=None):
    from laplace.writing import records
    if read_context is None:return records.fold_records(root)
    key=('work_delivery.writing_fold',str(Path(root).resolve()))
    if key not in read_context:read_context[key]=records.fold_records(root)
    return read_context[key]


def _task_for(root, project, work_id, *, read_context=None):
    tasks = _read_tasks(root,project,read_context)
    task = tasks.get(work_id)
    if task is None:
        raise ValueError('work_delivery names an existing Work id of this project.')
    return tasks, task


def _task_of_event(root, project, event_id, *, read_context=None):
    for task in _read_tasks(root,project,read_context).values():
        if _history(task, event_id):
            return task
    raise ValueError('work_delivery: unknown event %s for this project.' % event_id)


def _event_lock(root: Path, event_id: str):
    """The event-wide reservation lock: one consumer of one event at a time, across threads and processes."""
    from filelock import FileLock
    path = Path(root) / 'contract' / 'work_delivery' / (event_id + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(path), timeout=30)


# ------------------------------------------------------------------------------------------------ binding

def binding_content(work_id, payload):
    """Existing content identity, shared with pure intended-settings inspection."""
    result = {'work_id': work_id, 'role': 'review', 'recipient_kind': payload['kind'],
        'provider': payload.get('provider'), 'model': payload.get('model'),
        'effort': payload.get('effort') or DEFAULT_BINDING_EFFORT,
        'label': payload.get('label') or '', 'external': payload.get('external') or None}
    if payload.get('effect'):
        result.update(effect=payload['effect'], role='review' if payload['effect']=='independent-review' else payload['effect'])
        if payload['effect']=='research-producer':
            result.update({key:copy.deepcopy(payload.get(key)) for key in ('producer_id','producer_mode','producer_args','feedback_argument')})
    return result


def latest_bindings(task):
    """One latest canonical row per RB identity; history remains attached."""
    return {row['id']: row for row in _rows(task, BINDING)}


def bind(root: Path, project: str, payload: dict, door: dict) -> dict:
    from laplace.work import project_work
    _require(payload, 'bind')
    acting = _acting(root, project, door)
    if acting.get('role') == 'review':
        raise ValueError('work_delivery: a review-role turn cannot bind a recipient.')
    if payload['kind'] == 'external' and acting['kind'] != 'human':
        raise ValueError('work_delivery: an external recipient is author-approved only; a native turn cannot mint an external identity.')
    effect = payload.get('effect')
    if effect and (acting['kind'] != 'human' or payload['kind'] != 'app-owned'):
        raise ValueError('Effect-specific execution bindings require explicit human approval of this exact Work.')
    if effect:
        raise ValueError('Use workflow-bind for exact effect settings/basis and stable approval request recovery.')
    if payload['kind'] == 'app-owned' and effect != 'research-producer' and not (payload.get('provider') and payload.get('model')):
        raise ValueError('work_delivery: an app-owned recipient names its provider and model.')
    lifetime = int(payload.get('lifetime_s') or DEFAULT_BINDING_LIFETIME_S)
    with project_work.dispatch_lock(root):
        tasks, task = _task_for(root, project, payload['work_id'])
        if payload['expected_work_revision'] != project_work._task_revision(task):
            raise project_work.WorkConflict('Read the exact Work before binding its recipient.', project, task['id'],
                                            expected=payload['expected_work_revision'], observed=project_work._task_revision(task), field='expected_work_revision')
        content = binding_content(task['id'], payload)
        revision = _digest(content)
        row = {'record': RECORD, 'kind': BINDING, 'id': 'RB-' + revision[7:31], 'revision': revision, 'project': project, 'state': 'APPROVED',
               **content, 'ts': _now(), 'expires_at': dt.datetime.fromtimestamp(time.time() + lifetime, dt.timezone.utc).isoformat(),
               'actor': _actor(root, project, payload, door), 'approved_by': acting['kind'],
               'attachment': 'app-owned review session' if payload['kind'] == 'app-owned' else 'UNSUPPORTED: no authenticated external attachment adapter on this host'}
        existing = _latest(task, BINDING, row['id'])
        if existing is None:
            project_work._append(root, row)
        else:
            row = existing
    return {'ok': True, 'binding': _public_binding(row)}


def _public_binding(row: dict) -> dict:
    # the ledger row's `kind` is its record kind (recipient-binding); the recipient's kind is `recipient_kind`, public as `kind`
    # Public projections must not alias the retained Work fold's nested approval intent.
    return copy.deepcopy({**{key: row.get(key) for key in ('id', 'revision', 'work_id', 'role', 'provider', 'model', 'effort', 'label', 'state', 'attachment', 'approved_by', 'expires_at', 'previous_revision', 'approval_generation', 'approval')},
            **{key:row[key] for key in ('effect','producer_id','producer_mode','producer_args','producer_basis','producer_timeout_seconds','feedback_argument') if key in row},
            'kind': row.get('recipient_kind')})


def _binding_problem(task: dict, binding_id: str, revision: str | None = None) -> str | None:
    binding = _latest(task, BINDING, binding_id)
    if binding is None or binding.get('state') != 'APPROVED':
        return 'the recipient binding is not an approved binding of this Work'
    if revision and binding.get('revision') != revision:
        return 'the recipient binding changed since submission'
    if binding.get('expires_at') and dt.datetime.fromisoformat(binding['expires_at']) <= dt.datetime.now(dt.timezone.utc):
        return 'the recipient binding expired at ' + binding['expires_at']
    return None


# ------------------------------------------------------------------------------------------------ submission

def _content_pin(handoff: dict) -> str:
    value={'pins': handoff.get('pins') or {}, 'object': handoff.get('object') or {}}
    if 'source_basis' in handoff:
        value['source_basis'] = handoff['source_basis']
    if 'source_review_plan' in handoff:
        value['source_review_plan_id'] = handoff['source_review_plan']['plan_id']
        if 'review_subject' in handoff['source_review_plan']:
            # A cumulative plan also binds its whole subject and the bounded brief the reviewer is shown.
            value['review_subject_id'] = handoff['source_review_plan']['review_subject']['subject_id']
            value['handoff_brief'] = _digest({'summary': handoff.get('summary'), 'evidence': handoff.get('evidence')})
    if handoff.get('feedback_origin'):
        value.update(feedback_origin=handoff['feedback_origin'],feedback_route={
            key:handoff['feedback_route'][key] for key in ('edge_id','generation')})
    return _digest(value)


def submit(root: Path, project: str, payload: dict, door: dict) -> dict:
    from laplace.work import project_work
    _require(payload, 'submit')
    acting = _acting(root, project, door)
    if acting.get('role') == 'review':
        raise ValueError('work_delivery: a review-role turn cannot submit a delivery.')
    with project_work.dispatch_lock(root):
        tasks, task = _task_for(root, project, payload['work_id'])
        if payload['expected_work_revision'] != project_work._task_revision(task):
            raise project_work.WorkConflict('Read the exact Work before submitting its delivery.', project, task['id'],
                                            expected=payload['expected_work_revision'], observed=project_work._task_revision(task), field='expected_work_revision')
        handoff = next((row for row in task.get('phases') or () if row.get('id') == payload['handoff_id'] and row.get('phase') == 'handoff'), None)
        if handoff is None:
            raise ValueError('work_delivery: submit names a handoff phase of this Work.')
        if payload['obligation_id'] not in (handoff.get('obligations') or []):
            raise ValueError('work_delivery: the handoff does not cover obligation %s.' % payload['obligation_id'])
        problem = _binding_problem(task, payload['recipient_binding_id'])
        if problem:
            raise ValueError('work_delivery: name an approved recipient binding of this Work (%s).' % problem)
        binding = _latest(task, BINDING, payload['recipient_binding_id'])
        basis, issue = project_work._work_basis(tasks, task['id'])
        if issue or not basis.get('scope_revision'):
            raise ValueError('work_delivery: the Work has no current material scope: ' + str(issue))
        identity = {'handoff_id': handoff['id'], 'binding_id': binding['id'], 'binding_revision': binding['revision'],
                    'obligation_id': payload['obligation_id'], 'work_scope_revision': basis['scope_revision'], 'content_pin': _content_pin(handoff)}
        event_id = 'WD-' + _digest(identity)[7:31]
        if _history(task, event_id):
            original=_history(task,event_id)[0]
            if binding.get('effect') in {'proposal-writer','research-producer'} and 'runtime_seconds' in payload:
                if payload['runtime_seconds']!=original.get('effect_runtime_seconds'):
                    raise ValueError('This exact delivery already retains another running ceiling; no requested limit was silently dropped.')
            return {'ok': True, 'reused': True, 'event': _facet_event(root, project, task, event_id)}
        from laplace.work import feedback_route
        source_attachment = _source_origin(root, project, acting, handoff.get('source_basis'), _public_binding(binding))
        execution=feedback_route.event_context(root,project,task,handoff)
        effect_selection = None
        if binding.get('effect') in {'proposal-writer','research-producer'}:
            runtime=(execution or {}).get('runtime_seconds',payload.get('runtime_seconds'))
            if type(runtime) is not int or not 1<=runtime<=3600:raise ValueError('Effect recipient requires an explicit supported finite runtime_seconds.')
        if binding.get('effect') == 'proposal-writer':
            if handoff.get('feedback_origin'):
                origin=feedback_route._origin(root,project,handoff['feedback_origin'],current=True)
                effect_selection={'files':[origin['source_basis']['file']]}
            elif (task.get('anchor') or {}).get('file'):effect_selection={'files':[task['anchor']['file']]}
            elif task.get('section_ids'):effect_selection={'section_ids':task['section_ids']}
            else:raise ValueError('A proposal-writer effect requires an exact anchored source or declared section scope.')
        deadline = dt.datetime.fromtimestamp(time.time() + int(payload.get('deadline_s') or 3600), dt.timezone.utc).isoformat()
        continuation = _continuation_intent(root, project, acting, payload.get('parent_return'))
        intent = {'record': RECORD, 'kind': EVENT, 'id': event_id, 'work_id': task['id'], 'project': project, 'state': 'SUBMITTED', **identity,
                  'attempts': 0, 'max_attempts': int(payload.get('max_attempts') or MAX_ATTEMPTS), 'deadline_at': deadline, 'ts': _now(),
                  'actor': _actor(root, project, payload, door), 'recipient': _public_binding(binding), 'continuation': continuation,
                  **({'feedback_execution':execution} if execution else {}),
                  **({'effect_selection':effect_selection} if effect_selection else {}),
                  **({'effect_runtime_seconds':runtime} if binding.get('effect') in {'proposal-writer','research-producer'} else {}),
                  **({'source_execution': source_attachment} if source_attachment else {}),
                  **({'source_basis': copy.deepcopy(handoff['source_basis'])} if 'source_basis' in handoff else {}),
                  **({'source_review_plan': copy.deepcopy(handoff['source_review_plan'])} if 'source_review_plan' in handoff else {})}
        project_work._append(root, intent)   # the intent is durable before any transport is touched
    _deliver(root, project, event_id)
    task = _task_of_event(root, project, event_id)
    return {'ok': True, 'event': _facet_event(root, project, task, event_id)}


def _continuation_intent(root, project, acting, route) -> dict | None:
    """The parent coordinates a native submission's result returns to, with the approved route and this submission's
    continuation depth (a delivery submitted from a continuation turn is one level deeper)."""
    if acting['kind'] != 'native':
        return None   # a human-door submission has no parent session: inspect-only, by Root's decision
    from laplace.writing import records as writing_records
    turn = writing_records.fold_records(root)['turns'].get(acting['turn_id']) or {}
    depth = 0
    if str(turn.get('request_id') or '').startswith('CONT-'):
        prior = _event_anywhere(root, project, turn['request_id'][5:])
        depth = int(((prior or {}).get('continuation') or {}).get('depth') or 0) + 1
    approved = {'admit_idle': bool(route.get('admit_idle')), 'max_attempts': int(route.get('max_attempts') or 1), 'max_depth': int(route.get('max_depth') or 1)} if route else None
    return {'parent_session_id': acting['session_id'], 'parent_turn_id': acting['turn_id'], 'depth': depth, 'route': approved}


def _record_line(task, intent) -> str:
    """The complete owner-issued work_review template with its closed limits and pure preflight read, never a verdict."""
    from laplace.work import project_work_review
    tail = ' This request is identified by request_id %s and is never repeated as a new turn.' % intent['id']
    try:
        template = project_work_review.review_template(task, intent['handoff_id'], intent['obligation_id'], 'REVIEW-' + intent['id'])
    except ValueError as error:
        # Ordinary handoffs keep their admission; the reason is stated rather than silently degraded. The prepared
        # path refuses before any effect instead (project_work_continuity._require_template).
        return ('Record your verdict with work_review {phase: review, handoff_id, obligation_id, verdict} under your own admitted identity. '
                'The complete owner template is unavailable for this handoff (%s); read the handoff and the work_review help before '
                'recording.' % str(error)[:200] + tail)
    preflight = {key: template['preflight'][key] for key in ('operation', 'payload', 'fill') if key in template['preflight']}
    return ('Record your verdict with work_review under your own admitted identity, using this complete owner-issued template. '
            'Author verdict (ACCEPT, HOLD or REJECT), summary and findings yourself; keep every other field exactly: '
            + json.dumps(template['payload'], sort_keys=True) + '. Closed limits: ' + json.dumps(template['limits'], sort_keys=True)
            + '. Pure preflight that records nothing: ' + json.dumps(preflight, sort_keys=True) + '.' + tail)


def prepared_event(task, intent, handoff, scope_revision) -> dict:
    """The pure identity and composition of the ONE prepared delivery event of a completion intent and its handoff:
    submit_prepared appends exactly this, and project_work_continuity.request_fit composes the reviewer request from it
    before any append. Records nothing."""
    binding = _latest(task, BINDING, intent['policy']['recipient_binding_id'])
    identity = {'handoff_id': handoff['id'], 'binding_id': binding['id'], 'binding_revision': binding['revision'],
                'obligation_id': intent['obligation_id'], 'work_scope_revision': scope_revision, 'content_pin': _content_pin(handoff)}
    return {'id': 'WD-' + _digest(identity)[7:31], 'identity': identity, 'recipient': _public_binding(binding),
            **identity, 'source_basis': copy.deepcopy(handoff['source_basis']),
            **({'source_review_plan': copy.deepcopy(handoff['source_review_plan'])} if 'source_review_plan' in handoff else {})}


def submit_prepared(root, project, task, intent, handoff, dispatcher, *, basis) -> str:
    """The ONE trusted-origin submission (project_work_continuity.continue_intent; the caller holds the Work lock).

    The event is the existing delivery event of a handoff the original Source producer armed: its actor, origin and
    parent coordinates are that producer's recorded ones, and its commission is resolved again from the producer turn
    (source_execution.prepared_inheritance) and checked by the ordinary _source_origin. The actual dispatcher is
    retained beside them and grants nothing. Returns the deterministic event id; an existing event is reused.
    """
    from laplace.work import project_work
    from laplace.writing import source_execution
    policy, origin = intent['policy'], intent['origin']
    problem = _binding_problem(task, policy['recipient_binding_id'], policy.get('recipient_binding_revision'))
    if problem:
        raise ValueError('work_delivery: the prepared recipient binding is unusable (%s).' % problem)
    current, issue = project_work._work_basis(project_work._tasks(project, root), task['id'])
    if issue or current.get('scope_revision') != intent['work']['scope_revision']:
        raise ValueError('work_delivery: the Work material scope changed since the completion was armed.')
    composed = prepared_event(task, intent, handoff, current['scope_revision'])
    identity, event_id = composed['identity'], composed['id']
    if _history(task, event_id):
        return event_id
    recipient = composed['recipient']
    continuation = copy.deepcopy(origin.get('continuation'))
    attached = source_execution.prepared_inheritance(root, project, origin, handoff['source_basis'], recipient)
    if _source_origin(root, project, origin['actor'], handoff['source_basis'], recipient, continuation=continuation) != attached:
        raise ValueError('work_delivery: the recorded producer origin and its commission disagree; nothing was submitted.')
    route = policy['return_policy']
    row = {'record': RECORD, 'kind': EVENT, 'id': event_id, 'work_id': task['id'], 'project': project, 'state': 'SUBMITTED', **identity,
           'attempts': 0, 'max_attempts': int(route['max_attempts']), 'ts': _now(),
           'deadline_at': dt.datetime.fromtimestamp(time.time() + int(route['review_deadline_s']), dt.timezone.utc).isoformat(),
           'actor': copy.deepcopy(origin['actor']), 'dispatcher': copy.deepcopy(dispatcher),
           'prepared_completion': {'intent_id': intent['id'], 'basis': basis},
           'recipient': recipient, 'continuation': continuation, 'source_execution': attached,
           'source_basis': copy.deepcopy(handoff['source_basis']),
           # a prepared cumulative handoff carries its armed plan/subject; the event retains it exactly as submit does
           **({'source_review_plan': copy.deepcopy(handoff['source_review_plan'])} if 'source_review_plan' in handoff else {})}
    project_work._append(root, row)   # durable before any transport, exactly like submit
    return event_id


def _event_anywhere(root, project, event_id) -> dict | None:
    from laplace.work import project_work
    for task in project_work._tasks(project, root).values():
        history = _history(task, event_id)
        if history:
            return history[0]
    return None



def _source_consumed_pins(task, intent, handoff):
    """The same per-obligation coverage as Work review; Source owns hashes/fences."""
    obligation = next((row for row in task.get('review_obligations') or [] if row['id'] == intent['obligation_id']), None)
    if obligation is None:
        raise ValueError('the submitted Source obligation is no longer declared')
    handed = handoff.get('pins') or {}
    required = set(obligation.get('inputs') or handed)
    missing = required - set(handed)
    if missing:
        raise ValueError('the source handoff does not cover the obligation inputs: ' + ', '.join(sorted(missing)[:4]))
    return {path: handed[path] for path in sorted(required)}


def _source_description(basis):
    return {key: basis[key] for key in ('repository', 'base', 'grant_id', 'candidate_id', 'effect_id')}


def native_initial_read(read: dict) -> dict:
    """One Source plan initial read as the native reviewer request carries it: the exact window and the native
    operation/payload that reads it. The plan's duplicate HTTP and human read carriers stay in the immutable plan (the
    exact qualified handoff read below); they are not repeated per read in the native message."""
    handle = read['read']
    return {'path': read['path'], 'offset': read['offset'], 'chars': read['chars'], 'stop_before_offset': read['stop_before_offset'],
            'operation': handle['operation'], 'payload': handle['payload']}


HANDOFF_SUMMARY_CHARS = 4000
HANDOFF_EVIDENCE_ROWS = 24


def _fit(rows, budget) -> list:
    """The longest prefix of rows whose JSON rendering fits budget bytes (F2)."""
    kept, used = [], 2
    for row in rows:
        size = len(json.dumps(row, sort_keys=True).encode('utf-8')) + 2
        if used + size > budget:
            break
        kept.append(row)
        used += size
    return kept


def _listing(label, rows, share, page, section) -> str:
    """One rendered list: every row, or (bounded, F2) the prefix that fits share bytes, its omitted count and the exact
    owner-issued continuation page at that offset. Omitted rows stay review scope; nothing is silently dropped."""
    if share is None:
        return label + ': ' + json.dumps(rows, sort_keys=True)
    shown = _fit(rows, share)
    text = '%s (bounded: showing %d of %d): %s' % (label, len(shown), len(rows), json.dumps(shown, sort_keys=True))
    if len(shown) < len(rows):
        text += ('. The other %d row(s) are omitted from this bounded request but remain review scope: read them in order with this exact '
                 'owner page, following each page\'s next: %s' % (len(rows) - len(shown), json.dumps(page(section, len(shown)), sort_keys=True)))
    return text


def _subject_page_read(task, intent, handoff, section, offset, path=None) -> dict:
    from laplace.work import project_work_continuity as C
    return C.subject_page_handle(task['project'], task['id'], handoff['id'], section, offset, path=path,
                                 obligation_id=intent['obligation_id'] if section in C._PROJECTED else None)


def _subject_lines(handoff: dict, subject: dict, page=None, budget=None) -> list:
    """The WHOLE cumulative review subject, its typed stage and the bounded handoff brief, rendered BEFORE any geometry.
    The Source owner derived the subject; this only presents it. Pins identify bytes and are never reads. With a budget
    (the bounded request, F2) each list is the prefix that fits its share plus its exact continuation page."""
    union, commission = subject['union'], subject['commission']
    lines = ['WHOLE REVIEW SUBJECT %s (cumulative; every path below is review scope whether or not this obligation consumes it): '
             '%d path(s) = %d changed by %d committed Source effect(s) across %d grant(s) of commission %s (original parent session %s) '
             '+ %d read-only carry member(s) outside those changes; base %s of %s. Pins identify bytes; they are not reads.'
             % (subject['subject_id'], union['paths_total'], union['commission_changed'], union['effects'], union['grants'],
                commission.get('commission_request_id') or '(none declared)', commission.get('original_parent_session_id'),
                union['carry_outside_changes'], subject['base'], subject['repository'])]
    prior = subject.get('prior_production')
    if prior:
        lines.append('Prior production explicitly selected into this subject (separately attributed commissions of this Work and original parent; '
                     'their own accounts, write authority and reviews stay separate): ' + json.dumps(
                         {'grants': [{key: row.get(key) for key in ('id', 'commission_request_id', 'parent_session_id')} for row in prior['grants']],
                          'effects': len(prior['effects'])}, sort_keys=True))
    base = subject.get('base_relation')
    if base:
        lines.append('Change provenance is judged against base %s (%s, tree %s). %s' % (
            base['commit'], 'declared accepted base' if base['declared'] else 'the grant base', base['tree'], base['meaning']))
    stage = subject.get('stage') or {}
    if 'id' in stage:
        lines.append('Acceptance stage %s. %s Judge NOW (pre-source review): %s. LATER typed obligations, neither satisfied nor waived here: %s.%s'
                     % (stage['id'], stage['meaning'], json.dumps(stage['pre_source_review'], ensure_ascii=False),
                        json.dumps(stage['post_adoption'], ensure_ascii=False),
                        (' Stage authority (exact evidence): ' + json.dumps(stage['authority'], sort_keys=True) + '.') if stage.get('authority') else ''))
        if stage.get('summary'):
            lines.append('Stage summary: ' + stage['summary'])
    else:
        lines.append('Acceptance stage: NOT DECLARED for this subject. Judge the review question and state which criteria you could not assess.')
    summary = str(handoff.get('summary') or '')
    if summary:
        lines.append('Handoff summary (bounded): ' + summary[:HANDOFF_SUMMARY_CHARS]
                     + (' [truncated; the exact handoff read below has the rest]' if len(summary) > HANDOFF_SUMMARY_CHARS else ''))
    evidence = list(handoff.get('evidence') or [])
    if evidence:
        lines.append('Handoff evidence (exact pinned handles; read those that support the stage criteria before judging them): '
                     + json.dumps(evidence[:HANDOFF_EVIDENCE_ROWS], sort_keys=True)
                     + ('' if len(evidence) <= HANDOFF_EVIDENCE_ROWS else ' (+%d more in the exact handoff read)' % (len(evidence) - HANDOFF_EVIDENCE_ROWS)))
    changes = [{'path': row['path'], 'retained_preimage': row['retained_preimage'], 'current_postimage': row['current_postimage'],
                'baseline': row['baseline'], 'effects': [link['effect_id'] for link in row['effects']],
                'geometry': row['geometry']['state'], 'hunks': row['geometry']['hunks_total'],
                'base_relation': row.get('base_relation')} for row in subject['changed_files']]
    lines.append(_listing('Commission change inventory (every committed effect; retained raw preimage -> current postimage)', changes,
                          (budget or {}).get('inventory'), page, 'changed_files'))
    carry = subject.get('readonly_carry') or {}
    if 'members' in carry:
        relations = {}
        for row in carry['members']:
            relations[row['relation']] = relations.get(row['relation'], 0) + 1
        lines.append('Read-only carry %s (digest %s; %d member(s) by relation %s): inherited unreviewed/held source in review scope, never write '
                     'authority or accepted by inclusion. UNCHANGED_CARRY means the member IS the base blob; CHANGED_SINCE_BASE, ADDED_SINCE_BASE '
                     'and BASE_UNKNOWN members are not shown unchanged by their pins. Read a member with the pinned repository reader: %s.'
                     % (carry['source'], carry['digest'], carry['members_total'], json.dumps(relations, sort_keys=True), json.dumps({
                         'operation': 'repository', 'payload': {'action': 'read', 'repository': subject['repository'], 'path': '<member path>',
                         'expected_sha256': '<member pin>', 'offset': 0, 'limit': 6000}}, sort_keys=True)))
        lines.append(_listing('Carry members [path, pin, relation]', [[row['path'], row['sha256'], row['relation']] for row in carry['members']],
                              (budget or {}).get('carry'), page, 'readonly_carry'))
    else:
        lines.append('Read-only carry: NOT DECLARED. Inherited source outside the commission changes is not part of this subject.')
    lines.append('State your actual family/path coverage and every subject path you did not read. Semantic adequacy is UNASSESSED until you judge it.')
    return lines


#: F2: the COMPLETE rendered reviewer request (purpose, question, scope identity, stage, brief, evidence, inventory, carry,
#: per-input geometry and initial reads) has this explicit byte ceiling. A cumulative request above it is re-rendered
#: bounded: everything upfront stays, and each list that does not fit shows its prefix, its omitted count and the exact
#: owner-issued continuation page (Work view continuity part:subject). A request that still cannot fit refuses; scope
#: is never silently dropped and pins are never presented as reads.
MAX_REVIEW_REQUEST_BYTES = 64 * 1024
_BOUNDED_SHARES = ({'inventory': 12000, 'carry': 8000, 'inputs': 8000, 'reads': 10000},
                   {'inventory': 4000, 'carry': 3000, 'inputs': 3000, 'reads': 3000},
                   {'inventory': 0, 'carry': 0, 'inputs': 0, 'reads': 0})


def prepared_completion_read(task: dict, handoff=None, intent=None):
    """ONE body-free exact same-project native read of a prepared Source completion, issued by the completion owner
    (project_work_continuity.handle part:completion) for the handoff's continuation_origin.intent_id. A prospective fit
    (staged handoff, no event field yet) and the real request (banked handoff) derive the same coordinate; a real event's
    prepared_completion must name the same intent. None when this delivery is not a prepared completion."""
    from laplace.work import project_work_continuity as C
    origin = ((handoff or {}).get('continuation_origin') or {}).get('intent_id')
    banked = ((intent or {}).get('prepared_completion') or {}).get('intent_id')
    if origin and banked and origin != banked:
        raise ValueError('work_delivery: the event prepared completion %s does not match its handoff continuation origin %s.' % (banked, origin))
    ident = origin or banked
    if not ident:
        return None
    read = C.handle(task['project'], task['id'], {'part': 'completion', 'intent_id': ident})
    return {'operation': read['operation'], 'payload': read['payload']}


def _completion_line(read, event_id, handoff_id) -> str:
    return ('Prepared Source completion of delivery %s (late proof arrivals for handoff %s): read %s, match its readiness.continued '
            'to this event and handoff, then read each proof at its exact pin: by its recorded path, scope and observed_sha256 with '
            'read_artifact {path, scope, expected_sha256, offset: 0, limit: 16000}, or by the proof row\'s own exact read when the '
            'completion is a bounded projection, following owner-returned offsets. A proof row is an arrival, '
            'never a review, acceptance or PASS; a missing, changed or forbidden proof stays qualified.'
            % (event_id, handoff_id, json.dumps(read, sort_keys=True)))


def _request_text(task: dict, intent: dict, handoff: dict, root=None) -> str:
    text = _render_request(task, intent, handoff, root)
    if len(text.encode('utf-8')) <= MAX_REVIEW_REQUEST_BYTES:
        return text
    cumulative = 'source_basis' in handoff and ((intent.get('source_review_plan') or {}).get('review_subject') is not None)
    for shares in (_BOUNDED_SHARES if cumulative else ()):
        text = _render_request(task, intent, handoff, root, shares=shares)
        if len(text.encode('utf-8')) <= MAX_REVIEW_REQUEST_BYTES:
            return text
    raise ValueError('work_delivery: the rendered review request exceeds its %d-byte ceiling even with every list bounded to owner-issued '
                     'continuation pages; nothing was sent.' % MAX_REVIEW_REQUEST_BYTES)


def _bounded_input_lines(task, intent, handoff, planned, shares) -> list:
    """The consumed inputs and initial reads of a bounded request: same-order rows of the continuation pages (F2)."""
    from laplace.work import project_work_continuity as C
    page = lambda section, offset, path=None: _subject_page_read(task, intent, handoff, section, offset, path)
    inputs = C.subject_rows(planned, 'inputs', hunk_read=lambda path: page('hunks', 0, path))
    return [_listing('Consumed inputs, compact (exact latest-delta edits and cumulative hunks are in the pinned source; each hunks_read '
                     'pages that file\'s cumulative hunks)', inputs, shares['inputs'], page, 'inputs'),
            _listing('Bounded initial reads; stop each excerpt at its stop_before_offset. Each entry is its exact window and the one native '
                     'call that reads it', C.subject_rows(planned, 'initial_reads'), shares['reads'], page, 'initial_reads')]


def _render_request(task: dict, intent: dict, handoff: dict, root=None, *, shares=None) -> str:
    pins = _source_consumed_pins(task, intent, handoff) if 'source_basis' in handoff else handoff.get('pins') or {}
    lines = ['Independent review requested (delivery %s).' % intent['id'],
             'Work %s: %s' % (task['id'], task.get('title') or ''),
             'Obligation %s of handoff %s; material scope %s.' % (intent['obligation_id'], intent['handoff_id'], intent['work_scope_revision']),
             'Consume only these exact inputs: ' + ('; '.join('%s %s' % (p, d) for p, d in sorted(pins.items())) if pins else str(handoff.get('object') or {})) + '.',
             _record_line(task, intent)]
    if intent['recipient'].get('effect')=='proposal-writer':
        lines[0]='Author-requested manuscript proposal (delivery %s).' % intent['id']
        lines[-1]=('Return a source-addressed edit proposal in the ordinary revise result. Read the exact author instruction and selected source first. '
            'Do not apply edits, run research, claim independent acceptance or change unrelated objects. '
            'The actual runtime owner bounds this one request %s; recovery retains its original turn.' % intent['id'])
    if 'source_basis' in handoff:
        from laplace.work.project_work_views import handle
        basis = intent['source_basis']
        if 'source_review_plan' in intent:
            from laplace.work import development_source
            planned = development_source.review_plan_for_inputs(intent['source_review_plan'], pins)
            if planned['state'] != 'COMPLETE':
                raise ValueError('The offered Source reading plan is not structurally complete for this obligation.')
            question = next(row for row in task['review_obligations'] if row['id'] == intent['obligation_id'])
            lines = ['Required inputs: ' + ', '.join(sorted(pins)) + '.' if line.startswith('Consume only these exact inputs: ') else line for line in lines]
            lines[2:2] = ['Purpose: ' + str(task.get('goal') or task.get('title') or ''),
                          'Review question: ' + str(question['label']) + ' (scope: ' + str(question['scope']) + ').']
            lines.append('Qualified configured Source: ' + json.dumps(_source_description(basis), sort_keys=True) +
                         '. These inputs belong to that configured checkout, not similarly named canonical repository files.')
            inventory = [{key: row[key] for key in ('path', 'before_sha256', 'after_sha256', 'changed')}
                         for row in intent['source_review_plan']['candidate_files']]
            subject = intent['source_review_plan'].get('review_subject')
            if subject is not None:
                lines.extend(_subject_lines(handoff, subject, (lambda section, offset, path=None: _subject_page_read(
                    task, intent, handoff, section, offset, path)) if shares else None, shares))
                if shares:
                    lines.append('Bounded request: the full rendering exceeded %d bytes, so each list shows the prefix that fits and its exact '
                                 'continuation page. Every omitted row remains review scope; state which of them you read.' % MAX_REVIEW_REQUEST_BYTES)
                lines.append('Latest delta only (exact anchor of the most recent committed Source change; NOT the review scope, '
                             'which is the whole subject above): ' + json.dumps(inventory, sort_keys=True))
            else:
                lines.append('Latest candidate file inventory (legacy v1 plan: the latest delta only; earlier committed Source effects of this Work '
                             'are not listed here and are not thereby unchanged): ' + json.dumps(inventory, sort_keys=True))
            if shares is not None:
                lines.extend(_bounded_input_lines(task, intent, handoff, planned, shares))
            for item in (planned['inputs'] if shares is None else ()):
                edits = (item.get('verified_edits') or {}).get('edits') or []
                if edits or subject is None:
                    lines.append('Latest-delta verified edits in ' + item['path'] + ': ' + json.dumps(edits, ensure_ascii=False, sort_keys=True))
                change = item.get('cumulative_change')
                if change:
                    lines.append('Cumulative change in ' + item['path'] + ' (' + change['geometry']['basis'] + '): ' + json.dumps(
                        {'retained_preimage': change['retained_preimage'], 'current_postimage': change['current_postimage'],
                         'baseline': change['baseline'], 'effect_ids': change['effect_ids'], 'geometry': change['geometry']['state'],
                         'hunks': change['geometry']['hunks']}, sort_keys=True))
                lines.append('Context and coverage for ' + item['path'] + ': ' + json.dumps({key: item.get(key) for key in
                    ('requested_context', 'selected_context', 'uninspected_extents', 'uncovered_edit_ids', 'uncovered_hunk_ids')}, sort_keys=True))
            if shares is None:
                lines.append('Bounded initial reads; stop each excerpt at its stop_before_offset, even if the repository offers a later page. '
                         'Each entry is its exact window (path, offset, chars, stop_before_offset) and the one native call that reads it '
                         '(operation, payload; payload.expected_sha256 is the full input pin): ' +
                         json.dumps([native_initial_read(read) for item in planned['inputs'] for read in item['initial_reads']], sort_keys=True))
            lines.append('Suggested reading plan ' + planned['plan_id'] + ' is offered, not observed. COMPLETE means structural input/change coverage only. '
                         'Reading these excerpts neither satisfies this obligation nor proves semantic adequacy. Deliberately expand through the existing pinned '
                         'repository reader when needed to judge dependencies; do not automatically continue to EOF. State any remaining uncertainty in your independent verdict.')
            lines.append('Each initial read carries its full input pin; the retained handoff has the complete pin map. Read permission is separate from Source write authority.')
        else:
            reads = [{'operation': 'repository', 'payload': {'action': 'read', 'repository': basis['repository'],
                'path': path, 'expected_sha256': digest, 'offset': 0, 'limit': 6000}} for path, digest in pins.items()]
            lines.append('Qualified configured Source: ' + json.dumps(_source_description(basis), sort_keys=True) +
                         '. These inputs belong to that configured checkout, not similarly named canonical repository files.')
            lines.append('Pinned repository reads (follow each owner-issued next page): ' + json.dumps(reads, sort_keys=True) +
                         '. Read permission is separate from Source write authority.')
        lines.append('Exact qualified handoff read: ' + json.dumps(handle(task['project'],
            {'view': 'review', 'id': task['id'], 'phase_id': handoff['id']}), sort_keys=True))
        completion = prepared_completion_read(task, handoff, intent)   # one line on the ordinary and bounded renders alike
        if completion is not None:
            lines.append(_completion_line(completion, intent['id'], handoff['id']))
    if handoff.get('feedback_origin'):
        from laplace.pipeline import authoring
        origin=authoring.correction_origin(task['project'],handoff['feedback_origin'],repo_root=root)
        # The exact reference is enough to request the shared correction read;
        # ordinary contextual review can also consume its existing instruction.
        lines.append('Origin is one anchored author instruction, not a new copied comment: '+json.dumps(handoff['feedback_origin'],sort_keys=True)+'. Read its exact owner correction before judging. Existing native read: '+json.dumps({'operation':'author_history','payload':{'id':handoff['feedback_origin']['correction_id']}},sort_keys=True)+'. Exact HTTP origin/currentness read: '+json.dumps(origin['read'],sort_keys=True))
    return '\n'.join(lines)


def _source_origin(root, project, actor, basis, recipient, *, continuation=None,
                   recorded=False, retained_execution=None):
    """One durable-origin check before NEW delivery/return effects, never replay.

    Missing optional handoff fields or a human recovery caller cannot erase the
    actual original turn's commission. Its metadata is read through the Source
    owner; neither public actor labels nor a live incoming carrier grant scope.
    """
    from laplace.writing import records as writing_records, source_execution
    origins = []
    coordinates = [(actor.get('turn_id'), actor.get('session_id'))]
    if continuation:
        coordinates.append((continuation.get('parent_turn_id'), continuation.get('parent_session_id')))
    index = writing_records.index(root) if any(turn for turn, _session in coordinates) else None
    for turn_id, session_id in coordinates:
        if not turn_id:
            continue
        # THE canonical cut-bounded record-family rule (the one source_execution.for_turn uses), never the latest-row
        # index.turns map: a lawful current turn of this project resolves even when its session has later settings
        # versions or another project holds its own immutable ID; an immutable duplicate, a kind/project collision or a
        # contradictory session history refuses before any delivery effect.
        try:
            turn = source_execution._family(index, project, turn_id, 'writing-turn')
        except source_execution.AllowanceRefused as error:
            raise ValueError('work_delivery: original delivery turn/session custody is ambiguous: ' + str(error)[:200]) from None
        if not turn or session_id and turn.get('session_id') != session_id:
            raise ValueError('work_delivery: original delivery turn/session custody is unavailable or changed.')
        attached = source_execution.for_turn(root, project, turn_id)
        if attached is not None:
            origins.append(attached)
    origin = origins[0] if origins else None
    if any(value != origin for value in origins):
        raise ValueError('work_delivery: original delivery and parent have different Source commissions.')
    if origin is not None and basis is None:
        raise ValueError('work_delivery: Source-bound delivery requires its qualified Source basis and commission; ordinary handoff cannot launch it.')
    inherited = (source_execution.inherit_delivery(root, project, actor.get('turn_id'), basis, recipient)
                 if basis is not None else None)
    if inherited != origin or recorded and inherited != retained_execution:
        raise ValueError('work_delivery: original Source execution attachment is unavailable or changed; no legacy admission is permitted.')
    return inherited


def _revalidate(root, project, task, intent) -> str | None:
    """Why this event can no longer be consumed (None when it still can): binding, scope, pins, standing."""
    from laplace.work import project_work, project_work_review
    problem = _binding_problem(task, intent['binding_id'], intent['binding_revision'])
    if problem:
        return problem
    tasks = project_work._tasks(project, root)
    basis, issue = project_work._work_basis(tasks, task['id'])
    if issue or basis.get('scope_revision') != intent['work_scope_revision']:
        return 'the Work material scope changed since submission (%s -> %s)' % (intent['work_scope_revision'], basis.get('scope_revision'))
    if task.get('status') in {'cancelled', 'withdrawn'}:
        return 'the Work is ' + task['status']
    handoff = next((row for row in task.get('phases') or () if row.get('id') == intent['handoff_id']), None)
    if handoff is None or _content_pin(handoff) != intent['content_pin']:
        return 'the handoff is no longer the submitted one'
    try:
        _source_origin(root, project, intent.get('actor') or {}, intent.get('source_basis'), intent['recipient'],
                       continuation=intent.get('continuation'), recorded=True, retained_execution=intent.get('source_execution'))
    except (ValueError, OSError) as error:
        return str(error)
    if 'source_basis' in handoff:
        from laplace.work import development_source
        if 'source_basis' not in intent or intent['source_basis'] != handoff['source_basis']:
            return 'the submitted qualified Source basis is unavailable or changed'
        try:
            pins = _source_consumed_pins(task, intent, handoff)
            observed = development_source.validate_review_basis(root, project, task['id'], intent['source_basis'], consumed_pins=pins)
            if observed['status'] != 'CURRENT':
                return 'qualified Source inputs are ' + observed['status'] + ': ' + observed['reason']
            if 'source_review_plan' in handoff:
                if intent.get('source_review_plan') != handoff['source_review_plan']:
                    return 'the submitted Source reading plan is unavailable or changed'
                projected = development_source.review_plan_for_inputs(intent['source_review_plan'], pins)
                if projected['state'] != 'COMPLETE':
                    return 'the offered Source reading plan is ' + projected['state'] + '; inspect its missing context before transport'
                if 'review_subject' in intent['source_review_plan']:
                    subject = development_source.validate_review_subject(root, project, task['id'], intent['source_basis'],
                                                                         intent['source_review_plan']['review_subject'])
                    if subject['status'] != 'CURRENT':
                        return 'the cumulative Source review subject is ' + subject['status'] + ': ' + subject['reason']
            development_source.validate_review_recipient(root, project, task['id'], intent['source_basis'], intent['recipient'])

        except (ValueError, OSError) as error:
            return str(error)
    else:
        digests = {}
        changed = [path for path, digest in (handoff.get('pins') or {}).items() if project_work_review._file_digest(root, path, digests) != digest]
        if changed:
            return 'handed-off inputs changed since submission: ' + ', '.join(changed[:4])
    if intent.get('feedback_execution'):
        from laplace.work import feedback_route
        try:feedback_route.event_context(root,project,task,handoff)
        except ValueError as error:return str(error)
    return None


def source_admission(root, project, event_id, session_id, reservation):
    """Recheck this exact Work reservation at the actual turn owner, under its lock."""
    task = _task_of_event(root, project, event_id)
    history = _history(task, event_id)
    intent, latest = history[0], history[-1]
    if (latest.get('state') != 'RESERVED' or latest.get('session_id') != session_id
            or latest.get('source_admission_id') != reservation['admission_id']
            or intent.get('source_execution') != reservation['attachment']):
        raise ValueError('Source review admission does not match this original Work reservation.')
    problem = _revalidate(root, project, task, intent)
    if problem:raise ValueError(problem)
    return reservation


def start_source_review(root, project, event_id, request):
    """The detached reviewer host's one entry (native.tools --start-child-turn --source-event). The Source reservation is
    REPLAYED from its owner under the event's original request id (no new admission, session or quota); the request must
    be this RESERVED event's own (request id, reserved session, mode), and admission rechecks it (source_admission)."""
    from laplace.writing import source_execution, turn_admission
    task = _task_of_event(root, project, event_id)
    history = _history(task, event_id)
    intent, latest = history[0], history[-1]
    mode = 'revise' if intent['recipient'].get('effect') == 'proposal-writer' else 'review'
    if (not intent.get('source_execution') or latest.get('state') != 'RESERVED' or not latest.get('source_admission_id')
            or request.get('project') != project or request.get('request_id') != event_id
            or not latest.get('session_id') or request.get('session_id') != latest['session_id'] or request.get('mode') != mode):
        raise ValueError('Detached Source review does not match its original Work reservation.')
    reservation = source_execution.reserve_app(root, intent['source_execution'], event_id, session_id=latest['session_id'], role='review')
    if reservation['admission_id'] != latest['source_admission_id'] or reservation['session_id'] != latest['session_id']:
        raise ValueError('Detached Source review reservation is not the original one.')
    return turn_admission.start_source_turn(root, request, reservation, source_event=event_id,
                                            delivery_event=event_id if intent.get('feedback_execution') else None)


def start_source_return(root, project, event_id, request):
    """The detached parent-return host's one entry (native.tools --start-child-turn --source-return): the once-only
    continuation of a settled Source event into its ORIGINAL parent session. The continuation reservation must already be
    banked by _return_to_parent (proved through the Source owner's spawn guard before any replay), so the host can only
    replay it: no new admission, session or quota. The request must be this event's own CONT request."""
    from laplace.writing import source_execution, turn_admission
    task = _task_of_event(root, project, event_id)
    history = _history(task, event_id)
    intent, latest = history[0], history[-1]
    continuation = intent.get('continuation') or {}
    parent = continuation.get('parent_session_id')
    attachment = intent.get('source_execution')
    if (not attachment or latest.get('state') not in ('RESULT', 'PENDING_PARENT') or not (continuation.get('route') or {}).get('admit_idle')
            or not parent or parent != attachment.get('original_parent_session_id') or request.get('project') != project
            or request.get('request_id') != 'CONT-' + event_id or request.get('session_id') != parent or request.get('mode') != 'work'):
        raise ValueError('Detached Source parent return does not match its original settled Work event.')
    expected = source_execution._ident('SA-', [attachment['commission_id'], request['request_id']])
    source_execution.guard_spawn(root, project, reservation={'attachment': attachment, 'admission_id': expected, 'session_id': parent})
    reservation = source_execution.reserve_app(root, attachment, request['request_id'], session_id=parent, role='continuation')
    if reservation['admission_id'] != expected:
        raise ValueError('Detached Source parent return reservation is not the original one.')
    return turn_admission.start_source_turn(root, request, reservation)


def _source_work_fields(root, project, work_id):
    """The existing Work owner's guards for this trusted, exact inherited target."""
    from laplace.work import project_work
    tasks = project_work._tasks(project, root)
    basis, issue = project_work._work_basis(tasks, work_id)
    if issue:raise ValueError('Source Work basis unavailable: ' + str(issue))
    return {'work_id': work_id, 'expected_work_scope_revision': basis['scope_revision'],
            'expected_dependency_revision': project_work._dependency_revision(tasks[work_id], tasks)}


def _require_source_replay(root, project, intent, found):
    if intent.get('source_execution'):
        from laplace.writing import source_execution
        if source_execution.for_turn(root, project, found['turn_id']) != intent['source_execution']:
            raise ValueError('The existing admitted Source turn has unresolved or different commission custody; no new admission is permitted.')


#: _deliver_event replayed an already-found admitted turn (lost acknowledgement) and retained its coordinates
_REPLAYED = 'REPLAYED_ADMISSION'


def _settle_saved_reply(root: Path, project: str, event_id: str) -> None:
    """The saved terminal reply is the fact. Outside the event lock, settle it through the existing settle_turn owner for the
    event's CURRENT admitted coordinates, only when the banked turn is exactly this event's (same project, admitted session
    and turn, request id = event id) and carries a terminal status. settle_turn rechecks the admitted row under its own
    locks, so a concurrent or repeated call settles once. Never inferred from a local done flag; no verdict is invented."""
    from laplace.writing import records as writing_records
    latest = _history(_task_of_event(root, project, event_id), event_id)[-1]
    if latest['state'] != 'ADMITTED' or not latest.get('turn_id') or not latest.get('session_id'):
        return
    turn = writing_records.fold_records(root)['turns'].get(latest['turn_id']) or {}
    if turn.get('project') != project or turn.get('session_id') != latest['session_id'] or turn.get('request_id') != event_id:
        return   # a foreign or ambiguous saved reply is no terminal proof for this event
    reply = turn.get('reply') or {}
    if reply.get('status'):
        settle_turn(root, project, latest['session_id'], latest['turn_id'], reply)


def _deliver(root: Path, project: str, event_id: str):
    """Consume one event (_deliver_event); an already-found admitted turn it replays is then settled from its exact saved
    terminal reply after the event lock is released (0864: the found branch used to return before that catch-up)."""
    outcome = _deliver_event(root, project, event_id)
    if outcome == _REPLAYED:
        _settle_saved_reply(root, project, event_id)
        return None
    return outcome


def _deliver_event(root: Path, project: str, event_id: str):
    """Consume one event under its own lock: revalidate, reserve, transport, retain; terminal rows are explicit."""
    from laplace.work import project_work
    from laplace.writing import turn_admission
    task = _task_of_event(root, project, event_id)
    history = _history(task, event_id)
    if history[0].get('workflow_execution'):
        from laplace.writing import workflow_progression
        # The workflow owner releases its reservation lock before settling a
        # fast reply or admitting the next phase. Do not wrap that lifecycle.
        return workflow_progression.deliver_event(root, project, task, history[0], history[-1])
    with _event_lock(root, event_id):
        task = _task_of_event(root, project, event_id)
        history = _history(task, event_id)
        intent, latest = history[0], history[-1]
        if intent['recipient'].get('effect') == 'research-producer':
            from laplace.writing.workflow_progression import deliver_research_event
            return deliver_research_event(root,project,task,intent,latest)
        if latest['state'] in TERMINAL:
            return
        from laplace.writing import records as writing_records
        found = turn_admission.reused_turn(writing_records.fold_records(root), {'request_id':event_id,'project':project,
            'mode':'revise' if intent['recipient'].get('effect')=='proposal-writer' else 'review'})
        if found:
            _require_source_replay(root, project, intent, found)
            project_work._append(root, _admitted_row(intent, latest.get('attempts',0), found['session_id'], found['turn_id'], reused=True, recovered=True))
            return _REPLAYED
        binding = intent['recipient']
        if binding['kind'] != 'app-owned':
            project_work._append(root, {**intent, 'state': 'UNSUPPORTED', 'ts': _now(),
                                        'reason': 'no authenticated external attachment adapter: the event stays pending for a real binding; nothing was cloned or started'})
            return
        attempts = latest.get('attempts', 0)
        if attempts >= intent['max_attempts'] or dt.datetime.fromisoformat(intent['deadline_at']) <= dt.datetime.now(dt.timezone.utc):
            project_work._append(root, {**intent, 'state': 'UNCONFIRMED', 'attempts': attempts, 'session_id': latest.get('session_id'), 'ts': _now(),
                                        'reason': 'delivery attempts or deadline exhausted without admitted coordinates'})
            return
        problem = _revalidate(root, project, task, intent)
        if problem:
            project_work._append(root, {**intent, 'state': 'STALE', 'attempts': attempts, 'session_id': latest.get('session_id'), 'ts': _now(),
                                        'reason': 'consumption refused: ' + problem})
            return
        handoff = next(row for row in task.get('phases') or () if row.get('id') == intent['handoff_id'])
        session_id = latest.get('session_id')
        source_reservation = None
        try:
            if intent.get('source_execution'):
                from laplace.writing import source_execution
                source_reservation = source_execution.reserve_app(root, intent['source_execution'], event_id,
                    session_id=session_id, new_session=not bool(session_id), role='review')
                if source_reservation.get('session_id'):
                    session_id = source_reservation['session_id']
                elif not source_reservation.get('may_create_session'):
                    raise ValueError('Source session creation is unknown; reconcile its original reservation.')
            if not session_id:
                writer = binding.get('effect') == 'proposal-writer'
                if writer:
                    matches=[s for s in writing_records.fold_records(root)['sessions'].values()
                        if s.get('project')==project and s.get('workflow_event_id')==event_id]
                    if len(matches)>1:raise ValueError('Proposal writer session custody is ambiguous.')
                    if matches:session_id=matches[0]['id']
                    elif latest.get('session_creation_attempted'):raise ValueError('Proposal writer session creation is UNKNOWN; retain original event.')
            if not session_id:
                if writer:project_work._append(root,{**intent,'state':'RESERVED','session_creation_attempted':True,'ts':_now()})
                session = turn_admission.new_session(root, project, binding['provider'], binding['model'] or '', binding.get('effort') or '', role='author' if writer else 'review',
                    model_role='worker' if writer else 'session',
                    **({'workflow_event_id':event_id} if writer else {}),
                    **({'source_reservation':source_reservation} if source_reservation else {}))
                session_id = session['id']
            if source_reservation:
                source_reservation = source_execution.bind_app(root, source_reservation, session_id)
        except Exception as exc:
            project_work._append(root, {**intent, 'state': 'SUBMITTED', 'attempts': attempts + 1, 'ts': _now(),
                **({'session_creation_attempted':True} if binding.get('effect')=='proposal-writer' else {}),'last_error': str(exc)[:400]})
            return
        # the reservation is durable before transport: a concurrent caller finds this session, never opens another
        project_work._append(root, {**intent, 'state': 'RESERVED', 'attempts': attempts + 1, 'session_id': session_id, 'ts': _now(),
            **({'source_admission_id':source_reservation['admission_id']} if source_reservation else {})})
        try:
            request={'project': project, 'session_id': session_id, 'mode': 'revise' if binding.get('effect')=='proposal-writer' else 'review',
                     'text': _request_text(task, intent, handoff,root), 'request_id': event_id}
            if source_reservation:
                request.update(_source_work_fields(root, project, intent['source_execution']['work_id']))
                admitted = turn_admission.start_source_turn(root, request, source_reservation, source_event=event_id,
                    delivery_event=event_id if intent.get('feedback_execution') else None)
            else:
                if binding.get('effect')=='proposal-writer':
                    request['selection']=intent['effect_selection']
                    admitted=turn_admission.start_workflow_turn(root,request,event_id)
                else:admitted = (turn_admission.start_work_delivery_turn(root,request,event_id)
                            if intent.get('feedback_execution') else turn_admission.start_turn(root,request))
        except Exception as exc:
            project_work._append(root, {**intent, 'state': 'SUBMITTED', 'attempts': attempts + 1, 'session_id': session_id, 'ts': _now(),
                                        'last_error': str(exc)[:400]})
            return
        project_work._append(root, {**intent, 'state': 'DELIVERED', 'attempts': attempts + 1, 'session_id': session_id, 'ts': _now()})
        project_work._append(root, _admitted_row(intent, attempts + 1, admitted['session_id'], admitted['turn_id'], reused=bool(admitted.get('reused'))))
    # A recipient that reached its terminal reply before ADMITTED was published found this event still RESERVED and its
    # terminal hook settled nothing. The saved reply is the fact: settle it now through the same hook, whose own event
    # lock and ADMITTED recheck keep the settlement once-only against a hook that runs concurrently or later. The fresh
    # path holds its exact admitted coordinates; the replay and recovery paths use _settle_saved_reply on the retained ones.
    reply = (writing_records.fold_records(root)['turns'].get(admitted['turn_id']) or {}).get('reply') or {}
    if reply.get('status'):
        settle_turn(root, project, admitted['session_id'], admitted['turn_id'], reply)


def _admitted_row(intent, attempts, session_id, turn_id, *, reused=False, recovered=False) -> dict:
    return {**intent, 'state': 'ADMITTED', 'attempts': attempts, 'session_id': session_id, 'turn_id': turn_id, 'request_id': intent['id'],
            'retained': {'session_id': session_id, 'turn_id': turn_id, 'request_id': intent['id']}, 'recipient_ack': 'UNKNOWN',
            'reused': reused, 'recovered': recovered, 'ts': _now()}


def recover(root: Path, project: str, payload: dict, door: dict) -> dict:
    """Recover the same event: by its request id first (no new turn), else one more bounded consumption."""
    from laplace.work import project_work
    from laplace.writing import records as writing_records, turn_admission
    _require(payload, 'recover')
    if _acting(root, project, door).get('role') == 'review':
        raise ValueError('work_delivery: a review-role turn cannot recover a delivery.')
    event_id = payload['event_id']
    task = _task_of_event(root, project, event_id)
    if _history(task, event_id)[0].get('workflow_execution'):
        _deliver(root, project, event_id)
        from laplace.writing import workflow_progression
        workflow_progression.advance(root, project, task['id'])
        current = _task_of_event(root, project, event_id)
        return {'ok':True,'event':_facet_event(root,project,current,event_id)}
    if _history(task,event_id)[0]['recipient'].get('effect')=='research-producer':
        _deliver(root,project,event_id)
        return {'ok':True,'event':_facet_event(root,project,_task_of_event(root,project,event_id),event_id)}
    with _event_lock(root, event_id):
        # fresh under the event lock: a RESULT published concurrently is never followed by a stale recovered ADMITTED
        history = _history(_task_of_event(root, project, event_id), event_id)
        intent, latest = history[0], history[-1]
        if latest['state'] not in TERMINAL:
            found = turn_admission.reused_turn(writing_records.fold_records(root), {'request_id': event_id, 'project': project,
                'mode':'revise' if intent['recipient'].get('effect')=='proposal-writer' else 'review'})
            if found:
                _require_source_replay(root, project, intent, found)
                with project_work.dispatch_lock(root):
                    project_work._append(root, _admitted_row(intent, latest.get('attempts', 0), found['session_id'], found['turn_id'], reused=True, recovered=True))
    # A lost admission acknowledgement can let the actual terminal reply bank before WD learns its coordinates, for an
    # ordinary, Source or feedback delivery alike (workflow and research returned above through their own owners). Reuse
    # the same terminal hook with that exact retained reply; never infer a verdict or fabricate an ACK.
    _settle_saved_reply(root, project, event_id)
    latest = _history(_task_of_event(root, project, event_id), event_id)[-1]
    if latest['state'] not in TERMINAL:
        _deliver(root, project, event_id)
    elif latest['state'] in ('RESULT', 'PENDING_PARENT', 'PARENT_REFUSED') and ((intent.get('continuation') or {}).get('parent_session_id')):
        # the SAME parent-return transaction: an admission whose publication was cut is reconciled from the turn owner by its
        # stable request id (never a new turn); otherwise the once-only admission is asked again under the same budget
        _return_to_parent(root, project, event_id)
    task = _task_of_event(root, project, event_id)
    return {'ok': True, 'event': _facet_event(root, project, task, event_id)}


# ------------------------------------------------------------------------------------------------ the terminal hook and the continuation

def settle_turn(root: Path, project: str, session_id: str, turn_id: str, result: dict) -> list[dict]:
    """Called by turn_execution._bank_reply for every terminal turn: the admitted deliveries of this turn get their
    RESULT row, and an intent with parent coordinates gets ONE bounded continuation row addressed to that parent."""
    from laplace.work import project_work
    settled = []
    for task in project_work._tasks(project, root).values():
        for event_id in dict.fromkeys(row['id'] for row in _rows(task, EVENT)):
            history = _history(task, event_id)
            latest = history[-1]
            if latest['state'] != 'ADMITTED' or latest.get('turn_id') != turn_id:
                continue
            intent = history[0]
            if intent.get('workflow_execution'):
                from laplace.writing import workflow_progression
                workflow_progression.settle_event(root, project, task, intent, latest, result)
                settled.append({'event_id':event_id,'work_id':task['id'],'workflow':True})
                continue
            with _event_lock(root, event_id), project_work.dispatch_lock(root):
                current = _history(_task_of_event(root, project, event_id), event_id)[-1]
                if current['state'] != 'ADMITTED' or current.get('turn_id') != turn_id or current.get('session_id') != session_id:
                    continue   # settled once, only for the exact admitted session and turn
                acceptance = _acceptance(root, project, task, intent, turn_id)
                row = {**intent, 'state': 'RESULT', 'attempts': latest.get('attempts', 0), 'session_id': session_id, 'turn_id': turn_id,
                       'retained': latest.get('retained'), 'recipient_ack': 'TERMINAL', 'ts': _now(),
                       'result': {'status': result.get('status'), 'text': str(result.get('text') or '')[:300], 'error': str(result.get('error') or '')[:300] or None},
                       'acceptance': acceptance}
                continuation = intent.get('continuation')
                if continuation and continuation.get('parent_session_id'):
                    row['continuation_work_id'] = _continuation_row(root, project, task, intent, row, continuation)
                project_work._append(root, row)
            returned = _return_to_parent(root, project, event_id) if continuation and continuation.get('parent_session_id') else None
            settled.append({'event_id': event_id, 'work_id': task['id'], 'continuation_work_id': row.get('continuation_work_id'),
                            'parent_return': (returned or {}).get('state')})
    return settled


def admit_pending_continuations(root: Path, project: str, session_id: str) -> list[dict]:
    """Called by turn_execution._finish when a turn of `session_id` is done: the approved continuations that found this
    parent active are admitted now, once, in the same session; nothing else starts a turn."""
    from laplace.work import project_work
    admitted = []
    for task in project_work._tasks(project, root).values():
        for event_id in dict.fromkeys(row['id'] for row in _rows(task, EVENT)):
            history = _history(task, event_id)
            if history[-1]['state'] == 'PENDING_PARENT' and (history[0].get('continuation') or {}).get('parent_session_id') == session_id:
                outcome = _return_to_parent(root, project, event_id)
                if outcome:
                    admitted.append({'event_id': event_id, 'state': outcome['state']})
    return admitted


def _return_to_parent(root: Path, project: str, event_id: str) -> dict | None:
    """Root's PARENT_RETURN: admit at most one authorised continuation in the SAME idle parent session through the existing
    turn owner, or keep the event pending with the exact reason. Stable request identity CONT-<event>; finite attempts and depth;
    scope currentness and cancellation rechecked; no new session."""
    from laplace.work import project_work
    from laplace.writing import records as writing_records, turn_admission
    from laplace.writing import child_hosts, turn_jobs
    with _event_lock(root, event_id):
        task = _task_of_event(root, project, event_id)
        history = _history(task, event_id)
        intent, latest = history[0], history[-1]
        if latest['state'] not in ('RESULT', 'PENDING_PARENT', 'PARENT_REFUSED'):
            return None
        continuation = intent.get('continuation') or {}
        route = continuation.get('route')
        parent = continuation.get('parent_session_id')
        request_id = 'CONT-' + event_id
        attempts = sum(1 for row in history if row['state'] == 'CONTINUED')            # admissions actually made
        deferrals = sum(1 for row in history if row['state'] == 'PENDING_PARENT')      # a busy parent defers; the parent's own finish retries once
        settled = next(row for row in reversed(history) if row['state'] in SETTLED or row['state'] == 'RESULT')
        base = {**intent, 'attempts': settled.get('attempts', 0), 'session_id': settled.get('session_id'), 'turn_id': settled.get('turn_id'),
                'retained': settled.get('retained'), 'recipient_ack': settled.get('recipient_ack'), 'result': settled.get('result'),
                'acceptance': settled.get('acceptance'), 'continuation_work_id': settled.get('continuation_work_id'), 'ts': _now()}
        if settled.get('research_run_id'):base['research_run_id']=settled['research_run_id']
        fold = writing_records.fold_records(root)
        session = fold['sessions'].get(parent) or {}

        def keep(state, reason, **extra):
            if state == 'PARENT_REFUSED' and latest['state'] == 'PARENT_REFUSED' and latest.get('reason') == reason:
                return latest   # the same refusal is not appended twice
            row = {**base, 'state': state, 'return_attempts': attempts + (1 if state == 'CONTINUED' else 0),
                   'return_deferrals': deferrals + (1 if state == 'PENDING_PARENT' else 0), 'reason': reason, **extra}
            with project_work.dispatch_lock(root):
                project_work._append(root, row)
            return row
        # 1. RECONCILE FIRST: an admission the turn owner already holds under this event's stable request id is an effect
        #    already committed; it is published as it stands (recovered), whatever the authority looks like now
        found = turn_admission.reused_turn(fold, {'request_id': request_id, 'project': project, 'mode': 'work'}) if route else None
        if found and latest['state'] != 'CONTINUED':
            _require_source_replay(root, project, intent, found)
            return keep('CONTINUED', None, continuation_turn={'session_id': found['session_id'], 'turn_id': found['turn_id'], 'request_id': request_id, 'reused': True},
                        recovered=True, cost={key: session.get(key) for key in ('provider', 'model', 'effort')}, depth=int(continuation.get('depth') or 0) + 1)
        if latest['state'] == 'PARENT_REFUSED':
            return latest   # nothing to reconcile and the refusal stands; a new route is a new submission
        # 2. THE STOP BOUNDARY: the authoritative facts of the submitting parent turn (its saved reply, its live job flag, the
        #    host's cancel marker); a stopped parent is never restarted under the old route
        parent_turn_id = continuation.get('parent_turn_id')
        parent_turn = fold['turns'].get(parent_turn_id) or {}
        stopped = None
        if (parent_turn.get('reply') or {}).get('status') == 'interrupted':
            stopped = 'its saved reply is interrupted'
        elif (turn_jobs._JOBS.get(parent_turn_id) or {}).get('interrupt_requested'):
            stopped = 'Stop was requested on its live job'
        elif parent:
            try:
                marker = child_hosts._read_host(child_hosts._host_path(root, parent).with_suffix('.cancel.json'))
            except ValueError:
                marker = {}
            if marker.get('turn_id') == parent_turn_id:
                stopped = 'its host carries a cancel marker'
        if stopped:
            return keep('PARENT_REFUSED', 'stopped: the submitting parent turn %s was stopped (%s); no automatic restart under this route, a new submission is a new route'
                        % (parent_turn_id, stopped))
        if not route or not route.get('admit_idle'):
            return keep('PARENT_REFUSED', 'no approved parent route: the result is retained for inspection (status / the queued continuation row)')
        if int(continuation.get('depth') or 0) >= int(route.get('max_depth') or 1):
            return keep('PARENT_REFUSED', 'continuation depth %d reached the approved max_depth %d' % (continuation.get('depth') or 0, route.get('max_depth') or 1))
        if attempts >= int(route.get('max_attempts') or 1):
            return keep('PARENT_REFUSED', 'the approved return attempts (%d) are spent' % route.get('max_attempts', 1))
        if deferrals >= MAX_RETURN_DEFERRALS:
            return keep('PARENT_REFUSED', 'the parent stayed busy through %d deferrals; the result is retained for inspection' % deferrals)
        if not session or session.get('project') != project or session.get('role', 'author') != 'author' or session.get('dispatch_id'):
            return keep('PARENT_REFUSED', 'the submitting session is no longer an author session of this project')
        problem = _revalidate_standing(root, project, task, intent)
        if problem:
            return keep('PARENT_REFUSED', 'the Work is no longer the submitted one: ' + problem)
        try:
            _source_origin(root, project, intent.get('actor') or {}, intent.get('source_basis'), intent['recipient'],
                           continuation=continuation, recorded=True, retained_execution=intent.get('source_execution'))
        except (ValueError, OSError) as error:
            return keep('PARENT_REFUSED', 'original delivery admission refused: ' + str(error)[:400])
        text = _continuation_text(task, intent, settled, root=root)
        source_reservation = None
        if intent.get('source_execution'):
            from laplace.writing import source_execution
            try:
                source_reservation = source_execution.reserve_app(root, intent['source_execution'], request_id, session_id=parent, role='continuation')
            except (ValueError, OSError) as error:
                return keep('PARENT_REFUSED', 'Source allowance refuses a new parent admission: ' + str(error)[:400])
        try:
            request = {'project':project,'session_id':parent,'mode':'work','text':text,'request_id':request_id,
                       'queued_work_ids':[settled['continuation_work_id']] if settled.get('continuation_work_id') else []}
            if source_reservation:
                request.update(_source_work_fields(root, project, intent['source_execution']['work_id']))
                admitted = turn_admission.start_source_turn(root, request, source_reservation, source_return=event_id)
            else:
                admitted = turn_admission.start_turn(root, request)
        except ValueError as exc:
            # the existing admission's own refusals: a working session (not idle), a review session, a missing project
            return keep('PENDING_PARENT', 'parent not admitted now: ' + str(exc)[:300])
        # the admission is committed at the turn owner under the stable request id; if THIS publication is cut, public recover
        # finds the same turn there (step 1) and publishes it, never a second one
        return keep('CONTINUED', None, continuation_turn={'session_id': admitted['session_id'], 'turn_id': admitted['turn_id'], 'request_id': request_id,
                                                          'reused': bool(admitted.get('reused'))},
                    cost={key: session.get(key) for key in ('provider', 'model', 'effort')}, depth=int(continuation.get('depth') or 0) + 1)


def _revalidate_standing(root, project, task, intent) -> str | None:
    from laplace.work import project_work
    tasks = project_work._tasks(project, root)
    basis, issue = project_work._work_basis(tasks, task['id'])
    if issue or basis.get('scope_revision') != intent['work_scope_revision']:
        return 'material scope changed (%s -> %s)' % (intent['work_scope_revision'], basis.get('scope_revision'))
    if task.get('status') in {'cancelled', 'withdrawn'}:
        return 'the Work is ' + task['status']
    return None


PLAN_READ_SECTIONS = ('changed_files', 'readonly_carry', 'effects', 'inputs', 'initial_reads')


def plan_reads(project, task, intent) -> dict:
    """The bounded default-status projection of one delivery's recorded Source reading plan: its identity, NOT_EXPANDED
    and the exact owner subject-page continuations (project_work_continuity) of every recorded section. The whole
    immutable plan is never copied into status; it remains on the intent and its handoff phase, unchanged."""
    from laplace.work import project_work_continuity as C
    plan = intent.get('source_review_plan') or {}
    subject = plan.get('review_subject')
    out = {'state': 'NOT_EXPANDED', 'plan_id': plan.get('plan_id'), 'handoff_id': intent.get('handoff_id'),
           'review_subject_id': (subject or {}).get('subject_id'), 'obligation_id': intent.get('obligation_id'),
           'meaning': ('The recorded plan is not expanded in default status. Follow each exact subject page and its next; pages are '
                       'recorded review scope, not a read of any source file, and offered context is not observed reading.')}
    if subject is None:
        out.update(sections=None, reason='This plan records no cumulative review subject; its handoff phase holds the whole plan.')
        return out
    out['sections'] = {section: C.subject_page_handle(project, task['id'], intent['handoff_id'], section, 0,
                                                      obligation_id=intent.get('obligation_id') if section in C._PROJECTED else None)
                       for section in PLAN_READ_SECTIONS}
    out['hunks'] = 'Each changed_files row names a path; read section hunks with that exact path.'
    return out


def _review_phase_line(root, task, acceptance) -> str:
    """The existing small guarded read of the review phase this result recorded.

    It carries that review's verdict and every finding. The delivery status
    envelope is for standing and retained facts. Empty when no phase is named
    or the captured Work no longer holds it (the status read still applies).
    """
    review_id = acceptance.get('review_id')
    if not review_id or root is None:
        return ''
    from laplace.work import project_work_review
    try:
        read = project_work_review.phase_read(task, root, review_id, project=task.get('project'))
    except (ValueError, KeyError, TypeError):
        return ''
    native = {key: read[key] for key in ('operation', 'payload') if key in read}
    return ('Recorded review %s: read its verdict and every finding with this exact phase read before relying on any summary: %s.\n'
            % (review_id, json.dumps(native, sort_keys=True)))


def exact_reply_read(root, project, turn_id, *, fold=None) -> dict | None:
    """The existing same-project exact stored reply record of ONE admitted terminal turn (author_history view:record).

    Issued only for the unique banked reply of that turn in this project; a missing or ambiguous reply issues nothing.
    It is the stored record, not the presented public-message page, and following it is not acceptance or receipt.
    """
    if root is None or not project or not turn_id:
        return None
    from laplace.writing import records as writing_records
    try:
        fold = fold if fold is not None else writing_records.fold_records(root)
        turn = fold['turns'].get(turn_id) or {}
        replies = [row.get('id') for row in writing_records.index(root).by_turn.get(turn_id, []) if row.get('record') == 'writing-reply']
    except (ValueError, OSError, KeyError):
        return None
    reply = turn.get('reply') or {}
    if turn.get('project') != project or not reply.get('id') or replies != [reply['id']]:
        return None
    from laplace.work.author_history_metrics import _read_handle
    return {**_read_handle(project, {'view': 'record', 'id': 'activity:journal:' + reply['id']}),
            'reply_id': reply['id'], 'turn_id': turn_id,
            'native_scope': 'Any admitted session of this same project may follow this exact public record read; another project refuses.',
            'meaning': ('The exact stored reply record of this turn. The presented message page is a separate view; reading '
                        'either is not acceptance, receipt or completion.')}


def _reply_line(root, project, result_row) -> str:
    found = exact_reply_read(root, project, result_row.get('turn_id'))
    if not found:
        return ''
    native = {'operation': found['operation'], 'payload': found['payload']}
    return ('Exact stored reply record of turn %s, readable from any admitted session of this project (the presented '
            'message page is a separate view): %s.\n' % (result_row.get('turn_id'), json.dumps(native, sort_keys=True)))


def _reply_target(root, project, result_row) -> dict:
    found = exact_reply_read(root, project, result_row.get('turn_id'))
    return {'exact_reply_read': {'operation': found['operation'], 'payload': found['payload']}} if found else {}


def _pending_reply_read(root, project, target) -> dict | None:
    """A queued row's exact reply read: its own banked target, or lazily from its settled delivery for older rows."""
    if isinstance(target.get('exact_reply_read'), dict):
        return target['exact_reply_read']
    from laplace.work import project_work
    try:
        work = project_work._tasks(project, root).get(target.get('work_id')) or {}
        history = _history(work, target.get('event_id')) if work else []
    except (ValueError, KeyError, TypeError, OSError):
        return None
    settled = next((row for row in reversed(history) if row.get('turn_id') and (row.get('state') == 'RESULT' or row.get('state') in SETTLED)), None)
    found = exact_reply_read(root, project, settled.get('turn_id')) if settled else None
    return {'operation': found['operation'], 'payload': found['payload']} if found else None


def _continuation_text(task, intent, result_row, *, root=None, project=None) -> str:
    acceptance = result_row.get('acceptance') or {}
    result = result_row.get('result') or {}
    review_line = _review_phase_line(root, task, acceptance) + _reply_line(root, project or task.get('project'), result_row)
    if intent['recipient'].get('effect')=='research-producer':
        return ('REGISTERED RESEARCH RESULT for delivery %s, Work %s, obligation %s: run %s ended %s. '
                'Inspect exact run/result/cleanup and separate canonical obligation standing with work_delivery '
                '{action: status, event_id: %s}. Producer completion is not scientific acceptance.'
                % (intent['id'],task['id'],intent['obligation_id'],result_row.get('research_run_id'),result.get('status'),intent['id']))
    if 'source_basis' in intent:
        header = 'DELIVERY RESULT (continuation of your submission %s; admitted once by the delivery owner).\n' % intent['id']
        source = 'Qualified configured Source: %s.\n' % json.dumps(_source_description(intent['source_basis']), sort_keys=True)
        work = ('Work %s, obligation %s: reviewer turn %s ended %s. Recorded obligation status at result: %s (%s).\n'
                % (task['id'], intent['obligation_id'], result_row.get('turn_id'), result.get('status') or 'unknown',
                   acceptance.get('status'), acceptance.get('currentness')))
        completion = prepared_completion_read({'id': task['id'], 'project': project or task.get('project')}, None, intent)
        reads = (_completion_line(completion, intent['id'], intent.get('handoff_id')) + '\n') if completion else ''
        status = ('Read current qualified standing and the exact retained facts with work_delivery {action: status, event_id: %s}; '
                  'complete the queued continuation request with task_status when done.' % intent['id'])
        # Bound: drop optional prose first; if the whole review-phase/reply/completion reads still cannot fit, the one exact
        # delivery-status descent (it names the review phase, stored reply and prepared_completion) replaces them. No read is cut.
        for text in (header + review_line + source + work + reads + status, header + review_line + work + reads + status):
            if len(text) <= PARENT_TEXT_CHARS:
                return text
        tail = ('The exact review-phase, stored-reply and prepared-completion reads do not fit this %d-character return; '
                'follow them from the delivery status read below.\n' % PARENT_TEXT_CHARS) + status
        return (header + work)[:max(0, PARENT_TEXT_CHARS - len(tail))] + tail
    return ('DELIVERY RESULT (continuation of your submission %s; this turn was admitted once by the delivery owner).\n'
            '%s'
            'Work %s, obligation %s: the reviewer turn %s ended %s. Canonical obligation status: %s (%s)%s.\n'
            'Read the exact facts with work_delivery {action: status, event_id: %s}; complete the queued continuation request with task_status when it is done.'
            % (intent['id'], review_line, task['id'], intent['obligation_id'], result_row.get('turn_id'), result.get('status') or 'unknown',
               acceptance.get('status'), acceptance.get('currentness'), '; recorded by this delivery' if acceptance.get('by_this_delivery') else '; not recorded by this delivery',
               intent['id']))[:4000]


#: the existing automatic-parent and queued-goal bounds (characters)
PARENT_TEXT_CHARS = 4000
QUEUED_GOAL_CHARS = 2000


def _continuation_goal(summary, completion, event_id, limit=QUEUED_GOAL_CHARS) -> str:
    """The queued CR goal: the summary prose is cut first. A completion read that cannot fit whole (a valid long Work id)
    is replaced by the exact delivery-status descent to event.prepared_completion, never sliced."""
    suffix = (' Prepared completion read (late proof arrivals; a read, never acceptance): ' + json.dumps(completion, sort_keys=True)) if completion else ''
    if completion and len(suffix) > limit // 2:
        suffix = (' Prepared completion: its exact read does not fit this %d-character goal; follow work_delivery %s to event.prepared_completion.'
                  % (limit, json.dumps({'action': 'status', 'event_id': event_id}, sort_keys=True)))
    return summary[:max(0, limit - len(suffix))] + suffix


def _continuation_row(root, project, task, intent, result_row, continuation) -> str:
    """ONE bounded session-request Work row per event, addressed to the parent session that submitted it; the parent's
    next admitted turn carries it (turn_admission.admit -> pending_continuations); the ordinary task_status door closes it."""
    from laplace.work import project_work
    ident = 'CR-' + _digest({'event': intent['id']})[7:31]
    if ident in project_work._tasks(project, root):
        return ident
    acceptance = result_row['acceptance']
    summary = ('Delivery %s of obligation %s returned: turn %s %s; canonical obligation status %s (%s)%s.'
               % (intent['id'], intent['obligation_id'], result_row['turn_id'], result_row['result']['status'] or 'unknown',
                  acceptance.get('status'), acceptance.get('currentness'),
                  '; recorded by this delivery' if acceptance.get('by_this_delivery') else '; not recorded by this delivery'))
    if result_row.get('research_run_id'):
        summary=('Registered Research delivery %s of obligation %s returned run %s: %s. '
                 'Result/cleanup and scientific acceptance are separate.' % (intent['id'],intent['obligation_id'],
                 result_row['research_run_id'],result_row['result']['status']))
    completion = None if result_row.get('research_run_id') else prepared_completion_read({'id': task['id'], 'project': project}, None, intent)
    goal = _continuation_goal(summary, completion, intent['id'])
    project_work._task(project, {'id': ident, 'title': 'Review result for delivery %s' % intent['id'], 'goal': goal, 'kind': 'session-request',
                                 'parent_work_id': task['id'], 'obligation_id': intent['obligation_id'], 'origin': 'work-delivery',
                                 'logical_target': {'kind': CONTINUATION_KIND, 'event_id': intent['id'], 'work_id': task['id'],
                                                    'parent_session_id': continuation['parent_session_id'], 'parent_turn_id': continuation.get('parent_turn_id'),
                                                    'read': {'operation': 'work_delivery', 'payload': {'action': 'status', 'event_id': intent['id']}},
                                                    **_reply_target(root, project, result_row)}}, root)
    return ident


def pending_continuations(root: Path, project: str, session_id: str, exclude=()) -> list[dict]:
    """The open continuation rows addressed to this session, in the queued-request shape, bounded."""
    from laplace.work import project_work
    if not session_id:
        return []
    rows = []
    for task in project_work._tasks(project, root).values():
        target = task.get('logical_target') if isinstance(task.get('logical_target'), dict) else {}
        if (task.get('task_kind') == 'session-request' and target.get('kind') == CONTINUATION_KIND and target.get('parent_session_id') == session_id
                and task.get('status') not in {'done', 'verified', 'cancelled'} and task['id'] not in exclude):
            rows.append({'id': task['id'], 'title': str(task.get('title') or ''), 'goal': str(task.get('goal') or ''), 'anchor': task.get('anchor') or {},
                         'continuation': {'event_id': target.get('event_id'), 'work_id': target.get('work_id'), 'read': target.get('read'),
                                          **({'exact_reply_read': reply} if (reply := _pending_reply_read(root, project, target)) else {})}})
    rows.sort(key=lambda row: row['id'])
    return rows[:MAX_CONTINUATIONS]


# ------------------------------------------------------------------------------------------------ the shared facet

def _acceptance(root, project, task, intent, turn_id, *, read_context=None) -> dict:
    """The Work's CANONICAL obligation status (project_work_review.facet), and whether this delivery's turn recorded it."""
    from laplace.work import project_work, project_work_review
    context={} if read_context is None else read_context
    tasks = _read_tasks(root,project,context)
    key=('work_delivery.review_facet',str(Path(root).resolve()),project,task['id'])
    if key not in context:
        context[key]=project_work_review.facet(tasks.get(task['id'],task),root,tasks=tasks,
            digests=context.setdefault(('work-evidence',str(Path(root).resolve())),{}),read_context=context)
    canonical=context[key]
    entry = next((row for row in (canonical or {}).get('obligations') or [] if row.get('id') == intent['obligation_id']), None)
    if entry is None:
        return {'status': 'UNDECLARED', 'currentness': 'UNKNOWN', 'satisfied': False, 'by_this_delivery': False, 'review_id': None}
    review = next((row for row in reversed(task.get('phases') or ()) if row.get('id') == entry.get('review_id')), None)
    return {key: entry.get(key) for key in ('status', 'currentness', 'currentness_reason', 'independence', 'satisfied', 'review_id', 'reviewer')} | {
        'by_this_delivery': bool(review and turn_id and (review.get('actor') or {}).get('turn_id') == turn_id)}


def _facet_event(root, project, task, event_id, *, read_context=None) -> dict:
    from laplace.work import project_work_review
    from laplace.writing import child_hosts, records as writing_records, turn_jobs
    history = _history(task, event_id)
    intent, latest = history[0], history[-1]
    if intent['recipient'].get('effect')=='research-producer':
        from laplace.writing.workflow_progression import research_event_view
        return research_event_view(root,project,task,intent,latest,read_context=read_context)
    if intent.get('workflow_execution'):
        from laplace.writing import workflow_progression
        return workflow_progression.event_view(root, project, task, intent, latest,read_context=read_context)
    facts = {'submitted': intent['ts']}
    for row in history:
        if row['state'] in ('RESERVED', 'DELIVERED', 'ADMITTED', 'RESULT', 'STALE', 'UNSUPPORTED', 'UNCONFIRMED', 'PENDING_PARENT', 'CONTINUED', 'PARENT_REFUSED'):
            facts[row['state'].lower()] = row['ts']
    event = {'id': event_id, 'state': latest['state'], 'work_id': task['id'], 'handoff_id': intent['handoff_id'], 'obligation_id': intent['obligation_id'],
             'recipient': intent['recipient'], 'attempts': latest.get('attempts', 0), 'max_attempts': intent['max_attempts'], 'deadline_at': intent['deadline_at'],
             'content_pin': intent['content_pin'], 'work_scope_revision': intent['work_scope_revision'], 'facts': facts,
             'submitted_by': (intent.get('actor') or {}).get('actor'), 'continuation': intent.get('continuation'),
             'reason': latest.get('reason'), 'last_error': latest.get('last_error')}
    if intent['recipient'].get('effect'):event['effect']=intent['recipient']['effect']
    if intent.get('dispatcher'):
        event['dispatcher']={key:intent['dispatcher'].get(key) for key in ('actor','origin','session_id','turn_id')}
    if intent.get('prepared_completion'):event['prepared_completion']=copy.deepcopy(intent['prepared_completion'])
    if 'source_basis' in intent:
        event['source_basis'] = copy.deepcopy(intent['source_basis'])
    if intent.get('source_execution'):
        from laplace.writing import source_execution
        event['source_execution'] = copy.deepcopy(intent['source_execution'])
        try:event['source_allowance'] = source_execution.status(root, intent['source_execution'])
        except (ValueError, OSError) as error:event['source_allowance'] = {'state':'UNKNOWN','stop_reason':str(error)[:400]}
    if 'source_review_plan' in intent:
        # Default status is a bounded semantic header (Root causal case RW-20261103-111139-631665: copying the whole plan
        # made one 450-620K status line). The immutable plan stays unchanged on the intent and its handoff phase; exact
        # owner subject-page continuations reach every recorded row.
        event['source_review_plan_summary'] = project_work_review.source_plan_summary(intent['source_review_plan'])
        event['source_review_plan_reads'] = plan_reads(project, task, intent)
    admitted = next((row for row in reversed(history) if row['state'] in ('ADMITTED',) + SETTLED), None)
    if admitted:
        turn_id, session_id = admitted['turn_id'], admitted['session_id']
        event['admitted'] = {**(admitted.get('retained') or {'session_id': session_id, 'turn_id': turn_id, 'request_id': event_id}),
                             'reused': admitted.get('reused'), 'recovered': admitted.get('recovered', False), 'recipient_ack': latest.get('recipient_ack') or admitted.get('recipient_ack')}
        fold = _read_fold(root,read_context)
        turn = fold['turns'].get(turn_id) or {}
        job = turn_jobs._JOBS.get(turn_id)
        execution = child_hosts.child_execution(root, session_id)
        event['running'] = bool(job and not job.get('done')) or execution.get('state') in {'STARTING', 'RUNNING', 'WAITING'}
        reply = turn.get('reply') or {}
        # Existing exact public owners, qualified by the actual WD admission.
        # No cross-session native message fence is widened by this descriptor.
        from urllib.parse import urlencode
        from laplace.writing import session_reads
        message = session_reads._message_handle({'project': project, 'session_id': session_id,
            'turn_id': turn_id, 'part': 'reply', 'limit': 4000}, offset=0)
        event['public_reply_read'] = {key: message[key] for key in ('identity', 'http', 'sdk')}
        event['turn_read'] = {'http': {'method': 'GET', 'url': '/authoring/session-turn?' +
            urlencode({'project': project, 'id': turn_id, 'view': 'turn'})}}
        if reply.get('id'):
            from laplace.work.author_history_metrics import _read_handle
            event['exact_reply_read'] = _read_handle(project, {'view': 'record', 'id': 'activity:journal:' + reply['id']})
        # The bounded preview is THE public-message owner's own first page at this admitted identity (its
        # reply_presentation precedence, row pins and seal), never a slice of a raw fold field. The Complete
        # handle above is unchanged; a changed/ambiguous message is a qualified refusal, never a fallback.
        try:
            preview = session_reads.public_message(root, {'project': project, 'session_id': session_id,
                'turn_id': turn_id, 'part': 'reply', 'limit': 300})
        except (ValueError, OSError) as error:
            event['result'] = {'status': reply.get('status'), 'available': False, 'state': 'REFUSED',
                'refusal': {'reason': str(error)[:300], **session_reads.message_refusal_details(error)},
                'restart_read': event['public_reply_read']}
        else:
            if preview['state'] != 'AVAILABLE':
                event['result'] = {'status': reply.get('status'), 'available': False, 'state': preview['state'],
                    'reason': preview.get('reason')}
            else:
                event['result'] = {'status': reply.get('status'), 'text': preview['content'], 'available': True,
                    'state': 'AVAILABLE', 'basis': preview['basis'], 'presentation_origin': preview['presentation_origin'],
                    'truncated': preview['truncated'], 'total_characters': preview['total_characters'],
                    'page_read': preview['page_read'], 'next_read': preview['next_read']}
        if intent['recipient'].get('effect')=='proposal-writer':
            from laplace.manuscript import proposal_navigation,manuscript_proposals
            version,_candidate=manuscript_proposals.proposal_version(turn)
            if version:
                event['proposal_read']=proposal_navigation.handle(project,{'view':'preview','id':turn_id,'proposal_version':version})
                event['application_boundary']='Unapplied proposal; independent review and human manuscript Apply remain separate.'
        event['acceptance'] = _acceptance(root, project, task, intent, turn_id,read_context=read_context)
        event['continuation_work_id'] = latest.get('continuation_work_id')
    else:
        event.update(running=False, result={'available': False}, acceptance=_acceptance(root, project, task, intent, None,read_context=read_context), continuation_work_id=None)
    continued = next((row for row in reversed(history) if row['state'] == 'CONTINUED'), None)
    event['parent_return'] = {'state': latest['state'] if latest['state'] in ('PENDING_PARENT', 'CONTINUED', 'PARENT_REFUSED') else None,
                              'attempts': max((row.get('return_attempts', 0) for row in history), default=0),
                              'deferrals': max((row.get('return_deferrals', 0) for row in history), default=0),
                              'continuation_turn': continued.get('continuation_turn') if continued else None,
                              'cost': continued.get('cost') if continued else None}
    route = ((intent.get('continuation') or {}).get('route') or {})
    if latest['state'] not in TERMINAL or (latest['state'] in ('RESULT', 'PENDING_PARENT') and route.get('admit_idle')):
        event['recovery'] = {'operation': 'work_delivery', 'payload': {'action': 'recover', 'event_id': event_id}}
    return copy.deepcopy(event)


def cut(task: dict, root, *, read_context=None) -> str:
    """The local owner cut of the delivery view: every attached row's identity (id, state, ts), the review phases, and the
    CANONICAL Work basis the acceptance is read against (project_work._work_basis: the Work's own scope with its containing
    context), read with the same root as the page; a goal/scope update, an append or a standing change moves it (J-R5-R1)."""
    from laplace.work import project_work
    basis, issue = project_work._work_basis(_read_tasks(root,task['project'],read_context), task['id'])
    return _digest({'deliveries': [(row.get('id'), row.get('state'), row.get('ts')) for row in task.get('deliveries') or ()],
                    'phases': [(row.get('id'), row.get('phase'), row.get('verdict')) for row in task.get('phases') or ()],
                    'basis': {'revision': basis.get('revision'), 'scope_revision': basis.get('scope_revision'), 'issue': issue}, 'status': task.get('status')})


def facet(task: dict, root, *, offset: int = 0, limit: int = PAGE,read_context=None) -> dict | None:
    """The Work detail's delivery facet: bounded pages of approved recipients and events (latest first); the next page is
    one exact read (work_delivery status) pinned to this view's cut."""
    from laplace.work.feedback_route import handle_read
    if not task.get('deliveries'):
        return None
    context={} if read_context is None else read_context
    pinned = cut(task, root,read_context=context)
    bindings = {}
    for row in _rows(task, BINDING):
        bindings[row['id']] = row
    event_ids = list(dict.fromkeys(row['id'] for row in _rows(task, EVENT)))[::-1]
    page = event_ids[offset:offset + limit]
    return {'cut': pinned, 'recipients': [_public_binding(row) for row in list(bindings.values())[-16:]], 'recipients_total': len(bindings),
            'events': [_facet_event(root, task['project'], task, event_id,read_context=context) for event_id in page],
            'events_total': len(event_ids), 'offset': offset, 'limit': limit,
            'next_read': handle_read(task['project'],
                {'action': 'status', 'work_id': task['id'], 'offset': offset + limit, 'limit': limit, 'cut': pinned})
            if offset + limit < len(event_ids) else None}


def geometry_observation(root,project,work_id,*,event_id=None,read_context=None):
    """Bounded delivery metadata; an intent is not an admitted route.

    Only the selected Writing index coordinates establish an actual turn. This
    projection never folds or opens recipient replies to draw a topology edge.
    """
    from laplace.work import project_work
    from laplace.writing import records
    from laplace.work.feedback_route import handle_read
    context={} if read_context is None else read_context
    _tasks,task=_task_for(root,project,work_id,read_context=context)
    key=('work_delivery.writing_index',str(Path(root).resolve()))
    if key not in context:context[key]=records.index(root)
    index=context[key];turns=[row for row in index.by_project.get(project,()) if row.get('record')=='writing-turn']
    ids=list(dict.fromkeys(row['id'] for row in _rows(task,EVENT)))[::-1]
    known=len(ids)
    if event_id is not None:
        if event_id not in ids:raise ValueError('Unknown delivery event in the selected Work.')
        ids=[event_id]
    events=[];basis_rows=[]
    for event_id in ids:
        history=_history(task,event_id);intent,latest=history[0],history[-1]
        coordinates=next((r for r in reversed(history) if r.get('session_id')),None)
        sid=coordinates.get('session_id') if coordinates else None
        tid=next((r.get('turn_id') for r in reversed(history) if r.get('turn_id')),None)
        matches=[r for r in turns if sid and r.get('project')==project and r.get('session_id')==sid and r.get('request_id')==event_id
            and (tid is None or r.get('id')==tid)]
        verified=matches[0] if len(matches)==1 else None
        observed={'event_id':event_id,'state':latest['state'],
            'history':[(r.get('id'),r.get('state'),r.get('ts'),r.get('session_id'),r.get('turn_id')) for r in history],
            'turn':{k:verified.get(k) for k in ('id','project','session_id','request_id')} if verified else None}
        basis= _digest(observed);basis_rows.append(basis)
        if len(events)>=PAGE:continue
        events.append({'id':event_id,'state':latest['state'],
            'title':intent['recipient'].get('label') or intent.get('workflow_execution',{}).get('effect') or intent.get('obligation_id') or 'Delivery',
            'ts':latest.get('ts'),'basis':basis,'admitted':verified is not None,
            'admission_observation':'VERIFIED_WRITING_TURN' if verified else 'UNCONFIRMED_NO_MATCHING_WRITING_TURN',
            'session_id':verified.get('session_id') if verified else sid,'turn_id':verified.get('id') if verified else tid,
            'read':handle_read(project,{'action':'status','event_id':event_id})})
    return copy.deepcopy({'events':events,'coverage':{'state':'RECORDED_DELIVERY_METADATA','known':known,
        'selected_event':event_id,'omitted':max(0,known-len(events)),'meaning':'Pending intent and observed admitted route are separate; no reply body, acceptance or running state is inferred.'},
        'cut':_digest({'work_revision':project_work._task_revision(task),'events':basis_rows})})


def status(root: Path, project: str, payload: dict, door: dict, *, read_context=None) -> dict:
    context={} if read_context is None else read_context
    if payload.get('event_id'):
        task = _task_of_event(root, project, payload['event_id'],read_context=context)
        return {'event': _facet_event(root, project, task, payload['event_id'],read_context=context)}
    if payload.get('work_id'):
        from laplace.work import development_source
        _tasks, task = _task_for(root, project, payload['work_id'],read_context=context)
        development_source.admit_cut(project, task, payload, cut(task, root,read_context=context), 'work_delivery')
        return {'deliveries': facet(task, root, offset=int(payload.get('offset') or 0), limit=int(payload.get('limit') or PAGE),read_context=context)
                or {'cut': cut(task, root,read_context=context), 'recipients': [], 'recipients_total': 0, 'events': [], 'events_total': 0, 'offset': 0, 'limit': PAGE, 'next_read': None}}
    raise ValueError('work_delivery status names an event_id or a work_id.')


def handle(root: Path, project: str, payload: dict, door: dict) -> dict:
    from laplace.core import admission
    admission.admit_owner_payload('work_delivery', payload, contract(), project=project)
    action = payload.get('action')
    from laplace.writing import workflow_progression
    if action in workflow_progression.ACTIONS:
        return workflow_progression.handle(root, project, payload, door)
    from laplace.work import feedback_route, review_setup
    if action in review_setup.ACTIONS:return review_setup.handle(root,project,payload,door)
    if action in feedback_route.ACTIONS:return feedback_route.handle(root,project,payload,door)
    if action == 'bind':
        return bind(root, project, payload, door)
    if action == 'submit':
        return submit(root, project, payload, door)
    if action == 'continue':
        _require(payload, 'continue')
        from laplace.work import project_work_continuity
        return project_work_continuity.continue_intent(root, project, payload, door)
    if action == 'recover':
        return recover(root, project, payload, door)
    if action == 'status':
        return status(root, project, payload, door)
    raise ValueError('work_delivery action is bind, submit, continue, recover or status.')


def compose_origin(root,project,origin_receipt,route_spec,*,door):
    from laplace.work.feedback_route import compose_origin as compose
    return compose(root,project,origin_receipt,route_spec,door=door)


def origin_route_read(project,origin_ref,route_spec):
    """Pure descriptor for an exact saved comment's existing Work aggregate."""
    from laplace.work.feedback_route import origin_route_read as read
    return read(project,origin_ref,route_spec)
