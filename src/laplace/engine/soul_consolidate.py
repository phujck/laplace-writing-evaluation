"""soul_consolidate.py - the SEALED upward operator over the soul-shard index.

The conjugate of ``soul_shard`` (which shards DOWN). This grades UP: the chunk pile is pushed to the
bottom grade and navigable coarse nodes are lifted above it, so no single level is a hairball as the
dump swells (his warning, 2026-06-08: *be prepared to consolidate and grade, to push down the lower
levels; it's going to be hard*).

The grade model:

    grade 3  the soul conceptric (1 root)
    grade 2  STREAMS            chat_logs / personal_writing / claude_chats / proposals
    grade 1  UNITS              a coherent document or conversation - the navigable middle
    grade 0  CHUNKS             the char-range leaves, sealed, recovered by re-reading (soul_shard)

The load-bearing move is the **UNIT** grade. Most sources are one unit (a tex piece, a chat log). The
one hairball - ``conversations.json``, 15k of the 17.5k chunks - is a top-level JSON array, so it is
graded along its OWN structure: each conversation is a unit, found by ``json.JSONDecoder.raw_decode``
(exact char-spans, no re-serialise, no content kept). 15,251 flat chunks become N conversation-units.

Sealed by construction: the structural grades read the raw only to find element BOUNDARIES (offsets,
counts) - never content rises. The semantic axis-grade (clustering units along the generated axes) is
a sealed-sub hook, not done here. The faithfulness gate is **LOCAL** - sample a node's members and
check they reconstruct - never the O(N^2) all-pairs sweep that the watchdog timeout warned of.

What is too wide to grade mechanically is FLAGGED (``reshape_flags``) for the semantic pass - the
proxy for the reshape signal phi (F1, his); the threshold stays his.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import bisect
import hashlib
import json
from pathlib import Path
from typing import Any

from laplace.engine import soul_shard

GRADED_LOCAL = "archive/soul_dump/_shard/graded.json"   # TRACKED since THE UNSEAL (2026-07-12, PV-20260712-unseal) - the rich grade tree
SKELETON = "soul_corpus/_graded_skeleton.md"            # committed, structural - counts only
DEFAULT_MAX_WIDTH = 200   # a level wider than this is flagged for the semantic (axis) regrade


# ---------------------------------------------------------------------------
# unit boundaries - the structure-aware middle grade (no content rises)
# ---------------------------------------------------------------------------

def _top_level_array_ranges(text: str) -> list[tuple[int, int]]:
    """Exact char-spans of a top-level JSON array's elements, via ``raw_decode`` (which returns the
    end index of each value). Handles ``[...]``. Returns [] if the text is not a leading array.

    Only the (start, end) offsets are kept - the decoded element is discarded, so no content rises."""
    lb = text.find("[")
    if lb < 0:
        return []
    # the array must be the leading structure (claude export is a top-level array); a stray '[' inside
    # a leading object would mis-seek, so require only whitespace before it.
    if text[:lb].strip():
        return []
    dec = json.JSONDecoder()
    n = len(text)
    i = lb + 1
    out: list[tuple[int, int]] = []
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n or text[i] == "]":
            break
        try:
            _obj, end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            break
        out.append((i, end))
        i = end
    return out


def _assign_units(repo_root: Path, shards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group chunks into UNITS (grade 1). Most sources are one unit; a top-level-array JSON source is
    split into one unit per element (each chunk joins the unit whose char-span contains its start)."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for sh in shards:
        by_source.setdefault(sh["source"], []).append(sh)

    units: dict[str, dict[str, Any]] = {}
    for source, chunks in by_source.items():
        path = repo_root / source
        ranges: list[tuple[int, int]] = []
        # Array-range only a JSON that was actually byte-chunked into many leaves (the generic path).
        # A Claude export is now exploded UPSTREAM into per-conversation transcripts (soul_shard) and
        # its source demoted to a single asset chunk - so len(chunks)<=1 here, and we must NOT re-read
        # the 90 MB blob to range a node that has nothing to distribute. The transcripts grade as their
        # own one-unit-per-conversation sources below; this stays the fallback for any unexploded array.
        if path.suffix.lower() == ".json" and path.is_file() and len(chunks) > 1:
            ranges = _top_level_array_ranges(soul_shard._read(path))
        if len(ranges) > 1:
            starts = [a for a, _b in ranges]
            for sh in chunks:
                j = bisect.bisect_right(starts, sh["start"]) - 1
                j = max(0, j)
                uid = f"{source}#u{j:05d}"
                u = units.setdefault(uid, {"unit": uid, "stream": sh["category"], "source": source,
                                          "chunk_ids": [], "n_chars": 0})
                u["chunk_ids"].append(sh["id"])
                u["n_chars"] += sh["n_chars"]
        else:
            u = units.setdefault(source, {"unit": source, "stream": chunks[0]["category"],
                                          "source": source, "chunk_ids": [], "n_chars": 0})
            for sh in chunks:
                u["chunk_ids"].append(sh["id"])
                u["n_chars"] += sh["n_chars"]
    return units


# ---------------------------------------------------------------------------
# the grade tree + its width report (the reshape proxy)
# ---------------------------------------------------------------------------

def build_graded(repo_root: Path | str) -> dict[str, Any]:
    """Assemble the graded conceptric from the soul-shard index: streams -> units -> chunk ids."""
    repo_root = Path(repo_root)
    shards = soul_shard.load_local_index(repo_root)
    units = _assign_units(repo_root, shards)
    streams: dict[str, list[str]] = {}
    for uid, u in units.items():
        streams.setdefault(u["stream"], []).append(uid)
    return {"streams": streams, "units": units, "n_chunks": len(shards)}


def grade_stats(graded: dict[str, Any], max_width: int = DEFAULT_MAX_WIDTH) -> dict[str, Any]:
    """Width per level + the reshape flags - which nodes are too wide to leave un-regraded (the proxy
    for phi: a too-wide grade is an under-hierarchialised one). The threshold stays the author's."""
    streams, units = graded["streams"], graded["units"]
    unit_widths = {uid: len(u["chunk_ids"]) for uid, u in units.items()}
    stream_widths = {s: len(uids) for s, uids in streams.items()}
    flags = []
    for s, w in stream_widths.items():
        if w > max_width:
            flags.append({"node": f"stream:{s}", "grade": 2, "children": w,
                          "why": "too many units - needs a mid grade (by time / by axis)"})
    for uid, w in unit_widths.items():
        if w > max_width:
            # ``node`` keeps the raw uid for LOCAL use (it indexes graded.json); ``stream`` carries the
            # non-PII category so the committed skeleton can label the flag content-free (a unit uid is
            # a raw source path - a chat-log filename names a person, so it must never be committed).
            flags.append({"node": f"unit:{uid}", "stream": units[uid]["stream"], "grade": 1,
                          "children": w, "why": "too many chunks - the unit itself needs sub-grading"})
    return {
        "n_chunks": graded["n_chunks"],
        "n_units": len(units),
        "n_streams": len(streams),
        "max_unit_width": max(unit_widths.values()) if unit_widths else 0,
        "max_stream_width": max(stream_widths.values()) if stream_widths else 0,
        "stream_widths": dict(sorted(stream_widths.items(), key=lambda kv: -kv[1])),
        "reshape_flags": sorted(flags, key=lambda f: -f["children"]),
    }


