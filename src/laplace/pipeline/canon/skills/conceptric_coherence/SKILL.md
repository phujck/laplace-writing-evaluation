---
name: conceptric_coherence
description: "[EXPERIMENTAL] The conceptric is a living multi-scale object, and feedback grows it, not the draft. An iteration is done only at a self-consistency fixed point: every coarse node (a claim, a motive - the what/how/why) is completely described by the nodes at the level below it. This measures that, so 'the conceptric grew' can be told from 'the conceptric got bigger'. More nodes is not more integration."
---
# conceptric_coherence

**Status: [EXPERIMENTAL]** - forged 2026-06-03 when the author asked whether a rebuilt
conceptric was genuinely integrating or just a different, larger stochastic sample with
the same incoherence. The honest answer needed an instrument, not an assertion.

## Why this exists
A review lands on the draft, but the draft is a projection of the conceptric (see
[the core-outward trunk](canon://workflow/core_outward_trunk.md), "feedback grows the
conceptric, not the draft"). Increased demands on the paper are demands for *structure*
in the lower-level object. So an iteration adds nodes - but adding nodes is not the goal.
The goal is the **renormalisation condition the author keeps pointing at**: iterate until
the conceptric is consistent with itself and **the nodes at one level are completely
described by the nodes at the level below**. A coarse node that cannot be reconstructed
from its children is a hole, however many nodes surround it. That is a fixed point, and
reaching it is the work.

## The two instruments
- **The compiler** (`scripts/build_conceptric.py`) merges a substrate and a blueprint and
  **computes** the cross-level harmonisation edges rather than drawing them by hand (the
  stance the substrate already takes on induced interactions): a claim to the result it
  realises and to the definition of every term it names, a section to the author guess it
  serves (the why beneath the what/how), and each reader requirement to the node that
  satisfies it. The conceptric is built, not hand-wired, so it cannot quietly drift out of
  self-consistency.
- **The audit** (`scripts/conceptric_coherence.py`) scores integration: the fraction of
  coarse nodes completely described below them, averaged over the levels (results composed
  by a why and a how, claims grounded in a result and in their terms, motives grounded in
  a guess, reader requirements wired, no floating nodes). It reports the gaps by id, so the
  next iteration knows exactly what is under-determined. **It judges self-consistency, not
  whether the physics is right** - that is `falsifiable_core`'s axis.

## The protocol (one iteration)
1. **Grow the conceptric** with the feedback - add the nodes and the layers the demand
   requires (a vocabulary layer for ungrounded terms, a motive layer, a reader layer).
2. **Compile** it, so the harmonisation edges are recomputed.
3. **Audit** it. Compare the *score* to the previous iteration, not the node count. A rise
   in nodes with a flat score is a different sample, not an evolution - say so honestly.
4. **Close the named gaps** and re-compile, until the only un-described nodes are the
   doors themselves (the boundary, with nothing below them). That is the fixed point.
5. Only then grow the draft from the blueprint, core-outward, shells staying loose until
   an oracle locks them.

## Conceptric evolution tracks the global ideas
The diff between two conceptric snapshots is itself a record of how a new perspective
propagated through the object - which coarse claims and motives changed, which new layer
appeared, how integration moved. Bake a snapshot each iteration
(`scripts/bake_graph_snapshot.py`) and keep them: the sequence is a legible trace of the
high-level ideas evolving, the coarse-grained `what/how/why` shifting as the work learns.
This is a second handle on the standing problem of tracking global ideas across sessions.

## The engine conceptric obeys this too
What applies to a project conceptric applies to the engine conceptric, because the canon
is a conceptric - [`graph.py`](canon://engine/eigen) projects it through the same node and
edge model (`from_canon`). Feedback (a session, a lesson) grows the engine conceptric, and
it is iterated to the same fixed point: each level completely described by the level below,
the boundary the only un-described nodes. [`canon_weaver`](canon://skills/canon_weaver) is
the **topology** layer of this gate (orphans, dangling links, components), and this skill is
the **renormalisation** layer (is each coarse node composed by its children). The two catch
different holes: a pair of nodes that link only to each other reads `orphans = 0` to the
topology check but shows up as a disconnected **component** - an island not woven into the
body. When this lens was first turned on the engine itself it found exactly that (a git
mechanics island, two nodes floating off the 81-node body) and the newest skill weakly
woven - both grown back into the object. The engine studies self-similarity and is subject
to it.

## The build-completion contract (seven gates)

The conceptric is **not built** until seven gates pass. Any failure names its failing nodes
by id — the friction worklist. This closes the loop between "conceptric mint" and
"conceptric projection-ready": a projector reading a build-complete conceptric never
descends into an orphan, a phantom label, a coined-and-recoined term, a claim without
literature under it, or a figure a stranger cannot reproduce.

| Gate | Owner | Enforces |
|---|---|---|
| **topology** | [`canon_weaver`](canon://skills/canon_weaver) | zero orphans, zero dangling links, single connected component; a pair of nodes linking only to each other is a disconnected island, not an integrated part |
| **coherence** | this skill's `scripts/conceptric_coherence.py` + the editor's regrade panel (`/corpus/grade_stats`) | every coarse node completely described by the level below; node sizes watched per grade (the power law is watched, never imposed — split the bloated, merge the content-free) |
| **connectivity** | [`laplace_verify`](canon://engine/eigen) `checks=['connectivity']` | every node reachable from ≥1 spine beat via `deps` — a definition orphaned from every IRF that uses it is a floor a projector cannot descend to |
| **projection_labels** | [`laplace_verify`](canon://engine/eigen) `checks=['projection_labels']` | every `fig:` / `eq:` / `thm:` / `def:` / `ref:` node carries `projection.latex_label`; every experiment-result `fig:` node carries `projection.data_source` — the projector emits stable `\label{}` / `\ref{}` / `\cite{}` from a slot that is always present, never confabulated at emit time |
| **glossary** | `laplace_verify` `checks=['glossary']` | terminology locked at the conceptric level: every `def:` carries `projection.term` (+ `aliases` / `deprecated_aliases`); no two defs claim one term; retired vocabulary appears in no live essence; GLOSSARY.md renders FROM this registry (`scripts/render_glossary.py`) so the doc cannot drift. The invent-and-reinvent failure, caught structurally |
| **substrate** | `laplace_verify` `checks=['substrate']` | nothing is assumed: every `res:` / `thm:` / `goal:` node reaches VERIFIED literature (`ref:`/`sup:`) within 2 hops; a CSV proves the number, a reference positions the claim. Refs live rich in `corpus/corpus.bib` (tldr/claim/summary/relations, provenance-tagged) so generation receives context, not citation tokens |
| **figures** | `laplace_verify` `checks=['figures']` | every `fig:` node carries a stranger-reproducible `projection.provenance` block: kind (data/schematic), generator, engine, data files, banked commit per CSV, seed, reproduce recipe |

**After the gates, projection has its own contract** (earned 2026-07-02 on the subset-sum
whitepaper): author a **plan object** (`manuscript/projection_plan.json` — content
selection + the pinned linear order of nodes per section + figures + refs + binding
builder rules), validate it mechanically (`scripts/validate_projection_plan.py` — every
node live, every ref resolvable, every figure provenanced, unplanned live claims
surfaced), then build each blind builder's COMPLETE context bundle mechanically
(`scripts/build_section_briefs.py`). The builder receives its brief and nothing else;
the citations gate (armed with `corpus` + `project`) fails any relied-on reference the
prose does not surface. Put the voice constraints (Vonnegut rule: no semi-colons in
prose, spaced hyphens, no em/en-dashes; no AI house-style tells) INTO the brief contract
— builders drift to em-dashes otherwise and the voice gate pays the cleanup.

**Topology + coherence catch different holes than connectivity** (as canon_weaver already
teaches — orphans zero to topology but disconnected components hide). Connectivity adds a
sharper failure mode: a node that satisfies topology (has some edge) and satisfies
coherence (is fully described by its children) can still float, if none of its consumers
lead back to the spine. Projection walks the spine down; a node the spine cannot reach is
a node the projector never emits. That is a silent hole the earlier gates do not catch.

**Projection_labels is the emit-time obligation** paid at mint time. The projector's
descent produces LaTeX; every `\label{}` and `\ref{}` must resolve to a stable name the
conceptric already owns. Minting the slot at node-creation time means the projection is
mechanical — no name is invented downstream, no manifest drifts out of sync. The slot
lives on the node (`projection: {latex_label, section_ref, data_source?}`), not in a
separate index: locality wins over sync problems.

## The protocol (one iteration, extended)

1. **Grow the conceptric** with the feedback — add the nodes and layers the demand
   requires (a vocabulary layer for ungrounded terms, a motive layer, a reader layer).
2. **Compile** it — `build_conceptric.py` recomputes the cross-level edges by term-match
   over every kind that names a term (claims, IRFs, derivation-steps, theorems), so
   ground-term edges land automatically rather than orphaning definitions.
3. **Run the seven gates.** Any failure is a typed friction with node ids. The gates run
   through `laplace_verify --checks=conceptric_build`, so the failure is scriptable, not
   author-eyeballed.
4. **Close the named gaps** (backfill, mint labels, wire supports to consumers, add
   missing IRFs) and re-compile, until all seven gates pass. Only then author the projection plan and grow the draft from
   the blueprint, core-outward.
5. **Assets participate in the same loop.** A `fig:` node carries `projection.data_source`
   (CSV path, TikZ source, code path). Figure generator scripts read the IRFs their beat
   carries — when a scope-condition IRF is added, the figure re-renders with the
   boundary as first-class content, not caption prose. This is the render-time analogue
   of the connectivity gate: prose IRFs and rendered figures stay in sync because both
   descend from the same node.

## Conceptric evolution tracks the global ideas
The diff between two conceptric snapshots is itself a record of how a new perspective
propagated through the object - which coarse claims and motives changed, which new layer
appeared, how integration moved. Bake a snapshot each iteration
(`scripts/bake_graph_snapshot.py`) and keep them: the sequence is a legible trace of the
high-level ideas evolving, the coarse-grained `what/how/why` shifting as the work learns.
This is a second handle on the standing problem of tracking global ideas across sessions.

## The engine conceptric obeys this too
What applies to a project conceptric applies to the engine conceptric, because the canon
is a conceptric - [`graph.py`](canon://engine/eigen) projects it through the same node and
edge model (`from_canon`). Feedback (a session, a lesson) grows the engine conceptric, and
it is iterated to the same fixed point: each level completely described by the level below,
the boundary the only un-described nodes. [`canon_weaver`](canon://skills/canon_weaver) is
the **topology** layer of this gate (orphans, dangling links, components), and this skill is
the **renormalisation** layer (is each coarse node composed by its children). The two catch
different holes: a pair of nodes that link only to each other reads `orphans = 0` to the
topology check but shows up as a disconnected **component** - an island not woven into the
body. When this lens was first turned on the engine itself it found exactly that (a git
mechanics island, two nodes floating off the 81-node body) and the newest skill weakly
woven - both grown back into the object. The engine studies self-similarity and is subject
to it.

## Invariants
- Compare the integration score, never the node count. More nodes is not more integration.
- A coarse node not completely described by the level below is a hole, and the iteration
  is not done. Name the hole by id - do not smooth it.
- The harmonisation edges are computed by the compiler, not drawn by hand, so the object
  cannot drift out of self-consistency between audits.
- **The conceptric is not built until all seven gates pass.** Topology, coherence,
  connectivity, projection_labels. The gates run automatically at the close ritual; a
  conceptric can grow beyond the last audit but cannot ship without one.
- **Projection labels live on the node, never in a separate manifest.** Locality wins;
  no drift is possible when the label is the node's own frontmatter.
- **Assets are conceptric-aware.** Figure generators read the IRFs their beat carries and
  render scope boundaries as first-class content. When a scope-condition IRF is added,
  the figure re-renders on the next projection pass; the loop closes without touching
  the caption.
- The audit scores self-consistency, not correctness. Pair it with
  [`falsifiable_core`](canon://skills/falsifiable_core) for whether the locked results are
  earned, and [`blind_reader`](canon://skills/blind_reader) for whether the projected draft
  reads.

*Experimental. The four-gate contract was earned on the subset-sum-itqde disclosure and extended to seven (glossary, substrate, figures) plus the projection plan-object contract at the forty-ninth session (2026-07-02), when the whitepaper projection ran end to end through it
(forty-fifth session, day 5) when a projection lens over 11 figures surfaced 94 orphan
leaf-kinds (~41% of the corpus) that all four gates in isolation would have caught earlier.
Refine the checks when an iteration teaches a sharper sense of what "completely described
by the level below" demands.*
