"""grade_probe.py - set up one barren-plateau-vs-hierarchy probe across two grades of an object.

The first rung of the graded climb. The conceptric is a graded algebra; each corpus record is an
object held at several grades of compression (coarsest -> finest: tldr -> claim -> summary). This
script lays out a single grade step k -> k+1 as a blind experiment with two arms:

  * FLAT      - reconstruct the finer grade (k+1) directly from the distributed neighbourhood (the
                router-reachable code: the object's title + the records that refine/extend it). No
                intermediate grade. This arm is the barren plateau: jump straight to the high grade.
  * HIERARCHICAL - reconstruct the coarse grade (k) first, hand it down as scaffold + residual
                (seed_from_gap.py), then reconstruct k+1 on that. This arm is the cure: climb.

Both arms start from the SAME neighbourhood and target the SAME held-out grade; the only difference
is the intermediate grade. So the contrast isolates hierarchialisation. The held-out grades (the
ground truth the ghost is scored against) are never in any brief - the interface is the context wall.

This script is mechanical: it parses the record, resolves the neighbourhood, and writes the held-out
originals + the two base briefs. The reconstructions themselves are spawned SEALED ghosts (blind,
no tools, the brief alone); the verdicts are adjudicate.py from outside. builder != judge.

Usage:
    python grade_probe.py <record-id> [--corpus corpus/corpus.bib] [--out <workdir>]
                          [--coarse claim] [--fine summary]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[6]

_REC_RE = re.compile(r"@\w+\{([^,]+),(.*?)\n\}", re.S)
_FIELD_RE = re.compile(r"^\s*(\w+)\s*=\s*\{(.+?)\},?\s*$", re.M)


def parse_corpus(bib_text: str) -> dict[str, dict[str, str]]:
    """Parse the corpus into {id: {field: value}}. Single-line fields (the corpus convention)."""
    out: dict[str, dict[str, str]] = {}
    for m in _REC_RE.finditer(bib_text):
        rid = m.group(1).strip()
        fields = {fm.group(1): fm.group(2).strip() for fm in _FIELD_RE.finditer(m.group(2))}
        out[rid] = fields
    return out


def parse_relations(rel: str) -> list[tuple[str, str]]:
    """`extends:idA | note; motivates:idB | note` -> [(extends, idA), (motivates, idB)]."""
    pairs = []
    for chunk in rel.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        head = chunk.split("|", 1)[0].strip()
        if ":" in head:
            rtype, rid = head.split(":", 1)
            pairs.append((rtype.strip(), rid.strip()))
    return pairs


def neighbourhood(rec: dict, corpus: dict, rid: str) -> str:
    """The distributed code: the object's title + the tldr/summary of each related record.

    This is the router-reach proxy - the joint of coarse nodes the ghost reconstructs FROM. It does
    NOT contain the held-out grades of the object itself (only its title, the minimal anchor).
    """
    lines = [f"# The object (held at grades you must reconstruct - only its TITLE is given here)",
             f"title: {rec.get('title', rid)}",
             f"cluster: {rec.get('cluster', '(none)')}    keywords: {rec.get('keywords', '(none)')}",
             "",
             "# The distributed neighbourhood (the router-reachable code - reconstruct from THIS)"]
    rels = parse_relations(rec.get("relations", ""))
    if not rels:
        lines.append("(no related records - the neighbourhood is empty; say so if you cannot rebuild)")
    for rtype, nid in rels:
        nrec = corpus.get(nid, {})
        lines.append(f"\n## {rtype} -> {nid}")
        lines.append(f"title: {nrec.get('title', '(unknown - not in corpus)')}")
        if nrec.get("tldr"):
            lines.append(f"tldr: {nrec['tldr']}")
        if nrec.get("summary"):
            lines.append(f"summary: {nrec['summary']}")
    return "\n".join(lines)


def brief(goal_grade: str, target_desc: str, nbhd: str) -> str:
    """A blind reconstruction brief in the reconstruct.py voice - the ghost sees ONLY this."""
    return "\n".join([
        f"# Reconstruction brief: the {goal_grade} of this object",
        "",
        "You are a SEALED, blind reconstructor. From ONLY the neighbourhood below - you do NOT have "
        "the object's own text at any grade, and you must NOT use any outside knowledge of the "
        "specific paper, nor any tools, files, or search - reconstruct:",
        "",
        f"  >> {target_desc}",
        "",
        "Write it as the object itself would state it, at that grade of detail. Where the "
        "neighbourhood is too thin to reconstruct a piece, say so plainly - that named gap is the "
        "finding, not a thing to paper over with a confident guess (a confident-wrong fill is the "
        "confabulation the loop is built to catch). Output ONLY the reconstruction.",
        "",
        "---",
        "",
        nbhd,
        "",
    ])


def run(rid: str, corpus_path: str, workdir: str, coarse: str, fine: str) -> int:
    bib = Path(corpus_path).read_text(encoding="utf-8")
    corpus = parse_corpus(bib)
    if rid not in corpus:
        print(f"record {rid!r} not in {corpus_path}", file=sys.stderr)
        return 2
    rec = corpus[rid]
    for g in (coarse, fine):
        if g not in rec:
            print(f"record {rid!r} has no {g!r} grade (fields: {sorted(rec)})", file=sys.stderr)
            return 2

    wd = Path(workdir)
    wd.mkdir(parents=True, exist_ok=True)
    nbhd = neighbourhood(rec, corpus, rid)
    (wd / "neighbourhood.md").write_text(nbhd, encoding="utf-8")
    # Held-out ground truth (scored against, never shown to a ghost).
    (wd / f"original_{coarse}.md").write_text(rec[coarse], encoding="utf-8")
    (wd / f"original_{fine}.md").write_text(rec[fine], encoding="utf-8")
    # The two base briefs.
    (wd / "brief_coarse.md").write_text(
        brief(coarse, f"the {coarse} (the coarse grade): the single load-bearing assertion the "
                      f"object makes.", nbhd), encoding="utf-8")
    (wd / "brief_flat.md").write_text(
        brief(fine, f"the {fine} (the finer grade): the mechanism in full - how the claim is "
                    f"achieved, what it establishes, what it connects to.", nbhd), encoding="utf-8")

    print(f"# Grade probe laid out: {rid}   {coarse} (k) -> {fine} (k+1)")
    print("*" * 50)
    print(f"workdir: {wd}")
    print("held-out ground truth:  original_%s.md, original_%s.md" % (coarse, fine))
    print("briefs:  brief_coarse.md (reconstruct k),  brief_flat.md (reconstruct k+1 flat)")
    print("\nOrchestration (sealed ghosts, builder != judge):")
    print("  1. ghost_coarse  <- brief_coarse.md   (reconstruct the %s)" % coarse)
    print("  2. adjudicate_sealed.py brief original_%s.md ghost_coarse.md -> spawn ensemble -> "
          "aggregate  (the SEMANTIC coarse residual; adjudicate.py banked alongside as the "
          "unfaithful floor)" % coarse)
    print("  3. seed_from_gap.py original_%s.md ghost_coarse.md brief_flat.md --out brief_hier.md" % coarse)
    print("  4. ghost_flat <- brief_flat.md ;  ghost_hier <- brief_hier.md   (both reconstruct %s)" % fine)
    print("  5. adjudicate_sealed.py on original_%s.md vs ghost_flat / ghost_hier  (flat vs hierarchy)" % fine)
    return 0


def print_loop_plan(coarse: str, fine: str, cycles: int, kind: str) -> None:
    """The iterated wake-sleep plan (G0b): the loop the sealed-ghost driver (G1) runs, gated by
    converge.converged(). Zero-cloud here - this prints the control structure; the ghosts that fill
    it are sealed cloud agents. The halt is spectral-radius framed, not a wall-clock budget."""
    print("\n" + "=" * 50)
    print(f"Iterated climb plan: up to {cycles} cycles, kind={kind}")
    print("Halt = converge.converged(verdicts, grade=%r, kind=%r) - rho vs rho*(grade, kind):" % (fine, kind))
    print("  factual -> deep-stable basin;  generative -> the lower edge (don't over-contract);")
    print("  factual_people -> the covenant ratchet (never toward the edge).")
    print("  each cycle:")
    print(f"    a. ghost_flat, ghost_hier <- briefs            (reconstruct {fine})")
    print(f"    b. adjudicate_sealed.py original_{fine}.md ghost_*.md -> Verdict (lost, added, "
          "structured, recurses)   [G2: adapt converge.Verdict to read the sealed shape]")
    print("    c. converged(verdicts, grade=%r, kind=%r):" % (fine, kind))
    print("         OSCILLATING (rho>=1 | limit cycle) -> stop: the loop will not close")
    print("         CONVERGED-DEGENERATE -> stop: the plateau, route UP a grade (never minimise it)")
    print("         CONVERGED-FAITHFUL   -> stop: the rung closed")
    print("         OPEN -> seed_from_gap.py (reseed on the residual) and continue")
    print("    d. converge.bank(halt, grade, kind) -> dial-attributable telemetry")
    print("=" * 50)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    rid = args[0]
    corpus = argv[argv.index("--corpus") + 1] if "--corpus" in argv else str(_REPO / "corpus" / "corpus.bib")
    workdir = argv[argv.index("--out") + 1] if "--out" in argv else str(_REPO / "experiments" / "grade_probe" / rid)
    coarse = argv[argv.index("--coarse") + 1] if "--coarse" in argv else "claim"
    fine = argv[argv.index("--fine") + 1] if "--fine" in argv else "summary"
    cycles = int(argv[argv.index("--cycles") + 1]) if "--cycles" in argv else 1
    kind = argv[argv.index("--kind") + 1] if "--kind" in argv else "factual"
    rc = run(rid, corpus, workdir, coarse, fine)
    if rc == 0 and cycles > 1:
        print_loop_plan(coarse, fine, cycles, kind)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
