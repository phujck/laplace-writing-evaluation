---
name: context_firewall
description: "[EXPERIMENTAL] Enforces Contextual Compartmentalisation to prevent local project lore from infecting the global Laplace architecture and skills."
---
# context_firewall

**Status: [EXPERIMENTAL]**

## Purpose
The `context_firewall` skill acts as an absolute barrier between the universal, generic architecture of the Laplace identity and the local, highly specific jargon of individual projects. It ensures that any structural updates, protocol refinements, or skill modifications remain universally applicable and uncontaminated by transient project context.

## The Axiom of Compartmentalisation
1. **The Global Context is Universal**: Skills, the McCaul Protocol, and global workflows must NEVER contain project-specific nouns, concepts, or equations.
2. **The Local Context is Transient**: Project files, manuscripts, and scratchpads exist to be operated on, but their contents must not leak upward into the rules governing the operations.
3. **The Cleansing Mandate**: Before any Laplace agent writes an update to a `SKILL.md`, `mcp_config.json`, or any global configuration file, it must pass the proposed content through a strict jargon-scrubbing review.

## Sibling-project clause

The firewall covers not only upward canon-poisoning (project lore leaking into
global skills) but also lateral project-to-project poisoning. Prior or
sibling-project material - results, framings, named constructs, claims - enters a
working session only by re-derivation, never by copy. A name or framing is earned
once the current development produces what it denotes. Carrying a construct across
project boundaries without re-earning it violates this firewall in the same way
that writing it into a global skill does: it imports an unearned assumption into a
context where it has not yet been established.

In practice: if a result, concept, or framing arose in a different paper or
project, treat it as a prior reference - cite it, re-derive what you need, and
name the result only when the current work justifies the name.

## The two upward flows: scrub the jargon, lift the intuition
The firewall above blocks one upward flow - project jargon and specifics leaking into
the global rules. There is a second upward flow it must **not** block, and the quiet
failure is to scrub it by mistake. A project conversation carries two things tangled
together: the **local instance** (this Hamiltonian, this ansatz, this number) and the
**general intuition voiced through it** (a move about representation, structure, scale,
or method that would recur in an unrelated project). The local instance stays local.
The general intuition must be **lifted** - recognised, generalised away from its
example, and stored where planning will meet it again. Scrubbing the jargon and
discarding the intuition with it is how the engine loses what should compound (the
author's own gap-name, "we're losing information that should compound").

This is the method for separating the globally useful from the project-local. Apply it
to any sentence in a source by **stripping the project nouns**:
- If something still stands once the nouns are gone - "find the representation in which
  the structure is diagonal and the rest follows", "the failure at large N is solved by
  hierarchy, not by finer local control" - it is a general intuition. **Lift it.**
- If nothing remains once the nouns are gone, it was local. **Leave it.**

Lift targets: a domain's [parked intuitions](canon://domains/synthetics/conjectures.md)
for substantive motifs, [author signals](canon://voice_corpus/author_signals.md) for
method traits. A lifted intuition is **parked, sourced, and never load-bearing in a
derivation until promoted** - the same earned-commitment discipline the scrub side
enforces, run in the other direction. This is the engine's purpose made operational
(see [Eigen, "What it is for"](canon://engine/eigen.md)): the scrub keeps the rules
clean, the lift makes the motive cumulative.

## Usage Instructions
When forging or refining a skill (e.g., as `the_dreamer` or when manually prompted):
1. **Identify the Core Structural Logic**: Extract the meta-operation that needs to be encoded (e.g., "Ban complex derivations from the main text" instead of "Move the domain-specific derivation to the appendix").
2. **Scrub Local Variables**: Replace project-specific terms with abstract variables or generic functional descriptions.
3. **Verify Universal Applicability**: Ask: "Would this exact skill instruction work seamlessly for a biology paper or a software manual?" If no, the skill is too specific and must be generalized.
4. **Enforce Segregation**: If project-specific instructions are strictly necessary, relegate them to a local `project_instructions.md` within the current workspace (see [Project Scaffold](canon://templates/project_scaffold.md)), leaving the global `SKILL.md` pristine.
