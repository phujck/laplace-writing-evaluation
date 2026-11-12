"""Source-byte effects and their required and optional follow-through.

Feature owners retain admission, lock order, required transactions and rollback.
This owner consumes exact per-file observations made under those locks; it never
renews a caller's basis or persists another ledger. Legacy response fields are
projections of this result while their callers migrate.
"""

from __future__ import annotations

from pathlib import Path

from laplace.core import identity as core_identity, receipts as core_receipts
from laplace.writing.records._fold import _proposal_digest, _proposal_effect_digest

SCHEMA = "laplace.source-effect/1"
STATES = ("UNCHANGED", "COMMITTED", "ROLLED_BACK", "PARTIAL", "UNPROVED")


def protocol() -> dict:
    """One source-effect contract for native help, HTTP and client fixtures."""
    return {
        "schema_version": SCHEMA,
        "location": "top-level source_effect; nested legacy failure strings are not this schema",
        "states": list(STATES),
        "required_statuses": ["COMPLETE", "NOT_NEEDED", "COMPENSATED", "FAILED", "UNPROVED"],
        "identity": "project and the originally admitted selection_identity; null only for genuine unregistered legacy source",
        "files": "Nonempty exact core.receipts.file_receipt observations: scope, path, before_sha256, after_sha256, observed_after_sha256. Null pin means absent file; observation_error distinguishes unproved physical fate.",
        "completion": "complete:true requires state COMMITTED or UNCHANGED and every required status COMPLETE or NOT_NEEDED. COMPENSATED, FAILED and UNPROVED require complete:false. Physical source fate remains independent; optional heading/history maintenance cannot revoke a known source commit.",
        "no_op": "Successful no-op requires matching before/intended/observed file pins and complete:true. UNCHANGED with complete:false means source unchanged but required work incomplete, not acknowledgement. Ordinary raw Save mints no version when unchanged; explicit archive/restore retains its distinct audit occurrence.",
        "refusal": "Pre-admission refusal and metadata-only effects omit this block. Empty file evidence cannot prove a no-op.",
        "follow_through": "required steps; heading_sync (existing plan_sync); maintenance_warnings",
        "impact": "status NONE/REOBSERVE/UNPROVED; reads are existing operation/payload handles; coverage explicitly excludes inferred logical membership. Metadata owned_changes remain independent.",
        "recovery": "Never automatically repeat COMMITTED-incomplete, PARTIAL or UNPROVED outcomes. ROLLED_BACK also requires explicit reinspection. Fresh reads may support a new independent edit but do not repair earlier required work.",
        "compatibility": "Raw source_committed/changed, native source_applied/source_effect_retained, plan_sync and owned_changes remain explicit compatibility projections while reached callers migrate.",
    }


class SourceEffectFailure(ValueError):
    """A domain operation failed after it attempted a physical source change."""

    def __init__(self, error, effect):
        super().__init__(str(error))
        self.details = {
            "source_effect": effect,
            "recovery": "Inspect the exact source effect and required follow-through before another action; do not automatically repeat it.",
        }


def error_details(error) -> dict:
    """Retain this owner's receipt through HTTP/native error adapters."""
    for _ in range(8):
        if error is None:
            break
        details = getattr(error, "details", None)
        effect = details.get("source_effect") if isinstance(details, dict) else None
        if isinstance(effect, dict) and effect.get("schema_version") == SCHEMA:
            return {key: details[key] for key in ("source_effect", "recovery") if key in details}
        error = error.__cause__ or error.__context__
    return {}


def raw_compatibility(effect) -> dict:
    """Legacy raw-source acknowledgements; retire after all raw clients migrate."""
    return {
        "source_committed": effect["state"] in {"COMMITTED", "UNCHANGED"},
        "changed": any(
            "observation_error" in row or row["before_sha256"] != row["observed_after_sha256"]
            for row in effect["files"]
        ),
    }


def application_compatibility(effect) -> dict:
    """Legacy application flags, derived from the same observed source fate."""
    return {
        "complete": effect["complete"],
        "source_applied": effect["state"] in {"COMMITTED", "UNCHANGED"},
        "source_effect_retained": any(
            "observation_error" not in row and row["before_sha256"] != row["observed_after_sha256"]
            for row in effect["files"]
        ),
    }


