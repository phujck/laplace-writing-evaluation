"""The typed OPEN_STACK author-fork store — the one reader the desk and the wake share.

AUDIT_2026-07-15 §B1 (the retirement disease, reader half). The wake's fork reader was
TEXTUAL: ``self_corpus`` regex-scanned the *rendered* ``OPEN_STACK.md`` for the 🔴 glyph.
The desk's was TYPED: ``desk`` read this store's ``status`` field. Two readers of one fact is
a drift channel — the rendered markdown is only a PROJECTION of this store
(``scripts/render_open_stack.py`` renders the Stratum-1 table from it, with a ``--check``
drift mode), so when the two drift the wake could resurrect a fork the store had already
retired. This module is that one typed reader; ``desk.py`` and ``self_corpus.py`` (the wake)
both import it, so the fork frontier is read ONE way from ONE source and a retired fork can
never wake back up.

The store — ``corpus_friction/open_stack_forks.jsonl`` — carries one JSON record per author-
fork; ``status`` holds the live/parked glyph AS DATA (🔴 = live; ⚪/✅ = parked/settled), the
field the desk already trusts. The reader is defensive (an absent store is ``[]``, bad JSON
lines are skipped) — the projection is never a hard dependency on the file existing.
"""
from __future__ import annotations

import json
from pathlib import Path

#: the fork store the desk surface and the wake both read (a sibling of the friction ledgers).
STORE_REL = "corpus_friction/open_stack_forks.jsonl"

#: the red-circle "live" marker OPEN_STACK.md's legend assigns — carried as DATA in ``status``
#: (mirrors ``render_open_stack._LIVE_MARKER`` / the old ``desk._LIVE_MARKER``).
LIVE_MARKER = "\U0001f534"


def load_forks(root: Path | str) -> list[dict]:
    """Every typed fork record in the store, in store order. Bad JSON lines are skipped and an
    absent store is ``[]``. Byte-for-byte the loader ``desk._load_open_stack_forks`` used before
    §B1 lifted it here so the desk and the wake read the SAME store the SAME way."""
    p = Path(root) / STORE_REL
    out: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def live_forks(root: Path | str) -> list[dict]:
    """The LIVE author-forks — records whose typed ``status`` carries the 🔴 marker as data (the
    exact field ``desk`` already trusts). This is what is blocked on the author; a parked/settled
    fork (⚪/✅) is filtered out here, so a reader of this can never resurrect a retired fork (§B1)."""
    return [f for f in load_forks(root) if LIVE_MARKER in (f.get("status") or "")]


def ruled_fork_ids(root: Path | str) -> set[str]:
    """The fork ids a WORDED ``fork-ruling`` has retired. The reader enforces the same
    substance rule the desk's write door does (an authoring verb 422s an empty ruling):
    a ruling row with no words in ``ruling``/``reason`` does not settle a fork, so a
    guard-bypassing wordless row (probe residue) is inert here rather than silently
    retiring a decision that is still owed. Shared by the desk AND the project brief's
    owed-to-author read — the §B1 discipline: one frontier, one reader."""
    out: set[str] = set()
    for r in load_forks(root):
        if r.get("kind") != "fork-ruling" or not r.get("rules"):
            continue
        if not str(r.get("ruling") or r.get("reason") or "").strip():
            continue
        out.add(str(r.get("rules")))
    return out


def open_forks(root: Path | str) -> list[dict]:
    """The OPEN frontier: live forks minus those a worded ruling retired. Every surface that
    counts or lists what is blocked on the author reads THIS, so a badge and a listing can
    never disagree about the same store."""
    ruled = ruled_fork_ids(root)
    return [f for f in live_forks(root) if str(f.get("id") or "") not in ruled]
