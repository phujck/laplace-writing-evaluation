"""MUTATION ATTRIBUTION (S1 B3): which reads a write affected, and proof that a write's files really changed.

Pure functions over the journal fold and the files named in a tool action:

  _READ_VIEWS / _read_views / _views_cover_reason   which read views of an operation a write can make stale.
  _mutation_file_snapshot                           the exact canonical owner files (and their bytes'
                                                    digests) an action may touch, captured before and after.
  _owned_changes_exact                              a write's owned changes, proved only by a canonical owner
                                                    file whose digest moved; an object-only change without
                                                    such a file proves nothing (so no read is refreshed).
  _read_relevant_to_action / _affected_turn_reads   the current turn's reads that a proven change touches.
  _proposal_consulted_reads / _label_only_source_edit / _historical_activity_read
                                                    the narrow exceptions those rules state.

Consumers: writing.turn_reads (read baselines and context rebase) and the native tool door. Nothing here
banks; the journal is read through records.fold_records.
"""
from __future__ import annotations

import hashlib
import json
import re
from laplace.core import identity as core_identity, receipts as core_receipts
from laplace.projects import artifacts
from laplace.writing import records as writing_records
from pathlib import Path
from typing import Any, Mapping


_READ_VIEWS = {
    "document": {"document", "presentation"}, "writing_style": {"writing_style"},
    "project_guidance": {"project_guidance", "project"},
    "source": {"manuscript"}, "pipeline": {"pipeline"}, "structure": {"structure"},
    "logical_plan": {"structure", "concepts", "references", "research", "manuscript"},
    "project": {"project", "argument", "framing", "pipeline"},
    "concept": {"concepts", "references", "research", "manuscript"},
    "concept_tree": {"concepts"},
    "concept_history": {"concepts", "references", "research", "manuscript"},
    "references": {"references"}, "reference": {"references"}, "reference_text": {"references"},
    "references_attached": {"references"},
    "reference_source": {"references"},
    "literature_scope": {"concepts", "references", "structure", "research", "manuscript"},
    "literature_uses": {"references", "concepts", "manuscript", "structure"},
    "research": {"research"}, "visuals": {"visuals", "presentation"},
    "proof_targets": {"concepts", "proofs", "research"},
    "proofs": {"proofs", "research"}, "read_artifact": {"artifact", "research"},
    "author_history":{"corrections","manuscript"},
}


# These reads remain journaled for audit and can be refreshed explicitly, but
# describe UI/help/progress state rather than evidence a manuscript hunk rests on.
_TRANSIENT_APPLY_READS = frozenset({"help", "conversation_history", "run_status", "build_status", "writing_stage", "project_metadata"})


_STALE_REASON_VIEWS={
    "argument-or-framing-changed":{"argument","framing"},
    "writing-style-profile-or-guidance-changed":{"writing_style"},
    "project-working-guide-changed":{"project_guidance"},
    "concept-glossary-changed":{"concepts"},
    "reference-association-changed":{"references"},
    "structure-plan-conceptric-or-evidence-changed":{"structure","concepts","research","proofs"},
}


def _historical_activity_read(operation: str, payload: dict | None = None) -> bool:
    return operation == "author_history" and (payload or {}).get("view") in {"activity", "telemetry", "record", "structural-undo"}


def _proposal_consulted_reads(turn: Mapping[str, Any], edits: list[dict]) -> list[dict]:
    """Exact consumed evidence reads, excluding discovery and audit navigation.

    Callers supply the sealed candidate snapshot, not later conversation reads.
    Mutable scientific projections remain dependencies even for human review.
    """
    navigation={"help","conversation_history","run_status","build_status",
                "literature_discover","project_metadata","authoring/proposals","authoring/proposal-preview"}
    rows=[]
    for read in (turn.get("tool_reads") or {}).values():
        operation=str(read.get("operation") or "");payload=read.get("payload") or {}
        if operation in navigation or _historical_activity_read(operation,payload):continue
        if operation=="repository" and payload.get("action") not in {"read","view"}:continue
        rows.append(read)
    return rows


