"""the pipeline surface (surface 5) — the live chain, at ``/pipeline``.

The conception's P3 (DESIGN_2026-07-14 §7): the entire chain — stages, organs,
subloops — rendered FROM the release state machine and the round stores, never a
drawn diagram. VIEW = MECHANISM: a stage exists here iff it is a real state in
``release.STATES`` (the mechanism) or a real dial group in ``dials.defaults()``;
a stage that lives only in prose renders from the store truth or not at all.

His ruling (verbatim, 2026-07-14): "dials are useful but they need to be
integrated into the pipeline." So this surface DOES NOT reinvent the dials editor —
it re-houses it IN PLACE, per organ: each organ card's expansion carries ITS dials
(the ``/dials`` profile knobs mapped to their consuming organ, mechanically, by the
group name), and edit/undo ride the EXISTING ``/dials/op`` + ``/dials/undo``
endpoints (``dials_surface`` stays the one write path). The ``/dials`` standalone
page dies; its wire endpoints live on, consumed here.

READ-ONLY. This module owns no write machinery: every scoped fire dispatches
through the EXISTING ``/storyboard/run/launch`` door (local-safe fires; model-heavy
BANKS a work-order — the offer law), and the dry-run "what would fire" preview is
``storyboard``'s pure-read worklist (``/storyboard/propagate``). This module only
ASSEMBLES the board's one read model and names the mechanism behind every panel (ⓘ).

The routes (all GET; every mutation rides an existing door elsewhere):

  * ``GET /pipeline``        — the surface page (``pipeline.html``; served by the
                               scanner, like the other apps — :func:`handle` returns
                               ``None`` for the bare path).
  * ``GET /pipeline/chain``  — the one board read model: the release-state ladder
                               (which passed / current / ahead, from the mechanism),
                               each organ a card (its owning state, evidence, verdicts,
                               staleness, its dials in place, its scoped controls), and
                               the regrade-health / run-tray joins named for lazy fetch.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from laplace.pipeline import dials as _dials_mod
from laplace.pipeline import registry
from laplace.pipeline import release as _release

_HTML = Path(__file__).resolve().parent / "pipeline.html"
_JSON = "application/json; charset=utf-8"

_DEFAULT_PROFILE = "dials-v1.yaml"

#: F3 (audit §A5): the converge organ's lock roster is TIER-AWARE — the same
#: dial group ``loop.lock.readers`` is served by TWO organs at different widths.
#: The HARNESSED converge flow implements every rostered arm; the OLD loop
#: (``loop.fix_mode=loop``, ``project-fixedpoint.js``) implements neither R9 (the
#: caption-blind rasteriser) nor R10 (the whole-PDF-restart), so it serves the
#: roster MINUS R9/R10 (harnessed-only arms, per the dials.py tier ruling). Named
#: here as data so /pipeline renders the carve-out per organ rather than mapping the
#: loop dial group to the converge organ uniformly (the invisibility this fixes).
_LOCK_CARVEOUT = (
    "lock roster per organ — the harnessed converge flow serves the full "
    "loop.lock.readers roster; the old loop (fix_mode=loop) serves it MINUS "
    "R9/R10 (the caption-blind rasteriser and whole-PDF-restart arms are "
    "harnessed-only, per the dials.py tier ruling)."
)


def _repo_root() -> Path:
    from laplace.core.checkout import repo_root as rr   # the serving checkout's owner (the server module held the same object under an old name)
    return rr()


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, default)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else default
    return (v or default).strip()


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# THE ORGANS — one per release STATE (the chain comes from the mechanism, not a
# drawing). ``label`` names the operator that acts at the stage; ``blurb`` is the
# ⓘ one-liner. NEVER_RUN is a pre-state carried only when the machine never ran.
# ---------------------------------------------------------------------------
_ORGAN_FOR_STATE: dict[str, tuple[str, str, str]] = {
    "STAGED": ("staged", "staged build",
               "conceptric → storyboard manifest → staged prose (the dispatch manifest)"),
    "WELDED": ("weld", "weld",
               "the seam weld over the assembled sections"),
    "MECHANICALLY_VALID": ("mechanical", "mechanical validation",
                           "the mechanical gate — geometry / refs / cites over the compile log"),
    "UNDER_CONVERGENCE": ("converge", "converge",
                          "the harnessed converge loop: detect → adjudicate → one strong fix "
                          "→ re-detect → revert-on-regression → lock"),
    "CANDIDATE_LOCKED": ("lock", "candidate lock",
                         "candidate_lock.lock_eligible — hard-pass + clean compile + complete round"),
    "AUTHOR_REVIEWED": ("review", "author review",
                        "the author review gate — banks a version snapshot (Fork-7)"),
    "FINAL_CLEAN_BUILD": ("final_build", "final build",
                          "the finalize compile — a named, metadata-stamped PDF"),
    "FINAL_GATES_PASSED": ("final_gates", "final gates",
                           "the figure-layout review gates over the finalised PDF"),
    "AUTHOR_ACCEPTED": ("accept", "accept",
                        "the author's acceptance of the release bundle"),
    "RELEASED": ("release", "release",
                 "the pinned release bundle — byte-addressable, GERARD'S LAW"),
}

#: dial GROUP → the organ that consumes it, derived BY NAME from what each group
#: governs (documented in ``dials.py`` _DEFAULTS). A group no organ claims (roles,
#: prompts — cross-cutting dispatch calibration) renders in the 'global' card. This
#: is a mapping table, never a drawn diagram: the knobs render from the live profile,
#: the stages from release.STATES; the table only says which stage reads which knob.
_DIAL_GROUP_ORGAN: dict[str, str] = {
    "loop": "converge",
    "drift": "converge",
    "suppression": "converge",
    "routing": "converge",
    "machine_adjudication": "converge",
    "regen_grain": "converge",
    "mech": "mechanical",
    # roles / prompts fall through to 'global' (cross-cutting; no single stage owns them).
}

#: HIS COMMISSION (PV-20260722T225941Z) — each dial wears a WORDED meaning + stage
#: effect IN PLACE. The meaning is NOT machine-derivable (it lives in the ``dials.py``
#: _DEFAULTS comments as prose); this table lifts that prose faithfully, keyed by dotted
#: path (``roles.*`` / ``stores.*`` wildcards collapse the per-name leaves). A leaf ABSENT
#: here carries no invented prose — the card states plainly that the meaning is not
#: documented in code/docs (the offer law applied to legibility). ``what`` = what the dial
#: is; ``effect`` = what moving it does to the run. The consuming organ is derived
#: separately (``_DIAL_GROUP_ORGAN`` → the card the knob renders on), never restated here.
_DIAL_MEANINGS: dict[str, dict[str, str]] = {
    "roles.*.model": {
        "what": "the model tier this dispatch role runs at (haiku < sonnet < opus).",
        "effect": "raises/lowers the capability (and cost) of every agent compiled for "
                  "this role; sealed readers are least-capable BY DESIGN (worse-is-better)."},
    "roles.*.effort": {
        "what": "the reasoning-effort tier for this role (low / medium / high).",
        "effect": "trades depth for spend on every agent of this role — high for "
                  "builders/welders/referee, low for utilities."},
    "loop.max_rounds": {
        "what": "the round budget for the converge loop.",
        "effect": "caps how many detect→fix→re-detect rounds one convergence may spend "
                  "before it stops (a zero budget is nonsense — the gate refuses < 1)."},
    "loop.fix_mode": {
        "what": "which converge flow runs — the HARNESSED pass (demoted middle: detect → "
                "one strong fix → re-detect → revert-on-regression → conditional 2nd pass) "
                "or the old every-round LOOP.",
        "effect": "'harnessed' is the ruled target; 'loop' restores the old "
                  "project-fixedpoint every-round converge (and serves the lock roster "
                  "MINUS R9/R10). Gate-pinned to 'loop' today, see dials.py."},
    "loop.harnessed.second_pass_open_threshold": {
        "what": "the residue floor a conditional SECOND harnessed pass needs.",
        "effect": "a 2nd opus pass fires only if the re-detect improved AND this many "
                  "findings still stand; below it the residue rides to the lock readers."},
    "loop.harnessed.max_passes": {
        "what": "the hard cap on harnessed fixing passes in one invocation.",
        "effect": "the ceremony guard — the first pass plus at most this-minus-one "
                  "conditional passes."},
    "loop.weld": {
        "what": "when the converge leg welds — auto (only when the round asks), always "
                "(every round), never (scoped seam passes only).",
        "effect": "governs whether a converge round re-welds the seam across sections."},
    "loop.weld_global_dirty_threshold": {
        "what": "the dirty-section count at/above which a scoped seam pass escalates to a "
                "GLOBAL reweld.",
        "effect": "a fix touching this many sections is no longer local — it triggers a "
                  "whole-paper reweld."},
    "loop.final_layer": {
        "what": "the end-stage rhetorical-scaffold wash — off, or descaffold.",
        "effect": "'descaffold' runs final_layer over the CONVERGED artefact as the last "
                  "layer (the four defensive registers, the negative-inventory, the "
                  "disclaimer keep-once table) and banks a before/after census; off = never."},
    "loop.lock.readers": {
        "what": "the readers that must return a verdict at candidate-lock.",
        "effect": "sets the hold-out bar for locking a candidate; R9 (caption-blind) and "
                  "R10 (whole-artefact restart) are harnessed-lock-only arms."},
    "loop.lock.voice_wash": {
        "what": "whether the voice wash runs at the lock stage.",
        "effect": "gates the lock-cadence voice-wash pass (conjugate of loop.final_layer)."},
    "loop.verify_votes": {
        "what": "the verify-vote count at a gate.",
        "effect": "how many independent verify votes a gated decision demands (>= 1)."},
    "drift.page_change_warn": {
        "what": "the changed-page count above which a build is flagged unexpected.",
        "effect": "more than this many changed pages between builds reads as drift."},
    "drift.page_count_change": {
        "what": "how loudly a page-COUNT delta is reported (a count change is always loud).",
        "effect": "governs the loudness label on a page-count change (free string — the "
                  "author has not named a closed alternative set)."},
    "suppression.key": {
        "what": "the fingerprint key a suppressed finding is matched on.",
        "effect": "which fields (node / kind / fingerprint) identify 'the same finding' "
                  "for suppression — a narrower key suppresses less."},
    "suppression.stale_on_fingerprint_mismatch": {
        "what": "whether a suppression goes stale when the fingerprint moves.",
        "effect": "on = a changed fingerprint re-surfaces the finding (the content moved, "
                  "the old dismissal no longer applies)."},
    "routing.defer_kinds": {
        "what": "the finding KINDS the fixer defers to human adjudication.",
        "effect": "a deferred kind stays REPORTED (the panel is unclean, no lock) but is "
                  "never dispatched to builders — the class-grain conjugate of suppression. "
                  "Empty by default."},
    "routing.dismissal_recalibrate_threshold": {
        "what": "the meta-signal threshold: N dismissals of a finding-KIND surfaces "
                "'recalibrate the check?'.",
        "effect": "the class-vs-instance signal that the CHECK, not each finding, may be "
                  "miscalibrated (author-gated evidence only, no auto-recalibration)."},
    "machine_adjudication.enabled": {
        "what": "the machine-adjudication organ — verdicts banked as files before the route.",
        "effect": "on = the per-round adjudicate step runs the Tier-1 rules over deferred "
                  "classes and banks actor:'machine' verdicts before dispatch."},
    "machine_adjudication.may_dismiss": {
        "what": "the finding-KINDS the machine may DISMISS (drop a fingerprinted non-fault).",
        "effect": "a kind outside this list may only be confirmed or escalated, never "
                  "machine-dismissed. Empty by default (the machine dismisses nothing)."},
    "machine_adjudication.calibration_threshold": {
        "what": "N machine-dismissals of a KIND deposits a calibration intent.",
        "effect": "after this many dismissals of one kind, the CHECK is flagged possibly "
                  "miscalibrated (author-gated)."},
    "machine_adjudication.referee": {
        "what": "the referee tier for the undecidable (residue) queue.",
        "effect": "which role tier adjudicates the residue that the Tier-1 rules cannot "
                  "settle (defaults to the 'referee' role tier)."},
    "mech.overfull_floor_pt": {
        "what": "the mechanical geometry floor — overfull boxes over this many pt are "
                "unclean; sub-floor boxes are typographically invisible and tolerated.",
        "effect": "raises/lowers the visible-overflow bar the mechanical gate enforces "
                  "over the compile log."},
    "regen_grain.mode": {
        "what": "the regeneration grain — auto (density heuristic decides per section) or "
                "section (kill-switch: restore section-grain byte-identically).",
        "effect": "auto lets a sparse fault regenerate only the offending paragraph(s); "
                  "section forces the whole section every time."},
    "regen_grain.paragraph_max_fraction": {
        "what": "the fraction of a section's paragraphs at/below which it demotes to "
                "paragraph grain (must be in (0, 1]).",
        "effect": "above this fraction a fault is dense enough that a section rebuild is "
                  "the truthful grain."},
    "regen_grain.structural_kinds": {
        "what": "the finding KINDS that FORCE section grain even when sparse.",
        "effect": "a structural fault (a missing section-level object, a reorder) is never "
                  "a paragraph patch. Empty by default."},
    "fanout.max_width": {
        "what": "the fixed-width fan-out cap (0 = UNCAPPED — one batch = the whole list).",
        "effect": "caps how many agents a workflow fan-out dispatches per batch; 0 keeps "
                  "today's exact one-batch shape, a real cap is opt-in."},
    "fanout.batch_max_chars": {
        "what": "the char budget for a char-bounded pack() batch.",
        "effect": "the size budget consulted only by callers that batch on chars rather "
                  "than count."},
    "stores.*.enabled": {
        "what": "the stage-store kill-switch — a corpus store's FORM exemplars enter a "
                "stage's compiled dispatch only when this is on AND its holdout gate passed.",
        "effect": "the Dial cannot override the gate: on with an absent/failed gate REFUSES "
                  "loudly at run. Every store ships behaviour-inert (a compile is "
                  "byte-identical to pre-wire until a deliberate flip)."},
    "prompts.overrides_dir": {
        "what": "the directory the per-judge/per-reader/per-role prompt override files "
                "live in.",
        "effect": "a file <overrides_dir>/<name>.<md|txt|j2|jinja> REPLACES that judge's "
                  "built-in prompt template wholesale (see the prompts view for provenance)."},
    "evolution.ratify_mode": {
        "what": "the evolution desk's ratify DOOR SHAPE — per-item, or bulk-arm.",
        "effect": "'bulk-arm' additionally offers 'ratify all (N)': one arm previews every "
                  "open application, one attributed apply fires them, stop-on-first-failure. "
                  "The LAW (his word, armed + attributed, per-item records) is identical."},
    "selection.draft_psi": {
        "what": "which DRAFT selection-rule FILE the selection sheet reads "
                "(profiles/selection/<value>.yaml) — ψ/φ are HIS; the file only proposes.",
        "effect": "draft-psi-v2 adds the REACH GATE. Recalibration is a NEW file, never an "
                  "edit; the live default flips on his/the orchestrator's word, not a dial-nudge."},
}


def _dial_meaning(path: str) -> dict[str, str] | None:
    """The worded meaning for a dial leaf (``roles.*`` / ``stores.*`` collapse to the
    wildcard), or ``None`` when the meaning is not documented in code/docs — the card
    then states that plainly rather than inventing prose (HIS COMMISSION 9a)."""
    import re as _re
    m = _re.fullmatch(r"roles\.[^.]+\.(model|effort)", path)
    if m:
        return _DIAL_MEANINGS.get(f"roles.*.{m.group(1)}")
    m = _re.fullmatch(r"stores\.[^.]+\.enabled", path)
    if m:
        return _DIAL_MEANINGS.get("stores.*.enabled")
    return _DIAL_MEANINGS.get(path)


#: a run-panel launch action → the organ whose card offers it as a scoped control.
#: The action set + cost class + arm-to-fire come from ``storyboard.launch_roster``
#: (the mechanism); this only says which organ card each scoped control belongs to.
_ACTION_ORGAN: dict[str, str] = {
    "storyboard-rebuild": "staged",
    "re-projection": "staged",
    "dispatch-compile": "staged",
    "harnessed-round": "converge",
    "nodemap-rebuild": "converge",
    "projection-compile": "final_build",
    "dream": "global",
    # The cockpit completion (ACT 4 / E4b): every launch_roster action carries an
    # EXPLICIT owning organ — no silent fallback into the global card. These five are
    # the sub-organ fires (their sub-cards live under the state's organ in
    # _SUBORGAN_FOR_STATE); the owning organ is the state-organ that consumes them, so
    # the scoped control renders on the RIGHT stage card, never duplicated into global.
    "detector-run": "converge",              # detectors sub-organ (UNDER_CONVERGENCE)
    "bibliography-run": "staged",            # bibliography sub-organ (STAGED)
    "citation-direction-run": "staged",      # citation-direction sub-organ (STAGED)
    "figure-materialize": "staged",          # figures sub-organ (STAGED)
    "structural-conformance-run": "weld",    # structural-conformance sub-organ (WELDED)
}


# ---------------------------------------------------------------------------
# The sub-organs — the night-organs (detectors, literature, figures, structural,
# proxy/growth) that run WITHIN a stage, not as their own release STATE (THE
# CONJUGATE WAVE, SCOUT_2026-07-17). This table MIRRORS ``_ORGAN_FOR_STATE`` but
# NEVER touches ``release.STATES``: a sub-organ is a card nested under its
# consuming state-organ, never a new state (the new-state-corruption risk, §3).
#
# Each entry names its lawful READER (view=mechanism — the card calls the organ's
# own reader, never re-parses the artifact) and its ``fire_action`` (a
# ``storyboard.launch_roster`` action, or ``None`` for a read-only organ whose
# fire is desk-supervised). ``chain()`` attaches a LIGHT summary per sub-organ
# (bounded scalars); the FULL per-detector / per-intent / per-store telemetry
# lazy-fetches through ``GET /pipeline/organ`` (the reader_door), so the board's
# first paint stays bounded (the payload-bloat risk, §4).
# ---------------------------------------------------------------------------
_SUBORGAN_FOR_STATE: dict[str, list[dict[str, Any]]] = {
    # the detect phase of the harnessed converge loop + the proxy/growth steering
    "UNDER_CONVERGENCE": [
        {"id": "detectors", "reader": "detectors", "fire_action": "detector-run",
         "label": "detector organs",
         "blurb": "the detect phase — gap-ledger · meta-leak-scrub · source-delta · "
                  "promise-audit over the round census",
         "producer": "detector_organs.read_detector_organs (newest "
                     "rounds/detector_organs_<date>.json; no compile on the read)"},
        {"id": "proxy", "reader": "proxy", "fire_action": None,
         "label": "proxy loop",
         "blurb": "the fork-adjudication proxy (ENGINE-WIDE, not per-project) — parked "
                  "forks framed, verdicts banked, GENUINELY-HIS residue routed to the desk",
         "producer": "author_proxy.load_verdicts + fork_adjudicator.enumerate_parked_forks "
                     "(proxy_verdicts.jsonl, ROOT-scoped — engine-global, not this project; "
                     "the live bank is desk-supervised)"},
        {"id": "growth", "reader": "growth", "fire_action": None,
         "label": "growth steering",
         "blurb": "gap discovery vs closure — the metric that steers the conceptric "
                  "grow legs",
         "producer": "detector_organs.read_detector_organs gap census (discovery); "
                     "closure is the cross-round join on /analytics/loop"},
        # The evolution desk (2026-07-20): his ratification stage as a card — the
        # drafted contracts awaiting his word, each with the mined substrate + the
        # source context; ratify/hold/reject through /evolution/* (the one apply
        # path, armed + attributed; the draft-only law held structurally).
        {"id": "evolution", "reader": "evolution", "fire_action": None,
         "label": "evolution desk",
         "blurb": "the ratify queue — drafted evolution contracts awaiting his word; "
                  "ratify / hold / reject through the lawful doors",
         "producer": "evolution_consumer.read_ratify_queue (evolution/evolutions/* "
                     "joined against the feedback ledger; the apply fires ONLY through "
                     "POST /evolution/ratify — armed, attributed)"},
        # The fitness panel (2026-07-20): selection's instrument — readings, never
        # the rule (psi/phi stay his; the selection-layer WO carries the rest).
        {"id": "fitness", "reader": "fitness", "fire_action": None,
         "label": "fitness panel",
         "blurb": "the readings he rules φ/ψ against — debt trajectory · freeze "
                  "verdicts · mechround derivative · the named suite floor",
         "producer": "fitness_panel.read_fitness (banked run records + freeze "
                     "verdicts + census history + suite_baseline.json; pure read)"},
        # The selection face (2026-07-21): heredity's ratify stage as a card — each
        # scored generation joined to its own dated readings and a DRAFT verdict
        # (draft-psi-v1, versioned + inspectable). ψ/φ stay HIS; the ruling fires
        # through the selection desk's OWN doors (GET /selection/sheet · POST
        # /selection/rule — armed, attributed, record-only), never a run-launch fire.
        # fire_action is None because there is no storyboard launch action here (the
        # organ HAS doors, but they are /selection/*; the doors block in read_organ
        # names them, the evolution-desk idiom exactly).
        {"id": "selection", "reader": "selection", "fire_action": None,
         "label": "selection sheet",
         "blurb": "the ruling sheet — each generation's readings + a DRAFT verdict "
                  "(the versioned rule the sheet names, inspectable); promote / hold / "
                  "retire through the lawful doors, arm-then-bank (his overrides calibrate)",
         "producer": "selection_sheet.read_selection (generations.jsonl joined to the "
                     "dated reprojection refs + the draft rule; the ruling fires ONLY "
                     "through POST /selection/rule — armed, attributed, record-only)"},
        # The derivation face (2026-07-21): the aspiration-first reach organ as a card
        # — the maximal TRUE claim asserted as the boundary condition BEFORE
        # achievability is known, and the isnad chain from the substrate toward it
        # (each link attested via a forged .tex / a computation / a cite, or a NAMED
        # gap). INSPECTION reads derivation_organ (pure); INTERACTION fires through the
        # derivation face's OWN doors (GET /derivation/sheet · /derivation/fragment ·
        # POST /derivation/rescope · /derivation/forge · /derivation/contest — armed,
        # attributed). fire_action is None (the organ HAS doors, but they are
        # /derivation/*, not a storyboard launch — the selection/evolution-desk idiom).
        {"id": "derivation", "reader": "derivation", "fire_action": None,
         "label": "derivation face",
         "blurb": "the maximal TRUE claim (asserted before achievability) + the isnad "
                  "chain toward it; each link attested or a NAMED gap; re-scope / forge "
                  "/ contest via the lawful doors",
         "producer": "derivation_organ (aspiration.json + chain.jsonl + derivations/"
                     "*.tex); acts via POST /derivation/rescope·forge·contest "
                     "(armed, attributed)"},
    ],
    # the materialize leg of the staged build: refs render, cites get sources, figures place
    "STAGED": [
        {"id": "bibliography", "reader": "bibliography", "fire_action": "bibliography-run",
         "label": "bibliography",
         "blurb": "the References made to render — cited/resolved/dangling resolution "
                  "+ literature intents for dangling keys",
         "producer": "bibliography_stage.read_manifest (bibliography_manifest.json; "
                     "no compile on the read)"},
        {"id": "citation-direction", "reader": "citation_direction",
         "fire_action": "citation-direction-run",
         "label": "citation direction",
         "blurb": "dangling + unverified cites → directed retrieval → entailment judge "
                  "packets (admission deferred to the judge)",
         "producer": "citation_direction.read_run_record (run_record.json + entailment "
                     "manifests; no network on the read)"},
        {"id": "figures", "reader": "figures", "fire_action": "figure-materialize",
         "label": "figures",
         "blurb": "the text's figure promises matched to generators, placed as floats; "
                  "promised-but-absent typed as computation intents",
         "producer": "figure_runner.read_manifest (figure_manifest.json; the live "
                     "dry-run is apply=False run_gen=False, proven non-mutating)"},
    ],
    # the pre-projection conformance pass over the welded seam (the dials-and-gate lane)
    "WELDED": [
        {"id": "structural-conformance", "reader": "structural",
         "fire_action": "structural-conformance-run",
         "label": "structural conformance",
         "blurb": "sections scored against the author's own architecture/spine manifolds "
                  "→ candidate respine/reorder/demote patches",
         "producer": "structural_conformance.read_manifest "
                     "(dispatches/structural_conformance_manifest.json; stores gate-and-"
                     "dial gated)"},
    ],
}

#: the two structural stores :mod:`structural_conformance` reads (its ``_ARCH_STORE``
#: / ``_SPINE_STORE``). Their ``stores.<name>.enabled`` dial is the ONLY real dial in
#: the sub-organ band; each row co-displays its holdout gate (the dial-cannot-override-
#: the-gate law, Lane 3 / RISK 2).
_STRUCTURAL_STORES: tuple[str, ...] = ("section_architecture", "spine_chain")

#: EVERY gated retrieval store — the two structural ones ABOVE plus the three
#: stage-retrieval stores (``paragraph_plan``/``derivation_walk``/``figure_caption``).
#: E4b: these three rendered as BARE ungated checkboxes in the global card — a
#: ``stores.<name>.enabled`` toggle carrying no gate, exactly the smuggle
#: ``figure_caption``'s own ``refusal_proof_holds:false`` warns about. Every one of
#: them now co-displays its holdout gate (read through ``stage_retrieval``'s OWN
#: ``_gate_refusal``); the client refuses to arm ``enabled`` on a red gate. The
#: structural two keep rendering (gated) in the structural sub-card, so they are
#: SKIPPED from the global card to avoid a double-render; the other three render
#: gated in the global calibration card.
_GATED_STORES: tuple[str, ...] = (
    "section_architecture", "spine_chain",
    "paragraph_plan", "derivation_walk", "figure_caption",
)


def _store_gate(name: str, root: Path) -> dict:
    """One gated store's holdout-gate verdict, read through :mod:`stage_retrieval`'s
    OWN gate logic (``_read_json`` + ``_gate_refusal`` — NEVER re-derived, RISK 2):
    ``{state, passed, refusal}``. ``passed`` teal when the gate holds, ``absent``/
    ``failed`` warn (never green on a red gate). ``figure_caption``'s
    ``refusal_proof_holds:false`` surfaces here as ``failed`` + the refusal string."""
    from laplace.pipeline import stage_retrieval as _sr
    verdict = _sr._read_json(root / "corpus_stores" / name / "gate_verdict.json")
    refusal = _sr._gate_refusal(verdict)
    passed = refusal is None
    state = "passed" if passed else ("absent" if verdict is None else "failed")
    return {"state": state, "passed": passed, "refusal": refusal or ""}

#: every sub-organ id the ``GET /pipeline/organ`` door serves — derived from the table
#: (no drift: a new sub-organ is reachable the moment it joins ``_SUBORGAN_FOR_STATE``).
_KNOWN_SUBORGANS: frozenset[str] = frozenset(
    sub["id"] for subs in _SUBORGAN_FOR_STATE.values() for sub in subs)


# ---------------------------------------------------------------------------
# dials → per-organ knobs (in place). Reuses dials_surface's schema helpers so the
# kind / enum / provenance the card renders is the SAME the write gate enforces.
# ---------------------------------------------------------------------------

def _flatten(d: dict, prefix: str):
    for k, v in d.items():
        p = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            yield from _flatten(v, p)
        else:
            yield p, v


def _leaf_kind(path: str, val: Any) -> str:
    from laplace.web import dials_surface as _ds
    if _ds._enum_key(path):
        return "enum"
    if isinstance(val, bool):
        return "bool"
    if isinstance(val, (int, float)):
        return "num"
    if isinstance(val, list):
        return "list"
    return "text"


def _dials_by_organ(profile: str, root: Path) -> tuple[dict[str, list[dict]], dict]:
    """Map every dial leaf to its consuming organ (or 'global'). Returns
    ``({organ_id: [knob, ...]}, dials_state)`` where a knob is
    ``{path, value, kind, source, group, enum?[, gate]}`` — the whole editable
    overlay, split so each organ card renders ITS dials in place."""
    from laplace.web import dials_surface as _ds
    state = _ds.dials_state(profile)
    merged = state.get("merged") or {}
    overlay = state.get("overlay") or {}
    defaults = state.get("defaults") or {}
    ops = state.get("ops") or []
    struct_paths = {f"stores.{s}.enabled" for s in _STRUCTURAL_STORES}
    gate_paths = {f"stores.{s}.enabled": s for s in _GATED_STORES}
    # HIS COMMISSION (9a) — the per-dial ledger history, one act deep: the friction
    # rows that touched THIS leaf (set-leaf / reset-leaf), newest last, so the card
    # can show what it does + current-vs-default AND who moved it, when, to what.
    hist_by_path: dict[str, list[dict]] = {}
    for o in ops:
        p = o.get("path")
        if not isinstance(p, str):
            continue
        hist_by_path.setdefault(p, []).append(
            {"ts": o.get("ts"), "by": o.get("by"), "kind": o.get("kind"),
             **({"value": o.get("value")} if "value" in o else {})})
    by_organ: dict[str, list[dict]] = {}
    for group, gval in merged.items():
        if group == "version" or not isinstance(gval, dict):
            continue
        organ = _DIAL_GROUP_ORGAN.get(group, "global")
        for path, val in _flatten(gval, group):
            # The conjugate wave (Lane 3 / RISK 2): the structural stores render
            # GATED in the structural sub-card (each ``enabled`` toggle paired with its
            # holdout gate); they must NOT ALSO render raw in the global card, where a
            # toggle carries no gate and could arm a red gate into a run-time SystemExit.
            if group == "stores" and path in struct_paths:
                continue
            kind = _leaf_kind(path, val)
            ek = _ds._enum_key(path)
            knob = {
                "path": path, "value": val, "kind": kind, "group": group,
                "source": "overlay" if _ds._get_path(overlay, path)[0] else "default",
            }
            if ek:
                knob["enum"] = sorted(_ds._LEAF_ENUMS[ek])
            # HIS COMMISSION (9a): the worded meaning + stage effect IN PLACE, the
            # code DEFAULT (so current-vs-default reads at a glance), the consuming
            # organ named, and the ledger history one act deep. Where the meaning is
            # not documented in code/docs, ``meaning`` is null and the card says so.
            knob["meaning"] = _dial_meaning(path)
            found_def, def_val = _ds._get_path(defaults, path)
            if found_def:
                knob["default"] = def_val
            knob["consumer"] = organ
            if path in hist_by_path:
                knob["history"] = hist_by_path[path]
            # E4b GATES-HONEST: a stage-retrieval store toggle (paragraph_plan /
            # derivation_walk / figure_caption) is no longer a BARE checkbox — it
            # co-displays its holdout gate so the client refuses to arm ``enabled`` on
            # a red gate (figure_caption's refusal_proof_holds:false surfaces here) and
            # the chip never reads green on a failed gate. The mjs dialRow renders
            # ``k.gate`` (chip + arm-refusal) exactly as the structural sub-card does.
            if group == "stores" and path in gate_paths:
                knob["store"] = gate_paths[path]
                knob["gate"] = _store_gate(gate_paths[path], root)
            by_organ.setdefault(organ, []).append(knob)
    return by_organ, state


# ---------------------------------------------------------------------------
# the release-state ladder (which passed / current / ahead) — from the mechanism
# ---------------------------------------------------------------------------

def _ladder_index(current: str) -> int:
    order = {s: i for i, s in enumerate(_release.STATES)}
    if current in order:
        return order[current]
    if current == _release.REOPENED:
        # a reopened release resumes at UNDER_CONVERGENCE (release._REOPEN_RESUME).
        return order.get("UNDER_CONVERGENCE", 0)
    return -1  # NEVER_RUN — nothing has passed


def _status_for(state: str, current: str, ci: int) -> str:
    si = _release.STATES.index(state)
    if current == _release.REOPENED and si <= ci:
        return "reopened" if si == ci else "passed"
    if si < ci:
        return "passed"
    if si == ci:
        return "current"
    return "ahead"


def _defacto_index(verdict: dict) -> int:
    """FINDING 1 — the de-facto rung for a project the release MACHINE never drove but
    HEREDITY shows real history (rounds / generations / a minted artefact). The raw
    ``current_state`` is ``NEVER_RUN`` ⇒ ``_ladder_index`` = -1 ⇒ every rung reads
    'ahead' (ten identical next moves, contradicting a GEN-3/r2-minted body). Derive
    the de-facto rung from the verdict itself, never guessed:

      * a minted artefact (a revision-tagged release bundle on disk) completed the
        ladder for that mint ⇒ RELEASED (the terminal rung);
      * scored generations or banked rounds without a mint sit at UNDER_CONVERGENCE
        (where banked rounds live);
      * no history ⇒ -1 (no de-facto; a cold scaffold stays plainly pre-ladder).

    So exactly ONE rung reads current and the rungs behind it read passed."""
    art = verdict.get("artefact") or {}
    gens = verdict.get("generations") or {}
    rounds = (verdict.get("rounds") or {}).get("n") or 0
    # a mint is real only when the bytes are (or were) there — minted_at is the release
    # record's own timestamp; exists is False only for a recorded-but-gone artefact,
    # which still means the ladder was climbed once.
    minted = bool(art.get("minted_at"))
    if minted:
        return _release.STATES.index("RELEASED")
    if gens.get("present") or rounds:
        return _release.STATES.index("UNDER_CONVERGENCE")
    return -1


def _ladder_banner(position: str | None, verdict: dict) -> str:
    """FINDING 1 — the explicit worded banner a heredity-tracked ladder carries: the
    release machine was never driven here, so the position is tracked by HEREDITY, not
    the machine. Composed from the truth-layer position (the SAME words the header +
    dashboard render) so one truth reads on one page."""
    pos = (position or "").strip()
    tail = (" — position tracked by heredity: " + pos) if pos else ""
    return "the release machine has not been driven here" + tail


# ---------------------------------------------------------------------------
# release evidence — the release/finalize/bundle records the terminal organs bank
# ---------------------------------------------------------------------------

def _release_evidence(ctx) -> dict:
    """The terminal organs' banked evidence, honest-empty when absent: the finalize
    record, the release bundles, and the current artefact fact — all bounded refs."""
    out: dict[str, Any] = {"finalize": None, "bundles": [], "artefact": None}
    if ctx is None:
        return out
    rel = ctx.release_dir
    if rel is not None and rel.is_dir():
        fin = rel / "finalize.json"
        if fin.is_file():
            try:
                d = json.loads(fin.read_text(encoding="utf-8"))
                out["finalize"] = {"slug": d.get("slug"), "title": d.get("title"),
                                   "revision": d.get("revision"), "pdf_path": d.get("pdf_path"),
                                   "created": d.get("created")}
            except (OSError, ValueError):
                pass
        out["bundles"] = sorted(p.name for p in rel.glob("bundle_r*.json"))[-6:]
    art = getattr(ctx, "current_artefact", None)
    if isinstance(art, dict) and (art.get("pdf") or art.get("tex")):
        out["artefact"] = {"pdf": art.get("pdf"), "version_id": art.get("version_id"),
                           "kind": art.get("kind")}
    return out


#: what each terminal stage's OWN evidence object fills (P7: an empty state names its
#: filler; a stale read names its rebuild). Keyed by organ id — the five back-half
#: cards no longer share ONE ``_release_evidence`` blob (E4b): each names the distinct
#: record IT banks, so a chair reading the release stage never sees the review stage's
#: story painted onto it.
_STAGE_FILLS: dict[str, str] = {
    "review":      "the AUTHOR_REVIEWED gate banks a Fork-7 version snapshot of the "
                   "reviewed source (release.transition → bank_snapshot)",
    "final_build": "the finalize compile banks a named, metadata-stamped PDF "
                   "(release.finalize → release/finalize.json)",
    "final_gates": "the figure-layout review gates run over the finalised PDF "
                   "(final_layer / layout_gates over the minted build)",
    "accept":      "the author's acceptance binds the reviewed bundle "
                   "(release.transition AUTHOR_ACCEPTED, bundle-bound)",
    "release":     "the pinned release bundle — byte-addressable, GERARD'S LAW "
                   "(release/bundle_r*.json + the minted artefact)",
}


def _stage_evidence(oid: str, rel_ev: dict, ctx) -> dict:
    """The DISTINCT evidence object one terminal organ renders (E4b: five distinct
    objects, never one shared blob). Each slices ``rel_ev`` (the pure-read release
    records) to exactly what THAT stage banks, carries a ``kind`` so the card can tell
    them apart, and a P7 ``fills`` line naming what an empty stage waits on. Every
    slice is honest-empty when the machine has not reached the stage — no fabricated
    record, the ``fills`` line names the producer."""
    fin = rel_ev.get("finalize")
    bundles = rel_ev.get("bundles") or []
    art = rel_ev.get("artefact")
    fills = _STAGE_FILLS.get(oid, "")
    if oid == "review":
        # the Fork-7 review snapshots (versions labelled at the AUTHOR_REVIEWED gate).
        snaps: list[str] = []
        vd = getattr(ctx, "versions_dir", None) if ctx is not None else None
        if vd is not None and vd.is_dir():
            snaps = sorted(p.name for p in vd.glob("*AUTHOR_REVIEWED*"))[-6:]
        return {"kind": "review", "snapshots": snaps,
                "present": bool(snaps), "fills": fills}
    if oid == "final_build":
        return {"kind": "final_build", "finalize": fin,
                "present": bool(fin), "fills": fills}
    if oid == "final_gates":
        # the layout-gate verdicts over the finalised PDF live beside the finalize
        # record; honest-empty (present:false) until the final build has run.
        return {"kind": "final_gates", "finalize_slug": (fin or {}).get("slug"),
                "present": bool(fin), "fills": fills}
    if oid == "accept":
        # acceptance binds the reviewed bundle — the newest bundle IS the accept
        # subject; honest-empty until a bundle is bound.
        return {"kind": "accept", "bundle": (bundles[-1] if bundles else None),
                "present": bool(bundles), "fills": fills}
    # release — the pinned bundles + the byte-addressable artefact.
    return {"kind": "release", "bundles": bundles, "artefact": art,
            "present": bool(bundles or art), "fills": fills}


# ---------------------------------------------------------------------------
# The sub-organ readers (view=mechanism) — every card calls the organ's OWN
# reader; this module never re-parses an artifact (RISK 1). Each reader is a PURE
# read (no subprocess/compile/embed/network) so it is lawful on the GET path.
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict | None:
    """A boom-guarded JSON load — ``None`` on a missing/unreadable/non-dict file, so
    no GET path booms on a corrupt artifact (WIRING LAW 2)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError, TypeError):
        return None


