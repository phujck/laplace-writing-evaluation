# The pipeline operators — evolve, restructure, propagate

The generic operator set over any registered project (`laplace.pipeline.registry`),
replacing the bespoke per-evolution scripts (the calcification class the
2026-07-08 infra mandate retired). Every operator: a library function, a thin
CLI (`scripts/evolve.py` / `restructure.py` / `propagate.py`, dry-run by
default), a verify hook, and tests including a golden master that re-derives a
banked real run from its own inputs.

## evolve(project, evolution_dir)

Execute an evolution CONTRACT (`evolution_plan.json`, either banked shape:
substrate-led mints/reshapes/deprecations, or storyboard-led spine-reorder +
plan regeneration) as the six steps of
[conceptric_evolution](canon://skills/conceptric_evolution), mechanised:
freeze → records via the L1 write gate inside ONE `ledger.transaction` →
round-trip diff against the contract's own enumeration — exact or the
transaction rolls back byte-identically. The laws hold in code: fold by ledger
never replay · deprecate projections keep nodes · the plan is downstream ·
supersessions are new dated files. Verify: `laplace_verify(checks=['evolution'],
project=...)` — pass = round-trip exact OR already applied (a banked contract
correctly refuses a second replay).

## restructure(project, target_arc)

The N→M section-set restructure (resequence, merge, split, re-home, refs
redistribution) as ONE declarative operator — the generalisation of the
2026-07-08 general-first bespoke scripts. The arc is DATA: ordered sections
with `seed_from` provenance, explicit node re-homing overrides (human rulings
as inputs, never code), a refs plurality carry-forward rule, figures following
their nodes. Dry-run previews the new plan + validation + dirty diff + prose
re-integration bundles; apply freezes, regenerates plan+base through the L2
ledger semantics, and reconciles section_refs. See
[the how-to](canon://operations/restructure_howto).

## propagate(project, since | feedback)

The minimal-change router: from an L1 change-set (byte offset or record id) or
the intake/feedback ledger, compute exactly which sections are dirty (membership
via the %NODES join keys + section_ref re-homing, classified cheap/expensive)
and emit the TYPED WORKLIST — a dependency DAG over
`{derive, simulate, figure, mint, prose}` where missing substance blocks the
prose that needs it (28 missing-derivation records → 28 derive items with their
downstream prose, proven live). Pure read: executing items is
[dispatch](canon://operations/briefs_and_dispatch)'s job. A feedback kind
without a routing in `schema.KIND_TO_WORK` raises by name — new kinds cannot
arrive silently.

## sewup — the standing up-operator

`scripts/sewup.py`: render the schema-owned canon → suite → canon graph health
→ reembed (the deposit; remote auto-allows the full spectral run) → contracts →
the cold probes. The close's mechanical half: work that does not fold back into
the global does not pass. Run it at every close and after any structural
change; `--no-embed` for a quick gate pass, `--only step` to compose.

## The shared floor

`ledger.freeze()` (stamped snapshot + manifest) before any mutation;
`ledger.transaction()` for every dual-ledger write (byte-offset rollback, txn
journal); the registry for every path; `schema` for every record shape. An
operator that bypasses any of these is the drift class this node exists to end.
