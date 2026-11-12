"""The substance-freeze validator organ (pipeline/freeze_validate.py).

The quarantine's law, mechanized: substance deltas STOP, mechanical slips are
retry-lawful, benign ref-drift reports. The ad-hoc wash_validate.py scratchpad
is retired by this organ.
"""
from __future__ import annotations

import pytest

from laplace.pipeline import freeze_validate as fv

_BASE = r"""% PLAN: sec:x
% NODES: n1 n2
\section{The Object}
Prose referencing \eqref{eq:one} twice, and \eqref{eq:one} again.
\begin{equation}\label{eq:one}
E = mc^2
\end{equation}
Grounded by \cite{alpha2020,beta2019}.
"""


def test_identical_fragment_is_clean():
    d = fv.diff_fragment(_BASE, _BASE, fragment="N1")
    assert d["clean"] and not d["substance"] and not d["mechanical"]


def test_pure_prose_rewrite_holds_the_freeze():
    """Language is the welder's; the frozen classes untouched = clean."""
    after = _BASE.replace("Prose referencing", "The argument leans on")
    d = fv.diff_fragment(_BASE, after, fragment="N1")
    assert d["clean"]


def test_new_labeled_equation_is_substance():
    """The N4 precedent: a NEW labeled equation = substance, STOP."""
    after = _BASE + "\n\\begin{equation}\\label{def:new}\nU = e^{-iHt}\n\\end{equation}\n"
    d = fv.diff_fragment(_BASE, after, fragment="N4")
    classes = {v["class"] for v in d["substance"]}
    assert "equations-changed" in classes and "labels-changed" in classes


def test_dropped_citation_is_substance():
    """The N8 precedent: removing a cite key = substance."""
    after = _BASE.replace(r"\cite{alpha2020,beta2019}", r"\cite{alpha2020}")
    d = fv.diff_fragment(_BASE, after, fragment="N8")
    assert any(v["class"] == "cites-changed" and "beta2019" in v["removed"]
               for v in d["substance"])


def test_marker_lines_are_frozen():
    after = _BASE.replace("% NODES: n1 n2", "% NODES: n1")
    d = fv.diff_fragment(_BASE, after, fragment="N1")
    assert any(v["class"] == "markers-changed" for v in d["substance"])


def test_ref_multiplicity_drift_is_benign():
    """The N1/N6 precedent: referencing fewer times = benign, never a fail."""
    after = _BASE.replace(", and \\eqref{eq:one} again", "")
    d = fv.diff_fragment(_BASE, after, fragment="N1")
    assert d["clean"] or (not d["substance"] and not d["mechanical"])
    assert any(v["class"] == "ref-drift" for v in d["benign"])


def test_equation_reflow_is_not_substance():
    """Whitespace-only reflow inside a display env keeps the hash."""
    after = _BASE.replace("E = mc^2", "E  =  mc^2")
    d = fv.diff_fragment(_BASE, after, fragment="N2")
    assert not any(v["class"] == "equations-changed" for v in d["substance"])


def test_validate_freeze_whole_pass_and_retry_law():
    before = {"N1": _BASE, "N2": _BASE}
    after = {"N1": _BASE.replace("Prose referencing", "The argument leans on"),
             "N2": _BASE + "\n\\begin{equation}\\label{def:x}\nX=1\n\\end{equation}\n"}
    v = fv.validate_freeze(before, after, main_before="M", main_after="M")
    assert v["substance_pass"] is False and v["pass"] is False
    assert v["retry_lawful"] is False           # broken freeze is never retried
    assert v["per_fragment"]["N1"]["clean"] is True
    assert v["front_matter"] == {"checked": True, "identical": True}


def test_front_matter_touch_is_substance():
    v = fv.validate_freeze({"N1": _BASE}, {"N1": _BASE},
                           main_before="\\title{A}", main_after="\\title{B}")
    assert v["substance_pass"] is False
    assert v["classes"].get("front-matter-touched") == 1


def test_orphan_fragment_is_substance():
    """The NA3 precedent: a minted fragment = substance violation."""
    v = fv.validate_freeze({"N1": _BASE}, {"N1": _BASE, "NA3": "orphan"},
                           main_before="M", main_after="M")
    assert any(x["class"] == "fragment-added"
               for x in v["per_fragment"]["NA3"]["substance"])


def test_retry_lawful_when_freeze_held_and_only_mechanical(monkeypatch):
    """The one-retry precondition: substance HELD + a voice slip = retry_lawful."""
    calls = {"n": 0}
    def fake_check_voice(text):
        calls["n"] += 1
        # baseline 0 flags, candidate 1 flag
        return {"flags": [{"class": "opposition-closer"}] if calls["n"] % 2 == 0 else []}
    import laplace.pipeline.verify as _v
    monkeypatch.setattr(_v, "check_voice", fake_check_voice)
    v = fv.validate_freeze({"N1": _BASE},
                           {"N1": _BASE.replace("Prose", "Reworked prose")},
                           main_before="M", main_after="M")
    assert v["substance_pass"] is True
    assert v["mechanical_pass"] is False
    assert v["retry_lawful"] is True
