---
name: welder
description: "The final stage of manuscript projection: a single GLOBAL pass over the already-assembled, content-locked draft that leaves no seam. The projector works node-by-node, and a node can only narrate its OWN role, so each section announces the trellis it was grown on - 'in this section we show X', the descent map printed as prose about the paper. No node can see the whole, so no node can dissolve the announcement; only a global pass can. The welder smooths the rhetorical surface so the structure is FELT through the prose, never declared: it replaces every sentence that announces a property with prose that exhibits it, until the artefact is isomorphic to its core idea. It never touches substance - not one claim, citation, equation, figure, or epistemic status. The weld is judged from outside by blind_reader: no seam, the construction cannot be reverse-engineered from the page."
consistency:
  - canon://engine/operatorial_self.md | supports | the weld is the OUTERMOST scale of the friction-as-loss tower - buffing the artefact↔kernel residual to zero; no seam = zero residual = closed loop, and the first-exercise SEAMED verdict is a residual the first descent step could not reach
  - canon://workflow/manuscript_projection.md | supports | the welder is the FINAL stage of the projection loop - it runs after node-by-node projection, before the artefact is judged; manuscript_projection wires it in as that stage
  - canon://workflow/object_not_artefact.md | supports | the welder is the COMPLETION of that law - object_not_artefact removes leaked labels, the welder removes leaked narrative/scaffolding; the residue a global-only pass can reach
  - canon://workflow/generation_discipline.md | supports | the no-seam / embody-don't-announce principle is the generation-discipline invariant the welder enforces on the projected artefact; builder != judge sends the weld to an out-of-loop reader
  - canon://skills/blind_reader.md | depends_on | the welder never certifies its own weld - the seam is exactly what a cold reader would spy, so blind_reader is the out-of-loop judge of no-seam
  - canon://aesthetics/earned_simplicity.md | supports | the welder serves earned simplicity - embody-don't-announce is its mechanism; meta-narration is one of its named false-simplicity forms, dissolved here at global scale
---
# welder

Forged 2026-06-05 by the meta-dreamer from the
author's diagnosis: *meta-instructions still leak into the draft.* A projected
manuscript announces its own structure - "we look at X because Y", per-section
scaffolding sentences, the form's demands manifesting as prose *about* the paper
instead of *as* the paper.

## Why this exists - the node-local leak only a global pass can close

