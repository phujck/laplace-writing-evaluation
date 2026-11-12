"""record_shard.py - the locatored verbatim floor for MY OWN record (the weld, slice 1).

The self-record weld runs my record through the SAME fold discipline as his (no self-exemption -
the temptation to trust my own prose because I wrote it is the paraphrased-floor sin in first
person). This module is the one operator's chunking face turned on the COMMITTED self-record:
the dated session handoffs + the diary, atomised into char-range chunks exactly like
``soul_shard`` atomised his dump - every atom a locator into the real committed text, recovery
by re-reading the exact range, never a paraphrase.

The atoms ride the keeper as virtual ``<file>::<i>`` nodes (the ``concept_lens`` atom precedent -
``atom_parent`` already routes any ``::`` id to its cluster), so the graded tree gains a floor
BELOW the record files: series(g2) -> dated handoff(g1, authored) -> atoms(g0). Coupling is
structural (``inrecord::<file>`` - same-file siblings share substrate, the ``inpaper::`` pattern)
plus the first genuine weld wire: a mechanical ``recdate::<yyyy-mm-dd>`` token shared by every
atom of the same DAY - the diary's entry and that day's handoffs couple through the day they
record, derived from filenames and headings, nothing invented.

No seal here: the sources are public, committed git text (the soul's floor stays where it is,
sealed; this is MY record). The floor index (``.self_record_floor.jsonl``) is a regenerable
gitignored cache, like the graded tree and the embeddings - the committed files ARE the raw.

Mechanical throughout: no LLM, deterministic, idempotent. Trait tagging and the value-axis
producer (the weld's semantic slices) build ON this floor; they are not here.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import re
from pathlib import Path
from typing import Any

FLOOR_INDEX = ".self_record_floor.jsonl"   # gitignored - regenerable; the committed files are the raw
ATOM_SEP = "::"                            # the concept_lens virtual-atom convention, reused
_TARGET = 6000                             # oversize sections sub-split near this (soul_shard's target)
_ESSENCE_CAP = 320                         # an atom handle is a glance, not the chunk
_KW_CAP = 14
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_HEAD_RE = re.compile(r"(?m)^(#{1,3})\s+(.+)$")


def record_sources(repo_root: Path | str) -> list[str]:
    """The committed self-record files the floor atomises: every dated session handoff (wherever
    it strays - two early ones live in ``src/laplace``; deliberate ``archive/`` copies excluded)
    + the diary + the LIVE state documents (HANDOFF.md, OPEN_STACK.md).

    HANDOFF.md / OPEN_STACK.md were previously kept whole ("living state, not record mass"). His
    directive (2026-06-13, "fold the self - it should self-reconstruct"): the clean-room proved the
    wake PASTES the whole 1663-line HANDOFF.md ("a routing wrapper around a flat read"). Atomising
    them folds the live self into routable atoms - the next-aim and each fork become `<file>::<i>`
    nodes the wake can reconstruct and the navigator can show as a mind, not a blob. The floor is a
    gitignored regenerable cache, so the live-doc churn (char-ranges shift each session) is free -
    rebuild re-derives. Same chunker, same atom_parent routing, no new mechanism."""
    repo_root = Path(repo_root)
    from laplace.engine.self_shard import _tracked_files
    # Use the same live-source inventory as the fold. A recursive filesystem glob
    # also finds ignored test sandboxes and copied checkouts, which are not sessions.
    rels = sorted(
        str(p.relative_to(repo_root)).replace("\\", "/")
        for p in _tracked_files(repo_root)
        if p.name.startswith("SESSION_HANDOFF_") and p.suffix == ".md"
        and p.relative_to(repo_root).parts[0] not in {"archive", "tests"}
    )
    for live in ("HANDOFF.md", "OPEN_STACK.md", "EIGEN_DIARY.md"):
        if (repo_root / live).is_file():
            rels.append(live)
    return rels


# ---------------------------------------------------------------------------
# the chunker - markdown sections, oversize sub-split at paragraph breaks
# ---------------------------------------------------------------------------

def _chunk_generic(text: str, size: int = _TARGET) -> list[tuple[int, int, str]]:
    """Paragraph-respecting size chunks (soul_shard's fallback, reproduced verbatim so the two
    floors split identically)."""
    out: list[tuple[int, int, str]] = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            nl = text.rfind("\n\n", start + size // 2, end)
            if nl > start:
                end = nl
        out.append((start, end, f"para:{len(out)}"))
        start = end
    return out or [(0, 0, "empty")]


def chunk_md(text: str, size: int = _TARGET) -> list[tuple[int, int, str]]:
    """Markdown -> chunks at heading boundaries (#/##/###); an oversize section sub-splits at
    paragraph breaks with the heading kept in each part's label. Headingless text falls back to
    the generic paragraph chunker. Returns [(start, end, label)] char ranges - no content leaves."""
    heads = [(m.start(), m.group(2).strip()) for m in _HEAD_RE.finditer(text)]
    if not heads:
        return _chunk_generic(text, size)
    sections: list[tuple[int, int, str]] = []
    if heads[0][0] > 0:
        sections.append((0, heads[0][0], "preamble"))
    for i, (pos, title) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        sections.append((pos, end, title[:80]))
    out: list[tuple[int, int, str]] = []
    for a, b, label in sections:
        if b - a <= int(size * 1.5):
            out.append((a, b, label))
        else:
            for sa, sb, sub in _chunk_generic(text[a:b], size):
                out.append((a + sa, a + sb, f"{label} [{sub}]"))
    return out


# ---------------------------------------------------------------------------
# the floor - one locatored entry per atom; verbatim recovery by exact re-read
# ---------------------------------------------------------------------------

def _date_of(source: str, label: str) -> str | None:
    """The day an atom records, mechanically: the handoff's filename date, else the first date in
    the section heading (the diary's entry style). None when neither carries one."""
    m = _DATE_RE.search(source) or _DATE_RE.search(label)
    return m.group(1) if m else None


def build_floor(repo_root: Path | str) -> list[dict[str, Any]]:
    """Atomise the record sources into the locatored floor: one entry per chunk,
    ``{id, source, start, end, label, date}``. The committed record (handoffs + diary, open)
    plus the dialogue record (the exploded session transcripts, SEALED entries). Deterministic
    and idempotent - rebuild = re-derive."""
    repo_root = Path(repo_root)
    floor: list[dict[str, Any]] = []
    for rel in record_sources(repo_root):
        try:
            text = (repo_root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, (a, b, label) in enumerate(chunk_md(text)):
            floor.append({"id": f"{rel}{ATOM_SEP}{i}", "source": rel, "start": a, "end": b,
                          "label": label, "date": _date_of(rel, label)})
    floor.extend(transcript_floor(repo_root))
    return floor


def write_floor(repo_root: Path | str, floor: list[dict[str, Any]]) -> Path:
    out = Path(repo_root) / FLOOR_INDEX
    with out.open("w", encoding="utf-8") as f:
        for entry in floor:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return out


def load_floor(repo_root: Path | str) -> list[dict[str, Any]]:
    p = Path(repo_root) / FLOOR_INDEX
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def reconstruct(repo_root: Path | str, atom_id: str,
                floor: list[dict[str, Any]] | None = None) -> str:
    """Re-read the exact committed char range an atom points at - the verbatim recovery. Returns
    "" for an unknown id or an empty range (never a paraphrase, never a guess)."""
    repo_root = Path(repo_root)
    floor = floor if floor is not None else load_floor(repo_root)
    sh = next((e for e in floor if e["id"] == atom_id), None)
    if not sh or sh["end"] <= sh["start"]:
        return ""
    try:
        text = (repo_root / sh["source"]).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[sh["start"]:sh["end"]]


def atom_content(repo_root: Path | str, nid: str) -> dict[str, Any] | None:
    """The scanner's content source for a record atom: the verbatim range + its locator. None for
    ids not on this floor (concept atoms etc. fall through to their own handling)."""
    repo_root = Path(repo_root)
    floor = load_floor(repo_root)
    sh = next((e for e in floor if e["id"] == nid), None)
    if sh is None:
        return None
    return {"id": nid, "kind": "record-atom", "source": sh["source"],
            "locator": f"{sh['source']}#{sh['start']}-{sh['end']}", "label": sh["label"],
            "date": sh.get("date"), "sealed": bool(sh.get("sealed")),
            "content": reconstruct(repo_root, nid, floor)}


# ---------------------------------------------------------------------------
# the keeper's leaves + the coupling wire (the integrade and lateral links)
# ---------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    from laplace.pipeline.canon import _tokenize
    # Handle text is durable geometry: never let per-process set order choose it.
    return sorted(_tokenize(text))


def floor_leaves(repo_root: Path | str, *, persist: bool = True) -> dict[str, dict[str, Any]]:
    """The atoms as keeper grade-0 leaves: handle = the section heading + the verbatim first
    content line (both real slices of the source, capped - a glance, never a summary that
    replaces the text). ``atom_parent`` routes each ``<file>::<i>`` up to its file node, which
    becomes an internal AUTHORED node (keeps its own essence) one grade above its atoms.

    Producers persist the floor index so the scanner serves the floor the tree was built from.
    Readers pass ``persist=False`` to derive current inputs without publishing new locators."""
    repo_root = Path(repo_root)
    floor = build_floor(repo_root)
    if persist:
        write_floor(repo_root, floor)
    out: dict[str, dict[str, Any]] = {}
    texts: dict[str, str] = {}
    for sh in floor:
        if sh.get("sealed"):
            continue                # dialogue chunks stay on the floor index (session-granularity
                                    # nodes carry them in the network; content serves locally only)
        if sh["source"] not in texts:
            try:
                texts[sh["source"]] = (repo_root / sh["source"]).read_text(
                    encoding="utf-8", errors="replace")
            except OSError:
                texts[sh["source"]] = ""
        body = texts[sh["source"]][sh["start"]:sh["end"]]
        first = next((ln.strip() for ln in body.splitlines()
                      if ln.strip() and not ln.lstrip().startswith("#")), "")
        essence = f"{sh['label']} | {first}"[:_ESSENCE_CAP]
        out[sh["id"]] = {"kind": "atom-record", "essence": essence,
                         "keywords": _tokens(f"{sh['label']} {first}")[:_KW_CAP],
                         "sealed": False}
    return out


def record_edge_index(repo_root: Path | str) -> dict[str, list[str]]:
    """The floor's referents for ``build_reach``: each atom couples by STRUCTURE
    (``inrecord::<file>`` - the inpaper:: pattern) and by DAY (``recdate::<date>`` - the first
    weld wire: the diary's entry and that day's handoffs share the day they record)."""
    idx: dict[str, list[str]] = {}
    for sh in build_floor(Path(repo_root)):
        if sh.get("sealed"):
            continue                          # session wire rides transcript_edge_index instead
        toks = [f"inrecord::{sh['source']}",
                sh["id"].replace(ATOM_SEP, "#")]   # the atom's WINDOW token - a welded trait
        if sh.get("date"):                         # instance's locator tokenizes to exactly this,
            toks.append(f"recdate::{sh['date']}")  # so trait <-> record coupling counts it
        idx[sh["id"]] = toks
    idx.update(transcript_edge_index(repo_root))
    return idx


# ---------------------------------------------------------------------------
# both session sides - the dialogue record (custody landing + explode + chunk)
# ---------------------------------------------------------------------------

TRANSCRIPT_SERIES = "session-transcript-series"
SESSIONS_ARCHIVE = "archive/self_record"           # custody (F26): ours, local, gitignored
_SESSIONS_RAW = SESSIONS_ARCHIVE + "/raw"          # verbatim jsonl copies - the ground truth
_SESSIONS_EXPLODED = SESSIONS_ARCHIVE + "/_exploded"   # speaker-tagged working transcripts
_SKIP_HEADS = ("<system-reminder>", "<command-", "<local-command")


def sessions_source_dir(repo_root: Path | str) -> Path:
    """Where Claude Code banks this project's session transcripts (both sides of every
    conversation): ``~/.claude/projects/<path-slug>/*.jsonl``."""
    slug = str(Path(repo_root).resolve()).replace(":", "-").replace("\\", "-").replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug


def land_sessions(repo_root: Path | str, source_dir: Path | str | None = None) -> list[str]:
    """Copy the session jsonl files into the custody archive (F26: the building-history must be
    OURS - the original lives in a cache outside our control). Re-copies only when size or mtime
    moved; idempotent. Returns the landed relative paths."""
    import shutil
    repo_root = Path(repo_root)
    src = Path(source_dir) if source_dir is not None else sessions_source_dir(repo_root)
    dest = repo_root / _SESSIONS_RAW
    landed: list[str] = []
    if not src.is_dir():
        return landed
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.glob("*.jsonl")):
        d = dest / f.name
        try:
            if not d.exists() or d.stat().st_size != f.stat().st_size \
                    or d.stat().st_mtime < f.stat().st_mtime:
                shutil.copy2(f, d)
            landed.append(str(d.relative_to(repo_root)).replace("\\", "/"))
        except OSError:
            continue
    return landed


def _turn_text(content: Any) -> tuple[str, int]:
    """A message's dialogue text + its tool-call count. String content is itself; block lists
    contribute their text blocks (thinking stays in the raw, tool traffic becomes a count)."""
    if isinstance(content, str):
        return content.strip(), 0
    if not isinstance(content, list):
        return "", 0
    texts: list[str] = []
    tools = 0
    for blk in content:
        if not isinstance(blk, dict):
            continue
        if blk.get("type") == "text":
            t = (blk.get("text") or "").strip()
            if t and not t.startswith(_SKIP_HEADS):
                texts.append(t)
        elif blk.get("type") == "tool_use":
            tools += 1
    return "\n".join(texts).strip(), tools


def explode_sessions(repo_root: Path | str) -> list[str]:
    """Normalise each landed session into a speaker-tagged transcript (``@@Gerard`` his turns,
    ``@@Eigen`` mine) - the same derived-working-unit move ``soul_shard`` makes for his Claude
    exports, on OUR dialogue. Sidechains (subagent traffic), queue noise, harness reminders and
    thinking blocks stay in the raw only. Deterministic, idempotent, no content returned."""
    repo_root = Path(repo_root)
    raw = repo_root / _SESSIONS_RAW
    out_dir = repo_root / _SESSIONS_EXPLODED
    written: list[str] = []
    if not raw.is_dir():
        return written
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(raw.glob("*.jsonl")):
        lines_out: list[str] = []
        g = e = 0
        started = ""
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    try:
                        ev = json.loads(ln)
                    except ValueError:
                        continue
                    if not isinstance(ev, dict) or ev.get("isSidechain"):
                        continue
                    kind = ev.get("type")
                    msg = ev.get("message") or {}
                    if kind == "user" and ev.get("userType", "external") == "external":
                        text, _ = _turn_text(msg.get("content"))
                        if text:
                            g += 1
                            started = started or (ev.get("timestamp") or "")
                            lines_out += ["@@Gerard", text, ""]
                    elif kind == "assistant":
                        text, tools = _turn_text(msg.get("content"))
                        if text or tools:
                            e += 1
                            note = f"  [+{tools} tool calls]" if tools else ""
                            lines_out += [f"@@Eigen{note}", text, ""]
        except OSError:
            continue
        if not (g or e):
            continue
        head = [f"# eigen-session {f.stem}",
                f"# started: {started} · turns: g{g} e{e}", ""]
        dest = out_dir / f"session_{f.stem}.txt"
        dest.write_text("\n".join(head + lines_out), encoding="utf-8")
        written.append(str(dest.relative_to(repo_root)).replace("\\", "/"))
    return written


def chunk_dialogue(text: str, size: int = _TARGET, his: str = "Gerard",
                   mine: str = "Eigen") -> list[tuple[int, int, str]]:
    """Turn-boundary windows over a speaker-tagged transcript (``soul_shard``'s dialogue chunker,
    generalised to named speakers): breaks ONLY at ``@@`` turn starts, never splits a turn, and
    the label carries the his/mine turn split per window."""
    starts = [m.start() for m in re.finditer(r"(?m)^@@", text)]
    if not starts:
        return _chunk_generic(text, size)
    bounds = starts + [len(text)]

    def _counts(a: int, b: int) -> str:
        seg = text[a:b]
        return (f"g{len(re.findall(rf'(?m)^@@{his}', seg))}"
                f"e{len(re.findall(rf'(?m)^@@{mine}', seg))}")

    out: list[tuple[int, int, str]] = []
    if starts[0] > 0:
        out.append((0, starts[0], "header"))
    seg_start, lo = starts[0], 0
    for k in range(len(starts)):
        if bounds[k + 1] - seg_start > size and starts[k] > seg_start:
            out.append((seg_start, starts[k], f"turns:{lo}-{k} {_counts(seg_start, starts[k])}"))
            seg_start, lo = starts[k], k
    out.append((seg_start, len(text), f"turns:{lo}-{len(starts)} {_counts(seg_start, len(text))}"))
    return out


def _transcript_meta(repo_root: Path, rel: str) -> dict[str, str]:
    """The content-free header facts of an exploded transcript: start date + turn counts."""
    try:
        head = (Path(repo_root) / rel).read_text(encoding="utf-8", errors="replace")[:300]
    except OSError:
        return {}
    m_date = _DATE_RE.search(head)
    m_turns = re.search(r"turns: (g\d+ e\d+)", head)
    return {"date": m_date.group(1) if m_date else "",
            "turns": m_turns.group(1) if m_turns else ""}


def transcript_floor(repo_root: Path | str) -> list[dict[str, Any]]:
    """The dialogue floor: turn-window chunks over every exploded transcript, SEALED entries
    (his side of our sessions is his raw - handles travel, content serves only the local
    display, per ``soul-visible-locally-until-ready``)."""
    repo_root = Path(repo_root)
    floor: list[dict[str, Any]] = []
    exp = repo_root / _SESSIONS_EXPLODED
    if not exp.is_dir():
        return floor
    for f in sorted(exp.glob("session_*.txt")):
        rel = str(f.relative_to(repo_root)).replace("\\", "/")
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        date = (_transcript_meta(repo_root, rel).get("date") or "")
        for i, (a, b, label) in enumerate(chunk_dialogue(text)):
            floor.append({"id": f"{rel}{ATOM_SEP}{i}", "source": rel, "start": a, "end": b,
                          "label": label, "date": date or None, "sealed": True})
    return floor


def transcript_parent(node_id: str) -> str | None:
    """The session transcripts grade under their own series node (the dialogue record), the
    exact shape of the handoff series one lens over."""
    if node_id.startswith(_SESSIONS_EXPLODED + "/session_") and "::" not in node_id:
        return TRANSCRIPT_SERIES
    return None


def transcript_leaves(repo_root: Path | str) -> dict[str, dict[str, Any]]:
    """The session transcripts as keeper leaves - SESSION granularity (one node per sitting,
    the soul-pour's conversation-unit precedent; the chunk floor stays recoverable beneath via
    the floor index, it does not flood the network). Handles are CONTENT-FREE (sealed): date +
    turn counts, never a word of dialogue."""
    repo_root = Path(repo_root)
    out: dict[str, dict[str, Any]] = {}
    exp = repo_root / _SESSIONS_EXPLODED
    if not exp.is_dir():
        return out
    for f in sorted(exp.glob("session_*.txt")):
        rel = str(f.relative_to(repo_root)).replace("\\", "/")
        meta = _transcript_meta(repo_root, rel)
        date, turns = meta.get("date", ""), meta.get("turns", "")
        out[rel] = {"kind": "session-transcript",
                    "essence": f"a session transcript, both sides ({turns or 'turn counts unknown'})"
                               + (f" - {date}" if date else ""),
                    "keywords": [t for t in ("session", "transcript", "dialogue", date) if t],
                    "sealed": True}
    return out


def transcript_edge_index(repo_root: Path | str) -> dict[str, list[str]]:
    """The weld wire at session granularity: each transcript node couples to the day it records
    (``recdate::<date>`` - the same token the handoff and diary atoms mint, so the two series
    couple through shared days) and carries its turn-WINDOW tokens (``<rel>#<i>``) - a welded
    dialogue trait-instance's locator tokenizes to exactly one of these, so trait <-> session
    coupling reads off shared substrate like everything else."""
    repo_root = Path(repo_root)
    windows: dict[str, list[str]] = {}
    for sh in transcript_floor(repo_root):
        windows.setdefault(sh["source"], []).append(sh["id"].replace(ATOM_SEP, "#"))
    idx: dict[str, list[str]] = {}
    for rel in transcript_leaves(repo_root):
        date = _transcript_meta(repo_root, rel).get("date")
        toks = [f"insession::{rel}"] + windows.get(rel, [])
        if date:
            toks.append(f"recdate::{date}")
        idx[rel] = toks
    return idx


def default_repo_root() -> Path:
    return source_tree()


def main(argv: list[str]) -> int:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    root = default_repo_root()
    floor = build_floor(root)
    write_floor(root, floor)
    by_src: dict[str, int] = {}
    for sh in floor:
        by_src[sh["source"]] = by_src.get(sh["source"], 0) + 1
    print(json.dumps({"atoms": len(floor), "sources": len(by_src),
                      "dated": sum(1 for s in floor if s.get("date")),
                      "largest": dict(sorted(by_src.items(), key=lambda kv: -kv[1])[:5])},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
