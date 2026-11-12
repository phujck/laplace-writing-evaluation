from __future__ import annotations

import copy
import hashlib
import json

from laplace.engine.front_semantic_junction import ATLAS_LINEAGE_SCHEMA, BOUNDED_DOWN_SCHEMA, CANONICAL_UP_FAMILY_SCHEMA, COMPACT_FOLD_SCHEMA, MEANING_UPFOLD_SCHEMA, OUTER_FOLD_VERIFICATION_SCHEMA, REGISTER_DICTIONARY_SCHEMA, REGISTER_MEASUREMENT_SCHEMA, SEMANTIC_JUNCTION_SCHEMA, TYPED_DESCENT_COVERAGE_SCHEMA, embedding_health_side_ref, expand_register_opcode, project_semantic_junction


def _h(name: str) -> str:
    return "sha256:" + (name.encode("utf-8").hex() + "0" * 64)[:64]


def _residual(subject: str = "promotion") -> dict[str, object]:
    return {
        "class": "REPRESENTATION",
        "state": "RESOLVED",
        "code": "REPRESENTATION_WITHIN_PHI",
        "subject": subject,
        "meaning": "The retained frame is within the declared residual dial",
        "count": 0,
        "budget": {"chi": 3, "phi": 0.1},
        "continuation": "Open the retained-frame evidence",
        "receipt_handle": _h("residual"),
    }


def _typed(name: str, emitted: int) -> dict[str, object]:
    return {
        "schema_version": TYPED_DESCENT_COVERAGE_SCHEMA,
        "status": "COMPLETE",
        "emitted_count": emitted,
        "typed_count": emitted,
        "untyped_count": 0,
        "receipt_handle": _h(f"{name}-type-coverage"),
        "target_registry_handle": _h("target-registry"),
        "emitted_root": _h(f"{name}-emitted"),
        "typed_root": _h(f"{name}-typed"),
        "kinds": [{
            "kind": "semantic-fold-object" if name == "fold" else "atlas-object",
            "count": emitted,
            "root": _h(f"{name}-kind"),
        }],
        "continuation": "Open the target-registry totality receipt",
    }


def _atlas() -> dict[str, object]:
    members = [_h("leaf-a"), _h("leaf-b"), _h("leaf-c")]
    return {
        "schema_version": ATLAS_LINEAGE_SCHEMA,
        "status": "CURRENT",
        "summary": "The latest local semantic promotion and prolongation",
        "receipt_handle": _h("atlas-lineage"),
        "event_handle": _h("atlas-event"),
        "operator_generation": _h("atlas-generation"),
        "latest_operation": {
            "kind": "UP then DOWN",
            "from_grade": "leaf evidence",
            "to_grade": "coarse semantic node",
            "assumption": "source-bearing reconstruction",
            "fibre": "repository meaning",
            "representation": "representation sufficient; goal closure measured separately",
            "act_handle": _h("up-act"),
            "node_handle": _h("node"),
            "metric_version": _h("metric"),
            "grade_contract": _h("grade"),
        },
        "reach": {
            "leaf_handles": list(members),
            "member_handles": list(members),
            "cluster_handles": [_h("cluster")],
        },
        "latest_down": {
            "schema_version": "atlas.down-history-act/1",
            "receipt_handle": _h("down-receipt"),
            "act_handle": _h("down-act"),
            "event_handle": _h("down-event"),
            "node_handle": _h("node"),
            "member_handles": list(members),
            "reconstructed_handles": list(members),
            "verified_handles": list(members),
            "round_trip_residual": 0.025,
            "originals_supplied": True,
            "verified": True,
            "route_only": False,
            "continuation": "Inspect the exact child reconstruction",
        },
        "typed_descent": _typed("atlas", 4),
        "residuals": [_residual()],
    }


