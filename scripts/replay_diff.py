#!/usr/bin/env python3
"""Replay a historical fold input delta in an isolated worktree.

The worktree starts at each target commit's parent. Only source-bearing inputs from
parent..target are applied; the fold's own outputs remain at the parent's BEFORE bytes.
The current checkout's deposit implementation then runs against that reconstructed root.
Every repeat starts from a fresh worktree, so the diff is held constant.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "tests" / ".scratch-odiff-a"

_OUTPUT_PATHS = {
    ".meaning_tree.json", ".metric_M.npz", ".metric_M.receipt.json",
    ".reembed_timing.jsonl", ".residue.jsonl", ".self_embeddings.json",
    ".self_graded.json", ".upfold_triggers.jsonl", ".wire_proposals.jsonl",
    ".wire_verdicts.jsonl", ".learned_keywords.json", ".escalate_briefs.json",
    "SELF_GRADED_INDEX.md", "SELF_SHARD_INDEX.md", "contract/journal.jsonl",
    "contract/act_costs.jsonl",
}


def _git(*args: str, cwd: Path = ROOT, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=text)


def _resolve_commits(specs: list[str]) -> list[str]:
    commits: list[str] = []
    for spec in specs:
        if ".." in spec:
            values = _git("rev-list", "--reverse", spec).stdout.splitlines()
        else:
            values = [_git("rev-parse", f"{spec}^{{commit}}").stdout.strip()]
        for value in values:
            if value and value not in commits:
                commits.append(value)
    return commits


def _input_paths(parent: str, commit: str) -> list[str]:
    raw = _git("diff", "--name-only", "-z", parent, commit, text=False).stdout
    paths = [part.decode("utf-8", errors="surrogateescape") for part in raw.split(b"\0") if part]
    return [path for path in paths
            if path not in _OUTPUT_PATHS and Path(path).name not in _OUTPUT_PATHS]


def _apply_input_diff(worktree: Path, parent: str, commit: str, paths: list[str]) -> int:
    if not paths:
        return 0
    return len(_git("diff", "--binary", parent, commit, "--", *paths, text=False).stdout)


def _extract_archive(commit: str, destination: Path, paths: list[str] | None = None) -> None:
    command = ["git", "-C", str(ROOT), "archive", commit]
    if paths:
        command += ["--", *paths]
    producer = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert producer.stdout is not None
    consumer = subprocess.run(
        ["tar", "-x", "-C", str(destination)],
        stdin=producer.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    producer.stdout.close()
    producer_stderr = producer.stderr.read() if producer.stderr is not None else b""
    producer_rc = producer.wait()
    if producer_rc or consumer.returncode:
        raise RuntimeError(
            "failed to reconstruct archived tree: "
            + (producer_stderr + consumer.stderr).decode("utf-8", errors="replace")[-1000:]
        )


def _checkout_with_parent_outputs(worktree: Path, parent: str, commit: str) -> None:
    """Materialize target inputs with every deposit output reset to its parent version."""
    worktree.mkdir(parents=True)
    _extract_archive(commit, worktree)
    parent_outputs = []
    for name in sorted(_OUTPUT_PATHS):
        path = worktree / name
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        probe = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{parent}:{name}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if probe.returncode == 0:
            parent_outputs.append(name)
    if parent_outputs:
        _extract_archive(parent, worktree, parent_outputs)


def _last_timing_row(worktree: Path) -> dict:
    path = worktree / ".reembed_timing.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    if not rows:
        raise RuntimeError("deposit returned without a timing row")
    return rows[-1]


def _one_run(commit: str, parent: str, paths: list[str], run_index: int) -> dict:
    worktree = SCRATCH / f"{commit[:12]}-{run_index}"
    _checkout_with_parent_outputs(worktree, parent, commit)
    try:
        patch_bytes = _apply_input_diff(worktree, parent, commit, paths)
        env = os.environ.copy()
        for name in ("LAPLACE_NO_SPECTRAL", "LAPLACE_NO_SPECTRAL_GPU",
                     "LAPLACE_EMBED_NO_GPU", "LAPLACE_STATE"):
            env.pop(name, None)
        env.update({
            "LAPLACE_REQUIRE_GPU": "1",
            "LAPLACE_REEMBED_ROOT": str(worktree),
            "LAPLACE_STATE": str(worktree / "contract"),
            "LAPLACE_FALLBACK_LOG": str(worktree / ".fallback_events.jsonl"),
            "LAPLACE_COST_SINCE_COMMIT": parent,
            "LAPLACE_COST_HEAD_COMMIT": commit,
            "LAPLACE_COST_DIFF_JSON": json.dumps({"files": paths, "bytes": patch_bytes}),
            "LAPLACE_DECLARED_N_REASON": (
                f"replay of {len(paths)} source-bearing paths from {parent[:12]}..{commit[:12]}; "
                "fold outputs held at parent bytes"
            ),
        })
        run = subprocess.run(
            ["/usr/bin/python3", str(ROOT / "scripts" / "reembed.py")],
            cwd=worktree, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True,
        )
        if run.returncode:
            raise RuntimeError(f"deposit rc={run.returncode}:\n{run.stdout[-3000:]}")
        row = _last_timing_row(worktree)
        observed_d = (row.get("diff") or {}).get("D")
        seconds = row.get("seconds", row.get("total"))
        cost_row = {key: row.get(key) for key in (
            "act", "act_id", "ts", "diff", "io", "bytes_read", "bytes_written",
            "files_touched", "seconds", "phases", "declared_N_reason",
        )}
        return {
            "run": run_index,
            "seconds": seconds,
            "observed_D": observed_d,
            "cost_per_unit_diff": (seconds / observed_d
                                   if isinstance(observed_d, int) and observed_d > 0 else None),
            "io": row.get("io"),
            "receipt_bytes": len((worktree / ".reembed_timing.jsonl").read_bytes()),
            "declared_input_files": len(paths),
            "declared_patch_bytes": patch_bytes,
            "cost_row": cost_row,
        }
    finally:
        shutil.rmtree(worktree, ignore_errors=True)


def _stability(runs: list[dict]) -> dict:
    if len(runs) < 2:
        return {"status": "UNASSESSED", "reason": "repeat count is one"}
    first, second = runs[0], runs[1]
    base = max(float(first["seconds"]), float(second["seconds"]), 1e-12)
    wall_delta = abs(float(first["seconds"]) - float(second["seconds"])) / base
    byte_keys = ("io", "receipt_bytes", "declared_patch_bytes")
    bytes_equal = all(first.get(key) == second.get(key) for key in byte_keys)
    return {"status": "PASS" if wall_delta <= 0.10 and bytes_equal else "FAIL",
            "wall_fraction": round(wall_delta, 6), "within_10_percent": wall_delta <= 0.10,
            "byte_counts_exact": bytes_equal}


def replay(commits: list[str], repeat: int = 1) -> dict:
    if SCRATCH.exists():
        if any(SCRATCH.iterdir()):
            raise RuntimeError(f"scratch is not empty; refusing to erase it: {SCRATCH}")
        SCRATCH.rmdir()
    SCRATCH.mkdir(parents=True)
    results = []
    try:
        for commit in commits:
            parent = _git("rev-parse", f"{commit}^").stdout.strip()
            paths = _input_paths(parent, commit)
            runs = [_one_run(commit, parent, paths, index + 1) for index in range(repeat)]
            results.append({"commit": commit, "parent": parent, "input_paths": paths,
                            "runs": runs, "stability": _stability(runs)})
    finally:
        if SCRATCH.exists() and not any(SCRATCH.iterdir()):
            SCRATCH.rmdir()
    return {"schema_version": "laplace.replay-diff/1", "implementation": str(ROOT),
            "commits": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commits", nargs="+", help="commit(s) or rev-list ranges")
    parser.add_argument("--repeat", type=int, default=1,
                        help="fresh replays per commit; two enables the 10%%/exact-byte gate")
    args = parser.parse_args(argv)
    if args.repeat not in (1, 2):
        parser.error("--repeat must be 1 or 2")
    report = replay(_resolve_commits(args.commits), args.repeat)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return int(any(item["stability"]["status"] == "FAIL" for item in report["commits"]))


if __name__ == "__main__":
    raise SystemExit(main())
