"""The fabric pull is a SERVE, not a dump (WO-20260824-fabric-pull-is-a-serve).

Four invariants, all over a synthetic pull envelope - never a real seat, never a real store:

1. GRADED: one bounded line per message (sender, type, cursor, expiry, body_handle, ~120
   chars of body). No verbatim body rides unless the caller descended into it.
2. NAMED DISPLACEMENT: when the budget truncates, the output carries the count AND the exact
   omitted ids, and says they are already PULLED - the banked cursor advance covered them.
3. DESCENT IS EXPLICIT: --message <id> / --full carry full bodies, and a named id is served
   even when the budget would have displaced it.
4. THE ENVELOPE SURVIVES: schema_version / receipt / seat_id / after_cursor / result_cursor /
   messages ride through unchanged, and pull still calls the bridge with the same cursor
   arguments - programmatic consumers and the durable cursor are both untouched.

Plus the drain-and-re-arm verb: it grades, it hands back the exact watcher arm, and it does
NOT acknowledge - reconstruction and ack stay judgment verbs owned by the seat.
"""

from __future__ import annotations

import importlib.util
import json
import types
from pathlib import Path

import pytest
from atlas.errors import StateTransitionRefused

ROOT = Path(__file__).resolve().parents[1]


def _load(stem: str):
    spec = importlib.util.spec_from_file_location(
        f"{stem}_under_test", ROOT / "scripts" / f"{stem}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sf = _load("seat_fabric")
fw = _load("fabric_watch")

LONG_BODY = (
    "the codex seat asks for the exact prefix boundary ruling and will not move "
    "until the ego seat answers with a banked row " * 6
)


def test_cli_resolves_unique_message_prefix_without_direct_sqlite(monkeypatch):
    monkeypatch.setattr(
        sf,
        "_provider_state",
        lambda: {
            "messages": {
                "message:abc123": {"message": {"cursor": 1}},
                "message:def456": {"message": {"cursor": 2}},
            }
        },
    )

    assert sf.resolve_message_id("abc") == "message:abc123"
    assert sf.resolve_message_id("message:def") == "message:def456"
    with pytest.raises(ValueError, match="does not resolve"):
        sf.resolve_message_id("missing")


def test_exact_message_id_bypasses_provider_projection_but_not_the_called_verb(monkeypatch):
    exact = "message:" + "a" * 64
    monkeypatch.setattr(
        sf,
        "_provider_state",
        lambda: pytest.fail("an exact canonical id must not replay the provider projection"),
    )
    assert sf.resolve_message_id(exact) == exact


def test_custody_batch_preserves_individual_effects_in_one_process(monkeypatch):
    ids = tuple("message:" + char * 64 for char in ("a", "b", "c"))
    statuses = {message_id: "pulled" for message_id in ids}
    calls = []

    def status(*, message_id):
        calls.append(("status", message_id))
        return {
            "message_id": message_id,
            "status": {
                "status": statuses[message_id],
                "delivered": statuses[message_id] == "delivered",
                "message": {"recipient_seat_id": "ego-seat"},
            },
        }

    def reconstruct(**kwargs):
        calls.append(("reconstruct", kwargs["message_id"], kwargs["seat_id"], kwargs["goal"]))
        return {
            "body_handle": "sha256:" + "d" * 64,
            "reconstruction_event_id": "sha256:" + kwargs["message_id"][-64:],
            "reconstruction_handle": "sha256:" + "e" * 64,
        }

    def acknowledge(**kwargs):
        calls.append((
            "acknowledge",
            kwargs["message_id"],
            kwargs["reconstruction_event_id"],
            kwargs["reconstruction_handle"],
        ))
        statuses[kwargs["message_id"]] = "delivered"
        return {"receipt": {"event_id": "sha256:" + "f" * 64}}

    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: types.SimpleNamespace(
            status=status,
            reconstruct=reconstruct,
            acknowledge=acknowledge,
        ),
    )
    monkeypatch.setattr(
        sf,
        "_prime_custody_stores",
        lambda bridge: {
            "store_constructions": 2,
            "replayed_rows": 6400,
            "replayed_rows_by_face": {"read_store": 3200, "store": 3200},
            "measurement": "deterministic plant",
        },
    )

    result = sf.custody_batch(
        seat_id="ego-seat",
        message_ids=ids,
        goal="reconstruct the exact commission",
        provider="codex",
        model="test",
    )

    assert result["batch_size"] == 3
    assert result["measurements"]["process_count"] == 1
    assert result["measurements"]["before"]["process_count"] == 12
    assert result["measurements"]["before"]["store_constructions"] == 18
    assert result["measurements"]["before"]["replayed_rows"] == 57_600
    assert result["measurements"]["after"]["process_count"] == 1
    assert result["measurements"]["after"]["store_constructions"] == 2
    assert result["measurements"]["after"]["replayed_rows"] == 6400
    assert result["measurements"]["store_constructions"] == 2
    assert result["measurements"]["replayed_rows"] == 6400
    assert [row["state"] for row in result["rows"]] == ["DELIVERED"] * 3
    assert result["phase_receipt"]["message_ids"] == list(ids)
    assert result["phase_receipt"]["handle"].startswith("sha256:")
    assert result["residual"]["crutch"] == "CR-C1-COLD-STORE-CONSTRUCTION"
    assert [call[0] for call in calls] == [
        "status", "status", "status",
        "reconstruct", "acknowledge", "status",
        "reconstruct", "acknowledge", "status",
        "reconstruct", "acknowledge", "status",
    ]


