"""THE OPERATION TABLE (core consolidation, family 2): one admission, then exactly one family dispatcher.

``_execute`` is the owner call of every project operation on every caller path (the native gateway, pure replay, the
recursive dispatch of a child, the tool bodies): ``_admit_operation`` holds every refusal that precedes an owner call;
``_FAMILY_OPERATIONS`` is the one table naming which ``_execute_<family>`` dispatches each operation (exactly-one
coverage of reads.READS | reads.WRITES is checked at import). ``replay_read`` is THE PURE REPLAY of a consumed read: the
same owner call under the retained projection, banking nothing. The dispatch citations (writing_declarations.dispatch_site,
tools/writing_verbs/gen_routes.py, writing.artifacts.declaration_sites) read this region's own text, so the families
stay contiguous after ``_execute``. The gateway's help document is the one injected renderer (``set_help_renderer``);
nothing here imports the gateway, the facade, a provider or the HTTP door.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from laplace.writing import records as writing_records
from laplace.projects.artifacts import resolve_path as _artifact
from laplace.writing.reads import READS, WRITES, output_digest, effect


def _unset_help(root, project, mode, payload, *, turn_id=None):
    raise RuntimeError("the help renderer is not registered: the native gateway (writing_tools) registers its own")


_help_renderer = _unset_help
_interface_projection = None


def set_help_renderer(renderer, *, interface=None) -> None:
    """The gateway's contract renderings, injected once: its help document and the repository interface view over its
    declarations (both are the door's own contract rendered, not owners)."""
    global _help_renderer, _interface_projection
    _help_renderer = renderer
    _interface_projection = interface


class OwnerError(ValueError):
    """Canonical owner refusal with bounded machine-readable recovery fields."""
    def __init__(self, details:dict):
        self.details=details
        super().__init__(str(details.get("error") or details))


def _admit_operation(root: Path, project: str, mode: str, operation: str, payload, turn_id: str | None) -> dict:
    """Every refusal that precedes an owner call, in its original order; returns the project-scoped payload."""
    if operation not in READS | WRITES:
        raise ValueError("Unknown project operation.")
    if mode not in {'work', 'discuss', 'revise', 'review'}:
        raise ValueError('Unknown writing role')
    if operation in WRITES and mode == "review" and effect(operation, payload) == "write" and operation not in {"note", "note_status", "task", "work_review"}:
        _admit_review_write(root, project, operation, payload, turn_id)
    if not isinstance(payload, dict):
        raise ValueError("Operation payload must be an object.")
    if 'project' in payload and payload['project'] != project:
        raise ValueError('This tool is scoped to project '+project+'; remove the conflicting project field or use the intended project session.')
    if turn_id:
        from laplace.writing.workflow_progression import admit_operation
        admit_operation(root, project, turn_id, operation, payload)
    if turn_id and operation in ("store_artifact", "dispatch_plan"):
        _fence_dispatched_child_write(root, project, payload, turn_id)
    if operation == 'source':
        _check_source_shape(payload)
    if operation in {'storage','storage_prune','literature_scope','literature_lookup','literature_discover','literature_import','literature_bind','literature_uses','reference_source','reference_text','reference_fetch','proposal_supersede'}:
        from laplace.writing.schemas import SCHEMAS   # the operation's input contract (the native door composes no guard onto these)
        contract=SCHEMAS[operation]
        if operation in {'literature_import','reference_source'}:
            from laplace.core import admission
            admission.admit_owner_payload(operation,payload,contract,project=project)
        else:
            unknown=set(payload)-set(contract.get('properties',{}))-{'project'}
            if unknown:raise ValueError(operation+' has unknown fields: '+', '.join(sorted(unknown))+'; inspect help {"operation":"'+operation+'"} for exact names.')
            missing=[key for key in contract.get('required',[]) if key not in payload]
            if missing:raise ValueError(operation+' requires '+', '.join(missing))
    payload = {**payload, "project": project}
    return payload


def _admit_review_write(root: Path, project: str, operation: str, payload, turn_id: str | None) -> None:
    """Review mode writes notes, note status and tasks; one judge child may store its own declared return."""
    permitted = False
    if operation == "store_artifact" and turn_id and isinstance(payload, dict) \
            and payload.get("scope", "project") == "project":
        # ONE exception, and it widens review mode's authority over the REVIEWED artifacts
        # by not a single byte: a JUDGE CHILD of a dispatch may write exactly the one path
        # its own packet declared as its return, and nothing else.  Without it a judge
        # child cannot return at all -- every write but note/note_status/task is refused
        # here -- so a judgement validated by check-return and read back through
        # read_artifact, which is how the dispatch design says a judgement travels, is
        # unreachable.  The path is a new fact nowhere: the dispatch's own plan artifact
        # declares it and the child's session row names its packet.
        from laplace.work import project_work
        from laplace.writing.dispatch_returns import child_permission
        records = writing_records.fold_records(root)
        turn = records["turns"].get(turn_id) or {}
        session = records["sessions"].get(turn.get("session_id")) or {}
        dispatch = project_work._tasks(project, root).get(str(turn.get("dispatch_id") or ""))
        if turn.get('project')==project and dispatch:
            publication=child_permission(root,project,session['id'],dispatch['id'],turn_id=turn_id)
            permitted=bool(publication and publication['payload']['path']==payload.get('path'))
    if not permitted:
        raise ValueError("Independent review can save findings and tasks; reviewed artifacts stay unchanged.")


def _fence_dispatched_child_write(root: Path, project: str, payload: dict, turn_id: str) -> None:
    """A dispatched child cannot overwrite its plan, the synthesis return or another packet's return."""
    from laplace.work import project_work
    records = writing_records.fold_records(root)
    turn = records["turns"].get(turn_id) or {}
    if turn.get("dispatch_id"):
        task = project_work._tasks(project, root).get(turn["dispatch_id"]) or {}
        plan_path = (root / str((task.get("evidence") or [""])[0])).resolve()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        session = records["sessions"].get(turn.get("session_id")) or {}
        target = _artifact(root, project, str(payload.get("path") or ""), payload.get("scope", "project"))
        protected = {plan_path}
        if plan.get('synthesis_return_path'):
            protected.add(_artifact(root,project,plan['synthesis_return_path']))
        protected.update(_artifact(root, project, str(item.get("return_path") or ""))
                         for item in plan.get("packets") or []
                         if item.get("packet") != session.get("packet"))
        if target in protected:
            raise ValueError("A dispatched child cannot overwrite its plan or another packet's return.")


def _check_source_shape(payload: dict) -> None:
    """The source read's closed field set and value shapes."""
    allowed = {'project','files','section_ids','sections','ids','selection','line_start','line_end','quote','node_id','node_ids','include_numbered_text'}
    unknown = set(payload) - allowed
    if unknown:
        raise ValueError('source has unsupported fields: '+', '.join(sorted(unknown))+'. Read current bytes with source {"files":["actual/file.tex"]}; every source call reads current bytes, so omit fresh. Inspect help {"operation":"source"} for physical-source versus concept-context scopes.')
    if 'include_numbered_text' in payload and not isinstance(payload['include_numbered_text'],bool):
        raise ValueError('source.include_numbered_text must be a boolean')
    for key in ('files','section_ids','sections','ids','selection','node_ids'):
        value = payload.get(key)
        if key in payload and not (isinstance(value,str) or isinstance(value,list) and all(isinstance(item,str) for item in value)):
            raise ValueError('source.'+key+' must be a string or an array of strings.')
    for key in ('node_id','quote'):
        if key in payload and not isinstance(payload[key],str):raise ValueError('source.'+key+' must be a string.')
    for key in ('line_start','line_end'):
        if key in payload and (not isinstance(payload[key],int) or isinstance(payload[key],bool) or payload[key]<1):
            raise ValueError('source.'+key+' must be a positive line number.')
    if payload.get('line_start') and payload.get('line_end') and payload['line_start']>payload['line_end']:
        raise ValueError('source line_start must not exceed line_end.')


def _owner_answer(reply: tuple) -> dict:
    """An owner's (status, value) answer as the native door's: a refusal (>= 400) is the owner's own OwnerError."""
    status, value = reply
    if status >= 400:
        raise OwnerError(value)
    return value


def _execute(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None = None, *, observe_reads: bool = False) -> dict:
    """THE native operation door (S1 B8): one admission, then exactly one family dispatcher.

    `_admit_operation` holds every refusal that precedes an owner call; `_OPERATION_FAMILY` names
    the one `_execute_<family>` below whose branch dispatches the operation (exactly-one coverage of
    READS | WRITES is checked at import). The families stay contiguous after this function because
    the dispatch citations -- writing_declarations.dispatch_site, tools/writing_verbs/gen_routes.py
    and writing.artifacts.declaration_sites -- are read from this region's own text.
    """
    payload = _admit_operation(root, project, mode, operation, payload, turn_id)
    if operation in {"concept_change", "logical_plan_change", "writing_style_change", "writing_style_profile_change"}:
        payload["by"] = "eigen:session"
    return _OPERATION_FAMILY[operation](root, project, mode, operation, payload, turn_id, observe_reads=observe_reads)


def _execute_source(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None, *,
        observe_reads: bool = False) -> dict:
    """Manuscript source: exact reads, proposals and applications, structure edits, document and builds."""
    if operation == 'reference_text':
        from laplace.research import literature
        return literature.observe_read(project,str(payload.get('key') or ''),root,
            int(payload.get('offset') or 0),int(payload.get('limit') or 24000),int(payload.get('source_index') or 0),persist=observe_reads,query=payload.get('query') or '',expected_source_revision=payload.get('expected_source_revision') or '')
    if operation == "apply_revision":
        from laplace.manuscript import source_application
        if not turn_id:
            raise ValueError("apply_revision requires the current project turn.")
        # A DISPATCHED CHILD PROPOSES; THE PARENT APPLIES.  This sits beside the review-mode
        # refusal above because it is the same kind of rule: the authority to change the
        # manuscript belongs to the turn the author is in, and a child's turn is not it.  The
        # fact is already on the child's own writing-turn row (`parent_turn_id`), so no second
        # permission list exists for children.
        if (writing_records.fold_records(root)["turns"].get(turn_id) or {}).get("parent_turn_id"):
            raise ValueError("A dispatched child proposes; the parent applies. Save this as a "
                             "proposal with propose_revision; the dispatching turn applies it.")
        return source_application.apply_revision(root, project, turn_id, payload)
    if operation == "section_change":
        from laplace.manuscript import manuscript_structure
        return manuscript_structure.change(project, payload, root)
    if operation == "block_change":
        from laplace.manuscript import blocks as manuscript_blocks
        return manuscript_blocks.change(root, project, payload)
    if operation == 'propose_revision':
        return tool_source.propose_revision(root, project, payload, turn_id)
    if operation == "proposal_supersede":
        from laplace.manuscript import manuscript_proposals
        current=writing_records.fold_records(root)["turns"].get(turn_id)
        if not current or current.get("project")!=project:
            raise ValueError("proposal_supersede requires the current project turn")
        return manuscript_proposals.supersede(
            root, project, {key:value for key,value in payload.items() if key != "project"},
            by="eigen:session", recorded_in_turn=turn_id)
    if operation == "build" or operation == "build_status":
        return tool_source.build(root, project, operation, payload)
    if operation == "document":
        from laplace.manuscript import document
        if payload.get('view') in {'template','template-candidates'}:
            from laplace.manuscript import document_templates
            return document_templates.inspect(project,{key:value for key,value in payload.items() if key!='project'},root,actor={'kind':'agent','turn_id':turn_id,'mode':mode})
        if payload.get('target_kind') in {'derived','publication-edition'}:
            from laplace.manuscript import build_targets
            return build_targets.read(project,root,target_kind=payload['target_kind'])
        return document.current(project,root)
    if operation == "style":
        from laplace.manuscript import document_templates
        return document_templates.change(project,{key:value for key,value in payload.items() if key!='project'},root,
            actor={'kind':'agent','turn_id':turn_id,'mode':mode})
    if operation == "export_pdf":
        from laplace.manuscript import document_style
        return document_style.export_pdf(project,root,mode=str(payload.get("mode") or "selected-source"),candidate_ref=payload.get("candidate_ref"),preview_ref=payload.get("preview_ref"))
    if operation == "chapter":
        from laplace.manuscript import manuscript_structure
        return manuscript_structure.create_chapter(project, payload.get("title", ""), root, expected_root_digest=payload.get("expected_root_digest"))
    if operation == "source":
        return tool_source.read_source(root, project, payload, turn_id)
    raise ValueError("Unknown project operation.")


def _execute_sessions(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None, *,
        observe_reads: bool = False) -> dict:
    """The current conversation: help, its session settings and its history."""
    if operation == "help":
        return _help_renderer(root, project, mode, payload, turn_id=turn_id)
    if operation == "session_settings":
        return tool_sessions.session_settings(root, project, payload, turn_id)
    if operation == "session_settings_change":
        return tool_sessions.session_settings_change(root, project, payload, turn_id)
    if operation == "conversation_history":
        return tool_sessions.conversation_history(root, project, payload, turn_id)
    raise ValueError("Unknown project operation.")


def _execute_work(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None, *,
        observe_reads: bool = False) -> dict:
    """Project Work: dispatches, tasks and notes, pipeline and stages, structure, framing and argument."""
    from laplace.work import project_work
    from laplace.pipeline import authoring
    if operation == "dispatch_plan" or operation == "dispatch" or operation == "dispatch_launch" or operation == "dispatch_continue" or operation == "dispatch_status" or operation == "dispatch_returns":
        return tool_work.dispatch(root, project, mode, operation, payload, turn_id, observe_reads=observe_reads)
    if operation == "pipeline":
        from laplace.manuscript import writing_pipeline
        from laplace.writing import stages as writing_stages
        view=str(payload.get("view") or "summary")
        if view not in {"summary","audit"}:raise ValueError("pipeline view must be summary or audit")
        result=writing_pipeline.inspect(project, root, include_history=view=="audit")
        stages=writing_stages.inspect(project,{},root)
        return {**result,"writing_stage":{"operation":"writing_stage",
            "http":"/work/writing-stage?project="+project,
            "schema_version":stages.get("schema_version"),
            "revision":stages.get("revision"),"stages":stages.get("stages")}}
    if operation == "writing_stage":
        from laplace.writing import stages as writing_stages
        return writing_stages.inspect(project,
            {key:value for key,value in payload.items() if key!="project"},root)
    if operation == "structure":
        from laplace.manuscript import project_structure
        scope={key:value for key,value in payload.items() if key!="project"}
        return project_structure.read(project,scope,root)
    if operation == "structure_change":
        from laplace.manuscript import project_structure
        admitted=writing_records.index(root).turns.get(turn_id) or {}
        if payload.get('action') in {'restructure','recover-restructure','undo-restructure','reconcile-restructure'} and admitted.get('project')!=project:
            raise ValueError('Structural application requires the actual admitted caller turn in this project.')
        return project_structure.change(project, payload, root,actor={'kind':'agent','turn_id':turn_id,'mode':mode,'dispatch_id':admitted.get('dispatch_id')})
    if operation == "workflow_definition_change":
        return tool_work.workflow_definition(root, project, mode, payload, turn_id)
    if operation == "project":
        # detail joins the Scoped reads: the Work owner issues its continuity_read (or an explicit gap) from this actual Scope
        if payload.get('view') in {'review-evidence', 'provenance', 'continuity', 'detail'} or payload.get('view') == 'review' and ('phase_revision' in payload or 'obligation_id' in payload):
            from laplace.work import owner_discovery,project_work_views
            return {**project_work_views.read(project, {key: value for key, value in payload.items() if key != 'project'}, root,
                mode=mode, native_caller=owner_discovery.project_scope(project,'native')),
                **_read_extras(operation, project)}
        if payload.get('view') == 'workflow-definitions':
            from laplace.pipeline import workflow_definitions
            from laplace.work import project_work_views
            return project_work_views.read(project, {key: value for key, value in payload.items() if key != 'project'}, root,
                                           mode=mode, native_caller=workflow_definitions.native_caller(root, project, mode, turn_id))
        return {**project_work.read(project,{key:value for key,value in payload.items() if key!='project'},root,mode=mode),
                **_read_extras(operation, project)}
    if operation == "framing":
        return project_work.framing(project, payload, root)
    if operation == "argument":
        return authoring.save(project, payload, root)
    if operation == "task":
        if payload.get("action")=="planning" and mode=="review":raise ValueError("Review role cannot change existing Work planning.")
        if mode == "review":
            payload = {**payload, "origin": "eigen:review", "by": "eigen:review"}
        return project_work.task(project, payload, root)
    if operation == "work_review":
        # the native door of the review lifecycle: the caller's admitted turn is the recording identity
        from laplace.work import project_work_review
        return project_work_review.bounded_ack(project, project_work_review.record(
            project, payload, root, door={"origin": "native", "turn_id": turn_id}, mode=mode))
    if operation == "development_source":
        # the development-source grant over a configured repository (in-harness join): the admitted turn is the actor;
        # the owner refuses every mutation or check to a review-role turn and rechecks the grant before any effect
        from laplace.work import development_source
        return development_source.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})
    if operation == "work_delivery":
        # the Work recipient delivery (in-harness join): durable idempotent submission beside the review phases
        from laplace.work import work_delivery
        return work_delivery.handle(root, project, payload, {"origin": "native", "turn_id": turn_id})
    if operation == "task_status":
        if payload.get("status") == "verified":
            raise ValueError("Independent verification cannot be self-awarded by the producing session.")
        if payload.get("status") == "done" and turn_id:
            payload["completed_in_turn"] = turn_id
        return project_work.transition(project, payload, root)
    if operation == "note":
        if payload.get("scope") == "global":
            raise ValueError("A writing session cannot turn a project note into global law.")
        return authoring.bank_correction(project, {**payload, "by":"eigen:review" if mode == "review" else "eigen:session"}, root)
    if operation == "note_status":
        return authoring.correction_status(project, {
            **payload, "by":"eigen:review" if mode == "review" else "eigen:session"}, root)
    raise ValueError("Unknown project operation.")


