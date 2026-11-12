"""THE CONJUGATE WAVE — the sub-organ band on /pipeline (SCOUT_2026-07-17).

These clauses bind the substrate (Lane 0) + the per-organ cards (Lanes 1-5):

  * the night-organs attach as sub_organs UNDER the right state-organ, each carrying
    a reader_door + a fire_action (or None for a read-only organ), NEVER as a new
    release STATE (RISK 3);
  * chain() carries LIGHT summaries only — the payload stays bounded, no per-detector
    / per-intent / per-fork body inlined (RISK 4);
  * GET /pipeline/organ is a PURE read (no subprocess/compile/network on the GET
    path, WIRING LAW 2), honest-404s an unknown organ/project, and stays 405 on POST;
  * the dials-vs-gate seam (Lane 3 / RISK 2): a store dial reads its holdout gate
    through stage_retrieval's OWN logic; a red/absent gate renders warn, NEVER green,
    and arming is refused with the reason inline;
  * every card derives from the organ's OWN reader (view=mechanism, RISK 1).

Pure stdlib + the on-disk falqon artifacts (which exist for every organ, 2026-07-17).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from laplace.web import pipeline_surface as ps
from laplace.pipeline import registry
from laplace.pipeline import release


# the reference project — falqon carries a banked run for EVERY night-organ.
_FALQON = "paper_falqon"


def _has_falqon() -> bool:
    return registry.resolve(_FALQON) is not None


falqon_only = pytest.mark.skipif(not _has_falqon(),
                                 reason="paper_falqon not resolvable on disk")


def _git_status() -> str:
    root = ps._repo_root()
    return subprocess.run(["git", "status", "--porcelain"], cwd=str(root),
                          capture_output=True, text=True).stdout


# --------------------------------------------------------------------------- #
# RISK 3 — the sub-organs are NOT release STATES (the new-state-corruption catch)
# --------------------------------------------------------------------------- #

def test_suborgan_table_never_touches_release_states():
    """``_SUBORGAN_FOR_STATE`` keys are a subset of ``release.STATES`` (they attach
    UNDER a state, never define one); no sub-organ id collides with a STATE; and the
    known-organs set derives from the table, so a new organ is reachable the moment it
    joins — never a hand-maintained parallel list."""
    states = set(release.STATES)
    assert set(ps._SUBORGAN_FOR_STATE) <= states, \
        "a _SUBORGAN_FOR_STATE key is not a release STATE"
    sub_ids = {sub["id"] for subs in ps._SUBORGAN_FOR_STATE.values() for sub in subs}
    assert not (sub_ids & states), "a sub-organ id collides with a release STATE"
    assert ps._KNOWN_SUBORGANS == frozenset(sub_ids), \
        "the served-organ set drifted from the table"


def test_ladder_still_derives_from_release_states_only():
    """The chain's ``states`` ladder is EXACTLY ``release.STATES`` — the sub-organ band
    added no rung (the ladder is the mechanism, sub-organs are cards)."""
    if not _has_falqon():
        pytest.skip("no falqon")
    out = ps.chain(_FALQON)
    assert [s["state"] for s in out["states"]] == list(release.STATES)


# --------------------------------------------------------------------------- #
# Lane 0 — sub_organs attach under the right state, with reader_door + fire_action
# --------------------------------------------------------------------------- #

@falqon_only
def test_suborgans_attach_under_the_right_states():
    """detectors/proxy/growth under UNDER_CONVERGENCE (converge); bibliography/
    citation-direction/figures under STAGED (staged); structural-conformance under
    WELDED (weld) — each entry carrying id/label/blurb/producer/reader_door/fire_action."""
    out = ps.chain(_FALQON)
    by_organ = {o["id"]: [s["id"] for s in o.get("sub_organs", [])] for o in out["organs"]}
    # evolution + fitness joined 2026-07-20 (THE EVOLUTION DESK): the judgment
    # stage's queue and selection's instrument panel, both converge-side. selection
    # joined 2026-07-21 (THE SELECTION FACE): heredity's ratify sheet, beside fitness.
    # derivation joined 2026-07-21 (THE DERIVATION FACE): the aspiration-first reach
    # organ (the maximal claim + the isnad chain), beside selection.
    assert set(by_organ.get("converge", [])) == {"detectors", "proxy", "growth",
                                                 "evolution", "fitness", "selection",
                                                 "derivation"}
    assert set(by_organ.get("staged", [])) == {"bibliography", "citation-direction", "figures"}
    assert by_organ.get("weld", []) == ["structural-conformance"]
    # states with no sub-organs carry no (empty) band — the payload stays lean.
    assert "sub_organs" not in next(o for o in out["organs"] if o["id"] == "lock")


@falqon_only
def test_every_suborgan_carries_reader_door_and_fire_action_field():
    """Each sub-organ names a reader_door (GET /pipeline/organ) + a fire_action field
    (a launch-roster action, or None for a read-only organ whose fire is elsewhere)."""
    from laplace.manuscript import storyboard as sb
    out = ps.chain(_FALQON)
    roster = sb.launch_roster()
    roster_actions = {a["action"] for a in roster["local_safe"]} | \
                     {a["action"] for a in roster["model_heavy"]}
    for o in out["organs"]:
        for so in o.get("sub_organs", []):
            assert so["reader_door"] == f"/pipeline/organ?project={_FALQON}&organ={so['id']}"
            assert "fire_action" in so
            if so["fire_action"] is not None:
                assert so["fire_action"] in roster_actions, \
                    f"{so['id']} names a fire_action not in the roster (dead button)"
                # a fire_action ⇒ a wired control (never a dead button)
                assert so["controls"] and so["controls"][0]["action"] == so["fire_action"]


@falqon_only
def test_falqon_cards_carry_real_banked_telemetry():
    """The falqon sub-cards render REAL banked telemetry (2026-07-17 artifacts exist for
    every organ) — not honest-absence. Each summary is present with real counts."""
    out = ps.chain(_FALQON)
    subs = {s["id"]: s["summary"] for o in out["organs"] for s in o.get("sub_organs", [])}
    for oid in ("detectors", "bibliography", "citation-direction", "figures",
                "structural-conformance", "proxy", "growth"):
        assert subs[oid]["present"] is True, f"{oid} reads absent on falqon"
    # The gap census is the one LIVE count here: the detectors organ re-fires and banks a
    # new rounds/detector_organs_<date>.json, so a frozen literal pins a snapshot, not the
    # wire. It moved 30 → 10 on 2026-08-21 because ce8c77f1 ("ruling_recall returned 0 of
    # 241 rulings from a string iterated as characters") reconnected prior rulings to the
    # ledger — with judgement severed, no gap could ever be retired, and 30 was the count
    # of that severance. So assert what the card actually owes: a real, non-absent count
    # that is FAITHFUL to the newest banked round, read here through the artifact rather
    # than through the surface's own reader.
    from laplace.engine import detector_organs as _det
    banked = _det.read_detector_organs(_FALQON, ps._repo_root())
    assert banked["present"], "no detector round banked for falqon"
    assert subs["detectors"]["gaps"] == banked["gaps"]["gaps"] > 0, \
        "the detectors card does not render the newest banked gap census"
    assert subs["bibliography"]["resolved"] == 11
    assert subs["citation-direction"]["intents"] == 5
    assert subs["figures"]["placed"] == 2
    assert subs["structural-conformance"]["verdict"] == "patched"


# --------------------------------------------------------------------------- #
# RISK 4 — the chain payload stays bounded (no heavy telemetry inlined)
# --------------------------------------------------------------------------- #

@falqon_only
def test_chain_suborgan_payload_bounded():
    """The sub-organ band is a LIGHT summary only — its whole contribution stays small
    and NO list body (per-fork / per-intent / per-detector-by-class) is inlined; the
    heavy telemetry lazy-joins through the reader_door."""
    out = ps.chain(_FALQON)
    sub_bytes = sum(len(json.dumps(o.get("sub_organs", [])).encode())
                    for o in out["organs"])
    # the bound scales with the (bounded) number of night-organs, not with any
    # telemetry: it grew for the 7th converge sub-organ (THE DERIVATION FACE,
    # 2026-07-21) and again when the structural sub-card's store toggles gained their
    # WORDED meaning IN PLACE (HIS COMMISSION 9a, 2026-07-22 — a legitimate legibility
    # enrichment, not telemetry). The real "no list body inlined" law is the per-entry
    # scalars-only check below — this total is the belt-and-braces heuristic against a
    # body sneaking into a summary, and it must leave headroom for a legitimate new card.
    assert sub_bytes < 10240, f"sub-organ band bloated to {sub_bytes} bytes (lazy-join it)"
    for o in out["organs"]:
        for so in o.get("sub_organs", []):
            summ = so["summary"]
            # only bounded scalars + the tiny stores_fed name-list; no organ bodies.
            for k, v in summ.items():
                if isinstance(v, list):
                    assert k == "stores_fed" and len(v) <= 8, \
                        f"{so['id']}.summary.{k} inlines a list body (bound it)"


# --------------------------------------------------------------------------- #
# Lane 0 door — GET /pipeline/organ pure + honest 404s + 405 on POST
# --------------------------------------------------------------------------- #

def _organ(query, method="GET"):
    res = ps.handle("/pipeline/organ", query, method, b"")
    st, _ct, body = res
    return st, json.loads(body)


@falqon_only
@pytest.mark.parametrize("organ", ["detectors", "bibliography", "citation-direction",
                                   "structural-conformance", "figures", "proxy", "growth"])
def test_get_pipeline_organ_returns_the_reader_payload(organ):
    st, obj = _organ({"project": _FALQON, "organ": organ})
    assert st == 200
    assert obj["organ"] == organ and obj["project"] == _FALQON
    assert obj["payload"]["present"] is True


def test_get_pipeline_organ_honest_404s_and_400s():
    assert _organ({"project": _FALQON, "organ": "no_such"})[0] == 404
    assert _organ({"project": "no_such_project", "organ": "detectors"})[0] == 404
    assert _organ({"project": _FALQON})[0] == 400          # missing organ
    assert _organ({"organ": "detectors"})[0] == 400        # missing project


def test_get_pipeline_organ_post_is_405():
    st, _ct, body = ps.handle("/pipeline/organ",
                              {"project": _FALQON, "organ": "detectors"}, "POST", b"")
    assert st == 405


@falqon_only
def test_get_pipeline_organ_does_no_subprocess_on_the_read_path(monkeypatch):
    """WIRING LAW 2 — a boom-guard: no organ read (including the proxy + figures live
    dry-runs) may spawn a subprocess on the GET path."""
    def _boom(*a, **k):
        raise AssertionError("a /pipeline/organ read spawned a subprocess (GET must be pure)")
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    for organ in ("detectors", "bibliography", "citation-direction",
                  "structural-conformance", "figures", "proxy", "growth"):
        assert _organ({"project": _FALQON, "organ": organ})[0] == 200
    assert _organ({"project": _FALQON, "organ": "proxy", "dryrun": "1"})[0] == 200
    assert _organ({"project": _FALQON, "organ": "figures", "dryrun": "1"})[0] == 200


@falqon_only
def test_get_pipeline_organ_writes_nothing_to_the_tree():
    """Every GET read — including the proxy dry-run frames + the figures live dry-run —
    leaves the tree byte-identical (pure reads on GET)."""
    before = _git_status()
    for organ in ("detectors", "bibliography", "citation-direction",
                  "structural-conformance", "figures", "proxy", "growth"):
        _organ({"project": _FALQON, "organ": organ})
    _organ({"project": _FALQON, "organ": "proxy", "dryrun": "1"})
    _organ({"project": _FALQON, "organ": "figures", "dryrun": "1"})
    assert _git_status() == before, "a GET /pipeline/organ read mutated the tree"


# --------------------------------------------------------------------------- #
# Lane 5 — proxy dry-run frames + the figures live dry-run
# --------------------------------------------------------------------------- #

@falqon_only
def test_proxy_dryrun_returns_drive_frames():
    """organ=proxy&dryrun=1 returns fork_adjudicator.drive dry-run frames (parked count
    + fork handles) — the supervised live bank stays desk-only (never on a GET)."""
    st, obj = _organ({"project": _FALQON, "organ": "proxy", "dryrun": "1"})
    assert st == 200
    p = obj["payload"]
    assert p["mode"] == "dry-run" and "parked" in p and isinstance(p["forks"], list)


@falqon_only
def test_figures_dryrun_is_the_one_live_nonmutating_preview():
    """organ=figures&dryrun=1 is the ONE permitted live dry-run (RISK 2):
    run(apply=False, run_gen=False) — computes matches, mutates nothing."""
    st, obj = _organ({"project": _FALQON, "organ": "figures", "dryrun": "1"})
    assert st == 200
    p = obj["payload"]
    assert p.get("live_dry_run") is True and "matched_count" in p


# --------------------------------------------------------------------------- #
# RISK 1 — view=mechanism: the payload derives from the organ's OWN reader
# --------------------------------------------------------------------------- #

@falqon_only
def test_reader_door_calls_the_organ_reader_not_a_reparse():
    """The detectors organ payload is IDENTICAL to detector_organs.read_detector_organs
    — the card calls the organ's own reader, never re-parses the artifact (RISK 1)."""
    from laplace.engine import detector_organs as det
    root = ps._repo_root().resolve()
    ctx = registry.project_context(_FALQON, root)
    proj = registry.resolve(_FALQON)
    got = ps.read_organ("detectors", proj.name, ctx, root)
    assert got == det.read_detector_organs(proj.name, root)


