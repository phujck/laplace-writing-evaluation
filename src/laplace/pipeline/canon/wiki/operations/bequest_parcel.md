# Bequest parcel syntax and refusal at the cap

`laplace.engine.bequest.parse_parcel(text)` accepts one sentence per line:
`<sentence> -> descend: <node> | probe: <query>`. Both tails are optional;
`→` also works. Blank lines and `#` comments are ignored. A supplied probe
becomes `{"query": ..., "must_reach": [node]}` (an empty list without a node).
JSON arrays of line objects and objects with `lines` are also accepted.

The parser does not enforce the cap. `rotate(root, rows, dry_run=...)` enforces
`TEXT_CAP = 900` against the sentence texts joined by newlines, excluding
addresses and probe queries. Exactly 900 characters is allowed; 901 is refused
with `ok: false` and an overflow error before writing or archiving. Refusal
never trims the parcel. Empty parcels are also refused.

Example parcel file for the [close](canon://operations/sewup_contract):

```text
Check the close contract. -> descend: canon://operations/sewup_contract | probe: what flags does the sew-up take
```

Validate it with `/usr/bin/python3 scripts/sewup.py --only bequest --dry-run
--bequest-file /tmp/bequest.txt --no-bequest-prompt`.
Executable check: `laplace.pipeline.contracts_verify:bequest_parcel_contract`.
