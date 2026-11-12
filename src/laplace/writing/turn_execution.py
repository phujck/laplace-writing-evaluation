"""TURN EXECUTION (S1 B2): one admitted turn's live provider run, from first event to terminal reply.

Input is the immutable writing.turn_admission.TurnLaunch; its `job` dict is THE live job (the same object
writing.turn_jobs._JOBS holds and the facade's stream reads). The lifecycle, in order:

  start            one daemon thread per turn ("writing-turn"); nothing here waits under a lock.
  emit             every provider event: sequence number, job text/progress/usage, condition notify;
                   execution observations are owner facts, not provider JSON; a `session` event banks the
                   native binding row.
  _provider_turn   a dispatched child first waits for its declared predecessor returns; the effort truth
                   is read once (turn_admission.effort_as_sent); the provider service (writing_provider.WritingTurn)
                   is constructed and the governed run starts.
  _governed_run    a dispatched child or a connected observation runs a control loop beside the provider
                   (_govern: parent/author stop, observation sync, steering delivery); an interrupt before
                   the run never starts it; a provider-reported failure keeps its inference boundary.
  _failed_turn     an exception: a pre-inference failure invalidates the native binding (banked), the
                   result says which stage failed; nothing is retried.
  _bank_reply      the provider proposal is finalised, native file changes and the reply row are banked
                   once (with the dispatch parent's continuation receipt), then `complete` is emitted.
  _finish          the execution record is settled (writing.child_hosts), the job is marked done and
                   completed jobs are evicted (the newest 8 stay readable, writing.turn_jobs).

Also here: launch_child_host, the one-shot child host process a dispatched child's turn runs in.
"""
from __future__ import annotations

import functools
import json
import sys
import threading
import uuid
import time
import datetime as dt
from pathlib import Path
from typing import Any, Mapping

from laplace.writing import provider as writing_provider
from laplace.writing import records as writing_records, session_projection
from laplace.manuscript import source_effects
from laplace.writing.records import _fold


_STARTED: list = []   # this process's turn threads, so a one-shot host outlives settlement and continuation admission


def start(launch) -> None:
    """Run the admitted turn on its own daemon thread; the caller returns at once."""
    thread = threading.Thread(target=run, args=(launch,), name="writing-turn", daemon=True)
    _STARTED[:] = [*(t for t in _STARTED if t.is_alive()), thread]
    thread.start()


def running() -> bool:
    """Whether a turn this process started is still inside run(): reply, delivery settlement, finish and the once-only
    continuation admission all happen after its job is marked done, so job.done alone cannot end a host's ownership."""
    return any(thread.is_alive() for thread in list(_STARTED))


def emit(launch, event: Mapping[str, Any]) -> None:
    """One provider event into the live job, in order, with notification."""
    job = launch.job
    # Capability authority belongs to this execution owner, not provider JSON.
    if event.get('type') == 'execution-observation':
        return
    with job["condition"]:
        if event.get("type") == "delta":
            job["text"] += event.get("text", "")
        if event.get("type") == "progress":
            job["progress"] = event.get("text", "Working")
        if event.get("type") == "usage":
            job["usage"] = event.get("usage")
            job["context_window_advertised"] = event.get("context_window_advertised")
            job["context_window_effective"] = event.get("context_window_effective")
            job["context_tokens_used"] = event.get("context_tokens_used")
            job["usage_selection"] = event.get("usage_selection")
        event = {**event, "seq": len(job["events"]) + 1}
        job["events"].append(event)
        job["condition"].notify_all()
    if event.get("type") in {"session", "turn"} and job.get("provider"):
        child_hosts._publish_execution_observation(launch.root, job, job['provider'])
    if event.get("type") == "session":
        writing_records.bank(launch.root, turn_admission.binding_row(
            launch.session_id, event, tool_contract_digest=launch.contract_digest,
            native_registration_signature=launch.registration_signature,
            operating_brief_digest=launch.operating_brief["digest"]))


