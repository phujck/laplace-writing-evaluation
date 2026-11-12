from __future__ import annotations

from copy import deepcopy

import pytest

from laplace.web.conversation_serve import AuthorTurnCustodyMismatch, bind_blueprint_routes, broker_round, canonical_bytes, canonical_handle, materialize_conversation_serve, resolve_audience, turn_handle


def _turn() -> dict:
    return {
        "schema_version": "laplace.author-turn/1",
        "record": "talk",
        "id": "TALK-ONE",
        "actor": "gerard",
        "audience": "eigen",
        "recipient_seat_ids": ["codex-seat", "claude-seat"],
        "blueprint_materialization_ids": ["sha256:" + "c" * 64],
        "text": "make the front door the session",
        "via": "front-door",
        "ts": "2026-08-25T00:00:00+00:00",
    }


def _message(turn: dict, seat_id: str, cursor: int, status: str = "queued") -> dict:
    message_id = f"message:{seat_id}"
    return {
        "message": {
            "message_id": message_id,
            "sender_seat_id": "gerard-seat",
            "recipient_seat_id": seat_id,
            "message_type": "conversation-turn",
            "body_handle": f"sha256:{cursor:064x}",
            "dependency_roots": {"author_turn": turn_handle(turn)},
            "cursor": cursor,
            "expires_at": "2026-08-28T00:00:00+00:00",
        },
        "sent_event_id": f"event:send:{seat_id}",
        "assumption": "atlas rebuild",
        "fibre": "s1",
        "status": status,
        "last_pull_event_id": None,
        "acknowledgement_event_id": None,
        "reconstruction_handle": None,
        "delivered": False,
    }


def _state(turn: dict) -> dict:
    return {
        "active_context": {"assumption": "atlas rebuild", "fibre": "s1"},
        "event_count": 20,
        "head_event_id": "event:20",
        "seats": {
            "codex-seat": {"role": "provider", "status": "active"},
            "claude-seat": {"role": "provider", "status": "active"},
            "gerard-seat": {"role": "author", "status": "active"},
        },
        "seat_cursors": {},
        "messages": {
            "message:codex-seat": _message(turn, "codex-seat", 10),
            "message:claude-seat": _message(turn, "claude-seat", 11),
        },
        "reconstruction_proofs": {},
    }


def _blueprint() -> dict:
    return {
        "generation_id": "sha256:" + "a" * 64,
        "pour_handle": "sha256:" + "b" * 64,
        "encoder_id": "bge-small",
        "embedding_batch_policy": "singleton-content/1",
        "entry_role": "live-s1-law",
        "counts": {
            "clauses": 140,
            "clusters": 64,
            "implementation_bindings": 10,
            "evidence_findings": 5,
            "current_materializations": 1,
            "stale_materializations": 5,
        },
        "current_materializations": [{
            "materialization_id": "sha256:" + "c" * 64,
            "goal": "unify the interface and attention broker",
            "fibre": "conjugate-interface",
            "coverage": 0.5,
            "dependency_frontier": {"design.md": "sha256:" + "d" * 64},
            "results": [{
                "logical_id": "design:transport",
                "subject_id": "design-subject:stable",
                "subject_handle": "sha256:" + "e" * 64,
                "version_edge_id": "edge:version-of:one",
                "object_id": "design-clause:version-one",
                "content_handle": "sha256:" + "f" * 64,
                "exact_byte_hash": "sha256:" + "1" * 64,
                "source_path": "DESIGN.md",
                "source_hash": "sha256:" + "2" * 64,
                "start": 20,
                "end": 80,
                "trail": ["Design", "transport"],
                "design_role": "conjugate-interface",
                "fibre": "conjugate-interface",
                "implements": [{
                    "implementation_path": "src/laplace/web/conversation_serve.py",
                    "proof_state": "conjecture",
                    "required_findings": [],
                }],
            }],
        }],
        "omitted_materializations": 0,
    }


def _turn_custody_bytes(turn: dict) -> bytes:
    return canonical_bytes({
        "schema_version": "laplace.author-turn/1",
        "row": turn,
    })


