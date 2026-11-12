#!/bin/bash
# One differential replay of this worktree against a base checkout, through the campaign's
# own oracle.  $1 = out dir, $2 = allow file, $3 = sources, $4 = value of the bank dial.
set -u
H=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/harness
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-11
B=/tmp/claude-1000/base-706a8204
cd "$W" || exit 3
export LAPLACE_WRITING_BANK_EVERY_PATH="$4"
exec scripts/laplace-python "$H/replay.py" --old "$B" --new . \
    --sources "$3" \
    --work "/tmp/claude-1000/recon-altitude$5" \
    --out "$1" \
    --allow "$2" \
    --netcache /tmp/claude-1000/recon-altitude/netcache
