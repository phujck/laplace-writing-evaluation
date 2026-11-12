"""Unit tests for reconstruction_fitness - the inverse of digestion, scored.

Covers the mechanical backing (parse the digest skeleton, band placement confidence, build the
blind packet, surface each concept's proposed neighbours) and the telemetry reconstruction
producer (the reinforcement record + the fidelity fates)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SKILLS = _REPO / "src" / "laplace" / "pipeline" / "canon" / "skills"
_RECON = _SKILLS / "reconstruction_fitness" / "scripts" / "reconstruct.py"
_ADJ = _SKILLS / "reconstruction_fitness" / "scripts" / "adjudicate.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SKELETON = """\
# Digest skeleton: t

## concepts  (2 candidate(s))
- [Gerard] The Fisher metric defines the steepest-descent direction on the manifold.
- Barren plateaus are an uncertainty principle between loss resolution and operator scale.

## decisions  (1 candidate(s))
- [Gerard] Go with the residual as the inter-scale coupling.

## forks  (1 candidate(s))
- The eigenvalue of the return map is the open fork.
"""


def test_parse_skeleton_partitions_and_strips_speaker():
    mod = _load(_RECON)
    parts = mod.parse_skeleton(SKELETON)
    assert set(parts) == {"concepts", "decisions", "forks"}
    assert len(parts["concepts"]) == 2
    # the [speaker] tag is stripped from the stub
    assert parts["concepts"][0].startswith("The Fisher metric")
    assert parts["decisions"][0].startswith("Go with the residual")


def test_confidence_band_thresholds():
    mod = _load(_RECON)
    assert mod.confidence_band(0.3) == "placed"
    assert mod.confidence_band(0.1) == "weak"
    assert mod.confidence_band(0.0) == "ungrounded"


def test_run_builds_blind_packet_with_neighbours_and_logs(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    ddir = tmp_path / "digest"
    ddir.mkdir()
    (ddir / "skeleton.md").write_text(SKELETON, encoding="utf-8")

    mod = _load(_RECON)
    corpus = str(_REPO / "corpus" / "corpus.bib")
    rc = mod.run(str(ddir), corpus, None, "t", do_log=True)
    assert rc == 0

    brief = (ddir / "reconstruction_brief.md").read_text(encoding="utf-8")
    # the packet is digest-only (no raw transcript) and carries the neighbour-wiring test
    assert "blind reconstructor" in brief
    assert "TRUE neighbours" in brief
    assert "neighbours:" in brief

    from laplace.engine import telemetry
    evs = [e for e in telemetry.events() if e.get("phase") == "reconstruction"]
    assert len(evs) == 1
    assert evs[0]["caller"] == "eigen"
    assert evs[0]["target"] == "t"
    # the reinforcement record: the nodes this ghost called
    assert "activated" in evs[0]


def test_reconstruction_fates_and_producer(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    # The stampable set is a SUPERSET of the frozen base three (F14 layers the derived codebook over
    # it), and the base weights are never moved by the layering.
    assert {"faithful", "partial", "confabulated"} <= set(telemetry.reconstruction_fates())
    assert telemetry.RECONSTRUCTION_FATES == {"faithful": 0.9, "partial": 0.6, "confabulated": 0.2}
    merged = telemetry.reconstruction_fates()
    assert (merged["faithful"], merged["partial"], merged["confabulated"]) == (0.9, 0.6, 0.2)
    ev = telemetry.reconstruction(fate="partial", target="s", caller="adjudicator",
                                  nodes=["a", "b"], gap="lost the derivation",
                                  cycle=2, similarity=0.21)
    assert ev["fate"] == "partial"
    assert ev["value"] == telemetry.RECONSTRUCTION_FATES["partial"]
    assert ev["caller"] == "adjudicator"
    assert ev["cycle"] == 2
    assert ev["similarity"] == 0.21
    assert ev["activated"] == ["a", "b"]
    assert ev["gap"] == "lost the derivation"
    with pytest.raises(ValueError):
        telemetry.reconstruction(fate="nonsense")


def test_adjudicator_is_blind_and_scores_similarity():
    """The adjudicator sees only two artifacts; identical text -> faithful, disjoint -> confabulated,
    and it surfaces the lost / added (confabulation-risk) content."""
    mod = _load(_ADJ)
    original = ("The regularised loss is an action with a local generator, the Loss Hamiltonian. "
                "Loss value and operator scale are conjugate, so a barren plateau is an uncertainty "
                "principle. The cure is to tunnel through the barrier.")
    # a faithful ghost - same phrasing recurs
    same = mod.adjudicate(original, original)
    assert same["similarity"] == 1.0
    assert same["proxy_fate"] == "faithful"
    # a confabulated ghost - disjoint content, the added tokens are flagged
    ghost = "Quantum reservoir computing encodes data in a fixed nonlinear dynamical substrate."
    bad = mod.adjudicate(original, ghost)
    assert bad["proxy_fate"] == "confabulated"
    assert "reservoir" in bad["added"]
    assert any(w in bad["lost"] for w in ("loss", "barren", "hamiltonian", "conjugate"))


def test_adjudicate_run_logs_proxy(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    orig = tmp_path / "orig.md"
    ghost = tmp_path / "ghost.md"
    orig.write_text("The metric is the natural gradient; the potential is the loss landscape.",
                    encoding="utf-8")
    ghost.write_text("The natural gradient defines the metric on the landscape.", encoding="utf-8")
    mod = _load(_ADJ)
    rc = mod.main([str(orig), str(ghost), "--target", "t", "--cycle", "1"])
    assert rc == 0
    from laplace.engine import telemetry
    evs = [e for e in telemetry.events()
           if e.get("phase") == "reconstruction" and e.get("caller") == "adjudicator-mechanical"]
    assert len(evs) == 1
    assert evs[0]["cycle"] == 1
    assert "similarity" in evs[0]


# ---------------------------------------------------------------------------
# the network-trace producer - the shape banked ahead of its consumer (the fork)
# ---------------------------------------------------------------------------
def test_trace_verdicts_and_producer(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    # The verdict map is the survived-vs-earned axis run on cross-level consistency.
    assert set(telemetry.TRACE_VERDICTS) == {"consistent", "drifted", "inconsistent"}

    # A segment banked WITHOUT a verdict (fires now, judged later).
    seg = telemetry.trace(
        span="spawn", caller="eigen", role="orchestrator",
        request="project the kernel letter", spawned=["guide-1"],
        consulted=["canon://skills/orchestrated_generation"], cycle=3,
    )
    assert seg["span"] == "spawn"
    assert seg["role"] == "orchestrator"
    assert seg["spawned"] == ["guide-1"]
    assert seg["consulted"] == ["canon://skills/orchestrated_generation"]
    assert seg["cycle"] == 3
    assert "verdict" not in seg  # optional: banked ahead of judgement

    # The supplier's consistency-verdict, run backward up the supply channel.
    judged = telemetry.trace(
        span="judge", caller="global_self", returned="ghost-out",
        verdict="drifted", by="author", reason="intent-drift: answered a narrower question",
    )
    assert judged["verdict"] == "drifted"
    assert judged["value"] == telemetry.TRACE_VERDICTS["drifted"]
    assert judged["by"] == "author"

    with pytest.raises(ValueError):
        telemetry.trace(span="judge", verdict="nonsense")

    evs = [e for e in telemetry.events() if e.get("phase") == "trace"]
    assert len(evs) == 2


# --- the graded climb: grade_probe + seed_from_gap (the first rung's tools) ----------------------

_PROBE = _SKILLS / "reconstruction_fitness" / "scripts" / "grade_probe.py"
_SEED = _SKILLS / "reconstruction_fitness" / "scripts" / "seed_from_gap.py"

_BIB = """\
@article{objA,
  title      = {The Object Under Test},
  cluster    = {test_cluster},
  keywords   = {alpha, beta},
  claim      = {A single load-bearing assertion holds for the system.},
  summary    = {The object derives a mechanism, states a constraint, and grounds a follow-on.},
  relations  = {extends:objB | the prior work it builds on; motivates:objC | the follow-on},
}

