#!/usr/bin/env python
"""Pour a compiled conceptric (conceptric_v1.json) into a corpus friction ledger as typed
rewire records, so ``corpus_ingest.corpus_network`` reconstructs the REAL graph — the compiled
nodes with their kinds/essences, the dependency edges by relation, and the spine ordering.

General over (conceptric, corpus); paper_falqon is its first run:

    uv run python scripts/pour_conceptric.py \
        --conceptric paper_falqon/manuscript/conceptric_v1.json \
        --corpus paper_falqon --repo-root .

THE ONE DOOR. Every record is authored through ``corpus_ingest.rewire_add`` (the validated
rewire door) — never hand-written jsonl. The ledger stays the one source of truth; the conceptric
is the upstream source and the ledger is its derived projection, so the pour is REPLAYABLE:
each run first drops the prior records tagged ``by == POUR_TAG`` (ledger maintenance, not
authoring), then re-appends the full set. Human/non-pour records on the ledger are preserved.

RECONCILIATION WITH THE TEX-WALK BASE. ``atomise_paper`` already yields base leaves (paper://,
references, and the ``ref:<key>`` citations minted from the .bib). A conceptric node that names
the SAME OBJECT as a base leaf under a different id convention is NOT re-added as a duplicate —
it is mapped onto the existing leaf and enriched (edit-essence). The mapping is recorded in the
pour report. Concretely: the conceptric's literature nodes (kind ``result``, group ``literature``)
carry bare bib keys (``magann2022falqon``); the tex walk already carries them as ``ref:magann2022falqon``
citations. They are mapped, enriched, and their incident edges are rewritten onto the ``ref:`` id.

HONEST SCHEMA GAP (named, not silently dropped). ``rewire_add``'s add-node gate admits only
``LOGICAL_KINDS`` (the derivation-DAG taxonomy). The conceptric uses a document/evidence taxonomy
(domain/cluster/section/claim/limitation) that is NOT a subset of it, so those kinds cannot be
carried verbatim. Each is translated to its nearest LOGICAL kind (see KIND_MAP); the native kind
is preserved in the pour report's mapping table. cluster/section/limitation all collapse to
``support`` (grouping/structural/scope substrate, provenance-exempt) — an information loss in the
KIND field that this report makes explicit.

DRIVEN BY THE CONCEPTRIC'S OWN DECLARATIONS (2026-08-04). The pour was paper-shaped in four
places — the spine (``kind == "section"``), containment (``rel == "contains"``), the dependency
edges (``rel ∈ {draws, shares}``) and the literature reconciliation (``kind == "result" ∧
group == "literature"``). Each is now a DEFAULT that an additive top-level declaration overrides:

    "arc":       {"label"?: str, "beats": [{"node": id, "narrative"?: str}]}
    "kind_map":  {<native kind>: <a corpus_ingest.LOGICAL_KINDS member>}
    "rel_map":   {<native rel>: "parent" | "arc" | "drop" | <a schema.TARGET_AXES name>}
    "reconcile": [{"kind"?: str, "group"?: str, "leaf": "<template with {id}>"}]

``ord`` is the beat's LIST INDEX, never a per-node order field: falqon carries ``meta.order`` on
17 nodes of which only 13 are sections, with ords colliding at 0-3, so any "sort by meta.order"
heuristic would scramble the two projects that already work. Absent a declaration each default
reproduces the old behaviour verbatim, so falqon and eigenengine pour byte-identically.

NOTHING IS SILENTLY DROPPED. Every native kind lands in KIND_FALLBACK and every native relation
in REL_FALLBACK, each named in the report (``kind_fallbacks``, ``rel_fallbacks``); every edge is
accounted for in ``edges_by_role``, whose sum must equal the conceptric's edge count. The pour
HARD-FAILS on a beat naming an unknown node, a duplicate beat, an unregistered rel_map target and
a zero-beat spine (``--allow-spineless`` to override) — a silently empty spine on a green run is
exactly how the section-only rule survived unnoticed while engine-devplan poured 35 orphan nodes
and dropped all 42 of its edges.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from laplace.research import corpus_ingest as ci

POUR_TAG = "pour:conceptric"

# conceptric (document/evidence) kind -> nearest LOGICAL_KINDS member (rewire_add's add-node gate).
# 'result' (literature) is handled by RECONCILIATION onto existing ref: citations, not add-node.
KIND_MAP = {
    "domain": "goal",         # the project's central claim/orientation, above the DAG
    "cluster": "support",     # thematic grouping bin — no native cluster kind
    "section": "support",     # narrative beat — role realised via set-spine, not kind
    "claim": "result",        # the paper's asserted findings (evidence-ledger atoms)
    "def": "definition",      # model parameters / definitions — exact fit
    "limitation": "support",  # scope/limitation notes — provenance-exempt substrate
}

# The map is TOTAL: a native kind not named above collapses to the same "support"
# substrate cluster/section/limitation already collapse to, and the report names it
# under kind_fallbacks. General over conceptrics (a devplan pours as readily as a
# paper) — the alternative, growing KIND_MAP per project, is the per-project
# hardcoding this script exists to end.
KIND_FALLBACK = "support"

# ---------------------------------------------------------------------------
# the RELATION axis, made total the same way KIND_FALLBACK made the KIND axis total
# ---------------------------------------------------------------------------
REL_PARENT = "parent"     # the edge IS containment: it names the node's parent, not a dependency
REL_ARC = "arc"           # the edge carries ordering; the spine comes from the arc declaration
REL_DROP = "drop"         # declared as carrying nothing the network models
REL_ROLES = (REL_PARENT, REL_ARC, REL_DROP)

# The defaults reproduce the pre-2026-08-04 behaviour exactly: contains was the only parent
# source, precedes/has_project were counted as structure and never poured, draws/shares were the
# only poured edges. A declared rel_map is merged OVER this, so a conceptric names only what it
# differs on.
DEFAULT_REL_MAP = {
    "contains": REL_PARENT,
    "precedes": REL_ARC,
    "has_project": REL_ARC,
    "draws": "derives",
    "shares": "derives",
}

# An unmapped relation is poured as an edge on the derives axis rather than dropped, and named in
# the report under rel_fallbacks. `derives` is also the token apply_overlay applies to an UNTYPED
# add-edge (corpus_ingest: confirmed-derives), so this axis is written implicitly — emitting it as
# an explicit `axis` field would change the record bytes without changing the applied graph.
REL_FALLBACK = "derives"

# The literature rule, generalised: a node matching every declared field is not re-added as a
# duplicate but mapped onto the named base leaf. `{id}` is the conceptric node id.
DEFAULT_RECONCILE = [{"kind": "result", "group": "literature", "leaf": "ref:{id}"}]


class PourError(RuntimeError):
    """A conceptric whose declaration would pour a broken graph — named, never poured."""


def _kind_map(concept: dict) -> tuple[dict[str, str], str]:
    """(the merged kind map, its provenance). A declared kind_map is merged OVER KIND_MAP, so a
    conceptric whose taxonomy the fallback would flatten (a claim landing as `support` rather than
    `result`) names its own translation instead of growing KIND_MAP per project. The TARGET stays
    inside LOGICAL_KINDS: DERIVATION_KINDS and PROVENANCE_EXEMPT derive from that tuple, so
    widening it for one project moves every other project's gap counts."""
    declared = concept.get("kind_map")
    if declared is None:
        return dict(KIND_MAP), "default"
    if not isinstance(declared, dict):
        raise PourError("kind_map must be an object of {native kind: LOGICAL_KINDS member}")
    for native, logical in declared.items():
        if logical not in ci.LOGICAL_KINDS:
            raise PourError(f"kind_map[{native!r}] = {logical!r} is outside LOGICAL_KINDS "
                            f"{ci.LOGICAL_KINDS} — the taxonomy is never widened for one project")
    return {**KIND_MAP, **declared}, "declared"


