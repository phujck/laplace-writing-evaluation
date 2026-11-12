"""A thin, read-only activity projection for the writing workspace.

This module deliberately joins only records that already exist in their owner
stores.  It is not an event ledger and it never asks a provider to reconstruct
who did something.  The list is intentionally small; exact rows and byte
checks are loaded only through :func:`detail`.

Contract (consumers: workspace-history.mjs, the shell's open-target handler,
native ``author_history``)
  Source identity  a manuscript target carries ``repo_file`` (checkout path) with
                   ``binding`` BOUND when the producer knows the path (editor-save
                   VERSION.source_file, authoring anchors and journal file paths
                   that resolve under the checkout); a historical row that kept
                   only a basename carries ``file`` with ``binding`` UNPROVED and
                   consumers open its saved text instead of a guessed file.
  Comparisons      :func:`detail` delivers recorded source hunks one page at a
                   time (``comparison_offset``/``comparison_limit``, default
                   COMPARISON_PAGE) with ``comparisons_pagination`` {offset,
                   limit, total, next_offset, next_read}; :func:`record` (the
                   exact stored row, explicit demand) keeps every hunk.
  Currentness      the activity index is a stamp-cached fold (:func:`_indexed`);
                   detail re-reads only the one record's bytes and digests.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree
from laplace.projects import artifacts
from laplace.writing import records as writing_records

from datetime import datetime, timezone, timedelta
from functools import lru_cache
import copy
import hashlib, math
import json
import re
import threading
from urllib.parse import urlencode
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "laplace.activity-history/1"
DEFAULT_LIMIT = 20
MAX_LIMIT = 20
from laplace.writing.records._project import _TALK
from laplace.writing.records._project import _TALK_CACHE
from laplace.writing.records._project import _TALK_LOCK
from laplace.writing.records._project import _TALK_RELEVANT


HISTORICAL_SOURCE_SCHEMA = "laplace.historical-source/1"
HISTORICAL_SOURCE_MAX_BYTES = 2_000_000


def source_contract():
    return {
        "type": "object",
        "required": ["view", "kind", "version_id", "file"],
        "properties": {
            "view": {"const": "source"},
            "kind": {"enum": ["editor-save", "snapshot"]},
            "version_id": {"type": "string", "minLength": 1},
            "file": {"type": "string", "minLength": 1},
            "offset": {"type": "integer", "minimum": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100000},
            "expected_content_revision": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
        },
        "additionalProperties": False,
    }


def source_http_contract():
    schema = source_contract()
    schema["properties"].update(project={"type": "string"}, corpus={"type": "string"})
    schema["allOf"] = [{"anyOf": [{"required": ["project"]}, {"required": ["corpus"]}]}]
    return schema


def source_protocol():
    return {
        "input": source_contract(),
        "schema_version": HISTORICAL_SOURCE_SCHEMA,
        "limits": {
            "max_file_bytes": HISTORICAL_SOURCE_MAX_BYTES,
            "default_limit": 40000,
            "maximum_limit": 100000,
            "offset_units": "Unicode characters",
        },
        "response": {
            "type": "object",
            "required": [
                "schema_version",
                "project",
                "file",
                "content",
                "content_revision",
                "archive_identity",
                "read_only",
                "offset",
                "limit",
                "total_characters",
                "next_offset",
                "complete",
            ],
            "properties": {
                "schema_version": {"const": HISTORICAL_SOURCE_SCHEMA},
                "project": {"type": "string"},
                "file": {"type": "string"},
                "content": {"type": "string"},
                "content_revision": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
                "archive_identity": {"type": "object"},
                "read_only": {"const": True},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
                "total_characters": {"type": "integer"},
                "next_offset": {"type": ["integer", "null"]},
                "complete": {"type": "boolean"},
            },
        },
        "authority": "Historical bytes grant no selected-source or save authority. Snapshot pins are observed-only unless their existing owner can verify them.",
    }


def source_handle(
    project, kind, version_id, file, *, expected_content_revision=None, offset=0, limit=40000
):
    query = {
        "project": project,
        "view": "source",
        "kind": kind,
        "version_id": version_id,
        "file": file,
        "offset": offset,
        "limit": limit,
    }
    if expected_content_revision:
        query["expected_content_revision"] = expected_content_revision
    return {"method": "GET", "route": "/authoring/history", "query": query}


def source(project, payload, root=None):
    """Read one exact archived file, never through current-source admission."""
    from jsonschema import Draft202012Validator
    from laplace.pipeline import registry
    from laplace.manuscript import projection_viewer

    root = _root(root)
    values = {key: value for key, value in payload.items() if key != "project"}
    error = next(Draft202012Validator(source_contract()).iter_errors(values), None)
    if error:
        raise ValueError("Historical source request rejected: " + error.message)
    ctx = registry.project_context(project, root)
    if ctx is None or ctx.manuscript_dir is None:
        raise ValueError("Historical source project is unavailable.")
    version_id = values["version_id"]
    kind = values["kind"]
    if not projection_viewer._SEGMENT_RE.fullmatch(version_id) or version_id in {".", ".."}:
        raise ValueError("Historical version must be an exact owner version id.")
    requested = Path(values["file"])
    if requested.is_absolute() or ".." in requested.parts or requested.suffix != ".tex":
        raise ValueError("Historical file must be an exact project-owned TeX archive path.")
    requested = (root / requested).resolve()
    if not requested.is_relative_to(root):
        raise ValueError("Historical source escapes the checkout.")
    recorded = None
    if kind == "editor-save":
        store = ctx.storage_dir or ctx.manuscript_dir
        meta = projection_viewer.read_editor_save(
            store, version_id, repo_root=root, read_body=False
        )
        if (
            requested != meta["saved_file"]
            or requested.stat().st_size > HISTORICAL_SOURCE_MAX_BYTES
        ):
            raise ValueError(
                "Historical file does not match its exact saved occurrence or exceeds the 2 MB limit."
            )
        observed = projection_viewer.read_editor_save(store, version_id, repo_root=root)
        data = observed["data"]
        recorded = "sha256:" + observed["manifest"]["sha"]
        verification = "VERIFIED"
    else:
        parent = (ctx.manuscript_dir / "versions").resolve()
        archive = (parent / version_id).resolve()
        if (
            archive.parent != parent
            or not requested.is_relative_to(archive)
            or not archive.is_dir()
        ):
            raise ValueError("Historical snapshot path does not belong to this project/version.")
        manifest = _read_json(archive / "SNAPSHOT.json")
        if manifest and manifest.get("id") not in (None, version_id):
            raise ValueError("Snapshot manifest identity changed.")
        names = manifest.get("files") if isinstance(manifest, dict) else None
        allowed = (
            {str(value) for value in names if isinstance(value, str)}
            if isinstance(names, list)
            else {"main.tex", "whitepaper/main.tex"}
        )
        relative = requested.relative_to(archive).as_posix()
        if relative not in allowed or not requested.is_file():
            raise ValueError("Historical file is not recorded in this snapshot.")
        if requested.stat().st_size > HISTORICAL_SOURCE_MAX_BYTES:
            raise ValueError("Historical source exceeds the 2 MB exact-file limit.")
        data = requested.read_bytes()
        verification = "OBSERVED_ONLY"
    if len(data) > HISTORICAL_SOURCE_MAX_BYTES:
        raise ValueError("Historical source exceeds the 2 MB exact-file limit.")
    revision = "sha256:" + hashlib.sha256(data).hexdigest()
    if values.get("expected_content_revision") and values["expected_content_revision"] != revision:
        raise ValueError(
            "CHANGED_INPUT: historical source bytes changed since the inspected revision."
        )
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Historical source is not UTF-8 text; it was not rewritten or normalized."
        ) from exc
    offset = values.get("offset", 0)
    limit = values.get("limit", 40000)
    if offset > len(text):
        raise ValueError("Historical source offset is beyond this exact file.")
    end = min(len(text), offset + limit)
    next_offset = end if end < len(text) else None
    file = requested.relative_to(root).as_posix()
    handle = source_handle(
        project,
        kind,
        version_id,
        file,
        expected_content_revision=revision,
        offset=offset,
        limit=limit,
    )
    next_read = (
        source_handle(
            project,
            kind,
            version_id,
            file,
            expected_content_revision=revision,
            offset=next_offset,
            limit=limit,
        )
        if next_offset is not None
        else None
    )
    return {
        "schema_version": HISTORICAL_SOURCE_SCHEMA,
        "project": project,
        "file": file,
        "content": text[offset:end],
        "content_revision": revision,
        "archive_identity": {
            "kind": kind,
            "version_id": version_id,
            "file": file,
            "recorded_revision": recorded,
            "verification": verification,
        },
        "read_only": True,
        "offset": offset,
        "limit": limit,
        "total_characters": len(text),
        "next_offset": next_offset,
        "complete": next_offset is None,
        "read_handle": handle,
        "next_read": next_read,
        "native_read": {
            "operation": "author_history",
            "payload": {key: value for key, value in handle["query"].items() if key != "project"},
        },
        "verification_note": "Existing saved-occurrence pins verified."
        if recorded
        else "Snapshot bytes observed in this read; no independent per-file historical pin was available.",
    }

COMPARISON_PAGE=6   # recorded source hunks delivered per detail page (G4)


def activity_contract():
    """Only selectors this activity owner consumes; analytics has its own scope.

    An ``id`` read accepts ``comparison_offset``/``comparison_limit`` to page the
    recorded source comparisons of one record (default page of COMPARISON_PAGE).
    """
    names=('file','file_scope','node','claim','result_id','result','category','type','actor','provider',
           'model','operation','session_id','event_kind','day','from','to','outcome','row')
    properties={name:{'type':'string'} for name in names}
    properties.update(view={'const':'activity'},id={'type':'string','minLength':1},
        as_of={'type':['string','number']},offset={'type':'integer'},limit={'type':'integer'},
        comparison_offset={'type':'integer','minimum':0},comparison_limit={'type':'integer','minimum':1,'maximum':50})
    return {'type':'object','properties':properties,'additionalProperties':False,
        'allOf':[{'if':{'required':['id']},'then':{'propertyNames':{'enum':['view','id','comparison_offset','comparison_limit']}}},
                 {'if':{'anyOf':[{'required':['comparison_offset']},{'required':['comparison_limit']}]},'then':{'required':['id']}}]}


def validate_activity_query(payload):
    from jsonschema import Draft202012Validator
    if not isinstance(payload,Mapping):raise ValueError('Activity query must be an object.')
    value={key:item for key,item in payload.items() if key!='project'}
    error=next(Draft202012Validator(activity_contract()).iter_errors(value),None)
    if error:
        advice=(' Use author_history view=telemetry, projection=trace, scope=turn and exact turn_id for turn audit.'
                if 'turn_id' in value else '')
        raise ValueError('Activity query does not match its consumed selectors: '+error.message+advice)


def http_history_payload(query):
    """Retain query keys for owner admission; only decode declared numeric carriers."""
    value={key:(item[0] if isinstance(item,(list,tuple)) and item else item)
           for key,item in query.items() if key not in {'project','corpus'}}
    for key in ('offset','limit','comparison_offset','comparison_limit'):
        if key in value:value[key]=int(value[key])
    return value


def comparison_page(payload: Mapping[str, Any]) -> tuple[int, int]:
    """The comparison page one detail read asked for (defaults apply when absent)."""
    offset=int(payload.get('comparison_offset') or 0);limit=int(payload.get('comparison_limit') or COMPARISON_PAGE)
    return max(0,offset),max(1,min(50,limit))


def _paged_comparisons(project: str, ident: str, rows: list[dict[str, Any]], offset: int, limit: int) -> dict[str, Any]:
    """One page of recorded comparisons with the owner's continuation (same shape as Work paging)."""
    page=rows[offset:offset+limit];next_offset=offset+len(page) if offset+len(page)<len(rows) else None
    def read(start):
        payload={'view':'activity','id':ident,'comparison_offset':start,'comparison_limit':limit}
        return {'operation':'author_history','payload':payload,
                'http':{'method':'GET','url':'/authoring/history?'+urlencode({'project':project,**payload})}}
    return {'comparisons':page,'comparisons_pagination':{'offset':offset,'limit':limit,'total':len(rows),
            'next_offset':next_offset,'next_read':read(next_offset) if next_offset is not None else None}}


def activity_http_contract():
    schema=activity_contract()
    schema['properties'].update(project={'type':'string'},corpus={'type':'string'})
    schema['allOf'][0]['then']['propertyNames']['enum']+=['project','corpus']
    return schema


def _root(value: Path | str | None = None) -> Path:
    return Path(value).resolve() if value is not None else source_tree()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return []
    return rows


from laplace.writing.records._project import _walk_talk


from laplace.writing.records._project import _talk_file_identity


from laplace.writing.records._project import _scan_project_talk


from laplace.writing.records._project import _advance_project_talk


from laplace.writing.records._project import _talk_rows


def _stamp(row: Mapping[str, Any]) -> Any:
    """Return an owner-recorded time, never a read-time or filesystem inference."""
    for key in ("ts", "created", "created_at", "checked_at", "at", "timestamp"):
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _sort_time(value: Any) -> float:
    if not isinstance(value, (str,int,float)):
        return float("-inf")
    return _parsed_time(value)


