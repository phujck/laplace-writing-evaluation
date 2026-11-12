"""Bounded, reusable stage briefs over the existing writing owners.

Reading a stage never launches a model, edits a manuscript, or awards acceptance.
Its revision describes instructions and profile selection, not scientific truth
or a frozen source edition. Source reads and writes keep their canonical guards.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
from pathlib import Path

CATALOGUE = "profiles/writing/stages-v1.json"
ACCEPTANCE = "profiles/acceptance/writing-workspace-v1.json"
VIEWS = {"summary", "guidance", "materials", "full"}
MAX_PROFILE_BYTES = 48_000


def _digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()).hexdigest()


def _profile(root: Path, relative: str):
    local = root / relative
    source_root = root if local.exists() or local.is_symlink() else source_tree()
    path = source_root / relative
    if (not path.resolve().is_relative_to(source_root.resolve()) or path.is_symlink()
            or not path.is_file()):
        raise ValueError("Stage profile must be a regular owned file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_PROFILE_BYTES + 1)
    if len(raw) > MAX_PROFILE_BYTES:
        raise ValueError("Stage profile exceeds the bounded size")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Stage profile must contain an object")
    return value, {"path": relative, "origin": "repository" if path == local else "deployed",
                   "revision": "sha256:" + hashlib.sha256(raw).hexdigest()}


def _call(operation, payload=None, purpose=None):
    value = {"operation": operation, "payload": payload or {}}
    if purpose:
        value["purpose"] = purpose
    return value



def programme(root: Path, *, catalogue=None, reference=None, compact=False):
    """One ordered recipe, not an execution ledger or a new writing_stage enum."""
    if catalogue is None:
        catalogue, reference = _profile(Path(root), CATALOGUE)
    value = catalogue.get("programme")
    if not isinstance(value, dict) or value.get("schema_version") != "laplace.writing-programme/1":
        raise ValueError("Writing programme profile is absent or invalid")
    phases = value.get("phases")
    if not isinstance(phases, list) or not 1 <= len(phases) <= 16:
        raise ValueError("Writing programme must contain a bounded ordered phase list")
    seen, kinds = set(), set()
    for phase in phases:
        if not isinstance(phase, dict):
            raise ValueError("Writing programme phase must be an object")
        ident, kind = phase.get("id"), phase.get("work_kind")
        if (not isinstance(ident, str) or not ident or ident in seen
                or not isinstance(kind, str) or not kind.startswith("writing-") or kind in kinds):
            raise ValueError("Writing programme phase identities/kinds must be unique")
        dependencies = phase.get("depends_on")
        if (not isinstance(dependencies, list) or len(dependencies) != len(set(dependencies))
                or any(dep not in seen for dep in dependencies)):
            raise ValueError("Programme prerequisites must name earlier phases")
        for key in ("title", "guidance", "completion", "consumer"):
            if not isinstance(phase.get(key), str) or not phase[key].strip():
                raise ValueError("Writing programme phase requires " + key)
        if not isinstance(phase.get("read"), list) or not phase["read"]:
            raise ValueError("Writing programme phase requires owner reads")
        seen.add(ident)
        kinds.add(kind)
    result = {**value, "profile": reference, "revision": _digest({"catalogue": reference}),
              "autonomous_execution": False, "acceptance": "NOT_ASSESSED"}
    if compact:
        result["phases"] = [{key: item[key] for key in
            ("id", "title", "work_kind", "depends_on", "consumer")} for item in phases]
    return result


def literature_observation(scope):
    """Project an actually read bounded scope without conflating cite/build and support."""
    gaps = scope.get("gaps") or []
    citation_only = {"not-yet-cited", "citation-not-rendered", "bibliography-build-not-current"}
    support_gaps = [gap for gap in gaps if gap.get("kind") not in citation_only]
    page = scope.get("pagination") or {}
    complete = (page.get("offset") == 0 and page.get("next_offset") is None
                and len(scope.get("claims") or []) == page.get("total")
                and not scope.get("gaps_omitted"))
    qualified = complete and bool(scope.get("claims")) and not support_gaps
    return {"revision": scope.get("revision"), "coverage_complete": complete,
            "support_usable": qualified, "support_gaps": support_gaps,
            "citation_build_gaps": [gap for gap in gaps if gap.get("kind") in citation_only],
            "ready_for_completion": scope.get("ready_for_completion") is True,
            "qualification": "Scoped documentary qualification, not independent scientific acceptance.",
            "pagination": page, "gaps_omitted": scope.get("gaps_omitted", 0)}


def inspect(project: str, payload: dict | None = None, repo_root=None) -> dict:
    from laplace.pipeline import registry
    from laplace.manuscript import manuscript_source, project_protocol, writing_style
    from laplace.core.identity import revision_matches

    root = Path(repo_root or source_tree()).resolve()
    if registry.resolve(project, repo_root=root) is None:
        raise ValueError("Unknown project")
    payload = payload or {}
    if set(payload) - {"stage", "view", "known_revision"}:
        raise ValueError("writing_stage accepts only stage, view and known_revision")
    view = payload.get("view", "guidance")
    if view == "full":
        view = "guidance"
    if view not in VIEWS:
        raise ValueError("stage view must be summary, guidance (or full) or materials")
    known = payload.get("known_revision")
    if known is not None and (not isinstance(known, str) or len(known) > 80):
        raise ValueError("known_revision must be a stage revision string")
    catalogue, catalogue_ref = _profile(root, CATALOGUE)
    stages = catalogue.get("stages")
    if not isinstance(stages, dict) or not stages:
        raise ValueError("Writing stage catalogue is empty or invalid")
    stage = payload.get("stage")
    base = {"schema_version": "laplace.writing-stage/1", "project": project,
            "autonomous_execution": False, "acceptance": "NOT_ASSESSED"}
    if not stage:
        revision = _digest({"catalogue": catalogue_ref})
        result = {**base, "revision": revision,
                  "revision_scope": "catalogue only; each opened stage has its own revision",
                  "reentry_action": _call("writing_stage", {"known_revision": revision}),
                  "full_stage_handle": _call("writing_stage"), "profile": catalogue_ref}
        if revision_matches(known, revision):
            return {key: value for key, value in {**result, "unchanged": True, "delta": []}.items()
                    if key in {"schema_version", "project", "revision", "full_stage_handle", "unchanged", "delta"}}
        return {**result, "unchanged": False,
                "programme": programme(root, catalogue=catalogue, reference=catalogue_ref, compact=True),
                "stages": [
            {"id": key, "title": item["title"], "purpose": item["purpose"],
             "open": _call("writing_stage", {"stage": key})}
            for key, item in stages.items()]}
    if not isinstance(stage, str) or stage not in stages:
        raise ValueError("Unknown writing stage; call writing_stage {} for current stages")
    recipe = stages[stage]
    profiles = {"stage": catalogue_ref}
    voice = None
    if recipe.get("voice"):
        voice = writing_style.context(project, root)
        profiles["voice"] = {k: voice[k] for k in (
            "revision", "profile_path", "profile_revision", "profile_title", "profile_version",
            "guidance_sha256", "genre")}
    acceptance = None
    if recipe.get("acceptance_profile"):
        data, reference = _profile(root, ACCEPTANCE)
        acceptance = data["profiles"][recipe["acceptance_profile"]]
        profiles["acceptance"] = {**reference, "section": recipe["acceptance_profile"]}
    presentation = None
    if stage == "presentation":
        from laplace.manuscript import document_style
        settings = document_style.defaults_status(project, root)
        presentation = {"document_settings": settings, "read_operation": "document",
                        "change_operation": "style"}
        profiles["document_style"] = {"revision": settings["revision"], "scope": "project", "effective_origin":settings["effective_origin"], "consumed_source":settings["consumed_source"]}
    guides = project_protocol.read(project, {}, root)
    profiles["project_guidance"] = {"revision": guides["revision"],
                                   "catalog_revision": guides["catalog_revision"]}
    source = manuscript_source.resolve(project, repo_root=root)
    selected_source = {k: source.get(k) for k in (
        "status", "root", "manuscript_dir", "edition", "revision", "read_only")}
    revision = _digest({"stage": stage, "recipe": recipe, "profiles": profiles,
                        "selected_source": selected_source})
    handle = _call("writing_stage", {"stage": stage, "view": "guidance"})
    result = {**base, "stage": stage, "title": recipe["title"],
              "revision": revision, "profiles": profiles, "full_stage_handle": handle,
              "reentry_action": _call("writing_stage", {"stage": stage, "known_revision": revision}),
              "revision_scope": "stage instructions and selected profile/guidance identities; read live source before editing"}
    if revision_matches(known, revision):
        return {key: value for key, value in {**result, "unchanged": True, "delta": []}.items()
                if key in {"schema_version", "project", "stage", "revision", "full_stage_handle", "unchanged", "delta"}}
    result["unchanged"] = False
    if view == "summary":
        return {**result, "purpose": recipe["purpose"],
                "materials_handle": _call("writing_stage", {"stage": stage, "view": "materials"})}

    materials = {
        "selected_source": selected_source,
        "project_guides": guides.get("documents", []),
        "read": recipe["read"],
        "tool_contract": "help(operation) supplies exact current required fields; do not infer write payloads from prose",
        "source_policy": "Read current affected passages and required dependencies. History and original calibration sources are explicit descents, not repeated stage context.",
    }
    if source.get("root"):
        materials["selected_source_read"] = _call("source", {"files": [source["root"]]},
            "Read the selected root and follow its chapter includes or the structure overview; document is the presentation state, not manuscript prose")
    if presentation is not None:
        materials["presentation"] = presentation
    if voice:
        materials["voice"] = {
            "guidance": voice["content"], "project_guidance": voice["guidance"],
            "genre": voice["genre"], "calibration": voice["provenance"],
            "source_catalogue": _call("writing_style", {"view": "provenance"}),
            "full_profile": _call("writing_style", {"view": "profile"}),
            "selection_tool": "writing_style_change",
            "global_profile_edit_tool": "writing_style_profile_change",
        }
    if acceptance is not None:
        # Historical benchmark samples stay in the explicit profile source. They
        # are neither current observations nor compulsory universal thresholds.
        materials["acceptance_profile"] = {k: v for k, v in acceptance.items()
                                            if not k.startswith("reference_observations")}
    if view == "materials":
        return {**result, "materials": materials}
    return {**result, "purpose": recipe["purpose"], "guidance": recipe["guidance"],
            "materials": materials, "apply": recipe["apply"], "verify": recipe["verify"],
            "completion": recipe["completion"],
            "record_result": {"operation": "store_artifact", "required_content": [
                "stage and profile revisions used", "actual read coverage", "applied receipt identities",
                "observed verification and remaining gaps"],
                "rule": "Reuse one project result note if useful. A preparation call or self-authored receipt is not acceptance."},
            "reentry": "Use reentry_action verbatim for this stage; catalogue and stage revisions are different. Omit known_revision when explicitly requesting the full body again."}


def main(argv=None) -> int:
    """The same stage contract for repository/engine sessions with a shell."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Registered project identity in this checkout")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--stage", help="Omit to discover available stage identities")
    parser.add_argument("--view", choices=sorted(VIEWS), default="guidance")
    parser.add_argument("--known-revision", help="Return only a handle when guidance is unchanged")
    args = parser.parse_args(argv)
    payload = {"view": args.view}
    if args.stage:
        payload["stage"] = args.stage
    if args.known_revision:
        payload["known_revision"] = args.known_revision
    try:
        result = inspect(args.project, payload, args.repo_root)
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
