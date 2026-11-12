# Atlas front: supported optional consumer

The existing `atlas.front` command composes record ingestion/opening, declared
lenses, persisted grading, range readers, question compilation, evidence supply
and item update. It is a research entrypoint with historical toy/benchmark
callers; production Laplace use is not established by this boundary repair.

`python -m atlas.front --help` and importing `atlas.front` are core-only reads.
The public question declaration types and receipt types are also lightweight.
Accessing numeric exports such as `FrontDoor`/`LoadedLens`, or executing the full
command, requires declared optional dependencies. Direct numeric-module imports
can expose their actual missing dependency. The command preflights its reached
capabilities and returns a named refusal before creating record/tree state; it
never installs a dependency, changes the selected device, or falls back to a
sibling research checkout.

From this source checkout, use:

```sh
scripts/laplace-python -m atlas.front manifest.json --datasets toy --out result.json
```
 An installed Atlas exposes the same command, but the toy input is the exact
tracked `evidence/ATLAS_PROGRAMME/lane_c/toy_corpus.py` source fixture. It is not
shipped in the wheel. A missing fixture produces `FRONT-TOY-INPUT-UNAVAILABLE`
with its owner path and source-checkout resolution before record/tree state is
created. `manifest.root` selects state, not a replacement input. No input copy,
research-sibling discovery or implicit alternate dataset is attempted. Installed
typed/numeric capability checks do not prove whole installed FrontDoor carriage;
portable dataset/replay inputs remain required subsequent ingestion work.

The manifest supplies a state root, a declared draw ID and
optional dataset subset. The existing factory owner validates the entire selection
(unknown/duplicate names refuse), constructs each selected dataset once and
performs no unselected dataset setup/IO. Cheap discovery uses the same factory
keys; an empty/omitted call override falls through to the manifest subset, and
an empty/omitted manifest subset deliberately means the complete draw. Malformed
overrides refuse rather than widening the request. Tolerance selects a declared precision. The full path
writes record segments, compressed tree blobs/manifests and an optional result
file. The selected draw/device/capacity must be observed independently. Atlas
package metadata declares the optional reconstruction, kernel and spectral
extras; choose what the reached path requires rather than adding heavy default
runtime dependencies.

## Typed declaration versus literal observation

`compile_question` remains the executable authority: its original coded
conditions, operator, budget, derived tensors and row sets are unchanged.
`as_query_plan` now emits `atlas.front.question/2`; `as_obligation_plan` uses
`atlas.front.obligations/2`, both with the existing canonical reconstruction
dataclasses. Historical v1 and `typed-query-obligations-v2` records are preserved.

Each condition becomes a dataset-scoped `ContextBinding`, with exact row-kind
and column, a stable `condition:<index>` key, its authored `Condition.as_dict()`
and deterministic JSON typed payload. The index is in this exact
`CompiledQuestion.coded`, which can include appended derived conditions; it is
not necessarily an index in `QuestionSpec.conditions`. The evidence obligation
references every context ID. A declaration is not an English `ClaimObligation`.
Only actual literal occurrences of declared surfaces become lexical candidates,
with exact Unicode-character spans. All repeated/overlapping occurrences are
explicit. Literal occurrence does not establish a semantic attachment or truth.

Scalar payloads and finite declared surface-code lists serialize directly.
Record-sized derived codes serialize as `{compiled_ref: {dataset_id, qid,
condition_index, field}, availability: live_compiled_question_only}`. Those names
are labels inside the exact retained live object, not unique cross-record/lens
or revision resolvers. `resolution: provided` qualifies the declaration/reference,
not the unavailable numeric values in a detached JSON document. A round trip
preserves the declaration and reference but cannot replay the original derived
set. Never pass this descriptor to the numeric reader in place of actual codes.
The original live compiled payload remains the object the numeric path executes;
this projection never expands tensors, scans rows or hashes full derived sets.

## Source basis and receipts

`FrontDoor.answer_stage` calls `_question_stage` for the real question emission.
Its CPU control exercises that same method over already compiled objects; it is
not a whole-front, GPU, encoder or ingestion proof. The stage consumes only the
`query_plan`/`query_obligations` capability closure, through the shared lifted
owner. That owner compares retained first-adapter observations to current files
before a successful question receipt enters the chain. Changed or unknown basis
refuses with affected paths and cold revalidation; no hot reload occurs.

The receipt separates historical origins, selected qualified package/API and
first-adapter/current file observations. Every file observation explicitly says
`loaded_bytes_asserted: false`: an ordinary import's disk hash is not proof of
all executed source bytes. Numeric capabilities used later belong to those later
consumers, not this typed receipt. The source check charges its hash work and
gate latency. Producer-owned stable receipt bases retain every pin/status/byte
count in the stage address, while timing diagnostics remain visible outside it,
alongside stage/gate seconds. Loaded objects and first observations are reused in the process.

Stage hash chains show recorded address linkage, not complete dependency
closure, current implementation, numerical correctness or scientific acceptance.
Old receipts remain inspectable as historical. Warm-tree reuse does not yet
compare the full stored lens/source/implementation basis; this remains required
persistence work and this boundary must use a cold whole-front acceptance fixture.

## Cost and independent checks

The typed projection costs declared-condition serialization, literal searches
and emitted spans; it does not scale with derived tensor/record size. First
imports and explicit source hashes are charged over the deduplicated consumed
closure. Full cold work includes ingestion and grading; warm opening still reads
persisted bytes and resolves identities. Historical two-pass toy timings changed
both compilation state and record-open path, so they do not isolate compilation
as the sole explanation or establish a current speedup.

