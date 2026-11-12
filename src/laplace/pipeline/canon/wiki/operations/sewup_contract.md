# Sew-up: authored checkpoint and publication

Use the declared runtime entry:

```sh
scripts/laplace-python scripts/sewup.py --authored-text "What changed; evidence; next action."
```

The default `CORE_STEPS` is `handoff, reembed`: first preserve the authored
checkpoint, then publish it. An empty authored checkpoint fails; supply
`--authored-text TEXT` (also `--authored-text=TEXT`) or retain the filled authored
section of the dated handoff. A failed handoff makes the default publication
step `UNPAYABLE`. Successful publication requires a zero producer exit, current
checkpoint hashes and matching publication artifact/input hashes. Only then does
the close advance `contract/close_receipt.json` and report `PUBLISHED`.
A failed publication retains checkpoint/failure evidence without advancing that
receipt. Independent successor recovery remains `UNVERIFIED`; publication does
not establish that a later session consumed it. The close does not commit, push,
launch a provider session or transition custody.

`--only step[,step]` (also `--only=...`) selects a diagnostic, not a default close.
Selection runs in registry order, regardless of the order typed. Repeated
`--only` uses the last selection; bare `--only` selects none. Unknown selected
step names return 2. `--all-steps` selects the complete registry unless an
explicit `--only` controls selection. The registry order is `render, suite,
canon, contracts, probes, threads, battery, poolfold, census, bench, custody,
git_state, wants, bequest, handoff, reembed`.

The suite, thread probes, custody and other diagnostics are not default gates
or an authored tail. `--with-suite` adds the suite to the default close;
`--impacted` adds it in delta mode; `--full` (alias `--full-suite`) adds the
whole-suite mode. A selected suite otherwise uses its floor unless
`LAPLACE_SUITE_FULL=1` selects full mode. These flags do not force a full spectral
upfold. `--full-metric` requests metric refitting during publication and does not
select the suite. Non-interrupting diagnostic failures do not prevent writing the
authored checkpoint or attempting its publication, but they still make the
overall result non-green. Each executed step retains its supervised process/resource budget.

`--no-suite` and `--no-embed` explicitly skip those selected steps as
`UNPAYABLE`; skipping publication cannot complete a default close.
`--close-red REASON` (also `--close-red=REASON`) records an operator explanation only: it
neither banks override debt nor changes a failing gate into a pass. Exit is zero
only for a green executed result, 1 for a non-green result, or 130 for an
interrupted run.

`--dry-run` previews the default handoff and publication without performing the
upfold or banking the close receipt. It is not a blanket no-work switch for
explicit diagnostics: a selected suite still runs, with pytest caching and suite
banking disabled. `--bequest-file PATH` (also equals spelling) supplies the parcel
for the separately selected bequest step; `--no-bequest-prompt` disables its
interactive prompt. `-h` / `--help` prints help before runtime admission or close
work.

For example, this explicitly runs the
[operation contracts](canon://operations/gate_registry) diagnostic:

```sh
scripts/laplace-python scripts/sewup.py --only contracts
```

The `reembed` step consumes the producer's publication result. A failed step
reports its retained nonempty producer `reason` directly as `detail`, including
a source-frontier refusal even after successful prior-publication restoration.
If no producer reason is available, it reports the existing publication/hash
diagnostic with the output tail. Restoration is not publication success.
The producer's publication receipt remains attached to the step.

The finite `tests/check_close_publication_cause.py` evaluator checks that cause
propagation with isolated heavy/runtime/transport seams. The existing
`laplace.pipeline.contracts_verify:sewup_ready` runs the render diagnostic only.
It regenerates projections and records a diagnostic act; it is not a no-write
probe and does not establish a completed authored checkpoint or publication.
