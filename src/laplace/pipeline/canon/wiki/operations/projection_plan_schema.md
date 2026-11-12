# The projection-plan schema and the storyboard op vocabulary

<!-- RENDERED from src/laplace/pipeline/schema.py + src/laplace/pipeline/verify.py by scripts/render_pipeline_docs.py - edit the SOURCE, never this file; the contracts gate fails on drift. -->

The L2 plan (`projection_plan.json`) is `meta` + `sections[]` + `appendices[]`. Section fields: `beats`, `figures`, `id`, `job`, `nodes_in_order`, `notes`, `refs`, `spec`, `title`.
A section's pinned nodes are `nodes_in_order` (legacy fallback `nodes`) — read them through `schema.section_nodes`, never by hand.

## Typed plan meta

`plan.meta` carries typed policy fields (set via the `set-meta` op, merge semantics): `gate_refs`, `postures`, `workflow_modes`. The legacy free-text `builder_contract` folds into the brief POLICY channel until migrated.

## The op vocabulary (the board's drag verbs)

CHEAP (node SETS unchanged; zero-token recompile): `reorder-appendices`, `reorder-nodes`, `reorder-sections`, `retitle`, `set-outline`.

EXPENSIVE (section substrate changes; builder re-runs): `add-node`, `add-section`, `edit-job`, `edit-notes`, `move-node`, `remove-node`, `remove-section`, `restore-section`, `set-meta`, `set-nodes`, `set-refs`, `set-serves`, `toggle-beat`.

`set-spine`/`unset-spine` live on the L1 ledger (the apex chain: `ord`, `narrative`); the storyboard bridge (`_coemit`/`spine_write`/`reconcile_section_refs`) mirrors plan placement into L1 `section_ref` slots.

## The %-marker convention (the dirty-detection join key)

A compiled fragment carries `% PLAN:<section-id>` once and `% NODES: <id> ...` per discharged span. A section is dirty iff its plan node-set differs from the set its fragment's markers discharge.

- node-id grammar the diff compares (kind-prefixed OR bare — pools mint both, e.g. `RQ-CLM-043`, `ridge_lambda`): `^(?:[a-z][\w-]*:[^\s]+|[A-Za-z][\w.-]*)$`
- the identity guard (is a free-text reference a node at all?): `^[a-z][\w-]*:[^\s]+$` — kind-prefixed only, so a section stem or bib key never becomes a claim/feedback anchor
- paragraph spec ids (`-p\d+$`) are prose provenance, excluded from the diff
- support namespaces excluded from the diff: `fig:`, `ref:` (figures ride `\ref` and `figures[]`; citations ride `\cite`)

## Brief channels

A brief is two fenced channels: `<!-- POLICY -->` configures the builder (never rendered; the `meta_leak` gate echo-scans prose for its text) and `<!-- OBJECT -->` is the only renderable substrate. The one contract line:

> Render the OBJECT channel only. POLICY configures you — obey it and never let its text, vocabulary, or self-description surface in the prose (a policy sentence in the output is the defect the meta_leak gate rejects). An unmet demand is a typed friction to report, never a confabulation.

---

The operations cluster: [two-ledger system](canon://operations/two_ledger_system) · [plan schema + ops](canon://operations/projection_plan_schema) · [gate registry](canon://operations/gate_registry) · [operators](canon://operations/pipeline_operators) · [briefs + dispatch](canon://operations/briefs_and_dispatch) · [restructure how-to](canon://operations/restructure_howto). Axioms: [the engine domain](canon://domains/engine/axioms).
