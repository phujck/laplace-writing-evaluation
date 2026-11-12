"""Phase C — the coherence / apparatus gates (checklist cats 3–10, 12).

Two layers of test per module:

* **synthetic** — a minimal ``.tex`` with exactly one injected defect: the module
  must FIRE the intended kind on the defect and NOT fire it on the clean variant
  (the false-positive guard),
* **acceptance** — the real committed SSG whitepaper: the calibration case. C1 must
  confirm the 71 unreferenced equations, C2's two sweeps must fire, C3's backward
  sweep must find unlinked cross-section reliances, C6 must catch the missing
  abstract + the three unreachable appendices.

Plus the Phase-F precondition: every finding kind an audit module emits is declared
in the manifest and routes to a real owning stage.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from laplace.pipeline import (
    apparatus_common as ac,
    equation_lifecycle as c1,
    citation_audit as c2,
    crosslink_audit as c3,
    figure_audit as c4,
    caption_audit as c5,
    matter_audit as c6,
    table_audit as c7,
    notation_audit as c8,
    proportionality_audit as c9,
)
from laplace.pipeline import schema
from laplace.pipeline.graph import CanonGraph

ROOT = Path(__file__).resolve().parents[1]
WHITEPAPER = ROOT / "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"
# The byte-frozen pre-run copy of the whitepaper. THE RUN legitimately mutates the
# live tex above (equations get referenced, orphan figures adopted, reliances cited),
# which would shatter every exact-count pin below. The frozen copy holds the
# calibration point (74 equations / 71 orphans / 9 naked reliances / the f5-dp-price
# orphan) still, so the exact assertions ride the fixture while the live tex keeps
# only the relational invariants. Refreeze this fixture only when the calibration
# case itself is intentionally re-baselined.
FROZEN_WHITEPAPER = ROOT / "tests/fixtures/whitepaper_prerun/main.tex"
CORPUS = ROOT / "corpus/corpus.bib"
PROJECT = "subset-sum-itqde"


def _write(tmp_path: Path, body: str, name: str = "m.tex") -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def _kinds(result) -> set[str]:
    return {f["kind"] for f in result["findings"]}


# ===========================================================================
# The Phase-F precondition — the finding-kinds manifest is closed and routable
# ===========================================================================

def test_manifest_stages_route_to_real_owning_layers():
    """Every Phase-C kind's stage is either None (report-only) or a real layer
    that ``WORK_TO_LAYER`` already produces — so Phase F can wire each kind
    without inventing a stage."""
    layers = set(schema.WORK_TO_LAYER.values())
    for kind, stage in ac.FINDING_KIND_STAGE.items():
        if stage is None:
            continue
        assert stage in layers, (kind, stage, sorted(layers))


def test_every_emitted_kind_is_declared():
    """No module emits a kind absent from the manifest (an unrouted finding)."""
    results = [
        c1.check_equation_lifecycle(WHITEPAPER),
        c2.check_citation_audit(WHITEPAPER, CORPUS, PROJECT),
        c3.check_crosslink_audit(WHITEPAPER),
        c4.check_figure_system(WHITEPAPER),
        c5.check_caption_completeness(WHITEPAPER),
        c6.check_matter_coherence(WHITEPAPER),
        c7.check_tables_algorithms(WHITEPAPER),
        c8.check_notation_consistency(WHITEPAPER),
        c9.check_proportionality(WHITEPAPER),
    ]
    for r in results:
        for f in r["findings"]:
            assert f["kind"] in ac.FINDING_KIND_STAGE, f["kind"]
            assert f["where"] and f["issue"] and "kind" in f


# ===========================================================================
# C1 — equation lifecycle
# ===========================================================================

def test_c1_unreferenced_equation_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
We introduce the object.
\begin{equation}\label{def:widget}
X = 1
\end{equation}
It is the widget.
""")
    r = c1.check_equation_lifecycle(tex)
    assert "eq-unused" in _kinds(r)


def test_c1_referenced_equation_clean(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
We introduce the object in \eqref{def:widget}.
\begin{equation}\label{def:widget}
X = 1
\end{equation}
As \eqref{def:widget} shows, the widget is one.
""")
    r = c1.check_equation_lifecycle(tex)
    assert "eq-unused" not in _kinds(r)


def test_c1_ref_before_intro_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{First}\label{sec:a}
By \eqref{def:late} we already lean on it here.
\section{Second}\label{sec:b}
\begin{equation}\label{def:late}
Y = 2
\end{equation}
Now it exists.
""")
    r = c1.check_equation_lifecycle(tex)
    assert "eq-ref-before-intro" in _kinds(r)


