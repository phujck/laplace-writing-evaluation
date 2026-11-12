"""The review viewer (G-2) data layer: node extraction, class badging, the
node-precise findings grouping, the nodemap freshness/stale verdict, the artefact
tabs, the manuscript-dir fence, and the honest rebuild-failure surface.

Pure-logic tests over synthetic manuscript trees (the internal functions take a
Path directly, so no repo fence is involved); the route-level handle() tests read
the live corpus read-only. No browser, no LaTeX - the live render is the smoke.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from laplace.manuscript import review_surface as rv
from laplace.web import review_http
from laplace.pipeline import nodemap as nm

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# fixtures — a synthetic manuscript tree
# ---------------------------------------------------------------------------

def _make(tmp_path, *, nodemap=None, feedback=None, round_data=None,
          main_pdf=True, incumbent=False, main_tex=True):
    md = tmp_path / "wp"
    md.mkdir()
    if main_tex:
        (md / "main.tex").write_text(
            "\\documentclass{article}\\begin{document}x\\end{document}",
            encoding="utf-8")
    if main_pdf:
        (md / "main.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    if nodemap is not None:
        (md / "main.nodemap.json").write_text(json.dumps(nodemap), encoding="utf-8")
    if feedback is not None:
        (md / "feedback").mkdir()
        (md / "feedback" / "feedback.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in feedback), encoding="utf-8")
    if round_data is not None:
        jr = md / "judge_rounds"
        jr.mkdir()
        (jr / "2026-07-10_round1.json").write_text(json.dumps(round_data),
                                                   encoding="utf-8")
    if incumbent:
        inc = md / "rounds" / "incumbent_r1"
        inc.mkdir(parents=True)
        (inc / "main.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
        (inc / "SNAPSHOT.json").write_text(json.dumps({"round": 1, "ts": "t"}),
                                           encoding="utf-8")
    return md


def _nodemap(fingerprint="sha256:bogus"):
    return {
        "source_fingerprint": fingerprint,
        "entries": {
            "def:a": [{"page": 2, "x0": 54.0, "y0": 90.0, "x1": 558.0, "y1": 400.0,
                       "kind": "float", "width": "inferred"}],
            "N1-p1": [{"page": 1, "x0": 54.0, "y0": 500.0, "x1": 300.0, "y1": 500.0,
                       "kind": "paragraph", "width": "inferred"}],
        },
        "coverage": {"floats": {"mapped": 1, "total": 1, "pct": 100.0},
                     "overall": {"mapped": 2, "total": 3, "pct": 66.7},
                     "roster_only": 1},
        "unmapped": [{"node_id": "irf:orphan", "kind": "roster", "reason": "roster-only"}],
    }


# ---------------------------------------------------------------------------
# node extraction from a judge flag's `where`
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("where,expect", [
    ("Acquisition and the finite-record envelope", []),
    ("spectral_surface_generation:def:filtered-mean", ["def:filtered-mean"]),
    ("def:spectral-surface, res:one-sided-reconstruction",
     ["def:spectral-surface", "res:one-sided-reconstruction"]),
    ("relation_to_itqde:huang2020predicting", []),          # citation, not a node
    ("app:NA1", []),                                          # appendix ref, not a node
    ("", []),
])
def test_nodes_in_where(where, expect):
    assert rv._nodes_in_where(where) == sorted(expect)


# ---------------------------------------------------------------------------
# class badging — deferred (dials) precedence, then hard, then soft
# ---------------------------------------------------------------------------

def test_classify_precedence():
    defer = {"eq-unused", "citation-uncited"}
    # deferred wins even over a hard panel / hard kind
    assert rv._classify("eq-unused", "apparatus", defer) == "deferred"
    assert rv._classify("citation-uncited", None, defer) == "deferred"
    # a hard kind or a hard panel → hard
    assert rv._classify("missing-derivation", None, defer) == "hard"
    assert rv._classify("caption-scaffold", "meta_leak", defer) == "hard"
    # everything else → soft
    assert rv._classify("caption-scaffold", "caption", defer) == "soft"
    assert rv._classify("note", None, defer) == "soft"


# ---------------------------------------------------------------------------
# findings — grouped by node, anchored vs unanchored, badged
# ---------------------------------------------------------------------------

def test_findings_group_anchor_and_flag_unanchored(tmp_path):
    md = _make(
        tmp_path,
        nodemap=_nodemap(),
        feedback=[
            {"id": "FB-1", "node_id": "def:a", "kind": "note",
             "anchor": {"section": "S1", "quote": "q"}, "comment": "c1",
             "by": "gerard", "status": "open"},
            {"id": "FB-2", "node_id": "A whole section title", "kind": "legacy-notation",
             "anchor": {}, "comment": "section-level", "by": "judge-panel",
             "status": "open"},
        ],
        round_data={
            "round": 1, "date": "2026-07-10",
            "panel": [
                {"label": "meta_leak", "clean": False, "flags": [
                    {"where": "sec:def:a", "issue": "leak", "kind": "legacy-notation"}]},
                {"label": "apparatus", "clean": False, "flags": [
                    {"where": "introduction", "issue": "unused", "kind": "eq-unused"}]},
            ],
            "hard_failing": True, "lock_eligible": False,
            "drift": {"skipped": True, "notes": "no incumbent yet"},
        },
    )
    out = rv.findings(md, "smoke")

    # def:a anchored (in the map): carries the feedback note + the meta_leak flag
    anchored = {g["node"]: g for g in out["by_node"]}
    assert "def:a" in anchored
    g = anchored["def:a"]
    assert g["anchored"] is True and g["page"] == 2
    assert len(g["findings"]) == 2

    # the section-title feedback + the section-level eq-unused flag are unanchored
    un_nodes = {(f.get("node"), f["kind"]) for f in out["unanchored"]}
    assert (None, "legacy-notation") in un_nodes         # FB-2 (section-title node_id → node None)
    assert (None, "eq-unused") in un_nodes

    # eq-unused is a dials defer_kind (dials-h) → deferred, reported not hidden
    assert "eq-unused" in out["defer_kinds"]
    assert out["counts"]["deferred"] >= 1
    assert out["counts"]["total"] == 4
    assert out["round"]["hard_failing"] is True
    assert out["round"]["drift"]["skipped"] is True


def test_findings_without_map_all_unanchored(tmp_path):
    md = _make(tmp_path, feedback=[
        {"id": "F", "node_id": "def:a", "kind": "note", "anchor": {}, "comment": "c"}])
    out = rv.findings(md, "smoke")
    assert out["by_node"] == []                          # nothing anchors without a map
    assert out["counts"]["n_unanchored"] == 1
    assert out["map_present"] is False


# ---------------------------------------------------------------------------
# the harnessed round layout (rounds/harnessed/mech_r*.json) + integer ordering
# ---------------------------------------------------------------------------

def _mech(md: Path, rnd: int, panels):
    h = md / "rounds" / "harnessed"
    h.mkdir(parents=True, exist_ok=True)
    (h / f"mech_r{rnd}.json").write_text(json.dumps({
        "round": rnd, "date": "2026-07-11",
        "panel": [{"label": lab, "clean": clean, "flags": flags}
                  for lab, clean, flags in panels],
    }), encoding="utf-8")


def test_round_findings_reads_harnessed_mech_layout(tmp_path):
    md = tmp_path / "wp"
    md.mkdir()
    _mech(md, 1, [("apparatus", False,
                   [{"where": "sec:def:a", "issue": "leak", "kind": "citation-uncited"}])])
    summary, findings = rv._round_findings(md)
    assert summary is not None and summary["round"] == 1     # harnessed layout is found
    assert any(f["kind"] == "citation-uncited" for f in findings)


def test_round_findings_newest_by_integer_not_lexical(tmp_path):
    md = tmp_path / "wp"
    md.mkdir()
    _mech(md, 2, [("apparatus", False,
                   [{"where": "sec:x", "issue": "old", "kind": "old-kind"}])])
    _mech(md, 10, [("apparatus", False,
                    [{"where": "sec:y", "issue": "new", "kind": "new-kind"}])])
    summary, findings = rv._round_findings(md)
    assert summary["round"] == 10                            # r10 beats r2, not lexical
    assert {f["kind"] for f in findings} == {"new-kind"}


# ---------------------------------------------------------------------------
# the nodemap freshness / stale verdict (ruling 4)
# ---------------------------------------------------------------------------

def test_nodemap_absent_is_stale(tmp_path):
    md = _make(tmp_path)
    st = rv.nodemap_state(md)
    assert st["present"] is False and st["fresh"] is False
    assert "no instrumented map" in st["stale_reason"]


def test_nodemap_stale_on_fingerprint_mismatch(tmp_path):
    md = _make(tmp_path, nodemap=_nodemap("sha256:OLD"))
    st = rv.nodemap_state(md)
    assert st["present"] is True and st["fresh"] is False
    assert "older source tree" in st["stale_reason"]
    assert "def:a" in st["entries"]                      # entries still served (best-available)


def test_nodemap_fresh_when_fingerprint_matches(tmp_path):
    md = _make(tmp_path, nodemap=_nodemap("placeholder"))
    fp = nm.source_fingerprint(md)                       # the real fingerprint of this tree
    (md / "main.nodemap.json").write_text(
        json.dumps({**_nodemap(fp)}), encoding="utf-8")
    st = rv.nodemap_state(md)
    assert st["fresh"] is True
    assert st.get("stale_reason") is None


# ---------------------------------------------------------------------------
# the artefact tabs
# ---------------------------------------------------------------------------

def test_artefacts_candidate_only(tmp_path):
    md = _make(tmp_path)
    art = rv.artefacts(md)
    assert art["candidate"]["name"] == "main.pdf"
    assert art["clean"] is None                          # no finalize product → no clean tab
    assert art["incumbent"] is None
    assert art["release_state"] == "STAGED"


def test_artefacts_incumbent_present(tmp_path):
    md = _make(tmp_path, incumbent=True)
    art = rv.artefacts(md)
    assert art["incumbent"]["round"] == 1
    assert art["incumbent"]["pdf"].endswith("rounds/incumbent_r1/main.pdf")


# ---------------------------------------------------------------------------
# the manuscript-dir fence
# ---------------------------------------------------------------------------

def test_manuscript_dir_fence(tmp_path,monkeypatch):
    monkeypatch.setattr(rv,'_repo_root',lambda:tmp_path)
    md=tmp_path/'project/whitepaper';md.mkdir(parents=True)
    (md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nFixture prose words.\n\\end{document}\n')
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'fixture','project_dir':'project','tex_root':'project/whitepaper'}]}))
    # an absolute path outside the repo is refused
    assert rv.manuscript_dir(dir_param="/tmp") is None
    # a traversal shape is refused
    assert rv.manuscript_dir(dir_param="../../etc") is None
    # an unknown corpus is None (never touches disk)
    assert rv.manuscript_dir("no-such-corpus-xyz") is None
    # a real corpus resolves to its target_dir inside the repo
    md = rv.manuscript_dir("fixture")
    assert md is not None and md.is_dir() and md.name == "whitepaper"


def test_manuscript_dir_planless_registry_fallback(tmp_path,monkeypatch):
    monkeypatch.setattr(rv,'_repo_root',lambda:tmp_path)
    md=tmp_path/'foreign/manuscript';md.mkdir(parents=True)
    (md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nForeign fixture words.\n\\end{document}\n')
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'foreign','kind':'project','project_dir':'foreign'}]}))
    # a plan-less project (foreign artefact) falls back to the registry's
    # manuscript_dir so the deposit door works without a projection_plan.json
    md = rv.manuscript_dir("foreign")
    assert md is not None and md.is_dir() and md.name == "manuscript"


# ---------------------------------------------------------------------------
# the honest rebuild-failure surface (ruling 4: no silent degrade)
# ---------------------------------------------------------------------------

def test_rebuild_surfaces_layout_drift(tmp_path, monkeypatch):
    md = _make(tmp_path)

    def _raise(*a, **k):
        raise nm.LayoutDriftError("instrumented build drifted", {"notes": "2 page(s) moved"})
    monkeypatch.setattr(nm, "build_nodemap", _raise)
    res = rv.rebuild(md)
    assert res["ok"] is False and res["kind"] == "LayoutDriftError"
    assert res["drift"]["notes"] == "2 page(s) moved"


def test_rebuild_success_returns_coverage(tmp_path, monkeypatch):
    md = _make(tmp_path)
    monkeypatch.setattr(nm, "build_nodemap",
                        lambda *a, **k: {"coverage": {"overall": {"pct": 91.0}},
                                         "gate": {"ok": True}, "page_count": 3,
                                         "built": "t", "unmapped": []})
    res = rv.rebuild(md)
    assert res["ok"] is True and res["coverage"]["overall"]["pct"] == 91.0


# ---------------------------------------------------------------------------
# routing (handle) — HTML, the data routes on the live corpus, error paths
# ---------------------------------------------------------------------------

def test_handle_serves_the_consolidation_notice():
    # W2: the review PAGE folded into /artefact's annotate mode (the scanner 301-redirects the
    # bare route); the data handler names where it went, never serving the deleted HTML.
    st, ctype, body = review_http.handle("/review", {}, "GET", b"")
    assert st == 200 and "json" in ctype
    assert json.loads(body)["consolidated_into"] == "/artefact"


def test_handle_unknown_route_404():
    st, _, _ = review_http.handle("/review/nope", {}, "GET", b"")
    assert st == 404


def test_handle_not_ours_returns_none():
    assert review_http.handle("/storyboard", {}, "GET", b"") is None


def test_handle_findings_live_corpus():
    st, ctype, body = review_http.handle("/review/findings",
                                {"corpus": ["subset-sum-itqde"]}, "GET", b"")
    assert st == 200
    data = json.loads(body)
    assert "by_node" in data and "unanchored" in data and "counts" in data
    assert set(data["counts"]) >= {"hard", "soft", "deferred", "total"}


def test_handle_bad_corpus_404():
    st, _, _ = review_http.handle("/review/artefacts", {"corpus": ["no-such"]}, "GET", b"")
    assert st == 404


# ---------------------------------------------------------------------------
# G-3 ADJUDICATION verbs — exact ledger records, idempotency, restyle, meta-signal
# ---------------------------------------------------------------------------

from laplace.pipeline import suppress as _sup            # noqa: E402
from laplace.pipeline.ledger import read_jsonl           # noqa: E402


def _sectioned(tmp_path, feedback=None, s1="Original body of section one.\n"):
    """A manuscript whose main.tex \\inputs S1.tex, so 'S1' resolves in the node-text
    map (a real fingerprint, not the empty-string fallback)."""
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
    return read_jsonl(md / "feedback" / "feedback.jsonl")


def _un(board, fid):
    return next(f for f in board["unanchored"] if f["id"] == fid)


def test_node_text_map_resolves_input_section(tmp_path):
    md = _sectioned(tmp_path)
    assert "S1" in rv._node_text_map(md)                 # the shared route resolver


def test_adjudicate_confirm_record_and_restyle(tmp_path):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-1", "node_id": "S1", "kind": "eq-unused", "anchor": {}, "comment": "c"}])
    res = rv.adjudicate(md, "smoke", {"by": "author", "verb": "confirm", "finding_id": "FB-1",
                                      "node": "S1", "kind": "eq-unused", "round": 2})
    rec = res["record"]
    assert res["ok"] and rec["record"] == "confirmation"
    assert rec["target"] == "FB-1" and rec["status"] == "open"
    assert rec["provenance"] == {"actor": "author", "verdict": "confirmed",
                                 "round": 2, "ts": rec["ts"]}
    assert _un(rv.findings(md, "smoke"), "FB-1")["adjudication"]["state"] == "confirmed"
    # idempotent: a second confirm appends nothing
    n0 = len(_ledger(md))
    assert rv.adjudicate(md, "smoke", {"by": "author", "verb": "confirm",
                                       "finding_id": "FB-1"}).get("idempotent") is True
    assert len(_ledger(md)) == n0


def test_adjudicate_dismiss_fingerprint_idempotent_and_stale(tmp_path):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-1", "node_id": "S1", "kind": "caption-scaffold", "anchor": {},
         "comment": "c"}])
    res = rv.adjudicate(md, "smoke", {"by": "author", "verb": "dismiss", "node": "S1",
                                      "kind": "caption-scaffold", "reason": "not a fault"})
    rec = res["record"]
    assert rec["record"] == "suppression" and rec["kind"] == "caption-scaffold"
    assert rec["node_id"] == "S1"
    assert rec["fingerprint"] == _sup.content_fingerprint(rv._node_text_map(md)["S1"])
    assert rec["provenance"]["reason"] == "not a fault"
    dj = _un(rv.findings(md, "smoke"), "FB-1")["adjudication"]
    assert dj["state"] == "dismissed" and dj["suppression_id"] == rec["id"]
    # idempotent (same fingerprint) → no new record
    n0 = len(_ledger(md))
    assert rv.adjudicate(md, "smoke", {"by": "author", "verb": "dismiss", "node": "S1",
                                       "kind": "caption-scaffold"}).get("idempotent") is True
    assert len(_ledger(md)) == n0
    # MUTATE S1 materially → the suppression goes STALE → the finding is REBORN
    (md / "S1.tex").write_text("A completely different body now.\n", encoding="utf-8")
    assert _un(rv.findings(md, "smoke"), "FB-1")["adjudication"]["state"] == "reborn"


def test_adjudicate_defer_record_and_restyle(tmp_path):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-1", "node_id": "S1", "kind": "note", "anchor": {}, "comment": "c"}])
    rec = rv.adjudicate(md, "smoke", {"by": "author", "verb": "defer", "finding_id": "FB-1",
                                      "note": "later"})["record"]
    assert rec["record"] == "defer" and rec["status"] == "deferred"
    assert rec["target"] == "FB-1"
    assert _un(rv.findings(md, "smoke"), "FB-1")["adjudication"]["state"] == "deferred"


def test_adjudicate_widen_scope_and_revoke_roundtrip(tmp_path):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-1", "node_id": "S1", "kind": "note", "anchor": {}, "comment": "a"},
        {"id": "FB-2", "node_id": "S1", "kind": "off-voice", "anchor": {}, "comment": "b"}])
    res = rv.adjudicate(md, "smoke", {"by": "author", "verb": "widen", "node": "S1"})
    assert res["ok"] and res["record"]["kind"] == "*"
    assert res["scope_count"] == 2                        # both open findings on S1
    board = rv.findings(md, "smoke")
    assert {f["id"]: f["adjudication"]["state"] for f in board["unanchored"]} == \
        {"FB-1": "dismissed", "FB-2": "dismissed"}
    assert all(f["adjudication"]["widen"] for f in board["unanchored"])
    # REVOKE the wildcard → both findings return to live (load_suppressions drops it)
    supp_id = res["record"]["id"]
    assert rv.adjudicate(md, "smoke", {"by": "author", "verb": "revoke", "supersedes": supp_id})["ok"]
    assert all(f["adjudication"] is None
               for f in rv.findings(md, "smoke")["unanchored"])
    # revoke again → idempotent no-op
    assert rv.adjudicate(md, "smoke",
                         {"by": "author", "verb": "revoke", "supersedes": supp_id}).get("idempotent") is True


def test_adjudicate_route_conceptric_queues_typed_intent(tmp_path):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-1", "node_id": "S1", "kind": "note", "anchor": {}, "comment": "c"}])
    rec = rv.adjudicate(md, "smoke", {"by": "author", "verb": "route-conceptric", "node": "def:x",
                                      "intent": "essence-wrong", "note": "wrong essence",
                                      "finding_id": "FB-1"})["record"]
    assert rec["record"] == "conceptric-intent" and rec["kind"] == "conceptric-intent"
    assert rec["intent"] == "essence-wrong" and rec["node"] == "def:x"
    assert rec["payload"] == {"intent": "essence-wrong", "note": "wrong essence",
                              "finding_kind": ""}
    assert rec["status"] == "open"                       # queued, never executed
    fj = _un(rv.findings(md, "smoke"), "FB-1")["adjudication"]
    assert fj["state"] == "routed" and fj["intent"] == "essence-wrong"
    # unknown intent normalises to 'other'
    o = rv.adjudicate(md, "smoke", {"by": "author", "verb": "route-conceptric", "node": "def:y",
                                    "intent": "nonsense"})["record"]
    assert o["intent"] == "other"
    # idempotent (same node + intent)
    assert rv.adjudicate(md, "smoke", {"by": "author", "verb": "route-conceptric", "node": "def:x",
                                       "intent": "essence-wrong",
                                       "finding_id": "FB-1"}).get("idempotent") is True


def test_meta_signal_threshold_and_calibrate(tmp_path):
    # five ACTIVE dismissals of the SAME kind (five nodes) → the meta-signal fires
    supps = [_sup.make_suppression(f"S{i}", "caption-scaffold", "body", reason="",
                                   actor="author", round=1, rec_id=f"SUP-{i}")
             for i in range(5)]
    md = _sectioned(tmp_path, feedback=supps)
    sig = [m for m in rv.findings(md, "smoke")["meta_signals"]
           if m["kind"] == "caption-scaffold"]
    assert sig and sig[0]["count"] == 5 and sig[0]["threshold"] == 5
    assert sig[0]["deposited"] is False
    # queue recalibration → a kind-level calibration-intent
    rec = rv.adjudicate(md, "smoke",
                        {"by": "author", "verb": "calibrate", "finding_kind": "caption-scaffold"})["record"]
    assert rec["record"] == "calibration-intent" and rec["finding_kind"] == "caption-scaffold"
    assert rec["payload"]["dismissal_count"] == 5
    sig2 = [m for m in rv.findings(md, "smoke")["meta_signals"]
            if m["kind"] == "caption-scaffold"]
    assert sig2[0]["deposited"] is True                  # now shows 'queued'
    assert rv.adjudicate(md, "smoke",
                         {"by": "author", "verb": "calibrate",
                          "finding_kind": "caption-scaffold"}).get("idempotent") is True


def test_adjudicate_below_threshold_no_meta_signal(tmp_path):
    supps = [_sup.make_suppression(f"S{i}", "off-voice", "body", reason="",
                                   actor="author", round=1, rec_id=f"SO-{i}")
             for i in range(4)]                          # 4 < the default threshold 5
    md = _sectioned(tmp_path, feedback=supps)
    assert rv.findings(md, "smoke")["meta_signals"] == []


def test_adjudicate_validation_errors(tmp_path):
    md = _sectioned(tmp_path)
    assert "error" in rv.adjudicate(md, "smoke", {"by": "author", "verb": "confirm"})       # no finding_id
    assert "error" in rv.adjudicate(md, "smoke", {"by": "author", "verb": "dismiss", "node": "S1"})  # no kind
    assert "error" in rv.adjudicate(md, "smoke", {"by": "author", "verb": "bogus"})         # unknown verb


# --- the POST plumbing through handle() (error paths; no live-tree mutation) ---

def test_handle_adjudicate_bad_json_400():
    st, _, _ = review_http.handle("/review/adjudicate", {}, "POST", b"{not json")
    assert st == 400


def test_handle_adjudicate_unknown_corpus_404():
    body = json.dumps({"verb": "confirm", "corpus": "no-such-xyz"}).encode()
    st, _, _ = review_http.handle("/review/adjudicate", {}, "POST", body)
    assert st == 404


def test_handle_adjudicate_unknown_verb_422():
    # a valid corpus resolves read-only; 'bogus' errors BEFORE any ledger write
    body = json.dumps({"verb": "bogus", "corpus": "subset-sum-itqde"}).encode()
    st, _, resp = review_http.handle("/review/adjudicate", {}, "POST", body)
    assert st == 422
    assert "unknown adjudication verb" in json.loads(resp)["error"]


# ---------------------------------------------------------------------------
# G-4 — the tower joins: provenance (minting trace), substrate queue, board link
# ---------------------------------------------------------------------------

def _friction(tmp_path, corpus, records):
    """A fixture friction ledger under a tmp corpus_friction/ dir."""
    fd = tmp_path / "corpus_friction"
    fd.mkdir(exist_ok=True)
    (fd / f"{corpus}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return fd


def test_provenance_filters_by_node_newest_first(tmp_path):
    recs = [
        {"id": "RW-1", "ts": "2026-06-30T10:00:00", "kind": "add-node", "node": "def:x",
         "node_kind": "definition", "essence": "the essence of x", "by": "gerard"},
        {"id": "RW-2", "ts": "2026-06-30T11:00:00", "kind": "add-edge", "node": "def:x",
         "target": "def:y", "by": "eigen"},
        {"id": "RW-3", "ts": "2026-07-01T09:00:00", "kind": "edit-essence", "node": "def:x",
         "value": "a sharper essence", "by": "gerard"},
        {"id": "RW-9", "ts": "2026-07-02T09:00:00", "kind": "add-node", "node": "res:other",
         "node_kind": "result", "essence": "not x", "by": "gerard"},
        {"id": "TX-1", "ts": "2026-07-03T00:00:00", "kind": "txn", "by": "hygiene"},   # non-op
    ]
    fd = _friction(tmp_path, "smoke-corpus", recs)
    p = rv.provenance("smoke-corpus", "def:x", friction_dir=fd)
    assert p["present"] and p["count"] == 3
    assert [h["id"] for h in p["history"]] == ["RW-3", "RW-2", "RW-1"]     # newest first
    assert p["history"][0]["kind"] == "edit-essence"
    assert "re-essenced" in p["history"][0]["summary"]
    assert "def:y" in p["history"][1]["summary"]                          # + edge → def:y
    assert "minted" in p["history"][2]["summary"] and "definition" in p["history"][2]["summary"]
    # an unregistered corpus has no net → upstream absent, but the trace still lands
    assert p["upstream"] is None and p["in_conceptric"] is False


def test_provenance_absent_ledger_and_no_corpus(tmp_path):
    fd = tmp_path / "corpus_friction"
    fd.mkdir()
    p = rv.provenance("nope", "def:x", friction_dir=fd)
    assert p["present"] is False and p["count"] == 0 and "no friction ledger" in p["reason"]
    q = rv.provenance("", "def:x", friction_dir=fd)
    assert q["present"] is False and "no corpus" in q["reason"]


def test_provenance_path_fence(tmp_path):
    fd = tmp_path / "corpus_friction"
    fd.mkdir()
    (fd.parent / "secret.jsonl").write_text("{}\n", encoding="utf-8")
    assert rv._friction_path("../secret", friction_dir=fd) is None       # cannot climb out


def test_substrate_queue_lists_open_intents_and_revoke(tmp_path):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-1", "node_id": "def:x", "kind": "naked-claim", "anchor": {}, "comment": "c"}])
    ci = rv.adjudicate(md, "smoke", {"by": "author", "verb": "route-conceptric", "node": "def:x",
                                     "intent": "essence-wrong", "note": "the essence is off",
                                     "finding_id": "FB-1", "kind": "naked-claim"})["record"]
    rv.adjudicate(md, "smoke", {"by": "author", "verb": "calibrate", "finding_kind": "naked-claim",
                                "note": "too trigger-happy"})
    q = rv.substrate_queue(md)
    assert q["count"] == 2
    assert {it["kind"] for it in q["queue"]} == {"conceptric-intent", "calibration-intent"}
    cint = next(it for it in q["queue"] if it["kind"] == "conceptric-intent")
    assert cint["node"] == "def:x" and cint["intent"] == "essence-wrong"
    assert cint["note"] == "the essence is off"
    calit = next(it for it in q["queue"] if it["kind"] == "calibration-intent")
    assert calit["finding_kind"] == "naked-claim"
    # revoke the conceptric intent → it drops (append-only supersede, mirroring G-3)
    r = rv.adjudicate(md, "smoke", {"by": "author", "verb": "revoke-intent", "supersedes": ci["id"]})
    assert r["ok"] and r["record"]["record"] == "intent-revoke"
    q2 = rv.substrate_queue(md)
    assert q2["count"] == 1 and q2["queue"][0]["kind"] == "calibration-intent"
    # unknown / already-revoked id → idempotent no-op (never a second revoke)
    again = rv.adjudicate(md, "smoke", {"by": "author", "verb": "revoke-intent", "supersedes": ci["id"]})
    assert again["ok"] and again.get("idempotent") is True
    # the revoke-intent record is an ACTION, never itself a finding on the board
    assert not any(f["id"] == r["record"]["id"]
                   for f in rv.findings(md, "smoke")["unanchored"])


def test_revoke_intent_requires_id(tmp_path):
    md = _sectioned(tmp_path, feedback=[])
    assert "error" in rv.adjudicate(md, "smoke", {"by": "author", "verb": "revoke-intent"})


def test_revoke_intent_retires_projection_intent(tmp_path):
    # C3.6: revoke-intent extends to PROJECTION_INTENT so a projection intent can be
    # retired from the surface — the AUTHOR's door to the retire the C3.5 apply path
    # writes programmatically. open_projection_intents stops being monotonic.
    from laplace.pipeline import evolution_consumer as _ec
    from laplace.pipeline.ledger import read_jsonl as _read
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-9", "node_id": "def:x", "kind": "whole-artefact", "anchor": {}, "comment": "c"}])
    pi = rv.adjudicate(md, "smoke", {"by": "author", "verb": "route-plan",
                                     "finding_id": "FB-9", "plan_verb": "CUT",
                                     "object": {"kind": "section", "key": "S3"},
                                     "note": "cut this section"})["record"]
    ledger = md / "feedback" / "feedback.jsonl"
    assert pi["id"] in {r["id"] for r in _ec.open_projection_intents(_read(ledger))}
    assert pi["id"] in {it["id"] for it in rv.substrate_queue(md)["queue"]}
    # revoke it → open_projection_intents no longer lists it, and the queued deposit
    # leaves the surface too (the open queue stops being monotonic)
    r = rv.adjudicate(md, "smoke", {"by": "author", "verb": "revoke-intent",
                                    "supersedes": pi["id"]})
    assert r["ok"] and r["record"]["record"] == "intent-revoke"
    assert pi["id"] not in {r2["id"] for r2 in _ec.open_projection_intents(_read(ledger))}
    assert pi["id"] not in {it["id"] for it in rv.substrate_queue(md)["queue"]}
    # already-revoked → idempotent no-op
    again = rv.adjudicate(md, "smoke", {"by": "author", "verb": "revoke-intent",
                                        "supersedes": pi["id"]})
    assert again["ok"] and again.get("idempotent") is True


def test_revoke_intent_unattributed_is_refused(tmp_path, monkeypatch):
    # the actor guard stays: an unattributed revoke never mints a verdict (422 at
    # the route, error-before-persist in the executor — the intent stays OPEN).
    from laplace.pipeline import evolution_consumer as _ec
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-9", "node_id": "def:x", "kind": "whole-artefact", "anchor": {}, "comment": "c"}])
    pi = rv.adjudicate(md, "smoke", {"by": "author", "verb": "route-plan",
                                     "finding_id": "FB-9", "plan_verb": "CUT",
                                     "object": {"kind": "section", "key": "S3"}})["record"]
    res = rv.adjudicate(md, "smoke", {"verb": "revoke-intent", "supersedes": pi["id"]})
    assert "error" in res and "by" in res["error"]
    # ... and the same refusal reaches the wire as 422, with the intent still open
    monkeypatch.setattr(rv, "manuscript_dir", lambda *a, **k: md)
    st, _, body = review_http.handle("/review/adjudicate", {}, "POST", json.dumps(
        {"corpus": "smoke", "verb": "revoke-intent", "supersedes": pi["id"]}).encode())
    assert st == 422 and "by" in json.loads(body)["error"]
    assert pi["id"] in {r["id"] for r in _ec.open_projection_intents(_ledger(md))}


def test_revoke_intent_retires_calibration_intent(tmp_path):
    # C3.6 extends the filter; it must not narrow it — the calibration kind (the
    # one the older tests never revoked) still retires through the same door.
    md = _sectioned(tmp_path, feedback=[])
    ci = rv.adjudicate(md, "smoke", {"by": "author", "verb": "calibrate",
                                     "finding_kind": "naked-claim",
                                     "note": "too trigger-happy"})["record"]
    assert rv.substrate_queue(md)["count"] == 1
    r = rv.adjudicate(md, "smoke", {"by": "author", "verb": "revoke-intent",
                                    "supersedes": ci["id"]})
    assert r["ok"] and r["record"]["record"] == "intent-revoke"
    assert rv.substrate_queue(md)["count"] == 0


def test_storyboard_focus_url():
    assert rv.storyboard_focus_url("subset-sum-itqde", "def:hamiltonian") == \
        "/storyboard?corpus=subset-sum-itqde&focus=def%3Ahamiltonian"
    assert rv.storyboard_focus_url("subset-sum-itqde", "") == "/storyboard?corpus=subset-sum-itqde"
    assert rv.storyboard_focus_url("", "def:x") == ""            # no corpus → no board address


def test_handle_provenance_requires_node():
    st, _, _ = review_http.handle("/review/provenance", {"corpus": ["c"]}, "GET", b"")
    assert st == 400


def test_handle_provenance_returns_200_even_without_a_ledger():
    st, _, body = review_http.handle("/review/provenance",
                            {"corpus": ["no-such-corpus-xyz"], "node": ["def:x"]}, "GET", b"")
    j = json.loads(body)
    assert st == 200 and j["node"] == "def:x" and j["present"] is False


def test_handle_substrate_route(tmp_path, monkeypatch):
    md = _sectioned(tmp_path, feedback=[])
    monkeypatch.setattr(rv, "manuscript_dir", lambda corpus="", dir_param="": md)
    st, _, body = review_http.handle("/review/substrate", {"dir": ["wp"]}, "GET", b"")
    assert st == 200 and json.loads(body)["queue"] == []


# ---------------------------------------------------------------------------
# B13.7 — the DISMISSAL AUDIT, stratified by (kind, fingerprint), and its
# agree (calibrate) / overrule (revoke) rulings through the EXISTING verbs
# ---------------------------------------------------------------------------

def test_dismissal_audit_stratifies_by_kind_and_fingerprint(tmp_path):
    # three dismissals: two of the same kind on IDENTICAL content (one class,
    # count 2) and one of the same kind on DIFFERENT content (a second class).
    supps = [
        _sup.make_suppression("def:a", "eq-unused", "shared body", reason="r1",
                              actor="machine", round=1, rec_id="SUP-A"),
        _sup.make_suppression("def:b", "eq-unused", "shared body", reason="r1",
                              actor="machine", round=1, rec_id="SUP-B"),
        _sup.make_suppression("def:c", "eq-unused", "a different body", reason="r2",
                              actor="machine", round=1, rec_id="SUP-C"),
    ]
    md = _sectioned(tmp_path, feedback=supps)
    aud = rv.dismissal_audit(md)
    assert aud["counts"] == {"classes": 2, "dismissals": 3, "stale": 0,
                             "machine": 3, "author": 0}
    # the two identical-content dismissals collapse into one class (count 2)
    big = next(r for r in aud["rows"] if r["count"] == 2)
    assert big["kind"] == "eq-unused"
    assert {n["node"] for n in big["nodes"]} == {"def:a", "def:b"}
    assert set(big["suppression_ids"]) == {"SUP-A", "SUP-B"}
    assert big["source"] == "machine" and big["widen"] is False
    # the two classes carry different fingerprints (the stratification key)
    assert len({r["fingerprint"] for r in aud["rows"]}) == 2
    # rows are biggest-class-first (the systemic dismissals on top)
    assert aud["rows"][0]["count"] == 2


def test_dismissal_audit_flags_deferred_calibrated_and_stale(tmp_path):
    # a dismissal on the resolvable section S1 (so its fingerprint can go stale),
    # of a kind that is BOTH a dials defer_kind AND already calibration-queued.
    md = _sectioned(tmp_path, s1="Original body of section one.\n", feedback=[
        _sup.make_suppression("S1", "eq-unused",
                              "Original body of section one.\n", reason="dup label",
                              actor="machine", round=1, rec_id="SUP-S1")])
    rv.adjudicate(md, "smoke", {"by": "author", "verb": "calibrate", "finding_kind": "eq-unused"})
    aud = rv.dismissal_audit(md)
    row = next(r for r in aud["rows"] if r["kind"] == "eq-unused")
    assert row["deferred"] is True                       # eq-unused ∈ dials-h defer_kinds
    assert row["calibrated"] is True                     # a calibration-intent exists
    assert row["stale"] is False and row["reason"] == "dup label"
    # MUTATE S1 materially → the dismissed content no longer matches → STALE
    (md / "S1.tex").write_text("A completely different body now.\n", encoding="utf-8")
    aud2 = rv.dismissal_audit(md)
    row2 = next(r for r in aud2["rows"] if r["kind"] == "eq-unused")
    assert row2["stale"] is True and aud2["counts"]["stale"] == 1


def test_dismissal_audit_widen_class_has_no_kind(tmp_path):
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-1", "node_id": "S1", "kind": "note", "anchor": {}, "comment": "a"}])
    rv.adjudicate(md, "smoke", {"by": "author", "verb": "widen", "node": "S1"})   # a WILDCARD silence
    aud = rv.dismissal_audit(md)
    wrow = next(r for r in aud["rows"] if r["kind"] == "*")
    assert wrow["widen"] is True


def test_audit_agree_calibrate_and_overrule_revoke_roundtrip(tmp_path):
    # the row-level rulings map onto the EXISTING verbs, banked through the one door.
    md = _sectioned(tmp_path, s1="Body one.\n", feedback=[
        {"id": "FB-1", "node_id": "S1", "kind": "eq-unused", "anchor": {}, "comment": "c"}])
    # a machine dismissal of FB-1's (node, kind) → the audit shows one class
    dm = rv.adjudicate(md, "smoke", {"by": "author", "verb": "dismiss", "node": "S1",
                                     "kind": "eq-unused", "reason": "referenced"})["record"]
    assert _un(rv.findings(md, "smoke"), "FB-1")["adjudication"]["state"] == "dismissed"
    row = next(r for r in rv.dismissal_audit(md)["rows"] if r["kind"] == "eq-unused")
    assert dm["id"] in row["suppression_ids"]

    # AGREE → calibrate the kind (affirm the class); a calibration-intent lands
    ag = rv.adjudicate(md, "smoke", {"by": "author", "verb": "calibrate", "finding_kind": "eq-unused"})
    assert ag["ok"] and ag["record"]["record"] == "calibration-intent"
    assert "eq-unused" in rv.dismissal_audit(md)["calibrated_kinds"]

    # OVERRULE → revoke the class's suppression; the finding is REBORN live
    ov = rv.adjudicate(md, "smoke", {"by": "author", "verb": "revoke",
                                     "supersedes": row["suppression_ids"][0]})
    assert ov["ok"] and ov["record"]["record"] == "suppression-revoke"
    assert _un(rv.findings(md, "smoke"), "FB-1")["adjudication"] is None   # back to live
    # the revoked suppression drops out of the audit entirely
    assert not any(dm["id"] in r["suppression_ids"]
                   for r in rv.dismissal_audit(md)["rows"])


def test_handle_dismissals_route(tmp_path, monkeypatch):
    md = _sectioned(tmp_path, feedback=[
        _sup.make_suppression("def:a", "eq-unused", "b", reason="", actor="machine",
                              round=1, rec_id="SUP-A")])
    monkeypatch.setattr(rv, "manuscript_dir", lambda corpus="", dir_param="": md)
    st, ct, body = review_http.handle("/review/dismissals", {"dir": ["wp"]}, "GET", b"")
    j = json.loads(body)
    assert st == 200 and "application/json" in ct
    assert j["counts"]["classes"] == 1 and j["rows"][0]["kind"] == "eq-unused"
    # unknown corpus / dir → 404
    monkeypatch.setattr(rv, "manuscript_dir", lambda corpus="", dir_param="": None)
    st2, _, _ = review_http.handle("/review/dismissals", {"corpus": ["nope"]}, "GET", b"")
    assert st2 == 404


def test_handle_dismissals_live_corpus():
    # read-only against the live corpus: the audit resolves and the seven accepted
    # deferred classes surface (the machine's SSG dismissals are stratified here).
    st, _, body = review_http.handle("/review/dismissals",
                            {"corpus": ["subset-sum-itqde"]}, "GET", b"")
    j = json.loads(body)
    assert st == 200 and j["counts"]["classes"] >= 1
    assert j["counts"]["dismissals"] >= j["counts"]["classes"]
    assert "eq-unused" in {r["kind"] for r in j["rows"]}


# ---------------------------------------------------------------------------
# THE REDLINE WALK (DESIGN_2026-08-10) — the server legs of the deposit loop: the
# altitude fields, the span + whole-paper anchors, the unscoped path, and the
# editor-save exemplar door with its receipt and its revoke.
# ---------------------------------------------------------------------------

from laplace.pipeline import schema as _sch                # noqa: E402


def _rows(md, kind=None):
    """The banked feedback rows (no ``record`` discriminator = a row, not an action)."""
    return [r for r in _ledger(md)
            if not r.get("record") and (kind is None or r.get("kind") == kind)]


def test_comment_banks_the_three_altitude_fields(tmp_path):
    md = _sectioned(tmp_path)
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "comment", "section": "S1", "paragraph": "S1-p1",
        "comment": "this opener buries the question",
        "scope": "structure", "scope_source": "chosen", "suggested_scope": "voice"})
    assert res["ok"] and res["grade"] == "paragraph"
    assert res["scope"] == "structure" and res["scope_source"] == "chosen"
    rec = _rows(md)[-1]
    assert rec["scope"] == "structure"
    assert rec["scope_source"] == "chosen"
    assert rec["suggested_scope"] == "voice"
    # …and the findings board carries all three through
    f = _un(rv.findings(md, "smoke"), rec["id"])
    assert (f["scope"], f["scope_source"], f["suggested_scope"]) == \
        ("structure", "chosen", "voice")


@pytest.mark.parametrize("scope", list(_sch.FEEDBACK_SCOPES))
def test_comment_accepts_every_one_of_the_six_scopes(tmp_path, scope):
    md = _sectioned(tmp_path)
    res = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "comment",
                                      "section": "S1", "comment": "x", "scope": scope})
    assert res["ok"] and _rows(md)[-1]["scope"] == scope


def test_comment_unscoped_is_first_class_and_absent(tmp_path):
    """No scope chosen → the row banks UNSCOPED: the field is ABSENT, not an empty
    string and not guessed, and the board reports it as None."""
    md = _sectioned(tmp_path)
    res = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "comment",
                                      "section": "S1", "comment": "a wordless squint"})
    assert res["ok"] and "scope" not in res
    rec = _rows(md)[-1]
    assert "scope" not in rec and "scope_source" not in rec
    f = _un(rv.findings(md, "smoke"), rec["id"])
    assert f["scope"] is None and f["scope_source"] is None


@pytest.mark.parametrize("bad", [
    {"scope": "sentance"}, {"scope": "node"},
    {"scope_source": "guessed"}, {"suggested_scope": "prose"}])
def test_comment_refuses_a_scope_outside_the_vocabulary(tmp_path, bad):
    md = _sectioned(tmp_path)
    n0 = len(_ledger(md))
    res = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "comment",
                                      "section": "S1", "comment": "x", **bad})
    assert "error" in res and "must be one of" in res["error"]
    assert len(_ledger(md)) == n0                       # nothing minted on a refusal


def test_comment_span_anchor_banks_grade_span_never_a_node(tmp_path):
    md = _sectioned(tmp_path)
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "comment", "span": {"sections": ["S1", "S2", "S3"]},
        "comment": "these three sections repeat one argument", "scope": "structure"})
    assert res["ok"] and res["grade"] == "span"
    assert res["sections"] == ["S1", "S2", "S3"]
    rec = _rows(md)[-1]
    assert rec["anchor"]["grade"] == "span"
    assert rec["anchor"]["sections"] == ["S1", "S2", "S3"]
    assert rec["node_id"] == "span:S1+S2+S3"            # a pseudo id, never a node
    f = _un(rv.findings(md, "smoke"), rec["id"])
    assert f["node"] is None and f["grade"] == "span"
    assert f["sections"] == ["S1", "S2", "S3"]


def test_comment_span_refuses_an_empty_or_malformed_span(tmp_path):
    md = _sectioned(tmp_path)
    n0 = len(_ledger(md))
    for span in ({"sections": []}, {"sections": "S1"}, 7):
        res = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "comment",
                                          "span": span, "comment": "x"})
        assert "error" in res and "span" in res["error"]
    assert len(_ledger(md)) == n0


@pytest.mark.parametrize("payload,grade,pseudo", [
    ({"artefact": True}, "artefact", "whole-artefact"),
    ({"grade": "artefact"}, "artefact", "whole-artefact"),
    ({"grade": "handover"}, "handover", "handover"),
])
def test_comment_whole_paper_banks_artefact_or_handover_grade(tmp_path, payload,
                                                              grade, pseudo):
    md = _sectioned(tmp_path)
    res = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "comment",
                                      "comment": "the through-line is not feelable",
                                      "scope": "artefact", **payload})
    assert res["ok"] and res["grade"] == grade
    rec = _rows(md)[-1]
    assert rec["anchor"]["grade"] == grade and rec["node_id"] == pseudo
    f = _un(rv.findings(md, "smoke"), rec["id"])
    assert f["node"] is None and f["grade"] == grade and f["section"] == ""


def test_comment_mark_only_banks_a_wordless_deposit(tmp_path):
    """Selection + Enter with an empty composer banks a mark, saying so in words —
    never an empty row that reads back as a lost comment."""
    md = _sectioned(tmp_path)
    res = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "comment",
                                      "section": "S1", "mark_only": True})
    assert res["ok"] and res["grade"] == "section"
    assert _rows(md)[-1]["comment"] == rv._MARK_ONLY_TEXT
    # without the flag an empty body is still refused (unchanged behaviour)
    assert "error" in rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "comment",
                                                  "section": "S1"})


def test_comment_actor_law_holds_for_every_new_tier(tmp_path):
    md = _sectioned(tmp_path)
    n0 = len(_ledger(md))
    for extra in ({"span": {"sections": ["S1"]}}, {"artefact": True}):
        res = rv.adjudicate(md, "smoke", {"verb": "comment", "comment": "x", **extra})
        assert "by (explicit actor) is required" in res["error"]
    assert len(_ledger(md)) == n0


def test_string_anchor_rows_do_not_sink_the_board(tmp_path):
    """His own calibration rows carry a STRING anchor ("whole-artefact", "handover").
    The board carries it through as anchor_ref instead of raising on it."""
    md = _sectioned(tmp_path, feedback=[
        {"id": "FB-gm-1", "project": "smoke", "ts": "2026-08-08T13:20:00",
         "source": "gerard:first-read", "anchor": "whole-artefact", "supersedes": "",
         "scope": "artefact", "kind": "orientation-starvation", "node_id": "",
         "section": "", "text": "the reader's window is tiny"}])
    f = _un(rv.findings(md, "smoke"), "FB-gm-1")
    assert f["anchor_ref"] == "whole-artefact" and f["node"] is None
    assert f["scope"] == "artefact" and f["comment"] == "the reader's window is tiny"
    assert f["row_source"] == "gerard:first-read"


# ------------------------------------------------------------------ the exemplar door

_BASELINE = "One.\nTwo.\nThree.\n"


def _exemplar_tree(tmp_path, monkeypatch, live=None):
    """A tmp repo root: a machine-minted baseline copy of S1.tex, the live (edited)
    S1.tex the editor saved, and the project's feedback ledger."""
    from laplace.manuscript import manuscript_versions
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "S1.tex").write_text(_BASELINE, encoding="utf-8")
    md = tmp_path / "ms"
    (md / "feedback").mkdir(parents=True)
    from laplace.manuscript import projection_viewer
    monkeypatch.setattr(projection_viewer,'_repo_root',lambda:tmp_path)
    (md / "S1.tex").write_text(_BASELINE, encoding="utf-8")
    projection_viewer.bank_editor_save(md,md/'S1.tex',_BASELINE.encode(),author='eigen:fixture',surface='walk',source='rewrite')
    baseline_rows,_=manuscript_versions._editor_save_rows(md,tmp_path)
    (md / "S1.tex").write_text(_BASELINE if live is None else live, encoding="utf-8")
    monkeypatch.setattr(manuscript_versions, "versions_payload", lambda corpus, root=None: {
        "rows": baseline_rows})
    monkeypatch.setattr(rv, "_exemplar_ledger",
                        lambda corpus, root: md / "feedback" / "feedback.jsonl")
    return md


