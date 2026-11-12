"""THE DIALS — the pipeline's one outward-facing calibration surface.

Every stage of the convergence pipeline is calibratable from HERE, never from a
constant buried in a script (his directive, 2026-07-09): model tier + effort per
role, which readers fire at candidate-lock, verify-vote counts, round budget,
drift tolerances, suppression posture, and per-judge/per-reader prompt overrides.

The split mirrors ``profiles/voice/`` and ``profiles/house_style/``:

  * the CODE owns the defaults (``_DEFAULTS`` below) — today's design, so the
    pipeline runs with zero configuration;
  * ``profiles/pipeline/dials-v1.yaml`` is the VERSIONED profile that overlays the
    defaults — the file a human edits to recalibrate a run.

``load_dials`` deep-merges the profile onto the defaults and **raises loudly on
any unknown key** — a typo (``buidler``, ``verify_vote``) must never silently
no-op into today's default. The returned object is a plain nested ``dict`` (JSON-
shaped, so it banks into a release bundle and renders in the guide) carrying a
``version`` field.

Prompt-override naming rule (documented once, here): a per-judge/per-reader
override file lives at ``<overrides_dir>/<name>.<ext>`` where ``<name>`` is the
panel label / reader id / role name (e.g. ``referee.md``, ``cold_reader.md``,
``house_style.txt``) and ``<ext>`` is one of ``md``/``txt``/``j2``/``jinja``.
When such a file is present it **REPLACES** that judge's built-in prompt template
wholesale (not appends); absent, the built-in template stands. ``overrides_dir``
is resolved relative to the repo root when not absolute; the directory is
optional.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import copy
from pathlib import Path
from typing import Any

from laplace.pipeline import schema as _schema

#: repo root = src/laplace/pipeline/dials.py -> parents[3]
_REPO_ROOT = source_tree()

#: the versioned profile that overlays the code defaults (parallel to
#: profiles/voice/, profiles/house_style/). Consulted by ``load_dials(None)``.
DEFAULT_DIALS_PATH = _REPO_ROOT / "profiles" / "pipeline" / "dials-v1.yaml"

#: The profiles a run or the /dials surface may name, resolved by basename only.
#: the ONLY profiles a browser edit may touch, by basename equality (never a
#: caller-supplied path — a traversal shape is a named reject).
#: dials-v2.yaml joined 2026-07-19 (the consolidation, C01/BLOCKER-A): the voiced-
#: everywhere intent record becomes a lawful, launchable profile — threaded per-run
#: through the compile chain (dispatch._resolve_dials), never a hand-edit of v1.
#: dials-arm-opus.yaml joined 2026-08-04 (B17): the measured-arm policy — every
#: role AND the python-leg dispatch pin at the apex tier, so no stage of a
#: benchmark arm rides a cheaper model than the arm claims.
PROFILE_ALLOWLIST = {"dials-v1.yaml", "dials-v2.yaml", "dials-h.yaml",
                      "dials-arm-opus.yaml"}


class DialsProfileError(ValueError):
    """A profile name outside the allowlist (an unknown profile or a traversal)."""


def profile_dir() -> Path:
    """The directory the profiles live in. The one seam tests monkeypatch to a
    tmp copy — the allowlist logic in :func:`profile_path` stays exercised."""
    return _REPO_ROOT / "profiles" / "pipeline"


def profile_path(name: str) -> Path:
    """Resolve a profile name under ``profiles/pipeline/``, by BASENAME equality
    against the allowlist. Anything not in the allowlist (an unknown profile, a
    ``../`` traversal, an absolute path) is a named reject — never a filesystem
    touch."""
    if name != Path(name).name or name not in PROFILE_ALLOWLIST:
        raise DialsProfileError(
            f"profile {name!r} refused — not in the allowlist "
            f"{sorted(PROFILE_ALLOWLIST)} (a path/traversal is never a profile)")
    return profile_dir() / name

#: role -> {model, effort}. Sealed readers are least-capable BY DESIGN
#: (worse-is-better: a context-starved reader that still follows the argument is
#: the sharp test); builders/welders/referee/voice-washer run at the top tier.
#:
#: NOT a second model-choice table, and the distinction is the reason this one stays.
#: ``schema.ROLE_TIER`` answers "what model does THIS SYSTEM give a role of the engine
#: --- the in-app session, a dispatched worker, a judge, a test" and is derived, with no
#: literal and nothing a human edits.  These ``roles`` are the convergence pipeline's
#: CALIBRATION surface: a per-stage dial a human retunes through ``/dials`` and the
#: versioned ``profiles/pipeline/dials-v1.yaml`` overlay, so a literal here is the dial's
#: current SETTING, not a decision about which model the system is.  The two tables share
#: exactly one role NAME, ``judge``; that one row is therefore DERIVED from the tier table
#: below instead of typed, and ``tests/test_writing_provider_tiers.py``
#: ``test_the_one_role_name_the_two_tables_share_agrees`` fails the moment the loaded dials
#: (defaults plus profile overlay) disagree with ``schema.role_model('judge')``.
_DEFAULTS: dict[str, Any] = {
    "version": "dials-v1",
    "roles": {
        "builder":      {"model": "opus",   "effort": "high"},
        "welder":       {"model": "opus",   "effort": "high"},
        # the shared name, read out of the tier table (today: sonnet/medium)
        "judge":        {"model": _schema.tier_model(_schema.role_tier("judge")),
                         "effort": _schema.tier_effort(_schema.role_tier("judge"))},
        "sealed_reader":{"model": "haiku",  "effort": "low"},   # worse-is-better
        "referee":      {"model": "opus",   "effort": "high"},
        "vision":       {"model": "sonnet", "effort": "medium"},
        "voice_washer": {"model": "opus",   "effort": "high"},
        "fixer":        {"model": "sonnet", "effort": "medium"},
        "utility":      {"model": "haiku",  "effort": "low"},
        # AUDIT §A3 (F1): the STAGED build leg's own roles. The leg
        # (project-staged.js) historically read ZERO dials and carried its model
        # tiers as in-script literals; these three name those literals AT TODAY'S
        # ACTUAL tiers, so bringing the leg under dials is honest with ZERO silent
        # behaviour change by default (retunable on /dials). The narrative planners
        # and prose realisers ran at sonnet; the leg's mechanical utilities
        # (read-manifest / compile-dispatches / validate / post-weld-fidelity) ran
        # at haiku/low. The ONE real behaviour change is NOT here: the weld maps to
        # the EXISTING ``welder`` (opus/high) role above — honouring the dial that
        # always claimed the seat the staged literal had pinned to sonnet.
        "planner":       {"model": "sonnet", "effort": "medium"},  # staged narrative
        "realiser":      {"model": "sonnet", "effort": "medium"},  # staged prose
        "staged_utility":{"model": "haiku",  "effort": "low"},     # staged mechanical utilities
    },
    # THE ARM MODEL PIN (B17). ``roles`` is the tier policy the .js organs read;
    # this group is the SAME policy for the python leg (compile_dispatch), whose
    # stamp otherwise comes from the per-worker schema.WORKER_MODEL constant. A
    # measured arm needs both moved together or half the run rides another tier.
    #   model_pin : a FLOOR tier applied BEFORE schema.clamp_model (pin-then-clamp,
    #               so the ceiling law still binds). None = inert: the per-worker
    #               default stands and the stamp is byte-identical to pre-pin.
    #   model_id  : the exact provider id string the run ledger records VERBATIM.
    #               MODEL_RANK carries tier tokens only, with no version grade, so
    #               the tier is what the audit can enforce and the id is what the
    #               ledger can prove. None = no id claimed.
    "dispatch": {
        "model_pin": None,
        "model_id": None,
    },
    "loop": {
        "max_rounds": 4,
        # LEG A (his ruling, 2026-07-10, evidence-backed): the fixing middle is
        # DEMOTED. The RULED TARGET default is the HARNESSED pass
        # (project-harnessed.js): mechanical detect -> adjudicate -> ONE
        # tightly-harnessed strong fixing pass -> mechanical re-detect ->
        # revert-on-regression -> conditional second pass -> lock -> finalize.
        # The old every-round converge loop (project-fixedpoint.js) survives
        # behind 'loop'.
        #
        # THE MECHANICAL READINESS GATE (AUDIT_2026-07-15 §A-GATE) ruled
        # 2026-07-15: the dispatch seam is wired and live-proven on its refusal
        # leg (3x honest CANDIDATE_LOCKED refusals, atomic in-process evidence),
        # but the PASS leg (a real mint under fix_mode=harnessed) is unproven —
        # the live fixture ran tex-mode, whose corpus-coupled hard dimensions
        # (meta_leak/apparatus/claims) structurally cannot lock (§A7). Per the
        # gate law the default stays on OBSERVED behavior until a corpus-mode
        # mint proof passes; then this flips to 'harnessed' with the evidence
        # banked. Contestable at his review.
        "fix_mode": "loop",                 # harnessed|loop — gate-pinned, see above
        # the harnessed pass's own calibration (read only under fix_mode=harnessed):
        "harnessed": {
            # a conditional SECOND pass fires IFF the re-detect IMPROVED and the
            # count of open findings still standing is at/above this floor — below
            # it a second opus pass is not worth the spend (the residue rides to the
            # lock readers / the author). 0 would mean "always second-pass on any
            # residue"; the default demands a non-trivial residue.
            "second_pass_open_threshold": 3,
            # the hard cap on harnessed fixing passes in one invocation (the first
            # pass + at most this-minus-one conditional passes). Ceremony guard.
            "max_passes": 2,
        },
        # when the converge leg welds: auto (weld only when the round asks for it),
        # always (weld every round), never (never weld — scoped seam passes only).
        "weld": "auto",                     # auto|always|never
        # dirty sections at/above which a scoped seam pass escalates to a GLOBAL
        # reweld (a fix touching this many sections is no longer local).
        "weld_global_dirty_threshold": 4,
        # THE FINAL LAYER (his brief, 2026-07-10): the LAST projection layer, run
        # AFTER content converges — the rhetorical-scaffold wash (final_layer.py),
        # conjugate of scaffold_wipe one level up. It de-scaffolds the four defensive
        # voice registers, the abstract negative-inventory, the §VII self-demotion,
        # and enforces the disclaimer keep-once-where table. Gated like the voice
        # wash: OFF by default (it is the last layer, never a per-round pass).
        #   off        = never run the rhetorical wash (today's default);
        #   descaffold  = run final_layer.final_layer over the converged artefact at
        #                 the end and surface its findings + before/after census.
        "final_layer": "off",               # off|descaffold
        # the readers that must return a verdict at candidate-lock (R3 apparatus
        # runs every round and is not lock-gated; R8 is the human terminal bar). R9
        # Caption-blind (the hold-out review surface) fires here too — it needs the
        # figure crops of a compiled PDF + a vision model, so it is a lock-cadence
        # rasteriser read, driven by the harnessed lock stage's R9 dispatch branch. R10
        # Restart (the whole-artefact judgement grade) also fires here — a two-phase
        # blind-then-compare read of the finished PDF TEXT, driven by the HARNESSED lock
        # stage's R10 dispatch branch (extract_artefact_text -> restart_reader.blind_packet
        # -> compare_packet(intended=plan.meta) -> bank -> verdict_io write 'restart'; an
        # absent finalized PDF reads as FAILED, never a false clean). Fixedpoint's lock
        # tier gets NO R10 arm (the tier-aware ruling).
        "lock": {"readers": ["R1", "R2", "R4", "R5", "R6", "R7", "R9", "R10"],
                 "voice_wash": True},
        "verify_votes": 1,
    },
    "drift": {
        "page_change_warn": 3,          # > this many changed pages -> unexpected
        "page_count_change": "loud",    # a page-count delta is ALWAYS loud
    },
    "suppression": {
        "key": ["node", "kind", "fingerprint"],
        "stale_on_fingerprint_mismatch": True,
    },
    "routing": {
        # finding KINDS the fixer defers pending human adjudication: still
        # reported (the panel stays unclean, no lock), never dispatched to
        # builders/patchers. The class-grain conjugate of per-instance
        # suppression - for known noise-heavy classes (eq-unused on named
        # results) where machine "fixes" would be the noise made flesh.
        # Default EMPTY: nothing deferred unless a profile says so.
        "defer_kinds": [],
        # THE META-SIGNAL threshold (G-3): the review surface surfaces
        # 'recalibrate the check?' for a finding-KIND once this many of its
        # instances have been dismissed — the class-vs-instance signal that the
        # CHECK, not each finding, is miscalibrated. Author-gated evidence only;
        # no auto-recalibration.
        "dismissal_recalibrate_threshold": 5,
    },
    "machine_adjudication": {
        # BITE B1 — the machine-adjudication organ (verdicts as files). When
        # enabled, the per-round adjudicate step runs the Tier-1 rules over the
        # DEFERRED classes and banks actor:"machine" verdicts BEFORE the route.
        "enabled": True,
        # the finding-KINDS the machine may DISMISS (drop a fingerprinted non-
        # fault). A kind OUTSIDE this list may only be confirmed or escalated —
        # never machine-dismissed (enforced in machine_adjudicate). Default
        # empty: the machine dismisses nothing unless a profile opts a class in.
        "may_dismiss": [],
        # N machine-dismissals of a KIND in one run deposits a calibration intent
        # (the CHECK, not the instance, may be miscalibrated) — author-gated.
        "calibration_threshold": 5,
        # the referee tier for the residue (undecidable) queue. Defaults to the
        # existing 'referee' role tier when a profile does not override it.
        "referee": "referee",
    },
    "mech": {
        # The mechanical geometry floor (2026-07-10 run evidence): the compile
        # log locates every overfull box for free with its pt overhang; only
        # overflow past this VISIBLE floor makes the visual axis unclean.
        # Sub-floor boxes are typographically invisible and tolerated.
        "overfull_floor_pt": 6.0,
    },
    "regen_grain": {
        # BITE B3 — the regen-GRAIN dial (his ruling, 2026-07-10): a sparse fault
        # regenerates the offending `% <SEC>-pN` PARAGRAPH(s), not the whole
        # section (section grain was measured wildly blunt for small faults); a
        # dense or structural fault still regenerates the section (today's path).
        #   auto    = the route's density heuristic decides per section;
        #   section = KILL-SWITCH — restore today's section-grain behaviour
        #             byte-identically (no paragraph_regens emitted).
        "mode": "auto",
        # a section demotes to paragraph grain only when the faulted paragraphs are
        # at most this fraction of the section's paragraphs (ceil). Above it the
        # fault is dense enough that a section rebuild is the honest grain.
        "paragraph_max_fraction": 0.4,
        # finding KINDS that FORCE section grain even when sparse — a structural
        # fault (a missing section-level object, a reorder) is never a paragraph
        # patch. Default empty: nothing is structural unless a profile says so.
        "structural_kinds": [],
    },
    "fanout": {
        # AUDIT §A4 — the pipeline's fan-out width / batch bound (F2). Every
        # workflow fan-out (project-staged / project-fixedpoint's
        # parallel(items.map(...))) reads its cap from HERE via pipeline/fanout.py
        # (width/pack) — never an uncapped one-agent-per-item dispatch buried in a
        # script. The batched discipline is lifted from the wf_fold_*.mjs family.
        #   max_width       = fixed-width fan-out cap; 0 means UNCAPPED (today's
        #                     exact behaviour — one batch = the whole list, so the
        #                     default changes no existing fleet's shape). A real
        #                     cap is OPT-IN via the profile.
        #   batch_max_chars = the char budget for a char-bounded pack() batch (the
        #                     wf_fold_up pack precedent); consulted only by callers
        #                     that batch on size rather than count.
        "max_width": 0,
        "batch_max_chars": 140000,
    },
    "stores": {
        # THE STAGE-STORE KILL-SWITCH (DESIGN_2026-07-15_the-stage-stores §4).
        # The retrieval wire (pipeline/stage_retrieval.build_form_channel) injects
        # FORM exemplars from a gate-passed corpus store into a stage's compiled
        # dispatch. Each store is readable IFF its per-store `enabled` flag is true
        # AND its corpus_stores/<store>/gate_verdict.json passed its holdout gate
        # (§5). EVERY flag ships FALSE, so the wiring lands behaviour-inert: a
        # narrative compile at these defaults is byte-identical to pre-wire, and a
        # store enters a prompt only on a deliberate flip.
        #
        # THE DIAL CANNOT OVERRIDE THE GATE (§4 law): a store whose flag is true but
        # whose gate verdict is absent or FAILED REFUSES loudly (stage_retrieval
        # raises) — the dial is a permission, never the gate's proof. A flag is
        # flipped ONLY once its holdout gate passes (the audit's §A-GATE pattern:
        # the default is never a pre-commitment, it is the gate's evidence).
        # flipped ON at his in-session yes (2026-07-16, "flip and run") after the
        # first watched run: 13/13 falqon narrative compiles served + sidecar-banked;
        # the two-key gate (gate_verdict + hardened refusal proof) stands behind it
        "paragraph_plan":       {"enabled": True},
        "section_architecture": {"enabled": False},
        "spine_chain":          {"enabled": False},
        "derivation_walk":      {"enabled": False},
        "figure_caption":       {"enabled": False},
    },
    "prompts": {
        "overrides_dir": "profiles/pipeline/prompts",
    },
    "evolution": {
        # THE RATIFY-MODE DIAL (his ruling 2026-07-21; consumes the banked
        # ratify-mode-dial work order). Governs the evolution desk's ratify DOOR
        # SHAPE only — the law (his word, armed + attributed, per-item records)
        # is identical under both values:
        #   per-item = every ratification is its own arm→apply round trip
        #              (the desk's original posture);
        #   bulk-arm = the queue card additionally offers "ratify all (N)": ONE
        #              arm round-trip previews every open application, one
        #              attributed apply fires them through the same transactional
        #              path, a per-item record banked each, STOP on first failure
        #              (no partial silence). Hold/reject stay per-item always.
        "ratify_mode": "per-item",
    },
    "selection": {
        # THE SELECTION DIAL (P2). Names which DRAFT selection-rule FILE the selection
        # sheet reads (profiles/selection/<value>.yaml) — ψ/φ are HIS; the file only
        # proposes. The rule FILE is versioned; recalibration is a NEW file
        # (draft-psi-v2), NEVER an edit — the threshold is calibrated by experience, so
        # a moved threshold is a new generation of the rule, not a silent dial-nudge.
        "draft_psi": "draft-psi-v1",
    },
}

#: extensions a prompt-override file may carry (checked in this order).
_PROMPT_EXTS = ("md", "txt", "j2", "jinja")


def defaults() -> dict[str, Any]:
    """A deep copy of the code defaults (today's design). The loader owns these;
    the YAML only overlays."""
    return copy.deepcopy(_DEFAULTS)


def _overlay(base: dict[str, Any], over: dict[str, Any], path: str = "") -> None:
    """Deep-merge ``over`` into ``base`` in place. UNKNOWN keys raise loudly: a
    key present in the overlay but absent from the defaults schema at that level
    is a typo, never a new dial (a silent no-op would hide a mis-calibration)."""
    for k, v in over.items():
        dotted = f"{path}{k}"
        if k not in base:
            raise ValueError(
                f"unknown dial key {dotted!r} — not in the defaults schema; "
                "a typo must not silently no-op (add it to dials._DEFAULTS first)")
        if isinstance(base[k], dict):
            if not isinstance(v, dict):
                raise ValueError(
                    f"dial key {dotted!r} expects a mapping, got {type(v).__name__}")
            _overlay(base[k], v, dotted + ".")
        else:
            base[k] = v


def load_dials(path: str | Path | None = None) -> dict[str, Any]:
    """Load the dials: code defaults overlaid by a versioned YAML profile.

    ``path=None`` overlays :data:`DEFAULT_DIALS_PATH` when it exists (the versioned
    profile is the live calibration surface; the code defaults are the fallback if
    the file is absent). An explicit ``path`` overlays that file (missing file ->
    ``FileNotFoundError``, loud). Any key not in the defaults schema raises
    ``ValueError``. Returns a plain nested ``dict`` carrying a ``version`` field.
    """
    dials = defaults()
    src: Path | None = None
    if path is not None:
        src = Path(path)
    elif DEFAULT_DIALS_PATH.is_file():
        src = DEFAULT_DIALS_PATH
    if src is not None:
        import yaml  # local import: only needed when a file profile is used
        with open(src, "r", encoding="utf-8") as fh:
            overlay = yaml.safe_load(fh)
        if overlay is None:
            overlay = {}
        if not isinstance(overlay, dict):
            raise ValueError(f"dials profile {src} must be a mapping, got "
                             f"{type(overlay).__name__}")
        _overlay(dials, overlay)
    return dials


# --- small typed accessors (raise on a mistyped role, mirroring the loader) ---

def role(dials: dict[str, Any], name: str) -> dict[str, Any]:
    """``{model, effort}`` for a role. Raises ``KeyError`` naming the known roles
    if ``name`` is not a role (typo protection at the call site too)."""
    roles = dials.get("roles") or {}
    if name not in roles:
        raise KeyError(f"unknown role {name!r}; known: {sorted(roles)}")
    return roles[name]


def model_pin(dials: dict[str, Any] | None) -> str | None:
    """The arm's FLOOR tier for the dispatch stamp, or ``None`` (inert). Read by
    ``pipeline.dispatch.compile_dispatch`` and applied through ``schema.pin_model``
    BEFORE ``schema.clamp_model``."""
    if not dials:
        return None
    return ((dials.get("dispatch") or {}).get("model_pin")) or None


def model_id(dials: dict[str, Any] | None) -> str | None:
    """The exact provider model-id string this arm claims, recorded verbatim in the
    dispatch record. The audit enforces the TIER; this proves the id."""
    if not dials:
        return None
    return ((dials.get("dispatch") or {}).get("model_id")) or None


def lock_readers(dials: dict[str, Any]) -> list[str]:
    """The reader labels that must return a verdict at candidate-lock."""
    return list(((dials.get("loop") or {}).get("lock") or {}).get("readers") or [])


def final_layer_mode(dials: dict[str, Any]) -> str:
    """The end-stage rhetorical-wash dial: ``off`` (default) or ``descaffold``. When
    ``descaffold`` the harnessed flow runs ``final_layer.final_layer`` over the
    converged artefact as the LAST layer and banks its findings + before/after
    disclaimer census (the conjugate of the ``loop.lock.voice_wash`` gate)."""
    return str(((dials.get("loop") or {}).get("final_layer")) or "off")


def prompt_override(dials: dict[str, Any], name: str,
                    repo_root: str | Path | None = None) -> str | None:
    """The override prompt template for judge/reader/role ``name``, or ``None`` if
    no override file is present. Naming rule: ``<overrides_dir>/<name>.<ext>`` for
    ``ext`` in ``md``/``txt``/``j2``/``jinja`` (first hit wins). When present, the
    text REPLACES the built-in template for that judge (never appends)."""
    d = (dials.get("prompts") or {}).get("overrides_dir")
    if not d:
        return None
    base = Path(d)
    if not base.is_absolute():
        base = Path(repo_root or _REPO_ROOT) / base
    for ext in _PROMPT_EXTS:
        f = base / f"{name}.{ext}"
        if f.is_file():
            return f.read_text(encoding="utf-8")
    return None
