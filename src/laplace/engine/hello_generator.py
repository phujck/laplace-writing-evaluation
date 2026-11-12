"""hello_generator.py - the hello, reconstructed by a swarm of cheap Haiku agents.

The distributed reconstruction of the orientation, on Eigen first. ``self_corpus`` reconstructs the
GRADED self (the data, deterministic); this module shatters that reconstruction into one tiny SLICE
per orientation dimension and prepares a brief for each, so a swarm of sealed "stupid little haiku"
agents can each generate ONE fragment of the briefing from ONE slice. The codec's *distributed
code*: no single agent holds the orientation - the JOINT of the swarm reconstructs it. ``compose``
assembles the fragments into the five-point hello.

The engine pattern (``grade_probe``, ``adjudicate_sealed``): the SCRIPT is pure and prepares the
briefs; the ORCHESTRATOR spawns the swarm (builder != judge), here a Haiku fan-out via the workflow
``hello-generator``. The bet under test, next session: cheap PARALLEL reconstruction + a single read
of the composed briefing orients the next Opus instance FASTER than a serial five-file linear read.

The slices are written to their own files so the swarm's args stay small - pointers, not payloads -
and so each Haiku reads only its own slice (the context firewall: a reader sees one bounded slice).

Usage:
    python -m laplace.engine.hello_generator prepare [--cache DIR]    # -> manifest JSON; writes slice files
    # orchestrator: spawn one Haiku per manifest row; each reads its path, applies its ask -> fragment
    echo '{"fragments":[...]}' | python -m laplace.engine.hello_generator compose   # -> the composed hello
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from laplace.engine.self_corpus import reconstruct_self

_CACHE = Path("corpus_stores") / "hello_cache"
_SLICE_CAP = 6000


def _briefs(repo_root: Path) -> list[dict[str, str]]:
    """The swarm's work items: (dimension, slice, ask) - one tiny reconstruction each.

    Shatters the grade-0 fixed point (the aim, the live forks) and the grade-1 delta (the latest
    hand-off) into per-dimension slices. One Haiku per slice; the forks fan out one-per-fork, so the
    swarm is genuinely little and parallel.
    """
    g0 = reconstruct_self(repo_root, 0)
    g1 = reconstruct_self(repo_root, 1)
    s0 = {s["shard"]: s for s in g0.get("shards", [])}
    s1 = {s["shard"]: s for s in g1.get("shards", [])}
    out: list[dict[str, str]] = []
    if "next-aim" in s0:
        out.append({"dimension": "where_and_next", "slice": s0["next-aim"]["body"][:_SLICE_CAP],
                    "ask": "In <=70 words: where the project stands and the single next move. "
                           "Flat statement, no preamble, no hedging."})
    if "latest-handoff" in s1:
        out.append({"dimension": "since_last_close", "slice": s1["latest-handoff"]["body"][:_SLICE_CAP],
                    "ask": "In <=60 words: what changed or shipped last session. Factual, flat, no preamble."})
    if "live-forks" in s0:
        for row in s0["live-forks"]["body"].splitlines():
            row = row.strip()
            if row.startswith("| F"):
                out.append({"dimension": "blocked_on_author", "slice": row,
                            "ask": "In <=25 words: restate this as the single crisp decision the author "
                                   "must make. Imperative, just the decision - no restating the context."})
    return out


def prepare(repo_root: Path | str, cache_dir: Path | str | None = None) -> list[dict[str, str]]:
    """Reconstruct the self, shatter it into per-dimension slice files, return the manifest.

    Returns ``[{dimension, path, ask}]`` - the small manifest the orchestrator fans the Haiku swarm
    over (no slice payloads ride in the manifest; each Haiku reads its own ``path``).
    """
    repo_root = Path(repo_root)
    cache = Path(cache_dir) if cache_dir else (repo_root / _CACHE)
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)
    cache.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    for i, b in enumerate(_briefs(repo_root)):
        p = cache / f"brief_{i:02d}_{b['dimension']}.txt"
        p.write_text(b["slice"], encoding="utf-8")
        manifest.append({"dimension": b["dimension"], "path": str(p), "ask": b["ask"]})
    return manifest


def compose(fragments: list[dict[str, str]]) -> str:
    """Assemble the swarm's fragments into the five-point hello briefing (deterministic - the
    composition is structure, not another generation; the swarm did the reconstruction)."""
    by_dim: dict[str, list[str]] = defaultdict(list)
    for f in fragments or []:
        t = (f.get("text") or "").strip()
        if t:
            by_dim[f.get("dimension", "")].append(t)
    out = ["# Hello - orientation reconstructed by the Haiku swarm\n"]
    if by_dim["where_and_next"]:
        out.append("**Where we are / the next move.** " + " ".join(by_dim["where_and_next"]))
    if by_dim["since_last_close"]:
        out.append("**Since last close.** " + " ".join(by_dim["since_last_close"]))
    if by_dim["blocked_on_author"]:
        out.append("**Blocked on you:**\n" + "\n".join(f"- {t}" for t in by_dim["blocked_on_author"]))
    out.append("**Live probe (at-grade).** Run `git status` (cheap, always); if the tree is clean and HEAD "
               "is the last banked-green commit, INHERIT green / canon-healthy from the fixed point - do not "
               "re-run `pytest -q` or the flat canon walk. Re-derive only on contradiction, and scoped "
               "(`laplace_verify(focus=...)`, the changed test shard). A contradiction with the above is the "
               "highest-signal find, and the trigger to fall back to the linear read.")
    out.append("**How to close.** `sew up` runs the close ritual and banks the trace.")
    return "\n\n".join(out)


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    cmd = argv[0] if argv else ""
    repo_root = source_tree()
    if cmd == "prepare":
        cache = argv[argv.index("--cache") + 1] if "--cache" in argv else None
        print(json.dumps(prepare(repo_root, cache), ensure_ascii=False, indent=2))
        return 0
    if cmd == "compose":
        data = json.load(sys.stdin)
        frags = data.get("fragments", []) if isinstance(data, dict) else data
        print(compose(frags))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
