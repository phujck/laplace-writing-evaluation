"""Sweep deprecated skills into the archive once disuse is proven.

Per AUTONOMY_BACKLOG.md ("Deprecated skills are demoted but never swept"): a
skill the dreamer marks `deprecated` stays on disk, in the manifest, and in
every orient bundle's flat `available_refs` list forever - the one part of the
orient footprint that only ever grows (`available_refs` is unbounded, unlike
`rank_skills`/`rank_wiki`, which are budgeted). This sweep finds every skill
whose *effective* status is `deprecated` (lifecycle overlay wins over the
index.yaml manifest - the same precedence `Canon._discover_skills` itself
uses: lifecycle > manifest > inference), asks how long it has sat there and
whether anything has fired it since, and relocates the safely-dead ones to
`skills/_archive/<name>/`.

The archive move needs no companion filter in the assembler. Canon discovers
skills via a SINGLE-LEVEL glob, ``skills/*/SKILL.md``, which does not reach two
levels down into ``skills/_archive/<name>/SKILL.md`` - so a moved skill drops
out of ``Canon.skills``, ``available_refs``, and the weave graph purely by
relocation. This mirrors the 2026-06-02 sweep (css_forge, html_mechanic, ...
-> ``_archive/``); confirmed by re-running the orient bundle before/after (see
this script's own report, or ``python3 -c`` against ``Canon.load(...)``).

Qualification (both required):
  1. ``--min-windows`` (default 3) *dream windows* have elapsed since the skill
     became deprecated. A window is a ``dream_complete`` telemetry event after
     the deprecation timestamp. If the telemetry store has *never* recorded a
     ``dream_complete`` marker at all (a fresh/short-lived store - not evidence
     the skill is young), this falls back to whole elapsed calendar days, the
     dreamer's own day-boundary vocabulary (see telemetry.events_since_last_dream).
  2. Zero usage: no ``execute`` / ``verify_check`` telemetry event naming the
     skill since the deprecation timestamp.

The deprecation timestamp is read from lifecycle.yaml's own history (the
machine-written, exact record) when lifecycle overrides the manifest for that
skill; otherwise (deprecated by hand-editing index.yaml, no lifecycle entry)
it falls back to ``git log -L`` on the manifest line carrying that skill's
``status: deprecated``, i.e. the commit that actually deprecated it. A skill
whose timestamp cannot be determined by either path is never archived - unknown
data is never treated as "old enough".

Reversible: the move is a plain filesystem relocation (git-mv semantics - the
orchestrator stages/commits the result), so ``git mv skills/_archive/<name>
skills/<name>`` (or reverting the commit) restores it exactly. Nothing is
deleted, and index.yaml / lifecycle.yaml entries are left as-is (the same
harmless dangling-reference debt class canon_weaver already owns, per
AUTONOMY_BACKLOG's "canon verify is red on topology debt" note).

Usage:
    python3 scripts/sweep_deprecated_skills.py                  # dry-run (default)
    python3 scripts/sweep_deprecated_skills.py --dry-run
    python3 scripts/sweep_deprecated_skills.py --apply
    python3 scripts/sweep_deprecated_skills.py --min-windows 5 --apply
    python3 scripts/sweep_deprecated_skills.py --root /tmp/fixture/canon --repo-root /tmp/fixture --apply
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.pipeline.canon import Canon, canon_root  # noqa: E402
from laplace.engine import telemetry  # noqa: E402

DEFAULT_MIN_WINDOWS = 3
USAGE_PHASES = ("execute", "verify_check")


@dataclass
class SkillPlan:
    name: str
    deprecated_since: str | None
    since_source: str  # lifecycle-history | lifecycle-updated | git-blame | unknown
    windows_elapsed: int
    windows_source: str  # dream_complete | elapsed-days-fallback | n/a
    usage_since: int
    qualifies: bool
    reason: str
    src: Path
    dest: Path


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def deprecated_skills(canon: Canon) -> list[str]:
    """Skills whose *effective* status (lifecycle overlay > manifest) is deprecated."""
    return sorted(n for n, sk in canon.skills.items() if sk.status == "deprecated")


def _lifecycle_deprecated_ts(canon: Canon, name: str) -> str | None:
    life = (canon.lifecycle.get("skills", {}) or {}).get(name) or {}
    if life.get("status") != "deprecated":
        return None
    for h in reversed(life.get("history", []) or []):
        if h.get("to") == "deprecated":
            return h.get("at")
    return life.get("updated")


def _git_blame_deprecated_ts(repo_root: Path, manifest: Path, name: str) -> str | None:
    """The authored date of the commit that set ``status: deprecated`` for
    ``name`` inside the manifest - used only when no lifecycle entry exists."""
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    key = f"{name}:"
    in_block = False
    target_line: int | None = None
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if indent == 2 and stripped == key:
            in_block = True
            continue
        if in_block:
            if stripped and indent <= 2:
                break  # dedent or next top-level key: left this skill's block
            if stripped.startswith("status:") and "deprecated" in stripped:
                target_line = i
                break
    if target_line is None:
        return None
    try:
        rel = manifest.relative_to(repo_root)
    except ValueError:
        return None
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "-L",
             f"{target_line},{target_line}:{rel.as_posix()}"],
            cwd=repo_root, capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return out.stdout.splitlines()[0].strip() or None


def deprecation_timestamp(canon: Canon, repo_root: Path, name: str) -> tuple[str | None, str]:
    ts = _lifecycle_deprecated_ts(canon, name)
    if ts:
        return ts, "lifecycle-history"
    ts = _git_blame_deprecated_ts(repo_root, canon.root / "index.yaml", name)
    if ts:
        return ts, "git-blame"
    return None, "unknown"


def dream_windows_elapsed(since_ts: str) -> tuple[int, str]:
    """How many dream cycles have completed since ``since_ts``."""
    all_events = telemetry.events()
    ever_dreamed = any(e.get("phase") == "dream_complete" for e in all_events)
    if ever_dreamed:
        since_events = telemetry.events(since=since_ts)
        count = sum(1 for e in since_events if e.get("phase") == "dream_complete")
        return count, "dream_complete"
    # The store has no dream-cycle marker at all - it cannot judge cadence.
    # Approximate a window as one elapsed calendar day (the dreamer's own
    # day-boundary; see telemetry.events_since_last_dream's docstring).
    days = max(0, (datetime.now(timezone.utc) - _parse_ts(since_ts)).days)
    return days, "elapsed-days-fallback"


def usage_since(name: str, since_ts: str) -> int:
    evs = telemetry.events(since=since_ts)
    return sum(1 for e in evs if e.get("skill") == name and e.get("phase") in USAGE_PHASES)


def build_plan(canon: Canon, repo_root: Path, min_windows: int) -> list[SkillPlan]:
    plans: list[SkillPlan] = []
    archive_dir = canon.root / "skills" / "_archive"
    for name in deprecated_skills(canon):
        src = canon.root / "skills" / name
        dest = archive_dir / name
        ts, src_kind = deprecation_timestamp(canon, repo_root, name)
        if ts is None:
            plans.append(SkillPlan(
                name, None, src_kind, 0, "n/a", 0, False,
                "cannot determine a deprecation timestamp - skipped (never "
                "archived on unknown data)", src, dest))
            continue
        windows, wsrc = dream_windows_elapsed(ts)
        usage = usage_since(name, ts)
        qualifies = windows >= min_windows and usage == 0
        if qualifies:
            reason = (f"deprecated {ts} ({src_kind}); {windows} dream window(s) "
                      f"elapsed ({wsrc}) >= {min_windows}; zero usage since")
        elif usage:
            reason = (f"deprecated {ts} ({src_kind}); {usage} usage event(s) "
                      f"since deprecation - still exercised")
        else:
            reason = (f"deprecated {ts} ({src_kind}); only {windows} dream "
                      f"window(s) elapsed ({wsrc}) < {min_windows} - too recent")
        plans.append(SkillPlan(name, ts, src_kind, windows, wsrc, usage, qualifies,
                               reason, src, dest))
    return plans


def apply_plan(plans: list[SkillPlan]) -> list[SkillPlan]:
    """Move every qualifying skill (git-mv semantics: plain fs move). Returns
    the subset actually moved."""
    moved = []
    for p in plans:
        if not p.qualifies or not p.src.is_dir():
            continue
        p.dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p.src), str(p.dest))
        moved.append(p)
    return moved


def _print_plan(plans: list[SkillPlan], applied: bool) -> None:
    verb = "MOVED" if applied else "WOULD MOVE"
    any_q = False
    for p in plans:
        if p.qualifies:
            any_q = True
            print(f"[{verb}] {p.name}: {p.src} -> {p.dest}\n    {p.reason}")
        else:
            print(f"[skip] {p.name}: {p.reason}")
    if not any_q:
        print("(no deprecated skill currently qualifies)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="canon root (default: canon_root())")
    ap.add_argument("--repo-root", type=Path, default=ROOT,
                    help="repo root for the git-blame fallback (default: this repo)")
    ap.add_argument("--min-windows", type=int, default=DEFAULT_MIN_WINDOWS,
                    help=f"dream windows required since deprecation (default: {DEFAULT_MIN_WINDOWS})")
    ap.add_argument("--apply", action="store_true",
                    help="actually move qualifying skills (default: dry-run/plan only)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan only (default behaviour; explicit flag is a no-op)")
    a = ap.parse_args(argv)

    root = a.root or canon_root()
    canon = Canon.load(root)
    plans = build_plan(canon, a.repo_root, a.min_windows)

    if a.apply:
        moved = apply_plan(plans)
        _print_plan(plans, applied=True)
        print(f"\narchived {len(moved)} skill(s) to {root / 'skills' / '_archive'}")
        print("reversible: `git mv skills/_archive/<name> skills/<name>`, or revert the commit.")
    else:
        _print_plan(plans, applied=False)
        print("\n(dry-run - pass --apply to execute)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