def _manuscript_dir(ctx) -> Path | None:
    md = getattr(ctx, "manuscript_dir", None) if ctx is not None else None
    return Path(md) if md else None


def _proxy_payload(root: Path, *, full: bool) -> dict:
    """The proxy loop's telemetry, read through the organ's OWN readers
    (``author_proxy.load_verdicts`` for the banked verdicts,
    ``fork_adjudicator.enumerate_parked_forks`` for the parked residue — both pure).
    ``full`` adds the parked-fork handles (bounded to 20) + the GET dry-run door; the
    LIGHT shape (chain summary) carries counts only, so the board stays bounded (§4).

    SCOPE: every count here is ROOT-scoped — the proxy loop adjudicates the engine's
    ONE corpus_friction fork channel, not this project's forks. The card sits under a
    project's converge state for placement, so the payload carries ``scope`` explicitly
    and the card labels it ``engine-global (not <project>)`` — the counts are the same
    on every project (a chair-visible fact, not a per-project adjudication)."""
    from laplace.engine import author_proxy
    rows = author_proxy.load_verdicts(root)
    verdicts = [v for v in rows if v.get("kind") != "contest"]
    contested = sum(1 for v in rows if v.get("kind") == "contest")
    genuinely_his = sum(1 for v in verdicts
                        if str(v.get("confidence") or "").upper().startswith("GENUINELY"))
    out: dict[str, Any] = {
        "present": bool(verdicts),
        "scope": "engine-global",
        "adjudicated": len(verdicts),
        "genuinely_his": genuinely_his,
        "contested": contested,
    }
    if full:
        from laplace.pipeline import fork_adjudicator
        parked = fork_adjudicator.enumerate_parked_forks(root)
        out["parked"] = len(parked)
        out["forks"] = [{"key": f.key, "source": f.source, "node": f.node}
                        for f in parked[:20]]
        out["desk_door"] = "/desk/act (class proxy-drafts — the live bank is supervised, desk-only)"
        out["dry_run_door"] = "/pipeline/organ?organ=proxy&dryrun=1 (fork_adjudicator.drive dry-run frames — zero tree writes)"
    return out


