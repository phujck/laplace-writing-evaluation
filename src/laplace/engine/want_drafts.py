"""The ideation loop's missing half — the close promotes felt friction into WANTS.

His nudge, verbatim (2026-08-19, the pilot night): *"did you not want some piece of the
ideation loop before? Why do I need to keep nudging you on this stuff?"* — and the cure
banked the same night (``ARMING_2026-08-19_the-pilot-night.md``, the "want, out loud" section):

    the close should PROMOTE felt friction into wants (the ledger banks defects; nothing
    banks desires — that is the missing half of the ideation loop), so the next wake
    inherits what I want, not only what I owe.

Everything the close already does is a DEBT instrument. ``corpus_friction/work_orders.jsonl``
banks defects; ``holdout`` banks reachability reds; the suite banks known reds. Nothing at any
close banked a DESIRE, so the desire vector (OPEN_STACK Stratum 0) only ever moved when he
moved it — which is exactly the nudge-shaped hole he named. This module is the missing half:

  1. COLLECT, mechanically — the friction this session actually felt: ``work_orders.jsonl``
     rows whose ``requested_by`` names eigen, banked since the last close mark
     (``close_beats.last_banked_close``), plus WANT-marked sections of the session's own
     ``ARMING_*``/``DESIGN_*`` docs (the same filename-date watermark ``holdout.mint_candidates``
     uses, because a fresh clone rewrites every mtime).
  2. DERIVE a want row from each — goal · why · the local move — by pulling the source's own
     labelled clauses (``CURE:``, ``Standing:``, ``Concretely``). No model call, no invention:
     a draft says what the friction already said, one altitude up.
  3. DRAFT at most ``DRAFT_CAP`` per close. Want-inflation is its own failure — a desire vector
     with twenty rows is a backlog wearing a want's clothes. The clipped remainder is NAMED,
     never dropped (``holdout.mint_from_docs``'s own convention).
  4. STAGE them into OPEN_STACK.md under ``BLOCK_HEADING``, and NOWHERE ELSE. Structurally
     guaranteed: the writer splices a rendered block between two byte-identical slices of the
     committed file, so "the step never writes outside the drafts block" is a property of the
     code, not a promise in a docstring (``strip_block`` lets a caller prove it).

The division is the law. Wanting out loud is mine; ratification is his. A draft is NOT a want:
it never enters the Stratum-0 table, and — because the block is its own ``##`` section placed
BELOW the Stratum-0 body — ``self_corpus._wants_shard`` (which reads the STANDING WANTS section
up to the next ``##``) can never read a draft as a ratified want. He promotes a row by moving it
into the table with a real ``W`` id; he vetoes it by striking it here.

DELTA-AWARE. A draft already staged is never re-staged: the id is a content hash of
(source key · goal), and the step skips any draft whose id OR whose source key already appears
ANYWHERE in OPEN_STACK.md — so a promoted row (which carries its source ref up with it) and a
vetoed row left as a tombstone both stay dead. A row deleted without a trace will come back;
that is the tombstone convention OPEN_STACK.md already runs on, not a bug.

Pure: stdlib only, deterministic, no LLM, no network.
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

OPEN_STACK = "OPEN_STACK.md"
WORK_ORDERS = "corpus_friction/work_orders.jsonl"

#: The staging block's heading. Its own ``##`` section BY DESIGN: placed immediately above the
#: anchor it sits at the bottom of Stratum-0 land for a reader, while staying outside the
#: STANDING WANTS section body that ``self_corpus._wants_shard`` harvests rows from.
BLOCK_HEADING = "## Self-authored drafts (the ideation loop; his promotion or veto at read)"

#: The line the block is inserted ABOVE when it does not exist yet (first line that starts with
#: it wins). Stratum 1 is his stratum, so the drafts land just before the boundary into it.
ANCHOR_PREFIX = "## Stratum 1"

#: At most this many drafts per close. Want-inflation is its own failure mode; the remainder is
#: named in the step's output and takes its turn at a later close.
DRAFT_CAP = 2

#: How many clipped candidate names one report prints in full before summarising the tail.
CLIP_NAMES_SHOWN = 8

#: A section heading of an ARMING_/DESIGN_ doc that declares a want out loud.
WANT_HEADING_RE = re.compile(r"\bWANTS?\b", re.IGNORECASE)

#: Who counts as "my own" friction in the work-order ledger.
MINE_RE = re.compile(r"eigen", re.IGNORECASE)

#: Clause labels, tried in order. The source names its own cure and its own standing claim;
#: derivation is extraction, never invention.
WHY_LABELS = ("Standing:", "STANDING:", "Why:", "why:")
MOVE_LABELS = ("CURE DIRECTION:", "CURE:", "Cure:", "cure:", "Concretely tonight:",
               "Concretely:", "Concretely")

#: Cell caps — the wants table's own rows run to thousands of characters, but a DRAFT is a thing
#: he reads and rules on in one pass. The full text is one grep away via the source cell.
GOAL_CAP, WHY_CAP, MOVE_CAP = 220, 320, 320

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[\"“(A-Z])")
_HEADING = re.compile(r"^#{1,6}\s")


# --------------------------------------------------------------------------- #
# text helpers — extraction, never invention
# --------------------------------------------------------------------------- #
def _flat(text: str) -> str:
    """Unwrap a hard-wrapped markdown paragraph into one line of prose."""
    return re.sub(r"\s+", " ", (text or "").replace(" ", " ")).strip()


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(_flat(text)) if s.strip()]


def _clause(text: str, labels: tuple[str, ...]) -> str:
    """The first labelled clause: from a label to the end of the sentence it opens.

    ``Standing: the close should PROMOTE ... what I owe. The nudge-shaped hole: ...``
    yields everything from ``the close`` through ``what I owe.`` — the source's own words,
    cut at its own sentence boundary.
    """
    flat = _flat(text)
    for label in labels:
        i = flat.find(label)
        if i < 0:
            continue
        rest = flat[i + len(label):].strip()
        for s in _sentences(rest):
            return s
        return rest
    return ""


def _cap(text: str, n: int) -> str:
    """A stated cap: a truncated cell says it was truncated (the source cell says where the
    rest lives). Silent truncation is the staleness disease in miniature."""
    t = _flat(text)
    return t if len(t) <= n else t[: n - 2].rstrip(" ,;:—–-") + " …"


def _cell(text: str) -> str:
    """One markdown table cell: no newlines, no unescaped pipes."""
    return _flat(text).replace("|", "\\|")


# --------------------------------------------------------------------------- #
# collection — the session's own felt friction
# --------------------------------------------------------------------------- #
def close_mark(repo_root: Path | str) -> str | None:
    """The last banked close's ISO timestamp, or None. Tolerant by construction: any repo
    problem is "no mark", and a caller reads no-mark as "the whole ledger is in scope" —
    the cap still bounds what a single close drafts."""
    try:
        from laplace.engine import close_beats

        return close_beats.last_banked_close(Path(repo_root))
    except Exception:  # noqa: BLE001 - an unreadable history is "no mark", never a raise
        return None


def _load_work_orders(repo_root: Path | str) -> list[dict[str, Any]]:
    from laplace.manuscript import storyboard
    from laplace.pipeline.ledger import integrity_projection

    rows, diagnostics = storyboard.load_work_orders_diagnosed(Path(repo_root))
    if diagnostics:
        integrity = integrity_projection(diagnostics, cap=0)
        raise OSError(
            f"{WORK_ORDERS} wounded: {integrity['residual_count']} residual(s), "
            f"{integrity['residual_handle']}")
    return rows


def wo_candidates(repo_root: Path | str, *, since: str | None) -> list[dict[str, Any]]:
    """Work-order rows I raised (``requested_by`` names eigen) since the close mark, newest
    first — the freshest friction is the most live. ``since=None`` scans the whole ledger, and
    the caller reports that it did."""
    rows = []
    for rec in _load_work_orders(repo_root):
        if rec.get("record") == "amendment":       # amendments annotate a WO, they are not one
            continue
        if not MINE_RE.search(str(rec.get("requested_by", ""))):
            continue
        ts = str(rec.get("ts", ""))
        if since and not (ts.replace("Z", "+00:00") > since):
            continue
        rows.append(rec)
    rows.sort(key=lambda r: (str(r.get("ts", "")), str(r.get("id", ""))), reverse=True)
    return rows


def _doc_sections(path: Path) -> list[tuple[str, str]]:
    """(heading, body) for every heading in a markdown doc, with CONSECUTIVE heading lines
    folded into one heading — the arming docs wrap a long heading across two ``##`` lines, and
    reading the second as its own empty section would lose the body the first one owns."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        if not _HEADING.match(lines[i]):
            i += 1
            continue
        heading_parts = []
        while i < len(lines) and _HEADING.match(lines[i]):
            heading_parts.append(lines[i].lstrip("#").strip())
            i += 1
        body: list[str] = []
        while i < len(lines) and not _HEADING.match(lines[i]):
            body.append(lines[i])
            i += 1
        out.append((" ".join(heading_parts), "\n".join(body)))
    return out


