"""TURN READ BASELINES (S1 B1): what a turn has read, and when a write inside it advances those reads.

  capture_turn_read_baselines   before an owner write: snapshot the turn's affected reads and the owner files
                                (writing.mutation_attribution).
  refresh_turn_read_baselines   after the write: advance ONLY reads that were current before the write and
                                whose owner files changed exactly (_owned_changes_exact); everything else keeps
                                its original baseline (a conservative zero is the honest answer).
  refresh_context_after_read / _refresh_owned_context
                                a read inside a turn that moves the turn's owned context banks a new
                                writing-turn-context-baseline row with the rebuilt part tokens (the delta
                                in writing.turn_context.without_already_delivered then withholds them).
  failure_recovery_reads        the exact reads that recover a recorded tool failure.

Banks through records.bank and its own bank_read_baseline_groups; reads the fold through records.fold_records.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from laplace.writing import records as writing_records


def capture_turn_read_baselines(root: Path, project: str, turn_id: str, operation: str,
                                action_payload:dict|None=None) -> dict:
    """Capture affected reads which are still current before one tool mutation.

    The capture is intentionally taken before the write.  A read which has
    already moved is omitted, so the writer's later result cannot bless an
    external change that preceded its own mutation.
    """
    from laplace.writing import operations
    from laplace.writing import reads as read_contract
    from laplace.research import corpus_ingest
    turn, reads = mutation_attribution._affected_turn_reads(root, project, turn_id, operation, include_potential=True,
                                       action_payload=action_payload)
    baselines, conflicts = {}, []
    for key, read in reads:
        try:
            current = operations.replay_read(root, project, turn.get("mode", "discuss"), read, turn_id)
            digest = read_contract.comparison_digest(str(read.get("operation") or ""),current,read,root=root)
        except (OSError, ValueError):
            conflicts.append(key)
            continue
        if digest == read_contract.consumed_digest(read):
            baselines[key] = digest
        else:
            conflicts.append(key)
    context_current = False
    context_mutations={"concept_change","logical_plan_change","structure_change",
        "literature_bind","literature_import","reference_attach","reference_update",
        "reference_refresh","reference_fetch","reference_text","research_record",
        "research_reconcile","proof_check","section_change","block_change","chapter",
        "note","note_status","writing_style_change","project_guidance_change"}
    # A stale affected read already proves this action must not advance the
    # turn's whole context. Avoid rebuilding the expensive joined structure
    # merely to rediscover that fact. Artifact/run/progress writes do not alter
    # consumed authoring context and likewise need no semantic inspection.
    if turn.get("context_id") and not conflicts and operation in context_mutations:
        from laplace.pipeline import authoring
        current_context = authoring.inspect(project, turn.get("selection"), repo_root=root,
                                            context_id=turn.get("context_id") or "")
        context_current = not any(row.get("context_id") == turn["context_id"]
                                  for row in current_context.get("stale", []))
    return {"turn_id": turn_id, "operation": operation, "baselines": baselines,
            "action_payload":dict(action_payload or {}),
            "context_id": turn.get("context_id"), "context_current": context_current,
            "mutation_project":project,"mutation_operation":operation,
            "mutation_files":mutation_attribution._mutation_file_snapshot(root,project,operation,action_payload),
            "mutation_rewire_records":corpus_ingest.rewire_list(root,project),
            "conflicts": len(conflicts)}


def _refresh_owned_context(root, turn, operation, before, actual_views=None, *, attribution_ok=True):
    """Advance a pre-write-current context only across this operation's effects.

    An old external change cannot be made current by an unrelated write. Nor can
    a source/reference mutation bless a newly changed instruction or author note.
    """
    if (not attribution_ok or not before.get("context_current")
            or before.get("context_id") != turn.get("context_id")):
        return False
    from laplace.writing import operations
    from laplace.writing import reads as read_contract
    from laplace.pipeline import authoring
    affected = set(actual_views if actual_views is not None else
                   read_contract.ACTION_VIEWS.get(operation, ()))
    details = authoring.inspect(turn["project"], turn.get("selection"), repo_root=root,
                                context_id=turn.get("context_id") or "")
    stale = next((row for row in details.get("stale", [])
                  if row.get("context_id") == turn.get("context_id")), None)
    if not stale:
        return False
    def caused_by_write(reason):
        return mutation_attribution._views_cover_reason(affected,reason)
    if not all(caused_by_write(reason) for reason in stale.get("reasons", [])):
        return False
    context = authoring.build_context(turn["project"], turn.get("selection"), repo_root=root,
                                      include_guidance=False, include_orientation=True)
    # The part baseline advances with the owned context, on the row that already carries
    # that context: a part this write moved is re-delivered on the next turn, and a part
    # it did not move is still held.  One mechanism, one home, no second row kind.
    held = dict(turn.get("context_parts") or {})
    held.update({str(part.get("key")): part.get("token")
                 for part in context.get("parts") or [] if part.get("key")})
    writing_records.bank(root, {"record": "writing-turn-context-baseline", "id": "CTXBASE-" + uuid.uuid4().hex,
                 "turn_id": turn["id"], "project": turn["project"],
                 "context_id": context["context_id"], "dependencies": context["dependencies"],
                 "document": context["document"], "consumed": context["consumed"],
                 "science_context_digest": context.get("science_context_digest"),
                 "context_parts": held,
                 "cause": "current-turn-" + operation})
    return True


def refresh_turn_read_baselines(root: Path, project: str, turn_id: str, operation: str,
                                before: dict | None = None, *, actual_views=None, owned_changes=None) -> dict:
    """Advance only pre-write-current affected reads after the writer's own action.

    A later external change still differs from this post-write digest and
    refuses application; unrelated reads and reads already stale before the
    write retain their original baseline.
    """
    from laplace.writing import operations
    from laplace.writing import reads as read_contract
    action_payload=(before or {}).get("action_payload") if isinstance(before,dict) else None
    turn, reads = mutation_attribution._affected_turn_reads(root, project, turn_id, operation,
                                       actual_views=actual_views,action_payload=action_payload)
    captured = (before or {}).get("baselines") if isinstance(before, dict) else None
    if not isinstance(captured, dict):
        return {"turn_id": turn_id, "operation": operation, "refreshed": 0,
                "reason": "no-pre-write-baseline"}
    attribution_ok,attribution_reason=mutation_attribution._owned_changes_exact(root,before or {},owned_changes)
    if attribution_ok and isinstance(owned_changes,dict) and isinstance(owned_changes.get("views"),list):
        actual_views=list(owned_changes["views"])
    refreshed = 0
    candidates = []
    for key, read in reads:
        if not attribution_ok or captured.get(key) != read_contract.consumed_digest(read):
            continue
        read_operation = str(read.get("operation") or "")
        try:
            current = operations.replay_read(root, project, turn.get("mode", "discuss"), read, turn_id)
            digest = read_contract.comparison_digest(read_operation,current,read,root=root)
        except (OSError, ValueError):
            continue
        if digest == read_contract.consumed_digest(read):
            continue
        fields = (read_contract.record_read_basis(read_operation,current,read.get("payload") or {},
                    project=project,projection=read.get("projection")) if "consumption" in read
                  else {"output_sha256":digest})
        candidates.append({"operation": read_operation,
                           "payload": dict(read.get("payload") or {}),
                           **fields,
                           **({"projection":read["projection"]} if "projection" in read else {}),
                           "supersedes_read": read.get("id")})
        refreshed += 1
    baseline_records = bank_read_baseline_groups(
        root, turn_id, project, operation, candidates) if candidates else 0
    context_refreshed = _refresh_owned_context(root, turn, operation, before, actual_views,
                                                attribution_ok=attribution_ok)
    return {"turn_id": turn_id, "operation": operation, "refreshed": refreshed,
            "baseline_records": baseline_records,
            "context_refreshed": context_refreshed,
            "attribution":{"exact":attribution_ok,"reason":attribution_reason}}


def _refresh_candidate(root,project,turn_id,operation,payload):
    """Whether this read may adopt a changed context: {"turn", "reasons"} when the turn's context is stale and the read's
    views can cover a changed input, else the not-refreshed answer. Pure; shared by the refresh and the delivery plan."""
    from laplace.pipeline import authoring
    if operation=='conversation_history' and (payload or {}).get('view')=='message':
        return {'refreshed':False,'reason':'One exact public message was read; it cannot rebase author context.'}
    records=writing_records.fold_records(root);turn=records["turns"].get(turn_id)
    if not turn or turn.get("project")!=project:return {"refreshed":False,"reason":"turn unavailable"}
    if operation=='structure' and (payload or {}).get('view')=='delivery':
        return {'refreshed':False,'reason':'One exact delivery part was read; it is not a complete-context freshness rebase.'}
    if operation in mutation_attribution._TRANSIENT_APPLY_READS:return {"refreshed":False,"reason":"transient read"}
    if mutation_attribution._historical_activity_read(operation,payload):
        return {"refreshed":False,"reason":"historical audit read"}
    details=authoring.inspect(project,turn.get("selection"),repo_root=root,
                              context_id=turn.get("context_id") or "")
    stale=next((row for row in details.get("stale",[]) if row.get("context_id")==turn.get("context_id")),None)
    if not stale:return {"refreshed":False,"reason":"current context is unchanged"}
    reasons=list(stale.get("reasons") or [])
    current_views=mutation_attribution._read_views(operation,payload)
    source_may_cover_structure=(operation=="source" and
        "structure-plan-conceptric-or-evidence-changed" in reasons)
    if not source_may_cover_structure and not any(mutation_attribution._views_cover_reason(current_views,reason) for reason in reasons):
        return {"refreshed":False,"reason":"this read cannot cover the changed context",
                "uncovered":reasons,"reads_checked":0}
    return {"turn":turn,"reasons":reasons}


def deferred_refresh(context_id:str) -> dict:
    """THE DEFERRED REFRESH NOTICE: a bounded delivery had no room for the refreshed context, so the turn did not adopt
    it and no baseline was banked. Context ids are fixed-length ("CTX-" and 32 hex), so the plan sizes it exactly."""
    return {"refreshed":False,"deferred":True,"context_id":context_id,
            "reason":"The current context does not fit what this bounded delivery has left, so this turn did not "
                     "adopt it; its context stays stale until a later covering read adopts it."}


def pending_refresh_notice(root:Path,project:str,turn_id:str,operation:str,payload:dict|None=None) -> dict|None:
    """The deferred notice this read may have to carry (its turn context is stale and this read can cover it), sized
    with a fixed-length placeholder id, or None. Asked by the delivery plan before a bounded page is selected."""
    candidate=_refresh_candidate(root,project,turn_id,operation,payload)
    return None if "refreshed" in candidate else deferred_refresh("CTX-"+"0"*32)


def refresh_context_after_read(root:Path,project:str,turn_id:str,operation:str,
                               payload:dict|None=None,*,fits=None) -> dict:
    """Adopt externally changed context only after exact current reads cover it.

    This is the recovery path when mutation attribution refused an automatic
    rebase. It reuses banked tool reads and returns the newly built scoped prompt;
    unchanged reads never mint another context.
    """
    from laplace.writing import operations
    from laplace.writing import reads as read_contract
    from laplace.pipeline import authoring
    candidate_or_reason=_refresh_candidate(root,project,turn_id,operation,payload)
    if "refreshed" in candidate_or_reason:return candidate_or_reason
    turn,reasons=candidate_or_reason["turn"],candidate_or_reason["reasons"]
    def payload_without_project(read):
        return {key:value for key,value in (read.get("payload") or {}).items() if key!="project"}
    def candidate(reason,read):
        read_operation=str(read.get("operation") or "");payload=payload_without_project(read)
        if read_operation in mutation_attribution._TRANSIENT_APPLY_READS:return False
        if reason.startswith("source-revision-changed"):
            if read_operation!="source":return False
            named=reason.partition(":")[2]
            return not named or any(row.get("file")==named for row in read.get("source_scope") or [])
        if reason.startswith(("correction-unconsumed:","correction-retired:")):
            return read_operation=="author_history" and payload.get("id")==reason.partition(":")[2]
        if reason=="argument-or-framing-changed":return read_operation=="project"
        if reason=="writing-style-profile-or-guidance-changed":return read_operation=="writing_style"
        if reason=="project-working-guide-changed":return read_operation=="project_guidance"
        if reason=="concept-glossary-changed":return read_operation=="concept" and not payload.get("node")
        if reason=="reference-association-changed":return read_operation in {"references","references_attached"}
        if reason=="structure-plan-conceptric-or-evidence-changed":
            if read_operation=="structure":
                wanted={key:value for key,value in (turn.get("selection") or {}).items() if key!="project"}
                return payload==wanted or (not wanted and not payload)
            return read_operation=="source"
        return False
    selected={};required_counts={}
    for reason in reasons:
        matches=[(key,read) for key,read in (turn.get("tool_reads") or {}).items()
                 if candidate(reason,read)]
        matches.sort(key=lambda item:(str(item[1].get("ts") or ""),str(item[1].get("id") or "")))
        if reason=="project-working-guide-changed":
            from laplace.manuscript import project_protocol
            paths=[row.get("path") for row in project_protocol.load(project,root).get("documents") or []
                   if row.get("role")=="instructions" and isinstance(row.get("path"),str)]
            chosen=[]
            for path in paths or [None]:
                scoped=[item for item in matches if payload_without_project(item[1]).get("path")==path]
                if scoped:chosen.append(scoped[-1])
            selected[reason]=chosen;required_counts[reason]=len(paths) or 1
        elif matches:selected[reason]=[matches[-1]];required_counts[reason]=1
    current_reads=[]
    checked=set()
    for _reason,reason_reads in selected.items():
        for key,read in reason_reads:
            if key in checked:continue
            checked.add(key)
            read_operation=str(read.get("operation") or "")
            views=mutation_attribution._read_views(read_operation,read.get("payload") or {})
            try:
                current=operations.replay_read(root,project,turn.get("mode","discuss"),read,turn_id)
                digest=read_contract.comparison_digest(read_operation,current,read,root=root)
            except (OSError,ValueError):continue
            if digest==read_contract.consumed_digest(read):
                current_reads.append({"operation":read_operation,"views":set(views),"key":key})
    source_only_structure=False
    if any(row["operation"]=="source" for row in current_reads):
        prior=(turn.get("dependencies") or {}).get("structure")
        scope=(turn.get("dependencies") or {}).get("structure_scope") or turn.get("selection") or {}
        if isinstance(prior,dict):
            try:
                from laplace.manuscript import project_structure
                live=project_structure.context(project,scope,root)
                def without_source_revision(value):
                    value=json.loads(json.dumps(value,default=str));value.pop("revision",None);value.pop("structure_revision",None)
                    value.pop("selected_source",None)
                    if isinstance(value.get("authority"),dict):value["authority"].pop("source_revision",None)
                    return value
                source_only_structure=without_source_revision(prior)==without_source_revision(live)
            except (OSError,ValueError,TypeError,json.JSONDecodeError):pass
    uncovered=[reason for reason in reasons if len({row["key"] for row in current_reads
        if row["key"] in {key for key,_read in selected.get(reason,[])}
        and mutation_attribution._views_cover_reason(row["views"],reason)}) < required_counts.get(reason,1)
        and not (reason=="structure-plan-conceptric-or-evidence-changed" and source_only_structure)]
    if uncovered:return {"refreshed":False,"reason":"fresh reads do not cover every changed input",
                         "uncovered":uncovered,"reads_checked":len(checked)}
    context=authoring.build_context(project,turn.get("selection"),repo_root=root,
                                    include_guidance=False,include_orientation=True)
    # The recovery delivery is still a delivery into this conversation, so it pays for
    # the parts that actually moved and nothing else: the same one mechanism.
    delivery=turn_context.without_already_delivered(context.get("parts") or [],turn.get("context_parts"))
    refreshed={"refreshed":True,"context_id":context["context_id"],
            "covered_by":sorted({row["operation"] for row in current_reads}),
            "reads_checked":len(checked),"withheld":delivery["withheld"],
            "prompt":delivery["prompt"],"science_context_digest":context.get("science_context_digest")}
    if fits is not None and not fits(refreshed):
        # a bounded delivery cannot carry this refresh: no turn baseline is banked, so the turn keeps its stale context
        # (proposals still refuse on it) and a later covering read retries the refresh (writing.delivery, step 3)
        return deferred_refresh(context["context_id"])
    writing_records.bank(root,{"record":"writing-turn-context-baseline","id":"CTXREAD-"+uuid.uuid4().hex,
        "turn_id":turn_id,"project":project,"context_id":context["context_id"],
        "dependencies":context["dependencies"],"document":context["document"],
        "consumed":context["consumed"],
        "science_context_digest":context.get("science_context_digest"),
        "context_parts":delivery["held"],
        "cause":"explicit-current-reads"})
    return refreshed


def failure_recovery_reads(root:Path,project:str,turn_id:str,operation:str,payload:dict,error:str,*,
                           observed_context_reasons=None,include_named_reads=True)->dict:
    """Describe exact read calls that can recover a refused current-turn action.

    This is a pure diagnostic projection. It never performs the reads, advances a
    context baseline, or treats a retry as approval of changed evidence.
    """
    from laplace.pipeline import authoring
    root=Path(root).resolve();turn=writing_records.fold_records(root)["turns"].get(turn_id)
    if not turn or turn.get("project")!=project:return {"reads":[],"reason":"turn unavailable"}
    reads=[]
    def add(op,data,why):
        if read_contract.effect(op, data) != 'read':return
        row={"operation":op,"payload":dict(data or {}),"reason":why}
        if not any(existing["operation"]==op and existing["payload"]==row["payload"] for existing in reads):reads.append(row)
    from laplace.writing import operations
    from laplace.writing import reads as read_contract
    families=read_contract.stale_evidence_families(str(error or ""))
    if families and include_named_reads:
        for read in (turn.get("tool_reads") or {}).values():
            if read.get("operation") in families:
                add(read["operation"],read.get("payload") or {},"repeat the exact consulted read payload")
    if observed_context_reasons is None:
        details=authoring.inspect(project,turn.get("selection"),repo_root=root,
                                  context_id=turn.get("context_id") or "")
        stale=next((row for row in details.get("stale") or []
                    if row.get("context_id")==turn.get("context_id")),None)
        reasons=list((stale or {}).get("reasons") or [])
    else:reasons=list(observed_context_reasons)
    dependencies=turn.get("dependencies") or {}
    for reason in reasons:
        if reason.startswith("source-revision-changed"):
            named=reason.partition(":")[2]
            spans=[row for row in dependencies.get("selection_spans") or []
                   if not named or row.get("file")==named]
            if spans:
                for span in spans:add("source",{key:span[key] for key in ("file","line_start","line_end") if span.get(key) is not None},reason)
            elif named:add("source",{"files":[named]},reason)
            else:add("source",turn.get("selection") or {},reason)
        elif reason=="argument-or-framing-changed":add("project",{},reason)
        elif reason=="writing-style-profile-or-guidance-changed":add("writing_style",{},reason)
        elif reason=="project-working-guide-changed":
            from laplace.manuscript import project_protocol
            guides=[row for row in project_protocol.load(project,root).get("documents") or []
                    if row.get("role")=="instructions" and isinstance(row.get("path"),str)]
            if guides:
                for guide in guides:add("project_guidance",{"path":guide["path"]},reason)
            else:add("project_guidance",{},reason)
        elif reason.startswith(("correction-unconsumed:","correction-retired:")):
            add("author_history",{"id":reason.partition(":")[2]},reason)
        elif reason=="concept-glossary-changed":add("concept",{},reason)
        elif reason=="reference-association-changed":add("references",{},reason)
        elif reason=="structure-plan-conceptric-or-evidence-changed":add("structure",turn.get("selection") or {},reason)
    if operation=="apply_revision" and not reads:
        files=list(dict.fromkeys(str(edit.get("file")) for edit in (payload.get("proposal") or {}).get("edits") or []
                                if isinstance(edit,dict) and edit.get("file")))
        if files:add("source",{"files":files},"read the exact proposed source files before retrying")
    return {"reads":reads,"context_reasons":reasons,
            "note":"Perform these current reads, inspect changed content, and retry only if the proposal remains valid. Reads do not approve or rewrite changed evidence."}


def bank_read_baseline_groups(root: Path, turn_id: str, project: str,
                               cause: str, candidates: list[dict]) -> int:
    """Bank one transition per observed owner result, retaining every alias.

    Historical tool calls can spell an equivalent owner read several ways.  A
    mutation must still replay every spelling because aliases can later diverge,
    but once those replays return the same new digest their baseline transition
    is one fact.  The row retains each exact payload and superseded receipt; the
    journal index expands them back into independent guards on read.
    """
    groups: dict[tuple[str, str], list[dict]] = {}
    for candidate in candidates:
        operation = str(candidate.get("operation") or "")
        digest = str(candidate.get("output_sha256") or "")
        # Version/scope/raw identities are not interchangeable alias baselines.
        identity=json.dumps(candidate.get("consumption"),sort_keys=True)
        groups.setdefault((operation, digest, identity), []).append(candidate)
    for (operation, digest, _identity), rows in groups.items():
        primary = rows[0]
        aliases = [{"payload": dict(row.get("payload") or {}),
                    "supersedes_read": row.get("supersedes_read")}
                   for row in rows[1:]]
        writing_records.bank(root, {"record": "writing-tool-read-baseline",
                     "id": "READBASE-" + uuid.uuid4().hex,
                     "turn_id": turn_id, "project": project,
                     "operation": operation,
                     "payload": dict(primary.get("payload") or {}),
                     "output_sha256": digest,
                     **{k:primary[k] for k in ("consumption","research_raw","basis_index","projection") if k in primary},
                     "supersedes_read": primary.get("supersedes_read"),
                     **({"payload_aliases": aliases,
                         "supersedes_reads": [row.get("supersedes_read") for row in rows
                                               if row.get("supersedes_read")]}
                        if aliases else {}),
                     "caused_by_operation": cause})
    return len(groups)


from laplace.writing import mutation_attribution  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import turn_context  # noqa: E402  (cycle-safe: imported last)
