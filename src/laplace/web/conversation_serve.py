"""Conjugate conversation projection over author turns, Atlas truth and blueprint routes.

The talk row is the durable saga root.  Atlas is the sole delivery/reconstruction truth and the
self-hosted blueprint store is the sole source of design generations and spectral routes.  This
module joins those reads into one bounded author serve; it owns no cursor, lease or message state.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from laplace.representation.attention import project_attention_from_state

CONVERSATION_SERVE_SCHEMA = "laplace.conversation-serve/1"
AUTHOR_TURN_SCHEMA = "laplace.author-turn/1"


class AuthorTurnAbsent(LookupError):
    """The requested durable conversation root does not exist."""


class AuthorTurnCustodyMismatch(ValueError):
    """Supplied custody bytes do not reconstruct the requested author turn exactly."""


_BROKER_STATE: dict[str, Any] = {
    "status": "NOT_STARTED",
    "last_round": None,
    "last_round_at": None,
    "last_error": None,
}

_PHASE_RANK = {
    "banked-not-routed": 0,
    "routed": 1,
    "received": 2,
    "reconstructed": 3,
    "replied": 4,
    "closed": 5,
}


def canonical_handle(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def canonical_bytes(value: object) -> bytes:
    """Return the one byte representation whose digest is used by this projection."""

    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return canonical.encode("utf-8")


def turn_handle(row: Mapping[str, Any]) -> str:
    """Bind the exact banked author row; changing its handle changes the conversation."""

    return canonical_handle({"schema_version": AUTHOR_TURN_SCHEMA, "row": dict(row)})


def resolve_audience(
    provider_state: Mapping[str, Any], requested: str | Sequence[str]
) -> tuple[str, tuple[str, ...]]:
    """Resolve an author audience to live logical seats, never provider session addresses."""

    seats = provider_state.get("seats", {})
    if isinstance(requested, str):
        names = tuple(item.strip() for item in requested.split(",") if item.strip())
    else:
        names = tuple(str(item).strip() for item in requested if str(item).strip())
    names = names or ("eigen",)
    lowered = {item.lower() for item in names}
    if lowered & {"eigen", "both"}:
        recipients = tuple(sorted(
            seat_id
            for seat_id, seat in seats.items()
            if seat.get("role") == "provider" and seat.get("status") == "active"
        ))
        return "eigen", recipients
    aliases = {
        "ego": "ego-seat",
        "author": "gerard-seat",
        "sensorium": "sensorium-seat",
    }
    resolved = []
    for name in names:
        seat_id = aliases.get(name.lower(), name)
        seat = seats.get(seat_id)
        if seat is not None and seat.get("status") == "active":
            resolved.append(seat_id)
    return "+".join(names), tuple(dict.fromkeys(resolved))


def route_author_turn(
    author_turn: Mapping[str, Any], *, only_recipients: Sequence[str] | None = None,
    retry_generation_by_recipient: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Actuate the replayable fan-out saga through Atlas's one write boundary."""

    from datetime import datetime, timedelta, timezone

    from laplace.representation import atlas_bridge

    turn = turn_handle(author_turn)
    custody_handle = atlas_bridge.put_custody(canonical_bytes({
        "schema_version": AUTHOR_TURN_SCHEMA,
        "row": dict(author_turn),
    }))
    if custody_handle != turn:
        raise RuntimeError("author-turn custody handle disagrees with the minted turn handle")
    try:
        blueprint_generation = atlas_bridge.blueprint_projection(
            materialization_limit=0
        )["generation_id"]
    except Exception:  # stale blueprint is a serve red, not permission to lose conversation
        blueprint_generation = None
    expires_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    routed, failed = [], []
    intended = tuple(str(item) for item in author_turn.get("recipient_seat_ids", ()))
    recipients = intended if only_recipients is None else tuple(
        seat_id for seat_id in intended if seat_id in {str(item) for item in only_recipients}
    )
    retry_generation_by_recipient = retry_generation_by_recipient or {}
    for seat_id in recipients:
        roots = {"author_turn": turn}
        retry_generation = max(0, int(retry_generation_by_recipient.get(seat_id, 0)))
        if retry_generation:
            roots["fanout_generation"] = str(retry_generation)
        if blueprint_generation is not None:
            roots["blueprint_generation"] = str(blueprint_generation)
        try:
            sent = atlas_bridge.send(
                sender_seat_id="gerard-seat",
                recipient_seat_id=seat_id,
                message_type="conversation-turn",
                body=str(author_turn["text"]),
                dependency_roots=roots,
                idempotency_key=(
                    f"front-talk:{turn}:{seat_id}"
                    + (f":retry-{retry_generation}" if retry_generation else "")
                ),
                expires_at=expires_at,
                provider="front-door",
                model="author-relay",
            )
            routed.append({
                "recipient": seat_id,
                "message_id": sent["message_id"],
                "idempotent": bool(sent.get("idempotent")),
            })
        except Exception as exc:  # noqa: BLE001 — partial fan-out remains an explicit saga red
            failed.append({"recipient": seat_id, "error": f"{type(exc).__name__}: {exc}"})
    return {
        "turn_handle": turn,
        "routed": routed,
        "failed": failed,
        "complete": len(routed) == len(recipients),
    }


