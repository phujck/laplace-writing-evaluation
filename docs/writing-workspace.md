# Writing workspace reference

Launch **Laplace Writing App** from the desktop application menu. This is a standalone GTK application with its own window, navigation and native file dialogs. It uses the installed WebKitGTK rendering component internally; Chrome, Firefox and browser tabs are not required. **Projects** is the ordinary starting view. Explicit Research links still open the Research workspace.

The OS Python runs only the desktop toolkit. The research engine runs through the repository's pinned Python wrapper, including when launched outside the checkout with no `PYTHONPATH`. Repeated launch activates the same window. Closing the application checks for unsaved work and active sessions, numerical runs, formal checks, figure renders, builds and downloads before stopping its owned local engine. The window size, project location and private editing/session storage persist between launches.

For development diagnostics only, `scripts/laplace-python -m laplace.desktop.writing_app --no-open` starts the service without a desktop window. The optional browser surface remains at `http://127.0.0.1:8771/project?workspace=writing`.

## Start with your task

For the first visit, open [Start here](writing-start-here.md). The complete
[task recipes](writing-tasks.md) cover opening a project, reading a source,
writing, tasks and reviews, optional workflows, and recovery. The
[glossary](writing-glossary.md) explains unfamiliar terms; [Advanced reference](writing-reference.md)
locates the deeper guides.

The compact **Workspace** menu keeps **Projects**, all **Tasks**, **Activity**,
**Workflows** and advanced tools available.
Project navigation leads with **Home**, **Writing**, **Sources**, **Tasks** and
**Research**. **More project tools** keeps **Review & notes**, outline and other existing
views available. Internal links and
technical references still use names such as Work, Material and Manuscript.
**Help** explains the current screen; **?** opens the same help where no text field
is active. Help and its recipes never submit an action or claim a task is complete.

Choose **Continue writing** on Home, click a paragraph, and wait for **Saved**.
A draft document can already be saved. In the workflow editor, unsaved local
changes are a different kind of draft. **Add task** uses the existing task form.
In **Set up reviews**, **Save review questions** needs no approvals. Open
**Optional reviewer approvals** only when intended; **Save questions and selected
approvals** is separate from starting a review.

Imported documents offer **Use in conversation** after inspection. A recorded
file's **Prepare a question about this file** fills unsent text and does not attach
an inspected passage. Read the exact offered source first, then open Conversation
and **Inspect context** beside the destination before Send. **Next message** sets future intent
and preferences, not permissions. The retained reading, target and **Next message:**
intent stay visible outside Options. **Back to reading** returns from Conversation;
when the editor has too little room for a source and conversation together,
**Show source instead** restores the same source without discarding the message.
Reading and manual writing need no AI account.

## Find an outcome, then decide what remains

Open a Task and **What led here** to read its bounded recorded history. Follow
offered **Read reply**, **Open conversation**, **Read file**, **Read review**,
**Read Source basis** or **Read run** links explicitly. Supporting availability
is inspected separately from direct completion standing. Review satisfaction,
currentness and independence differ. Counts and history metadata do not mean
that evidence bodies were inspected.

An associated report is not an invented native conversation. An unavailable
exact reply stays unavailable even when its summary can be read. **Recent
activity** names what happened and where its result went. Finished conversations
remain readable when nothing is running; In progress is a saved declaration,
whereas Running requires a current execution observation.

