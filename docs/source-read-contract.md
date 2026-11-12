# Pinned source pages

`expected_sha256` optionally pins the complete raw source bytes on repository,
project text artifact and Material source reads. Matching plain reads keep their
ordinary text format; a pin does not select JSON parsing or add authority.
Malformed, stale or absent-source pins refuse without returning mismatching
content. Digests accept 64 hex characters, optionally prefixed `sha256:`; hex case
is normalized. Malformed diagnostics do not echo arbitrary supplied values.

The stateless `core.source_pin.check` compares the identity the existing owner
already acquired. It reads or hashes no bytes. Repository fences/identity checks,
artifact permissions and all page/source/parse bounds remain with those owners.
JSON-record readers retain `RecordRefusal`; plain pin refusals are
`SourcePinRefusal`, also a `ValueError`. Material propagates both as refused reads,
rather than converting a source conflict to a successful unavailable observation.

Presence of `pointer` selects strict JSON mode. The empty pointer selects the
whole parsed JSON serialization, which differs from raw text. JSON pages preserve
their original Unicode-character units and existing UTF-8/duplicate/depth/parse
rules. `json_record.value_sha256` hashes the selected serialization;
`json_record.source_sha256` identifies the entire raw file. A change outside the
selected value invalidates the source pin even when the value hash is unchanged.
PDF source pins likewise identify original PDF bytes, not extracted page text.

Direct repository reads return three callable `operation`/`payload` handles:

| Field | Meaning |
| --- | --- |
| `page_read` | Same qualified source, mode/pointer, offset/limit and observed source pin |
| `read_handle` | NEXT page under that pin, or null at the end |
| `restart_read` | Explicit CURRENT source from offset 0 without the pin |

Repository offsets remain Unicode characters; PDF offsets apply to the selected
extracted page range. PDF continuation finishes that text range before advancing
pages under the same raw-source pin. Restart keeps the selected PDF page/count
and resets its character cursor. It never silently chooses another source,
changes parsing mode, retries or adopts a consumed dependency.

`reference_identity.read_handle` still selects the current source without a pin.
It is an initial current-read locator, not a claimed continuation of old bytes.
No whole-source content is repeated in handle metadata.

Artifact plain offsets remain returned UTF-8 byte boundaries. The existing
`read_handle` retains its NEXT/current-identity meaning: next pages now carry the
observed source pin, and a caller-supplied pin is retained. A complete legacy
identity reread remains current unless explicitly pinned. `page_read` repeats the
exact observed page; plain `restart_read` selects current bytes from offset 0.
Artifact JSON `record_read`, human link and Material restart keep their existing
pointer/page/version meanings. Mutation/update handles are separate and unchanged.

Material `read_handle` remains NEXT. JSON `record_read` remains its pinned same
record page; plain `page_read` and its human link now refer to the pinned same
source page. Both modes retain an explicit unpinned `restart_read`. Workspace
source wrappers preserve their consumer identity on all these handles. These are
current owner observations, not a new membership, consumed revision or acceptance
grant. A failed continuation may leave the prior page and its restart available;
the consumer must not fetch, reset or adopt automatically.
