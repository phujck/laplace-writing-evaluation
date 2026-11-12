# Frontend implementation methods — bounded research

21 October 2026. Context-rich implementation-method research by the existing Sol6.1/high session, **not blind review**, implementation approval or architecture synthesis. Source basis: `fb10e3165c45183d1bcac098743191fd217ef254`. Exact source and reference records are in `method-decision.json`. No code, prototype, tests, installation, provider, browser or package-download run was performed.

## Recommendation

**Keep native ES modules and the useful controller/service boundaries as the default implementation method. Make renderers replaceable through small explicit contracts. Keep CodeMirror and the draft owner. Do not commission a whole-shell framework rewrite.** This is a source-informed choice about migration risk and ownership, not a claim that native rendering is faster or that current interaction design is sufficient.

Lit is the best incremental alternative for repeated action/configuration/inspection controls if declarative rendering materially reduces duplicated rendering and lifecycle code. React is credible where an interactive workflow editor is central: React Flow offers a stronger ready-made editing surface than extending our current read-oriented SVG. If that benefit is selected, host a bounded React/React Flow region behind the same view contract; do not let the graph library choose backend authority or force a shell rewrite. Do not introduce Lit and React together merely to postpone choosing.

The decision before implementation is therefore concrete: approve native controller ownership, editor custody and renderer contracts now as the design basis; decide whether the *workflow editing region* warrants React Flow after the coordinator settles its actual backend action contract. A renderer comparison can change this local choice without losing the rest of the design. This recommendation does not authorise that experiment today.

## What the current code actually gives us

| Reached source | Useful mechanism to retain | Remaining method implication |
|---|---|---|
| `workspace.mjs` (372 lines), domain view controllers | Composition, admitted `show`, controller release, generation ownership, explicit return context | Separate navigation admission from paint; a new renderer must not replace a dirty editor or frame merely because data changed. File length is inventory, not a complexity score. |
| `workspace-session.mjs` (1,065 lines) | Project requests, saved-session views, SSE generation fencing, stream closure and truthful unsaved/disconnected outcome | Separate conversation presentation, transport observation and draft/settings interaction at real contracts. A framework does not infer final persisted reply from a stream end. |
| `workspace-work-view.mjs`, `workspace-work-observer.mjs` | Selected Work intent/revision, exact off-page selection; applied observation token, backoff, visibility suspension and stop/late-reply behavior | Keep the observer service, including advancing its token only after delivery succeeds. Generalise only a reached shared read/subscription mechanism, not a second lifecycle ledger. |
| `workspace-bridge.mjs` | Nineteen routes, same-origin plus exact current iframe-window fence, named handlers, bounded counters, uninstall | Preserve the frame seam. A component event bus is not a substitute for these message/identity checks. |
| `walk-drafts.mjs` (708 lines), `manuscript-editor.mjs` | Issued original basis, held/awaiting postimage states, persistent parks, selection/scroll and dirty admission | Keep custody outside ephemeral renderer state. CodeMirror transactions and visual equality are not backend source identity. |
| `exact-source-editor.mjs` | Existing CodeMirror 6 adapter, position capture/restore, read-only compartment, explicit destroy and textarea fallback | Reuse it in all three methods. It already isolates widget choice from source/draft/save authority. |
| `workspace-topology.mjs`, `workspace-work.mjs` | Shared typed nodes/edges/boundaries, fold/descent, exact relation-list representation and selected Work controller | Preserve data semantics and list alternatives; current appended-page accumulation is not a proven retention bound. This is not yet universal workflow authoring. |
| `workspace-chrome.mjs` | One responsive layout decision, nav/overlay priority, explicit Escape and focus ownership | Preserve behavior while improving navigation design; component libraries do not establish actual focus or narrow-screen legibility. |
| `web/shared_ui.py` | Explicit assets and recursive captured dependency validation | Any new bundle/chunk must enter this existing packaging/asset contract. |

The requested root `package.json` is absent at the pinned commit. The current browser consumes explicit local ES modules and a prebuilt CodeMirror bundle, not a demonstrated root npm application build. Introducing packages means defining a reproducible development build and distribution path. That does **not** require a Node application server in production. The static frontend README's source-map links also predate the extra `web/` nesting; treat this as a reached navigation/currentness correction for later adoption, not an excuse to edit Main during sew-up.

Backend limits matter more than renderer fashion. `projects/library.py` explicitly reports no global-default/tier write and no runtime-selection write. `turn_admission.configure_session` changes the next turn and refuses an active session. Stage/pipeline guidance is not a universal visual workflow author. A global settings form, topology mutation, comment fan-out or unattended execution control needs the relevant backend-owned operation; none of the compared libraries supplies it. Show unsupported controls honestly until their owners exist.

