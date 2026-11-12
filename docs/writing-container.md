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
different explicit state root. Project/source/profile state belongs to that selected data root,
not `site-packages` or a shared home directory. The data root need not contain
application Python or a manuscript. Separately installed code supplies the server;
see [operational homes](operational-homes.md) for managed code/data selection and
[project handover](project-data-handover.md) for moving selected data to a fresh home.

Provider working directories have a separate persistent location from runtime state.
The portable default uses a checkout/state-specific directory under Linux user data
(`$XDG_DATA_HOME/laplace`, or `~/.local/share/laplace`), macOS
`~/Library/Application Support/Laplace`, or Windows `%LOCALAPPDATA%/Laplace`.
`--session-workspaces PATH` or `LAPLACE_SESSION_WORKSPACES` selects an explicit location.
Existing `.laplace-state` bytes stay in place; this change migrates no runtime state.
Provider instructions in the selected directory or its ancestors still refuse a turn.
Old `STATE/session-workspaces` directories are preserved; inspect them before any manual
migration of provider-owned files.

The minimum Python dependencies come from `pyproject.toml`. Writing UI HTML, CSS,
JavaScript and vendored reader assets are package data. TeX, Poppler, Graphviz,
provider CLIs and numerical libraries are capability profiles: the corresponding
build, PDF, provider or research action must report unavailable when its executable or
account is absent. No startup path installs those tools.

The [sealed text reader](sealed-text-reader.md) ships as source and installed
application code. A source-host qualification is not an image capability: neither
`profiles/writing/sealed-reader-qualification.json` nor its local observation
bodies/operator receipts are seeded into the image or portable workspace. A
recipient must explicitly authorise public canaries for its own executable and
policy, inspect the retained evidence and install its own local qualification.
Ordinary reader Start remains qualified-only. This does not alter normal provider
login or ordinary informed review.

## Reproducible Linux container

The `runtime` image supplies Python 3.12, the declared numerical/figure extras,
LaTeX/Biber, Poppler, qpdf, Graphviz, librsvg, Ghostscript and ripgrep. It contains code and
UI assets but no project or history. Point Compose at an explicitly exported workspace:

Set the workspace once in the terminal used for the following commands. On Linux
or macOS, run `export LAPLACE_WORKSPACE="$(pwd)"` from the exported checkout. On
Windows PowerShell, run `$env:LAPLACE_WORKSPACE = (Get-Location).Path` there. For
multiple workspaces on one host, also give each a distinct `COMPOSE_PROJECT_NAME`
so their provider authentication volumes remain separate.

```text
docker compose -f deploy/writing/compose.yaml up --build writing
docker compose -f deploy/writing/compose.yaml exec writing python /workspace/deploy/writing/smoke.py
```

