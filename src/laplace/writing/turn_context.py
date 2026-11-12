"""TURN CONTEXT (S1 B1): what one author turn may carry, validated before it is delivered.

Pure request-local assembly used by writing.turn_admission (and steering in writing.turn_control):

  _selection_draft / _draft_prompt   the author's exact source selection and unsaved draft (bounded,
                                     _DRAFT_TEXT_LIMIT), quoted into the prompt as the author's pointer.
  _workspace_context                 the view the author is in, validated against canonical structure
                                     (_WORKSPACE_SURFACES) and the proposal/application owners.
  _queued_requests                   exact queued Work requests carried into this turn.
  without_already_delivered          THE ONE DELTA over a delivery: a part whose token the session
                                     already holds is withheld, the rest is the prompt body.
  _orientation_snapshot / _legacy_registration_compatibility / _latest_session_turn
                                     the facts a continuing native session is checked against.

Nothing here banks, mutates a session or caches across requests; the journal fold is read through
records.fold_records and proposal facts through the proposal-view owner, writing.proposal_currentness.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from laplace.writing.session_projection import reply_presentation_text
from laplace.writing import records as writing_records


_WORKSPACE_SURFACES = {"project", "manuscript", "structure", "evidence", "concepts", "review",
                       "sources", "argument", "presentation", "research", "formal", "visuals"}


_DRAFT_TEXT_LIMIT = 64_000


def _selection_draft(value) -> tuple[dict | None,dict | None]:
    """Separate an unsaved editor draft from canonical source attention."""
    if value is None:return None,None
    if not isinstance(value,dict):raise ValueError("selection must be an object")
    selection=dict(value);draft=selection.pop("draft",None)
    if draft is None:return selection,None
    if not isinstance(draft,dict) or set(draft)-{"status","format","text","anchor","reason"}:
        raise ValueError("selection.draft must contain only status, format, text, anchor, and reason")
    if draft.get("status")!="UNSAVED":raise ValueError("selection.draft status must be UNSAVED")
    if draft.get("format") not in {"tex","rendered"}:
        raise ValueError("selection.draft format must be tex or rendered")
    text=draft.get("text")
    if not isinstance(text,str):raise ValueError("selection.draft text must be a string")
    if len(text)>_DRAFT_TEXT_LIMIT:
        raise ValueError(f"selection.draft text is limited to {_DRAFT_TEXT_LIMIT} characters")
    reason=draft.get("reason")
    if not isinstance(reason,str) or len(reason)>1000:
        raise ValueError("selection.draft reason must be a string of at most 1000 characters")
    anchor=draft.get("anchor")
    if not isinstance(anchor,dict) or set(anchor)-{"file","line_start","line_end"}:
        raise ValueError("selection.draft anchor must contain only file, line_start, and line_end")
    file=str(anchor.get("file") or "")
    raw=Path(file)
    if not file or len(file)>1000 or raw.is_absolute() or ".." in raw.parts:
        raise ValueError("selection.draft anchor.file must be a project-relative source path")
    start,end=anchor.get("line_start"),anchor.get("line_end")
    if (isinstance(start,bool) or not isinstance(start,int) or start<1 or
            isinstance(end,bool) or not isinstance(end,int) or end<start):
        raise ValueError("selection.draft anchor requires positive line_start and line_end")
    return selection,{"status":"UNSAVED","format":draft["format"],"text":text,
                      "anchor":{"file":file,"line_start":start,"line_end":end},
                      "reason":reason}


def _draft_prompt(draft:dict|None)->str:
    if not draft:return ""
    return ("\n\nUNSAVED LOCAL EDITOR DRAFT (not persisted source)\n"
            "The author is showing these exact local words before saving. They are not a source read, "
            "revision guard, validated TeX, or evidence that the manuscript contains them. Use them to "
            "understand the request, but use the source tool with the anchor file to read persisted bytes "
            "before proposing or applying an edit. Never use this draft as an expected_source_digest or "
            "an edit's before value, and do not claim it was saved.\n"+
            json.dumps(draft,ensure_ascii=False))


def _workspace_context(root: Path, project: str, value) -> dict:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError("workspace_context must be an object")
    unknown=set(value)-{"surface","node_id","node_ids","label","beat_id","section_ids","review","structure_observation","workflow_action","material_read","object_context"}
    if unknown:raise ValueError("workspace_context has unsupported fields: "+", ".join(sorted(unknown)))
    object_context = None
    if 'object_context' in value:
        from laplace.work.object_facets import resolve_object_context
        resolve_object_context(root, project, value['object_context'])
        # Keep the exact closed pointer carrier, not the owner's expanded read
        # observation (which is not a legal input to a later Send or steer).
        object_context = json.loads(json.dumps(value['object_context']))
    surface = str(value.get("surface") or "").strip()
    if surface not in _WORKSPACE_SURFACES:
        raise ValueError("workspace_context surface is unknown")
    from laplace.manuscript import project_structure
    from laplace.manuscript import bindings
    observation = (bindings.validate_observation(project, root, value["structure_observation"])
                   if "structure_observation" in value else None)
    try:
        structure = bindings.reader_snapshot(project, root)
    except ValueError:
        structure = {"sections": [], "nodes": []}
    sections = {str(row.get("id")): row for row in structure.get("sections", []) if row.get("id")}
    nodes = {str(row.get("id")) for row in
             list(structure.get("nodes", []))+list(structure.get("logical_objects", []))
             if row.get("id")}
    section_ids = [str(item) for item in value.get("section_ids") or []]
    if any(item not in sections for item in section_ids):
        raise ValueError("workspace_context names an unavailable plan section")
    node_id = str(value.get("node_id") or "").strip()
    raw_node_ids=value.get("node_ids") or []
    if (not isinstance(raw_node_ids,list) or len(raw_node_ids)>500
            or any(not isinstance(item,str) or not item.strip() for item in raw_node_ids)):
        raise ValueError("workspace_context node_ids must contain at most 500 canonical identities")
    node_ids=list(dict.fromkeys(item.strip() for item in raw_node_ids))
    beat_id = str(value.get("beat_id") or "").strip()
    if node_id and node_id not in nodes:
        project_structure.focused_node(project, node_id, root)  # validates canonical unplanned nodes
    for ident in node_ids:
        if ident not in nodes:
            project_structure.focused_node(project,ident,root)
    beat_ids = {str(beat) for section in sections.values() for beat in section.get("beat_ids", [])}
    if beat_id and beat_id not in beat_ids:
        raise ValueError("workspace_context names an unavailable plan beat")
    for section in sections.values():
        members = set(section.get("node_ids", [])) | set(section.get("beat_ids", []))
        if (node_id and node_id in members) or (beat_id and beat_id in members):
            if section["id"] not in section_ids:
                section_ids.append(section["id"])
    label=str(value.get("label") or "").strip()
    if len(label)>240:raise ValueError("workspace_context label is too long")
    review_value=value.get("review");review=None
    if review_value is not None:
        if surface!="review" or not isinstance(review_value,dict) or set(review_value)-{"turn_id","application_ids"}:
            raise ValueError("workspace_context review requires only turn_id/application_ids on the review surface")
        turn_id=str(review_value.get("turn_id") or "").strip();application_ids=review_value.get("application_ids")
        if (not turn_id or not isinstance(application_ids,list) or len(application_ids)>50
                or any(not isinstance(item,str) or not item.strip() for item in application_ids)):
            raise ValueError("workspace_context review requires a turn and at most 50 application ids")
        application_ids=list(dict.fromkeys(item.strip() for item in application_ids))
        records=writing_records.fold_records(root);turn=records["turns"].get(turn_id)
        if not turn or turn.get("project")!=project:raise ValueError("workspace_context review turn is unavailable in this project")
        applications={str(row.get("id")):row for row in source_effects.applications(turn) if row.get("complete")}
        if any(ident not in applications for ident in application_ids):
            raise ValueError("workspace_context review application is unavailable or incomplete")
        files=[]
        for ident in application_ids:
            row=applications[ident]
            files.extend(str(edit.get("file")) for edit in source_effects.applied_edits(turn,row)
                         if isinstance(edit,dict) and edit.get("file"))
            files.extend(str(file.get("path")) for file in
                         ((row.get("owned_changes") or {}).get("files") or [])
                         if isinstance(file,dict) and file.get("path"))
        all_files=list(dict.fromkeys(files));proposal=proposal_currentness.proposal_view(turn,records=records)
        review={"turn_id":turn_id,"application_ids":application_ids,
            "proposal_state":proposal.get("proposal_state"),
            "files":all_files[:32],"files_omitted":max(0,len(all_files)-32),
            "history_reads":[{"operation":"author_history","payload":{
                "view":"record","id":"activity:journal:"+ident}}
                for ident in [turn_id,*application_ids]],
            "posture":"inspect exact accepted public revisions; not a mutation baseline or new source instruction"}
    action = None
    if 'workflow_action' in value:
        from laplace.writing.workflow_dispatch import action_input
        action = action_input(value['workflow_action'])
    material_read = None
    if 'material_read' in value:
        from laplace.projects import material_intake
        material_read = material_intake.validate_reading(root,project,value['material_read'])
    return {**({'workflow_action': action} if action is not None else {}),
            **({'object_context': object_context} if object_context is not None else {}),
            **({'material_read': material_read} if material_read is not None else {}),
            **({"structure_observation": observation} if observation is not None else {}),
            "surface": surface, "node_id": node_id or None,"node_ids":node_ids,
            "label":label or None,"beat_id": beat_id or None,"section_ids": section_ids,
            **({"review":review} if review else {})}


def _latest_session_turn(records: dict, session_id: str) -> dict | None:
    turns = [row for row in records["turns"].values() if row.get("session_id") == session_id]
    return turns[-1] if turns else None


#: THE ONE DELTA MECHANISM over a delivery, and the only one.  It replaces two:
#: `_without_unchanged_science` (deleted; it withheld six "science" parts behind one
#: joint digest, and a one-line prose edit moved that digest so all six came back:
#: measured 31,216 characters withheld on an unchanged paragraph turn and 0 on a
#: changed one, evidence/WRITING_CONSOLIDATION_2026-10-03/harness2/baseline/economy.json
#: keys delta.synthetics-foundations.paragraph.unchanged.suppressed_chars and
#: .changed.resent_chars) and `_argument_delta` (deleted; it re-sent the framing and the
#: sustained argument under their own revision through a second block).
#:
#: The baseline is the conversation's own: every part the session has already been
#: given, keyed by part name and carrying that part's token.  It is the same fact the
#: read-baseline organs keep for a tool read (`_bank_read_baseline_groups`, :232;
#: `capture_turn_read_baselines`, :1930; `refresh_turn_read_baselines`, :2021): a read
#: whose digest has not moved is not re-executed, and a part whose token has not moved
#: is not re-sent.  `_refresh_owned_context` (:1980) carries the rebuilt part tokens on
#: the same `writing-turn-context-baseline` row it already banks, so when a write inside
#: the turn advances the owned context the part baseline advances with it.
def without_already_delivered(parts, held: Mapping[str, Any] | None, *,
                              brief_delta: tuple[Any, Any] | None = None,
                              also_delivered=(), body_delivered=False) -> dict:
    """Split a delivery into what this conversation still needs and what it holds.

    Returns the delivered text, the withheld parts each with the declared read that
    reaches its facts, and the part baseline to bank for the next turn.  A part absent
    from this delivery keeps its earlier token: the conversation still carries it, so an
    altitude that comes back to it unchanged is still not re-sent.

    The text ends in THE ONE delta block, written by the one producer the contract names
    (`writing_operating.turn_delta`): what this conversation already holds and what moved
    since its last turn, in one place and one grammar.  `brief_delta` is the pair of
    orientation snapshots (the last turn's, this turn's). The current brief's body uses
    the same per-part baseline; `body_delivered` marks its delivery by a new session's
    adapter so the first turn records its tokens without sending those bytes twice.
    """
    baseline = {str(key): value for key, value in (held or {}).items()}
    rows = [part for part in (parts or []) if isinstance(part, Mapping)]
    from laplace.writing import operating as writing_operating
    previous_orientation, current_brief = brief_delta if brief_delta else (None, {})
    body_parts = writing_operating.body_parts(current_brief) if brief_delta else []
    if body_delivered:
        # A new native session gets these bytes from its adapter on this very turn.
        baseline.update({part['key']: part['token'] for part in body_parts})
    rows.extend(body_parts)
    sent, withheld = [], []
    for part in rows:
        key = str(part.get("key") or "")
        # A token match saves bytes only when the delivery can name an executable
        # current-content read. Parts without one stay in-band; prior conversation
        # retention is explicitly not evidence that provider compaction kept them.
        if key and baseline.get(key) == part.get("token") and part.get("read") is not None:
            withheld.append(part)
        else:
            sent.append(part)
    body_keys = {part['key'] for part in body_parts}
    prompt = "\n\n".join(str(part.get("text") or "") for part in sent if part.get('key') not in body_keys)
    changed_body = {part['key'].removeprefix('operating_brief.'): part['value']
                    for part in sent if part.get('key') in body_keys}
    held_now = dict(baseline)
    held_now.update({str(part.get("key") or ""): part.get("token") for part in rows
                     if part.get("key")})
    notice = [{"part": str(part.get("key") or ""), "chars": int(part.get("chars") or 0),
               "read": part.get("read")} for part in withheld]
    delta = writing_operating.turn_delta(None if body_delivered else previous_orientation,
                                         {} if body_delivered else current_brief,
                                         list(notice) + list(also_delivered or ()), changed_body=changed_body)
    if delta["block"]:
        prompt += ("\n\n" if prompt else "") + delta["block"]
    return {"prompt": prompt, "withheld": notice, "held": held_now, "delta": delta,
            "sent_chars": len(prompt), "withheld_chars": sum(row["chars"] for row in notice)}


def _orientation_snapshot(brief: dict) -> dict:
    voice = brief.get("writing_style") or {}
    protocol = brief.get("project_protocol") or {}
    return {"selected_source": dict(brief.get("selected_source") or {}),
            "tool_contract_digest": brief.get("tool_contract_digest"),
            "native_registration_signature":brief.get("native_registration_signature"),
            "exact_action_digests":dict(brief.get("exact_action_digests") or {}),
            "action_catalogue_digest":brief.get("action_catalogue_digest"),
            "role_permissions_digest":brief.get("role_permissions_digest"),
            "shared_rules_revision": brief.get("shared_rules_revision"),
            "capability_guidance_revision":brief.get("capability_guidance_revision"),
            "writing_style": {key: voice.get(key) for key in
                              ("revision", "selected_profile", "profile_revision", "guidance_sha256")},
            "architecture_prior": {key: (brief.get("architecture_prior") or {}).get(key)
                                   for key in ("revision", "status", "profile_revision", "scope", "source")},
            "project_protocol": {"revision": protocol.get("revision")},
            "workspace": dict(brief.get("workspace") or {})}


def _legacy_registration_compatibility(session:dict,previous_turn:dict|None,brief:dict)->dict:
    """Establish an old binding's gateway shape only from its saved operation set."""
    if session.get("tool_contract_digest")==brief.get("tool_contract_digest"):
        return {"compatible":True,"basis":"saved full contract digest matches current contract"}
    prior=(previous_turn or {}).get("operating_brief") or {}
    permissions=prior.get("permissions")
    gateway=(((brief.get("operation_contract") or {}).get("inputSchema") or {})
             .get("properties",{}).get("operation",{}).get("enum"))
    if (prior.get("schema_version")=="laplace.writing-operating-brief/1"
            and session.get("role","author")!="review" and isinstance(permissions,list)
            and isinstance(gateway,list)):
        from laplace.writing import operating as writing_operating
        reconstructed=writing_operating.legacy_v1_registration_signature(permissions)
        if reconstructed is None:
            return {"compatible":False,"basis":"saved v1 operation set is malformed"}
        if set(permissions)!=set(gateway):
            return {"compatible":False,"basis":"saved v1 operation enum differs from current gateway enum",
                    "reconstructed_signature":reconstructed}
        if reconstructed!=brief.get("native_registration_signature"):
            return {"compatible":False,"basis":"saved v1 structural registration differs from current gateway schema or callback protocol",
                    "reconstructed_signature":reconstructed,
                    "current_signature":brief.get("native_registration_signature")}
        return {"compatible":True,"basis":"reconstructed saved v1 structural registration matches current signature",
                "operations":len(gateway),"reconstructed_signature":reconstructed}
    return {"compatible":False,"basis":"legacy binding has no native registration signature or complete comparable operation set"}


