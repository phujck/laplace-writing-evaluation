"""NATIVE SOURCE ADAPTERS (S1 B8): the long manuscript-source branches of writing.operations._execute_source.

Each is the original branch body, unchanged, called once from its dispatch branch after the one
admission in writing.operations._admit_operation; they return the owner result or raise its error.

  read_source        `source`: exact current bytes of the selection, excerpts and selection identity.
  build              `build` / `build_status`: a build job, a derived or publication-edition build target
                     (or that edition's preparation), or the selected source.
  propose_revision   `propose_revision`: preflight, then the one sealed writing-proposal row.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from laplace.writing import records as writing_records


def read_source(root: Path, project: str, payload: dict, turn_id: str | None) -> dict:
    from laplace.pipeline import authoring
    # An ordinary in-turn source read without an explicit file means the
    # source scope already selected for this turn.  It must expose its
    # exact per-file expected_source_digest, rather than forcing a writer
    # to discover a hashing convention through a shell command.
    if not payload.get("files") and turn_id:
        turn = writing_records.fold_records(root).get("turns", {}).get(turn_id) or {}
        selection = turn.get("selection") if isinstance(turn.get("selection"), dict) else {}
        if selection.get("files"):
            payload = {**selection, **payload}
    selection={key:value for key,value in payload.items() if key!="include_numbered_text"}
    result=authoring.inspect(project, selection=selection, repo_root=root, context_id="")
    # Exact raw text already carries its starting/ending line addresses.
    # Numbered text is useful when explicitly requested, but repeating both
    # copies by default doubles every scientific source read.
    if not payload.get("include_numbered_text",False):
        for source in result.get("sources") or []:
            source.pop("numbered_text",None)
    excerpts=[]
    for boundary in result.get("boundaries") or []:
        raw=str(boundary.get("text") or "")
        text,side=authoring._boundary_text(boundary,result.get("sources") or [])
        start=max(0,len(raw)-len(text)) if side=="before" else 0
        excerpts.append({"file":boundary.get("file"),"order":boundary.get("order"),
            "parent":boundary.get("parent"),"include_line":boundary.get("include_line"),
            "line_start":raw.count("\n",0,start)+1,
            "line_end":raw.count("\n",0,start+len(text))+1,
            "text":text,"character_start":start,"character_end":start+len(text),
            "excerpt":True,"side":side,
            "note":"Context excerpt only; read this file through source before editing it.",
            "read_more":{"operation":"source","payload":{"files":[boundary.get("file")]}}})
    result["boundaries"]=excerpts
    from laplace.manuscript import manuscript_source
    result["selection_identity"] = manuscript_source.selection_identity(result.get("document") or manuscript_source.resolve(project, root), project)
    result["source_format"]="raw-and-numbered" if payload.get("include_numbered_text",False) else "raw"
    return result


def build(root: Path, project: str, operation: str, payload: dict) -> dict:
    from laplace.manuscript import manuscript_source, projection_viewer
    from laplace.manuscript import build_jobs
    admitted = build_jobs.admit(payload, project, read=operation=='build_status')
    if admitted['operation'] == 'job':
        job=admitted['build_job']
        return build_jobs.status(job,project,root) if operation=='build_status' else build_jobs.cancel(job,project,root)
    if admitted['operation'] == 'prepare':
        from laplace.manuscript import publication_editions
        return publication_editions.prepare(project,payload,root)
    if admitted['operation'] == 'target':
        from laplace.manuscript import build_targets
        target = admitted['build_target']
        if target.get('kind')=='candidate':
            if operation=='build_status':return build_targets.candidate_status(project,target,root)
            from laplace.manuscript import document_templates
            build_targets.stage_candidate(project,target['candidate_ref'],document_templates.candidate(project,target['candidate_ref'],root)['proposal'],root)
        build_targets.resolve(target,project,root)
        if operation=='build_status':
            return projection_viewer.recompile_status(target['root'],repo_root=root,corpus=project,build_target=target)
        status,result = projection_viewer.recompile(target['root'],project,'author',repo_root=root,build_target=target)
        if status>=400:
            raise ValueError(result.get('reason') or result.get('error') or 'Derived build could not start.')
        return result
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("status") != "resolved" or not source.get("root"):
        raise ValueError("Select a manuscript source before building.")
    if operation == "build_status":
        return projection_viewer.recompile_status(source["root"], repo_root=root, corpus=project, compile_root=source["root"], _selection=source)
    if source.get("read_only"):
        raise ValueError("This source is read-only. Build an editable working copy to produce a new PDF.")
    status, result = projection_viewer.recompile(source["root"], project, "author", repo_root=root, compile_root=source["root"], _selection=source)
    if status >= 400:
        raise ValueError(result.get("reason") or result.get("error") or "PDF build could not start.")
    return result


def propose_revision(root: Path, project: str, payload: dict, turn_id: str | None) -> dict:
    from laplace.manuscript import proposal_preflight
    from laplace.core.records import journal
    with writing_records.proposal_write_lock(root):
        turn = writing_records.fold_records(root)['turns'].get(turn_id)
        if not turn or turn.get('project') != project:
            raise ValueError('A manuscript proposal requires the current project turn')
        proposal = {key:value for key,value in payload.items() if key != 'project'}
        proposal.setdefault('answer','')
        validation = proposal_preflight.preflight(root, project, turn, proposal)
        if not validation['valid']:
            raise ValueError('Proposal validation failed: '+'; '.join(validation['errors']))
        sealed=writing_records.bank(root, {'record': 'writing-proposal',
            'id': 'PROP-' + uuid.uuid4().hex, 'turn_id': turn_id, 'project': project,
            'proposal': validation['proposal']})
        return {'ok': True, 'status': 'PROPOSED', 'edits': len(proposal['edits']),
                'proposal_version':sealed['proposal_instance_version'],
                'proposal_content_sha256':sealed['proposal_content_sha256'],
                'proposal_record_id':sealed['id']}
