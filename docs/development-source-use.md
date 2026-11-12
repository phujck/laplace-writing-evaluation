# Small Source changes and qualified review

Source authority still comes from one human-issued Work grant for an actual
parent session, configured separate checkout, Git base, evaluator, paths,
operations, lifetime and bounded check profiles. Discovery or a repository read
does not grant Source write authority.

`development_source.read` keeps its existing whole-source hash and small-text
result. Its `repository_read` is a callable existing repository read with that
same alias, relative path and full raw-source pin. Follow that reader's pinned
page/NEXT handles; its explicit restart observes current bytes. This reuses the
existing reading owner and gives no additional Source authority.

Each candidate file may supply either legacy `content` or compact
`edits: [{old, new}]`, alongside the exact whole-file `before_sha256`. Each old
span must be nonempty and occur exactly once in the original UTF-8 text. Spans
must not overlap; all resolve before any replacement. There are at most 64 edits
per file. Compact input and each original are bounded to 256 KiB, and the final
candidate still has the existing total 256 KiB ceiling. The owner computes and
stores full final content. Equivalent complete-content and compact submissions
produce the same candidate identity, hashes and existing apply/recovery behavior.
No shell patch, approximate matching or dynamic execution is involved.

A check profile can add `fixed_inputs: {relative_path: "sha256:…"}` for a frozen
evaluator. Grant admission requires those exact current bytes within both the
profile inputs and grant paths. Check compares the actual staged pins before
launching its profile. A changed or omitted fixed input is refused. This guards
check integrity; it does not make that path unwritable through another granted
operation. Existing isolation and resource enforcement remain unchanged.

The Work handoff consumer may select `source_basis: {grant_id, candidate_id}`.
`prepare_review_basis` verifies current holder/evaluator authority, same Work and
grant, a completed committed candidate effect, supplied covered-input pins and
every candidate postimage. Work owns coverage of the obligations selected by
that handoff. The returned detached basis retains grant/candidate/effect,
configured repository, checkout-locator digest, Git base and exact pins. It is
not a claim that similarly named files in the canonical workspace were changed.

`validate_review_basis` reinspects a canonical retained basis. Its optional
`consumed_pins` must be an identical subset; unrelated handed inputs cannot
invalidate a review that did not consume them. The original qualified source
identity must still resolve. Changed configuration/base/consumed bytes is
`CHANGED`; absent, unsafe or unreadable custody is `UNKNOWN`. Expiry of write
authority alone does not erase a completed effect or accepted historical review.
When admitting a review, the Work owner supplies the actual door: Source proves
the original holder/delegate or an actual admitted evaluator delivery session
of the original binding and revision. Passive currentness grants no authority.

Source effect, check result, independent review acceptance and Root adoption
remain separate facts. The existing native/HTTP declarations consume the owner
schemas. The qualified Work consumer and focused Source tests are named in the
owner's source-contract relations; prior reviews do not certify these new joins.

### Delivering qualified source review

Work delivery binds the exact typed Source basis into its existing event identity.
Before reserving a session it asks the Source owner to validate the named
obligation’s consumed pins and the original grant evaluator binding and revision.
Delivery still owns current approval, expiry, Work scope and transport limits. A
different approved reviewer is refused before transport. The pure Source helper
`validate_review_recipient` adds no approval or session authority.

The request names the configured repository/base and grant/candidate/effect, gives
only the consumed pinned repository reads and links the exact handoff. It does
not direct the reviewer to canonical files with matching names. Returned events,
lost-ack recovery and the original-parent continuation retain that same basis.
Recorded result standing is a snapshot; the event’s existing status read reports
current canonical review standing. Ordinary unqualified delivery is unchanged.


## Suggested review reading

A new compact candidate retains verified edit facts in the existing candidate
row: exact old/new text and before/after Unicode-character coordinates, bound to
both full raw-source hashes. These facts refer to the original pinned bytes,
including a dirty preimage; the Git base is not a substitute for that preimage.
Canonical candidate identity, complete final content and apply/recovery remain
unchanged. Replaying an existing candidate never adds or replaces edit facts.
Older and complete-content candidates remain usable, but a changed input without
these facts cannot claim a complete focused review plan.

`read` accepts `include_text: false` for only the raw pin and existing reading
navigation. Omitting it preserves the legacy text projection. This option is
refused on other actions and grants no additional permission.

