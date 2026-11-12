# Independent work, adversarial judgement and synthesis

**Current entry:** new campaign waves use [one grammar, two launchers](#current-practice-one-grammar-two-launchers-law-proceduredispatch-distil-first): `distil.py preflight` and `brief`, then the provider launcher. The exact-text carrier documented first below is retained historical machinery, not the default route for new waves. Current writing-campaign reconciliation and limitations are in [its continuation](../evidence/WRITING_JOINS_2026-10-04/codex-continuation/NODE.md). This entry notice does not establish provider parity.

## Connected parent continuation in the writing app

The existing author turn can opt into one connected observation by admitting
`connected_observation_seconds` before provider setup. The model reads that
admission through `session_settings`, declares a distinct `synthesis_return_path`
on its existing `dispatch_plan`, then calls `dispatch_launch` with the exact
dispatch ID and `await_completion: true`. The same native tool call waits on
owner state. Parent execution remains `RUNNING`, with a nested continuation
phase `WAITING`; judge dependency `WAITING` still means no provider inference.
There is no scheduled parent resume, repeated model polling or extra paid turn.

The observation duration bounds the connection only. It leaves the original
dispatch deadline and detached child supervision unchanged. Claude receives an
invocation-local native MCP timeout of that duration plus a declared five-second
return/cleanup margin. Codex uses its existing threaded reverse callback, whose
host handler has no separate timeout setting; the observation and governor own
the same semantic bound. Finite observed transport probes do not prove arbitrary
native durations. The representation limit is the native timer range, not an
arbitrary task-duration policy.

Successful, rejected and failed settled children all wake the connected parent;
execution and review standing remain separate. Expiry records
`OBSERVATION_EXPIRED` before the existing governor ends inference. Parent Stop
records `PARENT_STOPPED` and ends parent observation only. The separate guarded
dispatch cancellation action cancels child work. Neither late completion nor a
new session turn revives the old native call. The final continuation receipt is
banked on the existing immutable writing reply before host cleanup; an absent
reply after a crash remains unknown. Exact historical replies remain addressed
after a newer turn occupies that session's host.

The implicit `parent-consumes` synthesis uses `laplace.packet-return/2` with
`role: synthesis`; it is never another child. Before publication, the original
parent or an explicit Work recovery turn in the same author session must read
the exact admitted plan, prepared input if any, and every available worker/judge
return, including rejected outcomes. The owner derives those required pins and
checks complete consumed read coverage. Missing or unstarted packets must appear
in remaining work. Caller-listed input pins alone cannot qualify synthesis.

`task_status` consumes and pins the reserved current synthesis. Rejected, failed,
blocked or incomplete results cannot mark Work done; a blocked synthesis retains
its evidence receipts. Publication and attachment are separate recoverable acts:
if attachment fails, inspect the retained ART and use its exact guarded
`attach_action` without republishing. Parent scope, containment, plan and unrelated
prerequisites retain their admitted guards; only the exact waited dispatch's
expected lifecycle changes are allowed. Recovery always composes an explicit
inspected Work message in the original parent conversation. A dispatch admitted
without connected wait intent retains its passive status/return/synthesis route
and cannot adopt a new wait basis or silently relaunch children. Legacy plans
without the optional synthesis field keep their previous identity and behavior.

An admitted independent judge has one scoped `store_artifact` permission: its
own exact declared project return path. The operating frame, `help` and
`session_settings.return_contract.publish_action` expose that same capability;
ordinary review still cannot write arbitrary artifacts or reviewed source. A
negative judgement must be returned through that publisher as well as any
corrective Work the reviewer authors. A completed provider reply without its
typed return remains `NO-RETURN`. Recorded tool failures and a model's reported
inability are displayed separately, with exact saved-turn inspection.

The parent contract supplies the authoritative registered `/2` schema, exact
required read actions, retained report options, and a publication scaffold whose
pins, scope, guard and actual read-check are filled by their owners. The parent
authors the conclusion and reasons, then publishes through the existing
`store_artifact` action. A successful owner read is `PASSED` even when the read
reveals a failed dispatch. Blocked/incomplete/interrupted synthesis retains a
continuation object and remaining work, with empty residuals; only demonstrated
impossibility belongs in residuals. Refresh the contract after required reads to
obtain the actual consumed receipt, without polling or replaying children.

Native `dispatch_status` defaults to a small status summary. Its owner-issued
`read_contract` selects `view: return-contract` on that same operation: required
read actions and one copy of publication content, without a duplicate scaffold
or schema. `view: return-schema` reads only the authoritative schema; `view:
detail` inspects child evidence. Direct operation calls remain supported; the
ambiguous generic `read task@project` shim is not the status route. Child
`session_settings` likewise exposes its publisher in summary and reserves the
full profile for its explicit `return-schema` view. No provider-side saved
response file is needed by these routes.

Prepared Work recovers retained dispatches from its exact contained prerequisites,
even when a newer same-session parent turn ended without another wait receipt.
One retained dispatch composes recovery in its original parent session; multiple
retained dispatches require exact selection. An explicitly empty current scope
cannot revive a historical wait. Ordinary scoped Work also contains and depends
on the dispatch it creates, preserving that same recovery and completion route.

### Prepared completion: produced, awaiting proof, review, synthesis and delivery

A Source producer that has finished its changes can arm one prepared completion per grant and obligation
(`development_source {action:"arm"}`, from the grant's original parent author turn while it is still active).
The intent pins every changed and obligation input, the approved recipient and the return policy. It is a
prepared continuation, not a review, acceptance or completion. Declared peer proof arrives through
`development_source {action:"proof", intent_id, slot_id, reference:{id, expected_sha256}}` into its declared
slot; arrival is recorded and verified against the retained Artifact bytes, never judged. Readiness is the Work
owner's current derivation, not a separate controller ledger: `AWAITING_PROOF`, `READY`, `HELD` (changed proof,
Source, scope or recipient, or an UNKNOWN account or custody) or `CLOSED` (a recorded Stop request for the producer, which does not prove its process ended, a closed account,
withdrawn Work or expired recipient).

Read progress through the selected detail's issued `continuity_read`. When its summary issues
`next.kind: "continue"`, one `work_delivery {action:"continue", intent_id, expected_basis}` records the handoff
under the original producer, submits the approved review request once with the actual dispatcher recorded
separately, and continues through the existing delivery recovery. A changed basis refuses with the current
readiness. Repeating Continue for the same intent returns the same handoff and event, so a lost acknowledgement
is reconciled by reading the issued outcome, not by composing a new request. An error reply that carries no
owner no-effect receipt is treated the same way: the original stays UNKNOWN until its outcome is read. The review, the original-parent
synthesis and any delivery keep their own records. Work owns judgement phases, Source owns exact production
provenance and Writing owns the actual requests, turns and processes.

A reviewer records its phase with `work_review {id, phase, request_id, expected_work_revision, ...}` from the
owner's issued template, after its preflight: summary at most 2000 characters, `object.aggregate` at most 200,
at most 20 findings of `{id, summary}`, and pins omitted or exactly the handoff pins. A proposed verdict is not a
recorded phase, and an original HOLD stays a real judgement. Until this route is adopted, proof that arrives
after its producer has ended is consumed by one same-original-parent completion turn under the same account.
That bootstrap limitation is recorded as such; it is not evidence that the new continuation works.

### How the native workflow view presents this route

An authored Synthesis step corresponds to this implicit `parent-consumes` synthesis. The execution preview reports it with `execution_location: original-parent`, and the workflow view says that it runs in the original parent conversation under that conversation's admitted model, settings and authority. A model chosen on the step is retained in the draft but is not applied to the parent. Reviewers are admitted children that receive the exact handoff they judge, with project context, so the view does not describe them as blind. Cancelling child work remains the separate guarded dispatch cancellation described above. When **Open run detail** names an app-dispatch run rather than a research run, the observed flow shows that run read-only: the original-parent synthesis standing, its recorded uses and observed flow, each child's exact response read and what Cancel dispatched work means. Cancelling stays on the run's Work view. A selected-turn Stop, a comment-route cancellation and a Source Stop remain separate controls, and none is offered there. A run-level Stop (`workflow-stop-run`) gates further admission and then stops each owned child through its own owner. The accepted owner issues it on the research run view, and the app mounts it on that run's **Plan & run** and after **Open run detail** in its observed flow. It is shown as stopped only when the reply names the same Work, project and request, admission is gated and every requested child is observed settled. Before sending, the exact original request and its owner-issued read are saved in the research-workbench recovery and read back, or nothing is sent. The record survives remounts, Refresh and reload (a reloaded request still awaiting its reply is unknown) and is never resent automatically. **Check original Stop request** must name the same project, Work and request. Unknown or unmatched answers keep it held, while `RECORDED` or `NONE` (no record at that read, not proof of no effect) permit one explicit **Resend original Stop unchanged**, which the owner treats as the same request. A new Stop needs a newly issued request identity, and a late reply never overwrites a newer request. Original-parent synthesis publication (`workflow-synthesis`) remains a native action of the original parent turn and has no app button. The conversation's own Stop still ends only the parent turn.

## Historical exact-text carrier

The local carrier compiles exact node reconstructions through
`laplace.pipeline.dispatch.compile_dispatch`, runs fresh `codex exec` contexts,
and banks their exact returns in `contract/dispatches.jsonl`. It requires no
Fabric seat, watcher, lease, MCP server or fixed set of persistent agents.
The supplied graph has three roles; a graph can contain several builders and
adversaries. Every builder must be reviewed and the final synthesis consumes
every preceding role's exact receipt, including failures.

Run from the checkout whose source and artifacts are being worked on. The
selected runtime belongs to Laplace; the shared Python installation supplies
packages only. First inspect a graph without running a model:

```sh
scripts/laplace-python scripts/workflow.py plan profiles/workflows/build-review-synthesize.json
scripts/laplace-python scripts/workflow.py list
```

An explicit read-only task:

```sh
scripts/laplace-python scripts/workflow.py run profiles/workflows/build-review-synthesize.json \
  --node src/laplace/representation/custody_mode.py \
  --goal 'Assess whether the OFF diagnostic can activate a watcher; independently verify the claim.' \
  --model gpt-6-luna --effort low --state /home/phujck/.mcp-gerard/laplace
```

Routine reconstruction uses the local CLI and needs no model call. When a reader
needs interpretation, use the provider's inexpensive model at low effort and pass
only the bounded reconstruction. Escalate difficult judgement or synthesis as
needed. Do not launch a full coding session for every node or substitute a fixed
provider model tier for the actual task. Record model, effort and token usage.

The model name is an explicit executor choice, not a claim that a Claude model
tier maps to a Codex model. Each receipt keeps the original authored policy,
the compiler's model stamp, and actual provider/model/effort separately.
Per-stage `executor` model/effort overrides are supported; currently the only
implemented carrier is `codex-cli`. No host configuration is written.

Write useful outputs directly into the project and name their paths in the return.
`--output relative/path` optionally identifies expected artifacts; the older
`--builder-write` spelling remains an alias. These are navigation hints, not a
permission list. The carrier records observed changed paths and their resulting
hashes, including newly produced evidence, and passes those references to review.
Concurrent edits may be included in that observation. Independent reviewers may
write their own findings while preserving the builder result they judge.

Every stage starts with the reconstructed source and task, and receives only
the dependency evidence named by the graph. The adversary must make its own
successful command observation before an acceptance can be admitted. Exact
provider thread IDs must differ. A successful model process alone is not an
accepted judgement; malformed, missing, nonzero or context-ambiguous returns
remain failures. Synthesis cannot accept a failed or contested dependency.

The runner prints its run directory before dispatch. `--stop-after build`
pauses between stages to check recovery. From a fresh process:

```sh
scripts/laplace-python scripts/workflow.py status evidence/WORKFLOWS/WORKFLOW-...
scripts/laplace-python scripts/workflow.py resume evidence/WORKFLOWS/WORKFLOW-...
```

`status` performs no model call or repair. `resume` reuses a completed stage
only after verifying its banked receipt, exact return, dependency digests and
the latest declared artifact bytes. Changed artifacts or interrupted writers
refuse automatic replay. Inspect the retained effects, reconcile them, and
start a new explicit run when needed. One run-local lock excludes competing
runners; it claims no repository-wide authority.

Packet handoffs use the current versioned files in `profiles/workflows/`.
`packet-return/2` distinguishes `COMPLETE`, `INCOMPLETE`, `BLOCKED`,
`INTERRUPTED` and `DEMONSTRATED-IMPOSSIBILITY`. A fixable implementation gap,
missing dependency or provider quota interruption belongs to the noncomplete
states, with concrete `remaining_work` and a `continuation` naming retained
path/sha256 handles, the next action and its resume condition. Those states
never certify the parent task complete, even when a judge accepts a subset.
The original `/1` profile files and receipts remain unchanged and readable.

An authored return is distinct from a provider stopping. If quota or termination
prevents an authored return, the existing execution receipt and retained effects
remain the evidence; no synthetic completion is produced. Recover the exact
artifacts, check their current bytes, reconcile partial effects and explicitly
continue the task. A continuation can replace its return in the same wave; the
banker appends a correction under the existing run identity and preserves the
old exact deposit. Neither a return nor a handoff authorizes replay, scheduling,
another provider call or an automatic stop/retry rule.

`source.kind` is `git` for an actual checkpoint, or `artifacts` for exact source
pins. The artifact alternative supports manuscript/research packets and downloaded
container workspaces with no `.git`; it invents no commit IDs. A noncomplete Git
packet can record null checkpoint IDs while retaining exact patch/artifact handles.
`output` is an exact path/sha256 pin, so changing the result invalidates current
acceptance even when the return file remains unchanged. Source roots and review
paths are provenance only; each consumer bounds reads to its actual declared scope.

### Qualified repository pins

An input or source pin may name a file the packet read through the repository
owner rather than through the project: `{"repository": "<id>", "path": "<path
inside that repository>", "sha256": ...}`, with the id from `repository
{action: "list"}`. The return validator admits exactly what that owner admits
(`writing_sources.qualified_file`: a configured, available repository, no escape or
symlink out of it, a regular file) and then checks the bytes against the pin, so
a pin taken from a `repository.read` result is accepted as written. An unqualified
input path keeps its meaning: project artifact, then manuscript source, then the
one configured repository whose workspace route owns it (the contract's
"absolute or repository-relative" input); outside all of those it is refused as
before. `output` stays a project artifact: a repository-qualified output is
refused. A return refused only for this reason is revalidated in place on the next
`dispatch_status` read; the reading is not replayed and the return file is not
rewritten. Callers whose own scope admits no repository (a resolver without a
`repository` parameter) refuse a qualified pin by name instead of guessing.

`packet-judgement/2` pins the worker return and output, using an actual Git target
or artifact target. Its review context can be an independent checkout or the
actual independent read-only review session; a whole checkout copy is optional.
An accepted judgement requires a current `COMPLETE` worker, matching output pins,
no deficiencies and successful independent observations. Command observations
carry their actual exit codes. Owner-read observations carry the existing `READ-`
receipt ID, operation/payload and owner-result digest from the actual reviewer
turn/session; a self-claimed successful read is insufficient. Receipt metadata
is attached after the consulted result is digested, avoiding a self-referential hash.

The `/2` scripted check is a real command or a receipt-bound owner read, with
`PASSED`, `FAILED`, `INTERRUPTED` or `NOT_RUN` execution state. A read does not
invent command exit zero. An unrun check can retain the intended check and null
observed execution fields. Packet plans may explicitly require a Git checkpoint
or command check with `requires_git_checkpoint` and `requires_command_check`.
An existing executable `check`/`check_template` remains a command obligation;
omitting or setting a flag false never weakens it. New briefs/launch arguments
derive their schema and these obligations from the same owners. Historical plans
do not acquire a Git requirement from file extensions or natural-language guesses.

Evidence under the run directory contains an immutable specification, schema,
source/prompt hashes, stage receipts, bounded provider observations, exact
returns and final result. Prompts are generated in memory and sent on stdin;
no prompt files or full transcripts are written. Compilation uses its existing
telemetry, scoped to the explicit state directory. The carrier neither installs
a sandbox shim nor infers a writable HOME/live state. All stages use normal trusted host execution, as requested by the author;
`--state` binds the intended state, not an OS access boundary. Pure orchestration
does not probe GPUs; algebra, embeddings and upfold retain their own measured
GPU/runtime requirements.

For a stage that will actually perform algebra, embedding or upfold, request
`--gpu-stage build` (repeat for other exact stage IDs), or set `require_gpu: true`
on that stage in its JSON specification. Unknown stage IDs refuse. The request
is stored in the immutable run manifest and applies on resume.

All stages run in **trusted host mode** (`danger-full-access`), with the user's
filesystem and network access. The tested Linux workspace sandbox did not expose
working CUDA. This carrier uses no device shim or global permission change.
`LAPLACE_REQUIRE_GPU=1` forbids CPU fallback; conflicting opt-outs refuse.
Reviewers can deposit their own evidence in the project.

Provider evidence records the effective execution mode; a real operation
establishes GPU execution. `codex_sandbox_profile(context)` provides matching
execution/probe arguments and the checkout/state environment.

`accepted: true` means only that this defined role graph completed with
supporting review and consumed results. It does not mean author acceptance,
publication, or independent cold recovery of the whole engine. Keep meaningful
counterexamples and returned residuals alongside the result.

The historical Claude JavaScript workflows remain available as source/design
evidence. Their native DSL, manuscript release pipeline and sealed visual
reader isolation are not ported by this small carrier. The first supported
scope is bounded exact text-file work with the existing `derive` compiler.

### Cumulative Source review subject (closure contract, 2026-11-02)

A Source review used to be planned from one candidate. When a commission had already committed earlier effects, the request listed only the latest candidate as the "complete inventory" and showed an empty change list for every other file. A reviewer reading that request could not tell what the commission had actually produced.

The Source owner now derives one review subject from the same qualified basis (`development_source.review_subject`, schema `laplace.development-review-subject/1`). It contains:

- every COMMITTED effect of the commission, across grants reissued on the same configured checkout, base and commission request id
- for each changed path, the exact effect chain, the retained raw preimage, the current postimage and line hunks derived from preimage to postimage. Earlier candidate offsets are never replayed. An unknown baseline, a broken chain or an oversized file is named as such (`UNKNOWN_BASELINE`, `CHAIN_DISCONTINUOUS`, `EXCEEDS_GEOMETRY_CEILING`)
- an optional read-only carry manifest, admitted separately through the handoff field `source_subject.carry` (an inline manifest or a pinned project Artifact). Each member must be current. A member the commission changed must equal that change's retained preimage or its current postimage, so a stale or foreign cut refuses. Any other member is compared with the base tree: `UNCHANGED_CARRY` only when it is the base blob, otherwise `CHANGED_SINCE_BASE`, `ADDED_SINCE_BASE` or `BASE_UNKNOWN`. A matching pin proves only that the member has not drifted since it was pinned. The carry never becomes write authority, a check input or acceptance by inclusion
- optional explicitly selected prior production, `source_subject.prior: {grants: [...]}`: earlier grants of the same Work, repository, checkout, base and original parent session that belong to separately attributed commissions. Their committed effects and change chains join the subject with their own attribution (`prior_production`); their accounts, write fences and recorded reviews stay separate. Own, foreign, conflicting or empty ancestry refuses. An optional `source_subject.accepted_base` names the readable commit that change provenance is judged against (default: the grant base). Every changed path records `base_relation`: `PREIMAGE_AT_BASE`, `CREATED_BY_SUBJECT`, `CHANGED_BEFORE_SUBJECT` (production outside the subject changed it after the base) or `BASE_UNKNOWN`
- an optional typed stage, `source_subject.stage {id, pre_source_review[], post_adoption[], authority[], summary}`, which separates what this review judges now from obligations that stay open after adoption
- the latest candidate and effect as `latest_delta`. This is the exact anchor and nothing more

Reading plans that carry a subject use schema `laplace.development-review-plan/2`. Version 1 plans keep their original latest-candidate meaning. The consumed inputs are still at most 64 obligation pins, a local projection of the subject. Delivery binds the subject id and the handoff brief into its content pin and rechecks subject currentness before transport. The reviewer request shows the whole subject, the stage criteria, the bounded handoff summary and the evidence handles before any geometry, and labels the latest candidate as the latest delta only. The complete rendered request has a 64 KiB ceiling. Above it, the purpose, question, subject identity, stage, brief and evidence stay upfront, and each list (change inventory, carry members, compact consumed inputs, initial reads) shows the prefix that fits, its omitted count and the exact continuation page: the Work view `continuity` part `subject` (`{phase_id, section, offset}`, plus `path` for one file's hunks and `obligation_id` for input projections). Pages return the recorded rows in order, byte-bounded. Omitted rows remain review scope, and a request that still cannot fit is refused with nothing sent. `COMPLETE` still means structural coverage. It does not mean the reviewer has read anything or accepted it.

### Approved proposal writer and human Apply

An independent-review recipient stays read-only. Its `propose_revision` is refused, and the route test keeps that refusal as an adverse control. A route that should produce a manuscript proposal names a proposal-writer binding approved by the human through `work_delivery {action:"workflow-bind", effect:"proposal-writer", kind:"app-owned", expected_work_revision, request_id, provider, model, effort, lifetime_s}`. Ordinary `bind` refuses effect bindings. The writer is admitted as an author turn in `revise` mode, with the origin-derived effect selection and the route, edge and turn provenance. The human then applies the exact saved version through `POST /authoring/apply`. The revision join reports `NOT_BUILT` until a build of exactly those bytes is recorded, and `BUILT` after. Applying a stale sibling proposal is refused and changes no bytes.

In the browser, deciding a proposal from "Review responses" is an explicit capability (`decision:true`), separate from inspecting it. Each caller reaches the decision differently:

- From project Review in the workspace shell, the decision goes to the canonical project Review controller (`createProjectReview.open`, then `mountProposalReview`), which owns drafts, permission, the decision and Apply.
- From the writing panel inside the manuscript frame (the correction history), the panel sends one `laplace:review-proposal` request through the validated walk bridge (same origin, current manuscript frame only). The shell's `createProposalDecisionHandler` hands it to that same controller and answers with exactly one result. A refusal, such as unsaved drafts, permission or a stale or foreign read handle, comes back to the responses dialog, which stays open.
- The panel's own saved-comparison cards, and every open that does not carry `decision:true`, remain read-only inspections.
- The Work tab's responses decide through the same controller: the shell gives the Work view its `projectReview` service, and `workspace-work-view.mjs` passes `mountOperatorWork({openProposal})`. Nested read-only Work mounts still only inspect.
- The selected-passage comment (`writing-panel` `commentFrom` → `openFeedbackComment`) carries the same capability into both the fresh and the existing-comment Review responses.
- An opening counts only if `mountProposalReview` reports that it showed the decision view for exactly the requested project, turn and version (`proposalDecisionOutcome`). A manuscript that did not open, a superseded review, another version or a read-only showing is a refusal with its reason. The responses dialog, and a passage comment dialog that opened it, close only after an actual opening, judged by their own lifetimes; on a refusal they stay. Opening never posts. Only the human decision in the canonical view sends `/authoring/proposal-decision` with the identities that were read.

### Prepared completion with the same subject

A producer that arms a prepared completion (`development_source {action:"arm"}`) may add `source_context` and `source_subject`. Arming then uses the same commission collector, plan, subject, stage and read-only carry as an ordinary cumulative handoff, and refuses an incomplete reading offer. Readiness rechecks the subject's currentness (`SOURCE_SUBJECT_<status>`) and counts commission effects across reissued grants. The one prepared handoff carries the armed plan unchanged, and the delivery event keeps it. An intent armed without these fields keeps its earlier meaning: its effects are grant-only and its handoff records explicitly that it has no reading plan.

The tests that exercise this route use a deterministic provider stub and a recorded compiler status boundary. They are not a paid app-agent run, a real browser session or a compiler build. Those, along with the ordinary app Source check after adoption, remain later acceptance obligations.

## Current practice: one grammar, two launchers (law: `procedure/dispatch-distil-first`)

One fact, one holder, two launchers. A dispatch names a provider-neutral intelligence **tier**
and an **effort** (`STANDING_LAW.md:46`); a tier becomes a model in exactly one place,
`laplace.pipeline.schema.TIERS`, whose Claude column is `MODEL_RANK` read as tiers and whose
Codex column is the ids Codex root chose for itself. `WORKER_MODEL` is that table's Claude
projection, not a second table. A packet's **return** and **judgement** are separate versioned families.
Their exact supported `$id` values are registered by `pipeline.workflow.packet_schemas`
from `profiles/workflows/*.schema.json`. The current selection is version2; the immutable
`packet-return.schema.json` and `packet-judgement.schema.json` version1 profiles remain
supported for historical returns, with their original coverage qualification. The
current version2 profiles add strict artifact/currentness and exact review coverage;
legacy version1 acceptance does not acquire that authority by being read today. The worker WRITES its return to the path its brief names in
section 0 and checks it itself; the harness envelope carries only that path and one line, so
the exact return is a file with a sha256 rather than a paraphrase in a transcript.

```sh
scripts/laplace-python scripts/distil.py preflight   <plan>                      # prints exactly what goes into each worker; writes the one-use PASS marker
scripts/laplace-python scripts/distil.py launch-args <plan>                      # the args a Claude Workflow launch passes: models from the tier table, both schemas from their files
scripts/laplace-python scripts/distil.py spawn-args  <plan> <label> --role build # the collaboration.spawn_agent arguments Codex root uses (fork_turns none, model from the codex column)
scripts/laplace-python scripts/distil.py brief       <plan> <label> --role build # what that worker reads first; section 0 names its return_path and return_schema
scripts/laplace-python scripts/distil.py check-return <return file>              # the worker's own gate before it returns
scripts/laplace-python scripts/distil.py watch       <plan> --run-dir <run dir>  # right after launch, in the background, no model: rows as each packet returns
scripts/laplace-python scripts/distil.py cost        <run dir>                   # after the wave: turns, contexts, flow
scripts/laplace-python scripts/distil.py wave-rows   --from-dir <out dir> --wave <w>   # the wave's rows when the returns are files and there is no run journal
```

Code checks must select their actual Python package and entrypoint, for example
`scripts/laplace-python scripts/distil.py reachable --package src/laplace --root src/laplace/web/writing_server.py src/laplace/work/project_work.py`.
This checks static imports only; process launches, HTTP behavior and frontend modules need
their own execution evidence. Requested files outside the selected package fail the check;
they are never counted as reachable. Separate entrances need separate checks.

`distil.py stage-receipt <stage> --from-wave <w1> --from-wave <w2>` is the historical
Atlas programme receipt: it reads Atlas wave plans/rulings and checks Atlas's front door.
It does not certify other campaigns. Their typed returns and explicit integration review
must establish acceptance against the current parent contract.

**The Claude launcher** is `.claude/workflows/atlas-wave.js` for every campaign, launched with
`scriptPath` (saved workflows and agent types are read at session start; a launch by name runs
the session's stale copy). It carries no model literal and no schema literal: it reads
`args.models[label][role]` and `args.schemas.return` / `args.schemas.judgement` from
`launch-args`. **The Codex launcher** is Codex root's own `collaboration.spawn_agent`, whose
arguments come from `spawn-args` — the same plan, the same brief command, the same return
schema, only the provider column of the tier table differs.

The **Claude launch sequence** is four commands and holds nothing of its own:
`preflight <plan>` (it prints the per-packet estimate for the author and writes the one-use PASS
marker the launch hook demands), `launch-args <plan>`, then
`Workflow(scriptPath=".claude/workflows/atlas-wave.js", args=<that JSON>)`, then
`watch <plan> --run-dir <run dir>` in the background so rows bank as packets return. A launch by
workflow NAME runs the session's cached copy, so it is always launched by `scriptPath`.
The three campaign wave launchers beside it — `.claude/workflows/writing-campaign-wave.js`,
`writing-friction-wave.js` and `writing-reconciliation-wave.js`, all three untracked, each with its
own hardcoded model and its own three inline schemas — are **retired** together: everything they had
and `atlas-wave.js` lacked is now read from the launch arguments — stages with a barrier each (`args.stages`), a packet
fed by named earlier packets (`args.agents[].feeds`), a per-packet worktree (the brief's own rule,
`scripts/sparse_worktree.sh`), and a restart that is a fresh run fed from banked returns
(`args.prior`, `args.start_stage`) — while their hardcoded models and their inline schemas are
exactly what `launch-args` resolves. There is no third launcher and no generic one. The seven other
`.js` launchers tracked in that directory are the historical ORGAN launchers of the loop runners, a
different grammar: three (`f-loop-integration.js`, `pipeline-chain-integration.js`, `weld-cwave3.js`)
carry `model: 'opus'` inline, which the audit's `_LITERAL` ceiling-checks (`scripts/audit_dispatch_models.py:84`);
all seven bind `const BOOTSTRAP_MODEL = 'haiku'`, which its `_BOOTSTRAP` checks (`scripts/audit_dispatch_models.py:90`).
The `const MODEL = {tier: name}` binding this packet deleted was seen by neither pattern, and the grammar's own
test now holds that fact (`tests/test_dispatch_grammar.py`). They are not wave launchers and S0 does not touch them.

Both have the same three roles as the carrier above and the same rule: each role is built from
the exact return of the one before, and a wave is built on the synthesis of the wave before it
(`builds_on` in the plan). Every worker's first act is the `brief` command: the engine wake,
the reconstruction of the node it serves, the charter keys it needs, the organs that already
exist, what its wave builds on, an index of its inputs, and its return path and schema. What a
worker is given is decided there, by script, and measured; there are no hand-set size, count or
budget caps. A PreToolUse hook refuses a Workflow launch without a fresh preflight PASS.

A wave is recorded in the engine's rows: `watch` banks each packet's dispatch and verdict rows
as they return, with the workflow row `PENDING`; the wave's last phase banks the final rows
(`wave-returns`, then `wave-rows`, or `wave-rows --from-dir` when the returns are files), and
`scripts/laplace-python scripts/workflow.py list` and the wake's campaign head read them. Each
dispatch row discloses what ran — `packet_model_stamp` derived from the plan's tier, plus
`executor`, `codex_model` and `sandbox` — which is what `scripts/audit_dispatch_models.py`
reads; with no plan in hand those fields are omitted rather than invented, and the audit then
says so. The workflow row's `programme` is the plan's own. A packet's standing is its last
verdict. After two judgement rounds the orchestrator rules and records `orchestrator_rulings`
in the packet's report. Wave evidence lives under the plan's `out_dir`
(`evidence/ATLAS_PROGRAMME/waves/<wave>/` for Atlas waves).

`src/laplace/pipeline/workflow.py` is **retained as the historical exact-text carrier**: the
provider-executed, three-role carrier described earlier on this page, with its own
`RETURN_SCHEMA` for bounded exact text-file work through the `derive` compiler. It has not run
since 2026-09-29. It is not the grammar above and is not a second launcher — new waves go
through `launch-args` or `spawn-args`.