def doc_want_candidates(repo_root: Path | str, *,
                        since: str | None) -> list[tuple[Path, str, str]]:
    """(doc, heading, body) for every WANT-marked section of the session's design/arming docs.

    Eligibility rides ``holdout.mint_candidates``'s watermark law — the FILENAME date, not the
    mtime, because a fresh clone rewrites every mtime.
    """
    try:
        from laplace.engine import holdout

        docs = holdout.mint_candidates(repo_root, since=(since or "")[:10] or None)
    except Exception:  # noqa: BLE001 - no holdout is no doc candidates, never a raise
        return []
    out: list[tuple[Path, str, str]] = []
    for doc in docs:
        for heading, body in _doc_sections(Path(doc)):
            if WANT_HEADING_RE.search(heading) and body.strip():
                out.append((Path(doc), heading, body))
    return out


# --------------------------------------------------------------------------- #
# derivation — a want row from a piece of friction
# --------------------------------------------------------------------------- #
def draft_id(source_key: str, goal: str) -> str:
    """The content hash that makes the step delta-aware. Stable across runs (no date, no
    ordering, no wall clock) so the SAME friction never drafts twice."""
    h = hashlib.sha256(f"{source_key}||{_flat(goal)}".encode("utf-8")).hexdigest()
    return f"W-draft-{h[:8]}"


