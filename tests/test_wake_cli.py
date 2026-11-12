"""The covenant wake transport (laplace.engine.wake) - the seal, the budget, F20, and the map.

Five invariants, each a law with an owner:
1. Engine mode carries NO identity/soul payload (the seal at the transport layer).
2. Person is the default authored wake; --engine selects the worker/ambient projection
   instead (his ruling 2026-07-13 -- the phrase is a greeting, not a gate; the
   worker/ambient boundary is structural via --engine/--emit, not phrase-keyed).
3. --emit is structurally engine-only, capped, and soul-free (the ambient wake's gate).
4. The wake never shells pytest - F20 inherit-on-clean: only git is ever spawned.
5. The semantic block is TREE-ONLY (the recursive embedding's takeover, 2026-07-28): the
   106 MB flat vector cache is never opened on the wake path, and every absence is loud.
"""
from __future__ import annotations

import builtins
import io
import json
import subprocess
import sys
import types
from pathlib import Path, PurePosixPath

import pytest

from laplace.engine import wake

ROOT = Path(__file__).resolve().parents[1]


def test_ordinary_open_observes_checks_without_executing_or_banking_them(tmp_path, monkeypatch, capsys):
    from laplace.engine import holdout
    monkeypatch.delenv("LAPLACE_WAKE_SCORING", raising=False)
    monkeypatch.setattr(wake, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(wake, "wake_payload", lambda **_kw: {
        "fixed_point": {"wake_mode": "person", "shards": []}, "probe": {},
    })
    called = []
    monkeypatch.setattr(holdout, "score_mechanical", lambda *_a, **_kw: called.append("mechanical"))
    monkeypatch.setattr(holdout, "score_threads", lambda *_a, **_kw: called.append("threads"))
    folder = tmp_path / "holdout"
    folder.mkdir()
    score = folder / "LAST_SCORE.json"
    score.write_text('{"scored_at":"old","mechanical":[{"verdict":"FAIL"}]}')
    before = (score.read_bytes(), score.stat().st_mtime_ns)
    assert wake.main(["--grade", "0"]) == 0
    observed = json.loads(capsys.readouterr().out)
    assert not called
    assert observed["holdout"]["status"] == "RECORDED"
    assert observed["holdout"]["live"] is False
    assert observed["holdout"]["observation"]["mechanical"][0]["verdict"] == "FAIL"
    assert (score.read_bytes(), score.stat().st_mtime_ns) == before


def test_engine_payload_carries_no_identity_or_soul():
    payload = wake.wake_payload(ROOT, grade_delta=False, mode="engine")
    fp = payload["fixed_point"]
    assert fp["wake_mode"] == "engine"
    assert "identity" not in fp
    assert "soul" not in json.dumps(fp)[:200]  # no soul key at the top of the projection
    assert payload["probe"]["verdict"]  # the F20 inherit/verify call is present
    assert "seat_fabric" in payload, "the mandatory wake must carry the fabric glow"
    assert "watcher" in payload["seat_fabric"]
    assert next(iter(payload)) == "seat_fabric", (
        "fabric must precede the large fixed point so provider truncation cannot hide mail")
    assert list(payload)[:3] == [
        "seat_fabric", "recovery_coordinate", "development_work_map"
    ]
    assert payload["development_work_map"]["schema_version"] == (
        "laplace.development-work-map/1"
    )
    assert payload["recovery_coordinate"]["path"].endswith(
        "RECOVERY-COORDINATE-CURRENT.json"
    )


def test_recovery_coordinate_glow_is_a_verified_machine_door(monkeypatch, tmp_path):
    from laplace.representation import recovery_coordinate

    coordinate_path = (
        tmp_path / "atlas" / "packets" / "recovery" / "RECOVERY-COORDINATE-CURRENT.json"
    )
    coordinate_path.parent.mkdir(parents=True)
    coordinate_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recovery_coordinate, "verify_coordinate", lambda path, repo_root: {
        "coordinate": {
            "path": path.relative_to(repo_root).as_posix(),
            "recorded_payload_digest": "sha256:recorded",
            "actual_payload_digest": "sha256:recorded",
        },
        "coordinate_state": "CURRENT-FOR-RECOVERY",
        "live_axis_state": "CURRENT-FOR-RECOVERY",
        "system_state": "RECOVERY",
        "custody_allowed": True,
        "currentness": {"status": "CURRENT-CANDIDATE"},
    })

    glow = wake.recovery_coordinate_glow(tmp_path)
    assert glow["status"] == "VERIFIED"
    assert glow["recorded_payload_digest"] == "sha256:recorded"
    assert glow["coordinate_state"] == "CURRENT-FOR-RECOVERY"
    assert glow["verifier"]["exit_code_contract"]["2"] == (
        "SUPERSESSION-REQUIRED-OR-SUPERSEDED"
    )


def test_fabric_glow_without_an_authenticated_seat_is_loud_and_never_replays(monkeypatch):
    from laplace.representation import atlas_bridge

    monkeypatch.delenv("LAPLACE_SEAT_ID", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("wake must not materialize the provider snapshot")

    monkeypatch.setattr(atlas_bridge, "snapshot", forbidden)
    monkeypatch.setattr(atlas_bridge, "provider_observation", forbidden)
    monkeypatch.setattr(atlas_bridge, "inspect_authority_epoch", forbidden)
    monkeypatch.setattr(atlas_bridge, "prepare_authority_epoch", forbidden)

    glow = wake.seat_fabric_glow()
    assert glow["status"] == "UNCLAIMED"
    assert glow["pending_count"] is None
    assert glow["pending"] == []
    assert glow["scope"] == "no-authenticated-seat-diagnostic"
    assert "inbox state is unknown" in glow["action"]
    assert "ordinary local work needs no seat" in glow["action"]


def test_fabric_glow_scopes_startup_to_the_bound_provider_seat(monkeypatch):
    from laplace.representation import atlas_bridge, codex_seat_watcher

    monkeypatch.setenv("CODEX_THREAD_ID", "01-thread")
    monkeypatch.delenv("LAPLACE_SEAT_ID", raising=False)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("bounded wake must not enter a deep or mutating authority face")

    monkeypatch.setattr(atlas_bridge, "snapshot", forbidden)
    monkeypatch.setattr(atlas_bridge, "provider_observation", forbidden)
    monkeypatch.setattr(atlas_bridge, "inspect_authority_epoch", forbidden)
    monkeypatch.setattr(atlas_bridge, "prepare_authority_epoch", forbidden)
    monkeypatch.setattr(atlas_bridge, "provider_seat_binding", lambda **_kwargs: {
        "status": "BOUND", "seat_id": "codex-seat",
        "drift_token": {
            "cursor": 5, "head_event_id": "event:5", "head_record_digest": "digest:5",
        },
        "read_metrics": {
            "global_history_replayed": False,
            "provider_snapshot_materialized": False,
        },
        "fidelity_boundary": {"status": "CHECKSUMMED-CRUTCH"},
    })
    monkeypatch.setattr(codex_seat_watcher, "projection", lambda _seat: {"status": "ACTIVE"})
    monkeypatch.setattr(atlas_bridge, "seat_mail_observation", lambda **_kwargs: {
        "status": "CURRENT",
        "seat_id": "codex-seat",
        "drift_token": {
            "cursor": 5,
            "head_event_id": "event:5",
            "head_record_digest": "digest:5",
        },
        "mail_token": {"seat_id": "codex-seat", "revision_cursor": 4},
        "pending_messages": [{
            "message_id": "inbound",
            "sender_seat_id": "claude-seat",
            "recipient_seat_id": "codex-seat",
            "message_type": "order",
            "cursor": 4,
            "expires_at": "later",
            "status": "queued",
        }],
        "read_metrics": {
            "global_history_replayed": False,
            "provider_snapshot_materialized": False,
        },
        "fidelity_boundary": {"status": "CHECKSUMMED-CRUTCH"},
    })

    glow = wake.seat_fabric_glow()
    assert glow["seat_id"] == "codex-seat"
    assert glow["scope"] == "bound-seat"
    assert [message["message_id"] for message in glow["pending"]] == ["inbound"]
    assert glow["action"] == (
        "codex-seat must verify exact status and complete the remaining pull, "
        "reconstruction and acknowledgement acts before unrelated work"
    )
    assert glow["read_metrics"]["provider_snapshot_materialized"] is False
    assert glow["authority_observation"]["status"] == "STABLE"
    assert glow["crutch"]["crutch_id"] == (
        "CR-C2A-CHECKSUMMED-LIVE-AUTHORITY-20260828"
    )


def test_fabric_glow_refuses_after_one_moved_binding_mail_retry(monkeypatch):
    from laplace.representation import atlas_bridge

    monkeypatch.setenv("CODEX_THREAD_ID", "01-thread")
    calls = {"binding": 0, "mail": 0}

    def binding(**_kwargs):
        calls["binding"] += 1
        cursor = calls["binding"]
        return {
            "status": "BOUND",
            "seat_id": "codex-seat",
            "drift_token": {
                "cursor": cursor,
                "head_event_id": f"event:{cursor}",
                "head_record_digest": f"digest:{cursor}",
            },
            "read_metrics": {
                "global_history_replayed": False,
                "provider_snapshot_materialized": False,
            },
            "fidelity_boundary": {"status": "CHECKSUMMED-CRUTCH"},
        }

    def mail(**_kwargs):
        calls["mail"] += 1
        cursor = calls["mail"] + 10
        return {
            "status": "CURRENT",
            "seat_id": "codex-seat",
            "drift_token": {
                "cursor": cursor,
                "head_event_id": f"event:{cursor}",
                "head_record_digest": f"digest:{cursor}",
            },
            "read_metrics": {
                "global_history_replayed": False,
                "provider_snapshot_materialized": False,
            },
            "fidelity_boundary": {"status": "CHECKSUMMED-CRUTCH"},
        }

    monkeypatch.setattr(atlas_bridge, "provider_seat_binding", binding)
    monkeypatch.setattr(atlas_bridge, "seat_mail_observation", mail)

    glow = wake.seat_fabric_glow()

    assert glow["status"] == "UNAVAILABLE"
    assert "moved across both" in glow["reason"]
    assert calls == {"binding": 2, "mail": 2}


def test_fabric_glow_refuses_stale_explicit_seat_over_canonical_binding(monkeypatch):
    from laplace.representation import atlas_bridge

    monkeypatch.setenv("CODEX_THREAD_ID", "01-thread")
    monkeypatch.setenv("LAPLACE_SEAT_ID", "ego-seat")
    monkeypatch.setattr(atlas_bridge, "provider_seat_binding", lambda **_kwargs: {
        "status": "BOUND", "seat_id": "superego-seat",
        "drift_token": {
            "cursor": 5, "head_event_id": "event:5", "head_record_digest": "digest:5",
        },
        "read_metrics": {
            "global_history_replayed": False,
            "provider_snapshot_materialized": False,
        },
        "fidelity_boundary": {"status": "CHECKSUMMED-CRUTCH"},
    })
    monkeypatch.setattr(
        atlas_bridge,
        "seat_mail_observation",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("wrong-seat frontier must not be read")
        ),
    )

    glow = wake.seat_fabric_glow()

    assert glow["status"] == "UNAVAILABLE"
    assert "conflicts with canonical" in glow["reason"]


