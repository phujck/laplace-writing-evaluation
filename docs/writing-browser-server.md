# Browser Writing server: portable minimum

The portable entry point is the foreground browser server. It is separate from the
optional Linux GTK window and from provider/research process supervision.

## Minimum checkout-bound setup

Use CPython 3.12 for the tested setup and a checkout containing the project
registry, selected project records and profiles. Create an environment explicitly;
startup installs nothing:

macOS or Linux:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install ./atlas .
.venv/bin/python -m laplace.web.writing_server --root . --host 127.0.0.1 --port 8771
```

Windows PowerShell (environment activation is unnecessary):

```powershell
py -3.12 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install ./atlas .
& .\.venv\Scripts\python.exe -m laplace.web.writing_server --root . --host 127.0.0.1 --port 8771
```

Run these commands from the cloned Writing repository. Paths containing spaces
are supported. Open `http://127.0.0.1:8771/project?workspace=writing` in the browser.
The foreground process owns no GTK dependency and stops with its terminal. The entry binds
`LAPLACE_REPO_ROOT` and an isolated `LAPLACE_STATE`; state defaults to
`ROOT/.laplace-state`, never the author's shared home directory. `--state` chooses a
different explicit state root. Project/source/profile state belongs to the checkout,
not `site-packages` or a shared home directory.

The minimum Python dependencies come from `pyproject.toml`. Writing UI HTML, CSS,
JavaScript and vendored reader assets are package data. TeX, Poppler, Graphviz,
provider CLIs and numerical libraries are capability profiles: the corresponding
build, PDF, provider or research action must report unavailable when its executable or
account is absent. No startup path installs those tools.

## Full application on Windows and macOS

Use the existing [container profile](writing-container.md) with Docker Desktop in
Linux-container mode for the complete provider, TeX and supervised research
runtime. The host supplies the browser and the mounted project directory; providers
and research processes run inside Linux. Follow that guide's PowerShell or shell
workspace setup, use your own provider account, and inspect the release acceptance
record for the tested image identity. Native browser-server tests do not establish
native provider or research-process parity.

## Updating the managed Linux desktop workspace

This section applies to the full Laplace checkout's installed native desktop app.
Its service must be started and updated through its existing owner:

```sh
scripts/laplace-python -m laplace.desktop.writing_app --repo-root "$PWD" --update
scripts/laplace-python -m laplace.desktop.writing_app --repo-root "$PWD" --reconnect
```

Use the same `--state`, host and port as the installed launcher if customised.
The update waits for active work; it owns the PID/start-tick receipt and source
identity used by desktop reconnect. Replacing this process by launching
`laplace.web.scanner` directly leaves the receipt stale, even if HTTP health is green.
Deployment acceptance requires native `--reconnect` to report a running/reused
process whose receipt PID and start tick match health, followed by a loaded native
window. An unrelated listener must still be refused; never fabricate its receipt.
The foreground/browser and container entry points above have separate lifecycles.

## Platform boundary

The repository contains a three-OS smoke workflow for Python 3.12 on current GitHub
Linux, macOS and Windows runners. It checks installed UI assets, explicit checkout
selection and canonical project/authoring owners. The workflow also exercises concurrent atomic authoring saves, transient Windows
sharing conflicts and local startup without reverse DNS. Acceptance names the exact
commits and observed runner results; a workflow declaration alone is not a pass.

The following remain Linux/POSIX-only until separately ported and exercised:

- the GTK/WebKit native window (`runtime_profiles.toml` declares Linux system packages);
- managed service PID/start-tick ownership, `/proc` inspection and Unix signal handling;
- Codex/Claude process-group interruption;
- supervised numerical timeout/cancellation and live-run discovery;
- the repository's `/usr/bin/python3` `scripts/laplace-python` selector;
- TeX/PDF/native provider availability beyond the installed runner profile.

Use the foreground server for cross-platform evaluation. Do not claim native-window,
provider, build or supervised-research parity from the browser smoke. A release still
needs clean-checkout provider-account, build/export and bounded research rehearsals on
each platform it advertises.

## Evidence readers and companion links