def test_c1_acceptance_confirms_71_orphans():
    """Exact calibration on the byte-frozen pre-run whitepaper."""
    r = c1.check_equation_lifecycle(FROZEN_WHITEPAPER)
    assert r["n_equations"] == 74
    assert r["n_unreferenced"] == 71
    assert r["counts"].get("eq-unused") == 71


def test_c1_live_equation_lifecycle_is_internally_consistent():
    """On the live tex (which THE RUN legitimately mutates) only the relational
    invariants hold: a non-empty equation set, an unreferenced count that cannot
    exceed it, and one eq-unused finding per unreferenced equation."""
    r = c1.check_equation_lifecycle(WHITEPAPER)
    assert r["n_equations"] > 0
    assert r["n_unreferenced"] <= r["n_equations"]
    # one eq-unused finding per unreferenced equation - and, when THE RUN has linked
    # every equation, zero findings (an absent count key reads as 0, the codebase's
    # count convention; c3 below reads unlinked-reliance the same way).
    assert r["counts"].get("eq-unused", 0) == r["n_unreferenced"]


# ===========================================================================
# C2 — citation apparatus + coverage
# ===========================================================================

def test_c2_forward_strong_tell_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Background}\label{sec:bg}
It is known that the spectrum was shown to be discrete.
""")
    r = c2.check_citation_audit(tex)
    assert "citation-uncited" in _kinds(r)


def test_c2_forward_cited_is_clean(tmp_path):
    tex = _write(tmp_path, r"""
\section{Background}\label{sec:bg}
It is known that the spectrum was shown to be discrete \cite{smith2020}.
""")
    r = c2.check_citation_audit(tex)
    assert "citation-uncited" not in _kinds(r)


def test_c2_original_contribution_not_flagged_on_weak_tell(tmp_path):
    tex = _write(tmp_path, r"""
\section{Method}\label{sec:m}
We show our method requires only one acquisition campaign.
""")
    r = c2.check_citation_audit(tex)
    # weak tell ("requires") in a first-person sentence is the paper's own work
    assert "citation-uncited" not in _kinds(r)


def test_c2_cluster_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Related}\label{sec:r}
Many methods exist for this problem \cite{a2020, b2021, c2022, d2023}.
""")
    r = c2.check_citation_audit(tex)
    assert "citation-cluster" in _kinds(r)


def test_c2_acceptance_backward_and_forward_fire():
    """Exact backward-reliance + claim-table calibration on the frozen whitepaper."""
    r = c2.check_citation_audit(FROZEN_WHITEPAPER, CORPUS, PROJECT)
    assert r["backward"]["status"] == "ran"
    assert r["backward"]["naked"] == 9            # check_corpus_citations reliances
    assert r["n_forward"] > 0                     # the forward sweep catches uncited external tells
    assert r["n_clusters"] > 0
    assert len(r["claim_to_source"]) == 74        # every claim node has a table row


def test_c2_live_backward_and_claim_table_are_consistent():
    """On the live tex only internal consistency holds: the backward sweep ran and
    its naked count is a subset of the reliances it weighed; both forward sweeps
    still fire; and the claim table carries exactly one row per live claim node
    (mirrors _claim_to_source, which keys on nodes of kind 'claim')."""
    r = c2.check_citation_audit(WHITEPAPER, CORPUS, PROJECT)
    assert r["backward"]["status"] == "ran"
    assert 0 <= r["backward"]["naked"] <= r["backward"]["relied_on"]
    assert r["n_forward"] > 0
    assert r["n_clusters"] > 0
    g = CanonGraph.from_manuscript(WHITEPAPER)
    n_claims = sum(1 for n in g.nodes.values() if n.kind == "claim")
    assert len(r["claim_to_source"]) == n_claims


# ===========================================================================
# C3 — apparatus crosslink
# ===========================================================================

def test_c3_broken_ref_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
See \ref{fig:ghost} for details.
""")
    r = c3.check_crosslink_audit(tex)
    assert "crosslink-broken" in _kinds(r)


def test_c3_vague_reference_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
As shown in the equation above, the result holds.
""")
    r = c3.check_crosslink_audit(tex)
    assert "crosslink-vague" in _kinds(r)


