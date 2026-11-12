"""The brain scanner - a persistent, interactive conceptric viewer (N22).

The human-facing conjugate of ``telemetry.trace``: the engine banks the firing
path; this *renders* it, live, so the author can SEE a prompt fire through the
conceptric and the grades resurface - and have the realisation. The author's
realisations come from seeing the path.

One surface, both of us drive it:

* the **author** opens ``http://127.0.0.1:8770`` and types a prompt; it fires
  through the conceptric and the matched nodes flare;
* **Eigen** fires the same surface from the shell::

      curl -s -XPOST localhost:8770/fire -d '{"goal":"earned simplicity","by":"eigen"}'

  and the author's open page lights up live (it polls ``/firings``). When Eigen
  fires, the author sees what Eigen reached; when the author fires, Eigen can
  read it back (``GET /firings``). The channel made visible, both ways.

Three views of the one conceptric, switchable live:

* **canon** - the typed canon graph (``graph.render``). What ``Canon.route``
  fires into: wiki pages, skills, domains, agents, wired by ``[[name]]`` /
  ``canon://`` links.
* **self** - the 569-node directory shard (``self_shard``). The engine's own
  tree as a conceptric: every tracked file a node, wired by imports / links /
  inputs. What ``reconstruct_by_name`` resurfaces. The *self* the scanner can
  point at itself.
* **corpus** - the literature store (``graph.from_corpus``).

A single ``/fire`` runs BOTH ``Canon.route`` (the canon/corpus/soul/
self-knowledge/project reach) AND ``self_shard.reconstruct_by_name`` (the
directory reach), maps every hit to a node id, and returns the full reach. The
frontend lights up whatever is present in the current view and lists the rest in
the feed - so the picture is explicit about what it cannot show as well as what it
can.

The soul covenant holds: a ``soul/`` node can *light* (the reach is real and
worth seeing) but never reveals content - its handle stays sealed at every grade,
exactly as ``route`` returns soul as refs-only.

Pure stdlib ``http.server``. It NEVER spawns git - it reads the canon graph, the
shard, and the corpus, and banks each fire to telemetry (``reconstruction``,
tagged ``caller="scanner"``) so the instrument that shows the trace also feeds
it. A telemetry hiccup never breaks a fire.
"""

from __future__ import annotations
from laplace.engine.self_shard import self_graph as _self_graph
from laplace.engine.process_health import probe

import argparse
import json
import os
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

#: the CORS cure (IFACE-DEFECT-20260824-cors-wildcard): the old blanket
#: ``Access-Control-Allow-Origin: *`` let ANY page in a local browser read engine
#: responses cross-origin (DNS-rebinding/CSRF class, live once POST routes existed).
#: Now the origin is echoed ONLY for loopback origins; foreign origins get no CORS
#: header at all. curl and same-origin pages never needed the header.
_LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")

_APP = Path(__file__).resolve().parent / "scanner_app.html"
_FIRINGS_FILE = "scanner_firings.jsonl"
_FIRINGS_KEEP = 200  # bounded in-memory ring; the page replays the recent tail on connect


from laplace.core.checkout import repo_root as _repo_root   # the serving checkout (laplace.core.checkout); same object, old name


def _corpus_feedback_ledger(rr: Path, corpus: str) -> Path | None:
    """The corpus' ONE feedback ledger: ``<plan target_dir>/feedback/feedback.jsonl``
    - the same file the projection viewer's review mode reads and writes, resolved
    through the plan (registry-fenced), so node comments and review comments share
    a single store and the comment-driven revision sees them together."""
    from laplace.pipeline import registry
    pp = registry.plan_path_for(corpus)
    if pp is None:
        return None
    try:
        import json as _json
        target = ((_json.loads(pp.read_text(encoding="utf-8")).get("meta") or {})
                  .get("target_dir") or "").rstrip("/")
    except (OSError, ValueError):
        return None
    if not target:
        return None
    led = (rr / target / "feedback" / "feedback.jsonl").resolve()
    try:
        led.relative_to(rr.resolve())     # containment: checked, not assumed
    except ValueError:
        return None
    led.parent.mkdir(parents=True, exist_ok=True)
    return led


# ---------------------------------------------------------------------------
# Graph sources - canon / self-shard / corpus, all in the one node/edge shape
# ---------------------------------------------------------------------------

_GRAPH_CACHE: dict[str, dict] = {}
_GRAPH_LOCK = threading.Lock()


def _canon_graph() -> dict:
    """The typed canon graph as {nodes, edges, health} - what ``route`` fires into."""
    from laplace.pipeline import graph as _graph

    res = _graph.render("json")
    art = res.get("artifact", {})
    return {"nodes": art.get("nodes", []), "edges": art.get("edges", []),
            "health": art.get("health", {}), "source": "canon"}


def _corpus_graph() -> dict:
    """The literature store as a conceptric, when a corpus.bib is present."""
    from laplace.pipeline import graph as _graph

    bib = _repo_root() / "corpus" / "corpus.bib"
    if not bib.exists():
        return {"nodes": [], "edges": [], "health": {}, "source": "corpus",
                "note": "no corpus/corpus.bib"}
    res = _graph.render("json", corpus=str(bib))
    art = res.get("artifact", {})
    return {"nodes": art.get("nodes", []), "edges": art.get("edges", []),
            "health": art.get("health", {}), "source": "corpus"}






def _soul_corpus_graph() -> dict:
    """The soul-pour relational world as a seal-safe graded graph - the nodes the POUR built: people,
    circles, their grade-1 slices, the cross-world fusions, all wired by grade-down / membership /
    fusion edges. Names (identity, preserved per the covenant) + STRUCTURE are shown; CONTENT (voice,
    history) is NEVER carried - only counts. Reads the gitignored ``archive/soul_dump`` folded dirs at
    runtime; an absent dir drops out cleanly. The author asked to SEE the world he built - this lens."""
    root = _repo_root()
    shard = root / "archive" / "soul_dump" / "_shard"
    folded = shard / "scaled_tranche2_folded"
    xworld = shard / "scaled_tranche1_folded" / "_xworld"
    nodes: list[dict] = []
    edges: list[dict] = []
    have: set[str] = set()

    def _add(nid: str, label: str, kind: str, grade: int, meta=None) -> None:
        if nid in have:
            return
        have.add(nid)
        nodes.append({
            "id": nid, "kind": kind, "label": label, "group": "soul-corpus",
            "status": None, "weight": round(min(1.0, 0.4 + grade * 0.18), 3),
            "source": "world", "store": "world", "link": "linked", "grade": grade,
            "sealed": True,  # the covenant doubled: label + structure shown, content never carried
            "meta": dict(meta or {}),  # counts only - never history/voice text
        })

    def _edge(s: str, d: str, rel: str) -> None:
        edges.append({"src": s, "dst": d, "rel": rel, "evidence": "", "source": "world", "count": 1})

    if folded.is_dir():
        for fp in sorted(folded.glob("*.json")):
            try:
                d = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - a malformed node drops out, never breaks the lens
                continue
            name = d.get("canonical_name") or d.get("name")
            if not name:
                continue
            is_circle = bool(d.get("members")) or d.get("kind") == "circle"
            nid = f"world:{fp.stem}"
            _add(nid, name, "circle" if is_circle else "person", 2,
                 {"history": len(d.get("history", [])), "voice": len(d.get("voice", [])),
                  "relations": len(d.get("relations", []))})
            for sh in d.get("slice_shards", []):
                sid = f"world:slice:{Path(sh).stem}"
                _add(sid, Path(sh).stem.replace("_", " "), "slice", 1, {})
                _edge(nid, sid, "grade-down")
            for m in d.get("members", []):
                mn = (m.get("name") if isinstance(m, dict) else m) or ""
                if mn:
                    mid = f"world:member:{mn}"
                    _add(mid, mn, "person", 2, {})
                    _edge(nid, mid, "member")

    if xworld.is_dir():
        for fp in sorted(xworld.glob("*.json")):
            try:
                d = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            name = d.get("canonical_name")
            if not name:
                continue
            nid = f"world:xworld:{fp.stem}"
            _add(nid, name, "xworld", 3,
                 {"corpora": len(d.get("corpora_present", [])), "research": len(d.get("research", [])),
                  "history": len(d.get("history", []))})
            apex = f"world:{fp.stem.replace('-', '_')}"
            if apex in have:
                _edge(nid, apex, "fuses")

    return {"nodes": nodes, "edges": edges, "source": "world",
            "health": {"node_count": len(nodes), "edge_count": len(edges), "sealed": len(nodes)}}


def _unified_graph() -> dict:
    """The one conceptric: canon + self + corpus merged, each node tagged with its
    store. canon / self / corpus become the three top super-nodes you descend from -
    'synthesise, do not partition' (the canon's own rule, against the AutoSci split).

    Node id namespaces are already disjoint (wiki:/skill:/domain:/agent: · file: ·
    ref:/cluster:/theme:/project:), so the merge is collision-free; ``missing:``
    placeholders are dropped (they would collide across stores and add no signal).
    The payoff is the firing: one ``/fire`` reaches canon AND self AND corpus, so it
    lights across all three at once - what ``Canon.route`` actually does.
    """
    parts = (("canon", _canon_graph), ("self", _self_graph), ("corpus", _corpus_graph),
             ("world", _soul_corpus_graph))
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()
    for store, builder in parts:
        try:
            g = builder()
        except Exception:  # noqa: BLE001 - a missing store drops out, never breaks the union
            continue
        for n in g.get("nodes", []):
            if n.get("kind") == "missing" or n["id"] in seen:
                continue
            seen.add(n["id"])
            nn = dict(n)
            nn["store"] = store
            nodes.append(nn)
        edges.extend(g.get("edges", []))
    ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["src"] in ids and e["dst"] in ids]
    return {"nodes": nodes, "edges": edges, "source": "all",
            "health": {"node_count": len(nodes), "edge_count": len(edges),
                       "stores": [p[0] for p in parts],
                       "sealed": sum(1 for n in nodes
                                     if n.get("group") == "soul" or n.get("kind") == "soul")}}


_BUILDERS = {"all": _unified_graph, "canon": _canon_graph, "self": _self_graph,
             "corpus": _corpus_graph, "world": _soul_corpus_graph}


def graph_for(source: str, refresh: bool = False) -> dict:
    """Build (and cache) the node/edge graph for a source. Cheap to re-serve."""
    source = source if source in _BUILDERS else "all"
    with _GRAPH_LOCK:
        if refresh or source not in _GRAPH_CACHE:
            try:
                g = _BUILDERS[source]()
            except Exception as exc:  # noqa: BLE001 - a view must degrade, never crash the server
                return {"nodes": [], "edges": [], "source": source, "error": str(exc)}
            for n in g.get("nodes", []):  # every node carries its store (the top grain)
                n.setdefault("store", source if source in ("canon", "self", "corpus") else "canon")
            _GRAPH_CACHE[source] = g
        return _GRAPH_CACHE[source]


# ---------------------------------------------------------------------------
# Descend - reconstruct ANY node grade by grade through the ONE graded reader
# ---------------------------------------------------------------------------

def _node_to_relpath(node_id: str) -> str | None:
    """Resolve a node id to its repo-relative source path.

    The self-similar move: a canon wiki page, a skill, an agent, and a directory
    file all reconstruct through the SAME graded reader (``self_shard``), by their
    repo path - there is one reconstruction, not one per source. A node with no
    backing file (a corpus record, a domain) returns None (grade-0 handle only).
    """
    if node_id.startswith("file:"):
        return node_id[5:]
    root = _repo_root()
    try:
        from laplace.pipeline.canon import get_canon
        c = get_canon()
        p = None
        if node_id.startswith("wiki:"):
            n = c.wiki.get(node_id[5:])
            p = getattr(n, "path", None)
        elif node_id.startswith("skill:"):
            sk = c.skills.get(node_id[6:])
            p = getattr(sk, "skill_md", None)
        elif node_id.startswith("agent:"):
            p = c.root / "agents" / f"{node_id[6:]}.yaml"
        if p is not None:
            return str(Path(p).relative_to(root)).replace("\\", "/")
    except Exception:  # noqa: BLE001 - an unresolvable node degrades to handle-only
        return None
    return None


def reconstruct_node(node_id: str, grade: int = 1) -> dict:
    """Reconstruct one node at a grade by RE-READING its source - the descend.

    grade 0 = the handle (essence + keywords), 1 = the spine (structure), 2 = the
    content (re-read, capped). The store holds the handle; deeper grades are
    reconstructed, never a stored copy - the conceptric's law, made interactive.
    The soul covenant holds at every grade (``self_shard`` seals it).
    """
    grade = max(0, min(2, int(grade)))
    rel = _node_to_relpath(node_id)
    if not rel:
        return {"id": node_id, "grade": grade, "reconstructible": False,
                "note": "no source file for this node kind - grade-0 handle only"}
    try:
        from laplace.engine import self_shard
        res = self_shard.reconstruct_by_name(_repo_root(), rel, grade=grade, k=1)
    except Exception as exc:  # noqa: BLE001
        return {"id": node_id, "grade": grade, "reconstructible": False, "note": str(exc)}
    # Require the EXACT path back. Never fall back to the closest token match - a
    # reconstruction of a *different* file is the confident-wrong failure this whole
    # engine exists to kill. An untracked/moved source returns honest absence instead.
    matches = res.get("matches", [])
    m = next((x for x in matches if x.get("name") == rel), None)
    if not m:
        return {"id": node_id, "grade": grade, "reconstructible": False,
                "note": "source not in the tracked conceptric (untracked or moved) - handle only"}
    return {
        "id": node_id, "grade": grade, "reconstructible": True, "name": m.get("name"),
        "essence": m.get("essence"), "sealed": bool(m.get("sealed")),
        "spine": m.get("spine"), "content": m.get("content"),
        "content_truncated": bool(m.get("content_truncated")), "pointer": m.get("pointer"),
        "descend": res.get("descend"),  # the embedded call that fires the next grade
    }


# ---------------------------------------------------------------------------
# The graded tree (the keeper) - grades / hierarchy / the ring's substrate
# ---------------------------------------------------------------------------

_TREE_CACHE: dict[str, object] = {}


