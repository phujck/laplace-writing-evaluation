"""Fresh-process probe for a blueprint generation with a declared encoder.

This tool exists for the durability campaign only.  It opens an already-poured store in a new
interpreter, reconstructs through the public blueprint API and emits the bounded result as JSON.
It never pours or repairs; stale dependencies are warnings alongside banked clause text.
"""
from __future__ import annotations

import argparse
import contextlib
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

from ..blueprint import reconstruct_blueprint
from ..encoders.base import EncoderRuntimeEvidence
from ..encoders.deterministic import SyntheticEncoder
from ..history import ProducerRef, SeatRole, SourceRef
from ..runtime import collect_runtime_receipt
from ..spectral_pour import PourMetadata
from ..store import ConceptricStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--encoder", choices=("synthetic", "bge"), default="synthetic")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--beam", type=int, default=2)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    observed_at = _now()
    manifest = None
    if args.manifest:
        from ..dataset import load_manifest
        manifest = load_manifest(args.manifest, repo_root)
    if args.encoder == "bge":
        from .blueprint import _runtime_encoder
        declared = args.model_dir
        if declared is None and manifest is not None:
            declared = Path(manifest["core"]["encoder"]["model_dir"])
            if not declared.is_absolute():
                declared = repo_root / declared
        with contextlib.redirect_stdout(sys.stderr):
            encoder, runtime, providers, evidence = _runtime_encoder(32, declared, repo_root=repo_root)
    else:
        encoder = SyntheticEncoder()
        runtime = collect_runtime_receipt(repo_root, observed_at=observed_at)
        evidence = EncoderRuntimeEvidence.exact_single_provider(
            encoder.spec, "deterministic-python", "sha256:" + "f" * 64,
        )
        providers = ("deterministic-python",)
    metadata = PourMetadata(
        observed_at,
        SeatRole.EGO,
        SeatRole.EGO,
        "blueprint-cold-fixture-probe",
        (SourceRef(
            "test:blueprint-cold-fixture-probe",
            "sha256:" + "f" * 64,
            "test://blueprint-cold-fixture-probe",
        ),),
        runtime,
        ProducerRef("atlas", args.encoder, "cold-fixture-probe"),
        evidence,
    )
    from ..dataset import extra_authority_files
    extras = extra_authority_files(repo_root) if manifest is not None else ()
    context = (ConceptricStore.authority_context_manifest(
        args.store.resolve(), store_role="blueprint-fixture", allow_git_unavailable=True,
    ) if args.read_only and manifest is None else None)
    result = reconstruct_blueprint(
        ConceptricStore(args.store.resolve(), read_only=args.read_only,
                        extra_authority_files=extras, authority_context=context),
        repo_root,
        args.goal,
        encoder,
        metadata,
        top_k=args.top_k,
        beam=args.beam,
        container_root=(Path(__file__).resolve().parents[3] / "atlas" if manifest else None),   # <checkout>/atlas (R2)
        dataset_roots=({manifest["core"]["dataset_id"]: repo_root} if manifest else None),
    )
    print(json.dumps({
        "encoder_id": encoder.encoder_id,
        "encoder_generation": encoder.spec.spec_id,
        "providers": list(providers),
        "generation_id": result.generation_id,
        "materialization_id": result.materialization_id,
        "cache_hit": result.cache_hit,
        "traversed_cluster_ids": list(result.traversed_cluster_ids),
        "rejected_cluster_ids": list(result.rejected_cluster_ids),
        "results": list(result.results),
        "dependency_frontier": dict(result.dependency_frontier),
        "source_currency": dict(result.source_currency),
    }, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
