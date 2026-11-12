"""Canonical command and read projection for object-relative Front feedback.

This module deliberately owns no persistence.  The historical Walk feedback door is
manuscript-local and one of its lifecycle operations rewrites old rows; using it for
carrier-wide comments would turn a useful predecessor into a second, lossy truth store.
Atlas does not yet expose a typed semantic-annotation event.  Consequently the only
write entry here requires an injected canonical adapter and refuses when none exists.

The pure seam is nevertheless complete: it validates semantic anchors, mints immutable
append events, folds their lifecycle, derives non-authoritative routing, and rehydrates
markers across lenses.  Tests use an in-memory adapter as a safe specimen only.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

ANCHOR_SCHEMA = "laplace.front-semantic-anchor/1"
COMMAND_SCHEMA = "laplace.front-feedback-command/1"
EVENT_SCHEMA = "laplace.front-feedback-event/1"
PROJECTION_SCHEMA = "laplace.front-feedback-projection/1"
ADAPTER_SCHEMA = "laplace.front-feedback-adapter/1"

ANNOTATION_STATES = frozenset({"OPEN", "RESOLVED", "SUPERSEDED", "WITHDRAWN"})
ANCHOR_KINDS = frozenset({"object", "edge", "omission", "residual"})
ACTIONS = frozenset({"CREATE", "TRANSITION", "RECONCILE"})
GRADES = frozenset({"far", "mid", "near", "audit", "summary", "picture", "detail"})
EXPOSITIONS = frozenset({f"E{grade}" for grade in range(8)})
VIEWPORTS = frozenset({"wide", "medium", "narrow"})
CURRENTNESS_STATES = frozenset(
    {"CURRENT", "LAST-TRUSTED", "STALE", "IN_FLIGHT", "UNKNOWN", "REFUSED", "ABSENT"}
)
_FORBIDDEN_LOCATION_KEYS = frozenset({"dom_path", "xpath", "css_selector", "selector"})


class FeedbackRefused(ValueError):
    """A malformed or causally invalid feedback command/event."""


class CanonicalFeedbackAdapter(Protocol):
    """The required durable boundary.

    A real implementation must append to the one canonical history and return its
    receipt.  This protocol intentionally does not prescribe an Atlas event before the
    producer owns one.
    """

    schema_version: str

    def read_events(self) -> Sequence[Mapping[str, Any]]: ...

    def append_event(self, event: Mapping[str, Any]) -> Mapping[str, Any]: ...


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def canonical_handle(value: Any, *, kind: str = "front-feedback") -> str:
    return f"{kind}:sha256:{hashlib.sha256(canonical_bytes(value)).hexdigest()}"


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise FeedbackRefused(f"{field} is required")
    return result


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FeedbackRefused(f"{field} must be an object")
    return dict(value)


def _reject_dom_paths(value: Any, *, path: str = "anchor") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() in _FORBIDDEN_LOCATION_KEYS:
                raise FeedbackRefused(
                    f"{path}.{key} is a DOM-location key; feedback requires semantic identity"
                )
            _reject_dom_paths(child, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_dom_paths(child, path=f"{path}[{index}]")


def _geometry(value: Any) -> dict[str, float] | None:
    if value is None:
        return None
    raw = _mapping(value, "selection_geometry")
    expected = ("x", "y", "width", "height")
    if set(raw) != set(expected):
        raise FeedbackRefused("selection_geometry requires exactly x, y, width and height")
    out: dict[str, float] = {}
    for key in expected:
        number = raw[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)):
            raise FeedbackRefused(f"selection_geometry.{key} must be numeric")
        number = float(number)
        if not math.isfinite(number):
            raise FeedbackRefused(f"selection_geometry.{key} must be finite")
        if key in {"width", "height"} and number < 0:
            raise FeedbackRefused(f"selection_geometry.{key} cannot be negative")
        out[key] = number
    return out


def _screenshot(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    raw = _mapping(value, "screenshot")
    content_handle = _text(raw.get("content_handle"), "screenshot.content_handle")
    media_type = _text(raw.get("media_type"), "screenshot.media_type")
    if not media_type.startswith("image/"):
        raise FeedbackRefused("screenshot.media_type must be an image type")
    return {"content_handle": content_handle, "media_type": media_type}


def normalize_anchor(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one semantic anchor and return its exact canonical shape."""

    raw = _mapping(value, "anchor")
    _reject_dom_paths(raw)
    kind = _text(raw.get("kind"), "anchor.kind").casefold()
    if kind not in ANCHOR_KINDS:
        raise FeedbackRefused(f"anchor.kind must be one of {sorted(ANCHOR_KINDS)}")
    selection = _mapping(raw.get("selection"), "anchor.selection")
    expected_selection = ("lens", "focus", "edge", "grade", "exposition", "viewport")
    missing = [key for key in expected_selection if key not in selection]
    if missing:
        raise FeedbackRefused(f"anchor.selection is missing {missing}")
    lens = _text(selection.get("lens"), "anchor.selection.lens")
    grade = _text(selection.get("grade"), "anchor.selection.grade")
    exposition = _text(selection.get("exposition"), "anchor.selection.exposition")
    viewport = _text(selection.get("viewport"), "anchor.selection.viewport")
    if grade not in GRADES:
        raise FeedbackRefused(f"anchor.selection.grade must be one of {sorted(GRADES)}")
    if exposition not in EXPOSITIONS:
        raise FeedbackRefused("anchor.selection.exposition must be E0 through E7")
    if viewport not in VIEWPORTS:
        raise FeedbackRefused(f"anchor.selection.viewport must be one of {sorted(VIEWPORTS)}")
    currentness = _mapping(raw.get("currentness"), "anchor.currentness")
    currentness_status = _text(
        currentness.get("status") or currentness.get("state"), "anchor.currentness.status"
    ).upper()
    if currentness_status not in CURRENTNESS_STATES:
        raise FeedbackRefused(
            f"anchor.currentness.status must be one of {sorted(CURRENTNESS_STATES)}"
        )
    source = _mapping(raw.get("source"), "anchor.source")
    if not source:
        raise FeedbackRefused("anchor.source must name at least one source/currentness root")
    route = raw.get("route")
    if route is not None:
        route = _mapping(route, "anchor.route")
        if route.get("authority") is True or route.get("authority_effect") not in (None, "none"):
            raise FeedbackRefused("anchor.route cannot grant authority")
    normalized = {
        "schema_version": ANCHOR_SCHEMA,
        "semantic_anchor": _text(raw.get("semantic_anchor"), "anchor.semantic_anchor"),
        "kind": kind,
        "label": _text(raw.get("label"), "anchor.label"),
        "model_handle": _text(raw.get("model_handle"), "anchor.model_handle"),
        "shown_handle": _text(raw.get("shown_handle"), "anchor.shown_handle"),
        "selection": {
            "lens": lens,
            "focus": None if selection.get("focus") in (None, "") else str(selection["focus"]),
            "edge": None if selection.get("edge") in (None, "") else str(selection["edge"]),
            "grade": grade,
            "exposition": exposition,
            "viewport": viewport,
        },
        "source": source,
        "currentness": {**currentness, "status": currentness_status},
        "selection_geometry": _geometry(raw.get("selection_geometry")),
        "screenshot": _screenshot(raw.get("screenshot")),
        "route": route,
    }
    normalized["anchor_handle"] = canonical_handle(normalized, kind="front-anchor")
    return normalized


