---
name: reconstruction_fitness
description: "[EXPERIMENTAL] The inverse of digestion, scored. The knowledge-digestion pipeline only ran forward (raw -> digest -> place in the conceptric); this is the missing assess half. Digest a session (or any object), then ask a blind, context-starved agent to RECONSTRUCT it from the digest ALONE, and judge the ghost against the archived original. The gap is the fitness - on the memory (did the digest carry the object) and on the level tender's organisation of the hierarchy (did the placement help the rebuild or scatter it). Every reconstruction-call is banked as the reinforcement record: ghosts summoned again and again accrete in the activation history the growth rule restructures from. Memory is not stored; it is the refined skill of good-enough reconstruction."
earned_by:
  - SESSION_HANDOFF_2026-06-05_reconstruction-and-self-judgement.md | forged as the inverse of digestion, scored - the tripartite digester/ghost/adjudicator loop
---
# reconstruction_fitness

**Status: [EXPERIMENTAL]** - forged 2026-06-05 from the author's `/goal`: *all the systems of
storage, persistence, resurfacing and evolution have to run harmoniously*, and the first thing that
unlocks the rest is **a fitness test on memory and on the level tender's organisation of the
hierarchy.** It may eventually force a root-and-branch rebase and a full corpus reingestion; this is
the design we watch first.

## The idea