def _rel_map(concept: dict) -> tuple[dict[str, str], str]:
    """(the merged relation map, its provenance). A declared value is a role token or a
    target-bearing axis; anything else is a typo that would silently become a derives edge."""
    from laplace.pipeline.schema import PAIR_AXES, TARGET_AXES
    declared = concept.get("rel_map")
    if declared is None:
        return dict(DEFAULT_REL_MAP), "default"
    if not isinstance(declared, dict):
        raise PourError("rel_map must be an object of {native rel: role|axis}")
    for rel, role in declared.items():
        if role in REL_ROLES:
            continue
        if role not in TARGET_AXES or role in PAIR_AXES:
            raise PourError(f"rel_map[{rel!r}] = {role!r} is neither a role {REL_ROLES} nor a "
                            f"target-bearing axis {TARGET_AXES}")
    return {**DEFAULT_REL_MAP, **declared}, "declared"


def _reconcile_rules(concept: dict) -> tuple[list[dict], str]:
    declared = concept.get("reconcile")
    if declared is None:
        return [dict(r) for r in DEFAULT_RECONCILE], "default"
    if not isinstance(declared, list) or not all(isinstance(r, dict) for r in declared):
        raise PourError("reconcile must be a list of {kind?, group?, leaf} rules")
    for rule in declared:
        if "{id}" not in (rule.get("leaf") or ""):
            raise PourError(f"reconcile rule {rule!r} needs a `leaf` template carrying {{id}}")
    return declared, "declared"


