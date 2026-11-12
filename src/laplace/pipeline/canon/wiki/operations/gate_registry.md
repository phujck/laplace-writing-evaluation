# The gate registry — every verify check, and what it feeds

<!-- RENDERED from src/laplace/pipeline/schema.py + src/laplace/pipeline/verify.py by scripts/render_pipeline_docs.py - edit the SOURCE, never this file; the contracts gate fails on drift. -->

`laplace_verify(checks=[...], project=<name>)` runs these. An UNKNOWN check name hard-fails the whole verify (no silent `pass: None` — the hole the banked evolution contracts fell through, closed 2026-07-08). Deliberate deferrals return `manual: true`.

Default checks: `citations`, `crossref`, `epistemic`, `voice`.

| check | fitness feeds |
|---|---|
| `canon` | canon_weaver |
| `conceptric_build` | conceptric_coherence |
| `connectivity` | conceptric_coherence |
| `contracts` | orchestrated_generation |
| `crossref` | global_weaver |
| `empirical` | empirical_ledger |
| `epistemic` | epistemic_ledger |
| `evolution` | conceptric_evolution |
| `figures` | figure_standard |
| `glossary` | conceptric_coherence |
| `meta_leak` | orchestrated_generation |
| `projection_labels` | conceptric_coherence |
| `substrate` | literature_scout |
| `voice` | orchestrated_generation |

## The seven gates (the build-completion contract)

1. **topology** — dangling edges (canon_weaver / graph health)
2. **coherence** — under-described coarse nodes (conceptric_coherence renormalisation audit)
3. **connectivity** — every CONTENT node reachable from a spine beat (`check_connectivity`); the synthetic containers minted above the spine (the `paper://` apex, the `references` shell) are structurally exempt and named in `structural_exempt`; `ratio` reports the reachable-content fraction
4. **projection_labels** — every projectable node carries `projection.latex_label`; `fig:exp-*` also `data_source` (`check_projection_labels`)
5. **glossary** — `projection.term` registry on every def; deprecated vocabulary hard-fails; GLOSSARY.md renders FROM the conceptric (`check_glossary`)
6. **substrate** — every `res:`/`thm:`/`goal:` reaches `ref:`/`sup:` literature within 2 hops (`check_substrate`)
7. **figures** — stranger-reproducible provenance blocks: generator/engine/data/banked-commit/seed (`check_figures`)

Composites: `conceptric_build` = gates 3-7 + the plan validator + a clean dirty report — the one verdict the evolution contracts invoke. `meta_leak` = the object_not_artefact lexicon over compiled tex + the POLICY-channel echo scan. `contracts` = every operational surface has its canon node, is orient-reachable, and its executable verify runs green (claims → gates).

---

The operations cluster: [two-ledger system](canon://operations/two_ledger_system) · [plan schema + ops](canon://operations/projection_plan_schema) · [gate registry](canon://operations/gate_registry) · [operators](canon://operations/pipeline_operators) · [briefs + dispatch](canon://operations/briefs_and_dispatch) · [restructure how-to](canon://operations/restructure_howto). Axioms: [the engine domain](canon://domains/engine/axioms).