def _execute_project(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None, *,
        observe_reads: bool = False) -> dict:
    """Project state: repository, storage, metadata and settings, materials, artifacts and history."""
    from laplace.pipeline import authoring
    if operation == "repository":
        from laplace.projects import writing_sources
        return writing_sources.execute(root, payload, interface=_interface_projection)
    if operation == "storage":
        from laplace.projects import writing_storage
        return writing_storage.inspect(project, root)
    if operation == "storage_prune":
        from laplace.projects import writing_storage
        return writing_storage.prune(project, payload, root)
    if operation == "project_metadata":
        from laplace.projects import library as writing_projects
        return writing_projects.metadata(project,root)
    if operation == "app_settings":
        from laplace.projects import library as writing_projects
        from jsonschema import Draft202012Validator
        fields = {key: value for key, value in payload.items() if key != "project"}
        error = next(Draft202012Validator(writing_projects.app_settings_contract()).iter_errors(fields), None)
        if error is not None: raise ValueError("App settings read does not match its owner contract: " + error.message)
        return writing_projects.app_settings(root, **{key: value for key, value in fields.items() if key != "by"})
    if operation == "material_references":
        from laplace.projects import library as writing_projects
        from jsonschema import Draft202012Validator
        fields = {key: value for key, value in payload.items() if key != "project"}
        error = next(Draft202012Validator(writing_projects.material_reference_contract()["read"]).iter_errors(fields), None)
        if error is not None:
            raise ValueError("Material reference read does not match its owner contract: " + error.message)
        return writing_projects.material_references(project, root, **{key: value for key, value in fields.items() if key != "by"})
    if operation == "material_reference_change":
        from laplace.projects import library as writing_projects
        return writing_projects.change_material_reference(project, {**payload, "by": "eigen:session"}, root)
    if operation == "project_metadata_change":
        from laplace.projects import library as writing_projects
        return writing_projects.change_metadata(project,
            {**{key:value for key,value in payload.items() if key!="project"},
             "by":"eigen:session"},root)
    if operation == "materials":
        from laplace.projects import artifacts
        material_payload = {k: v for k, v in payload.items() if k != "project"}
        return artifacts.catalogue(root, project, material_payload)
    if operation == "author_history":
        if payload.get('view')=='source':
            from laplace.work import history as author_history
            return author_history.source(project,payload,root)
        if payload.get("view") not in (None,"","corrections","activity","telemetry","record","structural-undo"):
            raise ValueError("author_history view must be corrections, activity, telemetry, record, or structural-undo")
        if payload.get("view")=="activity":
            from laplace.work import history as author_history
            author_history.validate_activity_query(payload)
            page=author_history.comparison_page(payload)
            return (author_history.detail(project,str(payload["id"]),root,comparison_offset=page[0],comparison_limit=page[1]) if payload.get("id")
                    else author_history.history(project,payload,root))
        if payload.get("view")=="telemetry":
            from laplace.work import history as author_history
            return author_history.telemetry(project,payload,root)
        if payload.get("view")=="structural-undo":
            from laplace.work import history as author_history
            return author_history.structural_undo(project,payload,root)
        if payload.get("view")=="record":
            from laplace.work import history as author_history
            if not payload.get("id"):raise ValueError("author_history record requires an exact activity id")
            return author_history.record(project,str(payload["id"]),root)
        return authoring.history(project, payload, repo_root=root)
    if operation == "author_changes":
        from laplace.manuscript import manuscript_fragments
        return manuscript_fragments.change_preview(project, payload, root)
    if operation == "read_artifact":
        from laplace.projects import artifacts
        return artifacts.read(root, project, payload)
    if operation == "store_artifact":
        from laplace.projects import artifacts
        return artifacts.store(root, project, payload, turn_id)
    if operation == 'research_object_change':
        from laplace.work import object_facets, owner_discovery
        return object_facets.change(root, owner_discovery.project_scope(project, 'native'), payload,
            door={'origin': 'native', 'turn_id': turn_id, 'mode': mode})
    if operation == 'research_handover':
        from laplace.projects import project_handover
        from laplace.work import owner_discovery
        return project_handover.object_request(root, owner_discovery.project_scope(project, 'native'),
            {'project': project, **payload}, door={'origin': 'native', 'turn_id': turn_id, 'mode': mode})
    raise ValueError("Unknown project operation.")


