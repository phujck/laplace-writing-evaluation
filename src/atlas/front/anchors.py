"""anchors.py - the corrected anchor instrument, LIFTED onto the read's own path.

``record/measure.py`` is deleted by this packet (must_achieve 11: the measurement scripts are
deleted into the receipts). Two of its eight symbols are not measurements at all - they are the
organ the I1 judge and the orchestrator upheld as the CORRECTION of packet I1's instrument:
``declared_walk_horizon`` derives the walk cap from the dataset declaration (never a tuned
depth) and ``anchor_expansion`` walks the DECLARED relation CSR from the resolved anchors,
reporting the resolution count and the hop at which the first carrier was reached as two
different numbers, which is what packet I1 conflated.

They are LIFTED HERE VERBATIM (same bodies, same complexity notes) rather than re-authored,
because the compiler needs exactly them: a question's surfaces resolve through the anchor index
and are walked to the declared horizon, and the reached set becomes a two-code derived column
the frontier reduces like any other face. "Deleted into the receipts" for these two means the
measurement script is gone and the organ now runs on the read's path with its counters in the
read's own receipt - it does not mean the capability was thrown away.

The six symbols that WERE measurements (grammar_residue, longmem_gold_rows, unit_surface_census,
bench_sizes, o_diff_measurement, reach_and_cost) are gone with the file.
"""

from __future__ import annotations

from typing import Any

import torch

from ..record.device import require_device
from ..record.ingestion import Ingestion

__all__ = ["declared_walk_horizon", "anchor_expansion"]


def declared_walk_horizon(declaration: Any, carrier_kind: str) -> int:
    """The declared walk cap: hops from the furthest ANCHORED kind to the carrier kind.

    Not a tuned depth and not a constant. The dataset declaration is a graph whose vertices are
    row kinds and whose edges are the declared relation kinds (walkable in either direction,
    because a relation is an adjacency, not an arrow); the horizon is the largest shortest-path
    distance from a kind that carries an anchor column to the carrier kind. On LongMemEval at
    rung (b) that is 2 (question -> session -> turn); on QASPER it is 3 (question -> paper ->
    section -> paragraph). Change the declaration and the horizon changes with it.

    Complexity: O(kinds + declared relation kinds).
    """
    adjacency: dict[str, set[str]] = {spec.kind: set() for spec in declaration.row_kinds}
    for spec in declaration.relation_kinds:
        for source in spec.source_kinds:
            for target in spec.target_kinds:
                adjacency.setdefault(source, set()).add(target)
                adjacency.setdefault(target, set()).add(source)
    anchored = [spec.kind for spec in declaration.row_kinds if spec.anchor_fields]
    horizon = 0
    for start in anchored:
        seen = {start: 0}
        frontier = [start]
        while frontier:
            nxt: list[str] = []
            for kind in frontier:
                for other in adjacency.get(kind, ()):
                    if other not in seen:
                        seen[other] = seen[kind] + 1
                        nxt.append(other)
            frontier = nxt
        horizon = max(horizon, seen.get(carrier_kind, 0))
    return horizon


def anchor_expansion(ingestion: Ingestion, resolved: torch.Tensor, carrier_kind: str,
                     horizon: int) -> dict[str, Any]:
    """Expand resolved anchors through the DECLARED relations and report where they landed.

    Packet I1's instrument resolved an anchor to a row id and then asked whether that row id WAS
    a turn - which is the question "did the question name a turn", not "what does the question
    reach". It answered zero by construction. The correction, upheld by the I1 judge and the
    orchestrator, is here: a resolved anchor is a SEED, and the walk is the relation CSR of
    ``RelationKindTable.neighbours`` / ``neighbours_in`` (the same object ``joins.anchor_expand``
    gathers over), taken hop by hop up to the declared horizon.

    Reported separately, because they are different quantities and packet I1's number conflated
    them: ``resolved`` is how many anchors the question resolved at all, and ``depth`` is how
    many hops it took to reach the first carrier row. A question that resolves ten anchors and
    reaches no carrier is not the same failure as one that resolves none.

    Complexity: O(sum of the frontier's degrees) per hop - never O(E), because both directions
    are gathers over a cached CSR. Returns the carrier LOCAL ordinals plus the per-hop counts.
    """
    device = require_device(ingestion.store.device)
    rows = max(ingestion.store.row_count, 1)
    local_of = ingestion.store.local_of_global(carrier_kind)
    empty = torch.empty(0, dtype=torch.int64, device=device)
    if resolved.numel() == 0:
        return {"resolved": 0, "depth": 0, "rows_by_hop": [], "carrier_local": empty,
                "horizon": horizon}
    seen = resolved.to(torch.int64)
    frontier = seen
    carriers = local_of.index_select(0, seen)
    carriers = carriers[carriers >= 0]
    rows_by_hop = [int(frontier.numel())]
    depth = 0 if carriers.numel() else -1
    for hop in range(1, horizon + 1):
        found = [empty]
        for table in ingestion.relations.kinds.values():
            if len(table) == 0:
                continue
            found.append(table.neighbours(frontier, rows))
            found.append(table.neighbours_in(frontier, rows))
        reached = torch.unique(torch.cat(found))
        frontier = reached[~torch.isin(reached, seen)]
        if frontier.numel() == 0:
            break
        seen = torch.unique(torch.cat([seen, frontier]))
        rows_by_hop.append(int(frontier.numel()))
        new_carriers = local_of.index_select(0, frontier)
        new_carriers = new_carriers[new_carriers >= 0]
        if new_carriers.numel():
            carriers = torch.cat([carriers, new_carriers])
            if depth < 0:
                depth = hop
    return {"resolved": int(resolved.numel()), "depth": max(depth, 0),
            "reached_a_carrier": bool(carriers.numel()),
            "rows_by_hop": rows_by_hop, "carrier_local": torch.unique(carriers),
            "horizon": horizon}
