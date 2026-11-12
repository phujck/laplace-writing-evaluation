"""The altitude tower — one substrate viewed at rising altitudes.

The north star (his, 2026-07-08): *one substrate viewed at rising altitudes
(nodes -> grade-shells -> spine -> plan -> prose), the manuscript just the top
skin; a viewer where the wiring-back through every layer is transparent.* This
module is the PAPER-corpus altitude view — the read-only complement to the
navigator (which instruments the engine self via ``/network/*``). It never
writes: the ruling verbs live in ``/review``; the plan edits live in
``/storyboard``. Altitude only *looks*.

The one navigation, four altitudes, opened AT an anchor and shiftable up/down:

  0. **NODES**        — the anchor's nodes (kind / essence / edges) + 1-hop
                        neighbourhood.
  1. **GRADE-SHELLS** — the same nodes organised BY ``dep_grade`` (grade-0 atoms
                        at the floor, the spine at ``g_max``). This is grading
                        made load-bearing: the grade is computed LIVE from the
                        network (``corpus_ingest.dep_grade`` — derived, never
                        stored, per DECISION_2026-07-10) and rendered navigable,
                        with each node's derivation (its grade-setting deps)
                        exposed on demand and stored-vs-derived divergence
                        surfaced plainly.
  2. **SPINE**        — the anchor's beats on the conceptric spine rail (REUSED
                        from ``storyboard.enriched_plan`` — not rebuilt).
  3. **PLAN / PROSE** — the owning plan section + the materialized prose skin,
                        marked stale-aware (a compile stamp, a plain
                        "rebuild to refresh"; never a live-reflow pretense).

Every layer carries its JOIN KEY to the layer below — the wiring-back clause:
``pid -> node ids -> grades -> beats -> section -> artefact page`` — so the climb
is transparent at every altitude.

The anchor is a ``pid`` (a paragraph id, ``N5-p2``), a ``section`` (a plan
section id, ``N5``), or a ``node`` (a conceptric node id, ``def:staircase``).
The route contract B-4's trace-up honours is exactly ``GET /altitude?corpus=&anchor=``
(a dir-based review with no ``?corpus=`` passes ``?dir=`` instead — the dir
reverse-resolves to its registered corpus key through the same registry fence).
"""

from __future__ import annotations
from laplace.core.checkout import package_root
from laplace.core.checkout import source_tree

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

# The anchor shapes. A pid is a section id followed by ``-p<N>`` (the realiser's
# paragraph marker, ``% N5-p2``); a section is a bare plan section id (``N5`` /
# ``NA1``); anything carrying a ``:`` is a conceptric node id (every node kind
# prefix — def/res/irf/thm/ds/goal/fork — uses one, and node ids never do
# otherwise). Detection is ordered pid -> section -> node.
_PID_RE = re.compile(r"^(N[A-Z]?\d+)-p\d+$")
_SECTION_RE = re.compile(r"^N[A-Z]?\d+$")

_HTML = package_root() / "web" / "altitude.html"   # the page is the HTTP adapter's resource

# per-shell cap on the GLOBAL membership sample (the anchor's own nodes are never
# capped). His no-silent-caps rule: the omitted count always rides in a sibling
# ``global_truncated`` field, never a silent drop.
_SHELL_SAMPLE_CAP = 24


def _repo_root() -> Path:
    return source_tree()


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key)
    if isinstance(v, list):
        return v[0] if v else default
    return v if v is not None else default


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, "application/json; charset=utf-8", json.dumps(obj).encode("utf-8")


def detect_anchor(anchor: str) -> dict[str, Any]:
    """Classify an anchor string into (kind, section, node). ``kind`` is one of
    ``pid`` / ``section`` / ``node`` / ``None`` (empty anchor -> the whole tower,
    nothing highlighted)."""
    a = (anchor or "").strip()
    if not a:
        return {"raw": a, "kind": None, "section": None, "node": None}
    m = _PID_RE.match(a)
    if m:
        return {"raw": a, "kind": "pid", "section": m.group(1), "node": None}
    if _SECTION_RE.match(a):
        return {"raw": a, "kind": "section", "section": a, "node": None}
    # anything else is treated as a node id (the ``:``-bearing shape, and a
    # graceful fallback for an unrecognised token — it simply resolves to
    # ``missing`` downstream rather than 400ing).
    return {"raw": a, "kind": "node", "section": None, "node": a}


