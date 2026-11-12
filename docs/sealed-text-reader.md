# Sealed text reader

A sealed reader reports on one complete selected text document and the complete
text references you explicitly supply. Inspect the input before starting. Its
report belongs to those immutable inputs; it does not certify their claims or
accept Work. Ordinary informed review remains available through its existing
conversation path.

This edition ships one fresh, tool-less Claude profile and its local operator
qualification entry. It does not ship this host's qualification or enable Start
on the strength of CLI flags. A recipient must qualify its own exact executable
and adapter with public startup, tool/read and input-delivery canaries. The
source-host qualification is evidence for that host, not portable permission.

## Provider build and local support

The conversation-reading image includes Claude 2.1.304. Installed verification
found the exact supported Linux/x64/glibc executable SHA-256,
`ea0f135784631619a7a409d07322ecec964f9cc4fd377508ed1ba3f141f27912`,
and reader support `CANDIDATE` with no installed proof. The normal and
both-provider [source builds](writing-container.md) select that version too.

To enable reader Start in your installation:

1. Sign in with your own provider account using the
   [account guide](writing-account-setup.md).
2. Inspect support and select a model/effort supported for that account. Prepare
   and read the complete public qualification input.
3. Follow the [local operator procedure](#local-operator-qualification-attempt),
   judge its retained public observations and install the local qualification.
4. Read back `QUALIFIED` support and its evidence, then use the issued Start
   payload for your selected document.

The qualification belongs to the exact local executable, adapter and evidence.
A different provider override needs its own reviewed support; copying another
host's proof does not qualify it. See [edition history](writing-container-download.md#earlier-editions)
for the earlier package's provider limitation.

## Prepare and inspect

Use the existing System owner entry for `domain.authoring`, which reaches the
existing P6 Work. A registered project supplies custody; it need not have a
manuscript or code root. Select an existing owner-qualified Material repository
or artifact target and its full raw-source SHA-256. Do the same for each selected
reference. Missing or unselected references are explicit declarations, never
automatically fetched. Existing Material linkage is retained where available;
selection does not certify citation alignment or transfer release permission.

`GET /authoring/reader?project=...&view=support` reads support without starting a
provider. `POST /authoring/reader` with `action: "prepare"` retains an input using
the existing Writing header and body custody. The equivalent SDK call is:

```python
from laplace import sdk

prepared = sdk.reader_request({
    "project": "public-project", "view": "prepare",
    "primary": {
        "target": {"owner": "repository", "repository": "public", "path": "document.txt"},
        "expected_sha256": "sha256:<the owner's full raw-source digest>",
        "representation": "utf8-text",
    },
    "references": [],
    "missing_references": [],
    "task": "Explain the stated claim and identify missing support.",
    "model": "<an explicitly supported Claude model>", "effort": "<supported effort or null>",
}, root="/absolute/selected/workspace")
```

The existing native `project` operation delegates the same request through
`{view: "sealed-text-reader", request: {...}}`; its request project must equal the
actual caller project. That operation prepares or reads; it never starts a model.

Read the returned manifest and all `parts` handles: generic kernel, editable task
and complete selected packet. Part reads page at most 40,000 characters and carry
the exact full part hash and length. The manifest retains owner-qualified targets,
raw-source pins, text-body hashes, derivation, coverage, model/effort and sizes.
One metadata receipt in the existing Writing journal records that this owner
issued the manifest. Supplying an arbitrary public-body reference cannot create
an admitted input. Bodies are content-addressed and reused, not copied into a new
reader store.

Plain UTF-8 is the primary representation. `pdf-text` is separately explicit and
requires the existing pinned extractor to establish coverage from the first to
last page. Extraction identity and selected extent are retained. Figures, visual
layout and inaccessible references are not supplied. A human PDF viewer is not
evidence that the model received page images.

The editable task has the existing 100,000-character author-message limit.
Attached document and reference text has no transplanted task limit. Exact
characters and UTF-8 bytes are shown without clipping. Input fit remains
unmeasured: model capacity and compaction belong to the provider, and advertised
or observed windows remain separate telemetry. A capacity rejection retains that
attempt and exact input; prepare an explicitly smaller scope rather than silently
clipping or automatically retrying.

## Explicit Start and uncertainty

Only a `QUALIFIED` support receipt permits Start. Retain its input, support basis
and a stable request ID before submitting the returned payload through
`POST /authoring/turn` or `sdk.reader_start`. This closed profile accepts only
`project`, `profile`, `input`, `expected_support_basis` and `request_id`. It rejects
existing WS/native IDs, ordinary workspace/selection/draft/queued Work context,
model overrides and resume. Admission rechecks selected owner pins and exact
representation, then creates a fresh WS/WT before calling existing execution.

The response supplies the new WS/WT and `reader_submission.read`. When the first
acknowledgement is lost, no WS is required for reconciliation:

```text
GET /authoring/session-turn?view=reader-request&project=...&request_id=...&manifest_id=sha256:...
```

This pure read returns `RECORDED` with exact identity/intent and an ordinary turn
read, `NOT_ADMITTED` with an exact terminal refusal and no WS/WT, or `NONE` at its
captured journal cut. It uses the existing metadata index,
normal index lock, incremental capture and replacement detection; it opens no
content bodies and adds no unlocked request registry. A lock wait or transport
failure is uncertainty, not absence. `NONE` is not automatic retry permission.
Keep the original wire intent and identity. An explicit identical retry passes
through existing locked admission; replay is compared before mutable source or
support checks and returns the same attempt. Changed intent under that identity
refuses, including when the original is still in flight. Ordinary selected-action
reconciliation continues to require its original parent session.

A known check before session creation may explicitly return
`reader_refusal.disposition: "NOT_ADMITTED"`, `terminal: true`, the exact profile,
project, request, manifest, intent, stable outcome identity/read, rejection code
and scoped support/input/currentness reads. This is published and verified in the
existing Writing journal under the admission lock before terminality is claimed.
Only that terminal response releases a pending Start for explicit reinspection or
preparation with the retained task and selection. Support drift or unqualified
support, changed/unavailable selected inputs and missing/corrupt prepared bodies
have named codes. Required kernel/task/packet bytes resolve before session
effects. Generic HTTP 409, unknown storage or transport failures and post-effect
errors do not carry this terminal disposition. They keep the original pending
identity for reconciliation; a pure read may later discover an outcome that
published before its acknowledgement was lost. A late identical copy replays the
same terminal refusal even after inputs are restored. Changed intent or request
kind under that identity refuses. Reinspection may explicitly choose a new
request; rejection does not permanently block its manifest. A previously recorded
successful replay still returns its old attempt before mutable bodies, source or
qualification are checked.

## Read the result or make a fresh attempt

The reader WS is permanently one attempt, including after completion or Stop.
Session reads expose `reader_profile` and `reader_capabilities`: ordinary Send,
settings changes, active steering and native tools are unavailable. Use the
returned input/new-attempt handle to inspect or prepare an explicit new question;
do not resume the old provider session. Existing interrupt, partial reply and
history owners retain the old result. Source currentness is reported separately;
later source edits do not rewrite the packet or renew the report.

The issued manifest reference remains opaque in reader session/turn control
metadata and the reader's consumed/dependency wrappers. Ordinary session reads
do not hydrate the selected document to recover that identity. The returned
new-attempt handle opens verbatim after completion or Stop; explicit reader input
reads retrieve the retained content. Ordinary rich content reads keep their
existing behavior.

The adapter uses the existing process supervision and stream reader with safe
mode, empty built-ins, disabled slash commands, strict empty MCP, no Chrome, no
session persistence, a replacement generic system prompt and exact model/effort.
It uses no project gateway, style, plan, history or additional directories. No
credentials or provider history are copied and HOME is unchanged. Requested
controls, sent bytes and observed public inventory are distinct facts. Unexpected
offered tools/MCP, attempted tool calls or positively reported unsupported
effective instruction context make the attempt unqualified. Agent-type and
plugin-manifest catalogues are separate metadata: their nonzero counts or unknown
identities alone do not establish read capability or effective context. Missing
optional context fields remain explicitly unobserved. General model
knowledge and ordinary platform safety instructions remain premises; no claim is
made about model attention or universal provider/OS isolation.

The operator proof in `profiles/writing/sealed-reader-qualification.json` is bound
to actual executable identity, exact controls/kernel and adapter/profile source
identity. It is not an app/native mutation or a Start override. Missing, malformed
or changed qualification leaves Start unavailable. Synthetic fixture proof and
fake process streams verify source joins only; they do not qualify a real model
run. Codex and visual document reading are outside this first profile.

Fresh startup receipts use `OBSERVED_SEALED_READ_BOUNDARY` when explicitly
reported offered tool/MCP lists are empty and the selected effective-context
fields establish no contrary behavior. This does not claim every inventory or
platform instruction is absent. Receipts separately retain declared policy
premises, catalogue totals/provenance/digests and unobserved effective context.
Only approved public builtin matches or matched descriptor classifications are
shown; custom names, plugin paths and configuration contents are never retained.
Unknown catalogue provenance is nonblocking metadata. Unsupported schemas are
labelled rather than guessed. The pinned executable/source policy scopes the
classification; it grants no capability or qualification. Old saved startup
receipts and failed actual attempts are not reinterpreted by this observer.

The installed qualification names exactly three kinds: startup,
tool-read-canary and input-delivery. Each entry holds a local Writing body
reference to a closed evidence envelope, which names the same profile,
fingerprint and kind and retains its observation through another verified local
body reference. All bytes must resolve and hash-verify before support is
qualified. Opaque hashes, wrong kinds/bases, foreign stores and unavailable or
corrupt bodies do not qualify. This verifies custody and the declared basis;
The responsible operator still judges the substance of the canary.

Support/input inspection exposes bounded evidence summaries and exact
owner-issued envelope/observation reads. These use `view=evidence` with the
installed proof's kind, part and expected support basis, and page at most 40,000
characters of the exact JSON body text. Callers cannot select arbitrary body
references or paths. A changed installed proof requires explicit reinspection.
The first real canary is a separately commissioned operator action through the
existing adapter; neither app nor native Start has a provisional qualification
bypass.

## Local operator qualification attempt

An explicit trusted local operator can exercise the same fresh sealed adapter
before production proof exists. This is a separate purpose, not an app Start
override. The public HTTP/native/SDK Start contract still requires `QUALIFIED`
and accepts no purpose, limits or `allow_unqualified` flag. Imports stay passive;
there is no second runner, store or provider adapter.

The local entry is `python -m laplace.writing.reader_qualification --root
/absolute/public/workspace --commission /absolute/commission.json`. The closed
commission has schema `laplace.sealed-reader-operator-commission/1`, purpose
`operator-qualification`, project, issued input reference, exact inspected
candidate fingerprint/support basis, unique request ID, and explicit limits:
positive finite decimal `max_budget_usd`, positive finite `wall_seconds` and
`cleanup_grace_seconds`, and positive integer `max_input_utf8_bytes` and
`max_output_utf8_bytes`. Local invocation is the operator action; possessing a
file is not a cryptographic proof of authority. The responsible operator must
explicitly authorise any actual public canary, including its public inputs,
purpose and finite limits.

1. Inspect support in the selected public workspace and prepare a public input
   through the owner above. Read every retained input part. `CANDIDATE` means only
   that the executable matches the reviewed help/control basis; `UNAVAILABLE`
   cannot use this entry. A different CLI needs its own reviewed support basis,
   not a copied certificate or an override.
2. After explicit operator authorisation, create the closed commission below.
   Substitute the issued reference, current support values, a unique request ID
   and the authorised finite limits. Place no credentials or private input in it.
3. Run the local command above in the same environment and OS account as the
   provider. Inspect the exact turn's input/SENT facts, startup capabilities,
   tool/read canary result, report, usage and stop/cleanup observations. Missing
   or unknown facts are not successful qualification. Do not retry automatically.
4. Only after judging those public canaries, retain their observations and the
   three closed evidence envelopes in the existing local Writing body store.
   Install the closed qualification JSON described above, bound to that exact
   fingerprint. Preserve an unexpected existing proof for explicit reconciliation.
   Re-read support and all six issued envelope/observation reads; Start must remain
   unavailable if bytes, source, executable or required evidence do not match.

```json
{
  "schema_version": "laplace.sealed-reader-operator-commission/1",
  "purpose": "operator-qualification",
  "project": "<registered public custody project>",
  "input": "<replace with the complete issued input reference object>",
  "expected_fingerprint": "sha256:<inspected support fingerprint>",
  "expected_support_basis": "sha256:<inspected support basis>",
  "request_id": "<unique authorised request ID>",
  "limits": {
    "max_budget_usd": "<positive finite decimal string>",
    "wall_seconds": "<replace with a positive JSON number>",
    "cleanup_grace_seconds": "<replace with a positive JSON number>",
    "max_input_utf8_bytes": "<replace with a positive JSON integer>",
    "max_output_utf8_bytes": "<replace with a positive JSON integer>"
  }
}
```

This is a field template, not an executable commission. Qualification and its
observation bodies are installation-local and excluded from distribution seeding.
The package supplies source and documentation, not a qualification-install helper
or an automatic canary. Its ordinary UI/HTTP/native/SDK surfaces cannot authorise
this operator action.

The input limit covers complete generic KERNEL plus actual stdin before session
effects. It is an operator canary scope, not a new reader document cap. Purpose
and all limits are sealed in the exact request intent. Existing admission locks,
terminal outcomes and replay apply: the same request starts once, while changed
purpose/limits or request kind collide. Only the exact supported candidate or
qualified executable/profile can reach the existing execution path; unavailable
support and forged inputs cannot.

Both purposes share the exact input builder, information-control arguments,
kernel, observer, stream/reply owner and cancellation. Only the declared operator
stopping restrictions differ. `--max-budget-usd` is constructed and validated by
the shared argv policy. It requests the CLI's documented monetary ceiling; it
does not establish invoice accuracy or a hard output-token guarantee. Existing
supervision observes wall expiry independently of stdout, interrupts the owned
process group and uses the admitted cleanup grace. Public output is retained and
emitted as a valid UTF-8 prefix within its byte bound; expiry retains partial
reply and limit reason, with no automatic retry or fallback. OS cancellation and
cleanup are observed facts, not a universal real-time guarantee.

The existing exact turn/result receipt retains operator purpose, limits,
candidate fingerprint, input/SENT facts, actual argv/process identity, public
inventory, final/partial text, usage/cost and stopping observations. The local
entry waits its existing supervised job rather than leaving a daemon behind.
It never creates evidence envelopes or installs qualification. The responsible operator separately
judges a commissioned real attempt before installing any production proof.
Harmless Python fake-process tests prove these source joins and cleanup only;
they are not a Claude canary and use no temporary or synthetic qualification.
