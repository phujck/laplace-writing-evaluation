"""Digest a raw transcript into distilled stubs along several partitions.

The mouth of the knowledge-digestion pipeline (canon://workflow/knowledge_digestion):
raw transcript -> DIGEST (here) -> level_tender (locate + lift/lower) -> the_librarian
(recommend couplings) -> the conceptric, with the raw transcript moved to archival
storage for historic provenance.

What this does, mechanically (the judged distillation is host/agent-run, like
deep_corpus_scout's skeleton): it segments a transcript into turns, classifies each
line into the controlled PARTITIONS by marker heuristics, and emits a bounded
*skeleton* of candidate stubs per partition for a reader to distil - plus an
immutable archival *manifest* (id, sha256, size, date, partition counts). With
--archive it copies the raw transcript to the archive verbatim. It never distils a
stub itself - degrade to candidates, never guess the meaning.

Stdlib-only, in the structured-ledger style of the other laplace scripts.

Usage:
    python digest.py <transcript.md> [--out <digest-dir>] [--archive <archive-dir>]
                     [--id <id>] [--budget <bytes>]
"""

import hashlib
import json
import os
import re
import sys
from datetime import date

# The controlled partitions - the lenses a transcript is distilled along. A line
# may land in several. `concepts` is the substantive residue that becomes corpus
# stubs; the rest route to forks/todos/voice/retention as the pipeline needs.
PARTITIONS = ["concepts", "decisions", "forks", "todos", "author_voice", "retention"]

_MARKERS = {
    "decisions": re.compile(
        r"\b(decided|settled|we'?ll go|let'?s go|chose|choosing|approved|going with|"
        r"the call is|recommend(?:ed)?|keep the|hold all|confirmed)\b", re.I),
    "forks": re.compile(
        r"\b(fork|defer(?:red)?|open question|open problem|undecided|your call|"
        r"author'?s call|tbd|to be decided|still open|priority[- ]zero|leave .* open)\b", re.I),
    "todos": re.compile(
        r"\b(todo|next move|next session|next step|when (?:i'?m |we'?re )?back|"
        r"action item|first task|we (?:should|need to|will|must)|build (?:a|the|me))\b", re.I),
    "author_voice": re.compile(
        r"\b(i think|i feel|i realise|i realize|i want|i hope|i made a mistake|"
        r"honestly|much love|in my (?:taste|judgement|view)|my (?:mistake|sense|instinct))\b", re.I),
    "retention": re.compile(
        r"\b(kept|rewritten|bypassed|survived|retention|did .* survive|"
        r"hand[- ]corrected|earned|not a loss)\b", re.I),
}
# A concept candidate: a declarative, definition-like sentence not better explained
# as one of the routing partitions above.
_CONCEPT = re.compile(r"\b(is|are|means|defines?|because|so that|the .+ is|implies)\b", re.I)
# A speaker turn: "Name:" / "**Name:**" / "## Name" at the line head.
_TURN = re.compile(r"^\s*(?:\*\*)?([A-Za-z][\w .'-]{0,40}?)(?:\*\*)?\s*:\s*(.*)$")
_AUTHOR_NAMES = {"gerard", "author", "user"}

_DEFAULT_BUDGET = 120_000


def read_safe(path):
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeError, OSError):
            continue
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _sentences(text):
    # Lightweight sentence split - good enough to bucket lines, not a parser.
    parts = re.split(r"(?<=[.!?])\s+|\n", text)
    return [s.strip() for s in parts if s.strip()]


def segment(text):
    """Return list of (speaker_or_None, line) in order, carrying the current speaker
    forward across continuation lines."""
    out = []
    speaker = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _TURN.match(line)
        if m and len(m.group(1).split()) <= 4:
            speaker = m.group(1).strip().lower()
            body = m.group(2).strip()
            if body:
                out.append((speaker, body))
        else:
            out.append((speaker, line.strip()))
    return out


def classify(speaker, line):
    """Which partitions this line lands in (a set)."""
    hits = set()
    for name, rx in _MARKERS.items():
        if rx.search(line):
            hits.add(name)
    if speaker in _AUTHOR_NAMES:
        # An author turn is voice by attribution, plus whatever markers it carries.
        hits.add("author_voice")
    # Concept residue: a declarative sentence not already routed to forks/todos.
    if _CONCEPT.search(line) and len(line) > 40 and not (hits & {"forks", "todos"}):
        hits.add("concepts")
    return hits


