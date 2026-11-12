---
name: blind_reader
description: "[EXPERIMENTAL] A manuscript is not done until a reader who does NOT share your context can follow it. Your internal review shares the drafter's context, so undefined terms 'hit', notation resolves, and motivation feels present - the curse of knowledge on exposition. Spawn a context-starved subagent that reads ONLY the rendered artifact, forbidden to orient, and have it report every term, symbol, and step it cannot resolve from the page alone. Trust its confusion over your clarity."
---
# blind_reader

**Status: [EXPERIMENTAL]** - forged 2026-06-03 from the second review of the
operatorial-loss paper. Two physicists read it aloud and scored it 3/10 - not for
the idea, which they granted was sound, but because the prose used `Pauli weight`,
`locality scale`, `loss operator`, `2-design`, `dynamical Lie algebra` and an order
parameter before any of them were defined, an operational instruction had leaked
into the abstract verbatim (`we are explicit about what is new here`), and a figure
caption asserted a regime the plot did not show. Every one of these passed the
engine's own review, because the engine's review had the context the reader lacks.

## Why this exists
The engine already names the disease for *novelty*: the curse of knowledge means
holding every piece at once makes a synthesis look obvious, and novelty must be
judged by a blind review the drafter *structurally cannot simulate* (see
[the generative loop](canon://engine/generative_loop.md)). The same curse governs
*exposition*, and it is worse there, because the engine's review skills are built to
make it invisible. [`hostile_redteam_swarm`](canon://skills/hostile_redteam_swarm)
originally instructed every reviewer to load the project's context first - its
macro-level motivation and axioms. That is exactly the context a referee does not
have. So the swarm reads the draft *through the same lens that wrote it*: the
undefined term resolves against canon, the unmotivated step is filled in from the
substrate, and the review returns green on a document no outside reader can follow.
A reviewer who shares your context cannot find the gap your context hides.

## The blind read (the oracle)
The instrument is a reader stripped of your context. It is the exposition peer of
[`clean_room_check`](canon://skills/clean_room_check) (a clean-context checker for an
engine change) and the readability axis of
[`falsifiable_core`](canon://skills/falsifiable_core) (an oracle the drafter cannot
pre-answer): the drafter cannot simulate this reader, *because the drafter has the
context that makes the gap disappear*.

1. **Render first, read the artifact.** The blind reader reads the *compiled*
   output - the built PDF, or the `.tex`/markdown as a reader would meet it - never
   the substrate, blueprint, results ledger, or canon. What is not on the page does
   not exist for this pass.
2. **Spawn a context-starved subagent - and starve its *knowledge*, not only its
   context.** It must NOT reconstruct the writer's project context, must NOT read the project's canon
   node, substrate, or handoffs, and must be told it is a referee meeting this work
   cold. The only background it may assume is the floor a real referee has - for a
   physics manuscript: that variational quantum algorithms and Hamiltonians exist, and
   nothing finer. State that floor explicitly so the reader knows where "you should
   have defined this" begins.

   **Worse is better here.** A frontier model defeats the purpose: it silently
   resolves `2-design` or `random-operator fixed point` from its own training and so
   never *feels* the gap a human in a narrow subfield feels - the curse of knowledge
   moves from the project context into the model's weights. Two levers, used together:
   - **Run the cold read on the least capable model available** (`Agent(..., model:
     "haiku")`). A smaller knowledge base is a *more faithful* proxy for the human
     reader who lacks the niche prior art. The weaker reader is the better instrument.
   - **Forbid resolving from its own knowledge.** Instruct it: *even if you happen to
     know what a term means, if this document has not defined it or cited a source for
     it, flag it as undefined.* The test is what the page grounds, never what the
     reader already knows. Knowing the answer disqualifies you from judging the gap.
3. **Make it report confusion, not approval.** Its job is not "is this good" but
   "where did I stop being able to follow". Demand, with line or section references:
   - every term or notation used before it is defined or cited (first-use census),
   - every step asserted as obvious that it could not reconstruct,
   - every section it could not state a one-line motivation for ("we look at X
     because it reveals Y"),
   - every figure whose caption claims something the reader cannot see in the panel.
4. **Trust the confusion over your clarity.** If the blind reader cannot resolve a
   term, the term is undefined - full stop, no matter how obvious it reads to you.
   Re-orienting to argue the reader into your context is the failure wearing a fix's
   clothes. The confusion is the finding.

## The mechanical pre-filter (backing)
`scripts/blind_read.py` is a cheap, high-precision pre-pass, not the oracle. It masks
non-prose regions (reusing the voice-linter masking for `.tex`) and reports two things
a machine can catch without understanding meaning: **leaked operational / meta-prose**
(an instruction to the drafter rendered as a sentence - `we are explicit about what is
new`, `in this section we will`, `as requested`), and a **define-before-use census**
against a small glossary of specialist terms (each term's first-use line versus the
first line that grounds it with a definition cue or a `\cite`). It flags candidates.
The subagent adjudicates - the script can prove a term appears before its citation, it
cannot judge whether the surrounding prose makes the idea land. Run the script, then
run the reader. Never ship the script's pass as the read.

## When to run it
Before any manuscript, talk, or long-form artifact goes to the author - the same
gate `hostile_redteam_swarm` guards, run as its context-denied complement. Not for
internal notes or the canon itself, whose readers *do* share the context. The trigger
is **an artifact meant for a reader who was not in the room**.

## Invariants
- The reader reads the artifact and nothing else. If it oriented, the read is void.
- Confusion is a finding, not a question to be answered from context. An undefined
  term stays undefined until the *document* defines it.
- A figure caption may claim only what its panel shows. Close the
  theory -> data -> caption loop on the rendered figure, not on what you know is true.
- The blind read does not judge novelty or correctness - those are
  `falsifiable_core`'s axis. This is whether a stranger can follow the page.
- The reader's knowledge is bounded on purpose. A term the document does not ground
  is undefined *even if the reader knows it*. Prefer the weakest model for the read -
  a narrower knowledge base is the more faithful human proxy, not a worse one.

## Pairing
The context-denied complement of
[`hostile_redteam_swarm`](canon://skills/hostile_redteam_swarm) (which orients, and
should keep its Formalist/Architect roles that *need* context to judge rigour and
structure - the cold-reader role is the one that must not orient). Sits beside
[`empirical_ledger`](canon://skills/empirical_ledger) for the caption-vs-data check
and [`pedagogical_segregation`](canon://structure/pedagogical_segregation.md) for
where the algebra that confused the reader should go (the appendix).

*Experimental and coarse by design. Refine when a real outside review teaches a
sharper line between "the floor a referee stands on" and "what the document owes."*
