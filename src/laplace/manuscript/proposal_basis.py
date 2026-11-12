"""Canonical scientific basis for a source-addressed manuscript proposal.

This module does not create manuscript-to-concept links.  It reports the
existing plan placement for an edited source location and validates an optional
authorial declaration against the already-current canonical owners.
"""
from __future__ import annotations

from laplace.writing import records as writing_records

from laplace.core.identity import revision_matches

from pathlib import Path
from typing import Any, Mapping


def accepted_links(root: Path | str, project: str, *, files=None, application_id=None,
                   edit_id=None, offset=0, limit=40, as_of='', _span=None) -> dict:
    """Inspect one indexed page of accepted declarations and its exact carriers.

    Historical discovery has a captured cut. Text anchors and declared scientific
    basis are observed afresh; a changed whole-file SHA is not scientific rejection.
    """
    root = Path(root).resolve()
    from laplace.manuscript import manuscript_source, manuscript_proposals, proposal_preflight
    from laplace.manuscript import proposal_currentness
    source = manuscript_source.resolve(project, repo_root=root)
    manuscript = (root / str(source.get('manuscript_dir') or '')).resolve()
    rows, source_lines, body_cache, recovery = [], {}, {}, []
    current_span = None
    if _span:
        path = proposal_preflight._resolve(root, manuscript, str(_span.get('file') or ''))
        if path is not None:
            file = path.relative_to(root).as_posix()
            source_lines[file] = path.read_text(encoding='utf-8').split('\n')
            current_span = {**_span, 'repository_file': file,
                            'lines': source_lines[file], 'document': source}
    selected = writing_records.accepted_link_candidates(
        root, project, files=files, application_id=application_id, edit_id=edit_id,
        offset=offset, limit=limit, as_of=as_of, _current_span=current_span)
    requested_files = set(selected['file_scope']) if selected['file_scope'] is not None else None
    body_reads = 0
    structure, concept_cache = None, {}

    def field(handle, name):
        nonlocal body_reads
        key = (handle['id'], name, handle.get('row_sha256'))
        if key not in body_cache:
            body_cache[key] = writing_records.selected_journal_fields(
                project, handle['id'], root, fields=[name],
                expected_row_sha256=handle.get('row_sha256')).get(name)
            body_reads += 1
        return body_cache[key]

    for candidate in selected.pop('candidates'):
        summary = {key: candidate.get(key) for key in
                   ('application_id', 'turn_id', 'candidate_id', 'origin_turn_id', 'semantic_currentness','review_obligations', 'edit_id', 'file', 'line_start', 'line_end',
                    'develops', 'evidence_refs', 'application_read', 'carrier_read',
                    'declaration_coverage', 'scope_status', 'repository_file', 'span_status', 'read_more', 'carrier_read_more')}
        summary.update(anchor=None, basis=None, origin={
            'status': 'RECORDED_CANDIDATE' if candidate.get('candidate_id') else 'RECORDED_TURN', 'turn_id': candidate.get('turn_id'),
            'candidate_id':candidate.get('candidate_id'),'origin_turn_id':candidate.get('origin_turn_id'),
            'session_id': candidate.get('session_id'),
            'reason': 'Saved authoring application; earlier originating inputs are not inferred.'})
        inspection = None
        if (candidate.get('declaration_coverage') == 'LEGACY_UNKNOWN'
                or candidate.get('scope_status') == 'UNKNOWN'
                or candidate.get('span_status') == 'UNRESOLVED_CURRENT_SPAN'):
            # A recovery route is retained even if hydration finds no scientific
            # declaration. It names history, without asserting passage membership.
            inspection = {key: summary.get(key) for key in
                          ('application_id', 'turn_id', 'edit_id', 'file', 'repository_file',
                           'scope_status', 'read_more', 'carrier_read_more')}
            inspection.update(scope='RETAINED_CANDIDATE_INSPECTION',
                              passage_membership='NOT_ASSERTED',
                              declaration_status='NOT_YET_INSPECTED',
                              reason='Inspect the exact retained application; candidate discovery does not establish that it supports this passage.')
            recovery.append(inspection)
        try:
            edits = field(candidate['application_read'], 'edits')
            if not isinstance(edits, list):
                carrier = candidate.get('carrier_read') or {}
                if not carrier.get('id'):
                    if inspection is not None:
                        inspection['declaration_status'] = 'CARRIER_UNAVAILABLE'
                    rows.append({**summary, 'status': 'LEGACY_CARRIER_UNAVAILABLE',
                                 'reason': 'No exact proposal carrier can be selected from retained application identities.'})
                    continue
                proposal = field(carrier, 'proposal')
                edits = (proposal or {}).get('edits') if isinstance(proposal, dict) else None
                if isinstance(edits, list) and candidate.get('candidate_edit_ids'):
                    edits = [edit for edit in edits if isinstance(edit, Mapping)
                             and manuscript_proposals.edit_id(edit) in candidate['candidate_edit_ids']]
            if not isinstance(edits, list):
                raise ValueError('Selected application/proposal has no recoverable edit array.')
            edits = [edit for edit in edits if isinstance(edit, Mapping)
                     and (not candidate.get('edit_id') or manuscript_proposals.edit_id(edit) == candidate['edit_id'])
                     and (not edit_id or manuscript_proposals.edit_id(edit) == edit_id)
                     and (requested_files is None or writing_records.recorded_source_file(
                         candidate.get('document'), str(edit.get('file') or '')) in requested_files
                         or candidate.get('scope_status') == 'UNKNOWN')]
            if candidate.get('edit_id') and len(edits) != 1:
                raise ValueError('The exact selected edit is missing or ambiguous in its retained carrier.')
        except (ValueError, OSError, TypeError) as exc:
            if inspection is not None:
                inspection['declaration_status'] = 'RECORD_UNAVAILABLE'
            rows.append({**summary, 'status': 'RECORD_UNAVAILABLE', 'reason': str(exc)})
            continue
        if inspection is not None:
            declared = any(edit.get('develops') or edit.get('evidence_refs') for edit in edits)
            inspection['declaration_status'] = ('DECLARATION_RECORDED' if declared
                                                else 'NO_DECLARATION_IN_SELECTED_EDITS')
        for edit in edits:
            if not (edit.get('develops') or edit.get('evidence_refs')):
                continue
            row = {**summary, 'edit_id': manuscript_proposals.edit_id(edit),
                   'file': edit.get('file'), 'line_start': edit.get('line_start'),
                   'line_end': edit.get('line_end'), 'develops': list(edit.get('develops') or []),
                   'evidence_refs': list(edit.get('evidence_refs') or [])}
            same_edition = proposal_currentness._same_application_edition(
                {'document': candidate.get('document')}, {'document': source})
            after, anchor = edit.get('after'), None
            if same_edition and isinstance(after, str) and after:
                file = str(edit.get('file') or '')
                path = proposal_preflight._resolve(root, manuscript, file)
                if path is not None:
                    repository_file = path.relative_to(root).as_posix()
                    row['repository_file'] = repository_file
                    if repository_file not in source_lines:
                        source_lines[repository_file] = path.read_text(encoding='utf-8').split('\n')
                    lines, needle = source_lines[repository_file], after.split('\n')
                    matches = [i for i in range(len(lines) - len(needle) + 1)
                               if lines[i:i + len(needle)] == needle]
                    if len(matches) == 1:
                        anchor = {'file': repository_file, 'line_start': matches[0] + 1,
                                  'line_end': matches[0] + len(needle)}
            basis = None
            if anchor:
                if structure is None:
                    from laplace.manuscript import project_structure
                    try:
                        structure = project_structure.state(project, root)
                    except ValueError:
                        structure = {'sections': []}
                basis = assess(root, project, {**edit, **anchor}, structure=structure,
                               concept_cache=concept_cache, selected_source=source)
            status = ('UNPINNED_OR_OTHER_EDITION' if not same_edition else
                      'STALE_OR_AMBIGUOUS' if not anchor else
                      'LIVE_TEXT_REVIEW_REQUIRED' if candidate.get('semantic_currentness')=='REVIEW_REQUIRED' else
                      'LIVE_CURRENT_BASIS' if not basis.get('errors') else 'LIVE_TEXT_STALE_BASIS')
            rows.append({**row, 'status': status, 'basis': basis, 'anchor': anchor})
    selected['links'] = rows
    selected['uncertainty_recovery'] = recovery
    selected['coverage'].update(body_reads=body_reads, source_files_read=len(source_lines),
                                body_read_basis='Selected field resolutions, including inline fields; custody opens counted separately by records diagnostics.',
                                currentness_basis='Current unique after-text and independently checked declared revisions/placement.')
    return selected


