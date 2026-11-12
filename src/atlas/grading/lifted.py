"""A.35(a) optional numeric capabilities; A.35(b) remains refused by name.

Canonical code lives once in atlas.reconstruction. Ordinary qualified imports own
module identity; atlas.lifted owns source observations/currentness. No research
root discovery, bare modules, hot reload or scientific acceptance is implied.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from ..lifted import load, receipt, REFUSED_BY_A35

__all__ = ["RECONSTRUCTION_DIR", "LIFTED_BY_A35", "REFUSED_BY_A35",
           "section_calculus", "section_block_operator", "forbidden_import_check",
           "lift_receipt"]

RECONSTRUCTION_DIR = Path(__file__).resolve().parents[1] / "reconstruction"

LIFTED_BY_A35 = ("section_calculus", "section_block_operator")

# A.35(b), verbatim in intent: "Nothing in (b) may be imported, re-implemented or defaulted to
# by an Atlas lane."


class LiftViolation(RuntimeError):
    """Raised when a module A.35(b) refuses has entered the process through this package."""


def section_calculus() -> ModuleType:
    """The lifted A.35(a) coarse-section calculus. Complexity: O(1)."""
    return load("section_calculus")


def section_block_operator() -> ModuleType:
    """The lifted A.35(a) sparse block transport. Complexity: O(1)."""
    return load("section_block_operator")


def forbidden_import_check() -> dict[str, Any]:
    """Assert no A.35(b) module is in the process. Complexity: O(|sys.modules|)."""
    present = sorted(name for name in sys.modules if name in REFUSED_BY_A35
                     or name.removeprefix("atlas.reconstruction.") in REFUSED_BY_A35)
    if present:
        raise LiftViolation(
            "A.35(b) refuses these by name and one is imported: " + ", ".join(present))
    return {"refused_by_A35b": list(REFUSED_BY_A35), "present_in_process": present,
            "verdict": "clean"}


def lift_receipt(names=None, *, observe_current=True) -> dict[str, Any]:
    """The common scoped basis, plus retained A.35(a)/(b) labels."""
    requested = LIFTED_BY_A35 if names is None else tuple(names)
    if any(name not in LIFTED_BY_A35 for name in requested):
        raise KeyError("LIFT-MODULE-NOT-DECLARED")
    result = receipt(requested, observe_current=observe_current)
    result["clause"] = "A.35(a)"
    result["lifted"] = {row["name"]: row.get("current_disk", row["first_adapter"])
                        for row in result["modules"] if row["name"] in requested}
    result["refused"] = forbidden_import_check()
    return result
