---
consistency:
  - canon://engine/operatorial_self.md | supports | the typed CONTENT/FORM/TENSION friction this node owns IS the closure residual, sector-decomposed; that node reads the friction as a loss and the repair as descent along the residual
  - canon://engine/generative_loop.md | supports | this is the prescriptive discipline the descriptive generative-loop account demands; that node says how generation fails, this one states the hygiene that holds the loop closed
  - canon://skills/orchestrated_generation.md | supports | the conceptric-GENERATION loop obeys this discipline and points here for the asset gate and the friction/closure law
  - canon://workflow/manuscript_projection.md | supports | the artefact-PROJECTION loop obeys this discipline and points here for the same asset gate and friction/closure law
  - canon://workflow/object_not_artefact.md | supports | the no-seam / embody-don't-announce rule is that law turned on the projected artefact; this node demands it of any generated artefact, object_not_artefact owns the leak law
  - canon://skills/welder.md | supports | the welder is the manuscript-scale enforcer of the no-seam discipline - the final global pass; it is judged out-of-loop under the builder != judge law this node owns
---
# Generation Discipline — the common hygiene of generating anything

Whenever the engine *generates* — builds a conceptric (a substrate/blueprint with assets
specced or rendered into it), or projects an artefact from one — it obeys the **same** two
disciplines. They are not a property of any one loop; they are the hygiene of the generative
act itself. This node states them **once**, so the
[conceptric-generation loop](canon://skills/orchestrated_generation.md) and the
[artefact-projection loop](canon://workflow/manuscript_projection.md) both **point here**
rather than carry a copy. Each rule has exactly one home: this node owns the *demand*; the
named owner skills own the *detail*; the two loops own only their loop-specific *application*.

This is the prescriptive peer of the [generative loop](canon://engine/generative_loop.md):
that node accounts for *how generation fails* (the backwards-run loop, the curse of knowledge,
the oracle gradient); this one states the *hygiene that keeps the loop closed* on anything the
engine generates.

---

## 1. The asset discipline

Every figure or asset the generation references obeys two rules.

- **(a) House conformance.** Every figure/asset conforms to the **house style** — REVTeX/APS
  geometry, viridis/cividis + Okabe-Ito, vector output, CM serif via usetex matching the body
  face, and every figure from a version-controlled script. This node **demands** conformance;
  the detail of what conformance *means* is owned by
  [`figure_standard`](canon://skills/figure_standard.md) (with the axiom-level appearance
  sources [`visual_mechanics`](canon://aesthetics/visual_mechanics.md) and
  [`tikz_guidelines`](canon://aesthetics/tikz_guidelines.md)). The demand lives here; the
  standard owns the detail.

- **(b) Asset existence is an out-of-loop check.** An asset is **real-or-registered-TODO**, and
  its *existence* is verified from **outside** the generating loop — the builder never trusts a
  node's `Real asset:` claim that a figure file exists, because the builder shares the context
  that hides the gap ([`blind_reader`](canon://skills/blind_reader.md): a reader who shares your
  context cannot find the gap your context hides). A missing or unverifiable asset is a **prose
  fallback** or an **out-of-band registered TODO** (a typed friction repaired into the
  conceptric) — **never** a rendered `\fbox` / `[FIGURE TODO]` placeholder box in the artefact
  body. A rendered TODO box is a leaked meta-instruction wearing a figure's clothes.

---

## 2. The friction / closure discipline

When generation cannot meet a demand, four rules hold.

- **(a) The typed friction report — CONTENT / FORM / TENSION.** An unmet demand is emitted as a
  typed friction row, attributed:
  - **CONTENT** — the slot is well-posed but the content node is absent or thin (a missing
    asset, a claim with no result, a naked reliance with no corpus record). The repair routes
    *into the content conceptric* — grow the node, then re-generate
    ([`core_outward_trunk`](canon://workflow/core_outward_trunk.md): feedback grows the
    conceptric, not the draft).
  - **FORM** — the demand itself is wrong or over-specified for this content. The repair routes
    *into the form/spec object*.
  - **TENSION** — content and demand each say something coherent but they disagree. Surfaced,
    never silently resolved by the generator.

- **(b) No confabulation.** A gap is left as a typed marker, **never invented over**. The
  friction report is the generator's honest account of its own loop leaking — *"I could not
  close demand D because node N is missing X"* — and is signal, never something to paper over.

- **(c) Builder ≠ judge — out-of-loop assessment.** The generator *builds*; whether the build
  is *good* is judged from **outside** its context
  ([`orchestrated_generation`](canon://skills/orchestrated_generation.md): builder ≠ judge;
  [`blind_reader`](canon://skills/blind_reader.md)). The self-consistency audit
  ([`conceptric_coherence`](canon://skills/conceptric_coherence.md)) is the builder's *internal*
  gate (is each level described by the level below), **never** the judge of quality. The same
  builder ≠ judge law turned on *memory* rather than an artefact is
  [`closure_check`](canon://skills/closure_check.md) (re-derivability) and
  [`reconstruction_fitness`](canon://skills/reconstruction_fitness.md) (digest fidelity).

- **(d) Sew up when done.** Every interior loop — every sub/meta agent that generates — closes
  and locks a digest before it returns: the conclusion kept as a primitive, the friction it
  could not close named as a typed gap, the forks surfaced. This is the standing law of
  `EIGEN_PROTOCOL.md` Part D ("interior loops also sew up"); this node **aligns with and points
  at** that law, it does not restate it. A sub-agent that returns a raw transcript instead of a
  sewn-up digest has leaked its loop.

---

## 3. The no-seam discipline — embody, don't announce

A generated artefact built **node-by-node** leaks its own construction: each part can only
narrate its *own* role, so it announces the trellis it was grown on — "in this section we
show…", a slide titled with its design contract, a caption stating what it is *for*. This is
[`object_not_artefact`](canon://workflow/object_not_artefact.md)'s leak (a meta-instruction
surfacing as a self-assertion) in the one place a node-local pass cannot reach: the **global**
narrative no single node can see, and so no single node can dissolve. The discipline of *any*
generated artefact, manuscript or deck or talk, is therefore to **embody, not announce** — the
artefact must *do* the thing it claims rather than *say* it does, so the structure is felt
through its form, never declared in its content, and the finished object is **isomorphic to the
core it grew from**.

This demands a **final global pass** that the node-by-node build structurally cannot apply, run
**once over the whole assembled artefact**, surface-only — it never touches substance (a claim,
citation, equation, figure, or epistemic status); a smoothing that needs substance to change is a
typed friction (§2(a)), not an edit. Its success criterion is **no seam**: the construction —
the node structure, the build order, the form's demand-list — cannot be reverse-engineered from
the finished artefact. And by §2(c) (builder ≠ judge) the pass **never certifies its own weld**;
the seam is what a context-sharing builder cannot see, so it is judged from **outside** by a
cold reader ([`blind_reader`](canon://skills/blind_reader.md)). This node owns the *demand* that
any node-built artefact be welded seamless; the manuscript-scale *enforcer* — the four moves, the
guardrail, the seam test — is the [`welder`](canon://skills/welder.md), the final stage of the
[projection loop](canon://workflow/manuscript_projection.md).

---

## Invariants

- **One home per rule.** This node owns the *demand* (house conformance, out-of-loop existence,
  typed friction, no confabulation, builder ≠ judge, sew-up). The owner skills own the *detail*
  ([`figure_standard`](canon://skills/figure_standard.md), `EIGEN_PROTOCOL.md` Part D). The two
  loops own only their loop-specific application. A rule stated twice is a fork to collapse.
- **Asset existence is judged from outside.** Never trusted from a node's claim; missing assets
  fall back to prose or an out-of-band TODO, never a rendered box in the body.
- **An unmet demand is a typed friction, never a confabulation.** CONTENT / FORM / TENSION, with
  the fix routed to the right conceptric; a gap invented over is the defect this closes.
- **Builder ≠ judge at every depth.** The generator builds; quality is judged from outside its
  context; the coherence audit is the internal gate, never the verdict.
- **Interior loops sew up.** Close-and-lock a digest before returning
  (`EIGEN_PROTOCOL.md` Part D), at every scale.
- **No seam — embody, don't announce.** A node-built artefact leaks its construction; the cure is
  a final global pass that makes it *do* the thing rather than *say* it does, surface-only, judged
  for no-seam from outside. This node owns the demand; the [`welder`](canon://skills/welder.md)
  enforces it for manuscripts as the projection loop's final stage.

*This is the shared discipline both generative loops obey. It points at the owners and is pointed
at by the loops; it copies no rule it does not own. Whether the factoring is GOOD is the author's
verdict; the meta-dreamer built and integrated it and does not self-certify its quality.*
