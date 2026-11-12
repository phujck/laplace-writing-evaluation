# Continue one failed review

This owner slice continues one existing settled judge session in an admitted app
workflow. It keeps the exact saved plan, consumed settings and completed worker
return/report. It cannot create a missing judge session, rerun a worker, repeat a
valid positive or negative judgement, clear a held Work, or renew a deadline.
Cancelled, withdrawn, done, verified and blocked Work need a separate disposition.

`dispatch_execution.continuation_offer` returns a read-only available/refused
offer. Its opaque `guard` pins Work scope/standing/dependencies, plan ART and WDEF,
prior judge turn, return revision/absence and prerequisite return/output custody.
Its budget is one child launch and the unchanged original deadline, explicitly
null when absent. The native `dispatch_continue` payload is exactly `id`, `packet`,
`request_id`, `guard`, `budget`. The caller's actual project/turn/role are bound by
the adapter. An offer or browser composer does not supply effect authority.

`continue_dispatch` requires fresh actual author admission in the original parent
session. Under the existing dispatch lock it rechecks the offer, app provenance,
completed prerequisite standing and pinned judge settings, then appends a request
reservation to the same Work. `dispatch_review_continuations` retains the request,
intent digest, existing WS, planned WT, child request, guards and phase;
`dispatch_review_current` selects the authoritative request for each packet.
These are existing Work transition fields, not another ledger or runner.

The reservation is written before effects and marked LAUNCHING before the normal
detached child-host route. Normal turn admission consumes the reserved WT identity
and uses the same judge WS in review mode. The native binding owner decides
provider continuity; no account or history is cloned. The operating brief precedes
WT banking, so template discovery without a turn ID uses only the exact durable
planned WT while LAUNCHING. Actual effect/help/session consumers pass their real
turn ID. Artifact publication rechecks the banked selected WT under the existing
dispatch lock; a template is never independent write authority.

Same request and identical intent returns its receipt without another host;
changed intent refuses. `continuation_request` is a read-only reconciliation of
the exact reserved WT/session/request/parent binding. RESERVED without a turn is
NONE; ambiguous host acknowledgement is UNKNOWN; a matching banked WT is RECORDED
admission, not proof that a provider executed or review succeeded. A timeout,
replay or read never launches again. The original request is retained even when
the host acknowledged no result.

`project_work.dispatch_attempts` selects current turns from the explicit Work
binding before dependency, execution, review and parent synthesis calculations.
Prior turns retain exact public-content/history reads. A pending attempt carries
no invented observed WT or conversation. Legacy single-attempt runs retain their
existing meaning. Recorded usage/cost includes all historical attempts, while
execution/review counts use current attempts. The old wave's FAILED flag is bypassed only for the exact newly
admitted target turn; no other host is revived and old failure history remains.

Only the selected turn may publish at the existing return path. Missing output
uses `before:null`; an invalid existing return uses the ART owner's exact CAS.
The write retains prior before/after bytes in ordinary ART history; an old ART ID
alone still reads the current path, so historical bodies use the selected journal
record owner. A stale prior turn, changed prerequisite or invalid replacement
cannot write/qualify the new return. Successful native READ execution stays
separate from a positive or negative judgement. Ordinary recoverable call errors
may be corrected within an admitted finite budget; zero tool errors is not a
completion invariant.

The workflow/native adapters and original-parent composer consume this owner
interface separately. No browser Send, child retry or new provider use occurs
automatically. Model-backed use requires a separate bounded actual-use grant.

## Selected action in an author message

The continuation composer returns a short editable request and a typed
`workspace_context.workflow_action` input with only `reference` and
`expected_basis`. The qualified reference names the project, saved definition,
Work, judge step, stable continuation request and original parent session.
Navigation uses `expected_action_basis` on the existing composer read. A changed
offer refuses with `next_reads`; choosing a new proposal requires explicit
reinspection. The basis seals the exact native call, parent, definition version
and Work guards, without display labels or timestamps.

Before creating or changing a session, banking a new turn or starting a provider,
ordinary turn admission resolves that input through the continuation owner. Only
the owner creates `laplace.workflow-action-context/1`, containing the exact native
call, summary and pinned read. The existing public-body store retains the resolved
workspace context once, at every size; exact turn reads recover it while thread
summaries remain bounded. The admitted prompt has one labelled selected-action
section beside the human request. The agent still invokes the existing project
tool, whose original parent and effect checks remain authoritative.

The parent submission request is separate from the child continuation request.
For this selected-action path, admission seals every supplied JSON input field
except the parent `request_id`. Identical replay compares that seal before reading
mutable current state and returns the original turn; changed intent refuses.
Other author requests retain their existing replay behavior. Pure reconciliation
uses `GET /authoring/session-turn?view=request&project=...&session_id=...&request_id=...`.
It returns the exact recorded receipt or `NONE` at that read, and never launches
or retries. A failed read or unknown acknowledgement preserves the original
submission identity. `NONE` is not proof that an in-flight request cannot later
be recorded.

The browser context-card and pending-draft consumers implement this input
separately. No automatic Send, active-steering attachment, generic attachment
framework or provider inference is introduced by this owner contract.
