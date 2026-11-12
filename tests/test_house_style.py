"""The formal house-style layer (Phase I1): the corpus-derived presentation sweep.

Fixtures carry KNOWN-GOOD (house-conformant) and KNOWN-BAD cross-ref / citation /
punctuation / orthography forms. The two forks (F33 orthography, F34 punctuation)
are asserted to be REPORTED, never enforced and never auto-edited.
"""
from pathlib import Path

import pytest

from laplace.pipeline import house_style as hs

REPO = Path(__file__).resolve().parents[1]


# --- the manifest (wired into schema.KIND_TO_WORK in Phase F) ----------------
def test_finding_kinds_manifest():
    assert set(hs.FINDING_KINDS) == {
        "xref-style", "citation-style", "equation-punct",
        "dash-surface", "orthography-fork",
    }
    # every kind has a Phase-F route; orthography-fork is report-only (None).
    assert set(hs.KIND_ROUTES) == set(hs.FINDING_KINDS)
    assert hs.KIND_ROUTES["orthography-fork"] is None
    assert hs.KIND_ROUTES["xref-style"] == "prose"
    assert hs.KIND_ROUTES["citation-style"] == "prose"
    assert hs.KIND_ROUTES["dash-surface"] == "render"


def test_profile_loads_default():
    prof = hs.load_profile()
    assert prof["profile"] == "gerard-manuscript-v1"
    ids = {r["id"] for r in prof["rules"]}
    assert {"xref.equation", "xref.no_cleveref", "cite.style"} <= ids
    forks = {f["id"] for f in prof["forks"]}
    assert forks == {"F33.orthography", "F34.punctuation_surface"}


def test_profile_path_exists():
    assert hs.DEFAULT_PROFILE_PATH.is_file()


# --- known-GOOD: the house-conformant surface passes -------------------------
GOOD = r"""
As shown in Fig.~\ref{fig:x} and Eq.~\eqref{eq:y}, the bound is tight \cite{a}.
See Eqs.~(\ref{eq:p}, \ref{eq:q}) and Sec.~\ref{sec:z} and App.~\ref{app:a}.
Consult Ref.~\cite{b} for the derivation \cite{c,d}.
"""


def test_good_crossref_and_citation_pass():
    r = hs.check_house_style(GOOD)
    assert r["pass"] is True
    assert r["enforced_count"] == 0
    # the correct works-as-noun form Ref.~\cite must NOT be read as cite-after-period
    assert not any(f["rule"] == "cite.pre_punct" for f in r["findings"])
    # a plain space before \cite is the corpus norm (435:76) - must NOT be flagged
    assert not any("cite" in f["match"] and f["status"] == "enforced"
                   for f in r["findings"] if f["kind"] == "citation-style"
                   and f["rule"] == "xref.nbsp")


# --- known-BAD: cross-references --------------------------------------------
def test_bad_crossref_spelled_out_enforced():
    r = hs.check_house_style(r"as in equation~\ref{eq:y} and Section~\ref{sec:z}.")
    kinds = [(f["rule"], f["status"]) for f in r["findings"]]
    assert ("xref.equation", "enforced") in kinds
    assert ("xref.section", "enforced") in kinds
    assert r["pass"] is False


def test_bad_crossref_cleveref_enforced():
    r = hs.check_house_style(r"See \cref{eq:y} and \autoref{fig:x}.")
    assert sum(1 for f in r["findings"] if f["rule"] == "xref.no_cleveref") == 2
    assert all(f["status"] == "enforced"
               for f in r["findings"] if f["rule"] == "xref.no_cleveref")


def test_figure_spelled_midsentence_is_advisory():
    r = hs.check_house_style(r"the result in Figure~\ref{fig:x} holds.")
    fig = [f for f in r["findings"] if f["rule"] == "xref.figure"]
    assert fig and fig[0]["status"] == "advisory"
    assert r["pass"] is True     # advisory never fails the sweep


def test_figure_hardcoded_number_caught():
    r = hs.check_house_style(r"the curve in Figure 3 rises.")
    assert any("hard-codes a number" in f["issue"] for f in r["findings"])


def test_nbsp_is_advisory_not_enforced():
    # Eq.( (no space) and Eq. ( (space) are minority-but-real corpus forms -> advisory
    r = hs.check_house_style(r"see Eq.(3) and Fig. \ref{fig:z}.")
    nbsp = [f for f in r["findings"] if f["rule"] == "xref.nbsp"]
    assert nbsp, "expected nbsp advisories"
    assert all(f["status"] == "advisory" for f in nbsp)
    assert r["pass"] is True


# --- known-BAD: citations ----------------------------------------------------
def test_citet_banned_enforced():
    r = hs.check_house_style(r"following \citet{smith} we proceed.")
    assert any(f["rule"] == "cite.style" and f["status"] == "enforced"
               for f in r["findings"])
    assert r["pass"] is False


def test_cite_after_period_enforced():
    r = hs.check_house_style(r"The method works. \cite{smith} It is exact.")
    assert any(f["rule"] == "cite.pre_punct" and f["status"] == "enforced"
               for f in r["findings"])


def test_citep_under_revtex_flagged_but_not_under_other():
    revtex = r"\documentclass{revtex4-2}" + "\n" + r"see \citep{a}."
    other = r"\documentclass{svjour3}" + "\n" + r"see \citep{a}."
    assert any(f["kind"] == "citation-style" and "citep" in f["match"]
               for f in hs.check_house_style(revtex)["findings"])
    assert not any("citep" in f["match"]
                   for f in hs.check_house_style(other)["findings"])


