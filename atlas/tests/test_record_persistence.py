"""test_record_persistence.py - ingestion builds the structure once and STORES it.

Every claim the packet makes is a command here. The two fixture proofs - a segment is a pure
function of one item, and a segment cut alone equals the segment cut inside a batch - are the
ones that let the run-time path carry NO check of either: purity is proved once, here, and the
mint keeps only the two cheap gates (a row's witness is its own item's span; an edge's two
endpoints are one item's rows).

The heavy fixtures ingest two LongMemEval haystacks and two QASPER papers at rung (ab), which
is the smallest draw on which relations, located edges and shared dictionaries all exist.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

from atlas.ids import hash_bytes
from atlas.record import segments as S
from atlas.record.diff import item_bytes_cache_key
from atlas.record.errors import MalformedSource
from atlas.record.extract import extractor_roster_hash
from atlas.record.ingest import longmem, qasper
from atlas.record.json_spans import iter_array_items
from atlas.store import BlobHashMismatch

ROOT = Path(__file__).resolve().parents[2]
ROSTER = extractor_roster_hash()
HAYSTACKS = 2
PAPERS = 2


def _raws(count: int = HAYSTACKS) -> list[bytes]:
    return [raw for _, _, raw in iter_array_items(longmem.DATASET_PATH, limit=count)]


def _cut_in_order(raws: list[bytes]) -> dict[str, str]:
    """Ingest the given haystacks in the given order; return item hash -> segment key."""
    from atlas.record.diff import apply_case

    declared = longmem.declaration("ab")
    ingestion = S.Ingestion(declared)
    ingestion.store.share_dictionary("question_id", [k.kind for k in declared.row_kinds])
    for raw in raws:
        key = item_bytes_cache_key(raw, longmem.EXTRACTOR_ID, declared.declaration_hash)
        with ingestion.item(key, item_bytes=raw, blob_handles=(hash_bytes(raw),),
                            extracts=True):
            apply_case(ingestion, raw)
    cut, _ = S.cut_segments(ingestion, extractor_roster_hash=ROSTER)
    return {mark.item_content_hash: hash_bytes(payload) for mark, payload in cut}


@pytest.fixture(scope="module")
def longmem_store(tmp_path_factory):
    root = tmp_path_factory.mktemp("longmem-record")
    store = S.SegmentStore(root)
    ingestion = longmem.ingest(histories=HAYSTACKS, rungs="ab", segments=store)
    return store, ingestion, ingestion.persistence, S.content_digests(ingestion)


# --------------------------------------------------------------- (1) purity
def test_a_segment_is_a_pure_function_of_one_item():
    """Two haystacks in either order give the same two segment keys (must-achieve 1)."""
    raws = _raws()
    forward = _cut_in_order(raws)
    backward = _cut_in_order(list(reversed(raws)))
    assert forward == backward
    assert len(forward) == HAYSTACKS


def test_a_segment_cut_alone_equals_the_segment_cut_in_a_batch():
    """The property a process pool rests on: the item is the whole context (must-achieve 5)."""
    ingestion = longmem.ingest(histories=HAYSTACKS, rungs="ab")
    cut, _ = S.cut_segments(ingestion, extractor_roster_hash=ROSTER)
    batch = {mark.item_content_hash: hash_bytes(payload) for mark, payload in cut}
    alone = {}
    for raw in _raws():
        _, payload = S.segment_for_item("longmem", raw, rungs="ab",
                                        extractor_roster_hash=ROSTER)
        alone[S.Segment.decode(payload).header["item_content_hash"]] = hash_bytes(payload)
    assert alone == batch


def test_a_segment_holds_no_global_code_or_ordinal(longmem_store):
    """Nothing inside a segment names the store it was cut from."""
    store, _, _, _ = longmem_store
    segment = S.Segment.decode(store.get(store.rows()[0]["segment_key"]))
    spans = segment.arrays["spans"]
    assert spans[:, 0].max() < len(segment.header["blobs"])
    for kind, entry in segment.header["rows"].items():
        witness = segment.arrays[f"rows.{kind}.__witness"]
        assert int(witness.max()) < segment.header["span_count"]
        assert int(witness.min()) >= 0
    for kind, entry in segment.header["relations"].items():
        endpoints = segment.arrays[f"rel.{kind}.endpoints"]
        for column, local in ((0, 1), (2, 3)):
            names = segment.header["kind_index"]
            for code in np.unique(endpoints[:, column]):
                owner = names[int(code)]
                assert int(endpoints[endpoints[:, column] == code][:, local].max()) \
                    < segment.header["rows"][owner]["count"]


def test_the_span_map_refuses_a_span_that_is_not_the_items_own():
    """The first run-time gate, directly: the lookup checks what it found. O(k log n)."""
    spans = np.array([[0, 0, 5], [0, 5, 9], [0, 9, 12]], dtype=np.int64)
    mapping = S._SpanMap(np.array([0, 1], dtype=np.int64), spans)
    assert mapping.of(np.array([1, 0], dtype=np.int64)).tolist() == [1, 0]
    with pytest.raises(MalformedSource):
        mapping.of(np.array([2], dtype=np.int64))


# --------------------------------------------------------------- (2) the manifest
def test_the_manifest_is_one_thin_row_per_item(longmem_store):
    store, ingestion, receipt, _ = longmem_store
    rows = store.rows()
    assert len(rows) == HAYSTACKS == receipt.manifest_rows_appended
    declared = ingestion.declaration
    for row in rows:
        assert row["schema_version"] == S.MANIFEST_ROW_SCHEMA
        assert row["dataset_declaration_hash"] == declared.declaration_hash
        assert row["extractor_roster_hash"] == ROSTER
        assert row["segment_key"] == hash_bytes(store.get(row["segment_key"]))
        assert row["supersedes"] is None
        assert set(row) == {"schema_version", "dataset_id", "dataset_declaration_hash",
                            "extractor_roster_hash", "item_content_hash", "item_span",
                            "item_cache_key", "segment_key", "segment_bytes", "blobs",
                            "spans", "rows", "relations", "supersedes"}
    assert sum(row["rows"] for row in rows) == ingestion.store.row_count
    assert sum(row["relations"] for row in rows) == len(ingestion.relations)


def test_the_manifest_names_the_records_own_identity_and_no_second_one(longmem_store):
    store, ingestion, _, _ = longmem_store
    meta = store.meta()
    assert meta["dataset_declaration_hash"] == ingestion.declaration.declaration_hash
    assert {"column": "question_id",
            "kinds": sorted(k.kind for k in ingestion.declaration.row_kinds)} in \
        meta["shared_dictionaries"]


# --------------------------------------------------------------- (3) open
def test_open_in_this_process_rebuilds_the_same_record(longmem_store):
    store, ingestion, _, digests = longmem_store
    opened = S.open_record(store, longmem.declaration("ab"), rung=1)
    assert opened.receipt.extractions == 0 and opened.receipt.parses == 0
    assert opened.receipt.source_reads == 0
    assert opened.receipt.digests == digests
    assert opened.receipt.rows == ingestion.store.row_count
    assert opened.receipt.relations == len(ingestion.relations)
    tables = sum(1 for t in opened.ingestion.store.tables.values() if len(t))
    kinds = sum(1 for t in opened.ingestion.relations.kinds.values() if len(t))
    assert opened.receipt.host_to_device_copies == 1 + tables + kinds


def test_open_in_a_second_process_rebuilds_the_same_record(longmem_store):
    """Must-achieve 3, in a process that never saw the source file."""
    store, _, _, digests = longmem_store
    code = (
        "import json\n"
        "from pathlib import Path\n"
        "from atlas.record import segments as S\n"
        "from atlas.record.ingest import longmem\n"
        f"opened = S.open_record(S.SegmentStore(Path({str(store.root)!r})),"
        " longmem.declaration('ab'), rung=1)\n"
        "print(json.dumps(opened.receipt.as_dict()))\n"
    )
    result = subprocess.run([str(ROOT / "scripts" / "laplace-python"), "-c", code],  # pool-once: the SECOND PROCESS is the claim under test - one per test, never per item
                            capture_output=True, text=True, cwd=str(ROOT), timeout=600)
    assert result.returncode == 0, result.stderr[-2000:]
    receipt = json.loads(result.stdout.strip().splitlines()[-1])
    assert receipt["extractions"] == 0
    assert receipt["parses"] == 0
    assert receipt["source_reads"] == 0
    assert receipt["digests"] == digests


def test_a_rows_identity_and_its_span_survive_the_process_boundary(longmem_store):
    """HANDLES SURVIVE THE PROCESS BOUNDARY: an answer minted before a restart names its row.

    Twenty rows and twenty relations at random in this process, each recorded as its B.2
    identity plus its witness ADDRESS (content handle, start, end) and the digest of the bytes
    there; the second process resolves each identity in what it opened and must find the same
    address and the same bytes, and must find a relation instance of the same kind between the
    two endpoint IDENTITIES with the same witness addresses. Ordinals may differ between the
    processes - the persisted record stores an item's DISTINCT byte ranges - identities may not.

    This is the test that fails on the code before 2026-09-22: with the span ORDINAL inside
    ``row_id``, 5,186 of 33,373 rows at 10 haystacks changed identity across the boundary
    (every row of a kind declaring a span_ref field) while the record's content digest stayed
    equal. The driver that measures it at full size, on both benchmarks, is
    evidence/ATLAS_PROGRAMME/waves/J1-join/A1/A1_rowids.py.
    """
    store, ingestion, _, _ = longmem_store
    driver = ROOT / "evidence/ATLAS_PROGRAMME/waves/J1-join/A1/A1_rowids.py"
    checker = _import_driver(driver)

    rows, relations = checker.claim(ingestion, rows=20, relations=20)
    assert len(rows) == 20 and len(relations) == 20
    payload = {"rows": rows, "relations": relations}
    handed = store.root.parent / "identity-claims.json"
    handed.write_text(json.dumps(payload), encoding="utf-8")

    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from atlas.record import segments as S\n"
        "from atlas.record.ingest import longmem\n"
        f"sys.path.insert(0, {str(driver.parent)!r})\n"
        "import A1_rowids as R\n"
        f"opened = S.open_record(S.SegmentStore(Path({str(store.root)!r})),"
        " longmem.declaration('ab'), rung=1)\n"
        f"claims = json.loads(Path({str(handed)!r}).read_text())\n"
        "checked_rows, checked_relations = R.check(opened.ingestion, claims)\n"
        "print(json.dumps({'rows': checked_rows, 'relations': checked_relations}))\n"
    )
    result = subprocess.run([str(ROOT / "scripts" / "laplace-python"), "-c", code],  # pool-once: the SECOND PROCESS is the claim under test - one per test, never per item
                            capture_output=True, text=True, cwd=str(ROOT), timeout=900,
                            env=dict(os.environ, A1_ROWIDS_IMPORTED="1"))
    assert result.returncode == 0, result.stderr[-3000:]
    checked = json.loads(result.stdout.strip().splitlines()[-1])
    assert all(row["identity_resolves"] for row in checked["rows"]), checked["rows"]
    assert all(row["same_address"] for row in checked["rows"]), checked["rows"]
    assert all(row["same_bytes"] for row in checked["rows"]), checked["rows"]
    assert all(rel["endpoint_identities_resolve"] for rel in checked["relations"])
    assert all(rel["instance_found"] for rel in checked["relations"])
    assert all(rel["same_witness_addresses"] for rel in checked["relations"])


def _import_driver(path: Path):
    """The deposited driver, imported as a module so the test and the report share one check."""
    import importlib.util

    os.environ["A1_ROWIDS_IMPORTED"] = "1"
    spec = importlib.util.spec_from_file_location("a1_rowids_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_open_calls_no_extractor_and_no_parser(longmem_store, monkeypatch):
    """The receipt's two zeros are structural: poison every way to extract or parse, then open.

    The receipt reads ``extractions`` and ``parses`` off ``Ingestion.counters``, which only
    ``Ingestion.item()`` ever raises - so a zero there says no item was opened, not that a
    literal was written. This is the fixture proof behind it, and it is why the open path
    carries no run-time check of its own: every grammar of the roster, the ingester's per-item
    parse and extraction entry points, its whole ``ingest`` and the source scanner all raise if
    they are called, and the open still returns the same digests.
    """
    from atlas.record import extract as X
    from atlas.record import json_spans

    def poison(name):
        def refuse(*_args, **_kwargs):
            raise AssertionError(f"open_record called {name}")
        return refuse

    for name in ("proper_nouns", "reference_markers", "quantities", "temporal_expressions",
                 "state_claims", "alias_pairs", "locator_for_json_string"):
        monkeypatch.setattr(X, name, poison(f"extract.{name}"))
    for name in ("_ingest_case", "_extract_case", "ingest", "read_gold"):
        monkeypatch.setattr(longmem, name, poison(f"longmem.{name}"))
    for name in ("iter_array_items", "iter_object_members"):
        monkeypatch.setattr(json_spans, name, poison(f"json_spans.{name}"))

    store, _, _, digests = longmem_store
    opened = S.open_record(store, longmem.declaration("ab"), rung=1)
    assert opened.receipt.extractions == 0 and opened.receipt.parses == 0
    assert opened.receipt.source_reads == 0
    assert opened.receipt.digests == digests


def test_the_opened_record_can_still_read_its_own_witness_bytes(longmem_store):
    store, ingestion, _, _ = longmem_store
    opened = S.open_record(store, longmem.declaration("ab"), rung=1)
    table = opened.ingestion.store.table("turn")
    handle, start, end = opened.ingestion.spans.address(int(table.witness_span[0]))
    assert opened.ingestion.blobs.read(handle, start, end) == \
        ingestion.blobs.read(handle, start, end)


# --------------------------------------------------------------- (4) the cache
def test_the_extraction_cache_is_the_segment_store(tmp_path):
    """Re-ingesting the same source extracts nothing and parses nothing (must-achieve 4)."""
    store = S.SegmentStore(tmp_path / "record")
    first = longmem.ingest(histories=HAYSTACKS, rungs="ab", segments=store)

    again = longmem.ingest(histories=HAYSTACKS, rungs="ab", segments=store)
    assert again.counters["extractions"] == 0
    assert again.counters["item_parses"] == 0
    assert again.counters["segment_hits"] == HAYSTACKS
    assert S.content_digests(again) == S.content_digests(first)

    receipt = again.persistence
    assert receipt.segments_written == 0
    assert receipt.manifest_rows_appended == 0
    assert receipt.bytes_written == 0
    assert store.cache_index().keys() == {row["item_cache_key"] for row in store.rows()}


# --------------------------------------------------------------- (6) change
def test_a_changed_corpus_writes_exactly_one_segment_and_one_row(tmp_path):
    store = S.SegmentStore(tmp_path / "record")
    longmem.ingest(histories=HAYSTACKS, rungs="ab", segments=store)
    before = store.persisted_bytes()

    grown = longmem.ingest(histories=HAYSTACKS + 1, rungs="ab", segments=store)
    assert grown.counters["extractions"] == 1
    assert grown.counters["segment_hits"] == HAYSTACKS
    receipt = grown.persistence
    assert receipt.segments_written == 1
    assert receipt.manifest_rows_appended == 1
    assert receipt.segments_total == HAYSTACKS + 1
    assert 0 < receipt.bytes_written == store.persisted_bytes() - before

    opened = S.open_record(store, longmem.declaration("ab"), rung=1)
    cold = longmem.ingest(histories=HAYSTACKS + 1, rungs="ab")
    assert opened.receipt.digests == S.content_digests(cold)


# --------------------------------------------------------------- (7) corruption
def test_one_flipped_byte_in_the_hive_refuses_with_its_key(tmp_path):
    store = S.SegmentStore(tmp_path / "record")
    longmem.ingest(histories=HAYSTACKS, rungs="ab", segments=store)
    key = store.rows()[0]["segment_key"]
    path = store.hive.key_path(key)
    poisoned = bytearray(path.read_bytes())
    poisoned[len(poisoned) // 2] ^= 0x01
    path.write_bytes(bytes(poisoned))
    with pytest.raises(BlobHashMismatch) as refusal:
        S.open_record(store, longmem.declaration("ab"), rung=1)
    assert key in str(refusal.value)


# --------------------------------------------------------------- (5) per-item isolation
def test_the_item_is_the_whole_context_of_its_segment():
    """What must-achieve (5) rests on, with the pool WITHDRAWN: cutting an item alone, in any
    order, gives the segment the batch gives - so items could be cut anywhere.

    The pool itself is gone (the measurement that withdrew it:
    evidence/ATLAS_PROGRAMME/waves/J1-join/A1/pool_withdrawn.json - four children 1.05x, each
    holding a CUDA context). This is the property, tested without it, and it is also the
    guard against the pool being re-added as an unreachable organ.
    """
    assert not hasattr(S, "segments_in_parallel")
    raws = _raws()
    forward = [S.segment_for_item("longmem", raw, rungs="ab", extractor_roster_hash=ROSTER)
               for raw in raws]
    backward = [S.segment_for_item("longmem", raw, rungs="ab", extractor_roster_hash=ROSTER)
                for raw in reversed(raws)]
    assert [key for key, _ in forward] == [key for key, _ in reversed(backward)]
    assert [hash_bytes(payload) for _, payload in forward] == \
        [hash_bytes(payload) for _, payload in reversed(backward)]


# --------------------------------------------------------------- the other benchmark
@pytest.mark.skipif(not qasper.available("dev"), reason="QASPER dev split is not on disk")
def test_qasper_round_trips_through_its_segments(tmp_path):
    store = S.SegmentStore(tmp_path / "record")
    ingestion = qasper.ingest("dev", papers=PAPERS, rungs="ab", segments=store)
    assert ingestion.persistence.segments_written == PAPERS
    opened = S.open_record(store, qasper.declaration("ab"), rung=1)
    assert opened.receipt.digests == S.content_digests(ingestion)
    assert opened.receipt.extractions == opened.receipt.parses == 0

    again = qasper.ingest("dev", papers=PAPERS, rungs="ab", segments=store)
    assert again.counters["extractions"] == 0 and again.counters["item_parses"] == 0
    assert S.content_digests(again) == S.content_digests(ingestion)


@pytest.mark.skipif(not qasper.available("dev"), reason="QASPER dev split is not on disk")
def test_qasper_segments_are_pure_in_the_paper():
    papers = [(item.raw, item.paper_id) for item in qasper.iter_papers("dev", limit=PAPERS)]
    forward = [S.segment_for_item("qasper", raw, rungs="ab", item_id=paper_id,
                                  extractor_roster_hash=ROSTER) for raw, paper_id in papers]
    backward = [S.segment_for_item("qasper", raw, rungs="ab", item_id=paper_id,
                                   extractor_roster_hash=ROSTER)
                for raw, paper_id in reversed(papers)]
    assert sorted(hash_bytes(p) for _, p in forward) == \
        sorted(hash_bytes(p) for _, p in backward)