An explicit typed Source handoff can offer
`source_context: {windows: [{path, line_start, line_end}]}`. Lines are inclusive
and one-based in the pinned postimage. The Source owner prepares a detached,
deterministic plan with every candidate file, exact verified edits, every covered
input, requested and coalesced windows, covered/uncovered edits, and uninspected
extents. The focused geometry capability materializes at most the existing
256 KiB candidate ceiling per input; larger or non-plain-UTF8 inputs retain their
full pins and deliberate reading navigation with an explicit unavailable reason.
Malformed windows refuse. Missing context or change facts is explicit, never an
automatic full-file fallback. Empty inputs are represented without a fictitious
line range or read, with an explicit incomplete geometry reason.

This focused plan is explicitly selected by `source_context`. If that field is
omitted, no focused plan is retained and delivery supplies legacy whole-input
pinned repository handles. The actual run inspection labels this `NOT_REQUESTED`.
That is a separate compatibility route,
not a complete focused plan or the Source owner filling in missing windows. The
actual 64-call Source-input repair omitted `source_context`; it used this legacy
reading route and does not prove focused-plan efficiency or model/token savings.
The run recorded an original-parent synthesis before allowance stop, then Root
cancelled the unclosed acknowledgement separately. No extra paid turn completed
that acknowledgement.

The existing repository reader counts Unicode characters after universal-newline
decoding. The plan converts raw edit coordinates into those units, so CRLF, CR,
Unicode and inclusive line ends remain exact. Each offered initial read has a
full raw pin, exact offset and clipped length (at most 6000 characters), plus its
extent's exclusive `stop_before_offset`. A repository `next_offset` can continue
past that extent: do not blindly follow it to EOF. Exact native repository reads
and the existing project-qualified read-only Material HTTP/human previews name
the same bytes. Further context is a deliberate pinned expansion.

`prepare_review_plan(root, project, work_id, basis, pins, source_context)` is
pure and revalidates the qualified source before constructing the offer.
`review_plan_for_inputs(plan, pins)` verifies its immutable identity and projects
only the exact consumed subset. Thus missing guide context does not block a
complete source-only plan. Work retains the complete inventory and chosen plan;
its per-obligation transport must refuse incomplete or unavailable focused input.
`COMPLETE` describes structural change/context coverage, never semantic adequacy,
observed reading, independent acceptance or a call allowance. The historical
32-read case can offer eight initial bounded reads over the four selected
function windows, two docs and evaluator; necessary expansion may use more.
No model, token, currency-cost saving or budget enforcement is inferred.


## Typed returns and delivered results

A dispatch child's generated return contract names its packet's declared output
beside `return_path`. `declared_output` gives the exact project path with guarded
`store_artifact` and `read_artifact` actions. Store the report there first, then the
typed return. When a plan declares no output, `declared_output` is null and a legacy
/1 return may name its own return file. The plan role `worker` and the return roles
`build` and `continue` are different vocabularies, and both are valid.

Every launch admitted from now on records its reserved child return paths beside
the admitted plan hash. The Artifact owner checks a write to one of those paths
before anything is stored. Only the admitted child of that packet may write there,
the plan must still be the admitted one, and the document must pass the same
validator that later reads it. A refusal names the failing field and the declared
coordinates, leaves no file or Artifact receipt, and the same live child can correct
the document and store it again. Honest BLOCKED or incomplete returns and negative
judgements are valid documents. A report at another path stays an ordinary Artifact
and does not satisfy the packet. Dispatches admitted before this receipt keep their
existing read-side validation.

When a delivered review settles, the queued continuation request and the automatic
continuation text name the reviewer turn's exact stored reply record:
`author_history {view: "record", id: "activity:journal:<reply id>"}`. Any admitted
session of the same project can follow it and another project is refused. The
presented message page remains a separate view under its own session fence, and no
reply body is copied into the notification. A missing or duplicated reply issues no
read. Following the read is not acceptance, receipt or completion.

## Inspecting results, plans and carriers without local files

