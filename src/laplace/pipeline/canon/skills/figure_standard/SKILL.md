---
name: figure_standard
description: The house style for data figures, as render-order discipline. The same voice projected into the figure medium - a correct plot that does not carry the mark still fails. Compute placement from the data, render vital information on top, never let furniture collide with meaning.
---

# Figure Standard

A figure is the voice in a non-prose medium (see [Visual Aesthetics](canon://aesthetics/visual_mechanics.md)). The physics can be right and the figure still fail - if a gridline crosses a label, if an inset lands on the curve, if a number floats free of the thing it measures. This skill is that failure mode stated as a discipline, settled live with the author against his standing peeve: a non-important element drawn over vital information, above all text colliding with a graphic.

State it positively. "Do not overlap" gives no guidance. "Vital information renders on top, and every element's place is computed from the data" does.

## Shared author design context

The current author-owned design guidance is the `design_guidance` object in
`profiles/visual_style.json`. The app's `visuals` detail owner returns it with the
shared house style (the compact index omits it), so figure planning, production
and review consume the same guidance.
Apply that context together with the render and provenance rules below. A project
may choose dimensions suited to its manuscript; retain the shared guidance rather
than replacing it with an isolated project-only preference.

## The settled forks

- **Frame and ticks.** Despined - drop the top and right spines. Ticks inward.
- **Grid off by default.** A grid earns its place only when the reader's job is to read values off the plot. On a structural figure - a slope, a trend, anything carrying labels or insets over it - the grid is background texture competing with the meaning-bearing elements, so it stays off. When a value does need reading, turn it on, always below the data (`set_axisbelow`). Prefer a single reference line at a meaningful value (an axis-zero crossing) over a full grid.
- **Legend is conditional on geometry.** Direct labels on curves when they are spatially distinct, degrading to a colourbar for a family or ensemble. A discrete legend box when curves overlay or cross - a label at the end is ambiguous then. When exact markers sit *on* a fitted line because their coincidence is the result, a legend is correct, not direct labels.
- **Panel labels.** Bold lowercase `(a)`, exterior top-left.
- **Hero intent is per figure.** A mechanism schematic and a result plot want different framing. Decide which a figure is before building it.
- **Caption epistemic status.** The caption tells the reader which mode the figure is in. A schematic caption states what the figure *illustrates* (postulated structure, method, argument); a data caption states what the figure *shows* (measurement, sweep, computed quantity). A schematic captioned as data confabulates measurement; a data plot captioned as illustration launders evidence. Which mode the figure is in must be visible from the caption alone.
- **No titles inside the plot.** Figures land in artefacts with a `\caption{}` beside them. A title text embedded in the plot area competes with that caption, duplicates it inconsistently, and drifts as the caption is edited. Every claim the figure carries lives in the caption, not in a `plt.title()` or `\node` inside the drawing. Panel labels `(a)(b)` remain; a figure-wide title does not.
- **No internal cross-references baked into the figure.** A note like *"F4 splits these"* inside the schematic is a `\ref{}` leaked as prose — it belongs to the LaTeX cross-reference system, not to the figure's pixel content. When the section order changes, or the figure moves, the baked reference is silently wrong; when it's a `\ref`, the counter tracks. All inter-figure references travel through `\ref{fig:...}` in the caption or body prose. This is [`object_not_artefact`](canon://workflow/object_not_artefact.md) applied to the figure surface.
- **Vector-first delivery.** The manuscript asset is vector (PDF from `tikz-standalone`, or PGF/PostScript from a Python generator). Raster PNG is a preview for eyeballing, never the shipable artefact. A figure delivered as PNG at any DPI carries pixel edges the reader sees; the same figure emitted as PDF is resolution-independent and matches the surrounding CM serif exactly. Preview PNGs may live in the repo alongside the source, but the manuscript's `\includegraphics` must point at the vector emit.
- **Adopted silently (best practice, not peeves).** viridis/cividis continuous, Okabe-Ito categorical. Vector line art (PDF/EPS), raster at 600dpi or more. Match the body face (CM serif via usetex for REVTeX). 6pt floor, 7-8pt target. Exact column-width sizing (APS 8.6cm single, 17.8cm double). Every figure from a version-controlled script. (Axiom-level source: [TikZ Guidelines](canon://aesthetics/tikz_guidelines.md).)

## Render-order discipline (the core)

Vital information renders on top. Data above structure, labels above data. Gridlines always `set_axisbelow(True)`, annotation text always on the upper layer.

Reserve space before placing text. Identify each label's collision zone - plot boundary, corner, dense data region, neighbouring labels - at design time and give it room. Extend the axis limit for headroom, pad, or relocate, rather than letting it land on or under another element.

Think in render layers up front. Post-hoc visual inspection is the costly path. Boundaries, corners, and dense regions are the standing risk zones.

## Placement is derived from the data, not guessed

You know what you are plotting before you render it, so you know where the whitespace is. Compute the data's footprint and place every secondary element - inset, legend, annotation - where the data is not. Never hand-place and then discover it landed on the curve.

**Draw the canvas first** (`fig.canvas.draw()`) so the data transform reflects the final limits. Computing placement before the draw uses provisional transforms and lands in the wrong corner.

Two consequences of the inward-tick default:
- **Reserve an edge band along every spine.** Inward ticks live *inside* the data area, so the plot region is not clean to its edges. A secondary element flush against an axis occludes that axis's ticks. Pay this once in the placer, not by eye each time.
- **An inset's labelled axes face the figure interior.** An inset whose y-axis abuts the parent's y-axis sandwiches two near-identical sets of tick furniture and the reader cannot tell whose is whose, even with no literal overlap. Turn the inset's decorations into empty space - a left-half inset puts its y-ticks on the right, a bottom-half inset puts its x-ticks on top.

## An annotation attaches to its referent, and its label is enclosed

A floating "psi = 0.505" in a corner is meaningless without the caption. Attach the annotation to the thing it describes - a slope triangle *on* the power-law line, a label beside its curve, an arrow to its feature. Put the label *inside* the element where possible (a slope-triangle label at the triangle's log-centroid, enclosed by its own legs) - an enclosed label is guaranteed clear and cannot drift into a neighbour. If it cannot be attached, it belongs in the caption, not floating.

Fixing one collision can open another. Placing elements one at a time, each fix can push a label into a neighbour. The durable answer is to make each element's footprint *and its label* self-contained and placed against the data footprint - which is why labels are enclosed and placement is computed, not nudged.

## Usage

This is a protocol, not a backing script. It is the standard the manuscript form object's
[Ring IV](canon://workflow/manuscript_projection.md) (D-figures-to-house-style) points at: the form
demands that every figure asset carry the house mark, and this node owns the detail of what that
means. Build every data figure on the active project's figure-style module (the project node names it). That module encodes the forks above and should provide at minimum: an occupancy-grid placer with an edge-pad band for the inward-tick reserve, an interior-facing inset orienter, an enclosed-label slope-triangle annotator, and an axes finisher (despine, inward ticks, opt-in grid below data). The project node identifies the concrete module; do not hard-code it here.

After rendering, inspect the PNG yourself before presenting - catch collisions before the author does - and open the result natively for review.

### Provenance is part of the standard

`verify.check_figures` is the gate that cites this skill, and building to the standard has to be
sufficient to pass it. Every `fig:` node in the corpus network needs:

- a **non-empty `essence`** - what the figure shows and how, in the node itself, not only in the caption;
- a **`projection.provenance` block** declaring `kind`, either `data` or `schematic`;
- **`reproduce`** on both kinds - the recipe a stranger follows to regenerate the figure;
- **`engine`** on a data figure - the script that produced the numbers (the check also expects the
  data files and the commit that banked them alongside it);
- **`generator`** on a schematic figure.

A missing field is reported by name, so the report reads as a worklist. Build the block when the
figure is made, not at the gate.
