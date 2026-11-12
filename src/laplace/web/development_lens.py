"""Seven bounded Aisthesis cameras over one canonical DevelopmentWorkMap read model.

This module owns no development state.  It consumes ``wake.development_work_map_glow``
and renders one read-only representation carrying the exact canonical coordinate,
shown handle, omission residual, and typed source links.  It never reads a ledger and it
offers no mutation endpoint.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable, Mapping

_JSON = "application/json; charset=utf-8"
_HTML = "text/html; charset=utf-8"
_PAGE = Path(__file__).resolve().parent / "development_lens.html"
_DEFAULT_CAP = 8
_HEX_TAIL = re.compile(r"^(?:sha256:|message:)([0-9a-f]+)$")
_MODEL_SCHEMA = "laplace.aisthesis-read-model/1"
_SHOWN_SCHEMA = "laplace.aisthesis-shown-state/1"
_CONTINUITY_SCHEMA = "laplace.aisthesis-continuity-loom/1"
_CONTINUITY_FIELD_SCHEMA = "laplace.aisthesis-continuity-field/1"
_CONTINUITY_LAYOUT_SCHEMA = "laplace.aisthesis-continuity-layout/1"
_CONTINUITY_LAYOUT_VERSION = "integer-causal-lanes-v2"
_CONTINUITY_GRADES = ("far", "mid", "near", "audit")
_EXPOSITION_GRADES = tuple(f"E{index}" for index in range(8))
_SHOWN_PREIMAGE_KEYS = (
    "model_handle",
    "lens_id",
    "focus_handle",
    "selected_edge_id",
    "ordered_visible_handles",
    "visible_set_digest",
    "omitted_set_digest",
    "representation_grade",
    "exposition",
    "viewport",
    "layout_receipt_handle",
    "selected_audit_subject",
    "binding_generation",
    "effective_authority_handle",
)
_CAMERAS = (
    "programme",
    "critical-path",
    "live-custody",
    "evidence-descent",
    "continuity",
    "residual-crutch",
    "lens-self",
)


def _q1(query: Mapping[str, Any], key: str, default: str = "") -> str:
    value = query.get(key, default)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else default
    return str(value)


def _optional_q(query: Mapping[str, Any], key: str) -> str | None:
    value = query.get(key)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return None if value in (None, "") else str(value)


def _json_string_list_q(query: Mapping[str, Any], key: str) -> list[str] | None:
    raw = _q1(query, key)
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return value


def _json_digest(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _read_map(candidate_cap: int = _DEFAULT_CAP) -> dict[str, Any]:
    """Call the one canonical adapter; kept as a seam for bounded fixture tests."""

    from laplace.engine.wake import development_work_map_glow

    return development_work_map_glow(candidate_cap=candidate_cap)


def _read_authority() -> dict[str, Any]:
    """Read one drift-fenced provider/lease face without founding or repairing it."""

    from laplace.representation import atlas_bridge

    before = atlas_bridge.drift_token()
    provider = atlas_bridge.snapshot()["provider"]
    leases = atlas_bridge.region_leases()
    after = atlas_bridge.drift_token()
    if before != after:
        raise RuntimeError("Atlas moved while the authority face was being joined")
    return {
        "schema_version": "laplace.aisthesis-authority-join/1",
        "drift_token": after,
        "provider": provider,
        "lease_projection": leases,
        "read_only": True,
    }


def _read_conversation() -> dict[str, Any]:
    """Use Lane A's one pure conversation projection; never copy its join logic."""

    from laplace.web.front_door import _conversation_serve_data

    return _conversation_serve_data()


def _capture_projection(
    reader: Callable[[], dict[str, Any]] | None,
    *,
    absent_exception: str | None = None,
) -> dict[str, Any]:
    """Make a read refusal/absence visible without laundering it into an empty face."""

    if reader is None:
        return {
            "capture_state": "ABSENT",
            "reason": "no upstream projection reader was supplied",
            "value": None,
        }
    try:
        value = reader()
    except Exception as exc:  # noqa: BLE001 - the refusal is product evidence
        if absent_exception and type(exc).__name__ == absent_exception:
            state = "ABSENT"
        else:
            state = "REFUSED"
        return {
            "capture_state": state,
            "reason": f"{type(exc).__name__}: {exc}",
            "value": None,
        }
    if not isinstance(value, Mapping):
        return {
            "capture_state": "REFUSED",
            "reason": "upstream projection did not return a mapping",
            "value": None,
        }
    return {"capture_state": "COMPLETE", "reason": None, "value": dict(value)}


def _git_head() -> str | None:
    from laplace.core.versioning import head_sha

    return head_sha(source_tree())


def _short(reference: Any, width: int = 10) -> str:
    text = str(reference or "")
    match = _HEX_TAIL.match(text)
    if match:
        return match.group(1)[:width]
    return text[:width]


