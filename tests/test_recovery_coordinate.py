from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.representation import recovery_coordinate as R


def test_runtime_recovery_claim_requires_exact_point_and_external_grant_roots() -> None:
    point = {
        "schema_version": R.RUNTIME_RECOVERY_POINT_SCHEMA,
        "source_snapshot_id": "sha256:" + ("1" * 64),
        "source_checkpoint": {"checkpoint_digest": "sha256:" + ("2" * 64)},
    }
    point["point_root"] = R._canonical_chash(point)
    grant = {
        "schema_version": "laplace.runtime-recovery-coordinate-grant/1",
        "point_root": point["point_root"],
        "source_snapshot_id": point["source_snapshot_id"],
        "source_checkpoint_digest": point["source_checkpoint"]["checkpoint_digest"],
    }
    grant["grant_anchor_root"] = R._canonical_chash(grant)

    exact = R._verify_runtime_recovery_coordinate_claim(
        {"runtime_recovery_point": point, "runtime_recovery_grant": grant}
    )
    assert exact["status"] == "EXACT"
    forged = dict(grant)
    forged["source_snapshot_id"] = "sha256:" + ("3" * 64)
    refused = R._verify_runtime_recovery_coordinate_claim(
        {"runtime_recovery_point": point, "runtime_recovery_grant": forged}
    )
    assert refused == {
        "status": "INVALID",
        "reason": "runtime recovery grant root mismatch",
    }