def _growth_payload(project: str, root: Path) -> dict:
    """The growth-steering telemetry: the gap DISCOVERY census from the newest
    detector round (via ``detector_organs.read_detector_organs`` — view=mechanism),
    with closure named as the cross-round join (``gap_ledger.closure_metric`` over the
    trajectory, surfaced on ``/analytics/loop``). One banked round shows discovery
    only; closure needs two."""
    from laplace.engine import detector_organs as det
    census = det.read_detector_organs(project, root)
    gaps = census.get("gaps") or {}
    return {
        "present": bool(census.get("present")),
        "date": census.get("date", ""),
        "discovered": gaps.get("gaps", 0),
        "capped": gaps.get("capped", 0),
        "conceptric_intents": gaps.get("conceptric_intents", 0),
        "research_intents": gaps.get("research_intents", 0),
        "spine_critical": gaps.get("spine_critical", 0),
        "substrate_absent": gaps.get("substrate_absent", 0),
        "by_gap_class": gaps.get("by_gap_class") or {},
        "closure": ("closure vs discovery is the cross-round metric "
                    "(gap_ledger.closure_metric); the round-over-round view is on "
                    "/analytics/loop — a single banked round shows discovery only"),
    }


def _figures_dry_run(ctx, root: Path) -> dict:
    """The one permitted LIVE dry-run (RISK 2 / WIRING LAW 2): ``figure_runner.run(
    apply=False, run_gen=False)`` — computes promises/matches with NO generator
    subprocess and NO tree mutation (proven non-mutating). The generator script is
    read from the banked manifest's ``generator_script``; absent that, honest-empty."""
    md = _manuscript_dir(ctx)
    from laplace.pipeline import figure_runner as fr
    manifest = _read_json((md / "figure_manifest.json")) if md else None
    script = (manifest or {}).get("generator_script") or ""
    if not md or not script:
        return {"present": False,
                "note": "no banked manifest names a generator script — fire "
                        "figure-materialize (banks a work-order) to establish one"}
    spath = Path(script)
    if not spath.is_absolute():
        spath = root / script
    if not spath.is_file():
        return {"present": False,
                "note": f"generator script {script!r} not on disk — cannot preview"}
    prev = fr.run(md, spath, apply=False, run_gen=False)
    return {
        "present": True,
        "live_dry_run": True,
        "matched_count": prev.get("matched_count", 0),
        "unmatched_count": prev.get("unmatched_count", 0),
        "placed": [{"promise": p.get("promise"), "generator": p.get("generator"),
                    "matched": p.get("matched"), "placed_at": p.get("placed_at"),
                    "label": p.get("label")} for p in (prev.get("placed") or [])],
        "note": "live preview (apply=False, run_gen=False) — computes promises/matches, "
                "mutates nothing; a full materialize runs the generators (banks a WO)",
    }