def test_custody_batch_refuses_noncanonical_or_duplicate_ids_before_bridge(monkeypatch):
    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: pytest.fail("invalid batch must refuse before store construction or effects"),
    )
    exact = "message:" + "a" * 64
    with pytest.raises(ValueError, match="canonical"):
        sf.custody_batch(
            seat_id="ego-seat",
            message_ids=("message:prefix",),
            goal="goal",
            provider="codex",
            model="test",
        )
    with pytest.raises(ValueError, match="duplicate"):
        sf.custody_batch(
            seat_id="ego-seat",
            message_ids=(exact, exact),
            goal="goal",
            provider="codex",
            model="test",
        )


def test_custody_batch_refuses_mixed_recipient_before_any_effect(monkeypatch):
    mine = "message:" + "a" * 64
    theirs = "message:" + "b" * 64
    effects = []

    def status(*, message_id):
        recipient = "ego-seat" if message_id == mine else "superego-seat"
        return {
            "message_id": message_id,
            "status": {
                "status": "pulled",
                "delivered": False,
                "message": {"recipient_seat_id": recipient},
            },
        }

    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: types.SimpleNamespace(
            status=status,
            reconstruct=lambda **kwargs: effects.append(("reconstruct", kwargs)),
            acknowledge=lambda **kwargs: effects.append(("acknowledge", kwargs)),
        ),
    )
    monkeypatch.setattr(
        sf,
        "_prime_custody_stores",
        lambda bridge: {
            "store_constructions": 2,
            "replayed_rows": 20,
            "replayed_rows_by_face": {"read_store": 10, "store": 10},
            "measurement": "deterministic plant",
        },
    )

    result = sf.custody_batch(
        seat_id="ego-seat",
        message_ids=(mine, theirs),
        goal="goal",
        provider="codex",
        model="test",
    )

    assert effects == []
    assert [row["state"] for row in result["rows"]] == ["REFUSED", "REFUSED"]
    assert "recipient" in result["rows"][1]["reason"]


