# Where Laplace lives

This is the one entry for where each part of Laplace is, who owns it, and how it is set up, launched and updated.
The authoritative source is the code and declarations named on each line: `src/laplace/system/description.json`
(checked by `scripts/laplace-python -m laplace.system check`) for source ownership, `runtime_profiles.toml` for the
runtime, and the owner modules for state. This page points at them; it decides nothing itself.

## Choose the entry for your installation

The absolute paths and CPython 3.14.7 selection below describe the development
installation on the author's machine. They are not prerequisites for a downloaded
Writing package. In an extracted package, use [agent startup](writing-agent-start.md):
its tested portable profile is Python 3.12 with both local distributions installed,
and its foreground server takes that package's own `--root`. The prebuilt Linux
image contains its installed implementation under `/opt/laplace`; the mounted
workspace supplies registry, projects and writable data. Its package manifest
identifies the exact image. No author checkout, worktree, private state or metric
cache is needed for that route.

For direct installed Python SDK use, pass the data workspace explicitly as `root`
on every call. Package resources come from the imported installation. Root selection
and source/installed module identity are different facts; [owner discovery](owner-discovery.md)
gives the executable example.

The managed Writing launcher can also select an **existing data workspace**
separately from its application code. `--repo-root` still names the executable
code/runtime entrance; `--workspace-root` names data with `registry_projects.json`
and `profiles/`. The data workspace supplies no Python, native script or executable
runtime. With no new option, the existing co-located launch stays unchanged.

```sh
/path/to/code/scripts/laplace-python -m laplace.desktop.writing_app --repo-root /path/to/code --workspace-root /path/to/data
```

In this explicit separate mode, `desktop.managed_homes.resolve` supplies the one
selection used by the managed service, native viewer and installer:

| Meaning | Separate-mode default or option |
|---|---|
| Application code/runtime | `--repo-root`; scripts, imported package and bundled frontend come from this entrance |
| Mutable data and workspace profiles | `--workspace-root`; existing domain owners retain registry, project, Work, artifact/material and history identities |
| Managed process receipt **file** | `--state FILE`, or a workspace-qualified `workspaces/<digest>/writing-app.json` under the existing platform receipt home |
| Engine state **directory** | `--engine-state DIR`, or `<workspace>/.laplace-state` |
| Provider session cwd **directory** | `--session-workspaces DIR`, or the platform session-workspace location qualified by workspace and engine state |
| Native profile and window state | Workspace/receipt-qualified profile under the receipt's parent; geometry/URI in that profile's `window.json` |

Separate mode does not borrow `LAPLACE_STATE` or `LAPLACE_SESSION_WORKSPACES` from
another running workspace. Engine/session overrides require `--workspace-root`.
The receipt file is never an engine directory. Status and health report effective
locations; executable source/runtime/frontend currentness and consumed workspace
profiles/configuration have separate bases.

For the installed desktop entry, select the same homes explicitly:

```sh
/path/to/code/scripts/laplace-python /path/to/code/scripts/install_writing_app.py --install --checkout /path/to/code --workspace-root /path/to/data
```

This writes the existing per-user launcher entry for that selection and records
all effective locations in its printed plan. It does not install a provider,
create a workspace, copy projects, export custody or migrate author data.

Use the same selection for status, reconnect and an explicit idle update. Passive
reconnect preserves a healthy older service. A source update within the selected
code entrance preserves the data workspace; its new source/runtime is validated
before an owned idle service is retired. Source-location changes require stopping
and closing the old viewer, then reopening explicitly. A separate-mode primary
viewer holds its qualified profile while open; an incompatible viewer cannot
reuse that busy profile. Activation with the same effective homes and requested
loopback endpoint presents the existing window. Registration includes code,
workspace, receipt, engine/session homes and endpoint; profile storage remains
workspace/receipt-qualified.
Unsent text is not silently reloaded or copied to another profile. Busy, foreign or
unattributed listeners/windows remain preserved with a refusal.

A [complete selected project-data handover](project-data-handover.md) can now plan and
export one source-optional project into a fresh workspace. Occupied merge, automatic
external alias rebinding and live author migration remain separate operations;
selecting existing data proves none of those migrations. The native path still requires the installed GTK/WebKit
runtime; command/controller checks alone are not desktop or platform parity.

## Source

| What | Where | Status |
|---|---|---|
| Live checkout | `/home/phujck/VScodeProjects/laplace` | The source the managed Writing app serves. Changes reach it only by the coordinator's promotion of an accepted commit. |
| Development worktrees | `~/.local/share/laplace/worktrees/<name>` (git worktrees of the live repository) | Where source changes are made and checked before promotion. |
| Published Writing distribution | `/home/phujck/VScodeProjects/laplace-writing` | A curated released copy, regenerated from the manifest (`scripts/export_writing_evaluation.py`); never edited by hand. |

One source tree, `src/`, holds both libraries:

