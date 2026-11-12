# Writing source and action map

Use [operational homes](operational-homes.md) for installation, runtime, writable
state and update commands, and [the code overview](writing-code-overview.md) for
the declared ownership tree. This map follows current responsibilities. Release
manifests and `release/current-acceptance.json` identify measured package bytes
and scope; a source map cannot certify them.

## Current entry and guidance

`native/help_guides.py` owns the layered Start here/Task recipes/Glossary/Advanced
reference content. Its four Markdown views are generated, and native Help and HTTP
share the same declarations. `native/declarations.py` records actual conditional
control states, including explicit Conversation Options and native document tools;
a control behind a closed disclosure is not cold usable. Shared delivery selectors
come from `scripts/writing_eval_manifest.py:OPERATIONAL_INPUTS`. The neutral portable
README/agent/reviewer entries use the exporter's existing template mapping, rather
than inheriting operational host session instructions.

`workspace-chrome.mjs`, `workspace-manuscript.mjs` and `workspace-session.mjs` keep
focal editor/source/conversation controllers and qualified return places.
`workspace-home.mjs` composes bounded recorded events through the existing Activity
target dispatcher; it does not infer placement or execution from an attempt.
`workspace-presentation.mjs` supplies one passive human standing lexicon without
altering owner status, currentness or action guards. See [the workspace guide](writing-workspace.md).

## Workflow operation and complete saved lineage

`pipeline/workflow_operations.py` owns pure execution/context/uses/river contracts,
context/handoff composition and exact synthesis read-coverage validation.
`writing/workflow_progression.py` and `workflow_dispatch.py` retain preparation,
explicit binding/start, run transitions, exact child Stop and original-parent
synthesis. `projects/artifacts.py` recovers one exact durable owner publication;
a later genuine parent turn may complete the same retained bytes while preserving
the first publication's execution identity. These are not generic undo operations.

`pipeline/workflow_definition_history.py` supplies bounded bodyless history and
explicit saved-body parts. `projects/project_handover_lineage.py` implements the
opt-in complete-lineage fresh-root transfer through the existing handover owner.
The history, operation and run helpers beside `workspace-workflow-editor.mjs`
follow issued handles, checked bodies and native draft recovery. Workspace designs
receive no project-only Runs read; copying a verified saved body uses existing
owner choices and a new local draft, not identity or lineage migration.

`native/declared.py`, SDK and existing HTTP adapters derive these owner contracts.
Canonical `native/declarations.py` separately owns actual Help/control states.
The 21-input model's partial HOLD and final eight-path unrecorded proposal remain
historical; external component judgments and Root browser acceptance are explicit
separate evidence. No fresh current-definition provider execution is inferred.

## Task outcomes and supporting evidence

`work/project_work_evidence.py` composes exact recorded Work/session/reply/ART,
review and delivery relationships. Aggregate counts, relationship pages, selected
supporting availability and admitted evidence choices are separate demands.
`projects/artifacts.py` derives exact artifact coordinates;
`research/research_runs.py` keeps run locators and result bytes in the actual
selected project Research home. New guarded completion can name a pinned typed
support manifest; missing support does not silently rewrite historical Done.
The existing SDK/native/HTTP doors retain actual caller Scope. The
`workspace-task-trail.mjs` reader opens explicit typed child routes and preserves
qualified return focus. See [Task outcomes](writing-evidence-navigation.md).

## Focused review-evidence reading

`work/review_evidence.py` composes the existing `project_work_review.facts` decision
path. It counts without rich support construction, reobserves the actually consumed
Work/Source/evidence facts and exposes closed bounded enumeration/selected support
reads. The existing Work read owner and native/HTTP doors preserve actual Scope;
`laplace.sdk.work_read` follows project Work payloads without routing them into
owner discovery. Guarded phases retain current same-ID row-set identity. The
shared `workspace-review-evidence.mjs` inspector follows exact handles and keeps
counts, metadata expansion and body inspection separate. Existing Work editing
and effects keep their original owners. See [review evidence](writing-review-evidence.md).

## Entry and discovery

