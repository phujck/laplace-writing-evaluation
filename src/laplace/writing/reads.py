"""THE READ CONTRACT (core consolidation, family 2): what a consulted read is, in one place, with no door.

``READS`` and ``WRITES`` name every project operation; ``output_digest``/``read_output_digest`` give a read's consulted
substance one identity (diagnostics excluded); ``read_basis_index``/``basis_changes``/``bounded_inspect_reads`` say
WHERE a consulted read moved and which bounded current reads show it; ``stale_evidence_message``/``_families`` are the
one refusal sentence for stale consulted evidence; ``ACTION_VIEWS`` names the views each write affects. The native
gateway (writing_tools), the operation table (writing.operations) and the currentness owners (proposal_currentness,
turn_reads, source_application, mutation_attribution) all consume these definitions; nothing here imports them.
"""
from __future__ import annotations

import hashlib
import json
import re

READS = {"profile", "app_settings", "material_references", "storage", "materials", "help", "conversation_history", "document", "source", "pipeline", "writing_stage", "project_metadata", "structure", "logical_plan", "writing_style", "writing_style_calibration", "project_guidance", "reference_text", "reference_source", "project", "concept", "concept_tree", "concept_history", "references", "reference", "research", "visuals", "proofs", "read_artifact", "repository", "author_changes",
         "proof_targets", "references_attached", "run_status", "build_status", "author_history", "literature_discover", "literature_lookup", "literature_uses", "literature_scope", "session_settings",
         # S3 (2026-10-06) the in-app dispatch door: the three reads of a dispatch
         "dispatch", "dispatch_status", "dispatch_returns"}


WRITES = {"profile_change", "material_reference_change", "storage_prune", "propose_revision", "proposal_supersede", "project_metadata_change", "style", "writing_style_change", "writing_style_profile_change", "project_guidance_change", "export_pdf", "chapter", "framing", "argument", "task", "task_status", "structure_change", "concept_change", "logical_plan_change", "research_record", "research_reconcile", "research_producer",
          "visual_create", "visual_render", "visual_place", "experiment_run", "run_cancel", "proof_check", "note", "note_status", "store_artifact", "reference_attach", "reference_update", "reference_refresh", "literature_import", "literature_bind", "reference_fetch", "build", "apply_revision", "section_change", "block_change", "session_settings_change",
          # S3 (2026-10-06) the in-app dispatch door: its two writes
          "dispatch_plan", "dispatch_launch", "dispatch_continue",
          # M5 (2026-10-16) the Work review lifecycle (project_work_review)
          "work_review",
          # in-harness join (2026-10-20): the development-source grant and the Work recipient delivery
          "development_source", "work_delivery", "workflow_definition_change", "research_object_change", "research_handover"}


def output_digest(value):
    def stable(v):
        if isinstance(v, dict):
            return {k:stable(x) for k,x in v.items()
                    if k not in {"observed_at", "contexts", "reading_observations", "owned_changes", "context_refresh", "read_receipt"}}
        if isinstance(v, list):
            return [stable(x) for x in v]
        return v
    return hashlib.sha256(json.dumps(stable(value), sort_keys=True, default=str).encode()).hexdigest()


