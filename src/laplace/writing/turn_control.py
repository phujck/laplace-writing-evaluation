"""TURN CONTROL (S1 B2): the author's steering and interruption of a running turn.

steer_turn / _prepare_steering_input   admit an author steering message for a running in-process turn:
                                       the same selection/draft/workspace validation as a new turn
                                       (writing.turn_context), delivered as a bounded delta, banked once.
_queue_child_steering / _admit_child_steering / _deliver_child_steering
                                       the same for a turn running in a child host: queued in that
                                       host's steering mailbox (writing.child_hosts), admitted exactly
                                       once and delivered when the host's provider accepts steering.
interrupt_turn                         stop one exact turn: the live job's provider (writing.turn_jobs)
                                       or the owned child host process; never another session's process.
                                       Before it acts it banks one durable exact project/session/turn/host-generation
                                       Stop request (writing-turn-stop-request) that Source producer_origin reads.

The journal is writing_records.bank/_records; the execution record is writing.child_hosts.
"""
from __future__ import annotations

import datetime as dt
import json
import time
import uuid
from pathlib import Path
from collections.abc import Mapping

from laplace.core.identity import canonical_digest


def _deliver_child_steering(root: Path, session_id: str, turn_id: str):
    from laplace.work import project_work
    with project_work.dispatch_lock(root):
        first = child_hosts._child_execution_record(root,session_id)
        frontier = int(first.get("control_completed_sequence") or 0)
        admitted = int(first.get("control_sequence") or 0)
    if frontier >= admitted:return
    for sequence in range(frontier+1,admitted+1):
        with project_work.dispatch_lock(root):
            execution = child_hosts.child_execution(root, session_id)
            if execution.get("turn_id") != turn_id or execution.get("state") != "RUNNING":return
            # Admission reserves the ordinal and publishes both files under this
            # lock. Only a completed or failed admission can be inspected here.
            # A second governor may already have delivered this ordinal.
            if int(execution.get("control_completed_sequence") or 0) >= sequence:continue
            matches = list(child_hosts._steer_mailbox(root,session_id).glob(f"{sequence:020d}-*.request.json"))
            if not matches:
                child_hosts._update_child_execution(root,session_id,{"control_completed_sequence":sequence},expected_turn_id=turn_id)
                continue
            request = matches[0]
            acknowledgement = request.with_name(request.name.replace(".request.json", ".ack.json"))
            receipt = child_hosts._read_host(acknowledgement)
            if receipt.get("turn_id") != turn_id:
                child_hosts._update_child_execution(root,session_id,{"control_completed_sequence":sequence},expected_turn_id=turn_id)
                continue
            if (receipt.get("state") in {"ADMITTED", "DELIVERING"} and
                    receipt.get("execution_host") != execution.get("host")):
                child_hosts._write_host(acknowledgement, {**receipt, "state": "FAILED" if receipt["state"] == "ADMITTED" else "UNCONFIRMED",
                                            "error": "admitted host identity changed; control is not replayed"})
                child_hosts._update_child_execution(root,session_id,{"control_completed_sequence":sequence},expected_turn_id=turn_id)
                continue
            # An unacknowledged native call is never replayed, and blocks later calls.
            if receipt.get("state") == "DELIVERING" or receipt.get('state') in {'OFFERED_AT_TOOL_BOUNDARY','PREPARING_AT_EXACT_READ'}:return
            if receipt.get("state") != "ADMITTED":
                child_hosts._update_child_execution(root,session_id,{"control_completed_sequence":sequence},expected_turn_id=turn_id)
                continue
            if receipt.get("delivery_mode")=="project_tool_boundary":return
            command = child_hosts._read_host(request)
            payload = command.get("payload") or {}
            if (command.get("sequence") != receipt.get("sequence") or
                    command.get("control_id") != receipt.get("control_id") or payload.get("turn_id") != turn_id):
                child_hosts._write_host(acknowledgement, {**receipt, "state": "FAILED", "error": "control admission identity disagrees with its payload"})
                continue
            receipt = {**receipt, "state": "DELIVERING"}
            child_hosts._write_host(acknowledgement, receipt)
            child_hosts._update_child_execution(root, session_id, {"last_control": receipt}, expected_turn_id=turn_id)
        try:
            result = steer_turn(root, payload)
            outcome = {**receipt, "state": "DELIVERED", "result": result}
        except Exception as exc:
            outcome = {**receipt, "state": "FAILED", "error": str(exc)}
        with project_work.dispatch_lock(root):
            execution = child_hosts.child_execution(root, session_id)
            observed = child_hosts._read_host(acknowledgement)
            if (execution.get("turn_id") != turn_id or execution.get("state") != "RUNNING" or
                    observed.get("state") != "DELIVERING"):
                outcome = {**receipt, "state": "UNCONFIRMED", "error": "child ended before the native acknowledgement was saved"}
            else:
                child_hosts._update_child_execution(root, session_id, {"last_control": outcome,"control_completed_sequence":sequence}, expected_turn_id=turn_id)
            child_hosts._write_host(acknowledgement, outcome)


