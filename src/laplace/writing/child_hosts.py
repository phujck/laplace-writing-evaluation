"""CHILD EXECUTION HOSTS (S1 B2): the receipt files and process identities of turns that run in a host.

A turn runs either in this process (writing.turn_execution) or in a one-shot child host process (a
dispatched child, writing_tools --start-child-turn). Either way its execution is observable through ONE
receipt file per session under `<LAPLACE_STATE or root/contract>/writing-hosts/<root digest>/`, written
only here (_write_host, atomic replace) and read by streams, interrupts, steering and lifecycle views:

  state            STARTING | WAITING | RUNNING | terminal; ORPHANED / UNKNOWN-OWNERSHIP when the
                   recorded host process no longer matches (_process_matches by pid + start time).
  provider_process(es), provider_inference_started, control_capabilities, last_control, steering.
  auxiliary_processes  owner-created non-provider processes of the turn (a development check), registered by
                   generation from any process of the turn; stopped and observed with the provider's.

Owned here: the host directory/path, process identity and termination of OWNED processes only,
begin/update/finish of an execution record (finish settles queued steering under the author-update
delivery lock), execution observations published from the live provider, and the bounded public control
receipt. Not owned here: the live in-process registry (writing.turn_jobs), dispatch control decisions
(writing.dispatch_execution) and the journal (writing_records.bank).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from laplace.writing.provider_catalogue import ProviderError   # the neutral owner; the provider service is never imported here
from pathlib import Path


def _host_directory(root: Path) -> Path:
    # Execution observations only: tasks and turns remain in their existing ledgers.
    base = Path(os.environ.get("LAPLACE_STATE") or (Path(root) / "contract"))
    return base / "writing-hosts" / hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()


def _host_path(root: Path, session_id: str) -> Path:
    if not re.fullmatch(r"WS-[a-zA-Z0-9-]+", session_id):
        raise ValueError("Invalid writing session identity.")
    return _host_directory(root) / (session_id + ".json")


def _read_host(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_host(path: Path, value: dict):
    # Same fsync/replace protocol as semantic_cadence._write, without its Unix-only import.
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _process_identity(pid: int | None = None) -> dict:
    # psutil is already the portable process owner used by offline_launcher.
    import psutil
    try:
        process = psutil.Process(pid or os.getpid())
        return {"pid": process.pid, "created_at": process.create_time()}
    except psutil.Error:
        return {}


def _process_matches(identity: dict) -> bool:
    import psutil
    try:
        process = psutil.Process(identity["pid"])
        return (process.create_time() == identity["created_at"]
                and process.is_running() and process.status() != psutil.STATUS_ZOMBIE)
    except (psutil.Error, KeyError, TypeError, ValueError):
        return False


def _public_control_receipt(receipt, *, project="", session_id=""):
    """One transport projection; exact inspection and recovery keep the raw row."""
    if not isinstance(receipt,dict):return None
    from copy import deepcopy
    fields=('control_id','sequence','turn_id','execution_host','state','terminal',
            'delivery_mode','admitted_at','preparation_sha256','message_sha256',
            'request_sha256','error','basis','ack_basis','context_invalidation_unproved')
    result={key:deepcopy(receipt[key]) for key in fields if key in receipt}
    for key in ('error','basis','ack_basis','context_invalidation_unproved'):
        if isinstance(result.get(key),str):result[key]=result[key][:500]
    for name,keys in {
        'context_delivery':('record_id','baseline_record_id'),
        'context_read':('complete_message','baseline_record_id','basis','scope','newer_scope_preserved'),
        'context_disposition':('status','record_id','error'),
        'publication':('scope','included_chars','total_chars','text_complete','context_baseline_advanced','basis'),
    }.items():
        value=receipt.get(name)
        if isinstance(value,dict):result[name]={key:deepcopy(value[key]) for key in keys if key in value}
    publication=receipt.get('publication')
    if isinstance(publication,dict) and isinstance(publication.get('parts'),dict):
        result['publication']['parts']={name:{key:part[key] for key in
            ('included_chars','total_chars','complete') if key in part}
            for name,part in publication['parts'].items()
            if name in {'author_request','context'} and isinstance(part,dict)}
    if receipt.get('control_id') and receipt.get('turn_id') and isinstance(project,str) and project:
        payload={
            'view':'controls','turn_id':receipt['turn_id'],'item_id':receipt['control_id']}
        from laplace.writing.provider_updates import _read_handle
        result['read_handle']=_read_handle(project,'conversation_history',payload)
    return result


def child_execution(root: Path, session_id: str, *, controls: bool = False) -> dict:
    row = _child_execution_record(root, session_id)
    if row.get("state") in {"STARTING", "WAITING", "RUNNING"}:
        identity = row.get("host") or row.get("launcher") or {}
        if not _process_matches(identity):
            row = {**row, "state": "FAILED", "reason": "child host exited without a completion receipt"}
    owned = [identity for identity in row.get("provider_processes") or [] if _process_matches(identity)]
    if _process_matches(row.get("provider_process") or {}) and row["provider_process"] not in owned:
        owned.append(row["provider_process"])
    auxiliary = [identity for identity in row.get("auxiliary_processes") or [] if _process_matches(identity)]
    if row.get("state") == "FAILED" and (owned or auxiliary):
        row = {**row, "state": "ORPHANED"}
    row["active_provider_processes"] = owned
    row["active_auxiliary_processes"] = auxiliary
    if row.get('parent_continuation'):
        from laplace.writing import dispatch_parent
        continuation=row['parent_continuation']
        if row.get('state') not in {'STARTING','WAITING','RUNNING'}:
            from laplace.work import project_work
            task=project_work._tasks(row['project'],root).get(continuation['dispatch_id'])
            if task:continuation=dispatch_parent.recorded(root,row['project'],task)
        row['parent_continuation']=dispatch_parent.public(root,row['project'],continuation)
    if not controls:return {**row,'last_control':_public_control_receipt(row.get('last_control'),project=row.get('project'),session_id=session_id)} if row else {}
    controls = _child_control_rows(root, session_id, str(row.get("turn_id") or ""), row.get("state"), limit=16, latest=True)
    last = next((control for control in controls if control.get("control_id") ==
                 (row.get("last_control") or {}).get("control_id")), row.get("last_control"))
    return {**row, "last_control": _public_control_receipt(last,project=row.get('project'),session_id=session_id),
            "controls": [_public_control_receipt(control,project=row.get('project'),session_id=session_id) for control in controls],
            "controls_total":int(row.get("control_sequence") or len(controls)),
            "controls_omitted":max(0,int(row.get("control_sequence") or len(controls))-len(controls))} if row else {}


def _terminate_owned_process(identity: dict):
    """Crash recovery only, bound to the observed process birth identity."""
    if not _process_matches(identity):
        return
    import psutil
    try:
        process = psutil.Process(identity["pid"])
        descendants = process.children(recursive=True)
        for child in reversed(descendants):
            try:child.terminate()
            except psutil.Error:pass
        if _process_matches(identity):process.terminate()
        _, alive = psutil.wait_procs(descendants + [process], timeout=3)
        for child in alive:
            try:child.kill()
            except psutil.Error:pass
    except psutil.Error:
        pass


def active_child_hosts(root: Path | None = None) -> list[dict]:
    from laplace.core.checkout import repo_root
    root = Path(root or repo_root()).resolve()
    rows = [child_execution(root, path.stem) for path in _host_directory(root).glob("WS-*.json")
            if re.fullmatch(r"WS-[a-zA-Z0-9-]+", path.stem)]
    return [row for row in rows if row.get("state") in {"STARTING", "WAITING", "RUNNING", "ORPHANED"}]


def _provider_controls(provider) -> dict:
    if provider is not None and callable(getattr(provider,"control_capabilities",None)):
        return provider.control_capabilities()
    return {"can_interrupt":True,"can_steer":False}


def _session_snapshot_url(project: str, session_id: str) -> str:
    from urllib.parse import urlencode
    return "/authoring/session?" + urlencode({"project":project,"id":session_id,"view":"summary","limit":1})


def _register_child_process(root: Path, session_id: str, turn_id: str, process, phase: str):
    """Trusted Popen callback; native JSON events cannot publish process ownership."""
    from laplace.work import project_work
    identity = _process_identity(process.pid)
    if not identity:raise ProviderError("Provider birth identity could not be observed.")
    with project_work.dispatch_lock(root):
        row = _child_execution_record(root, session_id)
        if row.get("turn_id") != turn_id or row.get("state") != "RUNNING" or row.get("host") != _process_identity():
            raise ProviderError("Provider spawn no longer belongs to this active child host.")
        identities = list(row.get("provider_processes") or [])
        if identity not in identities:identities.append(identity)
        _update_child_execution(root, session_id, {"provider_process":identity,"provider_processes":identities,
                                                "provider_phase":phase,"provider_inference_started":False}, expected_turn_id=turn_id)
        reason = _spawn_cancel_reason(root, row, session_id, turn_id)
        if reason:raise ProviderError("Provider spawn was cancelled: " + reason)


def _spawn_cancel_reason(root: Path, row: dict, session_id: str, turn_id: str) -> str | None:
    """Why an owned spawn of this execution must stop now (dispatch control, workflow deadline, Source custody)."""
    reason = dispatch_execution._child_control_reason(root, {"dispatch_id":row.get("dispatch_id"),"project":row.get("project")}, session_id)
    if row.get('workflow_execution'):
        import datetime as dt
        if dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(row['workflow_execution']['runtime_deadline_at']):
            reason = 'Workflow recipient runtime expired before provider spawn.'
    if row.get('source_execution'):
        from laplace.writing import source_execution
        try:
            control = source_execution.control(root, row['project'], turn_id)
            if control.get('stop') or control.get('state') == 'UNKNOWN':
                reason = control.get('reason') or 'Source allowance is ' + str(control.get('state'))
        except Exception as error:
            reason = 'Source allowance unavailable: ' + str(error)[:400]
    return reason


# AUXILIARY PROCESSES: an owner-created process of an active turn (a development check) that is not the provider. Its
# trusted owner may run in another process of that turn (a Claude native call runs in the provider's MCP adapter, never
# in the host), so it cannot pass the provider registrar's same-process host test, and it must not replace the
# provider's process, phase or inference facts. It joins the ONE generation it read before launch: root, session, turn
# and the host's birth identity; a newer turn, another host or an ended execution owns nothing it registered.

def auxiliary_generation(root: Path, session_id: str, turn_id: str) -> dict | None:
    """The live execution an auxiliary process of `turn_id` may join, read once before launch (None: nothing owns it)."""
    if not session_id or not turn_id:return None
    row = _child_execution_record(root, session_id)
    if row.get("turn_id") != turn_id or row.get("state") != "RUNNING" or not _process_matches(row.get("host") or {}):
        return None
    return {"root": str(Path(root).resolve()), "project": row.get("project"), "session_id": session_id,
            "turn_id": turn_id, "host": row["host"]}


def auxiliary_problem(root: Path, generation: dict) -> str | None:
    """Why `generation` no longer owns its session's execution (None while it still does)."""
    if str(Path(root).resolve()) != generation.get("root"):return "the execution root changed"
    row = _child_execution_record(root, generation["session_id"])
    if row.get("turn_id") != generation["turn_id"]:return "a newer turn owns this session"
    if row.get("host") != generation["host"]:return "the host generation changed"
    if row.get("state") != "RUNNING":return "the acting turn is " + str(row.get("state") or "not running")
    if not _process_matches(generation["host"]):return "the host process exited"
    return None


