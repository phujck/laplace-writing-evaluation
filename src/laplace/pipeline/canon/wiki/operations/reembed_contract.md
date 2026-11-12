# Reembed: publication, work flags and recovery

Use the declared runtime entry, `scripts/laplace-python scripts/reembed.py`.
With no work flag, the producer uses incremental reuse; structural triggers can
still select full spectral work. `--full` forces a complete spectral upfold
without incremental reuse. `--full-metric` requests metric initialization or a
full refit; it is separate from `--full`. The options can be combined.
`-h` / `--help` returns zero before runtime admission or opening an act; an
unsupported argument returns 2 before preparing or depositing publication bytes.

Any nonempty `LAPLACE_NO_SPECTRAL` disables the full spectral branch; incremental
work still runs. `LAPLACE_REQUIRE_GPU=1` (also `true`, `yes`, `on`) makes an
undialed device fallback a refusal. Explicit device opt-outs remain recorded
choices. Capability failures must not be mistaken for a completed deposit.

The deposit journals `upfold, write, index, wire, embed, metric_distill, publish`
in that order. It writes the graded self cache `.self_graded.json`, skeleton
`SELF_GRADED_INDEX.md`, the meaning-tree fold and receipts, the shard index, and
`.self_embeddings.json`. Wire work updates its ledgers/projections when proposals
exist; an empty frontier skips it. Metric work is gated by the embedding result
and the explicit refit choice. `.reembed_timing.jsonl` retains counts, device,
trigger, timing and metric verdicts. Publication prepares reader projections,
backs up the prior publication and emits its exact artifact/input receipt.
These are writes, not a read-only probe.

Example invocation (performs a deposit):

```sh
LAPLACE_REQUIRE_GPU=1 scripts/laplace-python scripts/reembed.py
```

A nonzero deposit result restores the prior publication. Its
`LAPLACE_PUBLICATION=` result retains the exact nonempty producer `reason` and
available `act_id` and `input_signature`. It remains `published: false` with
empty `artifacts`. Successful restoration is reported separately as
`restoration: {restored: true}`, not as a replacement cause or newly published
bytes. Without a producer reason, the result explicitly says so. Exceptions
remain exceptions, and a failed restoration retains its failure and backup path.

For explicit recovery, `--restore-publication PATH` restores a preserved backup
without running a deposit. Use the exact backup path reported by the producer.
The result reports restored artifacts, uncovered artifacts and whether the
complete group was restored; restoration alone is not a new publication or a
successful close. This recovery mode takes exactly those two arguments.

The [close](canon://operations/sewup_contract) selects this publication door by
default after its authored checkpoint. The finite cause-propagation evaluator is
`tests/check_close_publication_cause.py`; its compiled function checks isolate
heavy deposit, runtime and snapshot/restore seams, so they do not prove a real
publication. `laplace.pipeline.contracts_verify:reembed_contract` checks the
no-run argv door, exact journal phase order, staged producer/publication wiring
and device refusal without running a deposit. Its static checks do not establish
a real publication or rollback.