def _execute_style(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None, *,
        observe_reads: bool = False) -> dict:
    """Writing profiles, writing style and project guidance."""
    if operation in {"profile", "profile_change"}:
        from laplace.manuscript import profiles
        values = {key:value for key,value in payload.items() if key != "project"}
        actor = {"kind":"agent", "turn_id":turn_id, "mode":mode}
        turn = writing_records.index(root).turns.get(turn_id) or {}
        if turn.get("dispatch_id"): actor["dispatch_id"] = turn["dispatch_id"]
    if operation == "profile":
        return profiles.inspect(project, values, root, actor=actor)
    if operation == "profile_change":
        return profiles.change(project, values, root, actor=actor)
    if operation == "writing_style":
        from laplace.manuscript import writing_style
        return writing_style.inspect(project, {k:v for k,v in payload.items() if k!="project"}, root)
    if operation == "writing_style_calibration":
        from laplace.manuscript import writing_style
        return writing_style.calibration(project, {k:v for k,v in payload.items() if k!="project"}, root)
    if operation == "writing_style_change":
        from laplace.manuscript import writing_style
        return writing_style.save(project, payload, root)
    if operation == "writing_style_profile_change":
        from laplace.manuscript import writing_style
        return writing_style.update_profile(project, {k:v for k,v in payload.items() if k!="project"}, root)
    if operation == "project_guidance":
        from laplace.manuscript import project_protocol
        return project_protocol.read(project, payload, root)
    if operation == "project_guidance_change":
        from laplace.manuscript import project_protocol
        return project_protocol.change(project, payload, root)
    raise ValueError("Unknown project operation.")


