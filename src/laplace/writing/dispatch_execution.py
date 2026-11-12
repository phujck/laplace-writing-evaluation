"""DISPATCH EXECUTION (S1 B2): admitting a dispatch plan and launching its already-admitted children.

Two distinct phases that must not merge:

  admission   launch_dispatch / _launch_dispatch: validate the exact stored plan (packets, return paths,
              capacity, stage reservations) for a parent turn and either answer validate_only or reserve
              and record the launch. No child is started while validating, and nothing waits under the
              launch/admission lock.
  launch      _start_dispatch_children: open each admitted child's session (turn_admission.new_session)
              and start its turn in a one-shot child host (turn_admission.start_turn).

While a child runs, writing.turn_execution asks this module two questions: _await_dispatch_dependencies
(wait for declared predecessor returns, bounded) and _child_control_reason (has the parent or author
stopped/cancelled this child?). _child_return_contract and return_read_receipt_errors describe and check
the typed return a child writes through store_artifact. Final parent receipts stay in
writing.dispatch_parent; returns are validated in writing.dispatch_returns.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import copy
import uuid
from laplace.pipeline import registry
from laplace.projects import artifacts
from laplace.writing.records._fold import _STORE, _canonical_read_payload
from laplace.writing.provider_catalogue import ProviderError   # the neutral owner; the provider service is imported only where a child is launched
from pathlib import Path


def _await_dispatch_dependencies(root: Path, project: str, session_id: str, turn_id: str,
                                 dispatch: dict, job: dict, emit):
    """Wait in the admitted child host, before capability probes or provider creation.

    The task/return owners decide readiness; this sidecar records execution only. A
    waiting host still owns active work, and ordinary Stop/deadline controls govern it.
    No provider is used to poll. Initial context remains the recorded admission cut;
    the generated contract names exact return handles the judge must read independently.
    """
    from laplace.work import project_work
    session=writing_records.fold_records(root)['sessions'].get(session_id) or {}
    if session.get('packet') is None:return
    contract=_child_return_contract(root,project,session_id,dispatch.get('dispatch_id'),turn_id=turn_id) or {}
    if not contract.get('judged_workers'):return
    cache={};previous=None;previous_cut=None
    while True:
        reason=('interrupted' if job.get('interrupt_requested') else
                _child_control_reason(root,{**dispatch,'project':project},session_id,cache=cache))
        if reason:
            child_hosts._update_child_execution(root,session_id,{'dependency_wait_ended':reason},expected_turn_id=turn_id)
            raise ProviderError(reason)
        task=cache.get('task') or {}
        try:
            stat=(root/_STORE).stat();journal_cut=(stat.st_ino,stat.st_size,stat.st_mtime_ns)
        except OSError:journal_cut=None
        executions=[child_hosts.child_execution(root,row['session_id']) for row in (previous or {}).get('dependencies',[])
                    if row.get('session_id')]
        cut=(journal_cut,cache.get('ledger_identity'),tuple((row.get('turn_id'),row.get('state'),row.get('result_status')) for row in executions))
        if previous and previous['state']=='WAITING' and previous_cut==cut:
            time.sleep(.25)
            continue
        readiness=project_work.dispatch_dependency_state(task,project,session.get('packet'),root)
        previous_cut=cut
        if readiness!=previous:
            state=readiness['state']
            child_hosts._update_child_execution(root,session_id,{'state':'WAITING' if state=='WAITING' else 'RUNNING' if state in {'READY','FAILURE-REVIEW'} else 'BLOCKED',
                'dependency_state':state,'dependencies':readiness['dependencies']},expected_turn_id=turn_id)
            emit({'type':'progress','text':'Waiting for settled worker returns' if state=='WAITING' else
                  'Reviewing settled incomplete worker evidence' if state=='FAILURE-REVIEW' else
                  'Worker dependency unavailable; review blocked' if state=='BLOCKED' else 'Worker returns ready for independent review'})
            previous=readiness
        if readiness['state']=='BLOCKED':raise ProviderError('DEPENDENCY-INCOMPLETE: worker return is missing, invalid, stale, or its provider did not complete.')
        if readiness['state']!='WAITING':return
        # Local owner polling only; controls checked at this same bounded interval.
        time.sleep(.25)


def _child_control_reason(root: Path, dispatch: dict, session_id: str, *,
                          cache: dict | None = None, execution_path: Path | None = None) -> str | None:
    from laplace.work import project_work
    cache = cache if cache is not None else {}
    path = execution_path or child_hosts._host_path(root, session_id)
    if path.with_suffix(".cancel.json").exists():
        cancel = child_hosts._read_host(path.with_suffix(".cancel.json"))
        if cancel.get("turn_id") == child_hosts._read_host(path).get("turn_id"):
            return "interrupted"
    def identity(file):
        try:
            stat = file.stat()
            return (stat.st_ino, stat.st_size, stat.st_mtime_ns)
        except OSError:return None
    ledger = project_work._ledger(root)
    ledger_identity = identity(ledger)
    if "task" not in cache or cache.get("ledger_identity") != ledger_identity:
        cache["task"] = project_work._tasks(str(dispatch.get("project") or ""), root).get(dispatch.get("dispatch_id")) or {}
        cache["ledger_identity"] = ledger_identity
    task = cache["task"]
    if task.get("status") == "cancelled":return "cancelled"
    if task.get("dispatch_launch_state") == "FAILED":
        current = continuation_for_session(task, session_id)
        observed = child_hosts._read_host(path)
        if not current or observed.get('turn_id') != current.get('planned_turn_id'):
            return "launch failed"
    if task.get('dispatch_launch_state')=='STARTING' and not child_hosts._process_matches(task.get('dispatch_launcher') or {}):
        return 'launcher exited before dispatch start completed'
    deadline = task.get("dispatch_deadline_at")
    if isinstance(deadline, (int, float)) and time.time() >= deadline:
        return "deadline exceeded"
    if task.get("dispatch_plan_sha256"):
        plan = root / str((task.get("evidence") or [""])[0])
        plan_identity = identity(plan)
        if "plan_token" not in cache or cache.get("plan_identity") != plan_identity:
            try:cache["plan_token"] = hashlib.sha256(plan.read_bytes()).hexdigest()
            except OSError:cache["plan_token"] = None
            cache["plan_identity"] = plan_identity
        if cache["plan_token"] != task["dispatch_plan_sha256"]:
            return "admitted plan changed"
    return None


def _child_return_contract(root: Path, project: str, session_id: str, dispatch_id: str | None, *, turn_id=None) -> dict | None:
    from laplace.work import project_work
    from laplace.pipeline import workflow
    task = project_work._tasks(project,root).get(dispatch_id) or {}
    rel = str((task.get("evidence") or [""])[0])
    if not rel:return None
    path = (root/rel).resolve()
    if not path.is_relative_to(root):raise ValueError("Dispatch plan is outside its owner.")
    plan = json.loads(path.read_text(encoding="utf-8"))
    session = writing_records.fold_records(root)["sessions"].get(session_id) or {}
    item = next((item for item in plan.get("packets") or [] if item.get("packet")==session.get("packet")),None)
    if item is None:return None
    current = continuation_for_session(task, session_id)
    if item['packet'] in (task.get('dispatch_review_current') or {}) and not current:return None
    if current and turn_id is not None and turn_id != current.get('planned_turn_id'):return None
    if current and turn_id is None and current['phase'] != 'LAUNCHING':return None
    family = "laplace.packet-judgement/" if item.get("role")=="judge" else "laplace.packet-return/"
    from laplace.writing import dispatch_returns
    typed=dispatch_returns.profile(root,family)
    workers=project_work.dispatch_dependencies(plan.get('packets') or [],item['packet'])
    parent_work = project_work._tasks(project,root).get(task.get('parent_work_id')) or {}
    prepared = parent_work.get('prepared_storyboard')
    prepared_input = ({'work_id':parent_work['id'],'section_ids':parent_work.get('section_ids') or [],
        'artifact_revision':prepared['revision'],
        'read':{'operation':'read_artifact','payload':{'id':prepared['artifact_id']}},
        'meaning':'Exact prepared parent inputs; inspect through this read and retain its real read receipt. It is not source application or scientific acceptance.'}
        if prepared else None)
    return {**typed,"own_packet":item["packet"],
            **({'continuation': {'request_id':current['request_id'],
                'prior_turn_id':current['guard']['prior_attempt']['turn_id'],
                'selected_turn_id':current['planned_turn_id'], 'reused_outputs':current['guard']['prerequisites'],
                'meaning':'Continue only this admitted review; exact saved instructions and completed worker outputs are retained.'}} if current else {}),
            **dispatch_returns.publication_projection(dispatch_returns.publication(root,project,item['return_path'])),
            'schema_read':{'operation':'session_settings','payload':{'view':'return-schema'}},
            'publication_policy':('The actual judge may use store_artifact at this one declared return path despite ordinary '
                                  'review write restrictions. Source and arbitrary artifact writes remain forbidden.'),
            **({'prepared_work':prepared_input} if prepared_input else {}),
            **({'packet':item['packet']} if item.get('role')!='judge' else {
                'packet_field':('The judgement.packet must name ONE of judged_workers, not own_packet. One judgement reviews '
                                'one worker; all workers need exact accepted coverage before parent completion.'),
                'judged_workers':[{'packet':label,'return_path':next(row['return_path'] for row in plan['packets'] if row['packet']==label),
                                   'read':{'operation':'read_artifact','payload':{
                                       'path':next(row['return_path'] for row in plan['packets'] if row['packet']==label),
                                       'scope':'project'}}}
                                  for label in workers],
                'dependency_policy':('Wait is enforced before inference. Read settled returns independently. Non-COMPLETE '
                                     'evidence with a retained readable output is failure-review only; absent output blocks '
                                     'review. It cannot support accepted:true.')}),
            "return_path":item["return_path"],
            **_declared_output_contract(root, project, item),
            "requires_git_checkpoint":item.get("requires_git_checkpoint",plan.get("requires_git_checkpoint",False)),
            "requires_command_check":item.get("requires_command_check",plan.get("requires_command_check",False)) or bool(plan.get("check_template")),
            "declared_check":item.get("check") or plan.get("check_template"),
            "independent_session": {"session_id":session_id,"read_only":True} if item.get("role")=="judge" else None}


def _declared_output_contract(root: Path, project: str, item: dict) -> dict:
    """The packet's own declared output coordinate and prewrite rule, generated from the admitted plan beside return_path.

    One projection for every consumer: turn_context serialises this contract into the child prompt and session_settings
    returns it, so no prompt prose or caller copies the coordinates.
    """
    prewrite = ('A typed return stored at return_path is validated before the Artifact write. A refusal names the failing '
                'field and these coordinates, writes nothing, and this same turn may correct the document and store it again.')
    if item.get('role') == 'judge':
        return {'prewrite_validation': prewrite}
    declared = item.get('output')
    path = declared.get('path') if isinstance(declared, dict) else declared
    vocabulary = {'return_roles': ['build', 'continue'],
                  'role_vocabulary': ('The plan role of this packet is worker. Its typed return role is build, or continue '
                                      'for an admitted continuation; both are valid and distinct from the plan role.'),
                  'prewrite_validation': prewrite}
    if not path:
        return {**vocabulary, 'declared_output': None,
                'output_policy': ('This packet declares no separate output path. A COMPLETE return names the report it '
                                  'actually produced; a legacy /1 return may name its own return file.')}
    try:
        observed = artifacts.read(root, project, {'path': path, 'scope': 'project', 'limit': 1})
    except (OSError, ValueError) as error:
        return {**vocabulary, 'declared_output': {'path': path, 'scope': 'project', 'available': False,
                                                  'reason': str(error)[:300]}}
    guard = {'expected_revision': observed['revision']} if observed.get('exists') else {'before': None}
    return {**vocabulary,
            'declared_output': {'path': path, 'scope': 'project', 'exists': bool(observed.get('exists')),
                'write': {'operation': 'store_artifact', 'payload': {'path': path, 'scope': 'project',
                          'reason': "Store this packet's declared report.", **guard}},
                'read': {'operation': 'read_artifact', 'payload': {'path': path, 'scope': 'project'}},
                'meaning': ('Store the packet report at exactly this project path first, then name it as the return '
                            'output. A report at any other path stays an ordinary artifact and does not satisfy this packet.')},
            'output_policy': 'The declared output must already exist when the COMPLETE return is stored.'}


def return_read_receipt_errors(root: Path, observation: dict, *, project: str, turn_id: str,
                             _records_lookup=None) -> list[str]:
    """Bind an immutable successful owner-read ID; latest-read replacement grants no authority."""
    from laplace.core.identity import revision_matches
    records = (_records_lookup(observation.get('receipt_id')) if _records_lookup is not None
               else writing_records.fold_records(Path(root).resolve()))
    row = records.get("read_receipts",{}).get(observation.get("receipt_id"))
    turn = records["turns"].get(turn_id) or {}
    if not row:return ["owner-read receipt is not present in the bound writing journal"]
    errors = []
    if row.get("project") != project or turn.get("project") != project or row.get("turn_id") != turn_id:
        errors.append("owner-read receipt does not belong to the actual turn/project")
    if observation.get("operation") != row.get("operation"):
        errors.append("owner-read operation differs from the actual read")
    payload = observation.get("payload")
    if not isinstance(payload,dict) or payload.get("project",project) != project:
        errors.append("owner-read request scope differs from the actual read")
    elif _canonical_read_payload(str(row.get("operation")),{**payload,"project":project}) != \
            _canonical_read_payload(str(row.get("operation")),row.get("payload") or {}):
        errors.append("owner-read payload differs from the actual read")
    if observation.get("ok") is not True or not revision_matches(observation.get("output_sha256"),row.get("output_sha256")):
        errors.append("owner-read digest/success differs from the actual successful read")
    return errors


def launch_dispatch(root: Path, project: str, parent_turn_id: str | None, payload: dict,
                    *, validate_only: bool = False) -> dict:
    from laplace.work import project_work
    from laplace.writing import dispatch_parent
    root=Path(root).resolve();started=time.time();observation=None
    with project_work.dispatch_lock(root):
        if payload.get('await_completion') is not None and not isinstance(payload['await_completion'],bool):
            raise ValueError('await_completion must be an explicit boolean.')
        if payload.get('await_completion') and not validate_only:
            task=project_work._tasks(project,root).get(payload.get('id'))
            if not task:raise ValueError('Connected observation requires the exact existing dispatch.')
            observation=dispatch_parent.prepare_observation(task,project,root,parent_turn_id,started)
        prepared = _launch_dispatch(root, project, parent_turn_id, payload, validate_only=validate_only,observation=observation)
        if observation and prepared.get('reused'):
            task=project_work._tasks(project,root)[observation['dispatch_id']]
            if not task.get('dispatch_parent_observation'):
                admission={key:value for key,value in observation.items() if not key.startswith('_')}
                admission['basis']=observation['_basis']
                project_work.transition(project,{'id':task['id'],'status':task['status']},root,
                    dispatch_receipt={'dispatch_parent_observation':admission})
        if observation:dispatch_parent.install_observation(root,observation)
    if prepared.get("_execution_admission"):
        try:
            prepared=_start_dispatch_children(root,project,parent_turn_id,str(payload.get('id') or ''),prepared)
        except Exception as error:
            if not observation:raise
            prepared={'started':False,'dispatch_id':observation['dispatch_id'],'launch_error':str(error)}
    if observation:
        phase=dispatch_parent.await_observation(root,project,observation)
        return {**prepared,'parent_continuation':dispatch_parent.public(root,project,phase)}
    return prepared


def _launch_dispatch(root: Path, project: str, parent_turn_id: str | None, payload: dict,
                     *, validate_only: bool = False, observation: dict | None = None) -> dict:
    """THE ONE new function of the in-app dispatch door: start a dispatch's child sessions.

    It is composed entirely of owners that already exist -- :new_session per child,
    :start_turn per child, ``project_work.transition`` for the row -- and it copies the
    research supervisor's order verb for verb (``research_surface.py:1537`` ``launch``):
    All packet settings and output paths are checked before durable admission. Admission
    precedes child effects and is serialized with task transitions. Retries observe the
    same admission and never replay children, including after a partial launch failure.
    The terminal state is never in this answer; it is read later from the durable row by
    ``dispatch_status``, exactly as ``run_status`` reads a research run's.

    ``validate_only`` runs the refusal half alone and starts nothing, which is how
    ``dispatch_plan`` validates a plan: a plan that would be refused at launch is refused at
    planning time by THIS code and not by a second copy of the rules.

    One thing is deliberately NOT here.  The fan-out bound is the plan's own
    ``fan_out_max`` -- the code refuses a launch above it and holds no bound of its own,
    because nothing may hand-set a dispatch's budget.  The children's model order has its
    one declaration at the inline comment in ``_packet_stage``, beside the refusal that remains of it.

    Phases: the dispatch row and its plan, the plan's own shape, the carrier stages (every packet
    checked), the per-packet session settings, then -- launches only -- the one durable admission.
    """
    from laplace.work import project_work
    root = Path(root).resolve()
    if registry.resolve(project, repo_root=root) is None:
        raise ValueError("Select a registered project.")
    ident = str(payload.get("id") or "")
    found = _dispatch_row(root, project, parent_turn_id, payload, ident, validate_only=validate_only, observation=observation)
    if "reused" in found:
        return found
    if not validate_only:
        from laplace.writing import source_execution
        source_execution.guard_spawn(root, project, parent_turn_id=parent_turn_id)
    plan, row, plan_file, parent_provider = found["plan"], found["row"], found["plan_file"], found["parent_provider"]
    if (plan.get('workflow_definition') or {}).get('research_workflow') and not validate_only:
        raise ValueError('This prepared policy executes only through workflow-start with exact approved effect recipients; generic dispatch cannot broaden its effects.')
    bound, packets, deadline = _plan_shape(root, plan)
    own_plan_path = (artifacts.resolve_path(root, project, str(payload["plan_path"]))
                     if validate_only and payload.get("plan_path") else plan_file if not validate_only else None)
    stages = _carrier_stages(root, project, ident, plan, packets, own_plan_path, validate_only=validate_only)
    choices = {}
    for item in packets:
        choices[str(item["packet"])] = project_work.validate_session_settings(
            {"provider": item.get("provider") or parent_provider,
             "model": item.get("model"), "effort": item.get("effort")}, root, role=str(item["role"]))
    if plan.get('workflow_definition'):
        # Pin exactly the consumed settings; later catalogue/tier changes cannot
        # silently retarget an already prepared definition's child configuration.
        pin = plan['workflow_definition']
        for sid, packet in pin['step_packets'].items():
            expected = pin['settings'][sid]['values']
            if any(choices[packet].get(key) != expected.get(key) for key in ('provider', 'model', 'effort')):
                raise ValueError('Prepared workflow effective settings changed; inspect the exact plan.')
    if validate_only:
        return {"validated": True, "fan_out_max": bound,
                "packets": [{"packet": str(item.get("packet")), "role": item.get("role"),
                             "return_path": item.get("return_path")} for item in packets],
                "carrier_spec_stages": [stage["id"] for stage in stages]}
    admission = _admit_dispatch(root, project, parent_turn_id, ident, plan, row, plan_file, deadline, observation)
    return {"_execution_admission": True, "plan": plan, "choices": choices,
            "admission": admission, "deadline": deadline}


def _dispatch_row(root: Path, project: str, parent_turn_id, payload: dict, ident: str, *,
                  validate_only: bool, observation: dict | None) -> dict:
    """The parent's provider and, for a launch, the exact open dispatch row and its plan artifact.

    An already admitted dispatch answers its retained children (``reused``) and replays nothing."""
    from laplace.work import project_work
    plan, row, plan_file, parent_provider = payload.get("plan"), None, None, "codex"
    parent_records = writing_records.fold_records(root)
    parent_record = parent_records["turns"].get(str(parent_turn_id or "")) or {}
    parent_provider = str((parent_records["sessions"].get(parent_record.get("session_id")) or {}).get("provider") or "codex")
    if not validate_only:
        records = writing_records.fold_records(root)
        parent = records["turns"].get(str(parent_turn_id or ""))
        if not parent or parent.get("project") != project:
            raise ValueError("A dispatch is launched from the dispatching turn of this project.")
        parent_provider = str((records["sessions"].get(parent.get("session_id")) or {}).get(
            "provider") or "codex")
        row = project_work._tasks(project, root).get(ident)
        if row is None or row.get("task_kind") != "dispatch":
            raise ValueError("dispatch_launch names an existing dispatch of this project.")
        if row.get("dispatch_admitted"):
            if row.get("dispatch_parent_turn_id") != parent_turn_id and observation is None:
                raise ValueError("Dispatch belongs to its admitted parent turn.")
            view = project_work.dispatch_view(row, project, root)
            return {"started": True, "reused": True, "dispatch_id": ident,
                    "children": view["children"], "execution_state": view.get("execution_state")}
        if row.get("status") != "open":
            raise ValueError("Only an open dispatch can be launched; this one is "
                             + str(row.get("status")) + ".")
        plan_rel = str((row.get("evidence") or [""])[0] or "")
        plan_file = (root / plan_rel).resolve()
        if not plan_rel or not plan_file.is_file():
            raise ValueError("The dispatch's plan artifact is no longer at the path its row names.")
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        if row.get('prepared_workflow') or plan.get('workflow_definition'):
            if not row.get('prepared_workflow'):
                raise ValueError('Workflow plan provenance requires its owner-issued preparation Work.')
            from laplace.writing import workflow_dispatch
            workflow_dispatch.admit_launch(root, project, row, parent_turn_id)
    return {"plan": plan, "row": row, "plan_file": plan_file, "parent_provider": parent_provider}


def _plan_shape(root: Path, plan) -> tuple[int, list, int | None]:
    """The plan's declared contract, its own fan-out bound, packets and deadline; both return families exist."""
    from laplace.work import project_work
    from laplace.pipeline import workflow
    if not isinstance(plan, dict) or plan.get("schema_version") != "laplace.dispatch-plan/1":
        raise ValueError("A dispatch plan declares schema_version laplace.dispatch-plan/1.")
    from jsonschema import Draft202012Validator
    shape_error = next(Draft202012Validator(project_work.dispatch_plan_contract()).iter_errors(plan),None)
    if shape_error:
        location = '.'.join(map(str,shape_error.absolute_path)) or 'plan'
        raise ValueError('Dispatch plan '+location+': '+shape_error.message+'; inspect current dispatch_plan help.')
    bound = plan.get("fan_out_max")
    if not isinstance(bound, int) or isinstance(bound, bool) or not 1 <= bound <= 8:
        raise ValueError("A dispatch plan declares its own fan_out_max (1..8); the code holds "
                         "no bound of its own, because nothing hand-sets a dispatch's budget.")
    packets = plan.get("packets")
    if not isinstance(packets, list) or not packets:
        raise ValueError("A dispatch plan declares at least one packet.")
    if len(packets) > bound:
        raise ValueError("%d packets exceed the plan's own declared fan_out_max %d."
                         % (len(packets), bound))
    deadline = plan.get("deadline_seconds")
    if deadline is not None and (not isinstance(deadline, int) or isinstance(deadline, bool) or deadline <= 0):
        raise ValueError("deadline_seconds must be a positive integer when declared.")
    if "requires_git_checkpoint" in plan and not isinstance(plan["requires_git_checkpoint"],bool):
        raise ValueError("requires_git_checkpoint is an explicit boolean.")
    if "requires_command_check" in plan and not isinstance(plan["requires_command_check"],bool):
        raise ValueError("requires_command_check is an explicit boolean.")
    # Both current return families must be discoverable before session/provider effects.
    workflow.packet_schemas(project_work._dispatch_schema_directory(root))
    return bound, packets, deadline


