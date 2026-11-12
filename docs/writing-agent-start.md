# Agent startup: the Writing evaluation checkout

Use this guide when an agent is given a fresh Writing App package and asked to start it or do bounded project work. Begin at that package's root. For code work, read the [code overview](writing-code-overview.md), [backend guide](../src/laplace/writing/README.md) and [source map](writing-source-map.md) before selecting an implementation owner. The [engine walkthrough](writing-engine-walkthrough.md) explains its provenance and governance; the [implementation map](writing-evaluation-release.md) identifies owners and limitations.

A package's edition and image tag are recorded in its own `container-package.json`,
`release/export-manifest.json` and `release/current-acceptance.json`; read those for the
exact bytes, identities, observed checks and limitations. This edition is
`writing-bundle-20261025-sealed-reader` (see [the download guide](writing-container-download.md));
the 2026-10-16 research collection and the 2026-10-04 edition remain historical
reproductions. Names alone are not acceptance.

This is an evaluator startup, not the author's personal engine wake. Do not borrow another checkout, its home-state directory, provider transcript, semantic cache or private calibration source to make the package appear complete.

## This edition: inspect actions and selected text

The failed-review composer keeps the human request short and attaches a qualified
action context. Inspect that card before Send; the owner retains exact action
details and original-parent guards. Reconcile an uncertain submission using its
retained identity rather than starting a new request. See the
[selected-action contract](failed-review-continuation.md#selected-action-in-an-author-message).

In Material or an exact artifact reader, choose **Prepare text-only reader**.
Inspect the complete selected input and explicit references, then Start only when
the local profile is qualified. The report retains that immutable input; the
session cannot take an ordinary follow-up. Choose **Prepare a fresh reader** for
another question. Plain UTF-8 is primary; explicitly complete PDF text supplies
neither figures nor visual layout. See the [reader guide](sealed-text-reader.md)
for SDK/native preparation, result/Stop/reconciliation and the exact local
operator procedure.

Host qualification is deliberately absent from this package. The responsible
operator must explicitly commission public canaries for the recipient's exact
provider executable and policy, inspect their retained evidence and install its
own proof. Ordinary Start remains unavailable until then. The shipped module
`laplace.writing.reader_qualification` uses the existing admission and adapter;
it never installs qualification itself. Do not copy another host's certificate,
body store, provider history or credentials.

## 1. Install the declared evaluation profile

Use Python 3.12 for the evaluation profile. The package contains both `pyproject.toml` and `atlas/pyproject.toml`. In a fresh terminal at its root:

Check `python --version`. If the default differs, use `python3.12` on Linux/macOS
or `py -3.12` on Windows for the environment-creation command. A different default
does not establish that Python 3.12 is unavailable.

```sh
python -m venv .venv
.venv/bin/python -m pip install ./atlas '.[research]'
.venv/bin/python scripts/verify_writing_evaluation.py --root .
```

The two local packages are disjoint: `laplace-engine` (this root, source `src/laplace`)
and `atlas` (`atlas/pyproject.toml`, source `src/atlas`). `research` is the complete
CPU research/figure profile (matplotlib, scikit-learn, scipy, mpmath); the core
runtime (pydantic, PyYAML, dulwich, filelock, psutil, jsonschema, numpy) plus the
`review` extra (pytest) is enough for headless Work/source operations, the browser
server and the portable test selection, as observed in a cold Python 3.12 virtual
environment. Optional tools stay optional and are never installed by the package:
AI turns need your own Codex or Claude CLI login (`writing-account-setup.md`); the
`laplace-writing` desktop window needs the system GTK/WebKit bindings described in
`writing-browser-server.md`; the Atlas `reconstruction*` extras need Torch, Triton or a
CUDA 12 CuPy build. The server requires two workspace inputs at its `--root`: the
project registry `registry_projects.json` (an empty registry is `{"projects": []}`)
and the repository configuration `profiles/writing_sources.json` (the export writes
both; a synthetic workspace provides them explicitly); nothing is read from another
checkout.

On Windows PowerShell, replace `.venv/bin/python` with `.venv\Scripts\python.exe`; activation is unnecessary when invoking that interpreter directly. The install command follows the evaluation README and the declared extras. It does not install a TeX distribution, provider CLI or GTK.

The verifier checks untouched export bytes, imported history bodies, registry/source resolution and bundled assets. Run it before changing the example. A missing `release/export-manifest.json` means this is not the expected materialized evaluation export; report that fact rather than treating the original development checkout as a substitute. After authorized edits, export-hash mismatches are expected; use the app's new revision history to assess those changes.

An existing body is verified again before its content handle is reused. If verification fails,
Writing retains the complete text inline and reports `custody_degradation` on the existing
saved artifact/action receipt and artifact reader. The small warning reports failed attempts,
inline bytes and bounded refusal identities; it contains no copied request text. The corrupt
body remains available for diagnosis. Inline retention preserves the save; it does not certify
that the body store is healthy or silently repair it.

For a Linux container with the documented system-tool profile, use the exact commands in [writing-container.md](writing-container.md). Do not guess a Compose location or claim Docker Desktop establishes native Windows/macOS parity. Scientific dependencies beyond the declared profile must be identified from the selected producer, not silently installed at startup.

## 2. Start the foreground browser app

Keep this command running in its terminal:

```sh
.venv/bin/python -m laplace.web.writing_server --root . --host 127.0.0.1 --port 8771
```

Open `http://127.0.0.1:8771/project?workspace=writing`. The server binds the explicit checkout and defaults to its own `.laplace-state`; `--state PATH` selects another explicit state directory. Startup installs nothing and does not start an AI turn. The foreground process stops with its terminal; use Ctrl+C when its work is idle. Do not kill an unknown listener or interrupt active work to reuse a port; choose another `--port` when needed.

For a configured managed source installation, application code and an existing
data workspace can instead be selected separately. The code/runtime entrance and
existing data root are explicit:

```sh
/path/to/code/scripts/laplace-python -m laplace.desktop.writing_app --repo-root /path/to/code --workspace-root /path/to/data
```

`--repo-root` selects executable code and its runtime entrance. The existing data
workspace must contain `registry_projects.json` and `profiles/`; it never supplies
the native script or Python. Default co-located launch remains unchanged.

The managed launcher's `--state FILE` is its process receipt, unlike the
foreground server's state-directory option above. In separate mode engine state
defaults to `<data>/.laplace-state`, and provider cwd is workspace/state-qualified;
`--engine-state DIR` and `--session-workspaces DIR` override those directories.
Separate mode ignores inherited private-state/session selections. Its default
receipt, native profile, window geometry and URI are qualified to the selected
workspace; use the same explicit selections when reconnecting or updating.
`--status`, `--reconnect` and `--update` belong to this managed lifecycle. Do not
point them at or stop an unknown listener.

The installer accepts the same workspace/receipt/directory options after
`--install --checkout /path/to/code`. A code update inside that entrance preserves
workspace identities and histories, and refuses replacement while work is busy.
Changing the code location requires stopping/closing and an explicit reopen; it
does not hot-migrate an existing window or adopt another profile. This selects an
already-existing workspace, not an export/import/migration facility. See
[operational homes](operational-homes.md) for effective defaults and limits.

Health exposes distinct startup observations. In foreground/co-located mode,
`source_start` fingerprints covered files under the declared repository root. In
separate managed mode it fingerprints the **selected code root**, while
`workspace_start` separately records consumed workspace profiles/configuration.
Neither is a fingerprint
of every installed implementation module. In foreground mode, a source checkout
may include code and profiles in that coverage, while an exported data-only root
may report zero code files. That data-root observation does not replace the
separate managed code basis. Bind the launcher/package manifest and actual installed module origins
separately. `runtime_start` identifies the running interpreter/version;
`runtime_selection_start`, when present for a managed launch, records its selected
runtime basis. Its absence in a foreground launch is not a failure. None of these
claims all loaded bytes. `frontend_bundle` identifies the captured served assets.

The managed launcher compares its declared start basis with current inputs and
preserves the old process during active work or invalid source. Installed-package
verification and actual UI use remain separate from a source/data-root match.

Open **Workflows** from workspace navigation, or use
`/project?workspace=writing&app=workflows`. **Save definition** records an immutable
version. For a saved project definition, **Prepare agent run…** selects a supported
slice and opens an exact message in the project composer. **Send** admits the
parent turn that prepares its plan/Work without children. **Agent runs** shows that
saved version's recorded dispatches; **Prepare start message** opens a separate
request in the original conversation, and explicit **Send** starts it. Select a
step for the full public reply/actions, typed return and original conversation.
**Return to workflow** retains the exact viewed version, selected step and draft.
**Prepare external run…** remains the separate external/CLI carrier. Follow the
[editor guide](writing-workflow-editor.md) and [owner contract](workflow-definition-owner.md)
for settings origins, unsupported selected assignments and guarded recovery.

An open run uses the existing graph/list and inspector in read-only mode, from
its exact consumed definition and prepared dependencies. Keep this run, a newer
saved definition and an unsaved draft distinct. If the owner offers **Prepare
review continuation message**, it targets one existing settled judge with a
missing, invalid or unreadable return in the original parent conversation. Review
the guarded message and Send explicitly; completed worker output, exact plan and
settings, and earlier attempts remain. Valid judgements and workers cannot be
rerun through this route. Unknown acknowledgement requires inspecting the same
request, not retrying it. See [failed review continuation](failed-review-continuation.md).

`laplace.sdk` exposes `workflow_request`, `workflow_save`, `workflow_prepare` and
`workflow_restore` through that owner. Project-confined native reads use the
owner-issued `project` request envelope. Native `workflow_definition_change`
accepts Save or app-profile Prepare only inside the actual current admitted author
turn of that project; a later admitted turn in the same preparation session may
Start its unchanged plan. An external SDK/HTTP client cannot manufacture that
parent. Role names do not supply execution or source authority. `source_contract` reads owner-declared segments and recorded
standing; a copied release contains its own data and may report a consumer as
unreviewed. Source grants and an actual app-agent source loop are separate.

Workspace **New workflow** defaults to workspace ownership. App preparation needs
a definition owned by the selected registered project. An admitted project author
can Save through its returned native action. An authorised workspace SDK caller can
also create it through `workflow_save(payload, root=data)`. Its payload includes
`scope={"kind":"project","namespace":"example"}`, `definition` with the full
body, `expected_revision=None` and a stable `request_id`. Use the actual project ID; this
scope selects custody, not an admitted parent or permission to launch.

A differing served frontend offers an explicit refresh. Owner-captured drafts and
uncertain attempts are restored without automatically replaying a mutation; a
failed read retains recovery for Retry. Existing pages are never forcibly reloaded.

The image uses CPython **3.12.15** and its installed local packages. The development
host's CPython **3.14.7** and personal runtime selection are not release inputs.
The package keeps the frozen 22-project/65-session data snapshot; new source does
not import later project content or author state.

The optional native GTK window is not required. Its availability and lifecycle are separate from this portable browser entry. Source/frontend changes require a deliberate idle server replacement: the running Writing process serves its captured frontend bundle. Merely editing files or refocusing a viewer does not prove that a changed bundle is live.

In another terminal, a bounded readiness read is:

```sh
.venv/bin/python -c "import json,urllib.request; h=json.load(urllib.request.urlopen('http://127.0.0.1:8771/authoring/health')); print({k:h.get(k) for k in ('runtime','pid','frontend_bundle','active_turns','active_runs')})"
```

Use the chosen port in that URL. HTTP health is not visual acceptance: open the actual page and record what works or fails.

For read-only diagnostics outside a native session, the History routes are explicit:
`/authoring/history?project=PROJECT_ID&view=activity` returns the paged all-project
timeline, `&view=telemetry` returns its counts, and `&view=record&id=ACTIVITY_ID`
opens an exact returned record. The route without `view` is the older author-correction
view, not the all-project timeline. Keep any selected file/concept/session filters
visible when comparing counts. The UI's **All project history** clears the selected
passage scope; it does not erase records.

If the server refuses to start or the package cannot import, do not borrow another
checkout. The read-only inspector needs no kernel and writes nothing, bytecode
included. Run from inside the package it describes only the package's own declared
consistency:

```sh
python scripts/inspect_writing_export.py --root .
```

Acceptance identity needs the externally pinned checker and the accepted manifest
identity, both supplied from outside the package; an anchor requested from the
in-package copy is refused. The recipe, the status and exit meanings and the
recovery routes are in [writing-recovery-and-currentness.md](writing-recovery-and-currentness.md).

## Design, Runs and Guide for agents

The native workflow view consumes owner offers and never builds its own. **Check execution** posts the exact draft to the offered pure `execution-preview` read and verifies `transport_request.sha256` against the exact submitted UTF-8 bytes. The owner's semantic `basis`, `definition_digest` and intent digests stay opaque, and the client never recomputes them. Role context and handoff choices are built only from the returned `declarations` and are written to the step assignment as `context` and `handoff`. The next preview's per-role `context` and `handoff` echo shows whether the owner consumed them. A choice that is not echoed is reported as not consumed and is never treated as delivered. `definition.run_policy` is edited only when the definition carries one. Its fields and limits come from the declared `run_policy.oneOf` variant whose `profile` matches. The legacy `laplace.research-review/1` limits are the fallback before a check, and no limit is invented for another profile.

**Runs** mounts `uses` and `river` observations only from offers present in the owner read. It reads on explicit request, pages by the owner's `next_read` and refuses mixed cuts. `NO_PROJECT_EXECUTION_BINDING` is shown as no observable binding, not as no activity. Withdrawal uses the owner `withdrawal-preview` digest with the exact retained `original_request`. Stop of an admitted research run consumes the accepted owner `workflow-stop-run` action issued on the research run view (`laplace.research-workflow-run/1`). The research workbench **Plan & run** pane mounts it, and a schema/3 `river` row mounts it after **Open run detail** follows `row_projection.detail_read` (facet `app-run`). The compact `stop.stop_run` summary carries no HTTP and is never posted. A detail that is not a research run, or names another Work or project, is refused, so an app-dispatch run is never relabelled. The consumer accepts only an issued `actions['stop-run']` whose native and HTTP carriers are both present and agree, which has `permitted: true`, and whose `work_id`, project and `expected_run_revision` match the selected view's `work.id`, `work.project` and `revision`. It posts that body once, presents the `laplace.workflow-stop-composition/1` reply, refuses a reply naming another request or Work, reports a stop only when further admission is gated and exactly the requested children are all settled, treats `REQUESTED` as unsettled and a lost reply as unknown, and never resends automatically. The reply must also name the same nested `work.id`, `work.project` and `stop_request.request_id`, with `stop_request.children` equal to the requested set. A different subject is unknown, and a missing subject or missing `stop_request.children` is unqualified. Before posting, the consumer writes the exact original body, `request_id`, owner-issued `request_read` and attempt to the research-workbench Stop recovery (session storage with a local backup, keyed by project and Work) and reads it back; a failed readback sends nothing. Plan & run, river detail remounts, Refresh and reload share that record; a record from an earlier page is `UNKNOWN`, nothing is resent automatically, and a late reply for an earlier request or attempt never overwrites a newer one. **Check original Stop request** follows only that read and accepts only an answer naming the same `project`, `work_id` and `request_id`: `UNKNOWN`, missing, foreign or malformed answers keep the hold. `RECORDED` (with a matching receipt) and `NONE` (no retained request at that cut, not a no-effect settlement) permit one explicit **Resend original Stop unchanged** of the retained wire, which the owner reconciles as the same request. A new Stop is offered only for a newly issued `request_id`; the client never mints one. `readWorkflowRunDetail` refuses before reading unless the HTTP query and every `request`, native and SDK carrier name the same closed selector (`definition_id` and `version` or `reference`, `project_lens`, `facet`, `work_id`). Original-parent synthesis publication stays a native action of the original parent turn. The run pane shows where synthesis runs, its admitted and declared settings, whether it is due and how many inputs must be read completely, and offers no publication button. Recovery of a failed publication belongs to the owner. It keeps the exact original publication identity, including the original provider, model and effort, in the same original-parent conversation and request. Changed settings may be refused, a fresh `request_id` is not recovery, and if the original settings cannot be restored the partial record stays inspectable. The app offers no publication or recovery button, and settings-drift recovery has not been exercised end to end in the UI.

## Read and transfer an exact retained workflow prefix

Use a user's explicitly selected `history_read`; do not manufacture a page token
or substitute the newest version. `workflow_request(handle["request"], root=data)`
returns one metadata page. Follow its supplied next read deliberately; `at_end`
only describes that cut. Choose a saved row's read and keep its exact scope/version.
For BODY_PAGE, retain ordered parts and byte pin, verify their complete joined UTF-8
bytes before parsing/displaying a full definition. Reading never adopts a draft.

For an authorised local operator, an un-lensed `lineage` read of the exact selected
reference can offer **Prepare complete lineage export**. A project-lensed/native
read cannot promote itself to that authority. Use the existing offered fields and
inspect the result before the separate explicit Export:

```python
# selected_reference is the exact saved version deliberately chosen by the user.
lineage = sdk.workflow_request({"facet": "lineage", "reference": selected_reference}, root=data)
offer = lineage["handover_action"]
# Stop if this actual offer is unavailable. Fill its destination/total budgets explicitly.
assert offer["permitted"]
payload = {**offer["sdk"]["payload"], "destination": chosen_fresh_directory,
           "max_files": chosen_files, "max_rows": chosen_rows, "max_bytes": chosen_bytes}
prepared = sdk.research_handover(payload, root=data)  # PREPARED/effect:none
# After an explicit user Export decision:
result = sdk.research_handover(prepared["export"]["sdk"]["payload"], root=data)
# Keep prepared["inspect"] for a lost first acknowledgement. Never blind-replay Export.
# PARTIAL may offer result["continue"]; follow only after another explicit decision.
```

This opt-in lineage-v2 transfer uses existing custody and fresh-root publication,
not `workflow_restore`, a new execution runner or a general in-place merge. Original
raw rows/bodies and full selected chain verify; total/body/per-file/staged budgets
still refuse oversized custody. See [the complete transfer contract](project-data-handover.md#opt-in-complete-workflow-lineage).

## Hand over one selected project

The package supplies application source under `src/` and two installable Python
packages (`./atlas` and `.`). The imported installation supplies executable code;
`root`/`data_root` selects registry, profiles, project files and public history.
Use explicit roots even when code and data happen to share a directory.

For a read-only data plan from your installed environment:

```python
from pathlib import Path
from laplace.projects import project_handover

data = Path("/path/to/data")
pinned_plan = project_handover.plan(
    data, "example", max_files=1000, max_rows=2000, max_bytes=20_000_000)
```

Inspect the returned files, selected rows, dependencies and total budgets. After
that review, export the unchanged plan to a new, absent destination and inspect
its ordinary owner views:

```python
destination = Path("/path/to/new-data")
receipt = project_handover.export(data, destination, pinned_plan)
inspection = project_handover.inspect_handover(destination)
```

The exact CLI equivalents, no-replace platform bounds, WDEF limits and repeated
handover lineage are in [project-data-handover.md](project-data-handover.md).
Use `python -m laplace.projects.project_handover` from this installed environment;
a configured source installation may use its own `scripts/laplace-python` entrance.
This data-only operation keeps the selected project namespace, Work, material,
artifacts, public history and workflow versions. It neither merges into occupied
data nor copies application code, credentials, provider transcripts, process
receipts or browser state. External aliases stay explicitly UNBOUND and foreign
references remain qualified unavailable until authorised binding. A subsequent
explicit author turn creates a fresh provider binding.

Open the new data home with the foreground installed server's `--root`, or with
the managed source launcher's separate `--workspace-root` above. Export/inspection
starts no provider. The release's supplied 22-project snapshot remains unchanged
unless you explicitly author or export your own data.

## Find system Work before selecting a project

For system development, begin at **Workspace → System owners** or the local SDK:
`from pathlib import Path; from laplace import sdk; entry = sdk.describe(root=Path.cwd(), task="browser workflow")`.
Follow its owner-returned subsystem and Work handles rather than supplying an
insider project name, task ID or deep evidence path. The SDK/local HTTP host
reads its owned workspace; a native project session remains confined to its
admitted project. A discovery read grants no mutation or evidence-body access.
The [owner-discovery contract](owner-discovery.md) explains selected versions,
coverage, evidence continuation and retained versus current views.

## Continue a Task from its Work owner

For a selected Task, read `project {view:"detail", id}` and follow its `continuity_read` exactly. When it is
`null`, `continuity_read_gap` says why no summary was issued; do not compose the route or claim a wider scope.
The summary (`laplace.work-continuity/1`) names its `subject` and `basis` and reports `standing`, `production`,
`completion`, `review`, `delivery`, `execution` and `coverage`, with one `next` step. Pass a `callable` step
unchanged, for example:

```json
{"operation":"work_delivery","payload":{"action":"continue","intent_id":"CI-...","expected_basis":"sha256:..."}}
```

A `template` step fills only its `fill` paths. `attach-proof` fills `payload.reference` with the exact retained
Artifact `{id, expected_sha256}`; `record-<phase>` uses its `preparation` and the review owner's preflight. Proof
arrival is not a review, and a handoff satisfies no obligation. After a lost acknowledgement, read the same issued
summary (or the returned `completion` read) before anything else; the owner returns the same handoff and event for
the same intent. Recorded completion, evidence currentness, proof arrival, review verdict and observed execution
are separate facts. The engine's programme pointer and its typed descent are described in
[`EIGEN_PROTOCOL.md`](../EIGEN_PROTOCOL.md); a Writing session does not run that host wake.

## 3. Discover the project and available capabilities

The research collection contains 21 projects, with three primary entry documents: **Foundations of Synthetics**, the **technical due-diligence account** and **Laplace — Living System Guide**. The [paper collection](writing-paper-collection.md) lists their roles and editions. **A little fun never hurt anybody** is retained as unfinished historical work: its frozen pilot is INCOMPLETE/INCONCLUSIVE (seven assessed with no eligible continuation; episode eight UNPROVED), its hypothesis was not tested and its paper is unfinished. Check the export manifest for the actual selected edition; the 2026-10-04 download predates this research collection. Create an unrelated project through **Projects** for mutation rehearsals. Keep its stable project ID distinct from its display title and scientific question. Project home names the current manuscript and exposes writing settings, active work and stages.

Use the existing views:

- **Manuscript:** source-addressed editing, source flip, changes and Undo.
- **Logical structure:** containment, typed dependencies and individual records.
- **Material:** selected project materials, addressed sources and their current binding; its **Shared material** section is the project's shared bindings (the former Dependencies view). Workspace-wide dependencies are an app view under the top-bar **Workspace** menu.
- **Research:** literature acquisition/readings, numerical results/runs and formal targets.
- **Review & notes:** author directions, review findings and proposal decisions.
- **Figures & output:** figure production/placement, builds and PDF inspection.
- **Activity:** scoped telemetry and exact records, original failure arguments, recorded recovery reads and separate current tool help.
- **Changes & history:** saved versions and source comparisons, with readable inspection and return.

Read `release/current-acceptance.json` for measured capabilities and gaps. A file's presence or a declared CI platform is not an observed pass. TeX/PDF work needs the document's actual packages/fonts and system tools; formal checking needs its declared toolchain. Report unavailable capabilities precisely.

## 4. Connect a provider only when model work is required

Follow [writing-account-setup.md](writing-account-setup.md) using the evaluator's own provider account in the same environment and OS user as the server. Credentials are not shipped. Opening Project, reading stages or reading History does not require a model turn.

Open the **Conversation** panel from the top bar (a cold entry keeps it closed unless the address asks for `conversation=open` or names a session), choose **Conversations** inside it or **Saved conversations** on Home to select or create a conversation, inspect its settings, and use **Refresh providers** when live catalogue/authentication discovery is needed. Select an available provider/model/effort. Explicit Send begins model work. Project's **New conversation defaults** are separate from the settings of an already-running conversation.

Imported history is readable but cannot resume the original machine's native provider conversation. The app says so; a subsequent explicit turn establishes a new binding. Do not send the entire imported transcript merely to simulate a resume.

## 5. Use native operation help before payloads

An app-managed session receives `laplace_project`, bound to its selected project and role. It accepts either the named form `{operation,payload}` used below or the complete semantic form `{verb,concept,target,expected,payload,by}`. Use one form at a time; follow the offered schema and exact `native_request` returned by current help. These are tool calls, not shell commands:

```json
{"operation":"help","payload":{}}
```

Then read only the contract needed for the next action, for example:

```json
{"operation":"help","payload":{"operation":"source"}}
```

For a typed packet or parent synthesis publication, pass the returned
`publish_action` itself as `{operation,payload}`, adding authored content only
inside that payload. Its adjacent `publication_context` is project/permission
metadata, not callable arguments. A read of `session_settings {view:"connection"}`
returns the actual admitted connection budget without discovering providers;
summary reads are passive, while **Refresh providers** remains explicit discovery.

Use the supplied current operating brief first. Avoid rereading context already provided and unchanged. When needed, discover the active profile and stage catalogue:

```json
{"operation":"writing_style","payload":{"view":"summary"}}
```

```json
{"operation":"writing_stage","payload":{}}
```

Select a returned stage identity; for example:

```json
{"operation":"writing_stage","payload":{"stage":"voice_integration","view":"guidance"}}
```

A matching `known_revision` permits compact reentry; omit it when explicitly requesting the complete stage again. Read the exact current profile or provenance only when required. The profile filename alone is not its version, and absent private originals must not be claimed as read.

An external repository agent can inspect the same stage owner without starting a provider:

```sh
.venv/bin/python -m laplace.writing.stages synthetics-foundations --repo-root . --view summary
```

Substitute a registered project ID for unrelated work. `python -m laplace.native.tools --help` describes its optional **stdio MCP adapter**; it is not a one-shot `--operation` CLI. App sessions configure that adapter and their turn identity. Do not invent a turn ID or bypass the controller to make a guarded write succeed.

## 6. Complete one bounded piece of work

Read the relevant current object/source, perform the authorized operation through its owner, then inspect the result. Obtain filenames and identities from the selected source/owner response rather than guessing `main.tex` or copying example IDs into a new project.

For prose, read `help(source)`, then the exact file/line range. Use that returned text and guard for the relevant revision/block/section operation. If refused, follow the reported recovery reads and obtain current source; do not replace a failed `before` value with a guess. An unsaved editor draft is useful discussion context, not persisted source evidence.

For research, inspect the summary and open the exact selected result. Read producer contracts before a run; inspect its terminal `run_status` before describing it as complete. For literature, distinguish acquisition metadata, returned source passages, claim binding and citation placement. For formal work, inspect `proof_targets` and the exact selected statement before checking it. A label or receipt is not scientific validation.

Read `help(author_history)` or `help(conversation_history)` when history is needed. Start with a bounded scoped page, then open its exact returned record/turn handle. Keep the full saved responses accessible without loading every session by default. Record original failed attempts as well as repaired outcomes.

**Use in conversation** on a stage prepares text in the composer; it is not Run. Review the prepared request before Send. During a running turn, use the offered capability: native steering and queued input are different routes. Inspect the exact acknowledgement/delivery state; publication is not proof that the model read it. Switching conversations leaves earlier work running. Explicit next-message Work selection, including Clear, is distinct from a historical conversation's recorded Work; verify it before Send. The active conversation's provider/model/effort controls cannot be changed during its live turn; this is not a lock on all project or global settings.

## 7. Return observed evidence

Report the checkout/code identity, served frontend identity, project/source selection, operations actually exercised and their receipts, visible outcomes, tests and remaining gaps. Preserve the distinction between an HTTP/component test and an actual browser action. For a build, inspect the resulting PDF, figures, references and links rather than reporting only the compiler exit status.

Use owner operations to record project findings. Do not rewrite old events, erase failed attempts, edit generated owner state directly, or retrofit missing historical hashes from current bytes. Broader semantic upfold/publication and independent recovery are separate workflows; ordinary evaluator startup does not run them. The [historical Atlas walkthrough](../atlas_system_walkthrough.pdf) is deeper architecture from 2026-08-16, not a startup requirement or current acceptance record.

Provider cwd has a separate persistent per-checkout/state location in platform user data
(Linux `~/.local/share/laplace`, macOS `~/Library/Application Support/Laplace`, Windows
`%LOCALAPPDATA%/Laplace`). `--session-workspaces PATH` or `LAPLACE_SESSION_WORKSPACES`
selects it explicitly. Runtime state stays at its existing location; provider cwd must
have no project instructions in its ancestors. Container profiles persist cwd in their
own `session-workspaces` volume. Old images require a rebuilt release for this behavior.

Read pins identify complete raw source bytes: `expected_sha256` works on plain
and JSON-pointer reads without changing format or permission. Copy the returned
source SHA, not a page or selected-value hash. For repository and Material pages,
use the owner's `page_read`/`record_read` for that pinned page and `read_handle` for
the next page. Artifact handles retain their declared next/current meaning. Use
`restart_read` only when explicitly choosing current source; it drops the pin and
resets the cursor without adopting source or acceptance. See the
[source read contract](source-read-contract.md).

A failed pinned continuation qualifies the retained page and enclosing Material
row as an earlier observation. Explicit Restart updates their observed standing
without changing consumed membership or enabling Adopt; use ordinary Inspect for
the current owner's mutation guard. Named `read_artifact` operation/payload
handles are callable. Its generic artifact grammar route remains unsupported:
`exact` legacy round-trip and a supported `verb_door` are separate conditions.