def _engineering_read_substance(value):
    """Remove only known engineering IO counters, preserving acceptance substance."""
    def support(row):
        if not isinstance(row,dict):return row
        answer={key:item for key,item in row.items() if key!='read_metrics'}
        if 'claims' in answer:answer['claims']=[support(claim) for claim in answer['claims']]
        return answer
    if not isinstance(value,dict):return value
    answer=dict(value)
    if isinstance(answer.get('source_support'),dict):
        sources=dict(answer['source_support'])
        if 'engineering_support' in sources:sources['engineering_support']=support(sources['engineering_support'])
        answer['source_support']=sources
    if 'engineering_support' in answer:answer['engineering_support']=support(answer['engineering_support'])
    if isinstance(answer.get('project_protocol'),dict):answer['project_protocol']=_engineering_read_substance(answer['project_protocol'])
    if isinstance(answer.get('documents'),list):answer['documents']=[_engineering_read_substance(row) for row in answer['documents']]
    # A JSON-record page reports how long its parse took (json_record.select parse.parse_ms): a wall-clock
    # counter, proved volatile for byte-identical sources (tests/test_scoped_progress.py), never consumed
    # meaning. source_sha256, value_sha256, pointer and source_bytes stay in the digest.
    record=answer.get('json_record')
    if isinstance(record,dict) and isinstance(record.get('parse'),dict) and 'parse_ms' in record['parse']:
        answer['json_record']={**record,'parse':{key:item for key,item in record['parse'].items() if key!='parse_ms'}}
    return answer


#: Coordination reads describe session, dispatch, Work-progress and catalogue state that moves with unrelated
#: activity (another task's status, a child's progress, a new artifact elsewhere in the project). A manuscript
#: source effect does not rest on them: they are still replayed, and a change is reported as a local review
#: obligation on the result instead of refusing it (the original apply refusals named exactly these families).
#: The inputs a hunk rests on -- source, concept, plan, structure, research, visuals, literature and the exact
#: artifact or repository read -- remain consumed and refuse when they move.
COORDINATION_READS = frozenset({"dispatch_status", "session_settings", "materials", "storage", "app_settings"})

#: Work-object views of the ``project`` read (the Work owner's detail, continuity, review and provenance
#: projections). The default project read also carries the authored argument and framing, so it stays consumed.
WORK_COORDINATION_VIEWS = frozenset({"detail", "continuity", "review-evidence", "provenance", "review",
                                     "workflow-definitions"})


def read_role(operation: str, payload: dict | None = None) -> str:
    """The scoped role (laplace.core.scoped) of a consulted read for a manuscript source effect.

    A document read (manuscript, derived or publication-edition target) observes derived build, PDF and
    presentation state; a source repair never consumes it, so its change is a local review obligation
    (consulted). Its template views and every other read carry meaning a proposal may rest on (sources,
    evidence, plan, argument): consumed.
    """
    payload = payload if isinstance(payload, dict) else {}
    if operation == "document" and not payload.get("view"):
        return "consulted"
    # Coordination state (COORDINATION_READS and Work-object project views) is consulted, never consumed.
    if operation in COORDINATION_READS:
        return "consulted"
    if operation == "project" and payload.get("view") in WORK_COORDINATION_VIEWS:
        return "consulted"
    return "consumed"


