"""Tests for laplace.engine.voice_corpus_ingest — the voice-corpus .tex -> sealed embedded passage
store, and nearest_authored_passage over the author's real prose.

The build+query mechanics run on the deterministic HashBackend (offline, no model), so these
tests exercise chunking, provenance, the sealed store, caching and cosine ranking without the
vendored bge weights. The real-model semantic evidence is produced out of band (see report).
"""

from __future__ import annotations

import json

import pytest

from laplace.engine import voice_corpus_ingest as vci
from laplace.representation.embed_router import HashBackend

# a small LaTeX fixture: markup to strip + one in-band prose paragraph that survives the band.
ALPHA_TEX = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
% a stray comment that must vanish
The wave operator evolves the quantum state through time, and this evolution operator
$U(t)$ acts on the state vector to propagate it forward.\cite{foo2020} We emphasize that the
operator formalism makes the dynamics \emph{manifestly} linear, so the state evolves by a
single application of the propagator at each and every step of the numerical simulation.
\begin{equation}
i \partial_t \psi = H \psi
\end{equation}
Too short.
\end{document}
"""

BETA_TEX = r"""
\begin{document}
Low rank approximation of the density matrix reduces the computational cost of simulating the
Fermi-Hubbard model, because truncating the singular value spectrum keeps only the dominant
correlations while discarding the negligible ones, which lets the ensemble rank truncation
method scale to substantially larger lattices than a full configuration interaction treatment.
\end{document}
"""


def _make_corpus(root):
    (root / "alpha").mkdir(parents=True)
    (root / "beta").mkdir(parents=True)
    (root / "alpha" / "main.tex").write_text(ALPHA_TEX, encoding="utf-8")
    (root / "beta" / "main.tex").write_text(BETA_TEX, encoding="utf-8")
    return root


# --------------------------------------------------------------------------- #
# strip_latex / band
# --------------------------------------------------------------------------- #
def test_strip_latex_removes_markup_keeps_prose():
    out = vci.strip_latex(ALPHA_TEX)
    assert "wave operator evolves the quantum state" in out
    assert "manifestly" in out                 # \emph{...} unwrapped
    for gone in ("\\cite", "\\emph", "\\begin", "\\section", "\\documentclass", "U(t)", "H \\psi"):
        assert gone not in out, f"{gone!r} leaked through strip_latex"
    assert "stray comment" not in out          # % comment removed


def test_prose_paragraphs_band():
    paras = vci.prose_paragraphs(ALPHA_TEX)
    assert len(paras) == 1                      # only the in-band paragraph survives
    assert paras[0].startswith("The wave operator evolves")
    assert vci.MIN_PARA <= len(paras[0]) <= vci.MAX_PARA
    assert "Too short" not in " ".join(paras)   # sub-band line dropped
    assert "Introduction" not in " ".join(paras)  # heading dropped


# --------------------------------------------------------------------------- #
# provenance + determinism (chunk_source wiring)
# --------------------------------------------------------------------------- #
def test_chunk_source_is_wired():
    cs = vci.chunk_source()
    for sym in ("paragraph_spans", "byte_offsets", "chunk_id", "digest", "Span"):
        assert hasattr(cs, sym), f"chunk_source missing {sym}"


def test_passages_for_source_provenance_and_determinism(tmp_path):
    root = _make_corpus(tmp_path)
    recs1 = vci.passages_for_source(root / "alpha" / "main.tex", root)
    recs2 = vci.passages_for_source(root / "alpha" / "main.tex", root)
    assert len(recs1) == 1
    r = recs1[0]
    assert r["slug"] == "alpha"
    assert r["source_handle"] == "VOICE-ALPHA"
    assert r["file"] == "main.tex"
    assert r["passage_id"].startswith("VOICE-ALPHA-P")
    assert r["text"].startswith("The wave operator evolves")
    # stable ids/hashes for unchanged content
    assert [x["passage_id"] for x in recs1] == [x["passage_id"] for x in recs2]
    assert [x["sha256"] for x in recs1] == [x["sha256"] for x in recs2]


# --------------------------------------------------------------------------- #
# build store + query
# --------------------------------------------------------------------------- #
def test_build_store_writes_sealed_artifacts(tmp_path):
    root = _make_corpus(tmp_path / "exemplars")
    cache = tmp_path / "cache"
    summary = vci.build_store(root, cache, backend=HashBackend())

    assert summary["passage_count"] == 2
    assert summary["source_count"] == 2
    store = cache / vci._STORE_SUBDIR
    for name in ("passages.jsonl", "manifest.json", "embeddings.json"):
        assert (store / name).is_file()

    # manifest carries provenance but NO passage text; passages.jsonl carries the text.
    manifest = json.loads((store / "manifest.json").read_text())
    assert manifest["schema_version"] == vci.SCHEMA
    assert manifest["passage_count"] == 2
    assert all("text" not in p for p in manifest["passages"])
    rows = [json.loads(l) for l in (store / "passages.jsonl").read_text().splitlines()]
    assert all(r["text"] for r in rows)

    emb = json.loads((store / "embeddings.json").read_text())
    assert emb["backend"] == HashBackend.name
    assert emb["dim"] == HashBackend.dim
    assert len(emb["items"]) == 2


def test_embedding_cache_reused_on_second_build(tmp_path):
    root = _make_corpus(tmp_path / "exemplars")
    cache = tmp_path / "cache"
    first = vci.build_store(root, cache, backend=HashBackend())
    assert first["embedded_now"] == 2
    second = vci.build_store(root, cache, backend=HashBackend())
    assert second["embedded_now"] == 0          # nothing re-embedded (content-hash cache hit)


def test_nearest_authored_passage_ranks_his_prose(tmp_path):
    root = _make_corpus(tmp_path / "exemplars")
    cache = tmp_path / "cache"
    vci.build_store(root, cache, backend=HashBackend())

    hits = vci.nearest_authored_passage(
        "the operator evolves the state", k=2, cache_root=cache, backend=HashBackend()
    )
    assert len(hits) == 2
    # the operator/evolves/state paragraph is his nearest prose, not the low-rank one
    assert hits[0]["slug"] == "alpha"
    assert "wave operator evolves" in hits[0]["text"]
    # cosine descending, real provenance carried
    assert hits[0]["cos"] >= hits[1]["cos"]
    assert hits[0]["file"] == "main.tex"
    assert hits[0]["paragraph_start"] >= 1


def test_query_before_ingest_errors(tmp_path):
    with pytest.raises(SystemExit):
        vci.nearest_authored_passage("anything", cache_root=tmp_path / "empty",
                                     backend=HashBackend())


def test_build_store_no_tex_errors(tmp_path):
    (tmp_path / "empty").mkdir()
    with pytest.raises(SystemExit):
        vci.build_store(tmp_path / "empty", tmp_path / "cache", backend=HashBackend())


# --------------------------------------------------------------------------- #
# THE EXTRACTION LENS KEEPS THE MATH (WO-20260820-extraction-lens-keeps-math)
# --------------------------------------------------------------------------- #
#: The measured mutilation, verbatim from the blind bench (PP-ss-p0003): the default strip deletes
#: every math span, which removes the NUMBERS mid-sentence and leaves the sentence grammatical, so
#: nothing downstream can tell that anything was lost.
_MUTILATED = (
    "This has a pulse duration of $190$ fs, $400~\\mu$J pulse energy "
    "and a $50~$kHz repetition rate.\n"
)


def test_default_strip_deletes_the_numbers_mid_sentence():
    """The defect, pinned: the loss is SILENT — grammatical prose with the physics removed."""
    out = vci.strip_latex(_MUTILATED)
    assert "pulse duration of fs" in " ".join(out.split())
    for number in ("190", "400", "50"):
        assert number not in out


def test_keep_math_keeps_the_numbers_verbatim():
    out = vci.strip_latex(_MUTILATED, keep_math=True)
    assert "$190$ fs" in out
    assert "$400~\\mu$J" in out
    assert "$50~$kHz" in out


def test_keep_math_is_paragraph_identical_to_the_default_strip():
    """THE RE-MINT'S LOAD-BEARING INVARIANT. A stored row is re-minted by its PARAGRAPH INDEX, so
    the two renderings must have the same paragraphs in the same order — a display equation is a
    paragraph break under both, and only the text inside a paragraph changes."""
    tex = (
        "\\begin{document}\n"
        "First paragraph with $x=1$ inline math and more words here.\n"
        "\\begin{equation}\\label{eq:a} E = mc^2 \\end{equation}\n"
        "Second paragraph continues after the display, with $T=300$ K.\n"
        "\n"
        "Third paragraph, no math at all, stands on its own.\n"
        "\\end{document}\n"
    )
    plain = vci.strip_latex(tex).split("\n\n")
    kept = vci.strip_latex(tex, keep_math=True).split("\n\n")
    assert len(plain) == len(kept)
    for a, b in zip(plain, kept):
        assert " ".join(a.split()) == " ".join(vci.demath(b).split())


def test_keep_math_drops_the_non_prose_environments():
    """Only MATH is protected. A figure/tabular payload is not his notation and stays deleted —
    restoring it verbatim would drown the row it is supposed to make findable."""
    tex = ("\\begin{document}\nProse with $a=2$.\n"
           "\\begin{figure}\\includegraphics{plot.png}\\caption{A plot}\\end{figure}\n"
           "\\end{document}\n")
    out = vci.strip_latex(tex, keep_math=True)
    assert "$a=2$" in out
    assert "includegraphics" not in out and "plot.png" not in out


def test_math_segments_treats_a_spaced_span_as_one_unit():
    """A math span holding spaces is ONE segment — the trap a whitespace-first tokeniser falls
    into (it would read ``$\\hat c_j \\hat c_k$`` as two words and mis-budget the window)."""
    segs = vci.math_segments("we take $\\hat{c}_j \\hat{c}_k$ as the operator")
    assert [s for m, s in segs if m] == ["$\\hat{c}_j \\hat{c}_k$"]
    assert "".join(s for _, s in segs) == "we take $\\hat{c}_j \\hat{c}_k$ as the operator"


def test_passages_keep_math_without_moving_the_row_set(tmp_path):
    """The re-mint is safe only if keep_math changes TEXT, never rows: same count, same paragraph
    indices, same order — the length band is judged on the math-free rendering for exactly this."""
    root = _make_corpus(tmp_path / "exemplars")
    for tex in sorted(root.rglob("*.tex")):
        plain = vci.passages_for_source(tex, root)
        kept = vci.passages_for_source(tex, root, keep_math=True)
        assert len(plain) == len(kept)
        assert [p["paragraph_start"] for p in plain] == [k["paragraph_start"] for k in kept]
        for p, k in zip(plain, kept):
            assert p["text"] == " ".join(vci.demath(k["text"]).split())