Evidence navigation shares the existing research artifact owner and a read-only
dialog. Included TeX chapters resolve relative companion links against their
selected document root after source-closure membership is checked. Exported PDFs
use the existing verified source receipt. These paths are project-confined,
including after portable alias relocation. Unsupported URI schemes, encoded
traversal, missing receipts and missing targets are failures to inspect, not
reasons to disable the guard.

Argument-map and visual-index JSON have explicit schema adapters. Saved maps
display recorded identities; opening current concepts/results is a separate
labelled action. Other JSON is shown honestly without guessing from a project
name. Structured reads use `format=json` with offset/limit, verify identity on
each chunk and keep `download=1` available. Oversized plain responses refuse
rather than silently truncating. No reader action saves, reloads or discards the
manuscript editor's draft.

This behaviour belongs to a reviewed application update. Reinstall/rebuild and
restart the idle server through the normal deployment process before judging it.
The local candidate tests do not replace browser acceptance or the separately
recorded platform/provider checks.

The artifact route's optional `expected_sha256` is a full recorded byte identity,
not a freshness bypass. Matching media/download requests return the exact checked
bytes; mismatches return a conflict. Saved argument @section locators and recorded
result paths are resolved from the saved JSON only. The visual-index/1 reader
supports the documented current string-path/digest-map form and the retained
explicit output-object form, with visible refusal for ambiguous representations.
No saved blueprint or placed figure is rewritten by this compatibility adapter.

Structured readers are bounded to 2 MiB, 2,000 argument objects and 10,000 typed
relations; larger files retain text continuation and complete download. These are
viewer limits, not model context cutoffs. Companion files remain current project
files unless the saved link supplies an expected hash.

## Saved evidence format and identity contract


The canonical current `writing-system-architecture.visual-index/1` representation
mirrors the visual owner: `figures[].render.outputs` is an array of manuscript-relative
paths, and `render.output_digests` maps each exact path to SHA-256. The retained older
representation uses output objects with explicit `path, scope, format, sha256`.
The reader accepts those two representations only. Mixed entries, missing hashes,
contradictory formats/scopes or conflicting digests fail visibly with raw JSON
available. It does not fetch current figure state to fill gaps in a saved index.
The primary saved `figures` array is displayed; historical/integration metadata is
retained in the exact raw file rather than substituted by guessed keys.

`expected_sha256` on the existing artifact route guards text, PDF, image and
download bytes. Media/download responses reuse the bytes checked, avoiding a
second path read after verification. PDF companion requests retain the pinned
origin hash. A changed or missing pinned output is refused, never relabelled as
the old snapshot. An image failure offers a separately labelled current-file
choice. Inspected text downloads are pinned to the completed read's hash;
uninspected downloads are explicitly labelled current/unverified. NPZ metadata
previews do not have a pinned-byte viewing contract: use the hash-guarded download
or explicitly select the current inspector.

Artifact dialogs have individual accessible names and asynchronous status/error
announcements. Removable dialogs are not returned as cacheable inline panels to
research cards, so Close followed by another artifact action opens a fresh reader.
Real keyboard, focus restoration and assistive-technology acceptance remain part
of root's browser checks.

The corrected argument snapshot is `writing-system-architecture.argument-map/2`.
The reader explicitly supports this version and retained `argument-map/1`.
Both use the recorded `nodes`, typed `relations`, `chapters`,
`source_registry`, `mechanism_source` and result bindings. Version 2 additionally
carries richer recorded meanings and source/binding detail. Those saved values
do not license a current canonical fetch. Future unknown versions retain the
honest generic/raw fallback until their contract is implemented explicitly.

Provider cwd has a separate persistent per-checkout/state location in platform user data
(Linux `~/.local/share/laplace`, macOS `~/Library/Application Support/Laplace`, Windows
`%LOCALAPPDATA%/Laplace`). `--session-workspaces PATH` or `LAPLACE_SESSION_WORKSPACES`
selects it explicitly. Runtime state stays at its existing location; provider cwd must
have no project instructions in its ancestors. Container profiles persist cwd in their
own `session-workspaces` volume. Old images require a rebuilt release for this behavior.
