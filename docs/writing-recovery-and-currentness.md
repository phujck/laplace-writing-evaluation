# Recovery and currentness: inspect, reimport, and keep documentation true to source

Three bounded routes, each served by an owner that already exists. Commands are
exact; trust boundaries are stated with each.

## 1. Inspect an export when its kernel cannot start

`scripts/inspect_writing_export.py` and the byte layer it shares with the full
verifier (`scripts/writing_export_bytes.py`) use the standard library only. They
never import `laplace` or `atlas`, so they run when the installed packages are
broken, absent or refuse to import, and they write nothing under the inspected
root: bytecode writing is disabled before the first helper loads, so a cold run
from a fresh directory leaves the tree byte for byte as it found it.

**One admission boundary.** Every candidate coordinate, fixed (the two manifests,
the registry, the repository configuration, the package declarations, the journal,
the Work ledger) or declared (each file the manifest lists), is admitted the same
way before it is opened: no `..`, no symbolic link in any component, resolved
inside the root, a regular file. A refused coordinate is named under `refused` and
never read. Shapes are checked before consumption: an unsupported schema, a
missing required field, a scalar where a list belongs or a row without a string
id is a bounded malformed fact, never a traceback.

**One verdict.** Status and exit agree about every requested condition:

| Status | Exit | Meaning |
|---|---|---|
| `ACCEPTED_IDENTITY_AND_BYTES` | 0 | an external anchor was supplied, usable, and matches; the declared bytes are consistent |
| `DECLARED_BYTES_CONSISTENT_UNANCHORED` | 0 | no anchor was requested; the candidate's own claims are self-consistent. This is description, not acceptance |
| `DISCREPANCY` | 2 | drift, a source-manifest identity mismatch, a refused coordinate, missing workspace inputs, an unknown journal kind, or any requested anchor or package condition that failed |
| `MALFORMED` | 3 | the export manifest is absent, not JSON, not an object or of an unsupported shape |

A requested anchor that is missing, unreadable, a symbolic link, malformed, not a
supported manifest, inside the candidate, or in conflict with a second anchor is
`DISCREPANCY`; it never degrades to the unanchored outcome. Admission proves a
path's shape and type, not that its bytes can be read: an admitted file whose open,
hash or parse fails is a typed problem (`unreadable: PermissionError`, `malformed:
…`) that reaches the same verdict. Container packages keep their own tool,
`scripts/writing_container_package.py`; this inspector does not compose with it and
refuses `--package` as `UNSUPPORTED_OPTION` (exit 2) without opening anything.

**The trusted checker must come from outside the candidate.** A candidate can
replace the inspector it ships, so the program that judges it is taken from the
accepted source commit, pinned, and compared before it runs:

```sh
# the two checker files from the accepted commit, placed outside the candidate
mkdir -p /trusted/laplace-checker && cd /trusted/laplace-checker
git -C <accepted source checkout> show <accepted commit>:scripts/inspect_writing_export.py > inspect_writing_export.py
git -C <accepted source checkout> show <accepted commit>:scripts/writing_export_bytes.py   > writing_export_bytes.py
sha256sum *.py          # compare with the pins recorded in the accepted commit's acceptance record

# the inspection, anchored by the accepted export manifest identity from the same record
python /trusted/laplace-checker/inspect_writing_export.py --root /path/to/candidate \
    --accepted-manifest-sha256 sha256:<accepted export manifest identity> \
    [--accepted-manifest /trusted/accepted/export-manifest.json]
```

The report's `checker` block hashes the two files that actually ran and says whether
they ran from inside or outside the candidate; a checker file whose identity cannot
be read is itself a discrepancy. Those hashes are coordinates for
your comparison with the pins you hold; a program cannot certify itself, and the
inspector does not pretend to. Run from inside the candidate
(`python scripts/inspect_writing_export.py --root .`) it reports the candidate's
own declared consistency only; an anchor requested from a candidate-local checker
is refused. A copy of the manifest taken from the same candidate is not external
authority and is refused as an anchor.

The full verifier, `scripts/verify_writing_evaluation.py --root`, shares the byte
layer and the admission boundary, needs a working kernel and checks the
application's own semantics (registry and source closure, body custody, document
links); it is the second step, not a replacement.

Witnesses: `tests/test_writing_export_inspection.py` (an external checker over a
real synthetic export with an unimportable kernel; drift; a self-rewritten
manifest; conflicting, missing, malformed, unreadable, inside-candidate and
symlinked anchors; the unsupported package option refused without an open; the
candidate-local checker; symlinked fixed coordinates whose targets are FIFOs, so
one outside open would hang; unreadable admitted files and an unreadable manifest;
wrong-shaped metadata; cold invocations that write no bytecode).

## 2. Recover selected state faithfully

An export is the reimport. `scripts/export_writing_evaluation.py` copies the selected
original rows and bodies byte for byte and appends one explicit
`writing-session-import` boundary per session; the records fold
(`src/laplace/writing/records/_fold.py`) then detaches the native binding
(`native_id` becomes null, `imported_history` names the source manifest) so the
next turn starts a new provider conversation. Work rows, review phases, their pins
and their currentness travel unchanged; the original source is never written.

In the reimported workspace, an application interrupted after its bytes moved and
before its finish is replayed as the same application: the existing owner answers
`reused`, the same id and `POSTIMAGE`, and the journal keeps one application row.

Witness: `tests/test_writing_reimport_recovery.py`. The project owner, the Work
review owner and the saved-source application are the only owners it drives.

**Root's actual check stays synthetic**: export a synthetic project with history
into a fresh workspace and read its sessions as detached; a real author project or
its history is never copied for this check.

## 3. Local documentation currentness and the bounded reflexive review

A documentation page and the module it describes are declared together as the
exact inputs of one review obligation (`review_obligations[].inputs`). The Work
review owner (`src/laplace/work/project_work_review.py`) pins every input at review
time and reads currentness per obligation:

- the module changes: that obligation's review is `STALE`, naming the changed input;
  an unrelated obligation stays `CURRENT`;
- a new independent review of the changed scope restores only that scope;
- completion stays refused while any required obligation is unsatisfied.

There is no timestamp, no global ledger freshness and no stored parallel status;
the facet is read from the exact pins each time.

**The reflexive case, stated exactly.** The evaluator is the real, unchanged,
accepted review owner, `src/laplace/work/project_work_review.py`, pinned by its sha256
(`EVALUATOR_PIN` in the witness) and shown to lie outside the synthetic candidate.
The candidate's `kernel/acceptance.py` is an input text the evaluator pins and
judges; it is never imported or executed. Under that unchanged accepted evaluator:
the candidate's own session can record an acceptance, but its independence is
`SELF` and it never satisfies the obligation; an evaluator pinned outside the
candidate (another session, or an author-attested external identity with public
evidence) satisfies it; when the candidate edits the rule again, that acceptance is
`STALE`, the candidate's re-review is `SELF` again, and an external identity
claimed through a native turn stays unverified. Actor attestation is identity
evidence about who reviewed, not a proof about which program ran. The witness says
nothing about an arbitrarily modified evaluator enforcing rules on itself; a
change to the evaluator file is a change to the pin and must be re-accepted.

Witness: `tests/test_source_documentation_currentness.py`. The lifecycle itself is
described in `docs/writing-work-review-lifecycle.md`.
