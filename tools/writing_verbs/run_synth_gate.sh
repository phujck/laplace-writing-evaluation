#!/bin/bash
# The dispatch x jev synthesis gate: one differential replay of the MERGED tree against a
# separate checkout of the campaign base 706a8204, in the configuration that would ship --
# the bank dial at its default (on) and the routing advisor flag UNSET, which is its default.
#
# The allow list is the altitude-dispatch lane's own allow.bank-on.json: the 2 causes two
# identical trees produce, the 15 creation-clock rows, and the 49 `homes` / 2 `bytes` rows the
# bank-every-path dial produces, each of which that lane's check_allow.py checked before it was
# granted.  The jev half of the merge adds nothing to it: its two seams are off unless
# LAPLACE_ROUTING_ADVISOR is set, which this run does not set.
set -u
H=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/harness
A=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch
E=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/synth-dispatch-jev
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-27
B=/tmp/claude-1000/base-identity-tokens-706a8204
cd "$W" || exit 3
unset LAPLACE_ROUTING_ADVISOR
echo "=== SYNTHESIS GATE RUN 4 (final commit, after the harness save-clock flake): full corpus, shipped default, advisor flag unset ==="
echo "merged commit: $(git rev-parse HEAD)"
scripts/laplace-python "$H/replay.py" --old "$B" --new . \
    --sources failures,reads,writes,arrival \
    --work /tmp/claude-1000/recon-synth-dj \
    --out "$E/parity-shipped-run4" \
    --allow "$A/allow.bank-on.json" \
    --netcache /tmp/claude-1000/recon-synth-dj/netcache
echo "GATE exit $?"
