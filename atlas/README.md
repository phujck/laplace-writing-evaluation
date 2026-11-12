# atlas

Atlas is included as a local package in the standalone Writing repository.
Start with the [Writing code-base overview](../docs/writing-code-overview.md)
and [detailed source map](../docs/writing-source-map.md) to see how the app consumes it.

| Code | Responsibility |
|---|---|
| [src/atlas/record/](src/atlas/record/) | Source identity, extraction, ingestion, typed rows and witnesses |
| [src/atlas/reconstruction/](src/atlas/reconstruction/) | Packaged corpus-as-state query, obligation and context implementations |
| [src/atlas/lifted.py](src/atlas/lifted.py) | Qualified algorithm access and current-source receipts |
| [src/atlas/front/](src/atlas/front/README.md) | Front-door reconstruction, routing and output construction |
| [src/atlas/updown.py](src/atlas/updown.py), [src/atlas/spectral_pour.py](src/atlas/spectral_pour.py) | Graded UP/DOWN representation and spectral hierarchy |
| [src/atlas/store.py](src/atlas/store.py), [src/atlas/snapshot.py](src/atlas/snapshot.py) | Stored records and exact snapshot bytes |
| [src/atlas/bench/](src/atlas/bench/) | Benchmark protocols, retrieval arms, scoring and analysis |
| [src/atlas/sensorium/](src/atlas/sensorium/README.md) | Read-only provider/store projection |
| [pyproject.toml](pyproject.toml) | Local package and optional numerical dependency profiles |

The following phase account is retained historical architecture. The packaged
`release/acceptance.json` names actual Writing release checks;
the [campaign guide](../docs/writing-campaigns.md) locates retained experiments,
results and their runnable examples.

The record's navigation layer. Source stays authoritative and immutable; everything derived from
it — segmentations, encoders, projections, hierarchies, schemas — is a versioned, disposable,
measured projection over a frozen snapshot of that record.

Design: `DESIGN_2026-08-01_the-atlas.md` (repo root). Seal contract: `SEAL.md`.

The supported corpus-as-a-state subset is now `atlas.reconstruction`, inside this
same wheel. It holds fourteen existing canonical implementations, including the
shared query/obligation dataclasses and the optional numerical kernels. Its inert
namespace does not load numeric dependencies. The original paths under
`synthetics papers/corpus-as-a-state/reconstruction` are historical adapters;
experiments and old results remain historical. `_provenance.py` records original
source hashes, inventory purposes, declared local imports and preserved
function/class ASTs. Import/replay glue changed; numerical implementations did not.

Use `atlas.lifted.load(name)` for deliberate consumption and
`receipt(names, observe_current=False)` followed by `require_current(receipt)`
for a current-purpose source check. Front and grading retain their public lift
functions as delegates. Normal qualified imports own one module/class identity;
there is no research-directory fallback, module alias or hot reload. A receipt
reports first-adapter and current **disk** observations, never executed-source
attestation. Pre-imported code has an unknown start basis. Changed or unproved
required inputs refuse current use and supply a fresh-process revalidation route;
historical receipts remain readable. Each explicit current check hashes the
deduplicated requested local closure, package initializer and shared provenance map, with byte/time
costs attached. No global history scan or payload/result ledger is added.

Consumed receipts are validated against the selected schema/API, unique closure,
qualified modules and exact current-root paths, typed hashes/bytes and false loaded-byte
proof flag. A historical receipt from another root is readable but needs explicit
cold revalidation; relocation never silently becomes CURRENT. A small local lock
settles first observations and imports together so concurrent supported calls cannot
replace an observed basis with UNKNOWN. Python retains actual import/cache ownership.
The adapter interprets its versioned receipt contract; it is not an algorithm source
attestation. Its own loaded implementation is outside this deliberately bounded
algorithm/initializer/provenance coverage.

Core requirements remain NumPy only. Query-plan, query-obligation and context
modules need no heavy extras; `gpu_budget` needs Torch even for its CPU integer
budget helper. Optional extras `reconstruction`, `reconstruction-kernels` and
`reconstruction-spectral` declare Torch/regex, Torch/Triton and Torch/CUDA12 CuPy
respectively. Select an appropriate build/device explicitly; these declarations
do not prove device execution or numerical theory. Install only when requested,
for example `python -m pip install './atlas[reconstruction]'`. There is no startup
installation or silent device fallback. Broken selected code fails with its actual
cause; an absent optional dependency is named as unavailable. Source and installed
prefix imports use this same package boundary; the old research sibling cannot
redirect either one. See `tests/test_lifted_boundary.py` for bounded controls;
whole FrontDoor execution and persisted-tree currentness are separate obligations.

Cold entry: `PYTHONPATH=src /usr/bin/python3 -m atlas.entry --json` reads the
configured store, serves an 8192-byte capped page, and supplies commands for exact
event-byte descent and older pages. Generation roots come from completed stored
generations. Unreached dataset, snapshot, or bench registrations are typed issues;
the entry states every omission. It does not discover snapshots by listing stores.

For a known snapshot, `atlas.snapshot.load_snapshot(path).read_node_bytes(node_id)`
reads verified blob bytes. If a blob is absent, a clean manifest permits local
`git show <commit_sha>:<path>` regeneration, hash verification and blob caching.
A dirty manifest or unreachable pinned Git raises `SnapshotRegenerationRefused`
with the door and remedy. Read-only cache failures are exposed in
`bundle.cache_refusals`; verified bytes remain readable in that process.

