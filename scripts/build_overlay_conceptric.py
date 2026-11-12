#!/usr/bin/env python
"""Build a registered project's conceptric from a DECLARATION into its friction ledger.

The overlay form: a project whose graph has no tex to atomise (a campaign, a plan, a
design) carries an ~8-line stub ``main.tex`` so ``corpus_ingest.resolve_corpus`` accepts
it, and authors every node/edge/beat as rewire records that ``corpus_network`` replays.
Four registered corpora already ride that form (design_conceptric, qde, free-snacks,
subset-sum-itqde); this builder is the generic emitter for it — the project is named on
the command line and every constant lives in the declaration, so no project's name ever
enters engine code.

    <project_dir>/conceptric_overlay.json   the declaration (registry-resolved project_dir)
    <ledger>                                 the registry-resolved friction ledger

DECLARATION SHAPE (all keys required unless marked optional):
    ts        the record timestamp, fixed so two runs are byte-identical
    kind_map  native kind -> a corpus_ingest.LOGICAL_KINDS member. The native kinds are
              NEVER added to LOGICAL_KINDS: DERIVATION_KINDS and PROVENANCE_EXEMPT derive
              from that tuple, so every gap count and provenance score of every project
              would move. The native kind rides the node's ``projection`` slot instead.
    goal      {id, kind, term, essence, ref, supersedes?} — the apex; ``supersedes``
              retires an older goal (the dashboard scaffold's) so exactly one stays live
    nodes     [{id, kind, parent, term, essence, ref, projection?}] — ``projection`` is an
              OPTIONAL flat dict of extra emit-time slots merged into the node's
              ``set-projection`` value (``latex_label`` for the projection-label gate, an
              authored ``epistemic_status``, …). ``native_kind`` and ``term`` are the
              builder's own and are never overridden by it.
    edges     [{node, target, rel, axis?}] — ``rel`` is the native relation, carried on
              the record's ``value``; ``axis`` types the edge against schema.TARGET_AXES
    arc       {label?, beats: [{node, narrative?}]} — the DECLARED spine. ``ord`` is the
              beat's LIST INDEX; a per-node order field is never consulted (kinds and
              orders collide across projects, so only a declaration is total).

HARD FAILS (a silently empty or dangling spine on a green run is how R1 survived): an
unknown or duplicate beat id, zero beats, an unmapped native kind, a mapped kind outside
LOGICAL_KINDS, a dangling parent/edge endpoint, a parent cycle, an unregistered axis, and
a source ref that does not resolve.

REFS (``laplace.manuscript.source_anchor``). A node's ``ref`` is either the legacy offset form
``<path>:<line>[-<line>]`` or a CONTENT ANCHOR ``<path>:@<digest>[+<n>]`` keyed on the
anchored text rather than on its offset. Prefer the anchor: an offset ref drifts whenever
anything is inserted above it, which turns every upstream edit into a false byte-stability
failure downstream; an anchor moves with its prose and changes only when the prose does.

DETERMINISM: records are emitted in declaration order with stable ``OV-NNNN`` ids and the
declared ts, so two runs produce a byte-identical ledger. Records the builder does not own
(the dashboard's birth records, a human's rule deposited through /corpus/friction) are
preserved ahead of the rebuilt block.

    python3 scripts/build_overlay_conceptric.py --project superarc      # (re)emit
    python3 scripts/build_overlay_conceptric.py --project superarc --check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DECL_FILE = "conceptric_overlay.json"
BUILD_TAG = "build:overlay-conceptric"     # our records' `by`; every other record is kept
ROOT = "paper://"                          # atomise_paper's apex (the base leaf)


class DeclarationError(Exception):
    """A declaration that would emit a broken conceptric — named, never poured."""


# ---------------------------------------------------------------------------
# validation — every clause fails loudly, none degrades to a quiet empty graph
# ---------------------------------------------------------------------------

def validate(decl: dict, repo: Path) -> None:
    from laplace.research.corpus_ingest import LOGICAL_KINDS
    from laplace.pipeline.schema import PAIR_AXES, TARGET_AXES

    if not isinstance(decl.get("ts"), str) or not decl["ts"].strip():
        raise DeclarationError("declaration needs a fixed `ts` (the byte-stable record stamp)")

    goal = decl.get("goal") or {}
    nodes = decl.get("nodes") or []
    if not goal.get("id"):
        raise DeclarationError("declaration needs a `goal` with an id")
    if not nodes:
        raise DeclarationError("declaration has no nodes")

    kind_map = decl.get("kind_map") or {}
    ids: list[str] = [goal["id"]] + [n.get("id", "") for n in nodes]
    seen: set[str] = set()
    for nid in ids:
        if not nid:
            raise DeclarationError("a node carries no id")
        if nid in seen:
            raise DeclarationError(f"duplicate node id {nid!r}")
        seen.add(nid)

    for n in [goal] + list(nodes):
        native = n.get("kind")
        if native not in kind_map:
            raise DeclarationError(f"node {n['id']!r}: native kind {native!r} is not in kind_map")
        if kind_map[native] not in LOGICAL_KINDS:
            raise DeclarationError(
                f"kind_map[{native!r}] = {kind_map[native]!r} is outside LOGICAL_KINDS "
                f"{LOGICAL_KINDS} — the taxonomy is never widened for one project")
        if not (n.get("essence") or "").strip():
            raise DeclarationError(f"node {n['id']!r} carries no essence")
        _check_ref(n.get("ref", ""), n["id"], repo)
        _check_projection(n.get("projection"), n["id"])

    # containment: every parent resolves, and no chain loops back on itself
    parents = {n["id"]: n.get("parent") or "" for n in nodes}
    parents[goal["id"]] = ROOT
    for nid, par in parents.items():
        if not par:
            raise DeclarationError(f"node {nid!r} carries no parent")
        if par != ROOT and par not in seen:
            raise DeclarationError(f"node {nid!r} parents onto unknown node {par!r}")
    for nid in parents:
        walked: set[str] = set()
        cur = nid
        while cur != ROOT:
            if cur in walked:
                raise DeclarationError(f"parent cycle through {nid!r}")
            walked.add(cur)
            cur = parents[cur]

    for e in decl.get("edges") or []:
        for end in ("node", "target"):
            if e.get(end) not in seen:
                raise DeclarationError(f"edge {end} {e.get(end)!r} is not a declared node")
        axis = (e.get("axis") or "").strip()
        if axis and (axis not in TARGET_AXES or axis in PAIR_AXES):
            raise DeclarationError(f"edge axis {axis!r} is not a target-bearing axis {TARGET_AXES}")
        if not (e.get("rel") or "").strip():
            raise DeclarationError(f"edge {e.get('node')!r} -> {e.get('target')!r} carries no rel")

    beats = (decl.get("arc") or {}).get("beats") or []
    if not beats:
        raise DeclarationError("arc declares no beats — a corpus with an empty spine renders "
                               "'no spine on this corpus yet' and loses its focus seed")
    beat_ids: set[str] = set()
    for b in beats:
        bid = b.get("node")
        if bid not in seen:
            raise DeclarationError(f"arc beat {bid!r} names a node the declaration does not build")
        if bid in beat_ids:
            raise DeclarationError(f"arc beat {bid!r} declared twice")
        beat_ids.add(bid)


def _check_projection(proj: Any, nid: str) -> None:
    """The optional extra emit-time slots: a FLAT dict of scalars, so a declaration can
    never smuggle a nested structure into the node payload ``/corpus/node`` serves."""
    if proj is None:
        return
    if not isinstance(proj, dict) or not proj:
        raise DeclarationError(f"node {nid!r}: `projection` must be a non-empty object")
    for k, v in proj.items():
        if not isinstance(k, str) or not k.strip():
            raise DeclarationError(f"node {nid!r}: a projection key is not a name: {k!r}")
        if not isinstance(v, (str, int, float, bool)):
            raise DeclarationError(
                f"node {nid!r}: projection[{k!r}] is {type(v).__name__}, not a scalar")


def _check_ref(ref: str, nid: str, repo: Path) -> None:
    """The refs-only house law, enforced: every node names a source that exists, at a place
    in it that exists. A ref into a moved file is a dead ref, so it fails here, not in a reader.

    TWO LOCATOR GRAMMARS, one door (``laplace.manuscript.source_anchor``). The legacy ``<path>:<line>``
    offset promises only that the file is that long. A ``<path>:@<digest>[+<n>]`` CONTENT
    ANCHOR promises more and is checked harder: the anchored text is searched for here, so a
    ref whose prose was rewritten fails even though the file still has the lines — and a ref
    whose prose merely moved down the file passes without the declaration's bytes changing."""
    from laplace.manuscript.source_anchor import AnchorError, resolve
    try:
        resolve(ref or "", repo)
    except AnchorError as e:
        raise DeclarationError(f"node {nid!r}: {e}") from None


