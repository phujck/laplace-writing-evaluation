#!/usr/bin/env python3
"""Codex JSON hook adapter for the actual PreCompact/PostCompact events."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from laplace.engine.compaction_boundary import postcompact, precompact  # noqa: E402


def _output(receipt: dict) -> dict:
    event = receipt["event"]
    if event == "PreCompact":
        allowed = receipt.get("status") == "SEALED"
    else:
        # Human continuity survives FOG/UNKNOWN, while the injected receipt explicitly keeps
        # substantive tools/provider claims disabled until the cold successor is ADMITTED.
        allowed = receipt.get("status") in {"ADMITTED", "FOG", "UNKNOWN"}
    reason = None if allowed else (
        "semantic compaction held: the current author/session delta is banked, but no "
        "CURRENT zero-deferred S-to-F profile is sealed"
    )
    return {
        "continue": allowed,
        "stopReason": reason,
        "suppressOutput": False,
        "systemMessage": "COMPACTION CONTINUATION:\n" + json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
    }


def main() -> int:
    try:
        event = json.load(sys.stdin)
        name = str(event.get("hook_event_name") or "")
        if name == "PreCompact":
            receipt = precompact(ROOT, event)
        elif name == "PostCompact":
            receipt = postcompact(ROOT, event)
        else:
            raise RuntimeError(f"unsupported compaction hook event {name!r}")
        print(json.dumps(_output(receipt), ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as exc:  # noqa: BLE001 - a malformed boundary must explicitly hold
        print(json.dumps({
            "continue": False,
            "stopReason": f"compaction continuation refused: {type(exc).__name__}: {exc}",
            "suppressOutput": False,
            "systemMessage": "COMPACTION CONTINUATION: REFUSED; predecessor context remains live",
        }, ensure_ascii=False, separators=(",", ":")))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
