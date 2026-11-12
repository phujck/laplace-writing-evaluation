"""Joined manuscript structure over the canonical plan, conceptric and evidence."""
from __future__ import annotations

from laplace.core import identity_doors

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Mapping


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, default=str,
        separators=(",", ":")).encode()).hexdigest()


def _root(value=None) -> Path:
    if value is not None:
        return Path(value).resolve()
    from laplace.pipeline import registry
    return registry._repo_root().resolve()


def _label(node: dict, ident: str) -> str:
    projection = node.get("projection") or {}
    title = projection.get("title") or node.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return str(projection.get("term") or node.get("label") or node.get("essence") or ident)


def _node_row(nodes: dict, ident: str) -> dict:
    node = nodes.get(ident)
    if node is None:
        return {"id": ident, "label": ident, "missing": True, "kind": None,
                "status": "MISSING", "summary": "", "result_bindings": []}
    projection = node.get("projection") or {}
    bindings = projection.get("result_bindings") or []
    return {"id": ident, "label": _label(node, ident), "missing": False,
            "kind": node.get("kind"), "status": node.get("status"),
            "summary": node.get("essence") or "",
            "section_ref": projection.get("section_ref"),
            "result_bindings": list(bindings) if isinstance(bindings, list) else []}



def _node_summary(nodes: dict, ident: str) -> dict:
    node = nodes.get(ident)
    if node is None:
        return {"id": ident, "label": ident, "missing": True, "kind": None, "status": "MISSING"}
    projection = node.get("projection") or {}
    # An absent authored title is an address-only label, not a clipped essence.
    label = projection.get("title") or projection.get("term") or node.get("title") or node.get("label")
    return {"id": ident, "label": label or ident, "label_basis": "authored" if label else "address",
            "missing": False, "kind": node.get("kind"), "status": node.get("status"),
            "section_ref": projection.get("section_ref")}

def _logical_inventory(project: str, root: Path, placed_ids=(), net=None, *, summary=False, only_ids=None) -> dict:
    """All canonical L1 objects, independent of an L2 reader plan."""
    from laplace.research import corpus_ingest, concepts as concepts_surface
    if net is None:
        tex = corpus_ingest.resolve_corpus(root, project)
        net = corpus_ingest.corpus_network(tex, repo_root=root, name=project) if tex else {"nodes": {}}
    nodes = net.get("nodes") or {}
    placed = set(placed_ids)
    rows = []
    for ident, node in nodes.items():
        if only_ids is not None and ident not in only_ids:
            continue
        if node.get("kind") not in set(corpus_ingest.LOGICAL_KINDS) | set(corpus_ingest.DERIVATION_KINDS):
            continue
        row = _node_summary(nodes, ident) if summary else _node_row(nodes, ident)
        row.update(placed=ident in placed)
        if not summary:
            row.update(source_refs=concepts_surface._source_refs(node),
                       obligation=(node.get("projection") or {}).get("obligation"))
        rows.append(row)
    rows.sort(key=lambda row: (str(row.get("kind") or ""), str(row.get("label") or "").casefold()))
    return {"logical_objects": rows,
            "unplaced_nodes": [row for row in rows if not row["placed"]],
            "logical_omission": {"objects_total": len(rows), "objects_omitted": 0,
                                 "reader_order_declared": bool(placed)}}


def _source_correspondence(source: dict, traversal: dict, section: dict, *,
                           heading_rows_by_file: Mapping[str, list[dict]] | None = None) -> dict:
    from laplace.manuscript.bindings import correspondence
    return correspondence(source, traversal, section, heading_rows_by_file=heading_rows_by_file)


_HEADING = re.compile(r"\\(part|chapter|section|subsection|subsubsection)\*?\s*\{([^}]+)\}")

def _source_outline(traversal: dict, *, heading_rows_by_file=None) -> list[dict]:
    from laplace.manuscript.bindings import outline_rows
    rows = outline_rows({}, traversal, parsed=heading_rows_by_file)
    # Compatibility IDs are observation-local; never use them as plan identity.
    stack = []
    for index, row in enumerate(rows):
        while stack and stack[-1][0] >= row["level"]:
            stack.pop()
        row.update(id="source-heading-" + str(index + 1),
                   parent_id=stack[-1][1] if stack else None, bound=False)
        stack.append((row["level"], row["id"]))
    return rows


def _structure_identities(project: str, revision, authority, selected_source) -> dict:
    """The structure read's tokens: one name per value, the name being the home.

    ONE mint site for BOTH structure reads.  ``state`` serves ``GET /work/structure``
    (``project_work_surface.py:39``) -- the structure read the live app's browser actually
    calls -- and ``overview`` is the tool-door read.  Until this existed only the tool door
    published tokens, so the browser's own read offered four identity values and no token and
    the cure was unreachable from the one caller that matters most.  ``overview`` passes this
    block through instead of re-minting it, so the two doors cannot drift.
    """
    return identity_doors.identities(
        ("plan", project, revision),
        ("plan-file", project, (authority or {}).get("plan_revision")),
        ("selected-edition", project, (selected_source or {}).get("revision")))