def _execute_owner_http(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None, *,
        observe_reads: bool = False) -> dict:
    """The surface owners' HTTP handlers, forwarded once (the scanner handler contract, explicit root).

    The Research operations are not here: `_execute_research` calls the Research owners directly."""
    from laplace.research import concepts as concepts_surface, references_surface, visuals_surface, formal_surface
    routes = {
        "concept": (concepts_surface,
                    "/concepts/source" if payload.get("source_index") is not None else "/concepts/context", "GET"),
        "concept_tree": (concepts_surface, "/concepts/tree", "GET"),
        "concept_history": (concepts_surface, "/concepts/history", "GET"),
        "concept_change": (concepts_surface, "/concepts/change", "POST"),
        "logical_plan": (concepts_surface,
                         "/concepts/catalog" if payload.get("view")=="catalog" else "/concepts/plan/context", "GET"),
        "logical_plan_change": (concepts_surface, "/concepts/plan/change", "POST"),
        "references": (references_surface, "/references/search", "GET"),
        "literature_discover": (references_surface, "/references/literature-discover", "GET"),
        "literature_lookup": (references_surface, "/references/literature-lookup", "GET"),
        "literature_import": (references_surface, "/references/literature-import", "POST"),
        "literature_bind": (references_surface, "/references/literature-bind", "POST"),
        "literature_scope": (references_surface, "/references/literature-scope", "GET"),
        "reference_fetch": (references_surface, "/references/fetch", "POST"),
        "literature_uses": (references_surface, "/references/literature-uses", "GET"),
        "reference": (references_surface, "/references/item", "GET"),
        "reference_source": (references_surface, "/references/source", "GET"),
        "reference_text": (references_surface, "/references/text", "GET"),
        "references_attached": (references_surface, "/references/attached", "GET"),
        "reference_attach": (references_surface, "/references/attach", "POST"),
        "reference_update": (references_surface, "/references/update", "POST"),
        "reference_refresh": (references_surface, "/references/refresh", "POST"),
        "visuals": (visuals_surface, "/visuals/state", "GET"),
        "visual_create": (visuals_surface, "/visuals/create", "POST"),
        "visual_render": (visuals_surface, "/visuals/render", "POST"),
        "visual_place": (visuals_surface, "/visuals/place", "POST"),
        "proof_targets": (formal_surface, "/formal/targets", "GET"),
        "proofs": (formal_surface, "/formal/state", "GET"),
        "proof_check": (formal_surface, "/formal/check", "POST"),
    }
    owner, route, method = routes[operation]
    query = {k: [json.dumps(v,separators=(',',':')) if operation=='reference_source' and k=='original' else str(v)] for k, v in payload.items() if v is not None}
    # Adapters expose the scanner handler contract; explicit root seams are used
    # where provided so integration fixtures stay isolated.
    import inspect
    kwargs = {}
    if "repo_root" in inspect.signature(owner.handle).parameters:
        kwargs["repo_root"] = root
    elif "root" in inspect.signature(owner.handle).parameters:
        kwargs["root"] = root
    status, _, raw = owner.handle(route, query, method, json.dumps(payload).encode(), **kwargs)
    result = json.loads(raw)
    if status >= 400:
        raise OwnerError(result)
    return result