def run(launch) -> None:
    """The whole live turn; always ends with a done job and a settled execution record."""
    held: list = []          # the provider once constructed: the failure path reports its inference stage
    feedback_done=threading.Event();feedback_monitor=None
    if getattr(launch,'feedback_execution',None) or getattr(launch,'source_execution',None) or getattr(launch,'workflow_execution',None):
        # The SAME governor covers owned metadata preflight as well as the
        # provider run, so a silent process cannot evade the admitted deadline.
        if getattr(launch,'feedback_execution',None):launch.job['feedback_governor']=True
        if getattr(launch,'source_execution',None):launch.job['source_governor']=True
        if getattr(launch,'workflow_execution',None):launch.job['workflow_governor']=True
        launch.job['feedback_reasons']=[]
        feedback_monitor=threading.Thread(target=_govern,args=(launch,None,feedback_done,launch.job['feedback_reasons'],{}),
                                          name='writing-child-control',daemon=True)
        feedback_monitor.start()
    try:
        result = _provider_turn(launch, held)
    except Exception as exc:
        result = _failed_turn(launch, held[0] if held else None, exc)
    finally:
        feedback_done.set()
        if feedback_monitor:feedback_monitor.join()  # existing owned cleanup completes before job done
    if launch.job.get('source_limit_reason'):
        result={**result,'status':'interrupted','error':launch.job['source_limit_reason']}
    if launch.job.get('workflow_limit_reason'):
        result={**result,'status':'interrupted','error':launch.job['workflow_limit_reason']}
    if getattr(launch,'source_execution',None):
        from laplace.writing import source_execution
        try:result['source_allowance']=source_execution.status(launch.root,launch.source_execution)
        except (ValueError,OSError) as error:result['source_allowance']={'state':'UNKNOWN','stop_reason':str(error)[:400]}
    if launch.job.get('feedback_limit_reason'):
        result={**result,'status':'interrupted','error':launch.job['feedback_limit_reason']}
    if getattr(launch,'feedback_execution',None):
        result['feedback_execution']={**launch.feedback_execution,'limit_reason':launch.job.get('feedback_limit_reason'),
                                      'partial_result_retained':bool(result.get('text'))}
    provider = held[0] if held else None
    # Preserve admitted metadata even on a transport exception or early interruption.
    if provider is not None:
        facts = getattr(provider, 'usage_facts', None)
        if facts is not None:
            result.setdefault('usage_facts', facts.snapshot())
        receipt = getattr(provider, 'delivery', None)
        if receipt is not None:
            result.setdefault('delivery_receipt', receipt)
    from laplace.writing import sealed_reader
    operator=sealed_reader.operator_profile(launch.reader_profile)
    if operator:
        limit=operator['limits']['max_output_utf8_bytes']
        result['text'],clipped=sealed_reader.byte_prefix(str(result.get('text') or ''),limit)
        reason=launch.job.get('reader_limit_reason') or getattr(provider,'reader_limit_reason',None)
        if clipped:reason=reason or 'operator-public-output-bytes'
        if reason:result.update(status='interrupted',error=reason)
        if result.get('error') is not None:result['error']=sealed_reader.byte_prefix(str(result['error']),limit)[0]
        attempt={'schema_version':'laplace.sealed-reader-operator-attempt/1',
            'purpose':operator['purpose'],'limits':operator['limits'],'fingerprint':launch.reader_profile['fingerprint'],
            'input_utf8_bytes':operator['input_utf8_bytes'],'stdin_sha256':operator['stdin_sha256'],
            'limit_reason':reason,'public_output_utf8_bytes':len(result['text'].encode()),
            'elapsed_seconds':time.monotonic()-launch.job['reader_started_at'] if 'reader_started_at' in launch.job else None,
            'argv':getattr(provider,'reader_operator_argv',None),
            'argv_state':'SENT' if getattr(provider,'process',None) is not None else 'PREPARED',
            'input_delivery':((getattr(provider,'delivery',None) or {}).get('parts',{}).get('task') or {}).get('state','UNOBSERVED'),
            'provider_processes':child_hosts._child_execution_record(launch.root,launch.session_id).get('provider_processes',[]),
            'qualification_installed':False}
        if operator['purpose']==sealed_reader.DELIBERATION_PURPOSE:
            # purpose-correct metadata: an ordinary bounded deliberation is not a reader qualification attempt
            attempt.pop('qualification_installed')
            attempt.update(schema_version='laplace.sealed-reader-deliberation-attempt/1',
                           qualification_claim='none: ordinary bounded deliberation does not qualify the reader')
            result['document_deliberation']=attempt
        else:
            result['reader_qualification']=attempt
    try:
        _bank_reply(launch, result)
    except Exception as exc:
        original = (str(result.get("error") or "") if isinstance(result, Mapping) else "")
        message = original + f"; Could not save the reply: {exc}" if original else f"Could not save the reply: {exc}"
        emit(launch, {"type": "error", "message": message})
    finally:
        _finish(launch, result)