| Distribution | Declaration | Package | Contents |
|---|---|---|---|
| `laplace-engine` | `pyproject.toml` | `src/laplace` | `core/` (identity, admission, runtime, records), `system/` (the description), the domains `writing/` (authoring), `manuscript/`, `projects/`, `work/`, `research/`, `representation/`, `pipeline/`, `engine/`, and the adapters `native/` (the project tool gateway), `web/` (HTTP servers, pages and `web/static_shared/` assets) and `desktop/` (the managed app, window and deploy units). CLI scripts live in `scripts/` and `tools/`, explanations in `docs/`. |
| `atlas` | `atlas/pyproject.toml` | `src/atlas` | The representation library: Atlas stores, routing and the body store. It imports nothing from Laplace. |

The package resources that ship are listed in `pyproject.toml` (`[tool.setuptools.package-data]`): the system
description, `web/*.html`, `web/static_shared/**`, `pipeline/*.json`, `pipeline/canon/**`,
`pipeline/writing_organ/*.json` and `engine/AUTONOMY_BACKLOG.md`. Code finds them through
`laplace.core.checkout.package_root()`, so an installed copy reads its own resources rather than a checkout's.

## Runtime and dependencies

- **Selected interpreter.** `runtime_profiles.toml` `[lifecycle] python`, resolved by `laplace.core.runtime.lifecycle_python`:
  `~/.local/share/laplace/runtime/python/current/bin/python3.14` (CPython 3.14.7). `LAPLACE_PYTHON` overrides it explicitly
  (the bootstrap override for a cold checkout or a fixture). Nothing is installed at startup.
- **Launcher.** `scripts/laplace-python` (`scripts/laplace_python.py`) runs this checkout's `src/` on the selected
  interpreter, isolated (`-I`, no user site).
- **Dependencies.** Only the packages installed in the selected interpreter (`[capabilities]` lists the profiles).
- **Compatibility aliases.** The original build moved to the owned home on 21 October 2026. Both
  `/home/phujck/VScodeProjects/eigenengine-v2/runtime/python/current` and its old concrete
  `cpython-3.14.7-linux-x86_64-gnu` spelling now resolve to that one build. Existing saved consumers and both
  installed-script shebang spellings still work; there is no second physical runtime. The normal launcher uses
  the owned home without an override; `previous_python` records the old compatibility spelling.

### Runtime migration and rollback (coordinator, quiet)

The move above is complete. This is the guarded maintenance recipe used for it, including rollback.

One build moves; both spellings that consumers already hold keep working as aliases of it. Old `current` is a
relative link to the concrete build directory, and installed scripts carry shebangs naming either
`.../python/current/bin/python3.14` or `.../python/cpython-3.14.7-linux-x86_64-gnu/bin/python3.14`.

Let `OLD=/home/phujck/VScodeProjects/eigenengine-v2/runtime/python`, `NEW=~/.local/share/laplace/runtime/python`,
`BUILD=cpython-3.14.7-linux-x86_64-gnu`.

Guards, all required before step 1:
- quiet: the managed app is stopped, no turn or provider child is active, and no process runs from `$OLD/$BUILD`
  (`fuser`/`lsof` on `$OLD/$BUILD/bin/python3.14` finds nothing);
- source identity: `$OLD/$BUILD` is a real directory (not a link), `$OLD/current` is the link `$BUILD`, and the sha256 of
  `$OLD/$BUILD/bin/python3.14` and its `-c 'import sys; print(sys.version)'` output are recorded;
- destination free: neither `$NEW/$BUILD` nor `$NEW/current` exists.

1. `mkdir -p $NEW`, then `mv $OLD/$BUILD $NEW/$BUILD` (same filesystem: a rename, so one physical build).
2. `ln -s $BUILD $NEW/current` (the owned selection).
3. `ln -s $NEW/$BUILD $OLD/$BUILD` (the concrete old spelling, now an alias). `$OLD/current` is left untouched: its
   relative target `$BUILD` now resolves through that alias, so the old `current` spelling reaches the same build.
4. Verify: `$OLD/current/bin/python3.14`, `$OLD/$BUILD/bin/python3.14` and `$NEW/current/bin/python3.14` all resolve
   (`realpath`) to `$NEW/$BUILD/bin/python3.14` and report the recorded version; the executable sha256 is unchanged;
   one installed script of each shebang spelling runs; `scripts/laplace-python -V` prints `Python 3.14.7` with
   `LAPLACE_PYTHON` unset; `scripts/laplace-python -c "import laplace, atlas, numpy, jsonschema, filelock, dulwich"`
   succeeds.
5. Rollback (quiet again): check `$OLD/$BUILD` is the link to `$NEW/$BUILD`, remove it, `mv $NEW/$BUILD $OLD/$BUILD`,
   remove `$NEW/current`; `$OLD/current` was never changed. While the source still declares the new home, launch with
   `LAPLACE_PYTHON=$OLD/current/bin/python3.14` (the explicit override) until the move is redone.

## Writable state (never part of a source package)

