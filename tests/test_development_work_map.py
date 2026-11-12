from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from atlas.ids import chash

from laplace.engine.development_work_map import project_development_work_map_from_frontier, project_development_work_map_from_state

FROZEN = {
    "frozen_commit": "a" * 40,
    "frozen_tree": "b" * 40,
    "frozen_diff_sha256": "sha256:" + "c" * 64,
}


def _materialized(
    message_id: str,
    message_type: str,
    cursor: int,
    *,
    sender: str,
    recipient: str,
    status: str = "delivered",
    roots: dict[str, str] | None = None,
    body_handle: str | None = None,
) -> dict:
    row = {
        "assumption": "assumption",
        "fibre": "fibre",
        "status": status,
        "message": {
            "message_id": message_id,
            "message_type": message_type,
            "cursor": cursor,
            "sender_seat_id": sender,
            "recipient_seat_id": recipient,
            "dependency_roots": roots or {},
            "body_handle": body_handle or f"sha256:body-{cursor}",
        },
    }
    if status == "delivered":
        row.update({
            "last_pull_event_id": f"sha256:pull-{cursor}",
            "acknowledgement_event_id": f"sha256:ack-{cursor}",
            "reconstruction_handle": f"sha256:reconstruction-{cursor}",
        })
    return row


def _state(messages: list[dict]) -> dict:
    return {
        "active_context": {"assumption": "assumption", "fibre": "fibre"},
        "event_count": 19,
        "head_event_id": "sha256:head",
        "head_record_digest": "sha256:head-record",
        "messages": {
            row["message"]["message_id"]: row for row in messages
        },
        "seat_occupancy": {},
        "region_leases": {},
    }


def _valid_candidate(_root: Path, _frozen: dict[str, str]) -> dict:
    return {
        "status": "VALID",
        "reasons": [],
        "actual_tree": FROZEN["frozen_tree"],
        "actual_diff_sha256": FROZEN["frozen_diff_sha256"],
        "relation_to_head": "ANCESTOR",
    }


def _verdict_body(decision: str = "ACCEPT", frozen: dict[str, str] = FROZEN) -> str:
    return json.dumps({
        "verdict": decision,
        "frozen": {
            "commit": frozen["frozen_commit"],
            "tree": frozen["frozen_tree"],
            "diff_sha256": frozen["frozen_diff_sha256"],
        },
    })


def _project(messages: list[dict], bodies: dict[str, str], *, cap: int = 6) -> dict:
    return project_development_work_map_from_state(
        _state(messages),
        repo_root=Path("."),
        body_resolver=bodies.__getitem__,
        candidate_verifier=_valid_candidate,
        candidate_cap=cap,
        observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )


def _lease_frontier(
    lease: dict,
    *,
    authority_observed_at: str | None,
    seat_occupancy: dict | None = None,
    include_seat_occupancy: bool = True,
) -> dict:
    frontier = {
        "status": "CURRENT",
        "active_context": {"assumption": "assumption", "fibre": "fibre"},
        "caused_by_event_cursor": 19,
        "head_event_id": "sha256:head",
        "head_record_digest": "sha256:head-record",
        "rows": [],
        "projection_terminal_count": 0,
        "region_leases": {"lease:historical": lease},
        "region_lease_authority_observed_at": authority_observed_at,
    }
    if include_seat_occupancy:
        frontier["seat_occupancy"] = seat_occupancy or {}
    return frontier