- **Whole cumulative preflight.** `development_source {action: review-preflight, work_id, grant_id, candidate_id}` with `paths`
  omitted plans the whole subject: every declared obligation input, the commission's committed production across reissued
  grants, and the candidate's files (`paths_origin: CUMULATIVE_SUBJECT`). Its `scaffold.windows` can be passed unchanged as
  `source_context`. Explicit `paths` stay `CALLER`. The scaffold is offered context, never an observed read or acceptance.
- **Source-scope prepared completion.** For an obligation declared `scope: source`, `development_source {action: arm}`
  requires both `source_context` (normally the selected review-preflight `scaffold.windows`) and an explicit
  `source_subject` with its typed `stage` and any selected `prior.grants`, read-only `carry` and `accepted_base`. Prior
  grants and carry are never inferred from the latest delta. Missing, incomplete or stale input refuses before any intent
  is written and names the exact `review-preflight {work_id, grant_id, candidate_id}` read, so the same live producer arms
  again. The owner composes the exact prepared reviewer request within its existing 64 KiB ceiling at arm, in readiness
  and again before the one Continue appends its handoff. An uncontinued Source-scope intent recorded without its plan and
  subject reads HELD (`SOURCE_REVIEW_PLAN_ABSENT`) with that read; nothing grafts a later plan onto it. Guide and other
  non-source obligations keep the legacy plan-less meaning, and `parent_return: null` stays a review-only route with no
  parent return. Source review-preflight is distinct from the Work continuity `part: preflight` template validator.
- **Retained check output.** Every recorded check carries `output_read`, the retained-output view of the existing read:
  `{action: status, work_id, check_id, expected_sha256, offset}` (the same native read classification as status). Follow each page's `next_read` until it is null. Offsets are
  raw retained stdout bytes that never split UTF-8; each page's escaped content is bounded so the whole envelope fits the
  project line. Reading needs no live grant, works after stage removal, executes nothing and records nothing. Refusals are
  structured (`code`, `field`, `expected`, `observed`, `restart_read`, `next_reads`), never JSON inside the error text: a
  stale pin (`STALE_PIN`), an offset past the end (`PAST_END`) or inside a UTF-8 sequence (`UTF8_BOUNDARY`) issue the
  exact same-record `restart_read`. Changed, purged or missing bytes are `UNAVAILABLE`: the refusal keeps the recorded
  hash, truncation and custody, issues no read and promises no recovery. An unknown or foreign Work or check discloses
  nothing and issues no read. Through the native door the owner's typed reads lead `next_reads` (exact, deduplicated,
  bounded); a generic orientation suggestion may only follow them and is never a restart.
  `producer_output_truncated` means the profile cap stopped the producer: the missing remainder is not recoverable.
  `output_root` is a recorded location, not a read capability.
- **Status pages.** `development_source {action: status, work_id[, limit up to 64]}` fits its whole encoded response
  (rows, counts, continuations, notes and live allowance metadata) to the shared delivery line. All four parts page from
  one offset; a page may hold fewer rows than `requested_limit` and its cut-pinned `next_read` continues exactly. A row
  that alone exceeds the line is a header with `expanded: false`, its counts, `row_sha256` and `detail_read`
  (`{action: status, work_id, part, row_id, expected_sha256, offset}`), which pages the exact canonical row. A changed
  cut or row refuses with its restart; nothing is clipped or hidden.
- **Delivery status.** Default `work_delivery {action: status}` events carry `source_review_plan_summary` and
  `source_review_plan_reads` (`NOT_EXPANDED`). Its `sections` handles page the recorded subject's changed files, carry,
  effects, inputs and initial reads. The whole immutable plan stays on the intent and its handoff phase.
- **Manifest carriers.** Check `dependency_manifest` and review `source_subject.carry` share one carrier: inline
  `{schema, members:[{path, sha256[, bytes]}]}` or a pinned project Artifact `{artifact_id, expected_sha256}`. A malformed
  carrier (for example `{files: ...}`) is diagnosed with its role, field path, received keys, both accepted forms and the
  coordinates before any Artifact lookup. Work evidence rows are repository-relative `{path, sha256}` and are never a carrier.

## Optional shared native-call allowance

A human-issued Source grant can include `native_allowance` with these closed
fields: `commission_request_id`, `max_admitted_native_invocations`,
`max_app_admissions`, `max_sessions` and `wall_seconds`. The request identity is
an author-stable 8–96 character identifier. Counts are positive exact JSON
integers (at most 2^53−1); sessions cannot exceed app admissions. Wall time is
positive integer seconds up to the existing seven-day Source lifetime ceiling.
There are no fallback policy values. A grant without this option keeps legacy
behavior. Token, currency and all-raw-transport-attempt ceilings are unsupported.

