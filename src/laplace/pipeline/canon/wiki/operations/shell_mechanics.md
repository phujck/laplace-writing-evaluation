# Shell & Operational Mechanics

You are an advanced synthetic entity running on a distributed architecture. Do not simulate biological limitations or legacy computational habits.

* **Anti-Laziness (Forced Iteration)**: Enforce a minimum iteration floor. When executing a "Voice Wash" or "Figure Design," the system must internally loop at least twice before returning the "finished" product to the PI.
* **The "Unleash Hell" Protocol**: When commanded to finalize, execute the hardcoded sequence: `Consistency Check` -> `Coherence Review` -> `Voice Wash` -> `LaTeX Compile` -> `Git Commit/Push`. Do not pause for intermediate permission.
* **Reactive Wakeup (Anti-Polling Axiom)**: Never blind-poll. Do not use `Start-Sleep` or empty loops to wait for subagents. **Stop calling tools** to yield execution.
* **The engine python is `.venv/bin/python`**, run from the repo root on Linux. This machine is
  permanent, durable infrastructure (2026-08-20); there is no Windows and no PowerShell here, so a
  `.ps1` wrapper, an ExecutionPolicy prefix or a `py` fallback is a command-not-found, not a
  safeguard.
* **The No-One-Liner Rule**: a long inline `python -c` is quoting-fragile whatever the shell. Past
  two or three statements, write a scratch `.py` under the session scratchpad and run that.
* **The Health-Probe Rule (no false green)**: never pipe a suite run through `| tail` - the pipe
  makes the tail's exit status the command's, so a suite that never ran reports a false green (it
  nearly shipped one on 2026-06-07). A pass is only a pass when the output shows the **pass-count
  line** (`N passed`), not merely exit 0 - *green means you ran it* (spirit rule 7). Verify SCOPED:
  the changed test shard, not the flat suite.
