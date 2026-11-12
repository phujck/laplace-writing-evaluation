#!/bin/bash
# Re-evaluate the deposited runs under this lane's allow lists, rebuild the retirement ledger,
# render the report from the banked measurements, and run the packet's scripted check on it.
set -u
E=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch
R=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch.md
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-11
cd "$W" || exit 3
# 1. the shipped-default run's allow list, every row CHECKED before it is granted
scripts/laplace-python tools/writing_verbs/make_bank_on_allow.py \
    --rows "$E/parity-bank-on/rows.jsonl" --parity "$E/parity-bank-on/parity.json" \
    --base "$E/allow.gate.json" --out "$E/allow.bank-on.json"
echo "allow builder exit $?"
scripts/laplace-python tools/writing_verbs/check_allow.py \
    --rows "$E/parity-bank-on/rows.jsonl" --allow "$E/allow.bank-on.json" \
    --out "$E/parity-bank-on/verdict_under_bank_on_allow.json"
# 2. the shim retirement ledger, from the deposited both-ways run
scripts/laplace-python tools/writing_verbs/shim_retirement.py \
    --rows "$E/parity-verb-door/rows.jsonl" --out "$E" > "$E/shim_retirement.out"
# 3. the report
scripts/laplace-python tools/writing_verbs/emit_report.py --evidence "$E" \
    --gate "$E/parity-dial-off" --bank "$E/parity-bank-on" \
    --verbdoor "$E/parity-verb-door" --shipped "$E/parity-shipped" --retire "$E" \
    --commit "$(git rev-parse --short HEAD)" --out "$R"
echo "=== SCRIPTED CHECK ==="
test -s "$R" && grep -q 'worktree' "$R" && grep -q 'parity' "$R" \
  && grep -c 'src/laplace/[a-z_/]*\.py:[0-9]' "$R"
echo "check exit $?"