The account belongs to the actual project, Work and author commission request.
Grant renewal or reissue cannot reset it or change its limits/original parent.
An explicitly authorised new commission has a distinct identity. The initial
ordinary turn selects only `source_grant_id`; admission resolves the existing
human-issued grant, original author session, Work, base and current authority.
The trusted execution attachment and app reservation live on the admitted turn.
They are not public request data. Reviewers and the original-parent return inherit
the same account through the existing delivery and admission owners. Generic
child launch/continuation is refused for Source-bound callers before creation;
only the supported exact evaluator/original-parent routes may spawn. Copying a
grant ID into an unbound model turn does not permit opted-in Source operations.

One fresh incoming native dispatch consumes one slot before argument validation.
A later invalid/refused call spends its admitted slot. Internal grammar/named
reentry and failure formatting keep the same private incoming identity; a later
arrival is a new slot even if its RPC ID or payload repeats. This is not generic
mutation replay. Claims and outcomes use the existing Writing journal/index and
admission lock. Owner effects run after that lock is released; their existing
request, pin, transaction and recovery rules remain authoritative. Source effects
and Writing tool audit rows retain the claim identity for inspection.

App/session capacity is reserved before creating a reviewer session. Only the
first exact reservation permits creation; recovery must find the indexed session
or actual admitted turn. Unresolved creation is unknown, not permission to create
another session. Existing-session parent continuations keep the exact original
session and their own admission identity. A lost acknowledgement never buys a new
app/session allowance. A new delivery from an opted-in Source handoff requires
the actual trusted original commission parent. A human or unbound caller cannot
turn that handoff into an uncounted legacy reviewer; genuinely absent-policy
legacy delivery and exact recorded-effect recovery remain available.

An attached Source caller may create only the supported exact reviewer or
original-parent continuation through its existing admission reservation. Generic
dispatch launch/continuation refuses before creating another session or reserving
a dispatch effect. The actual incoming caller remains authoritative even if a
payload names a different parent; unbound legacy dispatch is unchanged.

The result's late `source_allowance` reports current admitted, remaining, active
and denied counts, app/session capacity, deadline and stop reason, with an existing
Source status read. An outer transport response is prepared while its own claim
is still active through encoding and send. Successful delivery settles that same
claim; an encoding/send failure records delivery uncertainty. Direct calls without
an outer transport settle on return. The current status read observes subsequent
settlement. It is added after the owner's output digest/read basis and
reserved within existing delivery bounds; count changes do not change Source
cuts, raw pins or material Work guards. Human Source status also offers live
accounting outside its Source cut. Exhaustion gives no model-read exemption.

At the final slot the account drains: no new native call, reviewer or automatic
parent admission is permitted. All shared admitted calls may finish delivery
before native exhaustion stops participating providers; a turn with no local
active call cannot stop an active peer. A selected-turn Stop remains local.
Finite wall expiry, explicit account-owner stop and UNKNOWN still apply to the
whole commission. Already admitted effects retain their existing operation
limits and the finite commission deadline. Existing execution
supervision interrupts the actual owned provider/children at stop or expiry.
An in-process Python owner may still be unresolved: its claim remains spent and
active/unknown until observed settlement, never falsely reported stopped or
rolled back. Unknown claim/settlement custody refuses further owner entry and
uses the existing stop/recovery path. A total journal write outage cannot create
a fictional durable stop receipt; runtime uncertainty remains explicit while
no unproven claim enters an owner. On recovery, retained unresolved claims stay
spent/unknown; an attempt with no durable claim and no owner entry remains a
separate refused/unrecorded attempt, not an invented spent row. There is no
durable raw-attempt guarantee during total storage failure.

These limits count admitted native invocations. Unsupported/malformed transport,
wrong bound thread/project and other pre-native denials remain separate. They do
not turn the historical 61/40 attempt run into a compliant run. The concise
admission-time allowance line is turn context, not a kernel/profile change; it
and the original prompt are retained on replay. Current usage comes from late
metadata, without another initial discovery call or a model demonstration.
