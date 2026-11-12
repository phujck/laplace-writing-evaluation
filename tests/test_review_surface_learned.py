"""The 2026-07-11 learning-loop build on the review surface (scout holes 1-4 +
the actor-guard incident): the /review/learned rollup and its Law I budget, the
stateless ``since`` cursor on findings/substrate, the fork fold into the
substrate queue, the findings facet + head (the 2053-finding scroll wall), the
adjudicate door's ACTOR GUARD (RW-20260711-103301-400002 regression), and the
/conceptric2 offline-boot contract.

Same idioms as ``test_review_surface.py``: synthetic manuscript trees + fixture
friction ledgers under tmp_path; the handle() probes on the live corpus are
read-only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.manuscript import review_surface as rv
from laplace.web import review_http
from laplace.pipeline import friction_consumer as fc
from laplace.pipeline.ledger import read_jsonl

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# fixtures — the test_review_surface idioms
# ---------------------------------------------------------------------------

def _sectioned(tmp_path, feedback=None, s1="Original body of section one.\n"):
    md = tmp_path / "wp"
    md.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}\\input{S1}\\end{document}",
        encoding="utf-8")
    (md / "S1.tex").write_text(s1, encoding="utf-8")
    (md / "main.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    if feedback is not None:
        (md / "feedback").mkdir()
        (md / "feedback" / "feedback.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in feedback), encoding="utf-8")
    return md


def _ledger(md):
    p = md / "feedback" / "feedback.jsonl"
    return read_jsonl(p) if p.is_file() else []


def _friction_dir(tmp_path, name, records):
    fd = tmp_path / "corpus_friction"
    fd.mkdir(exist_ok=True)
    (fd / f"{name}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return fd


def _fr(rid, *, kind="friction", node="surface/x", layer="review_surface.py",
        ts="2026-07-11T09:00:00", value="a stumble", **extra):
    rec = {"id": rid, "ts": ts, "kind": kind, "node": node, "target": "t",
           "value": value, "by": "eigen", "status": "open",
           "owning_layer": layer}
    rec.update(extra)
    return rec


def _res(rid, target, *, evidence="commit abc123", ts="2026-07-11T10:00:00"):
    rec = fc.make_friction_resolution(target, evidence=evidence or "x",
                                      rec_id=rid, ts=ts)
    if not evidence:
        rec["evidence"] = ""                        # the evidence-less shape under test
    return rec


# ---------------------------------------------------------------------------
# /review/learned — the rollup (scout hole 1) and the Law I mechanical budget
# ---------------------------------------------------------------------------

def test_learned_groups_consumed_by_layer_with_evidence(tmp_path):
    fd = _friction_dir(tmp_path, "laplace_engine", [
        _fr("RW-1", layer="scripts/wake.py", value="wake stumbled"),
        _fr("RW-2", layer="scripts/wake.py", value="still open here"),
        _fr("RW-3", kind="fork", layer="protocol", value="does verdict auto-apply?"),
        _res("RES-1", "RW-1", evidence="commit abc123", ts="2026-07-11T10:00:00"),
    ])
    out = rv.learned(friction_dir=fd)
    # the consumed row carries its layer + resolution evidence
    assert out["consumed_total"] == 1
    row = out["rows"][0]
    assert row["id"] == "RW-1" and row["layer"] == "scripts/wake.py"
    assert row["evidence"] == "commit abc123" and row["resolution"] == "RES-1"
    # open counts: RW-2 (friction) + RW-3 (fork) — counts, and the fork row heads
    assert out["open"] == {"friction": 1, "fork": 1, "total": 2,
                           "by_layer": {"protocol": 1, "scripts/wake.py": 1}}
    assert [f["id"] for f in out["forks"]] == ["RW-3"]
    assert out["flagged"] == 0 and out["truncated"] is False


def test_learned_evidence_less_resolution_flagged_target_stays_open(tmp_path):
    fd = _friction_dir(tmp_path, "laplace_engine", [
        _fr("RW-1"),
        _res("RES-1", "RW-1", evidence="", ts="2026-07-11T10:00:00"),
    ])
    out = rv.learned(friction_dir=fd)
    assert out["consumed_total"] == 0 and out["rows"] == []
    assert out["flagged"] == 1
    assert out["open"]["friction"] == 1                  # the target stays OPEN


def test_learned_law_one_budget_rows_and_bytes(tmp_path):
    # 200 consumed frictions across 10 layers: the golden numbers hold — ≤40
    # rows, ≤16KB of JSON — and the totals stay honest.
    recs = []
    for i in range(200):
        recs.append(_fr(f"RW-{i:03d}", layer=f"layer-{i % 10}",
                        value="a long stumble description " * 6,
                        ts=f"2026-07-10T{i % 24:02d}:00:00"))
        recs.append(_res(f"RES-{i:03d}", f"RW-{i:03d}",
                         evidence="commit " + "e" * 40,
                         ts=f"2026-07-11T{i % 24:02d}:00:00"))
    fd = _friction_dir(tmp_path, "laplace_engine", recs)
    out = rv.learned(friction_dir=fd)
    assert out["consumed_total"] == 200
    assert out["shown"] <= rv._LEARNED_MAX_ROWS
    assert len(out["rows"]) + len(out["forks"]) == out["shown"]
    payload = json.dumps(out, ensure_ascii=False).encode("utf-8")
    assert len(payload) <= rv._LEARNED_MAX_BYTES
    assert out["truncated"] is True


def test_learned_since_cursor_filters_new_resolutions(tmp_path):
    fd = _friction_dir(tmp_path, "laplace_engine", [
        _fr("RW-1"), _fr("RW-2"),
        _res("RES-1", "RW-1", ts="2026-07-10T09:00:00"),
        _res("RES-2", "RW-2", ts="2026-07-11T09:00:00"),
    ])
    out = rv.learned(friction_dir=fd, since="2026-07-10T12:00:00")
    assert [r["id"] for r in out["rows"]] == ["RW-2"]    # only the newer one
    assert out["rows_matched"] == 1
    assert out["consumed_total"] == 2                    # totals stay full
    assert out["since"] == "2026-07-10T12:00:00"


def test_handle_learned_live_repo_within_budget():
    # read-only against the LIVE ledgers: the route resolves with no corpus and
    # the Law I budget holds on real data.
    st, ct, body = review_http.handle("/review/learned", {}, "GET", b"")
    assert st == 200 and "application/json" in ct
    j = json.loads(body)
    assert set(j) >= {"rows", "forks", "open", "consumed_total", "ledgers",
                      "truncated", "budget"}
    assert len(j["rows"]) + len(j["forks"]) <= rv._LEARNED_MAX_ROWS
    assert len(body) <= rv._LEARNED_MAX_BYTES
    # the engine ledger is always one of the reduced sources
    assert any(l.endswith("laplace_engine.jsonl") for l in j["ledgers"])


# ---------------------------------------------------------------------------
# the stateless ``since`` cursor on findings + substrate (scout hole 2, Fork 7:
# the baseline is the CLIENT's — nothing here writes a visit record)
# ---------------------------------------------------------------------------

def test_findings_since_filters_by_ts_and_drops_ts_less(tmp_path):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-old", "node_id": "S1", "kind": "note", "anchor": {},
         "comment": "old", "ts": "2026-07-09T10:00:00"},
        {"id": "FB-new", "node_id": "S1", "kind": "note", "anchor": {},
         "comment": "new", "ts": "2026-07-11T10:00:00"},
        {"id": "FB-nots", "node_id": "S1", "kind": "note", "anchor": {},
         "comment": "no ts at all"},
    ])
    out = rv.findings(md, "smoke", since="2026-07-10T00:00:00")
    ids = {f["id"] for f in out["unanchored"]}
    assert ids == {"FB-new"}                             # old + ts-less drop out
    assert out["since"] == "2026-07-10T00:00:00"
    # no cursor -> everything, and the response says so
    full = rv.findings(md, "smoke")
    assert {f["id"] for f in full["unanchored"]} == {"FB-old", "FB-new", "FB-nots"}
    assert full["since"] is None
    # the SERVER wrote nothing anywhere: the ledger is exactly the 3 deposits
    assert len(_ledger(md)) == 3


def test_route_plan_lands_projection_intent_with_verb_and_object(tmp_path):
    md = _sectioned(tmp_path, feedback=[])
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "route-plan", "plan_verb": "DEMOTE",
        "object": {"kind": "section", "sid": "N7"}, "note": "fold into N6",
        "finding_id": "FB-42", "kind": "novelty-overbroad"})
    assert res["ok"] and res["record"]["record"] == "projection-intent"
    rec = res["record"]
    assert rec["verb"] == "DEMOTE" and rec["object"] == {"kind": "section", "sid": "N7"}
    assert rec["target"] == "FB-42" and rec["scope"] == "plan"
    assert rec["payload"]["finding_kind"] == "novelty-overbroad"
    # it surfaces in the substrate queue beside the intents (never vanishes)
    q = rv.substrate_queue(md)
    pi = next(it for it in q["queue"] if it["kind"] == "projection-intent")
    assert pi["intent"] == "DEMOTE" and pi["object_key"] == "N7"
    assert pi["target"] == "FB-42"
    # idempotent: the same finding+verb+object re-posts as a no-op
    again = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "route-plan", "plan_verb": "DEMOTE",
        "object": {"kind": "section", "sid": "N7"}, "finding_id": "FB-42"})
    assert again.get("idempotent") is True


def test_route_plan_actor_guard_and_validation(tmp_path):
    md = _sectioned(tmp_path, feedback=[])
    # no actor -> refused BEFORE any append (the RW-20260711 actor-guard incident)
    noby = rv.adjudicate(md, "smoke", {
        "verb": "route-plan", "plan_verb": "CUT", "finding_id": "FB-1"})
    assert "error" in noby and "by" in noby["error"]
    # a finding id is required (a plan intent rules on a finding)
    nofid = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "route-plan", "plan_verb": "CUT"})
    assert "error" in nofid and "finding_id" in nofid["error"]
    # an out-of-vocabulary plan verb is refused by name
    badverb = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "route-plan", "plan_verb": "NUKE",
        "finding_id": "FB-1"})
    assert "error" in badverb and "plan_verb" in badverb["error"]
    # nothing was appended by any refused request
    assert not (md / "feedback" / "feedback.jsonl").exists() \
        or rv.substrate_queue(md)["count"] == 0


def test_substrate_since_filters_queue(tmp_path):
    md = _sectioned(tmp_path, feedback=[])
    rv.adjudicate(md, "smoke", {"by": "author", "verb": "route-conceptric",
                                "node": "def:x", "intent": "essence-wrong"})
    q_all = rv.substrate_queue(md)
    assert q_all["count"] == 1
    ts = q_all["queue"][0]["ts"]
    assert rv.substrate_queue(md, since=ts)["count"] == 0        # nothing newer
    assert rv.substrate_queue(md, since="2000-01-01T00:00:00")["count"] == 1


# ---------------------------------------------------------------------------
# fork records fold into the substrate queue (scout hole 3 — extend, not a route)
# ---------------------------------------------------------------------------

def test_substrate_queue_folds_open_forks_beside_intents(tmp_path):
    fd = _friction_dir(tmp_path, "fixture-corpus", [
        _fr("RW-F1", kind="fork", node="surface/verdict-apply",
            layer="protocol", value="does a ratify auto-apply?"),
        _fr("RW-F2", kind="fork", node="surface/retired", value="already ruled",
            ts="2026-07-10T09:00:00"),
        _res("RES-F2", "RW-F2", evidence="OPEN_STACK row F7"),
        _fr("RW-N1", kind="friction", value="not a fork — never queues here"),
    ])
    md = _sectioned(tmp_path, feedback=[])
    rv.adjudicate(md, "smoke", {"by": "author", "verb": "calibrate",
                                "finding_kind": "eq-unused"})
    q = rv.substrate_queue(md, corpus="fixture-corpus", friction_dir=fd)
    kinds = [it["kind"] for it in q["queue"]]
    assert kinds.count("fork") == 1                      # open fork only
    assert kinds.count("calibration-intent") == 1        # intents undisturbed
    fork = next(it for it in q["queue"] if it["kind"] == "fork")
    assert fork["id"] == "RW-F1" and fork["node"] == "surface/verdict-apply"
    assert fork["intent"] == "author-fork"
    assert "auto-apply" in fork["note"]
    assert fork["owning_layer"] == "protocol"
    # the consumed fork (evidence-carrying resolution) and the plain friction
    # never queue; an absent / unknown corpus keeps the queue intents-only
    ids = {it["id"] for it in q["queue"]}
    assert "RW-F2" not in ids and "RW-N1" not in ids
    assert all(it["kind"] != "fork"
               for it in rv.substrate_queue(md, corpus="no-such",
                                            friction_dir=fd)["queue"])


# ---------------------------------------------------------------------------
# the findings facet + head (scout hole 4 — the 254,273px scroll wall)
# ---------------------------------------------------------------------------

def _many_findings(tmp_path, n_hard=5, n_soft=3):
    fb = []
    for i in range(n_hard):
        fb.append({"id": f"FB-H{i}", "node_id": "S1", "kind": "refute",
                   "anchor": {}, "comment": f"hard {i}",
                   "ts": f"2026-07-11T0{i}:00:00"})
    for i in range(n_soft):
        fb.append({"id": f"FB-S{i}", "node_id": "S1", "kind": "note",
                   "anchor": {}, "comment": f"soft {i}",
                   "ts": f"2026-07-11T1{i}:00:00"})
    return _sectioned(tmp_path, feedback=fb)


def test_board_head_limit_and_truncation(tmp_path):
    md = _many_findings(tmp_path)
    board = rv._board_head(rv.findings(md, "smoke"), limit=3)
    assert board["shown"] == 3 and board["matched"] == 8
    assert board["truncated"] is True
    assert board["counts"]["total"] == 8                 # full counts stay honest
    shown = [f["id"] for f in board["unanchored"]]
    assert len(shown) == 3
    # offset pages past the head
    page2 = rv._board_head(rv.findings(md, "smoke"), limit=3, offset=3)
    assert page2["shown"] == 3
    assert set(f["id"] for f in page2["unanchored"]).isdisjoint(shown)


def test_board_head_class_facet(tmp_path):
    md = _many_findings(tmp_path)
    board = rv._board_head(rv.findings(md, "smoke"), cls="hard")
    assert board["matched"] == 5 and board["shown"] == 5
    assert all(f["cls"] == "hard" for f in board["unanchored"])
    assert board["truncated"] is False and board["cls"] == "hard"
    # facet + head compose
    b2 = rv._board_head(rv.findings(md, "smoke"), cls="soft", limit=2)
    assert b2["matched"] == 3 and b2["shown"] == 2 and b2["truncated"] is True


def test_board_head_noop_without_params(tmp_path):
    md = _many_findings(tmp_path)
    board = rv._board_head(rv.findings(md, "smoke"))
    assert board["shown"] == board["matched"] == board["counts"]["total"] == 8
    assert board["truncated"] is False


def test_handle_findings_head_params(tmp_path, monkeypatch):
    md = _many_findings(tmp_path)
    monkeypatch.setattr(rv, "manuscript_dir", lambda corpus="", dir_param="": md)
    st, _, body = review_http.handle("/review/findings",
                            {"dir": ["wp"], "cls": ["hard"], "limit": ["2"]},
                            "GET", b"")
    j = json.loads(body)
    assert st == 200 and j["shown"] == 2 and j["matched"] == 5
    assert j["truncated"] is True and j["limit"] == 2
    # a malformed limit degrades to the full board, never a 500
    st2, _, body2 = review_http.handle("/review/findings",
                              {"dir": ["wp"], "limit": ["bogus"]}, "GET", b"")
    assert st2 == 200 and json.loads(body2)["truncated"] is False


# ---------------------------------------------------------------------------
# THE ACTOR GUARD — the scout's live incident, regression-tested in its shape:
# unauthenticated clicks fired confirm/overrule/defer and minted actor=author
# records. Now: no explicit ``by`` -> 422, NOTHING appended.
# ---------------------------------------------------------------------------

def test_adjudicate_without_actor_refused_nothing_minted(tmp_path):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-1", "node_id": "S1", "kind": "eq-unused", "anchor": {},
         "comment": "c"}])
    n0 = len(_ledger(md))
    # the incident's three verbs, replayed WITHOUT an actor
    for payload in ({"verb": "confirm", "finding_id": "FB-1"},
                    {"verb": "defer", "finding_id": "FB-1"},
                    {"verb": "revoke-intent", "supersedes": "CI-x"}):
        res = rv.adjudicate(md, "smoke", payload)
        assert "error" in res and "by (explicit actor)" in res["error"], payload
    assert len(_ledger(md)) == n0                        # ZERO records minted
    # a whitespace-only actor is no actor
    res = rv.adjudicate(md, "smoke", {"verb": "confirm", "finding_id": "FB-1",
                                      "by": "   "})
    assert "error" in res and len(_ledger(md)) == n0
    # with an explicit actor the same verb lands, attributed to it
    ok = rv.adjudicate(md, "smoke", {"verb": "confirm", "finding_id": "FB-1",
                                     "by": "eigen-scout"})
    assert ok["ok"] and ok["record"]["provenance"]["actor"] == "eigen-scout"
    assert ok["record"]["source"] == "eigen-scout"


def test_handle_adjudicate_actorless_is_422(tmp_path, monkeypatch):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-1", "node_id": "S1", "kind": "note", "anchor": {},
         "comment": "c"}])
    monkeypatch.setattr(rv, "manuscript_dir", lambda corpus="", dir_param="": md)
    body = json.dumps({"verb": "confirm", "finding_id": "FB-1",
                       "dir": "wp"}).encode()
    st, _, resp = review_http.handle("/review/adjudicate", {}, "POST", body)
    assert st == 422
    assert "by (explicit actor)" in json.loads(resp)["error"]
    assert len(_ledger(md)) == 1                         # the deposit only
    # the UI's shape (mloc carries by) succeeds
    body2 = json.dumps({"verb": "confirm", "finding_id": "FB-1", "dir": "wp",
                        "by": "author"}).encode()
    st2, _, _ = review_http.handle("/review/adjudicate", {}, "POST", body2)
    assert st2 == 200


def test_unknown_verb_still_reads_as_unknown_before_actor_guard(tmp_path):
    md = _sectioned(tmp_path)
    res = rv.adjudicate(md, "smoke", {"verb": "bogus"})
    assert "unknown adjudication verb" in res["error"]


def test_ui_supplies_the_actor_nowhere_defaulted():
    # THE LIVE CLAUSE (the security teeth): the adjudication EXECUTOR defaults the actor
    # NOWHERE — the old "author" fallback is gone from review_surface.py, so a verb with no
    # actor is refused, never silently attributed. W2: review_surface.html folded into the
    # artefact surface; the executor guard is where the teeth live and it stays green. The
    # annotate mode's adjudication-verb UI is a named W2 follow-up (the executors are wired).
    src = (Path(rv.__file__).parent / "review_surface.py").read_text(
        encoding="utf-8")
    assert '"author").strip() or "author"' not in src    # the old default is gone


# ---------------------------------------------------------------------------
# /conceptric boots OFFLINE — nothing off-box; math rides the shared lazy KaTeX
# (W3 rebuild: conceptric_editor2.html -> conceptric.html; the inline unbounded
# katex wait that was the scout stumble no longer exists — math loads on demand
# through shell.js window.renderMath, which vendors /shared/katex).
# ---------------------------------------------------------------------------

def test_conceptric_no_cdn_and_module_boot():
    html = (Path(rv.__file__).parents[1] / "web" / "conceptric.html").read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net" not in html                # nothing off-box
    assert "//cdn" not in html and "https://" not in html  # no external boot dependency
    # the surface is a thin shell on the shared model: hymn.css + shell.js + the pane module.
    assert "/shared/hymn.css" in html
    assert "/shared/shell.js" in html
    # UPDATED TO CURRENT TRUTH (W-TRIAGE 2026-07-22): conceptric.html now boots the GROWTH COCKPIT
    # (cockpit-panes.mjs / initCockpit) — growth-cockpit.html superseded, landed live at /conceptric
    # (E2/E3, mocks/README_RETIRED.md). Behaviour lives in the shared cockpit module now.
    assert "/shared/cockpit-panes.mjs" in html           # behaviour lives in the shared module
    # math renders through the shared lazy renderer (no inline katex boot loop to hang on).
    assert "katex" not in html.lower()


def test_vendored_katex_served_by_shared_ui():
    from laplace.web import shared_ui
    for name in ("katex/katex.min.js", "katex/katex.min.css"):
        st, ctype, body = shared_ui.handle("/shared/" + name, {})
        assert st == 200 and len(body) > 1000, name
