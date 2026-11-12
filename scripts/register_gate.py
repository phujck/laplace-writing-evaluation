"""The register gate: mechanical scan for the banned tic classes in outward prose.

Usage: python scripts/register_gate.py <file> [<file> ...] [--json]

Scans text/LaTeX files for the tic classes the register law names: oppositional
intensifiers, empty appositives, virtue adjectives, marketing verbs, vague
attribution, filler openers, and AI-prose markers. Exit 0 clean, exit 1 with a
finding list otherwise. The allowlist is the author's call: a line containing
``%REGISTER-ALLOW`` (LaTeX comment) is skipped and counted as allowlisted.

General by construction: patterns are data, files are arguments. First
instance: the engine-devplan whitepaper (2026-08-03).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# (class, pattern, note) — case-insensitive; word-ish boundaries where sensible.
PATTERNS: list[tuple[str, str, str]] = [
    ("oppositional-intensifier", r"\bnot (?:just|only|merely|simply)\b", "the 'not just X' opener"),
    ("oppositional-intensifier", r"\bisn'?t (?:just|only|merely|simply)\b", "the 'isn't just X' opener"),
    ("oppositional-intensifier", r"\bmore than (?:just|merely|simply)\b", "the 'more than just' construction"),
    ("oppositional-intensifier", r"---?\s*it(?:'s| is)\b", "the 'X --- it's Y' rhetorical turn"),
    ("empty-appositive", r"\ba testament to\b", "empty appositive"),
    ("empty-appositive", r"\bunderscor(?:es|ing)\b", "empty analysis verb"),
    ("empty-appositive", r"\bhighlight(?:s|ing) the (?:importance|significance|value|power)\b", "empty analysis phrase"),
    ("empty-appositive", r"\bspeaks to\b", "empty appositive verb"),
    ("virtue-adjective", r"\b(?:powerful|robust|seamless|cutting[- ]edge|state[- ]of[- ]the[- ]art|world[- ]class|revolutionary|transformative|game[- ]chang\w*|groundbreaking|innovative)\b", "virtue adjective"),
    ("marketing-verb", r"\b(?:unlock(?:s|ing)?|leverag(?:e|es|ing)|empower(?:s|ing)?|supercharg\w+|streamlin(?:e|es|ing))\b", "marketing verb"),
    ("vague-attribution", r"\b(?:experts (?:agree|say|believe)|many believe|it is widely (?:believed|regarded|accepted)|studies show)\b", "vague attribution"),
    ("filler", r"\bit(?:'s| is) worth noting\b", "filler opener"),
    ("filler", r"\bin today'?s (?:world|landscape|environment|market)\b", "filler scene-setting"),
    ("filler", r"\brapidly (?:evolving|changing)\b", "filler scene-setting"),
    ("self-narration", r"\bstated (?:honestly|carefully|as such|here as one)\b", "narrating the register instead of using it"),
    ("self-narration", r"\b(?:because|so that|so) the reader\b", "document talking about its reader"),
    ("self-narration", r"\bin the reader'?s line of sight\b", "document talking about its reader"),
    ("self-narration", r"\boffered as a reading\b", "candour narration"),
    ("self-certification", r"\bwithout softening\b", "candour claimed in place of candour"),
    ("self-certification", r"\bstate[d]? this plainly\b", "plainness announced instead of performed"),
    ("self-certification", r"\bplainly stated\b", "plainness announced instead of performed"),
    ("ai-marker", r"\bdelv(?:e|es|ing)\b", "AI-prose marker"),
    ("ai-marker", r"\b(?:journey|tapestry|beacon)\b", "inflated metaphor"),
    ("ai-marker", r"\bnavigat(?:e|ing) the \w+ landscape\b", "inflated metaphor"),
]

COMPILED = [(cls, re.compile(pat, re.IGNORECASE), note) for cls, pat, note in PATTERNS]
ALLOW_MARK = "%REGISTER-ALLOW"


def scan_file(path: Path) -> tuple[list[dict], int]:
    findings, allowlisted = [], 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("%") and ALLOW_MARK not in line:
            continue  # LaTeX comment lines are not outward prose
        for cls, rx, note in COMPILED:
            m = rx.search(line)
            if not m:
                continue
            if ALLOW_MARK in line:
                allowlisted += 1
                continue
            findings.append({
                "file": str(path), "line": lineno, "class": cls, "note": note,
                "match": m.group(0), "text": stripped[:160],
            })
    return findings, allowlisted


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    paths = [Path(a) for a in argv if not a.startswith("--")]
    if not paths:
        print(__doc__)
        return 2
    all_findings, total_allow = [], 0
    for p in paths:
        if not p.is_file():
            print(f"register_gate: missing file {p}", file=sys.stderr)
            return 2
        f, a = scan_file(p)
        all_findings.extend(f)
        total_allow += a
    if as_json:
        print(json.dumps({"findings": all_findings, "allowlisted": total_allow}, indent=1))
    else:
        for f in all_findings:
            print(f"[{f['class']}] {f['file']}:{f['line']}  {f['match']!r}  ::  {f['text']}")
        print(f"register_gate: {len(all_findings)} finding(s), {total_allow} allowlisted, {len(paths)} file(s)")
    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
