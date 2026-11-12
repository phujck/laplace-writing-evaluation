# Writing frontend

This directory contains the browser workspace and manuscript reader/editor.
The [code overview](../../../docs/writing-code-overview.md) connects it to the
backend; the [frontend source map](../../../docs/writing-source-map.md#6-frontend)
lists controllers, state, disposal and tests.

| Start here | What it does |
|---|---|
| [workspace.mjs](workspace.mjs) | Compose the project workspace and its domain controllers |
| [workspace-bridge.mjs](workspace-bridge.mjs) | Messages and contracts between the workspace and manuscript frame |
| [workspace-session.mjs](workspace-session.mjs) | Conversation presentation and session interaction |
| [workspace-spine.mjs](workspace-spine.mjs), [reader-state.mjs](reader-state.mjs) | Reader-plan display, selection and focused planning |
| [workspace-manuscript.mjs](workspace-manuscript.mjs) | Manuscript-frame attachment and lifecycle |
| [walk.mjs](walk.mjs) | Compose the manuscript reader/editor from `walk-*.mjs` owners |
| [walk-document.mjs](walk-document.mjs), [walk-drafts.mjs](walk-drafts.mjs), [walk-editing.mjs](walk-editing.mjs) | Document model, unsaved drafts and editing |
| [workspace-help.mjs](workspace-help.mjs), [workspace-guide.mjs](workspace-guide.mjs) | Contextual Help, internal diagrams and guided-task overlays |
| [workspace-inspection.mjs](workspace-inspection.mjs) | Contextual artifact and source inspection |
| [workspace-chrome.mjs](workspace-chrome.mjs) | Navigation and responsive workspace layout |
| [work-port.mjs](work-port.mjs), [work-port-outline.mjs](work-port-outline.mjs) | The renderer-neutral selected Work port (owner read, title/purpose draft with its original guard, attempts and owner results, visits, disposal) and its plain-DOM outline; the Work card in [workspace-work.mjs](workspace-work.mjs) is its current-view adapter |
| [owner-request.mjs](owner-request.mjs) | The neutral same-origin owner request carrier (GET/POST JSON, abort signal, exact status and owner body; connection, abort and unreadable replies keep an unknown effect for a POST). Writing's reply meaning stays in `writingOwnerResponse` in [workspace-session.mjs](workspace-session.mjs), which `projectRequest` applies |
| [selected-lifetime.mjs](selected-lifetime.mjs) | Shared lifetime mechanics: liveness, generation and leases (currentness is controller identity, not DOM attachment), owned cleanups and idempotent disposal; for a selected region also the qualified selection, visit stack, per-object delivery tokens and listeners. Used by the Work port, the Work card, the outline and the System owners view |
| [frontend-basis.mjs](frontend-basis.mjs) | The page-issued frontend basis (the frozen asset snapshot digest the served project page names, `shared_ui.issued_page`) compared with `/authoring/health` `frontend_bundle`; an explicit refresh only after each open owner captured its state, otherwise a stated refusal and the page is kept |

Controllers present backend-owned records and use declared operations for writes.
A new served asset must be declared in [shared_ui.py](../shared_ui.py). A controller
that adds listeners, a stream, a retained draft or an asynchronous operation must
also own its disposal and preserve the selected context through replacement.
See the source map's controller and lifecycle tables before extending a view.
