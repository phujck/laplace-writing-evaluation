from __future__ import annotations

import json
import subprocess
from collections import Counter
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from laplace.representation import embedding_health as health
from laplace.representation import semantic_cadence as cadence
from laplace.representation.semantic_vertical import canonical_bytes, digest, digest_bytes


def test_external_text_custody_preserves_markdown_without_json_coercion(
    monkeypatch, tmp_path: Path
) -> None:
    from laplace.representation import atlas_bridge, semantic_vertical

    body = b"# Semantic lifecycle design\n\nTyped prose remains exact custody.\n"
    handle = digest_bytes(body)
    path = tmp_path / "design.md"
    path.write_bytes(body)
    monkeypatch.setattr(atlas_bridge, "custody_has", lambda observed: observed == handle)

    observed, face = semantic_vertical._external_custody(
        path, handle, json_object=False
    )

    assert observed == body
    assert face == {
        "schema_version": "laplace.external-text-custody/1",
        "content_handle": handle,
        "bytes": len(body),
    }


def test_blob_inventory_is_deterministic_by_handle(tmp_path: Path) -> None:
    from laplace.representation import semantic_vertical

    for name, body in (("f" * 64, b"later"), ("0" * 64, b"first")):
        path = tmp_path / name[:2] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    assert semantic_vertical._blob_inventory(tmp_path) == [
        {"handle": "sha256:" + "0" * 64, "bytes": 5},
        {"handle": "sha256:" + "f" * 64, "bytes": 5},
    ]


def test_historical_unavailable_body_becomes_typed_semantic_fog() -> None:
    from laplace.representation import semantic_vertical

    message_id = "message:0acc29d0812d5e3822b964e8c0db1123ea8a0f95d4b9590d4a2f14f98bacb3e5"
    body_handle = "sha256:79f7d5243362a02b9bec16ecd4c32f45500217f6f3056ac25ca8b30611e15a3e"
    body = semantic_vertical._historical_unavailable_embedding(
        message_id, body_handle
    )
    assert body is not None
    value = json.loads(body)
    assert value["state"] == "REFUSED"
    assert value["content_available"] is False
    assert value["message_id"] == message_id
    assert value["body_handle"] == body_handle
    assert value["reason"] == "LEGACY_BODY_ABSENT_AT_CUSTODY_BOUNDARY"
    assert semantic_vertical._historical_unavailable_embedding(
        "message:" + "0" * 64, body_handle
    ) is None


def test_reachability_witness_consumes_bounded_exact_continuations() -> None:
    calls: list[int] = []

    def descend(**kwargs):
        offset = kwargs["content_offset"]
        calls.append(offset)
        if offset == 0:
            return {
                "content_status": "TRUNCATED",
                "content_handle": "sha256:" + "a" * 64,
                "content_bytes": 8,
                "content_offset": 0,
                "content_omitted_before": 0,
                "content_omitted_after": 3,
                "content_next_offset": 5,
                "authority_write": "none",
            }
        return {
            "content_status": "FINAL",
            "content_handle": "sha256:" + "a" * 64,
            "content_bytes": 8,
            "content_offset": 5,
            "content_omitted_before": 5,
            "content_omitted_after": 0,
            "content_next_offset": None,
            "authority_write": "none",
        }

    result = health._complete_exact_descent(
        descend,
        route={"kind": "ledger-row", "reference": "OP-X", "source": "test"},
        query="recover all content",
        expected="OP-X",
    )

    assert calls == [0, 5]
    assert result["content_status"] == "COMPLETE"
    assert result["content_pages"] == 2
    assert result["content_bytes"] == 8
    assert result["content_handle"] == "sha256:" + "a" * 64


def test_profile_source_class_carries_query_bearing_meaning() -> None:
    from laplace.representation import semantic_vertical

    rows = semantic_vertical._synthetic_class_rows(
        [
            {
                "source_class": "seat-profiles-goals-bindings",
                "root": "sha256:" + "a" * 64,
                "count": 3,
                "omitted": 0,
                "reason": "complete",
            }
        ]
    )
    profile_class = rows[1]
    summary = profile_class["semantic_summary"].lower()
    assert "live and retired seat binding lineage" in summary
    assert "ego, aisthesis, and superego" in summary
    assert "reconstruction profiles" in summary


