#!/usr/bin/env python3
"""Ensure DERIVED state exists, driven by localstate.json (repo root).

Generalises the one-off scripts (ensure_voice_store.sh, ensure_tex.sh) into one
manifest-driven walk: for each entry, run its `check` command; on a miss, run
its `rebuild` command (which must derive the state from COMMITTED RAW), then
re-check to see whether the rebuild actually landed. This script does not
replace ensure_voice_store.sh / ensure_tex.sh -- their entries in the manifest
CALL those scripts; this is the table, not a rewrite of the mechanism.

Usage:
    python scripts/ensure_state.py [--manifest PATH] [--only NAME [--only NAME2 ...]]
                                    [--cheap-only] [--dry-run]

Exit code: 0 when every SELECTED entry ends check-passing, 1 otherwise (mirrors
the FAIL-LOUD contract of ensure_voice_store.sh / ensure_tex.sh: a durable,
greppable verdict line, always the LAST line of output).

Sentinel (always the final line, exactly one):
    VERDICT=PASS missing=[]
    VERDICT=FAIL missing=[name1,name2]

Entries excluded by --only / --cheap-only are not attempted and cannot appear
in `missing` -- only entries actually selected and still failing after any
rebuild attempt count.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = "localstate.json"
OUTPUT_CAP = 4000  # bounded output per entry (chars, combined stdout+stderr)

# The one platform-aware executor (laplace.core.process): POSIX one-liners via Git
# Bash on Windows, venv path rewritten. Absent (script run outside the venv on a
# POSIX box) the plain shell=True path below is already POSIX-correct.
try:
    from laplace.core.process import normalize_cmd, run_manifest_cmd
except ImportError:  # pragma: no cover - POSIX standalone fallback
    normalize_cmd = None
    run_manifest_cmd = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"{path}: no 'entries' list")
    names = {e.get("name") for e in entries}
    for e in entries:
        for key in ("name", "check", "rebuild", "cost"):
            if key not in e:
                raise ValueError(f"{path}: entry {e!r} missing required key {key!r}")
        if e["cost"] not in ("cheap", "expensive"):
            raise ValueError(f"{path}: entry {e['name']!r} has invalid cost {e['cost']!r}")
        dep = e.get("depends_on")
        if dep is not None:
            if not isinstance(dep, list) or any(not isinstance(d, str) for d in dep):
                raise ValueError(f"{path}: entry {e['name']!r} depends_on must be a list of str")
            unknown = [d for d in dep if d not in names]
            if unknown:
                raise ValueError(f"{path}: entry {e['name']!r} depends_on names unknown "
                                 f"entr(y/ies) {unknown}")
    return entries


def _cap(text: str) -> str:
    text = text.rstrip("\n")
    if len(text) <= OUTPUT_CAP:
        return text
    return text[:OUTPUT_CAP] + f"\n...[truncated, {len(text) - OUTPUT_CAP} more chars]"


def run_cmd(cmd: str, cwd: Path) -> tuple[int, str]:
    """Run a shell command (manifest commands are shell one-liners, e.g. `test -f ...`
    or piped/quoted checks) with cwd=repo root. Returns (returncode, bounded combined output)."""
    try:
        if run_manifest_cmd is not None:
            proc = run_manifest_cmd(cmd, cwd)
        else:
            proc = subprocess.run(
                cmd, shell=True, cwd=cwd, capture_output=True, text=True, timeout=600,
            )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, _cap(out)
    except subprocess.TimeoutExpired as exc:
        return 124, _cap(f"TIMEOUT after {exc.timeout}s")


def _dep_failure_banner(entry: dict[str, Any], failed_deps: list[str],
                        by_name: dict[str, dict[str, Any]], cwd: Path) -> str:
    """The LOUD, greppable stderr banner: a rebuild refused because a dependency did not end
    check-passing. Names the dependency and its own fix command so the failure is causal, never
    a silent die (audit_2026-07-14 Part 2 #4 -- the vendored-embedder extraction failure must
    fail loud+blocking for the caches that depend on it)."""
    name = entry["name"]
    bar = "=" * 78
    _n = (lambda c: normalize_cmd(c, cwd)) if normalize_cmd else (lambda c: c)
    fixes = "\n".join(f"      {d}: {_n(by_name[d]['rebuild'])}" for d in failed_deps)
    return (
        f"{bar}\n"
        f"ensure_state: DEPENDENCY FAILURE -- refusing to rebuild '{name}'\n"
        f"  '{name}' depends on {failed_deps} but that dependency did NOT end\n"
        f"  check-passing this run. Its rebuild ({entry['rebuild']}) needs it and\n"
        f"  would silently die -- so it is BLOCKED, not attempted.\n"
        f"  FIX THE DEPENDENCY FIRST:\n{fixes}\n"
        f"{bar}"
    )


def process_entry(entry: dict[str, Any], cwd: Path, dry_run: bool,
                  status: dict[str, bool] | None = None,
                  by_name: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    name = entry["name"]
    result: dict[str, Any] = {"name": name, "cost": entry["cost"]}

    rc, out = run_cmd(entry["check"], cwd)
    result["check_rc"] = rc
    result["check_output"] = out

    if rc == 0:
        result["action"] = "skip (check passed)"
        result["final_ok"] = True
        return result

    # the check failed -> a rebuild is needed. Gate on dependencies BEFORE attempting it:
    # if a named dependency did not end check-passing this run, the embedding-backed rebuild
    # would silently die, so REFUSE it and fail LOUD naming the dependency.
    status = status or {}
    failed_deps = [d for d in entry.get("depends_on", []) if status.get(d) is False]
    if failed_deps:
        by_name = by_name or {}
        print(_dep_failure_banner(entry, failed_deps, by_name, cwd), file=sys.stderr, flush=True)
        result["action"] = (f"BLOCKED: dependency {failed_deps} failed -- rebuild refused "
                            f"(would silently die without the embedding backend)")
        result["dep_blocked"] = failed_deps
        result["final_ok"] = False
        return result

    if dry_run:
        result["action"] = f"would rebuild: {entry['rebuild']}"
        result["final_ok"] = False
        return result

    result["action"] = f"rebuilding: {entry['rebuild']}"
    rrc, rout = run_cmd(entry["rebuild"], cwd)
    result["rebuild_rc"] = rrc
    result["rebuild_output"] = rout

    rc2, out2 = run_cmd(entry["check"], cwd)
    result["recheck_rc"] = rc2
    result["recheck_output"] = out2
    result["final_ok"] = rc2 == 0
    return result


def select(entries: list[dict[str, Any]], only: list[str] | None, cheap_only: bool) -> list[dict[str, Any]]:
    sel = entries
    if only:
        wanted = set(only)
        known = {e["name"] for e in entries}
        missing_names = wanted - known
        if missing_names:
            raise SystemExit(f"--only: unknown entry name(s): {sorted(missing_names)}")
        sel = [e for e in sel if e["name"] in wanted]
    if cheap_only:
        sel = [e for e in sel if e["cost"] == "cheap"]
    return sel


def order_by_deps(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable topological order over the SELECTED entries so a dependency that is also selected
    is processed before its dependent (its status is then known when the dependent's gate reads
    it). Only intra-selection edges matter here; dependencies outside the selection are handled
    separately (check-only) in main. A dependency cycle falls back to manifest order (the gate
    still fires on whichever side resolves first) rather than raising."""
    by_name = {e["name"]: e for e in selected}
    ordered: list[dict[str, Any]] = []
    placed: set[str] = set()
    visiting: set[str] = set()

    def visit(e: dict[str, Any]) -> None:
        n = e["name"]
        if n in placed or n in visiting:
            return
        visiting.add(n)
        for d in e.get("depends_on", []):
            if d in by_name:
                visit(by_name[d])
        visiting.discard(n)
        placed.add(n)
        ordered.append(e)

    for e in selected:  # manifest order preserved among independents
        visit(e)
    return ordered


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=None, help=f"path to the manifest (default: repo root {DEFAULT_MANIFEST})")
    ap.add_argument("--root", default=None,
                    help="cwd check/rebuild commands run in (default: this script's repo root); "
                         "tests point this at a fixture directory")
    ap.add_argument("--only", action="append", default=None, help="only process this entry (repeatable)")
    ap.add_argument("--cheap-only", action="store_true", help="only process entries with cost=cheap")
    ap.add_argument("--dry-run", action="store_true", help="run checks only; never run rebuild commands")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else repo_root()
    manifest_path = Path(args.manifest) if args.manifest else root / DEFAULT_MANIFEST
    entries = load_manifest(manifest_path)
    by_name = {e["name"]: e for e in entries}
    selected = select(entries, args.only, args.cheap_only)
    selected_names = {e["name"] for e in selected}
    ordered = order_by_deps(selected)

    print(f"ensure_state: manifest={manifest_path} entries={len(entries)} selected={len(selected)} "
          f"dry_run={args.dry_run} cheap_only={args.cheap_only}")

    # dependency status ledger: name -> ended check-passing this run. A dependency a selected
    # entry needs but that is NOT itself selected (e.g. `--only voice-store`) is evaluated
    # check-only up front, so the loud dependency gate fires even under a narrowed selection.
    status: dict[str, bool] = {}
    needed_deps = [d for e in selected for d in e.get("depends_on", []) if d not in selected_names]
    for dname in dict.fromkeys(needed_deps):  # dedupe, preserve order
        dep = by_name[dname]
        drc, _dout = run_cmd(dep["check"], root)
        status[dname] = drc == 0
        print(f"\n--- dependency {dname} (check-only, not selected) --- check: rc={drc} "
              f"-> {'present' if drc == 0 else 'MISSING'}")

    missing: list[str] = []
    for entry in ordered:
        print(f"\n--- {entry['name']} (cost={entry['cost']}) ---")
        r = process_entry(entry, root, args.dry_run, status=status, by_name=by_name)
        status[entry["name"]] = r["final_ok"]
        print(f"check: rc={r['check_rc']}")
        if r["check_output"]:
            print(r["check_output"])
        print(f"action: {r['action']}")
        if "rebuild_rc" in r:
            print(f"rebuild: rc={r['rebuild_rc']}")
            if r["rebuild_output"]:
                print(r["rebuild_output"])
            print(f"recheck: rc={r['recheck_rc']}")
            if r["recheck_output"]:
                print(r["recheck_output"])
        if not r["final_ok"]:
            missing.append(entry["name"])

    verdict = "FAIL" if missing else "PASS"
    print(f"\nVERDICT={verdict} missing=[{','.join(missing)}]")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
