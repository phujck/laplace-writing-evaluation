#!/bin/bash
# The scripted arrival acceptance for this worktree, compared with the banked HEAD baseline.
set -u
H=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/harness
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-11
cd "$W" || exit 3
exec scripts/laplace-python "$H/arrival.py" --tree . --out "$1" \
    --compare "$H/baseline/arrival_head.json"