def _meaning() -> dict[str, object]:
    return {
        "schema_version": MEANING_UPFOLD_SCHEMA,
        "status": "CURRENT",
        "summary": "Incremental whole-repository concept-tree fold",
        "receipt_handle": _h("meaning-tree"),
        "event_handle": _h("meaning-trigger"),
        "operator_generation": _h("meaning-generation"),
        "latest_operation": {
            "kind": "incremental concept-tree fold",
            "from_grade": "repository residue",
            "to_grade": "clustered meaning tree",
            "assumption": "repository-wide semantic reach",
            "fibre": "whole-system meaning",
            "representation": "local cluster lineages retained",
            "act_handle": _h("fold-act"),
            "node_handle": _h("tree-root"),
            "metric_version": _h("embedder"),
            "grade_contract": _h("tree-grade"),
        },
        "reach": {
            "leaf_handles": [_h("source-a"), _h("source-b")],
            "member_handles": [_h("member-a"), _h("member-b")],
            "cluster_handles": [_h("family")],
        },
        "typed_descent": _typed("meaning", 3),
        "residuals": [{
            "class": "OMISSION",
            "state": "OPEN",
            "code": "UNVISITED_SOURCE_CLASS",
            "subject": "non-local source",
            "meaning": "One admitted source family has not yet entered this fold",
            "count": 1,
            "budget": None,
            "continuation": "Continue through the fold coverage receipt",
            "receipt_handle": _h("meaning-residual"),
        }],
    }


