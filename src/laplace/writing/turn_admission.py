"""TURN ADMISSION (S1 B1): an author request becomes one banked turn and one live job, in order.

start_turn/_start_turn (below) are the lifecycle entry; authoring_surface forwards them. Its sequence, unchanged from the monolith it replaces:

  prepare_request      shape only (text or queued work, size, mode, request id); no read.
  -- under the existing journal fold lock (records._fold._LOCK), every step below --
  reused_turn          an exact request id already admitted for this project/role/mode answers again.
  observation_budget_for  the connected-observation budget (an author's work-turn budget only).
  work_context         explicit Work context and its guards, a prepared storyboard's currentness; never an
                       inferred Work.
  admit_session        the existing session (project/role checked) or a new one through the session
                       owner (new_session, below); a working session refuses; explicit
                       provider/model/effort changes go through configure_session (below).
  native_continuation  whether the provider's native session may continue: an unsaved or pre-inference
                       previous reply, a changed or unproven native registration, or a changed operating
                       kernel each start a fresh native session (banked as a binding invalidation).
  deliver_context      authoring.build_context once; the delivery delta against the parts this session
                       already holds; the prompt (writing.turn_context.turn_prompt).
  bank_turn            the one writing-turn row (the delivered part baseline is its context_parts).
  register_job         the live job in writing.turn_jobs and the execution record in writing.child_hosts.

The result is a TurnLaunch: the immutable coordinates writing.turn_execution runs with. Nothing here
starts a provider or waits; session mutation stays with its owner and the journal with authoring_surface.
"""
from __future__ import annotations

DEFAULT_PROVIDER='codex'

import hashlib
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import time
# the provider SERVICE (laplace.writing.provider) is imported only where a turn's outward operation needs it (binding facts,
# effort truth before a run); admitting sessions, Work and context never loads it (standalone boundary, 2026-10-20)
from laplace.pipeline import registry
from laplace.writing import records as writing_records

MODES = ("discuss", "revise", "work", "review")
WORK_GUARDS = ("expected_work_scope_revision", "expected_dependency_revision")


@dataclass(frozen=True)
class TurnLaunch:
    """What one admitted turn runs with. Built once under the admission lock; never mutated."""
    root: Path
    project: str
    turn_id: str
    session_id: str
    mode: str
    session: Mapping[str, Any]
    operating_brief: Mapping[str, Any]
    contract_digest: str
    registration_signature: str
    prompt: str
    native_source_paths: frozenset
    queued_requests: tuple
    workspace_context: Mapping[str, Any]
    dispatch: Mapping[str, Any] | None = None
    connected_observation: Any = None
    work_id: str | None = None
    reader_profile: Mapping[str, Any] | None = None
    job: dict = field(default_factory=dict, compare=False)
    feedback_execution: Mapping[str, Any] | None = None
    source_execution: Mapping[str, Any] | None = None
    workflow_execution: Mapping[str, Any] | None = None


def native_write_admission(root: Path, project: str, mode: str, turn_id: str | None) -> dict:
    """Resolve this door's current authority from the existing turn/session and execution owners.

    A recorded turn alone is not live authority. No request JSON contributes these facts.
    Readers may show a local refusal; writers resolve again after waiting for their lock.
    """
    from laplace.writing import child_hosts
    refused = lambda code: {'permitted': False, 'code': code}
    try:
        records = writing_records.fold_records(root)
        turn = records['turns'].get(turn_id) or {}
        session = records['sessions'].get(turn.get('session_id')) or {}
        if not turn or turn.get('project') != project or session.get('project') != project:
            return refused('NATIVE_TURN_NOT_ADMITTED')
        if mode not in MODES or turn.get('mode') != mode:
            return refused('NATIVE_MODE_MISMATCH')
        if mode == 'review' or session.get('role', 'author') != 'author':
            return refused('NATIVE_READ_ONLY')
        if turn.get('reply'):
            return refused('NATIVE_TURN_FINISHED')
        execution = child_hosts.child_execution(root, session['id'])
        if (execution.get('state') != 'RUNNING' or execution.get('turn_id') != turn_id
                or execution.get('project') != project or execution.get('session_id') != session['id']):
            return refused('NATIVE_EXECUTION_UNAVAILABLE')
        return {'permitted': True, 'code': 'ADMITTED', 'turn_id': turn_id, 'session_id': session['id']}
    except (OSError, ValueError) as exc:
        return {**refused('NATIVE_EXECUTION_UNAVAILABLE'), 'reason': str(exc)[:300]}


def prepare_request(payload: Mapping[str, Any]) -> dict:
    """The request's own shape; nothing is read."""
    if any(key in payload for key in ('workflow_execution', 'workflow_event_id', 'workflow_reservation','workflow_input')):
        raise ValueError('Workflow execution membership comes only from its existing Work delivery reservation.')
    private_source = {key for key in payload if key.startswith('source_') and key != 'source_grant_id'}
    private_source.update(key for key in ('native_allowance', 'commission_id', 'allowance_revision',
        'max_admitted_native_invocations', 'max_app_admissions', 'max_sessions', 'wall_seconds',
        'original_parent_session_id') if key in payload)
    if private_source:
        raise ValueError('A turn request cannot supply private Source execution controls: ' + ', '.join(sorted(private_source)))
    source_grant_id = payload.get('source_grant_id')
    if 'source_grant_id' in payload and (not isinstance(source_grant_id, str) or not source_grant_id.strip()):
        raise ValueError('source_grant_id must name one exact existing Source grant.')
    if source_grant_id and (payload.get('profile') or payload.get('mode') == 'review'):
        raise ValueError('A Source selector belongs to the original ordinary author session, not a reader or reviewer.')
    if 'profile' in payload:
        from laplace.writing.sealed_reader import start_request
        return start_request(dict(payload))
    text = str(payload.get("text") or "").strip()
    queued_values = payload.get("queued_work_ids") or []
    if not text and not queued_values:
        raise ValueError("Write a message first.")
    if len(text) > 100_000:
        raise ValueError("The message is too large; attach the source to the project and refer to it.")
    mode = payload.get("mode", "discuss")
    if mode not in MODES:
        raise ValueError("Unknown writing mode.")
    action_intent = submission_intent(payload) if has_selected_action(payload) else None
    return {**({'source_grant_id': source_grant_id} if source_grant_id else {}), **({'action_submission_intent_sha256': action_intent} if action_intent else {}),
            "project": str(payload.get("project") or ""), "text": text, "queued_values": queued_values,
            "session_id": str(payload.get("session_id") or ""), "mode": mode,
            "request_id": str(payload.get("request_id") or uuid.uuid4().hex)}


def has_selected_action(payload):
    context = payload.get('workspace_context')
    return isinstance(context, Mapping) and 'workflow_action' in context