@lru_cache(maxsize=8192, typed=True)
def _parsed_time(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else float("-inf")
    if not isinstance(value, str):
        return float("-inf")
    try:
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("-inf")


def _opaque(owner: str, ident: Any) -> str:
    return f"activity:{owner}:{ident}" if ident else f"activity:{owner}:unidentified"


def _actor(*, label: Any = None, provider: Any = None, model: Any = None,
           role: Any = None) -> dict[str, Any]:
    # Attribution remains explicitly unknown when the owner did not bank it.
    label = str(label).strip() if label not in (None, "") else None
    provider = str(provider).strip() if provider not in (None, "") else None
    model = str(model).strip() if model not in (None, "") else None
    if label:
        low = label.lower()
        if low in {"author", "human", "user"} or low.startswith("author:"):
            kind = "human"
        elif low.startswith(("eigen:", "agent:", "model:", "pipeline:")):
            kind = "agent"
        else:
            # A historical name such as "gerard" or "manual" does not safely
            # identify either a human or an agent without an explicit owner field.
            kind = "unknown"
    elif provider or model:
        kind = "agent"
    else:
        kind = "unknown"
    value: dict[str, Any] = {"label": label, "kind": kind}
    if provider:
        value["provider"] = provider
    if model:
        value["model"] = model
    if role not in (None, ""):
        value["role"] = str(role)
    return value


def _trim(value: Any, limit: int = 280) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _target(kind: str, *, ident: Any = None, label: Any = None, file: Any = None,
            line_start: Any = None, line_end: Any = None, correction_id: Any = None,
            repo_file: Any = None, binding: Any = None) -> dict[str, Any]:
    """One affected object.

    A manuscript target carries the ONE source identity every consumer matches on:
    ``repo_file`` (checkout-relative, the walk's ``src.repo_file``) with
    ``binding`` BOUND. A historical row that retained only a basename keeps it in
    ``file`` with ``binding`` UNPROVED, so no reader maps it onto a same-named file
    elsewhere; its saved text stays readable through the record.
    """
    out: dict[str, Any] = {"kind": kind}
    for key, value in (("id", ident), ("label", label), ("file", file), ("repo_file", repo_file),
                       ("line_start", line_start), ("line_end", line_end),
                       ("correction_id", correction_id), ("binding", binding)):
        if value not in (None, ""):
            out[key] = value
    return out


def _manuscript_target(root: Path | None, file: Any, *, repo_file: Any = None, **fields) -> dict[str, Any]:
    """A manuscript target bound to its checkout path.

    ``repo_file`` is the identity the PRODUCER banked (``review_surface`` retains the
    validated checkout-relative path on new correction rows): an authored identity binds
    as it was recorded. Without one, a ``file`` that is a real path under ``root`` binds;
    a bare historical name stays UNPROVED and is never guessed onto a same-named file.
    """
    authored = repo_file if isinstance(repo_file, str) and repo_file else None
    if authored is not None:
        parts = Path(authored).parts
        if Path(authored).is_absolute() or ".." in parts or not parts:
            authored = None
    if authored is not None:
        return _target("manuscript", file=file, repo_file=authored, binding="BOUND", **fields)
    repo_file = None
    if root is not None and isinstance(file, str) and file:
        base = Path(root).resolve()
        try:
            candidate = _within(base, file)
        except ValueError:
            candidate = None
        if candidate is not None and candidate.is_file():
            repo_file = candidate.relative_to(base).as_posix()
    return _target("manuscript", file=file, repo_file=repo_file,
                   binding="BOUND" if repo_file else ("UNPROVED" if file else None), **fields)


def _dedup_targets(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out, seen = [], set()
    for row in rows:
        key = json.dumps(row, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def _item(owner: str, ident: Any, category: str, row: Mapping[str, Any], *,
          actor: dict[str, Any], summary: str, status: Any = None,
          targets: Iterable[dict[str, Any]] = (), conversation: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value = {"id": _opaque(owner, ident), "owner": owner, "category": category,
             "at": _stamp(row), "actor": actor, "summary": _trim(summary),
             "status": str(status or row.get("status") or "recorded"),
             "targets": _dedup_targets(targets), "detail_available": True}
    if conversation and (conversation.get("session_id") or conversation.get("turn_id")):
        value["conversation"] = {key: conversation.get(key) for key in ("session_id", "turn_id")
                                 if conversation.get(key)}
    return value


def _files_from(value: Any) -> list[str]:
    """Extract explicitly named file targets without guessing paths from prose."""
    out: list[str] = []
    if isinstance(value, Mapping):
        for key in ("file", "path"):
            if isinstance(value.get(key), str) and value[key]:
                out.append(value[key])
        files = value.get("files")
        if isinstance(files, list):
            out.extend(str(item) for item in files if isinstance(item, str) and item)
        for key in ("edits", "hunks", "receipts", "owned_files", "outcome", "action_receipt", "output", "payload"):
            if isinstance(value.get(key), list):
                for item in value[key]:
                    out.extend(_files_from(item))
            elif isinstance(value.get(key), Mapping):
                out.extend(_files_from(value[key]))
        proposal = value.get("proposal")
        if isinstance(proposal, Mapping):
            out.extend(_files_from(proposal))
    return list(dict.fromkeys(out))


def _manuscript_dir(project: str, root: Path) -> Path | None:
    """Resolve the registered home without resolving or hashing a live source file."""
    from laplace.pipeline import registry
    record = registry.resolve(project, repo_root=root)
    if record is None or not record.manuscript_dir:
        return None
    directory = record.path(record.manuscript_dir, root)
    return directory.resolve() if directory is not None and directory.is_dir() else None


def _project_dir(project: str, root: Path) -> Path | None:
    from laplace.pipeline import registry
    record = registry.resolve(project, repo_root=root)
    if record is None or not record.project_dir:
        return None
    directory = record.path(record.project_dir, root)
    return directory.resolve() if directory is not None and directory.is_dir() else None


def _claims_from(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    out: list[str] = []
    for key in ("claim", "claim_id", "node", "node_id", "section_id", "result_id"):
        if isinstance(value.get(key), str) and value[key]:
            out.append(value[key])
    for key in ("develops", "evidence_refs", "references", "identities", "receipts"):
        for item in value.get(key) or []:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, Mapping) and item.get("id"):
                out.append(str(item["id"]))
    return list(dict.fromkeys(out))


def _research_label(project: str, root: Path, ident: Any) -> str | None:
    """Use a current owner label only as navigation text, never as historical fact."""
    manuscript = _manuscript_dir(project, root)
    payload = _read_json(manuscript / "research_records.json") if manuscript else None
    for row in (payload or {}).get("records") or []:
        if isinstance(row, Mapping) and str(row.get("id") or "") == str(ident):
            return _trim(row.get("title") or row.get("summary") or row.get("question") or "") or None
    return None


def _research_identity(project: str, root: Path, ident: str, revision: str | None) -> dict[str, Any]:
    """Find an exact current or retained research record by its typed revision."""
    manuscript = _manuscript_dir(project, root)
    payload = _read_json(manuscript / "research_records.json") if manuscript else None
    records = (payload or {}).get("records") or []
    current = next((row for row in records if isinstance(row, Mapping) and row.get("id") == ident), None)
    history = (payload or {}).get("history") or []
    retained = next((row.get("record") for row in reversed(history) if isinstance(row, Mapping)
                     and row.get("id") == ident and isinstance(row.get("record"), Mapping)
                     and (row.get("revision") == revision or row["record"].get("revision") == revision)), None)
    current_revision = current.get("revision") if isinstance(current, Mapping) else None
    if revision and current_revision == revision:
        return {"status": "current", "recorded": revision, "current": current_revision,
                "record": dict(current), "basis": "current research record exactly matches the recorded action revision"}
    if isinstance(retained, Mapping):
        return {"status": "current", "recorded": revision, "current": current_revision,
                "record": dict(retained), "basis": "owner-retained historical research record exactly matches the recorded action revision"}
    if current_revision:
        return {"status": "changed", "recorded": revision, "current": current_revision,
                "record": None, "basis": "current research record differs; no retained body with the recorded revision is available"}
    return {"status": "missing", "recorded": revision, "current": None, "record": None,
            "basis": "the action's research record is no longer available"}


def _literature_association(project: str, root: Path, key: str) -> dict[str, Any] | None:
    manuscript = _manuscript_dir(project, root)
    payload = _read_json(manuscript / "references.json") if manuscript else None
    row = next((item for item in (payload or {}).get("associations") or []
                if isinstance(item, Mapping) and item.get("key") == key), None)
    if not isinstance(row, Mapping):
        return None
    from laplace.research import references_surface
    revision = "sha256:" + references_surface._digest(dict(row))
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    return {"row": dict(row), "revision": revision,
            "title": metadata.get("title") or row.get("citekey") or key}


def _journal_targets(row: Mapping[str, Any], project: str, root: Path, *,
                     research_labels: Mapping[str, str] | None = None,
                     literature_labels: Mapping[str, str] | None = None,
                     artifact_context=None, artifact_records=None) -> list[dict[str, Any]]:
    """Turn a recorded operation into typed targets without promoting receipt IDs to claims."""
    operation = str(row.get("operation") or "")
    if operation in {"store_artifact", "read_artifact"}:
        # Artifact paths are project-scoped, whereas file history uses checkout
        # paths. Resolve the receipt/returned handle at its existing owner; do
        # not hydrate stored text or treat a note as a manuscript passage.
        outcome = row.get("outcome") if isinstance(row.get("outcome"), Mapping) else {}
        artifact = outcome.get("artifact") if isinstance(outcome.get("artifact"), Mapping) else {}
        ids = [artifact.get("id"), row.get("artifact_record_id")]
        ids.extend(value for value in outcome.get("receipts", [])
                   if isinstance(value, str) and value.startswith("ART-"))
        ids = list(dict.fromkeys(value for value in ids if value))
        if len(ids) > 1:
            return []  # A single-file operation has no unique recorded receipt target.
        ident = ids[0] if ids else None
        handle = ({"id": ident} if ident else
                  {"path": row.get("artifact_path"), "scope": row.get("artifact_scope")})
        if not ident and not (handle.get("path") and handle.get("scope")):
            return []  # Legacy metadata has no exact scoped target; keep its activity.
        try:
            lookup = None
            if artifact_records is not None:
                def lookup(key):
                    matches = artifact_records.get(key, [])
                    if len(matches)>1: raise ValueError("Ambiguous artifact receipt in selected project.")
                    return matches[0] if matches else None
            context = artifact_context() if artifact_context is not None else None
            path, scoped, scope, receipt = artifacts.target(root, project, handle, context=context, record_lookup=lookup, allow_read_only=True)
            file = path.relative_to(root).as_posix()
        except (ValueError, OSError):
            return []
        target = _target("artifact", ident=ident, file=file, label=scoped)
        target.update(artifact_path=scoped, scope=scope,
                      recorded_revision=(receipt or {}).get("sha256"),
                      availability="present" if path.is_file() else "missing",
                      # the receipt's canonical human route (owner, artifact id, scope, pin)
                      **artifacts._receipt_human_read(project, scoped, scope, (receipt or {}).get("sha256"), ident))
        return [target]
    if row.get("candidate_kind")=="profile-change" or row.get("decision")=="confirm-profile":
        from laplace.manuscript import profiles
        candidate=row.get("candidate_id") or (row.get("id") if row.get("record")=="writing-proposal" else None)
        version=row.get("candidate_version") or row.get("proposal_version") or row.get("proposal_instance_version")
        family=row.get("profile_family")
        if not family and candidate and version:
            index=writing_records.index(root)
            matches=[item for item in index.by_id.get(candidate,[]) if item.get("record")=="writing-proposal"
                and item.get("candidate_kind")=="profile-change" and index.project(item)==project
                and item.get("proposal_instance_version")==version]
            if len(matches)==1:family=matches[0].get("profile_family")
        if row.get("decision")=="confirm-profile":family="architecture"
        fields=({"view":"candidate","candidate_ref":{"id":candidate,"version":version}} if candidate and version
                else {"family":row.get("profile_family") or "architecture","scope":row.get("profile_scope") or "workspace"})
        target=_target("profile",ident=candidate or row.get("id"),label=(family.capitalize() if family else "Profile")+" preferences")
        target['read_handle']=profiles.handle(project,fields)
        return [target]
    targets = [_manuscript_target(root, file) for file in _files_from(row)]
    outcome = row.get("outcome") if isinstance(row.get("outcome"), Mapping) else {}
    if row.get("record") == "writing-application":
        for receipt in row.get("receipts") or []:
            if not isinstance(receipt, Mapping):
                continue
            version_id = receipt.get("version_id") or ((receipt.get("receipt") or {}).get("version_id") if isinstance(receipt.get("receipt"), Mapping) else None)
            if version_id:
                targets.append(_target("editor-save", ident=version_id, label="Banked post-application version"))
    if operation.startswith("concept"):
        targets.extend(_target("concept", ident=ident) for ident in _claims_from(row))
    elif operation.startswith("research"):
        ids = _claims_from(row) + _claims_from(outcome)
        # `research_record` banks its exact result identity in outcome.receipts.
        # These are result receipts in this operation, not generic concept IDs.
        ids.extend(str(value) for value in outcome.get("receipts") or [] if isinstance(value, str))
        targets.extend(_target("research", ident=ident,
                               label=(research_labels or {}).get(str(ident)) if research_labels is not None
                               else _research_label(project, root, ident))
                       for ident in dict.fromkeys(ids))
    elif operation.startswith("literature"):
        ids = _claims_from(row) + _claims_from(outcome)
        ids.extend(str(value) for value in outcome.get("identities") or [] if isinstance(value, str))
        targets.extend(_target("literature", ident=ident,
                               label=(literature_labels or {}).get(str(ident)) if literature_labels is not None
                               else (_literature_association(project, root, ident) or {}).get("title"))
                       for ident in dict.fromkeys(ids))
    elif operation in {"proof_check", "formal", "proofs", "proof_targets"}:
        result = row.get("result_id") or ((row.get("payload") or {}).get("result_id") if isinstance(row.get("payload"), Mapping) else None)
        targets.append(_target("formal", ident=result, label=operation))
        if result:
            targets.append(_target("research", ident=result))
    return _dedup_targets(targets)


def _application_actor(row: Mapping[str, Any], turn: Mapping[str, Any] | None) -> tuple[dict[str, Any], str]:
    recorded = row.get("actor")
    if isinstance(recorded, Mapping):
        return ({key: recorded.get(key) for key in ("label", "kind", "provider", "model", "role", "basis")
                 if recorded.get(key) not in (None, "")}, "recorded")
    origin = str(row.get("origin") or "")
    if origin == "manuscript-review":
        return _actor(label="author"), "inferred from explicit manuscript-review origin"
    if origin == "current-turn-tool":
        settings = (turn or {}).get("provider_settings") if isinstance((turn or {}).get("provider_settings"), Mapping) else {}
        return _actor(label="eigen:session", provider=settings.get("provider"), model=settings.get("model")), "inferred from explicit current-turn-tool origin"
    return _actor(), "legacy application attribution is ambiguous"


def _correction_items(project: str, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    manuscript = _manuscript_dir(project, root)
    if manuscript is None:
        return [], {}, ["authoring corrections are unavailable because the manuscript directory is unresolved"]
    # Reuse the owner's feedback fold directly, avoiding authoring.load/history's
    # source-context resolution.  Feedback author edits are canonical correction
    # history too; raw authoring.json alone would incorrectly hide them.
    from laplace.pipeline import authoring
    state = authoring._normalise(_read_json(manuscript / "authoring.json") or {}, project)
    state = authoring._with_feedback(state, manuscript / "feedback" / "feedback.jsonl")
    rows = state.get("corrections") if isinstance(state.get("corrections"), list) else []
    records: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("id"):
            continue
        ident = str(row["id"])
        records[ident] = dict(row)
        anchor = row.get("anchor") if isinstance(row.get("anchor"), Mapping) else {}
        source_edit = bool(row.get("applied") or row.get("before") is not None
                           or row.get("after") is not None or row.get("hunks"))
        # A new passage row carries the producer's verified checkout path (`anchor.repo_file`);
        # an older row without one binds or stays UNPROVED exactly as before.
        authored = anchor.get("repo_file")
        if source_edit:
            target = [_manuscript_target(root, anchor.get("file"), repo_file=authored, line_start=anchor.get("line_start"),
                                         line_end=anchor.get("line_end"), correction_id=ident,
                                         label=anchor.get("section") or anchor.get("section_id"))]
        else:
            # An anchored instruction is still a note.  Its manuscript anchor is
            # navigation only, and intentionally carries no correction ID because
            # there is no exact before/after source comparison to open.
            target = [_target("note", ident=ident, label=row.get("kind"))]
            if anchor.get("file"):
                target.append(_manuscript_target(root, anchor.get("file"), repo_file=authored, line_start=anchor.get("line_start"),
                                                 line_end=anchor.get("line_end"), label=anchor.get("section") or anchor.get("section_id")))
        category = "manuscript" if source_edit else "notes"
        items.append(_item("authoring", ident, category, row,
                           actor=_actor(label=row.get("by")), summary=row.get("text") or "Author correction",
                           status=row.get("status"), targets=target))
    return items, records, []


def _journal_items(project: str, root: Path, *,
                   talk_rows: list[dict[str, Any]] | None = None, selected: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    rows = talk_rows if talk_rows is not None else _talk_rows(root, project)
    sessions = {str(row.get("id")): row for row in rows if row.get("record") == "writing-session" and row.get("id")}
    turns = {str(row.get("id")): row for row in rows if row.get("record") == "writing-turn" and row.get("id")}
    # A dispatch's own turn-id -> dispatch-id(s) it launched, so the PARENT's turn (which
    # carries neither member: `authoring_surface.py` keeps the two rows that distinguish a
    # child deliberately off the parent's own row) is still findable by the dispatch it
    # launched, from data this fold already walks once.  S3 dispatch-pane's `row` filter below
    # reads this, not a second store.
    dispatch_of_turn: dict[str, set[str]] = {}
    for turn_row in turns.values():
        if turn_row.get("dispatch_id") and turn_row.get("parent_turn_id"):
            dispatch_of_turn.setdefault(str(turn_row["parent_turn_id"]), set()).add(str(turn_row["dispatch_id"]))
    manuscript=_manuscript_dir(project,root)
    research=_read_json(manuscript/"research_records.json") if manuscript and not selected else None
    research_labels={str(row.get("id")): _trim(row.get("title") or row.get("summary") or row.get("question") or "")
                     for row in (research or {}).get("records") or [] if isinstance(row,Mapping) and row.get("id")}
    references=_read_json(manuscript/"references.json") if manuscript and not selected else None
    literature_labels={str(row.get("key")): _trim(((row.get("metadata") or {}).get("title")
                       if isinstance(row.get("metadata"),Mapping) else None) or row.get("citekey") or row.get("key"))
                       for row in (references or {}).get("associations") or [] if isinstance(row,Mapping) and row.get("key")}
    artifact_records = {}
    for artifact in rows:
        if artifact.get('record')=='writing-artifact' and artifact.get('project')==project:
            artifact_records.setdefault(str(artifact.get('id')),[]).append(artifact)
    artifact_basis = []
    def artifact_context():
        if not artifact_basis:
            from laplace.projects.artifacts import context as _artifact_context
            artifact_basis.append(_artifact_context(root,project))
        return artifact_basis[0]
    records: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    relevant = {"writing-turn", "writing-reply", "writing-application", "writing-proposal-decision",
                "writing-tool-read", "writing-tool-action", "writing-tool-failure",
                "writing-native-file-change", "writing-proposal"}
    for row in rows:
        if row.get("record") not in relevant or not row.get("id"):
            continue
        turn = turns.get(str(row.get("turn_id"))) if row.get("turn_id") else (row if row.get("record") == "writing-turn" else None)
        session = sessions.get(str((turn or row).get("session_id")))
        belongs = row.get("project") == project or (turn or {}).get("project") == project or (session or {}).get("project") == project
        if not belongs:
            continue
        ident, kind = str(row["id"]), str(row["record"])
        records[ident] = dict(row)
        settings = (turn or {}).get("provider_settings") if isinstance((turn or {}).get("provider_settings"), Mapping) else {}
        # A turn's immutable provider settings win; session fields are used only for
        # rows before a turn exists, never to rewrite a past turn's attribution.
        provider = settings.get("provider") or row.get("provider") or ((session or {}).get("provider") if turn is None else None)
        model = settings.get("model") or row.get("model") or ((session or {}).get("model") if turn is None else None)
        actor_label = row.get("by") or row.get("actor") or row.get("source")
        executing = kind in {"writing-reply", "writing-tool-read", "writing-tool-action",
                             "writing-tool-failure", "writing-proposal"}
        actor = (_application_actor(row, turn)[0] if kind == "writing-application" else
                 _actor(label=actor_label, provider=provider if executing else None,
                        model=model if executing else None, role=(session or {}).get("role") if executing else None))
        if row.get("candidate_kind")=="profile-change" or row.get("decision")=="confirm-profile":
            recorded_actor=row.get("actor") or row.get("author")
            if isinstance(recorded_actor,Mapping): actor=_application_actor({"actor":recorded_actor},turn)[0]
            if actor.get("kind") in {"human","agent"}: actor.setdefault("label", "Author" if actor["kind"]=="human" else "Eigen")
        targets = _journal_targets(row, project, root, research_labels=None if selected else research_labels,
                                   literature_labels=None if selected else literature_labels,
                                   artifact_context=artifact_context,artifact_records=None if selected else artifact_records)
        conversation = {"session_id": (turn or row).get("session_id"), "turn_id": (turn or row).get("id") if kind == "writing-turn" else row.get("turn_id")}
        category, status, summary = "session", row.get("status") or "recorded", kind.replace("writing-", "").replace("-", " ")
        if kind == "writing-turn":
            summary = row.get("text") or "Writing request"
        elif kind == "writing-reply":
            summary = row.get("error") or row.get("text") or "Writing reply"
        elif kind == "writing-application":
            category = "manuscript"
            status = "applied" if row.get("complete") else "partial"
            _actor_value, attribution = _application_actor(row, turn)
            if _actor_value.get("kind") == "human":
                summary = "Author-approved revision"
            elif _actor_value.get("kind") == "agent":
                summary = "Agent-applied revision"
            else:
                summary = "Recorded revision application (attribution ambiguous)"
            if not row.get("complete"):
                summary = "Partial revision application"
        elif kind == "writing-proposal-decision":
            category, status, summary = "manuscript", row.get("decision") or status, "Proposal decision"
        elif kind == "writing-native-file-change":
            category, summary = "manuscript", f"Native file {row.get('kind') or 'change'}"
        elif kind in {"writing-tool-read", "writing-tool-action"}:
            operation = str(row.get("operation") or "action")
            category = ("research" if operation.startswith("research") else "literature" if operation.startswith("literature")
                        else "formal" if operation in {"proof_check", "proofs", "proof_targets", "formal"} else "session")
            action_labels = {"research_record": "Recorded research result", "proof_check": "Recorded formal proof check",
                             "source": "Read manuscript source", "apply_revision": "Applied manuscript revision"}
            summary = action_labels.get(operation, ("Tool read: " if kind=="writing-tool-read" else "Tool action: ") + operation.replace("_", " "))
            if operation == "literature_import":
                label = next((target.get("label") for target in targets
                              if target.get("kind") == "literature" and target.get("label")), None)
                if label:
                    summary = "Imported " + str(label)
        elif kind == "writing-tool-failure":
            summary, status = row.get("error") or "Writing tool failed", "failed"
        if row.get("candidate_kind")=="profile-change" or row.get("decision")=="confirm-profile":
            category="settings"
            summary=("Explicit author confirmation of structural preferences" if row.get("decision")=="confirm-profile" else
                     "Profile preference applied" if kind=="writing-application" and row.get("complete") else
                     "Profile application started" if kind=="writing-application" else
                     "Profile suggestion saved" if kind=="writing-proposal" else "Profile preference decision")
            if kind=="writing-application" and not row.get("complete"):status="recorded"
        item=_item("journal", ident, category, row, actor=actor, summary=summary,
                   status=status, targets=targets, conversation=conversation)
        if kind in {"writing-tool-read","writing-tool-action","writing-tool-failure"}:
            item.update(event_kind="tool-attempt",operation=str(row.get("operation") or "unknown"))
        # The dispatch(es) this row belongs to: its OWN dispatch_id (a child's turn, session,
        # reply or tool row -- every one of those already carries or inherits `turn`) union
        # the dispatch(es) its turn LAUNCHED (the parent's own activity).  A plain turn with
        # neither is untagged, exactly as before.
        row_dispatch=row.get("dispatch_id") or (turn or {}).get("dispatch_id")
        launched=dispatch_of_turn.get(str(conversation.get("turn_id") or ""),set())
        dispatch_ids=sorted({str(row_dispatch)} | launched) if row_dispatch else sorted(launched)
        if dispatch_ids:item["dispatch_ids"]=dispatch_ids
        items.append(item)
    return items, records, []


def _editor_save_items(project: str, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    from laplace.manuscript import manuscript_source
    manuscript = manuscript_source.storage_home(project, root)
    if manuscript is None:
        return [], {}, ["editor saves are unavailable because the manuscript directory is unresolved"]
    saves = manuscript / "editor_saves"
    records, items = {}, []
    for version in sorted(saves.iterdir(), key=lambda value: value.name, reverse=True) if saves.is_dir() else []:
        if not version.is_dir():
            continue
        row = _read_json(version / "VERSION.json")
        if not row or not row.get("version_id"):
            continue
        ident = str(row["version_id"])
        row = {**row, "_version_dir": str(version), "_manuscript_dir": str(manuscript)}
        records[ident] = row
        file = row.get("file")
        # VERSION.source_file is the checkout path the save was banked for; a legacy
        # save without it is a basename only and stays UNPROVED (G1).
        bound = row.get("source_file") if isinstance(row.get("source_file"), str) and row.get("source_file") else None
        items.append(_item("editor-save", ident, "manuscript", row,
                           actor=_actor(label=row.get("author")), summary=f"Saved {file or 'manuscript'}",
                           status="saved", targets=[_target("manuscript", file=file, repo_file=bound,
                                                            binding="BOUND" if bound else "UNPROVED")]))
    return items, records, []


def _snapshot_items(project: str, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    manuscript = _manuscript_dir(project, root)
    if manuscript is None:
        return [], {}, ["snapshots are unavailable because the manuscript directory is unresolved"]
    versions = manuscript / "versions"
    records, items = {}, []
    for version in sorted(versions.iterdir(), key=lambda value: value.name, reverse=True) if versions.is_dir() else []:
        if not version.is_dir():
            continue
        row = _read_json(version / "SNAPSHOT.json")
        if not row or not row.get("id"):
            continue
        ident = str(row["id"])
        row = {**row, "_version_dir": str(version), "_manuscript_dir": str(manuscript)}
        records[ident] = row
        targets = [_target("manuscript", file=file) for file in row.get("files") or [] if isinstance(file, str)]
        items.append(_item("snapshot", ident, "manuscript", row,
                           actor=_actor(label=row.get("by")), summary=row.get("label") or "Banked snapshot",
                           status="banked", targets=targets))
    return items, records, []


def _concept_items(project: str, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """List exact rewire deposits without reprojecting their historical network."""
    from laplace.research import corpus_ingest
    records, items = {}, []
    for row in corpus_ingest.rewire_list(root, project):
        if not isinstance(row, Mapping) or not row.get("id"):
            continue
        ident = str(row["id"])
        records[ident] = dict(row)
        node = row.get("node") or row.get("target")
        items.append(_item("concept", ident, "notes", row, actor=_actor(label=row.get("by")),
                           summary=row.get("narrative") or row.get("essence") or row.get("kind") or "Concept change",
                           status="recorded", targets=[_target("concept", ident=node, label=row.get("node_kind"))]))
    return items, records, []


def _research_items(project: str, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    manuscript = _manuscript_dir(project, root)
    payload = _read_json(manuscript / "research_records.json") if manuscript else None
    history = payload.get("history") if isinstance(payload, Mapping) and isinstance(payload.get("history"), list) else []
    records, items = {}, []
    # The owner retains at most 100 historical revisions.  Do not turn current
    # records into invented events when they carry no recorded event timestamp.
    for ordinal, event in enumerate(history[-100:]):
        if not isinstance(event, Mapping) or not event.get("id"):
            continue
        prior = event.get("record") if isinstance(event.get("record"), Mapping) else {}
        ident = f"{event['id']}@{event.get('revision') or ordinal}"
        row = {**event, "record": dict(prior)}
        records[ident] = row
        provenance = prior.get("provenance") if isinstance(prior.get("provenance"), Mapping) else {}
        event_time = {**row, "recorded_at": provenance.get("recorded_at") or row.get("archived_at")}
        items.append(_item("research", ident, "research", event_time,
                           actor=_actor(label=provenance.get("by")),
                           summary=prior.get("summary") or prior.get("question") or f"Archived research record {event['id']}",
                           status="archived", targets=[_target("research", ident=event["id"], label=prior.get("kind"))]))
    warnings = []
    if isinstance(payload, Mapping) and payload.get("history_dropped"):
        warnings.append(f"research owner previously dropped {payload['history_dropped']} retained-history rows")
    return items, records, warnings


def _formal_items(project: str, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    manuscript = _manuscript_dir(project, root)
    payload = _read_json(manuscript / "formal" / "check_receipts.json") if manuscript else None
    rows = payload.get("receipts") if isinstance(payload, Mapping) and isinstance(payload.get("receipts"), list) else []
    records, items = {}, []
    for row in rows[-100:]:
        if not isinstance(row, Mapping) or not row.get("id"):
            continue
        ident = str(row["id"])
        records[ident] = {**row, "_manuscript_dir": str(manuscript) if manuscript else ""}
        formal_target = _target("formal", ident=ident, file=row.get("file"), label=row.get("declaration"))
        formal_target["receipt_id"] = ident
        targets = [formal_target]
        concept = row.get("concept") if isinstance(row.get("concept"), Mapping) else {}
        result = row.get("result") if isinstance(row.get("result"), Mapping) else {}
        concept_id = concept.get("id") or row.get("concept_id") or row.get("claim_id")
        result_id = result.get("id") or row.get("result_id")
        if concept_id:
            formal_target["concept_id"] = concept_id
            formal_target["action_label"] = "Open formal check for this concept"
            targets.append(_target("concept", ident=concept_id))
        if result_id:
            targets.append(_target("research", ident=result_id))
        items.append(_item("formal", ident, "formal", row, actor=_actor(label=row.get("by")),
                           summary=f"Formal check: {row.get('declaration') or row.get('file') or ident}",
                           status=row.get("proof_status") or "recorded", targets=targets))
    return items, records, []


def _literature_items(project: str, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    manuscript = _manuscript_dir(project, root)
    payload = _read_json(manuscript / "references.json") if manuscript else None
    associations = payload.get("associations") if isinstance(payload, Mapping) and isinstance(payload.get("associations"), list) else []
    records, items = {}, []
    for association in associations:
        if not isinstance(association, Mapping):
            continue
        key = str(association.get("key") or association.get("canonical_id") or "")
        for ordinal, receipt in enumerate(association.get("reading_observations") or []):
            if not isinstance(receipt, Mapping) or not receipt.get("id"):
                continue
            ident = str(receipt["id"])
            records[ident] = {**receipt, "_reference_key": key}
            targets = [_target("literature", ident=key, label=association.get("citekey"))]
            if association.get("claim_id"):
                targets.append(_target("concept", ident=association["claim_id"]))
            # Existing reading receipts intentionally have no timestamp/actor.  Keep
            # that absence visible instead of borrowing association modification time.
            items.append(_item("literature", ident, "literature", receipt, actor=_actor(),
                               summary=receipt.get("observation") or f"Reading observation for {key or 'reference'}",
                               status="recorded", targets=targets))
    return items, records, []


#: Every path and directory the eight adapters of :func:`_fold` read, keyed by the
#: project.  OBSERVED, not assumed: ``evidence/WRITING_CONSOLIDATION_2026-10-03/wave1/
#: storage-latency/probes/history_sources.py`` wraps ``open`` and
#: ``Path.read_text``/``read_bytes`` for the duration of one ``_fold`` -- the FOLD, not
#: ``_all``, which on this tree is a cache lookup that opens nothing -- and prints the
#: paths it touched: 39 for the author's own ``synthetics-foundations``, 0 of them outside
#: what the stamp below can see.  ``tests/test_author_history_index.py`` re-runs that
#: observation and fails if a reader ever opens a path this list does not name, so the
#: derived index below cannot go quietly stale when an adapter grows a source.
def _source_paths(project: str, root: Path) -> tuple[list[Path], list[Path]]:
    """``(files, directories)`` the projection is derived from, for this project."""
    files = [root / _TALK, root / "registry_projects.json",
             # the same spelling corpus_ingest._rewire_path makes (:883-889)
             root / "corpus_friction" / f"{re.sub(r'[^a-z0-9_-]', '_', project)}.jsonl"]
    directories: list[Path] = []
    manuscript = _manuscript_dir(project, root)
    if manuscript is not None:
        files += [manuscript / "authoring.json",
                  manuscript / "feedback" / "feedback.jsonl",
                  manuscript / "references.json",
                  manuscript / "research_records.json",
                  manuscript / "formal" / "check_receipts.json"]
        directories += [manuscript / "editor_saves", manuscript / "versions"]
    from laplace.manuscript import manuscript_source
    storage = manuscript_source.storage_home(project, root)
    if storage is not None and storage != manuscript:
        directories.append(storage / "editor_saves")
    return files, directories


def _source_stamp(project: str, root: Path, *, talk_revision: int | None = None) -> tuple:
    """The identity of those sources as the filesystem states it: per file
    ``(name, mtime_ns, size)``; per listed directory the directory, each child, AND the
    entries inside each child -- because THAT is the level the adapters actually read:
    ``editor_saves/<save>/VERSION.json`` (:496) and ``versions/<snap>/SNAPSHOT.json``
    (:518).  A file rewritten in place two levels down moves neither its save directory's
    mtime nor its size, so a stamp that stopped at the immediate children would stand
    while the page it validated went stale, in silence.  (Today's writer happens to make
    each save directory fresh and whole -- ``projection_viewer.py:740-750`` -- and
    ``_prune_editor_saves`` removes whole directories, both of which move the parent; that
    is a property of one writer, not of the index, and the index does not rely on it.)
    ``tests/test_author_history_index.py::
    test_the_stamp_moves_when_a_file_the_fold_opens_is_rewritten_in_place`` asserts the
    property itself: rewrite any file the fold opens, same byte length, and the stamp
    moves.  A path that does not exist stamps as absent and stamps differently the moment
    it appears."""
    files, directories = _source_paths(project, root)
    def stamp(path: Path) -> tuple:
        try:
            info = path.stat()
        except OSError:
            return (path.name, None, None)
        return (path.name, info.st_mtime_ns, info.st_size)
    def entries(path: Path) -> list[Path]:
        try:
            return sorted(path.iterdir())
        except OSError:
            return []
    # The ledger is global, but the indexed fold is project-scoped. `_indexed`
    # advances its exact project projection before calling here, so its revision
    # replaces the global file mark. Direct diagnostic callers omit the revision
    # and still observe the physical file, as `_source_paths` promises.
    marks: list[tuple] = ([('talk-project-revision', talk_revision), *[stamp(path) for path in files[1:]]]
                          if talk_revision is not None else [stamp(path) for path in files])
    for directory in directories:
        marks.append(stamp(directory))
        for child in entries(directory):
            marks.append(stamp(child))
            if child.is_dir():
                marks.extend(stamp(inner) for inner in entries(child))
    return tuple(marks)


#: The derived index: the folded projection per ``(root, project)``, valid exactly while
#: its sources' stamp is unchanged.  IN MEMORY ONLY -- no file, no new store, nothing to
#: reconcile; a cold process rebuilds it from the owner stores it already reads.  It
#: exists because ``MAX_LIMIT = 20`` (:22) is clamped on every call (:900) while every
#: call re-folded the whole projection: 266 calls to walk the author's own record, 238 ms
#: each, 63.3 s (harness2/baseline/storage.json ``storage.history.real_ledger.paged``).
#: ``views`` memoises the filtered order per request shape, so paging is a slice.
#:
#: BOUNDED, in the same spirit as ``_VIEW_LIMIT`` and for the same reason: one entry
#: retains the whole fold -- 20.1 MiB for the author's own project, 101.8 MiB peak while
#: folding (``wave1/storage-latency/probes/fold_retention.py``) -- and the app is
#: long-running, so an index that never evicted would retain the fold of every project
#: whose history was ever read: 21 rows in ``registry_projects.json``, roughly 0.41 GiB
#: that the base tree retained none of.  ``_INDEX_LIMIT`` is the most recent (root,
#: project) pairs; an evicted entry is a refold on its next read, never a stale answer.
_ALL_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_INDEX_LIMIT = 3
_VIEW_LIMIT = 8


def _all(project: str, root: Path, *, talk_rows: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    """The folded projection, from the derived index when its sources have not moved.

    A caller that supplies ``talk_rows`` has its own read of the ledger and is served
    directly, uncached: the index's validity is defined by the files it stamped.
    """
    if talk_rows is not None:
        return _fold(project, root, talk_rows=talk_rows)
    return _indexed(project, root)["fold"]


def _indexed(project: str, root: Path) -> dict[str, Any]:
    """The cache entry for ``(root, project)``, refolded only when its stamp moved."""
    key = (str(root), project)
    with _TALK_LOCK:
        entry = _ALL_CACHE.pop(key, None)        # pop/insert == least-recently-read last
        talk = _advance_project_talk(root, project, entry.get("talk") if entry else None)
        _TALK_CACHE[key] = talk                  # observable alias; _ALL_CACHE owns eviction
        stamp = _source_stamp(project, root, talk_revision=talk["revision"])
        if entry is None or entry["stamp"] != stamp:
            entry = {"stamp": stamp, "talk": talk,
                     "fold": _fold(project, root, talk_rows=talk["rows"]), "views": {}}
        else:
            entry["talk"] = talk
        _ALL_CACHE[key] = entry
        while len(_ALL_CACHE) > _INDEX_LIMIT:
            evicted = next(iter(_ALL_CACHE))
            _ALL_CACHE.pop(evicted)
            _TALK_CACHE.pop(evicted, None)
        return entry


def _fold(project: str, root: Path, *, talk_rows: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]], list[str]]:
    adapters = (("authoring", "Author corrections", _correction_items),
                ("journal", "Writing activity", _journal_items),
                ("editor-save", "Banked editor saves", _editor_save_items),
                ("snapshot", "Banked manuscript snapshots", _snapshot_items),
                ("concept", "Concept rewire records", _concept_items),
                ("research", "Retained research revisions", _research_items),
                ("formal", "Formal check receipts", _formal_items),
                ("literature", "Reading observations", _literature_items))
    items: list[dict[str, Any]] = []
    records: dict[str, dict[str, Any]] = {}
    coverage, limitations = [], []
    for owner, label, reader in adapters:
        try:
            rows, source, warnings = (reader(project,root,talk_rows=talk_rows)
                                      if reader is _journal_items else reader(project, root))
            items.extend(rows)
            records[owner] = source
            omitted = 0
            for warning in warnings:
                words = str(warning).split()
                if "dropped" in words:
                    index = words.index("dropped")
                    if index + 1 < len(words):
                        try:
                            omitted += int(words[index + 1])
                        except ValueError:
                            pass
            coverage.append({"owner": owner, "label": label, "status": "available", "omitted": omitted})
            limitations.extend(warnings)
        except Exception as exc:  # a projection must degrade rather than hide other owners
            records[owner] = {}
            coverage.append({"owner": owner, "label": label, "status": "unavailable", "note": str(exc), "omitted": 0})
    # Connect only literal action receipt + typed revision matches.  No time/text
    # similarity grouping is permitted: two identical edits remain distinct work.
    research_rows = records.get("research", {})
    for item in items:
        if item.get("owner") != "journal":
            continue
        raw_id = item["id"].split(":", 2)[-1]
        action = records.get("journal", {}).get(raw_id) or {}
        if action.get("operation") != "research_record":
            continue
        outcome = action.get("outcome") if isinstance(action.get("outcome"), Mapping) else {}
        revision = (outcome.get("revisions") or {}).get("revision") if isinstance(outcome.get("revisions"), Mapping) else None
        linked = []
        for result_id in outcome.get("receipts") or []:
            for stored_id, archived in research_rows.items():
                prior = archived.get("record") if isinstance(archived, Mapping) and isinstance(archived.get("record"), Mapping) else {}
                if (str(archived.get("id") or "") == str(result_id)
                        and (archived.get("revision") == revision or prior.get("revision") == revision)):
                    target = _opaque("research", stored_id)
                    linked.append(target)
                    archive_item = next((row for row in items if row["id"] == target), None)
                    if archive_item is not None:
                        archive_item.setdefault("related_activity_ids", []).append(item["id"])
        if linked:
            item["related_activity_ids"] = list(dict.fromkeys(linked))
    items.sort(key=lambda row: (_sort_time(row.get("at")), row["id"]), reverse=True)
    return items, records, coverage, limitations


def _bound_repo_files(items: Iterable[Mapping[str, Any]]) -> frozenset[str]:
    """Every checkout path this project's history has BOUND a manuscript target to."""
    return frozenset(str(target.get("repo_file")) for row in items for target in (row.get("targets") or ())
                     if target.get("kind") == "manuscript" and target.get("binding") == "BOUND" and target.get("repo_file"))


def file_scope(project: str, root: Path | str | None, file: Any,
               items: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any] | None:
    """THE ONE RESOLUTION of a file query (M5-I1/R1): one qualified source coordinate.

    A manuscript target's identity is its BOUND ``repo_file`` (checkout-relative, the
    walk's ``src.repo_file``). A caller still asks with the spelling it has: the walk's
    qualified path, a manuscript-relative path from a source block or a plan heading,
    or the exact ``file`` a historical record retained. The query is resolved ONCE here
    to ONE checkout path, through the selected source (``manuscript_source.resolve``)
    and the identities this history has already bound:

    * a path under the selected source's directory is that path;
    * otherwise a path that is a known BOUND identity or a file of the checkout is a
      checkout path, and a path that is neither is the selected source's relative path
      (``manuscript_dir/<path>``); when both readings are proven the query is AMBIGUOUS
      and matches nothing, which the page states;
    * an absolute path or one with ``..`` is UNRESOLVED: no identity.

    ``_filter`` then matches a BOUND target by that one ``repo_file`` and nothing else
    (its recorded display name never widens or narrows a known identity), and an
    unbound (UNPROVED or legacy) target by its exact recorded name when that name is
    the resolved path or its selected-source-relative spelling. No basename equality,
    no row rewritten. The resolved ``repo_file`` is the continuation coordinate: a
    later page or another consumer that asks with it reaches the same identity even
    after the selection changed, because a known identity resolves to itself.
    """
    requested = str(file or "").strip()
    if not requested:
        return None
    base = _root(root)
    parts = PurePosixPath(requested).parts
    if not parts or PurePosixPath(requested).is_absolute() or ".." in parts:
        return {"file": requested, "repo_file": None, "relative": None, "resolution": "unresolved", "names": [requested]}
    if items is None:
        items = _indexed(project, base)["fold"][0]
    known = _bound_repo_files(items)
    from laplace.manuscript import manuscript_source
    directory = manuscript_source.resolve(project, base, include_candidates=False).get("manuscript_dir")
    prefix = directory.rstrip("/") + "/" if isinstance(directory, str) and directory not in ("", ".") else None
    proven = lambda path: path in known or (base / path).is_file()
    if prefix and requested.startswith(prefix):
        qualified, resolution = requested, "selected-source"
    else:
        joined = prefix + requested if prefix else None
        own, under = proven(requested), joined is not None and proven(joined)
        if own and under:
            return {"file": requested, "repo_file": None, "relative": None, "resolution": "ambiguous",
                    "candidates": [requested, joined], "names": []}
        if own or joined is None:
            qualified, resolution = requested, "checkout"
        else:
            qualified, resolution = joined, "selected-source"
    relative = qualified[len(prefix):] if prefix and qualified.startswith(prefix) else None
    return {"file": requested, "repo_file": qualified, "relative": relative, "resolution": resolution,
            "names": sorted({qualified, *([relative] if relative else [])})}


def _continuation(scope: Mapping[str, Any]) -> dict[str, Any] | None:
    """The exact next-read handle of a resolved file scope: the stable target and the recorded
    names the first page admitted, as one admitted query value (``file_scope``)."""
    if not scope.get("repo_file"):
        return None
    basis = {"repo_file": scope["repo_file"], "names": sorted(scope.get("names") or [scope["repo_file"]])}
    return {"file": scope["repo_file"], "file_scope": json.dumps(basis, sort_keys=True, separators=(",", ":"))}


def _safe_relative(value: Any) -> bool:
    parts = PurePosixPath(str(value)).parts
    return isinstance(value, str) and bool(value.strip()) and bool(parts) and not PurePosixPath(value).is_absolute() and ".." not in parts


def requested_file_scope(project: str, root: Path | str | None, payload: Mapping[str, Any],
                         items: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any] | None:
    """The file scope one request asks for: a first read resolves (``file_scope``), a
    continuation CARRIES the basis its first page returned (M5-R1 continuation).

    A continuation's membership predicate is the first page's, whole: the stable qualified
    target AND the recorded names that page admitted as historical evidence. It is carried
    in the request (``file_scope``, the value the owner itself returned under
    ``scope.continuation``), never re-resolved against the selection of the moment, so a
    later page under the same ``as_of`` neither skips nor repeats a row. A carried basis
    that is malformed, or that disagrees with the ``file`` asked beside it, is a changed
    basis and is refused before any offset is applied.
    """
    carried = str(payload.get("file_scope") or "").strip() if isinstance(payload.get("file_scope"), str) else payload.get("file_scope")
    if not carried:
        return file_scope(project, root, payload.get("file"), items)
    # THE COMMON ADMISSION (M5): a carried basis continues a file walk, so the file it continues must be asked
    # beside it. Without one the request is neither a project-wide read nor a scoped one, and it is refused here,
    # before any filter or slice, for every consumer (activity page, telemetry, native, HTTP) at once.
    if not str(payload.get("file") or "").strip():
        raise ValueError("file_scope continues a file walk and needs the file it continues beside it (the `file` the first page returned under scope.continuation); start a new read without file_scope for the whole project.")
    try:
        basis = json.loads(carried) if isinstance(carried, str) else None
    except ValueError:
        basis = None
    if (not isinstance(basis, Mapping) or not _safe_relative(basis.get("repo_file")) or not isinstance(basis.get("names"), list)
            or not basis["names"] or not all(_safe_relative(name) for name in basis["names"]) or basis["repo_file"] not in basis["names"]
            or set(basis) != {"repo_file", "names"}):
        raise ValueError("file_scope must be the continuation handle a first history page returned (its stable source and recorded names); continue with that handle.")
    requested = str(payload.get("file") or "").strip()
    if requested and requested != basis["repo_file"]:
        raise ValueError("file_scope continues %r but file asks for %r: the basis changed; continue with the handle the first page returned or start a new read without file_scope."
                         % (basis["repo_file"], requested))
    prefix_relative = None
    return {"file": requested or basis["repo_file"], "repo_file": basis["repo_file"], "relative": prefix_relative,
            "resolution": "continuation", "names": sorted(set(basis["names"]))}


def _file_match(target: Mapping[str, Any], scope: Mapping[str, Any]) -> bool:
    if target.get("binding") == "BOUND":   # a known identity is matched by its identity, never by its name
        return bool(scope.get("repo_file")) and str(target.get("repo_file") or "") == scope["repo_file"]
    return str(target.get("file") or "") in (scope.get("names") or ())


def _filter(items: Iterable[dict[str, Any]], payload: Mapping[str, Any], *,
            scope: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    category = str(payload.get("category") or payload.get("type") or "").strip()
    actor = str(payload.get("actor") or "").strip()
    file = str(payload.get("file") or "").strip()
    # A caller that resolved the file query through ``file_scope`` passes it; one that did
    # not asks for exactly that checkout path (BOUND) or exactly that recorded name.
    file_scope_ = scope if scope and scope.get("file") == file else (
        {"file": file, "repo_file": file, "relative": None, "resolution": "checkout", "names": [file]} if file else None)
    node = str(payload.get("node") or payload.get("claim") or "").strip()
    result = str(payload.get("result_id") or payload.get("result") or "").strip()
    day = str(payload.get("day") or "").strip()
    outcome = str(payload.get("outcome") or "").strip()
    provider = str(payload.get("provider") or "").strip()
    model = str(payload.get("model") or "").strip()
    event_kind = str(payload.get("event_kind") or "").strip()
    operation = str(payload.get("operation") or "").strip()
    session_id = str(payload.get("session_id") or "").strip()
    dispatch = str(payload.get("row") or "").strip()
    as_of = payload.get("as_of")
    cutoff = _sort_time(as_of) if as_of not in (None, "") else None
    start = _sort_time(payload.get("from")) if payload.get("from") not in (None, "") else None
    end = _sort_time(payload.get("to")) if payload.get("to") not in (None, "") else None
    out = []
    for row in items:
        if event_kind and row.get("event_kind") != event_kind:
            continue
        if operation and row.get("operation") != operation:
            continue
        if session_id and str((row.get("conversation") or {}).get("session_id") or "") != session_id:
            continue
        if dispatch and dispatch not in (row.get("dispatch_ids") or ()):
            continue
        if category and row.get("category") != category:
            continue
        if actor:
            recorded_actor = row.get("actor") or {}
            # The UI's actor chip is a kind (human/agent/unknown).  A caller that
            # supplies any other value is asking for the exact recorded label.
            actor_matches = (recorded_actor.get("kind") == actor if actor in {"human", "agent", "unknown"}
                             else str(recorded_actor.get("label") or "") == actor)
            if not actor_matches:
                continue
        targets = row.get("targets") or []
        if file_scope_ and not any(_file_match(target, file_scope_) for target in targets):
            continue
        if node and not any(str(target.get("id") or "") == node for target in targets):
            continue
        if result and not any(str(target.get("id") or "") == result for target in targets):
            continue
        if day and _day(row.get("at")) != day:
            continue
        if outcome and str(row.get("status") or "") != outcome:
            continue
        recorded_actor = row.get("actor") or {}
        if provider and str(recorded_actor.get("provider") or "") != provider:
            continue
        if model and str(recorded_actor.get("model") or "") != model:
            continue
        if start is not None and _sort_time(row.get("at")) < start:
            continue
        if end is not None and _sort_time(row.get("at")) >= end:
            continue
        # A row without an owner-recorded date remains in an explicit tail.  It
        # cannot be ordered by a date cutoff, but hiding it would falsely imply
        # there was no activity; callers receive a limitation below.
        if cutoff is not None and _sort_time(row.get("at")) > cutoff:
            continue
        out.append(row)
    return out


def _view(entry: dict[str, Any], items: list[dict[str, Any]],
          payload: Mapping[str, Any], requested_as_of: Any,
          scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """The filtered order for one request shape, derived once per index entry.

    The cutoff and the undated tail are properties of the folded projection, so they
    live beside it.  The shape key is the whole request minus its page window, so two
    pages of one walk share the order and a different filter gets its own.  The
    resolved file scope is part of the shape: a changed source selection is a new order.
    """
    with _TALK_LOCK:
        if "undated" not in entry:
            entry["undated"] = sum(1 for row in items if row.get("at") is None)
            recorded = [row.get("at") for row in items
                        if math.isfinite(_sort_time(row.get("at"))) and _sort_time(row.get("at")) != float("-inf")]
            entry["recorded_max"] = max(recorded, key=_sort_time) if recorded else None
        as_of = requested_as_of if requested_as_of not in (None, "") else entry["recorded_max"]
        key = json.dumps([{name: value for name, value in payload.items()
                           if name not in ("offset", "limit", "as_of")}, as_of, scope],
                         sort_keys=True, default=str)
        view = entry["views"].get(key)
        if view is None:
            view = {"as_of": as_of, "items": _filter(items, {**payload, "as_of": as_of}, scope=scope)}
            if len(entry["views"]) >= _VIEW_LIMIT:
                entry["views"].pop(next(iter(entry["views"])))
            entry["views"][key] = view
        return view


def history(project: str, payload: Mapping[str, Any] | None = None,
            repo_root: Path | str | None = None) -> dict[str, Any]:
    """Return a bounded page of compact activity items; this performs no hashing."""
    if not isinstance(payload or {}, Mapping):
        raise ValueError("history payload must be an object")
    payload = payload or {}
    validate_activity_query(payload)
    root = _root(repo_root)
    entry = _indexed(project, root)
    items, _records, coverage, limitations = entry["fold"]
    try:
        offset = max(0, int(payload.get("offset", 0)))
        limit = max(1, min(MAX_LIMIT, int(payload.get("limit", DEFAULT_LIMIT))))
    except (TypeError, ValueError) as exc:
        raise ValueError("history offset and limit must be integers") from exc
    requested_as_of = payload.get("as_of")
    if requested_as_of not in (None, "") and _sort_time(requested_as_of) == float("-inf"):
        raise ValueError("history as_of must be an owner-recorded ISO or epoch timestamp")
    # The first page establishes a stable cutoff from the newest owner-recorded
    # event.  Subsequent pages pass it back verbatim; date-less records remain
    # visible at the end with an explicit limitation rather than disappearing.
    # PAGING IS A SLICE, not a refold: the cutoff and the filtered order are derived
    # once per request shape and held in the same index as the projection, which is
    # what makes the 266-call read of the author's own record a read and not a rebuild.
    scope = requested_file_scope(project, root, payload, items)
    if scope and scope["resolution"] == "ambiguous":
        limitations = [*limitations, "file query %r is ambiguous between the checkout path %r and the selected source's %r; ask with the checkout path."
                       % (scope["file"], scope["candidates"][0], scope["candidates"][1])]
    view = _view(entry, items, payload, requested_as_of, scope)
    as_of, filtered = view["as_of"], view["items"]
    page = copy.deepcopy(filtered[offset:offset + limit])
    return {"schema_version": SCHEMA_VERSION, "project": project,
            "as_of": as_of, "items": page,
            # The qualified handle the caller's file query resolved to, so the shell, the
            # native operation and the HTTP route can see one answer to one coordinate, and
            # ``scope.continuation``: the exact query a later page of this walk asks with.
            **({"scope": {**scope, "continuation": _continuation(scope)}} if scope else {}),
            "pagination": {"offset": offset, "limit": limit, "total": len(filtered),
                           "next_offset": offset + len(page) if offset + len(page) < len(filtered) else None},
            # A COPY, like the page itself: ``coverage`` is the live list inside the
            # cached fold, so handing it out raw let a caller that edited what it was
            # given change every later page for the life of the process.
            "coverage": copy.deepcopy(coverage), "limitations": [*limitations, *(
                [f"{entry['undated']} activity rows have no recorded date and remain in the unrecorded-date tail."]
                if entry["undated"] else [])]}


def _sha(path: Path) -> str | None:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _hash(recorded: Any, path: Path | None, label: str, *, note: str = "", kind: str = "file",
          observed_bytes: bytes | None = None) -> dict[str, Any]:
    expected = str(recorded) if recorded not in (None, "") else None
    if expected and not expected.startswith("sha256:"):
        expected = "sha256:" + expected
    current = "sha256:"+hashlib.sha256(observed_bytes).hexdigest() if observed_bytes is not None else _sha(path) if path is not None else None
    status = ("unrecorded" if expected is None else "unavailable" if path is None else
              "missing" if current is None else "current" if current == expected else "changed")
    result: dict[str, Any] = {"kind": kind, "label": label, "recorded": expected, "current": current, "status": status}
    if path is not None:
        result["path"] = str(path)
    if note:
        result["note"] = note
    return result


def _within(base: Path, value: str) -> Path | None:
    from laplace.projects.writing_portability import scoped_path
    return scoped_path(base, value)


def _detail(owner: str, row: Mapping[str, Any], item: dict[str, Any], root: Path) -> dict[str, Any]:
    hashes: list[dict[str, Any]] = []
    comparison: dict[str, Any] | None = None
    limitations = ["Hash comparison checks recorded bytes and current bytes only; it does not establish scientific validity."]
    if owner == "authoring":
        anchor = row.get("anchor") if isinstance(row.get("anchor"), Mapping) else {}
        from laplace.manuscript.manuscript_fragments import recorded_source_comparisons

        comparisons = recorded_source_comparisons(row)
        before, after = row.get("before"), row.get("after")
        if comparisons:
            comparison = comparisons[0]
        elif isinstance(before, str) or isinstance(after, str):
            comparison = {
                "format": "tex",
                "title": "Recorded correction",
                "before": before or "",
                "after": after or "",
                "basis": "exact correction row; current locatability is owned by author_changes",
            }
        else:
            comparison = {
                "format": "fields",
                "title": "Recorded correction",
                "changes": [
                    {"field": "status", "before": None, "after": row.get("status")},
                    {"field": "text", "before": None, "after": row.get("text")},
                ],
                "basis": "correction has no stored source bytes",
            }
        if anchor.get("sha256"):
            limitations.append(
                "The correction anchor hash is a passage anchor, not a claim that a whole historical source snapshot exists."
            )
        baseline = row.get("baseline") if isinstance(row.get("baseline"), Mapping) else {}
        source_file = baseline.get("source_file")
        recorded_file = anchor.get("file") or row.get("file")
        before_pin, after_pin = baseline.get("before_sha256"), baseline.get("after_sha256")
        pins_match = (
            baseline.get("kind") == "guarded-save-preimage"
            and source_file == recorded_file
            and isinstance(source_file, str)
            and all(
                isinstance(pin, str) and re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", pin)
                for pin in (before_pin, after_pin)
            )
        )
        if pins_match:
            hashes.append(
                {
                    "kind": "file",
                    "label": "Recorded file preimage",
                    "recorded": "sha256:" + before_pin.removeprefix("sha256:"),
                    "current": None,
                    "status": "recorded",
                    "note": "Preimage digest was banked with this delta; it does not claim an archived whole preimage body.",
                }
            )
            hashes.append(
                _hash(
                    after_pin,
                    _within(root, source_file),
                    "Saved file postimage compared with current source",
                )
            )
        else:
            hashes.append(
                _hash(
                    None,
                    None,
                    "Correction source bytes",
                    note="No qualified whole-file pins were retained for this correction; recorded source hunks remain independent evidence.",
                )
            )
    elif owner == "journal":
        edits = row.get("edits") or ((row.get("proposal") or {}).get("edits") if isinstance(row.get("proposal"), Mapping) else [])
        if isinstance(edits, list) and edits:
            comparisons = [{"format": "tex", "title": "Recorded proposed or applied edit",
                            "before": edit.get("before") or "", "after": edit.get("after") or "",
                            "basis": "journal record; application state is shown separately"}
                           for edit in edits if isinstance(edit, Mapping)]
            comparison = comparisons[0] if comparisons else None
        owned = row.get("owned_changes") if isinstance(row.get("owned_changes"), Mapping) else {}
        for file in owned.get("files") or []:
            if not isinstance(file, Mapping) or not isinstance(file.get("path"), str):
                continue
            path = _within(root, file["path"])
            hashes.append(_hash(file.get("after_sha256"), path, f"Current file: {file['path']}"))
        for edit in edits if isinstance(edits, list) else []:
            if isinstance(edit, Mapping) and edit.get("after_sha256") and isinstance(edit.get("file"), str):
                hashes.append(_hash(edit.get("after_sha256"), None, f"Recorded edit: {edit['file']}"))
        comparison = comparison or {"format": "fields", "title": "Recorded journal activity",
                                    "changes": [{"field": key, "after": row.get(key)} for key in ("record", "status", "operation") if key in row],
                                    "basis": "exact stored journal row"}
        outcome = row.get("outcome") if isinstance(row.get("outcome"), Mapping) else {}
        evidence = outcome.get("owner_evidence") if isinstance(outcome.get("owner_evidence"), Mapping) else {}
        for file in evidence.get("files") or []:
            if not isinstance(file, Mapping) or not isinstance(file.get("path"), str):
                continue
            checked = _hash(file.get("after_sha256"), _within(root, file["path"]),
                            f"Owner postimage: {file['path']}", note="exact owner mutation receipt")
            hashes.append(checked)
        for obj in evidence.get("objects") or []:
            if not isinstance(obj, Mapping):
                continue
            hashes.append({"kind": "record-revision", "label": f"Owner record: {obj.get('id')}",
                           "recorded": obj.get("after_revision"), "current": None, "status": "unavailable",
                           "note": "recorded owner revision; current owner comparison is operation-specific"})
        if outcome.get("output_sha256"):
            response = str(outcome["output_sha256"])
            hashes.append({"kind": "response", "label": "Action response fingerprint", "recorded": response if response.startswith("sha256:") else "sha256:" + response,
                           "current": None, "status": "recorded",
                           "note": "response fingerprint, not a source-file or research-record hash"})
        if row.get("operation") == "literature_import":
            imported = [value for value in outcome.get("identities") or [] if isinstance(value, str)]
            current_rows = []
            for key in imported:
                association = _literature_association(item.get("project", ""), root, key)
                if association is None:
                    hashes.append({"kind": "record-revision", "label": f"Imported citation: {key}",
                                   "recorded": None, "current": None, "status": "missing",
                                   "note": "the action did not retain an owner record identity and no current association is available"})
                    continue
                current_rows.append(association)
                hashes.append({"kind": "record-revision", "label": f"Imported citation: {key}",
                               "recorded": None, "current": association["revision"], "status": "unrecorded",
                               "note": "current association identity only; this legacy action did not bank its historical owner revision"})
            if current_rows:
                assoc = current_rows[0]
                source = assoc["row"].get("source") if isinstance(assoc["row"].get("source"), Mapping) else {}
                comparison = {"format": "fields", "title": "Imported citation", "changes": [
                    {"field": "key", "after": assoc["row"].get("key")},
                    {"field": "title", "after": assoc["title"]},
                    {"field": "citation_source", "after": source.get("provider")}],
                    "basis": "current association is linked by the exact imported key; historical owner revision was not banked"}
        if row.get("operation") == "research_record":
            outcome = row.get("outcome") if isinstance(row.get("outcome"), Mapping) else {}
            revisions = outcome.get("revisions") if isinstance(outcome.get("revisions"), Mapping) else {}
            recorded_revision = revisions.get("revision")
            identities = []
            for result_id in outcome.get("receipts") or []:
                if not isinstance(result_id, str):
                    continue
                identity = _research_identity(item.get("project", ""), root, result_id, recorded_revision)
                identities.append(identity)
                hashes.append({"label": f"Research record identity: {result_id}",
                               "recorded": recorded_revision, "current": identity.get("current"),
                               "status": identity["status"], "note": "typed research-record revision, not a file hash"})
                record = identity.get("record")
                if isinstance(record, Mapping):
                    comparison = {"format": "fields", "title": f"Recorded research result: {result_id}",
                                  "changes": [{"field": "question", "after": record.get("question")},
                                              {"field": "finding", "after": record.get("summary") or record.get("title")},
                                              {"field": "limitations", "after": record.get("limitations")}],
                                  "basis": identity["basis"]}
                else:
                    comparison = {"format": "fields", "title": f"Recorded research result: {result_id}",
                                  "changes": [{"field": "revision", "after": recorded_revision}],
                                  "basis": identity["basis"]}
            if identities:
                result_identity = identities
        if not hashes:
            hashes.append(_hash(None, None, "Activity byte evidence", note="this journal row records no source byte hash"))
    elif owner == "editor-save":
        version, manuscript = Path(row["_version_dir"]), Path(row["_manuscript_dir"])
        file = str(row.get("file") or "")
        saved = _within(version, file) if file else None
        from laplace.manuscript.projection_viewer import read_editor_save
        saved_text = None
        try:
            observed = read_editor_save(manuscript, str(row.get("version_id")), repo_root=root)
            hashes.append(_hash(row.get("sha"), saved, "Recorded banked save", observed_bytes=observed['data']))
            saved_text = observed['data'].decode('utf-8', errors='replace')
            hashes.append(_hash(row.get("sha"), observed['live_file'], "Current manuscript file",
                note="Exact VERSION.source_file binding" if observed['live_file'] is not None else
                     "Legacy save has no exact VERSION.source_file binding; no live mapping is inferred"))
        except (OSError, ValueError) as exc:
            hashes.append(_hash(row.get("sha"), saved, "Recorded banked save", note=str(exc)))
            hashes.append(_hash(row.get("sha"), None, "Current manuscript file", note=str(exc)))
        comparison = {"format": "tex", "title": "Banked editor save", "before": None,
                      "after": saved_text[:12_000] if saved_text is not None else None,
                      "basis": "exact banked save bytes"}
        if saved_text is not None and len(saved_text) > 12_000:
            comparison["note"] = f"Preview is the first 12,000 of {len(saved_text)} characters; use the saved target for the exact file."
    elif owner == "snapshot":
        version, manuscript = Path(row["_version_dir"]), Path(row["_manuscript_dir"])
        files = [file for file in row.get("files") or [] if isinstance(file, str)]
        for file in files:
            saved, live = _within(version, file), _within(manuscript, file)
            recorded = _sha(saved) if saved else None
            hashes.append(_hash(recorded, saved, f"Snapshot bytes present: {file}",
                                note="hash computed during this detail read from immutable snapshot bytes; not a previously pinned verification"))
            hashes.append(_hash(recorded, live, f"Current snapshot file: {file}",
                                note="compared with the immutable snapshot bytes"))
        comparison = {"format": "fields", "title": "Banked snapshot", "changes": [
            {"field": "source_tree_hash", "after": row.get("source_tree_hash")},
            {"field": "files", "after": files}], "basis": "snapshot manifest and immutable files"}
    elif owner == "concept":
        node = str(row.get("node") or row.get("target") or "")
        comparison = {"format": "fields", "title": "Exact concept rewire", "changes": [
            {"field": key, "after": row.get(key)} for key in
            ("kind", "node", "target", "value", "essence", "rel", "axis", "rationale") if key in row],
            "basis": "exact rewire ledger row; semantic before/after is reprojected only on detail"}
        if node:
            try:
                from laplace.research import concepts as concepts_surface
                projected = concepts_surface.history(project=item.get("project", ""), node=node, record_id=str(row.get("id") or ""), root=root)
            except Exception:
                projected = None
            if projected and projected.get("history"):
                changes = projected["history"][0].get("subject", {}).get("changes") or []
                comparison["changes"] = changes or comparison["changes"]
                comparison["note"] = "Concept before/after is reprojected over current source, not a historical source snapshot."
        hashes.append(_hash(None, None, "Historical concept source bytes", note="the rewire ledger does not bank historical corpus source bytes"))
    elif owner == "research":
        prior = row.get("record") if isinstance(row.get("record"), Mapping) else {}
        provenance = prior.get("provenance") if isinstance(prior.get("provenance"), Mapping) else {}
        comparison = {"format": "fields", "title": "Archived research revision", "changes": [
            {"field": key, "after": prior.get(key)} for key in ("id", "revision", "kind", "summary", "question", "limitations") if key in prior],
            "basis": "owner-retained research history"}
        base = _project_dir(item.get("project", ""), root)
        for dependency in provenance.get("dependencies") or []:
            if isinstance(dependency, Mapping) and isinstance(dependency.get("path"), str):
                hashes.append(_hash(dependency.get("sha256"), _within(base, dependency["path"]) if base else None,
                                    f"Research dependency: {dependency['path']}"))
        if not hashes:
            hashes.append(_hash(None, None, "Research dependency bytes", note="this archived revision contains no recorded dependency hash"))
    elif owner == "formal":
        base = Path(str(row.get("_manuscript_dir") or ""))
        file = str(row.get("file") or "")
        comparison = {"format": "fields", "title": "Formal check receipt", "changes": [
            {"field": key, "after": row.get(key)} for key in ("declaration", "proof_status", "result_id", "claim_id") if key in row],
            "basis": "exact formal receipt; proof status does not establish scientific validity"}
        hashes.append(_hash(row.get("file_digest"), _within(base, file) if file and base.is_dir() else None,
                            f"Formal source: {file or 'unrecorded'}"))
    elif owner == "literature":
        comparison = {"format": "fields", "title": "Reading observation", "changes": [
            {"field": key, "after": row.get(key)} for key in ("reference_key", "locator", "observation", "offset", "length") if key in row],
            "basis": "stored reading receipt; observation is not independent comprehension or entailment"}
        hashes.append(_hash(row.get("source_sha256"), None, "Observed source bytes",
                            note="the reading receipt does not retain a local immutable source snapshot"))
    saved_text = row.get("text") if isinstance(row.get("text"), str) else (
        str(row.get("error")) if row.get("record") == "writing-tool-failure" and row.get("error") is not None else None)
    result = {"item": item, "record_kind": row.get("record") or owner,
            "saved_text_available": saved_text is not None,
            "response_body_status": ("stored-public-text" if saved_text is not None else
                                     "summary-only" if owner == "journal" else "not-applicable"),
            "description": _trim(saved_text or row.get("label") or item["summary"], 2000),
            "comparison": comparison, "hashes": hashes, "links": item.get("targets") or [],
            "conversation": item.get("conversation"), "limitations": limitations, "warnings": []}
    if owner in {"journal", "authoring"} and 'comparisons' in locals() and comparisons:
        result["comparisons"] = comparisons
    if owner == "journal" and 'result_identity' in locals():
        result["record_identities"] = [{key: identity.get(key) for key in ("status", "recorded", "current", "basis")}
                                       for identity in result_identity]
    return result


def _activity_id(items, ident: str) -> str:
    """Accept an exact activity handle or one unique owner-issued record ID.

Conversation failure controls already name the recorded TOOLFAIL ID. Requiring
an agent to guess an activity prefix before inspecting that row adds no safety.
Ambiguous IDs still require the explicit activity handle from the timeline.
"""
    if ident.startswith("activity:"):
        return ident
    matches = [row["id"] for row in items if row["id"].split(":", 2)[-1] == ident]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError("history record ID is ambiguous; use its full activity ID from the timeline")
    return ident


def _selected_journal_item(project, ident, root, *, strict):
    selected = writing_records.selected_journal(project, ident, root, strict=strict)
    if selected is None:
        raise ValueError("history record is unavailable")
    row, _meta, context = selected
    items, _rows, _limitations = _journal_items(project, root,
        talk_rows=[*context, row], selected=True)
    item = next((value for value in items if value['id'] == ident), None)
    if item is None:
        item = _item('journal', str(row['id']), 'session', row,
                     actor=_actor(label=row.get('by'), provider=row.get('provider')),
                     summary='Exact saved ' + str(row.get('record') or 'owner record'),
                     status=row.get('status') or 'recorded', targets=[])
    return row, copy.deepcopy(item)


def structural_undo_contract() -> dict:
    """Closed native selector for the existing structural inverse read owner."""
    return {"type":"object", "required":["view", "kind", "id"],
        "properties":{"view":{"const":"structural-undo"},
            "kind":{"enum":["block", "section"]},
            "id":{"type":"string", "minLength":1, "maxLength":300},
            "project":{"type":"string", "minLength":1}},
        "additionalProperties":False}


def structural_undo_read(project: str, reference) -> dict | None:
    """A current read coordinate from a recorded reference, never an inverse body."""
    if (not isinstance(reference, Mapping) or reference.get("project", project) != project
            or reference.get("kind") not in ("block", "section")
            or not isinstance(reference.get("id"), str) or not 0 < len(reference["id"]) <= 300):
        return None
    return {"operation":"author_history", "payload":{"view":"structural-undo",
            "kind":reference["kind"], "id":reference["id"]}}


def structural_undo(project: str, payload: Mapping, repo_root=None) -> dict:
    """Read one existing exact inverse lazily; source guards remain at application."""
    from jsonschema import Draft202012Validator
    if isinstance(payload, Mapping) and payload.get("kind") not in ("block", "section"):
        raise ValueError("Choose a block or section history record.")
    error = next(Draft202012Validator(structural_undo_contract()).iter_errors(payload), None)
    if error is not None:
        raise ValueError("Structural Undo read selector: " + error.message)
    if payload.get("project", project) != project:
        raise ValueError("Structural Undo read belongs to another project")
    root = _root(repo_root)
    kind, ident = payload["kind"], payload["id"]
    if kind == "block":
        from laplace.manuscript import blocks as manuscript_blocks
        result = manuscript_blocks.undo_record(root, project, ident)
    else:
        from laplace.manuscript import manuscript_structure
        result = manuscript_structure.undo_record(project, ident, root)
    if (result.get("project") != project or result.get("kind") != kind
            or result.get("id") != ident or not isinstance(result.get("undo"), dict)):
        raise ValueError("Structural Undo owner returned a different exact reference")
    return result


def _record_envelope(project, row, item, owner):
    text = row.get("text") if isinstance(row.get("text"), str) else (
        str(row.get("error")) if row.get("record") == "writing-tool-failure" and row.get("error") is not None else None)
    # COPIES, for the same reason ``history`` copies its page: ``item`` is the object
    # inside the derived index and ``row`` is the stored row inside it, so returning
    # either raw let a caller that edited what it was handed change every later page.
    # ``exact`` is a fresh dict but its values were the index's nested structures.
    item = copy.deepcopy(item)
    exact = copy.deepcopy({key: value for key, value in row.items()
                           if not str(key).startswith("_")})
    # Some owners (research archives) retain a scientific object in `record`.
    # That object is payload, not the journal's scalar record discriminator.
    kind = row.get("record")
    record_kind = kind if isinstance(kind, str) and kind else owner
    measurements=[]
    catalogue_row = record_kind not in {"writing-turn", "writing-reply", "writing-application",
        "writing-proposal-decision", "writing-tool-read", "writing-tool-action", "writing-tool-failure",
        "writing-native-file-change", "writing-proposal"}
    if catalogue_row and isinstance(row.get("_storage_bytes"),int):
        measurements.append({"kind":"storage_bytes","value":row["_storage_bytes"],"unit":"bytes",
                             "basis":"exact saved journal line"})
    if record_kind in {"writing-tool-read","writing-tool-action","writing-tool-failure"}:
        if isinstance(row.get("_storage_bytes"),int):measurements.append({"kind":"storage_bytes","value":row["_storage_bytes"],"unit":"bytes","basis":"exact stored journal line"})
        for key,unit in (("response_bytes","bytes"),("duration_seconds","seconds"),("context_tokens_used","tokens")):
            if isinstance(row.get(key),(int,float)):measurements.append({"kind":key,"value":row[key],"unit":unit,"basis":"owner-recorded tool event field"})
        if isinstance(row.get("cost"),(int,float)):measurements.append({"kind":"cost","value":row["cost"],"unit":row.get("cost_unit") or "recorded-unit","basis":"owner-recorded tool event field"})
    outcome = row.get("outcome")
    inverse_read = (structural_undo_read(project, outcome.get("undo_ref"))
                    if record_kind == "writing-tool-action" and isinstance(outcome, Mapping)
                    and outcome.get("status") == "SUCCEEDED" else None)
    from laplace.manuscript.manuscript_fragments import recorded_source_comparisons
    source_comparisons = recorded_source_comparisons(row)
    return {"schema_version": SCHEMA_VERSION, "project": project, "item": item,
            **({"comparisons":source_comparisons,"comparison":source_comparisons[0]} if source_comparisons else {}),
            **({"structural_undo_read":inverse_read} if inverse_read else {}),
            "record_kind": record_kind, "record": exact, "text": text,
            "measurements":measurements,
            "saved_text_available": text is not None,
            "response_body_status": "stored-public-text" if text is not None else "summary-only",
            "format": "markdown" if row.get("record") == "writing-reply" and text is not None else "text",
            "limitations": (["One exact stored public owner row, not reconstructed provider history."] if catalogue_row else
                ["This is the exact stored public owner row. It is not a reconstructed conversation or hidden model reasoning."])}


def _page_detail(project: str, ident: str, result: dict[str, Any], offset: int, limit: int) -> dict[str, Any]:
    """Deliver recorded comparisons one bounded page at a time; `comparison` stays the first hunk."""
    rows=result.get("comparisons")
    if isinstance(rows,list):
        result.update(_paged_comparisons(project,ident,rows,offset,limit))
    return result


def detail(project: str, ident: str, repo_root: Path | str | None = None, *,
           comparison_offset: int = 0, comparison_limit: int = COMPARISON_PAGE) -> dict[str, Any]:
    """Resolve one exact list ID and lazily verify only its relevant bytes.

    Recorded source comparisons (hunks) are paged: ``comparisons`` is one page and
    ``comparisons_pagination`` carries total and the owner's next read. ``record``
    (the exact stored row, on explicit demand) keeps every hunk.
    """
    root = _root(repo_root)
    if ident.startswith("activity:journal:"):
        row, item = _selected_journal_item(project, ident, root, strict=False)
        return _page_detail(project, ident, {"schema_version": SCHEMA_VERSION, "project": project,
                **_detail("journal", row, {**item, "project": project}, root)}, comparison_offset, comparison_limit)
    items, records, _coverage, _limitations = _all(project, root)
    ident = _activity_id(items, ident)
    item = next((row for row in items if row["id"] == ident), None)
    if item is None:
        raise ValueError("history item is unavailable")
    prefix = "activity:"
    if not ident.startswith(prefix):
        raise ValueError("history item is unavailable")
    owner, _, raw_id = ident[len(prefix):].partition(":")
    row = records.get(owner, {}).get(raw_id)
    if not isinstance(row, Mapping):
        raise ValueError("history detail is unavailable")
    if owner=="journal":
        from laplace.representation.writing_bodies import resolve_fields
        row=resolve_fields(row,root,strict=False)
    item = {**copy.deepcopy(item), "project": project}   # a copy, as in record()
    return _page_detail(project, ident, {"schema_version": SCHEMA_VERSION, "project": project, **_detail(owner, row, item, root)},
                        comparison_offset, comparison_limit)


def record(project: str, ident: str, repo_root: Path | str | None = None) -> dict[str, Any]:
    """Return one exact stored public owner row only on explicit demand."""
    root = _root(repo_root)
    if ident.startswith("activity:journal:"):
        row, item = _selected_journal_item(project, ident, root, strict=True)
        return _record_envelope(project, row, item, "journal")
    from laplace.work import author_history_metrics
    if ident.startswith('activity:admission:'):
        exact = author_history_metrics.exact_record(project, ident.removeprefix('activity:admission:'), root)
        if exact is None or exact[0].get('record') != 'writing-turn':
            raise ValueError('Exact turn admission is unavailable in this project.')
        row, meta = exact
        return {'schema_version': SCHEMA_VERSION, 'project': project, 'record_kind': 'writing-turn',
                'record': row, 'exact': True, 'basis': 'Original immutable turn admission row; later context refreshes do not replace it.',
                'policy_body_status': 'UNAVAILABLE-not-retained; current policy is not reconstructed as historical bytes',
                'limitations': ['Admission proves recorded app basis; delivered provider channels require their separate receipt.']}
    if ident.startswith('activity:feedback:'):
        row = author_history_metrics.exact_feedback(project, ident, root)
        return {'schema_version': SCHEMA_VERSION, 'project': project,
                'record_kind': row.get('record') or row.get('kind') or 'note', 'record': row,
                'text': row.get('comment') or row.get('text'), 'saved_text_available': True,
                'response_body_status': 'stored-public-text', 'format': 'text',
                'limitations': ['Exact existing feedback owner record, not inferred response attribution.']}
    if ident.startswith('activity:journal:') or not ident.startswith('activity:'):
        exact = author_history_metrics.exact_record(project, ident, root, catalogue_only=True)
        if exact is not None:
            row, metadata = exact
            raw_id = str(row.get('id'))
            item = _item('journal', raw_id, 'session', row,
                         actor=_actor(label=row.get('by'), provider=row.get('provider')),
                         summary='Exact saved ' + str(row.get('record') or 'owner record'),
                         status=row.get('status') or 'recorded', targets=[])
            text = row.get('text') if isinstance(row.get('text'), str) else None
            return {'schema_version': SCHEMA_VERSION, 'project': project, 'item': item,
                    'record_kind': row.get('record'), 'record': copy.deepcopy(row), 'text': text,
                    'measurements': [{'kind': 'storage_bytes', 'value': metadata['_end'] - metadata['_offset'],
                                      'unit': 'bytes', 'basis': 'exact saved journal line'}],
                    'saved_text_available': text is not None,
                    'response_body_status': 'stored-public-text' if text is not None else 'summary-only',
                    'format': 'markdown' if row.get('record') == 'writing-reply' else 'text',
                    'limitations': ['One exact stored public owner row, not reconstructed provider history.']}
    items, records, _coverage, _limitations = _all(project, root)
    ident = _activity_id(items, ident)
    item = next((row for row in items if row["id"] == ident), None)
    if item is None or not ident.startswith("activity:"):
        raise ValueError("history record is unavailable")
    owner, _, raw_id = ident[len("activity:"):].partition(":")
    row = records.get(owner, {}).get(raw_id)
    if not isinstance(row, Mapping):
        raise ValueError("history record is unavailable")
    if owner=="journal":
        from laplace.representation.writing_bodies import resolve_fields
        row=resolve_fields(row,root,strict=True)
    return _record_envelope(project, row, item, owner)


def help() -> dict[str, Any]:
    """Small native-agent contract; no historical rows are included here."""
    from laplace.work.author_history_metrics import contract as metrics_contract
    return {"operation": "author_history", "metadata_analytics": {
        'input': metrics_contract(),
        'entry': {'view': 'telemetry', 'projection': 'sessions'},
        'basis': 'Original owner metadata with exact lazy drilldowns; no source or response bodies in aggregates.'}, "views": {"activity": {
        "summary": "Read a bounded activity timeline or one exact activity item.",
        "list": {"view": "activity", "offset": 0, "limit": DEFAULT_LIMIT,
                 "filters": ["file", "node", "result_id", "category", "actor", "as_of"]},
        "detail": {"view": "activity", "id": "exact item id from the list"},
        "limitations": ["The list does not hash files or call providers.",
                        "Hash comparison confirms bytes, not scientific validity."]},
        "record": {"summary": "Read one exact saved public owner row or stored response text by its activity ID or unique owner-issued record ID.",
                   "input": {"view": "record", "id": "exact activity ID or unique recorded ID (for example TOOLFAIL-...)"},
                   "limitations": ["The exact row is loaded lazily and is never reconstructed from provider history."]},
        "telemetry": {"summary": "Read bounded grouped activity and recorded run, usage, identity, and exact original tool-attempt telemetry.",
                      "input": {"view": "telemetry", "filters": ["file", "node", "result_id", "category", "actor", "as_of", "event_kind", "operation", "session_id", "provider", "model", "outcome", "from", "to"]},
                      "outputs": ["day/actor/category counts with exact timeline filters", "original tool read/action/failure counts by operation, time, session and outcome", "recorded supervised run durations/outcomes", "recorded provider context-token usage", "typed identity coverage without raw hash values"],
                      "limitations": ["Missing dates, durations, token usage, and hashes are never estimated."]}}}


def _day(value: Any) -> str:
    stamp = _sort_time(value)
    if math.isfinite(stamp) and stamp != float("-inf"):
        return datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat()
    if isinstance(value, str) and len(value) >= 10:
        return value[:10]
    return "unrecorded"


def _telemetry_runs(project: str, root: Path, *, scope: Mapping[str, Any], as_of: Any) -> list[dict[str, Any]]:
    if scope.get("category") not in (None, "", "research") or any(scope.get(key) for key in ("file", "node", "actor", "provider", "model")):
        return []
    manuscript = _manuscript_dir(project, root)
    runs = manuscript / "research_runs" if manuscript else None
    if runs is None or not runs.is_dir():
        return []
    rows = []
    research = _read_json(manuscript / "research_records.json") if manuscript else None
    result_by_run = {str(row.get("run_id")): str(row.get("id")) for row in (research or {}).get("records") or []
                     if isinstance(row, Mapping) and row.get("run_id") and row.get("id")}
    for receipt_path in sorted(runs.glob("*.receipt.json"), key=lambda path: path.name, reverse=True)[:100]:
        receipt = _read_json(receipt_path) or {}
        ident = receipt_path.name.removesuffix(".receipt.json")
        job = _read_json(runs / (ident + ".json")) or {}
        if job.get("project") not in (None, project):
            continue
        started, finished = job.get("started_at"), receipt.get("finished_at")
        if as_of not in (None, "") and _sort_time(finished) > _sort_time(as_of):
            continue
        if scope.get("day") and _day(finished) != scope["day"]:
            continue
        if scope.get("from") and _sort_time(finished) < _sort_time(scope["from"]):
            continue
        if scope.get("to") and _sort_time(finished) >= _sort_time(scope["to"]):
            continue
        if scope.get("outcome") and scope["outcome"] != (receipt.get("state") or job.get("state") or "recorded"):
            continue
        result_id = result_by_run.get(ident)
        if scope.get("result_id") and scope["result_id"] != result_id:
            continue
        duration = (float(finished) - float(started) if isinstance(started, (int, float))
                    and isinstance(finished, (int, float)) and float(finished) >= float(started) else None)
        rows.append({"id": ident, "outcome": receipt.get("state") or job.get("state") or "recorded",
                     "producer_id": job.get("producer_id"), "started_at": started, "finished_at": finished,
                     "duration_seconds": duration, "result_id": result_id,
                     "filter": ({"category": "research", "result_id": result_id, "as_of": as_of}
                                if result_id else None)})
    return rows[:20]


def _telemetry_usage(project: str, root: Path, *, scope: Mapping[str, Any], as_of: Any,
                     talk_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if scope.get("category") not in (None, "", "session") or any(scope.get(key) for key in ("file", "node", "result_id")):
        return {"records": 0, "missing": 0, "by_provider_model": [], "scope_status": "not-applicable-to-selected-scope"}
    rows = talk_rows if talk_rows is not None else _talk_rows(root, project)
    turns = {str(row.get("id")): row for row in rows if row.get("record") == "writing-turn" and row.get("id")}
    grouped: dict[tuple[str | None, str | None], dict[str, Any]] = {}
    eligible = recorded = 0
    for row in rows:
        if row.get("record") != "writing-reply":
            continue
        turn = turns.get(str(row.get("turn_id"))) or {}
        if row.get("project") != project and turn.get("project") != project:
            continue
        if scope.get('session_id') and scope['session_id'] != turn.get('session_id'):
            continue
        if as_of not in (None, "") and _sort_time(row.get("ts")) > _sort_time(as_of):
            continue
        if scope.get("day") and _day(row.get("ts")) != scope["day"]:
            continue
        if scope.get("from") and _sort_time(row.get("ts")) < _sort_time(scope["from"]):
            continue
        if scope.get("to") and _sort_time(row.get("ts")) >= _sort_time(scope["to"]):
            continue
        if scope.get("outcome") and scope["outcome"] != str(row.get("status") or "recorded"):
            continue
        settings = turn.get("provider_settings") if isinstance(turn.get("provider_settings"), Mapping) else {}
        usage = row.get("usage") if isinstance(row.get("usage"), Mapping) else {}
        provider = settings.get("provider") or usage.get("provider")
        model = settings.get("model")
        if scope.get("provider") and scope["provider"] != provider:
            continue
        if scope.get("model") and scope["model"] != model:
            continue
        eligible += 1
        if not isinstance(row.get("usage"), Mapping):
            continue
        key = (str(provider) if provider else None, str(model) if model else None)
        value = grouped.setdefault(key, {"provider": key[0], "model": key[1], "model_basis":"immutable turn admission, not actual provider resolution", "count": 0,
                                         "latest_context_tokens_used": None, "max_context_tokens_used": None, "context_tokens_observations": 0,
                                         "filter": {"category": "session", "provider": key[0], "model": key[1], "as_of": as_of}})
        value["count"] += 1
        tokens = row.get("context_tokens_used")
        if isinstance(tokens, (int, float)):
            value["latest_context_tokens_used"] = int(tokens)
            value["max_context_tokens_used"] = max(value["max_context_tokens_used"] or 0, int(tokens))
            value["context_tokens_observations"] += 1
        recorded += 1
    return {"records": recorded, "missing": max(0, eligible-recorded), "by_provider_model": list(grouped.values()),
            "scope_status": "selected-session-activity"}


def _telemetry_tool_calls(project: str, root: Path, *, scope: Mapping[str, Any], as_of: Any,
                          talk_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Exact original tool attempts; derived baselines and reply copies never enter."""
    rows=talk_rows if talk_rows is not None else _talk_rows(root, project)
    sessions={str(row.get("id")):row for row in rows if row.get("record")=="writing-session"}
    turns={str(row.get("id")):row for row in rows if row.get("record")=="writing-turn"}
    selected=[]
    for row in rows:
        kind=row.get("record")
        if kind not in {"writing-tool-read","writing-tool-action","writing-tool-failure"}:continue
        turn=turns.get(str(row.get("turn_id"))) or {};session=sessions.get(str(turn.get("session_id"))) or {}
        if row.get("project")!=project and turn.get("project")!=project and session.get("project")!=project:continue
        settings=turn.get("provider_settings") if isinstance(turn.get("provider_settings"),Mapping) else {}
        provider=settings.get("provider") or session.get("provider");model=settings.get("model") or session.get("model")
        operation=str(row.get("operation") or "unknown")
        allowed=scope.get("_allowed_tool_ids")
        if isinstance(allowed,set) and str(row.get("id") or "") not in allowed:continue
        action_status=((row.get("outcome") or {}).get("status")
                       if isinstance(row.get("outcome"),Mapping) else None)
        outcome=("failed" if kind=="writing-tool-failure" else
                 "read" if kind=="writing-tool-read" else str(action_status or "recorded").lower())
        stamp=_stamp(row);stamp_value=_sort_time(stamp)
        if as_of not in (None,"") and stamp_value>_sort_time(as_of):continue
        if scope.get("from") and stamp_value<_sort_time(scope["from"]):continue
        if scope.get("to") and stamp_value>=_sort_time(scope["to"]):continue
        if scope.get("operation") and scope["operation"]!=operation:continue
        if scope.get("session_id") and scope["session_id"]!=turn.get("session_id"):continue
        if scope.get("provider") and scope["provider"]!=provider:continue
        if scope.get("model") and scope["model"]!=model:continue
        if scope.get("outcome") and scope["outcome"]!=outcome:continue
        selected.append({"row":row,"operation":operation,"outcome":outcome,"at":stamp,
                         "session_id":turn.get("session_id"),"provider":provider,"model":model})
    base_filter={"event_kind":"tool-attempt",**({"as_of":as_of} if as_of not in (None,"") else {}),
        **{key:scope[key] for key in ("file","node","result_id","category","actor","operation",
        "session_id","provider","model","outcome","from","to") if scope.get(key)}}
    by_operation:dict[str,int]={};by_outcome:dict[str,int]={};by_session:dict[str,dict]={}
    for item in selected:
        by_operation[item["operation"]]=by_operation.get(item["operation"],0)+1
        by_outcome[item["outcome"]]=by_outcome.get(item["outcome"],0)+1
        sid=str(item.get("session_id") or "unrecorded")
        value=by_session.setdefault(sid,{"id":sid,"provider":item.get("provider"),"model":item.get("model"),"count":0})
        value["count"]+=1
    for sid,value in by_session.items():
        first=next((turn for turn in turns.values() if str(turn.get("session_id") or "")==sid),{})
        value["label"]=_trim(first.get("text") or sid,80);value["filter"]={**base_filter,"session_id":sid}
    dated=[item for item in selected if math.isfinite(_sort_time(item.get("at"))) and _sort_time(item.get("at"))!=float("-inf")]
    stamps=[_sort_time(item["at"]) for item in dated];hourly=bool(stamps) and max(stamps)-min(stamps)<=3*24*3600
    buckets:dict[tuple[str,str,str],int]={}
    for item in dated:
        stamp=datetime.fromtimestamp(_sort_time(item["at"]),tz=timezone.utc)
        start=stamp.replace(minute=0,second=0,microsecond=0) if hourly else stamp.replace(hour=0,minute=0,second=0,microsecond=0)
        end=start+(timedelta(hours=1) if hourly else timedelta(days=1));key=(start.isoformat().replace("+00:00","Z"),end.isoformat().replace("+00:00","Z"),item["operation"])
        buckets[key]=buckets.get(key,0)+1
    operations=sorted(by_operation.items(),key=lambda row:(-row[1],row[0]));all_cells=sorted(buckets.items())
    bins=[]
    for start,end,_operation in (key for key,_count in all_cells):
        if (start,end) not in bins:bins.append((start,end))
    kept_bins=[];kept_cells=0
    for stamp in reversed(bins):
        size=sum(key[:2]==stamp for key,_count in all_cells)
        if kept_bins and kept_cells+size>240:break
        kept_bins.append(stamp);kept_cells+=size
    kept=set(kept_bins);cells=[item for item in all_cells if item[0][:2] in kept]
    def clipped(start,end):
        lower=scope.get("from");upper=scope.get("to")
        return {**base_filter,"from":start if not lower or _sort_time(start)>_sort_time(lower) else lower,
                "to":end if not upper or _sort_time(end)<_sort_time(upper) else upper}
    return {"filter":base_filter,"total":len(selected),
        "by_operation":[{"operation":op,"count":count,"filter":{**base_filter,"operation":op}}
                        for op,count in operations[:100]],
        "by_time_operation":[{"start":start,"end":end,"operation":op,"count":count,
            "filter":{**clipped(start,end),"operation":op}}
            for (start,end,op),count in cells],
        "by_outcome":[{"outcome":outcome,"count":count,"filter":{**base_filter,"outcome":outcome}}
                      for outcome,count in sorted(by_outcome.items())],
        "session_choices":sorted(by_session.values(),key=lambda row:(-row["count"],row["id"]))[:100],
        "coverage":{"dated":len(dated),"unrecorded_date":len(selected)-len(dated),
                    "provider_model_recorded":sum(bool(item.get("provider") or item.get("model")) for item in selected),
                    "response_bytes_recorded":sum(isinstance(item["row"].get("response_bytes"),int) for item in selected),
                    "storage_bytes_recorded":sum(int(item["row"].get("_storage_bytes") or 0) for item in selected),
                    "duration_recorded":sum(isinstance(item["row"].get("duration_seconds"),(int,float)) for item in selected),
                    "context_tokens_recorded":0},
        "operations_omitted":max(0,len(operations)-100),"time_operation_bins_omitted":max(0,len(all_cells)-len(cells)),
        "limitations":["Counts include each original writing-tool-read/action/failure row once. Read baselines, context bookkeeping, and reply action copies are excluded.","Durations, response bytes, and context tokens are reported only when the tool row recorded them. Storage bytes are exact journal-line bytes."]}


def telemetry(project: str, payload: Mapping[str, Any] | None = None,
              repo_root: Path | str | None = None) -> dict[str, Any]:
    """Compact measured activity telemetry; never estimates missing timing or usage."""
    if not isinstance(payload or {}, Mapping):
        raise ValueError("telemetry payload must be an object")
    if (payload or {}).get('projection'):
        from laplace.work import author_history_metrics
        return author_history_metrics.read(project, payload or {}, _root(repo_root))
    payload, root = payload or {}, _root(repo_root)
    entry = _indexed(project, root)
    talk_rows = entry["talk"]["rows"]
    items, records, _coverage, limitations = entry["fold"]
    file_scope_ = requested_file_scope(project, root, payload, items)
    cache_key = json.dumps([dict(payload), file_scope_], sort_keys=True, default=str)
    cached = entry.setdefault("telemetry_views", {}).get(cache_key)
    if cached is not None:
        result = copy.deepcopy(cached)
        # Run receipts have their own owner and are not part of this fold stamp.
        result["runs"] = _telemetry_runs(project, root, scope=result["scope"], as_of=result["as_of"])
        return result
    requested = payload.get("as_of")
    if requested not in (None, "") and _sort_time(requested) == float("-inf"):
        raise ValueError("telemetry as_of must be an owner-recorded ISO or epoch timestamp")
    recorded_times = [row.get("at") for row in items if row.get("at") is not None]
    as_of = requested if requested not in (None, "") else (max(recorded_times, key=_sort_time) if recorded_times else None)
    scope = {key: payload[key] for key in ("file", "node", "result_id", "category", "actor", "provider", "model", "day", "from", "to", "outcome", "operation", "session_id", "event_kind") if payload.get(key) not in (None, "")}
    selected = _filter(items, {**scope, "as_of": as_of}, scope=file_scope_)
    tool_scope={**scope,"_allowed_tool_ids":{
        row["id"].split(":",2)[-1] for row in selected if row.get("event_kind")=="tool-attempt"}}
    by_day: dict[str, int] = {}
    by_actor: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_outcome: dict[str, int] = {}
    coverage = {"recorded_file_identities": 0, "record_revisions": 0, "response_fingerprints": 0}
    for item in selected:
        by_day[_day(item.get("at"))] = by_day.get(_day(item.get("at")), 0) + 1
        actor = str((item.get("actor") or {}).get("kind") or "unknown")
        by_actor[actor] = by_actor.get(actor, 0) + 1
        category = str(item.get("category") or "session")
        by_category[category] = by_category.get(category, 0) + 1
        status = str(item.get("status") or "recorded")
        by_outcome[status] = by_outcome.get(status, 0) + 1
        if item.get("owner") == "journal":
            raw = records.get("journal", {}).get(item["id"].split(":", 2)[-1]) or {}
            owned = raw.get("owned_changes") if isinstance(raw.get("owned_changes"), Mapping) else {}
            outcome = raw.get("outcome") if isinstance(raw.get("outcome"), Mapping) else {}
            evidence = outcome.get("owner_evidence") if isinstance(outcome.get("owner_evidence"), Mapping) else {}
            files = list(owned.get("files") or []) + list(evidence.get("files") or [])
            coverage["recorded_file_identities"] += sum(bool(isinstance(file, Mapping) and any(
                file.get(key) for key in ("after_sha256", "intended_after_sha256", "observed_after_sha256"))) for file in files)
            revisions = outcome.get("revisions") if isinstance(outcome.get("revisions"), Mapping) else {}
            coverage["record_revisions"] += int(bool(revisions.get("revision")))
            coverage["response_fingerprints"] += int(bool(outcome.get("output_sha256")))
    dated = [row for row in selected if math.isfinite(_sort_time(row.get("at"))) and _sort_time(row.get("at")) != float("-inf")]
    activity_buckets: dict[tuple[str, str], int] = {}
    timestamps = [_sort_time(row.get("at")) for row in dated]
    hourly = bool(timestamps) and max(timestamps) - min(timestamps) <= 3 * 24 * 3600
    for row in dated:
        stamp = datetime.fromtimestamp(_sort_time(row["at"]), tz=timezone.utc)
        start = stamp.replace(minute=0, second=0, microsecond=0) if hourly else stamp.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + (timedelta(hours=1) if hourly else timedelta(days=1))
        key = (start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z"))
        activity_buckets[key] = activity_buckets.get(key, 0) + 1
    result = {"schema_version": SCHEMA_VERSION, "project": project, "as_of": as_of, "scope": scope,
            "totals": {"activity": len(selected), "dated": len(dated),
                       "unrecorded_date": len(selected)-len(dated)},
            "series": {"activity": [{"start": start, "end": end, "label": start[:13] if hourly else start[:10], "count": count,
                                         "filter": {**scope, "from": start, "to": end, "as_of": as_of}}
                                       for (start, end), count in sorted(activity_buckets.items())][-72:],
                       "by_day": [{"day": key, "count": value, "filter": {**scope, "day": key, "as_of": as_of}}
                                  for key, value in sorted(by_day.items())][-60:],
                       "by_actor": [{"actor": key, "count": value, "filter": {**scope, "actor": key, "as_of": as_of}}
                                    for key, value in sorted(by_actor.items())],
                       "by_category": [{"category": key, "count": value, "filter": {**scope, "category": key, "as_of": as_of}}
                                       for key, value in sorted(by_category.items())],
                       "by_outcome": [{"outcome": key, "count": value, "filter": {**scope, "outcome": key, "as_of": as_of}}
                                      for key, value in sorted(by_outcome.items())]},
            "runs": _telemetry_runs(project, root, scope=scope, as_of=as_of),
            "usage": _telemetry_usage(project, root, scope=scope, as_of=as_of,talk_rows=talk_rows),
            "tool_calls": _telemetry_tool_calls(project, root, scope=tool_scope, as_of=as_of,talk_rows=talk_rows),
            "identity_coverage": [{"type": key, "count": value, "status": "recorded" if value else "absent"}
                                  for key, value in coverage.items()],
            "activity_buckets_omitted": max(0, len(activity_buckets)-72),
            "limitations": [*limitations, "Telemetry uses only banked timestamps, durations, usage, and identities; it does not estimate missing values or verify file bytes."]}
    with _TALK_LOCK:
        cache = entry.setdefault("telemetry_views", {})
        if len(cache) >= _VIEW_LIMIT: cache.pop(next(iter(cache)))
        cache[cache_key] = copy.deepcopy({key: value for key,value in result.items() if key != "runs"})
    return result