def _fold(*, status: str = "CURRENT", current: str = "F") -> dict[str, object]:
    coordinates = {
        "S": _h("source-root"),
        "F": _h("fold-root"),
        "G": _h("later-root"),
    }
    receipt = _h("fold-receipt")
    source_root = coordinates["S"]
    successor_root = coordinates["F"]
    membership_root = _h("membership")
    return {
        "schema_version": COMPACT_FOLD_SCHEMA,
        "status": status,
        "source_root": source_root,
        "successor_root": successor_root,
        "current_source_root": coordinates[current],
        "successor_of": source_root,
        "receipt_handle": receipt,
        "source_class_receipts_root": _h("source-classes"),
        "leaf_object_root": _h("leaf-objects"),
        "leaf_content_root": _h("leaf-content"),
        "membership_root": membership_root,
        "cluster_root": _h("clusters"),
        "retained_state_root": _h("retained-state"),
        "semantic_source_root": _h("semantic-sources"),
        "descent_index_root": _h("descent-index"),
        "residual_root": _h("residuals"),
        "fog_omission_root": _h("fog"),
        "artifact_family_root": _h("artifact-family"),
        "register_dictionary_root": _h("register-dictionary"),
        "predecessor_fold_root": _h("predecessor-fold"),
        "outer_verification": {
            "schema_version": OUTER_FOLD_VERIFICATION_SCHEMA,
            "status": "VERIFIED",
            "receipt_handle": receipt,
            "verification_receipt_handle": _h("outer-verification"),
            "sole_parent_root": source_root,
            "successor_root": successor_root,
            "candidate_manifest_root": _h("candidate-manifest"),
            "candidate_validated": True,
            "artifact_family_coherent": True,
            "canonical_up_verified": True,
            "down_index_verified": True,
            "runtime_verified": True,
            "source_unchanged": True,
            "deferred_count": 0,
            "continuation": "Open the outer receipt verification",
        },
        "canonical_up": {
            "schema_version": CANONICAL_UP_FAMILY_SCHEMA,
            "status": "VERIFIED",
            "cluster_count": 821,
            "verified_cluster_count": 821,
            "unverified_cluster_count": 0,
            "membership_root": membership_root,
            "family_root": _h("up-family"),
            "receipt_rows_root": _h("up-rows"),
            "node_handle_root": _h("up-nodes"),
            "up_act_handle_root": _h("up-acts"),
            "up_receipt_handle_root": _h("up-receipts"),
            "verification_receipt_handle": _h("up-verification"),
            "continuation": "Open the canonical UP family",
        },
        "bounded_down": {
            "schema_version": BOUNDED_DOWN_SCHEMA,
            "status": "COMPLETE",
            "fold_receipt_handle": receipt,
            "down_result_handle": _h("bounded-down-result"),
            "up_act_handle": _h("bounded-up-act"),
            "up_receipt_handle": _h("bounded-up-receipt"),
            "row_hash": _h("bounded-row"),
            "requested_count": 3,
            "reconstructed_count": 3,
            "verified_count": 3,
            "shards_read": 1,
            "rows_read": 1,
            "originals_supplied": True,
            "verified": True,
            "round_trip_residual": 0.025,
            "route_only": False,
            "continuation": "Open the exact bounded DOWN result",
        },
        "lag_commits": 0 if current == "F" else 1,
        "coverage": {"leaves": 23217, "members": 24872, "clusters": 821},
        "typed_descent": _typed("fold", 24038),
        "residuals": [{
            "class": "COVERAGE",
            "state": "RESOLVED",
            "code": "REQUIRED_CLASSES_COMPLETE",
            "subject": "semantic source coverage",
            "meaning": "Every required source class is represented",
            "count": 6,
            "budget": None,
            "continuation": "Open the exact coverage receipt",
            "receipt_handle": _h("coverage"),
        }],
    }


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _embedding_health() -> dict[str, object]:
    source = {"commit": "c" * 40, "tree": "1" * 40}
    successor = {"commit": "f" * 40, "tree": "2" * 40}
    profiles = {
        "aisthesis": _h("profile-aisthesis"),
        "ego": _h("profile-ego"),
        "superego": _h("profile-superego"),
    }
    atlas = {
        "schema_version": "laplace.semantic-atlas-currentness-token/1",
        "drift_token": {
            "schema_version": "laplace.atlas-drift-token/1",
            "cursor": 3300,
            "head_event_id": _h("atlas-event"),
            "head_record_digest": _h("atlas-record"),
        },
        "effective_checkpoint_digest": _h("checkpoint"),
        "authority_roots": {"seat_occupancy_root": _h("occupancy")},
        "integrity_boundary": "CURRENT",
    }
    atlas["token_handle"] = _digest(atlas)
    source_tuple = {
        "schema_version": "laplace.semantic-fold-source-tuple/1",
        "git": source,
        "atlas": atlas,
        "coverage_contract": {
            "schema_version": "laplace.semantic-source-coverage/1",
            "required_classes": ["development-work-map"],
        },
        "profile_heads_handle": _h("profile-heads"),
        "profile_heads": {},
        "profile_handles": profiles,
        "goal_context_handle": _h("goal-context"),
        "policy_roots": {"design": _h("design")},
        "builder": {
            "entry": "scripts/semantic_cadence.py --worker",
            "law_generation": "canonical-up-down-outer-receipt/1",
            "required_gpu": True,
        },
    }
    source_tuple["source_tuple_handle"] = _digest(source_tuple)
    receipt = _h("outer-receipt")
    index = _h("fold-index")
    register = _h("register-generation")
    return {
        "schema_version": "laplace.embedding-health/1",
        "status": "CURRENT",
        "ui_status": "CURRENT",
        "shared": True,
        "non_blocking": True,
        "authority_effect": "none",
        "current_source": source,
        "source_currentness": {
            "status": "CURRENT",
            "source_tuple": source_tuple,
            "claimed_source_tuple_handle": source_tuple["source_tuple_handle"],
            "active_source_tuple_handle": source_tuple["source_tuple_handle"],
            "moved_fields": [],
        },
        "side_refs": {
            "refs/eigen/semantic-fold": {
                "ref": "refs/eigen/semantic-fold", **successor,
            },
            "refs/eigen/semantic-fold-receipt": {
                "ref": "refs/eigen/semantic-fold-receipt",
                "receipt_handle": receipt,
            },
        },
        "fold": {
            "source_commit": source["commit"],
            "source_tree": source["tree"],
            "output_commit": successor["commit"],
            "output_tree": successor["tree"],
            "forward_relation": "EXACT",
            "semantic_horizon": {
                "source_commit": source["commit"],
                "source_tree": source["tree"],
                "atlas_cursor": 3300,
                "atlas_head_event_id": _h("atlas-event"),
                "nodes": 100,
                "clusters": 8,
                "leaves": 92,
            },
            "lag_commits": 0,
            "manifest_handle": _h("manifest"),
            "coverage_handle": _h("coverage"),
            "semantic_fold_receipt_handle": receipt,
            "semantic_fold_index_handle": index,
            "semantic_register_generation": register,
        },
        "up_down": {
            "status": "CANONICAL-UP-BATCH-READ-ONLY-DOWN",
            "receipt_handle": receipt,
            "index_handle": index,
            "register_generation": register,
            "entries": 100,
        },
        "coverage": {
            "required_complete": True,
            "classes": [{
                "source_class": "development-work-map",
                "count": 1,
                "root": _h("devmap"),
                "admitted": True,
                "omitted": 0,
                "reason": "complete canonical projection admitted",
            }],
        },
        "profile_handles": profiles,
        "artifacts": {
            "root": _h("artifacts"),
            "count": 12,
            "bytes": 4096,
            "cache_sidecar_consistent": True,
        },
        "latest_receipt": {
            "full_requested": True,
            "mode": "full-rebuild",
            "embedding_counts": {"deferred": 0, "total": 100},
        },
        "semantic_reachability": [{
            "query": "current development frontier",
            "router": "conceptric",
            "visited": 8,
            "expected_semantic_node": "OP-DEVELOPMENT-WORK-MAP",
            "reached": True,
            "exact_route": {
                "kind": "ledger-row",
                "reference": "OP-DEVELOPMENT-WORK-MAP",
                "source": "semantic_operational_sources",
            },
            "exact_content_handle": _h("devmap-content"),
            "exact_content_status": "COMPLETE",
            "descent_authority_write": "none",
        }],
    }