Every task, at every scale, is one self-similar loop: **orient -> synthesize -> execute -> assess.**
The knowledge-digestion pipeline ([`knowledge_digestion`](canon://workflow/knowledge_digestion))
built the first three for *memory* - orient on a transcript, synthesize the digest, execute the
placement ([`transcript_digest`](canon://skills/transcript_digest) ->
[`level_tender`](canon://skills/level_tender) -> [`the_librarian`](canon://agents/the_librarian.yaml)).
It never built **assess**. This is that piece.

A conceptric *is* a reconstruction of its object - that is the whole point. Weaving a conceptric
that reliably projects into a finished artefact (the manuscript work) and rebuilding a session from
its digest are **the same operation at different scales**: both reconstruct an object from a
compressed, hierarchically-placed residue. So the fitness of memory is measured the only honest way -
*reconstruct it and look at the gap*:

> raw object -> **digest** (forward) -> conceptric -> **reconstruct from the digest alone**
> (here) -> ghost -> **judge ghost vs. archived original** -> fitness + the residue that is the
> spec for what the digest must carry next.

The stored form is always the **digest**, never the raw - *it can never live locally as just the
full transcript.* The raw rests immutable in [archival storage](canon://workflow/knowledge_digestion)
**only** as the ground truth the ghost is scored against, never as the working store.

## The tripartite loop (this is the core of self-judgement)

Reconstruction fitness is **three context-bounded roles cycling in a loop** - not a tree of agents
reporting up once, and *not* the orchestrator judging from its own context (that was the residual
bug: a judge who still holds the session context fills the gap from memory it shouldn't have, and
scores a green that means nothing - the same curse [`blind_reader`](canon://skills/blind_reader) and
[`orchestrated_generation`](canon://skills/orchestrated_generation) name, now caught in the *judge*).

- **Digester (D)** - has the original; produces the digest (placed, neighbour-wired). The only role
  that sees the original *and* writes to the store.
- **Ghost (G)** - sees the **digest only**, never the original; reconstructs from it. (Else it copies
  and nothing is tested.)
- **Adjudicator (A)** - sees **{original, ghost} only** - no session context, no digest, no
  conceptric; judges *similarity* and names the *gap*. (Else it scores self-consistency, or fills the
  gap from context the orchestrator would have leaked.)

Three messages cycle, each crossing exactly one context-wall: **D -> G** passes the digest packet;
**G -> A** passes the ghost; **A -> D** passes the gap (*what* differs, never *how* to fix it - A has
no standing to prescribe). D tightens the digest against the gap, G re-reconstructs, A re-judges. The
loop converges on the **minimal digest that still reconstructs faithfully** - earned simplicity made
operational for memory: compressed as far as it goes without losing the object. It **terminates** on
convergence (similarity stops improving) or a depth budget - the bounded-recursion law
[`generative_loop`](canon://engine/generative_loop) / Component 5 already demand, since a loop that
chases fidelity forever is the runaway failure mode.

Why this *is* self-judgement: no single context both makes and grades. The adjudicator is the
**endogenous oracle** - it cannot pre-answer, because it never saw the digest, only the outputs. The
self judges itself without confirming itself. That is the frontier (Component 5) in a buildable shape,
and it is the author's to bless as the fitness mechanism, not mine to decree.

`scripts/adjudicate.py` is the adjudicator's **mechanical proxy** - it accepts exactly two artifacts
and nothing else (the interface is the context-wall), computes a cheap 2-shingle similarity and the
crude lost/added gap, and banks it. The proxy is the shape of the data we collect, but **it is
unfaithful** - the first graded-climb run (2026-06-06) showed it scoring three semantically faithful
reconstructions "confabulated", because 2-shingle Jaccard measures shared *phrasing*, not shared
*meaning*. So the scalar gate that reads it is **void**.

### The sealed semantic adjudicator (G1) - the meter, validated (`scripts/adjudicate_sealed.py`)

The replacement: a **semantic** verdict from a blind sealed sub-Eigen, judging by meaning, emitting
`{lost, added, structured, recurses, justification}` - SEMANTIC lost/added (claims, not tokens) and
the approximate-closure discriminator (is the residual *structured* - a namable gap that *recurses*
to seed the next grade - or noise). It emits **no fate label**: FORK-FATES is the author's,
deferred; the meter banks raw signals (`telemetry.adjudication`), the vocabulary that reads them is
set downstream. An **ensemble** of model/temp-diverse verdicts is folded into the *joint* (meaning
lives in the joint, never one channel); the cloud ghost is spawned by the orchestrator, the script
is the pure, testable harness (the same instrument/policy decoupling `converge.py` used).

**A meter you have not validated cannot validate anything.** So the adjudicator gates *itself* first
(`faithfulness_gate`), against the `calibration/` set - `{original, ghost}` pairs whose ground-truth
property is known, mapped to predicates over the signals - and a **planted wrong ghost** (a ghost
carrying a specific falsehood the meter MUST surface in `added`; the load-bearing one inverts the
covenant ratchet - a confabulated fact about people). A meter that misses a plant is void; a meter
never tried against a plant cannot pass. Only **PASS** un-voids the scalar gate the first rung threw
away. Thresholds are a pluggable policy socket (conservative defaults, F1-adjacent, the seam open).

## The two fitnesses it reads - and which one is the point

A digest is only powerful if it is stored so that **each digested concept lives next to the other
concepts it belongs with.** So the deep test is not "can this one session be replayed" - it is
"can digestion wire *every concept into its proper place with its proper neighbours*", across all
prior digestions, not just this one. Session-replay is the integration test; correct
neighbour-wiring is the mechanism. These are one operation at two scales.

1. **Neighbour-wiring (the core).** For each concept the level tender names a placement *and its
   proposed neighbours* (`nearest_refs`); `reconstruct.py` surfaces both. A concept wired to the
   wrong neighbours is a **confabulation even if the session reconstructs** - the digest reproduced
   the words but lost the concept's true relations, which is the part that makes the store generative
   (concepts from different sessions living adjacently is what lets them *interfere* into something
   richer). The judged verdict is whether the proposed neighbours are right; the mechanical proxy is
   the placement band (placed / weak / ungrounded), since a weak or ungrounded placement is the
   confabulation risk surfaced *before* the agent runs. This is why fitness is bounded by the store's
   semantic richness: where the corpus is rich the concept lands with its true kin; where the corpus
   is blind to a lineage, the level tender places *confidently and wrongly* - the exact failure that
   demands a corpus reingestion.
2. **Memory fidelity (the integration test).** Reconstruction works by traversing the
   neighbourhoods: if every concept is wired to its true neighbours, the ghost is rebuilt by walking
   the right edges; if concepts are mis-wired, the walk goes to the wrong places and the ghost
   confabulates. The judged verdict mirrors retention's survived-vs-earned axis
   (`telemetry.RECONSTRUCTION_FATES`):
   - **faithful** - the ghost matched; the digest carried the object *and* its relations.
   - **partial** - the spine survived, the flesh was lost; the craft of compression working, *not* a
     loss (the rewrite-toward-the-line analogue).
   - **confabulated** - the ghost asserted what was never in the source, or wired it to the wrong
     neighbours; the real loss, the *confident wrong* placement - the microexpression defect at the
     retrieval layer.

## When divergence is the point — and why the adjudicator is a sealed sub-Eigen

If the wiring works, a mature ghost should eventually return something **richer than the digester** —
it draws on the whole neighbourhood, not just the session, so it legitimately reconstructs *more than
the original.* This inverts the early fitness: "similarity to the original" is the right test while the
web is thin (can the digest even reconstruct the session), but for a rich web it would score genuine
**enrichment** as confabulation. The adjudicator's target therefore evolves:

- **Early (thin web):** fidelity — did the digest carry the object.
- **Mature (rich web):** coherent enrichment — does the concept wire so well the ghost returns *more*,
  and is that more *consistent with the web* (constructive interference) rather than invented
  (incoherent addition / destructive noise wearing confident clothes).

Telling enrichment from confabulation **cannot be decided in the moment** by any metric — it is a
judgement of taste ([Component 6](canon://engine/self): does this addition sing with its neighbours).
So the verdict belongs to a **sealed sub-Eigen** ([sealed_subself](canon://engine/sealed_subself)), not
to `adjudicate.py`; the script is only the floor, the cheap phrasing signal we bank each cycle. The
adjudicator must carry the soul (to judge coherence) yet be sealed to {original, ghost} only (to judge
without the orchestrator's generator-bias).

The optimal in-the-moment call is deferred on purpose: the long-term way to close the enrichment loop is
**benchmarks and ensemble evolution of the self** — run variants, score them against a held benchmark,
let selection decide what divergence was worth keeping. That is the endogenous fitness (Component 5)
reached by population, not by a single in-session verdict. Future, not now; banked here so the gap is
named, not papered over.

## The reinforcement record (why every call is logged)

`telemetry.reconstruction(target, caller, nodes, ...)` banks every summon - including the
`caller` (the orchestrator *or* a spawned guide, so sub-agent calls count too) and the `activated`
nodes the ghost called. This is the substrate the author named: **long-term memory works by
reinforcement** - the ghosts called again and again show up in the activation histories, and that is
how the brain restructures. It is the same co-activation signal Component 1 already banks, now driven
by reconstruction demand, feeding the same growth-rule analyser (Component 2). Banked at summon, ahead
of the fidelity verdict, because un-logged history is the one loss that cannot be recovered.

The deep consequence the author flagged: reinforcement has a runaway twin (the most-called path
deepens until memory collapses onto one over-reinforced attractor), so a healthy reconstruction
regime needs a conjugate decay/coverage pressure - the optimum-size physics, reinforce vs. forget as
a conjugate pair. That balance is the author's fork, not set here.

## How to run the loop

```
# D: digest the object (forward half - existing), archiving the raw as the adjudicator's ground truth
python ../transcript_digest/scripts/digest.py <transcript.md> --out <digest-dir> \
    --archive archive/transcripts --id <id>

# D: build the blind packet (digest only) + the neighbour-wiring read; bank the reinforcement record
python scripts/reconstruct.py <digest-dir> --corpus corpus/corpus.bib --target <id>

# G: hand reconstruction_brief.md to a BLIND agent (the ghost); it weaves the reconstruction from the
#    packet ALONE - it must never see the original. Save the ghost to <ghost.md>.

# A: the SEALED SEMANTIC adjudicator (G1) - the real verdict. Build the sealed brief from
#    {archived original, <ghost.md>} only, spawn N model/temp-diverse sealed agents, fold the joint:
python scripts/adjudicate_sealed.py brief <archived-original.md> <ghost.md> --out adj_brief.md
#    (spawn the ensemble on adj_brief.md; save each verdict JSON), then:
python scripts/adjudicate_sealed.py aggregate v1.json v2.json ... --target <id>
#    The cheap 2-shingle proxy is banked alongside as the FLOOR only (it is unfaithful - see above):
python scripts/adjudicate.py <archived-original.md> <ghost.md> --target <id> --cycle <n>
#
# Validate the meter ITSELF before trusting it to gate (the faithfulness gate):
#    for each calibration/<item>: build the brief, spawn the ensemble, drop v*.json in the item dir
python scripts/adjudicate_sealed.py gate calibration/   # PASS un-voids the scalar gate

# Loop: feed the gap back to D, re-digest, re-ghost, re-adjudicate, until similarity converges
#       or the depth budget is hit.
```

## What it is, and is not

It is the **assess** corner of the digestion loop, made first-class, and the first test of whether the
conceptric we hold actually reconstructs what it digested. It is **not** the endogenous fitness policy
(what fidelity is *worth* at first call), the decay/forgetting rule, or the decision to rebase and
reingest the corpus - those are the author's forks ([`self`](canon://engine/self),
[`generative_loop`](canon://engine/generative_loop) name the bounded-recursion discipline it must
eventually obey). Born experimental, reversible; let measured fitness promote or retire it.
