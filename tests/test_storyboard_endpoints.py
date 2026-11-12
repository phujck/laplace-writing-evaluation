"""The storyboard's capability endpoints - the pipeline operators as routes.

The contracts under test: PREVIEW NEVER MUTATES (restructure dry-run and the
propagate report byte-preserve every ledger and the plan), APPLY IS
TRANSACTIONED (an injected failure after the spine leg truncates the L1 suffix
back - ledgers byte-identical), the propagate route serves the LIVE 37-item
typed worklist for subset-sum-itqde, and an unknown corpus is a 404-shaped
error on every new route. handle() is called directly, as test_storyboard.py
does - the scanner owns HTTP, the handler owns the contract.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.manuscript import storyboard as sb

RR = Path(__file__).resolve().parent.parent
MS = RR / "synthetics papers" / "subset-sum-itqde" / "manuscript"
CORPUS = "subset-sum-itqde"


def _get(path: str, **params):
    return sb.handle(path, {k: [v] for k, v in params.items()}, "GET", b"")


def _post(path: str, body: dict | None = None, **params):
    return sb.handle(path, {k: [v] for k, v in params.items()}, "POST",
                     json.dumps(body if body is not None else {}).encode("utf-8"))


def _json(res) -> tuple[int, dict]:
    status, ctype, payload = res
    assert ctype.startswith("application/json")
    return status, json.loads(payload)


def _identity_arc(plan: dict) -> dict:
    """Every section seeded from itself - the no-op restructure."""
    return {"sections": [{"id": s["id"], "title": s.get("title"),
                          "seed_from": [s["id"]], "beats": list(s.get("beats") or []),
                          "job": s.get("job") or ""} for s in plan.get("sections") or []],
            "refs": {"carry": {s["id"]: [s["id"]] for s in plan.get("sections") or []}}}


def _watched() -> list[Path]:
    """Every ledger + plan file a pure endpoint must byte-preserve."""
    plan_p = MS / "projection_plan.json"
    return [p for p in (plan_p,
                        RR / "corpus_friction" / f"{CORPUS}.jsonl",
                        plan_p.with_name("projection_plan.friction.jsonl"),
                        plan_p.with_name("projection_plan.base.json"),
                        MS / "whitepaper" / "feedback" / "feedback.jsonl")
            if p.is_file()]


# ---------------------------------------------------------------------------
# GET /storyboard/plan - the board's own enriched_plan, meta.contribution_rank
# threaded additively (the authored spine the return path pivots on)
# ---------------------------------------------------------------------------

def test_board_plan_meta_carries_the_authored_contribution_rank():
    """The board payload (GET /storyboard/plan) grows the fifth meta key additively.
    W-SB (2026-07-22): the weighting-card-grounding-visible floor requires each rank
    card to be GROUNDED server-side, so the primary/excluded entries are no longer raw
    strings but structured dicts carrying (claim, role, rank, source nodes, the why) —
    the client renders each card's grounding in place and never regexes {#id} back out.
    subset-sum-itqde's real rank is 3 primary + 1 excluded (the planted-hardness entry,
    role exploratory-excluded); every card names a non-empty source with a why."""
    status, out = _json(_get("/storyboard/plan", corpus=CORPUS))
    assert status == 200
    assert set(out["meta"]) == {"project", "artefact", "form", "target_dir", "contribution_rank"}
    rank = out["meta"]["contribution_rank"]
    assert len(rank["primary"]) == 3
    assert len(rank["excluded"]) == 1
    excl = rank["excluded"][0]
    assert isinstance(excl, dict) and "planted hardness" in excl["claim"]
    # the grounding floor: every card is a dict carrying non-empty source nodes + a why.
    for card in rank["primary"] + rank["excluded"]:
        assert isinstance(card, dict) and card.get("nodes") and card.get("why"), card


# ---------------------------------------------------------------------------
# GET /storyboard/coverage - THE COVERAGE INVERSE (spine §4 link 4). The clause:
# the rendered counts NEVER under-report the stores' own truth (spine §6).
# ---------------------------------------------------------------------------

def _direct_coverage_truth() -> tuple[int, int]:
    """Recompute the two prose-without-stock counts DIRECTLY from the narrative +
    prose_provenance stores - an independent second reader the endpoint is checked
    against, so a silently-shrinking count is caught."""
    from laplace.pipeline import registry, narrative, schema
    from laplace.pipeline import document_model as dm
    plan = registry.resolve(CORPUS).read_plan()
    by_plan = by_fact = 0
    for sec in schema.plan_sections(plan):
        sid = sec.get("id")
        if not sid:
            continue
        nspec = narrative.load_section(CORPUS, sid)
        for para in (nspec or {}).get("paragraphs") or []:
            if not (para.get("input_nodes") or []):
                by_plan += 1
        for rec in (dm.load_provenance(CORPUS, sid) or []):
            if not (rec.get("nodes_realised") or []):
                by_fact += 1
    return by_plan, by_fact


def test_coverage_inverse_never_under_reports_the_stores():
    """THE COVERAGE-INVERSE CLAUSE (spine §6): GET /storyboard/coverage renders two
    counts - prose_by_plan (narrative beats with an empty input-node set) and
    prose_by_fact (realised paragraphs whose prose_provenance is empty). Each must
    equal the store's own truth (computed here independently) and, above all, NEVER
    under-report it - the desk-rejection failure mode ('JUDGE SILENCE IS NOT
    MANUSCRIPT QUALITY') made a mechanical count."""
    status, out = _json(_get("/storyboard/coverage", corpus=CORPUS))
    assert status == 200 and out["ok"] is True
    truth_plan, truth_fact = _direct_coverage_truth()
    got_plan = out["prose_by_plan"]["count"]
    got_fact = out["prose_by_fact"]["count"]
    # the clause: the interface never under-reports (equality is the honest case)
    assert got_plan >= truth_plan, f"prose_by_plan UNDER-REPORTS: {got_plan} < {truth_plan}"
    assert got_fact >= truth_fact, f"prose_by_fact UNDER-REPORTS: {got_fact} < {truth_fact}"
    assert got_plan == truth_plan and got_fact == truth_fact
    # every counted offender carries its (section, paragraph) so the board doors one click deep
    for o in out["prose_by_plan"]["offenders"] + out["prose_by_fact"]["offenders"]:
        assert o.get("section") and o.get("paragraph")
    assert len(out["prose_by_plan"]["offenders"]) == got_plan
    assert len(out["prose_by_fact"]["offenders"]) == got_fact


def test_coverage_and_arc_reject_unknown_corpus():
    """The two new reads fail 404-shaped on an unknown corpus (no plan)."""
    st_c, out_c = _json(_get("/storyboard/coverage", corpus="no-such-corpus"))
    assert st_c == 404 and "no projection plan" in out_c["error"]
    st_a, out_a = _json(_get("/storyboard/arc", corpus="no-such-corpus"))
    assert st_a == 404 and "no projection plan" in out_a["error"]


def test_current_arc_is_the_identity_reshape():
    """GET /storyboard/arc is the editable STARTING POINT: each section seeded from
    its own id, so dry-running it reproduces the plan (the restructure door's
    pre-fill)."""
    status, out = _json(_get("/storyboard/arc", corpus=CORPUS))
    assert status == 200
    plan = sb._load_plan(CORPUS)[1]
    assert [s["id"] for s in out["sections"]] == [s["id"] for s in plan.get("sections") or []]
    for s in out["sections"]:
        assert s["seed_from"] == [s["id"]]


def test_board_renders_the_grounded_weighting_in_the_engine():
    """DOM-less render-side check (no browser). W-SB (2026-07-22) rebuilt the storyboard
    AS AN ENGINE INSTRUMENT: the surface rests at a composed BRIEF and materialises cards
    on focus. The narrative weighting is no longer a horizontal top strip (#sb-rank, retired)
    — it is a materialised set of GROUNDED cards. ``renderRank`` (kept by contract name for
    cards-expand-in-place-with-context) builds each weighting card from the server-grounded
    ``BRIEF.weighting`` (source nodes + the why, rendered in place) and, on open, REALLOCATES
    around the examined card (pinWeighting) — never a context-free jump (no openNode /
    revealSection in the renderRank block). The pane rides engine.mjs and rests composed."""
    html = (Path(sb.__file__).parents[1] / "web" / "storyboard.html").read_text(encoding="utf-8")
    assert 'id="eng-root"' in html and 'class="eng-brief"' in html   # the engine root + brief altitude
    assert "storyboard-panes.mjs" in html
    mjs = (Path(sb.__file__).parents[1] / "web" / "static_shared" / "storyboard-panes.mjs").read_text(encoding="utf-8")
    assert "engine.mjs" in mjs                                        # the surface rides the focus runtime
    assert "function renderRank(mat)" in mjs                          # the weighting materialiser, kept by name
    block = mjs.split("function renderRank(mat)", 1)[1].split("\nfunction ", 1)[0]
    assert "openNode(" not in block and "revealSection(" not in block   # expands in place, never jumps
    assert "pinWeighting(" in block                                   # opening a card reallocates around it
    assert "groundBlock(" in mjs and "grounding · the nodes it draws from" in mjs   # grounding rendered in place
    assert "BRIEF.weighting" in mjs                                   # cards read the server-grounded rank


# ---------------------------------------------------------------------------
# restructure - preview never mutates; refusals verbatim; apply transactioned
# ---------------------------------------------------------------------------

def test_restructure_preview_mutates_nothing():
    plan = json.loads((MS / "projection_plan.json").read_text(encoding="utf-8"))
    before = {p: p.read_bytes() for p in _watched()}
    assert len(before) >= 3
    listing = sorted(p.name for p in MS.iterdir())

    status, out = _json(_post("/storyboard/restructure", _identity_arc(plan),
                              corpus=CORPUS))
    assert status == 200 and out["ok"] is True and out["applied"] is False
    # the summary is the decision surface: sequence + counts + verdicts
    assert [s["id"] for s in out["sections"]] == [s["id"] for s in plan["sections"]]
    assert all({"n_nodes", "n_beats", "n_refs", "n_figures"} <= set(s)
               for s in out["sections"])
    assert out["validation"].get("pass") is True
    assert {d["class"] for d in out["dirty"]["sections"]} == {"cheap"}
    assert out["n_spine_payloads"] == 0
    assert "new_plan" not in out and "spine_payloads" not in out   # board-sized

    for p, b in before.items():
        assert p.read_bytes() == b, f"preview wrote {p}"
    assert sorted(p.name for p in MS.iterdir()) == listing   # no sidecars minted


def test_restructure_refusal_comes_back_verbatim_and_pure():
    before = {p: p.read_bytes() for p in _watched()}
    status, out = _json(_post("/storyboard/restructure",
                              {"sections": [{"id": "Z1", "title": "Z", "seed_from": []}]},
                              corpus=CORPUS))
    assert status == 422 and out["ok"] is False
    assert "stray" in out["error"]              # the operator's own words
    for p, b in before.items():
        assert p.read_bytes() == b


def test_restructure_apply_rolls_back_on_injected_failure(monkeypatch):
    """The transaction contract: the endpoint writes the arc's spine payloads
    into L1 FIRST; a failure in execute(apply) must truncate that suffix back,
    leaving every ledger byte-identical."""
    plan = json.loads((MS / "projection_plan.json").read_text(encoding="utf-8"))
    l1 = RR / "corpus_friction" / f"{CORPUS}.jsonl"
    before = {p: p.read_bytes() for p in _watched()}

    seen: dict = {}
    from laplace.pipeline import restructure as rmod

    def boom(project, arc, dry_run=True, repo_root=None):
        seen["dry_run"] = dry_run
        # the spine leg must already have landed when execute runs
        seen["l1_grew"] = l1.stat().st_size > len(before[l1])
        raise RuntimeError("injected: apply fails after the spine leg")

    monkeypatch.setattr(rmod, "execute", boom)
    beats = [b for s in plan["sections"] for b in (s.get("beats") or [])][:3]
    assert beats, "the live plan is expected to carry beats"
    arc = {**_identity_arc(plan), "spine": {"order": beats}}

    status, out = _json(_post("/storyboard/restructure", arc,
                              corpus=CORPUS, apply="1"))
    assert status == 422 and out["ok"] is False and out.get("rolled_back") is True
    assert "injected" in out["error"]
    assert seen == {"dry_run": False, "l1_grew": True}
    for p, b in before.items():
        assert p.read_bytes() == b, f"rollback left {p} changed"


def test_restructure_apply_refusal_report_rolls_back_too(monkeypatch):
    """execute returning ok:False (a refused arc) must also unwind the spine
    suffix - the not-ok report travels out, the bytes travel back."""
    plan = json.loads((MS / "projection_plan.json").read_text(encoding="utf-8"))
    before = {p: p.read_bytes() for p in _watched()}
    from laplace.pipeline import restructure as rmod
    monkeypatch.setattr(rmod, "execute",
                        lambda *a, **k: {"ok": False, "error": "restructure refused: synthetic"})
    beats = [b for s in plan["sections"] for b in (s.get("beats") or [])][:2]
    arc = {**_identity_arc(plan), "spine": {"order": beats}}
    status, out = _json(_post("/storyboard/restructure", arc, corpus=CORPUS, apply="1"))
    assert status == 422 and out["ok"] is False and out.get("rolled_back") is True
    assert out["error"] == "restructure refused: synthetic"
    for p, b in before.items():
        assert p.read_bytes() == b


# ---------------------------------------------------------------------------
# propagate - the live worklist through the route, pure
# ---------------------------------------------------------------------------

def test_propagate_endpoint_returns_the_live_worklist():
    before = {p: p.read_bytes() for p in _watched()}
    status, out = _json(_get("/storyboard/propagate", corpus=CORPUS))
    assert status == 200

    # the standing WK-050 residue as a SUBSET (same repin as
    # test_pipeline_propagate, 2026-07-10): the ledger legitimately grows with
    # live convergence use, so presence is asserted, never exact totals.
    assert len(out["worklist"]) >= 2
    assert out["comments_routed"] >= 5
    assert any(w.get("target") == "irf:retained-overlap-budget"
               for w in out["worklist"])
    from laplace.pipeline import schema
    for w in out["worklist"]:
        assert set(schema.WORK_ITEM_FIELDS) <= set(w)
    # the typed DAG arrives ordered: every blocker precedes its dependant
    ids = {w["id"] for w in out["worklist"]}
    seen: set = set()
    for w in out["worklist"]:
        assert set(w["blocked_by"]) & ids <= seen, w["id"]
        seen.add(w["id"])
    # dirty map + minimum dispatch carried whole
    assert set(out["minimum_dispatch"]) >= {w["section"] for w in out["worklist"]
                                            if w["kind"] == "derive"}
    assert all(v["class"] in ("cheap", "expensive", None)
               for v in out["sections"].values())

    for p, b in before.items():
        assert p.read_bytes() == b, f"propagate GET wrote {p}"


def test_propagate_endpoint_since_mark_and_bad_mark():
    status, out = _json(_get("/storyboard/propagate", corpus=CORPUS, since="0"))
    assert status == 200 and out["since"] == "0" and out["changeset"] > 0
    status, out = _json(_get("/storyboard/propagate", corpus=CORPUS, since="RW-nope"))
    assert status == 400 and "RW-nope" in out["error"]


# ---------------------------------------------------------------------------
# dispatch - the wiring, stubbed so the test writes nothing
# ---------------------------------------------------------------------------

def _canned_worklist() -> list[dict]:
    return [
        {"id": "WK-1-derive", "kind": "derive", "project": CORPUS, "target": "def:x",
         "section": "S1", "goal": "missing-derivation: t", "blocked_by": [],
         "source_feedback": "F1", "worker": "agent:derivation-builder"},
        {"id": "WK-2-prose", "kind": "prose", "project": CORPUS, "target": "S1",
         "section": "S1", "goal": "prose: t", "blocked_by": ["WK-1-derive"],
         "source_feedback": None, "worker": "agent:prose-builder"},
    ]


def _tmp_surface(tmp_path: Path, monkeypatch, mtime_key):
    """An isolated plan+briefs surface for dispatch_report: a fresh-or-stale
    manifest is the fork under test, and nothing real may be written."""
    plan_p = tmp_path / "projection_plan.json"
    plan_p.write_text(json.dumps({"meta": {}, "sections": [{"id": "S1"}],
                                  "appendices": []}), encoding="utf-8")
    dispatches = tmp_path / "dispatches"
    dispatches.mkdir()
    (dispatches / "S1_dispatch.md").write_text("compiled", encoding="utf-8")
    mtime = plan_p.stat().st_mtime_ns if mtime_key == "fresh" else -1
    (dispatches / "dispatch_manifest.json").write_text(
        json.dumps({"corpus": CORPUS, "sections": ["S1"], "plan_mtime_ns": mtime}),
        encoding="utf-8")
    monkeypatch.setattr(sb, "_load_plan",
                        lambda c: (plan_p, json.loads(plan_p.read_text(encoding="utf-8")))
                        if c == CORPUS else None)
    monkeypatch.setattr("laplace.pipeline.propagate.propagate",
                        lambda c, since=None, **k: {"project": c, "since": since,
                                                    "changeset": 0, "comments_routed": 0,
                                                    "sections": {},
                                                    "worklist": _canned_worklist(),
                                                    "minimum_dispatch": ["S1"]})
    calls: dict = {}

    def fake_compile(project, sections=None, repo_root=None, dials_profile=None):
        calls["sections"] = sections
        calls["dials_profile"] = dials_profile
        return []

    def fake_rebuild(*a, **k):
        calls["rebuilt"] = True
        return {"ok": True, "manifest": {"sections": ["S1"], "rebuilt": True}}

    monkeypatch.setattr("laplace.pipeline.dispatch.compile_section_dispatches", fake_compile)
    monkeypatch.setattr(sb, "rebuild", fake_rebuild)
    return calls


def test_dispatch_endpoint_fresh_manifest_skips_rebuild(tmp_path, monkeypatch):
    calls = _tmp_surface(tmp_path, monkeypatch, "fresh")
    status, out = _json(_post("/storyboard/dispatch", {"corpus": CORPUS}))
    assert status == 200 and out["ok"] is True
    assert out["rebuilt"] is False and "rebuilt" not in calls
    assert calls["sections"] == ["S1"]          # the prose-section dispatch leg ran
    by_id = {i["id"]: i for i in out["items"]}
    # prose: compiled availability + the materialised path
    assert by_id["WK-2-prose"]["dispatch_available"] is True
    assert by_id["WK-2-prose"]["dispatch"].endswith("S1_dispatch.md")
    # substance: worker route + the exact on-demand compile (worker = the KIND)
    assert by_id["WK-1-derive"]["dispatch_available"] is False
    assert by_id["WK-1-derive"]["worker"] == "agent:derivation-builder"
    assert by_id["WK-1-derive"]["compile_with"] == {
        "target": "def:x", "goal": "missing-derivation: t",
        "worker": "derive", "project": CORPUS}
    assert out["minimum_dispatch"] == ["S1"]
    assert out["invocation"] and "dispatch_manifest.json" in out["invocation"]


def test_dispatch_endpoint_stale_manifest_triggers_rebuild(tmp_path, monkeypatch):
    calls = _tmp_surface(tmp_path, monkeypatch, "stale")
    status, out = _json(_post("/storyboard/dispatch", {"corpus": CORPUS}))
    assert status == 200 and out["ok"] is True
    assert out["rebuilt"] is True and calls["rebuilt"] is True
    assert out["manifest"] == {"sections": ["S1"], "rebuilt": True}


# ---------------------------------------------------------------------------
# refs - the global bib key list for the picker
# ---------------------------------------------------------------------------

def test_refs_endpoint_serves_the_global_bib_keys():
    status, out = _json(_get("/storyboard/refs", corpus=CORPUS))
    assert status == 200 and out["n"] == len(out["keys"]) > 0
    plan = json.loads((MS / "projection_plan.json").read_text(encoding="utf-8"))
    a_ref = next(r for s in plan["sections"] if s.get("refs") for r in s["refs"])
    assert a_ref in out["keys"]                 # plan refs live in the global store
    assert a_ref in out["used"]                 # and the usage index names them


# ---------------------------------------------------------------------------
# unknown corpus - 404-shaped on every new route
# ---------------------------------------------------------------------------

def test_unknown_corpus_is_404_shaped_everywhere():
    for res in (_get("/storyboard/propagate", corpus="no-such-corpus"),
                _get("/storyboard/refs", corpus="no-such-corpus"),
                _post("/storyboard/restructure", {"sections": []}, corpus="no-such-corpus"),
                _post("/storyboard/dispatch", {}, corpus="no-such-corpus")):
        status, out = _json(res)
        assert status == 404
        assert "no projection plan" in out["error"]


def test_missing_corpus_param_is_400():
    for res in (_get("/storyboard/propagate"),
                _get("/storyboard/refs"),
                _post("/storyboard/restructure", {"sections": []}),
                _post("/storyboard/dispatch", {})):
        status, out = _json(res)
        assert status == 400 and "corpus" in out["error"]


def test_restructure_bad_body_is_400():
    res = sb.handle("/storyboard/restructure", {"corpus": [CORPUS]}, "POST", b"not json")
    assert _json(res)[0] == 400
    res = sb.handle("/storyboard/restructure", {"corpus": [CORPUS]}, "POST", b'["a list"]')
    status, out = _json(res)
    assert status == 400 and "target_arc" in out["error"]
