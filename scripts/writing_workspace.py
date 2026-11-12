"""Pinned legacy-workflow bridge to the live interactive writing contracts.

The bridge can record a provider-produced proposal, but it never treats that
proposal as author acceptance. ``apply --accept`` is the explicit review door
and delegates to the guarded controller used by the interactive workspace.
"""
from __future__ import annotations

from laplace.writing import records as writing_records

import argparse
import json
from pathlib import Path
import shlex
import sys
import uuid


def _emit(value: dict, code: int = 0) -> int:
    print(json.dumps(value, ensure_ascii=False, default=str))
    return code


def _scope(root: Path, project: str, mode: str, sections: list[str], target_dir: str = "") -> dict:
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("status") != "resolved" or not source.get("root"):
        raise ValueError("the workflow project has no selected manuscript source")
    manuscript = (root / str(source.get("manuscript_dir") or "")).resolve()
    if not manuscript.is_relative_to(root) or not manuscript.is_dir():
        raise ValueError("the selected manuscript directory is outside the workflow root")
    if target_dir:
        requested = Path(target_dir)
        requested = (requested if requested.is_absolute() else root / requested).resolve()
        if not requested.is_relative_to(root) or requested != manuscript:
            raise ValueError("pipeline target_dir does not match the selected project manuscript")
    return {"project": project, "mode": mode, "section_ids": list(sections),
            "root": str(root), "manuscript_dir": manuscript.relative_to(root).as_posix(),
            "selected_root": source.get("root"), "source_revision": source.get("revision")}


def _command(root: Path, command: str, project: str, mode: str, sections: list[str],
             *extra: str) -> str:
    argv = [str(root / "scripts/laplace-python"), str(root / "scripts/writing_workspace.py"),
            command, project, "--mode", mode, "--root", str(root)]
    for section in sections:
        argv += ["--section", section]
    argv += list(extra)
    return shlex.join(argv)


def _rows(root: Path) -> list[dict]:
    path = root / "contract/talk.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
        except ValueError:
            continue
    return rows


def _context(root: Path, project: str, context_id: str) -> dict:
    from laplace.pipeline import authoring
    value = authoring.load(project, repo_root=root)
    receipt = next((row for row in value.get("contexts", []) if row.get("id") == context_id), None)
    if receipt is None:
        raise ValueError("proposal context is unavailable; rebuild the workflow context")
    return receipt


def _binding(root: Path, project: str, context_id: str) -> dict:
    row = next((item for item in reversed(_rows(root))
                if item.get("record") == "writing-workspace-context"
                and item.get("project") == project and item.get("context_id") == context_id), None)
    if row is None:
        raise ValueError("context was not created by the pinned writing workspace bridge")
    return row


def _proposal(value) -> dict:
    if not isinstance(value, dict) or set(value) != {"answer", "edits"}:
        raise ValueError("proposal must contain exactly answer and edits")
    if not isinstance(value["answer"], str) or not isinstance(value["edits"], list):
        raise ValueError("proposal answer must be text and edits must be a list")
    required = {"file", "line_start", "line_end", "before", "after", "reason"}
    edits = []
    for index, edit in enumerate(value["edits"]):
        if not isinstance(edit, dict) or set(edit) != required:
            raise ValueError(f"proposal edit {index} must contain exactly {sorted(required)}")
        if not all(isinstance(edit[key], str) for key in ("file", "before", "after", "reason")):
            raise ValueError(f"proposal edit {index} text fields have the wrong type")
        if (not isinstance(edit["line_start"], int) or isinstance(edit["line_start"], bool)
                or not isinstance(edit["line_end"], int) or isinstance(edit["line_end"], bool)
                or edit["line_start"] < 1 or edit["line_end"] < edit["line_start"]):
            raise ValueError(f"proposal edit {index} has an invalid 1-based line span")
        edits.append(dict(edit))
    return {"answer": value["answer"], "edits": edits}