Historical Done may need current review because scope or evidence changed; this
is not automatically failed tests or unfinished implementation. Follow its
reason and next action. **Update task status** distinguishes the saved record
from a new disposition. **Mark done** is offered only under its actual conditions.
**Choose saved evidence** uses admitted project items or run outputs; an optional
retained-support manifest is a separate explicit selection, never an ordinary
answer file promoted automatically. Follow [the finishing
recipe](writing-tasks.md#finish-a-task-without-losing-its-evidence).

A reviewed candidate, the running app and a published edition need their own
dated records. Missing raw stays unavailable; a report or completion count does
not recover it or establish a release. See [Task outcomes and supporting
evidence](writing-evidence-navigation.md).

## Progress and next action

When the Work owner issues a progress read for the selected Task, **Progress and next action** appears below
its reason. It reads that one owner-issued summary for this Task and reuses it until the Task details change.
**Delivered so far** lists recorded facts: applied Source changes and checks, each armed prepared completion,
arrived proof, recorded review decisions and review requests. **Still open** lists what is awaited: a declared
proof, a handoff or review, remaining obligations, or a prepared completion that is ready, held or waiting. An
applied change is
provenance, and proof arrival is not a review or acceptance. **Activity** lists admitted turns and Source account
standing with the time they were observed; In progress is a saved declaration, not an observed running process.
**Uncertain or unknown** keeps UNKNOWN acknowledgements, stale or unknown decision currentness, held completions
and omitted rows in view. A Task whose owner issues no summary says why, or shows nothing on an owner that has no
such read.

**Next** is the owner's one issued step. **Continue to the approved review** appears only when the owner offers
Continue with a human route; it records one handoff and one approved review request, not a review or completion.
When the owner offers Continue only to agents, the view says so and sends nothing. **Attach arrived proof** fills
only the declared proof reference. A handoff or review step offers **Open form:** with the owner's phase title, which opens the existing review form
with its own draft.
If a sent request returns no acknowledgement, or an error that does not show whether it took effect, its original
request stays UNKNOWN with the Task's drafts across navigation
and Back, and travels with them wherever the workspace carries drafts over a refresh. **Check the original outcome** reads the same issued summary, and **Resend the original ...
unchanged** is offered only when that read shows no effect. **Exact progress basis and reads** keeps the qualified
Task, revisions, cuts and the intent, request, grant, account and producer identities, and opens review records
only on request. A summary read at another Task revision withholds its action until you reinspect.

## Starting with a research object

Open **Explore across projects** from the Workspace menu to explore existing questions, evidence, results, Work and workflow definitions without choosing a manuscript. **Project context (optional)** narrows the catalogue; clearing it returns to all permitted projects. **Find in loaded objects** searches the titles of objects already loaded, including pages appended with **More objects**. It does not search unloaded records. **Tasks** is the dedicated route for finding and planning recorded Work across permitted work namespaces, including namespaces without a registered project.

The compact working frame keeps global destinations and Help above the task, with a scope outline on the left, a focal reading/editor in the centre, and the focus inspector with situated conversation alongside it. Introductory guidance is optional in Help; the panes keep their own scroll positions. **Hide outline** and **Hide inspector** give the task more room; their Show controls restore the same panels. **Relation map**, **Relation outline** and **Timeline** show supplied owner observations of the same objects. Select a name to inspect it without replacing the open reader or draft; **Open focused object** opens its full reading or native editor. **Explore this neighbourhood** and **Descend into this scope** follow explicit bounded reads and bring the new scope into the relation map, or the readable outline on a narrow screen. The reading/editor stays mounted; Back restores the prior pane position and named opener. **Fit** keeps readable text rather than shrinking the whole network into the pane. A bounded initial page is drawn, including the focal node; pan, expand or use the complete loaded object/relation list for the rest. Short inspected purpose leads the inspector; a long purpose offers **Read complete purpose**. Navigation names may come from the loaded catalogue; metadata-only objects remain uninspected. Map movement and representation changes use the loaded observations; they do not fetch every node's body. Containment, prerequisites, consumed inputs, related-unpinned links and configured/admitted routes have different meanings. Each timeline lane keeps its owner's order and coverage; delivery lanes show the latest state per event, not every transition or a global clock.

Navigation focus and comparison checkboxes are presentation state. Neither includes evidence, changes the manuscript target, edits a draft, retargets a message, approves a recipient or admits work. **Saved presentation views** retain their scope/read reference, representation and camera; reopening reads current observations and restores no evidence or permission. **Back** follows the shared place trail. On a narrow window, **Outline**, **Inspector** and **Conversation** open retained panels; Escape closes the panel and returns to its opener. **Orientation** → **Find your way around the working surface** offers optional cues over observed navigation only.

Select an object to read its complete purpose and recorded relationships. **Evidence & inputs** opens exact source readings. Include an object projection or an inspected source window explicitly: the selected inputs retain the owner, version and reading extent. A window does not stand for the rest of a document. Named **Read** links use an offered body reader directly; **Open source** uses the object owner and lands on its evidence/read surface. Sources without a recorded title are distinguished by type and position. Previously inspected readings remain available through **Back to previous object**; **Read current** is a separate request.

**Settings** shows saved inheritance and its origins. **Open workflow editor** uses the existing graph/list editor, including unsaved draft recovery and custom provider/model choices. **Start from a research workflow** copies an owner-supplied starter into an unsaved draft. Saving a definition, preparing a Work item and starting its execution are separate decisions. Changing a draft does not change settings already consumed by a running step. The surrounding relation map is read-only; topology edits use that native definition editor. Execution remains limited to supported owner-validated workflows, not an arbitrary graph.

The workflow view has three views over one selection. **Design** holds the plan and your unsaved draft: steps, instructions, configured connections and, after **Check execution**, the context and handoff choices the owner actually supports for each step. The check saves and starts nothing. Its result names what the owner consumed for each step, and a choice it does not return stays in the draft without being delivered. **Runs** reads recorded uses of the exact saved version and, where the owner offers it, observed flow from run receipts. A drawn connection is planned, a prepared request is recorded, an admitted run has been accepted for execution, and only a receipt is an observation. **Guide** explains the selected workflow's ownership, roles, review, synthesis and limits and how to finish it, without reading or changing anything.

Three controls that look alike do different things. **Discard unsaved edits** removes only the local draft. A draft that was never saved then closes, returning to the saved workflow you had open or to the chooser. **Use as new draft…** copies the selected saved version, never unsaved edits, into a new local draft whose ownership you choose; the original keeps its identity and history. A reusable workspace design has no Runs of its own. **Withdraw original request** asks the owner to drop an exact Save or Prepare that has not been admitted. If the owner already recorded it, the receipt stays and nothing is undone. **Stop this run** belongs to a research workflow run. It appears in that run's **Plan & run** in Explore across projects, and in Runs under **Open run detail** in the run's observed flow. It is enabled only when the run's owner permits it, sends the owner's exact request once and never resends it automatically. The run counts as stopped only when the reply names the same Work, project and Stop request, further admission is gated and every requested child is observed settled. Anything else stays still stopping or unknown, and recorded results are kept. Before sending, the browser saves the exact original request with its owner-issued read and reads it back; if it cannot, nothing is sent and the refusal stays visible. That one record is shared by **Plan & run**, **Open run detail**, Refresh, Back and a browser reload, and a reload shows a request still awaiting its reply as unknown. Nothing is resent automatically. **Check original Stop request** reads it through its owner. An unknown answer, or one that does not name the same project, Work and request, keeps it held. A recorded answer, or NONE (no record at that read, which is not proof of no effect), offers **Resend original Stop unchanged**: the same request once more, which the owner treats as that request, not a new Stop. A new Stop needs a newly issued owner request, so Refresh the run for one. The app-dispatch runs this view lists carry no Stop, so **Stop admitted run** says where to go instead. A reviewer judges the exact handoff it receives with project context, which is not blind review. Synthesis is written by the original parent conversation under its admitted model and settings, so a different model chosen on a synthesis step is not applied there. When a workflow carries a review policy, Design edits it within the limits the owner declares for that policy profile: one to three rounds for the legacy profile, or your own finite rounds, admission budget, deadline and written continue and exit criteria for the bounded profile. A profile the owner does not declare is kept as authored and is not given invented limits.

**Plan & run** shows the selected evidence packet, actual recipients, progress, complete-response doors and available recovery or next-step decisions. Evidence-packet review is informed by that packet. A proposal and an accepting review still require the human manuscript review and Apply boundary.

For the proposal/review starter, choose **Use a workflow**, then **Start from a research workflow** and save the definition in an explicit project context. **Prepare agent run…** lets you select the saved steps, completion goal, evidence inputs and **Manuscript to revise**. The manuscript choice carries its inspected source basis; it remains separate from the evidence packet. **Inspect selected manuscript** reads that source without leaving the form. **Prepare in conversation** fills the existing composer; review it and choose **Send** to prepare the Work item.

Open that Work’s **Plan and run**. Approve the proposal writer and independent reviewer by name and duration; approval starts no delivery. **View current run** inspects the updated choices. **Prepare start message** uses the selected approvals and original author conversation; **Review prepared message**, then **Send**, starts the admitted run. **Stop before next step** preserves work already admitted; **Stop this run** also asks each running step to stop through its own owner; **Resume pending step** is explicit. After uncertainty, **Check original request** before retrying its identical wire. Complete response and proposal readers keep their original turn/version. After application, the recorded outcome, review and responses lead; **Future changes and recovery** retains the owner’s remaining actions. Work standing remains separate from run progress. **Accept human Apply boundary** and **Apply reviewed manuscript proposal** remain separate author decisions.


Future plan or recipient changes first open a **Preview** of their prospective scope. The preview separates work already admitted from future candidates, names changed input/settings categories, and establishes no provider capacity. Leaving replacement inputs unchecked keeps the current packet. **Review exact confirmation** opens the existing guarded decision form; it sends nothing until the explicit decision. A changed basis offers **Inspect current run** rather than silently updating the held request. Exact acknowledgements identify the original decision; a separately marked current-run observation describes progress. Uncertainty keeps the original request and newer typing.

Open **Registered methods and results** from a project-scoped question, method or result. **Run** shows the registered method’s actual modes, argument fields and execution limit. The calculation and cleanup standing remain separate from scientific judgement. Inspect the completed output, then choose **Record result** and author its title, finding and limitations. To use a later completed calculation for the same canonical result, choose it under **Revise an existing result**, then **Revise selected result**. Nothing records automatically. After uncertainty, **Check original request** follows the exact retained Run or Record submission; a new decision is explicit and retains newer typing.

Include that inspected result under **Evidence & inputs**, then choose **Record selected consumed inputs** on the claim that actually used it. **Consequences** → **Inspect recorded dependents** follows those recorded bases. Choose **Changed scientific assumption**, explain **Mark for reconsideration**, and open its canonical scientific concern for **Record author judgement**. A reasoned REVISE or WITHDRAW remains a scientific decision; fresh producer provenance cannot silently clear it.

**Consequences** follows recorded consumed-input bases. An unrelated object is not affected merely because it is nearby in a graph. Scientific reconsideration and provenance currentness remain distinct: matching bytes do not clear an open scientific concern. **Handover** separates local inspection from permitted portable content; inspect its included and omitted coverage before exporting.

For a supported object, open its conversation and choose **Use this object for the next message**. This attaches its inspected pointer while retaining your message text and other selected context. Reading another object does not send a message or silently replace that target. **Inspect context** beside the destination shows the exact retained pointer; **Send** remains explicit. After an unclear action, check its original request before retrying; recovery keeps that original wire and any newer typing.

In a saved comment’s **Review responses**, the selected source passage and saved instruction remain separate. **Show review context** opens the recorded routed Work’s bounded map, outline and event timeline alongside those native controls. It is a recorded association, not the route currently selected in an unsaved comment. Looking around that context starts no review and leaves the original comment request intact. Full response, verdict and handed-input readers keep their existing Close/Back return to the source.

Each reviewer in **Review responses** also carries a **Revision chain** from the feedback owner (`laplace.feedback-revision-join/1`). It follows the admitted reviewer's own turn: the proposal it saved (an exact proposal read), any application of that proposal version with the application's own source-effect receipt, and a recorded build only when that build's dependencies equal the applied after-bytes under the same selection (an exact build-status read). It never picks the nearest or latest PDF. A missing link stays visible as *no proposal produced*, *not applied*, *application incomplete* or *not built*, with the owner read that answers it. An application not attributed to a proposal of this review is listed but not counted as applied. The chain opens reads only; applying, building and recovery remain their owners' guarded actions. Production, application and build are separate facts: none of them is your disposition of the comment, which stays the comment's own status, or a review verdict.

## Find and plan recorded Work

Open **Tasks** from workspace navigation. It starts with unfinished, nondeferred Work and a **Suggested next to inspect** based on owner readiness and preferred order. **All recorded Work** includes completed, withdrawn and deferred history. The catalogue covers permitted namespaces, including Work whose namespace has no registered project. Reading that Work does not register or move it. The catalogue reports its full and matching counts, and **More Work** follows the same bounded observation cut. **Find Work** searches complete IDs, titles and purposes at the owner; namespace and **Status and planning filters** apply to that full catalogue. The unfinished view excludes recorded completions even when their current evidence needs fresh review. A filter does not discard the Work or planning form already open beside it.

Inspect a task to read its complete purpose, exact owner standing and permitted next action in the existing Work editor. **Hierarchy and prerequisites** opens its containing/contained Work navigation; Needs, Affects and Contains retain their distinct meanings. **Return to backlog** returns to the queue control. An unregistered namespace stays inspectable here; **Open Work in project** is offered only where the owner issues a real project destination.

**Plan this task** keeps the task's purpose beside your queue preferences; **Inspect complete Work** opens its permitted next actions. Larger priority comes first, then smaller preferred-order numbers; declared prerequisites still come before their dependants. Existing numeric values remain editable. Deferral is an explicit intention with a reason: it does not cancel running work, change readiness, create a prerequisite or grant permission. Recorded completion remains separate from current acceptance; filter lifecycle **done** with currentness **Review required** to find historical completions needing fresh review. Recorded **in-progress** alone is not an observation of a running process.

Planning fields are local until **Save planning**. After a lost response, **Check original planning save** reads that exact request. Only an owner **NONE** observation offers **Retry exact original save**; an unknown outcome never creates a replacement request. Newer fields remain separate from the submitted wire across navigation and reload. **Retained planning drafts and saves** reopens their exact Work target without requiring you to remember its current page. **Read current planning**, then **Use inspected guard for next save**, deliberately prepares a new decision while keeping those fields. **Refresh catalogue** explicitly reads the resulting order; a successful save does not silently refresh every task body. **Using the backlog** keeps the shared ordering and authority guidance available without repeating it in every row. **Status, planning and owner details** retains each row's exact facts; exact request and receipt details remain available below the form.

## Read review evidence deliberately

**Inspect review evidence** opens the selected Work's review summary directly. Its purpose and review outcomes lead, followed by required, satisfied and remaining obligation counts. These count review obligations, not follow-up tasks, phase records or evidence files. A Work without managed review says so; zero required obligations is not automatically a 100% success rate. Local satisfaction, currentness, independence and pending follow-up joins remain separate owner facts.

Choose an offered obligation list, then **Inspect evidence routes** for a particular obligation. A complete summary can have an unexpanded or paged list: **More obligations** follows the same observation, while selected support describes only the requested obligations. Inspection routes and expanded metadata do not mean original evidence bodies have been read. Follow an explicit phase or body read when you need it. An exact phase read guards the observed rowset; it does not reconstruct historical rows after they change. Retained Source facts keep their separate handed version and body basis.

If a consumed input changes, the old continuation refuses rather than mixing observations. **Read fresh review summary** deliberately begins a new observation; it does not refresh a pending save, change a review target or adopt a new edit guard. Reopening after a process restart can continue only when the owner can reproduce the same observation. Close and Back restore the actual opening control and its disclosure unless a later keyboard or focus choice takes precedence. Work editors, newer Unicode text and original pending requests remain separate from these read-only inspections.

## Source and older engine obligations

The Backlog offers **Inspect Source contracts** only through its owner's issued read. Select a known registered project in the existing **Namespace** filter to inspect Source in that reading context and follow its permitted pinned human source reads. **All** retains the global read; an unregistered or unavailable project does not acquire a project/body reader. Changing the filter affects a later Source entry, while an already-open inspector keeps its captured scope and normal Back/Close behavior. This is read narrowing, not Source execution authority. The Source inspector separates the current declaration, explicitly selected retained Work/handoff facts and a verified kernel counterpart. Selecting a retained publication or preparing its leaf metadata is read-only: it does not ingest, fold, approve or grant a source change. **Read retained facts** follows the handed version; a separate current-standing read cannot rewrite that historical basis. **Check published counterpart** may remain unresolved until actual verified publication exists. The selected reading leads with its kernel state, Work/obligation scope and useful reads; exact limits and metadata remain in expandable details. A published reading identifies the active publication and exact selected node, content and semantic identity. It distinguishes a **selected Source contribution** from an **ordinary active publication** that retained the selection; both prove only the selected Source scope shown here. Other kernel contents follow their carried historical basis, without renewed currentness. The exact receipt, parent/retained bases and declared derived changes remain expandable. **Recover exact published meaning** follows the offered current-publication object read; retired fold receipts do not establish a current Source counterpart. Unavailable older publication bytes are reported rather than replaced with a newer tree. This reader offers no publication effect or permission toggle. Closing a nested reading restores its re-rendered opening control; a later focus or keyboard choice takes precedence.

In **Inspect owner declaration**, the purpose leads to named **Read part** controls and **How this operation proceeds** step readings. These are current owner facts, not instructions to run the step. Each selection keeps the observed declaration version and part basis; if they changed, the reader withholds the old constituent and offers explicit current reinspection. An observed current digest is not an already-retained historical version. **Up to operation overview** and Close keep the exact reading trail and its re-created opener.

A retained Work publication can hold nine parts while the reader selects one. The displayed retained/selected counts describe that cut. Follow the offered previous/next part or up read to inspect the rest; no other part body is fetched automatically. Current declaration, retained handed facts and an actually verified published counterpart keep separate headings and guards. Local draft text, addressed target, evidence inputs and pending requests are unaffected by this navigation.

**Historical engine obligations** opens a separate read-only catalogue of existing engine work orders or promises. Its effective statuses and bounded exact record readers are not canonical app Work, proof of fulfillment or permission to migrate, close, order or start anything. Counts cover the selected engine source, and reading may scan that bounded source; it is not a constant-I/O or complete historical audit claim. Closing the reader returns to its Backlog opener while Work planning fields, pending saves and native editors stay mounted.

## Working through a project

The project has six working views: Project, Structure, Research, Manuscript, Review & notes, and Figures & output. They edit and inspect the existing canonical records. The same live conversation remains available across all six views; changing activities does not open a different editor or lose the conversation draft.

| Stage | Material it consumes | What uses its output |
| --- | --- | --- |
| Purpose, reader and form | Author framing and manuscript specification | Research goals, sustained argument, document form |
| Concepts, claims and dependencies | Corpus network, typed rewires, definitions and source links | Glossary, logical prerequisites, result verification and explanatory order |
| Literature, numerics and proof | Zotero associations and local attachments, declared producers, run receipts, results and formal manifests | Result conceptrics, claims, visuals and writing contexts |
| Connected argument and shape | The project argument, concepts, evidence and projection specification | Chapter structure and coherent writing scopes |
| Draft, discuss and revise | Selected source edition, neighbouring prose and applicable feedback | Reader, source versions, review and compiled document |
| Review and propagation | Exact dependency receipts, author edits, comments and independent findings | Affected work orders and fresh revisions |
| Visuals, style and publication | Data and result identities, visual specifications, house style and document profile | Asset inventory, inline figures, compiled PDF and local exports |

A stage being available or current does not mean its scientific claims have been independently established. Empirical and formal evidence are chosen for the kind of claim; neither is imposed on every piece of writing.

Use the library to open existing projects or create a book/article. Existing sources can be registered with explicit read-only/editable choice. Registered projects with empty roots can start a new working draft without replacing the old files. Empty chapter/section creation is versioned and updates the selected root’s input order. A manuscript can retain multiple source editions; reader, editor and revision application follow the selected edition.

Set the purpose, reader, question and form, then develop the sustained argument. Create work orders around uncertainties and completion conditions. Prerequisites use effective currentness, including their own upstream dependencies. Completion names real evidence files and records their hashes. Recorded completion remains in history. Changed consumed evidence can require fresh review and block current acceptance; inspect currentness before treating a recorded completion as current.

The writing grain is a connected explanation. Fine-grained evidence identities do not require separately generated paragraphs or a final voice-welding pass. The staged workflow now returns a canonical reviewable proposal by default. Explicit `applyProposal: true` crosses the guarded Apply door; validation and compilation follow actual application. The caller stops at proposal review when acceptance has not been supplied, and never reports a proposal as an authored or compiled manuscript.

## The live session

The selected conversation mode is retained per conversation, including across
reconnects and page reloads. Loading historical messages does not replace a new
composer choice with the last turn's mode. Healthy native-window focus checks do
not trigger session recovery. Independent review still uses its own conversation.

Choose the conversation, then **Model & settings** beside next-message intent to inspect saved provider, model and effort with each recorded origin. A value equal to a project default is not continuing inheritance. Role and conditional actions are read-only owner facts; **Read exact admitted turn** opens the captured turn when one is recorded. Full origins and mechanical facts remain under details.

Edit the next-message fields, then choose **Save next-message preferences**. Field changes alone start no work. New-conversation choices stay local until ordinary admission. **Make project default**, under **Future new conversations in this project**, is a separate explicit scope; it does not change existing conversations, workflow workers or admitted work. Unsupported/current choices remain visible for inspection; a provider change never silently replaces dependent fields.

Beside **Model & settings**, one line states together where the next message goes, what it reads, its intent and that settings apply only to the next message. When a sent request is retained or a turn is active, the same line says so. Typing then changes only a later message or steers the active turn, and nothing is sent until **Send**.

An uncertain save retains its original wire and your newer fields. **Check original save** is a pure read; **Retry original save** uses only that wire after known absence. **Edit again — withdraw pending save** closes an unadmitted request before a new deliberate Save. Withdrawal cannot undo recorded settings. Unknown custody keeps the pending request. Send and reconnect never silently retry a settings save. Close and Escape return to **Model & settings** without changing the composer target or draft. **Open separate review conversation** explicitly opens another conversation; it is not a permission toggle and the old conversation's draft remains there.

The project header keeps task context separate from the current view. **Home**,
**Writing**, **Sources**, **Tasks** and **Research** lead the project navigation;
secondary views remain in **More project tools**. Conversation navigation is
separate from its message destination and future settings. **Refresh status**
observes the selected admitted turn; **Stop active turn** asks its owner to
interrupt it, without undoing a result or proving every workflow child stopped.
When space is tight, **Back to reading** and **Show source instead** switch the
existing surfaces without replacing the retained reading or unsent text.

- **Discuss** streams a reply into the panel. Conversations are persisted and can resume; reconnects use an event cursor. Provider, model and effort settings reflect discovered capabilities. Older conversations and older messages can be loaded.
- **Propose revision** returns exact source-addressed before/after edits. The author applies them explicitly. Source, selected-edition, feedback and consumed-evidence changes can refuse an obsolete proposal.
- **Work on project** exposes the same project producers used by the interface: concepts, tasks, scoped research artifacts, numerical producers, results, visuals, formal checks, document style and export.
- **Independent review** starts a fresh review conversation. It can inspect, save findings and create work orders; it cannot change the reviewed artifacts or award itself verification. Review findings enter the subsequent writer’s context with their machine origin retained.

Saving provider, model or effort preferences retains the logical conversation and its draft. Changes apply to future messages only; admitted turns keep their captured settings. The installed Codex protocol persists a thread’s original dynamic-tool declarations. A changed tool contract therefore resets the native binding while retaining the logical conversation and bounded exact history. The live operating guide, operation payload contracts, current permissions, selected voice profile and project guidance are loaded on every start/resume. The reply records their revisions, and source reads include numbered addresses beside unchanged source text. The saved project argument and feedback remain independent of the native provider thread. The adapter was checked against the installed protocol schema and the [official App Server documentation](https://learn.chatgpt.com/docs/app-server).

Codex’s advertised models/efforts are validated before starting a turn. Both the configured default `gpt-6-astra` and `gpt-5.6-luna` completed real local-account checks. Claude’s adapter is present, but its account was signed out during acceptance. It is shown as unavailable until `claude auth login` succeeds; **Refresh providers** rechecks it. Claude generation/resume parity is not claimed from executable presence.

Provider delivery and accounting are declared by `laplace.writing.operating`. Session policy `/2` places the app kernel in Codex `baseInstructions` with an empty app developer slot; both adapters carry the same project body and current mode/permission frame in the user channel. Policy `/1` remains historical evidence. Delivery receipts distinguish prepared or sent bytes from observed runtime inventory and unobservable provider retention. Requested feature flags do not prove that provider-owned instruction or capability extras were removed; strict provider parity still needs actual admission evidence.

New replies retain `usage_facts` and `delivery_receipt`, plus slim original header projections for history and analytics. Large bodies and filtered raw counter metadata use the existing writing body custody store. Explicit counter basis and domain separate a request input proxy from an app turn aggregate and native binding totals. Reasoning is a subset of output, omitted counts are unknown, duplicate assistant emissions are not summed, and provider-reported cost variants remain labelled estimates. Older replies are preserved without assigning them a new accounting basis. Exact metadata detail and custody errors remain visible through the saved turn owner.

## Feedback and direct editing

Select manuscript text to Comment, Discuss or Revise. A comment needs only its text. Click prose or a figure caption to edit directly, then use Save edits or Ctrl/⌘S. Right-click offers manuscript actions including Edit caption, Edit exact source, Discuss this passage and Focus manuscript. Captions carry their own exact source spans; changes preserve the figure code and labels. Unsaved prose drafts are retained locally; saving clears the local draft so reload cannot apply the change twice. Source spans, before/after text, context and versions are banked through the existing review/feedback doors. Unsaved prose and source-editor changes both block competing model application and document builds. Proposal preflight accepts exact spans, or records a deterministic correction only when the unchanged before-text has one unique full-line match in consumed scope. Ambiguous, missing, overlapping and out-of-scope addresses remain invalid, with no source write.

Review & notes shows comments and direct edits, with passage links and before/after inspection. Surviving quoted text reattaches feedback when line numbers move. A changed or unlocatable passage is not silently matched to a different ordinal block. Accepted model revisions retain a distinct origin from human-authored edits.

“Review patterns in my feedback” supports examining repeated corrections and examples. It proposes guidance for review. A local note does not silently become global law.

## Structure and writing profiles

Structure joins the canonical projection plan, narrative beats, conceptrics, typed dependencies, selected source and current evidence. Creating or editing that plan does not overwrite prose. A failed plan mirror remains explicitly pending and blocks revision application until reconciled. Logical prerequisites and explanatory order are distinct.

The recursive conceptric opens one bounded level at a time. Descent uses canonical child handles; Up re-derives `conceptric.identity_chain` against live state, so a move below changes the return path correctly. Typed dependency traversal is a separate operation. Goal-driven reconstruction uses the bounded keeper return machinery. This does not assert that the seed design for Atlas spectral charts and transition maps is materialized. Parent-focused authoring includes bounded descendants, uplinks and omission metadata; changes below a parent invalidate consumed contexts even when its authored summary is unchanged.

Writing style is separate from document presentation. Project settings select a voice profile and hold project-specific guidance and approved examples. The current style and operating instructions enter each model context automatically and are receipted. Changing the style invalidates older consumed proposals. Pattern review proposes guidance; it does not silently turn corrections into global law.

## Research, references and visuals

The writer can read the source repositories declared in `profiles/writing_sources.json`
through the `repository` operation: list roots, discover files, search literal text,
read bounded UTF-8/PDF passages, and view original PDF pages or raster images.
Rendered images are delivered as native model image content. Laplace, its Atlas
subdirectory, Eigenengine and Physics Paper Orchestra are configured on this host.
Source reads carry path and SHA-256; historical instructions stay source content.
This read access does not broaden the project write permissions.

Codex notifications are accepted only for the owning writer thread and turn,
including notifications arriving before the turn-start response. Descendant
completion cannot finish the writer or replace its reply. Native delegation is
disabled for this writing connection because client-executed project tools are
not available to its delegated workers. This is a per-session override; the
user's global Codex settings are unchanged.

Zotero access is API-first with a read-only SQLite fallback. Attaching a source writes only the selected project bibliography and association records. Citation identity is collision checked, including entry-bounded Zotero/DOI identity. Metadata updates preserve citekeys and authored notes. Available local PDFs can be extracted in bounded, paginated text with attachment hashes; missing local attachments remain explicitly metadata-only.

### Find document and reference actions

Open **Help** in Material or Research and choose **Find document and reference actions**. The short guide points to Material, Conversation, Context and Research using the controls already on screen. Its progress records finding those views and Context, not adding a document, saving a reference or linking a claim. It never chooses a file or performs those actions for you.

### Add a local document

In **Sources**, or in the conversation’s **Options**, choose **Add local document**. Select one PDF or UTF-8 document/transcript, check its name, type, size and destination project, then choose **Add document**. PDFs may be up to 16,000,000 bytes; UTF-8 documents up to 2,000,000 bytes. **Show this document in Sources** is an explicit choice. Adding stores an immutable original in the project’s data home; it does not send a message or start a review. Different bytes with the same filename remain distinct originals.

The result distinguishes retained original bytes from its Sources entry. **Inspect document text** or **Inspect PDF text** opens the actual retained source reading; a PDF also offers its original and first page image. Extracted PDF text does not establish figure or layout coverage. An unavailable extraction does not discard the original. **Use in conversation** explicitly selects the owner’s pinned reading for the original same-project conversation while preserving its text and Work target. Send remains a separate action. The read pane leads with the document name and actual byte/page coverage; source pins are under **Exact source observation**. Close and inspector Back preserve the intake request, conversation draft and last inspected reading extent. A reopened selection says **Last inspected**; **Reinspect selected reading** explicitly rereads its pinned page. **Use in conversation** focuses the held composer, while **View in Sources** focuses that destination; ordinary Close returns to the opener.

If a response is lost, use **Check document request**. A retained original needs no further file selection. If the owner still needs bytes, reselect the exact original and explicitly choose **Retry same document**; the request and intended source remain unchanged. An unfinished Sources entry offers **Check project before adding to Sources**, followed by **Add saved original to Sources** against that inspected project revision. This repairs the separate entry without uploading the original again. A completed entry that is later removed is not silently restored by replay. Technical identities and receipts are available under **Exact document and request details**.

### Add a retained document to Literature

After inspecting a retained original, choose **Add to Literature** in its document or Material controls. The original stays fixed; enter its **Title** and **Source provenance**, then **Save to Literature**. **More bibliography details** holds optional metadata. This mode has no local-path field and infers no author, year or DOI. The ordinary manual-path and DOI forms remain available separately. Asking a question through **Use in conversation** does not require bibliography setup.

An already-saved source leads with its title, **Read source** and **Link to claim**, reusing the existing passage reader and claim form. **Import draft** is optional and initially closed on reopen; it preserves authored fields without changing saved metadata. The reader marks the **Saved original** and returns Close to its Read source opener. Read an actual Literature passage before recording partial/read status or relying on a quotation; inspecting the ART original or importing metadata does not itself create that passage receipt. Claim linking still requires the inspected claim meaning, a relationship, rationale and located evidence. An interpretation is not independent scientific verification. A pending bibliography does not mean that source metadata failed to save, and citation placement stays explicit.

A lost acknowledgement retains the exact metadata submission and newer typing. **Check Literature source** observes the current saved source; it does not attribute the earlier request. If no source is observed, **Retry same Literature submission** resends only the retained wire. A named pre-effect validation rejection offers **Edit details**: it retains the rejected wire and reason, preserves newer typing, and requires another deliberate Save. Generic errors and uncertain transport do not unlock this action. A returned partial source-effect receipt keeps its warning and blocks blind retry. An unfinished bibliography retains the same submission; its explicit same-wire retry is offered only when no unresolved physical source effect blocks it. **Use saved source** accepts the observed source while preserving your metadata draft. Repeating an original reuses its saved identity and citation key; it does not overwrite differing saved metadata. **Saved metadata and bibliography** shows that standing. Inspector Back returns to the retained document and its selected page without changing the conversation draft or sending a message.

Numerical execution requires a declared producer, allowed arguments and smoke/full modes. Project-relative and manuscript-relative paths are explicit. Each run retains code/config identities, output checksum, exit state and logs. Timeout/cancellation belong to the job supervisor. Output presence alone cannot establish successful execution or scientific acceptance.

Visual specifications live in `manuscript_spec.json`; older visual-spec files are read-compatible. Matplotlib produces data plots, Graphviz produces typed relation diagrams, and authored TikZ supports scientific conceptual diagrams. PDF/vector output and previews are banked into the existing asset inventory. Data, specification, style and output hashes determine render currentness. Placement is explicit, section-addressed, idempotent and versioned through the review door. A declared intended location is not reported as actual placement. Placement checks the source revision and exact file state under a lock. Result-to-concept binding checks both structural and conceptric revisions, including for concepts not yet placed in the manuscript plan.

`figure_ids` normally denote downstream depictions of a result. Changing presentation does not invalidate the empirical result. An image used as upstream evidence must be declared explicitly. Formal checks bind a declaration to a result revision, pin the active Lean version and library identity, inspect transitive axioms and track local imports. `sorry`, `admit` and `sorryAx` do not qualify as checked proofs. Formal statement-to-scientific-claim alignment remains a separate judgement.

Existing figures are resolved from the selected manuscript’s actual declarations, including sibling directories used by imported manuscripts. Both asset routes require those exact declared dependencies. Every image in a multi-panel figure is displayed. Raster dimensions reserve reading space; PDF figures load near the viewport and release their documents when replaced. Inline TikZ and tabular figures use a bounded cached TeX preview with shell escape disabled and source-revision checks. This produces a display cache without changing authored files.

The reader handles explanation labels from the actual preamble, nested lists, algorithmic controls, theorem/proof titles, longtables, parboxes, footnotes and provenance tags. Unsupported syntax remains marked and source-editable; unresolved authored numerical placeholders remain unresolved. A provenance tag is not a verification status.

## Presentation and output

Document profiles cover book, article, report and briefing layouts, with page size, text size, margins, spacing, columns and visual adjustments. The figure dimensions follow the available column width unless explicitly overridden. The shared visual style remains the default.

A style preview compiles a staged source tree, preserving original prose and files. Declared sibling bibliographies and symlinked figure inputs are mirrored into the preview workspace. Source, bibliography, style and figure dependencies are checked for staleness. Style previews and saved PDFs open in an embedded reader with page controls, text fallback and download; it renders one page at a time and releases the worker on close. **Export PDF** keeps a versioned deliverable and its build receipt in the manuscript’s `exports/` directory. **Build PDF** compiles the selected source edition through the existing compiler. Compiler failures remain visible; they do not replace the source with guessed repairs.

## Runtime and verification

The app starts one owned loopback scanner on demand, with prewarming disabled. It starts no idle model process, watcher or embedding workload. Provider processes and build jobs run when requested. The launcher recognises its own process, does not replace an unrelated listener, and defers upgrades while writing, numerical runs, formal checks, previews or builds are active. The desktop host replaces the launcher process and uses WebKit's document-viewer cache policy; no duplicate launcher interpreter stays idle. System dependencies are recorded in `runtime_profiles.toml`, and none is installed at startup. A lost backend is restored on activation or a failed connection without reloading a healthy page. Initial-load failures offer reconnect instead of a raw connection-refused page. On this X11/NVIDIA host, the viewer uses the software compatibility mode; scientific GPU work is unaffected. The host follows the [GTK application lifecycle](https://docs.gtk.org/gtk3/class.Application.html) and [WebKitGTK WebView API](https://webkitgtk.org/reference/webkit2gtk/stable/class.WebView.html).

Acceptance evidence is under `evidence/WRITING_2026-09-26/`. It includes independent consumer reviews, actual local-account provider checks, real Lean checks, real TeX builds, parser/source-span checks, and browser walkthroughs. Fixtures are isolated from live manuscripts. Existing unrelated scientific changes in the working tree have been preserved.

Library inventory is live and includes newly imported projects. Empty registered roots such as `free-snacks` and `qde` remain explicit empty-source states with a draft-start action. A missing manuscript is not reported as successfully rendered.


The observed resting footprint on this host was 276.9 MiB proportional memory across the window, renderer/network helpers and owned engine, with no measurable CPU ticks over a 10.262-second sample. Active navigation is recorded separately; builds and provider work have additional transient cost. The author confirmed that the corrected native window felt smooth. These are bounded measurements, not a guarantee for every workload or graphics stack.

The existing `author_history` owner also serves metadata projections with `view: telemetry`
and `projection: sessions|trace|overview|usage|delivery|feedback|coverage`. Select an explicit
project, workspace, session, turn or work scope; `turn_id` is distinct from the older dispatch
`row` filter. Returned `next_read` handles preserve a selected source cut. Fresh reads admit
new rows; changed retained selected rows refuse page mixing. Sessions use the existing
bounded conversation display-title rule and recorded recent activity order. Numerical and
trace projections contain identities, counts, coverage and lazy owner reads, without public
prompt/reply/comment/error/source bodies. Original tool rows are counted once; derived read
baselines are excluded. Containment, prerequisites and turn parentage remain distinct.

Usage projections import the collector's canonical usage-facts contract. Context snapshots,
logical-turn counters, cumulative binding counters and unproven provider variants remain
separate. Only compatible reported logical-turn bases aggregate; absent counts remain unknown,
reasoning stays an output subset, and estimates never become invoices. Legacy usage has unknown
basis. Delivery states and available admission hashes do not prove unseen provider retention,
inventory or historical policy bytes. `activity:admission:<WT>` reads the original immutable
admission lazily; `activity:feedback:<FB>` reads one existing canonical feedback row.

An exact response note may carry `feedback_target` returned by its trace and an explicit
`feedback_effect`. The target binds project, session, turn, reply ID and response SHA256 before
writes. The default `observation_only` effect, including discussion replies, is readable history
and cannot constrain writing or retire instructions. `instruction` is an explicit choice;
existing actor/scope rules still apply. Candidate decisions, source edits and undo continue
through their original guarded owners; no sentiment or causal attribution is inferred.
