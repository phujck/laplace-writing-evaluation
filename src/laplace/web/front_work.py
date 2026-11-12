"""Pure read model for the next-generation Front ``Work`` room.

The room does not embed either historical page.  It preserves their mechanisms as
source-bearing organs which a carrier can render around the attended object:

* the Walk's content-faithful, source-addressed manuscript canvas and its existing
  review, version, redline, PDF and SyncTeX doors; and
* the Pipeline's real release chain, composed brief, typed verdict, lazy organ
  readers, in-place dials and scoped controls.

This module has no HTTP handler and no writer.  POST doors are described so the
carrier can explain the already-existing governed act, but nothing here invokes one.
Absent joined evidence is ``UNKNOWN`` rather than an empty success.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import quote

SCHEMA = "laplace.aisthesis-work-room/1"
ORGAN_SCHEMA = "laplace.aisthesis-work-organ/1"
CAPABILITY_SCHEMA = "laplace.aisthesis-work-capability/1"
ACTION_LAYER_SCHEMA = "laplace.aisthesis-manuscript-action-layer/1"
LAUNCH_ACTION_SCHEMA = "laplace.aisthesis-pipeline-launch-action/1"

_STATES = frozenset({"COMPLETE", "UNKNOWN", "REFUSED"})
_DISPOSITIONS = frozenset({"KEEP", "TRANSFORM", "SUBMERGE", "RETIRE"})


def _canon(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def _handle(kind: str, value: Any) -> str:
    return f"{kind}:sha256:{hashlib.sha256(_canon(value)).hexdigest()}"


def _q(value: str) -> str:
    return quote(str(value or ""), safe="")


def _state(value: Mapping[str, Any] | None) -> tuple[str, str]:
    if value is None:
        return "UNKNOWN", "the canonical producer has not been joined into this projection"
    if not isinstance(value, Mapping):
        return "REFUSED", "the joined producer returned a malformed non-object value"
    if value.get("error") or value.get("ok") is False:
        return "REFUSED", str(value.get("error") or value.get("note") or "producer refused")
    if not value:
        return "UNKNOWN", "the joined producer returned an empty object with no affirmative evidence"
    return "COMPLETE", "joined from the canonical read producer"


def _door(
    method: str,
    route: str,
    *,
    authority: str,
    evidence_state: str,
    effect: str = "read",
    cost_class: str = "none",
    note: str = "",
) -> dict[str, Any]:
    """Describe one existing door without invoking it."""
    method = method.upper()
    return {
        "method": method,
        "route": route,
        "authority": authority,
        "effect": effect,
        "cost_class": cost_class,
        "evidence_state": evidence_state,
        "projection_executes": False,
        "authority_effect": "none",
        "note": note,
    }


def _omission(
    ident: str,
    label: str,
    *,
    cause: str,
    continuation: str,
    count: int = 1,
    members: list[str] | None = None,
) -> dict[str, Any]:
    ordered = list(members or [])
    return {
        "id": ident,
        "label": label,
        "cause": cause,
        "count": int(count),
        "member_digest": _handle("omission-members", ordered),
        "continuation": continuation,
    }


def _capability(
    ident: str,
    label: str,
    *,
    family: str,
    disposition: str,
    state: str,
    reason: str,
    source: list[str],
    reads: list[dict[str, Any]] | None = None,
    acts: list[dict[str, Any]] | None = None,
    evidence: Mapping[str, Any] | None = None,
    omissions: list[dict[str, Any]] | None = None,
    continuation: str = "",
    preserves: list[str] | None = None,
) -> dict[str, Any]:
    if disposition not in _DISPOSITIONS:
        raise ValueError(f"unknown disposition {disposition!r}")
    if state not in _STATES:
        raise ValueError(f"unknown state {state!r}")
    anchor = f"work:{family}:{ident}"
    out: dict[str, Any] = {
        "schema_version": CAPABILITY_SCHEMA,
        "id": ident,
        "semantic_anchor": anchor,
        "family": family,
        "label": label,
        "disposition": disposition,
        "state": state,
        "reason": reason,
        "source": list(source),
        "reads": list(reads or []),
        "acts": list(acts or []),
        "evidence": dict(evidence or {}),
        "omissions": list(omissions or []),
        "continuation": continuation,
        "preserves": list(preserves or []),
        "read_only_projection": True,
    }
    out["capability_handle"] = _handle("work-capability", out)
    return out


def _blocks(document: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(document, Mapping):
        return []
    out: list[Mapping[str, Any]] = []
    for section in document.get("sections") or []:
        if not isinstance(section, Mapping):
            continue
        out.extend(b for b in section.get("blocks") or [] if isinstance(b, Mapping))
    return out


def _words(value: Any) -> str:
    """Small human-facing rendering of one already-parsed Walk value.

    The Walk remains the parsing authority.  This only collapses its typed pieces to a
    bounded resting excerpt for the carrier; exact TeX and source spans remain available
    on the block itself through the continuation.
    """
    if value is None:
        return ""
    return " ".join(str(value).split())


def _block_words(block: Mapping[str, Any]) -> str:
    title = _words(block.get("title"))
    if title:
        return title
    caption = _words(block.get("caption"))
    if caption:
        return caption
    text = _words(block.get("text"))
    if text:
        return text
    pieces: list[str] = []
    for piece in block.get("pieces") or []:
        if not isinstance(piece, Mapping):
            continue
        kind = str(piece.get("t") or "")
        if kind == "text":
            pieces.append(_words(piece.get("s")))
        elif kind == "cite":
            keys = [_words(key) for key in piece.get("keys") or [] if _words(key)]
            if keys:
                pieces.append("[" + "; ".join(keys) + "]")
        elif kind == "ref" and piece.get("label"):
            pieces.append(f"reference {_words(piece.get('label'))}")
        elif kind in {"math", "macro"}:
            pieces.append(_words(piece.get("s")))
    joined = _words(" ".join(p for p in pieces if p))
    if joined:
        return joined
    # Raw front matter is still valuable at rest.  Remove only the environment wrapper;
    # the exact source remains behind the source-addressed continuation.
    raw = _words(block.get("tex"))
    for marker in (
        r"\begin{abstract}", r"\end{abstract}", r"\begin{quote}",
        r"\end{quote}", r"\itshape", r"\\",
    ):
        raw = raw.replace(marker, " ")
    return _words(raw)


def _action_authority(context: Mapping[str, Any] | None) -> dict[str, Any]:
    """Carry, but never invent, a stronger provider/seat authority face.

    None of the existing projection/storyboard endpoints accepts a provider binding
    receipt.  The carrier therefore exposes an absent receipt as ``UNKNOWN`` while
    saying plainly that it is not an endpoint precondition.  This prevents both a
    forged green light and an unnecessary block on the endpoint's actual contract.
    """
    ctx = context if isinstance(context, Mapping) else {}
    supplied = ctx.get("provider_authority")
    if not isinstance(supplied, Mapping) or not supplied:
        return {
            "state": "UNKNOWN",
            "reason": "no stronger provider or seat authority receipt was supplied",
            "required_by_endpoint": False,
            "evidence": {},
        }
    supplied_state = str(supplied.get("state") or supplied.get("status") or "COMPLETE").upper()
    if supplied_state not in _STATES:
        supplied_state = "UNKNOWN"
    return {
        "state": supplied_state,
        "reason": _words(supplied.get("reason")) or "a stronger authority face was supplied",
        "required_by_endpoint": False,
        "evidence": dict(supplied),
    }


def _request(
    method: str,
    route: str,
    *,
    query: Mapping[str, Any] | None = None,
    body: Mapping[str, Any] | None = None,
    body_kind: str = "json",
) -> dict[str, Any]:
    """Describe one request for the carrier's shared gateway; never execute it."""
    return {
        "method": method.upper(),
        "route": route,
        "query": dict(query or {}),
        "body": dict(body or {}),
        "body_kind": body_kind,
        "projection_executes": False,
    }