def submission_intent(payload):
    """Exact JSON wire intent for this action path; legacy requests keep their contract."""
    import json
    from laplace.core.identity import canonical_digest
    allowed = {'project', 'text', 'queued_work_ids', 'session_id', 'mode', 'provider', 'model', 'effort',
               'request_id', 'selection', 'work_id', *WORK_GUARDS, 'connected_observation_seconds', 'workspace_context'}
    if set(payload) - allowed:
        raise ValueError('Selected action submission contains unsupported fields.')
    if not isinstance(payload.get('request_id'), str) or not 1 <= len(payload['request_id']) <= 160:
        raise ValueError('Selected action requires a retained parent submission request_id.')
    from laplace.writing.workflow_dispatch import action_input
    action_input(payload['workspace_context']['workflow_action'])
    # JSON round-trip excludes Python-only values/nonfinite numbers. Field presence
    # and null remain exact; no default filling or text trimming changes the seal.
    value = {key: item for key, item in payload.items() if key != 'request_id'}
    value = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    return canonical_digest(value)


def action_submission_read(project, session_id, request_id):
    from urllib.parse import urlencode
    return {'http': {'method': 'GET', 'url': '/authoring/session-turn?' + urlencode({
        'view': 'request', 'project': project, 'session_id': session_id, 'request_id': request_id})}}


def _submission_metadata(turn):
    return {'request_id': turn['request_id'], 'intent_sha256': turn['action_submission_intent_sha256'],
            'read': action_submission_read(turn['project'], turn['session_id'], turn['request_id'])}


def _settings_read(project,session_id):
    from laplace.writing.session_settings import handle
    return handle(project,{'action':'read','target':{'kind':'conversation','session_id':session_id}})


def reused_turn(records: Mapping[str, Any], request: Mapping[str, Any]) -> dict | None:
    """An exact request id already admitted for this project answers again (same role and mode only)."""
    for old in records["turns"].values():
        if old.get("request_id") == request["request_id"] and old.get("project") == request["project"]:
            if old.get('reader_profile'):
                raise ValueError('This request belongs to a sealed reader attempt, not an ordinary turn.')
            if old.get('source_grant_id') or request.get('source_grant_id'):
                if old.get('source_grant_id') != request.get('source_grant_id') or request.get('session_id') != old.get('session_id'):
                    raise ValueError('Source admission request identity belongs to a different selector or original session.')
            prior_session = records["sessions"].get(old.get("session_id")) or {}
            expected_role = "review" if request["mode"] == "review" else "author"
            if old.get("mode") != request["mode"] or prior_session.get("role", "author") != expected_role:
                raise ValueError("Request identity belongs to a different conversation role or mode.")
            if old.get('action_submission_intent_sha256') or request.get('action_submission_intent_sha256'):
                if old.get('action_submission_intent_sha256') != request.get('action_submission_intent_sha256'):
                    raise ValueError('Selected action submission intent changed under this request_id.')
                return {'turn_id': old['id'], 'session_id': old['session_id'], 'reused': True,
                        'action_submission': _submission_metadata(old),'settings_read':_settings_read(old['project'],old['session_id'])}
            return {"turn_id": old["id"], "session_id": old["session_id"], "reused": True,'settings_read':_settings_read(old['project'],old['session_id'])}
    return None


def observation_budget_for(payload: Mapping[str, Any], request: Mapping[str, Any], records: Mapping[str, Any],
                           dispatch: Mapping[str, Any] | None) -> Any:
    """The connected dispatch-observation budget: an author's own work-turn budget, nothing else."""
    from laplace.writing.dispatch_parent import observation_budget
    mode, ident, project = request["mode"], request["session_id"], request["project"]
    connected = observation_budget(payload.get('connected_observation_seconds'))
    if connected and (dispatch or mode != 'work'):
        raise ValueError('Connected dispatch observation is an explicit author work-turn budget, not a child/review control.')
    observed_session = records['sessions'].get(ident) or {}
    if connected and ident and (observed_session.get('role', 'author') != 'author' or observed_session.get('dispatch_id')):
        raise ValueError('Connected observation requires an actual author parent session, not a dispatched child or reviewer.')
    return connected


def work_context(root: Path, payload: Mapping[str, Any], request: Mapping[str, Any], records: Mapping[str, Any],
                 dispatch: Mapping[str, Any] | None) -> dict | None:
    """The explicit Work this turn carries, observed now under its guards; never inferred."""
    if "work_id" in payload and (not isinstance(payload["work_id"], str) or not payload["work_id"].strip()):
        raise ValueError("work_id must be a nonempty exact Work identity.")
    context = None
    if payload.get("work_id"):
        from laplace.work import project_work
        context = project_work.context(request["project"], payload["work_id"], root, require_observation=True,
                                       **{key: payload.get(key) for key in WORK_GUARDS})
    elif any(key in payload for key in WORK_GUARDS):
        raise ValueError("Work observation guards require an explicit work_id.")
    if context and context.get("prepared_storyboard"):
        from laplace.writing.prepared_work import require_current
        ident = request["session_id"]
        require_current(request["project"], root, {"id": context["work_id"], "prepared_storyboard": context["prepared_storyboard"]},
                        mode=request["mode"], session=records["sessions"].get(ident) if ident else None, dispatch=dispatch)
    return context


def admit_session(root: Path, payload: Mapping[str, Any], request: Mapping[str, Any],
                  records: Mapping[str, Any]) -> tuple[dict, str]:
    """(session, session id): the session this turn continues (checked) or opens (through the session owner)."""
    project, mode, ident = request["project"], request["mode"], request["session_id"]
    if ident:
        session = records["sessions"].get(ident)
        if not session or session["project"] != project:
            raise ValueError("The session does not belong to this project.")
        if session.get('reader_profile'):
            raise ValueError('This sealed reader is one attempt. Prepare a fresh packet instead of a follow-up.')
        if mode == "review" and session.get("role") != "review":
            raise ValueError("Independent review needs a fresh review conversation.")
        if session.get("role") == "review" and mode != "review":
            raise ValueError("Keep the independent review intact; continue it in review mode or start a writing conversation.")
    else:
        # No model and no effort literal here: an omitted model or effort is resolved from the role's tier
        # (project_work.session_choice), so this door cannot hold a default of its own. The provider name is
        # not a model choice.
        session = new_session(root, project, str(payload.get("provider") or DEFAULT_PROVIDER),
                                      str(payload.get("model") or ""), str(payload.get("effort") or ""),
                                      role="review" if mode == "review" else "author")
        ident = session["id"]
    execution = child_hosts.child_execution(root, ident)
    busy = (any(job["session_id"] == ident and not job["done"] for job in turn_jobs._JOBS.values())
            or execution.get("state") in {"ORPHANED", "UNKNOWN-OWNERSHIP"}
            or (not turn_jobs.child_host() and execution.get("state") in {"STARTING", "WAITING", "RUNNING"}))
    if busy:
        raise ValueError("This session is working. Steer it, stop it, or wait for its reply.")
    if payload.get("session_id") and any(key in payload for key in ("provider", "model", "effort")):
        return configure_session(root, project, ident, dict(payload))["session"], ident
    return dict(session), ident