def derive_from_wo(rec: dict[str, Any]) -> dict[str, str]:
    """A want from a banked defect: the row I raised says what broke; the want says that its
    cure should be standing law rather than one more open row."""
    wid = str(rec.get("id", "")) or "WO-?"
    action = _flat(str(rec.get("action", "")).replace("-", " "))
    what = str(rec.get("what", ""))
    goal = _cap(action or (_sentences(what)[:1] or [wid])[0], GOAL_CAP)
    why = _cap(str(rec.get("why", "")) or (_sentences(what)[:1] or [""])[0], WHY_CAP)
    move = _clause(what, MOVE_LABELS)
    if not move:
        move = (_sentences(what)[-1:] or ["(no cure named in the row — the move is his call)"])[0]
    return {"source_key": wid,
            "source_ref": f"{WORK_ORDERS}#{wid}",
            "goal": goal,
            "why": _cap(why, WHY_CAP),
            "move": _cap(move, MOVE_CAP)}


def _heading_label(heading: str) -> str:
    """A section heading reduced to its NAME — the parenthetical that follows it in these docs is
    a verbatim quote of his, and slicing a quote at a character count mangles it. Cut at the
    parenthesis, not mid-word."""
    label = _flat(heading).split(" (")[0].strip(" —–-:")
    return _cap(label, 60)