def create_command(
    *, command_id: str, actor: str, text: str, anchor: Mapping[str, Any]
) -> dict[str, Any]:
    preimage = {
        "schema_version": COMMAND_SCHEMA,
        "action": "CREATE",
        "command_id": _text(command_id, "command_id"),
        "actor": _text(actor, "actor"),
        "text": _text(text, "text"),
        "anchor": normalize_anchor(anchor),
        "annotation_id": None,
        "state": None,
        "replacement_annotation_id": None,
    }
    preimage["command_handle"] = canonical_handle(preimage, kind="front-feedback-command")
    return preimage


def transition_command(
    *, command_id: str, actor: str, annotation_id: str, state: str,
    replacement_annotation_id: str | None = None,
) -> dict[str, Any]:
    normalized_state = _text(state, "state").upper()
    if normalized_state not in ANNOTATION_STATES - {"OPEN"}:
        raise FeedbackRefused("transition state must be RESOLVED, SUPERSEDED or WITHDRAWN")
    replacement = (
        _text(replacement_annotation_id, "replacement_annotation_id")
        if replacement_annotation_id not in (None, "") else None
    )
    if normalized_state == "SUPERSEDED" and replacement is None:
        raise FeedbackRefused("SUPERSEDED requires replacement_annotation_id")
    if normalized_state != "SUPERSEDED" and replacement is not None:
        raise FeedbackRefused("replacement_annotation_id is only valid for SUPERSEDED")
    preimage = {
        "schema_version": COMMAND_SCHEMA,
        "action": "TRANSITION",
        "command_id": _text(command_id, "command_id"),
        "actor": _text(actor, "actor"),
        "text": None,
        "anchor": None,
        "annotation_id": _text(annotation_id, "annotation_id"),
        "state": normalized_state,
        "replacement_annotation_id": replacement,
    }
    preimage["command_handle"] = canonical_handle(preimage, kind="front-feedback-command")
    return preimage