def _source_control_reason(launch):
    if not getattr(launch, 'source_execution', None):
        return None
    from laplace.writing import source_execution
    try:
        control = source_execution.control(launch.root, launch.project, launch.turn_id)
        reason = (control.get('reason') or 'Source allowance is ' + str(control.get('state')) + '.') if control.get('stop') else None
        if control.get('state') == 'UNKNOWN':
            reason = reason or 'Source allowance custody is unknown.'
    except Exception as error:
        reason = 'Source allowance unavailable: ' + str(error)[:400]
    if reason:
        launch.job['source_limit_reason'] = reason
    return reason


def _provider_turn(launch, held: list) -> dict:
    root, ident, turn_id, job = launch.root, launch.session_id, launch.turn_id, launch.job
    emitter = functools.partial(emit, launch)
    reason = _source_control_reason(launch)
    if reason:return {'status':'interrupted','text':job.get('text',''),'error':reason}
    if getattr(launch,'workflow_execution',None) and (job.get('interrupt_requested') or
            dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(launch.workflow_execution['runtime_deadline_at'])):
        return {'status':'interrupted','text':'','error':'workflow-recipient-runtime-exceeded or interrupted'}
    if getattr(launch,'feedback_execution',None) and (launch.job.get('interrupt_requested') or
            dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(launch.feedback_execution['runtime_deadline_at'])):
        launch.job['feedback_limit_reason']='feedback-review-runtime-exceeded' if not launch.job.get('interrupt_requested') else 'interrupted'
        return {'status':'interrupted','text':'','error':launch.job['feedback_limit_reason']}
    if launch.dispatch:
        dispatch_execution._await_dispatch_dependencies(root, launch.project, ident, turn_id, launch.dispatch, job, emitter)
    # EFFORT TRUTH, before the turn is built: one capability read both answers whether the flag is sendable
    # AND re-banks a settings row that disagrees with it, so the recorded effort IS the sent effort even for a
    # session opened before this installation's catalogue was discovered (turn_admission.effort_as_sent).
    on_spawn = lambda process, phase: child_hosts._register_child_process(root, ident, turn_id, process, phase)  # noqa: E731
    if launch.reader_profile:
        from laplace.writing import sealed_reader
        sealed_reader.execution_support(root,launch.project,launch.reader_profile)
        truth={'session':launch.session,'supports_effort':launch.session.get('effort') is not None}
    else:truth = turn_admission.effort_as_sent(root, launch.session, on_spawn=on_spawn)
    settings = truth["session"]
    if getattr(launch,'workflow_execution',None) and (job.get('interrupt_requested') or
            dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(launch.workflow_execution['runtime_deadline_at'])):
        return {'status':'interrupted','text':'','error':'workflow-recipient-runtime-exceeded or interrupted'}
    reason = _source_control_reason(launch)
    if reason:return {'status':'interrupted','text':job.get('text',''),'error':reason}
    if getattr(launch,'feedback_execution',None) and (launch.job.get('feedback_limit_reason') or
            dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(launch.feedback_execution['runtime_deadline_at'])):
        launch.job['feedback_limit_reason']=launch.job.get('feedback_limit_reason') or 'feedback-review-runtime-exceeded'
        return {'status':'interrupted','text':'','error':launch.job['feedback_limit_reason']}
    provider = writing_provider.WritingTurn(root, settings["provider"], settings["model"], settings["effort"],
                                   settings.get("native_id"), emitter, launch.mode, project=launch.project,
                                   logical_turn_id=turn_id, native_source_paths=set(launch.native_source_paths),
                                   session_id=ident)
    held.append(provider)
    provider.on_spawn = on_spawn
    provider.operating_brief = launch.operating_brief
    if launch.reader_profile:provider.reader_profile=launch.reader_profile
    provider.supports_effort = truth["supports_effort"]
    if launch.connected_observation:
        provider.connected_observation = launch.connected_observation
    job["provider"] = provider
    child_hosts._publish_execution_observation(root, job, provider)
    result = _governed_run(launch, provider)
    if getattr(launch,'workflow_execution',None):
        result = {**result,'settings_as_sent':{key:settings.get(key) for key in ('provider','model','effort')},
                  'settings_observation':'existing effort_as_sent owner and actual provider adapter arguments'}
    return result