def native_continuation(session: Mapping[str, Any], previous_turn: Mapping[str, Any] | None,
                        operating_brief: Mapping[str, Any]) -> tuple[dict, dict | None, dict | None]:
    """(session as it will run, migration reason or None, registration compatibility or None).

    A native provider session continues only when the previous turn saved a terminal reply that reached
    inference, the native tool registration is the same (or provably compatible) and the session-invariant
    operating kernel is unchanged; otherwise the native id is dropped and a fresh native session starts."""
    session = dict(session)
    migration = session.get("pending_context")
    compatibility = None
    signature = operating_brief["native_registration_signature"]
    if not session.get("native_id"):
        return session, migration, compatibility
    previous_reply = (previous_turn or {}).get("reply")
    if not migration and previous_turn and not isinstance(previous_reply, Mapping):
        migration = {"reason": "previous turn has no saved terminal reply", "previous_native_id": session["native_id"]}
    elif (not migration and isinstance(previous_reply, Mapping) and previous_reply.get("status") == "failed"
          and previous_reply.get("provider_stage") != "inference"):
        migration = {"reason": "previous turn ended before inference or its delivery is unproven",
                     "previous_native_id": session["native_id"]}
    saved_signature = session.get("native_registration_signature")
    if saved_signature is None:
        compatibility = turn_context._legacy_registration_compatibility(session, previous_turn, operating_brief)
    elif saved_signature != signature:
        compatibility = {"compatible": False, "basis": "native registration signature changed",
                         "saved": saved_signature, "current": signature}
    if compatibility is not None and not compatibility["compatible"]:
        migration = {"reason": "native tool registration is incompatible or unproven",
                     "previous_native_id": session["native_id"], "registration_compatibility": compatibility}
    if not migration:
        prior_orientation = (previous_turn or {}).get("orientation") or {}
        kernel_members = ("tool_contract_digest", "shared_rules_revision", "capability_guidance_revision")
        kernel_changed = [key for key in kernel_members if prior_orientation.get(key) != operating_brief.get(key)]
        if kernel_changed:
            migration = {"reason": "session-invariant operating kernel changed or is unproven",
                         "previous_native_id": session["native_id"], "changed_kernel_members": kernel_changed}
    if migration:
        session.update(native_id=None, tool_contract_digest=operating_brief["tool_contract_digest"],
                       native_registration_signature=signature)
    else:
        session["native_registration_signature"] = signature
    return session, migration, compatibility


def deliver_context(root: Path, request: Mapping[str, Any], session: Mapping[str, Any], records: Mapping[str, Any], *,
                    selection: Any, migration: Mapping[str, Any] | None, operating_brief: Mapping[str, Any],
                    previous_turn: Mapping[str, Any] | None) -> tuple[dict, dict, set]:
    """(context, delivery, native source paths): one build_context, delivered as a delta against the parts
    this native session already holds (nothing is withheld when it does not continue)."""
    from laplace.pipeline import authoring
    retained = bool(session.get("native_id")) and not migration
    context = authoring.build_context(request["project"], selection, repo_root=root,
                                      include_guidance=False, include_orientation=True)
    held = dict((previous_turn or {}).get("context_parts") or {}) if retained else {}
    delivery = turn_context.without_already_delivered(context.get("parts") or [], held,
                                         brief_delta=((previous_turn or {}).get("orientation"), operating_brief),
                                         body_delivered=not retained)
    paths = set()
    for dependency in (context.get("dependencies") or {}).get("source_dependencies") or []:
        if isinstance(dependency, dict) and isinstance(dependency.get("file"), str):
            paths.add(str((root / dependency["file"]).resolve()))
    document_root = (context.get("document") or {}).get("root")
    if isinstance(document_root, str):
        paths.add(str((root / document_root).resolve()))
    return context, delivery, paths


def _source_allowance_snapshot(root, attachment):
    """One owner-derived per-turn task line; not operating/kernel identity or authority."""
    from laplace.writing import source_execution
    standing = source_execution.status(root, attachment)
    keys = ('commission_id','state','remaining','app_remaining','session_remaining','deadline_at')
    if any(key not in standing for key in keys) or not isinstance(standing['deadline_at'], str):
        raise ValueError('Source admission allowance snapshot is unavailable.')
    basis = {key: standing[key] for key in keys}
    text = ('Source allowance (admission-time snapshot): commission ' + basis['commission_id']
            + '; grant ' + attachment['source_grant_id'] + '; remaining admitted native calls '
            + str(basis['remaining']) + ', app admissions ' + str(basis['app_remaining'])
            + ', sessions ' + str(basis['session_remaining']) + '; deadline ' + basis['deadline_at']
            + '. Source write authority remains separate; native result envelopes report current standing.')
    return {'text': text, 'basis': basis}


def bank_turn(root: Path, launch_facts: Mapping[str, Any]) -> None:
    """The one writing-turn row of an admitted turn (see the field notes below)."""
    facts = launch_facts
    session, operating_brief, work, context = facts["session"], facts["operating_brief"], facts["work"], facts["context"]
    # The two members that distinguish a dispatched child's turn from the parent's. The fold stores a
    # writing-turn row WHOLE, so they reach every reader of a turn with no fold change at all; they are
    # written only when this turn IS a child, so an ordinary turn's banked bytes are byte-identical to before.
    # They are NOT request members: they arrive on the internal `dispatch` argument that `launch_dispatch`
    # passes to the turn it starts (and that the one-shot child host receives through its own entry's
    # `--dispatch-id`/`--parent-turn-id`), so no caller of `/authoring/turn` can set them.
    dispatch_members = {}
    for member in ("parent_turn_id", "dispatch_id"):
        if (facts["dispatch"] or {}).get(member):
            dispatch_members[member] = str(facts["dispatch"][member])
    writing_records.bank(root, {"record": "writing-turn", "id": facts["turn_id"], "session_id": facts["session_id"],
                         **({'reader_profile':facts['reader_profile'],'reader_intent_sha256':facts['reader_intent_sha256']}
                            if facts.get('reader_profile') else {}),
                         **({'action_submission_intent_sha256': facts['action_submission_intent_sha256']}
                            if facts.get('action_submission_intent_sha256') else {}),
                         **dispatch_members,
                         **({'feedback_execution':facts['feedback_execution']} if facts.get('feedback_execution') else {}),
                         **({'workflow_execution':facts['workflow_execution']} if facts.get('workflow_execution') else {}),
                         **({'workflow_input':facts['workflow_input']} if facts.get('workflow_input') else {}),
                         **({'source_execution':facts['source_execution'], 'source_admission_id':facts['source_admission_id'],
                             'source_allowance_snapshot':facts['source_allowance_snapshot']} if facts.get('source_execution') else {}),
                         **({'source_grant_id':facts['source_grant_id']} if facts.get('source_grant_id') else {}),
                         "project": facts["project"], "request_id": facts["request_id"], "text": facts["text"],
                         "mode": facts["mode"],
                         **({'connected_observation': facts["connected"]} if facts["connected"] else {}),
                         "queued_work_ids": [row["id"] for row in facts["queued"]],
                         "queued_requests": facts["queued"],
                         **({"work_id": work["work_id"], "work_basis": work["work_basis"]} if work else {}),
                         "selection": facts["selection"], "consumed": context.get("consumed"),
                         "unsaved_draft": facts["unsaved_draft"],
                         "provider_settings": {key: session[key] for key in ("provider", "model", "effort")},
                         "workspace_context": facts["workspace_context"],
                         "operating_brief": {"schema_version": operating_brief["schema_version"],
                             "digest": operating_brief["digest"], "tool_contract_digest": operating_brief["tool_contract_digest"],
                             "writing_style_revision": operating_brief["writing_style"]["revision"],
                             "writing_style_profile": operating_brief["writing_style"]["selected_profile"],
                             "project_protocol_revision": operating_brief["project_protocol"]["revision"],
                             "permissions": operating_brief["permissions"]},
                         "orientation": turn_context._orientation_snapshot(operating_brief),
                         "native_contract_migration": facts["migration"],
                         "native_registration_compatibility": facts["compatibility"],
                         "context_id": context.get("context_id"), "dependencies": context.get("dependencies"),
                         "document": context.get("document"),
                         "science_context_digest": context.get("science_context_digest"),
                         # The conversation's part baseline: ONE home for what this session already holds,
                         # read by the next turn's delta and advanced by `_refresh_owned_context` when a write
                         # moves the owned context. A part's token is the digest of the text DELIVERED when it
                         # was delivered, so no later read of the project can reproduce it. `context_altitude`
                         # (authoring.delivery_altitude(selection)) and `context_withheld` (the parts whose
                         # token equals the previous baseline) are derivable and are not stored.
                         "context_parts": facts["held"],
                         "context_sha256": hashlib.sha256(facts["prompt"].encode()).hexdigest()})