def test_materialization_is_pure_and_exact_custody_is_reported_outside_identity(
    monkeypatch,
) -> None:
    from laplace.representation import atlas_bridge

    def refuse_write(_data: bytes) -> str:
        raise AssertionError("a read projection attempted to write custody")

    monkeypatch.setattr(atlas_bridge, "put_custody", refuse_write)
    turn = _turn()
    custody = _turn_custody_bytes(turn)
    serve = materialize_conversation_serve(
        turn,
        _state(turn),
        _blueprint(),
        author_turn_custody_bytes=custody,
    )

    assert serve["author_turn_custody"] == {
        "status": "CUSTODY_EXACT",
        "content_handle": turn_handle(turn),
        "bytes": len(custody),
    }
    assert serve["acknowledgement_eligible"] is True
    assert not any(
        row["class"] == "author-turn-custody-absent"
        for row in serve["omission_residual"]
    )
    assert "author_turn_custody" not in serve["dependency_frontier"]


def test_missing_author_turn_custody_is_a_hashed_visible_nonblocking_omission() -> None:
    turn = _turn()
    serve = materialize_conversation_serve(turn, _state(turn), _blueprint())
    omission = next(
        row for row in serve["omission_residual"]
        if row["class"] == "author-turn-custody-absent"
    )
    unhashed = {key: value for key, value in omission.items() if key != "omission_handle"}

    assert serve["author_turn_custody"]["status"] == "CUSTODY_ABSENT"
    assert serve["acknowledgement_eligible"] is False
    assert omission["expected_handle"] == turn_handle(turn)
    assert omission["omission_handle"] == canonical_handle(unhashed)


def test_one_byte_author_turn_custody_mismatch_refuses() -> None:
    turn = _turn()
    custody = _turn_custody_bytes(turn)

    with pytest.raises(AuthorTurnCustodyMismatch, match="custody bytes disagree"):
        materialize_conversation_serve(
            turn,
            _state(turn),
            _blueprint(),
            author_turn_custody_bytes=custody[:-1] + bytes([custody[-1] ^ 1]),
        )


def test_queued_is_routed_but_never_rendered_delivered() -> None:
    turn = _turn()
    serve = materialize_conversation_serve(turn, _state(turn), _blueprint())

    assert serve["author_lifecycle"] == "routed"
    assert all(row["phase"] == "routed" for row in serve["recipient_states"])
    assert all(row["delivered"] is False for row in serve["recipient_states"])
    assert {row["logical_recipient"] for row in serve["recipient_states"]} == {
        "builder", "other-self"
    }
    assert all("diagnostic_seat_id" not in row for row in serve["recipients"])
    assert sum(
        item["class"] == "delivery-incomplete"
        for item in serve["omission_residual"]
    ) == 2


def test_mixed_recipient_state_preserves_exact_reconstruction_proof() -> None:
    turn = _turn()
    state = _state(turn)
    codex = state["messages"]["message:codex-seat"]
    codex.update({
        "status": "delivered",
        "last_pull_event_id": "event:pull:codex",
        "acknowledgement_event_id": "event:ack:codex",
        "reconstruction_handle": "sha256:" + "3" * 64,
        "delivered": True,
    })
    state["reconstruction_proofs"] = {
        "event:reconstruct:codex": {
            "evaluation": {
                "arguments": {
                    "message_id": "message:codex-seat",
                    "goal": "answer this exact author turn",
                },
                "output_handles": ["sha256:" + "3" * 64],
            }
        }
    }

    serve = materialize_conversation_serve(turn, state, _blueprint())
    by_label = {row["logical_recipient"]: row for row in serve["recipient_states"]}

    assert serve["author_lifecycle"] == "routed"
    assert serve["mixed_recipient_phases"] is True
    assert by_label["builder"]["phase"] == "closed"
    assert by_label["builder"]["reconstruction_event"] == "event:reconstruct:codex"
    assert by_label["builder"]["delivered"] is True
    assert by_label["other-self"]["phase"] == "routed"


def test_unrelated_atlas_event_moves_browser_cursor_not_shown_serve() -> None:
    turn = _turn()
    first_state = _state(turn)
    second_state = deepcopy(first_state)
    second_state["event_count"] = 99
    second_state["head_event_id"] = "event:unrelated"

    first = materialize_conversation_serve(turn, first_state, _blueprint())
    second = materialize_conversation_serve(turn, second_state, _blueprint())

    assert first["shown_handle"] == second["shown_handle"]
    assert first["browser_event_cursor"] != second["browser_event_cursor"]


def test_unrelated_blueprint_route_and_stale_count_do_not_move_shown_serve() -> None:
    turn = _turn()
    first_blueprint = _blueprint()
    second_blueprint = deepcopy(first_blueprint)
    unrelated = deepcopy(first_blueprint["current_materializations"][0])
    unrelated["materialization_id"] = "sha256:" + "9" * 64
    unrelated["goal"] = "freeze release figures for a foreign pipeline"
    unrelated["results"][0]["content_handle"] = "sha256:" + "8" * 64
    second_blueprint["current_materializations"].insert(0, unrelated)
    second_blueprint["counts"]["stale_materializations"] += 1

    first = materialize_conversation_serve(turn, _state(turn), first_blueprint)
    second = materialize_conversation_serve(turn, _state(turn), second_blueprint)

    assert first["shown_handle"] == second["shown_handle"]
    assert [r["materialization_id"] for r in second["blueprint"]["routes"]] == [
        "sha256:" + "c" * 64
    ]


