"""verify_seal_fingerprints.py - the SECOND seal instrument: does sealed text appear in a bundle?

    python3 scripts/verify_seal_fingerprints.py atlas/stores/snapshots/<hex>

WHY A SECOND INSTRUMENT. The exporter's laundered-leak check measures sealed-PATH-REFERENCE
density, and that signature has a blind spot: a derived store keyed by opaque ids - hashes,
integer row numbers, uuids - carries sealed CONTENT while referencing no sealed PATH, and scores
zero. This tool closes that hole from the other side. It samples distinctive lines out of the
sealed files themselves and asks, as fixed strings, whether any of them appear anywhere in the
bundle. Path-blind and content-based: exactly the complement of the first check.

Since 2026-08-13 the sealed set it draws from includes ``exporter.NEVER_PUBLIC_PATHS`` - files
whose own headers forbid them to travel - and their lines enter as a GUARANTEED quota rather
than a draw, because a uniform sample over a 188k-line corpus is evidence about the corpus and
not about a named document. See the quota block below for the measurement. Since 2026-08-21 the
quota is drawn from the LIVE never-public set - that list UNION whatever
``exporter.scan_declarations`` binds today - so a document that declares itself never-public
after the last hand-edit of the list is in the quota the same day it is written.

WHY IT LIVES HERE AND NOT IN ``atlas/``. It must READ SEALED BYTES to derive fingerprints. Atlas
code never reads sealed content - that is the seal - so this sits beside the exporter on the
laplace side. It does not import atlas.

ITS OWN BYTE ACCOUNTING, STATED PLAINLY. This tool reads sealed bytes locally, in this process,
to derive fingerprints. It emits COUNTS AND PATHS ONLY - never a fingerprint, never a matched
line, never a byte of sealed text. That is precisely why it is not part of the exporter: the
exporter's ``bytes_read_from_sealed: 0`` is a true statement about the export, and folding this
scan into it would make that number a lie. Two tools, two postures, one perimeter.

DETERMINISM. Sampling is seeded and the seed is printed with the result, so a run is reproducible
and a disagreement between two runs is a real change in the corpus rather than a different draw.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import export_atlas_snapshot as exporter  # noqa: E402 - the perimeter, single-sourced

ROOT = exporter.ROOT

SEED = 20260801

# Sensitivity is a real dial and it is set at the level that FOUND something, not at the level
# that runs fastest. 120 samples returns clean against the 2026-08-01 bundle in ~5 s; 1200
# samples surfaces two hits in ~30 s. An instrument tuned down until it passes is not an
# instrument, so the default is the sensitive one and the cost is paid.
DEFAULT_SAMPLES = 1200

# THE NEVER-PUBLIC QUOTA - GUARANTEED, NOT DRAWN.
#
# A uniform draw over the whole sealed corpus is the right instrument for "is soul content
# leaking somewhere", and the wrong one for "did THIS document travel". Measured 2026-08-13:
# the pool is 188,409 distinctive lines and the never-public profiles contribute 450 of them, so
# a 1200-sample draw expects 2.9 of their lines and misses the class entirely about 6% of the
# time. A perimeter instrument that misses the named document one run in seventeen is not
# evidence about that document.
#
# So every candidate line of every TEXT rendering in ``exporter.NEVER_PUBLIC_PATHS`` is added on
# top of the draw, unconditionally. It is bounded by construction - ``MAX_CANDIDATES_PER_FILE``
# caps each file at 200 - and the cost is ~37% more fixed-string passes at today's corpus. The
# .pdf renderings carry no text extension and contribute nothing here; the .md/.tex do, and the
# .tex matters most because its LaTeX escaping means a fingerprint drawn from the .md would not
# match it.

# A fingerprint has to be distinctive enough that an incidental match means something. Short
# lines and boilerplate collide by chance; a 60-400 byte line carrying at least six spaces is
# prose or structured text with real lexical content.
MIN_LEN, MAX_LEN = 60, 400
MIN_SPACES = 6
MAX_CANDIDATES_PER_FILE = 200

# KNOWN FALSE POSITIVES, allowlisted by the SOURCE FILE the hit lands in, each with the trace
# that established it. These three modules contain literal template lines that they WRITE INTO
# the content-free sealed skeletons; the fingerprint is therefore sampled from generated sealed
# output and matches the generator's own source, which is ordinary unsealed record. The match is
# real and the direction is backwards: the bundle carries the template, not the soul.
#
#   src/laplace/engine/soul_consolidate.py  write_skeleton's literal header block (~:235) - the
#                                    "COMMITTED, content-free" preamble it emits into the
#                                    graded skeleton.
#   src/laplace/engine/soul_dream.py        write_dream_state's literal header block (~:551/:561) -
#                                    the same construction for the dream-state file.
#   scripts/build_soul_vectors.py    the soul-vector manifest's literal "what"/"built" strings
#                                    (~:243) emitted into soul_vectors/manifest.json.
#
# An allowlist entry excuses a FILE, not a fingerprint: any hit anywhere else is a violation.
#
# NOT ALLOWLISTED, and deliberately left failing (2026-08-01): the 1200-sample run against
# bundle ebc72ca2 surfaces two further hits that are NOT traced false positives -
#
#   concept_corpus/_atoms_manifest.json      <- archive/soul_dump/_shard/deepen_opus_recovered.json
#   paper_control_degeneracy/voice_carrier.md <- archive/soul_dump/voice_samples.md
#
# - and an untraced hit must not be allowlisted, or the allowlist becomes the leak. The first
# has a named producer: scripts/ingest_soul_dump.py:267 writes that manifest, which
# concept_lens.py:78 documents as "public physics, never sealed" - so soul-dump ingestion emits
# into an unsealed store by design, and whether the emitted line is public physics or personal
# material is a content question this tool must not answer (it would have to print the bytes).
# The second has no producer this scan could find; direction is unestablished.
#
# Both are pre-existing REPOSITORY facts, not bundle defects: the bundle faithfully mirrors what
# is already committed at an unsealed path. Escalated to the author/judge for the trace ruling.
ALLOWLISTED_HIT_NODES = {
    "src/laplace/engine/soul_consolidate.py": "write_skeleton literal template emitted into the skeleton",
    "src/laplace/engine/soul_dream.py": "write_dream_state literal template emitted into dream state",
    "scripts/build_soul_vectors.py": "soul-vector manifest literal template",
}

COMMITTED_FILES = ("manifest.json", "nodes.jsonl", "seal_report.json", "segmentation.json")


def sealed_sources(repo_root: Path) -> list[Path]:
    """Every readable sealed text file: the sealed zones plus the EXTRA_SEALED_PATHS stores."""
    out: list[Path] = []
    for rel in exporter.node_universe(repo_root):
        if not exporter.is_sealed(rel):
            continue
        path = repo_root / rel
        if path.suffix.lower() not in exporter.TEXT_EXTENSIONS or not path.is_file():
            continue
        out.append(path)
    return sorted(out)


def candidates(path: Path) -> list[bytes]:
    """Distinctive lines from one sealed file, bounded and deterministically strided."""
    try:
        data = path.read_bytes()
    except OSError:
        return []
    found: list[bytes] = []
    for line in data.split(b"\n"):
        line = line.strip()
        if MIN_LEN <= len(line) <= MAX_LEN and line.count(b" ") >= MIN_SPACES:
            found.append(line)
    if len(found) <= MAX_CANDIDATES_PER_FILE:
        return found
    stride = len(found) / MAX_CANDIDATES_PER_FILE      # even coverage, not just the head
    return [found[int(i * stride)] for i in range(MAX_CANDIDATES_PER_FILE)]


def never_public_paths(repo_root: Path) -> list[str]:
    """The never-public set as of NOW: the literal list, plus whatever the heads declare today.

    The literal list alone would give this instrument the same staleness the exporter's fourth
    class was built to end - a document written after the last judge read the corpus would be
    sealed by the head scan and then not be in the quota that proves it did not travel. The union
    keeps the two instruments looking at the same perimeter (2026-08-21,
    WO-20260814-autoseal-by-declaration).
    """
    declared = exporter.scan_declarations(repo_root, exporter.node_universe(repo_root))["sealed"]
    return sorted(set(exporter.NEVER_PUBLIC_PATHS) | set(declared))


def never_public_lines(repo_root: Path) -> list[bytes]:
    """Every candidate line of the never-public documents' TEXT renderings - the guaranteed set."""
    out: list[bytes] = []
    for rel in never_public_paths(repo_root):
        path = repo_root / rel
        if path.suffix.lower() in exporter.TEXT_EXTENSIONS and path.is_file():
            out.extend(candidates(path))
    return sorted(set(out))


