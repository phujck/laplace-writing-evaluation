"""The cut instrument: per-seam cut composition and the orientation budget.

The cut law (DESIGN_2026-08-08b): at every seam of the telling's linear order there is a
cut — the set of claim-graph edges crossing that point. The cut is the reader's working
memory, formally. Orientation prose is licensed only where the cut licenses it (budget
proportional to cut size) and must realise edges *in* the cut; economy governs everything
else. This module computes the cuts; the orientation probe (dispatched, not here) checks
whether the manuscript's seam prose realises them. All deterministic, no model.

Run: python3 -m laplace.pipeline.writing_organ.breath <manuscript_dir>
Prints the seam report and writes <manuscript_dir>/breath_report.json.
"""

from __future__ import annotations

import json
import sys
import pathlib

# One orientation sentence licensed per this many open edges at the seam, minimum one
# at every movement boundary (the bridge is always owed).
EDGES_PER_BREATH = 12


def load(manuscript_dir: pathlib.Path) -> tuple[dict, dict]:
    graph = json.loads((manuscript_dir / "claim_graph.json").read_text())
    telling = json.loads((manuscript_dir / "telling_line.json").read_text())
    return graph, telling


def linear_order(telling: dict) -> tuple[list[str], list[tuple[str, int]]]:
    """The telling's atom order and the movement boundaries as (title, position)."""
    order: list[str] = []
    boundaries: list[tuple[str, int]] = []
    for movement in telling["line"]:
        boundaries.append((movement["movement"], len(order)))
        order.extend(a["id"] if isinstance(a, dict) else a for a in movement["atoms"])
    return order, boundaries


def seam_cuts(order: list[str], edges: list[dict]) -> list[list[dict]]:
    """cuts[i] = edges crossing the seam between position i-1 and i (cuts[0] empty)."""
    pos = {a: i for i, a in enumerate(order)}
    cuts: list[list[dict]] = [[] for _ in range(len(order) + 1)]
    for e in edges:
        if e["src"] not in pos or e["dst"] not in pos:
            continue
        a, b = pos[e["src"]], pos[e["dst"]]
        lo, hi = (a, b) if a < b else (b, a)
        for s in range(lo + 1, hi + 1):
            cuts[s].append(e)
    return cuts


def movement_report(graph: dict, telling: dict) -> list[dict]:
    label = {v["id"]: v.get("label", "") for v in graph["vertices"]}
    order, boundaries = linear_order(telling)
    cuts = seam_cuts(order, graph["edges"])
    report = []
    for i, (title, position) in enumerate(boundaries):
        cut = cuts[position] if position > 0 else []
        by_rel: dict[str, int] = {}
        for e in cut:
            by_rel[e["rel"]] = by_rel.get(e["rel"], 0) + 1
        held = sorted({e["src"] for e in cut})
        report.append({
            "movement": title,
            "question": telling["line"][i]["question"],
            "seam_position": position,
            "cut_size": len(cut),
            "cut_by_rel": dict(sorted(by_rel.items())),
            "breath_budget": max(1, len(cut) // EDGES_PER_BREATH) if position > 0 else 1,
            "held_open": [{"id": h, "label": label.get(h, "")[:90]} for h in held[:12]],
        })
    return report


def peak_positions(graph: dict, telling: dict, top: int = 8) -> list[dict]:
    """The highest-cut positions inside movements - where intra-movement breath is owed
    (display equations and dense hand-offs live here)."""
    label = {v["id"]: v.get("label", "") for v in graph["vertices"]}
    order, boundaries = linear_order(telling)
    starts = {p for _, p in boundaries}
    cuts = seam_cuts(order, graph["edges"])
    sizes = [(len(c), i) for i, c in enumerate(cuts[: len(order)]) if i not in starts and i > 0]
    peaks = []
    for size, i in sorted(sizes, reverse=True)[:top]:
        peaks.append({"position": i, "cut_size": size,
                      "atom": order[i], "label": label.get(order[i], "")[:90]})
    return peaks



def movement_contracts(manuscript_dir: pathlib.Path, word_budgets: dict[str, int] | None = None) -> list:
    """Movement contracts carrying the cut law: question, beats, and breath budget per
    movement, derived from the telling and the cut meter - never authored by hand."""
    from .schema import MovementContract
    graph, telling = load(manuscript_dir)
    report = movement_report(graph, telling)
    contracts = []
    for m, r in zip(telling["line"], report):
        atoms = [a["id"] if isinstance(a, dict) else a for a in m["atoms"]]
        claims = [a for a in atoms if str(a).startswith("RQ-CLM")]
        contracts.append(MovementContract(
            id=m["movement"], establishes=claims, assumes=[],
            word_budget=(word_budgets or {}).get(m["movement"], m.get("word_budget", 0)),
            question=m["question"], breath_budget=r["breath_budget"],
        ))
    return contracts


def main() -> int:
    md = pathlib.Path(sys.argv[1])
    graph, telling = load(md)
    movements = movement_report(graph, telling)
    peaks = peak_positions(graph, telling)
    out = {"movements": movements, "intra_movement_peaks": peaks,
           "provenance": {"built_by": "breath.py", "edges_per_breath": EDGES_PER_BREATH,
                          "law": "DESIGN_2026-08-08b_the-cut-law.md"}}
    (md / "breath_report.json").write_text(json.dumps(out, indent=1))
    print(f"seams: {len(movements)} movements over {sum(len(m['atoms']) for m in telling['line'])} atoms")
    for m in movements:
        print(f"  cut {m['cut_size']:3d}  breath {m['breath_budget']}  {m['movement']}")
    print("intra-movement peaks (breath owed at these positions):")
    for p in peaks:
        print(f"  cut {p['cut_size']:3d}  pos {p['position']:3d}  {p['atom']}  {p['label'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
