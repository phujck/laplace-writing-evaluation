"""WAVE 0.5 — THE LADDER (server contract).

``GET /shared/ladder?corpus=&target=&kind=`` opens SIX rungs over one target
(concept·argument·prose·evidence·judgment·machine), each with an honest count + door,
an honest absence naming its own fix, and an honest staleness verdict. These tests
fail-close on:

  * detection: the server grammar (project/asset/pid/section/beat/node) + the hint
    override (the client's URL key wins);
  * six rungs ALWAYS, fixed order, across all seven target kinds — populated ⇔
    count+door, absent ⇔ reason+fix (never a blank);
  * honest empties (paper_eigen: no plan → argument absent naming its fix);
  * 400 missing corpus / 404 unregistered / traversal fenced BEFORE any disk touch;
  * the golden byte law (≤16KB, LOUD truncation, counts never reduced);
  * the pure-reads boom guard (subprocess / build_nodemap / rebuild / embed route → raise;
    the payload completes for EVERY kind on the warm cache);
  * scoped_decisions reads EXACTLY two stores (the feedback ledger + one friction file,
    never the glob), caps rows, and shares _desk_feedback's filter;
  * THE UP-CONJUGATE: altitude/ladder resolve the same node ids; the desk deep-links ARE
    the ladder doors; the rung-source bijection holds; a store mutation moves the count.

The resolver is exercised on the LIVE subset-sum-itqde corpus (the real counts, as
test_altitude does) with paper_eigen for the honest empties — the readers under test are
the real ones, never a hand-faked tree that cannot exercise them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.web import ladder, desk, shared_ui
from laplace.engine import altitude

pytestmark = pytest.mark.unit

RR = Path(__file__).resolve().parent.parent
CORPUS = "subset-sum-itqde"
EMPTY = "paper_eigen"


# ---------------------------------------------------------------------------
# live target ids (resolved once from the real substrate, so the kinds are real).
# ---------------------------------------------------------------------------
def _a_beat() -> str:
    from laplace.research import corpus_ingest as ci
    troot = ci.resolve_corpus(RR, CORPUS)
    net = ci.corpus_network(troot, repo_root=RR, name=CORPUS)
    return net["spine"][0]["id"]


def _an_asset() -> str:
    from laplace.pipeline import asset_model
    return asset_model.enumerate_assets(CORPUS)[0].id


def _seven_kinds() -> dict[str, tuple[str, str]]:
    """kind → (target, hint) — one real live target per kind (version rides a synthetic
    revision id: a version selection opens the uniform ladder regardless)."""
    return {
        "project": ("", ""),
        "node": ("def:spectral-surface", "node"),
        "section": ("N5", "section"),
        "pid": ("N5-p2", "pid"),
        "beat": (_a_beat(), "beat"),
        "asset": (_an_asset(), "asset"),
        "version": ("2026-07-12_015849", "version"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# DETECTION — the server grammar + the hint override.
# ═══════════════════════════════════════════════════════════════════════════
def test_detect_target_grammar():
    spine = frozenset({"res:beat-one"})
    assert ladder.detect_target("", corpus=CORPUS)["kind"] == "project"
    assert ladder.detect_target(CORPUS, corpus=CORPUS)["kind"] == "project"
    assert ladder.detect_target("figure:foo")["kind"] == "asset"
    assert ladder.detect_target("derivation:WK-032")["kind"] == "asset"
    assert ladder.detect_target("N5-p2")["kind"] == "pid"
    assert ladder.detect_target("N5")["kind"] == "section"
    assert ladder.detect_target("NA1")["kind"] == "section"
    assert ladder.detect_target("res:beat-one", spine_ids=spine)["kind"] == "beat"
    assert ladder.detect_target("def:staircase")["kind"] == "node"
    # the section/node fields ride from the anchor grammar (no second parse)
    assert ladder.detect_target("N5-p2")["section"] == "N5"
    assert ladder.detect_target("def:x")["node"] == "def:x"


def test_detect_hint_wins():
    # the client read ?node= off a beat-shaped id → node wins over the spine grammar
    spine = frozenset({"res:beat-one"})
    assert ladder.detect_target("res:beat-one", "node", spine_ids=spine)["kind"] == "node"
    # a version id is grammar-invisible; only the hint names it
    assert ladder.detect_target("2026-07-12_015849")["kind"] == "node"        # grammar fallback
    assert ladder.detect_target("2026-07-12_015849", "version")["kind"] == "version"
    # a non-kind hint is ignored (the grammar stands)
    assert ladder.detect_target("N5", "garbage")["kind"] == "section"


# ═══════════════════════════════════════════════════════════════════════════
# SIX RUNGS ALWAYS — fixed order, full shape, honesty invariant, all seven kinds.
# ═══════════════════════════════════════════════════════════════════════════
def test_six_rungs_always_across_seven_kinds():
    for kind, (target, hint) in _seven_kinds().items():
        out = ladder.ladder_payload(CORPUS, target, hint)
        assert out is not None, kind
        ids = [r["id"] for r in out["rungs"]]
        assert ids == list(ladder._RUNG_ORDER), f"{kind}: {ids}"
        assert out["target"]["kind"] == kind
        for r in out["rungs"]:
            # every rung carries the full uniform shape
            assert set(r) >= {"id", "label", "present", "count", "sub", "href",
                              "items", "absent", "stale"}, (kind, r["id"])
            # THE HONESTY INVARIANT: populated ⇔ count+door; absent ⇔ reason+fix.
            if r["present"]:
                assert r["href"], f"{kind}/{r['id']}: present with no door"
                assert r["absent"] is None
            else:
                assert r["absent"] is not None, f"{kind}/{r['id']}: absent with no reason"
                assert r["absent"]["reason"] and r["absent"]["fix"] and r["absent"]["fix_href"]
                assert r["count"] == 0
            assert len(r["items"]) <= 6


def test_target_known_and_labels():
    # a real node resolves known:true with a grade and node_ids
    out = ladder.ladder_payload(CORPUS, "def:spectral-surface", "node")
    assert out["target"]["known"] is True
    assert out["target"]["node_ids"] == ["def:spectral-surface"]
    assert isinstance(out["target"]["grade"], int)
    # an unknown node is a 200 with known:false (a helpful panel, never a dead end)
    unk = ladder.ladder_payload(CORPUS, "def:does-not-exist", "node")
    assert unk["target"]["known"] is False
    # concept/prose/evidence/judgment are absent-with-fix; machine (corpus-scoped) stands
    by = {r["id"]: r for r in unk["rungs"]}
    assert by["concept"]["present"] is False and by["concept"]["absent"]["fix_href"]
    assert by["judgment"]["present"] is False        # an unknown node NEVER leaks the project set
    assert by["judgment"]["count"] == 0


def test_asset_target_evidence_is_it():
    aid = _an_asset()
    out = ladder.ladder_payload(CORPUS, aid, "asset")
    by = {r["id"]: r for r in out["rungs"]}
    assert by["evidence"]["present"] and by["evidence"]["count"] >= 1
    assert any(it["id"] == aid for it in by["evidence"]["items"])
    assert f"&asset={aid.replace(':', '%3A')}" in by["evidence"]["href"]


def test_version_opens_uniform_ladder():
    """His ruling: a version selection opens the UNIFORM ladder (project scope), with the
    prose rung pinned to that revision + one line noting the history lives in the rail."""
    proj = ladder.ladder_payload(CORPUS, "", "")
    ver = ladder.ladder_payload(CORPUS, "2026-07-12_015849", "version")
    pby = {r["id"]: r for r in proj["rungs"]}
    vby = {r["id"]: r for r in ver["rungs"]}
    # concept/argument/evidence/judgment/machine are the project ladder, verbatim counts
    for rid in ("concept", "argument", "evidence", "judgment", "machine"):
        assert vby[rid]["count"] == pby[rid]["count"], rid
    # prose is pinned to the revision, and the door carries &version=
    assert "2026-07-12_015849" in vby["prose"]["sub"]
    assert "rail" in vby["prose"]["sub"]
    assert "&version=2026-07-12_015849" in vby["prose"]["href"]


# ═══════════════════════════════════════════════════════════════════════════
# HONEST EMPTIES — paper_eigen has no projection plan.
# ═══════════════════════════════════════════════════════════════════════════
def test_honest_empties_name_the_fix():
    out = ladder.ladder_payload(EMPTY, "", "")
    by = {r["id"]: r for r in out["rungs"]}
    assert by["argument"]["present"] is False
    assert "no projection plan" in by["argument"]["absent"]["reason"]
    assert by["argument"]["absent"]["fix_href"].startswith("/storyboard?corpus=")
    # the empties are rendered reasons, never a blank rung
    assert len(out["rungs"]) == 6


# ═══════════════════════════════════════════════════════════════════════════
# THE ENDPOINT — status semantics + the traversal fence.
# ═══════════════════════════════════════════════════════════════════════════
def test_endpoint_status_and_fence():
    st, _, body = shared_ui.handle("/shared/ladder", {})
    assert st == 400 and b"corpus" in body
    st, _, _ = shared_ui.handle("/shared/ladder", {"corpus": "no-such-project"})
    assert st == 404
    # a path-shaped name is fenced to 404 BEFORE any disk touch
    st, _, _ = shared_ui.handle("/shared/ladder", {"corpus": "../etc/passwd"})
    assert st == 404
    st, _, body = shared_ui.handle("/shared/ladder",
                                   {"corpus": CORPUS, "target": "N5", "kind": "section"})
    obj = json.loads(body)
    assert st == 200 and len(obj["rungs"]) == 6
    # an unresolvable target is a 200 (target.known:false), never a 4xx/5xx
    st, _, body = shared_ui.handle("/shared/ladder",
                                   {"corpus": CORPUS, "target": "def:nope", "kind": "node"})
    assert st == 200 and json.loads(body)["target"]["known"] is False


# ═══════════════════════════════════════════════════════════════════════════
# THE GOLDEN BYTE LAW — ≤16KB, LOUD, counts never reduced.
# ═══════════════════════════════════════════════════════════════════════════
def test_payload_bound_loud_counts_intact():
    # every kind's real payload already fits; prove the ceiling + the loud-shed contract.
    for _, (target, hint) in _seven_kinds().items():
        out = ladder.ladder_payload(CORPUS, target, hint)
        size = len(json.dumps(out, ensure_ascii=False).encode("utf-8"))
        assert size <= ladder._LADDER_MAX_BYTES, (hint, size)
    # force the shed: a tiny ceiling drops ITEMS loudly while counts stay honest.
    out = ladder.ladder_payload(CORPUS, "", "")
    counts_before = {r["id"]: r["count"] for r in out["rungs"]}
    monkey_max = 3000        # between the item-less floor and the full project payload
    saved = ladder._LADDER_MAX_BYTES
    try:
        ladder._LADDER_MAX_BYTES = monkey_max
        out2 = ladder.ladder_payload(CORPUS, "", "")
    finally:
        ladder._LADDER_MAX_BYTES = saved
    assert out2["truncated"] is True and out2["omitted"] > 0
    assert len(json.dumps(out2, ensure_ascii=False).encode("utf-8")) <= monkey_max
    # counts are the HONEST discovered totals, never the shed-down shown length
    assert {r["id"]: r["count"] for r in out2["rungs"]} == counts_before


# ═══════════════════════════════════════════════════════════════════════════
# THE PURE-READS BOOM GUARD — no subprocess / build_nodemap / rebuild / embed route.
# ═══════════════════════════════════════════════════════════════════════════
def test_pure_reads_boom_guard(monkeypatch):
    import subprocess
    from laplace.research import corpus_ingest as ci
    from laplace.representation import embed_router as er
    from laplace.pipeline import nodemap

    # WARM the cached network first (the join RIDES the cache — a cold miss legitimately
    # builds once; the ladder itself must never trigger a rebuild/subprocess/embed).
    ladder.ladder_payload(CORPUS, "", "")

    def _boom(name):
        def _f(*a, **k):
            raise AssertionError(f"ladder fired {name} — not a pure read")
        return _f

    monkeypatch.setattr(subprocess, "run", _boom("subprocess.run"))
    monkeypatch.setattr(subprocess, "Popen", _boom("subprocess.Popen"))
    monkeypatch.setattr(ci, "build_corpus_network", _boom("build_corpus_network"))
    monkeypatch.setattr(nodemap, "build_nodemap", _boom("build_nodemap"))
    monkeypatch.setattr(er, "route", _boom("embed_router.route"))

    for kind, (target, hint) in _seven_kinds().items():
        out = ladder.ladder_payload(CORPUS, target, hint)
        assert out is not None and len(out["rungs"]) == 6, kind


# ═══════════════════════════════════════════════════════════════════════════
# scoped_decisions — EXACTLY two stores, cap, filter parity with _desk_feedback.
# ═══════════════════════════════════════════════════════════════════════════
def test_scoped_decisions_reads_exactly_two_stores(monkeypatch):
    read_paths: list[str] = []
    real = desk.read_jsonl

    def _spy(path):
        read_paths.append(str(path))
        return real(path)

    monkeypatch.setattr(desk, "read_jsonl", _spy)
    out = desk.scoped_decisions(RR, CORPUS, [])
    # exactly the project feedback ledger + the ONE corpus_friction/<corpus>.jsonl —
    # never the corpus_friction/*.jsonl glob (no sibling ledger is touched).
    assert len(read_paths) == 2, read_paths
    assert any(p.endswith("feedback/feedback.jsonl") for p in read_paths)
    assert any(p.endswith(f"corpus_friction/{CORPUS}.jsonl") for p in read_paths)
    assert not any(p.endswith("law-of-laws.jsonl") for p in read_paths)
    assert out["sources"]["feedback_ledger"] and out["sources"]["corpus_friction"]


def test_scoped_decisions_cap_and_count_honest():
    full = desk.scoped_decisions(RR, CORPUS, [])
    capped = desk.scoped_decisions(RR, CORPUS, [], cap=1)
    assert capped["count"] == full["count"]          # count is the honest total
    assert len(capped["rows"]) <= 1                   # rows obey the cap
    assert full["count"] >= 1


def test_scoped_decisions_filter_parity_with_desk_feedback():
    """The scoped feedback filter is _desk_feedback's, verbatim: the unscoped
    (project) decision count matches the desk's own adjudications-by-project count
    (plus this corpus's open non-fork frictions, which the desk counts separately)."""
    adj, _ = desk._desk_feedback(RR)
    desk_adj = adj["by_project"].get(CORPUS, 0)
    from laplace.pipeline.friction_consumer import open_frictions
    from laplace.pipeline.ledger import read_jsonl
    fled = RR / "corpus_friction" / f"{CORPUS}.jsonl"
    fr = sum(1 for r in open_frictions(read_jsonl(fled)) if r.get("kind") != "fork") \
        if fled.is_file() else 0
    assert desk.scoped_decisions(RR, CORPUS, [])["count"] == desk_adj + fr


# ═══════════════════════════════════════════════════════════════════════════
# THE UP-CONJUGATE #2 — altitude and the ladder resolve IDENTICAL node ids.
# ═══════════════════════════════════════════════════════════════════════════
def test_altitude_same_node_ids():
    from laplace.engine import altitude as alt
    for anchor, hint in (("N5", "section"), ("N5-p2", "pid"),
                         ("def:staircase", "node")):
        alt_out = alt.resolve(CORPUS, anchor)
        lad = ladder.ladder_payload(CORPUS, anchor, hint)
        assert lad["target"]["node_ids"] == alt_out["altitudes"]["nodes"]["anchor_ids"], anchor


# ═══════════════════════════════════════════════════════════════════════════
# THE UP-CONJUGATE #1 — the desk deep-links ARE the ladder doors (ONE function).
# ═══════════════════════════════════════════════════════════════════════════
def test_desk_deeplink_parity():
    name, node, section = CORPUS, "def:spectral-surface", "N3"
    dl = desk._adjudication_deeplinks(name, node, section)
    target = {"raw": node, "kind": "node", "node": node, "section": section,
              "node_ids": [node]}
    doors = {d["id"]: d["href"] for d in ladder.doors_for(name, target)}
    got = {d["href"] for d in dl}
    # every desk deep-link href is a ladder rung door (prose/concept/argument), verbatim
    assert dl[0]["href"] == doors["prose"]
    assert dl[1]["href"] == doors["concept"]
    assert dl[2]["href"] == doors["argument"]
    assert got <= set(doors.values())


def test_desk_row_primary_href_is_the_prose_door():
    """DRIFT-4 closed: the adjudication ROW's PRIMARY href is the SAME ladder prose door as
    its deeplinks[0] — one composition, not a second private _artefact_href — so the desk's
    landing can never drift from the viewer's prose door. Proven structurally over every
    adjudication row the desk emits (never vacuous: _desk_feedback spans all projects)."""
    adj, _ = desk._desk_feedback(RR)
    for row in adj["rows"]:
        assert row["href"] == row["deeplinks"][0]["href"], row["id"]
    # and the scoped read (the ladder's judgment join) obeys the same single-source rule,
    # re-derived against doors_for for the live corpus's adjudication rows.
    out = desk.scoped_decisions(RR, CORPUS, [])
    for row in out["rows"]:
        if row["class"] != "adjudications":
            continue
        node = row["fields"].get("node") or ""
        section = row["fields"].get("section") or ""
        target = {"raw": node or section, "kind": "node" if node else "section",
                  "node": node, "section": section, "node_ids": [node] if node else []}
        doors = {d["id"]: d["href"] for d in ladder.doors_for(CORPUS, target)}
        assert row["href"] == doors["prose"], row["id"]


# ═══════════════════════════════════════════════════════════════════════════
# THE BIJECTION CLAUSE — every rung has a reader; every reader owns exactly one rung;
# each reader IS the owning surface's function (identity); a planted 7th fails.
# ═══════════════════════════════════════════════════════════════════════════
def test_rung_source_bijection():
    from laplace.research import corpus_ingest as ci
    from laplace.manuscript import storyboard as sb
    from laplace.pipeline import asset_model, registry
    # (a) every rung id a payload emits appears in _RUNG_SOURCES
    out = ladder.ladder_payload(CORPUS, "N5", "section")
    emitted = {r["id"] for r in out["rungs"]}
    assert emitted == set(ladder._RUNG_SOURCES), (emitted, set(ladder._RUNG_SOURCES))
    assert emitted == set(ladder._RUNG_ORDER)
    # (b) each declared reader IS the owning surface's function (identity, not a copy)
    assert ladder._RUNG_SOURCES["argument"] is sb.enriched_plan
    assert ladder._RUNG_SOURCES["evidence"] is asset_model.enumerate_assets
    assert ladder._RUNG_SOURCES["machine"] is registry.project_states
    assert ladder._RUNG_SOURCES["judgment"] is desk.scoped_decisions
    # prose's declared reader is its ACTUAL fact source — the % NODES reader /artefact's
    # projection uses — not read_nodemap (which only feeds the evidence stale chip). The
    # count is proven to derive from it in test_prose_count_derives_from_declared_reader.
    assert ladder._RUNG_SOURCES["prose"] is altitude.section_nodes
    assert ladder._RUNG_SOURCES["concept"] is ci.corpus_network
    for reader in ladder._RUNG_SOURCES.values():
        assert callable(reader)


def test_prose_count_derives_from_declared_reader(monkeypatch):
    """The bijection is FUNCTIONAL, not nominal: the prose rung's count IS produced by the
    declared reader (altitude.section_nodes), not a decoy of the same name. Monkeypatch the
    reader → the prose count moves to the planted value (the drift proof §2 promised)."""
    monkeypatch.setattr(altitude, "section_nodes",
                        lambda td: {"N5": ["a", "b", "c", "d"]})
    out = ladder.ladder_payload(CORPUS, "N5", "section")
    prose = next(r for r in out["rungs"] if r["id"] == "prose")
    assert prose["count"] == 4, "the prose count must derive from altitude.section_nodes"


def test_bijection_rejects_a_planted_seventh_reader():
    # (c) a reader with no rung breaks the census — the payload's rungs must still bijec
    # with the DECLARED sources; a smuggled seventh has no rung to own.
    planted = dict(ladder._RUNG_SOURCES)
    planted["telemetry"] = lambda *a, **k: None
    out = ladder.ladder_payload(CORPUS, "N5", "section")
    emitted = {r["id"] for r in out["rungs"]}
    assert "telemetry" not in emitted
    assert emitted != set(planted), "a planted 7th reader must fail the rung↔source bijection"


# ═══════════════════════════════════════════════════════════════════════════
# DRIFT FAILS LOUDLY — a store mutation moves the judgment count on the next call.
# ═══════════════════════════════════════════════════════════════════════════
def test_store_mutation_moves_counts(tmp_path):
    """Add an open friction row for a node in a tmp corpus_friction store → the scoped
    decision count for that node MOVES on the next read (the up-loop banks real work, and
    the read sees it). The feedback ledger is absent under the tmp root, so only the
    friction substrate is exercised — a clean single-store drift proof."""
    node = "def:spectral-surface"
    fdir = tmp_path / "corpus_friction"
    fdir.mkdir()
    fled = fdir / f"{CORPUS}.jsonl"

    def _write(rows):
        fled.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    _write([{"kind": "friction", "status": "open", "node": node, "id": "FR1",
             "ts": "2026-07-16T00:00:00Z"}])
    before = desk.scoped_decisions(tmp_path, CORPUS, [node])["count"]
    _write([{"kind": "friction", "status": "open", "node": node, "id": "FR1",
             "ts": "2026-07-16T00:00:00Z"},
            {"kind": "friction", "status": "open", "node": node, "id": "FR2",
             "ts": "2026-07-16T00:00:01Z"}])
    after = desk.scoped_decisions(tmp_path, CORPUS, [node])["count"]
    assert after == before + 1, (before, after)


def test_judgment_scopes_an_unknown_node_by_its_raw_id(monkeypatch):
    """A friction/feedback record keys by the node STRING, independent of current graph
    membership. So a node target that resolves to NO graph node (renamed/removed) must
    STILL scope its judgment read by its raw id — never short-circuit to a reassuring 0 the
    desk would contradict. Proven by the scoped reader receiving the raw id."""
    seen: dict[str, list] = {}
    real = desk.scoped_decisions

    def _spy(repo, corpus, node_ids, **kw):
        seen["ids"] = list(node_ids)
        return real(repo, corpus, node_ids, **kw)

    monkeypatch.setattr(desk, "scoped_decisions", _spy)
    ladder.ladder_payload(CORPUS, "def:ghost-renamed", "node")
    assert "ids" in seen, "the judgment rung short-circuited an unknown node — never read the store"
    assert "def:ghost-renamed" in seen["ids"]