**Phases 1, 2 and 3 are what is here**: the snapshot bundle, the segmentation layer, the
deterministic encoders plus a lazy bge adapter, bench v2 with its Tier-1 baselines
(`bench/README.md`), and Phase 3's two comparator arms — `raptor` (RAPTOR-class collapsed-tree
retrieval at a declared summary budget, the one arm that pays a model bill at fold time) and
`incumbent_arch` (the engine's own architecture rebuilt over the snapshot). No axes, no fibres and
no atlas ablation arms — those phases land later and are absent rather than stubbed.

Phase 3's pre-registered stop **fired**: the engine's measured advantage is a wake advantage, not
a retrieval advantage. `evidence/ATLAS_PHASE3_2026-08-01_stop-condition.md`.

## Layout

```
src/atlas/
  ids.py errors.py       one hashing law (sha256 over canonical JSON); every degrade a named refusal
  schema.py              SnapshotNode / RecordSnapshot / Span / SegmentationGeneration
  store.py snapshot.py   append-only jsonl + content-addressed blobs; bundle verify
  segment/               markdown / code / structured / tex / fallback, and the three laws
  encoders/              deterministic (Hash, Synthetic) + the lazy bge_onnx adapter
  bench/                 bench v2: scoring (ported), universe, cost, protocol, task, freeze,
                         arms/, runner, summary, figures — see bench/README.md
                         Phase 3: contamination.py (the freeze-time atom-density tripwire),
                         stats.py (the seeded paired bootstrap), cluster.py (silhouette-spectral
                         splitting in numpy), raptor_fold.py (the RAPTOR tree and its bill)
  tools/                 build_spans, export_verify, segment_sweep, freeze_tasks, run_bench,
                         re_anchor, raptor_fold (THE DISPATCH SITE — explicit model stamp),
                         assert_tier1_parity (the determinism re-run)
bench/                   frozen task bundles, banked runs, live-surface records
stores/snapshots/        exported bundles: metadata travels; blobs/ and spans.jsonl are
                         gitignored and regenerable — from commit_sha when the manifest's
                         tree_dirty is false, otherwise the bundle carries dirty_nodes_hash
                         naming the delta that commit_sha does not account for
stores/projections/      dense vector caches, content-keyed: floats gitignored, the generation
                         manifest committed
stores/raptor/           RAPTOR folds: summaries.jsonl + manifest.json + tree.json COMMITTED
                         (model-written derived text over unsealed record — it is what the fold's
                         model bill bought), only vectors.npy gitignored
tests/                   seal, ids, schema, store, snapshot, segment, encoders, bench
```

## Upstream development tests (reference only)

The commands and suite paths in this section describe the full upstream development
checkout. The standalone Writing mirror includes the Atlas implementation and
selected application smoke checks, rather than the full historical Atlas test
suite and snapshot tooling. Follow the [portable startup guide](../docs/writing-agent-start.md)
for runnable checks in the mirror; do not treat absent upstream test/script paths
as missing app imports.

The package is not installed. Both suites run from the repo root with the two source trees on
the path:

```sh
PYTHONPATH=src python3 -m pytest -q atlas/tests
PYTHONPATH=src python3 -m pytest -q tests/test_atlas_seal.py
```

The root `pyproject.toml` already sets `pythonpath = ["src", "atlas/tests", "tests"]` (src holds laplace and atlas since core consolidation R2, 2026-10-19; this distribution's pyproject reads `../src`) and
`testpaths = ["tests", "atlas/tests"]`, so a plain `python3 -m pytest -q` from the repo root
runs both suites with no environment variable at all. The `PYTHONPATH` form above is for running
the tools by hand or from a different working directory.

Unit tests use no model, no network and no snapshot on disk. A test asserts `fastembed` is
absent from `sys.modules` after the suite; if that fails, an import moved to module scope.

## The Phase 1 gate

Four commands, in order. The first is on the laplace side of the seal and imports laplace; the
rest are atlas-side and import only atlas.

```sh
# 1. export a snapshot of the record (writes atlas/stores/snapshots/<hex>/).
#    Refuses a dirty working tree: a bundle exported from one is not rebuildable from its
#    commit_sha. --allow-dirty exports anyway and records tree_dirty + dirty_nodes_hash.
python3 scripts/export_atlas_snapshot.py

# 2. verify it: manifest id, blob bytes, seal report zeros
PYTHONPATH=src python3 -m atlas.tools.export_verify atlas/stores/snapshots/<hex>

# 3. segment it: writes spans.jsonl + segmentation.json beside the bundle
PYTHONPATH=src python3 -m atlas.tools.build_spans atlas/stores/snapshots/<hex> \
    --target-tokens 384

# 4. sweep the target span size
PYTHONPATH=src python3 -m atlas.tools.segment_sweep atlas/stores/snapshots/<hex> \
    --sizes 256,384,512
```

Determinism is the gate that matters: run (1) twice over an unchanged tree and the
`snapshot_id` must be identical; run (3) twice and the `generation_id` must be identical.
An instrument whose ids move under a clock cannot measure anything.

For the encoder timing arm of the sweep, point `LAPLACE_EMBED_MODEL_DIR` at the extracted
bge-small model directory (the one containing `model_optimized.onnx`). Without it the arm is
skipped with a printed reason, never silently dropped.

## The three laws of segmentation

Every segmenter is bound by them and `atlas.segment.segment_bytes` checks all three on every
node:

* **coverage** — leaf spans partition the node's bytes exactly. Silent truncation is
  structurally impossible, not merely discouraged.
* **cap** — no leaf span over `hard_cap_tokens` (512, the bge window) unless it names why it
  could not be split; those are counted in `oversize_spans`.
* **structure** — a structured source never reaches the raw fallback. JSON/JSONL bind strictly;
  YAML binds to a bounded column-zero key scan whose limits are stated and counted.

Spans nest — a heading section over its subsections, a JSON object over its members — and the
partition is the leaf layer. Token estimates are bytes/4 rounded up, the repo's canonical figure.
