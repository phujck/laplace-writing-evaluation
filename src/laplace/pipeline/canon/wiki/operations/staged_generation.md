# Staged generation — compile the manuscript before rendering its prose

The 2026-07-09 rebuild (mandate: `DESIGN_2026-07-09_manuscript-generation-rebuild-mandate.md`,
banked at repo root; his correction: the mandate is a guide — these stages are
recovered INSIDE the existing machinery, not imposed beside it). The governing
principle: **the manuscript exists completely as semantic and narrative
specification before any prose does.** Prose is the last stage allowed a
generative choice; LaTeX is a constrained backend.

## The stages and their artifacts

| Stage | Artifact | Producer / validator |
|---|---|---|
| A research state | the conceptric (L1 friction ledger → nodes; the seven gates) | unchanged — [two-ledger system](canon://operations/two_ledger_system) |
| B projection spec | `manuscript_spec.json`: the §5.1 global record (purpose, scope, non-claims, reader, genre, notation + terminology), figure/table SPECS with settled captions, equation-ledger role overlays. Strict `0.2` terminology entries state the topic-preferred term, its home field, cross-literature alternatives, and whether it is field-standard, inherited from prior literature, or coined here; a new coinage must name the novel concept and the construction shown before the name appears | `pipeline.projection_spec` (`validate_spec`, §11.1) |
| C structural resolution | `section_contracts.json` (function, question, reader entry/exit states) + derived `reader_state.json` | `pipeline.structural` (`gate`, §6.3 — red closes every later stage) |
| D narrative spec | `narrative/<sid>.json` — paragraph plans (function, proposition, inputs, anchors, qualification, connections) | `pipeline.narrative` (`validate_narrative`, §7.2) |
| E prose realisation | section fragments + `prose_provenance/<sid>.json` | the prose dispatch ([briefs_and_dispatch](canon://operations/briefs_and_dispatch)); `document_model.validate_fidelity` (§11.4) + `verify.check_voice` (§11.5) + `meta_leak` |
| F document model | `document_model.json` — derived typed view in true `\input` order | `pipeline.document_model` |
| G LaTeX backend | `main.tex` + `figures_tex/*.tex`, assembled under `profiles/typography/` | `pipeline.tex_backend` (deterministic; `scripts/render_manuscript.py`) |

Each stage adds one kind of information; no stage silently redoes an earlier
stage's work; a stage's gate must pass before the next stage runs.

## Where voice lives

In exactly two seats: the compiled prose dispatch (the ONE compiler joins the
versioned profile `profiles/voice/gerard-technical-v1.md` into the realiser's
context) and the weld pass. Never in plans, briefs, contracts, narrative
specs, judges other than the voice evaluator, or reply behaviour. The profile
is versioned independently (§14): swapping it re-renders language and nothing
else. The negative space is a DETECTOR (`schema.VOICE_FAILURE_PATTERNS`,
§11.5), never a generation instruction — a blacklist in a prompt breeds
synonyms (§1.10); a detector at the boundary routes a flag to its owning
stage.

## Sequencing law (his, 2026-07-09)

Voice comes last, at the final leg (prose realiser + weld). Iteration and
judgement come after the first weld. `project-fixedpoint` fires only after
the first weld. Feedback returns upstream: new nodes make new demands on
sections; prose is re-rendered from the same specification, never repaired
rhetorically downstream (`schema.WORK_TO_LAYER` — mandate §12).

## The weld (his re-scope, 2026-07-09, after reading the first fragments)

The weld is not smoothing. Per-section realisers — even clean-context ones —
write under rule pressure and perform the rules: the narrator re-emerges with
fresh words (§1.10 live; the five extension classes in
`schema.VOICE_FAILURE_PATTERNS` are his read of the first staged fragments).
So the weld is THE ONE WRITER: the whole assembled object rewritten as one
voice. Inputs, joined by the one compiler
(`dispatch.compile_weld_dispatch`): the fragments as settled content, the
voice profile as who writes, the detector report as the classes that must
simply not exist in the rewrite, and the substance freeze (every claim,
displayed equation + label, cite key, ref, marker line, section order —
untouchable; a substantive doubt returns as a typed issue). A fresh instance
runs the weld — a long-context session marinated in engine register is the
wrong writer. Acceptance for the FIRST weld: a blind reader follows the paper
front to back; every fragment's detector count is zero; fidelity §11.4 still
passes (content preserved through the rewrite).

## Judging (designed 2026-07-09; runs only after the first weld)

The judge panel is `project-fixedpoint`'s Converge loop, re-aimed at the
profile: the VOICE judge carries the profile's own §20 evaluation questions
plus the Part B final test ("would the author actually LEAVE this sentence
in") and the full failure-pattern catalogue; closure/caption/claims/calc
judges are unchanged; the mechanical floor (meta_leak + the extended
detector) runs before any judge tokens. Every flag lands through the one
feedback door typed by kind, and
[propagate](canon://operations/pipeline_operators) routes it to its owning
stage (`schema.KIND_TO_WORK` / `WORK_TO_LAYER`): a voice flag re-renders
prose from the SAME narrative spec or revises the PROFILE (the author's
fork) — never an instruction appended to any prompt. Convergence = a round
with zero flags and no failed judge.

## The loop

`storyboard.rebuild` (headless, token-free) → `dispatches/dispatch_manifest.json`
→ the `project-staged` workflow (planners → realisers → mechanical validation
→ THE WELD, compiled by `compile_weld_dispatch`) → first-weld acceptance →
judgement: `project-fixedpoint` convergence under the profile-aimed panel →
[propagate](canon://operations/pipeline_operators) routes every flag to its
owning stage through the one feedback door.