# --------------------------------------------------------------------------- #
# Lane 3 / RISK 2 — the dials-vs-gate seam: a red gate renders warn, NEVER green
# --------------------------------------------------------------------------- #

def _write_verdict(store_dir: Path, obj):
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / "gate_verdict.json").write_text(json.dumps(obj), encoding="utf-8")


def test_structural_store_dial_reads_gate_through_stage_retrieval(tmp_path):
    """The structural store rows read each store's gate through stage_retrieval's OWN
    logic (``_gate_refusal`` — NEVER re-derived): a PASSED gate → state 'passed' /
    passed True; an absent verdict → 'absent' / passed False; a
    refusal_proof_holds=false verdict → 'failed' / passed False. A red/absent gate is
    NEVER rendered 'passed' (the CHIP law) and carries the refusal reason inline."""
    stores = tmp_path / "corpus_stores"
    # section_architecture: a real passing verdict
    _write_verdict(stores / "section_architecture", {"passed": True})
    # spine_chain: NO gate_verdict.json → absent
    (stores / "spine_chain").mkdir(parents=True, exist_ok=True)
    dials_state = ps._dials_state_for()
    rows = {r["store"]: r for r in ps._structural_store_dials(dials_state, tmp_path)}

    arch = rows["section_architecture"]
    assert arch["gate"]["state"] == "passed" and arch["gate"]["passed"] is True

    spine = rows["spine_chain"]
    assert spine["gate"]["state"] == "absent" and spine["gate"]["passed"] is False
    assert spine["gate"]["refusal"], "an absent gate must carry a refusal reason"

    # now flip section_architecture to a REFUSING verdict (gate.passed but proof fails)
    _write_verdict(stores / "section_architecture",
                   {"passed": True, "refusal_proof_holds": False})
    rows = {r["store"]: r for r in ps._structural_store_dials(dials_state, tmp_path)}
    bad = rows["section_architecture"]
    assert bad["gate"]["passed"] is False and bad["gate"]["state"] == "failed", \
        "a store that cannot prove its refusal is NEVER rendered passed (the smuggle)"
    assert bad["gate"]["refusal"]


