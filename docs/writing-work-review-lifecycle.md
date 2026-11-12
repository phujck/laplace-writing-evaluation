# Work review lifecycle

How a Work item moves from an implementation handoff, through scoped reviews and a synthesis, to linked follow-up Work,
and why required reviews must be current and independent when that obligation requires it. Written 2026-10-16 for
`WORK-editor-work-review-lifecycle-20261015` (M5). It describes this source tree, not acceptance evidence.

For ordinary use, open **Tasks**, choose a task and read **What led here** or
**Inspect review outcomes**. A historical completion may remain Done while its
current evidence needs review; this is different from an unmet review question.
Approval permits a future action; it is not an accepted judgement. Not every
Task is review-managed, and a handoff or synthesis never closes one by itself.
Use [the task recipes](writing-tasks.md) for setup and guarded completion, and
[Task outcomes](writing-evidence-navigation.md) for availability and result links.

## Owners

| Concern | Owner |
|---|---|
| Phase rows, actors, independence, the review facet, currentness, completion gate | `src/laplace/work/project_work_review.py` (a section of the `project_work` owner) |
| Durable truth | the same Work ledger, `corpus_friction/work_orders.jsonl`: rows `record: project-work-phase`, `kind: work-phase`, appended by `project_work._append` under `project_work.dispatch_lock` |
| Folding phases into a Work | `project_work._merge_task` (a per-Work `phases` list; never merged into the specification) |
| Facet on every read | `project_work._resolved_tasks` attaches `review` to review-managed Work |
| Completion gate | `project_work._transition`: `done` refuses with `project_work_review.completion_problem` |
| Views and actions | `project_work_views`: `FULL_KEYS` carries `review_obligations`, `followup_origin`, `review`; LIST rows get a compact `review` (counts only, managed rows only); `_actions` issues `work_review` (phases by role, guard, `POST /work/review`) and drops `done` while required obligations remain |
| Native door | `writing_tools` operation `work_review` (`record task@evidence`, declared in `identity_doors` beside its owner); review mode may record `review` and `followup` only |
| HTTP door | `project_work_surface`: `POST /work/review` (the author is the recording identity) |
| One admission | `project_work_review.record` calls `writing_declarations.validate_owner_payload('work_review', ...)`, so native, HTTP and any direct caller refuse the same shapes before a lock or a row |
| Frontend | `static_shared/workspace-work-review.mjs` `workReviewSection` (`reviewLifecycle` / `phaseRecorder`, control `work:review`), mounted by `workspace-work.mjs` on the controller's own closures |
| Phase definitions and preparation | `project_work_review.PHASE_SPEC` (payload fields, owner-filled basis, authored inputs, title, consequence) drives `PHASE_FIELDS` (the schema), `role_phases` (what a role may record; `_record` enforces it) and `preparation` (carried on `allowed_actions.work_review.preparation`, rendered by `workspace-work-review.mjs`, read by native callers); the follow-up phase carries `followup_composition()` and the pending-join recovery requests |

## Opt-in

