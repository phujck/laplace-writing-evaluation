"""closure_meter.py - T1 of the structuring loop: what the descent DID, banked per descend.

Pre-registered in ``DESIGN_2026-08-11_the-structuring-loop.md`` §4 organ 1 ("the closure meter -
build first, changes nothing"), granted 2026-08-16 ("yes land T1 now, it's free"). It is the
INSTRUMENT half of the loop and nothing else: the up never hears the down today (design §3,
"NOTHING flows from descent traffic back into geometry"), and this module is the ear, not the
mouth. It reads a finished descent's own observations and appends one row. It never routes,
never scores, never re-fires, never proposes.

Where the row lives: the design names the home as "Rung 13a's history store - the environment
record the DMRG frame says is missing". That store is ``atlas/stores/history.jsonl``
(``DESIGN_2026-08-01_the-atlas.md`` §4: "Reconstruction history lives in stores/history.jsonl,
never in the bundle") and Rung 13a has NOT been built - the atlas gauntlet lists it as the
serve-path rung still ahead, and neither the file nor its writer exists in the tree. So this
module banks to ``.closure_meter.jsonl`` at the repo root, in the shape of a sibling dot-store
ledger (``.wire_verdicts.jsonl``): append-only JSONL, one row per event, an ISO-8601 UTC ``ts``
per row. When Rung 13a lands, ``STORE_FILE`` is the one line that moves and ``read_rows`` is the
one reader that follows it; the row schema is deliberately store-agnostic.

IT TRAVELS. No ``.gitignore`` rule is added and none is wanted: the sibling precedent is explicit
in that file - ".wire_verdicts.jsonl now TRAVELS ... the wire/grit/noise judgment history is
accumulated canon, not a local instrument". Banked descent traffic is the same kind of object (it
is the ENVIRONMENT RECORD the whole loop is to be fitted against), so it travels by the same rule.

THE GUARD, honored literally. Design §4: "only need-fired reaches count (dutiful fire poisons any
such signal - kill-board item, honored)". Two halves:
  1. The meter adds NO descents of its own. It has no probe, no warm-up, no replay. Every row is
     a reach some caller already needed to make; if nothing descends, nothing is banked.
  2. The meter cannot know need, so it never claims it. ``fire`` defaults to ``"unattributed"``
     and only a caller (or ``LAPLACE_CLOSURE_FIRE``) can say ``"need"`` / ``"dutiful"``. A
     consumer computing residual MUST filter to ``fire == "need"``; defaulting to "need" would
     silently enrol the harness's 40 bench probes as real traffic, which is exactly the poisoning
     the guard names.

LOUD-DEGRADE, the module's half of the law. ``recursive_read``'s descent is loud by design - every
unavailability is a ``RecursiveReadError`` at the call site. The METER is the opposite polarity and
says so: a store that cannot be written must never cost a caller its answer. So the banking call
is wrapped at the seam and degrades to ONE stderr line. Loud, non-fatal, never silent - a bare
``except: pass`` here would be the 07-24 regression rebuilt inside the instrument that exists to
detect exactly that class of thing.

CLOCK DISCIPLINE. ``ts`` is wall-clock UTC to the second, the same call
(``datetime.now(timezone.utc).isoformat(timespec="seconds")``) and the same shape the wire ledger
banks. Wall clock can step backwards under NTP, so it is a LABEL, never the order: the ledger is
append-only and APPEND ORDER is the ordering. ``seconds`` (the descent's own duration) rides the
row from ``time.perf_counter``, which is monotonic - so every DURATION in the store is monotonic-
safe and no row's timing depends on the wall clock at all. No stamping pass, no rewrite, no sort.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STORE_FILE = ".closure_meter.jsonl"   # the placeholder home; Rung 13a's atlas/stores/history.jsonl supersedes
SCHEMA = "closure-meter/v1"
ENV_DISABLE = "LAPLACE_CLOSURE_METER"  # "0"/"off"/"false" kills the banking outright
ENV_FIRE = "LAPLACE_CLOSURE_FIRE"      # lets an out-of-process caller declare need/dutiful

FIRE_CLASSES = ("need", "dutiful", "unattributed")

# The design names four per-node route stats. Three have an operational referent in today's
# descent; ONE does not, and is banked as null rather than fabricated (see _node_rows).
NULL_STATS_NOTE = {
    "digest_decided": (
        "NULL, not zero: today's descent has no digest-decide. A cluster centroid is a RANKING "
        "signal only - it orders a level so the beam can keep `beam` of it - and it never answers "
        "a query and never terminates a branch. Every kept branch is descended to exhaustion, "
        "every entered node's direct leaves are materialized regardless of what its centroid "
        "said, and every returned hit is a LEAF. So 'the cut closed at the digest' (design §2's "
        "commuting sector) has no event to count here. It gains one the moment a digest-stop rule "
        "exists - a node whose digest answers without descent. Until then: null. The adjacent "
        "thing the descent does do is recorded beside it as `digest_pruned` (scored, then "
        "not entered), which is a routing decision, not a closure."),
    "terminal_holdout_self_score": (
        "NULL, not zero: a live descend holds no held-out answer to score itself against. The "
        "only scoring surfaces that exist are external and offline - scripts/recursive_read_"
        "harness.py against the flat-cache oracle, and holdout.py's F25 prediction machinery, "
        "neither of which a descent can reach from inside itself. Scoring the descent by the "
        "cosines it just ranked by would be the descent grading its own ruler. The row banks "
        "`top1_score`/`mean_topk_score` as what the descent RETURNED (plain observations, not a "
        "self-grade) and leaves the self-score null until a scored recall exists to fill it - "
        "which is precisely what Rung 13a's history store is specified to carry."),
}


def _now() -> str:
    """Wall-clock UTC to the second - the wire ledger's exact stamp shape. A label, not the order."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def enabled() -> bool:
    """The banking kill-switch. On by default; ``LAPLACE_CLOSURE_METER=0`` turns it off."""
    return os.environ.get(ENV_DISABLE, "").strip().lower() not in ("0", "off", "false", "no")