# --- known-BAD: F34 punctuation surface (dash-surface fork) ------------------
def test_dash_surface_prose_flagged_as_fork():
    r = hs.check_house_style("a clause; an em-dash --- here and a spaced en-dash -- there.")
    ds = [f for f in r["findings"] if f["kind"] == "dash-surface"]
    assert {"semicolon" in f["issue"] for f in ds} == {True} or any(
        "semicolon" in f["issue"] for f in ds)
    assert any("em-dash" in f["issue"] for f in ds)
    assert any("en-dash" in f["issue"] for f in ds)
    assert all(f["status"] == "fork" for f in ds)          # never enforced
    assert r["pass"] is True                                # forks never fail the sweep


def test_math_semicolons_are_masked_out():
    # a semicolon inside math is NOT prose and must not fire the F34 surface.
    r = hs.check_house_style(r"The set $\{a; b\}$ and \begin{equation} f(x;y) \end{equation}.")
    assert not any(f["kind"] == "dash-surface" for f in r["findings"])


# --- known-BAD: F33 orthography (report-only fork) ---------------------------
def test_orthography_reported_both_ways_never_fixed():
    r = hs.check_house_style("we analyse the behaviour and the color of the behavior.")
    ortho = [f for f in r["findings"] if f["kind"] == "orthography-fork"]
    labels = {f["match"].lower() for f in ortho}
    assert {"behaviour", "color", "behavior"} <= labels     # both British AND American
    assert all(f["status"] == "fork" for f in ortho)
    assert all(f["fix"] is None for f in ortho)             # report-only: never a fix
    assert all(f["route"] is None for f in ortho)           # report-only route
    assert r["pass"] is True                                # a fork-only doc passes


def test_orthography_can_be_disabled():
    r = hs.check_house_style("we analyse the colour.", include_orthography=False)
    assert not any(f["kind"] == "orthography-fork" for f in r["findings"])


# --- pass semantics + aggregation -------------------------------------------
def test_only_enforced_fails_pass():
    # forks + advisories alone -> pass True; add one enforced -> pass False
    forks_only = hs.check_house_style("a; b, colour, Fig.(3).")
    assert forks_only["pass"] is True
    with_enforced = hs.check_house_style(r"a; \citet{x}.")
    assert with_enforced["pass"] is False


def test_finding_shape_has_standard_keys():
    r = hs.check_house_style(r"\citet{x} and equation~\ref{eq:y}.")
    for f in r["findings"]:
        assert {"where", "issue", "fix", "kind"} <= set(f)
        assert f["kind"] in hs.FINDING_KINDS


# --- calibration: the real SSG manuscript (the design's calibration case) ----
SSG_MAIN = (REPO / "synthetics papers" / "subset-sum-itqde" / "manuscript"
            / "whitepaper" / "main.tex")


@pytest.mark.skipif(not SSG_MAIN.is_file(), reason="SSG manuscript not present")
def test_ssg_manuscript_flags_known_deviations_not_noise():
    r = hs.check_house_style_manuscript(SSG_MAIN)
    # NOTE (2026-07-10): the original pin asserted the known xref deviations
    # were PRESENT - then the convergence loop FIXED them (Section -> Sec.,
    # the bite-2 wave), so the pin celebrated the disease after the cure.
    # Detection is proven on seeded fixtures elsewhere in this file; the live
    # manuscript keeps only the never-noise contracts below.
    rules = {f["rule"] for f in r["findings"] if f["status"] == "enforced"}
    assert isinstance(rules, set)
    # forks are reported but never enforced
    assert all(f["status"] != "enforced"
               for f in r["findings"] if f["kind"] in ("orthography-fork", "dash-surface"))
    # each finding is attributed to a source fragment
    assert all(":" in f["where"] for f in r["findings"])


def test_af1_loughborough_affiliation_is_banned_his_standing_word():
    """AF1 (his word, 2026-07-18: 'how many times have I told you I don't want my
    Loughborough affiliation on it. ever.') — any occurrence, any casing, front
    matter included, fails the enforced sweep; a clean front matter passes."""
    from laplace.pipeline.house_style import check_house_style
    dirty = ("\\author{Gerard McCaul}\n"
             "\\affiliation{Department of Physics, Loughborough University, "
             "Loughborough, UK}\n\\begin{document}\nBody prose.\n\\end{document}\n")
    res = check_house_style(dirty)
    hits = [f for f in res["findings"] if f["kind"] == "identity"]
    assert len(hits) == 2 and not res["pass"], \
        "both occurrences must be findings and the enforced sweep must fail"
    clean = dirty.replace(
        "\\affiliation{Department of Physics, Loughborough University, "
        "Loughborough, UK}\n", "")
    res2 = check_house_style(clean)
    assert not [f for f in res2["findings"] if f["kind"] == "identity"]


def test_af1_live_manuscripts_carry_no_affiliation():
    """The three live manuscripts stay clean — the sweep that keeps it 'ever'."""
    from pathlib import Path
    for p in ("synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex",
              "paper_falqon/manuscript/main.tex",
              "eigenengine/manuscript/main.tex"):
        src = Path(p).read_text(encoding="utf-8")
        assert "loughborough" not in src.lower(), f"{p} reintroduced the affiliation"
