# The code base

This is the short orientation for a person or agent arriving at the repository.
For a blind software assessment, begin with the [reviewer guide](../REVIEWER_GUIDE.md).
Then follow the linked code and the detailed [source map](writing-source-map.md).
Where the source, packages, runtime, writable state, caches and current coordination live, and how each is set up,
launched and updated, is in [operational homes](operational-homes.md).

## The system description

Everything this repository owns is described once, in
[src/laplace/system/description.json](../src/laplace/system/description.json), and read
only through [laplace.system](../src/laplace/system/__init__.py). The design follows from
the reflexive construction the system implements: its parts, their relationships, the
operations they carry and the evaluators that judge them are themselves qualified,
inspectable objects, so a change can select the consumers its imports reach and leave the
rest outside that structural cone.

- **Core** owns the common qualified identity and record mechanics. A **domain** owns
  meaningful state, transformations and adequacy criteria and may use core and the
  domains it declares. An **adapter** is an inbound door: native tools, HTTP, desktop or
  browser, command line, distribution, documentation. Nothing imports upward except the
  retained boundaries below, each with exact edges or consumers and a retirement condition.
- `python -m laplace.system check` measures every claim against the tree: one owner per
  file, the layer law, the retained lists, the shipped distributions, each capability's
  references and this section. `owner PATH`, `cone PATH...` (the affected owners, importing
  modules, evaluators, explanations and capabilities, and the subsystems structurally outside
  that import cone) and `capability ID` are the bounded ways to descend.
- Current limits: the domain relations are measured and declared, not yet acyclic; the
  cone is structural (import-level): outside it is not an independent-review CURRENT/STALE
  standing or semantic sufficiency, and a consumer reached through a callable or a file is
  found by its evaluator, not by the cone; the distribution checks read the declarations
  and prove no archive complete; a curated export carries this description (its front door
  links it) but omits tests and documents the full check measures, so the full check is an
  upstream check. Four capability records describe the reached dispatch-return admission,
  scoped progress, owner-discovery and source-contract routes; they do not establish four
  complete app-owned self-modification loops. The whole organisation,
  the retained edges and facade consumers, evidence/coordination storage and native
  continuation remain open.

