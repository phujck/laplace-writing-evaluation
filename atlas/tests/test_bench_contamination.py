"""test_bench_contamination.py - the freeze-time atom-density check, and what it refuses.

The check exists because the Phase 2 answer key was found by hand AFTER a scored run, and both
verdict rows told Phase 3 to bank it at mint. So the tests here are mostly about the REFUSAL
firing: a rule that never says no is not a check.

The applicability floor gets its own test because it is the part most likely to be mistaken for a
bypass. It is not one - it is what stops a share computed over four nodes from being reported as
a share - and the test pins the difference by showing that the same contaminated corpus passes
below the floor and refuses above it.
"""

from __future__ import annotations

import pytest
from bench_fixture import DOC, build_bundle, open_bundle

from atlas.bench.contamination import (
    MIN_NODES_FOR_DENSITY,
    OUTLIER_PAIR_SHARE,
    assert_no_outlier,
    outliers,
    report,
    scan,
    total_pairs,
)
from atlas.bench.freeze import anchor_task, freeze_bundle
from atlas.bench.universe import BENCH_FILTERED, SnapshotView
from atlas.errors import ContaminationDetected


@pytest.fixture()
def view(tmp_path):
    return SnapshotView(open_bundle(build_bundle(tmp_path / "snap")), BENCH_FILTERED)


def _task(view, task_id="T1", atoms=None):
    return anchor_task(
        view, task_id=task_id, task_class="current-aim",
        question="What is the next move?",
        atoms=atoms or ["run the widget sweep"], window=None,
        source="HANDOFF.md", truth_date="2026-08-01")


# --- the measurement -------------------------------------------------------

def test_the_scan_finds_the_node_that_holds_the_atom(view):
    rows = scan(view, [_task(view)])
    assert rows, "a task whose atom is in the corpus must produce at least one row"
    assert rows[0].node_id == "HANDOFF.md"
    assert rows[0].pairs == 1


def test_the_denominator_is_one_pair_per_task_atom(view):
    tasks = [_task(view, "T1"), _task(view, "T2", atoms=["run the widget sweep",
                                                        "correctness comes before cost"])]
    assert total_pairs(tasks) == 3


def test_rows_are_ordered_densest_first_and_ties_break_on_node_id(view):
    rows = scan(view, [_task(view, atoms=["run the widget sweep",
                                          "correctness comes before cost"])])
    pairs = [r.pairs for r in rows]
    assert pairs == sorted(pairs, reverse=True)
    for a, b in zip(rows, rows[1:], strict=False):
        if a.pairs == b.pairs:
            assert a.node_id < b.node_id


def test_an_excluded_node_cannot_be_scanned_or_flagged(view):
    """The 'unless it is in the universe exclusions' carve-out, obtained structurally.

    ``node_modules/vendor.md`` mentions the atom and is excluded by the universe, so it is not in
    the view and therefore cannot appear in the scan at all - no second exclusion list to drift.
    """
    rows = scan(view, [_task(view)])
    assert all(not r.node_id.startswith("node_modules/") for r in rows)


# --- the refusal -----------------------------------------------------------

def _wide_bundle(tmp_path, contaminate: bool):
    """A corpus above the applicability floor, optionally carrying an answer-key node."""
    import dataclasses
    import json
    from pathlib import Path

    from atlas.ids import canonical_json, hash_bytes
    from atlas.schema import REFS_ONLY, RecordSnapshot, SnapshotNode
    from atlas.segment import segment_bytes
    from atlas.store import BlobStore, sha256_file, write_atomic, write_jsonl

    root = Path(tmp_path)
    root.mkdir(parents=True, exist_ok=True)
    atoms = [f"the widget sweep runs at cadence {i}" for i in range(10)]
    files = {"HANDOFF.md": DOC.encode("utf-8")}
    # One legitimate home per atom, spread across distinct nodes: no single node is dense.
    for i, atom in enumerate(atoms):
        files[f"notes/note_{i:03d}.md"] = f"# Note {i}\n\n{atom}\n".encode("utf-8")
    # Filler so the corpus clears MIN_NODES_FOR_DENSITY.
    for i in range(MIN_NODES_FOR_DENSITY + 8):
        files[f"filler/f_{i:03d}.md"] = f"# Filler {i}\n\nnothing an atom depends on.\n".encode()
    if contaminate:
        # The answer key: every atom in one file, exactly the shape of the v1 task file.
        key = "# tasks\n\n" + "\n".join(f'{{"q": {i}, "must": "{a}"}}' for i, a in enumerate(atoms))
        files["scripts/answer_key.md"] = key.encode("utf-8")

    store = BlobStore(root / "blobs")
    nodes = []
    for path, data in files.items():
        digest = hash_bytes(data)
        store.put(data)
        nodes.append(SnapshotNode(node_id=path, path=path, kind="md", sealed=False, is_text=True,
                                  read_policy="text", content_hash=digest, content_blob=digest,
                                  size_bytes=len(data)))
    nodes.append(SnapshotNode(node_id="soul/private.md", path="soul/private.md", kind="soul",
                              sealed=True, is_text=False, read_policy="sealed-refs-only",
                              content_hash=REFS_ONLY, content_blob=None, size_bytes=0))
    nodes.sort(key=lambda n: n.node_id)
    write_jsonl(root / "nodes.jsonl", [n.to_dict() for n in nodes])
    spans = []
    for path, data in files.items():
        spans.extend(segment_bytes(path, path, hash_bytes(data), data, 384, 512).spans)
    write_jsonl(root / "spans.jsonl", [s.to_dict() for s in spans])
    report_json = {"soul_paths_with_content": 0, "sealed_spans": 0, "sealed_nodes": 1,
                   "bytes_read_from_sealed": 0, "sealed_prefixes": ["soul/"],
                   "nodes_scanned": len(nodes)}
    write_atomic(root / "seal_report.json",
                 (canonical_json(report_json) + "\n").encode("utf-8"))
    man = RecordSnapshot(
        snapshot_id="", created_ts="2026-08-01T00:00:00+00:00", atlas_schema_version="1",
        exporter_version="1", source_repo="laplace", commit_sha="deadbeef",
        node_count=len(nodes), text_node_count=len(files), sealed_node_count=1,
        asset_node_count=0, total_content_bytes=sum(len(d) for d in files.values()),
        nodes_sha256=sha256_file(root / "nodes.jsonl"),
        seal_report_sha256=sha256_file(root / "seal_report.json"),
        sealed_prefixes=["soul/"], sealed_paths=[], excluded_prefixes=["atlas/stores/"],
        text_extensions=[".md"], node_limit=None, tree_dirty=False,
        dirty_node_count=0, dirty_nodes_hash="sha256:" + "5" * 64)
    man = dataclasses.replace(man, snapshot_id=man.computed_id())
    write_atomic(root / "manifest.json",
                 (json.dumps(man.to_dict(), sort_keys=True, indent=2) + "\n").encode("utf-8"))
    write_atomic(root / "segmentation.json", (json.dumps({
        "generation_id": "sha256:" + "a" * 64, "snapshot_id": man.snapshot_id}) + "\n").encode())
    return SnapshotView(open_bundle(root), BENCH_FILTERED), atoms