def test_structural_gate_matches_stage_retrieval_verdict(tmp_path):
    """The gate the card shows equals stage_retrieval's own verdict for the SAME file —
    proving the card delegates the rule, never re-implements it (RISK 2 / never re-derive)."""
    from laplace.pipeline import stage_retrieval as sr
    stores = tmp_path / "corpus_stores"
    _write_verdict(stores / "section_architecture",
                   {"passed": True, "wired_in": False})   # a refusing shape
    (stores / "spine_chain").mkdir(parents=True, exist_ok=True)
    dials_state = ps._dials_state_for()
    rows = {r["store"]: r for r in ps._structural_store_dials(dials_state, tmp_path)}
    for store, row in rows.items():
        verdict = sr._read_json(stores / store / "gate_verdict.json")
        assert row["gate"]["passed"] == (sr._gate_refusal(verdict) is None)


def test_client_refuses_to_arm_a_red_gate():
    """The pane guards the dial-cannot-override-the-gate law in source: arming
    enabled=on for a store whose gate is not passed surfaces the refusal + reverts the
    toggle instead of POSTing a config that SystemExits at run (Lane 3)."""
    mjs = (Path(ps.__file__).resolve().parent / "static_shared"
           / "pipeline-panes.mjs").read_text(encoding="utf-8")
    assert "k.gate" in mjs and "gateRefuse" in mjs
    # the guard fires on (arming true) AND (gate not passed), and does NOT dialWrite then.
    assert "v === true && !k.gate.passed" in mjs