def fingerprints(repo_root: Path, n: int, seed: int) -> tuple[list[bytes], int, int]:
    pool: list[bytes] = []
    sampled_files = 0
    for path in sealed_sources(repo_root):
        got = candidates(path)
        if got:
            sampled_files += 1
            pool.extend(got)
    guaranteed = never_public_lines(repo_root)
    # Drawn from what is left, so the quota adds coverage instead of consuming the draw.
    pool = sorted(set(pool) - set(guaranteed))          # deterministic before the draw
    rng = random.Random(seed)
    if len(pool) > n:
        pool = rng.sample(pool, n)
    return sorted(set(pool) | set(guaranteed)), sampled_files, len(guaranteed)


def scan(bundle: Path, fps: list[bytes]) -> tuple[dict[str, int], int, int]:
    """Fixed-string every fingerprint against the bundle. Returns (hits by node, blobs, bytes)."""
    blob_owner: dict[str, str] = {}
    nodes_path = bundle / "nodes.jsonl"
    if nodes_path.is_file():
        with open(nodes_path, encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("content_blob"):
                    blob_owner[row["content_blob"].split(":", 1)[1]] = row["node_id"]

    hits: dict[str, int] = {}
    blobs = 0
    scanned = 0
    blobs_root = bundle / "blobs"
    targets: list[tuple[str, Path]] = []
    if blobs_root.is_dir():
        for blob in sorted(blobs_root.rglob("*")):
            if blob.is_file():
                targets.append((blob_owner.get(blob.name, f"(unowned blob {blob.name})"), blob))
                blobs += 1
    for name in COMMITTED_FILES + ("spans.jsonl",):
        path = bundle / name
        if path.is_file():
            targets.append((f"(bundle file) {name}", path))

    for label, path in targets:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        scanned += len(data)
        for fp in fps:
            if fp in data:
                hits[label] = hits.get(label, 0) + 1
    return hits, blobs, scanned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="scan a bundle for sealed-content fingerprints")
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    if not (args.bundle / "nodes.jsonl").is_file():
        print(f"REFUSED not a bundle: {args.bundle}", file=sys.stderr)
        return 2

    started = time.perf_counter()
    fps, sampled_files, guaranteed_n = fingerprints(ROOT, args.samples, args.seed)
    if not fps:
        print("REFUSED no fingerprints could be drawn from the sealed zones", file=sys.stderr)
        return 2
    hits, blobs, scanned = scan(args.bundle, fps)

    allowlisted = {k: v for k, v in hits.items() if k in ALLOWLISTED_HIT_NODES}
    violations = {k: v for k, v in hits.items() if k not in ALLOWLISTED_HIT_NODES}

    print("seal fingerprint scan")
    print(f"seed                  {args.seed}")
    print(f"sealed files sampled  {sampled_files}")
    print(f"fingerprints          {len(fps)} "
          f"({MIN_LEN}-{MAX_LEN} bytes, >={MIN_SPACES} spaces)")
    print(f"  never-public quota  {guaranteed_n} (guaranteed, not drawn)")
    print(f"bundle                {args.bundle}")
    print(f"blobs scanned         {blobs}")
    print(f"bytes scanned         {scanned}")
    print(f"hits                  {sum(hits.values())} in {len(hits)} file(s)")
    print(f"  allowlisted         {sum(allowlisted.values())} in {len(allowlisted)} file(s)")
    for node in sorted(allowlisted):
        print(f"      {allowlisted[node]:>4}  {node}  [{ALLOWLISTED_HIT_NODES[node]}]")
    print(f"  violations          {sum(violations.values())} in {len(violations)} file(s)")
    for node in sorted(violations):
        print(f"      {violations[node]:>4}  {node}")
    print(f"wall_clock            {time.perf_counter() - started:.2f}s")
    print("counts and paths only - no fingerprint or matched line is ever printed")

    if violations:
        print("REFUSED sealed-content fingerprints found in the bundle", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
