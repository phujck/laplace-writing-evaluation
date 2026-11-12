"""Unit tests for the knowledge-digestion pipeline: transcript_digest (the mouth)
and level_tender (the scale judge)."""

from __future__ import annotations

import importlib.util
import json
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SKILLS = _REPO / "src" / "laplace" / "pipeline" / "canon" / "skills"


def _load(rel: str):
    path = _SKILLS / rel
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TRANSCRIPT = textwrap.dedent(
    """\
    # Session notes

    Gerard: I think we settled that the residual is the inter-scale coupling. Let's go with that.
    eigen: The Fisher metric defines the steepest-descent direction on the parameter manifold.
    Gerard: The eigenvalue of the return map is still the open fork, we'll defer it, it is undecided.
    Gerard: Next session we should ingest the transcripts. First task when back is to wire the engine.
    eigen: Retention note: the framing was kept, the claim was rewritten toward the line.
    """
)


# --------------------------------------------------------------------------
# transcript_digest
# --------------------------------------------------------------------------
def test_digest_partitions_and_archives(tmp_path: Path):
    digest = _load("transcript_digest/scripts/digest.py")
    src = tmp_path / "t.md"
    src.write_text(TRANSCRIPT, encoding="utf-8")
    out = tmp_path / "digest"
    arch = tmp_path / "archive"
    rc = digest.digest(str(src), str(out), str(arch), "t1", 120_000)
    assert rc == 0

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    pc = manifest["partition_counts"]
    # The transcript exercises every routing partition.
    assert pc["decisions"] >= 1      # "we settled ... Let's go with"
    assert pc["forks"] >= 1          # "open fork ... defer ... undecided"
    assert pc["todos"] >= 1          # "Next session ... First task when back"
    assert pc["concepts"] >= 1       # the Fisher-metric claim
    assert pc["retention"] >= 1      # "kept ... rewritten toward the line"
    assert pc["author_voice"] >= 1   # Gerard's turns

    # The raw is archived verbatim, and the manifest carries the integrity hash.
    archived = arch / "t1.md"
    assert archived.read_text(encoding="utf-8") == TRANSCRIPT
    import hashlib
    assert manifest["sha256"] == hashlib.sha256(TRANSCRIPT.encode()).hexdigest()
    assert manifest["archived_to"].endswith("t1.md")


def test_digest_emits_skeleton_not_distillation(tmp_path: Path):
    """The digest is candidates only - it never invents a distilled stub."""
    digest = _load("transcript_digest/scripts/digest.py")
    src = tmp_path / "t.md"
    src.write_text(TRANSCRIPT, encoding="utf-8")
    out = tmp_path / "digest"
    digest.digest(str(src), str(out), None, "t1", 120_000)
    skel = (out / "skeleton.md").read_text(encoding="utf-8")
    assert "# Digest skeleton: t1" in skel
    assert "## concepts" in skel and "## forks" in skel
    # candidates are verbatim transcript lines, not summaries
    assert "Fisher metric" in skel


def test_digest_speaker_attribution(tmp_path: Path):
    digest = _load("transcript_digest/scripts/digest.py")
    segs = digest.segment(TRANSCRIPT)
    speakers = {s for s, _ in segs if s}
    assert "gerard" in speakers and "eigen" in speakers


# --------------------------------------------------------------------------
# level_tender
# --------------------------------------------------------------------------
FIXTURE_BIB = textwrap.dedent(
    """\
    @article{alpha2020plateau,
      author = {A, A}, title = {Barren plateaus in deep circuits}, year = {2020},
      tldr = {x}, claim = {Deep circuits show barren plateaus with vanishing gradient variance.},
      summary = {s}, status = {borrowed}, cluster = {barren_plateaus},
      keywords = {barren_plateaus, gradient, variance, trainability},
      provenance = {p}, added = {2026-06-04}, scout = {eigen}}
    @article{beta2021sim,
      author = {B, B}, title = {Classical simulability of circuits}, year = {2021},
      tldr = {x}, claim = {Plateau-free circuits are classically simulable via pauli propagation.},
      summary = {s}, status = {borrowed}, cluster = {classical_simulability},
      keywords = {classical_simulability, pauli, surrogate, simulable},
      provenance = {p}, added = {2026-06-04}, scout = {eigen}}
    @article{gamma2019rg,
      author = {G, G}, title = {Renormalization and learning}, year = {2019},
      tldr = {x}, claim = {Coarse-graining renormalization maps onto deep network depth.},
      summary = {s}, status = {borrowed}, cluster = {renormalization_and_learning},
      keywords = {renormalization, coarse_graining, learning, compression},
      provenance = {p}, added = {2026-06-04}, scout = {eigen}}
    """
)
FIXTURE_KEYWORDS = textwrap.dedent(
    """\
    themes:
      trainability_and_simulability:
        label: Trainability and simulability
        clusters: [barren_plateaus, classical_simulability]
      learning_theory:
        label: Learning theory
        clusters: [renormalization_and_learning]
    clusters:
      barren_plateaus: {label: Barren plateaus}
      classical_simulability: {label: Classical simulability}
      renormalization_and_learning: {label: Renormalization and learning}
    """
)


@pytest.fixture
def fixture_corpus(tmp_path: Path) -> Path:
    (tmp_path / "corpus.bib").write_text(FIXTURE_BIB, encoding="utf-8")
    (tmp_path / "keywords.yaml").write_text(FIXTURE_KEYWORDS, encoding="utf-8")
    return tmp_path / "corpus.bib"


def test_level_tender_lower_when_one_node_dominates(fixture_corpus: Path):
    lt = _load("level_tender/scripts/level_tender.py")
    rec = lt.tend(
        "Barren plateaus in deep circuits with vanishing gradient variance and trainability loss.",
        str(fixture_corpus),
    )
    assert rec["action"] == "lower"
    assert rec["target"] == "alpha2020plateau"


def test_level_tender_lift_when_cross_cutting(fixture_corpus: Path):
    lt = _load("level_tender/scripts/level_tender.py")
    # vocabulary drawn comparably from BOTH the barren_plateaus and the
    # classical_simulability clusters - a cross-cutting stub.
    rec = lt.tend(
        "Trainability and gradient variance versus pauli surrogate and classical simulable circuits.",
        str(fixture_corpus),
    )
    assert rec["action"] == "lift"
    spanned = {c["cluster"] for c in rec["top_clusters"][:2]}
    assert spanned == {"barren_plateaus", "classical_simulability"}
    # the lift target resolves to the coarser node spanning them (the theme).
    assert rec["target"] == "trainability_and_simulability"


def test_level_tender_new_when_no_overlap(fixture_corpus: Path):
    lt = _load("level_tender/scripts/level_tender.py")
    rec = lt.tend("Sourdough fermentation relies on wild yeast colonies.", str(fixture_corpus))
    assert rec["action"] == "new"
    assert rec["target"] is None


def test_level_tender_place_at_single_cluster(fixture_corpus: Path):
    lt = _load("level_tender/scripts/level_tender.py")
    # renormalization_and_learning vocabulary, one cluster, not dominated by one ref enough to lower
    rec = lt.tend("Compression and coarse-graining as a learning principle.", str(fixture_corpus))
    assert rec["action"] in ("place", "lower")  # learning cluster; single-cluster region
    assert rec["top_clusters"][0]["cluster"] == "renormalization_and_learning"