def broker_round() -> dict[str, Any]:
    """Repair every banked-not-routed author turn idempotently from the durable outbox."""

    from laplace.representation import atlas_bridge
    from laplace.engine import rows

    provider = atlas_bridge.snapshot()["provider"]
    fanout: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for raw in provider.get("messages", {}).values():
        message = raw.get("message", {})
        turn = message.get("dependency_roots", {}).get("author_turn")
        if message.get("sender_seat_id") != "gerard-seat" or not turn:
            continue
        key = (str(turn), str(message.get("recipient_seat_id")))
        fanout.setdefault(key, []).append(raw)
    examined = repaired = 0
    failures: list[dict[str, Any]] = []
    for _offset, row in rows.scan("talk"):
        if row.get("schema_version") != AUTHOR_TURN_SCHEMA or row.get("record") != "talk":
            continue
        examined += 1
        turn = turn_handle(row)
        missing = []
        retry_generations: dict[str, int] = {}
        for raw_seat_id in row.get("recipient_seat_ids", ()):
            seat_id = str(raw_seat_id)
            attempts = fanout.get((turn, seat_id), [])
            live = [raw for raw in attempts if raw.get("status") not in {"expired", "refused"}]
            if not live:
                missing.append(seat_id)
                retry_generations[seat_id] = len(attempts)
        if not missing:
            continue
        result = route_author_turn(
            row,
            only_recipients=missing,
            retry_generation_by_recipient=retry_generations,
        )
        repaired += len(result["routed"])
        failures.extend(result["failed"])
    return {
        "schema_version": "laplace.conversation-broker-round/1",
        "examined_turns": examined,
        "routed_messages": repaired,
        "failures": failures,
        "complete": not failures,
    }


def broker_projection() -> dict[str, Any]:
    """Expose bounded process health; this adapter state makes no delivery claim."""

    return {
        "schema_version": "laplace.conversation-broker/1",
        **_BROKER_STATE,
        "read_only": True,
        "message_cursor_owner": "Atlas seat fabric",
    }


def _broker_frontier() -> tuple[tuple[int, int], tuple[int, int]]:
    """Return a cheap change frontier without replaying Atlas or scanning the talk store."""

    from laplace.representation import atlas_bridge
    from laplace.engine import sources

    talk_spec = sources.get("talk") or {}
    atlas_path = atlas_bridge.store_root() / "conceptric.sqlite3"

    def stamp(path: object) -> tuple[int, int]:
        try:
            stat = Path(str(path)).stat()
            return stat.st_mtime_ns, stat.st_size
        except OSError:
            return 0, 0

    return stamp(talk_spec.get("abspath")), stamp(atlas_path)


def run_broker(*, interval_seconds: float = 2.0, idle_seconds: float = 30.0) -> None:
    """Repair after the causal frontier moves; never replay Atlas on a wall-clock tick."""

    observed = None
    delay = max(0.25, float(interval_seconds))
    while True:
        frontier = _broker_frontier()
        if frontier == observed:
            delay = min(
                max(delay * 2.0, float(interval_seconds)),
                max(float(idle_seconds), float(interval_seconds)),
            )
            time.sleep(delay)
            continue
        try:
            result = broker_round()
            observed = _broker_frontier()
            delay = max(0.25, float(interval_seconds))
            _BROKER_STATE.update({
                "status": "ACTIVE",
                "last_round": result,
                "last_round_at": time.time(),
                "last_error": None,
            })
        except Exception as exc:  # noqa: BLE001
            # Atlas unavailability must not kill the face.  The serve carries the red and the
            # next bounded round retries from the same durable author row.
            _BROKER_STATE.update({
                "status": "DEGRADED",
                "last_round_at": time.time(),
                "last_error": f"{type(exc).__name__}: {exc}",
            })
            delay = min(
                max(delay * 2.0, float(interval_seconds)),
                max(float(idle_seconds), float(interval_seconds)),
            )
        time.sleep(delay)