def _admit_child_steering(root: Path, turn: dict, payload: dict) -> tuple[Path, dict]:
    from laplace.work import project_work
    with project_work.dispatch_lock(root):
        execution = child_hosts.child_execution(root, turn["session_id"])
        if execution.get("turn_id") != turn.get("id") or payload.get("turn_id") != turn.get("id"):
            raise ValueError("The selected execution belongs to another turn.")
        if execution.get("state") != "RUNNING":
            raise ValueError("There is no active provider turn available for steering.")
        mode=payload.get('delivery_mode') or ('native_rpc' if (turn.get('provider_settings') or {}).get('provider')=='codex' else 'project_tool_boundary')
        if mode not in {'native_rpc','project_tool_boundary'}:raise ValueError('Unknown input delivery mode.')
        if mode=='native_rpc' and (turn.get("provider_settings") or {}).get("provider") != "codex":
            raise ValueError("This provider has no native steering; use project_tool_boundary input.")
        if payload.get("project") and payload["project"] != turn.get("project"):
            raise ValueError("The active turn belongs to another project.")
        if not str(payload.get("text") or "").strip():raise ValueError("Write steering input first.")
        if mode=='project_tool_boundary':
            frontier=int(execution.get('control_completed_sequence') or 0)
            admitted=int(execution.get('control_sequence') or 0)
            for pending_sequence in range(frontier+1,admitted+1):
                matches=list(child_hosts._steer_mailbox(root,turn['session_id']).glob(f'{pending_sequence:020d}-*.ack.json'))
                previous=child_hosts._read_host(matches[0]) if len(matches)==1 else {}
                if previous.get('turn_id') and previous['turn_id']!=turn['id']:continue # Historical turn, never the current slot.
                if (previous.get('turn_id')!=turn['id'] or previous.get('execution_host')!=execution.get('host')
                        or (previous.get('state') not in {'PUBLISHED_AT_TOOL_BOUNDARY','EXACT_SCOPED_CONTROL_READ','FAILED'}
                            and not (previous.get('delivery_mode')=='project_tool_boundary' and previous.get('terminal') is True))):
                    ident=previous.get('control_id')
                    read={'operation':'conversation_history','payload':{'view':'controls','turn_id':turn['id'],**({'item_id':ident} if ident else {'limit':1})}}
                    raise ValueError('Queued input '+str(ident or 'with unproved identity')
                                     +' is awaiting publication; compose the next input while waiting. Inspect its exact receipt with '
                                     +json.dumps(read)+'. Nothing new was admitted.')
        control_id = uuid.uuid4().hex
        sequence = int(execution.get("control_sequence") or 0) + 1
        request = child_hosts._steer_mailbox(root, turn["session_id"]) / (f"{sequence:020d}-" + control_id + ".request.json")
        receipt = {"control_id": control_id, "turn_id": turn["id"], "sequence": sequence,
                   "execution_host": execution.get("host"), "state": "ADMITTED", "delivery_mode":mode}
        child_hosts._update_child_execution(root, turn["session_id"], {"control_sequence": sequence}, expected_turn_id=turn["id"])
        child_hosts._write_host(request, {**receipt, "payload": payload})
        child_hosts._write_host(request.with_name(request.name.replace(".request.json", ".ack.json")), receipt)
        child_hosts._update_child_execution(root, turn["session_id"], {"last_control": receipt}, expected_turn_id=turn["id"])
        return request, receipt


