"""NATIVE WORK ADAPTERS (S1 B8): the in-app dispatch door of writing.operations._execute_work.

The original branch body, unchanged, split in two: `dispatch` admits the caller turn and serves
dispatch / dispatch_launch / dispatch_status / dispatch_returns; `_dispatch_plan` validates a plan
with launch_dispatch's own refusal half, stores it as a project artifact and records the dispatch
task. Recursive native calls go through writing.operations._execute, so they are admitted once each.
"""
from __future__ import annotations

import json
from pathlib import Path

from laplace.writing import records as writing_records


def workflow_definition(root: Path, project: str, mode: str, payload: dict, turn_id: str | None) -> dict:
    """Native definition decisions use the actual admitted caller, never JSON authority."""
    from laplace.pipeline import workflow_definitions as definitions
    if payload.get('action') == 'withdraw':
        return definitions.withdraw(root, definitions.native_caller(root, project, mode, turn_id),
                                    {key: value for key, value in payload.items() if key != 'project'})
    if payload.get('action') not in {'save', 'prepare'}:
        raise definitions.Refused('NATIVE_ACTION_UNAVAILABLE')
    action = definitions.save if payload['action'] == 'save' else definitions.prepare
    return action(root, definitions.native_caller(root, project, mode, turn_id),
                            {key: value for key, value in payload.items() if key not in {'project', 'action'}})


def dispatch(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None, *,
             observe_reads: bool = False) -> dict:
    # THE IN-APP DISPATCH DOOR (S3, 2026-10-06).  Five operation names at the ONE concept
    # `task@project`: a dispatch IS a project-work task row whose `task_kind` is
    # `dispatch` (project_work.py:299 mints it), its plan is a project artifact that row
    # names in `evidence`, and its children are ordinary writing sessions of this project.
    # No new row kind, no new store, no new validator and no second permission list.
    from laplace.work import project_work
    from laplace.writing import dispatch_execution
    records = writing_records.fold_records(root)
    turn = records["turns"].get(turn_id)
    if not turn or turn.get("project") != project:
        raise ValueError("A dispatch operation requires this project's current logical turn.")
    if operation == "dispatch_plan":
        return _dispatch_plan(root, project, mode, payload, turn, turn_id, observe_reads=observe_reads)
    ident = str(payload.get("id") or "")
    task_row = project_work._tasks(project, root).get(ident)
    if task_row is None or task_row.get("task_kind") != "dispatch":
        raise ValueError("Unknown dispatch; name the exact dispatch_id dispatch_plan returned.")
    if operation == "dispatch":
        return {"dispatch": task_row, "context": project_work.context(project, ident, root)}
    if operation == "dispatch_launch":
        return dispatch_execution.launch_dispatch(root, project, turn_id, {"id": ident,
            **({'await_completion':payload['await_completion']} if 'await_completion' in payload else {})})
    if operation == "dispatch_continue":
        result = dispatch_execution.continue_dispatch(root, project, turn_id,
            {key: value for key, value in payload.items() if key != 'project'})
        # This run receipt is admission/reconciliation, never completed child work.
        return {**result, 'pending': True}
    if operation == "dispatch_status" and payload.get('view') == 'continuation':
        request_id = payload.get('request_id')
        if not isinstance(request_id, str) or not request_id:
            raise ValueError('Continuation inspection requires the exact request_id.')
        return dispatch_execution.continuation_request(root, project, task_row, request_id)
    if operation == "dispatch_status" and 'request_id' in payload:
        raise ValueError('request_id is only for dispatch_status view continuation.')
    # The two consuming reads share one truth about what was planned: the plan ARTIFACT
    # the row names in `evidence`, read back off disk.  The return paths are not copied
    # onto a row, which is why four field names were added and not five.
    plan_rel = str((task_row.get("evidence") or [""])[0] or "")
    plan_file = (root / plan_rel).resolve()
    if not plan_rel or not plan_file.is_file():
        raise ValueError("The dispatch's plan artifact is no longer at the path its row names.")
    plan = json.loads(plan_file.read_text(encoding="utf-8"))
    packets = {str(item.get("packet")): item for item in plan.get("packets") or []}
    wanted = str(payload.get("packet") or "")
    if wanted and wanted not in packets:
        raise ValueError("The dispatch plan declares no packet named " + wanted + ".")
    if operation == "dispatch_status":
        from laplace.writing import dispatch_parent
        return dispatch_parent.native_status(task_row,project,root,turn_id=turn_id,
            selected=payload.get('view','status'))
    if operation == "dispatch_returns":
        return dispatch_returns.dispatch_returns_projection(root,project,ident,plan,payload,
            read=lambda values:operations._execute(root,project,mode,'read_artifact',values,
                turn_id=turn_id,observe_reads=observe_reads))


