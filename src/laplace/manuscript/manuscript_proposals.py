"""Render and decide saved suggestions at their manuscript source locations."""
from __future__ import annotations

from laplace.writing import records as writing_records

import hashlib
import json
import difflib
from pathlib import Path
import uuid


# Disposable identity projections of existing owner records, never mutation bodies.
PROPOSAL_METADATA_SCHEMA = 'laplace.proposal-metadata/1'

class EditIdentity(dict):
    pass

class ProposalIdentity(dict):
    pass


def text_identity(edit, field):
    if isinstance(edit, EditIdentity): return edit[field + '_sha256']
    return hashlib.sha256(str(edit.get(field) or '').encode()).hexdigest()


def edit_metadata(edit):
    return {**{key:edit.get(key) for key in ('file','line_start','line_end','source_anchor') if key in edit},
            'edit_id':edit_id(edit), 'before_sha256':text_identity(edit,'before'),
            'after_sha256':text_identity(edit,'after'),
            'after_line_count': edit.get('after_line_count') if isinstance(edit, EditIdentity) else len(str(edit.get('after') or '').split('\n')),
            # IDs and revision pins only; retained prose stays in its exact carrier.
            'declaration_schema':'laplace.source-declarations/1',
            **{field:[{key:row[key] for key in ('id',pin) if key in row}
                      for row in edit.get(field) or [] if isinstance(row,dict)]
               for field,pin in (('develops','content_revision'),('evidence_refs','revision'))}}


def proposal_metadata(proposal):
    return {'schema_version':PROPOSAL_METADATA_SCHEMA,
            'content_sha256':writing_records.proposal_digest(proposal),'effect_sha256':writing_records.proposal_effect_digest(proposal),
            'edits':[edit_metadata(edit) for edit in proposal.get('edits') or []]}


def identity_proposal(value):
    from laplace.core.identity import require_schema_version
    require_schema_version(value,(PROPOSAL_METADATA_SCHEMA,),owner='Proposal metadata')
    import re
    if set(value)!={'schema_version','content_sha256','effect_sha256','edits'} or not isinstance(value.get('edits'),list):raise ValueError('Malformed proposal metadata')
    if any(not isinstance(value.get(key),str) or not re.fullmatch(r'sha256:[a-f0-9]{64}',value[key]) for key in ('content_sha256','effect_sha256')):raise ValueError('Malformed proposal metadata digests')
    for edit in value['edits']:
        if not isinstance(edit,dict) or not isinstance(edit.get('file'),str) or not isinstance(edit.get('edit_id'),str) or not re.fullmatch(r'EDIT-[a-f0-9]{24}',edit['edit_id']):raise ValueError('Malformed proposal edit identity')
        if any(type(edit.get(key)) is not int or edit[key]<1 for key in ('line_start','line_end')) or edit['line_end']<edit['line_start']:raise ValueError('Malformed proposal edit lines')
        if any(not isinstance(edit.get(key),str) or not re.fullmatch(r'[a-f0-9]{64}',edit[key]) for key in ('before_sha256','after_sha256')):raise ValueError('Malformed proposal edit hashes')
    return ProposalIdentity({**value,'edits':[EditIdentity(edit) for edit in value['edits']]})

def edit_id(edit: dict) -> str:
    if isinstance(edit, EditIdentity): return edit["edit_id"]
    value = {key: edit.get(key) for key in ("file", "line_start", "line_end", "before", "after")}
    return "EDIT-" + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def saved_proposals(turn: dict) -> dict:
    """All immutable versions, including a final reply not separately banked."""
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    versions = dict(turn.get("proposal_versions") or {})
    for proposal in (turn.get("pending_proposal"), (turn.get("reply") or {}).get("proposal")):
        if isinstance(proposal, dict) and not any(proposal==known for known in versions.values()):
            versions[writing_records.proposal_digest(proposal)] = proposal
    return versions


def select_version(turn: dict, version: str | None = None) -> dict:
    if not version:
        return turn
    versions=saved_proposals(turn)
    proposal=versions.get(version)
    if proposal is None:
        from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
        from laplace.writing import turn_jobs
        from laplace.writing import records as writing_records
        matches=[key for key,value in versions.items() if writing_records.proposal_digest(value)==version]
        if len(matches)>1:
            raise ValueError('This authored-content digest has multiple candidate input bases. Select the exact owner proposal_version.')
        if matches:
            version=matches[0];proposal=versions[version]
    if proposal is None:
        raise ValueError("This saved proposal version is unavailable. Refresh the proposal list.")
    # This is a selected view, never a fabricated terminal provider reply.
    # The scalar is not banked; the existing pending slot carries the selected
    # body while the actual original reply/carrier remains unchanged.
    selected = {**turn, "pending_proposal": proposal,'pending_proposal_version':version,
                '_selected_proposal_version':version}
    if isinstance(turn.get('reply'), dict):
        selected['reply'] = dict(turn['reply'])
    return selected


