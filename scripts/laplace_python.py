"""Run Python against this Laplace checkout and its selected package runtime."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(arguments: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if arguments is None else arguments)
    policy = runpy.run_path(str(ROOT / "src" / "laplace" / "core" / "runtime.py"))
    try:
        selected = policy["lifecycle_python"](ROOT)
    except policy["RuntimePolicyError"] as exc:
        print(f"LAPLACE RUNTIME REFUSED: {exc}", file=sys.stderr)
        return 2
    source_paths = [str(ROOT / "src")]   # src holds laplace and atlas (one source home since R2)
    env = dict(os.environ)
    env.pop("PYTHONHOME", None)
    env.update({
        "LAPLACE_PYTHON": selected,
        "PYTHONPATH": os.pathsep.join(source_paths),
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "_LAPLACE_RUNTIME_TARGET": selected,
    })
    matches = Path(sys.executable).resolve() == Path(selected).resolve()
    if not matches and not sys.flags.no_site and os.environ.get("_LAPLACE_RUNTIME_TARGET") == selected:
        print(f"LAPLACE RUNTIME REFUSED: selected launcher did not execute {selected}", file=sys.stderr)
        return 2
    if not matches or not sys.flags.isolated or sys.flags.no_site:
        os.execve(selected, [selected, "-I", "-B", str(Path(__file__).resolve()), *args], env)
    os.environ.pop("PYTHONHOME", None)
    os.environ.update(env)
    try:
        policy["require_runtime"](ROOT)
    except policy["RuntimePolicyError"] as exc:
        print(f"LAPLACE RUNTIME REFUSED: {exc}", file=sys.stderr)
        return 2
    # Let the platform/application own temporary storage and its retention. A
    # checkout-local default leaked repository instructions into provider test
    # workspaces and retained every subprocess's scratch indefinitely.
    # An explicit runtime override remains available for a declared fixture.
    if os.environ.get("LAPLACE_RUNTIME_SCRATCH"):
        scratch = Path(os.environ["LAPLACE_RUNTIME_SCRATCH"]).expanduser().resolve()
        scratch.mkdir(parents=True, exist_ok=True)
        os.environ.update({"TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)})
    sys.path[:0] = source_paths
    if args[:1] == ["--"]:
        args.pop(0)
    while args[:1] in (["-B"], ["-u"]):
        if args.pop(0) == "-u":
            for stream in (sys.stdout, sys.stderr):
                if hasattr(stream, "reconfigure"):
                    stream.reconfigure(line_buffering=True, write_through=True)
    if args[:1] in (["-V"], ["--version"]):
        print("Python " + sys.version.split()[0])
        return 0
    if not args or args[0] in {"-h", "--help"}:
        print("usage: scripts/laplace-python script.py [args] | -m module [args] | -c code [args] | -")
        return 0
    mode = args.pop(0)
    if mode == "-m":
        if not args:
            raise ValueError("-m requires a module")
        module = args.pop(0)
        sys.argv = [module, *args]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    elif mode in {"-c", "-"}:
        if mode == "-c" and not args:
            raise ValueError("-c requires code")
        code = args.pop(0) if mode == "-c" else sys.stdin.read()
        sys.argv = [mode, *args]
        namespace = {"__name__": "__main__", "__package__": None, "__builtins__": __builtins__}
        exec(compile(code, "<string>" if mode == "-c" else "<stdin>", "exec"), namespace)
    elif mode.startswith("-"):
        raise ValueError(f"unsupported interpreter option {mode}; use script, -m, -c or -")
    else:
        script = Path(mode).resolve()
        sys.path.insert(2, str(script.parent))
        sys.argv = [str(script), *args]
        runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