# --------------------------------------------------------------------------- #
# RISK 1 — the re-parse clause, broadened: EVERY reader door delegates to the
# organ's OWN reader (never a re-parse of the raw artifact)
# --------------------------------------------------------------------------- #

@falqon_only
def test_every_reader_door_delegates_to_the_organ_reader():
    """view=mechanism for EVERY pass-through organ: ``read_organ`` returns the organ's
    own reader output byte-identical — never a re-parse layer (RISK 1). detectors ·
    bibliography · citation-direction · figures each EQUAL their named reader;
    structural-conformance equals ``read_manifest`` PLUS the gate join (its only
    enrichment), so even the enriched organ derives its manifest facts from the reader,
    never a hand re-parse of the artifact."""
    from laplace.engine import detector_organs as det
    from laplace.pipeline import bibliography_stage as bib
    from laplace.pipeline import citation_direction as cd
    from laplace.pipeline import figure_runner as fr
    from laplace.pipeline import structural_conformance as sc
    root = ps._repo_root().resolve()
    ctx = registry.project_context(_FALQON, root)
    proj = registry.resolve(_FALQON)
    md = ps._manuscript_dir(ctx)

    assert ps.read_organ("detectors", proj.name, ctx, root) == \
        det.read_detector_organs(proj.name, root)
    assert ps.read_organ("bibliography", proj.name, ctx, root) == bib.read_manifest(md)
    assert ps.read_organ("citation-direction", proj.name, ctx, root) == cd.read_run_record(md)
    assert ps.read_organ("figures", proj.name, ctx, root) == fr.read_manifest(md)

    # structural = the reader's manifest dict PLUS the gate join (the ONE enrichment):
    # every manifest key is the reader's own value, never re-derived.
    got = ps.read_organ("structural-conformance", proj.name, ctx, root)
    base = sc.read_manifest(md)
    for k, v in base.items():
        assert got[k] == v, f"structural payload re-derived {k!r} instead of using read_manifest"
    assert set(got) == set(base) | {"store_gates"}, \
        "structural payload added a field beyond the reader + the gate join (a re-parse leak)"


