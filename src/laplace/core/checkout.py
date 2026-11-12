"""Qualified roots: one resolver for each meaning of "where", never one unqualified root.

  source_tree()   the source checkout this package was imported from: the directory holding src/laplace. It is
                  derived from this file's location here and nowhere else in the package. For an installed package
                  it is only the install location's grandparent, so code that needs a writable checkout uses
                  repo_root() or an explicit root, not this.
  package_root()  the imported laplace package directory, the origin of shipped resources (canon, static assets,
                  the system description), in a checkout or installed alike.
  repo_root()     the serving checkout: LAPLACE_REPO_ROOT when configured, else source_tree().
  state_root()    the engine's private state home: LAPLACE_STATE when set, else ~/.mcp-gerard/laplace.

An explicit root an operation is given always wins over all four. External manuscript repositories, Writing's own
state (LAPLACE_WRITING_STATE) and the journal's isolation rule (laplace.core.records.journal) are qualified by their
owners, which consume these resolvers rather than restating them. Standard library only; no import-time effects.
"""
from __future__ import annotations

import os
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parents[1]


def source_tree() -> Path:
    """The checkout holding src/laplace (this package's source tree)."""
    return _PACKAGE.parents[1]


def package_root() -> Path:
    """The imported laplace package directory: where shipped resources are read from."""
    return _PACKAGE


def repo_root() -> Path:
    """The serving checkout: LAPLACE_REPO_ROOT when configured, else the source tree."""
    configured = os.environ.get("LAPLACE_REPO_ROOT")
    return Path(configured).resolve() if configured else source_tree()


def state_root() -> Path:
    """The engine's private state home: LAPLACE_STATE when set (blank counts as unset), else ~/.mcp-gerard/laplace."""
    configured = os.environ.get("LAPLACE_STATE", "").strip()
    return Path(configured).expanduser() if configured else Path.home() / ".mcp-gerard" / "laplace"
