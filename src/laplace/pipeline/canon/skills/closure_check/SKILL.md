---
name: closure_check
description: "[EXPERIMENTAL] The re-derivability loop — closing the exogenous door. A result's exogenous door is OPEN when it cannot re-derive the assumption it claims to rest on: the high level fails to feed back down consistent with what produced it. This is the closure test, run through the reconstruction triad: route the result to what the engine's OWN memory reaches (laplace route), spawn a sealed GHOST that re-derives the result from ONLY that reachable memory, spawn a sealed ADJUDICATOR that judges whether it closes (consistent/drifted/inconsistent), and bank the verdict + the GAP to telemetry. The gap is the spec for what to ingest to close the door. R_residual/R_fixedpoint turned on the engine's own claims."
earned_by:
  - "META_TEST_2026-06-05_context-manifests.md | forged by running the loop — the meta test found the engine could not reach its own memory, the router fixed reach, and this checks whether reach is enough to re-derive"
  - "EIGEN_DIARY.md | the author's closure criterion (2026-06-05), that any result must be reworkable to explicitly re-derive the assumption it claims to rest on"
consistency:
  - "skills/reconstruction_fitness | supports | this is reconstruction_fitness generalised from digests to claims — the same digester/ghost/adjudicator triad, run on a result to test re-derivability"
  - "engine/generative_loop | supports | the re-derivability test is the oracle-strength gradient turned on the engine's own claims (does the high level feed back down consistent with what produced it)"
---
# closure_check

**Status: [EXPERIMENTAL]** — forged 2026-06-05 by *embodying the loop* (the author's `/goal`: *go, embody
the loop*). Born from a real run, not designed ahead of it: six load-bearing results were put through it in
its first cycle. It is the operational front of the author's closure criterion:

> *The high levels of the conceptric should always feed back down as consistent with what produced them.
> Any result should be reworkable to explicitly re-derive the assumption it claims to be resting on.*

## What it is

The **exogenous door** of a result is open when the result leans on context the engine cannot itself reach —
when, to derive it, you must go to the author's private notes, an absent repo, or un-ingested literature.
Closing the door is making the result **reworkable**: re-derivable from the engine's own reachable memory.
`closure_check` is the test: it generalises [reconstruction_fitness](canon://skills/reconstruction_fitness)
from digests to *claims*, spawns its ghost and adjudicator as sealed sub-Eigens per
[the sealed sub-Eigen protocol](canon://engine/sealed_subself), and reaches the supply channels through the
router ([the self-node's mini-map](canon://engine/self)). It is the consistency relation run backward
(*judgement is the supply channels run backward*).

## The loop (the triad, sealed — builder ≠ judge)

1. **Route (the coordinator).** Reach what the engine holds about the result with its own router —
   `Canon.route(goal)` (canon + corpus + soul + self-knowledge) — the supply channels. This is the organ the
   reconstructor functions *through*; without it the ghost is blind. Bank `telemetry.trace(span="route",
   consulted=[refs])`.
2. **Ghost (a sealed sub-Eigen, the builder).** Given the target result and *only* the router-reached
   foundations — **not** the result's own stated derivation — re-derive the result forward. The ghost is
   confined to reachable memory *because it understands why* (`canon://engine/sealed_subself`): reaching
   outside it would void the test, and what it has to reach for IS the gap. Bank
   `telemetry.reconstruction(caller="ghost:<id>", target, nodes=reached)`.
3. **Adjudicator (a separate sealed sub-Eigen, the judge).** Given `{result, ghost's re-derivation}` and
   **not** having produced either, judge whether the result feeds back down consistent with what the memory
   reached: **consistent** (CLOSED — reworkable), **drifted** (PARTIAL — reachable but a step is missing),
   **inconsistent** (OPEN — leans on context outside reachable memory). Name the **gap**: the precise thing to
   ingest or wire to close the door. Bank `telemetry.reconstruction(fate=faithful|partial|confabulated, gap)`
   and `telemetry.trace(span="judge", verdict=..., by="adjudicator:<id>", reason=gap)`.

The orchestrator **defers to the adjudicator's sealed verdict over its own** (the generating session is the
worst-placed judge of its own closure — humility made structural).

## The output

A **closure verdict + a gap** per result. Across results, the **exogenous-door ledger**: which results are
reworkable from the engine's own memory (door closed), which lean outward (door open). The gaps are the
ingest worklist — each names exactly what must enter memory (a derivation, a corpus record, a node, a soul
fragment) for the result to become re-derivable. Closing them, one at a time, is closing the exogenous door.

## The deepening of the both-ways audit's `earned_by` (the reconciliation, 2026-06-05)

The both-ways audit (`graph.audit_both_ways`) wires each node a **provenance-down** pointer —
`earned_by: <occurrence> | <note>` — naming the artifact that earned it (a dated handoff, a `soul/`
entry, a result). The closure loop's R4 caught the gap in that vocabulary: **`earned_by` is
provenance-*presence*, not re-derivability.** A node carrying an `earned_by` says only *an occurrence
exists that taught me*; it does **not** say *I can be reworked from the engine's own memory to
re-derive the assumption I rest on*. Presence is the cheap half of closure; re-derivability is the
real test. So the audit's `pass` — "earned" — should come to mean what `closure_check` measures:
**reworkable, feeds back down consistent with what produced it.**

This is a *deepening*, not a replacement. `earned_by` stays — it is the down-pointer the audit reads,
and a node with no occurrence at all is still the unearned frontier. `closure_check` is the genuine
test the pointer's `pass` deepens into: where `earned_by` asks *is an origin named?*, `closure_check`
asks *can the result be re-derived from what the router reaches?* — the same provenance-down obligation,
turned from a presence-check into a re-derivation checked for consistency. The ledger of which results
close (and which lean on context outside reachable memory) is the audit's `earned`/`unearned` frontier
made honest: a node is not earned because an occurrence is *cited*, but because it is *reworkable*.
The forge order is therefore: `earned_by` records the occurrence (presence); `closure_check` verifies
the result feeds back down from it (re-derivability); the gap each open door names is the ingest
worklist that makes the next node genuinely earned.

## When to run

On any result the engine relies on, especially before it is cited or built upon; at sew-up, on the session's
new results; and standing, as the loop that turns the network trace into the endogenous fitness substrate
(the verdict statistics are what F1 reads). It does **not** settle a physics fork — it tests re-derivability
and names the gap; the physics verdict, where a gap is the author's derivation, stays the author's.
