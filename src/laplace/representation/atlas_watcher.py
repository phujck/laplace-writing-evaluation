"""Cheap persistent watcher process for the canonical Atlas conceptric.

The process holds no provider context and owns no queue.  Registrations, cursors, matches and
dispatch messages are all reconstructed from and appended to the one Atlas store on every pass.
Killing this process therefore loses no watcher state; a provider/model session is never kept
alive merely to poll.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import argparse
import json
import signal
import threading
from collections.abc import Sequence
from pathlib import Path

from laplace.representation import atlas_bridge
from laplace.core.runtime import require_system_runtime

REPO_ROOT = source_tree()


def _interval(default: float) -> float:
    watchers = atlas_bridge.snapshot()["provider"]["watchers"].values()
    intervals = [
        float(item["registration"]["poll_interval_seconds"])
        for item in watchers
    ]
    return default if not intervals else max(0.25, min(intervals))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="advance every watcher once and exit")
    parser.add_argument(
        "--idle-interval",
        type=float,
        default=2.0,
        help="seconds between passes when no registration asks for a shorter interval",
    )
    args = parser.parse_args(argv)
    if args.idle_interval < 0.25:
        parser.error("--idle-interval must be at least 0.25 seconds")

    require_system_runtime(REPO_ROOT)
    stop = threading.Event()

    def _stop(_signum: int, _frame: object) -> None:
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    while True:
        result = atlas_bridge.watch_all_once()
        print(json.dumps(result, sort_keys=True), flush=True)
        if args.once or stop.wait(_interval(args.idle_interval)):
            return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a real subprocess
    raise SystemExit(main())
