"""G4 — the demand registry, the token-free demand audit, the coverage vector +
goal-tension detector, and the refusal router (ARMING_2026-07-22, wave G4).

The four apex laws + the 20 D-demands of the manuscript FORM object live only as
prose in ``canon/wiki/workflow/manuscript_projection.md``; the token-free WALKING of
them is already built and scattered across ``pipeline/loop_gates.py``'s checks and
``verify.py``'s ``check_*`` functions. This module is the missing typed wrapper: the
demand FORM as DATA (id, ring, owning_check, friction_type, goal_activation), the
goal-conditioned audit that walks the registry over the SYMBOLIC substrate only, the
per-axis coverage vector, the DEMOTE goal-tension detector, and the refusal router.

Four laws hold throughout (his rulings, this session):
  * no model calls anywhere; deterministic; bounded outputs; absolute zero registers.
  * nothing changes any existing built network or existing check behaviour — this
    module only WRAPS ``verify.check_*`` / ``loop_gates`` (read-only) and READS
    ``corpus_ingest.corpus_network``. loop_gates.py / verify.py / propagate.py are
    never edited; the only schema touch is three ADDITIVE ``KIND_TO_WORK`` rows.
  * the audit's verdict vocabulary is floor-holds / red / judged-pending /
    not-runnable-here only — the word ``passed`` is structurally unavailable (the
    ``demand-audit-floor-honest`` red clause of ``conceptric.yaml``).
  * the ~7 oracle-tier demands carry NO mechanical check and render judged-pending by
    construction (the blind reader's; a mechanical green is never their verdict).

Every ambiguous enumeration choice is NAMED in the row's ``note`` rather than guessed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from laplace.pipeline import schema

# ---------------------------------------------------------------------------
# Deliverable 1 — THE DEMAND REGISTRY AS DATA
# ---------------------------------------------------------------------------
#
# The four apex rings, and the friction taxonomy the FORM object owns.
RINGS = ("I completeness", "II consistency", "III clarity", "IV presentation")
FRICTION_TYPES = ("CONTENT", "FORM", "TENSION")

#: The verdict vocabulary the audit may utter. ``passed`` is DELIBERATELY absent —
#: the demand-audit-floor-honest contract makes it structurally unavailable.
AUDIT_VERDICTS = ("floor-holds", "red", "judged-pending", "not-runnable-here", "inactive")

#: The verify checks that run on the SYMBOLIC substrate (corpus_network) with no
#: compile — the only checks the token-free audit can actually run. Everything else a
#: demand owns (rendered .tex checks, unbuilt house gates) is marked not-runnable-here.
_SYMBOLIC_CHECKS = frozenset(
    {"check_coherence", "check_figures", "check_substrate", "check_glossary"})

#: Each row realises exactly one demand of the prose FORM object. ``owning_check`` is
#: the loop_gates/verify function that realises it, ``demand:status_floor`` for the one
#: floor this module supplies (no pre-existing gate reads the G1 epistemic_status
#: slot — a NAMED GAP), ``oracle:<reader>`` for the judged-tier demands (no mechanical
#: check), or ``unbuilt:<canon-standard>`` for a Ring IV house demand no gate realises
#: yet (Ring IV points at the standard, it does not copy it). ``default_friction_type``
#: is the CONTENT/FORM/TENSION class an UNMET instance defaults to. ``goal_activation``
#: is ``always`` or ``goal-conditioned:<cond>``.
DEMANDS: tuple[dict[str, str], ...] = (
    # ---- Ring I — COMPLETENESS (every promised loop is closed) ----
    {"id": "D-roadmap", "ring": "I completeness",
     "owning_check": "oracle:blind_reader", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "the intro's roadmap-of-descent is a narrative promise; no symbolic "
             "graph gate reads it — the blind reader's verdict."},
    {"id": "D-sections-close-the-primitives", "ring": "I completeness",
     "owning_check": "oracle:blind_reader", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "each body section closes one promised primitive; a narrative judgement, "
             "not the connectivity gate (which only proves reachability, not closure)."},
    {"id": "D-every-claim-has-a-result", "ring": "I completeness",
     "owning_check": "verify:check_coherence", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "coherence: a res/thm/goal shell drawing from nothing below is a stub. "
             "CHOICE: coherence (has-a-result-below) over substrate (reaches-literature) "
             "— 'every claim traces to a result' is the level-below relation."},
    {"id": "D-figure-resolves", "ring": "I completeness",
     "owning_check": "verify:check_figures", "default_friction_type": "CONTENT",
     "goal_activation": "goal-conditioned:has-figures",
     "note": "figures: every fig node carries a provenance block resolving to a real "
             "asset/recipe. Asset EXISTENCE proper is Ring IV D-asset-existence-out-of-"
             "loop (rendered/out-of-band); this is the symbolic provenance floor."},
    {"id": "D-ends-on-the-frontier", "ring": "I completeness",
     "owning_check": "oracle:blind_reader", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "the conclusion ends on the open frontier, stated plainly; a narrative judgement."},
    # ---- Ring II — CONSISTENCY (no naked claims; one voice; stated status) ----
    {"id": "D-no-naked-claims", "ring": "II consistency",
     "owning_check": "verify:check_substrate", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "substrate: every claim node reaches ref:/sup: within 2 hops (grounded in "
             "an external reference OR an internal pointer). The RENDERED face is "
             "loop_gates orphan_numerals+bad_claim_tags; chose the symbolic substrate "
             "gate as owning so the audit runs on the wire (token-free law)."},
    {"id": "D-real-corpus-citation", "ring": "II consistency",
     "owning_check": "verify:check_corpus_citations", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "corpus-citations: a relied-on corpus ref never \\cite'd is a naked "
             "reliance. RENDERED (needs the manuscript + corpus bib) → the audit marks "
             "it not-runnable-here. Rendered loop-gate = bad_citekeys; symbolic proxy = "
             "substrate reaching a ref: node."},
    {"id": "D-honest-status", "ring": "II consistency",
     "owning_check": "demand:status_floor", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "NAMED GAP: G1 landed the epistemic_status node slot but NO verify/loop_"
             "gates gate reads it. status_floor (this module) is the symbolic floor — "
             "every load-bearing claim carries a status in EPISTEMIC_STATUSES. Default "
             "CONTENT (a claim lacking a stated status is thin); the TENSION flavour "
             "(status DEMOTES vs a goal that names it primary) is minted by the goal-"
             "tension detector, and tier fidelity (never-laundered) is result_foundry's "
             "judged call above the floor."},
    {"id": "D-equation-grounded", "ring": "II consistency",
     "owning_check": "verify:check_epistemic", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "epistemic: orphaned equation labels (every display eq introduced/\\ref'd). "
             "RENDERED → not-runnable-here. The symbol-grounding half overlaps "
             "check_glossary; the equation-introduced half is check_epistemic's orphans. "
             "always (not goal-conditioned): equation labels use corpus-specific prefixes "
             "(def:/res:/thm:, zero eq:) a symbolic has-equations probe cannot reliably "
             "see, and grounding is a universal content demand regardless."},
    {"id": "D-caption-true", "ring": "II consistency",
     "owning_check": "oracle:blind_reader", "default_friction_type": "TENSION",
     "goal_activation": "goal-conditioned:has-figures",
     "note": "a caption claims only what its panel shows — the theory→data→caption loop "
             "on the RENDERED figure; the blind reader's. TENSION when caption vs panel "
             "disagree."},
    {"id": "D-one-document", "ring": "II consistency",
     "owning_check": "oracle:blind_reader", "default_friction_type": "FORM",
     "goal_activation": "always",
     "note": "reads as one document through the seams — the welder's seam test, judged "
             "from outside by blind_reader. Surface unity → FORM (the welder never "
             "touches substance)."},
    # ---- Ring III — CLARITY (a stranger can follow the page) ----
    {"id": "D-motivated-sections", "ring": "III clarity",
     "owning_check": "oracle:blind_reader", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "every section carries a one-line 'we look at X because it reveals Y'; the "
             "blind reader's (Ring III's verdict is always the blind reader's)."},
    {"id": "D-define-before-use", "ring": "III clarity",
     "owning_check": "verify:check_glossary", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "glossary: the def: nodes ARE the registry (term declared, no collisions, "
             "no retired term reused) — the first-use census's symbolic home. The "
             "RENDERED face is loop_gates.lexicon_ladder (taught-before-used over "
             "draft_full.md); chose the symbolic glossary gate as owning so the audit "
             "runs on the wire."},
    {"id": "D-no-leaked-meta", "ring": "III clarity",
     "owning_check": "verify:check_meta_leak", "default_friction_type": "FORM",
     "goal_activation": "always",
     "note": "meta_leak: object_not_artefact over the compiled .tex. RENDERED → "
             "not-runnable-here. The leak is the artefact carrying meta → FORM."},
    {"id": "D-reader-floor", "ring": "III clarity",
     "owning_check": "oracle:blind_reader", "default_friction_type": "CONTENT",
     "goal_activation": "always",
     "note": "the reader's assumed floor is stated (the section contracts' reader entry "
             "states); the blind reader's."},
    # ---- Ring IV — PRESENTATION / FORMAT (the artefact wears the house) ----
    {"id": "D-house-document-class", "ring": "IV presentation",
     "owning_check": "unbuilt:canon://skills/latex_forge", "default_friction_type": "FORM",
     "goal_activation": "goal-conditioned:genre=manuscript",
     "note": "REVTeX4-2 / APS house class, not plain article. NO mechanical gate built; "
             "latex_forge owns the rule (Ring IV points, it does not copy). "
             "not-runnable-here (rendered + unbuilt). Inferred default per the doc's "
             "fork #1."},
    {"id": "D-figures-to-house-style", "ring": "IV presentation",
     "owning_check": "unbuilt:canon://skills/figure_standard", "default_friction_type": "FORM",
     "goal_activation": "goal-conditioned:has-figures",
     "note": "house figure style (viridis/Okabe-Ito, exact APS column widths, usetex CM "
             "serif). NO symbolic gate; figure_standard owns. not-runnable-here."},
    {"id": "D-house-typography-mechanics", "ring": "IV presentation",
     "owning_check": "verify:check_voice", "default_friction_type": "FORM",
     "goal_activation": "goal-conditioned:genre=manuscript",
     "note": "voice: the TYPOGRAPHY half (TikZ colours, reserved-keyword collisions, "
             "layout distortions) realises this. RENDERED → not-runnable-here. Prose-"
             "register mechanics moved to the versioned voice profile (2026-07-09)."},
    {"id": "D-forge-compiler", "ring": "IV presentation",
     "owning_check": "unbuilt:canon://skills/latex_forge", "default_friction_type": "FORM",
     "goal_activation": "goal-conditioned:genre=manuscript",
     "note": "compiled through the Forge chain, never raw pdflatex/latexmk. A PROCESS "
             "demand; no gate reads it. not-runnable-here."},
    {"id": "D-asset-existence-out-of-loop", "ring": "IV presentation",
     "owning_check": "unbuilt:canon://workflow/generation_discipline", "default_friction_type": "FORM",
     "goal_activation": "goal-conditioned:has-figures",
     "note": "asset existence is out-of-loop; a missing asset → prose fallback / an out-"
             "of-band registered TODO, never a rendered box in the body. check_figures "
             "provenance is the nearest symbolic proxy; existence proper is rendered. "
             "not-runnable-here. This is Ring IV's artefact-facing SHARPENING of "
             "D-figure-resolves — the +1 over the doc's approximate '20'."},
)

_DEMAND_BY_ID: dict[str, dict] = {d["id"]: d for d in DEMANDS}


def demand_by_id(demand_id: str) -> dict | None:
    """The registry row for ``demand_id``, or ``None``."""
    return _DEMAND_BY_ID.get(demand_id)


def registry_split() -> dict[str, Any]:
    """The registry's shape as data: total, per-ring counts, and the mechanical /
    oracle / unbuilt split. Deterministic, token-free."""
    per_ring: dict[str, int] = {r: 0 for r in RINGS}
    oracle: list[str] = []
    unbuilt: list[str] = []
    symbolic: list[str] = []
    rendered_or_unbuilt: list[str] = []
    for d in DEMANDS:
        per_ring[d["ring"]] += 1
        oc = d["owning_check"]
        if oc.startswith("oracle:"):
            oracle.append(d["id"])
        elif oc.startswith("unbuilt:"):
            unbuilt.append(d["id"])
            rendered_or_unbuilt.append(d["id"])
        elif oc == "demand:status_floor" or (
                oc.startswith("verify:") and oc.split(":", 1)[1] in _SYMBOLIC_CHECKS):
            symbolic.append(d["id"])
        else:
            rendered_or_unbuilt.append(d["id"])
    return {
        "total": len(DEMANDS),
        "per_ring": per_ring,
        "oracle_tier": sorted(oracle),
        "mechanical_tier": sorted(d["id"] for d in DEMANDS
                                  if not d["owning_check"].startswith("oracle:")),
        "runnable_here_symbolic": sorted(symbolic),
        "not_runnable_here": sorted(rendered_or_unbuilt),
        "unbuilt_ring_iv": sorted(unbuilt),
    }


# ---------------------------------------------------------------------------
# Substrate accessors — load-bearing claims, axis edges, the goal
# ---------------------------------------------------------------------------

def load_bearing(nodes: dict) -> list[str]:
    """The load-bearing claim nodes: id-prefix ``res:``/``thm:`` or node kind
    ``result`` (the ARMING's 'res:/thm:/result kinds'). Sorted, deterministic."""
    return sorted(nid for nid, n in nodes.items()
                  if nid.startswith(("res:", "thm:")) or (n or {}).get("kind") == "result")


def _result_nodes(nodes: dict) -> list[str]:
    """The RESULT-tier nodes for demonstration coverage: id-prefix ``res:`` or kind
    ``result`` (thm: theorems are results too, folded in — a theorem is demonstrated
    like a result)."""
    return sorted(nid for nid, n in nodes.items()
                  if nid.startswith(("res:", "thm:")) or (n or {}).get("kind") == "result")


def _axis_targets(net: dict, nid: str, axis: str, resolvable: bool = False) -> list[str]:
    """The referents on ``nid`` whose edge token parses to ``axis`` (schema.parse_edge_token
    — G1's one parser). ``resolvable`` keeps only targets that are live nodes (the
    validates-axis dereference). A bare referent (no axis marker) parses to None and is
    never counted, so an untyped derives edge never masquerades as coverage."""
    nodes = net.get("nodes") or {}
    out: list[str] = []
    for ref in (net.get("edge_index") or {}).get(nid, []):
        parsed = schema.parse_edge_token(ref)
        if parsed and parsed.get("axis") == axis:
            tgt = parsed.get("target") or ref
            if resolvable and tgt not in nodes:
                continue
            out.append(tgt)
    return out


def _axis_bearers(net: dict, nid: str, axis: str) -> list[str]:
    """The BEARER-KEYED read (the G3 judge's direction catch, reconciled): supports and
    demonstrates edges live on the node that bears (the ref:/fig: node) with the borne
    node as target — the axis sense, "literature bears a claim". Coverage for ``nid``
    therefore scans the whole edge index for any bearer whose token targets ``nid``.
    The one parser decodes; the emitters (leg 1 admission/born-edge, leg 3 assets) and
    this reader now agree on exactly one convention, matched by the schema grammar."""
    out: list[str] = []
    for bearer, refs in (net.get("edge_index") or {}).items():
        for ref in refs:
            parsed = schema.parse_edge_token(ref)
            if parsed and parsed.get("axis") == axis and parsed.get("target") == nid:
                out.append(bearer)
    return out


def status_floor(net: dict) -> dict[str, Any]:
    """The symbolic floor for D-honest-status (no pre-existing gate reads the G1
    epistemic_status slot). Every load-bearing claim node must carry a status resolving
    into ``schema.EPISTEMIC_STATUSES`` (via ``canonical_status``, so a legacy carrier
    folds). Returns the fail-names-node-ids shape. ``pass`` is the internal boolean; the
    audit NEVER surfaces it as 'passed'."""
    nodes = net.get("nodes") or {}
    lb = load_bearing(nodes)
    missing = [nid for nid in lb
               if schema.canonical_status((nodes[nid] or {}).get("status")) is None]
    return {"pass": not missing, "load_bearing": len(lb),
            "missing_status": sorted(missing)}


# ---------------------------------------------------------------------------
# Deliverable 3 — THE COVERAGE VECTOR (per-axis, relative to the goal) + goal-tension
# ---------------------------------------------------------------------------

def _read_goal(repo_root: Path | str, corpus: str, net: dict) -> dict[str, Any]:
    """The goal the coverage vector is relative to: the goal node essences (from the
    net), plan ``meta.contribution_rank`` primaries where present, and ``goal_version``
    from the growth sidecar if present. Every read is READ-ONLY and tolerant — a missing
    plan/sidecar degrades to an empty field, never a crash."""
    nodes = net.get("nodes") or {}
    goal_nodes = sorted(nid for nid, n in nodes.items()
                        if nid.startswith("goal:") or (n or {}).get("kind") == "goal")
    essences = [(nodes[g] or {}).get("essence", "") for g in goal_nodes]
    primary: list[str] = []
    try:  # plan.meta.contribution_rank — the one authored judgement (schema's one decode)
        from laplace.pipeline import registry
        proj = registry.resolve(corpus)
        plan = proj.read_plan(Path(repo_root)) if proj is not None else None
        meta = ((plan or {}).get("meta") or {})
        primary, _excluded = schema.contribution_rank_lines(meta.get("contribution_rank"))
    except Exception:
        pass
    goal_version = None
    try:  # the growth sidecar (read-only; growth.py is never edited)
        from laplace.pipeline import growth
        goal_version = growth.growth_state(repo_root, corpus).get("goal_version")
    except Exception:
        pass
    return {"goal_nodes": goal_nodes, "essences": essences,
            "contribution_rank_primary": primary, "goal_version": goal_version}


def coverage_over_net(net: dict, goal: dict | None = None) -> dict[str, Any]:
    """The per-axis coverage vector over a built network — the pure, testable core.
    Each component IS its filter (count + the uncovered ids); denominators are REAL (the
    live load-bearing set), so an empty axis renders 0/N with a real denominator, never a fake or a
    crash. Zeros are real: the supports/validates/demonstrates axes are empty until G3
    lands the typed edges — the vector shows 0/N with N real, by construction."""
    nodes = net.get("nodes") or {}
    lb = load_bearing(nodes)
    results = _result_nodes(nodes)

    def _frac(ids: list[str], axis: str, resolvable: bool = False,
              bearer_keyed: bool = False) -> dict:
        covered = [nid for nid in ids
                   if (_axis_bearers(net, nid, axis) if bearer_keyed
                       else _axis_targets(net, nid, axis, resolvable=resolvable))]
        return {"axis": axis, "covered": len(covered), "total": len(ids),
                "fraction": (len(covered) / len(ids)) if ids else 0.0,
                "uncovered": sorted(set(ids) - set(covered))}

    return {
        "goal": goal or {},
        "load_bearing_claims": len(lb),
        "result_nodes": len(results),
        "literature": _frac(lb, "supports", bearer_keyed=True),
        "validation": _frac(lb, "validates", resolvable=True),
        "demonstration": _frac(results, "demonstrates", bearer_keyed=True),
    }


def coverage_vector(repo_root: Path | str, corpus: str) -> dict[str, Any]:
    """The coverage vector for a registered corpus (resolves the net + the goal, then
    ``coverage_over_net``). READ-ONLY."""
    net = _net(repo_root, corpus)
    goal = _read_goal(repo_root, corpus, net)
    out = coverage_over_net(net, goal)
    out["corpus"] = corpus
    # the composition layer: each axis is a coverage row (glance+working, decision null).
    # Composed on the wrapper's copy so coverage_over_net's pure shape is untouched.
    from laplace.pipeline import composed as _composed
    gv = goal.get("goal_version")
    for key in ("literature", "validation", "demonstration"):
        ax = out.get(key)
        if isinstance(ax, dict):
            ax["composed"] = _composed.compose_coverage_row(
                axis=ax.get("axis", key), covered=ax.get("covered", 0),
                total=ax.get("total", 0), goal_version=gv, route=True)
    return out


#: The demoted epistemic statuses — a load-bearing claim wearing one of these while the
#: goal names it primary is the DEMOTE goal-tension signature (the queue's substance).
DEMOTED_STATUSES = ("conjectured", "exploratory")


def goal_tensions_over_net(net: dict, *, goal_version: int | None = None,
                           goal_essences: list | None = None) -> list[dict[str, Any]]:
    """The goal-tension detector v1 — the DEMOTE signature ONLY. A load-bearing node
    whose epistemic status is conjectured/exploratory while the goal names it primary
    mints a typed TENSION row. CHOICE (named): 'the goal names it primary' is proxied by
    SPINE membership — the apex narrative chain IS the headline results (his 2026-06-29
    ruling); the richer contribution_rank primary→node linkage rides a section's serves-
    ref, which is G3 territory, so v1 reads the spine. A real zero: no node carries a
    status yet (G3 writes them), so this returns [] on today's corpora — wired, not
    faked."""
    nodes = net.get("nodes") or {}
    spine_ids = {s["id"] for s in (net.get("spine") or [])}
    rows: list[dict[str, Any]] = []
    from laplace.pipeline import composed as _composed
    for nid in load_bearing(nodes):
        status = schema.canonical_status((nodes[nid] or {}).get("status"))
        if nid in spine_ids and status in DEMOTED_STATUSES:
            row = {
                "node_id": nid, "signature": "DEMOTE", "status": status,
                "friction_type": "TENSION", "demand": "D-honest-status",
                "detail": f"load-bearing spine node {nid} carries demoted status "
                          f"{status!r} while the goal names the spine primary — "
                          "REGOAL / HOLD / REJECT is his jurisdiction, machine-proposed",
            }
            # the composition layer: the detector holds the drift context at detection,
            # so it composes here — is_fresh is true at emit by construction.
            gt_id, block = _composed.compose_tension(
                node_id=nid, signature="DEMOTE", status=status,
                goal_version=goal_version, goal_essences=goal_essences)
            row["id"] = gt_id
            row["composed"] = block
            rows.append(row)
    return rows


def goal_tensions(repo_root: Path | str, corpus: str) -> list[dict[str, Any]]:
    """The DEMOTE goal-tensions for a registered corpus. READ-ONLY."""
    net = _net(repo_root, corpus)
    goal = _read_goal(repo_root, corpus, net)
    return goal_tensions_over_net(net, goal_version=goal.get("goal_version"),
                                  goal_essences=goal.get("essences"))


# ---------------------------------------------------------------------------
# The SECOND drift signature — the authored-goal reconciliation tension.
# ---------------------------------------------------------------------------
#
# Mechanical over typed records, no inference: a proxy-verdict row of kind
# ``author-goal`` at confidence ``GENUINELY-HIS`` whose evidence names this corpus, with
# NO goal supersede in the corpus rewire ledger postdating it, means the authored goal
# statement has not been reconciled with the banked goal node — a role tension his to
# rule through the cockpit. A DISMISS suppression (fingerprinted on the tension content)
# drops it until the goal material or his statement changes.


def _verdict_names_corpus(verdict: dict, corpus: str) -> bool:
    """Whether an ``author-goal`` verdict's evidence paths name this corpus — a plain
    substring match on the corpus id, so the binding is over the typed evidence field,
    never inferred from prose."""
    ev = verdict.get("evidence") or []
    return any(isinstance(e, str) and corpus in e for e in ev)


def _goal_supersede_postdates(repo_root: Path | str, corpus: str, when: str) -> bool:
    """Whether the corpus rewire ledger carries a goal supersede (an ``add-node`` naming
    an older node in ``supersedes``) whose ts postdates ``when`` — the mechanical reading
    of "reconciled". A missing ledger reads as no supersede, never a crash."""
    try:
        from laplace.research import corpus_ingest as _ci
        recs = _ci.rewire_list(repo_root, corpus)
    except Exception:  # noqa: BLE001 — a roster hiccup reads as not-yet-reconciled
        return False
    for r in recs:
        if r.get("kind") == "add-node" and (r.get("supersedes") or "").strip():
            if str(r.get("ts") or "") > str(when or ""):
                return True
    return False


def _corpus_feedback_ledger(repo_root: Path | str, corpus: str):
    """The corpus' one feedback ledger (``<plan target_dir>/feedback/feedback.jsonl``),
    resolved through the registry-fenced plan — the store the DISMISS suppression writes
    to and this reader loads suppressions from. ``None`` when the corpus has no plan."""
    from pathlib import Path as _P
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
    root = _P(repo_root).resolve()
    led = (root / target / "feedback" / "feedback.jsonl").resolve()
    try:
        led.relative_to(root)
    except ValueError:
        return None
    return led


#: the finding-kind a DISMISS suppression silences on the tension's gt_id.
AUTHOR_GOAL_KIND = "author-goal-tension"


def _reconstruct_authored_goal(banked_essence: str) -> str:
    """The provisional goal text REGOAL shows before any supersede — a synthesis of his
    restatement, marked as a reconstruction so it is confirmed or corrected, never minted
    as authored text silently. Deterministic so the confirm gate is stable across reads."""
    marker = "Reconstructed goal (confirm or correct this before it is saved): "
    body = ("A FALQON-based methodological development using mid-circuit measurements — how to "
            "run this class of measurement-driven iterative algorithm in a clever, coherent "
            "manner, and what that coherence gains — with the 30-site Fermi-Hubbard resource "
            "estimate as a separate supporting part.")
    return marker + body


def author_goal_tensions(repo_root: Path | str, corpus: str) -> list[dict[str, Any]]:
    """The authored-goal reconciliation tensions for a corpus (the second signature).
    READ-ONLY. Fires when a GENUINELY-HIS ``author-goal`` verdict names this corpus and no
    goal supersede postdates it; drops when a fingerprint-matching DISMISS suppression is
    active. Each row carries its composed block whole (the four verbs, REGOAL recommended,
    the confirm reconstruction on REGOAL's row)."""
    from laplace.engine import author_proxy
    from laplace.pipeline import composed as _composed
    from laplace.pipeline import suppress as _suppress

    net = _net(repo_root, corpus)
    goal = _read_goal(repo_root, corpus, net)
    goal_nodes = goal.get("goal_nodes") or []
    goal_node_id = goal_nodes[0] if goal_nodes else "goal"
    banked_essence = next((e for e in (goal.get("essences") or []) if str(e).strip()), "")
    goal_version = goal.get("goal_version")

    verdicts = author_proxy.load_verdicts(repo_root)
    candidates: list[dict[str, Any]] = []
    for v in verdicts:
        if v.get("kind") != "author-goal" or v.get("confidence") != "GENUINELY-HIS":
            continue
        if not _verdict_names_corpus(v, corpus):
            continue
        if _goal_supersede_postdates(repo_root, corpus, v.get("date") or ""):
            continue
        gt_id, block = _composed.compose_author_goal_tension(
            corpus=corpus, goal_node_id=goal_node_id, banked_goal_essence=banked_essence,
            restatement_gist=str(v.get("ruling") or "")[:400],
            reconstruction=_reconstruct_authored_goal(banked_essence),
            gen_note="that reshaping is already queued on the manuscript's current generation",
            goal_version=goal_version, verdict_ref=str(v.get("id") or ""))
        candidates.append({
            "id": gt_id, "node_id": goal_node_id, "signature": "AUTHOR-GOAL",
            "friction_type": "TENSION", "demand": "D-honest-status",
            "verdict_id": v.get("id"),
            "detail": "an authored-goal statement banked in his words, unreconciled with the "
                      "banked goal node — his ruling through the cockpit",
            "composed": block,
        })

    if not candidates:
        return []

    # DISMISS suppression: fingerprinted on the tension content, so the same detection
    # stays dismissed until the goal material or his statement changes (suppress.py).
    led = _corpus_feedback_ledger(repo_root, corpus)
    if led is None or not led.is_file():
        return candidates
    supps = _suppress.load_suppressions(led)
    if not supps:
        return candidates
    findings = [{"node_id": c["id"], "kind": AUTHOR_GOAL_KIND} for c in candidates]
    node_text = {c["id"]: (c["composed"]["glance"] + c["composed"]["working"]) for c in candidates}
    split = _suppress.filter_findings(findings, supps, node_text)
    dropped = {f["node_id"] for f in split["suppressed"]}
    return [c for c in candidates if c["id"] not in dropped]


# ---------------------------------------------------------------------------
# Deliverable 2 — THE DEMAND AUDIT (token-free, symbolic substrate only)
# ---------------------------------------------------------------------------

def _net(repo_root: Path | str, corpus: str) -> dict:
    """Build the corpus network for a registered corpus — the SYMBOLIC wire only
    (semantic OFF, the human overlay applied). Raises ValueError if the corpus does not
    resolve (a caller passing a bad name should hear it, not get a fake floor)."""
    from laplace.research import corpus_ingest as ci
    troot = ci.resolve_corpus(repo_root, corpus)
    if troot is None:
        raise ValueError(f"corpus {corpus!r} does not resolve to a tex root "
                         "(registry.conceptric_projects / main.tex gate)")
    return ci.corpus_network(troot, repo_root=repo_root, name=corpus)


def _activated(demand: dict, net: dict) -> bool:
    """Whether a goal-conditioned demand is active for this corpus. ``always`` is always
    active; ``has-figures``/``has-equations`` read the substrate; ``genre=manuscript``
    is True for v1 (every registered corpus is a manuscript — the slides/talk kind is a
    banked later order, ARMING 'deferred')."""
    ga = demand["goal_activation"]
    if ga == "always":
        return True
    cond = ga.split(":", 1)[1] if ":" in ga else ""
    nodes = net.get("nodes") or {}
    if cond == "has-figures":
        return any(nid.startswith("fig:") for nid in nodes)
    if cond == "has-equations":
        return any(nid.startswith("eq:") for nid in nodes)
    if cond == "genre=manuscript":
        return True
    return True


def _check_node_ids(check_name: str, result: dict) -> list[str]:
    """The fail-names-node-ids extraction, per symbolic check — the seven-gate shape
    reused (each gate names the node ids that fail it)."""
    if check_name == "check_coherence":
        return list(result.get("under_described") or [])
    if check_name == "check_substrate":
        return list(result.get("unscaffolded") or [])
    if check_name == "check_figures":
        return [d.get("node") for d in (result.get("defects") or []) if d.get("node")]
    if check_name == "check_glossary":
        ids = list(result.get("missing_term") or [])
        for owners in (result.get("collisions") or {}).values():
            ids.extend(owners)
        ids.extend(h.get("node") for h in (result.get("deprecated_hits") or []) if h.get("node"))
        return sorted(set(ids))
    return []


def audit(repo_root: Path | str, corpus: str,
          goal_conditioned: bool = True) -> dict[str, Any]:
    """The token-free demand audit — walk the registry over the SYMBOLIC substrate only,
    emitting one typed row per demand. Its verdict vocabulary is
    floor-holds / red / judged-pending / not-runnable-here / inactive — the word
    ``passed`` is structurally unavailable (the conceptric.yaml demand-audit-floor-honest
    contract). NEVER calls a model; deterministic; bounded; nothing is written and no
    check behaviour changes (the checks are wrapped, never edited).

    Per demand:
      * ``oracle:<reader>`` → ``judged-pending`` (the ~7 blind-reader demands, no
        mechanical verdict, by construction);
      * a SYMBOLIC verify check (or ``demand:status_floor``) → run it on the wire and
        emit ``red`` with the failing node_ids, or ``floor-holds`` when the floor holds;
      * a RENDERED verify check (epistemic/voice/meta_leak/corpus_citations) or an
        ``unbuilt`` Ring IV house demand → ``not-runnable-here`` (a compile or an
        unbuilt gate is out of the symbolic audit's reach, and the row says so).

    Returns ``{corpus, rows, summary}`` where each row carries ``{demand_id, ring,
    friction_type, node_ids, detail, verdict}`` — the CONTENT rows reusing the seven-gate
    fail-names-node-ids shape.
    """
    from laplace.pipeline import verify as _verify

    net = _net(repo_root, corpus)
    goal_version = None
    try:
        goal_version = _read_goal(repo_root, corpus, net).get("goal_version")
    except Exception:  # noqa: BLE001 - a missing goal degrades to None, never a crash
        goal_version = None
    rows: list[dict[str, Any]] = []

    for d in DEMANDS:
        oc = d["owning_check"]
        activated = _activated(d, net) if goal_conditioned else True
        row: dict[str, Any] = {
            "demand_id": d["id"], "ring": d["ring"],
            "friction_type": d["default_friction_type"],
            "owning_check": oc, "goal_activation": d["goal_activation"],
            "activated": activated, "node_ids": [], "detail": "", "verdict": None,
        }
        if not activated:
            row["verdict"] = "inactive"
            row["detail"] = f"goal-conditioned ({d['goal_activation']}) — inactive for this corpus"
            rows.append(row)
            continue
        if oc.startswith("oracle:"):
            row["verdict"] = "judged-pending"
            row["detail"] = (f"oracle-tier ({oc.split(':', 1)[1]}) — no mechanical check; "
                             "renders judged-pending by construction, never green")
            rows.append(row)
            continue
        if oc == "demand:status_floor":
            res = status_floor(net)
            ids = res["missing_status"]
            row["node_ids"] = ids
            row["verdict"] = "red" if ids else "floor-holds"
            row["detail"] = (f"{len(ids)}/{res['load_bearing']} load-bearing claims carry "
                             "no epistemic_status in the enum (G1 slot, no gate reads it)")
            rows.append(row)
            continue
        if oc.startswith("verify:"):
            check_name = oc.split(":", 1)[1]
            if check_name in _SYMBOLIC_CHECKS:
                fn = getattr(_verify, check_name)
                res = fn(corpus)
                if res.get("pass") is None:      # the check itself could not run
                    row["verdict"] = "not-runnable-here"
                    row["detail"] = res.get("note") or "check returned manual/None"
                else:
                    ids = _check_node_ids(check_name, res)
                    row["node_ids"] = ids
                    row["verdict"] = "red" if ids else "floor-holds"
                    row["detail"] = f"{check_name}: {len(ids)} failing node(s)"
                rows.append(row)
                continue
            # a RENDERED verify check — needs a compiled artefact the symbolic audit lacks
            row["verdict"] = "not-runnable-here"
            row["detail"] = (f"{check_name} needs a rendered artefact (compiled .tex / "
                             "corpus bib) — out of the token-free audit's reach")
            rows.append(row)
            continue
        if oc.startswith("unbuilt:"):
            row["verdict"] = "not-runnable-here"
            row["detail"] = (f"Ring IV house demand — no gate built; {oc.split(':', 1)[1]} "
                             "owns the rule (Ring IV points, it does not copy)")
            rows.append(row)
            continue
        # defensive: an unrecognised owning_check renders not-runnable, never green
        row["verdict"] = "not-runnable-here"
        row["detail"] = f"unrecognised owning_check {oc!r}"
        rows.append(row)

    # the composition layer: each audit row is a queue item — glance+working, decision
    # null (the row's real doors today are reads). Composed in one pass after the rows
    # are fully built, each with a stable DQ- id addressable across recomputations.
    from laplace.pipeline import composed as _composed
    for row in rows:
        dq_id, block = _composed.compose_audit_row(
            demand_id=row["demand_id"], verdict=row["verdict"],
            node_ids=row["node_ids"], detail=row["detail"], goal_version=goal_version)
        row["id"] = dq_id
        row["composed"] = block

    verdicts = [r["verdict"] for r in rows]
    summary = {
        "corpus": corpus,
        "n_demands": len(rows),
        "red": sum(1 for v in verdicts if v == "red"),
        "floor_holds": sum(1 for v in verdicts if v == "floor-holds"),
        "judged_pending": sum(1 for v in verdicts if v == "judged-pending"),
        "not_runnable_here": sum(1 for v in verdicts if v == "not-runnable-here"),
        "inactive": sum(1 for v in verdicts if v == "inactive"),
        "by_ring": {r: sum(1 for row in rows if row["ring"] == r) for r in RINGS},
        "by_friction": {f: sum(1 for row in rows if row["friction_type"] == f)
                        for f in FRICTION_TYPES},
    }
    return {"corpus": corpus, "rows": rows, "summary": summary}


# ---------------------------------------------------------------------------
# Deliverable 4 — THE REFUSAL ROUTER
# ---------------------------------------------------------------------------
#
# A REFUTED (or partial-STANDS) verdict is routed, never shelved. Each served=no|partial
# question and each defect mints a typed feedback record; the records run through the one
# intake door (``propagate.intake_items``, which RAISES on an unrouted kind by design).
# The three friction classes route to the three growth stages — the mapping below, and
# the three ADDITIVE schema.KIND_TO_WORK rows registered at the foot of this module:
#   CONTENT  → growth mining      (kind ``growth-content`` → work ``mint`` → projection)
#   FORM     → the demand registry (kind ``growth-form``   → None: a registry edit, the
#                                    author-gated comment idiom, no builder work item)
#   TENSION  → the goal-tension queue (kind ``growth-tension`` → None: an author ruling,
#                                    REGOAL/HOLD/REJECT — his jurisdiction, not builder work)
# Only CONTENT demands NEW SUBSTANCE (a real work item); FORM/TENSION are adjudication-
# tier, so they route through the same door as routed comments (the None idiom the desk-
# review kinds already use). No new WORK_TO_LAYER row is needed — ``mint`` already maps to
# ``projection`` and the None kinds carry no work stage.

FRICTION_TO_KIND = {"CONTENT": "growth-content", "FORM": "growth-form",
                    "TENSION": "growth-tension"}
FRICTION_TO_STAGE = {"CONTENT": "growth-mining", "FORM": "demand-registry",
                     "TENSION": "goal-tension-queue"}


def _friction_of(item: dict) -> str:
    """The friction class of a question/defect. An explicit ``friction`` field wins; else
    a ``demand`` field looks the class up in the demand registry (closing the loop —
    deliverable 1 drives deliverable 4); else CONTENT (a content gap is the modal
    refusal). NAMED default."""
    explicit = str(item.get("friction") or "").upper()
    if explicit in FRICTION_TYPES:
        return explicit
    dem = item.get("demand")
    if dem and dem in _DEMAND_BY_ID:
        return _DEMAND_BY_ID[dem]["default_friction_type"]
    return "CONTENT"


def _feedback_record(idx: int, verdict: dict, source: str, text: str,
                     node_id: str | None, kind: str, project: str | None) -> dict:
    """One schema.FEEDBACK_FIELDS-shaped record minted from a refusal row — the intake
    door's one typed shape. ``supersedes`` is None (a fresh finding); ``status`` is left
    open by omission (intake reads absent status as open)."""
    return {
        "id": f"FB-refusal-{idx:03d}",
        "project": project or "",
        "ts": "",
        "scope": "node",
        "kind": kind,
        "node_id": node_id or "",
        "section": "",
        "text": text,
        "source": f"superego:{verdict.get('id', '')}:{source}",
        "anchor": {},
        "supersedes": None,
    }


def route_refusal(repo_root: Path | str, verdict_record: dict,
                  project: str | None = None, plan: dict | None = None,
                  net: dict | None = None) -> dict[str, Any]:
    """Route a REFUTED (or partial-STANDS) verdict — the re-task path. Walk the verdict's
    served=no|partial question rows and its defects, mint one typed feedback record each,
    and run them all through the one intake door (``propagate.intake_items``) so the
    routing is the pipeline's, not this router's. Never writes — pure, like propagate;
    the caller banks nothing here (his 'never a write outside the one intake door').

    Returns::

        {claim, verdict, minted, routed, work_items, sticky_questions, counts}

    where ``minted`` are the feedback records, ``routed`` is the per-row class/kind/stage
    summary, ``work_items`` are the typed items intake produced (the CONTENT→mint ones;
    FORM/TENSION route as author-gated comments, no item), ``sticky_questions`` is the
    unserved question set a caller re-asks (the questions stay on the object until banked
    served or ruled moot), and ``counts`` is the CONTENT/FORM/TENSION tally.

    ``project``/``plan``/``net`` are optional: with none, intake routes against an empty
    plan/substrate (a mint item passes its node through as target unknown) — the router
    stands alone on a synthetic verdict; with a real project they thread through so a
    known node resolves to its section.
    """
    from laplace.pipeline import propagate

    questions = verdict_record.get("questions") or []
    defects = verdict_record.get("defects") or []

    minted: list[dict] = []
    routed: list[dict] = []
    sticky: list[str] = []
    idx = 0

    for q in questions:
        if q.get("served") not in ("no", "partial"):
            continue
        qtext = str(q.get("question") or "")
        sticky.append(qtext)
        fr = _friction_of(q)
        kind = FRICTION_TO_KIND[fr]
        minted.append(_feedback_record(idx, verdict_record, "question", qtext,
                                       q.get("node_id"), kind, project))
        routed.append({"source": "question", "served": q.get("served"),
                       "friction": fr, "kind": kind, "owning_stage": FRICTION_TO_STAGE[fr],
                       "demand": q.get("demand"), "text": qtext[:200]})
        idx += 1

    for d in defects:
        what = str(d.get("what") or "")
        fr = _friction_of(d)
        kind = FRICTION_TO_KIND[fr]
        minted.append(_feedback_record(idx, verdict_record, "defect", what,
                                       d.get("node_id"), kind, project))
        routed.append({"source": "defect", "severity": d.get("severity"),
                       "friction": fr, "kind": kind, "owning_stage": FRICTION_TO_STAGE[fr],
                       "demand": d.get("demand"), "text": what[:200]})
        idx += 1

    # through the one door — intake_items RAISES on an unrouted kind, so this proves the
    # three growth kinds are registered; it yields the CONTENT→mint work items and drops
    # the FORM/TENSION None-routed records as author-gated comments.
    net_nodes = (net or {}).get("nodes") or {}
    work_items = propagate.intake_items(minted, plan or {}, net_nodes)

    # dedupe sticky, order preserved
    seen: set[str] = set()
    sticky_unique = [q for q in sticky if not (q in seen or seen.add(q))]

    counts = {f: sum(1 for r in routed if r["friction"] == f) for f in FRICTION_TYPES}
    return {
        "claim": verdict_record.get("claim"),
        "verdict": verdict_record.get("verdict"),
        "minted": minted,
        "routed": routed,
        "work_items": work_items,
        "sticky_questions": sticky_unique,
        "counts": counts,
    }