def _control_reason(launch, cache: dict | None = None) -> str | None:
    if not launch.dispatch:
        return None
    return dispatch_execution._child_control_reason(launch.root, {**launch.dispatch, "project": launch.project}, launch.session_id,
                                 **({"cache": cache} if cache is not None else {}),
                                 execution_path=launch.job.get("execution_path"))


def _govern(launch, provider, done: threading.Event, reasons: list, cache: dict) -> None:
    """The control loop beside a dispatched child or a connected observation (every 50 ms until done)."""
    root, ident, job = launch.root, launch.session_id, launch.job
    while not done.wait(0.05):
        if launch.dispatch:
            child_hosts._publish_execution_observation(root, job, provider)
            process = getattr(provider, "process", None) or getattr(getattr(provider, "conn", None), "process", None)
            if process is not None and getattr(process, "pid", None):
                identity = child_hosts._process_identity(process.pid)
                if identity:
                    child_hosts._update_child_execution(root, ident, {"provider_process": identity}, expected_turn_id=launch.turn_id)
        reason = "interrupted" if job.get("interrupt_requested") else _control_reason(launch, cache)
        workflow = getattr(launch, 'workflow_execution', None)
        if workflow and dt.datetime.now(dt.timezone.utc) >= dt.datetime.fromisoformat(workflow['runtime_deadline_at']):
            reason = 'workflow-recipient-runtime-exceeded'
        if workflow and reason:
            job['workflow_limit_reason'] = reason
            if not reasons:reasons.append(reason)
            child_hosts.terminate_child_processes(child_hosts._child_execution_record(root, ident))
            active = provider or job.get('provider')
            if active and cache.get('workflow_stopped_provider') is not active:
                cache['workflow_stopped_provider'] = active
                try:active.interrupt()
                except Exception:pass
            continue
        source = getattr(launch, 'source_execution', None)
        source_reason = _source_control_reason(launch) if source else None
        if source and (source_reason or reason):
            reason = source_reason or reason
            if not reasons:reasons.append(reason)
            job['source_limit_reason'] = reason
            # The job flag stops this turn only. Shared cancellation comes
            # from the account owner's current decision, never that local flag.
            job['source_interrupt_scope'] = 'commission' if source_reason else 'turn'
            job['interrupt_requested'] = True
            from laplace.writing import source_execution
            if source_reason and not cache.get('source_stop_recorded'):
                try:source_execution.stop(root, source, reason)
                except (ValueError, OSError) as error:job['source_stop_unconfirmed'] = str(error)[:400]
                cache['source_stop_recorded'] = True
            # Only the existing registered children are stopped. An unresolved
            # Python owner claim remains spent/unknown, not cancelled or refunded.
            child_hosts.terminate_child_processes(child_hosts._child_execution_record(root, ident))
            active = provider or job.get('provider')
            if active and cache.get('source_stopped_provider') is not active:
                cache['source_stopped_provider'] = active
                try:active.interrupt()
                except Exception:pass
            continue
        feedback=getattr(launch,'feedback_execution',None)
        if feedback and dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(feedback['runtime_deadline_at']):
            reason='feedback-review-runtime-exceeded'
        if feedback and reason:
            if not reasons:reasons.append(reason)
            job['feedback_limit_reason']=reason
            # Reinspect the existing ownership record: a metadata process
            # born just after the deadline must not evade the first sweep.
            # Birth identity and TERM/KILL/reaping stay with the same owner.
            child_hosts.terminate_child_processes(child_hosts._child_execution_record(root,ident))
            active=provider or job.get('provider')
            if active and cache.get('feedback_stopped_provider') is not active:
                cache['feedback_stopped_provider']=active
                try:active.interrupt()
                except Exception:pass
            continue
        if 'reader_deadline' in cache:
            limit_reason=getattr(provider,'reader_limit_reason',None)
            if not limit_reason and time.monotonic()>=cache['reader_deadline']:limit_reason='operator-wall-seconds'
            if limit_reason:
                job['reader_limit_reason']=limit_reason;provider.reader_limit_reason=limit_reason;reason=limit_reason
        if launch.connected_observation:
            from laplace.writing import dispatch_parent
            phase_reason = dispatch_parent.sync_job(root, job, functools.partial(emit, launch))
            if reason is None:
                reason = phase_reason
        if reason:
            if not reasons:
                reasons.append(reason)
            try:
                provider.interrupt()
                if launch.dispatch and not getattr(provider, "inference_started", False):
                    child_hosts.terminate_child_processes(child_hosts._child_execution_record(root, ident))
            except Exception:
                if launch.dispatch:
                    child_hosts._terminate_owned_process(child_hosts._read_host(child_hosts._host_path(root, ident)).get("provider_process") or {})
            if 'reader_deadline' in cache:return  # the existing provider interrupt owns its grace/kill cleanup
        elif launch.dispatch:
            turn_control._deliver_child_steering(root, ident, launch.turn_id)


