#!/usr/bin/env python3
"""Every figure the whole-system account quotes, printed from the tree that produced it.

One producer, so the chapter and the report cannot carry a number the tree does not make.

    scripts/laplace-python tools/whole_figures.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laplace.core import grammar as g                      # noqa: E402
from laplace.core import identity_doors                    # noqa: E402
from laplace.native import declarations as d         # noqa: E402
from laplace.native import verbs as writing_verbs                     # noqa: E402


def figures() -> dict:
    """Every figure the report quotes, as a dict, so a proof can read the same numbers."""
    out: dict = {}

    out["verbs"] = sorted(g.VERBS)
    out["n_verbs"] = len(g.VERBS)
    out["n_home_kinds"] = len(g.HOME_KINDS)
    out["n_declared_pairs"] = len(g.VERB_CONCEPTS)
    out["n_concepts"] = len({concept for _, concept in g.VERB_CONCEPTS})
    out["n_routes"] = len(writing_verbs.ROUTES)
    out["n_operations"] = len(d.DECLARATIONS)
    out["n_http_declarations"] = len(d.HTTP_DECLARATIONS)

    pairs = {}
    for operation in d.DECLARATIONS:
        for act in writing_verbs.pairs_for(operation):
            pairs.setdefault(act, []).append(operation)
    out["acts_an_operation_name_hides"] = sum(
        len(writing_verbs.pairs_for(operation)) for operation in d.DECLARATIONS)
    out["operations_with_more_than_one_act"] = sorted(
        operation for operation in d.DECLARATIONS
        if len(writing_verbs.pairs_for(operation)) > 1)

    shim_routes = [route for route in writing_verbs.ROUTES if getattr(route, "expiry", "")]
    out["routes_with_an_expiry"] = len(shim_routes)
    out["routes_total"] = len(writing_verbs.ROUTES)
    # `DOORS` is a dict keyed by the old operation name, so iterating it yields the KEYS.
    # Until the closing read of 2026-10-02 this asked each key --- a `str` --- for an `expiry`
    # and published `identity_doors_with_an_expiry: 0` while all 13 shim rows carried
    # `identity_doors.EXPIRY` (src/laplace/identity_doors.py:57).  The rows are the values, and
    # `test_the_identity_door_expiry_figure_is_the_count_the_tree_holds` holds the published
    # figure to the module, so this instrument cannot report an absent expiry again.
    doors = getattr(identity_doors, "DOORS", ())
    rows = list(doors.values()) if hasattr(doors, "values") else list(doors)
    out["identity_doors_declared"] = len(rows)
    out["identity_doors_with_an_expiry"] = sum(
        1 for row in rows if getattr(row, "expiry", ""))
    out["identity_door_expiry"] = getattr(identity_doors, "EXPIRY", "")
    out["base_revision"] = d.BASE_REVISION
    out["base_revision_expiry"] = getattr(d, "BASE_REVISION_EXPIRY", "")
    out["coordinate_law"] = d.COORDINATE_LAW

    rules = [rule for decl in d.DECLARATIONS.values() for rule in decl.rules]
    out["rule_instances"] = len(rules)
    # RECONCILED WITH THE OTHER INSTRUMENT, because two numbers for one thing is the disease.
    # `tools/door_citations.py` prints `rule_instances` too and prints a LARGER number: it
    # counts every typed COORDINATE, which is a different set from every rule instance.  It
    # includes the five HTTP declarations' rules, excludes any rule that carries no `door`,
    # and adds two things that are declaration fields rather than `Rule` rows --- each
    # declaration's `turn_door` (kind `turn_bound`, which is why a kind appears there that
    # `rule_kinds` below does not list) and each HTTP declaration's `header_door` (kind
    # `header`).  Both numbers are published here so a reader never has to re-derive the
    # difference, and `test_the_two_rule_counts_reconcile` holds the arithmetic.
    http_rules = [rule for decl in d.HTTP_DECLARATIONS.values() for rule in decl.rules]
    out["rule_instances_http_declarations"] = len(http_rules)
    out["rule_instances_without_a_typed_coordinate"] = sum(
        1 for rule in rules + http_rules if not rule.door)
    out["rule_instances_with_a_typed_coordinate"] = sum(
        1 for rule in rules + http_rules if rule.door)
    out["turn_doors"] = sum(
        1 for decl in list(d.DECLARATIONS.values()) + list(d.HTTP_DECLARATIONS.values())
        if decl.turn_door)
    out["header_doors"] = sum(
        1 for decl in list(d.DECLARATIONS.values()) + list(d.HTTP_DECLARATIONS.values())
        if getattr(decl, "header_door", ""))
    out["typed_coordinates_counted_by_door_citations"] = (
        out["rule_instances_with_a_typed_coordinate"] + out["turn_doors"]
        + out["header_doors"])
    out["acts_block_expiry"] = getattr(d, "ACTS_BLOCK_EXPIRY", "")
    out["rule_kinds"] = {}
    for rule in rules:
        out["rule_kinds"][rule.kind] = out["rule_kinds"].get(rule.kind, 0) + 1
    out["identity_rules"] = sum(1 for rule in rules if rule.kind == "identity")
    out["identity_rules_with_a_home"] = sum(
        1 for rule in rules if rule.kind == "identity" and rule.home)
    out["distinct_guard_fields_declared"] = len(
        {rule.field for rule in rules if rule.kind == "identity" and rule.field})
    out["distinct_homes_declared"] = len(
        {rule.home for rule in rules if rule.kind == "identity" and rule.home})

    mint = getattr(g, "MINT_STATUS", {})
    out["home_kinds_obtainable_from_the_home_alone"] = sum(
        1 for value in mint.values() if value == "read")
    out["home_kinds_needing_a_caller_value"] = sum(
        1 for value in mint.values() if value != "read")

    return out


def main() -> int:
    print(json.dumps(figures(), indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
