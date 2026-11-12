"""The DevelopmentWorkMap lens is one bounded representation, never a second store."""
from __future__ import annotations

import json
from pathlib import Path

from laplace.web import development_lens, front_door, front_places


def _row(*, node: str, cursor: int, state: str, publication: str) -> dict:
    message_id = "message:" + ("a" if cursor == 11 else "b") * 64
    return {
        "node_handle": node,
        "state": state,
        "publication_state": publication,
        "commission": {
            "message_id": message_id,
            "message_type": "interface-human-read-commission",
            "body_handle": "sha256:" + "c" * 64,
            "cursor": cursor,
            "builder_seat": "sensorium-seat",
            "reviewer_seat": "superego-seat",
            "delivery": {"delivered": True},
        },
        "candidate_evidence": {
            "status": "VALID",
            "relation_to_head": "HEAD" if publication != "CLOSED" else "ANCESTOR",
            "reasons": [],
        },
        "verdict": None if publication != "CLOSED" else {
            "message_id": "message:" + "d" * 64,
            "body_handle": "sha256:" + "e" * 64,
            "decision": "ACCEPT",
            "evidence_status": "VALID",
            "delivery": {"delivered": True},
        },
        "review_residue": {"count": 0, "latest": None},
        "source_links": [
            {"role": "commission", "kind": "fabric-message", "reference": message_id},
            {"role": "candidate-commit", "kind": "git-commit", "reference": "f" * 40},
        ],
    }


def _map(
    *, cursor: int = 42, status: str = "CURRENT", attention_proof: bool = False
) -> dict:
    if status != "CURRENT":
        return {
            "schema_version": "laplace.development-work-map/1",
            "status": status,
            "work": [],
            "reason": "HistoryChainMismatch: exact fixture refusal",
            "action": "repair the canonical history chain",
            "read_only": True,
        }
    open_row = _row(
        node="sha256:" + "1" * 64, cursor=11, state="PENDING", publication="OPEN"
    )
    closed_row = _row(
        node="sha256:" + "2" * 64, cursor=12, state="ACCEPTED", publication="CLOSED"
    )
    payload = {
        "schema_version": "laplace.development-work-map/1",
        "status": "CURRENT",
        "active_context": {"assumption": "fixture", "fibre": "fixture-fibre"},
        "freshness": {
            "state": "CURRENT",
            "source_handle": "sha256:" + "3" * 64,
            "coordinate": {
                "event_cursor": cursor,
                "head_event_id": "sha256:" + "4" * 64,
                "head_record_digest": "sha256:" + "5" * 64,
            },
        },
        "caused_by_event_cursor": cursor,
        "head_event_id": "sha256:" + "4" * 64,
        "head_record_digest": "sha256:" + "5" * 64,
        "shown_handle": "sha256:" + "6" * 64,
        "latest_work_state": "PENDING",
        "open_candidate_count": 1,
        "work": [open_row, closed_row],
        "read_metrics": {
            "open_rows_loaded": 1,
            "terminal_rows_loaded": 1,
            "rows_loaded": 2,
            "terminal_cap": 8,
            "review_residue_count": 1,
        },
        "omission_residual": {
            "status": "PRESENT",
            "omitted_open_candidates": 0,
            "omitted_terminal_candidates": 2,
            "reason": "terminal history is bounded",
            "continuation": {
                "action": "reconstruct with a larger explicit candidate_cap",
                "current_candidate_cap": 8,
            },
        },
        "fidelity_boundary": {
            "status": "CRUTCH",
            "crutch_id": "CR-review-frontier-terminal-aggregate-without-authoritative-root",
        },
        "proof_boundary": "exact visible evidence; terminal aggregate remains a crutch",
        "parallel_posture": {},
        "seat_occupancy": [],
        "read_only": True,
    }
    if attention_proof:
        open_handle = open_row["node_handle"]
        payload["attention_selection"] = {
            "schema_version": "laplace.representation.attention-selection/1",
            "state": "CURRENT",
            "source_handle": payload["freshness"]["source_handle"],
            "selection_handle": "sha256:" + "8" * 64,
            "open_set_digest": development_lens._json_digest([open_handle]),
            "ordered_handles": [open_handle],
        }
    return payload


