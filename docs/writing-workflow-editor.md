# Workflow definitions in the workspace

Open **Workflows** in workspace navigation. Read the [workflow task recipe](writing-tasks.md#use-a-workflow) for a first visit. Workflows are optional; manual writing and reading need neither a workflow nor an AI account. This is a
workspace view of definitions owned by `pipeline.workflow`; a manuscript project
is not required. The scope breadcrumb and permission details describe the actual
owner read. A role label is a purpose, never a grant of tools, source writes or
independent review authority.

Choose **New workflow** or open a saved definition. **Add step**, select its graph
node or list button, then use **Step**, **Instructions**, **Settings** and
**Connections** in the inspector. The title is directly editable. **Edit workflow purpose** explains the purpose; advanced defaults remain separately available. **Provider**, **Model** and **Effort** offer
observed catalogue choices, **Inherit** and **Custom…**; workflow defaults use
**Use role default**. Custom preserves the exact value you type. Changing provider
or model keeps the other settings, including values outside the observed choices.
Suggestions follow declared draft inheritance, or unchanged saved settings when
no value is declared. They do not establish provider availability or permission to
run. **Inherit** removes only that assignment override; workflow defaults are
edited separately. The input-policy field keeps its existing opaque meaning. Effective
values, their origins, limits and unavailable scopes are the owner's resolution of
the saved version. A draft's settings are resolved after Save.

The graph's **Connect** and **Nest** modes use the selected step as the source:
choose a destination or drag a step onto another. **Select / move** drags layout
positions. The list inspector offers the same nesting and typed control, data and
feedback relations. List buttons support arrow keys, Home and End; all actions are
native keyboard controls. **Fit workflow** and **Center selected** change the view
without editing saved layout; the Step section's four Move buttons give keyboard
users the same layout edits as dragging. Narrow windows default to the list and
retain the full inspector, with an explicit **Graph view** option.
Containment cycles are refused; feedback cycles remain editable even when the
selected execution carrier cannot prepare them.

**Read this saved version** and **Saved history** open a separate read-only
version, with its exact owner and version. **Close saved version** returns to the
local authoring draft and its original save guard. Reading does not adopt a newer
version, change the selected step, prepare work or save anything.

**Browse saved versions** in the library, or **Browse all saved versions** for a
selected definition, opens bounded metadata pages for its retained prefix. **Older
saved versions** and **Newer saved versions** follow the supplied cut; **Read
current history** is an explicit new observation. The page names covered and known
positions and how many were read in this visit. End of this cut is not proof that
all pages were loaded or bodies inspected. The legacy rich preview remains last32.

Choose **Read saved version** for an exact row. A large body offers **Read next
saved-body part**; no complete definition or technical-body display appears until
all explicit ordered parts match the retained byte pin. **Close saved version**
returns to its current history row; **Close saved history** returns to the current
library/detail opener. Both leave the authoring draft, selected step, original save
guard and uncertain request unchanged. A fully qualified **Open this saved version
in Workspace** is separate from Add, sharing permission or draft adoption.
See [exact history and body custody](workflow-definition-owner.md#bounded-complete-history)
and [complete-lineage transfer](project-data-handover.md#opt-in-complete-workflow-lineage).

When leaving an unsaved workflow, choose **Keep draft and leave** to retain it in
the existing local recovery store, or **Stay in workflow**. This retains local
authoring; it does not save a server version or replay a pending request. An
uncertain save must be inspected through its original request first.

**Save definition** submits the complete draft with its original owner guard.
Typing and Save start no inference. **Prepare external run…** retains the external / CLI
`laplace.workflow/1` carrier with its source node, goal and write paths. That
preparation does not create an app dispatch or conversation.

The global **New workflow** action defaults to workspace ownership. For an app
run, first Save a definition owned by the existing project through its admitted
native author turn, or through authorised `laplace.sdk.workflow_save` with an
explicit project scope. The owner breadcrumb shows that custody. SDK creation or
a role label cannot manufacture the parent session required for app execution.

For a saved project workflow, **Prepare agent run…** selects saved steps, a
completion goal and maximum parallel children. **Prepare in conversation** opens
the existing project composer with the owner's exact version and request; review
it and explicitly **Send**. The native `workflow_definition_change` operation can
Save or prepare this `laplace.app-dispatch/1` slice. It creates the existing plan
artifact and dispatch Work with no children or provider start. Builder/reviewer
relationships must match the actual dispatch carrier. Selected Synthesis and
unconsumed policies remain precise local obligations; their authored instructions
are never silently dropped.

**Agent runs** inspects only the viewed saved version. Execution, review and
recorded Work status are separate snapshots; Refresh reads their owner again.
Select a prepared step to read its complete retained public result and saved
actions in the existing turn inspector, or open its recorded conversation and
existing input/Stop controls. A missing binding or typed return stays unavailable.
An invalid retained return is readable evidence, with its issues under disclosure.

**Prepare start message** prepares a separate explicit request in the
original preparation session. A later admitted turn in that same session may
launch the unchanged plan. Preparation and launch identities remain separate;
no browser request manufactures a parent turn. **Return to workflow** restores
the viewed version, selected step, inspector and full local draft. Unrelated
composer drafts are retained rather than overwritten, and no lost acknowledgement
causes an automatic resend.

For native publication, the current worker, reviewer or parent contract supplies
`publish_action` as the directly callable `{operation,payload}` envelope. Author
content inside its payload; `publication_context` carries the adjacent project,
permission and exact-read qualifications and is not another tool argument.

Saved, prepared and running versions are shown separately. A prepared run keeps
its consumed version while later versions are edited. Opening a history version
does not silently turn it into the current head. **Compare draft with current**
shows both complete definitions; **Keep draft and adopt compared guard** preserves
your draft and explicitly adopts exactly the guard you saw.

Drafts, full input/output text, preparation text and unresolved attempts are kept
in this tab's `sessionStorage`, qualified by the owner's opaque scope identity.
Storage failure is visible. Reopening the view restores the draft's original
guard; a pending attempt returns as uncertain. Nothing is automatically resent.
Reinspect an uncertain attempt through its owner before deciding what to do next.
An effect receipt and its subsequent readback are distinct: failed readback does
not erase a recorded effect. Full recovery records can be inspected at the foot of
the editor under **Technical details**. Closing a tab clears browser session storage according to the browser's
session policy, so keep or copy the recovery text when it is still needed.

The heading shows the workflow’s whole first paragraph; **Full workflow purpose** reads the complete multi-paragraph purpose without entering an edit form. Inspector tabs show the latest draft while the graph and workflow list stay in place. **Technical details** loads exact current information when opened.

## Request reviews of a passage comment

Select a passage in the manuscript and choose **Comment**, or use **Comment on
this passage** from its context menu. Write **Your comment**, choose configured
reviewers, and read their responses together. The comment remains your
instruction for that passage. Reviews use the project's normal context.

Start with an existing Work item in the same project. In **Work**, choose
**Set up reviews**. From a passage comment, expand **Reviewers and limits**,
choose **Existing review Work**, then choose **Set up reviews**.

Add the review questions. Each question’s **Review settings** holds its scope,
required/independent choices and source inputs; its summary keeps the current
standing visible.
**Use selected passage file** offers the comment’s inspected file explicitly.
Existing specialised questions stay unchanged in this form. For a new app-owned
reviewer, choose its name, provider, model, effort and **Approval duration**, then
**Include reviewer approval**. Duration choices include the permitted hour/day
presets and **Custom seconds**, using the same owner limits. An expired approval offers **Include renewal for**
that reviewer. Renewal keeps its identity and applies to future requests.

Choose **Save review questions** without reviewer approvals, or deliberately
select approvals and choose **Save questions and selected approvals**. Questions
and approvals save in separate guarded
steps; setup starts no reviews. If an acknowledgement is lost, **Check setup save**
reads the original intended standing. Choose **Use inspected matching questions** or
**Use inspected matching approval** when offered before continuing. Earlier saved
steps and later typing remain available. Exact receipts and comparisons are under
**Exact setup and saved outcomes**.

**Back to Passage comment** keeps the comment and its original source basis.
Choose **Preview updated review setup** to inspect the updated choices, then
select the reviewers and limits below. Saving setup does not change an existing
review request or an already running reviewer. **Save comment** remains available
when you want to keep the comment without requesting reviews.

For a manual request:

1. Expand **Reviewers and limits**. Choose **Existing review Work** and
   **Saved review settings**, or select the review questions and choose a
   **Reviewer for** each one.
2. Check **Reviews allowed**, **Connection attempts per review**,
   **Time allowed to start reviews (seconds)** and **Review time limit (seconds)**.
   The start window limits when a new review can start; the review time limit
   covers how long it may run. Choose these values deliberately, then select
   **Preview reviews** to see the selected reviewers and limits. After Save,
   **Review responses** shows the remaining allowance, shared by this comment's
   reviews, including recovery.
3. Choose **Save comment** to keep just the comment, or **Save and request
   reviews** to save it and request the selected reviews in one action.

For automatic routing, explicitly choose **Save automatic review settings**.
Once those saved settings are selected, **Save comment and request reviews**
commits the comment and requests its reviews together. Automatic routing takes
place when you Save; you can keep editing before that decision.

Open **Review responses** from the saved comment or **Review & notes**. The panel
leads with your original comment and a summary, such as one response received and
one review start unconfirmed. Each reviewer card shows its purpose, progress and
available verdict. Keep a useful response while checking the outstanding review.
An earlier verdict remains labelled in its own context.

Choose **Read complete response** and, for a longer response, **Continue reading
response**. **Inspect recorded verdict** opens the review decision;
**Inspect handed inputs** shows what the reviewer received. Use **Refresh review
responses** to check for updates, **Recover outstanding reviews** for missing
work, or **Stop this review route** to request stopping outstanding reviews.
Saved comments and responses remain available. **Review settings** holds the
chosen limits; **Exact route and receipt details** is the optional technical view.

If Save becomes uncertain, keep the draft and choose **Check save** first.
**Retry same save**, when offered, keeps the original submission. To change the
passage or wording instead, choose **Resolve uncertain save**. If the comment was
already saved, use that comment and its **Review responses**. Once the app
confirms it was not saved, your prose and original comparison remain: refresh or
reselect the manuscript passage as needed, then choose **Check selected passage**.
Review the new selection before making a fresh Save decision.

Receiving reviews leaves the comment for your decision. Use the existing
**Resolve**, **Reply** or **Address with Eigen** actions when appropriate.

## Operational qualification

An open agent run uses the same graph, list and step inspector in read-only mode.
Its topology comes from the exact consumed saved definition, even when a newer
head or an unsaved editor draft exists. Arrows show only the owner's prepared
execution dependencies; authored containment and other relations are hidden.
If that mapping is unavailable, no execution arrows are inferred. Saved nodes
outside the preparation say **Not selected for this run**. Selected nodes show
their recorded state as text, and open only their exact owner-issued step read.
Fit, Center and keyboard/list navigation stay available; edit, drag, connect,
nest, nudge and Save are unavailable in this mode. **Refresh status** reads a new
snapshot explicitly; a failed refresh retains the prior qualified facts. The
snapshot time is not a heartbeat. Execution, review and Work states stay separate.
Full public results and conversations use their existing owners. **Return to
workflow** keeps the editor's exact draft, saved basis and selected step.

Real app use has observed native Save, exact preparation/launch, recorded worker
publication and full public result/conversation/return inspection. A complete paid
app cycle with independent typed judgement and parent synthesis remains unobserved.
The retained failed/interrupted attempts and synthetic owner/permission tests have
their own scopes in `release/current-acceptance.json`. A recorded return or valid
call is not accepted Work completion or scientific validation.

To move the complete selected project's data and workflow history, use the
[handover owner](project-data-handover.md), not a browser draft or an external run
folder. Imported conversations are public history and start new provider bindings.

For a settled failed judge, the step inspector separates the **Current attempt**
from **Earlier attempts** and keeps links to the retained worker output. When the
owner offers it, **Prepare review continuation message** opens the original parent
conversation with the exact request and inspected Work target. Review the message
and Send explicitly. An existing message draft stays intact; send, save or clear
it before preparing another request.

The continuation reuses the judge session and pinned plan/settings. Its receipt
selects the current attempt; earlier results remain inspectable. Missing or
uncertain acknowledgement stays a retained request to inspect, never an automatic
retry. This slice supports missing, invalid or unreadable settled judge returns;
a valid positive or negative judgement is not rerun. See
[failed review continuation](failed-review-continuation.md) for the exact owner
scope, guards, deadline and recovery boundaries.

**Share complete saved lineage** reads a descriptor for the exact saved endpoint;
it does not include local unsaved edits. Only an actual permitted **Prepare complete
lineage export** offer enables preparation. Inspect the destination and resource
budgets, then choose **Export prepared lineage** explicitly. Verified partial
progress can offer **Continue verified export**; **Inspect original transfer**
observes the held original request without advancing it. Keep that original request
for a lost acknowledgement. UNKNOWN, changed input or missing progress does not
permit an automatic retry. Runtime settings, permissions and sessions are not carried.
