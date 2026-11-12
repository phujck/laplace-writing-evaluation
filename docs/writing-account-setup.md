# Writing App account setup

This guide connects the Writing App to provider CLIs already installed for the same OS user. It does not copy credentials into the repository, create an OAuth system, or make the two provider accounts interchangeable.

## Before setting up an account

You can create projects, read sources, write and save text, and organise tasks
without an AI account. Start with [the task recipes](writing-tasks.md). Account
setup is needed when you want to Send a question or start supported AI work.

Open **More → App settings** for provider readiness. Authenticate through the
provider's own supported CLI as described below, then explicitly refresh the
provider catalogue in the app. Choose the provider, model and effort before Send;
**Next message context** shows what that message will use. Missing authentication
or a catalogue is an unavailable prerequisite, not a request to copy credentials
from another machine. Refresh may launch a discovery process; it sends no model
turn. Only Send exercises the selected model account.

## Codex

Install and authenticate Codex using the official Codex CLI flow. The supported browser login, `codex login status`, API-key stdin login, and optional device-auth details are documented by OpenAI at [Codex authentication](https://learn.chatgpt.com/docs/auth) and [Codex CLI](https://learn.chatgpt.com/docs/codex/cli).

After authentication, verify from the same OS account that will run the Writing App:

```sh
codex login status
command -v codex
```

The Writing App discovers the executable and, on refresh, asks the local Codex app-server for its model catalogue. It starts that process with the selected project as its working directory. No Codex credential or model cache is part of a release checkout. API-key login has separate billing from browser account login; choose the account path deliberately and keep the key outside shell history and repositories.

## Claude Code

Install Claude Code using the [official setup guide](https://code.claude.com/docs/en/setup). Run `claude` and complete its browser sign-in with your own account. Subscription, Console and organisation-managed authentication are described in [Authentication](https://code.claude.com/docs/en/authentication). The app uses the CLI's existing credentials. Available commands are documented in the [CLI reference](https://code.claude.com/docs/en/cli-reference).

Verify locally without logging in from this guide:

```sh
claude --help
claude auth --help
claude auth status --json
command -v claude
```

The Writing App reads `claude auth status --json` during provider refresh and reports authentication as unverified, unauthenticated, or authenticated-untested. A model catalogue refresh uses the installed CLI in the selected project directory with a no-session-persistence probe. Claude credentials remain owned by Claude Code and are never transferred to Codex.

## Connecting the app

Run the Writing App under the same OS user that owns the authenticated CLIs. Open the project UI, use **Refresh providers**, select a provider/model/effort, and explicitly send a turn. Discovery can start a local CLI process to inspect authentication and available models; it does not send a model turn. Sending a message is the point at which the selected account/model is exercised and model usage begins.

On Windows PowerShell, replace `command -v codex` and `command -v claude` with `Get-Command codex` and `Get-Command claude`. For Codex's browser sign-in run `codex login`; check the official guide for device authentication where a browser callback is unavailable. Complete login in the same environment as the server: a container login is separate from a host login.

The browser/server route does not require GTK. The optional native window uses the system GTK/WebKit runtime and launches the backend for the selected checkout. A container has no access to host credentials unless the operator explicitly mounts/configures them inside that container; host login state is not assumed to be visible.

Provider sessions own their native conversation history. The Writing App owns project context, author decisions, source-addressed edits, and receipts. Provider transcripts, credentials, private calibration sources, and personal author material remain outside a shareable evaluator repository.

## Evaluator boundary

Use a fresh checkout and its own project/state directories. Do not inherit the author’s checkout, shared runtime state, semantic caches, `AGENTS.md`/`CLAUDE.md` instructions, private profile sources, or provider transcripts. Provider credentials must be configured by each evaluator through the provider’s official CLI. Windows and macOS support require separate observed rehearsals; this guide does not certify them.

The setup guide records the current integration contract. It is not a login receipt or a claim that either provider is authenticated on a particular machine.