# ---------------------------------------------------------------------------
# emission — stable ids, declaration order, the same record shape rewire_add mints
# ---------------------------------------------------------------------------

class Emitter:
    """Mints rewire records with stable ``OV-NNNN`` ids in call order."""

    def __init__(self, ts: str) -> None:
        self.records: list[dict] = []
        self._ts = ts
        self._seq = 0

    def _rec(self, kind: str, node: str, **extra: Any) -> dict:
        self._seq += 1
        rec = {"id": f"OV-{self._seq:04d}", "ts": self._ts, "kind": kind, "node": node,
               "target": extra.pop("target", None), "value": extra.pop("value", None),
               "by": BUILD_TAG, "status": "open"}
        rec.update(extra)
        self.records.append(rec)
        return rec

    def node(self, decl_node: dict, logical_kind: str, parent: str) -> None:
        essence = f"{decl_node['essence']} · src:{decl_node['ref']}"
        rec = {"parent": parent, "node_kind": logical_kind, "essence": essence,
               "ref": decl_node["ref"]}
        sup = (decl_node.get("supersedes") or "").strip()
        if sup:
            rec["supersedes"] = sup
        self._rec("add-node", decl_node["id"], **rec)
        # the NATIVE kind is carried, not lost: the projection slot is what /corpus/node
        # serves and what /corpus/spine reads a beat's one-line handle from. A declaration
        # may add further emit-time slots (latex_label, an authored epistemic_status);
        # they ride the SAME record, and never overwrite the two the builder owns.
        value = {"native_kind": decl_node["kind"],
                 "term": decl_node.get("term") or decl_node["id"]}
        for k, v in (decl_node.get("projection") or {}).items():
            if k not in value:
                value[k] = v
        self._rec("set-projection", decl_node["id"], value=value)

    def edge(self, e: dict) -> None:
        extra = {"target": e["target"], "value": e["rel"]}
        if (e.get("axis") or "").strip():
            extra["axis"] = e["axis"].strip()
        self._rec("add-edge", e["node"], **extra)

    def beat(self, node: str, ord_: int, narrative: str) -> None:
        self._rec("set-spine", node, ord=ord_, narrative=narrative)