def _carrier_stages(root: Path, project: str, ident: str, plan: dict, packets: list, own_plan_path, *,
                    validate_only: bool) -> list[dict]:
    """Every packet checked against unused distinct return paths, then the carrier's own spec validation."""
    from laplace.work import project_work
    from laplace.pipeline import workflow
    stages: list[dict] = []
    returns = set()
    reserved_returns = set()
    for existing in project_work._tasks(project, root).values():
        if existing.get("task_kind") != "dispatch" or existing.get("id") == ident:
            continue
        old_path = (root / str((existing.get("evidence") or [""])[0])).resolve()
        try:old_plan = json.loads(old_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):continue
        for old_item in old_plan.get("packets") or []:
            reserved_returns.add(artifacts.resolve_path(root, project, str(old_item.get("return_path") or "")))
        if old_plan.get('synthesis_return_path'):
            reserved_returns.add(artifacts.resolve_path(root,project,old_plan['synthesis_return_path']))
    synthesis_path=None
    if plan.get('synthesis_return_path'):
        synthesis_path=artifacts.resolve_path(root,project,plan['synthesis_return_path'])
        if synthesis_path in reserved_returns or synthesis_path==own_plan_path or synthesis_path.exists():
            raise ValueError('Parent synthesis requires its unused distinct declared artifact path.')
        returns.add(synthesis_path)
    for item in packets:
        stages.append(_packet_stage(root, project, item, packets, stages, returns, reserved_returns, own_plan_path,
                                    validate_only=validate_only))
    stages.append({"id": "parent-consumes", "role": "synthesis",
                   "instruction": "The dispatching turn reads every return through "
                                  "dispatch_returns and says what they establish.",
                   "depends_on": [stage["id"] for stage in stages]})
    # THE CARRIER'S OWN VALIDATOR, not a copy of it: 2..16 finite stages, dependencies
    # precede their stage, every builder reviewed, an adversary with exact input, synthesis
    # last and consuming every stage (pipeline/workflow.py:119 validate_spec).  The same call
    # validates a repository-scoped plan the app emits for the external carrier, which is
    # what makes the two authorities comparable.
    try:
        workflow.validate_spec({"schema_version": workflow.SPEC_SCHEMA, "stages": stages})
    except workflow.WorkflowRefused as refused:
        # The carrier raises its own RuntimeError; the door's refusals are ValueErrors with
        # the owner's recovery fields, so the refusal is re-raised AS the carrier's own kind
        # name and nothing of it is softened.
        raise ValueError("the carrier's validator refuses this plan: " + str(refused)) from refused
    return stages