def _inspect(root: Path, project: str, turn_id: str) -> dict:
    from laplace.pipeline import authoring
    records = writing_records.fold_records(root)
    turn = records["turns"].get(turn_id)
    if not turn or turn.get("project") != project:
        raise ValueError("unknown workflow proposal for this project")
    reply = turn.get("reply") or {}
    proposal = reply.get("proposal") or {}
    validation = reply.get("proposal_validation")
    stale_ids = {row.get("context_id") for row in authoring.inspect(project, repo_root=root).get("stale", [])}
    application = turn.get("application")
    status = ("INVALID" if isinstance(validation, dict) and validation.get("valid") is False else
              "APPLIED" if application and application.get("complete") else
              "APPLY_INCOMPLETE" if application else
              "STALE" if turn.get("context_id") in stale_ids else "PROPOSED")
    return {"ok": status in {"PROPOSED", "APPLIED"}, "status": status,
            "project": project, "turn_id": turn_id, "session_id": turn.get("session_id"),
            "context_id": turn.get("context_id"), "mode": turn.get("mode"),
            "pipeline_scope": turn.get("pipeline_scope"), "proposal": proposal,
            "proposal_validation": validation,
            "application": application, "stale": turn.get("context_id") in stale_ids}


def _record_proposal(root: Path, project: str, mode: str, sections: list[str],
                     target_dir: str, context_id: str, raw) -> dict:
    if mode not in {"revise", "work"}:
        raise ValueError("manuscript proposals require revise or work mode")
    proposal = _proposal(raw)
    receipt = _context(root, project, context_id)
    binding = _binding(root, project, context_id)
    scope = _scope(root, project, mode, sections, target_dir)
    if binding.get("mode") != mode or binding.get("pipeline_scope") != scope:
        raise ValueError("proposal mode or pipeline scope differs from its context")
    selected = [str(item) for item in receipt.get("selection", []) if item]
    if proposal["edits"] and not selected:
        raise ValueError("the scoped context selected no manuscript files")
    from laplace.manuscript import proposal_preflight
    from laplace.writing import operating as writing_operating
    from laplace.writing import turn_admission
    from laplace.writing import records as writing_records
    session = turn_admission.new_session(root, project, "codex", "legacy-workflow-bridge", "medium")
    turn_id = "WT-" + uuid.uuid4().hex
    selection = {"section_ids": sections, "files": selected}
    brief = writing_operating.build(project, mode, root,
                                    {"surface": "manuscript", "section_ids": sections})
    turn = {"record": "writing-turn", "id": turn_id,
        "session_id": session["id"], "project": project, "request_id": "workflow-" + uuid.uuid4().hex,
        "text": "Legacy workflow produced a reviewable scoped manuscript proposal.",
        "mode": mode, "selection": selection, "context_id": context_id,
        "dependencies": receipt, "document": binding["document"], "pipeline_scope": scope,
        "operating_brief": {"schema_version": brief["schema_version"], "digest": brief["digest"],
            "tool_contract_digest": brief["tool_contract_digest"],
            "writing_style_revision": brief["writing_style"]["revision"],
            "writing_style_profile": brief["writing_style"]["selected_profile"],
            "permissions": brief["permissions"]}}
    validation = proposal_preflight.preflight(root, project, turn, proposal)
    writing_records.bank(root, turn)
    writing_records.bank(root, {"record": "writing-reply", "id": "WR-" + uuid.uuid4().hex,
        "turn_id": turn_id, "session_id": session["id"], "project": project,
        "status": "completed", "text": proposal["answer"], "proposal": validation["proposal"],
        "proposal_validation": {key: validation[key] for key in
            ("schema_version", "valid", "status", "edits", "errors")},
        "origin": "workflow:project-staged"})
    return _inspect(root, project, turn_id)


