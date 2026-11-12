"""Tests for the PROMISED-BUT-ABSENT detector (promise_audit) + its panel/schema
wiring."""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.pipeline import promise_audit as PA
from laplace.pipeline import schema


def _write(tmp_path: Path, body: str, bib: str = "") -> Path:
    main = tmp_path / "main.tex"
    main.write_text("\\documentclass{article}\\begin{document}\n"
                    + body + "\n\\end{document}\n", encoding="utf-8")
    if bib:
        (tmp_path / "refs.bib").write_text(bib, encoding="utf-8")
    return main


def test_zero_float_figure_promise_fires(tmp_path):
    main = _write(tmp_path, "As shown in the sweep-tradeoff plot, the cost rises.")
    res = PA.check_promises(main)
    assert res["pass"] is False
    kinds = {f["kind"] for f in res["findings"]}
    assert "promise-figure-absent" in kinds
    assert res["present"]["figures"] == 0


def test_numeric_figure_sense_not_charged(tmp_path):
    # "cost figure" is a numeric value, not a plot — the zero-float branch must
    # not drown in it. No plot/chart noun -> clean.
    main = _write(tmp_path, "Every cost figure is quoted against the baseline value.")
    res = PA.check_promises(main)
    assert res["pass"] is True, res["findings"]


def test_numbered_figure_beyond_count(tmp_path):
    body = ("\\begin{figure}\\includegraphics{a}\\caption{c}\\end{figure}\n"
            "See Figure 3 for the scaling.")
    main = _write(tmp_path, body)
    res = PA.check_promises(main)
    assert res["present"]["figures"] == 1
    assert any(f["kind"] == "promise-figure-absent" for f in res["findings"])


def test_dangling_xref_and_absent_cite(tmp_path):
    body = ("See \\ref{eq:missing}. As \\cite{ghost2020} showed.")
    main = _write(tmp_path, body, bib="@article{real2019, title={x}}")
    res = PA.check_promises(main)
    kinds = {f["kind"] for f in res["findings"]}
    assert "promise-xref-dangling" in kinds
    assert "promise-citation-absent" in kinds


def test_present_cite_and_label_are_clean(tmp_path):
    body = ("\\label{eq:e}Text. See \\ref{eq:e} and \\cite{real2019}.")
    main = _write(tmp_path, body, bib="@article{real2019, title={x}}")
    res = PA.check_promises(main)
    assert not any(f["kind"] in ("promise-xref-dangling", "promise-citation-absent")
                   for f in res["findings"]), res["findings"]


def test_findings_carry_route(tmp_path):
    main = _write(tmp_path, "The witness-scaling plot demonstrates the gap.")
    res = PA.check_promises(main)
    for f in res["findings"]:
        assert f["route"] == PA.FINDING_KIND_STAGE[f["kind"]]


def test_kinds_registered_in_schema():
    schema.register_component_kinds()
    for row in PA.finding_kinds_manifest():
        assert row["kind"] in schema.KIND_TO_WORK, row["kind"]


def test_convergence_promise_blocks_artefact_integrity():
    from laplace.pipeline import convergence as C
    dirty = C.evaluate_round(
        [{"label": "promise", "clean": False,
          "flags": [{"issue": "x", "kind": "promise-figure-absent"}]}],
        compile_ok=True)
    assert dirty["contract"]["hard"]["artefact_integrity"] is False


def test_convergence_absent_promise_is_safe():
    # a panel with no promise label is byte-unaffected (hard_ok absent -> True)
    from laplace.pipeline import convergence as C
    r = C.evaluate_round([{"label": "caption", "clean": True, "flags": []}],
                         compile_ok=True)
    assert r["contract"]["hard"]["artefact_integrity"] is True
