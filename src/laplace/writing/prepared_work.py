"""Join authored storyboard preparation to existing artifacts, Work and dispatch.

Preparation records an inspected cut and starts no provider. The ordinary parent
turn executes through dispatch_plan/dispatch_launch; their existing owners retain
admission, child sessions, typed returns and independent review. This module owns
only the prepared input binding, never an execution ledger or manuscript copy.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlencode

from laplace.projects import artifacts
from laplace.manuscript import bindings

SCHEMA = "laplace.prepared-storyboard-work/1"


class PreparationFailure(ValueError):
    def __init__(self, message, project, artifact, work_id=None, *, work_committed=False):
        super().__init__(message)
        from laplace.work.project_work_views import handle
        reads = [{"operation":"read_artifact", "payload":{"id":artifact["id"]},
                  "http":artifact["human_read"]["http"]}]
        if work_id:
            reads.append(handle(project,{"view":"detail","id":work_id}))
        self.details = {"preparation_publication": {"state":"ARTIFACT_RETAINED", "complete":False,
            "artifact": {key:artifact[key] for key in ("id","revision","path","read_handle","human_read")},
            "work_id":work_id, "work_publication":"COMMITTED" if work_committed else "UNCONFIRMED"},
            "next_reads":reads,
            "recovery":"Inspect the retained input artifact and any Work first. Preparation is idempotent for the same inspected cut; a changed cut requires explicit fresh preparation."}


def error_details(error):
    for _ in range(8):
        if isinstance(error,PreparationFailure):
            return dict(error.details)
        if error is None:
            break
        error = error.__cause__ or error.__context__
    return {}


def _digest(value):
    raw = value if isinstance(value, bytes) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def operation_contract():
    from laplace.core import identity_doors
    string = {"type": "string", "minLength": 1}
    return {"required": ["operation", "expected_plan_revision", "expected_selection", "section_ids"],
            "properties": {"operation": {"const": "prepare_work"}, "project": string,
                           "expected_plan_revision": string, "expected_selection": string,
                           "expected": identity_doors.EXPECTED_FIELD,
                           "section_ids": {"type": "array", "minItems": 1, "maxItems": 16,
                                           "uniqueItems": True, "items": string}}}


def action(project, plan_revision, selection_identity, section_ids):
    return {"operation": "structure_change", "http": {"method": "POST", "route": "/work/structure/change"},
            "project": project, "payload": {"operation": "prepare_work",
                "expected_plan_revision": plan_revision, "expected_selection": selection_identity,
                "section_ids": list(section_ids)},
            "effects": "Prepare durable Work and an exact input artifact; starts no provider."}



def _literature_inputs(project, root, sections):
    """Passage support is a consumed basis separate from reader-plan BibTeX pins."""
    from laplace.research import literature_support
    net = literature_support.network(project, root)
    nodes = net.get("nodes") or {}
    ids = set(ident for section in sections for ident in section.get("nodes_in_order") or [])
    pending = list(ids)
    while pending:
        current = pending.pop()
        for edge in net.get("relations") or []:
            target = edge.get("target")
            if (edge.get("source") == current and edge.get("rel") == "prerequisite"
                    and isinstance(target, str) and target not in ids):
                ids.add(target)
                pending.append(target)
        if len(ids) > 100:
            raise ValueError("Prepare a smaller reader-plan scope: more than 100 support/prerequisite nodes.")
    observed = []
    for ident in sorted(ids):
        if ident not in nodes:
            observed.append({"node": ident, "status": "UNAVAILABLE"})
            continue
        value = literature_support.for_node(project, ident, root, net=net)
        if len(value.get("sources") or []) > 100:
            raise ValueError("Prepare a smaller support scope: more than 100 sources for one claim.")
        basis = {key: value.get(key) for key in
                 ("node", "meaning_revision", "sources", "own_evidence", "documented_proof",
                  "declared_role", "gaps", "qualification")}
        observed.append({"node": ident, "revision": _digest(basis),
                         "qualification": value.get("qualification"),
                         "gaps": value.get("gaps") or []})
    return {"nodes": observed,
            "qualification": "Current scoped support observation, not independent scientific acceptance. "
                "Citation/build completion is assessed separately by literature_scope."}


def _inputs(project, root, section_ids):
    from laplace.manuscript import storyboard
    from laplace.pipeline import schema
    from laplace.manuscript.reader_plan import _paths
    loaded = storyboard._load_plan(project, root)
    if loaded is None:
        raise ValueError("This project has no authored reader plan to prepare. Source-only editing remains available.")
    path, _ = loaded
    plan_raw = path.read_bytes()
    plan = json.loads(plan_raw)
    sections = {row["id"]: row for row in schema.plan_sections(plan)}
    if (not isinstance(section_ids,list) or not 1 <= len(section_ids) <= 16
            or any(not isinstance(ident,str) or not ident for ident in section_ids)
            or len(set(section_ids)) != len(section_ids) or set(section_ids) - sections.keys()):
        raise ValueError("Prepare exact existing reader-plan section IDs; no section was inferred.")
    source, tree = bindings.selected_tree(project, root)
    if source.get("status") != "resolved" or tree.get("diagnostics"):
        raise ValueError("Inspect the selected source and its complete include tree before preparing work.")
    # These are input identities, not copied manuscript bodies. Source scope is
    # the selected include tree, honestly retained even for an unbound section.
    revisions = {path.relative_to(root).as_posix(): _digest(plan_raw)}
    revisions.update({row["file"]: "sha256:" + row["raw_file_sha256"].removeprefix("sha256:")
                      for row in tree.get("sources", [])})
    for section_id in section_ids:
        for reader_path in _paths(project, root, section_id, plan=plan):
            revisions[reader_path.relative_to(root).as_posix()] = (
                _digest(reader_path.read_bytes()) if reader_path.is_file() else None)
    from laplace.manuscript import project_structure
    observed = project_structure.read(project,{'view':'detail','section_ids':section_ids},root)
    reader_checks,reader_bases = [],[]
    for row in observed.get('sections',[]):
        transition,paragraphs = row.get('reader_transition') or {},row.get('paragraph_plan') or {}
        page = paragraphs.get('paragraphs') or {}
        items = [{key:item[key] for key in ('paragraph_id','identity_status','input_currentness','diagnostics','read_handle') if key in item}
                 for item in page.get('items',[])]
        reader_checks.append({'section_id':row['id'],
            'reader_transition':{key:transition[key] for key in ('status','input_currentness','diagnostics') if key in transition},
            'paragraph_plan':{key:paragraphs[key] for key in ('status','identity_status') if key in paragraphs},
            'paragraph_count':page.get('total',0),'paragraphs':items,
            'paragraphs_omitted':max(0,page.get('total',0)-len(items)),'paragraph_next_read':page.get('next_read'),
            'read_handle':{'operation':'structure','payload':{'view':'detail','section_ids':[row['id']]}},
            'qualification':'Existing M2 authored reader-state diagnostics and input freshness; not review, reader comprehension or scientific validity.'})
        reader_bases.extend([transition['reader_basis']] if transition.get('reader_basis') else [])
        reader_bases.extend(item['reader_basis'] for item in page.get('items',[]) if item.get('reader_basis'))
        order_basis = ((paragraphs.get('reorder_action') or {}).get('payload') or {}).get('expected_reader_basis')
        if order_basis:
            reader_bases.append(order_basis)
    basis = {"preparation_contract":"laplace.manuscript.storyboard-preparation/3",
             "project": project, "plan_path": path.relative_to(root).as_posix(),
             "plan_revision": revisions[path.relative_to(root).as_posix()],
             "selection_identity": source["selection_identity"],
             "section_ids": list(section_ids), "input_revisions": revisions,
             "reader_input_bases":reader_bases,
             "literature_support": _literature_inputs(project, root, [sections[ident] for ident in section_ids])}
    return basis, [sections[ident] for ident in section_ids],reader_checks


def _read_binding(project, root, binding):
    if (not isinstance(binding, dict) or set(binding) != {"artifact_id", "revision"}
            or not isinstance(binding["artifact_id"], str) or not isinstance(binding["revision"], str)):
        raise ValueError("Prepared Work requires its exact artifact identity and revision.")
    read = artifacts.read(root, project, {"id": binding["artifact_id"], "limit": 40_000})
    if read.get("revision") != binding["revision"] or read.get("recorded_revision") != binding["revision"]:
        raise ValueError("The prepared artifact changed; retain the old Work and explicitly prepare a new inspected cut.")
    # The complete bounded artifact is required. A truncated first page must
    # never be mistaken for a complete execution contract.
    path, _, _, _ = artifacts.target(root, project, {"id": binding["artifact_id"]})
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != binding["revision"]:
        raise ValueError("The prepared artifact changed during inspection; nothing was admitted.")
    if len(raw) > 200_000:
        raise ValueError("The prepared contract exceeds its bounded owner read.")
    value = json.loads(raw)
    if value.get("schema_version") != SCHEMA or value.get("project") != project:
        raise ValueError("The prepared artifact does not belong to this storyboard/project contract.")
    return value, read


def observe(project, root, binding):
    """Currentness of preparation is distinct from Work/result acceptance."""
    root = Path(root).resolve()
    try:
        value, read = _read_binding(project, root, binding)
        current, _,_ = _inputs(project, root, value["basis"]["section_ids"])
        same = current == value["basis"]
        return {"status": "CURRENT" if same else "STALE", "current": same,
                "basis": value["basis"], "observed_basis": current,
                "artifact": {"id": binding["artifact_id"], "revision": binding["revision"],
                             "read_handle": {"operation": "read_artifact", "payload": {"id": binding["artifact_id"]}},
                             "human_read": read.get("human_read")},
                "provider_started": False,
                "recovery": "Inspect current reader plan/source and explicitly prepare a new cut; retained Work is unchanged."}
    except (ValueError, KeyError, OSError) as error:
        return {"status": "UNAVAILABLE", "current": False, "error": str(error),
                "recovery": "Inspect the retained Work/artifact and current reader plan before explicitly preparing again."}


def require_current(project, root, task, *, mode, session=None, dispatch=None):
    """Prepared execution is a deliberate author-parent act before any effects."""
    from laplace.work.project_work import WorkConflict
    if mode != "work" or dispatch or session and (
            session.get("role", "author") != "author" or session.get("dispatch_id")):
        raise ValueError("Run prepared Work in a deliberate author parent conversation, in work mode; a reviewer or child cannot run it.")
    observation = observe(project, root, task["prepared_storyboard"])
    if not observation["current"]:
        error = WorkConflict("Prepared inputs changed or are unavailable. No provider was started; inspect and explicitly prepare again.",
                             project, task["id"], field="prepared_storyboard")
        error.details["preparation"] = observation
        raise error
    execution = executions(project, root, task["id"])
    prior = execution["items"][-1] if execution["items"] else None
    if (execution["running"] or prior and (not session or session.get("id") != prior["session_id"])):
        error = WorkConflict("Inspect/resume the recorded parent conversation for this prepared Work; a running parent or a different new conversation cannot start duplicate execution.",
                             project, task["id"], field="prepared_execution")
        error.details["execution"] = execution
        raise error
    return observation


def executions(project, root, work_id):
    """Bounded metadata from existing turns/jobs, never a second live-job owner."""
    from laplace.writing import child_hosts, turn_jobs
    from laplace.writing import records
    index = records.index(root)
    turns = [row for row in index.by_project.get(project, [])
             if row.get("record") == "writing-turn" and row.get("work_id") == work_id
             and not row.get("dispatch_id")]
    items, unresolved, running, hosts = [], False, False, {}
    for row in turns:
        replies = [value for value in index.by_turn.get(row["id"], [])
                   if value.get("record") == "writing-reply"]
        job = turn_jobs._JOBS.get(row["id"])
        session_id = row["session_id"]
        if session_id not in hosts:
            try:
                hosts[session_id] = child_hosts.child_execution(root, session_id)
            except ValueError:
                hosts[session_id] = {}
        host = hosts[session_id] if hosts[session_id].get("turn_id") == row["id"] else {}
        owned_active = host.get("state") in {"STARTING", "WAITING", "RUNNING", "ORPHANED", "UNKNOWN-OWNERSHIP"}
        state = "RUNNING" if (job and not job.get("done")) or owned_active else (
            str(replies[-1].get("status") or "TERMINAL").upper() if replies else "UNCONFIRMED")
        unresolved = unresolved or state in {"RUNNING", "UNCONFIRMED"}
        running = running or state == "RUNNING"
        continuation=host.get('parent_continuation')
        if continuation is None and replies:
            from laplace.writing import dispatch_parent
            retained=records.selected_journal_fields(project,replies[-1]['id'],root,fields=['parent_continuation']).get('parent_continuation')
            if retained:continuation=dispatch_parent.public(root,project,retained)
        items.append({"turn_id": row["id"], "session_id": row["session_id"], "state": state,
            **({'parent_continuation':continuation} if continuation else {}),
            "session_read": {"http": {"method": "GET", "url": "/authoring/session?" + urlencode({
                "id": row["session_id"], "view": "summary", "limit": 20})}},
            "execution_state": host.get("state"),
            "turn_read": {"operation": "author_history", "payload": {
                "view": "record", "id": "activity:journal:" + row["id"]}}})
    from laplace.work import project_work
    from laplace.writing import dispatch_parent
    tasks=project_work._tasks(project,root);parent=tasks.get(work_id) or {}
    retained=[]
    for ident in dict.fromkeys(parent.get('depends_on') or []):
        dispatch=tasks.get(ident) or {}
        if dispatch.get('task_kind')!='dispatch' or dispatch.get('parent_work_id')!=work_id or not dispatch.get('dispatch_parent_observation'):continue
        continuation=dispatch_parent.recorded(root,project,dispatch)
        if continuation:retained.append(dispatch_parent.public(root,project,continuation,task=dispatch))
    return {"items": items[-20:], "omitted": max(0, len(items) - 20), "unresolved": unresolved, "running": running,
            'retained_dispatches':retained,
            **({'parent_continuation':retained[0]} if len(retained)==1 else {}),
            "scope": "Existing prepared parent turns; metadata only. Unconfirmed does not prove process activity."}


def run_action(project, owned, preparation, execution):
    prior = execution["items"][-1] if execution["items"] else None
    continuation=execution.get('parent_continuation') or ((prior or {}).get('parent_continuation') if 'retained_dispatches' not in execution else None)
    multiple=len(execution.get('retained_dispatches') or [])>1
    retained=("Resume the exact retained dispatch "+continuation['dispatch_id']+" from its Work detail and declared plan. "
        "Do not create another dispatch or replay children. Read the exact original plan/prepared inputs and every available child return, "
        "including rejected outcomes. Retain the declared parent-consumes synthesis and attach it with task_status using current guards. "
        if continuation else "Execute this prepared storyboard Work through its exact artifact and the existing dispatch loop. "
        "Inspect its artifact, create a dispatch_plan with worker and independent judge packets and a distinct synthesis_return_path, "
        "then launch it once. ")
    return {"http": {"method": "POST", "route": "/authoring/turn"},
        "project": project, "requires_role": "author-parent",
        "label": "Resume recorded parent" if prior else "Run prepared work",
        **({'reason':'Inspect and select an exact retained dispatch Work before composing recovery; no new dispatch is implied.'} if multiple else {}),
        "permitted": preparation.get("current") is True and not execution["running"]
                     and not multiple
                     and owned.get("status") in {"open", "ready", "in-progress", "blocked"},
        "provider_cost": ("Starts a new explicit parent provider turn; retained dispatch children are inspected and not replayed."
            if continuation else "Select an exact retained dispatch first; this action starts no provider turn."
            if multiple else "Starts a parent provider turn; its dispatch explicitly starts worker/reviewer turns."),
        "payload": {"project": project, "mode": "work", "work_id": owned["id"],
            **({'session_id':continuation['origin_parent_session_id']} if continuation else {"session_id":prior["session_id"]} if prior else {}),
            "expected_work_scope_revision": owned["work_scope_revision"],
            "expected_dependency_revision": owned["dependency_revision"],
            "text": ("Inspect and select an exact retained dispatch before recovery; do not create another dispatch. " if multiple else retained)+"Consume exact owner reads and retain result/evidence/recovery. "
                    "Complete dispatch and Work only after successful typed returns and accepted current review coverage. "
                    "Source changes require their existing inspected source guards; preparation itself is not an application or scientific acceptance."}}


def _receipt(project, root, task, reused):
    from laplace.work import project_work
    detail = project_work.read(project, {"view": "detail", "id": task["id"]}, root)
    owned = detail["task"]
    preparation = observe(project, root, task["prepared_storyboard"])
    execution = executions(project, root, task["id"])
    summary = {key: preparation[key] for key in ("status", "current", "recovery") if key in preparation}
    summary.update(basis_revision=_digest(preparation.get("basis")),
                   observed_basis_revision=_digest(preparation.get("observed_basis")))
    return {"ok": True, "changed": not reused, "reused": reused, "provider_started": False,
            "effects":["project","pipeline","artifact"],
            "work_id": owned["id"], "work_read": owned["read_handle"],
            "task": {key:owned[key] for key in ("id", "title", "goal", "status", "evidence", "read_handle",
                "section_ids", "work_scope_revision", "dependency_revision", "prepared_storyboard") if key in owned},
            "preparation": summary, "execution": execution, "artifact": preparation.get("artifact"),
            "run_action": run_action(project, owned, preparation, execution),
            **({"owned_changes":task["owned_changes"]} if task.get("owned_changes") else {})}


def prepare(project, payload, root):
    """Idempotent preparation for one exact inspected plan/source/input cut."""
    from filelock import FileLock
    from laplace.work import project_work
    from laplace.manuscript import storyboard
    root = Path(root).resolve()
    loaded = storyboard._load_plan(project, root)
    if loaded is None:
        raise ValueError("This project has no authored reader plan to prepare.")
    # Share the existing plan publication lease. A concurrent source update is
    # checked again after the artifact/Work publication and will refuse Run.
    with FileLock(str(loaded[0]) + '.publication.lock', timeout=15), project_work.dispatch_lock(root):
        basis, sections,reader_checks = _inputs(project, root, payload["section_ids"])
        from laplace.core import identity_doors
        identity_doors.gate("structure_change prepare_work", supplied=payload,
            homes=[("plan-file",project,basis["plan_revision"])], required=["expected_plan_revision"],
            said="CHANGED_INPUT: prepared storyboard plan changed; inspect current structure before preparing.")
        if payload.get("expected_selection") != basis["selection_identity"]:
            raise ValueError("CHANGED_INPUT: prepared storyboard selection changed; inspect current source before preparing.")
        ident = "WORK-storyboard-" + _digest(basis).removeprefix("sha256:")[:32]
        old = project_work._tasks(project, root).get(ident)
        if old:
            return _receipt(project, root, old, True)
        value = {"schema_version": SCHEMA, "project": project, "basis": basis,
                 "sections": sections,
                 "reader_checks":reader_checks,
                 "structure_read": {"operation": "structure", "payload": {"view": "detail", "section_ids": basis["section_ids"]}},
                 "source_read": {"operation": "source", "payload": {"files": sorted(
                     path for path in basis["input_revisions"] if path.endswith(".tex"))}},
                 "execution": {"owner": "project_work/authoring_surface", "operations": [
                     "dispatch_plan", "dispatch_launch", "dispatch_status", "dispatch_returns", "task_status"],
                     "scope": "project", "source_application": "Existing guarded operations only; no automatic regeneration.",
                     "completion": "Successful typed worker returns, accepted independent review and explicit parent evidence."}}
        relative = "development/prepared-storyboard-" + ident.removeprefix("WORK-storyboard-") + ".json"
        path = artifacts.resolve_path(root, project, relative)
        content = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
        if len(content.encode()) > 200_000:
            raise ValueError("Prepare a smaller explicit reader-plan scope; this execution contract exceeds 200KB.")
        if path.is_file():
            # Recover a previous artifact effect before Work publication failed.
            if path.read_text(encoding="utf-8") != content:
                raise ValueError("A retained preparation artifact conflicts with this input cut; inspect it without overwriting.")
            from laplace.writing import records
            record = next((row for row in records.index(root).by_project.get(project, [])
                           if row.get("record") == "writing-artifact" and row.get("path") == path.relative_to(root).as_posix()
                           and row.get("sha256") == hashlib.sha256(content.encode()).hexdigest()), None)
            if record is None:
                raise ValueError("Prepared artifact has no retained owner receipt; inspect it before recovery.")
            saved = {"id": record["id"], "revision": record["sha256"], "path": record["path"],
                     "read_handle":{"operation":"read_artifact","payload":{"id":record["id"]}},
                     "human_read":artifacts.human_read(project,record['artifact_path'],record['scope'],record['sha256'],record['id'])}
        else:
            saved = artifacts.store(root, project, {"path": relative, "before": None, "content": content,
                                                   "reason": "Prepare exact storyboard Work; no provider or source effect."})
        task = None
        # The same sections prepared again on changed inputs are a new attempt, not the
        # same Work: the title says so, so two catalogue rows are never twins.
        earlier = sum(1 for row in project_work._tasks(project, root).values()
                      if row.get("origin") == "storyboard-preparation" and row.get("section_ids") == basis["section_ids"])
        title = "Develop reader plan: " + ", ".join(basis["section_ids"]) + (f" · attempt {earlier + 1}" if earlier else "")
        try:
            task = project_work.task(project, {"id": ident, "title": title,
                "goal": "Execute the prepared storyboard cut through reviewed dispatch, retain results and exact evidence, and report unresolved obligations.",
                "kind": "execution", "section_ids": basis["section_ids"], "evidence": [saved["path"]],
                "origin": "storyboard-preparation"}, root,
                prepared_storyboard={"artifact_id": saved["id"], "revision": saved["revision"]})
            return _receipt(project, root, task, False)
        except (ValueError,OSError) as error:
            raise PreparationFailure("Prepared inputs were retained, but Work publication/inspection did not finish: " + str(error),
                                     project,saved,ident,work_committed=task is not None) from error


def programme_create_action(project, root):
    """Create one explicit all-seven contract through ordinary Work closures."""
    import uuid
    from laplace.writing import stages
    recipe = stages.programme(root)
    ident = "WORK-" + uuid.uuid4().hex
    required = {phase["id"]: "WORK-writing-" + _digest([ident, phase["id"]]).removeprefix("sha256:")[:24]
                for phase in recipe["phases"]}
    return {"operation": "task", "payload": {
        "id": ident, "title": recipe["title"], "goal": recipe["purpose"],
        "kind": "programme", "logical_target": {"kind": "writing-programme"},
        "review_obligations": [{"id": "stage-" + phase["id"], "scope": "closure",
            "label": "Required manuscript stage: " + phase["title"], "required": True,
            "independent": False, "closure_work_id": required[phase["id"]]}
            for phase in recipe["phases"]]},
        "after": "Declare exact section_ids or logical_target.node_id claim scope, select this Work "
            "in the original author session, then re-read pipeline. All seven missing stages already block Done.",
        "parent_read": {"operation": "session_settings", "payload": {"view": "connection"}},
        "effects": "Work contract only. No provider or manuscript effect."}


def _programme_goal(recipe, phase):
    return (phase["guidance"] + "\nCompletion: " + phase["completion"]
            + "\nCatalogue: " + recipe["revision"])


def programme_route(project, root, work_id, *, origin_parent_session_id=None):
    """Compose existing task/transition/turn actions, never execute or schedule them.

    The programme marker is an ordinary logical target. Stage roles are ordinary
    Work kinds in the owned catalogue. No parallel or shadow lifecycle is kept.
    Acquisition Work is a separate final join, not a draft prerequisite.
    """
    from laplace.work import project_work
    from laplace.writing import stages, records
    root = Path(root).resolve()
    detail = project_work.read(project, {"view": "detail", "id": work_id}, root)
    parent = detail["task"]
    tasks = project_work._tasks(project, root)
    raw_parent = tasks[work_id]
    # Detail is a bounded projection, not the stored opt-in contract.
    problem = _contract_problem(raw_parent)
    if problem:
        return {"work_id": work_id, "issues": [problem], "next_action": None,
                "join_action": None, "phases": [], "original_parent_session_id": None}
    if not _is_programme(raw_parent):
        raise ValueError("Select an ordinary writing-programme Work, not an inferred title")
    contract = raw_parent["manuscript_programme"]
    recipe = contract["recipe"]
    required_stages = contract["required_stages"]
    children = [row for row in tasks.values() if row.get("parent_work_id") == work_id]
    index = records.index(root)
    # Earliest recorded programme turn fixes the original parent, not the latest
    # session that happens to request this read.
    turns = [row for row in index.by_project.get(project, [])
             if row.get("record") == "writing-turn" and row.get("work_id") == work_id
             and not row.get("dispatch_id")]
    original = turns[0].get("session_id") if turns else origin_parent_session_id
    issues = []
    if turns and origin_parent_session_id and original != origin_parent_session_id:
        issues.append("Resume the recorded original parent, not a replacement session.")
    if original:
        sessions = [row for row in index.by_id.get(original, ())
                    if row.get("record") == "writing-session"
                    and index.project(row) == project
                    and row.get("role", "author") == "author" and not row.get("dispatch_id")]
        if len(sessions) != 1:
            issues.append("Original author-parent session is unavailable.")
    else:
        issues.append("Select this programme in the original author session first. No new parent is implied.")

    rows, selected, executions_by_id = [], {}, {}
    invalid_stage_reads = []
    for phase in recipe["phases"]:
        matches = [row for row in children if row["id"] == required_stages[phase["id"]]]
        if len(matches) > 1:
            issues.append("Multiple retained Works for " + phase["id"] + "; explicitly reconcile attempts.")
        if len(matches) != 1:
            rows.append({"phase": phase["id"], "work_id": None, "status": "NOT_PREPARED"})
            continue
        child = matches[0]
        owned_detail = project_work.read(project, {"view": "detail", "id": child["id"]}, root)
        owned = owned_detail["task"]
        selected[phase["id"]] = (owned, owned_detail)
        problem = _contract_problem(child)
        if problem:
            issues.append("Required stage " + owned["id"] + ": " + problem
                          + " No admissible automatic re-preparation is available; inspect this child.")
            invalid_stage_reads.append({"work_id": owned["id"], "kind": "MANUSCRIPT_CONTRACT_INVALID",
                                        "reason": problem, "read": owned["read_handle"]})
        execution = executions(project, root, owned["id"])
        executions_by_id[owned["id"]] = execution
        expected_deps = [selected[ident][0]["id"] for ident in phase["depends_on"] if ident in selected]
        if (len(expected_deps) != len(phase["depends_on"])
                or owned.get("depends_on", []) != expected_deps):
            issues.append("Changed predecessor binding for " + phase["id"] + "; explicitly reconcile Work.")
        if owned["goal"] != _programme_goal(recipe, phase):
            issues.append("Changed programme recipe for " + phase["id"] + "; explicitly replan its Work.")
        rows.append({"phase": phase["id"], "work_id": owned["id"],
                     "status": owned["status"], "current_acceptance": owned.get("current_acceptance"),
                     "read": owned["read_handle"]})
    parent_execution = executions(project, root, work_id)
    busy = parent_execution["unresolved"] or any(item["unresolved"] for item in executions_by_id.values())
    # Retained dispatch observations can outlive a settled parent turn. Their
    # existing run_action is the recovery route, never permission to replay.
    required = [row["work_id"] for row in rows if row["work_id"]]
    required += _required_acquisitions(work_id, tasks)
    dependencies = list(dict.fromkeys([*(parent.get("depends_on") or []), *required]))
    join = None
    if dependencies != parent.get("depends_on", []):
        join = {"operation": "task", "payload": {
            **detail["allowed_actions"]["task"]["payload"],
            "title": parent["title"], "goal": parent["goal"], "depends_on": dependencies}}

    next_action = None
    # A malformed stored contract is not a valid stale consumed cut. The task
    # writer rejects that prior: do not advertise a dead-end rebind or run.
    if invalid_stage_reads:
        join = None
    for phase in (() if invalid_stage_reads else recipe["phases"]):
        item = selected.get(phase["id"])
        if item and (item[0].get("readiness") or {}).get("satisfies_prerequisites"):
            continue
        predecessors = [selected.get(ident) for ident in phase["depends_on"]]
        eligible = all(item and (item[0].get("readiness") or {}).get("satisfies_prerequisites")
                       for item in predecessors)
        if not item:
            if eligible and not issues and not busy:
                next_action = {"operation": "task", "payload": {
                    "id": required_stages[phase["id"]],
                    "title": phase["title"], "goal": _programme_goal(recipe, phase),
                    "kind": phase["work_kind"], "parent_work_id": work_id,
                    "depends_on": [item[0]["id"] for item in predecessors],
                    "section_ids": parent.get("section_ids") or [],
                    "logical_target": {"kind": "writing-stage-cut", "node_id": _digest(_stage_cut(project, root, raw_parent, phase))},
                    **({"review_obligations": phase["review_obligations"]} if phase.get("review_obligations") else {})},
                    "after": "Re-read pipeline, join required Work, then explicitly run in the original parent."}
        else:
            owned, owned_detail = item
            raw_stage = tasks[owned["id"]]
            currency = stage_currentness(raw_stage, tasks, root)
            if currency and currency["status"] != "CURRENT":
                cut = _stage_cut(project, root, raw_parent, phase)
                next_action = {"operation": "task", "payload": {
                    **owned_detail["allowed_actions"]["task"]["payload"],
                    "title": owned["title"], "goal": owned["goal"],
                    "logical_target": {"kind": "writing-stage-cut", "node_id": _digest(cut)}},
                    "currentness": currency,
                    "after": "Explicit cut re-preparation retains prior history. Re-read Work and set in-progress "
                        "through its current standing action before executing/completing the new cut. No human approval gate."}
                break
            execution = executions_by_id[owned["id"]]
            if execution.get("retained_dispatches") or execution.get("parent_continuation"):
                next_action = run_action(project, owned, {"current": True}, execution)
                next_action["permitted"] = (next_action["permitted"] and eligible
                                            and not issues and not busy and join is None)
            else:
                next_action = {"http": {"method": "POST", "route": "/authoring/turn"},
                    "permitted": (eligible and not issues and not busy and join is None
                                  and owned.get("status") in {"open", "ready", "in-progress"}),
                    "payload": {"project": project, "mode": "work", "work_id": owned["id"],
                        **({"session_id": original} if original else {}),
                        "expected_work_scope_revision": owned["work_scope_revision"],
                        "expected_dependency_revision": owned["dependency_revision"],
                        "text": _programme_goal(recipe, phase) +
                            "\nUse ordinary sequential Work. One active job in this lane. "
                            "Read the current predecessor evidence and actual source/support basis. "
                            "Existing guarded authorized source application is permitted by the commission. "
                            "Preserve direct author Save without repeated human permission gates. "
                            "Retain result/evidence and original-parent recovery. No automatic next-stage launch."}}
            next_action["transition_read"] = owned["read_handle"]
            next_action["standing"] = owned_detail["allowed_actions"]["task_status"]
        break
    if next_action and next_action.get("payload", {}).get("session_id") not in (None, original):
        issues.append("Retained dispatch belongs to a different original parent.")
        next_action["permitted"] = False
    if issues and next_action:
        next_action["permitted"] = False
    return {"work_id": work_id, "read": parent["read_handle"],
            "revision": recipe["revision"], "original_parent_session_id": original,
            "phases": rows, "issues": issues, "unresolved_execution": bool(busy),
            "join_action": join, "next_action": next_action,
            "invalid_stage_reads": invalid_stage_reads,
            "completion_read": parent["read_handle"],
            "qualification": "Ordinary Work acceptance and explicit parent actions, not scientific acceptance. "
                "Literature-support handoff is distinct from acquisition citation/build completion.",
            "recovery": "Inspect exact Work/turn/retained-dispatch reads. Resume the original parent only. "
                "Never replay children, implicitly renew, or start a replacement paid parent."}


# Opt-in manuscript contracts live in the existing Work specification. These
# helpers return observations/actions; only project_work writes or admits them.
def _logical_target(row):
    """A view only: legacy target values are never rewritten or re-hashed."""
    target = row.get("logical_target")
    return target if isinstance(target, dict) else {}


def _programme_opt_in(row):
    return ("manuscript_programme" in row
            or _logical_target(row).get("kind") == "writing-programme")


def _is_programme(row):
    return (row.get("task_kind") == "programme"
            and _logical_target(row).get("kind") == "writing-programme")


def _contract_problem(row):
    """Validate only new opt-ins, before descending into their stored shapes.

    Absence is legacy ordinary Work, even with a string/list/scalar target.
    A present malformed new contract is held locally, never silently ignored.
    """
    phases = ("results", "literature", "improvement", "draft", "judgement", "synthesis", "export")
    def text(value):
        return isinstance(value, str) and bool(value.strip())
    def revision(value):
        return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None
    def invalid(what):
        return "Invalid manuscript contract: " + what

    if _programme_opt_in(row):
        if not _is_programme(row):
            return invalid("programme requires its explicit writing-programme target and Work kind.")
        target = _logical_target(row)
        if "node_id" in target and not text(target["node_id"]):
            return invalid("programme claim scope must be a nonempty string.")
        contract = row.get("manuscript_programme")
        if not isinstance(contract, dict) or contract.get("schema_version") != "laplace.manuscript-programme/1":
            return invalid("programme object/schema is unavailable.")
        required, recipe = contract.get("required_stages"), contract.get("recipe")
        if (not isinstance(required, dict) or set(required) != set(phases)
                or any(not text(value) or value == row.get("id") for value in required.values())
                or len(set(required.values())) != len(phases)):
            return invalid("programme requires seven distinct exact stage Work identities.")
        if not isinstance(recipe, dict) or not revision(recipe.get("revision")):
            return invalid("programme recipe/revision is unavailable.")
        items = recipe.get("phases")
        if (not isinstance(items, list) or len(items) != len(phases)
                or any(not isinstance(item, dict) for item in items)
                or [item.get("id") for item in items] != list(phases)):
            return invalid("programme recipe must retain the seven ordered phase objects.")
        for index, item in enumerate(items):
            if any(not text(item.get(key)) for key in ("title", "work_kind", "guidance", "completion")):
                return invalid("phase role/guidance/completion is unavailable.")
            deps = item.get("depends_on")
            if (not isinstance(deps, list) or any(not isinstance(dep, str) or dep not in phases[:index] for dep in deps)):
                return invalid("phase prerequisites must name earlier phase identities.")
            reviews = item.get("review_obligations", [])
            if (not isinstance(reviews, list) or any(not isinstance(obligation, dict)
                    or not text(obligation.get("id")) for obligation in reviews)):
                return invalid("phase review obligations are malformed.")

    if "manuscript_stage" in row:
        stage = row["manuscript_stage"]
        if (not isinstance(stage, dict)
                or any(not text(stage.get(key)) for key in ("programme_id", "phase_id", "origin_parent_session_id"))
                or stage.get("phase_id") not in phases or not revision(stage.get("revision"))):
            return invalid("stage identity/revision is malformed.")
        cut = stage.get("cut")
        if (not isinstance(cut, dict) or cut.get("schema_version") != "laplace.manuscript-stage-cut/1"
                or cut.get("phase") != stage["phase_id"] or cut.get("programme_id") != stage["programme_id"]
                or not isinstance(cut.get("section_ids"), list)
                or any(not isinstance(ident, str) for ident in cut["section_ids"])
                or not isinstance(cut.get("support"), dict) or not isinstance(cut["support"].get("nodes"), list)
                or any(not isinstance(node, dict) for node in cut["support"]["nodes"])
                or any(not isinstance(cut.get(key), dict) for key in ("source_selection", "reader_inputs", "source_inputs"))
                or not isinstance(cut.get("reader_plan"), list) or not isinstance(cut.get("problems"), list)):
            return invalid("stage consumed cut is malformed.")
    return None


def _programme_origin(project, root, ident):
    from laplace.writing import records
    index = records.index(root)
    turns = [row for row in index.by_project.get(project, ())
             if row.get("record") == "writing-turn" and row.get("work_id") == ident
             and not row.get("dispatch_id")]
    return turns[0].get("session_id") if turns else None


def _programme_contract(row, root):
    from laplace.writing import stages
    recipe = stages.programme(root)
    closures = {item["id"]: item for item in row.get("review_obligations") or []}
    required = {}
    for phase in recipe["phases"]:
        item = closures.get("stage-" + phase["id"]) or {}
        ident = item.get("closure_work_id")
        if (not isinstance(ident, str) or not ident or ident == row["id"]
                or item.get("scope") != "closure" or item.get("required") is not True):
            raise ValueError("Manuscript programme requires explicit closure identity for " + phase["id"])
        required[phase["id"]] = ident
    if len(set(required.values())) != len(required):
        raise ValueError("Required manuscript stage Work identities must be distinct")
    return {"schema_version": "laplace.manuscript-programme/1",
            "required_stages": required, "recipe": recipe}


def _reader_readiness(project, root, section_ids, *, loaded=None):
    """Complete bounded typed coverage, not an exposition or science grade.

    Keep only owner substance. Action envelopes, reservation offers, observation
    telemetry and source/prose placement never enter this consumed reader basis.
    """
    from laplace.manuscript import project_structure, storyboard
    from laplace.pipeline import schema
    selected = list(section_ids)
    result = {"schema_version": "laplace.typed-reader-readiness/1",
              "scope": {"kind": "selected-sections" if selected else "whole-reader-plan",
                        "section_ids": selected},
              "sections": [], "inputs": {}, "problems": [], "status": "INCOMPLETE"}
    def problem(message):
        if message not in result["problems"]:
            result["problems"].append(message)
    def basis(value):
        if not isinstance(value, dict):
            return None
        return {key: value.get(key) for key in
                ("schema_version", "project", "path", "section_id", "subject_id",
                 "subject_revision", "inputs")}
    def standing(value):
        value = value or {}
        return {"status": value.get("status", "UNAVAILABLE"),
                "changed_inputs": sorted(value.get("changed_inputs") or []),
                "unobserved_inputs": sorted(value.get("unobserved_inputs") or [])}
    def diagnostics(value):
        return [{key: row[key] for key in ("kind", "field", "subject", "status", "reason") if key in row}
                for row in value or []]
    def subject(value):
        return {"basis": basis(value.get("reader_basis")),
                "currentness": standing(value.get("input_currentness")),
                "diagnostics": diagnostics(value.get("diagnostics"))}
    def qualified(value):
        b = value.get("basis")
        return (isinstance(b, dict) and isinstance(b.get("inputs"), dict)
                and value["currentness"]["status"] == "CURRENT" and not value["diagnostics"])
    try:
        loaded = loaded or storyboard._load_plan(project, root)
        if not loaded:
            problem("Typed reader plan is unavailable.")
            return result
        plan = json.loads(loaded[0].read_bytes())
        indexed = {row["id"]: row for row in schema.plan_sections(plan)}
        ids = selected or list(indexed)
        result["scope"]["section_ids"] = ids
        if not ids:
            problem("Typed reader whole-plan scope is empty; no owner N/A waiver exists.")
            return result
        if len(ids) > 64 or len(ids) != len(set(ids)) or set(ids) - indexed.keys():
            problem("Typed reader scope is unavailable, duplicated or exceeds 64 sections.")
            return result
        for sid in ids:
            row = {"section_id": sid, "paragraphs": [], "paragraph_total": None,
                   "paragraphs_observed": 0, "coverage": "INCOMPLETE"}
            result["sections"].append(row)
            offset, revision, order_basis = 0, None, None
            for page_number in range(27):  # 512 rows maximum per section, never a first-page waiver
                payload = {"view": "detail", "section_ids": [sid], "paragraph_offset": offset,
                           "paragraph_limit": 20}
                if page_number:
                    payload["paragraph_as_of"] = revision
                observed = project_structure.read(project, payload, root)
                sections = observed.get("sections") or []
                if len(sections) != 1 or sections[0].get("id") != sid:
                    raise ValueError("Typed reader owner returned a different section scope.")
                current = sections[0]
                transition = current.get("reader_transition") or {}
                paragraphs = current.get("paragraph_plan") or {}
                page = paragraphs.get("paragraphs") or {}
                contract = {"status": transition.get("status"), **subject(transition)}
                if not page_number:
                    row["contract"] = contract
                    row["paragraph_status"] = paragraphs.get("status")
                    row["identity_status"] = paragraphs.get("identity_status")
                    revision = paragraphs.get("revision")
                    order_basis = basis(((paragraphs.get("reorder_action") or {}).get("payload") or {})
                                        .get("expected_reader_basis"))
                    row["order_basis"] = order_basis
                elif row["contract"] != contract or paragraphs.get("revision") != revision:
                    raise ValueError("Typed reader subjects changed during complete coverage.")
                total = page.get("total")
                if (not isinstance(total, int) or isinstance(total, bool) or total < 0
                        or page.get("offset") != offset
                        or row["paragraph_total"] not in (None, total)):
                    raise ValueError("Typed reader paragraph coverage is not an exact current page.")
                row["paragraph_total"] = total
                items = page.get("items") or []
                for item in items:
                    row["paragraphs"].append({"paragraph_id": item.get("paragraph_id"),
                        "identity_status": item.get("identity_status"), **subject(item)})
                row["paragraphs_observed"] = len(row["paragraphs"])
                offset += len(items)
                if total > 512:
                    problem("Typed reader paragraph scope exceeds 512 rows in " + sid)
                    break
                if offset == total and page.get("next_read") is None:
                    row["coverage"] = "COMPLETE"
                    break
                if not items or offset >= total or page.get("next_read") is None:
                    raise ValueError("Typed reader paragraph coverage is incomplete.")
            ids_seen = [item["paragraph_id"] for item in row["paragraphs"]]
            contract_ok = row["contract"]["status"] == "DECLARED" and qualified(row["contract"])
            paragraphs_ok = (row["coverage"] == "COMPLETE" and row["paragraph_status"] == "DECLARED"
                and row["identity_status"] == "STABLE" and row["paragraph_total"] > 0
                and all(isinstance(ident, str) and ident for ident in ids_seen)
                and len(set(ids_seen)) == len(ids_seen)
                and all(item["identity_status"] == "STABLE" and qualified(item) for item in row["paragraphs"])
                and isinstance(order_basis, dict))
            if not contract_ok or not paragraphs_ok:
                problem("Typed reader declarations/currentness/diagnostics or complete paragraph coverage are incomplete: " + sid)
            cb = row["contract"].get("basis")
            if cb:
                result["inputs"][cb["path"] + "#" + sid] = _digest(row["contract"])
            if order_basis:
                # Observed input identities remain here even while STALE:
                # a second relevant change must not collapse to the same label.
                result["inputs"][order_basis["path"] + "#" + sid] = _digest({
                    "order": order_basis, "paragraphs": row["paragraphs"]})
        if not result["problems"]:
            result["status"] = "READY"
    except (ValueError, OSError, KeyError, TypeError) as error:
        result["status"] = "UNAVAILABLE"
        problem("Typed reader owner is unavailable: " + str(error))
    return result


def _stage_cut(project, root, parent, phase):
    """Phase-scoped live cut. A later cite/build cannot invalidate support-only Work."""
    from laplace.manuscript import storyboard, manuscript_source
    from laplace.manuscript.reader_plan import _paths
    from laplace.pipeline import schema
    from laplace.research import literature_support
    source = manuscript_source.resolve(project, repo_root=root)
    sections, reader_files = [], {}
    selected = parent.get("section_ids") or []
    loaded = storyboard._load_plan(project, root)
    if loaded:
        plan = json.loads(loaded[0].read_bytes())
        indexed = {row["id"]: row for row in schema.plan_sections(plan)}
        sections = [indexed[ident] for ident in (selected or list(indexed)) if ident in indexed]
    root_node = _logical_target(parent).get("node_id")
    scope_sections = list(sections)
    if root_node:
        scope_sections.append({"nodes_in_order": [root_node]})
    support = _literature_inputs(project, root, scope_sections)
    nodes = support["nodes"]
    # for_node's meaning/own-evidence remains distinct from external support.
    # Results precede acquisition, so later support edges are not their inputs.
    if phase["id"] == "results":
        net = literature_support.network(project, root)
        result_nodes = []
        for item in nodes:
            node = (net.get("nodes") or {}).get(item["node"]) or {}
            observed = literature_support.for_node(project, item["node"], root, net=net) if node else {}
            result_nodes.append({"node": item["node"], "meaning_revision": observed.get("meaning_revision"),
                                 "own_evidence": observed.get("own_evidence"),
                                 "status": "OBSERVED" if node and observed.get("meaning_revision") else "UNAVAILABLE"})
        support = {"nodes": result_nodes}
    reader_sensitive = phase["id"] in {"improvement", "draft", "judgement", "synthesis", "export"}
    readiness = (_reader_readiness(project, root, selected, loaded=loaded) if reader_sensitive
                 else {"status": "NOT_REQUIRED", "problems": [], "inputs": {}})
    reader_files = readiness["inputs"]
    source_files = {}
    if phase["id"] in {"draft", "judgement", "synthesis", "export"}:
        selected_source, tree = bindings.selected_tree(project, root)
        scope_files = {row.get("source_file") for row in sections}
        if not selected:
            scope_files = {row.get("file") for row in tree.get("sources", [])}
        scope_files.add(selected_source.get("root"))
        for row in tree.get("sources", []):
            if row.get("file") in scope_files or any(str(row.get("file", "")).endswith("/" + str(p)) for p in scope_files if p):
                source_files[row["file"]] = "sha256:" + row["raw_file_sha256"].removeprefix("sha256:")
        if tree.get("diagnostics"):
            source_files["unavailable_include_tree"] = tree["diagnostics"]
    if len(reader_files) + len(source_files) > 128:
        raise ValueError("Select a smaller manuscript stage cut (at most 128 source/reader inputs)")
    problems = list(readiness["problems"])
    if not support["nodes"] or any(item.get("status") == "UNAVAILABLE" for item in support["nodes"]):
        problems.append("Canonical claim scope is missing/unavailable; select exact sections or a canonical root claim.")
    if selected and len(sections) != len(selected):
        problems.append("Selected authored reader sections are unavailable.")
    if source.get("status") != "resolved":
        problems.append("Selected manuscript source is unavailable.")
    if phase["id"] != "results":
        for item in nodes:
            if item.get("qualification") == "OPEN" or item.get("status") == "UNAVAILABLE":
                problems.append("Unqualified canonical support for " + item["node"])
    return {"schema_version": "laplace.manuscript-stage-cut/1", "phase": phase["id"],
            "programme_id": parent["id"], "section_ids": selected, "root_claim": root_node,
            "source_selection": {key: source.get(key) for key in
                                 ("status", "root", "edition", "selection_identity")},
            "support": support,
            "reader_plan": [{"id": row["section_id"]} for row in readiness.get("sections", [])],
            "reader_readiness": readiness,
            "reader_inputs": reader_files, "source_inputs": source_files,
            "problems": list(dict.fromkeys(problems))}


def bind_work_contract(project, root, row, prior, tasks, payload):
    """Called only by the existing guarded task owner, before its append."""
    for candidate in (prior, tasks.get(row.get("parent_work_id")) or {}):
        problem = _contract_problem(candidate)
        if problem:
            raise ValueError(problem)
    if "manuscript_programme" in prior:
        if not _is_programme(row):
            raise ValueError("Withdraw an opted-in manuscript programme rather than silently removing its contract.")
        row["manuscript_programme"] = prior["manuscript_programme"]
        current = _programme_contract(row, root)
        if current["required_stages"] != row["manuscript_programme"]["required_stages"]:
            raise ValueError("Required manuscript stage identities cannot be silently replaced.")
    elif _is_programme(row):
        row["manuscript_programme"] = _programme_contract(row, root)
    parent = tasks.get(row.get("parent_work_id")) or {}
    contract = parent.get("manuscript_programme")
    old_stage = prior.get("manuscript_stage")
    if old_stage and (not contract or row["id"] not in contract["required_stages"].values()):
        raise ValueError("Withdraw a bound manuscript stage rather than silently detaching its input contract.")
    if not contract or row["id"] not in contract["required_stages"].values():
        return row
    phase_id = next(key for key, ident in contract["required_stages"].items() if ident == row["id"])
    phase = next(item for item in contract["recipe"]["phases"] if item["id"] == phase_id)
    expected = [contract["required_stages"][ident] for ident in phase["depends_on"]]
    if row.get("task_kind") != phase["work_kind"] or row.get("depends_on") != expected:
        raise ValueError("Manuscript stage must retain its exact role and prerequisite Work identities.")
    if row.get("section_ids") != parent.get("section_ids", []):
        raise ValueError("Manuscript stage must consume the programme's declared section scope.")
    from laplace.work.project_work_review import obligations
    required_review = obligations(phase.get("review_obligations") or [])
    if required_review and row.get("review_obligations") != required_review:
        raise ValueError("Independent manuscript judgement obligations must be retained.")
    if "logical_target" in payload:
        target = payload["logical_target"]
        cut = _stage_cut(project, root, parent, phase)
        if target != {"kind": "writing-stage-cut", "node_id": _digest(cut)}:
            raise ValueError("CHANGED_INPUT: inspect the owner-derived scoped stage cut before preparing Work.")
        origin = _programme_origin(project, root, parent["id"])
        if not origin:
            raise ValueError("Select the programme in its original author parent before stage preparation.")
        row["manuscript_stage"] = {"programme_id": parent["id"], "phase_id": phase_id,
                                   "origin_parent_session_id": origin, "cut": cut,
                                   "revision": _digest(cut)}
    elif old_stage:
        row["manuscript_stage"] = old_stage
    else:
        raise ValueError("An ordinary manuscript stage requires its owner-derived cut token.")
    return row


def stage_currentness(task, tasks, root, *, read_context=None, require_qualified=False):
    if "manuscript_stage" not in task:
        return None
    problem = _contract_problem(task)
    if problem:
        return {"status": "UNKNOWN", "kind": "MANUSCRIPT_CONTRACT_INVALID", "reason": problem}
    stage = task["manuscript_stage"]
    context = {} if read_context is None else read_context
    key = ("manuscript-stage-cut", task["id"])
    if key not in context:
        context[key] = {"status": "UNKNOWN", "reason": "Recursive stage support observation is unavailable."}
        parent = tasks.get(stage["programme_id"]) or {}
        problem = _contract_problem(parent)
        if problem:
            context[key] = {"status": "UNKNOWN", "kind": "MANUSCRIPT_CONTRACT_INVALID", "reason": problem}
            return context[key]
        contract = parent.get("manuscript_programme") or {}
        phase = next((item for item in (contract.get("recipe") or {}).get("phases", [])
                      if item["id"] == stage["phase_id"]), None)
        if not phase:
            return context[key]
        try:
            cut = _stage_cut(task["project"], root, parent, phase)
            observed = _digest(cut)
            context[key] = {"status": "CURRENT" if observed == stage["revision"] else "STALE",
                "kind": "MANUSCRIPT_STAGE_CUT", "consumed_revision": stage["revision"],
                "observed_revision": observed, "problems": cut["problems"],
                "reason": "Scoped stage inputs match." if observed == stage["revision"] else
                    "Consumed canonical claim/passage/source/reader inputs changed; explicitly reprepare this Work."}
        except (ValueError, OSError, KeyError) as error:
            context[key] = {"status": "UNKNOWN", "kind": "MANUSCRIPT_STAGE_CUT", "reason": str(error)}
    value = context[key]
    if require_qualified and value.get("problems"):
        return {**value, "status": "UNKNOWN", "reason": "; ".join(value["problems"])}
    return value


def _required_acquisitions(parent_id, tasks):
    required, pending, seen = [], [parent_id], set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        if len(seen) > 256:
            raise ValueError("Select a smaller manuscript programme terminal closure (at most 256 Works).")
        for row in tasks.values():
            if row.get("parent_work_id") != current:
                continue
            pending.append(row["id"])
            if row.get("task_kind") == "literature-acquisition" and row.get("recorded_status", row.get("status")) not in {"withdrawn", "cancelled"}:
                required.append(row["id"])
    return required


def programme_structure_problem(task, tasks):
    problem = _contract_problem(task)
    if problem:
        return problem
    contract = task.get("manuscript_programme")
    if not contract:
        return "Manuscript programme has no explicit required-stage identity contract." if _is_programme(task) else None
    required = contract["required_stages"]
    for phase in contract["recipe"]["phases"]:
        row = tasks.get(required[phase["id"]]) or {}
        problem = _contract_problem(row)
        if problem:
            return problem
        if (row.get("parent_work_id") != task["id"] or row.get("task_kind") != phase["work_kind"]
                or (row.get("manuscript_stage") or {}).get("phase_id") != phase["id"]):
            return "Required manuscript stage is missing or rebound: " + phase["id"]
        from laplace.work.project_work_review import obligations
        if phase.get("review_obligations") and row.get("review_obligations") != obligations(phase["review_obligations"]):
            return "Required independent judgement contract is missing."
    acquisitions = _required_acquisitions(task["id"], tasks)
    if not set([*required.values(), *acquisitions]).issubset(set(task.get("depends_on") or [])):
        return "Join all seven explicit stage identities and required literature-acquisition Work before programme completion."
    return None



def _programme_literature_problem(task, root):
    """Final claim/citation/build qualification cannot depend on acquisition child existence."""
    from laplace.manuscript import storyboard
    from laplace.pipeline import schema
    from laplace.research import literature_support
    selected = task.get("section_ids") or []
    roots = {}
    if selected:
        loaded = storyboard._load_plan(task["project"], root)
        if not loaded:
            return "Final literature scope has no current authored section plan."
        plan = json.loads(loaded[0].read_bytes())
        sections = {row["id"]: row for row in schema.plan_sections(plan)}
        for ident in selected:
            if ident not in sections:
                return "Final literature scope has an unavailable selected section: " + ident
            for node in sections[ident].get("nodes_in_order") or []:
                roots.setdefault(node, set()).add(ident)
    root_claim = _logical_target(task).get("node_id")
    if root_claim:
        roots.setdefault(root_claim, set())
    if not roots or len(roots) > 100:
        return "Final literature qualification requires an explicit bounded canonical claim scope."
    # One scoped owner snapshot shares graph/source/bibliography work across
    # roots. No global history or new acquisition ledger is consulted.
    context = {}
    for node, sections in sorted(roots.items()):
        observed = literature_support.scope(task["project"], root, node=node, limit=100, read_context=context)
        page = observed.get("pagination") or {}
        if (page.get("offset") != 0 or page.get("next_offset") is not None
                or len(observed.get("claims") or []) != page.get("total")
                or observed.get("gaps_omitted")):
            return "Final literature scope is incomplete; select a smaller explicit cut."
        if not observed.get("ready_for_completion"):
            kinds = sorted({gap.get("kind", "unknown") for gap in observed.get("gaps") or []})
            return "Final scoped literature/citation/build qualification is incomplete: " + ", ".join(kinds)
        for claim in observed["claims"]:
            needed = roots.get(claim["id"]) or set()
            if not needed:
                continue
            for link in claim.get("sources") or []:
                if link.get("relation") not in {"support", "validated_by", "counterevidence"}:
                    continue
                if not any(needed.intersection(use.get("section_ids") or [])
                           for use in link.get("manuscript_uses") or []):
                    return "Final literature citation is not attributable to the selected canonical section scope."
    return None


def programme_outcome_problem(task, tasks, root):
    """Terminal outcome proofs use the existing review/export owners, never a self-score."""
    problem = programme_structure_problem(task, tasks)
    if problem or not task.get("manuscript_programme"):
        return problem
    readiness = _reader_readiness(task["project"], root, task.get("section_ids") or [])
    if readiness["status"] != "READY":
        return "Final typed reader qualification is incomplete: " + "; ".join(readiness["problems"])
    from laplace.writing import records
    from laplace.manuscript import document_style, manuscript_source
    contract = task["manuscript_programme"]
    required = contract["required_stages"]
    origin = _programme_origin(task["project"], root, task["id"])
    if not origin:
        return "Original manuscript programme parent is unobserved."
    index = records.index(root)
    judgement = tasks[required["judgement"]]
    synthesis = [row for row in judgement.get("phases") or ()
                 if row.get("phase") == "synthesis" and (row.get("actor") or {}).get("session_id") == origin]
    phases = list(judgement.get("phases") or ())
    handoffs = [row for row in phases if row.get("phase") == "handoff"]
    if not handoffs:
        return "Independent judgement handoff is missing."
    current_handoff = handoffs[-1]
    consumed = {current_handoff["id"]}
    for obligation in judgement.get("review_obligations") or []:
        if not obligation.get("required"):
            continue
        reviews = [row for row in phases if row.get("phase") == "review"
                   and row.get("handoff_id") == current_handoff["id"]
                   and row.get("obligation_id") == obligation["id"]]
        if not reviews or reviews[-1].get("verdict") != "ACCEPT" or reviews[-1].get("independence") != "INDEPENDENT":
            return "Current independent manuscript judgement is not accepted."
        consumed.add(reviews[-1]["id"])
    synthesis = [row for row in synthesis if consumed.issubset(set(row.get("consumes") or []))]
    if not synthesis:
        return "Original-parent synthesis must consume the exact current handoff and accepted judgement."
    actor_turn = (synthesis[-1].get("actor") or {}).get("turn_id")
    turns = [row for row in index.by_id.get(actor_turn, ())
             if row.get("record") == "writing-turn" and row.get("project") == task["project"]
             and row.get("work_id") == required["synthesis"] and row.get("session_id") == origin]
    if not turns:
        return "Synthesis must be recorded by the original parent on its exact synthesis stage Work."
    exported = tasks[required["export"]]
    evidence = set(exported.get("evidence") or [])
    source = manuscript_source.resolve(task["project"], repo_root=root)
    try:
        _, current = document_style._selected_source_pdf(task["project"], root, source)
    except (ValueError, OSError) as error:
        return "Current selected-source export build is unavailable: " + str(error)
    # The canonical export read owns the saved PDF/receipt identity. Descend
    # through these exact evidence paths, not an eager unindexed journal scan
    # (Writing's journal index deliberately excludes manuscript-export rows).
    for file in sorted(evidence):
        if not file.endswith(".pdf"):
            continue
        receipt_path = file[:-4] + ".json"
        if receipt_path not in evidence:
            continue
        try:
            _, receipt = document_style.exported_pdf(task["project"], file, root, receipt=receipt_path)
        except (ValueError, OSError):
            continue
        if (receipt.get("mode") == "selected-source"
                and all(receipt.get(key) == current.get(key) for key in ("id", "pdf_sha256", "selected_source"))):
            return _programme_literature_problem(task, root)
    return "Actual current selected-source export receipt/PDF must be retained as export stage evidence."