def register_job(root: Path, launch: TurnLaunch, request_text: str) -> None:
    from laplace.writing import provider as writing_provider   # outward: the advertised context window of the bound model
    """Fill the launch's live job, record the RUNNING execution (writing.child_hosts) and register the job in
    writing.turn_jobs: the SAME dict object is the registry entry, the stream's source and execution's state."""
    session, dispatch, job = launch.session, launch.dispatch or {}, launch.job
    job.update({"id": launch.turn_id, "session_id": launch.session_id, "root": root, "text": "", "progress": "Connecting…",
           "project": launch.project, "request_label": " ".join(request_text.split())[:200],
           **({"work_id": launch.work_id} if launch.work_id else {}),
           "provider_name": session.get("provider"),
           "events": [], "condition": threading.Condition(), "observation_lock": threading.Lock(), "done": False,
           "provider": None, "usage": None,
           "context_window_advertised": writing_provider.context_window_advertised(session["provider"], session["model"]),
           "context_window_effective": None, "context_tokens_used": None})
    if launch.source_execution:
        job['source_execution'] = dict(launch.source_execution)
    job["execution_path"] = child_hosts._host_path(root, launch.session_id)
    child_hosts._begin_child_execution(root, launch.session_id, {"state": "RUNNING", "turn_id": launch.turn_id,
        "session_id": launch.session_id, "project": launch.project, "work_id": launch.work_id,
        "dispatch_id": dispatch.get("dispatch_id"), "parent_turn_id": dispatch.get("parent_turn_id"),
        **({"source_execution": dict(launch.source_execution)} if launch.source_execution else {}),
        **({"workflow_execution": dict(launch.workflow_execution)} if launch.workflow_execution else {}),
        "host": child_hosts._process_identity(), "provider_process": None, "provider_processes": [],
        "provider_inference_started": False, "control_capabilities": {"can_interrupt": True, "can_steer": False},
        "remote_steering": bool(launch.dispatch), "last_control": None})
    turn_jobs._JOBS[launch.turn_id] = job