def declared_fire(explicit: str | None = None) -> str:
    """Who says this reach was need-fired. Never guessed: caller argument, then env, then
    ``"unattributed"``. An unrecognised value is kept verbatim rather than coerced - a consumer
    filtering on ``fire == "need"`` is unharmed by a label it does not know, whereas silently
    rewriting a caller's word to a class it did not choose is how a guard gets hollowed out."""
    for candidate in (explicit, os.environ.get(ENV_FIRE)):
        if candidate:
            return str(candidate).strip()
    return "unattributed"


# ---------------------------------------------------------------------------
# the row - per-node route stats over one descent
# ---------------------------------------------------------------------------

def _node_rows(obs: dict[str, Any]) -> list[dict[str, Any]]:
    """One record per cluster the descent touched, in the order the descent touched it.

    ``obs`` carries only raw facts the descent already had in hand (no recomputation, no second
    pass over the tree). The four design stats, operationalized:

    entered              - the descent went INTO the node: the beam kept it, its direct leaf
                           children were materialized and scored, its cluster children became the
                           next level. The root is entered by construction (level zero, no handle
                           above it to prune on). A scored-but-not-kept node is NOT entered.
    digest_decided       - null, always. See NULL_STATS_NOTE.
    children_materialized- direct leaf children whose vectors were recomputed and scored under
                           this node. This is the node's COST: the embedding work the descent
                           spent by entering it. Zero for a node it never entered.
    wasted               - materialized-here minus returned-from-here: leaf vectors this node's
                           cost paid for that reached the caller's top-k not at all. Cost with no
                           answer behind it. Zero where no cost was paid; it is never negative,
                           since every returned hit was materialized under the node it hangs from.
    """
    entered: list[str] = list(obs["entered_order"])
    entered_set = set(entered)
    digest_score: dict[str, float] = obs["digest_score"]
    mat_by_node: dict[str, int] = obs["materialized_by_node"]
    hits_by_node: dict[str, int] = obs["hits_by_node"]
    depth_by_node: dict[str, int] = obs["depth_by_node"]
    branch_by_node: dict[str, int] = obs["cluster_children_by_node"]

    # every node the descent touched: entered ones first (in descent order), then the ones it
    # scored and passed over (the pruned frontier - the crossings T2 will want).
    ordered = entered + [cid for cid in digest_score if cid not in entered_set]
    rows = []
    for cid in ordered:
        is_entered = cid in entered_set
        scored = cid in digest_score
        materialized = int(mat_by_node.get(cid, 0))
        hits = int(hits_by_node.get(cid, 0))
        rows.append({
            "node": cid,
            "depth": depth_by_node.get(cid),
            "digest_score": round(digest_score[cid], 6) if scored else None,
            "entered": is_entered,
            "digest_decided": None,
            "children_materialized": materialized,
            "hits": hits,
            "wasted": materialized - hits,
            # neighbours of the null stat, never a stand-in for it:
            "digest_pruned": (not is_entered) if scored else None,
            "cluster_children": int(branch_by_node.get(cid, 0)) if is_entered else 0,
        })
    return rows


