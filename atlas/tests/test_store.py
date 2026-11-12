"""test_store.py - atomic writes, append-only jsonl, and blob addressing that verifies on read."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import atlas.store as store_module
from atlas.errors import BlobHashMismatch, BlobMissing, StoreError
from atlas.ids import hash_bytes
from atlas.store import (
    BlobStore,
    CompressedHive,
    append_jsonl,
    jsonl_bytes,
    read_jsonl,
    sha256_file,
    write_atomic,
    write_jsonl,
)


def test_write_atomic_leaves_no_temp_file(tmp_path):
    target = tmp_path / "deep" / "file.bin"
    write_atomic(target, b"payload")
    assert target.read_bytes() == b"payload"
    assert list(tmp_path.rglob("*.tmp")) == []


def test_write_atomic_replaces_in_place(tmp_path):
    target = tmp_path / "f.bin"
    write_atomic(target, b"one")
    write_atomic(target, b"two")
    assert target.read_bytes() == b"two"


def test_write_atomic_fsyncs_the_directory_after_replace(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(store_module, "_fsync_directory", lambda path: called.append(path))
    target = tmp_path / "durable" / "file.bin"

    write_atomic(target, b"payload")

    assert called == [target.parent]


def test_jsonl_bytes_is_canonical_and_newline_terminated():
    assert jsonl_bytes([{"b": 1, "a": 2}]) == b'{"a":2,"b":1}\n'


def test_write_and_read_jsonl_round_trips(tmp_path):
    rows = [{"i": i, "name": f"n{i}"} for i in range(5)]
    path = tmp_path / "rows.jsonl"
    assert write_jsonl(path, rows) == 5
    assert list(read_jsonl(path)) == rows


def test_append_jsonl_is_append_only(tmp_path):
    path = tmp_path / "log.jsonl"
    append_jsonl(path, [{"a": 1}])
    append_jsonl(path, [{"a": 2}, {"a": 3}])
    assert [r["a"] for r in read_jsonl(path)] == [1, 2, 3]


def test_read_jsonl_refuses_a_malformed_row(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"a":1}\nnot json\n', encoding="utf-8")
    with pytest.raises(StoreError) as exc:
        list(read_jsonl(path))
    assert exc.value.reason == "store-error"
    assert exc.value.detail["line"] == 2


def test_sha256_file_matches_hash_bytes(tmp_path):
    path = tmp_path / "x.bin"
    data = b"a" * 5000
    path.write_bytes(data)
    assert sha256_file(path) == hash_bytes(data)


def test_blob_store_is_content_addressed(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    key = store.put(b"hello")
    assert key == hash_bytes(b"hello")
    assert store.has(key)
    assert store.get(key) == b"hello"
    # putting the same bytes again is the same key and does not duplicate the file
    assert store.put(b"hello") == key
    assert len(list((tmp_path / "blobs").rglob("*"))) == 2      # one shard dir, one blob


def test_concurrent_identical_blob_puts_share_content_without_temp_collision(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    payload = (b"one immutable author turn\n" * 80_000) + b"end"
    workers = 16
    barrier = threading.Barrier(workers)

    def put() -> str:
        barrier.wait()
        return store.put(payload)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        handles = list(pool.map(lambda _index: put(), range(workers)))

    assert set(handles) == {hash_bytes(payload)}
    assert store.get(handles[0]) == payload
    assert list((tmp_path / "blobs").rglob("*.tmp")) == []


def test_blob_store_shards_by_two_hex_characters(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    key = store.put(b"payload")
    hexd = key.split(":", 1)[1]
    assert store.key_path(key) == tmp_path / "blobs" / hexd[:2] / hexd


def test_blob_store_refuses_a_missing_blob(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    with pytest.raises(BlobMissing) as exc:
        store.get(hash_bytes(b"absent"))
    assert exc.value.reason == "store-blob-missing"


def test_blob_store_refuses_corrupted_bytes(tmp_path):
    store = BlobStore(tmp_path / "blobs")
    key = store.put(b"original")
    store.key_path(key).write_bytes(b"tampered")
    with pytest.raises(BlobHashMismatch) as exc:
        store.get(key)
    assert exc.value.reason == "store-blob-hash-mismatch"


@pytest.mark.parametrize("corruption", [b"", b"tampered", b"original-extra"])
def test_duplicate_put_verifies_current_bytes_without_repair(tmp_path, corruption):
    store = BlobStore(tmp_path / "blobs")
    key = store.put(b"original")
    path = store.key_path(key)
    original_stat = path.stat()
    assert store.put(b"original") == key
    assert path.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert path.stat().st_ino == original_stat.st_ino
    path.write_bytes(corruption)
    corrupted_stat = path.stat()
    with pytest.raises(BlobHashMismatch) as exc:
        store.put(b"original")
    assert exc.value.reason == "store-blob-hash-mismatch"
    assert path.read_bytes() == corruption
    assert path.stat().st_mtime_ns == corrupted_stat.st_mtime_ns


def test_duplicate_put_checks_all_chunks_and_hashes_input_once(tmp_path, monkeypatch):
    import atlas.store as module
    data = b"x" * (3 * 64 * 1024 + 17)
    store = BlobStore(tmp_path / "blobs")
    key = store.put(data)
    calls = []
    original = module.hash_bytes
    monkeypatch.setattr(module, "hash_bytes", lambda value: calls.append(len(value)) or original(value))
    assert store.put(data) == key
    assert calls == [len(data)]
    changed = bytearray(data);changed[-1] = ord("y")
    store.key_path(key).write_bytes(changed)
    with pytest.raises(BlobHashMismatch):
        store.put(data)


def test_compressed_hive_addresses_uncompressed_content_and_deduplicates(tmp_path):
    hive = CompressedHive(tmp_path / "hive")
    data = (b"same canonical envelope " * 200) + b"end"
    key = hive.put(data)
    path = hive.key_path(key)

    assert key == hash_bytes(data)
    assert hive.put(data) == key
    assert hive.get(key) == data
    assert path.suffix == ".zlib"
    assert path.stat().st_size < len(data)
    assert len(list((tmp_path / "hive").rglob("*.zlib"))) == 1


def test_compressed_hive_refuses_missing_truncated_and_wrong_content(tmp_path):
    hive = CompressedHive(tmp_path / "hive")
    absent = hash_bytes(b"absent")
    with pytest.raises(BlobMissing):
        hive.get(absent)

    key = hive.put(b"original" * 100)
    path = hive.key_path(key)
    path.write_bytes(path.read_bytes()[:4])
    with pytest.raises(BlobHashMismatch, match="truncated"):
        hive.get(key)

    import zlib

    path.write_bytes(zlib.compress(b"different"))
    with pytest.raises(BlobHashMismatch, match="does not match"):
        hive.get(key)
    with pytest.raises(BlobHashMismatch, match="does not match"):
        hive.put(b"original" * 100)
