"""A `SyncProvider` for the MIT System One adapter, backed by a local provider CLI.

There is no TypeSafe key in this environment (`env | grep -i typesafe` is empty) and
this packet creates no account, so jev itself is not reachable from here.  What is
reachable is the adapter --- `github.com/typesafe-ai/system-one-adapter-python`, MIT,
installed into a scratch venv under /tmp and never into the laplace runtime --- which
*emulates* the System One request shape on an ordinary provider.  The adapter's own
`SyncProvider` protocol (`system_one_adapter/providers/base.py:62-78`) accepts a
caller-owned provider instance in place of a model name, so this class is the whole
integration: the adapter composes the prompt, generates the JSON schema from the
questions, validates the answer against it and normalises the probabilities, exactly
as it would against a vendor SDK.

The provider is the Claude CLI, which `GET /authoring/providers` on the live app lists
as available and authenticated alongside Codex.  It is driven with `--model haiku`
because a routing decision is a System One task and the price of the frontier model is
not part of the measurement; `--strict-mcp-config` keeps the account's MCP servers out
of the child's context.

Nothing here is imported by `laplace.native.routing`: the advisor takes its decider as an
argument, so importing the advisor cannot acquire a subprocess.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import subprocess
from typing import Any


@dataclass
class ClaudeCliProvider:
    """One synchronous decision request through the `claude` CLI."""

    model_name: str = "haiku"
    executable: str = "claude"
    timeout_s: int = 180
    calls: list[dict[str, Any]] = field(default_factory=list)

    def request(self, messages: list, *, schema: dict[str, Any], structured: bool) -> Any:
        from system_one_adapter.providers.base import ProviderResult

        system = "\n\n".join(m.content for m in messages if m.role == "system")
        user = "\n\n".join(m.content for m in messages if m.role != "system")
        prompt = user
        if not structured:
            # Prompted output mode: the adapter has already put the schema in the
            # messages when it asks for one, but the CLI has no schema-constrained
            # output, so the instruction is restated plainly and the adapter's own
            # validator remains the gate.
            prompt += ("\n\nReply with ONE JSON object and nothing else: no prose, no "
                       "markdown fence, no explanation.")
        argv = [self.executable, "-p", "--model", self.model_name,
                "--output-format", "json", "--strict-mcp-config"]
        if system:
            argv += ["--append-system-prompt", system]
        started = os.times()
        completed = subprocess.run(argv + [prompt], capture_output=True, text=True,
                                   timeout=self.timeout_s, check=False)
        if completed.returncode != 0:
            raise RuntimeError("claude CLI exited %d: %s"
                               % (completed.returncode, completed.stderr[:500]))
        envelope = json.loads(completed.stdout)
        text = envelope.get("result") or ""
        usage = envelope.get("usage") or {}
        self.calls.append({
            "duration_api_ms": envelope.get("duration_api_ms"),
            "duration_ms": envelope.get("duration_ms"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cache_creation_input_tokens": usage.get("cache_creation_input_tokens"),
            "cost_usd": envelope.get("total_cost_usd"),
            "prompt_chars": len(prompt) + len(system),
            "model": envelope.get("modelUsage") and list(envelope["modelUsage"]) or None,
            "cpu_s": round(sum(os.times()[:2]) - sum(started[:2]), 3)})
        return ProviderResult(text=text,
                              input_tokens=usage.get("input_tokens"),
                              output_tokens=usage.get("output_tokens"))

    def translate_error(self, error: Exception) -> Any:
        from typesafe_sdk import TypeSafeError
        return TypeSafeError(str(error))