def build_records(decl: dict) -> tuple[list[dict], dict[str, Any]]:
    """The declaration -> the record block + a census. Pure; validation ran first."""
    kind_map = decl["kind_map"]
    em = Emitter(decl["ts"])
    goal = decl["goal"]
    em.node(goal, kind_map[goal["kind"]], ROOT)
    for n in decl["nodes"]:
        em.node(n, kind_map[n["kind"]], n["parent"])
    for e in decl.get("edges") or []:
        em.edge(e)
    beats = decl["arc"]["beats"]
    for i, b in enumerate(beats):
        em.beat(b["node"], i, b.get("narrative") or "")

    natives: dict[str, int] = {}
    for n in [goal] + list(decl["nodes"]):
        natives[n["kind"]] = natives.get(n["kind"], 0) + 1
    census = {
        "n_nodes": sum(1 for r in em.records if r["kind"] == "add-node"),
        "n_edges": sum(1 for r in em.records if r["kind"] == "add-edge"),
        "spine_beats": len(beats),
        "arc_source": "declared",
        "arc_label": decl["arc"].get("label", ""),
        "native_kinds": dict(sorted(natives.items())),
        "logical_kinds": dict(sorted(
            {k: sum(1 for n in [goal] + list(decl["nodes"]) if kind_map[n["kind"]] == k)
             for k in {kind_map[n["kind"]] for n in [goal] + list(decl["nodes"])}}.items())),
        "edge_rels": sorted({r["value"] for r in em.records if r["kind"] == "add-edge"}),
    }
    return em.records, census


