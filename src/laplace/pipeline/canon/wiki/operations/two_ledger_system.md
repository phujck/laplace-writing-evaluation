# The two-ledger system

<!-- RENDERED from src/laplace/pipeline/schema.py + src/laplace/pipeline/verify.py by scripts/render_pipeline_docs.py - edit the SOURCE, never this file; the contracts gate fails on drift. -->

**L1 — substrate / corpus-friction**: `corpus_friction/<project>.jsonl`. Append-only rewire records over the conceptric. Writer `corpus_ingest.rewire_add`; reducers `friction_current` (live node view) and `apply_overlay` (fold into a build).

Record fields: `axis`, `by`, `essence`, `id`, `kind`, `narrative`, `node`, `node_kind`, `ord`, `parent`, `projection`, `rationale`, `ref`, `rel`, `status`, `supersedes`, `target`, `ts`, `value`.

Admitted kinds: `add-edge`, `add-node`, `confirm-edge`, `delete-node`, `edit-essence`, `move-node`, `reclassify`, `remove-edge`, `retype-edge`, `set-kind`, `set-projection`, `set-source`, `set-spine`, `set-status`, `unset-spine`.

Auxiliary pass-through kinds (audit trail; reducers ignore): `data`, `fork`, `friction`, `schematic`, `txn`.

`set-projection` values MERGE per record. Slots: `data_source`, `framing`, `latex_label`, `mathematics`, `obligation`, `provenance`, `result_bindings`, `retired`, `section_ref`, `term`, `title`. `retired: true` retires the PROJECTION — the node and its history stay (deprecate projections, keep nodes). `framing` is POLICY-channel positioning guidance, never rendered into an essence or prose.

**L2 — storyboard / projection-plan**: `projection_plan.base.json` (immutable origin) + `projection_plan.friction.jsonl` (append-only board ops) → reduced `projection_plan.json` (committed). Writer `storyboard.plan_write`; fold `storyboard._apply_op`.

**The engine**: `laplace.pipeline.ledger` — one tolerant reader, one appender, one fold-reduce, `freeze()` (stamped snapshot + MANIFEST), and `transaction()` — the atomic dual-ledger write: on failure each file truncates back to its recorded byte offset (only the operator's own suffix; append-only stays true), on success a `txn` journal record lands. An operator that writes one ledger without the other inside a transaction is the drift class that kept being re-discovered; none remain.

**The registry**: `laplace.pipeline.registry.resolve(name)` — every path (ledger, plan, briefs, glossary, feedback, versions, evolutions) for three layout families: `conceptric` (synthetics papers convention), `loop` (paper_eigen), `tex` (eigenengine). Unknown or path-shaped names resolve to None.

---

The operations cluster: [two-ledger system](canon://operations/two_ledger_system) · [plan schema + ops](canon://operations/projection_plan_schema) · [gate registry](canon://operations/gate_registry) · [operators](canon://operations/pipeline_operators) · [briefs + dispatch](canon://operations/briefs_and_dispatch) · [restructure how-to](canon://operations/restructure_howto). Axioms: [the engine domain](canon://domains/engine/axioms).