def _register_auxiliary_process(root: Path, generation: dict, process, phase: str) -> dict:
    """Trusted owner Popen callback for an auxiliary process; refuses (registering nothing) unless its generation still owns
    the execution and no spawn-cancel reason holds. Provider facts stay as the provider registrar left them."""
    from laplace.work import project_work
    identity = _process_identity(process.pid)
    if not identity:raise ProviderError("Auxiliary process birth identity could not be observed.")
    with project_work.dispatch_lock(root):
        reason = auxiliary_problem(root, generation)
        row = _child_execution_record(root, generation["session_id"])
        reason = reason or _spawn_cancel_reason(root, row, generation["session_id"], generation["turn_id"])
        if reason:raise ProviderError("Auxiliary process refused: " + reason)
        entry = {**identity, "phase": phase, "registrant": _process_identity()}
        _update_child_execution(root, generation["session_id"], {"auxiliary_processes": [*(row.get("auxiliary_processes") or []), entry]},
                                expected_turn_id=generation["turn_id"])
    return entry


def stop_auxiliary_processes(root: Path, session_id: str, turn_id: str, reason: str) -> list[dict]:
    """A selected-turn Stop's reach into the turn's auxiliaries that run in another process of it: each registered entry
    of THIS turn is marked stop-requested (its owner then reports CANCELLED) and terminated by birth identity. Another
    turn's or session's entries, and every unregistered process, are untouched."""
    from laplace.work import project_work
    with project_work.dispatch_lock(root):
        row = _child_execution_record(root, session_id)
        if row.get("turn_id") != turn_id:return []
        entries = [{**entry, "stop_requested": entry.get("stop_requested") or str(reason)[:200]} for entry in row.get("auxiliary_processes") or []]
        if entries:_update_child_execution(root, session_id, {"auxiliary_processes": entries}, expected_turn_id=turn_id)
    for entry in entries:_terminate_owned_process(entry)
    return entries


