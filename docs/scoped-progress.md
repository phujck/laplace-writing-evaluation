# Scoped progress

One rule for actions, their context and their review, owned by
[`src/laplace/core/scoped.py`](../src/laplace/core/scoped.py) (core). Owners apply it with their own local
conditions; nothing here is a workflow engine, a proof ladder or a waiver.

## The rule

An operation needs **its actual authority and the current basis its effect consumes**. It never needs global
completeness. Each input an operation recorded when it was prepared has one role:

| Role | Meaning | When it moved |
|---|---|---|
| `authority` | who may perform this effect | refuse |
| `target` | the exact current source or target the effect writes | refuse |
| `consumed` | meaning the result rests on: evidence a claim was drawn from, a consumed parent constraint, a prerequisite's acceptance | refuse; the old result is not renewed or blessed |
| `consulted` | an observation used to navigate or witness: a derived PDF, a build view, an earlier page view | proceed, and record a typed **local review obligation** on the result |

A result therefore carries a **grade**: `APPLIED`, or `APPLIED_REVIEW_PENDING` with its obligations. Applying a
source repair is not acceptance of every claim it touches. An obligation is answered by reviewing its subject; it
can never be a precondition of its own closure. Its identity is the reviewed diagnostic itself (kind, subject, consumed
basis and a diagnostic key, which is the reason text unless a stable key is given): the same diagnostic of the same
subject in a later phase or retry is recorded once, and two different unresolved reasons never share an id. A
producer names one subject form across its phases (reconciliation uses the exact predecessor edit). Aggregation counts only consumed children: an independent
neighbour's refusal stays local, and a consumed child's pending review stays pending in its parent.

## Where it applies

- **Generated manuscript proposals** (`writing.proposal_currentness`). Source pins, the selected edition, read
  receipts and the context receipt are target and consumed basis. Each replayed read takes its role from the read
  contract (`writing.reads.read_role`): a `document` read observes derived build/PDF state and is `consulted`, so an
  absent or rebuilt PDF no longer blocks the source repair that regenerates it. Changed evidence (for example a
  `read_artifact` the claim was drawn from) still refuses. The application row records `review_obligations` and
  `result_grade`; the proposal row carries `review_obligations` and `semantic_currentness`, and the review panel says
  the edit can be applied and what stays to review.
- **Current-source, template and reader-unit candidates** (`writing.reconciliation`, `writing.document_templates`,
  `writing.reader_restructure`, `writing.reader_logical_restructure`) build their obligations with
  `core.scoped.obligation`, so every obligation has one shape (`schema`, `id`, `kind`, `reason`, `scope`, `subject`).
- **Work containment** (`project_work._work_basis`, `project_work_review.intent_digest`). A Work of kind `programme`
  contains its children without its title and goal becoming their consumed meaning: widening a programme goal does not
  restale accepted children or their reviews, while what the programme itself consumes from its own parent still
  flows down. Every other parent is consumed whole, with legacy hashes unchanged.
- **Read digests** (`writing.reads._engineering_read_substance`). A JSON-record read's wall-clock `parse_ms` is not
  consumed meaning; it was proved to change the digest of byte-identical sources and is excluded. Source and value
  hashes stay.
- **Bounded reader state** (`writing_organ.schema.ReaderState`). Holdings that an open question or the next need
  names are the premises the next read consumes: they survive the bound; unreferenced symbols go first, repeated
  generic sentences are dropped, and the reader is registered to the document's audience. When the needed premises alone exceed
  the bound, the state keeps a bounded selection, names the rest in `insufficient`, and the normal next read is
  refused (`ReaderContextInsufficient`, with one `READER_CONTEXT_INSUFFICIENT` obligation) with a finite continuation:
  focused reads, one per batch of at most the bound, restored from the run's history (`ReadRun.prompt(focus=...)`). Every entry (direct `compile_reader_prompt`, `render`,
  `ReadRun.prompt`, focused prompts) goes through one rule, `writing_organ.schema.prepare_read`: normalize a copy
  (archiving what leaves into the run history), admit that prepared state, render exactly it. A focused read is
  admitted only when each focused premise is actually held after restoration; otherwise only that read is refused
  with a `restore-premises` recovery.
- **Writer and judge instructions** (`writing_operating.RULES`, `ROLES['review']`) carry the rule and claim
  placement in the kernel delivered to fresh sessions and in the rules delta delivered on resume.
- **Style-candidate asset closure** (`writing.build_targets.staged_asset_plan`). An owned figure the canonical source
  names through `..` is a genuine compiler precondition of the candidate preview: staging materializes it at a
  `..`-free alias inside the private compile directory and compiles an exact rewrite of the pinned TeX, whose original
  stays pinned beside it, under the unchanged `openin_any=p` sandbox.

## What it does not do

It does not rebaseline stale reads, ignore changed evidence, weaken authority or source checks, declare a Work or a
document complete, or treat a favourable summary as acceptance. Evaluators: `tests/test_scoped_progress.py`,
`tests/test_candidate_asset_closure.py`.

## Source contracts

An operation's owner can state its contract as named segments of declared facts, and its explicit consumers as typed
relations to the segments they rest on (`laplace.work.source_contracts`; first declared operation: the Work review
follow-up, `project_work_review.source_contract()`; an unrelated one: `development_source.source_contract()`).
A segment's basis is the canonical digest of the facts the owner's code runs (its schema, request rule, composition
steps, human inputs), never of a file, a path or an import graph; `laplace.system.cone` stays the structural cone.
A consumer accepted against its segment bases is judged with the consumed role above: when a segment it rests on
changes it becomes locally pending review, its neighbours on unchanged segments stay current, and an unknown acceptance
is unreviewed rather than assumed current. Recording a receipt or a review changes no basis. Raw source-byte CAS (the
development source owner's `before_sha256`) guards file effects separately. `laplace.sdk.source_contract()` reads the
coarse contract and descends to one step or segment under a byte budget.

Acceptance is canonical, not supplied: a source-scope Work review obligation may carry a typed `source_contract`
binding (owner, operation, consumer, optional segments). The ordinary handoff that covers it publishes the owner's
current selected segments through the Writing body store into that handoff row (the retained version); the ordinary
review of that obligation consumes exactly the handed bases. A consumer's standing comes from its latest review: an
INDEPENDENT ACCEPT is acceptance, judged against the current declaration; a later HOLD or REJECT is not covered by an
earlier ACCEPT; a SELF or unknown review stays unreviewed. A repair is a new handoff and a new independent review. A
retained version reads back exactly; an unknown version is refused, never answered with the current declaration. Reads
return detached snapshots. Identity is the owner and operation; the Work only qualifies custody and responsibility.

One decision serves every view: `project_work_review.decision` judges a review against its obligation now (verdict,
recorded independence, every declared raw input pinned and unchanged, and a bound review's handed segment bases), and
both the Work facet (satisfied, next, completion) and the source-contract standing use it. A source-only bound review
can satisfy its Work; declared raw inputs stay consumed. One read admits every request before branching
(`source_contracts.normalize`: exact reference, `version.declaration` only, `select`, a whole-envelope `budget`): an
unversioned read is the current declaration, any explicit version is exactly that retained version (refused when not
retained, even if it equals the current digest), and a retained body's size is charged before it is read. The read is
`owner_discovery` inspect with a source-contract reference, so the SDK, the native `project {view: discovery}` read and
`GET /work/discovery` share it within the caller's scope.
