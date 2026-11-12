"""Current document composition: source, dependency, template and output witnesses.

This domain owner stores no manuscript or history. HTTP/native/style compatibility
adapters delegate here. Source mutation remains the existing legacy executor until
the shared candidate-application packet extracts it; it is not duplicated here.
"""

from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from laplace.manuscript import manuscript_source, tex_dependencies
from laplace.pipeline import registry

CLASS_RE = re.compile(r"\\documentclass\s*(?:\[([^]]*)\]\s*)?\{\s*([^}]+?)\s*\}", re.I)
_CLASS_RE = CLASS_RE


def pdf_read(project, root, source, build):
    """An exact current-root output handle; provenance and source freshness differ."""
    from laplace.manuscript import projection_viewer

    if not source.get("root"):
        return None, None
    path = (root / source["root"]).with_suffix(".pdf").resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None, None
    file = path.relative_to(root).as_posix()
    recorded = (build.get("outputs") or {}).get("files", {}).get(file)
    if isinstance(recorded, dict):
        recorded = recorded.get("sha256")
    verified = (
        build.get("outputs_current") is True
        and build.get("ok") is True
        and isinstance(recorded, str)
    )
    try:
        pin = recorded if verified else projection_viewer._output_sha256(path)
    except OSError:
        return None, None
    if not pin:
        return None, None
    pin = "sha256:" + pin.removeprefix("sha256:")
    return (
        {
            "method": "GET",
            "route": "/projection/pdf",
            "query": {"corpus": project, "file": file, "expected_content_revision": pin},
        },
        {
            "file": file,
            "content_revision": pin,
            "verification": "VERIFIED_BUILD" if verified else "OBSERVED_ONLY",
        },
    )