_LABEL_COMMAND_RE=re.compile(r"\\label\s*\{([^{}]+)\}")


def _label_only_source_edit(edit: Mapping[str,Any]) -> bool:
    """True only for moving unchanged label commands through unchanged TeX."""
    before,after=edit.get("before"),edit.get("after")
    if not isinstance(before,str) or not isinstance(after,str) or before==after:return False
    left=_LABEL_COMMAND_RE.findall(before);right=_LABEL_COMMAND_RE.findall(after)
    if not left or sorted(left)!=sorted(right):return False
    without=lambda value:re.sub(r"\s+","",_LABEL_COMMAND_RE.sub("",value))
    return without(before)==without(after)


def _read_views(operation: str, payload: dict | None = None) -> set[str]:
    """Return mutable dependency views for one exact read payload.

    ``author_history`` normally reads current corrections and therefore remains
    an authoring dependency. Its activity, telemetry, record and structural inverse views are audit reads:
    later timeline appends do not change any instruction or evidence consulted
    by the writer.
    """
    if _historical_activity_read(operation,payload):
        return set()
    return set(_READ_VIEWS.get(operation, set()))


def _views_cover_reason(views:set[str],reason:str) -> bool:
    if reason.startswith("source-revision-changed"):return "manuscript" in views
    if reason.startswith(("correction-unconsumed:","correction-retired:")):return "corrections" in views
    return bool(views & _STALE_REASON_VIEWS.get(reason,set()))




