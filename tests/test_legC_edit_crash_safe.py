"""Leg C bite C1 — the edit-in-place splice is CRASH-SAFE (bank-before-apply).

The banked fear: the old order wrote the spliced fragment to disk BEFORE the
ledger bank, so a hard kill between the two left a spliced-but-unbanked hand edit
— the author's edit applied but UNPROTECTED, which the route could then
regenerate over (silent loss of the author's hand). The fix stages the write to a
temp sibling, banks the protection record, then atomically swaps the fragment in.
Apply now happens strictly AFTER the bank, so a failure at the bank step can only
ever leave the fragment at its PRE-EDIT bytes (benign over-protection), never a
spliced-but-unbanked state.

Both directions are proved: the happy path applies AND banks; a planted failure
at the bank step leaves the fragment byte-identical to before.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.manuscript import review_surface as RS
from laplace.pipeline.ledger import read_jsonl

pytestmark = pytest.mark.unit

_FRAG = "Intro prose.\nSome prose with a unique TARGET phrase here.\nOutro prose.\n"


def _md(tmp_path: Path) -> tuple[Path, Path]:
    md = tmp_path / "m"
    (md / "feedback").mkdir(parents=True)
    frag = md / "N1.tex"
    frag.write_text(_FRAG, encoding="utf-8")
    return md, frag


def _payload() -> dict:
    return {"verb": "edit-in-place", "section": "N1", "file": "N1.tex",
            "before": "TARGET", "after": "REPLACED", "by": "author"}


def test_happy_path_applies_and_banks(tmp_path):
    md, frag = _md(tmp_path)
    res = RS.adjudicate(md, "proj", _payload())
    assert res.get("ok") is True
    assert "REPLACED" in frag.read_text(encoding="utf-8")
    assert "TARGET" not in frag.read_text(encoding="utf-8")
    # the protection record is banked on the one door
    recs = read_jsonl(md / "feedback" / "feedback.jsonl")
    assert [r for r in recs if r.get("record") == "author-edit"]
    # no temp staging file survives a clean apply
    assert not (md / "N1.tex.editswap").exists()


def test_bank_crash_leaves_fragment_unedited(tmp_path, monkeypatch):
    """Planted failure BETWEEN the steps: the bank raises. The invariant is that
    the fragment is NOT spliced (no applied-but-unbanked state) — the exact
    data-loss window the old write-then-bank order left open."""
    md, frag = _md(tmp_path)
    before_bytes = frag.read_bytes()

    def _boom(path, rec):
        raise RuntimeError("planted bank failure between splice-stage and swap")

    monkeypatch.setattr(RS, "append_jsonl", _boom)

    with pytest.raises(RuntimeError):
        RS.adjudicate(md, "proj", _payload())

    # the fragment is byte-identical to before: the splice never became visible,
    # because the atomic swap only runs AFTER a successful bank.
    assert frag.read_bytes() == before_bytes
    assert "REPLACED" not in frag.read_text(encoding="utf-8")