def test_reachability_counts_direct_at_grade_source_class_hits() -> None:
    expected = "operational://seat-profiles-goals-bindings"
    fired = {
        "hits": [{"recovered": "OP-PROFILE-EGO", "path": []}],
        "per_grade": {
            "2": [{"id": expected, "salience": 1.0}],
        },
    }

    assert expected in health._fired_node_ids(fired)


def test_reachability_recovers_canonical_ancestry_when_route_path_is_thin() -> None:
    expected = "operational://seat-profiles-goals-bindings"
    profile = "OP-PROFILE-SUPEREGO"
    fired = {
        "hits": [{"recovered": profile, "path": [{"id": profile}]}],
        "per_grade": {},
    }
    network = {
        "nodes": {
            profile: {"parent": expected},
            expected: {"parent": "operational://root"},
            "operational://root": {"parent": None},
        }
    }

    reached = health._fired_node_ids(fired, network)

    assert profile in reached
    assert expected in reached
    assert "operational://root" in reached


def test_reachability_accepts_bounded_cluster_containing_target() -> None:
    expected = "operational://solution"
    fired = {
        "hits": [{"recovered": "operational://neighbour", "path": []}],
        "per_grade": {"2": [{"id": "operational://cluster"}]},
    }
    network = {
        "root": "operational://root",
        "nodes": {
            "operational://root": {
                "parent": None,
                "members": ["operational://cluster"],
            },
            "operational://cluster": {
                "parent": "operational://root",
                "members": [expected, "operational://neighbour"],
            },
            expected: {"parent": "operational://cluster", "members": []},
            "operational://neighbour": {
                "parent": "operational://cluster",
                "members": [],
            },
        },
    }

    witness = health._bounded_discovery_region(
        fired, network, expected, budget=3
    )

    assert witness == {
        "status": "REGION-HIT",
        "anchor_node": "operational://cluster",
        "region_member_count": 3,
        "budget": 3,
        "target_contained": True,
    }


def test_reachability_rejects_region_larger_than_local_search_budget() -> None:
    expected = "operational://solution"
    members = [expected, "operational://near", "operational://extra"]
    fired = {"hits": [{"recovered": "operational://near", "path": []}]}
    network = {
        "root": "operational://root",
        "nodes": {
            "operational://root": {"parent": None, "members": ["operational://cluster"]},
            "operational://cluster": {"parent": "operational://root", "members": members},
            **{
                member: {"parent": "operational://cluster", "members": []}
                for member in members
            },
        },
    }

    witness = health._bounded_discovery_region(
        fired, network, expected, budget=3
    )

    assert witness["status"] == "MISS"
    assert witness["target_contained"] is False


