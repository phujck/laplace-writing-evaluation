"""The reader-suite roster — the declarative spine Phase F consumes (checklist cat 13).

The terminal coherence test, conjugate to the scaffold-wipe: erasure proves no
construction debris survived; the readers prove the OBJECT survives the readers a
finished physics manuscript actually meets. This module is *data*, not logic — it
declares, for each of the 10 readers, everything Phase F needs to wire the panel and
the candidate-lock tier:

    reader → owned hard-failure(s) · seal · organ · cadence · dimension · route

Two design invariants make it a *suite*, not a list, and both are mechanically
checkable here (:func:`verify_single_ownership`, :func:`verify_kind_partition`):

  (i) **Each reader is sealed from a specific thing.** All readers are denied the
      construction *intention* (the spec / plan / narrative packet). Some are
      additionally denied the *domain*. The Referee alone is armed with the domain
      and denied only the intention — naming the seal is half the design. R10 alone
      carries a seal that INVERTS between phases: phase 1 denied even the blueprint
      (it reads the rendered PDF, not the .tex), phase 2 deliberately GIVEN the
      intended object, because comparing the blind recovery against intent is its
      function (the inversion lives in ``restart_reader.compare_seal_inverted``).

  (ii) **Exactly one reader owns each of the 14 hard-failures.** The non-redundancy
       proof. A reader may additionally *detect* a failure it does not own (R7
       machine-detects #13, owned terminally by R8); ownership is single.

Built as **6 constructs sharing 3 organs**, so the roster is broad but cheap:

    * sealed-subagent organ (blind_reader upgrade) → R1 Cold, R4 Skimmer, R7 Feral,
      R10 Restart (the two-phase blind-then-compare whole-artefact judge)
    * rasteriser organ (Phase-D2 visual_gate crops)  → R5 Figure-first, R6 Visual
    * mechanical apparatus spine (Phase-C modules)    → R3 Apparatus
    * adversary (hostile_redteam_swarm)               → R2 Referee
    * human terminal                                  → R8 Author (declared, not built here)

**Silence never reads as pass** (:func:`reader_verdict_score`): a missing or failed
reader scores 0.5 — never clean — the banked quota-wall lesson already encoded in
``convergence.evaluate_round.soft_score``, restated here as the reader-level floor.

Dimensions map onto the EXISTING convergence axes only (``reader_reconstruction``,
``technical_support``, ``artefact_integrity``, ``no_meta_leak``,
``prose_transparency``, ``rhythm`` — plus the terminal human ``author_acceptance``);
no new dimension is invented. Phase F owns ``convergence.py`` / ``schema.py`` /
``project-fixedpoint.js``; this module only declares what those must reflect.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


# ---------------------------------------------------------------------------
# The 13 hard-failures — single-owned (invariant ii)
# ---------------------------------------------------------------------------
#
# Each entry: the failure a finished physics manuscript must not exhibit, its one
# owning reader, any reader that additionally *detects* it (never owns it), and the
# convergence dimension the failure lives on. The "#N" tags mirror the plan's
# roster table. R4 Skimmer owns no numbered hard-failure: it re-verifies the
# skim-path (checklist cat 12) from the truncated bandwidth and feeds the
# reader_reconstruction axis it shares with R1 — a reader that detects, on the
# reconstruction dimension, without solely owning one of the numbered thirteen.

@dataclass(frozen=True)
class HardFailure:
    id: str
    tag: str                    # the plan's "#N"
    desc: str
    owner: str                  # the single owning reader id (invariant ii)
    dimension: str              # an existing convergence axis
    also_detected_by: tuple[str, ...] = ()


HARD_FAILURES: dict[str, HardFailure] = {
    hf.id: hf for hf in (
        HardFailure("claim-unearned", "#1",
                    "a major claim's evidence is not SUFFICIENT (is-this-earned / is-this-yours)",
                    owner="R2", dimension="technical_support"),
        HardFailure("global-unrecoverable", "#2",
                    "a cold reader cannot reconstruct problem/method/evidence-boundary/conclusion from the whole page",
                    owner="R1", dimension="reader_reconstruction"),
        HardFailure("figure-not-singular", "#3",
                    "a figure has no single principal function — it serves several purposes at once",
                    owner="R5", dimension="no_meta_leak"),
        HardFailure("figure-debris", "#4",
                    "construction debris survives in a figure (leftover arrows, type-tags, non-claim labels)",
                    owner="R5", dimension="no_meta_leak"),
        HardFailure("caption-mini-paper", "#5",
                    "a caption is a mini-paper (spec restatement / generating questions) not what-shown/how/one-observation",
                    owner="R5", dimension="no_meta_leak"),
        HardFailure("equation-not-reused", "#6",
                    "a numbered equation is never interpreted or reused — dead numbering the reader carries for nothing",
                    owner="R3", dimension="technical_support"),
        HardFailure("equation-overflow", "#7",
                    "a display equation overflows / is clipped by its column as rendered",
                    owner="R6", dimension="artefact_integrity"),
        HardFailure("claim-cite-unwired", "#8",
                    "an inherited claim / external-fact assertion has no citation wired at all",
                    owner="R3", dimension="technical_support"),
        HardFailure("notation-collision", "#9",
                    "one symbol carries two meanings, or one term of art surfaces in two spellings",
                    owner="R3", dimension="technical_support"),
        HardFailure("cross-surface-repeat", "#10",
                    "the same content repeats across surfaces (equation / prose / caption)",
                    owner="R3", dimension="technical_support",
                    also_detected_by=("R7",)),          # R7 owns the within-prose grain (#11)
        HardFailure("generated-cadence", "#11",
                    "machine cadence / repeated mannerism in the prose — the generated feel",
                    owner="R7", dimension="prose_transparency"),
        HardFailure("page-geometry", "#12",
                    "page geometry defect: column collision, tiny label, crowding, float misplacement",
                    owner="R6", dimension="artefact_integrity"),
        HardFailure("intolerable-surface", "#13",
                    "the author's terminal 'this surface is intolerable' bar — human, non-overruleable",
                    owner="R8", dimension="author_acceptance",
                    also_detected_by=("R7",)),          # R7 machine-detects the form; R8 owns
        HardFailure("identity-mismatch", "#14",
                    "the paper a blind reader recovers from the FINISHED rendered PDF is "
                    "not the paper the intended object names — a whole-artefact identity "
                    "failure (the recovered object is not the intended object)",
                    owner="R10", dimension="artefact_integrity"),
    )
}


# ---------------------------------------------------------------------------
# The reader-owned finding-kinds — the NEW vocabulary Phase F wires into the schema
# ---------------------------------------------------------------------------
#
# These are the kinds the reader suite *introduces* (the conjugate of
# visual_gate.VISUAL_FINDING_KINDS). Phase F reflects each into
# ``schema.KIND_TO_WORK[kind] = work_kind`` (``WORK_TO_LAYER[work_kind]`` already
# names the owning stage). Kinds the suite REUSES rather than introduces are NOT
# here — R3 rides the Phase-C kinds (already in ``apparatus_common.FINDING_KIND_STAGE``,
# wired via C's manifest) and R6 rides ``visual_gate.VISUAL_FINDING_KINDS`` (wired
# via D2's manifest). Every kind below maps to exactly one reader (invariant, the
# real anti-double-count: :func:`verify_kind_partition`).

@dataclass(frozen=True)
class ReaderKind:
    kind: str
    reader: str
    work_kind: Optional[str]    # one of schema.WORK_KINDS, or None = VERDICT-ONLY
    owning_stage: Optional[str] # WORK_TO_LAYER[work_kind], or None when verdict-only
    sense: str
    # ``work_kind=None`` is the verdict-only idiom (R10's whole-artefact kinds): the
    # finding demands NO per-node generation — its consequence is a DRAFT projection-
    # intent — so ``register_component_kinds`` folds it to ``KIND_TO_WORK[kind]=None``,
    # exactly as ``projection-intent`` and the banked desk-review kinds already route.


READER_FINDING_KINDS: dict[str, ReaderKind] = {
    rk.kind: rk for rk in (
        # R1 Cold — reader_reconstruction → narrative / prose
        ReaderKind("cold-undefined-term", "R1", "prose", "prose",
                   "a term/notation is used before the page defines or cites it"),
        ReaderKind("cold-unmotivated-step", "R1", "prose", "prose",
                   "a step asserted as obvious that the reader could not reconstruct"),
        ReaderKind("cold-unrecoverable-role", "R1", "narrative", "narrative",
                   "a section/equation/figure whose role the reader cannot state in one line (#2)"),
        ReaderKind("cold-caption-overclaim", "R1", "prose", "prose",
                   "a figure caption claims something the reader cannot see in the panel"),
        # R4 Skimmer — reader_reconstruction (skim-path / cat 12) → narrative / prose
        ReaderKind("skim-abstract-roadmap", "R4", "narrative", "narrative",
                   "the abstract narrates the paper's own structure instead of stating the result"),
        ReaderKind("skim-overclaim", "R4", "prose", "prose",
                   "the skim surface (abstract/headings/conclusion) overclaims versus the body"),
        ReaderKind("skim-conclusion-mismatch", "R4", "narrative", "narrative",
                   "the conclusion does not answer the promise the abstract made"),
        # R7 Feral-prose — prose_transparency / rhythm → prose / weld-voice
        ReaderKind("feral-cadence", "R7", "prose", "prose",
                   "generated cadence: uniform sentence movement, list-of-three tics, hedging scaffold"),
        ReaderKind("feral-mannerism", "R7", "prose", "prose",
                   "a repeated within-prose mannerism / phrase tic (the machine grain of repetition, #11)"),
        # R5 Figure-first — no_meta_leak (+soft) → figures / prose
        ReaderKind("figure-not-singular", "R5", "figure", "figures",
                   "a figure serves more than one purpose — no single principal function (#3)"),
        ReaderKind("figure-debris", "R5", "figure", "figures",
                   "construction debris in a figure: type-tags, decorative arrows, non-claim labels (#4)"),
        ReaderKind("caption-mini-paper", "R5", "figure", "figures",
                   "a caption that is a mini-paper rather than what-shown/how/one-observation (#5)"),
        # R2 Referee — technical_support → research-state / projection
        ReaderKind("referee-insufficient", "R2", "mint", "projection",
                   "a major claim whose stated evidence is insufficient — strengthen at the projection layer (#1)"),
        ReaderKind("referee-inherited-uncited", "R2", "derive", "research-state",
                   "a claim that is actually inherited, not this paper's own — find and cite the source"),
        # R9 Caption-blind — reader_reconstruction → figures (figure-routed, like R5)
        ReaderKind("caption-blind-claim", "R9", "figure", "figures",
                   "the supported claim cannot be named from the caption+image alone — the figure is not self-sufficient"),
        ReaderKind("caption-blind-evidence", "R9", "figure", "figures",
                   "a panel's evidence type cannot be read from the caption+image alone"),
        ReaderKind("caption-blind-limitation", "R9", "figure", "figures",
                   "the figure's stated limitation/scope is absent from the caption"),
        # R10 Restart — artefact_integrity (whole-artefact identity) → VERDICT-ONLY.
        # Plan-altitude judgements: each mismatch's consequence is a DRAFT projection-
        # intent (adjudicate.make_projection_intent), never per-node work — so every
        # kind routes to None (register_component_kinds → KIND_TO_WORK[kind]=None), the
        # same idiom projection-intent itself and the desk-review kinds already use.
        ReaderKind("identity-mismatch", "R10", None, None,
                   "the primary contribution the blind reader recovered is not the intended "
                   "one — the recovered object is not the intended object (#14; → RESPINE / RESTART / REOPEN)"),
        ReaderKind("emphasis-mismatch", "R10", None, None,
                   "the rhetorical weighting recovered blind does not match the intended "
                   "contribution rank (→ DEMOTE / REORDER / SPLIT)"),
        ReaderKind("conclusion-overreach", "R10", None, None,
                   "the conclusion claims more was achieved than the artefact's own evidence "
                   "bears, read blind against intent (→ CUT / DEMOTE)"),
        ReaderKind("exclusion-violated", "R10", None, None,
                   "content the intended object marks as deliberately excluded is present / "
                   "weighted in the finished artefact (→ CUT)"),
    )
}


# ---------------------------------------------------------------------------
# The readers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Cadence:
    """When a reader runs. ``floor`` is the cheap mechanical pass (runs every fixer
    round); ``read`` is the expensive sealed/vision/panel read (runs only at
    candidate-lock, gated by the hard dims passing + a clean compile)."""
    floor: Optional[str] = None          # "every_round" | None
    read: Optional[str] = None           # "candidate_lock" | None


@dataclass(frozen=True)
class Reader:
    id: str
    name: str
    organ: str                           # sealed_subagent | rasteriser | apparatus | adversary | human
    construct: str                       # the concrete construct within the organ
    seal: str                            # the human statement of the seal
    seal_denies: tuple[str, ...]         # what the reader is NOT shown
    seal_allows: tuple[str, ...]         # what the reader IS shown (beyond the rendered artifact)
    owns: tuple[str, ...]                # hard-failure ids solely owned (invariant ii)
    also_detects: tuple[str, ...]        # hard-failures detected but not owned
    owned_kinds: tuple[str, ...]         # finding-kinds this reader is the designated owner of
    reused_kinds: tuple[str, ...]        # kinds it emits via a reused organ (owned elsewhere)
    dimension: str                       # an EXISTING convergence axis
    hardness: str                        # "hard" | "soft" | "terminal"
    panel_label: str                     # suggested project-fixedpoint panel key (F wires)
    cadence: Cadence
    runnable_now: bool                   # True = mechanical, runs without a model; False = packaged-for-F
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# The GEOMETRY kinds R6 emits via the vision read. ``overfull-visual`` is NOT
# here: overflow is log-locatable and owned by the mechanical panel (the
# ``mech.overfull_floor_pt`` dial), and R6's retargeted scope never re-inspects it
# (enforced mechanically in visual_gate.VISION_JUDGE_KINDS / parse_vision_verdict).
_VISUAL_KINDS = ("crowded-page", "tiny-label",
                 "column-collision", "equation-clip", "float-misplacement")
_C_KINDS = ("eq-unused", "eq-ref-before-intro", "eq-uninterpreted", "eq-duplicate",
            "citation-uncited", "citation-naked-reliance", "citation-cluster",
            "citation-first-use", "crosslink-broken", "crosslink-vague",
            "crosslink-far", "unlinked-reliance", "notation-inconsistent",
            "orthography-fork")

READERS: dict[str, Reader] = {
    r.id: r for r in (
        Reader(
            id="R1", name="Cold", organ="sealed_subagent",
            construct="whole rendered text; reconstruct problem/method/each-eq-role/"
                      "each-figure-role/evidence-boundary/conclusion",
            seal="total — denied the intention AND the domain; reads only the page",
            seal_denies=("spec", "plan", "narrative", "domain", "canon", "substrate"),
            seal_allows=(),
            owns=("global-unrecoverable",), also_detects=(),
            owned_kinds=("cold-undefined-term", "cold-unmotivated-step",
                         "cold-unrecoverable-role", "cold-caption-overclaim"),
            reused_kinds=("leaked-meta", "undefined-term", "use-before-define"),
            dimension="reader_reconstruction", hardness="soft",
            panel_label="cold_reader",
            cadence=Cadence(floor="every_round", read="candidate_lock"),
            runnable_now=False,
            note="floor = blind_read leaked-meta + define-before-use census; the read is the oracle",
        ),
        Reader(
            id="R2", name="Referee", organ="adversary",
            construct="hostile_redteam_swarm sufficiency read — is every major claim's "
                      "evidence SUFFICIENT (distinct from R3's is-a-cite-wired-at-all)",
            seal="intent-only — the ONE domain-armed reader; denied the spec/plan/narrative, "
                 "allowed the domain + corpus (or it grades the paper it MEANT to write)",
            seal_denies=("spec", "plan", "narrative"),
            seal_allows=("domain", "corpus", "prior_art"),
            owns=("claim-unearned",), also_detects=(),
            owned_kinds=("referee-insufficient", "referee-inherited-uncited"),
            reused_kinds=(),
            dimension="technical_support", hardness="hard",
            panel_label="referee",
            cadence=Cadence(floor="every_round", read="candidate_lock"),
            runnable_now=False,
            note="floor = citation_audit forward tell-scan (shared with R3) surfaced as "
                 "sufficiency probes; the semantic is-this-earned call needs the real adversary",
        ),
        Reader(
            id="R3", name="Apparatus", organ="apparatus",
            construct="aggregate the Phase-C mechanical findings under the reader framing: "
                      "every pointer resolves, every symbol one meaning, every eq reused, "
                      "no cross-surface repeat",
            seal="n/a — reads structure, not the intention; the graph carries no spec",
            seal_denies=("spec", "plan", "narrative"),
            seal_allows=("graph", "apparatus"),
            owns=("equation-not-reused", "claim-cite-unwired",
                  "notation-collision", "cross-surface-repeat"),
            also_detects=(),
            owned_kinds=(),                          # R3 owns no NEW kinds; it aggregates the C kinds
            reused_kinds=_C_KINDS,
            dimension="technical_support", hardness="hard",
            panel_label="apparatus",
            cadence=Cadence(floor="every_round", read=None),
            runnable_now=True,
            note="pure mechanical; imports equation_lifecycle/citation_audit/crosslink_audit/"
                 "notation_audit and re-frames their findings as the apparatus-reader verdict",
        ),
        Reader(
            id="R4", name="Skimmer", organ="sealed_subagent",
            construct="input TRUNCATED to abstract+captions+conclusion; skim-reconstruct the "
                      "skim-path (abstract-roadmap, skim overclaim, conclusion≠abstract)",
            seal="total + input-truncated — the body is physically absent from its input",
            seal_denies=("spec", "plan", "narrative", "domain", "body"),
            seal_allows=(),
            owns=(), also_detects=("global-unrecoverable",),
            owned_kinds=("skim-abstract-roadmap", "skim-overclaim", "skim-conclusion-mismatch"),
            reused_kinds=("leaked-meta",),
            dimension="reader_reconstruction", hardness="soft",
            panel_label="skim_reader",
            cadence=Cadence(floor="every_round", read="candidate_lock"),
            runnable_now=False,
            note="owns no numbered hard-failure — re-verifies checklist cat-12 skim-path from the "
                 "truncated bandwidth; feeds reader_reconstruction shared with R1 (F aggregates)",
        ),
        Reader(
            id="R5", name="Figure-first", organ="rasteriser",
            construct="figure+caption crops (Phase-D2), MEANING lens: singular-purpose / debris / "
                      "caption-scope",
            seal="from the figure spec — shown the rendered figure, denied the spec that built it",
            seal_denies=("spec", "plan", "epistemic_labels", "type_tag"),
            seal_allows=("figure_crops", "caption_crops"),
            owns=("figure-not-singular", "figure-debris", "caption-mini-paper"),
            also_detects=(),
            owned_kinds=("figure-not-singular", "figure-debris", "caption-mini-paper"),
            reused_kinds=(),
            dimension="no_meta_leak", hardness="hard",
            panel_label="figure_reader",
            cadence=Cadence(floor="every_round", read="candidate_lock"),
            runnable_now=False,
            note="floor = caption/figure scrub+lint (scaffold_wipe + caption_audit); the meaning "
                 "read is the vision judge over the SAME crops R6 uses, different question",
        ),
        Reader(
            id="R6", name="Visual", organ="rasteriser",
            construct="full-page + reading + equation crops (Phase-D2), GEOMETRY lens: "
                      "collision / tiny-label / equation-clip / float-misplacement / crowding "
                      "(NOT overflow — the log locates that; the mechanical panel owns it)",
            seal="pixels — the inverse seal: must NOT be told the layout is acceptable",
            seal_denies=("spec", "plan", "acceptability_prior"),
            seal_allows=("page_crops", "reading_crops", "equation_crops", "boundary_overlays"),
            owns=("equation-overflow", "page-geometry"), also_detects=(),
            owned_kinds=(),                          # R6 owns no NEW kinds; it rides visual_gate's
            reused_kinds=_VISUAL_KINDS,
            dimension="artefact_integrity", hardness="hard",
            panel_label="visual",
            cadence=Cadence(floor="every_round", read="candidate_lock"),
            runnable_now=True,                       # the log-overfull floor runs without a model
            note="floor = the mechanical panel's 'visual' axis = visual_gate.parse_overfull_boxes "
                 "past the mech.overfull_floor_pt dial (log-owned, every round) + D1 lint; R6 does "
                 "NOT re-inspect log-locatable overflow. The candidate-lock read is "
                 "visual_gate.pack_for_vision_judge (retargeted GEOMETRY scope) — this reader IS "
                 "D2's judge for the defects the log cannot see",
        ),
        Reader(
            id="R7", name="Feral-prose", organ="sealed_subagent",
            construct="prose-only slice; cadence / mannerism — the machine grain",
            seal="intent + profile-as-instruction — denied the spec AND the voice profile "
                 "(a description of a generator does not generate; it must feel, not check)",
            seal_denies=("spec", "plan", "narrative", "voice_profile"),
            seal_allows=(),
            owns=("generated-cadence",), also_detects=("cross-surface-repeat", "intolerable-surface"),
            owned_kinds=("feral-cadence", "feral-mannerism"),
            reused_kinds=("leaked-meta",),
            dimension="prose_transparency", hardness="soft",
            panel_label="feral",
            cadence=Cadence(floor="every_round", read="candidate_lock"),
            runnable_now=False,
            note="also feeds rhythm; the within-prose repetition grain (vs R3's cross-surface)",
        ),
        Reader(
            id="R8", name="Author", organ="human",
            construct="the terminal author_acceptance bar — the true 'intolerable surface' verdict",
            seal="none — he IS the reference; no seal is coherent for the terminal human",
            seal_denies=(), seal_allows=("everything",),
            owns=("intolerable-surface",), also_detects=(),
            owned_kinds=(), reused_kinds=(),
            dimension="author_acceptance", hardness="terminal",
            panel_label="author",
            cadence=Cadence(floor=None, read="candidate_lock"),
            runnable_now=False,
            note="NOT built in Phase E — declared for Phase F to wire as the non-overruleable "
                 "terminal (never machine-scored; last, after every other reader)",
        ),
        Reader(
            id="R9", name="Caption-blind", organ="rasteriser",
            construct="figure crop + its caption ONLY (no body, no provenance, no "
                      "surrounding section); name the supported claim, the evidence "
                      "type in each panel, and the stated limitation — a figure whose "
                      "claim/evidence/limitation cannot be named from caption+image "
                      "alone is a FAILED figure (the caption does too little or the "
                      "figure too much)",
            seal="caption+image only — denied the body prose, the provenance block, and "
                 "the surrounding section. The isolation IS the test: a caption-blind "
                 "reader that can see the body is worthless",
            seal_denies=("spec", "plan", "narrative", "body", "provenance",
                         "surrounding_section"),
            seal_allows=("figure_crops", "caption_text"),
            owns=(), also_detects=(),
            owned_kinds=("caption-blind-claim", "caption-blind-evidence",
                         "caption-blind-limitation"),
            reused_kinds=(),
            dimension="reader_reconstruction", hardness="soft",
            panel_label="caption_blind",
            cadence=Cadence(floor=None, read="candidate_lock"),
            runnable_now=False,
            note="the hold-out review surface (his 2026-07-10): give a reviewer ONLY the "
                 "figure + caption; if they cannot name the claim / evidence-type / "
                 "limitation, the surface fails. Packaged-for-F like R5 — needs the "
                 "figure images (a compiled PDF) + a vision model, so it is NOT auto-fired "
                 "every round. Reuses visual_gate figure_crops (the A3/F1F2-corrected "
                 "per-column crop, not re-cut) paired with the caption text ONLY. To fire "
                 "it in a live lock: add 'R9' to dials.loop.lock.readers + a rasteriser "
                 "dispatch branch; verdict rides file+exit-code (verdict_io organ "
                 "'caption_blind'); FAILED figures pour through ledger.pour_finding as "
                 "figure-routed findings into the escalation queue",
        ),
        Reader(
            id="R10", name="Restart", organ="sealed_subagent",
            construct="TWO-PHASE whole-artefact judge. Phase 1 (BLIND): the WHOLE "
                      "rendered-PDF text — not the .tex blueprint — recovered cold "
                      "into {primary contribution; the evidence bearing its weight; "
                      "rhetorical weighting by section; what the conclusion claims was "
                      "achieved; what is deliberately excluded}. Phase 2 (COMPARE): "
                      "that blind recovery set beside the INTENDED OBJECT; every "
                      "disagreement is a mismatch routed to a DRAFT projection-intent "
                      "(RESPINE / RESTART / DEMOTE / REORDER / SPLIT / REOPEN / CUT)",
            seal="two-phase, INVERTED between the phases. Phase 1 is the TOTAL seal — "
                 "denied the intention AND the blueprint: it reads the rendered PDF "
                 "text, never the .tex (reading the blueprint is exactly what the "
                 "whole-artefact grade forbids). Phase 2 is DELIBERATELY un-sealed — "
                 "GIVEN the intended object, because comparing the blind recovery "
                 "against intent IS its function; this seal statement names the "
                 "PHASE-1 seal, and the inversion is documented and proved in "
                 "restart_reader.compare_seal_inverted",
            seal_denies=("spec", "plan", "narrative", "domain", "canon", "substrate",
                         "blueprint", "tex"),
            seal_allows=(),                      # phase 1 allows nothing beyond the rendered page
            owns=("identity-mismatch",), also_detects=(),
            owned_kinds=("identity-mismatch", "emphasis-mismatch",
                         "conclusion-overreach", "exclusion-violated"),
            reused_kinds=(),
            dimension="artefact_integrity", hardness="hard",
            panel_label="restart_reader",
            cadence=Cadence(floor=None, read="candidate_lock"),
            runnable_now=False,
            note="the whole-artefact judgement grade — a blind reader of the COMPLETE "
                 "rendered PDF, GIVEN the intended object, empowered to RESPINE/RESTART: "
                 "the organ the return path was missing (the altitude directive's law — "
                 "a lower-grade judge must never certify a higher-grade property — made "
                 "an organ). DIMENSION artefact_integrity, chosen as the axis of 'the "
                 "object survives as itself': R6 holds its pixel-integrity floor (is the "
                 "artefact physically intact), R10 its identity-integrity apex (is the "
                 "artefact the intended object) — NOT reader_reconstruction, which "
                 "certifies only that a reader CAN rebuild the page (R1/R4/R9, a lower "
                 "grade); R10 assumes recovery succeeds and asks whether what recovered "
                 "MATCHES intent. Reads the rendered PDF via release._discover_final_pdf "
                 "→ pypdfium2 isolated-uv subprocess (poppler fallback), NOT "
                 "graph._gather_manuscript_text (the blueprint the directive forbids). "
                 "VERDICT-ONLY: consequences flow through DRAFT projection-intents "
                 "(draft-only law), never per-node work. Joins the lock tier "
                 "(dials.loop.lock.readers). Packaged-for-F: the orchestrator dispatches "
                 "the two sealed phases with restart_reader.blind_packet / compare_packet "
                 "and banks via restart_reader.bank. The phase-2 seal INVERSION is exempt "
                 "from the intent-sentinel scrub BY CONSTRUCTION: seal scrubs are "
                 "per-reader (each pack calls its own; referee.INTENT_SENTINELS runs ONLY "
                 "inside referee.pack_for_referee_read), so there is no central scrub to "
                 "carve an exception out of — compare_packet simply never invokes it",
        ),
    )
}


# ---------------------------------------------------------------------------
# Silence never reads as pass
# ---------------------------------------------------------------------------

#: A missing or failed reader scores this — neutral, never a clean pass. Mirrors
#: ``convergence.evaluate_round.soft_score`` so the two never drift.
SILENT_SCORE = 0.5


def reader_verdict_score(entry: Optional[dict[str, Any]]) -> float:
    """The reader-level score with the silence floor. ``None`` (reader never ran)
    or a ``failed`` entry → :data:`SILENT_SCORE` (0.5), never clean. A ``clean``
    entry → 1.0. Otherwise 1.0 minus 0.15 per flag, floored at 0.0. This is the
    banked quota-wall lesson stated as a reusable reader helper for Phase F; it
    matches ``evaluate_round`` exactly so a reader panel and the loop agree."""
    if not entry or entry.get("failed"):
        return SILENT_SCORE
    if entry.get("clean"):
        return 1.0
    return max(0.0, 1.0 - 0.15 * len(entry.get("flags") or []))


# ---------------------------------------------------------------------------
# The manifests Phase F consumes
# ---------------------------------------------------------------------------

def roster() -> list[dict[str, Any]]:
    """The full reader roster as plain dicts, in reader order (R1..R10) — the object
    Phase F reads to wire the panel and the candidate-lock tier."""
    return [READERS[rid].as_dict() for rid in sorted(READERS)]


def finding_kinds_manifest() -> list[dict[str, str]]:
    """Every NEW reader-owned finding-kind, fully routed — the Phase-F schema-wiring
    contract (the conjugate of ``visual_gate.routing_manifest``). Phase F sets
    ``schema.KIND_TO_WORK[kind] = work_kind`` for each row; ``WORK_TO_LAYER`` already
    carries ``work_kind → owning_stage``. Reused kinds (R3's C kinds, R6's visual
    kinds) are wired by their own organ's manifest and are NOT repeated here."""
    return [{"kind": rk.kind, "reader": rk.reader, "work_kind": rk.work_kind,
             "owning_stage": rk.owning_stage, "sense": rk.sense}
            for rk in READER_FINDING_KINDS.values()]


