"""The recurring-tic detectors + the layout/tic EVIDENCE panel seam (his hold-out
review, 2026-07-10: the annoying tics, mechanically caught).

Each detector is asserted to FIRE on the live r2 SSG whitepaper (the captions ARE
defensive there; the six disclaimers DO recur; the sentences DO overload) AND to be
QUIET on a synthetic-clean fixture â€” the delta-rule proof that the detector is
hardened against real prose, not a straw man. The panel seam
(``apparatus.read_layout_evidence``) is asserted to fold the layout gates + the tics
into ONE advisory (evidence-grade) axis, never a hard blocker.
"""
from pathlib import Path

import pytest

from laplace.pipeline import tics
from laplace.pipeline.readers.apparatus import read_layout_evidence

REPO = Path(__file__).resolve().parents[1]
SSG = REPO / "synthetics papers/subset-sum-itqde/manuscript/whitepaper"

_have_ssg = pytest.mark.skipif(
    not (SSG.is_dir() and (SSG / "main.tex").is_file()),
    reason="needs the SSG manuscript source")


# a synthetic-clean manuscript: plain prose, one referenced figure with a tight
# caption, no defensive apparatus, no recurring disclaimer, no overloaded sentence.
_CLEAN = r"""
\documentclass{article}
\begin{document}
\section{Method}
The apparatus is measured against a fixed reference lattice throughout the study.
The gap scales with the reference size, as Fig.~\ref{fig:clean} records for each run.
\begin{figure}
\caption{Measured spectral gap versus lattice size.}
\label{fig:clean}
\end{figure}
\section{Results}
The estimate established in the method holds across the sampled sizes we tested.
Each value follows from the recursion, and the trend is smooth in the coupling range.
\end{document}
"""


def _clean(tmp_path: Path) -> Path:
    f = tmp_path / "main.tex"
    f.write_text(_CLEAN, encoding="utf-8")
    return f


# a synthetic DIRTY manuscript reproducing the r2 tic conditions: two defensive
# captions carrying all five facets, and all six disclaimer classes recurring past
# the threshold across two sections. Kept synthetic so the detector tests are
# independent of the live manuscript, which the de-scaffolding RUN drives to clean
# (the historical r2 magnitudes â€” no-hardness 20, exact-vs-finite 27 â€” are no longer
# in the tree; what the detector must still prove is that it FIRES on dirty prose).
_BOUNDARY = (
    "This inherits no worst-case hardness and asserts no hardness, "
    "no quantum advantage and is not an advantage, "
    "no quantum hardware data and contains no quantum hardware, "
    "finite-size observations over the tested sizes, "
    "a guide within the operating envelope, "
    "a validation reference and not a certification. ")
_DEF_CAPTION = (
    r"\caption{Panel (a) shows the profile (data source ED-N13, seeds fixed, "
    r"deterministic run 3). The bond dimension truncation tolerance is $10^{-12}$. "
    r"The figure supports the claim. It does not establish hardness of any kind, a "
    r"proof of principle only.}")
_OVERLOADED = (
    "The result holds provided the coupling is small, which is the regime we target, "
    "although the bound loosens where the disorder grows, because the spectrum spreads, "
    "unless the window is widened to compensate for the loss of contrast that would "
    "otherwise degrade the measured separation across every tested size entirely now. ")
_DIRTY = (
    r"\documentclass{article}\begin{document}" "\n"
    r"\section{Limits and discussion}" "\n"
    + _BOUNDARY + _BOUNDARY + _OVERLOADED + "\n"
    r"\begin{figure}" + _DEF_CAPTION + r"\label{fig:d1}\end{figure}" "\n"
    r"\section{Numerical validation}" "\n"
    + _BOUNDARY + _BOUNDARY + "\n"
    r"\begin{figure}" + _DEF_CAPTION + r"\label{fig:d2}\end{figure}" "\n"
    r"\end{document}" "\n")


def _dirty(tmp_path: Path) -> Path:
    f = tmp_path / "main.tex"
    f.write_text(_DIRTY, encoding="utf-8")
    return f


# ===========================================================================
# (a) DEFENSIVE-CAPTION
# ===========================================================================

def test_defensive_caption_fires_on_dirty(tmp_path):
    res = tics.check_defensive_captions(_dirty(tmp_path))
    assert res["pass"] is False
    flagged = {f["where"] for f in res["findings"]}
    # both defensive captions carry all five facets (what-shown + provenance +
    # conventions + supported-claim + non-claims) â€” the caption doing the whole job.
    assert {"fig:d1", "fig:d2"} <= flagged
    d1 = next(f for f in res["findings"] if f["where"] == "fig:d1")
    assert d1["n_facets"] == 5
    assert set(d1["facets"]) == {"what_shown", "provenance", "conventions",
                                 "supported_claim", "non_claims"}
    assert len(res["findings"]) >= 2
    assert all(f["kind"] == "caption-defensive" and f["grade"] == "evidence"
               and f["route"] == "figures" for f in res["findings"])


def test_defensive_caption_quiet_on_clean(tmp_path):
    res = tics.check_defensive_captions(_clean(tmp_path))
    assert res["pass"] is True and res["findings"] == []
    # the clean caption carries at most one facet (what-shown), never the apparatus.
    assert all(c["n_facets"] <= 1 for c in res["captions"])


# ===========================================================================
# (b) DISCLAIMER-REPETITION
# ===========================================================================

