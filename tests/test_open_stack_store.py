"""The one open-frontier read (2026-07-23, the F39 mismatch): a wordless fork-ruling
row retires NOTHING — the reader enforces the same substance rule the desk's write door
does (empty authoring 422s), so guard-bypassing probe residue can never make the desk
hide a decision the journey badge still counts.

Fail-closed contract:
  * a worded bank-ruling/contest-ruling retires its fork from ``open_forks``.
  * a wordless ruling row (the 07-23 probe-residue shape) is inert — the fork stays open.
  * ``ruling`` and legacy ``reason`` both carry the words (the writer mirrors them).
  * badge-vs-listing agreement: ``open_forks`` is live_forks minus worded rulings, exactly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine import open_stack_store as oss  # noqa: E402

_LIVE = oss.LIVE_MARKER


def _seed(repo: Path, rows: list[dict]) -> None:
    p = repo / oss.STORE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _fork(fid: str) -> dict:
    return {"id": fid, "kind": "open-stack-fork", "corpus": "paper_x",
            "title": f"fork {fid}", "status": f"{_LIVE} live"}


def test_worded_ruling_retires_fork(tmp_path: Path) -> None:
    _seed(tmp_path, [
        _fork("F1"), _fork("F2"),
        {"id": "FR-1-F1", "kind": "fork-ruling", "rules": "F1", "verb": "bank-ruling",
         "disposition": "banked", "ruling": "the register lands; plain wins", "reason": ""},
    ])
    assert oss.ruled_fork_ids(tmp_path) == {"F1"}
    assert [f["id"] for f in oss.open_forks(tmp_path)] == ["F2"]


def test_wordless_ruling_is_inert(tmp_path: Path) -> None:
    # the exact 07-23 probe-residue shape: reason "", no ruling field, by "author"
    _seed(tmp_path, [
        _fork("F39"),
        {"id": "FR-x-F39", "kind": "fork-ruling", "rules": "F39", "verb": "bank-ruling",
         "disposition": "banked", "reason": "", "by": "author"},
        {"id": "FR-y-F39", "kind": "fork-ruling", "rules": "F39", "verb": "contest-ruling",
         "disposition": "contested", "reason": "", "by": "author"},
    ])
    assert oss.ruled_fork_ids(tmp_path) == set()
    assert [f["id"] for f in oss.open_forks(tmp_path)] == ["F39"]


def test_legacy_reason_field_carries_the_words(tmp_path: Path) -> None:
    _seed(tmp_path, [
        _fork("F7"),
        {"id": "FR-z-F7", "kind": "fork-ruling", "rules": "F7", "verb": "contest-ruling",
         "disposition": "contested", "reason": "objection: the premise is wrong"},
    ])
    assert oss.ruled_fork_ids(tmp_path) == {"F7"}
    assert oss.open_forks(tmp_path) == []


def test_badge_and_listing_read_the_same_frontier(tmp_path: Path) -> None:
    _seed(tmp_path, [
        _fork("F1"), _fork("F2"), _fork("F3"),
        {"id": "FR-1-F2", "kind": "fork-ruling", "rules": "F2", "verb": "bank-ruling",
         "disposition": "banked", "ruling": "settled with words"},
        {"id": "FR-2-F3", "kind": "fork-ruling", "rules": "F3", "verb": "bank-ruling",
         "disposition": "banked", "reason": ""},   # wordless — F3 stays owed
    ])
    open_ids = {f["id"] for f in oss.open_forks(tmp_path)}
    live_ids = {f["id"] for f in oss.live_forks(tmp_path)}
    assert open_ids == {"F1", "F3"}
    assert open_ids == live_ids - oss.ruled_fork_ids(tmp_path)