def read_organ(organ: str, project: str, ctx, root: Path,
               *, dryrun: bool = False) -> dict | None:
    """The FULL reader payload one sub-organ card renders — dispatched by ``organ``
    id to the organ's OWN lawful reader (view=mechanism). Pure read. ``None`` for an
    unknown organ id (the handler 404s). ``organ=proxy`` + ``dryrun`` returns the
    ``fork_adjudicator.drive`` dry-run frames (zero tree writes); ``organ=figures`` +
    ``dryrun`` returns the one permitted live figure dry-run."""
    md = _manuscript_dir(ctx)
    if organ == "detectors":
        from laplace.engine import detector_organs as det
        return det.read_detector_organs(project, root)
    if organ == "evolution":
        from laplace.pipeline import evolution_consumer as ec
        payload = ec.read_ratify_queue(md) if md else {"present": False}
        payload = dict(payload)
        payload["doors"] = {
            "ratify": "POST /evolution/ratify {corpus, intent_id, by, armed} — his "
                      "word; fires the transactional apply + retires the intent",
            "hold": "POST /evolution/hold {corpus, intent_id, by, note?} — a typed "
                    "DEFER (valid, not this run)",
            "reject": "POST /evolution/reject {corpus, intent_id, by, reason?} — "
                      "revocation without apply, never a silent drop"}
        return payload
    if organ == "fitness":
        from laplace.pipeline import fitness_panel as fp
        return fp.read_fitness(project, root)
    if organ == "selection":
        # The selection face — the sheet the author rules against (view=mechanism:
        # selection_sheet's OWN reader, pure). The doors block names the selection
        # desk's routes (its own /selection/*, NOT a run-launch fire) — the
        # evolution-desk idiom exactly (a read plus its lawful doors).
        from laplace.pipeline import selection_sheet as ss
        payload = dict(ss.read_selection(project, root))
        # The queued next act (view=mechanism): an unclean R10 self-consistency finding
        # names a structural move via the reader's OWN MISMATCH_TABLE (contribution →
        # RESPINE, order → REORDER, …) — joined here so the sheet shows not just the
        # ruling but what it hands the release machine next. Never re-derives the map.
        try:
            from laplace.pipeline.readers import restart_reader as _rr
            for g in payload.get("generations") or []:
                r10 = g.get("r10")
                if not (isinstance(r10, dict) and r10.get("clean") is False):
                    continue
                intents = []
                for mk in (r10.get("mismatch_kinds") or []):
                    rule = _rr.MISMATCH_TABLE.get(mk)
                    if rule:
                        intents.append({"mismatch": mk, "verb": rule.verb})
                if intents:
                    r10["restart_intents"] = intents
        except Exception:  # noqa: BLE001 — the join is a bonus; never break the read
            pass
        payload["doors"] = {
            "sheet": "GET /selection/sheet?corpus= — the sheet he rules against "
                     "(pure read; every reading a banked dated ref)",
            "rule": "POST /selection/rule {corpus, generation_id, verdict∈"
                    "{promote,hold,retire}, by, armed} — his word on ONE generation "
                    "(record-only; unarmed returns the draft it would override + the "
                    "readings digest, armed banks the ruling; a ruled generation is "
                    "contested by a later record, never re-ruled)"}
        return payload
    if organ == "derivation":
        # The derivation face — the aspiration + chain + reach, joined (view=mechanism:
        # derivation_organ.read_sheet over derivation_organ's OWN readers, pure). The
        # doors block rides inside read_sheet's payload (its own /derivation/*), the
        # selection/evolution-desk idiom exactly (a read plus its lawful doors).
        from laplace.pipeline import derivation_organ
        return derivation_organ.read_sheet(md) if md else {"present": False}
    if organ == "bibliography":
        from laplace.pipeline import bibliography_stage as bib
        return bib.read_manifest(md) if md else {"present": False}
    if organ == "citation-direction":
        from laplace.pipeline import citation_direction as cd
        return cd.read_run_record(md) if md else {"present": False}
    if organ == "structural-conformance":
        from laplace.pipeline import structural_conformance as sc
        payload = sc.read_manifest(md) if md else {"present": False}
        payload = dict(payload)
        payload["store_gates"] = _structural_store_dials(_dials_state_for(), root)
        return payload
    if organ == "figures":
        if dryrun:
            return _figures_dry_run(ctx, root)
        from laplace.pipeline import figure_runner as fr
        return fr.read_manifest(md) if md else {"present": False}
    if organ == "proxy":
        if dryrun:
            from laplace.pipeline import fork_adjudicator
            import tempfile
            # drive() writes its manifest to a scratch dir ONLY (mkdtemp / here a
            # self-cleaning tempdir) — zero tree writes, verified; non-structural
            # question ⇒ no embed. A pure GET-lawful dry-run.
            with tempfile.TemporaryDirectory(prefix="pipeline-proxy-dry-") as td:
                res = fork_adjudicator.drive(root, mode="dry-run", scratch_dir=td)
            return {"present": True, "mode": res.get("mode"),
                    "parked": res.get("parked", 0), "forks": res.get("forks", [])}
        return _proxy_payload(root, full=True)
    if organ == "growth":
        return _growth_payload(project, root)
    return None