def _register() -> dict[str, object]:
    return {
        "schema_version": REGISTER_DICTIONARY_SCHEMA,
        "generation": "register-generation-7",
        "mode": "DICTIONARY",
        "allocation_algorithm": "benefit-descending-then-canonical-handle",
        "measurement": {
            "schema_version": REGISTER_MEASUREMENT_SCHEMA,
            "status": "MEASURED",
            "source": "persisted-token-frequency",
            "persisted_token_count": 39,
            "receipt_handle": _h("frequency"),
        },
        "entries": [
            {
                "opcode": "DESC",
                "kind": "operator",
                "meaning": "Reconstruct the exact finer-grained members",
                "count": 27,
                "canonical_bytes": 48,
                "encoded_bytes": 4,
                "canonical_handle": _h("down"),
                "evidence_handle": _h("down-frequency"),
            },
            {
                "opcode": "UNKN",
                "kind": "currentness",
                "meaning": "Evidence is not sufficient to assert the present state",
                "count": 12,
                "canonical_bytes": 64,
                "encoded_bytes": 4,
                "canonical_handle": _h("unknown"),
                "evidence_handle": _h("unknown-frequency"),
            },
        ],
    }


def _project(**changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "atlas_updown": _atlas(),
        "meaning_upfold": _meaning(),
        "compact_fold": _fold(),
        "register_dictionary": _register(),
        "active_register_generation": "register-generation-7",
    }
    values.update(changes)
    return project_semantic_junction(**values)  # type: ignore[arg-type]


def _without_audit(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_audit(item)
            for key, item in value.items()
            if key != "audit"
        }
    if isinstance(value, list):
        return [_without_audit(item) for item in value]
    return value


def test_projection_keeps_the_two_lineages_distinct_and_human_facing() -> None:
    result = _project()

    assert result["schema_version"] == SEMANTIC_JUNCTION_SCHEMA
    assert result["status"] == "CURRENT"
    assert [row["kind"] for row in result["lineages"]] == [
        "CANONICAL_ATLAS_UP_DOWN",
        "WHOLE_SYSTEM_MEANING_UPFOLD",
    ]
    assert result["lineages"][0]["reach"]["leaves"]["count"] == 3
    assert result["lineages"][1]["reach"]["leaves"]["count"] == 2
    assert result["down_reconstruction"]["status"] == "COMPLETE"
    assert result["down_reconstruction"]["coverage_ratio"] == 1.0
    assert result["compact_fold"]["reach"]["members"]["count"] == 24872
    assert result["compact_fold"]["typed_descent"]["status"] == "COMPLETE"


def test_exact_identifiers_exist_only_in_the_audit_envelope() -> None:
    result = _project()
    resting = json.dumps(_without_audit(result), sort_keys=True)

    assert "sha256:" not in resting
    assert _h("atlas-event") not in resting
    assert result["audit"]["visibility"] == "AUDIT_ONLY"
    assert result["audit"]["atlas_up_down"]["event_handle"] == _h("atlas-event")
    assert str(result["audit"]["projection_handle"]).startswith("sha256:")


def test_absent_producers_are_unknown_not_empty_successes() -> None:
    result = project_semantic_junction(
        atlas_updown=None,
        meaning_upfold=None,
        compact_fold=None,
        register_dictionary=None,
        active_register_generation=None,
    )

    assert result["status"] == "UNKNOWN"
    assert all(row["status"] == "UNKNOWN" for row in result["lineages"])
    assert result["compact_fold"]["status"] == "UNKNOWN"
    assert result["down_reconstruction"]["requested"] is None
    assert result["register_dictionary"]["entries"] == []
    assert result["register_dictionary"]["frequency_basis"] == "UNKNOWN"


