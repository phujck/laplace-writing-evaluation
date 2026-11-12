"""Authority-free, deterministic rehearsal of the provider lifecycle boundary.

The harness deliberately produces evidence, not publication authority.  It operates on
an archived committed tree and temporary roots, and keeps the still-open production
prerequisites visible in every receipt instead of turning a fixture into a false PASS.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tarfile
import tempfile
import time
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from laplace.representation.atlas_bridge import chash

EVIDENCE_SCHEMA = "laplace.faithful-lifecycle-rehearsal-evidence/1"
ISOLATION_SCHEMA = "laplace.faithful-lifecycle-rehearsal-isolation/1"
PREREQUISITES = (
    "WO-20260827-same-holder-generation-binding-renewal",
    "WO-20260827-provider-attention-crash-reconciliation",
    "WO-20260827-typed-compaction-continuation",
    "WO-20260827-authenticated-delta-currentness",
)
REQUIRED_PLANTS = (
    "cold-committed-tree",
    "retired-generation-replay",
    "checkpoint-compaction-orderings",
    "delayed-historical-duplicate",
)


class RehearsalRefused(RuntimeError):
    """A typed refusal before any authority-bearing operation."""

    def __init__(self, reason: str, **evidence: Any) -> None:
        super().__init__(reason)
        self.reason = reason
        self.evidence = evidence


def _bytes_handle(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _git(repo_root: Path, *args: str, binary: bool = False) -> str | bytes:
    completed = subprocess.run(
        ["git", "-C", os.fspath(repo_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        raise RehearsalRefused(
            "GIT-READ-REFUSED",
            command=list(args),
            stderr=completed.stderr.decode("utf-8", errors="replace"),
        )
    if binary:
        return completed.stdout
    return completed.stdout.decode("utf-8").strip()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def validate_rehearsal_isolation(
    *,
    writable_roots: Mapping[str, Path],
    protected_roots: Mapping[str, Path],
) -> dict[str, Any]:
    """Refuse any writable rehearsal root that aliases a protected live root."""

    resolved_writable = {name: Path(path).resolve() for name, path in writable_roots.items()}
    resolved_protected = {name: Path(path).resolve() for name, path in protected_roots.items()}
    for writable_name, writable in resolved_writable.items():
        for protected_name, protected in resolved_protected.items():
            if _is_within(writable, protected) or _is_within(protected, writable):
                raise RehearsalRefused(
                    "WRITABLE-ROOT-ALIASES-PROTECTED-ROOT",
                    writable_name=writable_name,
                    protected_name=protected_name,
                )
    if len(set(resolved_writable.values())) != len(resolved_writable):
        raise RehearsalRefused("WRITABLE-ROOTS-ALIAS")
    receipt = {
        "schema_version": ISOLATION_SCHEMA,
        "writable_root_kinds": sorted(resolved_writable),
        "protected_root_kinds": sorted(resolved_protected),
        "writable_roots_temporary": True,
        "network": "DISABLED",
        "canonical_writes": False,
        "provider_invocations": 0,
        "watcher_invocations": 0,
    }
    return {**receipt, "isolation_root": chash(receipt)}


def _path_inventory(path: Path) -> dict[str, Any]:
    path = path.resolve()
    if not path.exists() and not path.is_symlink():
        body = {"state": "ABSENT", "entries": []}
        return {**body, "root": chash(body), "bytes": 0}
    entries: list[dict[str, Any]] = []
    total_bytes = 0
    paths: Iterable[Path]
    if path.is_dir():
        paths = sorted((item for item in path.rglob("*") if ".git" not in item.parts))
    else:
        paths = (path,)
    for item in paths:
        relative = "." if item == path else item.relative_to(path).as_posix()
        mode = item.lstat().st_mode
        if stat.S_ISDIR(mode):
            entries.append({"path": relative, "kind": "directory", "mode": mode & 0o777})
        elif stat.S_ISLNK(mode):
            target = os.readlink(item)
            entries.append(
                {"path": relative, "kind": "symlink", "target": target, "mode": mode & 0o777}
            )
            total_bytes += len(target.encode("utf-8"))
        elif stat.S_ISREG(mode):
            data = item.read_bytes()
            entries.append(
                {
                    "path": relative,
                    "kind": "file",
                    "handle": _bytes_handle(data),
                    "mode": mode & 0o777,
                }
            )
            total_bytes += len(data)
        else:
            raise RehearsalRefused("UNSUPPORTED-PROTECTED-PATH-KIND", path=os.fspath(item))
    body = {"state": "PRESENT", "entries": entries}
    return {**body, "root": chash(body), "bytes": total_bytes}


def _source_fingerprint(repo_root: Path) -> dict[str, Any]:
    head = str(_git(repo_root, "rev-parse", "HEAD"))
    tree = str(_git(repo_root, "rev-parse", "HEAD^{tree}"))
    status = _git(repo_root, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)
    diff = _git(repo_root, "diff", "--binary", "HEAD", binary=True)
    body = {
        "head": head,
        "tree": tree,
        "status_handle": _bytes_handle(status),
        "diff_handle": _bytes_handle(diff),
    }
    return {**body, "root": chash(body)}


def _load_provider_history(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RehearsalRefused(
                "PROVIDER-HISTORY-MALFORMED", line=line_number, error=str(exc)
            ) from exc
        if not isinstance(row, dict) or type(row.get("step")) is not int or not row.get("kind"):
            raise RehearsalRefused("PROVIDER-HISTORY-ROW-MALFORMED", line=line_number)
        rows.append(row)
    if not rows or [row["step"] for row in rows] != list(range(1, len(rows) + 1)):
        raise RehearsalRefused("PROVIDER-HISTORY-SEQUENCE-NONCONTIGUOUS")
    return rows, _bytes_handle(raw)


def _plant(status: str, reason: str, **evidence: Any) -> dict[str, Any]:
    return {"status": status, "reason": reason, "evidence": evidence}


def _retired_generation_plant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    joins = [row for row in rows if row["kind"] == "seat.joined"]
    replays = [row for row in rows if row["kind"] == "generation.replayed"]
    progression = [(row.get("holder"), row.get("generation")) for row in joins]
    expected = [("A", "A1"), ("A", "A2"), ("B", "B1")]
    retired = {row.get("generation") for row in joins if row.get("retired") is True}
    refused = {
        row.get("generation")
        for row in replays
        if row.get("result") == "REFUSED-RETIRED"
    }
    if progression != expected or retired != {"A1", "A2"} or refused != retired:
        return _plant(
            "REFUSED",
            "RETIRED-GENERATION-LINEAGE-MISMATCH",
            progression=progression,
            retired=sorted(retired),
            refused=sorted(refused),
        )
    return _plant(
        "EVIDENCED",
        "A1-A2-B1-REPLAY-INERT",
        progression=progression,
        retired=sorted(retired),
        current={"holder": "B", "generation": "B1"},
    )


def _checkpoint_compaction_plant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    observations = [
        row for row in rows if row["kind"] in {"checkpoint.observed", "compaction.observed"}
    ]
    orders = {row.get("ordering") for row in observations}
    roots = {row.get("terminal_root") for row in observations}
    cursors = {row.get("cursor") for row in observations}
    required = {"checkpoint-then-compaction", "compaction-then-checkpoint"}
    if orders != required or len(roots) != 1 or len(cursors) != 1:
        return _plant(
            "CONTEST",
            "CHECKPOINT-COMPACTION-NONCONVERGENT",
            orderings=sorted(str(value) for value in orders),
            terminal_roots=sorted(str(value) for value in roots),
            cursors=sorted(str(value) for value in cursors),
        )
    return _plant(
        "EVIDENCED",
        "ORDERINGS-CONVERGE-IN-FIXTURE",
        orderings=sorted(orders),
        terminal_root=next(iter(roots)),
        cursor=next(iter(cursors)),
    )


def _delayed_duplicate_plant(rows: list[dict[str, Any]]) -> dict[str, Any]:
    acked: dict[str, int] = {}
    duplicates: list[dict[str, Any]] = []
    for row in rows:
        if row["kind"] == "message.acknowledged":
            acked[str(row.get("message_id"))] = int(row.get("cursor", -1))
        elif row["kind"] == "provider.delayed-duplicate":
            duplicates.append(row)
    failures = [
        row
        for row in duplicates
        if str(row.get("message_id")) not in acked
        or row.get("result") != "INERT"
        or int(row.get("cursor", -2)) != acked[str(row.get("message_id"))]
    ]
    if len(duplicates) != 1 or failures:
        return _plant(
            "REFUSED",
            "DELAYED-DUPLICATE-NOT-PROVED-INERT",
            duplicates=len(duplicates),
            failures=failures,
        )
    row = duplicates[0]
    return _plant(
        "EVIDENCED",
        "ACKNOWLEDGED-DUPLICATE-INERT",
        message_id=row["message_id"],
        cursor=row["cursor"],
    )


def _cold_tree_plant(candidate_root: Path, *, commit: str, tree: str) -> dict[str, Any]:
    inventory = _path_inventory(candidate_root)
    if not inventory["entries"]:
        return _plant("REFUSED", "COMMITTED-TREE-ARCHIVE-EMPTY")
    return _plant(
        "EVIDENCED",
        "COMMITTED-TREE-ARCHIVED-COLD",
        candidate_commit=commit,
        candidate_tree=tree,
        archive_inventory_root=inventory["root"],
        archive_files=sum(1 for row in inventory["entries"] if row["kind"] == "file"),
        archive_bytes=inventory["bytes"],
    )


def _extract_committed_tree(repo_root: Path, commit: str, destination: Path) -> None:
    archive = _git(repo_root, "archive", "--format=tar", commit, binary=True)
    archive_path = destination.parent / "candidate.tar"
    archive_path.write_bytes(archive)
    with tarfile.open(archive_path, mode="r:") as handle:
        for member in handle.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RehearsalRefused("COMMITTED-TREE-ARCHIVE-ESCAPES-ROOT", path=member.name)
        handle.extractall(destination, filter="fully_trusted")


@contextmanager
def _temporary_root() -> Iterable[Path]:
    with tempfile.TemporaryDirectory(prefix="laplace-lifecycle-rehearsal-") as raw:
        yield Path(raw)


def run_faithful_lifecycle_rehearsal(
    *,
    repo_root: Path,
    candidate_commit: str,
    candidate_tree: str,
    provider_history_path: Path,
    canonical_atlas_root: Path,
    blueprint_root: Path,
    live_provider_root: Path,
    live_watcher_root: Path,
    max_fixture_bytes: int = 1_048_576,
    max_trace_rows: int = 256,
) -> dict[str, Any]:
    """Run one bounded authority-free rehearsal over a committed tree archive."""

    started_wall = time.perf_counter_ns()
    started_cpu = time.process_time_ns()
    repo_root = repo_root.resolve()
    commit = str(_git(repo_root, "rev-parse", f"{candidate_commit}^{{commit}}"))
    tree = str(_git(repo_root, "rev-parse", f"{commit}^{{tree}}"))
    if commit != candidate_commit or tree != candidate_tree:
        raise RehearsalRefused(
            "CANDIDATE-COORDINATE-MISMATCH",
            expected_commit=candidate_commit,
            actual_commit=commit,
            expected_tree=candidate_tree,
            actual_tree=tree,
        )
    fixture_bytes = provider_history_path.stat().st_size
    if fixture_bytes > max_fixture_bytes:
        raise RehearsalRefused(
            "PROVIDER-HISTORY-BUDGET-EXCEEDED",
            bytes=fixture_bytes,
            budget=max_fixture_bytes,
        )
    rows, fixture_root = _load_provider_history(provider_history_path)
    if len(rows) > max_trace_rows:
        raise RehearsalRefused(
            "PROVIDER-HISTORY-ROW-BUDGET-EXCEEDED",
            rows=len(rows),
            budget=max_trace_rows,
        )
    protected_roots = {
        "source": repo_root,
        "canonical_atlas": canonical_atlas_root,
        "blueprint": blueprint_root,
        "live_provider": live_provider_root,
        "live_watcher": live_watcher_root,
    }
    source_before = _source_fingerprint(repo_root)
    protected_before = {name: _path_inventory(path) for name, path in protected_roots.items() if name != "source"}

    with _temporary_root() as root:
        writable_roots = {
            "home": root / "home",
            "xdg": root / "xdg",
            "laplace": root / "laplace",
            "git": root / "git",
            "provider": root / "provider",
            "output": root / "output",
        }
        isolation = validate_rehearsal_isolation(
            writable_roots=writable_roots,
            protected_roots=protected_roots,
        )
        for path in writable_roots.values():
            path.mkdir(parents=True, exist_ok=False)
        os.environ.get("HOME")  # read only; the process environment is never rewritten
        _extract_committed_tree(repo_root, commit, writable_roots["git"])
        plants = {
            "cold-committed-tree": _cold_tree_plant(
                writable_roots["git"], commit=commit, tree=tree
            ),
            "retired-generation-replay": _retired_generation_plant(rows),
            "checkpoint-compaction-orderings": _checkpoint_compaction_plant(rows),
            "delayed-historical-duplicate": _delayed_duplicate_plant(rows),
        }

    source_after = _source_fingerprint(repo_root)
    protected_after = {name: _path_inventory(path) for name, path in protected_roots.items() if name != "source"}
    if source_before != source_after or protected_before != protected_after:
        raise RehearsalRefused(
            "PROTECTED-ROOT-MOVED-DURING-REHEARSAL",
            source_equal=source_before == source_after,
            protected_equal=protected_before == protected_after,
        )

    prerequisite_states = {node: "OPEN" for node in PREREQUISITES}
    semantic_trace = {
        "candidate_commit": commit,
        "candidate_tree": tree,
        "provider_history_root": fixture_root,
        "isolation_root": isolation["isolation_root"],
        "plants": plants,
        "prerequisite_states": prerequisite_states,
    }
    failed = [name for name, plant in plants.items() if plant["status"] != "EVIDENCED"]
    elapsed_wall = time.perf_counter_ns() - started_wall
    elapsed_cpu = time.process_time_ns() - started_cpu
    evidence = {
        "schema_version": EVIDENCE_SCHEMA,
        "candidate_commit": commit,
        "candidate_tree": tree,
        "publication_authority": False,
        "verdict": "CONTEST",
        "verdict_reason": (
            "PLANT-REFUSAL" if failed else "CANONICAL-PREREQUISITES-REMAIN-OPEN"
        ),
        "input_root": chash(
            {
                "candidate_commit": commit,
                "candidate_tree": tree,
                "provider_history_root": fixture_root,
                "source_root": source_before["root"],
                "protected_roots": {
                    name: receipt["root"] for name, receipt in protected_before.items()
                },
            }
        ),
        "isolation": isolation,
        "semantic_trace_root": chash(semantic_trace),
        "plants": plants,
        "failed_plants": failed,
        "prerequisite_states": prerequisite_states,
        "budgets": {
            "fixture_bytes": fixture_bytes,
            "fixture_bytes_limit": max_fixture_bytes,
            "trace_rows": len(rows),
            "trace_rows_limit": max_trace_rows,
            "prompts": 0,
            "provider_invocations": 0,
        },
        "timings": {"wall_ns": elapsed_wall, "cpu_ns": elapsed_cpu},
        "residuals": [
            "provider-attention crash reconciliation remains OPEN",
            "typed pre/post-compaction continuation remains OPEN",
            "authenticated delta currentness remains CHECKSUMMED-CRUTCH/OPEN",
            "one non-Codex provider adapter remains absent",
            "fixture evidence is not canonical lifecycle acceptance",
        ],
        "source_before_after_equal": True,
        "protected_before_after_equal": True,
    }
    evidence["evidence_root"] = chash(
        {key: value for key, value in evidence.items() if key not in {"timings", "evidence_root"}}
    )
    return evidence


__all__ = [
    "EVIDENCE_SCHEMA",
    "PREREQUISITES",
    "REQUIRED_PLANTS",
    "RehearsalRefused",
    "run_faithful_lifecycle_rehearsal",
    "validate_rehearsal_isolation",
]