def test_work_map_never_promotes_raw_historical_lease_authority() -> None:
    observed_at = "2026-08-28T04:00:00Z"
    raw = {
        "state": "HELD-UNTIL-EXPIRY",
        "authority": "conditional-until-expiry",
        "checkout": {
            "lease_id": "lease:historical",
            "seat_id": "ego-seat",
            "holder_ref": "codex:historical",
            "function": "ego",
            "regions": ["src/historical"],
            "base_git_head": "a" * 40,
            "expires_at": "2036-08-28T05:00:00Z",
        },
        "checkout_authority": {
            "schema_version": "region-checkout-authority-lineage/1",
            "join_event_id": "sha256:old-join",
            "binding_event_id": "sha256:old-binding",
            "provider_identity_generation": "sha256:old-generation",
        },
        "checkin": None,
    }
    observed = datetime(2026, 8, 28, 4, tzinfo=timezone.utc)
    forged = {
        **raw,
        "effective_state": "ACTIVE",
        "write_authority": True,
        "authority_observed_at": observed_at,
        "lineage_state": "MATCH",
        "effective_authority": {
            "schema_version": "atlas.region-lease-effective-authority/1",
            "state": "ACTIVE",
            "write_authority": True,
            "observed_at": observed_at,
            "lineage_state": "MATCH",
            "lineage_reason": "current occupancy exactly matches checkout lineage",
        },
    }
    missing_seal = {**forged, "checkout_authority": {}}
    wrong_seal = {
        **forged,
        "checkout_authority": {
            **raw["checkout_authority"],
            "schema_version": "region-checkout-authority-lineage/forged",
        },
    }
    malformed_envelope = {**forged, "effective_authority": "ACTIVE"}
    plants = (
        _lease_frontier(raw, authority_observed_at=None),
        _lease_frontier(missing_seal, authority_observed_at=observed_at),
        _lease_frontier(wrong_seal, authority_observed_at=observed_at),
        _lease_frontier(forged, authority_observed_at=observed_at),
        _lease_frontier(
            forged,
            authority_observed_at=observed_at,
            include_seat_occupancy=False,
        ),
        _lease_frontier(malformed_envelope, authority_observed_at=observed_at),
    )

    for frontier in plants:
        projected = project_development_work_map_from_frontier(
            frontier,
            repo_root=Path("."),
            body_resolver=lambda _handle: "",
            candidate_verifier=_valid_candidate,
            observed_at=observed,
        )
        assert projected["leases"][0]["effective_state"] == "UNKNOWN"
        assert projected["leases"][0]["write_authority"] is False
        assert projected["parallel_posture"] == "NO-ACTIVE-WRITE-LEASES"


def test_work_map_carries_exact_effective_lease_observation() -> None:
    observed_at = "2026-08-28T04:00:00Z"
    join_event_id = "sha256:current-join"
    binding_event_id = "sha256:current-binding"
    generation = "sha256:current-generation"
    occupancy = {
        "routing_authority": True,
        "join_event_id": join_event_id,
        "binding_event_id": binding_event_id,
        "join": {
            "holder_ref": "codex:current",
            "function": "ego",
            "provider_identity_generation": generation,
        },
        "binding": {"provider_identity_generation": generation},
    }
    lease = {
        "checkout": {
            "lease_id": "lease:historical",
            "seat_id": "ego-seat",
            "holder_ref": "codex:current",
            "function": "ego",
            "regions": ["src/current"],
            "base_git_head": "a" * 40,
            "expires_at": "2036-08-28T05:00:00Z",
        },
        "checkout_authority": {
            "schema_version": "region-checkout-authority-lineage/1",
            "join_event_id": join_event_id,
            "binding_event_id": binding_event_id,
            "provider_identity_generation": generation,
        },
        "checkin": None,
        "effective_state": "ACTIVE",
        "write_authority": True,
        "authority_observed_at": observed_at,
        "lineage_state": "MATCH",
        "effective_authority": {
            "schema_version": "atlas.region-lease-effective-authority/1",
            "state": "ACTIVE",
            "write_authority": True,
            "observed_at": observed_at,
            "lineage_state": "MATCH",
            "lineage_reason": "current occupancy exactly matches checkout lineage",
        },
    }
    observed = datetime(2026, 8, 28, 4, tzinfo=timezone.utc)

    projected = project_development_work_map_from_frontier(
        _lease_frontier(
            lease,
            authority_observed_at=observed_at,
            seat_occupancy={"ego-seat": occupancy},
        ),
        repo_root=Path("."),
        body_resolver=lambda _handle: "",
        candidate_verifier=_valid_candidate,
        observed_at=observed,
    )

    assert projected["observed_at"] == observed_at
    assert projected["leases"][0]["authority_observed_at"] == observed_at
    assert projected["leases"][0]["effective_state"] == "ACTIVE"
    assert projected["leases"][0]["write_authority"] is True
    assert projected["parallel_posture"] == "LEASES-ACTIVE-CHECK-PATH-CONFLICTS"


