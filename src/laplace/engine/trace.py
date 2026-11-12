"""trace.py — the journal act/step tree reader (front door M1). No HTTP dependency.

``contract/journal.jsonl`` is already a span log with explicit parents and explicit
close events (act_begin / step begin–done pairs / bank rows / act_end), banked
kill-safe. The waterfall therefore needs NO new instrumentation — only this reader.
Verified row shapes (2026-08-24, the critic's correction folded in — four record
classes, not one):

  act          {record, act_id, act, manifest, pid, ts, note?}
  step         {record, act_id, index, name, phase: begin|done, ts, seconds?}
  bank         {record, act_id|null, store, row_id, phase, ts}
  act_end      {record, act_id, status, ts}
  adjudication {record, act_id, status, note, ts}

Reader laws (interaction spec s3.4):
  * orphans attach loudly, never dropped — a ``done`` with no ``begin`` renders with
    an ORPHAN chip; a bank with a null act_id groups under ``(ambient)``;
  * in-flight vs dead are DIFFERENT glyphs — an open act's pid is checked against
    /proc, because "running" and "died mid-act" must never share a rendering;
  * bank rows hang under their act as artifacts, clickable to the record — the
    provenance edge the surveyed family generally lacks and this engine gets free.

Read-only: this module writes nothing, ever.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from laplace.engine import rows as _rows

AMBIENT = "(ambient)"


def _ts(value: Any) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _pid_alive(pid: Any) -> bool:
    try:
        return Path(f"/proc/{int(pid)}").exists()
    except (TypeError, ValueError):
        return False


def acts(limit: int = 40) -> list[dict[str, Any]]:
    """The act list, newest first: one summary line per act_id."""
    return _read()[:max(1, limit)]


def act_tree(act_id: str) -> dict[str, Any] | None:
    """One act's full tree: paired steps with durations, banks as artifacts, orphans."""
    for a in _read(full_for=act_id):
        if a["act_id"] == act_id:
            return a
    return None


def _read(full_for: str | None = None) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}

    def group(act_id: Any) -> dict[str, Any]:
        key = str(act_id) if act_id else AMBIENT
        if key not in groups:
            groups[key] = {"act_id": key, "act": None, "pid": None, "start": None,
                           "end": None, "status": None, "steps": [], "banks": [],
                           "orphans": [], "adjudications": [], "regions": [],
                           "first_off": None}
        return groups[key]

    for off, row in _rows.scan("journal"):
        rec = row.get("record")
        g = group(row.get("act_id"))
        if g["first_off"] is None:
            g["first_off"] = off
        t = _ts(row.get("ts"))
        if rec == "act":
            g["act"] = row.get("act")
            g["pid"] = row.get("pid")
            g["start"] = t
            g["regions"] = list(row.get("authority_regions") or [])
        elif rec == "act_end":
            g["end"] = t
            g["status"] = row.get("status")
        elif rec == "adjudication":
            g["adjudications"].append({"status": row.get("status"),
                                       "note": row.get("note"), "ts": row.get("ts")})
        elif rec == "step":
            # steps are SPANS, not slots: a real act re-runs the same named step (a
            # retry, a loop, a second pass) and every run is its own row. Keying by
            # (index, name) overwrote the first — a COMPLETED span silently dropped,
            # and the waterfall then lied about what ran (the review's finding,
            # 2026-08-24). Append on begin; close the most recent still-open match.
            phase = row.get("phase")
            if phase == "begin":
                g["steps"].append({"index": row.get("index"), "name": row.get("name"),
                                   "begin": t, "end": None, "seconds": None,
                                   "offset": off})
            elif phase == "done":
                key = (row.get("index"), row.get("name"))
                step = next((s for s in reversed(g["steps"])
                             if (s["index"], s["name"]) == key and s["end"] is None),
                            None)
                if step is None:
                    g["orphans"].append({"kind": "step-done-without-begin",
                                         "name": row.get("name"),
                                         "index": row.get("index"),
                                         "ts": row.get("ts"), "offset": off})
                else:
                    step["end"] = t
                    step["seconds"] = row.get("seconds")
        elif rec == "bank":
            if row.get("phase") == "done":
                g["banks"].append({"store": row.get("store"),
                                   "row_id": row.get("row_id"),
                                   "ts": row.get("ts"), "offset": off})

    out: list[dict[str, Any]] = []
    for key, g in groups.items():
        start, end = g["start"], g["end"]
        open_act = end is None and key != AMBIENT
        alive = _pid_alive(g["pid"]) if open_act else False
        state = ("done" if not open_act else ("in-flight" if alive else "died"))
        # sorted() is stable: index orders the waterfall, and repeated spans of one
        # index keep the order they began in.
        steps = sorted(g["steps"], key=lambda s: (s["index"] or 0))
        for s in steps:
            if s["begin"] is not None and s["end"] is not None:
                s["duration_s"] = round(s["end"] - s["begin"], 3)
            elif s["seconds"] is not None:
                s["duration_s"] = s["seconds"]
            else:
                s["duration_s"] = None
            s["open"] = s["end"] is None
        summary = {
            "act_id": key, "act": g["act"] or (AMBIENT if key == AMBIENT else "?"),
            "pid": g["pid"], "state": state, "status": g["status"],
            "start": start, "end": end,
            "duration_s": (round(end - start, 3)
                           if start is not None and end is not None else None),
            "authority_regions": list(g["regions"]),
            "n_steps": len(steps), "n_banks": len(g["banks"]),
            "n_orphans": len(g["orphans"]),
        }
        if full_for and key == full_for:
            summary["steps"] = steps
            summary["banks"] = g["banks"]
            summary["orphans"] = g["orphans"]
            summary["adjudications"] = g["adjudications"]
        out.append(summary)
    out.sort(key=lambda a: a["start"] or 0, reverse=True)
    return out
