#!/usr/bin/env python3
"""check_durable_refs.py -- the ephemeral-path lint.

Friction 400005 (corpus_friction/laplace_engine.jsonl, RW-20260711-104316-400005): "a full
task brief was banked to a session scratchpad; the container died and the brief is gone --
OPEN_STACK rows are the only surviving mirror." The defect class is not that one brief: it's
DURABLE surfaces holding references to EPHEMERAL locations -- a session scratchpad, /tmp, an
agent's home dir -- that will not exist next container. This script scans the durable surfaces
for exactly that pattern and fails the gate when a reference has no in-repo durable twin to
fall back on.

DURABLE surfaces scanned (the record that is supposed to survive a container death):
  OPEN_STACK.md, HANDOFF.md, the newest 3 SESSION_HANDOFF_*.md (by date in the filename),
  EIGEN_PROTOCOL.md, corpus_friction/*.jsonl.

EPHEMERAL patterns matched: /tmp/..., scratchpad/<path> (a session scratchpad reference),
/root/.claude/..., /root/.ccr/..., and session-scoped task-output/task_output/<path> segments.

For each hit we look for a DURABLE TWIN: a file of the same basename living anywhere else in
the repo. A hit with a twin is a WARN (the phrasing is fragile but the content is recoverable);
a hit with NO twin is a FAIL (the reference is the only copy, and it just evaporated).

ACKNOWLEDGED LOSSES: a hit whose own line carries a loss marker ("EPHEMERAL" or "container
died") is the record OF an evaporation, not a reference that will surprise-evaporate — the
friction rows documenting loss 400005 necessarily name the dead path forever in an
append-only ledger. Such hits report ACK and do not fail the gate (calibration 2026-08-07,
his to overrule).

VERDICT sentinel (scripts/paper_gates.py convention): the LAST line of output is
VERDICT=PASS or VERDICT=FAIL ..., mirrored in the exit code, so a truncated read (tail -1)
still carries the whole verdict.

Usage:
    python scripts/check_durable_refs.py [--root PATH] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name -> pattern. Ordered specific-before-general: a more specific pattern (e.g. an absolute
# /tmp/.../scratchpad/... path) should claim the match before the bare "scratchpad/" pattern
# re-matches the same span as a second, redundant hit.
EPHEMERAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("claude_home", re.compile(r"/root/\.claude/[^\s`'\")]+")),
    ("ccr_home", re.compile(r"/root/\.ccr/[^\s`'\")]+")),
    ("tmp_path", re.compile(r"/tmp/[^\s`'\")]+")),
    ("task_output", re.compile(r"\btask[-_]output/[\w.\-/]+")),
    ("scratchpad", re.compile(r"\bscratchpad/[\w.\-/]+")),
]

# trailing characters that are prose/markdown punctuation riding along on the match, not part
# of the path itself (closing backtick, paren, quote, sentence-ending punctuation, etc).
_TRAILING_PUNCT = ".,;:)]}\"'`*"

_SESSION_HANDOFF_RE = re.compile(r"^SESSION_HANDOFF_(\d{4}-\d{2}-\d{2})_.*\.md$")

# a loss acknowledged on the hit's own line (see module docstring, ACKNOWLEDGED LOSSES).
_ACK_RE = re.compile(r"EPHEMERAL|container died", re.IGNORECASE)


@dataclass
class Hit:
    file: str        # relative to root
    line: int
    kind: str
    path: str         # the ephemeral path text, punctuation-stripped
    twin: str | None  # relative path of the durable twin, if any
    ack: bool = False  # loss acknowledged on the line itself


def _strip_trailing_punct(s: str) -> str:
    while s and s[-1] in _TRAILING_PUNCT:
        s = s[:-1]
    return s


def durable_surfaces(root: Path) -> list[Path]:
    """The durable surfaces to scan: OPEN_STACK.md, HANDOFF.md, the newest 3
    SESSION_HANDOFF_*.md (by date in the filename), EIGEN_PROTOCOL.md, corpus_friction/*.jsonl.
    Missing files are silently skipped (a fixture root need not carry all of them)."""
    surfaces: list[Path] = []
    for name in ("OPEN_STACK.md", "HANDOFF.md", "EIGEN_PROTOCOL.md"):
        p = root / name
        if p.is_file():
            surfaces.append(p)

    dated = []
    for p in root.glob("SESSION_HANDOFF_*.md"):
        m = _SESSION_HANDOFF_RE.match(p.name)
        if m:
            dated.append((m.group(1), p.name, p))
    dated.sort(key=lambda t: (t[0], t[1]), reverse=True)
    surfaces.extend(p for _, _, p in dated[:3])

    friction_dir = root / "corpus_friction"
    if friction_dir.is_dir():
        surfaces.extend(sorted(friction_dir.glob("*.jsonl")))

    return surfaces


def _find_twin(root: Path, basename: str) -> Path | None:
    """A durable twin: a file of the same basename living anywhere in the repo (excluding
    .git). Returns the first match, or None."""
    if not basename:
        return None
    for p in root.rglob(basename):
        if p.is_file() and ".git" not in p.parts:
            return p
    return None


def scan(root: Path) -> list[Hit]:
    hits: list[Hit] = []
    for surface in durable_surfaces(root):
        try:
            lines = surface.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            covered: list[tuple[int, int]] = []
            for kind, pattern in EPHEMERAL_PATTERNS:
                for m in pattern.finditer(line):
                    start, end = m.span()
                    if any(start < c_end and end > c_start for c_start, c_end in covered):
                        continue  # already claimed by a more specific pattern on this line
                    covered.append((start, end))
                    raw = _strip_trailing_punct(m.group(0))
                    if not raw:
                        continue
                    basename = Path(raw.rstrip("/")).name
                    twin = _find_twin(root, basename)
                    hits.append(Hit(
                        file=str(surface.relative_to(root)),
                        line=lineno,
                        kind=kind,
                        path=raw,
                        twin=str(twin.relative_to(root)) if twin else None,
                        ack=bool(_ACK_RE.search(line)),
                    ))
    return hits


def _verdict(hits: list[Hit]) -> tuple[bool, list[Hit]]:
    failing = [h for h in hits if h.twin is None and not h.ack]
    return not failing, failing


def render_report(hits: list[Hit]) -> str:
    if not hits:
        return "(no ephemeral-path references found on the durable surfaces)"
    lines = []
    for h in hits:
        if h.twin:
            level, detail = "WARN", f"twin={h.twin}"
        elif h.ack:
            level, detail = "ACK", "loss acknowledged on the line"
        else:
            level, detail = "FAIL", "no durable twin"
        lines.append(f"{h.file}:{h.line}  [{h.kind}] {h.path}  -- {level} ({detail})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=ROOT,
                     help="repo root to scan (default: the laplace repo root)")
    ap.add_argument("--json", action="store_true",
                     help="emit the hits as a JSON array instead of the human-readable list")
    a = ap.parse_args(argv)

    root = a.root.resolve()
    hits = scan(root)
    ok, failing = _verdict(hits)

    if a.json:
        print(json.dumps([h.__dict__ for h in hits], indent=1, ensure_ascii=False))
    else:
        print(render_report(hits))

    n_warn = len(hits) - len(failing)
    if ok:
        print(f"VERDICT=PASS hits={len(hits)} warn={n_warn}")
    else:
        print(f"VERDICT=FAIL hits={len(hits)} fail={len(failing)} warn={n_warn}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