def original_proposal(turn: dict) -> dict:
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    final = (turn.get("reply") or {}).get("proposal")
    proposal=(turn.get("pending_proposal") or {}) if turn.get("_selected_proposal_version") else (final if isinstance(final, dict) else turn.get("pending_proposal") or {})
    version=proposal_version(turn)[0]
    # Unqualified legacy anchors remain history, never mutation authority. An
    # identical edit in another version can have a different file/EOF basis.
    anchors=(turn.get('proposal_anchors_by_version') or {}).get(version) or {}
    edits=[(EditIdentity if isinstance(edit,EditIdentity) else dict)({**edit,**({"source_anchor":anchors[edit_id(edit)]} if edit_id(edit) in anchors else {})}) for edit in proposal.get("edits") or []]
    return (ProposalIdentity if isinstance(proposal,ProposalIdentity) else dict)({**proposal,"edits":edits})


def proposal_version(turn: dict) -> tuple[str, bool]:
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    selected = turn.get('_selected_proposal_version')
    if selected:
        proposal = turn.get('pending_proposal') or {}
        return selected, bool(proposal.get('edits')) and selected in saved_proposals(turn)
    final = (turn.get("reply") or {}).get("proposal")
    proposal = final if isinstance(final, dict) else turn.get("pending_proposal") or {}
    version = ((turn.get('reply') or {}).get('proposal_instance_version') if isinstance(final,dict)
        else turn.get('pending_proposal_version')) or writing_records.proposal_digest(proposal)
    sealed = bool(proposal.get("edits")) and (isinstance(final, dict)
        or version in (turn.get("proposal_versions") or {}))
    return version, sealed


def decisions(turn: dict, version: str | None = None) -> dict:
    version=version or proposal_version(turn)[0]
    choices={row["edit_id"]: row for row in turn.get("proposal_decisions", [])
             if row.get("edit_id") and row.get('proposal_version')==version}
    # Whole and selective applies share the existing application owner. Project
    # its exact consumed component IDs; never infer completion from text/effects.
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    members={edit_id(edit) for edit in (saved_proposals(turn).get(version) or {}).get('edits') or []}
    for app in source_effects.applications(turn):
        if not app.get('complete') or app.get('candidate_version')!=version:continue
        for index,ident in enumerate(app.get('candidate_edit_ids') or []):
            if ident in members:choices.setdefault(ident,{'edit_id':ident,'proposal_version':version,
                'decision':'accepted','application_id':app['id'],'application_edit_index':index,
                'derived_from_application':True})
    return choices


def consumed_alternatives(turn:dict,version:str,records:dict) -> dict:
    """Recorded source consumption, not inferred semantic supersession.

    An accepted overlapping version consumes an older observation of that
    occurrence. Undo cannot turn its retained alternatives into pending work.
    A genuinely later source/context observation can ground a fresh candidate.
    """
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    versions=saved_proposals(turn);basis=(turn.get('proposal_bases') or {}).get(version) or {}
    orders=records.get('orders') or {}
    observed=max([orders.get(basis.get('turn_basis_record_id'),0)]+[
        orders.get(read.get('id'),0) for read in (basis.get('tool_reads') or {}).values()
        if read.get('operation')=='source'])
    out={}
    for app in source_effects.applications(turn):
        other_version=app.get('candidate_version')
        if not app.get('complete') or other_version==version or not other_version or orders.get(app.get('id'),0)<=observed:continue
        other=versions.get(other_version) or {}
        used=set(app.get('candidate_edit_ids') or [])
        for original in (versions.get(version) or {}).get('edits') or []:
            left=original.get('source_anchor') or {}
            for accepted in other.get('edits') or []:
                right=accepted.get('source_anchor') or {}
                if (edit_id(accepted) in used and original.get('file')==accepted.get('file')
                    and left.get('sha256') and left.get('sha256')==right.get('sha256')
                    and int(original['line_start'])<=int(accepted['line_end'])
                    and int(accepted['line_start'])<=int(original['line_end'])):
                    out[edit_id(original)]={'application_id':app['id'],'proposal_version':other_version,
                        'relation':'consumed-overlapping-source-basis'}
    return out


def _turn(root: Path, project: str, ident: str, version=None, *, application_id=None) -> dict:
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    from laplace.manuscript.proposal_navigation import selected_records
    scoped=selected_records(root,project,ident,version,application_id=application_id)
    turn = scoped["turns"].get(ident)
    if not turn or turn.get("project") != project:
        raise ValueError("This suggestion does not belong to the selected project.")
    return {**turn,'_record_scope':scoped}