def test_c3_acceptance_unlinked_reliance_fires():
    # exact pre-run calibration fact (THE RUN links the reliances, so the live tex no
    # longer fires) - rides the byte-frozen fixture, like c1/c2/c4 acceptance.
    r = c3.check_crosslink_audit(FROZEN_WHITEPAPER)
    assert r["counts"].get("unlinked-reliance", 0) > 0


# ===========================================================================
# C4 — figure system
# ===========================================================================

def test_c4_unreferenced_figure_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
\begin{figure}
\includegraphics[width=\columnwidth]{a.pdf}
\caption{A widget.}\label{fig:w}
\end{figure}
""")
    r = c4.check_figure_system(tex)
    assert "figure-unreferenced" in _kinds(r)


def test_c4_oversized_single_column_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
See \ref{fig:w}.
\begin{figure}
\includegraphics[width=\textwidth]{a.pdf}
\caption{A widget.}\label{fig:w}
\end{figure}
""")
    r = c4.check_figure_system(tex)
    assert "figure-oversized" in _kinds(r)


def test_c4_acceptance_orphan_figure():
    """Exact orphan-figure calibration on the frozen whitepaper: the real
    fig:f5-dp-price sits unreferenced."""
    r = c4.check_figure_system(FROZEN_WHITEPAPER)
    wheres = " ".join(f["where"] for f in r["findings"])
    assert "fig:f5-dp-price" in wheres          # the real orphaned figure


def test_c4_live_figure_findings_have_orphan_shape():
    """On the live tex THE RUN may legitimately adopt that orphan, so pin only the
    finding SHAPE, not the specific id: a non-empty figure set, and every
    figure-unreferenced finding located at a fig: label."""
    r = c4.check_figure_system(WHITEPAPER)
    assert r["n_figures"] > 0
    assert isinstance(r["findings"], list)
    for f in r["findings"]:
        assert "kind" in f and "where" in f
        if f["kind"] == "figure-unreferenced":
            assert "fig:" in f["where"]


# ===========================================================================
# C5 — caption completeness
# ===========================================================================

def test_c5_missing_caption_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
\begin{figure}
\includegraphics[width=\columnwidth]{a.pdf}\label{fig:w}
\end{figure}
""")
    r = c5.check_caption_completeness(tex)
    assert "caption-missing" in _kinds(r)


def test_c5_deep_nested_caption_is_not_missing(tmp_path):
    """A caption with several levels of math braces must not read as missing."""
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
\begin{figure}
\includegraphics[width=\columnwidth]{a.pdf}
\caption{The reconstructed surface $\hat{Z}_{\tau,m}(s)$ against the exact $Z_\tau(s)$, showing the finite-record envelope.}\label{fig:w}
\end{figure}
""")
    r = c5.check_caption_completeness(tex)
    assert "caption-missing" not in _kinds(r)


def test_c5_acceptance_no_false_missing():
    r = c5.check_caption_completeness(WHITEPAPER)
    assert r["counts"].get("caption-missing", 0) == 0   # every SSG float is captioned


# ===========================================================================
# C6 — front/back-matter coherence
# ===========================================================================

def test_c6_missing_abstract_fires(tmp_path):
    tex = _write(tmp_path, r"""
\title{A real informative title about widgets}
\maketitle
\section{Introduction}\label{sec:i}
We do things.
""")
    r = c6.check_matter_coherence(tex)
    assert "matter-missing-abstract" in _kinds(r)


def test_c6_appendix_unreachable_fires(tmp_path):
    tex = _write(tmp_path, r"""
\title{A real informative title about widgets}
\begin{abstract} We contribute a widget. \end{abstract}
\maketitle
\section{Introduction}\label{sec:i}
We do things.
\appendix
\section{Extra derivations}\label{app:x}
Details nobody links to.
""")
    r = c6.check_matter_coherence(tex)
    assert "matter-appendix-unreachable" in _kinds(r)


def test_c6_acceptance_missing_abstract_and_three_appendices():
    # exact pre-run calibration facts (THE RUN adds the abstract and links the
    # appendices) - rides the byte-frozen fixture, like c1/c2/c4 acceptance.
    r = c6.check_matter_coherence(FROZEN_WHITEPAPER)
    assert r["has_abstract"] is False
    assert r["counts"].get("matter-missing-abstract") == 1
    assert r["counts"].get("matter-appendix-unreachable") == 3


# ===========================================================================
# C7 — tables / algorithms
# ===========================================================================

