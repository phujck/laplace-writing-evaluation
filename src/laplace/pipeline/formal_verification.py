"""Project-scoped Lean verification receipts.

This adapter binds a Lean declaration to an existing result revision.  A process
exit code is only one observation: a checked proof also needs a pinned toolchain
and library manifest, an axioms audit, and a current binding receipt.
"""
from __future__ import annotations

from laplace.core.identity import revision_matches

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

from laplace.pipeline import registry

_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_'.]*\Z")
_BAD = re.compile(r"\b(?:sorry|admit|sorryAx)\b")
_AXIOM = re.compile(r"^\s*axiom\s+([A-Za-z_][A-Za-z0-9_'.]*)", re.M)
_IMPORT = re.compile(r"^\s*import\s+([^\n]+)", re.M)
_VERSION = re.compile(r"(?:version\s+|:v?|\bv)(\d+\.\d+\.\d+)\b", re.I)


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _root(repo_root: Path | str | None) -> Path:
    return Path(repo_root).resolve() if repo_root is not None else registry._repo_root().resolve()


def _project(project: str, repo_root: Path | str | None) -> tuple[Path, Any]:
    root = _root(repo_root)
    proj = registry.resolve(project, repo_root=root)
    if proj is None:
        raise ValueError(f"unknown project {project!r}")
    base = proj.path(proj.manuscript_dir, root)
    if base is None or not base.is_dir():
        raise ValueError("project has no local manuscript directory")
    return root, proj


def _safe(base: Path, value: str, *, exists: bool = True) -> Path:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts:
        raise ValueError("project-relative path required")
    resolved = (base / path).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError("path escapes project") from exc
    if exists and not resolved.is_file():
        raise ValueError(f"file is missing: {value}")
    return resolved