def supersede(root: Path, project: str, payload: dict, *, by: str = "eigen:session",
              recorded_in_turn: str | None = None) -> dict:
    """Retire one complete old proposal through an exact later application.

    This records lineage only.  It never reads, replaces or blesses current
    manuscript bytes, and it retains every earlier decision/application row.
    """
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    target_id = str(payload.get("target_turn_id") or "")
    application_id = str(payload.get("application_id") or "")
    reason = str(payload.get("reason") or "").strip()
    if not target_id or not application_id or not reason:
        raise ValueError("proposal_supersede requires target_turn_id, application_id and reason")
    if len(reason.encode("utf-8")) > 2000:
        raise ValueError("proposal_supersede reason is limited to 2000 bytes")
    with writing_records.proposal_write_lock(root):
        from laplace.manuscript.proposal_navigation import selected_records
        records = selected_records(root,project,target_id,application_id=application_id)
        target = records["turns"].get(target_id)
        if not target or target.get("project") != project:
            raise ValueError("The target proposal does not belong to the selected project.")
        version, sealed = proposal_version(target)
        proposal = original_proposal(target)
        if not sealed or not proposal.get("edits"):
            raise ValueError("The target turn has no complete saved proposal to supersede.")
        found = None
        for other in records["turns"].values():
            if (other.get("id") == target_id or other.get("project") != project
                    or not proposal_currentness._same_application_edition(target, other)):
                continue
            for application in source_effects.applications(other):
                if application.get("id") == application_id and application.get("complete"):
                    found = (other, application)
                    break
            if found:
                break
        if found is None:
            raise ValueError("application_id must name one complete later-turn application in the same project edition")
        other, application = found
        if str(application.get("ts") or "") <= str(target.get("ts") or ""):
            raise ValueError("The superseding application must be later than the target proposal turn.")
        applied = source_effects.applied_edits(other, application)
        matches, used = [], set()
        for original in proposal["edits"]:
            candidates = [(index, edit) for index, edit in enumerate(applied) if index not in used
                          and proposal_currentness._same_edit_occurrence(original, edit, same_after=False)]
            if len(candidates) != 1:
                raise ValueError("The application does not cover every proposal edit at one exact recorded occurrence.")
            index, replacement = candidates[0]
            used.add(index)
            matches.append((original, replacement,
                            "exact" if str(original.get("after") or "") == str(replacement.get("after") or "")
                            else "refined"))
        prior = decisions(target)
        if all((prior.get(edit_id(original)) or {}).get("decision") == "superseded"
               and (prior.get(edit_id(original)) or {}).get("application_id") == application_id
               for original, _replacement, _kind in matches):
            return {"ok": True, "status": "SUPERSEDED", "reused": True,
                    "target_turn_id": target_id, "application_id": application_id,
                    "application_turn_id": other.get("id"), "proposal_version": version,
                    "superseded_edit_ids": [edit_id(original) for original, _r, _k in matches],
                    "exact_effects": sum(kind == "exact" for _o, _r, kind in matches),
                    "refined_effects": sum(kind == "refined" for _o, _r, kind in matches),
                    "remaining": 0, "effects": ["history"]}
        rows = []
        for original, _replacement, kind in matches:
            row = {"record": "writing-proposal-decision", "id": "DECISION-" + uuid.uuid4().hex,
                   "project": project, "turn_id": target_id, "edit_id": edit_id(original),
                   "decision": "superseded", "resolution": "supersede",
                   "proposal_version": version, "application_id": application_id,
                   "superseding_turn_id": other.get("id"), "supersession_kind": kind,
                   "reason": reason, "by": by}
            if recorded_in_turn:
                row["recorded_in_turn"] = recorded_in_turn
            writing_records.bank(root, row)
            rows.append(row)
        return {"ok": True, "status": "SUPERSEDED", "reused": False,
                "target_turn_id": target_id, "application_id": application_id,
                "application_turn_id": other.get("id"), "proposal_version": version,
                "decision_ids": [row["id"] for row in rows],
                "superseded_edit_ids": [row["edit_id"] for row in rows],
                "exact_effects": sum(kind == "exact" for _o, _r, kind in matches),
                "refined_effects": sum(kind == "refined" for _o, _r, kind in matches),
                "remaining": 0, "effects": ["history"],
                "next_read": {"operation": "author_history",
                              "payload": {"view": "record", "id": rows[-1]["id"]}}}


def _current_review(original:dict,target:Path, *, current_edit:dict | None = None,
                    mutation_available:bool=True) -> dict:
    """Only a proven source occurrence can receive current mutation authority."""
    raw=target.read_text(encoding="utf-8")
    if current_edit is None:
        return {"current_mapping":"unproven-historical-location","resolution_available":False,
                'target_proof':{'status':'UNPROVEN'},
                "resolution_note":"The old offsets do not prove a current target. Keep the current source or request a fresh source-centered proposal; replacement and merge are unavailable."}
    lines=raw.split("\n");before=str(original.get("before") or "")
    old=before.split("\n")
    placement = current_edit or original
    start=max(0,int(placement.get("line_start",1))-1)
    end=min(len(lines),max(start+1,int(placement.get("line_end",start+1))))
    if start>=len(lines):return {}
    mapping="proven-current-source-occurrence"
    current="\n".join(lines[start:end])
    source_sha=hashlib.sha256(raw.encode()).hexdigest()
    token=hashlib.sha256(json.dumps({"edit":edit_id(original),"source":source_sha,
        "start":start+1,"end":end,"before":current},sort_keys=True).encode()).hexdigest()
    current_anchor={'file':original['file'],'line_start':start+1,'line_end':end}
    return {"current_before":current,"current_anchor":current_anchor,
            **({'review_token':token} if mutation_available else {}),
            'resolution_available':mutation_available,
            'target_proof':{'status':'CURRENT','anchor':current_anchor,'source_text_sha256':'sha256:'+source_sha},
            "reviewed_current_sha256":source_sha,"current_mapping":mapping,
            "resolution_note":"Review the current passage below before replacing it; the original proposal was written against an earlier version.",
            "current_diff":"\n".join(difflib.unified_diff(old,current.split("\n"),
                fromfile="Original proposal basis",tofile="Current manuscript",lineterm=""))}