def _mutation_file_snapshot(root: Path, project: str, operation: str = "",
                            action_payload: Mapping[str, Any] | None = None,
                            extra_paths=()) -> dict[str, str | None]:
    """Bounded exact identities for files canonical project actions can mutate.

    This is transaction evidence, not a new store. It is held only across one
    in-process tool call and compared with the owner's returned mutation receipt.
    """
    from laplace.research import corpus_ingest
    from laplace.manuscript import manuscript_source
    from laplace.pipeline import registry
    root=Path(root).resolve();paths=set();action_payload=action_payload or {}
    record=registry.resolve(project,repo_root=root)
    source=manuscript_source.resolve(project,repo_root=root)
    for raw in (source.get("root"),):
        if not isinstance(raw,str) or not raw:continue
        path=Path(raw) if Path(raw).is_absolute() else root/raw
        if path.is_file():paths.add(path.resolve())
    if source.get("root"):
        try:
            traversal=manuscript_source.traversal(source["root"],repo_root=root)
            for row in traversal.get("sources") or []:
                raw=row.get("file")
                if isinstance(raw,str):paths.add((root/raw).resolve())
        except (OSError,ValueError):pass
    bases=[]
    if record is not None:
        for raw in (getattr(record,"project_dir",None),getattr(record,"manuscript_dir",None),
                    source.get("manuscript_dir")):
            if not isinstance(raw,str) or not raw:continue
            path=Path(raw) if Path(raw).is_absolute() else root/raw
            if path.resolve().is_relative_to(root):bases.append(path.resolve())
    canonical={"references.json","research_records.json","research_producers.json",
               "projection_plan.json","manuscript_spec.json","figure_manifest.json",
               "document_style.json"}
    paths.add((root/"corpus_friction"/"work_orders.jsonl").resolve())
    if operation=="project_metadata_change":
        paths.add((root/"registry_projects.json").resolve())
    if operation=="experiment_run":
        # The run owner chooses the manuscript (including its legacy selection
        # rules). Capture only its mutable index, even before the first launch;
        # unique job records are minted under the owner's launch lock.
        from laplace.research import research_context, research_runs
        _item,manuscript=research_context.project(project,root)
        if manuscript is not None:
            paths.add((research_runs._declared_run_home(_item,root,manuscript)/"index.json").resolve())
    for base in dict.fromkeys(bases):
        if not base.is_dir():continue
        for name in canonical:
            paths.add((base/name).resolve())
        for pattern in ("*.bib","formal/*.json","formal/*.toml","formal/lean-toolchain"):
            paths.update(path.resolve() for path in base.glob(pattern) if path.is_file())
    # Capture exact mutable artifacts only for the action that can own them.
    # The prior implementation rebuilt the complete research/evidence/visual
    # projection before and after every tiny write, rereading hundreds of
    # scientific artifacts even when a task row or one concept changed.
    if operation == "store_artifact" and isinstance(action_payload.get("path"),str):
        try:paths.add(artifacts.resolve_path(root,project,action_payload["path"],
                                              action_payload.get("scope","project")).resolve())
        except ValueError:pass
    if operation == "structure_change" and isinstance(action_payload.get("section_id"),str):
        # H5 (M5 C7-C9 repair, 2026-10-14): a reader-plan write (section contract, paragraph
        # create/edit/remove/reorder and the same-route restructures) mutates the project's
        # contracts file and the ONE narrative file of the selected section. Capture exactly
        # those two canonical owner files (resolved by the owner's own path rule, never by a
        # scan of narrative/), so the receipt's before identity has its captured preimage and
        # attribution is exact. An unsafe or unknown section id adds nothing here; the owner
        # refuses it in the write itself.
        try:
            from laplace.manuscript import reader_plan
            for path in reader_plan._paths(project,root,action_payload["section_id"]):
                paths.add(Path(path).resolve())
        except (OSError,ValueError,TypeError):pass
    if operation == "visual_render" and action_payload.get("id"):
        try:
            from laplace.pipeline import visual_production
            manuscript=Path(source.get("manuscript_dir") or "")
            manuscript=manuscript if manuscript.is_absolute() else root/manuscript
            spec=next((row for row in visual_production.load(manuscript).get("specs") or []
                       if row.get("id")==action_payload.get("id")),None)
            for raw in ((spec or {}).get("render") or {}).get("outputs") or []:
                if isinstance(raw,str):paths.add((manuscript/raw).resolve())
        except (OSError,ValueError,TypeError):pass
    science_sensitive={"literature_bind","literature_import","reference_attach",
        "reference_update","reference_refresh","reference_fetch","reference_text",
        "research_record","research_reconcile","proof_check","visual_create",
        "visual_render","visual_place"}
    if operation in science_sensitive:
        manuscript_dir=Path(source.get("manuscript_dir") or "")
        manuscript_dir=(manuscript_dir if manuscript_dir.is_absolute()
                        else root/manuscript_dir).resolve()
        project_base=(record.path(record.project_dir,root).resolve()
                      if record is not None and record.project_dir else manuscript_dir)
        try:
            research=json.loads((manuscript_dir/"research_records.json").read_text())
        except (OSError,ValueError):research={}
        for row in research.get("records") or []:
            if not isinstance(row,dict):continue
            scope=row.get("scope","manuscript");base=project_base if scope=="project" else manuscript_dir
            raw_paths=[]
            for key in ("config","source","result"):
                if isinstance(row.get(key),str):raw_paths.append(row[key])
            raw_paths.extend(path for path in row.get("data") or [] if isinstance(path,str))
            raw_paths.extend(artifact.get("path") for artifact in row.get("artifacts") or []
                             if isinstance(artifact,dict) and isinstance(artifact.get("path"),str))
            for raw in raw_paths:
                candidate=(base/raw).resolve()
                if candidate.is_relative_to(base):paths.add(candidate)
        try:
            producers=json.loads((manuscript_dir/"research_producers.json").read_text())
        except (OSError,ValueError):producers={}
        for row in producers.get("producers") or []:
            if not isinstance(row,dict):continue
            base=project_base if row.get("scope","manuscript")=="project" else manuscript_dir
            for raw in [row.get("executable"),*(row.get("dependencies") or [])]:
                if not isinstance(raw,str):continue
                candidate=(base/raw).resolve()
                if candidate.is_relative_to(base):paths.add(candidate)
    try:
        from laplace.manuscript import project_protocol
        protocol=project_protocol.load(project,root)
        project_base=(record.path(record.project_dir or record.manuscript_dir,root).resolve()
                      if record is not None else None)
        if project_base is not None:
            paths.update((project_base/row["path"]).resolve()
                         for row in protocol.get("documents") or [] if isinstance(row.get("path"),str))
    except (OSError,ValueError):pass
    for raw in extra_paths:
        path=Path(str(raw));path=path if path.is_absolute() else root/path
        if path.resolve().is_relative_to(root):paths.add(path.resolve())
    try:paths.add(corpus_ingest._rewire_path(root,project).resolve())
    except (OSError,ValueError):pass
    result={}
    for path in sorted(paths):
        if path.is_relative_to(root):result[path.relative_to(root).as_posix()]=core_identity.file_digest(path)
    return result