def _proofs_by_message(state: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    proofs: dict[str, dict[str, Any]] = {}
    for event_id, row in state.get("reconstruction_proofs", {}).items():
        evaluation = row.get("evaluation", {})
        message_id = evaluation.get("arguments", {}).get("message_id")
        if message_id:
            proofs[str(message_id)] = {
                "event_id": str(event_id),
                "handle": next(iter(evaluation.get("output_handles", ())), None),
                "goal": evaluation.get("arguments", {}).get("goal"),
            }
    return proofs


def _turn_messages(
    state: Mapping[str, Any], author_turn_handle: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    outbound: list[dict[str, Any]] = []
    replies: list[dict[str, Any]] = []
    for raw in state.get("messages", {}).values():
        message = raw.get("message", {})
        if message.get("dependency_roots", {}).get("author_turn") != author_turn_handle:
            continue
        item = dict(raw)
        if message.get("sender_seat_id") == "gerard-seat":
            outbound.append(item)
        elif message.get("recipient_seat_id") == "gerard-seat":
            replies.append(item)
    outbound.sort(key=lambda row: int(row["message"].get("cursor", 0)))
    replies.sort(key=lambda row: int(row["message"].get("cursor", 0)))
    return outbound, replies


def _recipient_phase(
    raw: Mapping[str, Any] | None,
    proof: Mapping[str, Any] | None,
    replies: Sequence[Mapping[str, Any]],
) -> str:
    if raw is None:
        return "banked-not-routed"
    status = str(raw.get("status") or "")
    if status in {"queued", "expired", "refused"}:
        return "routed" if status == "queued" else "banked-not-routed"
    message_id = raw.get("message", {}).get("message_id")
    if raw.get("acknowledgement_event_id") and raw.get("delivered"):
        return "closed"
    if any(
        reply.get("message", {}).get("sender_seat_id")
        == raw.get("message", {}).get("recipient_seat_id")
        and reply.get("message", {}).get("dependency_roots", {}).get("in_reply_to")
        == message_id
        for reply in replies
    ):
        return "replied"
    if proof is not None:
        return "reconstructed"
    if raw.get("last_pull_event_id") or status == "pulled":
        return "received"
    return "routed"


def _author_label(seat_id: str, index: int) -> str:
    labels = {
        "ego-seat": "Ego",
        "sensorium-seat": "Sensorium",
        "codex-seat": "builder",
        "claude-seat": "other-self",
    }
    return labels.get(seat_id, f"reader {index + 1}")


_ROUTE_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from", "how",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "what", "with",
}

_HISTORICAL_ROUTE_LIMIT = 3
_HISTORICAL_ROUTE_MIN_OVERLAP = 2
_HISTORICAL_ROUTE_MIN_SHORTER_COVERAGE = 0.5


def _route_terms(value: object) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", str(value).lower())
        if len(token) > 2 and token not in _ROUTE_STOP
    }


