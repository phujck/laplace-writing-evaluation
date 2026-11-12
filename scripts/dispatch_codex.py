#!/usr/bin/env python3
"""dispatch_codex.py - Codex as a plain executor: reconstruct(node, goal) -> codex exec.

His ask, 2026-09-14: "I would actually still like you to be able to use codex for example as an
executor perhaps ... just switching off custody until we're ready to reintegrate it." Before the
switch, a Codex session was a SEAT: mail gate, watcher, leases, custody receipts, a recovery
coordinate. This door keeps the dispatch kernel's one law - every packet is reconstruct(node,
goal), never read(file) - and drops the seat: the packet is compiled by
``pipeline.dispatch.compile_dispatch`` over an exact typed descent of the node (content verified
by hash; the custody-off admission in dispatch.py), written to disk with its handles, and handed
to ``codex exec`` on stdin. What comes back is a return file with its own hash and the exit code,
banked through journal.bank_row in contract/dispatches.jsonl at compile and return.
Returned prompt/return files move to evidence/DISPATCH_<date>/<id>/; the ignored
transcript retains only its digest and tail. No seat or acknowledgement ceremony: the
orchestrator judges the return against the bench and banks the verdict, or discards it.

  /usr/bin/python3 scripts/dispatch_codex.py <node> "<goal>" [--worker derive] [--model M]
        [--sandbox read-only|workspace-write] [--out-dir .dispatch] [--run | --compile-only]
        [--carrier codex-cli|claude-agent|compile-only] [--content-budget N]

Compile-only is the default; ``--compile-only`` explicitly aliases omitting ``--run``.
Both compile the typed descent and write packet.json, prompt.md and a COMPILED row.json.
A Claude-side orchestrator uses ``--carrier claude-agent`` without ``--run`` and hands
prompt.md to its own Agent tool under the row's ``packet_model_stamp``. This door does
not launch that tool; ``--run`` uses the codex-cli carrier. Unspecified compile carriers
are stamped ``compile-only``.

The default ``derive`` worker is deliberate: it retains the existing verification
method fibre for checking an engine work order. A separate engine kind would also need
its inherited policy/skill wiring separated; that change is outside this bounded door.

Model stamp: the packet's ``model`` is the Claude ceiling the compiler clamps to; the ROW stamps
``executor: codex-cli`` and ``codex_model`` explicitly (never inherited: -m or the codex config
default, read and recorded). ``carrier`` records the chosen transport separately.
``scripts/audit_dispatch_models.py`` scans workflow files and this door's row surface.

Sandbox: ``read-only`` for reads and reviews, ``workspace-write`` for edits. The codex config on
this box defaults to danger-full-access; this door never passes that - it always sets -s.
Runtime: /usr/bin/python3 (the engine's runtime law); src (laplace and atlas) rides sys.path only because of
FIND-20260914-deposit-unrunnable-at-head-seal-violation (the import chain through
turn_reconstruction -> embedding_health -> semantic_vertical -> atlas.errors).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.representation import custody_mode  # noqa: E402
from laplace.engine import descent
from laplace.core.records import journal  # noqa: E402
from laplace.pipeline import dispatch as D  # noqa: E402

MAX_BUDGET = 400_000
LEDGER = "contract/dispatches.jsonl"
OPT_OUTS = ("LAPLACE_NO_SPECTRAL", "LAPLACE_NO_SPECTRAL_GPU", "LAPLACE_EMBED_NO_GPU")


def check_fence_environment(env: dict[str, str]) -> None:
    """A supplied mapping makes the refusal probe independent of process knobs."""
    denied = [name for name in OPT_OUTS if env.get(name)]
    if denied:
        raise RuntimeError("DISPATCH-FENCE-OPT-OUT: " + ", ".join(denied))


# Installed only for an executing packet. Python's sitecustomize normally swallows
# import exceptions: os._exit is intentional for a startup refusal. Later writes
# and the engine's owned device-policy landing seam raise named refusals instead.
RUNTIME_FENCE = '''import os
import sys
DENIED = ("LAPLACE_NO_SPECTRAL", "LAPLACE_NO_SPECTRAL_GPU", "LAPLACE_EMBED_NO_GPU")
bad = [key for key in DENIED if os.environ.get(key)]
if bad:
    os.write(2, ("DISPATCH-FENCE-OPT-OUT: " + ", ".join(bad) + "\\n").encode())
    os._exit(78)
_setitem = os._Environ.__setitem__
_putenv = os.putenv
def _check(key, value):
    if isinstance(key, bytes):
        key = key.decode()
    if key in DENIED and value:
        raise RuntimeError("DISPATCH-FENCE-OPT-OUT: " + key)
def _guarded_setitem(self, key, value):
    _check(key, value)
    return _setitem(self, key, value)
def _guarded_putenv(key, value):
    _check(key, value)
    return _putenv(key, value)
os._Environ.__setitem__ = _guarded_setitem
os.putenv = _guarded_putenv
try:
    from laplace.representation import device_policy
except Exception as exc:
    os.write(2, ("DISPATCH-FENCE-UNAVAILABLE: " + str(exc) + "\\n").encode())
    os._exit(78)
_record = device_policy.record_fallback
def _guarded_fallback(organ, choice, why, *, dialed=False):
    _record(organ, choice, why, dialed=dialed)
    if choice == "cpu" or (choice == "disabled" and dialed):
        raise device_policy.DeviceRequired("DISPATCH-FENCE-FALLBACK: " + organ + ": " + why)
device_policy.record_fallback = _guarded_fallback
'''


def _fence_packet(packet: dict) -> None:
    fence = {"schema_version": "laplace.dispatch-fence/1", "unset": list(OPT_OUTS),
             "runtime": "sitecustomize:laplace.representation.device_policy.record_fallback",
             "runtime_handle": _sha(RUNTIME_FENCE)}
    packet["execution_fence"] = fence
    body = packet.get("prompt") or packet.get("script") or ""
    packet["prompt"] = body + "\n\n<!-- EXECUTION-FENCE -->\n" + json.dumps(
        fence, sort_keys=True) + "\n<!-- /EXECUTION-FENCE -->"


def _install_runtime_fence(out: Path, packet: dict, env: dict[str, str]) -> None:
    fence = packet["execution_fence"]
    expected = json.dumps(fence, sort_keys=True)
    if (fence["runtime_handle"] != _sha(RUNTIME_FENCE)
            or "<!-- EXECUTION-FENCE -->\n" + expected + "\n<!-- /EXECUTION-FENCE -->" not in packet["prompt"]):
        raise RuntimeError("DISPATCH-FENCE-HANDLE-MISMATCH")
    check_fence_environment(env)
    runtime = out / "runtime"
    runtime.mkdir()
    (runtime / "sitecustomize.py").write_text(RUNTIME_FENCE, encoding="utf-8")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (
        str(runtime), str(ROOT / "src"), env.get("PYTHONPATH", ""))))


def _edges(goal: str) -> list[dict[str, str]]:
    first = goal.splitlines()[0] if goal.splitlines() else ""
    match = re.search(r"\bWO-[A-Za-z0-9][A-Za-z0-9_.-]*", first)
    if not match:
        match = re.search(r"\bWORK ORDER\s+([^\s:]+)", first)
    return [{"rel": "grounds", "target": match.group(0) if match and match.group(0).startswith("WO-")
             else match.group(1)}] if match else []


def _bank(row: dict, out: Path | None = None) -> None:
    (ROOT / "contract").mkdir(exist_ok=True)
    journal.bank_row(LEDGER, row, root=ROOT)
    # Serve the bank's timestamp, not an independently restamped look-alike.
    with (ROOT / LEDGER).open(encoding="utf-8") as stream:
        for raw in stream:
            banked = json.loads(raw)
            if banked.get("id") == row["id"] and banked.get("phase") == row["phase"]:
                row.update(banked)
    if out is not None:
        (out / "row.json").write_text(json.dumps(row, indent=1), encoding="utf-8")


def _time_value(value: str) -> float:
    if not isinstance(value, str):
        raise ValueError("timestamp must be text")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("timestamp must name its timezone")
        return dt.timestamp()
    except ValueError:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()


def _fallbacks(start: float, end: float, path: Path) -> dict:
    hits, errors = [], []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    except (OSError, UnicodeError) as exc:
        lines = []
        errors.append(f"unreadable: {type(exc).__name__}")
    if lines:
        for line_number, raw in enumerate(lines, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
                when = _time_value(row["ts"])
            except (ValueError, TypeError, KeyError):
                errors.append(line_number)
                continue
            if start <= when <= end and row.get("dialed") is True and row.get("choice") in ("cpu", "disabled"):
                hits.append({"line": line_number, **row})
    return {"path": str(path), "start": start, "end": end,
            "selection": "all dialed CPU/disabled rows in inclusive time window; may include concurrent workers",
            "rows": hits, "malformed_lines": errors}


def _finish_return(row: dict, out: Path, *, start: float, end: float, exit_code: int | None,
                   keep_log: bool, error: str = "", fallback_path: Path | None = None) -> None:
    row.update(phase="return", status="RETURNED" if exit_code == 0 else "FAILED",
               exit=exit_code, seconds=round(end - start, 3))
    if error:
        row["error"] = error
    ret, log = out / "return.md", out / "codex.log"
    dest = ROOT / "evidence" / ("DISPATCH_" + datetime.fromtimestamp(start, timezone.utc).strftime("%Y-%m-%d")) / row["id"]
    dest.mkdir(parents=True, exist_ok=False)
    for name in ("prompt.md", "return.md"):
        src = out / name
        if src.is_file():
            src.replace(dest / name)
            row[name.split(".")[0] + "_path"] = str((dest / name).relative_to(ROOT))
    ret = dest / "return.md"
    row.update(return_handle=None, return_chars=0, return_path=row.get("return_path"))
    if ret.is_file():
        body = ret.read_text(encoding="utf-8")
        row.update(return_handle=_sha(body), return_chars=len(body))
    elif exit_code == 0:
        row.update(status="FAILED", error="MISSING-RETURN")
    fallback = _fallbacks(start, end, fallback_path or ROOT / ".fallback_events.jsonl")
    row["fallback"] = fallback
    if fallback["rows"]:
        row["status"] = "RETURNED-WITH-FALLBACK"
    elif fallback["malformed_lines"] and row["status"] == "RETURNED":
        row.update(status="RETURNED-FALLBACK-UNVERIFIED")
    if log.is_file() and not keep_log:
        blob = log.read_bytes()
        row.update(log_handle="sha256:" + hashlib.sha256(blob).hexdigest(), log_bytes=len(blob))
        log.write_bytes(blob[-4096:])
        row["log_retained"] = "tail-4096"
    _bank(row, out)


def backfill(directory: Path) -> dict:
    """Import archived observations, idempotently, without inventing lost phases."""
    directory = directory.resolve()
    directory.relative_to(ROOT.resolve())
    existing = set()
    ledger = ROOT / LEDGER
    if ledger.is_file():
        for raw in ledger.read_text(encoding="utf-8").splitlines():
            row = json.loads(raw)
            if row.get("backfill_source"):
                existing.add((row["id"], row["backfill_source"], row["backfill_handle"]))
    paths = sorted(directory.glob("*/row.json"))
    pending = []
    banked = skipped = 0
    for path in paths:
        raw = path.read_text(encoding="utf-8")
        row = json.loads(raw)
        if row.get("record") not in ("codex-dispatch", "dispatch") or not row.get("id") or not row.get("ts"):
            raise ValueError("BACKFILL-MALFORMED: " + str(path))
        source, handle = str(path.relative_to(ROOT)), _sha(raw)
        if (row["id"], source, handle) in existing:
            skipped += 1
            continue
        goal = row.pop("goal", "")
        row.update(record="dispatch", phase="backfill", dispatched_at=row["ts"],
                   goal_handle=_sha(goal), goal_path=row.get("goal_path"),
                   model=row.get("codex_model"), edges=_edges(goal),
                   backfill_source=source, backfill_handle=handle)
        row.setdefault("gpu", {"mode": "unknown", "visible": None, "detail": "not recorded in archive"})
        row.setdefault("gpu_shim", "unknown; not recorded in archive")
        for name in ("prompt", "return"):
            artifact = path.parent / (name + ".md")
            if artifact.is_file():
                body = artifact.read_text(encoding="utf-8")
                if row.get(name + "_handle") and _sha(body) != row[name + "_handle"]:
                    raise ValueError("BACKFILL-HANDLE-MISMATCH: " + str(artifact))
                row[name + "_path"] = str(artifact.relative_to(ROOT))
                row[name + "_handle"], row[name + "_chars"] = _sha(body), len(body)
        pending.append(row)
    # All source bytes validate before the first append; a bad archive cannot
    # turn a partially imported batch into an apparent complete observation.
    for row in pending:
        _bank(row)
        banked += 1
    rows = [json.loads(raw) for raw in ledger.read_text(encoding="utf-8").splitlines()] if ledger.exists() else []
    return {"status": "BACKFILLED", "source": str(directory.relative_to(ROOT)),
            "source_rows": len(paths), "banked": banked, "skipped": skipped,
            "ledger_rows": len(rows), "unique_dispatch_ids": len({r["id"] for r in rows}),
            "timestamps": "original ts retained as dispatched_at and ts_claimed; bank ts is ingestion time"}


def _sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n] or "node"


def _codex_default_model() -> str:
    cfg = Path.home() / ".codex" / "config.toml"
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            m = re.match(r'\s*model\s*=\s*"([^"]+)"', line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return "unknown"


def reconstruct(node: str, goal: str, *, kind: str, budget: int) -> dict:
    """The exact typed descent of the node, complete or refused. Never a filename read."""
    if kind == "stage":
        return D.reconstruct_stage(node, goal, repo_root=ROOT, content_budget=MAX_BUDGET)
    while True:
        d = descent.descend(kind=kind, reference=node, goal=goal, content_budget=budget,
                            record_telemetry=False)
        if d.get("content_status") == "COMPLETE" and not d.get("content_truncated"):
            return {**d, "goal": goal, "authority_write": "none"}
        if d.get("content_status") not in ("TRUNCATED", "BUDGET") or budget >= MAX_BUDGET:
            return {**d, "goal": goal, "authority_write": "none"}
        budget = min(MAX_BUDGET, max(budget * 2, int(d.get("content_bytes") or 0) + 1024))


# THE GPU SANDBOX (his ruling 2026-09-14: "NO NO FALLBACK TO CPU. FIX THE FUCKING SANDBOX").
# Codex's Linux sandbox builds `bwrap ... --dev /dev`, a fresh /dev with no NVIDIA nodes, strips
# the environment to a core set, and seccomp-filters the driver's socket call - so every executor
# measured on CPU ("cudaErrorNoDevice"). Three things restore the real machine to the executor:
# (1) scripts/sandbox/bwrap installed as ~/.local/bin/bwrap, first on PATH, dev-binds every
#     /dev/nvidia* after `--dev /dev` (crutch CR-20260914-codex-sandbox-gpu-shim);
# (2) shell_environment_policy.inherit=all, so /usr/bin/python3 runs with our environment
#     (LAPLACE_REQUIRE_GPU=1 included, which makes the engine refuse a CPU fallback itself);
# (3) sandbox_workspace_write.network_access=true, which drops the seccomp filter that broke CUDA init.
# Every dispatch probes the GPU through the same sandbox before handing over, and a workspace-write
# dispatch REFUSES when the executor cannot see it (GPU-NOT-VISIBLE); read-only records the fact.
SHIM_SRC = ROOT / "scripts" / "sandbox" / "bwrap"
SHIM_DST = Path.home() / ".local" / "bin" / "bwrap"


def _install_gpu_shim() -> str:
    if not SHIM_SRC.is_file():
        return "shim-source-missing"
    src = SHIM_SRC.read_bytes()
    if SHIM_DST.is_file() and SHIM_DST.read_bytes() == src:
        return "installed"
    SHIM_DST.parent.mkdir(parents=True, exist_ok=True)
    SHIM_DST.write_bytes(src); SHIM_DST.chmod(0o755)
    return "updated"


def _sandbox_config(sandbox: str) -> list[str]:
    cfg = ["-c", 'shell_environment_policy.inherit="all"']
    if sandbox == "workspace-write":
        cfg += ["-c", "sandbox_workspace_write.network_access=true"]
        # The engine's cross-process locks live under ~/.mcp-gerard/laplace (the MCP state dir); a
        # deposit inside the sandbox refused with EROFS on store-self-graded.lock (blk3 sweep,
        # 2026-09-14). That directory is a writable root for executors that may run the deposit.
        lock_dir = Path.home() / ".mcp-gerard" / "laplace"
        if lock_dir.is_dir():
            cfg += ["-c", f'sandbox_workspace_write.writable_roots=["{lock_dir}"]']
    return cfg


def _dispatch_env() -> dict[str, str]:
    env = {**os.environ, "NO_COLOR": "1"}
    for name in OPT_OUTS:
        env.pop(name, None)
    check_fence_environment(env)
    local_bin = str(Path.home() / ".local" / "bin")
    parts = env.get("PATH", "").split(os.pathsep)
    if parts[:1] != [local_bin]:
        env["PATH"] = os.pathsep.join([local_bin] + [q for q in parts if q != local_bin])
    return env


def _gpu_probe(sandbox: str, env: dict[str, str]) -> dict[str, Any]:
    """The executor's own view of the GPU, through the same sandbox it will run in."""
    cmd = ["codex", "sandbox", "-c", f'sandbox_mode="{sandbox}"', *_sandbox_config(sandbox), "--",
           "/usr/bin/python3", "-c",
           "import cupy as cp; n=cp.cuda.runtime.getDeviceCount(); "
           "print('GPU-VISIBLE', n, cp.cuda.runtime.getDeviceProperties(0)['name'].decode() if n else '')"]
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, cwd=str(ROOT), timeout=120, env=env)
        line = next((l for l in proc.stdout.splitlines() if l.startswith("GPU-VISIBLE")), "")
        return {"visible": line.startswith("GPU-VISIBLE") and line.split()[1] != "0",
                "detail": line or (proc.stdout + proc.stderr).strip()[-300:]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"visible": False, "detail": f"{type(exc).__name__}: {exc}"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("node", nargs="?")
    ap.add_argument("goal", nargs="?")
    ap.add_argument("--worker", default="derive", help="a schema.WORK_KINDS worker; derive = verification class")
    ap.add_argument("--kind", default="repository-file", choices=[*descent.KINDS, "stage"])
    ap.add_argument("--model", default="", help="codex model (-m); default: the codex config's model, recorded")
    ap.add_argument("--sandbox", default="read-only", choices=["read-only", "workspace-write"])
    ap.add_argument("--gpu", default="", choices=["", "required", "optional"],
                    help="GPU visible to the executor: required (default for workspace-write; the dispatch refuses without it) or optional (default for read-only; recorded)")
    ap.add_argument("--out-dir", default=".dispatch")
    ap.add_argument("--content-budget", type=int, default=descent.DEFAULT_CONTENT_BUDGET)
    execution = ap.add_mutually_exclusive_group()
    execution.add_argument("--run", action="store_true", help="hand the packet to codex exec")
    execution.add_argument("--compile-only", action="store_true",
                           help="explicit alias of omitting --run: write the admitted packet and exit")
    ap.add_argument("--carrier", choices=["codex-cli", "claude-agent", "compile-only"],
                    help="transport stamp; defaults to codex-cli with --run, else compile-only")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--keep-log", action="store_true", help="keep the full codex.log (default: after a return, only its sha256 and last 4 KB stay - the log is 300 KB per run and nobody reads it back)")
    ap.add_argument("--goal-file", default="", help="read the goal from this file (long goals; the positional goal becomes the title)")
    ap.add_argument("--output-schema", default="", help="a JSON schema file codex must answer with (passed through as --output-schema)")
    ap.add_argument("--backfill", type=Path, help="bank archived */row.json observations, preserving original ids")
    ap.add_argument("--project", help="prose project; may also be carried by the stage row")
    a = ap.parse_args(argv)
    if a.backfill:
        if a.run or a.node or a.goal:
            ap.error("--backfill cannot launch or compile a packet")
        print(json.dumps(backfill(ROOT / a.backfill), indent=1))
        return 0
    if not a.node or not a.goal:
        ap.error("node and goal are required unless --backfill is used")
    carrier = a.carrier or ("codex-cli" if a.run else "compile-only")
    if a.run != (carrier == "codex-cli"):
        ap.error("codex-cli requires --run; claude-agent and compile-only require omitting --run")
    if a.goal_file:
        a.goal = Path(a.goal_file).read_text(encoding="utf-8")

    mode = custody_mode.read(ROOT)
    if mode["mode"] != "OFF":
        print(json.dumps({"status": "REFUSED", "reason": "custody is ON: dispatch through the seat fabric, not this door",
                          "custody_mode": mode}, indent=1))
        return 2
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    out = ROOT / a.out_dir / f"{stamp}-{_slug(a.node)}-{_slug(a.goal, 24)}"
    out.resolve().relative_to(ROOT.resolve())
    out.mkdir(parents=True, exist_ok=False)

    rec = reconstruct(a.node, a.goal, kind=a.kind, budget=a.content_budget)
    packet = D.compile_dispatch(a.node, a.goal, worker=a.worker, repo_root=ROOT,
                                project=a.project, reconstruction=rec)
    codex_model = a.model or _codex_default_model()
    gpu_mode = a.gpu or ("required" if a.sandbox == "workspace-write" else "optional")
    row: dict = {
        "record": "dispatch", "id": f"CODEX-{stamp}-{_slug(a.node, 24)}", "ts": stamp,
        "dispatched_at": stamp, "phase": "compile",
        "node": a.node, "goal_handle": _sha(a.goal), "goal_path": None,
        "worker": a.worker, "kind": a.kind, "edges": _edges(a.goal),
        "executor": "codex-cli", "codex_model": codex_model, "model": codex_model,
        "sandbox": a.sandbox, "carrier": carrier,
        "custody_mode": mode.get("mode"), "custody_row": mode.get("id"),
        "reconstruction": {"content_status": rec.get("content_status"), "content_handle": rec.get("content_handle"),
                           "content_bytes": rec.get("content_bytes"), "budget_used": rec.get("content_budget")},
        "admission": (packet.get("reconstruction_admission") or {}).get("admission_result"),
        "packet_model_stamp": packet.get("model"), "packet_effort": packet.get("effort"),
        "out_dir": str(out.relative_to(ROOT)), "prompt_handle": None, "prompt_chars": 0,
        "gpu": {"mode": gpu_mode, "visible": None, "detail": "not probed; compile only"},
        "gpu_shim": "not installed; compile only",
    }
    if a.goal_file:
        src = Path(a.goal_file).resolve()
        goals = ROOT / "evidence" / ("DISPATCH_" + datetime.now(timezone.utc).strftime("%Y-%m-%d")) / "goals"
        if src.parent == goals.resolve():
            goal_path = src
        else:
            goals.mkdir(parents=True, exist_ok=True)
            goal_path = goals / (row["id"] + ".md")
            goal_path.write_text(a.goal, encoding="utf-8")
        row["goal_path"] = str(goal_path.relative_to(ROOT))
    if not packet.get("error"):
        _fence_packet(packet)
    (out / "packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=1), encoding="utf-8")
    if packet.get("error"):
        row.update(status="REFUSED", error=packet["error"])
        _bank(row, out)
        print(json.dumps(row, indent=1))
        return 2
    prompt = packet["prompt"]
    (out / "prompt.md").write_text(prompt, encoding="utf-8")
    row.update(prompt_handle=_sha(prompt), prompt_chars=len(prompt), status="COMPILED",
               execution_fence=packet["execution_fence"])
    env = _dispatch_env()
    if a.run:
        _install_runtime_fence(out, packet, env)
        row["gpu_shim"] = _install_gpu_shim()
        row["gpu"] = {"mode": gpu_mode, **_gpu_probe(a.sandbox, env)}
        if gpu_mode == "required" and not row["gpu"]["visible"]:
            row.update(status="REFUSED", error="GPU-NOT-VISIBLE: " + str(row["gpu"]["detail"]))
    _bank(row, out)
    if not a.run or row["status"] == "REFUSED":
        print(json.dumps(row, indent=1))
        return 2 if row["status"] == "REFUSED" else 0

    ret = out / "return.md"
    cmd = ["codex", "exec", "-C", str(ROOT), "-s", a.sandbox, *_sandbox_config(a.sandbox),
           "--ephemeral", "-o", str(ret), "--color", "never"]
    if a.model:
        cmd += ["-m", a.model]
    if a.output_schema:
        cmd += ["--output-schema", str(Path(a.output_schema).resolve())]
    cmd.append("-")
    t0, exit_code, error = time.time(), None, ""
    row["command"] = " ".join(cmd)
    try:
        with (out / "codex.log").open("w", encoding="utf-8") as lf:
            proc = subprocess.run(cmd, input=prompt, text=True, stdout=lf, stderr=subprocess.STDOUT,
                                  cwd=str(ROOT), timeout=a.timeout, env=env)
        exit_code = proc.returncode
    except (OSError, subprocess.SubprocessError) as exc:
        error = f"{type(exc).__name__}: {exc}"
    # Honor the recorder's configured destination without altering any engine knob.
    from laplace.representation import device_policy
    _finish_return(row, out, start=t0, end=time.time(), exit_code=exit_code,
                   keep_log=a.keep_log, error=error, fallback_path=device_policy._log_path())
    print(json.dumps(row, indent=1))
    return 0 if row["status"] == "RETURNED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
