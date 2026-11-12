"""Project guidance with explicit instructional and documentary roles.

``manuscript.working_guides`` remains the canonical configuration owner. A
legacy string means an instructional guide. New entries may be
``{"path": "CURRENT.md", "role": "handoff"}``, which keeps a changing handoff
discoverable without silently making it current operating authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROLES = {"instructions", "handoff", "background"}
MAX_GUIDES = 4
MAX_BYTES = 24_000


def _digest(value) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":")).encode()).hexdigest()


def _base(project: str, root: Path):
    from laplace.pipeline import registry
    record = registry.resolve(project, repo_root=root)
    base = record.path(record.project_dir or record.manuscript_dir, root) if record else None
    if base is None:
        raise ValueError("A project working guide requires an explicit local project path")
    return base.resolve()


def _entries(project: str, root: Path) -> list[dict[str, str]]:
    from laplace.pipeline import projection_spec
    spec = projection_spec.load_spec(project, root) or {}
    values = (spec.get("manuscript") or {}).get("working_guides", [])
    if not isinstance(values, list) or len(values) > MAX_GUIDES:
        raise ValueError(f"working_guides must name at most {MAX_GUIDES} project Markdown files")
    entries: list[dict[str, str]] = []
    for raw in values:
        if isinstance(raw, str):
            value = {"path": raw, "role": "instructions"}
        elif isinstance(raw, dict):
            if set(raw) - {"path", "role"}:
                raise ValueError("A working guide entry contains unknown fields")
            value = {"path": raw.get("path"), "role": raw.get("role", "instructions")}
        else:
            raise ValueError("A working guide must be a path or a path/role object")
        path, role = value.get("path"), value.get("role")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("A project working guide requires an explicit local project path")
        if role not in ROLES:
            raise ValueError(f"Working guide role must be one of {sorted(ROLES)}")
        normalized = Path(path)
        if normalized.is_absolute() or ".." in normalized.parts or normalized.suffix.lower() != ".md":
            raise ValueError("A working guide must be a Markdown file inside its project")
        entries.append({"path": normalized.as_posix(), "role": role})
    if len({row["path"] for row in entries}) != len(entries):
        raise ValueError("working_guides must not repeat a path")
    return entries


def guide_paths(project: str, root: Path) -> set[str]:
    """Pure configured path inventory; never enter guide support during validation."""
    base = _base(project, root)
    return {(base / entry['path']).resolve().relative_to(root).as_posix()
            for entry in _entries(project, root)}


def support_for_path(project: str, path: Path, root: Path, *, content=None,
                     historical=False, read_context=None):
    """Demand-driven current guide support on the existing exact artifact reader.

    A saved artifact pin identifies historical bytes; it never renews the guide's
    engineering acceptance. Unconfigured and other-project files pay no support IO.
    """
    root=Path(root).resolve();path=Path(path).resolve()
    if path.suffix.lower() != '.md':return None
    try:
        base=_base(project,root)
        entry=next((entry for entry in _entries(project,root)
                    if (base/entry['path']).resolve()==path),None)
    except ValueError:return None
    if entry is None:return None
    if historical:
        return {'status':'HISTORICAL_ARTIFACT',
                'reason':'Recorded guide bytes do not acknowledge current engineering support.',
                'read_handle':{'operation':'project_guidance','payload':{'path':entry['path']}}}
    from laplace.research import engineering_support
    if content is None:content=path.read_text(encoding='utf-8')
    nodes=engineering_support.guide_nodes(content,project)
    if not nodes:return None
    return {'basis':'CURRENT_GUIDE_ENGINEERING_SUPPORT',
            **engineering_support.guide_support(project,nodes,root,read_context=read_context)}


def _document(base: Path, entry: dict[str, str], *, include_body: bool, contents=None) -> dict:
    path = (base / entry["path"]).resolve()
    if not path.is_relative_to(base) or path.suffix.lower() != ".md":
        raise ValueError("A working guide must be a Markdown file inside its project")
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError(f"Working guide missing or larger than 24 KB: {entry['path']}")
    content = path.read_text(encoding="utf-8")
    if contents is not None:contents[entry["path"]]=content
    result = {**entry, "sha256": hashlib.sha256(content.encode()).hexdigest(),
              "bytes": len(content.encode()), "read_operation": "project_guidance"}
    if include_body:
        result["content"] = content
    return result


def load(project: str, root: Path, *, read_context=None) -> dict:
    """Load identities for all guides and bodies only for operating instructions.

    ``revision`` names content that was actually injected into a writer context.
    ``catalog_revision`` names the whole configured guide catalogue. Therefore a
    handoff update is observable without invalidating a context that never read it.
    """
    root = Path(root).resolve()
    entries = _entries(project, root)
    documents = []
    read_context = {} if read_context is None else read_context
    if entries:
        base = _base(project, root)
        contents=read_context.setdefault(("guide-contents",str(root),project),{})
        documents = [_document(base, entry, include_body=entry["role"] == "instructions",contents=contents)
                     for entry in entries]
        from laplace.research import engineering_support
        for document in documents:
            nodes=engineering_support.guide_nodes(contents[document['path']],project)
            if nodes and document['role']=='instructions':
                document['engineering_support']=engineering_support.guide_support(
                    project,nodes,root,read_context=read_context)
            elif nodes:
                document['engineering_support_read']={'operation':'project_guidance',
                    'payload':{'path':document['path']}}
    instruction_identity = [
        {key: row[key] for key in ("path", "role", "sha256")}
        for row in documents if row["role"] == "instructions"
    ]
    catalog_identity = [
        {key: row[key] for key in ("path", "role", "sha256")}
        for row in documents
    ]
    return {
        "documents": documents,
        "revision": _digest(instruction_identity),
        "catalog_revision": _digest(catalog_identity),
        "status": "LOADED" if documents else "UNCONFIGURED",
        "semantics": {
            "revision": "instruction bodies supplied to the writing session",
            "catalog_revision": "all configured guide identities, including handoff/background",
        },
    }


def read(project: str, payload: dict, root: Path) -> dict:
    """Read one configured guide exactly; omitted path discovers identities."""
    read_context={}
    state = load(project, root,read_context=read_context)
    requested = payload.get("path")
    if requested in (None, ""):
        return {**state, "documents": [
            {key: value for key, value in row.items() if key != "content"}
            for row in state["documents"]
        ]}
    if not isinstance(requested, str):
        raise ValueError("project_guidance path must be a configured Markdown path")
    document = next((row for row in state["documents"] if row["path"] == requested), None)
    if document is None:
        raise ValueError("project_guidance can read only a configured working guide")
    root=Path(root).resolve()
    content=read_context[('guide-contents',str(root),project)][document['path']]
    support=document.get('engineering_support')
    if support is None:
        support=support_for_path(project,_base(project,root)/document['path'],root,
                                 content=content,read_context=read_context)
    return {'project':project,**document,'content':content,
            'catalog_revision':state['catalog_revision'],
            **({'engineering_support':support} if support is not None else {})}


def _parse_configured_guides(project: str, guides, root: Path) -> list[dict[str, str]]:
    if not isinstance(guides, list) or len(guides) > MAX_GUIDES:
        raise ValueError(f"guides must contain at most {MAX_GUIDES} entries")
    parsed = []
    for raw in guides:
        if isinstance(raw, str):
            entry = {"path": raw, "role": "instructions"}
        elif isinstance(raw, dict) and not (set(raw) - {"path", "role"}):
            entry = {"path": raw.get("path"), "role": raw.get("role", "instructions")}
        else:
            raise ValueError("A working guide must be a path or a path/role object")
        if not isinstance(entry["path"], str) or entry["role"] not in ROLES:
            raise ValueError("A working guide requires a path and valid role")
        rel = Path(entry["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() != ".md":
            raise ValueError("A working guide must be a Markdown file inside its project")
        normalized = {"path": rel.as_posix(), "role": entry["role"]}
        _document(_base(project, root), normalized, include_body=False)
        parsed.append(normalized)
    if len({row["path"] for row in parsed}) != len(parsed):
        raise ValueError("working_guides must not repeat a path")
    return parsed


def change(project: str, payload: dict, root: Path) -> dict:
    """Configure guide roles or amend one configured body with exact guards."""
    from laplace.core import identity_doors
    identity_doors.admit_expected(payload, "project_guidance_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    from laplace.pipeline import projection_spec
    from filelock import FileLock
    import uuid

    root = Path(root).resolve()
    current = load(project, root)
    # `guide-catalogue` and `guide-instructions` are two homes ON PURPOSE (:80-85: a handoff
    # update must be observable without invalidating a context that never read it), and this
    # door compares the catalogue one.  Naming the home is what makes that deliberate pair
    # legible instead of looking like the twenty-name defect.
    from laplace.core import identity_doors
    identity_doors.gate("project_guidance_change", supplied=payload,
                        homes=[("guide-catalogue", project, current["catalog_revision"])],
                        required=["expected_catalog_revision"],
                        said="Project guidance changed; read project_guidance and retry")
    operation = payload.get("operation")
    if operation == "configure":
        parsed = _parse_configured_guides(project, payload.get("guides"), root)
        path = projection_spec.spec_path(project, root)
        if path is None:
            raise ValueError("Unknown project")

        def update(spec):
            live_guides = (spec.get("manuscript") or {}).get("working_guides", [])
            live_entries = _parse_configured_guides(project, live_guides, root)
            live_identity = []
            if live_entries:
                base = _base(project, root)
                live_identity = [
                    {key: row[key] for key in ("path", "role", "sha256")}
                    for row in (_document(base, entry, include_body=False)
                                for entry in live_entries)
                ]
            if _digest(live_identity) != payload.get("expected_catalog_revision"):
                raise ValueError("Project guidance changed; read project_guidance and retry")
            spec.setdefault("manuscript", {})["working_guides"] = parsed
            return spec

        projection_spec.update_file(path, update)
        return {**load(project, root), "operation_status": "CONFIGURED"}
    if operation == "write":
        requested = payload.get("path")
        document = next((row for row in current["documents"] if row["path"] == requested), None)
        if document is None:
            raise ValueError("write can amend only a configured project guide")
        content = payload.get("content")
        before = payload.get("before")
        if not isinstance(content, str) or len(content.encode()) > MAX_BYTES:
            raise ValueError("Project guidance content must be bounded UTF-8 text")
        target = (_base(project, root) / document["path"]).resolve()
        with FileLock(str(target) + ".lock", timeout=15):
            live = target.read_text(encoding="utf-8") if target.is_file() else None
            if live != before:
                raise ValueError("Project guidance changed; read its exact body and retry")
            pending = target.with_name(target.name + "." + uuid.uuid4().hex + ".pending")
            pending.write_text(content, encoding="utf-8")
            pending.replace(target)
        return {"status": "SAVED", "document": read(project, {"path": requested}, root),
                "project_protocol": load(project, root)}
    raise ValueError("project_guidance_change operation must be configure or write")