def test_custody_batch_translates_missing_exact_id_before_any_effect(monkeypatch):
    known = "message:" + "a" * 64
    missing = "message:" + "b" * 64
    effects = []

    def status(*, message_id):
        if message_id == missing:
            raise AttributeError("NoneType has no attribute get")
        return {
            "message_id": message_id,
            "status": {
                "status": "pulled",
                "delivered": False,
                "message": {"recipient_seat_id": "ego-seat"},
            },
        }

    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: types.SimpleNamespace(
            status=status,
            reconstruct=lambda **kwargs: effects.append(("reconstruct", kwargs)),
            acknowledge=lambda **kwargs: effects.append(("acknowledge", kwargs)),
        ),
    )
    monkeypatch.setattr(
        sf,
        "_prime_custody_stores",
        lambda bridge: {
            "store_constructions": 2,
            "replayed_rows": 20,
            "replayed_rows_by_face": {"read_store": 10, "store": 10},
            "measurement": "deterministic plant",
        },
    )

    result = sf.custody_batch(
        seat_id="ego-seat",
        message_ids=(known, missing),
        goal="goal",
        provider="codex",
        model="test",
    )

    assert effects == []
    assert [row["state"] for row in result["rows"]] == ["REFUSED", "REFUSED"]
    assert "does not contain" in result["rows"][1]["reason"]


def test_cli_refuses_ambiguous_message_prefix(monkeypatch):
    monkeypatch.setattr(
        sf,
        "_provider_state",
        lambda: {
            "messages": {
                "message:abc123": {"message": {"cursor": 1}},
                "message:abc999": {"message": {"cursor": 2}},
            }
        },
    )

    with pytest.raises(ValueError, match="ambiguous"):
        sf.resolve_message_id("abc")