`laplace.sdk` is the outer Python discovery adapter. `laplace.system.entry` and
`choices` describe declared owners; `laplace.work.owner_discovery` reads canonical
Work facts and separately revisioned bindings in the same Work ledger. Human
**System owners**, local `GET /work/discovery` and native
`project {view:"discovery", request:{...}}` share its request/result contract.
The host supplies actual scope. Returned up/down/lateral/evidence handles expose
partial coverage and qualified currentness, rather than infer missing ownership.
See [owner discovery](owner-discovery.md) for exact versions and admission.

`work/object_facets.py` composes existing domain records for the project-optional
Research workspace; `work/object_geometry.py` supplies bounded one-hop typed
neighbourhoods, parent-local coordinates and per-owner timeline lanes. Explicit
frontiers and cut/coverage qualify each observation. `research/object_context.py`
validates scientific context, and `projects/project_handover.py` supplies selected
portable closure without a second scientific store. See the
[research workbench](writing-research-workbench.md).

## Source families

Paths below are under `src/laplace/`. Atlas is independently packaged at
`src/atlas/`; its public namespace remains `atlas` and imports no Laplace.

| Responsibility | Owner |
|---|---|
| Neutral references, versions, admission and receipts | `core/identity.py`, `core/admission.py`, `core/receipts.py` and `core/scoped.py` |
| Checkout/state/runtime/process selection | `core/checkout.py`, `core/runtime.py`, `core/process.py` |
| Source ownership and operation-bearing descriptions | `system/description.json`, `system/__init__.py` |
| Work facts, specification/standing guards and ledger | `work/project_work.py` |
| Work read/actions/currentness/navigation/activity | `work/project_work_views.py`, `work/project_work_navigation.py`, `work/project_work_activity.py` |
| Review, synthesis and recoverable child/join composition | `work/project_work_review.py` |
| Human-granted source read/candidate/apply/check, verified review plans and durable recovery | `work/development_source.py` |
| Retained Source meaning, active scoped publication and typed recovery | `work/source_kernel.py`, `engine/source_kernel_input.py`, `representation/source_publication.py`, `engine/descent.py` |
| Separate human/root historical engine obligations | `engine/historical_obligations.py` |
| Optional Source commission accounting and shared drain | `writing/source_execution.py`, existing `writing/records/` journal/index |
| Admitted recipient/delivery/continuation and supported proposal/review progression | `work/work_delivery.py`, `writing/workflow_progression.py` |
| Conversations, records, turn admission/context/control/execution | `writing/records/__init__.py`, `writing/turn_admission.py`, `writing/turn_context.py`, `writing/turn_control.py`, `writing/turn_execution.py` |
| Proposals, consumed basis and source effects | `manuscript/proposal_currentness.py`, `manuscript/source_application.py`, `manuscript/source_effects.py` |
| Manuscript source/structure/blocks and reader plans | `manuscript/` |
| Projects, configured repository sources, material and settings | `projects/` |
| Complete selected project-data plan/export/inspection and shared selection | `projects/project_handover.py`, `projects/project_data.py`; [handover guide](project-data-handover.md) |
| Saved workflow definitions and existing app dispatch compilation/observation | `pipeline/workflow_definitions.py`, `writing/workflow_dispatch.py`, `writing/dispatch_execution.py`, `writing/dispatch_returns.py`, `writing/dispatch_parent.py` |
| Literature, result records/runs and bounded artifact reads | `research/` |
| Writing body policy and Atlas body-store boundary | `representation/writing_bodies.py`, `representation/writing_representation.py`, `core/bodies.py` |
| Native tool gateway, owner dispatch and generated help | `native/tools.py`, `writing/operations.py`, `native/declarations.py`, `native/declared.py` |
| HTTP routes/pages and captured package assets | `web/scanner.py`, `web/authoring_http.py`, `web/project_work_surface.py`, `web/shared_ui.py` |
| Managed server and OS window | `desktop/writing_app.py`, `desktop/native_writing.py` |

The system description and actual owner declarations decide responsibility.
The native gateway and HTTP routes call domain owners; neither a route table nor
an explanatory file grants authority. Historical version-qualified declaration
citations remain their original coordinates, even when source files moved.

## Launch and lifetime