## Three credible overall methods

| Criterion | A — disciplined native ES modules | B — native services + Lit views | C — native services + React regions |
|---|---|---|---|
| Fit and migration | Strongest direct reuse of existing mount/release contracts and local offline serving | Incremental conversion of repeated views; no need to replace shell/services | Incremental region is supported; whole-shell conversion is the highest-cost option |
| Rendering/state | Explicit DOM updates and keyed reuse must be consistently authored | Declarative templates and reactive properties; existing services remain outside components | Declarative components; `useSyncExternalStore` can subscribe to existing view snapshots |
| Lifetime/async | Explicit destroy, AbortSignal, generation and subscription cleanup | Controller lifecycle can package cleanup; disconnect/reconnect and async updates still need exact ownership | Effects can wrap imperative widgets, but cleanup and development remounts must be safe; no writes on mount |
| Editor/frame | Existing adapters remain intact | Keep editor host stable; do not reconstruct on property ticks | Keep an imperative stable editor/frame host; tree keys must not silently reset drafts |
| Graph editing | Current SVG/list reuse; considerable interaction work for ports/reparenting/connect/undo | Does not itself supply a graph editor; canvas/graph adapter still needed | React Flow is an integrated candidate for interactive nodes/edges/nesting presentation |
| Accessibility | Strong direct semantic HTML control; all composite behavior is ours | Same HTML possibilities; Shadow DOM changes event/focus/style reach | Same responsibility for forms/focus; graph support helps but cannot certify the application |
| Replacement | Minimal framework coupling if ports are explicit | Standard element/property/event boundary can be narrow; template types must stay inside the view | React props/root are a narrow adapter if no backend/draft rules move into hooks |
| Maintenance/cost | No new framework dependency; highest responsibility for shared UI discipline | Additional library/build/license/update work; moderate migration; CSS/event boundary choices | React/DOM plus graph/build/tooling/transitives; highest migration and integration burden |
| Evidence level | Actual source fit, no new performance measurement | Documented mechanisms; no trial or measured advantage here | Documented mechanisms; no trial or measured advantage here |

These are qualitative engineering judgements, not numerical scores or time estimates. All three still require the same semantic/action/read contracts. Native code can remain tangled; components can become callback bags. Count deleted duplicate decisions and actual shared callers when implementing, not headers, folder moves or framework components.

