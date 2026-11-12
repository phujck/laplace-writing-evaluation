#!/usr/bin/env python3
"""The seat mid-session mail watcher — self-armed at every wake, never by his hand.

The mailboy problem (his question at the 2026-08-24 close): the wake glow shows pending
mail at session START; this watcher covers MID-SESSION. Any session launches it as
a harness-tracked background task at wake (the session-start hook names the command); it
polls the canonical store every 20s and EXITS when a new cursor appears for its seat,
which re-invokes the session with the news. Read-only; the store stays the only cursor
owner; a refusing store is warned quietly and watched through.
Exit-on-change is the nudge mechanism — the harness re-invoke IS the delivery leg.

THE LOOP NAMES ITS OWN NEXT HALF (WO-20260824-fabric-pull-is-a-serve). arm -> fires ->
drain -> *manual* re-arm was jank held together by memory. Now the fire message carries the
exact drain command, and ``seat_fabric.py drain`` carries the exact re-arm command back, so
neither half of the cycle depends on anyone remembering the other. The seat is mandatory:
a watcher may never silently bind itself to another seat's mailbox.

Runtime law: /usr/bin/python3 (system + user site). The bridge refuses venv interpreters.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path("/home/phujck/VScodeProjects/laplace")
sys.path.insert(0, str(ROOT / "src"))

PY = "/usr/bin/python3"


def state_sig(seat_id: str) -> int:
    from laplace.representation import atlas_bridge as ab
    state = ab.snapshot()["provider"]
    # NEW CURSORS ONLY: status flips on already-seen mail are the drain doing its job,
    # not news — waking the session for them was measured churn (2026-08-24 19:0x ticks).
    return max((int(m["message"].get("cursor", 0))
                for m in state.get("messages", {}).values()
                if m["message"].get("recipient_seat_id") == seat_id), default=0)


def observed_state_sig(
    seat_id: str,
    previous_token: dict | None,
) -> tuple[dict, int | None]:
    """Materialise the provider face only when the O(1) causal tip moved."""

    from laplace.representation import atlas_bridge as ab

    observation = ab.provider_observation(previous_token=previous_token)
    if not observation["changed"]:
        return observation["drift_token"], None
    state = observation["provider"]
    cursor = max(
        (
            int(materialized["message"].get("cursor", 0))
            for materialized in state.get("messages", {}).values()
            if materialized["message"].get("recipient_seat_id") == seat_id
        ),
        default=0,
    )
    return observation["drift_token"], cursor


def drain_command(seat_id: str) -> str:
    return f"{PY} scripts/seat_fabric.py drain --seat {seat_id}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seat", required=True, help="recipient seat to watch")
    p.add_argument("--interval", type=int, default=20, help="poll seconds")
    p.add_argument("--hours", type=float, default=6.0, help="watch window")
    args = p.parse_args(argv)

    if args.seat == "codex-seat":
        from laplace.representation import codex_seat_watcher

        singleton = codex_seat_watcher.projection()
        if singleton.get("status") == "ACTIVE":
            print(
                "[fabric-watch] codex-seat manual watcher retired: wake-bound singleton "
                f"PID {singleton.get('pid')} is active",
                flush=True,
            )
            return 0

    deadline = time.time() + args.hours * 3600
    if time.time() >= deadline:
        baseline = state_sig(args.seat)
        print(f"[fabric-watch] baseline max cursor to {args.seat}: {baseline}", flush=True)
        print(f"[fabric-watch] {args.hours:g}h window closed with no change", flush=True)
        return 0

    observed_token, initial_cursor = observed_state_sig(args.seat, None)
    assert initial_cursor is not None  # previous_token=None always materialises once
    baseline = initial_cursor
    print(f"[fabric-watch] baseline max cursor to {args.seat}: {baseline}", flush=True)
    while time.time() < deadline:
        time.sleep(args.interval)
        try:
            observed_token, changed_cursor = observed_state_sig(args.seat, observed_token)
            if changed_cursor is None:
                continue
            now = changed_cursor
        except Exception as exc:  # noqa: BLE001 - report and keep watching
            print(f"[fabric-watch] snapshot error (kept watching): {exc}", flush=True)
            continue
        if now > baseline:
            print(f"[fabric-watch] NEW {args.seat} mail: cursor {baseline} -> {now}", flush=True)
            print(f"[fabric-watch] exiting so the session gets nudged. ONE ACT NEXT (it drains "
                  f"AND hands back the re-arm): {drain_command(args.seat)}", flush=True)
            return 0
    print(f"[fabric-watch] {args.hours:g}h window closed with no change", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
