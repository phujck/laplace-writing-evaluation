"""seed_from_gap.py - the residual -> next-grade adapter (R_residual -> R_hierarchy).

Hierarchialisation, made into a file handoff. The codec climbs a graded algebra one grade at a
time: a coarse grade is reconstructed first, then the finer grade is built *on* it. This script is
the handoff between the two. Given the reconstructed coarse grade (the ghost of grade k) and the
held-out coarse original, it computes the closure residual |r> - what the coarse reconstruction
could not carry, which is adjudicate's `lost` field - and prepends BOTH to the finer grade's blind
brief:

  * the reconstructed coarse grade, as the SCAFFOLD the fine grade is built on (not the original -
    we stay blind; the ghost's own coarse reconstruction is what carries up);
  * the residual |r>, as the named gap the finer grade must close.

This is the hierarchical arm's one new piece. The flat arm gets the base brief with no scaffold; the
hierarchical arm gets this seeded brief. The experiment is whether building the fine grade ON the
reconstructed coarse grade (+ its residual) beats jumping to it flat - hierarchialisation vs the
barren plateau, at one grade step. A *structured* residual recurses (it seeds the next grade's
descent); unstructured noise does not - that discriminator is the gate (judged downstream), not this
adapter's call. This script only threads the residual; it banks no telemetry (a transform, not a
reconstruction call).

Usage:
    python seed_from_gap.py <original_k.md> <ghost_k.md> <base_brief_k1.md> [--out seeded_brief.md]
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ADJ = _HERE.parent / "adjudicate.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def seed(original_k: str, ghost_k: str, base_brief_k1: str) -> tuple[str, dict]:
    """Prepend the coarse scaffold + residual |r> to the finer grade's blind brief.

    Returns (seeded_brief_text, coarse_verdict) so the caller can bank the coarse grade's own
    recurse signal - a low coarse similarity with a *named* lost set is a residual that should
    still seed the descent; an empty lost set with low similarity is noise.
    """
    adj = _load(_ADJ)
    r = adj.adjudicate(original_k, ghost_k)
    lost = ", ".join(r["lost"]) or "(none named)"
    seed_block = [
        "## the coarse grade, reconstructed (your scaffold - build the finer grade ON this)",
        "This is the level above, rebuilt blind from the same neighbourhood you have. Treat it as",
        "the established coarse description; your job is to close the *finer* grade it sits over,",
        "not to re-derive it. Where it is wrong, the residual below tells you where.",
        "",
        ghost_k.strip(),
        "",
        "## the residual |r> - what the coarse grade could not close (resolve these at this grade)",
        f"coarse-grade self-similarity: {r['similarity']}  (low + named lost = a structured residual",
        "that should recurse here; low + nothing named = noise the next grade cannot pick up)",
        f"lost (present in the coarse object, absent from its reconstruction): {lost}",
        "",
        "---",
        "",
    ]
    seeded = "\n".join(seed_block) + base_brief_k1.lstrip()
    return seeded, r


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) < 3:
        print(__doc__)
        return 2
    original_k = Path(args[0]).read_text(encoding="utf-8", errors="replace")
    ghost_k = Path(args[1]).read_text(encoding="utf-8", errors="replace")
    base = Path(args[2]).read_text(encoding="utf-8", errors="replace")
    out = argv[argv.index("--out") + 1] if "--out" in argv else str(Path(args[2]).with_name("seeded_brief.md"))

    seeded, r = seed(original_k, ghost_k, base)
    Path(out).write_text(seeded, encoding="utf-8")

    print(f"# Seeded the finer grade's brief from the coarse residual")
    print("*" * 50)
    print(f"coarse-grade similarity: {r['similarity']}   proxy fate: {r['proxy_fate']}")
    print(f"residual (lost): {', '.join(r['lost']) or '(none)'}")
    print(f"seeded brief -> {out}")
    print("Next: hand the seeded brief to the HIERARCHICAL ghost; the FLAT ghost gets the base brief.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
