"""THE ACTOR LAW, closed on the /corpus/feedback door (W-HANDS).

Bug (code-verified): POST /corpus/feedback did not enforce the actor law —
``manuscript_bridge.feedback_add`` silently defaulted ``by="gerard"`` (the
author's name as a silent default is the EXACT violation the actor law
forbids: "no door defaults his name; probes identify themselves"). The
sibling doors ``/corpus/friction``, ``/desk/act`` and
``/storyboard/run/launch`` already 422 an unattributed write.

This shard closes the hole two ways, mirroring ``/corpus/friction``'s own
pattern exactly:

1. ``manuscript_bridge.feedback_add``'s own silent default is now
   ``by="eigen"`` (the engine, never his name) — a fallback for internal
   Python callers that already name themselves, never a stand-in for a
   caller that skipped attribution.
2. The scanner's ``/corpus/feedback`` HTTP door refuses an unattributed
   write outright: no ``by`` on the payload is a 422, before any ledger
   touch — the same posture ``/corpus/friction`` already holds.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from laplace.manuscript import manuscript_bridge
from laplace.web import scanner

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------
# 1. manuscript_bridge.feedback_add — the silent default is "eigen", never
#    "gerard" (the author's name is never a silent default).
# --------------------------------------------------------------------------

def test_feedback_add_default_actor_is_eigen_not_gerard(tmp_path):
    ledger = tmp_path / "feedback.jsonl"
    out = manuscript_bridge.feedback_add(
        tmp_path, "proj",
        {"node_id": "n1", "comment": "no actor named"},
        ledger=ledger,
    )
    assert out.get("ok") is True, out
    assert out["record"]["by"] == "eigen", (
        "feedback_add's silent default must be the engine (eigen), never "
        "the author's name — a silent 'gerard' default IS the actor-law hole")
    assert out["record"]["by"] != "gerard"

    on_disk = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert on_disk["by"] == "eigen"


def test_feedback_add_still_honours_an_explicit_actor(tmp_path):
    """Callers that already name themselves (growth_surface, review_surface,
    the HTTP door) are unaffected — only the SILENT default moved."""
    ledger = tmp_path / "feedback.jsonl"
    out = manuscript_bridge.feedback_add(
        tmp_path, "proj",
        {"node_id": "n1", "comment": "attributed", "by": "author"},
        ledger=ledger,
    )
    assert out.get("ok") is True, out
    assert out["record"]["by"] == "author"


def test_feedback_ingest_local_channel_default_is_unchanged(tmp_path):
    """Out of this bug's scope (feedback_ingest is a different door, owned
    elsewhere) — a guard that this fix did not touch its documented local-
    channel behaviour."""
    ledger = tmp_path / "feedback.jsonl"
    out = manuscript_bridge.feedback_ingest(
        tmp_path, "proj",
        {"id": "FB-x", "node_id": "n1", "comment": "drained locally"},
        ledger=ledger, channel="local",
    )
    assert out.get("ok") is True, out
    on_disk = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert on_disk["by"] == "gerard"


# --------------------------------------------------------------------------
# 2. the /corpus/feedback HTTP door — mirrors /corpus/friction's 422
# --------------------------------------------------------------------------

def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read())


def _serve(monkeypatch, tmp_path, ledger: Path):
    """A scanner HTTP server whose /corpus/feedback ledger resolution is
    pinned to ``ledger`` — bypasses the project registry (irrelevant to the
    actor-law question this shard tests) exactly the way
    test_author_goal_tension.py pins ``demand._corpus_feedback_ledger``."""
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(scanner, "_corpus_feedback_ledger", lambda rr, name: ledger)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


def test_corpus_feedback_door_refuses_unattributed_write(tmp_path, monkeypatch):
    ledger = tmp_path / "feedback.jsonl"
    httpd, port = _serve(monkeypatch, tmp_path, ledger)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/corpus/feedback",
            data=json.dumps({"corpus": "proj", "node_id": "n1",
                             "comment": "no actor named"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(req, timeout=5)
        assert ei.value.code == 422
        err = json.loads(ei.value.read())
        assert "actor" in err.get("error", "").lower() or "attributed" in err.get("error", "").lower()
    finally:
        httpd.shutdown()

    assert not ledger.is_file(), "an unattributed write must never touch the ledger"


def test_corpus_feedback_door_refuses_blank_actor(tmp_path, monkeypatch):
    """Whitespace-only ``by`` is the same hole as absent ``by`` (mirrors the
    friction door's ``str(payload.get('by') or '').strip()`` guard)."""
    ledger = tmp_path / "feedback.jsonl"
    httpd, port = _serve(monkeypatch, tmp_path, ledger)
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/corpus/feedback",
            data=json.dumps({"corpus": "proj", "node_id": "n1",
                             "comment": "blank actor", "by": "   "}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with pytest.raises(urllib.error.HTTPError) as ei:
            urllib.request.urlopen(req, timeout=5)
        assert ei.value.code == 422
    finally:
        httpd.shutdown()


def test_corpus_feedback_door_banks_an_attributed_comment(tmp_path, monkeypatch):
    ledger = tmp_path / "feedback.jsonl"
    httpd, port = _serve(monkeypatch, tmp_path, ledger)
    try:
        res = _post(
            f"http://127.0.0.1:{port}/corpus/feedback",
            {"corpus": "proj", "node_id": "n1", "comment": "attributed comment",
             "kind": "note", "by": "author"},
        )
    finally:
        httpd.shutdown()

    assert res.get("record", {}).get("by") == "author", res
    assert ledger.is_file()
    rec = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert rec["by"] == "author"
    assert rec["comment"] == "attributed comment"


# --------------------------------------------------------------------------
# 3. the /assets/assess door (assets_surface._assess) — the same hole as
#    /corpus/feedback: it called manuscript_bridge.feedback_add without
#    requiring ``by``, so an unattributed POST would have landed on
#    feedback_add's own "eigen" fallback instead of refusing at the door
#    (mirrors this file's sibling _regen door, which already 422s).
# --------------------------------------------------------------------------

def _assess(monkeypatch, tmp_path, payload: dict) -> tuple[int, dict]:
    from laplace.web import assets_surface as asf
    from laplace.manuscript import review_surface as rs
    md = tmp_path / "manuscript"
    md.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rs, "manuscript_dir", lambda corpus, dir_param="": md)
    status, ctype, raw = asf._assess("proj", payload, tmp_path)
    return status, json.loads(raw)


def test_assets_assess_door_refuses_unattributed_write(tmp_path, monkeypatch):
    status, err = _assess(monkeypatch, tmp_path,
                          {"node_id": "n1", "comment": "no actor named"})
    assert status == 422, err
    assert "actor" in err.get("error", "").lower() or "attributed" in err.get("error", "").lower()
    ledger = tmp_path / "manuscript" / "feedback" / "feedback.jsonl"
    assert not ledger.is_file(), "an unattributed assess write must never touch the ledger"


def test_assets_assess_door_refuses_blank_actor(tmp_path, monkeypatch):
    status, err = _assess(monkeypatch, tmp_path,
                          {"node_id": "n1", "comment": "blank actor", "by": "   "})
    assert status == 422, err


def test_assets_assess_door_banks_an_attributed_finding(tmp_path, monkeypatch):
    status, res = _assess(monkeypatch, tmp_path,
                          {"node_id": "n1", "comment": "attributed finding",
                           "kind": "note", "by": "author"})
    assert status == 200, res
    assert res.get("record", {}).get("by") == "author", res
    ledger = tmp_path / "manuscript" / "feedback" / "feedback.jsonl"
    assert ledger.is_file()
    rec = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert rec["by"] == "author"
    assert rec["comment"] == "attributed finding"