def test_cli_turns_transport_refusal_into_a_typed_json_envelope(monkeypatch, capsys):
    def refuse(_argv=None):
        raise StateTransitionRefused("seat message must cross a logical-seat boundary")

    monkeypatch.setattr(sf, "main", refuse)
    assert sf.cli(["send"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["refused"] is True
    assert result["residue"]["code"] == "STATE_TRANSITION_REFUSED"
    assert "logical-seat boundary" in result["residue"]["message"]


def test_consume_wake_cli_preserves_the_exact_scoped_token(monkeypatch, capsys):
    from laplace.representation import codex_seat_watcher

    calls = []
    monkeypatch.setattr(
        codex_seat_watcher,
        "consume_wake_token",
        lambda **kwargs: (
            calls.append(kwargs)
            or {
                "schema_version": codex_seat_watcher.CONSUMPTION_SCHEMA,
                "canonical_reconciled": True,
                "delivery_claim": "none",
            }
        ),
    )
    token = "wake:" + "b" * 64

    assert (
        sf.main(
            [
                "consume-wake",
                "--seat",
                "codex-seat",
                "--thread",
                "01-thread",
                "--token",
                token,
            ]
        )
        == 0
    )

    assert calls == [
        {
            "seat_id": "codex-seat",
            "thread_id": "01-thread",
            "token": token,
        }
    ]
    result = json.loads(capsys.readouterr().out)
    assert result["canonical_reconciled"] is True
    assert result["delivery_claim"] == "none"


def test_preserve_fork_cli_carries_every_pinned_field(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(sf, "resolve_message_id", lambda reference: f"message:{reference}")
    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: types.SimpleNamespace(
            preserve_message_fork=lambda **kwargs: (
                calls.append(kwargs)
                or {
                    "message_id": kwargs["message_id"],
                    "status": {"status": "quarantined", "delivered": False},
                }
            )
        ),
    )
    authority = "sha256:" + "a" * 64
    body = "sha256:" + "b" * 64

    assert (
        sf.main(
            [
                "preserve-fork",
                "--seat",
                "superego-seat",
                "--message",
                "target",
                "--sender",
                "claude-seat",
                "--recipient",
                "ego-seat",
                "--body-handle",
                body,
                "--ruling-ref",
                "gerard:three-seats-now",
                "--authority-event",
                authority,
                "--reason",
                "Claude is deferred",
                "--reopen-condition",
                "authenticated sender delivers a replacement",
            ]
        )
        == 0
    )

    assert calls == [
        {
            "seat_id": "superego-seat",
            "message_id": "message:target",
            "original_sender_seat_id": "claude-seat",
            "recipient_seat_id": "ego-seat",
            "body_handle": body,
            "author_ruling_ref": "gerard:three-seats-now",
            "authority_event_id": authority,
            "reason": "Claude is deferred",
            "reopen_condition": "authenticated sender delivers a replacement",
            "provider": sf.PROVIDER_DEFAULT,
            "model": sf.MODEL_DEFAULT,
        }
    ]
    assert json.loads(capsys.readouterr().out)["status"] == {
        "status": "quarantined",
        "delivered": False,
    }


def test_recover_legacy_bundle_cli_has_no_freehand_predecessors_or_note(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(sf, "resolve_message_id", lambda reference: f"message:{reference}")
    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: types.SimpleNamespace(
            recover_legacy_message_bundle=lambda **kwargs: (
                calls.append(kwargs)
                or {
                    "replacement_message_id": kwargs["replacement_message_id"],
                    "delivery_claimed": False,
                }
            )
        ),
    )
    authority = "sha256:" + "c" * 64

    assert (
        sf.main(
            [
                "recover-legacy-bundle",
                "--seat",
                "superego-seat",
                "--replacement",
                "replacement",
                "--authority-ack",
                authority,
            ]
        )
        == 0
    )

    assert calls == [
        {
            "actor_seat_id": "superego-seat",
            "replacement_message_id": "message:replacement",
            "authority_acknowledgement_event_id": authority,
            "provider": sf.PROVIDER_DEFAULT,
            "model": sf.MODEL_DEFAULT,
        }
    ]
    assert json.loads(capsys.readouterr().out)["delivery_claimed"] is False


def test_stage_zero_reissue_cli_has_no_freehand_coordinate(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: types.SimpleNamespace(
            reissue_stage_zero_migration_replacement=lambda **kwargs: (
                calls.append(kwargs)
                or {
                    "migration_act": "stage-zero-exact-reissue/1",
                    "message_id": "message:reviewed",
                }
            )
        ),
    )

    assert sf.main(["reissue-stage-zero-replacement"]) == 0
    assert calls == [{"provider": sf.PROVIDER_DEFAULT, "model": sf.MODEL_DEFAULT}]
    assert json.loads(capsys.readouterr().out) == {
        "migration_act": "stage-zero-exact-reissue/1",
        "message_id": "message:reviewed",
    }


def _message(cursor: int, *, body: str = LONG_BODY, mid: str | None = None) -> dict:
    return {
        "schema_version": "seat-message/1",
        "message_id": mid or f"message:{cursor:03d}",
        "sender_seat_id": "codex-seat",
        "recipient_seat_id": "claude-seat",
        "message_type": "audit",
        "body_handle": f"sha256:{cursor:064d}",
        "dependency_roots": {"head": "abc"},
        "idempotency_key": f"key-{cursor}",
        "cursor": cursor,
        "expires_at": "2099-01-01T00:00:00+00:00",
        "body": body,
        "media_type": "text/plain; charset=utf-8",
    }


def _envelope(n: int = 14) -> dict:
    return {
        "schema_version": "laplace.atlas-seat-bridge.v1",
        "receipt": {"event_id": "event:99", "head": "sha256:deadbeef"},
        "seat_id": "claude-seat",
        "after_cursor": 3,
        "result_cursor": 17,
        "messages": [_message(c) for c in range(4, 4 + n)],
    }


def _blocked_envelope() -> dict:
    return {
        "schema_version": "laplace.atlas-seat-bridge.v1",
        "receipt": None,
        "status": "BLOCKED-UNKNOWN-CONTENT",
        "seat_id": "ego-seat",
        "after_cursor": 906,
        "result_cursor": 906,
        "cursor_advanced": False,
        "messages": [],
        "pending_count": 3,
        "readable_message_ids": ["message:good"],
        "unknown_content": [
            {
                "message_id": "message:poison",
                "cursor": 930,
                "body_handle": "sha256:" + "0" * 64,
                "status": "UNKNOWN",
                "reason": "store-blob-missing",
            }
        ],
        "delivery_claim": "none; no pull event was banked",
    }


class _Args:
    """The parsed-argv shape cmd_pull/cmd_drain consume."""

    def __init__(self, **kw):
        self.seat = "claude-seat"
        self.provider = "cli"
        self.model = "seat-fabric-cli"
        self.budget = sf.DEFAULT_PULL_BUDGET
        self.preview_chars = sf.DEFAULT_PREVIEW_CHARS
        self.message = []
        self.full = False
        self.lines = False
        self.__dict__.update(kw)


@pytest.fixture()
def fake_bridge(monkeypatch):
    """A bridge whose pull returns the flood envelope and records how it was called."""
    calls: dict[str, list] = {"pull": [], "acknowledge": [], "reconstruct": []}

    def pull(**kw):
        calls["pull"].append(kw)
        return _envelope()

    def acknowledge(**kw):  # pragma: no cover - a drain that lands here is the bug
        calls["acknowledge"].append(kw)
        raise AssertionError("drain must never acknowledge")

    bridge = types.SimpleNamespace(pull=pull, acknowledge=acknowledge)
    monkeypatch.setattr(sf, "_bridge", lambda: bridge)
    return calls


# --- 1. graded ------------------------------------------------------------------


def test_the_pull_grades_instead_of_flooding():
    graded = sf.grade_pull(_envelope(14))

    assert graded["pulled_count"] == 14
    assert graded["served_count"] == sf.DEFAULT_PULL_BUDGET
    assert len(graded["grade_lines"]) == sf.DEFAULT_PULL_BUDGET
    for row, line in zip(graded["messages"], graded["grade_lines"], strict=True):
        assert "body" not in row, "an ungraded body is exactly the flood this verb ended"
        assert row["body_chars"] == len(LONG_BODY)
        assert row["body_preview_truncated"] is True
        assert len(row["body_preview"]) <= sf.DEFAULT_PREVIEW_CHARS
        # every grade line answers "who, what, when, how big, where's the body"
        assert row["message_id"] in line and row["sender_seat_id"] in line
        assert row["message_type"] in line and str(row["cursor"]) in line
        assert row["body_handle"][:18] in line and row["expiry_grade"] in line
        assert "\n" not in line, "a grade is ONE line"
        assert row["descend"] == (
            f"/usr/bin/python3 scripts/seat_fabric.py body --message {row['message_id']}"
        )


def test_a_short_body_is_previewed_whole_and_not_marked_truncated():
    graded = sf.grade_pull({**_envelope(1), "messages": [_message(4, body="ping")]})
    (row,) = graded["messages"]
    assert row["body_preview"] == "ping" and row["body_preview_truncated"] is False
    assert row["body_chars"] == 4


def test_an_expired_row_is_not_labelled_unpulled_in_a_pull_grade():
    stale = _message(4)
    stale["expires_at"] = "2000-01-01T00:00:00+00:00"
    (row,) = sf.grade_pull({**_envelope(1), "messages": [stale]})["messages"]
    assert row["expiry_grade"] == "EXPIRED-AT-PULL"


# --- 2. named displacement ------------------------------------------------------


def test_the_budget_names_its_displacement_and_never_truncates_silently():
    graded = sf.grade_pull(_envelope(14), budget=6)

    assert graded["displaced_count"] == 8
    assert len(graded["displaced_message_ids"]) == 8
    served = {r["message_id"] for r in graded["messages"]}
    assert served.isdisjoint(graded["displaced_message_ids"])
    assert served | set(graded["displaced_message_ids"]) == {
        f"message:{c:03d}" for c in range(4, 18)
    }
    line = graded["displacement"]
    assert "DISPLACED 8 of 14" in line
    assert "PULLED" in line, "a displaced message is pulled, not still queued - say so"
    for mid in graded["displaced_message_ids"]:
        assert mid in line, "the ids are named, not just the count"
    # and the same residual survives the human rendering, one readable id per line
    rendered = sf.render_grade(graded)
    assert any("DISPLACED 8 of 14" in r and "ARE PULLED" in r for r in rendered)
    for mid in graded["displaced_message_ids"]:
        assert f"[seat-fabric]     {mid}" in rendered


def test_no_displacement_means_no_displacement_noise():
    graded = sf.grade_pull(_envelope(3), budget=6)
    assert graded["displaced_count"] == 0 and graded["displacement"] == ""
    assert not any("DISPLACED" in line for line in sf.render_grade(graded))


def test_budget_zero_is_no_budget():
    graded = sf.grade_pull(_envelope(14), budget=0)
    assert graded["served_count"] == 14 and graded["displaced_count"] == 0
    assert all("body" not in row for row in graded["messages"]), "still graded, just unbounded"


# --- 3. descent is explicit -----------------------------------------------------


def test_descent_carries_the_full_body_and_outranks_the_budget():
    late = "message:017"  # last by cursor: displaced under a budget of 6
    graded = sf.grade_pull(_envelope(14), budget=6, descend=(late,))

    served = {r["message_id"]: r for r in graded["messages"]}
    assert late in served, "an explicitly requested message is never displaced"
    assert served[late]["body"] == LONG_BODY
    assert graded["served_count"] == 6, "descent spends the budget, it does not enlarge it"
    assert all("body" not in r for mid, r in served.items() if mid != late)
    assert late not in graded["displaced_message_ids"]


def test_the_body_verb_is_the_across_session_half_of_the_descent(monkeypatch, capsys):
    """A displaced message is already pulled, so a second pull will not bring it back: the
    descent has to be a read, not a re-pull. That read must never claim delivery."""
    seen = {}

    def message_body(**kw):
        seen.update(kw)
        return {
            "schema_version": "laplace.atlas-message-body/1",
            "message_id": kw["message_id"],
            "body_handle": "sha256:aa",
            "body": LONG_BODY,
            "read_only": True,
            "delivery_claim": "none",
        }

    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: types.SimpleNamespace(
            message_body=message_body,
            snapshot=lambda: {
                "provider": {"messages": {"message:017": {"message": {"cursor": 17}}}}
            },
        ),
    )
    assert sf.cmd_body(_Args(message="message:017", raw=False)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert seen == {"message_id": "message:017"}
    assert payload["body"] == LONG_BODY and payload["delivery_claim"] == "none"

    assert sf.cmd_body(_Args(message="message:017", raw=True)) == 0
    assert capsys.readouterr().out.rstrip("\n") == LONG_BODY


def test_send_banks_supporting_files_as_resolvable_dependency_roots(tmp_path, monkeypatch, capsys):
    packet = tmp_path / "packet.bin"
    packet.write_bytes(b"exact supporting packet\x00with binary custody")
    calls = {"put": [], "send": []}

    def put_custody(data):
        calls["put"].append(data)
        return "sha256:" + ("a" * 64)

    def send(**kwargs):
        calls["send"].append(kwargs)
        return {"message_id": "message:banked-support"}

    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: types.SimpleNamespace(put_custody=put_custody, send=send),
    )
    args = _Args(
        sender="codex-seat",
        to="claude-seat",
        type="supporting-packet",
        key="supporting-packet:1",
        body="descend through the packet root",
        body_file="",
        expires="2099-01-01T00:00:00+00:00",
        root=["design=design:S1"],
        root_file=[f"packet={packet}"],
    )

    assert sf.cmd_send(args) == 0
    assert calls["put"] == [packet.read_bytes()]
    assert calls["send"][0]["dependency_roots"] == {
        "design": "design:S1",
        "packet": "sha256:" + ("a" * 64),
    }
    assert json.loads(capsys.readouterr().out)["message_id"] == "message:banked-support"


@pytest.mark.parametrize(
    ("roots", "root_files", "reason"),
    [
        (["body=sha256:forged"], [], "body dependency root"),
        (["packet=one", "packet=two"], [], "duplicate dependency root"),
        (["packet=one"], ["packet=/tmp/two"], "duplicate dependency root"),
        (["missing-separator"], [], "name=value"),
    ],
)
def test_send_refuses_ambiguous_dependency_roots(roots, root_files, reason, monkeypatch, capsys):
    monkeypatch.setattr(
        sf,
        "_bridge",
        lambda: (_ for _ in ()).throw(AssertionError("refusal must precede Atlas mutation")),
    )
    args = _Args(
        sender="codex-seat",
        to="claude-seat",
        type="bad-roots",
        key="bad-roots:1",
        body="a non-empty body",
        body_file="",
        expires="2099-01-01T00:00:00+00:00",
        root=roots,
        root_file=root_files,
    )

    assert sf.cmd_send(args) == 2
    assert reason in capsys.readouterr().err


def test_full_is_the_old_flood_made_explicit():
    graded = sf.grade_pull(_envelope(14), full=True)
    assert graded["served_count"] == 14 and graded["displaced_count"] == 0
    assert all(r["body"] == LONG_BODY for r in graded["messages"])


# --- 4. the envelope and the cursor survive -------------------------------------


def test_the_bridge_envelope_keys_ride_through_unchanged():
    envelope = _envelope(14)
    graded = sf.grade_pull(envelope)
    for key in (
        "schema_version",
        "receipt",
        "seat_id",
        "after_cursor",
        "result_cursor",
        "messages",
    ):
        assert key in graded
        if key != "messages":
            assert graded[key] == envelope[key]
    assert graded["grade_schema"] == sf.GRADE_SCHEMA
    assert envelope["messages"][0]["body"] == LONG_BODY, "grading must not mutate its input"


def test_cmd_pull_prints_one_parseable_envelope_and_keeps_the_cursor_call(fake_bridge, capsys):
    assert sf.cmd_pull(_Args()) == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["seat_id"] == "claude-seat" and payload["served_count"] == 6
    assert payload["displaced_count"] == 8
    # the delta-keying on the seat cursor is exactly as it was: same seat, same empty as_of
    assert fake_bridge["pull"] == [
        {"seat_id": "claude-seat", "as_of": "", "provider": "cli", "model": "seat-fabric-cli"}
    ]


def test_cmd_pull_lines_serves_the_grade_lines(fake_bridge, capsys):
    assert sf.cmd_pull(_Args(lines=True)) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("[seat-fabric] pull graded for claude-seat: served 6/14")
    assert sum(1 for line in out if "message:0" in line and "::" in line) == 6
    assert any("DISPLACED 8 of 14" in line for line in out)


# --- drain-and-re-arm -----------------------------------------------------------


def test_drain_grades_and_hands_back_the_exact_rearm_without_acking(fake_bridge, capsys):
    assert sf.cmd_drain(_Args()) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)  # stdout stays ONE parseable envelope

    assert payload["served_count"] == 6 and payload["displaced_count"] == 8
    assert payload["acked"] is False
    assert fake_bridge["acknowledge"] == [], "draining is not acknowledging"
    rearm = payload["rearm"]
    assert rearm["command"] == "/usr/bin/python3 scripts/fabric_watch.py --seat claude-seat"
    assert rearm["armed_by_this_verb"] is False and rearm["seat_id"] == "claude-seat"
    assert "RE-ARM NOW" in captured.err and rearm["command"] in captured.err


