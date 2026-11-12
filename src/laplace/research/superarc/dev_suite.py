"""The dev suite — binary items minted by the benchmark's own recipe.

The published 100 are read ONCE, post-freeze; every threshold, lens roster and
pilot run happens on items minted here. So this module is the whole held-out
design, and three constraints are load-bearing:

* **Zero overlap.** The published binary suite is read at generation time from a
  session-scoped clone (``LAPLACE_SUPERARC_BENCH``) purely to subtract it from
  the candidate pool. The published strings are never written to disk, never
  returned in a suite, and never cached — the manifest records only their count
  and a digest, which is enough to prove the check ran and not enough to
  reconstruct an item.
* **Both measures.** Items are laddered by the paper's pair: a statistical
  measure (block entropy, the entropy rate over overlapping k-blocks) and the
  algorithmic one (:py:func:`laplace.research.superarc.bdm.nbdm`). Tier assignment is by
  nBDM quantile band over the pooled candidates, so nBDM monotonicity holds by
  construction and block entropy's is measured, not assumed.
* **Determinism.** The recipe is a seeded pipeline over a fixed family order;
  :py:func:`regenerate` rebuilds the byte-identical suite from the manifest
  alone (given the same benchmark clone, whose digest it verifies).

Families are short generative programs, not aesthetic classes: tiling a period,
run-length blocks, a periodic string with one defect, an XOR recurrence, an
elementary cellular automaton, and uniform bits. Their outputs are pooled and
then laddered — provenance is recorded per item, but the tier is the measured
complexity, never the family label.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Sequence

from laplace.research.superarc.bdm import nbdm

REPO = source_tree()
SUITE_DIR = REPO / "synthetics papers" / "superarc" / "dev_suite"

GENERATOR_VERSION = "dev-suite-1"

DEFAULT_SEED = 20260804
DEFAULT_LENGTH = 12
DEFAULT_TIERS = 3
DEFAULT_PER_TIER = 40
DEFAULT_POOL_PER_FAMILY = 600
DEFAULT_BLOCK_K = 2

ALPHABET = "01"
SEPARATOR = ","


# --- the statistical measure -------------------------------------------------


def block_entropy(bits: Sequence[int], k: int = DEFAULT_BLOCK_K) -> float:
    """Shannon entropy rate over overlapping k-blocks, in bits per symbol.

    Overlapping blocks (not a disjoint tiling) because a 12-bit string gives 11
    2-blocks but only 6 disjoint ones, and the disjoint count is too coarse to
    order items at this length.
    """
    if k < 1:
        raise ValueError(f"block size must be >= 1, got {k}")
    if len(bits) < k:
        raise ValueError(f"sequence of length {len(bits)} is shorter than block {k}")
    counts: dict[tuple[int, ...], int] = {}
    total = len(bits) - k + 1
    for i in range(total):
        block = tuple(bits[i : i + k])
        counts[block] = counts.get(block, 0) + 1
    # Sequential left-to-right accumulation, in block first-occurrence order: the arithmetic the frozen suite was
    # generated with (`-sum(...)` under CPython < 3.12). CPython 3.12 made builtin sum() of floats compensated, which
    # moves the last bit, reorders entropy ties in generate() and changes the frozen 120-item digest (Root diagnostic
    # 2026-10-16, technical-dd-superarc-numeric-portability-finding). Spelled out so every interpreter agrees.
    accumulated = 0.0
    for c in counts.values():
        accumulated += (c / total) * math.log2(c / total)
    entropy = -accumulated
    # A single repeated block gives -0.0 through the log; the ladder is compared
    # numerically and a signed zero would print as "-0.0" in the manifest.
    return abs(entropy / k)


# --- the recipe --------------------------------------------------------------


def _fam_periodic(rng: random.Random, length: int) -> list[int]:
    period = rng.choice([1, 2, 3, 4])
    pattern = [rng.randint(0, 1) for _ in range(period)]
    return [pattern[i % period] for i in range(length)]


def _fam_runs(rng: random.Random, length: int) -> list[int]:
    bits: list[int] = []
    value = rng.randint(0, 1)
    while len(bits) < length:
        bits.extend([value] * rng.choice([2, 3, 4, 5]))
        value ^= 1
    return bits[:length]


def _fam_defect(rng: random.Random, length: int) -> list[int]:
    bits = _fam_periodic(rng, length)
    bits[rng.randrange(length)] ^= 1
    return bits


def _fam_recurrence(rng: random.Random, length: int) -> list[int]:
    lag = rng.choice([2, 3, 4])
    bits = [rng.randint(0, 1) for _ in range(lag)]
    while len(bits) < length:
        bits.append(bits[-1] ^ bits[-lag])
    return bits[:length]


def _fam_automaton(rng: random.Random, length: int) -> list[int]:
    rule = rng.choice([30, 90, 110, 150])
    state = [rng.randint(0, 1) for _ in range(length)]
    for _ in range(rng.choice([1, 2, 3])):
        state = [
            (rule >> ((state[(i - 1) % length] << 2) | (state[i] << 1) | state[(i + 1) % length])) & 1
            for i in range(length)
        ]
    return state


def _fam_uniform(rng: random.Random, length: int) -> list[int]:
    return [rng.randint(0, 1) for _ in range(length)]


# Order is load-bearing: the pool is drawn family by family from one stream.
FAMILIES: dict[str, Callable[[random.Random, int], list[int]]] = {
    "periodic": _fam_periodic,
    "runs": _fam_runs,
    "defect": _fam_defect,
    "recurrence": _fam_recurrence,
    "automaton": _fam_automaton,
    "uniform": _fam_uniform,
}


@dataclass(frozen=True)
class Recipe:
    """Every knob the generator reads, recorded verbatim in the manifest."""

    length: int = DEFAULT_LENGTH
    alphabet: str = ALPHABET
    separator: str = SEPARATOR
    tiers: int = DEFAULT_TIERS
    per_tier: int = DEFAULT_PER_TIER
    pool_per_family: int = DEFAULT_POOL_PER_FAMILY
    block_entropy_k: int = DEFAULT_BLOCK_K
    families: tuple[str, ...] = field(default_factory=lambda: tuple(FAMILIES))

    def __post_init__(self) -> None:
        unknown = [f for f in self.families if f not in FAMILIES]
        if unknown:
            raise ValueError(f"unknown families: {unknown}")
        if self.tiers < 2:
            raise ValueError("a ladder needs at least two tiers")
        if self.per_tier < 1 or self.pool_per_family < 1:
            raise ValueError("per_tier and pool_per_family must be positive")

    @classmethod
    def from_dict(cls, data: dict) -> "Recipe":
        return cls(
            length=int(data["length"]),
            alphabet=str(data["alphabet"]),
            separator=str(data["separator"]),
            tiers=int(data["tiers"]),
            per_tier=int(data["per_tier"]),
            pool_per_family=int(data["pool_per_family"]),
            block_entropy_k=int(data["block_entropy_k"]),
            families=tuple(data["families"]),
        )


@dataclass(frozen=True)
class Item:
    item_id: str
    tier: int
    family: str
    sequence: str
    block_entropy: float
    nbdm: float

    @property
    def bits(self) -> list[int]:
        return [int(c) for c in self.sequence.split(SEPARATOR)]


@dataclass(frozen=True)
class DevSuite:
    items: tuple[Item, ...]
    manifest: dict


# --- the exclusion check (reads the published items, copies nothing) ---------


def bench_dir(explicit: str | Path | None = None) -> Path:
    """The session-scoped benchmark clone. Never inside the repo working tree."""
    raw = explicit or os.environ.get("LAPLACE_SUPERARC_BENCH")
    if not raw:
        raise RuntimeError(
            "the published suite's location is unset; export LAPLACE_SUPERARC_BENCH "
            "to the benchmark clone (the one carrying manifest.json)"
        )
    return Path(raw)


def published_binary(clone: str | Path | None = None) -> frozenset[str]:
    """The published 100, in memory, for subtraction only.

    The caller may hash them and count them. Writing them anywhere — a suite
    file, a manifest, a fixture — breaks the frozen-set discipline.
    """
    root = bench_dir(clone)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"no benchmark manifest at {manifest_path}")
    entry = json.loads(manifest_path.read_text(encoding="utf-8"))["key_files"]["binary_suite_csv"]
    csv_path = root / "repo" / entry["path"]
    blob = csv_path.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != entry["sha256"]:
        raise RuntimeError(
            f"published suite CSV at {csv_path} hashes {digest}, manifest says {entry['sha256']}"
        )
    rows = list(csv.DictReader(blob.decode("utf-8").splitlines()))
    column = entry.get("sequence_column", "sequence")
    return frozenset(normalize(row[column]) for row in rows)


def normalize(sequence: str) -> str:
    """Canonical item form: comma-separated bits, no spaces — the published form."""
    parts = [p.strip() for p in sequence.strip().split(SEPARATOR)]
    if not all(p in tuple(ALPHABET) for p in parts):
        raise ValueError(f"not a binary sequence: {sequence!r}")
    return SEPARATOR.join(parts)


def exclusion_digest(excluded: Iterable[str]) -> str:
    """A digest over the sorted exclusion set — provable, not invertible."""
    joined = "\n".join(sorted(excluded))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


# --- generation --------------------------------------------------------------


def _candidate_pool(recipe: Recipe, seed: int, excluded: frozenset[str]) -> list[tuple[str, str]]:
    """(sequence, family) pairs, deduplicated, first-drawn family wins."""
    rng = random.Random(seed)
    pool: dict[str, str] = {}
    for name in recipe.families:
        mint = FAMILIES[name]
        for _ in range(recipe.pool_per_family):
            sequence = SEPARATOR.join(str(b) for b in mint(rng, recipe.length))
            if sequence in excluded or sequence in pool:
                continue
            pool[sequence] = name
    return list(pool.items())


def generate(
    seed: int = DEFAULT_SEED,
    recipe: Recipe | None = None,
    clone: str | Path | None = None,
) -> DevSuite:
    """Mint the dev suite: pool, subtract the published, score, ladder, select."""
    recipe = recipe or Recipe()
    excluded = published_binary(clone)
    pool = _candidate_pool(recipe, seed, excluded)
    needed = recipe.tiers * recipe.per_tier
    if len(pool) < needed:
        raise RuntimeError(
            f"pool of {len(pool)} candidates cannot fill {needed} items; raise pool_per_family"
        )

    scored = [
        (
            sequence,
            family,
            block_entropy([int(c) for c in sequence.split(SEPARATOR)], recipe.block_entropy_k),
            nbdm(sequence),
        )
        for sequence, family in pool
    ]
    # The ladder is nBDM-first; block entropy and the string break ties so the
    # order is total and the same on every machine.
    scored.sort(key=lambda row: (row[3], row[2], row[0]))

    items: list[Item] = []
    size = len(scored)
    for tier in range(recipe.tiers):
        band = scored[tier * size // recipe.tiers : (tier + 1) * size // recipe.tiers]
        if len(band) < recipe.per_tier:
            raise RuntimeError(f"tier {tier} band holds {len(band)} < {recipe.per_tier} candidates")
        # Spread across the band rather than taking its head, so a tier samples
        # its whole complexity range instead of piling on the boundary.
        stride = len(band) // recipe.per_tier
        chosen = band[::stride][: recipe.per_tier]
        for index, (sequence, family, entropy, algorithmic) in enumerate(chosen):
            items.append(
                Item(
                    item_id=f"dev-{tier}-{index:03d}",
                    tier=tier,
                    family=family,
                    sequence=sequence,
                    block_entropy=entropy,
                    nbdm=algorithmic,
                )
            )

    manifest = _manifest(seed, recipe, items, excluded, clone)
    return DevSuite(items=tuple(items), manifest=manifest)


def _manifest(
    seed: int,
    recipe: Recipe,
    items: Sequence[Item],
    excluded: frozenset[str],
    clone: str | Path | None,
) -> dict:
    source = json.loads((bench_dir(clone) / "manifest.json").read_text(encoding="utf-8"))["source"]
    return {
        "generator": GENERATOR_VERSION,
        "seed": seed,
        "recipe": asdict(recipe),
        "items": len(items),
        "tier_profile": tier_profile(items),
        "exclusion": {
            # The published items themselves appear nowhere: count and digest only.
            "count": len(excluded),
            "digest": exclusion_digest(excluded),
            "source_commit": source["commit_sha"],
            "source_url": source["clone_url"],
        },
        "items_digest": _items_digest(items),
    }


def _items_digest(items: Sequence[Item]) -> str:
    payload = "\n".join(_item_line(item) for item in items)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _item_line(item: Item) -> str:
    return json.dumps(asdict(item), sort_keys=True)


def tier_profile(items: Sequence[Item]) -> list[dict]:
    """Per-tier complexity summary under both measures — the monotonicity record."""
    profile = []
    for tier in sorted({item.tier for item in items}):
        band = [item for item in items if item.tier == tier]
        profile.append(
            {
                "tier": tier,
                "items": len(band),
                "block_entropy_mean": statistics.fmean(i.block_entropy for i in band),
                "block_entropy_median": statistics.median(i.block_entropy for i in band),
                "nbdm_mean": statistics.fmean(i.nbdm for i in band),
                "nbdm_median": statistics.median(i.nbdm for i in band),
                "nbdm_min": min(i.nbdm for i in band),
                "nbdm_max": max(i.nbdm for i in band),
            }
        )
    return profile


def is_monotone(profile: Sequence[dict], key: str) -> bool:
    values = [row[key] for row in profile]
    return all(b > a for a, b in zip(values, values[1:], strict=False))


# --- storage -----------------------------------------------------------------


def write_suite(suite: DevSuite, out_dir: str | Path = SUITE_DIR) -> dict[str, Path]:
    """Write manifest + items. Only our items are ever written."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    items_path = out / "items.jsonl"
    manifest_path = out / "manifest.json"
    items_path.write_text(
        "".join(_item_line(item) + "\n" for item in suite.items), encoding="utf-8"
    )
    manifest_path.write_text(json.dumps(suite.manifest, indent=2) + "\n", encoding="utf-8")
    return {"items": items_path, "manifest": manifest_path}