def _queue_child_steering(root: Path, turn: dict, payload: dict) -> dict:
    request, admitted = _admit_child_steering(root, turn, payload)
    acknowledgement = request.with_name(request.name.replace(".request.json", ".ack.json"))
    if admitted.get("delivery_mode")=="project_tool_boundary":
        return {"control_id":admitted["control_id"],"sequence":admitted["sequence"],"delivery":"PENDING","delivery_mode":"project_tool_boundary",
                "basis":"Queued only for this active turn; offered at its next project-tool result, never retargeted."}
    until = time.monotonic() + 5
    while time.monotonic() < until:
        execution = child_hosts.child_execution(root, turn["session_id"])
        receipt = next((row for row in child_hosts._child_control_rows(root, turn["session_id"], turn["id"],
                      execution.get("state") if execution.get("turn_id") == turn["id"] else "FINISHED", item_id=admitted["control_id"])
                        if row.get("control_id") == admitted["control_id"]), {})
        if receipt.get("state") in {"FAILED", "UNCONFIRMED"}:
            raise ValueError("Control " + admitted["control_id"] + ": " + str(receipt.get("error") or receipt["state"]))
        if receipt.get("state") == "DELIVERED":
            return {**(receipt.get("result") or {}), "control_id": admitted["control_id"],
                    "sequence": admitted["sequence"], "delivery": "DELIVERED"}
        time.sleep(.05)
    return {"control_id": admitted["control_id"], "sequence": admitted["sequence"], "delivery": "PENDING"}


def _publish_local_stop(root: Path, session_id: str, ident: str, execution: dict) -> dict | None:
    """A selected-turn Stop of a job running in THIS process publishes the existing exact-turn cancel marker, qualified by
    the live generation (this turn, RUNNING, hosted by this process: the caller holds the ownership lock), so another
    process of the turn sees it. Every consumer applies it to its own generation only (turn id, and the host where the
    marker records one), so the marker stays as the remote branch's does and cannot stop a newer turn of the session.
    Nothing account-wide is stopped."""
    if (execution.get("turn_id") != ident or execution.get("state") != "RUNNING"
            or execution.get("host") != child_hosts._process_identity()):
        return None
    marker = {"turn_id": ident, "host": execution["host"], "requested_at": time.time(), "scope": "selected-turn"}
    child_hosts._write_host(child_hosts._host_path(root, session_id).with_suffix(".cancel.json"), marker)
    return marker


STOP_REQUEST = "writing-turn-stop-request"


class StopRequestUnrecorded(ValueError):
    """A selected-turn Stop acted on its turn, but its durable exact-turn Stop request is not proven published.

    ``result`` is what the Stop did (the DTO a recorded Stop returns). ``stop_request`` is the exact publication outcome:
    UNRECORDED (the journal index does not hold the row after a failed append), UNCERTAIN (whether it does is unknown) or
    UNBOUND (the row is banked but names no host generation, so its reader cannot honour it as one generation's Stop).
    """

    def __init__(self, message: str, result: dict, stop_request: dict):
        super().__init__(message)
        self.result = result
        self.stop_request = stop_request


def stop_generation(execution: Mapping, turn_id: str) -> str | None:
    """The host generation a selected-turn Stop addresses: the birth identity of the recorded execution host when the
    session's execution names this turn, else None (no shared host is recorded for this turn)."""
    host = execution.get("host") if isinstance(execution, Mapping) and execution.get("turn_id") == turn_id else None
    return canonical_digest(host) if isinstance(host, Mapping) and host else None


def stop_request_id(project: str, session_id: str, turn_id: str, generation: str | None) -> str:
    """Deterministic: a repeated Stop of the same project, session, turn and generation is the same request."""
    return "TSR-" + canonical_digest({"project": project, "session_id": session_id, "turn_id": turn_id,
                                      "execution_generation": generation})[7:31]


