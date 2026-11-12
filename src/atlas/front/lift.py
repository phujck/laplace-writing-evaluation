"""Front reconstruction capability: one qualified implementation, ordinary imports.

The original judged algorithms now live in atlas.reconstruction inside this Atlas
wheel. The declarations below retain inventory purpose; Atlas never reaches into
an accidental research checkout. atlas.lifted owns scoped source observations and
named optional dependency refusal. Historical experiments/replay are separate.
"""

from __future__ import annotations

from ..lifted import load, receipt, require_current, check_current, stable_basis
from pathlib import Path
from typing import Any

__all__ = ["EXTENSION_ROOT", "RECONSTRUCTION_ROOT", "LIFTED", "lifted", "lift_receipt",
           "require_current", "check_current", "stable_basis"]

_HERE = Path(__file__).resolve()
RECONSTRUCTION_ROOT = _HERE.parents[1] / "reconstruction"
EXTENSION_ROOT = RECONSTRUCTION_ROOT

# module -> (where it lives, its INVENTORY.json verdict, what this packet uses it FOR).
LIFTED: dict[str, tuple[Path, str, str]] = {
    "query_plan": (EXTENSION_ROOT, "REUSE_WITH_FIX",
                   "the typed plan objects are the compiler's OUTPUT SHAPE: QueryPlan, "
                   "EvidenceObligation, ClaimObligation, DateObligation, ContextBinding, "
                   "IdentityConstraint, LogicConstraint, BindingAlternative, TextSpan"),
    "query_obligations": (EXTENSION_ROOT, "REUSE_WITH_FIX",
                          "the obligation vocabulary the plan's obligations are checked against"),
    "lexical_index": (EXTENSION_ROOT, "REUSE_WITH_FIX",
                      "the lexical predicate: surface -> candidate rows, no embedding"),
    "integer_contraction": (EXTENSION_ROOT, "REUSE_WITH_FIX",
                            "EXACT joint counts from primitive integer messages - the joint "
                            "count the frontier descent must not try to infer"),
    "contraction_kernels": (EXTENSION_ROOT, "REUSE_WITH_FIX",
                            "the MANDATORY CONTROL, kept verbatim: the packed direct scan "
                            "(pack_binary_rows, prepare_boolean_queries, prepare_direct, "
                            "packed_direct_count)"),
    "memory_packing": (EXTENSION_ROOT, "REUSE_AS_IS",
                       "the seam cache and atomic groups of the evidence pack"),
    "context_budget": (EXTENSION_ROOT, "REUSE_WITH_FIX",
                       "the byte budget the evidence stage spends against"),
    "mandatory_packing": (EXTENSION_ROOT, "REUSE_WITH_FIX",
                          "the mandatory-first packing order inside that budget"),
    "evidence_selection": (EXTENSION_ROOT, "REUSE_WITH_FIX",
                           "the typed exact-mask half (MetadataColumn, prepare_section, "
                           "_exact_mask) - the SCORING half is never reached from here"),
    "gpu_state": (RECONSTRUCTION_ROOT, "REUSE_WITH_FIX",
                  "the exact conditional-law quotient the integer contraction contracts "
                  "against: build_state (gpu_state.py:327), contract (:476), marginal (:787)"),
    "section_coupling": (RECONSTRUCTION_ROOT, "REUSE_WITH_FIX",
                         "the route-weighted quotient and tuple-posting CSR: build_coupling "
                         "(section_coupling.py:122), intersection_mass (:268), reached_sources "
                         "(:521) - the second exact route to a joint count, and the route back "
                         "from a selected tuple to the SOURCE ROWS it was drawn from"),
}

def lifted(name: str) -> Any:
    """Return the one canonical qualified object, never a bare-name alias."""
    if name not in LIFTED:
        raise KeyError(f"LIFT-MODULE-NOT-DECLARED: {name}")
    return load(name)


def lift_receipt(names=None, *, observe_current=True) -> dict[str, Any]:
    """Scoped consumed-source observations, separate from executed-byte proof."""
    requested = tuple(LIFTED) if names is None else names
    if any(name not in LIFTED for name in requested):
        raise KeyError("LIFT-MODULE-NOT-DECLARED")
    return receipt(requested, observe_current=observe_current)