def test_semantic_post_lock_uses_operator_frontier_not_git_touch_time(
    monkeypatch, tmp_path: Path
) -> None:
    from laplace.engine import keeper, meaning_upfold
    from laplace.representation.embed_router import TEXT_CAP

    leaf = {
        "kind": "md",
        "essence": "Example document",
        "keywords": ["example"],
        "sealed": False,
    }
    residue = {"doc.md": leaf}
    backend = "test-embedder"
    leaf_sha = meaning_upfold._text_sha(
        backend,
        meaning_upfold._embeddable_text(tmp_path, "doc.md", leaf, TEXT_CAP),
    )
    (tmp_path / ".meaning_tree.json").write_text(
        json.dumps({
            "version": backend,
            "lens_hash": "lens:1",
            "lens_pairs": [],
            "leaf_sha": {"doc.md": leaf_sha},
        }),
        encoding="utf-8",
    )
    (tmp_path / ".self_graded.json").write_text(
        json.dumps({
            "doc.md": {
                "id": "doc.md",
                "kind": "md",
                "essence": "Example document",
                "keywords": ["example"],
                "sealed": False,
                "leaf": True,
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        keeper,
        "semantic_input_frame",
        lambda _root: ({"doc.md": leaf}, lambda _name: None, residue, "lens:1", []),
    )

    result = R._semantic_post_lock(tmp_path)

    assert result["status"] == "CURRENT"
    assert result["meaning_leaf_frontier_exact"] is True
    assert result["graded_leaf_handles_exact"] is True


def test_semantic_post_lock_detects_changed_operator_input(monkeypatch, tmp_path: Path) -> None:
    from laplace.engine import keeper, meaning_upfold
    from laplace.representation.embed_router import TEXT_CAP

    old_leaf = {
        "kind": "md",
        "essence": "Old handle",
        "keywords": ["old"],
        "sealed": False,
    }
    new_leaf = {**old_leaf, "essence": "New handle", "keywords": ["new"]}
    backend = "test-embedder"
    old_sha = meaning_upfold._text_sha(
        backend,
        meaning_upfold._embeddable_text(tmp_path, "doc.md", old_leaf, TEXT_CAP),
    )
    (tmp_path / ".meaning_tree.json").write_text(
        json.dumps({
            "version": backend,
            "lens_hash": "lens:1",
            "lens_pairs": [],
            "leaf_sha": {"doc.md": old_sha},
        }),
        encoding="utf-8",
    )
    (tmp_path / ".self_graded.json").write_text(
        json.dumps({
            "doc.md": {
                "id": "doc.md",
                "kind": "md",
                "essence": "Old handle",
                "keywords": ["old"],
                "sealed": False,
                "leaf": True,
            }
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        keeper,
        "semantic_input_frame",
        lambda _root: (
            {"doc.md": new_leaf},
            lambda _name: None,
            {"doc.md": new_leaf},
            "lens:1",
            [],
        ),
    )

    result = R._semantic_post_lock(tmp_path)

    assert result["status"] == "STALE"
    assert result["delta"]["meaning_changed"] == ["doc.md"]
    assert result["delta"]["graded_changed"] == ["doc.md"]


def test_semantic_verification_ignores_unrelated_later_git_commits(
    monkeypatch, tmp_path: Path
) -> None:
    class Result:
        def __init__(self, stdout=b"", returncode=0):
            self.stdout, self.stderr, self.returncode = stdout, b"", returncode

    def fake_git(_root, *args, check=True):
        if args[:3] == ("log", "-1", "--format=%H"):
            return Result(b"a" * 40 + b"\n")
        if args == ("rev-parse", "HEAD"):
            return Result(b"b" * 40 + b"\n")
        if args[:2] == ("merge-base", "--is-ancestor"):
            return Result(returncode=0)
        if args[:2] == ("rev-list", "--count"):
            return Result(b"7\n")
        raise AssertionError(args)

    monkeypatch.setattr(R, "_git", fake_git)
    monkeypatch.setattr(
        R,
        "_semantic_post_lock",
        lambda _root: {"status": "CURRENT", "post_lock": "sha256:post"},
    )

    result = R._verify_semantic(tmp_path, {"post_lock": "sha256:post"})

    assert result["status"] == "CURRENT"
    assert result["post_lock_exact"] is True
    assert result["commits_behind"] == 7


def _blueprint_projection(current: str, *history: str) -> dict:
    return {
        "generation_id": current,
        "generation_completion_history": [
            {"generation_id": generation_id} for generation_id in history
        ],
        "pour_handle": "sha256:" + "c" * 64,
        "current": True,
        "moved_source_roots": [],
        "counts": {},
    }


@pytest.mark.parametrize(
    ("recorded", "history", "relation"),
    [
        ("generation:new", ("generation:old", "generation:new"), "SAME"),
        ("generation:old", ("generation:old", "generation:new"), "DESCENDANT"),
        ("generation:missing", ("generation:old", "generation:new"), "DIVERGED"),
    ],
)
def test_blueprint_generation_relation_uses_exact_completion_history(
    monkeypatch, recorded, history, relation
) -> None:
    from laplace.representation import atlas_bridge

    monkeypatch.setattr(
        atlas_bridge,
        "blueprint_projection",
        lambda **_kwargs: _blueprint_projection("generation:new", *history),
    )
    result = R._verify_blueprint({
        "generation_id": recorded,
        "pour_handle": "sha256:" + "c" * 64,
        "current_against_worktree": True,
        "moved_source_roots": [],
    })

    assert result["generation_relation"] == relation
    assert result["generation_exact"] is (relation == "SAME")
    assert result["completion_history_exact"] is True


def _occupancy(
    session: str,
    binding_event: str = "binding:1",
    join_event: str = "join:1",
) -> dict:
    return {
        "state": "BOUND",
        "routing_authority": True,
        "join": {"mail_state": "MAIL_READY"},
        "join_event_id": join_event,
        "binding_event_id": binding_event,
        "binding": {
            "function": "superego",
            "provider_session_ref": session,
            "registered_principal_ref": "logical:superego-seat",
            "provider_identity_proof_handle": "proof:1",
        },
    }


def _live_contact(
    session: str,
    binding_event: str = "binding:1",
    join_event: str = "join:1",
) -> dict:
    return {
        "schema_version": "atlas.recovery-live-contact/1",
        "required_seats": ["superego-seat"],
        "seats": {
            "superego-seat": {
                "state": "BOUND",
                "routing_authority": True,
                "mail_state": "MAIL_READY",
                "function": "superego",
                "provider_session_ref": session,
                "registered_principal_ref": "logical:superego-seat",
                "provider_identity_proof_handle": "proof:1",
                "join_event_id": join_event,
                "binding_event_id": binding_event,
            }
        },
        "derived_from": {
            "schema_version": "atlas.drift-token/1",
            "cursor": 100,
            "head_event_id": "event:head",
            "head_record_digest": "digest:head",
        },
        "claim_boundary": "Atlas occupancy evidence only",
    }


def _history_projection(*occupancies: dict) -> dict:
    events = {}
    sequence = 0
    for occupancy in occupancies:
        join_id = occupancy["join_event_id"]
        binding_id = occupancy["binding_event_id"]
        binding = occupancy["binding"]
        if join_id not in events:
            sequence += 1
            events[join_id] = {
                "event_id": join_id,
                "sequence": sequence,
                "kind": "seat.joined",
                "actor": binding["function"],
                "subject": "seat:superego-seat:occupancy",
                "causation_ids": [],
                "payload": {
                    "seat_id": "superego-seat",
                    "holder_ref": binding["provider_session_ref"],
                    "function": binding["function"],
                    "registered_holder_ref": binding["registered_principal_ref"],
                    "information_proof_handle": binding[
                        "provider_identity_proof_handle"
                    ],
                    "mail_state": occupancy["join"]["mail_state"],
                },
            }
        sequence += 1
        events[binding_id] = {
            "event_id": binding_id,
            "sequence": sequence,
            "kind": "seat.occupancy-bound",
            "actor": binding["function"],
            "subject": "seat:superego-seat:binding",
            "causation_ids": [join_id],
            "payload": {
                "seat_id": "superego-seat",
                "provider_session_ref": binding["provider_session_ref"],
                "function": binding["function"],
                "registered_principal_ref": binding["registered_principal_ref"],
                "provider_identity_proof_handle": binding[
                    "provider_identity_proof_handle"
                ],
                "join_event_id": join_id,
            },
        }
    return {
        "events": events,
        "requested_event_ids": list(events),
        "missing_event_ids": [],
        "proof_boundary": "test verified history",
    }


def _authority_epoch(
    *,
    occupancy: dict[str, dict] | None = None,
    messages: dict[str, dict] | None = None,
    cursor: int = 100,
    head_event_id: str = "sha256:" + "a" * 64,
    head_record_digest: str = "sha256:" + "b" * 64,
) -> dict:
    recipients: dict[str, dict] = {}
    for message_id, record in (messages or {}).items():
        record = {**record, "message": dict(record["message"])}
        record["message"].setdefault("message_id", message_id)
        seat_id = str(record["message"]["recipient_seat_id"])
        recipients.setdefault(
            seat_id,
            {"revision_cursor": 0, "revision_event_id": None, "pending": {}},
        )["pending"][message_id] = record
    checkpoint = {
        "cursor": cursor,
        "head_event_id": head_event_id,
        "head_record_digest": head_record_digest,
        "implementation_digest": "sha256:" + "c" * 64,
        "environment_root": "sha256:" + "d" * 64,
        "dirty_paths_root": "sha256:" + "e" * 64,
        "authority": {
            "active_context": {"assumption": "atlas-rebuild", "fibre": "s0"},
            "seat_occupancy": occupancy or {},
            "recipient_mail": recipients,
        },
    }
    digest = R._canonical_chash(checkpoint)
    return {
        "status": "CURRENT",
        "checkpoint": checkpoint,
        "checkpoint_digest": digest,
        "effective_checkpoint": checkpoint,
        "effective_checkpoint_digest": digest,
        "read_metrics": {
            "global_history_replayed": False,
            "suffix_rows_loaded": 0,
            "authority_tail_limit": 64,
            "elapsed_ns": 11,
            "cpu_ns": 7,
        },
        "rollback": {
            "status": "CRUTCH",
            "predicate": "stop all writers, deep replay exact history, compare checkpoint",
        },
        "integrity_boundary": {"status": "CHECKSUMMED-CRUTCH"},
        "crutch": {
            "crutch_id": "CR-C2A-CHECKSUMMED-LIVE-AUTHORITY-20260828",
        },
    }


def _install_history(monkeypatch, atlas_bridge, *occupancies: dict) -> None:
    projection = _history_projection(*occupancies)
    monkeypatch.setattr(
        atlas_bridge, "event_history_projection", lambda _event_ids: projection
    )


def _verify_contact(expected: dict, epoch: dict) -> dict:
    return R._verify_live_contact(
        expected,
        authority_epoch=epoch,
        derived_from_verification={
            "historical_token_exact": True,
            "relation": "DESCENDANT",
        },
    )


def test_authority_epoch_gate_refuses_digest_replay_and_tail_drift() -> None:
    epoch = _authority_epoch()
    assert R._checked_authority_epoch(epoch)["cursor"] == 100

    forged = {**epoch, "effective_checkpoint_digest": "sha256:" + "0" * 64}
    with pytest.raises(ValueError, match="effective checkpoint digest"):
        R._checked_authority_epoch(forged)

    replayed = {**epoch, "read_metrics": {**epoch["read_metrics"], "global_history_replayed": True}}
    with pytest.raises(ValueError, match="replayed global history"):
        R._checked_authority_epoch(replayed)

    unbounded = {**epoch, "read_metrics": {
        **epoch["read_metrics"], "suffix_rows_loaded": 65,
    }}
    with pytest.raises(ValueError, match="exceeds the C2a"):
        R._checked_authority_epoch(unbounded)


def test_authority_epoch_retries_whole_bundle_once_without_deep_faces(
    monkeypatch, tmp_path: Path
) -> None:
    from laplace.representation import atlas_bridge

    epochs = [
        _authority_epoch(cursor=100),
        _authority_epoch(
            cursor=101,
            head_event_id="sha256:" + "f" * 64,
            head_record_digest="sha256:" + "1" * 64,
        ),
    ]
    epoch_calls = []
    axis_calls: list[tuple[str, int]] = []

    def authority_epoch():
        epoch = epochs[len(epoch_calls)]
        epoch_calls.append(epoch)
        return epoch

    monkeypatch.setattr(atlas_bridge, "authority_epoch", authority_epoch)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("deep or mutating authority face was called")

    monkeypatch.setattr(atlas_bridge, "snapshot", forbidden)
    monkeypatch.setattr(atlas_bridge, "provider_observation", forbidden)
    monkeypatch.setattr(atlas_bridge, "inspect_authority_epoch", forbidden)
    monkeypatch.setattr(atlas_bridge, "prepare_authority_epoch", forbidden)

    def runtime(_expected, epoch):
        axis_calls.append(("runtime", id(epoch)))
        return {"historical_token_exact": True, "relation": "DESCENDANT"}

    def contact(_expected, *, authority_epoch, derived_from_verification):
        assert derived_from_verification["historical_token_exact"] is True
        axis_calls.append(("contact", id(authority_epoch)))
        return {"status": "SAME", "relation": "SAME", "current": True}

    def fabric(_expected, _root, *, authority_epoch):
        axis_calls.append(("fabric", id(authority_epoch)))
        return {"status": "SAME", "total": 0, "identity_source_error": None}

    monkeypatch.setattr(R, "_verify_runtime", runtime)
    monkeypatch.setattr(R, "_verify_live_contact", contact)
    monkeypatch.setattr(R, "_verify_fabric", fabric)
    final_tips = iter((
        {
            "cursor": 101,
            "head_event_id": "sha256:" + "f" * 64,
            "head_record_digest": "sha256:" + "1" * 64,
        },
        {
            "cursor": 101,
            "head_event_id": "sha256:" + "f" * 64,
            "head_record_digest": "sha256:" + "1" * 64,
        },
    ))
    monkeypatch.setattr(atlas_bridge, "drift_token", lambda: next(final_tips))

    _runtime, _contact, _fabric, observation = R._verify_authority_axes(
        {"freshness_vector": {}, "live_contact": {}, "fabric_debt": {}},
        repo_root=tmp_path,
    )

    assert len(epoch_calls) == 2
    assert observation["status"] == "STABLE"
    assert observation["attempts"] == 2
    assert axis_calls == [
        ("runtime", id(epochs[0])), ("contact", id(epochs[0])), ("fabric", id(epochs[0])),
        ("runtime", id(epochs[1])), ("contact", id(epochs[1])), ("fabric", id(epochs[1])),
    ]


def test_live_contact_exact_binding_is_same(monkeypatch) -> None:
    from laplace.representation import atlas_bridge

    current = _occupancy("codex:current")
    requested = []
    projection = _history_projection(current)
    monkeypatch.setattr(
        atlas_bridge,
        "event_history_projection",
        lambda event_ids: requested.extend(event_ids) or projection,
    )

    result = _verify_contact(
        _live_contact("codex:current"),
        _authority_epoch(occupancy={"superego-seat": current}),
    )

    assert result["status"] == "SAME"
    assert result["current"] is True
    assert requested == ["join:1", "binding:1"]


def test_live_contact_new_binding_requires_supersession(monkeypatch) -> None:
    from laplace.representation import atlas_bridge

    predecessor = _occupancy("codex:predecessor")
    successor = _occupancy("codex:successor", "binding:2", "join:2")
    _install_history(monkeypatch, atlas_bridge, predecessor, successor)

    result = _verify_contact(
        _live_contact("codex:predecessor"),
        _authority_epoch(occupancy={"superego-seat": successor}),
    )

    assert result["status"] == "CHANGED"
    assert result["relation"] == "DESCENDANT"
    assert result["current"] is False


def test_live_contact_same_binding_cannot_resolve_to_different_session(monkeypatch) -> None:
    from laplace.representation import atlas_bridge

    current = _occupancy("codex:current")
    _install_history(monkeypatch, atlas_bridge, current)

    result = _verify_contact(
        _live_contact("codex:forged"),
        _authority_epoch(occupancy={"superego-seat": current}),
    )

    assert result["status"] == "INVALID"
    assert result["relation"] == "DIVERGED"


def test_live_contact_nonexistent_predecessor_binding_is_diverged(monkeypatch) -> None:
    from laplace.representation import atlas_bridge

    current = _occupancy("codex:current", "binding:current", "join:current")
    _install_history(monkeypatch, atlas_bridge, current)

    result = _verify_contact(
        _live_contact("codex:forged", "binding:never-existed", "join:never-existed"),
        _authority_epoch(occupancy={"superego-seat": current}),
    )

    assert result["status"] == "INVALID"
    assert result["relation"] == "DIVERGED"
    assert result["seats"]["superego-seat"]["recorded_history_errors"]


def test_live_contact_other_seat_binding_is_diverged(monkeypatch) -> None:
    from laplace.representation import atlas_bridge

    current = _occupancy("codex:current")
    projection = _history_projection(current)
    projection["events"]["binding:1"]["subject"] = "seat:sensorium-seat:binding"
    projection["events"]["binding:1"]["payload"]["seat_id"] = "sensorium-seat"
    monkeypatch.setattr(
        atlas_bridge, "event_history_projection", lambda _event_ids: projection
    )

    result = _verify_contact(
        _live_contact("codex:current"),
        _authority_epoch(occupancy={"superego-seat": current}),
    )

    assert result["status"] == "INVALID"
    assert result["relation"] == "DIVERGED"


def test_live_contact_binding_after_derived_token_is_diverged(monkeypatch) -> None:
    from laplace.representation import atlas_bridge

    current = _occupancy("codex:current")
    _install_history(monkeypatch, atlas_bridge, current)
    contact = _live_contact("codex:current")
    contact["derived_from"]["cursor"] = 1

    result = _verify_contact(
        contact, _authority_epoch(occupancy={"superego-seat": current})
    )

    assert result["status"] == "INVALID"
    assert result["relation"] == "DIVERGED"


def test_live_contact_requires_exact_historical_derived_token(monkeypatch) -> None:
    from laplace.representation import atlas_bridge

    current = _occupancy("codex:current")
    _install_history(monkeypatch, atlas_bridge, current)

    result = R._verify_live_contact(
        _live_contact("codex:current"),
        authority_epoch=_authority_epoch(occupancy={"superego-seat": current}),
        derived_from_verification={
            "historical_token_exact": False,
            "relation": "DIVERGED",
        },
    )

    assert result["status"] == "INVALID"
    assert result["relation"] == "DIVERGED"


def test_authority_epoch_never_returns_same_when_atlas_moves_between_reads(
    monkeypatch, tmp_path: Path
) -> None:
    from laplace.representation import atlas_bridge

    old = _occupancy("codex:old")
    replacement = _occupancy("codex:new", "binding:2", "join:2")
    projection = _history_projection(old, replacement)
    monkeypatch.setattr(
        atlas_bridge, "event_history_projection", lambda _event_ids: projection
    )
    epoch = _authority_epoch(occupancy={"superego-seat": old})
    monkeypatch.setattr(atlas_bridge, "authority_epoch", lambda: epoch)
    monkeypatch.setattr(
        R,
        "_verify_runtime",
        lambda _expected, _epoch: {
            "historical_token_exact": True,
            "relation": "DESCENDANT",
        },
    )
    monkeypatch.setattr(
        atlas_bridge,
        "drift_token",
        lambda: {
            "cursor": 101,
            "head_event_id": "sha256:" + "f" * 64,
            "head_record_digest": "sha256:" + "1" * 64,
        },
    )
    document = {
        "freshness_vector": {"runtime_atlas": {}},
        "live_contact": _live_contact("codex:old"),
        "fabric_debt": {"total": 0, "all_message_ids_sorted_sha256": R._hash_lines([])},
    }

    _runtime, result, _fabric, observation = R._verify_authority_axes(
        document, repo_root=tmp_path, max_attempts=1
    )

    assert result["status"] == "CHANGED"
    assert result["relation"] == "MOVED-DURING-OBSERVATION"
    assert result["current"] is False
    assert observation["status"] == "MOVED-DURING-OBSERVATION"


def test_legacy_live_contact_is_migration_debt_not_current_or_corruption() -> None:
    result = R._verify_live_contact({"judge_boundary": "Claude is Superego"})

    assert result["status"] == "LEGACY-UNVERIFIABLE"
    assert result["relation"] == "UNKNOWN"
    assert result["current"] is False


def test_payload_digest_matches_jq_sorted_contract() -> None:
    document = json.loads(R.DEFAULT_COORDINATE.read_text(encoding="utf-8"))
    assert R.canonical_payload_digest(document) == document["coordinate_payload_digest"]


def test_hash_lines_is_sorted_input_with_trailing_newline() -> None:
    assert R._hash_lines(["a", "b"]) == R._sha256(b"a\nb\n")
    assert R._hash_lines([]) == R._sha256(b"")


def test_coordinate_refuses_custody_when_atlas_moves_during_axis_assembly(
    monkeypatch, tmp_path: Path
) -> None:
    coordinate = tmp_path / "coordinate.json"
    coordinate.write_text(json.dumps({
        "coordinate_payload_digest": "sha256:coordinate",
        "freshness_vector": {},
        "live_contact": {},
        "fabric_debt": {},
    }), encoding="utf-8")
    before = {
        "cursor": 10,
        "head_event_id": "event:old",
        "head_record_digest": "digest:old",
    }
    after = {
        "cursor": 11,
        "head_event_id": "event:new",
        "head_record_digest": "digest:new",
    }
    monkeypatch.setattr(R, "canonical_payload_digest", lambda _document: "sha256:coordinate")
    monkeypatch.setattr(R, "_find_direct_successors", lambda *_args: {"status": "CURRENT"})
    monkeypatch.setattr(R, "_verify_git", lambda *_args, **_kwargs: {
        "relation": "SAME", "base_tree_exact": True, "new_dirty_paths": [],
        "authority_source_dirty_paths": [], "coordinate_committed_exact": True,
    })
    monkeypatch.setattr(R, "_verify_allowlist_chain", lambda *_args: {"status": "VALID"})
    monkeypatch.setattr(R, "_verify_semantic", lambda *_args: {
        "status": "CURRENT", "fold_origin_exact": True,
    })
    monkeypatch.setattr(
        R,
        "_verify_authority_axes",
        lambda *_args, **_kwargs: (
            {"relation": "SAME", "active_fibre_changed": False, "live": before},
            {"status": "CHANGED", "relation": "MOVED-DURING-OBSERVATION"},
            {"status": "SAME", "total": 0, "identity_source_error": None},
            {"status": "MOVED-DURING-OBSERVATION", "before": before, "after": after},
        ),
    )

    result = R.verify_coordinate(
        coordinate, repo_root=tmp_path, include_blueprint=False
    )

    assert result["coordinate_state"] == "INVALID"
    assert result["authority_observation"]["status"] == "MOVED-DURING-OBSERVATION"
    assert result["custody_allowed"] is False
    assert "Atlas moved while the recovery coordinate axes were assembled" in result["hard_reds"]


def test_coordinate_allowlist_cannot_clear_unclassified_dirty_paths(monkeypatch, tmp_path) -> None:
    responses = {
        ("rev-parse", "HEAD"): b"b" * 40 + b"\n",
        ("cat-file", "-e", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa^{commit}"): b"",
        ("merge-base", "--is-ancestor", "a" * 40, "b" * 40): b"",
        ("diff", "--name-only", "-z", "a" * 40 + ".." + "b" * 40): b"src/new.py\x00",
        ("rev-parse", "a" * 40 + "^{tree}"): b"t" * 40 + b"\n",
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"): b" M old.txt\x00?? new.txt\x00",
        ("diff", "--binary"): b"dirty",
        ("diff", "--cached", "--binary"): b"",
    }

    class Result:
        def __init__(self, stdout=b"", returncode=0):
            self.stdout, self.stderr, self.returncode = stdout, b"", returncode

    def fake_git(_root, *args, check=True):
        key = tuple(args)
        if key == ("cat-file", "-e", "a" * 40 + "^{commit}"):
            return Result()
        return Result(responses[key])

    monkeypatch.setattr(R, "_git", fake_git)
    result = R._verify_git(
        tmp_path,
        {
            "head": "a" * 40,
            "tree": "t" * 40,
            "restored_preexisting_dirty_paths": ["old.txt"],
            "status_nul_sha256_before_coordinate": "different",
            "tracked_diff_sha256_before_coordinate": "different",
            "staged_diff_sha256_before_coordinate": R._sha256(b""),
        },
    )
    assert result["relation"] == "DESCENDANT"
    assert result["new_dirty_paths"] == ["new.txt", "old.txt"]
    assert result["staged_diff_exact"] is True
    assert result["authority_source_dirty_paths"] == []


def test_engine_written_runtime_state_is_visible_but_nonblocking(monkeypatch, tmp_path) -> None:
    responses = {
        ("rev-parse", "HEAD"): b"a" * 40 + b"\n",
        ("merge-base", "--is-ancestor", "a" * 40, "a" * 40): b"",
        ("rev-parse", "a" * 40 + "^{tree}"): b"t" * 40 + b"\n",
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"): (
            b" M .self_embeddings.json\x00 M .fallback_events.jsonl\x00"
            b" M SELF_SHARD_INDEX.md\x00 M contract/journal.jsonl\x00"
            b"?? atlas/stores/runtime/snapshot/conceptric.sqlite3-wal\x00"
        ),
        ("diff", "--binary"): b"runtime",
        ("diff", "--cached", "--binary"): b"",
    }

    class Result:
        def __init__(self, stdout=b"", returncode=0):
            self.stdout, self.stderr, self.returncode = stdout, b"", returncode

    def fake_git(_root, *args, check=True):
        if tuple(args) == ("cat-file", "-e", "a" * 40 + "^{commit}"):
            return Result()
        return Result(responses[tuple(args)])

    monkeypatch.setattr(R, "_git", fake_git)
    result = R._verify_git(
        tmp_path,
        {
            "head": "a" * 40,
            "tree": "t" * 40,
            "restored_preexisting_dirty_paths": [],
            "tracked_diff_sha256_before_coordinate": R._sha256(b"runtime"),
            "staged_diff_sha256_before_coordinate": R._sha256(b""),
        },
    )
    assert result["new_dirty_paths"] == []
    assert result["authority_source_dirty_paths"] == []
    assert result["runtime_derived_dirty_paths"] == [
        ".fallback_events.jsonl",
        ".self_embeddings.json",
        "SELF_SHARD_INDEX.md",
        "atlas/stores/runtime/snapshot/conceptric.sqlite3-wal",
        "contract/journal.jsonl",
    ]


def test_only_the_exact_coordinate_path_is_effective_packaging(monkeypatch, tmp_path) -> None:
    responses = {
        ("rev-parse", "HEAD"): b"b" * 40 + b"\n",
        ("merge-base", "--is-ancestor", "a" * 40, "b" * 40): b"",
        ("diff", "--name-only", "-z", "a" * 40 + ".." + "b" * 40): b"current.json\x00",
        ("rev-parse", "a" * 40 + "^{tree}"): b"t" * 40 + b"\n",
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"): b"",
        ("diff", "--binary"): b"",
        ("diff", "--cached", "--binary"): b"",
    }

    class Result:
        def __init__(self, stdout=b"", returncode=0):
            self.stdout, self.stderr, self.returncode = stdout, b"", returncode

    def fake_git(_root, *args, check=True):
        if tuple(args) == ("cat-file", "-e", "a" * 40 + "^{commit}"):
            return Result()
        return Result(responses[tuple(args)])

    monkeypatch.setattr(R, "_git", fake_git)
    monkeypatch.setattr(R, "_committed_file_exact", lambda _root, _path: True)
    result = R._verify_git(
        tmp_path,
        {
            "head": "a" * 40,
            "tree": "t" * 40,
            "allowed_descendant_paths": [
                "HANDOFF.md", "current.json", "src/laplace/representation/recovery_coordinate.py"
            ],
            "restored_preexisting_dirty_paths": [],
            "status_nul_sha256_before_coordinate": R._sha256(b""),
            "tracked_diff_sha256_before_coordinate": R._sha256(b""),
            "staged_diff_sha256_before_coordinate": R._sha256(b""),
        },
        coordinate_path="current.json",
    )
    assert result["relation"] == "PACKAGED"
    assert result["allowed_descendant_paths"] == ["current.json"]
    assert "src/laplace/representation/recovery_coordinate.py" in result["declared_allowed_descendant_paths"]


def test_declared_source_path_cannot_masquerade_as_packaging(monkeypatch, tmp_path) -> None:
    responses = {
        ("rev-parse", "HEAD"): b"b" * 40 + b"\n",
        ("merge-base", "--is-ancestor", "a" * 40, "b" * 40): b"",
        ("diff", "--name-only", "-z", "a" * 40 + ".." + "b" * 40): (
            b"current.json\x00src/laplace/representation/recovery_coordinate.py\x00"
        ),
        ("rev-parse", "a" * 40 + "^{tree}"): b"t" * 40 + b"\n",
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"): b"",
        ("diff", "--binary"): b"",
        ("diff", "--cached", "--binary"): b"",
    }

    class Result:
        def __init__(self, stdout=b"", returncode=0):
            self.stdout, self.stderr, self.returncode = stdout, b"", returncode

    def fake_git(_root, *args, check=True):
        if tuple(args) == ("cat-file", "-e", "a" * 40 + "^{commit}"):
            return Result()
        return Result(responses[tuple(args)])

    monkeypatch.setattr(R, "_git", fake_git)
    monkeypatch.setattr(R, "_committed_file_exact", lambda _root, _path: True)
    result = R._verify_git(
        tmp_path,
        {
            "head": "a" * 40,
            "tree": "t" * 40,
            "allowed_descendant_paths": [
                "current.json", "src/laplace/representation/recovery_coordinate.py"
            ],
            "restored_preexisting_dirty_paths": [],
            "status_nul_sha256_before_coordinate": R._sha256(b""),
            "tracked_diff_sha256_before_coordinate": R._sha256(b""),
            "staged_diff_sha256_before_coordinate": R._sha256(b""),
        },
        coordinate_path="current.json",
    )
    assert result["relation"] == "DESCENDANT"


def test_dirty_authority_source_is_never_cleared_by_its_own_allowlist(monkeypatch, tmp_path) -> None:
    responses = {
        ("rev-parse", "HEAD"): b"a" * 40 + b"\n",
        ("merge-base", "--is-ancestor", "a" * 40, "a" * 40): b"",
        ("rev-parse", "a" * 40 + "^{tree}"): b"t" * 40 + b"\n",
        ("status", "--porcelain=v1", "-z", "--untracked-files=all"): (
            b" M src/laplace/representation/recovery_coordinate.py\x00"
        ),
        ("diff", "--binary"): b"source-diff",
        ("diff", "--cached", "--binary"): b"",
    }

    class Result:
        def __init__(self, stdout=b"", returncode=0):
            self.stdout, self.stderr, self.returncode = stdout, b"", returncode

    def fake_git(_root, *args, check=True):
        if tuple(args) == ("cat-file", "-e", "a" * 40 + "^{commit}"):
            return Result()
        return Result(responses[tuple(args)])

    monkeypatch.setattr(R, "_git", fake_git)
    result = R._verify_git(
        tmp_path,
        {
            "head": "a" * 40,
            "tree": "t" * 40,
            "restored_preexisting_dirty_paths": ["src/laplace/representation/recovery_coordinate.py"],
            "tracked_diff_sha256_before_coordinate": R._sha256(b"source-diff"),
            "staged_diff_sha256_before_coordinate": R._sha256(b""),
        },
    )
    assert result["new_dirty_paths"] == []
    assert result["authority_source_dirty_paths"] == [
        "src/laplace/representation/recovery_coordinate.py"
    ]


def test_dirty_allowlist_can_only_narrow_across_committed_supersession(monkeypatch, tmp_path) -> None:
    prior = {
        "coordinate_payload_digest": "",
        "freshness_vector": {"git": {"restored_preexisting_dirty_paths": ["old.log"]}},
    }
    prior["coordinate_payload_digest"] = R.canonical_payload_digest(prior)
    (tmp_path / "prior.json").write_text(json.dumps(prior), encoding="utf-8")
    monkeypatch.setattr(R, "_committed_file_exact", lambda _root, _path: True)

    narrowed = {
        "freshness_vector": {"git": {"restored_preexisting_dirty_paths": []}},
        "supersedes": {
            "path": "prior.json",
            "payload_digest": prior["coordinate_payload_digest"],
        },
    }
    assert R._verify_allowlist_chain(narrowed, tmp_path)["status"] == "CHAINED"

    widened = json.loads(json.dumps(narrowed))
    widened["freshness_vector"]["git"]["restored_preexisting_dirty_paths"] = [
        "old.log", "src/new.py"
    ]
    result = R._verify_allowlist_chain(widened, tmp_path)
    assert result["status"] == "INVALID"
    assert result["steps"][0]["widened_by_successor"] == ["src/new.py"]


def test_reverse_currentness_discovers_exact_committed_successor(monkeypatch, tmp_path) -> None:
    packet = tmp_path / "atlas" / "packets" / "recovery"
    packet.mkdir(parents=True)
    prior = {
        "coordinate_id": "coordinate:test",
        "coordinate_version": 1,
        "coordinate_payload_digest": "",
    }
    prior["coordinate_payload_digest"] = R.canonical_payload_digest(prior)
    prior_path = packet / "RECOVERY-COORDINATE-v1.json"
    prior_path.write_text(json.dumps(prior), encoding="utf-8")
    prior_relative = prior_path.relative_to(tmp_path).as_posix()
    successor = {
        "coordinate_id": "coordinate:test",
        "coordinate_version": 2,
        "supersedes": {
            "path": prior_relative,
            "payload_digest": prior["coordinate_payload_digest"],
        },
        "coordinate_payload_digest": "",
    }
    successor["coordinate_payload_digest"] = R.canonical_payload_digest(successor)
    successor_path = packet / "RECOVERY-COORDINATE-CURRENT.json"
    successor_path.write_text(json.dumps(successor), encoding="utf-8")
    monkeypatch.setattr(R, "_committed_file_exact", lambda _root, _path: True)

    result = R._find_direct_successors(
        tmp_path, prior_relative, prior["coordinate_payload_digest"]
    )
    assert result["status"] == "SUPERSEDED"
    assert result["successors"] == [{
        "path": successor_path.relative_to(tmp_path).as_posix(),
        "payload_digest": successor["coordinate_payload_digest"],
        "coordinate_id": "coordinate:test",
        "coordinate_version": "2",
    }]

    successor["supersedes"]["payload_digest"] = "sha256:wrong"
    successor["coordinate_payload_digest"] = R.canonical_payload_digest(successor)
    successor_path.write_text(json.dumps(successor), encoding="utf-8")
    result = R._find_direct_successors(
        tmp_path, prior_relative, prior["coordinate_payload_digest"]
    )
    assert result["status"] == "INVALID"
    assert result["invalid_claims"][0]["reason"] == "predecessor-digest-mismatch"


def test_compact_fabric_debt_uses_count_and_exact_set_digest(monkeypatch) -> None:
    messages = {
        "message:b": {
            "status": "pulled",
            "message": {"recipient_seat_id": "ego-seat", "cursor": 2},
        },
        "message:a": {
            "status": "pulled",
            "message": {"recipient_seat_id": "interface-seat", "cursor": 1},
        },
        "message:c": {
            "status": "queued",
            "message": {"recipient_seat_id": "codex-seat", "cursor": 3},
        },
        "message:done": {
            "status": "delivered",
            "message": {"recipient_seat_id": "sensorium-seat", "cursor": 4},
        },
    }

    result = R._verify_fabric(
        {
            "total": 3,
            "all_message_ids_sorted_sha256": R._hash_lines(
                ["message:a", "message:b", "message:c"]
            ),
        },
        authority_epoch=_authority_epoch(messages={
            key: value for key, value in messages.items() if value["status"] != "delivered"
        }),
    )
    assert result["status"] == "SAME"
    assert result["comparison"] == "count-and-set-digest"
    assert result["by_seat"]["codex-seat"] == {
        "count": 1,
        "queued": 1,
        "pulled": 0,
        "message_ids": ["message:c"],
    }


def test_expanded_fabric_source_plus_delta_reconstructs_exact_identity_set(
    monkeypatch, tmp_path
) -> None:
    source = {
        "schema_version": "atlas.recovery-coordinate/1",
        "coordinate_payload_digest": "",
        "fabric_debt": {
            "total": 2,
            "by_seat": {
                "ego-seat": {"message_ids": ["message:a", "message:b"]},
            },
        },
    }
    source["coordinate_payload_digest"] = R.canonical_payload_digest(source)
    source_path = tmp_path / "expanded.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    messages = {
        "message:b": {
            "status": "pulled",
            "message": {"recipient_seat_id": "ego-seat", "cursor": 2},
        },
        "message:c": {
            "status": "queued",
            "message": {"recipient_seat_id": "codex-seat", "cursor": 3},
        },
    }

    result = R._verify_fabric(
        {
            "total": 2,
            "all_message_ids_sorted_sha256": R._hash_lines(["message:b", "message:c"]),
            "expanded_identity_source": {
                "path": "expanded.json",
                "payload_digest": source["coordinate_payload_digest"],
            },
            "identity_delta": {
                "added_message_ids": ["message:c"],
                "resolved_message_ids": ["message:a"],
            },
        },
        tmp_path,
        authority_epoch=_authority_epoch(messages=messages),
    )
    assert result["status"] == "SAME"
    assert result["comparison"] == "expanded-source-plus-delta"
    assert result["recorded_message_ids"] == ["message:b", "message:c"]
    assert result["expanded_source_message_ids"] == ["message:a", "message:b"]
