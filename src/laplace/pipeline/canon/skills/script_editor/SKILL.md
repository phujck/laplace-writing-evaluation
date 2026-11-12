---
name: script_editor
description: "[EXPERIMENTAL] The talk's elicitation engine - the peer of manuscript_spine. Discover the talk by interrogating the author: a sequence of decisions (central idea, entry frame, acts, per-beat idea/intent/provenance) that assembles the talk spine, each beat traced to a manuscript result or figure, so slide-building becomes mechanical."
---
# script_editor

**Status: [EXPERIMENTAL]**

## Purpose
The talks-domain twin of [`manuscript_spine`](canon://skills/manuscript_spine.md). The manuscript is to `manuscript_spine` as the talk is to `script_editor`: it does not write the talk, it *discovers the narrative* by asking. It fills the `talk_spine_generator` slot named in the [talks axioms](canon://domains/talks/axioms.md), and it owns the **spine before the slides** - the ordered beats and what each must land, settled before any artifact is built. In the [`talk_smith`](canon://skills/talk_smith.md) pipeline it owns stages 1-3: primitives, motivation recovery, and the storyboard.

**The manuscript is the source of truth.** A talk derives from a compiled manuscript and never asserts beyond it - every beat traces to a result, figure, or statement already in the paper (see [talks axioms](canon://domains/talks/axioms.md)). The talk medium is freer than the paper: direct address, a spoken aside, a slide that is mostly one figure. Project the voice, do not flatten it.

**Provenance is necessary, not sufficient - recover the motivation between results.** A beat that traces to a result still fails if it asserts that result without its origin. When the source is a results-list or a build record rather than a finished paper, the connective argument a paper would carry is missing, and the spine must recover it: for each beat, **why this step, and how it captures the essentials**, not just which result it points to. This is the deepest lesson of the first real talk - a draft built straight from results stated its equations as given and never showed where they came from (a self-consistency argument, the jump to renormalisation - both unmotivated). Decompress the results into a motivated spine (the proven artifact is a `DERIVATION_SPINE.md`) and settle it with the author for anything that is his physics: scaffold it, never invent it. The test of a beat is "does the audience see where it comes from", not "does it trace".

**The author decides; you surface the decisions** - `AskUserQuestion` on Claude, a numbered options list on Codex / Gemini.

## The spine (a beat list, the proven format)
The spine lives at `talk/spine.md` in the project. Each beat:

```
## Beat <n> - <title>
**One idea:** <the single thing this beat lands>
**Speaker intent:** <why it matters - register, structural function>
**Provenance:** <SETTLED|PROVISIONAL> - <manuscript result Rk / section>; <figure label>
**Motivation:** <why this step, and how it captures the essentials - the bridge from the previous beat; SETTLED only once the author confirms anything that is his physics>
<the spoken prose, optional>
```

Plus a running-order table (Beat | topic | minutes) that owns timing separately, and a consolidated PROVISIONAL ledger at the foot. SETTLED = manuscript-backed; PROVISIONAL = borrowed/unverified, flagged for confirmation before delivery.

## The question ladder (same shape as the manuscript, at talk scale)
1. **The one idea + audience + slot.** What single thing must the talk prove? Who is the audience, how long is the slot?
2. **The entry frame.** How does it open - the hook before the model appears?
3. **The acts.** Two or three acts; their names; the arc.
4. **The beats, in order.** For each: the one idea, the speaker intent, the provenance (which manuscript result/figure backs it, at what status), **and the motivation** - why this step and how it captures the essentials, the connective argument between results. One idea per beat. A beat with provenance but no motivation is incomplete.
5. **The running order + timing.** Minutes per beat; what trims if the slot is tight.

Surface one decision at a time; after each answer write the beat to `spine.md`. The spine is a graph too (beats -> claims -> figures), so the same [viewer](canon://skills/manuscript_spine.md) renders it - the author watches the talk assemble and steers it, exactly as for the manuscript.

## Hand-off
Once the narrative and each beat's function are locked, hand to [`visual_director`](canon://skills/visual_director.md), which proposes what to *create* for each slide. The spine before the slides - the arc is the work, the slides are its projection.

## Invariants
- **The manuscript is the source of truth.** Every beat traces to a manuscript result, figure, or statement. A talk that asserts beyond its paper is a defect, not a teaser.
- **Provenance is necessary, not sufficient.** Every beat also carries its motivation - why this step, how it captures the essentials. A beat that traces but does not show where it comes from is incomplete.
- **Spine before slides.** Settle the ordered beats and what each lands before any artifact.
- **One idea per beat.** Compression is the discipline.
- **Ask, do not assert.** The narrative is the author's; you surface the decisions. Scaffold motivation, never invent the physics.
- **Project the voice.** Use the freer medium's latitude rather than retreating to a bullet summary.

## Backing
Forge-by-doing on the next real manuscript-to-talk build, not before (the [talks project](canon://domains/talks/projects/talk_from_manuscript.md) holds the live state). A natural backing reads a compiled manuscript and proposes a beat skeleton with provenance back to manuscript labels, which the author then sharpens by answering.
