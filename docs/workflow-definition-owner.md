# Reusable workflow definitions

`pipeline.workflow` owns definitions, assignments, versions and compilation. The
implementation leaf `pipeline.workflow_definitions` keeps typed `workflow-definition`
rows in the existing `contract/dispatches.jsonl` and JSON bodies in the existing
root-scoped Writing body custody. These rows have no execution selectors. Definition
IDs (`WDEF-…`) and stable step/edge IDs survive project membership and custody moves.
No manuscript project is required for a workspace-owned definition.

The local SDK methods `workflow_request`, `workflow_save`, `workflow_prepare` and
`workflow_restore` use the same owner as `/work/workflow-definitions` HTTP reads and
its `/save`, `/prepare` and `/restore` POST routes. Trusted adapters choose scope;
request fields cannot widen it. A project-confined native `project` read with
`view: workflow-definitions` sees only definitions explicitly owned by that project.
A current admitted author turn can use `workflow_definition_change` with
`action: save` and the owner's `actions.create/save.native.payload`, adding the
complete definition and stable request ID. Actual project/session role and current
execution are checked again under the writer lock. Review, stale and unattributed
callers cannot save; payload labels cannot widen scope. Native Restore and legacy
carrier preparation remain unavailable; Start uses the separate existing dispatch
owner. A coarse read without turn context says admission is
required. Save and request recovery return the same owner receipts and exact reads
as HTTP/SDK, including saved effects whose readback is unavailable.

The explicit `laplace.app-dispatch/1` preparation profile connects a selected saved
project definition to the existing app dispatch owner. Native
`workflow_definition_change {action:prepare}` requires the exact reference,
selected `step_ids`, completion `goal`, explicit `fan_out_max` and stable
`request_id`. Its schema comes from `native_change_contract()`. It retains one
project plan ART and one dispatch Work, with complete packet instructions,
effective settings and stable step-to-packet mapping. Preparation creates no
session or provider child. The legacy `laplace.workflow/1` profile remains a
separate external carrier.

The first app slice supports builder and adversary roles only when the authored
control dependencies match the carrier's ordered worker/judge dependencies.
Selected Synthesis, feedback/data edges and unconsumed inputs, outputs, targets
or input policies return local obligations before effects. Automatic parent
consumption is identified as generated framing; it never replaces authored
Synthesis instructions.

The exact plan and preparation project/session/turn are immutable provenance.
A later explicit Start may use a new currently admitted author turn in the same
original session. It rechecks actual authority and the exact plan before effects;
another session cannot adopt the preparation. First launch records its actual
parent turn through existing dispatch admission. Subsequent replay and parent
continuation retain that admission.

An interrupted preparation is inspected through the existing request facet.
Explicit same-request recovery reuses the exact ART and Work. If ART publication
was interrupted, its owner may republish only the originally absent typed
artifact, with matching retained bytes/request metadata and no later artifact
edit or inverse. Different bytes are never overwritten and no replacement ART
is minted. Partial effects and unavailable readback retain their receipts.

`app-runs` and `app-run` read facets expose the actual dispatch Work and its
recorded packet/session/turn joins for one exact WDEF version. They keep recorded
standing, observed execution, review and historical-definition currentness
separate. Full public content, typed returns and existing conversation controls
are followed through owner-issued handles; missing bindings stay unavailable.
`app-compose` and `app-launch-compose` are read-only composer descriptors. Their
qualified project URL re-reads the exact action before composing the existing
`/authoring/turn` payload. Send remains explicit; an HTTP read never invents a
logical parent turn or launches a dispatch.

A definition contains full local instructions, nested steps and semantic roles,
settings, typed control/data/feedback edges, declared inputs/outputs/targets and
presentation layout. Save admits unfinished independent branches, feedback and
arbitrary semantic role labels; it rejects containment cycles and malformed shapes.
Save requires a unique request ID and exact `expected_revision` (null for create).
Identical completed requests return their receipt; changed content under the same
ID refuses. Historical reads retain their original save guard and exact version,
with a separate current handle for explicit comparison/adoption.

