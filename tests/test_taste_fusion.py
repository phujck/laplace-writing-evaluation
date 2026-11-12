"""W-TASTE — the taste channel threaded to the implicit substrate.

His ruling (2026-07-22): the loop closes against its own judgement, fuelled by the corpus
of his implicit tastes and standards. These tests prove :mod:`laplace.engine.taste_retrieval`
(and :func:`laplace.engine.superego.assemble_packet` over it) reaches PAST keyword overlap over
his explicit rulings into the wider substrate — the stage stores of his corpus, the
architecture / voice / house-style profiles, and his overrules of the machine — and that
the seal holds (refs-only, bounded quote, capped channel, stale metric never applied).

The embedding path is exercised with a small DETERMINISTIC bag-of-vocabulary backend so the
ranking is controllable and hermetic (no vendored model, no network); the offline path is
exercised by forcing the backend to ``None``. Both are the real selection code.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.engine import superego, taste_retrieval

# --------------------------------------------------------------------------- the fake geometry
_VOCAB = [
    "introduction", "manuscript", "opens", "runway", "contribution", "register",
    "process", "vocabulary", "derivation", "influence", "functional", "appendix",
    "bibliography", "keys",
]


def _bag(text: str) -> list[float]:
    """A unit bag-of-vocab vector — deterministic, so cosine reflects shared vocabulary.
    A text sharing no vocab with the query gives the zero vector (cosine 0, below floor)."""
    low = str(text).lower()
    v = [float(low.count(w)) for w in _VOCAB]
    n = sum(x * x for x in v) ** 0.5
    return [x / n for x in v] if n else v


class _FakeBackend:
    name = "fake:bag-of-vocab"

    def query(self, text: str) -> list[float]:
        return _bag(text)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_bag(t) for t in texts]


@pytest.fixture(autouse=True)
def _clear_embed_cache():
    taste_retrieval._EMBED_CACHE.clear()
    yield
    taste_retrieval._EMBED_CACHE.clear()


# --------------------------------------------------------------------------- substrate builder
def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _seed_substrate(root: Path) -> None:
    """A tiny but complete substrate: rulings (one register ruling, one author-taste
    overrule, one unrelated noise row), a promise ask, an architecture profile with a
    his-confirmed and a reconstructed field, and one stage store with precomputed vectors
    in the SAME bag space so store rows rank against a claim."""
    # -- proxy verdicts: register ruling, overrule (author-taste), noise
    rulings = [
        {"id": "PV-register", "date": "2026-07-21", "kind": "author-law",
         "question": "the manuscript register",
         "ruling": "process vocabulary never enters the rendered prose; the register stays "
                   "confident, not an exercise in bland assertion"},
        {"id": "PV-overrule-appendix", "date": "2026-07-22", "kind": "author-taste",
         "question": "derivation placement and the compression license",
         "ruling": "I am favouring derivations made explicitly in appendices; you can only "
                   "compress a derivation when the apposite literature supports it in citation"},
        {"id": "PV-noise", "date": "2026-07-20",
         "question": "an unrelated matter about bibliography keys",
         "ruling": "mint the bibliography keys British"},
    ]
    _write(root / "proxy_verdicts.jsonl",
           "\n".join(json.dumps(r) for r in rulings) + "\n")

    _write(root / "contract" / "promises.jsonl", json.dumps(
        {"id": "PRM-intro", "date": "2026-07-22",
         "ask": "the manuscript introduction must open on the contribution"}) + "\n")

    # -- architecture profile: one his-confirmed field, one reconstructed field
    arch = """schema: author-architecture/0.1
version: "1.0 (2026-07-22)"
profile:
  introduction_shape:
    summary: >-
      He opens on the contribution, not on a long runway. The first section is an
      introduce-motivate section that states the manuscript's contribution early.
    evidence:
      observation: "confirmed-his: the introduction opens on the contribution"
  derivation_granularity:
    summary: >-
      The license to compress a derivation is conditional on apposite citation; otherwise
      the derivation goes explicit in an appendix.
    evidence:
      observation: "reconstructed from the derivation_walk store"
