# Codex dispatch: arguments, sandbox and result row

`scripts/dispatch_codex.py node goal` reconstructs the node and compiles an
admitted packet through the [dispatch compiler](canon://operations/briefs_and_dispatch).
`--goal-file PATH` replaces the goal with file contents. Options are `--worker`
(default `derive`), `--kind` (default `repository-file`), `--model` (otherwise
the configured model is recorded), `--sandbox`, `--out-dir` (default `.dispatch`),
`--content-budget`, `--timeout` (seconds, default 900), and `--output-schema PATH`
(passed to Codex when running). `--run` launches Codex; `--compile-only` is the
explicit default and is mutually exclusive with `--run`.

The sandbox defaults to `read-only`; the only other allowed value is
`workspace-write`. `danger-full-access` is rejected by argv parsing. The command
passes the selected sandbox to `codex exec -s`. `--carrier` can stamp
`codex-cli`, `claude-agent` or `compile-only`; codex-cli requires `--run`, while
the other carriers require its absence. Custody ON refuses this door with exit 2.

Under a timestamp/node/goal directory inside `--out-dir`, compilation writes
`packet.json`, `prompt.md` and `row.json`. The row has `record: codex-dispatch`,
an ID and timestamp, node/goal/worker/kind, executor/model/sandbox/carrier,
custody provenance, reconstruction digest/budget, admission and packet model,
output directory, prompt digest/length and status `COMPILED`. A refused packet
writes `packet.json` and a `REFUSED` row and exits 2. A run also captures
`codex.log` and, if produced, `return.md`, recording exit, duration, command and
return digest/length/path; status is `RETURNED` or `FAILED` and exit is 0 or 1.

Example compilation (writes the packet, launches no worker):

```sh
/usr/bin/python3 scripts/dispatch_codex.py src/laplace/pipeline/schema.py 'Inspect operation contracts' --compile-only --sandbox read-only
```

Executable check: `laplace.pipeline.contracts_verify:dispatch_codex_contract`.
