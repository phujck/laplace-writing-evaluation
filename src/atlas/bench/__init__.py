"""bench - the reconstruction benchmark, v2: frozen bundles, declared arms, counted cost.

The v1 bench (``scripts/reconstruction_bench.py``, run 2026-07-28) measured live files. Its
headline arm lost half its correct answers overnight because the repository moved underneath the
frozen answer atoms - the same-day re-run is banked at
``evidence/reconstruction_bench_2026-07-29_baseline/`` and the two scores are quoted there, not
here. Bench v2 removes that defect at the root: every arm reads a content-addressed snapshot,
every answer atom is anchored to a span hash inside that snapshot, and the corpus and the ground
truth are covered by ONE identity (``BenchTaskBundle.bundle_id``) so the two cannot drift apart.

The module layout follows the order a run happens in:

    scoring.py    the ported v1 scorer - normalize, atom_positions, score, assert_no_leak
    universe.py   the declared filtered view over a snapshot, and the reading boundary
    cost.py       five cost dimensions, never summed, plus the counting wrappers
    protocol.py   ArmProtocol: what an arm is allowed to read, declared before it reads
    task.py       BenchTask v2 and BenchTaskBundle
    freeze.py     minting a bundle: every atom must resolve inside its anchor or nothing mints
    arms/         flat_read, grep_skilled, bm25, dense_flat
    runner.py     arms x tasks over one bundle, deterministic, rows.jsonl + manifest
    summary.py    recompute-and-assert; correctness table first, cost after
    figures.py    the three figures (matplotlib, the ``bench`` extra, imported lazily)

Two laws bind everything here. CORRECTNESS BEFORE COST: no cost number is printed, tabled or
plotted before the correctness table it belongs to, and cost is aggregated over correct tasks
only. THE SEED IS PART OF THE ARM: an arm is its versions plus its read protocol plus its seed
(``evidence/ATLAS_PHASE0_2026-08-01_agreement-gate.md``), and a gate threshold is evaluated at
the registered seed only - a number measured at another seed is a different measurement.
"""

from __future__ import annotations

#: The version of the whole bench contract: scorer, row shape, cost shape. It is folded into
#: every ``bundle_id``, so a scoring change cannot be replayed against an old bundle by accident.
BENCH_VERSION = "bench/2"

__all__ = ["BENCH_VERSION"]