def test_bank_exemplar_banks_one_row_in_the_gm_calibration_shape(tmp_path, monkeypatch):
    md = _exemplar_tree(tmp_path, monkeypatch, live="One.\nTwo, rewritten.\nThree.\n")
    receipt = rv.bank_exemplar("smoke", "ms/S1.tex", author="gerard",
                               project="smoke", root=tmp_path)
    assert receipt["banked"] is True
    assert receipt["passages"] == 1 and receipt["lines"] == 1
    assert receipt["destination"] == "ms/feedback/feedback.jsonl"
    rec = _rows(md)[-1]
    assert rec["id"] == receipt["exemplar_id"]
    for field in _sch.FEEDBACK_FIELDS:                  # the gm row shape, field for field
        assert field in rec, field
    assert rec["scope"] == "voice" and rec["kind"] == "author-rewrite"
    assert rec["anchor"] == "ms/S1.tex" and rec["source"].startswith("gerard:")
    assert rec["by"] == "gerard"                        # the actor law's attribution
    assert rec["hunks"] == [{"start": 2, "end": 2,
                             "before": ["Two."], "after": ["Two, rewritten."]}]
    # ONE row per save
    rv.bank_exemplar("smoke", "ms/S1.tex", author="gerard", project="smoke",
                     root=tmp_path)
    assert len(_rows(md, "author-rewrite")) == 2