def generation_custody(root: Path, session_id: str, turn_id: str) -> dict:
    """The host generation recorded for this turn WITH its custody, used by BOTH the Stop write and the Source read (never
    a projection): the session's raw execution record when it names the turn, else its finished record when that names
    it. BOUND: that record names the turn and its host birth identity (the generation). UNBOUND: no record names the turn
    any more (newer turns replaced both) or the naming record has no host. UNREADABLE: the host records could not be
    addressed. Only BOUND carries a generation; neither UNBOUND nor UNREADABLE is read as the absence of a Stop."""
    try:
        path = child_hosts._host_path(root, session_id)
        for record in (child_hosts._read_host(path), child_hosts._read_host(path.parent / "finished" / path.name)):
            if record.get("turn_id") == turn_id:
                generation = stop_generation(record, turn_id)
                return {"state": "BOUND" if generation else "UNBOUND", "generation": generation}
    except (ValueError, OSError) as error:
        return {"state": "UNREADABLE", "generation": None, "error": (type(error).__name__ + ": " + str(error))[:200]}
    return {"state": "UNBOUND", "generation": None}


def recorded_generation(root: Path, session_id: str, turn_id: str) -> str | None:
    """The BOUND generation of generation_custody, else None (UNBOUND or UNREADABLE: the reader then fails closed)."""
    return generation_custody(root, session_id, turn_id)["generation"]


def recorded_stop_requests(root: Path, project: str, session_id: str, turn_id: str) -> list[dict]:
    """The durable Stop requests of exactly this project, session and turn whose row agrees with its deterministic
    identity, from the existing journal index. Read-only; the shared cancel marker plays no part."""
    found = []
    for row in writing_records.index(root).by_turn.get(turn_id, ()):
        if (row.get("record") == STOP_REQUEST and row.get("state") == "REQUESTED" and row.get("project") == project
                and row.get("session_id") == session_id and row.get("turn_id") == turn_id
                and row.get("id") == stop_request_id(project, session_id, turn_id, row.get("execution_generation"))):
            found.append({key: row.get(key) for key in ("id", "project", "session_id", "turn_id", "execution_generation", "ts")})
    return found


def _publish_stop_request(root: Path, turn: dict, ident: str, execution: Mapping) -> dict:
    """Bank ONE durable exact-turn Stop request in the existing journal before the Stop acts and reports success.

    The row records the author's request for this turn generation, not that a process stopped; it names no other turn,
    generation, session or Source account. A repeated Stop of the same generation reuses its identity. A failed append
    is checked against the index: present is RECORDED, absent is UNRECORDED, an unreadable index is UNCERTAIN.
    """
    project, session_id = turn.get("project"), turn.get("session_id")
    custody = generation_custody(root, session_id, ident)  # the one function the Source read also uses
    generation = custody["generation"]
    # RECORDED is a claim the reader can honour: a request banked without a host generation is UNBOUND, or UNREADABLE when
    # the host records could not be read (the Source reader holds a prepared continuation of the turn UNKNOWN/HELD).
    settled = "RECORDED" if generation else ("UNREADABLE" if custody["state"] == "UNREADABLE" else "UNBOUND")
    public = {"id": stop_request_id(project, session_id, ident, generation), "turn_id": ident,
              "session_id": session_id, "execution_generation": generation}

    def present() -> bool:
        return any(row["id"] == public["id"] for row in recorded_stop_requests(root, project, session_id, ident))

    try:
        if present():
            return {**public, "state": settled, "reused": True}
    except Exception as error:
        return {**public, "state": "UNCERTAIN",
                "error": ("journal index unreadable: " + type(error).__name__ + ": " + str(error))[:300]}
    row = {"record": STOP_REQUEST, "id": public["id"], "project": project, "session_id": session_id, "turn_id": ident,
           "execution_generation": generation, "state": "REQUESTED", "scope": "selected-turn",
           "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
           "meaning": "The author requested an exact selected-turn Stop of this turn generation. A request, not proof that a "
                      "process stopped; no other turn, generation or Source account is stopped by it."}
    try:
        writing_records.bank(Path(root), row)
    except Exception as error:
        failure = (type(error).__name__ + ": " + str(error))[:300]
        try:
            if present():
                return {**public, "state": settled, "reused": False, "acknowledgement_error": failure}
            state = "UNRECORDED"
        except Exception:
            state = "UNCERTAIN"
        return {**public, "state": state, "error": failure}
    return {**public, "state": settled, "reused": False}