def test_disclaimer_repetition_fires_on_dirty(tmp_path):
    res = tics.check_disclaimer_repetition(_dirty(tmp_path), threshold=3)
    assert res["pass"] is False
    flagged = {f["where"].split(":", 1)[1] for f in res["findings"]}
    # ALL SIX disclaimer classes recur past the threshold across the two sections â€”
    # the boundary scattered, not stated once (the hold-out's exact complaint).
    assert flagged == {"no-hardness", "no-advantage", "no-hardware",
                       "exact-vs-finite-size", "guide-not-law",
                       "reference-not-certification"}
    # every finding carries its count + the sections it recurs in (the fix locator).
    for f in res["findings"]:
        assert f["count"] > 3 and len(f["sections"]) >= 2
        assert f["kind"] == "disclaimer-repetition" and f["grade"] == "evidence"


def test_disclaimer_repetition_quiet_on_clean(tmp_path):
    res = tics.check_disclaimer_repetition(_clean(tmp_path), threshold=3)
    assert res["pass"] is True and res["findings"] == []
    assert all(info["count"] == 0 for info in res["by_class"].values())


# ===========================================================================
# (c) SENTENCE-DENSITY
# ===========================================================================

SSG_PRECRANK = REPO / "tests/fixtures/ssg_whitepaper_precrank_r2"


def test_sentence_density_fires_on_r2():
    # FROZEN FIXTURE (2026-07-14): this test pins that the detector FIRES on real
    # degraded prose. It used to point at the LIVE whitepaper — then the first normal
    # harnessed round (C1.1, the crank) repaired exactly those sentences and the live
    # artifact stopped carrying the defect the test asserted. Same disease as the
    # golden's base.json preference, same cure: the comparison target is a frozen
    # copy of the pre-crank r2 tex set (git a3af7f7^), hermetic against the artifact
    # legitimately improving. The live artifact's CURRENT density rides the advisory
    # axis (read_layout_evidence), not a pinned pass=False.
    res = tics.check_sentence_density(SSG_PRECRANK)
    assert res["pass"] is False
    assert res["scanned"] > 200                      # the whole body was scanned
    assert len(res["findings"]) >= 3
    for f in res["findings"]:
        assert f["markers"] > 2 and f["words"] > 40
        assert f["kind"] == "sentence-overloaded" and f["grade"] == "evidence"
        assert f["quote"]                            # the split candidate is quoted


def test_sentence_density_quiet_on_clean(tmp_path):
    res = tics.check_sentence_density(_clean(tmp_path))
    assert res["pass"] is True and res["findings"] == []
    assert res["scanned"] >= 4                        # the clean sentences were counted


def test_sentence_density_tuned_thresholds(tmp_path):
    # a single overloaded sentence: 3 subordinate markers, > 40 words.
    over = (r"\section{S}" "\n"
            "The result holds provided the coupling is small, which is the regime we "
            "target, although the bound loosens where the disorder grows, because the "
            "spectrum spreads, unless the window is widened to compensate for the loss "
            "of contrast that otherwise degrades the measured separation entirely now.\n")
    f = tmp_path / "main.tex"
    f.write_text("\\documentclass{article}\\begin{document}\n" + over +
                 "\\end{document}\n", encoding="utf-8")
    res = tics.check_sentence_density(f)
    assert len(res["findings"]) == 1
    hit = res["findings"][0]
    assert hit["markers"] > 2 and hit["words"] > 40


# ===========================================================================
# the aggregator + the panel EVIDENCE seam
# ===========================================================================

def test_run_tic_detectors_aggregates_all_three_on_dirty(tmp_path):
    res = tics.run_tic_detectors(_dirty(tmp_path))
    assert res["clean"] is False
    kinds = set(res["counts"])
    assert {"caption-defensive", "disclaimer-repetition",
            "sentence-overloaded"} <= kinds
    # the aggregator folds the caption + disclaimer tics into one advisory axis.
    assert res["counts"]["caption-defensive"] >= 2
    assert res["counts"]["disclaimer-repetition"] == 6


def test_run_tic_detectors_quiet_on_clean(tmp_path):
    res = tics.run_tic_detectors(_clean(tmp_path))
    assert res["clean"] is True and res["findings"] == []


# Pins the r2 SSG whitepaper layout-evidence axis in the superseded corpus
# subtree; the captions moved past r2. Banked known-fail on the C5.7 triage.
_banked_r3 = pytest.mark.xfail(
    reason="content moved past r2 (file present; content drift) - banked known-fail 2026-07-13",
    strict=False,
)


@_have_ssg
@_banked_r3
def test_read_layout_evidence_is_one_advisory_axis_on_r2():
    # the layout gates (G2 float, G3 contract â€” source+aux) AND the three tics ride
    # ONE advisory axis; every finding is evidence-grade and feeds NO hard dim.
    ev = read_layout_evidence(SSG, size_gate=False)
    assert ev["advisory"] is True and ev["grade"] == "evidence"
    assert ev["failed"] is False
    kinds = set(ev["counts"])
    # both surfaces present: a layout kind AND all three tic kinds.
    assert {"caption-defensive", "disclaimer-repetition",
            "sentence-overloaded"} <= kinds
    assert any(k.startswith("float-") for k in kinds)         # G2 rode along
    # NOT a hard blocker: every finding is advisory, owns no hard-failure.
    assert all(f["grade"] == "evidence" and f["owned_failure"] is None
               for f in ev["findings"])
    # the render-dependent G1 is opt-in at the round cadence (release owns its teeth).
    assert ev["size_gate_ran"] is False
    assert "size" not in ev["layout"]


def test_read_layout_evidence_quiet_on_clean(tmp_path):
    ev = read_layout_evidence(_clean(tmp_path), size_gate=False)
    assert ev["clean"] is True and ev["findings"] == []
    assert ev["failed"] is False