def test_lexical_route_admission_uses_goal_not_shared_fibre_tokens() -> None:
    turn = _turn()
    turn.pop("blueprint_materialization_ids")
    turn["text"] = "unify the interface and attention broker"
    first_blueprint = _blueprint()
    second_blueprint = deepcopy(first_blueprint)
    foreign = deepcopy(first_blueprint["current_materializations"][0])
    foreign["materialization_id"] = "sha256:" + "7" * 64
    foreign["goal"] = "freeze release figures for a foreign pipeline"
    foreign["fibre"] = "conjugate-interface"
    foreign["results"][0]["content_handle"] = "sha256:" + "8" * 64
    second_blueprint["current_materializations"].insert(0, foreign)

    first = materialize_conversation_serve(turn, _state(turn), first_blueprint)
    second = materialize_conversation_serve(turn, _state(turn), second_blueprint)

    assert first["shown_handle"] == second["shown_handle"]
    assert [r["materialization_id"] for r in second["blueprint"]["routes"]] == [
        "sha256:" + "c" * 64
    ]


def test_historical_route_admission_refuses_one_weak_shared_goal_term() -> None:
    turn = _turn()
    turn.pop("blueprint_materialization_ids")
    turn["text"] = (
        "conjugate serve custody broker shown handle transport vocabulary implementation"
    )
    first_blueprint = _blueprint()
    first_blueprint["current_materializations"][0]["goal"] = (
        "conjugate serve custody broker handle transport vocabulary implementation"
    )
    second_blueprint = deepcopy(first_blueprint)
    foreign = deepcopy(first_blueprint["current_materializations"][0])
    foreign["materialization_id"] = "sha256:" + "7" * 64
    foreign["goal"] = "how does the pipeline release freeze the shown figures"
    foreign["fibre"] = "conjugate-interface"
    foreign["results"][0]["content_handle"] = "sha256:" + "8" * 64
    second_blueprint["current_materializations"].insert(0, foreign)

    first = materialize_conversation_serve(turn, _state(turn), first_blueprint)
    second = materialize_conversation_serve(turn, _state(turn), second_blueprint)

    assert first["shown_handle"] == second["shown_handle"]
    assert all(
        route["materialization_id"] != foreign["materialization_id"]
        for route in second["blueprint"]["routes"]
    )


def test_historical_route_cap_is_a_hashed_residual_not_a_silent_slice() -> None:
    turn = _turn()
    turn.pop("blueprint_materialization_ids")
    turn["text"] = "unify the interface and attention broker"
    blueprint = _blueprint()
    base = blueprint["current_materializations"][0]
    blueprint["current_materializations"] = []
    for index in range(6):
        route = deepcopy(base)
        route["materialization_id"] = f"sha256:{index:064x}"
        blueprint["current_materializations"].append(route)

    serve = materialize_conversation_serve(turn, _state(turn), blueprint)
    residual = next(
        item for item in serve["omission_residual"]
        if item["class"] == "historical-route-selection"
    )

    assert len(serve["blueprint"]["routes"]) == 3
    assert residual["eligible_count"] == 6
    assert residual["omitted_count"] == 3
    assert residual["omitted_handle"].startswith("sha256:")


def test_new_turn_binding_distinguishes_an_explicitly_empty_selection() -> None:
    turn = _turn()
    turn.pop("blueprint_materialization_ids")
    turn["text"] = "a wholly foreign question"
    binding = bind_blueprint_routes(turn, _blueprint())
    bound_turn = {**turn, "blueprint_materialization_ids": binding["selected_ids"]}

    assert binding["selected_ids"] == []
    serve = materialize_conversation_serve(bound_turn, _state(bound_turn), _blueprint())
    assert serve["blueprint"]["routes"] == []
    assert not any(
        item["class"] == "historical-route-selection"
        for item in serve["omission_residual"]
    )


