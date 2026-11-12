"""The frozen run's item loader: the one door onto the published CSV."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

from laplace.research.superarc import frozen_items

#: A stand-in header shaped like the real one: the sequence column plus the
#: answer/label columns the loader must refuse to carry forward.
_LABEL_COLUMNS = [
    "gpt_4o-formula",
    "gpt_4o-formula-correctness",
    "gpt_4o-formula-ordinal",
    "gpt_4o-formula-copy_seq",
]


def _sequences(count: int = 120) -> list[str]:
    return [",".join(format(index * 37 % 4096, "012b")) for index in range(count)]


@pytest.fixture
def fake_bench(tmp_path: Path) -> Path:
    clone = tmp_path / "bench"
    data = clone / "repo" / "data"
    data.mkdir(parents=True)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["sequence", *_LABEL_COLUMNS])
    for sequence in _sequences():
        writer.writerow([sequence, "2*n+1", "TRUE", "FALSE", "FALSE"])
    blob = buffer.getvalue().encode("utf-8")
    (data / "binary.csv").write_bytes(blob)
    (clone / "manifest.json").write_text(
        json.dumps(
            {
                "key_files": {
                    "binary_suite_csv": {
                        "path": "data/binary.csv",
                        "sha256": hashlib.sha256(blob).hexdigest(),
                        "sequence_column": "sequence",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return clone


def test_load_takes_exactly_the_first_hundred_rows_in_file_order(fake_bench):
    items = frozen_items.load(fake_bench)
    assert len(items) == frozen_items.FROZEN_N
    assert [item.row_index for item in items] == list(range(100))
    assert items[0].item_id == "bin-000"
    assert items[99].item_id == "bin-099"
    assert [item.sequence for item in items] == _sequences()[:100]


def test_load_refuses_a_csv_whose_hash_moved(fake_bench):
    csv_path = fake_bench / "repo" / "data" / "binary.csv"
    csv_path.write_bytes(csv_path.read_bytes() + b"1,1,1,1,1,1,1,1,1,1,1,1,x,TRUE,FALSE,FALSE\n")
    with pytest.raises(RuntimeError, match="hashes"):
        frozen_items.load(fake_bench)


def test_load_refuses_a_short_suite(fake_bench):
    with pytest.raises(RuntimeError, match="needs"):
        frozen_items.load(fake_bench, expect_n=400)


def test_load_needs_a_clone_location(monkeypatch):
    monkeypatch.delenv("LAPLACE_SUPERARC_BENCH", raising=False)
    with pytest.raises(RuntimeError, match="location is unset"):
        frozen_items.load()


def test_written_items_carry_the_sequence_and_nothing_else(fake_bench, tmp_path):
    run_dir = tmp_path / "run"
    provenance = frozen_items.write_run_items(run_dir, fake_bench)
    assert provenance["n"] == 100
    lines = (run_dir / frozen_items.ITEMS_FILENAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 100
    for line in lines:
        assert set(json.loads(line)) == frozen_items.ALLOWED_KEYS
    body = "\n".join(lines)
    for column in _LABEL_COLUMNS:
        assert column not in body
    assert "TRUE" not in body and "2*n+1" not in body


def test_the_contamination_gate_rejects_a_widened_record(fake_bench):
    items = list(frozen_items.load(fake_bench))

    class Leaky(frozen_items.FrozenItem):
        def as_record(self):  # type: ignore[override]
            record = super().as_record()
            record["gpt_4o-formula-correctness"] = True
            return record

    leaky = Leaky(item_id=items[0].item_id, row_index=0, sequence=items[0].sequence)
    with pytest.raises(RuntimeError, match="forbidden keys"):
        frozen_items._check_records([leaky])


def test_arms_read_the_run_dir_and_get_back_what_was_written(fake_bench, tmp_path):
    run_dir = tmp_path / "run"
    frozen_items.write_run_items(run_dir, fake_bench)
    assert frozen_items.read_run_items(run_dir) == frozen_items.load(fake_bench)


def test_read_run_items_refuses_a_tampered_run_file(fake_bench, tmp_path):
    run_dir = tmp_path / "run"
    frozen_items.write_run_items(run_dir, fake_bench)
    path = run_dir / frozen_items.ITEMS_FILENAME
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["gpt_4o-formula"] = "2*n+1"
    lines[0] = json.dumps(record, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="forbidden keys"):
        frozen_items.read_run_items(run_dir)


def test_items_digest_is_order_fixed_and_content_bound(fake_bench):
    items = frozen_items.load(fake_bench)
    assert frozen_items.items_digest(items) == frozen_items.items_digest(items)
    assert frozen_items.items_digest(items) != frozen_items.items_digest(tuple(reversed(items)))


def test_normalize_rejects_a_non_binary_sequence():
    assert frozen_items.normalize(" 1, 0 ,1 ") == "1,0,1"
    with pytest.raises(ValueError):
        frozen_items.normalize("1,2,3")
