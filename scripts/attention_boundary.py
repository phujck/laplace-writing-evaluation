#!/usr/bin/env python3
"""Codex lifecycle-hook face of the canonical Atlas attention projection."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation import atlas_bridge, codex_seat_watcher  # noqa: E402
from laplace.representation.attention import hook_response, project_attention_from_mail_frontier
from laplace.engine.turn_reconstruction import hook_response as turn_hook_response
from laplace.engine.turn_reconstruction import reconstruct_turn  # noqa: E402


def _bound_seat_id(*, watcher_prompt: bool = False) -> str | None:
    explicit = os.environ.get("LAPLACE_SEAT_ID", "").strip()
    thread_id = os.environ.get("CODEX_THREAD_ID", "").strip()
    if not thread_id:
        return explicit or None
    binding = atlas_bridge.provider_seat_binding(
        provider_session_ref=f"codex:{thread_id}"
    )
    if binding.get("status") == "BOUND":
        canonical = str(binding["seat_id"])
        if explicit and explicit != canonical:
            raise RuntimeError(
                "explicit startup seat conflicts with canonical provider binding: "
                f"explicit={explicit}, canonical={canonical}"
            )
        occupancy = binding.get("occupancy")
        bound_generation = (
            occupancy.get("current_provider_identity_generation")
            if isinstance(occupancy, dict)
            else None
        )
        watcher = codex_seat_watcher.projection(canonical)
        live_generation = watcher.get("lease_generation")
        if (
            not isinstance(bound_generation, str)
            or not bound_generation.strip()
            or not isinstance(live_generation, str)
            or not live_generation.strip()
            or live_generation != bound_generation
        ):
            raise RuntimeError(
                "provider seat binding requires watcher-generation renewal before "
                "authoritative tools: "
                f"bound={bound_generation}, live={live_generation}"
            )
        return canonical
    if binding.get("status") == "AMBIGUOUS":
        raise RuntimeError("provider task has an ambiguous canonical seat binding")
    if binding.get("status") == "UNBOUND":
        # A provider task that has lost canonical occupancy cannot recover authority from
        # the process-local seat label it inherited at startup.  Project it as unclaimed
        # for every hook face.  ``hook_response`` still permits the exact, single-command
        # startup/Fabric recovery capabilities from that state; ordinary tools remain
        # fenced and watcher prompts remain inert.
        return None
    raise RuntimeError(
        "canonical provider binding is unavailable: "
        + str(binding.get("status") or "missing status")
    )


def main() -> int:
    try:
        event = json.load(sys.stdin)
        prompt = str(event.get("prompt") or event.get("user_prompt") or "")
        classification = codex_seat_watcher.classify_attention_prompt(prompt)
        # Human turns always receive read-only reconstruction.  They do not need a watcher or
        # lifecycle identity proof merely to acquire context; that ceremony is suspended during
        # reversible development.  Exact provider attention still uses the canonical mail face.
        if classification not in {"LEGACY-INERT", "OPAQUE-TOKEN-CANDIDATE"}:
            turn = reconstruct_turn(
                ROOT,
                event_name=str(event.get("hook_event_name") or "UserPromptSubmit"),
                prompt=prompt,
                function=os.environ.get("LAPLACE_FUNCTION", ""),
                seat_id=os.environ.get("LAPLACE_SEAT_ID", ""),
                thread_id=os.environ.get("CODEX_THREAD_ID", ""),
                attention_projection={"status": "CLEAR", "pending": []},
            )
            print(json.dumps(turn_hook_response({}, turn), separators=(",", ":")))
            return 0
        if classification == "LEGACY-INERT":
            projection = {
                "status": "LEGACY-PROMPT-INERT",
                "attention_classification": classification,
            }
        else:
            seat_id = _bound_seat_id(
                watcher_prompt=classification == "OPAQUE-TOKEN-CANDIDATE"
            )
            if seat_id is None:
                if classification == "OPAQUE-TOKEN-CANDIDATE":
                    projection = {
                        "status": "STALE-PROMPT-INERT",
                        "attention_classification": "UNBOUND-TASK-INERT",
                        "reason": "watcher token has no exact current canonical seat/task binding",
                    }
                else:
                    projection = {
                        "status": "UNCLAIMED",
                        "seat_id": None,
                        "reason": "this provider task has no exact bound logical seat",
                    }
            else:
                currentness = (
                    codex_seat_watcher.attention_prompt_currentness(
                        prompt,
                        seat_id=seat_id,
                        thread_id=os.environ.get("CODEX_THREAD_ID", "").strip(),
                    )
                    if classification == "OPAQUE-TOKEN-CANDIDATE" else None
                )
                if currentness is not None and not currentness["actionable"]:
                    projection = {
                        "status": "STALE-PROMPT-INERT",
                        "attention_classification": currentness["state"],
                        "reason": "; ".join(currentness.get("reasons", [])),
                    }
                else:
                    frontier = atlas_bridge.seat_mail_observation(
                        seat_id=seat_id, previous_mail_token=None
                    )
                    projection = project_attention_from_mail_frontier(
                        frontier,
                        seat_id=seat_id,
                        watcher=codex_seat_watcher.projection(seat_id),
                    )
                    if currentness is not None and projection.get("status") == "CLEAR":
                        projection = {
                            "status": "STALE-PROMPT-INERT",
                            "attention_classification": "CANONICALLY-CLEAR-INERT",
                            "reason": "the current recipient frontier has no obligation",
                        }
    except Exception as exc:  # noqa: BLE001 - absence is returned as typed hook data
        event = locals().get("event", {})
        if locals().get("classification") in {"LEGACY-INERT", "OPAQUE-TOKEN-CANDIDATE"}:
            projection = {
                "status": "STALE-PROMPT-INERT",
                "attention_classification": "BINDING-UNAVAILABLE-INERT",
                "reason": f"{type(exc).__name__}: {exc}",
            }
        else:
            projection = {
                "status": "UNAVAILABLE",
                "reason": f"{type(exc).__name__}: {exc}",
            }
    base = hook_response(event, projection)
    turn = reconstruct_turn(
        ROOT,
        event_name=str(event.get("hook_event_name") or "UserPromptSubmit"),
        prompt=str(event.get("prompt") or event.get("user_prompt") or ""),
        function=os.environ.get("LAPLACE_FUNCTION", ""),
        seat_id=os.environ.get("LAPLACE_SEAT_ID", ""),
        thread_id=os.environ.get("CODEX_THREAD_ID", ""),
        attention_projection=projection,
    )
    print(json.dumps(turn_hook_response(base, turn), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