def read_output_digest(operation: str, value: dict) -> str:
    """Digest the consulted substance of one read, excluding its own diagnostics.

    A source read is manuscript bytes and exact scope. Historical context-stale
    rows are controller diagnostics; adding a replacement context must not make
    unchanged source look edited. Other read owners retain their full digest.
    """
    if not isinstance(value,dict):
        return output_digest(value)
    if operation in {'concept','project_guidance','read_artifact','project'}:
        value=_engineering_read_substance(value)
    if operation == "project":
        return output_digest({key:item for key,item in value.items() if key != "review_read"})
    if operation == "literature_discover":
        # Discovery is navigation metadata, not consulted scientific evidence.
        # Public search availability and ordering can change between immediate
        # identical calls (for example a Crossref 200 followed by 429).  The
        # exact imported/bound source and later reference_text read remain
        # guarded separately; this receipt identifies only the query that led
        # the writer there.
        return output_digest({"kind": "literature-discovery",
                              "query": value.get("query"),
                              "metadata_only": bool(value.get("metadata_only"))})
    if operation == "repository":
        if "matches" in value or "repositories" in value:
            # File/search listings explicitly advertise themselves as
            # discovery. A new neighbouring file must not invalidate prose
            # based on exact files subsequently read through this same owner.
            return output_digest({"kind": "repository-discovery",
                                  "repository": value.get("repository"),
                                  "query": value.get("query"),
                                  "offset": value.get("offset")})
        source = value.get("source") or {}
        images = value.get("_image_content") or []
        return output_digest({"kind": "repository-source",
            "repository": value.get("repository"),
            "source": {key: source.get(key) for key in ("path", "bytes", "sha256")},
            "content": value.get("content"), "offset": value.get("offset"),
            "truncated": value.get("truncated"), "next_offset": value.get("next_offset"),
            "pdf_page": value.get("pdf_page"),
            "pdf_page_start": value.get("pdf_page_start"),
            "pdf_page_end": value.get("pdf_page_end"),
            "images": [{"mime_type": row.get("mime_type"),
                        "sha256": hashlib.sha256(str(row.get("data") or "").encode()).hexdigest()}
                       for row in images if isinstance(row,dict)]})
    def _content_only(value):
        """A read's digest is over its CONTENT, never over its identities.

        These branches exist to stop an unrelated global change invalidating a local read, so
        they already drop `revision` and the `authority.*_revision` stamps.  The `identities`
        block is the same thing in its proper form -- the token OF those stamps -- so it drops
        here too.  Caught by tests/test_project_structure.py::
        test_local_read_digests_ignore_only_incidental_global_revisions, which failed the moment
        the overview published the `plan` token and the digest absorbed it.
        """
        projected=dict(value)
        projected.pop("revision",None);projected.pop("structure_revision",None)
        projected.pop("identities",None)
        authority=dict(projected.get("authority") or {})
        for key in tuple(authority):
            if key.endswith("_revision"):authority.pop(key,None)
        if "authority" in projected:projected["authority"]=authority
        return projected
    if operation=="concept" and value.get("schema_version")=="laplace.concept-context/2":
        # The bounded read carries a node-local mutation identity. An unrelated
        # graph append changes only the global revision and must not invalidate
        # source work based on an unchanged selected concept.
        return output_digest({key:item for key,item in value.items()
                              if key not in ("revision","identities")})
    if operation=="research" and isinstance(value,dict) and "read_basis" in value:
        # `read_basis` says whether THIS response came from the research state cache (G16);
        # it is transport, not content: the same inputs digest the same whether served
        # from the witness cache or derived, so a cache hit never looks like a change.
        # `index_stamp` is the cache WITNESS identity (every consumed file and directory,
        # including the manuscript directory whose mtime moves with this door's own banked
        # rows); it is diagnostics beside the consulted substance, not substance.
        return output_digest({key:item for key,item in value.items() if key not in {"read_basis","index_stamp","consumption_basis"}})
    if (operation=="structure" and value.get("schema_version")
            =="laplace.project-structure-overview/1"):
        # The overview digest is the actual returned map, not an opaque global
        # stamp: object/section/gap/source changes remain present and hashed.
        return output_digest(_content_only(value))
    if (operation=="structure" and ("structure_revision" in value
            or value.get("schema_version")=="laplace.project-structure-guard/1")):
        # The guard projection is the detail read's edit guards over the same section: its
        # consulted substance is the section's authored content, never the tokens it carries.
        from laplace.manuscript.project_structure import semantic_content
        return output_digest(semantic_content(value))
    if operation == "read_artifact":
        # Human routing is presentation, not consumed artifact evidence. Keep
        # existing read receipts valid when only this origin-relative door is added.
        return output_digest({key:item for key,item in value.items()
                              if key not in {"human_read","link_instruction"}})
    if operation != "source":
        return output_digest(value)
    document=value.get("document") or {}
    def scoped(rows):
        return [{key:row.get(key) for key in
                 ("file","order","parent","include_line","line_start","line_end","text")}
                for row in rows or [] if isinstance(row,dict)]
    projected={"project":value.get("project"),
        "document":{key:document.get(key) for key in
                    ("root","manuscript_dir","edition","read_only","status")},
        "selection":value.get("selection"),"requested_selection":value.get("requested_selection"),
        "sources":scoped(value.get("sources")),"boundaries":scoped(value.get("boundaries")),
        "diagnostics":value.get("diagnostics") or []}
    return output_digest(projected)