def _source_bound(root, ident: str, turn: Mapping) -> bool:
    """Whether the turn is a Source producer (its recorded commission attachment); unknown custody counts as bound."""
    if root is None or turn.get("source_execution"):
        return True
    try:
        return bool((writing_records.index(root).turns.get(ident) or {}).get("source_execution"))
    except (ValueError, OSError):
        return True


def _reported(request: dict | None, result: dict, *, root=None, ident: str = "", turn: Mapping | None = None) -> dict:
    """The unchanged Stop DTO only once its durable request is RECORDED (a generation its reader honours); otherwise the
    exact publication truth. An UNBOUND request (banked without a host generation) of a turn without a Source commission
    has no continuation consumer, so the process-Stop DTO stands. For a Source producer turn it raises: no definite
    durable Stop of one generation can be claimed, and its reader holds the prepared continuation UNKNOWN (HELD)."""
    if request is None or request.get("state") == "RECORDED":
        return result
    if request.get("state") in ("UNBOUND", "UNREADABLE"):
        if not _source_bound(root, ident, turn or {}):
            return result
        cause = ("the turn's host execution records could not be read" if request["state"] == "UNREADABLE"
                 else "no host generation of the turn was recorded")
        raise StopRequestUnrecorded(
            "Stop acted on turn %s and banked request %s, but %s, so its reader cannot bind the request to one generation: "
            "a prepared Source continuation of this turn reads Stop custody UNKNOWN (HELD, never READY), not a definite "
            "durable Stop." % (request["turn_id"], request["id"], cause), result, request)
    raise StopRequestUnrecorded(
        "Stop acted on turn %s, but its durable exact-turn Stop request %s is %s and not durably recorded (%s). The "
        "process stop is separate from that record: a prepared Source continuation of this turn stays withdrawn only "
        "while the shared cancel marker names it or a later write records it. Only while the turn is still active can a "
        "repeated Stop retry the same request; once it is inactive (for example its processes were terminated) no Stop "
        "can record it." % (request["turn_id"], request["id"], request["state"], request.get("error") or "unknown"),
        result, request)