"""
    _write(root / "profiles" / "author_architecture.yaml", arch)

    # -- one stage store + precomputed embeddings in the same bag space
    store_rows = [
        {"row_id": "SA-p-s0", "embed_text": "Introduction. This manuscript opens on the "
         "contribution and states the result before the runway of background.",
         "form": {"job": "introduce-motivate", "title": "Introduction"},
         "provenance": {"paper_id": "sample-paper"}},
        {"row_id": "SA-p-s3", "embed_text": "Derivation of the classical limit from the "
         "influence functional; the appendix carries the explicit derivation.",
         "form": {"job": "derive-the-classical-limit"},
         "provenance": {"paper_id": "sample-paper"}},
    ]
    sdir = root / "corpus_stores" / "section_architecture"
    _write(sdir / "sample-paper.jsonl",
           "\n".join(json.dumps(r) for r in store_rows) + "\n")
    _write(sdir / "embeddings.json", json.dumps({
        "backend": "fake:bag-of-vocab", "dim": len(_VOCAB),
        "items": {r["row_id"]: _bag(r["embed_text"]) for r in store_rows}}))


# --------------------------------------------------------------------------- the tests
def _kws(*words: str) -> set[str]:
    return set(words)


def test_manuscript_structure_claim_pulls_architecture_profile_row(tmp_path):
    """A manuscript-structure claim reaches the architecture profile — the relevant slice
    of how HE actually writes, not just a keyword hit over his explicit rulings."""
    _seed_substrate(tmp_path)
    claim = "The manuscript introduction opens on a long runway before the contribution."
    out = taste_retrieval.retrieve_taste(
        tmp_path, _kws("introduction", "manuscript", "contribution"), claim,
        cap=6, backend=_FakeBackend())
    srcs = {e["source"] for e in out["entries"]}
    assert "profiles/author_architecture.yaml" in srcs, (
        "the manuscript-structure claim did not reach the architecture profile — the "
        "implicit substrate never surfaced")
    intro = [e for e in out["entries"]
             if e["source"] == "profiles/author_architecture.yaml"
             and e["ref"] == "introduction_shape"]
    assert intro, "the introduction_shape field (the on-point row) is absent"
    # profile fields ride as typed rows: the field name is the ref, the his-confirmed flag
    # rides the quote prefix.
    assert intro[0]["quote"].startswith("[historical confirmation assertion]"), (
        "legacy observation prose remains an assertion, not fresh human authority")
    assert out["provenance"]["ranking"] == "embedding"


def test_register_claim_pulls_the_relevant_pv_rows(tmp_path):
    """A register claim surfaces the register ruling (the explicit channel still works)."""
    _seed_substrate(tmp_path)
    out = taste_retrieval.retrieve_taste(
        tmp_path, _kws("register"), "does the manuscript register stay confident",
        cap=6, backend=_FakeBackend())
    refs = {e["ref"] for e in out["entries"]}
    assert "PV-register" in refs
    assert "PV-noise" not in refs                      # unrelated ruling not dragged in


def test_overrule_always_surfaces_prefixed(tmp_path):
    """A place he corrected the machine is the highest-signal taste: a matching overrule is
    ALWAYS in the packet, marked, riding the reserved top slot — even amid the substrate."""
    _seed_substrate(tmp_path)
    out = taste_retrieval.retrieve_taste(
        tmp_path, _kws("derivation", "appendix", "compression"),
        "how should a derivation be compressed or placed in an appendix",
        cap=6, backend=_FakeBackend())
    over = [e for e in out["entries"] if e["ref"] == "PV-overrule-appendix"]
    assert over, "the author-taste overrule did not surface"
    assert over[0]["quote"].startswith("[his-overrule]"), "the overrule must be marked"
    assert "PV-overrule-appendix" in out["provenance"]["overrules_forced"], (
        "the matching overrule must ride the reserved top slot, outranking similarity")


def test_offline_fallback_degrades_marked(tmp_path):
    """No model → keyword overlap is the fallback, MARKED degraded in the provenance, and
    the embedding-only substrate rows (no keyword) do not silently ride."""
    _seed_substrate(tmp_path)
    out = taste_retrieval.retrieve_taste(
        tmp_path, _kws("register"), "the manuscript register",
        cap=6, backend=None)
    assert out["provenance"]["ranking"] == "keyword-degraded"
    assert out["provenance"]["model"] is None
    refs = {e["ref"] for e in out["entries"]}
    assert "PV-register" in refs                        # keyword hit still surfaces
    # a store row shares no keyword with the claim → it must NOT ride the degraded channel
    assert not any(e["source"].startswith("corpus_stores") for e in out["entries"])


def test_metric_absent_is_the_identity_special_case(tmp_path):
    """No ``.metric_M.npz`` on disk → the identity special case: ranking is raw cosine and
    the packet SAYS SO (M = I, nothing applied)."""
    _seed_substrate(tmp_path)                                    # seeds no metric file
    out = taste_retrieval.retrieve_taste(
        tmp_path, _kws("introduction"), "the introduction shape", cap=6,
        backend=_FakeBackend())
    metric = out["provenance"]["metric"]
    assert metric["state"] == "absent"
    assert metric["file"] == ".metric_M.npz"
    assert "raw cosine" in metric["reason"]


def _seed_metric(root: Path, *, fresh: bool) -> None:
    """Write a bag-space metric ``.metric_M.npz`` and a basis ``.self_embeddings.json`` with
    the requested mtime ordering. The metric couples the ``derivation`` axis onto the
    ``contribution`` axis, so ``q'Mv`` for a derivation claim reaches a contribution row that
    RAW cosine (M = I) would score at zero — the rerank is observable, not just labelled."""
    import os
    import time

    import numpy as np

    from laplace.representation.embed_router import CACHE_FILE, METRIC_FILE, _METRIC
    _METRIC.clear()                                              # bust the mtime-keyed cache
    d = len(_VOCAB)
    M = np.eye(d, dtype="float32")
    M[_VOCAB.index("derivation"), _VOCAB.index("contribution")] = 2.0
    np.savez(root / METRIC_FILE, M=M)
    (root / CACHE_FILE).write_text("{}", encoding="utf-8")
    from laplace.representation.embed_router import _file_digest
    (root / ".metric_pairs.json").write_text("{}")
    (root / ".metric_M.receipt.json").write_text(json.dumps({"pending": {}, "banked": {
        "shipped": True, "metric_hash": _file_digest(root / METRIC_FILE),
        "pairs_handle": _file_digest(root / ".metric_pairs.json"),
        "store_after": {CACHE_FILE: _file_digest(root / CACHE_FILE)}}}))
    if not fresh:
        (root / CACHE_FILE).write_text('{"moved": true}')
    now = time.time()
    if fresh:                                                    # metric newer than basis
        os.utime(root / CACHE_FILE, (now - 100, now - 100))
        os.utime(root / METRIC_FILE, (now, now))
    else:                                                        # metric older than basis
        os.utime(root / METRIC_FILE, (now - 100, now - 100))
        os.utime(root / CACHE_FILE, (now, now))


def test_fresh_metric_is_applied_as_qMv(tmp_path):
    """A metric bound to the current basis is FRESH: it is applied as ``q'Mv``, and the bend
    reranks — a derivation claim reaches the contribution store row the coupling lifts, one
    that raw cosine scores at zero (the metric-redistill producer act, WO-20260721-222252)."""
    _seed_substrate(tmp_path)
    _seed_metric(tmp_path, fresh=True)
    out = taste_retrieval.retrieve_taste(
        tmp_path, _kws("derivation"), "how is the derivation placed", cap=6,
        backend=_FakeBackend())
    metric = out["provenance"]["metric"]
    assert metric["state"] == "applied-fresh"
    assert "q'Mv" in metric["reason"]
    # the coupled contribution row surfaces ONLY because M bent the query onto its axis.
    intro = [e for e in out["entries"]
             if e["source"].startswith("corpus_stores") and e["ref"] == "SA-p-s0"]
    assert intro, "the fresh metric did not rerank the coupled row into the packet"


def test_mismatched_metric_refuses_before_taste_scoring(tmp_path):
    """A moved basis must not silently change the scoring geometry."""
    from laplace.representation.embed_router import MetricGenerationMismatch
    _seed_substrate(tmp_path)
    _seed_metric(tmp_path, fresh=False)
    with pytest.raises(MetricGenerationMismatch, match="published metric generation"):
        taste_retrieval.retrieve_taste(
            tmp_path, _kws("derivation"), "how is the derivation placed", cap=6,
            backend=_FakeBackend())


def test_caps_and_refs_only_discipline(tmp_path):
    """The seal holds: the channel is capped, every entry is refs-only (exactly the four
    keys), and no quote exceeds the bound — the packet carries the SLICE, never a dump."""
    _seed_substrate(tmp_path)
    # a store with many rows so the cap actually binds
    rows = [{"row_id": f"SA-x-{i}",
             "embed_text": "manuscript introduction contribution " * 40,
             "form": {"job": "introduce"}, "provenance": {"paper_id": "big"}}
            for i in range(20)]
    sdir = tmp_path / "corpus_stores" / "section_architecture"
    _write(sdir / "big.jsonl", "\n".join(json.dumps(r) for r in rows) + "\n")
    items = json.loads((sdir / "embeddings.json").read_text())
    items["items"].update({r["row_id"]: _bag(r["embed_text"]) for r in rows})
    _write(sdir / "embeddings.json", json.dumps(items))

    out = taste_retrieval.retrieve_taste(
        tmp_path, _kws("manuscript", "introduction"),
        "the manuscript introduction contribution", cap=6, backend=_FakeBackend())
    assert len(out["entries"]) <= 6
    for e in out["entries"]:
        assert set(e.keys()) == {"source", "ref", "quote", "date"}   # refs-only
        assert len(e["quote"]) <= 400                                # bounded quote


def test_assemble_packet_integration_carries_provenance(tmp_path, monkeypatch):
    """The superego's packet carries the substrate taste channel AND its provenance, and
    stays deterministic across two calls (his determinism floor)."""
    _seed_substrate(tmp_path)
    from laplace.representation import embed_router
    monkeypatch.setattr(embed_router, "get_backend", lambda: _FakeBackend())

    p1 = superego.assemble_packet(
        tmp_path, "The manuscript introduction opens on the contribution.",
        "candidate-lock", "builder-x", keywords=["introduction", "manuscript"])
    p2 = superego.assemble_packet(
        tmp_path, "The manuscript introduction opens on the contribution.",
        "candidate-lock", "builder-x", keywords=["introduction", "manuscript"])
    assert p1 == p2                                                  # deterministic
    assert "taste_provenance" in p1["frame"]
    assert p1["frame"]["taste_provenance"]["ranking"] == "embedding"
    assert len(p1["frame"]["taste"]) <= superego._TASTE_CAP
    srcs = {e["source"] for e in p1["frame"]["taste"]}
    assert "profiles/author_architecture.yaml" in srcs