<!-- laplace.system: subsystems (generated; python -m laplace.system front-door) -->
| Subsystem | Kind | Owns | Uses |
|---|---|---|---|
| `core.identity` | core | Qualified identity, revision, owner-mutation receipt, schema-version and lock mechanics, the public body-reference contract with its codec, retention, bounded reads and budget, and the public repository perimeter, shared by every owner; and this system description itself. | `core.runtime` |
| `core.runtime` | core | Where and how the system runs: one resolver per qualified root (source tree, package resources, serving checkout, state home), the declared runtime selection the launcher loads before Laplace is importable, bounded process work (manifest one-liners, the default-off watchdog) and path-scoped versioning. | — |
| `core.records` | core | Durable records with no store's own vocabulary: the intent-then-execute journal and bank_row (stamp law, closed edge vocabulary), JSONL row reading, captured incremental log reading with exact selected rows and cut tokens, and the one row-graph walker over a scope its domain supplies. | `core.identity`, `core.runtime` |
| `domain.authoring` | domain | Writing sessions and turns: the conversation journal (records fold, index and bank), admission, context, execution, steering, the live registry, dispatched children and parent continuation, provider processes and operating knowledge. Optional Source commissions use the existing Writing journal/index and native private incoming carrier for admitted-call/app/session accounting and bounded stop/drain. | `core.identity`, `core.records`, `domain.engine`, `domain.manuscript`, `domain.pipeline`, `domain.projects`, `domain.representation`, `domain.research`, `domain.work` |
| `domain.manuscript` | domain | Manuscript source, proposals and their application, reconciliation, documents, templates, style, structure, reader plan and builds. | `domain.authoring`, `domain.engine`, `domain.pipeline`, `domain.projects`, `domain.representation`, `domain.research`, `domain.work` |
| `domain.projects` | domain | Projects and their homes: the manuscript-project library, configured source repositories, storage, artifacts, portability of exported locations and project lifecycle. | `domain.authoring`, `domain.engine`, `domain.manuscript`, `domain.pipeline`, `domain.research`, `domain.work`, `core.records` |
| `domain.work` | domain | Work: durable tasks, recursive navigation, review obligations and synthesis, delivery to recipients, development-source grants, activity and author history. | `domain.authoring`, `domain.engine`, `domain.manuscript`, `domain.pipeline`, `domain.projects`, `domain.representation`, `domain.research` |
| `domain.research` | domain | Research: inputs, records, producers, runs and their supervision, literature and references, figures, formal checks, concepts and corpus statistics, SuperARC. | `domain.engine`, `domain.manuscript`, `domain.pipeline`, `domain.projects`, `domain.representation`, `domain.work` |
| `domain.representation` | domain | Representation and reconstruction: the Atlas library (records, segmentation, projections, reconstruction, benchmarks), its two reviewed Writing boundaries, seats, attention, embeddings and device policy. Writing body custody (content-addressed public bodies in the Atlas BlobStore) belongs here. | `domain.authoring`, `domain.engine`, `domain.pipeline`, `domain.work` |
| `domain.pipeline` | domain | The manuscript production pipeline and canon: registry, authoring state, workflow and dispatch schemas, canon loader and wiki, the writing organ, verification and calibration dials. | `domain.authoring`, `domain.engine`, `domain.manuscript`, `domain.representation`, `domain.research`, `domain.work`, `core.records`, `domain.projects` |
| `domain.engine` | domain | The Laplace engine itself: wake and close, memory and soul organs, the self-corpus and its obligation ledger and row graph (engine_ledger, qualifying core.records), seats, lenses, judgement, telemetry and assessment, descent and the Aisthesis front read models. The selected Source-kernel input adapter consumes explicit retained Work publications; historical engine obligation reads remain separate from canonical Work. | `domain.manuscript`, `domain.pipeline`, `domain.representation`, `domain.research`, `domain.work` |
| `adapter.sdk` | adapter | The installed Python entry (laplace.sdk): a local caller starts at the declared system entry and follows owner-returned handles to the Work affecting a subsystem, with its root's own authority; it composes laplace.system and work.owner_discovery and adds no rule. | — |
| `adapter.native` | adapter | The agent door: native tool admission, the operation table, delivery, declarations, schemas, verbs and help, and the generators of those declarations. | — |
| `adapter.http` | adapter | The web door: the scanner server, route entries and facades, the authoring and research HTTP doors, served pages and their declared preconditions. | — |
| `adapter.desktop` | adapter | The human desktop and browser door: the managed service, the native window, launchers and the browser workspace assets. | — |
| `adapter.cli` | adapter | The command-line door: repository scripts and developer tools. | — |
| `adapter.distribution` | adapter | What is shipped and run: package and lock declarations, test configuration, runtime profiles and the container recipes. | — |
| `adapter.explanation` | adapter | The human explanation door: the documentation set, linked from each subsystem and capability it explains. | — |

Retained boundaries (each list only shrinks; `python -m laplace.system check` fails on a new one):

- **owners-read-door-declarations** (5 edges, owner `adapter.native`): Five owner reads put the native door's own spelling of a next call, or its declared prose, inside the result they return, so they read it from the door's tables: the source read's write recipe (pipeline.authoring.inspect -> writing_declarations.source_write_guidance), a Work action's declared effects and summary (project_work_views._declared), author-update and control read handles (provider_updates._read_handle -> writing_verbs.native_example), a restructure action's native request (reader_restructure.action -> writing_verbs.from_owner_call), and the operating brief's catalogue, homes and help (writing_operating.build and tool_contract). The other nine owners of this group now hold and admit their own contracts (core.admission, writing_schemas reading owner contracts, review_http, the injected interface view). Retire when: The door that delivers each result composes the spelling of the next call when it renders the owner result, or the spelled fact (recipe, declared effects) moves to the owner that declares it; each converted owner is removed here.
- **owners-calling-the-native-door** (2 edges, owner `adapter.native`): The provider session hosts the native door as its only tool. The operating brief describes the gateway (writing_operating.build, session_policy, session_workspace and tool_contract read writing_tools.specification, READS and WRITES), and WritingTurn's in-process transports serve its calls (writing_provider calls writing_tools.call, tool_failure, bank_failure and specification). Project lifecycle and the project library no longer call the door: they bank through writing.records. Retire when: turn_admission.start_turn receives the tool door from each turn starter (authoring_http, writing_tools, dispatch_execution, work_delivery) and WritingTurn calls only that door; the brief takes the door's contract from the same object. Not exercised in this source commission, because provider sessions are outside its validation.

Capabilities described end to end (contract, code, help, explanation, evaluator, consumers, observables):

