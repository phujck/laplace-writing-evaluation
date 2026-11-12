---
name: visual_director
description: "The talk's staging owner - the peer of latex_forge. Once the narrative and each slide's function are locked, propose for each slide what to create: substrate-decides-theme, reuse the manuscript figure, embed-vs-bake, one idea per slide - then scaffold the slides and drive the build."
---
# visual_director

## Purpose
The talks-domain twin of [`latex_forge`](canon://skills/latex_forge.md): the Trunk-stage owner for a talk. It runs **after** [`script_editor`](canon://skills/script_editor.md) has locked the spine - the narrative and each beat's function are settled - and proposes, per slide, what to *create*. It fills the `slide_builder` slot named in the [talks axioms](canon://domains/talks/axioms.md), and it inherits the [Slide Design Guide](canon://domains/talks/projects/talk_from_manuscript.md) as its craft.

The drafting gate, exactly as for the manuscript: build a slide **only from a locked beat** whose function is decided. A slide that asserts beyond its beat, or invents a figure the manuscript does not have, is a defect.

## The craft (from the slide design guide)
- **Substrate decides the theme.** A deck is dark when its assets are dark (manim on black), paper-light when its assets are light (REVTeX figures on white). Do not pick a theme by taste and fight the assets into it - this is the highest-leverage staging choice.
- **Reuse the figure, do not recolour it.** Manuscript figures are the talk's figures; the slide's accent colour matches the figure's own data colour. A talk-only variant is derived from the original, never invented.
- **Render order is reveal order.** Vital information last - the punchline equation is the final reveal, not the first. Reserve space before placing.
- **Embed vs bake, per asset.** Bake a finished non-interactive asset (a manuscript figure, a rendered manim clip); embed live when the value *is* interactivity (an explorable phase portrait). The decision is per asset, never per talk.
- **One idea per slide.** A slide carrying two ideas carries neither. KaTeX traps: inline maths dies in raw HTML, captions carrying maths must be markdown siblings, display maths breaks at natural operators.
- **Slidev figures embed, they do not inline SVG.** MDC / Slidev strips `class` and `style` off raw inline `<svg>` tags at parse time, so a hand-tuned inline figure loses its styling silently in the browser and only surfaces broken on export. Serve figures as tiny standalone HTML files via `<Embed>` so the figure's own stylesheet ships with it. Verify by `slidev export` PNG, never eyeballed in the dev pane.

## The pass
For each locked beat, surface the decisions (author picks): the slide's **function** (intro / equation build / figure / result / recap), the **substrate**, and the **asset** (reuse-figure / bake / embed / new schematic). Then scaffold `slides/sNN-*.md` with the function, the message, the placed equation/figure, and the timing - and drive the build with `slidev build` or the per-talk build script (the pattern is `synthetics papers/feedback-twinning-fields/talk/build_deck.mjs`). Inspect the rendered slide (not just a screenshot - confirm KaTeX hydrated and figures are legible at projection size), then iterate.

**This is a hand-run deck, not a pipeline leg.** The slides kind is DESIGNED, NOT BUILT
(`PIPELINE_GUIDE.md` §9): nothing in `registry.py` or `dials.py` implements it, so there is no
registry gate, no state machine and no release bundle behind a talk. The design is
`DESIGN_2026-07-11_talk-slides-kind.md`; cite it as a design, never as a running stage.

## Hand down live assets to deck_applet
When the asset call is **embed a live/interactive thing** (an explorable phase portrait, a stepped derivation, a settling field, generated title art), the build goes down to [`deck_applet`](canon://skills/deck_applet.md) - do not hand-clone the harness. That bench carries the no-scroll fill-parent shell, the 2x-DPR crisp canvas + device-pixel text helper, the ResizeObserver re-fit, the host-inherited dark palette, the two interaction patterns (discrete stepper / continuous knob with talk presets), and the parametrised `verify-*.mjs` render check. A baked or static asset stays with you / [`figure_standard`](canon://skills/figure_standard.md). The embed-vs-bake call is yours; the live build is `deck_applet`'s.

## The voice runs to the chrome
The slide's words carry the register too - titles, captions, and applet control-strip text included. The register data is `profiles/voice/gerard-technical-v1.md` (thin orientation only; the generating standard is his retrieved prose). No gnomic subtitle, no gloss narrating an asset, no antithetical "X not Y" title, no padding caption ("click a face", "autoplay cycles"). A title is a title; generated art needs no caption. Strip the instructional and filler text to the minimum that reminds the speaker or orients the audience.

## Invariants
- **Narrative first.** Do not propose visuals before `script_editor` has locked the beat and its function.
- **Substrate decides the theme.** Never impose a theme the assets fight.
- **Reuse the figure.** The manuscript's figures are the talk's; derive variants, never invent.
- **One idea per slide.** Reveal order is render order - the payoff lands last.
- **Trace to the manuscript.** Every slide's content traces to a beat, which traces to the paper.

## Backing
None. `build_slide_meta.py` and `iterate.py` were named here but have never existed in this repo
(`git log --all --diff-filter=A` finds no commit that added either). What exists is `slidev build`
plus a per-talk build script written for the deck at hand - the pattern is
`synthetics papers/feedback-twinning-fields/talk/build_deck.mjs`. Forge a real backing by doing:
lift the slide-design-guide rules into one once they prove on a second deck (the
[talks project](canon://domains/talks/projects/talk_from_manuscript.md) holds the live state). The
judgement - function, substrate, asset per slide - stays here regardless.
