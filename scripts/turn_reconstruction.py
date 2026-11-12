#!/usr/bin/env python3
"""Codex hook adapter for mandatory read-only root-seat typed descent."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from laplace.engine.turn_reconstruction import reconstruct_turn  # noqa: E402


def main() -> int:
    event = json.load(sys.stdin)
    receipt = reconstruct_turn(
        ROOT,
        event_name=str(event.get("hook_event_name") or "UserPromptSubmit"),
        prompt=str(event.get("prompt") or event.get("user_prompt") or ""),
        function=os.environ.get("LAPLACE_FUNCTION", ""),
        seat_id=os.environ.get("LAPLACE_SEAT_ID", ""),
        thread_id=os.environ.get("CODEX_THREAD_ID", ""),
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": str(event.get("hook_event_name") or "UserPromptSubmit"),
            "additionalContext": "TURN RECONSTRUCTION:\n" + json.dumps(
                receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        }
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
