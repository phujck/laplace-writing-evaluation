# Campaign gate exit-code contracts

The three scripts print a JSON verdict and return a process status. Exit zero
means the particular gate's mechanical condition held, with these distinct ceilings:

- `scripts/atlas_s1g2_gate.py`: zero for `DONE-PENDING-WALK`, one otherwise.
  Each generation-2 clause must return GREEN; missing tests and timeouts remain
  residuals. The script runs clause tests, so this is not a cheap help probe.
- `scripts/atlas_s1_gate.py`: zero for `DONE`, one otherwise. Closed founding
  resolutions and the sealed blueprint hive receipt must satisfy `evaluate`.
  The walk is separately `PENDING-NONBLOCKING`.
- `scripts/atlas_s0_gate.py`: zero for `DONE-PENDING-WALK`, one for `OPEN`.
  The latest inventory generation must contain rows including mathematical
  inheritance, and a judged S0 row must exist. Missing conditions are printed
  as residuals. The gate does not claim the author's walk.

Example invocation:

```sh
/usr/bin/python3 scripts/atlas_s0_gate.py
```

Executable check: `laplace.pipeline.contracts_verify:campaign_gate_contract`.
It drives green and red inputs through the exit paths in isolation; it does not
certify current campaign completion. These contracts are part of the
[operation gate registry](canon://operations/gate_registry).