def test_delivered_exact_verdict_advances_the_live_candidate() -> None:
    commission = _materialized(
        "message:commission",
        "final-reattack-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    verdict_roots = {
        **FROZEN,
        "commission": "message:commission",
        "review_decision": "ACCEPT",
    }
    verdict = _materialized(
        "message:verdict",
        "final-verdict",
        11,
        sender="superego-seat",
        recipient="codex-seat",
        roots=verdict_roots,
        body_handle="sha256:verdict",
    )

    projected = _project(
        [commission, verdict], {"sha256:verdict": _verdict_body()}
    )

    assert projected["latest_work_state"] == "ACCEPTED"
    assert projected["open_candidate_count"] == 0
    assert projected["work"][0]["verdict"]["evidence_status"] == "VALID"


def test_queued_verdict_never_counts_as_an_accepted_review() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    verdict = _materialized(
        "message:verdict",
        "review-verdict",
        11,
        sender="superego-seat",
        recipient="codex-seat",
        status="queued",
        roots={
            **FROZEN,
            "commission": "message:commission",
            "review_decision": "ACCEPT",
        },
        body_handle="sha256:verdict",
    )

    projected = _project([commission, verdict], {})

    assert projected["latest_work_state"] == "VERDICT-QUEUED"
    assert projected["open_candidate_count"] == 1
    assert projected["work"][0]["verdict"]["evidence_status"] == "UNREAD"


def test_verdict_cannot_rebind_itself_to_different_candidate_roots() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    forged = {**FROZEN, "frozen_tree": "d" * 40}
    verdict = _materialized(
        "message:verdict",
        "review-verdict",
        11,
        sender="superego-seat",
        recipient="codex-seat",
        roots={
            **forged,
            "commission": "message:commission",
            "review_decision": "ACCEPT",
        },
        body_handle="sha256:verdict",
    )

    projected = _project(
        [commission, verdict], {"sha256:verdict": _verdict_body(frozen=forged)}
    )

    assert projected["latest_work_state"] == "INVALID-EVIDENCE"
    assert projected["open_candidate_count"] == 1
    assert projected["work"][0]["verdict"]["errors"]


def test_historical_exact_scope_verdict_closes_without_a_body_frozen_object() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    verdict = _materialized(
        "message:13b859bdec653046358bd1a005ebbf7ff4d822d7490a2cf8005462d288330ae3",
        "review-verdict",
        11,
        sender="superego-seat",
        recipient="codex-seat",
        roots={**FROZEN, "commission": "message:commission"},
        body_handle="sha256:verdict",
    )
    body = json.dumps({
        "verdict": "REJECT",
        "scope": f"exact commit {FROZEN['frozen_commit']} only",
    })

    projected = _project([commission, verdict], {"sha256:verdict": body})

    assert projected["latest_work_state"] == "REJECTED"
    assert projected["open_candidate_count"] == 0
    assert projected["work"][0]["verdict"]["binding_mode"] == (
        "DEPENDENCY-ROOTS+EXACT-COMMIT-SCOPE"
    )


