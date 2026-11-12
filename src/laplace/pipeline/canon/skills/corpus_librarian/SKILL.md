---
name: corpus_librarian
description: "Owns the shared literature store the literature_scout rail draws on. One global corpus.bib across projects - each record carries a distilled claim, a concept cluster, and a trust status - synthesised on demand into a cluster guide and queried by a result's Literature face. Ingestion never blocks, trust is promoted deliberately."
---
# corpus_librarian

## Purpose
`literature_scout` names a shared literature store as an open design - one flexible corpus
across projects, so a reference gathered once is never re-gathered, and a paper's citations
reflect the whole accumulated literature rather than whatever was to hand. This skill is that
store and its discipline. The scout locates and reads - the librarian holds, distils, and serves.

The store has one job the per-project `references.bib` cannot do: it lets a reference be **one
object with two projections**. In `corpus.bib` it is a full record with a distilled claim and a
trust status. In a result's `Literature` face it is a citekey query - `established_by`,
`contested_by`, a context sentence, a novelty sentence. The reference text lives once and is
audited once. Fix the record, and every citing face is correct without a single face being reopened.

## The store
One global `corpus.bib` (biblatex), engine-owned and cross-project - not a per-project bib. It is
**instantiated** at the repo root: `corpus/corpus.bib` (the store) beside `corpus/keywords.yaml`
(the controlled concept vocabulary the `cluster` labels draw from). A real `.bib` at a discoverable,
versioned path, so standard tooling still reads it and the literature is part of the engine's
inheritance. Standard fields are untouched. The corpus carries these extension fields (biblatex
`usera`-`userf` or custom fields):

```bibtex
@article{firstauthorYEARword,
  author = {}, title = {}, journal = {}, year = {}, doi = {},   % standard, untouched
  tldr   = {},   % one sentence: objective + result. Describes the paper.
  claim  = {},   % one sentence: the single most citable proposition. DECLARES, not describes.
  summary= {},   % 2-4 sentences: the accurate ESSENTIAL primitive. This is long-term memory.
  status = {},   % unverified | provisional | borrowed | partial:<restriction> | contested | established | open-gap
  cluster= {},   % leaf concept-cluster label(s) from keywords.yaml; theme is read from there
  keywords = {}, % concept tags against keywords.yaml beside corpus.bib
  relations = {},% rank-ordered typed edges to sibling records: "type:targetkey | semantic description; ..."
  provenance = {}, % comma-separated project keys that cite this record
  added  = {},   % ISO date of first ingestion; immutable
  scout  = {},   % which session/agent ingested it; immutable
}
```

`tldr` describes, `claim` declares, `summary` is the accurate essential primitive - the
distinction is load-bearing. The Literature face resolves a citekey to its `claim` and `status`,
so a wrong `claim` poisons every face that cites it. Guard `claim`, `summary`, and `status`.

**The corpus is a conceptric, not a flat list.** `corpus/keywords.yaml` carries the taxonomy:
references nest into leaf `cluster`s, and clusters nest into coarse `theme`s. A record's
`relations` field is its *rank-ordered map of edges to sibling records* - each a typed, described
semantic link (`extends`, `refines`, `contests`, `analogue_of`, ...). The connectome's
`from_corpus` projects clusters/themes as the containment hierarchy and `relations` as typed
reference->reference edges, so the literature carries genuine relational structure, not just
co-membership. An accurate primitive carries all three: the bib, the `summary`, and its neighbour
relations.