def test_bank_exemplar_refuses_without_an_explicit_actor(tmp_path, monkeypatch):
    md = _exemplar_tree(tmp_path, monkeypatch, live="One.\nTwo, rewritten.\nThree.\n")
    r = rv.bank_exemplar("smoke", "ms/S1.tex", author="", project="smoke",
                         root=tmp_path)
    assert r["banked"] is False and "explicit actor" in r["reason"]
    assert _rows(md) == []                              # nothing minted


def test_bank_exemplar_banks_nothing_when_the_save_changed_nothing(tmp_path,
                                                                   monkeypatch):
    md = _exemplar_tree(tmp_path, monkeypatch)          # live == baseline
    r = rv.bank_exemplar("smoke", "ms/S1.tex", author="gerard", root=tmp_path)
    assert r["banked"] is False and "no edits of your hand" in r["reason"]
    assert _rows(md) == []


def test_exemplar_row_is_revocable_through_the_revoke_verb(tmp_path, monkeypatch):
    md = _exemplar_tree(tmp_path, monkeypatch, live="One.\nTwo, rewritten.\nThree.\n")
    ex = rv.bank_exemplar("smoke", "ms/S1.tex", author="gerard", project="smoke",
                          root=tmp_path)["exemplar_id"]
    assert any(f["id"] == ex for f in rv.findings(md, "smoke")["unanchored"])
    out = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "revoke",
                                      "supersedes": ex, "reason": "not my wording"})
    assert out["ok"] and out["revoked"] == "ledger-row"
    assert out["record"]["supersedes"] == ex            # append-only, never a rewrite
    assert not any(f["id"] == ex for f in rv.findings(md, "smoke")["unanchored"])
    # revoking again is an idempotent no-op
    assert rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "revoke",
                                       "supersedes": ex}).get("idempotent") is True