The settings resolver applies definition defaults, nested ancestor assignment
settings, then local assignment settings. Omitted provider/model/effort keys resolve
through the existing passive catalogue and worker/judge tier policy. Project author
conversation preferences are not worker defaults. Explicit models are retained.
Each effective key includes value, origin and authority ceiling; role labels and
input-policy text confer no tool/source authority. Group instructions are displayed
as their own full text and are not silently concatenated into child instructions.
Global/subsystem policy mutation and project setting joins are explicitly unavailable.

Prepare consumes an exact saved version and an explicit selected slice, profile,
source node, goal and write-path list. The first profile is the existing ordered
`laplace.workflow/1` Codex carrier: 2–16 selected stages, builder/adversary roles
and final synthesis with all inputs. Unsupported feedback, provider, role,
input/output mapping or custom input policy refuses locally; the saved definition
remains usable. Other existing Claude/session/dispatch routes are unchanged. Current
Work target guards compare under the actual Work writer lock before the definition
lock. Unsupported historical/foreign targets remain explicit draft obligations.

Prepare creates the existing immutable run declaration with definition/body,
selected-step, consumed settings and semantic pins. It returns `NOT_STARTED` until
existing run records show execution. Start remains the existing separate run owner.
Editing a newer definition never changes an earlier plan. Full edit CAS includes
layout and labels; consumed execution meaning excludes those and shadowed settings.

`facet=request&request_id=…` reads completed receipts after an uncertain response,
including a lost create response. Missing records say `NOT_RECORDED` with unknown
effect; no automatic replay follows. A complete preparation candidate interrupted
before declaration is recovered under the same request ID; incomplete evidence
reports uncertainty. Effect receipts and readback availability remain separate.

`facet=export` carries the exact version chain through the selected version and all
bounded bodies (up to32versions/1MB). Restore verifies identity, chain, bodies and
scope in existing custody, preserves IDs/history and can resume an exact prefix.
It requires local workspace authority and transfers no source/run grants. Originals
are not moved or rewritten. These finite bounds are explicit refusals, not partial
exports represented as complete.

An explicit versioned read and a selected object handover use one owner-local
captured selection of the dispatch journal. The selection retains the original
physical rows, their hashes and the complete admitted same-definition prefix
through the requested revision. A later valid head does not replace that revision;
repeated requested definition IDs, ambiguous revisions, broken predecessor links
and reused request identities refuse. The 32-version bound applies to the selected
prefix, so a short old prefix can remain transferable after more versions exist.
Selected preparation pins use the same capture and retain `DECLARED` with unknown
activity; preparation rows are not part of the definition export.

This is a private metadata index, not another definition store or a public query
API. Its first capture still parses the journal, including the largest row.
Subsequent capture can reuse unchanged metadata and read a suffix; selected raw
rows and bodies are rechecked. Replacement, truncation or incomplete capture
cannot establish healthy selected custody. Append-only custody and anchor checks
do not certify arbitrary edits to every unselected middle byte. Library reads,
save/request recovery and run/preparation paths retain their existing costs;
current settings and target observations remain separate from saved body custody.

Use a returned handle's `request` with SDK `workflow_request`, its `native` project
read with the actual caller scope, or its exact HTTP read. SDK `request` is the
discovery dialect and is not a substitute. On a recipient containing an old
selected prefix, the same version may be `CURRENT` locally although the origin
called it `HISTORICAL`. This does not assert the origin's latest head, retain its
effective settings, or transfer execution permission.

Stable saved step IDs are not restricted by the legacy packet-name grammar. Prepare
uses a deterministic collision-checked mapping into legal packet IDs, pinned as
`step_stage_ids` in the immutable definition pin and preparation receipt. Control
dependencies are translated through the same map; saved IDs are never renamed.

Restore validates closed record fields and exact receipt identity against each
version/body/request, and refuses imported or destination request-ID collisions.
One request ID cannot name both Save and Prepare. The journal stamps the local
custody event; the imported owner timestamp remains `ts_claimed` across transfers.
These chronology fields are separate from immutable semantic version identity.

Preparation candidate recovery inspects at most64existing manifests per bounded
read. Unreadable unrelated files are local unavailable diagnostics and do not
block valid Save/Restore. Ledger declarations and readable typed candidates keep
their request reservations. Partial/omitted candidate coverage never proves no
prior effect; project-confined readers receive neither foreign names nor counts.
A known declared request with missing evidence remains unavailable/uncertain and
cannot create a duplicate run through retry.