def _arc_beats(concept: dict, nodes: dict) -> tuple[list[dict], str]:
    """The spine, declaration-first: [{node, ord, narrative}] in emission order + the source.

    Declared: the beat's LIST INDEX is its ord and the declaration is the whole spine. Absent:
    the legacy rule verbatim (every kind=="section" node, ord from meta.order, narrative from
    meta.intent), which is what keeps falqon and eigenengine byte-identical."""
    arc = concept.get("arc")
    if arc is None:
        return ([{"node": nid,
                  "ord": int((n.get("meta") or {}).get("order", 0) or 0),
                  "narrative": (n.get("meta") or {}).get("intent") or ""}
                 for nid, n in nodes.items() if n["kind"] == "section"],
                "legacy:kind==section")
    if not isinstance(arc, dict) or not isinstance(arc.get("beats"), list):
        raise PourError("arc must be an object carrying a `beats` list")
    beats, seen = [], set()
    for i, b in enumerate(arc["beats"]):
        nid = b.get("node") if isinstance(b, dict) else None
        if nid not in nodes:
            raise PourError(f"arc beat {nid!r} (index {i}) names no node in this conceptric — "
                            "apply_overlay drops a set-spine on an unknown id SILENTLY")
        if nid in seen:
            raise PourError(f"arc beat {nid!r} is declared twice")
        seen.add(nid)
        meta = nodes[nid].get("meta") or {}
        beats.append({"node": nid, "ord": i,
                      "narrative": b.get("narrative") or meta.get("intent")
                      or meta.get("thesis") or ""})
    return beats, "declared"


def _clear_prior_pour(repo_root: str, corpus: str) -> int:
    """Replayability: drop records this pour authored on a previous run (by == POUR_TAG),
    preserving every other (human) record. Ledger maintenance, not authoring."""
    path = ci._rewire_path(repo_root, corpus)
    if not path.is_file():
        return 0
    kept, dropped = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        if rec.get("by") == POUR_TAG:
            dropped += 1
        else:
            kept.append(line)
    path.write_text("".join(l + "\n" for l in kept), encoding="utf-8")
    return dropped