@article{objB,
  title      = {The Prior Work},
  tldr       = {Establishes the groundwork the object extends.},
}
"""


def test_grade_probe_parses_records_and_relations():
    mod = _load(_PROBE)
    corpus = mod.parse_corpus(_BIB)
    assert set(corpus) == {"objA", "objB"}
    assert corpus["objA"]["claim"].startswith("A single load-bearing")
    rels = mod.parse_relations(corpus["objA"]["relations"])
    assert rels == [("extends", "objB"), ("motivates", "objC")]


def test_grade_probe_brief_is_blind_and_carries_the_neighbourhood():
    mod = _load(_PROBE)
    corpus = mod.parse_corpus(_BIB)
    nbhd = mod.neighbourhood(corpus["objA"], corpus, "objA")
    # the distributed code carries the neighbour, only the object's TITLE, never its held-out grades
    assert "The Prior Work" in nbhd
    assert "Establishes the groundwork" in nbhd
    assert corpus["objA"]["claim"] not in nbhd
    assert corpus["objA"]["summary"] not in nbhd
    brief = mod.brief("summary", "the mechanism in full", nbhd)
    assert "SEALED" in brief and "The Prior Work" in brief
    assert corpus["objA"]["summary"] not in brief  # the target grade is never shown


def test_seed_from_gap_prepends_scaffold_and_residual():
    mod = _load(_SEED)
    original_k = "A single load-bearing assertion about the constraint holds for the driven system."
    ghost_k = "There is an assertion about the system, though the constraint is left unstated."
    base = "# Reconstruction brief: the summary\n\nrebuild the mechanism.\n"
    seeded, verdict = mod.seed(original_k, ghost_k, base)
    # the coarse reconstruction is handed down as the scaffold, ahead of the base brief
    assert seeded.startswith("## the coarse grade, reconstructed")
    assert ghost_k in seeded
    assert "the residual |r>" in seeded
    assert base.lstrip() in seeded
    # the residual carries the coarse verdict's lost tokens (here 'driven'/'constraint' were dropped)
    assert "lost" in seeded
    assert set(verdict) == {"similarity", "proxy_fate", "lost", "added"}