**A: native.** Keep ordinary semantic HTML and lifecycle-owned controllers. Standard abort/event facilities and SSE cover client lifetimes, but aborting a fetch does not cancel a committed backend command. Keep the existing operation receipt/recovery and actual Stop owners. Native custom elements are available if useful; they are not mandatory for every controller. [DOM abort](https://dom.spec.whatwg.org/#interface-abortcontroller), [HTML SSE](https://html.spec.whatwg.org/multipage/server-sent-events.html), [custom elements](https://html.spec.whatwg.org/multipage/custom-elements.html#custom-element-reactions).

**B: Lit.** Reactive controllers offer an explicit reusable lifecycle mechanism, and rendering updates asynchronously. This fits selected repeatable view behavior; it must consume current snapshots rather than own canonical Work state. Default Shadow DOM would break assumptions in current global selectors, CSS and delegated event targets. Choose light-DOM rendering or explicit host contracts deliberately; do not solve encapsulation by querying component internals everywhere. [Controllers](https://lit.dev/docs/composition/controllers/), [lifecycle](https://lit.dev/docs/components/lifecycle/), [event retargeting](https://lit.dev/docs/components/events/). The project documents production bundling, so pin and package resolved local assets if adopted. [Production](https://lit.dev/docs/tools/production/).

**C: React.** Official guidance supports partial-page integration. A region could subscribe to owner-backed presentation state without moving that state into React. Snapshot identity must be stable, and cleanup must actually unsubscribe. Effects are unsuitable places to invent auto-save or workflow advancement; development setup/cleanup replays expose such mistakes. Component tree/key changes can reset local state, so durable drafts remain outside that lifecycle. [Incremental integration](https://react.dev/learn/add-react-to-an-existing-project), [external store](https://react.dev/reference/react/useSyncExternalStore), [effect cleanup](https://react.dev/reference/react/useEffect), [state identity](https://react.dev/learn/preserving-and-resetting-state).

## Graph and editor choices stay separable

Keep the current SVG/HTML relation list for existing inspection until a replacement demonstrates a useful difference. It already knows our typed edges and folded boundaries. A more elaborate rendering engine will not repair an unreadable global fit, infer relevance or determine currentness.

| Targeted option | Practical use | Limitation/cost |
|---|---|---|
| Existing typed SVG/list | Selected-region inspection, existing focus/return and offline asset model | New direct manipulation must be designed; do not extend it into a hand-built general flow editor by default |
| Cytoscape.js behind a graph adapter | Framework-independent network exploration with compound-node and layout support | Rich form cards/ports need additional presentation; do not assume canvas interactions provide semantic HTML equivalence or complete screen-reader behavior |
| React Flow behind a React region | Workflow assembly with interactive nodes/handles and nested visual groups; strongest targeted editor candidate | Introduces React boundary; layout is a separate decision; app-specific actions still need list/forms and exact guarded commits |

Cytoscape's compound hierarchy and React Flow's `parentId` are display models. Neither equals a Work prerequisite, recursive grade, authority inheritance or causal membership. One visual parent cannot erase multiple semantic relationships. Preserve original typed identifiers and relation directions, then make a local display projection. [Cytoscape compound nodes](https://js.cytoscape.org/#compound-nodes), [React Flow subflows](https://reactflow.dev/learn/layouting/sub-flows), [layout choice](https://reactflow.dev/learn/layouting/layouting).

React Flow documents node/edge focus, selection, movement and ARIA mechanisms. This makes it credible, not automatically compliant. Connection, nesting and reorder actions also need discoverable non-dragging pointer forms and keyboard operations over the same owner commands. W3C distinguishes the non-dragging pointer requirement from keyboard access. [React Flow accessibility](https://reactflow.dev/learn/advanced-use/accessibility), [dragging alternatives](https://www.w3.org/WAI/WCAG22/Understanding/dragging-movements.html). Use a tree widget only when the data/interaction is a tree and implement its complete focus/selection behavior; a plain list with actions can be clearer. [WAI tree pattern](https://www.w3.org/WAI/ARIA/apg/patterns/treeview/).

**Retain CodeMirror 6.** The current adapter already preserves position and exposes explicit destruction; the vendoring record lists exact package versions and MIT notices. Do not replace source editing with another document model during the shell refactor. Preserve local editor undo separately from guarded reversal of a committed backend effect. Keep unsent text, original issued basis, pending/awaiting source readback and explicit reconciliation in the current owners. Official editor-view source confirms a real destroy lifecycle; our adapter determines the app integration. [CodeMirror source](https://github.com/codemirror/view/blob/main/src/editorview.ts). Official guide/reference pages returned HTTP403 to this research tool; no missing documentation behavior is inferred from that failure.

## Shared contracts to carry across any method

1. **Owner-backed snapshot and command boundary.** A snapshot carries project/object identity, selected scope, revision/cut, coverage/continuation, currentness and available action metadata. UI labels state their origin. Actions pass the exact inspected guards to the existing operation owner and consume its refusal/partial/effect receipt. Frontend disabled state is an explanation, never permission authority.
2. **Three kinds of state.** Backend facts and receipts stay remote. A bounded disposable projection cache owns pages and observation tokens. Interaction state owns selection/focus/expanded rows and pending intent. Draft text and its original issued basis survive renderer replacement. Never put all four into a generic persisted component store.
3. **Subscription and invalidation.** Preserve token-on-success observer semantics, visibility/backoff/expiry and stop/late-reply fences. Scope subscriptions by consumed project/object/cut; reread affected facts, not the whole campaign on each event. An event notification or client acknowledgement does not become a review, delivery acknowledgement or persisted completion.
4. **Lifecycle and return.** A mounted region has one disposer for requests, listeners, observers, streams, timers and children. Semantic focus targets are resolved only after an admitted render is connected and current. Abort/release prevents obsolete painting; it does not imply remote command rollback. Keep dirty navigation admission before teardown and preserve the current iframe fence.
5. **Graph/list and configuration equivalence.** Render purpose, state, next action, meaningful code such as M5/R5, location/history and affected relationships from the same qualified objects. Both graph and list invoke the same action. Effective configuration must show origin/version/override permission, including NEXT-turn-only boundaries. Do not simulate unsupported global writes, redefine parents as prerequisites, or mark configured topology as observed execution.
6. **Bounded context and retention.** A viewport is a selected region, not a licence to load every body or append pages forever. Keep exact selected object and held drafts when evicting disposable pages; retain continuation/cut identity and explain incomplete coverage. Virtualisation can reduce DOM but does not itself bound fetched/parsed/retained data. No framework supplies action-sufficient current context or backend selective fan-out.

These are proposed small integration contracts grounded in existing mechanisms, not a new ontology, DSL, authority registry or implementation approval. Coordinator/Root owns the cross-cutting architecture.

## Licensing and delivery implications

| Candidate | Observed upstream licence | Consequence to plan |
|---|---|---|
| Native browser APIs | No new distributed framework package | Existing project/vendor obligations remain; own the UI mechanism maintenance |
| Lit | BSD-3-Clause | Retain upstream notices/conditions; pin library and build inputs |
| React / React Flow | MIT / MIT repository code | Retain notices; audit exact chosen packages/transitives and any separately offered material |
| Cytoscape.js | MIT core | Pin core and each chosen extension separately; no extension pile by default |
| Existing CodeMirror modules | MIT per current vendoring record | Preserve bundled notices and exact rebuild recipe |

Primary licence records: [Lit](https://github.com/lit/lit/blob/main/LICENSE), [React](https://github.com/react/react/blob/main/LICENSE), [xyflow](https://github.com/xyflow/xyflow/blob/main/LICENSE), [Cytoscape factsheet](https://js.cytoscape.org/), [CodeMirror](https://github.com/codemirror/view/blob/main/LICENSE). This records observed project licences, not a blanket licence clearance for future bundles.

A new framework requires a local dependency manifest/lock, pinned reproducible build, retained notices, source-to-output mapping and an approved update path. Do not fetch a CDN at runtime. Shared assets/chunks must be declared and captured through `shared_ui.py`, included in wheel/curated export/Docker input selection and verified from the served installed package. Avoid absolute developer-node paths or a hidden second checkout. Source maps should use approved public source coordinates. Node can remain a development tool; Python may continue serving the compiled local assets. None of that work is performed by this research.

## Small implementation order, after design approval

- **First, one vertical read/action slice and shared lifetimes.** Retain shell routing and editor/bridge. Separate owner requests, observer snapshots, commands/refusals, draft custody and view painting using existing controllers. Migrate a selected Work/inspection/action surface and delete its duplicate rendering/state glue. Record before/after actual callers and preserved guards/late-reply/focus/drafts. A framework decision must not delay this reusable seam.
- **Then, reusable controls and situated conversation.** Apply the chosen renderer discipline to repeated action outcomes, provenance/settings fields and full-message disclosures, keeping domain field meaning local. Move the monolithic session concerns at their transport/read/draft boundaries. Retire copied behavior, not just move it into new files. Preserve body-on-demand and partial/unknown status.
- **Then, the workflow editing region.** Against the approved backend topology/configuration actions, use the same selected graph/list model. If direct manipulation is primary, authorise one bounded React Flow feasibility region before writing a custom connector engine; otherwise retain native inspection and form actions. No separate experiment per observation or new actor forest is needed.

## Falsifiable unknowns for a later authorised check

No timings, heap, bundle sizes, assistive-technology results or designer learning times were measured here. Relative migration cost is inference from actual boundaries, not a benchmark.

| Unknown | A bounded discriminating observation | What would change the decision |
|---|---|---|
| Does native rendering duplication remain expensive after the seam? | Compare actual deleted/shared callers in one repeated action/settings slice | If ownership stays clear but DOM/state glue repeats, prefer Lit for that view family |
| Is workflow editing the dominant unmet interaction? | One approved nested workflow task: connect, reparent, inspect scope, cancel and stale refusal using the same owner model | If React Flow materially reduces interaction code and stays replaceable, choose method C for that region |
| Do component moves/remounts preserve custody and focus? | Dirty TeX draft + stream + stale owner tick, switch/reopen/destroy, late reply; editor/frame unchanged unless admitted | Reject a renderer path that resets basis, leaks stream/listeners or auto-posts |
| Is selected-region scale readable and bounded? | Synthetic tens and low-hundreds of nodes/edges, narrow390/720 and desktop, measure actual label geometry, parse/heap and retention after repeated pages | Choose renderer/layout/page cap from observed behavior; no global fit or benchmark-only win |
| Are graph actions usable without dragging? | Same connect/nest/reorder task via pointer form and keyboard/list; inspect real activeElement and relevant screen-reader output | Library defaults are insufficient if any action/focus route is missing |

These observations belong to one later scoped feasibility/interaction episode only if needed for a real decision. They are not tests run now, a compulsory three-framework prototype, or conditions to reopen completed release gates.