RESEARCH_RECEIPT = "laplace.research-consumption-receipt/1"


def _consumption_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(",",":"),allow_nan=False).encode("utf-8")).hexdigest()


def _research_scope(project, payload, projection=None):
    return {"project":project,"operation":"research","payload":{k:v for k,v in payload.items() if k!="project"},
            "projection":projection}


def _research_substance(value, scope):
    from laplace.research.research_catalogue import summary_consumption
    if scope["payload"].get("view") != "summary" or value.get("project") != scope["project"]:
        raise ValueError("Research receipt scope differs")
    return _consumption_hash({"schema_version":RESEARCH_RECEIPT,"scope":scope,
                              "value":summary_consumption(value)})


def record_read_basis(operation, value, payload, *, project=None, projection=None):
    """One capture interpretation for all native read bankers, legacy digest retained.

    The raw JSON owner response remains complete, including per-read controls.
    Its hash and explicit scope/version are sealed. An unavailable new owner
    basis is recorded as unavailable, never silently treated as legacy.
    """
    fields={"output_sha256":read_output_digest(operation,value),
            "basis_index":read_basis_index(operation,value)}
    if operation != "research" or payload.get("view") != "summary":
        return fields
    raw=json.loads(json.dumps(value,ensure_ascii=False,allow_nan=False))
    scope=_research_scope(project or payload.get("project") or value.get("project"),payload,projection)
    descriptor={"schema_version":RESEARCH_RECEIPT,"scope":scope,
                "raw_sha256":_consumption_hash(raw),"status":"UNAVAILABLE"}
    try:
        descriptor.update(status="AVAILABLE",semantic_sha256=_research_substance(raw,scope))
    except (ValueError,TypeError,KeyError) as exc:
        descriptor["reason"]=str(exc)
    fields.update(consumption=descriptor,research_raw=raw)
    return fields


def comparison_digest(operation, value, read, *, root=None):
    """Replay in the SEALED receipt's version, never inferred from new owner data."""
    if "consumption" not in read:
        return read_output_digest(operation,value)
    desc=read["consumption"]
    if (operation!="research" or not isinstance(desc,dict)
            or desc.get("schema_version")!=RESEARCH_RECEIPT or desc.get("status")!="AVAILABLE"
            or not isinstance(desc.get("scope"),dict)
            or set(desc)!={"schema_version","scope","raw_sha256","status","semantic_sha256"}):
        raise ValueError("Unknown or unavailable Research consumption receipt")
    scope=_research_scope((read.get("payload") or {}).get("project") or desc["scope"].get("project"),
                         read.get("payload") or {},read.get("projection"))
    if desc["scope"]!=scope:
        raise ValueError("Research consumption scope changed")
    from laplace.representation import writing_bodies
    raw=writing_bodies.resolve_fields({"record":"writing-tool-read",
        "research_raw":read.get("research_raw")},root,strict=True).get("research_raw")
    if (not isinstance(raw,dict) or _consumption_hash(raw)!=desc["raw_sha256"]
            or _research_substance(raw,scope)!=desc["semantic_sha256"]
            or read_output_digest(operation,raw)!=read.get("output_sha256")):
        raise ValueError("Research raw custody or sealed substance changed")
    return _research_substance(value,scope)


def consumed_digest(read):
    desc=read.get("consumption")
    return desc.get("semantic_sha256") if isinstance(desc,dict) else read.get("output_sha256")


BASIS_INDEX_LIMIT = 160


BASIS_INDEX_BYTES = 6144   # the retained JSON budget of one receipt's selectors (custody threshold is 8192 for the row)


BASIS_COVERAGE_KEY = '__coverage__'


def _short(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:16]