def _file_sections(structure: Mapping[str, Any], file: str) -> list[dict]:
    target = str(file or "").replace("\\", "/")
    matches = []
    for section in structure.get("sections") or []:
        source = section.get("source") or {}
        files = source.get("source_files") or []
        if any(str(value).replace("\\", "/") == target or
               str(value).replace("\\", "/").endswith("/" + target) for value in files):
            matches.append(section)
    return matches


def _heading_spans(text: str) -> list[dict]:
    """Source-line heading spans using the structure owner's TeX parser."""
    from laplace.manuscript import manuscript_structure
    matches = manuscript_structure._heading_matches(text)
    levels = manuscript_structure._STRUCTURE_LEVEL
    rows = []
    for index, heading in enumerate(matches):
        end = len(text)
        for following in matches[index + 1:]:
            if levels[following["kind"]] <= levels[heading["kind"]]:
                end = following["start"]
                break
        rows.append({**heading, "level": levels[heading["kind"]],
                     "line_end": text.count("\n", 0, max(heading["start"], end - 1)) + 1})
    return rows


def _sections_for_edit(root: Path, project: str, structure: Mapping[str, Any],
                       edit: Mapping[str, Any], *,
                       selected_source: Mapping[str, Any] | None = None,
                       heading_spans_by_file: dict[str, list[dict]] | None = None,
                       require_heading_span:bool=False,
                       placement_cache:dict|None=None) -> tuple[list[dict], list[str]]:
    """Delegate to the same source witness shown by structure and passage readers."""
    from laplace.manuscript.bindings import sections_for_span
    return sections_for_span(structure, str(edit.get("file") or ""),
                             int(edit.get("line_start") or 0), int(edit.get("line_end") or 0))


