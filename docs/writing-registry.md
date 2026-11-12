# Download the prebuilt private runtime

For a complete download using repository access alone, use the
[repository container package](writing-container-download.md). This page is the
alternative registry route.

This edition is the repository Release `writing-bundle-20261013-astra-draft`, with local
image tag `laplace-writing:astra-draft-20261013`. Prefer the repository-download
route: its loader supplies the verified local tag without registry access.
For a registry launch, set `LAPLACE_IMAGE` to the exact qualified immutable digest
recorded in the matching `container-package.json` or `release/current-acceptance.json`.
Use that route only when the record names a registry image and your account can
pull it; a local tag is not a registry digest. Compose refuses an unset image.

The historical registry image is
`ghcr.io/phujck/laplace-writing:eval-20261004-blueprint`. Its publication/pull-test
results belong to the **Publish private Writing container** workflow for that
edition. Set `LAPLACE_IMAGE` to the recorded `ghcr.io/phujck/laplace-writing@sha256:…`
reference only when reproducing its exact matching workspace.

Use the workspace selected by that release's export manifest. The current edition
selects Foundations of Synthetics, Laplace — Living System Guide with current
development records, and the ongoing little-fun study; it does not turn the latter
into a completed paper or a tested hypothesis. The image contains its
runtime, TeX/numerical dependencies and pinned Codex/Claude CLIs, with projects
mounted separately. It contains no credentials. A current checkout paired with an
old image is not proof of a newly qualified package.

You need repository and package read access. Authenticate Docker to `ghcr.io` with
your own GitHub username and a classic personal access token with `read:packages`:
run `docker login ghcr.io -u YOUR_GITHUB_USERNAME` and enter the token at its password
prompt. Do not put it in a command, file or commit. See
[GitHub's registry authentication guide](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

From the clone, set `LAPLACE_WORKSPACE` to its absolute path. Bash:
`export LAPLACE_WORKSPACE="$PWD"`; PowerShell:
`$env:LAPLACE_WORKSPACE = (Get-Location).Path`.

```sh
docker compose -f deploy/writing/compose.registry.yaml pull
docker compose -f deploy/writing/compose.registry.yaml run --rm writing codex login --device-auth
docker compose -f deploy/writing/compose.registry.yaml run --rm writing claude auth login
docker compose -f deploy/writing/compose.registry.yaml up
```

Log into whichever providers you use; both login commands are optional for reading
and manual editing. See [account setup](writing-account-setup.md) for device-login
requirements. Open http://127.0.0.1:8771/project?workspace=writing. Ctrl+C stops the
server; the mounted checkout and named authentication volumes persist.

The image platform is Linux/amd64. Docker Desktop on Apple Silicon uses
emulation; native ARM performance has not been tested. Linux bind-mounted files
must be writable by image UID/GID 1000. If your account uses different IDs, use the
[local image build](writing-container.md) with the matching LAPLACE_UID/GID build
arguments. No inference starts until you send a session request.