def _packet_stage(root: Path, project: str, item, packets: list, stages: list, returns: set, reserved_returns: set,
                  own_plan_path, *, validate_only: bool) -> dict:
    """One packet's refusals and its carrier stage; its return path joins ``returns``."""
    from laplace.work import project_work
    if not isinstance(item, dict):
        raise ValueError("Each packet of a dispatch plan is an object.")
    label = str(item.get("packet") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", label):
        raise ValueError("A packet's label is a short lowercase name: " + repr(label))
    if any(stage["id"] == label for stage in stages):
        raise ValueError("Two packets share the label " + label + ".")
    role = str(item.get("role") or "")
    if role not in ("worker", "judge"):
        raise ValueError("A packet's role is worker or judge, and its model comes from "
                         "that role through the one tier table.")
    # THE DISPATCH'S OWN CHOICE, OR THE ROLE TABLE'S -- never the project's preference.
    # The author's model law (`STANDING_LAW.md`): "the interfacing session runs at the
    # highest tier; a dispatched worker never inherits it.  A model the user names for a
    # task overrides this."  So a packet MAY name the model and effort of its own child
    # (banked as `model_source` 'named'), and a packet that names neither resolves at
    # `pipeline/schema.py` `role_model` for its role ('tier-default').  What a child never
    # does is inherit `project_work.saved_preferences`, which is the author's choice for
    # HIS OWN conversations in this project (`project_work.DISPATCHED_ROLES`).  The
    # accepted contract refused a packet-named model outright; the orchestrator's steer
    # S4 of 2026-10-06 sets this order instead, and the refusal below is what remains of
    # that row: a named model is a model, not a blank or a placeholder.
    for key in ("model", "effort"):
        if key in item and not str(item.get(key) or "").strip():
            raise ValueError("A packet either names its %s or omits the key, and then it "
                             "is resolved from its role through pipeline/schema.py "
                             "role_model." % key)
    if str(item.get("scope") or "project") != "project":
        raise ValueError("A repository-scoped packet is EMITTED as a plan for the external "
                         "carrier and is never launched in the app, which owns no worktree.")
    if "requires_git_checkpoint" in item and not isinstance(item["requires_git_checkpoint"],bool):
        raise ValueError("requires_git_checkpoint is an explicit boolean.")
    if "requires_command_check" in item and not isinstance(item["requires_command_check"],bool):
        raise ValueError("requires_command_check is an explicit boolean.")
    if len(str(item.get("brief") or "")) > 100_000:
        raise ValueError("A packet brief exceeds the writing turn text bound.")
    if not str(item.get("brief") or "").strip():
        raise ValueError("Each packet carries the brief its child turn is started with.")
    # The boundary that makes a project-scoped dispatch project-scoped: the SAME artifact
    # path guard every project artifact passes (writing_tools.py:70 _artifact).
    result = artifacts.resolve_path(root, project, str(item.get("return_path") or ""))
    if result in returns or result in reserved_returns or result == own_plan_path or (not validate_only and result.exists()):
        raise ValueError("Each packet requires an unused, distinct return path.")
    returns.add(result)
    return {"id": label, "role": "builder" if role == "worker" else "adversary",
            "instruction": str(item["brief"]),
            "depends_on": project_work.dispatch_dependencies(packets,label)}


def _admit_dispatch(root: Path, project: str, parent_turn_id, ident: str, plan: dict, row: dict, plan_file: Path,
                    deadline, observation: dict | None) -> dict:
    """The one durable admission (row -> in-progress, STARTING) that precedes every child effect."""
    from laplace.work import project_work
    if row.get('prepared_workflow'):
        from laplace.writing import workflow_dispatch
        workflow_dispatch.admit_launch(root, project, row, parent_turn_id)
    admitted_at = time.time()
    admission = {"dispatch_admitted": True, "dispatch_parent_turn_id": parent_turn_id,
                 "dispatch_launcher": child_hosts._process_identity(), "dispatch_launch_state": "STARTING",
                 "dispatch_deadline_at": admitted_at + deadline if deadline else None,
                 "dispatch_plan_sha256": hashlib.sha256(plan_file.read_bytes()).hexdigest()}
    # The exact reserved child return paths of THIS admitted plan (its hash is recorded above). The Artifact owner's
    # prewrite guard (dispatch_returns.validate_child_publication) reads them from this receipt, never from later plan bytes.
    admission['dispatch_return_reservations'] = {
        str(item['packet']): artifacts.resolve_path(root, project, item['return_path']).relative_to(root).as_posix()
        for item in plan.get('packets') or []}
    if row.get('dispatch_synthesis_reservation'):
        from laplace.writing.dispatch_parent import reservation
        if reservation(row,root,project)!=row['dispatch_synthesis_reservation']:
            raise ValueError('The declared synthesis reservation or original plan changed before admission; '
                             'inspect the retained dispatch instead of transferring its reserved path.')
    elif plan.get('synthesis_return_path'):
        from laplace.writing.dispatch_parent import reservation
        admission['dispatch_synthesis_reservation']=reservation(row,root,project)
    if observation:
        admission['dispatch_parent_observation']={key:value for key,value in observation.items() if not key.startswith('_')}
        admission['dispatch_parent_observation']['basis']=observation['_basis']
    project_work.transition(project, {"id": ident, "status": "in-progress"}, root,
                            dispatch_receipt=admission)
    return admission


SETTLED_JUDGE_STATES = frozenset({'FINISHED', 'FAILED', 'CANCELLED'})


def settled_judge_problem(execution, turn_id):
    """Why ONE prior judge execution is not safely settled for a continuation (None when it is): the ONE predicate both
    continuation_offer and the actual continuation admission (continuation_turn_id) apply to the same host record.

    Settled: the record still names that prior turn, owns no live provider or auxiliary process, and is FINISHED, FAILED
    or CANCELLED, or is the terminal pre-inference BLOCKED record the host lifecycle itself writes when the judge's
    dependency wait found its workers unavailable (_await_dispatch_dependencies records BLOCKED, the host raises before
    any provider exists and child_hosts._finish_child_execution archives state BLOCKED with finished_at). A BLOCKED
    record without finished_at (its host may still run), with inference started or with any recorded provider process
    is not that state. Active, unknown or orphaned hosts refuse.
    """
    execution = execution if isinstance(execution, dict) else {}
    if execution.get('turn_id') != turn_id:
        return 'the judge session no longer records prior turn %s' % turn_id
    if execution.get('active_provider_processes') or execution.get('active_auxiliary_processes'):
        return 'an owned provider or auxiliary process is still running'
    state = execution.get('state')
    if state in SETTLED_JUDGE_STATES:
        return None
    if state == 'BLOCKED':
        if execution.get('dependency_state') != 'BLOCKED' or not isinstance(execution.get('finished_at'), (int, float)):
            return 'the BLOCKED judge host has no terminal finished record'
        if execution.get('provider_inference_started') or execution.get('provider_process') or execution.get('provider_processes'):
            return 'the BLOCKED judge host recorded a provider, so it is not pre-inference'
        return None
    return 'the judge host is %s' % (state or 'UNKNOWN')


def continuation_for_session(task, session_id):
    receipts = task.get('dispatch_review_continuations') or {}
    selected = [receipts.get(request) for request in (task.get('dispatch_review_current') or {}).values()]
    matches = [row for row in selected if row and row.get('session_id') == session_id]
    return matches[0] if len(matches) == 1 else None


def _continuation_task(root, project, task):
    from laplace.work import project_work
    if isinstance(task, str):task = project_work._tasks(project, root).get(task)
    if not task or task.get('project') != project or task.get('task_kind') != 'dispatch':
        raise ValueError('Select an exact dispatch in this project.')
    return task


def _artifact_pin(root, project, relative):
    value = artifacts.read(root, project, {'path': relative, 'scope': 'project', 'limit': 1})
    rows = [row for row in writing_records.index(root).by_project.get(project, [])
            if row.get('record') == 'writing-artifact' and row.get('path') == value['path']]
    if rows:
        value.update(id=rows[-1]['id'], recorded_revision=rows[-1].get('sha256'))
    return {key: value.get(key) for key in ('id', 'path', 'artifact_path', 'revision', 'exists', 'recorded_revision')}


def _continuation_basis(root, project, task, packet):
    from laplace.work import project_work
    from laplace.writing import dispatch_parent, workflow_dispatch
    if task.get('status') not in {'open', 'in-progress'}:
        raise ValueError('Work standing requires a separate explicit disposition before continuing review.')
    if not task.get('dispatch_admitted') or not task.get('prepared_workflow'):
        raise ValueError('Only an admitted prepared app workflow is supported.')
    plan, pin, artifact = workflow_dispatch._checked(root, project, task)
    declared = {row['packet']: row for row in plan['packets']}
    item = declared.get(packet)
    if not item or item['role'] != 'judge' or any(packet in project_work.dispatch_dependencies(plan['packets'], row['packet']) for row in plan['packets']):
        raise ValueError('Only an existing judge leaf can be continued.')
    deadline = task.get('dispatch_deadline_at')
    if deadline is not None and time.time() >= deadline:
        raise ValueError('The original deadline expired; no renewal is admitted.')
    view = project_work.dispatch_view(task, project, root)
    child = next((row for row in view['children'] if row['packet'] == packet), None)
    if not child or not child.get('turn_id') or not child.get('session_id'):
        raise ValueError('An exact existing judge session and prior turn are required.')
    records = writing_records.fold_records(root)
    origin = records['turns'].get(task.get('dispatch_parent_turn_id')) or {}
    if origin.get('project') != project or origin.get('session_id') != pin['prepared_by']['session_id']:
        raise ValueError('The original prepared parent binding changed.')
    session = records['sessions'].get(child['session_id']) or {}
    if session.get('role') != 'review' or session.get('dispatch_id') != task['id'] or session.get('packet') != packet:
        raise ValueError('The prior judge session binding is unavailable.')
    problem = settled_judge_problem(child_hosts.child_execution(root, child['session_id']), child['turn_id'])
    if problem:
        raise ValueError('The existing judge host is active, unknown or not safely settled: ' + problem + '.')
    if not (records['turns'].get(child['turn_id']) or {}).get('reply'):
        raise ValueError('The prior judge has no settled terminal reply.')
    values = pin['settings'][next(sid for sid, label in pin['step_packets'].items() if label == packet)]['values']
    if any(session.get(key) != values.get(key) for key in ('provider', 'model', 'effort')):
        raise ValueError('Judge settings differ from the immutable prepared settings.')
    target = _artifact_pin(root, project, item['return_path'])
    if target['exists']:
        try:
            document = json.loads(artifacts.resolve_path(root, project, item['return_path']).read_text())
            errors = project_work._dispatch_return_errors(document, item, declared, root=root, project=project,
                session_id=child['session_id'], dispatch_id=task['id'], turn_id=child['turn_id'])
        except (OSError, ValueError, UnicodeError):errors = ['Unreadable prior return']
        if not errors:raise ValueError('A valid judgement, including rejection, cannot be rerun in this slice.')
    readiness = project_work.dispatch_dependency_state(task, project, packet, root)
    if readiness['state'] != 'READY' or not readiness['dependencies']:
        raise ValueError('Completed current worker prerequisites are required.')
    prerequisites = []
    for dependency in readiness['dependencies']:
        source = next(row for row in view['children'] if row['packet'] == dependency['packet'])
        if source['state'] != 'COMPLETE':raise ValueError('A prerequisite is not complete.')
        document = json.loads(artifacts.resolve_path(root, project, source['return_path']).read_text())
        output = document['output'];output = output['path'] if isinstance(output, dict) else output
        output_path = project_work._dispatch_pin_path(root, project, output, artifact_only=True)
        relative = output_path.relative_to(artifacts.project_root(root, project)).as_posix()
        prerequisites.append({'packet': source['packet'], 'session_id': source['session_id'], 'turn_id': source['turn_id'],
            'return': _artifact_pin(root, project, source['return_path']), 'output': _artifact_pin(root, project, relative)})
    tasks = project_work._tasks(project, root)
    basis = project_work._work_basis(tasks, task['id'])[0]
    guard = {'work_scope_revision': basis['scope_revision'], 'work_status_revision': project_work._standing_revision(task),
        'work_standing': {key: task.get(key) for key in ('status','blocked_reason','summary','completion_work_basis','completion_dependency_basis','evidence_receipts')},
        'dependency_revision': project_work._dependency_revision(task, tasks), 'plan': artifact,
        'reference': pin['reference'], 'settings_digest': pin['settings_digest'],
        'origin_parent_turn_id': task.get('dispatch_parent_turn_id'),
        'prior_attempt': {'session_id': child['session_id'], 'turn_id': child['turn_id']},
        'return': target, 'prerequisites': prerequisites}
    parent = records['turns'].get(task.get('dispatch_parent_turn_id')) or {}
    return {'guard': guard, 'budget': {'max_child_launches': 1, 'deadline_at': deadline,
        'deadline_seconds': plan.get('deadline_seconds')}, 'parent': {'session_id': parent.get('session_id'),
        'origin_turn_id': parent.get('id')}, 'current_attempt': guard['prior_attempt'],
        'history': child.get('attempt_history', []), 'reused_outputs': prerequisites}


def continuation_offer(root, project, task_or_id, packet):
    task = _continuation_task(root, project, task_or_id)
    try:
        basis = _continuation_basis(root, project, task, packet)
        return {'available': True, 'operation': 'dispatch_continue',
            'payload': {'id': task['id'], 'packet': packet, 'guard': basis['guard'], 'budget': basis['budget']}, **basis}
    except (ValueError, OSError, KeyError, StopIteration) as error:
        return {'available': False, 'reason': str(error), 'operation': 'dispatch_continue'}


def _receipt_turn(receipt, records, ident, project):
    turn = records['turns'].get(receipt['planned_turn_id'])
    if turn and (turn.get('request_id') != receipt['child_request_id'] or turn.get('session_id') != receipt['session_id']
                 or turn.get('dispatch_id') != ident or turn.get('project') != project
                 or turn.get('parent_turn_id') != receipt['parent_turn_id']):
        raise ValueError('Continuation turn identity conflicts with its durable reservation.')
    return turn


def continuation_request(root, project, task_or_id, request_id):
    task = _continuation_task(root, project, task_or_id)
    receipt = (task.get('dispatch_review_continuations') or {}).get(request_id)
    if not receipt:return {'dispatch_id': task['id'], 'request_id': request_id, 'effect': 'NONE', 'receipt': None}
    turn = _receipt_turn(receipt, writing_records.fold_records(root), task['id'], project)
    current = {'session_id': receipt['session_id'], 'turn_id': turn['id'] if turn else None,
        'request_id': request_id, 'phase': 'ADMITTED' if turn else receipt['phase']}
    return {'dispatch_id': task['id'], 'packet': receipt['packet'], 'request_id': request_id,
        'effect': 'RECORDED' if turn else 'NONE' if receipt['phase'] == 'RESERVED' else 'UNKNOWN',
        'receipt': copy.deepcopy(receipt), 'current_attempt': current,
        'history': [{'session_id': receipt['session_id'], 'turn_id': receipt['guard']['prior_attempt']['turn_id']}],
        'budget': receipt['budget'], 'read': {'operation': 'dispatch_status',
            'payload': {'id': task['id'], 'view': 'continuation', 'request_id': request_id}}}


def guard_continuation_inputs(root, project, task, receipt, *, admitted_session=None):
    """Recheck retained immutable inputs without treating admitted standing as a new intent."""
    from laplace.writing import workflow_dispatch
    if task.get('status') not in {'open', 'in-progress'}:raise ValueError('Continuation Work is held or terminal.')
    _, pin, artifact = workflow_dispatch._checked(root, project, task)
    step = next(sid for sid, packet in pin['step_packets'].items() if packet == receipt['packet'])
    expected = pin['settings'][step]['values']
    actual = writing_records.fold_records(root)['sessions'].get(receipt['session_id']) or {}
    for selected in (actual, admitted_session) if admitted_session is not None else (actual,):
        if any(selected.get(key) != expected.get(key) for key in ('provider', 'model', 'effort')):
            raise ValueError('Actual judge settings changed from the immutable continuation plan.')
    guard = receipt['guard']
    if task.get('dispatch_parent_turn_id') != guard['origin_parent_turn_id']:
        raise ValueError('The original parent binding changed.')
    if artifact != guard['plan'] or pin['reference'] != guard['reference'] or pin['settings_digest'] != guard['settings_digest']:
        raise ValueError('The continuation plan changed.')
    deadline = receipt['budget']['deadline_at']
    if task.get('dispatch_deadline_at') != deadline:raise ValueError('The original deadline changed.')
    if deadline is not None and time.time() >= deadline:raise ValueError('The original deadline expired.')
    from laplace.work import project_work
    tasks = project_work._tasks(project, root)
    if (project_work._work_basis(tasks, task['id'])[0]['scope_revision'] != guard['work_scope_revision']
            or project_work._dependency_revision(task, tasks) != guard['dependency_revision']):
        raise ValueError('Continuation Work scope/dependencies changed.')
    if {key:task.get(key) for key in guard['work_standing']} != guard['work_standing']:
        raise ValueError('Continuation Work standing changed.')
    selected={row['packet']:row for row in project_work.dispatch_view(task,project,root,_include_parent=False)['children']}
    for prerequisite in guard['prerequisites']:
        child=selected.get(prerequisite['packet']) or {}
        if (child.get('session_id')!=prerequisite['session_id'] or child.get('turn_id')!=prerequisite['turn_id']
                or child.get('state')!='COMPLETE' or child.get('execution',{}).get('state') in {'STARTING','RUNNING','WAITING','ORPHANED','UNKNOWN-OWNERSHIP'}):
            raise ValueError('A retained prerequisite attempt is no longer settled/current.')
        for field in ('return', 'output'):
            old = prerequisite[field]
            if _artifact_pin(root, project, old['artifact_path']) != old:raise ValueError('A retained prerequisite changed.')


def continuation_turn_id(root, project, session_id, request_id, dispatch, *, admitted_session=None):
    from laplace.work import project_work
    task = _continuation_task(root, project, (dispatch or {}).get('dispatch_id'))
    receipt = continuation_for_session(task, session_id)
    if not receipt:
        session=writing_records.fold_records(root)['sessions'].get(session_id) or {}
        if session.get('packet') in (task.get('dispatch_review_current') or {}):raise ValueError('Current continuation binding is unavailable.')
        return None
    if (receipt['phase'] != 'LAUNCHING' or receipt['child_request_id'] != request_id
            or receipt['parent_turn_id'] != dispatch.get('parent_turn_id')):
        raise ValueError('This turn is not the reserved continuation admission.')
    problem = settled_judge_problem(child_hosts.child_execution(root, session_id), receipt['guard']['prior_attempt']['turn_id'])
    if problem:
        raise ValueError('The guarded prior judge is no longer safely settled: ' + problem + '.')
    guard_continuation_inputs(root, project, task, receipt, admitted_session=admitted_session)
    return receipt['planned_turn_id']


def continue_dispatch(root, project, parent_turn_id, payload):
    from laplace.work import project_work
    from laplace.writing import dispatch_parent, workflow_dispatch
    if set(payload) != {'id', 'packet', 'request_id', 'guard', 'budget'}:
        raise ValueError('dispatch_continue requires exactly id, packet, request_id, guard and budget.')
    if not isinstance(payload['request_id'], str) or not 1 <= len(payload['request_id']) <= 160:
        raise ValueError('A bounded stable request_id is required.')
    root = Path(root).resolve();ident = payload['id'];request_id = payload['request_id']
    intent = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with project_work.dispatch_lock(root):
        task = _continuation_task(root, project, ident)
        actor = writing_records.fold_records(root)
        if not dispatch_parent.parent_actor(task, actor, parent_turn_id):raise ValueError('The original author parent session is required.')
        current = workflow_dispatch._definitions().native_caller(root, project, 'work', parent_turn_id)
        workflow_dispatch._admit(root, current)
        receipts = copy.deepcopy(task.get('dispatch_review_continuations') or {})
        if request_id in receipts:
            if receipts[request_id]['intent_sha256'] != intent:raise ValueError('Continuation request intent changed.')
            return {**continuation_request(root, project, task, request_id), 'replayed': True}
        from laplace.writing import source_execution
        source_execution.guard_spawn(root, project, parent_turn_id=parent_turn_id)
        basis = _continuation_basis(root, project, task, payload['packet'])
        if payload['guard'] != basis['guard'] or payload['budget'] != basis['budget']:
            raise ValueError('Continuation guard/budget changed; inspect the exact offer.')
        session = actor['sessions'][basis['current_attempt']['session_id']]
        choice = project_work.validate_session_settings({key: session.get(key) for key in ('provider', 'model', 'effort')}, root, role='judge')
        if any(choice.get(key) != session.get(key) for key in ('provider', 'model', 'effort')):
            raise ValueError('The pinned judge settings are no longer supported unchanged.')
        retained_plan = workflow_dispatch._checked(root, project, task)[0]
        brief = next(item['brief'] for item in retained_plan['packets'] if item['packet'] == payload['packet'])
        receipt = {'request_id': request_id, 'intent_sha256': intent, 'packet': payload['packet'],
            'session_id': basis['current_attempt']['session_id'], 'parent_turn_id': parent_turn_id,
            'planned_turn_id': 'WT-' + uuid.uuid4().hex, 'child_request_id': 'continue-' + hashlib.sha256((project+'\0'+ident+'\0'+request_id).encode()).hexdigest(),
            'guard': payload['guard'], 'budget': payload['budget'], 'phase': 'RESERVED'}
        if any(row.get('request_id') == receipt['child_request_id'] for row in actor['turns'].values()):
            raise ValueError('Child request identity already belongs to another turn.')
        receipts[request_id] = receipt
        selected = {**(task.get('dispatch_review_current') or {}), payload['packet']: request_id}
        project_work.transition(project, {'id': ident, 'status': task['status']}, root,
            dispatch_receipt={'dispatch_review_continuations': receipts, 'dispatch_review_current': selected})
        receipt['phase'] = 'LAUNCHING'
        project_work.transition(project, {'id': ident, 'status': task['status']}, root,
            dispatch_receipt={'dispatch_review_continuations': receipts})
    try:
        started = turn_admission.start_turn(root, {'project': project, 'session_id': receipt['session_id'],
            'mode': 'review', 'request_id': receipt['child_request_id'],
            'text': brief},
            dispatch={'dispatch_id': ident, 'parent_turn_id': parent_turn_id})
        with project_work.dispatch_lock(root):
            task = _continuation_task(root, project, ident)
            turn = _receipt_turn(receipt, writing_records.fold_records(root), ident, project)
            if not turn or started.get('turn_id') != turn['id']:raise ValueError('No exact continuation admission was acknowledged.')
            receipts = copy.deepcopy(task['dispatch_review_continuations']);receipts[request_id].update(phase='ADMITTED', host_pid=started.get('host_pid'))
            project_work.transition(project, {'id': ident, 'status': task['status']}, root,
                dispatch_receipt={'dispatch_review_continuations': receipts})
    except Exception as error:
        with project_work.dispatch_lock(root):
            task = _continuation_task(root, project, ident);receipts = copy.deepcopy(task['dispatch_review_continuations'])
            receipts[request_id].update(phase='UNKNOWN', launch_error=str(error))
            project_work.transition(project, {'id': ident, 'status': task['status']}, root,
                dispatch_receipt={'dispatch_review_continuations': receipts})
    return {**continuation_request(root, project, ident, request_id), 'replayed': False}


def _start_dispatch_children(root: Path, project: str, parent_turn_id: str | None,
                             ident: str, prepared: dict) -> dict:
    from laplace.work import project_work
    plan, choices, admission, deadline = (prepared[key] for key in
                                         ("plan", "choices", "admission", "deadline"))
    packets = plan["packets"]
    tasks = project_work._tasks(project,root)
    parent_work = tasks.get((tasks.get(ident) or {}).get('parent_work_id')) or {}
    prepared_scope = ({'selection':{'section_ids':parent_work.get('section_ids') or []}}
                      if parent_work.get('prepared_storyboard') else {})
    children = []
    try:
        for item in packets:
            role, label = str(item["role"]), str(item["packet"])
            choice = choices[label]
            session = turn_admission.new_session(root, project, choice["provider"], str(item.get("model") or ""), str(item.get("effort") or ""),
                                  role="review" if role == "judge" else "author",
                                  model_role=role, dispatch_id=ident, packet=label)
            path = child_hosts._host_path(root, session["id"])
            child_hosts._update_child_execution(root, session["id"], {"state": "STARTING", "session_id": session["id"],
                              "project": project, "dispatch_id": ident, "packet": label,
                              "parent_turn_id": parent_turn_id, "provider": choice["provider"],
                              "launcher": admission["dispatch_launcher"]})
            started = turn_admission.start_turn(root, {"project": project, "session_id": session["id"],
                                       "mode": "review" if role == "judge" else "work",
                                       "text": str(item["brief"]),**prepared_scope},
                                 dispatch={"dispatch_id": ident, "parent_turn_id": str(parent_turn_id or "")})
            children.append({"packet": label, "session_id": started["session_id"],
                             "turn_id": started["turn_id"], "role": role,
                             "host_pid": started.get("host_pid"), "provider": session["provider"],
                             "tier": session.get("tier"), "model_source": session.get("model_source"),
                             "return_path": str(item["return_path"])})
    except Exception as exc:
        with project_work.dispatch_lock(root):
            if 'path' in locals():
                observed = child_hosts._read_host(path)
                if observed.get("state") == "STARTING":
                    child_hosts._update_child_execution(root, session["id"], {"state": "FAILED", "reason": str(exc)})
            current = project_work._tasks(project, root).get(ident) or {}
            project_work.transition(project, {"id": ident, "status": "cancelled" if current.get("status") == "cancelled" else "blocked"}, root,
                                    dispatch_receipt={"dispatch_launch_state": "FAILED", "dispatch_launch_error": str(exc)})
        # The banked launch failure is consumed by already-started hosts; nothing is replayed.
        raise
    with project_work.dispatch_lock(root):
        current = project_work._tasks(project, root).get(ident) or {}
        moved = project_work.transition(project, {"id": ident, "status": "cancelled" if current.get("status") == "cancelled" else "in-progress"}, root,
                                        dispatch_receipt={"dispatch_launch_state": "STARTED"})
    return {"started": True, "dispatch_id": ident, "children": children,
            "transition": {"status": moved.get("status"), "ts": moved.get("ts")},
            "deadline_seconds": deadline,
            "note": "read dispatch_status for terminal state and exact result paths"}


from laplace.writing import child_hosts  # noqa: E402  (cycle-safe: imported last)
from laplace.writing import records as writing_records, turn_admission  # noqa: E402  (owners; cycle-safe, imported last)
