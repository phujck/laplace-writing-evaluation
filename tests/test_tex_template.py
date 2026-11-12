"""The template + compile pillar: the documentclass/preamble gate and the
typography lint. Log snippets below are REAL pdflatex output captured from a
REVTeX4-2 + eigen-revtex compile."""
import shutil
import subprocess
from pathlib import Path

import pytest

from laplace.pipeline import tex_template as T

REPO = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO / "templates" / "eigen-revtex"


# --- THE GATE ---------------------------------------------------------------

GOOD_PREAMBLE = r"""
\documentclass[reprint,aps,prx,superscriptaddress,nofootinbib]{revtex4-2}
\usepackage{eigen-revtex}
\begin{document}
\title{X}\maketitle
\end{document}
"""


def test_gate_accepts_revtex_plus_eigen_layer():
    r = T.check_template(GOOD_PREAMBLE)
    assert r["pass"] is True
    assert r["documentclass"] == "revtex4-2"
    assert r["house_layer"] is True
    assert r["missing_required"] == []


def test_gate_accepts_the_shipped_template_example():
    r = T.check_template((TEMPLATE_DIR / "main.tex").read_text())
    assert r["pass"] is True and r["house_layer"] is True


def test_gate_rejects_plain_article():
    r = T.check_template(r"\documentclass[11pt]{article}" "\n" r"\usepackage{amsmath}")
    assert r["pass"] is False
    cats = {f["category"] for f in r["findings"]}
    assert "documentclass" in cats
    assert any(f.get("found") == "article" for f in r["findings"])


def test_gate_rejects_revtex_without_house_layer():
    r = T.check_template(r"\documentclass[aps,prx]{revtex4-2}" "\n" r"\usepackage{amsmath}")
    assert r["pass"] is False
    assert r["house_layer"] is False
    assert {"house_layer", "required_package"} <= {f["category"] for f in r["findings"]}


def test_gate_flags_legacy_eigenengine_layer():
    r = T.check_template(r"\documentclass[twocolumn,10pt]{article}" "\n" r"\usepackage{eigenengine}")
    assert r["pass"] is False
    assert any(f.get("found") == "eigenengine" for f in r["findings"])


def test_gate_ignores_commented_out_documentclass():
    src = "%\\documentclass{article}\n\\documentclass[aps,prx]{revtex4-2}\n\\usepackage{eigen-revtex}"
    r = T.check_template(src)
    assert r["documentclass"] == "revtex4-2" and r["pass"] is True


# --- THE LINT (real captured pdflatex log lines) ----------------------------

def test_lint_overfull_hbox_reports_pt_and_line_range():
    log = "Overfull \\hbox (152.33858pt too wide) in paragraph at lines 20--21\n"
    r = T.lint_typography(log)
    f = next(f for f in r["findings"] if f["category"] == "overfull_hbox")
    assert f["token"] == "152.33858" and f["lines"] == "20--21"
    assert f["severity"] == "warning"


def test_lint_undefined_reference_and_citation():
    log = (
        "LaTeX Warning: Reference `sec:ghost' on page 1 undefined on input line 17.\n"
        "Package natbib Warning: Citation `ghostkey' on page 1 undefined on input line 18.\n"
    )
    r = T.lint_typography(log)
    cats = {f["category"]: f for f in r["findings"]}
    assert cats["undefined_reference"]["token"] == "sec:ghost"
    assert cats["undefined_citation"]["token"] == "ghostkey"
    assert r["pass"] is False   # undefined ref/cite are errors


def test_lint_multiply_defined_label():
    r = T.lint_typography("LaTeX Warning: Label `sec:dup' multiply defined.\n")
    assert r["findings"][0]["category"] == "multiply_defined_label"
    assert r["findings"][0]["token"] == "sec:dup"


def test_lint_missing_file_is_deduplicated():
    # a missing graphic surfaces as both a LaTeX warning and a pdftex.def error;
    # they collapse to a single finding.
    log = (
        "LaTeX Warning: File `nonexistent_figure.pdf' not found on input line 7.\n"
        "! Package pdftex.def Error: File `nonexistent_figure.pdf' not found: using draft\n"
    )
    r = T.lint_typography(log)
    missing = [f for f in r["findings"] if f["category"] == "missing_file"]
    assert len(missing) == 1 and missing[0]["token"] == "nonexistent_figure.pdf"


def test_lint_dewraps_79_column_line_wrap():
    # pdflatex wraps at 79 columns; "undefined" here is split across the wrap.
    label = "sec:a:deliberately:long:label:name:that:forces:the:log:to:wrap:here"
    head = f"LaTeX Warning: Reference `{label}' on page 1 undefined on input line 4"
    assert len(head) >= 79  # precondition: this line is a real wrap
    wrapped = head[:79] + "\n" + head[79:] + "2.\n"
    r = T.lint_typography(wrapped)
    assert any(f["category"] == "undefined_reference" and f["token"] == label
               for f in r["findings"])


def test_lint_font_substitution():
    log = "LaTeX Font Warning: Font shape `T1/cmr/m/scit' undefined\n"
    r = T.lint_typography(log)
    assert r["findings"][0]["category"] == "font_substitution"


def test_lint_clean_log_has_no_findings():
    log = "This is pdfTeX...\n(main.tex\nOutput written on main.pdf (1 page).\n"
    r = T.lint_typography(log)
    assert r["clean"] is True and r["pass"] is True and r["findings"] == []


# --- the no-titles-on-figures rule (source-based) ---------------------------

def test_no_titles_flags_bold_titled_caption():
    tex = r"\begin{figure}\caption{\textbf{A Titled Figure.} Body prose.}\end{figure}"
    r = T.lint_typography("", tex_source=tex)
    f = next(f for f in r["findings"] if f["category"] == "no_titles_on_figures")
    assert f["title"] == "A Titled Figure."


def test_no_titles_allows_panel_labels_and_plain_captions():
    tex = (
        r"\caption{\textbf{(a)} the left panel; \textbf{(b)} the right panel.}"
        "\n"
        r"\caption{\textbf{Top:} energies. \textbf{Bottom:} residuals.}"
        "\n"
        r"\caption{A perfectly ordinary caption with no leading title.}"
    )
    r = T.lint_typography("", tex_source=tex)
    assert not any(f["category"] == "no_titles_on_figures" for f in r["findings"])


# --- live end-to-end: the shipped template really compiles + lints clean -----

@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex not installed")
def test_shipped_template_compiles_and_log_is_clean(tmp_path):
    for name in ("eigen-revtex.sty", "main.tex"):
        (tmp_path / name).write_text((TEMPLATE_DIR / name).read_text())
    for _ in range(2):  # two passes to resolve refs
        proc = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "main.tex"],
            cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert (tmp_path / "main.pdf").exists()
    log = (tmp_path / "main.log").read_text(errors="replace")
    r = T.lint_typography(log, tex_source=(tmp_path / "main.tex").read_text())
    assert r["pass"] is True, r["findings"]
    assert not any(f["category"] in ("overfull_hbox", "missing_file") for f in r["findings"]), r["findings"]