def test_poison_pull_is_loud_keeps_cursor_and_returns_nonzero(monkeypatch, capsys):
    bridge = types.SimpleNamespace(pull=lambda **_kwargs: _blocked_envelope())
    monkeypatch.setattr(sf, "_bridge", lambda: bridge)

    assert sf.cmd_pull(_Args(lines=True, seat="ego-seat")) == 1
    output = capsys.readouterr().out
    assert "BLOCKED for ego-seat" in output
    assert "cursor stayed at 906" in output
    assert "UNKNOWN #930 message:poison" in output
    assert "good mail remains QUEUED" in output


def test_poison_drain_does_not_claim_a_pull_or_rearm_success(monkeypatch, capsys):
    bridge = types.SimpleNamespace(pull=lambda **_kwargs: _blocked_envelope())
    monkeypatch.setattr(sf, "_bridge", lambda: bridge)

    assert sf.cmd_drain(_Args(seat="ego-seat")) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "BLOCKED-UNKNOWN-CONTENT"
    assert payload["cursor_advanced"] is False
    assert payload["acked"] is False


def test_drain_lines_carries_the_rearm_in_the_same_serve(fake_bridge, capsys):
    assert sf.cmd_drain(_Args(lines=True)) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("[seat-fabric] pull graded")
    assert out[-1] == (
        "[seat-fabric] RE-ARM NOW (background task): "
        "/usr/bin/python3 scripts/fabric_watch.py --seat claude-seat"
    )


