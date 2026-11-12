#!/usr/bin/env python3
"""Exhaustive parity of the binary vector sidecar against the legacy JSON store.

The audit re-encoded ``.meaning_vectors.json`` (float64 decimal text) into a
``.npy`` + index pair. The compression claim is only worth making beside a
losslessness claim, and a losslessness claim is only worth making if it is
exhaustive: every node, not a sample.

This producer runs the comparison over the whole index and banks the verdict
with the fingerprints of the three files it read. The number card that serves
the result re-computes those fingerprints at build time and refuses to serve
the banked verdict if any file has moved since it was verified — so a stale
"lossless" claim cannot outlive the store it describes.

  scripts/verify_sidecar_parity.py [--out evidence/.../sidecar_parity.json]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
LEGACY = REPO / ".meaning_vectors.json"
NPY = REPO / ".meaning_vectors.f32.npy"
INDEX = REPO / ".meaning_vectors.index.json"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO / "evidence" / "SELF_AUDIT_2026-08-20"
                                         / "sidecar_parity.json"))
    args = ap.parse_args()

    for p in (LEGACY, NPY, INDEX):
        if not p.exists():
            raise SystemExit(f"missing {p} — parity cannot be verified")

    idx = json.loads(INDEX.read_text(encoding="utf-8"))
    arr = np.load(NPY, mmap_mode="r")
    legacy = json.loads(LEGACY.read_text(encoding="utf-8"))["nodes"]

    # Two populations, kept apart on purpose. The legacy text store is frozen at
    # the moment it was last written; the sidecar keeps moving with the work. A
    # node whose content fingerprint has changed since then SHOULD hold different
    # numbers — it was re-read. Only the unchanged-content population tests the
    # re-encoding itself, and that is the population the losslessness claim is
    # made over. Folding the two together would either hide a real defect or
    # manufacture a fake one, depending on which way the work had moved.
    nodes = idx["nodes"]
    same_content = same_content_exact = 0
    changed_content = changed_content_exact = 0
    absent = 0
    unexpected: list[str] = []
    for key, entry in nodes.items():
        src = legacy.get(key)
        if src is None:
            absent += 1
            continue
        a = np.asarray(arr[entry["row"]], dtype=np.float32)
        b = np.asarray(src["v"], dtype=np.float32)
        equal = bool(a.shape == b.shape and np.array_equal(a, b))
        if entry.get("h") == src.get("h"):
            same_content += 1
            if equal:
                same_content_exact += 1
            elif len(unexpected) < 5:
                unexpected.append(key)
        else:
            changed_content += 1
            changed_content_exact += int(equal)
    exact = same_content_exact + changed_content_exact
    mismatch = (same_content - same_content_exact) + (changed_content - changed_content_exact)
    hash_match, hash_miss = same_content, changed_content
    examples = unexpected

    stored = idx.get("sha256")
    fresh_npy = sha256(NPY)

    out = {
        "what": "exhaustive float32 parity of the binary sidecar against the legacy "
                "JSON store, every node in the index, plus content-fingerprint parity",
        "when": datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="seconds").replace("+00:00", "Z"),
        "counts": {
            "nodes_in_index": len(nodes),
            "compared": exact + mismatch,
            "exact": exact,
            "mismatch": mismatch,
            "fingerprint_match": hash_match,
            "fingerprint_mismatch": hash_miss,
            "absent_from_legacy": absent,
            "unchanged_content": same_content,
            "unchanged_content_exact": same_content_exact,
            "changed_content": changed_content,
            "changed_content_exact": changed_content_exact,
        },
        "the_claim": (
            f"of the {same_content} documents whose content had not changed since the "
            f"text store was last written, {same_content_exact} hold values identical "
            "to the last bit in the binary store"
        ),
        "mismatch_examples": examples,
        "stored_sha256_matches_file": stored == fresh_npy,
        "fingerprints": {
            "meaning_vectors.f32.npy": fresh_npy,
            "meaning_vectors.index.json": sha256(INDEX),
            "meaning_vectors.json": sha256(LEGACY),
        },
        "sizes_bytes": {
            "meaning_vectors.f32.npy": NPY.stat().st_size,
            "meaning_vectors.index.json": INDEX.stat().st_size,
            "meaning_vectors.json": LEGACY.stat().st_size,
        },
        # PASS is about the re-encoding, which is what the claim is about: every
        # unchanged-content node identical, and the sidecar's own recorded
        # checksum still describing the file it sits beside. Nodes that are new
        # or re-read since the text store froze are drift, not damage, and are
        # reported rather than folded into the verdict.
        "verdict": "PASS" if (same_content > 0 and same_content == same_content_exact
                              and stored == fresh_npy) else "FAIL",
    }
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    c = out["counts"]
    print(f"{out['verdict']}  {c['unchanged_content_exact']}/{c['unchanged_content']} "
          f"unchanged-content nodes exact · {c['changed_content']} re-read since the "
          f"text store froze · {c['absent_from_legacy']} added since · stored sha matches "
          f"{out['stored_sha256_matches_file']}")
    print(f"banked -> {dest}")
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