def _graded_tree(refresh: bool = False) -> dict:
    """The keeper's graded conceptric (``id -> graded node``): the directory's grade-0 leaves lifted
    into a grade 0..k tree. Loaded from the gitignored cache when present, else built from the shard.
    Cached in-process (the Becoming lens busts it when growth lands). Soul stays sealed downstream."""
    with _GRAPH_LOCK:
        if refresh or "nodes" not in _TREE_CACHE:
            try:
                from laplace.engine import keeper
                root = _repo_root()
                nodes = keeper.load_tree_local(root) or keeper.build_self(root)
            except Exception as exc:  # noqa: BLE001 - a missing tree degrades to empty, never crashes
                return {"nodes": {}, "error": str(exc)}
            _TREE_CACHE["nodes"] = nodes
        return {"nodes": _TREE_CACHE.get("nodes", {})}


def _seal_node(n: dict) -> dict:
    """A graded node projected for the wire. The covenant doubled at the boundary: a sealed node's
    essence + keywords are blanked, so a soul handle carries grade + membership COUNT only, never
    content (the keeper node has no content to begin with - this guards the essence too)."""
    sealed = bool(n.get("sealed"))
    return {"id": n["id"], "grade": n["grade"], "kind": n.get("kind", ""),
            "leaf": bool(n.get("leaf")), "sealed": sealed,
            "members": len(n.get("members", [])), "parent": n.get("parent"),
            "essence": "" if sealed else (n.get("essence") or ""),
            "keywords": [] if sealed else list(n.get("keywords") or [])[:8]}


def grades_payload(refresh: bool = False) -> dict:
    """The graded hierarchy for the Hierarchy / Rings lenses: every node as a seal-safe handle
    (id, grade, member count, parent, essence) + ``grade_stats`` (by_grade, max_grade, widths)."""
    t = _graded_tree(refresh)
    nodes = t.get("nodes", {})
    if not nodes:
        return {"nodes": [], "stats": {}, "error": t.get("error", "empty graded tree")}
    try:
        from laplace.engine import keeper
        stats = keeper.grade_stats(nodes)
    except Exception:  # noqa: BLE001
        stats = {}
    return {"nodes": [_seal_node(n) for n in nodes.values()], "stats": stats}


def _pulse() -> dict:
    """A cheap growth fingerprint: the count of tracked files + the latest mtime under the repo
    (heavy dirs skipped). The Becoming lens polls this; when it changes, the brain GREW - so the
    lens busts the graph/grades caches and animates the new nodes being born. No file is read,
    no graph is built - just stat() over the tree, so it is light enough to poll every few seconds."""
    root = _repo_root()
    skip = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
    n = 0
    latest = 0.0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for f in filenames:
            n += 1
            try:
                m = os.stat(os.path.join(dirpath, f)).st_mtime
                if m > latest:
                    latest = m
            except OSError:
                pass
    return {"files": n, "latest": round(latest, 3)}


def ring_fire(goal: str, *, fanout: int = 8, pull_fraction: float = 0.0) -> dict:
    """Fire a goal through the keeper RING and return BOTH passes for the observer:

    * ``down`` - the descent path, each ``{id, grade, sealed}`` in visit order (the message piping
      out->in through the grades to the substrate);
    * ``returns`` - the enriched return at every visited node, seal-safe ``{node, grade, depth,
      gathered, pulled, negatives, leaves, result}`` (the ring closing in->out, the concepts
      surfacing at their grade - what the author asked to SEE).

    Run with the seal-safe ``MechanicalKeeper`` (no LLM): real structural flow, never invention. A
    sealed leaf's result is the refs-only placeholder ``base()`` returns; its result text is blanked
    here too (the covenant, doubled). ``pull_fraction`` is the enrichment knob (0 = pure recall)."""
    t = _graded_tree()
    nodes = t.get("nodes", {})
    if not nodes:
        return {"goal": goal, "via": "keeper-ring", "error": t.get("error", "empty graded tree"),
                "down": [], "returns": []}
    try:
        from laplace.engine import keeper_ring
        tr: dict = {}
        keeper_ring.reconstruct(nodes, "", goal, repo_root=_repo_root(),
                                fanout=fanout, pull_fraction=pull_fraction, trace=tr)
    except Exception as exc:  # noqa: BLE001 - a ring miss degrades to honest absence, never a crash
        return {"goal": goal, "via": "keeper-ring", "error": str(exc), "down": [], "returns": []}

    def _sealed(nid: str) -> bool:
        return bool((nodes.get(nid) or {}).get("sealed"))

    down = [{"id": nid, "grade": g, "sealed": _sealed(nid)} for nid, g in tr.get("activated", [])]
    returns = []
    for r in tr.get("returns", []):
        s = _sealed(r["node"])
        returns.append({
            "node": r["node"], "grade": r["grade"], "depth": r["depth"], "leaf": bool(r.get("leaf")),
            "sealed": s, "enriched": bool(r.get("enriched")),
            "gathered": list(r.get("gathered", [])),
            "pulled": [p.get("node") for p in r.get("pulled", [])],
            "negatives": [n.get("node") for n in r.get("negatives", [])],
            "leaves": list(r.get("leaves", []))[:12],
            "result": "" if s else (r.get("result", "") or "")[:240],
        })
    top = returns[-1] if returns else {}                       # post-order: the root (depth 0) is last
    out = {"goal": goal, "via": "keeper-ring", "down": down, "returns": returns,
           "max_grade": max((d["grade"] for d in down), default=0),
           "visited": tr.get("visited", len(down)), "total": len(nodes),
           "top": {"node": top.get("node", ""), "grade": top.get("grade", 0),
                   "result": top.get("result", ""), "gathered": top.get("gathered", []),
                   "pulled": top.get("pulled", []), "leaves": top.get("leaves", [])}}
    try:
        from laplace.engine import telemetry
        telemetry.reconstruction(target=goal[:120], caller="scanner-ring",
                                 nodes=[d["id"] for d in down][:40],
                                 reason=f"ring fire · {len(down)} visited / {len(nodes)} · g{out['max_grade']}")
    except Exception:  # noqa: BLE001 - telemetry never on the hot path
        pass
    return out


# ---------------------------------------------------------------------------
# The fire - one routing into the whole conceptric, mapped to node ids
# ---------------------------------------------------------------------------

def _fired_from_route(route: dict) -> list[dict]:
    """Map a ``Canon.route`` result to the node ids it lit, with channel + rank."""
    fired: list[dict] = []
    canon = route.get("canon", {})
    for rank, ref in enumerate(canon.get("wiki", []), start=1):
        rid = ref.replace("canon://", "")
        fired.append({"id": f"wiki:{rid}", "channel": "canon.wiki", "rank": rank})
    for rank, name in enumerate(canon.get("skills", []), start=1):
        fired.append({"id": f"skill:{name}", "channel": "canon.skill", "rank": rank})
    for rank, rec in enumerate(route.get("corpus", []), start=1):
        fired.append({"id": f"ref:{rec.get('key', '')}", "channel": "corpus",
                      "rank": rank, "score": rec.get("score")})
    # self-knowledge + project resolve to file: nodes (present in the self view).
    seen_files: set[str] = set()
    for rank, rec in enumerate(route.get("self_knowledge", []), start=1):
        f = rec.get("file", "")
        if f and f not in seen_files:
            seen_files.add(f)
            fired.append({"id": f"file:{f}", "channel": "self_knowledge", "rank": rank,
                          "score": rec.get("score")})
    for rank, rec in enumerate(route.get("project", []), start=1):
        f = rec.get("file", "")
        if f and f not in seen_files:
            seen_files.add(f)
            fired.append({"id": f"file:{f}", "channel": "project", "rank": rank,
                          "score": rec.get("score")})
    # soul lights (the reach is real) but stays sealed - a node id, never content.
    for rank, rec in enumerate(route.get("soul", []), start=1):
        ref = rec.get("ref", "")
        if ref:
            fired.append({"id": f"file:{ref}", "channel": "soul", "rank": rank,
                          "score": rec.get("score"), "sealed": True})
    return fired


_FIRE_KINDS = ("route", "reconstruct_self", "orient", "descend")


def fire(goal: str, by: str = "author", kind: str = "route",
         grade: int | None = None, nodes: list[str] | None = None) -> dict:
    """One firing recorded for the viewer - two shapes, one record.

    * A ROUTE fire (the default) runs ``Canon.route`` + ``self_shard.reconstruct_by_name`` on the
      goal and lights what it reached - what the author types, or what Eigen reaches for a task.
    * An EIGEN reconstruction fire carries ``kind`` (reconstruct_self / orient / descend) and a
      ``grade``, so the author SEES Eigen fire THROUGH the grades, not only the author's goal-fires
      (N24, "I want to see grades of eigen firing"). ``orient`` passes no ``nodes`` and lights its
      goal's reach; ``reconstruct_self`` passes the explicit self-substrate ``nodes`` it
      reconstructed at that grade. A sequence of these (g0 then g1) IS the path through the grades.

    Banks to telemetry (``caller="scanner"``). Never raises on a sub-store miss.
    """
    goal = (goal or "").strip()
    root = _repo_root()
    kind = kind if kind in _FIRE_KINDS else "route"
    grade = grade if isinstance(grade, int) else None

    if nodes:
        # Explicit-node fire (a self-reconstruction): light exactly what was reconstructed, in order.
        fired = [{"id": nid, "channel": f"eigen.{kind}", "rank": i + 1}
                 for i, nid in enumerate(dict.fromkeys(n for n in nodes if n))]
        channels: dict = {"reconstruct": kind, "grade": grade,
                          "nodes": [f["id"] for f in fired][:8]}
    else:
        route: dict = {}
        shard: dict = {}
        try:
            from laplace.pipeline.canon import get_canon
            route = get_canon().route(goal)
        except Exception as exc:  # noqa: BLE001
            route = {"error": str(exc)}
        try:
            from laplace.engine import self_shard
            shard = self_shard.reconstruct_by_name(root, goal, grade=0, k=6)
        except Exception as exc:  # noqa: BLE001
            shard = {"error": str(exc)}

        fired = _fired_from_route(route)
        shard_names = []
        for rank, m in enumerate(shard.get("matches", []), start=1):
            nm = m.get("name", "")
            if nm:
                shard_names.append(nm)
                fired.append({"id": f"file:{nm}", "channel": "self.shard", "rank": rank,
                              "sealed": bool(m.get("sealed"))})

        # Collapse duplicate node ids (a file can be hit by both self_knowledge and the
        # shard) to the strongest (lowest) rank, so the flare intensity is single-valued.
        best: dict[str, dict] = {}
        for f in fired:
            cur = best.get(f["id"])
            if cur is None or f["rank"] < cur["rank"]:
                best[f["id"]] = f
        fired = sorted(best.values(), key=lambda f: f["rank"])
        channels = {
            "domain": route.get("canon", {}).get("domain"),
            "canon_wiki": route.get("canon", {}).get("wiki", [])[:6],
            "canon_skills": route.get("canon", {}).get("skills", [])[:6],
            "corpus": route.get("corpus", [])[:6],
            "soul": route.get("soul", [])[:6],          # refs only, never content
            "self_knowledge": route.get("self_knowledge", [])[:6],
            "project": route.get("project", [])[:6],
            "shard": shard_names[:6],
        }

    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "goal": goal,
        "by": by if by in ("author", "eigen") else "author",
        "kind": kind,
        "grade": grade,
        "fired": fired,
        "channels": channels,
    }
    _bank_firing(rec, fired)
    return rec


def _bank_firing(rec: dict, fired: list[dict]) -> None:
    """Bank the fire to telemetry - the scanner feeding the trace it renders - AND to the
    firings feed the spine's ``learned_top`` reads, via spine's ONE writer.

    This runs for every call to ``fire()`` regardless of caller (the HTTP ``/fire`` handler
    or any future in-process caller), so persisting the learnable feed is a property of firing
    itself, never conditional on the ping that reached this process also having crossed a live
    HTTP hop (the diagnosis: most real fires - ``_ping_scanner`` in tool.py - are fire-and-forget
    pings to a scanner dev-server that is rarely running, so they were silently dropped before
    ever reaching this function; this only fixes fires that DO land here - see
    ``scripts/backfill_firings.py`` for recovering the ones that didn't, from telemetry)."""
    try:
        from laplace.engine import telemetry
        grade = rec.get("grade")
        reason = f"scanner fire by {rec['by']} ({rec.get('kind', 'route')}"
        reason += f" g{grade})" if isinstance(grade, int) else ")"
        telemetry.reconstruction(
            target=rec["goal"][:120], caller="scanner",
            nodes=[f["id"] for f in fired][:40],
            reason=reason,
        )
    except Exception:  # noqa: BLE001 - telemetry is never on the hot path of a fire
        pass
    try:
        from laplace.engine import spine
        spine.record_firing(_repo_root(), rec["goal"], fired, ts=rec.get("ts"))
        rec["_persisted"] = True  # tell the ring's append() the disk line is already down
    except Exception:  # noqa: BLE001 - the learned feed is a guide; a fire never fails on it
        pass


def client_fire(goal: str, *, by: str = "eigen", kind: str = "route",
                grade: int | None = None, nodes: list[str] | None = None,
                host: str = "127.0.0.1", port: int = 8770, timeout: float = 2.0) -> dict | None:
    """POST a fire to a RUNNING scanner so a long task - the soul pour - lights the brain live.

    The client conjugate of the server's ``/fire`` (and of the documented ``curl`` one-liner): a
    Python caller - the pour's materialise step, a sweep driver - fires ``by="eigen"`` as each shard
    distils and each node is born, and the author's open page animates it (it polls ``/firings``). So
    he WATCHES the real ingest, not a manual fire.

    **Seal-safe is the CALLER's contract.** Pass only seal-safe labels - a concept name, a node id, a
    paper title - never raw shard content, and for soul-class material only the ref/label, never the
    text. The seal lives in what you hand this, exactly as the orchestrator never holds the raw.

    NEVER raises, never blocks long: a fire is telemetry for the eye, never on the pour's hot path, so
    a scanner that is down / slow / absent returns ``None`` and the pour proceeds untouched.
    """
    import urllib.request
    goal = (goal or "").strip()
    if not goal:
        return None
    payload: dict = {"goal": goal, "by": by, "kind": kind}
    if isinstance(grade, int):
        payload["grade"] = grade
    if nodes:
        payload["nodes"] = list(nodes)
    req = urllib.request.Request(
        f"http://{host}:{port}/fire", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"{}")
    except Exception:  # noqa: BLE001 - the eye is never on the hot path; a miss is silent
        return None


# ---------------------------------------------------------------------------
# The firing ring - persistent, both of us poll it
# ---------------------------------------------------------------------------