# --------------------------------------------------------------------------- #
# RISK 6 — supervised-only: no GET path / no un-armed click reaches the live bank
# --------------------------------------------------------------------------- #

def test_proxy_live_bank_is_supervised_only():
    """RISK 6 — the proxy loop's LIVE bank stays desk-supervised: the ``/pipeline/organ``
    reader drives the proxy ONLY in dry-run (``fork_adjudicator.drive(mode='dry-run')``,
    zero tree writes), and NEITHER ``pipeline_surface.py`` NOR ``pipeline-panes.mjs`` ever
    reaches the live bank — no ``mode='live'``, no ``bank_fork_ruling``, no ``--live``.
    The proxy sub-organ carries NO scoped fire (``fire_action`` None), so no un-armed
    click can bank; the card's noFireZone names the desk door instead of a dead button."""
    surf = Path(ps.__file__).resolve().parent
    py = (surf / "pipeline_surface.py").read_text(encoding="utf-8")
    mjs = (surf / "static_shared" / "pipeline-panes.mjs").read_text(encoding="utf-8")
    for needle in ('mode="live"', "mode='live'", "bank_fork_ruling", "--live"):
        assert needle not in py, f"pipeline_surface.py reaches the supervised live bank: {needle!r}"
        assert needle not in mjs, f"pipeline-panes.mjs reaches the supervised live bank: {needle!r}"
    # the ONLY fork_adjudicator.drive call in the surface is pinned to dry-run mode.
    assert 'fork_adjudicator.drive(root, mode="dry-run"' in py, \
        "the proxy drive call is not pinned to dry-run mode"
    # the proxy (and growth) sub-organs carry no scoped fire → no un-armed click can bank.
    subs = {s["id"]: s for state in ps._SUBORGAN_FOR_STATE.values() for s in state}
    assert subs["proxy"]["fire_action"] is None, \
        "the proxy sub-organ must carry no scoped fire (supervised-only)"
    # the pane names the desk-supervised door for the proxy, never a live-bank click.
    assert "desk-supervised" in mjs and "POST /desk/act" in mjs


