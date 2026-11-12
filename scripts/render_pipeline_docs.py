"""Render the schema-owned canon operations nodes FROM the live code.

The operational schemas used to live implicitly in four code sites and were
re-discovered by grep every session. Now ``pipeline.schema`` states them once
and this script projects them into canon bodies — the doc is generated, so it
CANNOT drift from the code. ``--check`` re-renders to memory and exits 1 on any
difference: that is the executable half of the rendered nodes' contract rows
(schema.OPERATION_CONTRACTS → contracts_verify.rendered_docs_fresh).

Usage: python scripts/render_pipeline_docs.py [--check]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from laplace.pipeline import schema  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WIKI = ROOT / "src" / "laplace" / "pipeline" / "canon" / "wiki" / "operations"

_HEADER = ("<!-- RENDERED from src/laplace/pipeline/schema.py + src/laplace/pipeline/verify.py "
           "by scripts/render_pipeline_docs.py - edit the SOURCE, never this file; "
           "the contracts gate fails on drift. -->")

# every rendered node carries the cluster's cross-links so the canon graph wires
# it (a rendered table with no edges is an orphan the canon health check flags)
_FOOTER = (
    "\n---\n\nThe operations cluster: "
    "[two-ledger system](canon://operations/two_ledger_system) · "
    "[plan schema + ops](canon://operations/projection_plan_schema) · "
    "[gate registry](canon://operations/gate_registry) · "
    "[operators](canon://operations/pipeline_operators) · "
    "[briefs + dispatch](canon://operations/briefs_and_dispatch) · "
    "[restructure how-to](canon://operations/restructure_howto). "
    "Axioms: [the engine domain](canon://domains/engine/axioms).\n")


def _fmt_set(s) -> str:
    return ", ".join(f"`{x}`" for x in sorted(s))


def render_projection_plan_schema() -> str:
    lines = [
        "# The projection-plan schema and the storyboard op vocabulary",
        "", _HEADER, "",
        "The L2 plan (`projection_plan.json`) is `meta` + `sections[]` + "
        "`appendices[]`. Section fields: " + _fmt_set(schema.SECTION_FIELDS) + ".",
        "A section's pinned nodes are `nodes_in_order` (legacy fallback `nodes`) — "
        "read them through `schema.section_nodes`, never by hand.",
        "",
        "## Typed plan meta",
        "",
        "`plan.meta` carries typed policy fields (set via the `set-meta` op, merge "
        "semantics): " + _fmt_set(schema.PLAN_META_TYPED) + ". The legacy free-text "
        "`builder_contract` folds into the brief POLICY channel until migrated.",
        "",
        "## The op vocabulary (the board's drag verbs)",
        "",
        "CHEAP (node SETS unchanged; zero-token recompile): "
        + _fmt_set(schema.CHEAP_OPS) + ".",
        "",
        "EXPENSIVE (section substrate changes; builder re-runs): "
        + _fmt_set(schema.EXPENSIVE_OPS) + ".",
        "",
        "`set-spine`/`unset-spine` live on the L1 ledger (the apex chain: `ord`, "
        "`narrative`); the storyboard bridge (`_coemit`/`spine_write`/"
        "`reconcile_section_refs`) mirrors plan placement into L1 `section_ref` "
        "slots.",
        "",
        "## The %-marker convention (the dirty-detection join key)",
        "",
        "A compiled fragment carries `% PLAN:<section-id>` once and "
        "`% NODES: <id> ...` per discharged span. A section is dirty iff its plan "
        "node-set differs from the set its fragment's markers discharge.",
        "",
        f"- node-id grammar the diff compares (kind-prefixed OR bare — pools mint "
        f"both, e.g. `RQ-CLM-043`, `ridge_lambda`): `{schema.POOL_ID_RE.pattern}`",
        f"- the identity guard (is a free-text reference a node at all?): "
        f"`{schema.NODE_ID_RE.pattern}` — kind-prefixed only, so a section stem or "
        f"bib key never becomes a claim/feedback anchor",
        f"- paragraph spec ids (`{schema.SPEC_ID_TAIL_RE.pattern}`) are prose "
        f"provenance, excluded from the diff",
        f"- support namespaces excluded from the diff: "
        + ", ".join(f"`{p}`" for p in schema.NON_CONTENT_PREFIXES)
        + " (figures ride `\\ref` and `figures[]`; citations ride `\\cite`)",
        "",
        "## Brief channels",
        "",
        "A brief is two fenced channels: `<!-- POLICY -->` configures the builder "
        "(never rendered; the `meta_leak` gate echo-scans prose for its text) and "
        "`<!-- OBJECT -->` is the only renderable substrate. The one contract line:",
        "",
        f"> {schema.BUILDER_CONTRACT_LINE}",
        "",
    ]
    return "\n".join(lines) + _FOOTER


def render_two_ledger_system() -> str:
    lines = [
        "# The two-ledger system",
        "", _HEADER, "",
        "**L1 — substrate / corpus-friction**: `corpus_friction/<project>.jsonl`. "
        "Append-only rewire records over the conceptric. Writer "
        "`corpus_ingest.rewire_add`; reducers `friction_current` (live node view) "
        "and `apply_overlay` (fold into a build).",
        "",
        "Record fields: " + _fmt_set(schema.REWIRE_FIELDS) + ".",
        "",
        "Admitted kinds: " + _fmt_set(schema.REWIRE_KINDS) + ".",
        "",
        "Auxiliary pass-through kinds (audit trail; reducers ignore): "
        + _fmt_set(schema.AUXILIARY_RECORD_KINDS) + ".",
        "",
        "`set-projection` values MERGE per record. Slots: "
        + _fmt_set(schema.PROJECTION_SLOTS) + ". `retired: true` retires the "
        "PROJECTION — the node and its history stay (deprecate projections, keep "
        "nodes). `framing` is POLICY-channel positioning guidance, never rendered "
        "into an essence or prose.",
        "",
        "**L2 — storyboard / projection-plan**: `projection_plan.base.json` "
        "(immutable origin) + `projection_plan.friction.jsonl` (append-only board "
        "ops) → reduced `projection_plan.json` (committed). Writer "
        "`storyboard.plan_write`; fold `storyboard._apply_op`.",
        "",
        "**The engine**: `laplace.pipeline.ledger` — one tolerant reader, one "
        "appender, one fold-reduce, `freeze()` (stamped snapshot + MANIFEST), and "
        "`transaction()` — the atomic dual-ledger write: on failure each file "
        "truncates back to its recorded byte offset (only the operator's own "
        "suffix; append-only stays true), on success a `txn` journal record lands. "
        "An operator that writes one ledger without the other inside a transaction "
        "is the drift class that kept being re-discovered; none remain.",
        "",
        "**The registry**: `laplace.pipeline.registry.resolve(name)` — every path "
        "(ledger, plan, briefs, glossary, feedback, versions, evolutions) for "
        "three layout families: `conceptric` (synthetics papers convention), "
        "`loop` (paper_eigen), `tex` (eigenengine). Unknown or path-shaped names "
        "resolve to None.",
        "",
    ]
    return "\n".join(lines) + _FOOTER


def render_gate_registry() -> str:
    from laplace.pipeline import verify as vf
    lines = [
        "# The gate registry — every verify check, and what it feeds",
        "", _HEADER, "",
        "`laplace_verify(checks=[...], project=<name>)` runs these. An UNKNOWN "
        "check name hard-fails the whole verify (no silent `pass: None` — the "
        "hole the banked evolution contracts fell through, closed 2026-07-08). "
        "Deliberate deferrals return `manual: true`.",
        "",
        "Default checks: " + _fmt_set(vf.DEFAULT_CHECKS) + ".",
        "",
        "| check | fitness feeds |",
        "|---|---|",
    ]
    for check, skill in sorted(vf.CHECK_SKILL.items()):
        lines.append(f"| `{check}` | {skill} |")
    lines += [
        "",
        "## The seven gates (the build-completion contract)",
        "",
        "1. **topology** — dangling edges (canon_weaver / graph health)",
        "2. **coherence** — under-described coarse nodes (conceptric_coherence "
        "renormalisation audit)",
        "3. **connectivity** — every CONTENT node reachable from a spine beat "
        "(`check_connectivity`); the synthetic containers minted above the spine "
        "(the `paper://` apex, the `references` shell) are structurally exempt and "
        "named in `structural_exempt`; `ratio` reports the reachable-content fraction",
        "4. **projection_labels** — every projectable node carries "
        "`projection.latex_label`; `fig:exp-*` also `data_source` "
        "(`check_projection_labels`)",
        "5. **glossary** — `projection.term` registry on every def; deprecated "
        "vocabulary hard-fails; GLOSSARY.md renders FROM the conceptric "
        "(`check_glossary`)",
        "6. **substrate** — every `res:`/`thm:`/`goal:` reaches `ref:`/`sup:` "
        "literature within 2 hops (`check_substrate`)",
        "7. **figures** — stranger-reproducible provenance blocks: "
        "generator/engine/data/banked-commit/seed (`check_figures`)",
        "",
        "Composites: `conceptric_build` = gates 3-7 + the plan validator + a "
        "clean dirty report — the one verdict the evolution contracts invoke. "
        "`meta_leak` = the object_not_artefact lexicon over compiled tex + the "
        "POLICY-channel echo scan. `contracts` = every operational surface has "
        "its canon node, is orient-reachable, and its executable verify runs "
        "green (claims → gates).",
        "",
    ]
    return "\n".join(lines) + _FOOTER


RENDERED = {
    WIKI / "projection_plan_schema.md": render_projection_plan_schema,
    WIKI / "two_ledger_system.md": render_two_ledger_system,
    WIKI / "gate_registry.md": render_gate_registry,
}


def main(check: bool) -> int:
    WIKI.mkdir(parents=True, exist_ok=True)
    drift = []
    for path, fn in RENDERED.items():
        body = fn()
        if check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != body:
                drift.append(path.name)
        else:
            path.write_text(body, encoding="utf-8")
            print(f"rendered {path.relative_to(ROOT)}")
    if check:
        if drift:
            print(f"DRIFT: {', '.join(drift)} - re-run scripts/render_pipeline_docs.py")
            return 1
        print("rendered docs fresh")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv[1:]))
