"""Pure unit tests for THE DESK COCKPIT surface (no server, no browser).

W5 rehoused the desk MECHANISM out of the dead ``/guide`` explainer into
``laplace.web.desk`` (surface 6, ``/desk``). This suite is the W1.3/W2.1/W2.2 desk-join
+ act-door contract, re-aimed at the new home — NEVER weakened. The guide explainer's
own tests (STAGES, /guide/section, /guide/close, the architecture derivation, the
guide-chain live pane) retired WITH the chrome they tested (deleting tests for deleted
chrome is correct). What survives here is the desk itself:

  (a) the eleven-class read-model (GET /desk/data): strata-first, golden-payload-bounded
      (≤40 rows / 16KB, Law I), every class joining a REAL store, strata-ordered rows;
  (b) THE ONE MUTATION DOOR (POST /desk/act): each verb a THIN dispatch to an existing
      executor — unattributed → 422 + zero delta; unknown/closed target → refusal; the
      happy path writes the SAME record the executor writes; double-fire → idempotent;
      a NAMED-but-unwired verb is a fail-closed 422 naming where its door lands;
  (c) THE COCKPIT read-model (conception §6): every row carries its door-ready ``fields``,
      its ``deeplinks`` onto the WORKING surfaces (/artefact, /conceptric, /storyboard),
      and its per-class CONSEQUENCES model; GET /desk/referent serves the FULL CONTEXT
      referent for one row (the source document + the ledger row + the node's prose),
      inline and untruncated (the chair's P6 fix).

The DOM half (chip filter, cockpit expansion, arm-to-fire, the actor always sent, the
422 rendered, the four zones, the deep-link landing on /artefact) is proven in
tests/j5desk_cockpit.playwright.mjs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.web import desk

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCANNER_PY = _REPO_ROOT / "src" / "laplace" / "web" / "scanner.py"


# ── read-only, owns only /desk/* ────────────────────────────────────────────

def test_handle_returns_none_for_foreign_paths():
    assert desk.handle("/analytics/data", {}, "GET", b"") is None
    assert desk.handle("/desk", {}, "GET", b"") is None       # bare page served by scanner


def test_handle_405s_on_post_read_route():
    status, _, body = desk.handle("/desk/data", {}, "POST", b"{}")
    assert status == 405
    assert "read-only" in json.loads(body)["error"]


# ── the eleven-class read-model (GET /desk/data) ────────────────────────────

def test_queue_cap_is_forty_law_I():
    # F12 / Law I: the ONE producer of the density bound is 40 (was 50).
    assert desk._QUEUE_CAP == 40


def test_desk_classes_are_the_authored_eleven_in_order():
    assert len(desk._DESK_CLASSES) == 11
    expect = ["adjudications", "plan-ops", "forks", "proxy-drafts", "lifts",
              "open-frictions", "recurrence-clusters", "stale-reads", "work-orders",
              "holdout", "release-states"]
    assert [c["class"] for c in desk._DESK_CLASSES] == expect
    for c in desk._DESK_CLASSES:
        assert c["store"] and c["scope"] and c["verbs"]
        assert c["owner"] in {"him", "engine"}
        assert isinstance(c["verbs"], list) and all(isinstance(v, str) for v in c["verbs"])
    # the verb map is a pure projection of the one table (no second copy)
    assert desk._CLASS_VERBS == {c["class"]: c["verbs"] for c in desk._DESK_CLASSES}
    # the five author-gated classes are the badge's basis
    him = [c["class"] for c in desk._DESK_CLASSES if c["owner"] == "him"]
    assert him == ["adjudications", "plan-ops", "forks", "proxy-drafts", "lifts"]


def test_desk_endpoint_shape_and_golden_payload_law():
    status, ctype, body = desk.handle("/desk/data", {}, "GET", b"")
    assert status == 200 and "json" in ctype
    # THE GOLDEN PAYLOAD LAW: ≤16KB on the wire
    assert len(body) <= 16 * 1024, f"desk payload {len(body)}B exceeds the 16KB golden"
    d = json.loads(body)
    assert d["cap"] == desk._QUEUE_CAP == 40
    # strata-first: one summary per authored class, in order
    assert [s["class"] for s in d["classes"]] == [c["class"] for c in desk._DESK_CLASSES]
    for s in d["classes"]:
        assert isinstance(s["count"], int) and s["count"] >= 0
        assert isinstance(s["by_project"], dict)
        assert s["verbs"] == desk._CLASS_VERBS[s["class"]]
        # ZONE 2 (consequences) rides the stratum — one truth per class
        assert isinstance(s["consequences"], dict)
    # ≤40 drill-down rows; the row cap is honoured
    assert len(d["rows"]) <= 40
    assert d["shown"] == len(d["rows"])
    assert d["truncated"] == (d["total"] > d["shown"])
    # the desk badge: author-gated asks only, and never more than the full sum
    assert d["his_move"] == sum(s["count"] for s in d["classes"] if s["owner"] == "him")
    assert 0 <= d["his_move"] <= d["total"]
    valid = {c["class"] for c in desk._DESK_CLASSES}
    for row in d["rows"]:
        assert {"class", "project", "id", "title", "context", "verbs", "href",
                "ts", "deeplinks", "fields"} <= set(row)
        assert row["class"] in valid                       # every row joins a real class
        assert row["verbs"] == desk._CLASS_VERBS[row["class"]]   # verbs are NAMES
        # TITLE LEGIBILITY (E3, 2026-07-21): plan-ops titles carry verb + object.key +
        # the note's first clause (three identical "REOPEN meta" rows must distinguish),
        # bounded ~120 chars — every other class stays at the original 80.
        title_cap = 120 if row["class"] == "plan-ops" else 80
        assert len(row["title"]) <= title_cap and len(row["context"]) <= 90
        assert isinstance(row["deeplinks"], list)          # ZONE 4 carried per row
    # rows are strata-ordered (a class never reappears after a later class began)
    order = {c["class"]: i for i, c in enumerate(desk._DESK_CLASSES)}
    seen_idx = [order[r["class"]] for r in d["rows"]]
    assert seen_idx == sorted(seen_idx), "desk rows are not strata-ordered"


def test_desk_405s_on_post_no_mutation_door():
    # the DESK READ-MODEL stays read-only: POST /desk/data is 405. The verbs act
    # through the SIBLING door POST /desk/act, never on the read path.
    status, _, body = desk.handle("/desk/data", {}, "POST", b"{}")
    assert status == 405
    assert "read-only" in json.loads(body)["error"]


# ── ZONE 2 — CONSEQUENCES: authored per (class, verb), honest absence otherwise ──

def test_consequences_model_covers_the_wired_verbs():
    # every WIRED verb (adjudications' six, plan-ops' two, work-orders' consume)
    # names what changes; the model is a per-(class,verb) dict, honest where absent.
    cq = desk._DECISION_CONSEQUENCES
    for v in desk._CLASS_VERBS["adjudications"]:
        assert cq["adjudications"].get(v), f"no consequence model for adjudications/{v}"
    for v in desk._CLASS_VERBS["plan-ops"]:
        assert cq["plan-ops"].get(v)
    assert cq["work-orders"].get("consume")
    # the strata carry the SAME model (one truth, read by every row's cockpit)
    strata = {s["class"]: s for s in json.loads(desk.handle("/desk/data", {}, "GET", b"")[2])["classes"]}
    assert strata["adjudications"]["consequences"] == cq["adjudications"]


# ── THE DESK ACT DOOR (POST /desk/act) ──────────────────────────────────────

def _act(payload: dict):
    return desk.handle("/desk/act", {}, "POST",
                       json.dumps(payload).encode("utf-8"))


def _manuscript(md: Path, feedback=None) -> Path:
    """A tmp manuscript dir with a resolvable S1 fragment + optional feedback
    ledger — the review_surface.adjudicate write target."""
    (md / "feedback").mkdir(parents=True, exist_ok=True)
    md.joinpath("main.tex").write_text(
        "\\documentclass{article}\\begin{document}\\input{S1}\\end{document}",
        encoding="utf-8")
    md.joinpath("S1.tex").write_text("Original body of section one.\n", encoding="utf-8")
    if feedback is not None:
        md.joinpath("feedback", "feedback.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in feedback), encoding="utf-8")
    return md


def _finding(fid="FB-1"):
    # the REAL annotate-door shape (manuscript_bridge.feedback_add): a note the author
    # banks rides ``by`` (an author actor) + ``comment``, with NO ``record`` and NO
    # ``source`` — the live shape the desk adjudications reader must surface (not the
    # ingest-era record:"finding"/source:"the-author" stub no annotate writer produces).
    return {"id": fid, "node_id": "S1", "kind": "eq-unused",
            "anchor": {"section": "S1"}, "comment": "c", "by": "gerard", "status": "open"}


def _strip(rec: dict) -> dict:
    r = {k: v for k, v in rec.items() if k not in ("id", "ts")}
    prov = {k: v for k, v in (r.get("provenance") or {}).items() if k != "ts"}
    if "provenance" in r:
        r["provenance"] = prov
    return r


def test_desk_act_is_post_only():
    status, _, _ = desk.handle("/desk/act", {}, "GET", b"{}")
    assert status == 405


def test_desk_act_bad_json_is_400():
    status, _, body = desk.handle("/desk/act", {}, "POST", b"{not json")
    assert status == 400
    status2, _, _ = desk.handle("/desk/act", {}, "POST", b"[]")
    assert status2 == 400            # a json array is not a payload object


def test_desk_act_unknown_class_and_verb_are_422():
    st, _, body = _act({"class": "no-such", "verb": "confirm", "by": "author"})
    assert st == 422 and "unknown desk class" in json.loads(body)["error"]
    st2, _, body2 = _act({"class": "adjudications", "verb": "explode", "by": "author"})
    assert st2 == 422
    assert json.loads(body2)["verbs"] == desk._CLASS_VERBS["adjudications"]


def test_desk_act_unattributed_is_422_zero_delta(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface as rs
    md = _manuscript(tmp_path / "wp", feedback=[_finding()])
    monkeypatch.setattr(rs, "manuscript_dir", lambda *a, **k: md)
    led = md / "feedback" / "feedback.jsonl"
    before = led.read_bytes()
    st, _, body = _act({"class": "adjudications", "verb": "confirm",
                        "project": "smoke", "finding_id": "FB-1"})   # NO `by`
    assert st == 422 and "by (explicit actor)" in json.loads(body)["error"]
    assert led.read_bytes() == before                               # ZERO ledger delta


def test_desk_act_happy_path_writes_the_same_record_as_the_executor(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface as rs
    fb = [_finding()]
    md_direct = _manuscript(tmp_path / "direct", feedback=fb)
    md_door = _manuscript(tmp_path / "door", feedback=fb)
    fields = {"finding_id": "FB-1", "node": "S1", "kind": "eq-unused"}
    direct = rs.adjudicate(md_direct, "smoke", {"by": "author", "verb": "confirm", **fields})
    assert direct["ok"]

    monkeypatch.setattr(rs, "manuscript_dir", lambda *a, **k: md_door)
    st, _, body = _act({"class": "adjudications", "verb": "confirm",
                        "project": "smoke", "by": "author", **fields})
    door = json.loads(body)
    assert st == 200 and door["ok"]
    # the door's record is the executor's record (minus the fresh id/ts) — no
    # second copy of the write, no reimplementation.
    assert _strip(door["record"]) == _strip(direct["record"])


def test_desk_act_double_fire_is_idempotent(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface as rs
    md = _manuscript(tmp_path / "wp", feedback=[_finding()])
    monkeypatch.setattr(rs, "manuscript_dir", lambda *a, **k: md)
    led = md / "feedback" / "feedback.jsonl"
    act = {"class": "adjudications", "verb": "confirm", "project": "smoke",
           "by": "author", "finding_id": "FB-1", "node": "S1", "kind": "eq-unused"}
    st1, _, b1 = _act(act)
    assert st1 == 200 and json.loads(b1)["ok"]
    n = len(led.read_text().splitlines())
    st2, _, b2 = _act(act)
    assert st2 == 200 and json.loads(b2).get("idempotent") is True
    assert len(led.read_text().splitlines()) == n                  # no double-write


def test_desk_act_unknown_target_is_refused(monkeypatch):
    st, _, body = _act({"class": "adjudications", "verb": "confirm",
                        "project": "no-such-corpus-xyz", "by": "author",
                        "finding_id": "FB-1"})
    assert st == 422 and "unknown project/corpus" in json.loads(body)["error"]


def test_desk_act_deferred_verb_is_failclosed():
    # release-states run/resume defer to W6 (the /pipeline run panel owns the launch door).
    st, _, body = _act({"class": "release-states", "verb": "run",
                        "project": "eigenengine", "by": "author"})
    d = json.loads(body)
    assert st == 422 and d["deferred_to"].startswith("W6")
    assert d["class"] == "release-states" and d["verb"] == "run"
    # the PSU-guarded rebuild is deferred too, honestly named.
    st2, _, body2 = _act({"class": "stale-reads", "verb": "rebuild", "by": "author"})
    assert st2 == 422 and "PSU" in json.loads(body2)["deferred_to"]


def test_desk_act_revoke_intent_unknown_is_idempotent_noop(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface as rs
    md = _manuscript(tmp_path / "wp", feedback=[])
    monkeypatch.setattr(rs, "manuscript_dir", lambda *a, **k: md)
    led = md / "feedback" / "feedback.jsonl"
    before = led.read_bytes()
    st, _, body = _act({"class": "plan-ops", "verb": "revoke-intent",
                        "project": "smoke", "by": "author",
                        "supersedes": "NO-SUCH-INTENT"})
    d = json.loads(body)
    assert st == 200 and d.get("idempotent") is True               # honest no-op
    assert led.read_bytes() == before                              # zero delta


def test_desk_act_ratify_runs_the_c35_apply_bridge_and_is_idempotent(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface as rs
    from laplace.web import shared_ui as su
    from laplace.pipeline import adjudicate as adj
    APPLY = "apply-bridge-desk"
    plan = {"meta": {"project": APPLY, "weighting": "even across sections",
                     "target_dir": ""},
            "sections": [{"id": "S1", "title": "Intro", "job": "open",
                          "nodes_in_order": ["a"], "beats": [], "figures": [],
                          "refs": []}],
            "appendices": []}
    p = tmp_path / "projection_plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(su, "plan_path_for", lambda corpus: p)

    md = tmp_path / "wp"
    (md / "feedback").mkdir(parents=True)
    intent = adj.make_projection_intent("FB-w", "DEMOTE", object_kind="meta",
                                        object_key="weighting", note="lower it",
                                        finding_kind="emphasis-mismatch", project=APPLY)
    (md / "feedback" / "feedback.jsonl").write_text(json.dumps(intent) + "\n",
                                                    encoding="utf-8")
    monkeypatch.setattr(rs, "manuscript_dir", lambda *a, **k: md)

    act = {"class": "plan-ops", "verb": "ratify", "project": APPLY, "by": "gerard"}
    st, _, body = _act(act)
    d = json.loads(body)
    assert st == 200 and d["ok"]
    assert [x["intent"] for x in d["applied"]] == [intent["id"]]   # the C3.5 apply
    assert d["idempotent"] is False
    # re-fire: the consumed intent is retired, so a second ratify applies nothing.
    st2, _, body2 = _act(act)
    d2 = json.loads(body2)
    assert st2 == 200 and d2["applied"] == [] and d2["idempotent"] is True


# ── the eleven joins over real stores (fabricated / emptied / one-emptied) ───

def _synthetic_repo(tmp_path):
    """A repo skeleton with one populated store per class — the fabricated-row fixture."""
    from laplace.pipeline import registry as _registry

    fb = tmp_path / "feedback.jsonl"
    fb.write_text("\n".join(json.dumps(r) for r in [
        # the REAL annotate-door shape: an author note rides by-actor + comment, its
        # section on ``anchor.section``, NO record/source (what feedback_add emits).
        {"id": "FB-A", "project": "synthetic", "ts": "2026-07-13T09:00:00",
         "node_id": "", "kind": "note", "anchor": {"section": "main"},
         "comment": "his annotate-door finding", "by": "gerard", "status": "open"},
        {"id": "PI-1", "record": "projection-intent", "project": "synthetic",
         "ts": "2026-07-13T10:00:00", "verb": "CUT", "object": {"kind": "section", "sid": "sec-a"},
         "payload": {"note": "cut it"}, "status": "open", "source": "eigen:relay"},
    ]) + "\n")
    proj = _registry.Project(name="synthetic", kind="tex", feedback_ledger="feedback.jsonl")

    (tmp_path / "corpus_friction").mkdir(exist_ok=True)
    (tmp_path / "corpus_friction" / "open_stack_forks.jsonl").write_text(json.dumps(
        {"id": "F99", "kind": "open-stack-fork", "stratum": 1, "render_owned": True,
         "title": "A live fork awaiting his ruling", "opened": "2026-07-13",
         "recurrence": "1", "status": "\U0001f534", "trigger": "notes"}) + "\n")

    (tmp_path / "proxy_verdicts.jsonl").write_text(json.dumps(
        {"id": "PV-1", "kind": "derived-fork", "question": "which writer?",
         "ruling": "the transition entry", "contested": None, "date": "2026-07-13"}) + "\n")

    cf = tmp_path / "corpus_friction"
    cf.mkdir(exist_ok=True)
    (cf / "dream_lifts_2026-07-13.json").write_text(json.dumps(
        {"kind": "dream-lifts", "date": "2026-07-13", "status": "PROPOSED — awaiting authorization",
         "proposals": [{"region": "src/laplace", "proposed_slug": "a-lift",
                        "judgment": "coherent — worth forging"}]}))

    (cf / "synthetic.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"id": "FR-1", "kind": "friction", "node": "n1", "where": "x",
         "chain": ["global goal", "sub goal", "action a"]},
        {"id": "FR-2", "kind": "friction", "node": "n2", "where": "y",
         "chain": ["global goal", "sub goal", "action b"]},
    ]) + "\n")

    (tmp_path / "holdout").mkdir()
    (tmp_path / "holdout" / "PREDICTION_pending.json").write_text(json.dumps(
        {"note": "n", "banked": "2026-07-13T01:00:00", "session": "s",
         "mechanical": [{"id": "m1", "claim": "c"}], "behavioral": [{"id": "b1", "claim": "c"}]}))

    return proj


def _counts(d):
    return {s["class"]: s["count"] for s in d["classes"]}


def test_desk_fabricated_store_rows_appear(tmp_path, monkeypatch):
    proj = _synthetic_repo(tmp_path)
    monkeypatch.setattr(desk.registry, "all_projects", lambda: {"synthetic": proj})

    d = desk._desk(tmp_path)
    n = _counts(d)
    assert n["adjudications"] == 1
    assert n["plan-ops"] == 1
    assert n["forks"] == 1
    assert n["proxy-drafts"] == 1
    assert n["lifts"] == 1
    assert n["open-frictions"] == 2
    assert n["recurrence-clusters"] == 1          # the two frictions share a chain prefix
    assert n["holdout"] == 1
    assert n["release-states"] == 1               # synthetic is NEVER_RUN → needs a move
    ids = {r["id"] for r in d["rows"]}
    assert {"FB-A", "PI-1", "F99", "PV-1", "a-lift", "FR-1", "FR-2", "holdout-pending"} <= ids
    # stale-reads JOINS the real staleness store: its count == the degraded reads there
    from laplace.web import shared_ui
    degraded = sum(1 for r in shared_ui.staleness("", repo_root=tmp_path)["reads"] if r["degraded"])
    assert n["stale-reads"] == degraded


def test_desk_emptied_stores_drop_their_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(desk.registry, "all_projects", lambda: {})
    d = desk._desk(tmp_path)
    n = _counts(d)
    for cls in ("adjudications", "plan-ops", "forks", "proxy-drafts", "lifts",
                "open-frictions", "recurrence-clusters", "holdout", "release-states"):
        assert n[cls] == 0, f"{cls} did not drop to zero on an emptied store"
    dropped = {"adjudications", "plan-ops", "forks", "proxy-drafts", "lifts",
               "open-frictions", "recurrence-clusters", "holdout", "release-states"}
    assert not [r for r in d["rows"] if r["class"] in dropped]


def test_desk_one_emptied_store_drops_only_its_own_rows(tmp_path, monkeypatch):
    proj = _synthetic_repo(tmp_path)
    (tmp_path / "feedback.jsonl").write_text("")          # empty the feedback store only
    monkeypatch.setattr(desk.registry, "all_projects", lambda: {"synthetic": proj})
    n = _counts(desk._desk(tmp_path))
    assert n["adjudications"] == 0 and n["plan-ops"] == 0
    assert n["forks"] == 1 and n["proxy-drafts"] == 1 and n["open-frictions"] == 2


def test_desk_adjudications_are_author_sourced_not_machine(tmp_path, monkeypatch):
    """The crank's finding-5, made a regression: the adjudications stratum surfaces what
    the LIVE writers produce — a finding banked through the ANNOTATE door
    (manuscript_bridge.feedback_add: by-actor + comment, NO record/source) AND a relayed
    ``the-author`` finding — but NEVER a machine mech-panel finding (record:"finding" + a
    machine source), which is the converge loop's, not his desk. Driven through the REAL
    writer, so no stub-only shape stands in for the door's output."""
    from laplace.pipeline import registry as _registry
    from laplace.manuscript import manuscript_bridge as mb

    fb = tmp_path / "feedback.jsonl"
    # (1) a REAL annotate-door finding — minted by the live writer, never hand-stubbed.
    minted = mb.feedback_add(tmp_path, "synthetic",
                             {"node_id": "S1", "comment": "his note", "kind": "note",
                              "by": "gerard"}, ledger=fb)
    door_id = minted["record"]["id"]
    # (2) a relayed the-author finding (author-origin) + (3) a machine mech-panel finding.
    with fb.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": "REL-1", "record": "finding", "status": "open",
                            "kind": "note", "section": "main", "text": "relayed",
                            "source": "the-author:relayed-desk-review:2026-07-13"}) + "\n")
        f.write(json.dumps({"id": "MECH-1", "record": "finding", "status": "open",
                            "kind": "apparatus", "section": "S2", "text": "machine flag",
                            "source": "mech-panel:round7:apparatus"}) + "\n")

    proj = _registry.Project(name="synthetic", kind="tex", feedback_ledger="feedback.jsonl")
    monkeypatch.setattr(desk.registry, "all_projects", lambda: {"synthetic": proj})
    adj, _ops = desk._desk_feedback(tmp_path)
    ids = {r["id"] for r in adj["rows"]}
    assert door_id in ids, "the live annotate-door finding must surface on the desk"
    assert "REL-1" in ids, "a relayed the-author finding is still author-origin"
    assert "MECH-1" not in ids, "a machine mech-panel finding is never his adjudication"
    assert adj["count"] == 2                            # the annotate-door row + the relay row
    door = next(r for r in adj["rows"] if r["id"] == door_id)
    assert door["fields"]["kind"] == "note" and "his note" in door["context"]