def test_release_states_membership_pinned_no_night_organ_becomes_a_state():
    """RISK 3 (the wiring panel's residue): a night-organ modeled as a release STATE
    would corrupt release.STATES = mechanism. The canonical ten-membership is pinned
    here BY VALUE, so adding an eleventh state (or renaming one) fails loudly and the
    author decides — sub-organs live in ``_SUBORGAN_FOR_STATE`` and nowhere else."""
    from laplace.pipeline import release
    assert release.STATES == (
        "STAGED", "WELDED", "MECHANICALLY_VALID", "UNDER_CONVERGENCE",
        "CANDIDATE_LOCKED", "AUTHOR_REVIEWED", "FINAL_CLEAN_BUILD",
        "FINAL_GATES_PASSED", "AUTHOR_ACCEPTED", "RELEASED"), \
        "release.STATES membership moved — a night-organ must never become a state"
    # and no sub-organ id shadows a state name in any casing.
    import laplace.web.pipeline_surface as ps
    sub_ids = {s["id"].upper().replace("-", "_")
               for state in ps._SUBORGAN_FOR_STATE.values() for s in state}
    assert not (sub_ids & set(release.STATES)), \
        "a sub-organ id collides with a release state name"


# --------------------------------------------------------------------------- #
# B1 — the consequential door for a reproject next-act lands on the organ
# that OWNS the fire control (_ACTION_ORGAN["re-projection"] = staged), never
# wherever the chain currently sits: the door must promise what it delivers.
# --------------------------------------------------------------------------- #

def test_consequential_door_for_reproject_targets_the_staged_organ():
    """The chain's CURRENT organ is deliberately ``release`` here — the exact shape
    of B1 (the reprojection fire control renders on ``staged``, not wherever the
    chain currently sits). Both the primary door (``href``) and the organ-open
    button (``organ``), built from the same brief dict, must land on staged."""
    ch = {"organs": [{"id": "release", "status": "current"},
                     {"id": "staged", "status": "pending"}]}
    verdict = {"next_act": {
        "verb": "reproject", "target": "gen-open-id",
        "label": "reproject — gen-4 is open",
        "gen_word": "gen-4", "brief": None,
        "href": None, "cost_class": "model-heavy", "psu": "banks a work order"}}
    conseq = ps._brief_consequential("myproj", ch, verdict)
    assert conseq is not None
    assert conseq["organ"] == ps._ACTION_ORGAN["re-projection"] == "staged"
    assert conseq["href"] == "/project?project=myproj&organ=staged"
    assert conseq["label"] == "open the gen-4 reprojection"


def test_consequential_door_for_non_reproject_verb_still_falls_back_to_current_organ():
    """A next-act with no scoped owner (no ``href``, a verb other than reproject)
    keeps the prior fallback — the door opens wherever the chain currently sits,
    proving the fix is scoped to the owned-organ verb and not a blanket change."""
    ch = {"organs": [{"id": "release", "status": "current"},
                     {"id": "staged", "status": "pending"}]}
    verdict = {"next_act": {
        "verb": "harnessed-round", "target": None,
        "label": "run the harnessed round",
        "href": None, "cost_class": "cheap", "psu": "none"}}
    conseq = ps._brief_consequential("myproj", ch, verdict)
    assert conseq is not None
    assert conseq["organ"] == "release"
    assert conseq["href"] == "/project?project=myproj&organ=release"