def _human_type(value: Any) -> str:
    text = str(value or "unnamed development evidence")
    for suffix in ("-commission", "-verdict", "-request"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
            break
    return text.replace("-", " ")


def _edge_faces(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Materialise stable typed edges from the adapter's exact source links."""

    edges: list[dict[str, Any]] = []
    for row in rows:
        for ordinal, link in enumerate(row.get("source_links") or []):
            preimage = {
                "schema_version": "laplace.aisthesis-edge-id/1",
                "source_handle": row["node_handle"],
                "ordinal": ordinal,
                "role": link["role"],
                "kind": link["kind"],
                "reference": link["reference"],
            }
            edges.append(
                {
                    "edge_id": _json_digest(preimage),
                    "source_handle": row["node_handle"],
                    "target_reference": link["reference"],
                    "role": link["role"],
                    "kind": link["kind"],
                    "ordinal": ordinal,
                    "evidence_state": "COMPLETE",
                    "budget": {
                        "kind": "exact-reference",
                        "limit": 1,
                        "visible": 1,
                        "omitted": 0,
                    },
                    "continuation": {
                        "action": "reconstruct exact target reference",
                        "reference": link["reference"],
                    },
                }
            )
    return edges


def _acknowledgement(source: Mapping[str, Any]) -> dict[str, Any]:
    """Carry an existing receipt-shaped acknowledgement; never infer one."""

    value = source.get("acknowledgement")
    if not isinstance(value, Mapping):
        return {
            "state": "NOT-IN-THIS-SLICE",
            "actor": None,
            "shown_handle": None,
            "receipt_event_id": None,
        }
    receipt = dict(value)
    receipt.setdefault("state", "UNKNOWN")
    return receipt


def _critical_path(
    source: Mapping[str, Any], open_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Admit at most five rows only when the adapter supplies canonical proof."""

    proof = source.get("attention_selection")
    if not isinstance(proof, Mapping):
        return {
            "state": "UNKNOWN",
            "ordered_handles": [],
            "selection_handle": None,
            "reason": "canonical attention ordering/selection proof absent",
        }
    ordered = proof.get("ordered_handles")
    source_handle = (source.get("freshness") or {}).get("source_handle")
    open_handles = [row["node_handle"] for row in open_rows]
    valid = (
        proof.get("schema_version") == "laplace.representation.attention-selection/1"
        and proof.get("state") == "CURRENT"
        and proof.get("source_handle") == source_handle
        and proof.get("selection_handle")
        and isinstance(ordered, list)
        and len(ordered) <= 5
        and len(ordered) == len(set(ordered))
        and all(handle in open_handles for handle in ordered)
        and proof.get("open_set_digest") == _json_digest(sorted(open_handles))
    )
    if not valid:
        return {
            "state": "UNKNOWN",
            "ordered_handles": [],
            "selection_handle": proof.get("selection_handle"),
            "reason": "attention selection proof is incomplete or does not match the visible open set",
        }
    return {
        "state": "CURRENT",
        "ordered_handles": list(ordered),
        "selection_handle": proof["selection_handle"],
        "reason": None,
    }


def _authority_face(
    captured: Mapping[str, Any], source: Mapping[str, Any]
) -> dict[str, Any]:
    """Join exact binding generations and effective leases to the map coordinate."""

    if captured.get("capture_state") != "COMPLETE":
        return {
            "state": "UNKNOWN" if captured.get("capture_state") == "ABSENT" else "REFUSED",
            "reason": captured.get("reason"),
            "seat_occupancy": [],
            "leases": [],
            "binding_generation": None,
            "effective_authority": [],
            "effective_authority_handle": _json_digest(
                {
                    "capture_state": captured.get("capture_state"),
                    "reason": captured.get("reason"),
                }
            ),
            "evidence_edge": {
                "edge_id": _json_digest({"projection": "authority", "state": "REFUSED"}),
                "role": "authority-projection",
                "evidence_state": "REFUSED",
                "budget": {"kind": "all-current-seats-and-leases", "limit": None},
                "continuation": "repair and rederive the canonical authority projection",
            },
        }

    joined = captured.get("value") or {}
    provider = joined.get("provider")
    lease_projection = joined.get("lease_projection")
    if not isinstance(provider, Mapping) or not isinstance(lease_projection, Mapping):
        return _authority_face(
            {
                "capture_state": "REFUSED",
                "reason": "authority join omitted provider or lease projection",
            },
            source,
        )
    occupancies = provider.get("seat_occupancy")
    leases = lease_projection.get("leases")
    if not isinstance(occupancies, Mapping) or not isinstance(leases, Mapping):
        return _authority_face(
            {
                "capture_state": "REFUSED",
                "reason": "authority join carried malformed occupancy or lease rows",
            },
            source,
        )
    coordinate = (source.get("freshness") or {}).get("coordinate") or {}
    expected_cursor = str(source.get("caused_by_event_cursor", coordinate.get("event_cursor", "")))
    expected_head = str(source.get("head_event_id", coordinate.get("head_event_id", "")))
    observed_cursor = str(provider.get("event_count", ""))
    observed_head = str(provider.get("head_event_id", ""))
    if expected_cursor != observed_cursor or expected_head != observed_head:
        return _authority_face(
            {
                "capture_state": "REFUSED",
                "reason": (
                    "authority coordinate disagrees with DevelopmentWorkMap "
                    f"({expected_cursor}/{expected_head} != {observed_cursor}/{observed_head})"
                ),
            },
            source,
        )

    seat_rows: list[dict[str, Any]] = []
    binding_generation = None
    for seat_id, occupancy_value in sorted(occupancies.items()):
        occupancy = occupancy_value if isinstance(occupancy_value, Mapping) else {}
        binding = occupancy.get("binding") if isinstance(occupancy.get("binding"), Mapping) else {}
        join = occupancy.get("join") if isinstance(occupancy.get("join"), Mapping) else {}
        generation = (
            binding.get("provider_identity_generation")
            or join.get("provider_identity_generation")
            or occupancy.get("current_provider_identity_generation")
        )
        if seat_id == "sensorium-seat":
            binding_generation = generation
        seat_rows.append(
            {
                "seat_id": seat_id,
                "state": occupancy.get("state"),
                "function": join.get("function"),
                "routing_authority": bool(occupancy.get("routing_authority")),
                "binding_event_id": occupancy.get("binding_event_id"),
                "binding_generation": generation,
                "defects": list(occupancy.get("defects") or []),
            }
        )
    lease_rows = []
    effective_authority = []
    for lease_id, lease_value in sorted(leases.items()):
        lease = lease_value if isinstance(lease_value, Mapping) else {}
        checkout = lease.get("checkout") if isinstance(lease.get("checkout"), Mapping) else {}
        row = {
            "lease_id": lease_id,
            "seat_id": checkout.get("seat_id"),
            "holder_ref": checkout.get("holder_ref"),
            "function": checkout.get("function"),
            "regions": list(checkout.get("regions") or []),
            "effective_state": lease.get("effective_state"),
            "write_authority": lease.get("write_authority") is True,
            "lineage_state": lease.get("lineage_state"),
            "authority_observed_at": lease.get("authority_observed_at"),
        }
        lease_rows.append(row)
        if row["seat_id"] == "sensorium-seat":
            effective_authority.append(row)
    authority_identity = {
        "binding_generation": binding_generation,
        "effective_authority": effective_authority,
    }
    return {
        "state": "CURRENT",
        "reason": None,
        "seat_occupancy": seat_rows,
        "leases": lease_rows,
        **authority_identity,
        "effective_authority_handle": _json_digest(authority_identity),
        "evidence_edge": {
            "edge_id": _json_digest(
                {
                    "projection": "authority",
                    "cursor": observed_cursor,
                    "head_event_id": observed_head,
                    "authority": authority_identity,
                }
            ),
            "role": "authority-projection",
            "evidence_state": "COMPLETE",
            "budget": {
                "kind": "all-current-seats-and-leases",
                "limit": None,
                "visible": len(seat_rows) + len(lease_rows),
                "omitted": 0,
            },
            "continuation": "/front/development?lens=live-custody",
        },
    }


def _conversation_face(captured: Mapping[str, Any]) -> dict[str, Any]:
    """Expose the pure Lane A serve when present; exact absence remains UNKNOWN."""

    if captured.get("capture_state") != "COMPLETE":
        absent = captured.get("capture_state") == "ABSENT"
        return {
            "state": "UNKNOWN" if absent else "REFUSED",
            "reason": captured.get("reason"),
            "projection": None,
            "evidence_edge": {
                "edge_id": _json_digest(
                    {
                        "projection": "conversation",
                        "state": captured.get("capture_state"),
                        "reason": captured.get("reason"),
                    }
                ),
                "role": "conversation-projection",
                "evidence_state": "REFUSED",
                "budget": {"kind": "latest-author-turn", "limit": 1, "visible": 0},
                "continuation": "/front/serve",
            },
        }
    value = captured.get("value") or {}
    if value.get("schema_version") != "laplace.conversation-serve/1" or not value.get(
        "shown_handle"
    ):
        return _conversation_face(
            {
                "capture_state": "REFUSED",
                "reason": "conversation projection omitted its schema or exact shown handle",
            }
        )
    projection = {
        key: value.get(key)
        for key in (
            "serve_id",
            "turn_handle",
            "shown_handle",
            "author_lifecycle",
            "mixed_recipient_phases",
            "recipient_states",
            "dependency_frontier",
            "omission_residual",
            "author_turn_custody",
            "acknowledgement_eligible",
            "browser_event_cursor",
            "browser_head_event_id",
            "audience",
            "decision",
            "replies",
            "quarantine",
            "supersession",
            "closed_handle",
            "as_of",
        )
    }
    omissions = list(value.get("omission_residual") or [])
    return {
        "state": "CURRENT",
        "reason": None,
        "projection": projection,
        "evidence_edge": {
            "edge_id": _json_digest(
                {
                    "projection": "conversation",
                    "shown_handle": value.get("shown_handle"),
                }
            ),
            "role": "conversation-projection",
            "evidence_state": "BUDGET" if omissions else "COMPLETE",
            "budget": {
                "kind": "one-exact-author-turn-serve",
                "limit": 1,
                "visible": 1,
                "omitted": len(omissions),
            },
            "continuation": "/front/serve",
        },
    }


_CONTINUITY_RESIDUALS = (
    (
        "PHASE",
        "conversation projection owner",
        "every intended recipient carries an exact typed phase from the same conversation serve",
    ),
    (
        "QUARANTINE",
        "Fabric lifecycle projection owner",
        "the conversation projection carries the exact quarantine state and causal receipt",
    ),
    (
        "SUPERSESSION",
        "Fabric lifecycle projection owner",
        "the conversation projection carries every superseded message and its replacement edge",
    ),
    (
        "CLOSED",
        "author lifecycle projection owner",
        "the conversation projection carries Gerard's exact closed handle and closing edge",
    ),
    (
        "AS_OF",
        "conversation currentness owner",
        "the conversation projection carries an authenticated observation time and source coordinate",
    ),
    (
        "REPLY_ROOT",
        "conversation reply projection owner",
        "every visible reply carries its exact acknowledgement or author-turn dependency root",
    ),
)


def _continuity_handle(
    kind: str,
    evidence_handle: Any,
    *,
    recipient: str | None = None,
    ordinal: int = 0,
) -> str:
    """Mint a stable visual-object identity without aliasing its evidence handle."""

    return _json_digest(
        {
            "schema_version": "laplace.aisthesis-continuity-object-id/1",
            "kind": kind,
            "evidence_handle": evidence_handle,
            "recipient": recipient,
            "ordinal": ordinal,
        }
    )


def _continuity_object(
    *,
    kind: str,
    label: str,
    evidence_handle: Any,
    state: str,
    recipient: str | None = None,
    ordinal: int = 0,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    exact = evidence_handle not in (None, "")
    source_references = [evidence_handle] if exact else []
    exposition = [
        {
            "grade": "E0",
            "state": "COMPLETE",
            "claim": label,
            "authority": "READ_ONLY",
            "source_references": source_references,
        },
        {
            "grade": "E1",
            "state": "UNKNOWN",
            "claim": "the motivating-problem evidence is not carried by this projection",
            "authority": "ZERO",
            "source_references": [],
        },
        {
            "grade": "E2",
            "state": "COMPLETE" if exact else "UNKNOWN",
            "claim": state if exact else "present state is unresolved",
            "authority": "READ_ONLY",
            "source_references": source_references,
        },
        {
            "grade": "E3",
            "state": "UNKNOWN",
            "claim": "invariant and refusal receipts are not carried by this projection",
            "authority": "ZERO",
            "source_references": [],
        },
        {
            "grade": "E4",
            "state": "UNKNOWN",
            "claim": "mechanism evidence is not carried by this projection",
            "authority": "ZERO",
            "source_references": [],
        },
        {
            "grade": "E5",
            "state": "UNKNOWN",
            "claim": "mathematical correspondence is not carried by this projection",
            "authority": "ZERO",
            "source_references": [],
        },
        {
            "grade": "E6",
            "state": "COMPLETE" if exact else "UNKNOWN",
            "claim": "exact source descent is available" if exact else "source descent is unresolved",
            "authority": "READ_ONLY",
            "source_references": source_references,
            "descend": (
                None
                if not exact
                else {"action": "reconstruct exact evidence", "reference": evidence_handle}
            ),
        },
        {
            "grade": "E7",
            "state": "ZERO",
            "claim": "no production-authority specimen is available",
            "authority": "ZERO",
            "source_references": source_references,
        },
    ]
    return {
        "object_handle": _continuity_handle(
            kind, evidence_handle, recipient=recipient, ordinal=ordinal
        ),
        "kind": kind,
        "label": label,
        "state": state if exact else "UNKNOWN",
        "recipient": recipient,
        "evidence_state": "COMPLETE" if exact else "UNRESOLVED",
        "evidence_handle": evidence_handle if exact else None,
        "evidence": dict(evidence or {}),
        "receipt_ids": source_references,
        "descend": (
            None
            if not exact
            else {"action": "reconstruct exact evidence", "reference": evidence_handle}
        ),
        "exposition": exposition,
    }


def _continuity_edge(
    source: Mapping[str, Any],
    target: Mapping[str, Any],
    *,
    role: str,
    exact: bool,
    cause: Any,
    continuation: str,
) -> dict[str, Any]:
    preimage = {
        "schema_version": "laplace.aisthesis-continuity-edge-id/1",
        "source_handle": source["object_handle"],
        "target_handle": target["object_handle"],
        "role": role,
        "cause": cause,
    }
    return {
        "edge_id": _json_digest(preimage),
        "source_handle": source["object_handle"],
        "target_handle": target["object_handle"],
        "role": role,
        "relation": role,
        "label": role.replace("-", " "),
        "state": "COMPLETE" if exact else "UNRESOLVED",
        "evidence_state": "COMPLETE" if exact else "UNRESOLVED",
        "cause_handle": cause if exact else None,
        "receipt_ids": [cause] if exact and cause not in (None, "") else [],
        "budget": {
            "kind": "one-exact-causal-relation",
            "limit": 1,
            "visible": 1 if exact else 0,
            "omitted": 0 if exact else 1,
        },
        "continuation": continuation,
    }


def _continuity_residuals(projection: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Carry the six unpaid lifecycle faces with exact retirement predicates."""

    projection = projection or {}
    recipients = projection.get("recipient_states")
    recipients = recipients if isinstance(recipients, list) else []
    replies = projection.get("replies")
    replies = replies if isinstance(replies, list) else []
    evidence = {
        "PHASE": bool(recipients)
        and all(isinstance(row, Mapping) and row.get("phase") for row in recipients),
        "QUARANTINE": isinstance(projection.get("quarantine"), Mapping)
        and bool(projection.get("quarantine")),
        "SUPERSESSION": isinstance(projection.get("supersession"), Mapping)
        and bool(projection.get("supersession")),
        "CLOSED": bool(projection.get("closed_handle")),
        "AS_OF": isinstance(projection.get("as_of"), Mapping)
        and bool(projection.get("as_of")),
        "REPLY_ROOT": bool(replies)
        and all(
            isinstance(row, Mapping)
            and isinstance(row.get("dependency_roots"), Mapping)
            and bool(row.get("dependency_roots"))
            for row in replies
        ),
    }
    return [
        {
            "class": name,
            "state": "COMPLETE" if evidence[name] else "UNRESOLVED",
            "owner": owner,
            "retirement_trigger": {
                "predicate": predicate,
                "comparison": "exact",
            },
        }
        for name, owner, predicate in _CONTINUITY_RESIDUALS
    ]


def _continuity_field(
    conversation: Mapping[str, Any], authority: Mapping[str, Any]
) -> dict[str, Any]:
    """Normalize one conversation and admitted authority face without row-order causality."""

    projection = conversation.get("projection")
    projection = projection if isinstance(projection, Mapping) else None
    objects: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    recipients = [] if projection is None else projection.get("recipient_states")
    recipients = recipients if isinstance(recipients, list) else []
    replies = [] if projection is None else projection.get("replies")
    replies = replies if isinstance(replies, list) else []
    turn_handle = None if projection is None else projection.get("turn_handle")
    turn = _continuity_object(
        kind="turn",
        label="Author turn",
        evidence_handle=turn_handle,
        state=str((projection or {}).get("author_lifecycle") or "UNKNOWN"),
        evidence={
            "audience": (projection or {}).get("audience"),
            "decision": (projection or {}).get("decision"),
        },
    )
    if projection is not None:
        objects.append(turn)

    for ordinal, raw in enumerate(recipients):
        row = raw if isinstance(raw, Mapping) else {}
        recipient = str(row.get("logical_recipient") or f"reader {ordinal + 1}")
        message = _continuity_object(
            kind="message",
            label=f"Message for {recipient}",
            evidence_handle=row.get("recipient_message_id"),
            state=str(row.get("transport_state") or row.get("phase") or "UNKNOWN"),
            recipient=recipient,
            ordinal=ordinal,
            evidence={"phase": row.get("phase")},
        )
        pull = _continuity_object(
            kind="pull",
            label=f"Received by {recipient}",
            evidence_handle=row.get("received_event"),
            state="RECEIVED" if row.get("received_event") else "UNKNOWN",
            recipient=recipient,
            ordinal=ordinal,
        )
        reconstruction_evidence = row.get("reconstruction_handle") or row.get(
            "reconstruction_event"
        )
        reconstruction = _continuity_object(
            kind="reconstruction",
            label=f"Reconstructed by {recipient}",
            evidence_handle=reconstruction_evidence,
            state="RECONSTRUCTED" if reconstruction_evidence else "UNKNOWN",
            recipient=recipient,
            ordinal=ordinal,
            evidence={"event": row.get("reconstruction_event")},
        )
        acknowledgement = _continuity_object(
            kind="acknowledgement",
            label=f"Acknowledgement from {recipient}",
            evidence_handle=row.get("ack_event"),
            state="ACKNOWLEDGED" if row.get("ack_event") else "UNKNOWN",
            recipient=recipient,
            ordinal=ordinal,
        )
        objects.extend((message, pull, reconstruction, acknowledgement))
        if projection is not None:
            edges.append(
                _continuity_edge(
                    turn,
                    message,
                    role="routed-to-recipient",
                    exact=bool(row.get("recipient_message_id")),
                    cause=row.get("recipient_message_id"),
                    continuation="derive the exact recipient message from /front/serve",
                )
            )
        edges.extend(
            (
                _continuity_edge(
                    message,
                    pull,
                    role="pulled-by-recipient",
                    exact=bool(row.get("received_event")),
                    cause=row.get("received_event"),
                    continuation="wait for or descend to the exact pull receipt",
                ),
                _continuity_edge(
                    pull,
                    reconstruction,
                    role="typed-reconstruction",
                    exact=bool(reconstruction_evidence and row.get("received_event")),
                    cause=row.get("reconstruction_event"),
                    continuation="reconstruct the exact recipient message",
                ),
                _continuity_edge(
                    reconstruction,
                    acknowledgement,
                    role="acknowledges-reconstruction",
                    exact=bool(row.get("ack_event") and reconstruction_evidence),
                    cause=row.get("ack_event"),
                    continuation="acknowledge only with the exact reconstruction proof",
                ),
            )
        )

    for ordinal, raw in enumerate(replies):
        reply = raw if isinstance(raw, Mapping) else {}
        reply_object = _continuity_object(
            kind="reply",
            label="Rooted reply" if reply.get("dependency_roots") else "Reply observed",
            evidence_handle=reply.get("message_id"),
            state=str(reply.get("status") or "UNKNOWN"),
            ordinal=ordinal,
            evidence={
                "body_handle": reply.get("body_handle"),
                "dependency_roots": reply.get("dependency_roots"),
            },
        )
        objects.append(reply_object)
        if projection is not None:
            roots = reply.get("dependency_roots")
            exact_root = isinstance(roots, Mapping) and bool(roots)
            edges.append(
                _continuity_edge(
                    turn,
                    reply_object,
                    role="reply-belongs-to-turn",
                    exact=exact_root,
                    cause=roots,
                    continuation="supply the reply's exact acknowledgement or turn root",
                )
            )

    authority_handle = authority.get("effective_authority_handle")
    authority_object = _continuity_object(
        kind="authority",
        label="Current authority",
        evidence_handle=authority_handle,
        state=str(authority.get("state") or "UNKNOWN"),
        evidence={
            "binding_generation": authority.get("binding_generation"),
            "effective_authority": authority.get("effective_authority"),
        },
    )
    objects.append(authority_object)
    for raw in recipients:
        row = raw if isinstance(raw, Mapping) else {}
        seat_id = row.get("diagnostic_seat_id")
        if not seat_id:
            continue
        message = next(
            (
                item
                for item in objects
                if item["kind"] == "message"
                and item["recipient"] == row.get("logical_recipient")
            ),
            None,
        )
        occupancy = next(
            (
                item
                for item in authority.get("seat_occupancy", [])
                if item.get("seat_id") == seat_id
            ),
            None,
        )
        if message is not None:
            exact = bool(
                occupancy
                and occupancy.get("routing_authority")
                and occupancy.get("binding_generation")
            )
            edges.append(
                _continuity_edge(
                    authority_object,
                    message,
                    role="routes-under-current-authority",
                    exact=exact,
                    cause=None if occupancy is None else occupancy.get("binding_event_id"),
                    continuation="rederive the exact seat binding and generation",
                )
            )

    omission_rows = [] if projection is None else projection.get("omission_residual")
    omission_rows = omission_rows if isinstance(omission_rows, list) else []
    groups = []
    for name in sorted({str(row.get("class") or "UNCLASSIFIED") for row in omission_rows if isinstance(row, Mapping)}):
        members = [
            dict(row)
            for row in omission_rows
            if isinstance(row, Mapping) and str(row.get("class") or "UNCLASSIFIED") == name
        ]
        groups.append(
            {
                "group_handle": _json_digest(
                    {
                        "schema_version": "laplace.aisthesis-continuity-group/1",
                        "class": name,
                        "members": members,
                    }
                ),
                "class": name,
                "label": name.replace("-", " "),
                "count": len(members),
                "digest": _json_digest(members),
                "evidence_state": "BUDGET",
                "continuation": [row.get("descend") for row in members],
            }
        )

    canonical_order = [item["object_handle"] for item in objects]
    return {
        "schema_version": _CONTINUITY_FIELD_SCHEMA,
        "state": (
            "REFUSED"
            if conversation.get("state") == "REFUSED" or authority.get("state") == "REFUSED"
            else (
                "CURRENT"
                if conversation.get("state") == "CURRENT" and authority.get("state") == "CURRENT"
                else "UNKNOWN"
            )
        ),
        "objects": objects,
        "edges": edges,
        "canonical_order": canonical_order,
        "omission_groups": groups,
        "residuals": _continuity_residuals(projection),
        "projection_boundary": "/front/serve",
        "conversation_shown_handle": None if projection is None else projection.get("shown_handle"),
        "authority_handle": authority_handle,
        "read_only": True,
    }


def _continuity_layout(
    field: Mapping[str, Any],
    *,
    viewport: str,
    focus: str,
    edge: str,
    grade: str,
    exposition: str,
) -> dict[str, Any]:
    """Project exact focus cuts and deterministic integer-only geometry."""

    canonical_objects = [
        dict(item) for item in field.get("objects", []) if isinstance(item, Mapping)
    ]
    canonical_edges = [
        dict(item) for item in field.get("edges", []) if isinstance(item, Mapping)
    ]
    canonical_order = list(field.get("canonical_order", []))
    by_handle = {item["object_handle"]: item for item in canonical_objects}
    requested_focus_invalid = bool(focus) and focus not in by_handle
    focus_handle = focus if focus in by_handle else ""
    if not focus_handle and not requested_focus_invalid and canonical_objects:
        unresolved_ack = next(
            (
                item
                for item in canonical_objects
                if item["kind"] == "acknowledgement"
                and item["evidence_state"] == "UNRESOLVED"
            ),
            None,
        )
        focus_handle = (unresolved_ack or canonical_objects[0])["object_handle"]
    layout_focus = focus_handle or (canonical_order[0] if canonical_order else "")

    adjacency = {handle: set() for handle in by_handle}
    for item in canonical_edges:
        if item["source_handle"] in adjacency and item["target_handle"] in adjacency:
            adjacency[item["source_handle"]].add(item["target_handle"])
            adjacency[item["target_handle"]].add(item["source_handle"])
    distance = {layout_focus: 0} if layout_focus else {}
    frontier = {layout_focus} if layout_focus else set()
    while frontier:
        next_frontier = set()
        for handle in frontier:
            for candidate in adjacency.get(handle, ()):
                if candidate not in distance:
                    distance[candidate] = distance[handle] + 1
                    next_frontier.add(candidate)
        frontier = next_frontier
    limit = {"far": 0, "mid": 1, "near": 2, "audit": 999}[grade]
    visible_original_handles = [
        handle
        for handle in canonical_order
        if distance.get(handle, 999) <= limit
        or by_handle[handle]["evidence_state"] == "UNRESOLVED"
        or by_handle[handle]["kind"] in {"turn", "authority"}
    ]
    visible_set = set(visible_original_handles)
    omitted_handles = [handle for handle in canonical_order if handle not in visible_set]
    focus_index = canonical_order.index(layout_focus) if layout_focus in canonical_order else 0
    ordinary_states = {
        "COMPLETE", "CURRENT", "ROUTED", "DELIVERED", "RECEIVED",
        "RECONSTRUCTED", "ACKNOWLEDGED", "ROOTED", "BOUND",
    }

    compressed_groups: list[dict[str, Any]] = []
    for cut, members in (
        ("UPSTREAM", [h for h in omitted_handles if canonical_order.index(h) < focus_index]),
        ("DOWNSTREAM", [h for h in omitted_handles if canonical_order.index(h) >= focus_index]),
    ):
        if not members:
            continue
        boundary = members[-1] if cut == "UPSTREAM" else members[0]
        exceptional = []
        for handle in members:
            state = str(by_handle[handle].get("state") or "UNKNOWN")
            if state not in ordinary_states and state not in exceptional:
                exceptional.append(state)
        digest = _json_digest(members)
        preimage = {
            "schema_version": "laplace.aisthesis-continuity-cut-group/1",
            "cut": cut,
            "focus_handle": layout_focus,
            "grade": grade,
            "ordered_member_handles": members,
            "member_digest": digest,
            "boundary_member": boundary,
            "exceptional_states": exceptional,
        }
        group_handle = _json_digest(preimage)
        compressed_groups.append(
            {
                **preimage,
                "group_handle": group_handle,
                "object_handle": group_handle,
                "kind": "compressed-group",
                "class": f"{cut}_CUT",
                "label": (
                    "Earlier causal context" if cut == "UPSTREAM"
                    else "Later causal consequence"
                ),
                "state": "UNKNOWN" if exceptional else "BUDGET",
                "evidence_state": "BUDGET",
                "member_count": len(members),
                "count": len(members),
                "digest": digest,
                "continuation": {
                    "action": "expand the exact cut at its boundary member",
                    "focus_handle": boundary,
                    "grade": "near" if grade in {"far", "mid"} else "audit",
                    "ordered_member_handles": members,
                    "member_digest": digest,
                },
                "receipt_ids": [],
                "exposition": [],
            }
        )
    group_by_member = {
        handle: group
        for group in compressed_groups
        for handle in group["ordered_member_handles"]
    }
    display_order: list[str] = []
    for handle in canonical_order:
        if handle in visible_set:
            display_order.append(handle)
        else:
            group_handle = group_by_member[handle]["group_handle"]
            if group_handle not in display_order:
                display_order.append(group_handle)
    group_by_handle = {item["group_handle"]: item for item in compressed_groups}
    display_objects = [
        dict(by_handle[handle]) if handle in by_handle else dict(group_by_handle[handle])
        for handle in display_order
    ]

    cut_buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    display_edges: list[dict[str, Any]] = []
    for item in canonical_edges:
        source = group_by_member.get(item["source_handle"], {}).get(
            "group_handle", item["source_handle"]
        )
        target = group_by_member.get(item["target_handle"], {}).get(
            "group_handle", item["target_handle"]
        )
        if source == target:
            continue
        if source == item["source_handle"] and target == item["target_handle"]:
            display_edges.append(dict(item))
        else:
            cut_buckets.setdefault((source, target), []).append(item)
    cut_edges: list[dict[str, Any]] = []
    for (source, target), members in cut_buckets.items():
        member_ids = [item["edge_id"] for item in members]
        preimage = {
            "schema_version": "laplace.aisthesis-continuity-cut-edge/1",
            "source_handle": source,
            "target_handle": target,
            "ordered_member_edge_ids": member_ids,
            "member_digest": _json_digest(member_ids),
        }
        cut_edge = {
            **preimage,
            "edge_id": _json_digest(preimage),
            "kind": "cut-edge",
            "role": "compressed-causal-cut",
            "relation": "compressed-causal-cut",
            "label": "continues through hidden context",
            "state": (
                "UNRESOLVED"
                if any(item.get("evidence_state") != "COMPLETE" for item in members)
                else "COMPLETE"
            ),
            "evidence_state": "BUDGET",
            "member_count": len(members),
            "receipt_ids": [],
            "continuation": "expand the adjacent exact cut group",
        }
        cut_edges.append(cut_edge)
    display_edges.extend(cut_edges)

    edge_by_id = {item["edge_id"]: item for item in display_edges}
    requested_edge_invalid = bool(edge) and edge not in edge_by_id
    selected_edge = edge if edge in edge_by_id else ""
    selected_audit_subject = (
        f"edge:{selected_edge}" if selected_edge else (
            f"object:{focus_handle}" if focus_handle else None
        )
    )
    coverage_preimage = {
        "schema_version": "laplace.aisthesis-continuity-compression/1",
        "canonical_order": canonical_order,
        "visible_original_handles": visible_original_handles,
        "groups": [
            {
                "group_handle": item["group_handle"],
                "ordered_member_handles": item["ordered_member_handles"],
                "member_digest": item["member_digest"],
                "boundary_member": item["boundary_member"],
                "exceptional_states": item["exceptional_states"],
            }
            for item in compressed_groups
        ],
        "cut_edges": [
            {
                "edge_id": item["edge_id"],
                "ordered_member_edge_ids": item["ordered_member_edge_ids"],
                "member_digest": item["member_digest"],
            }
            for item in cut_edges
        ],
    }
    compression_receipt_handle = _json_digest(coverage_preimage)

    recipients = []
    for item in display_objects:
        recipient = item.get("recipient")
        if recipient and recipient not in recipients:
            recipients.append(recipient)
    row_by_recipient = {recipient: index for index, recipient in enumerate(recipients)}
    row_count = max(1, len(recipients))
    stages = {
        "turn": 0, "authority": 1, "message": 1, "pull": 2,
        "reconstruction": 3, "acknowledgement": 4, "reply": 5,
    }
    base_width = {"far": 104, "mid": 132, "near": 148, "audit": 160}[grade]
    base_height = {"far": 44, "mid": 54, "near": 64, "audit": 72}[grade]
    exposition_height = 0 if exposition == "E0" else 16 + int(exposition[1:]) * 4

    def layout_for(viewport_class: str) -> dict[str, Any]:
        width = {"wide": 1200, "medium": 720, "narrow": 360}[viewport_class]
        object_geometry: list[dict[str, Any]] = []
        if viewport_class in {"narrow", "medium"}:
            row_gap = max(112, base_height + exposition_height + 48)
            edge_rows = max(1, len(display_edges))
            edge_gap = 60 if viewport_class == "medium" else 56
            height = max(640, 56 + max(len(display_objects) * row_gap, edge_rows * edge_gap))
        else:
            row_gap = 152 if viewport_class == "wide" else 140
            height = max(380, 216 + row_count * row_gap)
        for ordinal, item in enumerate(display_objects):
            focused = item["object_handle"] == layout_focus
            node_width = base_width + (36 if focused else 0)
            node_height = base_height + (20 + exposition_height if focused else 0)
            if viewport_class == "narrow":
                x = 16
                y = 28 + ordinal * row_gap
                node_width = min(198, node_width)
            elif viewport_class == "medium":
                x = 24
                y = 28 + ordinal * row_gap
                node_width = 300
                node_height = max(80 if item["kind"] == "compressed-group" else 72, node_height)
            else:
                margin_x = 62 if viewport_class == "wide" else 48
                stage_step = (width - margin_x * 2) // 5
                if item["kind"] == "compressed-group":
                    stage = 0 if item["cut"] == "UPSTREAM" else 5
                else:
                    stage = stages[item["kind"]]
                x = max(12, min(width - node_width - 12, margin_x + stage * stage_step - node_width // 2))
                recipient = item.get("recipient")
                if item["kind"] == "turn":
                    y = 112 + ((row_count - 1) * row_gap) // 2
                elif item["kind"] == "authority":
                    y = 36
                elif item["kind"] == "compressed-group":
                    y = 188 + (ordinal % row_count) * row_gap
                elif recipient:
                    y = 164 + row_by_recipient[recipient] * row_gap
                else:
                    y = 164 + (ordinal % row_count) * row_gap
            object_geometry.append(
                {
                    "object_handle": item["object_handle"],
                    "x": int(x), "y": int(y),
                    "width": int(node_width), "height": int(node_height),
                    "compressed": item["kind"] == "compressed-group",
                }
            )
        geometry_by_handle = {item["object_handle"]: item for item in object_geometry}
        edge_geometry: list[dict[str, Any]] = []
        for ordinal, item in enumerate(display_edges):
            source = geometry_by_handle[item["source_handle"]]
            target = geometry_by_handle[item["target_handle"]]
            source_point = [source["x"] + source["width"] // 2, source["y"] + source["height"] // 2]
            target_point = [target["x"] + target["width"] // 2, target["y"] + target["height"] // 2]
            if viewport_class == "narrow":
                spine_x = 220
                points = [source_point, [spine_x, source_point[1]], [spine_x, target_point[1]], target_point]
                control_x, control_y, control_width, control_height = 224, 18 + ordinal * 56, 124, 44
            elif viewport_class == "medium":
                spine_x = 348
                points = [source_point, [spine_x, source_point[1]], [spine_x, target_point[1]], target_point]
                control_x, control_y, control_width, control_height = 372, 18 + ordinal * 60, 324, 48
            else:
                midpoint_x = (source_point[0] + target_point[0]) // 2
                points = [source_point, [midpoint_x, source_point[1]], [midpoint_x, target_point[1]], target_point]
                control_width, control_height = 116, 44
                control_x = max(8, min(width - control_width - 8, midpoint_x - control_width // 2))
                control_y = max(8, min(source_point[1], target_point[1]) + 10 + (ordinal % 2) * 48)
            edge_geometry.append(
                {
                    "edge_id": item["edge_id"], "points": points,
                    "control_x": int(control_x), "control_y": int(control_y),
                    "control_width": int(control_width), "control_height": int(control_height),
                    "label_slot": True,
                }
            )
        return {"width": width, "height": int(height), "objects": object_geometry, "edges": edge_geometry}

    geometry = {name: layout_for(name) for name in ("wide", "medium", "narrow")}
    selected_viewport = {
        "compact": "narrow",
        "375": "narrow",
        "balanced": "medium",
        "768": "medium",
        "expansive": "wide",
        "1536": "wide",
        "default": "wide",
    }.get(viewport, "wide")
    selected_geometry = geometry[selected_viewport]
    endpoints = [
        {
            "edge_id": item["edge_id"],
            "source": {
                "x": item["points"][0][0],
                "y": item["points"][0][1],
            },
            "target": {
                "x": item["points"][-1][0],
                "y": item["points"][-1][1],
            },
        }
        for item in selected_geometry["edges"]
    ]
    options = {
        "engine": "native-integer",
        "version": _CONTINUITY_LAYOUT_VERSION,
        "viewport": viewport,
        "selected_viewport": selected_viewport,
        "focus_handle": focus_handle or None,
        "selected_edge_id": selected_edge or None,
        "selected_audit_subject": selected_audit_subject,
        "grade": grade,
        "exposition": exposition,
        "compression_receipt_handle": compression_receipt_handle,
    }
    receipt_preimage = {
        "schema_version": _CONTINUITY_LAYOUT_SCHEMA,
        "version": _CONTINUITY_LAYOUT_VERSION,
        "options": options,
        "canonical_order": canonical_order,
        "compression": coverage_preimage,
        "display_edges": display_edges,
        "geometry": geometry,
        "node_geometry": selected_geometry["objects"],
        "endpoint_geometry": endpoints,
    }
    receipt_handle = _json_digest(receipt_preimage)
    omission_residual = [
        {
            "class": item["class"],
            "state": str(item.get("evidence_state") or "BUDGET"),
            "count": int(item["count"]),
            "label": item["label"],
            "digest": item["digest"],
            "continuation": item.get("continuation"),
        }
        for item in compressed_groups
    ]
    return {
        "schema_version": _CONTINUITY_SCHEMA,
        "state": field.get("state", "UNKNOWN"),
        "objects": display_objects,
        "edges": display_edges,
        "canonical_objects": canonical_objects,
        "canonical_edges": canonical_edges,
        "ordered_visible_handles": display_order,
        "visible_original_handles": visible_original_handles,
        "omitted_object_handles": omitted_handles,
        "compressed_groups": compressed_groups,
        "cut_edges": cut_edges,
        "compression": {**coverage_preimage, "compression_receipt_handle": compression_receipt_handle},
        "omission_residual": omission_residual,
        "residuals": list(field.get("residuals", [])),
        "focus_handle": focus_handle or None,
        "focus_state": (
            "REFUSED"
            if requested_focus_invalid
            else ("EXACT" if focus_handle else "NONE")
        ),
        "selected_edge_id": selected_edge or None,
        "selected_audit_subject": selected_audit_subject,
        "edge_state": (
            "REFUSED"
            if requested_edge_invalid
            else ("EXACT" if selected_edge else "NONE")
        ),
        "grade": grade,
        "exposition": exposition,
        "geometry": geometry,
        "selected_viewport": selected_viewport,
        "layout_receipt": {**receipt_preimage, "layout_receipt_handle": receipt_handle},
        "layout_receipt_handle": receipt_handle,
        "projection_boundary": field.get("projection_boundary"),
        "conversation_shown_handle": field.get("conversation_shown_handle"),
        "authority_handle": field.get("authority_handle"),
        "read_only": True,
    }
def _residual_classes(
    source: Mapping[str, Any],
    *,
    residue_count: int,
    omission: Mapping[str, Any],
    authority_state: str,
    continuity_state: str,
) -> list[dict[str, Any]]:
    """Conserve all debt in the exact three Aisthesis residual classes."""

    omission_class = {
        "state": str(omission.get("status") or "UNKNOWN"),
        "omission": dict(omission),
        "review_residue_count": residue_count,
        "proof_boundary": source.get("proof_boundary"),
        "owner": "laplace.engine.development_work_map",
        "retirement_trigger": {
            "predicate": (
                "omitted_open_candidates == 0 and omitted_terminal_candidates == 0 "
                "and review_residue_count == 0"
            ),
            "evidence": "a CURRENT source-bound DevelopmentWorkMap projection",
        },
    }
    currentness_or_authority = {
        "state": (
            "CURRENT"
            if authority_state == "CURRENT"
            and str((source.get("freshness") or {}).get("state")) == "CURRENT"
            else "UNRESOLVED"
        ),
        "source_currentness": str((source.get("freshness") or {}).get("state") or "UNKNOWN"),
        "authority_state": authority_state,
        "owner": "laplace.aisthesis-read-model/1",
        "continuation": "rederive /front/development from the canonical projections",
        "retirement_trigger": {
            "predicate": (
                "the rederived shown preimage, source coordinate, binding generation and "
                "effective authority face all exactly equal the served values"
            ),
            "evidence": "laplace.development-lens-currentness/1 state CURRENT",
        },
    }
    crutch_ids = [
        "CR-AIS-STREAM-500MS",
        "CR-AIS-SHADOW-FOUR-PANE",
        "CR-AIS-CARRIER-HOST-ASSUMPTIONS",
    ]
    inherited = source.get("fidelity_boundary")
    if isinstance(inherited, Mapping) and inherited.get("crutch_id"):
        crutch_ids.append(str(inherited["crutch_id"]))
    crutches = {
        "state": "OPEN",
        "continuity_state": continuity_state,
        "owner": "Aisthesis",
        "continuation": "/front/serve",
        "items": [
            {
                "crutch_id": crutch_id,
                "owner": {
                    "CR-AIS-STREAM-500MS": "Aisthesis carrier + canonical stream owner",
                    "CR-AIS-SHADOW-FOUR-PANE": "Aisthesis carrier",
                    "CR-AIS-CARRIER-HOST-ASSUMPTIONS": "front-door carrier contract",
                    "CR-review-frontier-terminal-aggregate-without-authoritative-root": (
                        "DevelopmentWorkMap frontier owner"
                    ),
                }.get(crutch_id, "upstream evidence owner"),
                "retirement_trigger": {
                    "predicate": {
                        "CR-AIS-STREAM-500MS": (
                            "p95 affected-event-to-rederived-CURRENT latency < 250ms under an "
                            "adversarial rolled/skipped/reconnect-gap plant, with zero missed or "
                            "duplicated affected events"
                        ),
                        "CR-AIS-SHADOW-FOUR-PANE": (
                            "all seven cameras operate over one stable spatial causal field and "
                            "the frozen four-pane carrier is no longer reachable as current state"
                        ),
                        "CR-AIS-CARRIER-HOST-ASSUMPTIONS": (
                            "the carrier supplies exact host, viewport grade, reduced-motion and "
                            "grayscale facts in the shown-state preimage"
                        ),
                        "CR-review-frontier-terminal-aggregate-without-authoritative-root": (
                            "the adapter supplies a source-bound authoritative terminal-root proof"
                        ),
                    }.get(
                        crutch_id,
                        "the upstream owner supplies a measurable exact retirement proof",
                    ),
                    "comparison": "strict",
                },
            }
            for crutch_id in crutch_ids
        ],
    }
    return [
        {
            "class": "OMISSION",
            "digest": _json_digest(omission_class),
            **omission_class,
        },
        {
            "class": "CURRENTNESS_OR_AUTHORITY",
            "digest": _json_digest(currentness_or_authority),
            **currentness_or_authority,
        },
        {
            "class": "UNRESOLVED",
            "digest": _json_digest(crutches),
            **crutches,
        },
    ]


def _row_face(row: Mapping[str, Any]) -> dict[str, Any]:
    commission = row.get("commission") if isinstance(row.get("commission"), Mapping) else {}
    verdict = row.get("verdict") if isinstance(row.get("verdict"), Mapping) else {}
    candidate = (
        row.get("candidate_evidence")
        if isinstance(row.get("candidate_evidence"), Mapping)
        else {}
    )
    residue = row.get("review_residue") if isinstance(row.get("review_residue"), Mapping) else {}
    links = [
        {
            "role": str(link.get("role") or "source"),
            "kind": str(link.get("kind") or "unknown"),
            "reference": str(link.get("reference") or ""),
        }
        for link in row.get("source_links", [])
        if isinstance(link, Mapping) and link.get("reference")
    ]
    node_handle = str(row.get("node_handle") or "")
    publication = str(row.get("publication_state") or "UNKNOWN")
    state = str(row.get("state") or "UNKNOWN")
    message_type = str(commission.get("message_type") or "")
    cursor = commission.get("cursor")
    return {
        "node_handle": node_handle,
        "short_handle": _short(node_handle),
        "label": _human_type(message_type),
        "state": state,
        "publication_state": publication,
        "attention": publication != "CLOSED",
        "commission": {
            "message_id": commission.get("message_id"),
            "body_handle": commission.get("body_handle"),
            "cursor": cursor,
            "builder_seat": commission.get("builder_seat"),
            "reviewer_seat": commission.get("reviewer_seat"),
            "delivered": (commission.get("delivery") or {}).get("delivered"),
        },
        "candidate": {
            "status": candidate.get("status"),
            "relation_to_head": candidate.get("relation_to_head"),
            "reasons": list(candidate.get("reasons") or []),
        },
        "verdict": {
            "message_id": verdict.get("message_id"),
            "body_handle": verdict.get("body_handle"),
            "decision": verdict.get("decision"),
            "evidence_status": verdict.get("evidence_status"),
            "delivered": (verdict.get("delivery") or {}).get("delivered"),
        }
        if verdict
        else None,
        "review_residue_count": int(residue.get("count") or 0),
        "source_links": links,
        "reconstruct": (
            f"/usr/bin/python3 scripts/reconstruct_node.py '{commission.get('message_id')}'"
            if commission.get("message_id")
            else None
        ),
    }


def _weave_identity(kind: str, value: Any) -> str:
    return _json_digest(
        {
            "schema_version": "laplace.aisthesis-causal-atlas-weave-id/1",
            "kind": kind,
            "value": value,
        }
    )


def _causal_atlas_weave(
    *,
    source: Mapping[str, Any],
    rows: list[dict[str, Any]],
    continuity_field: Mapping[str, Any],
    authority: Mapping[str, Any],
    residual_classes: list[dict[str, Any]],
    focus: str,
    edge: str,
    grade: str,
    viewport: str,
) -> dict[str, Any]:
    """Build one deterministic focus+context field from admitted model evidence.

    This is a camera transform, not a second model.  Every object descends to an
    already-admitted row, Continuity object, binding or residual.  Compression is
    content-addressed and conserved before geometry is assigned.
    """

    freshness = source.get("freshness") if isinstance(source.get("freshness"), Mapping) else {}
    source_handle = str(freshness.get("source_handle") or _weave_identity("source", "unknown"))
    metrics = source.get("read_metrics") if isinstance(source.get("read_metrics"), Mapping) else {}
    root = {
        "object_handle": source_handle,
        "kind": "source",
        "family": "programme",
        "label": "Canonical review frontier",
        "state": str(source.get("status") or "UNKNOWN"),
        "summary": (
            f"{int(source.get('open_candidate_count') or 0)} open · "
            f"{int(metrics.get('terminal_rows_loaded') or 0)} recent proofs"
        ),
        "continuation": "/front/development?lens=lens-self",
        "receipt_ids": [source.get("head_event_id"), source.get("head_record_digest")],
    }
    active_goals_gap = {
        "object_handle": _weave_identity(
            "programme-coverage-gap",
            {
                "profile": "sha256:334df47357e4c82158063a3dda5a6c26703a08f33905567581381128011d8723",
                "goals": "sha256:2991526a880b125269e3f95c35e7013797d23a51ee3e8841c8e8f45653111818",
            },
        ),
        "kind": "omission",
        "family": "programme",
        "label": "Active seat goals not joined",
        "state": "UNKNOWN",
        "summary": "P0 · P1 · P2 sit outside this review-frontier projection",
        "member_count": 3,
        "omission_class": "COVERAGE",
        "continuation": "/front/development?lens=lens-self",
        "receipt_ids": [
            "sha256:334df47357e4c82158063a3dda5a6c26703a08f33905567581381128011d8723",
            "sha256:2991526a880b125269e3f95c35e7013797d23a51ee3e8841c8e8f45653111818",
        ],
    }
    objects: list[dict[str, Any]] = [root, active_goals_gap]
    for row in rows:
        objects.append(
            {
                "object_handle": row["node_handle"],
                "kind": "work",
                "family": "programme",
                "label": row["label"],
                "state": row["state"],
                "summary": row["publication_state"],
                "continuation": "/front/development?lens=evidence-descent&node="
                + row["node_handle"],
                "receipt_ids": [row["commission"].get("message_id")],
            }
        )
    for item in continuity_field.get("objects", []):
        if not isinstance(item, Mapping):
            continue
        objects.append(
            {
                "object_handle": str(item.get("object_handle")),
                "kind": str(item.get("kind") or "continuity"),
                "family": "continuity",
                "label": str(item.get("label") or "Conversation evidence"),
                "state": str(item.get("state") or "UNKNOWN"),
                "summary": str(item.get("summary") or item.get("meaning") or "Exact continuity evidence"),
                "continuation": "/front/development?lens=continuity&focus="
                + str(item.get("object_handle")),
                "receipt_ids": list(item.get("receipt_ids") or []),
            }
        )
    for seat in authority.get("seat_occupancy", []):
        if not isinstance(seat, Mapping):
            continue
        handle = _weave_identity(
            "authority",
            {
                "seat_id": seat.get("seat_id"),
                "binding_event_id": seat.get("binding_event_id"),
                "binding_generation": seat.get("binding_generation"),
            },
        )
        objects.append(
            {
                "object_handle": handle,
                "kind": "authority",
                "family": "authority",
                "label": str(seat.get("seat_id") or "unknown seat").replace("-seat", "").title()
                + " authority",
                "state": str(seat.get("state") or "UNKNOWN"),
                "summary": "routing authority" if seat.get("routing_authority") else "no routing authority",
                "continuation": "/front/development?lens=live-custody",
                "receipt_ids": [seat.get("binding_event_id"), seat.get("binding_generation")],
            }
        )
    residual_labels = {
        "OMISSION": "Conserved omissions",
        "CURRENTNESS_OR_AUTHORITY": "Currentness boundary",
        "UNRESOLVED": "Owned residuals",
    }
    for item in residual_classes:
        handle = _weave_identity("residual", {"class": item.get("class"), "digest": item.get("digest")})
        objects.append(
            {
                "object_handle": handle,
                "kind": "residual",
                "family": "residual",
                "label": residual_labels.get(str(item.get("class")), str(item.get("class") or "Residual")),
                "state": str(item.get("state") or "UNKNOWN"),
                "summary": str(item.get("continuation") or item.get("proof_boundary") or "Exact residual retained"),
                "continuation": "/front/development?lens=residual-crutch",
                "receipt_ids": [item.get("digest")],
            }
        )

    by_handle = {item["object_handle"]: item for item in objects}
    edges: list[dict[str, Any]] = []

    def add_edge(source_id: str, target_id: str, relation: str, state: str = "COMPLETE") -> None:
        if source_id not in by_handle or target_id not in by_handle or source_id == target_id:
            return
        identity = {"source": source_id, "target": target_id, "relation": relation}
        edges.append(
            {
                "edge_id": _weave_identity("edge", identity),
                "source_handle": source_id,
                "target_handle": target_id,
                "relation": relation,
                "state": state,
            }
        )

    for item in objects[1:]:
        relation = {
            "programme": "admits",
            "continuity": "continues through",
            "authority": "is governed by",
            "residual": "conserves",
        }.get(item["family"], "relates to")
        add_edge(root["object_handle"], item["object_handle"], relation, item["state"])
    for causal in continuity_field.get("edges", []):
        if isinstance(causal, Mapping):
            add_edge(
                str(causal.get("source_handle")),
                str(causal.get("target_handle")),
                str(causal.get("label") or causal.get("relation") or "causes"),
                str(causal.get("state") or causal.get("evidence_state") or "UNKNOWN"),
            )

    focus_state = "NONE"
    if focus:
        focus_state = "EXACT" if focus in by_handle else "REFUSED"
    selected_edge = next((item for item in edges if item["edge_id"] == edge), None) if edge else None
    edge_state = "EXACT" if selected_edge else ("REFUSED" if edge else "NONE")
    selected = focus if focus in by_handle else root["object_handle"]
    neighbours = {
        item["target_handle"] if item["source_handle"] == selected else item["source_handle"]
        for item in edges
        if selected in (item["source_handle"], item["target_handle"])
    }
    families = ("programme", "continuity", "authority", "residual")
    visible_handles: list[str]
    if grade == "far":
        visible_handles = [root["object_handle"]]
    elif grade == "mid":
        visible_handles = [root["object_handle"], active_goals_gap["object_handle"]]
        if selected != root["object_handle"]:
            visible_handles.append(selected)
            visible_handles.extend(sorted(neighbours)[:2])
    else:
        visible_handles = [item["object_handle"] for item in objects]
    visible_handles = list(dict.fromkeys(handle for handle in visible_handles if handle in by_handle))

    compressed_groups: list[dict[str, Any]] = []
    for family in families:
        members = [
            item["object_handle"]
            for item in objects
            if item["family"] == family and item["object_handle"] not in visible_handles
        ]
        if not members:
            continue
        states = sorted({by_handle[handle]["state"] for handle in members})
        group_handle = _weave_identity("group", {"family": family, "members": members})
        group = {
            "object_handle": group_handle,
            "kind": "compressed-group",
            "family": family,
            "label": {
                "programme": "Programme context",
                "continuity": "Conversation flow",
                "authority": "Authority field",
                "residual": "Residual horizon",
            }[family],
            "state": "REFUSED" if "REFUSED" in states else ("UNKNOWN" if "UNKNOWN" in states else "COMPLETE"),
            "summary": f"{len(members)} conserved · " + ", ".join(states),
            "member_count": len(members),
            "ordered_member_handles": members,
            "member_digest": _json_digest(members),
            "boundary_member": members[0],
            "continuation": {"focus_handle": members[0], "grade": "near"},
            "receipt_ids": [],
        }
        compressed_groups.append(group)
        by_handle[group_handle] = group
        visible_handles.append(group_handle)

    visible_objects = [by_handle[handle] for handle in visible_handles]
    visible_set = set(visible_handles)
    visible_edges = [
        item for item in edges if item["source_handle"] in visible_set and item["target_handle"] in visible_set
    ]
    for group in compressed_groups:
        add = {
            "edge_id": _weave_identity("cut-edge", {"root": root["object_handle"], "group": group["object_handle"]}),
            "source_handle": root["object_handle"],
            "target_handle": group["object_handle"],
            "relation": "compresses with exact continuation",
            "state": group["state"],
            "kind": "cut-edge",
        }
        visible_edges.append(add)

    viewport_kind = "narrow" if viewport == "compact" else ("medium" if viewport == "balanced" else "wide")
    width = {"wide": 1180, "medium": 820, "narrow": 350}[viewport_kind]
    node_width = {"wide": 210, "medium": 220, "narrow": 286}[viewport_kind]
    left = {"wide": 56, "medium": 42, "narrow": 24}[viewport_kind]
    columns = 3 if viewport_kind == "wide" else (2 if viewport_kind == "medium" else 1)
    usable_width = width - 2 * left
    cell_width = usable_width // columns
    geometry_objects = []
    for index, item in enumerate(visible_objects):
        if item["object_handle"] == selected:
            w, h = (300 if viewport_kind != "narrow" else 302), 112
        else:
            w, h = node_width, 76
        column = index % columns
        row_index = index // columns
        x = left + column * cell_width + (cell_width - w) // 2
        y = 54 + row_index * 166
        geometry_objects.append({"object_handle": item["object_handle"], "x": x, "y": y, "width": w, "height": h})
    geometry_by_handle = {item["object_handle"]: item for item in geometry_objects}
    geometry_edges = []
    for item in visible_edges:
        source_geometry = geometry_by_handle.get(item["source_handle"])
        target_geometry = geometry_by_handle.get(item["target_handle"])
        if not source_geometry or not target_geometry:
            continue
        sx = source_geometry["x"] + source_geometry["width"] // 2
        sy = source_geometry["y"] + source_geometry["height"]
        tx = target_geometry["x"] + target_geometry["width"] // 2
        ty = target_geometry["y"]
        geometry_edges.append(
            {
                "edge_id": item["edge_id"],
                "points": [[sx, sy], [sx, (sy + ty) // 2], [tx, (sy + ty) // 2], [tx, ty]],
                "label_x": (sx + tx) // 2,
                "label_y": (sy + ty) // 2,
            }
        )
    height = max([item["y"] + item["height"] for item in geometry_objects] + [320]) + 64
    layout_preimage = {
        "schema_version": "laplace.aisthesis-causal-atlas-layout/1",
        "version": "causal-atlas-weave-v1",
        "viewport": viewport_kind,
        "grade": grade,
        "focus_handle": selected,
        "selected_edge_id": selected_edge["edge_id"] if selected_edge else None,
        "objects": geometry_objects,
        "edges": geometry_edges,
        "groups": [
            {key: group[key] for key in ("object_handle", "ordered_member_handles", "member_digest", "boundary_member")}
            for group in compressed_groups
        ],
    }
    return {
        "schema_version": "laplace.aisthesis-causal-atlas-weave/1",
        "state": str(source.get("status") or "UNKNOWN"),
        "grade": grade,
        "viewport": viewport_kind,
        "focus_handle": selected,
        "focus_state": focus_state,
        "selected_edge_id": selected_edge["edge_id"] if selected_edge else None,
        "edge_state": edge_state,
        "objects": visible_objects,
        "edges": visible_edges,
        "compressed_groups": compressed_groups,
        "omitted_object_handles": [item["object_handle"] for item in objects if item["object_handle"] not in visible_set],
        "canonical_order": [item["object_handle"] for item in objects],
        "layout": {"width": width, "height": height, "objects": geometry_objects, "edges": geometry_edges},
        "layout_receipt_handle": _json_digest(layout_preimage),
        "selected_audit_subject": (
            f"edge:{selected_edge['edge_id']}" if selected_edge else f"object:{selected}"
        )
        if grade == "audit"
        else None,
        "read_only": True,
    }


def _shown_state(
    source: Mapping[str, Any],
    *,
    model_handle: str,
    lens_id: str,
    focus_handle: str | None,
    selected_edge_id: str | None,
    ordered_visible_handles: list[str],
    omitted_preimage: Mapping[str, Any],
    representation_grade: str,
    exposition: str,
    viewport: str,
    layout_receipt_handle: str | None,
    selected_audit_subject: str | None,
    git_head: str | None,
    acknowledgement: Mapping[str, Any],
    binding_generation: str | None,
    effective_authority_handle: str,
) -> dict[str, Any]:
    freshness = source.get("freshness") if isinstance(source.get("freshness"), Mapping) else {}
    coordinate = freshness.get("coordinate") if isinstance(freshness.get("coordinate"), Mapping) else {}
    omission = (
        source.get("omission_residual")
        if isinstance(source.get("omission_residual"), Mapping)
        else {"status": "UNKNOWN"}
    )
    visible_set_digest = _json_digest(ordered_visible_handles)
    omitted_set_digest = _json_digest(omitted_preimage)
    preimage = {
        "model_handle": model_handle,
        "lens_id": lens_id,
        "focus_handle": focus_handle,
        "selected_edge_id": selected_edge_id,
        "ordered_visible_handles": ordered_visible_handles,
        "visible_set_digest": visible_set_digest,
        "omitted_set_digest": omitted_set_digest,
        "representation_grade": representation_grade,
        "exposition": exposition,
        "viewport": viewport,
        "layout_receipt_handle": layout_receipt_handle,
        "selected_audit_subject": selected_audit_subject,
        "binding_generation": binding_generation,
        "effective_authority_handle": effective_authority_handle,
    }
    return {
        "schema_version": _SHOWN_SCHEMA,
        "lens_id": lens_id,
        "model_handle": model_handle,
        "focus_handle": focus_handle,
        "selected_edge_id": selected_edge_id,
        "ordered_visible_handles": ordered_visible_handles,
        "source_handle": freshness.get("source_handle"),
        "observed_cursor": source.get("caused_by_event_cursor", coordinate.get("event_cursor")),
        "head_event_id": source.get("head_event_id", coordinate.get("head_event_id")),
        "head_record_digest": source.get(
            "head_record_digest", coordinate.get("head_record_digest")
        ),
        "source_shown_handle": source.get("shown_handle"),
        "shown_handle": _json_digest(preimage),
        "digest_preimage": preimage,
        "visible_set_digest": visible_set_digest,
        "omitted_set_digest": omitted_set_digest,
        "representation_grade": representation_grade,
        "exposition": exposition,
        "viewport": viewport,
        "layout_receipt_handle": layout_receipt_handle,
        "selected_audit_subject": selected_audit_subject,
        "git_head": git_head,
        "freshness": {
            "state": freshness.get("state", source.get("status", "UNKNOWN")),
            "reason": source.get("reason"),
            "rederive_owner": "laplace.engine.wake.development_work_map_glow",
        },
        "omission_residual": omission,
        "authority": {
            "mode": "READ-ONLY",
            "source": "canonical DevelopmentWorkMap projection",
            "mutation_available": False,
            "binding_generation": binding_generation,
            "effective_authority_handle": effective_authority_handle,
        },
        "acknowledgement": dict(acknowledgement),
    }


def project(
    *,
    focus: str = "",
    edge: str = "",
    lens: str = "programme",
    viewport: str = "default",
    grade: str = "mid",
    exposition: str = "E0",
    candidate_cap: int = _DEFAULT_CAP,
    reader: Callable[[int], dict[str, Any]] | None = None,
    authority_reader: Callable[[], dict[str, Any]] | None = None,
    conversation_reader: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build seven pure camera transforms over one content-addressed read model."""

    source = (reader or _read_map)(candidate_cap)
    status = str(source.get("status") or "UNAVAILABLE")
    rows = [_row_face(row) for row in source.get("work", []) if isinstance(row, Mapping)]
    edges = _edge_faces(rows)
    open_rows = [row for row in rows if row["attention"]]
    metrics = source.get("read_metrics") if isinstance(source.get("read_metrics"), Mapping) else {}
    residue_count = int(metrics.get("review_residue_count") or 0)
    omission = source.get("omission_residual") or {"status": "UNKNOWN"}
    crutch = source.get("fidelity_boundary") or {}
    acknowledgement = _acknowledgement(source)
    critical = _critical_path(source, open_rows)
    use_live_joins = reader is None
    authority_capture = _capture_projection(
        authority_reader or (_read_authority if use_live_joins else None)
    )
    conversation_capture = _capture_projection(
        conversation_reader or (_read_conversation if use_live_joins else None),
        absent_exception="AuthorTurnAbsent",
    )
    authority = _authority_face(authority_capture, source)
    conversation = _conversation_face(conversation_capture)
    grade_state = "EXACT" if grade in _CONTINUITY_GRADES else "REFUSED"
    exposition_state = "EXACT" if exposition in _EXPOSITION_GRADES else "REFUSED"
    layout_grade = grade if grade_state == "EXACT" else "mid"
    layout_exposition = exposition if exposition_state == "EXACT" else "E0"
    continuity_field = _continuity_field(conversation, authority)
    residual_classes = _residual_classes(
        source,
        residue_count=residue_count,
        omission=omission,
        authority_state=authority["state"],
        continuity_state=conversation["state"],
    )

    selected = None
    focus_state = "DEFAULT"
    if focus:
        selected = next((row for row in rows if row["node_handle"] == focus), None)
        focus_state = "EXACT" if selected else "REFUSED"
    elif rows:
        selected = rows[-1]
    selected_edge = next((item for item in edges if item["edge_id"] == edge), None) if edge else None
    edge_state = "EXACT" if selected_edge else ("REFUSED" if edge else "NONE")

    continuity_loom = _continuity_layout(
        continuity_field,
        viewport=viewport,
        focus=focus,
        edge=edge,
        grade=layout_grade,
        exposition=layout_exposition,
    )
    if grade_state == "REFUSED" or exposition_state == "REFUSED":
        continuity_loom["state"] = "REFUSED"
        continuity_loom["reason"] = (
            "grade must be far|mid|near|audit and exposition must be E0|E1|E2|E3|E4|E5|E6|E7"
        )
    continuity_selected = next(
        (
            item
            for item in continuity_loom["objects"]
            if item["object_handle"] == continuity_loom["focus_handle"]
        ),
        None,
    )
    continuity_selected_edge = next(
        (
            item
            for item in continuity_loom["edges"]
            if item["edge_id"] == continuity_loom["selected_edge_id"]
        ),
        None,
    )

    all_handles = [row["node_handle"] for row in rows if row.get("node_handle")]
    critical_rows = (
        [
            next(row for row in open_rows if row["node_handle"] == handle)
            for handle in critical["ordered_handles"]
        ]
        if critical["state"] == "CURRENT"
        else []
    )
    selected_handles = [selected["node_handle"]] if selected else []
    logical_seats = [row["seat_id"] for row in authority["seat_occupancy"]]
    crutch_items = next(
        item["items"] for item in residual_classes if item["class"] == "UNRESOLVED"
    )
    git_head = _git_head()
    model_coordinate = {
        "source_handle": (source.get("freshness") or {}).get("source_handle"),
        "observed_cursor": source.get("caused_by_event_cursor"),
        "head_event_id": source.get("head_event_id"),
        "head_record_digest": source.get("head_record_digest"),
        "git_head": git_head,
    }
    model_handle = _json_digest(
        {
            "schema_version": _MODEL_SCHEMA,
            "canonical_adapter": "laplace.engine.wake.development_work_map_glow",
            "coordinate": model_coordinate,
            "objects": rows,
            "edges": edges,
            "projection_evidence": {
                "authority": authority,
                "conversation": conversation,
            },
            "continuity_field": continuity_field,
            "residual_classes": residual_classes,
            "acknowledgement": acknowledgement,
        }
    )
    causal_weave = _causal_atlas_weave(
        source=source,
        rows=rows,
        continuity_field=continuity_field,
        authority=authority,
        residual_classes=residual_classes,
        focus=focus if lens == "programme" else "",
        edge=edge if lens == "programme" else "",
        grade=layout_grade,
        viewport=viewport,
    )
    cameras = {
        "programme": {
            "state": status,
            "ordered_visible_handles": [
                item["object_handle"] for item in causal_weave["objects"]
            ],
            "objects": rows,
            "weave": causal_weave,
        },
        "critical-path": {
            **critical,
            "ordered_visible_handles": list(critical["ordered_handles"]),
            "objects": critical_rows,
        },
        "live-custody": {
            "state": authority["state"],
            "ordered_visible_handles": all_handles,
            "logical_seats": logical_seats,
            "bindings": authority["seat_occupancy"],
            "leases": authority["leases"],
            "binding_generation": authority["binding_generation"],
            "effective_authority": authority["effective_authority"],
            "effective_authority_handle": authority["effective_authority_handle"],
            "reason": authority["reason"],
        },
        "evidence-descent": {
            "state": focus_state,
            "ordered_visible_handles": selected_handles,
            "selected_object": selected,
            "selected_edge": selected_edge,
            "edge_state": edge_state,
        },
        "continuity": {
            **continuity_loom,
            "phases": (
                None
                if conversation["projection"] is None
                else conversation["projection"].get("recipient_states")
            ),
            "conversation_shown_handle": (
                None
                if conversation["projection"] is None
                else conversation["projection"].get("shown_handle")
            ),
            "author_lifecycle": (
                None
                if conversation["projection"] is None
                else conversation["projection"].get("author_lifecycle")
            ),
            "reason": conversation["reason"],
        },
        "residual-crutch": {
            "state": "OPEN" if residual_classes else "ZERO",
            "ordered_visible_handles": [],
            "classes": residual_classes,
        },
        "lens-self": {
            "state": "SUBORDINATE-CANDIDATE",
            "ordered_visible_handles": [],
            "model_handle": model_handle,
            "source_contract": "contract/surfaces/front.yaml",
            "implementation": "src/laplace/web/development_lens.py",
            "carrier": "src/laplace/web/development_lens.html",
            "owned_crutches": crutch_items,
            "self_acceptance_available": False,
        },
    }
    lens_state = "EXACT" if lens in cameras else "REFUSED"
    active_camera = cameras.get(lens) or {
        "state": "REFUSED",
        "ordered_visible_handles": [],
        "reason": f"unknown Aisthesis camera: {lens}",
    }
    if lens == "continuity" and continuity_loom["state"] == "REFUSED":
        active_camera["reason"] = continuity_loom.get("reason") or conversation.get("reason")
    ordered_visible_handles = list(active_camera["ordered_visible_handles"])
    if lens == "continuity":
        omitted_preimage = {
            "conversation_omission_groups": continuity_field["omission_groups"],
            "camera_omitted_handles": continuity_loom["omitted_object_handles"],
            "compressed_group_handles": [
                item["group_handle"] for item in continuity_loom["compressed_groups"]
            ],
            "compression": continuity_loom["compression"],
            "cut_edges": continuity_loom["cut_edges"],
            "continuity_residuals": continuity_field["residuals"],
        }
    elif lens == "programme":
        omitted_preimage = {
            "source_omission": omission,
            "camera_omitted_handles": causal_weave["omitted_object_handles"],
            "compressed_groups": [
                {
                    "group_handle": item["object_handle"],
                    "ordered_member_handles": item["ordered_member_handles"],
                    "member_digest": item["member_digest"],
                    "boundary_member": item["boundary_member"],
                }
                for item in causal_weave["compressed_groups"]
            ],
            "canonical_order": causal_weave["canonical_order"],
            "residual_class_digests": [item["digest"] for item in residual_classes],
        }
    else:
        omitted_preimage = {
            "source_omission": omission,
            "camera_omitted_handles": [
                handle for handle in all_handles if handle not in set(ordered_visible_handles)
            ],
            "critical_path": {
                "state": critical["state"],
                "selection_handle": critical["selection_handle"],
                "reason": critical["reason"],
            },
            "residual_class_digests": [item["digest"] for item in residual_classes],
        }
    representation_grade = layout_grade
    if status == "CURRENT" and (
        (
            continuity_loom["focus_state"] == "REFUSED"
            if lens == "continuity"
            else causal_weave["focus_state"] == "REFUSED"
            if lens == "programme"
            else focus_state == "REFUSED"
        )
        or (
            continuity_loom["edge_state"] == "REFUSED"
            if lens == "continuity"
            else causal_weave["edge_state"] == "REFUSED"
            if lens == "programme"
            else edge_state == "REFUSED"
        )
        or lens_state == "REFUSED"
        or authority["state"] == "REFUSED"
        or grade_state == "REFUSED"
        or exposition_state == "REFUSED"
        or (lens == "continuity" and continuity_loom["state"] == "REFUSED")
    ):
        status = "REFUSED"
    elif status == "CURRENT" and lens == "continuity" and continuity_loom["state"] == "UNKNOWN":
        status = "UNKNOWN"
    shown = _shown_state(
        source,
        model_handle=model_handle,
        lens_id=lens,
        focus_handle=(
            continuity_loom["focus_handle"]
            if lens == "continuity"
            else causal_weave["focus_handle"]
            if lens == "programme"
            else (selected["node_handle"] if selected else None)
        ),
        selected_edge_id=(
            continuity_loom["selected_edge_id"]
            if lens == "continuity"
            else causal_weave["selected_edge_id"]
            if lens == "programme"
            else (selected_edge["edge_id"] if selected_edge else None)
        ),
        ordered_visible_handles=ordered_visible_handles,
        omitted_preimage=omitted_preimage,
        representation_grade=representation_grade,
        exposition=layout_exposition,
        viewport=viewport,
        layout_receipt_handle=(
            continuity_loom["layout_receipt_handle"]
            if lens == "continuity"
            else causal_weave["layout_receipt_handle"]
            if lens == "programme"
            else None
        ),
        selected_audit_subject=(
            continuity_loom["selected_audit_subject"]
            if lens == "continuity"
            else causal_weave["selected_audit_subject"]
            if lens == "programme"
            else None
        ),
        git_head=git_head,
        acknowledgement=acknowledgement,
        binding_generation=authority["binding_generation"],
        effective_authority_handle=authority["effective_authority_handle"],
    )
    shown["freshness"]["state"] = status
    if status != "CURRENT" and not shown["freshness"].get("reason"):
        shown["freshness"]["reason"] = authority.get("reason")

    if status != "CURRENT":
        exists = "The canonical development map is unavailable. No empty-work claim is made."
        matters = "Currentness must be repaired before this surface can rank or summarize work."
        blocked = str(source.get("reason") or "The canonical adapter refused without a reason.")
        inspect_next = str(
            source.get("action") or "Repair the canonical projection, then rederive this lens."
        )
    else:
        open_count = int(source.get("open_candidate_count") or len(open_rows))
        terminal_count = int(metrics.get("terminal_rows_loaded") or (len(rows) - len(open_rows)))
        exists = f"{open_count} open review candidates · {terminal_count} bounded terminal proofs"
        matters = (
            "Open candidates are waiting on exact builder-reviewer closure."
            if open_count
            else "No open review candidate exists in this canonical map."
        )
        residual_parts = []
        if residue_count:
            residual_parts.append(f"{residue_count} review residue")
        omitted = int(omission.get("omitted_terminal_candidates") or 0)
        if omitted:
            residual_parts.append(f"{omitted} terminal proofs omitted by the explicit cap")
        if crutch:
            residual_parts.append("the terminal aggregate is still a named crutch")
        blocked = " · ".join(residual_parts) if residual_parts else "No bounded residual is present."
        if lens == "continuity" and continuity_selected:
            inspect_next = f"Descend visually into {continuity_selected['label']}."
        else:
            inspect_next = (
                f"Descend into {selected['label']} at {selected['short_handle']}."
                if selected
                else "There is no visible work row to descend into."
            )

    return {
        "schema_version": _MODEL_SCHEMA,
        "status": status,
        "read_only": True,
        "canonical_adapter": "laplace.engine.wake.development_work_map_glow",
        "model_handle": model_handle,
        "coordinate": model_coordinate,
        "objects": rows,
        "edges": edges,
        "projection_evidence_edges": [
            authority["evidence_edge"],
            conversation["evidence_edge"],
        ],
        "cameras": cameras,
        "active_camera": active_camera,
        "lens_state": lens_state,
        "selected_edge": (
            continuity_selected_edge if lens == "continuity" else selected_edge
        ),
        "edge_state": (
            continuity_loom["edge_state"] if lens == "continuity" else edge_state
        ),
        "shown_state": shown,
        "questions": {
            "exists": exists,
            "matters_now": matters,
            "blocked": blocked,
            "inspect_next": inspect_next,
        },
        "programme_field": rows,
        "causal_atlas_weave": causal_weave,
        "critical_path": critical_rows,
        "critical_path_state": critical["state"],
        "critical_path_omitted": (
            max(0, len(open_rows) - len(critical_rows))
            if critical["state"] == "CURRENT"
            else None
        ),
        "focus_state": (
            continuity_loom["focus_state"]
            if lens == "continuity"
            else causal_weave["focus_state"]
            if lens == "programme"
            else focus_state
        ),
        "requested_focus": focus or None,
        "selected": continuity_selected if lens == "continuity" else selected,
        "requested_grade": grade,
        "grade_state": grade_state,
        "requested_exposition": exposition,
        "exposition_state": exposition_state,
        "continuity_field": continuity_field,
        "residual": {
            "omission": omission,
            "review_residue_count": residue_count,
            "fidelity_boundary": crutch,
            "proof_boundary": source.get("proof_boundary"),
            "classes": residual_classes,
        },
        "source_projection": {
            "active_context": source.get("active_context"),
            "latest_work_state": source.get("latest_work_state"),
            "read_metrics": metrics,
            "parallel_posture": source.get("parallel_posture"),
            "seat_occupancy": source.get("seat_occupancy"),
            "authority_join": authority,
            "conversation_join": conversation,
        },
    }


def currentness(
    *,
    served_cursor: str,
    served_head_event_id: str,
    served_head_record_digest: str,
    served_source_handle: str,
    served_git_head: str,
    shown_handle: str,
    served_preimage: Mapping[str, Any],
    reader: Callable[[int], dict[str, Any]] | None = None,
    authority_reader: Callable[[], dict[str, Any]] | None = None,
    conversation_reader: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rederive the full selected model/shown preimage, never echo a submitted handle."""

    served_preimage = dict(served_preimage)
    malformed = [key for key in _SHOWN_PREIMAGE_KEYS if key not in served_preimage]
    if not isinstance(served_preimage.get("ordered_visible_handles"), list):
        malformed.append("ordered_visible_handles:not-a-list")
    if served_preimage.get("representation_grade") not in _CONTINUITY_GRADES:
        malformed.append("representation_grade:invalid")
    if served_preimage.get("exposition") not in _EXPOSITION_GRADES:
        malformed.append("exposition:invalid")
    lens = str(served_preimage.get("lens_id") or "")
    focus = str(served_preimage.get("focus_handle") or "")
    edge = str(served_preimage.get("selected_edge_id") or "")
    viewport = str(served_preimage.get("viewport") or "")
    grade = str(served_preimage.get("representation_grade") or "")
    exposition = str(served_preimage.get("exposition") or "")
    rederived = project(
        focus=focus,
        edge=edge,
        lens=lens,
        viewport=viewport,
        grade=grade,
        exposition=exposition,
        candidate_cap=_DEFAULT_CAP,
        reader=reader,
        authority_reader=authority_reader,
        conversation_reader=conversation_reader,
    )
    live_shown = rederived["shown_state"]
    live_preimage = dict(live_shown["digest_preimage"])
    live = {
        "cursor": str(live_shown.get("observed_cursor") or ""),
        "head_event_id": str(live_shown.get("head_event_id") or ""),
        "head_record_digest": str(live_shown.get("head_record_digest") or ""),
        "source_handle": str(live_shown.get("source_handle") or ""),
        "git_head": str(live_shown.get("git_head") or ""),
    }
    served = {
        "cursor": served_cursor,
        "head_event_id": served_head_event_id,
        "head_record_digest": served_head_record_digest,
        "source_handle": served_source_handle,
        "git_head": served_git_head,
    }
    moved = {
        key: {"served": served[key], "live": live[key]}
        for key in live
        if served[key] != live[key]
    }
    for key in _SHOWN_PREIMAGE_KEYS:
        if served_preimage.get(key) != live_preimage.get(key):
            moved[f"shown_preimage.{key}"] = {
                "served": served_preimage.get(key),
                "live": live_preimage.get(key),
            }
    served_digest_valid = (
        not malformed and _json_digest(served_preimage) == shown_handle
    )
    if not served_digest_valid:
        moved["shown_handle"] = {
            "served": shown_handle,
            "recomputed_from_served_preimage": (
                None if malformed else _json_digest(served_preimage)
            ),
            "live": live_shown["shown_handle"],
        }
    unavailable = rederived["status"] != "CURRENT"
    state = (
        "REFUSED"
        if unavailable or malformed or not served_digest_valid
        else ("STALE" if moved else "CURRENT")
    )
    reason = None
    if malformed:
        reason = "served shown preimage is malformed: " + ", ".join(malformed)
    elif not served_digest_valid:
        reason = "served shown handle does not bind its submitted preimage"
    elif unavailable:
        reason = str(
            live_shown.get("freshness", {}).get("reason")
            or "canonical rederivation refused"
        )
    return {
        "schema_version": "laplace.development-lens-currentness/1",
        "state": state,
        "actions_enabled": False,
        "shown_handle": live_shown["shown_handle"],
        "served_shown_handle": shown_handle,
        "served_preimage": served_preimage,
        "live_preimage": live_preimage,
        "served": served,
        "live": live,
        "moved": moved,
        "reason": reason,
        "continuation": "rederive /front/development" if state != "CURRENT" else None,
        "read_only": True,
    }


def census() -> dict[str, Any]:
    """A cheap grade-zero place face; no terminal Git candidates are loaded."""

    source = _read_map(1)
    status = str(source.get("status") or "UNAVAILABLE")
    open_count = source.get("open_candidate_count")
    return {
        "chips": [
            {"n": open_count, "unit": "open review candidates", "warn": bool(open_count)},
            {"n": status, "unit": "canonical map", "warn": status != "CURRENT"},
        ],
        "source": "laplace.engine.wake.development_work_map_glow(candidate_cap=1)",
        "freshness": "live" if status == "CURRENT" else "unknown",
        "cracked": status != "CURRENT",
        "error": source.get("reason") if status != "CURRENT" else None,
    }


def handle(query: Mapping[str, Any]) -> tuple[int, str, bytes]:
    """Serve one page, its canonical projection, or its currentness comparison."""

    format_ = _q1(query, "format")
    if format_ == "json":
        focus = _q1(query, "focus")
        payload = project(
            focus=focus,
            edge=_q1(query, "edge"),
            lens=_q1(query, "lens", "programme"),
            viewport=_q1(query, "viewport", "default"),
            grade=_q1(query, "grade", "mid"),
            exposition=_q1(query, "exposition", "E0"),
        )
        status = 200 if payload["status"] == "CURRENT" else 503
        return status, _JSON, json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if format_ == "currentness":
        served_preimage = {
            "model_handle": _q1(query, "model_handle"),
            "lens_id": _q1(query, "lens"),
            "focus_handle": _optional_q(query, "focus"),
            "selected_edge_id": _optional_q(query, "edge"),
            "ordered_visible_handles": _json_string_list_q(query, "visible_handles"),
            "visible_set_digest": _q1(query, "visible_set_digest"),
            "omitted_set_digest": _q1(query, "omitted_set_digest"),
            "representation_grade": _q1(query, "grade"),
            "exposition": _q1(query, "exposition"),
            "viewport": _q1(query, "viewport"),
            "layout_receipt_handle": _optional_q(query, "layout_receipt_handle"),
            "selected_audit_subject": _optional_q(query, "audit_subject"),
            "binding_generation": _optional_q(query, "binding_generation"),
            "effective_authority_handle": _q1(query, "effective_authority_handle"),
        }
        payload = currentness(
            served_cursor=_q1(query, "cursor"),
            served_head_event_id=_q1(query, "head_event_id"),
            served_head_record_digest=_q1(query, "head_record_digest"),
            served_source_handle=_q1(query, "source_handle"),
            served_git_head=_q1(query, "git_head"),
            shown_handle=_q1(query, "shown_handle"),
            served_preimage=served_preimage,
        )
        return 200, _JSON, json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        return 200, _HTML, _PAGE.read_bytes()
    except OSError as exc:
        return 500, _JSON, json.dumps({"error": f"development lens missing: {exc}"}).encode()