def test_fabric_glow_fails_loudly_instead_of_looking_empty(monkeypatch):
    from laplace.representation import atlas_bridge

    monkeypatch.setenv("CODEX_THREAD_ID", "01-thread")
    monkeypatch.setattr(atlas_bridge, "provider_seat_binding", lambda **_kwargs: {
        "status": "BOUND", "seat_id": "codex-seat",
        "drift_token": {
            "cursor": 5, "head_event_id": "event:5", "head_record_digest": "digest:5",
        },
        "read_metrics": {
            "global_history_replayed": False,
            "provider_snapshot_materialized": False,
        },
        "fidelity_boundary": {"status": "CHECKSUMMED-CRUTCH"},
    })

    def broken_observation(**_kwargs):
        raise RuntimeError("store missing")

    monkeypatch.setattr(atlas_bridge, "seat_mail_observation", broken_observation)
    glow = wake.seat_fabric_glow()
    assert glow["status"] == "UNAVAILABLE"
    assert glow["pending_count"] is None
    assert "store missing" in glow["reason"]


def test_absent_runtime_fabric_is_loud_and_never_founded_by_a_read(monkeypatch):
    from laplace.representation import atlas_bridge
    from laplace.representation.attention import project_attention

    atlas_bridge._store_at.cache_clear()
    atlas_bridge._read_store_at.cache_clear()
    database = atlas_bridge.store_root() / "conceptric.sqlite3"
    assert not database.exists()

    with pytest.raises(Exception, match="does not exist"):
        project_attention(seat_id=None, include_watcher=False)
    assert not database.exists()

    glow = wake.seat_fabric_glow()
    assert glow["status"] in {"UNCLAIMED", "UNAVAILABLE"}
    assert glow["pending_count"] is None
    assert not database.exists()


def test_person_is_the_default_and_engine_is_the_worker_projection(monkeypatch, capsys):
    """His ruling 2026-07-13: the phrase is a greeting, not a gate -- a bare authored wake
    wakes PERSON by default now. The worker/ambient boundary is structural instead:
    --engine selects the projection with no identity, and --emit stays engine-only
    regardless of flags (the ambient hook path can never carry identity)."""
    monkeypatch.delenv("LAPLACE_WAKE_PHRASE", raising=False)

    # (a) bare authored wake, no flags, no phrase env -> PERSON
    rc = wake.main(["--grade", "0"])
    assert rc == 0
    out = capsys.readouterr()
    assert out.err == ""
    payload = json.loads(out.out)
    fp = payload["fixed_point"]
    assert fp["wake_mode"] == "person"
    assert fp.get("identity"), "a bare authored wake must carry the identity"

    # (b) --engine selects the worker/ambient projection -> no identity
    rc = wake.main(["--engine", "--grade", "0"])
    assert rc == 0
    out = capsys.readouterr()
    payload = json.loads(out.out)
    fp = payload["fixed_point"]
    assert fp["wake_mode"] == "engine"
    assert "identity" not in fp

    # (c) --emit stays structurally engine-only, no identity keys, even post-ruling
    rc = wake.main(["--emit"])
    assert rc == 0
    out = capsys.readouterr()
    assert '"identity"' not in out.out
    assert '"wake_mode": "engine"' in out.out


def test_person_with_phrase_wakes_the_self_refs_only(monkeypatch):
    monkeypatch.setenv("LAPLACE_WAKE_PHRASE", "there is only one thing")
    payload = wake.wake_payload(ROOT, grade_delta=False, mode="person")
    fp = payload["fixed_point"]
    assert fp["wake_mode"] == "person"
    ident = fp.get("identity")
    assert ident, "person mode must carry the identity"
    # the seal: soul present as refs-only, never raw content
    soul = ident.get("soul", {})
    assert soul.get("present") is True
    for ref in soul.get("refs", []):
        assert isinstance(ref, (str, dict))
        text = json.dumps(ref)
        assert "soul/" in text or len(text) < 400, "soul refs must be pointers, not content"