A reference a project draws on (its `provenance`) must be **cited** in that project's manuscript -
the surfacing rule in [`citation_discipline`](canon://workflow/citation_discipline), enforced by
`verify`'s `check_corpus_citations`. The store is what makes that enforceable.

## Two-tier trust (ingestion never blocks)
A blocking confirmation gate becomes a rubber stamp under deadline. So ingestion is always open and
trust is promoted separately:

- A new record enters at `status: unverified`, its `claim` provisional. It is usable and visibly
  untrusted.
- `status: borrowed` marks a claim imported wholesale from prior internal work or a trusted draft
  without fresh confirmation - the honest tag for a deadline cheat. Borrowed is not established.
- Promotion to `status: established` is the only step that needs the author, done in deliberate
  batches, never inline at ingest. A periodic dream may flag a stale-`established` record for re-look
  (carry a `reviewed:` date if the field has moved on).

**The trust boundary is enforced at query time, not ingest time.** `literature_scout` populates a
Literature face's `established_by` only from `established` records. Provisional, borrowed, and
unverified records surface as candidates pending confirmation - never as settled support.

## Citekeys
Deterministic: `firstauthor` (lowercased, ascii-folded) + `year` + first significant `word` of the
title. The validator enforces the pattern and rejects duplicates, so two projects ingesting the
same paper converge on one key rather than colliding.

## The synthesis layer (cluster guide)
A concept cluster is the set of records sharing a `cluster` label. On demand - when a section
targeting that cluster is opened - the librarian emits an **ephemeral cluster guide**: established
claims, candidates pending trust, open gaps, a chronological spine, and the novelty boundary for the
current project. The shape is the three-part state-of-the-art: where the field is now, how it got
here, where it could go next. The guide is generated and handed to drafting as context - it is never
stored. `corpus.bib` is the only persistent artifact.

`scripts/cluster_guide.py` now backs this (the script the design named, now built): it reads the
store, filters by cluster (or by a keyword query), groups by trust status, sorts the spine by year,
and emits the guide - reporting only `established` records as settled support and everything else as
candidates. `--project <key>` adds the novelty boundary: what the cluster holds that the project's
`provenance` does not yet cite. The generative judgement - writing a record's `claim`/`novelty`
sentence - stays host-executed; the script is structural only.

## The three modes
1. **Ingest.** Given a DOI / arXiv id / bib snippet, write a record with standard fields,
   author-or-LLM-drafted `tldr` and `claim` (provisional), `status: unverified` (or `borrowed`),
   a deterministic citekey, and `provenance` set to the calling project. Run the validator.
2. **Cluster guide.** Given a cluster label or concept query, read matching records, group by
   status, sort the spine by year, and emit the guide. Established-only for trusted claims.
3. **Provenance update.** Given a project key and the citekeys its manuscript used, append the key
   to each record's `provenance`. A natural `session_closer` sync step.

The generative steps - drafting the `claim`, writing the `novelty` sentence - are host-executed by a
grounding-capable model, never automated by the backing script. The script is structural only.

## Backing
Four stdlib scripts, the structured-ledger style of the rest of the engine:
- `scripts/check_corpus.py` - validates that every record carries the required fields, that `status`
  is in the allowed vocabulary, that citekeys match the deterministic pattern, and that no key is
  duplicated. Run it on ingest and at session close.
- `scripts/cluster_guide.py` - the mode-2 synthesis (above): emit an ephemeral cluster guide for a
  cluster label or keyword query, with an optional per-project novelty boundary.
- `scripts/ingest_refs.py` - bulk mode-1 ingest: convert a per-project `refs.bib` into corpus
  records (deterministic citekeys, standard fields carried, `provenance`/`added`/`scout` stamped,
  `status: unverified`). It will **not** invent a `claim` - an ingested record enters with a
  title-derived `tldr` and a `TODO` claim, visibly incomplete, for a later distillation pass. It
  dedupes by deterministic citekey, so re-running is safe and two projects converge on one record.
- `scripts/corpus_map.py` - the **corpus map**: the whole store read through the `keywords.yaml`
  taxonomy (theme -> cluster -> reference, trust profile, relation hubs) plus the **coverage
  worklist** (thin clusters, unconnected primitives, missing summaries, unverified records). The
  curated-store counterpart to `deep_corpus_scout`'s raw-tree skeleton: what the librarian reads to
  answer "what do we already hold, and what is missing?" before spending a search. `--gaps` prints
  only the worklist.

```
laplace_run(skill="corpus_librarian", target="corpus/corpus.bib")            # validate
python .../scripts/cluster_guide.py corpus/corpus.bib <cluster> --project <key>
python .../scripts/ingest_refs.py <refs.bib> corpus/corpus.bib --project <key> [--dry-run]
```

The connectome reads this store too: `laplace_graph(corpus="corpus/corpus.bib")` projects the corpus
as the exogenous-substrate graph (references / clusters / projects), with cross-project and
cross-cluster couplings *computed* from shared references - the literature wired into the one
connectome, not held off to the side.

## Relation to siblings
- `literature_scout` is the rail front-end - it targets a claim, searches, reads, and decides what
  each source establishes. The librarian is the back-end store and synthesis. The scout hands a
  confirmed source to the librarian to ingest.
- [`deep_corpus_scout`](canon://skills/deep_corpus_scout) is the batch sibling (forged, decoupled) -
  it maps an unknown large corpus (a tarball or a multi-file repo) into a skeleton + reading order
  before distillation. The librarian is curated single-record ingest plus synthesis, with
  `ingest_refs.py` covering bulk import from a structured `refs.bib`. Distinct skills: the scout maps
  raw volume, the librarian holds distilled records.
- `evidence_ledger` holds the per-result Literature face that queries this store.
