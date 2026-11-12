# Hand over one complete selected project

A project can be handed over without a manuscript or application source in its data
workspace. Use separately selected or installed Laplace code. The existing
selected-project exporter and this data policy share file, history, body and WDEF
selection; the manuscript distribution policy keeps its existing entrance.

The first handover targets a **new destination**. It keeps the project namespace,
Work and material references, artifact history, full public conversation bodies,
and every version of its project-owned workflow definitions. It does not merge
into another workspace or copy other projects, accounts or running processes.

For an explicit Research workspace selection, inspect the exact saved workflow
version, then use **Add this inspected object to handover choices**. The choice
retains that full versioned reference; inspecting another history entry in the
editor does not retarget the parent handover choice. In the Handover tab, explicitly
permit each included object, prepare the selected manifest and review it before
**Export selected handover** to a fresh local directory. A previously inspected
old version remains that version even if a newer origin head is saved. Existing
SDK `research_handover` accepts the same explicit entries and expected bases.

Nonempty selected workflow-definition references carry every admitted original
row from the start of that definition through the selected revision, plus its
exact bodies and receipts. Export rechecks those captured raw rows before
publication; it does not restore/re-stamp them, substitute the newest version or
follow `derived_from` into other definitions. The selected transfer is limited to
the target project's definitions and explicitly selected workspace-owned
definitions within the actual caller's scope. Project-native readers cannot gain
workspace or foreign-project authority from a manifest. An explicitly empty
definition selection requests no definition custody; full-project export keeps
its existing selection policy.

Open **Read carried copy** using the retained manifest's existing workflow editor
read. The recipient reads its ordinary local definition/body owners without the
origin, with the original IDs and version chain. “Origin observation CURRENT” in
the manifest means its selected basis still matches, not that this is the origin's
latest version. An old origin revision can be the recipient's local current head.
Prepared run pins, effective provider settings, pending browser requests, drafts
and execution grants are not transferred as definition authority.

Plan with explicit storage and selected-row budgets, review the plan, then export
that exact plan:

```sh
/path/to/code/scripts/laplace-python -m laplace.projects.project_handover plan \
  --root /path/to/data --project example \
  --max-files 1000 --max-rows 2000 --max-bytes 20000000 --output /path/to/plan.json
/path/to/code/scripts/laplace-python -m laplace.projects.project_handover export \
  --root /path/to/data --plan /path/to/plan.json --destination /path/to/new-data
/path/to/code/scripts/laplace-python -m laplace.projects.project_handover inspect \
  --root /path/to/new-data
```

Budgets include generated registry, repository configuration, imported-session
boundaries and the handover receipt. The plan pins selected original files and raw
ledger rows. Export revalidates that cut under the reached owner locks, stages exact
bytes and publishes the directory with a no-replace operation. Changed or missing
owned inputs, occupied destinations, conflicting identities and unsafe paths
refuse; an unpublished stage is removed. Unrelated project appends do not change the
selected cut. POSIX publication requires `renameat2(RENAME_NOREPLACE)`; unsupported
hosts refuse instead of falling back to an overwriting rename. Windows directory
rename is used only with its no-replace semantics; Linux checks do not certify
Windows execution.

Open the new data home using the existing separate-home entrance:

```sh
/path/to/code/scripts/laplace-python -m laplace.desktop.writing_app \
  --repo-root /path/to/code --workspace-root /path/to/new-data
```

Choose fresh receipt, engine and session locations when overriding those defaults;
see [Operational homes](operational-homes.md). Export and inspection launch no
provider. Original public binding rows stay as history. An appended existing
`writing-session-import` boundary clears the effective native ID and registration;
a future explicit author turn starts a new provider conversation. Native transcripts,
credentials, process receipts, session cwd trees and browser profiles never travel.

“Complete” describes **selected project data**, within the caller’s authority and
the existing private/runtime exclusions. Selection does not certify publication
permission. External repository aliases are
listed as UNBOUND, and foreign artifact/Work references remain qualified unavailable
dependencies. They are not copying permission, self-contained content or execution
readiness. The original external host path is not a destination default. An explicit
authorised target can be bound under the same repository ID through
`profiles/writing_sources.json`: remove its `unbound_repositories` entry and add the
chosen target in `repositories`. The ordinary source/material owner then observes
availability and the consumed revision; it does not rewrite history or adopt changed
bytes. Such an authorised configuration edit changes the frozen handover byte check.