def _governed_run(launch, provider) -> dict:
    done, reasons, cache = threading.Event(), launch.job.get('feedback_reasons',[]), {}
    monitor = None
    from laplace.writing.sealed_reader import operator_profile
    operator=operator_profile(launch.reader_profile)
    if operator:
        launch.job['reader_started_at']=time.monotonic()
        cache['reader_deadline']=launch.job['reader_started_at']+operator['limits']['wall_seconds']
    if launch.dispatch or launch.connected_observation or operator or (getattr(launch,'feedback_execution',None) and not launch.job.get('feedback_governor')) or (getattr(launch,'source_execution',None) and not launch.job.get('source_governor')) or (getattr(launch,'workflow_execution',None) and not launch.job.get('workflow_governor')):
        monitor = threading.Thread(target=_govern, args=(launch, provider, done, reasons, cache),
                                   name="writing-child-control", daemon=True)
        monitor.start()
    try:
        reason = _source_control_reason(launch) or _control_reason(launch, cache)
        if getattr(launch,'feedback_execution',None) and (launch.job.get('feedback_limit_reason') or
                dt.datetime.now(dt.timezone.utc)>=dt.datetime.fromisoformat(launch.feedback_execution['runtime_deadline_at'])):
            reason=launch.job.get('feedback_limit_reason') or 'feedback-review-runtime-exceeded'
        if reason or launch.job.get("interrupt_requested"):
            reasons.append(reason or "interrupted")
            provider.interrupt()
            result = {"status": "interrupted", "text": ""}
        else:
            result = provider.run(launch.prompt)
        if reasons:
            result = {**result, "status": "interrupted", "error": reasons[0]}
    finally:
        done.set()
        if monitor:
            monitor.join(timeout=1)
    if result.get("status") == "failed" and not result.get("provider_stage"):
        # A provider can report a terminal failure as an ordinary turn result rather than raising. Preserve
        # the already-observed inference boundary so the next explicit attempt resumes the native conversation
        # instead of treating the binding as an unproved pre-inference connection.
        result = {**result, "provider_stage": ("inference" if getattr(provider, "inference_started", False)
                                               else "pre-inference")}
    return result


def _failed_turn(launch, provider, exc: Exception) -> dict:
    _source_control_reason(launch)
    if launch.job.get('source_limit_reason'):
        return {'status':'interrupted','text':launch.job.get('text',''),'error':launch.job['source_limit_reason'],
                'provider_stage':'inference' if getattr(provider,'inference_started',False) else 'pre-inference'}
    pre_inference = provider is None or not getattr(provider, "inference_started", False)
    previous_native_id = (getattr(provider, "native_id", None) if provider is not None else None) \
        or launch.session.get("native_id")
    binding_error = None
    if pre_inference and previous_native_id:
        try:
            writing_records.bank(launch.root, turn_admission.binding_row(
                launch.session_id, tool_contract_digest=launch.contract_digest,
                native_registration_signature=launch.registration_signature,
                model=launch.session.get("model"), reason="provider refused before inference",
                previous_native_id=previous_native_id))
        except Exception as storage_exc:  # the accepted job must still terminate
            binding_error = storage_exc
    error = str(exc)
    if binding_error is not None:
        error += "; binding invalidation was not saved: " + str(binding_error)
    reason = "interrupted" if launch.job.get('interrupt_requested') else _control_reason(launch)
    return {"status": "interrupted" if reason else "failed", "text": launch.job["text"], "error": reason or error,
            "provider_stage": "pre-inference" if pre_inference else "inference"}


