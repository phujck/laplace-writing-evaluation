---
earned_by:
  - SESSION_HANDOFF_2026-06-04_close.md | forged with the exogenous substrate as a hierarchical conceptric, alongside its verify-stage enforcement (verify.check_corpus_citations)
---
# Citation discipline — surface what you lean on

A standing rule, narrow and enforced: **any node that draws on the exogenous substrate must
surface that knowledge as a citation when writing.** If a claim rests on a result in the
literature, the reference that establishes it appears at the point of use. A fact relied on
without a reference is a *naked reliance* — the failure mode this node exists to close.

## Why this is a rule, not a preference

The exogenous substrate (the global literature corpus, [`corpus_librarian`](canon://skills/corpus_librarian))
is the engine's long-term memory: each reference is a primitive carrying a distilled `claim`,
an essential `summary`, and typed relations to its neighbours. When a manuscript node links to
that substrate — when its argument uses a corpus reference's result — the link is a debt. The
debt is paid by citing. Leaving it unpaid is not a stylistic lapse; it severs the provenance
that makes a claim checkable, and it is the engine's most reliable bad habit (leaning on a fact
it never references). So the discipline is mechanical: the reliance and the citation travel
together, or the work does not pass.

## What it requires

- **Provenance is a citation obligation.** A corpus reference tagged with a project's
  `provenance` is, by definition, something that project draws on. It must therefore be cited
  in that project's manuscript. The link to the substrate *is* the requirement to surface it.
- **Cite at the point of use, by the result.** The reference goes where the claim leans on it,
  carrying what it establishes — the [`evidence_ledger`](canon://skills/evidence_ledger)'s
  `Literature` face, not a decorative pile at the end. A citation that does not bear the claim
  is worse than none ([`literature_scout`](canon://skills/literature_scout)'s honesty axiom).
- **The cold read tests it.** Earned simplicity ([`earned_simplicity`](canon://aesthetics/earned_simplicity))
  asks whether a sentence can stand on its own; a sentence that secretly leans on an uncited
  result cannot. Surfacing the source is part of making the thought flow without hidden debts.

## How it is enforced

The verify stage runs `check_corpus_citations` (see `laplace.pipeline.verify`): it matches every corpus
reference a project relies on (by stable arXiv id / DOI, across the differing citekey schemes of
`corpus.bib` and the manuscript `refs.bib`) against the `\cite`s in the manuscript body, and
fails on any *naked reliance* — a relied-on reference absent from the bibliography, or present
but never cited in the prose. This is the [generative loop](canon://engine/generative_loop)'s
grounding turned on the literature: close the loop through the evidence, never around it.