# --------------------------------------------------------------------------- #
# THE FIRE MADE LEGIBLE (r2 stranger-walk fix, evidence/r2_paces_2026-07-23) —
# the door "open the gen-4 reprojection" lands on the staged card (B1); the walk
# found the control there is a bare 're-projection · banks' button with no gen tag,
# the named brief an unreachable non-clickable span, the cost only 'model-heavy'.
# The fix: the staged control greets by the generation name, the brief is a REAL
# door, the cost is concretized in plain truth — the SAME reproject-fire dict backing
# both the staged control and the brief's consequential door (they speak identically).
# --------------------------------------------------------------------------- #

def test_reproject_fire_composes_the_named_control_and_plain_cost():
    """``_reproject_fire`` composes the fire the author presses himself: the generation
    name, a ``fire the <gen> reprojection`` label, and the model-heavy cost in plain words
    (the truth of run_launch — banks a work order, runs nothing, a shepherded session runs
    it; no invented numbers). Scoped strictly to the reproject verb — any other next-act
    (or none) yields ``None``, so no other control is ever touched."""
    na = {"verb": "reproject", "gen_word": "gen-4", "brief": "reprojection/gen4_brief.md",
          "cost_class": "model-heavy", "psu": "banks a work order"}
    fire = ps._reproject_fire(na, None)          # md=None ⇒ brief_door honest-absent
    assert fire is not None
    assert fire["gen_word"] == "gen-4"
    assert fire["fire_label"] == "fire the gen-4 reprojection"
    assert "banks a work order now, runs nothing" in fire["cost_plain"]
    assert "shepherded session" in fire["cost_plain"]
    assert fire["brief"] == "reprojection/gen4_brief.md"
    assert fire["brief_door"] is None            # no manuscript dir ⇒ no dead link
    # scoped to the verb — never enriches a non-reproject next-act
    assert ps._reproject_fire({"verb": "harnessed-round"}, None) is None
    assert ps._reproject_fire({}, None) is None
    assert ps._reproject_fire(None, None) is None


def test_brief_door_resolves_a_real_file_to_a_fenced_file_uri(tmp_path):
    """The brief made a REAL door: a manuscript-relative brief that resolves to a real
    file UNDER the manuscript dir becomes a ``/project/doc`` link (the general,
    scanner-served manuscript-doc route — no more dead ``file://`` deep-link, his ruling
    RW-20260723-154721-984120). Honest-absent — never a dead link — when the brief is
    empty, the manuscript dir is unknown, the path is not a file, or it escapes the
    manuscript dir (the containment fence)."""
    md = tmp_path / "manuscript"
    (md / "reprojection").mkdir(parents=True)
    brief = md / "reprojection" / "gen4_brief.md"
    brief.write_text("# gen-4 brief\n", encoding="utf-8")

    door = ps._brief_door(md, "reprojection/gen4_brief.md")
    assert door is not None
    assert door["href"].startswith("/project/doc?dir="), \
        "the brief must be a REAL reachable door, not the old dead file:// link"
    assert "path=reprojection/gen4_brief.md" in door["href"]
    assert "gen4_brief.md" in door["label"]
    assert door["path"] == "reprojection/gen4_brief.md"

    # honest absence, never a dead link
    assert ps._brief_door(md, "reprojection/nope.md") is None      # not a file
    assert ps._brief_door(md, None) is None                        # no brief
    assert ps._brief_door(md, "  ") is None                        # blank brief
    assert ps._brief_door(None, "x.md") is None                    # no manuscript dir
    # containment fence — a path escaping the manuscript dir never resolves
    (tmp_path / "escape.md").write_text("x", encoding="utf-8")
    assert ps._brief_door(md, "../escape.md") is None


