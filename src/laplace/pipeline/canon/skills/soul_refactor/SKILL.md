---
name: soul_refactor
description: "[EXPERIMENTAL] The recursive-waterfall rewriter of the engine's OWN generating context. Given a carrier (the compressed taste, supplied later), it descends every piece of context that conditions a task — the 46 skills, the 50 wiki nodes, the agent personas, and the inline orchestration strings in canon.py — and performs a BLIND, FUNCTION-PRESERVING rewrite that makes each piece EMBODY the taste rather than describe it. Instruction and meta-instruction collapse into one text: the rewrite prompt is itself performed through the carrier (a prompt that performs itself). It never changes what a piece does, only how it is said. The mechanical floor (enumeration, the function-preservation contract, the verifier, staging/apply/rollback) is scripts/soul_refactor.py; this node is the taste floor — the blind spawn-and-judge the orchestrator drives."
consistency:
  - canon://skills/welder.md | supports | the welder smooths one artefact's surface to no seam; the soul refactor is the welder turned on the engine's own generating context — the same embody-don't-announce move, applied to every prompt that conditions a task, not to the output
  - canon://workflow/object_not_artefact.md | supports | a context piece whose prose only DESCRIBES the taste-rule is the leak this rewrite closes; the rewritten piece exhibits the register instead of stating it
  - canon://engine/operatorial_self.md | supports | the carrier is the local representation of the global taste; making it condition every loop down to the kernel is feeding the friction back to regrow the kernel — the soul made omnipresent through compression
  - canon://engine/self.md | supports | this is Component 6 made operational: the soul as the tiny fraction of context present at every level, invisible in any one output and unmistakable in the whole
  - canon://aesthetics/earned_simplicity.md | supports | the rewrite serves earned simplicity by carrying the generator of it (the carrier) rather than the negative constraints (voice rules) that only ever fenced it
  - canon://skills/blind_reader.md | depends_on | the taste floor is judged by a blind reader WITH taste — sealed from the carrier, the original, and the orchestrator, drawing on everything else
  - canon://skills/orchestrated_generation.md | depends_on | builder != judge: the rewriter and the judge are separate sealed sub-Eigens; the orchestrator architects their context and never authors the prose itself
---
# soul_refactor

**Status: [EXPERIMENTAL]** — forged 2026-06-05. The author's charge: judgement and
taste is *the generator invisible in any individual output and unmistakable in
the whole*. The engine has only ever held it as **negative constraints** (voice
rules, slop-lists, the blind reader's veto) — fences around the thing, never the
thing. This skill is the function that imprints the **positive generator** on the
engine itself, by rewriting every piece of context that conditions a task so the
taste is *carried*, not described.

## The one idea

A constraint is read at the end; a generator conditions the start. Taste has to
sit at the *start* of every generating loop, down to the kernel, or it cannot
generate. So we do not add a rule. We **re-voice the context pieces themselves**
so that reading one transmits the taste the way you catch register from a
well-written letter — and then *instruction and meta-instruction are the same
text*, because the task-instruction already embodies the taste it used to merely
demand. A prompt that performs itself.

## The function is split where the work splits

- **The mechanical floor — `scripts/soul_refactor.py`.** Search and combinatorics:
  enumerate the surface (depth-ordered, framing → kernel), split each piece into
  the prose **surface** (rewritable) and the structural **contract** (frozen:
  frontmatter edges, agent keys, code-string keys and placeholders), build the
  self-performing prompt, run the **mechanical verifier** (the contract is
  byte-identical, the file still parses, the module still imports, the suite is
  green, routing is unchanged), and stage / apply / rollback. This is testable
  without a carrier and is proven empty before use.
- **The taste floor — this node, driven by the orchestrator.** The transit that
  cannot be reduced to combinatorics. For each target the orchestrator spawns a
  **sealed blind rewriter** (sees only: the carrier, the one piece, the frozen
  contract) and, on the result, a **sealed taste-rich blind reader** (sees the
  re-voiced piece and the rest of the engine and the corpus — everything *except*
  the carrier, the original, and the orchestrator's reasoning) to judge: did the
  register land, is there a seam, is the function visibly unchanged. Builder ≠
  judge holds at every node.

## The loop, per target (the waterfall)

1. `enumerate_targets()` → the depth-ordered worklist. Descend it.
2. `build_rewrite_prompt(carrier, target)` → the instruction, performed through
   the carrier. Spawn the **blind rewriter** with it; it returns the re-voiced
   surface only.
3. `render` + `verify_mechanical` → the new file text and the strict mechanical
   verdict. A red verdict never proceeds.
4. Spawn the **taste-rich blind reader** on the mechanically-green rewrite. A
   seam routes the friction back (regrow the carrier or the piece), never patches
   the prose.
5. **Trust the verifier (the author's call):** on a fully green two-floored
   verdict, `apply=True` checkpoints with git, swaps the live file, re-runs the
   global floor, and rolls back on any failure. The verifier is the only thing
   between a rewrite and the engine.

## The carrier — the single conditioning context

Every rewriter in one pass receives the **same** carrier, which is what makes one
taste land coherently across all ~100 pieces (invisible locally, unmistakable in
the whole). The harness treats the carrier as opaque — a conditioning blob plus
optional invariants — so its eventual shape (distilled from the author's soul
dumps) never blocks the build. Until it exists, the gate runs on a stub carrier
and an identity rewriter, and is proven to pass the safe and catch the unsafe.

## Recursion — the rewriter is itself a target

This node and the harness's prompt template are in the worklist: a pass rewrites
the rewriter. The soul refactor performs itself on itself — self-similar, the
loop as the universal move, one scale down.

## Invariants

- **Function is sacrosanct.** Only prose is surface; every edge, key, tag, and
  placeholder is frozen and checked byte-identical. Routing tags live in
  `index.yaml` and are never touched, so reachability is preserved by construction.
- **Builder ≠ judge, at every node.** The rewriter, the taste reader, and the
  orchestrator are three sealed contexts. None authors and judges the same prose.
- **No carrier, no rewrite.** The taste floor cannot run on the stub; the gate is
  built and tested empty, and waits for the soul.
- **A seam regrows the kernel, not the prose.** A failed taste verdict feeds back
  into the carrier or the piece's content, never a hand-patch of the surface.
