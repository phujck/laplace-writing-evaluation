#!/usr/bin/env python3
"""Read the historical semantic queue; refuse its retired publication entry points."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from laplace.representation import semantic_cadence  # noqa: E402
from laplace.representation.embedding_health import _read_outer_receipt, validate_fold_candidate

INCREMENTAL_SEED_PATHS = (
    ".meaning_tree.json",
    ".meaning_vectors.f32.npy",
    ".meaning_vectors.index.json",
    ".metric_M.npz",
    ".reembed_timing.jsonl",
    ".residue.jsonl",
    ".self_embeddings.json",
    ".self_graded.json",
    ".upfold_triggers.jsonl",
)


def _run(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int = 1800) -> str:
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command refused ({result.returncode}): {' '.join(command)}\n"
            f"{result.stdout[-4000:]}\n{result.stderr[-4000:]}"
        )
    return result.stdout


def _seed_verified_prior_fold(
    repo_root: Path, worktree: Path, side_refs: dict, *, source_commit: str
) -> dict:
    """Seed incremental caches from the enqueue-pinned F only after full verification."""

    fold = side_refs.get("semantic_fold")
    receipt_object = side_refs.get("semantic_fold_receipt")
    if not fold and not receipt_object:
        return {"state": "COLD", "seeded_paths": 0}
    if not isinstance(fold, str) or not isinstance(receipt_object, str):
        raise RuntimeError("pinned semantic side refs are incomplete")
    observed = semantic_cadence.pinned_side_refs(repo_root, source_commit=source_commit)
    if observed != side_refs:
        raise RuntimeError("semantic side refs moved after enqueue")
    carried = _read_outer_receipt(repo_root, receipt_object)
    outer = {key: value for key, value in carried.items() if key != "receipt_object"}
    validation = validate_fold_candidate(
        repo_root, output_commit=fold, outer_receipt=outer
    )
    if validation.get("status") != "VALIDATED":
        raise RuntimeError("prior semantic fold did not validate for incremental reuse")
    paths = list(INCREMENTAL_SEED_PATHS)
    _run(
        ["git", "restore", f"--source={fold}", "--worktree", "--", *paths],
        cwd=worktree,
        env=dict(os.environ),
    )
    return {
        "state": "VERIFIED-SEEDED",
        "fold": fold,
        "receipt_object": receipt_object,
        "receipt_handle": carried["receipt_handle"],
        "seeded_paths": len(paths),
    }


def _retirement_refusal(generation: str = "") -> dict:
    return {
        "schema_version": "laplace.semantic-cadence-retirement/1",
        "status": "REFUSED", "reason_code": "SEMANTIC-SIDE-REF-CADENCE-RETIRED",
        "reason": "The router consumes the worktree deposit; side-ref publication is retired.",
        "generation": generation, "authority_effect": "none", "blocking": False,
        "owner": "WO-20260914-eh-02-deposit-and-health-read-one-fold",
    }


def _worker(repo_root: Path, generation: str) -> dict:
    return _retirement_refusal(generation)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--enqueue-current", action="store_true")
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--generation", default="")
    args = parser.parse_args()
    if args.worker or args.enqueue_current:
        print(json.dumps(_retirement_refusal(args.generation), sort_keys=True))
        return 2
    print(json.dumps(semantic_cadence.read_state(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
