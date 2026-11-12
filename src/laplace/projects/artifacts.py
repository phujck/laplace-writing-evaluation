"""Project text artifacts: exact scoped paths, current reads and guarded stores.

ART IDs name immutable journal receipts. Reading by ART resolves its current
physical path; recorded_revision remains historical. human_read pins actual
bytes. Historical body recovery remains author_history's record operation.
This owner does not admit roles or record tool reads/actions: writing.operations and writing_tools do.
Custody banking uses the records owner (writing.records.bank) only.
"""
from __future__ import annotations

from laplace.writing import records as writing_records

import hashlib
import copy
from pathlib import Path
import uuid
from urllib.parse import urlencode

def _artifact_context(root: Path, project: str) -> dict:
    from laplace.pipeline import registry
    from laplace.manuscript import manuscript_source
    proj = registry.resolve(project, repo_root=root)
    if proj is None:
        raise ValueError("Unknown project.")
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("read_only"):
        rel = source.get("storage_dir")
        if not rel:
            raise ValueError("This project has no writable research workspace.")
        path = (root / rel).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Research state directory escapes the active checkout.")
        return {"base":path,"source":source}
    path = proj.path(proj.project_dir or proj.manuscript_dir, root)
    if path is None or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Project workspace is outside the active checkout.")
    return {"base":path.resolve(),"source":source}


def _project_root(root: Path, project: str, *, context=None) -> Path:
    return (context if context is not None else _artifact_context(root,project))["base"]

def _artifact(root: Path, project: str, path: str, scope="project", *, context=None, allow_read_only=False) -> Path:
    context = context or _artifact_context(root,project)
    base = context["base"]
    if scope == "manuscript":
        source = context["source"]
        if source.get("read_only") and not allow_read_only:
            raise ValueError("The manuscript source is read-only; use project scope for research artifacts.")
        base = (root / source["manuscript_dir"]).resolve()
        if source.get("read_only"):
            # An internal read opt-in is not permission to follow a foreign or
            # escaped selection. Keep default/store resolution strictly above.
            selected = (root / source["root"]).resolve() if source.get("root") else None
            if (source.get("project") != project or source.get("foreign")
                    or source.get("status") != "resolved" or selected is None
                    or not base.is_relative_to(root.resolve())
                    or not selected.is_relative_to(base) or not selected.is_file()):
                raise ValueError("Read-only artifacts require an eligible selected manuscript inside this workspace.")
    elif scope != "project":
        raise ValueError("Artifact scope must be project or manuscript.")
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("Research artifacts belong inside the selected project.")
    target = (base / rel).resolve()
    if not target.is_relative_to(base):
        raise ValueError("Artifact path escapes the selected project.")
    canonical = {"authoring.json", "document_style.json", "figure_manifest.json",
                 "manuscript_spec.json", "projection_plan.json", "references.json",
                 "research_producers.json", "research_records.json"}
    if target.suffix.lower() in {".tex", ".bib"} or target.name in canonical:
        raise ValueError("Use the source, bibliography, or canonical-record operation for this file.")
    return target


_ARTIFACT_READ_DEFAULT = 16_000
_ARTIFACT_READ_MAX = 40_000
_ARTIFACT_TEXT_MAX = 2_000_000