def replace(path: Path, data: bytes) -> None:
    """Atomic byte replacement; the feature owner already holds its source lease."""
    from laplace.manuscript.manuscript_source import stage_source

    staged = stage_source(path, data)
    try:
        publish(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def publish(staged: Path, path: Path) -> None:
    """Publish bytes already staged by an owner with a bank-before-swap contract."""
    staged.replace(path)


def observed_file(root, path, before, intended_after) -> dict:
    """Capture physical fate under the caller's existing source lease."""
    from laplace.core.receipts import file_receipt
    from laplace.core.identity import bytes_digest as digest
    try:
        return file_receipt(root, path, before, intended_after)
    except OSError as exc:
        return {
            "scope": "repository",
            "path": Path(path).resolve().relative_to(Path(root).resolve()).as_posix(),
            "before_sha256": digest(before),
            "after_sha256": digest(intended_after),
            "observed_after_sha256": None,
            "observation_error": str(exc),
        }


def receipt(project, selection_identity, files, *, complete=True, required=()) -> dict:
    """Physical byte disposition is independent of required domain completion."""
    files = [dict(row) for row in files]
    required_rows = [dict(row) for row in required]
    allowed = {"COMPLETE", "NOT_NEEDED", "COMPENSATED", "FAILED", "UNPROVED"}
    if any(row.get("status") not in allowed for row in required_rows):
        raise ValueError("unknown required source follow-through status")
    if any(
        "observation_error" in row and not isinstance(row["observation_error"], str)
        for row in files
    ):
        raise ValueError("source observation_error must be a string")
    if not files:
        raise ValueError(
            "source effect requires an observed source file; no-source metadata and pre-effect refusals omit this receipt"
        )
    if any("observation_error" in row for row in files):
        state = "UNPROVED"
    elif all(
        row["before_sha256"] == row["after_sha256"] == row["observed_after_sha256"] for row in files
    ):
        state = "UNCHANGED"
    elif all(row["after_sha256"] == row["observed_after_sha256"] for row in files):
        state = "COMMITTED"
    elif all(row["before_sha256"] == row["observed_after_sha256"] for row in files):
        state = "ROLLED_BACK"
    else:
        state = "PARTIAL"
    return {
        "schema_version": SCHEMA,
        "project": project,
        "selection_identity": selection_identity,
        "state": state,
        "complete": bool(
            complete
            and state in {"UNCHANGED", "COMMITTED"}
            and all(row["status"] in {"COMPLETE", "NOT_NEEDED"} for row in required_rows)
        ),
        "files": files,
        "follow_through": {
            "required": required_rows,
            "heading_sync": {"status": "DEFERRED"},
            "maintenance_warnings": [],
        },
        "impact": {
            "status": "NONE",
            "reads": [],
            "coverage": "Source files and document only; logical binding membership is not inferred.",
        },
    }


def from_changes(
    root, project, selection_identity, changes, *, complete=True, owner="source"
) -> dict:
    """Reduce transient successful writes, retaining the attempted postimage on rollback."""
    combined = {}
    for path, before, after in changes:
        before = before.encode("utf-8") if isinstance(before, str) else before
        after = after.encode("utf-8") if isinstance(after, str) else after
        path = Path(path).resolve()
        if path in combined:
            original, first, _previous = combined[path]
            combined[path] = (original, first, after)
        else:
            combined[path] = (before, after, after)
    files = [
        observed_file(root, path, before, first if not complete and after == before else after)
        for path, (before, first, after) in combined.items()
    ]
    effect = receipt(
        project,
        selection_identity,
        files,
        complete=complete,
        required=[{"owner": owner, "status": "COMPLETE" if complete else "FAILED"}],
    )
    return effect


def mirror_headings(project: str, changes: list, root: Path, *, expected_selection=None) -> dict:
    """Mirror proven heading postimages after the outer source lease releases."""
    from laplace.manuscript import manuscript_source
    from laplace.manuscript.manuscript_structure import _heading_rows, mirror_heading_titles

    if manuscript_source.source_mutation_active():
        raise manuscript_source.SourceLeaseError("heading projection requires outer source release")
    combined = {}
    for path, before, after in changes:
        path = Path(path).resolve()
        before = before.decode("utf-8") if isinstance(before, bytes) else before
        after = after.decode("utf-8") if isinstance(after, bytes) else after
        if path in combined:
            original, previous = combined[path]
            if previous != before:
                return {"status": "UNPROVED", "reason": "source changes are not contiguous"}
            combined[path] = (original, after)
        else:
            combined[path] = (before, after)
    combined = {
        p: pair
        for p, pair in combined.items()
        if p.suffix == ".tex" and _heading_rows(pair[0] or "") != _heading_rows(pair[1] or "")
    }
    if not combined:
        return {"status": "NOT_NEEDED", "updated": []}
    root = Path(root).resolve()
    with manuscript_source.selection_mutation(project, root):
        selected = manuscript_source.resolve(project, repo_root=root)
        if (
            expected_selection is not None
            and manuscript_source.selection_identity(selected, project) != expected_selection
        ):
            return {"status": "UNPROVED", "reason": "selected edition changed after source commit"}
        if not selected.get("root"):
            return {"status": "UNPROVED", "reason": "selected source unavailable"}

        def namespace():
            tree = manuscript_source.traversal(selected["root"], repo_root=root)
            return {(root / row["file"]).resolve() for row in tree.get("sources", [])}

        paths = namespace() | set(combined)
        with manuscript_source.source_mutation(paths):
            current = manuscript_source.resolve(project, repo_root=root)
            if current.get("root") != selected.get("root") or namespace() | set(combined) != paths:
                return {"status": "UNPROVED", "reason": "selected source namespace changed"}
            for path, (_before, after) in combined.items():
                if not path.is_file() or path.read_bytes().decode("utf-8") != after:
                    return {
                        "status": "SOURCE_CHANGED",
                        "reason": "saved heading postimage changed",
                        "file": path.relative_to(root).as_posix(),
                    }
            updated = []
            history_cache = {}
            for path, (before, after) in combined.items():
                updated.extend(
                    mirror_heading_titles(
                        project, path, before, after, root, history_cache=history_cache
                    )
                )
            return {"status": "CURRENT", "updated": updated}


def finish(result, project, root, effect, *, changes=(), heading_sync=None) -> dict:
    """Publish optional maintenance without changing known physical effect truth."""
    warnings = list(result.get("maintenance_warnings") or [])
    if heading_sync is None and not changes:
        heading_sync = {"status": "NOT_NEEDED", "updated": []}
    if heading_sync is None:
        try:
            heading_sync = (
                mirror_headings(
                    project,
                    list(changes),
                    Path(root),
                    expected_selection=effect.get("selection_identity"),
                )
                if project
                else {"status": "NOT_NEEDED", "updated": []}
            )
        except Exception as exc:
            heading_sync = {"status": "UNPROVED", "reason": str(exc),
                            **({"recovery": exc.details} if isinstance(getattr(exc, "details", None), dict) else {})}
    if heading_sync.get("status") not in {"CURRENT", "NOT_NEEDED", "DEFERRED"}:
        warnings.append(
            {
                "operation": "heading_sync",
                "reason": heading_sync.get("reason", "Heading projection is unproved."),
            }
        )
    effect["follow_through"]["heading_sync"] = heading_sync
    effect["follow_through"]["maintenance_warnings"] = warnings
    changed = [
        row
        for row in effect["files"]
        if "observation_error" in row or row["before_sha256"] != row["observed_after_sha256"]
    ]
    if changed or not effect["complete"]:
        reads = [{"operation": "document", "payload": {}}] if project else []
        files = [
            row["path"]
            for row in changed
            if row.get("observed_after_sha256") and Path(row["path"]).suffix.lower() == ".tex"
        ]
        if project and files:
            from laplace.manuscript import manuscript_source

            try:
                selected = manuscript_source.resolve(project, repo_root=root)
                tree = (
                    manuscript_source.traversal(selected["root"], repo_root=root)
                    if selected.get("root")
                    else {}
                )
                selected_files = set(tree.get("files") or [])
                omitted = [file for file in files if file not in selected_files]
                files = [file for file in files if file in selected_files]
                if omitted:
                    effect["impact"]["source_read_omissions"] = [
                        {
                            "file": file,
                            "reason": "Outside the current selected source traversal; no canonical source read authority is issued.",
                        }
                        for file in omitted
                    ]
            except (OSError, ValueError, KeyError) as exc:
                effect["impact"]["source_read_omissions"] = [
                    {"file": file, "reason": "Selected source membership unavailable: " + str(exc)}
                    for file in files
                ]
                files = []
            if files:
                reads.append({"operation": "source", "payload": {"files": files[:16]}})
        if project and heading_sync.get("status") != "NOT_NEEDED":
            reads.append({"operation": "structure", "payload": {"view": "summary"}})
        effect["impact"].update(
            status="UNPROVED" if effect["state"] == "UNPROVED" else "REOBSERVE", reads=reads
        )
        if len(files) > 16:
            effect["impact"]["source_reads_omitted"] = len(files) - 16
    if project and changes and changed:
        try:
            from laplace.manuscript.bindings import effect_impact
            scoped = effect_impact(project, root, changes,
                                   expected_selection=effect.get('selection_identity'))
            existing_reads = effect['impact'].get('reads', [])
            if scoped.get('status') == 'NONE':
                scoped['status'] = effect['impact'].get('status', 'NONE')
            effect['impact'].update(scoped)
            handles = existing_reads + scoped.get('reads', [])
            seen, unique = set(), []
            import json
            for handle in handles:
                key = json.dumps(handle, sort_keys=True)
                if key not in seen:
                    seen.add(key)
                    unique.append(handle)
            effect['impact']['reads'] = unique
        except Exception as exc:
            effect['impact']['binding_status'] = 'UNAVAILABLE'
            effect['impact']['binding_error'] = str(exc)
    result["source_effect"] = effect
    result["plan_sync"] = heading_sync
    return result


# ---------------------------------------------------------------------------------------- the record of applications
# An application is the owner receipt of one source effect: these projections join a turn's applications to the exact
# proposal they consumed and to the current bytes of the files they pinned (moved from authoring_surface, family 1).

def applications(turn: dict) -> list[dict]:
    rows = [dict(row) for row in turn.get("applications", []) if isinstance(row, dict)]
    latest = turn.get("application")
    if isinstance(latest, dict) and all(row.get("id") != latest.get("id") for row in rows):
        rows.append(dict(latest))
    return rows


def application_source_state(root:Path,application:dict,*,file_hashes:dict|None=None) -> str:
    """Current byte observation is distinct from historical execution success."""
    pins=(application.get('owned_changes') or {}).get('files') or []
    if not pins:return 'UNKNOWN'
    cache=file_hashes if file_hashes is not None else {}
    observed=[]
    for pin in pins:
        path=(root/str(pin.get('path') or '')).resolve()
        if not path.is_relative_to(root.resolve()):return 'UNKNOWN'
        if path not in cache:cache[path]=core_identity.file_digest(path)
        if not cache[path]:return 'UNKNOWN'
        observed.append((cache[path],pin))
    if all(digest==pin.get('after_sha256') for digest,pin in observed):return 'POSTIMAGE'
    if all(digest==pin.get('before_sha256') for digest,pin in observed):return 'PREIMAGE'
    return 'DIVERGED'


def applied_edits(turn: dict, application: dict) -> list[dict]:
    """Join an application to its existing exact proposal for editor undo."""
    if not application.get('complete'):
        return []
    from laplace.manuscript.manuscript_proposals import EditIdentity
    if isinstance(application.get('edits'),list):
        return [edit if isinstance(edit,EditIdentity) else dict(edit) for edit in application['edits']]
    versions = turn.get('proposal_versions') or {}
    proposal = versions.get(application.get('proposal_sha256'))
    if proposal is None:
        candidates = list(versions.values()) + [turn.get('pending_proposal'), (turn.get('reply') or {}).get('proposal')]
        proposal = next((value for value in candidates if isinstance(value, dict)
                         and (application.get('edit_sha256') == _proposal_effect_digest(value)
                              or application.get('proposal_sha256') == _proposal_digest(value))), None)
    return [edit if isinstance(edit,EditIdentity) else dict(edit) for edit in (proposal or {}).get('edits', [])]


def finish_source_changes(root: Path, project: str, result: dict, changes: list) -> None:
    """Optional projection cannot revoke an acknowledged source application."""
    if not changes and not isinstance(result.get('source_effect'), dict):
        return
    from laplace.manuscript import review_surface
    effect = result.get('source_effect')
    try:
        result['plan_sync'] = review_surface.mirror_source_changes(project, changes, root,
            expected_selection=effect.get('selection_identity') if isinstance(effect, dict) else None)
    except Exception as exc:
        result['plan_sync'] = {'status':'UNPROVED', 'reason':str(exc)}
    if isinstance(effect, dict):
        finish(result, project, root, effect, changes=changes, heading_sync=result['plan_sync'])
