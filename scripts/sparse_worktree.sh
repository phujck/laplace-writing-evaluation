#!/bin/bash
# A SPARSE worktree for a campaign lane (moved here from evidence/WRITING_CONSOLIDATION_2026-10-03/
# on 2026-10-04: a tool belongs with the tools, and it was untracked where it sat): bash scripts/sparse_worktree.sh <path> <commit-or-branch> [new-branch] [lean]
# A full checkout of this repository is 3.1 GB (archive, papers, vectors, models); a lane needs ~1/6 of it.
# The cone below is what the oracle and the writing app read from a tree: the code, the tests, the tools,
# the profiles and friction ledgers the fixture copies, the two fixture projects, the contract ledgers.
# Branches and commits are unaffected by sparseness: commit as usual. Remove the worktree when done:
#   git -C /home/phujck/VScodeProjects/laplace worktree remove --force <path>
set -eu
ROOT=/home/phujck/VScodeProjects/laplace
DEST="$1"; HEAD="$2"; BRANCH="${3:-}"
cd "$ROOT"
if [ -n "$BRANCH" ]; then git worktree add --no-checkout -b "$BRANCH" "$DEST" "$HEAD" >/dev/null
else git worktree add --no-checkout --detach "$DEST" "$HEAD" >/dev/null; fi
# A fourth argument "lean" checks out only what a frontend or code lane runs: the code, the tests, the tools and
# the profiles (about 90 MB instead of 1.1 GB). Cone mode always adds every root-level file, and those are engine
# state (vectors, indexes, meters: about 350 MB), so lean uses plain patterns instead. Use lean unless the lane
# needs the fixture projects or the contract ledgers.
if [ "${4:-}" = "lean" ]; then
  git -C "$DEST" sparse-checkout init --no-cone >/dev/null
  git -C "$DEST" sparse-checkout set --no-cone '/src/' '/tests/' '/scripts/' '/tools/' '/profiles/' '/docs/' '/node_modules/' '/.claude/workflows/' \
    '/pyproject.toml' '/package.json' '/runtime_profiles.toml' '/.gitignore' >/dev/null
else
git -C "$DEST" sparse-checkout init --cone >/dev/null
git -C "$DEST" sparse-checkout set src tests scripts tools docs profiles corpus_friction contract atlas \
  "synthetics papers/synthetics-foundations" "synthetics papers/writing-system-friction-report" \
  "synthetics papers/writing-app-understanding" >/dev/null
fi
git -C "$DEST" checkout -q "$HEAD" 2>/dev/null || git -C "$DEST" checkout -q
[ -n "$BRANCH" ] && git -C "$DEST" checkout -q "$BRANCH"
echo "$DEST $(git -C "$DEST" log -1 --format=%h) $(du -sh "$DEST" 2>/dev/null | cut -f1) branch=$(git -C "$DEST" branch --show-current)"