def interrupt_turn(root: Path, payload: dict) -> dict:
    """Selected-turn Stop is exact; task cancellation governs a dispatch's children.

    DURABLE REQUEST (A378d F5): when this Stop will act on its turn it first banks the exact project/session/turn/host
    generation Stop request (_publish_stop_request), so the Source producer origin stays stopped after a completed reply
    races or a newer turn replaces the session's shared marker. The process stop below stays separate from that record.
    A request that is not proven published raises StopRequestUnrecorded after the stop acted, never a plain success.
    """
    from laplace.work import project_work
    ident = str(payload.get("turn_id") or "")
    turn = writing_records.fold_records(root)["turns"].get(ident) or {}
    if not turn or (payload.get("project") and payload["project"] != turn.get("project")):
        raise ValueError("There is no active provider turn in this project.")
    controlled, settle, request = [], None, None
    with project_work.dispatch_lock(root):
        job = turn_jobs._JOBS.get(ident)
        execution = child_hosts.child_execution(root, turn["session_id"])
        continuation=execution.get('parent_continuation')
        if continuation and continuation.get('turn_id')==ident and continuation.get('phase') not in {'OBSERVATION_EXPIRED','STALE'}:
            from laplace.writing import dispatch_parent
            stopped={**continuation,'phase':'PARENT_STOPPED','invalidated':True,
                'reason':'Parent observation stopped; detached child work remains supervised under the original dispatch deadline.'}
            # Keep only the owner intent/phase on the host, not an expanded
            # public projection or process/control history.
            raw=child_hosts._child_execution_record(root,turn['session_id']).get('parent_continuation') or {}
            child_hosts._update_child_execution(root,turn['session_id'],{'parent_continuation':{**raw,
                **{key:stopped[key] for key in ('phase','invalidated','reason')}}},expected_turn_id=ident)
        remote = not job or job["done"]
        if remote and execution and execution.get("turn_id") != ident:
            raise ValueError("The selected execution belongs to another turn.")
        # RECOVERY: an author turn whose recorded host process exited while it was still running (no live job here,
        # the execution reads FAILED or ORPHANED) and that saved no terminal reply is settled below, after this lock,
        # by the turn's own reply producer; a dispatched child keeps its dispatch custody and deadline instead
        raw = child_hosts._child_execution_record(root, turn["session_id"]) if remote else {}
        if (remote and not turn.get("dispatch_id") and not isinstance(turn.get("reply"), Mapping)
                and execution.get("state") in {"FAILED", "ORPHANED"} and raw.get("turn_id") == ident
                and raw.get("state") in {"STARTING", "WAITING", "RUNNING"}):
            settle = raw
        # DURABLE REQUEST FIRST (under this lock, before any actuation): only a Stop that acts on this turn records one.
        if (job and not job["done"]) or settle is not None or (
                remote and execution.get("state") in {"ORPHANED", "STARTING", "WAITING", "RUNNING"}):
            request = _publish_stop_request(root, turn, ident, execution)
        if remote and execution.get("state") == "ORPHANED":
            child_hosts.terminate_child_processes(execution)
            controlled.append(ident)
        if remote and execution.get("state") in {"STARTING", "WAITING", "RUNNING"}:
            child_hosts._write_host(child_hosts._host_path(root, turn["session_id"]).with_suffix(".cancel.json"),
                        {"turn_id": ident, "requested_at": time.time()})
            controlled.append(ident)
            if not execution.get("provider_inference_started") or not execution.get("remote_steering"):
                child_hosts.terminate_child_processes(execution)
        if job and not job["done"]:
            # The shared stop fact FIRST: the job flag is visible only in this process, and a later native check of this
            # turn is admitted by its MCP adapter, which consumes the session's cancel marker at prelaunch and polling.
            _publish_local_stop(root, turn["session_id"], ident, execution)
            job["interrupt_requested"] = True
            if job.get("provider"):job["provider"].interrupt()
            # This turn's auxiliaries (a native check) may run in another process of it, out of reach of the job flag
            # and the provider interrupt; this selected-turn Stop ends exactly them, never the Source account.
            child_hosts.stop_auxiliary_processes(root, turn["session_id"], ident, "selected-turn Stop")
            if ident not in controlled:controlled.append(ident)
    if settle is not None:
        # ONE CONDITIONAL PUBLICATION (LF-R2): selection above used a snapshot; the turn's existing per-turn owner
        # lock now binds re-validation and the single terminal publication, so a competing Stop (or any changed
        # execution or late terminal reply) publishes nothing and refuses below
        from laplace.writing import turn_execution
        with writing_records.author_update_delivery_lock(root, ident):
            settled = turn_execution.settle_exited_host(root, ident, settle)
        if settled is None:
            raise ValueError("There is no active provider turn.")
        if settled.get("provider_running"):
            raise ValueError("The turn's provider process is still running; it was asked to stop. Stop again once it has exited.")
        if ident not in controlled:controlled.append(ident)
        return _reported(request, {"interrupted": True, "turn_ids": controlled, "settled": {"status": settled["status"],
                "provider_stage": settled["provider_stage"], "basis": settled["recovery"]["basis"]}},
                root=root, ident=ident, turn=turn)
    if not controlled:raise ValueError("There is no active provider turn.")
    return _reported(request, {"interrupted": True, "turn_ids": controlled}, root=root, ident=ident, turn=turn)


