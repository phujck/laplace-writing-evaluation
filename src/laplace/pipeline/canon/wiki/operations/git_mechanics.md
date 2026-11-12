# Git Mechanics

* **Never commit a broken state.** A raw `git revert` can fail and leave the tree in a "reverting"
  state with unresolved conflict markers; a later commit then ships `<<<<<<< HEAD` into the
  manuscript. Run `git diff` before committing whenever a merge, rebase or revert has occurred, and
  clear a stuck state with the matching `--abort` (`git merge --abort`, `git rebase --abort`,
  `git revert --abort`) before staging anything.
* **The engine's own git layer is `src/laplace/core/versioning.py`** - pure-python, path-scoped
  stage/commit/revert. Prefer it to shelling out when the engine is the one committing.
* **Commits land at the judge's seam.** A dispatched worker does not commit; it returns, and the
  judge commits the accepted work in one scoped commit.
