"""Tests for laplace.pipeline.voice_retrieval — the retrieval-grounded voice-wash
substrate (Phase I2).

Two acceptance shapes, both on the deterministic HashBackend (offline, no model):
  * the RETRIEVED-EXEMPLARS channel is populated PER PASSAGE and DEDUPED across the
    whole document (the used-set → next-nearest on collision);
  * the FAIL-LOUD contract: an unavailable store raises rather than degrading to a
    spec-driven pass — there is NO spec-only code path.
"""

from __future__ import annotations

import pytest

from laplace.engine import voice_corpus_ingest as vci
from laplace.pipeline import voice_retrieval as vr
from laplace.representation.embed_router import HashBackend

# --------------------------------------------------------------------------- #
# a small authored corpus — six distinct-topic paragraphs of "his" prose, each
# comfortably inside the 280–2400 char voice-bearing band
# --------------------------------------------------------------------------- #
CORPUS_TEX = r"""
\begin{document}
The wave operator evolves the quantum state through time, and this evolution operator acts on
the state vector to propagate it forward. The operator formalism makes the dynamics manifestly
linear, so the state evolves by a single application of the propagator at each step of the
numerical simulation of the driven model under study here.

Low rank approximation of the density matrix reduces the computational cost of simulating the
Fermi Hubbard model, because truncating the singular value spectrum keeps only the dominant
correlations while discarding the negligible ones, which lets the ensemble rank truncation
method scale to substantially larger lattices than a full configuration interaction treatment.

The spectral gap of the Hamiltonian controls the adiabatic timescale, and a vanishing gap
forces the schedule to slow down near the avoided crossing where the two lowest eigenvalues
approach one another, so the runtime of the annealing protocol is set by the inverse square of
the minimum gap along the interpolating path between the initial and final Hamiltonians.

Measurement of the observable collapses the wavefunction onto an eigenstate of the measured
operator, and the probability of each outcome follows the Born rule as the squared overlap
between the prepared state and the corresponding eigenvector of that observable in the chosen
measurement basis of the detecting apparatus used throughout the experiment described below.

Error correction encodes a single logical qubit across many physical qubits so that a local
fault can be detected by measuring the stabilizer generators without disturbing the encoded
information, and the threshold theorem guarantees arbitrarily long computation once the physical
error rate falls below the code threshold set by the geometry of the chosen stabilizer code.

The variational ansatz parameterizes a trial wavefunction whose parameters are optimized to
minimize the expectation value of the energy, and the classical outer loop updates the circuit
angles while the quantum processor estimates the cost gradient by sampling repeated preparations
of the parameterized state across many shots on the near term device available for this study.
\end{document}
"""

# the NEUTRAL welded draft: three % <sid>-pN paragraphs across two sections, with
# LaTeX (\cite, \emph, an equation) that must be STRIPPED before embedding
FRAG_S1 = (
    "% PLAN:S1\n% NODES: def:a def:b\n\\section{One}\\label{sec:S1}\n\n"
    "% S1-p1\n"
    "The wave operator evolves the quantum state through time.\\cite{foo2020} The "
    "\\emph{operator} formalism makes the dynamics linear, and the propagator advances "
    "the state one step at a time in the simulation.\n"
    "\\begin{equation}\\label{def:a}\ni \\partial_t \\psi = H \\psi\n\\end{equation}\n\n"
    "% S1-p2\n"
    "Low rank approximation of the density matrix reduces the cost of simulating the "
    "Fermi Hubbard model by truncating the singular value spectrum to the dominant "
    "correlations.\n"
)
FRAG_S2 = (
    "% PLAN:S2\n% NODES: res:c\n\\section{Two}\\label{sec:S2}\n\n"
    "% S2-p1\n"
    "The spectral gap of the Hamiltonian controls the adiabatic timescale, and a "
    "vanishing gap slows the annealing schedule near the avoided crossing.\n"
)
ORDER = ["S1", "S2"]
FRAGMENTS = {"S1": FRAG_S1, "S2": FRAG_S2}


@pytest.fixture()
def store_cache(tmp_path):
    """Build a sealed store from the authored corpus on the deterministic backend."""
    ex = tmp_path / "exemplars" / "paper"
    ex.mkdir(parents=True)
    (ex / "main.tex").write_text(CORPUS_TEX, encoding="utf-8")
    cache = tmp_path / "cache"
    summary = vci.build_store(tmp_path / "exemplars", cache, backend=HashBackend())
    assert summary["passage_count"] == 6      # all six paragraphs survived the band
    return cache


# --------------------------------------------------------------------------- #
# paragraph_units: marker parse + LaTeX-stripped query span
# --------------------------------------------------------------------------- #
def test_paragraph_units_split_by_markers_and_strip_latex():
    units = vr.paragraph_units("S1", FRAG_S1)
    assert [u["spec_id"] for u in units] == ["S1-p1", "S1-p2"]
    assert all(u["section"] == "S1" for u in units)
    # the query span is his prose, not markup: no backslash macros, no equation,
    # no marker comment survived the strip
    for u in units:
        assert "\\" not in u["query"]
        assert "cite" not in u["query"] and "partial_t" not in u["query"]
        assert "S1-p1" not in u["query"] and "S1-p2" not in u["query"]
    assert "wave operator evolves" in units[0]["query"]
    assert "operator" in units[0]["query"]          # \emph{operator} unwrapped, kept