A portable package uses its own installed Python and explicit workspace:
`python -m laplace.web.writing_server --root . --host 127.0.0.1 --port 8771`.
Its registry and configured sources belong to that data workspace; installed code
and package resources are separate. A managed host uses `desktop/managed_homes.py`
for explicit code, data, receipt, engine/session and native-profile selection. The foreground
server defaults to its `.laplace-state`; it does not import another checkout's
private data. [Agent startup](writing-agent-start.md) gives the install profile.

The managed desktop route is `desktop.writing_app` → the OS Python isolated
`desktop/native_writing.py` entry → the managed server owner. The window's
bootstrap cannot assume OS Python has Laplace installed. `--update` is an
explicit idle-guarded server changeover; it does not mean an existing window or
unsent client draft was reloaded. Source-start, interpreter selection and captured
frontend bundle identify different boundaries; each needs its own observation.

## Browser responsibilities

The browser composition root is `web/static_shared/workspace.mjs`; document
rendering is `walk.mjs`. `workspace-owners.mjs` renders P0 discovery responses.
`workspace-work.mjs` is the current Work view, `workspace-session.mjs` the session
adapter, and `workspace-work-observer.mjs` owns applied observation/backoff and
disposal. `workspace-context.mjs`, `workspace-inspector.mjs` and
`workspace-bridge.mjs` own their selected region, inspector and origin/frame
boundary. The exact-source editor and `walk-drafts.mjs` retain document drafts
and original bases. Shared static resources are selected by `web/shared_ui.py`
and packaged beside the code, not fetched from a runtime CDN.

`work-port.mjs` owns serialisable selected Work reads, issued action guards,
title/purpose drafts, attempts/results and selection lifetime. The current richer
Work card in `workspace-work.mjs` remains its adapter; `work-port-outline.mjs`
provides the independent plain-DOM editor reached from System owners. Both use
one port. Qualified capture retains original draft bases and uncertain attempts;
a remounted card presents their outcome before another submit. A read showing
matching fields remains an observation, not a save receipt. The owner basis must
be compared and explicitly adopted before a stale draft becomes a new attempt.
Document drafts and the exact-source frame fence retain their existing owners.
The graph/list workflow and role editor uses these same draft and selected-read
services. The native ES-module shell remains primary; the React/Flow experiment
is isolated and is not a shipped dependency.

`owner-request.mjs` carries same-origin owner HTTP status/body and transport uncertainty; `workspace-session.mjs` retains Writing-specific reply semantics. `selected-lifetime.mjs` owns selection generations, delivery fencing and disposal, shared by the port and current mounts. `frontend-basis.mjs` compares the page-issued asset snapshot with the server bundle. The shell captures each open owner before explicit refresh; it keeps the pending carry through entry/selected-owner refusal and acknowledges exact bytes only after qualified restoration. No mutation is replayed, and a different issued target is shown truthfully rather than called newer.

`workflow-port.mjs` consumes the pipeline workflow-definition owner through that
same transport and selection service. `workspace-workflow-editor.mjs` renders one
guarded draft as graph, keyboard list and full step inspector; its CSS is
`workspace-workflow-editor.css`. The global `app=workflows` route is composed in
`project-work.mjs`; [the editor guide](writing-workflow-editor.md) explains save,
prepare, version and recovery behaviour. Its app-run read follows the exact saved
version to existing dispatch Work, packet/step bindings and recorded child sessions.
Complete public replies/actions reuse the saved-turn inspector; conversation and
return use the existing session/composer owner. SDK read/Save and native admitted
Save/Prepare consume the same definition owner. `writing/workflow_dispatch.py`
compiles only supported builder/reviewer dependencies; it creates no separate run
ledger. Parent and child publication contracts expose `publish_action` as the exact
native call and `publication_context` as qualification metadata. The browser decides
no settings, permission or execution semantics.

`workflow-setting-choices.mjs` is the pure suggestion leaf used by the existing
editor; it consumes `provider-options.mjs`. It follows literal step/parent/default
assignments. Saved provider/model fallbacks require unchanged relevant declaration
and containment bases; the model fallback also retains the selected role basis. It keeps current custom values
rather than coercing them to catalogue choices. Effective settings remain the
saved owner's result. The editor updates local inspector tabs in place and
builds the optional Technical disclosure only while it is open; the existing
port still owns draft capture, pending requests and currentness.

