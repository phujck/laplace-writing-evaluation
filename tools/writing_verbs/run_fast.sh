#!/bin/bash
# The same gate with the three heaviest operations skipped, which `parity.json` records so a
# thin run cannot pass as a full one. Run as insurance when the machine is carrying several
# lanes' replays at once; the full run is the one that counts.
set -u
H=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/harness
E=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-11
B=/tmp/claude-1000/base-706a8204
cd "$W" || exit 3
export LAPLACE_WRITING_BANK_EVERY_PATH=0
exec scripts/laplace-python "$H/replay.py" --old "$B" --new . \
    --sources failures,reads,writes,arrival \
    --skip-operations export_pdf,build,experiment_run,research_reconcile \
    --work /tmp/claude-1000/recon-altitude-fast \
    --out "$E/parity-gate-fast" \
    --allow "$H/baseline/allow.head.json" \
    --netcache /tmp/claude-1000/netcache-copy