def _owned_changes_exact(root: Path, before: dict, owned_changes) -> tuple[bool, str]:
    """Verify an owner's intended before/after files against capture and disk."""
    if not isinstance(owned_changes,dict) or owned_changes.get("schema_version")!="laplace.owner-mutation/1":
        return False,"mutation owner returned no exact receipt"
    captured=before.get("mutation_files") if isinstance(before,dict) else None
    if not isinstance(captured,dict):return False,"pre-write canonical file snapshot is unavailable"
    rows=owned_changes.get("files")
    if not isinstance(rows,list):return False,"mutation receipt has no file identities"
    if not rows and owned_changes.get("objects") and not owned_changes.get("rewire_records"):
        return False,"mutation receipt names object changes without their canonical owner file"
    root=Path(root).resolve();receipt_paths=set()
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get("path"),str):
            return False,"mutation receipt contains a malformed file identity"
        raw=Path(row["path"])
        if raw.is_absolute() or ".." in raw.parts:return False,"mutation receipt path escapes the project checkout"
        path=(root/raw).resolve()
        if not path.is_relative_to(root):return False,"mutation receipt path escapes the project checkout"
        captured_before=captured.get(raw.as_posix())
        # A canonical owner may mint a unique output path only after entering
        # its mutation lock (for example a supervised run ID). Its explicit
        # null before identity proves that path was absent at the lock boundary;
        # requiring a speculative pre-enumeration would mislabel every safe
        # creation as a race. Existing files still require exact pre-capture.
        if raw.as_posix() not in captured and row.get("before_sha256") is not None:
            return False,"canonical owner preimage was not captured: "+raw.as_posix()
        if raw.as_posix() in captured and captured_before!=row.get("before_sha256"):
            return False,"canonical owner changed before its mutation lock was acquired: "+raw.as_posix()
        observed=core_identity.file_digest(path)
        if row.get("after_sha256")!=row.get("observed_after_sha256") or observed!=row.get("observed_after_sha256"):
            return False,"canonical owner changed during or after its mutation: "+raw.as_posix()
        receipt_paths.add(raw.as_posix())
    project=before.get("mutation_project")
    rewire_records=owned_changes.get("rewire_records") or []
    if rewire_records:
        prior=before.get("mutation_rewire_records")
        if not isinstance(prior,list) or not isinstance(project,str):
            return False,"pre-write canonical rewire snapshot is unavailable"
        try:
            from laplace.research import corpus_ingest
            now=corpus_ingest.rewire_list(root,project)
        except (OSError,ValueError):return False,"canonical rewire ledger is unavailable"
        if now[:len(prior)]!=prior or now[len(prior):]!=rewire_records:
            return False,"canonical rewire ledger contains changes outside the returned records"
        receipt_paths.add(corpus_ingest._rewire_path(root,project).resolve().relative_to(root).as_posix())
    if isinstance(project,str) and project:
        observed_snapshot=_mutation_file_snapshot(
            root,project,str(before.get("mutation_operation") or ""),
            before.get("action_payload") if isinstance(before.get("action_payload"),dict) else {},
            extra_paths=receipt_paths)
        # The read model can discover an existing evidence file only after its
        # canonical record is added.  That expands the snapshot inventory but
        # is not itself a file mutation.  Compare the pre-write inventory and
        # every explicitly receipted new output; fixed canonical owner files
        # are already present in ``captured`` even when absent on disk.
        compared=set(captured)|receipt_paths
        changed={path for path in compared
                 if captured.get(path)!=observed_snapshot.get(path)}
        unowned=sorted(changed-receipt_paths)
        if unowned:return False,"unowned canonical files changed during the mutation: "+", ".join(unowned[:8])
    return True,"exact owner receipts match captured before and observed after identities"