def test_hand_hunks_and_his_hand_share_one_baseline_diff(tmp_path, monkeypatch):
    _exemplar_tree(tmp_path, monkeypatch, live="One.\nTwo, rewritten.\nThree.\n")
    h = rv.hand_hunks("smoke", "ms/S1.tex", tmp_path)
    r = rv.his_hand("smoke", "ms/S1.tex", tmp_path)
    assert h["counts"] == r["counts"] == {"passages": 1, "lines": 1}
    assert r["ranges"] == [{"start": 2, "end": 2}]      # the hunk text projected away
    assert "hunks" not in r and h["hunks"][0]["before"] == ["Two."]


def test_his_hand_route_serves_hunks_only_when_asked(monkeypatch):
    """The your-hand band needs each passage's before/after; every other reader wants the
    bare ranges. One producer, two projections, selected by ``?hunks=1`` — and the DEFAULT
    is unchanged, so no existing reader moves."""
    monkeypatch.setattr(rv, "_resolve", lambda q: (Path("."), "smoke", ""))
    monkeypatch.setattr(rv, "his_hand", lambda c, f: {"ranges": [{"start": 1, "end": 2}]})
    monkeypatch.setattr(rv, "hand_hunks", lambda c, f: {"hunks": [{"start": 1, "end": 2,
                                                                   "before": ["a"],
                                                                   "after": ["b"]}]})
    q = {"corpus": ["smoke"], "file": ["ms/S1.tex"]}
    st, _, plain = review_http.handle("/review/his-hand", q, "GET", b"")
    assert st == 200 and "hunks" not in json.loads(plain)
    st2, _, full = review_http.handle("/review/his-hand", {**q, "hunks": ["1"]}, "GET", b"")
    assert st2 == 200 and json.loads(full)["hunks"][0]["before"] == ["a"]
    # and the file is still required, on either projection
    st3, _, _ = review_http.handle("/review/his-hand", {"corpus": ["smoke"], "hunks": ["1"]},
                          "GET", b"")
    assert st3 == 400


def test_projection_tex_save_carries_the_exemplar_receipt(tmp_path, monkeypatch):
    """The HTTP door: POST /projection/tex?bank=editor banks the save AND the exemplar,
    and the response carries the receipt the front end echoes."""
    from laplace.manuscript import projection_viewer as pv
    from laplace.web import scanner
    md = _exemplar_tree(tmp_path, monkeypatch)
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(pv, "_manuscript_dir_for", lambda corpus: md)
    from laplace.manuscript import manuscript_source
    (md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n\\input{S1}\n\\end{document}\n')
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'smoke','project_dir':'ms','tex_root':'ms','manifest':{'document':{'root':'main.tex','manuscript_dir':'ms'}}}]}))
    q = {"file": ["ms/S1.tex"], "bank": ["editor"], "corpus": ["smoke"],
         "author": ["gerard"], "expected_selection":[manuscript_source.selection_identity(manuscript_source.resolve('smoke',tmp_path))]}
    q["expected_source_digest"] = [pv._source_observation(md / "S1.tex")["expected_source_digest"]]
    st, _, body = pv.handle("/projection/tex", q, "POST",
                            "One.\nTwo, rewritten.\nThree.\n".encode("utf-8"))
    out = json.loads(body)
    assert st == 200 and out["ok"] and out["version_id"]
    ex = out["exemplar"]
    assert ex["banked"] is True and ex["passages"] == 1 and ex["lines"] == 1
    assert ex["destination"] == "ms/feedback/feedback.jsonl"
    assert _rows(md)[-1]["id"] == ex["exemplar_id"]
    # A registered document save with no actor refuses before source/history effects.
    q["expected_source_digest"] = [out["expected_source_digest"]]
    st2, _, body2 = pv.handle("/projection/tex", {**q, "author": [""]}, "POST",
                              "One.\nTwo, rewritten again.\nThree.\n".encode("utf-8"))
    assert st2 == 422 and json.loads(body2)["reason"] == "source-actor-required"
    assert (md/"S1.tex").read_text() == "One.\nTwo, rewritten.\nThree.\n"
    assert len(_rows(md, "author-rewrite")) == 1


def test_named_release_resolves_the_newest_named_artefact(tmp_path):
    from laplace.web import artefact as af

    class _Ctx:
        target_dir = tmp_path / "out"
        manuscript_dir = tmp_path / "ms"

    (tmp_path / "out").mkdir()
    (tmp_path / "ms").mkdir()
    (tmp_path / "out" / "main.pdf").write_bytes(b"%PDF")
    # absent → the payload says so in words, never an empty field to interpret
    absent = af.named_release(_Ctx, tmp_path)
    assert absent["present"] is False and absent["pdf"] is None
    assert "no named release artefact" in absent["note"]
    for name in ("roland-qrc-2026-08-08-r1.pdf", "roland-qrc-2026-08-09-r3.pdf",
                 "roland-qrc-2026-08-09-r2.pdf"):
        (tmp_path / "out" / name).write_bytes(b"%PDF")
    got = af.named_release(_Ctx, tmp_path)
    assert got["present"] is True and got["name"] == "roland-qrc-2026-08-09-r3.pdf"
    assert (got["slug"], got["date"], got["revision"]) == ("roland-qrc", "2026-08-09", 3)
    assert got["label"] == "reading: roland-qrc-2026-08-09-r3"
    assert got["pdf"] == "out/roland-qrc-2026-08-09-r3.pdf"


def test_context_payload_exposes_the_named_release_for_the_live_paper():
    """The handover law on the LIVE paper: the context names a minted release, and it is
    the newest one actually on disk. The NAME is not pinned here — every revision mints a
    new one (r3 was re-minted as roland-qrc-review-2026-08-10-r3 the day the walk was
    built), and a test that pins today's filename fails on tomorrow's release rather than
    on a real regression. The synthetic ordering test above pins the exact bytes."""
    from laplace.web import artefact as af
    ctx = af.context_payload("paper_roland_qrc")
    nr = ctx["named_release"]
    assert nr["present"] is True
    assert af._MINTED_PDF_RE.match(nr["name"])
    assert nr["label"] == f"reading: {nr['stem']}"
    root = af._repo_root()
    on_disk = sorted(
        (m.group("date"), int(m.group("rev")))
        for m in (af._MINTED_PDF_RE.match(p.name)
                  for p in (root / "paper_roland_qrc" / "manuscript").glob("*.pdf"))
        if m is not None)
    assert (nr["date"], nr["revision"]) == on_disk[-1]


# ---------------------------------------------------------------------------
# THE REDLINE WALK — the block model (GET /walk/doc) and the rewrite door.
#
# The block model is fenced against the REAL corpus (paper_roland_qrc), read-only: a
# synthetic tex tree would only prove the parser against itself. The rewrite door is
# fenced on tmp fixtures, because it WRITES.
# ---------------------------------------------------------------------------

from laplace.manuscript import walk as wk                              # noqa: E402
from laplace.web import scanner as _scanner                     # noqa: E402


def _tmp_project(monkeypatch, md):
    """A tmp manuscript the walk's doc model can actually read: `doc_model` and the
    path fences resolve against the REPO ROOT, so a fixture outside it is refused and
    the model comes back with no fragments at all. Both are pointed at the fixture's
    own tree — the one root, moved, not two roots disagreeing."""
    monkeypatch.setattr(_scanner, "_repo_root", lambda: md.parent)
    monkeypatch.setattr(rv, "manuscript_dir", lambda *a, **k: md)
    return md


@pytest.fixture(scope="module")
def roland_doc():
    """The live block model of the roland paper — built once, read many. Pure read."""
    return wk.doc("paper_roland_qrc")


def _all_blocks(doc):
    return [b for s in doc["sections"] for b in s["blocks"]]


def test_walk_doc_models_the_roland_paper_from_its_input_order(roland_doc):
    """Sections come from the root's \\input order and carry the paper's own labels."""
    d = roland_doc
    assert d["ok"] is True and d["corpus"] == "paper_roland_qrc"
    assert "Spectroscopic Learning" in d["title"]
    ids = [s["id"] for s in d["sections"]]
    for want in ("sec:r2_intro", "sec:r2_comb", "sec:r2_discussion"):
        assert want in ids, ids
    assert ids.index("sec:r2_intro") < ids.index("sec:r2_comb") \
        < ids.index("sec:r2_discussion")
    assert d["counts"]["sections"] == len(d["sections"]) >= 8
    assert d["counts"]["blocks"] == len(_all_blocks(d)) > 100
    assert "content-faithful" in d["fidelity"] and "Geometry" in d["fidelity"]
    assert not d.get("missing_files")


def test_walk_doc_blocks_slice_the_fragment_files_byte_for_byte(roland_doc):
    """THE IDENTITY THE SPLICE TURNS ON: every block's ``tex`` is exactly what its ``src``
    span reads back from disk, split the way the rewrite door splits it. If this drifts,
    the deterministic splice silently becomes a guess."""
    md = rv._repo_root() / "paper_roland_qrc" / "manuscript"
    cache = {}
    blocks = _all_blocks(roland_doc)
    assert blocks
    for b in blocks:
        src = b["src"]
        f = src["file"]
        assert not f.startswith("/") and ".." not in f       # manuscript-relative
        lines = cache.setdefault(f, (md / f).read_text(encoding="utf-8").split("\n"))
        assert 1 <= src["line_start"] <= src["line_end"] <= len(lines), (b["id"], src)
        assert "\n".join(lines[src["line_start"] - 1:src["line_end"]]) == b["tex"], b["id"]
        assert b["kind"] in ("para", "equation", "head", "figure", "caption",
                             "list", "table", "explained", "raw")
        assert b["id"].startswith(f + "#")
    assert len({b["id"] for b in blocks}) == len(blocks)      # ids are unique