`research-workbench.mjs` is the workspace-first object adapter. Its geometry
controller consumes issued metadata/coordinate reads while native editors and
readers remain mounted. `workspace-topology.mjs` provides the shared opt-in
readable map camera and explicit framing; it determines no domain relations.
Evidence inclusion uses the owner's inspected window descriptor. Back/focus,
conversation target, draft and pending original wire have separate lifetimes.
Comment review context reads its recorded Work association through the same
bounded projection. Delivery lanes show latest state per event, not invented
intermediate transitions or a total clock.

## A guarded action and its recovery

A read of Work detail returns `allowed_actions` and its exact owner payload.
Title/purpose edits submit those issued guards to `POST /work/task`; a changed
basis refuses before the intended effect. Keep authored words and the original
basis while comparing current input, then create an explicit new attempt.
A lost response is an uncertain effect, not permission to replay automatically.
The owner receipt and observed postimage, not a success badge, establish the
actual change. [Work review](writing-work-review-lifecycle.md) explains the
separate handoff, independent review, synthesis and follow-up obligations.

For source changes, discovery does not grant a write. A human-issued grant at
`work/development_source.py` binds a configured development checkout, exact base,
Work scope, session/evaluator, paths, operations, check profile and lifetime.
Candidates, conditional apply/compensation and bounded checks use its actual
owner. Its verified edit/context plans and configured repository reads preserve
complete pins while offering focused review. Optional shared Source native-call
accounting uses the existing Writing journal/index; providers stop after shared
admitted calls drain or a genuine account stop. These are scoped facilities, not
a universal self-change loop or generic workflow quota. See
[Source use](development-source-use.md) for the authority and recovery limits.

## Declared source inputs and distribution selection

`work/source_inventory.py` projects one exact declared subsystem's bounded modules,
contract/explanation/evaluator inputs and raw-source pins through the existing
owner-discovery read. `work/source_contracts.py` retains the existing provider
registry. Observed runtime declarations and current disk pins remain separate;
evaluator source is not an executed check and unresolved kernel standing is not
an invented memory identity. Contract-issued `projection=inputs` omits rich
contract/capability metadata with explicit `NOT_REQUESTED` coverage and keeps the
existing source pins, scope, cut and continuations. See
[declared source inputs](writing-source-inventory.md).

`work/source_kernel.py` retains selected canonical Work/body facts; the active
`representation/source_publication.py` transaction preserves unrelated kernel
basis, declares derived changes and exposes exact publication-object recovery.
The publisher authors its own nine-part Source declaration through the existing
registry. `ACTION_FIELDS` and the actual operator doors are shared with dispatch;
this declaration grants no effect authority. Current constituent reads use an
unversioned current reference plus separately held observation; retained parts use
an exact Work/handoff/version and issued navigation. Selected facts include their
held typed relations. A Source grant never inherits trusted SDK/CLI publication
authority. Host nine-part publication `74970785…` is observed selected-owner evidence;
no host artifact set is included. Preparation, published facts and current review are separate. Historical WO/PRM
reading is a separate human/root owner, not a canonical Work conversion. The
[Source/kernel guide](source-kernel-bridge.md) describes the exact operator and
limits. Canonical `scripts/reembed.py`/system runtime and an accepted active kernel
base belong to the upstream development checkout, not this package's startup.
The recipient ships owner modules but no host kernel artifact set or proof.

`scripts/writing_eval_manifest.py` owns the operational input declaration consumed
by the exporter and deterministic ordinary/refresh Docker selectors. Source/image
manifests identify shipped application bytes separately from the frozen project
snapshot. The Backlog owner reads that mounted data; a newer image does not import
live author planning. [Session settings](pilot-session-settings.md) likewise keep
saved future choices separate from actual admitted turns.

## Evidence and change scope

Use exact owner reads, source pins and retained raw results. A stale historical
acceptance is not renewed by reading current bytes, a project namespace is not
universal object ownership, and a package health response is not visual or
scientific acceptance. Run only checks meaningful to the changed owner and its
consumers; preserve failed attempts and unsupported cases with the result.
