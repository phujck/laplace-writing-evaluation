"""Flatten a large corpus into a navigable, size-bounded skeleton.

The problem this solves: a dense source tree, a multi-file repository, a tarball
of papers - too large to read in one context pass, and you do not yet know what
is in it, so you cannot target a distillation. [`reference_archaeologist`] distils
ONE known source's content past its framing; this maps an UNKNOWN large corpus
*first*, so you know what is there before you spend a pass reading it. The two are
distinct stages, not duplicates: scout, then distil.

What it emits, into a cache OUTSIDE git (the voice-corpus firewall pattern - raw
stays cached, only the skeleton surfaces into a working context):

* ``manifest.json`` - the full file tree with sizes, line counts, and a coarse
  type per file. The map.
* ``skeleton.md`` - a bounded structural digest: headings for prose/markdown,
  ``def`` / ``class`` / ``function`` / ``export`` signatures for code, the first
  non-empty lines for anything else. Bounded by a total budget, and any
  truncation is stated, never silent.
* ``chunks.txt`` - a reading order (largest-signal files first) so a reader agent
  processes the corpus in deliberate passes rather than one impossible gulp.

Decoupled and host-executed: standard library only, no network, no external API.
A ``.tar`` / ``.tar.gz`` / ``.zip`` target is extracted to a temp dir first.

Usage:
    python flatten_corpus.py <dir-or-archive> [--out <cache-dir>] [--budget <bytes>]
"""

from __future__ import annotations

import json
import os
import re
import sys
import tarfile
import tempfile
import zipfile

_CODE_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".go", ".rs", ".java", ".c", ".cpp", ".h"}
_PROSE_EXT = {".md", ".markdown", ".rst", ".txt", ".tex"}
_SKIP_DIRS = {".git", "node_modules", "dist", ".venv", "__pycache__", "build", ".next", "vendor"}
_SIG_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|function|func|fn|interface|type|struct|impl|"
    r"public|private|protected|const\s+\w+\s*=\s*(?:async\s*)?\()\b.*",
)
_HEADING_RE = re.compile(r"^(#{1,6}\s+\S|={3,}$|-{3,}$|\\(?:sub)*section\*?\{)")
_DEFAULT_BUDGET = 200_000  # bytes of skeleton; a corpus larger than this is summarised


def _coarse_type(ext: str) -> str:
    if ext in _CODE_EXT:
        return "code"
    if ext in _PROSE_EXT:
        return "prose"
    return "other"


def _read(path: str) -> str | None:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeError, OSError):
            continue
    return None


def _skeleton_of(text: str, kind: str, max_lines: int = 40) -> list[str]:
    lines = text.split("\n")
    out: list[str] = []
    if kind == "code":
        for ln in lines:
            if _SIG_RE.match(ln):
                out.append(ln.strip()[:160])
    elif kind == "prose":
        for ln in lines:
            if _HEADING_RE.match(ln.strip()) or _HEADING_RE.match(ln):
                out.append(ln.strip()[:160])
    if not out:  # no structure found - take the first non-empty lines as a sample
        out = [ln.strip()[:160] for ln in lines if ln.strip()][:8]
    if len(out) > max_lines:
        out = out[:max_lines] + [f"... (+{len(out) - max_lines} more)"]
    return out


def _walk(root: str) -> list[dict]:
    entries: list[dict] = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for f in sorted(files):
            full = os.path.join(dirpath, f)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            ext = os.path.splitext(f)[1].lower()
            rel = os.path.relpath(full, root).replace("\\", "/")
            text = _read(full)
            entries.append({
                "path": rel,
                "bytes": size,
                "lines": text.count("\n") + 1 if text else 0,
                "type": _coarse_type(ext),
                "_text": text,
                "_ext": ext,
            })
    return entries


def _extract_if_archive(target: str, workdir: str) -> str:
    low = target.lower()
    if low.endswith((".tar", ".tar.gz", ".tgz")):
        with tarfile.open(target) as tf:
            tf.extractall(workdir, filter="data")
        return workdir
    if low.endswith(".zip"):
        with zipfile.ZipFile(target) as zf:
            zf.extractall(workdir)
        return workdir
    return target


def scout(target: str, out_dir: str, budget: int) -> dict:
    with tempfile.TemporaryDirectory() as work:
        root = _extract_if_archive(target, work)
        if not os.path.isdir(root):
            print(f"Error: {target} is not a directory or supported archive.", file=sys.stderr)
            sys.exit(2)
        entries = _walk(root)

        # Reading order: signal-bearing files first (prose + code), largest first
        # within each, so a reader spends its first pass where the meaning is.
        rank = {"prose": 0, "code": 1, "other": 2}
        entries.sort(key=lambda e: (rank[e["type"]], -e["bytes"]))

        os.makedirs(out_dir, exist_ok=True)
        manifest = [{k: e[k] for k in ("path", "bytes", "lines", "type")} for e in entries]
        with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump({"target": target, "file_count": len(entries),
                       "total_bytes": sum(e["bytes"] for e in entries),
                       "files": manifest}, fh, indent=2)

        skeleton: list[str] = [f"# Corpus skeleton: {os.path.basename(target.rstrip('/\\\\')) or target}",
                               f"\n{len(entries)} files, {sum(e['bytes'] for e in entries):,} bytes total.\n"]
        used = len("\n".join(skeleton))
        truncated = 0
        chunks: list[str] = []
        for e in entries:
            if e["type"] == "other" or not e["_text"]:
                continue
            block = [f"\n## {e['path']}  ({e['type']}, {e['lines']} lines)"]
            block += [f"  {s}" for s in _skeleton_of(e["_text"], e["type"])]
            blob = "\n".join(block)
            if used + len(blob) > budget:
                truncated += 1
                continue
            skeleton.append(blob)
            used += len(blob)
            chunks.append(e["path"])
        if truncated:
            skeleton.append(f"\n... ({truncated} more file(s) omitted - skeleton budget {budget:,} bytes "
                            f"reached; raise --budget or read them from chunks.txt).")
        with open(os.path.join(out_dir, "skeleton.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(skeleton))
        with open(os.path.join(out_dir, "chunks.txt"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(chunks))

        return {"files": len(entries), "skeletonised": len(chunks),
                "omitted": truncated, "out": out_dir}


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("Usage: python flatten_corpus.py <dir-or-archive> [--out <dir>] [--budget <bytes>]",
              file=sys.stderr)
        return 2
    target = args[0]
    if not os.path.exists(target):
        print(f"Error: {target} does not exist.", file=sys.stderr)
        return 2
    out_dir = ".laplace_corpus_cache/" + (os.path.basename(target.rstrip("/\\")) or "corpus")
    budget = _DEFAULT_BUDGET
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    if "--budget" in argv:
        budget = int(argv[argv.index("--budget") + 1])
    res = scout(target, out_dir, budget)
    print(f"# Deep Corpus Scout")
    print("*" * 50)
    print(f"Scanned {res['files']} files. Skeletonised {res['skeletonised']}, "
          f"omitted {res['omitted']} (budget).")
    print(f"Cache: {res['out']}/  (skeleton.md, manifest.json, chunks.txt)")
    print("Next: read skeleton.md to map the corpus, then distil targeted files "
          "(reference_archaeologist) in chunks.txt order.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
