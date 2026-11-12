# Journal banking: signature, relations and write order

`laplace.core.records.journal.bank_row(store, row, *, act_id=None, edges=None, root=None)`
returns the row exactly as banked (the seam's `ts`, any caller `ts` kept as
`ts_claimed`, `edges` first-class). `store` is a repository-relative path; `root`
selects the root (default: the serving checkout, `laplace.core.checkout.repo_root`).
Omitting `act_id` binds an ambient act. The row receives the banking seam's
timestamp. Intent precedes execution: append the journal's `bank/begin` row,
durably append the target row, then append `bank/done`. A failed target append
must leave a begin without a done.

An edge has exactly `rel` and a nonempty, whitespace-free `target`. A target may
be store-qualified as `store.jsonl#row-id`. The closed `REL` vocabulary is
`grounds, amends, grades, supersedes, resolves, raised-by, cures, relays,
consumes, part-of`. Edges may come from the keyword argument or the row's
`edges` field, never both. Malformed edges raise `ValueError` before any append.

Example in an isolated temporary store:

```python
from tempfile import TemporaryDirectory
from pathlib import Path
from laplace.core.records.journal import bank_row
with TemporaryDirectory() as root:
    (Path(root) / "contract").mkdir()
    bank_row("example.jsonl", {"id": "example"}, act_id="contract-example",
             edges=[{"rel": "part-of", "target": "parent"}], root=root)
```

The journal directory and the target's parent directory must already exist.

This is the durable write seam used by the
[close operator](canon://operations/sewup_contract).
Executable check: `laplace.pipeline.contracts_verify:journal_bank_row_contract`.
