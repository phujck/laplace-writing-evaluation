"""The founding walk-serve slice — gates with their reds demonstrated, STATE-INDEPENDENT
(codex packet-refusal cure 4: the first suite broke the moment the author walked everything;
walked state is now fixtured, and the live all-walked state is proved separately).

Covers: exact-span descent (text-span sha contract, refuse-not-substitute), DRIFT rendering
(the handle law — content may move beneath a handle; a read shows drift, never substitutes
silently, never refuses), URL semantics (the # that a browser eats as a fragment), custody
at mint (a shown digest resolves by lookup), typed closure (no id-suffix authority), and the
POST door's refusals. scripts/atlas_walk_serve.py src/laplace/web/front_door.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

_spec = importlib.util.spec_from_file_location(
    "walk_serve_under_test", ROOT / "scripts" / "atlas_walk_serve.py")
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)

OPEN_STATE = {"card2": {}, "card3": {}}

TEST_CARD = [{
    "id": "cardT", "glance": "test card", "why_now": "w", "question": "q",
    "options": [{"o": "a", "c": "b"}], "recommendation": "r", "alternative": "alt",
    "blocks": "b", "cost_of_delay": "c", "store_write": "s", "irreversibility": "i",
    "grounds": [{"handle": "DESIGN_2026-08-24_the-interface-merge.md#L1-L1",
                 "label": "t", "why": "t"}],
    "residual": "none"}]


def test_descent_exact_and_refusals(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("alpha\nbeta\ngamma\ndelta\n", encoding="utf-8")
    r = ws.resolve_handle("doc.md#L2-L3", root=tmp_path)
    assert r["content"] == "beta\ngamma"
    assert r["span_text_sha256"] == hashlib.sha256(b"beta\ngamma").hexdigest()
    assert r["file_sha256"] == hashlib.sha256(f.read_bytes()).hexdigest()
    assert "ABSENT" in ws.resolve_handle("gone.md#L1-L2", root=tmp_path)["error"]
    assert "refused, not clipped" in ws.resolve_handle("doc.md#L1-L9", root=tmp_path)["error"]
    assert "escapes" in ws.resolve_handle("../etc/passwd#L1-L1", root=tmp_path)["error"]


def test_drift_renders_never_substitutes_never_refuses(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("one\ntwo\n", encoding="utf-8")
    minted = ws.resolve_handle("doc.md#L1-L2", root=tmp_path)["span_text_sha256"]
    f.write_text("one\nMOVED\n", encoding="utf-8")          # the ground moves beneath
    r = ws.resolve_handle("doc.md#L1-L2", root=tmp_path, expect_text_sha=minted)
    assert "error" not in r                                  # read path never refuses drift
    assert r["content"] == "one\nMOVED"                      # current content, honestly
    assert r["drift"]["expected"] == minted                  # shown-then named
    assert r["drift"]["found"] == r["span_text_sha256"]
    same = ws.resolve_handle("doc.md#L1-L2", root=tmp_path,
                             expect_text_sha=r["span_text_sha256"])
    assert "drift" not in same                               # no false drift


def test_rendered_hrefs_survive_browser_url_semantics(monkeypatch):
    monkeypatch.setattr(ws, "_walked_cards", lambda: dict(OPEN_STATE))
    monkeypatch.setattr(ws, "_cards", lambda: [dict(c) for c in TEST_CARD])
    b = ws.build()
    html = ws.render_html(b)
    hrefs = re.findall(r'data-h="([^"]+)"', html)
    assert hrefs, "cards must carry ground buttons"
    for h in hrefs:
        assert "#" not in h, f"raw # reaches the browser and dies as a fragment: {h}"
        url = f"/front/walk?handle={h}&format=json"
        split = urlsplit(url)                                # browser semantics
        assert split.fragment == ""                          # nothing eaten
        got = parse_qs(split.query)["handle"][0]
        assert "#L" in unquote(got)                          # server receives the full range


def test_custody_at_mint_and_digest_stability(monkeypatch):
    monkeypatch.setattr(ws, "_walked_cards", lambda: dict(OPEN_STATE))
    monkeypatch.setattr(ws, "_cards", lambda: [dict(c) for c in TEST_CARD])
    b1, b2 = ws.build(), ws.build()
    assert b1["serve_digest"] == b2["serve_digest"]          # produced_at outside the key
    banked = ws.custody_resolve(b1["serve_digest"])
    assert banked is not None, "a shown digest must resolve by lookup — custody at mint"
    assert ws.custody_verify(b1["serve_digest"])             # rehash proof, organ-side
    assert not ws.custody_verify("0" * 64)                   # absence never verifies
    assert ws.custody_resolve("0" * 64) is None              # absence is None, never invented
    assert b1["open_count"] == len(([b1["anchor"]] if b1["anchor"] else []) + b1["rails"])


def test_typed_closure_no_suffix_authority(tmp_path, monkeypatch):
    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    store.parent.mkdir(parents=True)
    rows = [
        # forged: right suffix, wrong record class — must NOT close
        {"record": "note", "id": "NOTE-x-founding-card-confirm-shown-walked"},
        # forged: typed-ish but shown_handle unresolvable — must NOT close
        {"record": "walk-verdict", "id": "RES-x-founding-card-confirm-shown-walked",
         "stage": "founding-card-confirm-shown", "verdict": "accepted",
         "actor": "gerard", "shown_handle": "0" * 64},
        # historical exact id — closes with RED custody stamp
        {"record": "walk-verdict", "id": "VERDICT-20260824-card2-honest-geometry-walked"},
    ]
    store.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(ws, "ROOT", tmp_path)
    ws.CUSTODY.mkdir(parents=True, exist_ok=True)
    state = ws._walked_cards()
    assert "card2" in state and "RED" in state["card2"]["custody"]
    assert "card-confirm-shown" not in state                 # both forgeries refused


def test_post_door_refusals_and_happy_path(monkeypatch):
    from laplace.web import front_door as fd
    fd._walk_serve_module.cache_clear()
    m = fd._walk_serve_module()
    monkeypatch.setattr(m, "_walked_cards", lambda: dict(OPEN_STATE))
    monkeypatch.setattr(m, "_cards", lambda: [dict(c) for c in TEST_CARD])
    live = m.build()
    first = ([live["anchor"]] if live["anchor"] else live["rails"])[0]["id"]

    def post(body):
        return fd._walk_serve_verdict(json.dumps(body).encode())

    st, _, p = post({"card": first, "verdict": "accept"})
    assert st == 400 and b"shown digest" in p
    st, _, p = post({"card": first, "verdict": "amend",
                     "shown_handle": live["serve_digest"], "text": ""})
    assert st == 400 and b"words first" in p
    st, _, p = post({"card": first, "verdict": "accept", "shown_handle": "x" * 64})
    assert st == 409 and b"REFUSED stale" in p
    st, _, p = post({"card": "card2", "verdict": "accept",
                     "shown_handle": live["serve_digest"]})
    assert st == 400 and b"not open" in p

    banked = {}
    monkeypatch.setattr("laplace.core.records.journal.bank_row",
                        lambda store, row, **kw: banked.update(row))
    st, _, p = post({"card": first, "verdict": "accept",
                     "shown_handle": live["serve_digest"]})
    out = json.loads(p)
    assert st == 200 and banked["shown_handle"] == live["serve_digest"]
    assert banked["actor"] == "gerard" and banked["record"] == "walk-verdict"
    assert out["open_count"] == live["open_count"] - 1


def test_all_five_historical_shown_objects_resolve():
    """Every founding act's shown digest resolves from rows through ONE custody home,
    and every json payload in custody rehash-verifies — the whole store, not samples."""
    state = ws._walked_cards()
    assert len(state) == 5
    for card, v in state.items():
        assert v["custody"] == "resolves", f"{card}: {v}"
        assert ws.custody_has(v["shown"]), card
    for f in ws.CUSTODY.glob("*.json"):
        assert ws.custody_verify(f.stem), f"{f.name} must rehash-verify"


def test_live_all_states_render():
    """The REAL repo state, whatever it is — the suite must hold before and after his acts."""
    b = ws.build()
    html = ws.render_html(b)
    assert f'id="opencount">{b["open_count"]}<' in html      # per-pane self-consistency
    assert ws.custody_resolve(b["serve_digest"]) is not None
    for k in ("card2", "card3"):
        assert k in b["walked"]                              # his banked verdicts, always
    if b["open_count"] == 0:
        assert "every decision here is walked" in html
