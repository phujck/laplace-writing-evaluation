# Consulted-read recovery

A proposal (candidate) is sealed with the exact reads it consulted. Before it can be applied, decided or shown as
current, the currentness owner replays those reads and compares each output digest with the sealed one. This note
says where that logic lives and how a refused candidate's changed reads are recovered without renewing, rebasing or
approving anything.

## Owners

| Concern | Owner |
|---|---|
| Seal: consumed read IDs and the receipts digest, in the warm fold's read-key order | `writing/records/_fold.py` `_seal_proposal_basis`, `_read_basis_digest` |
| Selected (cold) candidate projection | `proposal_navigation.selected_records` |
| Receipts, edition, source pins, siblings, owned inverse | `writing/proposal_currentness._read_scope` (shared by the whole check and the pages) |
| One consulted read replayed and compared | `proposal_currentness._observe_read` |
| The refusal's bounded summary | `proposal_currentness.consumed_read_recovery` |
| Every changed consulted read, in bounded pages | `proposal_currentness.changed_read_page`, served by the proposal read owner as `view=changed-reads` (`proposal_navigation._detail`) |
| Saved failure record | `writing_tools.bank_failure` banks the whole recovery, `changed_reads_page` included; the public history record and the session's failure view return it |
| Human route | `static_shared/writing-owner-read.mjs` (`changed-reads` target), `writing-artifact.mjs` (renderer), `workspace-analytics.mjs` ("Inspect every changed consulted read") |

## Sealed identity sequence (CR-R2)

The warm fold keys each read by `[operation, canonical payload]`. A key keeps the position its first read gave it,
even after a later read supersedes it; a grouped baseline read with `payload_aliases` appears once per key. The seal
hashes the reads in that key order. The selected projection used to fold only the sealed reads with payloads, so a
key first claimed by a superseded read moved, and valid receipts hashed differently (UNKNOWN, "identities
disagree"). `selected_records` now also folds, with their exact payloads, the earlier reads of the same turn that
share an operation with a sealed read (only those can share a key). They establish positions only; they never join
the consumed basis. `coverage.positional_reads` counts them, and they are real raw journal reads
(`raw_by_role.positional-read`): the cost grows with the turn's same-operation history. The stored checksum is unchanged and still decides: an
altered seal, a missing receipt, or a read ID carried by more than one journal row (now refused explicitly) stays
UNKNOWN.

## Changed-read recovery (CR-R1)

1. A refusal returns `consumed_read_recovery`. Its `changed_reads` are the first observations within the response
   bound; `changed_reads_omitted` counts the rest, and `changed_reads_page` is the handle to all of them. The banked
   failure row and its public history record carry the same handle.
2. `view=changed-reads` (native proposal read, `GET /authoring/proposal-preview`) observes EVERY consulted read of
   the candidate on every page, in the seal's consulted order (at most `PAGE_CONSULTED_MAX` 2048; a larger candidate
   is refused with the way forward). That observation is the page's **observation cut**: a digest of the project,
   turn, candidate version, consumed basis, consulted sequence, selected source revision and what was seen for each
   consulted read (current digest, `UNAVAILABLE`, or not replayed). The page lists a slice of the cut's changed
   reads: at most `limit` rows (default 8, 1..20), at most 6000 UTF-8 bytes of rows (`PAGE_BYTES`), each row at most
   4000 bytes (`ROW_BYTES`), and at most 12000 bytes for the whole response (`PAGE_RESPONSE_BYTES`, the exact HTTP
   body, reported as `response_bytes`; rows are trimmed to fit, never below one).
3. The cursor pins the cut and the position in its changed list. A continuation is served only when the page's own
   full observation gives the same cut; any moved evidence (already listed, not yet listed, disappeared) refuses it
   with "start again", so a complete traversal is exact for one stated cut and an invalidated one never reads as
   complete. Evidence that returns to the observed bytes gives the same cut again. A different candidate, version,
   record or turn, a forged or out-of-range position, or a cursor on another view is refused.
4. Each row has the observation, `read_detail` (the exact consulted receipt in author history), and `renew` (the
   exact read) when its payload is at most 1600 bytes; otherwise `payload_omitted` and the receipt is the way to the
   payload. Long selector lists and inspect reads give way to the receipt.
5. A candidate refused before observation (receipts, edition, source pins, siblings) returns `status: REFUSED`,
   `observation: null`, `complete: false`: nothing was observed and nothing is listed or complete.
6. Pages are diagnostics. Nothing is banked by the HTTP route; the native route banks only its own navigation read
   receipt. No witness is renewed, no baseline is banked, nothing is approved or applied. Running a row's `renew`
   read renews only that read's own witness for later candidates; the sealed candidate stays refused, and a fresh
   proposal on current evidence still refuses whatever is still changed.

### Work a page does (stated, not constant)

Every page prepares the selected projection and observes every consulted read, so its work depends on the
candidate, not on `limit`. The preparation runs under ONE invocation-local budget (`core.bodies.budget`, opened by
the proposal read owner before any carrier is projected and released before evidence is observed): at most
`PREPARATION_RECORDS` 4096 raw journal records, and at most `PREPARATION_BYTES` 16 MiB of raw line bytes and expanded
custody bodies together, at every depth. Each journal record is charged before it is opened; each custody body is
charged its declared size before a byte is read (a malformed size refuses; a body larger than its reference is
refused without being read whole: `BlobStore.get(max_bytes=)`; a nonlocal reference with no local copy is refused
before its unbounded Atlas fallback is called, while unbudgeted and observing reads keep that fallback), and the
selection is planned from index metadata and
refused when it cannot fit what remains. A sealed carrier names its own version, so the legacy projection is opened
only for a pre-instance carrier, inside the same budget. Refusals name the bound and the way forward.

`coverage` reports the actual work: `raw_records` and `raw_line_bytes` by role (`sealed-read`, `positional-read`,
`turn-basis`, `candidate-body`, `application`), `planned`, `custody_reads` and `custody_bytes` (bodies the shared
resolver actually read, nested ones included), `budget` (`records`, `bytes`, `spent`) and `evidence_replays`. A full
traversal costs one preparation and one full observation per page.

The historical DD failure stored five descriptors. Its 30 omitted observations are not retained facts and are not
reconstructed; a page over that candidate is a fresh observation with its own cut.

## Tests

`tests/test_consumed_read_order.py` (CR-R2), `tests/test_changed_read_pages.py` and
`tests/changed_read_pages_human.test.mjs` (CR-R1), with `tests/test_consumed_read_recovery.py` and
`tests/test_proposal_navigation.py`.