def dimension_manifest() -> list[dict[str, str]]:
    """reader → the EXISTING convergence dimension it feeds, its hardness, and the
    suggested project-fixedpoint panel label. Phase F bridges each into
    ``evaluate_round`` (it owns ``convergence.py``); this is the mapping, not the
    edit. No new dimension appears — every ``dimension`` is already in
    ``HARD_DIMENSIONS ∪ SOFT_DIMENSIONS`` (or the terminal ``author_acceptance``)."""
    return [{"reader": r.id, "name": r.name, "dimension": r.dimension,
             "hardness": r.hardness, "panel_label": r.panel_label,
             "cadence_floor": r.cadence.floor or "", "cadence_read": r.cadence.read or ""}
            for r in (READERS[rid] for rid in sorted(READERS))]


def owned_hard_failures() -> dict[str, str]:
    """hard-failure id → its single owning reader (the non-redundancy table)."""
    return {hf.id: hf.owner for hf in HARD_FAILURES.values()}


# ---------------------------------------------------------------------------
# The two invariants, as checks (builder ≠ judge — these verify the DECLARATION)
# ---------------------------------------------------------------------------

def verify_single_ownership() -> dict[str, Any]:
    """Invariant (ii): exactly one reader owns each of the 13 hard-failures, and
    every reader's ``owns`` tuple refers to a real hard-failure whose ``owner`` is
    that reader. Returns ``{ok, n_failures, violations}``."""
    violations: list[str] = []
    # every hard-failure has exactly one owner, and that owner is a real reader
    owners: dict[str, list[str]] = {}
    for hf in HARD_FAILURES.values():
        owners.setdefault(hf.id, []).append(hf.owner)
        if hf.owner not in READERS:
            violations.append(f"{hf.id}: owner {hf.owner!r} is not a reader")
    for hid, os_ in owners.items():
        if len(os_) != 1:
            violations.append(f"{hid}: {len(os_)} owners {os_}")
    # every reader's declared `owns` round-trips to a hard-failure it owns
    for r in READERS.values():
        for hid in r.owns:
            hf = HARD_FAILURES.get(hid)
            if hf is None:
                violations.append(f"{r.id} claims unknown failure {hid!r}")
            elif hf.owner != r.id:
                violations.append(f"{r.id} claims {hid!r} but owner is {hf.owner}")
    return {"ok": not violations, "n_failures": len(HARD_FAILURES),
            "violations": violations}