def preview(root: Path, project: str, turn_id: str, saved_version: str | None = None, *, records=None, render=True, selected_edit="") -> dict:
    from laplace.manuscript import manuscript_source, manuscript_figure_preview, proposal_preflight, walk
    from laplace.manuscript import projection_viewer
    from laplace.manuscript import proposal_basis
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    with turn_jobs._LOCK:
        if records is None:
            from laplace.manuscript.proposal_navigation import selected_records
            records=selected_records(root,project,turn_id,saved_version)
        turn = records["turns"].get(turn_id)
        if not turn or turn.get("project") != project:
            raise ValueError("This suggestion does not belong to the selected project.")
        turn = select_version(turn, saved_version)
        version, sealed = proposal_version(turn)
        proposal = original_proposal(turn)
        if isinstance(proposal,ProposalIdentity) or any(isinstance(edit,EditIdentity) or not isinstance(edit.get("before"),str) or not isinstance(edit.get("after"),str) for edit in proposal.get("edits") or []):
            raise ValueError("Identity-only proposal metadata cannot be rendered or decided; read the exact proposal body.")
        applied_elsewhere=proposal_currentness.applications_for_effect(records,turn,proposal)
        terminal_view=proposal_currentness.proposal_view(turn,records=records)
        terminal_state=terminal_view.get("proposal_state")
        terminal_application=next((row for row in reversed(source_effects.applications(turn))
            if row.get("complete") and row.get('candidate_version')==version
            and set(row.get('candidate_edit_ids') or [])=={edit_id(edit) for edit in proposal.get('edits') or []}),None)
        terminal_edits=(source_effects.applied_edits(turn,terminal_application)
                        if terminal_application else [])
        fulfilled_edits=proposal_currentness.applications_for_edits(records,turn,proposal)
        refined_edits=proposal_currentness.refinements_for_edits(records,turn,proposal)
        consumed=consumed_alternatives(turn,version,records)
        job = turn_jobs._JOBS.get(turn_id)
        active = bool(job and not job["done"])
    source = manuscript_source.resolve(project, repo_root=root)
    if not source.get("root") or not source.get("manuscript_dir"):
        raise ValueError("The selected manuscript is unavailable.")
    manuscript = (root / source["manuscript_dir"]).resolve()
    root_tex = (root / source["root"]).resolve()
    files = set(manuscript_source.traversal(root_tex, repo_root=root).get("files", []))
    macros = walk.preamble_macros(root_tex)
    environments = manuscript_figure_preview.declared_environments(root_tex, root)
    presentation = manuscript_figure_preview.declared_environment_presentation(root_tex, root)
    # One proposal may contain several edits in the same scientific region.
    # Read its canonical structure/network once so the preview cannot mix
    # revisions and does not rebuild the whole book for every edit.
    from laplace.research import concepts as concepts_surface
    from laplace.manuscript import project_structure
    try:
        shared_structure = project_structure.state(project, root)
    except ValueError:
        shared_structure = None
    concept_net = concepts_surface._network(project, root)
    concept_snapshot = ((concept_net, *concepts_surface._relations(project, root, concept_net))
                        if concept_net else None)
    concept_cache = {}
    heading_spans_by_file = {}
    prior = decisions(turn)
    # A RECORDED comparison, not a decidable one: the same condition the walk branches on
    # (walk.mjs showProposal -> showRecordedProposal), decided once, server-side, so the
    # answer carries what the view it is for actually renders.
    recorded_comparison = (bool(source.get("read_only"))
                           or bool(selected_edit and (prior.get(selected_edit) or {}).get('decision')=='resolved-into-successor')
                           or terminal_state in {"applied", "rejected", "applied-elsewhere",
                                                 "superseded", "fulfilled","consumed-alternative","resolved-into-successor"})
    immutable=saved_proposals(turn).get(version) or {}
    validation_basis=(proposal_currentness._proposal_validation_basis(root,turn,version,immutable,source=source,records=records)
                      if not recorded_comparison else {'currentness':'NOT_APPLICABLE','reason':None})
    rows = [];application_files={};application_states={}
    for edit_index,original in enumerate(proposal.get("edits") or []):
        ident = edit_id(original)
        if selected_edit and ident != selected_edit:continue
        row = {**original, "edit_id": ident, "status": "pending"}
        decision = prior.get(ident)
        if decision:
            row["status"] = decision["decision"]
            if decision['decision']=='resolved-into-successor':
                from laplace.manuscript.proposal_navigation import handle
                successor=decision['successor_ref']
                row.update(successor_ref=successor,resolution_application_id=decision['resolution_application_id'],
                    successor_read=handle(project,{'id':successor['id'],'proposal_version':successor['version'],'view':'preview'}),
                    resolution_note='This exact edit was resolved in a later revision. The original proposed text was not applied or scientifically accepted.')
            application=next((item for item in source_effects.applications(turn)
                              if item.get("id")==decision.get("application_id")),None)
            if application is None and decision.get("application_id"):
                application=next((item for other in records["turns"].values()
                    for item in source_effects.applications(other)
                    if item.get("id")==decision.get("application_id")),None)
            applied=source_effects.applied_edits(turn,application) if application else []
            index=decision.get('application_edit_index')
            accepted=(applied[index] if isinstance(index,int) and 0<=index<len(applied) else
                next((item for item in applied if item.get("file")==original.get("file")
                     and item.get("before")==original.get("before")),applied[0] if applied else None))
            if accepted:row.update(accepted,application_id=application.get("id"),
                application_turn_id=decision.get("superseding_turn_id") or turn_id)
        elif ident in consumed:
            row.update(status='consumed-alternative',consumption=consumed[ident],
                resolution_note='An accepted overlapping version consumed this source basis. This version is retained history; request a fresh proposal from current source.')
        elif ident in fulfilled_edits:
            candidate=fulfilled_edits[ident][-1]
            row.update(historical_application_matches=fulfilled_edits[ident],
                       resolution_note='A historical application matches this source effect. It does not accept this candidate or prove current source. Inspect it before any explicit supersession.',
                       next_decision={'decision':'supersede','application_id':candidate.get('id')})
        elif ident in refined_edits:
            candidate=refined_edits[ident][-1]
            row.update(refinement_candidates=refined_edits[ident],
                       resolution_note="A historical application has a related preimage. It does not accept this candidate or prove current source. Inspect it before any explicit supersession.",
                       next_decision={"decision":"supersede","application_id":candidate.get("id")})
        elif terminal_state=="applied" and terminal_application:
            if edit_index<len(terminal_edits):row.update(terminal_edits[edit_index])
            row.update(status="accepted",application_id=terminal_application.get("id"),
                       application_turn_id=turn_id)
        elif terminal_state=="rejected":
            row["status"]="rejected"
        if not decision:
            from laplace.manuscript.reconciliation import pending_successors
            recovery=pending_successors(root,project,turn_id,version,ident)
            if recovery:
                row['pending_successors']=recovery[:4]
                if len(recovery)==1:row.update(recovery[0])
                row['resolution_note']='A resolved successor is saved. Inspect it to finish only this predecessor disposition; the original edit remains unresolved until that record is saved.'
        target = proposal_preflight._resolve(root, manuscript, str(original.get("file") or ""))
        target_identity=(target.relative_to(root).as_posix() if target and target.is_relative_to(root)
                         else str(target) if target else str(original.get('file') or ''))
        expected=turn.get("document") or {}
        edition_changed=any(expected.get(key) is not None and expected[key]!=source.get(key)
                            for key in ("root","manuscript_dir","edition"))
        terminal=row["status"] in {"accepted","rejected","superseded","applied_elsewhere","refined_elsewhere","consumed-alternative","resolved-into-successor"}
        if not terminal and source.get('read_only'):
            row.update(status='conflict',error='This selected manuscript is read-only. The suggestion can be inspected here; applying it requires an editable working copy.')
        elif not terminal and (target is None or target_identity not in files or edition_changed):
            row.update(status="conflict", error="This suggestion belongs to a different manuscript version or a file no longer included.")
        elif not terminal:
            # Addressing and consumed input currentness are separate proofs.
            # Neither a current-source read nor human review renews old science.
            review_turn = {**turn, "selection": {"files": [str(original["file"])]},
                           "dependencies": {}, "tool_reads": {}}
            checked = proposal_preflight.preflight(root, project, review_turn,
                {"answer": proposal.get("answer", ""), "edits": [
                    {key:value for key,value in original.items() if key not in {"develops","evidence_refs"}}]},
                relocate_unanchored=False)
            proven=proposal_preflight.proven_current_span(target.read_text(encoding='utf-8'),original,
                turn=turn,root=root,path=target)
            if proven is None or validation_basis['currentness']!='CURRENT':
                checked['valid']=False
            if checked["valid"]:
                row.update(checked["proposal"]["edits"][0])
                row.update({key: value for key, value in
                            _current_review(original, target, current_edit=row).items()
                            if key in {"review_token", "current_before", "current_anchor",
                                       "current_mapping", "reviewed_current_sha256",'target_proof','resolution_available'}})
            else:
                row.update(status="conflict", error="The original passage has changed or its source scope is unproven. Keep the current source or request a fresh source-centered proposal.")
                physical=({**original,'line_start':proven[0],'line_end':proven[1]} if proven else None)
                row.update(_current_review(original,target,current_edit=physical,mutation_available=False))
                if validation_basis['currentness']!='CURRENT':row['error']=validation_basis['reason']
        row["anchor"] = {key: row.get(key) for key in ("file", "line_start", "line_end")}
        row["basis"]=proposal_basis.assess(
            root, project, {**row, **row.get("current_anchor", {})},
            structure=shared_structure, concept_cache=concept_cache,
            concept_network_snapshot=concept_snapshot, selected_source=source,
            heading_spans_by_file=heading_spans_by_file)
        if row['status']=='pending' and row['basis'].get('errors'):
            row.update(status='conflict',error='The declared scientific basis changed: '+'; '.join(row['basis']['errors']))
            row.pop('review_token',None);row['resolution_available']=False
        row['candidate_id']={'turn_id':turn_id,'proposal_version':version,'edit_id':ident}
        row['basis_currentness']=('STALE' if row['basis'].get('errors') and validation_basis['currentness']=='CURRENT'
                                 else validation_basis['currentness'])
        row['basis_reason']=(row.get('error') if row['basis'].get('errors') else validation_basis.get('reason'))
        # Scoped progress (laplace.core.scoped): what applying it leaves to review, never a precondition of it.
        row['review_obligations']=validation_basis.get('review_obligations') or []
        row['semantic_currentness']=validation_basis.get('semantic_currentness') or 'NOT_ASSERTED'
        row['acceptance_unit']={'kind':'edit','edit_ids':[ident]}
        row['allowed_actions']=(['accept','merge','replace-current','reject','keep-current']
            if row['status']=='pending' and sealed and row.get('review_token') and not source.get('read_only')
            else ['supersede'] if row['status']=='refined_elsewhere'
            else ['reject','keep-current'] if row['status']=='conflict' and sealed else [])
        if row.get('next_decision') and sealed and not decision:
            row['allowed_actions'].append('supersede')
        if sealed and not source.get('read_only') and not terminal:
            from laplace.manuscript.reconciliation import action
            row['resolution_action']=action(project,'prepare-resolution',{
                'turn_id':turn_id,'proposal_version':version,'edit_id':ident})
            row['target_required']=(row.get('target_proof') or {}).get('status')!='CURRENT'
        row['lifecycle']=('actionable' if row['status']=='pending' and 'accept' in row['allowed_actions']
            else 'blocked' if row['status'] in {'pending','conflict','refined_elsewhere'} else 'retained-history')
        app_id=row.get('application_id') or (row.get('consumption') or {}).get('application_id')
        if app_id:
            if app_id not in application_states:
                app=next((app for candidate_turn in records['turns'].values()
                    for app in source_effects.applications(candidate_turn) if app.get('id')==app_id),None)
                application_states[app_id]=(source_effects.application_source_state(root,app,file_hashes=application_files) if app else 'UNKNOWN')
            row['application_source_state']=application_states[app_id]
        def blocks(text: str) -> list:
            result = walk.blocks_for(str(text), file_rel=str(row["file"]),
                repo_file=target_identity,
                md=manuscript, corpus=project, dir_param="",
                para_spans=projection_viewer.parse_paragraphs(str(text)), known_macros=macros,
                declared_envs=environments, declared_presentation=presentation)
            for block in result:
                block["suggestion"] = True
            return result
        # THE RAIL IS CURRENT + PROPOSED.  The live rail renders the manuscript's own
        # blocks as "current" (they are moved into the pane, not re-rendered) and the
        # proposal as "proposed"; `before_blocks` was a THIRD rendering of the same
        # passage, 24,897 bytes of a 62,854-byte section preview, and the only pane that
        # read it -- "Original basis" -- had no way to be opened for a decidable
        # suggestion.  It is delivered only for the RECORDED comparison, which is the
        # exact history reference the rail now points at instead of carrying: that view
        # is read-only, both of its sides are historical, and neither is on the canvas.
        # The basis of a conflicted suggestion stays reachable through `current_diff`
        # (:154) and through the recorded comparison for the same turn and edit.
        if render and recorded_comparison:
            row["before_blocks"] = blocks(str(row.get("before") or ""))
        if render:
            row["after_blocks"] = blocks(str(row.get("after") or ""))
            if "current_before" in row:row["current_blocks"]=blocks(row["current_before"])
        rows.append(row)
    # The identity this read publishes, keyed by home, so the reviewer sends back a token it
    # READ rather than the bare `proposal_version` string whose home nothing names
    # (WRITING-CONSOLIDATION-W1; `grammar.HOME_KINDS["proposal"].closes`). The value is the
    # same `version` this read already returns --- one value, now with its home on it.
    from laplace.core import identity_doors as _idd
    return {"project": project, "turn_id": turn_id, "answer": proposal.get("answer", ""),
            "identities": _idd.identities(
                ("proposal", "%s::%s" % (project, turn_id), version)),
            "proposal_version": version, "reviewable": sealed, "turn_active": active,
            'proposal_content_sha256':writing_records.proposal_digest(immutable),
            "proposal_state":terminal_state,"read_only":bool(source.get("read_only")) or terminal_state=='resolved-into-successor'
                or bool(selected_edit and rows and rows[0]['status']=='resolved-into-successor'),
            "validation_basis":validation_basis,
            "edits": rows, "historical_application_matches": applied_elsewhere,
            "remaining": sum(row["status"] in {"pending", "conflict", "refined_elsewhere"} for row in rows)}