def _bank_reply(launch, result: dict) -> None:
    root, project, turn_id, ident = launch.root, launch.project, launch.turn_id, launch.session_id
    saved_turn = writing_records.fold_records(root)["turns"].get(turn_id) or {}
    result = _finalize_provider_proposal(root, project, saved_turn, result)
    for change in result.get("native_file_changes") or []:
        writing_records.bank(root, {"record": "writing-native-file-change", "id": "NATIVE-" + uuid.uuid4().hex,
                             "turn_id": turn_id, "project": project, "path": change.get("path"),
                             "kind": change.get("kind"), "status": change.get("status")})
    saved_turn = writing_records.fold_records(root)["turns"].get(turn_id) or saved_turn
    result = {**result, "actions": session_projection.editor_actions(saved_turn),
              "queued_work_ids": [row["id"] for row in launch.queued_requests]}
    row = {**result, "record": "writing-reply", "id": "WR-" + uuid.uuid4().hex,
           "native_turn_id": result.get("turn_id"), "turn_id": turn_id, "session_id": ident, "project": project}
    from laplace.writing import dispatch_parent
    continuation = dispatch_parent.final_receipt(root, ident, turn_id, interrupted=result.get('status') == 'interrupted',
                                                 author_stopped=bool(launch.job.get('interrupt_requested')))
    if continuation:
        row['parent_continuation'] = continuation
    else:
        row.pop('parent_continuation', None)
    writing_records.bank(root, row)
    # the Work recipient delivery (writing.work_delivery) learns a recipient turn's terminal result HERE, on the one
    # turn path, and returns it to the submitting parent as a bounded continuation; a settlement fault is banked on
    # the job, never allowed to lose the reply above
    from laplace.work import work_delivery
    try:
        settled = work_delivery.settle_turn(root, project, ident, turn_id, result)
    except Exception as exc:
        launch.job["delivery_settlement_error"] = str(exc)[:400]
        settled = []
    if settled:
        result = {**result, "delivery_settled": settled}
    emit(launch, {"type": "complete", "result": result})


def settle_exited_host(root: Path, turn_id: str, selected: Mapping[str, Any]) -> dict | None:
    """The terminal reply of a turn whose host process exited before it saved one (recovery after a stopped or frozen
    service), banked by the ONE reply producer above on an explicit Stop. The caller holds the turn's per-turn owner
    lock (records.author_update_delivery_lock), and everything is re-read HERE, at publication: the turn must still
    have no terminal reply, and its execution record must still be the selected one (same turn, same host identity,
    still recorded as running, its host gone and no owned provider process alive). Otherwise nothing is published
    and None is returned (or ``provider_running`` while an owned provider still lives). Truthful only: no model text
    is invented (``text`` is empty), the stage is what the execution record proved (``provider_inference_started``),
    and the reply says it was settled by recovery. An interrupted turn that reached inference keeps the native
    conversation under native_continuation's existing registration and kernel guards; one that never reached
    inference is a pre-inference failure, so the native id is dropped as before. Nothing is resumed or replayed."""
    from types import SimpleNamespace
    import time
    root = Path(root)
    turn = writing_records.fold_records(root)["turns"].get(turn_id) or {}
    if not turn or turn.get("dispatch_id") or isinstance(turn.get("reply"), Mapping):
        return None
    execution = child_hosts._child_execution_record(root, turn["session_id"])
    if (execution.get("turn_id") != turn_id or execution.get("state") not in {"STARTING", "WAITING", "RUNNING"}
            or execution.get("host") != selected.get("host") or execution.get("turn_id") != selected.get("turn_id")):
        return None
    derived = child_hosts.child_execution(root, turn["session_id"])
    if derived.get("active_provider_processes") or derived.get("active_auxiliary_processes"):
        return {"provider_running": True}
    if derived.get("state") != "FAILED":
        return None
    inference = execution.get("provider_inference_started") is True
    result = {"status": "interrupted" if inference else "failed", "text": "",
              "error": "The turn's host process exited before it saved a terminal reply; settled by an explicit Stop after recovery.",
              "provider_stage": "inference" if inference else "pre-inference",
              "recovery": {"basis": "host-exited-without-terminal-reply", "host": execution.get("host"),
                           "provider_processes": list(execution.get("provider_processes") or []),
                           "provider_inference_started": inference, "settled_at": time.time()}}
    job = {"condition": threading.Condition(), "events": [], "text": "", "done": True, "interrupt_requested": True}
    launch = SimpleNamespace(root=root, project=turn["project"], turn_id=turn_id, session_id=turn["session_id"],
                             queued_requests=(), job=job)
    _bank_reply(launch, result)
    child_hosts._finish_child_execution(root, turn["session_id"], turn_id, result["status"])
    return result


