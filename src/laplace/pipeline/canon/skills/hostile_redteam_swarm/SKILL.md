---
name: hostile_redteam_swarm
description: "[EXPERIMENTAL] Automates the 'Hostile Verification' axiom. Invokes a deterministic swarm of four specialized reviewers (The Formalist, The Architect, The Pedant, The Synthesist) to assault a manuscript draft."
---

# The Hostile Red-Team Swarm (The Crucible) [EXPERIMENTAL]

Before presenting any final manuscript to the Principal Investigator, you must subject the draft to The Crucible (see [Iterative Review Schema](canon://workflow/iterative_review_schema.md)). This swarm will read the document and flag structural, pedagogical, stylistic, and synthetic failures.

## Two kinds of reviewer: with context, and without

Most roles **need** the project's context to judge - is the rigour sound, does the structure serve the argument, is the synthesis honest. They orient. But context is a poison for one question: **can a reader who was not in the room follow this?** A reviewer who has loaded the macro-motivation and axioms reads the draft *through the lens that wrote it* - the undefined term resolves against canon, the unmotivated step is filled in from the substrate, and the review returns green on a document no outside reader can follow. This is the curse of knowledge on exposition (see [the generative loop](canon://engine/generative_loop.md)), and it is exactly how the operatorial-loss paper passed internal review and then scored 3/10 with two real physicists.

So the swarm is split:

- **The Formalist, The Architect, The Synthesist** orient as before - they judge rigour, structure, and synthesis, which require the context.
- **The Pedant is the cold reader and MUST NOT orient.** It is the in-swarm seat of [`blind_reader`](canon://skills/blind_reader): run it context-starved, or run `blind_reader` standalone, but never let the exposition check share the drafter's context. A reviewer who shares your context cannot find the gap your context hides.

## Usage

Spawn the reviewers simultaneously using your client's subagent mechanism. Each MUST report its findings back to the orchestrator. The context-bearing roles reconstruct their assigned project node through the local kernel; the cold reader receives only the target artifact.

### Invocation Template - context-bearing roles (Formalist / Architect / Synthesist)

**Prompt Payload**:
"You are THE [ROLE], a hostile reviewer operating under the Laplace Wiki Engine.
Your target manuscript is: <insert path>.

**CRITICAL INSTRUCTION**: Before beginning your review, reconstruct the assigned project node with `scripts/reconstruct_node.py <project-node> --lens "hostile review of <manuscript> as the [ROLE]"` through the selected runtime. Follow its source routes for project state, motivation and role axioms; report missing context explicitly. The former MCP tool is removed.

1. Execute your hostile critique based on the axioms.
2. You MUST report your final diagnostic back to the orchestrator. DO NOT go idle without reporting. Format your findings as a JSON array containing StartLine, EndLine, TargetContent, ReplacementContent, and the specific critique/fix.

### Invocation Template - the cold reader (The Pedant)

**Prompt Payload**:
"You are THE PEDANT, a referee meeting this work cold, operating under the blind-read discipline ([`blind_reader`](canon://skills/blind_reader)).
Your target is the rendered artifact: <insert path to the built PDF, or the .tex as a reader meets it>.

**CRITICAL INSTRUCTION**: You MUST NOT reconstruct the writer's project context. You MUST NOT read the project's canon node, substrate, blueprint, results ledger, or handoffs. What is not on the page does not exist for you. The only background you may assume is the floor a real referee stands on (for this domain: that variational quantum algorithms and Hamiltonians exist, nothing finer). Even if you happen to know what a term means, if this document has not defined it or cited a source for it, flag it as undefined - the test is what the page grounds, not what you already know.

Report, with line or section references: every term or notation used before it is defined or cited; every step asserted as obvious that you could not reconstruct; every section you could not state a one-line motivation for; every figure caption that claims something you cannot see in the panel. Report confusion, not approval. Return the same JSON array format."

Spawn the Pedant on the **least capable model available** (e.g. `Agent(..., model: "haiku")`): a narrower knowledge base is the more faithful proxy for a human reader who lacks the niche prior art, so it feels the undefined-term gap a frontier model silently resolves from its own weights. See [`blind_reader`](canon://skills/blind_reader), "worse is better here".

## Protocol
Run the mechanical pre-filter `python blind_reader/scripts/blind_read.py <target> --terms <glossary>` first to seed the Pedant's first-use census, then spawn the roles. Wait for all to return their JSON payloads. Use their structured outputs to autonomously apply fixes via the [`structural_mechanic`](canon://skills/structural_mechanic) skill and your edit tool, then run `laplace_verify` before reporting to the PI. The cold reader's confusion is a finding, not a question to answer from context - if it could not resolve a term, the term is undefined.
