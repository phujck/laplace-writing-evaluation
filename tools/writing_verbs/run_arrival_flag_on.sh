#!/bin/bash
# The flag-ON arrival the jev lane never ran (its residual 2: "still no flag-ON run against a
# live server ... which is the synthesis stage's call").  Same acceptance script, same tree,
# the advisor's two seams ON with the lane's deposited heads, compared against the same HEAD
# baseline as the flag-OFF run.  What it measures: what the advisor COSTS in the live doors,
# in the characters the acceptance script actually receives, and whether it changes any
# compared number.  The gate itself is run flag-OFF, which is the default and what ships.
set -u
H=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/harness
J=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/jev-routing
E=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/synth-dispatch-jev
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-27
cd "$W" || exit 3
export LAPLACE_ROUTING_ADVISOR=1
export LAPLACE_ROUTING_HEAD_D1="$J/heads/d1.jsonl"
export LAPLACE_ROUTING_HEAD_D4="$J/heads/d4.jsonl"
echo "flag ON: LAPLACE_ROUTING_ADVISOR=$LAPLACE_ROUTING_ADVISOR"
echo "heads: $LAPLACE_ROUTING_HEAD_D1  $LAPLACE_ROUTING_HEAD_D4"
scripts/laplace-python "$H/arrival.py" --tree . \
    --out /tmp/claude-1000/recon-synth-dj/arrival-flag-on \
    --compare "$H/baseline/arrival_head.json"
echo "arrival exit $?"
cp /tmp/claude-1000/recon-synth-dj/arrival-flag-on/arrival.json "$E/arrival_flag_on.json"