def test_c7_uncaptioned_table_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
\begin{table}
\begin{tabular}{ll} a & b \\ \end{tabular}
\label{tab:t}
\end{table}
""")
    r = c7.check_tables_algorithms(tex)
    assert "table-uncaptioned" in _kinds(r)


def test_c7_malformed_columns_fire(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
See \ref{tab:t}.
\begin{table}
\caption{A table.}\label{tab:t}
\begin{tabular}{ll} \toprule a & b & c \\ \end{tabular}
\end{table}
""")
    r = c7.check_tables_algorithms(tex)
    assert "table-malformed" in _kinds(r)


def test_c7_acceptance_ssg_table_clean():
    # exact pre-run calibration fact (THE RUN adds more tables) - rides the byte-frozen
    # fixture, like c1/c2/c4 acceptance.
    r = c7.check_tables_algorithms(FROZEN_WHITEPAPER)
    assert r["n_tables"] == 1
    assert r["counts"] == {}                     # the one SSG table is well-formed


# ===========================================================================
# C8 — notation consistency (+ report-only orthography fork)
# ===========================================================================

def test_c8_inconsistent_term_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
The Gauss-Hermite grid is used. The Gauss Hermite grid is stable. A Gauss-Hermite node.
""")
    r = c8.check_notation_consistency(tex)
    assert "notation-inconsistent" in _kinds(r)


def test_c8_orthography_fork_is_report_only(tmp_path):
    tex = _write(tmp_path, r"""
\section{Body}\label{sec:b}
We normalise the colour and then normalize the color of the neighbour and neighbor.
""")
    r = c8.check_notation_consistency(tex)
    forks = [f for f in r["findings"] if f["kind"] == "orthography-fork"]
    assert forks                                 # the split is surfaced
    assert all(f["fix"] is None for f in forks)  # never enforced — Gerard's fork
    assert all(f["route"] is None for f in forks)


def test_c8_acceptance_orthography_no_false_split():
    """SSG is internally consistent British (diagonalisation, neighbour, centre —
    no American forms), so the fork detector must stay quiet: the F33 split lives
    across the corpus, not inside this one manuscript. A spurious report here
    (from a bare \\w*ise matching noise/size) is exactly the false positive the
    curated stems remove."""
    r = c8.check_notation_consistency(WHITEPAPER)
    assert r["orthography_fork"] == []


# ===========================================================================
# C9 — proportionality
# ===========================================================================

def test_c9_finite_as_asymptotic_fires(tmp_path):
    tex = _write(tmp_path, r"""
\section{Discussion}\label{sec:d}
The cost is asymptotically exponential, observed for all n at finite-size n <= 12.
""")
    r = c9.check_proportionality(tex)
    assert "proportionality" in _kinds(r)


def test_c9_honest_hedge_not_flagged(tmp_path):
    tex = _write(tmp_path, r"""
\section{Discussion}\label{sec:d}
The growth is consistent with exponential scaling but is a guide, not an established law.
""")
    r = c9.check_proportionality(tex)
    assert "proportionality" not in _kinds(r)    # the hedge disclaims the strong reading


def test_c9_acceptance_runs():
    r = c9.check_proportionality(WHITEPAPER)
    assert isinstance(r["findings"], list)       # runs clean on the real manuscript


# ---------------------------------------------------------------------------
# C07 (2026-07-19): the front-matter freeze — wash clause + the wired fifth organ
# ---------------------------------------------------------------------------


def test_weld_preamble_freezes_front_matter():
    """The substance-freeze wash names front matter as identity, frozen and
    outside the weld's write scope — the gap the f40a5d4 fix-forward left open
    (the weld rewrote affiliation/abstract/marking from the voice corpus)."""
    import inspect
    from laplace.pipeline import dispatch as DP
    src = inspect.getsource(DP.compile_weld_dispatch)
    for token in ("FRONT MATTER IS IDENTITY", "noaffiliation", "hypersetup",
                  "abstract", "never touch main.tex"):
        assert token in src, f"weld wash missing the front-matter freeze token {token!r}"


def test_detector_organs_wire_matter_audit():
    """matter_audit rides the detector-organs census (the fifth organ) — a
    zero-abstract manuscript can no longer pass every gate."""
    import inspect
    from laplace.pipeline import detector_organs as DO
    src = inspect.getsource(DO.run_detector_organs)
    assert "check_matter_coherence" in src
    assert "matter" in src
