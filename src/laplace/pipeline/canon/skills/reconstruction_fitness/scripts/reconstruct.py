"""reconstruct.py - the mechanical backing of reconstruction_fitness.

The *inverse* of digest.py. Given a digest (the partition skeleton transcript_digest
emitted), it assembles the **blind reconstruction packet** - the context-starved input a
reconstructor agent is given, and the ONLY thing it is given: the digest stubs and, for each
concept stub, where the level tender places it in the hierarchy. The packet deliberately omits
the raw transcript, because the whole test is whether the *digest* can rebuild the session -
"it can never live locally as just the full transcript; it's digested."

What is mechanical here (and lives in this script):
  * parse the digest skeleton into typed partitions;
  * run the level tender on each concept stub -> its placement (cluster, action, confidence),
    which is the fitness signal on *the level tender's organisation of the hierarchy*;
  * a cheap placement-confidence score (how many stubs land confidently vs. weakly - a weak
    placement is the confabulation risk, the confident-wrong retrieval);
  * write the blind packet (reconstruction_brief.md);
  * log a `reconstruction` telemetry event at summon time - the reinforcement record (which
    nodes/stubs this ghost *called*), banked every time, ahead of the fidelity verdict.

What stays judgement (host / a spawned blind agent, never this script):
  * the reconstruction itself - weave the ghost from the packet alone;
  * the fidelity verdict - compare the ghost to the archived original and call it
    faithful / partial / confabulated, then score it with
    `telemetry.reconstruction(fate=..., gap=...)`.

Usage:
    python reconstruct.py <digest-dir> [--corpus corpus/corpus.bib] [--out <brief.md>]
                          [--target <id>] [--no-log]
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
# .../laplace/src/laplace/pipeline/canon/skills/reconstruction_fitness/scripts/reconstruct.py
_SKILLS = _HERE.parents[2]                      # .../canon/skills
_REPO = _HERE.parents[6]                        # repo root (.../laplace)

# The level tender supplies the hierarchy-placement read; import it the way the tests do.
_LT = _SKILLS / "level_tender" / "scripts" / "level_tender.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _telemetry():
    """Import laplace.engine.telemetry, adding src/ to the path if the package is not installed."""
    try:
        from laplace.engine import telemetry  # type: ignore
        return telemetry
    except Exception:
        sys.path.insert(0, str(_REPO / "src"))
        from laplace.engine import telemetry  # type: ignore
        return telemetry


_PARTITION_RE = re.compile(r"^##\s+(\w+)\b", re.M)


def parse_skeleton(skeleton_text: str) -> dict[str, list[str]]:
    """Parse a transcript_digest skeleton.md into {partition: [stub, ...]}."""
    parts: dict[str, list[str]] = {}
    current = None
    for line in skeleton_text.splitlines():
        m = _PARTITION_RE.match(line)
        if m:
            current = m.group(1)
            parts[current] = []
            continue
        if current and line.startswith("- "):
            stub = line[2:].strip()
            stub = re.sub(r"^\[[^\]]+\]\s*", "", stub)  # drop the [speaker] tag
            if stub:
                parts[current].append(stub)
    return parts


def confidence_band(score: float) -> str:
    """A weak placement is the confabulation risk - the confident-wrong retrieval."""
    if score >= 0.18:
        return "placed"
    if score >= 0.08:
        return "weak"
    return "ungrounded"


def run(digest_dir: str, corpus: str, out: str | None, target: str | None, do_log: bool) -> int:
    ddir = Path(digest_dir)
    skel = ddir / "skeleton.md"
    if not skel.exists():
        print(f"no skeleton.md in {digest_dir} (run transcript_digest first)", file=sys.stderr)
        return 2
    manifest = {}
    mpath = ddir / "manifest.json"
    if mpath.exists():
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    target = target or manifest.get("id") or ddir.name

    parts = parse_skeleton(skel.read_text(encoding="utf-8"))
    concepts = parts.get("concepts", [])

    lt = _load(_LT)
    placements = []
    for stub in concepts:
        try:
            r = lt.tend(stub, corpus)
            top = (r.get("top_clusters") or [{}])[0]
            score = float(top.get("score", 0.0))
            neighbours = [nr.get("ref") for nr in (r.get("nearest_refs") or []) if nr.get("ref")]
            placements.append({
                "stub": stub,
                "action": r.get("action"),
                "target": r.get("target"),
                "score": round(score, 3),
                "band": confidence_band(score),
                "neighbours": neighbours,
            })
        except Exception as e:  # a corpus that cannot place the stub is itself a finding
            placements.append({"stub": stub, "action": "error", "target": str(e),
                               "score": 0.0, "band": "ungrounded", "neighbours": []})

    bands = {"placed": 0, "weak": 0, "ungrounded": 0}
    for p in placements:
        bands[p["band"]] = bands.get(p["band"], 0) + 1
    n = max(1, len(placements))
    hierarchy_fitness = round(bands["placed"] / n, 3)

    # The blind reconstruction packet - the only thing the reconstructor sees.
    brief = [f"# Reconstruction brief: {target}",
             "",
             "You are a blind reconstructor. From ONLY the digested stubs below - you do not have "
             "the raw transcript - rebuild the session: its thesis, what was decided, what was left "
             "open, and what the next move is. State plainly where the digest is too thin to "
             "reconstruct a piece (that gap is the finding, not a failure to paper over).",
             ""]
    for part, stubs in parts.items():
        if not stubs:
            continue
        brief.append(f"## {part}")
        for s in stubs:
            brief.append(f"- {s}")
        brief.append("")
    brief.append("## concept placement + proposed neighbours (the level tender's wiring)")
    brief.append("The test is not only 'can this session be replayed' but 'does each concept land "
                 "with its TRUE neighbours'. Verify each concept's proposed neighbours below; a "
                 "concept wired to the wrong neighbours is a confabulation even if the session "
                 "reconstructs.")
    for p in placements:
        nbrs = ", ".join(p.get("neighbours") or []) or "(none)"
        brief.append(f"- [{p['band']} {p['score']}] {p['action']} -> {p['target']}  ::  "
                     f"{p['stub'][:72]}\n    neighbours: {nbrs}")
    brief_text = "\n".join(brief)

    out_path = Path(out) if out else (ddir / "reconstruction_brief.md")
    out_path.write_text(brief_text, encoding="utf-8")

    # Bank the reinforcement record: this ghost called these nodes (clusters touched).
    called = sorted({p["target"] for p in placements if p.get("target") and p["band"] != "ungrounded"})
    if do_log:
        try:
            tel = _telemetry()
            tel.reconstruction(target=str(target), caller="eigen", nodes=called,
                               reason=f"hierarchy_fitness={hierarchy_fitness} "
                                      f"({bands['placed']}/{n} placed)")
        except Exception as e:
            print(f"(telemetry not logged: {e})", file=sys.stderr)

    print(f"# Reconstruction packet: {target}")
    print("*" * 50)
    print(f"Concepts: {len(concepts)} | placed: {bands['placed']} | weak: {bands['weak']} | "
          f"ungrounded: {bands['ungrounded']}")
    print(f"Hierarchy fitness (placed/total): {hierarchy_fitness}")
    print(f"Called nodes (reinforced): {', '.join(called) if called else '(none grounded)'}")
    print(f"Blind packet -> {out_path}")
    print("Next: hand the packet to a blind agent; judge the ghost vs the archived original; "
          "score with telemetry.reconstruction(fate=faithful|partial|confabulated, gap=...).")
    return 0


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    corpus = str(_REPO / "corpus" / "corpus.bib")
    out = None
    target = None
    do_log = "--no-log" not in argv
    if "--corpus" in argv:
        corpus = argv[argv.index("--corpus") + 1]
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    if "--target" in argv:
        target = argv[argv.index("--target") + 1]
    return run(args[0], corpus, out, target, do_log)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