def _atom_tasks(view, atoms):
    return [anchor_task(view, task_id=f"T{i:02d}", task_class="topic-descent",
                        question=f"what is cadence {i}?", atoms=[a], window=None,
                        source="notes", truth_date="2026-08-01")
            for i, a in enumerate(atoms)]


def test_an_answer_key_above_the_floor_REFUSES(tmp_path):
    view, atoms = _wide_bundle(tmp_path / "snap", contaminate=True)
    tasks = _atom_tasks(view, atoms)
    with pytest.raises(ContaminationDetected) as exc:
        assert_no_outlier(view, tasks)
    assert exc.value.detail["node_id"] == "scripts/answer_key.md"
    assert exc.value.detail["pairs"] == len(atoms)
    assert exc.value.reason == "bench-contamination-detected"


def test_the_same_corpus_without_the_answer_key_is_clean(tmp_path):
    view, atoms = _wide_bundle(tmp_path / "snap", contaminate=False)
    record = assert_no_outlier(view, _atom_tasks(view, atoms))
    assert record["clean"] is True
    assert record["applicable"] is True
    assert record["outliers"] == []


def test_freeze_refuses_to_mint_over_a_contaminated_view(tmp_path):
    """The whole point: the bundle does not exist, rather than existing and being wrong later."""
    view, atoms = _wide_bundle(tmp_path / "snap", contaminate=True)
    tasks = _atom_tasks(view, atoms)
    with pytest.raises(ContaminationDetected):
        freeze_bundle(view, "sha256:" + "a" * 64, tasks)


def test_freeze_hands_back_the_scan_record_when_asked(tmp_path):
    view, atoms = _wide_bundle(tmp_path / "snap", contaminate=False)
    record: dict = {}
    bundle = freeze_bundle(view, "sha256:" + "a" * 64, _atom_tasks(view, atoms),
                           contamination_scan=record)
    assert bundle.bundle_id
    assert record["clean"] is True
    assert record["contamination_version"] == "atom-density/1"


# --- the applicability floor ----------------------------------------------

def test_below_the_floor_the_check_reports_not_applicable_rather_than_passing(view):
    """A four-node fixture's one document holds every atom and is not contaminated by anything."""
    record = report(view, [_task(view)])
    assert record["nodes_scanned"] < MIN_NODES_FOR_DENSITY
    assert record["applicable"] is False
    assert record["clean"] is False, "not-applicable must never read as a clean bill"
    assert record["outliers"] == []


def test_the_floor_is_the_only_thing_between_pass_and_refuse(tmp_path):
    """Same contaminated corpus, same rule: the floor decides whether the rule is allowed to."""
    view, atoms = _wide_bundle(tmp_path / "snap", contaminate=True)
    tasks = _atom_tasks(view, atoms)
    rows = scan(view, tasks)
    assert outliers(rows), "the answer key is over the share threshold on the raw rows"
    from atlas.bench import contamination
    original = contamination.MIN_NODES_FOR_DENSITY
    try:
        contamination.MIN_NODES_FOR_DENSITY = 10 ** 9      # pretend the corpus is tiny
        assert report(view, tasks)["applicable"] is False
        assert report(view, tasks)["outliers"] == []
    finally:
        contamination.MIN_NODES_FOR_DENSITY = original


def test_the_threshold_is_a_share_of_the_bundles_pairs_not_a_raw_count(tmp_path):
    view, atoms = _wide_bundle(tmp_path / "snap", contaminate=True)
    tasks = _atom_tasks(view, atoms)
    record = report(view, tasks)
    key = next(r for r in record["top"] if r["node_id"] == "scripts/answer_key.md")
    assert key["pair_share"] == pytest.approx(key["pairs"] / record["total_task_atom_pairs"])
    assert key["pair_share"] >= OUTLIER_PAIR_SHARE
