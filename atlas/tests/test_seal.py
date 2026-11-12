"""test_seal.py - the atlas side of the seal: this package never reaches for laplace.

An AST walk over every .py file under ``src/atlas`` (the Atlas source home since core consolidation R2). Three refusals, and the allowlist is empty
permanently - not "empty for now". A package that needs one exception needs a design change, and
that change should show up as a diff to this line, where a judge sees it.

  1. ``laplace`` is never imported, under any form (``import laplace``, ``from laplace import``,
     ``import laplace.x``).
  2. ``sys.path`` is never mutated. The rule the design states is "no sys.path mutation reaching
     src/laplace"; the rule enforced here is stronger and cheaper to check - atlas has no reason
     to touch the import path at all, so any mutation is the violation.
  3. no dynamic import (``importlib.import_module``, ``__import__``) whose argument is a literal
     containing "laplace".
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ATLAS_SRC = Path(__file__).resolve().parents[2] / "src" / "atlas"

#: Permanently empty. A second entry is a design change, visible as a diff.
ALLOWLIST: list[str] = []


def _python_files() -> list[Path]:
    return sorted(ATLAS_SRC.rglob("*.py"))


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_source_tree_is_present():
    files = _python_files()
    assert files, f"no python files found under {ATLAS_SRC}"


def test_allowlist_is_empty():
    assert ALLOWLIST == [], "the atlas-side seal allowlist is permanently empty"


def test_no_laplace_import():
    offenders: list[str] = []
    for path in _python_files():
        for node in ast.walk(_parse(path)):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "laplace" or alias.name.startswith("laplace."):
                        offenders.append(f"{path}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "laplace" or mod.startswith("laplace."):
                    offenders.append(f"{path}:{node.lineno} from {mod} import")
    assert offenders == []


def test_no_sys_path_mutation():
    offenders: list[str] = []
    for path in _python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "path":
                value = node.value
                if isinstance(value, ast.Name) and value.id == "sys":
                    offenders.append(f"{path}:{node.lineno} sys.path")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                if (isinstance(owner, ast.Attribute) and owner.attr == "path"
                        and isinstance(owner.value, ast.Name) and owner.value.id == "sys"):
                    offenders.append(f"{path}:{node.lineno} sys.path.{node.func.attr}")
    assert offenders == []


def test_no_dynamic_laplace_import():
    offenders: list[str] = []
    for path in _python_files():
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Call):
                continue
            name = ""
            if isinstance(node.func, ast.Attribute):
                name = node.func.attr
            elif isinstance(node.func, ast.Name):
                name = node.func.id
            if name not in ("import_module", "__import__", "find_spec", "load_module"):
                continue
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if "laplace" in arg.value:
                        offenders.append(f"{path}:{node.lineno} {name}({arg.value!r})")
    assert offenders == []


@pytest.mark.parametrize("module", ["atlas", "atlas.schema", "atlas.segment", "atlas.encoders",
                                    "atlas.snapshot", "atlas.store", "atlas.ids"])
def test_import_pulls_no_laplace(module, clean_import_probe):
    """Importing atlas must not drag laplace in through some transitive path.

    Read in a fresh interpreter, not in this one. Both halves of the repository share a process
    (root ``pyproject.toml``, ``testpaths``), so this process has laplace imported by the laplace
    tests before the atlas tests start; its ``sys.modules`` answers a question about the process.
    The child's path carries laplace too, so an empty result means atlas declined the import.
    See ``conftest.clean_import_probe``.
    """
    report = clean_import_probe(imports=[module], witness=["laplace"])
    assert report["importable"]["laplace"], (
        "laplace was not importable in the probe, so a clean result proves nothing about the "
        "seal - fix the probe path before reading this test"
    )
    assert report["leaked_laplace"] == []
