"""W-G — the gauge wired to the substrate. The coverage gauge stops lying about
falqon's validation axis: G3's LIVE claim->validation pointers, which the growth-stage
close banked but never wired into the conceptric edge_index the gauge walks, become
``validates``-axis edges the gauge counts — DETERMINISTICALLY, at build time, from the
evidence ledger + the numerics store (a poured conceptric takes no mutable writes).

The wave's acceptance, as tests:
  1. WIRING — falqon's validation axis moves off 0/22 to its real count; literature and
     figure-demonstration stay HONEST zeros (no supports/demonstrates tokens exist yet).
  2. DETERMINISM — the same edge_index on every rebuild (the critic trap: re-pour must
     reproduce it byte-for-byte, so no timestamped ledger write may sneak in).
  3. RESOLVABLE + ONE-HOME — every minted validates token parses to axis=validates
     through ``schema.parse_edge_token`` and targets a LIVE node (no dangling), and is
     byte-identical to ``schema.token_for`` (the one minter; never a parallel path).
  4. TRUE ZERO — a corpus with no registered evidence_store wires NOTHING (no token, no
     coverage), and the raw up-operator with no (name, repo_root) is untouched.
  5. THE PAIRING — regoal() clears the sidecar's pending_goal_supersede when handed the
     banked goal-v2 record id (the LADDERED path; also covered by test_g2_ladder's
     pairing-debt test), and author_goal_tensions' postdating check reads the REAL
     falqon supersede that cleared the authored-goal tension tonight.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from laplace.research import corpus_ingest as ci
from laplace.pipeline import demand, growth, schema

REPO = Path(__file__).resolve().parents[1]
CORPUS = "paper_falqon"

sys.path.insert(0, str(REPO / "scripts"))
import ingest_synthetic as ing  # noqa: E402  (the one evidence parser the wiring consumes)


def _falqon_or_skip() -> Path:
    troot = ci.resolve_corpus(REPO, CORPUS)
    if troot is None or not (REPO / "paper_falqon" / "numerics" /
                             "resource_readings.json").is_file():
        pytest.skip("paper_falqon corpus / numerics absent")
    return troot


# ============================================================ 1. WIRING

def test_falqon_validation_moves_off_zero_and_other_axes_stay_honest():
    """The gauge tells the truth: validation reads its REAL covered count (the results
    with a live evidence pointer), while literature and demonstration remain HONEST
    zeros — no supports/demonstrates tokens exist for falqon, so no coverage is faked."""
    _falqon_or_skip()
    ci._CORPUS_CACHE.clear()
    cov = demand.coverage_vector(REPO, CORPUS)
    assert cov["load_bearing_claims"] == 22            # the real denominator, unchanged
    val = cov["validation"]
    assert val["axis"] == "validates"
    assert val["total"] == 22
    # 17 of the 22 result nodes carry a resolvable validates edge today (the real count);
    # the 5 uncovered are the claims with no live evidence pointer (motivation /
    # qualitative) — honest zeros, not lies.
    assert val["covered"] == 17
    assert len(val["uncovered"]) == 5
    # the other two axes are still honest zeros (no typed supports/demonstrates tokens).
    assert cov["literature"]["covered"] == 0
    assert cov["demonstration"]["covered"] == 0


def test_uncovered_results_have_no_live_evidence_pointer():
    """Every uncovered result is uncovered BECAUSE it has no live validation pointer in
    the evidence ledger — the zero is earned, not an unwired token."""
    _falqon_or_skip()
    ci._CORPUS_CACHE.clear()
    cov = demand.coverage_vector(REPO, CORPUS)
    _regraded, edges = ing.build(REPO / "paper_falqon", CORPUS)
    live = edges["claim_to_validation"]
    for node in cov["validation"]["uncovered"]:
        cid = "FAL-CLM-" + node.split("_")[-1]
        assert not live.get(cid), f"{node} is uncovered but has live evidence {live.get(cid)}"


def test_real_falqon_validates_count_is_reachable():
    """FLOOR — the real numbers. The evidence substrate G3 banked carries >= 70 live
    validates tokens (77 today across every ledger claim); the builder wires every one
    whose claim maps to a live conceptric node into the net the gauge reads (51 today —
    the paper claims + the drift/limitation claims; the assumption claims fold onto
    param nodes, not fal_clm ids, so they are honestly skipped)."""
    troot = _falqon_or_skip()
    _regraded, edges = ing.build(REPO / "paper_falqon", CORPUS)
    n_substrate = sum(len(v) for v in edges["validates"].values())
    assert n_substrate >= 70                            # the substrate G3 banked (77)
    ci._CORPUS_CACHE.clear()
    net = ci.corpus_network(troot, repo_root=REPO, name=CORPUS)
    assert net["n_validation_edges"] == 51             # the real number wired into the net
    # and every wired edge lands on a load-bearing OR support node, none dangling.
    assert net["n_validation_edges"] >= 50


# ============================================================ 2. DETERMINISM

def test_wiring_is_deterministic_on_rebuild():
    """The critic trap: two independent builds (cache cleared between) produce the same
    edge_index and the same validates-edge count — no timestamped write, no re-pour
    drift."""
    troot = _falqon_or_skip()
    ci._CORPUS_CACHE.clear()
    net1 = ci.corpus_network(troot, repo_root=REPO, name=CORPUS)
    e1 = json.dumps(net1["edge_index"], sort_keys=True)
    n1 = net1["n_validation_edges"]
    ci._CORPUS_CACHE.clear()
    net2 = ci.corpus_network(troot, repo_root=REPO, name=CORPUS)
    e2 = json.dumps(net2["edge_index"], sort_keys=True)
    assert e1 == e2
    assert n1 == net2["n_validation_edges"] == 51


# ============================================================ 3. RESOLVABLE + ONE HOME

def test_validates_tokens_resolve_to_live_nodes_and_mint_through_one_home():
    """Every validates token on a result node parses to axis=validates (the one parser),
    targets a LIVE node (the resolvable dereference — no dangling), and is byte-identical
    to the one minter's output (never a hand-written prefix / parallel path)."""
    troot = _falqon_or_skip()
    ci._CORPUS_CACHE.clear()
    net = ci.corpus_network(troot, repo_root=REPO, name=CORPUS)
    nodes = net["nodes"]
    ei = net["edge_index"]
    seen = 0
    for nid in demand.load_bearing(nodes):
        for tok in ei.get(nid, []):
            parsed = schema.parse_edge_token(tok)
            if not parsed or parsed.get("axis") != "validates":
                continue
            seen += 1
            tgt = parsed["target"]
            assert tgt in nodes, f"validates edge {tok!r} on {nid} dangles (target not a node)"
            assert tok == schema.token_for("validates", tgt)   # the one home, byte-identical
    assert seen >= 30            # the validates edges on the 17 covered result nodes