def test_walk_doc_types_paragraphs_equations_and_figures(roland_doc):
    """The typed grain: prose tokenizes into pieces, equations carry body + env + the
    built number, figures carry a served route to bytes that exist."""
    d = roland_doc
    comb = next(s for s in d["sections"] if s["id"] == "sec:r2_comb")
    kinds = {b["kind"] for b in comb["blocks"]}
    assert {"head", "para", "equation", "figure"} <= kinds

    para = next(b for b in comb["blocks"] if b["kind"] == "para")
    assert para["pieces"] and all(p["t"] for p in para["pieces"])
    # the paragraph grain rides the ONE producer (projection_viewer.parse_paragraphs)
    assert para["spec_id"].startswith("sec:r2_comb-p")
    assert {p["t"] for p in para["pieces"]} & {"text", "math", "cite"}

    eq = next(b for b in comb["blocks"]
              if b["kind"] == "equation" and "eq:ridge" in (b.get("labels") or []))
    assert eq["env"] in ("align", "equation") and "\\lVert" in eq["math"]
    assert "\\label" not in eq["math"]                 # stripped for KaTeX…
    assert "\\label{eq:ridge}" in eq["tex"]            # …never lost from the source
    assert eq["number"] == d["refs"]["eq:ridge"]

    fig = next(b for b in _all_blocks(d)
               if b["kind"] == "figure" and b.get("label") == "fig:weights")
    assert fig["image"].startswith("/walk/asset?")
    assert fig["images"][0]["exists"] is True
    assert "readout" in fig["caption"] and fig["caption_pieces"]
    cs = fig["caption_src"]
    assert fig["src"]["line_start"] <= cs["line_start"] <= cs["line_end"] \
        <= fig["src"]["line_end"]


def test_walk_doc_resolves_every_cite_and_ref_the_prose_uses(roland_doc):
    """The built artifacts are the authority: keys resolve from the .bbl, labels from
    the .aux. An unresolved one would render as a bare key on his canvas."""
    d = roland_doc
    cit = d["citations"]["lukosevicius_reservoir_2009"]
    assert cit["num"] == 1
    assert "Reservoir computing approaches" in cit["entry"] and "2009" in cit["entry"]
    assert all(isinstance(v["num"], int) for v in d["citations"].values())

    pieces = [p for b in _all_blocks(d)
              for p in (b.get("pieces") or []) + (b.get("caption_pieces") or [])]
    keys = {k for p in pieces if p["t"] == "cite" for k in p["keys"]}
    labels = {p["label"] for p in pieces if p["t"] == "ref"}
    assert len(keys) > 20 and keys <= set(d["citations"]), sorted(keys - set(d["citations"]))
    assert len(labels) > 20 and labels <= set(d["refs"]), sorted(labels - set(d["refs"]))
    assert d["refs"]["sec:r2_comb"] and d["refs"]["fig:weights"]
    assert isinstance(d["macros"], dict)               # extracted; empty is honest


def test_walk_prefers_current_aux_over_larger_historical_snapshot(tmp_path, monkeypatch):
    """The current manuscript's labels must not be replaced by a larger old snapshot.

    This is the SSG failure mode: the historical aux has more labels and bytes, but
    its ``sec:S*`` vocabulary belongs to a different paper generation than the live
    ``sec:N*`` fragments.
    """
    current = tmp_path / "current-main.aux"
    historical = tmp_path / "historical-main.aux"
    current.write_text("\\relax\n\\newlabel{sec:N1}{{I}{1}{}{section*.3}{}}\n",
                       encoding="utf-8")
    historical.write_text("\\relax\n\\newlabel{sec:S1}{{1}{1}{old}{section.1}{}}\n"
                          + ("% old snapshot padding\n" * 2000), encoding="utf-8")
    monkeypatch.setattr(wk, "_bib_artifact_candidates",
                        lambda _md, _corpus, _filename, _root_tex=None: [current, historical])
    assert wk._resolve_bib_artifact(tmp_path, "subset-sum-itqde", "main.aux") == current


def test_walk_doc_keeps_unknown_environment_source_in_a_compiled_custom_block(tmp_path):
    """Unknown environments keep exact source while the real preamble decides rendering."""
    source = "\\begin{unrecognisedfixture}\nPreserve these words.\n\\end{unrecognisedfixture}"
    blocks = wk.blocks_for(source, file_rel="fixture.tex", repo_file="fixture.tex", md=tmp_path,
                           corpus="fixture", dir_param="", para_spans=[], known_macros=frozenset())
    assert len(blocks) == 1
    block = blocks[0]
    assert block["kind"] == "custom" and block["custom_kind"] == "compiled"
    assert block["env"] == "unrecognisedfixture" and block["tex"] == source
    assert block["src"] == {"file": "fixture.tex", "repo_file": "fixture.tex",
                             "line_start": 1, "line_end": 3}
    assert "Preserve these words." in "".join(
        piece.get("s", "") for piece in block["pieces"] if piece.get("t") == "text")


def test_walk_doc_emits_prose_written_in_the_root_itself(tmp_path, monkeypatch):
    """GAP-20260810-root-content-dropped. Prose written directly in ``main.tex`` — outside
    every ``\\input`` — used to be absent from the block model with nothing said: a silent
    hole in a canvas whose whole claim is content fidelity. It now emits as blocks whose
    ``src`` names ``main.tex`` and its real lines, IN DOCUMENT ORDER against the inputs,
    and whatever was genuinely skipped is named in one line on the payload."""
    md = tmp_path / "wp"
    md.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\n"
        "\\newcommand{\\Ham}{\\hat{H}}\n"
        "\\begin{document}\n"
        "\\title{A Root With Prose}\n"
        "\\begin{abstract}\n"
        "\\input{abstract}\n"
        "\\end{abstract}\n"
        "\\maketitle\n"
        "\\input{S1}\n"
        "\n"
        "\\section{Data Availability}\n"
        "\n"
        "The scripts are held under the project's numerics tree and are\n"
        "re-runnable in one step.\n"
        "\n"
        "\\bibliography{literature}\n"
        "\\end{document}\n", encoding="utf-8")
    (md / "abstract.tex").write_text("The abstract's own prose.\n", encoding="utf-8")
    (md / "S1.tex").write_text("\\section{One}\nSection one's body.\n", encoding="utf-8")

    _tmp_project(monkeypatch, md)
    d = wk.doc("smoke")
    assert d["ok"] is True
    root_blocks = [b for s in d["sections"] for b in s["blocks"]
                   if b["src"]["file"] == "main.tex"]
    kinds = [b["kind"] for b in root_blocks]
    assert "head" in kinds and "para" in kinds, kinds
    para = next(b for b in root_blocks if b["kind"] == "para")
    assert "numerics tree" in para["tex"]
    assert para["pieces"] and para["pieces"][0]["t"] == "text"
    # the src span reads the root back byte for byte, like every other block
    lines = (md / "main.tex").read_text(encoding="utf-8").split("\n")
    s = para["src"]
    assert "\n".join(lines[s["line_start"] - 1:s["line_end"]]) == para["tex"]
    # DOCUMENT ORDER: the root's own section comes AFTER the \input it follows in the root
    ids = [sec["id"] for sec in d["sections"]]
    assert ids.index("one") < ids.index("data-availability"), ids
    # the abstract's own prose still renders once, from its fragment — the revtex wrapper
    # around the \input is not printed as an empty raw block
    assert any(b["tex"].strip() == "The abstract's own prose."
               for sec in d["sections"] for b in sec["blocks"])
    assert not [b for sec in d["sections"] for b in sec["blocks"]
                if b["kind"] == "raw" and b.get("env") == "abstract"]
    # NO SILENT HOLES: what was skipped is named, in one line, on the payload
    note = d["root_note"]
    assert "main.tex" in note and "2 block(s)" in note
    for named in ("the preamble", "\\maketitle", "\\bibliography", "abstract wrapper"):
        assert named in note, note
    assert "\\newcommand" not in " ".join(d["root_skipped"][:1])   # preamble, said once


def test_walk_doc_renders_lists_and_typed_tables(tmp_path, monkeypatch, roland_doc):
    """GAP-20260810-raw-block-fidelity. itemize/enumerate/description are prose the author
    redlines: they render as real lists with each item through the SAME piece pipeline (so
    math and citations inside an item render and carry their source offsets), nested one
    level. Supported tabular content is now typed while retaining its exact source."""
    md = _sectioned(tmp_path, s1=(
        "\\section{Lists}\n"
        "\\begin{enumerate}\n"
        "\\item The first, with $\\omega$ and \\cite{a}.\n"
        "\\item The second.\n"
        "\\begin{itemize}\n"
        "\\item A nested one.\n"
        "\\end{itemize}\n"
        "\\end{enumerate}\n"
        "\\begin{description}\n"
        "\\item[term] its gloss.\n"
        "\\end{description}\n"
        "\\begin{tabular}{cc}\na & b \\\\\n\\end{tabular}\n"))
    # `_sectioned` writes its root on ONE line; the \input order (and so the doc model's
    # file list) is read line by line, so the fixture's root is written out properly here.
    (md / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n\\input{S1}\n\\end{document}\n",
        encoding="utf-8")
    _tmp_project(monkeypatch, md)
    d = wk.doc("smoke")
    blocks = [b for s in d["sections"] for b in s["blocks"]]
    lists = [b for b in blocks if b["kind"] == "list"]
    assert [b["env"] for b in lists] == ["enumerate", "description"]

    num = lists[0]
    assert num["ordered"] is True and len(num["items"]) == 2
    first = num["items"][0]
    assert {p["t"] for p in first["pieces"]} >= {"text", "math", "cite"}
    # the item's pieces carry offsets into the BLOCK's tex, not into the item in isolation
    for p in first["pieces"]:
        assert num["tex"][p["o_start"]:p["o_end"]]
        assert wk.tex_pieces(num["tex"][p["o_start"]:p["o_end"]])[0]["t"] == p["t"]
    cite = next(p for p in first["pieces"] if p["t"] == "cite")
    assert num["tex"][cite["o_start"]:cite["o_end"]] == "\\cite{a}"
    # nesting, one level
    sub = num["items"][1]["sub"]
    assert sub["env"] == "itemize" and sub["ordered"] is False
    assert sub["items"][0]["pieces"][0]["s"].strip() == "A nested one."
    # a description list's term rides its own pieces
    assert lists[1]["items"][0]["term"] == "term"

    tables = [b for b in blocks if b["kind"] == "table"]
    assert [b["env"] for b in tables] == ["tabular"]
    assert [[cell["tex"] for cell in row["cells"]] for row in tables[0]["rows"]] == [["a", "b"]]

    # AND ON THE REAL CORPUS: the raw count drops by exactly the two enumerates
    live_raw = [b["env"] for b in _all_blocks(roland_doc) if b["kind"] == "raw"]
    live_lists = [b["env"] for b in _all_blocks(roland_doc) if b["kind"] == "list"]
    assert sorted(live_lists) == ["enumerate", "enumerate"]
    assert "enumerate" not in live_raw and "itemize" not in live_raw
    assert not live_raw
    assert {b.get("env") for b in _all_blocks(roland_doc) if b["kind"] == "table"} == {"table", "table*"}
    assert any(b.get("env") == "acknowledgments" and b["kind"] == "para" for b in _all_blocks(roland_doc))


def test_walk_pieces_mark_an_unknown_macro_visibly():
    """An unknown macro is never silently dropped: it reads back as a macro piece
    carrying its verbatim source and ``known: False``."""
    pieces = wk.tex_pieces("A \\wobble{x} and \\emph{that}.")
    macro = next(p for p in pieces if p["t"] == "macro")
    assert macro["name"] == "wobble" and macro["s"] == "\\wobble{x}"
    assert macro["known"] is False and macro["args"] == ["x"]
    emph = next(p for p in pieces if p["t"] == "emph")
    assert emph["s"] == "that"
    known = wk.tex_pieces("\\wobble{x}", known_macros=frozenset({"\\wobble"}))
    assert known[0]["known"] is True


def test_walk_macros_extract_from_the_preamble_for_katex(tmp_path):
    root = tmp_path / "main.tex"
    root.write_text(
        "\\documentclass{article}\n"
        "\\newcommand{\\Ham}{\\hat{H}}\n"
        "\\newcommand\\vecx[1]{\\mathbf{#1}}\n"
        "\\DeclareMathOperator{\\tr}{tr}\n"
        "% \\newcommand{\\ghost}{never}\n"
        "\\begin{document}\\newcommand{\\late}{no}\\end{document}\n",
        encoding="utf-8")
    m = wk.preamble_macros(root)
    assert m["\\Ham"] == "\\hat{H}"
    assert m["\\vecx"] == "\\mathbf{#1}"
    assert m["\\tr"] == "\\operatorname{tr}"
    assert "\\ghost" not in m and "\\late" not in m    # commented out / past the preamble


def test_walk_doc_and_asset_route_through_handle():
    st, ctype, body = wk.handle("/walk/doc", {"corpus": ["paper_roland_qrc"]}, "GET", b"")
    d = json.loads(body)
    assert st == 200 and ctype.startswith("application/json") and d["ok"]
    fig = next(b for b in _all_blocks(d) if b["kind"] == "figure" and b["images"])
    rel = fig["images"][0]["file"]
    ast, actype, abody = wk.handle("/walk/asset",
                                   {"corpus": ["paper_roland_qrc"], "file": [rel]},
                                   "GET", b"")
    # the figure's PDF bytes, unrasterised — the client hands them to pdf.js
    assert ast == 200 and actype == "application/pdf" and abody[:4] == b"%PDF"
    fst, _, fbody = wk.handle("/walk/asset",
                              {"corpus": ["paper_roland_qrc"],
                               "file": ["../../src/laplace/manuscript/walk.py"]}, "GET", b"")
    assert fst == 403 and "manuscript" in json.loads(fbody)["error"]
    ust, _, ubody = wk.handle("/walk/doc", {"corpus": ["no-such-corpus"]}, "GET", b"")
    assert ust == 404 and json.loads(ubody)["ok"] is False