def _editor_action_layer(
    evidence: Mapping[str, Any] | None,
    *,
    corpus: str,
    context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    ev = evidence if isinstance(evidence, Mapping) else {}
    ctx = context if isinstance(context, Mapping) else {}
    editor = ev.get("editor") if isinstance(ev.get("editor"), Mapping) else {}
    file_name = str(editor.get("file") or "")
    content = editor.get("content")
    source_digest = editor.get("expected_source_digest")
    selection_identity = editor.get("selection_identity")
    actor = _words(ctx.get("actor"))
    profile = _words(ctx.get("profile"))
    surface = _words(editor.get("surface")) or "front-work"
    missing: list[str] = []
    if not file_name:
        missing.append("exact manuscript file")
    if not isinstance(content, str):
        missing.append("complete editable source bytes")
    if not isinstance(source_digest, str) or not source_digest.startswith("sha256:") or len(source_digest) != 71 or any(c not in "0123456789abcdef" for c in source_digest[7:]):
        missing.append("physical source digest from the same owner read")
    if corpus and not selection_identity:
        missing.append("selected document identity from the same owner read")
    if not actor:
        missing.append("explicit actor")
    edit_state = "COMPLETE" if not missing else "UNKNOWN"
    edit_reason = (
        "exact editor source and actor are joined"
        if not missing else "missing " + ", ".join(missing)
    )

    versions_value = ev.get("versions") if isinstance(ev.get("versions"), Mapping) else {}
    version_rows = []
    for index, row in enumerate(versions_value.get("states") or versions_value.get("versions") or []):
        if not isinstance(row, Mapping):
            continue
        version_id = str(row.get("version_id") or row.get("id") or "")
        version_rows.append(
            {
                "semantic_anchor": f"work:manuscript:version:{version_id or index + 1}",
                "version_id": version_id,
                "label": _words(row.get("label") or row.get("message") or version_id) or f"Version {index + 1}",
                "created_at": str(row.get("created_at") or row.get("timestamp") or row.get("ts") or ""),
                "actor": _words(row.get("actor") or row.get("author") or row.get("by")),
                "source_file": row.get("source_file"),
                "restorable": bool(row.get("restorable") or row.get("kind") == "editor-save" or row.get("schema_version") == "laplace.editor-save/1") and row.get("source_file") == file_name,
                "restore_reason": "exact inspected editor target" if row.get("source_file") == file_name else "saved target differs or is unproved; inspect its source first",
                "source": dict(row),
            }
        )

    authority = _action_authority(ctx)
    corpus_name = corpus or str(editor.get("corpus") or "")
    shared_preflight = {
        "source": {"state": "COMPLETE" if "physical source digest from the same owner read" not in missing else "UNKNOWN",
                   "expected_source_digest": source_digest,
                   "read": _request("GET", "/projection/tex", query={"file": file_name, "corpus": corpus or str(editor.get("corpus") or ""), "view": "source"})},
        "actor": {
            "state": "COMPLETE" if actor else "UNKNOWN",
            "value": actor,
            "reason": "explicit actor supplied" if actor else "the canonical write endpoints require an explicit actor",
        },
        "profile": {
            "state": "COMPLETE" if profile else "UNKNOWN",
            "value": profile,
            "mode": "EXPLICIT" if profile else "UNSUPPLIED",
            "reason": "explicit profile supplied" if profile else "no provider profile is part of the projection write contract",
        },
        "provider_authority": authority,
    }
    exact_file_query = {"file": file_name, "corpus": corpus_name}
    save_query = {
        **exact_file_query,
        "bank": "editor",
        "author": actor,
        "surface": surface,
        "expected_selection": selection_identity,
        "expected_source_digest": source_digest,
    }
    return {
        "schema_version": ACTION_LAYER_SCHEMA,
        "semantic_anchor": "work:manuscript:actions",
        "state": edit_state,
        "reason": edit_reason,
        "actor": actor,
        "profile": profile,
        "provider_authority": authority,
        "editor": {
            "semantic_anchor": "work:manuscript:editor",
            "state": edit_state,
            "reason": edit_reason,
            "file": file_name,
            "content": content if isinstance(content, str) else "",
            "content_handle": _handle("editor-source", content) if isinstance(content, str) else "",
            "expected_source_digest": source_digest,
            "selection_identity": selection_identity,
            "read": _request("GET", "/projection/tex", query={**exact_file_query, "view": "source"}),
            "surface": surface,
            "save": {
                "semantic_anchor": "work:manuscript:action:save",
                "label": "Save a new version",
                "state": edit_state,
                "request": _request("POST", "/projection/tex", query=save_query, body_kind="raw-text"),
                "body_source": "editor.content",
                "banks": ["editor-save", "editor-save-exemplar"],
                "restore": False,
                "preflight": shared_preflight,
            },
        },
        "compile": {
            "semantic_anchor": "work:manuscript:action:compile",
            "label": "Recompile and follow",
            "state": "COMPLETE" if file_name and actor else "UNKNOWN",
            "reason": "exact file and actor are joined" if file_name and actor else "compile requires an exact file and actor",
            "request": _request(
                "POST", "/projection/recompile",
                body={"file": file_name, "corpus": corpus_name, "by": actor},
            ),
            "status_request": _request("GET", "/projection/recompile", query=exact_file_query),
            "local_safe": True,
            "banks_latest_save_compile": True,
            "preflight": shared_preflight,
        },
        "synctex": {
            "semantic_anchor": "work:manuscript:action:synctex",
            "label": "Source and page correspondence",
            "state": "COMPLETE" if file_name else "UNKNOWN",
            "reason": "exact source file is joined" if file_name else "SyncTeX requires an exact source file",
            "follow": _request("GET", "/projection/follow", query=exact_file_query),
            "locate": _request("GET", "/projection/locate", query={**exact_file_query, "section": "", "line": ""}),
            "reverse": _request("GET", "/projection/synctex", query={**exact_file_query, "page": "", "x": "", "y": ""}),
            "read_only": True,
        },
        "versions": {
            "semantic_anchor": "work:manuscript:action:versions",
            "label": "Version trail",
            "state": "COMPLETE" if version_rows or versions_value else "UNKNOWN",
            "reason": "banked version evidence is joined" if version_rows or versions_value else "version evidence has not been joined",
            "rows": version_rows,
            "read": _request("GET", "/review/states", query={"corpus": corpus_name}),
        },
        "redline": {
            "semantic_anchor": "work:manuscript:action:redline",
            "label": "Compare two banked states",
            "state": "COMPLETE" if len(version_rows) >= 2 else "UNKNOWN",
            "reason": "two or more banked states are joined" if len(version_rows) >= 2 else "redline needs two banked states",
            "request": _request("GET", "/review/compare", query={"corpus": corpus_name, "a": "", "b": ""}),
            "read_only": True,
        },
        "restore": {
            "semantic_anchor": "work:manuscript:action:restore",
            "label": "Restore as a new save",
            "state": "COMPLETE" if edit_state == "COMPLETE" and any(row["restorable"] for row in version_rows) else "UNKNOWN",
            "reason": "an explicitly restorable editor save is joined" if file_name and any(row["restorable"] for row in version_rows) else "no explicitly restorable editor-save version is joined",
            "request": _request("POST", "/projection/restore", body={"file": file_name, "version_id": "", "corpus": corpus_name,
                                                                       "expected_source_digest": source_digest, "expected_selection": selection_identity}),
            "restore_as_new_save": True,
            "rewinds_history": False,
            "ui_arm_required": True,
            "preflight": shared_preflight,
        },
        "read_only_projection": True,
        "gateway": "shared-carrier-request",
        "owns_fetch": False,
        "owns_store": False,
    }


def _launch_action_layer(
    controls: list[dict[str, Any]],
    *,
    project: str,
    context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    ctx = context if isinstance(context, Mapping) else {}
    actor = _words(ctx.get("actor"))
    profile = _words(ctx.get("profile"))
    authority = _action_authority(ctx)
    actions: list[dict[str, Any]] = []
    for index, control in enumerate(controls):
        action = str(control.get("action") or "")
        cost_class = str(control.get("cost_class") or "UNKNOWN")
        owner = str(control.get("owner") or "")
        missing = [label for label, value in (("action", action), ("organ", owner), ("actor", actor)) if not value]
        control_state = "COMPLETE" if not missing and cost_class in {"local-safe", "model-heavy"} else "UNKNOWN"
        arm_required = bool(control.get("arm_to_fire"))
        model_heavy = cost_class == "model-heavy"
        body = {
            "corpus": project,
            "action": action,
            "by": actor,
            "armed": False,
            "mode": control.get("mode"),
            "profile": profile or None,
        }
        actions.append(
            {
                "schema_version": LAUNCH_ACTION_SCHEMA,
                "semantic_anchor": f"work:pipeline:launch:{action or index + 1}",
                "action": action,
                "label": _words(control.get("label") or control.get("what") or action) or "Unnamed action",
                "what": _words(control.get("what")),
                "state": control_state,
                "reason": "exact launch preflight is present" if not missing else "missing " + ", ".join(missing),
                "organ": owner,
                "cost_class": cost_class,
                "local_safe": cost_class == "local-safe",
                "model_heavy": model_heavy,
                "actor": actor,
                "profile": profile,
                "profile_mode": "EXPLICIT" if profile else "CANONICAL_DEFAULT",
                "arm_required": arm_required,
                "banks": str(control.get("banks") or ("work-order" if model_heavy else "")),
                "bank_before_effect": model_heavy,
                "effect_on_success": "banked work order only; no model is spawned" if model_heavy else "canonical local action",
                "request": _request("POST", "/storyboard/run/launch", body=body),
                "preflight": {
                    "cost": {"state": "COMPLETE" if cost_class in {"local-safe", "model-heavy"} else "UNKNOWN", "value": cost_class},
                    "organ": {"state": "COMPLETE" if owner else "UNKNOWN", "value": owner},
                    "actor": {"state": "COMPLETE" if actor else "UNKNOWN", "value": actor},
                    "profile": {"state": "COMPLETE", "value": profile, "mode": "EXPLICIT" if profile else "CANONICAL_DEFAULT"},
                    "arming": {"state": "COMPLETE", "required": arm_required},
                    "provider_authority": authority,
                },
            }
        )
    return {
        "schema_version": "laplace.aisthesis-pipeline-launch-layer/1",
        "semantic_anchor": "work:pipeline:launch",
        "state": "COMPLETE" if actions and all(row["state"] == "COMPLETE" for row in actions) else "UNKNOWN",
        "reason": "canonical storyboard launch roster is joined" if actions else "no canonical launch controls are joined",
        "actor": actor,
        "profile": profile,
        "provider_authority": authority,
        "actions": actions,
        "gateway": "shared-carrier-request",
        "owns_fetch": False,
        "owns_store": False,
    }


def _manuscript_surface(
    document: Mapping[str, Any] | None,
    evidence: Mapping[str, Any] | None,
    *,
    corpus: str,
    action_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize the historical Walk into one source-bearing Work surface.

    No new parser or store is founded here.  Section order, blocks, source spans and
    assets all descend from :func:`walk.doc`; auxiliary postures descend from the exact
    evidence already admitted to :func:`project`.
    """
    state, reason = _state(document)
    ev = evidence if isinstance(evidence, Mapping) else {}
    sections: list[dict[str, Any]] = []
    for section_index, section in enumerate((document or {}).get("sections") or []):
        if not isinstance(section, Mapping):
            continue
        normalized_blocks: list[dict[str, Any]] = []
        line_starts: list[int] = []
        line_ends: list[int] = []
        for block_index, block in enumerate(section.get("blocks") or []):
            if not isinstance(block, Mapping):
                continue
            src = dict(block.get("src") or {}) if isinstance(block.get("src"), Mapping) else {}
            if isinstance(src.get("line_start"), int):
                line_starts.append(src["line_start"])
            if isinstance(src.get("line_end"), int):
                line_ends.append(src["line_end"])
            block_id = str(block.get("id") or f"{section_index + 1}:{block_index + 1}")
            normalized_blocks.append(
                {
                    "id": block_id,
                    "semantic_anchor": f"work:manuscript:block:{block_id}",
                    "kind": str(block.get("kind") or "content"),
                    "words": _block_words(block),
                    "source": src,
                    "labels": [str(item) for item in block.get("labels") or []],
                    "asset": str(block.get("image") or ""),
                    "reason": _words(block.get("reason")),
                    "order": block_index,
                }
            )
        section_id = str(section.get("id") or f"section-{section_index + 1}")
        source = {
            "file": str(section.get("file") or ""),
            "line_start": min(line_starts) if line_starts else None,
            "line_end": max(line_ends) if line_ends else None,
        }
        section_state = state
        section_reason = reason
        if state == "COMPLETE" and any(not block["source"].get("file") for block in normalized_blocks):
            section_state = "UNKNOWN"
            section_reason = "one or more visible blocks lack an exact source address"
        sections.append(
            {
                "id": section_id,
                "semantic_anchor": f"work:manuscript:section:{section_id}",
                "title": _words(section.get("title")) or "Untitled section",
                "state": section_state,
                "reason": section_reason,
                "order": section_index,
                "source": source,
                "blocks": normalized_blocks,
                "block_count": len(normalized_blocks),
            }
        )

    def posture(key: str, label: str, continuation: str) -> dict[str, Any]:
        value = ev.get(key) if key in ev else None
        posture_state, posture_reason = _state(value)
        return {
            "id": key,
            "semantic_anchor": f"work:manuscript:posture:{key}",
            "label": label,
            "state": posture_state,
            "reason": posture_reason,
            "evidence": dict(value) if isinstance(value, Mapping) else {},
            "continuation": continuation,
        }

    corpus_q = _q(corpus)
    suffix = f"?corpus={corpus_q}" if corpus else ""
    postures = [
        {
            "id": "source",
            "semantic_anchor": "work:manuscript:posture:source",
            "label": "Source manuscript",
            "state": state,
            "reason": reason,
            "evidence": {
                "root": str((document or {}).get("root") or ""),
                "counts": dict((document or {}).get("counts") or {}),
            },
            "continuation": "/walk/doc" + suffix,
        },
        posture("pdf", "Typeset PDF geometry", "/projection/pdfinfo"),
        posture("review", "Findings and author hand", f"/review/findings{suffix}"),
        posture("versions", "Version history", f"/review/states{suffix}"),
        posture("compile", "Compile and hot reload", "/projection/recompile"),
        posture("redline", "Live redline", f"/review/compare{suffix}"),
        posture("feedback", "Durable anchored feedback", "/projection/feedback"),
    ]
    return {
        "schema_version": "laplace.aisthesis-manuscript-surface/1",
        "semantic_anchor": "work:manuscript",
        "state": state,
        "reason": reason,
        "title": _words((document or {}).get("title")) or (corpus or "Manuscript"),
        "fidelity": _words((document or {}).get("fidelity")),
        "counts": dict((document or {}).get("counts") or {}),
        "sections": sections,
        "postures": postures,
        "actions": _editor_action_layer(ev, corpus=corpus, context=action_context),
        "source_door": "/walk/doc" + suffix,
        "read_only": True,
        "authority_effect": "none",
    }


def _pipeline_surface(
    chain: Mapping[str, Any] | None,
    brief: Mapping[str, Any] | None,
    verdict: Mapping[str, Any] | None,
    *,
    project: str,
    action_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    state, reason = _state(chain)
    release_states: list[dict[str, Any]] = []
    for index, row in enumerate((chain or {}).get("states") or []):
        if not isinstance(row, Mapping):
            continue
        ident = str(row.get("state") or f"stage-{index + 1}")
        release_states.append(
            {
                "id": ident,
                "semantic_anchor": f"work:pipeline:stage:{ident.lower()}",
                "label": ident.replace("_", " ").title(),
                "status": str(row.get("status") or "UNKNOWN").upper(),
                "next_action": _words(row.get("next_action")) or "UNKNOWN",
                "order": int(row.get("index", index)),
            }
        )
    mechanisms: list[dict[str, Any]] = []
    for row in _pipeline_suborgans(chain):
        ident = str(row.get("id") or "mechanism")
        summary = dict(row.get("summary") or {}) if isinstance(row.get("summary"), Mapping) else {}
        mechanism_state = "COMPLETE" if summary.get("present") else "UNKNOWN"
        mechanisms.append(
            {
                "id": ident,
                "semantic_anchor": f"work:pipeline:mechanism:{ident}",
                "label": _words(row.get("label")) or ident.replace("-", " ").title(),
                "state": mechanism_state,
                "reason": "banked summary is present" if mechanism_state == "COMPLETE" else "mechanism evidence has not been joined",
                "summary": summary,
                "continuation": str(row.get("reader_door") or ""),
            }
        )
    controls = _pipeline_controls(chain)
    brief_value = dict(brief) if isinstance(brief, Mapping) else {}
    verdict_value = dict(verdict) if isinstance(verdict, Mapping) else {}
    return {
        "schema_version": "laplace.aisthesis-manuscript-pipeline/1",
        "semantic_anchor": "work:pipeline",
        "state": state,
        "reason": reason,
        "project": project,
        "position": str(
            brief_value.get("position") or verdict_value.get("position")
            or (chain or {}).get("current_state") or "UNKNOWN"
        ),
        "brief": brief_value,
        "verdict": verdict_value,
        "release_states": release_states,
        "mechanisms": mechanisms,
        "controls": controls,
        "launch": _launch_action_layer(controls, project=project, context=action_context),
        "continuation": f"/pipeline/chain?project={_q(project)}" if project else "/pipeline/chain",
        "read_only": True,
        "authority_effect": "none",
    }


def _walk_organ(
    document: Mapping[str, Any] | None,
    evidence: Mapping[str, Any] | None,
    *,
    corpus: str,
) -> dict[str, Any]:
    joined_state, joined_reason = _state(document)
    ev = evidence if isinstance(evidence, Mapping) else {}
    blocks = _blocks(document)
    addressed = [
        b
        for b in blocks
        if isinstance(b.get("src"), Mapping)
        and b["src"].get("file")
        and b["src"].get("line_start") is not None
        and b["src"].get("line_end") is not None
    ]
    missing_src = len(blocks) - len(addressed)
    provenance_state = joined_state
    provenance_reason = joined_reason
    if joined_state == "COMPLETE" and missing_src:
        provenance_state = "UNKNOWN"
        provenance_reason = f"{missing_src} rendered block(s) lack exact source spans"

    def ev_state(key: str) -> tuple[str, str]:
        return _state(ev.get(key) if key in ev else None)

    pdf_state, pdf_reason = ev_state("pdf")
    review_state, review_reason = ev_state("review")
    version_state, version_reason = ev_state("versions")
    compile_state, compile_reason = ev_state("compile")
    redline_state, redline_reason = ev_state("redline")
    feedback_state, feedback_reason = ev_state("feedback")

    corpus_q = _q(corpus)
    doc_route = "/walk/doc" + (f"?corpus={corpus_q}" if corpus else "")
    review_suffix = f"?corpus={corpus_q}" if corpus else ""
    document_counts = dict(document.get("counts") or {}) if isinstance(document, Mapping) else {}
    content_omissions: list[dict[str, Any]] = []
    if joined_state != "COMPLETE":
        content_omissions.append(
            _omission(
                "walk-document-not-joined",
                "The content-faithful document has not been joined",
                cause=joined_state,
                continuation=doc_route,
            )
        )
    if missing_src:
        content_omissions.append(
            _omission(
                "walk-source-spans-missing",
                "Rendered blocks without exact source spans",
                cause="UNRESOLVED",
                continuation=f"/review/provenance{review_suffix}",
                count=missing_src,
            )
        )

    capabilities = [
        _capability(
            "content-canvas",
            "Manuscript working canvas",
            family="walk",
            disposition="TRANSFORM",
            state=joined_state,
            reason=joined_reason,
            source=["src/laplace/manuscript/walk.py:doc", "src/laplace/manuscript/projection_viewer.py:doc_model"],
            reads=[_door("GET", doc_route, authority="walk.doc", evidence_state=joined_state)],
            evidence={
                "title": (document or {}).get("title", "") if isinstance(document, Mapping) else "",
                "fidelity": (document or {}).get("fidelity", "") if isinstance(document, Mapping) else "",
                "counts": document_counts,
            },
            omissions=content_omissions,
            continuation=doc_route,
            preserves=["words", "math", "figures", "document order", "root content"],
        ),
        _capability(
            "source-provenance",
            "Exact source and asset provenance",
            family="walk",
            disposition="KEEP",
            state=provenance_state,
            reason=provenance_reason,
            source=["src/laplace/manuscript/walk.py:blocks_for", "src/laplace/manuscript/walk.py:doc"],
            reads=[
                _door("GET", doc_route, authority="walk.doc", evidence_state=provenance_state),
                _door(
                    "GET",
                    "/walk/asset",
                    authority="walk.asset",
                    evidence_state=provenance_state,
                    note="fenced manuscript asset bytes; PDF figures remain unrasterised",
                ),
                _door(
                    "GET",
                    f"/review/provenance{review_suffix}",
                    authority="review_surface",
                    evidence_state=review_state,
                ),
            ],
            evidence={
                "blocks": len(blocks),
                "source_addressed": len(addressed),
                "missing_source_spans": missing_src,
            },
            omissions=content_omissions,
            continuation=f"/review/provenance{review_suffix}",
            preserves=["file", "line_start", "line_end", "paragraph provenance", "figure provenance"],
        ),
        _capability(
            "rewrite-and-scope",
            "Rewrite, block editing, parked edits and scope",
            family="walk",
            disposition="TRANSFORM",
            state=review_state,
            reason=review_reason,
            source=["src/laplace/manuscript/review_surface.py:adjudicate", "src/laplace/web/static_shared/walk.mjs"],
            reads=[
                _door("GET", f"/review/findings{review_suffix}", authority="review_surface", evidence_state=review_state),
                _door("GET", f"/review/his-hand{review_suffix}", authority="review_surface", evidence_state=review_state),
            ],
            acts=[
                _door(
                    "POST",
                    "/review/adjudicate",
                    authority="review_surface.adjudicate",
                    evidence_state=review_state,
                    effect="canonical review write",
                    note="comment, rewrite and scope verbs; exact source span splice; never invoked here",
                )
            ],
            evidence=dict(ev.get("review") or {}) if isinstance(ev.get("review"), Mapping) else {},
            omissions=[] if review_state == "COMPLETE" else [
                _omission(
                    "walk-review-evidence",
                    "Live parked edits, scope and author-hand evidence are not joined",
                    cause=review_state,
                    continuation=f"/review/findings{review_suffix}",
                )
            ],
            continuation=f"/review/findings{review_suffix}",
            preserves=[
                "rewrite-first composer",
                "exact safe TeX splice",
                "click-to-type blocks",
                "atomic rendered islands",
                "parked edits",
                "selective banking",
                "session-only deposit band",
                "scope and rescope",
            ],
        ),
        _capability(
            "feedback-and-findings",
            "Anchored findings and durable walk feedback",
            family="walk",
            disposition="TRANSFORM",
            state=feedback_state,
            reason=feedback_reason,
            source=["src/laplace/manuscript/review_surface.py", "src/laplace/manuscript/projection_viewer.py:handle"],
            reads=[
                _door("GET", f"/review/findings{review_suffix}", authority="review_surface", evidence_state=feedback_state),
                _door("GET", "/projection/feedback", authority="manuscript_bridge.feedback_list", evidence_state=feedback_state),
            ],
            acts=[
                _door("POST", "/review/adjudicate", authority="review_surface.adjudicate", evidence_state=feedback_state, effect="canonical review write"),
                _door("POST", "/projection/feedback", authority="manuscript_bridge.feedback_add", evidence_state=feedback_state, effect="canonical feedback write"),
                _door("POST", "/projection/feedback/resolve", authority="manuscript_bridge.feedback_resolve", evidence_state=feedback_state, effect="canonical feedback write"),
            ],
            evidence=dict(ev.get("feedback") or {}) if isinstance(ev.get("feedback"), Mapping) else {},
            omissions=[] if feedback_state == "COMPLETE" else [
                _omission(
                    "walk-feedback-routing",
                    "Durable Atlas routing and completion evidence for walk feedback are not joined",
                    cause="CURRENTNESS_OR_AUTHORITY",
                    continuation="/projection/feedback",
                )
            ],
            continuation="/projection/feedback",
            preserves=["anchored findings", "unanchored shelf", "visible resolution", "rebuild linkage"],
        ),
        _capability(
            "pdf-and-synctex",
            "Typeset geometry and reversible PDF–source descent",
            family="walk",
            disposition="KEEP",
            state=pdf_state,
            reason=pdf_reason,
            source=["src/laplace/manuscript/projection_viewer.py:pdf_info", "src/laplace/manuscript/projection_viewer.py:synctex_anchor", "src/laplace/manuscript/projection_viewer.py:synctex_locate"],
            reads=[
                _door("GET", "/projection/pdf", authority="projection_viewer", evidence_state=pdf_state),
                _door("GET", "/projection/pdfinfo", authority="projection_viewer.pdf_info", evidence_state=pdf_state),
                _door("GET", "/projection/synctex", authority="projection_viewer.synctex_anchor", evidence_state=pdf_state),
                _door("GET", "/projection/locate", authority="projection_viewer.synctex_locate", evidence_state=pdf_state),
                _door("GET", "/projection/follow", authority="projection_viewer.follow_status", evidence_state=pdf_state),
            ],
            evidence=dict(ev.get("pdf") or {}) if isinstance(ev.get("pdf"), Mapping) else {},
            omissions=[] if pdf_state == "COMPLETE" else [
                _omission("walk-pdf", "Compiled PDF/SyncTeX evidence is not joined", cause=pdf_state, continuation="/projection/pdfinfo")
            ],
            continuation="/projection/pdfinfo",
            preserves=["PDF geometry face", "PDF to source", "source to PDF", "continuous follow"],
        ),
        _capability(
            "version-compile-restore",
            "Save, compile, hot reload, version rail and restore",
            family="walk",
            disposition="KEEP",
            state=version_state if version_state != "COMPLETE" else compile_state,
            reason=version_reason if version_state != "COMPLETE" else compile_reason,
            source=["src/laplace/manuscript/projection_viewer.py:bank_editor_save", "src/laplace/manuscript/projection_viewer.py:restore_editor_save", "src/laplace/manuscript/review_surface.py:states"],
            reads=[
                _door("GET", f"/review/states{review_suffix}", authority="review_surface.states", evidence_state=version_state),
                _door("GET", "/projection/recompile", authority="projection_viewer.recompile_status", evidence_state=compile_state),
                _door("GET", "/projection/forks", authority="projection_viewer.forks", evidence_state=version_state),
            ],
            acts=[
                _door("POST", "/projection/tex?bank=editor", authority="projection_viewer", evidence_state=version_state, effect="canonical TeX save and version mint"),
                _door("POST", "/projection/compile", authority="projection_viewer.compile_tex", evidence_state=compile_state, effect="compile and stamp"),
                _door("POST", "/projection/recompile", authority="projection_viewer.recompile", evidence_state=compile_state, effect="debounced compile queue"),
                _door("POST", "/projection/restore", authority="projection_viewer.restore_editor_save", evidence_state=version_state, effect="restore as a new save"),
            ],
            evidence={
                "versions": dict(ev.get("versions") or {}) if isinstance(ev.get("versions"), Mapping) else {},
                "compile": dict(ev.get("compile") or {}) if isinstance(ev.get("compile"), Mapping) else {},
            },
            omissions=[] if version_state == compile_state == "COMPLETE" else [
                _omission("walk-version-compile", "Version/compile evidence is incomplete", cause="UNRESOLVED", continuation=f"/review/states{review_suffix}")
            ],
            continuation=f"/review/states{review_suffix}",
            preserves=["TeX save", "version mint", "compile", "hot reload", "diff", "restore without rewind"],
        ),
        _capability(
            "live-redline",
            "Live source and typeset redline",
            family="walk",
            disposition="KEEP",
            state=redline_state,
            reason=redline_reason,
            source=["src/laplace/manuscript/review_surface.py:states", "src/laplace/manuscript/review_surface.py:handle"],
            reads=[
                _door("GET", f"/review/compare{review_suffix}", authority="review_surface", evidence_state=redline_state),
                _door("GET", f"/review/states{review_suffix}", authority="review_surface.states", evidence_state=redline_state),
            ],
            evidence=dict(ev.get("redline") or {}) if isinstance(ev.get("redline"), Mapping) else {},
            omissions=[] if redline_state == "COMPLETE" else [
                _omission("walk-redline", "Banked before/after evidence is not joined", cause=redline_state, continuation=f"/review/compare{review_suffix}")
            ],
            continuation=f"/review/compare{review_suffix}",
            preserves=["source diff", "version selection", "live redline"],
        ),
        _capability(
            "legacy-page-shell",
            "Historical Walk page shell",
            family="walk",
            disposition="RETIRE",
            state="COMPLETE",
            reason="the producers remain; the standalone page composition does not enter the new carrier",
            source=["src/laplace/web/walk.html", "src/laplace/web/static_shared/walk.mjs"],
            evidence={"historical_route": "/walk", "replacement": "contextual Work room"},
            preserves=["no copied shell", "one carrier", "same canonical producers"],
        ),
    ]
    organ = {
        "schema_version": ORGAN_SCHEMA,
        "id": "walk",
        "semantic_anchor": "work:organ:walk",
        "label": "Manuscript walk",
        "state": joined_state,
        "reason": joined_reason,
        "source": ["src/laplace/manuscript/walk.py", "src/laplace/manuscript/review_surface.py", "src/laplace/manuscript/projection_viewer.py"],
        "capabilities": capabilities,
        "read_only_projection": True,
    }
    organ["organ_handle"] = _handle("work-organ", organ)
    return organ


def _pipeline_suborgans(chain: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    if not isinstance(chain, Mapping):
        return out
    for organ in chain.get("organs") or []:
        if not isinstance(organ, Mapping):
            continue
        out.extend(s for s in organ.get("sub_organs") or [] if isinstance(s, Mapping))
    return out


def _pipeline_controls(chain: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(chain, Mapping):
        return rows
    owners = list(chain.get("organs") or []) + [chain.get("global") or {}]
    for owner in owners:
        if not isinstance(owner, Mapping):
            continue
        for control in owner.get("controls") or []:
            if not isinstance(control, Mapping):
                continue
            row = dict(control)
            row["owner"] = str(owner.get("id") or "global")
            row["projection_executes"] = False
            rows.append(row)
    return rows


def _pipeline_organ(
    chain: Mapping[str, Any] | None,
    brief: Mapping[str, Any] | None,
    verdict: Mapping[str, Any] | None,
    organs: Mapping[str, Any] | None,
    *,
    project: str,
) -> dict[str, Any]:
    chain_state, chain_reason = _state(chain)
    brief_state, brief_reason = _state(brief)
    verdict_state, verdict_reason = _state(verdict)
    project_q = _q(project)
    suffix = f"?project={project_q}" if project else ""
    suborgans = _pipeline_suborgans(chain)
    sub_by_id = {str(s.get("id")): s for s in suborgans if s.get("id")}
    joined_organs = organs if isinstance(organs, Mapping) else {}
    controls = _pipeline_controls(chain)
    dials = []
    if isinstance(chain, Mapping):
        for organ in list(chain.get("organs") or []) + [chain.get("global") or {}]:
            if isinstance(organ, Mapping):
                dials.extend(d for d in organ.get("dials") or [] if isinstance(d, Mapping))

    def organ_state(ident: str) -> tuple[str, str]:
        if ident in joined_organs:
            return _state(joined_organs.get(ident))
        summary = sub_by_id.get(ident, {}).get("summary")
        if isinstance(summary, Mapping) and summary.get("present"):
            return "COMPLETE", "the bounded chain summary names banked organ evidence"
        if ident in sub_by_id:
            return "UNKNOWN", "the organ exists, but its banked evidence is absent or not lazy-joined"
        return "UNKNOWN", "the current chain does not expose this organ"

    chain_route = f"/pipeline/chain{suffix}"
    brief_route = f"/pipeline/brief{suffix}"
    verdict_route = f"/pipeline/verdict{suffix}"
    organ_route = f"/pipeline/organ{suffix + '&' if suffix else '?'}organ="
    controls_by_cost = {
        "local-safe": sum(1 for c in controls if c.get("cost_class") == "local-safe"),
        "model-heavy": sum(1 for c in controls if c.get("cost_class") == "model-heavy"),
        "other": sum(1 for c in controls if c.get("cost_class") not in {"local-safe", "model-heavy"}),
    }
    unknown_suborgans = [
        str(s.get("id"))
        for s in suborgans
        if organ_state(str(s.get("id")))[0] != "COMPLETE"
    ]
    lazy_state = chain_state
    lazy_reason = chain_reason
    if chain_state == "COMPLETE" and unknown_suborgans:
        lazy_state = "UNKNOWN"
        lazy_reason = (
            "the organ roster is joined, but full evidence remains absent for "
            + ", ".join(unknown_suborgans)
        )

    capabilities = [
        _capability(
            "composed-brief",
            "Composed project brief",
            family="pipeline",
            disposition="KEEP",
            state=brief_state,
            reason=brief_reason,
            source=["src/laplace/web/pipeline_surface.py:pipeline_brief"],
            reads=[_door("GET", brief_route, authority="pipeline_surface.pipeline_brief", evidence_state=brief_state)],
            evidence=dict(brief or {}) if isinstance(brief, Mapping) else {},
            omissions=[] if brief_state == "COMPLETE" else [
                _omission("pipeline-brief", "The composed brief is not joined", cause=brief_state, continuation=brief_route)
            ],
            continuation=brief_route,
            preserves=["goal", "release state", "last run", "next action", "cost", "at most one decision"],
        ),
        _capability(
            "release-chain",
            "Release chain and next action",
            family="pipeline",
            disposition="TRANSFORM",
            state=chain_state,
            reason=chain_reason,
            source=["src/laplace/web/pipeline_surface.py:chain", "src/laplace/pipeline/release.py:STATES"],
            reads=[_door("GET", chain_route, authority="pipeline_surface.chain", evidence_state=chain_state)],
            evidence={
                "project": (chain or {}).get("project", project) if isinstance(chain, Mapping) else project,
                "current_state": (chain or {}).get("current_state") if isinstance(chain, Mapping) else None,
                "never_run": bool((chain or {}).get("never_run")) if isinstance(chain, Mapping) else None,
                "states": list((chain or {}).get("states") or []) if isinstance(chain, Mapping) else [],
                "ladder_banner": (chain or {}).get("ladder_banner", "") if isinstance(chain, Mapping) else "",
            },
            omissions=[] if chain_state == "COMPLETE" else [
                _omission("pipeline-chain", "The release state machine is not joined", cause=chain_state, continuation=chain_route)
            ],
            continuation=chain_route,
            preserves=["release.STATES", "passed/current/ahead", "per-rung next action", "view equals mechanism"],
        ),
        _capability(
            "typed-verdict",
            "Release and fitness verdict",
            family="pipeline",
            disposition="KEEP",
            state=verdict_state,
            reason=verdict_reason,
            source=["src/laplace/pipeline/project_state.py:project_verdict"],
            reads=[_door("GET", verdict_route, authority="project_state.project_verdict", evidence_state=verdict_state)],
            evidence=dict(verdict or {}) if isinstance(verdict, Mapping) else {},
            omissions=[] if verdict_state == "COMPLETE" else [
                _omission("pipeline-verdict", "The typed verdict is not joined", cause=verdict_state, continuation=verdict_route)
            ],
            continuation=verdict_route,
            preserves=["position", "debt trajectory", "owed-to-author", "named red", "staleness"],
        ),
        _capability(
            "lazy-organs",
            "Lazy mechanism-owned organs",
                family="pipeline",
                disposition="TRANSFORM",
                state=lazy_state,
                reason=lazy_reason,
                source=["src/laplace/web/pipeline_surface.py:read_organ"],
                reads=[
                    _door("GET", organ_route + "<organ>", authority="pipeline_surface.read_organ", evidence_state=lazy_state)
                ],
            evidence={
                "organs": [
                    {
                        "id": s.get("id"),
                        "label": s.get("label"),
                        "producer": s.get("producer"),
                        "reader_door": s.get("reader_door"),
                        "summary": dict(s.get("summary") or {}),
                        "state": organ_state(str(s.get("id")))[0],
                    }
                    for s in suborgans
                ]
            },
            omissions=[
                _omission(
                    f"pipeline-organ-{s.get('id')}",
                    f"{s.get('label') or s.get('id')} detail is not joined",
                    cause=organ_state(str(s.get("id")))[0],
                    continuation=str(s.get("reader_door") or (organ_route + str(s.get("id")))),
                )
                for s in suborgans
                if organ_state(str(s.get("id")))[0] != "COMPLETE"
            ],
            continuation=organ_route + "<organ>",
            preserves=["bibliography", "citation direction", "figures", "detectors", "selection", "derivation", "evolution", "fitness", "growth", "structural conformance"],
        ),
        _capability(
            "dials-in-place",
            "Mechanism dials in their consuming organs",
            family="pipeline",
            disposition="KEEP",
            state=chain_state,
            reason=chain_reason,
            source=["src/laplace/web/pipeline_surface.py:_DIAL_GROUP_ORGAN", "src/laplace/web/dials_surface.py"],
            reads=[_door("GET", "/dials/state", authority="dials_surface", evidence_state=chain_state)],
            acts=[
                _door("POST", "/dials/op", authority="dials_surface", evidence_state=chain_state, effect="canonical profile edit"),
                _door("POST", "/dials/undo", authority="dials_surface", evidence_state=chain_state, effect="canonical profile undo"),
            ],
            evidence={"dials": dials, "count": len(dials)},
            omissions=[] if chain_state == "COMPLETE" else [
                _omission("pipeline-dials", "Live profile and dial provenance are not joined", cause=chain_state, continuation="/dials/state")
            ],
            continuation="/dials/state",
            preserves=["group-to-organ ownership", "worded meaning", "effect", "default", "overlay provenance", "structural store gates"],
        ),
    ]

    governed = (
        (
            "selection",
            "Selection sheet and author ruling",
            ["POST /selection/rule"],
            ["generation score", "draft verdict", "awaiting ruling", "promote/hold/retire"],
        ),
        (
            "derivation",
            "Aspiration and attested derivation chain",
            ["POST /derivation/rescope", "POST /derivation/forge", "POST /derivation/contest"],
            ["aspiration", "attested links", "depth", "frontier gap", "contest"],
        ),
        (
            "evolution",
            "Evolution queue",
            ["POST /evolution/ratify", "POST /evolution/hold", "POST /evolution/reject"],
            ["open", "held", "applied", "rejected", "transactional ratification"],
        ),
    )
    for ident, label, routes, preserves in governed:
        state, reason = organ_state(ident)
        summary = sub_by_id.get(ident, {}).get("summary")
        joined = joined_organs.get(ident)
        evidence = dict(joined) if isinstance(joined, Mapping) else dict(summary or {})
        capabilities.append(
            _capability(
                ident,
                label,
                family="pipeline",
                disposition="KEEP",
                state=state,
                reason=reason,
                source=[f"src/laplace/web/pipeline_surface.py:read_organ({ident})"],
                reads=[_door("GET", organ_route + ident, authority="pipeline_surface.read_organ", evidence_state=state)],
                acts=[
                    _door(method, route, authority=route, evidence_state=state, effect="canonical governed write")
                    for method, route in (r.split(" ", 1) for r in routes)
                ],
                evidence=evidence,
                omissions=[] if state == "COMPLETE" else [
                    _omission(f"pipeline-{ident}", f"{label} evidence is absent or not joined", cause=state, continuation=organ_route + ident)
                ],
                continuation=organ_route + ident,
                preserves=preserves,
            )
        )

    joins = dict((chain or {}).get("joins") or {}) if isinstance(chain, Mapping) else {}
    dry_run = joins.get("dry_run")
    run_tray = joins.get("run_tray")
    run_state = "COMPLETE" if controls and run_tray else "UNKNOWN"
    run_reason = (
        "scoped controls and the current run tray are joined"
        if controls and run_tray
        else "the launch roster or current run tray is not joined"
    )
    capabilities.extend(
        [
            _capability(
                "run-controls",
                "Scoped arm, fire and run recovery",
                family="pipeline",
                disposition="KEEP",
                state=run_state,
                reason=run_reason,
                source=["src/laplace/manuscript/storyboard.py:launch_roster", "src/laplace/web/pipeline_surface.py:_control_for_action"],
                reads=[
                    _door("GET", "/storyboard/run", authority="storyboard.run_panel", evidence_state=run_state),
                    _door("GET", "/storyboard/propagate", authority="storyboard.propagate", evidence_state="COMPLETE" if dry_run else "UNKNOWN", note="general worklist preview; not a universal execution dry-run"),
                ],
                acts=[
                    _door("POST", "/storyboard/run/launch", authority="storyboard", evidence_state=run_state, effect="scoped launch", cost_class=str(c.get("cost_class") or "UNKNOWN"), note=f"{c.get('action')}: {c.get('what') or ''}")
                    for c in controls
                ],
                evidence={"controls": controls, "counts_by_cost": controls_by_cost, "dry_run": dry_run},
                omissions=([] if controls and run_tray else [
                    _omission("pipeline-run-controls", "Run roster or current run is not joined", cause="UNKNOWN", continuation="/storyboard/run")
                ]) + ([] if dry_run else [
                    _omission("pipeline-general-dry-run", "No universal dry-run receipt exists; propagate is a worklist preview", cause="UNRESOLVED", continuation="/storyboard/propagate")
                ]),
                continuation="/storyboard/run",
                preserves=["scoped arm/fire", "run-scoped dial flip and recovery", "local-safe versus model-heavy", "work-order banking", "cost/PSU", "honest preview boundary"],
            ),
            _capability(
                "legacy-page-shell",
                "Historical Pipeline page shell",
                family="pipeline",
                disposition="RETIRE",
                state="COMPLETE",
                reason="the release and organ producers remain; the standalone board composition does not enter the new carrier",
                source=["src/laplace/web/pipeline.html", "src/laplace/web/static_shared/pipeline-panes.mjs"],
                evidence={"historical_route": "/pipeline", "replacement": "contextual Work room"},
                preserves=["no copied shell", "one carrier", "same release machine and organ readers"],
            ),
        ]
    )
    organ = {
        "schema_version": ORGAN_SCHEMA,
        "id": "pipeline",
        "semantic_anchor": "work:organ:pipeline",
        "label": "Build and release pipeline",
        "state": chain_state,
        "reason": chain_reason,
        "source": ["src/laplace/web/pipeline_surface.py", "contract/surfaces/pipeline.yaml"],
        "capabilities": capabilities,
        "read_only_projection": True,
    }
    organ["organ_handle"] = _handle("work-organ", organ)
    return organ


def project(
    *,
    project_name: str = "",
    corpus: str = "",
    walk_document: Mapping[str, Any] | None = None,
    walk_evidence: Mapping[str, Any] | None = None,
    pipeline_chain: Mapping[str, Any] | None = None,
    pipeline_brief: Mapping[str, Any] | None = None,
    pipeline_verdict: Mapping[str, Any] | None = None,
    pipeline_organs: Mapping[str, Any] | None = None,
    observation_time: str = "",
    source_currentness: Mapping[str, Any] | None = None,
    action_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the immutable Work-room projection from already-joined producer values."""
    walk = _walk_organ(walk_document, walk_evidence, corpus=corpus or project_name)
    pipeline = _pipeline_organ(
        pipeline_chain,
        pipeline_brief,
        pipeline_verdict,
        pipeline_organs,
        project=project_name or corpus,
    )
    manuscript_surface = _manuscript_surface(
        walk_document,
        walk_evidence,
        corpus=corpus or project_name,
        action_context=action_context,
    )
    pipeline_surface = _pipeline_surface(
        pipeline_chain,
        pipeline_brief,
        pipeline_verdict,
        project=project_name or corpus,
        action_context=action_context,
    )
    organs = [walk, pipeline]
    # The carrier may paint a structurally complete model while individual historical
    # mechanisms remain unjoined.  Its headline must not turn those honest gaps into a
    # green room merely because the Walk document and release chain themselves loaded.
    states = [
        capability["state"]
        for organ in organs
        for capability in organ["capabilities"]
        if capability["disposition"] != "RETIRE"
    ]
    room_state = "REFUSED" if "REFUSED" in states else "UNKNOWN" if "UNKNOWN" in states else "COMPLETE"
    anchors = [
        cap["semantic_anchor"]
        for organ in organs
        for cap in organ["capabilities"]
    ]
    if len(anchors) != len(set(anchors)):
        raise ValueError("duplicate semantic anchor in Work-room projection")
    omitted = [
        omission
        for organ in organs
        for cap in organ["capabilities"]
        for omission in cap.get("omissions") or []
    ]
    body: dict[str, Any] = {
        "schema_version": SCHEMA,
        "room": "work",
        "semantic_anchor": "front:room:work",
        "label": "Work",
        "state": room_state,
        "project": project_name,
        "corpus": corpus,
        "observation_time": observation_time,
        "source_currentness": dict(source_currentness or {}),
        "organs": organs,
        "workbench": {
            "schema_version": "laplace.aisthesis-manuscript-workbench/1",
            "semantic_anchor": "work:manuscript-workbench",
            "manuscript": manuscript_surface,
            "pipeline": pipeline_surface,
            "read_only": True,
            "authority_effect": "none",
        },
        "ordered_visible_handles": [o["organ_handle"] for o in organs],
        "omissions": omitted,
        "omitted_digest": _handle("work-omissions", omitted),
        "parity": {
            "statuses": ["KEEP", "TRANSFORM", "SUBMERGE", "RETIRE"],
            "source_bearing": True,
            "old_shells_embedded": False,
            "second_truth_store": False,
        },
        "read_only": True,
        "authority_effect": "none",
    }
    body["model_handle"] = _handle("work-model", body)
    return body


def _capture(call: Callable[[], Any]) -> Mapping[str, Any]:
    try:
        value = call()
    except Exception as exc:  # producer refusal must remain visible, not break the carrier
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if value is None:
        return {"ok": False, "error": "producer returned no value"}
    if not isinstance(value, Mapping):
        return {"ok": False, "error": "producer returned a malformed non-object value"}
    return value


def read(
    *,
    project_name: str,
    corpus: str = "",
    repo_root: Path | None = None,
    observation_time: str = "",
    source_currentness: Mapping[str, Any] | None = None,
    walk_evidence: Mapping[str, Any] | None = None,
    action_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Join the existing pure producers, then call :func:`project`.

    This is deliberately bounded: heavy organ bodies stay behind their existing lazy
    ``/pipeline/organ`` continuations.  No canonical write door is called.
    """
    from laplace.web import pipeline_surface
    from laplace.manuscript import walk
    from laplace.pipeline import project_state

    root = (repo_root or Path.cwd()).resolve()
    name = project_name or corpus
    walk_document = _capture(lambda: walk.doc(corpus or name))
    pipeline_chain = _capture(lambda: pipeline_surface.chain(name, repo_root=root))
    pipeline_brief = _capture(lambda: pipeline_surface.pipeline_brief(name, repo_root=root))
    pipeline_verdict = _capture(lambda: project_state.project_verdict(root, name))
    return project(
        project_name=name,
        corpus=corpus or name,
        walk_document=walk_document,
        walk_evidence=walk_evidence,
        pipeline_chain=pipeline_chain,
        pipeline_brief=pipeline_brief,
        pipeline_verdict=pipeline_verdict,
        observation_time=observation_time,
        source_currentness=source_currentness,
        action_context=action_context,
    )


__all__ = [
    "ACTION_LAYER_SCHEMA",
    "CAPABILITY_SCHEMA",
    "LAUNCH_ACTION_SCHEMA",
    "ORGAN_SCHEMA",
    "SCHEMA",
    "project",
    "read",
]