The POSIX execution lock is imported only when the existing carrier's Start is
selected. Its absence produces a typed unsupported-execution refusal before a
runner lock, ledger transition or provider start. A fresh-process test masks
`fcntl` and exercises existing SDK/HTTP/native imports plus definition Save/read
and Prepare; this is simulated import reach, not observed Windows parity.

Default packet-return and judgement schemas are packaged with the Python library.
Wheel builds copy the four unchanged canonical `profiles/workflows/*.schema.json`
inputs into package resources; source checkouts use those canonical inputs directly.
An explicitly supplied workspace `profiles/workflows` directory remains authoritative,
including an empty directory. An absent workspace override uses library defaults;
installed callers do not need a source checkout or an `/opt` profile directory.

App-run and exact app-step reads expose `prepared_dependencies` with `status`,
`edges` and `source: project_work.dispatch_view`. Each edge names the stable
`prerequisite_step_id` and `dependent_step_id`, sorted by dependent then
prerequisite ID. This maps only the canonical carrier dependency relation through
the immutable selected `step_packets`; it does not infer execution edges from
saved roles, ordering, containment or arbitrary authored relations. Complete
one-to-one mapping and exact packet/endpoint coverage produce `AVAILABLE`, including
an empty edge list when the carrier has no dependencies. Missing, foreign,
ambiguous or malformed mapping produces `UNAVAILABLE`, an empty edge list and a
reason, while retaining independent run/step observations. A step whose packet
binding itself is missing or ambiguous is `UNAVAILABLE`, with no invented child.
The exact saved body remains behind `definition_read`; unselected saved nodes are
outside this run, rather than steps observed as not started. Observed execution,
review and Work state remain separate snapshots, with explicit refresh.

## Bounded research proposal and review

An explicitly saved `run_policy` with profile `laplace.research-review/1` selects a
bounded proposal/review loop. The new unsaved starter offers a builder, an
independent adversary, a control edge to review and a feedback edge to revision.
Its defaults are two iterations, 300 seconds per recipient and a separate human
manuscript Apply. Existing definitions without this field keep their existing
compiler and execution semantics.

Preparation selects exactly one writer and reviewer, their saved instructions
and effective settings, actual owner-issued input windows, and the manuscript
scope. The complete selected evidence and saved step instructions enter the
private owned prompt/body path; the concise turn task retains the ordinary
author-message limit. Exact packet serialization/custody and request shape are
validated before a new recipient session. Provider capacity remains provider
owned; no clipping or blanket packet-fit claim is introduced. It retains a selected-evidence packet and plan in existing artifacts and
Work. Evidence review is explicitly project-informed; unsupported target-only
combinations refuse before launch. A definition, graph role or review approval
cannot grant writing, research execution or development Source authority.

The run view offers explicit human approvals for the consumed writer/reviewer
settings. Prepare start message opens the original author conversation. Send
admits that exact selected action; its native Start request and the parent
submission each retain their own request identity and pure reconciliation read.
The actual writer admits proposals only, the reviewer admits scoped findings,
and manuscript application remains a separate guarded human action. A valid
review `ACCEPT` reaches the human boundary; `REVISE` retains findings and consumes
another bounded iteration. Missing, malformed or non-object reviewer results
retain their raw reply and settle as partial terminal responses. Known pure
admission refusal precedes new WS/WT creation and remains distinct from an
unknown acknowledgement after publication; explicit replan retains its facts.

Stop before next prevents another admission while preserving the active attempt
and its eventual result. Explicit resume revalidates inputs and the pending
phase. Replan retains prior attempts, proposals and judgements and records a new
plan artifact/version; it never silently edits the consumed definition. A stopped
original parent cannot automatically launch later recipients. Readdress changes
only a permitted future effect recipient. Scientific dispositions reach the
canonical scientific concern owner with its exact concern basis; Work retains
that receipt rather than claiming an independent clearance state.

Registered Research recipients use explicit effect approval, a declared producer,
mode, arguments, inputs and an enforced finite runtime. The selected obligation
must cover the executable and every declared dependency. Existing Research job
and supervisor custody provide exact-request recovery and verified cleanup.
Producer completion and scientific acceptance are separate. No workflow policy
borrows the development Source-only native-call allowance.