def _artifact_revision(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def artifact_human_read(project: str, path: str, scope: str, revision: str, artifact_id: str | None = None) -> dict:
    """Canonical human route from owner coordinates, never a provider working directory."""
    import re
    if scope not in {'project','manuscript'} or not re.fullmatch(r'(?:sha256:)?[a-fA-F0-9]{64}',str(revision)):
        raise ValueError('A scoped artifact and complete byte identity are required for a human read.')
    pin=str(revision).removeprefix('sha256:').lower()
    params={'project':project,'scope':scope,'path':path,'expected_sha256':pin,'owner':'writing-artifact'}
    if artifact_id:params['artifact_id']=artifact_id
    url='/research/artifact?'+urlencode(params)
    return {'project':project,'path':path,'scope':scope,'expected_sha256':pin,'owner':'writing-artifact',
            **({'artifact_id':artifact_id} if artifact_id else {}),
            'url':url,'http':{'method':'GET','url':url}}


_ARTIFACT_LINK_GUIDANCE = ('Use human_read.url verbatim for user-facing Markdown links. '
    'Artifact paths are owner coordinates, not paths under the provider working directory. '
    'The link reads the pinned bytes; changed bytes remain an explicit refusal.')


def _artifact_record(root: Path, project: str, artifact_id: str) -> dict:
    """Resolve one exact store receipt without deriving a path from its ID."""
    if not artifact_id.startswith("ART-"):
        raise ValueError("Artifact id must be an exact ART-* id returned by store_artifact.")
    from laplace.writing.records import artifact_record as artifact_record
    try:
        row=artifact_record(root,project,artifact_id)
    except writing_records.AmbiguousRecord as exc:
        raise ValueError("Ambiguous artifact id. Use the exact scoped path from its original "
                         "read_handle; never infer a path from an ART id.") from exc
    if row is None:
        raise ValueError("Unknown artifact id. Use the exact read_handle returned by "
                         "store_artifact or read_artifact; never infer a path from an ART id.")
    return row


def reader_receipt(root: Path, project: str, artifact_id: str) -> dict:
    """Exact typed reader header from the existing index, without custody bodies.

    Domain reader owners need provenance to offer their inspector. Public source
    content cannot impersonate an owner by merely spelling its JSON schema.
    """
    with writing_records.index_lock:
        idx=writing_records.index(root)
        rows=[row for row in idx.by_id.get(artifact_id,()) if row.get('record')=='writing-artifact' and row.get('project')==project]
        if len(rows)!=1:raise ValueError('Exact artifact reader custody is unavailable or ambiguous.')
        writing_records.raw_indexed_record(idx,rows[0])
        marker=rows[0].get('reader_metadata') or {}
        return {key:copy.deepcopy(marker[key]) for key in ('schema_version','request_id','intent') if key in marker}


def _artifact_target(root: Path, project: str, payload: dict, *, context=None, record_lookup=None, allow_read_only=False) -> tuple[Path, str, str, dict | None]:
    artifact_id, supplied_path = payload.get("id"), payload.get("path")
    if bool(artifact_id) == bool(supplied_path):
        raise ValueError("read_artifact requires exactly one of path or id.")
    if supplied_path:
        scope = payload.get("scope", "project")
        artifact_path = str(supplied_path)
        return _artifact(root, project, artifact_path, scope, context=context, allow_read_only=allow_read_only), artifact_path, scope, None
    if not str(artifact_id).startswith("ART-"):
        raise ValueError("Artifact id must be an exact ART-* id returned by store_artifact.")
    record = record_lookup(str(artifact_id)) if record_lookup is not None else _artifact_record(root, project, str(artifact_id))
    if not isinstance(record,dict): raise ValueError("Unknown artifact id in this selected project.")
    scope, artifact_path = record.get("scope"), record.get("artifact_path")
    if isinstance(scope, str) and isinstance(artifact_path, str):
        return _artifact(root, project, artifact_path, scope, context=context, allow_read_only=allow_read_only), artifact_path, scope, record
    # Older receipts contain the exact repository-relative target but predate
    # scoped handles. Rebase that recorded path inside this project's root; the
    # ID itself is never interpreted as a filename.
    recorded = record.get("path")
    if not isinstance(recorded, str) or not recorded:
        raise ValueError("This artifact receipt predates scoped read handles and has no exact path. "
                         "Use read_artifact with the path and scope returned by its store receipt.")
    target = (root / recorded).resolve()
    context = context or _artifact_context(root,project)
    base = context["base"]
    if not target.is_relative_to(base):
        raise ValueError("The artifact receipt path is outside this selected project.")
    artifact_path = target.relative_to(base).as_posix()
    checked = _artifact(root, project, artifact_path, "project", context=context)
    if checked != target:
        raise ValueError("The artifact receipt path did not resolve to its selected project.")
    return target, artifact_path, "project", record


def _artifact_text(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Research artifacts must contain valid UTF-8 text.") from exc


def _artifact_chunk(raw: bytes, offset: int, limit: int) -> tuple[str, int]:
    if offset > len(raw):
        raise ValueError("read_artifact offset exceeds the current artifact size.")
    try:
        raw[:offset].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("read_artifact offset must be a returned UTF-8 byte boundary.") from exc
    end = min(len(raw), offset + limit)
    while end > offset:
        try:
            return raw[offset:end].decode("utf-8"), end
        except UnicodeDecodeError as exc:
            if exc.start < len(raw[offset:end]) - 4:
                raise ValueError("Research artifacts must contain valid UTF-8 text.") from exc
            end = offset + exc.start
    # A very small requested byte window can end inside the first code point.
    # Advance by that one complete character so the returned continuation
    # handle always makes progress (at most three bytes beyond the limit).
    for end in range(offset + 1, min(len(raw), offset + 4) + 1):
        try:
            return raw[offset:end].decode("utf-8"), end
        except UnicodeDecodeError:
            continue
    return "", offset


def _immutable_original(root,project,path,*,context=None):
    # A caller that already resolved this project's artifact context (the catalogue's one basis) reuses it.
    return path.resolve().is_relative_to((_project_root(root,project,context=context)/'.artifacts/originals').resolve())


def _bound_read_payload(project: str, payload) -> dict:
    """An artifact read's own controls without the door-bound project.

    writing.operations binds ``project`` into every admitted native payload; it names the custody this owner
    reads under, not a read control. The same project is transport, so a PDF reading pointer and its handles
    carry only exact id/path/scope/pin and selectors; another project is refused here rather than read under
    this project's custody.
    """
    if not isinstance(payload, dict):
        raise ValueError("read_artifact payload must be an object.")
    if "project" not in payload:
        return payload
    if payload["project"] != project:
        raise ValueError("This artifact read names another project; use that project's own exact read handle.")
    return {key: value for key, value in payload.items() if key != "project"}


def identity(root: Path, project: str, payload: dict) -> dict:
    """Scoped physical metadata without text decoding or PDF extraction."""
    payload = _bound_read_payload(project, payload)
    path, rel, scope, indexed = _artifact_target(root,project,payload,allow_read_only=True)
    if not path.is_file():raise ValueError('The owning artifact is absent.')
    from laplace.projects import writing_sources
    revision=writing_sources.file_revision(path)
    from laplace.core import source_pin
    source_pin.check(revision,payload)
    original=_immutable_original(root,project,path)
    if original:source_pin.check(revision,{'expected_sha256':path.stem})
    return {'id':indexed.get('id') if indexed else None,'artifact_path':rel,'scope':scope,
        'path':path.relative_to(root).as_posix(),'revision':revision,'size_bytes':path.stat().st_size,
        'media_type':'application/pdf' if path.suffix.lower()=='.pdf' else 'text/plain; charset=utf-8',
        **({'display_name':recorded_metadata(root,project,rel,scope).get('display_name')} if original else {}),
        'immutable':original,'exists':True}


def recorded_metadata(root,project,rel,scope='project'):
    """Existing captured ART metadata at this scoped path, without source extraction."""
    with writing_records.index_lock:
        idx=writing_records.index(root)
        rows=[row for row in idx.by_project.get(project,[]) if row.get('record')=='writing-artifact'
            and row.get('artifact_path')==rel and row.get('scope')==scope]
        return copy.deepcopy(rows[-1].get('original_metadata') or {}) if rows else {}


def _pdf_read(root,project,path,rel,scope,indexed,payload):
    from laplace.projects import material_intake, writing_sources
    from laplace.core import source_pin
    for key,minimum,maximum in [('offset',0,1_000_000_000),('limit',1,40_000),('page',1,1_000_000),('page_count',1,4)]:
        if key in payload and (type(payload[key])!=int or not minimum<=payload[key]<=maximum):raise ValueError('Invalid bounded PDF read controls.')
    if 'pointer' in payload:raise ValueError('PDF sources use pages, not JSON pointers.')
    # An absent or foreign-resolved PDF is a refusal at its exact recorded path, never an escaping OSError.
    if not path.is_file():raise ValueError('The owning artifact is absent at its exact recorded path.')
    if path.stat().st_size>16_000_000:raise ValueError('Artifact PDF reads are bounded to16000000bytes.')
    metadata=identity(root,project,payload);pin=metadata['revision']
    from laplace.research import literature
    selected={key:payload[key] for key in ('offset','limit','page','page_count','expected_sha256') if key in payload}
    selected['expected_sha256']=pin
    if payload.get('view','text') not in {'text','page'}:raise ValueError('Choose PDF text or page view.')
    base={'path':rel,'scope':scope,**({'id':indexed['id']} if indexed else {})}
    if indexed:base.pop('path');base.pop('scope')
    fields={**base,'page':payload.get('page',1),'page_count':payload.get('page_count',1),'limit':payload.get('limit',16000)}
    def handle(values):return material_intake.artifact_handle(project,values)
    result={**metadata,'recorded_revision':indexed.get('sha256') if indexed else None,
        'content':None,'read_only':True,'update_handle':None,'extraction_state':'UNAVAILABLE',
        **({'literature':literature.retained_capability(project,indexed['id'],pin,root)} if indexed and indexed.get('original_metadata') else {}),
        **({'material_read':material_intake.reading_context(root,project,indexed['id'],{key:payload[key] for key in ('offset','limit','page','page_count','view','expected_sha256') if key in payload})} if indexed else {}),
        'original_read':material_intake.artifact_handle(project,{'id':indexed['id'],'expected_sha256':pin},route='original') if indexed and indexed.get('original_metadata') else None,
        'page_read':handle({**fields,'offset':payload.get('offset',0),'expected_sha256':pin}),
        'restart_read':handle({**fields,'offset':0}),
        'human_read':material_intake.artifact_handle(project,{**base,'expected_sha256':pin})}
    try:
        observed=writing_sources.read_file(path,{'repository':'artifact','action':'view' if payload.get('view')=='page' else 'read',**selected})
        source_pin.check(observed['source']['sha256'],{'expected_sha256':pin})
        result.update({key:value for key,value in observed.items() if key not in {'repository','source','page_read','read_handle','restart_read','restart_read_semantics'}})
        result.update(source={'sha256':pin,'bytes':metadata['size_bytes'],'path':rel},extraction_state='RENDERED_PAGE' if payload.get('view')=='page' else 'TEXT_EXTRACTED')
        result['page_read']=handle({**fields,'offset':payload.get('offset',0),'expected_sha256':pin,**({'view':'page'} if payload.get('view')=='page' else {})})
        if result.get('next_offset') is not None:result['read_handle']=handle({**fields,'offset':result['next_offset'],'expected_sha256':pin})
        elif result.get('pdf_page_end',0)<result.get('pdf_total_pages',0) and payload.get('view')!='page':result['read_handle']=handle({**fields,'offset':0,'page':result['pdf_page_end']+1,'expected_sha256':pin})
        else:result['read_handle']=None
    except (ValueError,OSError) as exc:
        if isinstance(exc,source_pin.SourcePinRefusal):raise
        # Failure to extract/render does not invalidate the retained original.
        source_pin.check(writing_sources.file_revision(path),{'expected_sha256':pin})
        result.update(diagnostic=str(exc)[:1000],read_handle=None,extraction_state='UNAVAILABLE')
    return result


def read(root: Path, project: str, payload: dict) -> dict:
    payload = _bound_read_payload(project, payload)
    context = _artifact_context(root, project)
    path, artifact_path, scope, indexed = _artifact_target(root, project, payload,
        context=context, allow_read_only=True)
    source_read_only = scope == "manuscript" and bool(context["source"].get("read_only"))
    immutable = _immutable_original(root,project,path)
    if immutable and path.is_file():
        from laplace.core import source_pin
        from laplace.projects import writing_sources
        source_pin.check(writing_sources.file_revision(path),{'expected_sha256':path.stem})
    if path.suffix.lower()=='.pdf':return _pdf_read(root,project,path,artifact_path,scope,indexed,payload)
    if any(key in payload for key in ('page','page_count','view')):raise ValueError('Page controls select PDF artifacts only.')
    from laplace.manuscript.reader_plan import owns_path
    reader_owned = owns_path(project, root, path)
    owner_edit = {"read_only": True, "edit_read_handle": {"operation": "structure", "payload": {"view": "summary"}}} if reader_owned else ({"read_only": True} if source_read_only else {})
    from laplace.core import json_record, source_pin
    record = "pointer" in payload
    offset, limit = payload.get("offset", 0), payload.get("limit", json_record.POINTER_DEFAULT_LIMIT if record else _ARTIFACT_READ_DEFAULT)
    if (not isinstance(offset, int) or isinstance(offset, bool) or offset < 0
            or not isinstance(limit, int) or isinstance(limit, bool)
            or limit < 1 or limit > _ARTIFACT_READ_MAX):
        raise ValueError(f"read_artifact offset must be a non-negative byte offset and limit must be 1-{_ARTIFACT_READ_MAX}.")
    if not path.exists():
        source_pin.check(None, payload)
        if indexed:
            raise ValueError("The indexed artifact no longer exists at its exact recorded path.")
        read_handle = {"operation":"read_artifact","payload":{"path":artifact_path,"scope":scope}}
        return {"path":str(path.relative_to(root)),"artifact_path":artifact_path,"scope":scope,
                "exists":False,"content":None,"revision":None,"size_bytes":0,"offset":0,
                "next_offset":None,"complete":True,"read_handle":read_handle,
                "update_handle":None if reader_owned or immutable or source_read_only else {"operation":"store_artifact","payload":{"path":artifact_path,
                    "scope":scope,"before":None}}, **owner_edit}
    if not path.is_file():
        raise ValueError("The artifact path is not a regular file.")
    if path.stat().st_size > _ARTIFACT_TEXT_MAX:
        raise ValueError("read_artifact supports text artifacts up to 2 MB; inspect larger research data through the Research artifact reader or bounded repository reads.")
    # a record read requests at most the 2 MB cap + 1 bytes even if the artifact grows (repair1 R4)
    raw = json_record.read_capped(path, _ARTIFACT_TEXT_MAX) if record else path.read_bytes()
    if record:
        # ONE JSON value by RFC 6901 pointer from these admitted bytes (campaign bounded source
        # reading, 2026-10-14): character pages of that value, pinned to this revision; no update
        # proposal travels with a record page
        revision = _artifact_revision(raw)
        selected = json_record.page(raw, revision, {key: payload[key] for key in ("pointer", "offset", "limit", "expected_sha256") if key in payload})
        indexed_id = indexed.get("id") if indexed else None
        identity = ({"id": indexed_id} if indexed_id else {"path": artifact_path, "scope": scope})
        # repair1 R1: the human link opens THIS record page through the material reader's artifact
        # preview (the same artifact owner and fence), pinned to these bytes; restart_read is the
        # separate unpinned current read. The whole-file artifact route is not offered as the record.
        from laplace.projects import library as writing_projects
        controls = {"view": "preview", "target": {"owner": "artifact", "project": project, "path": artifact_path, "scope": scope},
                    "pointer": payload["pointer"], "offset": selected["offset"], "limit": selected["limit"]}
        record_read = writing_projects.material_read_handle(project, {**controls, "expected_sha256": "sha256:" + revision})
        return {"id": indexed_id, "recorded_id": indexed_id, "recorded_revision": indexed.get("sha256") if indexed else None,
                "path": str(path.relative_to(root)), "artifact_path": artifact_path, "scope": scope, "exists": True,
                "revision": revision, "current_revision": revision, "sha256": revision, "size_bytes": len(raw),
                "record_read": record_read, "human_read": record_read["human_read"],
                "page_read": {"operation": "read_artifact", "payload": {**identity, "pointer": payload["pointer"],
                    "offset": selected["offset"], "limit": selected["limit"], "expected_sha256": "sha256:" + revision}},
                "restart_read": writing_projects.material_read_handle(project, {**controls, "offset": 0}),
                "restart_read_semantics": writing_projects.RECORD_RESTART_SEMANTICS,
                "link_instruction": "Use human_read.url verbatim: it opens this record page under its source pin.", **selected, "complete": selected["next_offset"] is None,
                "read_handle": {"operation": "read_artifact", "payload": {**identity, "pointer": payload["pointer"],
                    **({"expected_sha256": "sha256:" + revision} if "expected_sha256" in payload else {}),
                    **({"offset": selected["next_offset"], "limit": selected["limit"], "expected_sha256": "sha256:" + revision}
                       if selected["next_offset"] is not None else {})}}, **owner_edit}
    revision = _artifact_revision(raw)
    source_pin.check(revision, payload)
    full_content = _artifact_text(raw)
    content, end = _artifact_chunk(raw, offset, limit)
    next_offset = None if end == len(raw) else end
    read_payload = {"path":artifact_path,"scope":scope,
                    **({"offset":next_offset,"limit":limit,"expected_sha256":"sha256:"+revision} if next_offset is not None else {}),
                    **({"expected_sha256":"sha256:"+revision} if "expected_sha256" in payload else {})}
    indexed_id = indexed.get("id") if indexed else None
    recorded_revision = indexed.get("sha256") if indexed else None
    update_payload = {"path":artifact_path,"scope":scope,"expected_revision":revision,
                      **({"artifact_id":indexed_id} if indexed_id else {})}
    from laplace.manuscript import project_protocol
    from laplace.projects import material_intake
    from laplace.research import literature
    support = (project_protocol.support_for_path(project,path,root,
                content=full_content,historical=bool(indexed),read_context={})
               if hasattr(project_protocol,"support_for_path") else None)
    return {"id":indexed_id,"recorded_id":indexed_id,"recorded_revision":recorded_revision,
            **({"engineering_support":support} if support is not None else {}),
            **({"custody_degradation":indexed["custody_degradation"]}
               if indexed and indexed.get("custody_degradation") else {}),
            "path":str(path.relative_to(root)),"artifact_path":artifact_path,"scope":scope,
            "exists":True,"content":content,"revision":revision,"current_revision":revision,
            "sha256":revision,"human_read":artifact_human_read(project,artifact_path,scope,revision,
                indexed_id if recorded_revision==revision else None),"link_instruction":_ARTIFACT_LINK_GUIDANCE,
            "size_bytes":len(raw),"offset":offset,"next_offset":next_offset,"read_only":immutable,
            **({"literature":literature.retained_capability(project,indexed_id,revision,root)} if indexed and indexed.get("original_metadata") else {}),
            **({"original_read":material_intake.artifact_handle(project,{"id":indexed_id,"expected_sha256":revision},route="original")} if indexed and indexed.get("original_metadata") else {}),
            "complete":next_offset is None,
            "read_handle":{"operation":"read_artifact","payload":read_payload},
            "page_read":{"operation":"read_artifact","payload":{"path":artifact_path,"scope":scope,
                "offset":offset,"limit":limit,"expected_sha256":"sha256:"+revision}},
            "restart_read":{"operation":"read_artifact","payload":{"path":artifact_path,"scope":scope,"offset":0,"limit":limit}},
            "update_handle":None if reader_owned or immutable or source_read_only else {"operation":"store_artifact","payload":update_payload},
            **({"material_read":material_intake.reading_context(root,project,indexed_id,{**{key:payload[key] for key in ("offset","limit") if key in payload},"expected_sha256":revision})} if indexed_id else {}), **owner_edit}


def store(root: Path, project: str, payload: dict, turn_id: str | None = None, *,
          owner_metadata: dict | None = None, publication_witness: dict | None = None) -> dict:
    from laplace.work import project_work
    with project_work.dispatch_lock(root):
        return _store(root,project,payload,turn_id,owner_metadata=owner_metadata,
            publication_witness=publication_witness)


def _store(root: Path, project: str, payload: dict, turn_id: str | None = None, *,
          owner_metadata: dict | None = None, publication_witness: dict | None = None) -> dict:
    path = _artifact(root, project, str(payload.get("path") or ""), payload.get("scope", "project"))
    if _immutable_original(root,project,path):
        raise ValueError('Retained originals are immutable; create an explicitly derived artifact at another path.')
    from laplace.manuscript.reader_plan import owns_path
    if owner_metadata is None and owns_path(project, root, path):
        raise ValueError('This authored reader-state artifact belongs to structure_change section_contract or paragraph_plan. Inspect structure detail and use its guarded edit_action.')
    scope, artifact_path = payload.get("scope", "project"), str(payload.get("path") or "")
    has_before, has_revision = "before" in payload, "expected_revision" in payload
    if has_before == has_revision:
        raise ValueError("store_artifact requires exactly one guard: before (null to create) or expected_revision from read_artifact.")
    supplied_before = payload.get("before")
    if has_before and supplied_before is not None and not isinstance(supplied_before, str):
        raise ValueError("store_artifact before must be exact text or null for creation.")
    expected_revision = payload.get("expected_revision")
    if has_revision and (not isinstance(expected_revision, str) or not expected_revision):
        raise ValueError("store_artifact expected_revision must be the exact revision returned by read_artifact.")
    source_artifact_id = payload.get("artifact_id")
    if source_artifact_id is not None:
        indexed_path, indexed_artifact_path, indexed_scope, _ = _artifact_target(
            root, project, {"id":source_artifact_id})
        if indexed_path != path or indexed_artifact_path != artifact_path or indexed_scope != scope:
            raise ValueError("store_artifact artifact_id does not identify this exact scoped path.")
    content = payload.get("content")
    if not isinstance(content, str) or len(content.encode("utf-8")) > 2_000_000:
        raise ValueError("Artifact content must be bounded text.")
    content_bytes = content.encode("utf-8")
    from laplace.writing import dispatch_parent
    dispatch_parent.validate_publication(root,project,path,content,turn_id)

    def guarded_current() -> tuple[bytes | None, str | None]:
        if path.exists() and not path.is_file():
            raise ValueError("The artifact path is not a regular file.")
        current_bytes = path.read_bytes() if path.is_file() else None
        current_text = _artifact_text(current_bytes) if current_bytes is not None else None
        if has_revision:
            if current_bytes is None or _artifact_revision(current_bytes) != expected_revision:
                raise ValueError("The artifact revision changed or no longer exists; nothing was written. Read its current revision before retrying.")
        elif current_text != supplied_before:
            raise ValueError("The artifact changed or already exists. Read its current contents or revision before revising it.")
        return current_bytes, current_text

    before_bytes, before = guarded_current()
    # A write-ahead record preserves the previous and intended text even if
    # the following atomic replace is interrupted.
    record = {"record": "writing-artifact", "id": "ART-" + uuid.uuid4().hex,
              "project": project, **({"turn_id":turn_id} if turn_id else {}), "path": str(path.relative_to(root)),
              "artifact_path": artifact_path, "scope": scope, "before": before,
              "before_sha256": _artifact_revision(before_bytes) if before_bytes is not None else None,
              "after": content, "reason": str(payload.get("reason") or ""),
              "sha256": _artifact_revision(content_bytes)}
    if owner_metadata is not None:
        # Typed domain callers supply bounded provenance; public payload cannot.
        record["reader_metadata"] = copy.deepcopy(owner_metadata)
    path.parent.mkdir(parents=True, exist_ok=True)
    from filelock import FileLock
    with FileLock(str(path) + ".lock"):
        current_bytes, current = guarded_current()
        if current_bytes != before_bytes:
            raise ValueError("A concurrent edit changed the artifact; nothing was written.")
        from laplace.writing import records as writing_records
        saved_record = writing_records.bank(Path(root), record)
        if publication_witness is not None:
            publication_witness.update(record_id=record["id"], banked=True)
        tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
        try:
            tmp.write_bytes(content_bytes)
            tmp.replace(path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise
        if publication_witness is not None:
            publication_witness["published"] = True
    from laplace.core import identity as core_identity, receipts as core_receipts
    owned_changes = core_receipts.bundle(
        files=[core_receipts.file_receipt(root,path,before_bytes,content_bytes)],
        views=["research","artifact"])
    read_handle = {"operation":"read_artifact","payload":{"id":record["id"]}}
    return {"id":record["id"],"saved":record["path"],"path":record["path"],
            "artifact_path":artifact_path,"scope":scope,"revision":record["sha256"],
            "record_id":record["id"],"read_handle":read_handle,"read_more":read_handle,
            "human_read":artifact_human_read(project,artifact_path,scope,record["sha256"],record["id"]),
            "link_instruction":_ARTIFACT_LINK_GUIDANCE,
            "update_handle":{"operation":"store_artifact","payload":{"path":artifact_path,
                "scope":scope,"expected_revision":record["sha256"],"artifact_id":record["id"]}},
            **({"custody_degradation":saved_record["custody_degradation"]}
               if saved_record.get("custody_degradation") else {}),
            "owned_changes":owned_changes,"effects":["research","artifact"]}



# Public owner entrypoints; compatibility callers use these same functions.
context = _artifact_context
project_root = _project_root
target = _artifact_target
record = _artifact_record
revision = _artifact_revision
text = _artifact_text
chunk = _artifact_chunk
resolve_path = _artifact
human_read = artifact_human_read


def _receipt_human_read(project: str, path: str, scope: str, pin, ident) -> dict:
    """{"human_read": ...} for an exact ART-* receipt with a complete pin, else {} (no partial route)."""
    try:
        return {"human_read": artifact_human_read(project, path, scope, pin, ident)} if ident else {}
    except ValueError:
        return {}


OPERATION_OWNERS = {"read_artifact": "read", "store_artifact": "store", "materials": "catalogue"}


def recover_workflow_publication(root, project, artifact_id, expected_revision, owner_metadata, *, admit, turn_id=None):
    """Explicit same-request recovery of one originally absent typed preparation ART.

    No new ART is banked. A later inverse/edit, foreign bytes or a changed request
    is a refusal, even if the path is now absent. This is not general restoration.

    turn_id is the private caller's actual acting turn. The reserved-path owner
    check (dispatch_parent.validate_publication) receives it exactly as store()
    did for the first publication, so a reserved research synthesis still needs
    the original parent session and the run owner's held exact-bytes scope.
    None keeps the earlier anonymous check, which every reserved path refuses.
    """
    from filelock import FileLock
    from laplace.work import project_work
    from laplace.writing import records
    from laplace.core import receipts
    root = Path(root).resolve()
    if owner_metadata.get('schema_version') != 'laplace.workflow-app-preparation/1':
        raise ValueError('Only exact typed workflow preparation publication can recover here.')
    with project_work.dispatch_lock(root):
        record = records.selected_journal_fields(project, artifact_id, root, fields=[
            'record', 'id', 'project', 'path', 'artifact_path', 'scope', 'before',
            'before_sha256', 'after', 'sha256', 'reader_metadata'])
        if (record.get('record') != 'writing-artifact' or record.get('project') != project
                or record.get('id') != artifact_id or record.get('scope') != 'project'
                or 'before' not in record or 'before_sha256' not in record
                or record.get('before') is not None or record.get('before_sha256') is not None
                or record.get('reader_metadata') != owner_metadata
                or record.get('sha256') != expected_revision or not isinstance(record.get('after'), str)):
            raise ValueError('Preparation ART custody or its originally absent preimage does not match.')
        raw = record['after'].encode('utf-8')
        if _artifact_revision(raw) != expected_revision:
            raise ValueError('Retained preparation ART bytes do not match their revision.')
        path = _artifact(root, project, record['artifact_path'], 'project')
        if path.relative_to(root).as_posix() != record['path']:
            raise ValueError('Preparation ART path changed.')
        latest = [row for row in records.index(root).by_project.get(project, [])
                  if row.get('record') == 'writing-artifact' and row.get('path') == record['path']]
        if not latest or latest[-1]['id'] != artifact_id:
            raise ValueError('A later artifact edit or inverse prevents publication recovery.')
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + '.lock'):
            admit()
            from laplace.writing import dispatch_parent
            dispatch_parent.validate_publication(root, project, path, record['after'], turn_id)
            before = path.read_bytes() if path.is_file() else None
            if path.exists() and not path.is_file() or before is not None and before != raw:
                raise ValueError('Different bytes occupy the retained preparation path.')
            if before is None:
                temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
                try:
                    temporary.write_bytes(raw)
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True)
    return {'id': artifact_id, 'revision': expected_revision, 'path': record['path'],
            'artifact_path': record['artifact_path'], 'scope': 'project',
            'read_handle': {'operation': 'read_artifact', 'payload': {'id': artifact_id}},
            'recovered': before is None,
            'owned_changes': receipts.bundle(files=[receipts.file_receipt(root, path, before, raw)], views=['artifact'])}


def restore_owned_absence(root, project, path, expected_revision, owner_metadata):
    """Restore an exact typed owner's originally absent artifact, with ART custody.

    This is deliberately not a public arbitrary-delete operation. The structural
    inverse caller proves the original absent preimage and pins the current ART.
    """
    from filelock import FileLock
    from laplace.work import project_work
    from laplace.core import identity as core_identity, receipts as core_receipts
    from laplace.writing import records as writing_records
    root=Path(root).resolve();path=Path(path).resolve();base=project_root(root,project)
    relative=path.relative_to(base).as_posix()
    if _artifact(root,project,relative,'project')!=path:
        raise ValueError('Typed absence restoration escapes its project artifact owner.')
    with project_work.dispatch_lock(root),FileLock(str(path)+'.lock'):
        before=path.read_bytes() if path.is_file() else None
        if before is None or _artifact_revision(before)!=expected_revision:
            raise ValueError('The exact inverse artifact preimage changed.')
        ident='ART-'+uuid.uuid4().hex
        writing_records.bank(root,{'record':'writing-artifact','id':ident,'project':project,
            'path':path.relative_to(root).as_posix(),'artifact_path':relative,'scope':'project',
            'before':_artifact_text(before),'before_sha256':_artifact_revision(before),
            'after':None,'sha256':None,'reason':'Exact structural inverse restores original artifact absence',
            'reader_metadata':copy.deepcopy(owner_metadata)})
        path.unlink()
    return {'id':ident,'owned_changes':core_receipts.bundle(
        files=[core_receipts.file_receipt(root,path,before,None)],views=['structure'])}


def declaration_sites(tool_source: str, owner_source: str) -> dict[str, dict]:
    """Resolve explicit adapters and their implementation, or refuse drift.

    Runtime help and route generation consume this same bounded declaration.
    Guards, comments, response projections and similarly named nearby calls are
    not dispatch sites. No authored operation or permission policy is inferred.
    """
    import ast
    door = ast.parse(tool_source)
    # S1 B8: the dispatch region is `_execute` and the `_execute_<family>` dispatchers that
    # immediately follow it (writing_declarations._dispatch_span reads the same region).
    functions = [node for node in door.body if isinstance(node, ast.FunctionDef)
                 and node.name == "_execute"]
    if len(functions) != 1:
        raise ValueError("Artifact adapters require one operations._execute owner.")
    region = list(functions)
    for node in door.body[door.body.index(functions[0]) + 1:]:
        if not (isinstance(node, ast.FunctionDef) and node.name.startswith("_execute_")):
            break
        region.append(node)
    implementation = ast.parse(owner_source)
    sites = {}
    for operation, name in OPERATION_OWNERS.items():
        hits = []
        for node in (inner for function in region for inner in ast.walk(function)):
            test = node.test if isinstance(node, ast.If) else None
            if not (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                    and test.left.id == "operation" and len(test.ops) == 1
                    and isinstance(test.ops[0], ast.Eq) and len(test.comparators) == 1
                    and isinstance(test.comparators[0], ast.Constant)
                    and test.comparators[0].value == operation):
                continue
            returns = [row for row in node.body if isinstance(row, ast.Return)]
            imports = [row for row in node.body if isinstance(row, ast.ImportFrom)
                       and row.module == 'laplace.projects' and row.level == 0
                       and len(row.names) == 1 and row.names[0].name == 'artifacts'
                       and row.names[0].asname is None]
            if len(returns) != 1 or len(imports) != 1:
                raise ValueError("Artifact adapter must return its declared owner directly: " + operation)
            call = returns[0].value
            expected = ["root", "project", "material_payload" if name == "catalogue" else "payload"] + (["turn_id"] if name == "store" else [])
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name) and call.func.value.id == "artifacts"
                    and call.func.attr == name and not call.keywords
                    and [item.id if isinstance(item, ast.Name) else None for item in call.args] == expected):
                raise ValueError("Artifact adapter differs from its declared owner: " + operation)
            hits.append(node.lineno)
        owners = [node for node in implementation.body if isinstance(node, ast.FunctionDef)
                  and node.name == name]
        if len(hits) != 1 or len(owners) != 1:
            raise ValueError("Artifact adapter/implementation is missing or ambiguous: " + operation)
        sites[operation] = {"handler": "src/laplace/writing/operations.py:" + str(hits[0]),   # the one operation table
            "implementation": "src/laplace/projects/artifacts.py:" + str(owners[0].lineno),
            "owner": "artifacts." + name + "(" + ", ".join(expected) + ")",
            "how": "branch"}
    return sites


