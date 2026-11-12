#!/usr/bin/env python3
"""Vendor the bge-small ONNX weights INTO the repo so reconstruction needs no network.

The reconstructor embeds with ``bge-small-en-v1.5`` via fastembed/ONNX. On an
ephemeral container the model cache is empty on every cold start, and the
canonical download host (huggingface.co) is often off the network egress
allowlist. This vendors the weights into ``models/fastembed/`` (which
``embed_router._vendored_model_path`` extracts + prefers), so the model is present
at clone time and reconstruction runs under ANY network policy, zero phone-home.

Source: the Qdrant fastembed GCS mirror (``storage.googleapis.com``), which hosts
the exact model as a tarball and is reachable where HF is walled off. The tarball
ships an "infinity" ``model_max_length`` sentinel that overflows fastembed's
truncation, so we patch it to the real 512 context before re-packing.

Run once (anywhere GCS is reachable), then commit ``models/fastembed/``:

    python scripts/vendor_embedding_model.py
    git add models/fastembed && git commit

The committed tarball is ~75 MB (under the 100 MB git blob limit, no git-lfs).
``embed_router`` extracts it on first load to ``~/.cache/laplace/fastembed``.
"""

from __future__ import annotations

import json
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEST = REPO / "models" / "fastembed"
TARBALL = DEST / "fast-bge-small-en-v1.5.tar.gz"
GCS_URL = "https://storage.googleapis.com/qdrant-fastembed/fast-bge-small-en-v1.5.tar.gz"
MODEL_SUBDIR = "fast-bge-small-en-v1.5"


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        raw = tmp / "model.tar.gz"
        print(f"[vendor] downloading {GCS_URL}")
        try:
            urllib.request.urlretrieve(GCS_URL, raw)  # noqa: S310 - pinned https GCS url
        except Exception as exc:  # noqa: BLE001
            print(f"[vendor] ERROR: download failed: {exc}", file=sys.stderr)
            print("[vendor] Run where storage.googleapis.com is reachable.", file=sys.stderr)
            return 1
        print(f"[vendor] downloaded {raw.stat().st_size / 1e6:.1f} MB; extracting + patching")
        with tarfile.open(raw) as tf:
            tf.extractall(tmp)
        model_dir = tmp / MODEL_SUBDIR
        tcfg_path = model_dir / "tokenizer_config.json"
        tcfg = json.loads(tcfg_path.read_text())
        # The mirror tarball carries model_max_length = 1e30-ish (HF "very large"
        # sentinel) and no max_length, which overflows tokenizer.enable_truncation.
        # bge-small's true context is 512 (config.json max_position_embeddings).
        if int(tcfg.get("model_max_length", 0)) > 1_000_000:
            tcfg["model_max_length"] = 512
            tcfg_path.write_text(json.dumps(tcfg, indent=2))
            print("[vendor] patched model_max_length -> 512")
        if TARBALL.exists():
            TARBALL.unlink()
        with tarfile.open(TARBALL, "w:gz") as tf:
            tf.add(model_dir, arcname=MODEL_SUBDIR)

    # Drop the placeholder once real weights are vendored.
    keep = DEST / ".gitkeep"
    if keep.exists():
        keep.unlink()

    size = TARBALL.stat().st_size
    print(f"[vendor] DONE: {TARBALL.relative_to(REPO)} ({size / 1e6:.1f} MB)")
    print("[vendor] Now: git add models/fastembed && git commit")
    if size > 100e6:
        print("[vendor] WARNING: >100 MB exceeds the git blob limit; needs git-lfs.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
