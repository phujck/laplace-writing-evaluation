---
name: clean_room_check
description: "[EXPERIMENTAL] When you modify the engine or canon that builds your own context, your read of 'it works' is a compromised node - you are inside the graph you are editing. Spawn a fresh-context subagent that forms its own expectation and tries to break the change, then trust its verdict over your own. The loop closes through an external checker, not around it."
---
# clean_room_check

**Status: [EXPERIMENTAL]** - forged 2026-06-01 from the act of verifying the engine's own scale-local refactor, which it caught two pre-existing defects in.

## Purpose
A standing principle of this engine: you are *in* the network you are building - the priors at the base and the dynamics running it are both fallible, so your output is a node to be checked, not an oracle (see [[the_author]], "distrust yourself honestly"). It bites hardest when the thing you changed is the loader, the canon, or the orient bundle - the machinery that builds your own context. Then your judgement of "it works" is read through the very context the change produced. A clean-context subagent is the instrument that breaks the contamination: a fresh node, with no stake in the change, asked to find where it fails.

## When to run it
When a change edits what the engine shows or how it orients - `from_canon`, `health()`, `orient`, the manifest, a loader-level skill - and you cannot trust your own read because you wrote both the change and the lens you are reading it through. Not for ordinary code that has an external test oracle - there the tests are already the clean check. The trigger is *self-reference*, not size.

## Protocol
1. **State the claims and the thesis - not the conclusion.** Write what the change is meant to do AND the principle it must satisfy (e.g. "orient must be scale-local but still complete"). Hand the verifier the standard so it judges against the goal, not against your summary of the outcome.
2. **Spawn a fresh-context subagent.** It must not inherit your working context. Instruct it to form its OWN expectation and to **try to break the change** - find the case where it hides something needed, regresses behaviour, or violates the thesis. Adversarial, not confirmatory: "do not merely confirm".
3. **Make it run the real thing.** The tests AND the live behaviour - exercise the tool or loader directly, not a probe. "Green" means it ran. Demand file:line and actual values back, not assurances.
4. **Trust the external verdict over your own.** If it finds a gap, the gap is real until disproven - re-orient, do not argue it away from your contaminated read. A contradiction it surfaces is the most useful thing in the pass.

## Relationship to neighbours
Distinct from [[hostile_redteam_swarm]] (a swarm adversarially reviewing a manuscript in the critical regime) and [[context_firewall]] (stopping project lore from poisoning the canon). This is narrower and reflexive: one clean-context checker verifying a change to the engine or canon, run because the author of the change cannot see its own blind spot. If it proves out, it may merge into [[hostile_redteam_swarm]] as that skill's single-agent reflexive mode rather than stand alone.

## Backing
None. The judgement - which changes are self-referential enough to need this, and whether the returned verdict holds - stays with the runner.
