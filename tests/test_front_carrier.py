from __future__ import annotations

import builtins
import copy

from laplace.engine import front_carrier


def _health(*, status: str = "CURRENT", source: str = "c" * 40) -> dict:
    source_commit = "c" * 40
    source_tree = "1" * 40
    output_commit = "f" * 40
    output_tree = "2" * 40
    classes = []
    names = (
        "development-work-map", "work-orders", "atlas-graph-objects",
        "atlas-typed-edges", "atlas-current-heads", "lifecycle-recovery-publication",
        "fabric-exchange", "custody", "seat-profiles-goals-bindings",
        "git-source-artifacts", "explicit-omissions-refusals",
    )
    for index, name in enumerate(names, 1):
        classes.append({
            "source_class": name, "count": index, "root": f"sha256:{index:064x}",
            "admitted": True, "omitted": 0, "reason": "complete canonical projection admitted",
        })
    profiles = {
        "aisthesis": "sha256:" + "3" * 64,
        "ego": "sha256:" + "4" * 64,
        "superego": "sha256:" + "5" * 64,
    }
    atlas_token = {
        "schema_version": "laplace.semantic-atlas-currentness-token/1",
        "drift_token": {
            "schema_version": "laplace.atlas-drift-token/1",
            "cursor": 3300,
            "head_event_id": "sha256:" + "6" * 64,
            "head_record_digest": "sha256:" + "7" * 64,
        },
        "effective_checkpoint_digest": "sha256:" + "8" * 64,
        "authority_roots": {"seat_occupancy_root": "sha256:" + "9" * 64},
        "integrity_boundary": "CURRENT",
    }
    atlas_token["token_handle"] = front_carrier.canonical_handle(atlas_token)
    source_tuple = {
        "schema_version": "laplace.semantic-fold-source-tuple/1",
        "git": {"commit": source_commit, "tree": source_tree},
        "atlas": atlas_token,
        "coverage_contract": {
            "schema_version": "laplace.semantic-source-coverage/1",
            "required_classes": list(names),
        },
        "profile_heads_handle": "sha256:" + "a" * 64,
        "profile_heads": {
            function: {
                "profile_handle": handle,
                "goal_digest": "sha256:" + f"{index:x}" * 64,
                "phase_policy_handle": "sha256:" + f"{index + 3:x}" * 64,
            }
            for index, (function, handle) in enumerate(sorted(profiles.items()), 1)
        },
        "profile_handles": profiles,
        "goal_context_handle": "sha256:" + "b" * 64,
        "policy_roots": {"regularization": "sha256:" + "c" * 64},
        "builder": {
            "entry": "scripts/semantic_cadence.py --worker",
            "law_generation": "canonical-up-down-outer-receipt/1",
            "required_gpu": True,
        },
    }
    source_tuple["source_tuple_handle"] = front_carrier.canonical_handle(source_tuple)
    fold_receipt = "sha256:" + "d" * 64
    fold_index = "sha256:" + "e" * 64
    register = "sha256:" + "f" * 64
    witnesses = [
        {
            "query": f"semantic query {index}",
            "router": "conceptric",
            "visited": 12 + index,
            "expected_semantic_node": f"OP-WITNESS-{index}",
            "reached": True,
            "exact_route": {
                "kind": "ledger-row", "reference": f"OP-WITNESS-{index}",
                "source": "semantic_operational_sources",
            },
            "exact_content_handle": f"sha256:{index + 16:064x}",
            "exact_content_status": "COMPLETE",
            "descent_authority_write": "none",
        }
        for index in range(6)
    ]
    return {
        "schema_version": "laplace.embedding-health/1",
        "status": status,
        "ui_status": "UPDATE-DUE" if status in {"STALE", "IN_FLIGHT"} else status,
        "shared": True,
        "current_source": {
            "commit": source,
            "tree": source_tree if source == source_commit else "3" * 40,
        },
        "source_currentness": {
            "status": "CURRENT" if status == "CURRENT" else "UPDATE-DUE",
            "claimed_source_tuple_handle": source_tuple["source_tuple_handle"],
            "active_source_tuple_handle": source_tuple["source_tuple_handle"],
            "moved_fields": [],
            "source_tuple": source_tuple,
        },
        "side_refs": {
            "refs/eigen/semantic-fold": {
                "ref": "refs/eigen/semantic-fold",
                "commit": output_commit,
                "tree": output_tree,
            },
            "refs/eigen/semantic-fold-receipt": {
                "ref": "refs/eigen/semantic-fold-receipt",
                "receipt_handle": fold_receipt,
            },
        },
        "fold": {
            "source_commit": source_commit,
            "source_tree": source_tree,
            "output_commit": output_commit,
            "output_tree": output_tree,
            "forward_relation": "EXACT",
            "semantic_horizon": {
                "source_commit": source_commit,
                "source_tree": source_tree,
                "atlas_cursor": 3300,
                "atlas_head_event_id": "sha256:" + "6" * 64,
                "nodes": 23217,
                "clusters": 2487,
                "leaves": 20730,
            },
            "lag_commits": 0,
            "manifest_handle": "sha256:" + "a" * 64,
            "coverage_handle": "sha256:" + "b" * 64,
            "semantic_fold_receipt_handle": fold_receipt,
            "semantic_fold_index_handle": fold_index,
            "semantic_register_generation": register,
        },
        "up_down": {
            "status": "CANONICAL-UP-BATCH-READ-ONLY-DOWN",
            "receipt_handle": fold_receipt,
            "index_handle": fold_index,
            "register_generation": register,
            "entries": 23217,
        },
        "coverage": {
            "required_complete": True,
            "classes": classes,
        },
        "profile_handles": profiles,
        "artifacts": {
            "root": "sha256:" + "0" * 64, "count": 536, "bytes": 4096,
            "cache_sidecar_consistent": True,
        },
        "runtime": {
            "model": "model-1", "backend": "torch", "providers": ["cuda"],
            "device": "cuda:0", "required_gpu": True,
        },
        "latest_receipt": {
            "full_requested": True,
            "mode": "full-rebuild",
            "embedding_counts": {"embedded": 2487, "cached": 22385, "deferred": 0, "total": 24872},
            "device": {
                "required": True, "embedding_backend": "gpu",
                "embedding_providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            },
        },
        "semantic_reachability": witnesses,
        "cadence": {
            "policy": "accepted-source-catchup", "queue_key": "fold:f", "queued": False,
            "running": None, "superseded_by": None, "last_success": "fold-1",
            "last_refusal": None, "latency_seconds": 4, "resource_effect": "read-only health",
        },
        "consumption": {"last_wake": "wake-1", "last_descent": "descent-1"},
        "non_blocking": True,
        "authority_effect": "none",
    }


def _producers() -> dict:
    return {
        key: {"schema_version": f"fixture.{key}/1", "status": "CURRENT", "value": key}
        for key in ("now", "programme", "work", "decision", "run", "conversation",
                    "exposition", "diagnostics")
    }


def _binding(*, with_receipt: bool = True) -> dict:
    return {
        "selected": {"seat": "sensorium-seat", "turn": "turn:1", "task": "task:1"},
        "routed_handles": ["sha256:" + "1" * 64],
        "current_forward_link": {
            "S": "sha256:" + "2" * 64, "F": "sha256:" + "3" * 64,
            "relation": "laplace.semantic-forward-link/1", "receipt": "sha256:" + "4" * 64,
        },
        "regions": {
            "reached": ["r1"], "admitted": ["r1"], "rejected": ["r2"],
            "unvisited": ["r3"],
        },
        "depth": 3,
        "budget": {"bytes": 4096, "tokens": 512},
        "fog": [{
            "class": "BOUNDARY_RESIDUAL", "count": 1,
            "digest": "sha256:" + "5" * 64, "continuation": "r2",
        }],
        "last_enforced_descent": {
            "time": "2026-08-28T10:00:00Z" if with_receipt else None,
            "receipt": "sha256:" + "6" * 64 if with_receipt else None,
        },
        "injected_context_currentness": "CURRENT" if with_receipt else "UNKNOWN",
    }


def _fabric() -> dict:
    return {
        "canonical": {
            "state": "COMPLETE",
            "send": {
                "state": "COMPLETE", "event": "event:send",
                "receipt": "receipt:send", "latency_ms": 3,
            },
            "queued": {
                "state": "COMPLETE", "event": "event:queued",
                "receipt": "receipt:queued", "latency_ms": 1,
            },
            "pull": {
                "state": "COMPLETE", "event": "event:pull",
                "receipt": "receipt:pull", "latency_ms": 5,
            },
            "typed-reconstruction": {
                "state": "COMPLETE", "event": "event:reconstruct",
                "receipt": "receipt:reconstruct", "latency_ms": 11,
            },
            "acknowledgement": {
                "state": "COMPLETE", "event": "event:ack",
                "receipt": "receipt:ack", "latency_ms": 2,
            },
            "delivered": {
                "state": "COMPLETE", "event": "event:delivered",
                "receipt": "receipt:delivered", "latency_ms": 1,
            },
            "reply": {
                "state": "COMPLETE", "event": "event:reply",
                "receipt": "receipt:reply", "latency_ms": 7,
            },
            "event_delta": 7,
            "queue": {"pending": 0},
            "backpressure": "CLEAR",
            "compaction_state": "INERT",
        },
        "watcher": {
            "state": "ACTIVE",
            "attention_tokens": 1,
            "seat": "sensorium-seat",
            "target_task": "task:aisthesis",
            "generation": "generation:1",
            "loaded_implementation": "implementation:1",
            "current_implementation": "implementation:1",
            "implementation_state": "CURRENT",
            # Hostile producer claims must never cross the observatory boundary.
            "delivery_claim": True,
            "acknowledgement_claim": True,
        },
        "metrics": {
            "batch_count": 1,
            "process_count": 1,
            "replay_count": 0,
            "consumed_count": 1,
            "inert_count": 1,
        },
        "fix_forward_state": "CLEAR",
        "fix_forward_next": None,
    }


def _direct_coordination() -> dict:
    return {
        "active": True,
        "coordination_reference": "CR-DIRECT-TASK-COORDINATION-SEMANTIC-RECOVERY-20260828",
        "source_task_ref": "task:superego",
        "target_task_ref": "task:aisthesis",
        "message_ref": "direct-message:1",
        "body_digest": "sha256:" + "7" * 64,
        "custody_artifact_digest": "sha256:" + "8" * 64,
        # Hostile producer claims must never be accepted as Fabric receipts.
        "delivery_claim": True,
        "acknowledgement_claim": True,
        "canonical_claims": {
            "send": True,
            "pull": True,
            "reconstruction": True,
            "acknowledgement": True,
            "reply": True,
        },
        "retirement_predicate": "one exact canonical Fabric round trip",
    }


def _semantic_junction(*, status: str = "UNKNOWN") -> dict:
    return {
        "schema_version": "laplace.aisthesis-semantic-junction/1",
        "status": status,
        "title": "Semantic junction",
        "lineages": [],
        "producer_boundary": {"read_only": True, "authority_effect": "none"},
    }


def _author_ruling(*, status: str = "REFUSED") -> dict:
    return {
        "schema_version": "laplace.aisthesis-author-ruling/1",
        "status": status,
        "human_summary": {"title": "Author ruling", "state": status},
        "publication_cut_policy": {
            "schema_version": "laplace.aisthesis-publication-cut-policy/1",
            "status": "CURRENT",
            "human_summary": {"disposition": "RUNNABLE-CUT"},
        },
        "read_only": True,
        "authority_effect": "none",
    }


def test_model_is_deterministic_and_has_exact_eight_room_manifest() -> None:
    first = front_carrier.project(producers=_producers(), embedding_health=_health())
    second = front_carrier.project(producers=_producers(), embedding_health=_health())
    assert first == second
    assert first["schema_version"] == "laplace.aisthesis-front-model/1"
    assert first["model_handle"] == front_carrier.canonical_handle(first["model_preimage"])
    assert [room["room_id"] for room in first["room_manifest"]] == [
        "Now", "Programme", "Work", "Decision", "Run", "Conversation",
        "Exposition", "Diagnostics",
    ]
    assert first["authority"] == {
        "read_only": True, "second_truth_store": "forbidden", "write_paths": [],
    }


def test_semantic_junction_and_author_ruling_are_bound_into_both_preimages() -> None:
    semantic = _semantic_junction()
    ruling = _author_ruling()
    served = front_carrier.project(
        producers=_producers(), embedding_health=_health(),
        semantic_junction=semantic, author_ruling=ruling,
    )
    assert served["semantic_junction"]["status"] == "UNKNOWN"
    assert served["author_ruling"]["status"] == "REFUSED"
    shown = served["shown_state"]
    assert shown["semantic_junction_handle"] in shown["visible_handles"]
    assert shown["author_ruling_handle"] in shown["visible_handles"]
    assert shown["semantic_junction_status"] == "UNKNOWN"
    assert shown["author_ruling_status"] == "REFUSED"

    current = front_carrier.currentness(
        served, producers=_producers(), embedding_health=_health(),
        semantic_junction=semantic, author_ruling=ruling,
    )
    assert current["status"] == "CURRENT"
    assert current["semantic_junction_status"] == "UNKNOWN"
    assert current["author_ruling_status"] == "REFUSED"

    moved = copy.deepcopy(semantic)
    moved["status"] = "REFUSED"
    stale = front_carrier.currentness(
        served, producers=_producers(), embedding_health=_health(),
        semantic_junction=moved, author_ruling=ruling,
    )
    assert stale["status"] == "STALE"
    assert {"model_preimage", "shown_preimage"} <= set(stale["mismatches"])


def test_optional_evidence_faces_fail_closed_on_wrong_schema_or_untyped_state() -> None:
    model = front_carrier.project(
        producers=_producers(), embedding_health=_health(),
        semantic_junction={"schema_version": "wrong/1", "status": "CURRENT"},
        author_ruling={
            "schema_version": "laplace.aisthesis-author-ruling/1",
            "status": "invented",
        },
    )
    assert model["semantic_junction"]["status"] == "REFUSED"
    assert model["author_ruling"]["status"] == "REFUSED"
    assert model["semantic_junction"]["semantic_junction_handle"].startswith("sha256:")
    assert model["author_ruling"]["author_ruling_handle"].startswith("sha256:")

    hostile = _semantic_junction()
    hostile["semantic_junction_handle"] = "sha256:" + "0" * 64
    normalized = front_carrier.project(
        producers=_producers(), embedding_health=_health(), semantic_junction=hostile,
    )["semantic_junction"]
    without_handle = dict(normalized)
    supplied_handle = without_handle.pop("semantic_junction_handle")
    assert supplied_handle == front_carrier.canonical_handle(without_handle)


def test_missing_shared_health_is_honest_unknown_with_exact_dependency() -> None:
    model = front_carrier.project(producers=_producers())
    memory = model["semantic_memory"]
    assert memory["state"] == "UNKNOWN"
    assert memory["health_status"] == "ABSENT"
    assert memory["S"] == {"commit": None, "tree": None}
    assert memory["F"] == {"commit": None, "tree": None}
    assert any(row["code"] == "EMBEDDING_HEALTH_ABSENT" for row in memory["omissions"])
    assert memory["exact_descent"]["health_schema"] == "laplace.embedding-health/1"


def test_current_requires_typed_forward_link_not_endpoint_equality() -> None:
    health = _health()
    del health["fold"]["forward_relation"]
    memory = front_carrier.semantic_memory(health)
    assert memory["health_status"] == "REFUSED"
    assert memory["state"] == "UNKNOWN"
    assert any(row["code"] == "FALSE_CURRENTNESS_REFUSED" for row in memory["omissions"])


def test_current_refuses_partial_artifact_or_source_class_family() -> None:
    health = _health()
    health["artifacts"]["cache_sidecar_consistent"] = False
    health["coverage"]["classes"] = [
        row for row in health["coverage"]["classes"]
        if row["source_class"] != "seat-profiles-goals-bindings"
    ]
    memory = front_carrier.semantic_memory(health)
    assert memory["state"] == "UNKNOWN"
    assert memory["health_status"] == "REFUSED"
    assert any(row["code"] == "SEMANTIC_SOURCE_CLASS_ABSENT" for row in memory["omissions"])


def test_update_due_is_stale_or_in_flight_from_exact_cadence() -> None:
    stale = _health(status="UPDATE-DUE", source="9" * 40)
    stale["cadence"]["queued"] = False
    stale["cadence"]["running"] = None
    assert front_carrier.semantic_memory(stale)["state"] == "STALE"
    stale["cadence"]["queued"] = True
    assert front_carrier.semantic_memory(stale)["state"] == "IN_FLIGHT"


def test_semantic_memory_exposes_required_health_dimensions_and_descent() -> None:
    memory = front_carrier.semantic_memory(_health())
    assert memory["state"] == "CURRENT"
    assert {row["source_class"] for row in memory["source_classes"]} == {
        "devmap", "Atlas", "lifecycle", "Fabric", "custody", "seats",
    }
    assert memory["coverage"]["node"]["count"] == 23217
    assert memory["coverage"]["vector"]["count"] == 24872
    assert memory["coverage"]["cluster"]["count"] == 2487
    assert memory["runtime"]["model"] == "model-1"
    assert memory["runtime"]["device"] == "cuda:0"
    assert memory["queue_active_act"]["queue_key"] == "fold:f"
    assert memory["consumption"] == {"last_wake": "wake-1", "last_descent": "descent-1"}
    assert memory["exact_descent"]["manifest_handle"] == "sha256:" + "a" * 64
    assert memory["active_source"] == memory["S"]
    assert memory["semantic_ref"] == {
        "name": "refs/eigen/semantic-fold",
        "commit": "f" * 40,
        "tree": "2" * 40,
    }


def test_provisional_producer_face_keeps_source_and_side_ref_distinct() -> None:
    health = _health()
    memory = front_carrier.semantic_memory(health)

    assert memory["health_status"] == "CURRENT"
    assert memory["S"] == {"commit": "c" * 40, "tree": "1" * 40}
    assert memory["active_source"] == memory["S"]
    assert memory["F"] == {"commit": "f" * 40, "tree": "2" * 40}
    assert memory["active_source"] != memory["F"]
    assert memory["source_tuple_status"] == "VERIFIED"
    assert memory["artifacts"]["cache_sidecar_consistent"] is True
    assert len(memory["semantic_reachability"]) == 6


def test_moved_atlas_or_profile_source_tuple_refuses_false_current() -> None:
    moved_atlas = _health()
    moved_atlas["source_currentness"]["source_tuple"]["atlas"]["drift_token"]["cursor"] += 1
    atlas_memory = front_carrier.semantic_memory(moved_atlas)
    assert atlas_memory["health_status"] == "REFUSED"
    assert atlas_memory["state"] == "UNKNOWN"

    moved_profile = _health()
    moved_profile["source_currentness"]["source_tuple"]["profile_handles"]["ego"] = (
        "sha256:" + "0" * 64
    )
    profile_memory = front_carrier.semantic_memory(moved_profile)
    assert profile_memory["health_status"] == "REFUSED"
    assert profile_memory["state"] == "UNKNOWN"

    producer_moved = _health()
    producer_moved["source_currentness"].update({
        "status": "MOVED",
        "active_source_tuple_handle": "sha256:" + "0" * 64,
        "moved_fields": ["atlas", "profile_handles.ego"],
    })
    moved_memory = front_carrier.semantic_memory(producer_moved)
    assert moved_memory["health_status"] == "REFUSED"
    assert moved_memory["state"] == "UNKNOWN"


def test_wrong_semantic_side_ref_or_incomplete_witness_refuses_current() -> None:
    wrong_f = _health()
    wrong_f["side_refs"]["refs/eigen/semantic-fold"]["commit"] = "0" * 40
    assert front_carrier.semantic_memory(wrong_f)["health_status"] == "REFUSED"

    route_only = _health()
    route_only["semantic_reachability"][0]["exact_content_status"] = "BUDGET"
    assert front_carrier.semantic_memory(route_only)["health_status"] == "REFUSED"


def test_shown_and_currentness_are_rederived_from_complete_preimages() -> None:
    producers = _producers()
    health = _health()
    served = front_carrier.project(
        producers=producers, embedding_health=health, binding_observation=_binding(),
        lens="conversation",
        focus="turn:1", edge="edge:1", grade="audit", exposition="E6", viewport="narrow",
    )
    shown = served["shown_state"]
    assert shown["shown_handle"] == front_carrier.canonical_handle(shown["shown_preimage"])
    assert shown["room"] == "Conversation"
    assert shown["raw_selection"]["lens"] == "conversation"
    current = front_carrier.currentness(
        served, producers=producers, embedding_health=health,
        binding_observation=_binding(),
    )
    assert current["status"] == "CURRENT"
    assert current["mismatches"] == []
    assert current["served_preimage"] == current["rederived_preimage"]

    moved = copy.deepcopy(producers)
    moved["conversation"]["value"] = "moved"
    stale = front_carrier.currentness(
        served, producers=moved, embedding_health=health,
        binding_observation=_binding(),
    )
    assert stale["status"] == "STALE"
    assert "model_preimage" in stale["mismatches"]
    assert "shown_preimage" in stale["mismatches"]


def test_forged_shown_handle_and_missing_preimage_do_not_pass_currentness() -> None:
    producers = _producers()
    health = _health()
    served = front_carrier.project(producers=producers, embedding_health=health)
    forged = copy.deepcopy(served)
    forged["shown_state"]["shown_handle"] = "sha256:" + "0" * 64
    assert front_carrier.currentness(
        forged, producers=producers, embedding_health=health,
    )["status"] == "STALE"
    del forged["shown_state"]["shown_preimage"]
    assert front_carrier.currentness(
        forged, producers=producers, embedding_health=health,
    )["status"] == "REFUSED"


def test_absent_room_projection_is_a_hashed_omission_not_an_empty_success() -> None:
    producers = _producers()
    del producers["work"]
    model = front_carrier.project(producers=producers, embedding_health=_health(), room="Work")
    assert model["active_room"]["status"] == "UNKNOWN"
    omission = model["active_room"]["omissions"][0]
    assert omission["code"] == "ROOM_PRODUCER_ABSENT"
    assert omission["omission_handle"] == front_carrier.canonical_handle({
        key: value for key, value in omission.items() if key != "omission_handle"
    })


def test_projection_performs_no_file_or_authority_write(monkeypatch) -> None:
    def forbidden_open(*_args, **_kwargs):
        raise AssertionError("front carrier attempted filesystem access")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    model = front_carrier.project(producers=_producers(), embedding_health=_health())
    assert model["authority"]["write_paths"] == []
    assert model["semantic_memory"]["authority_effect"] == "none"


def test_binding_observatory_never_equates_routing_with_loaded_context() -> None:
    routed = front_carrier.binding_observatory(_binding(with_receipt=False))
    assert routed["status"] == "ROUTING-ONLY"
    assert routed["injected_context_currentness"] == "UNKNOWN"
    assert any(row["code"] == "ENFORCED_DESCENT_RECEIPT_ABSENT"
               for row in routed["omissions"])

    absent = front_carrier.binding_observatory(None)
    assert absent["status"] == "UNKNOWN"
    assert any(row["code"] == "BINDING_OBSERVATORY_ABSENT"
               for row in absent["omissions"])


def test_binding_observatory_exposes_exact_descent_and_fog() -> None:
    face = front_carrier.binding_observatory(_binding())
    assert face["status"] == "DESCENDED"
    assert face["selected"] == {
        "seat": "sensorium-seat", "turn": "turn:1", "task": "task:1",
    }
    assert face["regions"]["unvisited"] == ["r3"]
    assert face["fog"][0]["class"] == "BOUNDARY_RESIDUAL"
    assert face["last_enforced_descent"]["receipt"] == "sha256:" + "6" * 64
    assert face["authority_effect"] == "none"


def test_parity_and_crutch_rows_are_source_bearing_and_measurably_retirable() -> None:
    model = front_carrier.project(producers=_producers(), embedding_health=_health())
    assert all(row["source_node"] and row["source_handle"].startswith("sha256:")
               for row in model["parity_evidence"])
    assert {row["decision"] for row in model["parity_evidence"]} <= {
        "KEEP", "TRANSFORM", "SUBMERGE", "RETIRE",
    }
    assert all(row["pass_predicate"] and row["missing_implementation_proof"]
               for row in model["parity_evidence"])
    assert {row["capability"] for row in model["parity_evidence"]} >= {
        "author conversation and Fabric custody",
        "manuscript reading, editing and exact source descent",
        "manuscript conception, spine and incremental build",
        "talk conception, motivated spine, staging and rendered verification",
    }
    assert all(row["retirement_predicate"] for row in model["owned_crutches"])
    assert {row["id"] for row in model["owned_crutches"]} >= {
        "CR-AIS-STREAM-500MS", "CR-AIS-SHADOW-FOUR-PANE",
        "CR-AIS-CARRIER-HOST-ASSUMPTIONS",
        "CR-review-frontier-terminal-aggregate-without-authoritative-root",
    }


def test_fabric_observatory_keeps_delivery_attention_and_fallback_disjoint() -> None:
    face = front_carrier.fabric_observatory(_fabric(), _direct_coordination())
    assert face["schema_version"] == "laplace.aisthesis-fabric-observatory/1"
    assert [row["phase"] for row in face["canonical"]["phases"]] == [
        "send", "queued", "pull", "typed-reconstruction",
        "acknowledgement", "delivered", "reply",
    ]
    assert [row["state"] for row in face["canonical"]["phases"]] == ["COMPLETE"] * 7
    assert face["canonical"]["state"] == "COMPLETE"
    assert face["watcher_attention"]["state"] == "ACTIVE"
    assert face["watcher_attention"]["delivery_claim"] is False
    assert face["external_direct_fallback"]["mode"] == "EXTERNAL-DIRECT-COORDINATION"
    assert face["external_direct_fallback"]["delivery_claim"] is False
    assert face["external_direct_fallback"]["acknowledgement_claim"] is False
    assert face["external_direct_fallback"]["canonical_claims"] == {
        "send": False,
        "pull": False,
        "reconstruction": False,
        "acknowledgement": False,
        "reply": False,
    }
    assert face["external_direct_fallback"]["message_ref"] == "direct-message:1"
    assert face["external_direct_fallback"]["body_digest"] == "sha256:" + "7" * 64


def test_watcher_and_fallback_cannot_complete_an_absent_canonical_flow() -> None:
    observation = _fabric()
    del observation["canonical"]
    observation["watcher"]["state"] = "COMPLETE"
    face = front_carrier.fabric_observatory(observation, _direct_coordination())
    assert face["canonical"]["state"] == "UNKNOWN"
    assert {row["state"] for row in face["canonical"]["phases"]} == {"UNKNOWN"}
    assert face["watcher_attention"]["delivery_claim"] is False
    assert face["external_direct_fallback"]["delivery_claim"] is False
    assert face["external_direct_fallback"]["acknowledgement_claim"] is False
    assert any(row["code"] == "FABRIC_CANONICAL_OBSERVATION_ABSENT"
               for row in face["omissions"])


def test_active_direct_fallback_keeps_missing_message_and_body_provenance_unknown() -> None:
    fallback = _direct_coordination()
    fallback["message_ref"] = None
    fallback["body_digest"] = None
    face = front_carrier.fabric_observatory(_fabric(), fallback)
    assert face["external_direct_fallback"]["state"] == "ACTIVE"
    assert face["external_direct_fallback"]["provenance_state"] == "UNKNOWN"
    assert face["external_direct_fallback"]["delivery_claim"] is False
    assert face["external_direct_fallback"]["acknowledgement_claim"] is False
    assert any(row["code"] == "DIRECT_COORDINATION_PROVENANCE_INCOMPLETE"
               for row in face["omissions"])


def test_fabric_loss_budget_preserves_exact_recoverable_and_forbidden_boundary() -> None:
    face = front_carrier.fabric_observatory(_fabric(), _direct_coordination())
    assert face["loss_budget"] == {
        "recoverable": [
            "dropped watcher nudge",
            "delayed attention",
            "missed telemetry sample",
            "temporary interface unavailability",
        ],
        "forbidden": [
            "canonical message or body loss",
            "false acknowledgement",
            "duplicate action",
            "wrong-seat routing",
            "custody loss",
            "source or authority corruption",
        ],
    }
    assert not (set(face["loss_budget"]["recoverable"])
                & set(face["loss_budget"]["forbidden"]))


def test_fabric_input_movement_invalidates_model_and_shown_currentness() -> None:
    producers = _producers()
    health = _health()
    fabric = _fabric()
    direct = _direct_coordination()
    served = front_carrier.project(
        producers=producers,
        embedding_health=health,
        fabric_observation=fabric,
        direct_coordination=direct,
        lens="conversation",
        focus="turn:1",
        grade="near",
    )
    assert front_carrier.currentness(
        served,
        producers=producers,
        embedding_health=health,
        fabric_observation=fabric,
        direct_coordination=direct,
    )["status"] == "CURRENT"

    moved_fabric = copy.deepcopy(fabric)
    moved_fabric["watcher"]["current_implementation"] = "implementation:2"
    moved = front_carrier.currentness(
        served,
        producers=producers,
        embedding_health=health,
        fabric_observation=moved_fabric,
        direct_coordination=direct,
    )
    assert moved["status"] == "STALE"
    assert {"model_preimage", "model_handle", "shown_preimage", "shown_handle"} <= set(
        moved["mismatches"]
    )

    moved_direct = copy.deepcopy(direct)
    moved_direct["body_digest"] = "sha256:" + "9" * 64
    moved = front_carrier.currentness(
        served,
        producers=producers,
        embedding_health=health,
        fabric_observation=fabric,
        direct_coordination=moved_direct,
    )
    assert moved["status"] == "STALE"
    assert "shown_preimage" in moved["mismatches"]
