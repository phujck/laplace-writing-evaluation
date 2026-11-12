#!/usr/bin/env python3
"""Auditable redaction of an export tree before it is shown to anyone.

The problem this exists for: an export that carries transcripts carries whatever
the session happened to load - private context, third-party names, ambient
instruction files. Deleting the export destroys its provenance value; shipping it
whole breaks the perimeter. This does the third thing: it replaces matched spans
in place with a visible class marker, and emits a manifest recording how many
spans of each class were removed from which file.

The marker is the point. A reader can see that redaction happened, what class was
removed, and how much - so the record stays honest about its own alteration
rather than pretending to be pristine. The manifest carries counts only, never the
removed text, so the manifest is safe to publish alongside the tree.

Policy is data, not code (--policy, a JSON file of {class: [regex, ...]}), so this
generalises to any export and any perimeter. Re-running is idempotent: markers are
never re-matched.

    python scripts/redact_export.py <tree> --policy policy.json [--apply]

Without --apply it is a dry run and writes nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

MARKER = "[REDACTED:{cls}]"
MARKER_RE = re.compile(r"\[REDACTED:[A-Za-z0-9_-]+\]")
TEXT_SUFFIXES = {".jsonl", ".json", ".md", ".txt", ".py", ".tex", ".yaml", ".yml"}


def load_policy(path: Path) -> dict[str, list[re.Pattern]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[re.Pattern]] = {}
    for cls, pats in raw.items():
        if not isinstance(pats, list):
            raise SystemExit(f"policy class {cls!r} must map to a list of regexes")
        out[cls] = [re.compile(p, re.IGNORECASE) for p in pats]
    return out


def redact_text(text: str, policy: dict[str, list[re.Pattern]]) -> tuple[str, Counter]:
    """Apply every class to text. Existing markers are inert."""
    hits: Counter = Counter()
    guarded: list[str] = []

    def stash(m: re.Match) -> str:
        guarded.append(m.group(0))
        return f"\x00{len(guarded) - 1}\x00"

    text = MARKER_RE.sub(stash, text)
    for cls, pats in policy.items():
        marker = MARKER.format(cls=cls)
        for pat in pats:
            text, n = pat.subn(marker, text)
            if n:
                hits[cls] += n
    text = re.sub(r"\x00(\d+)\x00", lambda m: guarded[int(m.group(1))], text)
    return text, hits


def redact_jsonl(path: Path, policy) -> tuple[str | None, Counter]:
    """Redact string values inside each record, preserving JSON structure."""
    hits: Counter = Counter()
    out_lines: list[str] = []
    changed = False

    def walk(node):
        nonlocal changed
        if isinstance(node, str):
            new, h = redact_text(node, policy)
            if h:
                hits.update(h)
                changed = True
            return new
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        return node

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            out_lines.append(line)
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            new, h = redact_text(line, policy)
            hits.update(h)
            changed = changed or bool(h)
            out_lines.append(new)
            continue
        out_lines.append(json.dumps(walk(rec), ensure_ascii=False))

    return ("\n".join(out_lines) + "\n") if changed else None, hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("tree", type=Path)
    ap.add_argument("--policy", type=Path, required=True)
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--manifest", type=Path, default=None)
    args = ap.parse_args()

    policy = load_policy(args.policy)
    tree = args.tree.resolve()
    per_file: dict[str, dict[str, int]] = {}
    totals: Counter = Counter()
    scanned = 0

    for path in sorted(tree.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        scanned += 1
        if path.suffix.lower() == ".jsonl":
            new, hits = redact_jsonl(path, policy)
        else:
            original = path.read_text(encoding="utf-8", errors="replace")
            redacted, hits = redact_text(original, policy)
            new = redacted if hits else None
        if not hits:
            continue
        rel = path.relative_to(tree).as_posix()
        per_file[rel] = dict(hits)
        totals.update(hits)
        if args.apply and new is not None:
            path.write_text(new, encoding="utf-8", newline="\n")

    manifest = {
        "tree": tree.as_posix(),
        "applied": bool(args.apply),
        "files_scanned": scanned,
        "files_redacted": len(per_file),
        "spans_by_class": dict(totals),
        "spans_total": sum(totals.values()),
        "by_file": per_file,
        "note": "counts only; removed text is never recorded here",
    }
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    if args.manifest:
        args.manifest.write_text(text, encoding="utf-8", newline="\n")
    print(text)
    print(
        f"{'APPLIED' if args.apply else 'DRY RUN'}: "
        f"{sum(totals.values())} spans across {len(per_file)} files",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
