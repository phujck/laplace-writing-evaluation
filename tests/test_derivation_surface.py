"""THE DERIVATION FACE (derivation_surface) — the aspiration-first reach organ as a
lawful set of doors: INSPECTION (the aspiration + chain + reach, joined) and
INTERACTION (re-scope the boundary claim, forge a GAP link, contest a link).

Every write door is armed + attributed with a typed refusal and a lock around
check-then-append; append-only correction is the law (a re-scope banks the prior to
history before the pointer moves; a contest rides as a later record leaving last-wins
reads untouched). The fragment door is read-only and PATH-FENCED to
``aspiration/derivations/``.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from laplace.web import derivation_surface as der
from laplace.pipeline import derivation_organ as do

CORPUS = "derivation-fixture"


@pytest.fixture
def face(tmp_path, monkeypatch):
    """A manuscript with a banked aspiration, a two-link isnad (one attested, one
    GAP), and one forged ``.tex`` fragment. ``_resolve_md`` points at it; ``_repo_root``
    points at the tmp root so a forge work-order lands in the tmp tree, never the repo."""
    root = tmp_path
    md = tmp_path / "manuscript"
    adir = md / "aspiration"
    (adir / "derivations").mkdir(parents=True)
    asp = {"record": "aspiration", "claim_maximal": "THE MAXIMAL CLAIM",
           "reach_axes": {"reach": "furthest", "scope": "broadest", "impact": "deepest"},
           "demonstrandum": ["D1 (link-a, derived)", "D2 (link-b, computed)"],
           "banked_by": "eigen", "ts": "2026-07-21T00:00:00Z"}
    (adir / "aspiration.json").write_text(json.dumps(asp), encoding="utf-8")
    chain = adir / "chain.jsonl"
    with chain.open("w", encoding="utf-8") as fh:
        # link-a: a NAMED gap; link-b: banked gap then re-appended attested (last-wins).
        fh.write(json.dumps({"id": "link-a", "from": "N_x: substrate", "to": "N_y: step",
                             "kind": "derived", "status": "gap", "attestation": None,
                             "ts": "2026-07-21T00:00:00Z",
                             "_gap_named": "the honest open frontier"}) + "\n")
        fh.write(json.dumps({"id": "link-b", "from": "N_y: step", "to": "N_z: reach",
                             "kind": "computed", "status": "gap", "attestation": None,
                             "ts": "2026-07-21T00:00:00Z"}) + "\n")
        fh.write(json.dumps({"id": "link-b", "from": "N_y: step", "to": "N_z: reach",
                             "kind": "computed", "status": "attested",
                             "attestation": "attested: 10/10 checks pass. derivations/link-b.tex",
                             "ts": "2026-07-21T00:10:00Z"}) + "\n")
    (adir / "derivations" / "link-b.tex").write_text(
        "\\subsection*{link-b}\nThe forged derivation.\n", encoding="utf-8")
    monkeypatch.setattr(der, "_resolve_md", lambda c: md if c == CORPUS else None)
    monkeypatch.setattr(der, "_repo_root", lambda: root)
    return md, root


def _chain_records(md: Path) -> list[dict]:
    p = md / "aspiration" / "chain.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _work_orders(root: Path) -> list[dict]:
    p = root / "corpus_friction" / "work_orders.jsonl"
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# ── INSPECTION — the joined read ─────────────────────────────────────────────

def test_read_sheet_joins_aspiration_chain_reach(face):
    md, _root = face
    p = der.read_sheet(md)
    assert p["present"] is True
    assert p["aspiration"]["claim_maximal"] == "THE MAXIMAL CLAIM"
    assert p["reach"]["links_total"] == 2 and p["reach"]["links_attested"] == 1
    assert p["reach"]["frontier_n"] == 1
    by_id = {l["id"]: l for l in p["chain"]}
    assert by_id["link-b"]["status"] == "attested" and by_id["link-b"]["fragment_available"] is True
    assert by_id["link-a"]["status"] == "gap" and by_id["link-a"]["fragment_available"] is False
    assert by_id["link-a"]["why"]                       # the named residual is visible
    assert "doors" in p and set(p["doors"]) == {"sheet", "fragment", "rescope", "forge", "contest"}


# ── the fragment door — read-only, path-fenced ───────────────────────────────

def test_fragment_serves_forged_tex(face):
    st, obj = der.fragment(CORPUS, "link-b")
    assert st == 200 and obj["present"] is True and "forged derivation" in obj["tex"]


def test_fragment_absent_404s(face):
    st, obj = der.fragment(CORPUS, "link-a")            # a gap has no .tex
    assert st == 404 and obj["present"] is False


def test_fragment_traversal_403s(face):
    for bad in ("../../../etc/passwd", "../aspiration", "a/../../b"):
        st, obj = der.fragment(CORPUS, bad)
        assert st == 403, bad
        assert "escapes the derivations fence" in obj["error"]


def test_fragment_no_corpus_404s(face):
    st, _ = der.fragment("no-such-corpus", "link-b")
    assert st == 404


# ── re-scope — appended revision, history banked, pointer rewritten ──────────

def test_rescope_unattributed_422s(face):
    md, _ = face
    st, obj = der.rescope(CORPUS, "", "NEW CLAIM", armed=True)
    assert st == 422 and "by required" in obj["error"]
    assert json.loads((md / "aspiration" / "aspiration.json").read_text())["claim_maximal"] == "THE MAXIMAL CLAIM"


def test_rescope_empty_claim_400s(face):
    st, obj = der.rescope(CORPUS, "gerard", "", armed=True)
    assert st == 400 and "claim required" in obj["error"]


def test_rescope_no_manuscript_404s(face):
    st, _ = der.rescope("no-such-corpus", "gerard", "NEW", armed=True)
    assert st == 404


def test_rescope_unarmed_previews_and_banks_nothing(face):
    md, _ = face
    hist = md / "aspiration" / "aspiration_history.jsonl"
    st, obj = der.rescope(CORPUS, "gerard", "NEW CLAIM", armed=False)
    assert st == 200 and obj["needs_arming"] is True
    assert obj["supersedes"] == "THE MAXIMAL CLAIM"
    assert not hist.exists()
    assert json.loads((md / "aspiration" / "aspiration.json").read_text())["claim_maximal"] == "THE MAXIMAL CLAIM"


def test_rescope_armed_banks_prior_to_history_and_rewrites_pointer(face):
    md, _ = face
    st, obj = der.rescope(CORPUS, "gerard", "NEW MAXIMAL CLAIM", armed=True, reason="widened")
    assert st == 200 and obj["ok"] and obj["revision"] == 1 and obj["history_appended"] is True
    # the pointer moved to the new claim, revision stamped
    now = json.loads((md / "aspiration" / "aspiration.json").read_text())
    assert now["claim_maximal"] == "NEW MAXIMAL CLAIM" and now["revision"] == 1
    assert now["reach_axes"]["reach"] == "furthest"          # prior structure carried forward
    # the PRIOR claim is banked to history, once
    hist = [json.loads(l) for l in (md / "aspiration" / "aspiration_history.jsonl").read_text().splitlines() if l.strip()]
    assert len(hist) == 1 and hist[0]["claim_maximal"] == "THE MAXIMAL CLAIM"
    assert hist[0]["_superseded_by"] == "gerard"


def test_rescope_twice_increments_revision(face):
    der.rescope(CORPUS, "gerard", "CLAIM v2", armed=True)
    st, obj = der.rescope(CORPUS, "gerard", "CLAIM v3", armed=True)
    assert st == 200 and obj["revision"] == 2
    md, _ = face
    hist = [json.loads(l) for l in (md / "aspiration" / "aspiration_history.jsonl").read_text().splitlines() if l.strip()]
    assert len(hist) == 2


# ── forge — banks a work-order for a GAP link (the offer law) ────────────────

def test_forge_unattributed_422s(face):
    _md, root = face
    st, obj = der.forge(CORPUS, "link-a", "", armed=True)
    assert st == 422 and "by required" in obj["error"]
    assert _work_orders(root) == []


def test_forge_no_link_400s(face):
    st, obj = der.forge(CORPUS, "", "gerard", armed=True)
    assert st == 400 and "link_id required" in obj["error"]


def test_forge_unknown_link_404s(face):
    st, obj = der.forge(CORPUS, "link-nope", "gerard", armed=True)
    assert st == 404 and "no chain link" in obj["error"]


def test_forge_attested_link_409s(face):
    _md, root = face
    st, obj = der.forge(CORPUS, "link-b", "gerard", armed=True)      # link-b is attested
    assert st == 409 and "already attested" in obj["error"]
    assert _work_orders(root) == []


def test_forge_unarmed_previews_and_banks_nothing(face):
    _md, root = face
    st, obj = der.forge(CORPUS, "link-a", "gerard", armed=False)
    assert st == 200 and obj["needs_arming"] is True and "brief" in obj
    assert _work_orders(root) == []


def test_forge_armed_banks_one_model_heavy_work_order(face):
    _md, root = face
    st, obj = der.forge(CORPUS, "link-a", "gerard", armed=True)
    assert st == 200 and obj["ok"] and obj["cost_class"] == "model-heavy" and obj["spawned"] is False
    wos = _work_orders(root)
    assert len(wos) == 1
    w = wos[0]
    assert w["record"] == w["kind"] == "work-order"
    assert w["action"] == "derivation-forge"
    assert w["link_id"] == "link-a" and w["requested_by"] == "gerard" and w["status"] == "open"


# ── contest — a later record, last-wins reads unaffected ─────────────────────

def test_contest_unattributed_422s(face):
    st, obj = der.contest(CORPUS, "link-b", "", "wrong", armed=True)
    assert st == 422 and "by required" in obj["error"]


def test_contest_empty_reason_400s(face):
    st, obj = der.contest(CORPUS, "link-b", "gerard", "", armed=True)
    assert st == 400 and "reason required" in obj["error"]


def test_contest_unknown_link_404s(face):
    st, obj = der.contest(CORPUS, "link-nope", "gerard", "wrong", armed=True)
    assert st == 404


def test_contest_unarmed_previews_and_banks_nothing(face):
    md, _ = face
    before = len(_chain_records(md))
    st, obj = der.contest(CORPUS, "link-b", "gerard", "the prefactor is wrong", armed=False)
    assert st == 200 and obj["needs_arming"] is True and obj["status"] == "attested"
    assert len(_chain_records(md)) == before


def test_contest_armed_appends_record_leaving_status_unchanged(face):
    md, _ = face
    st, obj = der.contest(CORPUS, "link-b", "gerard", "the prefactor is wrong", armed=True)
    assert st == 200 and obj["ok"] and obj["status"] == "attested"
    # a contest record was appended, carrying the _contest marker
    recs = _chain_records(md)
    contest_recs = [r for r in recs if r.get("_contest")]
    assert len(contest_recs) == 1
    assert contest_recs[0]["id"] == "link-b" and contest_recs[0]["status"] == "attested"
    assert contest_recs[0]["_contest"]["by"] == "gerard"
    # LAST-WINS reads are UNAFFECTED: link-b is still attested after the contest
    links = {l["id"]: l for l in do.read_chain(md)}
    assert links["link-b"]["status"] == "attested"
    assert links["link-a"]["status"] == "gap"
    # the sheet surfaces the contest
    sheet = der.read_sheet(md)
    by_id = {l["id"]: l for l in sheet["chain"]}
    assert len(by_id["link-b"]["contests"]) == 1
    assert by_id["link-b"]["contests"][0]["reason"] == "the prefactor is wrong"


# ── the handler — routing, strict arming, foreign paths ──────────────────────

def test_handle_get_sheet_400s_without_corpus(face):
    st, _, body = der.handle("/derivation/sheet", {}, "GET", b"")
    assert st == 400 and "corpus required" in json.loads(body)["error"]


def test_handle_get_sheet_returns_the_join(face):
    st, _, body = der.handle("/derivation/sheet", {"corpus": [CORPUS]}, "GET", b"")
    assert st == 200
    obj = json.loads(body)
    assert obj["corpus"] == CORPUS and obj["reach"]["links_attested"] == 1


def test_handle_get_fragment_path_fenced(face):
    st, _, body = der.handle("/derivation/fragment",
                             {"corpus": [CORPUS], "link": ["../secret"]}, "GET", b"")
    assert st == 403


def test_handle_returns_none_for_foreign_paths(face):
    assert der.handle("/not-ours", {}, "GET", b"") is None


def test_handle_bad_json_400s(face):
    for route in ("/derivation/rescope", "/derivation/forge", "/derivation/contest"):
        st, _, _ = der.handle(route, {}, "POST", b"not json")
        assert st == 400, route


@pytest.mark.parametrize("route,body", [
    ("/derivation/forge", {"corpus": CORPUS, "link_id": "link-a", "by": "gerard"}),
    ("/derivation/contest", {"corpus": CORPUS, "link_id": "link-b", "by": "gerard", "reason": "x"}),
    ("/derivation/rescope", {"corpus": CORPUS, "by": "gerard", "claim": "NEW"}),
])
def test_handle_armed_is_strict_true_never_truthy(face, route, body):
    """The arming gate fail-closes on malformed input: only JSON true arms —
    "yes"/"false"/1/"true"(string) read as UNARMED at every write door."""
    for bad in ("yes", "false", 1, "true"):
        st, _, resp = der.handle(route, {}, "POST",
                                 json.dumps({**body, "armed": bad}).encode())
        obj = json.loads(resp)
        assert st == 200 and obj.get("needs_arming") is True, (route, bad)


def test_concurrent_forge_banks_are_serialised(face):
    """The lock holds under the scanner's threading: N parallel armed forges on the
    same gap link each append through ONE critical section (no interleaved half-line)."""
    _md, root = face
    results: list[int] = []

    def fire():
        st, _ = der.forge(CORPUS, "link-a", "gerard", armed=True)
        results.append(st)

    threads = [threading.Thread(target=fire) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # every forge on a still-gap link is lawful (forging is retryable); all bank cleanly
    assert results.count(200) == 12
    assert len(_work_orders(root)) == 12