def auxiliary_stop_requested(root: Path, generation: dict, entry: dict) -> bool:
    """Whether a Stop marked this exact registered auxiliary (same generation, same birth identity)."""
    row = _child_execution_record(root, generation["session_id"])
    if row.get("turn_id") != generation["turn_id"]:return False
    return any(item.get("pid") == entry.get("pid") and item.get("created_at") == entry.get("created_at") and item.get("stop_requested")
               for item in row.get("auxiliary_processes") or [])


def terminate_child_processes(execution: dict):
    identities = list(execution.get("provider_processes") or [])
    if execution.get("provider_process") not in identities:identities.append(execution.get("provider_process") or {})
    identities += [identity for identity in execution.get("auxiliary_processes") or [] if identity not in identities]
    for identity in identities:_terminate_owned_process(identity)


def _child_execution_record(root: Path, session_id: str) -> dict:
    path = _host_path(root, session_id)
    return _read_host(path) or _read_host(path.parent / "finished" / path.name)


def _begin_child_execution(root: Path, session_id: str, admission: dict):
    """Fresh turn facts; only mailbox ordinals survive a reused session.

    A matching STARTING launch can contribute its declared launcher metadata.
    Completion, dependency and provider observations belong to the old turn.
    """
    from laplace.work import project_work
    with project_work.dispatch_lock(root):
        old = _child_execution_record(root, session_id)
        if old.get('turn_id') == admission.get('turn_id') and old.get('state') == 'RUNNING':return
        retained = {key: old[key] for key in ('control_sequence', 'control_completed_sequence') if key in old}
        if (old.get('state') == 'STARTING' and not old.get('turn_id') and
                old.get('session_id') == session_id and old.get('project') == admission.get('project') and
                old.get('dispatch_id') and old.get('dispatch_id') == admission.get('dispatch_id') and
                old.get('parent_turn_id') == admission.get('parent_turn_id') and
                _process_matches(old.get('launcher') or {})):
            retained.update({key: old[key] for key in ('launcher', 'provider', 'packet') if key in old})
        _write_host(_host_path(root, session_id), {**retained, **admission})