def test_foreign_moved_source_is_visible_outside_the_shown_preimage() -> None:
    turn = _turn()
    first_blueprint = _blueprint()
    second_blueprint = deepcopy(first_blueprint)
    second_blueprint["moved_source_roots"] = [{
        "path": "src/atlas/bench/planted_spectral.py",
        "expected": "sha256:" + "1" * 64,
        "actual": "sha256:" + "2" * 64,
    }]

    first = materialize_conversation_serve(turn, _state(turn), first_blueprint)
    second = materialize_conversation_serve(turn, _state(turn), second_blueprint)

    assert first["shown_handle"] == second["shown_handle"]
    assert not any(
        item["class"] == "source-frontier-moved"
        for item in second["omission_residual"]
    )
    assert second["projection_residual"][0]["boundary"].endswith(
        "planted_spectral.py"
    )


def test_truncated_blueprint_frontier_refuses_to_mint_a_reader_dependent_handle() -> None:
    blueprint = _blueprint()
    blueprint["omitted_materializations"] = 1

    with pytest.raises(ValueError, match="complete blueprint route frontier"):
        materialize_conversation_serve(_turn(), _state(_turn()), blueprint)


def test_truncated_blueprint_results_also_refuse_to_mint() -> None:
    blueprint = _blueprint()
    blueprint["current_materializations"][0]["omitted_results"] = 1

    with pytest.raises(ValueError, match="complete blueprint route frontier"):
        materialize_conversation_serve(_turn(), _state(_turn()), blueprint)


def test_unpulled_message_cannot_become_replied_through_a_missing_reply_key() -> None:
    turn = _turn()
    state = _state(turn)
    state["messages"]["message:reply"] = {
        **_message(turn, "gerard-seat", 12),
        "message": {
            **_message(turn, "gerard-seat", 12)["message"],
            "message_id": "message:reply",
            "sender_seat_id": "codex-seat",
            "recipient_seat_id": "gerard-seat",
        },
    }

    serve = materialize_conversation_serve(turn, state, _blueprint())
    builder = next(row for row in serve["recipient_states"] if row["logical_recipient"] == "builder")

    assert builder["phase"] == "routed"
    assert builder["delivered"] is False


def test_pulled_message_cannot_become_replied_through_a_missing_reply_key() -> None:
    turn = _turn()
    state = _state(turn)
    outbound = state["messages"]["message:codex-seat"]
    outbound.update({"status": "pulled", "last_pull_event_id": "event:pull:codex"})
    reply = _message(turn, "gerard-seat", 12, status="queued")
    reply["message"].update({
        "message_id": "message:reply",
        "sender_seat_id": "codex-seat",
        "recipient_seat_id": "gerard-seat",
        "dependency_roots": {"author_turn": turn_handle(turn)},
    })
    state["messages"]["message:reply"] = reply

    serve = materialize_conversation_serve(turn, state, _blueprint())
    builder = next(
        row for row in serve["recipient_states"]
        if row["logical_recipient"] == "builder"
    )
    assert builder["phase"] == "received"


def test_reply_requires_exact_message_id_and_the_original_recipient() -> None:
    turn = _turn()
    state = _state(turn)
    outbound = state["messages"]["message:codex-seat"]
    outbound.update({"status": "pulled", "last_pull_event_id": "event:pull:codex"})
    reply = _message(turn, "gerard-seat", 12, status="queued")
    reply["message"].update({
        "message_id": "message:reply",
        "sender_seat_id": "codex-seat",
        "recipient_seat_id": "gerard-seat",
        "dependency_roots": {
            "author_turn": turn_handle(turn),
            "in_reply_to": "message:wrong",
        },
    })
    state["messages"]["message:reply"] = reply

    wrong_id = materialize_conversation_serve(turn, state, _blueprint())
    builder = next(
        row for row in wrong_id["recipient_states"]
        if row["logical_recipient"] == "builder"
    )
    assert builder["phase"] == "received"

    state["messages"]["message:reply"]["message"]["dependency_roots"][
        "in_reply_to"
    ] = "message:codex-seat"
    state["messages"]["message:reply"]["message"]["sender_seat_id"] = "claude-seat"
    forged_sender = materialize_conversation_serve(turn, state, _blueprint())
    builder = next(
        row for row in forged_sender["recipient_states"]
        if row["logical_recipient"] == "builder"
    )
    assert builder["phase"] == "received"


def test_current_spectral_route_exposes_stable_mutation_subject_and_version() -> None:
    turn = _turn()
    serve = materialize_conversation_serve(turn, _state(turn), _blueprint())
    target = serve["blueprint"]["routes"][0]["results"][0]

    assert target["subject_id"] == "design-subject:stable"
    assert target["content_handle"] != target["subject_handle"]
    assert target["implements"][0]["implementation_path"].endswith(
        "conversation_serve.py"
    )


