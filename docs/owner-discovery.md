# Owner discovery: finding Work from the system entry

This explains the capability `work.owner-discovery` (declared in `src/laplace/system/description.json`). It lets a
person or an agent who knows nothing about the projects find the Work that affects part of the system, starting
from the system itself. The code is `src/laplace/work/owner_discovery.py` (Work facts and bindings),
`laplace.system.entry`/`choices` (the declared subsystems) and `src/laplace/sdk.py` (the Python entry).

## Start at the system

A caller supplies three things: the system entry, a task or the name of an affected subsystem, and its actual
scope. It does not supply a project name, a Work id or a file path. Each result says what to read next.

```python
from pathlib import Path
from laplace import sdk
workspace = Path.cwd().resolve()                 # the package's extracted data/workspace root
entry = sdk.describe(root=workspace, task='browser workflow interface')
for choice in entry['selection']['choices']:      # declared choices; the caller selects
    page = sdk.request(choice['next']['request'], root=workspace)
    for item in page['items']:
        work = sdk.request(item['next']['request'], root=workspace)
        print(work['reference'], work['purpose'])
```

Pass that same explicit `root` on installed-library calls. If omitted, the SDK
uses `LAPLACE_REPO_ROOT` when configured, otherwise the imported package's source
location; it does not infer the current data workspace. Empty `items` means no
bound Work in that scope, with the result's coverage qualification. It is not a
reason to guess a project or object ID.


The four reads share one request shape (`owner_discovery.contract()`) and one result shape
(`laplace.owner-discovery/1`):

| Read | Grade | Returns |
|---|---|---|
| `describe` | system | The declared purpose, each subsystem with its responsible owner and in-scope bound-Work count, the declared capabilities, and the subsystems a task's words name. These are choices: nothing is selected for the caller. |
| `discover` | subsystem | The in-scope Work bound to one subsystem, directly or through a capability it owns, with standing, the matching relations and a paged read cut. Also an upward summary. |
| `inspect` | Work | Purpose, standing, blockers, activity (an expired observation reads as unknown, never running), next actions permitted at this read, the Work owner's own evidence reads (first five, with the Work detail read as the continuation for the rest), the binding, the parent and the lateral relations, each with its next read. Also the old project-qualified handles. |
| `resolve` | reference | A reference, an old `namespace::id` or an old `project` read handle as the canonical reference. A bare id held by several namespaces returns choices. |

## References and versions

`resolve`, `inspect` and binding targets admit a reference through one boundary (`owner_discovery.admit_reference`).
A reference is admitted only as exactly what it names:

| Supplied | Result |
|---|---|
| A subsystem (owner `core.identity`), a declared capability (its declared owner) or an existing Work (owner `domain.work`, identity exactly `namespace` and `id`) | Admitted as itself |
| A kind outside those three (a document, a claim) | `UNSUPPORTED_TARGET` |
| Another owner for the object | `WRONG_OWNER` |
| An extra or missing identity key | `MALFORMED_REFERENCE` |
| An undeclared subsystem or capability | `UNKNOWN_TARGET` |
| Work that is absent, or outside the caller's scope | `NOT_IN_SCOPE` (identical in both cases) |
| `version: {"work_revision": ...}` equal to the Work's specification revision | Admitted, version `CURRENT` |
| A different `work_revision` | `STALE_VERSION`, with the current revision and its read; the current Work is never substituted |
| Any other version key, or a version on a subsystem or capability | `UNSUPPORTED_VERSION` |

No history is reconstructed: the owner compares the current revision only. `resolve` reports the refusal as its
`status`; `inspect` and `bind` raise it. A legacy `namespace::id` or `project` read handle names no version and
reads the current Work. What the caller passes in, and everything it gets back, are JSON copies: changing them never
changes the owner's records.

## Evidence

Each evidence item in `inspect` is the Work owner's own evidence read, unchanged: an artifact inside the project's
home carries its HTTP read with the completion pin and a native `read_artifact` payload; a repository file carries
the repository material read; a file the owners cannot read is `available: false` with its `capability_gap` and a
read-only `local_read` coordinate. Opening an item follows that item's own read, so a changed or missing pinned file
is refused by its owner. Beyond five items, `evidence.continuation` is the Work detail read, which carries all of
them.