def _load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable JSON {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _layout(project: str, repo_root: Path | str | None) -> tuple[Path, Any, Path, dict]:
    root, proj = _project(project, repo_root)
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    location = source.get("storage_dir") if source.get("read_only") else source.get("manuscript_dir")
    base = Path(location) if isinstance(location, str) and Path(location).is_absolute() else root / str(location or "")
    assert base is not None
    manifest = _load(base / "formal" / "manifest.json")
    return root, proj, base, manifest


def _pin(base: Path, manifest: dict) -> dict:
    toolchain = _safe(base, str(manifest.get("lean_toolchain") or ""))
    libraries = _safe(base, str(manifest.get("lake_manifest") or ""))
    declaration = toolchain.read_text(encoding="utf-8", errors="replace").strip()
    if not declaration:
        raise ValueError("lean-toolchain is empty")
    match = _VERSION.search(declaration)
    if match is None:
        raise ValueError("lean-toolchain does not declare a parseable semantic version")
    project_root=_safe(base,str(manifest.get("project_root") or "."),exists=False)
    lakefiles={path.relative_to(base).as_posix():_sha(path) for path in
               (project_root/"lakefile.toml",project_root/"lakefile.lean") if path.is_file()}
    return {"toolchain": _sha(toolchain), "libraries": _sha(libraries),
            "lakefiles":lakefiles,
            "axiom_policy": "sha256:" + hashlib.sha256(json.dumps({
                "approved_axioms": sorted(manifest.get("approved_axioms") or []),
                "project_root": manifest.get("project_root", ".")}, sort_keys=True).encode()).hexdigest(),
            "lean_version": match.group(1),
            "toolchain_path": toolchain.relative_to(base).as_posix(),
            "libraries_path": libraries.relative_to(base).as_posix()}

def _tool_version(command: str, base: Path) -> dict:
    run = subprocess.run([command, "env", "lean", "--version"], cwd=base,
                         capture_output=True, text=True, timeout=15)
    text = (run.stdout or run.stderr).strip()
    match = _VERSION.search(text)
    if run.returncode or match is None:
        raise ValueError("could not read the active Lean version")
    return {"version": match.group(1), "output": text}


def _local_dependencies(source: Path, project_root: Path, base: Path) -> dict[str, str]:
    """Hash recursively imported local Lean sources; installed modules stay in the pin."""
    project_root, base = project_root.resolve(), base.resolve()
    observed: dict[str, str] = {}
    visited: set[Path] = set()

    def resolve(module: str, parent: Path) -> Path | None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_'.]*(?:\.[A-Za-z_][A-Za-z0-9_']*)*", module):
            return None
        rel = Path(*module.split(".")).with_suffix(".lean")
        candidates = (project_root / rel, base / rel, parent / rel.name)
        for candidate in candidates:
            path = candidate.resolve()
            try:
                path.relative_to(project_root)
            except ValueError:
                continue
            if path.is_file():
                return path
        return None

    def visit(path: Path) -> None:
        path = path.resolve()
        if path in visited:
            return
        visited.add(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        for group in _IMPORT.findall(text):
            for module in group.split():
                dependency = resolve(module, path.parent)
                if dependency is None or dependency == source.resolve():
                    continue
                key = dependency.relative_to(project_root).as_posix()
                observed[key] = _sha(dependency)
                visit(dependency)

    visit(source)
    return dict(sorted(observed.items()))


def _result(base: Path, manifest: dict, result_id: str, revision: str,
            project_root: Path | None = None) -> dict:
    """Resolve a proof binding from canonical research, with legacy compatibility.

    New formal manifests do not need a second result list: an omitted ``results``
    field names the manuscript's canonical ``research_records.json``.  Existing
    manifests that explicitly name a legacy ``{"results": [...]}`` file remain
    valid and retain their content-handle staleness semantics.
    """
    declared = manifest.get("results")
    target = _safe(base, str(declared or "research_records.json"))
    results = _load(target)
    canonical = isinstance(results.get("records"), list)
    rows = results.get("records") if canonical else results.get("results")
    if not isinstance(rows, list):
        raise ValueError("formal result source has neither canonical records nor a legacy results list")
    row = next((item for item in rows if isinstance(item, dict)
                and item.get("id") == result_id
                and (not canonical or item.get("kind") == "result")), None)
    if row is None or not isinstance(row.get("revision"), str):
        raise ValueError("result_id is not an existing revisioned result")
    if row["revision"] != revision:
        raise ValueError("result_revision is stale or does not bind result_id")
    if canonical:
        from laplace.research import research_records
        currentness = research_records._currentness(
            base, [row], (project_root or base).resolve())
        if currentness.get("status") != "CURRENT":
            state = str(currentness.get('status') or 'unknown').lower()
            raise ValueError(f"result_id dependencies are {state}; inspect research and use research_reconcile only for untracked coverage")
    return {"id": result_id, "revision": revision, "handle": "sha256:" + hashlib.sha256(
        json.dumps(row, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def concept_target(project: str, ident: str, root: Path | str | None = None, *,
                   network_snapshot=None, relations_snapshot=None) -> dict:
    """Read canonical content/source pins without re-entering formal.state.

    Mathematical source resolution is pure here: no verification projection is
    requested, so state → target → mathematical record cannot recurse.
    """
    from laplace.research import concepts as cs, mathematical_records as mr
    root = _root(root)
    network = network_snapshot if network_snapshot is not None else cs._network(project, root) or {}
    node = (network.get('nodes') or {}).get(ident)
    if not node or (node.get('kind') not in mr.KINDS and not (node.get('projection') or {}).get('mathematics')):
        raise ValueError('concept_id must identify an existing mathematical concept')
    record = mr.read(project, ident, node, root, include_verification=False)
    relations = relations_snapshot
    if relations is None:relations, _ = cs._relations(project, root, network)
    immediate = [r for r in relations if r['source'] == ident or r['target'] == ident]
    revision = cs._content_revision(project, ident, node, immediate, root, record)
    raw = node.get('source') or node.get('sources') or node.get('ref') or []
    authored = ((node.get('projection') or {}).get('mathematics') or {}).get('sources') or []
    refs = (raw if isinstance(raw, list) else [raw]) + authored
    refs = list({json.dumps(ref, sort_keys=True, default=str):ref for ref in refs if ref}.values())
    locations = []
    for ref in refs:
        source = mr.resolve_source(project, ref, root)
        locations.append({k: source.get(k) for k in ('reference', 'status', 'file', 'repository', 'path', 'sha256', 'line_start', 'line_end', 'error')})
    source_revision = 'sha256:' + hashlib.sha256(json.dumps(locations, sort_keys=True).encode()).hexdigest()
    statement_origin=record.get('statement_origin')
    readable_sources=bool(locations) and all(source.get('status') == 'READ' for source in locations)
    authored_statement=statement_origin=='AUTHORED'
    binding_ready=bool(record.get('statement_tex')) and (authored_statement or readable_sources)
    target = {'kind':'concept', 'id':ident, 'revision':revision, 'source_revision':source_revision,
              'label':cs._label(node, ident), 'statement_tex':record.get('statement_tex'),
              'domain':record.get('domain'), 'assumptions':record.get('assumptions'),
              'source_locations':locations, 'qualification':record.get('qualification'),
              'source_candidates':record.get('source_ambiguity') or [],
              'statement_origin':statement_origin,
              'origin_posture':'AUTHOR_ORIGINATED' if authored_statement else 'SOURCE_DOCUMENTED' if statement_origin=='SOURCE' else 'MISSING',
              'documentation_status':(record.get('qualification') or {}).get('status'),
              'binding_ready':binding_ready,
              'binding_reason':('Exact authored statement can be checked without pretending it is externally established.'
                                if binding_ready and authored_statement else
                                'Exact statement and every declared source location are readable.'
                                if binding_ready else
                                'A precise statement is required.' if not record.get('statement_tex') else
                                'A source-projected statement requires at least one readable declared source.'),
              'informal_alignment':'UNASSESSED'}
    target['handle'] = 'sha256:' + hashlib.sha256(json.dumps(target, sort_keys=True, default=str).encode()).hexdigest()
    # Reader-only substance follows the binding handle so adding a readable
    # projection cannot invalidate historical formal receipts.
    target['title']=cs._short_title(node)
    target['concept_kind']=node.get('kind')
    target['parent']=node.get('parent')
    target['proof']=record.get('proof')
    target['limitations']=record.get('limitations') or []
    target['assumptions_authored']='assumptions' in (record.get('authored') or {})
    return target


def targets(project: str, root: Path | str | None = None, node: str = '', offset: int = 0, limit: int = 40) -> dict:
    from laplace.research import concepts as cs, mathematical_records as mr
    root = _root(root)
    network=cs._network(project, root) or {};nodes=network.get('nodes') or {}
    relations,_rows=cs._relations(project,root,network)
    ids = [node] if node else sorted(ident for ident, data in nodes.items()
        if data.get('kind') in mr.KINDS or (data.get('projection') or {}).get('mathematics'))
    offset = max(0, int(offset)); limit = max(1, min(100, int(limit)))
    page = ids[offset:offset+limit]
    return {'project':project, 'targets':[concept_target(
                project, ident, root, network_snapshot=network,
                relations_snapshot=relations) for ident in page],
            'pagination':{'offset':offset,'limit':limit,'total':len(ids),'next_offset':offset+len(page) if len(ids)>offset+len(page) else None},
            'note':'Select the intended claim. A checked declaration never establishes informal alignment.'}


def _concept(project: str, ident: str, revision: str, source_revision: str, root: Path) -> dict:
    target = concept_target(project, ident, root)
    if not revision_matches(revision,target['revision']):
        raise ValueError('concept_revision is stale; read proof_targets for this concept')
    if not revision_matches(source_revision,target['source_revision']):
        raise ValueError('source_revision is stale; read proof_targets for this concept')
    if not target.get('binding_ready'):
        raise ValueError('concept needs a precise statement and, for a source-projected statement, readable declared sources before binding')
    return {key:target[key] for key in ('kind','id','revision','source_revision','handle','label','statement_tex','domain','assumptions','source_locations')}


def _receipt_path(base: Path) -> Path:
    return base / "formal" / "check_receipts.json"


def _receipts(base: Path) -> list[dict]:
    path = _receipt_path(base)
    if not path.is_file():
        return []
    value = _load(path)
    rows = value.get("receipts")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _write_receipt(base: Path, receipt: dict, root:Path|None=None) -> dict:
    from filelock import FileLock
    from laplace.core.receipts import bundle, file_receipt
    path = _receipt_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(path)+'.lock',timeout=15):
        before=path.read_bytes() if path.is_file() else None
        rows=_receipts(base)
        receipt.setdefault('id', 'PROOF-' + hashlib.sha256((json.dumps(receipt, sort_keys=True) + str(time.time_ns())).encode()).hexdigest()[:24])
        rows.append(receipt)
        intended=(json.dumps({"receipts":rows[-100:]},ensure_ascii=False,indent=1)+"\n").encode('utf-8')
        temporary=path.with_name(path.name+'.'+str(os.getpid())+'.'+str(time.time_ns())+'.pending')
        temporary.write_bytes(intended);temporary.replace(path)
        owner_root=Path(root).resolve() if root is not None else base.resolve()
        return bundle(files=[file_receipt(owner_root,path,before,intended)],objects=[{
            'owner':'formal-check','id':receipt['id'],'before_revision':None,
            'after_revision':'sha256:'+hashlib.sha256(json.dumps(receipt,sort_keys=True,default=str).encode()).hexdigest()}],
            views=['proofs','research','structure'])


def _diagnostics(text:str,limit:int=12_000)->dict|None:
    text=str(text or '').strip()
    if not text:return None
    return {'text':text[:limit],'total_chars':len(text),'truncated':len(text)>limit}


def _declaration(text: str, declaration: str) -> bool:
    return bool(re.search(r"^\s*(?:theorem|lemma|def)\s+" + re.escape(declaration) + r"\b", text, re.M))


def _installed_toolchains(root: Path | None) -> list[dict]:
    """Passive inventory. A directory name is a candidate, not a verified runtime."""
    if root is None:
        return []
    return [{"version": path.parent.parent.name.removeprefix("v"), "command": str(path)}
            for path in sorted((root / ".laplace-tools" / "lean").glob("*/bin/lake"))
            if path.is_file() and os.access(path, os.X_OK)]


def _tool_state(root: Path | None = None, lean_version: str | None = None) -> dict:
    """Locate a candidate without executing it or altering PATH/config."""
    configured = os.environ.get("LAPLACE_LEAN_LAKE", "").strip()
    installed = _installed_toolchains(root)
    matches = [item for item in installed if item["version"] == lean_version]
    local = matches[0]["command"] if matches else (installed[0]["command"] if not lean_version and len(installed) == 1 else "")
    for candidate, source in ((configured, "env:LAPLACE_LEAN_LAKE"), (local, "project-local"),
                              (shutil.which("lake") or "", "PATH")):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return {"available": True, "command": candidate, "source": source, "reason": None}
    return {"available": False, "command": None, "source": None,
            "reason": "Lean/Lake is not installed for this project"}


def setup(project: str, root: Path | str | None = None) -> dict:
    """On-demand setup contract, derived from the selected project source."""
    from laplace.manuscript import manuscript_source
    root = _root(root)
    document = manuscript_source.resolve(project, repo_root=root)
    location = document.get("storage_dir") if document.get("read_only") else document.get("manuscript_dir")
    base = Path(str(location or ""))
    if not base.is_absolute():
        base = root / base
    return {
        "base_directory": str(base.resolve()),
        "artifact_scope": "project" if document.get("read_only") else "manuscript",
        "manifest_path": "formal/manifest.json",
        "manifest_template": {"lean_toolchain": "formal/lean-toolchain",
            "lake_manifest": "formal/lake-manifest.json", "project_root": "formal", "approved_axioms": []},
        "installed_toolchain_candidates": _installed_toolchains(root),
        "requirements": [
            "All manifest paths and proof_check.file are relative to base_directory; project_root is the Lake working directory.",
            "Choose the Lean version required by the proof and libraries. Write formal/lean-toolchain with leanprover/lean4:v<VERSION> and a real lakefile.toml or lakefile.lean; pin dependencies with Lake's generated lake-manifest.json.",
            "Create these files through store_artifact (before=null for a new file, exact prior text for replacement) or authorized native project work. Do not fabricate a library lockfile or install dependencies merely to open this view.",
            "approved_axioms lists intentionally accepted Lean axioms. An empty list permits none; never widen it to hide a failed proof.",
            "Read proof_targets for the intended concept, author its actual declaration, then proof_check with its current concept_revision and source_revision. No research result is required for a theorem.",
            "proof_check verifies the running Lean version, elaborates the source and audits transitive axioms. A checked declaration still needs review of its alignment with the scientific claim."],
        "next_read": {"operation": "help", "payload": {"operation": "store_artifact"}}}


def check(project: str, *, file: str, declaration: str, result_id: str = "", result_revision: str = "",
          concept_id: str = "", concept_revision: str = "", source_revision: str = "",
          repo_root: Path | str | None = None, timeout: int = 60) -> dict:
    """Run a pinned, project-local Lean check and persist a bound receipt."""
    if not _ID.fullmatch(declaration):
        raise ValueError("declaration is malformed")
    try:
        root, proj, base, manifest = _layout(project, repo_root)
    except ValueError as exc:
        from laplace.manuscript import manuscript_source
        source = manuscript_source.resolve(project, repo_root=_root(repo_root))
        if source.get("read_only"):
            return {"project": project, "proof_status": "UNAVAILABLE", "reason": "foreign project is read-only; no writable formal manifest"}
        raise
    from laplace.manuscript import manuscript_source
    document = manuscript_source.resolve(project, repo_root=root)
    if document.get("read_only") and not document.get("storage_dir"):
        return {"project": project, "proof_status": "UNAVAILABLE", "reason": "foreign project is read-only"}
    source = _safe(base, file)
    try:
        pin = _pin(base, manifest)
    except ValueError as exc:
        return {"project": project, "proof_status": "UNAVAILABLE", "reason": str(exc),
                "informal_alignment": "UNASSESSED"}
    research_root = proj.path(proj.project_dir, root) if getattr(proj, "project_dir", "") else base
    if bool(concept_id) == bool(result_id):
        raise ValueError('Supply exactly one concept_id or result_id binding; do not substitute another target')
    binding_kind = 'concept' if concept_id else 'result'
    bound = (_concept(project, concept_id, concept_revision, source_revision, root) if concept_id else
             _result(base, manifest, result_id, result_revision, research_root or base))
    initial_digest = _sha(source)
    text = source.read_text(encoding="utf-8", errors="replace")
    def persist(status: str, reason: str | None = None, **extra: Any) -> dict:
        receipt = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "file": file,
                   "file_digest": initial_digest, "declaration": declaration, binding_kind: bound, "pin": pin,
                   "proof_status": status, "informal_alignment": "UNASSESSED", **extra}
        if reason:
            receipt["reason"] = reason
        receipt['owned_changes']=_write_receipt(base,receipt,root)
        return receipt
    if not _declaration(text, declaration):
        raise ValueError("declaration is not defined in the selected Lean file")
    if _BAD.search(text):
        return {"project": project, **persist("REJECTED", "sorry/admit/sorryAx is forbidden")}
    axioms = _AXIOM.findall(text)
    approved = set(manifest.get("approved_axioms") or [])
    if any(item not in approved for item in axioms):
        return {"project": project, **persist("REJECTED", "unapproved axioms in source", axioms=axioms)}
    tool = _tool_state(root, pin["lean_version"])
    if not tool["available"]:
        return {"project": project, **persist("UNAVAILABLE", tool["reason"])}
    project_root = _safe(base, str(manifest.get("project_root") or "."), exists=False)
    try:
        active_version = _tool_version(str(tool["command"]), project_root)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return {"project": project, **persist("UNAVAILABLE", str(exc))}
    if active_version["version"] != pin["lean_version"]:
        return {"project": project, **persist(
            "UNAVAILABLE", f"active Lean {active_version['version']} does not match pinned {pin['lean_version']}",
            tool_version=active_version["output"])}
    dependencies = _local_dependencies(source, project_root, base)
    command = [str(tool["command"]), "env", "lean", source.relative_to(project_root).as_posix()]
    try:
        run = subprocess.run(command, cwd=project_root, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"project": project, **persist("FAILED", "Lean check timed out")}
    output = (run.stdout or "") + (run.stderr or "")
    # Lean's declaration audit is the authority for transitive imports.  Keep
    # the temporary file beside the source so imports and Lake's project scope
    # resolve exactly as they do for the checked declaration.
    temp = source.with_name(f".{source.stem}.axioms-{os.getpid()}-{time.time_ns()}.lean")
    try:
        temp.write_text(text + f"\n#print axioms {declaration}\n", encoding="utf-8")
        audit = subprocess.run([str(tool["command"]), "env", "lean", temp.relative_to(project_root).as_posix()], cwd=project_root,
                               capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {'project':project, **persist('FAILED', 'Lean axiom audit failed: ' + str(exc))}
    finally:
        temp.unlink(missing_ok=True)
    axioms_output = (audit.stdout or "") + (audit.stderr or "")
    # `#print axioms` reports a closed list after `depends on axioms:`.  Parse
    # that list rather than guessing identifiers from ordinary diagnostics.
    # The appended audit is last. Earlier #print commands in authored sources
    # must not substitute another declaration's approved axiom list.
    reports = list(re.finditer(r"(?P<none>does not depend on any axioms)|depends on axioms:\s*\[(?P<axioms>[^]]*)\]", axioms_output, re.S))
    report = reports[-1] if reports else None
    observed = re.findall(r"[A-Za-z_][A-Za-z0-9_.']*", report.group('axioms') or '') if report else []
    if report is None:
        return {"project": project, **persist("FAILED", "Lean did not emit #print axioms output",
            axioms_audit={"declaration":declaration,"observed":[],"forbidden":[],"exit_code":audit.returncode},
            axiom_diagnostics=_diagnostics(axioms_output))}
    forbidden = [name for name in observed if name not in approved]
    receipt = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "file": file,
               "file_digest": initial_digest, "declaration": declaration, binding_kind: bound, "pin": pin,
               "tool": "lake env lean", "tool_version": active_version["output"],
               "tool_version_number": active_version["version"], "dependencies": dependencies,
               "exit_code": run.returncode,
               "output_digest": "sha256:" + hashlib.sha256(output.encode()).hexdigest(),
               "informal_alignment": "UNASSESSED"}
    if run.returncode!=0 or output.strip():receipt['compiler_diagnostics']=_diagnostics(output)
    if audit.returncode!=0:receipt['axiom_diagnostics']=_diagnostics(axioms_output)
    # A clean compiler exit establishes only elaboration.  The separate source
    # audit above rejects local axioms/sorry; imported axioms remain explicit.
    receipt["axioms_audit"] = {"declaration": declaration, "observed": observed, "forbidden": forbidden}
    receipt["proof_status"] = "CHECKED" if run.returncode == 0 and audit.returncode == 0 and not forbidden else ("REJECTED" if forbidden else "FAILED")
    receipt['axioms_audit']['exit_code'] = audit.returncode
    try:
        final_bound = (_concept(project, concept_id, concept_revision, source_revision, root) if concept_id else
                       _result(base, manifest, result_id, result_revision, research_root or base))
        unchanged = (final_bound == bound and _sha(source) == initial_digest and _pin(base, _load(base / 'formal' / 'manifest.json')) == pin
                     and _local_dependencies(source, project_root, base) == dependencies)
    except (ValueError, OSError):
        unchanged = False
    if not unchanged:
        receipt.update(proof_status='FAILED', reason='Bound claim, proof source or pinned inputs changed during verification')
    receipt['owned_changes']=_write_receipt(base,receipt,root)
    return receipt


def state(project: str, repo_root: Path | str | None = None) -> dict:
    """Passive receipt currentness; viewing a claim never launches Lake."""
    root = _root(repo_root)
    tool = _tool_state(root)
    try:
        _root_value, proj, base, manifest = _layout(project, root)
        pin = _pin(base, manifest)
    except ValueError as exc:
        status = "UNAVAILABLE" if "lean-toolchain" in str(exc) else "UNCONFIGURED"
        try:
            setup_context = setup(project, root)
        except ValueError:
            setup_context = None
        return {"project": project, "proof_status": status, "reason": str(exc), "tool": tool,
                "receipts": [], "setup": setup_context, "runtime_check": "NOT_RUN_ON_READ"}
    tool = _tool_state(root, pin["lean_version"])
    rows = _receipts(base)
    project_root = _safe(base, str(manifest.get("project_root") or "."), exists=False)
    current = []
    identities = [(str(row.get("file") or ""), str(row.get("declaration") or ""),
                   str((row.get("concept") or row.get("result") or {}).get("id") or ""),
                   "concept" if row.get("concept") else "result") for row in rows]
    latest_index = {identity: index for index, identity in enumerate(identities)}
    for index, row in enumerate(rows):
        try:
            source = _safe(base, str(row.get("file") or ""))
            live = _sha(source)
            result = row.get("concept") or row.get("result") or {}
            research_root = (proj.path(proj.project_dir, root)
                             if getattr(proj, "project_dir", "") else base)
            bound = (_concept(project, str(result.get('id') or ''), str(result.get('revision') or ''),
                              str(result.get('source_revision') or ''), root) if row.get('concept') else
                     _result(base, manifest, str(result.get("id") or ""),
                             str(result.get("revision") or ""), research_root or base))
            dependencies = _local_dependencies(source, project_root, base)
            recorded_pin=row.get("pin") if isinstance(row.get("pin"),dict) else {}
            reasons=[]
            if live!=row.get("file_digest"):reasons.append("proof source changed")
            if "lakefiles" not in recorded_pin:
                reasons.append("legacy receipt did not pin lakefile configuration")
            elif recorded_pin!=pin:reasons.append("toolchain, libraries, lakefile, project root, or axiom policy changed")
            if bound.get("handle")!=result.get("handle"):reasons.append("bound scientific target changed")
            if dependencies!=row.get("dependencies",{}):reasons.append("imported local proof dependency changed")
            current.append({**row,"stale":bool(reasons),"currentness_reasons":reasons,
                            "pin_gap":"LAKEFILE_NOT_RECORDED" if "lakefiles" not in recorded_pin else None,
                            "superseded":False})
        except (ValueError, OSError):
            current.append({**row, "stale": True,
                            "currentness_reasons":["receipt inputs are unavailable"],
                            "superseded":False})
    groups={}
    for index,identity in enumerate(identities):groups.setdefault(identity,[]).append(index)
    contradictory=False
    for indices in groups.values():
        usable=[index for index in indices if not current[index].get("stale")]
        latest=max(usable or indices)
        conclusive=[index for index in usable if current[index].get("proof_status") in {"CHECKED","FAILED","REJECTED"}]
        last_conclusive=max(conclusive) if conclusive else None
        keep={latest}
        if last_conclusive is not None:keep.add(last_conclusive)
        for index in indices:
            current[index]["latest_attempt"]=index==latest
            current[index]["standing_check"]=index==last_conclusive and current[index].get("proof_status")=="CHECKED"
            current[index]["superseded"]=index not in keep
        if (last_conclusive is not None and current[last_conclusive].get("proof_status") in {"FAILED","REJECTED"}
                and any(current[index].get("proof_status")=="CHECKED" for index in usable if index<last_conclusive)):
            contradictory=True
    active = [row for row in current if not row.get("superseded")]
    latest_attempt=next((row for row in reversed(current) if row.get("latest_attempt")),None)
    standing_checked=next((row for row in reversed(current) if row.get("standing_check") and not row.get("stale")),None)
    last_checked=next((row for row in reversed(current) if row.get("proof_status")=="CHECKED" and not row.get("stale")),None)
    status = "UNAVAILABLE" if not tool["available"] else "UNPROVED"
    if any(row.get("stale") for row in active):
        status = "STALE"
    elif contradictory:
        status = "COULD_NOT_REPRODUCE"
    elif standing_checked is not None:
        status = "CHECKED"
    return {"project": project, "proof_status": status, "tool": tool, "pin": pin,
            "runtime_check": "NOT_RUN_ON_READ", "reason": None,
            "setup": setup(project, root),
            "read_only": bool(proj.external_root), "receipts": current,
            "latest_attempt":({key:latest_attempt.get(key) for key in
                ("id","checked_at","file","declaration","proof_status","stale","reason")}
                if latest_attempt else None),
            "last_current_checked_receipt":({key:last_checked.get(key) for key in
                ("id","checked_at","file","declaration","proof_status")}
                if last_checked else None),
            "reproduction_status":("COULD_NOT_REPRODUCE" if contradictory else
                "LATEST_ATTEMPT_UNAVAILABLE" if standing_checked is not None and latest_attempt
                    and latest_attempt.get("proof_status")=="UNAVAILABLE" else "CURRENT"),
            "informal_alignment": "UNASSESSED"}
