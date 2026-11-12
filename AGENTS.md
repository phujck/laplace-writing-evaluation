# Repository instructions

Read README.md and release/README.md first. This is a standalone evaluation checkout. Work only in this checkout and explicitly selected local state. Do not seek the author's home directory, original repository, private material, credentials or excluded history.

Use a fresh Python 3.12 environment and the documented foreground browser server. Do not install packages globally, launch model jobs, or use paid APIs unless the user asks. The repository does not require personal Eigen wake/startup hooks. Runtime state is local `.laplace-state`; provider authentication remains outside the repository.

For code changes, follow the relevant existing owner and run focused tests. `src/laplace` is the application; `src/atlas` is the separately installed Atlas package. JavaScript and vendored assets are in `src/laplace/web/static_shared`. Papers and figure inputs are listed in release/selection-manifest.json. Preserve manuscript source and data provenance; do not invent experimental results or silently substitute newer code for historical evidence.

For a clean-install exercise, use only this repository and the task. Record the interpreter, exact commands and actual failures. Do not borrow installed code or fixtures from an author checkout. Do not interpret a missing optional capability as evidence that its result was reproduced.

Keep private material excluded and preserve third-party notices. Do not replace rights terms with an assumed open-source licence. Do not alter or remove user drafts, saved sessions or runtime state as cleanup.