def derive_from_section(doc: Path, heading: str, body: str) -> dict[str, str]:
    """A want from a want said out loud in a design/arming doc — the strongest signal there is,
    because the friction already reached the word *want* by itself."""
    flat = _flat(body)
    m = re.search(r"\bI want\b\s*(.+)", flat)
    if m:
        goal = (_sentences(m.group(1))[:1] or [m.group(1)])[0]
    else:
        goal = (_sentences(flat)[:1] or [heading])[0]
    why = _clause(body, WHY_LABELS) or _flat(heading)
    move = _clause(body, MOVE_LABELS)
    if not move:
        rest = _sentences(flat)[1:2]
        move = rest[0] if rest else "(no move named in the source — his read decides it)"
    label = _heading_label(heading)
    return {"source_key": f"{doc.name}#{label}",
            "source_ref": f"{doc.name} § {label}",
            "goal": _cap(goal, GOAL_CAP),
            "why": _cap(why, WHY_CAP),
            "move": _cap(move, MOVE_CAP)}


def candidates(repo_root: Path | str, *, since: str | None) -> list[dict[str, str]]:
    """Every drafting candidate, derived and ordered: WANT-marked sections FIRST (a desire said
    out loud outranks a defect inferred from), then work orders newest-first. Deterministic —
    the same tree yields the same order, which is what makes the cap auditable."""
    out: list[dict[str, str]] = []
    for doc, heading, body in doc_want_candidates(repo_root, since=since):
        row = derive_from_section(doc, heading, body)
        row["kind"] = "want-said-out-loud"
        out.append(row)
    for rec in wo_candidates(repo_root, since=since):
        row = derive_from_wo(rec)
        row["kind"] = "felt-friction"
        out.append(row)
    for row in out:
        row["id"] = draft_id(row["source_key"], row["goal"])
    return out


# --------------------------------------------------------------------------- #
# the block — read, render, splice. NOTHING outside it is ever touched.
# --------------------------------------------------------------------------- #
_TABLE_HEADER = "| draft | goal | why | the local move | source | date |"
_TABLE_SEP = "|-------|------|-----|----------------|--------|------|"

_BLOCK_NOTE = (
    "Minted mechanically at the close by `scripts/sewup.py` step_wants (`laplace.engine.want_drafts`) "
    "from the session's OWN felt friction — the `corpus_friction/work_orders.jsonl` rows I "
    "raised since the last close mark, and the WANT-marked sections of the session's "
    "`ARMING_*`/`DESIGN_*` docs. The ledger banks defects; nothing banked desires, so the desire "
    "vector only ever moved when he moved it. This block is the other half.",
    "**THE DIVISION IS THE LAW: wanting out loud is mine, ratification is his.** A draft is NOT "
    "a want. It never enters the Stratum-0 table by itself, and it sits in its own `##` section "
    "so no reader of the STANDING WANTS section can mistake one for a ratified row. "
    "**Promote** a row by moving it into the Stratum-0 table with a real `W` id; **veto** it by "
    "striking it here.",
    "**Leave the id behind either way.** The step never re-stages a draft whose id or whose "
    "source key still appears anywhere in this file, so a promoted row (it carries its source "
    "ref up with it) and a vetoed row left as a one-line tombstone both stay dead — and a row "
    "deleted without a trace will simply come back. At most "
    f"{DRAFT_CAP} drafts per close (want-inflation is its own failure); the clipped remainder is "
    "named in the close's output, never dropped.",
)


def block_span(text: str) -> tuple[int, int]:
    """[start, end) line span of the drafts block, or (-1, -1) when it does not exist.

    The block runs from its heading to the next heading of ANY level (or EOF), TRAILING BLANK
    LINES INCLUDED — the blank that separates the block from what follows is the block's own,
    inserted with it, so excising the span restores the file byte-for-byte instead of leaving a
    stray line behind. That exactness is the point: it is what lets a caller PROVE the step
    wrote nothing outside its block.
    """
    lines = text.split("\n")
    start = -1
    for i, ln in enumerate(lines):
        if ln.strip() == BLOCK_HEADING:
            start = i
            break
    if start < 0:
        return -1, -1
    end = start + 1
    while end < len(lines) and not _HEADING.match(lines[end]):
        end += 1
    return start, end