def digest(path, out_dir, archive_dir, tid, budget):
    if not os.path.exists(path):
        print(f"Error: {path} not found.", file=sys.stderr)
        return 2
    text = read_safe(path)
    tid = tid or re.sub(r"[^A-Za-z0-9_-]", "_", os.path.splitext(os.path.basename(path))[0])
    segs = segment(text)

    buckets = {p: [] for p in PARTITIONS}
    for speaker, line in segs:
        for s in _sentences(line):
            for p in classify(speaker, s):
                buckets[p].append((speaker, s))

    os.makedirs(out_dir, exist_ok=True)
    # Archival manifest - the immutable provenance record.
    manifest = {
        "id": tid,
        "source": os.path.basename(path),
        "sha256": hashlib.sha256(text.encode("utf-8", "replace")).hexdigest(),
        "bytes": len(text.encode("utf-8", "replace")),
        "lines": text.count("\n") + 1,
        "turns": len(segs),
        "digested": date.today().isoformat(),
        "scout": "eigen",
        "partition_counts": {p: len(v) for p, v in buckets.items()},
        "archived_to": None,
    }

    # Archive the raw verbatim (the firewall pattern - raw stays archived, only the
    # distilled stubs surface into the working conceptric).
    if archive_dir:
        os.makedirs(archive_dir, exist_ok=True)
        dst = os.path.join(archive_dir, f"{tid}.md")
        with open(dst, "w", encoding="utf-8") as f:
            f.write(text)
        manifest["archived_to"] = dst

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # The skeleton - candidate stubs per partition, bounded, truncation stated.
    lines_out = [f"# Digest skeleton: {tid}",
                 f"\n{len(segs)} turns, {manifest['lines']} lines. "
                 f"Candidates per partition (distil these into stubs - do not take them verbatim):\n"]
    used = len("\n".join(lines_out))
    for p in PARTITIONS:
        rows = buckets[p]
        block = [f"\n## {p}  ({len(rows)} candidate(s))"]
        shown, truncated = 0, 0
        for speaker, s in rows:
            row = f"- " + (f"[{speaker}] " if speaker else "") + s[:240]
            if used + len(row) > budget:
                truncated += 1
                continue
            block.append(row)
            used += len(row)
            shown += 1
        if truncated:
            block.append(f"  ... (+{truncated} more - skeleton budget {budget:,} bytes reached)")
        lines_out.append("\n".join(block))
    with open(os.path.join(out_dir, "skeleton.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines_out))

    print(f"# Transcript digest: {tid}")
    print("*" * 50)
    print(f"Turns: {len(segs)} | " + " | ".join(f"{p}: {len(buckets[p])}" for p in PARTITIONS))
    print(f"Skeleton: {out_dir}/skeleton.md   Manifest: {out_dir}/manifest.json")
    if manifest["archived_to"]:
        print(f"Archived raw -> {manifest['archived_to']}")
    print("Next: distil the skeleton's concept candidates into stubs, then run "
          "level_tender to locate and place each in the conceptric, then hand to the_librarian.")
    return 0


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print("Usage: python digest.py <transcript.md> [--out <dir>] [--archive <dir>] "
              "[--id <id>] [--budget <bytes>]", file=sys.stderr)
        return 2
    path = args[0]
    out_dir = ".laplace_digest/" + re.sub(r"[^A-Za-z0-9_-]", "_", os.path.splitext(os.path.basename(path))[0])
    archive_dir = None
    tid = None
    budget = _DEFAULT_BUDGET
    if "--out" in argv:
        out_dir = argv[argv.index("--out") + 1]
    if "--archive" in argv:
        archive_dir = argv[argv.index("--archive") + 1]
    if "--id" in argv:
        tid = argv[argv.index("--id") + 1]
    if "--budget" in argv:
        budget = int(argv[argv.index("--budget") + 1])
    return digest(path, out_dir, archive_dir, tid, budget)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