def test_the_watcher_and_the_drain_name_each_other_exactly():
    """The cycle closes without memory: the fire message carries the drain command, and the
    drain carries the arm command back."""
    assert fw.drain_command("claude-seat") == (
        "/usr/bin/python3 scripts/seat_fabric.py drain --seat claude-seat"
    )
    codex = sf.rearm_block("codex-seat")
    assert codex["command"] is None
    assert codex["rearm_required"] is False
    assert codex["watcher"] == "laplace.representation.codex_seat_watcher"


def test_the_watcher_watches_the_seat_it_was_armed_for(monkeypatch):
    from laplace.representation import atlas_bridge

    monkeypatch.setattr(
        atlas_bridge,
        "snapshot",
        lambda: {
            "provider": {
                "messages": {
                    "a": {"message": {"recipient_seat_id": "claude-seat", "cursor": 4}},
                    "b": {"message": {"recipient_seat_id": "codex-seat", "cursor": 9}},
                }
            }
        },
    )
    assert fw.state_sig("claude-seat") == 4
    assert fw.state_sig("codex-seat") == 9
    assert fw.state_sig("nobody-seat") == 0


def test_the_bare_watcher_command_refuses_to_guess_a_seat():
    with pytest.raises(SystemExit) as exc:
        fw.main(["--hours", "0"])
    assert exc.value.code == 2


def test_manual_codex_watch_retires_when_wake_singleton_is_active(monkeypatch, capsys):
    from laplace.representation import atlas_bridge, codex_seat_watcher

    monkeypatch.setattr(
        codex_seat_watcher,
        "projection",
        lambda: {
            "status": "ACTIVE",
            "pid": 4321,
        },
    )
    monkeypatch.setattr(
        atlas_bridge,
        "provider_observation",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("retired manual watcher must not touch Atlas")
        ),
    )

    assert sf.main(["watch", "--seat", "codex-seat"]) == 0
    assert "manual watch retired" in capsys.readouterr().out


def test_harness_codex_watch_retires_when_wake_singleton_is_active(monkeypatch, capsys):
    from laplace.representation import atlas_bridge, codex_seat_watcher

    monkeypatch.setattr(
        codex_seat_watcher,
        "projection",
        lambda: {
            "status": "ACTIVE",
            "pid": 4321,
        },
    )
    monkeypatch.setattr(
        atlas_bridge,
        "provider_observation",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("retired harness watcher must not touch Atlas")
        ),
    )

    assert fw.main(["--seat", "codex-seat"]) == 0
    assert "manual watcher retired" in capsys.readouterr().out