def test_walk_figure_trust_root_is_the_project_dir_and_still_a_fence(tmp_path,
                                                                    monkeypatch):
    """WO-20260810: a figure written ``{../figures/x}`` leaves the manuscript dir, and the
    old md-only fence found it on disk then threw it away (exists:false, honest fallback).
    The trust root is now the registry row's project_dir for a CORPUS-addressed request —
    so the sibling figures dir resolves and serves — and it is still a fence: past the
    project_dir refuses, an absolute path refuses, and a raw ``?dir=`` is never widened."""
    project = tmp_path / "eigenengine"
    md = project / "manuscript"
    figures = project / "figures"
    md.mkdir(parents=True)
    figures.mkdir()
    (md / "main.tex").write_text(
        "\\documentclass{article}\\usepackage{graphicx}\\begin{document}"
        "\\includegraphics{../figures/fig_shard}\\end{document}", encoding="utf-8")
    (figures / "fig_shard.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    from laplace.web import shared_ui
    from laplace.manuscript import manuscript_versions
    from laplace.pipeline import registry
    monkeypatch.setattr(rv, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(wk, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(shared_ui, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(registry, "_repo_root", lambda: tmp_path)
    md = rv.manuscript_dir("eigenengine", "")
    assert md is not None and md.name == "manuscript"
    root = wk._trust_root("eigenengine", "", md)
    assert root == md.parent                            # widened to eigenengine/
    assert wk._trust_root("", "eigenengine/manuscript", md) == md   # raw ?dir=: never

    # the escape that used to be discarded now resolves, root-relative and inside the root
    p, rel = wk._resolve_image(md, "../figures/fig_shard", root)
    assert p is not None and rel == "figures/fig_shard.pdf"
    assert p.resolve().is_relative_to(root.resolve())
    # …and under the md-only root (a raw ?dir= walk) the SAME argument is still refused
    assert wk._resolve_image(md, "../figures/fig_shard", md) == (None,
                                                                 "../figures/fig_shard")
    # containment is the whole fence: an absolute argument OUTSIDE the root is refused
    # (an absolute one inside it is just a long spelling of a file the root already owns)
    assert wk._resolve_image(md, "/etc/passwd", root)[0] is None
    assert wk._resolve_image(md, str(md.parent.parent / "src/laplace/walk"), root)[0] \
        is None

    st, ctype, body = wk.handle("/walk/asset",
                                {"corpus": ["eigenengine"], "file": [rel]}, "GET", b"")
    assert st == 200 and ctype == "application/pdf" and body[:4] == b"%PDF"

    for bad in ("../src/laplace/manuscript/walk.py", "../../etc/passwd", "/etc/passwd"):
        bst, _, bbody = wk.handle("/walk/asset",
                                  {"corpus": ["eigenengine"], "file": [bad]}, "GET", b"")
        assert bst == 403, (bad, bst)
        assert "trust root" in json.loads(bbody)["error"]
    # the raw ?dir= door gets NO widening: the very figure the corpus door serves is 403
    dst, _, _ = wk.handle("/walk/asset",
                          {"dir": ["eigenengine/manuscript"],
                           "file": ["../figures/fig_shard.pdf"]}, "GET", b"")
    assert dst == 403


# ------------------------------------------------------------------ the rewrite door
#
# OWNING ROOT (M5 S3): rv.adjudicate admits ONE owning root at its public boundary (RD-EDITOR-ROOT) and refuses a
# rewrite whose source lies outside it before any lease, read or effect. These fixtures build their manuscript
# under pytest's tmp_path, so every rewrite names tmp_path as that root explicitly; the fence is unchanged and
# test_rewrite_outside_the_owning_root_refuses_before_any_effect keeps its adverse control.

def test_rewrite_splices_the_named_lines_and_banks_row_version_and_receipt(tmp_path):
    md = _sectioned(tmp_path, s1="% S1-p1\nOne.\nTwo, as written.\nThree.\n")
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "paragraph": "S1-p1",
        "file": "S1.tex", "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, rewritten by hand.",
        "block": "S1.tex#S1-p1"}, repo_root=tmp_path)
    assert res["ok"] is True and res["pending"] is False, res
    assert res["applied"]["file"] == "S1.tex" and res["applied"]["lines"] == [3, 3]
    # the file took the splice byte for byte, and nothing else moved
    assert (md / "S1.tex").read_text(encoding="utf-8") == \
        "% S1-p1\nOne.\nTwo, rewritten by hand.\nThree.\n"
    # the row: the SAME kind the exemplar door banks, scoped sentence by default
    row = _rows(md)[-1]
    assert row["kind"] == "author-rewrite" and row["by"] == "gerard"
    assert row["scope"] == "sentence" and res["scope"] == "sentence"
    assert row["anchor"]["before"] == "Two, as written."
    assert row["anchor"]["after"] == "Two, rewritten by hand."
    assert row["anchor"]["lines"] == [3, 3] and row["anchor"]["file"] == "S1.tex"
    assert row["anchor"]["block"] == "S1.tex#S1-p1"
    # the version: banked through the ONE editor-save store
    assert res["version_id"] and res["version_id"].startswith("save-")
    saved = md / "editor_saves" / res["version_id"] / "S1.tex"
    assert saved.read_text(encoding="utf-8") == (md / "S1.tex").read_text(encoding="utf-8")
    # the receipt: ids + destination, in words
    r = res["receipt"]
    assert r["banked"] is True and r["pending"] is False and r["row_id"] == row["id"]
    assert r["version_id"] == res["version_id"] and r["file"] == "S1.tex"
    assert row["id"] in r["words"] and "S1.tex:3-3" in r["words"]


def test_rewrite_outside_the_owning_root_refuses_before_any_effect(tmp_path):
    """The adverse control of the explicit owning root: the same rewrite under ANOTHER root is refused before any
    lease, read or effect; the file and the ledger are untouched."""
    (tmp_path / "project").mkdir()
    (tmp_path / "elsewhere").mkdir()
    md = _sectioned(tmp_path / "project", s1="% S1-p1\nOne.\nTwo, as written.\nThree.\n")
    before = (md / "S1.tex").read_bytes()
    ledger = md / "feedback" / "feedback.jsonl"
    rows_before = ledger.read_bytes() if ledger.exists() else None
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "paragraph": "S1-p1",
        "file": "S1.tex", "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, rewritten by hand.",
        "block": "S1.tex#S1-p1"}, repo_root=tmp_path / "elsewhere")
    assert res["reason"] == "source-outside-owning-root" and res["refused_before_effect"] is True and "ok" not in res
    assert (md / "S1.tex").read_bytes() == before
    assert (ledger.read_bytes() if ledger.exists() else None) == rows_before


def test_rewrite_with_a_note_banks_the_compound_row(tmp_path):
    md = _sectioned(tmp_path, s1="% S1-p1\nOne.\nTwo, as written.\n")
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, sharpened.",
        "note": "the hedge was doing no work", "scope": "voice"}, repo_root=tmp_path)
    assert res["ok"] and res["compound"] is True and res["scope"] == "voice"
    row = _rows(md)[-1]
    assert row["comment"] == "the hedge was doing no work"    # the rationale
    assert row["anchor"]["after"] == "Two, sharpened."         # the replacement
    assert row["anchor"]["compound"] is True
    assert res["receipt"]["compound"] is True
    assert "with your note" in res["receipt"]["words"]


def test_rewrite_on_a_byte_mismatch_banks_pending_and_says_so(tmp_path):
    md = _sectioned(tmp_path, s1="% S1-p1\nOne.\nTwo, MOVED ON.\n")
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, rewritten by hand."}, repo_root=tmp_path)
    assert res["ok"] is True and res["pending"] is True and res["applied"] is None
    # the file is UNTOUCHED — a mismatch never guesses
    assert (md / "S1.tex").read_text(encoding="utf-8") == "% S1-p1\nOne.\nTwo, MOVED ON.\n"
    row = _rows(md)[-1]
    assert row["kind"] == "pending-rewrite" and row["anchor"]["pending"] is True
    assert row["anchor"]["after"] == "Two, rewritten by hand."
    assert row["anchor"]["found"] == "Two, MOVED ON."
    words = res["receipt"]["words"]
    assert "no longer the text you edited" in words and "nothing was spliced" in words
    assert res["receipt"]["row_id"] == row["id"] and res["receipt"]["version_id"] is None
    # a span past the end of the file is the SAME honest pending path, never a crash
    far = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 90, "line_end": 99, "before": "x", "after": "y"}, repo_root=tmp_path)
    assert far["ok"] and far["pending"] is True
    assert _rows(md)[-1]["anchor"]["out_of_range"] is True


def test_rewrite_refuses_without_an_explicit_actor(tmp_path):
    """THE ACTOR LAW: no default anywhere — nothing banked, nothing spliced."""
    md = _sectioned(tmp_path, s1="% S1-p1\nOne.\nTwo, as written.\n")
    res = rv.adjudicate(md, "smoke", {
        "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, rewritten."}, repo_root=tmp_path)
    assert "error" in res and "by (explicit actor) is required" in res["error"]
    assert (md / "S1.tex").read_text(encoding="utf-8") == \
        "% S1-p1\nOne.\nTwo, as written.\n"
    assert not (md / "feedback" / "feedback.jsonl").exists()


def test_rewrite_refuses_marker_mutation_and_escapes_and_bad_spans(tmp_path):
    md = _sectioned(tmp_path, s1="% S1-p1\nOne.\nTwo, as written.\n")
    eaten = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 1, "line_end": 2, "before": "% S1-p1\nOne.", "after": "One."}, repo_root=tmp_path)
    assert "error" in eaten and eaten["reason"] == "marker-mutation"
    assert (md / "S1.tex").read_text(encoding="utf-8") == \
        "% S1-p1\nOne.\nTwo, as written.\n"
    out = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "../escape.tex",
        "line_start": 1, "line_end": 1, "before": "x", "after": "y"}, repo_root=tmp_path)
    assert "error" in out and out["reason"] == "no-fragment"
    nofile = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "",
        "line_start": 3, "line_end": 3, "before": "x", "after": "y"}, repo_root=tmp_path)
    assert "file is required" in nofile["error"]
    noguard = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 3, "line_end": 3, "before": "  ", "after": "y"}, repo_root=tmp_path)
    assert "before must be non-empty" in noguard["error"]
    badspan = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 4, "line_end": 2, "before": "x", "after": "y"}, repo_root=tmp_path)
    assert "1-based inclusive span" in badspan["error"]
    assert not (md / "feedback" / "feedback.jsonl").exists()


def test_rewrite_routes_through_the_adjudicate_door(tmp_path, monkeypatch):
    """The verb is reachable exactly where every other deposit rides — POST
    /review/adjudicate — and its roster entry is the one the executor checks."""
    md = _sectioned(tmp_path, s1="% S1-p1\nOne.\nTwo, as written.\n")
    monkeypatch.setattr(rv, "manuscript_dir", lambda *a, **k: md)
    monkeypatch.setattr(rv, "_repo_root", lambda: tmp_path)   # the door admits this fixture's owning root (M5 S3)
    payload = {"corpus": "smoke", "by": "gerard", "verb": "rewrite", "section": "S1",
               "file": "S1.tex", "line_start": 3, "line_end": 3,
               "before": "Two, as written.", "after": "Two, from the door."}
    st, _, body = review_http.handle("/review/adjudicate", {}, "POST",
                            json.dumps(payload).encode("utf-8"))
    out = json.loads(body)
    assert st == 200 and out["ok"] and out["receipt"]["row_id"]
    assert "Two, from the door." in (md / "S1.tex").read_text(encoding="utf-8")
    assert "rewrite" in rv._ADJ_VERBS


# ------------------------------------------------- the walk client reads THIS contract
#
# The defect these close: the walk surface tested ``res.applied === true``, but the door
# has never returned a boolean there — the applied path returns a DICT and the pending
# path returns ``None``, with ``pending`` carrying the verdict. Every splice that reached
# disk therefore read back on the surface as a refusal: the block never re-rendered, its
# line span went stale, and the composer told him in red that his edit had not landed.
# Nothing in the suite exercised the client's predicate, so the two sides drifted in
# silence. These fences read the door's real answers AND run the surface's real code
# against them, so the pair can never disagree again unnoticed.

def _rewrite_both_paths(tmp_path):
    """The door's two real answers: the applied path and the byte-mismatch path."""
    (tmp_path / "ok").mkdir()
    (tmp_path / "no").mkdir()
    md_ok = _sectioned(tmp_path / "ok", s1="% S1-p1\nOne.\nTwo, as written.\nThree.\n")
    applied = rv.adjudicate(md_ok, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "paragraph": "S1-p1",
        "file": "S1.tex", "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, rewritten by hand.",
        "block": "S1.tex#S1-p1"}, repo_root=tmp_path)
    md_no = _sectioned(tmp_path / "no", s1="% S1-p1\nOne.\nTwo, as written.\nThree.\n")
    pending = rv.adjudicate(md_no, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 3, "line_end": 3,
        "before": "Two, something ELSE entirely.", "after": "Two, rewritten by hand."}, repo_root=tmp_path)
    return applied, pending


def test_rewrite_door_states_its_verdict_in_pending_and_applied_only(tmp_path):
    """THE CONTRACT THE SURFACE MUST READ, pinned on both paths.

    ``pending`` is the verdict and it is an explicit bool on BOTH answers. ``applied`` is
    a provenance dict on the applied path and ``None`` on the pending one — never a
    boolean, and there is no ``spliced`` key to read instead."""
    applied, pending = _rewrite_both_paths(tmp_path)

    assert applied["ok"] is True
    assert applied["pending"] is False
    assert isinstance(applied["applied"], dict)
    assert applied["applied"]["file"] == "S1.tex"
    assert applied["applied"]["lines"] == [3, 3]
    assert applied["applied"]["block"] == "S1.tex#S1-p1"
    assert applied["applied"] is not True                 # the shape the client got wrong
    assert "spliced" not in applied                       # no such key has ever existed

    assert pending["ok"] is True
    assert pending["pending"] is True
    assert pending["applied"] is None
    assert "spliced" not in pending
    assert pending["record"]["kind"] == "pending-rewrite"
    # and the record's own flags, the client's last-resort reading
    assert applied["record"]["anchor"]["applied"] is True
    assert pending["record"]["anchor"]["pending"] is True


def _node():
    """The node binary, or a skip — the walk surface is JS and its predicate is only
    honestly testable by RUNNING it. Skips (never fails) where node is absent."""
    import shutil
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node is not on PATH; the walk client fence needs it")
    return exe


from walk_source import walk_source, walk_declarations  # noqa: E402  (walk.mjs and its owner modules, M5 S2)


def _walk_slice(start_mark, end_mark):
    """A verbatim slice of the SHIPPED surface between two markers. A missing marker
    fails loudly: the fence must never quietly start testing nothing."""
    src = walk_source()                       # the walk root and its owner modules
    a = src.index(start_mark)                 # ValueError if the marker moved away
    b = src.index(end_mark, a)
    return src[a:b]


