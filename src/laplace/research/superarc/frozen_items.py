"""The frozen run's item loader — the ONLY code permitted to open the published CSV.

The published binary suite ships as one CSV whose ``sequence`` column carries the
100 items and whose remaining ~69 columns carry every model's *answers* and the
authors' hand *labels*. Those columns are contamination: an arm that can see them
can copy an answer, and a scorer that reads them mid-run is no longer blind. So
the frozen-run design puts exactly one door on that file.

  * This module reads the CSV, verifies its sha256 against the bench manifest,
    takes rows 0..99, and keeps the ``sequence`` column and nothing else.
  * It writes ``items.jsonl`` into the run directory with three keys per row —
    ``item_id``, ``row_index``, ``sequence``. :data:`ALLOWED_KEYS` is enforced on
    the way out, so a future edit that widens the record fails a test rather than
    leaking a label into the run.
  * Every arm reads ``items.jsonl``. No arm is given the clone path.

This is deliberately NOT :func:`laplace.research.superarc.dev_suite.published_binary`,
whose docstring forbids writing the published items anywhere: that function
serves the dev suite's exclusion subtraction, where materializing the frozen set
would break the held-out discipline. Here the run directory IS the run, and
materializing the items is the point.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

#: The published binary suite: rows 0..99 of the released CSV, in file order.
FROZEN_N = 100
#: Item ids are positional and stable: row 0 is ``bin-000``.
ID_PREFIX = "bin"
#: The only keys a run-directory item record may carry.
ALLOWED_KEYS: frozenset[str] = frozenset({"item_id", "row_index", "sequence"})
#: The canonical run-directory filename.
ITEMS_FILENAME = "items.jsonl"

_SEPARATOR = ","
_ALPHABET = ("0", "1")


@dataclass(frozen=True)
class FrozenItem:
    """One published item, stripped to what an arm is allowed to see."""

    item_id: str
    row_index: int
    sequence: str

    def as_record(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "row_index": self.row_index,
            "sequence": self.sequence,
        }


def bench_dir(explicit: str | Path | None = None) -> Path:
    """The session-scoped benchmark clone. Never inside the repo working tree."""
    raw = explicit or os.environ.get("LAPLACE_SUPERARC_BENCH")
    if not raw:
        raise RuntimeError(
            "the published suite's location is unset; export LAPLACE_SUPERARC_BENCH "
            "to the benchmark clone (the one carrying manifest.json)"
        )
    return Path(raw)


def normalize(sequence: str) -> str:
    """Canonical item form: comma-separated bits, no spaces — the published form.

    The separator is load-bearing: nBDM is computed over the answer string as
    written, so a re-spaced sequence is a different item.
    """
    parts = [part.strip() for part in sequence.strip().split(_SEPARATOR)]
    if not parts or not all(part in _ALPHABET for part in parts):
        raise ValueError(f"not a binary sequence: {sequence!r}")
    return _SEPARATOR.join(parts)


def load(clone: str | Path | None = None, *, expect_n: int = FROZEN_N) -> tuple[FrozenItem, ...]:
    """Rows 0..``expect_n`` of the released binary suite, sequences only.

    Raises rather than returning a short suite: a frozen run scored over 97 items
    is not the preregistered run.
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
    column = entry.get("sequence_column", "sequence")
    rows = list(csv.DictReader(blob.decode("utf-8").splitlines()))
    if len(rows) < expect_n:
        raise RuntimeError(f"{csv_path} holds {len(rows)} data rows, the frozen run needs {expect_n}")
    items = tuple(
        FrozenItem(
            item_id=f"{ID_PREFIX}-{index:03d}",
            row_index=index,
            sequence=normalize(rows[index][column]),
        )
        for index in range(expect_n)
    )
    if len({item.sequence for item in items}) != expect_n:
        raise RuntimeError("the published suite carries duplicate sequences; the ids would not be 1:1")
    return items


def items_digest(items: Iterable[FrozenItem]) -> str:
    """A digest over the emitted records — provable after the fact, order-fixed."""
    payload = "\n".join(
        json.dumps(item.as_record(), sort_keys=True, separators=(",", ":")) for item in items
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _check_records(items: Iterable[FrozenItem]) -> list[dict[str, object]]:
    """The contamination gate: three keys, no more, on every record."""
    records = [item.as_record() for item in items]
    for record in records:
        extra = set(record) - ALLOWED_KEYS
        if extra:
            raise RuntimeError(
                f"item record carries forbidden keys {sorted(extra)}; only {sorted(ALLOWED_KEYS)} "
                "may reach the run directory (answers and hand labels are contamination)"
            )
    return records


def write_run_items(
    run_dir: str | Path,
    clone: str | Path | None = None,
    *,
    expect_n: int = FROZEN_N,
) -> dict[str, object]:
    """Materialize ``items.jsonl`` in the run directory and return its provenance."""
    items = load(clone, expect_n=expect_n)
    records = _check_records(items)
    destination = Path(run_dir)
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / ITEMS_FILENAME
    body = "".join(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records)
    path.write_text(body, encoding="utf-8")
    return {
        "path": str(path),
        "n": len(records),
        "items_digest": items_digest(items),
        "file_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def read_run_items(run_dir: str | Path) -> tuple[FrozenItem, ...]:
    """What an arm reads. Takes the run directory, never the clone."""
    path = Path(run_dir) / ITEMS_FILENAME
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        extra = set(record) - ALLOWED_KEYS
        if extra:
            raise RuntimeError(f"{path} carries forbidden keys {sorted(extra)}")
        out.append(
            FrozenItem(
                item_id=str(record["item_id"]),
                row_index=int(record["row_index"]),
                sequence=normalize(str(record["sequence"])),
            )
        )
    return tuple(out)