The [projector](canon://workflow/manuscript_projection.md) works **node-by-node**.
Each section is an inner loop that closes one primitive, and a node can only
describe its **own** role - so each section narrates the trellis it was grown on:
"in this section we show…", "we look at X because the argument requires…", "having
postulated, we now derive". No node can see the whole, so **no node can dissolve
the announcement**. The structure-narrative is correct information sitting in the
wrong place: a meta-instruction that, lacking a global home, leaks into the local
prose as a self-assertion.

This is the residue [`object_not_artefact`](canon://workflow/object_not_artefact.md)
cannot reach. That law removes leaked **labels** - the `[POSTULATE]` tag, the build
rule printed on a card, the sentence whose only content is the rule that generated
it. The welder removes leaked **narrative** - the *scaffolding*, the roadmap
declared per-section, the form's demand-list audible as prose. The label leak is
local and a node can scrub its own; the narrative leak is **global** - it is only
visible, and only removable, with the whole draft in one view. The welder is
[`object_not_artefact`](canon://workflow/object_not_artefact.md)'s completion: the
final firewall, run once, over the assembled whole.

It is the last stage of the projection loop, after the
[core-outward trunk](canon://workflow/core_outward_trunk.md) has grown the draft and
every [form-demand](canon://workflow/manuscript_projection.md) is met - and **before**
the artefact is judged. The draft it receives is already **form-compliant and
content-locked**; the welder operates only on the rhetorical surface over it.

## The two modes (his 2026-07-09 re-scope: neutral first, voice last)

The weld is not one pass. `compile_weld_dispatch(project, voice_on=...)` compiles two:

- **Neutral weld** (`voice_on=False`, the default). The structural work only - de-seam the
  fragments, keep the narrator classes absent, fix the provenance markers, in a clear NEUTRAL
  register. This is part of **neutral completion**: a draft is finished without it having ever
  been voiced.
- **Voice wash** (`voice_on=True`). The final, optional layer that rewrites the whole in his voice,
  grounded in retrieved exemplars (move 4). It is accepted **only if it dominates the neutral
  surface**: `convergence.voice_dominates_neutral` inside `candidate_lock.accept_or_restore`
  requires improvement on a soft dimension, degradation on none, and none of the five prohibitions
  (adds content, increases reader effort, repeats ideas, makes the authorial presence more
  conspicuous than the reasoning, weakens clarity). Voice is not better for being more authored -
  it carries the burden of proof, and a wash that fails it is discarded for the neutral surface.

And in both modes the weld **writes**; it does not smooth. The fragments are content, the
substance-freeze holds, and the output is new prose over a locked draft.

## The four moves

1. **Meta-narrative placement.** The structural / roadmap narrative - "what this
   paper does", the descent map, the ordered promise of the inner loops - appears
   **only** in its appropriate place: the framing rings (abstract, introduction,
   conclusion). Everywhere else the structure is *felt through the prose*, never
   declared. Per-section scaffolding ("in this section we show…", "we look at X
   because the argument requires…", "having established the setup, we turn to…") is
   removed. The roadmap is promised once, at the top, where it has a home; the body
   keeps it by *being* the loops it promised, not by announcing each one as it opens.

2. **Dissolve announcement into embodiment.** Replace every sentence that
   *announces* a property with prose that *exhibits* it. "This section motivates X"
   becomes an actually-motivating opening sentence. "We postulate first then derive"
   becomes: simply lead with the postulate and let the derivation follow. "This
   figure shows the trade-off" becomes a caption that makes the trade-off legible.
   The meta-instruction goes invisible because **the draft now does the thing
   instead of saying it does**. The motive survives - it is moved from a *statement
   about* the section into the *opening of* the section (the
   [earned-simplicity](canon://aesthetics/earned_simplicity.md) "open on the motive"
   move, run at the seam where the projector left a label).

3. **The deepest form - the draft EXHIBITS the property it claims to make.** A paper
   about earned simplicity reads simply; a paper about "one commutator, four faces"
   reads as one thing, not four announcements. The artefact becomes **isomorphic to
   its core idea** - the outer ring a seamless external representation of the
   believed core it was grown from. This is the author's ring frame, *there is only
   one thing*: the core is a belief, every ring outward is its growth, and the
   finished object **is the core made external**. The welder is the pass that closes
   the outermost ring onto that core - it makes the artefact's *form* obey the claim
   its *content* makes, so the reader meets the idea by the shape of the page, not
   only by its sentences.

4. **Global smoothing - one register.** Cross-section transitions are made to flow;
   notation and register are made consistent across the seams of independently
   composed faces; repeated structure-announcements are collapsed. The assembled
   pieces become **one grown whole**, not an assembly of node-projections. The
   register standard at this pass is his **retrieved prose** (Phase I2): for each
   `% <sid>-pN` paragraph of the neutral draft the dispatch fences the nearest
   passages of his real writing as a per-paragraph `RETRIEVED-EXEMPLARS` channel,
   built by `laplace.pipeline.voice_retrieval` over the sealed store, so the pass
   writes FROM his prose. `profiles/voice/gerard-technical-v1.md` is demoted to thin
   register orientation - by `voice_descent`'s law a description of a generator does
   not generate. FAIL LOUD: with the exemplar store unavailable the pass ships
   neutral (`neutral_fallback`) or errors; it never degrades to a spec-driven "sound
   like him" pass. Discharged at the only scale where a seam between two nodes is
   visible: the global one.

## The test - no seam (judged from outside)

The welder's success criterion: **no seam**. A blind reader cannot reverse-engineer
the construction - the node structure, the form's demand-list, the build process -
from the finished artefact. *The point of closing the loop is that there is no seam
through which the construction can be spied.*

The seam is exactly what a cold reader would spy, and the welder **never certifies
its own weld**. Builder != judge
([`generation_discipline`](canon://workflow/generation_discipline.md) §2(c)): the
welder smooths; whether the weld holds is judged from **outside** its context by
[`blind_reader`](canon://skills/blind_reader.md), the seam-spy. The blind reader
already reports leaked meta-prose and every unmotivated section; the welder's pass
is graded by exactly that read - extended with one question the cold reader is asked
to answer: *from the page alone, can you reconstruct the section list, the build
order, or the form's checklist?* If yes, a seam survived. The welder's own sense
that the draft now flows is read through the context that wrote it and cannot judge
its own no-seam any more than a drafter can judge its own clarity.

## The hard guardrail - the welder never touches substance (invariant)

The welder dissolves scaffolding and smooths voice; it operates **only on the
rhetorical surface** - the announcement-vs-embodiment layer - over a draft that is
already form-compliant and content-locked. It **must not**:

- add, drop, or alter a **claim**;
- add, drop, or alter a **citation** (`\citep`) or an internal **`\ref`**;
- add, drop, or alter an **equation** or a **figure**;
- change an **epistemic status** - never launder a postulate into an established
  result, nor soften an established result into a hedge.

It may not introduce a **naked claim**: every claim stays grounded in a `\citep` or
an internal `\ref` exactly as the projector left it
([Ring II D-no-naked-claims](canon://workflow/manuscript_projection.md)). Moving the
motive from an announcement into an embodying sentence must carry the same grounding
with it - the embodiment cites what the announcement cited.

If a smoothing would **require** changing substance, that is a **friction to
report**, not a licence to edit content. The welder emits it as a typed friction
under the shared discipline
([`generation_discipline`](canon://workflow/generation_discipline.md) §2): a
**TENSION** when the form's no-seam demand and a content commitment each cohere yet
disagree (the only way to dissolve this announcement is to drop a claim), a
**CONTENT** friction when the seam exists because a content node is thin (a section
with no real motive can only announce one), surfaced and routed to the content
conceptric, never silently resolved by editing the prose.

## When to run it

The **last** pass before an artefact meant for a reader who was not in the room goes
out - after the trunk is drafted and every form-demand met, after the
[`blind_reader`](canon://skills/blind_reader.md) floor and the always-on detector
floor (`verify.check_voice` + `verify.check_meta_leak`) are cleared, as the global
finish that the node-by-node build structurally could not apply. Not for internal
notes or the canon itself, whose readers share the context the seam would betray.
The trigger is **an assembled, content-locked draft that still narrates its own
construction**.

## Invariants

- **Global-only.** The welder runs **once, over the whole assembled draft**. Its
  defect - the per-section announcement - is invisible node-by-node; a per-node pass
  cannot be the welder. If it ran inside a node it would be the projector again.
- **Surface, never substance.** It touches only the announcement-vs-embodiment
  layer. Not one claim, citation, equation, figure, or epistemic status moves. A
  smoothing that needs substance to change is a friction, not an edit.
- **Embody, don't announce.** Every sentence that *states* a property is replaced by
  prose that *exhibits* it; the motive is moved, never deleted. The structure is
  felt, not declared - declared only in the framing rings where it has a home.
- **Isomorphic to the core.** The finished artefact's form obeys the claim its
  content makes - the outer ring a seamless external face of the core it grew from.
- **No seam, judged from outside.** Success is that the construction cannot be
  reverse-engineered from the page. The welder never certifies its own weld;
  [`blind_reader`](canon://skills/blind_reader.md) is the out-of-loop judge, asked
  the seam question. The welder's own sense of flow is not the verdict.

## Pairing

The completion of [`object_not_artefact`](canon://workflow/object_not_artefact.md)
(labels removed locally; narrative removed globally) and the final stage of
[`manuscript_projection`](canon://workflow/manuscript_projection.md) (after the
node-by-node projection, before the judge). Serves
[`earned_simplicity`](canon://aesthetics/earned_simplicity.md) (embody-don't-announce
is its mechanism; meta-narration is the false-simplicity form dissolved here).
Judged by [`blind_reader`](canon://skills/blind_reader.md), the seam-spy,
under the builder != judge law of
[`generation_discipline`](canon://workflow/generation_discipline.md). In the pipeline the weld is
one member of the dial-gated **generating-loop family** (neutral weld / voice wash / de-scaffold
final layer / child-kind projection / the designed slides kind); the family table — one acceptance
law per member — lives in `PIPELINE_GUIDE.md` §9.

*Experimental and coarse by design. Refine when a real out-of-loop read teaches a
sharper line between a scaffolding sentence the welder should dissolve and a genuine
signpost the reader needs - or when the seam test wants its own backing pre-pass
(an extension of `scripts/blind_read.py` that flags reconstructable structure, not
only leaked meta). Whether a given weld is GOOD is the author's verdict, read
through the blind reader; the welder builds and does not self-certify.*

## First exercise (2026-06-05) — what the full recursion taught

The welder's first real pass (on the v9 manuscript, contextualised by its generating
conceptric) **worked as a mechanism** — verified from outside: it dissolved 16+
announce-the-move openers to zero while every citation, `\ref`, numeric, equation, and
`\textsc{}` tier survived byte-identical (the substance guardrail held), and it still
compiled. But the blind seam-judge graded the result **SEAMED**: one pass with this
discipline did not reach no-seam. Two findings, banked:

1. **The residual seam the first pass missed is the epistemic-tier refrain.** Nearly
   every section closes by *stamping* its tier ("The result is ESTABLISHED.", "we carry
   it as POSTULATE"), so the intro's status checklist is visibly ticked section by
   section — the sharpest reconstructable scaffold. The welder left it because dissolving
   a status *word* felt like touching status (the guardrail). **The convergence:** the
   welder's own FORM friction (a tier rides in a descriptor) and the blind judge's verdict
   (the tier-stamp is the seam) point at the same place independently.
2. **The deep tension this surfaces — the author's fork, the refinement phase's seed.**
   *Honest-status-shell-by-shell* (the form's consistency demand) collides with *no-seam*:
   stamping the tier is honest **and** a seam. The candidate resolution is the welder's own
   principle applied to status itself — **embody the tier in the register, do not stamp it**
   (an established result reads asserted-and-grounded; a postulate reads hedged — "we
   propose", "if the mapping holds"; the reader feels the tier without a rubric). This
   redraws the surface/substance line for the welder (the tier *information* is substance and
   must survive; the tier *stamp* is surface and may dissolve) — an architecture call reserved
   to the author. Also clearly-dissolvable and missed by pass 1 (no tension, safe next pass):
   the "Three points of discipline / First…Second…Third" enumerations, role-narration ("this
   is the pivot, not a weakness"), the twice-stated "a theory not a list" meta-commentary, and
   an over-complete `\ref`-list roadmap. **A second pass converges; reaching seamless on the
   status refrain waits on the fork.**