def _node_eval(js_prelude, expr, node_exe, *, module=False):
    import subprocess
    prog = js_prelude + "\nprocess.stdout.write(JSON.stringify(" + expr + "));\n"
    out = subprocess.run([node_exe, *(["--input-type=module"] if module else []), "-e", prog], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_walk_client_predicate_reads_the_doors_real_answers(tmp_path):
    """THE SURFACE'S OWN CODE, run against THE DOOR'S OWN ANSWERS.

    ``appliedOf``/``pendingOf`` are sliced verbatim out of ``walk.mjs`` and evaluated on
    the two dicts :func:`rv.adjudicate` actually returned. The old predicate
    (``res.applied === true || res.spliced === true``) is evaluated beside them, so the
    fence records the defect as well as the fix."""
    node_exe = _node()
    applied, pending = _rewrite_both_paths(tmp_path)
    src = _walk_slice("/** did the door splice?", "function receiptWords")
    # M5 S3: the slice calls sourceEffectDisposition, which walk-source-client.mjs imports from source-effect.mjs;
    # the REAL export is imported here (it has no dependencies), never a stub.
    effect = Path(__file__).resolve().parents[1] / "src/laplace/web/static_shared/source-effect.mjs"
    prelude = ("import {sourceEffectDisposition} from " + json.dumps(effect.as_uri()) + ";\n" + src
               + "\nconst A = " + json.dumps(applied, default=str) + ";"
               + "\nconst P = " + json.dumps(pending, default=str) + ";")
    got = _node_eval(prelude, (
        "{ appliedOnApplied: appliedOf(A, A.record),"
        "  appliedOnPending: appliedOf(P, P.record),"
        "  pendingOnApplied: pendingOf(A, A.record),"
        "  pendingOnPending: pendingOf(P, P.record),"
        "  oldOnApplied: (A.applied === true || A.spliced === true"
        "                 || A.record.applied === true) }"), node_exe, module=True)
    assert got["appliedOnApplied"] is True     # the splice that landed reads as landed
    assert got["appliedOnPending"] is False
    assert got["pendingOnApplied"] is False
    assert got["pendingOnPending"] is True
    assert got["oldOnApplied"] is False        # the defect, recorded


def test_walk_locator_reads_the_tie_and_writes_the_source_register_back(tmp_path):
    """THE ONE TRANSFORM, INVERTED IN BOTH DIRECTIONS — on the shipped locator source.

    ``walk._text_norm`` maps ``~`` to U+00A0 and ``---`` to an em dash when it renders.
    The locator must map them BACK to find the passage (JS ``\\s`` matches U+00A0, so a
    whitespace-first test silently ate every tie), and the splice must map them back
    again when it writes, or a rewrite converts an all-ASCII LaTeX source to the
    typographic register the composer promises it will not touch."""
    node_exe = _node()
    src = (_walk_slice("const WS_NOT_TIE", "const el = (tag")
           + _walk_slice("const SOURCE_OF = {", "/** The block's source as it now stands"))
    # the rendered face of `Eq.~(4) --- the comb`, exactly as `_text_norm` produces it
    tex = "the comb of Eq.~(4) --- and its width"
    from laplace.manuscript import walk as wk_
    rendered = wk_._text_norm(tex)
    assert "\u00a0" in rendered and "\u2014" in rendered
    prelude = (src
               + "\nconst TEX = " + json.dumps(tex) + ";"
               + "\nconst Q = norm(" + json.dumps(rendered) + ");"
               + "\nfunction hits(q){const re=locatorRe(q);if(!re)return 0;"
                 "let m,n=0;while((m=re.exec(TEX))){if(!m[0].length){re.lastIndex+=1;"
                 "continue;}n+=1;if(n>2)break;}return n;}")
    got = _node_eval(prelude, (
        "{ tieSurvivesNorm: Q.indexOf('\\u00a0') >= 0,"
        "  matches: hits(Q),"
        "  writtenBack: toSourceRegister(Q) }"), node_exe)
    assert got["tieSurvivesNorm"] is True      # `norm` no longer eats the tie
    assert got["matches"] == 1                 # so the splice is deterministic, not pending
    # and his passage goes back into the file in the file's own register
    assert got["writtenBack"] == tex
    assert all(ord(c) < 128 for c in got["writtenBack"])


# ------------------------------------------------- the scope verb and the door's default
#
# Both had NO standing fence. The scope verb is the door behind the composer's promise
# ("scope it later from the band") and the band's only write; the ``sentence``/``default``
# pair is what lets any consumer tell the machine's lean from his hand — the contract's own
# mechanical retirement test ("a rule whose override rate exceeds ~1/3 is retired") has
# nothing to count without it. Unfenced, either could be deleted or quietly re-defaulted
# and every suite would stay green.

def test_scope_verb_appends_a_scoping_record_and_is_idempotent(tmp_path):
    """THE SCOPE-LATER DOOR. An APPEND naming the row and the altitude — the banked line is
    never rewritten — and a second scoping to the SAME altitude says nothing twice."""
    md = _sectioned(tmp_path)
    banked = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "comment", "section": "S1",
        "comment": "this belongs earlier", "suggested_scope": "structure"})
    fid = banked["record"]["id"]
    assert "scope" not in banked["record"]              # banked UNSCOPED, first-class
    before = len(_ledger(md))

    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "scope", "finding_id": fid, "scope": "structure",
        "scope_source": "chosen", "note": "scoped from the walk's session band"})
    assert res["ok"] is True and res["scope"] == "structure"
    assert res["scope_source"] == "chosen" and res["previous_scope"] == ""
    assert res["receipt"]["banked"] is True and res["receipt"]["target"] == fid
    rec = res["record"]
    assert rec["record"] == "scoping" and rec["target"] == fid
    assert rec["scope"] == "structure" and rec["suggested_scope"] == "structure"
    # AN APPEND, NOT A RELABEL: exactly one new line, and the deposit itself is untouched
    ledger = _ledger(md)
    assert len(ledger) == before + 1
    row = next(r for r in ledger if r.get("id") == fid)
    assert "scope" not in row or row.get("scope") != "structure"
    # and the findings board folds the scoping over the row when it reads
    board = rv.findings(md, "smoke")
    folded = next(f for f in board["unanchored"] + [x for s in board.get("sections", [])
                                                    for x in s.get("findings", [])]
                  if f["id"] == fid)
    assert folded["scope"] == "structure"

    again = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "scope", "finding_id": fid, "scope": "structure"})
    assert again["ok"] is True and again["idempotent"] is True and again["record"] is None
    assert len(_ledger(md)) == before + 1               # nothing appended twice

    moved = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "scope", "finding_id": fid, "scope": "voice"})
    assert moved["ok"] and moved["previous_scope"] == "structure"
    assert len(_ledger(md)) == before + 2


def test_scope_verb_refuses_an_unknown_row_scope_or_actor(tmp_path):
    """It sets an altitude and never guesses one: no id, no such id, an altitude outside
    the vocabulary, or no actor — each refuses, and each writes nothing."""
    md = _sectioned(tmp_path)
    banked = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "comment", "section": "S1", "comment": "a note"})
    fid = banked["record"]["id"]
    before = len(_ledger(md))

    noid = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "scope",
                                       "scope": "voice"})
    assert "finding_id is required" in noid["error"]

    ghost = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "scope",
                                        "finding_id": "no-such-row", "scope": "voice"})
    assert ghost["reason"] == "no-such-row" and "mints nothing" in ghost["error"]

    noscope = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "scope",
                                          "finding_id": fid})
    assert "scope is required" in noscope["error"]

    bad = rv.adjudicate(md, "smoke", {"by": "gerard", "verb": "scope",
                                      "finding_id": fid, "scope": "altitude"})
    assert "scope must be one of" in bad["error"]

    unattributed = rv.adjudicate(md, "smoke", {"verb": "scope", "finding_id": fid,
                                               "scope": "voice"})
    assert "error" in unattributed and "actor" in unattributed["error"]

    assert len(_ledger(md)) == before                    # not one line written


def test_rewrite_banks_the_doors_own_default_scope_on_both_paths(tmp_path):
    """THE DOOR'S LEAN IS NAMED AS THE DOOR'S. A rewrite with no altitude banks
    ``sentence`` with ``scope_source: "default"`` — on the applied path AND on the pending
    one — so no consumer can read the machine's default as an altitude he picked. An
    altitude he DID pick survives untouched."""
    (tmp_path / "ok").mkdir()
    (tmp_path / "no").mkdir()
    (tmp_path / "his").mkdir()

    md_ok = _sectioned(tmp_path / "ok", s1="% S1-p1\nOne.\nTwo, as written.\n")
    applied = rv.adjudicate(md_ok, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, rewritten."}, repo_root=tmp_path)
    assert applied["pending"] is False and applied["scope"] == "sentence"
    row = _rows(md_ok)[-1]
    assert row["scope"] == "sentence" and row["scope_source"] == "default"

    md_no = _sectioned(tmp_path / "no", s1="% S1-p1\nOne.\nTwo, MOVED ON.\n")
    pending = rv.adjudicate(md_no, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, rewritten."}, repo_root=tmp_path)
    assert pending["pending"] is True and pending["scope"] == "sentence"
    prow = _rows(md_no)[-1]
    assert prow["kind"] == "pending-rewrite"
    assert prow["scope"] == "sentence" and prow["scope_source"] == "default"

    md_his = _sectioned(tmp_path / "his", s1="% S1-p1\nOne.\nTwo, as written.\n")
    chosen = rv.adjudicate(md_his, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, sharpened.",
        "scope": "voice", "scope_source": "chosen"}, repo_root=tmp_path)
    assert chosen["scope"] == "voice"
    hrow = _rows(md_his)[-1]
    assert hrow["scope"] == "voice" and hrow["scope_source"] == "chosen"
    # the constants the walk's routing line mirrors are the door's own, named once
    assert rv._REWRITE_DEFAULT_SCOPE == "sentence"
    assert rv._REWRITE_DEFAULT_SCOPE_SOURCE == "default"


def test_a_defaulted_rewrite_row_is_re_scopable_from_the_band(tmp_path):
    """THE ROW CLASS THE BAND COULD NOT REACH. A rewrite banked at the door's own default
    carries a scope, so a band gated on ``!scope`` would never offer it the door. The
    scope verb takes it — the machine's lean is re-scopable, which is the whole reason
    ``scope_source`` is recorded."""
    md = _sectioned(tmp_path, s1="% S1-p1\nOne.\nTwo, as written.\n")
    rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "rewrite", "section": "S1", "file": "S1.tex",
        "line_start": 3, "line_end": 3,
        "before": "Two, as written.", "after": "Two, rewritten."}, repo_root=tmp_path)
    row = _rows(md)[-1]
    assert row["scope"] == "sentence" and row["scope_source"] == "default"
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "scope", "finding_id": row["id"], "scope": "voice",
        "scope_source": "chosen"})
    assert res["ok"] and res["scope"] == "voice" and res["previous_scope"] == "sentence"
    assert res["record"]["record"] == "scoping"


def test_the_walk_is_rostered_and_its_doors_link_both_ways():
    """THE DOORS (his call 2026-08-10: integration, not orphanhood).

    The walk was reachable only by typing its URL. It is now on the ONE authored roster
    (``shared_ui._VIEWS``, whose coverage law puts every row in the journey exactly once),
    the artefact surface's head carries a plain ``walk`` anchor, and the walk's head
    carries a named return anchor back. All three are LINKS: the clean room governs what
    this surface IMPORTS, never what it links to, and neither surface imports a line of the
    other's code."""
    from laplace.web import shared_ui
    from laplace.manuscript import manuscript_versions

    row = next(v for v in shared_ui.views_roster()["views"] if v["id"] == "walk")
    assert row["path"] == "/walk" and row["clean_room"] is True
    assert "redline walk" in row["purpose"]
    # the journey's coverage law: every roster row appears exactly once, stage or door
    placed = []
    for st in shared_ui.journey_payload(None)["stages"]:
        placed.append(st.get("view") or st.get("id"))
        placed += [d.get("view") for d in (st.get("doors") or []) if d.get("view")]
    assert placed.count("walk") == 1, placed

    src = Path(rv.__file__).resolve().parents[1] / "web"   # the served pages (laplace/web)
    art = (src / "artefact.html").read_text(encoding="utf-8")
    walk_html = (src / "walk.html").read_text(encoding="utf-8")

    # the artefact head's walk door: named, model-wired, and importing no walk code
    assert 'id="art-walk-door"' in art and ">walk</a>" in art
    assert '"/walk?corpus=" + encodeURIComponent(c)' in art
    assert "walk.mjs" not in art and "walk.py" not in art
    # the walk's named return door, and no shell import on either side of it
    assert 'id="back-door"' in walk_html and ">artefact surface</a>" in walk_html
    assert "artefact-panes.mjs" not in walk_html and "shell.js" not in walk_html
    mjs = walk_source()
    assert '"/artefact?corpus=" + encodeURIComponent(S.corpus)' in mjs
    assert re.search(r'^import .*from "([^"]+)"', mjs, re.M).group(1) == "/shared/store.mjs"


# --------------------------------------------------------- THE FELT DIGIT BOUNDARY
#
# The regression this closes, in its own words. Three boundaries have been tried:
#
#   1. "a digit is a scope key while the note is empty and holds the caret" — a state the
#      DOMINANT gesture never reaches, because arming a selection puts the caret in the
#      PASSAGE. A bare `1` there typed a digit into the frozen quote, `shapeOf()` flipped
#      to "rewrite", and Enter banked a rewrite of his paragraph with a `1` in it.
#   2. "am I in a text field" — right for the field case, and it moved the scope key to
#      Alt+digit. But Alt+digit was wired ONLY into the composer element's own listener,
#      so from the paper, from a flipped block's source, from the band — everywhere the
#      hint line promised "from anywhere" — the key did nothing at all.
#   3. THIS. One `scopeKey(ev)` called from both chains, the document's chain bailing on
#      any key a nearer handler already took (without which `setScope`'s toggle would
#      take the altitude straight back off in the same keystroke).
#
# The fence runs the SHIPPED functions, and evaluates boundary (2) beside them, so the
# defect is recorded as well as the fix.

_KEY_STUBS = """
const SCOPES = ["sentence", "structure", "voice", "artefact", "meta", "delivery"];
const C = { armed: { grade: "selection" }, scope: "", scopeSource: "" };
function setScope(scope, source) {
  C.scope = C.scope === scope ? "" : scope;
  C.scopeSource = C.scope ? source : "";
}
const keymap = { hidden: true };
const L = { open: false }, F = { blockId: "" }, G = { open: false };
const S = { span: null, sections: [], current: -1 };
const paragraphTransition = null;
const noop = () => {};
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const takeDoor = () => false, setSpan = noop, saveFlip = noop, disarm = noop;
const armArtefact = noop, undoLast = noop, flipBlock = noop, focusedBlock = () => null;
const toggleGeometry = noop, toggleLedger = noop, closeLedger = noop;
const armFromSelection = () => false, armBlockAtReadingLine = () => false;
const armSpan = noop, toggleRail = noop, toggleSpine = noop, jumpToIndex = noop;
const sectionAtY = () => 0, readingY = () => 0;
const zoomIn = noop, zoomOut = noop, zoomFit = noop;
const compActorInput = { tagName: "INPUT" }, nameActor = noop, bankDeposit = noop;
// the edit card's chain (gesture 1.1): a live typed edit takes the digits when no
// composer is armed. Stubbed COLD here (no card) so the composer boundary is graded
// alone; the card-live case gets its own eval below.
const E = { blockId: "", scope: "" };
let CARD = null;
function setEditScope(s) { E.scope = s; }
const commitEdit = noop, revertEdit = noop;
const FIELD = { tagName: "TEXTAREA", isContentEditable: false };   // the passage / the note
const CHROME = { tagName: "DIV", isContentEditable: false };       // a chip / the shape line
// the cross-paragraph refusal (2026-08-11) touches the live selection on every editing
// key; stubbed COLD (no selection) so the boundary is graded alone, as with the card.
const document = { getSelection: () => null };
const P = new Map();
const commitAll = noop, closestBlock = () => null, blockById = new Map(), showCard = noop;
function mk(key, target, mods) {
  const e = Object.assign({ key, target, altKey: false, ctrlKey: false, metaKey: false,
                            shiftKey: false, defaultPrevented: false }, mods || {});
  e.preventDefault = () => { e.defaultPrevented = true; };
  e.stopPropagation = noop;
  return e;
}
/** boundary (2), as it stood before this round: the composer's listener only, and the
 *  document chain bailing on any modifier. */
function oldChain(e, insideComposer) {
  if (insideComposer) {
    const d = /^[1-6]$/.test(e.key) ? Number(e.key) : 0;
    return !!(d && (e.altKey || !inField(e.target)));
  }
  return false;                       // `if (ev.metaKey || ev.ctrlKey || ev.altKey) return;`
}
function run(key, target, mods, both) {
  C.scope = ""; C.scopeSource = "";
  const e = mk(key, target, mods);
  onComposerKey(e);
  if (both) onKey(e);                 // the SAME event bubbling on to the document chain
  return { scope: C.scope, source: C.scopeSource, prevented: e.defaultPrevented };
}
function runDoc(key, target, mods) {
  C.scope = ""; C.scopeSource = "";
  const e = mk(key, target, mods);
  onKey(e);
  return { scope: C.scope, prevented: e.defaultPrevented, old: oldChain(e, false) };
}
"""