def _finish(launch, result: Mapping[str, Any]) -> None:
    job = launch.job
    if getattr(launch,'source_execution',None):
        # A selected-turn Stop/finalization is not a commission Stop. Re-read
        # the same shared owner decision: a peer may still be delivering its
        # final admitted response, regardless of this job's interrupt flag.
        source_reason = _source_control_reason(launch)
        if source_reason:
            from laplace.writing import source_execution
            job['source_interrupt_scope'] = 'commission'
            try:source_execution.stop(launch.root,launch.source_execution,source_reason)
            except (ValueError,OSError) as error:job['source_stop_unconfirmed']=str(error)[:400]
        elif job.get('interrupt_requested'):
            job['source_interrupt_scope'] = 'turn'
    try:
        child_hosts._finish_child_execution(launch.root, launch.session_id, launch.turn_id, result.get("status"))
    except Exception as exc:
        job["completion_error"] = str(exc)
    finally:
        with job["condition"]:
            job["done"] = True
            job["condition"].notify_all()
    # the session is idle NOW: an approved delivery continuation that found it active is admitted once, here, through the
    # same turn owner (writing.work_delivery.admit_pending_continuations); a dispatched child never continues a parent
    if not launch.dispatch:
        from laplace.work import work_delivery
        try:
            work_delivery.admit_pending_continuations(launch.root, launch.project, launch.session_id)
        except Exception as exc:
            job["continuation_admission_error"] = str(exc)[:400]
    # Completed transcripts live in the journal, not indefinitely in RAM.
    turn_jobs.evict_finished()