def test_forged_down_membership_refuses_coverage() -> None:
    atlas = _atlas()
    atlas["latest_down"]["reconstructed_handles"].append(_h("not-a-member"))
    result = _project(atlas_updown=atlas)

    assert result["down_reconstruction"]["status"] == "REFUSED"
    assert result["down_reconstruction"]["coverage_ratio"] is not None


def test_canonical_down_without_originals_is_truthfully_unverified() -> None:
    atlas = _atlas()
    down = atlas["latest_down"]
    down["originals_supplied"] = False
    down["verified"] = False
    down["verified_handles"] = []
    down["round_trip_residual"] = None
    result = _project(atlas_updown=atlas)

    assert result["down_reconstruction"]["status"] == "COMPLETE"
    assert result["down_reconstruction"]["verification"] == "UNVERIFIED"


def test_down_route_metadata_cannot_count_as_reconstruction() -> None:
    atlas = _atlas()
    atlas["latest_down"]["route_only"] = True
    result = _project(atlas_updown=atlas)

    assert result["down_reconstruction"]["status"] == "REFUSED"
    assert result["down_reconstruction"]["verification"] == "REFUSED"


def test_duplicate_reach_handles_refuse_a_claimed_current_lineage() -> None:
    atlas = _atlas()
    atlas["reach"]["leaf_handles"] = [_h("same"), _h("same")]
    result = _project(atlas_updown=atlas)

    assert result["lineages"][0]["status"] == "REFUSED"
    assert result["status"] == "REFUSED"


def test_unknown_residual_class_fails_a_current_lineage_closed() -> None:
    meaning = _meaning()
    meaning["residuals"][0]["class"] = "DECORATIVE_HAZE"
    result = _project(meaning_upfold=meaning)

    assert result["lineages"][1]["status"] == "REFUSED"
    assert result["lineages"][1]["residuals"][0]["state"] == "REFUSED"


def test_false_current_fold_without_exact_successor_match_refuses() -> None:
    result = _project(compact_fold=_fold(status="CURRENT", current="G"))

    assert result["compact_fold"]["status"] == "REFUSED"
    assert result["status"] == "REFUSED"


def test_embedding_health_side_ref_keeps_live_source_s_and_semantic_f_distinct() -> None:
    health = _embedding_health()
    proof = embedding_health_side_ref(health)

    assert proof["status"] == "CURRENT"
    assert proof["active_source"] == proof["S"]
    assert proof["active_source"] != proof["F"]
    assert proof["semantic_ref"] == {
        "name": "refs/eigen/semantic-fold",
        "commit": "f" * 40,
        "tree": "2" * 40,
    }
    result = _project(compact_fold=health)
    assert result["compact_fold"]["status"] == "CURRENT"
    assert result["compact_fold"]["outer_verification"]["status"] == "VERIFIED"
    assert result["status"] == "CURRENT"


def test_embedding_health_side_ref_accepts_current_source_tuple_v2() -> None:
    health = _embedding_health()
    source_tuple = health["source_currentness"]["source_tuple"]
    source_tuple["schema_version"] = "laplace.semantic-fold-source-tuple/2"
    source_tuple["source_tuple_handle"] = _digest({
        key: value for key, value in source_tuple.items() if key != "source_tuple_handle"
    })
    health["source_currentness"]["claimed_source_tuple_handle"] = source_tuple[
        "source_tuple_handle"
    ]
    health["source_currentness"]["active_source_tuple_handle"] = source_tuple[
        "source_tuple_handle"
    ]

    proof = embedding_health_side_ref(health)

    assert proof["status"] == "CURRENT"
    assert proof["source_tuple_status"] == "VERIFIED"


def test_embedding_health_moved_source_tuple_and_wrong_f_fail_closed() -> None:
    moved = _embedding_health()
    moved["source_currentness"]["status"] = "MOVED"
    moved["source_currentness"]["active_source_tuple_handle"] = _h("later-tuple")
    moved["source_currentness"]["moved_fields"] = ["atlas", "profile_handles.ego"]
    assert embedding_health_side_ref(moved)["status"] == "REFUSED"
    assert _project(compact_fold=moved)["compact_fold"]["status"] == "REFUSED"

    wrong_f = _embedding_health()
    wrong_f["side_refs"]["refs/eigen/semantic-fold"]["commit"] = "0" * 40
    assert embedding_health_side_ref(wrong_f)["status"] == "REFUSED"
    assert _project(compact_fold=wrong_f)["status"] == "REFUSED"