def admit(root: Path, payload: Mapping[str, Any], request: Mapping[str, Any], records: Mapping[str, Any],
          dispatch: Mapping[str, Any] | None, *, reader_operator=None, delivery_event=None, source_reservation=None, source_event=None, workflow_event=None) -> TurnLaunch:
    """Every admission step, in the monolith's order, under the caller's fold lock."""
    from laplace.writing import operating as writing_operating
    if request.get('profile'):
        if delivery_event or source_reservation or workflow_event:raise ValueError('A Work review or Source execution is not a sealed-reader admission.')
        if dispatch:raise ValueError('A sealed reader is not a dispatched child or resumed session.')
        from laplace.writing.sealed_reader import admit as admit_reader
        return admit_reader(root,payload,request,records,operator=reader_operator)
    project, mode = request["project"], request["mode"]
    connected = observation_budget_for(payload, request, records, dispatch)
    queued = turn_context._queued_requests(project, request["queued_values"], root)
    source_selection, unsaved_draft = turn_context._selection_draft(payload.get("selection"))
    workspace = turn_context._workspace_context(root, project, payload.get("workspace_context"))
    work = work_context(root, payload, request, records, dispatch)
    source_attachment = None
    if request.get('source_grant_id'):
        if dispatch or source_reservation:
            raise ValueError('Dispatched and inherited executions cannot self-attach with a Source selector.')
        from laplace.writing import source_execution
        source_attachment = source_execution.prepare_initial(root, project, request['session_id'], request['source_grant_id'])
        if source_attachment is None:
            raise ValueError('The selected Source grant has no admitted native allowance.')
    elif source_reservation:
        if dispatch:
            raise ValueError('A dispatched child cannot acquire a Source commission through an author reservation.')
        source_attachment = source_reservation['attachment']
    if source_attachment and (not work or work['work_id'] != source_attachment['work_id'] or source_attachment['project'] != project):
        raise ValueError('Source execution requires its exact explicitly inspected Work and project.')
    if 'workflow_action' in workspace:
        if dispatch:
            raise ValueError('Selected workflow actions require an ordinary author parent turn.')
        from laplace.writing.workflow_dispatch import resolve_action_context
        workspace['workflow_action'] = resolve_action_context(root, project, workspace['workflow_action'],
            session_id=request['session_id'], mode=mode, work_id=payload.get('work_id'),
            work_guards={key: payload.get(key) for key in WORK_GUARDS})
    session, ident = admit_session(root, payload, request, records)
    workflow_execution = None
    if workflow_event:
        from laplace.writing import workflow_progression
        workflow_execution = workflow_progression.admission_context(root, project, workflow_event, ident)
    if source_attachment:
        from laplace.writing import source_execution
        if source_event:
            from laplace.work.work_delivery import source_admission
            source_reservation = source_admission(root, project, source_event, ident, source_reservation)
        if source_reservation is None:
            source_reservation = source_execution.reserve_app(root, source_attachment, request['request_id'], session_id=ident, role='parent')
        if source_reservation.get('session_id') != ident:
            raise ValueError('Source admission reservation belongs to another session.')
        if session.get('source_execution') != source_attachment:
            session = {**session, 'source_execution': dict(source_attachment), 'source_admission_id': source_reservation['admission_id']}
            writing_records.bank(root, session)
        source_reservation = source_execution.bind_app(root, source_reservation, ident)
    if mode != "review" and session.get("role", "author") == "author" and not dispatch:
        # the authorised automatic parent continuation (writing.work_delivery): a recipient result addressed to THIS
        # session by the delivery it submitted joins its next turn's queued requests, bounded; nothing polls
        from laplace.work import work_delivery
        queued = queued + work_delivery.pending_continuations(root, project, ident, exclude={row["id"] for row in queued})
    selection = turn_context.context_selection(source_selection, work, workspace)
    operating_brief = writing_operating.build(project, mode, root,
                                              {key: value for key, value in workspace.items() if key != 'workflow_action'}, session_id=ident,
                                              dispatch_id=(dispatch or {}).get('dispatch_id'))
    previous_turn = turn_context._latest_session_turn(records, ident)
    session, migration, compatibility = native_continuation(session, previous_turn, operating_brief)
    if migration and session.get("native_id") is None:
        # The invalidation occasion of the SAME binding row through the same producer: `migration` carries
        # this occasion's own facts, so a new migration key is a TypeError, not an unreadable row shape.
        writing_records.bank(root, binding_row(ident, tool_contract_digest=operating_brief["tool_contract_digest"],
                                                native_registration_signature=operating_brief["native_registration_signature"],
                                                model=session.get("model"), **migration))
    context, delivery, paths = deliver_context(root, request, session, records, selection=selection, migration=migration,
                                               operating_brief=operating_brief, previous_turn=previous_turn)
    prompt = turn_context.turn_prompt(root, delivery["prompt"], records, ident=ident, mode=mode, migration=migration,
                         source_selection=source_selection, unsaved_draft=unsaved_draft, text=request["text"],
                         queued=queued, work=work, workspace=workspace, framing=context["prompt_framing"],
                         dispatch=dispatch, project=project)
    workflow_input=None
    if workflow_execution and workflow_execution.get('schema_version')=='laplace.research-workflow-run/1':
        from laplace.writing.workflow_progression import private_input
        selected=private_input(root,project,workflow_event)
        prompt=prompt+writing_operating.BLOCK_JOIN+'OWNER-SELECTED WORKFLOW CONTEXT\n'+selected['text']
        workflow_input=selected['receipt']
    source_snapshot = _source_allowance_snapshot(root, source_attachment) if source_attachment else None
    if source_snapshot:
        prompt = prompt + writing_operating.BLOCK_JOIN + source_snapshot['text']
    reserved_turn = None
    if dispatch:
        from laplace.writing.dispatch_execution import continuation_turn_id
        reserved_turn = continuation_turn_id(root, project, ident, request['request_id'], dispatch, admitted_session=session)
    turn_id = reserved_turn or "WT-" + uuid.uuid4().hex
    feedback_execution=None
    if delivery_event:
        if dispatch or mode!='review' or session.get('role')!='review':raise ValueError('Feedback execution is its reserved review session only.')
        from laplace.work.feedback_route import admit_execution
        feedback_execution=admit_execution(root,project,delivery_event,ident)
    bank_turn(root, {"turn_id": turn_id, "session_id": ident, "project": project, "request_id": request["request_id"],
                     **({'action_submission_intent_sha256': request['action_submission_intent_sha256']}
                        if request.get('action_submission_intent_sha256') else {}),
                     "text": request["text"], "mode": mode, "connected": connected, "queued": queued, "work": work,
                     "selection": selection, "context": context, "unsaved_draft": unsaved_draft, "session": session,
                     "workspace_context": workspace, "operating_brief": operating_brief, "migration": migration,
                     "compatibility": compatibility, "held": delivery["held"], "prompt": prompt, "dispatch": dispatch,
                     'feedback_execution':feedback_execution,
                     **({'workflow_execution':workflow_execution} if workflow_execution else {}),
                     **({'workflow_input':workflow_input} if workflow_input else {}),
                     **({'source_execution':source_attachment,'source_admission_id':source_reservation['admission_id'],
                         'source_allowance_snapshot':source_snapshot} if source_attachment else {}),
                     **({'source_grant_id':request['source_grant_id']} if request.get('source_grant_id') else {})})
    if source_attachment:
        source_execution.bind_app(root, source_reservation, ident, turn_id)
    launch = TurnLaunch(root=root, project=project, turn_id=turn_id, session_id=ident, mode=mode, session=session,
                        operating_brief=operating_brief, contract_digest=operating_brief["tool_contract_digest"],
                        registration_signature=operating_brief["native_registration_signature"], prompt=prompt,
                        native_source_paths=frozenset(paths), queued_requests=tuple(queued), workspace_context=workspace,
                        dispatch=dispatch, connected_observation=connected,
                        feedback_execution=feedback_execution, source_execution=source_attachment, workflow_execution=workflow_execution,
                        work_id=work.get("work_id") if work else None)
    register_job(root, launch, request["text"])
    return launch


from laplace.writing import child_hosts  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_context  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_jobs  # noqa: E402  (cycle-safe: imported last)


# ---------------------------------------------------------------- the session owner and THE LIFECYCLE ENTRY
# A conversation opens and changes its settings here; start_turn admits one author turn (above) and hands the launch to
# writing.turn_execution. Moved from authoring_surface (core consolidation, family 2); the facade forwards the names.

def binding_row(session_id: str, event: Mapping[str, Any] | None = None, *,
                tool_contract_digest: str, native_registration_signature: str,
                operating_brief_digest: str | None = None, model: str | None = None,
                reason: str | None = None, previous_native_id: str | None = None,
                registration_compatibility: Mapping[str, Any] | None = None,
                changed_kernel_members: list | None = None) -> dict:
    """THE writing-binding row, on both of its occasions: a session bound, or unbound.

    ONE producer for the record name, because this row is the only place a later reader --
    the frontend, a harness, the next packet of this wave -- can learn what a provider
    session was ACTUALLY given, as opposed to what the contract declares it should be, and
    three sites spelling one record name were three shapes of it.

    A BOUND session passes the `session` event the transport already emits, which carries
    that runtime's own observation of its process (src/laplace/writing_provider.py:954 for
    the Claude runtime's `system/init` tool and MCP inventory with its cwd, :806 for the
    Codex thread's cwd and its pre-thread MCP preflight).  An INVALIDATION passes no event
    and names why the binding fell: the native id is cleared and the occasion's own facts
    ride as the keyword arguments below -- which is why they are keywords and not a dict,
    so a caller inventing a new field is a TypeError here rather than a fourth row shape
    in the journal.  A field that is not this occasion's is ABSENT from the row, never
    present and null: `process` on a refusal would read as "this session was observed to
    be given nothing".
    """
    row = {"record": "writing-binding", "id": "WB-" + uuid.uuid4().hex,
           "session_id": session_id, "native_id": (event or {}).get("native_id"),
           "tool_contract_digest": tool_contract_digest,
           "native_registration_signature": native_registration_signature,
           "model": (event or {}).get("model") if event is not None else model}
    if event is not None:
        row.update({"operating_brief_digest": operating_brief_digest,
                    "provider": event.get("provider"), "process": event.get("process")})
        if event.get("delivery_receipt") is not None:
            from laplace.writing import operating as writing_operating
            row["delivery_receipt_projection"]=writing_operating.delivery_receipt_projection(event["delivery_receipt"])
    for key, value in (("reason", reason), ("previous_native_id", previous_native_id),
                       ("registration_compatibility", registration_compatibility),
                       ("changed_kernel_members", changed_kernel_members)):
        if value is not None:
            row[key] = value
    return row