def state(project: str, repo_root=None, *, research_records_snapshot=None,
          research_currentness_snapshot=None,research_run_cache=None,
          research_digest_cache=None,research_visual_specs=None,support_context=None,
          include_support: bool = True, _scope=None, _read_cache=None) -> dict:
    root = _root(repo_root)
    from laplace.pipeline import registry, schema
    from laplace.research import corpus_ingest
    from laplace.manuscript import manuscript_source
    from laplace.research import research_context, research_records
    record = registry.resolve(project, repo_root=root)
    if record is None or not record.plan_path:
        raise ValueError("This project has no canonical projection plan.")
    plan_path = record.plan(root)
    if plan_path is None or not plan_path.resolve().is_relative_to(root):
        raise ValueError("The canonical projection plan is unavailable inside this checkout.")
    source = support_context['source'] if support_context is not None else manuscript_source.resolve(project, repo_root=root)
    traversal = (support_context['traversal'] if support_context is not None else manuscript_source.traversal(source["root"], repo_root=root)
                 if source.get("status") == "resolved" and source.get("root")
                 else {"sources": [], "files": [], "diagnostics": source.get("diagnostics") or []})
    source = {**source, 'project': project,
              'selection_identity': manuscript_source.selection_identity(source, project)}
    if _read_cache is not None:
        _read_cache['source_tree'] = (source, traversal)
    selected_source = {key: source.get(key) for key in
                       ("root", "manuscript_dir", "edition", "status", "revision", "read_only", "selection_identity")}
    heading_rows_by_file = {}
    from laplace.manuscript.bindings import spine_snapshot
    spine, spine_revision = [], None
    outline = [] if _scope is not None else _source_outline(
        traversal, heading_rows_by_file=heading_rows_by_file)
    if not plan_path.is_file():
        spine, spine_revision = spine_snapshot(project, root)
        inventory = _logical_inventory(project, root, summary=not include_support)
        authority = {"plan_path": plan_path.relative_to(root).as_posix(), "plan_revision": None, "spine_revision": spine_revision,
                     "conceptric_revision": None, "research_revision": None,
                     "source_revision": source.get("revision")}
        gaps = [{"kind": "plan", "id": "projection_plan",
                 "reason": "canonical projection plan is missing; initialise it explicitly"}]
        gaps.extend({"kind": "source-outline", "id": row["id"],
                     "reason": "selected-source heading is not yet bound to a plan section"}
                    for row in outline)
        revision = _digest({"authority": authority, "outline": outline, "gaps": gaps})
        return {"schema_version": "laplace.project-structure/1", "project": project,
                "status": "MISSING", "revision": revision, "authority": authority,
                "selected_source": selected_source, "source_outline": outline,
                # The tokens, on every return of this read, not only the populated one: a
                # caller must not have to know which branch answered to know how to retry.
                # `identity_doors.identities` drops a home whose value is absent, so a
                # plan-less project publishes the homes it HAS.
                "identities": (_structure_identities(project, revision, authority, selected_source)
                    if include_support else identity_doors.identities(
                        ("plan-file", project, authority.get("plan_revision")),
                        ("selected-edition", project, selected_source.get("revision")))),
                "sections": [], "spine": spine, "nodes": [], "edges": [], "evidence": [], "gaps": gaps,
                **inventory,
                "writers": {"plan": "storyboard.plan_write", "membership": "storyboard coemit/spine",
                            "relations": "corpus_ingest.rewire_add"}}
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    if _read_cache is not None:
        _read_cache['plan'] = plan
    from laplace.manuscript.bindings import clearing_action
    from laplace.writing.prepared_work import action as prepare_action
    if not (plan.get("sections") or plan.get("appendices")):
        spine, spine_revision = spine_snapshot(project, root, plan=plan)
        inventory = _logical_inventory(project, root, summary=not include_support)
        authority = {"plan_path": plan_path.relative_to(root).as_posix(),
                     "plan_revision": "sha256:" + hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                     "spine_revision": spine_revision, "conceptric_revision": None, "research_revision": None,
                     "source_revision": source.get("revision")}
        gaps = [{"kind": "plan", "id": "projection_plan",
                 "reason": "canonical projection plan has no sections; initialise it explicitly"}]
        gaps.extend({"kind": "source-outline", "id": row["id"],
                     "reason": "selected-source heading is not yet bound to a plan section"}
                    for row in outline)
        revision = _digest({"authority": authority, "outline": outline, "gaps": gaps})
        return {"schema_version": "laplace.project-structure/1", "project": project,
                "status": "MISSING", "revision": revision, "authority": authority,
                "selected_source": selected_source, "source_outline": outline,
                # The tokens, on every return of this read, not only the populated one: a
                # caller must not have to know which branch answered to know how to retry.
                # `identity_doors.identities` drops a home whose value is absent, so a
                # plan-less project publishes the homes it HAS.
                "identities": (_structure_identities(project, revision, authority, selected_source)
                    if include_support else identity_doors.identities(
                        ("plan-file", project, authority.get("plan_revision")),
                        ("selected-edition", project, selected_source.get("revision")))),
                "sections": [], "spine": spine, "nodes": [], "edges": [], "evidence": [], "gaps": gaps,
                **inventory,
                "writers": {"plan": "storyboard.plan_write", "membership": "storyboard coemit/spine",
                            "relations": "corpus_ingest.rewire_add"}}
    tex = corpus_ingest.resolve_corpus(root, project)
    net = (support_context['net'] if support_context is not None else
           corpus_ingest.corpus_network(tex, repo_root=root, name=project) if tex else {"nodes": {}, "edge_index": {}, "spine": []})
    if _read_cache is not None:
        _read_cache['network'] = net
    nodes = net.get("nodes") or {}
    spine, spine_revision = spine_snapshot(project, root, plan=plan, network=net)
    from laplace.research import concepts as concepts_surface
    relations, _rewire = concepts_surface._relations(project, root, net)
    sections, planned_ids = [], []
    collection_of = {row["id"]: name for name in ("sections", "appendices") for row in plan.get(name, [])}
    scope_ids = set((_scope or {}).get('section_ids') or [])
    from laplace.manuscript.bindings import _declared_files
    scope_files = {file for supplied in (_scope or {}).get('files', [])
                   for file in _declared_files(source, traversal, str(supplied))}
    scope_nodes = set((_scope or {}).get('node_ids') or [])
    if (_scope or {}).get('node_id'):
        scope_nodes.add(_scope['node_id'])
    for order, raw in enumerate(schema.plan_sections(plan)):
        node_ids = schema.section_nodes(raw)
        if _scope is not None:
            from laplace.manuscript.bindings import _declared_files
            relevant = (raw.get('id') in scope_ids
                or bool(scope_files and set(_declared_files(source, traversal, str(raw.get('source_file') or ''))) & scope_files)
                or bool(set(node_ids + list(raw.get('beats') or [])) & scope_nodes))
            if not relevant:
                continue
        beat_ids = list(raw.get("beats") or [])
        planned_ids.extend(node_ids); planned_ids.extend(beat_ids)
        correspondence = _source_correspondence(
            source, traversal, raw, heading_rows_by_file=heading_rows_by_file)
        sections.append({"id": raw.get("id"), "collection": collection_of.get(raw.get("id")),
                         "title": raw.get("title") or raw.get("id"),
                         **{key: raw.get(key) for key in ('kind', 'parent_id', 'depth', 'number', 'ancestor_ids', 'child_ids')},
                         "order": order, "job": raw.get("job") or "",
                         "notes": raw.get("notes") or "", "refs": list(raw.get("refs") or []),
                         "node_ids": node_ids, "nodes": [(_node_row if include_support else _node_summary)(nodes, ident) for ident in node_ids],
                         "beat_ids": beat_ids, "beats": [(_node_row if include_support else _node_summary)(nodes, ident) for ident in beat_ids],
                         "source": correspondence,
                         "prepare_action": prepare_action(project,"sha256:" + hashlib.sha256(plan_bytes).hexdigest(),
                             source['selection_identity'],[raw.get("id")]),
                         "clearing_action": clearing_action(
                             project, raw.get("id"), "sha256:" + hashlib.sha256(plan_bytes).hexdigest())})
    live_beats = {row['id'] for row in net.get('spine', [])}
    for section in sections:
        for beat in section['beats']:
            beat['spine_status'] = 'LIVE' if beat['id'] in live_beats else 'MISSING_FROM_NARRATIVE'
            if beat['id'] not in live_beats and not beat.get('missing'):
                beat['repair_action'] = {'operation': 'structure_change',
                    'payload': {'operation': 'plan', 'op': {'kind': 'toggle-beat',
                        'section': section['id'], 'node': beat['id'], 'on': True}},
                    'guard_read': {'operation': 'structure', 'payload': {'view': 'full'}},
                    'requires': 'Copy the inspected full structure revision into expected_revision.'}
    planned = set(planned_ids)
    edges = [edge for edge in relations if edge.get("source") in planned and edge.get("target") in planned]
    evidence, evidence_by_node, gaps = [], {}, []
    if include_support:
        from laplace.research import literature_support, references_surface
        source_heading_cache = support_context['heading_cache'] if support_context is not None else {}
        citation_spans = literature_support.citation_context(
            project, root, structure={"sections":sections,"selected_source":selected_source},
            citations=support_context['citations'] if support_context is not None else None,
            selected_source=source, heading_spans_by_file=source_heading_cache)
        manuscript=support_context['manuscript'] if support_context is not None else references_surface._manuscript(project,root)
        associations=(support_context['associations'] if support_context is not None else references_surface._load_associations(manuscript) if manuscript else [])
        if support_context is not None:
            research_manuscript=support_context['research_store']
            research_records_snapshot=support_context['research_records_snapshot']
            research_run_cache=support_context['research_run_cache'];research_digest_cache=support_context['research_digest_cache']
            research_visual_specs=support_context['research_visual_specs']
        else:_item, research_manuscript = research_context.project(project, root)
        project_root = research_context.project_root(record, root) or research_manuscript
        if support_context is not None:literature_support._context_result_bindings(support_context,[str(binding['id'])
            for ident in dict.fromkeys(planned_ids) for binding in (nodes.get(ident,{}).get('projection') or {}).get('result_bindings') or [] if binding.get('id')])
        support_by_node = {ident: literature_support.for_node(
                           project, ident, root, net=net, associations=associations,
                           citations=citation_spans,
                           research_records_snapshot=research_records_snapshot,
                           research_store=research_manuscript,
                           research_project_root=project_root,
                           research_currentness_snapshot=research_currentness_snapshot,
                           research_run_cache=research_run_cache,
                           research_digest_cache=research_digest_cache,
                           research_visual_specs=research_visual_specs,support_context=support_context)
                           for ident in dict.fromkeys(planned_ids)}
        for section in sections:
            section["source_support"] = [support_by_node[ident] for ident in dict.fromkeys(section["node_ids"] + section["beat_ids"])]
        manuscript = research_manuscript
        for ident in dict.fromkeys(planned_ids):
            row = _node_row(nodes, ident)
            declared = row.get("result_bindings") or []
            ids = [str(binding.get("id")) for binding in declared
                   if isinstance(binding, Mapping) and binding.get("id")]
            if not ids:
                continue
            if manuscript is None:
                gaps.append({"kind": "evidence", "id": ident,
                             "reason": "linked results have no project research store"})
                continue
            observed = (literature_support._context_result_bindings(support_context,ids) if support_context is not None else research_records.result_bindings(
                manuscript, ids, project_root,
                records_snapshot=research_records_snapshot,
                currentness_snapshot=research_currentness_snapshot,
                run_cache=research_run_cache,digest_cache=research_digest_cache,
                visual_specs=research_visual_specs))
            expected = {str(binding.get("id")): str(binding.get("revision")) for binding in declared
                        if isinstance(binding, Mapping) and binding.get("id")}
            joined = []
            for binding in observed["bindings"]:
                item = {**binding, "node_id": ident,
                        "expected_revision": expected.get(binding["id"]),
                        "revision_match": expected.get(binding["id"]) == binding.get("revision")}
                joined.append(item); evidence.append(item)
                if not item["revision_match"] or item["currentness"] != "CURRENT":
                    gaps.append({"kind": "evidence", "id": binding["id"], "node_id": ident,
                                 "reason": "linked result revision is stale or not current"})
            for gap in observed["gaps"]:
                gaps.append({"kind": "evidence", "id": ident, "reason": gap})
            evidence_by_node[ident] = joined
    for section in sections:
        section["evidence"] = [item for ident in section["node_ids"] + section["beat_ids"]
                               for item in evidence_by_node.get(ident, [])]
        if section["source"]["status"] != "MATCHED":
            gaps.append({"kind": "source-correspondence", "id": section["id"],
                         "reason": "plan section has no match in the selected source edition"})
        elif section["source"]["title_status"] == "MISMATCH":
            gaps.append({"kind": "source-title-drift", "id": section["id"],
                         "reason": "plan title differs from the heading in its explicit source file"})
        for node in section["nodes"] + section["beats"]:
            if node["missing"]:
                gaps.append({"kind": "node", "id": node["id"],
                             "reason": "plan membership names an unavailable conceptric node"})
    spine_order = {str(beat.get("id")): index for index, beat in enumerate(net.get("spine", []))}
    # The mirror rule is judged over the WHOLE plan in document order, whatever the read's
    # scope: a node's first placement may lie outside a scoped detail read, and a scoped
    # read that computed first ownership over its own sections only called the plan
    # eligible while the full read refused it (reproduced 2026-10-14).  The listed gaps
    # stay scoped; eligibility does not.
    plan_rows = [{"id": raw.get("id"), "node_ids": schema.section_nodes(raw), "beat_ids": list(raw.get("beats") or [])}
                 for raw in schema.plan_sections(plan)]
    first_owner = {}
    for section in plan_rows:
        for node in section["node_ids"]:
            first_owner.setdefault(node, section["id"])
    mirror_gaps = []
    for section in plan_rows:
        live_beats = [beat for beat in section["beat_ids"] if beat in spine_order]
        anchor = min(live_beats, key=spine_order.get) if live_beats else None
        for beat in section["beat_ids"]:
            if beat not in spine_order:
                mirror_gaps.append({"kind": "mirror", "id": beat, "section_id": section["id"],
                                    "reason": "plan beat is not current spine membership"})
        for ident in section["node_ids"]:
            if first_owner.get(ident) != section["id"]:
                continue
            desired = None if not anchor or ident == anchor else anchor
            actual = ((nodes.get(ident) or {}).get("projection") or {}).get("section_ref")
            if actual != desired:
                mirror_gaps.append({"kind": "mirror", "id": ident, "section_id": section["id"],
                                    "reason": "node section_ref does not mirror its first plan section anchor",
                                    "expected_section_ref": desired, "actual_section_ref": actual})
    scoped_section_ids = {section["id"] for section in sections}
    gaps.extend(gap for gap in mirror_gaps if _scope is None or gap["section_id"] in scoped_section_ids
                or gap["id"] in planned_ids)
    node_rows = [(_node_row if include_support else _node_summary)(nodes, ident) for ident in dict.fromkeys(planned_ids)]
    authority = {"plan_path": plan_path.relative_to(root).as_posix(),
                 "spine_revision": spine_revision, "plan_revision": "sha256:" + hashlib.sha256(plan_path.read_bytes()).hexdigest(),
                 "conceptric_revision": _digest({"nodes": node_rows if include_support else {ident:nodes.get(ident) for ident in dict.fromkeys(planned_ids)}, "edges": edges,
                                                  "relation_diagnostics": net.get("relation_diagnostics") or []}),
                 "research_revision": _digest(evidence) if include_support else None,
                 "source_revision": source.get("revision")}
    revision = _digest({"authority": authority, "sections": sections, "gaps": gaps})
    eligible = not mirror_gaps
    inventory = _logical_inventory(project, root, planned_ids, net, summary=not include_support,
                                   only_ids=(set(planned_ids) | scope_nodes | {edge['target'] for edge in relations
                                       if edge.get('source') in set(planned_ids) | scope_nodes
                                       and edge.get('rel') == 'prerequisite'}) if _scope is not None else None)
    return {"schema_version": "laplace.project-structure/1", "project": project,
            "status": "AVAILABLE" if eligible else "INELIGIBLE", "eligible_for_authoring": eligible,
            "revision": revision, "authority": authority,
            # The HTTP read the browser actually uses (`GET /work/structure`,
            # project_work_surface.py:39) published FOUR identity values and no token:
            # `revision`, `authority.plan_revision`, `authority.source_revision` and
            # `selected_source.revision`.  `overview()` had the cure and this function did
            # not, so the one read the editor and the walk call was the only writing read
            # still naming four fields without naming a home.  Safe to add here and nowhere
            # else: `revision` is digested at :308 from {authority, sections, gaps} BEFORE
            # this dict is built, so the `plan` home's value cannot move, and
            # writing_tools.read_output_digest selects this read by `schema_version` before
            # any key test.  `authority.source_revision` STAYS in `authority` --- it is
            # inside the digested dict, and dropping it would move the home for every
            # caller; it is dropped from the PROJECTION at :418 only.
            "selected_source": selected_source, "source_outline": outline,
            # THE TOKENS, on the read the live app actually uses.  `GET /work/structure` is
            # served by THIS function (`project_work_surface.py:39`), never by `overview`, so
            # the browser's structure read published four identity values and no token until
            # now; `overview` reuses this block rather than minting a second one.
            #
            # The four scalars beside it are RETAINED, and each is a row of
            # `identity_doors.RETAINED` carrying its home, its live consumer, what deletes it
            # and its expiry (`identity_doors.EXPIRY`: a date and the parity run).
            # `authority.source_revision` is this read's second name for
            # `selected_source.revision`.  It is dropped from `overview`'s PROJECTION only and
            # NOT deleted here, because `revision` above is a digest OVER `authority`
            # (`:_digest({"authority": ..., "sections": ..., "gaps": ...})`), so removing the
            # key would move the `plan` home's value for every caller in the system.
            "identities": (_structure_identities(project, revision, authority, selected_source)
                if include_support else identity_doors.identities(
                    ("plan-file", project, authority.get("plan_revision")),
                    ("selected-edition", project, selected_source.get("revision")))),
            "sections": sections, "spine": spine,
            "plan_collections": {name: [row["id"] for row in plan.get(name, [])] for name in ("sections", "appendices")},
            "nodes": node_rows, "edges": edges,
            "evidence": evidence, "gaps": gaps,
            **inventory,
            "relation_diagnostics": list(net.get("relation_diagnostics") or []),
            "writers": {"plan": "storyboard.plan_write", "membership": "storyboard coemit/spine",
                        "relations": "corpus_ingest.rewire_add"}}