def _dials_state_for(profile: str = _DEFAULT_PROFILE) -> dict:
    from laplace.web import dials_surface as _ds
    return _ds.dials_state(profile)


def _structural_store_dials(dials_state: dict, root: Path) -> list[dict]:
    """The structural sub-organ's store rows — each ``stores.<name>.enabled`` dial
    PAIRED with its holdout gate, read through :mod:`stage_retrieval`'s OWN gate logic
    (``_read_json`` + ``_gate_refusal`` — NEVER re-derived, RISK 2). A row carries the
    dial value + source (for the one ``/dials/op`` write path) AND a ``gate`` verdict
    (``passed`` teal / ``absent``|``failed`` warn, never green on a red gate); the
    client refuses to arm ``enabled`` on a red gate and surfaces ``gate.refusal``
    inline instead of POSTing a config that ``SystemExit``s at run."""
    from laplace.web import dials_surface as _ds
    merged = dials_state.get("merged") or {}
    overlay = dials_state.get("overlay") or {}
    stores_val = merged.get("stores") or {}
    rows: list[dict] = []
    for name in _STRUCTURAL_STORES:
        path = f"stores.{name}.enabled"
        enabled = bool((stores_val.get(name) or {}).get("enabled"))
        source = "overlay" if _ds._get_path(overlay, path)[0] else "default"
        rows.append({
            "path": path, "value": enabled, "kind": "bool", "group": "stores",
            "source": source, "store": name,
            "meaning": _dial_meaning(path), "default": bool(
                (((_defaults_for().get("stores") or {}).get(name)) or {}).get("enabled")),
            "consumer": "structural-conformance",
            "gate": _store_gate(name, root),
        })
    return rows


def _defaults_for() -> dict:
    from laplace.pipeline import dials as _dm
    return _dm.defaults()


def _control_for_action(action: str, roster: dict) -> dict | None:
    """The scoped-control shape for one ``fire_action``, from
    ``storyboard.launch_roster`` (the mechanism) — ``{action, cost_class, arm_to_fire,
    what[, banks]}``. ``None`` when the action is not in the roster (a mis-wired
    fire_action fails visibly, never a dead button)."""
    for a in roster.get("local_safe", []):
        if a["action"] == action:
            return {"action": action, "cost_class": "local-safe",
                    "arm_to_fire": bool(a.get("arm_to_fire")), "what": a.get("what", "")}
    for a in roster.get("model_heavy", []):
        if a["action"] == action:
            return {"action": action, "cost_class": "model-heavy", "banks": "work-order",
                    "arm_to_fire": True, "what": a.get("what", "")}
    return None


def _structural_staleness(stores_fed: list[str],
                          would_feed: set[str]) -> tuple[bool, str]:
    """Reconcile the BANKED manifest's fed-stores against what the LIVE store dials
    would feed NOW (a store feeds iff its ``enabled`` dial is on AND its holdout gate
    passes). The banked structural manifest may have been produced under a PRIOR dial
    state; when the set that fed it no longer matches the set a refire would feed, a
    green ``patched`` verdict claims a capability the current config has disabled —
    mark it STALE and name the truth (a refire under the live dials changes it). This
    is the one place the reconcile is derived, so the card reads it, never re-derives."""
    fed = set(stores_fed)
    if fed == would_feed:
        return False, ""
    now = (", ".join(sorted(would_feed)) + " now feed") if would_feed \
        else "both stores now off"
    if fed and not would_feed:
        return True, (f"patched under a prior dial state ({', '.join(sorted(fed))} fed) "
                      f"— {now}; refire yields empty-patch")
    if would_feed and not fed:
        return True, (f"empty-patch banked with the stores off — {now}; refire would "
                      f"query them")
    return True, (f"banked with {', '.join(sorted(fed))} fed; {now} — refire changes "
                  f"the verdict")


def _suborgan_summary(reader: str, project: str, ctx, root: Path,
                      dials_state: dict | None = None) -> dict:
    """The LIGHT chain-summary for one sub-organ — bounded SCALAR facts only (present
    + headline counts), never the per-detector / per-intent / per-store bodies (those
    lazy-fetch through the reader_door, §4). Every count is real banked telemetry read
    through the organ's own reader. The structural summary ADDITIONALLY reconciles the
    banked verdict against the live store dials (``dials_state``) so a stale ``patched``
    green is caught here, at the reader, not painted green by the card."""
    md = _manuscript_dir(ctx)
    if reader == "detectors":
        from laplace.engine import detector_organs as det
        c = det.read_detector_organs(project, root)
        return {"present": bool(c.get("present")), "date": c.get("date", ""),
                "gaps": (c.get("gaps") or {}).get("gaps", 0),
                "meta_leak": (c.get("meta_leak") or {}).get("n", 0),
                "source_delta": (c.get("source_delta") or {}).get("n", 0),
                "promise": (c.get("promise") or {}).get("n", 0)}
    if reader == "bibliography":
        from laplace.pipeline import bibliography_stage as bib
        b = bib.read_manifest(md) if md else {"present": False}
        return {"present": bool(b.get("present")), "dangling": b.get("dangling_n", 0),
                "resolved": b.get("resolved_n", 0), "cited": b.get("cited_n", 0),
                "renders": b.get("renders")}
    if reader == "citation_direction":
        from laplace.pipeline import citation_direction as cd
        c = cd.read_run_record(md) if md else {"present": False}
        return {"present": bool(c.get("present")), "intents": c.get("intents_n", 0),
                "needs_judge": (c.get("buckets") or {}).get("needs-judge", 0),
                "admitted": c.get("admitted", 0),
                "manifests_pending": c.get("manifests_pending", 0)}
    if reader == "structural":
        from laplace.pipeline import structural_conformance as sc
        s = sc.read_manifest(md) if md else {"present": False}
        stores_fed = s.get("stores_fed", [])
        # RECONCILE the banked verdict against the LIVE store dials (a store feeds iff
        # enabled AND its gate passes): a 'patched' banked under a prior dial state,
        # with the stores now off, is a STALE green — surface it so the card reads warn.
        would_feed = {r["store"]
                      for r in _structural_store_dials(dials_state or {}, root)
                      if r["value"] and r["gate"]["passed"]}
        stale, reconcile = (_structural_staleness(stores_fed, would_feed)
                            if s.get("present") else (False, ""))
        return {"present": bool(s.get("present")), "patch_count": s.get("patch_count", 0),
                "verdict": s.get("verdict", "absent"),
                "conformant": s.get("conformant", 0), "unscored": s.get("unscored", 0),
                "stores_fed": stores_fed,
                "stale": stale, "reconcile": reconcile}
    if reader == "figures":
        from laplace.pipeline import figure_runner as fr
        f = fr.read_manifest(md) if md else {"present": False}
        return {"present": bool(f.get("present")), "placed": f.get("figures_placed", 0),
                "total": f.get("promises_total", 0), "absent": f.get("promises_absent", 0),
                "intents": f.get("intents_banked", 0)}
    if reader == "proxy":
        return _proxy_payload(root, full=False)
    if reader == "evolution":
        from laplace.pipeline import evolution_consumer as ec
        q = ec.read_ratify_queue(md) if md else {"present": False}
        c = q.get("counts") or {}
        return {"present": bool(q.get("present")), "open": c.get("open", 0),
                "held": c.get("held", 0), "applied": c.get("applied", 0),
                "rejected": c.get("rejected", 0)}
    if reader == "fitness":
        from laplace.pipeline import fitness_panel as fp
        f = fp.read_fitness(project, root)
        traj = f.get("debt_trajectory") or []
        return {"present": bool(f.get("present")),
                "debt": (traj[-1].get("n") if traj else None),
                "freeze_pass": (f.get("freeze") or {}).get("pass"),
                "mech_derivative": (f.get("mechround") or {}).get("derivative"),
                "named_red": (f.get("suite_baseline") or {}).get("named_red")}
    if reader == "selection":
        # LIGHT scalars only (the chain stays bounded): the generation count, the
        # newest row's DRAFT verdict, and how many still await his word. Tolerant —
        # a broken sheet degrades to honest-absent, never a raise on the GET path.
        from laplace.pipeline import selection_sheet as ss
        try:
            s = ss.read_selection(project, root)
        except Exception:  # noqa: BLE001 — a broken sheet never breaks the paint
            s = {"present": False}
        gens = s.get("generations") or []
        newest = gens[0] if gens else {}          # read_selection sorts newest-first
        latest = (newest.get("draft_verdict") or {}).get("verdict") if gens else None
        return {"present": bool(s.get("present")),
                "generations_n": (s.get("counts") or {}).get("generations", len(gens)),
                "newest_n": newest.get("n"),
                "debt_before": newest.get("debt_before"),
                "debt_after": newest.get("debt_after"),
                "latest_draft_verdict": latest,
                "awaiting_ruling_n": s.get("awaiting_ruling_n", 0)}
    if reader == "derivation":
        # LIGHT scalars only (the chain stays bounded): the reach headline the
        # draft-psi-v2 gate reads — how far UP the aspiration the attested isnad got.
        # Tolerant — an absent/broken aspiration degrades to honest-absent, never a
        # raise on the GET path.
        from laplace.pipeline import derivation_organ as do
        try:
            r = do.reach(md) if md else {}
        except Exception:  # noqa: BLE001 — a broken chain never breaks the paint
            r = {}
        return {"present": bool(r.get("present")),
                "aspiration_present": r.get("aspiration_present", False),
                "links_attested": r.get("links_attested", 0),
                "links_total": r.get("links_total", 0),
                "depth_attested": r.get("depth_attested", 0),
                "frontier_n": len(r.get("frontier_gap") or [])}
    if reader == "growth":
        g = _growth_payload(project, root)
        return {"present": bool(g.get("present")), "discovered": g.get("discovered", 0),
                "research_intents": g.get("research_intents", 0),
                "substrate_absent": g.get("substrate_absent", 0)}
    return {"present": False}


def _suborgans_for_state(state: str, project: str, ctx, root: Path,
                         dials_state: dict, roster: dict) -> list[dict]:
    """The LIGHT sub-organ band for one release state — one entry per night-organ the
    state consumes (``_SUBORGAN_FOR_STATE``), each ``{id,label,blurb,producer,
    reader_door,fire_action,dials,summary}``. Heavy telemetry lazy-joins through
    ``reader_door``; only the structural organ carries dials in place (the store
    kill-switches + their gates)."""
    out: list[dict] = []
    for sub in _SUBORGAN_FOR_STATE.get(state, []):
        action = sub.get("fire_action")
        control = _control_for_action(action, roster) if action else None
        dials = (_structural_store_dials(dials_state, root)
                 if sub["id"] == "structural-conformance" else [])
        entry = {
            "id": sub["id"], "label": sub["label"], "blurb": sub["blurb"],
            "producer": sub["producer"],
            "reader_door": f"/pipeline/organ?project={project}&organ={sub['id']}",
            "fire_action": action,
            "controls": [control] if control else [],
            "dials": dials,
            "summary": _suborgan_summary(sub["reader"], project, ctx, root, dials_state),
        }
        # Lane 4 — figures is the one organ whose dry-run zone renders a TRUE live
        # preview (RISK 2 / WIRING LAW 2: run(apply=False, run_gen=False), proven
        # non-mutating). Name the door so the card's dry-run zone fetches it live
        # instead of the generic dial-settings preview.
        if sub["id"] == "figures":
            entry["live_dry_run_door"] = (
                f"/pipeline/organ?project={project}&organ=figures&dryrun=1")
        out.append(entry)
    return out