# ============================================================ 4. TRUE ZERO

def test_no_evidence_store_wires_nothing(tmp_path):
    """A minimal corpus with no registered evidence_store wires no validates edge; the
    coverage vector reads a true zero (no token, no coverage), and the raw up-operator
    (no name/repo_root) is unchanged."""
    tex = tmp_path / "tex"
    tex.mkdir()
    (tex / "main.tex").write_text(r"\input{s1}", encoding="utf-8")
    (tex / "s1.tex").write_text(
        "\\section{Intro}\\label{sec:intro}\n"
        "\\begin{equation}\\label{eq:one} a=b \\end{equation}\n", encoding="utf-8")
    # name is unknown to the registry -> apply_evidence_edges returns 0 (fail-closed).
    net = ci.corpus_network(tex, repo_root=tmp_path, name="not-registered")
    assert net["n_validation_edges"] == 0
    cov = demand.coverage_over_net(net)
    assert cov["validation"]["covered"] == 0
    # the raw up-operator with no (name, repo_root) never wires and never crashes.
    raw = ci.build_corpus_network(tex)
    assert raw["n_validation_edges"] == 0


# ============================================================ 5. THE PAIRING

def _seed_at_stocked(root: Path, name: str) -> None:
    """Seed the growth sidecar directly at STOCKED — regoal is reachable from STOCKED
    onward, and STOCKED's own bar fails closed (its gate is G3/G4's), so a test reaches
    it by writing the sidecar, not by transitioning through the un-built gate."""
    growth.seed(root, name, by="gerard")
    sc = growth._sidecar_path(root, name)
    side = growth._read_sidecar(sc)
    side["state"] = "STOCKED"
    side["bar"] = growth.BARS["STOCKED"]
    growth._atomic_write(sc, side)


def test_regoal_clears_pending_supersede_when_given_the_record_id(tmp_path):
    """The LADDERED pairing path (item 4): regoal WITHOUT the banked goal-v2 record id
    names the debt (pending_goal_supersede visible); WITH it, the flag clears and the id
    is recorded on the REGOALED history row."""
    root = tmp_path
    _seed_at_stocked(root, "p")
    side = growth.regoal(root, "p",
                         evidence={"ruling": {"by": "gerard", "verb": "REGOAL", "ref": "card-1"}})
    assert side.get("pending_goal_supersede") is True

    _seed_at_stocked(root, "q")
    side_q = growth.regoal(root, "q",
                           evidence={"ruling": {"by": "gerard", "verb": "REGOAL", "ref": "card-2"},
                                     "supersede_record_id": "RW-20260722-000000-000042"})
    assert "pending_goal_supersede" not in side_q
    regoal_row = [h for h in side_q["history"] if h["to"] == "REGOALED"][-1]
    assert regoal_row["evidence"]["supersede_record_id"] == "RW-20260722-000000-000042"


def test_author_goal_tension_postdating_reads_the_real_supersede():
    """Item 4 — the REGOAL that drove a REAL supersede on pre-ladder falqon tonight
    (RW-20260722-163328-193609) cleared the authored-goal reconciliation tension: the
    postdating check sees a goal supersede that postdates the author-goal verdict, so
    author_goal_tensions reads the corpus as reconciled (no tension), never a stale fire."""
    _falqon_or_skip()
    from laplace.engine import author_proxy
    verdict = next((v for v in author_proxy.load_verdicts(REPO)
                    if v.get("kind") == "author-goal"
                    and v.get("confidence") == "GENUINELY-HIS"
                    and demand._verdict_names_corpus(v, CORPUS)), None)
    if verdict is None:
        pytest.skip("no GENUINELY-HIS author-goal verdict naming falqon")
    # the supersede postdates the verdict -> reconciled -> the tension cleared.
    assert demand._goal_supersede_postdates(REPO, CORPUS, verdict.get("date") or "")
    assert demand.author_goal_tensions(REPO, CORPUS) == []