Use Docker Desktop with Linux containers on Windows or macOS; see the official
[Windows installation guide](https://docs.docker.com/desktop/setup/install/windows-install/)
and [Mac installation guide](https://docs.docker.com/desktop/setup/install/mac-install/). On Windows, select
the WSL 2 backend and keep this shell's `LAPLACE_WORKSPACE` pointed at the checkout
you intend to edit. On macOS, allow Docker Desktop access to that directory.
The registry Compose profile explicitly selects Linux/amd64; Apple Silicon runs
that published image through emulation. Native ARM image performance has not been
measured. This provides a Linux runtime on either host, not native provider/TeX parity.
The bind mount holds project/runtime state; `.laplace-state` is created inside
it. No host home directory is mounted.

Provider images are opt-in profiles. Supply a pinned npm package spec, build the named
profile, then perform the provider's normal login explicitly inside the container. Auth
is kept in a named Docker volume, not copied from `~/.codex` or `~/.claude`:

```text
docker compose -f deploy/writing/compose.yaml --profile codex build writing-codex
docker compose -f deploy/writing/compose.yaml --profile codex run --rm writing-codex codex login --device-auth

docker compose -f deploy/writing/compose.yaml --profile claude build writing-claude
docker compose -f deploy/writing/compose.yaml --profile claude run --rm writing-claude claude auth login
```

The Research workspace and source review edition uses the Claude 2.1.304 provider pin.
The supported Linux/x64/glibc executable has expected SHA-256
`ea0f135784631619a7a409d07322ecec964f9cc4fd377508ed1ba3f141f27912`,
and the recipient reader profile remains `CANDIDATE` without local proof.
The package manifests record the final installed identity. Sign in with
your own account, select a supported model/effort, and complete the
[local reader qualification procedure](sealed-text-reader.md#local-operator-qualification-attempt)
before reader Start. Conversation reads and manual editing need no provider.

For source builds, the Claude and both-provider targets default to
`@anthropic-ai/claude-code@2.1.304`; the Codex default remains
`@openai/codex@0.160.1`. Both explicit package overrides remain available.
The [workspace guide](writing-workspace.md) describes local documents, retained
Literature sources and explicit reading context. The
[comment-review guide](writing-workflow-editor.md#request-reviews-of-a-passage-comment)
explains reviewer setup and responses; the
[conversation guide](writing-conversation-reading.md) covers complete saved-message
reads. The workflow editor adds local tab preservation and scoped setting choices;
its shared owner still controls saved settings and preparation. Earlier package
limits are recorded in the download guide's
[edition history](writing-container-download.md#earlier-editions).

The recipe installs everything heavy and pinned first (OS packages, the Python dependency closure from the
two pyproject files, Node and the pinned provider CLIs) and the application source last, in the same block
at the end of each named target, so a source-only change rebuilds only those light layers and never the
provider npm layers (`tests/test_writing_recipe_order.py`).

No provider package or authenticated inference is part of the default image build or
startup. Project-specific numerical dependencies beyond the declared analysis/figure
profile require a reviewed derived image.

Evaluators who need both providers in one server use the `providers` profile and provide
both pinned package specs. The service mounts both named auth volumes:

```text
docker compose -f deploy/writing/compose.yaml --profile providers build writing-providers
docker compose -f deploy/writing/compose.yaml --profile providers run --rm writing-providers codex login --device-auth
docker compose -f deploy/writing/compose.yaml --profile providers run --rm writing-providers claude auth login
docker compose -f deploy/writing/compose.yaml --profile providers up writing-providers
```

Run each CLI's login explicitly against that service before starting it. Only one Writing
service should bind the configured port at a time.

Codex device login is beta and must be enabled by the account or workspace admin;
see [OpenAI's headless authentication instructions](https://learn.chatgpt.com/docs/auth).
If it is unavailable, use the documented account-specific alternative rather than
expecting the host browser to reach a callback inside an unmapped container.
Claude's [authentication guide](https://code.claude.com/docs/en/authentication)
describes copying its printed login URL and pasting the returned code when a
container callback cannot be reached. Never place auth caches in the checkout.

These verified pins require Node 16+ and Node 22+ respectively; provider images copy the
official Node 22 runtime. Builds can override either explicit package spec, but an unpinned
provider install is never performed.

## Review the downloaded package

The Writing image includes the reviewer guide, source navigation, workflow
resources and the portable Python test dependencies. In the extracted workspace,
run the following with the image from the **same** release:

```sh
docker run --rm --network none -v "$PWD:/workspace:ro" laplace-writing:backlog-source-20261028 python -m pytest tests -p no:cacheprovider
docker run --rm --network none -v "$PWD:/workspace:ro" laplace-writing:backlog-source-20261028 node --test tests/project_landing.test.mjs
```

These are the portable evaluator suite and project-entry tests described in
[the reviewer guide](writing-reviewer-guide.md), not the complete upstream monorepo
suite. Both run without downloading dependencies. The guide is also present at
`/opt/laplace/REVIEWER_GUIDE.md`; project documents and histories belong to the mounted
workspace. No provider login is needed for these checks.

The **Research workspace and source review** package keeps application code and static
assets in the installed Python packages and `/opt/laplace/src`. Its current
guides are under `/opt/laplace/docs`; the four packet schemas are also installed
as `laplace.pipeline.packet_profiles` resources. The mounted `/workspace` supplies
project data and its retained histories. Generated `README.md` and `AGENTS.md`
come from the canonical human and agent entries. `release/current-acceptance.json`
and the package manifests identify the final canonical source, private workspace
commit and image separately; no edition name substitutes for those identities.

The optional `deploy/writing/Dockerfile.refresh` reuses a previously qualified image's
OS, TeX and provider dependencies. Check the local tag's image ID against the prior acceptance before supplying
`--build-arg BASE_IMAGE=laplace-writing:…`; it replaces both local packages and copies the current operational
resources. The release acceptance records the base and installed-source comparison.
Its optional `--build-arg CLAUDE_NPM_SPEC=@anthropic-ai/claude-code@2.1.304`
updates only the selected Claude package using the base's existing npm and Claude
installation; missing prerequisites or an npm failure stop the build. Leaving
the argument empty preserves the base provider bytes. It does not update Codex
or install auth or qualification. A source-only refresh without that explicit
argument cannot replace an older provider executable.
A clean build uses the ordinary Dockerfile and its declared `research,review` extras.
The clean multi-provider target remains `provider-both`, with its existing
explicit provider pins and overrides.

## Platform boundary

This edition uses the container **Python 3.12** profile; its exact interpreter,
installed modules and frontend identity are recorded in `release/current-acceptance.json`.
The retained container runtime baseline uses CPython **3.12.15**. The development
host's selected CPython **3.14.7** and its personal runtime entrance are separate.
Workflow definition reads, saves and Prepare do not import the POSIX execution
lock; a fresh unavailable-`fcntl` simulation exercised those doors and qualified
Start with a refusal before effects. That simulation is not Windows execution
parity. The Linux/amd64 image and actual browser qualification are recorded in
this edition's `release/current-acceptance.json`.


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

Provider cwd data is mounted at `/var/lib/laplace/session-workspaces` in the named
`session-workspaces` volume for every Compose profile. The image creates that directory
with the configured non-root UID/GID. Container recreation preserves it; `docker compose
down -v` deliberately removes named volumes, including provider cwd/auth data. Use separate
`COMPOSE_PROJECT_NAME` values for separate workspaces. An older downloaded image does not
gain this code from a mounted checkout: the final release must rebuild and smoke-test the
image before this new default is claimed for that image.

`GET /work/storage?project=ID` measures logical bytes in the existing stores on demand.
Saved versions are also included in own-files bytes. The census does not follow symlinks
or write a growth baseline. `POST /work/storage/prune` accepts only `project` and
`confirm: true`; it records an existing journal act and removes only empty orphan provider
cwd directories after checking conversation references and process cwd/identity. Recorded
sessions, discovery, active/unknown processes, nonempty provider data, source, saved versions,
evidence, conversation, journals and saved bodies are protected. This small cleanup does
not reclaim historical body/evidence storage or oracle gigabytes.