def _publish_execution_observation(root: Path, job: dict, provider):
    """Change-only owner capabilities on the existing public event sequence.

    Dispatch/source ownership settles before taking the job condition, so an
    event waiter never participates in a condition→dispatch lock inversion.
    The transient frontier records emitted observations, not a second authority.
    """
    # Sampling must be inside the same job-local boundary as settlement and
    # publication: concurrent governor/emitter callers cannot reverse samples.
    with job['observation_lock']:
        _publish_execution_observation_locked(root, job, provider)


def _publish_execution_observation_locked(root: Path, job: dict, provider):
    from laplace.work import project_work
    capabilities = _provider_controls(provider)
    with project_work.dispatch_lock(root):
        row = _child_execution_record(root, job['session_id'])
        if (row.get('turn_id') != job['id'] or row.get('state') != 'RUNNING' or
                row.get('project') != job['project'] or row.get('host') != _process_identity()):return
        _update_child_execution(root, job['session_id'], {'control_capabilities':capabilities,
            'provider_inference_started':bool(getattr(provider, 'inference_started', False))}, expected_turn_id=job['id'])
    with job['condition']:
        if job.get('done') or job.get('observed_capabilities') == capabilities:return
        job['observed_capabilities'] = dict(capabilities)
        job['events'].append({'type':'execution-observation', 'project':job['project'],
            'session_id':job['session_id'], 'turn_id':job['id'],
            'capabilities':{'observation':'events', 'events_url':'/authoring/events?turn='+job['id'], **capabilities},
            'seq':len(job['events'])+1})
        job['condition'].notify_all()


def _update_child_execution(root: Path, session_id: str, patch: dict, *, expected_turn_id: str | None = None):
    from laplace.work import project_work
    with project_work.dispatch_lock(root):
        path = _host_path(root, session_id)
        row = _child_execution_record(root, session_id)
        if expected_turn_id and (row.get("turn_id") != expected_turn_id or row.get("state") not in {"RUNNING","WAITING","BLOCKED"}):
            return
        if all(row.get(key) == value for key, value in patch.items()):return
        _write_host(path, {**row, **patch})