def _execute_research(root: Path, project: str, mode: str, operation: str, payload: dict, turn_id: str | None, *,
        observe_reads: bool = False) -> dict:
    """The Research owners, called directly with the explicit root (research family R1, 2026-10-19).

    These are the same owner functions the /research HTTP routes call (laplace.web.research_surface), with the same
    (status, value) contract: one implementation, two doors. A refusal (status >= 400) is the owner's own answer."""
    from laplace.research import research_catalogue, research_records, research_runs
    named = project or str(payload.get("project") or "")
    if operation == "research":
        if payload.get('view')=='record-request':
            return _owner_answer((200,research_records.inspect_request(project,payload['request'],root)))
        return _owner_answer(research_catalogue.state_read(project, root, view=str(payload.get("view") or ""), ident=str(payload.get("id") or "")))
    if operation == "run_status":
        if 'request' in payload:
            return _owner_answer((200,research_runs.inspect_request(project,payload['request'],root)))
        return _owner_answer(research_runs.run_status_read(project, str(payload.get("id") or ""), root))
    if operation == "research_reconcile":
        return _owner_answer(research_records.reconcile(named, payload, root=root))
    if operation == "research_record":
        return _owner_answer(research_records.record(named, payload, root=root))
    if operation == "research_producer":
        return _owner_answer(research_runs.register_producer(named, payload, root=root))
    if operation == "experiment_run":
        return _owner_answer(research_runs.launch(named, payload, root=root))
    if operation == "run_cancel":
        return _owner_answer(research_runs.cancel(named, payload, Path(root)))
    raise ValueError("Unknown research operation.")