def retained_bytes(value) -> int:
    """The size of a value in the domain the READ row is actually retained in: journal.bank_row
    serializes with json.dumps(ensure_ascii=False, default=str) and writes UTF-8, so a legal
    non-ASCII path (an 80-CJK-character chapter name is one 240-byte filename component) costs its
    encoded bytes, not its character count (Sol N2-utf8, 2026-10-14)."""
    return len(json.dumps(value, ensure_ascii=False, default=str).encode('utf-8'))


# the coverage marker is part of the retained index, so its widest shape (closed index at the entry
# cap with a twelve-digit omission count) is reserved before the first selector is admitted; the
# default json separators put two bytes (", ") between members
BASIS_MEMBER_SEPARATOR = 2


BASIS_COVERAGE_RESERVE = retained_bytes({BASIS_COVERAGE_KEY: {'complete': False, 'indexed': BASIS_INDEX_LIMIT, 'omitted': 10 ** 12 - 1,
                                                              'budget_bytes': BASIS_INDEX_BYTES, 'budget_entries': BASIS_INDEX_LIMIT}}) - 2 + BASIS_MEMBER_SEPARATOR


class _BasisIndex:
    """Exact selector keys (never truncated into another path or id) under an explicit retained
    byte and entry budget; the first selector that does not fit closes the index and every later
    one is counted as omitted, so coverage is declared, never implied (Sol N2, 2026-10-14).
    Bytes are counted in the retained serialization (UTF-8 of the ensure_ascii=False dump) and
    the whole value including the coverage marker fits BASIS_INDEX_BYTES."""
    def __init__(self):
        self.selectors = {}; self.bytes = 2; self.omitted = 0; self.closed = False; self.seen = 0
    def put(self, key, item):
        key = str(key); self.seen += 1
        if self.closed:
            self.omitted += 1; return
        value = _short(item)
        # the member's own bytes inside the braces plus the separator from the previous member
        cost = retained_bytes({key: value}) - 2 + (BASIS_MEMBER_SEPARATOR if self.selectors else 0)
        if key in self.selectors:
            self.omitted += 1; return   # a repeated exact selector is one selector; the first observation stands
        if len(self.selectors) >= BASIS_INDEX_LIMIT or self.bytes + cost + BASIS_COVERAGE_RESERVE > BASIS_INDEX_BYTES:
            self.closed = True; self.omitted += 1; return
        self.selectors[key] = value; self.bytes += cost
    def value(self):
        return {**self.selectors, BASIS_COVERAGE_KEY: {'complete': self.omitted == 0, 'indexed': len(self.selectors),
                'omitted': self.omitted, 'budget_bytes': BASIS_INDEX_BYTES, 'budget_entries': BASIS_INDEX_LIMIT}}


def basis_index_selectors(index) -> dict:
    return {key: value for key, value in (index or {}).items() if key != BASIS_COVERAGE_KEY} if isinstance(index, dict) else {}


def basis_index_coverage(index) -> dict:
    coverage = (index or {}).get(BASIS_COVERAGE_KEY) if isinstance(index, dict) else None
    if isinstance(coverage, dict):
        return coverage
    selectors = basis_index_selectors(index)
    return {'complete': bool(selectors), 'indexed': len(selectors), 'omitted': 0, 'legacy': True}