In Writing, choose **Set up reviews** from the selected Work or its passage-comment
review controls. The [comment review guide](writing-workflow-editor.md#request-reviews-of-a-passage-comment)
describes question setup, reviewer approval, renewal and return to the comment.

Work becomes review-managed when its specification has `review_obligations`, authored through the existing guarded `task`
edit (`project_work_review.obligations` validates them). An obligation has an `id`, a `scope` (source, owner-native-http,
human-desktop, human-narrow, live, guide, closure, other), a `label`, `required` and `independent` (both default true) and
`inputs` (repository paths its review consumes). Work without the field keeps its hashes, its LIST bytes and its completion
meaning: `_task_revision` includes the lifecycle fields only when present.

## Phases

One request per phase: `request_id` (8-96 characters) is the client's stable id, so the phase id is
`PHASE-<digest(project, work, phase, request_id)>` and a replay is `REUSED`, never a second row. The declared schema's
`oneOf` states each phase's own fields; another phase's field is refused.

- **handoff**: the object (kind, profile, repository, base, checkpoint, aggregate), exact per-file `pins`
  (`{path: sha256:<hex>}`, each equal to the file's bytes now) and public evidence. It satisfies no obligation and launches
  nothing.
- **review**: one disposition (ACCEPT, HOLD, REJECT) of one obligation that its handoff covers, with findings. Reviewed
  pins default to the handoff pins the obligation consumes; a pin that differs from the handoff is refused
  (`CHANGED_INPUT`). A review with only an aggregate and no pins is `coarse` and never CURRENT.
- **synthesis**: consumes exact handoff and review ids of this Work. It does not complete the Work.
- **followup**: creates or reuses ONE child per (parent, finding) through the existing task owner (the child's
  `followup_origin` is minted only here; a payload cannot author it), then joins it by its closure: `optional`
  (membership), `required` (a `closure` obligation on the parent, satisfied when the child is done) or `prerequisite`
  (parent `depends_on`). A join that fails is recorded `PENDING_JOIN` with the exact child; the facet issues the exact
  recovery request (`pending_joins[].recover`) and the same request completes it (`RECOVERED`).

## The follow-up as one compound action

The follow-up is the Work owner's worked example of a compound transition, and it is described once, beside its
primitives: `project_work_review.followup_composition()` names the admission (`_record`), the canonical request
(`_followup_request`), the steps (`project_work._append` PENDING, `project_work._task` child guarded by `_refuse_drift`,
`_join`, `project_work._append` COMPLETE), the shared effects used by the first request and every recovery
(`_followup_effects`), the closures, guards, recovery, evidence and authority. The Work detail's `action_context`
carries it on `allowed_actions.work_review.preparation.phases.followup`, so the native reader and the follow-up form
(`workspace-work-review.mjs`, "What this records, step by step") unfold the same declaration; `tests/test_work_navigation.py` traces the owner's
calls against the declared steps, so the description cannot drift from the execution. It executes nothing and is not
a workflow language: the domain conditions (closure semantics, permission, currentness) stay in this owner.

The same descriptor shape describes every Work grade (campaign, branch, task); the module text of
`project_work_navigation.py` is its contract.

## Actors and independence

The recording identity comes from the door, never from a label:

- native: the admitted writing turn of this project; its session is the identity (provider:model, turn and any dispatch
  lineage are recorded beside it);
- external: an attested name with pinned public evidence (path and sha256), attested by the admitting door;
- human: `author` at the HTTP door.

A payload `actor` may carry a role, or an external name with evidence; a native or human name claimed by label is refused.
`independence(reviewer, producer)` is INDEPENDENT when both identities are proved and differ, SELF when they are the same
(the same session; a self-assessment never satisfies an independent obligation) and UNKNOWN when either is unproved.

## Currentness

On every read each obligation's latest review is compared with now: a changed reviewed pin makes only the obligations whose
reviews consumed it STALE; a revised obligation definition (its digest) makes only that obligation STALE; recorded
verdicts stay as history. An obligation is satisfied when its latest review is ACCEPT, CURRENT and, when required,
INDEPENDENT. `remaining` lists the required obligations not satisfied; `next` is the owner's one next step
(recover-join, handoff, review, synthesis, closure, complete).

## Bounds

The Work budgets are unchanged (LIST row 1,300 B, summary 30,000 B, detail 50,000 B, graph 30,000 B, 12/20-row pages).
LIST rows carry four counts; phase bodies are not inlined in the detail read (`phases` is not a public key). The default
help total stays under its held cap: the input inline limit moved from 900 to 600 characters (ten schemas now serve their
summary plus an exact `input` section), which admits this door without raising the cap.

## Tests

`tests/test_work_review_lifecycle.py` (WL-T1..T5: doors, identities, gating, follow-ups, currentness, legacy and bytes),
`tests/test_work_navigation.py` (the composition trace, navigation, descriptor, qualified activity and the observer token),
`tests/work_navigation_frontend.test.mjs` (the follow-up form's owner composition, navigator, relationships, observer),
`tests/test_work_repair1.py` (one disposition decision, phase preparation and recovery, references and history, observation scope and
event identity, page bounds), with `tests/helpers/work_preparation.mjs` giving hand-built frontend fixtures the owner's real preparation,
`tests/work_review_frontend.test.mjs` (WL-T6: the surface, allowed phases, stable retry, owner-issued recovery, read-only),
and the Work suites `tests/test_project_work_views.py`, `tests/workspace_work.test.mjs`.

### Reviewing a configured development checkout

A handoff may explicitly select `source_basis: {grant_id, candidate_id}` from
the existing development Source owner, alongside exact relative-path `pins`. The
owner must admit the actual holder and a completed candidate effect; the handoff
pins every input of the obligations it covers and every candidate postimage.
`object.repository` remains a display label and does not select a filesystem.

The review inherits the recorded Source identity and consumes the exact pin
subset of its obligation. Currentness follows that configured checkout, never
files with the same names in the canonical repository. Unrelated guide drift
does not stale a source-only review. Changed bytes or configuration remain stale;
unavailable source remains unknown. An expired write grant does not erase
completed evidence or make it writable again. Admission of a new review still
requires the actual original holder/delegate, admitted evaluator or human door.
Legacy handoffs without `source_basis` keep their canonical-root pin meaning.

### Suggested reading for a qualified Source handoff

A handoff with `source_basis` may also offer
`source_context: {windows: [{path, line_start, line_end}]}`. Lines are inclusive,
1-based positions in the exact pinned postimage. The Source owner computes and
retains one immutable `source_review_plan`; a replay keeps that original plan
and authored context. A different offer needs a new deliberate handoff request.
This option belongs only to handoff, and it does not change legacy handoffs.

Open **Handoff details → Inspect the handoff record → Suggested review reading**
to see changed files, required inputs, offered excerpts and missing context.
**Read …** opens an existing pinned source reader. Each initial excerpt has an
exact character start and exclusive stop offset; reaching that stop is enough
for the offered excerpt even if the reader offers another page. Further reading
is a deliberate expansion when needed to judge a dependency. Exact pins, plan
identity, change spans and uninspected ranges remain available in details.

`COMPLETE` means structural representation of the offered changes and inputs.
It does not mean that a person or agent read them, considered every dependency,
or completed an independent review. A delivery selects only its obligation's
consumed inputs from the retained plan. Missing context for an unrelated guide
cannot block a complete source-only selection; missing or unavailable context
for a selected input is retained as a refusal before reviewer transport, without
silently substituting a full-file walk. The event, recovery and existing result
reads retain the same plan identity. Source effect, read observations, review
acceptance and adoption remain separate. This reading offer implements no call
budget or automatic execution.

### Optional Source commission allowance

An author may select an existing human-issued, opted-in Source grant with
`source_grant_id` on the ordinary turn request. It must name the exact registered
project, inspected Work and already-existing original author session. The owner
resolves the trusted execution attachment; a caller cannot supply that attachment,
policy, counters, deadline or parent identity. Dispatched/reviewer turns cannot
attach themselves through this selector. Ordinary unbound work is unchanged;
copying an opted-in grant's text into an unbound native turn neither attaches
a commission nor grants new write authority.

The admitted task context includes one owner-derived **admission-time snapshot**:
remaining admitted native calls, app admissions, sessions and the exact deadline.
It is separate from the operating kernel and from Source write authority. Current
standing arrives in native result envelopes and existing owner reads. Recovering
an already-admitted request returns its original turn and snapshot; it does not
recompute a prompt or start another provider turn.

The immutable commission policy limits admitted native invocations, app
admissions, distinct session reservations and wall seconds. A permitted incoming
native invocation spends its slot before argument validation, including a
refused/invalid call. Internal reentry and failure handling retain that same
private invocation; a later incoming call spends a new slot even if its RPC ID
or payload repeats. This is not a strict raw-transport-attempt, token or currency
limit. A grant reissue cannot reset the original commission account.

A qualified Work delivery inherits that same commission only after exact Source
basis/evaluator and current reviewer-approval checks. It reserves reviewer
session capacity before creating the session; lost acknowledgements recover the
same indexed session/turn. Unknown creation is not permission to create another.
The original-parent continuation reconciles an existing admission first, then
requires remaining allowance and current standing for a new admission. The
worker's complete result and review acceptance remain inspectable even when a
new parent admission is refused. Count changes do not change Source pins or
material Work guards. Attached execution can create app work only through these
qualified evaluator and original-parent routes. Generic dispatch and other
unsupported child/session routes refuse before creation or effect reservation;
they cannot silently become unbound work.

When the allowance drains, new native and app/parent admissions stop. Admitted
calls may settle within existing operation supervision and the finite commission
deadline. The turn owner interrupts the actual provider and registered owned
children, preserving partial output and receipts. It cannot safely cancel an
arbitrary in-process Python owner thread: unresolved claims/effects stay spent
or unknown, and their eventual receipts remain reconcilable. Stopping is not a
claim that those effects ceased or rolled back.

Native exhaustion drains the **shared account**: an idle participant cannot stop
a peer's admitted response while it is still being delivered. The governor and
finalizer use the owner's current shared standing; `active_for_turn` describes
only one participant. Once all admitted responses have settled, the exhausted
account stops further work. Its wall deadline, explicit account Stop and unknown
custody still take precedence.

The author's existing selected-turn **Stop** remains local for both parent and
reviewer. A local interrupt/finalization flag does not cancel the commission.
The original Work delivery still refuses automatic continuation of a stopped
parent under that old route; recorded reviewer results remain available. An
opted-in Source handoff cannot become an unbound delivery through a human or
unattached native submission: new delivery needs its trusted original commission
parent. Absent-policy legacy handoffs and exact admitted recovery are unchanged.

Work delivery checks the **recorded original turn and parent**, even when an old
pending event has no `source_basis` or execution field. A Source-bound ordinary
handoff is refused before a new event can be saved. Human recovery cannot turn
an already-retained pending Source-origin event into a legacy reviewer or parent
admission. One shared origin check applies at each new-admission boundary.
Existing admitted reviewer/continuation identities reconcile first without a
second launch or a new quota-coverage claim; inspection of historical effects
and genuine unbound legacy delivery remains available.

## Catalogue and planning

`project {view:"catalogue"}` and `GET /work/state?view=catalogue` read all existing
Work namespaces for the local author/trusted SDK, including those without a registered project. A native turn sees only its actual project scope; a payload cannot widen it or inspect another namespace’s planning request. Search covers the
complete recorded ID, title and purpose before paging. Lifecycle is historical
standing; currentness is current acceptance, and readiness is separate. Combine
filters to find recorded-done Work whose evidence needs review. The owner returns
qualified identities, registration facts, exact detail/hierarchy reads and a pinned
continuation. The catalogue observes no running process and reads no document body.

`row.planning_read` opens one bounded `laplace.work-planning/1` observation and its
`actions.planning`; a Work detail also offers `allowed_actions.planning`. The list
carries no write schema or original recovery form. Planning uses the existing `task` door with `action:"planning"`. Its independent guard protects
priority (higher first), order (lower first), deferral intent and authored reason.
True prerequisites come first. Legacy neutral ties retain first-specification order.
Deferral is planning, not lifecycle, execution refusal, completion or authority.
Planning records existing Work phases without changing its specification, standing
or completion identity. A namespace is never registered by inspection or planning.

Retain the exact emitted request before Save. Canonical intent includes project,
action, Work ID, both guards and literal planning values, excluding only request_id.
Stable same-ID replay returns its original durable receipt; current planning/action
is a separate observation. A stale guard is a durable terminal NOT_ADMITTED receipt;
a missing deferral reason is likewise refused without a planning effect. Follow the
issued planning-request read after an unclear result. NONE permits only explicit
same-wire retry; malformed or unavailable custody is UNKNOWN. Newer local choices
stay separate. Read current Work before a new decision, never replace an uncertain
wire by changing its guards. SDK work_catalogue/work_plan and native/HTTP compose
the same owners; existing native role and project authority remain in force.

The owner issues `active_read` for recorded unfinished/nondeferred Work and
`all_read` for the full admitted scope. The no-query catalogue still covers all
recorded Work. An unfinished group contains recorded open/ready/blocked/in-progress
items; a historical completed item with stale evidence belongs in current-review
filters instead. `suggested_next` identifies a matching READY/nondeferred candidate
in preferred order, or explicitly says NONE. It is a suggestion to inspect, not an
execution command. Human scope identity remains stable across filters so retained
planning drafts do not acquire a new target. Native continuations and preset reads
carry the actual namespace; no transport can turn that read into a wider query.