def new_session(root: Path, project: str, provider: str, model: str, effort: str, role: str = "author",
                *, model_role: str = "session", dispatch_id: str | None = None,
                packet: str | None = None, reader_profile: Mapping[str, Any] | None = None,
                source_reservation: Mapping[str, Any] | None = None, workflow_event_id: str | None = None) -> dict:
    root = Path(root).resolve()
    if registry.resolve(project, repo_root=root) is None:
        raise ValueError("Select a registered project.")
    if provider not in ("codex", "claude"):
        raise ValueError("Select Codex or Claude.")
    # The conversation's model choice is RESOLVED here, through the one tier table, instead
    # of being whatever this door's caller typed: `role` above is the CONVERSATION's role
    # (author or review), and the model-choice role of an in-app conversation is `session`
    # -- the author's law, the interfacing session runs at the highest tier.  The row carries
    # `model_source` and `tier` so a reader can ask WHY this conversation has this model.
    from laplace.work import project_work
    # `model_role` is the MODEL-CHOICE role, which is not the conversation role above: an
    # in-app conversation resolves at `session` (the apex, the author's law), and a DISPATCHED
    # child resolves at `worker` or `judge` through the same table (pipeline/schema.py:752
    # role_model).  One argument, threaded from launch_dispatch; no model literal anywhere.
    if reader_profile:
        from laplace.writing.sealed_reader import settings
        choice=settings(root,model,effort)
    else:
        choice = project_work.session_choice(
            project, {"provider": provider, "model": model, "effort": effort}, root, role=model_role,include_provenance=True)
    from laplace.writing import source_execution
    source_execution.guard_spawn(root, project, reservation=source_reservation)
    if workflow_event_id:
        from laplace.work import work_delivery
        task = work_delivery._task_of_event(root, project, workflow_event_id)
        history = work_delivery._history(task, workflow_event_id)
        if (not history[0].get('workflow_execution') and history[0]['recipient'].get('effect')!='proposal-writer') or history[-1]['state'] != 'RESERVED':
            raise ValueError('Workflow session requires its actual durable event reservation.')
        from laplace.writing.workflow_progression import _validate_event,_validate_general_effect
        (_validate_event if history[0].get('workflow_execution') else _validate_general_effect)(root, project, task, history[0])
    if source_reservation and not source_reservation.get('may_create_session'):
        raise ValueError('Source session creation is not explicitly reserved; reconcile the original admission.')
    row = {"record": "writing-session", "id": "WS-" + uuid.uuid4().hex,
           **({'workflow_event_id':workflow_event_id} if workflow_event_id else {}),
           **({'source_execution':dict(source_reservation['attachment']), 'source_admission_id':source_reservation['admission_id']} if source_reservation else {}),
           **({'reader_profile':dict(reader_profile)} if reader_profile else {}),
           "project": project, **choice,
           "native_id": None, "role": role, "created_at": time.time()}
    if reader_profile:row['settings_provenance']={key:{'origin':'immutable-reader-profile','value':choice.get(key),'application_boundary':'immutable attempt'} for key in ('provider','model','effort')}
    # Two members on this EXISTING row kind, written only when this session is a dispatched
    # child, so an ordinary session's banked bytes are untouched.
    if dispatch_id:
        row["dispatch_id"] = str(dispatch_id)
        row["packet"] = str(packet or "")
    writing_records.bank(root, row)
    if source_reservation:
        from laplace.writing import source_execution
        source_execution.bind_app(root, source_reservation, row['id'])
    return row


_SESSION_SETTINGS_LOCKS = {}


def session_settings_lock(root: Path, ident: str):
    """The existing session-settings writer's cross-process serialization.

    Reuse one FileLock object per session so legacy/new settings/withdrawal
    callers are reentrant and serialize against the same WSS custody.
    """
    from filelock import FileLock
    from laplace.core.identity import canonical_digest
    path=Path(root).resolve()/'contract'/'.session-settings'/ (canonical_digest(ident)[7:]+'.lock')
    path.parent.mkdir(parents=True,exist_ok=True)
    return _SESSION_SETTINGS_LOCKS.setdefault(str(path),FileLock(str(path),timeout=15))


def configure_session(root: Path, project: str, ident: str, payload: dict) -> dict:
    root = Path(root).resolve()
    """Change the next turn's settings while retaining the logical conversation."""
    from laplace.work.project_work import validate_session_settings
    with turn_jobs._LOCK, session_settings_lock(root,ident):
        state=writing_records.fold_records(root)
        session = state["sessions"].get(ident)
        if not session or session["project"] != project:
            raise ValueError("The session does not belong to this project.")
        if session.get('reader_profile'):
            raise ValueError('Sealed reader settings are immutable. Prepare a fresh input/attempt.')
        if (any(j["session_id"] == ident and not j["done"] for j in turn_jobs._JOBS.values())
                or child_hosts.child_execution(root, ident).get("state") in {"STARTING", "WAITING", "RUNNING", "ORPHANED", "UNKNOWN-OWNERSHIP"}):
            raise ValueError("Wait for the current reply or stop it before changing its settings.")
        values = {key: payload.get(key, session[key]) for key in ("provider", "model", "effort")}
        if all(values[key] == session[key] for key in values):
            return {"session": dict(session)}
        if (session.get('source_execution') or session.get('dispatch_id') or session.get('workflow_event_id')
                or any(row.get('session_id')==ident and any(row.get(key) for key in ('feedback_execution','workflow_execution','source_execution')) for row in state['turns'].values())):
            raise ValueError('Admitted recipient settings are immutable; use the responsible future-recipient owner.')
        values = validate_session_settings(values, root)
        from laplace.writing.session_settings import _provenance
        writing_records.bank(root, {"record": "writing-session-settings", "id": "WSS-" + uuid.uuid4().hex,
                     "session_id": ident, "project": project, **values,
                     'settings_provenance':_provenance(session,{key:payload[key] for key in ('provider','model','effort') if key in payload},values),
                     "settings_revision": session.get("settings_revision", 0) + 1,
                     "provider_changed": values["provider"] != session["provider"],
                     "previous_native_id": session.get("native_id")})
        return {"session": dict(writing_records.fold_records(root)["sessions"][ident])}