def test_partial_fanout_is_a_priced_red_not_a_collapsed_success() -> None:
    turn = _turn()
    state = _state(turn)
    del state["messages"]["message:claude-seat"]

    serve = materialize_conversation_serve(turn, state, _blueprint())

    by_label = {row["logical_recipient"]: row for row in serve["recipient_states"]}
    assert serve["author_lifecycle"] == "banked-not-routed"
    assert serve["mixed_recipient_phases"] is True
    assert by_label["other-self"]["phase"] == "banked-not-routed"
    assert any(
        item["class"] == "recipient-not-routed"
        and item["boundary"] == "other-self"
        for item in serve["omission_residual"]
    )


def test_duplicate_fanout_keeps_strongest_proof_and_prices_the_omission() -> None:
    turn = _turn()
    state = _state(turn)
    first = state["messages"]["message:codex-seat"]
    first.update({
        "status": "delivered",
        "last_pull_event_id": "event:pull:codex",
        "acknowledgement_event_id": "event:ack:codex",
        "delivered": True,
    })
    duplicate = deepcopy(_message(turn, "codex-seat", 99))
    duplicate["message"]["message_id"] = "message:codex-seat:retry"
    duplicate["sent_event_id"] = "event:send:codex:retry"
    state["messages"]["message:codex-seat:retry"] = duplicate

    serve = materialize_conversation_serve(turn, state, _blueprint())
    builder = next(row for row in serve["recipient_states"] if row["logical_recipient"] == "builder")

    assert builder["phase"] == "closed"
    assert builder["recipient_message_id"] == "message:codex-seat"
    duplicate_red = next(
        item for item in serve["omission_residual"] if item["class"] == "duplicate-fanout"
    )
    assert duplicate_red["descend"] == ["message:codex-seat:retry"]


def test_eigen_audience_resolves_logical_seats_not_sessions() -> None:
    state = _state(_turn())
    state["seats"]["closed-seat"] = {"role": "provider", "status": "closed"}
    name, recipients = resolve_audience(state, "eigen")

    assert name == "eigen"
    assert recipients == ("claude-seat", "codex-seat")


def test_broker_repairs_only_missing_fanout_from_the_durable_turn(monkeypatch) -> None:
    from laplace.representation import atlas_bridge
    from laplace.engine import rows

    turn = _turn()
    state = _state(turn)
    del state["messages"]["message:claude-seat"]
    sent = []

    monkeypatch.setattr(rows, "scan", lambda source: iter(((17, turn),)))
    monkeypatch.setattr(atlas_bridge, "snapshot", lambda: {"provider": state})
    monkeypatch.setattr(
        atlas_bridge,
        "blueprint_projection",
        lambda materialization_limit=0: {"generation_id": _blueprint()["generation_id"]},
    )

    def send(**kwargs):
        sent.append(kwargs)
        return {
            "message_id": "message:repair",
            "idempotent": False,
        }

    monkeypatch.setattr(atlas_bridge, "send", send)
    result = broker_round()

    assert result["complete"] is True and result["routed_messages"] == 1
    assert [item["recipient_seat_id"] for item in sent] == ["claude-seat"]
    assert sent[0]["dependency_roots"]["author_turn"] == turn_handle(turn)


def test_broker_retries_dead_fanout_under_a_new_idempotency_generation(monkeypatch) -> None:
    from laplace.representation import atlas_bridge
    from laplace.engine import rows

    turn = _turn()
    state = _state(turn)
    state["messages"]["message:codex-seat"]["status"] = "expired"
    state["messages"]["message:claude-seat"]["status"] = "refused"
    sent = []

    monkeypatch.setattr(rows, "scan", lambda source: iter(((17, turn),)))
    monkeypatch.setattr(atlas_bridge, "snapshot", lambda: {"provider": state})
    monkeypatch.setattr(
        atlas_bridge,
        "blueprint_projection",
        lambda materialization_limit=0: {"generation_id": _blueprint()["generation_id"]},
    )

    def send(**kwargs):
        sent.append(kwargs)
        return {"message_id": f"message:retry:{len(sent)}", "idempotent": False}

    monkeypatch.setattr(atlas_bridge, "send", send)
    result = broker_round()

    assert result["complete"] is True and result["routed_messages"] == 2
    assert all(item["idempotency_key"].endswith(":retry-1") for item in sent)
    assert all(item["dependency_roots"]["fanout_generation"] == "1" for item in sent)
    assert atlas_bridge.custody_has(turn_handle(turn))
