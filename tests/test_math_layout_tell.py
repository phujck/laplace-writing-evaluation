"""BITE A2 â€” the mechanical WIDENING tell (math_layout_tell.detect_widening).

The pathology it fires on (r1 PDF pages 3/20/27; the r2 tab_dp-price still carries
it): a fix that "satisfies" the overfull detector by WIDENING or FONT-SHRINKING a
display/table, or by drawing a full-width \\rule separator â€” detector clean, object
worse. The tell must fire on those forms and STAY QUIET on the object-correct
remedy (a display SPLIT with align/multline) and on the one legitimate size use
(``font=\\small`` inside a TikZ node style key).
"""
from __future__ import annotations

import pytest

from laplace.pipeline import math_layout_tell as W

pytestmark = pytest.mark.unit


def test_bare_small_inside_a_table_is_the_tell():
    src = (r"\begin{table}" "\n" r"\small" "\n"
           r"\begin{tabular}{ll} a & b \\ \end{tabular}" "\n" r"\end{table}")
    hits = W.detect_widening(src)
    assert len(hits) == 1
    assert hits[0]["kind"] == "table-fontshrink"
    assert hits[0]["pathology"] == "widening"


def test_font_key_small_in_tikz_is_NOT_the_tell():
    # font=\small is a pgfkey value â€” the one legitimate size use, never flagged.
    src = (r"\begin{tikzpicture}" "\n"
           r"\node[lab, font=\footnotesize\sffamily] at (0,0) {a};" "\n"
           r"\node[font=\scriptsize] {x};" "\n" r"\end{tikzpicture}")
    assert W.detect_widening(src) == []


def test_resizebox_around_a_tabular_is_the_tell():
    src = (r"\resizebox{\textwidth}{!}{" "\n"
           r"\begin{tabular}{ll} a & b \\ \end{tabular}}")
    hits = W.detect_widening(src)
    assert [h["kind"] for h in hits] == ["table-scalebox"]


def test_scalebox_around_a_display_is_the_tell():
    src = r"\scalebox{0.8}{\begin{equation} x = y \end{equation}}"
    hits = W.detect_widening(src)
    assert any(h["kind"] == "display-scalebox" for h in hits)


def test_full_width_rule_separator_is_the_tell():
    for w in ("linewidth", "textwidth", "columnwidth"):
        hits = W.detect_widening(r"\rule{\%s}{0.4pt}" % w)
        assert [h["kind"] for h in hits] == ["rule-width-separator"]


def test_object_correct_split_display_is_clean():
    # the REMEDY the policy mandates: a display SPLIT across lines â€” never flagged.
    src = (r"\begin{align}" "\n" r"a &= b \\" "\n" r"  &= c" "\n" r"\end{align}")
    assert W.detect_widening(src) == []


def test_small_around_plain_prose_is_not_this_pathology():
    # a size command far from any display/table is a different (non-math-layout)
    # matter â€” the tell is scoped to math/table layout, so it stays quiet here.
    src = (r"\small This is a paragraph of ordinary prose with no display and no "
           r"table anywhere near it at all, just words for the reader.")
    assert W.detect_widening(src) == []


def test_commented_out_form_does_not_trip():
    src = ("% \\small  (a commented example, not live)\n"
           r"\begin{tabular}{ll} a & b \\ \end{tabular}")
    assert W.detect_widening(src) == []


def test_fragment_form_names_the_file_and_summary_rolls_up():
    frags = [("N1", r"\resizebox{\linewidth}{!}{\begin{tabular}{l}x\end{tabular}}"),
             ("N2", "\\begin{table}\n\\small\n\\begin{tabular}{l}y\\\\ \\end{tabular}\n\\end{table}")]
    hits = W.detect_widening(frags)
    files = {h["file"] for h in hits}
    assert files == {"N1", "N2"}
    summ = W.widening_summary(hits)
    assert summ["n"] == 2 and summ["files"] == ["N1", "N2"]


# Pins the r2 SSG table tell in the superseded whitepaper corpus subtree; the
# table moved past that snapshot. Banked known-fail on the C5.7 quiet-tree triage.
_banked_r3 = pytest.mark.xfail(
    reason="content moved past r2 (file present; content drift) - banked known-fail 2026-07-13",
    strict=False,
)


@_banked_r3
def test_the_real_r2_table_carries_the_tell():
    # the shipped r2 table (tables_tex/tab_dp-price.tex) still font-shrinks â€” the
    # exact form the harnessed re-detect must catch. Reads it if present.
    from pathlib import Path
    p = (Path(__file__).resolve().parents[1] / "synthetics papers" /
         "subset-sum-itqde" / "manuscript" / "whitepaper" / "tables_tex" /
         "tab_dp-price.tex")
    if not p.is_file():
        pytest.skip("the SSG r2 table fixture is not present in this checkout")
    hits = W.detect_widening(p.read_text(encoding="utf-8"))
    assert any(h["kind"] == "table-fontshrink" for h in hits)