def launch_child_host(root: Path, payload: Mapping[str, Any], dispatch: Mapping[str, Any], *, source_event: str | None = None,
                      source_return: str | None = None) -> dict:
    """A DISPATCHED CHILD'S TURN IS STARTED IN A PROCESS OF ITS OWN: the same door module run one-shot
    (`writing_tools.main --start-child-turn`), which sets turn_jobs.set_child_host(True) and calls straight
    back into start_turn, so there is one turn path and no second launcher. The child's membership travels on
    the host's own entry, never in the payload it reads from stdin. Only the admission handshake is bounded
    (20 s); never the governed work's lifetime or the plan's execution budget.
    A Work delivery's Source review uses the same host with `--source-event` instead of a dispatch membership: the
    host replays that event's canonical reservation (work_delivery.start_source_review); no authority is on stdin.
    Its once-only parent return uses `--source-return` (work_delivery.start_source_return) the same way."""
    import subprocess
    # The host imports laplace BEFORE any provider helper runs: bind it to the package this process actually loaded
    # (the provider's existing policy), never the inherited PYTHONPATH or the data root used as cwd.
    from laplace.writing.provider import native_code_environment
    membership = (["--source-event", str(source_event)] if source_event else
                  ["--source-return", str(source_return)] if source_return else
                  ["--dispatch-id", str(dispatch.get("dispatch_id") or ""),
                   "--parent-turn-id", str(dispatch.get("parent_turn_id") or "")])
    host = subprocess.Popen(
        [sys.executable, "-m", "laplace.native.tools", "--root", str(root),
         "--project", str(payload.get("project") or ""),
         "--mode", str(payload.get("mode") or "discuss"), "--start-child-turn", *membership],
        cwd=str(root), env=native_code_environment(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8", start_new_session=True)
    host.stdin.write(json.dumps(payload, ensure_ascii=False, default=str))
    host.stdin.close()
    lines = []
    reader = threading.Thread(target=lambda: lines.append(host.stdout.readline()), daemon=True)
    reader.start()
    reader.join(timeout=20)
    if reader.is_alive():
        host.terminate()
        host.wait(timeout=5)
        raise ValueError("Child host did not acknowledge admission within 20 seconds.")
    host.stdout.close()
    started = json.loads(lines[0]) if lines and lines[0].strip() else {}
    if not started.get("turn_id"):
        raise ValueError("The child's own door host did not start its turn: "
                         + (started.get("error") or "no answer on its stdout"))
    return {**started, "host_pid": host.pid}


from laplace.writing import child_hosts  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import dispatch_execution  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_control  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_admission  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_jobs  # noqa: E402  (cycle-safe: imported last)


# ---------------------------------------------------------------- the reply's proposal, finalised
# Moved from authoring_surface (core consolidation, family 2).

def _terminal_candidate_summary(turn: dict) -> dict | None:
    """The last sealed candidate's exact owner lineage, never text-based acceptance.

    A complete application can consume a selected subset. Its covered edit IDs
    therefore contribute to this summary, but only complete coverage of the
    candidate permits the whole-candidate complete label.
    """
    from laplace.manuscript.manuscript_proposals import edit_id
    version=turn.get('pending_proposal_version')
    candidate=(turn.get('proposal_versions') or {}).get(version)
    basis=(turn.get('proposal_bases') or {}).get(version) or {}
    if (not isinstance(candidate,dict) or not candidate.get('edits')
            or not basis.get('record_id') or version!=_fold._candidate_version(candidate,basis)):
        return None
    ids=[edit_id(edit) for edit in candidate['edits']];members=set(ids)
    applications=[];covered=set()
    for app in source_effects.applications(turn):
        consumed=set(app.get('candidate_edit_ids') or [])
        if (app.get('complete') and app.get('candidate_version')==version and app.get('id')
                and app.get('project')==turn.get('project') and app.get('turn_id')==turn.get('id')
                and consumed and consumed<=members):
            applications.append(app['id']);covered.update(consumed)
    return {'kind':'terminal-application-summary' if applications else 'terminal-candidate-summary',
            'candidate_record_id':basis['record_id'],'candidate_version':version,
            'application_ids':applications,'covered_edit_ids':[ident for ident in ids if ident in covered],
            'remaining_edit_ids':[ident for ident in ids if ident not in covered],
            'complete':covered==members}


def _finalize_provider_proposal(root: Path, project: str, turn: dict, result: dict) -> dict:
    """A terminal summary is not a newly authored proposal under later read inputs.

    Preserve the provider's raw text. Only an explicit nonempty structured
    proposal enters fresh preflight; the backend does not clone pending edits
    into that channel or infer application from a matching source-effect hash.
    """
    result={key:value for key,value in result.items() if key not in {'proposal_carrier','proposal_validation'}}
    proposal=result.get('proposal')
    if proposal is None or proposal=={} or (isinstance(proposal,dict) and proposal.get('edits')==[]):
        result['proposal']=None
        carrier=_terminal_candidate_summary(turn)
        if carrier:result['proposal_carrier']=carrier
        return result
    from laplace.manuscript import proposal_preflight
    try:validation=proposal_preflight.preflight(root,project,turn,proposal)
    except (OSError,ValueError) as exc:
        validation={'schema_version':proposal_preflight.VERSION,'valid':False,'status':'INVALID',
                    'edits':[],'errors':[f'proposal preflight could not read its source: {exc}'],'proposal':proposal}
    return {**result,'proposal':validation['proposal'],'proposal_validation':{
        key:validation[key] for key in ('schema_version','valid','status','edits','errors') if key in validation}}
