"""Public generation records keep the visible conversation and nothing else."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "synthetics papers"
    / "feedback-twinning-fields"
    / "publication"
    / "export_public_chat.py"
)
SPEC = importlib.util.spec_from_file_location("export_public_chat", SCRIPT)
assert SPEC and SPEC.loader
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


def _row(role: str, text: str) -> dict:
    return {
        "timestamp": "2026-07-24T12:00:00Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [{"type": "input_text", "text": text}],
        },
    }


def test_visible_messages_only_and_local_paths_redacted(tmp_path: Path):
    rollout = tmp_path / "rollout.jsonl"
    rows = [
        _row("developer", "hidden instruction"),
        _row("user", "<recommended_plugins>\nprivate wrapper"),
        _row(
            "user",
            "<codex_internal_context source=\"goal\">\nprivate goal state\n"
            "</codex_internal_context>",
        ),
        _row(
            "user",
            "<in-app-browser-context source=\"ambient-ui-state\">\n"
            "private browser state\n</in-app-browser-context>\n\n"
            "## My request for Codex:\nA visible browser-era request.",
        ),
        _row(
            "user",
            r"Please inspect C:\Users\gerar\VScodeProjects\laplace\paper.tex",
        ),
        _row("assistant", "I inspected it."),
        {
            "timestamp": "2026-07-24T12:00:01Z",
            "type": "response_item",
            "payload": {"type": "function_call", "name": "shell", "arguments": "{}"},
        },
    ]
    rollout.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    messages = EXPORT.extract_messages(rollout)

    assert [row["role"] for row in messages] == ["user", "user", "assistant"]
    assert messages[0]["text"] == "A visible browser-era request."
    assert "[local Laplace workspace]" in messages[1]["text"]
    assert "hidden instruction" not in json.dumps(messages)
    assert "recommended_plugins" not in json.dumps(messages)
    assert "private goal state" not in json.dumps(messages)
    assert "private browser state" not in json.dumps(messages)
    assert "in-app-browser-context" not in json.dumps(messages)


def test_html_states_the_public_boundary(tmp_path: Path):
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text(
        json.dumps(_row("user", "A visible message.")) + "\n",
        encoding="utf-8",
    )

    rendered = EXPORT.render_html(
        EXPORT.extract_messages(rollout),
        "thread-id",
    )

    assert "user and assistant messages only" in rendered
    assert "hidden reasoning" in rendered
    assert "A visible message." in rendered