def read_basis_index(operation: str, value) -> dict:
    """A bounded index of the selectors a read published, retained on its receipt (2026-10-14).

    `output_sha256` says THAT a consulted read changed; this index says WHERE, so a stale
    refusal can name the changed figure, section, file or use and offer a bounded current
    read instead of a whole-domain replay. Keys are the exact selectors (a full path, spec id,
    section id or citation key); values are 16-hex prefixes of each selector's own content
    digest: diagnostics only, never a guard or a second token store. The index is closed at
    BASIS_INDEX_BYTES / BASIS_INDEX_LIMIT and carries its own coverage marker; a read with no
    natural selectors indexes its top-level fields.
    """
    if not isinstance(value, dict):
        return {}
    index = _BasisIndex(); put = index.put
    if operation == "visuals":
        rows = value.get("specs")
        rows = rows.get("items") if isinstance(rows, dict) else rows
        for spec in rows or []:
            if not isinstance(spec, dict) or not spec.get("id"):continue
            put("spec:" + str(spec["id"]), spec.get("spec_revision") or {k: v for k, v in spec.items() if k not in ("currentness", "placement_caption", "render", "render_freshness", "render_readiness")})
            if "currentness" in spec:put("currentness:" + str(spec["id"]), spec.get("currentness"))
            if "placement_caption" in spec or "placement" in spec:put("placement:" + str(spec["id"]), spec.get("placement_caption") or spec.get("placement"))
            if "render" in spec:put("render:" + str(spec["id"]), spec.get("render"))
        return index.value()
    if operation == "structure":
        from laplace.manuscript.project_structure import semantic_content
        sections = value.get("sections")
        sections = sections.get("items") if isinstance(sections, dict) else sections
        for section in sections or []:
            if isinstance(section, dict) and section.get("id"):put("section:" + str(section["id"]), semantic_content(section))
        if value.get("schema_version") == "laplace.project-structure-guard/1":
            transition = value.get("reader_transition") or {}
            if transition:put("contract:" + str(value.get("section_id")), transition.get("revision"))
            for row in ((value.get("paragraph_plan") or {}).get("paragraphs") or {}).get("items") or []:
                if isinstance(row, dict) and row.get("paragraph_id"):put("paragraph:" + str(row["paragraph_id"]), {k: row.get(k) for k in ("function", "proposition", "input_currentness")})
            paragraph = value.get("paragraph")
            if isinstance(paragraph, dict) and paragraph.get("paragraph_id"):put("paragraph:" + str(paragraph["paragraph_id"]), paragraph.get("subject_revision"))
        for key in ("gaps", "evidence", "edges", "logical_objects", "spine", "source_outline", "unplaced_nodes"):
            if key in value:put(key, semantic_content(value[key]))
        return index.value()
    if operation == "document":
        for row in value.get("files") or []:
            if isinstance(row, dict) and row.get("file"):put("file:" + str(row["file"]), row.get("expected_source_digest") or row)
        for key in ("selected_source", "current_build", "template", "dependency_revisions", "style_preview", "pdf_identity"):
            if key in value:put(key, value[key])
        return index.value()
    if operation == "literature_uses":
        for row in value.get("uses") or []:
            if isinstance(row, dict) and (row.get("key") or row.get("citekey")):
                put("use:" + str(row.get("key") or row.get("citekey")) + ("|" + str(row["claim_id"]) if row.get("claim_id") else ""), row)
        for key in ("source_claims", "claim_sources", "source_revision", "unassociated_uses"):
            if key in value:put(key, value[key])
        return index.value()
    if operation == "repository":
        source = value.get("source") or {}
        if source.get("path"):put("source:" + str(source["path"]), source.get("sha256") or source)
        if "content" in value:put("content", value.get("content"))
        if "matches" in value:put("matches", value.get("matches"))
        return index.value()
    for key, item in value.items():
        if key in ("read_receipt", "revision", "identities", "structure_revision", "human_read", "link_instruction"):continue
        put(key, item)
    return index.value()


