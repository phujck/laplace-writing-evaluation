# Writing instrument: existing-system trace and integration plan

29 September 2026. This supersedes the premature redesign previously at this path. The replacement UI mockup is rejected and must not guide implementation. This document preserves the initial trace; implementation has since landed in the working tree. Current changes, checks and limits are recorded in `evidence/WRITING_INTEGRATION_2026-09-29/verification.md`. The author's required post-publication workload is `docs/synthetics-interface-acceptance-2026-09-29.md`.

## The commission

Integrate what already exists. Preserve the application, adjustable conversation sidebar, editor, concept structure, section pipeline, research facilities and project records. One continuing session must be capable of all manuscript-project work. The normal operation is **do a piece of work, then place its result in the appropriate organisational structure**. The application handles mechanical joins for both the author and the agent. Neither should have to manage the plumbing, manufacture permissions or repeatedly ingest the operating manual.

This applies equally to a new numerical result and to inserting an equation reference at the caret. The latter is not complete merely because someone can manually type a TeX command. Creating, finding, placing, displaying and subsequently updating a reference must work together.

The editor itself needs substantial enhancement, alongside agent integration. Preserving the existing application does not mean preserving interaction restrictions that make reading and writing difficult. A successful tool integration with the current editing friction left intact would still fail the commission. Custom environments such as `operationalexample` must render as manuscript content in the manuscript surface.

## Scope and evidence

The active route inspected was `/project?workspace=writing`, with Synthetics open. Browser inspection was read-only. The source trace covers the embedded editor, selection bridge, conversation controller, provider adapter, project tools, canonical structure/research writers, source application and refresh. The separate `/front` workbench is not the active route and its defects are not attributed to this screen.

The audit also inspected current staged-workflow source and Eigenengine v2's actual entry/action path. It ran 77 existing isolated tests, all passing, and additional temporary-project probes for repeated context/help and self-invalidation. No real provider research task, external account mutation, live source write or new live manuscript build was performed. Character counts below are not provider-token measurements.

## 1. Manuscript → session already has a working bridge

`src/laplace/web/static_shared/workspace.mjs:230` embeds `/walk?...&embedded=1`. Walk loads `writing-panel.mjs`; `bootEmbedded()` adds editing and selection controls.

- Ordinary chat gets the current section's source scope from `workspace.mjs:26`.
- Highlight → Discuss/Revise captures the quote and source anchor in `writing-panel.mjs:35–36`. The source scope expands to the touched sections. It sends `laplace:discuss-selection` to the parent.
- `workspace.mjs:265` sets `session.selectionOverride`. `WorkspaceSession.send()` consumes that in `/authoring/turn`.
- `authoring_surface.start_turn()` validates scope, resolves the session, builds context and starts `WritingTurn`. Project tool calls reach `writing_tools.execute()` and its existing domain handlers.
- Completion streams back to `WorkspaceSession`, which invokes the workspace change/refresh callbacks.

The highlighted quote does reach the agent. An early audit-worker claim that the bridge was missing was corrected after reading both ends. The containing-section scope can still make a small request larger than its highlighted text.

Persistent conversations, reconnection, Codex steering, model settings, sidebar resizing and the selection bridge already exist. The mode selector is hidden in the active UI; author modes `work`, `discuss` and `revise` already share the same declared project-write set. Adding those features again would not solve the problem.

## 2. Source changes and comments take several existing paths

**Direct editing:** `walk.mjs:5132` computes an exact rewrite and posts `/review/adjudicate`. `review_surface.py:1765` checks the source span; a matching rewrite is recorded, source replaced, and an editor-save version attempted. Walk then reloads document data. Paragraph joining and multi-paragraph editing already exist, with restrictions around source files and atomic inline structures.

**Embedded selection Comment:** `writing-panel.mjs:35` calls `/authoring/correction`, which calls `authoring.bank_correction`. That stores an authoring correction and canonical feedback row, without changing TeX. The native Walk card separately comments through `/review/adjudicate`. Both paths matter when assessing comment behavior and visibility.

**Agent prose:** `propose_revision` only records a proposal. `WorkspaceSession.proposal()` supplies a separate Apply button. `/authoring/apply` validates the finished turn, context, consulted reads, edition and exact source, then uses the same review rewrite owner. Completion requests a manuscript refresh.

