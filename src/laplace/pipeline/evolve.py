"""The native ``evolve`` operator — execute an evolution contract, mechanised.

The canon skill (``canon://skills/conceptric_evolution``) states the six-step
procedure the two banked contracts hand-ran; this module is that procedure as
code. An evolution arrives as a directory holding ``evolution_plan.json`` (the
CONTRACT) plus banked sources; executing it means: freeze the ledgers, translate
the contract's enumeration into append-only L1 rewire records, land them inside
ONE transaction, and round-trip the live node-id set against the contract's own
enumeration — exact or the transaction truncates back.

The two banked shapes this loader must take AS-IS (their field variations are
the generality proof, pinned by ``tests/test_pipeline_evolve.py``):

- **substrate-led** (``v2_to_v3_spectral_surfacing``): ``mints`` carry ``kind``
  + ``projection_seed`` + ``edges`` as ``[{"target": id}, …]``; ``reshapes``
  carry optional ``essence``/``projection_merge``; ``deprecations`` are
  TERM-shaped (``successor_def`` + ``deprecated_aliases``), not node retirals.
- **storyboard-led** (``general_first_restructure_2026-07-08``): the one mint
  carries ``node_kind`` + ``provenance`` + ``edges`` as plain id strings; the
  arc lives in ``spine_reorder.new_order`` (not the schema's ``target_arc``
  name) and the rulings under a dated ``meta`` key; ``reshapes_placement`` is a
  PLAN regeneration, which is the :func:`plan_leg` seam, not substrate records.

The laws enforced here: fold by ledger never replay (a re-run mints nothing new,
fails the round trip, and rolls back) · deprecate projections keep nodes (no
contract path ever emits ``delete-node``) · the plan is downstream (the
storyboard leg is an explicit, deferred hand-off) · round-trip exact or stop.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from laplace.pipeline import ledger as _ledger
from laplace.pipeline import registry, schema


class EvolveError(RuntimeError):
    """A contract violation. Raised INSIDE the transaction so the ledgers
    truncate back to their entry offsets — append-only stays true."""


# ---------------------------------------------------------------------------
# Loading — parse + validate, tolerating both banked shapes
# ---------------------------------------------------------------------------

def _mint_kind(mint: dict) -> str:
    """``kind`` (v2→v3) or ``node_kind`` (general-first) — one accessor."""
    return mint.get("kind") or mint.get("node_kind") or ""


def _mint_edges(mint: dict) -> list[str]:
    """Edge targets, whichever spelling: ``[{"target": id}]`` or ``[id, …]``."""
    out = []
    for e in mint.get("edges") or []:
        t = e.get("target") if isinstance(e, dict) else e
        if t:
            out.append(t)
    return out


def contract_shapes(contract: dict) -> list[str]:
    """Which of the two banked directions the contract carries (it may carry
    both — the general-first restructure mints AND reorders the spine)."""
    shapes: list[str] = []
    if any(contract.get(k) for k in schema.EVOLUTION_SUBSTRATE_SECTIONS):
        shapes.append("substrate")
    storyboard_keys = set(schema.EVOLUTION_STORYBOARD_SECTIONS) | {"spine_reorder"}
    meta = contract.get("meta") or {}
    if (any(contract.get(k) for k in storyboard_keys)
            or any(str(k).startswith("rulings") for k in meta)):
        shapes.append("storyboard")
    return shapes


def load_contract(evolution_dir: Path | str) -> dict:
    """Parse ``evolution_plan.json`` and validate it against the schema's
    required meta + recognised section shapes. The sidecar ``_essences.json``
    (when banked beside the plan) is folded in so :func:`plan_records` stays
    IO-free. The evolution dir itself is READ-ONLY — nothing here writes."""
    d = Path(evolution_dir)
    plan_path = d / "evolution_plan.json"
    if not plan_path.is_file():
        raise EvolveError(f"no evolution_plan.json in {d}")
    try:
        contract = json.loads(plan_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise EvolveError(f"unparseable contract {plan_path}: {e}") from e

    meta = contract.get("meta") or {}
    missing = [k for k in schema.EVOLUTION_META_REQUIRED if k not in meta]
    if missing:
        raise EvolveError(f"contract meta missing {missing} (required: "
                          f"{schema.EVOLUTION_META_REQUIRED})")
    shapes = contract_shapes(contract)
    if not shapes:
        raise EvolveError(
            "no recognised evolution sections — expected some of "
            f"{schema.EVOLUTION_SUBSTRATE_SECTIONS} (substrate-led) or "
            f"{schema.EVOLUTION_STORYBOARD_SECTIONS}/spine_reorder (storyboard-led)")

    from laplace.research.corpus_ingest import LOGICAL_KINDS
    for m in contract.get("mints") or []:
        if not m.get("id"):
            raise EvolveError(f"mint without id: {m}")
        if _mint_kind(m) not in LOGICAL_KINDS:
            raise EvolveError(f"mint {m['id']}: kind/node_kind "
                              f"{_mint_kind(m)!r} not in LOGICAL_KINDS")

    ess = d / "_essences.json"
    try:
        contract["_essences"] = (json.loads(ess.read_text(encoding="utf-8"))
                                 if ess.is_file() else {})
    except json.JSONDecodeError:
        contract["_essences"] = {}
    contract["_evolution"] = d.name          # the ledger-stamp identity
    contract["_dir"] = str(d)
    contract["_shapes"] = shapes
    return contract


# ---------------------------------------------------------------------------
# Planning — the PURE contract → records map (what golden masters pin)
# ---------------------------------------------------------------------------

def plan_records(contract: dict, project: registry.Project | None = None,
                 repo_root: Path | str | None = None) -> list[dict]:
    """The ordered L1 rewire payloads a contract enumerates. Pure — no IO, no
    ids/timestamps (``rewire_add`` stamps those at append time).

    Per mint: ``add-node`` (essence from the seed or the ``_essences`` sidecar;
    the FIRST edge rides the birth record's ``target``, the v2→v3 convention) +
    one ``set-projection`` seed + ``add-edge`` for the rest. Per reshape:
    ``edit-essence`` when the contract carries the text, ``set-projection`` for
    the merge. Deprecations retire PROJECTIONS (never ``delete-node``); the
    term-shaped kind maps aliases onto the successor's projection. Spine ops
    come from ``spine_reorder``/``target_arc``. A reshape that declares an
    essence change without the text emits nothing — the planner never invents
    content the contract does not carry."""
    meta = contract.get("meta") or {}
    if project is not None and meta.get("project") not in (None, "", project.name):
        raise EvolveError(f"contract is for {meta.get('project')!r}, "
                          f"not {project.name!r}")
    evo = contract.get("_evolution") or ""
    essences = contract.get("_essences") or {}
    by = "evolve"
    out: list[dict] = []

    def _stamp(value: dict, anchor: Any) -> dict:
        # the banked audit convention: projection values carry the evolution
        # name + the source anchor, so every slot is traceable to the verdict
        if anchor:
            value.setdefault("evolution_source", anchor)
        if evo:
            value.setdefault("evolution", evo)
        return value

    for m in contract.get("mints") or []:
        nid = m["id"]
        edges = _mint_edges(m)
        rec = {"kind": "add-node", "node": nid, "node_kind": _mint_kind(m),
               "essence": m.get("essence_seed") or essences.get(nid) or "",
               "by": by}
        if edges:
            rec["target"] = edges[0]     # born deriving-from its first edge
        out.append(rec)
        seed = dict(m.get("projection_seed") or {})
        if not seed:                     # storyboard-led mints carry no seed
            seed = {"latex_label": nid}
            if m.get("section_target"):
                seed["section_ref"] = m["section_target"]
        if m.get("provenance") and "provenance" not in seed:
            seed["provenance"] = m["provenance"]
        out.append({"kind": "set-projection", "node": nid,
                    "value": _stamp(seed, m.get("source_anchor")), "by": by})
        for t in edges[1:]:
            out.append({"kind": "add-edge", "node": nid, "target": t, "by": by})

    for r in contract.get("reshapes") or []:
        nid = r.get("id") or r.get("node")
        if not nid:
            raise EvolveError(f"reshape without id: {r}")
        if r.get("essence"):
            out.append({"kind": "edit-essence", "node": nid,
                        "value": r["essence"], "by": by})
        if r.get("projection_merge"):
            out.append({"kind": "set-projection", "node": nid,
                        "value": _stamp(dict(r["projection_merge"]),
                                        r.get("source_anchor")), "by": by})

    for dep in contract.get("deprecations") or []:
        nid = dep.get("id") or dep.get("node")
        if nid:                          # node-shaped: retire the projection
            out.append({"kind": "set-projection", "node": nid,
                        "value": {"retired": True}, "by": by})
        if dep.get("successor_def") and dep.get("deprecated_aliases"):
            out.append({"kind": "set-projection", "node": dep["successor_def"],
                        "value": {"deprecated_aliases":
                                  list(dep["deprecated_aliases"])}, "by": by})

    for e in contract.get("edges") or []:     # schema section; banked contracts
        src = e.get("node") or e.get("source")  # enumerate edges per-mint instead
        tgt = e.get("target")
        if not (src and tgt):
            raise EvolveError(f"edge needs node+target: {e}")
        out.append({"kind": "add-edge", "node": src, "target": tgt, "by": by})

    # removals — a true DELETE through the gated door (B10). The ledger op vocabulary
    # already carries ``delete-node`` (corpus_ingest.rewire_add / friction_current:
    # state.pop, children reparent); what was missing was a CONTRACT path to emit it,
    # so a mis-mint could only be retired (deprecations keep the node) never removed.
    # This is the minimal draft+apply extension (draft-only structural): a ``removals``
    # entry deletes a live node. Collision-proofed — a removal may not name a node the
    # SAME contract mints (that is an incoherent contract, refused before any write).
    mint_ids = {m["id"] for m in contract.get("mints") or []}
    for rem in contract.get("removals") or []:
        nid = (rem.get("id") or rem.get("node")) if isinstance(rem, dict) else rem
        if not nid:
            raise EvolveError(f"removal without id: {rem}")
        if nid in mint_ids:
            raise EvolveError(f"removal {nid!r} collides with a mint of the same id")
        out.append({"kind": "delete-node", "node": nid, "by": by})

    spine = contract.get("spine_reorder") or contract.get("target_arc") or {}
    for i, entry in enumerate(spine.get("new_order") or []):
        nid = entry.get("id") or entry.get("node") if isinstance(entry, dict) else entry
        rec = {"kind": "set-spine", "node": nid, "ord": i, "by": by}
        if isinstance(entry, dict) and entry.get("narrative") is not None:
            rec["narrative"] = entry["narrative"]
        out.append(rec)
    for nid in spine.get("unset_from_spine") or []:
        out.append({"kind": "unset-spine", "node": nid, "by": by})

    return out


def _expected_delta(contract: dict) -> tuple[set[str], set[str]]:
    """The live node-id delta the contract's OWN enumeration declares:
    added = mints (+ any un-retired projection), removed = retired projections.
    This is the round-trip manifest — exact or stop."""
    added = {m["id"] for m in contract.get("mints") or []}
    removed: set[str] = set()
    for r in contract.get("reshapes") or []:
        merge = r.get("projection_merge") or {}
        if "retired" in merge:
            nid = r.get("id") or r.get("node")
            (removed if merge["retired"] else added).add(nid)
    for dep in contract.get("deprecations") or []:
        nid = dep.get("id") or dep.get("node")
        if nid:
            removed.add(nid)
    for rem in contract.get("removals") or []:
        nid = (rem.get("id") or rem.get("node")) if isinstance(rem, dict) else rem
        if nid:
            removed.add(nid)
    return added, removed


# ---------------------------------------------------------------------------
# Execution — freeze, one transaction, round-trip exact or truncate
# ---------------------------------------------------------------------------

def _l2_friction_rel(project: registry.Project) -> str:
    """The plan-ledger sidecar path, repo-relative (projection_plan.json →
    projection_plan.friction.jsonl, storyboard's convention)."""
    if not project.plan_path:
        return ""
    p = Path(project.plan_path)
    return str(p.parent / (p.name.replace(".json", "") + ".friction.jsonl"))


def _live(ledger_path: Path) -> set[str]:
    from laplace.research.corpus_ingest import friction_current
    return {r["node"] for r in friction_current(_ledger.read_jsonl(ledger_path))}


def execute(project_name: str, evolution_dir: Path | str, dry_run: bool = True,
            repo_root: Path | str | None = None,
            keep_rehearsal: bool = False) -> dict:
    """Execute an evolution contract as the skill's steps 3–4, mechanised.

    ``dry_run=True`` (the default) copies the ledgers into a private temp root
    and runs the WHOLE procedure there — freeze, transaction, round trip — so
    the report is the real rehearsal and the repo's files are never touched.
    ``dry_run=False`` writes the resolved root's ledgers, freezing L1 + the
    plan trio into ``manuscript/archive/`` first (must_exist_before_mutation).

    ``keep_rehearsal=True`` (dry-run only, additive) leaves the private temp root
    on disk and returns its path as ``rehearsal_root`` — the evolved ledgers are
    then an inspectable POST state the B10 apply-gates run against (:func:`gated_apply`).
    The CALLER owns the returned root and must remove it. Default False keeps the
    self-cleaning behaviour every existing caller relies on.

    A round-trip mismatch (or a write-gate rejection) raises inside the
    transaction — the ledgers truncate back byte-exact — and is REPORTED, not
    propagated: {ok: False, round_trip_exact: False, error: …}."""
    proj = registry.resolve(project_name)
    if proj is None or not proj.ledger:
        raise EvolveError(f"unknown or ledger-less project {project_name!r}")
    root = Path(repo_root) if repo_root is not None else registry._repo_root()
    contract = load_contract(evolution_dir)
    records = plan_records(contract, proj)

    from laplace.research import corpus_ingest as ci

    temp_root: Path | None = None
    try:
        if dry_run:
            temp_root = Path(tempfile.mkdtemp(prefix="evolve_dry_"))
            for rel in (proj.ledger, _l2_friction_rel(proj)):
                src = root / rel if rel else None
                if src is not None and src.is_file():
                    dst = temp_root / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            eff_root = temp_root
        else:
            eff_root = root

        l1 = eff_root / proj.ledger
        l2_rel = _l2_friction_rel(proj)
        l2 = eff_root / l2_rel if l2_rel else None

        # step: freeze before mutation — L1 + the plan trio, into the archive
        plan_rel = proj.plan_path
        trio = ([plan_rel, plan_rel.replace(".json", ".base.json"), l2_rel]
                if plan_rel else [])
        freeze_dir = _ledger.freeze(
            [l1] + [eff_root / rel for rel in trio if rel],
            eff_root / proj.manuscript_dir / "archive" if proj.manuscript_dir
            else eff_root / "archive",
            label=f"evolve_{contract['_evolution']}")

        before = _live(l1)
        exp_added, exp_removed = _expected_delta(contract)
        already_applied = (bool(exp_added) and exp_added <= before
                          and not (exp_removed & before))

        ledgers = [l1] + ([l2] if l2 is not None and l2.is_file() else [])
        ok, err = True, ""
        added: set[str] = set()
        removed: set[str] = set()
        try:
            with _ledger.transaction(*ledgers, by="evolve",
                                     note=contract["_evolution"]):
                for payload in records:
                    res = ci.rewire_add(eff_root, proj.name, payload)
                    if res.get("error"):
                        raise EvolveError(
                            f"write gate rejected {payload.get('kind')} "
                            f"{payload.get('node')}: {res['error']}")
                after = _live(l1)
                added, removed = after - before, before - after
                if added != exp_added or removed != exp_removed:
                    raise EvolveError(
                        "round-trip mismatch — "
                        f"added-missing={sorted(exp_added - added)} "
                        f"added-stray={sorted(added - exp_added)} "
                        f"removed-missing={sorted(exp_removed - removed)} "
                        f"removed-stray={sorted(removed - exp_removed)}")
        except EvolveError as e:
            ok, err = False, str(e)
            added, removed = set(), set()   # the transaction truncated back

        after = _live(l1)
        return {
            "ok": ok, "dry_run": dry_run,
            "project": proj.name, "evolution": contract["_evolution"],
            "shapes": contract["_shapes"],
            "records": len(records),
            "kinds": dict(Counter(r["kind"] for r in records)),
            "before_count": len(before), "after_count": len(after),
            "added": sorted(added), "removed": sorted(removed),
            "round_trip_exact": ok,
            "already_applied": already_applied,
            "freeze": str(freeze_dir),
            "ledger": str(l1),
            "plan_leg": plan_leg(contract, proj, dry_run=dry_run),
            **({"rehearsal_root": str(temp_root)}
               if (dry_run and keep_rehearsal and temp_root is not None) else {}),
            **({"error": err} if err else {}),
        }
    finally:
        if temp_root is not None and not (dry_run and keep_rehearsal):
            shutil.rmtree(temp_root, ignore_errors=True)


# ---------------------------------------------------------------------------
# The storyboard leg — an explicit seam, deliberately deferred
# ---------------------------------------------------------------------------

def plan_leg(contract: dict, project: registry.Project,
             dry_run: bool = True) -> dict:
    """The PLAN side of a storyboard-led contract.

    The plan is downstream (skill law 3): the substrate records above are the
    evolution; re-planning is a separate move. When the contract carries a
    NATIVE declarative arc (``target_arc`` in the restructure module's shape —
    a dict with ``sections``), this leg EXECUTES it through
    ``pipeline.restructure`` (lazy import; restructure never imports evolve, so
    the composition is acyclic) — the operators compose end to end. Contracts
    that carry only the banked legacy shape (``spine_reorder.new_order`` +
    ``reshapes_placement``, whose plan regeneration already landed via bespoke
    scripts) get the structured hand-off report, never a replay."""
    shapes = contract.get("_shapes") or contract_shapes(contract)
    if "storyboard" not in shapes:
        return {"direction": "substrate-led", "action": "none"}

    arc = contract.get("target_arc")
    if isinstance(arc, dict) and arc.get("sections"):
        from laplace.pipeline import restructure
        report = restructure.execute(project.name, arc, dry_run=dry_run)
        return {"direction": "storyboard-led", "action": "restructure-executed",
                "dry_run": dry_run, "restructure": report}

    spine = contract.get("spine_reorder") or {}
    placement = contract.get("reshapes_placement") or {}
    return {
        "direction": "storyboard-led",
        "action": "deferred-to-restructure",
        "handoff": {"project": project.name,
                    "target_arc": spine.get("new_order") or [],
                    "new_sections": placement.get("new_sections") or [],
                    "status": placement.get("status", "")},
        "banked_procedure": [
            "write the new projection_plan.json + .base.json (fresh generation)",
            "clear projection_plan.friction.jsonl",
            "storyboard.reconcile_section_refs(project) mirrors section_ref deltas to L1",
            "scripts/validate_projection_plan.validate must pass",
        ],
    }


# ---------------------------------------------------------------------------
# The verify surface — ready for the orchestrator to register as 'evolution'
# ---------------------------------------------------------------------------

def latest_evolution_dir(project: registry.Project,
                         repo_root: Path | str | None = None) -> Path | None:
    """The newest contract directory under the project's evolutions dir
    (mtime, name as tiebreak) — 'latest by default' for the verify branch."""
    base = project.path(project.evolutions_dir, Path(repo_root) if repo_root else None)
    if base is None or not base.is_dir():
        return None
    cands = [p for p in base.iterdir()
             if p.is_dir() and (p / "evolution_plan.json").is_file()]
    return max(cands, key=lambda p: (p.stat().st_mtime, p.name), default=None)


def verify_check(project: str, evolution_dir: Path | str | None = None) -> dict:
    """The ``evolution`` check, in verify.py's check shape ({pass, …}; pass
    None = not applicable). Dry-runs the contract against temp copies. Pass iff
    the round trip is exact OR the contract is already applied (its mints all
    live, its retirals all gone) — a banked audit trail must stay green, and
    replaying it must never look like a defect of the substrate."""
    proj = registry.resolve(project)
    if proj is None:
        return {"pass": None, "error": f"unknown project {project!r}"}
    if not proj.evolutions_dir or not proj.ledger:
        return {"pass": None, "manual": True,
                "note": f"no evolutions/ledger registered for {project!r}"}
    if evolution_dir is None:
        evolution_dir = latest_evolution_dir(proj)
        if evolution_dir is None:
            return {"pass": None, "manual": True,
                    "note": f"no evolution contracts for {project!r}"}
    try:
        rep = execute(project, evolution_dir, dry_run=True)
    except EvolveError as e:
        return {"pass": False, "project": project,
                "evolution_dir": str(evolution_dir), "error": str(e)}
    passed = bool(rep.get("round_trip_exact") or rep.get("already_applied"))
    return {"pass": passed, "project": project,
            "evolution_dir": str(evolution_dir),
            "round_trip_exact": rep.get("round_trip_exact"),
            "already_applied": rep.get("already_applied"),
            "records": rep.get("records"), "kinds": rep.get("kinds"),
            **({"error": rep["error"]} if rep.get("error")
               and not rep.get("already_applied") else {})}


# ---------------------------------------------------------------------------
# BITE B10 — the seven gates hard-block an evolution apply
# ---------------------------------------------------------------------------
#
# Author ruling (binding): ALL SEVEN build-completion gates
# (canon://operations/gate_registry) must pass against the POST-evolution state
# for an apply to land. There is NO override flag — the CLI grows no --force;
# loosening is a dials change made later with evidence from real refusals. The
# verdict travels as a file: ``<evolution_dir>/gates.json`` is written on every
# gated_apply, pass or fail, so the refusal (or the green light) is inspectable.

#: The seven gates in registry order, each (gate-name -> verify checker name).
#: Every checker takes ``(corpus_name, root=<evolved friction-ledger root>)``.
#: topology + coherence are computed on the friction-ledger network (the object
#: an evolution mutates); the CanonGraph instruments that nominally own them run
#: on the markdown projection and cannot see a rewire — see verify.check_topology.
GATE_CHECKS = (
    ("topology", "check_topology"),
    ("coherence", "check_coherence"),
    ("connectivity", "check_connectivity"),
    ("projection_labels", "check_projection_labels"),
    ("glossary", "check_glossary"),
    ("substrate", "check_substrate"),
    ("figures", "check_figures"),
)


def pre_apply_gates(project: str, evolved_root: Path | str) -> dict:
    """Run all seven build-completion gates against a POST-evolution state.

    ``evolved_root`` is a repo root whose L1 friction ledger already carries the
    evolution's rewire records (the rehearsal root :func:`execute` leaves when
    ``keep_rehearsal=True``). Each gate reads its overlay from that root, so the
    verdict is on the conceptric the apply WOULD produce, not the live one.

    Returns ``{gate_name: {ok, detail}}`` for every gate. ``ok`` is True only for
    a HARD pass — a gate that returns ``pass: None`` (manual / not-applicable) is
    not a green light under the B10 law: a gate that cannot run cannot clear the
    apply, so its ``ok`` is False and its note rides in ``detail``. A gate that
    raises is likewise a refusal, never a silent skip."""
    from laplace.pipeline import verify as _verify

    report: dict[str, dict] = {}
    for name, fn_name in GATE_CHECKS:
        fn = getattr(_verify, fn_name)
        try:
            res = fn(project, root=evolved_root)
        except Exception as e:            # a gate that raises cannot clear the apply
            report[name] = {"ok": False,
                            "detail": {"error": f"{fn_name} raised: {e}"}}
            continue
        detail = {k: v for k, v in res.items() if k != "pass"}
        report[name] = {"ok": res.get("pass") is True, "detail": detail}

    # DELTA semantics for inherited debt (first real refusal, 2026-07-10): the
    # topology gate stays HARD but judges the evolution's DELTA — an apply may
    # never ADD dangling links or components, yet is not hostage to debt the
    # corpus already carries (8 pre-existing components blocked a single mint
    # wired to an existing node). Inherited debt is its own future evolution.
    topo = report.get("topology")
    if topo is not None and not topo["ok"]:
        try:
            base = getattr(_verify, dict(GATE_CHECKS)["topology"])(project, root=None)
        except Exception:
            base = None                      # no baseline -> the absolute verdict stands
        if base is not None:
            post_d = topo["detail"].get("dangling") or []
            pre_d = base.get("dangling") or []
            post_c = topo["detail"].get("components")
            pre_c = base.get("components")
            no_worse = (set(map(str, post_d)) <= set(map(str, pre_d))
                        and post_c is not None and pre_c is not None
                        and post_c <= pre_c)
            topo["detail"]["baseline"] = {"dangling": len(pre_d), "components": pre_c}
            if no_worse:
                topo["ok"] = True
                topo["detail"]["note"] = ("passes on DELTA: inherited debt "
                                          "unchanged, nothing worsened")
    return report


def _write_gates(evolution_dir: Path, verdict: dict) -> None:
    """Write the B10 verdict to ``<evolution_dir>/gates.json`` — the file the
    refusal (or the green light) travels as. This is the one intentional write to
    the evolution dir (:func:`load_contract` keeps it read-only); best-effort, so
    a write failure never masks the gate verdict itself."""
    try:
        (Path(evolution_dir) / "gates.json").write_text(
            json.dumps(verdict, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass


def gated_apply(project: str, evolution_dir: Path | str,
                repo_root: Path | str | None = None) -> dict:
    """Apply an evolution contract ONLY if all seven gates pass the POST state.

    The B10 round-trip: rehearse the contract into a private temp root
    (:func:`execute` ``dry_run=True, keep_rehearsal=True``) so the evolved
    ledgers exist as an inspectable POST state; run :func:`pre_apply_gates`
    against that root; iff ALL seven gates are ok, land the evolution for real
    (:func:`execute` ``dry_run=False``). ANY gate failure raises
    :class:`EvolveError` naming the failing gate(s), the repo untouched.

    The verdict travels as a file: ``<evolution_dir>/gates.json`` is written
    either way (the B10 law), carrying the full seven-gate report, the rehearsal
    round-trip, and the apply outcome. Returns the verdict on a clean apply."""
    evolution_dir = Path(evolution_dir)

    rehearsal = execute(project, evolution_dir, dry_run=True,
                        repo_root=repo_root, keep_rehearsal=True)
    rehearsal_root = rehearsal.get("rehearsal_root")
    try:
        gates = pre_apply_gates(project, rehearsal_root) if rehearsal_root else {}
        # a rehearsal that itself failed (broken round trip / write-gate reject /
        # a replay of an already-applied contract) never applies cleanly — refuse
        # before honouring the gate verdict, but still bank the report.
        if not rehearsal.get("ok"):
            verdict = {
                "project": project, "evolution": evolution_dir.name,
                "applied": False, "rehearsal_ok": False,
                "already_applied": rehearsal.get("already_applied"),
                "rehearsal_error": rehearsal.get("error", ""),
                "round_trip_exact": rehearsal.get("round_trip_exact"),
                "gates": gates,
                "failed_gates": [n for n, g in gates.items() if not g["ok"]],
            }
            _write_gates(evolution_dir, verdict)
            raise EvolveError(
                "evolution refused: rehearsal did not apply cleanly "
                f"({rehearsal.get('error') or 'already applied'}); repo untouched, "
                f"verdict in {evolution_dir / 'gates.json'}")
        failed = [n for n, g in gates.items() if not g["ok"]]
    finally:
        if rehearsal_root:
            shutil.rmtree(rehearsal_root, ignore_errors=True)

    if failed:
        verdict = {
            "project": project, "evolution": evolution_dir.name,
            "applied": False, "rehearsal_ok": True,
            "round_trip_exact": rehearsal.get("round_trip_exact"),
            "gates": gates, "failed_gates": failed,
        }
        _write_gates(evolution_dir, verdict)
        raise EvolveError(
            f"evolution refused: {len(failed)} of {len(GATE_CHECKS)} gates failed "
            f"({', '.join(failed)}); repo untouched, verdict in "
            f"{evolution_dir / 'gates.json'}")

    # all seven green — land it for real
    applied = execute(project, evolution_dir, dry_run=False, repo_root=repo_root)
    verdict = {
        "project": project, "evolution": evolution_dir.name,
        "applied": bool(applied.get("ok")), "rehearsal_ok": True,
        "round_trip_exact": applied.get("round_trip_exact"),
        "gates": gates, "failed_gates": [],
        "added": applied.get("added"), "removed": applied.get("removed"),
    }
    _write_gates(evolution_dir, verdict)
    if not applied.get("ok"):
        # gates were green on the rehearsal but the real apply broke its round trip
        # (the ledgers truncated back) — surface it, never claim a false success.
        raise EvolveError(
            "gates passed but the apply round trip failed "
            f"({applied.get('error', '')}); ledgers truncated back, verdict in "
            f"{evolution_dir / 'gates.json'}")
    return verdict
