#!/usr/bin/env python3
"""Audit plan-class documents for environmental claims that cite no probe.

THE CLASS (his, 2026-07-16, RW-20260716-144235-142690 / RW-20260716-144417-326593):
the orchestrator patched a subagent's hedge into a plan without re-deriving against
state the wake had already banked — "nodemaps are not gitignored and travel, yet the
plan claimed absent-on-remote". Twice in one session. The behavioral fix
(probe-before-claim) got no structural guard, while the sibling failure-class from
the same night (the dispatch-model ceiling) earned ``audit_dispatch_models.py`` + a
red test. This audit is the missing guard, in that mold — repair the CLASS, not the
instance.

THE CONVENTION it enforces: an ENVIRONMENTAL CLAIM in a plan-class document — a
statement that something is absent / missing / untracked / gitignored / not present
on some tree — must carry a probe citation in the same paragraph: either the typed
marker ``[probed: <command or evidence-node>]`` or a recognizable probe reference
(a git/ls command, a localstate / VERDICT line, a ``file:line`` evidence node).
A claim with no probe is a HEDGE WEARING A FACT'S CLOTHES — exactly what let the
subagent's guess outrank banked state.

WHAT IT SCANS (the seam where the class fired): plan-class files being banked THIS
session — ARMING_*.md / PLAN_*.md that are dirty/untracked in the working tree or
dated today. ``--all`` sweeps every ARMING_*.md (advisory archaeology, expect noise
from pre-convention documents).

Run:  python3 scripts/audit_probe_before_claim.py [--all] [--root PATH]
Exit: 0 = no unprobed environmental claim in the scanned set; 1 = finding(s),
each printed file:line. The close runs this WARN-tier via close_checklist
(``probe_before_claim``) — advisory, never a hard gate (the exact gate shape
stays the author's, the reserved-to-author pattern).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: an environmental claim: present/absent/tracked-ness asserted about a tree
ENV_CLAIM_RE = re.compile(
    r"\b(?:absent(?:-on-remote)?|missing|untracked|not\s+tracked|gitignored|"
    r"does\s*n[o']t\s+exist|no\s+such\s+(?:file|dir|path)|not\s+present|"
    r"not\s+on\s+(?:the\s+)?remote|nothing\s+at\s+`)", re.I)

#: a probe citation: the typed marker, or a recognizable this-session probe ref
PROBE_REF_RE = re.compile(
    r"\[probed:[^\]]+\]|\bgit\s+(?:ls-files|status|log|show|diff)\b|\bls\s+-|"
    r"\blocalstate\b|VERDICT=|session-start probe|\bprobe[d]?\s+(?:run|this session)|"
    r"[\w/.-]+\.\w+[#:]L?\d+", re.I)

PLAN_GLOBS = ("ARMING_*.md", "PLAN_*.md")


def scan_text(text: str, path: str = "<text>") -> list[tuple[str, int, str]]:
    """Scan one document: every paragraph (blank-line block) containing an
    environmental claim but no probe citation yields one finding per claim line.
    Returns [(path, 1-based line_no, claim line)]."""
    findings: list[tuple[str, int, str]] = []
    block: list[tuple[int, str]] = []

    def flush() -> None:
        if not block:
            return
        joined = "\n".join(l for _, l in block)
        if ENV_CLAIM_RE.search(joined) and not PROBE_REF_RE.search(joined):
            for no, l in block:
                if ENV_CLAIM_RE.search(l):
                    findings.append((path, no, l.strip()))
        block.clear()

    for no, line in enumerate(text.splitlines(), 1):
        if line.strip():
            block.append((no, line))
        else:
            flush()
    flush()
    return findings


def _session_plan_files(root: Path) -> list[Path]:
    """The seam: plan-class files being banked this session — dirty/untracked in
    the working tree, or filename-dated today."""
    today = time.strftime("%Y-%m-%d")
    out: set[Path] = set()
    try:
        porcelain = subprocess.run(
            ["git", "status", "--porcelain"], cwd=str(root),
            capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        porcelain = ""
    dirty = {ln[3:].strip().strip('"') for ln in porcelain.splitlines() if len(ln) > 3}
    for glob in PLAN_GLOBS:
        for p in root.glob(glob):
            if str(p.relative_to(root)) in dirty or today in p.name:
                out.add(p)
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--all", action="store_true",
                    help="sweep every plan-class file (advisory archaeology)")
    args = ap.parse_args(argv)
    root = Path(args.root)
    files: list[Path] = []
    if args.all:
        for glob in PLAN_GLOBS:
            files.extend(sorted(root.glob(glob)))
    else:
        files = _session_plan_files(root)
    findings: list[tuple[str, int, str]] = []
    for p in files:
        findings.extend(scan_text(p.read_text(encoding="utf-8", errors="replace"),
                                  str(p.relative_to(root))))
    if findings:
        print(f"[probe-before-claim] {len(findings)} environmental claim(s) with no "
              f"probe citation (the convention: [probed: <cmd or evidence-node>]):")
        for path, no, line in findings:
            print(f"  {path}:{no}: {line[:140]}")
        return 1
    print(f"[probe-before-claim] clean: {len(files)} plan-class file(s) scanned, "
          f"every environmental claim carries a probe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
