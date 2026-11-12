#!/bin/bash
# The brief's BOTH-WAYS replay: the whole recorded corpus through the old operation names and
# through writing_tools.request(), in two sandboxes of THIS tree, compared on class, home,
# homes and bytes. The dial is left at its shipped default: both sides are this tree, so both
# bank the same rows and the new grain is not a difference here.
set -u
E=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-11
cd "$W" || exit 3
exec env -u LAPLACE_WRITING_BANK_EVERY_PATH scripts/laplace-python \
    tools/writing_verbs/replay_verb_door.py \
    --sources failures,reads,writes,arrival \
    --work /tmp/claude-1000/recon-verb-door-full \
    --out "$E/parity-verb-door" \
    --netcache /tmp/claude-1000/recon-ad-bankon/netcache