def _read_relevant_to_action(operation:str,action_payload:dict,read:dict) -> bool:
    """Select only read scopes the named action can directly change.

    Omitted reads retain their old baseline.  They are never blessed: if they
    later matter to an apply, normal stale-read validation still replays and
    rejects them.  This predicate only avoids eagerly replaying unrelated
    node/path/key scopes after every exact owner write.
    """
    read_operation=str(read.get("operation") or "");payload=read.get("payload") or {}
    node_ids={str(action_payload.get(key)) for key in
              ("node","id","claim_id","concept_id","target") if action_payload.get(key)}
    path_ids={str(action_payload.get(key)) for key in ("path","file") if action_payload.get(key)}
    reference_ids={str(action_payload.get(key)) for key in ("key","reference_key") if action_payload.get(key)}
    node_actions={"concept_change","logical_plan_change","structure_change","literature_bind",
                  "reference_update","reference_refresh","proof_check"}
    if read_operation=="concept":
        if operation in {"experiment_run","research_record","reference_fetch",
                         "literature_import","task","task_status","work_review"}:return False
        return (str(payload.get("node") or "") in node_ids if node_ids
                else operation not in node_actions | {"store_artifact"})
    if read_operation=="logical_plan":
        return ((str(payload.get("node") or "") in node_ids or payload.get("view")=="catalog")
                if node_ids else operation not in node_actions | {"store_artifact"})
    if read_operation=="concept_tree":
        return (bool(node_ids & {str(payload.get("node") or ""),str(payload.get("from") or "")})
                if node_ids else operation not in node_actions | {"store_artifact"})
    if read_operation=="literature_scope":
        if operation in {"experiment_run","research_record","reference_fetch",
                         "literature_import","task","task_status","work_review"}:return False
        return (str(payload.get("node") or "") in node_ids if node_ids
                else operation not in node_actions | {"store_artifact"})
    if read_operation in {"reference","reference_source","reference_text"}:
        return (str(payload.get("key") or "") in reference_ids if reference_ids else
                operation not in {"literature_bind","reference_update","reference_refresh","store_artifact"})
    if read_operation=="read_artifact":
        artifact_id=str(action_payload.get("artifact_id") or "")
        return (str(payload.get("path") or read.get("artifact_path") or "") in path_ids
                or bool(artifact_id and str(payload.get("id") or "")==artifact_id)
                if path_ids or artifact_id else operation=="store_artifact")
    # Source reads remain relevant to operations that may materialize a
    # bibliography/source edit; global summaries are few and intentionally
    # conservative. Exact owner receipts still gate every refresh.
    return True


def _affected_turn_reads(root: Path, project: str, turn_id: str, operation: str, *,
                         actual_views=None, include_potential=False,
                         action_payload:dict|None=None) -> tuple[dict, list[tuple[str, dict]]]:
    from laplace.writing import reads as read_contract
    from laplace.research import corpus_ingest
    records = writing_records.fold_records(root)
    turn = records["turns"].get(turn_id)
    if not turn or turn.get("project") != project:
        raise ValueError("The current writing turn does not belong to this project.")
    affected = (set(actual_views) if actual_views is not None else
                set(read_contract.ACTION_VIEWS.get(operation, ())))
    if include_potential:
        affected.update(read_contract.ACTION_POTENTIAL_VIEWS.get(operation, ()))
    excluded = set(read_contract.ACTION_EXCLUDED_READS.get(operation, ()))
    reads = [(key, read) for key, read in (turn.get("tool_reads") or {}).items()
             if str(read.get("operation") or "") not in excluded
             and _read_views(str(read.get("operation") or ""), read.get("payload") or {}) & affected
             and _read_relevant_to_action(operation,action_payload or {},read)]
    return turn, reads