def section_nodes(target_dir: Path) -> dict[str, list[str]]:
    """``{section id: [node ids]}`` read from the ``% NODES`` markers of each
    projected ``N*.tex`` in the target dir. The marker is the prose->node join —
    the ground truth of what each section actually pinned. Reuses
    ``projection_viewer.parse_map`` (the one % PLAN/% NODES parser) rather than
    re-deriving the grammar."""
    from laplace.manuscript import projection_viewer as pv
    out: dict[str, list[str]] = {}
    if not target_dir or not target_dir.is_dir():
        return out
    for f in sorted(target_dir.glob("N*.tex")):
        try:
            spans = pv.parse_map(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        seen: dict[str, None] = {}
        for s in spans:
            for n in s.get("nodes", []):
                seen.setdefault(n, None)
        out[f.stem] = list(seen)
    return out


def _grade_contributions(net: dict) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Reproduce ``corpus_ingest.dep_grade``'s EXACT memoised, cycle-guarded DFS and
    record, per node, the depth each dependency CONTRIBUTED at the moment the node's
    derivational depth was finalised. Returns ``(depth, contrib)`` where
    ``depth[nid]`` equals ``dep_grade``'s pre-elevation ``dep_depth`` (verified
    node-for-node) and ``contrib[nid][d]`` is what dep ``d`` gave ``nid``.

    Why this is needed for coherence: the derivation DAG carries cycles (the guard
    in ``dep_grade`` exists precisely for them). For a dependency on a cycle THROUGH
    ``nid`` the recursion breaks the back-edge to 0, so that dep's contribution here
    is LESS than its own final ``dep_depth`` — which is exactly why the naive
    ``grade = 1 + max(dep dep_depth)`` fails to reconcile for ~40 nodes (e.g.
    ``res:classical-hardness-frontier`` grade 22 cites ``thm:…-advantage`` whose own
    depth is 24 but which contributed 0 as a broken back-edge). Reading the setter
    and the rule off the CONTRIBUTED depth makes the arithmetic land on the shown
    grade for all 494 nodes. The result is cached on ``net`` as an explicit derived
    read model; ``dep_grade`` itself does not mutate canonical cached nodes.
    """
    cached = net.get("_grade_contrib")
    if cached is not None:
        return cached
    from laplace.research import corpus_ingest as ci
    nodes = net.get("nodes", {})
    post = net.get("postulates", set())
    memo: dict[str, int] = {}
    contrib: dict[str, dict[str, int]] = {}

    def g(nid: str, stack: frozenset) -> int:
        if nid in memo:
            return memo[nid]
        if nid in stack:            # cycle back-edge — broken to 0, exactly as dep_grade
            return 0
        deps = ci.inferential_dependencies(net, nid)
        if nid in post or not deps:
            memo[nid] = 0
            return 0
        c = {d: g(d, stack | {nid}) for d in deps}
        contrib[nid] = c
        memo[nid] = max(0, 1 + max(c.values(), default=-1))
        return memo[nid]

    for nid in nodes:               # same iteration order as dep_grade -> same memo
        g(nid, frozenset())
    net["_grade_contrib"] = (memo, contrib)
    return memo, contrib


def _derivation(net: dict, dg: dict[str, int], nid: str) -> dict[str, Any]:
    """The load-bearing-as-derived view of one node's grade, RECONCILED step by step
    so a reader can redo the arithmetic from exactly what is shown — for every node
    in the corpus, spine consumers and cycle members included.

    The grade is built in the two explicit stages ``corpus_ingest.dep_grade`` uses,
    and the drawer names each:

      1. DERIVATIONAL DEPTH: 0 for a postulate / dependency-free node, else
         ``1 + max(dependency CONTRIBUTED depth)`` — the depth each dep actually gave
         THIS node under dep_grade's cycle-guarded DFS (see ``_grade_contributions``).
         The grade-setter and the ``1 + max`` rule are read off that contributed
         depth, NOT off a dep's spine-ELEVATED display grade and NOT off a dep's own
         final depth. This is the F1 fix: previously the setter/rule came from the
         elevated ``dg``, so ``1 + max(dep grade)`` disagreed with the shown grade for
         the 15-node spine tier and its ~54 consumers; the contributed basis also
         reconciles the ~40 cycle nodes a dep's-own-depth basis would still miss.
      2. SPINE ELEVATION: a spine-tagged node is then lifted to ``g_max``. When that
         lift actually raises the value it is surfaced as its OWN step in ``rule``
         ("… ; spine-elevated to g_max = g"), so the displayed grade never silently
         contradicts the derivational arithmetic.

    Each dependency carries its display ``grade`` (elevated), its own final
    ``dep_depth``, the ``contributed`` depth it gave this node, and ``spine_elevated``
    / ``cycle_broken`` flags — so a reader sees precisely why a high-grade spine dep
    or a high-depth cycle dep did not set a low consumer's grade.
    """
    from laplace.research import corpus_ingest as ci
    nodes = net.get("nodes", {})
    nd = nodes.get(nid) or {}
    post = net.get("postulates", set())
    spine_ids = {s["id"] for s in net.get("spine", [])}
    deps = ci.inferential_dependencies(net, nid)
    depth, contrib = _grade_contributions(net)
    contribs = contrib.get(nid, {})

    def _own_depth(x: str) -> int:
        v = depth.get(x)
        if isinstance(v, int):
            return v
        w = (nodes.get(x) or {}).get("dep_depth")
        return w if isinstance(w, int) else dg.get(x, 0)

    # a postulate is an AXIOM: its grade is 0 by declaration, NOT derived from what it
    # happens to cite — so a postulate that carries edges (a goal citing its
    # substrate, say) is still ``is_free`` and none of its listed deps set its grade.
    is_free = nid in post or not deps
    dep_info = []
    for d in deps:
        own = _own_depth(d)
        contributed = contribs.get(d, 0 if not is_free else own)
        dep_info.append({
            "id": d, "grade": dg.get(d, 0), "dep_depth": own,
            "contributed": contributed,
            "kind": (nodes.get(d) or {}).get("kind"),
            "spine_elevated": d in spine_ids and own < dg.get(d, 0),
            "cycle_broken": contributed < own,   # a back-edge cut to grade this node
        })
    dep_info.sort(key=lambda x: (-x["contributed"], -x["dep_depth"], x["id"]))
    # the grade-setter is the dependency whose CONTRIBUTED depth is deepest — the value
    # dep_grade actually used for THIS node — so ``1 + it`` == the derivational depth
    # shown. A free node derives its grade from no dep, so NOTHING is flagged (else the
    # drawer would show setters under a "depth 0" rule — a fresh incoherence).
    max_contrib = max((d["contributed"] for d in dep_info), default=-1)
    for d in dep_info:
        d["is_grade_setter"] = (not is_free) and d["contributed"] == max_contrib and max_contrib >= 0

    grade = dg.get(nid, 0)
    dep_depth = depth.get(nid)
    if not isinstance(dep_depth, int):  # depth pass unavailable — restate the identity
        dep_depth = 0 if is_free else 1 + max_contrib
    spine_elevated = nid in spine_ids and dep_depth < grade

    if is_free:
        kind = "postulate" if nid in post else "dependency-free"
        base = f"{kind} -> derivational depth 0" + (
            " (its cited deps are references, not grade-setting)" if deps else "")
    else:
        # keep the "grade = 1 + max(dependency …)" headline, over the CONTRIBUTED depth
        # (the honest basis), with the concrete numbers so the arithmetic is visible.
        base = (f"grade = 1 + max(dependency contributed depths) "
                f"= 1 + {max_contrib} = {dep_depth}")
    rule = (f"{base}; spine-elevated to g_max = {grade} "
            "(the spine is the top stratum by convention, not derivation)"
            if spine_elevated else base)

    return {
        "id": nid,
        "grade": grade,
        "dep_depth": dep_depth,
        "stored_grade": nd.get("grade"),
        "is_postulate": nid in post,
        "spine_elevated": spine_elevated,
        "rule": rule,
        "deps": dep_info,
    }


def _short_node(nodes: dict, dg: dict[str, int], nid: str) -> dict[str, Any]:
    nd = nodes.get(nid)
    if nd is None:
        return {"id": nid, "kind": None, "grade": dg.get(nid), "missing": True,
                "essence": None, "section_ref": None}
    proj = nd.get("projection") or {}
    ess = nd.get("essence") or ""
    return {
        "id": nid,
        "kind": nd.get("kind"),
        "grade": dg.get(nid, nd.get("grade")),
        "missing": False,
        "essence": ess if len(ess) <= 320 else ess[:317] + "…",
        "section_ref": proj.get("section_ref"),
        "latex_label": proj.get("latex_label"),
        "retired": bool(nd.get("retired") or proj.get("retired")),
    }


def _artefact_stamp(target_dir: Path, ledger: Path | None) -> dict[str, Any]:
    """The materialized upper half's honesty: the compile stamp + a stale-aware
    diff against the live source. NEVER a live-reflow pretense — the prose skin
    is a projection that goes stale, and this says so with numbers."""
    stamp: dict[str, Any] = {"compiled": False}
    rel = target_dir / "release" / "finalize.json"
    state_p = target_dir / "release" / "state.json"
    created_ts: str | None = None
    if rel.is_file():
        try:
            fin = json.loads(rel.read_text(encoding="utf-8"))
            created_ts = fin.get("created")
            stamp.update({
                "compiled": True,
                "pdf_path": fin.get("pdf_path"),
                "title": fin.get("title"),
                "revision": fin.get("revision"),
                "created": created_ts,
            })
        except (OSError, ValueError):
            pass
    if state_p.is_file():
        try:
            st = json.loads(state_p.read_text(encoding="utf-8"))
            stamp["state"] = st.get("state")
            stamp["state_updated"] = st.get("updated")
        except (OSError, ValueError):
            pass

    # staleness: any source (a projected N*.tex, main.tex, or the friction
    # ledger) whose mtime is newer than the compile stamp means the prose skin
    # no longer reflects the substrate. Report the count and the newest, honestly.
    newer: list[str] = []
    newest_mtime = 0.0
    compiled_mtime = 0.0
    pdf_name = stamp.get("pdf_path")
    for cand in ((target_dir / "main.pdf"),
                 (target_dir / pdf_name) if pdf_name else None):
        if cand and cand.is_file():
            compiled_mtime = max(compiled_mtime, cand.stat().st_mtime)
    sources: list[Path] = list(target_dir.glob("N*.tex")) + [target_dir / "main.tex"]
    if ledger and ledger.is_file():
        sources.append(ledger)
    for s in sources:
        if not s.is_file():
            continue
        mt = s.stat().st_mtime
        newest_mtime = max(newest_mtime, mt)
        if compiled_mtime and mt > compiled_mtime + 1.0:
            newer.append(s.name)
    stamp["staleness"] = {
        "stale": bool(newer),
        "n_newer": len(newer),
        "newer_sources": sorted(newer),
        "note": ("materialized projection — the slow LLM leg does not re-flow live; "
                 + (f"{len(newer)} source(s) changed since compile — rebuild to refresh"
                    if newer else "in sync with source")),
    }
    return stamp


def anchor_node_ids(anchor: dict, sec_nodes: dict[str, list[str]], corpus: str) -> list[str]:
    """The anchor's node set — the join every altitude (and the ladder) keys off. A
    node anchor is its own singleton; a section/pid anchor is its ``% NODES`` set,
    falling back to the plan's declared ``nodes_in_order`` when the section pins no
    ``% NODES`` (N1/N8 — intro/close, written last). Extracted verbatim from
    :func:`resolve` so the tower and the ladder resolve one (corpus, anchor) through
    ONE reader (the up-conjugate's same-node-ids clause)."""
    if anchor["kind"] == "node" and anchor["node"]:
        return [anchor["node"]]
    if anchor.get("section"):
        ids = list(sec_nodes.get(anchor["section"], []))
        if not ids:
            from laplace.manuscript import storyboard as sb
            enriched0 = sb.enriched_plan(corpus) or {}
            for s in (enriched0.get("sections") or []) + (enriched0.get("appendices") or []):
                if s.get("id") == anchor["section"]:
                    return list(s.get("nodes_in_order") or [])
        return ids
    return []


def owning_section(anchor: dict, sec_nodes: dict[str, list[str]],
                   plan_sections: list[dict], node_id: str | None) -> str | None:
    """Which plan section OWNS the anchor: a section/pid anchor names its own
    section; a node anchor resolves to the first section whose ``% NODES`` (or
    plan ``nodes_in_order``) claims it."""
    if anchor.get("section"):
        return anchor["section"]
    if not node_id:
        return None
    for sid, nodes in sec_nodes.items():
        if node_id in nodes:
            return sid
    for s in plan_sections:
        if node_id in (s.get("nodes_in_order") or s.get("nodes") or []):
            return s.get("id")
    return None


def corpus_for_dir(dir_param: str) -> str | None:
    """Reverse-lookup a repo-relative manuscript ``dir`` to its registered corpus
    key, so a dir-based review (``/review?dir=…``) can still address the tower
    (F3). A dir-only review leaves ``?corpus=`` empty, which used to build
    ``/altitude?corpus=&anchor=…`` → a dead 400; resolving the key here lets the
    exact same tower open.

    The SAME registry fence as :func:`resolve`: only a dir that resolves — inside
    the repo root — to a registered project's compiled ``target_dir`` (or its
    manuscript dir) maps to a key; a traversal-shaped or unregistered dir returns
    ``None`` (the caller then degrades plainly, never touching disk on a guess).
    """
    if not dir_param:
        return None
    from laplace.pipeline import registry
    rr = _repo_root().resolve()
    try:
        p = Path(dir_param)
        want = (p if p.is_absolute() else rr / p).resolve()
        want.relative_to(rr)  # fence: an escaping dir never matches
    except (ValueError, OSError):
        return None
    for name, proj in registry.all_projects().items():
        for cand in (proj.resolved_target_dir(rr), proj.path(proj.target_dir, rr),
                     proj.path(proj.manuscript_dir, rr)):
            try:
                if cand is not None and cand.resolve() == want:
                    return name
            except OSError:
                continue
    return None


def resolve(corpus: str, anchor: str) -> dict[str, Any] | None:
    """Build the four-altitude payload for ``corpus`` opened at ``anchor``.
    Returns ``None`` when the corpus is unknown (a registry-fenced name — a
    traversal shape never touches disk)."""
    from laplace.research import corpus_ingest as ci
    from laplace.manuscript import storyboard as sb
    from laplace.pipeline import registry

    proj = registry.resolve(corpus)
    if proj is None:
        return None
    rr = _repo_root()
    troot = ci.resolve_corpus(rr, corpus)
    if troot is None:
        return None
    net = ci.corpus_network(troot, repo_root=rr, name=corpus)
    nodes = net.get("nodes", {})
    dg = ci.dep_grade(net)
    g_max = max(dg.values(), default=0)

    target_dir = proj.path(proj.target_dir, rr)
    ledger = proj.path(proj.ledger, rr) if proj.ledger else None
    sec_nodes = section_nodes(target_dir) if target_dir else {}

    a = detect_anchor(anchor)

    # ── the anchor's node set — the join every altitude keys off (the extracted
    #    shared reader; the ladder resolves the SAME (corpus, anchor) through it) ──
    anchor_ids: list[str] = anchor_node_ids(a, sec_nodes, corpus)

    # ── altitude 0 · NODES ────────────────────────────────────────────────────
    node_cards = [_short_node(nodes, dg, nid) for nid in anchor_ids]
    neighborhood = None
    if a["kind"] == "node" and a["node"] in nodes:
        try:
            neighborhood = ci.neighborhood(net, a["node"])
        except Exception:
            neighborhood = None

    # ── altitude 1 · GRADE-SHELLS (grading made load-bearing) ────────────────
    global_hist = Counter(dg.values())
    stored_hist = Counter(nd.get("grade") for nd in nodes.values()
                          if nd.get("grade") is not None)
    # a stable ordering of every node by grade, so the shell sample is deterministic
    by_grade: dict[int, list[str]] = {}
    for nid in sorted(nodes):
        by_grade.setdefault(dg.get(nid, 0), []).append(nid)
    shells = []
    for g in range(0, g_max + 1):
        members = by_grade.get(g, [])
        anchor_in = [nid for nid in anchor_ids if dg.get(nid, 0) == g]
        sample = members[:_SHELL_SAMPLE_CAP]
        shells.append({
            "grade": g,
            "global_count": global_hist.get(g, 0),
            "is_floor": g == 0,
            "is_spine_tier": g == g_max and g_max > 0,
            "anchor_ids": anchor_in,
            "anchor_nodes": [_short_node(nodes, dg, nid) for nid in anchor_in],
            "global_sample": [{"id": nid, "kind": (nodes.get(nid) or {}).get("kind")}
                              for nid in sample],
            "global_truncated": max(0, len(members) - len(sample)),
        })
    # the derivation of every anchor node (load-bearing-as-derived, on demand)
    derivation = {nid: _derivation(net, dg, nid) for nid in anchor_ids if nid in nodes}
    # honest stored-vs-derived divergence. The stored ``grade`` is a build-tree
    # containment default (the corpus histogram proves it — almost all 0), NOT an
    # authored grade; the derived dep_grade is the load-bearing value. Divergence
    # is expected here, and we say so with the live histogram rather than crying
    # "bug" — this feeds his Leg-D hard-gate ruling.
    mismatch_rows = [
        {"id": nid, "stored": (nodes.get(nid) or {}).get("grade"), "derived": dg.get(nid)}
        for nid in anchor_ids
        if nid in nodes and (nodes.get(nid) or {}).get("grade") != dg.get(nid)
    ]
    grade_mismatch = {
        "count": len(mismatch_rows),
        "rows": mismatch_rows,
        "stored_grade_histogram": dict(sorted(stored_hist.items())),
        "note": ("the stored 'grade' field is a build-tree containment default "
                 "(see the histogram — nearly all 0), not an authored grade; the "
                 "derived dep_grade is the load-bearing value. Divergence is "
                 "expected, not a data fault. Flagged for the Leg-D grade-gate call."),
    }

    # ── altitude 2 · SPINE (reused from the storyboard, not rebuilt) ─────────
    enriched = sb.enriched_plan(corpus) or {}
    spine_rail = [
        {**b, "grade": dg.get(b.get("id"), None),
         "anchor": b.get("id") in {(nodes.get(nid) or {}).get("projection", {}).get("section_ref")
                                   for nid in anchor_ids}}
        for b in enriched.get("spine", [])
    ]
    spine_ids = {b.get("id") for b in enriched.get("spine", [])}
    anchor_beats = sorted(
        {(nodes.get(nid) or {}).get("projection", {}).get("section_ref")
         for nid in anchor_ids} & spine_ids
    )

    # ── altitude 3 · PLAN / PROSE (materialized, stale-aware) ────────────────
    plan_sections = (enriched.get("sections") or []) + (enriched.get("appendices") or [])
    owning = owning_section(a, sec_nodes, plan_sections,
                            a["node"] if a["kind"] == "node" else None)
    owning_section_obj = next((s for s in plan_sections if s.get("id") == owning), None)
    stamp = _artefact_stamp(target_dir, ledger) if target_dir else {"compiled": False}

    # ── the wiring-back keys — every layer's join to the one below, with the
    #    concrete VALUES for THIS anchor (the transparency clause) ─────────────
    anchor_grades = {nid: dg.get(nid) for nid in anchor_ids}
    wiring_back = {
        "pid": a["raw"] if a["kind"] == "pid" else None,
        "pid_to_nodes": {
            "join": "% NODES marker of the anchor's section",
            "section": a.get("section"),
            "node_ids": anchor_ids,
        },
        "nodes_to_grades": {
            "join": "corpus_ingest.dep_grade(net) — derivational depth, spine-elevated (derived, never stored)",
            "grades": anchor_grades,
        },
        "grades_to_beats": {
            "join": "projection.section_ref -> spine beat (the spine sits at grade g_max)",
            "beats": anchor_beats,
        },
        "beats_to_section": {
            "join": "plan section.beats[] membership",
            "section": owning,
        },
        "section_to_artefact": {
            "join": "target_dir/<section>.tex + main.pdf page",
            "tex": (owning + ".tex") if owning else None,
            "pdf": stamp.get("pdf_path") or "main.pdf",
        },
    }

    # the altitude the climb OPENS at (the anchor's own altitude), and the ladder.
    # Every GRAIN that resolves to a node set — pid, node AND section — opens at the
    # NODES substrate (altitude 0): the north star is substrate-first, and a section
    # anchor already carries its % NODES set, so it lands on the nodes it names, not
    # the prose skin above them (F4 — was 'plan_prose', which contradicted the
    # report's node-substrate landing and the pid/node grains' behaviour). Only the
    # empty anchor (no node set to stand on) opens at the spine overview.
    open_at = {"pid": "nodes", "node": "nodes", "section": "nodes", None: "spine"}[a["kind"]]

    return {
        "corpus": corpus,
        "anchor": a,
        "open_at": open_at,
        "ladder": ["nodes", "grade_shells", "spine", "plan_prose"],
        "g_max": g_max,
        "n_nodes": len(nodes),
        "grade_derivation_exposed": True,
        "altitudes": {
            "nodes": {
                "anchor_ids": anchor_ids,
                "nodes": node_cards,
                "neighborhood": neighborhood,
                "join_down": "the anchor pid/section -> these node ids (% NODES membership)",
            },
            "grade_shells": {
                "g_max": g_max,
                "shells": shells,
                "anchor_grades": anchor_grades,
                "derivation": derivation,
                "grade_mismatch": grade_mismatch,
                "join_down": "each node -> its dep_grade (derived depth); click a shell -> its nodes -> their sections",
            },
            "spine": {
                "rail": spine_rail,
                "anchor_beats": anchor_beats,
                "storyboard_link": f"/storyboard?corpus={corpus}",
                "join_down": "grades -> spine beats via projection.section_ref (spine at g_max)",
            },
            "plan_prose": {
                "section": owning_section_obj,
                "owning_section_id": owning,
                "artefact": stamp,
                "links": {
                    # W2: projection + review consolidated into the ONE artefact surface.
                    "projection": f"/artefact?corpus={corpus}",
                    "review": f"/artefact?corpus={corpus}",
                    "storyboard": f"/storyboard?corpus={corpus}",
                },
                "join_down": "beats -> plan section -> the materialized artefact page (stale-aware)",
            },
        },
        "wiring_back": wiring_back,
    }


def handle(path: str, query: dict, method: str, body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/altitude*`` request. Returns (status, content_type, body) or
    None when the path is not ours (the scanner falls through). READ-ONLY: GET
    only — no write verbs live here (rulings are ``/review``'s, plan edits are
    ``/storyboard``'s)."""
    if path != "/altitude" and not path.startswith("/altitude/"):
        return None
    method = (method or "GET").upper()

    if path == "/altitude" and method == "GET":
        # the viewer page; it reads corpus+anchor from its own URL and fetches
        # /altitude/data. Navigating to /altitude?corpus=&anchor= lands here — the
        # exact contract B-4's trace-up honours.
        if not _HTML.is_file():
            return _json_resp(500, {"error": "altitude.html missing on disk"})
        return 200, "text/html; charset=utf-8", _HTML.read_bytes()

    if path == "/altitude/data" and method == "GET":
        corpus = _q1(query, "corpus")
        if not corpus:
            # F3: a dir-based review (no ?corpus=) can still address the tower — the
            # dir reverse-resolves to its registered corpus key through the same
            # registry fence. An unresolvable dir degrades honestly to a 400 that
            # names why (never a silent empty-corpus 400).
            dir_param = _q1(query, "dir")
            if dir_param:
                corpus = corpus_for_dir(dir_param) or ""
                if not corpus:
                    return _json_resp(400, {
                        "error": f"dir {dir_param!r} does not resolve to a registered "
                                 "corpus — open the tower with ?corpus="})
            if not corpus:
                return _json_resp(400, {"error": "corpus= (or a resolvable dir=) required"})
        anchor = _q1(query, "anchor")
        try:
            out = resolve(corpus, anchor)
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"altitude resolve failed: {e}"})
        if out is None:
            return _json_resp(404, {"error": f"unknown corpus {corpus!r}"})
        return _json_resp(200, out)

    return _json_resp(404, {"error": f"no altitude route {path!r}"})