- `work.dispatch-return-admission` (owner `domain.work`): A dispatched packet's typed return is admitted against its declared contract: every input, source and continuation pin must name bytes an owner admits, and the return's standing (COMPLETE, INVALID-RETURN, ...) is what the Work parent and judge consume.
- `core.scoped-progress` (owner `core.identity`): An operation needs only its authority and the current basis its effect consumes; a changed consulted observation becomes a typed local review obligation on the result, a result carries its grade, and aggregation counts only consumed children.
- `work.owner-discovery` (owner `domain.work`): A caller given only the system entry, a task or affected subsystem and its actual scope finds the responsible owner, the bound Work affecting it with qualified standing, activity, next actions and evidence handles, then summarises upward and follows lateral relations; owner bindings live in the Work ledger, separately revisioned, and grant nothing.
- `work.source-contracts` (owner `domain.work`): An operation's owner declares its contract as segments of the facts its code runs and its explicit consumers as typed implements/consumes/projects/evaluates/explains/contains relations; one generic resolver judges each consumer against the segment bases it was accepted on, so a changed segment makes only its consumers locally pending review.
- `representation.source-publication` (owner `domain.representation`): One selected Source contribution to the active publication, with exact request recovery and retained typed facts; a source declaration of this operation is distinct from its publication.
- `work.review-evidence` (owner `domain.work`): Read one Work's review obligation counts, explicitly enumerate a bounded list and inspect selected evidence routes at the same consumed observation. Counts, metadata expansion and body reading remain separate.
- `work.provenance` (owner `domain.work`): Read the actual recorded path from a selected Task to its conversations, replies, artifacts, reviews and delivery evidence, separately from supporting availability and direct completion standing.
- `pipeline.workflow-history` (owner `domain.pipeline`): Read complete retained workflow prefixes through bounded metadata and exact saved-body pages, then deliberately hand over complete selected lineage to a fresh ordinary recipient under existing local custody and resource bounds.
<!-- /laplace.system -->

## The three parts

**The backend owns the work.** It resolves projects and source identities, prepares
agent context, runs admitted turns, applies guarded changes, supervises research
and builds, and records what happened. Start with the [Python package](../src/laplace/README.md)
and the [Writing backend owners](../src/laplace/writing/README.md).

**The frontend makes that work usable.** The browser workspace, manuscript editor,
reader plan, Research, Work and inspectors call the same backend owners used by
agents. Start with the [frontend map](../src/laplace/web/static_shared/README.md).

**Atlas supplies representation and reconstruction machinery.** Its source lives
in [src/atlas/](../src/atlas/) beside `src/laplace/`; [atlas/](../atlas/README.md)
holds its distribution declaration, README and tests and builds its wheel from that
source. The two wheels are disjoint (`laplace-engine` ships `laplace*` only, `atlas`
ships `atlas*` only). The Writing App uses Atlas's qualified modules and provenance
checks; install both local packages (`pip install ./atlas .`).

## Where to go