class _FiringLog:
    """A bounded, persistent ring of firings. Append on fire; the page polls the
    tail since a sequence number, so a fire from either of us reaches both."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[dict] = []
        self._seq = 0
        self._load_tail()

    def _path(self) -> Path:
        from laplace.engine import telemetry
        return telemetry.state_dir() / _FIRINGS_FILE

    def _load_tail(self) -> None:
        try:
            text = self._path().read_text(encoding="utf-8")
        except OSError:
            return
        rows = [ln for ln in text.splitlines() if ln.strip()][-_FIRINGS_KEEP:]
        for ln in rows:
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            self._seq += 1
            rec["seq"] = self._seq
            self._items.append(rec)

    def append(self, rec: dict) -> dict:
        """Ring bookkeeping + persistence, without duplicating the disk line.

        The ``fire()`` path already wrote the line through ``spine.record_firing``
        (the one writer, in ``_bank_firing``) and stamped ``rec["_persisted"]``, so
        for ``do_POST``'s ``_FIRINGS.append(fire(...))`` we only do the in-memory
        seq/ring work. A DIRECT append - an in-process caller (or a restart-replay
        test) that did not route through ``fire()`` - carries no such stamp, so we
        persist it here through the SAME one writer, exactly once. Either way the
        ring is both sequenced and persistent (the feed survives a restart)."""
        with self._lock:
            self._seq += 1
            rec["seq"] = self._seq
            self._items.append(rec)
            if len(self._items) > _FIRINGS_KEEP:
                self._items = self._items[-_FIRINGS_KEEP:]
        if not rec.pop("_persisted", False):
            try:
                from laplace.engine import spine
                spine.record_firing(
                    _repo_root(), rec.get("goal", ""), rec.get("fired", []), ts=rec.get("ts")
                )
            except Exception:  # noqa: BLE001 - a lossy substrate never breaks a fire
                pass
        return rec

    def since(self, seq: int) -> dict:
        with self._lock:
            return {"seq": self._seq, "firings": [r for r in self._items if r["seq"] > seq]}


_FIRINGS = _FiringLog()


# ---------------------------------------------------------------------------
# The navigator - the conceptric organ behind the graded-descent tool
# (his design 2026-06-10: directional coupling, two axes, dimensionalised pull,
#  thinking phases as parameter presets; the scanner DRIVES the real machinery)
# ---------------------------------------------------------------------------

# W0.3: _NAVIGATOR_APP / _EDITOR_APP / _CONCEPTRIC_APP (scanner_navigator.html,
# manuscript_editor.html, conceptric_editor.html) are retired — their routes now
# redirect (301) or return 410, and the templates are deleted.
# renamed from conceptric_editor_v2_mockup.html 2026-07-03, then conceptric_editor2.html
# -> conceptric.html in W3 (the rebuild on the shared model): the daily-driver conceptric
# surface, served at /conceptric (the route promoted from /conceptric2 in the same wave).
# THE GRAPH CHART LEADS (his fifth ruling, 2026-07-23: "the conceptric map is defined by
# its links!" — the graded descent renders AS a drawn graph, lists are secondary lenses):
# /conceptric now serves the link-graph map as the Grow stage's primary chart; the growth
# cockpit survives whole at /conceptric/cockpit, doored from the map (L5: nothing hidden).
_CONCEPTRIC_APP = Path(__file__).resolve().parent / "conceptric_map.html"
_CONCEPTRIC_COCKPIT = Path(__file__).resolve().parent / "conceptric.html"
_CONCEPTRIC_MAP = Path(__file__).resolve().parent / "conceptric_map.html"
# W6: the /dials standalone PAGE dies (his ruling: "dials are useful but they need to be
# integrated into the pipeline"). Its wire endpoints (/dials/state, /dials/op, /dials/undo)
# live on — dials_surface stays the ONE write path, now consumed by THE PIPELINE SURFACE's
# dials-in-place. The bare /dials route 301s to /pipeline (dials.html deleted).
_PIPELINE_APP = Path(__file__).resolve().parent / "pipeline.html"  # W6: THE PIPELINE SURFACE at /pipeline
# W5: the /guide explainer + the /tutorial page DIE (their desk MECHANISM rehoused to /desk);
# _GUIDE_APP / _TUTORIAL_APP and their routes are excised. THE DESK COCKPIT serves its page here.
_DESK_APP = Path(__file__).resolve().parent / "desk.html"
_DASHBOARD_APP = Path(__file__).resolve().parent / "dashboard.html"  # W1: THE DASHBOARD at /
# W2: THE ARTEFACT SURFACE (/artefact) serves its own page through artefact.handle (the
# projection/review pattern), so it needs no _APP constant here.

_FIG_EXTS = (".pdf", ".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif")
_CODE_EXTS = (".py", ".jl", ".m", ".c", ".cpp", ".js", ".ts", ".sh", ".r")
# GET /project/doc (W-brief-door, his ruling RW-20260723-154721-984120: "I can't read
# the brief... this option has been made bespoke rather than a mechanical consequence").
# The whitelist of text-like manuscript docs this route will render inline (never
# download) — everything else 404s. ``.md`` renders as markdown source; the rest as
# plain text (both readable in a browser tab, unlike an octet-stream download).
_DOC_EXTS = {
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".json": "text/plain; charset=utf-8",
    ".yaml": "text/plain; charset=utf-8",
    ".yml": "text/plain; charset=utf-8",
    ".tex": "text/plain; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
}
_FILENAME_HINT_RX = re.compile(r"([A-Za-z_][A-Za-z0-9_\-]*\.(?:" +
                                "|".join(e.lstrip(".") for e in _FIG_EXTS + _CODE_EXTS) +
                                "))")


def _corpus_asset_roots(troot: Path, corpus_name: str) -> list[Path]:
    """The full set of dirs the asset endpoint will look under for ``corpus_name``. Order matters
    — the resolver returns the FIRST hit, so we want:

    1. The paper's own tree (tex_root, its parent, its grandparent) — in-tree copies win, so a
       committed asset is reproducible across machines.
    2. The per-corpus extra roots (resolved against $HOME) — kept as a fallback for assets that
       still live outside the laplace repo.
    """
    from laplace.research.corpus_ingest import CORPUS_ASSET_ROOTS
    bases: list[Path] = []
    cur = Path(troot).resolve()
    for _ in range(3):
        if cur.is_dir():
            bases.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    for rel in CORPUS_ASSET_ROOTS.get(corpus_name, []):
        p = (Path.home() / rel).resolve()
        if p.is_dir():
            bases.append(p)
    # dedupe preserving order
    seen, out = set(), []
    for b in bases:
        s = str(b)
        if s not in seen:
            seen.add(s)
            out.append(b)
    return out


def _resolve_asset_for_node(troot: Path, corpus_name: str, nid: str,
                            node: dict | None = None) -> Path | None:
    """Resolve a node id to an asset file. Tries, in order:

    1. A filename hinted in the node's essence (e.g. 'method_exact.pdf' embedded in the text)
       — the PDF-sourced rewiring captures the path this way, since atomise_paper itself only
       stores captions. Tried first because it's a directly-named ground truth.
    2. The id suffix as a filename stem, with common extensions, in known asset dirs.
    3. A last-pass loose match: any file whose stem contains the key.

    Confined to the dirs returned by ``_corpus_asset_roots`` (the corpus' own tree + its declared
    extra roots).
    """
    bases = _corpus_asset_roots(Path(troot), corpus_name)
    if not bases:
        return None
    key = nid.split(":", 1)[1] if ":" in nid else nid
    # 1. hint from essence
    if node and node.get("essence"):
        m = _FILENAME_HINT_RX.search(node["essence"])
        if m:
            hint = m.group(1)
            for base in bases:
                for p in base.rglob(hint):
                    if p.is_file() and str(p.resolve()).startswith(str(base.resolve())):
                        return p.resolve()
    # 2. id-stem * common extension in known dirs
    candidates = ["", "source", "figures", "fig", "images", "img", "assets", "scripts", "code", "src"]
    stems = [key, "fig_" + key, key.replace("-", "_"), "fig_" + key.replace("-", "_")]
    exts = _FIG_EXTS + _CODE_EXTS
    for base in bases:
        for d in candidates:
            dpath = base / d if d else base
            if not dpath.is_dir():
                continue
            for stem in stems:
                for ext in exts:
                    p = dpath / f"{stem}{ext}"
                    if p.is_file() and str(p.resolve()).startswith(str(base.resolve())):
                        return p.resolve()
    # 3. loose match — any file in any common dir whose stem contains the key
    for base in bases:
        for d in candidates:
            dpath = base / d if d else base
            if not dpath.is_dir():
                continue
            for p in dpath.iterdir():
                if (p.is_file() and p.suffix.lower() in exts
                        and key.replace("-", "_") in p.stem.replace("-", "_")
                        and str(p.resolve()).startswith(str(base.resolve()))):
                    return p.resolve()
    return None


# kept for back-compat with the original /corpus/asset wiring
def _resolve_figure_asset(troot: Path, nid: str, corpus_name: str = "",
                          node: dict | None = None) -> Path | None:
    return _resolve_asset_for_node(troot, corpus_name, nid, node)
_NETWORK: dict = {}
_NETWORK_LOCK = threading.Lock()
_NETWORK_DIFF: dict = {}     # what LANDED at the last rebuild - the weld made watchable


def _network(refresh: bool = False) -> dict:
    """The one conceptric network, cached - the same object every reconstruction couples over.
    A refresh DIFFS the node sets (new / gone), so a fold's landing is something the author can
    SEE rather than hunt for - the minimal 'watch it land' the weld needs. The baseline PERSISTS
    (gitignored id-set beside the tree): a code-change restart no longer eats the landed card -
    what arrived since the last-served network shows regardless of which process serves it."""
    from laplace.engine import conceptric
    baseline = _repo_root() / ".scanner_last_ids.json"
    with _NETWORK_LOCK:
        if refresh or not _NETWORK:
            old_ids = set(_NETWORK.get("nodes", {}))
            if not old_ids and baseline.is_file():
                try:
                    old_ids = set(json.loads(baseline.read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    old_ids = set()
            _NETWORK.clear()
            _NETWORK.update(conceptric.load_network(_repo_root()))
            if old_ids:
                new_ids = set(_NETWORK["nodes"]) - old_ids
                gone_ids = old_ids - set(_NETWORK["nodes"])
                _NETWORK_DIFF.clear()
                _NETWORK_DIFF.update({
                    "n_new": len(new_ids), "n_gone": len(gone_ids),
                    "new": [{"id": i, "grade": _NETWORK["nodes"][i].get("grade", 0),
                             "label": i.replace("mind://", "mind/").rstrip("/").split("/")[-1] or "(root)"}
                            for i in sorted(new_ids, key=lambda x: (-_NETWORK["nodes"][x].get("grade", 0), x))[:60]],
                    "gone": sorted(gone_ids)[:60],
                })
            try:
                baseline.write_text(json.dumps(sorted(_NETWORK["nodes"])), encoding="utf-8")
            except OSError:
                pass                       # the card is best-effort; serving the network is not
        return _NETWORK


def _router_health() -> dict:
    """The router's vital signs for the cockpit, read from the mechanism's own files - the
    embedding cache, the trained metric, the wire-proposal ledger - never recomputed view-side.
    Cheap: file reads only, the model is never loaded here."""
    from laplace.representation import embed_router
    root = _repo_root()
    out: dict = {"backend": None, "embeddings_cached": 0,
                 "backend_loaded": embed_router._BACKEND is not None,
                 "metric_trained": (root / embed_router.METRIC_FILE).is_file(),
                 "proposals_banked": 0}
    cache = root / embed_router.CACHE_FILE
    if cache.is_file():
        try:
            disk = json.loads(cache.read_text(encoding="utf-8"))
            out["backend"] = disk.get("backend")
            out["embeddings_cached"] = len(disk.get("nodes", {}))
        except (OSError, ValueError):
            pass
    ledger = root / embed_router.PROPOSALS_FILE
    if ledger.is_file():
        try:
            out["proposals_banked"] = sum(
                1 for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip())
        except OSError:
            pass
    return out


def _pick_network(q: dict | None) -> dict:
    """The navigator's data layer, UNIFIED: serve the chosen paper conceptric when ``corpus`` is
    asked, else the engine's own network. Every /network/* route then renders identically over
    whichever network this returns - the same down-operators (his 'what I see == what you see'),
    one interface, never a second shell. A no-op (returns the engine network) when no corpus is set,
    so the navigator's existing behaviour is untouched."""
    corpus = (q.get("corpus", [""])[0] if q else "") or ""
    corpus = corpus.strip()
    if corpus:
        from laplace.research import corpus_ingest as _ci
        rr = _repo_root()
        troot = _ci.resolve_corpus(rr, corpus)
        if troot:
            return _ci.corpus_network(troot, repo_root=rr, name=corpus)
    return _network()


def corpus_content_dependencies(net: dict, nid: str) -> dict[str, list[str]]:
    """The derivation fields served by ``/corpus/content``.

    The endpoint can still serve citations and general links through their own
    fields, but its ``deps`` contract names logical prerequisites. Build that
    view through the same inferred adjacency used by planning consumers.
    """
    from laplace.research import corpus_ingest as _ci

    prerequisites = _ci.inferential_dependencies(net, nid)
    confirmed = {
        token[len("confirmed::"):]
        for token in net.get("edge_index", {}).get(nid, [])
        if token.startswith("confirmed::")
    }
    return {
        "explicit": [target for target in prerequisites if target not in confirmed],
        "confirmed": [target for target in prerequisites if target in confirmed],
    }


def network_meta(refresh: bool = False, q: dict | None = None) -> dict:
    from laplace.engine import conceptric
    from laplace.representation import embed_router
    net = _pick_network(q) if (q and (q.get("corpus", [""])[0] or "").strip()) else _network(refresh)
    nodes = net["nodes"]
    grades: dict[int, int] = {}
    for n in nodes.values():
        grades[n.get("grade", 0)] = grades.get(n.get("grade", 0), 0) + 1
    lenses: dict[str, int] = {}
    for ls in net["lenses"].values():
        for ln in ls:
            lenses[ln] = lenses.get(ln, 0) + 1
    return {
        "n_nodes": len(nodes), "root": net["root"],
        "grades": {str(g): c for g, c in sorted(grades.items())},
        "lenses": dict(sorted(lenses.items(), key=lambda kv: -kv[1])),
        "phases": conceptric.PHASES,
        "diff": dict(_NETWORK_DIFF),
        # the standing reconstruction geometry - the engine's own defaults, served so the
        # cockpit's knobs start from the mechanism's numbers, never a view-side copy.
        "geometry": {"beam": embed_router.BEAM,
                     "per_branch_width": embed_router.PER_BRANCH_WIDTH,
                     "path_decay": embed_router.PATH_DECAY,
                     "ancestor_decay": conceptric.ANCESTOR_DECAY,
                     "limit": 10},
        "router": _router_health(),
    }


