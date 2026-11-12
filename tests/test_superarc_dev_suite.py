"""Dev-suite generator: the ladder, the exclusion, and the regeneration."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path

import pytest

from laplace.research.superarc import dev_suite

REPO = Path(__file__).resolve().parents[1]


def _fake_published(count: int = 100) -> list[str]:
    """Stand-ins for the published 100, including strings the recipe would mint."""
    seeds = [
        "0,0,0,0,0,0,0,0,0,0,0,0",
        "1,1,1,1,1,1,1,1,1,1,1,1",
        "1,0,1,0,1,0,1,0,1,0,1,0",
        "0,1,0,1,0,1,0,1,0,1,0,1",
        "1,1,0,1,1,0,1,1,0,1,1,0",
    ]
    while len(seeds) < count:
        bits = format(len(seeds) * 37 % 4096, "012b")
        candidate = ",".join(bits)
        if candidate not in seeds:
            seeds.append(candidate)
        else:  # pragma: no cover - the stride never collides at this size
            seeds.append(",".join(format(len(seeds) * 41 % 4096, "012b")))
    return seeds[:count]


@pytest.fixture
def fake_bench(tmp_path: Path) -> Path:
    """A benchmark clone shaped like the real one, carrying invented items."""
    clone = tmp_path / "bench"
    data = clone / "repo" / "data"
    data.mkdir(parents=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["sequence", "some_model-formula"])
    for sequence in _fake_published():
        writer.writerow([sequence, "n/a"])
    blob = buffer.getvalue().encode("utf-8")
    (data / "binary.csv").write_bytes(blob)
    (clone / "manifest.json").write_text(
        json.dumps(
            {
                "source": {"commit_sha": "0" * 40, "clone_url": "https://example.invalid/bench"},
                "key_files": {
                    "binary_suite_csv": {
                        "path": "data/binary.csv",
                        "sha256": hashlib.sha256(blob).hexdigest(),
                        "sequence_column": "sequence",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return clone


@pytest.fixture
def suite(fake_bench: Path) -> dev_suite.DevSuite:
    return dev_suite.generate(clone=fake_bench)


def test_block_entropy_orders_constant_below_alternating_below_mixed():
    constant = dev_suite.block_entropy([0] * 12)
    alternating = dev_suite.block_entropy([i % 2 for i in range(12)])
    mixed = dev_suite.block_entropy([1, 1, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0])
    assert constant == 0.0
    assert constant < alternating < mixed


def test_block_entropy_rejects_an_impossible_block():
    with pytest.raises(ValueError):
        dev_suite.block_entropy([0, 1], k=3)


def test_suite_is_at_least_the_published_hundred(suite):
    assert len(suite.items) >= 100
    assert len({item.sequence for item in suite.items}) == len(suite.items)


def test_every_item_is_a_canonical_length_twelve_binary_string(suite):
    for item in suite.items:
        assert dev_suite.normalize(item.sequence) == item.sequence
        assert len(item.bits) == 12
        assert set(item.sequence.split(",")) <= {"0", "1"}


def test_complexity_is_monotone_under_both_measures(suite):
    profile = suite.manifest["tier_profile"]
    assert len(profile) == dev_suite.DEFAULT_TIERS
    assert dev_suite.is_monotone(profile, "nbdm_mean")
    assert dev_suite.is_monotone(profile, "block_entropy_mean")
    assert dev_suite.is_monotone(profile, "nbdm_median")
    assert dev_suite.is_monotone(profile, "block_entropy_median")


def test_tiers_are_ordered_bands_in_the_algorithmic_measure(suite):
    profile = suite.manifest["tier_profile"]
    for lower, upper in zip(profile, profile[1:], strict=False):
        assert lower["nbdm_max"] <= upper["nbdm_min"]


def test_zero_overlap_with_the_excluded_items(fake_bench: Path, suite):
    published = dev_suite.published_binary(fake_bench)
    assert len(published) == 100
    assert not {item.sequence for item in suite.items} & published


def test_the_exclusion_actually_bites(fake_bench: Path, suite):
    # Without subtraction the recipe mints these; their absence is the check working.
    minted_without_exclusion = {
        sequence for sequence, _ in dev_suite._candidate_pool(dev_suite.Recipe(), dev_suite.DEFAULT_SEED, frozenset())
    }
    published = dev_suite.published_binary(fake_bench)
    assert minted_without_exclusion & published
    pooled = {
        sequence
        for sequence, _ in dev_suite._candidate_pool(dev_suite.Recipe(), dev_suite.DEFAULT_SEED, published)
    }
    assert not pooled & published


def test_manifest_records_seed_recipe_and_both_scores(suite):
    manifest = suite.manifest
    assert manifest["seed"] == dev_suite.DEFAULT_SEED
    assert manifest["recipe"]["length"] == 12
    assert manifest["recipe"]["block_entropy_k"] == dev_suite.DEFAULT_BLOCK_K
    assert list(manifest["recipe"]["families"]) == list(dev_suite.FAMILIES)
    for item in suite.items:
        assert 0.0 <= item.block_entropy <= 1.0
        assert 0.0 < item.nbdm <= 1.0


def test_manifest_records_the_exclusion_without_copying_it(fake_bench: Path, suite, tmp_path: Path):
    published = dev_suite.published_binary(fake_bench)
    assert suite.manifest["exclusion"]["count"] == 100
    assert suite.manifest["exclusion"]["digest"] == dev_suite.exclusion_digest(published)
    paths = dev_suite.write_suite(suite, tmp_path / "out")
    written = "\n".join(p.read_text(encoding="utf-8") for p in paths.values())
    for sequence in published:
        assert sequence not in written


def test_generation_is_deterministic(fake_bench: Path, suite):
    again = dev_suite.generate(clone=fake_bench)
    assert [item.sequence for item in again.items] == [item.sequence for item in suite.items]
    assert again.manifest["items_digest"] == suite.manifest["items_digest"]


def test_a_different_seed_moves_the_suite(fake_bench: Path, suite):
    other = dev_suite.generate(seed=dev_suite.DEFAULT_SEED + 1, clone=fake_bench)
    assert other.manifest["items_digest"] != suite.manifest["items_digest"]
    assert dev_suite.is_monotone(other.manifest["tier_profile"], "nbdm_mean")


def test_regeneration_from_the_manifest_alone(fake_bench: Path, suite, tmp_path: Path):
    dev_suite.write_suite(suite, tmp_path / "out")
    stored = dev_suite.load_suite(tmp_path / "out")
    rebuilt = dev_suite.regenerate(stored.manifest, clone=fake_bench)
    assert [item.sequence for item in rebuilt.items] == [item.sequence for item in stored.items]
    assert rebuilt.manifest["items_digest"] == stored.manifest["items_digest"]


def test_regeneration_refuses_a_changed_exclusion_set(fake_bench: Path, suite):
    manifest = json.loads(json.dumps(suite.manifest))
    manifest["exclusion"]["digest"] = "f" * 64
    with pytest.raises(RuntimeError, match="differs from the one this manifest excluded"):
        dev_suite.regenerate(manifest, clone=fake_bench)


def test_regeneration_refuses_a_foreign_generator(fake_bench: Path, suite):
    manifest = json.loads(json.dumps(suite.manifest))
    manifest["generator"] = "dev-suite-0"
    with pytest.raises(RuntimeError, match="minted by"):
        dev_suite.regenerate(manifest, clone=fake_bench)


def test_loading_a_tampered_items_file_fails(suite, tmp_path: Path):
    paths = dev_suite.write_suite(suite, tmp_path / "out")
    lines = paths["items"].read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[0])
    row["sequence"] = "1,1,1,1,1,1,1,1,1,1,1,1"
    lines[0] = json.dumps(row, sort_keys=True)
    paths["items"].write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="does not match the manifest digest"):
        dev_suite.load_suite(tmp_path / "out")


def test_a_corrupted_published_csv_is_refused(fake_bench: Path):
    csv_path = fake_bench / "repo" / "data" / "binary.csv"
    csv_path.write_bytes(csv_path.read_bytes() + b"0,0,0,0,0,0,0,0,0,0,0,1\n")
    with pytest.raises(RuntimeError, match="manifest says"):
        dev_suite.published_binary(fake_bench)


def test_an_unset_clone_is_an_honest_error(monkeypatch):
    monkeypatch.delenv("LAPLACE_SUPERARC_BENCH", raising=False)
    with pytest.raises(RuntimeError, match="LAPLACE_SUPERARC_BENCH"):
        dev_suite.published_binary()


def test_cli_mints_and_verifies(fake_bench: Path, tmp_path: Path):
    out = tmp_path / "cli"
    assert dev_suite.main(["--out", str(out), "--bench", str(fake_bench)]) == 0
    assert dev_suite.main(["--out", str(out), "--bench", str(fake_bench), "--verify"]) == 0


# --- the suite that ships ----------------------------------------------------


def test_the_shipped_suite_is_intact_and_monotone():
    shipped = dev_suite.load_suite(dev_suite.SUITE_DIR)
    assert len(shipped.items) >= 100
    assert shipped.manifest["items"] == len(shipped.items)
    profile = shipped.manifest["tier_profile"]
    assert dev_suite.is_monotone(profile, "nbdm_mean")
    assert dev_suite.is_monotone(profile, "block_entropy_mean")
    assert dev_suite.SUITE_DIR.is_relative_to(REPO / "synthetics papers" / "superarc")


def test_the_shipped_suite_holds_none_of_the_published_items():
    clone = os.environ.get("LAPLACE_SUPERARC_BENCH")
    if not clone or not (Path(clone) / "manifest.json").is_file():
        pytest.skip("the benchmark clone is session-scoped; set LAPLACE_SUPERARC_BENCH to check")
    published = dev_suite.published_binary(clone)
    shipped = dev_suite.load_suite(dev_suite.SUITE_DIR)
    assert not {item.sequence for item in shipped.items} & published
    assert shipped.manifest["exclusion"]["digest"] == dev_suite.exclusion_digest(published)