def test_paragraph_units_merge_groups_adjacent_markers():
    merged = ("% PLAN:S3\n% NODES: def:x\n\\section{S}\n\n"
              "% S3-p1\n% S3-p2\nOne merged paragraph carrying two plan units of "
              "content spanning both markers here.\n")
    units = vr.paragraph_units("S3", merged)
    assert len(units) == 1
    assert units[0]["markers"] == ["S3-p1", "S3-p2"]      # the join, his many-to-many model
    assert units[0]["spec_id"] == "S3-p1"


def test_paragraph_units_empty_without_markers():
    assert vr.paragraph_units("S9", "\\section{Plain}\nNo markers at all here.\n") == []


# --------------------------------------------------------------------------- #
# build_channel: populated PER PASSAGE, DEDUPED per section (his 2026-07-09
# ruling: the used-set resets at each section boundary — coverage over variety)
# --------------------------------------------------------------------------- #
def test_channel_is_per_passage_and_deduped_within_section(store_cache):
    channel, summary = vr.build_channel(
        FRAGMENTS, ORDER, k=2, cache_root=store_cache, backend=HashBackend())

    # per-passage: exactly one record per % <sid>-pN paragraph, in document order
    assert [u["spec_id"] for u in channel] == ["S1-p1", "S1-p2", "S2-p1"]
    # non-empty: every paragraph fenced its k nearest authored passages
    assert all(len(u["exemplars"]) == 2 for u in channel)
    assert all(e["text"] and e["source"] for u in channel for e in u["exemplars"])

    # DEDUPED within the section: S1's two paragraphs force four distinct
    # authored passages (next-nearest on collision); the used-set then RESETS
    # at the S2 boundary, so S2-p1 fences its true nearest even if S1 claimed it
    s1_ids = [e["id"] for u in channel if u["section"] == "S1" for e in u["exemplars"]]
    assert len(s1_ids) == 4 and len(set(s1_ids)) == 4
    ids = [e["id"] for u in channel for e in u["exemplars"]]
    assert summary["exemplars_total"] == 6
    assert summary["distinct_exemplars"] == len(set(ids))
    assert summary["paragraphs_with_exemplars"] == 3
    assert summary["cos_max"] is not None


def test_used_set_resets_per_section_coverage_over_exhaustion(store_cache):
    # k=3: S1's two paragraphs claim ALL six authored passages. Under the old
    # GLOBAL dedup S2-p1 would arrive to an exhausted store and fence nothing —
    # the ~76-paragraph ungrounded tail, one scale down. Under the per-section
    # reset S2-p1 still fences its true k nearest (his ruling: every paragraph
    # stays grounded; reuse across sections does not read as repetition).
    channel, summary = vr.build_channel(
        FRAGMENTS, ORDER, k=3, cache_root=store_cache, backend=HashBackend())
    s1_ids = [e["id"] for u in channel if u["section"] == "S1" for e in u["exemplars"]]
    assert len(set(s1_ids)) == 6                  # S1 exhausts the store alone
    s2 = next(u for u in channel if u["section"] == "S2")
    assert len(s2["exemplars"]) == 3              # the tail is NOT left ungrounded
    assert summary["paragraphs_with_exemplars"] == 3
    assert summary["distinct_exemplars"] == 6     # no invented passages


# --------------------------------------------------------------------------- #
# FAIL LOUD: store unavailable → raise; NEVER a spec-driven degrade
# --------------------------------------------------------------------------- #
def test_build_channel_fails_loud_without_store(tmp_path):
    with pytest.raises(SystemExit):
        vr.build_channel(FRAGMENTS, ORDER, k=2,
                         cache_root=tmp_path / "no-store", backend=HashBackend())


# --------------------------------------------------------------------------- #
# FILE-BACKED (Leg C bite C1): the retrieved substrate persists to a sidecar,
# like the weld decision sidecars / reader verdicts — not a prompt-only artefact
# --------------------------------------------------------------------------- #
def test_write_channel_sidecar_persists_channel_and_summary(store_cache, tmp_path):
    import json

    channel, summary = vr.build_channel(
        FRAGMENTS, ORDER, k=2, cache_root=store_cache, backend=HashBackend())
    out = tmp_path / "decisions" / vr.SIDECAR_NAME
    p = vr.write_channel_sidecar(out, channel, summary)

    assert p.exists() and p.name == "_voice_retrieval.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["channel"] == channel            # the full per-paragraph grounding
    assert data["summary"] == summary            # the retrieval summary rides along
    assert data["summary"]["exemplars_total"] == 6


def test_weld_ships_neutral_when_store_unavailable(tmp_path):
    # the CONTRACT point: with the store down, the voice weld ships NEUTRAL
    # (neutral_fallback) and produces NO prompt — never a spec-driven "sound like
    # him" pass. Pointed at an empty cache_root, the store is unavailable by force.
    from laplace.pipeline import dispatch
    neutral = dispatch.compile_weld_dispatch("subset-sum-itqde")
    if "error" in neutral:
        pytest.skip("SSG neutral weld unavailable in this environment")
    out = dispatch.compile_weld_dispatch(
        "subset-sum-itqde", voice_on=True,
        cache_root=tmp_path / "no-store", backend=HashBackend())
    assert out["voice_on"] is True
    assert out["neutral_fallback"] is True
    assert out["reason"] == "voice_store_unavailable"
    assert "prompt" not in out                      # NO spec-driven prompt emitted
    assert "Refusing a spec-driven pass" in out["error"]