def summary_contract() -> dict:
    return {"type":"object", "additionalProperties":False,
        "properties":{"view":{"const":"summary"},
            "section_ids":{"type":"array","items":{"type":"string"},"uniqueItems":True},
            "section_offset":{"type":"integer","minimum":0}, "section_limit":{"type":"integer","minimum":1,"maximum":200},
            "object_offset":{"type":"integer","minimum":0}, "object_limit":{"type":"integer","minimum":1,"maximum":200},
            "gap_offset":{"type":"integer","minimum":0}, "gap_limit":{"type":"integer","minimum":1,"maximum":200},
            # an EXPLICIT member page on a scoped summary (a wide section the detail read
            # cannot hydrate); absent, list rows carry member_count only
            "member_offset":{"type":"integer","minimum":0}, "member_limit":{"type":"integer","minimum":1,"maximum":200},
            "spine_offset":{"type":"integer","minimum":0},
            "spine_limit":{"type":"integer","minimum":1,"maximum":200},
            "as_of":{"type":"string"}},"required":["view"]}




def navigation_reads() -> dict:
    return {"start":{"operation":"structure","payload":{"view":"summary"}},
            "selected_sections":{"operation":"structure","payload":{"view":"summary","section_ids":["<section_id from returned sections>"]}},
            "section_detail":{"operation":"structure","payload":{"view":"detail","section_ids":["<section_id>"],"member_offset":0,"member_limit":40}},
            "section_display":{"operation":"structure","payload":{"view":"detail","section_ids":["<section_id>"],"projection":"display"}},
            "section_beats":{"operation":"structure","payload":{"view":"detail","section_ids":["<section_id>"],"projection":"display","spine_offset":0}},
            "section_guard":{"operation":"structure","payload":{"view":"detail","section_ids":["<section_id>"],"projection":"guard"}},
            "plan_guard":{"operation":"structure","payload":{"view":"plan"}},
            "paragraph_guard":{"operation":"structure","payload":{"view":"detail","section_ids":["<section_id>"],"projection":"guard","subject":"paragraph","paragraph_id":"<paragraph_id from section_guard rows>"}},
            "then":"Summary rows are the list (number, title, job, precision, one detail_read); follow a row's detail_read for its members (paged by member_offset/member_limit; every continuation carries member_cut, the ordered-membership cut, and a changed plan refuses it with CHANGED_INPUT), source correspondence, source_reads and actions; plan_guard (view:plan) supplies the existing plan-state token and the complete plan order before a plan or spine mutation without the hydrated structure (full_guard_read is the same token on the full read). section_display (projection:display) is the bounded human page of one section: authored text, standing and doors, with its exact calls on subject reads. section_guard (projection:guard, subject:contract) is the bounded read for editing one section's reader contract: the exact edit_action payload (expected_plan_revision, expected_contract_revision, expected_reader_basis), the section's source binding, current authored values and a clipped row list of its paragraph page with one subject_read per row; paragraph_guard (subject:paragraph, paragraph_id) carries that one unit's row with its edit and remove calls; subject:create and subject:reorder carry those calls alone. One subject per read keeps every useful guard read under the native ceiling; full_read names the plain detail for everything omitted."}

def outline_contract() -> dict:
    return {"type": "object", "required": ["view"], "additionalProperties": False,
            "properties": {"view": {"const": "outline"},
                "files": {"type": "array", "items": {"type": "string"}},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "as_of": {"type": "string"}}}


def read_contract() -> dict:
    from laplace.pipeline.authoring import delivery_read_contract
    legacy={"type":"object","required":[],"properties":{
        "section_ids":{"type":"array","items":{"type":"string"}},
        "files":{"type":"array","items":{"type":"string"}},
        "node_id":{"type":"string"},"node_ids":{"type":"array","items":{"type":"string"}},
        "section_offset":{"type":"integer"},"section_limit":{"type":"integer"}},"additionalProperties":False}
    detail={**legacy,"required":["view"],"properties":{**legacy["properties"],
        "member_offset":{"type":"integer","minimum":0},"member_limit":{"type":"integer","minimum":1,"maximum":200},
        "member_cut":{"type":"string","minLength":1},
        "paragraph_offset":{"type":"integer","minimum":0},"paragraph_limit":{"type":"integer","minimum":1,"maximum":50},
        "paragraph_id":{"type":"string"},"paragraph_as_of":{"type":"string"},"edit_choices":{"type":"boolean"},
        # projection:display only (ACTUAL-C1011-DISPLAY-BYTES): one compact page of the section's narrative beats
        "spine_offset":{"type":"integer","minimum":0},
        # projection:guard (2026-10-14): the exact section_contract/paragraph_plan edit guards of ONE
        # section (expected_plan_revision, expected_contract_revision, expected_reader_basis) with
        # bounded context, from the same owner read; members, support, evidence and history stay
        # on the plain detail read.
        "projection":{"enum":["guard","display"]},
        "subject":{"enum":["contract","paragraph","create","reorder","section","structure"]},
        "view":{"const":"detail"},"line_start":{"type":"integer","minimum":1},"line_end":{"type":"integer","minimum":1}},
        # the guard selector policy (Sol guard-selector-policy, 2026-10-14): a guard names exactly
        # ONE canonical section_ids entry; files/node_id/node_ids are plain-detail selectors that
        # resolve to canonical ids first. Ordinary unprojected detail keeps every selector.
        "if":{"required":["projection"]},
        "then":{"required":["section_ids"],"properties":{"section_ids":{"type":"array","items":{"type":"string"},"minItems":1,"maxItems":1},
                                                         "files":False,"node_id":False,"node_ids":False}}}
    from laplace.manuscript.reader_restructure import read_contract as restructure_contract
    return {"oneOf":[summary_contract(),
        {"type":"object","properties":{"view":{"const":"full"}},"required":["view"],"additionalProperties":False},
        # view:plan (2026-10-14): the complete plan order and spine with the mutation revision, nothing hydrated
        {"type":"object","properties":{"view":{"const":"plan"}},"required":["view"],"additionalProperties":False},
        legacy, detail, outline_contract(), delivery_read_contract(),
        {"type":"object","required":["view"],"properties":{"view":{"const":"architecture-profile"}},"additionalProperties":False},restructure_contract()]}


def http_read_contract() -> dict:
    branches=[]
    for branch in read_contract()["oneOf"]:
        # the legacy project-only read (no view) is served by the final project-only branch below;
        # it is identified by shape, not by position, so an added view branch cannot shift it
        if "view" not in branch.get("properties",{}):continue
        branches.append({**branch,"properties":{"project":{"type":"string"},**branch.get("properties",{})},
                         "required":["project",*branch.get("required",[])],"additionalProperties":False})
    branches.append({"type":"object","properties":{"project":{"type":"string"}},
                     "required":["project"],"additionalProperties":False})
    return {"oneOf":branches}


def read(project: str, payload: Mapping | None = None, repo_root=None, *, http=False) -> dict:
    payload = dict(payload or {})
    view = payload.pop("view", "")
    if view=='restructure':
        from laplace.manuscript.reader_restructure import read as restructure_read
        return restructure_read(project,{'view':view,**payload},_root(repo_root))
    if view == 'delivery':
        from laplace.pipeline.authoring import read_delivery_part
        return read_delivery_part(project,{'view':view,**payload},repo_root)
    if view == "architecture-profile":
        if payload:
            raise ValueError("Architecture-profile read takes no selection or override.")
        from laplace.pipeline.narrative import architecture_status
        return {"project": project, **architecture_status(_root(repo_root), include_content=True)}
    if view == "outline":
        from jsonschema import Draft202012Validator
        issue = next(Draft202012Validator(outline_contract()).iter_errors({"view": view, **payload}), None)
        if issue:
            raise ValueError("Outline request: " + issue.message)
        from laplace.manuscript.bindings import outline
        return outline(project, _root(repo_root), **payload)
    if view == "summary":
        from jsonschema import Draft202012Validator
        query = {"view":view, **payload}
        issue = next(Draft202012Validator(summary_contract()).iter_errors(query), None)
        if issue:raise ValueError("Structure summary request: " + issue.message)
        return overview(project, repo_root, summary=True, **{
            "section_limit":40,"object_limit":40,"gap_limit":40,**payload})
    if view == "full":
        if payload:raise ValueError("Full structure read takes no scope; use summary or detail for selected sections.")
        return state(project, repo_root)
    if view == "plan":
        # THE PLAN GUARD (2026-10-14): the complete plan order and spine identities with the
        # mutation revision; the plan-level editors' bounded replacement for view:full
        if payload:raise ValueError("Plan read takes no scope; it is the complete plan order with the mutation revision.")
        from laplace.manuscript.reader_plan import plan_guard
        return plan_guard(state(project, repo_root))
    if view not in {"", "detail"}:raise ValueError("Structure view must be summary, detail, plan or full")
    if view == "detail":
        projection = payload.pop("projection", None)
        subject = payload.pop("subject", None)
        if "spine_offset" in payload and projection != "display":
            raise ValueError("spine_offset pages a section's narrative beats on projection:display only (read the display's spine_page.read).")
        if projection == "display":
            # THE HUMAN DISPLAY (ACTUAL-C6-DETAIL-BYTES): one section's bounded display page from
            # the same detail owner; exact calls are lazy subject reads
            from laplace.manuscript.reader_plan import display_projection, guard_section_id, DISPLAY_PAGE_ROWS, DISPLAY_MEMBER_ROWS
            if subject is not None:raise ValueError("projection:display takes no subject; subjects are projection:guard reads")
            if "spine_offset" in payload and payload.get("paragraph_id"):
                raise ValueError("projection:display reads either one paragraph (paragraph_id) or one beat page (spine_offset), not both.")
            wanted = guard_section_id(payload)
            scope = {key: value for key, value in payload.items() if key not in ('edit_choices', 'spine_offset')}
            if 'paragraph_limit' not in scope and 'paragraph_id' not in scope:
                scope['paragraph_limit'] = DISPLAY_PAGE_ROWS
            if 'member_limit' not in scope:
                scope['member_limit'] = DISPLAY_MEMBER_ROWS
            try:
                detail = context(project, scope, repo_root)
            except ValueError as exc:
                if 'Paragraph reads require one exact reader-plan section' not in str(exc): raise
                raise ValueError('projection:display reads exactly one existing reader-plan section; section_ids entry %r is not a current section (read view:summary for current ids).' % wanted) from exc
            return display_projection(detail, payload)
        if projection == "guard":
            from laplace.manuscript.reader_plan import guard_projection, guard_detail_scope, guard_section_id
            scope = {**payload, **({"subject": subject} if subject else {})}
            wanted = guard_section_id(scope)   # exactly one canonical section_ids entry, refused before any resolution
            # the detail read is scoped to what the subject can carry (N1-default): a paragraph
            # subject hydrates only its own row, the contract subject a GUARD_PAGE_ROWS page unless
            # a page or paragraph is named, and create/reorder hydrate no rows at all
            try:
                detail = context(project, guard_detail_scope(scope), repo_root)
            except ValueError as exc:
                if 'Paragraph reads require one exact reader-plan section' not in str(exc): raise
                raise ValueError('projection:guard reads exactly one existing reader-plan section; section_ids entry %r is not a current section (read view:summary for current ids).' % wanted) from exc
            return guard_projection(detail, scope)
        if projection is not None:raise ValueError("Structure detail projection must be guard or display")
        if subject is not None:raise ValueError("subject selects a projection:guard read")
        return context(project, payload, repo_root)
    if http:
        if payload:raise ValueError("Choose summary or detail for a scoped HTTP structure read")
        return state(project, repo_root)
    if not payload or set(payload) <= {"section_offset","section_limit"}:
        return overview(project, repo_root, **payload)
    return context(project, payload, repo_root)