#: Implementation grouping only: which `_execute_<family>` holds an operation's branch. It restates
#: no verb, concept, permission, schema or guard (writing_verbs / writing_declarations own those);
#: the check below refuses any operation of READS | WRITES that is not in exactly one family.
_FAMILY_OPERATIONS = {
    _execute_source: frozenset({"reference_text", "apply_revision", "section_change", "block_change",
                                "propose_revision", "proposal_supersede", "build", "build_status", "document",
                                "style", "export_pdf", "chapter", "source"}),
    _execute_sessions: frozenset({"help", "session_settings", "session_settings_change", "conversation_history"}),
    _execute_work: frozenset({"dispatch_plan", "dispatch", "dispatch_launch", "dispatch_continue", "dispatch_status", "dispatch_returns",
                              "pipeline", "writing_stage", "structure", "structure_change", "project", "framing",
                              "argument", "task", "task_status", "work_review", "note", "note_status",
                              "development_source", "work_delivery", "workflow_definition_change"}),
    _execute_project: frozenset({"repository", "storage", "storage_prune", "project_metadata", "app_settings",
                                 "material_references", "material_reference_change", "project_metadata_change",
                                 "materials", "author_history", "author_changes", "read_artifact", "store_artifact",
                                 "research_object_change", "research_handover"}),
    _execute_style: frozenset({"profile", "profile_change", "writing_style", "writing_style_calibration",
                               "writing_style_change", "writing_style_profile_change", "project_guidance",
                               "project_guidance_change"}),
    _execute_owner_http: frozenset({"concept", "concept_tree", "concept_history", "concept_change", "logical_plan",
                                    "logical_plan_change", "references", "literature_discover", "literature_lookup",
                                    "literature_import", "literature_bind", "literature_scope", "reference_fetch",
                                    "literature_uses", "reference", "reference_source", "references_attached",
                                    "reference_attach", "reference_update", "reference_refresh", "visuals",
                                    "visual_create", "visual_render", "visual_place", "proof_targets", "proofs",
                                    "proof_check"}),
    _execute_research: frozenset({"research", "research_reconcile", "research_record", "research_producer",
                                  "experiment_run", "run_status", "run_cancel"}),
}