def catalogue(root: Path, project: str, payload: dict | None = None) -> dict:
    """Latest recorded receipt per scoped path, from one metadata-only cut.

    Discovery never resolves custody bodies. Path availability is checked, but
    recorded revisions are historical pins and do not assert current bytes.
    """
    from laplace.pipeline import registry
    from laplace.projects import material_intake
    from laplace.research import literature
    if registry.resolve(project, repo_root=root) is None:
        raise ValueError("Select a registered project.")
    payload = {} if payload is None else payload
    if not isinstance(payload, dict) or set(payload) - {"offset", "limit"}:
        raise ValueError("Material catalogue accepts only offset and limit.")
    offset, limit = payload.get("offset", 0), payload.get("limit", 20)
    if (isinstance(offset, bool) or not isinstance(offset, int) or offset < 0
            or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50):
        raise ValueError("Material pagination requires offset >= 0 and limit 1-50.")
    with writing_records.index_lock:
        cut = writing_records.index(root)
        rows = copy.deepcopy([row for row in cut.by_project.get(project, [])
                              if row.get("record") == "writing-artifact"])
    # Match the existing one-ID catalogue grain, including explicit ambiguous
    # ID gaps. The cut is detached before any source/path resolution.
    by_id = {}
    latest, gaps = {}, []
    for row in rows:
        ident = row.get("id")
        if not isinstance(ident,str) or not ident.startswith("ART-"):
            gaps.append({"id": ident, "reason": "Recorded artifact has no exact ART-* identity."})
            continue
        by_id.setdefault(ident, []).append(row)
    basis = _artifact_context(root, project) if by_id else None
    def lookup(ident):
        matches = by_id.get(ident, [])
        if len(matches) > 1:
            raise ValueError("Ambiguous artifact id. Use the exact scoped path from its original "
                             "read_handle; never infer a path from an ART id.")
        return matches[0] if matches else None
    for ident, occurrences in by_id.items():
        row = occurrences[-1]
        try:
            path, scoped, scope, _ = _artifact_target(root, project, {"id": ident},
                context=basis, record_lookup=lookup, allow_read_only=True)
        except ValueError as exc:
            gaps.append({"id": ident, "reason": str(exc)})
            continue
        latest[(scope, scoped)] = {"id": ident, "path": scoped, "scope": scope,
            "recorded_revision": row.get("sha256"), "recorded_at": row.get("ts"),
            "history_path": row.get("path"),
            "availability": "present" if path.is_file() else "missing",
            "currentness": "NOT_CHECKED",
            "read_handle": {"operation": "read_artifact", "payload": {"id": ident}},
            # the canonical human route of this exact receipt (owner, artifact id, scope and pin), the
            # same one read_artifact issues; consumers open it instead of rebuilding a path URL
            **_receipt_human_read(project, scoped, scope, row.get("sha256"), ident),
            "update_handle": None if _immutable_original(root,project,path,context=basis) or (scope == "manuscript" and basis["source"].get("read_only")) else {"operation": "store_artifact", "requires": "Read current revision first."},
            **({'literature':literature.retained_capability(project,ident,row['sha256'],root),'media_type':row['original_metadata']['media_type'],'display_name':row['original_metadata'].get('display_name'),'read_only':True,
                'original_read':material_intake.artifact_handle(project,{'id':ident,'expected_sha256':row['sha256']},route='original'),
                'text_read':material_intake.artifact_handle(project,{'id':ident,'expected_sha256':row['sha256']})} if row.get('original_metadata') else {})}
    materials = sorted(latest.values(), key=lambda row: (row["scope"], row["path"]))
    return {"project": project, "materials": materials[offset:offset + limit],
        "pagination": {"offset": offset, "limit": limit, "total": len(materials),
            "next_offset": offset + limit if offset + limit < len(materials) else None},
        "gaps": gaps[:20], "gaps_total": len(gaps),
        "coverage": "Latest recorded artifact receipt per scoped path; unrecorded files are not included. Recorded revisions are not currentness checks.",
        "read_only": True}