def reconcile_command(
    *, command_id: str, actor: str, annotation_id: str, anchor: Mapping[str, Any]
) -> dict[str, Any]:
    preimage = {
        "schema_version": COMMAND_SCHEMA,
        "action": "RECONCILE",
        "command_id": _text(command_id, "command_id"),
        "actor": _text(actor, "actor"),
        "text": None,
        "anchor": normalize_anchor(anchor),
        "annotation_id": _text(annotation_id, "annotation_id"),
        "state": None,
        "replacement_annotation_id": None,
    }
    preimage["command_handle"] = canonical_handle(preimage, kind="front-feedback-command")
    return preimage


def validate_command(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(value, "command")
    if raw.get("schema_version") != COMMAND_SCHEMA:
        raise FeedbackRefused("feedback command schema is unknown")
    action = _text(raw.get("action"), "command.action").upper()
    if action not in ACTIONS:
        raise FeedbackRefused(f"command.action must be one of {sorted(ACTIONS)}")
    if action == "CREATE":
        normalized = create_command(
            command_id=raw.get("command_id", ""), actor=raw.get("actor", ""),
            text=raw.get("text", ""), anchor=_mapping(raw.get("anchor"), "command.anchor"),
        )
    elif action == "TRANSITION":
        normalized = transition_command(
            command_id=raw.get("command_id", ""), actor=raw.get("actor", ""),
            annotation_id=raw.get("annotation_id", ""), state=raw.get("state", ""),
            replacement_annotation_id=raw.get("replacement_annotation_id"),
        )
    else:
        normalized = reconcile_command(
            command_id=raw.get("command_id", ""), actor=raw.get("actor", ""),
            annotation_id=raw.get("annotation_id", ""),
            anchor=_mapping(raw.get("anchor"), "command.anchor"),
        )
    supplied = raw.get("command_handle")
    if supplied not in (None, normalized["command_handle"]):
        raise FeedbackRefused("feedback command handle does not match its preimage")
    return normalized


def _event_for(command: Mapping[str, Any], *, occurred_at: str) -> dict[str, Any]:
    action = command["action"]
    annotation_id = command.get("annotation_id")
    if action == "CREATE":
        annotation_id = canonical_handle(
            {
                "command_id": command["command_id"],
                "actor": command["actor"],
                "text": command["text"],
                "anchor_handle": command["anchor"]["anchor_handle"],
            },
            kind="front-annotation",
        )
    payload = {
        "text": command.get("text"),
        "anchor": command.get("anchor"),
        "state": command.get("state"),
        "replacement_annotation_id": command.get("replacement_annotation_id"),
    }
    preimage = {
        "schema_version": EVENT_SCHEMA,
        "event_id": None,
        "event_type": {
            "CREATE": "annotation.created",
            "TRANSITION": "annotation.transitioned",
            "RECONCILE": "annotation.reconciled",
        }[action],
        "command_id": command["command_id"],
        "command_handle": command["command_handle"],
        "annotation_id": annotation_id,
        "actor": command["actor"],
        "occurred_at": _text(occurred_at, "occurred_at"),
        "payload": payload,
    }
    event_id = canonical_handle(preimage, kind="front-feedback-event-id")
    preimage["event_id"] = event_id
    preimage["event_handle"] = canonical_handle(preimage, kind="front-feedback-event")
    return preimage


def _normalize_event(value: Mapping[str, Any]) -> dict[str, Any]:
    raw = _mapping(value, "event")
    if raw.get("schema_version") != EVENT_SCHEMA:
        raise FeedbackRefused("feedback event schema is unknown")
    event_type = _text(raw.get("event_type"), "event.event_type")
    if event_type not in {
        "annotation.created", "annotation.transitioned", "annotation.reconciled"
    }:
        raise FeedbackRefused("feedback event type is unknown")
    payload = _mapping(raw.get("payload"), "event.payload")
    normalized = {
        "schema_version": EVENT_SCHEMA,
        "event_id": _text(raw.get("event_id"), "event.event_id"),
        "event_type": event_type,
        "command_id": _text(raw.get("command_id"), "event.command_id"),
        "command_handle": _text(raw.get("command_handle"), "event.command_handle"),
        "annotation_id": _text(raw.get("annotation_id"), "event.annotation_id"),
        "actor": _text(raw.get("actor"), "event.actor"),
        "occurred_at": _text(raw.get("occurred_at"), "event.occurred_at"),
        "payload": {
            "text": payload.get("text"),
            "anchor": normalize_anchor(payload["anchor"]) if payload.get("anchor") else None,
            "state": payload.get("state"),
            "replacement_annotation_id": payload.get("replacement_annotation_id"),
        },
    }
    if event_type == "annotation.created":
        _text(normalized["payload"]["text"], "event.payload.text")
        if normalized["payload"]["anchor"] is None:
            raise FeedbackRefused("created annotation requires an anchor")
    elif event_type == "annotation.transitioned":
        state = _text(normalized["payload"]["state"], "event.payload.state").upper()
        if state not in ANNOTATION_STATES - {"OPEN"}:
            raise FeedbackRefused("transitioned annotation carries an invalid state")
        normalized["payload"]["state"] = state
        replacement = normalized["payload"]["replacement_annotation_id"]
        if state == "SUPERSEDED" and not replacement:
            raise FeedbackRefused("superseded event omits its replacement")
    elif normalized["payload"]["anchor"] is None:
        raise FeedbackRefused("reconciled annotation requires an anchor")
    event_id_preimage = {**normalized, "event_id": None}
    expected_event_id = canonical_handle(event_id_preimage, kind="front-feedback-event-id")
    if normalized["event_id"] != expected_event_id:
        raise FeedbackRefused("feedback event id does not match its preimage")
    supplied = _text(raw.get("event_handle"), "event.event_handle")
    expected = canonical_handle(normalized, kind="front-feedback-event")
    if supplied != expected:
        raise FeedbackRefused("feedback event handle does not match its preimage")
    normalized["event_handle"] = expected
    return normalized


def _derive_routing(anchor: Mapping[str, Any]) -> dict[str, Any]:
    route = anchor.get("route") if isinstance(anchor, Mapping) else None
    if not isinstance(route, Mapping) or not route:
        return {
            "state": "UNKNOWN",
            "reason": "the semantic anchor exposes no canonical routing hint",
            "route": None,
            "basis": anchor.get("semantic_anchor"),
            "authority_granted": False,
            "authority_effect": "none",
        }
    return {
        "state": "DERIVED",
        "reason": "visibility is derived from the anchor's source-owned route hint",
        "route": dict(route),
        "basis": anchor.get("semantic_anchor"),
        "authority_granted": False,
        "authority_effect": "none",
    }


def _anchor_face(
    anchor: Mapping[str, Any], *, catalog: Sequence[Mapping[str, Any]] | None,
    catalog_complete: bool, visible_anchor_ids: set[str] | None,
) -> dict[str, Any]:
    semantic_anchor = anchor["semantic_anchor"]
    normalized_catalog: list[dict[str, Any]] = []
    if catalog is not None:
        for item in catalog:
            normalized_catalog.append(normalize_anchor(item))
    exact = next(
        (item for item in normalized_catalog if item["semantic_anchor"] == semantic_anchor), None
    )
    candidates = [
        item for item in normalized_catalog
        if semantic_anchor in tuple((item.get("route") or {}).get("predecessor_anchors") or ())
    ]
    if exact is None:
        state = "STALE" if catalog_complete else "UNKNOWN"
        reason = (
            "the complete current anchor catalogue no longer contains this semantic identity"
            if catalog_complete else "the current anchor catalogue is unavailable or partial"
        )
    else:
        current_status = str(exact.get("currentness", {}).get("status") or "UNKNOWN").upper()
        if current_status == "REFUSED":
            state, reason = "REFUSED", "the current anchor's own currentness refused"
        elif current_status in {"UNKNOWN", "ABSENT", "IN_FLIGHT"}:
            state, reason = "UNKNOWN", "the current anchor cannot prove its source currentness"
        elif exact.get("source") != anchor.get("source") or current_status in {"STALE", "LAST-TRUSTED"}:
            state, reason = "STALE", "the semantic identity survives but its source/currentness roots moved"
            candidates.insert(0, exact)
        else:
            state, reason = "CURRENT", "the semantic identity and exact source roots remain current"
    visibility = "UNKNOWN"
    if visible_anchor_ids is not None:
        visibility = "VISIBLE" if semantic_anchor in visible_anchor_ids else "OFF_CAMERA"
    return {
        "status": state,
        "reason": reason,
        "visibility": visibility,
        "current_anchor": exact,
        "reconcile_candidates": candidates,
        "reconcile_available": bool(candidates),
    }


def project(
    events: Sequence[Mapping[str, Any]], *,
    anchor_catalog: Sequence[Mapping[str, Any]] | None = None,
    catalog_complete: bool = False,
    visible_anchor_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Fold ordered canonical events into the durable marker projection."""

    annotations: dict[str, dict[str, Any]] = {}
    command_ids: set[str] = set()
    event_handles: set[str] = set()
    defects: list[str] = []
    ordered_handles: list[str] = []
    for index, raw in enumerate(events):
        try:
            event = _normalize_event(raw)
        except (FeedbackRefused, KeyError) as exc:
            defects.append(f"event[{index}]: {exc}")
            continue
        if event["command_id"] in command_ids:
            defects.append(f"event[{index}]: duplicate command_id {event['command_id']}")
            continue
        if event["event_handle"] in event_handles:
            defects.append(f"event[{index}]: duplicate event_handle {event['event_handle']}")
            continue
        command_ids.add(event["command_id"])
        event_handles.add(event["event_handle"])
        annotation_id = event["annotation_id"]
        kind = event["event_type"]
        payload = event["payload"]
        if kind == "annotation.created":
            if annotation_id in annotations:
                defects.append(f"event[{index}]: annotation {annotation_id} was created twice")
                continue
            annotations[annotation_id] = {
                "annotation_id": annotation_id,
                "text": payload["text"],
                "state": "OPEN",
                "actor": event["actor"],
                "created_at": event["occurred_at"],
                "updated_at": event["occurred_at"],
                "original_anchor": payload["anchor"],
                "anchor": payload["anchor"],
                "anchor_lineage": [payload["anchor"]["anchor_handle"]],
                "replacement_annotation_id": None,
                "event_handles": [event["event_handle"]],
            }
            ordered_handles.append(annotation_id)
            continue
        annotation = annotations.get(annotation_id)
        if annotation is None:
            defects.append(f"event[{index}]: event targets unknown annotation {annotation_id}")
            continue
        if annotation["state"] in {"SUPERSEDED", "WITHDRAWN"}:
            defects.append(
                f"event[{index}]: terminal annotation {annotation_id} cannot transition or reconcile"
            )
            continue
        if kind == "annotation.transitioned":
            next_state = payload["state"]
            if annotation["state"] != "OPEN":
                defects.append(
                    f"event[{index}]: only OPEN annotations can enter {next_state}"
                )
                continue
            annotation["state"] = next_state
            annotation["replacement_annotation_id"] = payload["replacement_annotation_id"]
        else:
            anchor = payload["anchor"]
            annotation["anchor"] = anchor
            annotation["anchor_lineage"].append(anchor["anchor_handle"])
        annotation["updated_at"] = event["occurred_at"]
        annotation["event_handles"].append(event["event_handle"])
    visible = set(visible_anchor_ids) if visible_anchor_ids is not None else None
    folded: list[dict[str, Any]] = []
    for annotation_id in ordered_handles:
        annotation = annotations[annotation_id]
        anchor_face = _anchor_face(
            annotation["anchor"], catalog=anchor_catalog,
            catalog_complete=catalog_complete, visible_anchor_ids=visible,
        )
        folded.append({
            **annotation,
            "anchor_currentness": anchor_face,
            "routing": _derive_routing(annotation["anchor"]),
        })
    status = "REFUSED" if defects else "CURRENT" if catalog_complete else "UNKNOWN"
    preimage = {
        "schema_version": PROJECTION_SCHEMA,
        "status": status,
        "annotations": folded if not defects else [],
        "ordered_annotation_ids": ordered_handles if not defects else [],
        "counts": {
            state: sum(1 for annotation in folded if annotation["state"] == state)
            for state in sorted(ANNOTATION_STATES)
        } if not defects else {state: 0 for state in sorted(ANNOTATION_STATES)},
        "defects": defects,
        "catalog_complete": bool(catalog_complete),
        "persistence": {
            "required_adapter_schema": ADAPTER_SCHEMA,
            "available": True,
            "status": "CURRENT",
            "authority_effect": "none",
        },
    }
    preimage["projection_handle"] = canonical_handle(preimage, kind="front-feedback-projection")
    return preimage


def unavailable_projection(reason: str = "canonical Atlas annotation adapter is not available") -> dict[str, Any]:
    preimage = {
        "schema_version": PROJECTION_SCHEMA,
        "status": "REFUSED",
        "annotations": [],
        "ordered_annotation_ids": [],
        "counts": {state: 0 for state in sorted(ANNOTATION_STATES)},
        "defects": [reason],
        "catalog_complete": False,
        "persistence": {
            "required_adapter_schema": ADAPTER_SCHEMA,
            "available": False,
            "status": "REFUSED",
            "refusal": "CANONICAL_ADAPTER_UNAVAILABLE",
            "authority_effect": "none",
        },
    }
    preimage["projection_handle"] = canonical_handle(preimage, kind="front-feedback-projection")
    return preimage


def read(
    adapter: CanonicalFeedbackAdapter | None, *,
    anchor_catalog: Sequence[Mapping[str, Any]] | None = None,
    catalog_complete: bool = False,
    visible_anchor_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    if adapter is None:
        return unavailable_projection()
    if getattr(adapter, "schema_version", None) != ADAPTER_SCHEMA:
        return unavailable_projection("canonical adapter schema is absent or unknown")
    try:
        events = adapter.read_events()
    except Exception as exc:  # adapter refusal is data, not a shadow empty queue
        return unavailable_projection(f"canonical adapter read refused: {type(exc).__name__}: {exc}")
    return project(
        events, anchor_catalog=anchor_catalog, catalog_complete=catalog_complete,
        visible_anchor_ids=visible_anchor_ids,
    )


def execute(
    adapter: CanonicalFeedbackAdapter | None,
    command: Mapping[str, Any], *, occurred_at: str,
) -> dict[str, Any]:
    """Validate and append one command through the sole injected canonical adapter."""

    if adapter is None:
        return {
            "ok": False,
            "status": "REFUSED",
            "refusal": "CANONICAL_ADAPTER_UNAVAILABLE",
            "reason": "Atlas has no adopted semantic-annotation writer; no fallback ledger was used",
            "authority_effect": "none",
        }
    if getattr(adapter, "schema_version", None) != ADAPTER_SCHEMA:
        return {
            "ok": False,
            "status": "REFUSED",
            "refusal": "CANONICAL_ADAPTER_SCHEMA_MISMATCH",
            "authority_effect": "none",
        }
    try:
        normalized = validate_command(command)
        try:
            existing = tuple(adapter.read_events())
        except Exception as exc:
            return {
                "ok": False,
                "status": "REFUSED",
                "refusal": "CANONICAL_ADAPTER_UNAVAILABLE",
                "reason": f"canonical adapter read refused: {type(exc).__name__}: {exc}",
                "authority_effect": "none",
            }
        for raw in existing:
            event = _normalize_event(raw)
            if event["command_id"] == normalized["command_id"]:
                return {
                    "ok": True,
                    "status": "IDEMPOTENT",
                    "annotation_id": event["annotation_id"],
                    "event_handle": event["event_handle"],
                    "command_handle": normalized["command_handle"],
                    "authority_effect": "none",
                }
        # Refuse causally invalid lifecycle acts before asking the adapter to append.
        before = project(existing)
        if before["status"] == "REFUSED":
            raise FeedbackRefused("canonical feedback history is already malformed")
        if normalized["action"] != "CREATE":
            target = next(
                (item for item in before["annotations"]
                 if item["annotation_id"] == normalized["annotation_id"]), None
            )
            if target is None:
                raise FeedbackRefused("feedback command targets an unknown annotation")
            if target["state"] in {"SUPERSEDED", "WITHDRAWN"}:
                raise FeedbackRefused("feedback command targets a terminal annotation")
            if normalized["action"] == "TRANSITION" and target["state"] != "OPEN":
                raise FeedbackRefused("only OPEN annotations can transition")
        event = _event_for(normalized, occurred_at=occurred_at)
        try:
            receipt = _mapping(adapter.append_event(event), "append receipt")
        except Exception as exc:
            raise FeedbackRefused(
                f"canonical adapter append refused: {type(exc).__name__}: {exc}"
            ) from exc
        if receipt.get("accepted") is not True:
            raise FeedbackRefused(str(receipt.get("reason") or "canonical adapter refused append"))
        if receipt.get("event_handle") != event["event_handle"]:
            raise FeedbackRefused("canonical append receipt does not bind the event handle")
        position_handle = _text(receipt.get("position_handle"), "append receipt.position_handle")
    except (FeedbackRefused, KeyError, TypeError) as exc:
        return {
            "ok": False,
            "status": "REFUSED",
            "refusal": "INVALID_OR_UNPROVEN_FEEDBACK_ACT",
            "reason": str(exc),
            "authority_effect": "none",
        }
    return {
        "ok": True,
        "status": "APPENDED",
        "annotation_id": event["annotation_id"],
        "event_id": event["event_id"],
        "event_handle": event["event_handle"],
        "command_handle": normalized["command_handle"],
        "position_handle": position_handle,
        "adapter_receipt": receipt,
        "authority_effect": "none",
    }


@dataclass
class InMemoryFeedbackAdapter:
    """Safe specimen adapter; never use as product persistence."""

    events: list[dict[str, Any]]
    schema_version: str = ADAPTER_SCHEMA

    def read_events(self) -> Sequence[Mapping[str, Any]]:
        return tuple(self.events)

    def append_event(self, event: Mapping[str, Any]) -> Mapping[str, Any]:
        row = dict(event)
        self.events.append(row)
        return {
            "accepted": True,
            "event_handle": row["event_handle"],
            "position_handle": canonical_handle(
                {"sequence": len(self.events), "event_handle": row["event_handle"]},
                kind="front-feedback-position",
            ),
            "sequence": len(self.events),
            "specimen_only": True,
        }


__all__ = [
    "ADAPTER_SCHEMA", "ANCHOR_SCHEMA", "ANNOTATION_STATES", "COMMAND_SCHEMA",
    "EVENT_SCHEMA", "PROJECTION_SCHEMA", "CanonicalFeedbackAdapter", "FeedbackRefused",
    "InMemoryFeedbackAdapter", "canonical_bytes", "canonical_handle", "create_command",
    "execute", "normalize_anchor", "project", "read", "reconcile_command",
    "transition_command", "unavailable_projection", "validate_command",
]
