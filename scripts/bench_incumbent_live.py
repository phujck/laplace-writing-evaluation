#!/usr/bin/env python3
"""bench_incumbent_live.py - the DEPLOYED system measured as-is, as a declared external reference.

    PYTHONPATH=src python3 scripts/bench_incumbent_live.py \\
        --bundle atlas/bench/tasks/<hex>/tasks.json \\
        --out atlas/bench/runs/<date>/incumbent-live

WHAT THIS IS, AND WHY IT IS NOT AN ARM. The atlas bench's ``incumbent_arch`` arm reproduces the
engine's ARCHITECTURE over the frozen snapshot: same universe, same tasks, same scorer, same
counted budget as every other arm. That is the fair comparison, and it is the one that belongs in
the table. This script is the other thing - the engine's ACTUAL production descent, run against
the same task questions, with none of the fairness constraints:

  * it descends the LIVE ``.meaning_tree.json``, which is folded over the working tree, not over
    the frozen snapshot the arms share;
  * that tree includes SEALED-DERIVED material - the soul is folded in vector-only - which no arm
    in the fair table is permitted to see;
  * its corpus is whatever the working tree holds right now, so its universe is neither
    ``bench-filtered/2`` nor any other declared view.

Every one of those is a real advantage and none of them is available to the arms. So the number
this produces is emitted as a DECLARED EXTERNAL REFERENCE: the summary prints it beside the fair
table, labelled, and never ranks it inside. "Our system as deployed, measured as-is" is a useful
thing to know and a dishonest thing to rank.

THE SEAL. This file imports ``laplace`` and NEVER ``atlas`` - ``tests/test_atlas_seal.py`` walks
``scripts/**`` and enforces exactly that, with an allowlist that is empty until Phase 7. The task
bundle is read as DATA (a JSON file path), which is the same one-way arrangement
``scripts/export_atlas_snapshot.py`` uses in the other direction.

THE PROTOCOL is v1 arm A's, and it is IMPORTED from ``scripts/reconstruction_bench.py`` rather
than re-implemented: the same ``score``, the same normalizer, the same 32 KB per-file read cap,
the same three whole-file opens, the same two rounds at beam 8 then 16. Re-implementing it here
would produce a second instrument and make any difference unattributable.

``--with-wake`` IS THE DECOMPOSITION, and it is the reason this script runs twice. v1's arm A was
``wake+descend``: the grade-0 wake payload was the arm's BASE CONTEXT and the descent added to it.
Run without the wake, this script measures the retrieval path alone; run with it, it measures what
the deployed system actually puts in front of a session. The difference between the two runs is
the wake's contribution, as a number - which is exactly the quantity Phase 3's pre-registered stop
is about. Reporting only one of them would leave "the engine's advantage is the wake" as an
inference; reporting both makes it a measurement, in whichever direction it falls.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

# The v1 arm-A protocol and the v1 scorer, imported so there is exactly one of each.
from reconstruction_bench import (  # noqa: E402
    A_FILE_READ_CAP,
    MAX_WHOLE_READS,
    CountingLeafSource,
    score,
)

DEFAULT_BEAM = 8
DEFAULT_K = 10
ROUNDS = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                          text=True).stdout.strip()


def hit_text(dsc, hit_id: str, open_file: bool) -> str:
    """What a reconstructing agent reads after a descent hit. Ported from v1 ``hit_text``.

    Top hits get the real repository file under a read-with-limit; the rest contribute their leaf
    digest, which is the skim a reader does over the tail of a hit list.
    """
    path = REPO / hit_id.split("#")[0]
    if open_file and path.is_file():
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:A_FILE_READ_CAP] if len(text.encode("utf-8")) > A_FILE_READ_CAP else text
    try:
        return dsc.leaf_source(hit_id) or ""
    except Exception:                                    # noqa: BLE001 - a missing leaf is data
        return ""


def run_wake() -> tuple[str, int]:
    """The grade-0 wake payload, as v1 arm A used it: the arm's BASE CONTEXT, charged in full."""
    proc = subprocess.run([sys.executable, "scripts/wake.py", "--grade", "0"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    out = proc.stdout or ""
    return out, len(out.encode("utf-8"))


def run_task(dsc, counter, task: dict, beam: int, k: int, wake: str = "") -> dict:
    """One task through the real descent under the arm-A read protocol. Everything counted."""
    atoms, window = task["atoms"], task.get("window")
    context = wake
    packets: list[dict] = []
    files_opened: list[str] = []
    started = time.perf_counter()
    bytes_at_start = counter.bytes

    for round_no in range(1, ROUNDS + 1):
        b = beam * (2 ** (round_no - 1))
        packet = dsc.descend(task["question"], k=k, beam=b)
        context += "\n" + json.dumps(packet, ensure_ascii=False, default=str)
        # The skim: every hit's digest first.
        for hit in packet["hits"]:
            context += "\n" + hit_text(dsc, hit["id"], open_file=False)
        # The opens: top hits whole, stopping as soon as the atoms are present.
        for hit in packet["hits"][:MAX_WHOLE_READS]:
            if score(context, atoms, window)[0]:
                break
            context += "\n" + hit_text(dsc, hit["id"], open_file=True)
            files_opened.append(hit["id"])
        packets.append({
            "round": round_no, "beam": b, "k": k,
            "materialized": packet.get("materialized"),
            "seconds": packet.get("seconds"),
            "top_hits": [h["id"] for h in packet["hits"][:5]],
        })
        if score(context, atoms, window)[0]:
            break

    seconds = time.perf_counter() - started
    correct, offset = score(context, atoms, window)
    context_bytes = len(context.encode("utf-8"))
    return {
        "task": task["task_id"],
        "class": task["task_class"],
        "correct": bool(correct),
        "first_hit_offset": offset,
        "rounds": len(packets),
        "tokens_context": context_bytes // 4,
        # tokens_touched is the LEAF-SOURCE bytes the descent served plus the whole files the
        # protocol opened - the same "everything that entered context" definition the arms use.
        "tokens_touched": context_bytes // 4,
        "leaf_source_bytes": counter.bytes - bytes_at_start,
        "files_opened": files_opened,
        "whole_file_reads": len(files_opened),
        "seconds": round(seconds, 3),
        "packets": packets,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="run the REAL production descent over frozen tasks")
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--beam", type=int, default=DEFAULT_BEAM)
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--with-wake", action="store_true",
                    help="prepend the grade-0 wake payload as base context, as v1 arm A did")
    args = ap.parse_args(argv)

    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    tasks = bundle["tasks"]

    from laplace.engine import recursive_read

    counter = CountingLeafSource(recursive_read.SelfGradedLeafSource(REPO))
    try:
        dsc = recursive_read.open_descender(REPO, leaf_source=counter)
    except Exception as exc:                             # noqa: BLE001 - named, never substituted
        print(f"REFUSED the live descender did not open: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 1

    started_ts = _now()
    wake, wake_bytes = ("", 0)
    if args.with_wake:
        wake, wake_bytes = run_wake()
        if not wake.strip():
            print("REFUSED the wake produced no payload; a wake arm with an empty base context "
                  "would measure the descent and be labelled the wake", file=sys.stderr)
            return 1
        print(f"# wake payload {wake_bytes:,} B ({wake_bytes // 4:,} tok) charged to every task")
    rows = [run_task(dsc, counter, task, args.beam, args.k, wake) for task in tasks]

    args.out.mkdir(parents=True, exist_ok=True)
    with open(args.out / "rows.jsonl", "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    correct = sum(1 for r in rows if r["correct"])
    manifest = {
        "kind": "incumbent-live-reference/1",
        "label": "incumbent-live-wake" if args.with_wake else "incumbent-live",
        "ranked_in_fair_table": False,
        "with_wake": bool(args.with_wake),
        "wake_payload_bytes": wake_bytes,
        "wake_payload_tokens": wake_bytes // 4,
        "provenance": (
            "the REAL production descent (laplace.engine.recursive_read.open_descender, beams "
            f"{args.beam} then {args.beam * 2}) over the LIVE .meaning_tree.json, under the v1 "
            "arm-A read protocol, against the frozen bundle's QUESTIONS"
            + (", WITH the grade-0 wake payload as base context (v1 arm A's 'wake+descend')"
               if args.with_wake else
               ", WITHOUT the wake payload - the retrieval path alone")
            + ". The live tree is folded over the working tree and includes sealed-derived "
              "stores (the soul is folded in vector-only) that no arm in the fair table may see."
        ),
        "universe": "live working tree (NOT the frozen snapshot; not a declared bench universe)",
        "bundle_id": bundle.get("bundle_id"),
        "bundle_path": str(args.bundle),
        "task_count": len(tasks),
        "correct": correct,
        "beam_rounds": [args.beam, args.beam * 2],
        "k": args.k,
        "read_protocol": {
            "file_read_cap_bytes": A_FILE_READ_CAP,
            "max_whole_file_reads": MAX_WHOLE_READS,
            "rounds": ROUNDS,
            "source": "scripts/reconstruction_bench.py (v1 arm A), imported not re-implemented",
        },
        "tree_file": ".meaning_tree.json",
        "commit_sha": _git("rev-parse", "HEAD"),
        "tree_dirty": bool(_git("status", "--porcelain")),
        "leaf_source_bytes_total": counter.bytes,
        "started_ts": started_ts,
        "finished_ts": _now(),
    }
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    print("# incumbent-live (EXTERNAL REFERENCE - not ranked in the fair table)")
    print(f"  correct           {correct}/{len(tasks)}")
    print(f"  leaf bytes served {counter.bytes:,}")
    print(f"  banked            {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