def _authority(*, cursor: int = 42, generation: str = "sha256:generation") -> dict:
    return {
        "schema_version": "laplace.aisthesis-authority-join/1",
        "drift_token": {"cursor": cursor},
        "provider": {
            "event_count": cursor,
            "head_event_id": "sha256:" + "4" * 64,
            "seat_occupancy": {
                "sensorium-seat": {
                    "state": "BOUND",
                    "routing_authority": True,
                    "join": {"function": "sensorium"},
                    "binding": {"provider_identity_generation": generation},
                    "binding_event_id": "sha256:" + "9" * 64,
                    "defects": [],
                }
            },
        },
        "lease_projection": {
            "schema_version": "laplace.region-leases/1",
            "leases": {
                "region-lease:fixture": {
                    "checkout": {
                        "seat_id": "sensorium-seat",
                        "holder_ref": "codex:fixture",
                        "function": "sensorium",
                        "regions": ["src/laplace/web/development_lens.py"],
                    },
                    "effective_state": "ACTIVE",
                    "write_authority": True,
                    "lineage_state": "MATCH",
                    "authority_observed_at": "2026-08-28T00:00:00Z",
                }
            },
            "read_only": True,
        },
        "read_only": True,
    }


def _conversation() -> dict:
    return {
        "schema_version": "laplace.conversation-serve/1",
        "serve_id": "serve:fixture",
        "turn_handle": "sha256:" + "a" * 64,
        "shown_handle": "sha256:" + "b" * 64,
        "author_lifecycle": "acknowledged",
        "mixed_recipient_phases": False,
        "recipient_states": [
            {
                "logical_recipient": "sensorium",
                "phase": "acknowledged",
                "recipient_message_id": "message:" + "8" * 64,
                "transport_state": "DELIVERED",
                "received_event": "sha256:" + "9" * 64,
                "reconstruction_event": "sha256:" + "a" * 64,
                "reconstruction_handle": "sha256:" + "d" * 64,
                "ack_event": "sha256:" + "c" * 64,
                "diagnostic_seat_id": "sensorium-seat",
            }
        ],
        "dependency_frontier": {"ack:sensorium-seat": "sha256:" + "c" * 64},
        "replies": [
            {
                "message_id": "message:" + "7" * 64,
                "body_handle": "sha256:" + "6" * 64,
                "status": "ROOTED",
                "dependency_roots": {
                    "ack_event": "sha256:" + "c" * 64,
                    "turn_handle": "sha256:" + "a" * 64,
                },
            }
        ],
        "omission_residual": [],
        "author_turn_custody": {"status": "CUSTODY_EXACT"},
        "acknowledgement_eligible": True,
        "browser_event_cursor": 42,
        "browser_head_event_id": "sha256:" + "4" * 64,
        "read_only": True,
    }


