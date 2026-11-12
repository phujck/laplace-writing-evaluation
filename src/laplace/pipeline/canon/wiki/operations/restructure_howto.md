# restructure(project, target_arc) — the how-to

The N→M section-set restructure as ONE declarative operator
(`laplace.pipeline.restructure`; CLI `scripts/restructure.py <project> <arc.json>
[--apply]`, dry-run default). Golden-mastered at FULL DICT EQUALITY against the
banked 2026-07-08 general-first restructure — rulings are ARC DATA, never code.

## The target_arc object (constants: `restructure.TARGET_ARC_*`)

```json
{ "sections":  [{"id", "title", "seed_from": ["old ids"], "job?", "notes?", "beats?", "spec?"}],
  "appendices": ["same shape - OPTIONAL; omitted = carried verbatim"],
  "overrides":  {"node id": "new section id"},
  "figure_overrides": {"fig id": "new section id"},
  "refs": {"carry": {"new sid": ["old sids"]}, "overrides": {"bibkey": "new sid"}},
  "park": ["node ids explicitly dropped - recorded, never stray"],
  "spine": {"order": ["node ids"], "narratives?": {}, "unset": []},
  "meta": {"merged into plan.meta"} }
```

## The laws

- An old section's default destination is the ONE new section claiming it in
  `seed_from`. Claimed twice = a declared SPLIT: every node of that section
  needs an override or a park, else the operator REFUSES listing the strays.
- Conservation: every pre-plan node lands exactly once (or is parked). Strays,
  dupes, and inventions are refusals, not warnings.
- Refs follow node-occurrence plurality (parked nodes don't vote); `carry`
  unions; key overrides win.
- Figures: override > own-node re-homing > old default; a homeless figure
  refuses (never a silent drop).
- `spine` emits L1 set-spine payloads — EMITTED, never self-applied: the caller
  (evolve, or the board's execute) applies them first and reconciles after.
- Cross-realm moves (body↔appendix) refuse in v1 — park + add-node instead.

## The run

Dry-run: `{new_plan, validation (the ONE plan validator), dirty diff
(cheap/expensive), spine_payloads, prose_bundles}` — nothing written. Apply:
freeze → plan+base regenerated through the L2 ledger semantics (fresh
generation: new base, cleared plan-friction) → `reconcile_section_refs`.
`prose_bundles` gathers each new section's %NODES spans from wherever its nodes
used to live — the re-integration substrate the builders consume.
