"""selection_sheet.py — the selection sheet's reader and the draft rule it proposes.

The fitness panel (``fitness_panel.py``) reads the numbers; this sheet joins them per
generation and proposes a verdict against a draft rule (ψ/φ). The rule and the
threshold belong to the author — ``profiles/selection/draft-psi-v1.yaml`` proposes a
reading, and the threshold is calibrated from ruling history (ratify/override deltas),
not hand-set. A recalibration is a new rule file (``draft-psi-v2``), not an edit of
this one.

Pure read (the fitness_panel idiom): every number is a banked artifact re-read through
the generation row's own dated ref; an absent ref degrades to empty, never a raise. An
absent reading never promotes — a missing gate input makes the gate ``null`` and the
generation holds with the absence named (silence never passes).

Per generation row (``<manuscript>/generations.jsonl``):

* the debt delta — ``reprojection.run_record`` ref (``source_delta_before.n`` /
  ``source_delta_after.n``); when the row carries no ``before``, it falls back to the
  previous generation's ``after`` (the trajectory is the series), and the reason says
  so;
* the freeze substance — ``reprojection.freeze_verdict`` ref;
* the mechround derivative — ``converge.detect_pre`` / ``converge.detect_post`` refs;
* the R10 whole-artefact verdict — ``r10.report_id`` against the feedback ledger;
* the retention aggregate over the entered intent ids, author-supersedes-machine;
* the suite floor — the global ``corpus_friction/suite_baseline.json`` (v1: presence
  of the banked floor is the ``no_new_suite_reds`` reading).

The three gates (self-consistency, cost, representation-stability) and the net-gain
stopping rule are the author's theory (cost-of-complexity §VII "structure is earned,
not gifted"; law-of-laws "retention forced by closure, not a modelling choice"; "Your
Brain on Algebra" §4 "the threshold is part of the self-consistent loss geometry").
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# The draft rule — the code owns the defaults; the versioned YAML overlays them
# (the dials idiom). _DRAFT_PSI_DEFAULTS must equal draft-psi-v1.yaml's body, so a
# fresh checkout reads the designed rule and the overlay round-trips.
# ---------------------------------------------------------------------------

_DRAFT_PSI_DEFAULTS: dict[str, Any] = {
    "version": "draft-psi-v1",
    "law": ("This file proposes verdicts; the author's ruling supersedes and is "
            "recorded. Thresholds are calibrated from ruling history, not hand-set."),
    "gate_self_consistency": {"r10_must_have_run": True, "r10_must_be_clean": True},
    "gate_cost": {"debt_must_not_rise": True, "no_new_suite_reds": True},
    "gate_representation_stability": {"freeze_substance_must_hold": True,
                                      "mechround_derivative_at_most": 0},
    # gate_reach — the reach gate's schema slot. It lives in the defaults so a
    # versioned rule file (draft-psi-v2) can activate it without tripping the
    # unknown-key guard in _overlay; both flags default false so the code fallback
    # (and draft-psi-v1, which never names gate_reach) keeps its exact v1 semantics
    # — a fresh v1 read round-trips to these defaults with the gate inert. draft-
    # psi-v2 flips them true. See _draft_verdict: the reach gate is computed only
    # when a flag is on, so v1's verdict is byte-identical. (PV-20260721T121500Z:
    # "what would have the furthest reach ...? And then the game is to try to build
    # the chain from the substrate towards that ... like haddiths and isnads, except
    # it all has to actually be true." — the endpoint banked first, each link
    # attested, reach measured generation-over-generation.)
    "gate_reach": {"aspiration_must_exist": False, "reach_must_not_fall": False},
    "promotion_ledger": {"residual_gain_source": "debt_delta", "lambda": 1.0},
    "retire_when": {"debt_rose_and_r10_unclean": True},
    "otherwise": "hold",
}


def _read_json(p: Path) -> dict | None:
    try:
        import json
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _overlay(base: dict[str, Any], over: dict[str, Any], path: str = "") -> None:
    """Deep-merge ``over`` onto ``base`` in place, raising on an unknown key (the
    ``dials._overlay`` pattern): a key absent from the defaults schema at that level is
    a typo, not a new clause — a silent no-op would hide a mis-calibrated rule."""
    for k, v in over.items():
        dotted = f"{path}{k}"
        if k not in base:
            raise ValueError(
                f"unknown draft-rule key {dotted!r} — not in the "
                "selection_sheet._DRAFT_PSI_DEFAULTS schema; a typo must not silently "
                "no-op (recalibration is a NEW rule file, never an unknown key)")
        if isinstance(base[k], dict):
            if not isinstance(v, dict):
                raise ValueError(
                    f"draft-rule key {dotted!r} expects a mapping, got {type(v).__name__}")
            _overlay(base[k], v, dotted + ".")
        else:
            base[k] = v


def _load_rule(root: Path, dial_value: str) -> dict[str, Any]:
    """The draft rule: code defaults overlaid by ``profiles/selection/<dial>.yaml``.
    Returns ``{"version","law","path","rule"}``. Absent file → the code defaults (empty
    ``path``). An unknown key in the YAML raises."""
    rule = copy.deepcopy(_DRAFT_PSI_DEFAULTS)
    prof = root / "profiles" / "selection" / f"{dial_value}.yaml"
    path: str | None = None
    if prof.is_file():
        import yaml
        overlay = yaml.safe_load(prof.read_text(encoding="utf-8")) or {}
        if not isinstance(overlay, dict):
            raise ValueError(f"draft rule {prof} must be a mapping, got "
                             f"{type(overlay).__name__}")
        _overlay(rule, overlay)
        path = str(prof)
    return {"version": rule["version"], "law": rule["law"], "path": path, "rule": rule}


# ---------------------------------------------------------------------------
# ref resolution + the per-reading readers (all honest-empty)
# ---------------------------------------------------------------------------

def _resolve_ref(md: Path, ref: Any) -> dict | None:
    """Read the JSON a generation-row ref points at, honest-empty. A ref may be a
    path string relative to the manuscript dir, a ``{"path": ...}`` dict, an already-
    inlined payload dict, or ``None``. Anything else → ``None``."""
    if ref is None:
        return None
    if isinstance(ref, str):
        return _read_json(md / ref)
    if isinstance(ref, dict):
        rel = ref.get("path") or ref.get("ref")
        if isinstance(rel, str):
            return _read_json(md / rel)
        return ref  # an inlined payload
    return None


def _delta_n(rec: dict | None, key: str) -> int | None:
    """``source_delta_<key>.n`` off a run_record payload, or ``None``."""
    if not rec:
        return None
    sd = rec.get(f"source_delta_{key}") or {}
    n = sd.get("n") if isinstance(sd, dict) else None
    return n if isinstance(n, int) else None


def _open_n(rec: dict | None) -> int | None:
    """The open-finding count off a detect payload (the fitness_panel idiom)."""
    if not rec:
        return None
    for k in ("open", "flags_routed", "open_findings_n"):
        v = rec.get(k)
        if isinstance(v, int):
            return v
    return None


def _freeze_of(rec: dict | None) -> dict | None:
    if not rec:
        return None
    return {"pass": rec.get("pass"),
            "substance_pass": rec.get("substance_pass"),
            "mechanical_pass": rec.get("mechanical_pass"),
            "classes": rec.get("classes")}


def _r10_of(feedback_rows: list[dict], report_id: Any,
            stamped_at: Any = None) -> dict:
    """R10's whole-artefact verdict via ``report_id`` against the feedback ledger:
    the ``reader-report`` record (``reader=='R10'``, ``id==report_id``). Absent →
    ``{"ran": False}`` (silence never certifies clean)."""
    if not report_id:
        return {"ran": False}
    # The generation window resolves the id collision: make_reader_report derives a
    # deterministic id from the artifact, so two generations' reports of the same
    # paper collide on id (the gen-2 worker's catch, 2026-07-21 — first-match gave
    # gen-2 the stale 07-19 clean report; plain newest-match gives gen-1 tomorrow's
    # report). The right report for a generation is the newest matching record banked
    # at or before its stamp (reports bank during the converge, the stamp closes the
    # generation); rows without a usable ts stay candidates.
    cands = [r for r in feedback_rows
             if (r.get("record") == "reader-report" and r.get("reader") == "R10"
                 and r.get("id") == report_id)]
    if stamped_at:
        windowed = [r for r in cands
                    if not str(r.get("ts") or "") or str(r.get("ts")) <= str(stamped_at)]
        cands = windowed or cands
    for r in reversed(cands):
        if True:
            findings = [f for f in (r.get("findings") or []) if isinstance(f, dict)]
            kinds = sorted({str(f.get("mismatch_type") or f.get("kind") or "")
                            for f in findings} - {""})
            return {"ran": True, "clean": bool(r.get("clean")),
                    "findings_n": len(findings), "mismatch_kinds": kinds}
    return {"ran": False}


def _retention_aggregate(events: list[dict], corpus: str,
                         intent_ids: list[str]) -> dict[str, Any]:
    """The retention aggregate over a generation's entered intent ids, with the author
    superseding the machine. Group retention events by artifact key
    (``corpus:intent_id``); on any key an ``author`` event supersedes the machine
    (``door``/``gate``) events, which are counted as ``machine_superseded``. A ``None``
    source is treated as machine."""
    keys = {f"{corpus}:{iid}" for iid in (intent_ids or []) if iid}
    if not keys:
        return {"keys": 0, "by_fate": {}, "author_ruled": 0, "machine_superseded": 0}
    by_key: dict[str, list[dict]] = {}
    for e in events:
        if e.get("phase") != "retention":
            continue
        art = e.get("artifact")
        if art in keys:
            by_key.setdefault(art, []).append(e)
    by_fate: dict[str, int] = {}
    author_ruled = 0
    machine_superseded = 0
    for art, evs in by_key.items():
        authors = [e for e in evs if e.get("source") == "author"]
        if authors:
            winner = authors[-1]                       # newest author event rules
            author_ruled += 1
            machine_superseded += sum(1 for e in evs if e.get("source") != "author")
        else:
            winner = evs[-1]                           # newest machine event stands
        fate = str(winner.get("fate") or "")
        if fate:
            by_fate[fate] = by_fate.get(fate, 0) + 1
    return {"keys": len(by_key), "by_fate": by_fate,
            "author_ruled": author_ruled, "machine_superseded": machine_superseded}


# ---------------------------------------------------------------------------
# The reach reading (draft-psi-v2 · the isnad frame) — the derivation organ's reach()
# measured generation-over-generation. PV-20260721T121500Z: "one must ask themselves
# what the best possible version of a result is. what would have the furthest reach,
# broadest scope and deepest impact? And then the game is to try to build the chain
# from the substrate towards that ... like haddiths and isnads, except it all has to
# actually be true." The endpoint is banked first; each chain link is attested; the
# gate measures how far up the attested chain got, this generation against the banked
# baseline — hedging-as-inaction becomes a visible stall (silence never promotes).
# ---------------------------------------------------------------------------

def _reach_of(rec: Any) -> dict | None:
    """A reach snapshot as a plain dict, or ``None``. A snapshot is the derivation
    organ's ``reach()`` shape: ``links_total`` / ``links_attested`` /
    ``depth_attested`` / ``frontier_gap``. Anything without the attested measures is
    treated as absent (silence, not a zero-reach claim)."""
    if not isinstance(rec, dict):
        return None
    if "depth_attested" not in rec and "links_attested" not in rec:
        return None
    return rec


def _reach_lex(r: dict | None) -> tuple[int, int]:
    """The comparable reach measure: ``(depth_attested, links_attested)`` — depth (how
    far up the aspiration the attested chain reached) dominates, attested-link count
    tiebreaks. Missing measures read as 0 (no reach), never as a raise."""
    r = r or {}
    depth = r.get("depth_attested")
    links = r.get("links_attested")
    return (int(depth) if isinstance(depth, int) else 0,
            int(links) if isinstance(links, int) else 0)


def _reach_brief(r: dict | None) -> str:
    """A short human phrase for a reach snapshot (or ``absent``)."""
    if not isinstance(r, dict):
        return "absent"
    depth = r.get("depth_attested")
    att = r.get("links_attested")
    tot = r.get("links_total")
    gap = r.get("frontier_gap")
    return (f"depth {depth}, {att}/{tot} links attested"
            + (f", frontier gap {gap}" if gap is not None else ""))


def _live_reach(md: Path) -> dict | None:
    """The manuscript's current reach via the derivation organ (the frozen interface,
    imported inside the function so an absent sibling organ degrades to empty, not an
    ImportError). Trusted only when the aspiration record is banked at
    ``<md>/aspiration/aspiration.json`` — so a reach() that returns zeros over an empty
    substrate cannot masquerade as a banked maximal claim."""
    asp = _read_json(md / "aspiration" / "aspiration.json")
    if not (isinstance(asp, dict) and asp.get("record") == "aspiration"):
        return None
    try:
        from laplace.pipeline import derivation_organ  # frozen sibling interface
        r = derivation_organ.reach(md)
    except Exception:  # noqa: BLE001 — organ absent/broken → honest-empty
        return None
    return _reach_of(r)


# ---------------------------------------------------------------------------
# The draft verdict — three gates, the net-gain stopping rule, absence holds
# ---------------------------------------------------------------------------

def _draft_verdict(reading: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    """Propose promote|hold|retire for one generation reading against the draft rule.

    Three gates, each ``{"pass": bool|None, "reasons": [...]}``; a missing input makes
    the gate ``None`` and the generation holds with the absence named (an absent
    reading never promotes). Promote only when all three gates pass and the net gain is
    positive (``debt_delta > 0`` — the residual gain pays the marginal cost, §VII).
    Retire only when debt rose and R10 is unclean (both)."""
    debt_before = reading.get("debt_before")
    debt_after = reading.get("debt_after")
    debt_source = reading.get("debt_before_source")   # "run_record" | "prev-generation" | None
    freeze = reading.get("freeze")
    mech = reading.get("mechround") or {}
    derivative = mech.get("derivative")
    r10 = reading.get("r10") or {"ran": False}
    suite_present = reading.get("suite_floor_present")

    delta = (debt_before - debt_after
             if isinstance(debt_before, int) and isinstance(debt_after, int) else None)

    gates: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []

    # --- gate_self_consistency: r10 ran AND r10 clean ---
    g1_reasons: list[str] = []
    if not r10.get("ran"):
        g1_pass: bool | None = None
        g1_reasons.append("r10 absent (gate_self_consistency · self-consistency unproven)")
    else:
        g1_pass = bool(r10.get("clean"))
        g1_reasons.append(
            f"r10 {'clean' if g1_pass else 'unclean'} "
            f"({r10.get('findings_n', 0)} finding(s)) "
            "(gate_self_consistency · closure demands consistency)")
    gates["gate_self_consistency"] = {"pass": g1_pass, "reasons": g1_reasons}

    # --- gate_cost: debt must not rise AND no new suite reds ---
    g2_reasons: list[str] = []
    if delta is None:
        sub_debt: bool | None = None
        g2_reasons.append("debt delta absent (gate_cost · marginal cost unmeasured)")
    else:
        sub_debt = delta >= 0
        src = (f" (before={debt_before}, prev generation's after)"
               if debt_source == "prev-generation"
               else f" (before={debt_before}, the census point)"
               if debt_source == "census" else "")
        g2_reasons.append(
            f"debt {debt_before}→{debt_after}{src} "
            f"({'held/fell' if sub_debt else 'ROSE'}) "
            "(gate_cost · structure earned)")
    if suite_present is None:
        sub_suite: bool | None = None
        g2_reasons.append("suite floor absent (gate_cost · global floor unknown)")
    else:
        sub_suite = bool(suite_present)
        g2_reasons.append(
            f"suite floor {'banked' if sub_suite else 'missing'} "
            "(gate_cost · no new reds beyond the global floor)")
    g2_pass = (None if (sub_debt is None or sub_suite is None)
               else (sub_debt and sub_suite))
    gates["gate_cost"] = {"pass": g2_pass, "reasons": g2_reasons}

    # --- gate_representation_stability: freeze substance holds AND derivative <= 0 ---
    g3_reasons: list[str] = []
    if not freeze:
        sub_freeze: bool | None = None
        g3_reasons.append("freeze verdict absent "
                          "(gate_representation_stability · representation unproven)")
    else:
        sub_freeze = bool(freeze.get("substance_pass"))
        g3_reasons.append(
            f"freeze substance {'held' if sub_freeze else 'BROKEN'} "
            "(gate_representation_stability · substance must hold)")
    at_most = ((rule.get("rule") or {}).get("gate_representation_stability") or {}) \
        .get("mechround_derivative_at_most", 0)
    if derivative is None:
        sub_deriv: bool | None = None
        g3_reasons.append("mechround derivative absent "
                          "(gate_representation_stability · stability unmeasured)")
    else:
        sub_deriv = derivative <= at_most
        g3_reasons.append(
            f"mechround derivative {derivative:+d} (≤ {at_most}? "
            f"{'yes' if sub_deriv else 'no'}) "
            "(gate_representation_stability · no widening)")
    g3_pass = (None if (sub_freeze is None or sub_deriv is None)
               else (sub_freeze and sub_deriv))
    gates["gate_representation_stability"] = {"pass": g3_pass, "reasons": g3_reasons}

    # --- gate_reach (draft-psi-v2, off in v1): the aspiration exists and its attested
    # reach did not fall generation-over-generation. Computed only when a gate_reach
    # flag is on — so under draft-psi-v1 (both flags default false) no fourth gate is
    # added and the verdict is byte-identical. A generation with no aspiration banked →
    # gate null → hold, the stall named (silence never promotes; PV: "Hedging and
    # verification are too often being used as an excuse to do nothing ... Sets the end
    # point before we know if that end point is achievable").
    gr_cfg = (rule.get("rule") or {}).get("gate_reach") or {}
    must_exist = bool(gr_cfg.get("aspiration_must_exist"))
    must_not_fall = bool(gr_cfg.get("reach_must_not_fall"))
    if must_exist or must_not_fall:
        g4_reasons: list[str] = []
        this_reach = reading.get("reach")
        prev_reach = reading.get("prev_reach")
        if must_exist and this_reach is None:
            g4_pass: bool | None = None
            g4_reasons.append(
                "aspiration absent — no maximal claim banked this generation "
                "(gate_reach · silence never promotes; the stall is visible)")
        else:
            if this_reach is not None:
                g4_reasons.append(
                    f"aspiration present: {_reach_brief(this_reach)} "
                    "(gate_reach · ambition at the endpoint)")
            if must_not_fall:
                if prev_reach is None:
                    g4_pass = True
                    g4_reasons.append(
                        "no prior banked reach to fall from "
                        "(gate_reach · reach measured generation-over-generation)")
                else:
                    fell = _reach_lex(this_reach) < _reach_lex(prev_reach)
                    g4_pass = not fell
                    g4_reasons.append(
                        f"reach {_reach_brief(prev_reach)} → {_reach_brief(this_reach)} "
                        f"({'FELL' if fell else 'held/grew'}) "
                        "(gate_reach · honesty per-link, no retreat to a weaker claim)")
            else:
                g4_pass = True
        gates["gate_reach"] = {"pass": g4_pass, "reasons": g4_reasons}

    for g in gates.values():
        reasons.extend(g["reasons"])

    all_pass = all(g["pass"] is True for g in gates.values())
    net_gain = isinstance(delta, int) and delta > 0
    debt_rose = isinstance(delta, int) and delta < 0
    r10_unclean = bool(r10.get("ran")) and not r10.get("clean")

    if all_pass and net_gain:
        verdict = "promote"
        reasons.append(f"net gain {delta} > 0 pays the marginal cost "
                       "(promotion_ledger · §VII structure earned)")
    elif (rule.get("rule") or {}).get("retire_when", {}).get(
            "debt_rose_and_r10_unclean") and debt_rose and r10_unclean:
        verdict = "retire"
        reasons.append(f"debt rose {debt_before}→{debt_after} AND r10 unclean "
                       "(retire_when · the change did not pay)")
    else:
        verdict = "hold"

    return {"verdict": verdict, "draft": True, "rule": rule["version"],
            "law": rule["law"], "gates": gates, "reasons": reasons}


# ---------------------------------------------------------------------------
# The public read
# ---------------------------------------------------------------------------

def read_selection(project: str, root: str | Path | None = None) -> dict[str, Any]:
    """The selection sheet for a project: every generation joined to its own banked
    readings and a DRAFT verdict. Pure read, honest-empty — an unregistered project,
    an absent manuscript dir, or an absent generations ledger all return a present-
    false sheet, never a raise."""
    root = Path(root) if root is not None else Path(".")
    from laplace.pipeline import registry
    proj = registry.resolve(project)
    md = (proj.path(proj.manuscript_dir, root)
          if (proj and proj.manuscript_dir) else None)
    if md is None:
        return {"present": False, "corpus": project}

    corpus = proj.name

    # the draft rule (dials-selected file, code-default fallback)
    from laplace.pipeline import dials
    try:
        dials_d = dials.load_dials()
    except Exception:  # noqa: BLE001 — a broken dials profile never breaks the read
        dials_d = dials.defaults()
    dial_val = ((dials_d.get("selection") or {}).get("draft_psi")) or "draft-psi-v1"
    rule = _load_rule(root, dial_val)

    from laplace.pipeline import ledger
    rows_raw = ledger.read_jsonl(md / "generations.jsonl")
    feedback = ledger.read_jsonl(md / "feedback" / "feedback.jsonl")
    try:
        from laplace.engine import telemetry
        events = telemetry.events()
    except Exception:  # noqa: BLE001 — an unreadable telemetry substrate → empty
        events = []

    def _census_before(corp: str, run_rec: dict | None) -> int | None:
        """The latest fitness-trajectory point STRICTLY before this generation's
        run_record date — the census half of the one series (pure read of the
        fitness panel; a point at-or-after the run measures the run itself,
        never its 'before')."""
        try:
            from laplace.pipeline import fitness_panel as fp
            at = str((run_rec or {}).get("at") or "")[:10]
            if not at:
                return None
            pts = [t for t in (fp.read_fitness(corp).get("debt_trajectory") or [])
                   if isinstance(t.get("n"), int) and str(t.get("at") or "")[:10] < at]
            return pts[-1]["n"] if pts else None
        except Exception:
            return None

    suite = _read_json(root / "corpus_friction" / "suite_baseline.json")
    suite_floor = ({"named_red": (suite.get("counts") or {}).get("failed"),
                    "captured_at": suite.get("captured_at")} if suite else None)
    suite_present = suite is not None

    gens_raw = [r for r in rows_raw if r.get("record") == "generation"]
    # join in n-ascending order so each row's debt_after carries forward as the next
    # row's debt_before fallback (the trajectory is the series — orchestrator ruling).
    gens_raw.sort(key=lambda r: (r.get("n") if isinstance(r.get("n"), int) else 0,
                                 str(r.get("stamped_at") or "")))

    # The reach gate (draft-psi-v2): measured only when the active rule turns a
    # gate_reach flag on — under draft-psi-v1 no reach reading is joined, so the
    # per-generation payload and verdict stay byte-identical. The manuscript's current
    # reach (the frozen organ over the live aspiration files) is the newest generation's
    # reading; prior generations read their own banked reach snapshot (row["reach"]).
    _gr = (rule.get("rule") or {}).get("gate_reach") or {}
    reach_active = bool(_gr.get("aspiration_must_exist") or _gr.get("reach_must_not_fall"))
    live_reach = _live_reach(md) if reach_active else None

    joined: list[dict[str, Any]] = []
    prev_after: int | None = None
    reach_baseline: dict | None = None            # last non-null banked reach (the trajectory)
    n_gens = len(gens_raw)
    for gen_idx, row in enumerate(gens_raw):
        rr = _resolve_ref(md, (row.get("reprojection") or {}).get("run_record"))
        fv = _resolve_ref(md, (row.get("reprojection") or {}).get("freeze_verdict"))
        cvg = row.get("converge") or {}
        pre = _open_n(_resolve_ref(md, cvg.get("detect_pre")))
        post = _open_n(_resolve_ref(md, cvg.get("detect_post")))
        r10 = _r10_of(feedback, (row.get("r10") or {}).get("report_id"),
                      row.get("stamped_at"))
        entered = (row.get("entered") or {}).get("intent_ids") or []
        retention = _retention_aggregate(events, corpus, entered)

        debt_after = _delta_n(rr, "after")
        debt_before = _delta_n(rr, "before")
        debt_source = "run_record" if debt_before is not None else None
        if debt_before is None and prev_after is not None:
            debt_before = prev_after                    # trajectory fallback
            debt_source = "prev-generation"
        if debt_before is None:
            # third source, first-generation case: the CENSUS trajectory point
            # strictly before this generation's run_record date (the fitness
            # panel's own series — gen-1's "before" was measured by the 07-17
            # census, never re-banked into the 07-19 run_record). Still exact:
            # no point strictly earlier → stays None → gate_cost holds.
            debt_before = _census_before(corpus, rr)
            if debt_before is not None:
                debt_source = "census"

        mech: dict[str, Any] = {}
        if pre is not None:
            mech["pre"] = pre
        if post is not None:
            mech["post"] = post
        if isinstance(pre, int) and isinstance(post, int):
            mech["derivative"] = post - pre

        delta = (debt_before - debt_after
                 if isinstance(debt_before, int) and isinstance(debt_after, int)
                 else None)

        reading = {
            "n": row.get("n"), "id": row.get("id"),
            "stamped_at": row.get("stamped_at"),
            "dials_profile": row.get("dials_profile"),
            "debt_before": debt_before, "debt_after": debt_after,
            "debt_delta": delta, "debt_before_source": debt_source,
            "freeze": _freeze_of(fv),
            "mechround": mech,
            "r10": r10,
            "retention": retention,
            "suite_floor_present": suite_present if suite_present else None,
        }

        if reach_active:
            banked = _reach_of(_resolve_ref(md, row.get("reach")))
            is_newest = (gen_idx == n_gens - 1)
            this_reach = banked if banked is not None else (live_reach if is_newest else None)
            reading["reach"] = this_reach
            reading["prev_reach"] = reach_baseline

        reading["draft_verdict"] = _draft_verdict(reading, rule)
        joined.append(reading)

        if debt_after is not None:
            prev_after = debt_after
        if reach_active and reading.get("reach") is not None:
            reach_baseline = reading["reach"]   # baseline carries the last banked reach

    # rulings (P3): selection-ruling records keyed by target generation id
    rulings: dict[str, Any] = {}
    for r in feedback:
        if r.get("record") == "selection-ruling" and r.get("target"):
            rulings[str(r["target"])] = {"verdict": r.get("verdict"),
                                         "overrode_draft": r.get("overrode_draft")}

    counts = {"generations": len(joined), "promote": 0, "hold": 0, "retire": 0}
    for g in joined:
        v = g["draft_verdict"]["verdict"]
        counts[v] = counts.get(v, 0) + 1
    awaiting = sum(1 for g in joined if str(g.get("id")) not in rulings)

    joined.sort(key=lambda g: (g.get("n") if isinstance(g.get("n"), int) else 0,
                               str(g.get("stamped_at") or "")), reverse=True)

    return {
        "present": bool(joined),
        "corpus": corpus,
        "rule": {"version": rule["version"], "law": rule["law"], "path": rule["path"]},
        "generations": joined,
        "counts": counts,
        "awaiting_ruling_n": awaiting,
        "rulings": rulings,
        "suite_floor": suite_floor,
    }