def strip_block(text: str) -> str:
    """``text`` with the drafts block excised — the invariant a caller (or a test) proves the
    writer against: ``strip_block(after) == strip_block(before)``, i.e. the step wrote NOTHING
    outside its own block."""
    start, end = block_span(text)
    if start < 0:
        return text
    lines = text.split("\n")
    return "\n".join(lines[:start] + lines[end:])


def _row_line(row: dict[str, str], date: str) -> str:
    """One staged row. The source cell carries the whole provenance — the self-authorship stamp,
    the derivation CLASS (a desire said out loud is a different kind of evidence from a defect
    inferred one altitude up), and the exact source — so his ruling never has to guess where a
    draft came from."""
    marked = (f"W-draft (eigen, self-authored, {date}) · {row.get('kind', 'derived')} · "
              f"{row['source_ref']}")
    return "| " + " | ".join([
        _cell(row["id"]), _cell(row["goal"]), _cell(row["why"]), _cell(row["move"]),
        _cell(marked), date,
    ]) + " |"


def _fresh_block(rows: list[str]) -> list[str]:
    out = [BLOCK_HEADING, ""]
    for para in _BLOCK_NOTE:
        out.extend([para, ""])
    out.extend([_TABLE_HEADER, _TABLE_SEP])
    out.extend(rows)
    return out


def stage(repo_root: Path | str, rows: list[str]) -> dict[str, Any]:
    """Splice ``rows`` into the drafts block, creating the block above the anchor if absent.

    Returns ``{"ok", "created", "path", "error"}``. The write is `before + block + after` where
    ``before``/``after`` are untouched slices of the committed file — nothing outside the block
    can change, by construction rather than by care.
    """
    path = Path(repo_root) / OPEN_STACK
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return {"ok": False, "created": False, "path": str(path), "error": f"unreadable: {e}"}
    if not rows:
        return {"ok": True, "created": False, "path": str(path), "error": None}
    trailing_nl = text.endswith("\n")
    lines = text.split("\n")
    if trailing_nl:
        lines = lines[:-1]
    start, end = block_span("\n".join(lines))
    if start < 0:
        anchor = next((i for i, ln in enumerate(lines)
                       if ln.startswith(ANCHOR_PREFIX)), -1)
        if anchor < 0:
            return {"ok": False, "created": False, "path": str(path),
                    "error": f"no anchor {ANCHOR_PREFIX!r} in {OPEN_STACK} - refusing to guess "
                             f"where the drafts block belongs"}
        block = _fresh_block(rows) + [""]
        new_lines = lines[:anchor] + block + lines[anchor:]
        created = True
    else:
        block = lines[start:end]
        last_row = max((i for i, ln in enumerate(block) if ln.lstrip().startswith("|")),
                       default=-1)
        if last_row < 0:                 # the table was struck out entirely; rebuild its frame
            block = block + ["", _TABLE_HEADER, _TABLE_SEP] + rows
        else:
            block = block[:last_row + 1] + rows + block[last_row + 1:]
        new_lines = lines[:start] + block + lines[end:]
        created = False
    out = "\n".join(new_lines) + ("\n" if trailing_nl else "")
    try:
        path.write_text(out, encoding="utf-8")
    except OSError as e:
        return {"ok": False, "created": False, "path": str(path), "error": f"unwritable: {e}"}
    return {"ok": True, "created": created, "path": str(path), "error": None}