@falqon_only
def test_staged_card_reproject_control_greets_by_gen_and_carries_the_brief_door():
    """END-TO-END: when the machine's next act is a reproject, the staged organ card's
    re-projection control (where "open the gen-4 reprojection" lands, B1) carries the
    ``reproject`` enrichment — greeting by the generation name, the plain cost, and the
    brief as a REAL door (gen4_brief.md exists on disk for falqon). Guarded: if falqon's
    gen-4 has since been stamped (the reproject next-act retired), the shape is gone and
    the clause skips rather than falsely failing."""
    root = ps._repo_root().resolve()
    from laplace.pipeline import project_state
    na = (project_state.project_verdict(root, _FALQON) or {}).get("next_act") or {}
    if na.get("verb") != "reproject":
        pytest.skip("falqon is not on a reproject next-act right now")
    out = ps.chain(_FALQON)
    owner = ps._ACTION_ORGAN["re-projection"]          # 'staged'
    staged = next(o for o in out["organs"] if o["id"] == owner)
    ctrl = next((c for c in staged.get("controls", []) if c["action"] == "re-projection"), None)
    assert ctrl is not None, "the staged card carries no re-projection control"
    rp = ctrl.get("reproject")
    assert rp, "the re-projection control does not greet by generation (the r2 gap)"
    assert rp["gen_word"] == na["gen_word"]
    assert rp["fire_label"] == "fire the " + na["gen_word"] + " reprojection"
    assert "banks a work order now, runs nothing" in rp["cost_plain"]
    if na.get("brief"):
        bd = rp["brief_door"]
        assert bd and bd["href"].startswith("/project/doc?"), "the brief is not a real door"
        assert na["brief"].rsplit("/", 1)[-1] in bd["label"]
    # scoping proof: a non-reproject control on the same board carries no enrichment.
    for o in out["organs"]:
        for c in o.get("controls", []):
            if c["action"] != "re-projection":
                assert "reproject" not in c, \
                    f"{c['action']} wrongly carries a reproject enrichment"


def test_consequential_reproject_names_the_same_brief_door(tmp_path):
    """FIX #4 — the consequential card names the brief as the SAME real door the staged
    fire control carries: the move and its fire point at one reachable brief. Proven by
    equality against ``_reproject_fire``'s own ``brief_door`` for the same manuscript dir."""
    md = tmp_path / "manuscript"
    (md / "reprojection").mkdir(parents=True)
    (md / "reprojection" / "gen4_brief.md").write_text("# brief\n", encoding="utf-8")

    class _Ctx:
        manuscript_dir = md

    ch = {"organs": [{"id": "release", "status": "current"},
                     {"id": "staged", "status": "pending"}]}
    verdict = {"next_act": {
        "verb": "reproject", "target": "g", "label": "reproject — gen-4 is open",
        "gen_word": "gen-4", "brief": "reprojection/gen4_brief.md",
        "href": None, "cost_class": "model-heavy", "psu": "banks a work order"}}
    conseq = ps._brief_consequential("myproj", ch, verdict, _Ctx())
    assert conseq["organ"] == "staged"
    assert conseq["label"] == "open the gen-4 reprojection"
    bd = conseq.get("brief_door")
    assert bd and bd["href"].endswith("gen4_brief.md")
    assert "gen4_brief.md" in bd["label"]
    # THE identity: the consequential door and the staged control's door are the same dict.
    fire = ps._reproject_fire(verdict["next_act"], md)
    assert fire["brief_door"] == bd, \
        "the consequential + staged brief doors must be identical (one reachable brief)"
    # an unresolved brief leaves the move standing with no dead link
    verdict["next_act"]["brief"] = "reprojection/missing.md"
    conseq2 = ps._brief_consequential("myproj", ch, verdict, _Ctx())
    assert "brief_door" not in conseq2 and conseq2["label"] == "open the gen-4 reprojection"


def test_pane_renders_the_named_reproject_fire_and_the_brief_door():
    """The pane source carries the reproject fire face + the brief door (the render half of
    the fix): the controls zone branches on ``c.reproject`` into ``reprojectControl`` (the
    named greeting + plain cost + the real brief door), and ``conseqHTML`` renders
    ``cq.brief_door`` — so the two surfaces both land the reachable brief."""
    mjs = (Path(ps.__file__).resolve().parent / "static_shared"
           / "pipeline-panes.mjs").read_text(encoding="utf-8")
    assert "c.reproject" in mjs and "function reprojectControl" in mjs
    assert "rp.fire_label" in mjs and "rp.cost_plain" in mjs and "rp.brief_door" in mjs
    assert "cq.brief_door" in mjs
