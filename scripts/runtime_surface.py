#!/usr/bin/env python3
"""Build the deterministic top-level runtime surface snapshot.

This is an evidence census, not runtime policy.  Authored policy remains in
``runtime_profiles.toml`` and is carried in a separate top-level object.  The
scanner never imports Laplace, starts a service, checks a device, or touches
local state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import tomllib

SCHEMA_VERSION = "laplace.runtime-surface/1"
SNAPSHOT_PATH = "runtime_surface.json"
POLICY_PATH = "runtime_profiles.toml"
GENERATOR_PATH = "scripts/runtime_surface.py"

PYTHON_PROJECTS = ("pyproject.toml", "atlas/pyproject.toml")
HOOK_CONFIGS = (".codex/hooks.json", ".claude/settings.json")
BASE_CONFIGS = (
    ".python-version",
    "pyproject.toml",
    "atlas/pyproject.toml",
    "uv.lock",
    POLICY_PATH,
    "localstate.json",
    ".mcp.json",
    ".codex/config.toml",
    ".codex/hooks.json",
    ".claude/settings.json",
    ".claude/launch.json",
    "scripts/laplace-python",
    "scripts/laplace_python.py",
    "src/laplace/core/runtime.py",
)

INDEX_PATHS = (
    *BASE_CONFIGS,
    GENERATOR_PATH,
    "scripts",
    "src",
    "atlas/stores",
    ".codex/hooks",
    ".claude/hooks",
    ".claude/workflows",
    "usb_stick",
    "systemd",
    "models",
    "soul_vectors",
    "corpus_stores",
    ".metric_M.npz",
    ".self_embeddings.json",
    ".meaning_tree.json",
    ".meaning_vectors.npz",
    ":(glob)**/*.service",
    ":(glob)**/*.desktop",
)

ACTIVE_PYTHON_ROOTS = ("scripts/", "src/")   # src holds laplace and atlas (R2)
ACTIVE_SOURCE_ROOTS = (
    "scripts/",
    "src/",
    ".codex/hooks/",
    ".claude/hooks/",
    ".claude/workflows/",
    "usb_stick/",
    "systemd/",
)
RETIRED_PREFIXES = (
    "scripts/_archive/",
    "src/laplace/_archive/",
    "src/atlas/_archive/",
)
SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".sh", ".service", ".desktop"}

EMBEDDING_PROVIDER_PATTERNS = {
    "cuda-execution-provider": re.compile(r"CUDAExecutionProvider", re.IGNORECASE),
    "device-policy": re.compile(r"LAPLACE_REQUIRE_GPU|device[_ -]?policy", re.IGNORECASE),
    "embedding": re.compile(r"\bembed(?:ding|dings|der|ders)?\b|embed_router", re.IGNORECASE),
    "fastembed": re.compile(r"fastembed", re.IGNORECASE),
    "onnx-runtime": re.compile(r"onnxruntime", re.IGNORECASE),
    "provider": re.compile(r"\bprovider(?:s|[_-][A-Za-z0-9_]+)?\b", re.IGNORECASE),
    "spectral-gpu": re.compile(r"spectral_gpu|\bcupy\b|\bcuda\b", re.IGNORECASE),
    "vendored-model": re.compile(r"vendored_model|vendor_embedding_model", re.IGNORECASE),
}

SUBPROCESS_PATTERNS = {
    "node-child-process": re.compile(r"node:child_process|from ['\"]child_process['\"]"),
    "node-exec": re.compile(r"\bexec(?:File)?Sync\b|\bexecFile\b"),
    "node-spawn": re.compile(r"\bspawnSync\b|\bspawn\s*\("),
    "os-exec": re.compile(r"\bos\.(?:exec|spawn|system|popen)\w*\s*\("),
    "process-detach": re.compile(r"\bnohup\b|\bsetsid\b|start_new_session"),
    "python-subprocess": re.compile(
        r"\bsubprocess\b|\bPopen\s*\(|\bcheck_(?:call|output)\s*\("
    ),
    "service-control": re.compile(r"\bsystemctl\b|\bservice\s+[A-Za-z0-9_.@-]+"),
}

EXACT_ARTIFACTS = {
    ".metric_M.npz": "metric",
    ".self_embeddings.json": "embedding-cache",
    ".meaning_tree.json": "meaning-index",
    ".meaning_vectors.npz": "meaning-vectors",
    "soul_vectors/manifest.json": "vector-manifest",
    "soul_vectors/nodes.jsonl": "vector-store",
}


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _canonical_bytes(value: Any) -> bytes:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{text}\n".encode("utf-8")


def _read_bytes(repo: Path, relative: str) -> bytes:
    return (repo / relative).read_bytes()


def _normalise_text(value: str, repo: Path) -> str:
    """Remove checkout-specific roots while retaining authored system paths."""

    value = value.replace(str(repo), "${REPO}")
    value = re.sub(
        r"/(?:home|Users)/[^/\s\"']+/VScodeProjects/laplace(?:-[^/\s\"']+)?",
        "${REPO}",
        value,
    )
    value = re.sub(
        r"[A-Za-z]:\\Users\\[^\\\s\"']+\\[^\s\"']*\\laplace(?:-[^\\\s\"']+)?",
        "${REPO}",
        value,
    )
    return value


def _normalise_value(value: Any, repo: Path) -> Any:
    if isinstance(value, str):
        return _normalise_text(value, repo)
    if isinstance(value, dict):
        return {str(key): _normalise_value(item, repo) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalise_value(item, repo) for item in value]
    if isinstance(value, tuple):
        return [_normalise_value(item, repo) for item in value]
    return value


def _git_index(repo: Path) -> dict[str, dict[str, str]]:
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--stage", "-z", "--", *INDEX_PATHS],
        check=True,
        capture_output=True,
    )
    index: dict[str, dict[str, str]] = {}
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        metadata, path_bytes = raw.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        path = path_bytes.decode("utf-8", errors="surrogateescape")
        if stage == "0" or path not in index:
            index[path] = {"mode": mode, "object_id": object_id, "stage": stage}
    return index


def _service_paths(repo: Path, indexed: Iterable[str]) -> list[str]:
    paths = {path for path in indexed if path.endswith(".service")}
    for root_name in ("systemd", "src/laplace/desktop/deploy"):
        root = repo / root_name
        if root.is_dir():
            paths.update(path.relative_to(repo).as_posix() for path in root.rglob("*.service"))
    return sorted(paths)


def _authoritative_config_paths(repo: Path, index: dict[str, dict[str, str]]) -> list[str]:
    paths = set(BASE_CONFIGS)
    paths.update(_service_paths(repo, index))
    deploy = repo / "src/laplace/desktop/deploy"
    if deploy.is_dir():
        paths.update(path.relative_to(repo).as_posix() for path in deploy.glob("*.desktop"))
    return sorted(paths)


def _input_hashes(repo: Path, index: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in _authoritative_config_paths(repo, index):
        path = repo / relative
        if not path.is_file():
            rows.append({"path": relative, "present": False})
            continue
        content = path.read_bytes()
        rows.append(
            {
                "bytes": len(content),
                "path": relative,
                "present": True,
                "sha256": _sha256(content),
            }
        )
    return rows


def _authored_policy(repo: Path) -> dict[str, Any]:
    path = repo / POLICY_PATH
    if not path.is_file():
        return {"present": False, "source": POLICY_PATH}
    content = path.read_bytes()
    policy = tomllib.loads(content.decode("utf-8"))
    return {
        "content_sha256": _sha256(content),
        "policy": _normalise_value(policy, repo),
        "present": True,
        "source": POLICY_PATH,
    }


def _python_projects(repo: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in PYTHON_PROJECTS:
        path = repo / relative
        if not path.is_file():
            continue
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        project = document.get("project", {})
        optional = project.get("optional-dependencies", {})
        entrypoints = project.get("scripts", {})
        rows.append(
            {
                "dependencies": sorted(str(item) for item in project.get("dependencies", [])),
                "entrypoints": [
                    {"name": str(name), "target": str(target)}
                    for name, target in sorted(entrypoints.items())
                ],
                "name": str(project.get("name", "")),
                "optional_dependencies": {
                    str(name): sorted(str(item) for item in dependencies)
                    for name, dependencies in sorted(optional.items())
                },
                "requires_python": str(project.get("requires-python", "")),
                "source": relative,
            }
        )
    return rows


def _is_retired(path: str) -> bool:
    return path.startswith(RETIRED_PREFIXES)


def _active_python_paths(repo: Path, index: dict[str, dict[str, str]]) -> list[str]:
    candidates = {
        path
        for path in index
        if path.endswith(".py")
        and path.startswith(ACTIVE_PYTHON_ROOTS)
        and not _is_retired(path)
    }
    if (repo / GENERATOR_PATH).is_file():
        candidates.add(GENERATOR_PATH)
    return sorted(candidates)


def _main_guard_line(text: str) -> int | None:
    pattern = re.compile(
        r"(?m)^\s*if\s+(?:__name__\s*==\s*['\"]__main__['\"]"
        r"|['\"]__main__['\"]\s*==\s*__name__)\s*:"
    )
    match = pattern.search(text)
    return text.count("\n", 0, match.start()) + 1 if match else None


def _module_name(relative: str) -> str | None:
    path = PurePosixPath(relative)
    parts = list(path.with_suffix("").parts)
    if parts[:1] == ["src"]:
        parts = parts[1:]
    elif parts[:2] == ["atlas", "src"]:
        parts = parts[2:]
    else:
        return None
    if parts[-1:] == ["__main__"]:
        parts = parts[:-1]
    return ".".join(parts) if parts else None


def _python_main_surfaces(
    repo: Path, index: dict[str, dict[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    surfaces: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for relative in _active_python_paths(repo, index):
        path = repo / relative
        if not path.is_file():
            continue
        content = path.read_bytes()
        line = _main_guard_line(content.decode("utf-8", errors="replace"))
        if line is None:
            continue
        row: dict[str, Any] = {
            "guard_line": line,
            "path": relative,
            "sha256": _sha256(content),
        }
        module = _module_name(relative)
        if module:
            row["module"] = module
        surfaces.append(row)
    return surfaces, failures


def _hook_registrations(repo: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in HOOK_CONFIGS:
        path = repo / relative
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        hooks = document.get("hooks", {})
        if not isinstance(hooks, dict):
            continue
        for event, groups in sorted(hooks.items()):
            if not isinstance(groups, list):
                continue
            for group_index, group in enumerate(groups):
                if not isinstance(group, dict):
                    continue
                registrations = group.get("hooks", [])
                if not isinstance(registrations, list):
                    continue
                for hook_index, hook in enumerate(registrations):
                    if not isinstance(hook, dict):
                        continue
                    row: dict[str, Any] = {
                        "event": str(event),
                        "group_index": group_index,
                        "hook_index": hook_index,
                        "source": relative,
                    }
                    for field in ("type", "command", "timeout", "statusMessage"):
                        if field in hook:
                            output_name = "status_message" if field == "statusMessage" else field
                            row[output_name] = _normalise_value(hook[field], repo)
                    if "matcher" in group:
                        row["matcher"] = _normalise_value(group["matcher"], repo)
                    rows.append(row)
    return rows


def _logical_service_lines(text: str) -> list[str]:
    rows: list[str] = []
    pending = ""
    for physical in text.splitlines():
        stripped = physical.strip()
        if pending:
            pending += stripped
        else:
            pending = stripped
        if pending.endswith("\\"):
            pending = pending[:-1] + " "
            continue
        rows.append(pending)
        pending = ""
    if pending:
        rows.append(pending)
    return rows


def _service_exec_surfaces(
    repo: Path, index: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for relative in _service_paths(repo, index):
        path = repo / relative
        if not path.is_file():
            continue
        for line in _logical_service_lines(path.read_text(encoding="utf-8")):
            match = re.match(r"^(ExecStart(?:Pre|Post)?)=(.*)$", line)
            if not match:
                continue
            rows.append(
                {
                    "command": _normalise_text(match.group(2).strip(), repo),
                    "directive": match.group(1),
                    "source": relative,
                }
            )
    return rows


def _localstate_entries(repo: Path) -> list[dict[str, Any]]:
    path = repo / "localstate.json"
    if not path.is_file():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for entry in document.get("entries", []):
        if not isinstance(entry, dict):
            continue
        rows.append(
            {
                "check": _normalise_text(str(entry.get("check", "")), repo),
                "cost": str(entry.get("cost", "")),
                "depends_on": sorted(str(item) for item in entry.get("depends_on", [])),
                "name": str(entry.get("name", "")),
                "rebuild": _normalise_text(str(entry.get("rebuild", "")), repo),
            }
        )
    return sorted(rows, key=lambda row: row["name"])


def _artifact_kind(path: str) -> str | None:
    if path in EXACT_ARTIFACTS:
        return EXACT_ARTIFACTS[path]
    if path.startswith("models/fastembed/") and path.endswith((".tar.gz", ".onnx")):
        return "embedding-model"
    if path.startswith("models/ctm/") and path.endswith(("MANIFEST.json", ".pkl.gz")):
        return "ctm-model"
    if path.startswith("atlas/stores/") and path.endswith("/handle_vectors.npy"):
        return "atlas-handle-vectors"
    if path.startswith("corpus_stores/") and path.endswith("/embeddings.json"):
        return "corpus-embeddings"
    return None


def _tracked_embedding_model_artifacts(
    index: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path, metadata in sorted(index.items()):
        kind = _artifact_kind(path)
        if kind is None:
            continue
        rows.append(
            {
                "git_blob": metadata["object_id"],
                "kind": kind,
                "path": path,
            }
        )
    return rows


def _surface_source_paths(repo: Path, index: dict[str, dict[str, str]]) -> list[str]:
    candidates = {
        path
        for path in index
        if path.startswith(ACTIVE_SOURCE_ROOTS)
        and PurePosixPath(path).suffix.lower() in SOURCE_SUFFIXES
        and not _is_retired(path)
    }
    candidates.update(
        relative
        for relative in (*BASE_CONFIGS, GENERATOR_PATH)
        if (repo / relative).is_file() and relative != "uv.lock"
    )
    return sorted(candidates)


def _matching_surface_files(
    repo: Path,
    index: dict[str, dict[str, str]],
    patterns: dict[str, re.Pattern[str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relative in _surface_source_paths(repo, index):
        path = repo / relative
        if not path.is_file():
            continue
        content = path.read_bytes()
        text = content.decode("utf-8", errors="replace")
        terms = sorted(name for name, pattern in patterns.items() if pattern.search(text))
        if terms:
            rows.append({"path": relative, "sha256": _sha256(content), "terms": terms})
    return rows


def _counts(evidence: dict[str, Any], inputs: list[dict[str, Any]]) -> dict[str, int]:
    projects = evidence["python_projects"]
    return {
        "active_python_main_surfaces": len(evidence["active_python_main_surfaces"]),
        "authoritative_input_configs": len(inputs),
        "declared_python_dependencies": sum(len(row["dependencies"]) for row in projects),
        "declared_python_entrypoints": sum(len(row["entrypoints"]) for row in projects),
        "declared_python_optional_dependencies": sum(
            len(items) for row in projects for items in row["optional_dependencies"].values()
        ),
        "declared_python_optional_groups": sum(
            len(row["optional_dependencies"]) for row in projects
        ),
        "embedding_provider_files": len(evidence["embedding_provider_files"]),
        "hook_registrations": len(evidence["hook_registrations"]),
        "localstate_entries": len(evidence["localstate_entries"]),
        "python_projects": len(projects),
        "python_scan_failures": len(evidence["python_scan_failures"]),
        "service_exec_surfaces": len(evidence["service_exec_surfaces"]),
        "subprocess_launch_files": len(evidence["subprocess_launch_files"]),
        "tracked_embedding_model_artifacts": len(
            evidence["tracked_embedding_model_artifacts"]
        ),
    }


def build_snapshot(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    index = _git_index(repo)
    inputs = _input_hashes(repo, index)
    mains, scan_failures = _python_main_surfaces(repo, index)
    evidence = {
        "active_python_main_surfaces": mains,
        "embedding_provider_files": _matching_surface_files(
            repo, index, EMBEDDING_PROVIDER_PATTERNS
        ),
        "hook_registrations": _hook_registrations(repo),
        "localstate_entries": _localstate_entries(repo),
        "python_projects": _python_projects(repo),
        "python_scan_failures": scan_failures,
        "service_exec_surfaces": _service_exec_surfaces(repo, index),
        "subprocess_launch_files": _matching_surface_files(repo, index, SUBPROCESS_PATTERNS),
        "tracked_embedding_model_artifacts": _tracked_embedding_model_artifacts(index),
    }
    generator_content = _read_bytes(repo, GENERATOR_PATH)
    snapshot: dict[str, Any] = {
        "authoritative_inputs": inputs,
        "authored_policy": _authored_policy(repo),
        "counts": _counts(evidence, inputs),
        "generator": {"path": GENERATOR_PATH, "sha256": _sha256(generator_content)},
        "inferred_evidence": evidence,
        "schema_version": SCHEMA_VERSION,
        "scope": {
            "active_python_roots": list(ACTIVE_PYTHON_ROOTS),
            "large_artifact_identity": "tracked Git blob identity; no runtime health claim",
            "meaning": "declared and source-visible surfaces; presence is not health or authority",
            "retired_prefixes_excluded": list(RETIRED_PREFIXES),
        },
    }
    snapshot["snapshot_digest"] = _sha256(_canonical_bytes(snapshot))
    rendered = _canonical_bytes(snapshot).decode("utf-8")
    if str(repo) in rendered or re.search(
        r"/(?:home|Users)/[^/\s\"']+/VScodeProjects/laplace", rendered
    ):
        raise RuntimeError("snapshot contains a checkout-specific absolute path")
    return snapshot


def render_snapshot(snapshot: dict[str, Any]) -> bytes:
    return _canonical_bytes(snapshot)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--write", action="store_true", help=f"write {SNAPSHOT_PATH}")
    action.add_argument("--check", action="store_true", help="refuse if the snapshot is stale")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    snapshot = build_snapshot(repo)
    rendered = render_snapshot(snapshot)
    target = repo / SNAPSHOT_PATH
    if args.write:
        target.write_bytes(rendered)
        print(f"runtime_surface: WROTE {SNAPSHOT_PATH} {snapshot['snapshot_digest']}")
        return 0
    if args.check:
        if not target.is_file() or target.read_bytes() != rendered:
            print(
                f"runtime_surface: STALE {SNAPSHOT_PATH}; "
                f"run ./scripts/laplace-python {GENERATOR_PATH} --write",
                file=sys.stderr,
            )
            return 1
        print(f"runtime_surface: CURRENT {snapshot['snapshot_digest']}")
        return 0
    sys.stdout.buffer.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