Run the scoped CPU boundary with:

```sh
scripts/laplace-python -m pytest atlas/tests/test_front_lift_consumer.py -q
```
 It covers declaration/JSON semantics,
literal spans, live-only derived references, actual question emission, module
identity, simulated caller source-currentness refusal and metadata/CLI dependency refusal. Real disk mutation is exercised by the package owner in its disposable installed
fixture; this caller file never mutates active checkout implementation. Source
and installed-prefix selection and one cold toy/numeric path are separate parent
integration checks. No code being moved/importable or old benchmark PASS proves
whole Atlas acceptance, arbitrary English understanding or a numerical theory.

## Versioned serialized readers and scoped comparisons

The command emits `atlas.front-door-run/2`, containing one canonical
`atlas.front-dataset-run/2` per selector. Questions occur only in the read stage's
payload; per-lens tree observations occur once and name their primary lens.
Repeated fixed tolerance prose and the measured planner model are contained
stage references. Root/dataset IDs and selectors are distinct coordinates.
Raw live `StageReceipt.as_dict()` remains its original interface; a historical
serialized file is never rewritten merely by reading or converting it.

Use `atlas.front.receipts.verify_run` for complete known-version/hash/chain and
reference validation. `canonical_dataset_of_run` validates and returns a detached
v2 snapshot. Comparisons use `inspect_dataset_run` once per dataset/arm: this
fixed owner batch validates and resolves question, primary-tree, planner and
tolerance-recipe views privately within the same detached observation. Its
availability distinguishes missing optional historical basis from malformed
advertised data. No whole-receipt validation occurs inside question loops. `questions_of_run` and
`primary_tree_of_run` default to compact basis; `recipe_of_run` resolves only a
contained exact reference. Explicit `expand=True` restores known prose/timing
views transiently. The CLI uses these owners before publishing its result or
summary; stored `chain_verified: true` alone never establishes successful linkage.
These are offline consistency checks, not proof of current code, the original
source cut, scientific correctness or complete historical reproduction.

The maintained J3 `synthesis/compare_runs.py`, J4 `compare_cold_warm.py` and P1
`ablation_off_is_today.py` use the same `atlas.front.comparison` assurance owner.
Their exit codes are 0 for `EQUIVALENT`, 1 for `DIFFERENT` and 2 for `UNPROVED`.
They require exact nonempty dataset and question coverage, required fields
(distinct from explicit null), and complete represented row/range handles.
Truncated first-40 samples with larger totals cannot establish identity equality.
Canonical dataset identity and the exact recorded declared task must match;
equal selector/qid labels alone do not establish the same question. The task
basis contains the authored conditions/surfaces/operator, requested budget and
other QuestionSpec fields, excluding only the fixture oracle's known_answer and
known_answer_source. Oracle labels are a separate visible clause. A present known_answer requires
an observed boolean agreement; explicit known_answer=None means no oracle is
asserted, and its conditional agreement field may be absent or null. A missing
known_answer itself, absent agreement with a present oracle, or agreement asserted
without an oracle is unproved/refused. The CLI and comparisons use the same
comparison-owner helper for this rule. No oracle assertion is fabricated by an
unknown oracle. Changing a
fixture oracle description does not redefine the requested task. Missing or
mismatched task basis yields a scoped UNPROVED same-task claim, while other
observable clauses remain available. This compares recorded declaration identity,
not English paraphrase equivalence or record-local coded tensor/ordinal values.
Resolved numeric tolerance/recipe meaning is also a named substantive clause.
Stable content/row identity is separate from local ordinal/occurrence identity.
A represented range does not establish each underlying member row's identity.

J3's named claim compares retained answers/certificates/refusals and control
agreements, admitted counts and complete represented handle identities. Planner
decision and exact-occurrence differences are reported separately. J4 additionally
requires planner/tolerance-decision equivalence, retaining coefficients, clock precision,
predicted costs and chosen routes. P1 requires all four arms, required declaration
hashes and ingestion row/relation counts, plus within-arm cold/warm record digest
consistency. Different declaration hashes are retained rather than equated across
an intentionally different ablation. Answer equivalence alone proves neither
bit-for-bit system equivalence nor an unchanged cost model. Only explicit elapsed
diagnostics are outside addressed basis; there is no reader-side timer scrub.
The exact-occurrence clause names retained record/tree pins and local ordinals;
missing warm/cold occurrence evidence is explicitly unproved for that clause.

P3 `door_census.py` validates and observes the supplied receipt, but reports
`UNPROVED` until `WORK-atlas-census-evidence-20261008` binds the exact original
source/gold row identities and each budget's paid-for row set. Fresh ingestion
ordinals and count-derived reach fractions are not substitutes. P1/P3 refuse
replacing an existing result path. Arbitrary comparison inputs remain useful;
no frozen historical report is overwritten by these readers.

J3's fixed-output `j3_report.py` and `profile_three_sizes.py` are historical
writers, not current comparison entrypoints. Their early guard reads the selected
package's lightweight `FRONT_DOOR_RUN_RECORD`; a missing or non-v1 producer refuses
before manifest I/O, store deletion, numerical imports or warmup. A v1 format
match only permits explicit historical execution; it does not prove the original
complete source/runtime/input edition. See the dated J3 wave README for that
reproduction boundary. P3's fixed-input `update_report_c1.py` is import-safe but
retains its dated explicit historical body; this packet does not run it.