def load_suite(out_dir: str | Path = SUITE_DIR) -> DevSuite:
    out = Path(out_dir)
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    items = tuple(
        Item(**json.loads(line))
        for line in (out / "items.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    if _items_digest(items) != manifest["items_digest"]:
        raise RuntimeError(f"items.jsonl in {out} does not match the manifest digest")
    return DevSuite(items=items, manifest=manifest)


def regenerate(manifest: dict, clone: str | Path | None = None) -> DevSuite:
    """Rebuild from the manifest alone; the exclusion digest is verified, not trusted."""
    if manifest.get("generator") != GENERATOR_VERSION:
        raise RuntimeError(
            f"manifest was minted by {manifest.get('generator')!r}, this is {GENERATOR_VERSION!r}"
        )
    suite = generate(
        seed=int(manifest["seed"]),
        recipe=Recipe.from_dict(manifest["recipe"]),
        clone=clone,
    )
    if suite.manifest["exclusion"]["digest"] != manifest["exclusion"]["digest"]:
        raise RuntimeError("the published suite differs from the one this manifest excluded")
    if suite.manifest["items_digest"] != manifest["items_digest"]:
        raise RuntimeError("regeneration diverged from the manifest's items digest")
    return suite


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mint or verify the SuperARC dev suite.")
    parser.add_argument("--out", default=str(SUITE_DIR))
    parser.add_argument("--bench", default=None, help="the benchmark clone (else LAPLACE_SUPERARC_BENCH)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--tiers", type=int, default=DEFAULT_TIERS)
    parser.add_argument("--per-tier", type=int, default=DEFAULT_PER_TIER)
    parser.add_argument("--verify", action="store_true", help="regenerate from the stored manifest")
    args = parser.parse_args(argv)

    if args.verify:
        stored = load_suite(args.out)
        regenerate(stored.manifest, args.bench)
        print(f"verified {len(stored.items)} items against {args.out}/manifest.json")
        return 0

    suite = generate(
        seed=args.seed,
        recipe=Recipe(tiers=args.tiers, per_tier=args.per_tier),
        clone=args.bench,
    )
    paths = write_suite(suite, args.out)
    profile = suite.manifest["tier_profile"]
    for row in profile:
        print(
            f"tier {row['tier']}: n={row['items']} "
            f"H2={row['block_entropy_mean']:.4f} nBDM={row['nbdm_mean']:.4f}"
        )
    print(
        f"{len(suite.items)} items -> {paths['items']} "
        f"(entropy monotone: {is_monotone(profile, 'block_entropy_mean')}, "
        f"nBDM monotone: {is_monotone(profile, 'nbdm_mean')})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