def test_walk_digit_boundary_types_in_a_field_and_scopes_from_anywhere(tmp_path):
    """THE BOUNDARY, RUN. In a field a bare digit types and sets nothing; on chrome a bare
    digit scopes; Alt+digit scopes from anywhere — including from the document chain, which
    is where boundary (2) did nothing — and one keystroke seen by both chains sets the
    altitude ONCE."""
    node_exe = _node()
    src = (_walk_slice("function rulingKey(ev)", "function renderScopeChips()")
           + _walk_slice("function inField(t)", "function onKey(ev)")
           + _walk_slice("function onKey(ev)", "/** the felt mode boundary")
           + _walk_slice("function scopeKey(ev)", "function wireControls()"))
    got = _node_eval(src + _KEY_STUBS, (
        "{ bareInField:   run('3', FIELD, null, true),"
        "  altInField:    run('3', FIELD, { altKey: true }, true),"
        "  bareOnChrome:  run('2', CHROME, null, true),"
        "  ctrlInField:   run('3', FIELD, { ctrlKey: true }, true),"
        "  altFromPaper:  runDoc('3', CHROME, { altKey: true }),"
        "  altInFieldDoc: runDoc('4', FIELD, { altKey: true }),"
        "  oldAltInField: oldChain(mk('3', FIELD, { altKey: true }), true),"
        "  disarmed:      (C.armed = null, run('3', CHROME, null, true)) }"), node_exe)

    # 1 · IN A FIELD A BARE DIGIT TYPES. Nothing is scoped and nothing is swallowed, so
    #     the character reaches the textarea and the composer re-renders around it.
    assert got["bareInField"] == {"scope": "", "source": "", "prevented": False}
    # 2 · ALT+DIGIT SCOPES FROM INSIDE A FIELD …
    assert got["altInField"]["scope"] == "voice"
    assert got["altInField"]["source"] == "chosen"
    assert got["altInField"]["prevented"] is True
    # 3 · … AND FROM THE DOCUMENT CHAIN, which is exactly what boundary (2) could not do:
    #     `onKey` bailed on every modifier before any digit was read.
    assert got["altFromPaper"]["scope"] == "voice"
    assert got["altFromPaper"]["old"] is False          # the defect, recorded
    assert got["altInFieldDoc"]["scope"] == "artefact"
    # 4 · ONE KEYSTROKE, ONE ALTITUDE. Every case above ran the composer's chain AND the
    #     document's over the same event; without the `defaultPrevented` bail the second
    #     pass would toggle the altitude straight back off.
    assert got["altInField"]["scope"] and got["altFromPaper"]["scope"]
    # 5 · on chrome a bare digit scopes; a control-modified digit is not ours
    assert got["bareOnChrome"]["scope"] == "structure"
    assert got["ctrlInField"] == {"scope": "", "source": "", "prevented": False}
    # 6 · and with nothing armed the digit is nobody's
    assert got["disarmed"] == {"scope": "", "source": "", "prevented": False}
    # 7 · UNLESS the edit card is live (gesture 1.1): the same digits set THAT altitude —
    #     Alt+digit from anywhere; in a field a bare digit still TYPES.
    card_got = _node_eval(src + _KEY_STUBS + """
CARD = { hidden: false };
E.blockId = "abstract.tex#abstract-p1";
C.armed = null;
""", (
        "{ altSets:  (E.scope = '', scopeKey(mk('3', FIELD, { altKey: true }))"
        "             , E.scope),"
        "  bareTypes: (E.scope = '', scopeKey(mk('3', FIELD, null)), E.scope),"
        "  bareOnChrome: (E.scope = '', scopeKey(mk('5', CHROME, null)), E.scope) }"),
        node_exe)
    assert card_got["altSets"] == "voice"       # Alt+3 reaches the card from a field
    assert card_got["bareTypes"] == ""          # in a field a bare digit TYPES, still
    assert card_got["bareOnChrome"] == "meta"   # on chrome a bare digit scopes the card


def test_walk_a_digit_typed_into_the_passage_converts_the_shape_visibly(tmp_path):
    """THE SILENT CONVERSION, REPRODUCED AND CLOSED. In a field a bare digit TYPES — which
    in the prefilled passage IS the rewrite gesture. The fence runs the shipped `shapeOf`
    over the composer's own fields: one digit appended flips the banked shape from comment
    to rewrite, and the surface's `edited` predicate — the same expression `renderComposer`
    writes onto the passage's label and border in that frame — is true with it."""
    node_exe = _node()
    src = (_walk_slice("const WS_NOT_TIE", "const el = (tag")
           + walk_declarations("quotable", "shapeOf"))
    prelude = (src + """
const QUOTE = "the comb of the drive sets the reach";
const compQuote = { value: QUOTE };
const compBody = { value: "" };
const C = { armed: { grade: "selection", texFace: false, quote: QUOTE } };
function edited() { return norm(compQuote.value) !== norm(C.armed.quote); }
function type(ch) { compQuote.value += ch; return { shape: shapeOf(), edited: edited() }; }
""")
    got = _node_eval(prelude, (
        "{ atRest: { shape: shapeOf(), edited: edited() },"
        "  afterOneDigit: type('3'),"
        "  withANote: (compBody.value = 'the hedge does no work', shapeOf()) }"), node_exe)
    assert got["atRest"] == {"shape": "comment", "edited": False}
    # ONE BARE DIGIT: the deposit is now a REWRITE, and the passage says so in that frame
    assert got["afterOneDigit"] == {"shape": "rewrite", "edited": True}
    assert got["withANote"] == "compound"
    # and the surface writes exactly that predicate to the label and the border
    mjs = walk_source()
    assert "const edited = hasQuote && norm(compQuote.value) !== norm(a.quote);" in mjs
    assert 'compQuote.dataset.edited = edited ? "1" : ""' in mjs
    assert "EDITED, so Enter banks a rewrite" in mjs


# ------------------------------------------- the piece source offsets and the piecewise
#                                              locator (GAP-20260810-piece-source-offsets)
#
# The narrowing these close: para pieces carried no per-piece source span, so the client's
# locator could only invert ONE transform over a WHOLE block — it could place a passage
# only when the passage was a single unbroken run of prose in the source. On a physics
# paper nearly every sentence carries inline math or a citation, and the rendered face of
# those (`[12]`, KaTeX's glyphs) is nowhere in the fragment: every such rewrite fell to the
# pending path. That is his DOMINANT gesture.

_PIECE_TEX = ("The comb of $\\omega_k$ and its width \\cite{lukos} is set by $\\tau$ "
              "here.\n\\[ E = mc^2 \\]\nAnd 20\\% after it.")

#: the harness's stand-in renderer. The map's RENDERED half is whatever the canvas draws —
#: a citation draws its number from the built bibliography, KaTeX draws glyphs — and only a
#: browser knows that. What is fenced here is the ARITHMETIC that inverts the map, so the
#: rendered side is any faithful stand-in with the right shape; `scripts/audit_walk_surface.py`
#: fences that the shipped renderer is the thing that fills it in.
_PIECE_RENDER_JS = """
function mapOf(pieces) {
  const R = { math: (p) => "[" + String(p.s || "").replace(/[\\\\\\s{}]/g, "") + "]",
              cite: () => "[1]", ref: () => "3", break: () => "" };
  let at = 0; const map = [];
  for (const p of pieces) {
    const r = (R[p.t] || ((q) => String(q.s == null ? "" : q.s)))(p);
    map.push({ t: p.t, rStart: at, rEnd: at + r.length, rText: r,
               oStart: p.o_start, oEnd: p.o_end });
    at += r.length;
  }
  return map;
}
function rendered(map) { return map.map((m) => m.rText).join(""); }
function wholeBlockHits(tex, q) {
  const re = locatorRe(q); if (!re) return 0;
  let m, n = 0;
  while ((m = re.exec(tex))) { if (!m[0].length) { re.lastIndex += 1; continue; }
                               n += 1; if (n > 2) break; }
  return n;
}
"""


def test_walk_piece_offsets_are_the_source_of_every_piece(roland_doc):
    """THE INVARIANT THE CLIENT MAP RESTS ON, on the real corpus: for every piece,
    ``tex[o_start:o_end]`` IS that piece's own source — re-tokenizing that slice alone
    yields exactly that one piece back. Offsets are ordered and non-overlapping, and they
    address the BLOCK's tex (a head's title, a figure's caption and a list item's prose
    included), never some inner string in isolation."""
    known = frozenset(roland_doc["macros"])
    seen = 0
    for b in _all_blocks(roland_doc):
        groups = [b.get("pieces"), b.get("caption_pieces")]
        for it in b.get("items") or []:
            groups += [it.get("pieces"), it.get("term_pieces")]
            for sub in ([it["sub"]] if it.get("sub") else []):
                groups += [i2.get("pieces") for i2 in sub["items"]]
        for pieces in groups:
            last = 0
            for p in pieces or []:
                seen += 1
                assert 0 <= p["o_start"] <= p["o_end"] <= len(b["tex"]), (b["id"], p)
                assert p["o_start"] >= last, (b["id"], p)     # ordered, non-overlapping
                last = p["o_end"]
                again = wk.tex_pieces(b["tex"][p["o_start"]:p["o_end"]], known)
                assert len(again) == 1, (b["id"], p["t"], again)
                assert again[0]["t"] == p["t"] and again[0].get("s") == p.get("s")
                assert again[0].get("keys") == p.get("keys")
                assert again[0].get("label") == p.get("label")
    assert seen > 1000, seen


def test_walk_locator_splices_across_math_and_refuses_inside_it(tmp_path):
    """THE PIECEWISE-EXACT LOCATOR, on the shipped source.

    Three claims, each run through ``pieceSpanOf`` sliced verbatim out of ``walk.mjs``:

      * a selection BRIDGING an inline math piece maps to a byte-exact source span —
        and the whole-block locator finds it ZERO times, which is the defect recorded;
      * a selection ADJACENT to inline math, and one spanning a citation, do too;
      * a selection STRICTLY INSIDE display math refuses, naming ``math`` as the reason —
        rendered math is not addressable as prose."""
    node_exe = _node()
    pieces = wk.tex_pieces(_PIECE_TEX)
    src = (_walk_slice("const WS_NOT_TIE", "const el = (tag")
           + _walk_slice("const SOURCE_OF = {", "/** The block's source as it now stands"))
    prelude = (src + _PIECE_RENDER_JS
               + "\nconst TEX = " + json.dumps(_PIECE_TEX) + ";"
               + "\nconst PIECES = " + json.dumps(pieces) + ";"
               + "\nconst MAP = mapOf(PIECES);"
               + "\nconst R = rendered(MAP);"
               + "\nconst DM = MAP[PIECES.findIndex((p) => p.t === 'math' && p.display)];"
               + "\nfunction span(a, b) { return pieceSpanOf(MAP, TEX, a, b); }"
               + "\nfunction cut(r) { return r && r.at ? TEX.slice(r.at[0], r.at[1]) : null; }")
    got = _node_eval(prelude, (
        "{ bridge: cut(span(R.indexOf('comb'), R.indexOf('width') + 5)),"
        "  bridgeOldHits: wholeBlockHits(TEX,"
        "      R.slice(R.indexOf('comb'), R.indexOf('width') + 5)),"
        "  adjacent: cut(span(R.indexOf('comb'), MAP[1].rStart)),"
        "  acrossCite: cut(span(R.indexOf('width'), R.indexOf('set') + 3)),"
        "  insideMath: span(DM.rStart + 2, DM.rEnd - 2),"
        "  plainProse: cut(span(R.indexOf('And'), R.indexOf('after') + 5)),"
        "  headWord: cut(span(R.indexOf('The'), R.indexOf('The') + 3)) }"), node_exe)

    # THE BRIDGE: byte-exact, and the whole-block locator could not place it at all
    assert got["bridge"] == "comb of $\\omega_k$ and its width"
    assert got["bridgeOldHits"] == 0            # the defect, recorded
    assert got["adjacent"] == "comb of "
    assert got["acrossCite"] == "width \\cite{lukos} is set"
    # STRICTLY INSIDE display math: refused, with the reason stated
    assert got["insideMath"]["at"] is None and got["insideMath"]["refused"] == "math"
    # a TeX escape inside a prose run still inverts (`20\\%` renders `20%`)
    assert got["plainProse"] == "And 20\\% after"
    assert got["headWord"] == "The"
    # and the whole-block locator DOES place plain prose — the fallback is still live
    assert _PIECE_TEX.count("comb of $") == 1


def test_comment_door_keeps_the_block_and_the_line_span_it_is_handed(tmp_path):
    """The walk addresses a BLOCK over a line SPAN; both ride the anchor when supplied,
    and a precise paragraph id grades the row at ``paragraph``, not the section beat."""
    md = _sectioned(tmp_path, s1="% S1-p1\nOne.\nTwo.\n")
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "comment", "section": "S1", "paragraph": "S1-p1",
        "comment": "this beat lands twice", "quote": "Two.", "coarse": False,
        "block": "S1.tex#S1-p1", "source_file": "S1.tex",
        "source_line": 2, "line_end": 3})
    assert res["ok"] and res["grade"] == "paragraph" and res["coarse"] is False
    a = res["record"]["anchor"]
    assert a["paragraph_id"] == "S1-p1" and a["grade"] == "paragraph"
    assert a["block"] == "S1.tex#S1-p1"
    assert a["source_file"] == "S1.tex" and a["source_lines"] == [2, 3]
    # BACKWARD COMPATIBLE: a caller that names neither mints exactly the old anchor
    plain = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "comment", "section": "S1", "comment": "coarse one"})
    pa = plain["record"]["anchor"]
    assert plain["grade"] == "section"
    assert "block" not in pa and "source_lines" not in pa


def test_comment_on_a_figure_block_reaches_the_figure_tier(tmp_path):
    """A note deposited on a figure must reach the figure tier the re-authoring session
    reads (``figure-standard``), carrying its block and span — the walk sends the label
    the door's own model already parsed."""
    md = _sectioned(tmp_path, s1="% S1-p1\nOne.\n")
    res = rv.adjudicate(md, "smoke", {
        "by": "gerard", "verb": "comment", "section": "S1",
        "comment": "the axes want units", "figure": "fig:comb",
        "block": "S1.tex#fig-comb", "source_file": "S1.tex",
        "source_line": 4, "line_end": 9})
    assert res["ok"] and res["grade"] == "figure"
    assert res["review_kind"] == "figure-standard" and res["figure"] == "fig:comb"
    a = res["record"]["anchor"]
    assert a["figure"] == "fig:comb" and a["block"] == "S1.tex#fig-comb"
    assert a["source_file"] == "S1.tex" and a["source_lines"] == [4, 9]
