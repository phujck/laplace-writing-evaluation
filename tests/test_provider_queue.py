"""Provider attention is a replaceable projection, never a second work ledger."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from laplace.representation import provider_queue


class FakeQueue:
    rows: dict[str, list[dict]] = {}
    next_id = 1

    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None

    def list(self, thread_id):
        return deepcopy(self.rows.get(thread_id, []))

    def add(self, *, thread_id, client_message_id, prompt):
        row = {
            "id": f"queued:{self.next_id}",
            "clientUserMessageId": client_message_id,
            "input": [{"type": "text", "text": prompt}],
        }
        type(self).next_id += 1
        self.rows.setdefault(thread_id, []).append(row)
        return deepcopy(row)

    def delete(self, *, thread_id, submission_id):
        before = self.rows.get(thread_id, [])
        after = [row for row in before if row["id"] != submission_id]
        self.rows[thread_id] = after
        return len(after) != len(before)


@pytest.fixture(autouse=True)
def _fake_provider(monkeypatch):
    FakeQueue.rows = {}
    FakeQueue.next_id = 1
    monkeypatch.setattr(provider_queue, "CodexProviderQueue", FakeQueue)


def _token(*, generation="sha256:generation", token="wake:" + "a" * 64):
    return {
        "seat_id": "codex-seat",
        "thread_id": "01-thread",
        "lease_generation": generation,
        "token": token,
    }


def _prompt(token):
    return (
        "[Eigen Fabric watcher] scoped under "
        "laplace.provider-attention-contract/2: " + token["token"]
    )


def test_queue_attention_is_idempotent_for_one_seat_task_token_generation():
    token = _token()

    first = provider_queue.queue_attention(
        thread_id="01-thread", wake_token=token, prompt=_prompt(token)
    )
    second = provider_queue.queue_attention(
        thread_id="01-thread", wake_token=token, prompt=_prompt(token)
    )

    assert first["created"] is True
    assert second["created"] is False
    assert first["queued_submission_id"] == second["queued_submission_id"]
    assert len(FakeQueue.rows["01-thread"]) == 1


def test_generation_changes_provider_client_identity():
    first = provider_queue.attention_client_message_id(_token(generation="sha256:one"))
    second = provider_queue.attention_client_message_id(_token(generation="sha256:two"))

    assert first != second


def test_deterministic_client_id_collision_with_different_body_fails_closed():
    token = _token()
    client_id = provider_queue.attention_client_message_id(token)
    FakeQueue.rows["01-thread"] = [{
        "id": "queued:collision",
        "clientUserMessageId": client_id,
        "input": [{"type": "text", "text": "wrong human body"}],
    }]

    with pytest.raises(provider_queue.ProviderQueueError, match="collides"):
        provider_queue.queue_attention(
            thread_id="01-thread", wake_token=token, prompt=_prompt(token)
        )

    assert FakeQueue.rows["01-thread"][0]["id"] == "queued:collision"


def test_ordinary_retirement_preserves_unowned_raw_provider_input():
    token = _token()
    queued = provider_queue.queue_attention(
        thread_id="01-thread", wake_token=token, prompt=_prompt(token)
    )
    FakeQueue.rows["01-thread"].append(
        {
            "id": "queued:raw",
            "clientUserMessageId": "raw-message",
            "input": [{"type": "text", "text": "EMERGENCY stale direct packet"}],
        }
    )

    receipt = provider_queue.retire_attention(
        thread_id="01-thread",
        client_message_id=queued["client_user_message_id"],
        prompt_digest=queued["prompt_digest"],
    )

    assert receipt["retired_submission_count"] == 1
    assert receipt["nonmatching_submission_count"] == 1
    assert [row["id"] for row in FakeQueue.rows["01-thread"]] == ["queued:raw"]


def test_human_lookalike_body_is_never_owned_without_exact_id_and_digest():
    lookalike = {
        "id": "queued:human-lookalike",
        "clientUserMessageId": "random-human-id",
        "input": [{
            "type": "text",
            "text": (
                "[Eigen Fabric watcher] please discuss "
                "laplace.provider-attention-contract/2"
            ),
        }],
    }
    FakeQueue.rows["01-thread"] = [lookalike]

    receipt = provider_queue.retire_attention(
        thread_id="01-thread",
        client_message_id="expected-scoped-id",
        prompt_digest="sha256:" + "a" * 64,
    )

    assert receipt["retired_submission_count"] == 0
    assert receipt["nonmatching_submission_count"] == 1
    assert FakeQueue.rows["01-thread"] == [lookalike]


def test_exact_client_id_with_a_copied_or_altered_body_refuses_retirement():
    token = _token()
    client_id = provider_queue.attention_client_message_id(token)
    FakeQueue.rows["01-thread"] = [{
        "id": "queued:collision",
        "clientUserMessageId": client_id,
        "input": [{
            "type": "text",
            "text": _prompt(token) + "\nHuman-added instruction",
        }],
    }]

    with pytest.raises(provider_queue.ProviderQueueError, match="different or unowned"):
        provider_queue.retire_attention(
            thread_id="01-thread",
            client_message_id=client_id,
            prompt_digest="sha256:" + "a" * 64,
        )

    assert FakeQueue.rows["01-thread"][0]["id"] == "queued:collision"


def test_delete_false_or_surviving_owned_row_cannot_return_success(monkeypatch):
    token = _token()
    queued = provider_queue.queue_attention(
        thread_id="01-thread", wake_token=token, prompt=_prompt(token)
    )
    monkeypatch.setattr(FakeQueue, "delete", lambda *_args, **_kwargs: False)

    with pytest.raises(provider_queue.ProviderQueueError, match="could not be retired"):
        provider_queue.retire_attention(
            thread_id="01-thread",
            client_message_id=queued["client_user_message_id"],
            prompt_digest=queued["prompt_digest"],
        )

    assert len(FakeQueue.rows["01-thread"]) == 1


def test_operational_api_exposes_no_authority_to_delete_unowned_input():
    assert not hasattr(provider_queue, "retire_task_generation")
    assert not hasattr(provider_queue, "recover_retired_task_generation")
    source = (Path(__file__).parents[1] / "scripts/provider_queue_gate.py").read_text(
        encoding="utf-8"
    )
    assert "task-generation" not in source
    assert "--client-message-id" not in source
    assert "--prompt-digest" not in source


def test_operational_route_never_shells_out_to_raw_codex_queue():
    root = Path(__file__).parents[1]
    watcher = (root / "src/laplace/representation/codex_seat_watcher.py").read_text(encoding="utf-8")
    wake = (root / "src/laplace/engine/wake.py").read_text(encoding="utf-8")
    session_hook = (root / ".codex/hooks/session-start.mjs").read_text(encoding="utf-8")

    forbidden = ('"queue", "--thread"', "'queue', '--thread'", "`codex queue`")
    for source in (watcher, wake, session_hook):
        assert not any(fragment in source for fragment in forbidden)