def network_node(q: dict) -> dict:
    from laplace.engine import conceptric
    net = _pick_network(q)
    nid = q.get("id", [""])[0] or net["root"]
    width = q.get("width", [None])[0]
    lens = q.get("lens", [None])[0] or None
    conj = q.get("conjectural", [None])[0]
    phase = q.get("phase", [None])[0] or None
    scope = q.get("scope", ["grade"])[0]
    radius = q.get("radius", [None])[0]
    grade = q.get("grade", [None])[0]
    cross = q.get("cross_lens", ["1"])[0]
    # the navigator serves the SAME primitive a firing reconstructs (his unification): node_view +
    # the correlation-radius cut + the cross-lens bridges, so what he sees == what they see.
    return conceptric.reconstruct_node(
        net, nid,
        grade=int(grade) if grade is not None else None,
        width=int(width) if width is not None else None,
        lens=lens,
        radius=float(radius) if radius is not None else None,
        conjectural=(conj in ("1", "true")) if conj is not None else None,
        phase=phase, scope=scope,
        cross_lens=cross not in ("0", "false"),
    )

# ---------------------------------------------------------------------------
# the warm channel - the recurring mechanical acts, served by the warm process
# (the frictionless rule: a shell spawn costs 1-2s of profile before 50ms of
#  work; the warm scanner does the same work in-process and serves it as JSON)
# ---------------------------------------------------------------------------







def wake() -> dict:
    """The wake panel payload: the live probe + the grade-0 fixed point, both mechanical - the
    hello PAINTED into the cockpit before a single token is spent. What the author sees here is
    exactly what meets the agent (view = mechanism, applied to the wake itself)."""
    from laplace.engine import self_corpus
    return {"probe": probe(), "fixed_point": self_corpus.reconstruct_self(_repo_root(), 0)}


BENCH_FILE = ".recall_bench.json"     # gitignored: gold rows are the author's local instrument
COCKPIT_FILE = ".cockpit.json"        # gitignored: knob defaults + panel layout, his


def bench_rows() -> list[dict]:
    p = _repo_root() / BENCH_FILE
    if not p.is_file():
        return []
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def bench_add(row: dict) -> dict:
    """Append one gold row {q, expect, kind} - the author curates gold from the browser (he can
    see content; the orchestrator cannot, so item-level gold is HIS to write)."""
    q = str(row.get("q") or "").strip()
    expect = str(row.get("expect") or "").strip()
    if not q or not expect:
        return {"error": "a gold row needs q and expect"}
    rows = bench_rows()
    rows.append({"q": q, "expect": expect, "kind": str(row.get("kind") or "recall")})
    (_repo_root() / BENCH_FILE).write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    return {"ok": True, "n": len(rows)}


def bench_run() -> dict:
    """Run every gold row through the REAL fire (same call, standing geometry) and score
    mechanically: pass = the expected id (prefix) within the top 3 of the hit pool or of any
    per-grade bucket. The zero-token regression gate for all geometry tweaking."""
    from laplace.engine import conceptric
    net = _network()
    out_rows: list[dict] = []
    for row in bench_rows():
        q, expect = row.get("q", ""), row.get("expect", "")
        res = conceptric.fire_by_grade(_repo_root(), net, q, limit=10)
        rank = None
        for i, h in enumerate(res.get("hits", [])):
            if str(h.get("recovered", "")).startswith(expect):
                rank = i
                break
        if rank is None:
            for entries in (res.get("per_grade") or {}).values():
                for j, e in enumerate(entries):
                    if str(e.get("id", "")).startswith(expect):
                        rank = j if rank is None else min(rank, j)
                        break
        out_rows.append({**row, "rank": rank, "pass": rank is not None and rank < 3,
                         "router": res.get("router")})
    return {"rows": out_rows, "n": len(out_rows),
            "n_pass": sum(1 for r in out_rows if r["pass"])}


def cockpit_state(update: dict | None = None) -> dict:
    """The author's cockpit layout + knob defaults, persisted server-side (gitignored) so what
    is shown is HIS and survives restarts. GET returns it; POST merges."""
    p = _repo_root() / COCKPIT_FILE
    state: dict = {}
    if p.is_file():
        try:
            state = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
    if isinstance(update, dict) and update:
        state.update(update)
        try:
            p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    return state


def review_last_visit(key: str) -> str:
    """W2.4 - the author's last-visit cursor for a /review corpus/dir ``key``, read
    from the ``review_last_visit`` map in the gitignored .cockpit.json. The
    deltas-first baseline lives HERE now (not browser localStorage) so "new since
    your last visit" survives a browser wipe and is server-computable. Pure read,
    FAIL-CLOSED: absent / broken / no-such-key -> ``""``, never a raise."""
    key = (key or "").strip()
    if not key:
        return ""
    lv = cockpit_state().get("review_last_visit")
    if isinstance(lv, dict):
        v = lv.get(key)
        if isinstance(v, str):
            return v.strip()
    return ""


def record_review_visit(key: str, ts: str) -> dict:
    """W2.4 - bank the author's last-visit cursor for a /review ``key`` into
    .cockpit.json, NESTED-merged under ``review_last_visit`` so every OTHER cockpit
    key (active_corpus, knob layout) AND every other corpus's cursor survives (the
    W0.2 additive-merge idiom, one level deeper). scanner is the one writer of
    .cockpit.json. The cursor is MONOTONE: a stale tab banking an older ts never
    moves the baseline backward (which would make already-seen findings read new)."""
    key = (key or "").strip()
    ts = (ts or "").strip()
    if not key or not ts:
        return {"ok": False, "error": "key and ts are required"}
    cur = cockpit_state().get("review_last_visit")
    lv = dict(cur) if isinstance(cur, dict) else {}
    if ts > str(lv.get(key) or ""):
        lv[key] = ts
    # shallow-merge the WHOLE nested map back: it carries every prior corpus cursor,
    # so the shallow cockpit_state update loses no sibling entry, and every unrelated
    # top-level key is untouched.
    cockpit_state({"review_last_visit": lv})
    return {"ok": True, "key": key, "ts": lv.get(key, ts)}


def _writing_entry_redirect(path, query, repo_root):
    """Retire general arrivals without losing explicitly addressed legacy reads."""
    if path not in ("/", "/artefact"):
        return None
    from urllib.parse import urlencode
    from laplace.pipeline import registry
    if "corpus" in query:
        values = query["corpus"]
        if (not isinstance(values, list) or len(values) != 1 or
                not isinstance(values[0], str) or not values[0] or
                values[0] != values[0].strip() or
                any(ord(char) < 32 for char in values[0]) or
                registry.resolve(values[0], repo_root=repo_root) is None):
            raise ValueError("corpus must name exactly one registered project; duplicate, blank or unknown scope was not adopted")
    # A version/file/node/object/finding/mode (or any other legacy coordinate)
    # still belongs to the legacy reader. Its semantics cannot be translated by
    # a generic arrival redirect.
    if path == "/artefact" and set(query) - {"corpus"}:
        return None
    if "workspace" in query and query["workspace"] != ["writing"]:
        raise ValueError("This entry moved to the writing workspace; conflicting workspace coordinates were not adopted")
    destination = {**query, "workspace": ["writing"]}
    if path == "/artefact":
        destination["view"] = ["manuscript"]
    return "/project?" + urlencode(destination, doseq=True)


def _writing_response(owner, path, query, method, body):
    """Keep the project root explicit through every UI operation and test fixture."""
    import inspect
    params = inspect.signature(owner.handle).parameters
    kwargs = {"repo_root": _repo_root()} if "repo_root" in params else {}
    try:
        return owner.handle(path, query, method, body, **kwargs)
    except (ValueError, KeyError, PermissionError) as exc:
        return 422, "application/json", json.dumps({"error": str(exc)}).encode()
    except Exception as exc:
        return 500, "application/json", json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode()


