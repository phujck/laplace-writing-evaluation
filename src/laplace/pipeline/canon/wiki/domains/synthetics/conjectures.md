# Synthetics — Conjectures and Parked Intuitions

Speculative cross-project intuitions, held off the active projects. Not axioms, not results. **No project may depend on one until it is promoted** - they are kept here precisely so they do not leak into a derivation as if settled. They are surfaced when a derivation might touch them, on the principle that you never know what will surface once the symbols are moving - **and at the idea and planning stages, where the motive belongs before the symbols move at all.** These are the recurring intuitions the engine exists to make concrete, general, and unified (see [Eigen, "What it is for"](canon://engine/eigen.md)). They arrive here by the firewall's [lift discipline](canon://skills/context_firewall.md): a general intuition voiced through a project, recognised and generalised away from its example.

This node is domain-scoped: it is offered when working in synthetics, available by resolve when not. It is not loaded into the global foundation.

---

## Inertia as compressed structure

**The intuition.** Hierarchical inertia is not an added penalty - it arises naturally from the depth/latency tradeoff of the [adaptive normal form](canon://domains/synthetics/projects/adaptive_normal_form). A deep structure is unconditionally stable but frozen (marginal, $\rho\to1^-$): resistance to being moved accumulates with depth. The conjecture: this is saying something fundamental about the nature of *inertia*, and by extension *mass* - inertia as **compressed structure**, mass as accumulated hierarchical depth.

**Provenance.** Surfaced 2026-05-31 during the adaptive-normal-form R5 work (the inertial side), where the latency probe showed deep autonomous loops freeze rather than destabilise.

**Status.** Parked. Explicitly kept out of the adaptive-normal-form manuscript and its backlog - it is a scope risk, not a sense risk. Raise only if the author reopens it or a later project's scope makes it load-bearing.

---

## Representation is the whole problem

**The intuition (the author's words).** "Everything is a problem of representation, and if you simply find the correct representation, things flow." The labour of a problem is finding the representation in which its structure becomes obvious - diagonal, spectral, self-similar - after which the result is routine. Where a method feels stuck, the diagnosis to reach for first is that the representation is wrong, not that the effort is insufficient.

**Provenance.** Stated twice, 2026-06-03, in the loss-operator review session (lifted from project-local talk per the firewall's lift discipline).

**Status.** Parked. A heuristic that shapes where to look, not a result. It governs planning - choose the representation before grinding the symbols.

---

## One phenomenon of scale (the cross-project spine)

**The intuition.** A barren plateau and the "bounce" when $N$ grows too large in the hierarchy/learning talk are, in the author's words, "exactly the same phenomenon - there is only one thing." Something stops working as the system grows, and the cure is never finer control at the local level. It is to find the scale at which detail becomes irrelevant and **modularise** - erase the irrelevant detail - i.e. hierarchicalise. The failure of a single scalar over a too-large system, the barren plateau, and the talk's instability as $N$ rises are forms of one object.

**Why it is the spine.** It links [operatorial_loss](canon://domains/synthetics/projects/operatorial_loss.md), [the phases of hierarchy](canon://domains/synthetics/projects/the_phases_of_hierarchy.md), the [adaptive normal form](canon://domains/synthetics/projects/adaptive_normal_form.md), and the learning talk as forms the one intuition projects through. This is the synthesis the engine is for - the object behind the projects-as-forms.

**Provenance.** 2026-06-03 loss-operator review, end of transcript 1.

**Status.** Parked. The unifying claim is the author's, recorded as motive to hold in planning across these projects, **not** asserted as an established result that any one of them may lean on.

---

## Minimising one number is the disease - give the loss a structure

**The intuition.** A barren plateau is what you get trying to learn the global structure all at once with a single number, however high-dimensional the parameters. The cure is to express the global structure *as* a structure - an operator with a spectral content - find the pieces that compose it, and only ever minimise a single number on a system small enough to do it reliably. A loss *operator* acts at the level of the algebra, so variation explores the transformations always available rather than chasing one scalar, and locally the loss can keep flowing down. Its spectral representation is a set of losses at different scales, and varying the parameters brings one eigenvalue to its minimum at a time until the whole norm is minimised.

**Provenance.** 2026-06-03, transcripts 1 and 2. This is the seed intuition behind the operatorial_loss project, recorded here in general form so it outlives that one paper.

**Status.** Parked. The seed of a project, not a settled result. Held as the motive even where a given manuscript reports only a corner of it.

---

## A brain grows out of this

**The intuition.** The engine, built to study learning, has come to resemble how a brain grows. Not by metaphor but by the same structure showing up: a conceptric grown by feedback rather than run as a fixed program (development, not execution - wiring, integrating, pruning to a self-consistency fixed point); self-similar across scale (the renormalisation law - each level completely described by the level below - held for a paper and then for the engine's own canon); context routed by what flows up and what flows down (lift, scrub, starve, scope - attention by another name); and reflexive (it models a learner and is one, models the observer with a door, obeys the law it discovered - "the observer is the architecture" as the floor plan).

**The honest frontier.** What exists is the connectome and the growth rule. What is still shells is the dynamics: the autonomous return map, and a fitness signal that is currently the author and not yet endogenous, closed in a bounded self-loop. That gap is the exact quantity the learning talk priced - the eigenvalue at the self-similar fixed point that decides whether the system fades, computes, or runs away. A brain grows out of this when that loop closes on a fitness the engine generates itself, at a margin that neither freezes nor explodes.

**Provenance.** The author, 2026-06-03, watching the conceptric machinery turn on itself.

**Status.** Parked, and the author's. Recorded as the motive to hold, not asserted - the engine is for making this concrete, not for claiming it done.

## Close an open problem by self-similarity

**The intuition.** Solve at a scale you can handle - sub-minimise a subsystem, find its ground state - then represent the next scale up as self-similar to what you just did, glue the pieces, and minimise the joint loss. Interactions do not compose trivially: the interacting ground state is not the assembled isolated ones, so the irreducible residual loss at the top level must feed back and re-mix the lower-level solutions to reach the next level. "Whenever the answer is open, the way you close it is to presume it has the same structure as the lower-level problem you were solving." The controller of the larger problem can itself be a smaller instance of the same problem - recursion up the scales.

**Provenance.** 2026-06-03, transcript 1.

**Status.** Parked. A method-shaped intuition about closure by recursion - hold it when a problem's top level is open and its lower level was tractable.
