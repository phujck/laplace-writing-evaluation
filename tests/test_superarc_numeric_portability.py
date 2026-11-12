"""SuperARC development-suite numerics are interpreter-independent (M5 release portability, 2026-10-16).

The frozen 120-item development suite (synthetics papers/superarc/dev_suite, items digest fd651c02...) was generated
with block_entropy's `-sum(...)` evaluated as plain left-to-right float addition. CPython 3.12 made builtin sum() of
floats compensated, which moves the last bit of some entropies, reorders ties in generate() and changed 34 items under
Python 3.14 (Root finding technical-dd-superarc-numeric-portability-finding-20261016). block_entropy now accumulates
explicitly in the original order. These vectors are frozen suite rows (public, sequence-only); the frozen files are
never rewritten.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from laplace.research.superarc import dev_suite

#: (item_id, sequence, frozen block_entropy): rows whose value differs in the last bit under compensated summation
FROZEN_ROWS = (
    ("dev-0-009", "0,1,0,0,1,1,0,1,0,0,1,1", 0.9681300137657637),
    ("dev-0-014", "0,0,0,0,0,0,0,0,1,1,0,1", 0.7455574250275929),
    ("dev-0-025", "0,1,1,0,1,0,0,0,0,0,1,0", 0.9338169454856061),
    ("dev-1-007", "0,0,1,1,1,1,1,1,1,0,0,0", 0.8085947862963576),
    ("dev-1-014", "0,0,0,0,0,1,1,1,0,0,0,0", 0.7455574250275927),
    ("dev-1-036", "1,0,1,0,1,0,1,0,0,1,1,0", 0.8383685150260665),
)
FROZEN_DIGEST = "fd651c0297d244e95663052ec9ee44ee72b5e66d47a5acd6a1b75716cf4bbe4d"


def _bits(sequence):
    return [int(x) for x in sequence.split(",")]


@pytest.mark.parametrize("item_id,sequence,frozen", FROZEN_ROWS)
def test_block_entropy_reproduces_the_frozen_value_bit_for_bit(item_id, sequence, frozen):
    assert dev_suite.block_entropy(_bits(sequence)) == frozen, item_id
    # the values differ from compensated summation in the last bit; that is the hazard this pins
    counts = {}
    for i in range(len(sequence.split(",")) - 1):
        block = tuple(_bits(sequence)[i:i + 2])
        counts[block] = counts.get(block, 0) + 1
    compensated = abs(-math.fsum((c / 11) * math.log2(c / 11) for c in counts.values()) / 2)
    assert compensated != frozen, "this row would move under compensated summation"


def test_block_entropy_edge_cases_keep_their_meaning():
    assert dev_suite.block_entropy([0] * 12) == 0.0 and str(dev_suite.block_entropy([0] * 12)) == "0.0", "no signed zero"
    assert dev_suite.block_entropy([0, 1] * 6, k=1) == 1.0
    assert dev_suite.block_entropy([0, 1, 1, 0], k=4) == 0.0
    with pytest.raises(ValueError):
        dev_suite.block_entropy([0, 1], k=3)
    with pytest.raises(ValueError):
        dev_suite.block_entropy([0, 1], k=0)


def _frozen_dir():
    for candidate in (dev_suite.SUITE_DIR, Path(os.environ.get("LAPLACE_SUPERARC_FROZEN_SUITE", "/nonexistent"))):
        if (candidate / "manifest.json").is_file() and (candidate / "items.jsonl").is_file():
            return candidate
    return None


def test_every_frozen_item_recomputes_exactly_and_the_suite_loads_unchanged():
    frozen = _frozen_dir()
    if frozen is None:
        pytest.skip("the frozen development suite is not in this checkout (set LAPLACE_SUPERARC_FROZEN_SUITE)")
    before = {name: (frozen / name).read_bytes() for name in ("manifest.json", "items.jsonl")}
    suite = dev_suite.load_suite(frozen)
    assert suite.manifest["items_digest"] == FROZEN_DIGEST and len(suite.items) == 120
    for item in suite.items:
        assert dev_suite.block_entropy(item.bits, suite.manifest["recipe"]["block_entropy_k"]) == item.block_entropy, item.item_id
    assert {name: (frozen / name).read_bytes() for name in before} == before, "the frozen files are read, never written"


def test_regeneration_from_the_frozen_manifest_reproduces_the_digest_with_the_upstream_exclusion():
    frozen = _frozen_dir()
    if frozen is None or not os.environ.get("LAPLACE_SUPERARC_BENCH"):
        pytest.skip("needs the frozen suite and an upstream acquisition (LAPLACE_SUPERARC_BENCH, docs/writing-campaigns.md)")
    manifest = json.loads((frozen / "manifest.json").read_text(encoding="utf-8"))
    rebuilt = dev_suite.regenerate(manifest)
    assert rebuilt.manifest["items_digest"] == FROZEN_DIGEST
