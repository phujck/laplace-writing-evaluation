#!/bin/bash
# WHAT THE SHIPPED CONFIGURATION COSTS THE ORACLE, over the WHOLE corpus.
# The dial is left at its default (writing_verbs.bank_every_path, src/laplace/writing_verbs.py:1447-1449
# -- `return True if raw is None else ...`), which is the tree that ships, so the new side banks a
# writing-tool row on caller paths where the base tree banks nothing. That is a `homes` difference on
# every such row by construction. The allow list is the LANE's own file, which declares those rows and
# names the cause, so this run is the gate on the configuration that ships and not a separate
# measurement beside it.
#   --old is a checkout of 706a82047ae9; --new is this worktree.
set -u
H=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/harness
E=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-11
B=${BASE_TREE:-/tmp/claude-1000/judge-ad/base}
ALLOW=${ALLOW:-$E/allow.gate.json}
OUT=${OUT:-$E/parity-bank-on}
WORK=${WORK:-/tmp/claude-1000/recon-ad-bankon}
cd "$W" || exit 3
exec env -u LAPLACE_WRITING_BANK_EVERY_PATH scripts/laplace-python "$H/replay.py" \
    --old "$B" --new . \
    --sources failures,reads,writes,arrival \
    --work "$WORK" \
    --out "$OUT" \
    --allow "$ALLOW" \
    --netcache "$WORK/netcache" ${REUSE:- }