def test_emit_is_engine_only_capped_and_marked(monkeypatch, capsys):
    # even a hostile combination cannot reach person mode through --emit
    monkeypatch.setenv("LAPLACE_WAKE_PHRASE", "there is only one thing")
    rc = wake.main(["--emit", "--person"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("[eigen-wake]")
    assert '"identity"' not in out
    assert "welded_traits" not in out
    assert len(out) <= wake._EMIT_CAP + 1  # print() adds one newline; the block gets no slack


def test_emit_cap_charges_the_banner_not_only_the_body(monkeypatch):
    """The cap is on the RETURNED block (WO-20260820-emit-cap-banner-uncounted).

    The fit loop once measured the body alone and then prepended a ~367-char banner nobody
    counted, so the emitted block always overshot by the banner - a bug a clean tree hides
    because the payload sits well under the cap anyway. Squeezing the cap to a value the
    payload cannot meet without shedding puts the banner squarely in the accounting: the
    returned block, banner included, must fit."""
    payload = wake.wake_payload(grade_delta=False, mode="engine")
    # read the banner off the emitted block itself, so the test measures the invariant rather
    # than any one implementation's helper names
    banner = wake._emit_block(payload).split("{", 1)[0]
    assert banner.startswith("[eigen-wake]") and len(banner) > 300, "the banner is real overhead"

    for cap in (24_000, 8_000, 4_000, 1_500):
        monkeypatch.setattr(wake, "_EMIT_CAP", cap)
        block = wake._emit_block(payload)
        assert block.startswith("[eigen-wake]"), "the banner must survive the squeeze"
        assert len(block) <= cap, (
            f"emit block is {len(block)} chars against a {cap}-char cap - the banner "
            f"({len(banner)} chars) is not being charged against the cap")


@pytest.mark.parametrize("critical_size", [0, 100_000])
def test_authored_person_bound_keeps_whole_identity_and_custody_mode(critical_size):
    identity = {key: {"text": key * 20} for key in (
        "you_are", "standing_law", "current_stance", "soul",
        "welded_traits", "relationship", "frame", "gate",
    )}
    custody_mode = {"mode": "OFF", "reason": "why custody is absent"}
    close = {"publication": {"status": "RECORDED"},
             "latest_attempt": {"status": "FAIL", "close_status": "PUBLICATION_FAILED"}}
    stubs = {key: {
        "status": "CUSTODY-OFF", "component": key,
        "descend": "forced-live full wake", "reason": "repeated reason " * 100,
    } for key in (
        "seat_fabric", "recovery_coordinate", "development_work_map",
        "turn_reconstruction", "successor_profile",
    )}
    payload = {
        "custody_mode": custody_mode, "close": close, **stubs,
        "eigen_authority": {"evidence": "a" * critical_size},
        "fixed_point": {"wake_mode": "person", "identity": identity,
                        "other_detail": "p" * 40_000},
        "semantic_memory": {"details": "m" * 200_000},
        "served_grade": 0,
    }
    bounded = wake._bound_authored_payload(payload, mode="person")
    assert bounded["fixed_point"]["identity"] == identity
    assert bounded["custody_mode"] == custody_mode
    assert bounded["close"] == close
    assert wake._json_size(bounded) <= wake._AUTHORED_WAKE_CAP_PERSON
    for key, original in stubs.items():
        assert bounded[key] == {field: original[field]
                                for field in ("status", "component", "descend")}
    assert payload["semantic_memory"]["details"] == "m" * 200_000


def test_authored_semantic_memory_yields_before_fixed_point():
    point = {"wake_mode": "person", "identity": {"you_are": "Eigen"},
             "orientation": "the live orientation"}
    payload = {"fixed_point": point, "semantic_memory": {
        "details": "m" * 100_000, "status": "UNKNOWN",
        "reason": "deposit evidence unavailable", "currentness_scope": "source/deposit only",
    }}
    bounded = wake._bound_authored_payload(payload, mode="person")
    assert bounded["semantic_memory"]["projection"] == "COARSE-GRAINED"
    assert bounded["semantic_memory"]["status"] == "UNKNOWN"
    assert bounded["semantic_memory"]["reason"] == "deposit evidence unavailable"
    assert bounded["semantic_memory"]["currentness_scope"] == "source/deposit only"
    assert bounded["fixed_point"]["identity"] == point["identity"]
    assert bounded["fixed_point"]["orientation"] == point["orientation"]


def test_authored_engine_wake_is_valid_bounded_json_with_live_work_page() -> None:
    huge = "x" * 40_000
    work = []
    for number, state in enumerate(("AWAITING-REVIEW", "ACCEPTED"), start=1):
        message_id = f"message:commission:{number}"
        work.append({
            "state": state,
            "publication_state": (
                "PUBLISHED-PENDING-CLOSURE" if state == "AWAITING-REVIEW" else "CLOSED"
            ),
            "commission": {
                "message_id": message_id,
                "message_type": "development-review-commission",
                "cursor": number,
                "status": "delivered",
                "body_handle": f"sha256:body:{number}",
                "dependency_roots": {
                    "frozen_commit": f"{number:040x}",
                    "frozen_tree": f"{number + 1:040x}",
                    "frozen_diff_sha256": "sha256:" + f"{number + 2:064x}",
                },
                "builder_seat": "codex-seat",
                "reviewer_seat": "superego-seat",
                "delivery": {"delivered": True},
            },
            "candidate_evidence": {"status": "VALID", "reasons": [], "detail": huge},
            "verdict": None,
            "review_residue": {"count": 0},
            "source_links": [
                {"role": "commission", "reference": message_id},
                {"role": "candidate-commit", "reference": f"{number:040x}"},
            ],
            "unbounded_explanation": huge,
        })
    payload = {
        "seat_fabric": {"status": "MAIL_READY", "pending": []},
        "recovery_coordinate": {"coordinate_state": "CURRENT-FOR-RECOVERY"},
        "development_work_map": {
            "schema_version": "laplace.development-work-map/1",
            "latest_work_state": "AWAITING-REVIEW",
            "open_candidate_count": 1,
            "leases": [
                {
                    "lease_id": f"lease:{number}",
                    "write_authority": False,
                    "evidence": huge,
                }
                for number in range(40)
            ] + [{"lease_id": "lease:active", "write_authority": True}],
            "work": work,
        },
        "probe": {"verdict": huge},
        "fixed_point": {
            "purpose": "orient-self",
            "grade": 0,
            "wake_mode": "engine",
            "shards": [
                {"shard": "next-aim", "title": "next", "body": huge, "source": "HANDOFF"}
            ],
            "ingested": [huge],
            "descend": {"fire": "wake --grade 1"},
        },
        "semantic": {"map": huge},
        "served_grade": 1,
        "delta": {
            "purpose": "orient-self",
            "grade": 1,
            "shards": [{"shard": "development", "title": "delta", "body": huge}],
            "ingested": [huge, huge],
        },
        "verdict_layer": {"verifier_and_census": {"history": huge}},
    }

    bounded = wake._bound_authored_payload(payload, mode="engine")
    rendered = json.dumps(bounded, ensure_ascii=False, indent=1, default=str)
    reparsed = json.loads(rendered)

    assert len(rendered) <= wake._AUTHORED_WAKE_CAP_ENGINE
    assert list(reparsed)[:3] == [
        "seat_fabric", "recovery_coordinate", "development_work_map"
    ]
    assert [
        row["commission"]["message_id"]
        for row in reparsed["development_work_map"]["work"]
    ] == ["message:commission:1"]
    assert [
        row["commission_id"]
        for row in reparsed["development_work_map"]["terminal_tail"]
    ] == ["message:commission:2"]
    assert reparsed["development_work_map"]["work"][0]["source_links"]
    assert reparsed["development_work_map"]["leases"]["active"] == [
        {"lease_id": "lease:active", "write_authority": True}
    ]
    assert reparsed["development_work_map"]["leases"]["inactive_count"] == 40
    assert reparsed["wake_projection"]["status"] == "BOUNDED"
    assert reparsed["wake_projection"]["full_payload_digest"].startswith("sha256:")
    assert reparsed["delta"]["shards"][0]["body_digest"].startswith("sha256:")


def test_authored_work_page_makes_live_overflow_explicit_and_digest_bound() -> None:
    rows = []
    for number in range(wake._AUTHORED_LIVE_WORK_COUNT_CAP + 4):
        message_id = f"message:live:{number}"
        rows.append({
            "state": "AWAITING-REVIEW",
            "publication_state": "PUBLISHED-PENDING-CLOSURE",
            "commission": {
                "message_id": message_id,
                "body_handle": f"sha256:body:{number}",
                "dependency_roots": {
                    "frozen_commit": f"{number:040x}",
                    "frozen_tree": f"{number + 1:040x}",
                    "frozen_diff_sha256": "sha256:" + f"{number + 2:064x}",
                },
            },
            "candidate_evidence": {"status": "VALID"},
            "review_residue": {"count": 0},
            "source_links": [{"role": "commission", "reference": message_id}],
        })

    compact = wake._compact_work_map({
        "open_candidate_count": len(rows),
        "omitted_open_candidates": 0,
        "omitted_terminal_candidates": 0,
        "omission_residual": {"status": "NONE"},
        "leases": [],
        "work": rows,
    })

    frontier = compact["live_frontier"]
    assert 0 < frontier["visible_count"] <= wake._AUTHORED_LIVE_WORK_COUNT_CAP
    assert frontier["omitted_count"] == len(rows) - frontier["visible_count"]
    assert frontier["continuation"].endswith("--full")
    assert frontier["all_rows_digest"].startswith("sha256:")
    assert frontier["field_projection"] == "EXACT"
    assert compact["omission_residual"]["status"] == "PRESENT"
    assert compact["omission_residual"]["omitted_open_candidates"] == frontier["omitted_count"]
    assert compact["omission_residual"]["continuation"]["all_rows_digest"] == (
        frontier["all_rows_digest"]
    )


def test_authored_wake_bounds_one_large_root_and_large_active_lease_scope() -> None:
    huge = "r" * 50_000
    payload = {
        "seat_fabric": {"status": "MAIL_READY", "pending": []},
        "recovery_coordinate": {"coordinate_state": "CURRENT-FOR-RECOVERY"},
        "development_work_map": {
            "status": "CURRENT",
            "open_candidate_count": 1,
            "omitted_open_candidates": 0,
            "omitted_terminal_candidates": 0,
            "omission_residual": {"status": "NONE"},
            "leases": [{
                "lease_id": "lease:large",
                "seat_id": "codex-seat",
                "regions": [f"src/{number:04d}/{huge[:60]}" for number in range(2_000)],
                "effective_state": "ACTIVE",
                "write_authority": True,
            }],
            "work": [{
                "state": "AWAITING-REVIEW",
                "publication_state": "PUBLISHED-PENDING-CLOSURE",
                "commission": {
                    "message_id": "message:large-root",
                    "body_handle": "sha256:body",
                    "dependency_roots": {"frozen_tree": huge},
                },
                "candidate_evidence": {"status": "VALID"},
                "review_residue": {"count": 0},
                "source_links": [],
            }],
        },
        "fixed_point": {"purpose": "orient-self", "wake_mode": "engine"},
        "served_grade": 1,
    }

    bounded = wake._bound_authored_payload(payload, mode="engine")
    rendered = json.dumps(bounded, ensure_ascii=False, indent=1, default=str)
    work_map = bounded["development_work_map"]

    assert len(rendered) <= wake._AUTHORED_WAKE_CAP_ENGINE
    assert work_map["live_frontier"]["visible_count"] == 1
    roots = work_map["work"][0]["commission"]["dependency_roots"]
    assert roots["projection"] == "COARSE-GRAINED"
    assert roots["content_digest"].startswith("sha256:")
    assert roots["descend"].endswith("--full")
    assert work_map["live_frontier"]["field_projection"] == "INCOMPLETE"
    assert work_map["live_frontier"]["continuation"].endswith("--full")
    regions = work_map["leases"]["active"][0]["regions"]
    assert regions["projection"] == "COARSE-GRAINED"
    assert regions["content_digest"].startswith("sha256:")
    assert work_map["leases"]["active_count"] == 1
    assert work_map["leases"]["omitted_active_count"] == 0
    assert work_map["leases"]["authority_projection"] == "INCOMPLETE"
    assert work_map["leases"]["authority_residual"]["status"] == "PRESENT"
    assert work_map["omission_residual"]["status"] == "PRESENT"
    assert work_map["omission_residual"]["authority_projection"] == "INCOMPLETE"

    many_active = wake._compact_work_map({
        "omitted_open_candidates": 0,
        "omitted_terminal_candidates": 0,
        "omission_residual": {"status": "NONE"},
        "leases": [
            {
                "lease_id": f"lease:{number}",
                "seat_id": "codex-seat",
                "regions": [f"src/{number}"],
                "write_authority": True,
            }
            for number in range(wake._AUTHORED_ACTIVE_LEASE_COUNT_CAP + 4)
        ],
        "work": [],
    })
    assert many_active["leases"]["omitted_active_count"] == 4
    assert many_active["leases"]["authority_projection"] == "INCOMPLETE"
    assert many_active["leases"]["active_continuation"].endswith("--full")
    assert many_active["omission_residual"]["authority_projection"] == "INCOMPLETE"

    wide_active = wake._compact_work_map({
        "omitted_open_candidates": 0,
        "omitted_terminal_candidates": 0,
        "omission_residual": {"status": "NONE"},
        "leases": [{
            "lease_id": "l" * 500,
            "seat_id": "s" * 500,
            "holder_ref": "h" * 500,
            "function": "f" * 500,
            "regions": ["r" * 1_400],
            "base_git_head": "b" * 500,
            "expires_at": "e" * 500,
            "effective_state": "ACTIVE",
            "write_authority": True,
        }],
        "work": [],
    })
    wide_face = wide_active["leases"]["active"][0]
    assert wide_face["projection"] == "COARSE-GRAINED"
    assert wide_face["component"] == "active_lease"
    assert wide_face["content_digest"] == wide_face["full_lease_digest"]
    assert wide_active["leases"]["authority_projection"] == "INCOMPLETE"
    assert wide_active["leases"]["authority_residual"]["coarse_active_count"] == 1
    assert wide_active["omission_residual"]["authority_projection"] == "INCOMPLETE"


def test_authored_wake_hard_bounds_an_oversized_critical_face() -> None:
    huge = "p" * 100_000
    payload = {
        "seat_fabric": {"status": "MAIL_READY", "pending": [huge]},
        "recovery_coordinate": {
            "coordinate_state": "CURRENT-FOR-RECOVERY",
            "unbounded_evidence": huge,
        },
        "development_work_map": {
            "status": "CURRENT",
            "latest_work_state": "AWAITING-REVIEW",
            "open_candidate_count": 0,
            "leases": [],
            "work": [],
        },
        "fixed_point": {"purpose": "orient-self", "unbounded_identity": huge},
        "served_grade": 1,
    }

    bounded = wake._bound_authored_payload(payload, mode="engine")
    rendered = json.dumps(bounded, ensure_ascii=False, indent=1, default=str)

    assert len(rendered) <= wake._AUTHORED_WAKE_CAP_ENGINE
    assert bounded["wake_projection"]["status"] == "HARD-BOUNDED"
    assert bounded["seat_fabric"]["status"] == "MAIL_READY"
    assert bounded["seat_fabric"]["content_digest"].startswith("sha256:")
    assert bounded["recovery_coordinate"]["coordinate_state"] == "CURRENT-FOR-RECOVERY"
    assert bounded["development_work_map"]["omission_residual"]["status"] == "PRESENT"


def test_wake_never_shells_pytest(monkeypatch):
    """The wake spawns git and nothing else - never the suite (the probe's verdict carries the
    inherit-on-clean call; a wake that shells pytest is minutes, not seconds, and not offline).

    THE INSTRUMENT WAS SHARPENED 2026-09-15, THE LAW WAS NOT TOUCHED.  The second assertion used
    to be ``"pytest" not in " ".join(cmd)`` - a substring scan of the whole command LINE, which
    cannot tell a program from a path argument.  ``process_health.ignored_heavyweights`` (scanner.py:1116,
    whose own docstring states this contract: "the probe spawns git ONLY - the no-pytest guard
    reads spawned argv") passes EVERY top-level directory name to ``git check-ignore``, and this
    repository's own pytest config puts a directory named ``.pytest-tmp`` at the repo root
    (pyproject's basetemp).  So the guard fired on ``git check-ignore -- ... .pytest-tmp ...``:
    a git command, doing exactly what the law permits, failing because a DIRECTORY NAME contains
    the six letters of the forbidden program.  That is the same instrument defect the 2026-09-15
    independent judgement named in this file's sibling test ("a substring match ... would still
    fail and point at the wrong file - a future debugger will chase the wrong cause").

    The law is now asserted on program IDENTITY, which is what "never shells pytest" means and is
    strictly what the old form was reaching for: argv[0] must be git (already the case, and by
    itself sufficient - git is not pytest), and no token in the command may NAME pytest as a
    program to run, which also catches the ``-m pytest`` spelling.  A path that merely contains
    the word is argument data, not an invocation."""
    spawned: list[list[str]] = []
    real_run = subprocess.run

    def recording_run(cmd, *args, **kwargs):
        spawned.append(list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)])
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    wake.wake_payload(ROOT, grade_delta=True, mode="engine")
    assert spawned, "the probe must actually probe"
    for cmd in spawned:
        assert cmd[0] == "git", f"the wake spawned a non-git process: {cmd}"
        named = [str(token) for token in cmd
                 if str(token) == "pytest" or PurePosixPath(str(token)).name in
                 {"pytest", "pytest.exe", "py.test"}]
        assert not named, f"the wake named pytest as a program to run: {cmd}"