def test_known_reachability_descends_exactly_when_fuzzy_discovery_misses(
    monkeypatch, tmp_path: Path
) -> None:
    from laplace.engine import conceptric, descent

    expected = (
        "OP-DEVELOPMENT-WORK-MAP",
        "operational://lifecycle-recovery-publication",
        "operational://fabric-exchange",
        "operational://seat-profiles-goals-bindings",
        "OP-EXPLICIT-OMISSIONS-REFUSALS",
        "OP-GIT-SOURCE-COORDINATE",
    )
    source = tmp_path / "operational.jsonl"
    source.write_text(
        "".join(
            json.dumps({
                "id": node_id,
                "exact_descent": {
                    "kind": "ledger-row",
                    "reference": node_id,
                    "source": "semantic_operational_sources",
                },
            }) + "\n"
            for node_id in expected
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        health,
        "load_coverage",
        lambda _root: {"sources_path": source.name},
    )
    monkeypatch.setattr(conceptric, "load_network", lambda _root: {"nodes": {}})
    monkeypatch.setattr(
        conceptric,
        "fire_by_grade",
        lambda *_args, **_kwargs: {
            "router": "semantic-test",
            "n_visited": 7,
            "hits": [],
            "per_grade": {},
        },
    )
    monkeypatch.setattr(
        descent,
        "descend",
        lambda **kwargs: {
            "content_status": "COMPLETE",
            "content_handle": "sha256:" + "a" * 64,
            "content_bytes": 10,
            "content_offset": kwargs["content_offset"],
            "content_next_offset": None,
            "content_omitted_after": 0,
            "content_omitted_before": kwargs["content_offset"],
            "authority_write": "none",
            "refused": False,
        },
    )

    witnesses = health.build_reachability_witnesses(tmp_path)

    assert len(witnesses) == 6
    assert all(row["reached"] is True for row in witnesses)
    assert all(row["discovery_reached"] is False for row in witnesses)
    assert all(row["discovery_status"] == "MISS" for row in witnesses)
    assert all(row["local_search_budget"] == 256 for row in witnesses)
    assert all(row["exact_content_status"] == "COMPLETE" for row in witnesses)


def test_semantic_cadence_scope_expands_untracked_directories_to_files(
    tmp_path: Path,
) -> None:
    _git(tmp_path, "init")
    nested = tmp_path / "semantic" / "fold_up" / "00.jsonl"
    nested.parent.mkdir(parents=True)
    nested.write_text("{}\n", encoding="utf-8")

    changed = cadence.worktree_changed_paths(tmp_path)

    assert changed == {"semantic/fold_up/00.jsonl"}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(
        root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-m", message,
    )
    return _git(root, "rev-parse", "HEAD")


def _tuple(source: str, tree: str) -> dict:
    body = {
        "schema_version": "laplace.semantic-fold-source-tuple/1",
        "git": {"commit": source, "tree": tree},
        "atlas": {
            "schema_version": "laplace.semantic-atlas-currentness-token/1",
            "drift_token": {
                "schema_version": "atlas.conceptric-drift-token/1",
                "cursor": 7,
                "head_event_id": "sha256:" + "a" * 64,
                "head_record_digest": "sha256:" + "b" * 64,
            },
            "effective_checkpoint_digest": "sha256:" + "c" * 64,
            "authority_roots": {"seat_occupancy_root": "sha256:" + "d" * 64},
            "integrity_boundary": "CHECKSUMMED-CRUTCH",
            "token_handle": "sha256:" + "e" * 64,
        },
        "coverage_contract": {
            "schema_version": "laplace.semantic-source-coverage/1",
            "required_classes": [],
        },
        "profile_heads_handle": "sha256:" + "f" * 64,
        "profile_heads": {
            name: {
                "profile_handle": f"sha256:{digit * 64}",
                "goal_digest": f"sha256:{digit.upper() * 64}",
                "phase_policy_handle": "sha256:" + "9" * 64,
            }
            for name, digit in (("ego", "1"), ("aisthesis", "2"), ("superego", "3"))
        },
        "profile_handles": {
            "ego": "sha256:" + "1" * 64,
            "aisthesis": "sha256:" + "2" * 64,
            "superego": "sha256:" + "3" * 64,
        },
        "goal_context_handle": "sha256:" + "4" * 64,
        "policy_roots": {"regularizer": "sha256:" + "5" * 64},
        "builder": {
            "entry": "scripts/semantic_cadence.py --worker",
            "law_generation": "canonical-up-down-outer-receipt/1",
            "required_gpu": True,
        },
    }
    atlas_body = dict(body["atlas"])
    atlas_body.pop("token_handle")
    body["atlas"]["token_handle"] = digest(atlas_body)
    body["source_tuple_handle"] = digest(body)
    return body


def _moved(value: dict, field: str) -> dict:
    changed = deepcopy(value)
    if field == "atlas":
        changed["atlas"]["drift_token"]["cursor"] += 1
        atlas = dict(changed["atlas"])
        atlas.pop("token_handle")
        changed["atlas"]["token_handle"] = digest(atlas)
    elif field == "profile_heads":
        changed["profile_heads"]["ego"]["profile_handle"] = "sha256:" + "6" * 64
        changed["profile_handles"]["ego"] = "sha256:" + "6" * 64
        changed["profile_heads_handle"] = "sha256:" + "7" * 64
    elif field == "goal_policy":
        changed["goal_context_handle"] = "sha256:" + "8" * 64
        changed["policy_roots"]["regularizer"] = "sha256:" + "0" * 64
    changed.pop("source_tuple_handle")
    changed["source_tuple_handle"] = digest(changed)
    return changed


def _fold_fixture(monkeypatch, root: Path) -> tuple[str, str, dict]:
    _git(root, "init")
    (root / "source.py").write_text("source\n")
    _commit(root, "source")
    source = _git(root, "rev-parse", "HEAD")
    source_tree = _git(root, "rev-parse", "HEAD^{tree}")
    source_tuple = _tuple(source, source_tree)
    artifact = root / "artifact.bin"
    artifact.write_bytes(b"fold bytes")
    blob = _git(root, "hash-object", "--path", "artifact.bin", "artifact.bin")
    row = {
        "path": "artifact.bin", "bytes": len(b"fold bytes"),
        "content_handle": digest_bytes(b"fold bytes"), "git_blob": blob,
    }
    index = {
        "path": health.SEMANTIC_FOLD_INDEX_PATH.as_posix(),
        "handle": "sha256:" + "6" * 64,
        "generation": "sha256:" + "7" * 64,
        "entries": 3,
    }
    candidate = {
        "exact_descent_index": index,
        "roots": {"leaf_content_handle_root": "sha256:" + "8" * 64},
        "register_dictionary": {"generation": index["generation"]},
    }
    body = {
        "schema_version": health.MANIFEST_SCHEMA,
        "status": "CANDIDATE", "shared": True,
        "source": {
            "commit": source, "tree": source_tree,
            "coverage_handle": "sha256:" + "1" * 64,
            "source_classes": [], "profile_handles": source_tuple["profile_handles"],
            "atlas": {}, "source_tuple": source_tuple,
            "source_tuple_handle": source_tuple["source_tuple_handle"],
        },
        "forward_transition": {
            "kind": "git-single-successor", "expected_parent": source,
            "allowed_paths": ["artifact.bin", health.MANIFEST_PATH.as_posix()],
            "unrelated_source_change": "UPDATE-DUE",
        },
        "builder": {}, "artifacts": [row], "artifact_root": digest([row]),
        "semantic_fold_candidate": candidate, "semantic_horizon": {},
        "runtime": {"latest_receipt": {"embedding_counts": {"deferred": 0}}},
        "semantic_reachability": [{"status": "COMPLETE", "reference": "WO-P0"}],
        "cadence": {}, "currentness_law": "test", "authority_effect": "none",
        "non_blocking": True,
    }
    body["manifest_handle"] = digest(body)
    (root / health.MANIFEST_PATH).write_bytes(canonical_bytes(body) + b"\n")
    output = _commit(root, "fold")
    output_tree = _git(root, "rev-parse", "HEAD^{tree}")
    _git(root, "update-ref", health.SEMANTIC_FOLD_REF, output)
    outer = {
        "receipt_handle": "sha256:" + "9" * 64,
        "artifact_root": body["artifact_root"], "manifest_handle": body["manifest_handle"],
        "output_commit": output, "output_tree": output_tree,
        "source_commit": source, "source_tree": source_tree,
        "source_tuple": source_tuple,
        "source_tuple_handle": source_tuple["source_tuple_handle"],
        "exact_descent_index": index, "roots": candidate["roots"],
        "register_dictionary": candidate["register_dictionary"],
        "reference_law": {"up": "atlas.up-history-act/2", "down": "atlas.down-act/1"},
    }
    monkeypatch.setattr(health, "_read_outer_receipt", lambda *_args, **_kwargs: outer)
    monkeypatch.setattr(health, "FOLD_ARTIFACT_PATHS", ("artifact.bin",))
    monkeypatch.setattr("laplace.representation.semantic_cadence.read_state", lambda: {"status": "IDLE"})
    monkeypatch.setattr(
        "laplace.representation.semantic_cadence.read_consumption",
        lambda: {"schema_version": "laplace.semantic-fold-consumption/1", "latest": {}},
    )
    monkeypatch.setattr(
        "laplace.representation.semantic_cadence.current_source_tuple", lambda *_args, **_kwargs: source_tuple
    )
    return source, output, source_tuple


def test_public_health_keeps_retired_side_ref_without_live_atlas_validation(
    monkeypatch, tmp_path: Path
) -> None:
    source, output, _ = _fold_fixture(monkeypatch, tmp_path)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("router health must not revalidate the retired side ref against Atlas")

    monkeypatch.setattr(cadence, "current_atlas_observation", forbidden)
    monkeypatch.setattr(cadence, "current_source_tuple", forbidden)
    result = health.read_health(tmp_path)
    assert result["side_ref_fold"]["status"] == "RETIRED"
    assert result["side_ref_fold"]["source_commit"] == source
    assert result["side_ref_fold"]["output_commit"] == output
    assert result["side_ref_fold"]["manifest_handle"]
    assert result["side_ref_fold"]["coverage_handle"]
    assert result["fold"] is result["tree_fold"]


def test_forward_health_allows_source_side_ref_and_immutable_fold_blobs(
    monkeypatch, tmp_path: Path
) -> None:
    source, _output, _source_tuple = _fold_fixture(monkeypatch, tmp_path)
    _git(tmp_path, "checkout", "--detach", source)
    current = health._read_side_ref_health(tmp_path)
    assert current["status"] == "CURRENT"
    assert current["source_currentness"]["status"] == "CURRENT"
    assert current["source_currentness"]["source_tuple"] == _source_tuple
    assert current["side_refs"]["semantic_fold"]["commit"] == _output
    assert current["side_refs"]["semantic_fold_receipt"]["receipt_handle"] == (
        "sha256:" + "9" * 64
    )
    assert current["artifacts"]["cache_sidecar_consistent"] is True
    assert current["semantic_reachability"] == [
        {"status": "COMPLETE", "reference": "WO-P0"}
    ]


def test_later_git_source_is_stale(monkeypatch, tmp_path: Path) -> None:
    source, _output, source_tuple = _fold_fixture(monkeypatch, tmp_path)
    _git(tmp_path, "checkout", "--detach", source)
    (tmp_path / "source.py").write_text("later source\n")
    later = _commit(tmp_path, "later source")
    later_tree = _git(tmp_path, "rev-parse", "HEAD^{tree}")
    moved = deepcopy(source_tuple)
    moved["git"] = {"commit": later, "tree": later_tree}
    moved.pop("source_tuple_handle")
    moved["source_tuple_handle"] = digest(moved)
    monkeypatch.setattr(
        "laplace.representation.semantic_cadence.current_source_tuple", lambda *_args, **_kwargs: moved
    )
    stale = health._read_side_ref_health(tmp_path)
    assert stale["status"] == "STALE"
    assert stale["ui_status"] == "UPDATE-DUE"
    assert "git" in stale["source_currentness"]["moved_fields"]


def test_atlas_only_event_makes_fold_noncurrent(monkeypatch, tmp_path: Path) -> None:
    _source, _output, source_tuple = _fold_fixture(monkeypatch, tmp_path)
    moved = _moved(source_tuple, "atlas")
    monkeypatch.setattr(
        "laplace.representation.semantic_cadence.current_source_tuple", lambda *_args, **_kwargs: moved
    )
    result = health._read_side_ref_health(tmp_path)
    assert result["status"] == "STALE"
    assert result["ui_status"] == "UPDATE-DUE"
    assert result["source_currentness"]["moved_fields"] == ["atlas", "source_tuple_handle"]


def test_profile_head_move_makes_fold_noncurrent(monkeypatch, tmp_path: Path) -> None:
    _source, _output, source_tuple = _fold_fixture(monkeypatch, tmp_path)
    moved = _moved(source_tuple, "profile_heads")
    monkeypatch.setattr(
        "laplace.representation.semantic_cadence.current_source_tuple", lambda *_args, **_kwargs: moved
    )
    result = health._read_side_ref_health(tmp_path)
    assert result["status"] == "STALE"
    assert {"profile_handles", "profile_heads", "profile_heads_handle"}.issubset(
        result["source_currentness"]["moved_fields"]
    )


def test_goal_and_policy_move_makes_fold_noncurrent(monkeypatch, tmp_path: Path) -> None:
    _source, _output, source_tuple = _fold_fixture(monkeypatch, tmp_path)
    moved = _moved(source_tuple, "goal_policy")
    monkeypatch.setattr(
        "laplace.representation.semantic_cadence.current_source_tuple", lambda *_args, **_kwargs: moved
    )
    result = health._read_side_ref_health(tmp_path)
    assert result["status"] == "STALE"
    assert {"goal_context_handle", "policy_roots"}.issubset(
        result["source_currentness"]["moved_fields"]
    )


def test_current_source_tuple_uses_compact_tip_and_checkpoint_not_snapshot(
    monkeypatch, tmp_path: Path
) -> None:
    from laplace.representation import atlas_bridge, semantic_vertical
    from laplace.engine import compaction_submergence, turn_reconstruction

    custody = {}
    for name in ("goal", "ceremony", "direct", "hierarchy", "ruling", "design"):
        path = tmp_path / f"{name}.json"
        path.write_bytes(name.encode())
        custody[name] = (path, digest_bytes(name.encode()))
    monkeypatch.setattr(cadence, "GOAL_CONTEXT_PATH", custody["goal"][0])
    monkeypatch.setattr(cadence, "GOAL_CONTEXT_HANDLE", custody["goal"][1])
    monkeypatch.setattr(
        compaction_submergence, "CEREMONY_SUSPENSION_PATH", custody["ceremony"][0]
    )
    monkeypatch.setattr(
        compaction_submergence, "CEREMONY_SUSPENSION_SHA256", custody["ceremony"][1]
    )
    monkeypatch.setattr(compaction_submergence, "INTEGRATED_ROOTS", {"work": "root"})
    for prefix, name in (
        ("DIRECT_COORDINATION", "direct"),
        ("HIERARCHY_DERIVATION", "hierarchy"),
        ("REGULARIZATION_RULING", "ruling"),
        ("REGULARIZATION_DESIGN", "design"),
    ):
        monkeypatch.setattr(semantic_vertical, f"{prefix}_PATH", custody[name][0])
        monkeypatch.setattr(semantic_vertical, f"{prefix}_HANDLE", custody[name][1])
    heads = {
        "heads_handle": "sha256:" + "f" * 64,
        "profiles": {
            name: {
                "profile_handle": "sha256:" + digit * 64,
                "goal_digest": "sha256:" + digit.upper() * 64,
                "phase_policy_handle": "sha256:" + "9" * 64,
            }
            for name, digit in (("ego", "1"), ("aisthesis", "2"), ("superego", "3"))
        },
    }
    monkeypatch.setattr(turn_reconstruction, "load_heads", lambda _root: heads)
    drift = {
        "schema_version": "atlas.conceptric-drift-token/1",
        "cursor": 17,
        "head_event_id": "sha256:" + "a" * 64,
        "head_record_digest": "sha256:" + "b" * 64,
    }
    roots = {
        name: "sha256:" + digit * 64
        for name, digit in (
            ("development_review_root", "1"),
            ("provider_session_root", "2"),
            ("region_lease_root", "3"),
            ("seat_mail_frontier_root", "4"),
            ("seat_occupancy_root", "5"),
        )
    }
    monkeypatch.setattr(atlas_bridge, "drift_token", lambda: drift)
    monkeypatch.setattr(
        atlas_bridge,
        "authority_epoch",
        lambda: {
            "status": "CURRENT",
            "effective_checkpoint_digest": "sha256:" + "c" * 64,
            "effective_checkpoint": {
                "cursor": drift["cursor"],
                "head_event_id": drift["head_event_id"],
                "head_record_digest": drift["head_record_digest"],
                "authority": roots,
            },
            "integrity_boundary": {"status": "CHECKSUMMED-CRUTCH"},
        },
    )
    monkeypatch.setattr(
        atlas_bridge,
        "snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("global replaying snapshot used")),
    )

    result = cadence.current_source_tuple(
        tmp_path, source_commit="a" * 40, source_tree="b" * 40
    )
    assert result["atlas"]["drift_token"] == drift
    assert result["atlas"]["authority_roots"] == roots
    assert result["profile_heads_handle"] == heads["heads_handle"]
    assert result["source_tuple_handle"] == digest(
        {key: value for key, value in result.items() if key != "source_tuple_handle"}
    )


def test_100k_leaf_down_reads_one_bounded_shard_without_top_level_leaf_map(
    monkeypatch, tmp_path: Path
) -> None:
    handles = [digest({"leaf": index}) for index in range(100_000)]
    counts = Counter(health._shard_for_handle(handle) for handle in handles)
    assert max(counts.values()) < health.SEMANTIC_FOLD_SHARD_CAP

    selected_handle = handles[54_321]
    selected_shard = health._shard_for_handle(selected_handle)
    row = {
        "kind": "leaf",
        "semantic_handle": selected_handle,
        "node_id": "node:54321",
        "content_handle": digest_bytes(b"leaf 54321"),
        "exact_descent": {
            "kind": "repository-file",
            "reference": "source/leaf-54321.md",
            "source": "",
        },
        "parent_id": "cluster:root",
    }
    shard_body = {
        "schema_version": "laplace.semantic-fold-down-shard/1",
        "shard": selected_shard,
        "cap": health.SEMANTIC_FOLD_SHARD_CAP,
        "entries": {
            selected_handle: {
                "kind": "leaf",
                "row": row,
                "row_handle": digest(row),
            }
        },
    }
    shard_body["shard_handle"] = digest(shard_body)
    top = {
        "schema_version": health.SEMANTIC_FOLD_INDEX_SCHEMA,
        "source": {},
        "coverage_handle": digest_bytes(b"coverage"),
        "roots": {},
        "down_shards": [
            {
                "shard": shard,
                "entries": counts[shard],
                "index_handle": digest({"shard": shard, "entries": counts[shard]}),
            }
            for shard in health.SEMANTIC_FOLD_SHARDS
        ],
        "register_dictionary": {"generation": digest_bytes(b"registers")},
        "typed_route_totality": {
            "status": "COMPLETE",
            "leaf_count": 100_000,
            "cluster_count": 0,
            "untyped": 0,
        },
        "reference_law": {
            "up": "atlas.up-history-act/2",
            "down": "atlas.down-act/1",
        },
        "atlas_event_delta": 0,
    }
    assert "leaf_entries" not in top and "entries" not in top
    top["index_handle"] = digest(top)
    receipt = {
        "receipt_handle": digest_bytes(b"outer receipt"),
        "exact_descent_index": {"handle": top["index_handle"]},
        "reference_law": top["reference_law"],
    }
    monkeypatch.setattr(
        health,
        "_read_side_ref_health",
        lambda _root: {
            "status": "CURRENT",
            "fold": {"output_commit": "f" * 40},
        },
    )
    monkeypatch.setattr(health, "_read_outer_receipt", lambda _root: receipt)
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        object_path = command[-1]
        if object_path.endswith(health.SEMANTIC_FOLD_INDEX_PATH.as_posix()):
            return SimpleNamespace(stdout=canonical_bytes(top) + b"\n", returncode=0)
        assert object_path.endswith(f"semantic/fold_down/{selected_shard}.json")
        return SimpleNamespace(stdout=canonical_bytes(shard_body) + b"\n", returncode=0)

    monkeypatch.setattr(health.subprocess, "run", fake_run)
    result = health.semantic_fold_down(
        tmp_path,
        semantic_handle=selected_handle,
        receipt_handle=receipt["receipt_handle"],
        register_generation=top["register_dictionary"]["generation"],
    )
    assert result["status"] == "COMPLETE"
    assert result["selected"] == row
    assert len(calls) == 2
    assert sum("semantic/fold_down/" in call[-1] for call in calls) == 1
