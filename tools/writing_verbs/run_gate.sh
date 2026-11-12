#!/bin/bash
# The lane's two oracle runs, in order, both against a separate checkout of 706a8204.
#   1. the GATE: the whole corpus, bank grain as the system banks it today, so parity is decidable.
#   2. the NEW GRAIN's cost: the arrival source with the shipped default, to measure exactly what
#      banking on every caller path costs against a tree that banks nothing there.
set -u
H=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/harness
E=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-11
B=/tmp/claude-1000/base-706a8204
cd "$W" || exit 3

echo "=== GATE: full corpus, LAPLACE_WRITING_BANK_EVERY_PATH=0 ==="
LAPLACE_WRITING_BANK_EVERY_PATH=0 scripts/laplace-python "$H/replay.py" --old "$B" --new . \
    --sources failures,reads,writes,arrival \
    --work /tmp/claude-1000/recon-altitude \
    --out "$E/parity-gate" \
    --allow "$E/allow.gate.json" \
    --netcache /tmp/claude-1000/recon-altitude/netcache \
    --reuse-fixture
echo "GATE exit $?"

echo "=== NEW GRAIN: arrival source, shipped default (dial on) ==="
scripts/laplace-python "$H/replay.py" --old "$B" --new . \
    --sources arrival \
    --work /tmp/claude-1000/recon-altitude \
    --out "$E/parity-bank-on" \
    --allow "$H/baseline/allow.head.json" \
    --netcache /tmp/claude-1000/recon-altitude/netcache \
    --reuse-fixture
echo "BANK exit $?"