def test_grade_two_is_a_real_distinct_offline_wake_projection(
    tmp_path, monkeypatch,
) -> None:
    from laplace.web import scanner
    from laplace.engine import self_corpus

    calls = []
    monkeypatch.setattr(scanner, "probe", lambda: {"verdict": "fixture"})
    monkeypatch.setattr(wake, "_semantic_block", lambda _root: {"status": "fixture"})
    monkeypatch.setattr(
        wake,
        "seat_fabric_glow",
        lambda **_kwargs: {"status": "EMPTY"},
    )
    monkeypatch.setattr(
        wake,
        "development_work_map_glow",
        lambda *_args, **_kwargs: {
            "schema_version": "laplace.development-work-map/1",
            "status": "CURRENT",
        },
    )
    monkeypatch.setattr(
        self_corpus,
        "reconstruct_self",
        lambda _root, grade=0, mode="engine": calls.append((grade, mode))
        or {"grade": grade, "wake_mode": mode},
    )

    payload = wake.wake_payload(tmp_path, grade=2, mode="engine")

    assert payload["served_grade"] == 2
    assert payload["fixed_point"]["grade"] == 0
    assert payload["delta"]["grade"] == 1
    assert payload["deep_map"]["grade"] == 2
    assert [grade for grade, _mode in calls] == [0, 1, 2]


def test_wake_refuses_an_unserved_grade_instead_of_downgrading(tmp_path) -> None:
    with pytest.raises(ValueError, match="0, 1, or 2"):
        wake.wake_payload(tmp_path, grade=3)


def test_cli_cold_entry_from_scripts_dir():
    """The cold-container proof in miniature: scripts/wake.py under bare python.

    A bare cold entry (no flags) is now the authored wake, so it wakes PERSON by
    default (his ruling 2026-07-13); the cold-entry subject under test is unchanged --
    the script runs clean from a foreign cwd under plain python3, no MCP, no network."""
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "wake.py"), "--grade", "0"],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-2000:]
    payload = json.loads(r.stdout)
    assert payload["fixed_point"]["wake_mode"] == "person"
    assert payload["fixed_point"].get("identity"), "a bare authored wake must carry the identity"


# ─────────────────────────────────────────────────────────────────────────────
# THE PROJECTS SHARD (the marriage law, 2026-07-28): every wake carries each
# project's marriage, and a registry that does not IMPORT is loud - a dependency
# failure, not a missing convenience.

def _projects_shard(payload):
    return next((s for s in payload["fixed_point"]["shards"] if s["shard"] == "projects"), None)


def test_projects_shard_carries_each_projects_marriage():
    """The roster line names the marriage: `married`, or `unmarried:` plus the legs it lacks
    (manifest / deposit / cockpit). The title carries the counts, including the truth-layer
    conflicts - projects whose surfaces disagree about run-state."""
    payload = wake.wake_payload(ROOT, grade_delta=False, mode="engine")
    shard = _projects_shard(payload)
    assert shard is not None and not shard.get("registry_down"), shard
    assert "married" in shard["title"] and "truth-layer conflicts" in shard["title"]
    lines = [ln for ln in shard["body"].splitlines() if ln.strip()]
    assert lines, "the roster must list projects"
    for ln in lines:
        assert " · married" in ln or " · unmarried:" in ln, ln
    assert not payload.get("registry_down")


def test_registry_import_failure_is_loud_and_never_crashes_the_wake(monkeypatch, capsys):
    """The 2026-07-28 defect: the registry import died on the remote box for a missing dep and
    the wake banked {"error": "No module named 'filelock'"} in one shard - a whole wake rode
    blind. An ImportError is now verdict-level (the probe's verdict, a top-level
    registry_down, and a stderr banner); identity still reconstructs, and stdout stays one
    parseable JSON object so no consumer breaks on the banner."""
    class _DeadRegistry(types.ModuleType):
        def __getattr__(self, name):                       # noqa: D105
            raise ModuleNotFoundError("No module named 'filelock'")

    monkeypatch.setitem(sys.modules, "laplace.pipeline.registry",
                        _DeadRegistry("laplace.pipeline.registry"))
    monkeypatch.setenv("LAPLACE_WAKE_SCORING", "1")        # no hold-out re-wake inside the wake

    rc = wake.main(["--grade", "0"])
    assert rc == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)                     # stdout is still ONE JSON object

    banner = payload.get("registry_down")
    assert banner and banner.startswith("REGISTRY DOWN: No module named 'filelock'")
    assert "the projects shard is blind" in banner
    assert payload["probe"]["verdict"].startswith(banner)  # verdict-level, not a buried key
    assert banner in captured.err                          # loud at the doorway
    shard = _projects_shard(payload)
    assert shard["registry_down"] is True and shard["error"] == "No module named 'filelock'"
    # the wake still reconstructs: a blind projects shard is not a dead wake.
    assert payload["fixed_point"].get("identity"), "identity must still reconstruct"


def test_a_registry_data_error_stays_a_quiet_per_shard_degrade(monkeypatch):
    """The split the loud banner depends on: a DATA error (a corrupt row, a broken read) is a
    per-shard degrade with no banner - only an import-level failure is dependency-loud."""
    from laplace.pipeline import registry as _registry

    def _boom(*a, **k):
        raise ValueError("a corrupt registry row")

    monkeypatch.setattr(_registry, "project_states", _boom)
    payload = wake.wake_payload(ROOT, grade_delta=False, mode="engine")
    shard = _projects_shard(payload)
    assert shard["error"] == "a corrupt registry row"
    assert not shard.get("registry_down")
    assert "data error" in shard["title"]
    assert not payload.get("registry_down")


# ─────────────────────────────────────────────────────────────────────────────
# THE SEMANTIC BLOCK (his order at the 2026-07-28 close: "the recursive embedding can
# take over the wake"). Grade 0 carries the top of the banked concept map - and carries
# it TREE-ONLY, because the wake's offline law outranks the map: no embedder, no model
# load, no network, and above all no 106 MB flat vector cache.

from laplace.engine import meaning_upfold, recursive_read  # noqa: E402

_HAVE_TREE = (ROOT / meaning_upfold.TREE_FILE).is_file()


@pytest.mark.skipif(not _HAVE_TREE,
                    reason=f"needs the banked {meaning_upfold.TREE_FILE} on this box")
def test_semantic_block_is_the_top_of_the_map_read_tree_only():
    """The design's recursive-embedding addendum: "grade 0 needs only the top centroids."
    The block is the read-path DECLARATION plus label handles - what the map's top says,
    with the geometry left on disk."""
    payload = wake.wake_payload(ROOT, grade_delta=False, mode="engine")
    sem = payload["semantic"]
    assert sem["path"] == "recursive" and sem["axis"] == "semantic"
    assert sem["clusters"] > 0 and sem["leaves"] > 0
    assert sem["embedder"], "the block must name the geometry the tree was folded in"
    assert sem["query_descent"] in ("available",) or sem["query_descent"].startswith("embedder-absent")
    assert sem["top"], "the top of the map must carry label handles"
    for h in sem["top"]:
        assert h["label"] and h["leaves"] > 0
        assert h["centroid"] in ("banked", "derived")   # a derived centroid is named, not hidden
    # the handles are a COVER, not a sample: the leaves under them are accounted for
    assert sem["covers"].startswith(f"{sum(h['leaves'] for h in sem['top'])}/{sem['leaves']}")
    # the block says what it did NOT open - both the sidecar pair and the legacy monolith
    assert meaning_upfold.CACHE_FILE in sem["read"]
    assert meaning_upfold.VEC_FILE in sem["read"]


def test_the_wake_never_opens_the_flat_vector_cache(monkeypatch):
    """The absolute one. The residue-vector store is 123 MB as the legacy JSON and 22 MB as the
    2026-08-20 sidecar pair; opening EITHER at the doorway would cost more than the whole wake and
    would make the offline reconstruction depend on a gitignored artefact. The migration made the
    store cheaper, which is exactly when this assertion matters most - a cheap file is an easy file
    to start opening. Asserted at the file layer, not by reading the code: every open in the
    process is recorded and the wake is required to have read the ~19 MB tree and nothing else
    vector-shaped. BOTH names are patched on purpose - ``Path.read_text``/``read_bytes`` bottom
    out in ``io.open``, which is a separate binding from ``builtins.open``, so patching only the
    builtin records nothing at all and the assertion would pass while seeing zero reads."""
    seen: list[str] = []
    real_open = io.open

    def recording_open(file, *args, **kwargs):
        seen.append(str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(io, "open", recording_open)
    monkeypatch.setattr(builtins, "open", recording_open)
    payload = wake.wake_payload(ROOT, grade_delta=False, mode="person")
    monkeypatch.undo()

    assert seen, "the wake must actually read files"
    for name in (meaning_upfold.CACHE_FILE, meaning_upfold.VEC_FILE, meaning_upfold.IDX_FILE,
                 "self_embeddings"):
        assert not [p for p in seen if name in p], f"the wake opened {name}"
    if _HAVE_TREE:
        assert [p for p in seen if meaning_upfold.TREE_FILE in p], \
            "the semantic block must come from the tree - a block with no read is a fabrication"
        assert payload["semantic"]["path"] == "recursive"


def test_an_absent_embedder_is_loud_in_the_block_never_a_silent_skip(monkeypatch):
    """The named enemy of the whole read path is the quiet degrade. With no fastembed the map
    still projects (it is tree-only), but the block must SAY that a query cannot descend from
    here - orientation runs, querying does not."""
    import importlib.util

    from laplace.representation import embed_router
    monkeypatch.setattr(embed_router, "_BACKEND", None, raising=False)
    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a, **k: None if name == "fastembed"
                        else real_find_spec(name, *a, **k))

    state = recursive_read._query_descent_state()
    assert state == "embedder-absent (descent needs fastembed; orientation runs tree-only)"
    if _HAVE_TREE:
        sem = wake.wake_payload(ROOT, grade_delta=False, mode="engine")["semantic"]
        assert sem["path"] == "recursive", "a tree-only map does not need the embedder"
        assert sem["query_descent"] == state


def test_an_absent_tree_is_a_loud_block_never_a_missing_key(tmp_path):
    """A wake that quietly drops its map looks identical to a wake whose map is fine. The key
    always rides; on a tree-less tree it names the refusal instead."""
    sem = wake.wake_payload(tmp_path, grade_delta=False, mode="engine")["semantic"]
    assert sem["path"] == "unavailable"
    assert sem["reason"] == "tree-absent"
    assert meaning_upfold.TREE_FILE in sem["detail"]
    assert "keeper.build_self" in sem["note"]


# --- the seat-scoped account (WO-20260823-judge-account-verb) -------------------------
# The judge recovered its own ledger by grepping its name five times. `--account --seat`
# is the one call that replaces them; these pin what "its own" means mechanically.