The actual interruptions are:

1. `workspace.mjs:24–25` blocks applying a proposal while any Walk draft is dirty/parked. Its change callback (`:34–41`) likewise avoids refreshing a dirty manuscript. Non-overlapping live author edits are not merged by this path.
2. `authoring_surface.py:573–584` replays every consulted tool read and compares its output digest. A turn's own successful changes are not distinguished from outside changes.

The second was reproduced in a temporary project using the real tool/apply handlers: record a proposal over unchanged prose; read `project`; create a research task in that same turn; apply the proposal. The error was:

> Consulted project evidence changed (project). Request a fresh revision; nothing was applied.

Source bytes were unchanged. This establishes the self-invalidation directly.

## 3. Existing capabilities are missing from the agent interface

`writing_provider.py:319` starts Codex read-only. Claude starts in plan permission mode with native `Read,Glob,Grep` (`:376–388`). The operating rules prohibit direct writes and native delegation. In that configuration the agent depends on the project tool being complete.

| Existing operation | Existing owner | Agent interface |
|---|---|---|
| Search/read references | `references_surface` search/item/text | Exposed. |
| Attach bibliography entry and source association | `/references/attach` | Not exposed. |
| Update/refresh attached references | `/references/update`, `/references/refresh` | Not exposed. |
| Create/render visual | `/visuals/create`, `/visuals/render` | Exposed. |
| Place rendered figure in TeX | `/visuals/place` | Not exposed. |
| Start numerical run | `/research/run` | Exposed as `experiment_run`. |
| Inspect/cancel an individual run | `/research/run/status`, `/research/cancel` | No dedicated operations; aggregate research inspection exists. |
| Create source chapter and include | `/authoring/chapter` | Exposed as `chapter`; separate from the outline's plan-only Add. |
| Build selected source | `/authoring/build` | No directly matching operation; style can start a separate styled preview. |
| Apply manuscript edit | `/authoring/apply` | Separate UI/CLI action; tool only proposes. |

The dispatcher is in `writing_tools.py:95–267`. `store_artifact` cannot fill all these gaps: its hard-coded folder/suffix list excludes bibliography, style and manuscript-source writes. This is a concrete mismatch between existing functionality and the interface the agent receives.

### Numerical work → result → visual → manuscript

The current path is:

1. `research_producer` → `research_surface.register_producer()` records an existing executable, modes, allowed arguments and dependencies.
2. `experiment_run` → `launch()` starts `research_runner`, which records output/exit/currentness.
3. A separate `research_record` creates or renews the result using that run and output file. Run completion does not itself create the result record.
4. `visual_create` stores the spec. Its `result_ids` connect visual freshness to the results.
5. `visual_render` produces assets and updates the figure manifest.
6. An optional separate `figure_binding` record supplies Research's explicit `depicts` invalidation edge. This is distinct from the visual's already-working `result_ids` freshness check.
7. `/visuals/place` validates currentness, ensures `graphicx`, inserts/reuses a labeled figure, records the source edit and updates placement. The UI can call this; the agent cannot.

The last operation already passes a fixture round trip through render, placement, source history and Walk discovery. It needs exposing and connecting, not replacing. The separate result/visual/research associations also need unambiguous handoffs rather than repeated agent bookkeeping.

## 4. Concepts, reader plan and source are connected—but edits stop at different layers

`concepts_surface.logical_plan_change()` writes objects and typed relations through `corpus_ingest.rewire_add`. `project_structure.state()` joins concepts, projection plan, selected source and evidence. `project_structure.context()` already narrows that join to selected sections/nodes and their neighbors. Preserve those mechanisms.

The active outline edits `/work/structure/change` → `project_structure.change()` → `storyboard.plan_write()`. Add creates a plan section; reorder changes plan order; retitle can produce a source-title-drift diagnostic. They do not update TeX. Existing tests explicitly assert source remains byte-identical.

Actual source creation is separate: `manuscript_structure.create_chapter()` creates a file and root include. The active outline's Add does not call it. No section-delete operation was found in the active outline or structure contract; “Unplace” removes a concept from a section, not the section.