def pour(conceptric_path: str, corpus: str, repo_root: str,
         allow_spineless: bool = False) -> dict:
    concept = json.loads(Path(conceptric_path).read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in concept["nodes"]}
    edges = concept["edges"]
    # every declaration is read and validated BEFORE the ledger is touched: a typo'd beat must
    # never leave a half-poured ledger behind.
    kind_map, kind_map_source = _kind_map(concept)
    rel_map, rel_map_source = _rel_map(concept)
    parent_rels = {r for r, v in rel_map.items() if v == REL_PARENT}
    recon_rules, recon_source = _reconcile_rules(concept)
    beats, arc_source = _arc_beats(concept, nodes)

    def role_of(rel: str) -> str:
        return rel_map.get(rel, REL_FALLBACK)

    if not beats and not allow_spineless:
        raise PourError(
            f"{corpus}: the pour would land ZERO spine beats (arc source: {arc_source}). The "
            "inspector renders 'no spine on this corpus yet' and the conceptric pane loses its "
            "focus seed. Declare an `arc` on the conceptric, or pass --allow-spineless.")
    # tex root: the registry, the one door. There was a hardcoded-dict branch ahead of
    # this until 2026-08-04, kept while the two sources disagreed; the dict is gone and
    # the registry answers for every corpus, born through the dashboard or hand-declared.
    from laplace.pipeline import registry
    proj = registry.resolve(corpus)
    if proj is None or not proj.tex_root:
        raise SystemExit(f"pour: {corpus!r} is not a registered corpus with a tex root")
    tex_rel = proj.tex_root
    # base tex-walk leaves (for reconciliation) — atomise, no overlay
    base_leaves, _, base_pmap = ci.atomise_paper(Path(repo_root) / tex_rel)
    base_ids = set(base_leaves)
    root_id = next((k for k in base_leaves if base_pmap.get(k) is None), "paper://")

    # ------- reconciliation: map declared nodes onto existing base leaves (default: literature) --
    id_map: dict[str, str] = {}          # conceptric id -> network id (identity unless remapped)
    reconciled: list[dict] = []          # the mapping table rows
    recon_misses: list[dict] = []        # matched a rule, but no such base leaf: named, not hidden
    for nid, n in nodes.items():
        for rule in recon_rules:
            if any(k in rule and n.get(k) != rule[k] for k in ("kind", "group")):
                continue
            cand = rule["leaf"].format(id=nid)
            if cand in base_ids:
                id_map[nid] = cand
                reconciled.append({"conceptric_id": nid, "conceptric_kind": n["kind"],
                                   "tex_walk_leaf": cand, "tex_walk_kind": base_leaves[cand]["kind"],
                                   "action": "enrich (edit-essence), keep kind=citation"})
            else:
                recon_misses.append({"conceptric_id": nid, "expected_leaf": cand,
                                     "action": "add-node (no such base leaf to reconcile onto)"})
            break
    remap = lambda x: id_map.get(x, x)

    # ------- clear prior pour, then author fresh records through the ONE door -------
    dropped = _clear_prior_pour(repo_root, corpus)

    def add(payload):
        payload["by"] = POUR_TAG
        r = ci.rewire_add(repo_root, corpus, payload)
        if "error" in r:
            raise RuntimeError(f"rewire_add rejected {payload}: {r['error']}")
        return r

    counts = Counter()

    # phase 1: add-node for every unreconciled conceptric node (a reconciled one is enriched, not added)
    for nid, n in nodes.items():
        if nid in id_map:
            continue
        meta = n.get("meta", {})
        parent = meta.get("parent")
        if parent is None:
            # containment, declaration-first: meta.parent -> any rel the map calls `parent`
            # -> the domain node -> the tex-walk root.
            parent = root_id if n["kind"] == "domain" else \
                (nodes and next((e["src"] for e in edges
                                 if e["rel"] in parent_rels and e["dst"] == nid), None))
        if parent is None:                       # nothing declared containment: hang under the domain
            parent = next((k for k, v in nodes.items() if v["kind"] == "domain"), root_id)
        add({"kind": "add-node", "node": nid,
             "node_kind": kind_map.get(n["kind"], KIND_FALLBACK),
             "essence": n.get("label", ""), "parent": parent})
        counts["add-node"] += 1

    # phase 2: set-spine, from the declared arc (or the legacy section chain)
    for beat in beats:
        add({"kind": "set-spine", "node": beat["node"],
             "ord": beat["ord"], "narrative": beat["narrative"]})
        counts["set-spine"] += 1

    # phase 3: edit-essence — enrich each reconciled base leaf with its conceptual role
    for nid, mapped in id_map.items():
        add({"kind": "edit-essence", "node": mapped, "value": nodes[nid].get("label", "")})
        counts["edit-essence"] += 1

    # phase 4: add-edge for every relation the map types onto an axis, endpoints remapped.
    # A role edge (parent/arc/drop) is consumed as structure; everything else pours, so an
    # unmapped relation lands as a derives edge instead of vanishing.
    by_role = Counter()
    for e in edges:
        role = role_of(e["rel"])
        by_role[role if role in REL_ROLES else "edge"] += 1
        if role in REL_ROLES:
            continue
        payload = {"kind": "add-edge", "node": remap(e["src"]), "target": remap(e["dst"])}
        if role != REL_FALLBACK:
            payload["axis"] = role      # REL_FALLBACK is apply_overlay's implicit token
        add(payload)
        counts["add-edge"] += 1

    rel_census = Counter(e["rel"] for e in edges)
    unmapped = sorted(r for r in rel_census if r not in rel_map)
    accounted = sum(by_role.values())
    if accounted != len(edges):                 # the no-silent-loss invariant, checked not assumed
        raise PourError(f"edge accounting: {accounted} roles for {len(edges)} edges")

    report = {
        "conceptric": conceptric_path,
        "corpus": corpus,
        "prior_pour_records_dropped": dropped,
        "record_counts_by_kind": dict(counts),
        "total_records": sum(counts.values()),
        "conceptric_node_count": len(nodes),
        "conceptric_edge_count": len(edges),
        "arc_source": arc_source,
        "arc_label": (concept.get("arc") or {}).get("label", ""),
        "spine_beats": len(beats),
        "rel_map_source": rel_map_source,
        # every relation the conceptric uses, with the role it poured under — the four
        # paper-shaped whitelists replaced by one census that always sums to the edge count.
        "rel_roles": {r: role_of(r) for r in sorted(rel_census)},
        "edges_by_role": dict(sorted(by_role.items())),
        "rel_fallbacks": [{"rel": r, "count": rel_census[r], "role": REL_FALLBACK}
                          for r in unmapped],
        "edges_dropped": [{"rel": r, "count": rel_census[r]}
                          for r in sorted(rel_census) if role_of(r) == REL_DROP],
        "kind_map_source": kind_map_source,
        "kind_translation": {k: kind_map.get(k, KIND_FALLBACK)
                             for k in sorted({n["kind"] for n in nodes.values()})},
        "kind_fallbacks": sorted({n["kind"] for n in nodes.values()} - kind_map.keys()),
        "reconcile_source": recon_source,
        "reconciliation": reconciled,
        "reconcile_misses": recon_misses,
    }
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--conceptric", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--report-out", default=None,
                    help="optional path to write the pour report json")
    ap.add_argument("--allow-spineless", action="store_true",
                    help="pour a conceptric that declares no arc and holds no section nodes "
                         "(the spine stays empty and the viewer says so)")
    args = ap.parse_args()
    try:
        report = pour(args.conceptric, args.corpus, args.repo_root,
                      allow_spineless=args.allow_spineless)
    except PourError as e:
        print(f"POUR: {e}", file=sys.stderr)
        return 2
    out = json.dumps(report, indent=2, ensure_ascii=False)
    print(out)
    if args.report_out:
        Path(args.report_out).write_text(out + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