def evidence_descriptor(root, project, reference):
    """Exact owner-issued evidence coordinate and read, without body hydration.

    The composing Work owner admits its actual caller before calling this. This
    helper resolves only the supplied owner coordinate; no alternate scope probe.
    """
    if not isinstance(reference,dict) or set(reference)-{'id','path','scope','expected_sha256'}:
        raise ValueError('Choose one exact artifact evidence reference.')
    if bool(reference.get('id'))==bool(reference.get('path')):
        raise ValueError('Choose an artifact id or explicit scoped path, exclusively.')
    if reference.get('id') and 'scope' in reference or reference.get('path') and 'scope' not in reference:
        raise ValueError('Artifact scope comes from its receipt or explicit path, not a fallback.')
    from laplace.core import source_pin
    pin=str(reference.get('expected_sha256','')).removeprefix('sha256:')
    import re
    if not re.fullmatch('[0-9a-f]{64}',pin):raise ValueError('Evidence requires an exact byte pin.')
    target,rel,scope,record=_artifact_target(Path(root),project,{k:v for k,v in reference.items() if k!='expected_sha256'},allow_read_only=True)
    if record and record.get('sha256') and str(record['sha256']).removeprefix('sha256:')!=pin:
        raise ValueError('Evidence pin differs from the exact artifact receipt.')
    original=_immutable_original(Path(root),project,target)
    if original and target.stem!=pin:raise ValueError('Original artifact evidence pin differs from its immutable identity.')
    human=artifact_human_read(project,rel,scope,pin,(record or {}).get('id'))
    payload={'id':record['id']} if record else {'path':rel,'scope':scope}
    return {'project':project,'scope':scope,'path':rel,'artifact_id':(record or {}).get('id'),
            'expected_sha256':pin,'recorded_revision':(record or {}).get('sha256'),
            'read':{'operation':'read_artifact','payload':{**payload,'expected_sha256':pin},'http':human['http']},
            'historical_body':'NOT_ASSERTED','available':target.is_file()},target