def decide(root: Path, project: str, payload: dict, *, actor=None) -> dict:
    """Publication and selected-source attribution settle before optional mirrors."""
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    from laplace.core import identity_doors
    identity_doors.admit_expected(payload, "proposal_decision")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    if payload.get('decision') in {'prepare-resolution','preview-resolution','apply-resolution','apply-candidate','finish-resolution-record'}:
        from laplace.manuscript import reconciliation
        return reconciliation.decide(root,project,payload,actor=actor)
    changes = []
    with writing_records.proposal_write_lock(root):
        if payload.get('decision') in {'accept', 'replace-current', 'merge'}:
            turn = select_version(_turn(root, project, str(payload.get('turn_id') or ''),payload.get('proposal_version')),
                                  payload.get('proposal_version'))
            with source_application.proposal_source_scope(root, project, original_proposal(turn)):
                result = _decide_locked(root, project, payload, source_changes=changes)
        else:
            result = _decide_locked(root, project, payload, source_changes=changes)
    if changes:
        source_effects.finish_source_changes(root, project, result['application'], changes)
    if isinstance((result.get('application') or {}).get('source_effect'), dict):
        result['source_effect'] = result['application']['source_effect']
    return result


def _application_result(root, project, turn_id, version, application, *, decision=None, warning=None):
    """Known effects survive an optional comparison read; no fresh rows are guessed."""
    try:
        result = preview(root, project, turn_id, version)
    except (OSError, ValueError) as exc:
        result = {'project':project, 'turn_id':turn_id, 'proposal_version':version,
                  'reviewable':False, 'read_only':True, 'preview_unavailable':True}
        message = ('Application recorded' if application.get('id') and application.get('complete')
                   else 'Source outcome retained')
        warning = (warning + ' ' if warning else '') + message + '; comparison unavailable: ' + str(exc) + '. Inspect exact source/application receipts; do not repeat the effect.'
    result['application'] = application
    if decision is not None:
        result['decision'] = decision
    if warning:
        result['warning'] = warning
        if application.get('id') and application.get('complete'):
            result['reviewable'] = False
            result['application_maintenance_unproved'] = True
    return result