# ---------------------------------------------------------------------------
# The fire made legible (r2 stranger-walk fix, evidence/r2_paces_2026-07-23) — when the
# machine's next act is a reproject, the author fires it HIMSELF, and the "open the gen-4
# reprojection" door lands on the staged organ card (B1). The walk found the control it
# lands on is a generic 're-projection · banks' button with no gen tag, the named brief a
# non-clickable unreachable span, and the cost never more specific than 'model-heavy'.
# These two helpers compose the one reproject-fire dict that BOTH the staged card's control
# (chain) and the brief's consequential door (pipeline_brief) ride, so the two surfaces
# speak identically: greeting by the generation name, the cost in plain words, the brief a
# REAL door.
# ---------------------------------------------------------------------------

#: the model-heavy reproject cost in plain words — the TRUTH of ``storyboard.run_launch``'s
#: ``_MODEL_HEAVY`` path (it banks EXACTLY ONE ``kind=work-order`` record and spawns
#: nothing; "the server spends no tokens; a worker session runs with it"). No invented
#: numbers — only what the code actually does; the "shepherded session" is that pickup run.
_REPROJECT_COST_PLAIN = ("model-heavy — banks a work order now, runs nothing; "
                         "a shepherded session runs it")


def _brief_door(md: Path | None, brief: str | None) -> dict | None:
    """The generation brief made a REAL door — resolve the manuscript-relative brief path
    (e.g. ``reprojection/gen4_brief.md``) into a path-fenced ``GET /project/doc`` link + label.

    The general door lands (his ruling RW-20260723-154721-984120: "I can't read the
    brief... it's a shame the read the brief doesn't hook in. I'm also worried that this
    option has been made bespoke rather than a mechanical consequence") — the old
    ``file://`` deep-link was dead from an http page in every browser and WAS the bespoke
    one-off he named. ``scanner.py`` now serves a read-only, path-fenced manuscript-doc
    route (``/project/doc?dir=<repo-relative manuscript dir>&path=<manuscript-relative>``)
    every review-family surface can point at, not just this brief — so the href built here
    is a mechanical consequence of that ONE route, never a bespoke construction. The client
    still treats ``brief_door.href`` as opaque, so nothing downstream changes.

    ``None`` when there is no brief, the manuscript dir is unknown, or the path does not
    resolve to a real file UNDER the manuscript dir (truthful absence — the span stays plain,
    never a dead link; the containment fence refuses any ``..`` escape)."""
    if not brief or md is None:
        return None
    raw = str(brief).strip()
    if not raw:
        return None
    path, _, frag = raw.partition("#")
    try:
        base = Path(md).resolve()
        resolved = (base / path).resolve()
        resolved.relative_to(base)          # containment fence — never escape the manuscript dir
    except (ValueError, OSError):
        return None
    if not resolved.is_file():
        return None
    from urllib.parse import quote
    try:
        dir_q = base.relative_to(_repo_root().resolve()).as_posix()
    except ValueError:
        dir_q = base.as_posix()             # outside the repo (e.g. a test tmp_path) — absolute fallback
    href = (f"/project/doc?dir={quote(dir_q, safe='')}&path={quote(path, safe='/')}"
            + (("#" + quote(frag, safe="")) if frag else ""))
    return {"href": href, "label": f"the brief ({resolved.name})", "path": raw}


def _reproject_fire(na: dict, md: Path | None) -> dict | None:
    """The reproject fire the author presses HIMSELF, composed so the staged card's
    re-projection control greets him By the generation name (never a bare
    're-projection · banks'). Returns ``{gen_word, fire_label, cost_plain, brief,
    brief_door}`` for a reproject next-act, else ``None`` (scoped strictly to the verb,
    so any other next-act leaves the control untouched). The SAME dict backs the brief's
    consequential door — the two surfaces cannot phrase the fire differently."""
    if not na or na.get("verb") != "reproject":
        return None
    gen_word = na.get("gen_word") or "the next generation"
    brief = na.get("brief")
    return {
        "gen_word": gen_word,
        "fire_label": f"fire the {gen_word} reprojection",
        "cost_plain": _REPROJECT_COST_PLAIN,
        "brief": brief,
        "brief_door": _brief_door(md, brief),
    }


# ---------------------------------------------------------------------------
# the one board read model
# ---------------------------------------------------------------------------

def chain(project: str, profile: str = _DEFAULT_PROFILE,
          repo_root: Path | None = None) -> dict | None:
    """THE board read model for ``project`` — the whole chain from the mechanism.
    ``None`` for an unknown / path-shaped project (the registry fence).

    Every field is derived, none drawn: the ``states`` ladder is ``release.STATES``
    marked against the live ``current_state``; each ``organ`` names its owning state,
    its evidence, its dials-in-place (mapped from the profile by group), and its
    scoped controls (from ``storyboard.launch_roster``); ``run`` is the pure-read run
    panel; the regrade-health + full run-tray reads are NAMED for lazy fetch, so the
    board's first paint stays bounded."""
    proj = registry.resolve(project)
    if proj is None:
        return None
    root = (repo_root or _repo_root()).resolve()
    ctx = registry.project_context(project, root)

    # the run panel (pure file reads) gives the live release state + phase + rounds.
    # Read TARGET-FIRST then manuscript (the two-root repair): the release machine writes
    # <target>/release/, so run_panel must derive over whichever base actually holds the
    # run — the SAME order registry.project_states reads, else a target-rooted project
    # (subset-sum: rounds under whitepaper/) reads a false NEVER_RUN.
    from laplace.manuscript import storyboard as _sb
    base = None
    for cand in ((ctx.target_dir if ctx else None), (ctx.manuscript_dir if ctx else None)):
        if cand is not None and (cand / "release" / "state.json").is_file():
            base = cand
            break
    if base is None:
        base = (ctx.manuscript_dir if ctx else None) or (ctx.target_dir if ctx else None)
    run = _sb.run_panel(base, root) if (base is not None and base.is_dir()) else None
    current = (run or {}).get("release_state") or "NEVER_RUN"
    never_run = (run is None) or bool(run.get("never_run")) or current == "NEVER_RUN"
    ci = _ladder_index(current)

    # The truth-layer join (one truth on one page): the truthful position + the heredity
    # verdict, read ONCE here (project_state owns it; the SAME words the dashboard card +
    # the L1 pill render). Guarded — a verdict hiccup leaves the ladder on current_state.
    verdict: dict = {}
    position = None
    try:
        from laplace.pipeline import project_state as _ps
        verdict = _ps.project_verdict(root, proj.name) or {}
        position = verdict.get("position")
    except Exception:  # noqa: BLE001 — the ladder still paints from current_state
        verdict, position = {}, None

    # FINDING 1 — when the machine was never driven but heredity shows real history,
    # mark the DE-FACTO rung (from the verdict) so EXACTLY ONE rung reads current and
    # the ladder carries an explicit worded banner naming the heredity-tracked position.
    # A cold scaffold (no history) keeps the truthful all-'ahead' pre-ladder reading.
    ladder_banner = None
    if never_run:
        dfi = _defacto_index(verdict)
        if dfi >= 0:
            ci = dfi
            ladder_banner = _ladder_banner(position, verdict)

    states = [{"state": s, "status": _status_for(s, current, ci),
               "index": _release.STATES.index(s),
               "next_action": registry._NEXT_ACTION.get(s)}
              for s in _release.STATES]

    dials_by_organ, dials_state = _dials_by_organ(profile, root)

    # the scoped launch controls, from the mechanism, bucketed by organ.
    roster = _sb.launch_roster()
    ctrl_by_organ: dict[str, list[dict]] = {}
    for a in roster.get("local_safe", []):
        organ = _ACTION_ORGAN.get(a["action"], "global")
        ctrl_by_organ.setdefault(organ, []).append(
            {"action": a["action"], "cost_class": "local-safe",
             "arm_to_fire": bool(a.get("arm_to_fire")), "what": a.get("what", "")})
    for a in roster.get("model_heavy", []):
        organ = _ACTION_ORGAN.get(a["action"], "global")
        ctrl_by_organ.setdefault(organ, []).append(
            {"action": a["action"], "cost_class": "model-heavy",
             "banks": "work-order", "arm_to_fire": True, "what": a.get("what", "")})

    # The fire made legible (r2 stranger-walk fix): when the machine's next act is a
    # reproject, the author fires it HIMSELF on the staged card (where "open the gen-4
    # reprojection" lands, B1). Thread the one reproject-fire dict onto that card's
    # re-projection control so it greets him by the generation name, names the cost in
    # plain words, and carries the brief as a REAL door — the SAME dict the consequential
    # door rides (they speak identically). Scoped to the verb: no reproject ⇒ no change.
    reproject = _reproject_fire(verdict.get("next_act") or {}, _manuscript_dir(ctx))
    if reproject:
        owner = _ACTION_ORGAN.get("re-projection", "global")
        for _c in ctrl_by_organ.get(owner, []):
            if _c.get("action") == "re-projection":
                _c["reproject"] = reproject
                break

    rel_ev = _release_evidence(ctx)
    has_plan = ctx is not None and ctx.plan_path is not None and ctx.plan_path.is_file()

    organs: list[dict] = []
    for s in _release.STATES:
        oid, label, blurb = _ORGAN_FOR_STATE[s]
        status = _status_for(s, current, ci)
        organ = {
            "id": oid, "state": s, "label": label, "blurb": blurb, "status": status,
            "dials": dials_by_organ.get(oid, []),
            "controls": ctrl_by_organ.get(oid, []),
        }
        # The conjugate wave: the night-organs the state consumes, as LIGHT sub-cards
        # (heavy telemetry lazy-joins through each entry's reader_door). Attached only
        # where the state has sub-organs, so states with none stay lean (§4).
        sub_organs = _suborgans_for_state(s, proj.name, ctx, root, dials_state, roster)
        if sub_organs:
            organ["sub_organs"] = sub_organs
        if oid == "converge":
            # the live run panel is the converge organ's evidence + the run-tray join
            # (the full tray — work orders + launch doors — lazy-fetches /storyboard/run*).
            organ["producer"] = "/storyboard/run → storyboard.run_panel (live round state from the run's own artifacts)"
            # F3 (audit §A5): the lock roster is tier-aware — surface the carve-out so
            # the loop→converge mapping is no longer uniform-and-silent about it.
            organ["lock_carveout"] = _LOCK_CARVEOUT
            organ["run_tray"] = has_plan          # the client mounts the shared run-tray here
            if run:
                organ["evidence"] = {
                    "phase": run.get("phase"), "current_round": run.get("current_round"),
                    "rounds_so_far": run.get("rounds_so_far"),
                    "open_findings": run.get("open_findings"),
                    "in_flight": run.get("in_flight"),
                    "artifacts": (run.get("artifacts") or [])[:8],
                }
            organ["dry_run"] = "/storyboard/propagate" if has_plan else None
        elif oid == "staged":
            organ["producer"] = "/storyboard/propagate → propagate.propagate (the pure-read worklist) + /storyboard/dispatch"
            organ["dry_run"] = "/storyboard/propagate" if has_plan else None
        elif oid in ("final_build", "final_gates", "accept", "release", "review"):
            organ["producer"] = "release.py — the bundle + finalize records"
            # E4b: five DISTINCT evidence objects, not one shared blob — each terminal
            # organ renders exactly the record IT banks (review snapshot / finalize /
            # gates / accepted bundle / pinned release), P7-honest when absent.
            organ["evidence"] = _stage_evidence(oid, rel_ev, ctx)
        elif oid == "mechanical":
            organ["producer"] = "the mech dials + release.transition MECHANICALLY_VALID"
        else:  # weld, lock
            organ["producer"] = "the release state machine (release.py STATES)"
        organs.append(organ)

    # the 'global' card — the cross-cutting dials + the project-wide heavy action.
    global_card = {
        "id": "global", "label": "global calibration",
        "blurb": "cross-cutting dispatch calibration — no single stage owns it",
        "dials": dials_by_organ.get("global", []),
        "controls": ctrl_by_organ.get("global", []),
        "producer": "/dials/state → dials_surface (roles + prompts — read across every organ)",
    }

    # THE truthful STATE WORD (fix wave, cross-surface truth): ``position`` (joined above
    # from the truth layer) is the header's one word — never bare "never run" beside a
    # GEN-3/r2-minted body. ``ladder_banner`` (FINDING 1) names the heredity-tracked
    # position on a machine-never-driven ladder; None on a driven or cold-scaffold one.

    return {
        "project": proj.name,
        "kind": proj.kind,
        "profile": profile,
        "current_state": current,
        "position": position,
        "ladder_banner": ladder_banner,
        "never_run": never_run,
        "states": states,
        "organs": organs,
        "global": global_card,
        "dials_base_present": bool(dials_state.get("base_present")),
        # the joins the board lazy-fetches (named here so the ⓘ is truthful + the census
        # sees the reuse): the regrade health, the full run tray, the dry-run worklist.
        "joins": {
            "regrade": "/corpus/grade_stats" if has_plan else None,
            "run_tray": "/storyboard/run" if has_plan else None,
            "dry_run": "/storyboard/propagate" if has_plan else None,
            "dials_write": "/dials/op + /dials/undo (the one write path — dials_surface)",
        },
        "info": {
            "chain": "/pipeline/chain → pipeline_surface.chain (the ladder from release.STATES; "
                     "dials mapped to organs by group; view = mechanism, never a drawn diagram)",
        },
    }


