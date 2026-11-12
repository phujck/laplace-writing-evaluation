#!/usr/bin/env python3
"""The lane's replay worker: the harness worker's protocol, plus the VERB DOOR.

Why this file exists at all.  ``harness/_worker.py:137`` is
``result = wt.execute(root, project, mode, operation, payload, turn_id)`` and nothing else:
the oracle drives every corpus row by OPERATION NAME.  The brief's test is "replay.py parity
over the whole corpus through BOTH the old names and the new verbs", and the rebuild-and-compare
inside ``execute`` is not that test -- it proves the owner receives the same pair, and never
exercises ``writing_tools.request()``, the door a caller would use.  The harness is shared with
three sibling lanes and is not this lane's to edit, so the second door is driven from here.

The protocol is the harness's, so ``_harness.Side`` can drive this worker unchanged:
one JSON request per line on stdin, one JSON answer per line on the protocol fd.

  {"op": "execute", project, mode, operation, payload, with_turn}   -- the old name
  {"op": "request", project, mode, verb, concept, target, expected, payload, by, with_turn}
                                                                   -- the verb door

Both answer the same five fields the oracle compares on (``ok``, ``class``, ``value``,
``home``, ``home_chain``), with ``class`` in the same four values
(read / applied / banked / refused), so one comparison covers both doors.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

HARNESS = Path("/home/phujck/VScodeProjects/laplace/evidence/"
               "WRITING_RECONCILIATION_2026-10-02/harness")

# The protocol fd, taken before anything can write to stdout -- identical to the harness
# worker's own first act (harness/_worker.py:40-42), and for the same reason: the owner
# package prints warnings, and a warning on the protocol channel kills the run.
_PROTOCOL = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
os.dup2(2, 1)
sys.stdout = os.fdopen(os.dup(2), "w", buffering=1, encoding="utf-8")


def emit(payload: dict) -> None:
    _PROTOCOL.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    _PROTOCOL.flush()


def owner_home(exc: BaseException, root: Path) -> tuple[str | None, list[str]]:
    """The innermost owner frame, and the whole owner chain, as file:line.

    The harness's definition (``harness/_worker.py:50``), copied rather than imported so the
    two workers cannot drift apart silently; ``test_writing_verbs.py`` asserts the two
    functions agree on one constructed traceback.
    """
    chain: list[str] = []
    for frame in traceback.extract_tb(exc.__traceback__):
        path = Path(frame.filename)
        parts = path.parts
        if "laplace" not in parts:
            continue
        index = len(parts) - 1 - parts[::-1].index("laplace")
        rel = "/".join(parts[index:])
        chain.append(f"src/{rel}:{frame.lineno}")
    return (chain[-1] if chain else None), chain


def classify(operation: str, payload: dict, result, reads: set, writes: set) -> str:
    """read / applied / banked, for a call that did not raise (harness/_worker.py:64)."""
    if operation in reads and operation not in writes:
        return "read"
    if isinstance(result, dict):
        if result.get("applied") in (None, False) and (
                result.get("pending") or result.get("proposal_id") or result.get("feedback_id")
                or str(result.get("status") or "").lower() in {"pending", "queued", "banked"}):
            return "banked"
        if result.get("reused"):
            return "applied"
    return "applied"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--turns", default="{}")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    turns = json.loads(args.turns or "{}")

    sys.path.insert(0, str(HARNESS))
    import _netcache
    netcache = _netcache.install_from_env(
        label="verbworker-" + os.environ.get("LAPLACE_HARNESS_SIDE", "?"))
    print(f"netcache: {netcache}", file=sys.stderr, flush=True)

    try:
        from laplace.native import tools as wt
        from laplace.writing import reads as reads_owner
        from laplace.core import grammar as g
        from laplace.native import verbs as v
        reads, writes = set(reads_owner.READS), set(reads_owner.WRITES)
        emit({"ready": True, "operations": len(reads | writes),
              "reads": len(reads), "writes": len(writes)})
    except Exception as exc:
        emit({"ready": False, "error": f"{type(exc).__name__}: {exc}",
              "traceback": traceback.format_exc()[-3000:]})
        return 1

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:
            emit({"ok": False, "class": "refused", "value": None,
                  "error": f"bad request: {exc}", "error_type": "HarnessError",
                  "home": None, "home_chain": []})
            continue
        if req.get("op") == "__quit__":
            return 0
        project = str(req.get("project") or "")
        mode = str(req.get("mode") or "work")
        payload = req.get("payload") or {}
        turn_id = turns.get(project) if req.get("with_turn") else None

        if req.get("op") == "request":
            emit(_verb_door(wt, g, v, root, project, mode, req, turn_id, reads, writes))
            continue

        operation = str(req.get("operation") or "")
        try:
            result = wt.execute(root, project, mode, operation, payload, turn_id)
            if isinstance(result, dict) and (result.get("error") or result.get("ok") is False):
                out = {"ok": False, "class": "refused", "value": result,
                       "error": str(result.get("error") or "owner refusal"),
                       "error_type": "OwnerResponse", "home": "owner-response",
                       "home_chain": []}
            else:
                out = {"ok": True,
                       "class": classify(operation, payload, result, reads, writes),
                       "value": result, "error": None, "error_type": None,
                       "home": None, "home_chain": []}
        except BaseException as exc:
            home, chain = owner_home(exc, root)
            out = {"ok": False, "class": "refused", "value": None,
                   "error": str(exc), "error_type": type(exc).__name__,
                   "home": home, "home_chain": chain}
        emit(out)
    return 0


def _verb_door(wt, g, v, root: Path, project: str, mode: str, req: dict,
               turn_id, reads: set, writes: set) -> dict:
    """One corpus row entered through ``writing_tools.request()``.

    The answer is the grammar's receipt or refusal (GRAMMAR.md section 5), which is a
    DIFFERENT SHAPE from the legacy response on purpose -- so this worker reports the four
    things the oracle compares (class, home, the changed files, the bytes) and carries the
    grammar answer in ``value`` for the record.  ``request`` itself decides nothing the old
    name does not: it chooses the route, rebuilds the owner call, and calls ``execute``.
    """
    request = g.Request(verb=str(req.get("verb") or ""), concept=str(req.get("concept") or ""),
                        target=str(req.get("target") or project),
                        expected=tuple(req.get("expected") or ()),
                        payload=req.get("payload") or {}, by=str(req.get("by") or ""))
    try:
        route = v.choose(request.verb, request.concept, request.payload)
    except Exception as exc:
        # Not a refusal of the act: the verb door cannot reach this route at all, which the
        # route itself declares (door="shim", with Route.because). Reported, never scored.
        return {"ok": False, "class": "unreachable", "value": None, "error": str(exc),
                "error_type": type(exc).__name__, "home": None, "home_chain": []}
    try:
        answer = wt.request(root, project, mode, request, turn_id=turn_id)
    except BaseException as exc:
        home, chain = owner_home(exc, root)
        return {"ok": False, "class": "refused", "value": None, "error": str(exc),
                "error_type": type(exc).__name__, "home": home, "home_chain": chain,
                "door": "verb", "escaped": True}
    if not answer.get("ok"):
        refused = answer.get("refused") or {}
        owner = refused.get("owner") or {}
        return {"ok": False, "class": "refused", "value": answer,
                "error": str(refused.get("said") or ""), "error_type": "Refusal",
                "home": owner.get("raised"), "home_chain": owner.get("chain") or [],
                "door": "verb", "operation": owner.get("operation"),
                "needed": refused.get("needed"), "homes_named": refused.get("homes")}
    outcome = str(answer.get("outcome") or "")
    operation = ((answer.get("owner") or {}).get("operation")) or ""
    value = answer.get("owner_response")
    klass = ("read" if outcome == "read" else
             "banked" if outcome == "banked" else
             classify(operation, request.payload, value, reads, writes))
    if isinstance(value, dict) and (value.get("error") or value.get("ok") is False):
        return {"ok": False, "class": "refused", "value": value,
                "error": str(value.get("error") or "owner refusal"),
                "error_type": "OwnerResponse", "home": "owner-response", "home_chain": [],
                "door": "verb", "operation": operation}
    return {"ok": True, "class": klass, "value": value, "error": None, "error_type": None,
            "home": None, "home_chain": [], "door": "verb", "operation": operation,
            "banked_row": answer.get("banked_row")}


if __name__ == "__main__":
    raise SystemExit(main())
