#!/bin/bash
# THE PACKET'S SCRIPTED CHECK, exactly as the brief states it, as one file so it can be re-run.
#
#   bash tools/writing_verbs/editor_doors_check.sh <tree>
#
# The oracle, then the word `parity` in its verdict, then the report's own check. The oracle
# script is the campaign's shared one and four lanes run it at once; it was rewritten underneath
# this lane's run once already (bash reads a script by byte offset, so the interpreter landed
# mid-comment and died), so this takes a byte-identical SNAPSHOT first and runs that. The md5 of
# both is printed, so the snapshot is never a different gate.
set -u
TREE="${1:-$(pwd)}"
E=/home/phujck/VScodeProjects/laplace/evidence/WRITING_CONSOLIDATION_2026-10-03
SNAP=/tmp/claude-1000/consol-editor-doors/oracle-snapshot.sh
mkdir -p "$(dirname "$SNAP")"
cp "$E/wave1/oracle.sh" "$SNAP"
md5sum "$E/wave1/oracle.sh" "$SNAP"
bash "$SNAP" "$TREE" editor-doors \
  && grep -q 'parity' "$E/wave1/editor-doors/oracle/verdict.txt" \
  && python3 "$E/check.py" "$E/wave1/editor-doors.md" --min-cites 14 \
       --heading 'door' --heading 'comment' --heading 'browser' --heading 'oracle'