# ---------------------------------------------------------------------------
# GET /pipeline/brief — The composed brief (W-PROJECT): the project surface's
# resting altitude joined to the one instrument (engine.mjs).
#
# His ruling (2026-07-22): "I need the full pipeline information so I can understand
# exactly what is happening and see how interventions change it." The /project
# surface's resting DOM is no longer the whole board — it is a composed brief of where
# THIS project's pipeline stands: the release state + growth rung in plain words, the
# last thing that ran and what it produced, the next action with its cost/PSU class,
# and At most one decision. The board (the cockpit strip, the organ panels, the
# generation story) is the summonable inventory, materialised behind one open and
# pinned into the engine's focus geometry.
#
# The lock-step law (mirrors the dashboard's): the brief composes over the EXISTING
# read models — :func:`chain` (the board's own truth) + project_state.project_verdict
# (the generation story / next_act) + the dashboard's banked-order read — never a
# parallel join, so the interface and the self-projection cannot disagree. The chain /
# verdict / organ reads stay one truth; this door forks none of them.
# ---------------------------------------------------------------------------


def _humanize_state(word: str | None) -> str:
    """A raw ALL_CAPS machine token (``UNDER_CONVERGENCE``) reads as prose in a
    sentence; authored plain prose ("pre-release — GEN-3") passes through untouched."""
    w = (word or "").strip()
    import re as _re
    if _re.match(r"^[A-Z][A-Z_]*$", w):
        return w.lower().replace("_", " ")
    return w


def _brief_state_line(ch: dict, verdict: dict, rounds_n: int) -> str:
    """Where the pipeline STANDS, in plain words: the truth-layer POSITION (never the
    bare machine token beside a scored body — a NEVER_RUN release machine past a minted
    r2 reads "pre-release — GEN-3, r2 minted", the SAME reconciled word the ladder + the
    dashboard card render), the growth rung when the project is on the ladder, and the
    banked convergence rounds. Only a genuinely cold scaffold (release never run AND
    nothing scored AND no artefact) degrades to the flat "no run yet" line."""
    g = verdict.get("generations") or {}
    art = verdict.get("artefact") or {}
    cold = (ch.get("never_run") and not g.get("present") and not art.get("name"))
    if cold:
        return "No release run yet — the pipeline has not started for this project."
    pos = _humanize_state(ch.get("position") or ch.get("current_state"))
    frag = "The pipeline stands at " + pos
    growth = verdict.get("growth") or {}
    if growth.get("present") and growth.get("state"):
        frag += ", on the growth ladder at " + _humanize_state(growth.get("state"))
    if rounds_n:
        frag += " — " + str(rounds_n) + " convergence round" + ("" if rounds_n == 1 else "s") + " banked"
    return frag + "."


def _brief_ran_last(verdict: dict) -> str | None:
    """The last thing that RAN and what it PRODUCED — the generation panel's story
    compressed to a sentence (debt trajectory as the first-class series), degrading to
    the minted/present artefact when nothing has been scored yet."""
    g = verdict.get("generations") or {}
    art = verdict.get("artefact") or {}
    if g.get("present") and g.get("gen"):
        frag = "The last run scored " + str(g.get("gen"))
        traj = g.get("debt_trajectory") or []
        if traj:
            frag += ", debt " + "→".join(str(n) for n in traj)
        return frag + "."
    if art.get("name"):
        if art.get("minted_at"):
            return "It last produced the minted release " + str(art["name"]) + " (" + str(art["minted_at"]).split("T")[0] + ")."
        if art.get("exists"):
            return "It carries a built artefact (" + str(art["name"]) + "), no generation scored yet."
    return None


def _next_act_words(na: dict) -> tuple[str, str | None]:
    """The next-act as plain glance-altitude words + the raw brief path peeled to audit
    depth. The reproject next-act reads as a clean sentence naming that a briefing note is
    banked — the raw ``.md`` path never rides the glance/face, only the audit return (where
    the door title already carries it). Any other next-act passes its composed label
    through unchanged."""
    if na.get("verb") == "reproject":
        gen_word = na.get("gen_word") or "the next generation"
        brief = na.get("brief")
        words = f"reproject — {gen_word} is open"
        if brief:
            words += " — a briefing note is banked for it"
        return words, (f"brief: {brief}" if brief else None)
    return na.get("label") or "", None


def _brief_next_line(verdict: dict) -> str | None:
    """The NEXT action from the state machine, with its cost/PSU class visible — the
    what-will-this-do law, at the altitude of a sentence (his P1 amendment). The next-act
    reads as plain words; any raw brief path drops to audit depth (never in the sentence)."""
    na = verdict.get("next_act") or {}
    if not na.get("label"):
        return None
    words, _audit = _next_act_words(na)
    frag = "Next: " + words
    cost = na.get("cost_class")
    psu = na.get("psu")
    if cost or psu:
        tail = " · ".join(x for x in (cost, (psu if psu and psu != "none" else None)) if x)
        if tail:
            frag += " (" + tail + ")"
    return frag + "."


def _brief_consequential(project: str, ch: dict, verdict: dict, ctx=None) -> dict | None:
    """THE single decision or move that matters most now — a queued RESPINE decision
    beats the release machine's next action. Carries its glance + a door into the board
    focus (the owning organ), so the one decision is one click from where it is ruled.

    For a reproject next-act it ALSO carries ``brief_door`` — the SAME real door
    (:func:`_brief_door`) the staged card's fire control names, so the "open the gen-4
    reprojection" move and the fire it lands on both point at one reachable brief (never
    the unreachable non-clickable span the r2 walk hit). ``ctx`` supplies the manuscript
    dir for that resolution; absent, the door is honest-absent (the move still stands)."""
    organs = ch.get("organs") or []
    cur_organ = next((o["id"] for o in organs if o.get("status") == "current"), None)
    if cur_organ is None and organs:
        cur_organ = organs[0]["id"]
    from urllib.parse import quote
    organ_door = ("/project?project=" + quote(project, safe="") + "&organ=" + quote(cur_organ, safe="")) if cur_organ else None
    g = verdict.get("generations") or {}
    respine = g.get("respine_intent")
    if respine:
        # plain outcome words at glance altitude — the drafted intent's raw title
        # (plan-meta vocabulary) stays behind the door it opens.
        return {"kind": "decision", "label": "rule the respine",
                "glance": ("a drafted respine awaits your ratify or revoke — re-weight "
                            "the manuscript to lead on its ranked contribution"),
                "href": respine.get("href") or organ_door,
                "organ": cur_organ, "cost_class": "cheap", "psu": "none"}
    na = verdict.get("next_act") or {}
    if na.get("label"):
        verb = na.get("verb")
        # the door FACE is the verb; the glance the plain-words sentence (shared with the
        # narrative next-line); the raw brief path drops to audit depth (the door's title) —
        # never doubled onto card + door, never a file path on the amber face or the glance.
        glance, audit = _next_act_words(na)
        # the door's OWNING organ (B1): reproject's fire control lives on the organ card
        # _ACTION_ORGAN["re-projection"] names (staged), never wherever the chain
        # currently sits — cur_organ is only the fallback for verbs with no scoped
        # owner, so the door always lands where the fire control actually renders.
        door_organ = _ACTION_ORGAN["re-projection"] if verb == "reproject" else cur_organ
        door_href = (
            "/project?project=" + quote(project, safe="") + "&organ=" + quote(door_organ, safe="")
            if door_organ else None
        )
        if verb == "reproject":
            gen_word = na.get("gen_word") or "the next generation"
            door_label = f"open the {gen_word} reprojection"
        else:
            door_label = na["label"]
        out = {"kind": verb or "run", "label": door_label,
               "glance": glance, "href": na.get("href") or door_href,
               "organ": door_organ,
               "cost_class": na.get("cost_class"), "psu": na.get("psu")}
        if audit:
            out["title"] = audit
        # the brief made a REAL door on the consequential card too (the SAME _brief_door
        # the staged fire control carries) — so the move and its fire point at one
        # reachable brief. Honest-absent when the brief does not resolve to a file.
        if verb == "reproject":
            bd = _brief_door(_manuscript_dir(ctx), na.get("brief"))
            if bd:
                out["brief_door"] = bd
        return out
    return None


def _banked_orders(project: str, root: Path) -> int:
    """The count of OPEN banked work-orders for this project — read through the
    dashboard's ONE order reader (never a parallel scan of the store)."""
    try:
        from laplace.web import dashboard as _dash
        return len(_dash._open_work_orders(root).get(project, []))
    except Exception:  # noqa: BLE001 — an unreadable store is plainly zero
        return 0


def pipeline_brief(project: str, repo_root: Path | None = None) -> dict | None:
    """The composed brief for ``project`` (W-PROJECT), over the EXISTING chain +
    verdict read models (the lock-step law). ``None`` for an unknown project (the
    registry fence). Returns the delta-and-ask ``glance``, the one ``consequential``
    move + its door, and the count chips (stages / organs / orders / rounds) the
    resting brief renders — the board itself stays in :func:`chain`, summoned behind
    one open."""
    proj = registry.resolve(project)
    if proj is None:
        return None
    root = (repo_root or _repo_root()).resolve()
    ch = chain(project, repo_root=root)
    if ch is None:
        return None
    try:
        from laplace.pipeline import project_state as _ps
        verdict = _ps.project_verdict(root, proj.name)
    except Exception:  # noqa: BLE001 — a verdict hiccup leaves the brief on the chain truth alone
        verdict = {"present": False}

    states = ch.get("states") or []
    organs = ch.get("organs") or []
    rounds = verdict.get("rounds") or {}
    rounds_n = rounds.get("n") or 0
    orders_n = _banked_orders(proj.name, root)

    state_line = _brief_state_line(ch, verdict, rounds_n)
    ran_last = _brief_ran_last(verdict)
    next_line = _brief_next_line(verdict)
    # ctx supplies the manuscript dir so the consequential reproject door can name the
    # brief as a REAL door (the SAME _brief_door the staged fire control carries).
    try:
        ctx = registry.project_context(proj.name, root)
    except Exception:  # noqa: BLE001 — no ctx ⇒ honest-absent brief door, the move still stands
        ctx = None
    conseq = _brief_consequential(proj.name, ch, verdict, ctx)
    respine_open = bool((verdict.get("generations") or {}).get("respine_intent"))
    decision_line = ("One decision waits: rule the queued RESPINE."
                     if respine_open else None)

    glance_parts = [state_line]
    if ran_last:
        glance_parts.append(ran_last)
    if next_line:
        glance_parts.append(next_line)
    if decision_line:
        glance_parts.append(decision_line)
    glance = " ".join(p for p in glance_parts if p)

    return {
        "project": proj.name,
        "kind": ch.get("kind"),
        "position": ch.get("position") or ch.get("current_state"),
        "never_run": bool(ch.get("never_run")),
        "brief": {
            "glance": glance,
            "state_line": state_line,
            "ran_last": ran_last,
            "next_line": next_line,
            "decision": decision_line,
            "consequential": conseq,
        },
        "counts": {
            "stages": len(states),
            "organs": len(organs),
            "orders": orders_n,
            "rounds": rounds_n,
        },
        "info": {
            "brief": "/pipeline/brief → pipeline_surface.pipeline_brief (composed over "
                     "chain + project_verdict — the lock-step law; the board is summoned "
                     "behind one open, never resident at rest)",
        },
    }