def _declared(value: Any, field: str, errors: list[str]) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    rows = []
    for row in value:
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str) or not row["id"]:
            errors.append(f"{field} entries need an id")
            continue
        revision = row.get("content_revision") if field == "develops" else row.get("revision")
        if not isinstance(revision, str) or not revision:
            errors.append(f"{field} entry {row['id']} needs its current revision")
            continue
        rows.append({"id": row["id"],
                     "content_revision" if field == "develops" else "revision": revision})
    return rows


def assess(root: Path | str, project: str, edit: Mapping[str, Any], *,
           structure: Mapping[str, Any] | None = None,
           concept_cache: dict[str, Any] | None = None,
           concept_network_snapshot=None,
           selected_source: Mapping[str, Any] | None = None,
           heading_spans_by_file: dict[str, list[dict]] | None = None,
           require_heading_span:bool=False) -> dict:
    """Return current placement/basis and declared-basis errors for one edit.

    Empty declarations remain ordinary editorial work.  A scientific declaration
    must name a currently placed concept and, where present, a current result
    already bound to that placement.
    """
    root = Path(root).resolve()
    from laplace.research import concepts as concepts_surface
    from laplace.manuscript import project_structure
    errors: list[str] = []
    if structure is None:
        try:
            structure = project_structure.state(project, root)
        except ValueError as exc:
            structure = {"sections": []}
            if edit.get("develops") or edit.get("evidence_refs"):
                errors.append(f"canonical structure is unavailable: {exc}")
    concept_cache = concept_cache if concept_cache is not None else {}
    def concept(ident: str):
        if ident not in concept_cache:
            concept_cache[ident] = concepts_surface.identity(
                project, ident, root=root,
                network_snapshot=concept_network_snapshot)
        return concept_cache[ident]
    sections, limitations = _sections_for_edit(
        root, project, structure, edit, selected_source=selected_source,
        heading_spans_by_file=heading_spans_by_file,require_heading_span=require_heading_span)
    if sections:
        automatic_sections = [{key: section.get(key) for key in ("id", "title", "kind", "parent_id")}
                              for section in sections]
        automatic = []
        for section in sections:
            for ident in list(section.get("node_ids") or []) + list(section.get("beat_ids") or []):
                value = concept(str(ident))
                if value:
                    automatic.append({"id": str(ident), "label": value.get("label"), "kind": value.get("kind"),
                                      "content_revision": value.get("content_revision"),
                                      "section_id": section.get("id")})
        merged = {}
        for row in automatic:
            current = merged.setdefault(row["id"], {key: value for key, value in row.items()
                                                       if key != "section_id"} | {"section_ids": []})
            current["section_ids"].append(row["section_id"])
        automatic = list(merged.values())
    else:
        automatic, automatic_sections = [], []

    develops = _declared(edit.get("develops"), "develops", errors)
    evidence_refs = _declared(edit.get("evidence_refs"), "evidence_refs", errors)
    declared_present = bool(develops or evidence_refs)
    placed_ids = {str(item) for section in sections
                  for item in list(section.get("node_ids") or []) + list(section.get("beat_ids") or [])}
    resolved_develops = []
    for declared in develops:
        value = concept(declared["id"])
        if value is None:
            errors.append(f"develops names an unavailable canonical concept: {declared['id']}")
            continue
        if not revision_matches(declared["content_revision"],value.get("content_revision")):
            errors.append(f"develops concept changed: {declared['id']}")
        if declared["id"] not in placed_ids:
            errors.append(f"develops concept is not canonically placed at this source section: {declared['id']}")
        resolved_develops.append({"id": declared["id"], "label": value.get("label"), "kind": value.get("kind"),
                                  "content_revision": value.get("content_revision")})

    evidence = []
    if evidence_refs:
        if not develops:
            errors.append("evidence_refs require a declared, canonically placed develops concept")
        from laplace.research import research_context, research_records
        item, manuscript = research_context.project(project, root)
        project_root = research_context.project_root(item, root) if item is not None else None
        found = (research_records.result_bindings(manuscript, [row["id"] for row in evidence_refs], project_root)
                 if manuscript is not None else {"bindings": [], "gaps": ["project research store is unavailable"]})
        by_id = {row.get("id"): row for row in found.get("bindings") or []}
        section_bindings = {str(row.get("id")): row for section in sections
                            for row in section.get("evidence") or []
                            if not develops or row.get("node_id") in {item["id"] for item in develops}}
        for declared in evidence_refs:
            value = by_id.get(declared["id"])
            if value is None:
                errors.append(f"evidence reference is unavailable: {declared['id']}")
                continue
            if value.get("revision") != declared["revision"] or value.get("currentness") != "CURRENT":
                errors.append(f"evidence reference changed or is not current: {declared['id']}")
            if declared["id"] not in section_bindings:
                errors.append(f"evidence reference is not canonically bound to this declared concept: {declared['id']}")
            evidence.append({key: value.get(key) for key in ("id", "revision", "currentness", "reason")})

    status = ("INVALID" if errors else "DECLARED" if declared_present else
              "SECTION_CONTEXT" if automatic else "UNATTRIBUTED_LEGACY")
    for row in automatic+resolved_develops:
        row['read']={'operation':'concept','payload':{'node':row['id']},
            'http':{'method':'GET','route':'/concepts/context','query':{'corpus':project,'node':row['id']}}}
    for row in evidence:
        row['read']={'operation':'research','payload':{'view':'result','id':row['id']},
            'http':{'method':'GET','route':'/research/result','query':{'project':project,'id':row['id']}}}
    return {"status": status,
            "automatic_sections": automatic_sections,
            "automatic_section_concepts": automatic,
            "develops": resolved_develops,
            "evidence": evidence,
            "limitations": limitations,
            "errors": errors}


