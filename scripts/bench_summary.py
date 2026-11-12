"""Recompute the served bench numbers from the frozen 2026-07-28 run.

The bench bundle (``evidence/reconstruction_bench_2026-07-28/``) is frozen
evidence: ``rows.json`` carries the per-task rows plus its own banked
``summary``/``headline`` blocks, and the README's environment line carries the
corpus size on the day of the run. Every function here recomputes from the
rows and then asserts agreement with the banked blocks — if the two split, the
recomputation is wrong, not the evidence.

Importable (no side effects); ``python3 scripts/bench_summary.py`` prints the
recomputed set for a human eye.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BENCH = REPO / "evidence" / "reconstruction_bench_2026-07-28"

# the four orientation classes (the wake's home ground); the other two classes
# (topic-descent, claim-evidence) are retrieval and ride the descent packets
ORIENTATION = ("current-aim", "standing-law", "session-state", "project-state")


def _data() -> dict:
    return json.loads((BENCH / "rows.json").read_text(encoding="utf-8"))


def run_meta() -> dict:
    d = _data()
    return {"date": d["date"], "head": d["head"].split()[0], "dirty": d["dirty"],
            "task_sha": d["task_file_sha256"]}


def corpus_leaves() -> int:
    m = re.search(r"tree of ([\d,]+) leaves",
                  (BENCH / "README.md").read_text(encoding="utf-8"))
    if not m:
        raise SystemExit("bench README lost its environment line (tree of N leaves)")
    return int(m.group(1).replace(",", ""))


def orientation() -> dict:
    """Per-arm correctness and per-question cost on the 12 orientation tasks."""
    d = _data()
    out = {}
    for arm in ("A", "B", "B+"):
        rows = [r for r in d["rows"] if r["arm"] == arm and r["class"] in ORIENTATION]
        toks = {r["tokens_context"] for r in rows}
        if len(rows) != 12 or len(toks) != 1:
            raise SystemExit(f"bench rows moved: arm {arm} orientation {len(rows)} rows, costs {toks}")
        out[arm] = {"correct": sum(1 for r in rows if r["correct"]),
                    "total": len(rows), "tokens": toks.pop()}
    s, h = d["summary"], d["headline"]
    if out["A"]["tokens"] != h["wake_tokens"] or out["A"]["tokens"] != s["A"]["median_tokens_correct"]:
        raise SystemExit("recomputed arm-A cost disagrees with the banked headline")
    if out["B"]["tokens"] != s["B"]["median_tokens_correct"] or out["B+"]["tokens"] != s["B+"]["median_tokens_correct"]:
        raise SystemExit("recomputed flat-set costs disagree with the banked summary")
    return out


def ratios() -> tuple[float, float]:
    o = orientation()
    return (round(o["B"]["tokens"] / o["A"]["tokens"], 1),
            round(o["B+"]["tokens"] / o["A"]["tokens"], 1))


def task_count() -> int:
    d = _data()
    tasks = {r["task"] for r in d["rows"]}
    if len(d["rows"]) != len(tasks) * 4:
        raise SystemExit("bench rows are not 4 arms per task")
    return len(tasks)


def touch() -> dict:
    """Documents materialized per retrieval query, over the run-day corpus."""
    d = _data()
    mats = [r["packet"]["materialized"] for r in d["rows"]
            if r["arm"] == "A" and r.get("packet")]
    if not mats:
        raise SystemExit("no arm-A descent packets in the bench rows")
    n = corpus_leaves()
    return {"lo": min(mats), "hi": max(mats), "leaves": n,
            "pct_lo": round(100 * min(mats) / n, 1),
            "pct_hi": round(100 * max(mats) / n, 1)}


if __name__ == "__main__":
    print("run:", run_meta())
    print("orientation:", orientation())
    print("ratios (B/A, B+/A):", ratios())
    print("tasks:", task_count())
    print("touch:", touch())