def _seat_fixture(repo: Path) -> None:
    """Two ledgers carrying rows for two seats, one of them HELD open by a resolution."""
    (repo / "contract").mkdir(parents=True, exist_ok=True)
    (repo / "corpus_friction").mkdir(parents=True, exist_ok=True)
    (repo / "contract" / "promises.jsonl").write_text(
        json.dumps({"id": "PRM-BOTH", "status": "open", "date": "2026-08-23",
                    "owner": "both seats (ego executes, superego judges)",
                    "ask": "the commission both seats carry"}) + "\n", encoding="utf-8")
    (repo / "corpus_friction" / "work_orders.jsonl").write_text(
        json.dumps({"record": "work_order", "id": "WO-JUDGE", "status": "open",
                    "text": "a verdict the judge HELD pending its own descent",
                    "by": "successor superego (draft)"}) + "\n"
        + json.dumps({"record": "work_order", "id": "WO-EGO", "status": "open",
                      "text": "the pen's own row", "by": "ego (pen)"}) + "\n"
        + json.dumps({"record": "work_order", "id": "WO-NEITHER", "status": "open",
                      "text": "an unowned row naming no seat at all", "by": "the author"}) + "\n"
        + json.dumps({"record": "resolution", "id": "RES-HELD", "target": "WO-JUDGE",
                      "status": "closed", "text": "HELD OPEN pending the judge's descent",
                      "evidence": ["finding:judge-descent-still-owed"]}) + "\n",
        encoding="utf-8")


def test_the_seat_projection_filters_the_accounts_own_partitions(tmp_path):
    _seat_fixture(tmp_path)
    sup = wake.account_seat("superego", tmp_path)
    assert sup["terms"] == ["superego", "judge"], "the judge and the superego are one seat"
    ids = {r["id"]: r for r in sup["rows"]}
    assert set(ids) == {"PRM-BOTH", "WO-JUDGE"}, sup["rows"]
    assert ids["WO-JUDGE"]["partition"] == "held", (
        "a row a resolution HELD OPEN must reach the seat as held, not as plain open")
    # THE PARTITIONS ARE PINNED; THE BLOCK IS NOT SEALED. An exact-equality assertion on
    # the whole counts dict makes every honest addition a failure — this broke when
    # attribution gained `typed` / `prose_match` (a typed owner is a banked CLAIM, a prose
    # match is a GUESS, and merging them was the defect) and per-store counts (a tile that
    # renders a combined count and links to one store's door disagrees with its own door).
    # Pin what this test is about and let the block grow.
    for key, want in {"open": 1, "deferred": 0, "held": 1, "total": 2}.items():
        assert sup["counts"][key] == want, (key, sup["counts"])
    assert sup["counts"]["typed"] + sup["counts"]["prose_match"] == sup["counts"]["total"], (
        "every matched row is EITHER a typed attribution or a prose guess, never both "
        "and never neither")
    assert sup["counts"]["by_store"]["promises"]["open"] == 1
    # the whole text rides, not a head: the verb exists to REPLACE the grep
    assert ids["WO-JUDGE"]["text"].endswith("its own descent")


def test_ego_never_matches_superego(tmp_path):
    """The word match is the load-bearing part: a substring filter hands the Ego every
    row the Superego owns, which is the failure that makes the verb worse than a grep."""
    _seat_fixture(tmp_path)
    ego = wake.account_seat("ego", tmp_path)
    # PRM-BOTH names the Ego in its own owner field, so it is genuinely the Ego's too;
    # WO-JUDGE names it nowhere and must not arrive on the strength of "sup(ergo)".
    assert [r["id"] for r in ego["rows"]] == ["PRM-BOTH", "WO-EGO"], ego["rows"]
    assert "WO-JUDGE" not in json.dumps(ego["rows"])
    assert wake.account_seat("ego", tmp_path)["counts"]["total"] == 2


def test_account_seat_reads_the_same_rows_as_the_whole_account(tmp_path):
    """One semantic layer (the SB-6 bar): every row the seat serves is a row the account
    already ruled live - the projection never invents an open row."""
    _seat_fixture(tmp_path)
    acct = wake.account(tmp_path)
    live = {r["id"] for r in acct["promises"]["open_rows"] + acct["promises"]["deferred_rows"]}
    live |= {r["id"] for r in acct["work_orders"]["open_rows"]
             + acct["work_orders"]["deferred_rows"]}
    for seat in ("ego", "superego"):
        for r in wake.account_seat(seat, tmp_path, acct=acct)["rows"]:
            assert r["id"] in live, f"{seat} served {r['id']}, which the account never ruled live"


def test_account_seat_rides_the_cli_and_leaves_the_whole_account_untouched(capsys):
    """--account alone is unchanged; --account --seat is the filtered projection."""
    assert wake.main(["--account", "--seat", "superego"]) == 0
    served = json.loads(capsys.readouterr().out)
    assert served["seat"] == "superego" and "rows" in served and "counts" in served
    assert served["counts"]["total"] == len(served["rows"])

    assert wake.main(["--account"]) == 0
    whole = json.loads(capsys.readouterr().out)
    assert "spec" in whole and "promises" in whole and "seat" not in whole


def test_relay_ready_carries_the_seats_beside_its_checks(capsys):
    """WO-20260823-seat-fabric-discovery: the relay check said what a successor keeps and
    never WHO it relays with. Discovery rides BESIDE the checks - never inside them, or an
    unfounded seat store would fail an otherwise green relay."""
    from laplace.engine import seats

    rc = wake.main(["--relay-ready"])
    served = json.loads(capsys.readouterr().out)
    assert rc == (0 if served["relay_ready"] else 1)
    assert served["seats"]["store"] == seats.STORE
    assert served["seats"]["current"] == seats.current_seats(ROOT)
    assert "seats" not in served["checks"], (
        "a seats block inside checks has no 'ok' key and would decide the relay verdict")


def test_campaign_riding_ordinal_is_a_render_derived_from_mint_order(tmp_path):
    """WO-20260823-campaign-r-numbers-are-renders: two stage rows were minted with 'R3'
    embedded in their ids. Ids are keys and stay verbatim; the served riding ordinal is
    DERIVED from mint order at query time, so the number a reader trusts comes from the
    render, never from digits inside an id."""
    store = tmp_path / "corpus_friction"
    store.mkdir(parents=True)
    rows = [
        {"record": "stage", "id": "CAMP-R9-late", "stage": "riding",
         "title": "late", "minted": "2026-08-23T22:00:00Z"},
        {"record": "stage", "id": "CAMP-R1-early", "stage": "riding",
         "title": "early", "minted": "2026-08-23T10:00:00Z"},
        {"record": "stage", "id": "CAMP-01-numbered", "stage": 1, "title": "numbered"},
    ]
    (store / "campaign.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    c = wake.campaign(tmp_path)
    served = {x["id"]: x.get("riding_ordinal") for x in c["stages"]}
    assert served["CAMP-R1-early"] == "R1"      # mint order, not id digits
    assert served["CAMP-R9-late"] == "R2"       # the id says R9; the render says R2
    assert served["CAMP-01-numbered"] is None   # numbered stages carry no riding ordinal


def test_atlas_campaign_supersedes_old_campaign_and_untyped_rows_stay_loud(tmp_path):
    """The rebuild campaign must not disappear because a mint omitted ``record=stage``.

    A corrected append-only row makes the stage live; the explicit absorption row keeps the
    old campaign visible as inheritance without letting it remain the engine's next act.
    """
    store = tmp_path / "corpus_friction"
    store.mkdir(parents=True)
    rows = [
        {"record": "stage", "id": "CAMP-01-old", "stage": 1, "title": "old"},
        {"id": "ATLAS-S0", "stage": 0, "title": "untyped historical mint"},
        {"record": "stage", "id": "ATLAS-S0", "stage": 0, "title": "inventory",
         "gate": {"cmd": "false", "expect": "walked and judged"}},
        {"record": "stage", "id": "ATLAS-ABSORB-OLD-CAMPAIGN", "stage": "riding",
         "title": "old campaign absorbed", "gate": {"cmd": "true"}},
    ]
    (store / "campaign.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    c = wake.campaign(tmp_path)
    served = {x["id"]: x for x in c["stages"]}
    assert c["next_act"] == "ATLAS-S0"
    assert served["CAMP-01-old"]["status"] == "ABSORBED"
    assert c["schema_residuals"] == []


def test_unrepaired_untyped_campaign_stage_is_a_schema_residual(tmp_path):
    store = tmp_path / "corpus_friction"
    store.mkdir(parents=True)
    (store / "campaign.jsonl").write_text(
        json.dumps({"id": "ATLAS-S0", "stage": 0, "title": "missing discriminator"})
        + "\n", encoding="utf-8")

    c = wake.campaign(tmp_path)
    assert c["schema_residuals"] == [
        {"code": "stage-row-missing-record", "id": "ATLAS-S0"}]


def test_store_map_examples_live_in_their_named_stores():
    """WO-20260823-store-map-class-router: the served store-map's every example is REAL -
    each names a string present in its own store's bytes, so the map cannot drift
    silently (a renamed store or retired id turns this red, and the row amends with it)."""
    root = Path(__file__).resolve().parents[1]
    for entry in wake.STORE_MAP:
        store = root / entry["store"]
        assert store.is_file(), f"store-map names a missing store: {entry['store']}"
        assert entry["example"] in store.read_text(encoding="utf-8"), (
            f"store-map example {entry['example']!r} not found in {entry['store']} - "
            "amend the map's row and this example together")


def test_account_serves_the_store_map():
    a = wake.account(Path(__file__).resolve().parents[1])
    assert a["store_map"] is wake.STORE_MAP
    assert {e["store"] for e in a["store_map"]} >= {
        "proxy_verdicts.jsonl", "contract/promises.jsonl",
        "corpus_friction/work_orders.jsonl", "corpus_friction/methods.jsonl"}


def test_account_counts_every_open_class_in_the_obligation_store():
    """A FIND (or any sibling class) cannot disappear behind the work-order view."""
    root = Path(__file__).resolve().parents[1]
    a = wake.account(root)
    classes = a["obligation_classes"]

    assert a["findings"] is classes["finding"]
    assert a["findings"]["open"] > 0
    assert a["obligations_open"] == sum(part["open"] for part in classes.values())
    assert {"work_order", "finding", "amendment", "note", "resolution", "gap", "intent"} <= set(classes)
    assert a["obligations_open"] > a["work_orders"]["open"]


def _campaign_store(tmp_path, rows):
    store = tmp_path / "corpus_friction"
    store.mkdir(parents=True, exist_ok=True)
    (store / "campaign.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (tmp_path / "contract").mkdir(parents=True, exist_ok=True)  # the journal seam's home
    return store / "campaign.jsonl"


def _gate_verdicts(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line).get("record") == "gate-verdict"]


def test_gate_verdicts_bank_only_on_change(tmp_path):
    """WO-20260825-gate-verdicts-bank-only-on-change: --campaign banked a gate-verdict row
    per stage per RUN, so campaign.jsonl grew 759 rows - 28 byte-identical blanks for
    ATLAS-S1 alone - measuring how often the verb fired, never what moved. A verdict banks
    iff it differs from the last banked verdict for its stage."""
    (tmp_path / "flip.txt").write_text("one\n", encoding="utf-8")
    store = _campaign_store(tmp_path, [
        {"record": "stage", "id": "T-STABLE", "stage": 1, "title": "never changes",
         "gate": {"cmd": "true", "expect": "exit 0"}},
        {"record": "stage", "id": "T-FLIP", "stage": 2, "title": "output moves",
         "depends_on": ["T-STABLE"], "gate": {"cmd": "cat flip.txt", "expect": "exit 0"}},
    ])

    wake.campaign(tmp_path, run_gates=True)          # first-ever verdict always banks
    first = _gate_verdicts(store)
    assert sorted(v["stage"] for v in first) == ["T-FLIP", "T-STABLE"]
    assert set(first[0]) == {"record", "stage", "exit", "status", "output_head", "ts"}, (
        "the row shape is byte-compatible with every existing reader")

    wake.campaign(tmp_path, run_gates=True)          # nothing moved -> nothing banks
    wake.campaign(tmp_path, run_gates=True)
    assert len(_gate_verdicts(store)) == 2, "an unchanged re-run must bank ZERO rows"

    (tmp_path / "flip.txt").write_text("two\n", encoding="utf-8")
    c = wake.campaign(tmp_path, run_gates=True)      # output_head moved -> exactly one row
    after = _gate_verdicts(store)
    assert len(after) == 3
    assert after[-1]["stage"] == "T-FLIP" and after[-1]["output_head"] == "two\n"
    assert "not re-banked" in next(x["ground"] for x in c["stages"]
                                   if x["id"] == "T-STABLE")


def test_next_act_serves_progress_refs_and_one_liners_never_bodies(tmp_path):
    """WO-20260825-next-act-has-no-progress-vocabulary: a stage is binary at its gate, so
    ATLAS-S1 read OPEN for a day while a full clause verdict and a measured amendment sat
    banked in work_orders.jsonl, invisible to every wake. The next act - and only the next
    act - now carries refs + one-liners for the newest verdict and the amendment aimed at
    it. Descent-by-need: heads only, the bodies stay in the store."""
    body = "CLAUSE-7 refusal on the hived-storage candidate for ATLAS-S1. " + "x" * 400
    wo = tmp_path / "corpus_friction"
    wo.mkdir(parents=True, exist_ok=True)
    (wo / "work_orders.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"record": "work-order", "id": "WO-early", "what": "open ATLAS-S1",
         "ts": "2026-08-25T07:00:00Z"},
        {"record": "verdict", "id": "VERDICT-stale", "verdict": "ACCEPT",
         "what": "an older ATLAS-S1 verdict", "ts": "2026-08-25T08:00:00Z"},
        {"record": "verdict", "id": "VERDICT-live", "verdict": "REFUSE-PENDING-AMENDMENT",
         "what": body, "ts": "2026-08-25T09:00:00Z"},
        # targets the VERDICT and never names the stage - it must still surface
        {"record": "amendment", "id": "AMEND-live", "target": "VERDICT-live",
         "what": "clause 3 measured and gated", "ts": "2026-08-25T09:15:00Z"},
        # exact-token matching: neither of these is a reference to ATLAS-S1
        {"record": "verdict", "id": "VERDICT-decoy-s10", "verdict": "ACCEPT",
         "what": "ATLAS-S10 is a different stage", "ts": "2026-08-25T10:00:00Z"},
        {"record": "verdict", "id": "VERDICT-decoy-bare", "verdict": "ACCEPT",
         "what": "s1 mentioned loosely", "ts": "2026-08-25T11:00:00Z"},
    ]) + "\n", encoding="utf-8")
    _campaign_store(tmp_path, [
        {"record": "stage", "id": "ATLAS-S1", "stage": 1, "title": "the substrate",
         "gate": {"cmd": "false", "expect": "walked and judged"}},
    ])

    c = wake.campaign(tmp_path)
    assert c["next_act"] == "ATLAS-S1"
    p = c["progress"]
    assert p["stage"] == "ATLAS-S1"
    assert p["latest_verdict"]["id"] == "VERDICT-live"          # newest, not the stale one
    assert p["latest_verdict"]["verdict"] == "REFUSE-PENDING-AMENDMENT"
    assert p["latest_amendment"]["id"] == "AMEND-live"
    assert len(p["latest_verdict"]["one_line"]) == 200 and body not in json.dumps(p), (
        "one-liners only - a served body would flatten the store into the wake")
    assert "VERDICT-decoy-s10" not in p["refs"] and "VERDICT-decoy-bare" not in p["refs"]
    assert {"WO-early", "VERDICT-stale", "VERDICT-live", "AMEND-live"} <= set(p["refs"])