def _prepare_steering_input(root:Path,turn:dict,payload:dict):
    """The existing owned attention/context preparation, independent of carrier."""
    from laplace.writing.sealed_reader import require_not_reader
    require_not_reader(root,turn_id=turn['id'])
    text=str(payload.get('text') or '').strip()
    if not text:raise ValueError('Write steering input first.')
    message=text;context=None;selection=None;workspace={};unsaved_draft=None
    if 'selection' in payload or 'workspace_context' in payload:
        from laplace.pipeline import authoring
        workspace=turn_context._workspace_context(root,turn['project'],payload.get('workspace_context'))
        clean_selection,unsaved_draft=turn_context._selection_draft(payload.get('selection'))
        selection=dict(clean_selection or {})
        if workspace.get('section_ids'):selection['section_ids']=workspace['section_ids']
        if workspace.get('node_id'):selection['node_id']=workspace['node_id']
        if workspace.get('node_ids'):selection['node_ids']=workspace['node_ids']
        context=authoring.build_context(turn['project'],selection,repo_root=root,
                                        include_guidance=False,include_orientation=True)
        # A steer is another delivery into the SAME conversation, so it takes the same one
        # delta against the same part baseline.  This is where the superseded mechanism's
        # second call site was (`_without_unchanged_science` on the steer's own prompt).
        delivery=turn_context.without_already_delivered(context.get('parts') or [],turn.get('context_parts'))
        context_text=delivery['prompt'];steer_held=delivery['held']
        message=('The author has sent a further request at the current workspace location. '
                 'Use this attention scope in place of the previous location; preserve completed work.\n'
                 +json.dumps(workspace,ensure_ascii=False)+'\n\n'+context_text
                 +turn_context._draft_prompt(unsaved_draft)+'\n\nAuthor request:\n'+text)
    return {'message':message,'message_parts':{'context':[0,len(message)-len(text)],
                                               'author_request':[len(message)-len(text),len(message)]},
            'context':context,'selection':selection,'workspace':workspace,'unsaved_draft':unsaved_draft,
            'held':steer_held if context is not None else None}


def steer_turn(root:Path,payload:dict) -> dict:
    """Deliver a steered request with the actual current attention, not an old node."""
    root=Path(root).resolve();ident=str(payload.get('turn_id') or '')
    from laplace.writing.sealed_reader import require_not_reader
    require_not_reader(root,turn_id=ident)
    if payload.get('delivery_mode') not in (None,'native_rpc','project_tool_boundary'):
        raise ValueError('Unknown input delivery mode.')
    job=turn_jobs._JOBS.get(ident);turn=writing_records.fold_records(root)['turns'].get(ident)
    if turn and not job:
        return _queue_child_steering(root, turn, payload)
    if not turn or not job or job['done'] or not job.get('provider'):
        raise ValueError('There is no active provider turn.')
    capabilities=child_hosts._provider_controls(job['provider'])
    if payload.get('delivery_mode')=='native_rpc' and not capabilities.get('can_steer'):
        raise ValueError('This provider has no native steering; use project_tool_boundary input.')
    if payload.get('delivery_mode')=='project_tool_boundary' or not capabilities.get('can_steer'):
        return _queue_child_steering(root,turn,{**payload,'delivery_mode':'project_tool_boundary'})
    text=str(payload.get('text') or '').strip()
    if not text:raise ValueError('Write steering input first.')
    if payload.get('project') and payload['project']!=turn['project']:
        raise ValueError('The active turn belongs to another project.')
    prepared=_prepare_steering_input(root,turn,payload)
    message=prepared['message'];context=prepared['context'];selection=prepared['selection']
    workspace=prepared['workspace'];unsaved_draft=prepared['unsaved_draft'];steer_held=prepared['held']
    result=job['provider'].steer(message)
    if context is not None:
        writing_records.bank(root,{"record":"writing-turn-context-baseline","id":"CTX-STEER-"+uuid.uuid4().hex,
            "turn_id":ident,"project":turn['project'],"selection":selection,
            "workspace_context":workspace,"unsaved_draft":unsaved_draft,
            "science_context_digest":context.get('science_context_digest'),
            "context_parts":steer_held,
            **{key:context.get(key) for key in ('context_id','dependencies','document','consumed')}})
    writing_records.bank(root,{"record":"writing-steer","id":"WST-"+uuid.uuid4().hex,
                "turn_id":ident,"text":text,"selection":selection,"workspace_context":workspace,
                "unsaved_draft":unsaved_draft})
    return result


from laplace.writing import child_hosts  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_context  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_jobs  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import records as writing_records  # noqa: E402  (the journal owner; cycle-safe, imported last)