def make_handler(*, shared_assets=None, source_start=None, runtime_start=None, runtime_selection_start=None,
                 managed_homes_start=None, workspace_start=None):
    class Handler(BaseHTTPRequestHandler):
        #: set by the walk-only gate when a request proved its token by query or header;
        #: `_send` hands it back so the page's own fetches carry it onward.
        _walk_cookie = ""

        def parse_request(self) -> bool:  # noqa: D401
            """The gate check, above every route and every method.

            The walk-only serving contract (``LAPLACE_WALK_ONLY`` / ``LAPLACE_WALK_TOKEN``,
            owned by :mod:`laplace.manuscript.walk`) is enforced HERE — once, on the parsed request
            line, before a single route branch runs. Scattering it through the do_GET /
            do_POST route ladders would mean every surface added later had to remember it,
            which is how a gate becomes a suggestion. Off by default: with no env set this
            is one dict lookup and the request proceeds exactly as before."""
            if not BaseHTTPRequestHandler.parse_request(self):
                return False
            self._exchange = _traffic_begin(self)   # the traffic ledger's exchange (writing/traffic.py)
            # THE HOST ALLOWLIST (the CORS cure's second leg, IFACE review 2026-08-24):
            # a loopback bind does not stop DNS rebinding — a hostile page resolving
            # its own name to 127.0.0.1 arrives with a foreign Host header. Refuse it
            # here, above every route, so every surface added later inherits the gate.
            # An absent Host (HTTP/1.0 curl) stays allowed; loopback names only else.
            host = self.headers.get("Host", "").split(":")[0].strip("[]").lower()
            if host not in ("", "localhost", "127.0.0.1", "::1"):
                body = b'{"error": "foreign Host refused - loopback names only"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                try:
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                self.close_connection = True
                return False
            from laplace.manuscript import walk as _wk
            gate = _wk.gate_request(self.path, self.headers)
            self._walk_cookie = gate.get("set_cookie") or ""
            refusal = gate.get("refusal")
            if refusal is not None:
                status, ctype, payload = refusal      # the handler convention, one order
                self._send(status, payload, ctype)
                self.close_connection = True
                return False
            return True

        def _send(self, code: int, body, ctype: str = "application/json") -> None:
            data = body if isinstance(body, bytes) else str(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            if self._walk_cookie:
                self.send_header("Set-Cookie", self._walk_cookie)
            origin = self.headers.get("Origin", "")
            if origin and _LOCAL_ORIGIN.match(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
            # no-cache (2026-07-15, the pull-back walk): with no validators the browser
            # heuristic-caches /shared/* and keeps running WEEK-OLD interface code after a
            # pull - the staleness law broken client-side. Localhost refetch is free.
            self.send_header("Cache-Control", "no-cache")
            # a client that closed the page mid-response (a browser abort, a killed
            # walk) must never take the whole engine down - swallow the disconnect,
            # the response has no reader (his walks hit this 2026-07-22 night)
            try:
                self.end_headers()
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _redirect(self, location: str, code: int = 301) -> None:
            # W0.3 retirements: a permanent move (301) to the surviving route. The
            # Location header is the contract; a tiny body keeps a bare fetch honest.
            body = f'moved permanently to {location}'.encode("utf-8")
            self.send_response(code)
            self.send_header("Location", location)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            origin = self.headers.get("Origin", "")
            if origin and _LOCAL_ORIGIN.match(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
            try:
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            if u.path == "/authoring/health":
                # THE HEALTH DOOR (declared 'authoring/health' in writing_declared_http): its query is
                # admitted against the declared schema BEFORE any health work. No query: the ordinary
                # lifecycle answer below; view=traffic: the traffic ledger, loopback clients only, a locked
                # copy of its counters (no source read or hashing), counted as a diagnostic self-read.
                try:
                    view = _health_view(u)
                except ValueError as exc:
                    self._send(422, json.dumps(_health_refusal(str(exc))))
                    return
                if view == "traffic":
                    from laplace.web import traffic
                    if str(self.client_address[0]).removeprefix("::ffff:") not in ("127.0.0.1", "::1"):
                        self._send(403, json.dumps({"error": "The traffic view answers loopback clients only.",
                                                    "recovery": _HEALTH_READS}))
                    else:
                        self._send(200, json.dumps(traffic.snapshot()))
                    return
            lossless_query = False
            if u.path.startswith(("/authoring/", "/research/", "/references/", "/formal/", "/projects/", "/work/", "/concepts/", "/visuals/")):
                from laplace.native.declarations import http_lossless_query
                try:
                    lossless_query = http_lossless_query(u.path, "GET")
                except ValueError as exc:
                    self._send(409, json.dumps({"error": str(exc)}), "application/json")
                    return
            q = parse_qs(u.query, keep_blank_values=lossless_query or u.path in ("/", "/artefact"))
            if u.path in ("/", "/artefact"):
                try:
                    destination = _writing_entry_redirect(u.path, q, _repo_root())
                except ValueError as exc:
                    self._send(422, json.dumps({"error": str(exc)}), "application/json")
                    return
                if destination:
                    self._redirect(destination, 301)
                    return
            if u.path == "/authoring/events":
                from laplace.web.authoring import stream
                stream(self, q)
                return
            if u.path.startswith(("/authoring/", "/research/", "/references/", "/formal/", "/projects/", "/work/", "/concepts/", "/visuals/")):
                from laplace.web import authoring as authoring_surface, research_surface, project_work_surface
                from laplace.research import references_surface, formal_surface, concepts as concepts_surface, visuals_surface
                from laplace.projects import library as writing_projects
                owner = {"authoring": authoring_surface, "research": research_surface,
                         "references": references_surface, "formal": formal_surface,
                         "projects": writing_projects, "work": project_work_surface,
                         "concepts": concepts_surface, "visuals": visuals_surface}[u.path.split("/")[1]]
                result = _writing_response(owner, u.path, q, "GET", b"")
                if result is not None:
                    status, ctype, payload = result
                    if u.path == "/authoring/health" and status == 200:
                        health = json.loads(payload)
                        if shared_assets is not None:
                            health["frontend_bundle"] = shared_assets.identity
                        if source_start is not None:
                            health["source_start"] = source_start
                        if runtime_start is not None:
                            health["runtime_start"] = runtime_start
                        if runtime_selection_start is not None:
                            health["runtime_selection_start"] = runtime_selection_start
                        if managed_homes_start is not None:
                            health['managed_homes'] = managed_homes_start
                            health.update({key: managed_homes_start[key] for key in
                                          ('code_root', 'workspace_root', 'engine_state', 'session_workspaces')})
                            health['workspace_start'] = workspace_start
                        payload = json.dumps(health).encode("utf-8")
                    self._send(status, payload, ctype)
                    return
            # FAVICON (fix wave minor): every page provoked a /favicon.ico 404 in the
            # console — honest noise, but noise. Serve one tiny embedded mark (the
            # Laplace glyph) so the browser's implicit request is satisfied, not 404'd.
            # Self-contained bytes, no static-asset dependency.
            if u.path == "/favicon.ico":
                icon = (
                    b'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" '
                    b'viewBox="0 0 16 16"><rect width="16" height="16" rx="3" fill="#0b0d12"/>'
                    b'<circle cx="8" cy="8" r="3.1" fill="none" stroke="#5ee6b0" '
                    b'stroke-width="1.5"/><circle cx="8" cy="8" r="1" fill="#5ee6b0"/></svg>'
                )
                self._send(200, icon, "image/svg+xml")
                return
            # W2 CONSOLIDATION: /projection + /review folded into the ONE artefact surface
            # (conception §2). The bare PAGE routes 301 to /artefact, preserving the corpus/
            # selection query so the deep-link travels unchanged; their /projection/* +
            # /review/* DATA producers stay live (the artefact panes re-house them).
            if u.path in ("/projection", "/review"):
                self._redirect("/artefact" + (("?" + u.query) if u.query else ""), 301)
                return
            if u.path == "/artefact" or u.path.startswith("/artefact/"):
                # THE ARTEFACT SURFACE (W2): GET /artefact serves the page; /artefact/context
                # (registry.project_context — the ONE authority) and /artefact/parity (the P2
                # disk-truth read) delegate here. artefact.handle owns /artefact*.
                from laplace.web import artefact as _af
                res = _af.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/walk" or u.path.startswith("/walk/"):
                # THE REDLINE WALK (DESIGN_2026-08-10): its OWN surface — walk.html +
                # walk.mjs — with no shell chrome inherited. Shared truth reaches it
                # through /artefact/context, /review/*, /projection/* only.
                from laplace.manuscript import walk as _wk
                if u.path == "/walk" and shared_assets is not None:
                    template = shared_assets.pages.get("walk")
                    res = ((200, "text/html; charset=utf-8", _wk.page_bytes(_wk._q1(q, "corpus"), template=template))
                           if template is not None else (404, "text/plain", b"writing template unavailable"))
                else:
                    res = _wk.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/projection" or u.path.startswith("/projection/"):
                from laplace.manuscript import projection_viewer as _pv
                res = _pv.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/shared/"):
                # the shared UI layer: hymn.css / shell.js / inspector.js + /shared/plan
                from laplace.web import shared_ui as _su
                res = _su.handle(u.path, q, snapshot=shared_assets)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/storyboard" or u.path.startswith("/storyboard/"):
                # the plan-object editor: the narrative structure as a board. Delegated
                # module, same contract as projection_viewer; edits the projection plan.
                from laplace.manuscript import storyboard as _sb
                res = _sb.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/review" or u.path.startswith("/review/"):
                # the REVIEW VIEWER (G-2): the real rendered artefact with node-precise
                # findings. Sibling surface, same contract; reuses projection's pdf.js
                # producer + /shared atoms, adds the nodemap-anchored findings layer.
                from laplace.manuscript import review_surface as _rv
                from laplace.web import review_http
                res = review_http.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/altitude" or u.path.startswith("/altitude/"):
                # the ALTITUDE TOWER (B13.5): one substrate viewed at rising
                # altitudes — nodes -> grade-shells -> spine -> plan/prose — opened
                # AT an anchor and shiftable up/down. READ-ONLY; grading made
                # load-bearing (live dep_grade). Trace-up from /review lands here
                # via the /altitude?corpus=&anchor= contract.
                from laplace.engine import altitude as _alt
                res = _alt.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/analytics" or u.path.startswith("/analytics/"):
                # the ANALYTICS DASHBOARD (P11): a read-only cross-project convergence
                # rollup + per-project round series, straight from the P7 assembler.
                # Honesty contract: zero rounds -> "never run", absent economics ->
                # "never captured"; no fabricated numbers.
                from laplace.web import analytics as _an
                res = _an.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/dials" or u.path.startswith("/dials/"):
                # THE DIALS CONJUGATE (the calibration write path): GET /dials/state
                # delegates to the write-surface module; the write verbs (/dials/op,
                # /dials/undo) are POST, handled in do_POST. dials_surface.handle owns
                # only /dials/* and returns None for the bare page. W6: the bare /dials
                # PAGE DIES (his ruling: the dials are integrated into the pipeline) —
                # it 301s to /pipeline, which re-houses the dials editor IN PLACE per
                # organ over these SAME wire endpoints. dials.html is deleted.
                from laplace.web import dials_surface as _ds
                res = _ds.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
                if u.path == "/dials":
                    self._redirect("/pipeline", 301)
                    return
            if u.path.startswith("/evolution/"):
                # THE EVOLUTION DESK (2026-07-20): the ratify queue's READ door
                # (GET /evolution/queue). The action verbs (/evolution/ratify,
                # /evolution/hold, /evolution/reject) are POST, in do_POST.
                from laplace.web import evolution_surface as _ev
                res = _ev.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/selection/"):
                # THE SELECTION DESK (P3): heredity's ratify stage's READ door
                # (GET /selection/sheet). The ruling verb (/selection/rule) is POST,
                # in do_POST. Record-only — a selection ruling mutates no artifact.
                from laplace.web import selection_surface as _sel
                res = _sel.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/derivation/"):
                # THE DERIVATION FACE (2026-07-21): the aspiration-first reach organ's
                # READ doors — GET /derivation/sheet (aspiration + chain + reach joined)
                # and GET /derivation/fragment (one forged .tex, path-fenced, read-only).
                # The acts (/derivation/rescope, /derivation/forge, /derivation/contest)
                # are POST, in do_POST — armed, attributed, append-only.
                from laplace.web import derivation_surface as _der
                res = _der.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/project/doc":
                # THE MANUSCRIPT DOC ROUTE (W-brief-door, 2026-07-23, his ruling
                # RW-20260723-154721-984120: "I can't read the brief... it's a shame
                # the read the brief doesn't hook in. I'm also worried that this
                # option has been made bespoke rather than a mechanical consequence").
                # GET /project/doc?corpus=<name>&path=<manuscript-relative> (a ``dir=``
                # repo-relative alternative also works — the SAME dual resolution
                # every review-family route already accepts) — a read-only, path-fenced
                # render of ONE text-like doc under the resolved manuscript dir. No
                # directory listing; the mechanism `_brief_door` (pipeline_surface) now
                # points at instead of a dead ``file://`` deep-link — this route is the
                # GENERAL consequence, not a bespoke one-off.
                from laplace.manuscript import review_surface as _rv
                from laplace.web import review_http
                corpus = (q.get("corpus", [""])[0] or "").strip()
                dir_param = (q.get("dir", [""])[0] or "").strip()
                rel = (q.get("path", [""])[0] or "").strip()
                md = _rv.manuscript_dir(corpus, dir_param)
                if md is None:
                    self._send(404, b"not found", "text/plain; charset=utf-8")
                    return
                try:
                    base = md.resolve()
                    resolved = (base / rel).resolve()
                    resolved.relative_to(base)      # containment fence — never escape the manuscript dir (mirrors pipeline_surface._brief_door)
                except (ValueError, OSError):
                    self._send(403, b"forbidden", "text/plain; charset=utf-8")
                    return
                ctype = _DOC_EXTS.get(resolved.suffix.lower())
                if ctype is None or not resolved.is_file():
                    self._send(404, b"not found", "text/plain; charset=utf-8")
                    return
                try:
                    data = resolved.read_bytes()
                except OSError:
                    self._send(404, b"not found", "text/plain; charset=utf-8")
                    return
                self._send(200, data, ctype)
                return
            if u.path == "/project" or u.path.startswith("/project/"):
                # THE PROJECT COCKPIT (ACT 4): the pipeline reborn as ONE page per
                # project — the truthful state strip, the generation panel (debt
                # 30→20→3→0), the RESPINE ("gen-4's opener"), the write-surface tabs.
                # The canonical route; the bare GET serves the page (the same
                # pipeline.html shell, whose mjs builds the cockpit sections). The API
                # stays under /pipeline/* (chain/verdict/organ) so the read model has
                # one home; /project/* delegates there too for any future sub-read.
                from laplace.web import pipeline_surface as _pl
                if u.path != "/project":
                    res = _pl.handle("/pipeline/" + u.path[len("/project/"):], q, "GET", b"")
                    if res is not None:
                        status, ctype, payload = res
                        self._send(status, payload, ctype)
                        return
                # the issued page names the frozen frontend snapshot it was served from (shared_ui.issued_page)
                from laplace.web import shared_ui as _su
                page = _su.issued_page(shared_assets, "project") if shared_assets is not None else _PIPELINE_APP.read_bytes()
                self._send(200 if page is not None else 404, page if page is not None else b"writing template unavailable", "text/html; charset=utf-8")
                return
            if u.path == "/pipeline" or u.path.startswith("/pipeline/"):
                # THE PIPELINE SURFACE (W6): the live chain rendered FROM the release
                # state machine (view = mechanism, never a drawn diagram). GET
                # /pipeline/chain·/verdict·/organ (the board read models) delegate to the
                # read-only pipeline_surface module. The bare page 301s to /project (ACT
                # 4: the cockpit is canonical) — the API routes are NOT redirected (they
                # are data, not a page). Every mutation rides an EXISTING door — dial
                # edits /dials/op·/dials/undo, scoped fires /storyboard/run/launch — so
                # this surface owns no write route.
                if u.path == "/pipeline":
                    self._redirect("/project" + (("?" + u.query) if u.query else ""), 301)
                    return
                from laplace.web import pipeline_surface as _pl
                res = _pl.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/guide" or u.path.startswith("/guide/"):
                # THE STRUCTURAL GUIDE (W-guide, 2026-07-22, PRM-20260721-structural-guide):
                # what the engine is, what each surface does, and what every action WILL DO
                # — rendered FROM contract/surfaces/*.yaml (the keystone: documentation is
                # the behavior's declaration, so the guide cannot drift). Read-only;
                # guide.handle owns /guide*. The W5-era /guide explainer died on this path
                # long ago — this is a different organ on the reclaimed route.
                from laplace.web import guide as _gd
                res = _gd.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/desk" or u.path.startswith("/desk/"):
                # THE DESK COCKPIT (W5): every decision expands in place into a cockpit
                # (conception §6). GET /desk/data (the read-model) + /desk/referent (the
                # full CONTEXT per row) delegate to the read-only desk module; the bare
                # GET /desk serves the page (read fresh, like the other apps). The ONE
                # mutation door POST /desk/act is handled in do_POST. desk.handle owns
                # /desk/* and returns None for the bare page. The /guide explainer + the
                # /tutorial page (W1-W8) DIE here — the desk mechanism rehoused (census W5).
                from laplace.web import desk as _dk
                res = _dk.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
                if u.path == "/desk":
                    self._send(200, _DESK_APP.read_bytes(), "text/html; charset=utf-8")
                    return
            if u.path == "/assets" or u.path.startswith("/assets/"):
                # THE ASSET SURFACE (W7): every derivation and every figure an ADDRESSABLE
                # OBJECT — the CARD/COCKPIT idiom over pipeline/asset_model.enumerate_assets
                # (THE FAILURE RECORD's debt paid). GET /assets serves the page; /assets/list
                # (the roster), /assets/object (one asset + anchors + history), and
                # /assets/render (the rendered figure bytes) delegate to the read-only
                # assets_surface module. The two POST doors (assess / regen) are in do_POST.
                # assets_surface.handle owns /assets*.
                from laplace.web import assets_surface as _as
                res = _as.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/lineage" or u.path.startswith("/lineage/"):
                # THE LINEAGE SURFACE (W-lineage, 2026-07-22): per-project views of the
                # conceptric and its descendants. GET /lineage serves the page (a brief base
                # altitude); /lineage/brief·node·object·whole·find delegate to the read-only
                # lineage_surface module, which composes over the master node index + the
                # descent walk + the provenance door. The one write, POST /lineage/reindex,
                # is in do_POST. lineage_surface.handle owns /lineage*.
                from laplace.web import lineage_surface as _lin
                res = _lin.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/provenance") or u.path.startswith("/descendants"):
                # THE PROVENANCE + LINEAGE DOORS (G-index, 2026-07-22): GET
                # /provenance/object (a rendered object resolved to where it came from,
                # across the five id namespaces) and GET /descendants/node (a concept node
                # and everything it leads to). Both compose in the block grammar over the
                # master node index; read-only, provenance_surface.handle owns them.
                from laplace.web import provenance_surface as _pr
                res = _pr.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/dashboard/"):
                # W1 THE DASHBOARD data/door: /dashboard/data (GET, the cards' one fetch)
                # and /dashboard/new (POST, handled in do_POST). dashboard.handle owns
                # /dashboard/* and returns None for the bare / page (served below).
                from laplace.web import dashboard as _dash
                res = _dash.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/front/stream":
                # FRONT DOOR M1: the one streaming route. A stream cannot ride the
                # whole-body handle() contract, so the tailer writes to this handler
                # directly (SSE, byte-offset cursors, Last-Event-ID resume). It
                # returns only when the client disconnects.
                from laplace.web import stream as _stream
                _stream.serve(self, q)
                return
            if u.path == "/front" or u.path.startswith("/front/"):
                # FRONT DOOR M1 (the Interface seat; his founding scope ruling
                # 2026-08-24): one read page over the rows - apex account strip,
                # campaign grid, live tail, trace waterfall, record descend, chats,
                # organ health. front_door.handle owns /front/*; read-only at M1.
                from laplace.web import front_door as _front
                res = _front.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/seats"):
                # FRONT DOOR M1 (PV-20260824-his-move-quickly-interface-first): the seats
                # surface - sessions with the hung detector, the seat rows, the pending
                # permission-ask lane, account/campaign panels. Read-only; the page at
                # /seats, the one fetch at /seats/data (seats_surface.handle owns it).
                if u.path == "/seats":
                    page = Path(__file__).resolve().parent / "seats_surface.html"
                    self._send(200, page.read_bytes(), "text/html; charset=utf-8")
                    return
                from laplace.web import seats_surface as _seatsurf
                res = _seatsurf.handle(u.path, q, "GET", b"")
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path in ("/index.html", "/map"):
                # the brain scanner (the reconstruction network's navigable page): its
                # own route now that / is the landing. /index.html stays a back-compat
                # alias for the same bytes.
                self._send(200, _APP.read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/meta":
                # RETIRED (W5 chrome census kill): zero front-end consumers (grep of every
                # html/js/mjs found none). The /editor idiom.
                self._send(410, "410 Gone — /meta is retired (zero front-end consumers).",
                           "text/plain; charset=utf-8")
            elif u.path == "/graph":
                src = q.get("source", ["all"])[0]
                refresh = q.get("refresh", ["0"])[0] in ("1", "true")
                self._send(200, json.dumps(graph_for(src, refresh)))
            elif u.path == "/reconstruct":
                # RETIRED (W5 chrome census kill): zero front-end consumers. The Python-side
                # equivalent (conceptric.reconstruct_node) is called directly, in-process, by
                # scripts/reconstruct_node.py and scripts/wake.py — never over this HTTP door.
                self._send(410, "410 Gone — /reconstruct is retired (zero front-end consumers). "
                           "Use `python scripts/reconstruct_node.py <node-id>` instead.",
                           "text/plain; charset=utf-8")
            elif u.path == "/pulse":
                self._send(200, json.dumps(_pulse()))
            elif u.path == "/grades":
                refresh = q.get("refresh", ["0"])[0] in ("1", "true")
                self._send(200, json.dumps(grades_payload(refresh)))
            elif u.path == "/ring":
                goal = q.get("goal", [""])[0]
                pull = float(q.get("pull", ["0"])[0] or 0)
                if not goal.strip():
                    self._send(400, json.dumps({"error": "empty goal"}))
                else:
                    self._send(200, json.dumps(ring_fire(goal, pull_fraction=pull)))
            elif u.path == "/firings":
                since = int(q.get("since", ["0"])[0] or 0)
                self._send(200, json.dumps(_FIRINGS.since(since)))
            elif u.path == "/spine":
                # RETIRED (W5 chrome census kill): zero front-end consumers. The spine still
                # rides every POST /fire response (spine.top_of_mind, called in-process there).
                self._send(410, "410 Gone — /spine is retired (zero front-end consumers). "
                           "The spine rides every POST /fire response instead.",
                           "text/plain; charset=utf-8")
            elif u.path == "/navigator":
                # RETIRED (W0.3): the navigator PAGE folds into the altitude tower.
                # /network/* (its surviving data layer) is untouched.
                self._redirect("/altitude", 301)
            elif u.path == "/conceptric":
                # THE conceptric surface — the drawn link-graph chart (his fifth ruling:
                # the map is defined by its links; the graded descent renders AS descent).
                self._send(200, _CONCEPTRIC_APP.read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/conceptric/cockpit":
                # the growth cockpit, whole, one door below the map (L5: re-homed, not hidden)
                self._send(200, _CONCEPTRIC_COCKPIT.read_bytes(), "text/html; charset=utf-8")
            elif u.path == "/editor":
                # RETIRED (W0.3, per N48): the manuscript editor is GONE — the
                # rendered-artefact surface is the projection viewer now.
                self._send(410,
                           "410 Gone — /editor is retired. Use the projection "
                           "viewer at /projection.",
                           "text/plain; charset=utf-8")
            elif u.path == "/conceptric2":
                # RETIRED (W3): the /conceptric2 route is retired; the surface is promoted to
                # /conceptric. The redirect is INVERTED (was /conceptric -> /conceptric2) so any
                # /conceptric2 deep-link still lands. Pinned by test_interface_weld _RETIRED.
                self._redirect("/conceptric", 301)
            elif u.path == "/review_static":
                # RETIRED (Wave 0 · L5 census): review_static.html is superseded by THE ARTEFACT
                # SURFACE (read / annotate / edit over the one model). 301 -> /artefact carrying
                # the selection query (corpus/node → the successor's same params) so a deep-link
                # lands on the same paper. The TEMPLATE is now DELETED (2026-07-17): export_review.py
                # was ported off it onto the artefact surface (his word PV-20260717T002125Z), so no
                # file backs this route — only the 301 stub. Pinned by test_palette_per_route.
                self._redirect("/artefact" + (("?" + u.query) if u.query else ""), 301)
            elif u.path == "/conceptric_editor2":
                # RETIRED (Wave 0 · L5 census): conceptric_editor2.html is superseded by THE
                # CONCEPTRIC SURFACE (rebuilt on the shared model). 301 -> /conceptric carrying the
                # selection query. The TEMPLATE stays on disk (his named call to remove); after
                # this, no route serves it. Pinned by test_palette_per_route.
                self._redirect("/conceptric" + (("?" + u.query) if u.query else ""), 301)
            # /manuscript/pdf + /manuscript/conceptric removed (Chrome Census W0 kill:
            # zero live consumers; the sole consumer /editor is already 410). The
            # manuscript_bridge module stays — /corpus/* and /projection/* still use it.
            elif u.path.startswith("/corpus/"):
                # the finished-paper conceptric served through the EXISTING down-operator (the navigator
                # machinery), embedding-free. corpus= names a paper; the rest reuses conceptric.*
                from laplace.engine import conceptric as _cc
                from laplace.research import corpus_ingest as _ci
                rr = _repo_root()
                if u.path == "/corpus/list":
                    # the roster is the REGISTRY roster (one door), the only roster there
                    # is — a dashboard-born project surfaces here by construction.
                    # openable: the switch only offers doors that open (main.tex gate).
                    self._send(200, json.dumps(
                        {"corpora": _ci.registered_corpora(rr, openable=True),
                         "default": _ci.default_corpus(rr)}))
                else:
                    name = q.get("corpus", [""])[0] or _ci.default_corpus(rr)
                    troot = _ci.resolve_corpus(rr, name)
                    if not troot:
                        self._send(404, json.dumps({"error": f"unknown corpus {name}"}))
                    elif u.path == "/corpus/candidates":
                        self._send(200, json.dumps(_ci.corpus_candidates(troot), ensure_ascii=False))
                    elif u.path == "/corpus/grade_stats":
                        from laplace.research import corpus_stats as _corpus_stats
                        st, ct, body = _corpus_stats.handle(u.path, q, name)
                        self._send(st, body, ct)
                    elif u.path == "/corpus/co-cited":
                        from laplace.research import corpus_cocited as _corpus_cocited
                        st, ct, body = _corpus_cocited.handle(u.path, q, name)
                        self._send(st, body, ct)
                    elif u.path == "/corpus/friction":
                        # the CURRENT per-node state, not the raw append-only event log (his 2026-07-03:
                        # an overlay-authored corpus dumps its whole build here, so show the reduced present)
                        if q.get('view',[''])[0] in {'reports','history'} or q.get('id'):
                            from laplace.work.technical_friction import read
                            values={key:q[key][0] for key in ('id','view','cursor','as_of') if q.get(key)}
                            self._send(200,json.dumps(read(rr,name,values),ensure_ascii=False))
                        else:
                            self._send(200, json.dumps(
                                {"records": _ci.friction_current(_ci.rewire_list(rr, name))}, ensure_ascii=False))
                    elif u.path == "/corpus/feedback":
                        # node comments WITHOUT editing the essence (his ask, 2026-07-08) -
                        # same ONE ledger the projection viewer's review mode writes
                        # (<plan target_dir>/feedback/feedback.jsonl), never a second store
                        led = _corpus_feedback_ledger(rr, name)
                        if led is None:
                            self._send(404, json.dumps({"error": f"corpus {name} has no plan/target_dir"}))
                        else:
                            from laplace.manuscript import manuscript_bridge as _mb
                            out = _mb.feedback_list(rr, name, ledger=led)
                            nid = q.get("node", [""])[0]
                            if nid:
                                out["records"] = [r for r in out["records"] if r.get("node_id") == nid]
                                out["n"] = len(out["records"])
                            self._send(200, json.dumps(out, ensure_ascii=False))
                    elif u.path == "/corpus/macros":
                        self._send(200, json.dumps({"macros": _ci.extract_macros(troot)}, ensure_ascii=False))
                    else:
                        net = _ci.corpus_network(troot, repo_root=rr, name=name)   # applies the rewiring overlay
                        if u.path == "/corpus/grade":
                            g = int(q.get("g", ["1"])[0] or 1)
                            self._send(200, json.dumps(_cc.grade_view(rr, net, g), ensure_ascii=False))
                        elif u.path == "/corpus/explode":
                            self._send(200, json.dumps(_cc.explode(rr, net, q.get("id", [""])[0]),
                                                       ensure_ascii=False))
                        elif u.path == "/corpus/node":
                            self._send(200, json.dumps(_cc.reconstruct_node(net, q.get("id", [""])[0]),
                                                       ensure_ascii=False))
                        elif u.path == "/corpus/spine":
                            # each beat carries its canonical TERM (projection.term) so the
                            # rails can render one-line handles instead of full essences
                            sp = [{**s, "term": (net["nodes"].get(s["id"], {})
                                                 .get("projection") or {}).get("term")}
                                  for s in net.get("spine", [])]
                            self._send(200, json.dumps({"spine": sp}, ensure_ascii=False))
                        elif u.path == "/corpus/neighborhood":
                            cand = _ci.candidates_cached(troot)   # read-only: never embeds (PSU)
                            self._send(200, json.dumps(
                                _ci.neighborhood(net, q.get("id", [""])[0], cand),
                                ensure_ascii=False))
                        elif u.path == "/corpus/derivation":
                            self._send(200, json.dumps(
                                _ci.derivation_subtree(net, q.get("id", [""])[0]), ensure_ascii=False))
                        elif u.path == "/corpus/map":
                            self._send(200, json.dumps(_ci.dag_map(net), ensure_ascii=False))
                        elif u.path == "/corpus/techniques":
                            self._send(200, json.dumps({"techniques": _ci.techniques(net)},
                                                       ensure_ascii=False))
                        elif u.path == "/corpus/gaps":
                            self._send(200, json.dumps({"gaps": [
                                {"id": g, "essence": (net["nodes"][g].get("essence") or "")[:120],
                                 "kind": net["nodes"][g].get("kind")} for g in _ci.gaps(net)]},
                                ensure_ascii=False))
                        elif u.path == "/corpus/goals":
                            # every goal node (kind=='goal') — the project's central claim(s),
                            # rendered at the TOP of the conceptric surface (the stock is FOR
                            # something). goals sit ABOVE the derivation DAG, so /corpus/map (which
                            # is DERIVATION_KINDS only) never carries them; this is their one door.
                            sp_ords = {s["id"]: s.get("ord") for s in net.get("spine", [])}
                            self._send(200, json.dumps({"goals": [
                                {"id": nid, "essence": n.get("essence") or "",
                                 "kind": n.get("kind"), "spine_ord": sp_ords.get(nid)}
                                for nid, n in net["nodes"].items()
                                if n.get("kind") == "goal"]}, ensure_ascii=False))
                        elif u.path == "/corpus/search":
                            self._send(200, json.dumps(
                                {"results": _ci.search_nodes(net, q.get("q", [""])[0])},
                                ensure_ascii=False))
                        elif u.path == "/corpus/content":
                            nid = q.get("id", [""])[0]
                            n = net["nodes"].get(nid, {})
                            deps = corpus_content_dependencies(net, nid)
                            spine_rec = next((s for s in net.get("spine", []) if s["id"] == nid), None)
                            cites = [{"id": "ref:" + k, "essence": net["nodes"]["ref:" + k].get("essence")}
                                     for k in net.get("edge_index", {}).get(nid, [])
                                     if "ref:" + k in net["nodes"]]
                            proj = n.get("projection") or {}
                            self._send(200, json.dumps({
                                "id": nid, "kind": n.get("kind"), "grade": n.get("grade"),
                                "essence": n.get("essence"), "keywords": n.get("keywords"),
                                "postulate": nid in net.get("postulates", set()),
                                "spine": spine_rec, "ctx": net.get("ctx", {}).get(nid, ""),
                                "cites": cites, "deps": deps,
                                # emit-time slots for the shared inspector (term, latex_label,
                                # retired + reason, provenance) — additive, view-only
                                "projection": proj,
                                "retired": bool(n.get("retired") or proj.get("retired")),
                            }, ensure_ascii=False))
                        elif u.path == "/corpus/meta":
                            ns = net["nodes"]
                            from collections import Counter as _C

                            from laplace.pipeline import growth as _growth
                            n_friction = len(_ci.friction_current(_ci.rewire_list(rr, name)))
                            self._send(200, json.dumps({
                                "corpus": name, "root": net["root"], "n_nodes": len(ns),
                                "kinds": dict(_C(n["kind"] for n in ns.values() if n["leaf"])),
                                "grades": dict(_C(n["grade"] for n in ns.values())),
                                "n_gaps": len(_ci.gaps(net)),
                                # G2 — additive: the growth ladder rung so /conceptric can
                                # render where the project stands (the crank's dead-end
                                # retired). The one growth producer, bound to the registry.
                                "growth": _growth.growth_state(rr, name),
                                "n_friction": n_friction}, ensure_ascii=False))
                        elif u.path == "/corpus/lit-search":
                            # Literature search via scholarly: takes corpus + optional id (use
                            # the node's content) or q (free-text fallback). Returns top-K
                            # candidates the editor's bulk-stage picker can mint into ref: nodes.
                            from laplace.research import lit_search as _ls
                            nid = q.get("id", [""])[0]
                            qtext = q.get("q", [""])[0]
                            try:
                                k = max(1, min(30, int(q.get("k", ["10"])[0] or 10)))
                            except ValueError:
                                k = 10
                            if nid and nid in net["nodes"]:
                                node = dict(net["nodes"][nid])
                                # node carries kind/essence/keywords; pull ctx from the network's
                                # side-table (atomise stores derivation lead-in there)
                                node["ctx"] = net.get("ctx", {}).get(nid, "")
                                out = _ls.query_for_node(node, k=k)
                                out["node_id"] = nid
                            else:
                                out = _ls.query(qtext, k=k)
                            self._send(200, json.dumps(out, ensure_ascii=False))
                        elif u.path == "/corpus/asset":
                            # serve the file backing a fig:/code: node — for the v2 editor's preview
                            # pane. PDF-sourced conceptrics carry the filename inside the essence
                            # (e.g. "method_exact.pdf"); _resolve_asset_for_node parses that hint plus
                            # the per-corpus declared asset roots. Confined to the corpus' allowed dirs.
                            nid = q.get("id", [""])[0]
                            if not (nid.startswith("fig:") or nid.startswith("code:")):
                                self._send(404, json.dumps({
                                    "error": "asset resolves fig: / code: nodes only"}))
                            else:
                                node = net["nodes"].get(nid)
                                asset = _resolve_asset_for_node(troot, name, nid, node)
                                if asset is None:
                                    self._send(404, json.dumps({"error": "asset not found",
                                                                "id": nid}))
                                else:
                                    ctype = {".pdf": "application/pdf", ".png": "image/png",
                                             ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                                             ".svg": "image/svg+xml", ".webp": "image/webp",
                                             ".gif": "image/gif",
                                             ".py": "text/plain; charset=utf-8",
                                             ".jl": "text/plain; charset=utf-8",
                                             ".js": "text/plain; charset=utf-8",
                                             ".ts": "text/plain; charset=utf-8",
                                             ".sh": "text/plain; charset=utf-8",
                                             ".m":  "text/plain; charset=utf-8",
                                             ".r":  "text/plain; charset=utf-8",
                                             }.get(asset.suffix.lower(), "application/octet-stream")
                                    self._send(200, asset.read_bytes(), ctype)
                        else:
                            self._send(404, json.dumps({"error": "not found"}))
            # /manuscript/provenance + /manuscript/asset removed (Chrome Census W0 kill:
            # zero live consumers; served the retired /editor polymorphic viewer, now 410).
            # /feedback (GET) removed (Chrome Census W2 kill: ZERO live consumer — surfaces
            # use /projection/feedback + /corpus/feedback; excision rides the review consolidation).
            elif (u.path == "/surface/contract" or u.path == "/growth"
                  or u.path.startswith("/growth/")):
                # THE GROWTH COCKPIT's data doors (E2): the composed brief + the six read
                # doors + the /surface/contract route. Delegated to the growth_surface
                # handler (the storyboard/desk idiom); its POST verbs ride do_POST.
                from laplace.web import growth_surface as _gs
                res = _gs.handle(u.path, q, "GET", b"")
                if res is not None:
                    st, ct, pl = res
                    self._send(st, pl, ct)
                else:
                    self._send(404, json.dumps({"error": "not found"}))
            elif u.path == "/conceptric/map":
                # THE READ-AND-RULE STOCK MAP, retained as an altitude reachable from the
                # cockpit brief (the graded descent surface, not foregrounded).
                self._send(200, _CONCEPTRIC_MAP.read_bytes(), "text/html; charset=utf-8")
            elif u.path.startswith("/network/"):
                # RETIRED (W5 chrome census kill, ACT5/job2): the whole /network/* family —
                # zero front-end consumers (grep of every html/js/mjs found none; the map
                # surface's own reads are /graph, /grades, /pulse, /ring, kept live below).
                # The self-model network those routes served is at /graph, /grades, /ring
                # (the Map surface) instead. Collapsed from 10 individual branches to one
                # prefix match — the /editor idiom, one 410 naming the real destination.
                self._send(410,
                           "410 Gone — /network/* is retired (zero front-end consumers). "
                           "The self-model network is served by /graph, /grades, /ring "
                           "(the Map surface) instead.",
                           "text/plain; charset=utf-8")
            elif u.path == "/probe":
                # RETIRED (W5 chrome census kill): zero front-end consumers. wake.py calls
                # process_health.probe() directly, in-process — never over this HTTP door.
                self._send(410, "410 Gone — /probe is retired (zero front-end consumers). "
                           "Call `laplace.engine.process_health.probe()` in-process instead.",
                           "text/plain; charset=utf-8")
            elif u.path == "/wake":
                # RETIRED (W5 chrome census kill): zero front-end consumers. `python3
                # scripts/wake.py` (THE wake, per CLAUDE.md) reconstructs the same payload
                # in-process — never over this HTTP door.
                self._send(410, "410 Gone — /wake is retired (zero front-end consumers). "
                           "Run `python3 scripts/wake.py` instead.",
                           "text/plain; charset=utf-8")
            elif u.path == "/soul/census":
                # RETIRED (W5 chrome census kill): zero front-end consumers.
                self._send(410, "410 Gone — /soul/census is retired (zero front-end consumers).",
                           "text/plain; charset=utf-8")
            elif u.path == "/bench/run":
                # RETIRED (W5 chrome census kill): zero front-end consumers.
                self._send(410, "410 Gone — /bench/run is retired (zero front-end consumers).",
                           "text/plain; charset=utf-8")
            elif u.path == "/bench/rows":
                # RETIRED (W5 chrome census kill): zero front-end consumers.
                self._send(410, "410 Gone — /bench/rows is retired (zero front-end consumers).",
                           "text/plain; charset=utf-8")
            elif u.path == "/cockpit/state":
                self._send(200, json.dumps(cockpit_state(), ensure_ascii=False))
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            if u.path.startswith(("/authoring/", "/research/", "/references/", "/formal/", "/projects/", "/work/", "/concepts/", "/visuals/")):
                # All writing mutations inherit one same-origin deliberate-action
                # boundary; an arbitrary website cannot launch a model/experiment.
                if self.headers.get("X-Laplace-Writing") != "1":
                    self._send(403, json.dumps({"error": "Missing writing-client header."}))
                    return
                if u.path == '/projects/material-intake/upload':
                    from laplace.projects import material_intake
                    try:
                        connection=getattr(self,'connection',None)
                        previous_timeout=connection.gettimeout() if connection is not None else None
                        try:
                            if connection is not None:connection.settimeout(30)
                            body=material_intake.read_upload_body(self.headers,self.rfile)
                        finally:
                            if connection is not None:connection.settimeout(previous_timeout)
                        query=parse_qs(u.query)
                        metadata=json.loads(material_intake.library._q1(query,'request') or '{}')
                        if self.headers.get('Content-Type') != metadata.get('media_type'):
                            raise material_intake.IntakeRefusal('INTAKE_CONTENT_TYPE','Content-Type must match the chosen closed media.')
                        project=material_intake.library._q1(query,'project')
                        from laplace.writing import turn_jobs
                        with turn_jobs.http_mutation(u.path,project):
                            result=material_intake.http(u.path,query,'POST',body,_repo_root())
                    except material_intake.IntakeRefusal as exc:
                        result=material_intake.library._response(exc.http_status,exc.body())
                    except OSError:
                        result=material_intake.library._response(400,{'error':'The upload did not complete within its bounded transport.','code':'INTAKE_FRAMING','intake_admission':'NOT_ADMITTED_THIS_INVOCATION'})
                    except (ValueError,TypeError) as exc:
                        result=material_intake.library._response(422,{'error':str(exc)[:500],'code':'INTAKE_METADATA','intake_admission':'NOT_ADMITTED_THIS_INVOCATION'})
                    self.close_connection=True
                    self._send(result[0],result[2],result[1])
                    return
                length = int(self.headers.get("Content-Length") or 0)
                if length > 2 * 1024 * 1024:
                    self._send(413, json.dumps({"error": "Request is too large."}))
                    return
                body = self.rfile.read(length)
                from laplace.web import authoring as authoring_surface, research_surface, project_work_surface
                from laplace.research import references_surface, formal_surface, concepts as concepts_surface, visuals_surface
                from laplace.projects import library as writing_projects
                from laplace.writing import turn_jobs
                owner = {"authoring": authoring_surface, "research": research_surface,
                         "references": references_surface, "formal": formal_surface,
                         "projects": writing_projects, "work": project_work_surface,
                         "concepts": concepts_surface, "visuals": visuals_surface}[u.path.split("/")[1]]
                query=parse_qs(u.query)
                try:
                    posted=json.loads(body or b"{}")
                except (ValueError,TypeError):
                    posted={}
                raw_project=query.get("project","")
                query_project=(raw_project[0] if isinstance(raw_project,list) and raw_project else raw_project)
                mutation_project=str((posted.get("project") if isinstance(posted,dict) else "") or query_project or "")
                with turn_jobs.http_mutation(u.path,mutation_project):
                    result = _writing_response(owner, u.path, query, "POST", body)
                if result is not None:
                    status, ctype, payload = result
                    self._send(status, payload, ctype)
                    return
                self._send(404, json.dumps({"error": "Unknown writing operation."}))
                return
            if u.path.startswith("/front/"):
                # THE ASK-DOOR (front door M2 slice). Cross-site form POSTs cannot
                # carry a custom header without a CORS preflight this server never
                # grants — so the header IS the same-origin proof (no cookies, no
                # token store). The page's own JS sends it; curl adds it knowingly.
                if self.headers.get("X-Front-Door") != "1":
                    self._send(403, json.dumps(
                        {"error": "missing X-Front-Door header - the front door's "
                                  "own page (or a deliberate curl) is the only caller"}))
                    return
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(min(length, 64 * 1024)) if length else b""
                q = parse_qs(u.query)
                from laplace.web import front_door as _front
                res = _front.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
                self._send(404, json.dumps({"error": "no such front-door verb"}))
                return
            if u.path == "/artefact" or u.path.startswith("/artefact/"):
                # THE ARTEFACT SURFACE is READ-ONLY (its mode producers ride the re-housed
                # /projection/* + /review/* POSTs); artefact.handle 405s every POST honestly.
                from laplace.web import artefact as _af
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _af.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/projection" or u.path.startswith("/projection/"):
                from laplace.manuscript import projection_viewer as _pv
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _pv.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/storyboard" or u.path.startswith("/storyboard/"):
                # the storyboard's plan-write + rebuild endpoints. Delegated BEFORE the
                # POST allowlist, exactly like /projection, so it owns its own writes.
                from laplace.manuscript import storyboard as _sb
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _sb.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/lineage/"):
                # THE LINEAGE SURFACE's one write door: POST /lineage/reindex mints the
                # per-project node_index.json (derived state — it overwrites only that file).
                # Delegated BEFORE the POST allowlist, like /storyboard.
                from laplace.web import lineage_surface as _lin
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _lin.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/review" or u.path.startswith("/review/"):
                # the review viewer's POST endpoints (the one-click map rebuild).
                # Delegated BEFORE the POST allowlist, like /storyboard.
                from laplace.manuscript import review_surface as _rv
                from laplace.web import review_http
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = review_http.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path in ("/dials/run-flip", "/dials/run-restore"):
                # KILLED ON SIGHT (the S0 census, 2026-08-24 + the Ego's directive
                # under the interface seat's refusal row): two write-capable verbs
                # named in NO declaration's reason and called by NOTHING in the tree
                # — a live undeclared write is an open door, not a disposition
                # question. The in-process functions (dials_run_flip/_restore)
                # remain importable; only the unowned HTTP door dies.
                self._send(410, json.dumps(
                    {"error": "410 Gone - killed on sight (undeclared write verb; "
                              "S0 census 2026-08-24; see contract/tombstones.yaml)"}))
                return
            if u.path == "/dials" or u.path.startswith("/dials/"):
                # the dials conjugate's WRITE endpoints (/dials/op, /dials/undo).
                # Delegated BEFORE the POST allowlist, like /storyboard, so it owns
                # its own writes (validate-before-persist, atomic replace).
                from laplace.web import dials_surface as _ds
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _ds.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/evolution/"):
                # THE EVOLUTION DESK's action doors: ratify (his word — armed,
                # attributed, fires the transactional apply + retires the intent),
                # hold (a typed DEFER), reject (revocation without apply). The
                # draft-only law holds: this is the ONE apply path, and it fires
                # only from an attributed, armed POST through his own cockpit.
                from laplace.web import evolution_surface as _ev
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _ev.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/selection/"):
                # THE SELECTION DESK's ruling door (P3): POST /selection/rule banks his
                # word on ONE heredity generation (promote/hold/retire) — armed,
                # attributed, ONE append-only selection-ruling record. Record-only: it
                # mutates NO artifact (heredity's promote/retire mechanics read it
                # later); a later ruling on the same generation contests it.
                from laplace.web import selection_surface as _sel
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _sel.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/derivation/"):
                # THE DERIVATION FACE's act doors (2026-07-21): rescope (re-scope the
                # boundary claim by APPENDED revision — the prior banks to
                # aspiration_history.jsonl, aspiration.json stays the latest-pointer),
                # forge (bank a model-heavy work-order for a GAP link — the offer law),
                # contest (append a contest record; the link's status is carried
                # UNCHANGED, last-wins reads unaffected until re-attestation). Each
                # armed + attributed, ONE append-only record, a lock around
                # check-then-append. Delegated BEFORE the POST allowlist, like /selection.
                from laplace.web import derivation_surface as _der
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _der.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/desk" or u.path.startswith("/desk/"):
                # THE DESK ACT DOOR (W5): the desk is read-only EXCEPT the one mutation
                # door POST /desk/act, each verb a thin dispatch to an existing executor.
                # Delegated BEFORE the POST allowlist, like /review; desk.handle 405s
                # every other /desk POST.
                from laplace.web import desk as _dk
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _dk.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/assets" or u.path.startswith("/assets/"):
                # THE ASSET SURFACE (W7) is READ-ONLY except two thin POST doors: assess
                # (bank a step/panel-anchored finding through manuscript_bridge.feedback_add,
                # the ONE finding writer) and regen (bank a MANIFEST-ONLY work-order, the
                # bank_work_order idiom). Delegated BEFORE the POST allowlist, like /desk;
                # assets_surface.handle 405s every other /assets POST.
                from laplace.web import assets_surface as _as
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _as.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/growth" or u.path.startswith("/growth/"):
                # THE GROWTH COCKPIT's ruling door (E2): POST /growth/rule banks one of the
                # four tension verbs — actor-guarded, one write, the false-ruling refusal on
                # the posted fingerprint. Delegated BEFORE the POST allowlist, like /desk.
                from laplace.web import growth_surface as _gs
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _gs.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path.startswith("/dashboard/"):
                # W1 THE NEW PROJECT DOOR (J6): POST /dashboard/new banks a scaffold
                # (dirs + conceptric seed + plan skeleton + registry_projects.json row)
                # and BANKS the heavy steps as work-orders — never fires inline.
                from laplace.web import dashboard as _dash
                q = parse_qs(u.query)
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                res = _dash.handle(u.path, q, "POST", body)
                if res is not None:
                    status, ctype, payload = res
                    self._send(status, payload, ctype)
                    return
            if u.path == "/bench/add":
                # RETIRED (W5 chrome census kill): zero front-end consumers.
                self._send(410, "410 Gone — /bench/add is retired (zero front-end consumers).",
                           "text/plain; charset=utf-8")
                return
            # POST /fire is KEPT (ACT5/job2's live-consumer escape clause): zero front-end
            # (html/js/mjs) consumer, but scanner.client_fire — a real Python-side conjugate
            # — POSTs here from scripts/ingest_collaborators.py and scripts/ingest_soul_dump.py
            # so the author's open scanner page can watch a long ingest fire live; killing it
            # would silently degrade that telemetry. GET /firings (the poll half of the same
            # pair) is kept alongside it for the same reason.
            if u.path not in ("/fire", "/cockpit/state",
                              "/corpus/rewire", "/corpus/feedback",
                              "/corpus/friction"):
                self._send(404, json.dumps({"error": "not found"}))
                return
            length = int(self.headers.get("Content-Length", 0))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send(400, json.dumps({"error": "bad json"}))
                return
            if u.path == "/corpus/rewire":
                from laplace.research import corpus_ingest as _ci
                name = payload.get("corpus") or _ci.default_corpus(_repo_root())
                self._send(200, json.dumps(_ci.rewire_add(_repo_root(), name, payload),
                                           ensure_ascii=False))
                return
            if u.path == "/corpus/friction":
                # the D16 rule-in-place door (his steer, 2026-07-16): the interface's
                # capture banks through the ONE sanctioned friction gate — typed,
                # draft-only (status: open), never a bare append.
                # THE ACTOR LAW (W-HANDS): the door never DEFAULTS the writer — an
                # unattributed capture is a 422, his name never a silent default. (The
                # friction_add Python door keeps its by="eigen" fallback for the drain/
                # sweep callers that name themselves; only THIS HTTP door refuses.)
                from laplace.research import corpus_ingest as _ci
                if not str(payload.get("by") or "").strip():
                    self._send(422, json.dumps({"error": "by (explicit actor) is required "
                                                "— a friction/fork capture is attributed, never defaulted"}))
                    return
                name = payload.get("corpus") or _ci.default_corpus(_repo_root())
                self._send(200, json.dumps(_ci.friction_add(_repo_root(), name, payload),
                                           ensure_ascii=False))
                return
            if u.path == "/corpus/feedback":
                # bank a node comment into the corpus' ONE manuscript ledger (same
                # file the projection viewer's review mode writes) - a comment on a
                # node is review signal, never an alternative to editing the essence
                # THE ACTOR LAW (W-HANDS): the door never DEFAULTS the writer — an
                # unattributed comment is a 422, his name never a silent default. (The
                # feedback_add Python door keeps its by="eigen" fallback for callers
                # that already name themselves; only THIS HTTP door refuses.)
                from laplace.research import corpus_ingest as _ci
                from laplace.manuscript import manuscript_bridge as _mb
                if not str(payload.get("by") or "").strip():
                    self._send(422, json.dumps({"error": "by (explicit actor) is required "
                                                "— a feedback comment is attributed, never defaulted"}))
                    return
                name = payload.get("corpus") or _ci.default_corpus(_repo_root())
                led = _corpus_feedback_ledger(_repo_root(), name)
                if led is None:
                    self._send(404, json.dumps({"error": f"corpus {name} has no plan/target_dir"}))
                    return
                payload.setdefault("project", name)
                self._send(200, json.dumps(
                    _mb.feedback_add(_repo_root(), name, payload, ledger=led), ensure_ascii=False))
                return
            # /feedback + /feedback/resolve (POST) removed (Chrome Census W2 kill: ZERO live
            # consumer — surfaces bank through /projection/feedback + /corpus/feedback).
            # /bench/add (POST) removed (W5 chrome census kill: ZERO live consumer; 410'd above
            # the allowlist check, like /editor).
            if u.path == "/cockpit/state":
                self._send(200, json.dumps(cockpit_state(payload), ensure_ascii=False))
                return
            goal = payload.get("goal", "")
            by = payload.get("by", "author")
            kind = payload.get("kind", "route")
            grade = payload.get("grade", None)
            nodes = payload.get("nodes") or None
            if not (goal or "").strip():
                self._send(400, json.dumps({"error": "empty goal"}))
                return
            rec = _FIRINGS.append(fire(goal, by, kind=kind, grade=grade, nodes=nodes))
            # the spine rides every fire (his "always top of mind"): the seeded/learned
            # calls-to-make for a goal of this shape, attached AFTER the feed is persisted
            # (the disk line stays lean; only the live response carries the reflex).
            try:
                from laplace.engine import spine
                rec = {**rec, "spine": spine.top_of_mind(_repo_root(), goal)}
            except Exception:  # noqa: BLE001 - the spine is a guide; a fire never fails on it
                pass
            self._send(200, json.dumps(rec))

        # THE TRAFFIC LEDGER'S THREE POINTS (writing/traffic.py): the socket writer counts every accepted and
        # failed write against the current exchange; the status is kept when it is sent; the exchange ends
        # with that status after the request returns (an event stream ends when it closes).
        _exchange = None
        _status = None

        def setup(self) -> None:
            super().setup()
            from laplace.web import traffic
            self.wfile = traffic.CountingWriter(self.wfile, lambda: self._exchange)

        def send_response(self, code, message=None) -> None:
            self._status = code
            super().send_response(code, message)

        def handle_one_request(self) -> None:
            self._exchange, self._status = None, None
            try:
                super().handle_one_request()
            finally:
                if self._exchange is not None:
                    from laplace.web import traffic
                    try:
                        traffic.end(self._exchange, self._status)
                    except Exception:
                        traffic.observer_failed()
                    self._exchange = None

        def log_message(self, *a) -> None:  # keep the console quiet
            pass

    return Handler


def _prewarm() -> None:
    """Warm the whole fire path off the request thread: the unified graph, the network build,
    the embedding model load (seconds, once per process), and the vector cache. The first REAL
    fire then costs milliseconds - the frictionless rule: the warm process pays the startup,
    never the moment.

    The graph goes first because a page waits on it: /map fetches ``/graph?source=all`` at boot
    and cannot paint until it answers. Cold, that build takes ~17s on the current tree (measured
    by curl against a freshly started server), which is inside a browser's navigation budget only
    if the request thread is not also paying it. Warming here moves the cost to process startup.
    """
    if os.environ.get("LAPLACE_NO_PREWARM") == "1":
        return

    try:
        # THE ATLAS BOARD FIRST, and on its own thread. It is the surface his S0 walk
        # lands on, and its build() reads six ledgers plus a full conceptric replay
        # (~9s cold). front_door is imported lazily inside the /front dispatch, so
        # without this the first person through the door pays it — and the first person
        # is him. It races the graph build below rather than queuing behind the embedder,
        # because a human waiting at a door is a worse cost than a warm vector cache.
        try:
            from laplace.web import front_door as _fd
            from laplace.web import front_places as _places

            # The places census has one expensive member (the verified fabric replay).
            # Start it beside the atlas receipt so the first /front/places request never
            # becomes the cold-path exception to the no-tollbooth law.
            _places.prewarm()
            _fd.prewarm_atlas()
        except Exception as exc:  # noqa: BLE001 - never take the door down to warm it
            print(f"scanner: atlas pre-warm skipped ({exc})", flush=True)

        from laplace.representation import embed_router
        graph_for("all")
        print("scanner: pre-warm done (unified graph)", flush=True)
        net = _network()
        backend = embed_router.get_backend()
        if backend is not None:
            embed_router.ensure_embeddings(_repo_root(), net, backend)
        print("scanner: pre-warm done (network + embedder + vectors)", flush=True)
    except Exception as exc:  # noqa: BLE001 - pre-warm is a convenience, never a crash
        print(f"scanner: pre-warm skipped ({exc})", flush=True)


#: the two reads the health door admits (declared 'authoring/health'); its refusals name them
_HEALTH_READS = [{"method": "GET", "url": "/authoring/health", "returns": "laplace.writing-health/2"},
                 {"method": "GET", "url": "/authoring/health?view=traffic", "returns": "laplace.writing-traffic/1", "clients": "loopback"}]


def _health_view(u) -> str:
    """The health door's admitted view: "ordinary" (no query) or "traffic". The query is admitted against the
    declared payload schema of 'authoring/health' (one value per key, blanks kept); any other shape (an unknown
    or repeated key, a blank or unknown view, a view mixed with another key) raises ValueError."""
    query = parse_qs(u.query, keep_blank_values=True)
    if not query:
        return "ordinary"
    repeated = sorted(key for key, values in query.items() if len(values) != 1)
    if repeated:
        raise ValueError("Each health selector appears at most once; repeated: " + ", ".join(repeated[:4]) + ".")
    from jsonschema import Draft202012Validator
    from laplace.native.declarations import HTTP_DECLARATIONS
    value = {key: values[0] for key, values in query.items()}
    errors = sorted(Draft202012Validator(HTTP_DECLARATIONS["authoring/health"].payload).iter_errors(value), key=str)
    if errors:
        raise ValueError("The health door admits no query or exactly view=traffic: " + errors[0].message[:160])
    return value.get("view") or "ordinary"


def _health_refusal(reason: str) -> dict:
    return {"error": reason, "recovery": _HEALTH_READS,
            "help": {"operation": "help", "payload": {"route": "/authoring/health", "method": "GET"}}}


def _traffic_view(u) -> bool:
    """Whether this request is an ADMITTED traffic read (a diagnostic self-read of the ledger)."""
    if u.path != "/authoring/health":
        return False
    try:
        return _health_view(u) == "traffic"
    except ValueError:
        return False


def _traffic_begin(handler):
    """Open the ledger exchange of one parsed request: its bounded route key, never its query or body.
    Observational: any failure of the observer is counted and the request proceeds unattributed."""
    from laplace.web import traffic
    try:
        u = urlparse(handler.path)
        return traffic.begin(handler.command, u.path, diagnostic=_traffic_view(u),
                             content_length=handler.headers.get("Content-Length"))
    except Exception:
        traffic.observer_failed()
        return None


class _EngineServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer performs a reverse-DNS lookup solely to fill server_name.
        # A loopback workspace must start even when the host resolver stalls.
        from socketserver import TCPServer
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def handle_error(self, request, client_address):  # noqa: N802
        # a disconnecting client is not an error in the engine - only real
        # faults reach the log, and none of them reach the process
        import sys

        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def serve(port: int = 8770, host: str = "127.0.0.1", *, writing: bool = False,
          repo_root: Path | str | None = None) -> None:
    if repo_root is not None:
        os.environ["LAPLACE_REPO_ROOT"]=str(Path(repo_root).resolve())
    shared_assets = None
    source_start = None
    runtime_start = None
    runtime_selection_start = None
    homes_start = workspace_start = None
    if writing:
        os.environ["LAPLACE_WRITING_APP"] = "1"
        from laplace.web import shared_ui
        from laplace.desktop import writing_app
        from laplace.core import runtime as core_runtime
        code_root = _repo_root()
        if os.environ.get('LAPLACE_MANAGED_HOMES'):
            from laplace.core.checkout import source_tree
            from laplace.desktop import managed_homes
            homes_start = json.loads(os.environ['LAPLACE_MANAGED_HOMES'])
            expected_homes = managed_homes.resolve(homes_start['code_root'], state=homes_start['receipt'],
                workspace_root=homes_start['workspace_root'], engine_state=homes_start['engine_state'],
                session_workspaces=homes_start['session_workspaces'])
            if (homes_start != expected_homes or Path(homes_start['code_root']) != source_tree()
                    or Path(homes_start['workspace_root']) != _repo_root()
                    or os.environ.get('LAPLACE_STATE') != homes_start['engine_state']
                    or os.environ.get('LAPLACE_SESSION_WORKSPACES') != homes_start['session_workspaces']):
                raise writing_app.WritingAppError('Managed source/data/state selection disagrees with actual imported source')
            code_root = Path(homes_start['code_root'])
            workspace_start = managed_homes.workspace_snapshot(_repo_root())
            expected_workspace = os.environ.get('LAPLACE_WRITING_EXPECTED_WORKSPACE')
            if expected_workspace and workspace_start['identity'] != expected_workspace:
                raise writing_app.WritingAppError('Workspace configuration changed before startup')
        source_start = writing_app.source_snapshot(code_root)
        runtime_start = core_runtime.receipt()
        if os.environ.get("LAPLACE_WRITING_STATE"):
            runtime_selection_start = core_runtime.selection_basis(code_root)
            expected_selection=os.environ.get("LAPLACE_WRITING_EXPECTED_SELECTION")
            if expected_selection and runtime_selection_start["identity"] != expected_selection:
                raise writing_app.WritingAppError("Managed runtime selection changed before service startup")
            if (runtime_start["executable"] != runtime_selection_start["resolved"]
                    or runtime_start["version"] != runtime_selection_start["expected_python"]):
                raise writing_app.WritingAppError("Managed service runtime disagrees with selection")
        expected = os.environ.get("LAPLACE_WRITING_EXPECTED_SOURCE")
        if expected and source_start["identity"] != expected:
            raise writing_app.WritingAppError("Workspace source changed before service startup")
        shared_assets = shared_ui.capture_asset_snapshot()
        if writing_app.source_identity(code_root) != source_start["identity"]:
            raise writing_app.WritingAppError("Workspace source changed during service startup")
        if runtime_selection_start and core_runtime.selection_basis(code_root)["identity"] != runtime_selection_start["identity"]:
            raise writing_app.WritingAppError("Managed runtime selection changed during service startup")
        if homes_start and managed_homes.workspace_snapshot(_repo_root()) != workspace_start:
            raise writing_app.WritingAppError('Workspace configuration changed during startup')
    httpd = _EngineServer((host, port), make_handler(shared_assets=shared_assets, source_start=source_start,
                         runtime_start=runtime_start,runtime_selection_start=runtime_selection_start,
                         managed_homes_start=homes_start, workspace_start=workspace_start))
    if not writing:
        threading.Thread(target=_prewarm, daemon=True).start()

    if not writing and os.environ.get("LAPLACE_TEST_PROCESS") != "1":
        from laplace.web.conversation_serve import run_broker

        threading.Thread(
            target=run_broker,
            name="laplace-conversation-broker",
            daemon=True,
        ).start()
    print(f"the eigen engine: http://{host}:{port}", flush=True)
    httpd.serve_forever()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Laplace brain scanner - the live conceptric viewer.")
    p.add_argument("--port", type=int, default=8770)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--writing", action="store_true", help="On-demand writing app: no prewarm, broker or embeddings at startup")
    p.add_argument("--repo-root",type=Path,help="Explicit checkout containing registry, projects and profiles")
    args = p.parse_args(argv)
    serve(args.port,args.host,writing=args.writing,repo_root=args.repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
