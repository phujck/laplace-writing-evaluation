---
name: literature_scout
description: "Owns the literature rail of the generation stage. For each core result, establish where it sits in the literature and what is genuinely established there, recording citable provenance per claim plus a bibtex entry, so the literature face is built alongside the result rather than patched onto a draft."
---

# Literature Scout

This skill owns the **literature rail** of the ledger bus - one of the three pieces
of the [generation stage](canon://workflow/core_outward_trunk.md), peer to [`result_foundry`](canon://skills/result_foundry) (results) and [`numerical_evidence`](canon://skills/numerical_evidence)
(numerics). It does not wait for a draft to expose a thin citation. As a result is
established, its literature face is built in parallel: where the claim sits in the
field, what the field already establishes, and what is therefore novel here.

The output has two parts. The lasting one is a **shared literature store** - one
flexible corpus across projects, so a reference gathered once is never re-gathered,
and the citations a paper draws reflect the whole accumulated literature rather than
whatever was to hand. The per-result part is the `Literature` face: a *selection* into
that store for one claim, carrying where the claim sits and what is established near it.
Both are about the *external* record of what the published field holds; how *internal*
prior work re-enters by re-derivation is [`reference_archaeologist`](canon://skills/reference_archaeologist)'s
jurisdiction, not this rail's.

The store is [`corpus_librarian`](canon://skills/corpus_librarian) - one global `corpus.bib` across projects, each record carrying a
distilled claim and a trust status. The scout is the rail front-end: it targets a claim, searches,
reads, and decides what each source establishes. The librarian holds and synthesises. The scout
hands a confirmed source to the librarian to ingest, and draws on its cluster guide for context.

The trust boundary is enforced here, at query time. A Literature face's `established_by` is
populated only from records the corpus marks `status: established`. Provisional, borrowed, and
unverified records may surface as candidates pending confirmation - never as settled support. So
ingest freely and promote trust deliberately, and the face never overstates what the field holds.

This skill has no deterministic backing script - research is an act of judgement.
It orchestrates the tools already on hand.

## Protocol

1. **Target the claim.** Take a settled or in-progress result and phrase the precise
   proposition its literature face must address - where it sits, what the field
   establishes near it, what it claims as novel. Not a vague topic.
2. **Search.** Use the literature surfaces that exist:
   - `src/laplace/research/lit_search.py` - the Scholar-backed candidate query that feeds the
     conceptric editor's bulk-stage picker. It returns bibkey, title, authors, year,
     venue, abstract snippet and URL per candidate, and degrades to
     `{"error": ..., "candidates": []}` when Scholar rate-limits. Standing permission
     to act as the author for Scholar fetching is recorded in its docstring.
   - `corpus_ingest` for adding a confirmed record to the store.
   - Whatever web/search tool the running client actually exposes, for broader or
     cross-disciplinary context. Name the tool you used in the record's provenance;
     do not assume any particular server is mounted.
3. **Read before citing.** Confirm the source actually supports the proposition.
   Trust no abstract - quote the supporting result. A citation that does not bear
   the claim is worse than none.
4. **Record.** Add the source to `corpus/corpus.bib` with the store's status
   vocabulary (established / borrowed / unverified / provisional), and bank the
   open question as a row in the shared research-intent ledger
   (`research_intents.jsonl`, class `literature`) that
   `pipeline/citation_direction.py` and the bibliography stage read. Then write the
   result's `Literature` face: what each cited source
   establishes, and the resulting novelty boundary for this claim. If a source only
   partially supports the claim, soften the claim to match - the ledger must stay honest.
5. **Hand to [the reconciler](canon://skills/reconciler).** A literature face that changes a result's novelty or
   scope is a commitment - propagate it like any other ledger edit.

## Honesty axiom
The point is not to decorate claims with references. It is to discover what the
literature genuinely establishes, and to bring the manuscript's reach into line
with it. If the search comes back empty, that is a finding: the claim is novel and
must be carried by derivation or numerics, or cut.