def test_desk_byte_cap_is_structural_not_data_dependent(tmp_path, monkeypatch):
    cf = tmp_path / "corpus_friction"
    cf.mkdir()
    big = [{"id": f"FR-{i}", "kind": "friction", "node": f"node-{i}",
            "where": "x" * 200, "note": "y" * 200} for i in range(500)]
    (cf / "big.jsonl").write_text("\n".join(json.dumps(r) for r in big) + "\n")
    monkeypatch.setattr(desk.registry, "all_projects", lambda: {})
    monkeypatch.setattr(desk, "_REPO_ROOT", tmp_path)
    status, _, body = desk.handle("/desk/data", {}, "GET", b"")
    assert status == 200
    d = json.loads(body)
    assert len(body) <= 16 * 1024
    assert len(d["rows"]) <= 40
    assert d["classes"][5]["count"] == 500       # the count is honest (open-frictions)
    assert d["truncated"] is True


# ── ZONE 3+4 — door-ready fields + deep-links onto the WORKING surfaces ──────

def test_desk_rows_carry_door_ready_fields(tmp_path, monkeypatch):
    proj = _synthetic_repo(tmp_path)
    monkeypatch.setattr(desk.registry, "all_projects", lambda: {"synthetic": proj})
    rows = {r["id"]: r for r in desk._desk(tmp_path)["rows"]}

    for r in rows.values():
        assert isinstance(r.get("fields"), dict)

    adj = rows["FB-A"]
    assert adj["class"] == "adjudications"
    assert adj["fields"]["finding_id"] == "FB-A"
    assert adj["fields"]["kind"] == "note"
    assert adj["fields"]["section"] == "main"
    assert "node" in adj["fields"]                       # present even when empty

    ops = rows["PI-1"]
    assert ops["class"] == "plan-ops"
    assert ops["fields"]["supersedes"] == "PI-1"