def test_current_fold_without_typed_descent_totality_refuses() -> None:
    fold = _fold()
    fold.pop("typed_descent")
    result = _project(compact_fold=fold)

    assert result["compact_fold"]["status"] == "REFUSED"
    assert result["compact_fold"]["typed_descent"]["status"] == "UNKNOWN"
    assert result["compact_fold"]["reach"]["leaves"]["status"] == "UNKNOWN"


def test_current_fold_with_a_missing_coherent_family_root_refuses() -> None:
    fold = _fold()
    fold.pop("descent_index_root")
    result = _project(compact_fold=fold)

    assert result["compact_fold"]["status"] == "REFUSED"
    assert result["status"] == "REFUSED"


def test_current_fold_requires_verified_outer_receipt_and_canonical_up_family() -> None:
    no_outer = _fold()
    no_outer.pop("outer_verification")
    outer_result = _project(compact_fold=no_outer)
    assert outer_result["compact_fold"]["status"] == "REFUSED"
    assert outer_result["compact_fold"]["outer_verification"]["status"] == "UNKNOWN"

    no_up = _fold()
    no_up.pop("canonical_up")
    up_result = _project(compact_fold=no_up)
    assert up_result["compact_fold"]["status"] == "REFUSED"
    assert up_result["compact_fold"]["canonical_up_membership"]["status"] == "UNKNOWN"

    forged_membership = _fold()
    forged_membership["canonical_up"]["membership_root"] = _h("other-membership")
    forged_result = _project(compact_fold=forged_membership)
    assert forged_result["compact_fold"]["canonical_up_membership"]["status"] == "REFUSED"


def test_bounded_down_distinguishes_verified_unverified_and_route_only() -> None:
    verified = _project()
    down = verified["compact_fold"]["bounded_down"]
    assert down["status"] == "COMPLETE"
    assert down["verification"] == "VERIFIED"
    assert down["shards_read"] == down["rows_read"] == 1

    unverified_fold = _fold()
    unverified = unverified_fold["bounded_down"]
    unverified["originals_supplied"] = False
    unverified["verified"] = False
    unverified["verified_count"] = 0
    unverified["round_trip_residual"] = None
    unverified_result = _project(compact_fold=unverified_fold)
    assert unverified_result["compact_fold"]["bounded_down"]["verification"] == "UNVERIFIED"

    route_fold = _fold()
    route = route_fold["bounded_down"]
    route["route_only"] = True
    route_result = _project(compact_fold=route_fold)
    assert route_result["compact_fold"]["bounded_down"]["status"] == "REFUSED"
    assert route_result["compact_fold"]["bounded_down"]["reconstructed"] == 3

    budget_fold = _fold()
    budget = budget_fold["bounded_down"]
    budget["status"] = "BUDGET"
    budget["reconstructed_count"] = 0
    budget["verified_count"] = 0
    budget["originals_supplied"] = False
    budget["verified"] = False
    budget["round_trip_residual"] = None
    budget["down_result_handle"] = None
    budget["continuation_handle"] = _h("down-continuation")
    budget_result = _project(compact_fold=budget_fold)
    assert budget_result["compact_fold"]["bounded_down"]["status"] == "BUDGET"

    budget.pop("continuation_handle")
    route_only_budget = _project(compact_fold=budget_fold)
    assert route_only_budget["compact_fold"]["bounded_down"]["status"] == "REFUSED"


def test_untyped_fold_handle_refuses_instead_of_counting_as_reachable() -> None:
    fold = _fold()
    coverage = fold["typed_descent"]
    coverage["typed_count"] -= 1
    coverage["untyped_count"] = 1
    coverage["kinds"][0]["count"] -= 1
    result = _project(compact_fold=fold)

    assert result["compact_fold"]["status"] == "REFUSED"
    assert result["compact_fold"]["typed_descent"]["status"] == "REFUSED"
    assert result["compact_fold"]["typed_descent"]["untyped"] == 1


def test_lineage_handle_counts_do_not_claim_reach_without_typed_routes() -> None:
    atlas = _atlas()
    atlas.pop("typed_descent")
    result = _project(atlas_updown=atlas)

    atlas_face = result["lineages"][0]
    assert atlas_face["status"] == "CURRENT"
    assert atlas_face["reach"]["leaves"] == {"status": "UNKNOWN", "count": 3}
    assert atlas_face["typed_descent"]["status"] == "UNKNOWN"


