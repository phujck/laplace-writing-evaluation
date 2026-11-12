"""The durable, coherent authoring context for a manuscript project.

Fine-grained source and evidence identities are deliberately separate from the
scope handed to a writer.  A context owns a connected stretch of the document,
its boundary prose, the sustained argument, and the corrections that have been
consumed while forming it.  Context receipts make later source, argument, and
correction changes visible as dependency staleness instead of silently treating
membership in a section as freshness.
"""
from __future__ import annotations

import contextlib
import copy
import datetime as _dt
import hashlib
import json
import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator, Mapping


from laplace.core.identity import require_schema_version

AUTHORING_SCHEMA = "laplace.authoring/1"
_STATE_NAME = "authoring.json"
_LOCK_NAME = ".authoring.lock"
_CONTEXT_BLOB_REF = "$laplace_context_blob"
_CONTEXT_BLOB_FIELDS = ("structure", "writing_style", "source_dependencies",
                        "structure_scope", "selection_spans")
_CONTEXT_BLOB_MIN_BYTES = 128
_CORRECTION_KINDS = frozenset({"factual", "style", "request", "note"})
_CORRECTION_SCOPES = frozenset({"passage", "project", "global"})
_CITE_RE = re.compile(r"\\cite[a-zA-Z*]*\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")


def _context_blob_identity(value: Any) -> tuple[str, bytes]:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest(), raw


def _context_receipt_revision(value: Mapping[str, Any]) -> str:
    body={key:item for key,item in value.items()
          if key not in {"id","created","receipt_revision","storage"}}
    raw=json.dumps(body,ensure_ascii=False,sort_keys=True,
                   separators=(",",":"),default=str).encode("utf-8")
    return "sha256:"+hashlib.sha256(raw).hexdigest()