def test_desk_wired_rows_deeplink_onto_the_working_surfaces(tmp_path, monkeypatch):
    proj = _synthetic_repo(tmp_path)
    monkeypatch.setattr(desk.registry, "all_projects", lambda: {"synthetic": proj})
    rows = {r["id"]: r for r in desk._desk(tmp_path)["rows"]}

    # the adjudications row deep-links into /artefact (the reader/annotator) at the
    # finding's section (no node on this fixture → section only) — never a front door.
    assert rows["FB-A"]["href"] == "/artefact?corpus=synthetic&section=main"
    # its deeplinks carry the spine locations onto the working surfaces.
    dl = {d["href"].split("?")[0].split("#")[0] for d in rows["FB-A"]["deeplinks"]}
    assert "/artefact" in dl and "/storyboard" in dl
    # the plan-ops row lands on the storyboard at the intent object's sid anchor.
    assert rows["PI-1"]["href"] == "/storyboard?corpus=synthetic#sec-a"


def test_artefact_href_url_encodes_the_anchor():
    # a node id carries a ':' (def:foo) — the params must be encoded so the deep-link
    # is a single well-formed query, never a split/dead anchor.
    href = desk._artefact_href("subset-sum", "def:spectral-signal")
    assert href == "/artefact?corpus=subset-sum&node=def%3Aspectral-signal"
    assert desk._artefact_href("wp") == "/artefact?corpus=wp"      # no anchor → bare