def test_explicit_unknown_type_coverage_stays_unknown_without_fabricated_counts() -> None:
    atlas = _atlas()
    atlas["typed_descent"] = {
        "schema_version": TYPED_DESCENT_COVERAGE_SCHEMA,
        "status": "UNKNOWN",
    }
    result = _project(atlas_updown=atlas)

    assert result["lineages"][0]["typed_descent"]["status"] == "UNKNOWN"
    assert result["lineages"][0]["typed_descent"]["typed"] is None


def test_a_later_source_move_is_update_due_when_the_producer_says_so() -> None:
    result = _project(compact_fold=_fold(status="UPDATE-DUE", current="G"))

    assert result["compact_fold"]["status"] == "UPDATE-DUE"
    assert result["status"] == "STALE"
    assert result["compact_fold"]["lag_commits"] == 1

    incomplete = _fold(status="UPDATE-DUE", current="G")
    incomplete.pop("artifact_family_root")
    refused = _project(compact_fold=incomplete)
    assert refused["compact_fold"]["status"] == "REFUSED"


def test_register_entries_are_observed_frequency_sorted_not_invented() -> None:
    result = _project()
    entries = result["register_dictionary"]["entries"]

    assert result["register_dictionary"]["status"] == "CURRENT"
    assert [row["opcode"] for row in entries] == ["DESC", "UNKN"]
    assert [row["count"] for row in entries] == [27, 12]
    assert result["register_dictionary"]["frequency_basis"] == "MEASURED_PERSISTED_TOKENS"

    register = _register()
    register["measurement"] = {
        "schema_version": REGISTER_MEASUREMENT_SCHEMA,
        "status": "MEASURED",
        "source": "route-metadata",
        "persisted_token_count": 39,
        "receipt_handle": _h("route-frequency"),
    }
    refused = _project(register_dictionary=register)
    assert refused["register_dictionary"]["status"] == "REFUSED"
    assert refused["register_dictionary"]["entries"] == []

    no_generation = _project(active_register_generation=None)
    assert no_generation["register_dictionary"]["status"] == "UNKNOWN"
    assert no_generation["register_dictionary"]["entries"] == []

    literal = _register()
    literal["mode"] = "LITERAL"
    literal["entries"] = []
    literal_result = _project(register_dictionary=literal)
    assert literal_result["register_dictionary"]["status"] == "LITERAL"
    assert literal_result["register_dictionary"]["entries"] == []

    invented = _register()
    invented["measurement"]["persisted_token_count"] = 1
    invented_result = _project(register_dictionary=invented)
    assert invented_result["register_dictionary"]["status"] == "REFUSED"

    reordered = _register()
    reordered["entries"].reverse()
    reordered_result = _project(register_dictionary=reordered)
    assert reordered_result["register_dictionary"]["status"] == "REFUSED"


def test_register_expansion_refuses_stale_generation() -> None:
    stale = expand_register_opcode(
        _register(),
        opcode="DESC",
        requested_generation="register-generation-6",
        active_generation="register-generation-7",
    )
    assert stale["status"] == "REFUSED"
    assert stale["audit"]["visibility"] == "AUDIT_ONLY"

    current = expand_register_opcode(
        _register(),
        opcode="DESC",
        requested_generation="register-generation-7",
        active_generation="register-generation-7",
    )
    assert current["status"] == "CURRENT"
    assert current["meaning"] == "Reconstruct the exact finer-grained members"
    assert current["audit"]["selected"]["canonical_handle"] == _h("down")


def test_projection_is_deterministic_and_does_not_mutate_inputs() -> None:
    atlas = _atlas()
    meaning = _meaning()
    fold = _fold()
    register = _register()
    before = copy.deepcopy((atlas, meaning, fold, register))

    first = project_semantic_junction(
        atlas_updown=atlas,
        meaning_upfold=meaning,
        compact_fold=fold,
        register_dictionary=register,
        active_register_generation="register-generation-7",
    )
    second = project_semantic_junction(
        atlas_updown=atlas,
        meaning_upfold=meaning,
        compact_fold=fold,
        register_dictionary=register,
        active_register_generation="register-generation-7",
    )

    assert first == second
    assert (atlas, meaning, fold, register) == before