# ---------------------------------------------------------------------------
# GET /pipeline/prompts — The prompts view (HIS COMMISSION, PV-20260722T225941Z,
# verbatim: "see the actual prompts they use"). A read-only door serving, per
# dispatch WORKER role, the REAL prompt text the dispatch layer composes — the
# genuine static template with its override provenance named. Where a prompt is only
# fully composed At dispatch time with live substrate (a packet, a voice profile, a
# node graph), the view shows the genuine template PLUS a worded note of what gets
# folded in — never a fabricated specimen composition. The composition lives around
# ``pipeline/dispatch.py`` compile_dispatch and the roles/prompts dial group.
# ---------------------------------------------------------------------------

#: per dispatch worker — the worded note of what LIVE SUBSTRATE compile_dispatch folds
#: into the genuine template at dispatch time (faithful to the worker branches in
#: ``dispatch.py``). The template pieces themselves are the real module constants served
#: below; this only names what is NOT knowable until a real target + goal are in hand.
_WORKER_FOLDS: dict[str, str] = {
    "prose": "the AIM head (this section's aim + goal/role/acceptance), the VOICE-PROFILE "
             "fence (the resolved voice profile file), the PACKET fence (the closed "
             "narrative specification for the target section), an optional derivation_walk "
             "FORM channel (dial-gated), any open section findings, and the OUTPUT CONTRACT "
             "(the exact .tex + provenance-sidecar paths for the target).",
    "structure": "the kernel head, the BUILDER-CONTRACT policy, the OBJECT (the manuscript "
                 "record + contract skeletons + the derived reader-state graph), an optional "
                 "section_architecture FORM channel (dial-gated), the AUTHOR-ARCHITECTURE "
                 "profile (refs-only) when present, and the STANDING-RULINGS channel — his "
                 "own live banked verdicts recalled from proxy_verdicts.jsonl against this "
                 "target + goal, as typed rows with refs (the taste flywheel's return leg; "
                 "an empty recall still rides, stating the absence).",
    "narrative": "the kernel head, the section contract, the node OBJECTs of the section's "
                 "nodes (from the corpus network), the figure specs + the section's equation "
                 "ledger — assembled at dispatch from live stores — plus the "
                 "AUTHOR-ARCHITECTURE section brief and the STANDING-RULINGS channel (his "
                 "live banked verdicts on this section's subject, typed rows with refs).",
    "render": "the kernel head + the deterministic render instruction over the assembled "
              "manuscript (a mechanical utility, least-capable by design).",
    "derive": "the kernel head + the derivation object for the target node (opus/high — the "
              "reach worker).",
    "simulate": "the kernel head + the provenance-backed script call for the figure/sim node.",
    "figure": "the kernel head + the figure generator call + its provenance record.",
    "mint": "the kernel head + the mint instruction (a low-tier mechanical utility).",
}


def prompts_view(project: str | None = None,
                 repo_root: Path | None = None) -> dict:
    """The prompts view — per worker role, the genuine composed template + its override
    provenance, plus the fold note for what live substrate rides at dispatch. Pure read;
    NEVER runs compile_dispatch (no live-substrate specimen is fabricated). ``project`` is
    optional context only — the templates are the engine's, not a project's."""
    from laplace.pipeline import schema
    from laplace.pipeline import dials as _dm
    root = (repo_root or _repo_root()).resolve()
    d = _dm.load_dials()

    # the calibratable role tiers (the roles dial group) — the SAME knobs the organ
    # cards edit; named here so the prompts view and the dials-in-place agree.
    roles = {name: {"model": v.get("model"), "effort": v.get("effort")}
             for name, v in (d.get("roles") or {}).items()}

    # the genuine STATIC template constants the composer uses (real module text, not a
    # specimen). Each carries its own source so a reader can trace it to the code.
    templates = {
        "prose_stage_preamble": {
            "source": "schema.PROSE_STAGE_PREAMBLE",
            "text": schema.PROSE_STAGE_PREAMBLE},
        "builder_contract_line": {
            "source": "schema.BUILDER_CONTRACT_LINE",
            "text": schema.BUILDER_CONTRACT_LINE},
        "aim_head": {
            "source": "dispatch._aim_head_fence — the AIM block prepended to every "
                      "prompt-bearing packet",
            "text": schema.fence("AIM", "This <worker> packet advances <the paper's "
                    "stated essence>. It is <section N of M>[; K later section(s) depend "
                    "on it]. Converge to the proper object the plan names — where a fact "
                    "is missing, return a typed issue against the owning stage; do not "
                    "guess.\n<goal / role_in_whole / acceptance JSON — composed at "
                    "dispatch from the live manifest>")},
    }

    workers = []
    for w in schema.WORK_KINDS:
        model, effort = schema.WORKER_MODEL.get(w, (schema.MAX_MODEL, "medium"))
        workers.append({
            "worker": w,
            "model": schema.clamp_model(model),
            "effort": effort,
            "folded_at_dispatch": _WORKER_FOLDS.get(w, "assembled at dispatch from the "
                                  "live plan + stores for the target."),
        })

    # the OVERRIDE surface — the prompt-override rule + every override file present, with
    # its REAL text (the genuine prompt), so the provenance is named, not asserted.
    overrides_dir = (d.get("prompts") or {}).get("overrides_dir") or ""
    ov_base = Path(overrides_dir)
    if not ov_base.is_absolute():
        ov_base = root / ov_base
    present: list[dict] = []
    if ov_base.is_dir():
        for f in sorted(ov_base.iterdir()):
            if f.is_file() and f.suffix.lstrip(".") in _dm._PROMPT_EXTS:
                try:
                    text = f.read_text(encoding="utf-8")
                except OSError:
                    text = ""
                present.append({
                    "name": f.stem, "ext": f.suffix.lstrip("."),
                    "path": str(f.relative_to(root)) if f.is_relative_to(root) else f.name,
                    "bytes": f.stat().st_size,
                    "text": text})

    return {
        "project": project,
        "composition_site": "pipeline/dispatch.py compile_dispatch — the kernel/AIM head "
                            "+ OBJECT + POLICY, composed per worker; the roles + prompts "
                            "dial group calibrate it",
        "roles": roles,
        "templates": templates,
        "workers": workers,
        "overrides": {
            "dir": overrides_dir,
            "rule": "a file <overrides_dir>/<name>.<md|txt|j2|jinja> REPLACES the built-in "
                    "prompt template for judge/reader/role <name> WHOLESALE (never appends); "
                    "absent, the built-in template stands. <name> is the panel label / "
                    "reader id / role name.",
            "present": present,
            "note": "these files carry the REAL override text; each names its own target "
                    "in its provenance header (e.g. feral.md → the R7 sealed-read).",
        },
        "law": "read-only. This door serves the genuine template + its override provenance; "
               "a prompt only fully composed at dispatch (with a live packet / voice profile "
               "/ node graph) shows the template + a worded fold note, never a fabricated "
               "specimen composition.",
        "info": {
            "prompts": "/pipeline/prompts → pipeline_surface.prompts_view (the real dispatch "
                       "templates + override provenance; view = the composer's own constants, "
                       "never a drawn or invented prompt).",
        },
    }


# ---------------------------------------------------------------------------
# the HTTP handler (analytics / desk / dials contract): GET reads only.
# ---------------------------------------------------------------------------

def handle(path: str, query: dict, method: str,
           body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/pipeline*`` request. Returns (status, content_type, body) or
    ``None`` when the path is not ours — the bare ``GET /pipeline`` page is served
    by the scanner (mirrors the other apps). READ-ONLY: every mutation (a dial edit,
    a scoped fire) rides an EXISTING door (``/dials/op`` · ``/dials/undo`` ·
    ``/storyboard/run/launch``); this surface owns no write route, so POST is 405."""
    if path != "/pipeline" and not path.startswith("/pipeline/"):
        return None
    method = (method or "GET").upper()

    if path == "/pipeline":
        return None  # the bare page is served by the scanner (reads pipeline.html)

    if method != "GET":
        return _json_resp(405, {"error": f"{method} not allowed — /pipeline is read-only "
                                "(edits ride /dials/op, /dials/undo, /storyboard/run/launch)"})

    if path == "/pipeline/brief":
        # The composed brief (W-PROJECT) — the resting altitude of the /project surface
        # joined to the one instrument. Composes over the EXISTING chain + verdict read
        # models (the lock-step law); the board is summoned behind one open.
        project = _q1(query, "project") or _q1(query, "corpus")
        if not project:
            return _json_resp(400, {"error": "project= required"})
        try:
            out = pipeline_brief(project)
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"pipeline brief assembly failed: {e}"})
        if out is None:
            return _json_resp(404, {"error": f"unknown project {project!r}"})
        return _json_resp(200, out)

    if path == "/pipeline/prompts":
        # The prompts view (HIS COMMISSION) — the REAL dispatch templates + override
        # provenance, per worker role. Pure read; NEVER composes a live specimen.
        # ``project`` is optional context (the templates are the engine's).
        project = _q1(query, "project") or _q1(query, "corpus") or None
        try:
            out = prompts_view(project)
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"prompts view assembly failed: {e}"})
        return _json_resp(200, out)

    if path == "/pipeline/chain":
        project = _q1(query, "project") or _q1(query, "corpus")
        if not project:
            return _json_resp(400, {"error": "project= required"})
        profile = _q1(query, "profile") or _DEFAULT_PROFILE
        try:
            out = chain(project, profile)
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"pipeline chain assembly failed: {e}"})
        if out is None:
            return _json_resp(404, {"error": f"unknown project {project!r}"})
        return _json_resp(200, out)

    if path == "/pipeline/verdict":
        # THE COCKPIT'S TRUTH LAYER (ACT 4) — the one typed verdict the state strip +
        # generation panel + RESPINE card read: position (pre-machine history labelled
        # plainly), the debt trajectory as a first-class series, the RESPINE intent
        # named "gen-4's opener", owed-to-author. Pure read: project_state.project_verdict
        # is a JOIN of existing readers (READ-ONLY import — this surface never edits it).
        project = _q1(query, "project") or _q1(query, "corpus")
        if not project:
            return _json_resp(400, {"error": "project= required"})
        proj = registry.resolve(project)
        if proj is None:
            return _json_resp(404, {"error": f"unknown project {project!r}"})
        try:
            from laplace.pipeline import project_state
            out = project_state.project_verdict(_repo_root(), proj.name)
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"pipeline verdict assembly failed: {e}"})
        return _json_resp(200, out)

    if path == "/pipeline/organ":
        # The conjugate wave — one sub-organ's FULL reader payload, PURE read
        # (view=mechanism: the organ's own reader, never a re-parse). Heavy telemetry
        # lazy-joins here so /pipeline/chain stays bounded. organ=proxy|figures + &dryrun=1
        # returns the dry-run frames (proxy: fork_adjudicator.drive, zero tree writes;
        # figures: run(apply=False, run_gen=False), non-mutating). POST stays 405 above.
        project = _q1(query, "project") or _q1(query, "corpus")
        organ = _q1(query, "organ")
        if not project:
            return _json_resp(400, {"error": "project= required"})
        if not organ:
            return _json_resp(400, {"error": "organ= required"})
        proj = registry.resolve(project)
        if proj is None:
            return _json_resp(404, {"error": f"unknown project {project!r}"})
        if organ not in _KNOWN_SUBORGANS:
            return _json_resp(404, {"error": f"unknown organ {organ!r} — one of "
                                    f"{sorted(_KNOWN_SUBORGANS)}"})
        dryrun = _q1(query, "dryrun") in ("1", "true", "yes")
        try:
            root = _repo_root().resolve()
            ctx = registry.project_context(project, root)
            payload = read_organ(organ, proj.name, ctx, root, dryrun=dryrun)
        except Exception as e:  # a substrate hiccup is a 500, never a crash
            return _json_resp(500, {"error": f"pipeline organ read failed: {e}"})
        if payload is None:
            return _json_resp(404, {"error": f"unknown organ {organ!r}"})
        return _json_resp(200, {"project": proj.name, "organ": organ,
                                "dryrun": dryrun, "payload": payload})

    return _json_resp(404, {"error": f"no pipeline route {path!r}"})