These are intentional distinctions between planning and source editing, not just failed writes. Integration must preserve planning before drafting while completing an actual manuscript-structure request across both existing owners.

The `pipeline` tool calls `writing_pipeline.inspect()`, a read-only joined status view. It is not a runner that automatically advances work through the stages. Current `.claude/workflows/project-staged.js:141–180` already uses one coherent context and one writer, followed by proposal/apply. The earlier audit's section-writers-plus-global-weld description is historical, not today's code.

## 5. References in text: insertion and rendering are separate gaps

The selected root is `synthetics papers/synthetics-master-guide/manuscript/Synthetics.tex`. Its existing `Synthetics.aux` contains:

| Label | Number |
|---|---|
| `eq:closure` | 1.2 |
| `eq:cauchy` | 1.5 |
| `eq:log-rank` | 1.6 |

But `walk.doc()` asks `_resolve_bib_artifact(..., 'main.aux')` (`walk.py:2058`). The read-only probe resolved no file. The JS already handles `eqref`; it receives no numbers and shows `??`. `main.bbl` is similarly hard-coded; its citation impact was not separately exercised here.

The editor renders citations and references through `citeNode`/`refNode` (`walk.mjs:544–580`). Citation clicks open exact source editing; references display the resolved number. The embedded toolbar exposes italic/bold/math and exact source. No dedicated inline reference/citation insertion picker was found in these active frontend paths. Typing TeX or editing an existing citation's source is available, but is not the requested low-friction insertion flow.

The integration requirement is explicit: at the current caret/range, choose an existing equation/section/figure or bibliographic source by recognisable content, insert the correct reference using its stable label/key, save through the existing source-edit path, and display/navigate it correctly. The agent needs the same target discovery and placement operation. Numbering remains a build result; neither intelligence should manually maintain it. Changing/deleting a target must preserve identity or expose the actual broken reference, not silently point elsewhere.

`operationalexample` is a separate boundary: it is defined with `\newtcolorbox` in the project preamble, but falls through `walk.blocks_for()` to the raw-environment branch (`walk.py:1820–1834`), displayed as collapsed source. Trace and extend the current rendering/editor support for this construct; the evidence does not justify replacing the entire rendering architecture.

### Substantial editor workstream: reading and writing, not only agent access

Further source inspection establishes several interaction restrictions in the current editor:

- `editableBlock()` (`walk.mjs:4240`) makes mapped paragraphs/captions and certain plain-text headings directly editable. Lists, theorem-like blocks, tables and headings containing math/macros do not get equivalent direct editing merely because they render.
- `sealIslands()` marks math, citations, references and structural pieces non-editable. `onBeforeInput()` refuses typing/deletion that intersects these elements (`:5500–5625`), and `wrapSelection()` refuses formatting across them. Whole-object removal/replacement is therefore tangled with the need to preserve internal TeX syntax.
- Formatting writes visible TeX which renders after save. Paragraph splits/pastes can save immediately, leaving and returning to paragraphs uses parked drafts, and the normal saved-source path has a different undo model from an unsaved edit.
- The Ctrl-Z/Ctrl-Y handler (`:5907–5922`) explicitly refuses ordinary undo outside the current unsaved edit and instructs the author to use other keys for saved records or parked blocks.

These are source-traced behaviors, not a fresh exhaustive native-window usability test. They identify where an editor improvement must go deeper than toolbar changes.

The acceptance requirements for the human editor are:

1. **Read the actual manuscript.** Prose, headings, equations, references, figures, tables, lists, theorem-like material and project-defined environments remain visible in document order. No collapsed raw-source box standing in for valid content. Comfortable typography, zoom and line wrapping; stable reading position when saving, compiling or receiving an agent result. Preserve the adjustable sidebar and existing navigation.
2. **Write continuously.** Click where the text is, move the caret, select across ordinary document content, type, split/join paragraphs, cut/copy/paste and format without being forced to manage per-block parked/saved states. Preserve source fidelity automatically. Routine edits to an example's title/body, captions, list items and headings need usable editing paths at that location.
3. **Treat inline objects as ordinary editable document objects.** An equation, citation or reference can protect its internal syntax while still supporting selection, movement, whole-object deletion and replacement with normal gestures. A selection containing one must not become an unexplained editing trap. Detailed mathematical/source editing remains available in place.
4. **Provide ordinary editor facilities.** Reliable undo/redo across typing and saves, find/replace, keyboard navigation/shortcuts, formatting and mathematical insertion, reference/citation insertion at the caret, and recoverable local drafts. Saving must not erase the user's useful undo history. Expose a simple saved/saving/error state rather than engine terminology. Default saving should be automatic, with an explicit save command retained.
5. **Keep reading, editing and collaboration connected.** Comments and requested revisions stay attached to what the author is reading. An agent result must preserve the current caret, scroll and unsaved work. The author can continue editing another passage while a task runs.