def passage_context(root:Path|str,project:str,anchor:Mapping[str,Any],plan:Mapping[str,Any], *,
                    accepted_offset=0, accepted_limit=40, accepted_as_of="") -> dict:
    """One reader/model join over exact source heading placement and existing owners."""
    root=Path(root).resolve()
    basis=assess(root,project,anchor,require_heading_span=True)
    sections=basis["automatic_sections"];ids={row["id"] for row in basis["automatic_section_concepts"]}
    obligations=[row for row in plan.get("obligations") or [] if any(
        (row.get("target") or {}).get(key) in ids for key in ("node_id","source","target"))]
    links=[]
    from laplace.manuscript import manuscript_source
    selected = manuscript_source.resolve(project, repo_root=root)
    accepted = accepted_links(root, project, files=[str(anchor.get('file') or '')], _span=anchor,
        offset=accepted_offset, limit=accepted_limit, as_of=accepted_as_of)
    for row in accepted['links']:
        place = row.get('anchor') or row
        if not row.get('anchor') or row.get('scope_status') == 'UNKNOWN' or (writing_records.recorded_source_file(selected, str(place.get('file') or ''))
                    == writing_records.recorded_source_file(selected, str(anchor.get('file') or ''))
                and (place.get('line_start') or 0) <= anchor.get('line_end', 0)
                and anchor.get('line_start', 0) <= (place.get('line_end') or 0)):
            links.append(row)
    from laplace.pipeline import document_model
    from laplace.manuscript import manuscript_source, proposal_preflight, projection_viewer
    selected=manuscript_source.resolve(project,repo_root=root)
    manuscript=(root/str(selected.get("manuscript_dir") or "")).resolve()
    path=proposal_preflight._resolve(root,manuscript,str(anchor.get("file") or ""))
    spans=projection_viewer.load_paragraphs(path) if path and path.is_file() else []
    matches=[span for span in spans if span["start_line"]<=anchor.get("line_start",0)
             and anchor.get("line_end",0)<=span["end_line"]]
    marker=matches[0] if len(matches)==1 else None
    if marker and marker.get("section") and not any(row["id"]==marker["section"] for row in sections):
        from laplace.manuscript import project_structure
        from laplace.research import concepts as concepts_surface
        declared=next((row for row in project_structure.state(project,root).get("sections") or []
                       if row.get("id")==marker["section"]),None)
        if declared:
            sections=[{key:declared.get(key) for key in ("id","title","kind","parent_id")}]
            basis["automatic_sections"]=sections
            basis["automatic_section_concepts"]=[value for ident in
                list(declared.get("node_ids") or [])+list(declared.get("beat_ids") or [])
                if (value:=concepts_surface.identity(project,ident,root))]
            basis["limitations"].append("Section bound by an explicit PLAN source marker.")
    paragraph_concepts=[];exact_paragraph=False
    provenance=[]
    for section in sections:
        sid=section["id"]
        diagnostics=[]
        records=document_model.load_provenance(project,sid,root,diagnostics=diagnostics)
        decisions=document_model.load_decisions(project,sid,root,diagnostics=diagnostics)
        precision="SECTION_ONLY";reason="Existing section sidecars; no paragraph origin is inferred for this passage."
        if marker and marker.get("section")==sid:
            section_spans=[span for span in spans if span.get("section")==sid]
            if isinstance(records,list) and [span["spec_ids"] for span in section_spans]==[
                    document_model._record_spec_ids(record) for record in records]:
                index=section_spans.index(marker);records=[records[index]]
                decisions=[row for row in decisions or [] if row.get("spec_id") in marker["spec_ids"]]
                precision="PARAGRAPH_MARKER";reason="Exact source marker group and ordered provenance records agree."
                exact_paragraph=True
                from laplace.research import concepts as concepts_surface
                for ident in records[0].get("nodes_realised") or []:
                    value=concepts_surface.identity(project,ident,root)
                    paragraph_concepts.append(value or {"id":ident,"status":"UNAVAILABLE"})
            else:reason="Paragraph markers exist, but their ordered provenance records do not agree; section context only."
        provenance.append({"section_id":sid,"precision":precision,
            "status":"RECORDED" if records is not None or decisions is not None else "UNKNOWN",
            "paragraphs":records,"decisions":decisions,"reason":reason,"diagnostics":diagnostics})
    ids={row["id"] for row in (paragraph_concepts if exact_paragraph else basis["automatic_section_concepts"])}
    obligations=[row for row in plan.get("obligations") or [] if any(
        (row.get("target") or {}).get(key) in ids for key in ("node_id","source","target"))]
    next_offset = accepted['pagination'].get('next_offset')
    continuation = None
    if next_offset is not None:
        query = {**dict(anchor), 'accepted_offset': next_offset, 'accepted_limit': accepted_limit,
                 'accepted_as_of': accepted['as_of']}
        continuation = {'operation': 'logical_plan', 'payload': query,
            'http': {'method': 'GET', 'route': '/concepts/plan/context', 'query': {'corpus': project, **query}}}
    return {"accepted_proposal_next_read": continuation, "anchor":dict(anchor),"precision":"PARAGRAPH_MARKER" if exact_paragraph else "SECTION_ONLY" if sections else "UNBOUND",
            "paragraph_marker":marker,"paragraph_concepts":paragraph_concepts,
            "basis":basis,"obligations":obligations,"accepted_proposals":links,
            "accepted_proposal_coverage":accepted["coverage"],
            "accepted_proposal_recovery":accepted["uncertainty_recovery"],
            "accepted_proposal_pagination":accepted["pagination"],
            "accepted_proposal_as_of":accepted["as_of"],
            "document_provenance":provenance,
            "limitations":["Section placement does not assert that every paragraph develops every section concept.",
                            "Historical origins absent from existing owners remain unknown."]}