The receipt is `project-handover.json`. Inspection verifies its selected output pins
and reads ordinary project, Work, artifact/material, definition and session owners.
It is a frozen handover check, not a claim that later authorised edits preserve the
original hashes. Original historical absolute paths are preserved as observations;
this policy grants no implicit alias to another host. Retained journal-store addresses are verified through the prior canonical
selection, exact local row hashes/order and project-qualified store associations.
Repeated handovers retain those original rows without reading old roots or
requiring mutable files to match an earlier export. Other old history pointers
without admitted portability remain unavailable.

Current bounds include 64 MiB/100,000 rows per legacy scanned ledger, 100,000 project
directories, 100 MiB per file,
and the caller's complete output budgets. Default v1 WDEF transfers retain the existing
32-version/1 MB owner bound; longer chains refuse rather than truncate. The
separate explicit `lineage-v2` profile below uses bounded cells without changing
those defaults. The legacy
WDEF journal bank `row_id: "?"` cannot be attributed to an exact definition and is
reported as unavailable provenance. No bank attribution or execution grant is
invented.

Explicit selected WDEF collection, exact owner inspection and final output use
one private captured metadata selection instead of repeatedly materializing the
whole dispatch journal. Cold capture remains linear; it does not make a fresh
library/editor startup, current policy resolution or a large selected output
constant-cost. Existing caller row/file/byte budgets still bound the selected
output. A malformed nonblank dispatch row, ambiguous selected history or missing
selected body refuses rather than producing an apparently complete package.

<a id="opt-in-complete-workflow-lineage"></a>

## Opt-in complete workflow lineage

Use `definition_transport: lineage-v2` only through its actual owner offer and
closed `project_handover.object_contract()`. The local SDK/human door can prepare
an exact saved definition selection or an already retained selected-manifest
reference and basis. The definition-only profile carries workspace-owned prefixes
into a fresh root without inventing a project or registry. A project profile
requires the actual matching local project; an explicit definitions-only project
selection is not a full project snapshot. A selected-manifest profile carries
that manifest's admitted project closure plus the selected definition prefixes.
The existing complete-project CLI above remains its v1 policy.

Project-lensed history is still project scope, even for local HTTP. Its offer
cannot silently promote itself to workspace export authority. Follow the saved
object's explicit Workspace/Add/permit/manifest route through the actual local
owned-workspace door, or use an authorised owned-workspace SDK request. Native
project reads can inspect admitted project definitions; they cannot request a
destination, Export, Continue or inspect local transfer directories. No JSON
scope label, shared link or copied cursor grants those permissions.

The first pure `action: request` takes the original request ID, exact selection,
fresh destination and explicit total file/row/byte budgets. It returns PREPARED,
`effect: none`, and an Export handle containing `expected_lineage_basis` before
any stage or recipient exists. Keep that full original wire. An Export processes
one bounded cell; only verified quiescent PARTIAL exposes the exact checkpoint-
bound Continue and Inspect. Continue is an explicit decision, never a loop hidden
inside a click. Repeating original Export observes the original stage; it does
not advance or repair it.

After a lost first/intermediate/final acknowledgement, use pure Inspect of the
same original wire. Use the PREPARED response's issued `inspect` handle, which retains every original
selection, destination, source basis and budget and changes only the requested
read action. Do not construct a new wire from current mutable fields.
The owner recomputes one deterministic stage path from that immutable intent,
not a directory search or registry. Missing original wire/locator, busy, corrupt,
foreign, CHANGED_INPUT and UNKNOWN states grant no replacement or continuation.
Neither stage nor destination observed is not proof of a terminal no-effect.

A completed transfer preserves original raw selected rows in global physical
order and unique original content-addressed bodies through every selected
terminal. It verifies cross-cell previous/request/pair/revision/body chains,
exact output sets and the final inventory/header pins before no-replace
publication. Scratch controls/parts stay outside the published payload. The
recipient uses ordinary local definition/history owners with the origin offline;
local currentness does not renew the origin head or import approval/execution.

A cell remains at most32versions/1MB, while total caller budgets bound the whole
transfer. Single bodies remain at most200000B and every final file, including raw
dispatch and inventory, remains at most100MiB. Capture bytes/metadata rows,
copy/hash buffers, progress-control size, staged peak and committed output are
separate costs. `max_staged_bytes` also bounds scratch/parts/assembly, not RSS or
filesystem allocation. Cell deadlines stop at safe boundaries; blocking I/O is
not hard realtime. No raised cap, O(delta), universal scale or one-read claim is
made. An actual resource refusal keeps the original request and explicit reason.