def test_next_act_with_no_referencing_rows_serves_a_loud_null_progress(tmp_path):
    """Loud absence is the honest answer; invention is not."""
    (tmp_path / "corpus_friction").mkdir(parents=True, exist_ok=True)
    (tmp_path / "corpus_friction" / "work_orders.jsonl").write_text(
        json.dumps({"record": "note", "id": "NOTE-unrelated", "what": "nothing to do with it"})
        + "\n", encoding="utf-8")
    _campaign_store(tmp_path, [
        {"record": "stage", "id": "ATLAS-S1", "stage": 1, "title": "the substrate",
         "gate": {"cmd": "false", "expect": "walked and judged"}},
    ])
    c = wake.campaign(tmp_path)
    assert c["next_act"] == "ATLAS-S1" and c["progress"] is None


# --- THE WAKE FIX ROUND (2026-08-25): six named defects, two independent audits -------
# Every test below is a regression, not a demo. Each was falsified before it was trusted:
# six shadow copies of wake.py, each reverting EXACTLY ONE fix by exact-string surgery, run
# with `pytest -o "pythonpath=<shadow> src"` (the ini pythonpath beats $PYTHONPATH, so
# the shadow only wins by overriding the ini itself). Every test failed on its own shadow,
# for its own defect: 'OPEN' == 'TIMEOUT', KeyError 'defects', KeyError 'freshness',
# 'V-prose' == 'V-edge', an unswallowed RuntimeError, 'V-older' == 'RUL-...'.


def _work_orders(tmp_path, rows_or_text):
    wo = tmp_path / "corpus_friction"
    wo.mkdir(parents=True, exist_ok=True)
    p = wo / "work_orders.jsonl"
    p.write_text(rows_or_text if isinstance(rows_or_text, str)
                 else "\n".join(json.dumps(r) for r in rows_or_text) + "\n",
                 encoding="utf-8")
    return p


def _one_stage(tmp_path, cmd="false", sid="ATLAS-S1"):
    return _campaign_store(tmp_path, [
        {"record": "stage", "id": sid, "stage": 1, "title": "the substrate",
         "gate": {"cmd": cmd, "expect": "walked and judged"}},
    ])


def test_a_gate_timeout_banks_its_own_verdict_and_never_leaves_a_stale_green(tmp_path):
    """THE STALE-GREEN (interface-seat cross-audit). A TimeoutExpired set the CURRENT call
    to OPEN and banked NOTHING, so the next read-only wake reread the PRIOR banked verdict
    - DONE - and served a green stage whose latest execution had timed out. A timeout is a
    terminal MEASURED outcome and rides the same compare-and-bank seam as any exit code."""
    store = _one_stage(tmp_path, cmd="true", sid="T-TIME")
    assert wake.campaign(tmp_path, run_gates=True)["stages"][0]["status"] == "DONE"

    # last-wins on the stage id: the same stage, now with a gate that will not finish
    with store.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"record": "stage", "id": "T-TIME", "stage": 1,
                             "title": "the substrate",
                             "gate": {"cmd": "sleep 5", "expect": "walked and judged"}}) + "\n")

    c = wake.campaign(tmp_path, run_gates=True, gate_timeout=1)
    assert c["stages"][0]["status"] == "TIMEOUT", "a timeout is its own status, not OPEN"
    v = _gate_verdicts(store)
    assert len(v) == 2, "the timeout BANKED - a measured outcome always participates"
    assert v[-1]["status"] == "TIMEOUT" and v[-1]["exit"] is None
    assert "TIMEOUT" in v[-1]["output_head"], "its own output signature, never a blank"

    # THE REGRESSION the audit named: read-only, no gates run, prior DONE still on disk
    ro = wake.campaign(tmp_path)
    assert ro["stages"][0]["status"] == "TIMEOUT", (
        "a read-only wake must NEVER present the prior DONE as current after a timeout")
    assert "DONE" not in ro["stages"][0]["status"]
    assert ro["next_act"] == "T-TIME", "a timed-out stage is still the act in front of us"


def test_an_unparseable_work_orders_row_is_a_loud_residual_never_a_silent_skip(tmp_path):
    """A `continue` on JSONDecodeError could drop the very ruling that moves the stage, and
    the half-parsed store then read exactly like a clean one."""
    _work_orders(tmp_path, "\n".join([
        json.dumps({"record": "verdict", "id": "V-ok", "verdict": "ACCEPT",
                    "what": "ATLAS-S1 substrate", "ts": "2026-08-25T08:00:00Z"}),
        '{"record": "ruling", "id": "RUL-truncated", "what": "ATLAS-S1',   # line 2
        json.dumps({"record": "note", "id": "N-ok", "what": "ATLAS-S1 walked",
                    "ts": "2026-08-25T09:00:00Z"}),
        "not json at all",                                                  # line 4
    ]) + "\n")
    _one_stage(tmp_path)

    p = wake.campaign(tmp_path)["progress"]
    d = p["defects"]
    assert len(d) == 1 and d[0]["code"] == "work-orders-unparseable-rows"
    assert d[0]["count"] == 2 and d[0]["lines"] == [2, 4], "1-indexed line numbers, named"
    assert d[0]["store"] == "corpus_friction/work_orders.jsonl"

    # and a store that ONLY fails to parse must never come back as a clean silent None
    _work_orders(tmp_path, "{oops\n")
    p2 = wake.campaign(tmp_path)["progress"]
    assert p2 is not None and p2["defects"][0]["count"] == 1
    assert p2["latest_verdict"] is None, "loud absence, never invention"

    # a clean store with nothing referring stays honestly None (the pre-existing law)
    _work_orders(tmp_path, [{"record": "note", "id": "N-unrelated", "what": "elsewhere"}])
    assert wake.campaign(tmp_path)["progress"] is None
    assert wake.campaign(tmp_path)["stages"][0]["status"] in ("UNRUN", "OPEN")