def test_desk_no_row_href_is_a_dead_anchor(tmp_path, monkeypatch):
    # every href a row offers must resolve to a REAL scanner route (no 404/dead anchor).
    # engine classes with no spine surface carry href "" (honest, not a dead link).
    proj = _synthetic_repo(tmp_path)
    monkeypatch.setattr(desk.registry, "all_projects", lambda: {"synthetic": proj})
    src = _SCANNER_PY.read_text(encoding="utf-8")
    for r in desk._desk(tmp_path)["rows"]:
        for link in ([{"href": r["href"]}] if r["href"] else []) + list(r.get("deeplinks") or []):
            href = link["href"]
            if not href:
                continue
            route = href.split("#", 1)[0].split("?", 1)[0]
            assert f'"{route}"' in src, f"row {r['id']!r} deep-links to a non-route {route!r}"


def test_batch_verbs_are_arm_to_fire_in_the_cockpit_module():
    """ratify batch-applies EVERY open projection-intent for the corpus (the C3.5 executor
    has no per-intent variant). A batch verb must never fire on a single click: it belongs
    to DESTRUCTIVE (arm-to-fire) with a label that names the batch semantics honestly."""
    mjs = (_REPO_ROOT / "src/laplace/web/static_shared/desk-panes.mjs").read_text(encoding="utf-8")
    block = mjs.split("DESTRUCTIVE = {", 1)[1].split("};", 1)[0]
    assert '"ratify"' in block, "ratify must be arm-to-fire (it is a batch apply)"
    assert "EVERY open plan intent" in block  # the label tells the batch truth