In the app, a Work's inspection also offers **Edit title and purpose**. It opens the plain outline over the Work
port (`work-port.mjs`): the owner's detail read, a draft that keeps the guard issued when you started typing, and a
save through the Work's own guarded `POST /work/task`. A refused save keeps your words and guard. **Compare with the
current Work** shows the current fields beside yours; **Use the displayed current Work as my basis** is a separate
step that adopts exactly that displayed basis, and is withdrawn if a newer owner read moves it. A save with no
response is shown as uncertain and is never resent, also after the view is captured and restored; **Reinspect**
says whether the owner now shows your words. Fields belong to one Work: selecting another Work replaces them. With a
draft or an unresolved save, **Open in project** asks first and leaving the page is guarded. The project Work card
uses the same port and the same compare-then-adopt steps.

In the app, **Open evidence** follows that read. **Back** shows the earlier result marked as retained, with the
time it was read. That retained result may be out of date. **Reinspect** rereads it. Observations keep the expiry
their owner stated.

Every handle spells the same request three ways: `request` for `laplace.sdk.request`, `native` for the agent door
(`project {"view": "discovery", "request": ...}` inside the session's project) and `http` for
`GET /work/discovery`. The app's **System owners** view (Workspace menu) paints the same results.

Project Work handles have a different, existing shape: `operation='project'`,
`payload` and an HTTP companion under `/work/state`. Follow their exact payload
with `sdk.work_read(handle['payload'], root=workspace)`, rather than passing it to
discovery's `sdk.request`. This SDK facade reads only its closed readonly Work
view family with the local root's authority. Native callers remain bound to their
actual project. [Review evidence](writing-review-evidence.md) separates counts,
explicit lists, selected inspection routes and evidence body reads.

## Bindings

A Work is found from a subsystem only when its owner records a binding. A binding is a `project-work-binding` row in
the Work ledger (`corpus_friction/work_orders.jsonl`). It names typed relations from one existing Work to declared
subsystems, declared capabilities or other existing Work: `responsible-owner`, `targets`, `coordinates`, `consumes`
and `explains`. It is written by `laplace.sdk.bind` or `POST /work/binding`. Two guards are required: the Work's
`expected_work_revision` (the same guard a Work edit uses) and `expected_binding_revision` (null for the first
binding). Both are compared inside the ledger's writer lock, and so is every target: a target Work given with
`version: {"work_revision": ...}` must still be at that revision when the binding is published or reused, or the
binding refuses `STALE_VERSION` and nothing is appended. The stored target is the Work itself, without the version.
Replaying the current binding appends nothing.

A binding is metadata only. It does not change the Work's specification, scope, standing, completion, evidence or
reviews, so no existing read cut or guard moves. It does not grant any write: actions still go through the Work's own
admitted doors.

## Scope and what stays private

The host supplies the scope, never the request. The SDK and the local HTTP door read the workspace they own. The
native door reads only the session's project. Work outside the scope is not listed, counted or named, and
inspecting it returns the same `NOT_IN_SCOPE` result as a Work that does not exist. Evidence appears as handles;
each handle's own owner decides whether its bytes can be read.

## Coverage

Only bound Work is listed. Absence from a page means "no binding in scope", not "no Work". Every result states its
coverage, and a long list pages with a read cut: a continuation is refused if bindings or standings changed in
between.


### Read a local map or timeline

The same discovery request accepts `facet: neighbourhood`, `semantic-scope` or
`timeline`. Follow the issued `neighbourhood_read`, `scope_read` and
`timeline_read` handles on a selected object. A project is an optional narrowing
lens. A map transports compact owner observations, not source text, prompts or a
complete network. Its coverage and frontier state what remains to inspect.

Containment, prerequisites, recorded consumption, unpinned relationships and
configured or admitted routes remain different edge kinds. A consumed edge keeps
its historical basis separately from the neighbour's current observation. The
lanes have separate cuts; they do not claim an atomic global snapshot. Camera and
representation changes over a loaded page need no new owner read.

A workflow step is an exact saved definition reference plus its local step ID.
A review phase or delivery event is its existing Work reference plus its recorded
local ID. Their detail handles enter the canonical editor or owner reader.
Timelines retain recorded owner order and report unavailable timestamps; they do
not turn navigation or a current scientific judgement into a fabricated event.

Pure aggregate reads may share a private request-local Work snapshot and review
facet memo. That frame never travels on the wire or into an effect, admission or
later request. Different closure statuses and consumed inputs retain their own
currentness. No cross-request permission or result cache is introduced.