def _apply(root: Path, project: str, turn_id: str, accept: bool) -> dict:
    if not accept:
        raise ValueError("apply requires explicit --accept authorisation")
    from laplace.manuscript import manuscript_source, review_surface
    from laplace.manuscript import source_application
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("read_only"):
        raise ValueError("selected manuscript source is read-only")
    manuscript = (root / str(source.get("manuscript_dir") or "")).resolve()
    if not manuscript.is_relative_to(root) or not manuscript.is_dir():
        raise ValueError("selected manuscript directory is unavailable inside the workflow root")
    original = review_surface.manuscript_dir
    review_surface.manuscript_dir = lambda corpus="", dir_param="": manuscript if corpus == project else original(corpus, dir_param)
    try:
        result = source_application.apply_proposal(root, {"turn_id": turn_id, "project": project})
    finally:
        review_surface.manuscript_dir = original
    inspected = _inspect(root, project, turn_id)
    return {**inspected, "ok": bool(result.get("complete")), "application": result,
            "status": "APPLIED" if result.get("complete") else "APPLY_INCOMPLETE"}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("context", "call", "proposal", "inspect", "apply"))
    parser.add_argument("project")
    parser.add_argument("--mode", choices=("discuss", "revise", "work", "review"), default="discuss")
    parser.add_argument("--section", action="append", default=[])
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--target-dir", default="")
    parser.add_argument("--context-id", default="")
    parser.add_argument("--turn", default="")
    parser.add_argument("--accept", action="store_true")
    args = parser.parse_args(argv); root = Path(args.root).resolve()
    try:
        if args.command == "context":
            from laplace.manuscript import manuscript_source
            from laplace.writing import operating as writing_operating
            from laplace.core.records import journal
            from laplace.pipeline import authoring
            scope = _scope(root, args.project, args.mode, args.section, args.target_dir)
            brief = writing_operating.build(args.project, args.mode, root,
                                            {"surface": "manuscript", "section_ids": args.section})
            context = authoring.build_context(args.project,
                {"section_ids": args.section} if args.section else None, repo_root=root)
            document = manuscript_source.resolve(args.project, repo_root=root)
            (root / "contract").mkdir(parents=True, exist_ok=True)
            journal.bank_row("contract/talk.jsonl", {"record": "writing-workspace-context",
                "id": "WWC-" + uuid.uuid4().hex, "project": args.project,
                "context_id": context["context_id"], "mode": args.mode,
                "pipeline_scope": scope, "document": document}, root=root)
            extra = ("--target-dir", args.target_dir) if args.target_dir else ()
            transports = {"call": _command(root, "call", args.project, args.mode, args.section),
                "proposal": _command(root, "proposal", args.project, args.mode, args.section,
                    "--context-id", context["context_id"], *extra)}
            return _emit({"ok": True, "operating": brief, "context": context,
                          "pipeline_scope": scope, "transport": transports["call"],
                          "transports": transports})
        if args.command == "call":
            from laplace.native import tools as writing_tools
            value = json.load(sys.stdin)
            if (not isinstance(value, dict) or not isinstance(value.get("operation"), str)
                    or not isinstance(value.get("payload", {}), dict)):
                raise ValueError("stdin requires object {operation,payload}")
            result = writing_tools.execute(root, args.project, args.mode,
                                           value["operation"], value.get("payload") or {})
            partial = isinstance(result, dict) and (result.get("ok") is False or
                result.get("status") in {"MIRROR_PENDING", "PARTIAL", "REFUSED", "FAILED"})
            return _emit({"ok": not partial, "result": result, "project": args.project,
                          "mode": args.mode}, 2 if partial else 0)
        if args.command == "proposal":
            if not args.context_id:
                raise ValueError("proposal requires --context-id from the context command")
            value = _record_proposal(root, args.project, args.mode, args.section,
                                     args.target_dir, args.context_id, json.load(sys.stdin))
            return _emit(value, 0 if value["ok"] else 2)
        if args.command == "inspect":
            if not args.turn: raise ValueError("inspect requires --turn")
            value = _inspect(root, args.project, args.turn)
            return _emit(value, 0 if value["ok"] else 2)
        if not args.turn: raise ValueError("apply requires --turn")
        value = _apply(root, args.project, args.turn, args.accept)
        return _emit(value, 0 if value["ok"] else 2)
    except Exception as exc:
        return _emit({"ok": False, "error": str(exc), "project": args.project,
                      "mode": args.mode, "command": args.command}, 2)


if __name__ == "__main__":
    raise SystemExit(main())