def _select_blueprint_routes(
    author_turn: Mapping[str, Any], blueprint: Mapping[str, Any], *,
    limit: int | None = _HISTORICAL_ROUTE_LIMIT,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Select turn-coupled routes and return the bounded selection residue.

    New turns carry an explicit write-time binding, including an explicitly empty one.  Only
    rows minted before that field existed use lexical recovery.  That recovery requires both
    two distinct terms and majority coverage of the shorter term set: a single common word is
    never enough to move the shown identity.  Its cap is a priced residue, not a silent slice.
    """

    has_explicit_binding = "blueprint_materialization_ids" in author_turn
    explicit = {
        str(item) for item in author_turn.get("blueprint_materialization_ids", ()) if item
    }
    query = _route_terms(" ".join((
        str(author_turn.get("text", "")),
        str(author_turn.get("decision", "")),
        str(author_turn.get("audience", author_turn.get("to", ""))),
    )))
    ranked: list[tuple[float, int, str, dict[str, Any]]] = []
    for route in blueprint.get("current_materializations", ()):
        route_id = str(route.get("materialization_id", ""))
        if has_explicit_binding:
            if route_id in explicit:
                ranked.append((1.0, 1_000_000, route_id, dict(route)))
            continue
        # A fibre is jurisdiction, not evidence that a route answers this turn.  Every route in a
        # jurisdiction shares those tokens, so admitting them here makes the shown frontier
        # fibre-wide.  Historical fallback is deliberately the narrower route-goal overlap only.
        route_terms = _route_terms(route.get("goal", ""))
        overlap = len(query & route_terms)
        shorter = min(len(query), len(route_terms))
        shorter_coverage = (overlap / shorter) if shorter else 0.0
        if (
            overlap >= _HISTORICAL_ROUTE_MIN_OVERLAP
            and shorter_coverage >= _HISTORICAL_ROUTE_MIN_SHORTER_COVERAGE
        ):
            ranked.append((shorter_coverage, overlap, route_id, dict(route)))
    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    selected_count = len(ranked) if has_explicit_binding or limit is None else max(
        0, min(len(ranked), int(limit))
    )
    selected = [route for _coverage, _overlap, _route_id, route in ranked[:selected_count]]
    omitted_ids = [route_id for _coverage, _overlap, route_id, _route in ranked[selected_count:]]
    missing_explicit = sorted(explicit - {
        str(route.get("materialization_id", "")) for route in selected
    }) if has_explicit_binding else []
    return selected, {
        "mode": "explicit" if has_explicit_binding else "historical-lexical-v2",
        "eligible_count": len(ranked),
        "selected_count": len(selected),
        "omitted_count": len(omitted_ids),
        "omitted_handle": canonical_handle(omitted_ids) if omitted_ids else None,
        "missing_explicit_count": len(missing_explicit),
        "missing_explicit_handle": (
            canonical_handle(missing_explicit) if missing_explicit else None
        ),
    }


def bind_blueprint_routes(
    author_turn: Mapping[str, Any], blueprint: Mapping[str, Any], *,
    limit: int = _HISTORICAL_ROUTE_LIMIT,
) -> dict[str, Any]:
    """Mint the explicit, bounded route binding stored with a new author turn."""

    routes, residue = _select_blueprint_routes(author_turn, blueprint, limit=limit)
    return {
        "schema_version": "laplace.blueprint-route-binding/1",
        "generation_id": blueprint.get("generation_id"),
        "policy": "goal-overlap-v2",
        "selected_ids": [str(route.get("materialization_id", "")) for route in routes],
        **residue,
    }


def materialize_conversation_serve(
    author_turn: Mapping[str, Any],
    provider_state: Mapping[str, Any],
    blueprint: Mapping[str, Any],
    *,
    watcher_by_seat: Mapping[str, Mapping[str, Any]] | None = None,
    author_turn_custody_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Purely join one exact author turn to recipient and blueprint read state.

    Custody is evidence supplied by the caller, never something a read projection repairs.
    Its exactness is reported outside the shown preimage.  Missing custody is readable but
    becomes a visible, hashed omission; mismatching bytes refuse the projection.
    """

    if int(blueprint.get("omitted_materializations", 0)) or any(
        int(route.get("omitted_results", 0))
        for route in blueprint.get("current_materializations", ())
    ):
        raise ValueError(
            "conversation serve identity requires the complete blueprint route frontier"
        )

    expected_turn_bytes = canonical_bytes({
        "schema_version": AUTHOR_TURN_SCHEMA,
        "row": dict(author_turn),
    })
    turn = "sha256:" + hashlib.sha256(expected_turn_bytes).hexdigest()
    custody_exact = author_turn_custody_bytes is not None
    if custody_exact:
        supplied_turn_bytes = bytes(author_turn_custody_bytes)
        if supplied_turn_bytes != expected_turn_bytes:
            actual = "sha256:" + hashlib.sha256(supplied_turn_bytes).hexdigest()
            raise AuthorTurnCustodyMismatch(
                "author-turn custody bytes disagree with the requested turn "
                f"(expected {turn}, actual {actual})"
            )
    stored_recipients = tuple(str(item) for item in author_turn.get("recipient_seat_ids", ()))
    audience_address = str(author_turn.get("audience", author_turn.get("to", "eigen")))
    if stored_recipients:
        recipients = stored_recipients
    else:
        _name, recipients = resolve_audience(provider_state, audience_address)
    audience_name = audience_address
    if "-seat" in audience_address:
        audience_name = "+".join(
            _author_label(seat_id, index) for index, seat_id in enumerate(recipients)
        ) or "specific reader"
    outbound, replies = _turn_messages(provider_state, turn)
    outbound_by_recipient: dict[str, list[dict[str, Any]]] = {}
    for row in outbound:
        seat_id = str(row.get("message", {}).get("recipient_seat_id"))
        outbound_by_recipient.setdefault(seat_id, []).append(row)
    proofs = _proofs_by_message(provider_state)
    watcher_by_seat = watcher_by_seat or {}
    recipient_rows = []
    dependency_frontier: dict[str, str] = {
        "author_turn": turn,
        "blueprint_generation": str(blueprint["generation_id"]),
    }
    omissions: list[dict[str, Any]] = []
    if not custody_exact:
        custody_omission = {
            "class": "author-turn-custody-absent",
            "boundary": "author turn",
            "cost": (
                "the exact author-turn bytes are not in the supplied custody read; "
                "this serve remains readable but cannot be acknowledged"
            ),
            "expected_handle": turn,
            "descend": turn,
        }
        custody_omission["omission_handle"] = canonical_handle(custody_omission)
        omissions.append(custody_omission)
    phases = []
    for index, seat_id in enumerate(recipients):
        attempts = outbound_by_recipient.get(seat_id, [])
        ranked_attempts = []
        for attempt in attempts:
            candidate_id = str(attempt.get("message", {}).get("message_id"))
            candidate_proof = proofs.get(candidate_id)
            candidate_phase = _recipient_phase(attempt, candidate_proof, replies)
            ranked_attempts.append((
                _PHASE_RANK[candidate_phase],
                int(attempt.get("message", {}).get("cursor", 0)),
                attempt,
            ))
        raw = max(ranked_attempts, default=(0, 0, None), key=lambda item: (item[0], item[1]))[2]
        message = {} if raw is None else raw.get("message", {})
        message_id = None if raw is None else str(message.get("message_id"))
        proof = None if message_id is None else proofs.get(message_id)
        phase = _recipient_phase(raw, proof, replies)
        phases.append(phase)
        if len(attempts) > 1:
            omitted_ids = sorted(
                str(item.get("message", {}).get("message_id"))
                for item in attempts if item is not raw
            )
            omissions.append({
                "class": "duplicate-fanout",
                "boundary": _author_label(seat_id, index),
                "cost": f"{len(omitted_ids)} superseded delivery attempt(s) are not shown",
                "descend": omitted_ids,
            })
        attention = project_attention_from_state(
            provider_state,
            seat_id=seat_id,
            watcher=watcher_by_seat.get(seat_id, {}),
            message_cap=4,
        )
        pending_ids = {
            str(item.get("message_id")) for item in attention.get("pending", ())
        }
        if raw is None:
            omissions.append({
                "class": "recipient-not-routed",
                "boundary": _author_label(seat_id, index),
                "cost": "the intended reader has no causally rooted Atlas message",
                "descend": None,
            })
        elif raw.get("status") in {"queued", "pulled"}:
            cost = (
                "the turn has not yet reached this reader"
                if raw.get("status") == "queued"
                else "the turn reached this reader but has not been reconstructed"
            )
            omissions.append({
                "class": "delivery-incomplete",
                "boundary": _author_label(seat_id, index),
                "cost": cost,
                "descend": message_id,
            })
        elif raw.get("status") in {"refused", "expired"}:
            omissions.append({
                "class": f"delivery-{raw.get('status')}",
                "boundary": _author_label(seat_id, index),
                "cost": "this recipient did not accept the turn",
                "descend": message_id,
            })
        if message_id is not None:
            dependency_frontier[f"message:{seat_id}"] = str(raw["sent_event_id"])
            if raw.get("last_pull_event_id"):
                dependency_frontier[f"received:{seat_id}"] = str(raw["last_pull_event_id"])
            if proof is not None:
                dependency_frontier[f"reconstruction:{seat_id}"] = str(proof["event_id"])
            if raw.get("acknowledgement_event_id"):
                dependency_frontier[f"ack:{seat_id}"] = str(
                    raw["acknowledgement_event_id"]
                )
        for attempt in attempts:
            attempt_message = attempt.get("message", {})
            attempt_id = str(attempt_message.get("message_id"))
            if attempt is not raw:
                dependency_frontier[f"message:{seat_id}:{attempt_id}"] = str(
                    attempt.get("sent_event_id")
                )
        recipient_rows.append({
            "logical_recipient": _author_label(seat_id, index),
            "diagnostic_seat_id": seat_id,
            "phase": phase,
            "recipient_message_id": message_id,
            "transport_state": None if raw is None else raw.get("status"),
            "received_event": None if raw is None else raw.get("last_pull_event_id"),
            "reconstruction_event": None if proof is None else proof.get("event_id"),
            "reconstruction_handle": None if proof is None else proof.get("handle"),
            "ack_event": None if raw is None else raw.get("acknowledgement_event_id"),
            "delivered": False if raw is None else bool(raw.get("delivered")),
            "attention": {
                "epoch_handle": attention["epoch_handle"],
                "posture": attention["posture"],
                "this_turn_pending": message_id in pending_ids,
                "other_pending_count": max(
                    0, int(attention["pending_count"]) - int(message_id in pending_ids)
                ),
            },
        })

    if not recipients:
        phases.append("banked-not-routed")
        omissions.append({
            "class": "audience-unresolved",
            "boundary": audience_name,
            "cost": "the author turn is banked but no live logical seat resolved",
            "descend": None,
        })
    for reply in replies:
        message = reply.get("message", {})
        event_id = str(reply.get("sent_event_id"))
        dependency_frontier[f"reply:{message.get('message_id')}"] = event_id
    omissions.extend((
        {
            "class": "bodies-omitted",
            "boundary": "fabric messages",
            "cost": "exact bodies are grade descent, not default inbox content",
            "descend": "/front/serve/body?message=<message-id>",
        },
        {
            "class": "lease-details-omitted",
            "boundary": "logical recipients",
            "cost": "provider tasks, PIDs and resume addresses are diagnostic transport only",
            "descend": "/front/serve?diagnostic=1",
        },
        {
            "class": "split-substrate",
            "boundary": "conversation and blueprint",
            "cost": "the projection is joined, but talk, fabric and blueprint do not yet share one atomic append door",
            "descend": None,
        },
    ))
    aggregate_phase = min(phases, key=lambda phase: _PHASE_RANK[phase])
    serve_id = "serve:" + canonical_handle({
        "schema_version": CONVERSATION_SERVE_SCHEMA,
        "turn_handle": turn,
        "audience": audience_name,
        "recipients": list(recipients),
        "decision": author_turn.get("decision"),
    }).split(":", 1)[-1]
    blueprint_routes, route_selection = _select_blueprint_routes(author_turn, blueprint)
    minted_binding = author_turn.get("blueprint_route_binding")
    if route_selection["mode"] == "historical-lexical-v2":
        omissions.append({
            "class": "historical-route-selection",
            "boundary": "blueprint materializations",
            "cost": (
                f"this pre-binding turn uses bounded lexical route admission; "
                f"{route_selection['omitted_count']} coupled route(s) are outside the cap"
                if blueprint_routes
                else "this pre-binding turn has no coupled blueprint route"
            ),
            **route_selection,
            "descend": [
                route.get("materialization_id") for route in blueprint_routes
            ],
        })
    elif isinstance(minted_binding, Mapping):
        omitted_count = int(minted_binding.get("omitted_count", 0))
        omissions.append({
            "class": "mint-route-selection",
            "boundary": "blueprint materializations at author-turn mint",
            "cost": (
                f"{omitted_count} coupled route(s) were represented by the binding residue"
                if omitted_count
                else "the complete coupled route set fitted the mint-time cap"
            ),
            "selected_count": int(minted_binding.get("selected_count", len(blueprint_routes))),
            "eligible_count": int(minted_binding.get("eligible_count", len(blueprint_routes))),
            "omitted_count": omitted_count,
            "omitted_handle": minted_binding.get("omitted_handle"),
            "descend": list(minted_binding.get("selected_ids", ())),
        })
    if route_selection["missing_explicit_count"]:
        omissions.append({
            "class": "bound-route-not-current",
            "boundary": "blueprint materializations",
            "cost": (
                f"{route_selection['missing_explicit_count']} explicitly bound route(s) are "
                "not current in this generation"
            ),
            "omitted_handle": route_selection["missing_explicit_handle"],
            "descend": author_turn.get("blueprint_generation_id"),
        })
    blueprint_face = {
        "generation_id": blueprint["generation_id"],
        "pour_handle": blueprint["pour_handle"],
        "encoder_id": blueprint["encoder_id"],
        "embedding_batch_policy": blueprint.get("embedding_batch_policy"),
        "entry_role": blueprint["entry_role"],
        "counts": dict(blueprint["counts"]),
        "routes": list(blueprint_routes),
        "omitted_materializations": int(blueprint.get("omitted_materializations", 0)),
        "moved_source_roots": list(blueprint.get("moved_source_roots", ())),
    }
    projection_residual: list[dict[str, Any]] = []
    selected_source_paths = {
        str(result.get("source_path"))
        for route in blueprint_routes
        for result in route.get("results", ())
        if result.get("source_path")
    }
    for moved in blueprint_face["moved_source_roots"]:
        residual = {
            "class": "source-frontier-moved",
            "boundary": str(moved.get("path")),
            "cost": "this source descent is stale; unaffected routes remain available",
            "descend": moved,
        }
        if str(moved.get("path")) in selected_source_paths:
            omissions.append(residual)
        else:
            # Whole-blueprint drift remains visible, but it is not part of this serve object's
            # identity unless the moved source is actually in the selected route frontier.
            projection_residual.append(residual)
    blueprint_frontier = {
        "generation_id": blueprint_face["generation_id"],
        "pour_handle": blueprint_face["pour_handle"],
        "encoder_id": blueprint_face["encoder_id"],
        "routes": [
            {
                "materialization_id": route.get("materialization_id"),
                "results": [
                    {
                        "subject_id": result.get("subject_id"),
                        "content_handle": result.get("content_handle"),
                    }
                    for result in route.get("results", ())
                ],
            }
            for route in blueprint_routes
        ],
    }
    shown_preimage = {
        "schema_version": CONVERSATION_SERVE_SCHEMA,
        "serve_id": serve_id,
        "turn_handle": turn,
        "audience": audience_name,
        "decision": author_turn.get("decision"),
        "recipients": [
            {
                key: value
                for key, value in row.items()
                if key not in {"diagnostic_seat_id", "attention"}
            }
            for row in recipient_rows
        ],
        "replies": [
            {
                "message_id": row.get("message", {}).get("message_id"),
                "body_handle": row.get("message", {}).get("body_handle"),
                "status": row.get("status"),
            }
            for row in replies
        ],
        "dependency_frontier": dict(sorted(dependency_frontier.items())),
        "blueprint": blueprint_frontier,
        "omission_residual": omissions,
    }
    shown_handle = canonical_handle(shown_preimage)
    return {
        **shown_preimage,
        "blueprint": blueprint_face,
        "projection_residual": projection_residual,
        "shown_handle": shown_handle,
        "author_lifecycle": aggregate_phase,
        "mixed_recipient_phases": len(set(phases)) > 1,
        "recipient_states": recipient_rows,
        "browser_event_cursor": int(provider_state.get("event_count", 0)),
        "browser_head_event_id": provider_state.get("head_event_id"),
        "author_turn_custody": {
            "status": "CUSTODY_EXACT" if custody_exact else "CUSTODY_ABSENT",
            "content_handle": turn,
            "bytes": len(expected_turn_bytes) if custody_exact else None,
        },
        "acknowledgement_eligible": custody_exact,
        "read_only": True,
    }


__all__ = [
    "AuthorTurnAbsent",
    "AuthorTurnCustodyMismatch",
    "AUTHOR_TURN_SCHEMA",
    "CONVERSATION_SERVE_SCHEMA",
    "canonical_bytes",
    "canonical_handle",
    "bind_blueprint_routes",
    "broker_round",
    "broker_projection",
    "materialize_conversation_serve",
    "resolve_audience",
    "route_author_turn",
    "run_broker",
    "turn_handle",
]