def _decide_locked(root: Path, project: str, payload: dict, *, source_changes: list) -> dict:
    from laplace.manuscript import proposal_currentness, source_application, source_effects  # the owners (family 1)
    from laplace.writing import turn_jobs
    from laplace.writing import records as writing_records
    turn_id, ident = str(payload.get("turn_id") or ""), str(payload.get("edit_id") or "")
    action = payload.get("decision")
    if action not in {"accept", "reject", "keep-current", "replace-current", "merge", "supersede"}:
        raise ValueError("Choose accept, reject, keep-current, replace-current, merge or supersede for this suggestion.")
    turn = _turn(root, project, turn_id,payload.get('proposal_version'),application_id=payload.get('application_id') if action=='supersede' else None)
    turn = select_version(turn, payload.get("proposal_version"))
    version, sealed = proposal_version(turn)
    if not payload.get('proposal_version') and not payload.get('expected'):
        raise ValueError('Refresh the saved suggestion and supply its exact proposal_version before deciding it.')
    records=turn['_record_scope']
    canonical=proposal_currentness.proposal_view(turn,records=records)
    # Approval selects an opaque sealed instance returned by the owner.
    # Authored content hashes and later session reads cannot renew its basis.
    if payload.get("expected"):
        from laplace.core import identity_doors
        identity_doors.gate(
            "proposal_decision", supplied=payload,
            homes=[("proposal", "%s::%s" % (project, turn_id), version)],
            said="this suggestion changed since you read it")
    if canonical.get("proposal_state") in {"applied","rejected","consumed-alternative"}:
        application=next((row for row in reversed(source_effects.applications(turn))
                          if row.get("complete") and row.get('candidate_version')==version),None)
        return {**preview(root,project,turn_id,version),"reused":True,
                "terminal_state":canonical["proposal_state"],"application":application}
    reviewed_version = payload.get("proposal_version")
    old = decisions(turn).get(ident)
    if old:
        if reviewed_version and old.get("proposal_version") and reviewed_version != old["proposal_version"]:
            raise ValueError("This edit was decided from a different saved version. Refresh the suggestion to inspect its decision.")
        application = next((row for row in source_effects.applications(turn)
                            if row.get("id") == old.get("application_id")), None)
        return {**preview(root, project, turn_id,version), "reused": True, "decision": old,
                "application": application}
    job = turn_jobs._JOBS.get(turn_id)
    active = bool(job and not job["done"])
    if not sealed:
        raise ValueError("This suggestion has no complete saved version to review yet.")
    if active and not reviewed_version:
        raise ValueError("Refresh the saved suggestion before deciding it while the session continues.")
    if reviewed_version and reviewed_version != version:
        raise ValueError("The saved suggestion changed after you opened it. Refresh the suggestion and review its current version.")
    original = next((edit for edit in original_proposal(turn).get("edits") or [] if edit_id(edit) == ident), None)
    if original is None:
        raise ValueError("This suggestion is no longer available.")
    if action=="supersede":
        application_id=str(payload.get("application_id") or "")
        records=turn['_record_scope'];found=None
        for other in records["turns"].values():
            if other.get("project")!=project or not proposal_currentness._same_application_edition(turn,other):continue
            for candidate in source_effects.applications(other):
                if candidate.get("id")==application_id and candidate.get("complete"):
                    found=(other,candidate);break
            if found:break
        if not found:raise ValueError("supersede requires one exact complete application in this project edition")
        other,candidate=found;applied=source_effects.applied_edits(other,candidate)
        replacement=next((edit for edit in applied
                          if proposal_currentness._same_edit_occurrence(
                              original,edit,same_after=False)),None)
        if replacement is None:raise ValueError("application does not refine this exact proposal preimage")
        record={"record":"writing-proposal-decision","id":"DECISION-"+uuid.uuid4().hex,
            "project":project,"turn_id":turn_id,"edit_id":ident,"decision":"superseded",
            "resolution":"supersede","proposal_version":version,"application_id":application_id,
            "superseding_turn_id":other.get("id"),"by":"author"}
        writing_records.bank(root,record)
        return {**preview(root,project,turn_id,version),"decision":record,"application":candidate}
    application = None
    if action in {"accept", "replace-current", "merge"}:
        reviewed=preview(root,project,turn_id,version,records=records)
        row = next(row for row in reviewed["edits"] if row["edit_id"] == ident)
        if action not in row['allowed_actions']:
            if reviewed['validation_basis']['currentness'] not in {'CURRENT','NOT_APPLICABLE'}:
                raise proposal_currentness.ProposalBasisRefused(reviewed['validation_basis'])
            raise ValueError(row.get('error') or 'This retained candidate has no current mutation authority.')
        normalized = {key: row[key] for key in ("file", "line_start", "line_end", "before", "after", "reason", "develops", "evidence_refs","source_anchor") if key in row}
        if action in {"replace-current", "merge"}:
            if not row.get("review_token") or payload.get("review_token")!=row["review_token"]:
                raise ValueError("The current passage changed after you opened it. Review the updated comparison before saving.")
            normalized.update(row["current_anchor"],before=row["current_before"])
            if action=="merge":
                merged=payload.get("merged_after")
                if not isinstance(merged,str) or len(merged.encode())>2_000_000:
                    raise ValueError("A merged replacement must be source text smaller than 2 MB.")
                normalized["after"]=merged
        proposal = {"answer": "Accepted in the manuscript", "edits": [normalized]}
        application = source_application._apply_proposal_locked(root,
            {"project": project, "turn_id": turn_id}, proposal_override=proposal,
            allow_multiple=True, allow_active=active, human_reviewed=True,
            application_origin="author-rewrite" if action=='merge' else "manuscript-review",
            candidate_version=version,candidate_edit_ids=[ident], source_changes=source_changes,records_scope=records)
        if application.get('application_tracking', {}).get('status') == 'UNPROVED':
            # Source feedback can prove a landed effect without a parent WA.
            # Do not bank acceptance or sibling transformations from that
            # unrecorded object, or describe the source as preserved unchanged.
            return {**_application_result(root, project, turn_id, version, application, warning=application['warning']), 'reviewable':False,
                    'application':application, 'source_applied':application.get('source_applied', False),
                    'source_effect_retained':application.get('source_effect_retained', False),
                    'application_tracking':application['application_tracking']}
        if not application.get("complete"):
            return {**_application_result(root, project, turn_id, version, application,
                    warning='The source change did not complete. Inspect its exact rewrite and rollback receipts before another action.'), 'reviewable':False}
        # Known accepted edits can move the other suggestions. Re-anchor
        # only exact untouched spans using that known source transformation.
        try:
            from laplace.manuscript import manuscript_source, proposal_preflight
            source=manuscript_source.resolve(project,repo_root=root)
            manuscript=(root/source['manuscript_dir']).resolve()
            for other in reviewed['edits']:
                if other['edit_id']==ident or other['status']!='pending':continue
                if other['file']!=normalized['file']:continue
                lo,hi=other['line_start'],other['line_end']
                if normalized['line_start']<=hi and lo<=normalized['line_end']:continue
                delta=(normalized['after'].count('\n')-normalized['before'].count('\n')) if normalized['line_end']<lo else 0
                lo+=delta;hi+=delta
                path=proposal_preflight._resolve(root,manuscript,other['file'])
                if not path:continue
                raw=path.read_text();lines=raw.split('\n')
                if '\n'.join(lines[lo-1:hi])!=other['before']:continue
                writing_records.bank(root,{"record":"writing-proposal-anchor","id":"ANCHOR-"+uuid.uuid4().hex,
                    "project":project,"turn_id":turn_id,"edit_id":other['edit_id'],
                    "source_anchor":proposal_preflight.source_anchor(raw,lo,hi),"caused_by":application['id'],
                    "proposal_version":version})
        except (OSError, ValueError) as exc:
            return _application_result(root, project, turn_id, version, application,
                warning='Application recorded; sibling metadata is unavailable: '+str(exc)+'. Inspect exact receipts; do not repeat the effect.')
    record = {"record": "writing-proposal-decision", "id": "DECISION-" + uuid.uuid4().hex,
              "project": project, "turn_id": turn_id, "edit_id": ident,
              "decision": "accepted" if action in {"accept","replace-current","merge"} else "rejected",
              "resolution":action,"review_token":payload.get("review_token"),
              "proposal_version":version,
              "application_id": application.get("id") if application else None,
              "by": "author"}
    try:
        writing_records.bank(root, record)
    except (OSError, ValueError) as exc:
        if not application or not application.get('complete'):
            raise
        return _application_result(root, project, turn_id, version, application,
            warning='Application recorded; decision metadata is unproved: '+str(exc)+'. Inspect exact receipts; do not repeat the effect.')
    if application:
        return _application_result(root, project, turn_id, version, application, decision=record)
    return {**preview(root, project, turn_id,version), "decision": record, "application": application}