def _queued_requests(project: str, values, root: Path) -> list[dict]:
    if values in (None, []):
        return []
    if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
        raise ValueError("queued_work_ids must be an array of request IDs")
    ids = list(dict.fromkeys(values))
    if len(ids) > 50:
        raise ValueError("queued_work_ids is limited to 50 requests")
    from laplace.work import project_work
    tasks = {str(row.get("id")): row for row in project_work.state(project, root).get("tasks", [])
             if row.get("id")}
    queued = []
    for ident in ids:
        task = tasks.get(ident)
        if task is None:
            raise ValueError("queued request is unavailable in this project: " + ident)
        if task.get("task_kind") != "session-request":
            raise ValueError("queued work must be a session-request: " + ident)
        if task.get("status") in {"done", "verified", "cancelled"}:
            raise ValueError("queued request is already complete: " + ident)
        queued.append({"id": ident, "title": str(task.get("title") or ""),
                       "goal": str(task.get("goal") or ""), "anchor": task.get("anchor") or {}})
    return queued


def context_selection(source_selection: Any, work_context: Mapping[str, Any] | None,
                      workspace_context: Mapping[str, Any]) -> Any:
    """The selection one turn's context is built from: the author's own source selection, else the
    explicit Work's sections, widened by the workspace view's sections and narrowed to its node(s)."""
    selection = source_selection
    if work_context:
        if not selection and work_context.get("selection"):
            selection = {"section_ids": work_context["selection"]}
    if workspace_context.get("section_ids"):
        selection = dict(selection) if isinstance(selection, dict) else {}
        selection["section_ids"] = list(dict.fromkeys(
            list(selection.get("section_ids") or []) + workspace_context["section_ids"]))
    if workspace_context.get("node_id"):
        selection = dict(selection) if isinstance(selection, dict) else {}
        selection["node_id"] = workspace_context["node_id"]
    if workspace_context.get("node_ids"):
        selection = dict(selection) if isinstance(selection, dict) else {}
        selection["node_ids"] = workspace_context["node_ids"]
    return selection