def basis_changes(recorded, current) -> dict | None:
    """Which recorded selectors moved between a consumed read and its current replay, with the
    coverage of both indexes stated: a change can lie outside the indexed selectors, and the
    receipt's output hash (not this diff) is what refused the application."""
    selectors = basis_index_selectors(recorded)
    if not selectors or not isinstance(current, dict):
        return None
    now = basis_index_selectors(current)
    changed = sorted(key for key in selectors if key in now and selectors[key] != now[key])
    removed = sorted(key for key in selectors if key not in now)
    added = sorted(key for key in now if key not in selectors)
    recorded_coverage = basis_index_coverage(recorded); current_coverage = basis_index_coverage(current)
    complete = bool(recorded_coverage.get('complete')) and bool(current_coverage.get('complete'))
    attributed = bool(changed or removed or added)
    return {"changed": changed[:12], "removed": removed[:12], "added": added[:12],
            "unchanged": sum(1 for key in selectors if now.get(key) == selectors[key]),
            "omitted": max(0, len(changed) - 12) + max(0, len(removed) - 12) + max(0, len(added) - 12),
            "coverage": {"recorded": recorded_coverage, "current": current_coverage, "complete": complete},
            "attributed": attributed,
            "outside_coverage": not attributed or not complete,
            "note": ("every indexed selector is current; the change lies in a field this index does not cover, so only the exact consulted read shows it"
                     if not attributed else
                     "the index is partial on at least one side; changes outside its coverage are possible, so the exact consulted read remains the authority"
                     if not complete else "the named selectors moved; the exact consulted read remains the authority")}


def bounded_inspect_reads(operation: str, payload: dict, changes: dict | None) -> list:
    """Bounded current reads for the changed selectors: inspection, never witness renewal.

    Only the exact consulted read (next_reads) renews a consumed witness; these reads let a
    caller see what moved before deciding whether its proposal still holds. Keys are exact
    selectors, so the read names the recorded file, spec or section, never a prefix of it. A
    change outside the index's coverage has no bounded read: the truthful fallback is the exact
    consulted read itself, which the refusal already lists.
    """
    if not changes:
        return []
    keys = [key for key in (changes.get("changed") or []) + (changes.get("removed") or []) + (changes.get("added") or [])]
    reads = []
    def add(read):
        if read not in reads and len(reads) < 6:reads.append(read)
    for key in keys:
        kind, _, ident = key.partition(":")
        if operation == "visuals" and ident and kind in ("spec", "currentness", "placement", "render"):
            add({"operation": "visuals", "payload": {"id": ident}})
        elif operation == "structure" and ident and kind in ("section", "contract"):
            add({"operation": "structure", "payload": {"view": "detail", "section_ids": [ident], "projection": "guard"}})
        elif operation == "structure" and ident and kind == "paragraph" and isinstance(payload, dict) and payload.get("section_ids"):
            add({"operation": "structure", "payload": {"view": "detail", "section_ids": list(payload["section_ids"])[:1], "projection": "guard", "subject": "paragraph", "paragraph_id": ident}})
        elif operation == "document" and ident and kind == "file":
            add({"operation": "source", "payload": {"files": [ident]}})
        elif operation == "literature_uses" and ident and kind == "use":
            add({"operation": "literature_uses", "payload": {"key": ident.split("|", 1)[0], "limit": 10, "citation_limit": 10}})
    if operation == "visuals" and not reads and keys:
        add({"operation": "visuals", "payload": {"view": "index"}})
    if operation == "structure" and not reads and keys:
        add({"operation": "structure", "payload": {"view": "summary"}})
    return reads


def stale_evidence_message(changed: list) -> str:
    """One refusal naming EVERY stale consulted family, not the first one found."""
    families = list(dict.fromkeys(str(row.get("operation")) for row in changed))
    count = len(changed)
    return ("Consulted project evidence changed (" + ", ".join(families) + "). "
            + ("%d consulted reads are no longer current; " % count if count > 1 else "")
            + "consumed_read_recovery names each changed read, its changed selectors and bounded inspect reads. Request a fresh proposal.")


def stale_evidence_families(message: str) -> list:
    import re
    match = re.search(r"Consulted project evidence changed \(([^)]+)\)", str(message or ""))
    return [part.strip() for part in match.group(1).split(",") if part.strip()] if match else []