def focused_node(project: str, node_id: str, repo_root=None) -> dict:
    """One canonical node plus its typed immediate conceptric neighborhood."""
    root = _root(repo_root)
    from laplace.research import corpus_ingest, concepts as concepts_surface
    tex = corpus_ingest.resolve_corpus(root, project)
    net = corpus_ingest.corpus_network(tex, repo_root=root, name=project) if tex else {"nodes": {}}
    nodes = net.get("nodes") or {}
    if node_id not in nodes:
        raise ValueError("workspace_context names an unavailable canonical concept node")
    relations, _rows = concepts_surface._relations(project, root, net)
    edges = [edge for edge in relations if edge.get("source") == node_id or edge.get("target") == node_id]
    neighbor_ids = {edge["source"] for edge in edges} | {edge["target"] for edge in edges}
    containment = concepts_surface.focus_projection(project, node_id, root)
    focus_node = {**containment["current"],
                  "result_bindings": list((containment["current"].get("projection") or {}).get(
                      "result_bindings") or [])}
    # concepts_surface owns the public mathematical-record projection, including
    # its qualified source locations.  Keep the structure view tied to that same
    # authority rather than reconstructing a second, potentially divergent record.
    concept = concepts_surface.state(project, node=node_id, root=root) or {}
    if concept.get("content_revision"):
        focus_node["content_revision"] = concept["content_revision"]
    result = {"node": focus_node,
            "neighbors": [_node_row(nodes, ident) for ident in sorted(neighbor_ids - {node_id})],
            "edges": edges, "containment": containment,
            "revision": _digest({"containment_revision": containment["revision"],
                                  "edges": edges,"neighbors": sorted(neighbor_ids),
                                  "mathematical_record": concept.get("mathematical_record")})}
    if isinstance(concept.get("mathematical_record"), Mapping):
        result["mathematical_record"] = concept["mathematical_record"]
    if isinstance(concept.get("source_support"), Mapping):
        focus_node["source_support"] = concept["source_support"]
        result["source_support"] = [concept["source_support"]]
        # The focus-scoped revision is no longer re-minted here.  It used to be a digest OF
        # A DIGEST under the same field name (`_digest({"focus_revision": result["revision"],
        # "source_support": ...})`), so one read published two different values called
        # `revision` depending on a branch, and neither was a home.  Nothing is lost: the
        # source identities this second digest folded in are already inside the
        # `concept-node` home, which concepts_surface.py:70-82 digests as
        # {node, content, relations, sources, prerequisites} and this read publishes as
        # `node.content_revision` and as the token below.
    # Only the homes this read IS about.  The `concept-network` token does NOT belong here:
    # this projection is embedded as `focus` in the scoped `context` read at :561, whose own
    # revision digests it, and a local read must not move when an unrelated global concept edit
    # moves the graph (tests/test_project_structure.py::
    # test_local_read_digests_ignore_only_incidental_global_revisions, which caught exactly that
    # when this lane first published both).  The focused homes are enough: `content_revision`
    # already covers this node's content, relations, sources and prerequisites
    # (concepts_surface.py:70-82).
    result["identities"] = identity_doors.identities(
        ("concept-node", "%s::%s" % (project, node_id), concept.get("content_revision")))
    return result


def overview(project:str,repo_root=None,*,object_limit:int=500,section_offset:int=0,
             section_limit:int=200, summary:bool=False, section_ids=None,
             object_offset:int=0, gap_offset:int=0, gap_limit:int=40, as_of:str="",
             member_offset:int=0, member_limit:int|None=None, spine_offset:int=0, spine_limit:int=40) -> dict:
    """Bounded agent map over the canonical structure owner.

    ``state`` remains the complete UI/canonical projection.  This view carries
    the reader plan and every bounded logical identity needed to choose an exact
    descent without copying scientific bodies, source excerpts or evidence rows.
    """
    if summary:
        from laplace.manuscript.bindings import reader_snapshot
        value = reader_snapshot(project, _root(repo_root), scope={"section_ids": section_ids or []},
                                window=(section_offset, section_limit))
    else:
        value = state(project, repo_root)
    if summary:
        object_limit=max(1,min(200,int(object_limit)));section_limit=max(1,min(200,int(section_limit)))
        return _summary_view(project, value, section_ids, section_offset, section_limit,
                             object_offset, object_limit, gap_offset, gap_limit, as_of, spine_offset, spine_limit,
                             member_offset=member_offset, member_limit=member_limit)
    object_limit=max(1,min(500,int(object_limit)));section_offset=max(0,int(section_offset))
    section_limit=max(1,min(200,int(section_limit)))
    def identity(row):
        out={key:row.get(key) for key in ("id","title","kind","status","placed")
             if row.get(key) is not None}
        if row.get("label") and row.get("label")!=row.get("summary"):out["label"]=row["label"]
        return out
    objects=[identity(row) for row in value.get("logical_objects") or []]
    unplaced=[row.get("id") for row in value.get("unplaced_nodes") or [] if row.get("id")]
    all_sections=value.get("sections") or [];sections=[]
    for section in all_sections[section_offset:section_offset+section_limit]:
        sections.append({key:section.get(key) for key in
            ("id","title","kind","parent_id","number","order","job","node_ids","beat_ids")
            if section.get(key) not in (None,[],"")})
    gaps=[{key:row.get(key) for key in ("kind","id","node_id","section_id","status")
           if row.get(key) is not None} for row in value.get("gaps") or []]
    evidence=value.get("evidence") or []
    return {"schema_version":"laplace.project-structure-overview/1","project":project,
        "status":value.get("status"),"eligible_for_authoring":value.get("eligible_for_authoring"),
        "revision":value.get("revision"),
        # `structure_revision` was a byte-identical second name for `revision` in this read
        # (both `value.get("revision")`, the `plan` home) and one of the twenty the friction
        # report counted.  Deleted, not deprecated: the token below names the home, and
        # writing_tools.read_output_digest selects this read's branch on `schema_version`
        # (writing_tools.py:682-684) before the `"structure_revision" in value` branch, so no
        # consumer loses its discriminator.  The scoped `context` read at :556 keeps the name
        # because there it is a DIFFERENT value from its own `revision` and is that branch's
        # discriminator (writing_tools.py:692).
        # `authority.source_revision` is likewise this read's second name for
        # `selected_source.revision`; it is dropped from the PROJECTION only, never from
        # state()'s own `authority`, because state()'s `revision` is a digest over that dict
        # and removing a key there would move the `plan` home's value for every caller.
        "authority":{key:item for key,item in (value.get("authority") or {}).items()
                     if key!="source_revision"},
        "selected_source":{key:(value.get("selected_source") or {}).get(key) for key in
            ("status","root","edition","revision","read_only")},
        # Every identity this read observed, each under the name of its own home, as the
        # token a caller copies into `expected`.  One name per value, and the name says where
        # the value came from -- which is the whole cure for the twenty names over nine
        # values.  Each scalar field that remains in this read is a ROW of
        # `identity_doors.RETAINED`, in code, carrying its home, its live consumer, what
        # deletes it and its expiry; the lane's report section 6.1 is a RENDER of that
        # register (`evidence/WRITING_RECONCILIATION_2026-10-02/wave1/identity-tokens/
        # retained_register.py` generates it), never a second list.
        # PASSED THROUGH from `state`, never re-minted: one mint site for the two structure
        # reads (`_structure_identities`), so the tool door and `GET /work/structure` cannot
        # publish different tokens for the same three homes.
        "identities":dict(value.get("identities") or {}),
        "reader_plan":{"sections":sections,"sections_total":len(all_sections),
            "sections_offset":section_offset,
            "sections_omitted":max(0,len(all_sections)-section_offset-len(sections)),
            **({"next_read":{"operation":"structure","payload":{
                "section_offset":section_offset+section_limit,"section_limit":section_limit}}}
               if section_offset+section_limit<len(all_sections) else {})},
        "logical_objects":{"items":objects[:object_limit],"total":len(objects),
            "omitted":max(0,len(objects)-object_limit),
            "unplaced_ids":unplaced[:object_limit],"unplaced_total":len(unplaced),
            "unplaced_omitted":max(0,len(unplaced)-object_limit)},
        "counts":{"evidence":len(evidence),"gaps":len(gaps),
            "relations":len(value.get("edges") or [])},"gaps":gaps[:80],
        "gaps_omitted":max(0,len(gaps)-80),
        "read_routes":{"section":{"operation":"structure",
            "payload":{"section_ids":["<section_id>"]}},
            "concept":{"operation":"concept","payload":{"node":"<logical_object_id>"}},
            "attention":{"operation":"logical_plan","payload":{"node":"<logical_object_id>"}},
            "inventory":{"operation":"logical_plan","payload":{"view":"catalog","offset":0,"limit":80}},
            "tree":{"operation":"concept_tree","payload":{"node":"<logical_object_id>"}}}}



