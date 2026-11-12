"""Bespoke clause verifiers for the generalized operating-contract runner.

``tests/test_operating_contract.py`` iterates EVERY ``contract/surfaces/*.yaml`` and
generates one test per structural clause and per counts law. A red clause only goes
LOUD through a *bespoke failing assertion body* (a no-op body under strict xfail xpasses
backwards — the arming names that trap), so each red clause needs a real probe of the
actual behavior that flips exactly when the wave lands. This module holds those probes,
keyed by clause id, plus the counts-law verifiers, plus the bar-law consumption check.

Each structural verifier is ``verifier(repo_root) -> None``. It RAISES ``AssertionError``
(with a message quoting the clause) when the behavioral FLOOR is absent — that is the
xfail-red state. It returns normally when the floor holds; the runner then applies the
bar law (a ``judged``/``author`` clause whose floor holds but carries no resolving
verdict is xfail-*verdict-owed*, a distinct honest state, never plain green).

The bar law reads verdicts ONLY through :func:`laplace.engine.superego.verdicts_for` — never a
private parser (his ruling, PRM-20260722-bars-on-clauses; production never self-certifies).
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path


class CountsSkip(Exception):
    """A counts law whose chip-equals-filter is not reachable in-process — an honest
    SKIP naming why, never a false green."""


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------
def _projects(repo_root: Path) -> list[str]:
    """The one authoritative conceptric list (G0), read through the registry door."""
    try:
        from laplace.pipeline import registry
        return [p.get("corpus") or p.get("name")
                for p in registry.conceptric_projects(Path(repo_root))]
    except Exception:
        return []


def _read(repo_root: Path, rel: str) -> str:
    return (Path(repo_root) / rel).read_text(encoding="utf-8", errors="replace")


def _net(repo_root: Path, proj: str):
    from laplace.research import corpus_ingest as ci
    troot = ci.resolve_corpus(Path(repo_root), proj)
    if not troot:
        return None
    return ci.corpus_network(troot, repo_root=Path(repo_root), name=proj)


# ---------------------------------------------------------------------------
# THE BAR LAW (his ruling, PRM-20260722-bars-on-clauses): a clause carrying
# ``bar: judged|author`` may only count GREEN when — in addition to its behavioral floor
# — contract/judged_verdicts.jsonl holds a resolving STANDS verdict whose claim (or refs
# or questions) references the clause id or its wave, ruled by a NON-BUILDER judge (bar
# judged) or the AUTHOR (bar author). Read ONLY via superego.verdicts_for.
# ---------------------------------------------------------------------------
def _actor_key(name: str) -> str:
    return str(name or "").strip().casefold()


def _is_author_ruling(judge: str) -> bool:
    """An author-bar clause needs HIS ruling (or his proxy), not merely a non-builder
    judge. The author identities the ledger would carry."""
    j = _actor_key(judge)
    return any(tok in j for tok in ("gerard", "author", "principal", "his ruling"))


def resolving_verdict(repo_root: Path, clause_id: str, wave: str | None,
                      bar: str | None) -> tuple[bool, str]:
    """Does a banked STANDS verdict resolve this clause at its bar? Returns
    ``(resolved, reason)``. Reads through :func:`laplace.engine.superego.verdicts_for` only."""
    from laplace.engine import superego
    rows = superego.verdicts_for(repo_root, limit=200)
    tokens = [t for t in (clause_id, wave) if t]
    for r in rows:
        if r.get("verdict") != "STANDS":
            continue
        # The law: a resolving verdict is one whose CLAIM (its subject) references the clause
        # id or its wave — plus its refs, where a wave-delivery verdict cites the clause file.
        # The judge's questions are Q&A about the claim, NOT the claim's subject, so they are
        # DELIBERATELY excluded: an incidental mention of a wave in a question ("the precedent,
        # the four W-grammar reds") must never masquerade as that wave's delivery verdict.
        hay = str(r.get("claim", "")) + " " + \
            " ".join(str(x) for x in (r.get("refs") or []))
        if not any(t in hay for t in tokens):
            continue
        judge, builder = str(r.get("judge", "")), str(r.get("builder", ""))
        if _actor_key(judge) == _actor_key(builder):
            continue  # a self-certified row never resolves (production never self-certifies)
        if bar == "author" and not _is_author_ruling(judge):
            return (False, f"a judged STANDS references {clause_id} but bar:author needs the "
                           f"author's own ruling, not judge={judge!r}")
        return (True, f"resolved by {r.get('id')} (judge {judge!r})")
    toks = " / ".join(repr(t) for t in tokens)
    return (False, f"no STANDS verdict in judged_verdicts.jsonl references {toks}")


# ===========================================================================
# STRUCTURAL VERIFIERS — one bespoke probe per structural clause.
# ===========================================================================

# ---- desk (green, migrated verbatim from the per-surface tests) -----------
def _v_desk_consume(repo_root: Path) -> None:
    mjs = _read(repo_root, "src/laplace/web/static_shared/desk-panes.mjs")
    m = re.search(r"COMPOSE\s*=[^;]*;", mjs, re.S)
    assert m and "consume" in m.group(0), (
        "work-order-consume-carries-evidence: consume has no evidence compose — it fires "
        "evidence_refs=[] and always 422s")


# ---- pipeline (green, migrated verbatim) ----------------------------------
def _v_pipeline_action_organ(repo_root: Path) -> None:
    from laplace.manuscript import storyboard
    from laplace.web import pipeline_surface as ps
    roster = storyboard.launch_roster()
    actions = {a["action"] for group in roster.values() if isinstance(group, list)
               for a in group if isinstance(a, dict) and a.get("action")}
    unmapped = sorted(actions - set(ps._ACTION_ORGAN))
    assert not unmapped, f"action-organ-complete: actions falling silently into 'global': {unmapped}"


def _v_pipeline_state_machine(repo_root: Path) -> None:
    pat = re.compile(r"release\.(transition|ensure_at_least)\s*\(|"
                     r"from\s+.*release\s+import\s+.*\btransition\b")
    hits = []
    for p in (Path(repo_root) / "src" / "laplace").rglob("*.py"):
        if p.name == "release.py":
            continue
        if pat.search(p.read_text(encoding="utf-8", errors="replace")):
            hits.append(p.name)
    assert hits, ("state-machine-driven: release.transition()/ensure_at_least() has no live "
                  "invoker outside release.py")


def _v_pipeline_next_action(repo_root: Path) -> None:
    mjs = _read(repo_root, "src/laplace/web/static_shared/pipeline-panes.mjs")
    assert "next_action" in mjs, (
        "next-action-rendered: states[].next_action is computed server-side and never rendered")


# ---- storyboard (W-grammar red) -------------------------------------------
def _v_weighting_grounding(repo_root: Path) -> None:
    """FLOOR (bar judged): weighting cards must carry STRUCTURED per-card grounding (source
    nodes + the why), not a raw authored line the client regexes ``{#id}`` off with a single
    global invite. Today ``contribution_rank`` items are raw strings — no per-card grounding."""
    from laplace.manuscript import storyboard
    seen_rank = False
    for proj in _projects(repo_root):
        ep = storyboard.enriched_plan(proj)
        if not ep:
            continue
        rank = (ep.get("meta") or {}).get("contribution_rank")
        if not rank:
            continue
        seen_rank = True
        items = list(rank.get("primary") or []) + list(rank.get("excluded") or [])
        grounded = [it for it in items
                    if isinstance(it, dict) and it.get("nodes") and it.get("why")]
        assert items and len(grounded) == len(items), (
            f"weighting-card-grounding-visible: {proj}'s weighting cards are raw strings "
            f"({len(items)} lines) — the board regexes {{#id}} off the text and shows one global "
            "invite, not each card's source nodes + why rendered in place")
        return
    assert seen_rank, ("weighting-card-grounding-visible: no project exposes a contribution_rank "
                       "to ground — the weighting grounding is undemonstrable")


def _v_cards_expand(repo_root: Path) -> None:
    """FLOOR (bar judged): section cards already expand in place; the clause also requires the
    WEIGHTING cards to expand around the point — today the weighting pill's door does a
    context-free jump (openNode/revealSection), the exact anti-pattern the clause forbids."""
    mjs = _read(repo_root, "src/laplace/web/static_shared/storyboard-panes.mjs")
    m = re.search(r"function renderRank\b[\s\S]*?\n}\n", mjs)
    assert m, "cards-expand-in-place-with-context: renderRank not found in storyboard-panes.mjs"
    block = m.group(0)
    assert "openNode(" not in block and "revealSection(" not in block, (
        "cards-expand-in-place-with-context: the weighting card door JUMPS "
        "(openNode/revealSection) instead of expanding in place — a context-free jump")


# ---- assets (W-grammar red) -----------------------------------------------
def _v_asset_cockpit(repo_root: Path) -> None:
    """FLOOR (bar mechanical): the cockpit's forward doors exist (landings→reader,
    nodes→conceptric). The BOTH-DIRECTIONS seal requires the conceptric side to door BACK to
    the named asset — probe a node an asset supports and assert its conceptric node view
    carries an /assets door back to it. Absent today (conceptric emits no /assets href)."""
    from laplace.web import assets_surface
    from laplace.engine import conceptric
    probed = None
    for proj in _projects(repo_root):
        lp = assets_surface.list_payload(proj)
        if not lp:
            continue
        cand = next((c for c in (lp["figures"] + lp["derivations"]) if c["nodes_n"] > 0), None)
        if cand is None:
            continue
        op = assets_surface.object_payload(proj, cand["id"])
        if not op or not op.get("nodes"):
            continue
        node = op["nodes"][0]["id"]
        net = _net(repo_root, proj)
        if net is None:
            continue
        probed = (proj, cand["id"], node)
        nv = conceptric.node_view(net, node)
        assert "/assets" in json.dumps(nv, ensure_ascii=False), (
            f"asset-cockpit-close-examination: {proj} asset {cand['id']} supports {node}, but the "
            "conceptric node view carries no /assets door back to it — the cockpit's doors are "
            "one-directional, not the both-directions seal the clause demands")
        return
    assert probed is not None, ("asset-cockpit-close-examination: no asset with a supported node "
                                "is reachable in-process to probe the both-directions door")


# ---- artefact (W-grammar red) ---------------------------------------------
def _v_anchor_chips(repo_root: Path) -> None:
    """FLOOR (bar judged): the reader's anchor overlay must wire asset door-chips landing on the
    NAMED asset (/assets?...&asset=<id>). This floor HOLDS today (artefact-panes.mjs builds it),
    so the clause is judged-verdict-owed until the W7 seal walk is banked — never plain green."""
    mjs = _read(repo_root, "src/laplace/web/static_shared/artefact-panes.mjs")
    assert ("assetChipHTML" in mjs and "assetsForNodes" in mjs and "&asset=" in mjs), (
        "anchor-chips-door-to-named-asset: the anchor overlay carries no asset door-chip landing "
        "on the named asset (/assets?...&asset=)")


# ---- conceptric (W-growth red) --------------------------------------------
def _v_growth_ladder(repo_root: Path) -> None:
    """FLOOR (bar mechanical): every project conceptric carries a live laddered growth state.
    G2 landed growth.py and the render rung, but no registered project is on the ladder yet —
    all pre_ladder (present:False). Flips when a project carries SEEDED/…/REGOALED."""
    from laplace.pipeline import growth
    projs = _projects(repo_root)
    live = [p for p in projs if growth.growth_state(repo_root, p).get("present")]
    assert live, (
        "growth-ladder-live: growth.py landed the ladder + the render rung, but NO registered "
        f"project carries a live laddered state (checked {len(projs)}; all pre_ladder) — the "
        "machine renders the rung but nothing walks it")


def _v_epistemic_status(repo_root: Path) -> None:
    """FLOOR (bar mechanical): a node's built record carries epistemic_status, rendered on its
    conceptric card/chip. Today no node payload carries the field (it lives in three unlinked
    carriers, on no built node record)."""
    from laplace.engine import conceptric
    checked = 0
    for proj in _projects(repo_root):
        net = _net(repo_root, proj)
        if net is None:
            continue
        checked += 1
        for g in (0, 1, 2):
            gv = conceptric.grade_view(repo_root, net, g)
            for n in gv.get("nodes", []):
                if n.get("epistemic_status") or n.get("epistemic"):
                    return
        if checked >= 3:
            break
    raise AssertionError(
        "epistemic-status-one-home: no node carries an epistemic_status field on its conceptric "
        "card/chip — the one-home status (proven/computed/conjectured/imported/exploratory) is "
        "written to no built node record and rendered on no chip")


def _v_axes_typed(repo_root: Path) -> None:
    """FLOOR (bar mechanical): edges carry a typed axis family as DATA (kind/axis), not smuggled
    in a string prefix parsed by convention. Today grade_view edges are a/b/out/in/shared/
    conjectural — no typed kind, no per-axis coverage law surfaced."""
    from laplace.engine import conceptric
    checked = 0
    for proj in _projects(repo_root):
        net = _net(repo_root, proj)
        if net is None:
            continue
        checked += 1
        for g in (0, 1, 2):
            gv = conceptric.grade_view(repo_root, net, g)
            for e in gv.get("edges", []):
                if e.get("kind") or e.get("axis") or e.get("family"):
                    return
        if checked >= 3:
            break
    raise AssertionError(
        "axes-typed-not-smuggled: conceptric edges carry no typed axis 'kind'/'axis' field — "
        "relation family is still smuggled as a string prefix (sem::/conn::) parsed by "
        "convention; no axis registry with a per-axis coverage law is surfaced on the edge")


def _v_goal_regoal(repo_root: Path) -> None:
    """FLOOR (bar author): the cockpit renders goal-tension cards offering the four tension
    verbs (REALIGN/RESPINE, REGOAL, HOLD/WAIVE, DISMISS SIGNAL — the composition-law ruling
    superseded the three-verb card), served by the growth surface's tension door. Re-aimed at
    the live pane after the E2+E3 wave moved cockpit behavior out of conceptric-panes.mjs
    (the E2+E3 adversary's ruling: three met floors read false-RED off the retired file)."""
    mjs = _read(repo_root, "src/laplace/web/static_shared/cockpit-panes.mjs")
    srv = _read(repo_root, "src/laplace/web/growth_surface.py")
    low = mjs.lower()
    assert ("regoal" in low and "dismiss" in low and "growth/tensions" in low), (
        "goal-versioned-regoal-loop: the cockpit renders no goal-tension card with the four "
        "tension verbs — goal versioning + the regoal forced-choice loop has no door")
    assert "goal_tensions" in srv, (
        "goal-versioned-regoal-loop: the growth surface serves no tension payload")


def _v_demand_audit(repo_root: Path) -> None:
    """FLOOR (bar mechanical): the goal-conditioned demand audit's typed CONTENT/FORM/TENSION
    rows are RENDERED on the conceptric surface (oracle-tier demands shown judged-pending, never
    green). The demand organ may exist (pipeline/demand.py) but reaches no surface payload."""
    mjs = _read(repo_root, "src/laplace/web/static_shared/cockpit-panes.mjs")
    srv = _read(repo_root, "src/laplace/web/growth_surface.py")
    low = mjs.lower()
    assert ("growth/queue" in low and "friction_type" in low), (
        "demand-audit-floor-honest: the cockpit renders no demand-audit rows "
        "(CONTENT/FORM/TENSION bound to demand ids) — the audit organ is not wired to a "
        "served payload the surface reads")
    assert "demand.audit" in srv or ("audit(" in srv and "from laplace.pipeline import" in srv), (
        "demand-audit-floor-honest: the growth surface does not serve the demand audit")


def _v_coverage_vector(repo_root: Path) -> None:
    """FLOOR (bar mechanical): completeness renders as a per-axis coverage VECTOR on the
    conceptric surface. Today the surface renders no coverage vector."""
    mjs = _read(repo_root, "src/laplace/web/static_shared/cockpit-panes.mjs")
    srv = _read(repo_root, "src/laplace/web/growth_surface.py")
    low = mjs.lower()
    assert "growth/coverage" in low, (
        "coverage-vector-per-axis: the cockpit renders no per-axis coverage vector "
        "(per-claim literature / evidence / demonstration coverage, each a count that is its "
        "filter)")
    assert "coverage_vector" in srv, (
        "coverage-vector-per-axis: the growth surface does not serve the coverage vector")


def _v_taste_fusion(repo_root: Path) -> None:
    """FLOOR (bar mechanical): assemble_packet's taste channel reaches past keyword
    overlap over proxy_verdicts + promise asks - it consults the wider substrate (stage
    stores / profiles / embedding-or-metric ranking). Keyword-only retrieval over the
    explicit rulings is the failing state."""
    src = _read(repo_root, "src/laplace/engine/superego.py")
    wider = ("corpus_stores" in src or "author_architecture" in src
             or "embed" in src or "metric" in src)
    assert wider, (
        "judgement-fueled-by-his-corpus: the taste channel retrieves by keyword overlap "
        "over explicit rulings only - the implicit corpus never reaches the judge")


_ENGINE_PANES = {
    "storyboard-in-the-engine": "src/laplace/web/static_shared/storyboard-panes.mjs",
    "dashboard-in-the-engine": "src/laplace/web/dashboard.html",
    "desk-in-the-engine": "src/laplace/web/static_shared/desk-panes.mjs",
    "assets-in-the-engine": "src/laplace/web/static_shared/assets-panes.mjs",
    "project-in-the-engine": "src/laplace/web/static_shared/pipeline-panes.mjs",
}


def _v_surface_in_engine(cid: str):
    """FLOOR (bar mechanical, one per remaining surface): the pane rides engine.mjs and
    rests at a brief altitude. The probe is the import plus a brief marker - a surface
    that neither imports the runtime nor rests composed is outside the one instrument."""
    def probe(repo_root: Path) -> None:
        src = _read(repo_root, _ENGINE_PANES[cid])
        assert ("engine.mjs" in src and ("brief" in src.lower() or "composed" in src.lower())), (
            f"{cid}: the pane does not ride the engine runtime - the surface is still a "
            "page outside the one instrument")
    return probe


def _v_packets_carry_aim(repo_root: Path) -> None:
    """FLOOR (bar mechanical): compile_dispatch mints a composed head onto every packet -
    goal version/essence + the packet's role + what acceptance writes. Probes the kernel
    for the composed-head threading; instructions-plus-facts without the aim is the
    failing state (his ruling: builders should know where they're aiming)."""
    src = _read(repo_root, "src/laplace/pipeline/dispatch.py")
    assert ("composed" in src and ("aim" in src or "goal_essence" in src or "role_in_whole" in src)), (
        "packets-carry-the-aim: compile_dispatch threads facts and instructions but no "
        "composed aim head - builders receive work without where it is aiming")


def _v_architecture_profile(repo_root: Path) -> None:
    """FLOOR (bar mechanical): the narrative planners consume the author-architecture
    profile — a code path at the storyboard/dispatch stage reads
    profiles/author_architecture.yaml. The profile existing is NOT the floor; the
    consuming edge is (his charge: a profile nothing reads is a prose doc that rots)."""
    import re as _re
    hits = []
    for rel in ("src/laplace/manuscript/storyboard.py", "src/laplace/pipeline/dispatch.py",
                "src/laplace/pipeline/narrative.py", "src/laplace/pipeline/projection_spec.py"):
        try:
            if "author_architecture" in _read(repo_root, rel):
                hits.append(rel)
        except Exception:
            pass
    assert hits, (
        "architecture-profile-consumed: no planner/dispatch code reads "
        "profiles/author_architecture.yaml - the profile exists but nothing consumes it, "
        "which is exactly the rot this clause exists to make loud")


def _v_growth_queues(repo_root: Path) -> None:
    """FLOOR (bar judged): the growth queues + verbs render FROM the contract — a
    /surface/contract route + states:/queues: blocks in the yaml + one generic renderer. Today
    there is no /surface/contract route and no states:/queues: blocks."""
    route = False
    for p in (Path(repo_root) / "src" / "laplace").rglob("*.py"):
        if "/surface/contract" in p.read_text(encoding="utf-8", errors="replace"):
            route = True
            break
    yaml_has = False
    for p in (Path(repo_root) / "contract" / "surfaces").glob("*.yaml"):
        txt = p.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*(queues|states):", txt, re.M):
            yaml_has = True
            break
    assert route and yaml_has, (
        "growth-queues-conjugate-views: the growth queues do not render FROM the contract — "
        f"/surface/contract route={route}, states:/queues: contract blocks={yaml_has}")


# ---- dashboard (W-growth red) ---------------------------------------------
def _v_birth_lands(repo_root: Path) -> None:
    """FLOOR (bar mechanical): a New Project scaffold is born SEEDED with its goal node AND its
    demand audit has populated the growth queues before any compile. G2's birth bridge seeds
    SEEDED, but the queue-population conjunct is owed (no 'queues' in the SEEDED state). Probed
    in an isolated temp root; the real repo is never touched."""
    from laplace.web import dashboard
    from laplace.projects import project_creation
    from laplace.pipeline import growth
    tmp = Path(tempfile.mkdtemp(prefix="contract-birth-"))
    name = "probe-birth-clause-runner"
    try:
        status, out = project_creation.create_project(name, "conceptric", root=tmp)
        assert status == 201, (
            f"birth-lands-on-the-ladder: the New Project door did not create the scaffold "
            f"(status {status}: {out.get('error')})")
        gs = growth.growth_state(tmp, name)
        assert gs.get("present") and gs.get("state") == "SEEDED", (
            f"birth-lands-on-the-ladder: a fresh scaffold is not born SEEDED (got {gs.get('state')})")
        assert gs.get("queues"), (
            "birth-lands-on-the-ladder: born SEEDED but the demand audit has NOT populated the "
            "growth queues at birth (no 'queues' in the growth state) — the birth bridge's "
            "queue-population conjunct is owed (the demand audit is not wired into seed)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


#: clause id -> its bespoke behavioral probe. A structural clause with no entry here gets an
#: honest SKIP-with-reason from the runner (never a false green).
STRUCTURAL_VERIFIERS = {
    # green (behaviorally live; migrated verbatim from the per-surface tests)
    "work-order-consume-carries-evidence": _v_desk_consume,
    "action-organ-complete": _v_pipeline_action_organ,
    "state-machine-driven": _v_pipeline_state_machine,
    "next-action-rendered": _v_pipeline_next_action,
    # W-grammar reds
    "weighting-card-grounding-visible": _v_weighting_grounding,
    "cards-expand-in-place-with-context": _v_cards_expand,
    "asset-cockpit-close-examination": _v_asset_cockpit,
    "anchor-chips-door-to-named-asset": _v_anchor_chips,
    # W-growth reds
    "growth-ladder-live": _v_growth_ladder,
    "epistemic-status-one-home": _v_epistemic_status,
    "axes-typed-not-smuggled": _v_axes_typed,
    "goal-versioned-regoal-loop": _v_goal_regoal,
    "demand-audit-floor-honest": _v_demand_audit,
    "coverage-vector-per-axis": _v_coverage_vector,
    "growth-queues-conjugate-views": _v_growth_queues,
    "architecture-profile-consumed": _v_architecture_profile,
    "packets-carry-the-aim": _v_packets_carry_aim,
    "judgement-fueled-by-his-corpus": _v_taste_fusion,
    "storyboard-in-the-engine": _v_surface_in_engine("storyboard-in-the-engine"),
    "dashboard-in-the-engine": _v_surface_in_engine("dashboard-in-the-engine"),
    "desk-in-the-engine": _v_surface_in_engine("desk-in-the-engine"),
    "assets-in-the-engine": _v_surface_in_engine("assets-in-the-engine"),
    "project-in-the-engine": _v_surface_in_engine("project-in-the-engine"),
    "birth-lands-on-the-ladder": _v_birth_lands,
}


# ===========================================================================
# COUNTS VERIFIERS — one per surface declaring law chip-equals-filter.
# Each returns a note (verified) or raises CountsSkip (not reachable in-process) or
# AssertionError (the law is violated).
# ===========================================================================
def _c_desk(repo_root: Path) -> str:
    from laplace.web import desk
    d = desk._desk(desk._REPO_ROOT)
    declared = {c["class"]: c.get("count", 0) for c in d["classes"]}
    reachable = Counter(r.get("cls") or r.get("class") for r in d.get("rows", []))
    bad = []
    for c in d["classes"]:
        cls = c["class"]
        nd, nr = declared.get(cls, 0), reachable.get(cls, 0)
        if not (nd == nr or c.get("more_href")):
            bad.append(f"{cls}: chip {nd} vs reachable {nr}, no +N-more door")
    assert not bad, "desk chip-equals-filter violated — " + "; ".join(bad)
    return f"desk: {len(d['classes'])} class chips each equal client-reachable rows"


def _c_assets(repo_root: Path) -> str:
    from laplace.web import assets_surface
    checked = 0
    for proj in _projects(repo_root):
        lp = assets_surface.list_payload(proj)
        if not lp:
            continue
        strata = {s["id"]: s["count"] for s in lp["strata"]}
        assert strata.get("figures") == len(lp["figures"]) and \
            strata.get("derivations") == len(lp["derivations"]), (
            f"assets chip-equals-filter violated for {proj}: figures "
            f"{strata.get('figures')} vs {len(lp['figures'])}, derivations "
            f"{strata.get('derivations')} vs {len(lp['derivations'])}")
        checked += 1
    if not checked:
        raise CountsSkip("no project exposes an asset roster in-process")
    return f"assets: figures/derivations strata chips == reachable cards across {checked} project(s)"


def _c_conceptric(repo_root: Path) -> str:
    from laplace.engine import conceptric
    checked = 0
    for proj in _projects(repo_root):
        net = _net(repo_root, proj)
        if net is None:
            continue
        grades = sorted({n.get("grade") for n in net.get("nodes", {}).values()
                         if n.get("grade") is not None})
        for g in grades:
            gv = conceptric.grade_view(repo_root, net, g)
            n_total, reach, capped = (gv.get("n_total_at_grade"),
                                      len(gv.get("nodes", [])), gv.get("capped"))
            assert n_total == reach or capped, (
                f"conceptric chip-equals-filter violated: {proj} grade {g} chip {n_total} vs "
                f"reachable {reach}, not capped")
        checked += 1
        if checked >= 3:
            break
    if not checked:
        raise CountsSkip("no project resolves an in-process corpus network")
    return f"conceptric: grade chips == reachable nodes (or capped) across {checked} project(s)"


def _c_storyboard(repo_root: Path) -> str:
    raise CountsSkip(
        "the storyboard rank/coverage meter's chip-equals-filter needs the compiled residue "
        "walk (projection_viewer.residue), which is None for uncompiled projects — the coverage "
        "leg is not a plain reachable-rows count in-process")


COUNTS_VERIFIERS = {
    "desk": _c_desk,
    "assets": _c_assets,
    "conceptric": _c_conceptric,
    "storyboard": _c_storyboard,
}