def verify_kind_partition() -> dict[str, Any]:
    """The real anti-double-count: every reader-owned finding-kind maps to exactly
    one reader, and each reader's ``owned_kinds`` all resolve to it. Reused kinds
    (owned by another organ) are excluded by construction. Returns
    ``{ok, n_kinds, violations}``."""
    violations: list[str] = []
    kind_owner: dict[str, list[str]] = {}
    for rk in READER_FINDING_KINDS.values():
        kind_owner.setdefault(rk.kind, []).append(rk.reader)
    for k, rs in kind_owner.items():
        if len(rs) != 1:
            violations.append(f"kind {k!r}: {len(rs)} owners {rs}")
    for r in READERS.values():
        for k in r.owned_kinds:
            rk = READER_FINDING_KINDS.get(k)
            if rk is None:
                violations.append(f"{r.id} owns unregistered kind {k!r}")
            elif rk.reader != r.id:
                violations.append(f"{r.id} owns {k!r} but manifest says {rk.reader}")
    # reused kinds must NOT appear as reader-owned kinds (they're owned elsewhere)
    for r in READERS.values():
        for k in r.reused_kinds:
            if k in READER_FINDING_KINDS and READER_FINDING_KINDS[k].reader != r.id:
                violations.append(f"{r.id} reuses {k!r} which is reader-owned by "
                                  f"{READER_FINDING_KINDS[k].reader}")
    return {"ok": not violations, "n_kinds": len(READER_FINDING_KINDS),
            "violations": violations}


def reader_finding(reader_id: str, where: str, issue: str, fix: Optional[str],
                   kind: str, quote: Optional[str] = None) -> dict[str, Any]:
    """One reader finding in the standard shape ``{where, issue, fix, kind}`` plus
    the routed ``owning_stage``, the ``reader`` id, and its ``dimension`` — stamped
    from the roster so a caller never re-derives the route. Unknown kinds keep the
    reader's dimension but route ``prose`` (a conservative default), never crash."""
    rk = READER_FINDING_KINDS.get(kind)
    stage = rk.owning_stage if rk else "prose"
    rec: dict[str, Any] = {"where": where}
    if quote:
        rec["quote"] = quote[:240]
    rec.update({"issue": issue, "fix": fix, "kind": kind,
                "reader": reader_id, "owning_stage": stage,
                "dimension": READERS[reader_id].dimension if reader_id in READERS else ""})
    return rec