def _summary_view(project, value, section_ids, section_offset, section_limit,
                  object_offset, object_limit, gap_offset, gap_limit, as_of, spine_offset=0, spine_limit=40,
                  *, member_offset=0, member_limit=None):
    """The reader-plan LIST (G18, `laplace.project-structure-summary/2`).

    A list row is what the plan is read as: number, title, job (the reader's purpose),
    the binding mark (precision and status of the source correspondence), the member
    count and ONE detail handle. Members, the source correspondence with its byte basis,
    source_reads and the clearing/prepare actions are the DETAIL of a section (`context`,
    view=detail, where members page by member_offset/member_limit). A section too wide for
    the detail's reader hydration still lists its members: an EXPLICIT `member_limit` on a
    scoped summary pages them on the row, and nothing else; absent, no row carries members.
    Measured on the live
    project the embedded members, source and source_reads were 38 KB of a 68 KB summary
    for 9 rows (5.8 KB per row); the list row is bounded by its title and job text.
    Invalidation is by `as_of`: the digest of the topology revision and the object
    inventory, so a continuation after a plan change is refused with CHANGED_INPUT.
    """
    cut = _digest({"topology":value["revision"],"inventory":value.get("logical_objects") or []})
    if as_of and as_of != cut:raise ValueError("CHANGED_INPUT: structure topology changed; read the current summary before paging")
    all_sections = value.get("sections") or []
    wanted = set(section_ids or [])
    missing = wanted - {row["id"] for row in all_sections}
    if missing:raise ValueError("Unknown structure section: " + ", ".join(sorted(missing)))
    selected = [row for row in all_sections if not wanted or row["id"] in wanted]
    members = {ident for row in selected for ident in row.get("node_ids", []) + row.get("beat_ids", [])}
    objects = [row for row in value.get("logical_objects") or [] if not wanted or row["id"] in members]
    gaps = [row for row in value.get("gaps") or [] if not wanted or row.get("id") in wanted|members or row.get("section_id") in wanted]
    query={"view":"summary",**({"section_ids":list(section_ids)} if section_ids else {}),
           "section_offset":section_offset,"section_limit":section_limit,
           "object_offset":object_offset,"object_limit":object_limit,"gap_offset":gap_offset,"gap_limit":gap_limit,
           **({"member_offset":member_offset,"member_limit":member_limit} if member_limit is not None else {}),
           "spine_offset":spine_offset,"spine_limit":spine_limit,"as_of":cut}
    def page(rows, offset, limit, prefix):
        items=rows[offset:offset+limit]
        result={"items":items,"offset":offset,"limit":limit,"total":len(rows),
                "omitted_before":min(offset,len(rows)),"omitted_after":max(0,len(rows)-offset-len(items))}
        if offset+len(items)<len(rows):
            result["next_read"]={"operation":"structure","payload":{**query,prefix+"_offset":offset+len(items)}}
        return result
    sections=[]
    for row in selected:
        source=row.get("source") or {}
        compact={key:row.get(key) for key in ("id","title","kind","parent_id","number","order","job","collection")}
        compact["precision"]=source.get("precision") or "NOT_ASSESSED"
        compact["binding_status"]=source.get("status")
        compact["member_count"]=len(row.get("node_ids") or [])+len(row.get("beat_ids") or [])
        compact["detail_read"]={"operation":"structure","payload":{"view":"detail","section_ids":[row["id"]]}}
        if member_limit is not None:
            availability={item['id']:item for item in (row.get('nodes') or [])+(row.get('beats') or []) if isinstance(item,Mapping) and item.get('id')}
            members=[{"id":ident,"role":role,"order":index,
                      "missing":bool(availability.get(ident,{}).get('missing')),
                      "detail_read":{"operation":"concept","payload":{"node":ident}}}
                     for role,key in (("node","node_ids"),("beat","beat_ids"))
                     for index,ident in enumerate(row.get(key) or [])]
            compact["members"]=page(members,max(0,int(member_offset)),max(1,min(200,int(member_limit))),"member")
            if compact["members"].get("next_read"):
                # the continuation narrows the section collection to this one exact row
                continuation=compact["members"]["next_read"]["payload"]
                continuation["section_ids"]=[row["id"]];continuation["section_offset"]=0
        sections.append(compact)
    for row in objects:
        row["detail_read"]={"operation":"concept","payload":{"node":row["id"]}}
    return {"schema_version":"laplace.project-structure-summary/2","project":project,
        "status":value.get("status"),"eligible_for_authoring":value.get("eligible_for_authoring"),
        # the summary is the reader-plan/source-correspondence list; plan/graph mirror
        # eligibility is judged by the full read, so an absent value is NOT_ASSESSED, never
        # "no gaps" (dossier 2026-10-13: summary CURRENT beside full INELIGIBLE)
        **({"eligibility_scope":"NOT_ASSESSED: plan/graph mirror eligibility (eligible_for_authoring) and mirror gaps are judged by full_guard_read; status here is reader-plan source correspondence only"}
           if value.get("eligible_for_authoring") is None else {}),
        "availability": value.get("availability", {}),
        "as_of":cut,"read_cut_scope":"Canonical topology/source correspondence; not the full plan-state mutation guard",
        "identities":value.get("identities") or {},"authority":{key:value for key,value in value.get("authority",{}).items() if key!="research_revision"},
        "selected_source":value.get("selected_source"),"support_assessment":"NOT_ASSESSED; descend to exact detail for scientific/evidence currentness",
        "sections":page(sections,section_offset,section_limit,"section"),
        # the spine LIST row: term, order, placement and one detail handle; the connective
        # narrative, concept read and guard live on the beat's detail (journey I budget)
        "spine":{**page([{key:row.get(key) for key in ("id","term","ord","placed","section_ids","detail_read") if key in row}
                         for row in value.get("spine", [])],spine_offset,spine_limit,"spine"),
                 "revision":value.get("authority", {}).get("spine_revision"),
                 "status":"AVAILABLE" if value.get("spine") else "MISSING"},
        "logical_objects":page(objects,object_offset,object_limit,"object"),"gaps":{**page(gaps,gap_offset,gap_limit,"gap"),"scope":"Structural gaps only; scientific gaps not assessed"},
        "full_guard_read":{"operation":"structure","payload":{"view":"full"}}}