These are required behaviors for the existing surface. They do not preselect a replacement editor library or justify another mockup before the current interaction paths are exercised.

### Custom environments: integrate the existing TeX rendering capability

The actual specimen is `chapters/what-a-theory-does.tex:171–180`. Its required title is “Composing two small alphabets”; its body contains prose, mathematics and an equation reference. `preamble.tex:15` defines the breakable titled box and its styling. The finished manuscript view must show that title and body, with working mathematics/reference rendering and the project's presentation—not a source disclosure and not an empty generic placeholder.

An existing implementation can supply much of the rendering path: `manuscript_figure_preview.py` resolves selected source spans, reads the project's preamble and included files, compiles TeX, caches output against dependencies, and serves PDF/PNG. `walk.doc()` attaches those previews to supported figure blocks; `walk.mjs` displays them. Current limitations are explicit: `_span()` requires a complete figure; `supports()` recognizes inline TikZ/tabular material; the preview attachment loop only handles figures.

Extend this existing source-to-preview path to custom-environment content and connect the result to the corresponding manuscript block. Discover project definitions through the real preamble/packages and preserve source anchors. The author must not manually register a renderer whenever they define an environment. A named fix for `operationalexample` alone is not completion of custom-environment support.

Do not copy the current fragment wrapper blindly: `_preamble()` substitutes the `standalone` class. Synthetics uses chapter-scoped theorem counters, and its example refers to equations outside the fragment. Rendering must retain the original class/context and correct build label data, or use the relevant output of the existing full-document build when fragment rendering cannot reproduce that context. A successful source build must have a route to visible typeset content even when the browser's semantic parser does not understand the environment.

Rendered text should retain selection, copy, search and anchored agent requests; displaying the right pixels alone does not settle the editor requirement. Reuse mapped text where it is reliable and the existing PDF/text rendering facilities for compiler output. Editing an environment must return to that same rendered location and preserve its title, body, labels and surrounding text. Exact source remains an available editing representation, not the substitute for rendering.

Validation must use the real specimen plus a renamed user-defined equivalent, nested mathematics/lists/references, a changed included preamble, and a box long enough to break across pages. Verify correct visible content, current numbers, reading order, selection/edit anchors, refresh after edits, and cache invalidation. Test both an actual TeX error and a valid environment unfamiliar to the browser parser: the former gets an actionable source-linked error; the latter still renders. These tests have not yet been run or implemented.

## 6. Repeated context and oversized help are measured

`start_turn()` calls `authoring.build_context()` and `writing_operating.build()` every turn. The context includes framing, argument, applicable corrections, glossary, citations, joined structure, selected numbered source and boundaries. Each context is appended to `authoring.json`, and that JSON is rewritten. `inspect()` traverses source and checks saved contexts for staleness. By contrast, the in-process talk-journal reader already consumes only the new suffix; it must not be described as rereading all history every time.

Two unchanged turns through the real controller with a fake provider yielded identical 1,201-character task-context prompts and identical 13,723-character operating briefs. The second turn retained its native session ID. The serialized tool declaration was 9,568 characters; it is supplied on native thread creation, not necessarily newly transmitted each turn. These are adapter/context-construction measurements, not actual provider token usage or caching evidence.

The tool advertises 39 operations. Only four have entries in `operation_payload_contracts`: concept change/tree, logical-plan change and structure change. Focused help for other operations falls back to the whole tool plus all those contracts:

| Requested help | Specific payload contract | Response characters |
|---|---|---:|
| `visual_render` | Absent | 34,553 |
| `research_producer` | Absent | 34,557 |
| `reference` | Absent | 34,549 |
| `structure_change` | Present | 13,536 |