# ---------------------------------------------------------------------------
# the LOCAL faithfulness gate - sample, never all-pairs (the O(N^2) sweep won't scale)
# ---------------------------------------------------------------------------

def local_faithfulness(repo_root: Path | str, graded: dict[str, Any], k: int = 3) -> dict[str, Any]:
    """Sample k chunks from each unit and confirm they reconstruct (exact range recovered). O(units*k),
    not O(N^2). The STRUCTURAL half of the gate (pointers resolve); the semantic half - does a unit's
    coarse handle capture its members - is a sealed sub, briefed separately, not run here.

    Deterministic sampling (evenly spaced, no RNG - scripts forbid Math.random and it must be
    reproducible): the first, middle, and last members stress the unit's span."""
    repo_root = Path(repo_root)
    shards = soul_shard.load_local_index(repo_root)
    by_id = {s["id"]: s for s in shards}
    checked = recovered = 0
    bad: list[str] = []
    for uid, u in graded["units"].items():
        ids = u["chunk_ids"]
        if not ids:
            continue
        picks = sorted({0, len(ids) // 2, len(ids) - 1})[:k]
        for p in picks:
            cid = ids[p]
            checked += 1
            sh = by_id.get(cid)
            if sh and sh["end"] <= sh["start"]:
                recovered += 1   # an empty leaf is vacuously fine
                continue
            text = soul_shard.reconstruct(repo_root, cid, shards)
            if sh and len(text) == sh["n_chars"] and text:
                recovered += 1
            else:
                bad.append(cid)
    return {"pass": not bad, "units": len(graded["units"]), "sampled": checked,
            "recovered": recovered, "bad": bad[:10]}


# ---------------------------------------------------------------------------
# persist - sealed local grade tree (gitignored) + committed structural skeleton
# ---------------------------------------------------------------------------

def write_graded_local(repo_root: Path | str, graded: dict[str, Any]) -> Path:
    repo_root = Path(repo_root)
    out = repo_root / GRADED_LOCAL
    out.parent.mkdir(parents=True, exist_ok=True)
    # streams -> unit ids, and unit -> chunk ids; the leaves are pointers, no content
    payload = {"streams": graded["streams"],
               "units": {uid: {"stream": u["stream"], "source": u["source"],
                               "chunks": u["chunk_ids"], "n_chars": u["n_chars"]}
                         for uid, u in graded["units"].items()}}
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out


def _safe_flag_label(flag: dict[str, Any]) -> str:
    """A CONTENT-FREE label for a reshape flag on the committed skeleton. A ``stream:`` node is a
    category name (chat_logs / personal_writing / ...) - non-PII, kept. A ``unit:`` node is a raw
    source path (a chat-log filename names a person) - so it is replaced by its non-PII stream plus a
    stable opaque id (a hash of the uid), which still distinguishes the flags and cross-references
    graded.json, without committing the name. The seal: the skeleton is counts + widths, never a path."""
    node = flag["node"]
    if node.startswith("unit:"):
        uid = node[len("unit:"):]
        h = hashlib.sha1(uid.encode("utf-8")).hexdigest()[:8]
        stream = flag.get("stream", "?")
        return f"unit in `{stream}` · id {h}"
    return node  # stream:<category> - a non-PII level name


def write_skeleton(repo_root: Path | str, stats: dict[str, Any]) -> Path:
    repo_root = Path(repo_root)
    out = repo_root / SKELETON
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Soul-dump graded skeleton (structural, no content)",
        "",
        "<!-- COMMITTED, content-free. The graded conceptric over the sealed soul shards: the chunk",
        "pile is pushed DOWN to grade 0 (recoverable leaves), navigable UNITS lifted at grade 1, and",
        "STREAMS at grade 2. Counts + widths only - the rich tree and every leaf are in the gitignored",
        "local layer (archive/soul_dump/_shard/graded.json). His warning made operational: no level a",
        "hairball; what is still too wide is FLAGGED for the semantic (axis) regrade. -->",
        "",
        f"- **grade 0 — chunks:** {stats['n_chunks']:,} (sealed leaves, recovered by re-read)",
        f"- **grade 1 — units:** {stats['n_units']:,} (max width {stats['max_unit_width']:,} chunks)",
        f"- **grade 2 — streams:** {stats['n_streams']} (max width {stats['max_stream_width']:,} units)",
        "",
        "## Stream widths (units per stream)",
        "",
    ]
    for s, w in stats["stream_widths"].items():
        lines.append(f"- `{s}`: {w:,} units")
    lines += ["", "## Reshape flags (too wide → the semantic axis-regrade, φ/F1 the threshold, his)", ""]
    if stats["reshape_flags"]:
        for f in stats["reshape_flags"]:
            lines.append(f"- **{_safe_flag_label(f)}** (grade {f['grade']}): {f['children']:,} children — {f['why']}")
    else:
        lines.append("- none — every level is within the width bound.")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def default_repo_root() -> Path:
    return source_tree()


def main(argv: list[str]) -> int:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    root = default_repo_root()
    graded = build_graded(root)
    stats = grade_stats(graded)
    write_graded_local(root, graded)
    write_skeleton(root, stats)
    gate = local_faithfulness(root, graded)
    print(json.dumps({"stats": stats, "gate": gate}, ensure_ascii=False, indent=2))
    return 0 if gate["pass"] else 1


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
