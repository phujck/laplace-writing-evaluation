"""Phase B — the scaffold-wipe: emit-boundary erasure + verify-erasure passes."""
from __future__ import annotations

import importlib.util
import io
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
SSG_MAIN = REPO / "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"


def _load_figstyle():
    path = REPO / "synthetics papers/subset-sum-itqde/manuscript/figures/figstyle.py"
    spec = importlib.util.spec_from_file_location("ssg_figstyle", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# B2 — figure scrub in figstyle.save()
# ---------------------------------------------------------------------------
def test_save_scrubs_type_tag_and_spanning_title():
    """A figure with a type_tag stamp + a spanning ax.set_title: after save(),
    NEITHER is in the emitted vector (default erase)."""
    figstyle = _load_figstyle()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["svg.fonttype"] = "none"     # keep text as literal strings in the SVG

    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("HEADLINE_TITLE_STRIP_ME")
    figstyle.type_tag(ax, "SchematicStampXYZ")

    tmp = REPO / "tests" / "_scaffold_tmp_fig"
    try:
        figstyle.save(fig, tmp, preview=False)
        buf = io.StringIO()
        fig.savefig(buf, format="svg")
        svg = buf.getvalue()
    finally:
        tmp.with_suffix(".pdf").unlink(missing_ok=True)
        plt.close(fig)

    assert "HEADLINE_TITLE_STRIP_ME" not in svg          # spanning title erased
    assert "SchematicStampXYZ" not in svg                # epistemic stamp erased
    assert ax.get_title() == ""
    assert all(t.get_gid() != figstyle._TYPE_TAG_GID for t in ax.texts)


def test_save_gate_keeps_epistemic_labels_when_asked():
    """The gate: keep_epistemic_labels=True retains the stamp (didactic render).
    The no-titles law is UNCONDITIONAL — the title still goes."""
    figstyle = _load_figstyle()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["svg.fonttype"] = "none"

    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_title("HEADLINE_TITLE_STRIP_ME")
    figstyle.type_tag(ax, "SchematicStampXYZ")

    tmp = REPO / "tests" / "_scaffold_tmp_fig2"
    try:
        figstyle.save(fig, tmp, preview=False, keep_epistemic_labels=True)
        buf = io.StringIO()
        fig.savefig(buf, format="svg")
        svg = buf.getvalue()
    finally:
        tmp.with_suffix(".pdf").unlink(missing_ok=True)
        plt.close(fig)

    assert "SchematicStampXYZ" in svg                    # kept for the didactic build
    assert "HEADLINE_TITLE_STRIP_ME" not in svg          # title still unconditional


# ---------------------------------------------------------------------------
# B3 — caption-projection reduction in tex_backend
# ---------------------------------------------------------------------------
def test_reduce_caption_projects_to_reader_facing():
    from laplace.pipeline import tex_backend
    cap = ("Panel (a) shows the acquisition aperture over the retained nodes. "
           "Panel (b) plots the retained-node count, computed by exact "
           "diagonalisation. The figure supports the central claim that the "
           "record is independent of the resolution. It is a schematic and an "
           "exact toy example - it establishes nothing about finite-shot accuracy.")
    red = tex_backend._reduce_caption(cap)
    # Q3 (claim-support) migrated to the body
    assert any("supports the central claim" in s for s in red["to_body"])
    # the reader-facing what-shown / how-made stays
    assert "acquisition aperture" in red["reduced"]
    assert "exact diagonalisation" in red["reduced"]
    # exactly one qualification kept; the Q3 sentence is gone from the caption
    assert "establishes nothing" in red["reduced"]
    assert "supports the central claim" not in red["reduced"]


def test_render_figure_env_reduces_and_routes():
    from laplace.pipeline import tex_backend
    profile = tex_backend.load_profile()
    env = tex_backend.render_figure_env("fig:z", {
        "figure_id": "fig:z", "status": "banked", "asset": "figures/Z.pdf",
        "caption": ("What is plotted, made by exact sums. The figure supports "
                    "the claim that X holds. It establishes nothing about Y."),
        "width": "single",
    }, profile)
    assert "\\includegraphics" in env and "\\caption{" in env
    # Q3 routed to the prose stage as a marked, non-rendering comment
    assert "ROUTED-FINDING kind=caption-scaffold owning_stage=prose" in env
    assert "supports\n    the claim" in env or "supports the claim" in env
    # the rendered caption no longer carries the claim-support sentence
    caption_line = [ln for ln in env.splitlines() if ln.strip().startswith("\\caption")][0]
    assert "supports the claim" not in caption_line


def test_render_figure_env_never_empties_a_pure_qualification_caption():
    """The existing single-sentence spec caption must survive (never \\caption{})."""
    from laplace.pipeline import tex_backend
    profile = tex_backend.load_profile()
    env = tex_backend.render_figure_env("fig:q", {
        "figure_id": "fig:q", "status": "banked", "asset": "figures/Q.pdf",
        "caption": "What is plotted; how generated; what it does not establish.",
        "width": "single",
    }, profile)
    caption_line = [ln for ln in env.splitlines() if ln.strip().startswith("\\caption")][0]
    assert "What is plotted" in caption_line


# ---------------------------------------------------------------------------
# scaffold_wipe verify passes — seeded fixtures (leak → flagged; clean → not)
# ---------------------------------------------------------------------------
def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_prose_scaffold_flags_planning_objects(tmp_path):
    from laplace.pipeline import scaffold_wipe
    tex = _write(tmp_path, "m.tex", r"""
\section{Introduction}\label{sec:i}
The paper's statements are typed by evidence class throughout.
On entry the reader may assume the spectral measure; the exit state delivers the bound.
This result is exact algebra and the covariance is derived in place.
""")
    fs = scaffold_wipe.check_prose_scaffold(tex, project=None)
    kinds = {f["kind"] for f in fs}
    assert kinds == {"prose-scaffold"}
    issues = " ".join(f["issue"] for f in fs)
    assert "evidence-ledger" in issues        # "typed by evidence class"
    assert "contract" in issues               # "exit state"
    # a clean paragraph alone flags nothing
    clean = _write(tmp_path, "c.tex", r"\section{X}\label{sec:x}" + "\nThe covariance is derived in place.\n")
    assert scaffold_wipe.check_prose_scaffold(clean, project=None) == []


def test_equation_scaffold_flags_unreferenced_bare_number(tmp_path):
    from laplace.pipeline import scaffold_wipe
    tex = _write(tmp_path, "m.tex", r"""
\section{Body}\label{sec:b}
A displayed but never-referenced numbered equation:
\begin{equation}\label{eq:orphan} x = y + z \end{equation}
A referenced one:
\begin{equation}\label{eq:used} a = b \end{equation}
As shown in \eqref{eq:used}, the relation holds.
""")
    fs = scaffold_wipe.check_equation_scaffold(tex)
    quotes = {f["quote"] for f in fs}
    assert "eq:orphan" in quotes              # numbered, never \eqref'd
    assert "eq:used" not in quotes            # referenced → not flagged
    assert all(f["kind"] == "legacy-notation" for f in fs)


def test_equation_scaffold_flags_legacy_notation(tmp_path):
    from laplace.pipeline import scaffold_wipe
    tex = _write(tmp_path, "m.tex", r"""
\section{Body}\label{sec:b}
The quantity $s$, formerly denoted $\lambda$ in the legacy notation, is the location.
""")
    fs = scaffold_wipe.check_equation_scaffold(tex)
    assert any("legacy notation" in f["issue"].lower() or "formerly" in f["quote"].lower()
               for f in fs)


def test_citation_scaffold_flags_cluster_and_selfcite(tmp_path):
    from laplace.pipeline import scaffold_wipe
    tex = _write(tmp_path, "m.tex", r"""
\section{Related}\label{sec:r}
Many methods exist \cite{a2020,b2021,c2022,d2023,e2024}.

We rely on our previous work \cite{mine2019} for the construction.
""")
    fs = scaffold_wipe.check_citation_scaffold(tex)
    issues = " ".join(f["issue"] for f in fs)
    assert "cite-everything cluster" in issues
    assert "self-citation" in issues
    assert all(f["kind"] == "citation-cluster" for f in fs)


def test_matter_scaffold_flags_abstract_roadmap_and_orphan_appendix(tmp_path):
    from laplace.pipeline import scaffold_wipe
    tex = _write(tmp_path, "m.tex", r"""
\begin{abstract}
We solve the problem. The paper is organized as follows.
\end{abstract}
\section{Introduction}\label{sec:i}
Our results are typed by evidence class.
\appendix
\section{Extra derivations}\label{app:orphan}
Content nobody points to.
""")
    fs = scaffold_wipe.check_matter_scaffold(tex)
    issues = " ".join(f["issue"] for f in fs)
    assert "roadmap in the abstract" in issues
    assert "dumping-ground" in issues
    assert all(f["kind"] == "matter-scaffold" for f in fs)


def test_legacy_terms_flags_deprecated_but_not_node_ids(tmp_path, monkeypatch):
    from laplace.pipeline import scaffold_wipe
    # a known deprecated set, so the pass needs no registered corpus fixture
    monkeypatch.setattr(scaffold_wipe, "_deprecated_vocabulary",
                        lambda cn: {"visibility lift": "def:null-channel"})
    tex = _write(tmp_path, "m.tex", r"""
\section{Body}\label{sec:b}
The visibility lift is large here, as the visibility-lift argument shows.
The canonical def:null-channel node is provenance, not a usage of the term.
""")
    fs = scaffold_wipe.check_legacy_terms(tex, corpus_name="whatever")
    assert fs and all(f["kind"] == "legacy-term" for f in fs)
    assert any("visibility lift" in f["issue"] for f in fs)
    # the def:null-channel node-id mention is provenance — never a usage hit
    assert all("def:null-channel" not in (f.get("quote") or "") or "lift" in f["quote"].lower()
               for f in fs)


def test_legacy_terms_flags_vocab_unavailable_when_empty(tmp_path, monkeypatch):
    # vocabulary honesty: a corpus was named but the deprecated set came back empty
    # (the accessor raised, or the corpus has none) — a zero-finding scan then
    # certifies nothing, so the report must carry vocab_unavailable, not read clean.
    from laplace.pipeline import scaffold_wipe
    monkeypatch.setattr(scaffold_wipe, "_deprecated_vocabulary", lambda cn: {})
    tex = _write(tmp_path, "m.tex",
                 r"\section{Body}\label{sec:b}" + "\nThe visibility lift is here.\n")
    report: dict = {}
    fs = scaffold_wipe.check_legacy_terms(tex, corpus_name="whatever", report=report)
    assert fs == []                                  # empty vocab -> nothing to hit
    assert report["vocab_unavailable"] is True       # but the emptiness is surfaced

    # no corpus requested -> not "unavailable" (the pass was simply not asked to run)
    report2: dict = {}
    scaffold_wipe.check_legacy_terms(tex, corpus_name=None, report=report2)
    assert report2["vocab_unavailable"] is False


def test_scaffold_wipe_result_carries_vocab_unavailable(tmp_path, monkeypatch):
    from laplace.pipeline import scaffold_wipe
    monkeypatch.setattr(scaffold_wipe, "_deprecated_vocabulary", lambda cn: {})
    tex = _write(tmp_path, "m.tex",
                 r"\section{Body}\label{sec:b}" + "\nPlain body prose.\n")
    res = scaffold_wipe.scaffold_wipe(tex, corpus_name="whatever")
    assert res["vocab_unavailable"] is True

    # a corpus that yields terms -> the flag is False (the scan had a vocabulary)
    monkeypatch.setattr(scaffold_wipe, "_deprecated_vocabulary",
                        lambda cn: {"visibility lift": "def:null-channel"})
    res2 = scaffold_wipe.scaffold_wipe(tex, corpus_name="whatever")
    assert res2["vocab_unavailable"] is False


def test_caption_scaffold_verify_flags_leaked_q3(tmp_path):
    from laplace.pipeline import scaffold_wipe
    tex = _write(tmp_path, "m.tex", r"""
\section{S}\label{sec:s}
\begin{figure}\centering\includegraphics{x.pdf}
\caption{Panel (a) shows the aperture, made by exact diagonalisation. The
figure supports the claim that the record is independent of resolution. It
establishes nothing about accuracy.}\label{fig:x}\end{figure}
""")
    fs = scaffold_wipe.check_caption_scaffold(tex)
    assert any("Q3 claim-support" in f["issue"] for f in fs)
    assert all(f["kind"] == "caption-scaffold" for f in fs)


def test_manifest_covers_every_emitted_kind(tmp_path):
    from laplace.pipeline import scaffold_wipe
    # every kind a pass can emit must be routable
    for kind in ("figure-debris", "caption-scaffold", "prose-scaffold",
                 "legacy-notation", "citation-cluster", "legacy-term", "matter-scaffold"):
        assert kind in scaffold_wipe.FINDING_KIND_STAGE


@pytest.mark.skipif(not SSG_MAIN.exists(), reason="SSG whitepaper not present")
def test_scaffold_wipe_runs_on_real_ssg():
    from laplace.pipeline import scaffold_wipe
    report = scaffold_wipe.scaffold_wipe(
        SSG_MAIN, project="subset-sum-itqde", corpus_name="subset-sum-itqde")
    assert set(report["counts"]) == {"prose", "caption", "equation", "citation",
                                     "notation", "matter"}
    # every finding is routable and well-formed
    for f in report["findings"]:
        assert f["kind"] in scaffold_wipe.FINDING_KIND_STAGE
        assert {"where", "issue", "fix", "kind", "owning_stage"} <= set(f)