The general description contains useful prose instructions; the problem is incomplete focused contracts and bloated discovery. Claude passes `--mcp-config` without `--strict-mcp-config`. The earlier account-plugin inflation report is consistent with that configuration but was not remeasured here.

## 7. Eigenengine v2's actual entry/action route

The path is `eigen` → runtime bootstrap → `scripts/eigen.py`. The optional session hook calls `eigen start` with session/provider/entry-role. `current_kernel_view()` derives the role and work frame; `card` renders contracts from `_PUBLIC_ACTS`, with detailed inputs/effects/refusals for the next action and coarse entries for others. `act <handle> --plan` resolves an existing action read-only; execution reaches its native handler.

Read-only probes returned a role/next-command entry and a card with 22 minted contracts, 14 rendered in the observed state. This establishes concrete discovery behavior, not the installation of every external hook or a ready-made manuscript workflow. The useful integration pattern is a short entry pointing to accurate executable actions. Its custody/role machinery is not required for writing.

## Integration order, grounded in the existing code

Agent integration and human editing are equal-priority workstreams. The numbered items below group engineering dependencies; they do not defer editor usability until after backend completion. The first usable slice includes real editing and custom-environment rendering as well as one complete agent action.

1. **Repair agent discoverability and reachability.** Make operation help specific and complete; reconcile advertised capabilities with existing handlers for references, placement, source application/builds and jobs. Test each through the real agent dispatcher. Preserve one full-capability session; remove artificial native-write/tool-coverage dead ends rather than relying on model workarounds.
2. **Complete “do work → place result”.** Reuse current result records, concepts, section placement, bibliography, visual generation and TeX insertion. Supply the missing joins and mechanical identity handling in their existing owners. Treat an output stranded in a research record or chat answer as unfinished when the request required manuscript placement.
3. **Substantially enhance the manuscript editor.** Deliver the reading/editing requirements above: continuous writing, ordinary undo/redo, usable structured content, reference insertion, selected-build labels, and actual project-defined environment rendering. Coordinate section add/move/retitle/delete/restore with the existing plan/source owners. Validate in the real native application, not only parser tests or an attractive static view.
4. **Remove self-invalidation and blanket dirty-document blocking.** Preserve exact source/conflict checks and source history, but let a turn consume its own successful changes and merge non-overlapping author/session edits. Keep actual overlap local. Already-requested edits can apply; explicit suggestions remain reviewable.
5. **Use persistent sessions with changed context only.** Stop appending unchanged operating material and returning whole manuals for focused help. Retrieve the research substance a task needs, maintain its scoped relationships, and send relevant changes. Measure actual provider payload/usage—including inherited tools—before claiming the large-token problem fixed.

These are integration repairs in existing owners, not a new agent framework, UI shell, permission layer, research graph or universal workflow engine. The first acceptance journeys must finish through the current UI and a real session: choose/insert a reference; find/read/attach/cite literature; create/run an example and insert its figure; reorganise a section; keep writing while the session updates another passage. Repeat within the same session and verify both source and organisation, as well as actual context cost.

## Verification run

```sh
scripts/laplace-python -m pytest -q tests/test_writing_controller.py tests/test_writing_operating.py tests/test_writing_proposal_recovery.py --disable-warnings
# 42 passed in 4.63s
scripts/laplace-python -m pytest -q tests/test_references_surface.py tests/test_manuscript_structure.py tests/test_project_structure.py --disable-warnings
# 31 passed in 4.38s
scripts/laplace-python -m pytest -q tests/test_visual_production.py::test_new_book_visual_roundtrip_is_registry_discovered_walk_served_and_compilable tests/test_visual_production.py::test_visual_consumes_only_linked_research_result_revision_and_currentness tests/test_research_surface.py::test_run_tracks_inputs_and_imported_code_before_and_after_execution tests/test_research_surface.py::test_records_link_declared_inputs_to_results_and_invalidate_live
# 4 passed in 1.51s (audit worker)
```

Those mechanisms pass while the missing agent routes and reproduced self-invalidation remain. Component success is therefore not acceptance of the research workflow. Fixes and real provider-to-manuscript acceptance remain unperformed in this planning task.