def join_dispatch_parent(root, project, dispatch_row, parent_id):
    """One explicit containing-Work prerequisite join for both preparation paths."""
    if not parent_id:
        return {}
    from laplace.work import project_work
    with project_work.dispatch_lock(root):
        parent = project_work._tasks(project, root).get(parent_id)
        if not parent or dispatch_row.get('parent_work_id') != parent_id:
            raise ValueError('Prepared dispatch containment no longer matches its original parent Work.')
        if dispatch_row['id'] in (parent.get('depends_on') or []):
            from laplace.work.project_work_views import handle
            return {'read_handle': handle(project, {'view': 'detail', 'id': parent_id}), 'reused': True}
        return project_work.task(project, {'id': parent_id,
            'expected_work_revision': project_work._task_revision(parent),
            'depends_on': list(parent.get('depends_on') or []) + [dispatch_row['id']]}, root)


def _dispatch_plan(root: Path, project: str, mode: str, payload: dict, turn: dict, turn_id: str | None, *,
                   observe_reads: bool = False) -> dict:
    from laplace.work import project_work
    from laplace.writing import dispatch_execution
    plan = payload.get("plan")
    if isinstance(plan, dict) and 'workflow_definition' in plan:
        raise ValueError('Workflow provenance is issued only by the saved workflow preparation owner.')
    # ONE validator for a plan: `launch_dispatch`'s own refuse-before-anything-starts
    # half, run with nothing started, so a plan that would be refused at launch is
    # refused at planning time BY THAT SAME CODE and never by a second copy of the
    # rules.  It is also where the carrier's own `workflow.validate_spec` is applied.
    checked = dispatch_execution.launch_dispatch(root, project, turn_id, {"plan": plan, "plan_path": str(payload.get("path") or "")},
                                                validate_only=True)
    stored = operations._execute(root, project, mode, "store_artifact",
                      {"path": str(payload.get("path") or ""), "scope": "project",
                       "before": None,
                       "content": json.dumps(plan, ensure_ascii=False, indent=1,
                                             sort_keys=True),
                       "reason": "dispatch plan " + str(payload.get("title") or "")},
                      turn_id=turn_id, observe_reads=observe_reads)
    with project_work.dispatch_lock(root):
        parent_work = project_work._tasks(project, root).get(turn.get("work_id")) or {}
        containing_parent = parent_work or None
        work_ledger = project_work._ledger(root)
        work_before = work_ledger.read_bytes() if containing_parent and work_ledger.is_file() else None
        row = project_work.task(project, {"title": payload.get("title"),
            "goal": payload.get("goal"), "kind": "dispatch", "section_ids": [],
            "depends_on": list(payload.get("depends_on") or []), "evidence": [stored["path"]],
            **({"parent_work_id":containing_parent["id"]} if containing_parent else {}),
            "origin": "eigen:session", "by": "eigen:session"}, root)
        preparation_join = {}
        if containing_parent:
            # Containment names the execution; its explicit prerequisite
            # propagates reviewed completion through the existing owner.
            # A failed join retains the unlaunched, inspectable child;
            # it cannot qualify prepared Work completion.
            parent = join_dispatch_parent(root, project, row, containing_parent['id'])
            from laplace.core.receipts import bundle, file_receipt
            preparation_join = {"parent_work_read":parent["read_handle"],
                "owned_changes":bundle(files=[
                    *(stored.get("owned_changes",{}).get("files") or []),
                    file_receipt(root,work_ledger,work_before,work_ledger.read_bytes())],
                    views=["project","pipeline","artifact"])}
            row = project_work.read(project,{"view":"detail","id":row["id"]},root)["task"]
    return {"dispatch_id": row["id"], "task": row, "plan_artifact": stored["path"],
            "plan_revision": stored["revision"], "packets": checked["packets"],
            "fan_out_max": checked["fan_out_max"],
            **preparation_join,
            "note": "launch it with dispatch_launch {\"id\": this dispatch_id}; read "
                    "terminal state with dispatch_status, never from a stream"}


from laplace.writing import operations  # noqa: E402  (the one operation table; cycle-safe: imported last)
from laplace.writing import dispatch_returns  # noqa: E402  (the returns owner; cycle-safe: imported last)
