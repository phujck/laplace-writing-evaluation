"""Atlas storage example. No Laplace import inside Atlas.
Based on atlas/tests/test_store.py, copied algorithms only, no test imports.
"""
from __future__ import annotations

def run(root, rec):
    from atlas.store import BlobStore, CompressedHive, append_jsonl, read_jsonl, write_atomic
    from atlas.errors import BlobHashMismatch, BlobMissing, StoreError
    from atlas.ids import hash_bytes
    base = root/"atlas-example"
    base.mkdir()
    blobs = BlobStore(base/"blobs")
    payload = b"An explicitly authored illustrative record.\n"
    key = blobs.put(payload)
    assert key == hash_bytes(payload)
    assert blobs.get(key) == payload and blobs.put(payload) == key
    hive = CompressedHive(base/"hive")
    compressed_key = hive.put(payload*100)
    assert hive.get(compressed_key) == payload*100
    ledger = base/"authored-inputs.jsonl"
    append_jsonl(ledger, [{"sequence":1,"kind":"synthetic-input","value":[1,2,3]}])
    prefix = ledger.read_bytes()
    append_jsonl(ledger, [{"sequence":2,"kind":"local-calculation","sum":6}])
    assert ledger.read_bytes().startswith(prefix)
    rows = list(read_jsonl(ledger))
    assert len(rows) == 2
    rec.save("atlas-jsonl", rows)
    rec.refuses("atlas-missing-blob", BlobMissing, blobs.get, hash_bytes(b"absent"))
    # A separate damaged store leaves the good illustrated record readable.
    damaged = BlobStore(base/"damaged-blobs")
    damaged_key = damaged.put(payload)
    damaged.key_path(damaged_key).write_bytes(b"deliberate test corruption")
    rec.refuses("atlas-corrupt-read", BlobHashMismatch, damaged.get, damaged_key)
    rec.refuses("atlas-corrupt-reput", BlobHashMismatch, damaged.put, payload)
    assert damaged.key_path(damaged_key).read_bytes() == b"deliberate test corruption"
    bad = base/"malformed.jsonl"
    write_atomic(bad, b'{"ok":1}\nnot-json\n')
    rec.refuses("atlas-malformed-jsonl", StoreError, lambda: list(read_jsonl(bad)))
    from . import atlas_history, atlas_snapshot
    history = atlas_history.run(root, rec)
    snapshot = atlas_snapshot.run(root, rec)
    rec.save("atlas-history", history)
    rec.save("atlas-snapshot", snapshot)
    return {"status":"EXECUTED", "blob":key, "compressed_blob":compressed_key,
        "ledger":"workspace/atlas-example/authored-inputs.jsonl",
        "qualification":"JSONL inputs are authored fixtures, not fabricated Atlas events or provider messages.",
        "event_history":history, "snapshot":snapshot,
        "query_reconstruction":"Exact object query and event/index reconstruction exercised. Spectral reconstruction NOT_YET_EXERCISED",
        "gpu":"NOT_RUN: separate explicitly opted-in CUDA toy required, not a benchmark"}