def context(project: str, scope: Mapping[str, Any] | None = None, repo_root=None,
            *, _state_snapshot: Mapping[str, Any] | None = None) -> dict:
    """Project one scope, reusing a proven request-local state when supplied."""
    read_cache = {}
    if _state_snapshot is not None:
        value = dict(_state_snapshot)
    else:
        try:
            value = state(project, repo_root, _scope=scope or {}, _read_cache=read_cache)
        except ValueError as exc:
            if str(exc) != 'This project has no canonical projection plan.':
                raise
            from laplace.manuscript.bindings import reader_snapshot
            value = reader_snapshot(project, _root(repo_root), scope=scope or {})
    scope = scope or {}
    section_ids = {str(item) for item in (scope.get("section_ids") or scope.get("sections") or [])}
    files = {str(item) for item in (scope.get("files") or [])}
    explicit_node_ids=list(dict.fromkeys(str(item) for item in (scope.get("node_ids") or []) if str(item)))
    if len(explicit_node_ids)>500:raise ValueError("node_ids is limited to 500 canonical identities")
    focus = focused_node(project, str(scope["node_id"]), repo_root) if scope.get("node_id") else None
    def file_matches(section):
        return any(source_file == wanted or source_file.endswith("/" + wanted)
                   for source_file in section["source"]["source_files"] for wanted in files)
    selected = [section for section in value["sections"] if
                section["id"] in section_ids or file_matches(section) or
                bool((set(section.get("node_ids") or [])|set(section.get("beat_ids") or []))
                     & set(explicit_node_ids))]
    scope_diagnostics=[]
    if files and isinstance(scope.get("line_start"),int) and isinstance(scope.get("line_end"),int):
        # Manuscript attention is a passage, not every sibling that happens to
        # share its TeX file. Reuse the source-heading/reader-plan join.
        from laplace.manuscript import proposal_basis
        chosen={section["id"]:section for section in value["sections"] if section["id"] in section_ids}
        for file in files:
            matched,issues=proposal_basis._sections_for_edit(_root(repo_root),project,value,
                {"file":file,"line_start":scope["line_start"],"line_end":scope["line_end"]})
            chosen.update({section["id"]:section for section in matched})
            scope_diagnostics.extend(issues)
        selected=[section for section in value["sections"] if section["id"] in chosen]
    if not selected and not section_ids and not files:
        selected = []
    from laplace.manuscript.reader_plan import section_view
    paragraph_scope = {key: scope[key] for key in ('paragraph_offset', 'paragraph_limit', 'paragraph_id', 'paragraph_as_of', 'edit_choices') if key in scope}
    if paragraph_scope and len(selected) != 1:
        raise ValueError('Paragraph reads require one exact reader-plan section.')
    if len(selected) > 16:
        raise ValueError('Reader detail supports at most 16 selected sections; narrow section_ids or use the paged summary.')
    for section in selected:
        section.update(section_view(project, _root(repo_root), section, value['sections'],
            value['authority']['plan_revision'], cache=read_cache, **({'paragraph_limit': 0} if len(selected) > 1 else {}), **paragraph_scope))
    # THE MEMBERS of a section live on its detail (G18): the ordered node and beat identities
    # with their availability and concept reads, paged by member_offset/member_limit, with an
    # owner continuation scoped to this one section.
    member_offset=max(0,int(scope.get('member_offset') or 0)); member_limit=max(1,min(200,int(scope.get('member_limit') or 40)))
    requested_cut=scope.get('member_cut')
    for section in selected:
        availability={item['id']:item for item in (section.get('nodes') or [])+(section.get('beats') or [])
                      if isinstance(item,Mapping) and item.get('id')}
        members=[{"id":ident,"role":role,"order":index,
                  "missing":bool(availability.get(ident,{}).get('missing')),
                  "detail_read":{"operation":"concept","payload":{"node":ident}}}
                 for role,key in (("node","node_ids"),("beat","beat_ids"))
                 for index,ident in enumerate(section.get(key) or [])]
        # THE ORDERED-MEMBERSHIP CUT: a continuation names the exact ordered membership it was
        # paging; a changed plan (reordered, added or removed members) refuses the page instead
        # of mixing two orders (Sol, 2026-10-12). The cut is the digest of the ordered ids and
        # the plan revision they were read under.
        cut=_digest({"section":section["id"],"members":[row["id"] for row in members],
                     "plan_revision":value["authority"].get("plan_revision")})
        if requested_cut is not None and len(selected)==1 and requested_cut!=cut:
            raise ValueError("CHANGED_INPUT: this section's membership changed since the member page was read; read the section detail again before paging its members")
        items=members[member_offset:member_offset+member_limit]
        section["members"]={"items":items,"offset":member_offset,"limit":member_limit,"total":len(members),"cut":cut,
                            "omitted_before":min(member_offset,len(members)),"omitted_after":max(0,len(members)-member_offset-len(items))}
        if member_offset+len(items)<len(members):
            section["members"]["next_read"]={"operation":"structure","payload":{"view":"detail","section_ids":[section["id"]],
                                              "member_offset":member_offset+len(items),"member_limit":member_limit,"member_cut":cut}}
    reader_observation = {'plan_revision': value['authority']['plan_revision'],
        'spine_revision': value['authority'].get('spine_revision'),
        'selection_identity': value['selected_source']['selection_identity'],
        'source_files': [{'file': file, 'source_digest': pin['source_digest']} for file, pin in
            {file: pin for section in selected[:16] for file, pin in section.get('source', {}).get('basis', {}).items()}.items()],
        'reader_subjects': [basis for section in selected[:16] if section.get('reader_transition')
            for basis in [section['reader_transition']['reader_basis'],
                *[row['reader_basis'] for row in section['paragraph_plan']['paragraphs']['items']]]]}
    if len(reader_observation['source_files']) > 16:
        raise ValueError('Displayed source observation exceeds 16 files; select a narrower reader-plan scope.')
    if not reader_observation['spine_revision']:
        reader_observation.pop('spine_revision')
    selected_ids = {section["id"] for section in selected}
    from laplace.manuscript.book_outline import compact
    from laplace.pipeline import registry, schema
    record = registry.resolve(project, repo_root=repo_root)
    topology_plan = read_cache.get('plan') or (record.read_plan(repo_root) if record else {}) or {}
    topology = list(schema.plan_sections(topology_plan))
    for position, row in enumerate(topology):
        row['order'] = position
    ancestor_ids = {ident for section in selected for ident in section.get('ancestor_ids', [])}
    children = [compact(section) for section in topology if section.get('parent_id') in selected_ids]
    ancestors = [compact(section) for section in topology if section['id'] in ancestor_ids]
    order = {section['id']: section['order'] for section in topology}
    boundary_ids = {sid for selected_id in selected_ids for sid, position in order.items()
                    if abs(position - order[selected_id]) == 1}
    boundaries = [compact(section) for section in topology if section['id'] in boundary_ids]
    node_ids = {ident for section in selected for ident in section["node_ids"] + section["beat_ids"]}
    all_nodes = {row.get("id"): row for row in value.get("logical_objects", []) if row.get("id")}
    missing_explicit=[ident for ident in explicit_node_ids if ident not in all_nodes]
    if missing_explicit:raise ValueError("workspace_context names unavailable canonical members: "+", ".join(missing_explicit[:8]))
    selected_nodes=[]
    for ident in explicit_node_ids[:40]:
        row=all_nodes[ident]
        selected_nodes.append({key:row.get(key) for key in
            ("id","label","kind","summary","source_refs","result_bindings","parent","grade")}|{
            "read_routes":{"concept":{"operation":"concept","node":ident},
                           "history":{"operation":"concept_history","node":ident},
                           "tree":{"operation":"concept_tree","node":ident}}})
    # A node-focused turn is useful even when it has no reader-plan section.
    # Treat that focused node as scoped for dependencies and evidence, but do not
    # pull its neighbours into the selected manuscript scope.
    scoped_node_ids = set(node_ids)
    scoped_node_ids.update(explicit_node_ids)
    if focus and isinstance(focus.get("node"), Mapping) and focus["node"].get("id"):
        scoped_node_ids.add(str(focus["node"]["id"]))
    all_edges = list(value["edges"])
    if focus:
        all_edges.extend(edge for edge in focus.get("edges") or [] if isinstance(edge, Mapping))
    edge_keys, edges = set(), []
    for edge in all_edges:
        key = (edge.get("source"), edge.get("target"), edge.get("rel"), edge.get("axis"))
        if key in edge_keys or not ({edge.get("source"), edge.get("target")} & scoped_node_ids):
            continue
        edge_keys.add(key)
        edges.append(edge)
    direct_dependencies = []
    for edge in edges:
        # A prerequisite relation is directed from the statement that requires a
        # premise to that premise.  Keep the relation explicit; it is not proof.
        if (edge.get("rel") != "prerequisite" or edge.get("source") not in scoped_node_ids
                or edge.get("target") in scoped_node_ids):
            continue
        subject = all_nodes.get(edge.get("target")) or {"id": edge.get("target"), "missing": True}
        direct_dependencies.append({"id": subject.get("id"), "label": subject.get("label"),
                                    "kind": subject.get("kind"), "statement": subject.get("summary"),
                                    "source_refs": subject.get("source_refs") or [],
                                    "relation": edge.get("rel"),
                                    "required_by": edge.get("source")})
    all_evidence = [item for item in value["evidence"] if item.get("node_id") in scoped_node_ids]
    # state() joins plan members eagerly.  A focused unplanned node can still
    # have its own exact result bindings, so join just that node here instead of
    # pretending the node-only context has no evidence.
    if focus and isinstance(focus.get("node"), Mapping):
        declared = focus["node"].get("result_bindings") or []
        binding_ids = [str(item.get("id")) for item in declared
                       if isinstance(item, Mapping) and item.get("id")]
        if binding_ids:
            from laplace.research import research_context, research_records
            from laplace.pipeline import registry
            root = _root(repo_root)
            record = registry.resolve(project, repo_root=root)
            _item, manuscript = research_context.project(project, root)
            project_root = research_context.project_root(record, root) or manuscript
            if manuscript is not None and project_root is not None:
                expected = {str(item.get("id")): str(item.get("revision")) for item in declared
                            if isinstance(item, Mapping) and item.get("id")}
                observed = research_records.result_bindings(manuscript, binding_ids, project_root)
                seen = {(item.get("node_id"), item.get("id"), item.get("revision")) for item in all_evidence}
                for binding in observed["bindings"]:
                    item = {**binding, "node_id": focus["node"]["id"],
                            "expected_revision": expected.get(binding["id"]),
                            "revision_match": expected.get(binding["id"]) == binding.get("revision")}
                    key = (item.get("node_id"), item.get("id"), item.get("revision"))
                    if key not in seen:
                        all_evidence.append(item)
                        seen.add(key)
    evidence_limit=80;evidence=all_evidence[:evidence_limit]
    all_gaps = [gap for gap in value["gaps"] if gap.get("id") in selected_ids | scoped_node_ids
            or gap.get("node_id") in scoped_node_ids]
    gap_limit=80;gaps=all_gaps[:gap_limit]
    from laplace.research import literature_support
    support_by_node = {row["node"]:row for section in value["sections"] for row in section.get("source_support") or []}
    support_ids=list(dict.fromkeys(explicit_node_ids+sorted(scoped_node_ids-set(explicit_node_ids))))
    support_limit=40;projected_support_ids=support_ids[:support_limit]
    extra_ids = set(projected_support_ids) - support_by_node.keys()
    if extra_ids:
        citation_spans = literature_support.citation_context(project, _root(repo_root), structure=value)
        support_by_node.update({ident:literature_support.for_node(project,ident,_root(repo_root),citations=citation_spans) for ident in extra_ids})
    source_support = [support_by_node[ident] for ident in projected_support_ids if ident in support_by_node]
    from laplace.research import corpus_ingest
    history_rows=[row for row in corpus_ingest.rewire_list(_root(repo_root),project)
                  if isinstance(row,Mapping) and
                  ({str(row.get("node") or ""),str(row.get("target") or "")} & scoped_node_ids)]
    history_rows=list(reversed(history_rows));history_limit=20
    scoped_revision = _digest({"source_support":source_support, "selected_source": value["selected_source"],
                               "sections": selected, "boundaries": boundaries, "structure_observation": reader_observation,
                               "edges": edges, "evidence": evidence, "gaps": gaps,
                               "focus": focus, "ancestors": ancestors, "children": children,
                               "direct_dependencies": direct_dependencies,
                               "selected_node_ids":explicit_node_ids,
                               "selected_nodes":selected_nodes,
                               "scoped_history":history_rows[:history_limit]})
    result = {"schema_version": "laplace.project-structure-context/1", "project": project,
            "full_guard_read": {"operation": "structure", "payload": {"view": "full"}},
            "revision": scoped_revision, "structure_revision": None,
            "eligible_for_authoring": value.get("eligible_for_authoring", value.get("status") != "INELIGIBLE"),
            "authority": value["authority"], "selected_source": value["selected_source"],
            "sections": selected, "boundaries": boundaries, "structure_observation": reader_observation,
            "spine": [row for row in value.get("spine", []) if row["id"] in scoped_node_ids
                      or bool(set(row.get("section_ids", [])) & selected_ids)],
            "ancestors": ancestors, "children": children,
            "outline": [compact(section) for section in topology if not section.get('parent_id')],
            "focus": focus, "edges": edges, "evidence": evidence, "gaps": gaps,
            "selected_node_ids":explicit_node_ids,"selected_nodes_total":len(explicit_node_ids),
            "selected_nodes":selected_nodes,
            "selected_nodes_omitted":max(0,len(explicit_node_ids)-len(selected_nodes)),
            "selected_node_read_routes":{
                "concept":{"operation":"concept","payload":{"node":"<selected_node_id>"}},
                "history":{"operation":"concept_history","payload":{"node":"<selected_node_id>"}},
                "tree":{"operation":"concept_tree","payload":{"node":"<selected_node_id>"}}},
            "evidence_total":len(all_evidence),"evidence_omitted":max(0,len(all_evidence)-len(evidence)),
            "gaps_total":len(all_gaps),"gaps_omitted":max(0,len(all_gaps)-len(gaps)),
            "scoped_history":[{key:row.get(key) for key in
                ("id","ts","kind","node","target","by","rel","rationale")} for row in history_rows[:history_limit]],
            "scoped_history_omitted":max(0,len(history_rows)-history_limit),
            "direct_dependencies": direct_dependencies,"scope_diagnostics":scope_diagnostics,
            "source_support":source_support,"source_support_total":len(support_ids),
            "source_support_omitted":max(0,len(support_ids)-len(source_support))}
    result['revision'] = _digest(semantic_content(result))
    return result


