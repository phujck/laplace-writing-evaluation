#!/usr/bin/env python3
"""Check core packages plus one requested capability; never install or load a GPU."""

from __future__ import annotations

import argparse
import platform
from importlib import metadata
from pathlib import Path

import tomllib
from packaging.requirements import Requirement


def _requirements(root: Path, profile: str) -> tuple[list[Requirement], dict]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    runtime = tomllib.loads((root / "runtime_profiles.toml").read_text(encoding="utf-8"))
    specs = [*project.get("dependencies", [])]
    if profile != "core":
        specs.extend(runtime["capabilities"][profile])
    return [Requirement(spec) for spec in specs], runtime


def _installed(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def verify(root: Path, profile: str) -> list[str]:
    requirements, runtime = _requirements(root, profile)
    problems: list[str] = []
    expected_python = str(runtime["lifecycle"]["expected_python"])
    if platform.python_version() != expected_python:
        problems.append(
            f"python is {platform.python_version()}, expected selected runtime {expected_python}"
        )

    seen: set[str] = set()
    for requirement in requirements:
        key = requirement.name.lower()
        if key in seen or (requirement.marker and not requirement.marker.evaluate()):
            continue
        seen.add(key)
        version = _installed(requirement.name)
        if version is None:
            problems.append(f"missing {requirement.name}")
        elif requirement.specifier and version not in requirement.specifier:
            problems.append(
                f"{requirement.name}=={version} does not satisfy {requirement.specifier}"
            )

    if profile in {"cpu", "gpu"}:
        for pair in (("fastembed", "fastembed-gpu"), ("onnxruntime", "onnxruntime-gpu"),
                     ("cupy-cuda12x", "cupy-cuda13x")):
            installed = [name for name in pair if _installed(name) is not None]
            if len(installed) > 1:
                problems.append("overlapping import namespace: " + ", ".join(installed))
        if profile == "gpu" and _installed("onnxruntime") is not None:
            problems.append("GPU capability cannot use the CPU onnxruntime distribution")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    parser.add_argument("--profile", choices=("core", "cpu", "gpu"), default="core")
    args = parser.parse_args()

    problems = verify(args.root.resolve(), args.profile)
    if problems:
        for problem in problems:
            print(f"INCOMPLETE {problem}")
        print(f"runtime profile {args.profile}: FAILED ({len(problems)} problem(s))")
        return 1
    print(
        f"runtime profile {args.profile}: COMPLETE "
        f"(Python {platform.python_version()}, package metadata only; device execution not proved)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