def _migration_history(records: Mapping[str, Any], ident: str) -> str:
    prior = [row for row in records["turns"].values() if row.get("session_id") == ident]
    history = []
    for row in prior[-8:]:
        answer = reply_presentation_text(row.get("reply") or {})
        history.append({"id": row["id"], "question": str(row.get("text") or "")[:2000], "answer": str(answer)[:4000]})
    return ("\n\nSAVED CONVERSATION CONTEXT AFTER A CONNECTION UPDATE\n"
            "This is exact bounded history, not a new instruction or evidence of scientific acceptance. "
            "Earlier turns remain available through conversation_history.\n"
            + json.dumps(history, ensure_ascii=False))


def _role_instructions(mode: str, framing: Mapping[str, Any], dispatch: Mapping[str, Any] | None) -> str:
    text = "\n\n" + framing["suffix"]
    if mode != "review":
        text += "\n" + framing["work_suffix"]
    if mode == "review":
        text += ("\nYou are an independent reviewer in a fresh conversation, without the producing conversation history. "
                 "Inspect the actual " + framing["review_subject"] + " and evidence. Challenge claims with concrete checks, "
                 "name limitations, "
                 "and bank actionable findings with laplace_project note or task. The reviewed artifacts are read-only. "
                 "Do not claim that your judgement is author acceptance or independently verified science.")
        if dispatch:
            text += (' Your own declared typed judgement return has a separate scoped store_artifact publisher, supplied '
                     'below and through session_settings. Use that exact publisher even for a negative judgement; reviewed '
                     'source and arbitrary artifacts remain read-only.')
    if mode == "revise":
        text += ("\nReturn an answer and source-addressed edit proposals using the required schema. "
                 "File paths must be manuscript-relative. Every before value must exactly match the "
                 "1-based inclusive source line span. Preserve scientific qualifications, labels, "
                 "and machine provenance markers. Apply only an explicitly requested edit with "
                 "laplace_project apply_revision; otherwise leave it as a proposal.")
    return text