def _root(repo_root: Path | str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    from laplace.pipeline import registry
    return registry._repo_root().resolve()


def _source(project: str, repo_root: Path | str | None) -> dict[str, Any]:
    # Imported lazily so this module stays usable while a project has no TeX
    # source, and so the document-selection seam remains the sole policy owner.
    from laplace.manuscript import manuscript_source
    return manuscript_source.resolve(project, repo_root=repo_root)


def _state_path(project: str, repo_root: Path | str | None, *, _observed_source=None) -> tuple[Path, dict[str, Any]]:
    # Internal reads may share an actual observation made by the source owner;
    # this is not a public override and does not skip namespace/storage fences.
    source = _observed_source if _observed_source is not None else _source(project, repo_root)
    if _observed_source is not None and source.get("project")!=project:
        raise ValueError("The observed source belongs to another project.")
    # A read-only imported source can declare an engine-owned storage_dir.
    # Never leave authoring receipts beside the author-owned original.
    if source.get("read_only") and not source.get("storage_dir"):
        raise ValueError("Read-only source has no valid engine-owned state directory.")
    directory = source.get("storage_dir") or source.get("manuscript_dir")
    if not isinstance(directory, str) or not directory:
        # Framing precedes a document for graph-only/new projects.  The registered
        # project home is still the project-backed deposit location; lack of a TeX
        # root only prevents source context construction, not author intent.
        from laplace.pipeline import registry
        project_record = registry.resolve(project, repo_root=_root(repo_root))
        directory = ((project_record.manuscript_dir or project_record.project_dir)
                     if project_record is not None else None)
    if not isinstance(directory, str) or not directory:
        detail = "; ".join(str(x) for x in source.get("diagnostics", []) if x) or "no registered project home"
        raise ValueError(f"authoring state unavailable for {project!r}: {detail}")
    root = _root(repo_root)
    candidate = Path(directory)
    path = candidate if candidate.is_absolute() else root / candidate
    if not path.resolve().is_relative_to(root):
        raise ValueError("Authoring state directory escapes the project checkout.")
    return path / _STATE_NAME, source


def _blank(project: str) -> dict[str, Any]:
    return {
        "schema_version": AUTHORING_SCHEMA,
        "project": project,
        "revision": 0,
        "argument_revision": 0,
        "argument": "",
        "framing": {"purpose": "", "audience": "", "question": ""},
        "section_ids": [],
        "corrections": [],
        "contexts": [],
        "context_blobs": {},
    }


def _normalise(state: Any, project: str) -> dict[str, Any]:
    base = _blank(project)
    if not isinstance(state, Mapping):
        return base
    require_schema_version(state, (AUTHORING_SCHEMA,), owner="Authoring state", allow_untagged=True)
    for key in ("schema_version", "project", "revision", "argument_revision", "argument",
                "framing", "section_ids", "corrections", "contexts", "context_blobs"):
        if key in state:
            base[key] = state[key]
    base["project"] = project
    base["revision"] = int(base["revision"]) if isinstance(base["revision"], int) else 0
    base["argument_revision"] = int(base["argument_revision"]) if isinstance(base["argument_revision"], int) else 0
    if isinstance(base["argument"], Mapping):
        base["argument"] = str(base["argument"].get("text") or "")
    elif not isinstance(base["argument"], str):
        base["argument"] = ""
    base["framing"] = _framing(base["framing"])
    base["section_ids"] = _strings(base["section_ids"])
    base["corrections"] = [dict(x) for x in base["corrections"] if isinstance(x, Mapping)]
    base["contexts"] = [dict(x) for x in base["contexts"] if isinstance(x, Mapping)]
    base["context_blobs"] = {str(key): value for key, value in
                             (base["context_blobs"].items()
                              if isinstance(base["context_blobs"], Mapping) else [])}
    return base


def _strings(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else ([] if value is None else [value])
    return list(dict.fromkeys(str(x).strip() for x in values if isinstance(x, (str, int)) and str(x).strip()))


def _framing(value: Any) -> dict[str, str]:
    value = value if isinstance(value, Mapping) else {}
    return {key: str(value.get(key) or "").strip() for key in ("purpose", "audience", "question")}


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.parent / _LOCK_NAME
    # filelock is an explicit runtime dependency and supplies the same
    # interprocess boundary on Windows, macOS and Linux. A missing fcntl module
    # must never silently turn authoring writes into an unlocked path.
    from filelock import FileLock
    with FileLock(str(lock),timeout=30):
        yield


def _read(path: Path, project: str, repo_root=None, *, contexts: bool = True,
          context_ids: set[str] | None = None, _framing_observation=None) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else _blank(project)
        if isinstance(raw, Mapping):
            require_schema_version(raw, (AUTHORING_SCHEMA,), owner=f"Authoring state {path}", allow_untagged=True)
        if _framing_observation is not None:
            _framing_observation.update(_raw_framing_projection(raw,project))
        if not contexts and isinstance(raw, Mapping):
            raw = {key: value for key, value in raw.items()
                   if key not in {"contexts", "context_blobs"}}
        state = _normalise(raw, project)
    except (OSError, json.JSONDecodeError):
        raise ValueError(f"authoring state is unreadable: {path}")
    stored_contexts = [dict(row) for row in state["contexts"]]
    blobs = state.get("context_blobs") or {}
    resolved_contexts = []
    for stored in stored_contexts:
        if context_ids is not None and stored.get('id') not in context_ids:
            continue
        context, missing = dict(stored), []
        for field in _CONTEXT_BLOB_FIELDS:
            value = context.get(field)
            reference = (value.get(_CONTEXT_BLOB_REF) if isinstance(value, Mapping)
                         and set(value) == {_CONTEXT_BLOB_REF} else None)
            if not isinstance(reference, str):
                continue
            if reference in blobs:
                identity, _raw = _context_blob_identity(blobs[reference])
                if identity == reference:
                    context[field] = blobs[reference]
                else:
                    missing.append({"field": field, "blob": reference,
                                    "reason": "content identity mismatch"})
            else:
                missing.append({"field": field, "blob": reference,
                                "reason": "content blob is unavailable"})
        if missing:
            context["storage"] = {"status": "MISSING", "missing_blobs": missing}
        resolved_contexts.append(context)
    state["contexts"] = resolved_contexts
    state["_stored_contexts"] = stored_contexts
    if context_ids is not None:
        state['_contexts_subset'] = True
    source = _source(project, repo_root)
    for ledger in _feedback_ledgers(path,source,project,repo_root):state=_with_feedback(state,ledger)
    return state


def _feedback_ledgers(path,source,project,repo_root):
    """The same existing feedback homes for projection and cache currentness."""
    ledgers=[path.parent/'feedback/feedback.jsonl']
    if source.get('manuscript_dir'):
        ledgers.append(_root(repo_root)/source['manuscript_dir']/'feedback/feedback.jsonl')
    # New request-bound origins stay in the registered project home when the
    # selected edition changes; legacy homes remain readable without migration.
    from laplace.pipeline import registry
    registered=registry.resolve(project,repo_root=_root(repo_root))
    if registered is not None and registered.manuscript_dir:
        ledgers.append(_root(repo_root)/registered.manuscript_dir/'feedback/feedback.jsonl')
    return list(dict.fromkeys(ledgers))


def _with_feedback(state: dict, ledger: Path) -> dict:
    """Project the existing feedback door into live authoring, without copying it.

    An applied author edit is an example and protection, not unresolved work or
    permission to infer a general rule. Model revisions have distinct provenance.
    """
    if not ledger.is_file():
        return state
    records = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
            if isinstance(row, dict):
                records.append(row)
        except ValueError:
            continue
    retired = {row.get("supersedes") for row in records if row.get("supersedes")}
    linked = {row.get("feedback_id"): row for row in state["corrections"] if row.get("feedback_id")}
    for row in records:
        if row.get('record')=='feedback-origin-settlement':continue
        ident = row.get("id")
        if not ident:
            continue
        if row.get('authoring_origin'):
            from laplace.pipeline.correction_origin import projection
            projected=projection(row)
            if ident in retired:projected['status']='superseded'
            if row.get('project')!=state['project']:
                raise ValueError('Canonical comment origin belongs to another project.')
            if ident not in linked:
                state['corrections'].append(projected);linked[ident]=projected
            else:
                linked[ident].update({key:projected[key] for key in
                    ('status','status_note','status_history')})
            state['revision']=max(state['revision'],row['authoring_origin']['authoring_revision'])
            continue
        if ident in retired:continue
        if ident in linked:
            if row.get("status") in {"open", "resolved", "dismissed"}:
                linked[ident]["status"] = row["status"]
            for field in ("status_note", "status_history"):
                if field in row:
                    linked[ident][field] = row[field]
            continue
        kind = row.get("record") or row.get("kind") or "note"
        edit = kind in {"author-edit", "author-rewrite", "author-exemplar",
                        "author-structure", "source-edit"} or bool(row.get("hunks"))
        actor = str(row.get("by") or row.get("source") or "")
        if actor.startswith(("eigen", "machine", "pipeline", "author:accepted-model")):
            continue
        anchor = row.get("anchor") or {}
        anchor = dict(anchor) if isinstance(anchor, dict) else {"file": str(anchor)}
        anchor.setdefault("file", row.get("file") or "")
        anchor.setdefault("section", row.get("section") or "")
        text = str(row.get("text") or row.get("comment") or "Author changed this passage.")
        before, after = row.get("before", anchor.get("before")), row.get("after", anchor.get("after"))
        # THE RULING, INTO THE CONTEXT (WRITING-CONSOLIDATION-W1). A keep/cut/rework ruling
        # the author left on a passage is the strongest instruction in the ledger and it was
        # invisible to a session: this projection is what `build_context` reads
        # (`_active_corrections`, :1105) and the only read a session is told about for these
        # rows is `author_history {view: corrections}` --- the `note` home's own declared read
        # (`grammar.HOME_KINDS["note"].read`). Carried from the anchor, where the door banks
        # it, and ABSENT when the row carries none, so no existing row changes shape.
        ruling = {key: anchor[key] for key in ("disposition", "altitude")
                  if isinstance(anchor.get(key), str) and anchor.get(key)}
        state["corrections"].append({**ruling, "id": ident, "feedback_id": ident,
            "kind": kind if kind in {"author-structure", "source-edit"} else "author-edit" if edit else kind,
            "origin_kind": kind, "scope": "passage" if any(anchor.values()) else "project",
            "anchor": anchor, "text": text, "before": before, "after": after,
            "hunks": row.get("hunks", []),
            **({"baseline":dict(row["baseline"])} if isinstance(row.get("baseline"), Mapping) else {}),
            "by": actor, "created": row.get("ts"),
            "status": row.get("status", "open"), "status_note": row.get("status_note"),
            "status_history": list(row.get("status_history") or []),
            "applied": edit, "context_role": anchor.get("context_role") or ("observation-only" if anchor.get("feedback_effect") == "observation_only" else None),
            "feedback_target": anchor.get("feedback_target"), "feedback_effect": anchor.get("feedback_effect"),
            "_ledger_projection": True})
    return state


def _write(path: Path, state: Mapping[str, Any]) -> None:
    if state.get('_contexts_subset'):
        raise ValueError('A targeted context read cannot overwrite the complete authoring state.')
    require_schema_version(state, (AUTHORING_SCHEMA,), owner=f"Authoring state {path}", allow_untagged=True)
    blobs = dict(state.get("context_blobs") or {})
    prior = {row.get("id"): row for row in state.get("_stored_contexts") or []
             if isinstance(row, Mapping) and row.get("id")}
    contexts = []
    for context in state["contexts"]:
        if context.get("id") in prior:
            # Context receipts are immutable. Reuse their exact legacy or
            # reference-bearing representation instead of opportunistically
            # rewriting history during an unrelated save.
            contexts.append(dict(prior[context["id"]]))
            continue
        encoded = {key: value for key, value in context.items() if key != "storage"}
        for field in _CONTEXT_BLOB_FIELDS:
            if field not in encoded:
                continue
            value = encoded[field]
            identity, raw = _context_blob_identity(value)
            if len(raw) < _CONTEXT_BLOB_MIN_BYTES:
                continue
            if identity in blobs and _context_blob_identity(blobs[identity])[0]!=identity:
                raise ValueError('Stored context body conflicts with its content identity; inspect retained state before publishing another context.')
            blobs.setdefault(identity, value)
            encoded[field] = {_CONTEXT_BLOB_REF: identity}
        contexts.append(encoded)
    stored = {key: value for key, value in state.items() if not key.startswith("_")}
    stored.update(contexts=contexts, context_blobs=blobs,
                  corrections=[row for row in state["corrections"]
                               if not row.get("_ledger_projection")])
    if not blobs:
        stored.pop("context_blobs", None)
    encoded = json.dumps(stored, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=".authoring-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        deadline = time.monotonic() + 1.0
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                # Windows readers and filesystem scanners can briefly prevent rename.
                # Keep the old file intact and retry only sharing/access conflicts.
                # A persistent failure is raised; no unlink/copy gap or partial file.
                if os.name != "nt" or getattr(exc, "winerror", None) not in (5, 32) or time.monotonic() >= deadline:
                    raise
                time.sleep(.01)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _public(state: Mapping[str, Any], source: Mapping[str, Any] | None = None) -> dict[str, Any]:
    out = {
        "project": state["project"], "revision": state["revision"],
        "argument_revision": state["argument_revision"], "argument": state["argument"],
        # The duplicate name lets a nested future representation remain compatible
        # with the current panel contract.
        "argument_text": state["argument"], "framing": dict(state["framing"]),
        "section_ids": list(state["section_ids"]), "corrections": [dict(x) for x in state["corrections"]],
        "contexts": [dict(x) for x in state["contexts"]],
    }
    if source is not None:
        out["document"] = dict(source)
    return out


def load(project: str, repo_root: Path | str | None = None) -> dict[str, Any]:
    """Load one complete atomic authoring snapshot without mutating the checkout.

    Saves publish with ``os.replace``, so a reader observes the complete old or
    new file.  It must not create a lock file: exported projects can be mounted
    read-only for inspection while mutation owners retain ``_locked``.
    """
    path, source = _state_path(project, repo_root)
    state = _read(path, project, repo_root)
    return _public(state, source)


_FRAMING_FIELDS = ('project','revision','argument_revision','argument','framing','section_ids')


def _raw_framing_projection(raw,project):
    """Canonical raw fields only; feedback/history projection cannot set this head."""
    state=_normalise({key:value for key,value in raw.items()
        if key not in {'corrections','contexts','context_blobs'}} if isinstance(raw,Mapping) else raw,project)
    return {key:state[key] for key in _FRAMING_FIELDS}


def _file_signature(path):
    try:
        stat=path.stat()
        return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
    except FileNotFoundError:return None


def _remember_history_projection(root,key,stamp,metadata,cut):
    """Bound the existing disposable metadata cache; retain no historical bodies."""
    metadata={**metadata,'_cache_root':str(_root(root))}
    _HISTORY_CACHE.pop(key,None);_HISTORY_CACHE[key]=(stamp,metadata,cut)
    # Root recency follows its most recently touched path, not its oldest path.
    roots=list(dict.fromkeys(value[1].get('_cache_root') for value in reversed(tuple(_HISTORY_CACHE.values()))))[::-1]
    while len(roots)>4:
        retired=roots.pop(0)
        for old in [name for name,value in _HISTORY_CACHE.items() if value[1].get('_cache_root')==retired]:
            _HISTORY_CACHE.pop(old,None)
    for owner in roots:
        paths=[name for name,value in _HISTORY_CACHE.items() if value[1].get('_cache_root')==owner]
        for old in paths[:-64]:_HISTORY_CACHE.pop(old,None)


def summary(project: str, repo_root: Path | str | None = None, *, _source=None) -> dict[str, Any]:
    """Compact raw framing, reused only while its canonical state file is unchanged.

    The first/changed read still parses the existing JSON. Warm reads retain only
    these current fields in the existing history metadata cache. Feedback has a
    separate signature/purpose and cannot set framing; no header file or store is
    created. Returned nested values are detached from the disposable cache.
    """
    path, _source = _state_path(project, repo_root, _observed_source=_source)
    key=str(path)
    with _HISTORY_LOCK:
        for _ in range(3):
            stamp=(str(path),_file_signature(path));cached=_HISTORY_CACHE.get(key)
            same=bool(cached and cached[0] and cached[0][0]==stamp
                and cached[1].get('project')==project)
            if same and '_framing' in cached[1]:
                _HISTORY_CACHE.pop(key);_HISTORY_CACHE[key]=cached
                return copy.deepcopy(cached[1]['_framing'])
            try:raw=json.loads(path.read_text(encoding='utf-8')) if stamp[1] is not None else _blank(project)
            except (OSError,json.JSONDecodeError) as exc:
                raise ValueError(f'authoring state is unreadable: {path}') from exc
            header=_raw_framing_projection(raw,project)
            if stamp!=(str(path),_file_signature(path)):continue
            # Preserve an existing history cut only if its raw state pin still
            # matches. History itself checks its full feedback signature later.
            metadata={**cached[1],'_framing':header} if same else {'project':project,'_framing':header}
            pins=cached[0] if same else [stamp]
            cut=cached[2] if same else 'authoring-cut:'+hashlib.sha256(json.dumps(pins).encode()).hexdigest()
            _remember_history_projection(repo_root,key,pins,metadata,cut)
            return copy.deepcopy(header)
    raise ValueError('CHANGED_INPUT: authoring state changed while reading framing; refresh the review.')


_HISTORY_CACHE: dict[str, tuple] = {}
_HISTORY_LOCK = threading.RLock()
CORRECTION_CATEGORIES = ("passage-comments", "project-notes", "global-notes", "applied-edits", "other")
CORRECTION_STATUSES = ("open", "resolved", "dismissed", "superseded", "unknown")


def correction_history_contract() -> dict:
    """Correction fields shared by the HTTP and declared native history read."""
    return {"correction_category": {"enum": list(CORRECTION_CATEGORIES) + ["notes"]},
            "status": {"enum": list(CORRECTION_STATUSES) + ["closed"]},
            "order": {"enum": ["oldest", "newest"]}}


def correction_category(row: Mapping) -> str:
    if row.get("applied") or isinstance(row.get("kind"), str) and row["kind"] in {
            "direct-edit", "author-edit", "author-structure", "source-edit"}:
        return "applied-edits"
    scope = row.get("scope")
    return ({"passage": "passage-comments", "project": "project-notes",
             "global": "global-notes"}.get(scope, "other") if isinstance(scope, str) else "other")


def _correction_status(row: Mapping) -> str:
    value = row.get("status", "open")
    return value if value in CORRECTION_STATUSES else "unknown"


def _history_snapshot(project: str, repo_root=None, *, exact: bool = False, path_source=None) -> tuple[dict, dict, str]:
    """Shallow, read-only projection; cache is disposable, never an authority store."""
    path, source = path_source if path_source is not None else _state_path(project, repo_root)
    ledgers = _feedback_ledgers(path,source,project,repo_root)
    def signature():
        rows = []
        for name in [path, *ledgers]:
            rows.append((str(name), _file_signature(name)))
        return rows
    with _HISTORY_LOCK:
        for _ in range(3):
            stamp = signature()
            key = str(path)
            cached = _HISTORY_CACHE.get(key)
            if not exact and cached and cached[0] == stamp and "corrections" in cached[1]:
                _HISTORY_CACHE.pop(key);_HISTORY_CACHE[key]=cached
                return cached[1], source, cached[2]
            framing={}
            state = _read(path, project, repo_root, contexts=False,_framing_observation=framing)
            if stamp != signature(): continue
            cut = "authoring-cut:" + hashlib.sha256(json.dumps(stamp).encode()).hexdigest()
            metadata = {"project": project, "revision": state["revision"],"_framing":framing,
                        "corrections": [_correction_summary(row) for row in state["corrections"]]}
            # A list read retains only metadata in memory, not a second copy of
            # every historical manuscript preimage. Exact detail reparses its
            # existing owner files on request, without resolving context blobs.
            _remember_history_projection(repo_root,key,stamp,metadata,cut)
            if not exact: state = metadata
            return state, source, cut
    raise ValueError("CHANGED_INPUT: author history changed while reading; refresh the review.")


def _correction_summary(row: Mapping) -> dict:
    text = str(row.get("text") or "")
    anchor = row.get("anchor") if isinstance(row.get("anchor"), Mapping) else {}
    # Source bodies can be nested in old anchors as well as in the row itself.
    safe_anchor = {key: anchor[key] for key in
                   ("file", "section", "section_id", "node_id", "asset_id")
                   if isinstance(anchor.get(key), str)}
    safe_anchor.update({key: anchor[key] for key in ("line_start", "line_end")
                        if isinstance(anchor.get(key), int) and not isinstance(anchor[key], bool)})
    if (isinstance(anchor.get("lines"), list) and len(anchor["lines"]) == 2
            and all(isinstance(value, int) and not isinstance(value, bool) for value in anchor["lines"])):
        safe_anchor["lines"] = list(anchor["lines"])
    return {"instruction_eligible":_correction_can_constrain(row),**{key: row.get(key) for key in
               ("id", "kind", "scope", "by", "created", "applied", "context_role", "reply_to", "supersedes", "feedback_effect", "feedback_target")},
            "anchor": safe_anchor, "text": text[:1200], "text_truncated": bool(row.get("text_truncated")) or len(text) > 1200,
            "text_characters": row.get("text_characters", len(text)), "status": _correction_status(row),
            "correction_category": correction_category(row),
            "has_source_edit": bool(row.get("has_source_edit") or row.get("before") is not None or row.get("after") is not None or row.get("hunks")),
            "detail": {"id": row.get("id")},
            **({'origin_ref':row['origin_ref'],'has_review_route':bool(row.get('has_review_route') or row.get('review_route_spec'))}
               if row.get('origin_ref') else {})}


def history(project: str, payload: Mapping[str, Any] | None = None,
            repo_root: Path | str | None = None) -> dict[str, Any]:
    """Bounded correction/history inspection; full source edits require an exact ID."""
    payload = payload or {}
    if not isinstance(payload, Mapping):
        raise ValueError("author_history payload must be an object")
    state, source, cut = _history_snapshot(project, repo_root, exact=bool(payload.get("id")))
    if payload.get("as_of") and payload["as_of"] != cut:
        raise ValueError("CHANGED_INPUT: author history changed after this page was read. Refresh to read current records.")
    rows = state["corrections"]
    counts = {category: {status: 0 for status in CORRECTION_STATUSES} for category in CORRECTION_CATEGORIES}
    for row in rows: counts[correction_category(row)][_correction_status(row)] += 1
    common = {"project": project, "revision": state["revision"], "as_of": cut,
              "counts": counts, "document": source}
    ident = str(payload.get("id") or "").strip()
    if ident:
        row = next((row for row in rows if row.get("id") == ident), None)
        if row is None:
            raise ValueError("author history item is unavailable")
        return {**common, "item": {**row, "correction_category": correction_category(row)}}
    raw_file = str(payload.get("file") or "").strip()
    if raw_file:
        rows = [row for row in rows if str((row.get("anchor") or {}).get("file") or "").endswith(raw_file)]
    for key, schema in correction_history_contract().items():
        if payload.get(key) and payload[key] not in schema["enum"]:
            raise ValueError("author_history " + key + " must be one of " + ", ".join(schema["enum"]))
    if payload.get("correction_category"):
        rows = [row for row in rows if (correction_category(row) != "applied-edits"
                                       if payload["correction_category"] == "notes"
                                       else correction_category(row) == payload["correction_category"])]
    if payload.get("status"):
        rows = [row for row in rows if (_correction_status(row) != "open" if payload["status"] == "closed"
                                       else _correction_status(row) == payload["status"])]
    if payload.get("order") == "newest": rows = list(reversed(rows))
    try:
        offset = max(0, int(payload.get("offset", 0)))
        limit = max(1, min(25, int(payload.get("limit", 10))))
    except (TypeError, ValueError) as exc:
        raise ValueError("author_history offset and limit must be integers") from exc
    page = rows[offset:offset + limit]
    return {**common, "file": raw_file or None, "items": [_correction_summary(row) for row in page],
            "offset": offset, "next_offset": offset + len(page) if offset + len(page) < len(rows) else None,
            "limit": limit, "total": len(rows), "omitted": len(rows) - len(page)}


def pending_author_updates(project:str,selection:Mapping[str,Any]|None,consumed_ids,
                           repo_root:Path|str|None=None)->list[dict[str,Any]]:
    """Shallow current human updates for one active turn/tool boundary.

    This does not read manuscript bodies or mark anything consumed.  Exact
    acknowledgement remains an ``author_history {id}`` read followed by the
    ordinary context-refresh guard.
    """
    state,_source,_cut=_history_snapshot(project,repo_root)
    selection=dict(selection or {});files=selection.get("files") or []
    if isinstance(files,str):files=[files]
    selected=[{"file":str(file),"line_start":selection.get("line_start"),
               "line_end":selection.get("line_end"),"text":""} for file in files]
    consumed={str(item) for item in consumed_ids or []}
    rows=[]
    for row in _active_corrections(state,selected,selection):
        if row.get("id") in consumed or str(row.get("by") or "").startswith("eigen:"):continue
        rows.append({key:row.get(key) for key in
            ("id","created","text","kind","scope","anchor","by","context_role","reply_to")})
    return rows


def _expected(payload: Mapping[str, Any]) -> int | None:
    for key in ("base_revision", "expected_revision", "revision"):
        if key in payload and payload[key] is not None:
            try:
                return int(payload[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be an integer")
    return None


def _assert_current(state: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
    expected = _expected(payload)
    if expected is not None and expected != state["revision"]:
        raise ValueError(f"revision conflict: expected {expected}, current {state['revision']}")


def save(project: str, payload: Mapping[str, Any], repo_root: Path | str | None = None) -> dict[str, Any]:
    """Atomically save an author-directed argument/framing change.

    ``base_revision`` is the UI's optimistic guard.  The aliases
    ``expected_revision`` and ``revision`` keep older callers compatible.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("authoring save payload must be an object")
    path, source = _state_path(project, repo_root)
    with _locked(path):
        state = _read(path, project, repo_root)
        _assert_current(state, payload)
        changed_argument = False
        if "argument" in payload or "argument_text" in payload:
            candidate = payload.get("argument", payload.get("argument_text"))
            if isinstance(candidate, Mapping):
                candidate = candidate.get("text")
            if not isinstance(candidate, str):
                raise ValueError("argument must be text")
            if candidate != state["argument"]:
                state["argument"] = candidate
                changed_argument = True
        if "framing" in payload:
            framing = _framing(payload["framing"])
            if framing != state["framing"]:
                state["framing"] = framing
                changed_argument = True
        if "section_ids" in payload:
            state["section_ids"] = _strings(payload["section_ids"])
        if changed_argument:
            state["argument_revision"] += 1
        if changed_argument or "section_ids" in payload:
            state["revision"] += 1
            _write(path, state)
    return _public(state, source)


def _revision(traversal: Mapping[str, Any]) -> str:
    digest = hashlib.sha256()
    for source in traversal.get("sources", []):
        if not isinstance(source, Mapping):
            continue
        digest.update(str(source.get("file") or "").encode())
        digest.update(b"\0")
        digest.update(str(source.get("text") or "").encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _selection_ids(selection: Any, default: list[str]) -> list[str]:
    if selection is None:
        return default
    if isinstance(selection, Mapping):
        values: list[str] = []
        for key in ("section_ids", "sections", "files", "ids", "selection"):
            if key in selection:
                values.extend(_strings(selection[key]))
        return list(dict.fromkeys(values))
    return _strings(selection)


def _source_matches(source: Mapping[str, Any], wanted: str) -> bool:
    file_name = str(source.get("file") or "")
    if wanted and not Path(wanted).is_absolute() and ".." not in Path(wanted).parts and file_name.endswith("/" + wanted):
        return True
    names = {file_name, Path(file_name).name, Path(file_name).stem, str(source.get("section_id") or "")}
    try:
        from laplace.pipeline import pathsafe
        return wanted in names or pathsafe.encode_sid_for_path(wanted) == Path(file_name).stem
    except Exception:
        return wanted in names


def _span(source: dict[str, Any], selection: Any) -> dict[str, Any]:
    """Apply a UI line/quote span without reducing a selected source by quota."""
    if not isinstance(selection, Mapping) or not any(key in selection for key in ("line_start", "line_end", "quote")):
        return source
    start, end = selection.get("line_start"), selection.get("line_end")
    lines = str(source.get("text") or "").splitlines(keepends=True)
    if isinstance(start, int) or isinstance(end, int):
        lower = max(1, int(start or 1))
        upper = min(len(lines), int(end or len(lines)))
        if lower <= upper:
            source["text"] = "".join(lines[lower - 1:upper])
            source["line_start"], source["line_end"] = lower, upper
            return source
    quote = selection.get("quote")
    if isinstance(quote, str) and quote.strip():
        text = str(source.get("text") or "")
        position = text.find(quote)
        if position >= 0:
            if text.find(quote,position+len(quote))>=0:
                raise ValueError("selection quote occurs more than once; provide exact line_start and line_end")
            before = text[:position]
            source["text"] = quote
            source["line_start"] = before.count("\n") + 1
            source["line_end"] = source["line_start"] + quote.count("\n")
    return source


def _numbered(source: Mapping[str, Any]) -> str:
    """Address guide for a source projection; prefixes are not manuscript text."""
    start = int(source.get("line_start") or 1)
    return "\n".join(f"{start + index:06d} | {line}"
                     for index, line in enumerate(str(source.get("text") or "").split("\n")))


def _scope(traversal: Mapping[str, Any], selection: Any, default: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    sources = [dict(x) for x in traversal.get("sources", []) if isinstance(x, Mapping)]
    # `raw_file_sha256` and `full_text_sha256` are DELETED, not deprecated.  They were two
    # more names for the value already published as `sha256` -- the `source-file` home -- and
    # the census measured all three carrying one value (ea5a8867..., three names).  Two of the
    # twenty go here.  The token for this home is published in `identities` on each row.
    # The digest of the file's TEXT is still needed by :731, because `text` is narrowed to the
    # read's own excerpt for a partial read and the structural writers compare the WHOLE file
    # (manuscript_structure.py:541, :923).  It is computed here, where the full text is still in
    # hand, into a private key that :731 consumes and removes, so the response carries one name
    # for it instead of two (caught by tests/test_manuscript_blocks.py::
    # test_partial_source_read_returns_full_file_guard_consumed_by_block_change).
    # `sha256` -- the one name the `source-file` home keeps -- is a row of
    # `identity_doors.RETAINED`, with the same dated expiry as the shim beside it.
    for source in sources:
        # SHIM, expires with identity_doors.EXPIRY.  `raw_file_sha256` is NOT a duplicate
        # publication: it is an ASKED-FOR name.  `help visual_place` names it as the field
        # `base_revision` is copied from (src/laplace/writing_contracts.py:170) and the published
        # arrival sequence copies it three times
        # (evidence/WRITING_FRICTION_2026-10-01/wave1/arrival-replay/replay_arrival.py:464, :616,
        # :795-796).  Deleting it sent two of those callers an empty guard and added two arrival
        # refusals, F3-section-create-doors and I7-visual-place, which is how this was measured
        # rather than argued.  It is deleted the moment those callers copy the token from this
        # row's `identities` instead; `sha256` is the one name this home keeps meanwhile, and
        # visual_place's own refusal now says so (src/laplace/visuals_surface.py:356-363).
        source["raw_file_sha256"] = source.get("sha256")
        source["_full_text_identity"] = _digest(str(source.get("text") or ""))
    wanted = _selection_ids(selection, default)
    selected = [s for s in sources if any(_source_matches(s, item) for item in wanted)]
    # No implicit whole-book dump. The UI must choose a meaningful scope, but the
    # response still exposes the source inventory needed to make that choice.
    if not selected:
        return [], [], wanted
    indices = {int(s.get("order", -1)) for s in selected}
    # A multi-section selection owns the complete connected document stretch
    # between its endpoints.  This prevents a user-selected argument from being
    # split into isolated paragraphs merely because an intermediate source file
    # was not named again in the UI gesture.
    lower, upper = min(indices), max(indices)
    explicit_files = (isinstance(selection, Mapping) and bool(selection.get("files"))
                      and not any(key in selection for key in
                                  ("section_ids", "sections", "ids", "selection",
                                   "line_start", "line_end", "quote")))
    # A plain physical file list is not a gesture spanning the document. Reading
    # the shared root and chapter three must not silently include chapters one
    # and two. Preserve the connected semantics for section/range gestures.
    if not explicit_files:
        selected = [s for s in sources if lower <= int(s.get("order", -1)) <= upper]
    # One line interval cannot address several different files. Keep the whole
    # connected stretch; the quoted passage remains the target in the prompt.
    if len(selected) == 1:
        selected = [_span(selected[0], selection)]
    boundaries = [s for s in sources if int(s.get("order", -1)) in {lower - 1, upper + 1}]
    # The private digest is for the SELECTED rows' one published guard; a boundary excerpt is
    # context, not an editable span, and must not carry an identity field at all.
    for row in boundaries:
        row.pop("_full_text_identity", None)
    return selected, boundaries, wanted


def _glossary(project: str, root: Path) -> list[dict[str, str]]:
    """Read canonical ``def:`` objects; rendered glossary lines are not identities."""
    try:
        from laplace.pipeline import verify
        network, _ = verify._load_corpus_network(project, None, root)   # workspace=root: the project's own registry, tex and overlay
    except Exception:  # canonical glossary absent is an honest empty context
        return []
    entries: list[dict[str, str]] = []
    for ident, node in sorted((network or {}).get("nodes", {}).items()):
        if not ident.startswith("def:"):
            continue
        projection = node.get("projection") or (node.get("meta") or {}).get("projection") or {}
        term = projection.get("term")
        if isinstance(term, str) and term.strip():
            entries.append({"id": ident, "term": term.strip(), "aliases": list(projection.get("aliases") or [])})
    return entries


def _writing_style(project: str, root: Path) -> tuple[dict | None, dict | None]:
    try:
        from laplace.manuscript import writing_style
        context = writing_style.context(project, root)
    except (ValueError, OSError):
        return None, None
    identity = {key: context.get(key) for key in
                ("revision", "selected_profile", "profile_revision", "profile_origin")}
    identity["guidance_sha256"] = hashlib.sha256(
        str(context.get("guidance") or "").encode()).hexdigest()
    return context, identity


def _correction_can_constrain(correction:Mapping[str,Any])->bool:
    """Whether this row is an authoring dependency rather than durable history."""
    if correction.get("feedback_effect") == "observation_only": return False
    feedback_anchor = correction.get("anchor") if isinstance(correction.get("anchor"), Mapping) else {}
    target = correction.get("feedback_target") or feedback_anchor.get("feedback_target")
    if target is not None:
        from laplace.work.feedback import TARGET_SCHEMA
        try:
            require_schema_version(target, (TARGET_SCHEMA,), owner="Correction feedback target")
        except ValueError:
            return False  # Preserve unknown retained feedback as history, never as an interpreted instruction.
    role=str(correction.get("context_role") or "")
    if role:return role not in {"agent-history", "observation-only"}
    by=str(correction.get("by") or "author")
    return not (by.startswith("eigen:") and correction.get("scope")=="project")


def _correction_applies(correction: Mapping[str, Any], selected: list[Mapping[str, Any]],
                        selection:Mapping[str,Any]|None=None) -> bool:
    if not _correction_can_constrain(correction):return False
    scope = correction.get("scope")
    if scope in {"project", "global"}:
        return True
    anchor = correction.get("anchor") if isinstance(correction.get("anchor"), Mapping) else {}
    node_id=str(anchor.get("node_id") or "")
    if node_id and isinstance(selection,Mapping):
        selected_nodes={str(selection.get("node_id") or "")}
        selected_nodes.update(str(item) for item in selection.get("node_ids") or [])
        if node_id in selected_nodes:return True
    targets = [str(anchor.get(key) or "") for key in ("file", "section_id", "section")]
    if not any(targets):
        return False
    anchor_start, anchor_end = anchor.get("line_start"), anchor.get("line_end")
    for source in selected:
        if not any(_source_matches(source, target) for target in targets if target):
            continue
        # Source line numbers and ordinal block ids move when chapters or figures
        # are inserted. Reattach a surviving passage before consulting old offsets.
        passage = str(anchor.get("quote") or correction.get("after") or anchor.get("after") or "").strip()
        if passage and passage in str(source.get("text") or ""):
            return True
        source_start, source_end = source.get("line_start"), source.get("line_end")
        if not all(isinstance(item, int) for item in (anchor_start, anchor_end, source_start, source_end)):
            return True
        if max(anchor_start, source_start) <= min(anchor_end, source_end):
            return True
    return False


def _active_corrections(state: Mapping[str, Any], selected: list[Mapping[str, Any]],
                        selection:Mapping[str,Any]|None=None) -> list[dict[str, Any]]:
    return [dict(row) for row in state["corrections"]
            if row.get("status", "open") == "open" and not row.get("applied")
            and _correction_applies(row, selected,selection)]


#: How much adjacent prose orients a join at each altitude asked for.  The code's own
#: comment is that "Boundaries orient joins" (:1312); 2,000 characters of a neighbouring
#: chapter is not orientation for a three-line edit, and the friction lane measured the
#: whole boundary part at 2,110 characters for that paragraph and 137,568 for a chapter.
#: The whole neighbour stays one `source` read away (``_DELIVERY_PART_READS``).
_BOUNDARY_WINDOW = {"passage": 400, "paragraph": 400, "section": 1000, "chapter": 2000, "manuscript": 2000}


def _boundary_text(source: Mapping[str, Any], selected: list[Mapping[str, Any]],
                   altitude: str = "manuscript") -> tuple[str, str]:
    text = str(source.get("text") or "")
    window = _BOUNDARY_WINDOW.get(altitude, 2000)
    side = "before" if selected and int(source.get("order", 0)) < int(selected[0].get("order", 0)) else "after"
    return (text[-window:] if side == "before" else text[:window]), side


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _source_dependencies(selected: list[Mapping[str, Any]], boundaries: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deps = [{"file": str(item.get("file")), "order": item.get("order"), "role": "selected",
             "line_start": item.get("line_start"), "line_end": item.get("line_end"),
             "digest": _digest(str(item.get("text") or ""))} for item in selected]
    for item in boundaries:
        text, side = _boundary_text(item, selected)
        deps.append({"file": str(item.get("file")), "order": item.get("order"), "role": f"boundary-{side}",
                     "digest": _digest(text)})
    return deps


def _dependency_current(dep: Mapping[str, Any], traversal: Mapping[str, Any]) -> str | None:
    source = next((item for item in traversal.get("sources", [])
                   if isinstance(item, Mapping) and item.get("file") == dep.get("file") and item.get("order") == dep.get("order")), None)
    if source is None:
        return None
    text = str(source.get("text") or "")
    if dep.get("role") == "selected" and isinstance(dep.get("line_start"), int):
        lines = text.splitlines(keepends=True)
        text = "".join(lines[dep["line_start"] - 1:int(dep.get("line_end") or len(lines))])
    elif str(dep.get("role") or "").startswith("boundary-"):
        text = text[-2000:] if dep["role"] == "boundary-before" else text[:2000]
    return _digest(text)


def _staleness(state: Mapping[str, Any], traversal: Mapping[str, Any],
               writing_style_identity: Mapping[str, Any] | None = None,
               protocol_revision: str | None = None) -> list[dict[str, Any]]:
    stale: list[dict[str, Any]] = []
    for context in state["contexts"]:
        reasons: list[str] = []
        dependencies = context.get("source_dependencies") or []
        if dependencies:
            changed = [str(dep.get("file")) for dep in dependencies
                       if isinstance(dep, Mapping) and _dependency_current(dep, traversal) != dep.get("digest")]
            reasons.extend(f"source-revision-changed:{file}" for file in sorted(set(changed)))
        elif context.get("source_revision") != _revision(traversal):
            reasons.append("source-revision-changed")  # legacy receipt, minted before per-source dependencies
        if context.get("argument_revision") != state["argument_revision"]:
            reasons.append("argument-or-framing-changed")
        if ("writing_style" in context and
                context.get("writing_style") != writing_style_identity):
            reasons.append("writing-style-profile-or-guidance-changed")
        if context.get("project_protocol_revision", protocol_revision) != protocol_revision:
            reasons.append("project-working-guide-changed")
        selected = context.get("selection_spans") or [{"file": item} for item in context.get("selection", [])]
        scope=context.get("structure_scope") if isinstance(context.get("structure_scope"),Mapping) else None
        current_ids = {row.get("id") for row in _active_corrections(state, selected,scope)}
        consumed = set(context.get("consumed_correction_ids") or [])
        new_corrections = sorted(str(item) for item in current_ids - consumed if item)
        if new_corrections:
            reasons.extend(f"correction-unconsumed:{item}" for item in new_corrections)
        eligible={row.get("id") for row in state["corrections"] if _correction_can_constrain(row)}
        retired_corrections = sorted(str(item) for item in (consumed - current_ids) & eligible if item)
        reasons.extend(f"correction-retired:{item}" for item in retired_corrections)
        if reasons:
            stale.append({"context_id": context.get("id"), "selection": context.get("selection", []), "reasons": reasons})
    return stale


def _structure_semantic_identity(value):
    """Structure identity after removing whole-edition source revision carriers.

    Scoped source_dependencies already guard selected/boundary prose. Keeping a
    second whole-file source hash here would veto unrelated edits in the same file.
    """
    from laplace.manuscript.project_structure import semantic_content
    return semantic_content(value)


def inspect(project: str, selection: Any = None, repo_root: Path | str | None = None,
            *, context_id: str | None = None, _source_observation: dict | None = None) -> dict[str, Any]:
    """Inspect current source and the requested dependency receipt.

    None checks historical receipts for the inspection UI; a nonempty ID checks
    that receipt alone. An empty ID reads fresh source without auditing history.
    Reading source or constructing a new context cannot require rebuilding every
    earlier conversation's dependency graph.
    """
    path, source = _state_path(project, repo_root)
    root = _root(repo_root)
    from laplace.manuscript import manuscript_source
    traversal = (manuscript_source.traversal(source["root"], repo_root=root)
                 if source.get("status") == "resolved" and source.get("root")
                 else {"root": None, "files": [], "sources": [], "includes": [],
                       "diagnostics": list(source.get("diagnostics") or ["no selected manuscript source"])})
    source_revision = _revision(traversal)
    if _source_observation is not None:
        # Internal output only: the validator shares this actual physical read,
        # never supplies a replacement traversal or serializes it into receipts.
        _source_observation.update(document=source,traversal=traversal)
    with _locked(path):
        state = _read(path, project, repo_root,contexts=context_id!='',
                      context_ids={context_id} if context_id else None)
    selected, boundaries, requested = _scope(traversal, selection, state["section_ids"])
    for item in selected:
        item["numbered_text"] = _numbered(item)
        # Every identity of this row, under the name of its own home.  The `source-file` home
        # is the file's exact bytes -- which is the value already published as `sha256`, so no
        # digest is computed here for it.
        from laplace.core import identity_doors
        item["identities"] = identity_doors.identities(
            ("source-file", "%s::%s" % (project, item.get("file") or ""), item.get("sha256")))
        # SHIM, expires with identity_doors.EXPIRY (retire on WRITING-RECONCILIATION replay
        # parity; review 2026-11-01).  `expected_source_digest` is an ASKED-FOR name published
        # as a read field: the writers at manuscript_structure.py:541 and :923 compare the
        # digest of the file's TEXT, so this value is kept until those callers send the token
        # in `expected` instead.  It is the one of the twenty that this lane could not delete
        # without stranding a caller whose schema does not yet carry `expected`.
        item["expected_source_digest"] = "sha256:" + str(item.pop("_full_text_identity", ""))
    active = _active_corrections(state, selected, selection if isinstance(selection, Mapping) else None)
    _style_context, style_identity = _writing_style(project, root)
    from laplace.manuscript import project_protocol
    protocol = project_protocol.load(project, root)
    receipts = state["contexts"] if context_id is None else [
        row for row in state["contexts"] if context_id and row.get("id") == context_id]
    stale = _staleness({**state, "contexts": receipts}, traversal, style_identity, protocol['revision'])
    glossary = _glossary(project, root) if any("glossary" in row for row in receipts) else None
    references_by_keys, structures_by_scope = {}, {}
    structure_state = None
    for receipt in receipts:
        if "references" not in receipt:
            continue
        if "glossary" in receipt and receipt["glossary"] != glossary:
            old = next((r for r in stale if r.get("context_id") == receipt["id"]), None)
            if old is None:
                old = {"context_id": receipt["id"], "selection": receipt.get("selection", []), "reasons": []}
                stale.append(old)
            old["reasons"].append("concept-glossary-changed")
        keys = tuple(receipt.get("source_ids") or [])
        if keys not in references_by_keys:
            references_by_keys[keys] = _reference_context(project, list(keys), root)
        now = references_by_keys[keys]
        if now != receipt["references"]:
            old = next((r for r in stale if r.get("context_id") == receipt["id"]), None)
            if old is None:
                old = {"context_id": receipt["id"], "selection": receipt.get("selection", []), "reasons": []}
                stale.append(old)
            old["reasons"].append("reference-association-changed")
        prior_structure = receipt.get("structure")
        if isinstance(prior_structure, Mapping):
            try:
                from laplace.manuscript import project_structure
                saved_scope = receipt.get("structure_scope")
                scope = dict(saved_scope) if isinstance(saved_scope, Mapping) else {
                    "files": receipt.get("selection", []),
                    "section_ids": [section.get("id") for section in
                                    prior_structure.get("sections", []) if section.get("id")]}
                if not isinstance(saved_scope, Mapping):
                    spans = receipt.get("selection_spans") or []
                    if len(spans) == 1:
                        scope.update({key: spans[0][key] for key in ("line_start", "line_end")
                                      if isinstance(spans[0].get(key), int)})
                if ((prior_structure.get("focus") or {}).get("node") or {}).get("id"):
                    scope["node_id"] = prior_structure["focus"]["node"]["id"]
                scope_key = json.dumps(scope, sort_keys=True, default=str)
                if scope_key not in structures_by_scope:
                    structures_by_scope[scope_key] = project_structure.context(project, scope, root)
                live_structure = structures_by_scope[scope_key]
            except ValueError:
                live_structure = None
            if live_structure is None or _structure_semantic_identity(live_structure) != _structure_semantic_identity(prior_structure):
                old = next((r for r in stale if r.get("context_id") == receipt["id"]), None)
                if old is None:
                    old = {"context_id": receipt["id"], "selection": receipt.get("selection", []), "reasons": []}
                    stale.append(old)
                old["reasons"].append("structure-plan-conceptric-or-evidence-changed")
    from laplace.core import identity_doors as _doors
    from laplace.native import declarations as writing_declarations
    return {
        "project": project, "revision": state["revision"], "source_revision": source_revision,
        # The two whole-project homes this read observes, each under its own name.  They were
        # five names over two values before, and the two values are DIFFERENT homes one letter
        # apart: `document.revision` is the selected edition's root-file bytes, while
        # `source_revision` is the whole traversal (`_revision`, :439-447, computed at :723 and
        # published here).  `help visual_place` warned about the confusion in prose; here it is
        # the name of the field.  The per-file `source-file` home is on each `sources[]` row.
        # Both scalars retained here -- `source_revision` and `document.revision` -- are rows
        # of `_doors.RETAINED`, each with its live consumer, what deletes it, and the dated
        # expiry the grammar validates.
        "identities": _doors.identities(
            ("selected-edition", project, source.get("revision")),
            ("source-traversal", project, source_revision)),
        "source_write_recipe": writing_declarations.source_write_guidance(),
        "document": source, "selection": [s.get("file") for s in selected],
        "requested_selection": requested, "sources": selected, "boundaries": boundaries,
        "inventory": [{"file": s.get("file"), "order": s.get("order")} for s in traversal.get("sources", [])],
        "diagnostics": traversal.get("diagnostics", []), "applicable_corrections": active,
        "stale": stale,
        "staleness_scope": "all" if context_id is None else {
            "context_id": context_id or None, "receipts_checked": len(receipts)},
    }


def _reference_context(project: str, keys: list[str], root: Path) -> list[dict]:
    source = _source(project, root)
    if not source.get("manuscript_dir"):
        return []
    path = root / source["manuscript_dir"] / "references.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [row for row in data.get("associations", []) if row.get("citekey") in keys]
    return [dict(row) for row in rows]


def _local_source_refs(project: str, structure: Mapping[str, Any] | None, root: Path) -> list[dict]:
    """Resolve explicit mathematical locators; no broad source traversal or guessed range."""
    if not isinstance(structure, Mapping):
        return []
    from laplace.research.mathematical_records import resolve_source
    refs = []
    for dependency in structure.get("direct_dependencies") or []:
        refs.extend((dependency.get("id"), ref) for ref in dependency.get("source_refs") or [])
    resolved, seen = [], set()
    for dependency, ref in refs:
        if ref is None:
            continue
        item = resolve_source(project, ref, root)
        if item.get("status") != "READ":
            continue
        key = (item.get("file"), item.get("sha256"), item.get("line_start"), item.get("line_end"))
        if key in seen:
            continue
        seen.add(key)
        resolved.append({"dependency": dependency, **{key: item.get(key) for key in
                        ("file", "sha256", "line_start", "line_end", "excerpt", "truncated",
                         "environment")}})
        if len(resolved) >= 12:
            break
    return resolved


_STRUCTURAL_FOCUS_KINDS = {"goal", "portal"}


def _prompt_node_identity(row: Mapping[str, Any], *, purpose: bool = False) -> dict[str, Any]:
    """A navigable identity for a structural overview, without copying its body.

    ``summary`` is the object's scientific/prose body in the canonical owner.  A
    group prompt needs that body once for the selected group's purpose, but not
    once per member.  Explicit titles/labels remain exact; an essence-derived
    label equal to the summary is omitted rather than character-truncated.
    """
    value = {key: row.get(key) for key in
             ("id", "title", "kind", "status", "grade", "parent", "has_children", "child_count")
             if row.get(key) is not None}
    summary = row.get("summary")
    label = row.get("label")
    if purpose and isinstance(summary, str) and summary:
        value["purpose"] = summary
    if isinstance(label, str) and label and label != summary:
        value["label"] = label
    elif not value.get("title"):
        value["label_available_via"] = {"operation": "concept", "payload": {"node": row.get("id")}}
    return value


def _prompt_containment_overview(containment: Mapping[str, Any], *, include_purpose: bool = True) -> dict[str, Any]:
    current = containment.get("current") if isinstance(containment.get("current"), Mapping) else {}
    descendants = [row for row in containment.get("descendants") or [] if isinstance(row, Mapping)]
    immediate = [row for row in descendants if row.get("depth") == 1]
    child_total = int(current.get("child_count") or len(immediate))
    residual = containment.get("omission_residual") if isinstance(
        containment.get("omission_residual"), Mapping) else {}
    dependency_projected = len(containment.get("dependencies") or [])
    dependency_total = dependency_projected + int(residual.get("dependencies_not_projected") or 0)
    node_id = current.get("id")
    return {
        "schema_version": "laplace.prompt-containment-overview/1",
        "authority": containment.get("authority"),
        "current": _prompt_node_identity(current, purpose=include_purpose),
        "immediate_parts": [_prompt_node_identity(row) for row in immediate],
        "immediate_parts_total": child_total,
        "immediate_parts_omitted": max(0, child_total - len(immediate)),
        "deeper_descendants_not_in_prompt": max(0, len(descendants) - len(immediate))
            + int(residual.get("queued_descendants_not_projected") or 0),
        "dependency_relations_total": dependency_total,
        "boundary_nodes_total": len(containment.get("boundary_nodes") or [])
            + int(residual.get("boundary_nodes_not_projected") or 0),
        "omission_residual": residual,
        "read_routes": {
            "parts_and_dependencies": {"operation": "concept_tree",
                                       "payload": {"node": node_id, "offset": 0, "limit": 40,
                                                   "dependency_offset": 0, "dependency_limit": 80}},
            "member": {"operation": "concept", "payload": {"node": "<immediate_part_id>"}},
        },
        "revision": containment.get("revision"),
    }


def delivery_altitude(selection: Any) -> str:
    """The requested delivery scope, independent of physical line count.

    Guarantee B of the consolidation campaign: the delivery is a function of the
    altitude asked for.  It is read from the selection and not from the resolved
    sources, because the traversal gives a whole-file read the same line_start and
    line_end as a passage read and the two are different questions.
    """
    if not isinstance(selection, Mapping):
        return "manuscript"
    files = [str(item) for item in (selection.get("files") or []) if str(item)]
    sections = [str(item) for item in (selection.get("section_ids") or selection.get("sections") or [])
                if str(item)]
    start, end = selection.get("line_start"), selection.get("line_end")
    if isinstance(start, int) and isinstance(end, int) and end >= start:
        return "passage"
    if isinstance(selection.get("quote"), str) and selection["quote"].strip():
        return "passage"
    if selection.get("node_id") or selection.get("node_ids") or len(sections) == 1:
        return "section"
    if len(files) == 1 and not sections:
        return "chapter"
    return "manuscript"


#: WHAT THE CANONICAL STRUCTURE PROJECTION CARRIES AT EACH ALTITUDE ASKED FOR.
#: ``full`` keys keep their bodies; ``identity`` keys are reduced to navigable
#: identities (every exact ID, title, number and source path retained); ``count``
#: keys become a total beside the read that returns the rows.  A paragraph gets its
#: section's structure, a section its chapter's, a chapter its book's.  Nothing is
#: dropped: ``_STRUCTURE_SCOPE_READS`` names the read for every reduced key and the
#: projection carries that name, so a withheld fact is one declared call away.
_STRUCTURE_ALTITUDE = {
    "paragraph": {"full": ("sections",),
                  "identity": ("children",),
                  "count": ("ancestors", "boundaries", "outline", "edges", "gaps",
                            "scoped_history", "source_support")},
    "section": {"full": ("sections", "edges", "source_support"),
                "identity": ("children", "ancestors", "boundaries"),
                "count": ("outline", "gaps", "scoped_history")},
    "chapter": {"full": ("sections", "children", "ancestors", "edges", "source_support",
                         "gaps", "scoped_history"),
                "identity": ("boundaries", "outline"),
                "count": ()},
    "manuscript": {"full": ("sections", "children", "ancestors", "edges", "source_support",
                            "gaps", "scoped_history"),
                   "identity": ("boundaries", "outline"),
                   "count": ()},
}

# Historical projection callers may still ask for paragraph. A selected span is
# honestly a passage; neither its length nor TeX formatting proves semantic containment.
_STRUCTURE_ALTITUDE["passage"] = _STRUCTURE_ALTITUDE["paragraph"]

#: The declared read that reaches each reduced key's own rows.  Every operation here is
#: a deployed read of ``writing_tools.READS``; the delivery carries this route beside the
#: total, which is the information rule of guarantee B.
_STRUCTURE_SCOPE_READS = {
    "sections": {"operation": "structure", "payload": {"section_ids": ["<section_id>"]}},
    "children": {"operation": "structure", "payload": {"section_ids": ["<section_id>"]}},
    "ancestors": {"operation": "structure", "payload": {"section_ids": ["<section_id>"]}},
    "boundaries": {"operation": "structure", "payload": {"section_ids": ["<section_id>"]}},
    "outline": {"operation": "structure", "payload": {}},
    "edges": {"operation": "concept_tree", "payload": {"node": "<node_id>"}},
    "gaps": {"operation": "logical_plan", "payload": {}},
    "scoped_history": {"operation": "concept_history", "payload": {"node": "<node_id>"}},
    "source_support": {"operation": "literature_uses", "payload": {"claim_id": "<claim_id>"}},
    "evidence": {"operation": "research", "payload": {}},
    "nodes": {"operation": "concept", "payload": {"node": "<node_id>"}},
}

#: Keys of a section row whose BODY is published once as its own part of the delivery
#: ("AUTHOR SECTION NOTES AND DECLARED REFERENCES"), so the structure projection carries
#: the section's identity and not a second copy of the same prose.
_SECTION_NOTE_KEYS = ("job", "notes", "refs")


def _section_identity(row: Mapping[str, Any]) -> dict[str, Any]:
    """A navigable section identity: every exact ID, number and source path, no body."""
    value = {key: row.get(key) for key in
             ("id", "title", "kind", "parent_id", "depth", "number", "order",
              "ancestor_ids", "child_ids", "node_ids", "beat_ids")
             if row.get(key) is not None}
    source = row.get("source")
    if isinstance(source, Mapping):
        # The exact file paths and the match state are facts; `plan_title`,
        # `source_titles` and `source_label` are three more spellings of `title`
        # above, and a section out of this altitude does not need its own title
        # three times.  The whole row stays one `structure` read away.
        value["source"] = {key: source.get(key) for key in
                           ("section_id", "source_files", "status") if source.get(key) is not None}
    return value


def _section_in_scope(row: Mapping[str, Any]) -> dict[str, Any]:
    """A selected section in full, with each member's body behind its own read route."""
    value = {key: value for key, value in row.items() if key not in _SECTION_NOTE_KEYS}
    for key in ("nodes", "beats"):
        members = value.get(key)
        if isinstance(members, list) and members:
            value[key] = [_prompt_node_identity(member) if isinstance(member, Mapping) else member
                          for member in members]
    return value


def _scoped_structure(canonical: dict[str, Any], altitude: str) -> dict[str, Any]:
    """Reduce the projection to the altitude asked for, naming the read for each cut."""
    rules = _STRUCTURE_ALTITUDE.get(altitude) or _STRUCTURE_ALTITUDE["manuscript"]
    reduced: dict[str, Any] = {}
    for key in rules["full"]:
        rows = canonical.get(key)
        if key == "sections" and isinstance(rows, list):
            canonical[key] = [_section_in_scope(row) if isinstance(row, Mapping) else row
                              for row in rows]
    for key in rules["identity"]:
        rows = canonical.get(key)
        if isinstance(rows, list) and rows:
            canonical[key] = [_section_identity(row) if isinstance(row, Mapping) else row
                              for row in rows]
            reduced[key] = {"rows": len(rows), "carried": "identity only", "read": _STRUCTURE_SCOPE_READS[key]}
    for key in rules["count"]:
        rows = canonical.get(key)
        if isinstance(rows, list) and rows:
            canonical[key] = {"total": len(rows), "read": _STRUCTURE_SCOPE_READS[key]}
            reduced[key] = {"rows": len(rows), "carried": "total only", "read": _STRUCTURE_SCOPE_READS[key]}
    canonical["altitude"] = altitude
    if reduced:
        canonical["scoped_out_of_this_altitude"] = reduced
    return canonical


def _prompt_structure_projection(structure: Mapping[str, Any], altitude: str = "manuscript") -> dict[str, Any]:
    canonical = {key: structure.get(key) for key in
                 ("eligible_for_authoring", "sections", "boundaries", "focus",
                  "selected_node_ids", "selected_nodes", "selected_nodes_total",
                  "selected_nodes_omitted", "selected_node_read_routes", "scoped_history",
                  "scoped_history_omitted", "edges", "direct_dependencies",
                  "source_support", "source_support_total", "source_support_omitted",
                  "evidence", "evidence_total", "evidence_omitted",
                  "gaps", "gaps_total", "gaps_omitted", "ancestors", "children", "outline")}
    focus = canonical.get("focus")
    if isinstance(focus, Mapping):
        focus = {key: value for key, value in focus.items() if key != "mathematical_record"}
        node = focus.get("node") if isinstance(focus.get("node"), Mapping) else {}
        structural = node.get("kind") in _STRUCTURAL_FOCUS_KINDS
        if isinstance(focus.get("containment"), Mapping):
            if structural:
                focus["node"] = _prompt_node_identity(node, purpose=True)
            else:
                # The resolved mathematical record is emitted once below the
                # structure block.  Keep the leaf's meaning here without
                # duplicating its authored mathematics inside node.projection.
                projection = dict(node.get("projection") or {})
                projection.pop("mathematics", None)
                focus["node"] = {**node, "projection": projection}
            focus["neighbors"] = [_prompt_node_identity(row) for row in focus.get("neighbors") or []
                                  if isinstance(row, Mapping)]
            # Top-level edges already carry each immediate relation once.
            focus.pop("edges", None)
            focus["containment"] = _prompt_containment_overview(
                focus["containment"], include_purpose=structural)
        canonical["focus"] = focus
    dependencies = canonical.get("direct_dependencies") or []
    if dependencies:
        canonical["direct_dependencies"] = {
            "total": len(dependencies),
            "details": "DIRECT PREREQUISITE STATEMENTS FOR THIS SCOPE below",
        }
    # The same rule, applied to the two remaining keys this prompt published TWICE.
    # `evidence` is emitted whole as "CURRENT EVIDENCE INTERPRETATIONS FOR THIS SCOPE"
    # below (:1285 in this tree, :1047 in the campaign base 87ece9da), and a section's
    # job/notes/refs as "AUTHOR SECTION NOTES AND DECLARED REFERENCES" (:1292);
    # `direct_dependencies` above has had the
    # pointer treatment since the reconciliation.  Measured on the published section
    # altitude: evidence was 5,277 characters inside the projection and 5,371 as its own
    # part.  One home per fact, and the pointer says which home.
    evidence = canonical.get("evidence") or []
    if evidence:
        canonical["evidence"] = {
            "total": len(evidence),
            "details": "CURRENT EVIDENCE INTERPRETATIONS FOR THIS SCOPE below",
        }
    # THE INFORMATION RULE, said ONCE for every section this projection reduced rather than
    # once per row.  A section carried as identity has lost its job, its notes, its refs, its
    # members' bodies, its literature support and its evidence; measured on the published
    # paragraph altitude, 4 source paths, 13 digests, 3 citekeys, 4 canonical nodes, 19
    # section ids and 2 read receipts left the delivery with the neighbouring sections'
    # bodies, and each one is inside one of these three reads with an id this delivery still
    # carries (evidence/WRITING_CONSOLIDATION_2026-10-03/wave1/context-economy/info_rule.json).
    # Repeating the three routes on all 11 rows cost 1,310 characters to say one thing 11
    # times, which is the defect this campaign exists to subtract.
    canonical["section_bodies"] = {
        "carried": "AUTHOR SECTION NOTES AND DECLARED REFERENCES below",
        "keys": list(_SECTION_NOTE_KEYS),
        # SIX reads, not three, and each one was added because a fact was measured
        # unreachable without it.  On the SECOND fixture project, which has no canonical
        # concept network at all, the first three left 20 literature digests, 2 citekeys and
        # 1 section id of the reduced sections unreachable: `literature_uses` needs a node id
        # that project does not have, and `structure {}` with no selector answers on an empty
        # scope.  `references`, `logical_plan` and `literature_scope` are the homes those
        # facts actually live in -- found by executing every deployed read with an empty
        # payload and asking which answer contains the fact, not by reasoning about it
        # (wave1/context-economy/info_rule.json and find_home.py).
        "bodies_available_via": [
            {"operation": "structure", "payload": {"section_ids": ["<section_id from this projection>"]}},
            {"operation": "literature_uses", "payload": {"claim_id": "<claim_id from this projection>"}},
            {"operation": "literature_scope", "payload": {}},
            {"operation": "research", "payload": {}},
            {"operation": "references_attached", "payload": {}},
            {"operation": "logical_plan", "payload": {}}]}
    # A graph-derived multi-object scope already carries every exact canonical
    # ID.  Keep its bounded identity preview, while each member's substance is
    # available through the declared read route instead of copying 40 bodies.
    if canonical.get("selected_node_ids"):
        canonical["selected_nodes"] = [_prompt_node_identity(row)
                                       for row in canonical.get("selected_nodes") or []
                                       if isinstance(row, Mapping)]
    return _scoped_structure(canonical, altitude)


#: THE ONE NAME FOR EACH PART OF A DELIVERY, and the declared read that reaches that
#: part's facts once the delta has withheld it.  The names are the friction lane's part
#: names (evidence/WRITING_FRICTION_2026-10-01/wave1/context-economy/measure_turns.py:45),
#: so a before/after figure means the same thing on both sides.  Every operation named
#: here is a deployed read of ``writing_tools.READS``.  A part whose key ends in a colon
#: and a file name is per-file; its read carries that file.  THE INFORMATION RULE of
#: guarantee B: nothing a delivery withholds may be unreachable, and the delivery itself
#: says how to reach it, so the route is data here and not prose in a report. ``None``
#: means no single exact owner read has been proved: that part remains in-band.
_DELIVERY_PART_READS = {
    "preamble": None,
    "framing": {"operation": "project", "payload": {}},
    "sustained_argument": {"operation": "project", "payload": {}},
    "author_comments": {"operation": "author_history", "payload": {"view": "corrections"}},
    # Multi-record parts stay in-band until this producer can name every concrete
    # existing owner read. A placeholder is not an executable recovery route.
    "applied_edits": None,
    "glossary": None,
    "bibliography_ids": {"operation": "references_attached", "payload": {}},
    "canonical_structure": None,
    "direct_prerequisites": None,
    "mathematical_record": None,
    "evidence_interpretations": {"operation": "research", "payload": {}},
    "section_notes": None,
    "local_source_refs": None,
    "writing_style": {"operation": "writing_style", "payload": {}},
    "numbered_source": {"operation": "source", "payload": {"files": ["<file>"]}},
    "boundary_prose": {"operation": "source", "payload": {"files": ["<file>"]}},
    "project_instructions": {"operation": "project_guidance", "payload": {"path": "<path>"}},
    "attached_source_notes": {"operation": "references_attached", "payload": {}},
}

# These compound projections need the saved exact scope, rather than a guessed
# structure/source selector. The existing CTX receipt owns that scope; it does
# not become another content store or a claim that provider compaction kept it.
_SCOPED_DELIVERY_PARTS = frozenset({'canonical_structure','direct_prerequisites',
    'mathematical_record','section_notes','local_source_refs'})


def delivery_read_contract():
    return {'type':'object','required':['view','context_id','part','expected_token'],
        'properties':{'view':{'const':'delivery'},
            'context_id':{'type':'string','pattern':'^CTX-[0-9a-f]{32}$'},
            'part':{'enum':sorted(_SCOPED_DELIVERY_PARTS)},
            'expected_token':{'type':'string','pattern':'^[0-9a-f]{32}$'}},
        'additionalProperties':False}


def read_delivery_part(project, payload, repo_root=None):
    """Recompute one current named projection from its retained exact scope.

    A changed token is reported with current content, never represented as the
    historical delivered bytes. Native execute records the actual successful
    owner read; this pure owner read creates no context/version or provider act.
    """
    from jsonschema import Draft202012Validator
    issue = next(Draft202012Validator(delivery_read_contract()).iter_errors(payload),None)
    if issue:
        raise ValueError('Delivery-part read: '+issue.message)
    path,source = _state_path(project,repo_root)
    if not path.is_file():
        raise ValueError('The exact saved context scope is unavailable; inspect current document/structure. No scope was guessed.')
    with _locked(path):
        state = _read(path,project,repo_root,context_ids={payload['context_id']})
    receipt = next((row for row in state['contexts'] if row['id']==payload['context_id']),None)
    if receipt is None or (receipt.get('storage') or {}).get('status')=='MISSING':
        raise ValueError('The exact saved context scope is unavailable or incomplete; inspect current document/structure. No scope was guessed.')
    scope = receipt.get('structure_scope')
    if not isinstance(scope,dict):
        raise ValueError('This legacy context did not retain an exact scoped recovery route; inspect current structure explicitly.')
    old_selection = ((receipt.get('structure') or {}).get('selected_source') or {}).get('selection_identity')
    if old_selection:
        from laplace.manuscript.manuscript_source import selection_identity
        if old_selection!=selection_identity(source,project):
            raise ValueError('The selected document changed since this scope was delivered; inspect current document/structure instead.')
    current = build_context(project,scope,repo_root,include_guidance=False,
                            include_orientation=True,record_context=False)
    part = next((row for row in current['parts'] if row['key']==payload['part']),None)
    if part is None:
        raise ValueError('This part is absent from the current exact scope; inspect current structure before continuing.')
    from urllib.parse import urlencode
    handle = {'operation':'structure','payload':dict(payload),
        'http':{'method':'GET','url':'/work/structure?'+urlencode({'project':project,**payload})}}
    return {'schema_version':'laplace.delivery-part/1','project':project,'view':'delivery',
        'recorded_context_id':payload['context_id'],'part':part['key'],'text':part['text'],
        'token':part['token'],'expected_token':payload['expected_token'],
        'matches_expected':part['token']==payload['expected_token'],
        'bytes':len(part['text'].encode()),'scope':scope,'read_handle':handle,
        'currentness':'CURRENT_MATCH' if part['token']==payload['expected_token'] else 'CHANGED_CURRENT_CONTENT',
        'historical_bytes':False,'context_recorded':False,
        'receipt_materializations':len(state['contexts'])}


def delivery_part_read(key: str, *, context_id=None, token=None, project=None) -> dict[str, Any] | None:
    """The declared read for one part key, with a per-file part's own file filled in."""
    name, _, detail = key.partition(":")
    if name in _SCOPED_DELIVERY_PARTS and context_id and token:
        from urllib.parse import urlencode
        payload = {'view':'delivery','context_id':context_id,'part':name,'expected_token':token}
        return {'operation':'structure','payload':payload,
            **({'http':{'method':'GET','url':'/work/structure?'+urlencode({'project':project,**payload})}}
               if project else {})}
    route = _DELIVERY_PART_READS.get(name)
    if route is None:
        return None
    if not detail:
        return {"operation": route["operation"], "payload": dict(route["payload"])}
    payload = dict(route["payload"])
    for field in ("file", "path", "id"):
        if payload.get(field) == "<" + field + ">":
            payload[field] = detail
    for field in ("files", "paths", "ids"):
        singular=field[:-1]
        if payload.get(field) == ["<" + singular + ">"]:
            payload[field] = [detail]
    return {"operation": route["operation"], "payload": payload}


def prompt_framing(document: Mapping[str, Any] | None, project_record=None) -> dict[str, str]:
    """Present an observed source capability; this grants no role or edit authority."""
    document = document or {}
    status = document.get("status")
    diagnostics = document.get("diagnostics") or []
    manifest = getattr(project_record, "manifest", {})
    manifest = manifest if isinstance(manifest, Mapping) else {}
    declared = manifest.get("document")
    declared = declared if isinstance(declared, Mapping) else {}
    source_optional = getattr(project_record, "kind", None) == "project"
    if status == "resolved" and document.get("root"):
        kind = "manuscript"
    elif (source_optional and status == "missing" and not document.get("root")
          and not any(declared.get(key) for key in ("root", "manuscript_dir", "edition"))
          and not getattr(project_record, "external_root", None)
          and diagnostics in (["no TeX document root found"], ["declared manuscript directory is absent"])):
        kind = "project"
    else:
        kind = "unresolved"
    if kind == "manuscript":
        return {"kind":kind,
            "preamble":"You are continuing one coherent manuscript argument. Preserve exact source and evidence identities while choosing the explanatory order that lets the reader follow the reason for each next move.",
            "framing_label":"Whole-manuscript framing:", "argument_label":"Sustained argument:",
            "empty_argument":"(No authored argument has been recorded yet.)",
            "suffix":"Work as the continuing writer of this connected argument. You may inspect relevant project evidence and neighbouring prose, and carry out user-authorized work within this project. Distinguish scientific gaps from writing decisions. Never manufacture citations or results.",
            "work_suffix":"Use laplace_project to advance this project's authorised research work: inspect concepts and sources, author scoped artifacts, organise tasks, record experiments, produce visuals and run declared checks. Verify actual outcomes before claiming completion. The manuscript itself remains source-addressed and reviewable. Never turn a local instruction into global law.",
            "review_subject":"manuscript"}
    unresolved = ("The manuscript source is unresolved. Do not assume a manuscript is available or that this is a source-free project. Source status: "
                  + str(status or "unknown") + "; diagnostics: " + json.dumps(diagnostics,ensure_ascii=False)) if kind == "unresolved" else ""
    return {"kind":kind,
        "preamble":unresolved or "You are working on this project's purpose and context. Preserve exact artifact and evidence identities while carrying out the author's requested project work.",
        "framing_label":"Project purpose:", "argument_label":"Project context:",
        "empty_argument":"(No authored project context has been recorded yet.)",
        "suffix":("The expected manuscript source is unresolved; inspect its selection diagnostics before source-dependent work. " if unresolved else "")
            + "Work within the current project. You may inspect relevant project evidence and artifacts and carry out user-authorized project work. Distinguish observed outcomes from assumptions. Never manufacture citations or results.",
        "work_suffix":"Use laplace_project for this project's authorised artifact and project work through its canonical tools. Verify actual outcomes before claiming completion. Source-dependent edits still require selected source and its existing guards. Never turn a local instruction into global law.",
        "review_subject":"project artifacts"}


def _prompt_parts(state: Mapping[str, Any], selected: list[Mapping[str, Any]], boundaries: list[Mapping[str, Any]], corrections: list[Mapping[str, Any]], glossary: list[Mapping[str, Any]], source_ids: list[str], structure: Mapping[str, Any] | None = None, writing_style_context: Mapping[str, Any] | None = None, genre: str = "", *, include_orientation: bool = True, local_refs=(), altitude: str = "manuscript", framing_scope=None) -> list[tuple[str, str]]:
    """Every part of the delivery, as (part key, text).

    The parts were already there, separated by blank lines and recognised by their
    opening words; this returns them NAMED, which is what lets one delta mechanism
    withhold a part and say which read reaches it.  ``_prompt`` below is the same
    join it always was.
    """
    framing = state["framing"]
    scope = framing_scope if framing_scope is not None else prompt_framing(None)
    parts: list[tuple[str, str]] = [("preamble", scope["preamble"])]
    if include_orientation:
        parts.extend((
            ("framing", scope["framing_label"] + "\n" + "\n".join(f"{k}: {framing[k]}" for k in ("purpose", "audience", "question") if framing[k])),
            ("sustained_argument", scope["argument_label"] + "\n" + (state["argument"] or scope["empty_argument"])),
        ))
    if corrections:
        notes = [row for row in corrections if not row.get("applied")]
        applied = [row for row in corrections if row.get("applied")]
        if notes:
            # ONE PART, ONE NAME, AND THE RULING IS SAID (WRITING-CONSOLIDATION-W1).  The
            # part is a (name, text) pair because the one delta mechanism keys every
            # delivery part by name (`_DELIVERY_PART_READS`); and a keep/cut/rework ruling
            # is the one author comment that is an INSTRUCTION about the passage's fate
            # rather than an observation about it, so it is rendered in the line a session
            # actually reads, at the altitude it was ruled at.  A field a session never
            # sees is a field the author wrote for nobody.
            parts.append(("author_comments", "Current author comments and instructions applicable to this scope (origin is explicit).\n" + "\n".join(
                f"[{row.get('id')}] ({row.get('kind')}/{row.get('scope')}; by {row.get('by') or 'unspecified'}"
                + (f"; RULING: {row['disposition']} this {row.get('altitude') or 'passage'}"
                   if row.get("disposition") else "")
                + f") {row.get('text')}"
                for row in notes)))
        if applied:
            parts.append(("applied_edits", "Prior applied author source edits are already embodied in the current source; preserve their local intent. "
                         + f"{len(applied)} edit(s): " + "; ".join(
                             f"[{row.get('id')}] {row.get('text')}" for row in applied[:24] if row.get("text"))
                         + ("; IDs: " + ", ".join(str(row.get("id")) for row in applied[:24]) if not any(row.get("text") for row in applied) else "")
                         + ("; inspect author_history by ID only when the exact historical hunk is needed." if applied else "")))
    if glossary:
        parts.append(("glossary", "Glossary identities available in this scope:\n" + ", ".join(f"{x['term']} ({x['id']})" for x in glossary)))
    if source_ids:
        parts.append(("bibliography_ids", "Bibliography/source identities in this scope: " + ", ".join(source_ids)))
    if structure and (structure.get("sections") or structure.get("focus") or
                      structure.get("selected_nodes") or structure.get('outline')):
        canonical = _prompt_structure_projection(structure, altitude)
        parts.append(("canonical_structure", "Canonical joined structure for this selected edition and scope:\n" +
                     json.dumps(canonical, ensure_ascii=False)))
        dependencies = structure.get("direct_dependencies") or []
        if dependencies:
            parts.append(("direct_prerequisites", "DIRECT PREREQUISITE STATEMENTS FOR THIS SCOPE (relations are not proof):\n" +
                         json.dumps(dependencies, ensure_ascii=False)))
        focus_record = ((structure.get("focus") or {}).get("mathematical_record")
                        if isinstance(structure.get("focus"), Mapping) else None)
        if isinstance(focus_record, Mapping):
            locations = [{key: location.get(key) for key in
                          ("status", "reference", "repository", "path", "label", "file", "sha256",
                           "line_start", "line_end", "truncated", "error")}
                         for location in focus_record.get("source_locations") or []
                         if isinstance(location, Mapping)]
            parts.append(("mathematical_record", "FOCUSED MATHEMATICAL RECORD (documented, qualification remains explicit):\n" +
                         json.dumps({key: focus_record.get(key) for key in
                                    ("node", "statement_tex", "statement_origin", "domain", "assumptions",
                                     "proof", "formal_targets", "verification", "qualification",
                                     "limitations", "revision")} | {"source_locations": locations},
                                    ensure_ascii=False)))
        if structure.get("evidence"):
            parts.append(("evidence_interpretations", "CURRENT EVIDENCE INTERPRETATIONS FOR THIS SCOPE (currentness is not scientific acceptance):\n" +
                         json.dumps(structure.get("evidence"), ensure_ascii=False)))
        section_notes = [{key: section.get(key) for key in ("id", "job", "notes", "refs")}
                         for section in structure.get("sections") or []
                         if section.get("job") or section.get("notes") or section.get("refs")]
        if section_notes:
            parts.append(("section_notes", "AUTHOR SECTION NOTES AND DECLARED REFERENCES:\n" + json.dumps(section_notes, ensure_ascii=False)))
    if local_refs:
        parts.append(("local_source_refs", "EXPLICIT LOCAL SOURCE REFERENCES FROM DIRECT PREREQUISITES:\n" + json.dumps(local_refs, ensure_ascii=False)))
    if writing_style_context:
        parts.append(("writing_style", "PROSE-ONLY WRITING STYLE (never scientific evidence or structure policy).\n"
                     + "Current manuscript genre: " + (genre or "unspecified")
                     + ". The current genre and manuscript contract control wherever a project-specific "
                       "historical note conflicts.\nVERSIONED PROFILE ["
                     + str(writing_style_context.get("selected_profile") or "") + "]:\n"
                     + str(writing_style_context.get("content") or "")
                     + ("\nPROJECT-LOCAL GUIDANCE (historical/contextual, not global law):\n"
                        + str(writing_style_context.get("guidance"))
                        if writing_style_context.get("guidance") else "")))
    for source in selected:
        parts.append((f"numbered_source:{source.get('file')}",
                     f"NUMBERED SOURCE ADDRESS GUIDE [{source.get('file')}]:\n"
                     "Prefixes to the left of | are 1-based line addresses, not manuscript text. "
                     "Use these addresses for the proposal span and copy source only from the right side.\n"
                     + str(source.get("numbered_text") or _numbered(source))))
    for source in boundaries:
        # Boundaries orient joins; selected spans above are never truncated.
        edge, side = _boundary_text(source, selected, altitude)
        whole = len(str(source.get("text") or ""))
        # THE INFORMATION RULE on a WINDOW.  The window is the altitude's, and what it cut is
        # the neighbour's own prose: measured on the second fixture project, one section label
        # and one path that the baseline delivery carried sat in the characters this window
        # drops, and nothing in the delivery said where they went.  The part says so itself.
        parts.append((f"boundary_prose:{source.get('file')}",
                      f"BOUNDARY PROSE [{source.get('file')}]:\n{edge}"
                      + (f"\n[the {side} edge only: {len(edge)} of this neighbour's {whole} "
                         f"characters, the window for {altitude} altitude; the whole neighbour is "
                         + json.dumps({"operation": "source",
                                       "payload": {"files": [str(source.get("file"))]}},
                                      ensure_ascii=False) + "]"
                         if len(edge) < whole else "")))
    return [(key, text) for key, text in parts if text]


def _prompt(state: Mapping[str, Any], selected: list[Mapping[str, Any]], boundaries: list[Mapping[str, Any]], corrections: list[Mapping[str, Any]], glossary: list[Mapping[str, Any]], source_ids: list[str], structure: Mapping[str, Any] | None = None, writing_style_context: Mapping[str, Any] | None = None, genre: str = "", *, include_orientation: bool = True, local_refs=(), altitude: str = "manuscript") -> str:
    return "\n\n".join(text for _key, text in _prompt_parts(
        state, selected, boundaries, corrections, glossary, source_ids, structure,
        writing_style_context, genre, include_orientation=include_orientation,
        local_refs=local_refs, altitude=altitude))


def build_context(project: str, selection: Any = None, repo_root: Path | str | None = None, *, include_guidance: bool = True, include_orientation: bool = True, record_context: bool = True) -> dict[str, Any]:
    """Build and receipt a context; this is the dependency producer for revision checks."""
    details = inspect(project, selection=selection, repo_root=repo_root, context_id="")
    path, source = _state_path(project, repo_root, _observed_source=details["document"])
    from laplace.pipeline import registry
    framing_scope = prompt_framing(source, registry.resolve(project, repo_root=_root(repo_root)))
    selected = details["sources"]
    boundaries = details["boundaries"]
    citations = sorted({key.strip() for item in selected for group in _CITE_RE.findall(str(item.get("text") or ""))
                        for key in group.split(",") if key.strip()})
    glossary = _glossary(project, _root(repo_root))
    references = _reference_context(project, citations, _root(repo_root))
    style_context, style_identity = _writing_style(project, _root(repo_root))
    from laplace.manuscript import project_protocol
    protocol = project_protocol.load(project, _root(repo_root))
    # The same effective selection served by the profile owner (authored blank
    # remains inheritance in the editor, not "unspecified" in native context).
    genre = str((style_context or {}).get('genre') or '')
    try:
        from laplace.manuscript import project_structure
        structure = project_structure.context(project, selection if isinstance(selection, Mapping) else {}, _root(repo_root))
    except ValueError:
        structure = None
    local_refs = _local_source_refs(project, structure, _root(repo_root))
    with _locked(path):
        state = _read(path, project, repo_root,contexts=record_context)
        corrections = _active_corrections(state, selected,selection if isinstance(selection,Mapping) else None)
        context_id = "CTX-" + uuid.uuid4().hex
        dependencies = _source_dependencies(selected, boundaries)
        receipt = {
            "id": context_id, "created": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
            "selection": [str(item.get("file")) for item in selected],
            "selection_spans": [{"file": str(item.get("file")), "line_start": item.get("line_start"),
                                 "line_end": item.get("line_end")} for item in selected],
            "source_revision": details["source_revision"], "argument_revision": state["argument_revision"],
            "consumed_correction_ids": [row["id"] for row in corrections if row.get("id")],
            "source_ids": citations, "source_dependencies": dependencies, "references": references, "glossary": glossary,
            "structure": structure,
            "structure_scope": dict(selection) if isinstance(selection, Mapping) else {
                "files": [str(item.get("file")) for item in selected]},
            "writing_style": style_identity,
            "project_protocol_revision": protocol['revision'],
        }
        receipt_revision=_context_receipt_revision(receipt)
        existing=next((row for row in reversed(state["contexts"])
                       if (row.get('storage') or {}).get('status')!='MISSING'
                       and (row.get("receipt_revision") or _context_receipt_revision(row))
                       == receipt_revision),None)
        reused=existing is not None
        if not record_context:
            context_id = None
            receipt['id'] = None
        elif existing is not None:
            context_id=str(existing["id"])
        else:
            receipt["receipt_revision"]=receipt_revision
            state["contexts"].append(receipt)
            _write(path, state)
        altitude = delivery_altitude(selection)
        parts = _prompt_parts(state, selected, boundaries, corrections, glossary, citations,
                              structure, style_context if include_guidance else None, genre,
                              include_orientation=include_orientation, local_refs=local_refs,
                              altitude=altitude, framing_scope=framing_scope)
        for guide in protocol['documents'] if include_guidance else []:
            if guide.get('role') != 'instructions' or not isinstance(guide.get('content'), str):
                continue
            parts.append(('project_instructions:' + guide['path'],
                          'PROJECT INSTRUCTIONS [' + guide['path'] + ']:\n' + guide['content']))
        if references:
            parts.append(("attached_source_notes",
                          "ATTACHED SOURCE NOTES (bibliographic association is not entailment evidence):\n"
                          + json.dumps(references, ensure_ascii=False)))
        prompt = "\n\n".join(text for _key, text in parts)
    return {
        "project": project, "context_id": context_id, "context_reused":reused,
        "prompt_framing": framing_scope,
        # The delivery, NAMED part by part, each with the token that makes it
        # re-deliverable and the declared read that reaches its facts once the one
        # delta mechanism has withheld it (authoring_surface.without_already_delivered).
        "altitude": altitude,
        "parts": [{"key": key, "text": text, "chars": len(text),
                   "token": _digest(text)[:32], "read": delivery_part_read(key,context_id=context_id,token=_digest(text)[:32],project=project)}
                  for key, text in parts],
        "revision": state["revision"],
        "source_revision": details["source_revision"], "selection": receipt["selection"],
        "prompt": prompt, "consumed": {"corrections": receipt["consumed_correction_ids"],
        "source_ids": citations, "references": references, "glossary": glossary,
        "structure": structure, "writing_style": style_identity,
        "project_protocol_revision": protocol['revision'],
        "argument": state["argument"]},
        "dependencies": receipt, "stale": details["stale"], "document": source,
        "science_context_digest": _digest(json.dumps({"structure": structure, "local_refs": local_refs}, sort_keys=True, default=str)),
        "diagnostics": details["diagnostics"],
    }


def bank_correction(project: str, payload: Mapping[str, Any], repo_root: Path | str | None = None) -> dict[str, Any]:
    """Record one explicitly scoped correction and invalidate affected receipts."""
    if isinstance(payload,Mapping) and 'request_id' in payload:
        from laplace.pipeline.correction_origin import save
        return save(project,payload,repo_root)
    return _bank_correction(project,payload,repo_root)


def prepare_correction(project, payload, repo_root=None):
    from laplace.pipeline.correction_origin import prepare
    return prepare(project,payload,repo_root)


def correction_request(project, request_id, repo_root=None, *, ledger, submission=None):
    """Exact same-request lookup; an optional ORIGINAL submission adds the owner's pure intent association."""
    from laplace.pipeline.correction_origin import request
    return request(project,request_id,repo_root,ledger=ledger,submission=submission)


def settle_correction(project,payload,repo_root=None):
    from laplace.pipeline.correction_origin import settle
    return settle(project,payload,repo_root)


def correction_origin(project, origin_ref, repo_root=None):
    from laplace.pipeline.correction_origin import inspect
    return inspect(project,origin_ref,repo_root)


def _bank_correction(project, payload, repo_root=None, *, _origin=None):
    """The existing correction writer, with optional owner-created custody."""
    if not isinstance(payload, Mapping):
        raise ValueError("correction payload must be an object")
    text = str(payload.get("text") or "").strip()
    kind, scope = str(payload.get("kind") or "").strip(), str(payload.get("scope") or "").strip()
    if not text:
        raise ValueError("correction text is required")
    if kind not in _CORRECTION_KINDS:
        raise ValueError(f"correction kind must be one of {sorted(_CORRECTION_KINDS)}")
    if scope not in _CORRECTION_SCOPES:
        raise ValueError(f"correction scope must be one of {sorted(_CORRECTION_SCOPES)}")
    if scope == "global":
        raise ValueError("global corrections require an explicit shared law mechanism; use project or passage scope")
    anchor = payload.get("anchor") if isinstance(payload.get("anchor"), Mapping) else {}
    pending_reply_to=str(payload.get("reply_to") or "").strip()
    if (scope == "passage" and not pending_reply_to
            and not payload.get("feedback_target") and not anchor.get("feedback_target")
            and not any(anchor.get(key) for key in ("section_id", "section", "file", "node_id"))):
        raise ValueError("passage correction requires an anchor section_id, section, file, or node_id")
    from laplace.work.feedback import validate_feedback
    target, effect = validate_feedback(project, payload, _root(repo_root))
    if target:
        anchor = {**anchor, "feedback_target": target, "feedback_effect": effect}
    if effect == "observation_only" and payload.get("supersedes"):
        raise ValueError("Observation feedback cannot retire an instruction; use its status or an explicit instruction.")
    path, source = _state_path(project, repo_root,_observed_source=_origin['source'] if _origin else None)
    with _locked(path):
        if _origin:
            from laplace.pipeline import correction_origin
            saved=correction_origin.recover(project,payload,_root(repo_root),_origin['intent'])
            if saved:return saved
        state = _read(path, project, repo_root)
        _assert_current(state, payload)
        supersedes = str(payload.get("supersedes") or "").strip()
        reply_to = str(payload.get("reply_to") or "").strip()
        if supersedes and reply_to:
            raise ValueError("correction may supersede an old instruction or reply to it, not both")
        reply_match=None
        if reply_to:
            reply_match=next((row for row in state["corrections"] if row.get("id")==reply_to),None)
            if reply_match is None:raise ValueError("correction reply target is unknown")
            scope=str(reply_match.get("scope") or scope)
            anchor={**dict(reply_match.get("anchor") or {}), **({"feedback_target":target,"feedback_effect":effect} if target else {})}
            if target is None and anchor.get("feedback_target"):
                target, effect = validate_feedback(project, {"anchor":anchor}, _root(repo_root))
                anchor.update(feedback_target=target, feedback_effect=effect)
        if supersedes:
            match = next((row for row in state["corrections"] if row.get("id") == supersedes), None)
            if match is None:
                raise ValueError(f"correction to supersede is unknown: {supersedes}")
            match["status"] = "superseded"
        by=str(payload.get("by") or "author")
        context_role=("observation-only" if effect == "observation_only" else
                      "agent-history" if by.startswith("eigen:") and scope=="project" else
                      "anchored-review" if by.startswith("eigen:") else "author-instruction")
        row = {"id": "AC-" + uuid.uuid4().hex, "project": project,
               "created": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(), "text": text,
               "kind": kind, "scope": scope, "anchor": dict(anchor), "by":by,
               "context_role":context_role,
               "status": "open", "base_revision": state["revision"]}
        if target:
            row.update(feedback_target=target, feedback_effect=effect)
        # The feedback ledger is the canonical cross-surface consumer.  The
        # authoring receipt remains a dependency projection, linked by this id.
        from laplace.manuscript import manuscript_bridge
        ledger_home = (_root(repo_root) / source["manuscript_dir"] if source.get("manuscript_dir") and not source.get("read_only") else path.parent)
        ledger = _root(repo_root)/_origin['ledger'] if _origin else ledger_home / "feedback" / "feedback.jsonl"
        node_id = str(anchor.get("node_id") or anchor.get("section_id") or anchor.get("file") or "authoring")
        feedback = manuscript_bridge.feedback_add(_root(repo_root), project, {
            "node_id": node_id, "comment": text, "kind": "author-correction",
            "anchor": {**anchor, "authoring_scope": scope, "correction_kind": kind,
                       "context_role":context_role, "correction_id": row["id"]}, "by": row["by"],
            "supersedes": match.get("feedback_id") if supersedes else None,
            "re": (reply_match or {}).get("feedback_id") or reply_to or None,
        }, ledger=ledger, **({'origin':correction_origin.custody(project,payload,row,state['revision']+1)} if _origin else {}))
        if feedback.get("error"):
            raise ValueError(f"feedback correction refused: {feedback['error']}")
        if _origin and feedback.get('origin_outcome'):
            found=feedback['origin_outcome']
            return found['receipt'] if found['effect']=='RECORDED' else found
        row["feedback_id"] = feedback["record"]["id"]
        if _origin:
            # The canonical feedback body is the only stored comment text.
            # Authoring retains its revision and projects the original AC alias.
            row=correction_origin.projection(feedback['record'])
        if supersedes:
            row["supersedes"] = supersedes
        if reply_to:
            row["reply_to"]=reply_to
        state["corrections"].append(row)
        state["revision"] += 1
        _write(path, state)
        if _origin:return correction_origin._receipt(feedback['record'])
    return {"project": project, "revision": state["revision"], "correction": row, "document": source}


def correction_status(project: str, payload: Mapping[str, Any],
                      repo_root: Path | str | None = None) -> dict[str, Any]:
    """Resolve, dismiss, or reopen one canonical correction and its feedback row."""
    if not isinstance(payload, Mapping):
        raise ValueError("correction status payload must be an object")
    ident = str(payload.get("id") or "").strip()
    status = str(payload.get("status") or "").strip()
    note = str(payload.get("note") or "").strip()
    if not ident:
        raise ValueError("correction id is required")
    if status not in {"open", "resolved", "dismissed"}:
        raise ValueError("correction status must be open, resolved, or dismissed")
    if len(note.encode("utf-8")) > 20_000:
        raise ValueError("correction status note is too large")
    path, source = _state_path(project, repo_root)
    root = _root(repo_root)
    with _locked(path):
        state = _read(path, project, repo_root)
        _assert_current(state, payload)
        correction = next((row for row in state["corrections"]
                           if row.get("id") == ident or row.get("feedback_id") == ident), None)
        if correction is None:
            raise ValueError("correction is unavailable")
        if correction.get("applied"):
            raise ValueError("applied edit history has no unresolved status to change")
        feedback_id = str(correction.get("feedback_id") or
                          (correction.get("id") if correction.get("_ledger_projection") else ""))
        ledgers = [path.parent / "feedback" / "feedback.jsonl"]
        directory = source.get("manuscript_dir")
        if isinstance(directory, str) and directory and not source.get("read_only"):
            candidate = Path(directory)
            manuscript = candidate if candidate.is_absolute() else root / candidate
            ledgers.append(manuscript.resolve() / "feedback" / "feedback.jsonl")
        ledgers = list(dict.fromkeys(ledger.resolve() for ledger in ledgers))
        feedback_records, feedback_changed = [], False
        if feedback_id:
            from laplace.manuscript import manuscript_bridge
            matched = [ledger for ledger in ledgers if any(
                row.get("id") == feedback_id
                for row in manuscript_bridge.feedback_list(root, project, ledger=ledger).get("records", []))]
            if not matched:
                raise ValueError("linked feedback correction is unavailable")
            for ledger in matched:
                changed = manuscript_bridge.feedback_resolve(
                    root, project, feedback_id, status, ledger=ledger, note=note,
                    by=str(payload.get("by") or "author"))
                if changed.get("error") or not changed.get("ok"):
                    raise ValueError(changed.get("error") or "feedback correction status was not saved")
                if changed.get("record"):
                    feedback_records.append(changed["record"])
                feedback_changed = feedback_changed or bool(changed.get("changed"))
        current_status = str(correction.get("status") or "open")
        changed = current_status != status or bool(note)
        if not feedback_id and changed:
            event = {"status": status, "at": _dt.datetime.now(tz=_dt.timezone.utc).isoformat(),
                     "by": str(payload.get("by") or "author")}
            if note:
                event["note"] = note
            correction["status_history"] = list(correction.get("status_history") or []) + [event]
            correction["status"] = status
            if note:
                correction["status_note"] = note
            else:
                correction.pop("status_note", None)
        elif feedback_records:
            receipt = feedback_records[-1]
            correction["status"] = receipt.get("status", status)
            correction["status_history"] = list(receipt.get("status_history") or [])
            if receipt.get("status_note"):
                correction["status_note"] = receipt["status_note"]
            else:
                correction.pop("status_note", None)
            changed = changed or feedback_changed
        if changed:
            state["revision"] += 1
            _write(path, state)
        fresh = _read(path, project, repo_root)
        projected = next(row for row in fresh["corrections"]
                         if row.get("id") == correction.get("id") or
                         (feedback_id and row.get("feedback_id") == feedback_id))
    return {"project": project, "revision": fresh["revision"],
            "correction": dict(projected), "status": projected.get("status"),
            "reused": not changed, "document": source}
