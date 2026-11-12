# Optional model account setup

Reading papers, inspecting saved conversations/evidence, manual editing and organising projects do not require an AI account. Model work begins only when you explicitly send or start it. The evaluation image ships without credentials, provider-native transcripts, private author calibration or model weights.

## Container accounts

The evaluation container keeps its runtime HOME at `/data/accounts` in your named volume. Authenticate the CLI inside the same container and OS account that runs the app; a host login is not automatically visible. The [container guide](writing-container.md) describes persistence and the separate provider working-directory location.

Use the container name or ID from `docker ps` in place of `CONTAINER` below. The image recipe includes Codex and Claude Code; verify the installed executables in the actual downloaded image:

```sh
docker exec CONTAINER sh -lc 'command -v codex; command -v claude'
```

An absent executable is an unavailable prerequisite, not an authenticated model service. Do not bake your login cache into an image or repository. Persist your own account only in the intended account volume.

## Codex

Codex supports ChatGPT sign-in for subscription access and API-key sign-in for separately metered API access. Choose the account path deliberately. For a headless container, the official documentation describes device-code authentication; it is a beta option that must be enabled for the account/workspace. [OpenAI authentication documentation](https://learn.chatgpt.com/docs/auth?surface=cli).

When the image provides Codex and your account permits device login:

```sh
docker exec -it CONTAINER codex login --device-auth
docker exec CONTAINER codex login status
```

Complete the printed link/code in your own browser. If that flow is unavailable, use a supported alternative from the official guide. The documentation also explains credential storage and account restrictions; no account, quota or authentication success is inferred from the image containing a CLI.

## Claude Code

When the image provides Claude Code, authenticate inside that container using its supported interactive flow and verify its account status. Follow [Anthropic’s authentication guide](https://code.claude.com/docs/en/authentication) for the installed CLI/account. Its credentials remain provider-owned; a Codex login does not authenticate Claude.

## Connect the application

Open **More → App settings**, refresh provider readiness, and select the provider, model and effort before sending. Catalogue/auth discovery may start a local CLI process; it does not itself send a model turn. Inspect **Next message context** and explicitly Send when ready to exercise the selected account.

Imported example histories remain inspectable without their original provider-native bindings. They do not transfer the author’s account or permission to resume the original provider thread. A locally configured account supports new authorised work in your own environment.