| State | Default home | Owner and override |
|---|---|---|
| Engine state | `~/.mcp-gerard/laplace` | `laplace.core.checkout.state_root()`; `LAPLACE_STATE` |
| Provider session workspaces | `~/.mcp-gerard/laplace/session-workspaces` | `laplace.writing.operating.session_workspace_root()`; `LAPLACE_SESSION_WORKSPACES` |
| Managed app receipt and lock | `~/.local/state/laplace/writing-app.json` | `laplace.desktop.writing_app.state_path()`; `LAPLACE_WRITING_STATE` |
| Writing projects | `<checkout>/writing_projects`, `<checkout>/registry_projects.json`, `<checkout>/profiles/writing_sources.json` | the project library (`laplace.projects.library`), registry (`laplace.pipeline.registry`) and repository sources (`laplace.projects.writing_sources`) |
| Journal, talk and bodies | `<checkout>/contract` (`talk.jsonl`, `writing_bodies/`) | `laplace.core.records.journal`, `laplace.writing.records`, `laplace.representation.writing_bodies` over Atlas's body store. Durable records, not caches: never relocated or rehashed by a source change. |

## Derived caches

`<checkout>/.laplace-cache` (for example `writing-style/` and preserved stale `build-metadata/`) and the local-cache artifacts in `runtime_profiles.toml`
`[publication]` (`.metric_pairs.json`, `.meaning_vectors*`). Each is rebuilt by its producer, explicitly
(`scripts/laplace-python scripts/reembed.py --full-metric` for the metric caches); none is rebuilt at startup.

## Current coordination

The current development run, the one mutable coordination record, is read through
`laplace.work.development_source.coordination_entry(root)`. Its home is `<checkout>/corpus_friction/development/current.json`.
The move completed on 21 October 2026: the old mutable record was archived byte-for-byte as
`evidence/WRITING_JOINS_2026-10-04/codex-continuation/source-state-development-run-20261019.historical-20261021T033656Z.json`,
then the canonical current was published. The coordinator and the existing router now read only the canonical home.
The old recognized current path is absent. The resolver retains its legacy fallback for older installations and
refuses two current copies. Historical grants, returns and pins stay where they were written.

Completed coordination migration and rollback (quiet: no coordinator or router is writing the run). The resolver is used unchanged:
1. Record the sha256 of the legacy file `L=evidence/WRITING_JOINS_2026-10-04/codex-continuation/source-state-development-run-20261019.json`.
2. Archive it in the same directory under its pinned historical name,
   `source-state-development-run-20261019.historical-<UTC stamp>.json` (`mv`, then verify the sha256 is unchanged).
   The historical name is not a current location, so the resolver no longer sees a legacy run.
3. Publish the sole canonical run: copy the archived bytes to `corpus_friction/development/current.json` and verify
   the sha256 matches. `coordination_entry` now selects the home; `COORDINATION_LEGACY` stays as the read fallback for
   genuinely older layouts and is not edited.
4. Migrate the coordinator's own reader and router references to `coordination_entry` (or the home path), recording
   old path, historical path, current path and the sha256 in the coordinator receipt. All grants, returns and pins stay.
5. Rollback: if `current.json` still equals the archived bytes, remove it and `mv` the archive back to `L`.

## Distribution qualification

The published Writing distribution's current measured qualification is `release/current-acceptance.json`.
Its `release/acceptance.json`, source-orientation receipt and earlier evidence remain unchanged historical proofs
for their original versions and scopes. The source/export manifests, container package and current qualification
identify the matching release; an older proof is never relabelled as a new pass.

## Routes

- **Set up.** Select the runtime as above. Install the desktop launcher with
  `scripts/laplace-python scripts/install_writing_app.py --install`, which writes the launcher for
  `-m laplace.desktop.writing_app`.
- **Launch.** Desktop: the installed launcher (`~/.local/share/applications/laplace-writing-app.desktop`). Browser server: `scripts/laplace-python -m laplace.web.writing_server --root . --host 127.0.0.1 --port 8771`.
- **Update.** The coordinator promotes an accepted source checkpoint and uses
  `scripts/laplace-python -m laplace.desktop.writing_app --update` under fresh idle-activity guards.
  The managed owner compares source/runtime/frontend identities and preserves an active service.
  A desktop entry repair is checked through its actual OS Python `-I` direct-script command;
  backend health alone does not prove that clicking the icon opens or reuses a window. Updating
  the backend is separate from reloading an existing native window or its unsent drafts.
- **Open browser version.** The page-issued frontend identity and the server's captured bundle are different observations. A differing identity offers an explicit refresh; existing windows are never forced to reload. Work drafts and uncertain attempts must restore successfully before their refresh capture is acknowledged. An unsaved source/form state without safe capture refuses with a local explanation. A page with no issued identity remains unknown.
- **Current Work.** Read the coordination entry, then work through the Writing app's Work owners (`laplace.work`).
- **Find Work from the system.** `laplace.sdk.describe(task=...)`, `GET /work/discovery` or the app's System owners view
  start at the declared system entry and follow owner-returned handles to the Work affecting a subsystem; see
  [owner discovery](owner-discovery.md).