ACTION_VIEWS = {
    "build": ["document", "manuscript"],
    "style": ["document", "presentation"], "export_pdf": ["document", "presentation"],
    "writing_style_change": ["writing_style", "manuscript"],
    "writing_style_profile_change": ["writing_style", "manuscript"],
    "profile_change": ["writing_style", "structure", "manuscript", "document", "history"],
    "project_guidance_change": ["project_guidance", "project"],
    "project_metadata_change": ["project"],
    "material_reference_change": ["project", "materials"],
    "chapter": ["manuscript", "document"], "section_change": ["manuscript", "structure", "document"],
    "framing": ["framing", "pipeline"],
    "argument": ["argument", "manuscript"], "apply_revision": ["manuscript", "document"],
    "proposal_supersede": ["history"],
    "task": ["project", "pipeline"],
    "work_review": ["project", "pipeline"],
    "workflow_definition_change": ["project"],
    "research_object_change": ["concepts", "research", "structure", "project"],
    "research_handover": ["materials", "project"],
    "development_source": ["project", "pipeline"], "work_delivery": ["project", "pipeline"],
    "task_status": ["project", "pipeline"], "concept_change": ["concepts", "structure", "pipeline"],
    "logical_plan_change": ["structure", "concepts", "pipeline"],
    "structure_change": ["structure", "manuscript", "pipeline"],
    "research_record": ["research", "pipeline"], "research_producer": ["research"],
    "experiment_run": ["research"], "run_cancel": ["research"],
    "visual_create": ["visuals", "presentation"],
    "visual_render": ["visuals", "presentation"], "visual_place": ["visuals", "manuscript"],
    "reference_fetch": ["references", "research", "pipeline"],
    "reference_text": ["references", "research"],
    "literature_import": ["references", "research", "manuscript", "pipeline"], "literature_bind": ["references", "concepts", "research", "structure", "pipeline"],
    "reference_attach": ["references", "research", "manuscript", "pipeline"], "reference_update": ["references", "research", "manuscript", "concepts", "structure", "pipeline"],
    "research_reconcile": ["research", "proofs", "visuals"],
    "reference_refresh": ["references", "research", "concepts", "structure", "pipeline"], "proof_check": ["proofs", "research", "structure"],
    "note": ["corrections", "manuscript"], "note_status": ["corrections", "manuscript"],
    "store_artifact": ["research", "artifact"],
}


#: ACTION-LEVEL EFFECT (causal correction J-R5, 2026-10-20): an operation in WRITES whose named action only reads.
#: `effect(operation, payload)` is the one classification every consumer asks (operations._admit_operation for the
#: review-role permit, writing_tools for baselines/receipts/replay/compaction, writing_operating for the role table,
#: the help's `acts`); no consumer keeps its own list.
ACTION_READS = {"research_handover": frozenset({"read", "request", "inspect"}), "development_source": frozenset({"read", "status"}), "work_delivery": frozenset({"status", "route-status", "review-setup", "renew-request", "workflow-preview", "workflow-status", "workflow-bind-request", "workflow-request", "workflow-compose-start", "workflow-impact-preview"})}


def effect(operation: str, payload=None) -> str:
    """'read' or 'write' for this exact call: WRITES operations with a read-only action are reads."""
    if operation in READS:
        return "read"
    actions = ACTION_READS.get(operation)
    if actions and isinstance(payload, dict) and payload.get("action") in actions:
        return "read"
    return "write"


#: views a write MAY affect beyond ACTION_VIEWS, and consulted reads a write never invalidates
ACTION_POTENTIAL_VIEWS = {"literature_bind": {"manuscript"},
                           "concept_change":{"references","structure","research","proofs"},
                           "structure_change":{"concepts","research"}}
ACTION_EXCLUDED_READS = {"reference_fetch": {"reference_text"},
                          "concept_change":{"reference_text"},
                          # A launch records a job, not a completed scientific
                          # result. Currentness begins with explicit run_status
                          # and research_record reads after completion.
                          "experiment_run":{"research","concept","literature_scope"}}