| You want to understand or change… | Start here |
|---|---|
| Browser/server startup and the selected workspace | [writing_server.py](../src/laplace/web/writing_server.py), [scanner.py](../src/laplace/web/scanner.py); [startup guide](writing-agent-start.md) |
| Managed Linux desktop service and native window | [writing_app.py](../src/laplace/desktop/writing_app.py), [native_writing.py](../src/laplace/desktop/native_writing.py); [server and platform guide](writing-browser-server.md) |
| Agent tools, schemas, roles and permissions | [writing_tools.py](../src/laplace/native/tools.py), [writing_declarations.py](../src/laplace/native/declarations.py), [identity_doors.py](../src/laplace/core/identity_doors.py) |
| Context, turn admission, execution and steering | [turn_context.py](../src/laplace/writing/turn_context.py), [turn_admission.py](../src/laplace/writing/turn_admission.py), [turn_execution.py](../src/laplace/writing/turn_execution.py), [turn_control.py](../src/laplace/writing/turn_control.py) |
| Codex/Claude process adapters | [writing_provider.py](../src/laplace/writing/provider.py) |
| Complete selected project-data handover, without application or provider state | [project_handover.py](../src/laplace/projects/project_handover.py), [shared selection](../src/laplace/projects/project_data.py); [Python/CLI guide](project-data-handover.md) |
| Saved workflow definitions and app run/step facts | [workflow_definitions.py](../src/laplace/pipeline/workflow_definitions.py), [workflow_dispatch.py](../src/laplace/writing/workflow_dispatch.py); [editor guide](writing-workflow-editor.md) |
| Projects, manuscript selection and file locations | [writing_projects.py](../src/laplace/projects/library.py), [pipeline/registry.py](../src/laplace/pipeline/registry.py), [manuscript_source.py](../src/laplace/manuscript/manuscript_source.py) |
| Applying a proposed edit and recovering conflicts | [source_application.py](../src/laplace/manuscript/source_application.py), [reconciliation.py](../src/laplace/manuscript/reconciliation.py), [consulted-read recovery](writing-consulted-read-recovery.md), [scoped progress](scoped-progress.md) |
| Work, independent review, synthesis and child tasks | [project_work.py](../src/laplace/work/project_work.py), [project_work_review.py](../src/laplace/work/project_work_review.py); [lifecycle guide](writing-work-review-lifecycle.md) |
| Research inputs, results, producers and runs | [research_surface.py](../src/laplace/web/research_surface.py), [research owners](../src/laplace/writing/README.md#research-and-evidence) |
| Reader plan, concepts and typed relationships | [project_structure.py](../src/laplace/manuscript/project_structure.py), [concepts_surface.py](../src/laplace/research/concepts.py), [reader_plan.py](../src/laplace/manuscript/reader_plan.py) |
| Literature, figures, formal checks and PDF builds | [literature.py](../src/laplace/research/literature.py), [visuals_surface.py](../src/laplace/research/visuals_surface.py), [formal_surface.py](../src/laplace/research/formal_surface.py), [build jobs](../src/laplace/manuscript/build_jobs.py), [publication editions](../src/laplace/manuscript/publication_editions.py) |
| Conversation history and saved evidence bytes | [records/](../src/laplace/writing/records/), [artifacts.py](../src/laplace/projects/artifacts.py) |
| The browser workspace and manuscript editor | [frontend guide](../src/laplace/web/static_shared/README.md), [workspace.mjs](../src/laplace/web/static_shared/workspace.mjs), [walk.mjs](../src/laplace/web/static_shared/walk.mjs) |
| Reproducing the research campaigns | [campaign guide](writing-campaigns.md), [paper collection](writing-paper-collection.md) |
| Exporting, verifying or packaging the repository | [exporter](../scripts/export_writing_evaluation.py), [verifier](../scripts/verify_writing_evaluation.py), [container recipe](../deploy/writing/Dockerfile), [release selection](writing-release-selection.md) |

## Follow one operation

A human action starts in a frontend controller and reaches an HTTP handler. An
agent action starts at `writing_tools.execute`. An owner is the module responsible for a particular object and its state.
Both paths are routed to that
backend owner, which checks the selected object, role and revision before a write.
The owner returns the outcome and evidence; the frontend and agent read that
same outcome. The [engine walkthrough](writing-engine-walkthrough.md) follows
this path through a concrete manuscript revision.

The shared Python package also contains Laplace's general pipeline, canon,
representation and lifecycle modules. Writing imports shared implementation from
that local package. Package names retain their original `laplace` namespace;
using them does not require a second Laplace checkout or the author's private state.
The [package directory guide](../src/laplace/README.md) distinguishes these areas.

## Code, project data and runtime state

- [profiles/workflows/](../profiles/workflows/) contains the shared packet-return
  and independent-review schemas used by dispatch. They travel with the source.
- `src/laplace/` and `src/atlas/` are implementation source. The local
  [package declarations](../pyproject.toml) and [Atlas declaration](../atlas/pyproject.toml)
  specify third-party dependencies and optional extras.
- [registry_projects.json](../registry_projects.json) identifies project homes and
  selected manuscript roots. `writing_projects/` and `synthetics papers/` contain
  authored projects, source, research and retained history. Resolve their paths
  through the registry and selected-source owner.
- `contract/talk.jsonl`, `contract/journal.jsonl` and `contract/writing_bodies/`
  retain conversations, actions and content-addressed public bodies;
  `corpus_friction/work_orders.jsonl` retains Work and review phases.
- `.laplace-state` is the portable server's default runtime-state directory.
  Provider execution workspaces have their own location, described in the
  [startup guide](writing-agent-start.md). Credentials and private engine state
  are supplied by the operator and are not bundled.

## Begin a code task

Read this overview and the relevant directory README. Use the detailed
[source map](writing-source-map.md) to identify the existing owner, producer,
consumer and tests. Read the current source before changing it. Keep the native
contract, HTTP interface and human control aligned, and use the current owner
operations for project and manuscript changes.

For portable startup, use the documented Python environment and
`python -m laplace.web.writing_server --root .`. The full engine's personal wake,
semantic publication and managed-runtime procedures are separate operations.
The repository's [agent entry](../AGENTS.md) supplies the bounded startup route.
