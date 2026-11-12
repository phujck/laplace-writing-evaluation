"""Pour a verified atlas.dataset-manifest/1 using its declared real encoder."""
from __future__ import annotations

import argparse
import contextlib
import sys
import json
from pathlib import Path

from ..dataset import DatasetRefused, load_manifest, pour_dataset
from ..blueprint import GENESIS_GENERATION, GenerationParentRefused
from ..history import SourceRef, SeatRole, ProducerRef
from ..spectral_pour import PourMetadata
from .blueprint import CONTAINER_ROOT, ROOT, _now, _runtime_encoder


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--container-root", type=Path, default=CONTAINER_ROOT)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--parent-generation", default=GENESIS_GENERATION,
                        help="current generation id; genesis is valid only for an empty dataset")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest, args.repo_root)
        declared = Path(manifest["core"]["encoder"]["model_dir"])
        if not declared.is_absolute():
            declared = args.repo_root / declared
        with contextlib.redirect_stdout(sys.stderr):
            encoder, runtime, providers, evidence = _runtime_encoder(32, declared, repo_root=args.repo_root)
        metadata = PourMetadata(
            _now(), SeatRole.EGO, SeatRole.EGO, "atlas-dataset-pour",
            (SourceRef("atlas:dataset-manifest", manifest["manifest_handle"], None),),
            runtime, ProducerRef("atlas", "bge-small-en-v1.5", "dataset-pour"), evidence,
        )
        receipt = pour_dataset(manifest, args.repo_root.resolve(), args.container_root.resolve(), encoder,
                               metadata, parent_generation=args.parent_generation)
        receipt["providers"] = list(providers)
        output = json.dumps(receipt, indent=2, ensure_ascii=False) + "\n"
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(output)
        print(output, end="")
        return 0
    except (DatasetRefused, GenerationParentRefused) as exc:
        print(json.dumps({"status": "REFUSED", "reason": exc.reason,
                          "message": exc.message, **exc.detail}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