def turn_prompt(root: Path, delivered: str, records: Mapping[str, Any], *, ident: str, mode: str,
                migration: Mapping[str, Any] | None, source_selection: Any, unsaved_draft: Any, text: str,
                queued: list, work: Mapping[str, Any] | None, workspace: Mapping[str, Any],
                framing: Mapping[str, Any], dispatch: Mapping[str, Any] | None, project: str) -> str:
    """The prompt one turn sends, in fixed order: the delivered context delta; saved history after a native
    connection update; the author's selected passage and unsaved draft; the request; queued requests; the
    explicit Work; the validated workspace view; the role's instructions; a child's typed return contract."""
    prompt = delivered
    if migration:
        prompt += _migration_history(records, ident)
    selection = source_selection
    if isinstance(selection, dict) and isinstance(selection.get("quote"), str) and selection["quote"].strip():
        prompt += ("\n\nAUTHOR'S SELECTED PASSAGE\n"
                   "This is the passage the author is pointing at within the connected source above. "
                   "Rendered wording may differ from TeX; obtain exact source before proposing an edit.\n"
                   + json.dumps({"anchor": selection.get("anchor", {}), "quote": selection["quote"]}, ensure_ascii=False))
    prompt += _draft_prompt(unsaved_draft)
    prompt += "\n\nAUTHOR'S CURRENT REQUEST\n" + text
    if queued:
        prompt += ("\n\nQUEUED AUTHOR REQUESTS INCLUDED IN THIS TURN\n"
                   + json.dumps(queued, ensure_ascii=False)
                   + "\nWhen a queued request is actually complete, use task_status with its ID, "
                     "status done, and evidence. Do not mark a queued request complete merely because it was included.")
    if work:
        prompt += "\n\nCURRENT PROJECT WORK\n" + work["prompt"]
    workspace_view = {key: value for key, value in workspace.items() if key != 'workflow_action'}
    if workspace_view:
        prompt += ("\n\nCURRENT WORKSPACE VIEW (validated against canonical structure)\n"
                   + json.dumps(workspace_view, ensure_ascii=False))
    if workspace.get('workflow_action'):
        selected_kind=(workspace['workflow_action'].get('reference') or {}).get('kind')
        wording=('The author selected this exact bounded research workflow Start. Use its native call '
                 if selected_kind=='research-workflow-start' else 'The author selected this exact continuation and retained output. Use its native call ')
        prompt += ('\n\nSELECTED WORKFLOW ACTION\n' + wording +
                   'through the project tools; current tool admission checks the action when invoked.\n'
                   + json.dumps(workspace['workflow_action'], ensure_ascii=False))
    prompt += _role_instructions(mode, framing, dispatch)
    if dispatch:
        from laplace.writing.dispatch_execution import _child_return_contract
        return_contract = _child_return_contract(root, project, ident, dispatch.get("dispatch_id"))
        if return_contract:
            prompt += ("\n\nWrite the packet's typed return through store_artifact at its declared return_path. "
                       "Pass publish_action itself as native tool arguments, authoring content only inside its payload. Publication_context is qualification metadata; do not merge project or other metadata into the call. The following current contract is generated from the canonical profile registry:\n"
                       + json.dumps(return_contract, ensure_ascii=False, separators=(",", ":")))
    return prompt


from laplace.manuscript import proposal_currentness, source_effects  # noqa: E402  (owner seams; cycle-safe, imported last)