def build_row(packet: dict[str, Any], obs: dict[str, Any], fire: str | None = None) -> dict[str, Any]:
    """The banked record for ONE descend: what it did, per node, plus the descent's own totals.

    Derived from the packet the descent already returns and the raw observations it already held.
    Nothing here re-reads the tree, re-embeds anything, or fires a second descent."""
    nodes = _node_rows(obs)
    hits = packet.get("hits") or []
    scores = [h["score"] for h in hits]
    materialized = sum(n["children_materialized"] for n in nodes)
    wasted = sum(n["wasted"] for n in nodes)
    answer_nodes = {h["cluster"] for h in hits}
    path_union: set[str] = set()
    for h in hits:
        path_union.update(h.get("path") or ())
    return {
        "schema": SCHEMA,
        "ts": _now(),
        "fire": declared_fire(fire),
        "query": packet.get("query"),
        # the tree's root id, named explicitly because it is legitimately the empty string on the
        # live fold - the depth-0 node row would otherwise read as a nameless entry
        "root_id": obs.get("root_id"),
        "axis": packet.get("axis"),
        "backend": packet.get("backend"),
        "tree_version": packet.get("tree_version"),
        "lens_hash": packet.get("lens_hash"),
        "geometry": packet.get("geometry"),
        "totals": {
            "scored": sum(1 for n in nodes if n["digest_score"] is not None),
            "entered": sum(1 for n in nodes if n["entered"]),
            "digest_pruned": sum(1 for n in nodes if n["digest_pruned"]),
            "digest_decided": None,          # see NULL_STATS_NOTE
            "children_materialized": materialized,
            "wasted": wasted,
            "waste_rate": round(wasted / materialized, 4) if materialized else None,
            "clusters_total": packet.get("n_clusters_total"),
            "leaves_total": packet.get("n_leaves_total"),
        },
        # ν(q), design §8: "the minimal subtree cover of the query's answer support -
        # operationally, the cuts crossed + branches held simultaneously ... ALREADY what the
        # closure meter (T1) banks per descent". Banked as the observable triple, flagged a
        # CANDIDATE operationalization - §8 is conjecture-status and does not fix the estimator.
        "nu": {
            "status": "candidate",
            "answer_cover": len(answer_nodes),      # distinct cuts the returned answer hangs from
            "path_union": len(path_union),          # clusters on the union of those hits' paths
            "max_frontier": obs.get("max_frontier"),  # widest level held simultaneously
        },
        "terminal_holdout_self_score": None,        # see NULL_STATS_NOTE
        "top1_score": scores[0] if scores else None,
        "mean_topk_score": round(sum(scores) / len(scores), 6) if scores else None,
        "n_hits": len(hits),
        "stale": packet.get("stale"),
        "seconds": packet.get("seconds"),           # perf_counter - monotonic, not wall clock
        "nodes": nodes,
        "notes": NULL_STATS_NOTE,
    }


# ---------------------------------------------------------------------------
# the store - append-only, and never fatal
# ---------------------------------------------------------------------------

def store_path(repo_root: Path | str) -> Path:
    return Path(repo_root) / STORE_FILE


def append_row(repo_root: Path | str, row: dict[str, Any]) -> Path:
    """Append one row. Raises on failure - ``bank`` is the seam that swallows it loudly."""
    path = store_path(repo_root)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def bank(repo_root: Path | str, packet: dict[str, Any], obs: dict[str, Any],
         fire: str | None = None) -> Path | None:
    """Build and append the row for one descent. NEVER raises into the caller.

    The loud-degrade split this module exists under: the DESCENT is loud (a broken read path is a
    ``RecursiveReadError`` at the call site), the METER degrades loud-but-nonfatal (a broken
    ledger costs one stderr line and nothing else). Every exception class is caught - an
    unwritable store, a full disk, a row that will not serialize - because there is no failure
    here worth an answer. Returns the path on success, None on degrade."""
    if not enabled():
        return None
    try:
        return append_row(repo_root, build_row(packet, obs, fire=fire))
    except Exception as exc:  # noqa: BLE001 - deliberate: a meter must not cost a descent
        print(f"closure meter: DEGRADED, row not banked to {STORE_FILE} "
              f"({type(exc).__name__}: {exc}) - the descent is unaffected",
              file=sys.stderr)
        return None


def read_rows(repo_root: Path | str, fire: str | None = None) -> list[dict[str, Any]]:
    """Read the banked rows in append order (which IS their order - see the module header).

    ``fire`` filters, and a consumer computing residual should pass ``fire="need"``: the design's
    guard is that dutiful fire poisons the signal, and this is where that filter is applied.
    Unparseable lines are skipped with a stderr line rather than raising - a half-written tail row
    (the one thing an append-only ledger can leave behind) must not make the whole store
    unreadable."""
    path = store_path(repo_root)
    if not path.is_file():
        return []
    rows = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            print(f"closure meter: skipping unparseable row {i} in {STORE_FILE} ({exc})",
                  file=sys.stderr)
            continue
        if fire is None or row.get("fire") == fire:
            rows.append(row)
    return rows