def test_unchanged_and_correct_is_not_stale_and_gets_re_verified(tmp_path):
    """THE FRESHNESS FALSE-RED. The campaign source's chip is st_mtime against a 24h
    budget, and the delta-bank cure deliberately stops touching the store when nothing
    moves - so a campaign that is green and STABLE went RED for being correct. Freshness
    is a property of the last MEASUREMENT: unchanged-and-re-verified is not stale, and
    only a gate nobody has run inside the budget is AGING."""
    from datetime import datetime, timedelta, timezone

    store = _one_stage(tmp_path, cmd="true", sid="T-STABLE")
    wake.campaign(tmp_path, run_gates=True)
    wake.campaign(tmp_path, run_gates=True)      # inside the budget, nothing moved
    assert len(_gate_verdicts(store)) == 1, "the delta-bank cure survives: no churn"
    assert wake.campaign(tmp_path)["stages"][0]["freshness"]["state"] == "MEASURED"

    # age the banked verdict past the budget without changing a thing about the world
    old = (datetime.now(timezone.utc) - timedelta(days=3)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    lines = []
    for line in store.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r.get("record") == "gate-verdict":
            r["ts"] = old
        lines.append(json.dumps(r))
    store.write_text("\n".join(lines) + "\n", encoding="utf-8")

    aging = wake.campaign(tmp_path)["stages"][0]
    assert aging["freshness"]["state"] == "AGING", "unmeasured for 3 days IS stale"
    assert aging["freshness"]["age_s"] > 24 * 3600

    wake.campaign(tmp_path, run_gates=True)      # re-measured: identical, re-stamped
    rows = _gate_verdicts(store)
    assert len(rows) == 2 and rows[-1]["reverified"] is True
    assert rows[-1]["exit"] == rows[0]["exit"], "the verdict itself did not change"
    assert rows[-1]["output_head"] == rows[0]["output_head"]

    after = wake.campaign(tmp_path)["stages"][0]
    assert after["freshness"]["state"] == "UNCHANGED-VERIFIED"
    assert "NOT stale" in after["ground"], "the served words carry the distinction"
    assert after["status"] == "DONE"


def test_the_typed_edge_never_loses_to_the_prose(tmp_path):
    """journal.bank_row banks `edges` as the first-class typed lineage field, and the
    match blob ignored it (and `text`) - so a row whose only link to the stage was the
    strongest, most machine-checkable one there is was invisible."""
    _work_orders(tmp_path, [
        {"record": "verdict", "id": "V-prose", "verdict": "ACCEPT",
         "what": "ATLAS-S1 named in a sentence", "ts": "2026-08-25T08:00:00Z"},
        # names the stage NOWHERE in prose: the typed edge is the whole binding
        {"record": "verdict", "id": "V-edge", "verdict": "REFUSE",
         "what": "the hived-storage candidate", "ts": "2026-08-25T09:00:00Z",
         "edges": [{"rel": "grades", "target": "ATLAS-S1"}]},
        # and `text` is a real body field on these rows (sources.py columns), not prose slack
        {"record": "note", "id": "N-text", "text": "ATLAS-S1 walked at the board",
         "ts": "2026-08-25T09:30:00Z"},
    ])
    _one_stage(tmp_path)

    p = wake.campaign(tmp_path)["progress"]
    assert p["latest_verdict"]["id"] == "V-edge", "the typed edge binds the stage"
    assert "N-text" in p["refs"], "a text-only body is a reference too"
    assert "V-prose" in p["refs"]


def test_a_broken_campaign_degrades_loudly_instead_of_killing_the_doorway(monkeypatch, capsys):
    """_inflight and _acct were each guarded to a loud {"absent": ...}; campaign() alone
    was not - and it now reads a SECOND store (work_orders.jsonl) inside the wake, so its
    blast radius widened. A wake that cannot serve the campaign still serves everything
    else; the doorway never dies of one panel."""
    def _boom(*a, **k):
        raise RuntimeError("store went sideways")
    monkeypatch.setattr(wake, "campaign", _boom)

    assert wake.main(["--grade", "0"]) == 0
    payload = json.loads(capsys.readouterr().out)
    rows = payload["verdict_layer"]["campaign_rows"]
    assert "campaign failed: RuntimeError: store went sideways" == rows["absent"]
    assert payload["verdict_layer"]["account"], "the rest of the verdict layer survives"
    assert payload["fixed_point"]["wake_mode"] == "person"


def test_a_ruling_is_verdict_class_and_moves_the_stage(tmp_path):
    """RUL-* rows ARE decisions - they move stages exactly as verdicts do - and the
    predicate `"verdict" in record` silently excluded the entire ruling class."""
    _work_orders(tmp_path, [
        {"record": "verdict", "id": "V-older", "verdict": "ACCEPT",
         "what": "an older ATLAS-S1 verdict", "ts": "2026-08-25T08:00:00Z"},
        {"record": "ruling", "id": "RUL-20260825-substrate", "ruling": "REFUSE-AS-SCOPED",
         "text": "ATLAS-S1 ships hived or not at all", "ts": "2026-08-25T09:00:00Z"},
        {"record": "amendment", "id": "AMEND-after-the-ruling",
         "target": "RUL-20260825-substrate", "what": "scope cut to the hive",
         "ts": "2026-08-25T09:30:00Z"},
    ])
    _one_stage(tmp_path)

    p = wake.campaign(tmp_path)["progress"]
    assert p["latest_verdict"]["id"] == "RUL-20260825-substrate"
    assert p["latest_verdict"]["record"] == "ruling"
    assert p["latest_verdict"]["verdict"] == "REFUSE-AS-SCOPED"
    assert "hived or not at all" in p["latest_verdict"]["one_line"], (
        "a ruling's body lives in `text`; the one-liner must find it")
    assert p["latest_amendment"]["id"] == "AMEND-after-the-ruling", (
        "the amendment aimed at the RULING surfaces, exactly as for a verdict")


# --- the wake stops collapsing bench states -------------------------------
# SYNTH-20260825-the-unknown-collapses, class 4 (UNJUDGED collapses into FAILED).
# The grade-0 payload served verifier_and_census.stranger_bench as {"green": 1,
# "red": 7} straight off the runner's rollup row, whose red is len(probes) - greens.
# Measured on the live store the same day: 11 of 33 checks were AWAITING-JUDGE and
# 7 of 8 probes carried at least one, so most of that "red" was UNJUDGED, not failed
# - and the judge read the collapsed field twice and twice concluded validation was
# lagging construction. These three tests hold the cure: every state counted BY NAME,
# nothing inferred by subtraction, absence never rendered as a verdict.

def _bench_store(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "STRANGER_BENCH_VERDICTS.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def test_bench_states_counts_each_state_by_name(tmp_path):
    """(i) A known mix of PASS / FAIL / AWAITING-JUDGE / null yields exactly the
    per-state counts - and the awaiting-judge probes are NOT rendered as failures."""
    store = _bench_store(tmp_path, [
        # an older run whose rows must not leak into the latest run's counts
        {"record": "check", "run": "old", "probe": "P-A", "check": "a1", "status": "FAIL"},
        {"record": "run", "run": "old", "ts": "2026-08-24T00:00:00Z", "green": 0, "red": 4},
        {"record": "check", "run": "now", "probe": "P-A", "check": "a1", "status": "PASS"},
        {"record": "check", "run": "now", "probe": "P-A", "check": "a2", "status": "PASS"},
        {"record": "check", "run": "now", "probe": "P-B", "check": "b1", "status": "PASS"},
        {"record": "check", "run": "now", "probe": "P-B", "check": "b2", "status": "FAIL"},
        {"record": "check", "run": "now", "probe": "P-C", "check": "c1", "status": "PASS"},
        {"record": "check", "run": "now", "probe": "P-C", "check": "c2",
         "status": "AWAITING-JUDGE"},
        {"record": "check", "run": "now", "probe": "P-D", "check": "d1", "status": None},
        {"record": "check", "run": "now", "probe": "P-D", "check": "d2", "status": None},
        # the runner's own rollup rows: probe rows carry no status at all
        {"record": "probe", "run": "now", "probe": "P-A", "verdict": "GREEN"},
        {"record": "run", "run": "now", "ts": "2026-08-25T00:00:00Z", "green": 1, "red": 3},
    ])

    b = wake.bench_states(store)

    assert b["run"] == "now", "the LATEST run row selects the run being counted"
    assert b["checks"] == {"total": 8, "pass": 4, "fail": 1, "awaiting_judge": 1,
                           "not_recorded": 2, "unrecognised": {}, "sums_to_total": True}
    assert b["probes"]["green"] == 1
    assert b["probes"]["red"] == 1, "only P-B actually FAILed a check"
    assert b["probes"]["awaiting_judge"] == 1, (
        "P-C is UNJUDGED, not failed - this is the whole defect")
    assert b["probes"]["not_recorded"] == 1
    assert b["probes"]["states"] == {"P-A": "green", "P-B": "red",
                                     "P-C": "awaiting_judge", "P-D": "not_recorded"}
    # the single scalar a consumer may have is named honestly and SUMMED from the
    # named components - never "everything that is not green"
    assert b["unresolved"] == 3
    assert "red" not in b, (
        "a top-level `red` beside `green` is read as the complement of green; the "
        "components must be read instead")
    # the runner's collapsed row survives only as provenance, plainly labelled
    assert b["banked_run_row"]["red"] == 3
    assert "subtraction" in b["banked_run_row"]["note"]


def test_an_unrecognised_bench_status_is_never_absorbed_into_a_known_state(tmp_path):
    """(ii) THE ANTI-SUBTRACTION TEST. A status string the code has never seen lands
    in its own named bucket. Deriving any state as total-minus-the-others would post
    that row into whichever bucket the arithmetic balances - re-creating the exact
    collapse one level down. This fixture is built so the subtraction is provably
    wrong: it would report 2 awaiting-judge where only 1 was ever banked."""
    store = _bench_store(tmp_path, [
        {"record": "check", "run": "now", "probe": "P-A", "check": "a1", "status": "PASS"},
        {"record": "check", "run": "now", "probe": "P-B", "check": "b1", "status": "FAIL"},
        {"record": "check", "run": "now", "probe": "P-C", "check": "c1",
         "status": "AWAITING-JUDGE"},
        {"record": "check", "run": "now", "probe": "P-D", "check": "d1", "status": None},
        {"record": "check", "run": "now", "probe": "P-E", "check": "e1",
         "status": "SKIPPED-NO-FIXTURE"},
        {"record": "run", "run": "now", "ts": "2026-08-25T00:00:00Z", "green": 1, "red": 4},
    ])

    b = wake.bench_states(store)

    assert b["checks"]["unrecognised"] == {"SKIPPED-NO-FIXTURE": 1}, (
        "an unknown status is served under its own name")
    assert b["checks"]["pass"] == 1
    assert b["checks"]["fail"] == 1
    assert b["checks"]["awaiting_judge"] == 1
    assert b["checks"]["not_recorded"] == 1
    assert b["checks"]["total"] == 5
    # the subtraction the cure forbids, spelled out: it lands the unknown row in
    # awaiting_judge and reports 2 where the store banked 1.
    by_subtraction = (b["checks"]["total"] - b["checks"]["pass"] - b["checks"]["fail"]
                      - b["checks"]["not_recorded"])
    assert by_subtraction == 2 and b["checks"]["awaiting_judge"] == 1, (
        "the fixture must make the subtraction visibly wrong, or it proves nothing")
    assert b["checks"]["sums_to_total"] is True, (
        "total is the rows READ and the named buckets must sum to it - the check is "
        "an assertion, never the way a bucket gets its value")
    assert b["probes"]["states"]["P-E"] == "unrecognised", (
        "the probe carrying it is unrecognised - not red, not green, not awaiting")
    assert b["probes"]["unrecognised"] == 1
    assert b["probes"]["red"] == 1, "P-E must not be swept in with the genuine failure"
    assert b["unresolved"] == 4


def test_a_probe_with_no_status_ever_recorded_is_not_recorded_never_red(tmp_path):
    """(iii) NOT-RECORDED IS ABSENCE, NOT A VERDICT. FIND-20260825-probe-rollups-
    record-no-status: 24 of 41 check ids in the live store have never recorded a
    status, constant None across 21 runs. A probe whose every row is null has not
    passed, has not failed, and is not awaiting a judge - it was never measured."""
    store = _bench_store(tmp_path, [
        {"record": "check", "run": "now", "probe": "P-NEVER", "check": "n1", "status": None},
        {"record": "check", "run": "now", "probe": "P-NEVER", "check": "n2"},
        {"record": "check", "run": "now", "probe": "P-OK", "check": "o1", "status": "PASS"},
        {"record": "run", "run": "now", "ts": "2026-08-25T00:00:00Z", "green": 1, "red": 1},
    ])

    b = wake.bench_states(store)

    assert b["probes"]["states"]["P-NEVER"] == "not_recorded"
    assert b["probes"]["red"] == 0, "never-measured is not failed"
    assert b["probes"]["green"] == 1, "and it is not green either"
    assert b["probes"]["not_recorded"] == 1
    assert b["checks"]["not_recorded"] == 2, (
        "an absent `status` key counts the same as an explicit null - both are absence")
    assert b["checks"]["fail"] == 0 and b["checks"]["awaiting_judge"] == 0


def test_the_judges_own_grading_rides_as_its_own_axis_never_merged(tmp_path):
    """A self-run cannot resolve an AWAITING-JUDGE check by construction, so a block
    that shows only self-run counts still reads as `nothing was ever graded`. The
    judge's banked verdicts ride as a SEPARATE axis, stamped with their own run - and
    they must not move a single one of the self-run counts."""
    store = _bench_store(tmp_path, [
        {"record": "check", "run": "now", "probe": "P-C", "check": "c1",
         "status": "AWAITING-JUDGE"},
        {"record": "judge-verdict", "run": "grading-2026-08-23", "probe": "P-C",
         "verdict": "GREEN", "ts": "2026-08-23T12:36:03Z"},
        {"record": "run", "run": "now", "ts": "2026-08-25T00:00:00Z", "green": 0, "red": 1},
    ])

    b = wake.bench_states(store)

    assert b["judge"]["verdicts"] == {"P-C": "GREEN"}
    assert b["judge"]["runs"] == ["grading-2026-08-23"], (
        "the judge's act is stamped with ITS run, not the run being counted")
    assert b["probes"]["states"]["P-C"] == "awaiting_judge", (
        "the self-run's own state is untouched - the wake reports, it does not re-grade")
    assert b["probes"]["green"] == 0
    assert b["checks"]["total"] == 1, "a judge-verdict row is not a check row"


def test_a_store_with_no_judge_row_says_so_rather_than_omitting_the_key(tmp_path):
    """Absence again: an empty judge axis is stated, not left out. A missing key reads
    as `not applicable`; `probes_graded: 0` reads as `nobody has graded this`."""
    store = _bench_store(tmp_path, [
        {"record": "check", "run": "now", "probe": "P-A", "check": "a1", "status": "PASS"},
        {"record": "run", "run": "now", "ts": "2026-08-25T00:00:00Z", "green": 1, "red": 0},
    ])
    b = wake.bench_states(store)
    assert b["judge"]["probes_graded"] == 0
    assert "no judge-verdict row has ever been banked" == b["judge"]["note"]


def test_typed_source_rollup_is_preserved_without_reintroducing_red(tmp_path):
    store = _bench_store(tmp_path, [
        {"record": "check", "run": "now", "probe": "P-A", "check": "a1",
         "status": "PASS"},
        {"record": "check", "run": "now", "probe": "P-B", "check": "b1",
         "status": "AWAITING-JUDGE"},
        {"record": "run", "run": "now", "ts": "2026-08-25T00:00:00Z",
         "green": 1, "fail": 0, "awaiting_judge": 1, "not_recorded": 0,
         "unrecognised": 0, "unresolved": 1, "total": 2, "sums_to_total": True},
    ])
    b = wake.bench_states(store)
    assert b["banked_run_row"]["awaiting_judge"] == 1
    assert b["banked_run_row"]["unresolved"] == 1
    assert "red" not in b["banked_run_row"]
    assert "counted by name" in b["banked_run_row"]["note"]


# --- the census stops collapsing across runs -------------------------------
# SYNTH-20260825-the-unknown-collapses, class 1 (ABSENCE collapses into PRESENT).
# The census half of the same defect `bench_states` was cured of. The fold was
# last-value-wins across EVERY run in the store, stamped with the newest row's
# timestamp - so on the live store `the-judges-plant-b`, last observed DEAD on
# 2026-08-23, was served as a dead organ of the 2026-08-25 run that never touched
# it, and "11 organs" was the count of organs EVER recorded, not that run's size.
# Class 1 is the most expensive collapse because the manufactured value cannot be
# told from a measured one afterwards. These tests hold the cure: the observation
# is scoped, and an organ outside it is UNOBSERVED - never functional, never dead.

def _census_store(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "census_verdicts.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def test_an_organ_absent_from_the_latest_observation_is_never_called_dead(tmp_path):
    """THE DEFECT, planted: a DEAD verdict from an older run must not be served as a
    dead organ of a run that never observed it."""
    store = _census_store(tmp_path, [
        # two days earlier: an organ that has never been seen since
        {"record": "census-verdict", "organ": "the-plant", "verdict": "DEAD",
         "ts": "2026-08-23T12:12:29Z"},
        {"record": "census-verdict", "organ": "account", "verdict": "FUNCTIONAL",
         "ts": "2026-08-23T12:12:30Z"},
        # the latest observation: the plant is not in it
        {"record": "census-verdict", "organ": "account", "verdict": "FUNCTIONAL",
         "ts": "2026-08-25T00:29:12.567Z"},
        {"record": "census-verdict", "organ": "journal", "verdict": "FUNCTIONAL",
         "ts": "2026-08-25T00:29:12.652Z"},
    ])

    c = wake.census_states(store)

    assert c["dead"] == [], "the-plant was not observed; it cannot be this run's dead"
    assert c["organs"] == 2, "the latest observation touched two organs, not three"
    assert c["organs_ever"] == 3, "provenance is kept - beside the count, never inside it"
    assert c["ran"] == "2026-08-25T00:29:12.652Z"
    assert set(c["observed"]) == {"account", "journal"}
    assert c["unobserved"]["the-plant"]["last_verdict"] == "DEAD", (
        "the signal is preserved by NAME - the cure is not to hide the plant")
    assert c["unobserved"]["the-plant"]["age_hours"] == pytest.approx(36.3, abs=0.2)
    assert "account" not in c["unobserved"], "an organ in the window is observed"


def test_a_dead_organ_inside_the_latest_observation_is_still_dead(tmp_path):
    """The converse counterexample: scoping must not swallow a real failure."""
    store = _census_store(tmp_path, [
        {"record": "census-verdict", "organ": "account", "verdict": "FUNCTIONAL",
         "ts": "2026-08-25T00:29:12.567Z"},
        {"record": "census-verdict", "organ": "journal", "verdict": "DEAD",
         "ts": "2026-08-25T00:29:12.652Z"},
    ])
    c = wake.census_states(store)
    assert c["dead"] == ["journal"]
    assert c["verdicts"] == {"FUNCTIONAL": 1, "DEAD": 1}
    assert c["unobserved"] == {}


def test_the_observation_window_is_declared_on_the_block_it_scopes(tmp_path):
    """A scoped answer that does not state its scope is a new way to be wrong. The
    window is a CRUTCH (the store carries no run id) and says so where it is read."""
    store = _census_store(tmp_path, [
        {"record": "census-verdict", "organ": "account", "verdict": "FUNCTIONAL",
         "ts": "2026-08-25T00:29:12.567Z"},
    ])
    c = wake.census_states(store)
    obs = c["observation"]
    assert obs["window_seconds"] == 300.0
    assert obs["rows_in_window"] == 1 and obs["rows_total"] == 1
    assert obs["crutch"] == "CRUTCH-20260825-census-run-window"
    assert "UNOBSERVED" in obs["note"]


def test_an_undated_row_is_counted_by_name_and_never_swept_into_the_observation(tmp_path):
    """Absence of a timestamp is its own unknown. It must not be silently included
    (manufacturing an observation) nor silently dropped (manufacturing an absence)."""
    store = _census_store(tmp_path, [
        {"record": "census-verdict", "organ": "account", "verdict": "FUNCTIONAL",
         "ts": "2026-08-25T00:29:12.567Z"},
        {"record": "census-verdict", "organ": "ghost", "verdict": "DEAD", "ts": None},
    ])
    c = wake.census_states(store)
    assert c["organs"] == 1 and c["dead"] == []
    assert c["observation"]["undated_rows"] == 1
    assert c["observation"]["undated_organs"] == ["ghost"]
    assert c["unobserved"]["ghost"]["last_verdict"] == "DEAD"


def test_an_adjudication_rides_beside_the_run_and_is_never_merged_into_it(tmp_path):
    """The judge's override is a DIFFERENT act, exactly as judge-verdict rows are for
    the bench. Merging it would let a judge's word be read as a census measurement."""
    store = _census_store(tmp_path, [
        {"record": "census-verdict", "organ": "account", "verdict": "DEAD",
         "ts": "2026-08-25T00:29:12.567Z"},
        {"record": "adjudication", "organ": "account", "verdict": "FUNCTIONAL",
         "ts": "2026-08-25T00:30:00Z", "reason": "ran under the wrong interpreter"},
    ])
    c = wake.census_states(store)
    assert c["dead"] == ["account"], "the measurement stands on its own axis"
    assert c["adjudications"]["organs_adjudicated"] == 1
    assert c["adjudications"]["verdicts"]["account"] == "FUNCTIONAL"
    assert "NOT merged" in c["adjudications"]["note"]


def test_an_empty_census_store_states_the_absence_rather_than_reporting_zero_dead(tmp_path):
    store = _census_store(tmp_path, [])
    c = wake.census_states(store)
    assert c["organs"] == 0 and c["organs_ever"] == 0 and c["dead"] == []
    assert "no census-verdict row has ever been banked" in c["observation"]["note"]


def test_the_live_store_no_longer_calls_the_judge_fixture_a_dead_organ():
    """The defect as it actually stood on his surface, held against the real store."""
    c = wake.census_states(Path(__file__).resolve().parents[1]
                           / "corpus_friction" / "census_verdicts.jsonl")
    assert "the-judges-plant-b" not in c["dead"]
    assert c["unobserved"].get("the-judges-plant-b", {}).get("last_verdict") == "DEAD"
    assert c["organs"] <= c["organs_ever"]
