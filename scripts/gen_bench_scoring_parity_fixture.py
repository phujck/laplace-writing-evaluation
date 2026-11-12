#!/usr/bin/env python3
"""Generate the bench-scoring parity fixture by running the OLD (v1) scorer.

    python3 scripts/gen_bench_scoring_parity_fixture.py

This is the laplace side of a two-sided agreement check, and it works the way the atlas seal
requires: it produces DATA, not an import edge. It imports ``scripts/reconstruction_bench.py``
(the scorer that produced the 2026-07-28 numbers the deck serves), runs it over a seeded set of
randomized cases plus the 18 frozen v1 task atom sets, and writes every input with the OLD
scorer's verdict to ``atlas/tests/fixtures/scoring_parity_2026-07-28.json``.

The atlas-side test reads that file and asserts the ported scorer reproduces every verdict. So
the parity claim is checked rather than trusted, exactly as ``snapshot.verify`` recomputes the
exporter's ids - and the atlas package still imports nothing from here.

WHAT PARITY CAN AND CANNOT COVER, stated plainly because the limit is real. The banked
``evidence/reconstruction_bench_2026-07-28/rows.json`` stores per-row VERDICTS but not the arm
CONTEXTS that produced them, so no row of that run can be re-scored: the scorer's input is gone.
Parity is therefore proved on the inputs that ARE recoverable - randomized synthetic cases
exercising every branch of the scorer, and the 18 frozen atom sets replayed against constructed
haystacks - and the absence of contexts in the banked rows is asserted mechanically by the
atlas-side test rather than described in prose.

Regenerating is deterministic: same seed, same cases, byte-identical fixture.
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "atlas" / "tests" / "fixtures" / "scoring_parity_2026-07-28.json"
SEED = 20260728
CASES = 220


def load_v1_scorer():
    """Import the v1 bench module by path. Its heavy imports are all inside functions."""
    path = ROOT / "scripts" / "reconstruction_bench.py"
    spec = importlib.util.spec_from_file_location("_v1_bench", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load the v1 scorer at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WORDS = ["wake", "descent", "atlas", "span", "corpus", "ledger", "verdict", "seal", "fold",
         "beam", "anchor", "residual", "packet", "handoff", "register", "arm"]
#: Fragments chosen to exercise every normalizer branch: digit-group commas, the dash family,
#: emphasis marks, JSON escapes, tabs, casefold, whitespace collapse.
EDGES = ["12,335", "12335", "1,937", "0.835", "83.5%", "11.1x", "19.3x", "7/18", "14/18",
         "a‐b", "a‑b", "a‒b", "a–b", "a—b", "a―b", "a−b",
         "a-b", "**bold**", "`code`", "MiXeD CaSe", "line\\nbreak", "tab\\tsep",
         "quote\\\"inside", "  spaced   out  ", "1,234,567", "£2.5M", "0.0001s"]


def make_case(rng: random.Random, index: int) -> dict:
    """One randomized case: a haystack, an atom list (with any-of groups), and a window."""
    n_atoms = rng.randint(1, 4)
    atoms: list = []
    planted: list[str] = []
    for _ in range(n_atoms):
        if rng.random() < 0.35:
            members = [rng.choice(EDGES + WORDS) for _ in range(rng.randint(2, 3))]
            atoms.append(members)
            if rng.random() < 0.8:
                planted.append(rng.choice(members))
        else:
            atom = rng.choice(EDGES + WORDS)
            atoms.append(atom)
            if rng.random() < 0.75:
                planted.append(atom)

    filler = [rng.choice(WORDS) for _ in range(rng.randint(5, 60))]
    pieces: list[str] = []
    for i, word in enumerate(filler):
        pieces.append(word)
        if planted and rng.random() < 0.2:
            pieces.append(planted.pop(rng.randrange(len(planted))))
        if i % 7 == 6:
            pieces.append(rng.choice(["\n", "\t", "  ", " \n  "]))
    pieces.extend(planted)
    haystack = " ".join(pieces)
    if rng.random() < 0.3:
        haystack = haystack.upper()
    window = None if rng.random() < 0.45 else rng.choice([20, 50, 120, 300, 900])
    return {"case_id": f"R{index:04d}", "context": haystack, "atoms": atoms, "window": window}


def frozen_task_cases() -> list[dict]:
    """The 18 v1 atom sets, replayed against constructed haystacks that hit and that miss."""
    tasks = json.loads((ROOT / "scripts" / "reconstruction_bench_tasks.json").read_text())["tasks"]
    out: list[dict] = []
    for task in tasks:
        atoms = task["atoms"]
        if atoms == ["__LIVE_GIT__"]:
            continue
        members = []
        for atom in atoms:
            members.append(atom[0] if isinstance(atom, list) else atom)
        hit = " ... ".join(members)
        near = " ".join(members)
        miss = " ... ".join(members[:-1]) if len(members) > 1 else "nothing here at all"
        for label, ctx in (("hit", hit), ("tight", near), ("miss", miss)):
            out.append({"case_id": f"{task['id']}-{label}", "context": ctx,
                        "atoms": atoms, "window": task.get("window")})
        # the same atoms with the v1 window, padded so the proximity check can fail
        out.append({"case_id": f"{task['id']}-far",
                    "context": (" filler" * 400).join(members),
                    "atoms": atoms, "window": task.get("window") or 100})
    return out


def main() -> int:
    v1 = load_v1_scorer()
    rng = random.Random(SEED)
    cases = [make_case(rng, i) for i in range(CASES)] + frozen_task_cases()

    rows = []
    for case in cases:
        correct, offset = v1.score(case["context"], case["atoms"], case["window"])
        rows.append({**case,
                     "v1_normalized_len": len(v1.normalize(case["context"])),
                     "v1_correct": bool(correct), "v1_first_hit_offset": offset})

    # A direct normalizer fixture too: the scorer's verdict hides most of the normalizer's work.
    norm_rows = [{"raw": s, "v1_normalized": v1.normalize(s)} for s in EDGES + [
        "  A\tB\nC  ", "Digits 1,234 and 12,345 and 1,23", "**a** `b` c", "MIXED\\nCASE"]]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "record": "bench-scoring-parity-fixture/1",
        "generated_by": "scripts/gen_bench_scoring_parity_fixture.py",
        "v1_scorer": "scripts/reconstruction_bench.py (the 2026-07-28 run)",
        "seed": SEED,
        "case_count": len(rows),
        "covers": ("normalize, atom_positions, score (both the window=None path and the sliding "
                   "proximity path), any-of atom groups, and the digit-comma / dash-family / "
                   "emphasis / JSON-escape / casefold / whitespace edges of the normalizer"),
        "does_not_cover": ("row-level replay of the 2026-07-28 run: rows.json banks verdicts but "
                           "not the arm contexts, so the scorer's inputs for that run no longer "
                           "exist anywhere. The atlas-side test asserts that absence rather than "
                           "asserting the replay."),
        "normalize_cases": norm_rows,
        "score_cases": rows,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    hits = sum(1 for r in rows if r["v1_correct"])
    print(f"wrote {OUT}")
    print(f"score cases {len(rows)} ({hits} correct, {len(rows) - hits} incorrect)")
    print(f"normalize cases {len(norm_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