def current(project, root=None, *, source=None, source_tree=None, include_preview=True) -> dict:
    """Selected-source build authority, with a separately labelled style preview.

    Canonical document builds already belong to projection_viewer. Reuse that
    pure status read rather than interpreting absence of a style-preview cache
    as absence of the current manuscript PDF. No build or history read occurs.
    """
    from laplace.manuscript import projection_viewer

    root = Path(root or registry._repo_root()).resolve()
    source = (
        source
        if source is not None
        else manuscript_source.resolve(project, repo_root=root, include_candidates=False)
    )
    build = (
        projection_viewer.recompile_status(
            source["root"],
            repo_root=root,
            corpus=project,
            compile_root=source["root"],
            _selection=source,
        )
        if source.get("root")
        else {
            "state": "idle",
            "ok": None,
            "fresh": False,
            "running": False,
            "reason": "Select a manuscript source.",
        }
    )
    tree = (
        source_tree
        if source_tree is not None
        else (
            manuscript_source.traversal(root / source["root"], root) if source.get("root") else {}
        )
    )
    observed = manuscript_source.observation(project, root, source=source, source_tree=tree)
    presentation = {
        key: build.get(key)
        for key in (
            "state",
            "ok",
            "fresh",
            "running",
            "pdf",
            "built_ts",
            "finished",
            "dependency_changes",
            "outputs",
            "output_proof",
            "outputs_current",
            "output_changes",
        )
        if key in build
    }
    inputs = build.get("input_revisions")
    missing = [
        path
        for path in observed["file_revisions"]
        if not isinstance(inputs, dict) or path not in inputs
    ]
    changed = [
        path
        for path, pin in observed["file_revisions"].items()
        if isinstance(inputs, dict) and path in inputs and inputs[path] != pin
    ]
    coherence = {
        "status": "UNPROVED" if missing else "CHANGED_DURING_READ" if changed else "MATCHED",
        "missing_inputs": missing,
        "changed_inputs": changed,
    }

    def digest(value):
        return (
            "sha256:"
            + hashlib.sha256(
                json.dumps(
                    value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
        )

    label = (
        "UNAVAILABLE"
        if observed["status"] == "UNAVAILABLE"
        else "RUNNING"
        if build.get("running")
        else "FAILED"
        if build.get("ok") is False or build.get("state") in {"error", "failed"}
        else "READY"
        if build.get("ok") is True
        and build.get("fresh") is True
        and coherence["status"] == "MATCHED"
        else "STALE"
        if build.get("ok") is True
        else "NOT_BUILT"
    )
    presentation_revision = digest(presentation)
    result = {
        "schema_version": "laplace.current-document/1",
        "project": project,
        "status": label,
        "selected_source": observed["selected_source"],
        "source_observation": observed,
        "current_build": build,
        "presentation_revision": presentation_revision,
        "observation_coherence": coherence,
        "current_revision": digest(
            {
                "source": observed["revision"],
                "presentation": presentation_revision,
                "coherence": coherence,
            }
        ),
    }
    # A bounded document manifest projects the same selected source and dependency
    # witnesses. It never loads manuscript history or exposes source bodies.
    result["selection_identity"] = manuscript_source.selection_identity(source, project)
    selected = set(observed["file_revisions"])
    selected_paths = {(root / name).resolve() for name in selected}
    dependencies = (
        tex_dependencies.dependency_paths(root / source["root"], root)
        if source.get("root")
        else set()
    )
    pins = {
        name: pin for name, pin in observed["file_revisions"].items() if root / name in dependencies
    }
    pins.update(
        tex_dependencies.snapshot_paths(
            (path for path in dependencies if path not in selected_paths), root
        )
    )
    result["dependency_revisions"] = pins
    files = []
    for name in sorted(selected | set(pins)):
        path = root / name
        if path.suffix.lower() not in {".tex", ".cls", ".sty", ".bst", ".bib"}:
            continue  # Binary dependencies remain in pins, never decoded as editable TeX.
        try:
            access = manuscript_source.source_access(
                project,
                path,
                root,
                source=source,
                source_tree=tree,
                dependencies=dependencies,
                selected_paths=selected_paths,
            )
        except manuscript_source.SourceAccessError:
            continue
        pin = observed["file_revisions"].get(name) or pins.get(name)
        guard = "sha256:" + pin.removeprefix("sha256:") if pin else None
        files.append(
            {
                "file": name,
                **access,
                "expected_source_digest": guard,
                **manuscript_source.source_handles(project, name, guard, access),
            }
        )
    result["files"] = files
    result["template"] = {"status": "UNAVAILABLE", "class_name": None, "class_options": []}
    if source.get("root"):
        root_body = next(
            (
                row.get("text", "")
                for row in tree.get("sources", [])
                if row["file"] == source["root"]
            ),
            "",
        )
        match = _CLASS_RE.search(manuscript_source._uncomment(root_body))
        if match:
            class_name = match.group(2).strip()
            result["template"] = {
                "status": "OBSERVED_SOURCE",
                "class_name": class_name,
                "class_options": [
                    value.strip() for value in (match.group(1) or "").split(",") if value.strip()
                ],
            }
            classes = [row for row in files if row["role"] == "class"]
            if len(classes) == 1:
                result["template"].update(
                    class_file=classes[0]["file"],
                    class_revision=classes[0]["expected_source_digest"],
                    read_handle=classes[0]["read_handle"],
                )
    from laplace.manuscript import document_templates
    result['template'].update(document_templates.discovery(project, root, source))
    from laplace.manuscript import document_style
    try: result['render_defaults'] = document_style.defaults_status(project, root, _observed_source=source)
    except (ValueError, OSError) as error:
        result['render_defaults'] = {'status':'UNAVAILABLE','reason':str(error),'authority':'Canonical defaults are invalid; no legacy substitution was made.'}
    result["read_handles"] = {
        "document": {
            "method": "GET",
            "route": "/authoring/document",
            "query": {"project": project},
        },
        "build": {
            "method": "GET",
            "route": "/authoring/build",
            "query": {"project": project, "view": "summary"},
        },
    }
    result["read_handles"]["pdf"], result["pdf_identity"] = pdf_read(project, root, source, build)
    result["current_revision"] = digest(
        {
            "source": observed["revision"],
            "dependencies": pins,
            "presentation": presentation_revision,
            "coherence": coherence,
            "pdf": result["pdf_identity"],
            "render_defaults": result["render_defaults"].get("revision"),
        }
    )
    if include_preview:
        from laplace.manuscript import document_style

        try:
            result["style_preview"] = document_style.status(project, root)
        except (OSError, ValueError) as exc:
            result["style_preview"] = {
                "status": "UNAVAILABLE",
                "error": str(exc),
                "reason": "Optional style preview is unavailable; document source observation remains authoritative.",
            }
    from laplace.manuscript.build_targets import read_handle as derived_read_handle
    result['derived_output_read'] = derived_read_handle(project)
    return result