Unknown acknowledgements retain the original request/event and any observed
WS/WT/job. Pure `NONE` means no matching retained request at that read cut; it
permits only an explicit identical retry and does not certify no effects. Exact
recorded request replay reconciles the original effect, never another child.
Prepared, admitted and actually sent settings are shown separately; sent values
are unobserved until an actual adapter receipt records them.

### Prospective intervention and acknowledged observations

`workflow-impact-preview` is a pure Work-delivery read. It takes the exact Work
specification, run revision and plan generation plus one supported replan or
future-recipient change. The compiler reports `READY`, `REFUSED` or
`CHANGED_INPUT`, retained actual attempts, selected input/settings differences
and future recipient standing. No artifact, reservation, approval, flag, quota
claim or turn is created. Readiness does not establish provider capacity or
grant future authority.

A ready preview issues a separate existing effect with its exact impact basis.
Confirmation revalidates the Work/run/generation and prospective inputs,
settings and approval revisions before publication. Readdressing preserves the
already-admitted recipient; replanning retains old attempts and effects. An
original recorded request still replays before mutable preview checks.

Acknowledgements carry an exact original `request_receipt`. A workflow mutation
also identifies its current response-root projection separately from the
historical decision snapshot in the receipt. Consumers may reuse that observed
projection, but an old approval receipt never becomes a current execution grant.
Pure aggregate reads can share one private request-local task/fold/facet/origin
frame; no JSON field transports that frame into mutation or admission.

<a id="bounded-complete-history"></a>

## Bounded complete history

The opt-in `history-page`, `lineage`, `lineage-page` and `saved-version` requests
come from `pipeline.workflow_definition_history.request_contract()`. Follow each
returned handle's exact `request` with `sdk.workflow_request`, its native companion
inside the actual project scope, or its HTTP read. Do not put this project payload
into `sdk.request`, which remains owner discovery. Scope is checked before capture;
a project lens narrows an actual caller and never grants workspace authority.
Library rows expose definition custody `scope`; top-level `scope`/`scope_id` qualify
the actual caller observation. They are deliberately different for an owned caller
reading a project-owned definition.

History pages are newest-first. `ordinal` is the 1-based chronological owner
position, so a newest-first page counts down. `lineage` describes the selected
prefix; `lineage-page` exposes its original rows oldest-first. `head_at_start`,
selected version, exact root/scope and retained prefix bind the cut. A later valid
append can preserve that prefix. A malformed, duplicated, gapped, unavailable or
changed prefix refuses instead of mixing pages. `current_head_read` is a separate
explicit observation, not a new interpretation of held pages.

`known`, `returned`, `covered` and `at_end` describe one delivered page and cut.
They do not record what every client loaded or certify body inspection. An
oversized position keeps its notice and exact read; it is not silently omitted.
Metadata pages perform no saved-body fanout. Cold capture/index/chain work can
remain linear, and selected raw rows are rehashed; anchor heuristics do not prove
every unselected middle byte. Existing capture byte/metadata-row budgets remain
explicit resource admission, not a promise arbitrary history fits.

`saved-version` is read-only and checks the exact ID, version, custody scope and
cut. A small complete body remains a verified definition. A large one returns
`BODY_PAGE`, `definition: null`, exact original UTF-8 JSON text, a raw byte SHA,
Unicode-code-point offset/count and `next_body_read`. Deliberately follow those
reads in order; require unchanged bindings, total and pin, then verify the joined
UTF-8 bytes and parse the complete JSON. Partial text must not masquerade as a
complete definition, including under technical details. Original valid spacing
is retained. Currentness/observed head is separate metadata; an older origin
version can be a recipient's local current version.

The whole new response fits the existing effective Work/native delivery line,
including reserved door additions; no global cap is raised. New HTTP numeric
fields are typed by that adapter and duplicate query/JSON fields refuse. Legacy
rich reads/history preview and v1 export/validate/restore keep their existing
32-version/1MB bounds. `lineage-v2` is a distinct fresh-root handover profile, not
an in-place restore, version squash, execution-settings migration or published
kernel node for the source label `pipeline.workflow`.