# ---------------------------------------------------------------------------
# ledger IO — foreign records preserved, ours rewritten, byte-stable
# ---------------------------------------------------------------------------

def _serialise(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def project_paths(repo: Path, name: str) -> tuple[Path, Path]:
    """(declaration, ledger) for a REGISTERED project — the registry is the one door, so
    the builder never guesses a layout the registry would resolve differently."""
    from laplace.pipeline import registry
    proj = registry.resolve(name)
    if proj is None:
        raise DeclarationError(f"{name!r} is not a registered project (registry.resolve)")
    return repo / proj.project_dir / DECL_FILE, repo / proj.ledger


def split_foreign(text: str, build_tag: str = BUILD_TAG) -> tuple[list[dict], list[dict]]:
    """Split a ledger's NON-build records by their side of the rebuilt block.

    The same cure as the design and atlas builders (WO-20260820-rewire-append-drifts-the-builder),
    and this is the builder it matters most for — it serves EVERY registered project, so every
    project's conceptric is exposed to the same disagreement: ``corpus_ingest.rewire_add`` appends
    at end-of-file (the one locked append), so a deposit through the sanctioned door lands AFTER
    our block, and re-emitting it before the block put the ledger into drift until the builder was
    re-run. Each foreign row is preserved on the side it was written on, which keeps ``--check``
    byte-exact and keeps a door deposit applying ON TOP of the built nodes (``apply_overlay`` drops
    an edit-essence / set-status whose node is not in ``leaves`` yet). A ledger with no block of
    ours yet keeps the old behaviour: everything is 'before'."""
    before: list[dict] = []
    after: list[dict] = []
    seen_build = False
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("by") == build_tag:
            seen_build = True
            continue
        (after if seen_build else before).append(r)
    return before, after


def emit(repo: Path, name: str) -> tuple[Path, str, dict[str, Any]]:
    """The pure core the writer and --check share: (ledger path, full text, census)."""
    decl_path, ledger = project_paths(repo, name)
    if not decl_path.is_file():
        raise DeclarationError(f"no declaration at {decl_path.relative_to(repo).as_posix()}")
    decl = json.loads(decl_path.read_text(encoding="utf-8"))
    validate(decl, repo)
    records, census = build_records(decl)
    before, after = split_foreign(ledger.read_text(encoding="utf-8") if ledger.is_file() else "")
    census["n_foreign_preserved"] = len(before) + len(after)
    census["n_foreign_after_block"] = len(after)
    return ledger, _serialise(before + records + after), census


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", required=True, help="the registered project name")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--check", action="store_true",
                    help="verify the on-disk ledger already equals a fresh build (idempotent)")
    args = ap.parse_args()
    repo = Path(args.repo_root).resolve()
    sys.path.insert(0, str(repo / "src"))   # so `import laplace` resolves from repo

    try:
        ledger, text, census = emit(repo, args.project)
    except DeclarationError as e:
        print(f"DECLARATION: {e}", file=sys.stderr)
        return 2
    rel = ledger.relative_to(repo).as_posix()
    if args.check:
        current = ledger.read_text(encoding="utf-8") if ledger.is_file() else ""
        if current != text:
            print(f"DRIFT: {rel} != a fresh build (run without --check to re-emit)",
                  file=sys.stderr)
            return 1
        print(f"idempotent: {rel} matches a fresh build")
        print(json.dumps(census, indent=2))
        return 0

    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(text, encoding="utf-8")
    print(f"wrote {rel}")
    print(json.dumps(census, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