def test_old_open_work_is_never_displaced_by_bounded_terminal_history() -> None:
    open_commission = _materialized(
        "message:open",
        "review-commission",
        1,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    messages = [open_commission]
    bodies: dict[str, str] = {}
    for number in (2, 3):
        frozen = {
            "frozen_commit": str(number) * 40,
            "frozen_tree": "b" * 40,
            "frozen_diff_sha256": "sha256:" + "c" * 64,
        }
        commission_id = f"message:closed-{number}"
        messages.append(_materialized(
            commission_id,
            "review-commission",
            number * 10,
            sender="codex-seat",
            recipient="superego-seat",
            roots=frozen,
        ))
        handle = f"sha256:verdict-{number}"
        messages.append(_materialized(
            f"message:verdict-{number}",
            "review-verdict",
            number * 10 + 1,
            sender="superego-seat",
            recipient="codex-seat",
            roots={
                **frozen,
                "commission": commission_id,
                "review_decision": "ACCEPT",
            },
            body_handle=handle,
        ))
        bodies[handle] = _verdict_body(frozen=frozen)

    projected = _project(messages, bodies, cap=1)

    assert projected["open_candidate_count"] == 1
    assert projected["omitted_open_candidates"] == 0
    assert projected["omitted_terminal_candidates"] == 1
    assert [row["commission"]["message_id"] for row in projected["work"]] == [
        "message:open",
        "message:closed-3",
    ]


def test_contest_is_a_terminal_review_disposition_not_invalid_evidence() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    verdict = _materialized(
        "message:verdict",
        "review-verdict",
        11,
        sender="superego-seat",
        recipient="codex-seat",
        roots={
            **FROZEN,
            "commission": "message:commission",
            "review_decision": "CONTEST",
        },
        body_handle="sha256:verdict",
    )

    projected = _project(
        [commission, verdict], {"sha256:verdict": _verdict_body("CONTEST")}
    )

    assert projected["latest_work_state"] == "CONTESTED"
    assert projected["open_candidate_count"] == 0
    assert projected["work"][0]["publication_state"] == "CLOSED"


def test_builder_or_third_seat_verdict_cannot_close_the_publication() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    for sender, recipient in (
        ("codex-seat", "superego-seat"),
        ("interface-seat", "codex-seat"),
    ):
        verdict = _materialized(
            f"message:verdict:{sender}",
            "review-verdict",
            11,
            sender=sender,
            recipient=recipient,
            roots={
                **FROZEN,
                "commission": "message:commission",
                "review_decision": "ACCEPT",
            },
            body_handle="sha256:verdict",
        )
        projected = _project(
            [commission, verdict], {"sha256:verdict": _verdict_body()}
        )
        assert projected["latest_work_state"] == "INVALID-EVIDENCE"
        assert projected["open_candidate_count"] == 1
        assert projected["work"][0]["publication_state"] == (
            "PUBLISHED-PENDING-CLOSURE"
        )


def test_verdict_cursor_must_follow_the_commission() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    verdict = _materialized(
        "message:verdict",
        "review-verdict",
        9,
        sender="superego-seat",
        recipient="codex-seat",
        roots={
            **FROZEN,
            "commission": "message:commission",
            "review_decision": "ACCEPT",
        },
        body_handle="sha256:verdict",
    )

    projected = _project(
        [verdict, commission], {"sha256:verdict": _verdict_body()}
    )

    assert projected["latest_work_state"] == "INVALID-EVIDENCE"
    assert projected["open_candidate_count"] == 1


def test_compact_frontier_verifies_only_open_plus_bounded_terminal_rows() -> None:
    calls = {"candidates": 0, "bodies": 0}

    def candidate(_root: Path, _frozen: dict[str, str]) -> dict:
        calls["candidates"] += 1
        return _valid_candidate(_root, _frozen)

    def body(_handle: str) -> str:
        calls["bodies"] += 1
        raise AssertionError("typed terminal decision must not reopen verdict body")

    rows = []
    for number in range(1, 21):
        frozen = {
            "frozen_commit": f"{number:040x}",
            "frozen_tree": FROZEN["frozen_tree"],
            "frozen_diff_sha256": FROZEN["frozen_diff_sha256"],
        }
        commission_id = f"message:commission:{number}"
        commission = _materialized(
            commission_id,
            "review-commission",
            number * 10,
            sender="codex-seat",
            recipient="superego-seat",
            roots=frozen,
        )
        verdict = _materialized(
            f"message:verdict:{number}",
            "review-verdict",
            number * 10 + 1,
            sender="superego-seat",
            recipient="codex-seat",
            roots={
                **frozen,
                "commission": commission_id,
                "review_decision": "ACCEPT",
            },
        )
        rows.append({
            "commission": commission,
            "verdict": verdict,
            "review_decision": "ACCEPT",
            "route_valid": True,
            "route_errors": [],
            "projection_terminal": True,
        })
    frontier = {
        "active_context": {"assumption": "assumption", "fibre": "fibre"},
        "caused_by_event_cursor": 1000,
        "head_event_id": "sha256:head",
        "head_record_digest": "sha256:head-record",
        # The Atlas SQL projection has already retained only the visible terminal tail.
        "rows": rows[-1:],
        "projection_open_count": 0,
        "projection_terminal_count": 20,
        "omitted_projection_terminal_count": 19,
        "seat_occupancy": {},
        "region_leases": {},
        "read_metrics": {"rows_loaded": 1, "history_replayed": False},
    }

    projected = project_development_work_map_from_frontier(
        frontier,
        repo_root=Path("."),
        body_resolver=body,
        candidate_verifier=candidate,
        candidate_cap=1,
        observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    assert calls == {"candidates": 1, "bodies": 0}
    assert projected["read_metrics"]["candidate_verifications"] == 1
    assert projected["omitted_terminal_candidates"] == 19


def test_compact_frontier_surfaces_non_authoritative_review_residue() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    verdict = _materialized(
        "message:verdict",
        "review-verdict",
        11,
        sender="superego-seat",
        recipient="codex-seat",
        roots={
            **FROZEN,
            "commission": "message:commission",
            "review_decision": "ACCEPT",
        },
    )
    residue = {
        "message": _materialized(
            "message:third-seat",
            "review-verdict",
            12,
            sender="interface-seat",
            recipient="codex-seat",
            roots={
                **FROZEN,
                "commission": "message:commission",
                "review_decision": "REJECT",
            },
        ),
        "route_valid": False,
        "route_errors": ["verdict sender is not the commissioned reviewer"],
        "review_decision": "REJECT",
    }
    frontier = {
        "active_context": {"assumption": "assumption", "fibre": "fibre"},
        "caused_by_event_cursor": 12,
        "head_event_id": "sha256:head",
        "head_record_digest": "sha256:head-record",
        "rows": [{
            "commission": commission,
            "verdict": verdict,
            "review_decision": "ACCEPT",
            "route_valid": True,
            "route_errors": [],
            "review_residue_count": 1,
            "latest_review_residue": residue,
            "projection_terminal": True,
        }],
        "projection_open_count": 0,
        "projection_terminal_count": 1,
        "seat_occupancy": {},
        "region_leases": {},
        "read_metrics": {"rows_loaded": 1, "history_replayed": False},
    }

    projected = project_development_work_map_from_frontier(
        frontier,
        repo_root=Path("."),
        body_resolver=lambda _handle: "",
        candidate_verifier=_valid_candidate,
        candidate_cap=1,
        observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    assert projected["latest_work_state"] == "ACCEPTED"
    assert projected["work"][0]["review_residue"] == {
        "count": 1,
        "latest": residue,
    }
    assert projected["read_metrics"]["review_residue_count"] == 1


def test_map_binds_exact_shown_state_and_bounded_descent_sources() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
        body_handle="sha256:commission-body",
    )
    verdict = _materialized(
        "message:verdict",
        "review-verdict",
        11,
        sender="superego-seat",
        recipient="codex-seat",
        roots={
            **FROZEN,
            "commission": "message:commission",
            "review_decision": "ACCEPT",
        },
        body_handle="sha256:verdict-body",
    )

    projected = _project(
        [commission, verdict],
        {"sha256:verdict-body": _verdict_body()},
    )

    shown = dict(projected)
    shown_handle = shown.pop("shown_handle")
    assert shown_handle == chash(shown)
    assert projected["observed_at"] == "2026-08-26T00:00:00Z"
    assert projected["freshness"]["state"] == "CURRENT"
    assert projected["freshness"]["coordinate"]["event_cursor"] == 19
    assert projected["omission_residual"]["status"] == "NONE"
    links = {
        (link["role"], link["kind"], link["reference"])
        for link in projected["work"][0]["source_links"]
    }
    assert (
        "commission",
        "fabric-message",
        "message:commission",
    ) in links
    assert (
        "commission-body",
        "atlas-custody",
        "sha256:commission-body",
    ) in links
    assert ("candidate-commit", "git-commit", FROZEN["frozen_commit"]) in links
    assert ("verdict", "fabric-message", "message:verdict") in links


def test_source_handle_is_stable_while_exact_shown_time_changes() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    state = _state([commission])
    first = project_development_work_map_from_state(
        state,
        repo_root=Path("."),
        body_resolver=lambda _handle: "",
        candidate_verifier=_valid_candidate,
        observed_at=datetime(2026, 8, 26, 0, tzinfo=timezone.utc),
    )
    later = project_development_work_map_from_state(
        state,
        repo_root=Path("."),
        body_resolver=lambda _handle: "",
        candidate_verifier=_valid_candidate,
        observed_at=datetime(2026, 8, 26, 1, tzinfo=timezone.utc),
    )

    assert first["freshness"]["source_handle"] == later["freshness"]["source_handle"]
    assert first["shown_handle"] != later["shown_handle"]


def test_noncurrent_frontier_refuses_instead_of_rendering_a_map() -> None:
    with pytest.raises(ValueError, match="requires a CURRENT Atlas frontier"):
        project_development_work_map_from_frontier(
            {
                "status": "STALE",
                "active_context": {"assumption": "assumption", "fibre": "fibre"},
                "caused_by_event_cursor": 1,
                "head_event_id": "sha256:head",
                "head_record_digest": "sha256:head-record",
                "rows": [],
            },
            repo_root=Path("."),
            body_resolver=lambda _handle: "",
            candidate_verifier=_valid_candidate,
        )


def test_nonzero_frontier_refuses_without_exact_head_record_digest() -> None:
    with pytest.raises(ValueError, match="exact Atlas head record digest"):
        project_development_work_map_from_frontier(
            {
                "status": "CURRENT",
                "active_context": {"assumption": "assumption", "fibre": "fibre"},
                "caused_by_event_cursor": 2,
                "head_event_id": "sha256:head",
                "rows": [],
            },
            repo_root=Path("."),
            body_resolver=lambda _handle: "",
            candidate_verifier=_valid_candidate,
        )


def test_strict_frontier_refuses_status_only_delivery_for_both_faces() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    verdict = _materialized(
        "message:verdict",
        "review-verdict",
        11,
        sender="superego-seat",
        recipient="codex-seat",
        roots={
            **FROZEN,
            "commission": "message:commission",
            "review_decision": "ACCEPT",
        },
    )
    for row in (commission, verdict):
        row.pop("last_pull_event_id")
        row.pop("acknowledgement_event_id")
        row.pop("reconstruction_handle")
    frontier = {
        "status": "CURRENT",
        "active_context": {"assumption": "assumption", "fibre": "fibre"},
        "caused_by_event_cursor": 11,
        "head_event_id": "sha256:head",
        "head_record_digest": "sha256:head-record",
        "rows": [{
            "commission": commission,
            "verdict": verdict,
            "review_decision": "ACCEPT",
            "route_valid": True,
            "route_errors": [],
            "projection_terminal": True,
        }],
        "projection_terminal_count": 1,
        "seat_occupancy": {},
        "region_leases": {},
    }

    projected = project_development_work_map_from_frontier(
        frontier,
        repo_root=Path("."),
        body_resolver=lambda _handle: "",
        candidate_verifier=_valid_candidate,
        observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    row = projected["work"][0]
    assert projected["delivery_evidence_mode"] == "strict"
    assert projected["latest_work_state"] == "COMMISSION-DELIVERY-UNPROVEN"
    assert projected["open_candidate_count"] == 1
    assert row["commission"]["delivery"]["delivered"] is False
    assert row["verdict"]["delivery"]["delivered"] is False
    assert row["commission"]["delivery"]["legacy_full_state_compatibility"] is False


def test_strict_frontier_gates_terminal_state_on_verdict_delivery_proof() -> None:
    commission = _materialized(
        "message:commission",
        "review-commission",
        10,
        sender="codex-seat",
        recipient="superego-seat",
        roots=dict(FROZEN),
    )
    verdict = _materialized(
        "message:verdict",
        "review-verdict",
        11,
        sender="superego-seat",
        recipient="codex-seat",
        roots={
            **FROZEN,
            "commission": "message:commission",
            "review_decision": "ACCEPT",
        },
    )
    verdict.pop("last_pull_event_id")
    verdict.pop("acknowledgement_event_id")
    verdict.pop("reconstruction_handle")
    frontier = {
        "status": "CURRENT",
        "active_context": {"assumption": "assumption", "fibre": "fibre"},
        "caused_by_event_cursor": 11,
        "head_event_id": "sha256:head",
        "head_record_digest": "sha256:head-record",
        "rows": [{
            "commission": commission,
            "verdict": verdict,
            "review_decision": "ACCEPT",
            "route_valid": True,
            "route_errors": [],
            "projection_terminal": True,
        }],
        "projection_terminal_count": 1,
        "seat_occupancy": {},
        "region_leases": {},
    }

    projected = project_development_work_map_from_frontier(
        frontier,
        repo_root=Path("."),
        body_resolver=lambda _handle: "",
        candidate_verifier=_valid_candidate,
        observed_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    assert projected["latest_work_state"] == "VERDICT-DELIVERY-UNPROVEN"
    assert projected["open_candidate_count"] == 1
    assert projected["work"][0]["verdict"]["decision"] is None
