# Read review evidence without expanding everything

Review evidence is a pure read of one selected Work. Start with the offered
review-evidence read in Work or Backlog to see its obligation counts, then ask
for a list or inspect a selected obligation. Reading starts no review, approval,
execution, acceptance or publication. The existing full Work and review views
remain available for their established editing and inspection tasks.

The count unit is a review obligation. Required, satisfied required and remaining
required counts describe the Work owner's actual decisions. Optional obligations,
follow-up Work, recorded phases and pending joins keep their separate meanings.
Unmanaged Work is explicitly unmanaged. Zero required obligations does not imply
a 100 percent satisfaction ratio. A complete count does not mean its identities
were enumerated, supporting metadata expanded or original evidence bodies read.

Listing is explicit and bounded: all obligations, required obligations or remaining
required obligations. Follow the exact advancing read supplied by the owner.
Inspect only supplied obligation identities at that same observation. A selected
inspection can offer declared inputs and exact phase or body reads; a link to a
container or phase is an inspection route, not a claim that its full evidence has
already been read. Oversized or unavailable support is labelled explicitly.

## Follow the actual read handle

The local Python SDK reads a project Work handle through `work_read`:

```python
from laplace import sdk

# read is the exact owner-issued project Work read selected by the caller.
observed = sdk.work_read(read['payload'], root=workspace)

# Choose the offered list deliberately. The owner binds its observation.
remaining = sdk.work_read(
    observed['enumerate_reads']['remaining-required']['payload'], root=workspace)
if remaining['items'] and 'support_read' in remaining['items'][0]:
    inspected = sdk.work_read(remaining['items'][0]['support_read']['payload'],
                              root=workspace)
```

The existing transport is `project` with `view='review-evidence'`, one Work `id`
and its closed `request`. The local handle's `namespace` names the selected Work;
it does not change the host's actual Scope. Requests default to aggregate/all.
Enumeration supplies an observed token, offset and bounded limit. A support read
also binds its enumeration page and selected IDs. Follow the issued payloads
rather than constructing tokens or collecting IDs from different pages. HTTP
companions encode `request` as JSON in the existing `/work/state` GET query;
duplicate query or request keys are refused. Native calls carry the same owner
payload inside their already bound project session.

Pass the payload unchanged when following a supplied continuation or inspection
read. `sdk.request` takes discovery-handle `request` objects instead; project Work
payloads do not belong to that discovery grammar. The SDK Work facade accepts only
the closed readonly Work view family. Effects still have their own explicit owners
and guarded APIs. A local SDK reads its root's owned workspace; that authority is
not transferred to a native project session. HTTP and native reads use their actual
host-supplied scope, never a JSON authority field.

## Observation, currentness and restart

An observation binds the selected Work, selector and count unit to the facts
actually consumed, including relevant review/closure records and Source or evidence
bases. It is not an atomic filesystem snapshot. A continuation reobserves those
inputs in a fresh request context. Unrelated Work or activity does not become a
dependency merely because it shares a ledger. Changed consumed input refuses
mixing and supplies an explicit fresh-summary restart. Refresh does not silently
rebase a held list, draft, target, basket or pending effect request.

There is no durable aggregate-support store. After process restart, equal observed
inputs can still be read; changed or missing inputs require a new observation.
Metadata already delivered remains that observation's metadata, not a guarantee
that its original bodies remain available. Current Work reads, retained Source
versions and exact publication recovery retain their distinct owner meanings.

New guarded phase reads include the phase row-set revision observed by the owner.
An append under the same phase ID can therefore refuse an old guarded read and
offer the fresh one. This checks currently retained rows; it neither reconstructs
an old historical row-set nor invents a retained body. Legacy unguarded phase reads
keep their prior current-row meaning.

## Delivery cost and limits

Aggregate-only reads avoid building unrequested rich support. They can still
resolve evidence and Source observations needed for a truthful decision; this is
not a promise of zero body, digest or discovery I/O. Enumeration remains proportional
to requested output. All new responses stay within the existing Work navigation
or smaller native delivery line, including handles and refusal metadata.

If a page shares identical support descriptors, its explicit encoding and ordered
per-obligation references retain original handles, context and duplicates. These
local references are data within that response: no URI, authority, durable identity
or cross-response catalogue. Byte compaction alone proves no token, latency,
memory or asymptotic improvement. Bodies remain separate explicit owner reads.