def operation_contract() -> dict:
    """Machine-readable payload contract used by both help and the write gate."""
    from laplace.pipeline.schema import PLAN_OP_KINDS
    from laplace.manuscript.reader_plan import operation_contracts as reader_operations
    from laplace.writing.prepared_work import operation_contract as preparation_contract
    string = {"type": "string", "minLength": 1}
    strings = {"type": "array", "items": string}
    from laplace.manuscript.book_outline import KINDS
    outline_kind = {"enum": list(KINDS)}
    parent_id = {"type": ["string", "null"]}
    section = {
        "type": "object", "required": ["id", "title"], "additionalProperties": False,
        "properties": {"id": string, "title": string, "job": {"type": "string"}, "notes": {"type": "string"},
                       "file": {"type": "string"}, "kind": outline_kind, "parent_id": parent_id},
    }
    plan = {
        "add-section": {"required": ["kind", "section", "title"],
            "properties": {"kind": {"const": "add-section"}, "section": string,
                "title": string, "collection": {"enum": ["sections", "appendices"]},
                "source_file": string, "source_label": string, "source_title": string,
                "source_plan_title": string, "before_section": string, "after_section": string,
                "job": {"type": "string"}, "notes": {"type": "string"},
                "refs": {**strings, "description": "Citation keys in the selected manuscript's declared bibliographies; not reference-library record IDs."},
                "beats": strings, "nodes_in_order": strings,
                "figures": {**strings, "description": "Canonical figure-node IDs carrying projection provenance; raw asset filenames or visual-spec IDs are not figure nodes."}, "by": string}},
        "remove-section": {"required": ["kind", "section"],
            "properties": {"kind": {"const": "remove-section"}, "section": string,
                           "by": string}},
        "restore-section": {"required": ["kind", "entries"],
            "properties": {"kind": {"const": "restore-section"},
                "entries": {"type": "array", "items": {
                    "type": "object", "additionalProperties": True}},
                "expected_plan_digest": string, "by": string}},
        "set-outline": {"required": ["kind", "section", "outline_kind", "parent_id"],
            "properties": {"kind": {"const": "set-outline"}, "section": string,
                           "outline_kind": outline_kind, "parent_id": parent_id, "by": string}},
        "reorder-sections": {"required": ["kind", "order"],
            "properties": {"kind": {"const": "reorder-sections"}, "order": strings, "by": string}},
        "reorder-appendices": {"required": ["kind", "order"],
            "properties": {"kind": {"const": "reorder-appendices"}, "order": strings, "by": string}},
        "retitle": {"required": ["kind", "section", "title"],
            "properties": {"kind": {"const": "retitle"}, "section": string,
                           "title": string, "by": string}},
        "reorder-nodes": {"required": ["kind", "section", "order"],
            "properties": {"kind": {"const": "reorder-nodes"}, "section": string,
                           "order": strings, "by": string}},
        "edit-job": {"required": ["kind", "section", "job"],
            "properties": {"kind": {"const": "edit-job"}, "section": string,
                           "job": {"type": "string"}, "by": string}},
        "edit-notes": {"required": ["kind", "section", "notes"],
            "properties": {"kind": {"const": "edit-notes"}, "section": string,
                           "notes": {"type": "string"}, "by": string}},
        "set-refs": {"required": ["kind", "section", "refs"],
            "properties": {"kind": {"const": "set-refs"}, "section": string,
                           "refs": {**strings, "description": "Citation keys in the selected manuscript's declared bibliographies."}, "by": string}},
        "move-node": {"required": ["kind", "node", "from", "to"],
            "properties": {"kind": {"const": "move-node"}, "node": string,
                           "from": string, "to": string, "index": {"type": "integer"},
                           "by": string}},
        "add-node": {"required": ["kind", "section", "node"],
            "properties": {"kind": {"const": "add-node"}, "section": string,
                           "node": string, "index": {"type": "integer"}, "by": string}},
        "remove-node": {"required": ["kind", "section", "node"],
            "properties": {"kind": {"const": "remove-node"}, "section": string,
                           "node": string, "by": string}},
        "toggle-beat": {"required": ["kind", "section", "node"],
            "properties": {"kind": {"const": "toggle-beat"}, "section": string,
                           "node": string, "on": {"type": "boolean"}, "by": string}},
        "set-nodes": {"required": ["kind", "section", "order"],
            "properties": {"kind": {"const": "set-nodes"}, "section": string,
                           "order": strings, "by": string}},
        "set-meta": {"required": ["kind", "value"],
            "properties": {"kind": {"const": "set-meta"},
                           "value": {"type": "object", "additionalProperties": True}, "by": string}},
        "set-serves": {"required": ["kind", "section", "serves"],
            "properties": {"kind": {"const": "set-serves"}, "section": string,
                "serves": {"type": ["array", "string", "integer", "null"],
                           "items": {"type": ["string", "integer"]}}, "by": string}},
    }
    plan['add-section']['properties'].update(outline_kind=outline_kind, parent_id=parent_id)
    # bind-source is a recorded plan op, admitted only by bind_source with
    # selected-source/file guards. It is not a raw plan-edit bypass.
    if set(plan) != set(PLAN_OP_KINDS) - {"bind-source"}:
        raise RuntimeError("structure operation contract has drifted from canonical plan kinds")
    spine = {
        "reorder-spine": {"required": ["kind", "order"],
            "properties": {"kind": {"const": "reorder-spine"}, "order": strings, "by": string}},
        "set-narrative": {"required": ["kind", "node", "narrative"],
            "properties": {"kind": {"const": "set-narrative"}, "node": string,
                           "narrative": {"type": "string"}, "ord": {"type": "integer"},
                           "by": string}},
        "unset-spine": {"required": ["kind", "node"],
            "properties": {"kind": {"const": "unset-spine"}, "node": string, "by": string}},
    }
    common = {"project": string, "operation": {"enum": ["initialize", "plan", "spine", "reconcile", "bind_results"]},
              "expected_revision": string,
              # The grammar's own identity field, on every operation of this door: one list of
              # tokens instead of three field names (`expected_revision`,
              # `expected_source_revision`, `expected_concept_revision`) whose homes the
              # caller had to infer.  The old three remain accepted as shims.
              "expected": identity_doors.EXPECTED_FIELD}
    result = {"schema_version": "laplace.structure-change-contract/1",
        "required": ["operation", "expected_revision"], "common_properties": common,
        "operations": {
            "prepare_work": preparation_contract(),
            # writing.project_lifecycle: a source-optional project starts its manuscript and/or owns its plan
            "start_authoring": {"required": ["operation", "expected_project_lifecycle"],
                "properties": {"project": string, "operation": {"const": "start_authoring"},
                    "expected_project_lifecycle": string, "expected": identity_doors.EXPECTED_FIELD,
                    "kind": {"enum": ["paper", "book"]},
                    "title": {"type": "string", "minLength": 1, "maxLength": 240}}},
            **reader_operations(),
            "bind_source": {"required": ["operation", "section_id", "file", "line", "heading_before",
                "expected_plan_revision", "expected_selection", "expected_source_digest"],
                "properties": {"project": string, "operation": {"const": "bind_source"}, "section_id": string,
                    "file": string, "line": {"type": "integer", "minimum": 1}, "heading_before": string,
                    "expected_plan_revision": string, "expected_selection": string,
                    "expected_source_digest": string, "expected": identity_doors.EXPECTED_FIELD}},
            "initialize": {"required": ["operation", "expected_revision", "expected_source_revision"],
                "properties": {**common, "expected_source_revision": string,
                               "sections": {"type": "array", "items": section}}},
            "plan": {"required": ["operation", "expected_revision"],
                     "oneOf": [{"required": ["op"], "not": {"required": ["ops"]}},
                               {"required": ["ops"], "not": {"required": ["op"]}}],
                     "properties": {**common, "op": {"discriminator": "kind", "variants": plan},
                         "ops": {"type": "array", "minItems": 1, "maxItems": 16,
                             "items": {"oneOf": [{"type": "object", "additionalProperties": False, **row}
                                                  for row in plan.values()]}}}},
            "spine": {"required": ["operation", "expected_revision", "op"],
                      "properties": {**common, "op": {"discriminator": "kind", "variants": spine}}},
            "reconcile": {"required": ["operation", "expected_revision"], "properties": common},
            "bind_results": {"required": ["operation", "expected_revision",
                                               "expected_concept_revision", "node", "results"],
                "properties": {**common, "expected_concept_revision": string,
                    "node": string, "results": {"type": "array",
                    "items": {"type": "object", "required": ["id", "revision"],
                              "additionalProperties": False,
                              "properties": {"id": string, "revision": string}}}}},
        },
        "plan_operations": plan, "spine_operations": spine}
    operations = result['operations']
    result['operations'] = {'initialize': operations['initialize'], **{key: value for key, value in operations.items() if key != 'initialize'}}
    return result


def _type_ok(value: Any, expected) -> bool:
    choices = expected if isinstance(expected, list) else [expected]
    for name in choices:
        if name == "null" and value is None: return True
        if name == "string" and isinstance(value, str): return True
        if name == "object" and isinstance(value, Mapping): return True
        if name == "array" and isinstance(value, list): return True
        if name == "integer" and isinstance(value, int) and not isinstance(value, bool): return True
        if name == "boolean" and isinstance(value, bool): return True
    return False