def test_projection_carries_exact_shown_state_without_inventing_authority(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    payload = development_lens.project(
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )

    assert payload["schema_version"] == "laplace.aisthesis-read-model/1"
    assert payload["read_only"] is True
    assert payload["canonical_adapter"] == "laplace.engine.wake.development_work_map_glow"
    shown = payload["shown_state"]
    assert shown["schema_version"] == "laplace.aisthesis-shown-state/1"
    assert shown["lens_id"] == "programme"
    assert shown["model_handle"] == payload["model_handle"]
    assert shown["source_shown_handle"] == "sha256:" + "6" * 64
    assert shown["shown_handle"] == development_lens._json_digest(shown["digest_preimage"])
    preimage = shown["digest_preimage"]
    assert preimage["model_handle"] == payload["model_handle"]
    assert preimage["lens_id"] == "programme"
    assert preimage["focus_handle"] == "sha256:" + "3" * 64
    assert preimage["selected_edge_id"] is None
    assert preimage["ordered_visible_handles"] == [
        item["object_handle"] for item in payload["causal_atlas_weave"]["objects"]
    ]
    assert preimage["visible_set_digest"] == shown["visible_set_digest"]
    assert preimage["omitted_set_digest"] == shown["omitted_set_digest"]
    assert preimage["representation_grade"] == "mid"
    assert preimage["exposition"] == "E0"
    assert preimage["viewport"] == "default"
    assert preimage["layout_receipt_handle"] == payload["causal_atlas_weave"][
        "layout_receipt_handle"
    ]
    assert preimage["selected_audit_subject"] is None
    assert preimage["binding_generation"] == "sha256:generation"
    assert (
        preimage["effective_authority_handle"]
        == shown["authority"]["effective_authority_handle"]
    )
    assert shown["acknowledgement"]["state"] == "NOT-IN-THIS-SLICE"
    assert set(payload["cameras"]) == {
        "programme",
        "critical-path",
        "live-custody",
        "evidence-descent",
        "continuity",
        "residual-crutch",
        "lens-self",
    }
    assert payload["critical_path_state"] == "UNKNOWN"
    assert payload["critical_path"] == []
    assert [item["class"] for item in payload["residual"]["classes"]] == [
        "OMISSION",
        "CURRENTNESS_OR_AUTHORITY",
        "UNRESOLVED",
    ]
    assert payload["residual"]["omission"]["omitted_open_candidates"] == 0
    assert {edge["evidence_state"] for edge in payload["edges"]} == {"COMPLETE"}
    assert {
        edge["role"]: edge["evidence_state"]
        for edge in payload["projection_evidence_edges"]
    } == {"authority-projection": "COMPLETE", "conversation-projection": "COMPLETE"}
    assert "1 open review candidates" in payload["questions"]["exists"]


def test_programme_weave_conserves_every_object_and_expands_exact_groups(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    mid = development_lens.project(
        lens="programme",
        grade="mid",
        viewport="compact",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )
    weave = mid["causal_atlas_weave"]
    root = weave["objects"][0]
    goal_gap = next(item for item in weave["objects"] if item.get("omission_class") == "COVERAGE")
    assert root["label"] == "Canonical review frontier"
    assert goal_gap["label"] == "Active seat goals not joined"
    assert goal_gap["state"] == "UNKNOWN"
    assert goal_gap["member_count"] == 3
    assert goal_gap["continuation"] == "/front/development?lens=lens-self"
    visible_originals = {
        item["object_handle"]
        for item in weave["objects"]
        if item["kind"] != "compressed-group"
    }
    grouped = [
        handle
        for group in weave["compressed_groups"]
        for handle in group["ordered_member_handles"]
    ]
    assert visible_originals.isdisjoint(grouped)
    assert visible_originals | set(grouped) == set(weave["canonical_order"])
    assert len(grouped) == len(set(grouped))
    assert all(
        group["member_digest"]
        == development_lens._json_digest(group["ordered_member_handles"])
        for group in weave["compressed_groups"]
    )
    group = weave["compressed_groups"][0]
    near = development_lens.project(
        lens="programme",
        grade="near",
        focus=group["boundary_member"],
        viewport="compact",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )
    assert near["focus_state"] == "EXACT"
    assert near["shown_state"]["focus_handle"] == group["boundary_member"]
    assert near["shown_state"]["layout_receipt_handle"] != weave["layout_receipt_handle"]


def test_programme_weave_forged_focus_and_edge_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    forged_focus = development_lens.project(
        lens="programme", focus="sha256:forged", reader=lambda _cap: _map()
    )
    forged_edge = development_lens.project(
        lens="programme", edge="sha256:forged", reader=lambda _cap: _map()
    )
    assert forged_focus["status"] == "REFUSED"
    assert forged_focus["focus_state"] == "REFUSED"
    assert forged_edge["status"] == "REFUSED"
    assert forged_edge["edge_state"] == "REFUSED"


def test_focus_and_selected_typed_edge_are_exact_and_independent(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    exact = "sha256:" + "1" * 64
    seed = development_lens.project(reader=lambda _cap: _map())
    edge_id = next(
        edge["edge_id"]
        for edge in seed["edges"]
        if edge["source_handle"] == "sha256:" + "2" * 64
    )
    selected = development_lens.project(
        focus=exact, edge=edge_id, lens="evidence-descent", reader=lambda _cap: _map()
    )
    refused = development_lens.project(focus="111111", reader=lambda _cap: _map())

    assert selected["focus_state"] == "EXACT" and selected["selected"]["node_handle"] == exact
    assert selected["edge_state"] == "EXACT"
    assert selected["selected_edge"]["source_handle"] != selected["selected"]["node_handle"]
    assert selected["shown_state"]["selected_edge_id"] == edge_id
    assert refused["focus_state"] == "REFUSED"
    assert refused["status"] == "REFUSED"
    assert refused["selected"] is None


def test_critical_path_admits_at_most_five_only_with_canonical_selection_proof(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    unknown = development_lens.project(reader=lambda _cap: _map())
    proved = development_lens.project(reader=lambda _cap: _map(attention_proof=True))

    assert unknown["critical_path_state"] == "UNKNOWN" and unknown["critical_path"] == []
    assert proved["critical_path_state"] == "CURRENT"
    assert [row["node_handle"] for row in proved["critical_path"]] == [
        "sha256:" + "1" * 64
    ]
    assert len(proved["critical_path"]) <= 5


def test_custody_continuity_and_lens_self_are_honest_boundaries(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    payload = development_lens.project(
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )

    custody = payload["cameras"]["live-custody"]
    assert custody["state"] == "CURRENT"
    assert custody["binding_generation"] == "sha256:generation"
    assert custody["leases"][0]["effective_state"] == "ACTIVE"
    continuity = payload["cameras"]["continuity"]
    assert continuity["state"] == "CURRENT"
    assert continuity["projection_boundary"] == "/front/serve"
    assert continuity["phases"][0]["phase"] == "acknowledged"
    assert continuity["conversation_shown_handle"] == "sha256:" + "b" * 64
    crutch_ids = {
        item["crutch_id"]
        for item in payload["cameras"]["lens-self"]["owned_crutches"]
    }
    assert crutch_ids == {
        "CR-AIS-STREAM-500MS",
        "CR-AIS-SHADOW-FOUR-PANE",
        "CR-AIS-CARRIER-HOST-ASSUMPTIONS",
        "CR-review-frontier-terminal-aggregate-without-authoritative-root",
    }
    assert all(
        item["owner"] and item["retirement_trigger"]["predicate"]
        for item in payload["cameras"]["lens-self"]["owned_crutches"]
    )
    stream = next(
        item
        for item in payload["cameras"]["lens-self"]["owned_crutches"]
        if item["crutch_id"] == "CR-AIS-STREAM-500MS"
    )
    assert "< 250ms" in stream["retirement_trigger"]["predicate"]
    assert "adversarial" in stream["retirement_trigger"]["predicate"]


def test_continuity_is_one_normalized_causal_field_not_workmap_adjacency(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    payload = development_lens.project(
        lens="continuity",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )
    loom = payload["active_camera"]

    assert loom["schema_version"] == "laplace.aisthesis-continuity-loom/1"
    assert [item["kind"] for item in loom["canonical_objects"]] == [
        "turn",
        "message",
        "pull",
        "reconstruction",
        "acknowledgement",
        "reply",
        "authority",
    ]
    assert "compressed-group" in {item["kind"] for item in loom["objects"]}
    workmap_handles = {row["node_handle"] for row in _map()["work"]}
    assert workmap_handles.isdisjoint(payload["continuity_field"]["canonical_order"])
    assert all(
        edge["source_handle"] not in workmap_handles
        and edge["target_handle"] not in workmap_handles
        for edge in loom["edges"]
    )
    assert {
        edge["relation"]: edge["evidence_state"] for edge in loom["canonical_edges"]
    } == {
        "routed-to-recipient": "COMPLETE",
        "pulled-by-recipient": "COMPLETE",
        "typed-reconstruction": "COMPLETE",
        "acknowledges-reconstruction": "COMPLETE",
        "reply-belongs-to-turn": "COMPLETE",
        "routes-under-current-authority": "COMPLETE",
    }
    assert all(item["read_only"] for item in [loom])
    assert all(
        [entry["grade"] for entry in item["exposition"]]
        == [f"E{index}" for index in range(8)]
        and item["exposition"][-1]["state"] == "ZERO"
        and item["exposition"][-1]["authority"] == "ZERO"
        for item in loom["canonical_objects"]
    )


def test_mid_compression_is_an_exact_disjoint_content_addressed_cut(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    initial = development_lens.project(
        lens="continuity",
        grade="audit",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )["active_camera"]
    focus = next(
        item["object_handle"]
        for item in initial["canonical_objects"]
        if item["kind"] == "reconstruction"
    )
    loom = development_lens.project(
        lens="continuity",
        focus=focus,
        grade="mid",
        viewport="375",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )["active_camera"]

    canonical = loom["compression"]["canonical_order"]
    originals = loom["visible_original_handles"]
    grouped = [
        handle
        for group in loom["compressed_groups"]
        for handle in group["ordered_member_handles"]
    ]
    assert set(originals).isdisjoint(grouped)
    assert set(originals) | set(grouped) == set(canonical)
    assert len(originals) + len(grouped) == len(canonical)
    assert {group["cut"] for group in loom["compressed_groups"]} == {
        "UPSTREAM",
        "DOWNSTREAM",
    }
    assert all(
        group["member_count"] == len(group["ordered_member_handles"])
        and group["member_digest"]
        == development_lens._json_digest(group["ordered_member_handles"])
        and group["boundary_member"] in group["ordered_member_handles"]
        and group["continuation"]["focus_handle"] == group["boundary_member"]
        for group in loom["compressed_groups"]
    )
    shown_handles = {item["object_handle"] for item in loom["objects"]}
    assert set(grouped).isdisjoint(shown_handles)
    assert shown_handles == set(loom["ordered_visible_handles"])
    assert loom["cut_edges"]
    assert all(
        edge["member_digest"]
        == development_lens._json_digest(edge["ordered_member_edge_ids"])
        for edge in loom["cut_edges"]
    )
    assert (
        loom["compression"]["compression_receipt_handle"]
        == loom["layout_receipt"]["options"]["compression_receipt_handle"]
    )


def test_medium_and_narrow_geometry_reserve_noncolliding_relation_label_lanes(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    loom = development_lens.project(
        lens="continuity",
        grade="mid",
        viewport="375",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )["active_camera"]
    def intersects(left: dict, right: dict) -> bool:
        return (
            left["x"] < right["x"] + right["width"]
            and left["x"] + left["width"] > right["x"]
            and left["y"] < right["y"] + right["height"]
            and left["y"] + left["height"] > right["y"]
        )

    for viewport in ("medium", "narrow"):
        geometry = loom["geometry"][viewport]
        assert all(
            item["width"] >= 44 and item["height"] >= 44
            for item in geometry["objects"]
        )
        assert all(
            edge["label_slot"]
            and edge["control_width"] >= 44
            and edge["control_height"] >= 44
            and not any(
                intersects(
                    {
                        "x": edge["control_x"], "y": edge["control_y"],
                        "width": edge["control_width"], "height": edge["control_height"],
                    },
                    node,
                )
                for node in geometry["objects"]
            )
            for edge in geometry["edges"]
        )


def test_continuity_geometry_is_all_server_supplied_integer_and_receipted(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    first = development_lens.project(
        lens="continuity",
        viewport="768",
        grade="near",
        exposition="E6",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )
    repeated = development_lens.project(
        lens="continuity",
        viewport="768",
        grade="near",
        exposition="E6",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )
    loom = first["active_camera"]

    assert loom["selected_viewport"] == "medium"
    assert set(loom["geometry"]) == {"wide", "medium", "narrow"}
    for geometry in loom["geometry"].values():
        assert type(geometry["width"]) is int and type(geometry["height"]) is int
        assert [item["object_handle"] for item in geometry["objects"]] == [
            item["object_handle"] for item in loom["objects"]
        ]
        assert all(
            all(type(item[key]) is int for key in ("x", "y", "width", "height"))
            and type(item["compressed"]) is bool
            for item in geometry["objects"]
        )
        assert all(
            all(type(value) is int for point in item["points"] for value in point)
            and all(
                type(item[key]) is int
                for key in ("control_x", "control_y", "control_width", "control_height")
            )
            for item in geometry["edges"]
        )
    receipt = dict(loom["layout_receipt"])
    receipt_handle = receipt.pop("layout_receipt_handle")
    assert receipt_handle == development_lens._json_digest(receipt)
    assert receipt_handle == repeated["active_camera"]["layout_receipt_handle"]
    assert receipt["geometry"] == loom["geometry"]

    changed = development_lens.project(
        lens="continuity",
        viewport="768",
        grade="audit",
        exposition="E7",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )
    assert changed["model_handle"] == first["model_handle"]
    assert (
        changed["active_camera"]["layout_receipt_handle"]
        != loom["layout_receipt_handle"]
    )


def test_continuity_refuses_invalid_selection_and_presentation_contract(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    arguments = {
        "lens": "continuity",
        "reader": lambda _cap: _map(),
        "authority_reader": _authority,
        "conversation_reader": _conversation,
    }
    bad_focus = development_lens.project(focus="not-an-object", **arguments)
    bad_edge = development_lens.project(edge="not-an-edge", **arguments)
    bad_grade = development_lens.project(grade="close", **arguments)
    bad_exposition = development_lens.project(exposition="E8", **arguments)

    assert bad_focus["status"] == "REFUSED" and bad_focus["focus_state"] == "REFUSED"
    assert bad_focus["shown_state"]["focus_handle"] is None
    assert bad_edge["status"] == "REFUSED" and bad_edge["edge_state"] == "REFUSED"
    assert bad_grade["status"] == "REFUSED" and bad_grade["grade_state"] == "REFUSED"
    assert (
        bad_exposition["status"] == "REFUSED"
        and bad_exposition["exposition_state"] == "REFUSED"
    )


def test_continuity_preserves_six_exact_residual_retirement_predicates(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    loom = development_lens.project(
        lens="continuity",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )["active_camera"]
    residuals = {item["class"]: item for item in loom["residuals"]}

    assert list(residuals) == [
        "PHASE",
        "QUARANTINE",
        "SUPERSESSION",
        "CLOSED",
        "AS_OF",
        "REPLY_ROOT",
    ]
    assert residuals["PHASE"]["state"] == "COMPLETE"
    assert residuals["REPLY_ROOT"]["state"] == "COMPLETE"
    assert all(
        item["owner"]
        and item["retirement_trigger"]["comparison"] == "exact"
        and item["retirement_trigger"]["predicate"]
        for item in residuals.values()
    )
    assert {
        residuals[name]["state"]
        for name in ("QUARANTINE", "SUPERSESSION", "CLOSED", "AS_OF")
    } == {"UNRESOLVED"}


def test_continuity_missing_phase_and_lifecycle_faces_remain_unresolved(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    conversation = _conversation()
    conversation["recipient_states"][0].pop("phase")
    conversation["recipient_states"][0].pop("transport_state")
    conversation["quarantine"] = {}
    conversation["supersession"] = {}
    conversation["as_of"] = {}
    loom = development_lens.project(
        lens="continuity",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=lambda: conversation,
    )["active_camera"]

    message = next(item for item in loom["objects"] if item["kind"] == "message")
    residuals = {item["class"]: item["state"] for item in loom["residuals"]}
    assert message["state"] == "UNKNOWN"
    assert residuals["PHASE"] == "UNRESOLVED"
    assert residuals["QUARANTINE"] == "UNRESOLVED"
    assert residuals["SUPERSESSION"] == "UNRESOLVED"
    assert residuals["CLOSED"] == "UNRESOLVED"
    assert residuals["AS_OF"] == "UNRESOLVED"


def test_genuine_conversation_absence_is_unknown_but_malformed_authority_refuses(
    monkeypatch,
) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)

    class AuthorTurnAbsent(RuntimeError):
        pass

    def absent_conversation() -> dict:
        raise AuthorTurnAbsent("no banked author turn")

    absent = development_lens.project(
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=absent_conversation,
    )
    malformed = development_lens.project(
        reader=lambda _cap: _map(),
        authority_reader=lambda: {"provider": {}, "lease_projection": {}},
        conversation_reader=_conversation,
    )

    assert absent["cameras"]["continuity"]["state"] == "UNKNOWN"
    assert "AuthorTurnAbsent" in absent["cameras"]["continuity"]["reason"]
    assert malformed["cameras"]["live-custody"]["state"] == "REFUSED"
    assert malformed["status"] == "REFUSED"


def test_unavailable_projection_never_collapses_to_an_empty_map(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    payload = development_lens.project(reader=lambda _cap: _map(status="UNAVAILABLE"))

    assert payload["status"] == "UNAVAILABLE"
    assert "unavailable" in payload["questions"]["exists"].lower()
    assert "no empty-work claim" in payload["questions"]["exists"].lower()
    assert "HistoryChainMismatch" in payload["questions"]["blocked"]


def test_currentness_refuses_false_stability_when_any_frontier_field_moves(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    observed_caps = []
    served = development_lens.project(reader=lambda _cap: _map(cursor=41))
    shown = served["shown_state"]
    face = development_lens.currentness(
        served_cursor="41",
        served_head_event_id="sha256:" + "4" * 64,
        served_head_record_digest="sha256:" + "5" * 64,
        served_source_handle="sha256:" + "3" * 64,
        served_git_head="7" * 40,
        shown_handle=shown["shown_handle"],
        served_preimage=shown["digest_preimage"],
        reader=lambda cap: observed_caps.append(cap) or _map(cursor=42),
    )

    assert face["state"] == "STALE"
    assert face["actions_enabled"] is False
    assert face["moved"]["cursor"] == {"served": "41", "live": "42"}
    assert "shown_preimage.model_handle" in face["moved"]
    assert face["shown_handle"] != shown["shown_handle"]
    assert face["continuation"] == "rederive /front/development"
    assert observed_caps == [8]


def test_currentness_rederives_every_shown_field_and_refuses_forged_active(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    served = development_lens.project(
        lens="live-custody",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )
    shown = served["shown_state"]
    current = development_lens.currentness(
        served_cursor=str(shown["observed_cursor"]),
        served_head_event_id=shown["head_event_id"],
        served_head_record_digest=shown["head_record_digest"],
        served_source_handle=shown["source_handle"],
        served_git_head=shown["git_head"],
        shown_handle=shown["shown_handle"],
        served_preimage=shown["digest_preimage"],
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )
    forged_preimage = {**shown["digest_preimage"], "binding_generation": "forged"}
    forged = development_lens.currentness(
        served_cursor=str(shown["observed_cursor"]),
        served_head_event_id=shown["head_event_id"],
        served_head_record_digest=shown["head_record_digest"],
        served_source_handle=shown["source_handle"],
        served_git_head=shown["git_head"],
        shown_handle=shown["shown_handle"],
        served_preimage=forged_preimage,
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )

    assert current["state"] == "CURRENT" and current["moved"] == {}
    assert forged["state"] == "REFUSED"
    assert forged["reason"] == "served shown handle does not bind its submitted preimage"
    assert "shown_handle" in forged["moved"]


def test_continuity_currentness_rederives_layout_receipt_and_exposition(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    served = development_lens.project(
        lens="continuity",
        viewport="375",
        grade="near",
        exposition="E6",
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )["shown_state"]
    arguments = {
        "served_cursor": str(served["observed_cursor"]),
        "served_head_event_id": served["head_event_id"],
        "served_head_record_digest": served["head_record_digest"],
        "served_source_handle": served["source_handle"],
        "served_git_head": served["git_head"],
        "reader": lambda _cap: _map(),
        "authority_reader": _authority,
        "conversation_reader": _conversation,
    }
    current = development_lens.currentness(
        shown_handle=served["shown_handle"],
        served_preimage=served["digest_preimage"],
        **arguments,
    )
    forged_preimage = {
        **served["digest_preimage"],
        "layout_receipt_handle": "sha256:" + "0" * 64,
    }
    forged = development_lens.currentness(
        shown_handle=development_lens._json_digest(forged_preimage),
        served_preimage=forged_preimage,
        **arguments,
    )
    forged_subject_preimage = {
        **served["digest_preimage"],
        "selected_audit_subject": "edge:forged",
    }
    forged_subject = development_lens.currentness(
        shown_handle=development_lens._json_digest(forged_subject_preimage),
        served_preimage=forged_subject_preimage,
        **arguments,
    )

    assert current["state"] == "CURRENT" and current["moved"] == {}
    assert forged["state"] == "STALE"
    assert "shown_preimage.layout_receipt_handle" in forged["moved"]
    assert forged_subject["state"] == "STALE"
    assert "shown_preimage.selected_audit_subject" in forged_subject["moved"]


def test_currentness_route_carries_the_complete_served_preimage(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_read_map", lambda _cap=8: _map())
    monkeypatch.setattr(development_lens, "_read_authority", _authority)
    monkeypatch.setattr(development_lens, "_read_conversation", _conversation)
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)
    served = development_lens.project(
        reader=lambda _cap: _map(),
        authority_reader=_authority,
        conversation_reader=_conversation,
    )["shown_state"]
    preimage = served["digest_preimage"]
    query = {
        "format": "currentness",
        "cursor": str(served["observed_cursor"]),
        "head_event_id": served["head_event_id"],
        "head_record_digest": served["head_record_digest"],
        "source_handle": served["source_handle"],
        "git_head": served["git_head"],
        "shown_handle": served["shown_handle"],
        "model_handle": preimage["model_handle"],
        "lens": preimage["lens_id"],
        "focus": preimage["focus_handle"],
        "visible_handles": json.dumps(preimage["ordered_visible_handles"]),
        "visible_set_digest": preimage["visible_set_digest"],
        "omitted_set_digest": preimage["omitted_set_digest"],
        "grade": preimage["representation_grade"],
        "exposition": preimage["exposition"],
        "viewport": preimage["viewport"],
        "audit_subject": preimage["selected_audit_subject"],
        "binding_generation": preimage["binding_generation"],
        "effective_authority_handle": preimage["effective_authority_handle"],
    }
    if preimage["layout_receipt_handle"] is not None:
        query["layout_receipt_handle"] = preimage["layout_receipt_handle"]
    status, _content_type, body = development_lens.handle(query)
    face = json.loads(body)

    assert status == 200 and face["state"] == "CURRENT"
    assert face["served_preimage"] == preimage
    assert face["shown_handle"] == served["shown_handle"]


def test_page_and_json_share_one_read_only_door(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_read_map", lambda _cap=8: _map())
    monkeypatch.setattr(development_lens, "_read_authority", _authority)
    monkeypatch.setattr(development_lens, "_read_conversation", _conversation)
    monkeypatch.setattr(development_lens, "_git_head", lambda: "7" * 40)

    status, ctype, page = front_door.handle("/front/development", {}, "GET", b"")
    jstatus, jctype, raw = front_door.handle(
        "/front/development", {"format": "json"}, "GET", b""
    )
    payload = json.loads(raw)

    assert status == 200 and ctype.startswith("text/html")
    assert jstatus == 200 and jctype.startswith("application/json")
    assert payload["read_only"] and payload["shown_state"]["shown_handle"]
    assert b"one canonical graph" in page.lower()


def test_static_page_has_no_browser_local_authority_or_mutation_action() -> None:
    html = (
        Path(__file__).resolve().parents[1] / "src" / "laplace" / "web" / "development_lens.html"
    ).read_text(encoding="utf-8")

    assert "localStorage" not in html and "sessionStorage" not in html
    assert "innerHTML" not in html
    assert "data-canonical-action" not in html
    assert "format:'currentness'" in html
    assert "new EventSource('/front/stream?sources=atlas')" in html
    assert "atlas:unavailable" in html and "skipped" in html and "rolled" in html
    assert "visible_handles:JSON.stringify" in html
    assert "375px" not in html  # layout uses a real media query, not device-specific copy


def test_places_table_names_the_lens_without_becoming_its_authority(monkeypatch) -> None:
    monkeypatch.setattr(development_lens, "_read_map", lambda _cap=0: _map())
    place = next(row for row in front_places.PLACES if row["id"] == "development")
    census = place["census"]()

    assert place["href"] == "/front/development" and place["kind"] == "page"
    assert census["source"] == "laplace.engine.wake.development_work_map_glow(candidate_cap=1)"
    assert census["freshness"] == "live"
