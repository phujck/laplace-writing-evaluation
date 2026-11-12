"""custody_mode.py - the one switch for the custody/fabric layer.

His ruling, 2026-09-14, verbatim: "just switching off custody until we're ready to reintegrate
it." The layer - seat fabric, leases, watchers, the recovery coordinate, the startup mail gate,
turn reconstruction's root-seat resolution - was built 2026-08-20..28 for a three-seat Codex
triad that died on 2026-08-28. Every consumer that gated or dominated on it since has refused
against nothing: the close's custody step (FAIL: receipt disagrees with commit-shaped authority),
the wake's grade-0 top (three of four components UNCLAIMED / INVALID / dead leases), the startup
wall, turn reconstruction's FOG. Same disease as the replacement next door, at lower speed.

This module is the ONE reader and the ONE writer of the mode. Rows, never a flag file: the mode is
an append-only typed row in ``contract/custody_mode.jsonl`` banked through the journal, and the
LATEST nonempty declaration wins. Missing or malformed declarations mean OFF: cold recovery must
not revive obsolete holders. Reintegration requires an explicit valid ON declaration.
Nothing is deleted; the layer stays in the tree and in the
fold. What changes is what GATES:

  * ``laplace.engine.wake``          - seat_fabric, recovery_coordinate, development_work_map,
                                turn_reconstruction, successor_profile render as one stub each
                                (``stub``), and their live glows are not computed.
  * ``scripts/sewup.py``      - the custody step is not manifested in a close; ``--only custody``
                                answers INERT, not FAIL.
  * ``laplace.engine.turn_reconstruction`` - returns status CUSTODY-OFF instead of resolving a root seat.
  * ``.claude/hooks/session-start.mjs`` - prints one line instead of the mail-gate wall.

Historical custody records remain available for inspection. Reintegration is an explicit
operator decision, not a fixed seat count or an automatic close-count trigger.

``LAPLACE_CUSTODY_LIVE=1`` forces the live paths for diagnosis without moving the row.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

STORE = "contract/custody_mode.jsonl"
CRUTCH = "CR-20260914-custody-off"
MODES = ("ON", "OFF")
_CONSUMERS = ("laplace.engine.wake", "scripts/sewup.py", "laplace.engine.turn_reconstruction",
              ".claude/hooks/session-start.mjs")


def _root(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root).resolve()
    return source_tree()


def _forced_live() -> bool:
    return os.environ.get("LAPLACE_CUSTODY_LIVE", "").strip().lower() in ("1", "true", "yes")


def read(root: Path | str | None = None) -> dict[str, Any]:
    """Explicit valid mode, with the retired layer OFF on missing or malformed input."""
    path = _root(root) / STORE
    last: dict[str, Any] | None = None
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                last = None
                continue
            if isinstance(row, dict) and row.get("record") == "custody-mode" and row.get("mode") in MODES:
                last = row
            else:
                last = None
    if last is None:
        return {"mode": "OFF", "source": f"default (no valid declaration in {STORE})",
                "reason": "custody remains retired until explicitly reintegrated", "forced_live": _forced_live(),
                "crutch": CRUTCH, "consumers": list(_CONSUMERS)}
    return {**last, "source": STORE, "forced_live": _forced_live(), "consumers": list(_CONSUMERS)}


def is_off(root: Path | str | None = None) -> bool:
    mode = read(root)
    return mode["mode"] == "OFF" and not mode["forced_live"]


def stub(component: str, root: Path | str | None = None) -> dict[str, Any]:
    """What a consumer renders in place of a live custody glow while the mode is OFF."""
    mode = read(root)
    return {
        "status": "CUSTODY-OFF",
        "component": component,
        "since": mode.get("since"),
        "by": mode.get("by"),
        "reason": mode.get("reason"),
        "reintegration_trigger": mode.get("reintegration_trigger"),
        "crutch": CRUTCH,
        "authority_effect": "none",
        "read_only": True,
        # --account returns before wake_payload: it reads local obligation evidence without
        # resolving provider holders or binding watchers. A forced-live wake is an activation
        # path, not a lawful continuation of this read-only diagnostic.
        "descend": "scripts/laplace-python scripts/wake.py --account",
    }


def set_mode(root: Path | str | None, mode: str, *, by: str, reason: str,
             reintegration_trigger: str) -> dict[str, Any]:
    """Bank one mode row through the journal. The latest row is the mode."""
    if mode not in MODES:
        raise ValueError(f"custody mode must be one of {MODES}; got {mode!r}")
    if not (by.strip() and reason.strip() and reintegration_trigger.strip()):
        raise ValueError("a custody-mode row names who, why, and the reintegration trigger")
    from laplace.core.records import journal

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    row = {
        "record": "custody-mode",
        "id": f"CUSTODY-{mode}-{stamp}",
        "mode": mode,
        "since": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "by": by,
        "reason": reason,
        "reintegration_trigger": reintegration_trigger,
        "crutch": CRUTCH,
    }
    journal.bank_row(STORE, row, root=_root(root))
    return row


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--set" in argv:
        i = argv.index("--set")
        mode = argv[i + 1] if i + 1 < len(argv) else ""

        def _opt(flag: str) -> str:
            return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else ""

        row = set_mode(None, mode.upper(), by=_opt("--by"), reason=_opt("--reason"),
                       reintegration_trigger=_opt("--trigger"))
        print(json.dumps(row, ensure_ascii=False, indent=1))
        return 0
    print(json.dumps(read(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