def effort_as_sent(root: Path, session: dict, *, on_spawn=None) -> dict:
    """Re-bank a session's effort as what its transport will SEND, on the TURN path.

    EFFORT TRUTH needs the model's capability and only the provider catalogue carries it.
    ``project_work.resolve_session_settings`` applies it at both session doors, but the
    OPENING door is handed a catalogue that may never have been discovered (starting a
    conversation must not start a provider process), and
    ``src/laplace/writing_provider.py:454`` ``models_discovered`` is what that looks like:
    one placeholder row with an empty id.  A session opened there recorded the effort it was
    handed while ``src/laplace/writing_provider.py:958`` sent no flag --- the row and the
    transport disagreeing, which is the live row WS-abc8cfa1d95c4828bc49aacbd93b81b8 this
    lane set out to end, and which my own instrument banked again at
    ``evidence/WRITING_JOINS_2026-10-04/S2/tier-defaults/instrument/claude-light/case-discuss-source.json``.

    The cure is HERE because this path already reads the live catalogue for this very
    capability and already starts a process, so nothing new runs on open: the turn corrects
    its own settings through the EXISTING ``writing-session-settings`` row (no new store, no
    new key, no second effort holder) and then runs on the corrected value.  Returns
    ``{'session': <the session as it now stands>, 'supports_effort': bool}``; the advertised
    row is found by ``writing_provider.advertised_model``, the one spelling organ, so an
    alias suffix is not a second lookup rule here."""
    from laplace.writing import provider as writing_provider   # outward: live capability discovery before a run
    provider_row = next((item for item in writing_provider.capabilities(root, provider_id=session.get('provider') or '', **({'on_spawn':on_spawn} if on_spawn else {})).get('providers', [])
                         if item.get('id') == session.get('provider')), {})
    row = writing_provider.advertised_model(provider_row, str(session.get('model') or '')) or {}
    supports = row.get('supports_effort', True)
    if supports is False and session.get('effort') is not None:
        with turn_jobs._LOCK, session_settings_lock(root,session['id']):
            current = writing_records.fold_records(root)["sessions"].get(session["id"]) or session
            writing_records.bank(root, {"record": "writing-session-settings", "id": "WSS-" + uuid.uuid4().hex,
                         "session_id": session["id"], "project": session["project"],
                         "provider": current["provider"], "model": current["model"],
                         "effort": None, "model_source": current.get("model_source"),
                         "tier": current.get("tier"),
                         'settings_provenance':{**(current.get('settings_provenance') or {}),'effort':{'origin':'transport-capability-normalization','value':None,'application_boundary':'future messages only'}},
                         "settings_revision": current.get("settings_revision", 0) + 1,
                         "provider_changed": False,
                         "previous_native_id": current.get("native_id")})
            session = dict(writing_records.fold_records(root)["sessions"][session["id"]])
    return {"session": session, "supports_effort": bool(supports)}


def _start_turn(root: Path, payload: dict, *, dispatch: dict | None = None, reader_operator=None, delivery_event=None, source_reservation=None, source_event=None, workflow_event=None) -> dict:
    """Admit one author turn and start it (writing.turn_admission, then writing.turn_execution)."""
    from laplace.writing import turn_execution
    root = Path(root).resolve()
    if reader_operator is None:request = prepare_request(payload)
    else:request,reader_operator=sealed_operator_request(payload)
    with turn_jobs._LOCK:
        if request.get('profile'):
            from laplace.writing import sealed_reader
            reused=sealed_reader.replay(root,request)
        else:
            from laplace.writing.sealed_reader import require_unreserved_request
            require_unreserved_request(root,request)
            reused=None
        if reused:
            return reused
        records = writing_records.fold_records(root)
        if not request.get('profile'):
            reused=reused_turn(records,request)
            if reused:return reused
        from laplace.writing import source_execution
        source_execution.guard_spawn(root, request['project'],
            parent_turn_id=(dispatch or {}).get('parent_turn_id'), reservation=source_reservation)
        try:launch = admit(root, payload, request, records, dispatch,reader_operator=reader_operator,
                          **({'delivery_event':delivery_event} if delivery_event else {}),
                          **({'workflow_event':workflow_event} if workflow_event else {}),
                          **({'source_reservation':source_reservation, 'source_event':source_event} if source_reservation else {}))
        except Exception as error:
            if request.get('profile') and isinstance(error,sealed_reader.NotAdmitted):
                raise sealed_reader.settle(root,payload,request,error) from error
            raise
    turn_execution.start(launch)
    if launch.reader_profile:
        from laplace.writing.sealed_reader import receipt
        return receipt(writing_records.fold_records(root)['turns'][launch.turn_id])
    return {**({'action_submission': {'request_id': request['request_id'],
                'intent_sha256': request['action_submission_intent_sha256'],
                'read': action_submission_read(launch.project, launch.session_id, request['request_id'])}}
                if request.get('action_submission_intent_sha256') else {}),
            "turn_id": launch.turn_id, "session_id": launch.session_id, "workspace_context": launch.workspace_context,
            'settings_read':_settings_read(launch.project,launch.session_id),
            "queued_work_ids": [row["id"] for row in launch.queued_requests],
            "events": "/authoring/events?turn=" + launch.turn_id}


def start_turn(root: Path, payload: dict, *, dispatch: dict | None = None) -> dict:
    # A TURN REQUEST CANNOT MAKE ITSELF A CHILD.  `dispatch_id` and `parent_turn_id` are not
    # request members at all: they reach a turn only on the internal `dispatch` argument that
    # `launch_dispatch` passes, after ITS refusals have passed (the dispatch row is open and
    # this project's, the parent turn is this project's, the plan's `fan_out_max` has room).
    # The HTTP door hands this function the request body verbatim (:3301), so without this
    # refusal any client of the local app could name a fabricated `dispatch_id`, spawn a
    # detached one-shot host per request and bank child rows whose parent names nothing --
    # every refusal of the dispatch bypassed because none of them is on this path.  The
    # refusal is a shape refusal and not a second copy of those rules: it says only that
    # these members are the launcher's, which is why `fan_out_max` is still enforced in
    # exactly one place.
    for member in ("dispatch_id", "parent_turn_id"):
        if member in payload:
            raise ValueError("A turn request cannot carry %s: a child turn's dispatch "
                             "membership is set by dispatch_launch alone, which refuses a "
                             "launch its plan does not allow before it starts anything."
                             % member)
    for member in ('feedback_execution','delivery_event','runtime_seconds','runtime_deadline_at'):
        if member in payload:
            raise ValueError('A turn request cannot carry '+member+': feedback execution limits are issued only by the existing Work delivery admission.')
    # A DISPATCHED CHILD'S TURN IS STARTED IN A PROCESS OF ITS OWN.  Every in-app turn is
    # supervised by the process that started it -- `_start_turn` below runs the provider on a
    # `threading.Thread` of THIS process -- and a dispatch is launched from a tool call, so
    # without this branch the children are supervised by the parent turn's own stdio door
    # adapter (`python -m laplace.native.tools`, spawned by `writing_provider`'s
    # `--mcp-config`), which the CLI ends with the parent's turn: a parent that returns the
    # instant it has launched killed its whole wave, measured on the stub chain
    # (dispatch-build/stub-replay-undetached/rehearsal.json, writing-reply 1 of 4).  The
    # system's own precedent is `research_surface.py:1609`, which starts a supervised research
    # run `start_new_session=True` and then reads its terminal state from the durable row;
    # this is the same move for a child turn, and it is why `launch_dispatch` can say
    # `started` and mean it.  The host is the SAME door module, run one-shot
    # (`writing_tools.main --start-child-turn`), so there is one turn path and no second
    # launcher: it sets `_CHILD_HOST` and calls straight back in here.
    if dispatch and not turn_jobs.child_host():
        if payload.get('source_grant_id'):
            raise ValueError('Dispatched executions cannot self-attach with a Source selector.')
        from laplace.writing import source_execution
        source_execution.guard_spawn(root, str(payload.get('project') or ''),
            parent_turn_id=dispatch.get('parent_turn_id'))
        from laplace.writing.turn_execution import launch_child_host
        return launch_child_host(root, payload, dispatch)
    return _start_scoped(root,payload,dispatch=dispatch)


