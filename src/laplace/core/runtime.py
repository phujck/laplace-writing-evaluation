"""Laplace runtime selection; the package interpreter supplies no source or state policy.

This module is stdlib-only so the launcher (scripts/laplace_python.py) can load it by path, with runpy, before
Laplace is importable. The launcher always passes its checkout explicitly. Package callers that omit the root get
laplace.core.checkout.source_tree(). The one location decision kept here is _policy_source_tree(): it checks that
the policy code actually loaded belongs to the checkout being run, and it has to work before any import.
"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path
from typing import Any


class RuntimePolicyError(RuntimeError):
    """The operation is not using Laplace's declared runtime."""


def _policy_source_tree() -> Path:
    """The checkout this policy file was loaded from (src/laplace/core/runtime.py, three levels below it)."""
    return Path(__file__).resolve().parents[3]


def _default_root(repo_root: Path | str | None) -> Path:
    if repo_root:
        return Path(repo_root)
    from laplace.core.checkout import source_tree
    return source_tree()


def runtime_profile(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    try:
        import tomllib
        profile = tomllib.loads((root / "runtime_profiles.toml").read_text())["lifecycle"]
        if not isinstance(profile,dict) or any(not isinstance(profile.get(key),str) or not profile[key]
                                              for key in ("python","expected_python")):
            raise ValueError("lifecycle needs python and expected_python")
        return profile
    except (OSError, ValueError, KeyError, ImportError) as exc:
        raise RuntimePolicyError(f"Laplace runtime declaration unavailable at {root}") from exc


def lifecycle_python(repo_root: Path | str | None = None) -> str:
    """Resolve the package interpreter or an explicit cold-checkout override."""
    root = _default_root(repo_root).resolve()
    profile = runtime_profile(root)
    return _selected_python(root, profile)


def _selected_python(root: Path, profile: dict[str, Any]) -> str:
    """One parsed declaration per selection observation."""
    value = os.environ.get("LAPLACE_PYTHON") or profile["python"]
    path = Path(value).expanduser()
    selected = (path if path.is_absolute() else root / path).absolute()
    if not selected.is_file() or not os.access(selected, os.X_OK):
        raise RuntimePolicyError(
            f"Laplace Python is unavailable: {selected}. Set LAPLACE_PYTHON to an "
            "explicit compatible interpreter; no environment is installed automatically."
        )
    return str(selected)


def runtime_command(repo_root: Path | str, *arguments: str) -> list[str]:
    """Keep child operations on this checkout's source and runtime selection."""
    return [str(Path(repo_root).resolve() / "scripts" / "laplace-python"), *arguments]


def selection_basis(repo_root: Path | str) -> dict[str, Any]:
    """Current managed selection/recipes, distinct from observed execution.

    The lifecycle profile is semantic: formatting changes do not change it.
    An effective explicit interpreter override does. Nothing is installed or
    launched here; managed lifecycle and validation remain with writing_app.
    """
    import hashlib
    import json
    root=Path(repo_root).resolve()
    profile=runtime_profile(root)
    selected=_selected_python(root,profile)
    recipes={}
    total=0
    for relative in ("scripts/laplace-python", "scripts/laplace_python.py"):
        try:raw=(root/relative).read_bytes()
        except OSError as error:raise RuntimePolicyError(f"Managed launcher recipe unavailable: {root/relative}") from error
        recipes[relative]="sha256:"+hashlib.sha256(raw).hexdigest();total+=len(raw)
    if not os.access(root/"scripts/laplace-python",os.X_OK):
        raise RuntimePolicyError("Managed checkout launcher is not executable")
    meaning={"profile":profile,"selected":selected,"resolved":str(Path(selected).resolve()),"recipes":recipes}
    identity="sha256:"+hashlib.sha256(json.dumps(meaning,sort_keys=True,separators=(",", ":")).encode()).hexdigest()
    return {"schema_version":"laplace.runtime-selection-basis/1","identity":identity,
            "selected":selected,"resolved":meaning["resolved"],"expected_python":profile["expected_python"],
            "profile_semantic_sha256":"sha256:"+hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(",", ":")).encode()).hexdigest(),
            "launcher_recipes":recipes,"recipe_bytes":total,"loaded_code_asserted":False}


def receipt() -> dict[str, Any]:
    """Return the small, serialisable runtime identity carried by durable acts."""
    return {
        "executable": str(Path(sys.executable).resolve()),
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "prefix": str(Path(sys.prefix).resolve()),
        "base_prefix": str(Path(sys.base_prefix).resolve()),
        "environment": "virtual" if sys.prefix != sys.base_prefix else "standalone",
        "user_site_disabled": bool(sys.flags.no_user_site),
    }


def require_runtime(repo_root: Path | str) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    profile = runtime_profile(root)
    selected = lifecycle_python(root)
    row = receipt()
    disagreements = []
    source_root = _policy_source_tree()
    if source_root != root:
        disagreements.append(f"runtime policy source is {source_root}, expected {root}")
    if row["executable"] != str(Path(selected).resolve()):
        disagreements.append(f"interpreter is {row['executable']}, expected {selected}")
    if row["version"] != profile["expected_python"]:
        disagreements.append(f"Python is {row['version']}, expected {profile['expected_python']}")
    if not row["user_site_disabled"]:
        disagreements.append("user-site imports are enabled")
    if disagreements:
        raise RuntimePolicyError(
            "; ".join(disagreements) + f". Use {root / 'scripts' / 'laplace-python'}."
        )
    return {**row, "source_root": str(root), "launcher": str(root / "scripts" / "laplace-python")}


def require_system_runtime(repo_root: Path | str) -> dict[str, Any]:
    """Compatibility name: authority now means the declared Laplace runtime."""
    return require_runtime(repo_root)


def configuration(repo_root: Path | str) -> dict[str, Any]:
    """Inspect declared runtime choices without changing selection or launching setup."""
    import hashlib
    path = Path(repo_root).resolve() / "runtime_profiles.toml"
    if not path.is_file():
        return {"path": "runtime_profiles.toml", "revision": None, "declared": {},
                "diagnostic": "No runtime declaration exists in this workspace"}
    raw = path.read_bytes()
    try:
        import tomllib
    except ImportError:
        return {"path":"runtime_profiles.toml", "revision":"sha256:"+hashlib.sha256(raw).hexdigest(),
                "declared":{},"diagnostic":"TOML parser unavailable in this observed runtime"}
    data = tomllib.loads(raw.decode("utf-8"))
    return {"path": "runtime_profiles.toml", "revision": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "declared": {key: data[key] for key in ("schema", "lifecycle", "development", "desktop", "browser_server", "gpu", "startup") if key in data}}
