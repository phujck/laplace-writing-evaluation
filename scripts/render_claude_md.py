"""Compatibility entry for the shared record-backed provider views."""
from pathlib import Path
import sys
from laplace.engine import session_memory
ROOT = Path(__file__).resolve().parents[1]

def render(repo_root: Path) -> str:
    return session_memory.render_entry(session_memory.resolve(repo_root))

def _check(repo_root: Path) -> int:
    state = session_memory.resolve(repo_root)
    status = session_memory.view_status(repo_root, state)
    print(status)
    return int(state["status"] != "CURRENT" or "STALE" in status.values())

def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--write"]:
        print({"changed": session_memory.render_views(ROOT)})
        return 0
    if args == ["--check"]:
        return _check(ROOT)
    if not args or args in (["-"], ["--stdout"]):
        print(render(ROOT), end="")
        return 0
    raise SystemExit("use --write, --check, or --stdout")

if __name__ == "__main__":
    raise SystemExit(main())