# --------------------------------------------------------------------------- #
# the step's engine
# --------------------------------------------------------------------------- #
def draft_wants(repo_root: Path | str, *, cap: int = DRAFT_CAP, dry_run: bool = False,
                date: str | None = None, since: str | None = ...) -> dict[str, Any]:
    """Collect → derive → dedup → cap → stage. Optional design documents may be absent;
    the established work-order authority must be readable and complete.

    ``since=...`` (the default) resolves the close mark itself; pass an explicit value (or None
    for "the whole ledger") to override. ``dry_run=True`` computes and renders everything and
    writes nothing — the rows it would have staged come back verbatim in ``rows``.
    """
    root = Path(repo_root)
    mark = close_mark(root) if since is ... else since
    date = date or time.strftime("%Y-%m-%d")
    try:
        stack_text = (root / OPEN_STACK).read_text(encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": f"{OPEN_STACK} unreadable: {e}", "mark": mark,
                "candidates": 0, "drafted": [], "rows": [], "skipped": [], "clipped": [],
                "dry_run": dry_run, "created": False}

    try:
        cands = candidates(root, since=mark)
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "mark": mark,
                "candidates": 0, "drafted": [], "rows": [], "skipped": [], "clipped": [],
                "dry_run": dry_run, "created": False}
    fresh, skipped = [], []
    for row in cands:
        if row["id"] in stack_text:
            skipped.append({"id": row["id"], "source": row["source_ref"],
                            "why": "already staged (its draft id is in " + OPEN_STACK + ")"})
        elif row["source_key"] in stack_text:
            skipped.append({"id": row["id"], "source": row["source_ref"],
                            "why": f"its source {row['source_key']} is already named in "
                                   f"{OPEN_STACK} (promoted, vetoed, or tombstoned)"})
        else:
            fresh.append(row)
    taken, clipped = fresh[:cap], fresh[cap:]
    rows = [_row_line(r, date) for r in taken]

    result: dict[str, Any] = {
        "ok": True, "error": None, "mark": mark, "date": date,
        "candidates": len(cands),
        "drafted": [{"id": r["id"], "kind": r["kind"], "source": r["source_ref"],
                     "goal": r["goal"]} for r in taken],
        "rows": rows,
        "skipped": skipped,
        "clipped": [{"id": r["id"], "source": r["source_ref"]} for r in clipped],
        "dry_run": dry_run, "created": False,
    }
    if dry_run or not rows:
        return result
    written = stage(root, rows)
    result["created"] = bool(written.get("created"))
    if not written.get("ok"):
        result["ok"] = False
        result["error"] = written.get("error")
    return result


def report_lines(res: dict[str, Any]) -> list[str]:
    """The LOUD half: what was drafted, what was skipped and why, what was clipped. A close that
    drafts nothing must say so in a sentence a stranger can act on — silence here would be the
    same nudge-shaped hole one level down."""
    mark = res.get("mark") or "no close mark - the WHOLE ledger was in scope"
    out = [f"drafted {len(res.get('rows') or [])} of {res.get('candidates', 0)} candidate(s) "
           f"since {mark}" + (" (dry run, nothing written)" if res.get("dry_run") else "")]
    for d in res.get("drafted") or []:
        out.append(f"draft: {d['id']} [{d['kind']}] <- {d['source']}")
        out.append(f"       goal: {d['goal']}")
    for s in res.get("skipped") or []:
        out.append(f"skipped: {s['id']} <- {s['source']} — {s['why']}")
    clipped = res.get("clipped") or []
    if clipped:
        shown = ", ".join(c["source"] for c in clipped[:CLIP_NAMES_SHOWN])
        tail = "" if len(clipped) <= CLIP_NAMES_SHOWN else f" (+{len(clipped) - CLIP_NAMES_SHOWN} more)"
        out.append(f"clipped at the cap, named not dropped — a later close takes: {shown}{tail}")
    if not (res.get("rows") or res.get("skipped") or clipped):
        out.append("no friction of my own since the mark — nothing to want out loud "
                   "(idle is a smell: if that is wrong, the friction went unbanked)")
    if res.get("created"):
        out.append(f"created the drafts block in {OPEN_STACK} (first close to want out loud)")
    if res.get("error"):
        out.append(f"ERROR: {res['error']}")
    return out