def start_work_delivery_turn(root,payload,event_id):
    """Trusted WD entry: execution limits are loaded from its canonical reservation."""
    return _start_scoped(root,payload,delivery_event=event_id)


def start_source_turn(root, payload, reservation, *, delivery_event=None, source_event=None, source_return=None):
    """Trusted Work delivery/parent entry; never forwarded from public request fields.

    A Work delivery's Source review (`source_event`) or its once-only parent return (`source_return`: the settled event)
    requested through the provider's transient stdio adapter is started in a one-shot host of its own, as a dispatched
    child is (start_turn): a turn is supervised by the process that started it, and the adapter ends with the parent's
    CLI. The host receives only the event id; it replays the canonical reservation (work_delivery.start_source_review /
    start_source_return) and re-enters here, so admission and its checks stay one path."""
    if (source_event or source_return) and not turn_jobs.child_host() and _transient_adapter_call():
        from laplace.writing import source_execution
        source_execution.guard_spawn(root, str(payload.get('project') or ''), reservation=reservation)
        from laplace.writing.turn_execution import launch_child_host
        return launch_child_host(root, payload, {}, source_event=source_event, source_return=source_return)
    return _start_scoped(root, payload, source_reservation=reservation, delivery_event=delivery_event, source_event=source_event)


def _transient_adapter_call() -> bool:
    """This call arrived through the Claude stdio MCP adapter (native.tools main loop): a process the CLI ends with its turn."""
    from laplace.writing import delivery
    holder = (delivery._invocation() or {}).get('native')
    return getattr(holder, 'transport_kind', None) == 'claude-mcp'


def start_workflow_turn(root, payload, event_id):
    """Private effect-specific entry; public request fields cannot construct it."""
    return _start_scoped(root, payload, workflow_event=event_id)


def sealed_operator_request(commission):
    """A bounded reader request by its declared purpose (operator qualification or ordinary document deliberation)."""
    from laplace.writing.sealed_reader import bounded_request
    return bounded_request(commission)


def start_reader_qualification(root: Path, commission: dict) -> dict:
    """Explicit trusted local operator entry; no public door forwards a purpose flag here."""
    from laplace.writing.sealed_reader import operator_request
    operator_request(commission)
    return _start_scoped(root,commission,reader_operator=True)


def start_reader_deliberation(root: Path, commission: dict) -> dict:
    """Ordinary bounded document deliberation through the same reader admission and execution.

    Closed purpose and supported limits, QUALIFIED support only, immutable request intent; the provider budget flag and
    the existing wall/cleanup/UTF-8 supervision are the enforced controls. It never selects the qualification purpose.

    The caller OWNS the turn's lifetime, as reader_qualification.commission does: supervision runs on a daemon thread
    of this process, so this entry waits for settlement and, if its caller is interrupted or exits (any BaseException,
    including KeyboardInterrupt and SystemExit), interrupts the turn through the existing turn_control owner and waits
    for the existing provider cleanup before re-raising. A hard kill of the calling process (SIGKILL) cannot be
    intercepted; the provider's own --max-budget-usd then remains the only control.
    """
    from laplace.writing.sealed_reader import deliberation_request
    deliberation_request(commission)
    acknowledgement = _start_scoped(root, commission, reader_operator=True)
    return _settle_owned_reader(Path(root).resolve(), commission['project'], acknowledgement)


def _settle_owned_reader(root: Path, project: str, acknowledgement: dict) -> dict:
    """Wait for one admitted bounded reader turn; on caller interruption interrupt it and wait for its settlement."""
    from laplace.writing import session_reads, turn_control
    from laplace.writing.sealed_reader import DELIBERATION_PURPOSE
    turn_id = acknowledgement['turn_id']
    job = turn_jobs._JOBS.get(turn_id)
    if job is not None:   # a replayed request settled elsewhere has no live job in this process
        try:
            with job['condition']:
                while not job['done']:
                    job['condition'].wait(timeout=.2)
        except BaseException:
            turn_control.interrupt_turn(root, {'project': project, 'turn_id': turn_id})
            with job['condition']:
                while not job['done']:
                    job['condition'].wait(timeout=.2)
            raise
    exact = session_reads.session_turn_detail(root, project, turn_id, 'turn')
    return {'purpose': DELIBERATION_PURPOSE, 'admission': acknowledgement, 'result': exact,
            'lifetime': 'owned by the calling process until settlement; interrupted and settled if the caller is interrupted or exits',
            'qualification_installed': False}


def _start_scoped(root,payload,*,dispatch=None,reader_operator=None,delivery_event=None,source_reservation=None,source_event=None,workflow_event=None):
    token = uuid.uuid4().hex
    with turn_jobs._STARTING_TURNS_LOCK:
        turn_jobs._STARTING_TURNS[token] = {
            "project":str(payload.get("project") or ""),
            "session_id":str(payload.get("session_id") or "") or None,
            "label":" ".join(str(payload.get("text") or "").split())[:200],
            "provider":str(payload.get("provider") or "") or None,
            # the requested Work target (admitted later by turn_admission); qualified activity reads it
            "work_id":payload.get("work_id") if isinstance(payload.get("work_id"), str) and payload.get("work_id") else None}
    try:
        if dispatch:
            from laplace.work import project_work
            with project_work.dispatch_lock(root):
                return _start_turn(root, payload, dispatch=dispatch,reader_operator=reader_operator,
                                   **({'delivery_event':delivery_event} if delivery_event else {}),
                                   **({'workflow_event':workflow_event} if workflow_event else {}),
                                   **({'source_reservation':source_reservation, 'source_event':source_event} if source_reservation else {}))
        from laplace.work import project_work
        with project_work.dispatch_lock(root):
            return _start_turn(root, payload, dispatch=dispatch,reader_operator=reader_operator,
                               **({'delivery_event':delivery_event} if delivery_event else {}),
                               **({'workflow_event':workflow_event} if workflow_event else {}),
                                   **({'source_reservation':source_reservation, 'source_event':source_event} if source_reservation else {}))
    finally:
        with turn_jobs._STARTING_TURNS_LOCK:
            turn_jobs._STARTING_TURNS.pop(token,None)