def _validate_object(value: Any, schema: Mapping[str, Any], label: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    properties = schema.get("properties") or {}
    missing = [key for key in schema.get("required") or [] if key not in value]
    if missing:
        raise ValueError(f"{label} requires {', '.join(missing)}")
    if schema.get("additionalProperties", False) is not True:
        unknown = sorted(set(value) - set(properties))
        if unknown:
            raise ValueError(f"{label} contains unknown keys: {', '.join(unknown)}")
    for key, item in value.items():
        rule = properties.get(key)
        if not rule:
            continue
        if "const" in rule and item != rule["const"]:
            raise ValueError(f"{label}.{key} must be {rule['const']!r}")
        if "enum" in rule and item not in rule["enum"]:
            raise ValueError(f"{label}.{key} must be one of {rule['enum']}")
        if "type" in rule and not _type_ok(item, rule["type"]):
            raise ValueError(f"{label}.{key} has the wrong type")
        if isinstance(item, str) and rule.get("minLength", 0) and len(item) < rule["minLength"]:
            raise ValueError(f"{label}.{key} must not be empty")
        if isinstance(item, list) and rule.get("items"):
            for index, child in enumerate(item):
                child_rule = rule["items"]
                if child_rule.get("type") == "object":
                    _validate_object(child, child_rule, f"{label}.{key}[{index}]")
                elif "type" in child_rule and not _type_ok(child, child_rule["type"]):
                    raise ValueError(f"{label}.{key}[{index}] has the wrong type")
        if isinstance(item, Mapping) and rule.get("discriminator"):
            discriminator = rule["discriminator"]
            kind = item.get(discriminator)
            variant = (rule.get("variants") or {}).get(kind)
            if variant is None:
                raise ValueError(f"{label}.{key}.{discriminator} is unknown")
            _validate_object(item, {"type": "object", "additionalProperties": False, **variant},
                             f"{label}.{key}")


def _validate_change_payload(payload: Mapping[str, Any]) -> None:
    contract = operation_contract()
    operation = payload.get("operation")
    schema = contract["operations"].get(operation)
    if schema is None:
        raise ValueError("operation must be initialize, plan, spine, reconcile, bind_results, bind_source or start_authoring")
    if payload.get("expected"):
        # A caller that presents its identities as tokens does not also send them under their
        # old names, so the old names stop being `required` for it.  The list of old names is
        # the door's shim and nothing else, so this schema cannot drift from the gate.
        old = identity_doors.old_names("structure_change", "structure_change bind_results", "structure_change bind_source",
            "structure_change section_contract", "structure_change paragraph_plan", "structure_change start_authoring")
        schema = {**schema, "required": [key for key in schema.get("required") or []
                                         if key not in old]}
    if operation == 'plan':
        if ('op' in payload) == ('ops' in payload):
            raise ValueError('Plan change requires exactly one of op or ops.')
        if 'ops' in payload:
            ops = payload['ops']
            if not isinstance(ops, list) or not 1 <= len(ops) <= 16:
                raise ValueError('Plan ops must contain between 1 and 16 ordered operations.')
            for item in ops:
                rule = contract['plan_operations'].get(item.get('kind')) if isinstance(item, Mapping) else None
                if rule is None:
                    raise ValueError('Plan batch contains an unsupported operation; binding uses bind_source.')
                _validate_object(item, {'type': 'object', 'additionalProperties': False, **rule}, 'plan batch operation')
    _validate_object(payload, {"type": "object", "additionalProperties": False, **schema},
                     "structure_change payload")


def change(project: str, payload: Mapping[str, Any], repo_root=None, *, actor=None) -> dict:
    from filelock import FileLock
    from laplace.core import identity_doors
    identity_doors.admit_expected(payload, "structure_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    _validate_change_payload(payload)
    root = _root(repo_root)
    if payload.get("operation") in {"section_contract", "paragraph_plan"}:
        from laplace.manuscript.reader_plan import change as reader_change
        return reader_change(project, payload, root,actor=actor)
    if payload.get("operation") == "prepare_work":
        from laplace.writing.prepared_work import prepare
        return prepare(project,payload,root)
    if payload.get("operation") == "bind_source":
        from laplace.manuscript.bindings import bind_source
        return bind_source(project, payload, root)
    if payload.get("operation") == "start_authoring":
        # a source-optional project takes manuscript + plan ownership through the one lifecycle owner
        from laplace.projects.project_lifecycle import start_authoring
        return start_authoring(project, dict(payload), root, actor=actor)
    from laplace.pipeline import registry
    record = registry.resolve(project, repo_root=root)
    if record is None or not record.plan_path:
        raise ValueError("This project has no canonical projection plan.")
    plan_path = record.plan(root)
    if plan_path is None:
        raise ValueError("The canonical projection plan is unavailable.")
    from laplace.manuscript import manuscript_source
    # These operations write project plan/graph metadata, not selected source.
    # Read-only source remains readable binding evidence; source writers retain
    # their own immutable-source admission.
    with FileLock(str(plan_path) + ".structure.lock", timeout=15):
        current = state(project, root)
        # ONE comparison, and it names the home: the `plan` home, whose value is the one this
        # read just published.  This was a hand-written revision_matches of the payload's own
        # expected-revision field against current[revision], with the observed value dropped on
        # the floor at the moment it refused; the refusal now carries that value as the token to
        # retry with.  The old field name is spoken in identity_doors.DOORS and nowhere else --
        # including in this comment, because identity_names.py --static counts a quoted name
        # here as a door reading it off the payload.
        identity_doors.gate("structure_change", supplied=payload,
                            homes=[("plan", project, current["revision"])],
                            required=["expected_revision"],
                            said="structure revision conflict; read the current plan state first")
        operation = payload.get("operation")
        if operation == "initialize":
            from laplace.core.receipts import bundle, file_receipt
            plan_before=plan_path.read_bytes() if plan_path.is_file() else None
            prior_plan = {}
            if plan_path.is_file():
                prior_plan = json.loads(plan_path.read_text(encoding="utf-8"))
                if prior_plan.get("sections") or prior_plan.get("appendices"):
                    raise ValueError("canonical projection plan already has sections")
            # `expected_source_revision` names the `selected-edition` home and nothing else:
            # both doors that compare it (here and visuals_surface.py:349-350) compare the
            # selected edition's root-file bytes, not a traversal and not the read file.
            identity_doors.gate(
                "structure_change", supplied=payload,
                homes=[("selected-edition", project,
                        current["selected_source"].get("revision"))],
                required=["expected_source_revision"],
                said="selected source revision conflict; inspect the current edition first")
            declared = payload.get("sections")
            seeds = declared if isinstance(declared, list) and declared else current.get("source_outline") or []
            if not seeds:
                raise ValueError("initialisation requires selected-source headings or explicit sections")
            sections, seen = [], set()
            for seed in seeds:
                if not isinstance(seed, Mapping):
                    raise ValueError("initial sections must be objects")
                ident, title = str(seed.get("id") or "").strip(), str(seed.get("title") or "").strip()
                if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,79}", ident) or not title or ident in seen:
                    raise ValueError("initial section ids must be unique safe identities with titles")
                seen.add(ident)
                sections.append({"id": ident, "title": title, "job": str(seed.get("job") or ""),
                                 "kind": seed.get('kind', 'section'), "parent_id": seed.get('parent_id'),
                                 "notes": str(seed.get("notes") or ""), "refs": [], "beats": [], "nodes_in_order": [],
                                 "figures": [], "source_file": seed.get("file"),
                                 **({"source_title": title, "source_plan_title": title} if seed.get("file") else {})})
            plan = {"meta": {**(prior_plan.get("meta") or {}), "project": project,
                             "target_dir": (prior_plan.get("meta") or {}).get("target_dir")
                             or current["selected_source"].get("manuscript_dir"),
                             "source_root": current["selected_source"].get("root"),
                             "source_revision": current["selected_source"].get("revision")},
                    "sections": sections, "appendices": []}
            from laplace.manuscript.book_outline import validate_plan
            validate_plan(plan)
            from laplace.core.records import journal
            (root / "contract").mkdir(parents=True, exist_ok=True)
            journal.bank_row("contract/talk.jsonl", {
                "record": "manuscript-plan-initialize", "id": "PLANINIT-" + uuid.uuid4().hex,
                "project": project, "plan_path": plan_path.relative_to(root).as_posix(),
                "source_root": current["selected_source"].get("root"),
                "source_revision": current["selected_source"].get("revision"),
                "section_ids": [section["id"] for section in sections]}, root=root)
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_intended=(json.dumps(plan,ensure_ascii=False,indent=2)+"\n").encode('utf-8')
            pending = plan_path.with_name(plan_path.name + "." + uuid.uuid4().hex + ".pending")
            pending.write_bytes(plan_intended)
            pending.replace(plan_path)
            result = {"ok": True, "record": {"id": "projection_plan", "sections": list(seen)},
                      "owned_changes":bundle(files=[file_receipt(root,plan_path,plan_before,plan_intended)],
                          objects=[{"owner":"projection-plan","id":"projection_plan",
                                    "before_revision":current["revision"],"after_revision":None}],
                          views=["structure","manuscript"])}
        elif operation == "plan":
            from laplace.manuscript import storyboard
            op = dict(payload.get("op") or {})
            if op.get("kind") == "add-section":
                ident, title = str(op.get("section") or "").strip(), str(op.get("title") or "").strip()
                if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,79}", ident) or not title
                        or ident in {section["id"] for section in current["sections"]}):
                    raise ValueError("add-section requires a new safe section identity and title")
            operations = list(payload['ops']) if 'ops' in payload else [op]
            result = storyboard.plan_write_batch(project, operations, repo_root=root)
        elif operation == "spine":
            from laplace.manuscript import storyboard
            result = storyboard.spine_write(project, {**dict(payload.get("op") or {}),
                "expected_spine_revision": current["authority"]["spine_revision"]}, repo_root=root)
        elif operation == "reconcile":
            from laplace.manuscript import storyboard
            result = storyboard.reconcile_plan_mirrors(project, repo_root=root)
        elif operation == "bind_results":
            node = str(payload.get("node") or "")
            bindings = payload.get("results")
            if not node or not isinstance(bindings, list) or any(
                    not isinstance(item, Mapping) or not item.get("id") or not item.get("revision")
                    for item in bindings):
                raise ValueError("bind_results requires node and results [{id,revision}]")
            from laplace.research import corpus_ingest, concepts as concepts_surface
            from laplace.research import research_context, research_records
            # Evidence may be established before narrative placement.  Admit any
            # live logical object, never the paper root or structural shell.
            tex = corpus_ingest.resolve_corpus(root, project)
            net = corpus_ingest.corpus_network(tex, repo_root=root, name=project) if tex else {}
            live = (net.get('nodes') or {}).get(node) or {}
            from laplace.research.corpus_ingest import LOGICAL_KINDS
            if node == 'paper://' or live.get('kind') not in LOGICAL_KINDS:
                raise ValueError("result binding must name a live logical conceptric node")
            concept = concepts_surface.state(project, node=node, root=root)
            if concept is None:
                raise ValueError("concept revision conflict; inspect the focused concept first")
            # The report's sharpest instance: a TWO-home gate (`plan` and `concept-network`)
            # that named only the home it checked first, which cost one writer 8 refusals and
            # then 8 more.  `grammar.require` checks every expected token and the refusal
            # lists every stale home, so the second one can no longer be learnt by paying.
            # The home is `concept-network`, measured: concepts_surface.py:20-22's _revision
            # is minted at :123 and published at :136 by state() and minted and published at
            # :752 by logical_plan(), one value under three guard names.
            identity_doors.gate("structure_change bind_results", supplied=payload,
                                homes=[("concept-network", project, concept.get("revision"))],
                                required=["expected_concept_revision"],
                                said="concept revision conflict; inspect the focused concept first")
            _item, manuscript = research_context.project(project, root)
            if manuscript is None:
                raise ValueError("result binding requires a project research store")
            ids = [str(item["id"]) for item in bindings]
            observed = research_records.result_bindings(
                manuscript, ids, research_context.project_root(record, root) or manuscript)
            actual = {item["id"]: item for item in observed["bindings"]}
            if observed["gaps"] or any(actual.get(str(item["id"]), {}).get("currentness") != "CURRENT"
                                       or actual.get(str(item["id"]), {}).get("revision") != str(item["revision"])
                                       for item in bindings):
                raise ValueError("result binding is unavailable, stale, or names a different revision")
            result = corpus_ingest.rewire_add(root, project, {"kind": "set-projection", "node": node,
                "value": {"result_bindings": [{"id": str(item["id"]),
                                                  "revision": str(item["revision"])} for item in bindings]},
                "by": "project-structure"})
            if result.get("error"):
                raise ValueError(result["error"])
            result = {"ok": True, "record": result["record"]}
        else:
            raise ValueError("operation must be initialize, plan, spine, reconcile, bind_results, bind_source or start_authoring")
        if not result.get("ok") and not result.get("applied"):
            violations = result.get("new_violations") or []
            if violations:
                details = "; ".join(f"{kind}: {detail}" for kind, detail in violations[:12])
                omitted = len(violations) - min(12, len(violations))
                raise ValueError("Plan change was not applied: " + details
                                 + (f"; {omitted} further violations" if omitted else "")
                                 + ". refs must name selected-bibliography citation keys; figures must name canonical figure nodes with provenance.")
            raise ValueError(result.get("error") or result.get("note")
                             or "canonical structure writer refused the change")
        maintenance_warnings = []
        try:
            refreshed = state(project, root)
        except Exception as exc:
            if not result.get('applied') and not result.get('owned_changes'):
                raise
            refreshed = None
            maintenance_warnings.append({'operation': 'structure refresh', 'reason': str(exc)})
        response={"ok": bool(result.get("ok")),
                "status": result.get("status") or ("CURRENT" if result.get("ok") else "REFUSED"),
                "error": result.get("error"), "operation": operation,
                "applied": bool(result.get("applied") or result.get("owned_changes")),
                "changed": result.get("changed", True),
                "revision": refreshed["revision"] if refreshed else None,
                "detail_read": {"operation": "structure", "payload": {"view": "summary"}},
                **({"plan_publication": result["plan_publication"]} if result.get("plan_publication") else {}),
                **({"maintenance_warnings": maintenance_warnings} if maintenance_warnings else {}),
                "affected": {"identities": [str(item.get(key)) for item in payload.get("ops", [])
                                            for key in ("section", "node", "from", "to") if item.get(key)]
                             + [str(payload.get("node") or "")]
                             + [str((payload.get("op") or {}).get(key) or "")
                                for key in ("section", "node", "from", "to")],
                             "plan_path": str(plan_path.relative_to(root))},
                "writer_result": {key: result.get(key) for key in
                                  ("rebuild_class", "mirror", "record", "validation",
                                   "spine_deltas", "section_refs") if key in result},
                "state": refreshed}
        response["effects"]=(['structure','concepts','research','pipeline'] if operation=='bind_results'
                             else ['structure','manuscript','pipeline'])
        if isinstance(result.get("owned_changes"),dict):
            response["owned_changes"]=result["owned_changes"]
            for row in response["owned_changes"].get("objects") or []:
                if row.get("owner")=="projection-plan" and row.get("after_revision") is None:
                    row["after_revision"]=refreshed["revision"] if refreshed else None
        return response


def semantic_content(value):
    """Consulted reader/scientific content, excluding navigation and edit capabilities.

    Source dependencies and mutation owners retain their own exact byte guards.
    A read handle or whole-artifact edit token must not become a second scientific
    dependency that stales a disjoint paragraph or an unrelated profile field.
    Both native consumed-read validation and authoring context use this projection.
    """
    navigation = {'identities', 'structure_observation', 'full_guard_read', 'read_handle', 'read_more',
        'source_reads', 'clearing_read', 'clearing_action', 'prepare_action', 'edit_action', 'remove_action', 'create_action',
        'reorder_action', 'review_action', 'choices_read', 'next_read', 'http', 'update_handle',
        'expected_reader_basis', 'reader_basis', 'choices', 'choices_omitted', 'choices_total', 'placement'}
    def project(item, parent=''):
        if isinstance(item, list):
            return [project(row, parent) for row in item]
        if not isinstance(item, Mapping):
            return item
        out = {}
        for key, child in item.items():
            if key in navigation or key == 'structure_revision':
                continue
            if key == 'revision' and parent in {'', 'reader_transition', 'paragraph_plan', 'architecture_prior'}:
                continue
            if key == 'read' and isinstance(child, Mapping) and child.get('operation'):
                continue
            if parent == 'heading' and key in {'line', 'line_end', 'heading_line_end', 'source_order', 'source_orders'}:
                continue
            if key == 'source_occurrences':
                continue
            if parent == 'authority' and key.endswith('_revision'):
                continue
            if key == 'selected_source' or parent == 'source' and key == 'basis':
                continue
            if parent == 'architecture_prior' and key in {'profile_revision', 'field_refs', 'effective_genre'}:
                continue
            out[key] = project(child, key)
        return out
    return project(value)