def _steer_mailbox(root: Path, session_id: str) -> Path:
    return _host_path(root, session_id).with_suffix(".controls")


def _child_control_rows(root: Path, session_id: str, turn_id: str, execution_state: str | None, *,
                        offset: int = 0, limit: int | None = None, latest: bool = False, item_id: str = "") -> list[dict]:
    rows = []
    current_host = _child_execution_record(root, session_id).get("host")
    pattern = "*-"+item_id+".request.json" if item_id else "*.request.json"
    requests = sorted(_steer_mailbox(root, session_id).glob(pattern))
    if limit is not None:requests = requests[-limit:] if latest else requests[offset:offset+limit]
    for request in requests:
        acknowledgement = request.with_name(request.name.replace(".request.json", ".ack.json"))
        receipt = _read_host(acknowledgement)
        if not receipt:
            legacy = _read_host(request)
            receipt = {"control_id": legacy.get("control_id"), "turn_id": (legacy.get("payload") or {}).get("turn_id"),
                       "state": "UNCONFIRMED", "error": "legacy control has no ordered admission receipt; it is not replayed"}
        if receipt.get("turn_id") != turn_id:continue
        host_changed = receipt.get("execution_host") and receipt["execution_host"] != current_host
        if receipt.get("state") == "ADMITTED":
            available = execution_state == "RUNNING" and not host_changed
            receipt = {**receipt, "state": "PENDING" if available else "FAILED",
                       **({"error": "admitted execution ended before delivery"} if not available else {})}
        elif receipt.get("state") == "DELIVERING" and (execution_state != "RUNNING" or host_changed):
            receipt = {**receipt, "state": "UNCONFIRMED", "error": "child ended without a native delivery acknowledgement"}
        if item_id:
            command=_read_host(request)
            if (command.get("payload") or {}).get("turn_id")==turn_id:receipt={**receipt,"payload":command["payload"]}
        rows.append(receipt)
    return rows


def _finish_child_execution(root: Path, session_id: str, turn_id: str, result_status: str | None):
    from laplace.work import project_work
    with writing_records.author_update_delivery_lock(root,turn_id), project_work.dispatch_lock(root):
        path = _host_path(root, session_id)
        row = _child_execution_record(root, session_id)
        if row.get("turn_id") != turn_id:return
        for request in sorted(_steer_mailbox(root, session_id).glob("*.request.json")):
            acknowledgement = request.with_name(request.name.replace(".request.json", ".ack.json"))
            receipt = _read_host(acknowledgement)
            if receipt.get("turn_id") != turn_id:continue
            if receipt.get("state") in {"ADMITTED", "DELIVERING", "OFFERED_AT_TOOL_BOUNDARY", "PREPARING_AT_EXACT_READ", "PREPARING_AT_TOOL_BOUNDARY", "PREPARED_AT_TOOL_BOUNDARY"}:
                from laplace.writing.provider_updates import invalidate_unpublished_input
                try:
                    disposition=invalidate_unpublished_input(root,str(row.get('project') or ''),turn_id,receipt,request=request)
                    receipt={**receipt,'context_disposition':disposition}
                    if disposition.get('error'):receipt['context_invalidation_unproved']=disposition['error']
                except (ValueError,OSError) as error:
                    receipt={**receipt,'context_invalidation_unproved':str(error)[:500]}
                prior_state=receipt['state']
                receipt = {**receipt, "state": "FAILED" if prior_state == "ADMITTED" else "OFFERED_UNACKNOWLEDGED" if prior_state=='OFFERED_AT_TOOL_BOUNDARY' else "UNCONFIRMED",
                           "terminal":True,"error": "child ended before input publication or native delivery was confirmed"}
                _write_host(acknowledgement, receipt)
                if (row.get("last_control") or {}).get("control_id") == receipt.get("control_id"):
                    row["last_control"] = receipt
        _write_host(path.parent / "finished" / path.name,
                    {**row, "state": "BLOCKED" if row.get("dependency_state")=="BLOCKED" else "FINISHED", "result_status": result_status, "finished_at": time.time()})
        path.unlink(missing_ok=True)
    if row.get('dispatch_id'):
        from laplace.writing import dispatch_parent
        dispatch_parent.notify(root,row['dispatch_id'])


from laplace.writing import records as writing_records  # noqa: E402  (the journal owner; cycle-safe, imported last)
from laplace.writing import dispatch_execution  # noqa: E402  (cycle-safe: imported last)
