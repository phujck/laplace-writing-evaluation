"""The RESTRUCTURE operator — the N→M section-set restructure as one native call.

The 2026-07-08 general-first restructure was executed by four bespoke scripts
(banked under ``manuscript/evolutions/general_first_restructure_2026-07-08/
_bespoke_scripts/``): ``build_general_first_plan.py`` / ``build_v2_split_refs.py``
(hardcoded NEW/BLOCK/OVER/FIGOVER maps → a new plan), ``build_prose_bundles.py``
(re-integration bundles from the old fragments) and ``commit_plan.py`` (plan+base
write, ledger clear, reconcile, validate). This module is that shape generalised:
the human rulings become a declarative **target_arc** JSON object, and the operator
does the rest — resequence, merge, split, re-home nodes, redistribute refs, carry
figures and beats — in both directions (substrate-led: ``evolve`` computes an arc
and calls in; storyboard-led: the author writes the arc and the plan leads).

THE TARGET_ARC (schema constants below; the orchestrator folds them into
``pipeline.schema`` at P6)::

    {
      "sections":  [ {"id", "title", "seed_from": [old ids], "job"?, "notes"?,
                      "beats"?: [node ids], "spec"?} ... ],      # ordered new body
      "appendices": [ same shape ... ],   # OPTIONAL — omitted: carried verbatim
      "overrides": {node_id: new_section_id},      # human rulings (the OVER map)
      "figure_overrides": {fig_id: new_section_id},  # the FIGOVER map; a fig id
                                                     # unknown to the old plan is
                                                     # ADDED (a fresh mint's home)
      "refs": {"carry":     {new_id: [old ids]},   # extra old pools unioned in
               "overrides": {bibkey: new_id}},     # single-key forced home
      "park": [node_id ...],              # explicitly dropped, recorded not stray
      "spine": {"order": [node ids], "narratives"?: {node: str},
                "unset": [node ids]},     # L1 reorder — emitted, never applied here
      "meta": {...}                       # merged into plan.meta
    }

THE LAWS (each generalising a line of the bespoke scripts):

- **default re-homing** — old section O's nodes follow the one new section listing
  O in ``seed_from`` (the BLOCK map). O claimed by two new sections is a declared
  SPLIT: no default, every node of O needs an explicit override or park (the OVER
  map's job), else it is a stray and the build refuses, listing them.
- **exactly once** — every unique in-scope node lands in exactly one new section
  or is parked (the old plan's duplicate occurrences collapse to the first seen,
  as the seed did). Appendices stay out of scope unless the arc declares them; a
  node living in both realms keeps its appendix occurrence untouched.
- **refs carry-forward** — an old section's ref pool follows the plurality
  destination of its node occurrences (``build_v2_split_refs.py``); ``carry``
  unions extra pools (the "intro keeps intro refs" ruling); key overrides win.
- **figures follow** — explicit override, else the figure's own node re-homing,
  else its old section's default destination.
- **beats** — explicit per arc section; omitted → the old beats (document order)
  that landed in the section.

Plan-side pure throughout: :func:`plan_from_arc`, :func:`spine_payloads` and
:func:`prose_bundles` never write. :func:`execute` is the lifecycle wrapper —
dry-run reports only; apply freezes, writes plan+base, CLEARS the L2 friction
ledger (the banked fresh-generation semantics) and reconciles section_refs. The
L1 spine payloads are always RETURNED, never applied — that write belongs to the
caller (``evolve``), keeping the two-ledger transaction in one place.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path

from laplace.pipeline.schema import (NODES_MARKER_RE, PLAN_MARKER_RE,
                                     clean_ids, plan_sections, section_nodes)

# ---------------------------------------------------------------------------
# target_arc schema constants (P6 folds these into pipeline.schema)
# ---------------------------------------------------------------------------

TARGET_ARC_FIELDS = ("sections", "appendices", "overrides", "figure_overrides",
                     "refs", "park", "spine", "meta")
TARGET_ARC_SECTION_FIELDS = ("id", "title", "seed_from", "job", "notes",
                             "beats", "serves", "spec")
TARGET_ARC_REFS_FIELDS = ("carry", "overrides")
TARGET_ARC_SPINE_FIELDS = ("order", "narratives", "unset")


def _net_nodes(net: dict) -> dict:
    """Accept either a full corpus_network dict or its bare node map."""
    if isinstance(net, dict) and isinstance(net.get("nodes"), dict):
        return net["nodes"]
    return net or {}


# ---------------------------------------------------------------------------
# the pure core — arc + current plan → new plan
# ---------------------------------------------------------------------------

def _seed_defaults(arc_secs: list[dict], old_ids: list[str],
                   errors: list[str]) -> dict[str, str | None]:
    """old section id → its ONE seed_from claimant (the BLOCK map), or None when
    unclaimed / claimed twice (a declared split: explicit assignment required)."""
    claims: dict[str, list[str]] = {o: [] for o in old_ids}
    for sec in arc_secs:
        for o in sec.get("seed_from") or []:
            if o not in claims:
                errors.append(f"section {sec.get('id')!r}: seed_from names "
                              f"unknown old section {o!r}")
            else:
                claims[o].append(sec["id"])
    return {o: (cs[0] if len(cs) == 1 else None) for o, cs in claims.items()}


def _assign_realm(old_secs: list[dict], arc_secs: list[dict],
                  overrides: dict[str, str], park: set[str],
                  defaults: dict[str, str | None],
                  errors: list[str]) -> tuple[dict[str, str | None], list[str]]:
    """One realm's node assignment: node → new section id (None = parked), plus
    the first-seen document order (the seed's ``order_seen``). Strays — nodes with
    no default, no override, no park — are collected as errors, never guessed."""
    new_ids = {s["id"] for s in arc_secs}
    realm_over = {n: t for n, t in overrides.items() if t in new_ids}
    assigned: dict[str, str | None] = {}
    order_seen: list[str] = []
    strays: list[tuple[str, str]] = []
    for osec in old_secs:
        for n in section_nodes(osec):
            if n in assigned:
                continue                       # duplicates collapse to first seen
            order_seen.append(n)
            if n in realm_over and n in park:
                errors.append(f"node {n!r} both overridden and parked")
            if n in realm_over:
                assigned[n] = realm_over[n]
            elif n in park:
                assigned[n] = None
            elif defaults.get(osec.get("id")) is not None:
                assigned[n] = defaults[osec["id"]]
            else:
                strays.append((osec.get("id"), n))
                assigned[n] = None
    if strays:
        listing = ", ".join(f"{n} (old {o})" for o, n in strays)
        errors.append(f"{len(strays)} stray node(s) — old section split/unclaimed, "
                      f"assign or park each explicitly: {listing}")
    return assigned, order_seen


def _redistribute_refs(old_secs: list[dict], arc_secs: list[dict],
                       assigned: dict[str, str | None],
                       refs_spec: dict) -> dict[str, list[str]]:
    """Refs carry-forward: each old section's pool lands where the plurality of its
    node occurrences went (parked occurrences don't vote); ``carry`` unions extra
    old pools in; per-key overrides win last."""
    pools: dict[str, set[str]] = {s["id"]: set() for s in arc_secs}
    old_refs = {s.get("id"): list(s.get("refs") or []) for s in old_secs}
    for osec in old_secs:
        votes = Counter(assigned[n] for n in section_nodes(osec)
                        if assigned.get(n) is not None)
        if votes:
            pools[votes.most_common(1)[0][0]] |= set(old_refs[osec.get("id")])
    for nid, sources in (refs_spec.get("carry") or {}).items():
        if nid in pools:
            for o in sources:
                pools[nid] |= set(old_refs.get(o) or [])
    for key, nid in (refs_spec.get("overrides") or {}).items():
        for pool in pools.values():
            pool.discard(key)
        if nid in pools:
            pools[nid].add(key)
    return {sid: sorted(pool) for sid, pool in pools.items()}


def _place_figures(old_secs: list[dict], arc_secs: list[dict],
                   assigned: dict[str, str | None], fig_over: dict[str, str],
                   park: set[str], defaults: dict[str, str | None],
                   errors: list[str]) -> dict[str, list[str]]:
    """Figure homes: override > the figure's own node assignment > the old
    section's default. A split parent's figure with no ruling is an error, never
    a silent drop. Override ids unknown to the old plan are fresh mints, appended
    after the carried figures."""
    new_ids = {s["id"] for s in arc_secs}
    home: dict[str, str | None] = {}
    for osec in old_secs:
        for f in osec.get("figures") or []:
            if f in home:
                continue
            if f in park:
                home[f] = None
                continue
            home[f] = (fig_over.get(f) or assigned.get(f)
                       or defaults.get(osec.get("id")))
            if home[f] is None:
                errors.append(f"figure {f!r} (old {osec.get('id')}) has no home - "
                              f"add a figure_overrides ruling or park it")
    for f, sid in fig_over.items():
        if f not in home and sid in new_ids:   # a mint's declared home
            home[f] = sid
    return {sid: [f for f, h in home.items() if h == sid]
            for sid in (s["id"] for s in arc_secs)}


def plan_from_arc(current_plan: dict, arc: dict, net_nodes: dict) -> dict:
    """PURE: the restructured plan. Sections resequenced/merged/split per the arc,
    nodes re-homed by rule+overrides, refs redistributed, figures following, beats
    carried. Raises ValueError (all problems listed at once) on strays, unknown
    ids, or contradictory rulings — the plan is only built when every node lands
    exactly once or is parked."""
    nodes = _net_nodes(net_nodes)
    errors: list[str] = []
    arc_secs = list(arc.get("sections") or [])
    if not arc_secs:
        errors.append("arc.sections is empty")
    seen_ids: set[str] = set()
    for s in arc_secs + list(arc.get("appendices") or []):
        sid = s.get("id")
        if not sid or sid in seen_ids:
            errors.append(f"duplicate/missing new section id {sid!r}")
        seen_ids.add(sid)

    overrides = dict(arc.get("overrides") or {})
    park = set(arc.get("park") or [])
    for n, t in overrides.items():
        if t not in seen_ids:
            errors.append(f"override {n!r} → unknown section {t!r}")
    if nodes:   # typo fence, only when a net is supplied
        for n in list(overrides) + sorted(park):
            if n not in nodes:
                errors.append(f"override/park id {n!r} is not a known node")
    if errors:
        raise ValueError("target_arc invalid:\n  " + "\n  ".join(errors))

    realms = [("sections", arc_secs)]
    if arc.get("appendices") is not None:
        realms.append(("appendices", list(arc.get("appendices") or [])))

    new_plan = copy.deepcopy(current_plan)
    applied_over: set[str] = set()
    for key, specs in realms:
        old_secs = list(current_plan.get(key) or [])
        defaults = _seed_defaults(specs, [s.get("id") for s in old_secs], errors)
        assigned, order_seen = _assign_realm(old_secs, specs, overrides, park,
                                             defaults, errors)
        applied_over |= {n for n in overrides if assigned.get(n) == overrides[n]}
        refs = _redistribute_refs(old_secs, specs, assigned,
                                  arc.get("refs") or {})
        figures = _place_figures(old_secs, specs, assigned,
                                 dict(arc.get("figure_overrides") or {}),
                                 park, defaults, errors)
        old_beats = [b for osec in old_secs for b in (osec.get("beats") or [])]
        built = []
        for spec in specs:
            sid = spec["id"]
            sec_nodes = [n for n in order_seen if assigned.get(n) == sid]
            beats = spec.get("beats")
            if beats is None:      # carry the old beats that landed here
                beats = [b for b in dict.fromkeys(old_beats)
                         if assigned.get(b) == sid]
            title = spec.get("title") or sid
            sec = {"id": sid, "title": title,
                   "job": spec.get("job") or (
                       f"[RESTRUCTURE-SEED] {title} - re-integrate existing "
                       f"prose into the new arc; do not regenerate."),
                   "notes": spec.get("notes") or "",
                   "refs": refs.get(sid, []),
                   "beats": list(beats),
                   "nodes_in_order": sec_nodes,
                   "figures": figures.get(sid, [])}
            if "serves" in spec:
                # C3.1 section ownership: an arc MAY declare the contribution(s)
                # each section earns (a content-id or 1-based rank, or a list),
                # resolved against meta.contribution_rank by check_serves. Carried
                # verbatim like ``spec`` — the arc is the producer of the plan-side
                # serves edge (there is no default; an omitted serves stays absent).
                sec["serves"] = spec["serves"]
            if "spec" in spec:
                sec["spec"] = spec["spec"]
            built.append(sec)
        new_plan[key] = built

    # a ruling that never landed is drift, not noise: in-scope-but-unapplied means
    # a cross-realm move (unsupported — park + re-add instead); out-of-scope keys
    # are inert (the seed's ``if n in assigned``) and reported by execute().
    scope_nodes = {n for key, _ in realms
                   for s in (current_plan.get(key) or []) for n in section_nodes(s)}
    unapplied = [n for n in overrides if n in scope_nodes and n not in applied_over]
    if unapplied:
        errors.append("override(s) in scope but never applied (cross-realm target?): "
                      + ", ".join(sorted(unapplied)))
    if errors:
        raise ValueError("restructure refused:\n  " + "\n  ".join(errors))

    if arc.get("meta"):
        new_plan.setdefault("meta", {}).update(arc["meta"])
    return new_plan


def spine_payloads(arc: dict) -> list[dict]:
    """The L1 set-spine reorder as rewire payloads (pure — the caller applies them
    via ``corpus_ingest.rewire_add``, evolve's transaction). A payload carries
    ``narrative`` only when the arc supplies one: the L1 fold preserves an existing
    narrative when the record omits it."""
    sp = arc.get("spine") or {}
    narratives = sp.get("narratives") or {}
    out = []
    for i, nid in enumerate(sp.get("order") or []):
        payload = {"kind": "set-spine", "node": nid, "ord": i, "by": "restructure"}
        if nid in narratives:
            payload["narrative"] = narratives[nid]
        out.append(payload)
    out.extend({"kind": "unset-spine", "node": nid, "by": "restructure"}
               for nid in sp.get("unset") or [])
    return out


# ---------------------------------------------------------------------------
# prose bundles — the re-integration input (generalising build_prose_bundles.py)
# ---------------------------------------------------------------------------

def _fragment_spans(frag: Path, old_sid: str) -> list[dict]:
    """A fragment's %NODES-marker spans with their prose (marker lines dropped),
    via the viewer's own parser — sidecar-preferred, never a parallel parse."""
    from laplace.manuscript import projection_viewer as pv
    lines = frag.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for span in pv.load_map(frag):
        lo, hi = span.get("start_line"), span.get("end_line")
        if not (isinstance(lo, int) and isinstance(hi, int)):
            continue
        body = [l for l in lines[lo - 1:hi]
                if not (PLAN_MARKER_RE.match(l) or NODES_MARKER_RE.match(l))]
        text = "\n".join(body).strip()
        if text:
            out.append({"old_section": old_sid,
                        "nodes": list(span.get("nodes") or []), "tex_span": text})
    return out


def prose_bundles(project: str, old_plan: dict, new_plan: dict,
                  repo_root: Path | str | None = None) -> dict[str, list[dict]]:
    """Per new section: the prose spans, from the OLD fragments of wherever its
    nodes used to live, in the new node order — the re-integration bundle
    ``{new_section: [{node, old_section, tex_span}]}``. Pure read; missing
    fragments are skipped (a never-compiled section simply has no prose to carry)."""
    from laplace.pipeline import pathsafe, registry
    rr = Path(repo_root) if repo_root else registry._repo_root()
    proj = registry.resolve(project)
    target = ((old_plan.get("meta") or {}).get("target_dir")
              or (proj.target_dir if proj else "")).rstrip("/")
    if not target:
        return {}
    spans: list[dict] = []
    for osec in plan_sections(old_plan):
        frag = rr / target / f"{pathsafe.encode_sid_for_path(osec.get('id'))}.tex"
        if frag.is_file():
            spans.extend(_fragment_spans(frag, osec.get("id")))
    by_node: dict[str, list[int]] = {}
    for i, sp in enumerate(spans):
        for n in sp["nodes"]:
            by_node.setdefault(n, []).append(i)
    bundles: dict[str, list[dict]] = {}
    for nsec in plan_sections(new_plan):
        picked, seen = [], set()
        for n in section_nodes(nsec):
            for i in by_node.get(n, []):
                if i not in seen:     # one span once per section, first node wins
                    seen.add(i)
                    picked.append({"node": n,
                                   "old_section": spans[i]["old_section"],
                                   "tex_span": spans[i]["tex_span"]})
        bundles[nsec.get("id")] = picked
    return bundles


# ---------------------------------------------------------------------------
# the dirty diff — which sections' node-sets changed (cheap/expensive per schema)
# ---------------------------------------------------------------------------

def dirty_diff(old_plan: dict, new_plan: dict) -> dict:
    """Old plan vs new plan, joined on section id (the fragment join key): a
    section whose clean node SET is unchanged is cheap (title/order only); a
    changed or new set means its builder must re-run (schema's op classes)."""
    old_sets = {s.get("id"): clean_ids(section_nodes(s))
                for s in plan_sections(old_plan)}
    out = []
    for sec in plan_sections(new_plan):
        sid = sec.get("id")
        new_set = clean_ids(section_nodes(sec))
        old_set = old_sets.get(sid)
        changed = old_set is None or new_set != old_set
        out.append({"id": sid, "new_section": old_set is None,
                    "changed": changed,
                    "added": sorted(new_set - (old_set or set())),
                    "removed": sorted((old_set or set()) - new_set),
                    "class": "expensive" if changed else "cheap"})
    new_ids = {s.get("id") for s in plan_sections(new_plan)}
    return {"sections": out,
            "removed_sections": sorted(set(old_sets) - new_ids)}


# ---------------------------------------------------------------------------
# execute — the lifecycle wrapper (dry-run pure; apply = the banked commit_plan)
# ---------------------------------------------------------------------------

def _inert_overrides(current_plan: dict, arc: dict) -> list[str]:
    """Override keys naming nodes outside the restructure scope — tolerated (the
    seed ignored them) but surfaced, so a mistyped ruling is visible."""
    scope = {n for s in plan_sections(
        current_plan, appendices=arc.get("appendices") is not None)
        for n in section_nodes(s)}
    return sorted(n for n in (arc.get("overrides") or {}) if n not in scope)


def execute(project_name: str, arc: dict, dry_run: bool = True,
            repo_root: Path | str | None = None) -> dict:
    """Run the restructure for a registered project. Dry-run (the default) is a
    pure report: {new_plan, validation, dirty, spine_payloads, prose_bundles}.
    Apply: freeze the ledgers+plan, write plan AND base (new base = new plan),
    CLEAR the L2 friction ledger (fresh generation), reconcile section_refs.
    ``repo_root`` steers the read-side only; apply writes through storyboard's
    own registry-fenced surface. Spine payloads are returned, never applied."""
    from laplace.manuscript import storyboard
    from laplace.pipeline import ledger, registry
    proj = registry.resolve(project_name)
    if proj is None or not proj.plan_path:
        return {"ok": False, "error": f"unknown or plan-less project {project_name!r}"}
    rr = Path(repo_root) if repo_root else registry._repo_root()
    plan_path = proj.plan(rr)
    if plan_path is None or not plan_path.is_file():
        return {"ok": False, "error": f"no plan file at {plan_path}"}
    current_plan = json.loads(plan_path.read_text(encoding="utf-8"))

    try:
        from laplace.research import corpus_ingest as ci
        troot = ci.resolve_corpus(rr, project_name)
        net = ci.corpus_network(troot, repo_root=rr, name=project_name) if troot else {}
    except Exception:                      # the net is advisory to the pure core
        net = {}

    try:
        new_plan = plan_from_arc(current_plan, arc, net)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    validation = storyboard._validate_reduced(new_plan, project_name)
    report = {
        "ok": True, "applied": False, "project": project_name,
        "new_plan": new_plan,
        "validation": validation,
        "dirty": dirty_diff(current_plan, new_plan),
        "spine_payloads": spine_payloads(arc),
        "prose_bundles": prose_bundles(project_name, current_plan, new_plan, rr),
        "parked": sorted(arc.get("park") or []),
        "inert_overrides": _inert_overrides(current_plan, arc),
    }
    if dry_run:
        return report

    structural = not validation.get("pass", True) and any(
        validation.get(k) for k in ("missing_nodes", "retired_used",
                                    "missing_refs", "fig_defects"))
    if structural:
        report.update(ok=False, error="validation failed structurally - not applied")
        return report

    base_p = storyboard._sidecar(project_name, ".base.json")
    friction_p = storyboard._sidecar(project_name, ".friction.jsonl")
    l1 = proj.path(proj.ledger, rr)
    frozen = ledger.freeze([p for p in (l1, plan_path, base_p, friction_p) if p],
                           plan_path.parent / "archive", label="restructure_preboard")
    payload = json.dumps(new_plan, ensure_ascii=False, indent=1) + "\n"
    storyboard._write_plan_json(project_name, new_plan)
    if base_p is not None:                 # new generation: base = plan, ledger empty
        base_p.write_text(payload, encoding="utf-8", newline="")
    if friction_p is not None:
        friction_p.write_text("", encoding="utf-8")
    report.update(applied=True, freeze_dir=str(frozen),
                  reconcile=storyboard.reconcile_section_refs(project_name))
    return report