# ── ZONE 1 — the referent: the FULL renderable CONTEXT, inline, untruncated ──

def test_referent_serves_the_full_context_for_an_adjudication(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface as rs
    md = _manuscript(tmp_path / "wp", feedback=[_finding("FB-9")])
    # a verbatim source document under feedback/sources — the chair's P6 fix: the ruling
    # reads the document from where the ruling happens (not a truncated one-liner).
    (md / "feedback" / "sources").mkdir(parents=True, exist_ok=True)
    long_body = "# The outside judgement\n\n" + ("A substantial paragraph of judgement prose. " * 40)
    (md / "feedback" / "sources" / "2026-07-13_judgement.md").write_text(long_body, encoding="utf-8")
    monkeypatch.setattr(rs, "manuscript_dir", lambda *a, **k: md)

    ref = desk._referent("adjudications", "wp", "FB-9",
                         {"node": "S1", "kind": "eq-unused", "section": "S1"})
    # the exact ledger row is present (the finding, verbatim)
    assert ref["ledger_row"]["id"] == "FB-9"
    # the source document is rendered inline — heading + FULL body, never truncated
    sd = ref["source_doc"]
    assert sd and sd["heading"] == "The outside judgement"
    assert len(sd["body"]) == len(long_body)            # the WHOLE document, not a one-liner
    assert "2026-07-13_judgement.md" in sd["path"]
    assert ref["anchor"] == {"node": "S1", "section": "S1"}


def test_referent_endpoint_validates_class_and_serves_json(tmp_path, monkeypatch):
    from laplace.manuscript import review_surface as rs
    md = _manuscript(tmp_path / "wp", feedback=[_finding("FB-3")])
    monkeypatch.setattr(rs, "manuscript_dir", lambda *a, **k: md)
    # unknown class → 422
    st, _, body = desk.handle("/desk/referent", {"class": ["no-such"]}, "GET", b"")
    assert st == 422 and "unknown desk class" in json.loads(body)["error"]
    # a real adjudication referent → 200 with the ledger row
    st2, ctype, body2 = desk.handle(
        "/desk/referent",
        {"class": ["adjudications"], "project": ["wp"], "id": ["FB-3"],
         "node": ["S1"], "kind": ["eq-unused"], "section": ["S1"]}, "GET", b"")
    assert st2 == 200 and "json" in ctype
    assert json.loads(body2)["ledger_row"]["id"] == "FB-3"


# ── W5 · PROXY-DRAFTS: the adjudicator's output surfaced, confirm/reject wired ───────────

def _proxy_ledger(repo: Path, *recs) -> None:
    (repo / "proxy_verdicts.jsonl").write_text(
        "\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


def test_proxy_referent_surfaces_the_adjudicators_own_output(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "_REPO_ROOT", tmp_path)
    _proxy_ledger(tmp_path, {"id": "PV-9", "kind": "derived-fork",
                             "question": "which writer owns the transition entry?",
                             "ruling": "the storyboard writer", "confidence": "firm",
                             "evidence": ["the beat sits in the plan"], "date": "2026-07-14"})
    ref = desk._referent("proxy-drafts", "engine", "PV-9", {"id": "PV-9", "target": "PV-9"})
    v = ref["proxy_verdict"]
    assert v["question"] == "which writer owns the transition entry?"
    assert v["ruling"] == "the storyboard writer" and v["confidence"] == "firm"
    # an id with no verdict → honest absence, never a crash
    miss = desk._referent("proxy-drafts", "engine", "PV-404", {"id": "PV-404"})
    assert "error" in miss and "PV-404" in miss["error"]


def test_proxy_reject_contests_and_drops_the_row(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "_REPO_ROOT", tmp_path)
    v = {"id": "PV-9", "kind": "derived-fork", "question": "q?", "ruling": "r",
         "confidence": "firm", "contested": None, "date": "2026-07-14"}
    _proxy_ledger(tmp_path, v)
    assert desk._desk_proxy(tmp_path)["count"] == 1               # open before the ruling
    # reject is an AUTHORING verb (PV the-ruling-needs-a-composer): the payload carries HIS
    # WORDS, so the door's authoring guard passes and the contest reaches author_proxy.
    st, _, body = _act({"class": "proxy-drafts", "verb": "reject", "target": "PV-9",
                        "by": "author",
                        "ruling": "the transition entry is the beat writer's, not the "
                                  "storyboard's — the plan names the beat"})
    d = json.loads(body)
    assert st == 200 and d["ok"] and d["record"]["kind"] == "contest"
    assert d["record"]["contests"] == "PV-9"
    assert desk._desk_proxy(tmp_path)["count"] == 0              # contested → off the desk


def test_proxy_confirm_appends_and_drops_the_row(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "_REPO_ROOT", tmp_path)
    _proxy_ledger(tmp_path, {"id": "PV-9", "kind": "derived-fork", "question": "q?",
                             "ruling": "r", "confidence": "firm", "date": "2026-07-14"})
    st, _, body = _act({"class": "proxy-drafts", "verb": "confirm",
                        "target": "PV-9", "by": "author"})
    d = json.loads(body)
    assert st == 200 and d["ok"] and d["record"]["kind"] == "confirm"
    assert d["record"]["confirms"] == "PV-9"
    assert desk._desk_proxy(tmp_path)["count"] == 0             # affirmed → leaves the queue


def test_proxy_verb_without_target_is_failclosed(tmp_path, monkeypatch):
    monkeypatch.setattr(desk, "_REPO_ROOT", tmp_path)
    # words present (so the authoring guard is satisfied and cannot mask this), target absent:
    # the per-verb target check downstream is what must refuse.
    st, _, body = _act({"class": "proxy-drafts", "verb": "reject", "by": "author",
                        "ruling": "this verdict does not hold"})
    assert st == 422 and "target required" in json.loads(body)["error"]


def test_proxy_reject_without_his_words_is_refused_and_banks_nothing(tmp_path, monkeypatch):
    # THE AUTHORING GUARD (PV the-ruling-needs-a-composer): reject is one of his authoring
    # verbs, so a targeted-but-WORDLESS rejection is refused at the door — 422 naming what
    # it needs, BEFORE any executor, with ZERO ledger delta. A wordless "rejected on the
    # desk" must never be banked.
    monkeypatch.setattr(desk, "_REPO_ROOT", tmp_path)
    _proxy_ledger(tmp_path, {"id": "PV-9", "kind": "derived-fork", "question": "q?",
                             "ruling": "r", "confidence": "firm", "date": "2026-07-14"})
    ledger = tmp_path / "proxy_verdicts.jsonl"
    before = ledger.read_bytes()
    st, _, body = _act({"class": "proxy-drafts", "verb": "reject",
                        "target": "PV-9", "by": "author"})
    d = json.loads(body)
    assert st == 422 and d["needs"] == "ruling"
    assert ledger.read_bytes() == before                        # zero delta: nothing banked
    assert desk._desk_proxy(tmp_path)["count"] == 1             # the row stays on the desk


def test_proxy_amend_is_the_compose_door_not_a_blind_write():
    # amend is a COMPOSE verb (client renders a nav link into the in-place mouth); the door
    # never writes for it — a POST is a fail-closed 422 naming where the compose lands.
    assert ("proxy-drafts", "amend") in desk._DEFERRED_VERBS
    st, _, body = _act({"class": "proxy-drafts", "verb": "amend",
                        "target": "PV-9", "by": "author"})
    assert st == 422 and "compose" in json.loads(body)["deferred_to"]
