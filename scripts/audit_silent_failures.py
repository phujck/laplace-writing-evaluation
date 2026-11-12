#!/usr/bin/env python3
"""audit_silent_failures.py — the SEAM-LIVENESS gate, a pure reporter.

The close_checklist watches the close ritual; this watches the SEAMS between the
pipeline's organs — the places where one leg writes a derived artifact a later leg
reads. A seam fails SILENTLY when the writer no-ops (or was never built) and the
reader just sees "nothing here" and carries on: no crash, no verdict, a real loss
that never surfaces. This audit walks the known silent-failure seams and reports
each one PASS / WARN, never mutating anything.

WHY EVERY CHECK IS WARN-ONLY IN v1 (FAIL_ELIGIBLE is EMPTY):
  A silent-failure seam is by definition a place the pipeline THINKS is fine. A
  string-match miss (an unwritten economics.json, a stale conformance) doesn't
  prove the seam is dead — it's a signal to LOOK, not a gate to block a close on.
  Until a check earns the right to gate (a false-positive rate near zero), it can
  only ever advise. The empty FAIL_ELIGIBLE is enforced by an assertion in
  _verdict, not just documented, so a future check that returns FAIL can't
  silently start moving the exit code before it has earned it.

CHECKS (each PASS / WARN + one-line detail):
  economics-fresh    per project with harnessed rounds, is economics.json present
                      beside them and newer than the newest mech_r*.json?
  state-present      does each registered project have a release/state.json?
                      (absent = NEVER_RUN — the release machine never touched it)
  rounds-findable    for every project with round files ON DISK, does the round-
                      discovery mechanism actually resolve at least one? (guards
                      the falqon-blindness fix: NEVER_RUN projects can still have
                      rounds, and discovery must not gate on state)
  ledger-poison      any poisoned (unparseable) lines silently dropped from the
                      corpus_friction/*.jsonl ledgers?
  versions-writer    is the ONE versions_dir writer built? release.bank_snapshot
                      is the single door (Fork 7); PASS when it is present and
                      callable, WARN if it regressed away (the gap it closed).
  interpreter-sanity does .venv/bin/python exist and import pytest + laplace? (if
                      not, every test-gate trigger silently no-ops)
  voice-conformance  does the newest conformance_*.json exist and name its inputs?
                      (the detector itself stays unwired by design)

VERDICT: the last line of output is always the sentinel (paper_gates.py convention):
    VERDICT=PASS warns=<n>
    VERDICT=FAIL checks=<n_fail>/<n_total> reasons=<comma,list> warns=<n>
so a truncated read (tail -1) still carries the whole verdict. In v1 no check can
FAIL, so the verdict is always PASS; the FAIL branch is present for the day a
check earns FAIL_ELIGIBLE membership.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# cold-run bootstrap (the wake.py idiom): the gate must see the engine's own
# modules under bare python3, or its rounds-findable/ledger-poison checks go
# blind and the registry-backed checks report a false N=0.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

# The only checks allowed to ever return FAIL. EMPTY in v1: every seam check is
# advisory until it earns the right to gate (see module docstring). Enforced by an
# assertion in _verdict, not just documented.
FAIL_ELIGIBLE: frozenset[str] = frozenset()


@dataclass
class Check:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str


def _run(cmd: list[str], cwd: Path, timeout: int = 60) -> tuple[Optional[int], str, str]:
    """Run a subprocess, never raising: (returncode, stdout, stderr).
    returncode is None if the executable could not even be launched."""
    import subprocess
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.SubprocessError) as exc:
        return None, "", str(exc)


def _registry():
    try:
        from laplace.pipeline import registry
        return registry
    except Exception:
        return None


def _project_rows(repo: Path) -> list[dict]:
    """One row per registered project: {name, kind, state, rounds_n, md}. Prefers
    registry.project_states (the inventory authority on state + rounds_n) and
    degrades to all_projects when it is absent. `md` is the resolved manuscript
    dir (None when unresolvable — a sibling clone missing under a test root)."""
    reg = _registry()
    if reg is None:
        return []
    md_of: dict[str, Optional[Path]] = {}
    for name, proj in reg.all_projects().items():
        md = None
        if getattr(proj, "manuscript_dir", ""):
            try:
                md = proj.path(proj.manuscript_dir, repo)
            except Exception:
                md = None
        md_of[name] = md

    if hasattr(reg, "project_states"):
        rows = []
        for st in reg.project_states(repo):
            rows.append({
                "name": st["name"], "kind": st.get("kind"), "state": st.get("state"),
                "rounds_n": st.get("rounds_n", 0), "md": md_of.get(st["name"]),
            })
        return rows

    rows = []
    for name, proj in reg.all_projects().items():
        md = md_of.get(name)
        harnessed = (md / "rounds" / "harnessed") if md else None
        rounds_n = sum(1 for _ in harnessed.glob("mech_r*.json")) if harnessed and harnessed.is_dir() else 0
        rows.append({"name": name, "kind": getattr(proj, "kind", None),
                     "state": None, "rounds_n": rounds_n, "md": md})
    return rows


# ------------------------------------------------------------- (1) economics-fresh
def check_economics_fresh(repo: Path) -> list[Check]:
    rows = [r for r in _project_rows(repo) if r["md"] is not None]
    priced = []
    for r in rows:
        harnessed = r["md"] / "rounds" / "harnessed"
        if not harnessed.is_dir():
            continue
        mechs = list(harnessed.glob("mech_r*.json"))
        if not mechs:
            continue
        priced.append((r["name"], r["md"], max(m.stat().st_mtime for m in mechs), len(mechs)))
    if not priced:
        return [Check("economics-fresh", "PASS", "no harnessed rounds to price (N=0)")]

    results = []
    for name, md, newest_mech, n in priced:
        econ = None
        for cand in (md / "rounds" / "economics.json", md / "economics.json"):
            if cand.is_file():
                econ = cand
                break
        if econ is None:
            results.append(Check("economics-fresh", "WARN",
                                 f"{name}: economics.json absent beside {n} harnessed round(s)"))
        elif econ.stat().st_mtime < newest_mech:
            results.append(Check("economics-fresh", "WARN",
                                 f"{name}: {econ.name} stale (older than newest mech_r*.json)"))
        else:
            results.append(Check("economics-fresh", "PASS", f"{name}: {econ.name} fresh"))
    return results


# --------------------------------------------------------------- (2) state-present
def check_state_present(repo: Path) -> list[Check]:
    rows = [r for r in _project_rows(repo) if r["md"] is not None]
    if not rows:
        return [Check("state-present", "PASS", "no registered projects resolve (N=0)")]
    results = []
    for r in rows:
        state_file = r["md"] / "release" / "state.json"
        if state_file.is_file():
            results.append(Check("state-present", "PASS", f"{r['name']}: {r['state'] or 'present'}"))
        else:
            results.append(Check("state-present", "WARN",
                                 f"{r['name']}: NEVER_RUN (no release/state.json)"))
    return results


# ------------------------------------------------------------- (3) rounds-findable
def _round_files_on_disk(md: Path) -> int:
    """Ground truth: round record files physically present, over the discovery's
    glob set (harnessed mech_r*.json + judge_rounds *round*.json)."""
    n = 0
    harnessed = md / "rounds" / "harnessed"
    if harnessed.is_dir():
        n += sum(1 for _ in harnessed.glob("mech_r*.json"))
    judge = md / "judge_rounds"
    if judge.is_dir():
        n += sum(1 for _ in judge.glob("*round*.json"))
    return n


def check_rounds_findable(repo: Path) -> list[Check]:
    try:
        from laplace.pipeline import convergence_ledger as cl
    except Exception:
        return [Check("rounds-findable", "WARN",
                      "round-discovery module (pipeline.convergence_ledger) unavailable — cannot verify")]
    rows = [r for r in _project_rows(repo) if r["md"] is not None]
    on_disk = [(r["name"], r["md"]) for r in rows if _round_files_on_disk(r["md"]) > 0]
    if not on_disk:
        return [Check("rounds-findable", "PASS", "no round files on disk (N=0)")]
    results = []
    for name, md in on_disk:
        ground = _round_files_on_disk(md)
        try:
            resolved = len(cl.assemble_ledger(name, repo).get("rounds", []))
        except Exception as exc:
            results.append(Check("rounds-findable", "WARN",
                                 f"{name}: discovery raised {type(exc).__name__} over {ground} round file(s)"))
            continue
        if resolved == 0:
            results.append(Check("rounds-findable", "WARN",
                                 f"{name}: {ground} round file(s) on disk but discovery resolves 0 "
                                 "(falqon-blindness would have regressed)"))
        else:
            results.append(Check("rounds-findable", "PASS",
                                 f"{name}: discovery resolves {resolved} of {ground} round file(s)"))
    return results


# ---------------------------------------------------------------- (4) ledger-poison
def check_ledger_poison(repo: Path) -> Check:
    try:
        from laplace.pipeline.ledger import read_jsonl_counted
    except Exception:
        return Check("ledger-poison", "WARN",
                     "ledger.read_jsonl_counted unavailable — cannot count dropped lines")
    friction = repo / "corpus_friction"
    ledgers = sorted(friction.glob("*.jsonl")) if friction.is_dir() else []
    if not ledgers:
        return Check("ledger-poison", "PASS", "N=0 corpus_friction ledgers")
    poisoned = []
    total = 0
    for p in ledgers:
        _recs, dropped = read_jsonl_counted(p)
        total += dropped
        if dropped:
            poisoned.append(f"{p.name}={dropped}")
    if total > 0:
        return Check("ledger-poison", "WARN",
                     f"dropped_n={total} across {len(ledgers)} ledger(s): {', '.join(poisoned)}")
    return Check("ledger-poison", "PASS", f"dropped_n=0 across {len(ledgers)} ledger(s)")


# --------------------------------------------------------------- (5) versions-writer
def check_versions_writer(repo: Path) -> Check:
    # THE GAP IS CLOSED (Fork 7 / W3.2): release.bank_snapshot is the ONE writer
    # into the per-manuscript versions/ dir. The audit flips from reporting a named
    # gap to ENFORCING the door exists — PASS when release.bank_snapshot is present
    # and callable, WARN if it ever regressed away (staying WARN-only per this
    # module's v1 law that a check earns FAIL-gating separately, FAIL_ELIGIBLE).
    try:
        from laplace.pipeline import release
    except Exception as e:  # noqa: BLE001 — cold-import failure is the signal
        return Check("versions-writer", "WARN",
                     f"cannot import laplace.pipeline.release to check the door: {e}")
    door = getattr(release, "bank_snapshot", None)
    if callable(door):
        return Check("versions-writer", "PASS",
                     "release.bank_snapshot is the one versions_dir writer (door built)")
    return Check("versions-writer", "WARN",
                 "release.bank_snapshot absent — the versions_dir writer regressed away")


# ------------------------------------------------------------- (6) interpreter-sanity
def check_interpreter_sanity(repo: Path) -> Check:
    for rel in (("bin", "python"), ("Scripts", "python.exe")):
        py = repo / ".venv" / rel[0] / rel[1]
        if py.exists():
            rc, _out, err = _run([str(py), "-c", "import pytest, laplace"], repo)
            if rc == 0:
                return Check("interpreter-sanity", "PASS",
                             f"{py.relative_to(repo)} imports pytest + laplace")
            if rc is None:
                return Check("interpreter-sanity", "WARN",
                             f"{py.relative_to(repo)} exists but could not be launched: {err.strip()}")
            return Check("interpreter-sanity", "WARN",
                         f"{py.relative_to(repo)} cannot import pytest+laplace (rc={rc}) — "
                         "test-gate triggers silently no-op")
    return Check("interpreter-sanity", "WARN",
                 ".venv interpreter absent — any test-gate trigger silently no-ops")


# ----------------------------------------------------------- (7) voice-conformance
def check_voice_conformance(repo: Path) -> Check:
    reports = list(repo.rglob("conformance_*.json"))
    if not reports:
        return Check("voice-conformance", "WARN",
                     "no conformance_*.json artifact found (detector unwired by design)")
    newest = max(reports, key=lambda p: p.stat().st_mtime)
    try:
        data = json.loads(newest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return Check("voice-conformance", "WARN",
                     f"{newest.name} exists but is unparseable: {exc}")
    corpus = data.get("corpus") if isinstance(data, dict) else None
    if corpus:
        return Check("voice-conformance", "PASS", f"{newest.name} names corpus={corpus}")
    return Check("voice-conformance", "WARN",
                 f"{newest.name} exists but names no input corpus")


def run_all(repo: Path) -> list[Check]:
    checks: list[Check] = []
    checks.extend(check_economics_fresh(repo))
    checks.extend(check_state_present(repo))
    checks.extend(check_rounds_findable(repo))
    checks.append(check_ledger_poison(repo))
    checks.append(check_versions_writer(repo))
    checks.append(check_interpreter_sanity(repo))
    checks.append(check_voice_conformance(repo))
    return checks


def _verdict(checks: list[Check]) -> tuple[bool, list[Check], list[Check]]:
    fails = [c for c in checks if c.status == "FAIL"]
    warns = [c for c in checks if c.status == "WARN"]
    stray = [c.name for c in fails if c.name not in FAIL_ELIGIBLE]
    assert not stray, (
        f"check(s) {stray} returned FAIL but aren't in FAIL_ELIGIBLE — "
        "every seam check is WARN-only until it earns the right to gate"
    )
    return not fails, fails, warns


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "The seam-liveness gate: an advisory reporter over the silent-failure "
            "seams between the pipeline's organs (economics freshness, release "
            "state, round discovery, ledger poison, unbuilt writers, interpreter "
            "sanity, voice conformance). Never mutates anything."
        )
    )
    parser.add_argument("--repo", default=".", help="repo root to check (default: cwd)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    checks = run_all(repo)
    ok, fails, warns = _verdict(checks)

    if args.json:
        print(json.dumps(
            {"repo": str(repo), "checks": [asdict(c) for c in checks], "ok": ok},
            indent=1,
        ))
    else:
        name_w = max(len(c.name) for c in checks) if checks else 4
        print(f"audit_silent_failures — {repo}")
        print(f"{'CHECK'.ljust(name_w)}  STATUS  DETAIL")
        for c in checks:
            print(f"{c.name.ljust(name_w)}  {c.status:<6}  {c.detail}")

    if ok:
        print(f"VERDICT=PASS warns={len(warns)}")
    else:
        reasons = ",".join(c.name for c in fails)
        print(f"VERDICT=FAIL checks={len(fails)}/{len(checks)} reasons={reasons} warns={len(warns)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
