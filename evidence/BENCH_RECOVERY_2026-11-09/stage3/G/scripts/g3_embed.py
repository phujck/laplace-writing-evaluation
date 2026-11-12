"""Packet G step 3 (one GPU pass per corpus, zero model calls): encode the piece texts with the imported fp16
BGE-small encoder (relational.encoder.load_imported_encoder, doc role, the same organ that banked the leaf vectors,
frames_corpus.encode_vectors:463-470) and write each key's rows as fp16 under G/vectors. The ORT arena is capped at
1.0 GiB (the campaign allows 1.2 GiB). A check key '<corpus>_leafcheck_plain' is compared with the banked rows.

    heavy.sh flock /home/phujck/.local/state/laplace/gpu.lock scripts/laplace-python .../g3_embed.py TEXTS.pkl OUTDIR [keys...]
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np

LAPLACE = Path("/home/phujck/VScodeProjects/laplace")
RF = LAPLACE / "synthetics papers" / "relational-frontend"
sys.path.insert(0, str(RF / "src"))


def main(texts_path: str, outdir: str, keys: list[str]) -> None:
    from relational.encoder import load_imported_encoder
    import torch
    with open(texts_path, "rb") as fh:
        embed = pickle.load(fh)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    enc = load_imported_encoder("cuda", budget_bytes=int(1.0 * 2**30))
    receipt = {"providers": enc.sess.get_providers(), "keys": {}}
    for key in keys or sorted(embed):
        path = out / f"{key}.f16.npy"
        if path.exists():
            receipt["keys"][key] = "exists"
            continue
        t0 = time.perf_counter()
        texts = embed[key]
        parts = []
        tmp = out / f"tmp_{key}"
        tmp.mkdir(exist_ok=True)
        for a in range(0, len(texts), 20000):        # resumable chunks; a chunk that overflows the arena is retried
            cp = tmp / f"{a:08d}.npy"                  # on a fresh session at a smaller batch
            if cp.exists():
                continue
            for batch in (24, 8, 2):
                try:
                    v = enc.embed(texts[a:a + 20000], batch=batch, role="doc").astype(np.float16)
                    break
                except Exception as error:            # noqa: BLE001 - ORT arena overflow on a long-text batch
                    print("retry chunk", a, "batch", batch, type(error).__name__, flush=True)
                    del enc
                    enc = load_imported_encoder("cuda", budget_bytes=int(1.0 * 2**30))
            np.save(cp.with_suffix(".part.npy"), v)
            cp.with_suffix(".part.npy").replace(cp)
            del v
        n = len(texts)
        embed[key] = texts = None                     # free the texts before the rows are joined
        V = np.concatenate([np.load(tmp / f"{a:08d}.npy") for a in range(0, n, 20000)])
        np.save(path, V)
        for f in tmp.glob("*.npy"):
            f.unlink()
        tmp.rmdir()
        receipt["keys"][key] = {"rows": int(V.shape[0]), "seconds": round(time.perf_counter() - t0, 1)}
        print(key, receipt["keys"][key], flush=True)
        del V
    (out / f"receipt_{Path(texts_path).stem}.json").write_text(json.dumps(receipt, indent=1) + "\n")
    print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