_OPERATION_FAMILY = {operation: family for family, operations in _FAMILY_OPERATIONS.items() for operation in operations}


def _read_extras(operation: str, project: str) -> dict:
    """What the native door adds beside a read's owner result: for a project (Work) read, the proposal review read."""
    if operation != "project":
        return {}
    from laplace.manuscript.proposal_navigation import handle
    return {'review_read': handle(project, {})}


def replay_read(root: Path, project: str, mode: str, read: dict, turn_id: str | None) -> dict:
    """THE PURE REPLAY of one consumed read (writing.delivery, step 4): the owner call with the recorded request and the
    retained semantic projection, so an unchanged owner reproduces the receipted bytes and a genuine change shows in the
    digest. It banks, publishes, acknowledges and refreshes nothing. A legacy read row (no projection) replays with the
    owner's own default, as before."""
    from laplace.writing import delivery
    operation = str(read.get("operation") or "")
    with delivery.planned(replay=read.get("projection")):
        return _execute(root, project, mode, operation, dict(read.get("payload") or {}), turn_id=turn_id)


_covered = [operation for operations in _FAMILY_OPERATIONS.values() for operation in operations]
if len(_covered) != len(set(_covered)) or set(_covered) != READS | WRITES:
    raise RuntimeError("native family dispatch must cover READS | WRITES exactly once: missing %s, extra %s"
                       % (sorted((READS | WRITES) - set(_covered)), sorted(set(_covered) - (READS | WRITES))))
del _covered


from laplace.writing import tool_sessions, tool_source, tool_work  # noqa: E402  the long family bodies (cycle-safe: imported last)
