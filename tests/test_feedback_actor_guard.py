"""THE ACTOR GUARD, extended to the remote genre (website milestone one, bite B4
engine-side): a public demo visitor can submit feedback that lands in the inbox and
gets drained into the ledger, but the remote channel must never be able to mint an
actorless or author-attributed record (manuscript_bridge.feedback_ingest's local
default of ``by -> "gerard"`` would otherwise let a stranger's silence, or a forged
``by: "gerard"``, become the author's own word). Mirrors the local precedent —
review_surface.adjudicate's actor guard (an explicit ``by``, defaults nowhere).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from laplace.manuscript import manuscript_bridge as mb

ROOT = Path(__file__).resolve().parents[1]


def _load_drain():
    spec = importlib.util.spec_from_file_location(
        "drain_feedback", ROOT / "scripts" / "drain_feedback.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("drain_feedback", mod)
    spec.loader.exec_module(mod)
    return mod


def _rec(fb_id="FB-2026-r0", by=None, **extra):
    rec = {"id": fb_id, "ts": "2026-07-11T10:00:00", "node_id": "res:window-verdict",
           "comment": "a visitor's comment", "kind": "note"}
    if by is not None:
        rec["by"] = by
    rec.update(extra)
    return rec


def test_remote_empty_by_is_refused(tmp_path):
    ledger = tmp_path / "feedback.jsonl"
    out = mb.feedback_ingest(ROOT, "demo", _rec(by=""), ledger=ledger, channel="remote")
    assert "error" in out
    assert not ledger.exists() or ledger.read_text().strip() == ""


def test_remote_missing_by_is_refused(tmp_path):
    ledger = tmp_path / "feedback.jsonl"
    out = mb.feedback_ingest(ROOT, "demo", _rec(), ledger=ledger, channel="remote")
    assert "error" in out
    assert not ledger.exists() or ledger.read_text().strip() == ""


def test_remote_gerard_is_refused(tmp_path):
    ledger = tmp_path / "feedback.jsonl"
    out = mb.feedback_ingest(ROOT, "demo", _rec(by="gerard"), ledger=ledger, channel="remote")
    assert "error" in out
    assert not ledger.exists() or ledger.read_text().strip() == ""


def test_remote_gerard_case_and_space_is_refused(tmp_path):
    ledger = tmp_path / "feedback.jsonl"
    out = mb.feedback_ingest(ROOT, "demo", _rec(by="GERARD "), ledger=ledger, channel="remote")
    assert "error" in out
    assert not ledger.exists() or ledger.read_text().strip() == ""


def test_remote_visitor_with_empty_name_is_refused(tmp_path):
    ledger = tmp_path / "feedback.jsonl"
    out = mb.feedback_ingest(ROOT, "demo", _rec(by="visitor:"), ledger=ledger, channel="remote")
    assert "error" in out
    assert not ledger.exists() or ledger.read_text().strip() == ""


def test_remote_visitor_with_name_is_folded_verbatim(tmp_path):
    ledger = tmp_path / "feedback.jsonl"
    out = mb.feedback_ingest(ROOT, "demo", _rec(by="visitor:anna"), ledger=ledger,
                              channel="remote")
    assert out.get("ok"), out
    stored = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert stored["by"] == "visitor:anna"


def test_remote_author_handle_is_reminted_author_claimed(tmp_path):
    """The username-as-key (his ruling, 2026-07-11): the handle unlocks author-tier
    routing but the mark stays 'author-claimed:' — never 'gerard' — so a forged
    claimant can't silently write in the author's own voice."""
    ledger = tmp_path / "feedback.jsonl"
    out = mb.feedback_ingest(ROOT, "demo", _rec(by="visitor:phujck"), ledger=ledger,
                              channel="remote")
    assert out.get("ok"), out
    stored = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert stored["by"] == "author-claimed:phujck"


def test_remote_author_handle_case_and_space_insensitive(tmp_path):
    ledger = tmp_path / "feedback.jsonl"
    out = mb.feedback_ingest(ROOT, "demo", _rec(by="visitor: Phujck "), ledger=ledger,
                              channel="remote")
    assert out.get("ok"), out
    stored = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert stored["by"] == "author-claimed:phujck"


def test_remote_author_handle_never_mints_gerard(tmp_path):
    """The handle routes author-tier; it must not cross into the local channel's
    author identity."""
    ledger = tmp_path / "feedback.jsonl"
    mb.feedback_ingest(ROOT, "demo", _rec(by="visitor:phujck"), ledger=ledger,
                       channel="remote")
    stored = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert stored["by"] != "gerard"
    assert stored["by"].lower() not in mb.AUTHOR_ACTORS


def test_local_channel_defaults_to_gerard_unchanged(tmp_path):
    """Regression: today's law for the author's own local flow is untouched."""
    ledger = tmp_path / "feedback.jsonl"
    out = mb.feedback_ingest(ROOT, "demo", _rec(), ledger=ledger)  # channel default "local"
    assert out.get("ok"), out
    stored = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert stored["by"] == "gerard"


def test_drain_remote_channel_leaves_refused_file_in_inbox(tmp_path):
    df = _load_drain()
    mdir = tmp_path / "manuscript" / "whitepaper"
    inbox = mdir / "feedback" / "inbox"
    inbox.mkdir(parents=True)
    root = mdir / "main.tex"
    root.write_text("\\documentclass{article}\\begin{document}x\\end{document}")

    good = _rec(fb_id="FB-2026-good", by="visitor:anna")
    forged = _rec(fb_id="FB-2026-forged", by="gerard")
    (inbox / "good.json").write_text(json.dumps(good))
    (inbox / "forged.json").write_text(json.dumps(forged))

    out = df.drain(str(root), "demo", channel="remote")
    assert out["found"] == 2
    assert out["ingested"] == 1
    assert out["refused"] == 1

    ledger = mdir / "feedback" / "feedback.jsonl"
    lines = [ln for ln in ledger.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["id"] == "FB-2026-good"

    # the accepted file was folded and deleted; the refused one is preserved as evidence
    assert not (inbox / "good.json").is_file()
    assert (inbox / "forged.json").is_file()
