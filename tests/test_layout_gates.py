"""The three figure-layout review gates (his hold-out review, 2026-07-10: create
independent surfaces). Each gate is asserted to FIRE on the live r2 SSG whitepaper
(the documented real defects) AND to PASS on a synthetic-clean fixture — the
delta-rule proof that the gate is hardened against a real refusal, not a straw man.

The render-dependent assertions (G1 — physical glyph measurement, G3 — asset panel
extraction) exercise the isolated ``uv --with pypdfium2`` subprocess and skip where
uv/pypdfium2 is unavailable; the source+aux logic (G2 float placement, G3 panel
agreement from source) runs everywhere.
"""
import json
import os
import shutil
from pathlib import Path

import pytest

from laplace.pipeline import layout_gates as lg
from laplace.pipeline import visual_gate as vg

REPO = Path(__file__).resolve().parents[1]
SSG = REPO / "synthetics papers/subset-sum-itqde/manuscript/whitepaper"
SLUG = "spectral-surface-generation-reconstructing-gaussian-filtered-spectral-surfaces-f"
R2_PDF = SSG / f"{SLUG}.pdf"
R2_AUX = SSG / f"{SLUG}.aux"

_HAVE_UV = bool(shutil.which(vg.DEFAULT_UV) or shutil.which("uv"))
_HAVE_SYNCTEX = bool(shutil.which("synctex"))
_render = pytest.mark.skipif(
    not (_HAVE_UV and R2_PDF.is_file()),
    reason="needs uv (pypdfium2) + the compiled r2 SSG PDF")
_have_ssg = pytest.mark.skipif(
    not (SSG.is_dir() and R2_AUX.is_file()),
    reason="needs the SSG manuscript + its compiled .aux")


# ---------------------------------------------------------------------------
# the .aux label/page resolver (the reused figure/section page map)
# ---------------------------------------------------------------------------

@_have_ssg
def test_parse_aux_resolves_figure_and_section_pages():
    aux = lg.parse_aux_labels(R2_AUX)
    figs = {k: v for k, v in aux.items() if k.startswith("fig:")}
    # the nine floats and their shipout pages, read from the .aux (brace-balanced
    # past the deep-nested caption fields).
    assert aux["fig:nf6"]["page"] == 24 and aux["fig:nf6"]["number"] == "7"
    assert aux["fig:nf7"]["page"] == 25
    assert aux["fig:f5-dp-price"]["page"] == 20
    assert len(figs) >= 9
    # boundaries: the concluding section starts p24, the appendix p25.
    conclusion, appendix = lg._boundary_pages(aux, SSG)
    assert conclusion == 24 and appendix == 25


# ===========================================================================
# G1 — final-size visual gate
# ===========================================================================

def test_measure_script_escapes_replacement_marker_for_windows_tempfile():
    # A literal U+FFFD cannot be written through a Windows cp1252 default text
    # stream. Keep the embedded script source portable even though _run_uv now
    # also opens its temporary file explicitly as UTF-8.
    assert "\ufffd" not in lg._MEASURE_SCRIPT
    assert r"\ufffd" in lg._MEASURE_SCRIPT


def test_measure_script_uses_rotation_invariant_glyph_extent():
    # A y-axis label rotates its physical height into the x direction. The
    # release gate must measure the major loose-box extent, not top-bottom only.
    assert (
        "max(abs(rect.top - rect.bottom), abs(rect.right - rect.left))"
        in lg._MEASURE_SCRIPT
    )


@_render
@_have_ssg
def test_g1_fires_on_r2_subsize_and_type3():
    res = lg.check_final_size_visual(R2_PDF, aux_path=R2_AUX)
    assert res["pass"] is False and res["clean"] is False
    assert res["release_blocker"] is True

    # per-page measurements reproduce his numbers: the worst two figure pages carry
    # hundreds of sub-6pt glyphs bottoming near 1.2-1.4pt (independently MEASURED).
    by_page = {m["page"]: m for m in res["measurements"]}
    assert by_page[23]["sub_count"] >= 400 and by_page[23]["min_height"] < 1.5   # Fig6
    assert by_page[24]["sub_count"] >= 600 and by_page[24]["min_height"] < 1.3   # Fig7

    undersize = [f for f in res["findings"] if f["kind"] == "layout-text-undersize"]
    fired_pages = {f["page"] for f in undersize}
    assert {22, 23, 24} <= fired_pages                 # Fig5/Fig6/Fig7 all fire
    # the figure is named from the .aux attribution.
    f24 = next(f for f in undersize if f["page"] == 24)
    assert "fig:nf6" in f24["where"]

    # Type-3 fonts (matplotlib default) are flagged as their own defect.
    assert res["type3_count"] > 0
    assert any(f["kind"] == "layout-type3-font" for f in res["findings"])


@_render
def test_g1_passes_on_clean_pdf(tmp_path):
    # a hand-built one-line PDF: 12pt Helvetica (Type-1), no tiny text, no clip.
    clean = tmp_path / "clean.pdf"
    clean.write_bytes(_CLEAN_PDF)
    res = lg.check_final_size_visual(clean)
    assert res["pass"] is True and res["clean"] is True
    assert res["findings"] == []
    assert res["type3_count"] == 0
    # every measured glyph is at/above the 6pt floor.
    assert all((m["min_height"] is None or m["min_height"] >= 6.0)
               and m["beyond_mediabox"] == 0 for m in res["measurements"])


# --- G1 text-layer machine-readability (Type-3 / ToUnicode / extraction) -------

@_render
@_have_ssg
def test_text_layer_passes_on_r2_clean_body():
    # the r2 body text layer is Type-1 CM with ToUnicode — extraction is intact, so
    # the text-layer gate PASSES on it even though G1's figure checks fire. The
    # benign figure Type-3 fonts (no ToUnicode) do NOT trip the text-layer gate.
    res = lg.check_text_layer(R2_PDF)
    assert res["pass"] is True and res["clean"] is True
    s = res["summary"]
    assert s["garbled_pages"] == []
    # the exact symptom words extract cleanly (the regression garbles these).
    assert {"floor", "coefficient", "spectral", "surface"} <= set(s["common_words_present"])
    # figure Type-3-without-ToUnicode fonts exist but did not fire the gate.
    assert s["type3_no_tounicode"] > 0


@_render
def test_text_layer_fires_on_type3_no_tounicode(tmp_path):
    # the production regression fixture: a Type-3 text layer with no ToUnicode map
    # extracts as control-char garbage. Synthesized minimal (the r2 text layer is
    # clean, so it cannot be the red fixture — the reviewer's note).
    garb = tmp_path / "type3_garbled.pdf"
    garb.write_bytes(_type3_garbled_pdf())
    res = lg.check_text_layer(garb)
    assert res["pass"] is False and res["clean"] is False
    kinds = {f["kind"] for f in res["findings"]}
    assert "layout-text-unextractable" in kinds        # garbled extraction
    assert "layout-text-font-unmapped" in kinds        # the ToUnicode mechanism
    assert res["summary"]["type3_no_tounicode"] >= 1


@_render
def test_text_layer_clean_pdf_passes(tmp_path):
    clean = tmp_path / "clean.pdf"
    clean.write_bytes(_CLEAN_PDF)
    res = lg.check_text_layer(clean)
    assert res["pass"] is True and res["clean"] is True


@_render
def test_g1_folds_text_layer_into_the_size_gate(tmp_path):
    # G1 covers the text layer, not just the figures: a garbled Type-3 PDF fails
    # check_final_size_visual through the folded-in text-layer findings.
    garb = tmp_path / "type3_garbled.pdf"
    garb.write_bytes(_type3_garbled_pdf())
    res = lg.check_final_size_visual(garb)
    assert res["pass"] is False
    assert res["text_layer"]["clean"] is False
    assert any(f["kind"] == "layout-text-unextractable" for f in res["findings"])


def test_g1_thresholds_separate_figure_text_from_body_math():
    # the calibration is a real gap, not a fitted constant: the illegible floor sits
    # strictly between conventional body-math scripting and scaled-down figure text.
    assert lg._ILLEGIBLE_FLOOR_PT == pytest.approx(3.5)
    # a synthetic body page (44 sub-6pt glyphs, min 4.42pt) does NOT fire; a figure
    # page (437 glyphs, min 1.39pt) DOES — driven through the decision directly.
    def undersize(sub, mn):
        return (mn is not None and mn < lg._ILLEGIBLE_FLOOR_PT) or sub >= lg._PAGE_CLUSTER
    assert undersize(437, 1.39) is True                # Fig6
    assert undersize(671, 1.196) is True               # Fig7
    assert undersize(44, 4.423) is False               # densest r2 body page
    assert undersize(21, 5.308) is False               # a body page of 5pt scripts


# ===========================================================================
# G2 — semantic float gate
# ===========================================================================

@_have_ssg
def test_g2_fires_on_r2_orphan_and_boundary():
    res = lg.check_semantic_float(SSG, aux_path=R2_AUX, pdf_path=R2_PDF)
    assert res["pass"] is False
    assert res["conclusion_boundary"] == 24 and res["appendix_boundary"] == 25

    kinds = {(f["kind"], f["where"]) for f in res["findings"]}
    # Fig3 is never \ref'd — an orphan (aux-only, no synctex needed).
    assert any(k == "float-orphan" and "fig:f5-dp-price" in w for k, w in kinds)
    # Same-page boundary encounters need vertical visual order; page arithmetic
    # alone cannot distinguish a top float from a float below the heading.
    same = {r["label"] for r in res["same_page_boundaries"]}
    assert "fig:nf6" in same                            # Fig7 / conclusion p24
    assert "fig:nf7" in same                            # Fig8 / appendix p25


@_have_ssg
@pytest.mark.skipif(not (_HAVE_SYNCTEX and R2_PDF.is_file()),
                    reason="exact ref-page backlog needs synctex + the PDF")
def test_g2_backlog_pages_are_exact_via_synctex():
    res = lg.check_semantic_float(SSG, aux_path=R2_AUX, pdf_path=R2_PDF)
    reg = {r["label"]: r for r in res["figures"]}
    # his measured mention->landing backlogs, resolved exactly through synctex.
    assert reg["fig:nf1"]["first_ref_page"] == 1 and reg["fig:nf1"]["landing_page"] == 3
    assert reg["fig:nf3"]["first_ref_page"] == 14 and reg["fig:nf3"]["landing_page"] == 21
    assert reg["fig:nf6"]["first_ref_page"] == 19 and reg["fig:nf6"]["landing_page"] == 24
    assert reg["fig:nf3"]["ref_page_method"] == "synctex"
    backlogs = {f["where"]: f["backlog"] for f in res["findings"]
                if f["kind"] == "float-backlog"}
    assert any("fig:nf3" in w and b == 7 for w, b in backlogs.items())   # Fig4 14->21


def test_g2_passes_on_clean_fixture(tmp_path):
    _write_clean_manuscript(tmp_path)
    res = lg.check_semantic_float(tmp_path, aux_path=tmp_path / "main.aux")
    assert res["pass"] is True and res["clean"] is True
    assert res["findings"] == []
    # the figure is referenced, near-placed, and lands before the conclusion.
    reg = {r["label"]: r for r in res["figures"]}
    assert reg["fig:good"]["orphan"] is False


# ===========================================================================
# G3 — figure contract registry
# ===========================================================================

@_render
@_have_ssg
def test_g3_fires_on_r2_panel_disagreement():
    res = lg.check_figure_contract(SSG, aux_path=R2_AUX, pdf_path=R2_PDF)
    assert res["pass"] is False
    reg = {r["label"]: r for r in res["registry"]}
    # the registry carries the structured contract fields.
    nf6 = reg["fig:nf6"]
    assert set(("hero_claim", "evidence_type", "panel_labels_caption",
                "panel_labels_asset", "caption_coverage", "landing_page",
                "data_key", "limitation")) <= set(nf6)
    # Fig7's ASSET draws more panels than its CAPTION covers — the coverage hole.
    assert set(nf6["panel_labels_caption"]) < set(nf6["panel_labels_asset"])
    uncovered = [f for f in res["findings"] if f["kind"] == "figure-panel-uncovered"]
    assert any("fig:nf6" in f["where"] for f in uncovered)
    # Fig3 the orphan is noted in the contract too.
    assert any(f["kind"] == "figure-contract-orphan" and "fig:f5-dp-price" in f["where"]
               for f in res["findings"])


@_have_ssg
def test_g3_panel_agreement_is_source_only_without_asset():
    # with asset resolution off, G3 still enforces caption<->body panel agreement
    # from the source alone (no rasteriser needed).
    res = lg.check_figure_contract(SSG, aux_path=R2_AUX, resolve_asset_panels=False)
    assert isinstance(res["registry"], list) and res["registry"]
    # no asset panels resolved -> the uncovered-asset check is silent, but the
    # registry is still built and the orphan note still fires.
    assert all(r["panel_labels_asset"] == [] for r in res["registry"])
    assert any(f["kind"] == "figure-contract-orphan" for f in res["findings"])


def test_g3_passes_on_clean_fixture(tmp_path):
    _write_clean_manuscript(tmp_path)
    res = lg.check_figure_contract(tmp_path, aux_path=tmp_path / "main.aux",
                                   resolve_asset_panels=False)
    assert res["pass"] is True and res["clean"] is True
    assert res["findings"] == []
    reg = {r["label"]: r for r in res["registry"]}
    # caption and body name the same panels -> agreement, no finding.
    assert reg["fig:good"]["panel_labels_caption"] == reg["fig:good"]["panel_labels_body"]


def test_g3_registry_writes_json_artefact(tmp_path):
    _write_clean_manuscript(tmp_path)
    res = lg.check_figure_contract(tmp_path, aux_path=tmp_path / "main.aux",
                                   resolve_asset_panels=False)
    out = lg.write_registry(res, tmp_path / "figure_registry.json")
    data = json.loads(Path(out).read_text())
    assert isinstance(data, list) and data[0]["label"] == "fig:good"


# ===========================================================================
# the release seam — all three gates over one artefact
# ===========================================================================

@_render
@_have_ssg
def test_run_layout_gates_aggregates_all_three_on_r2():
    res = lg.run_layout_gates(R2_PDF, SSG, aux_path=R2_AUX)
    assert res["clean"] is False
    assert set(res["gates"]) == {"size", "float", "contract"}
    kinds = set(res["counts"])
    # every gate contributed at least one real finding.
    assert "layout-text-undersize" in kinds
    assert "float-orphan" in kinds or "float-past-boundary" in kinds
    assert "figure-panel-uncovered" in kinds


def test_release_layout_gate_results_wiring_shape(tmp_path):
    # the release seam returns a gate_results-shaped dict; on a manuscript with no
    # PDF it is a loud non-pass, never a silent clean.
    from laplace.pipeline import release
    res = release.layout_gate_results(tmp_path)
    assert res["clean"] is False and res["pass"] is False


# ===========================================================================
# denominator honesty — an unreadable page/figure surfaces skipped_n, never a
# silent shrink of the denominator into a false clean pass
# ===========================================================================

def test_g3_unreadable_fragment_surfaces_skipped_n(tmp_path):
    # a `.tex` that is actually a directory raises IsADirectoryError (an OSError) on
    # read — the per-fragment skip leg fires and MUST be counted, not swallowed.
    _write_clean_manuscript(tmp_path)
    os.mkdir(tmp_path / "broken.tex")
    res = lg.check_figure_contract(tmp_path, aux_path=tmp_path / "main.aux",
                                   resolve_asset_panels=False)
    assert res["skipped_n"] >= 1              # the unreadable fragment is visible
    assert res["examined_n"] >= 1             # main.tex still read
    # the readable figure is still in the registry (skip behavior kept, not fatal)
    assert any(r["label"] == "fig:good" for r in res["registry"])


def test_g2_unreadable_aux_surfaces_skipped_n(tmp_path):
    # an unreadable .aux empties the figure set, which would otherwise read as a
    # clean pass over zero figures; skipped_n makes that loss visible.
    _write_clean_manuscript(tmp_path)
    res = lg.check_semantic_float(tmp_path, aux_path=tmp_path)   # a dir -> unreadable
    assert res["skipped_n"] == 1
    assert res["examined_n"] == 0
    assert res["figures"] == []


def test_g2_readable_aux_reports_zero_skips(tmp_path):
    _write_clean_manuscript(tmp_path)
    res = lg.check_semantic_float(tmp_path, aux_path=tmp_path / "main.aux")
    assert res["skipped_n"] == 0 and res["examined_n"] >= 1


def test_g2_propagates_explicit_synctex_binary(tmp_path, monkeypatch):
    _write_clean_manuscript(tmp_path)
    pdf = tmp_path / "main.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    seen = {}

    def fake_region(pdf_path, source_file, line, *, label="", synctex_bin="synctex"):
        seen["bin"] = synctex_bin
        return lg._vg.Region(page=1, x0=0, y0=0, x1=1, y1=1, label=label)

    monkeypatch.setattr(lg._vg, "synctex_region", fake_region)
    res = lg.check_semantic_float(
        tmp_path,
        aux_path=tmp_path / "main.aux",
        pdf_path=pdf,
        synctex_bin="C:/tools/synctex.exe",
    )

    assert seen["bin"] == "C:/tools/synctex.exe"
    assert res["figures"][0]["ref_page_method"] == "synctex"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _write_clean_manuscript(root: Path) -> None:
    """A synthetic clean manuscript: a figure referenced in the body, landing one
    page later (backlog 1, within tolerance), well before the conclusion, with
    caption panels that match the body-described panels."""
    aux = root / "main.aux"
    aux.write_text(
        r"\newlabel{sec:intro}{{I}{1}{}{section.1}{}}" "\n"
        r"\newlabel{sec:methods}{{II}{2}{}{section.2}{}}" "\n"
        r"\newlabel{sec:results}{{III}{3}{}{section.3}{}}" "\n"
        r"\newlabel{sec:conclusion}{{IV}{4}{}{section.4}{}}" "\n"
        r"\newlabel{app:extra}{{A}{5}{}{appendix.A}{}}" "\n"
        r"\newlabel{fig:good}{{1}{2}{A clean two-panel figure. Panel (a) shows the "
        r"input $x$; panel (b) shows the output $y$.}{figure.1}{}}" "\n",
        encoding="utf-8")
    main = root / "main.tex"
    main.write_text(
        r"\documentclass{article}" "\n\\begin{document}\n"
        r"\section{Intro}\label{sec:intro}" "\n"
        r"\section{Methods}\label{sec:methods}" "\n"
        r"We plot the pipeline in Fig.~\ref{fig:good}: panel (a) is the input and "
        r"panel (b) the output." "\n"
        r"\begin{figure}\centering\includegraphics{fig_good}"
        r"\caption{A clean two-panel figure. Panel (a) shows the input $x$; "
        r"panel (b) shows the output $y$.}\label{fig:good}\end{figure}" "\n"
        r"\section{Results}\label{sec:results}" "\n"
        r"\section{Conclusion}\label{sec:conclusion}" "\n"
        r"\appendix" "\n"
        r"\section{Extra}\label{app:extra}" "\n"
        r"\end{document}" "\n",
        encoding="utf-8")


def _type3_garbled_pdf(n_words: int = 60) -> bytes:
    """A minimal one-page PDF whose text layer is a Type-3 font with NO ToUnicode
    map and non-standard glyph names — pdfium extracts its ~300 glyphs as control
    chars (letter-ratio 0, control-ratio ~1). The synthetic red fixture for the
    text-layer machine-readability gate (the r2 body text is clean, so it cannot be
    the red fixture — the reviewer's note)."""
    glyph = b"1000 0 d0\n0 0 700 700 re f\n"
    objs: dict[int, bytes] = {}
    objs[8] = b"<</Length %d>>stream\n" % len(glyph) + glyph + b"endstream"
    objs[6] = b"<</g1 8 0 R/g2 8 0 R/g3 8 0 R/g4 8 0 R/g5 8 0 R>>"
    objs[7] = b"<</Type/Encoding/Differences[1/g1/g2/g3/g4/g5]>>"
    objs[5] = (b"<</Type/Font/Subtype/Type3/FontBBox[0 0 1000 1000]"
               b"/FontMatrix[0.001 0 0 0.001 0 0]/CharProcs 6 0 R/Encoding 7 0 R"
               b"/FirstChar 1/LastChar 5/Widths[700 700 700 700 700]>>")
    body = b"BT /F1 18 Tf\n"
    y, per_line, i = 740, 10, 0
    while i < n_words:
        body += b"1 0 0 1 60 %d Tm " % y
        body += b"".join(b"<0102030405> Tj " for _ in range(per_line)) + b"\n"
        y -= 24
        i += per_line
    body += b"ET\n"
    objs[4] = b"<</Length %d>>stream\n" % len(body) + body + b"endstream"
    objs[3] = (b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
               b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>")
    objs[2] = b"<</Type/Pages/Kids[3 0 R]/Count 1>>"
    objs[1] = b"<</Type/Catalog/Pages 2 0 R>>"
    out = b"%PDF-1.4\n"
    off: dict[int, int] = {}
    for k in sorted(objs):
        off[k] = len(out)
        out += b"%d 0 obj" % k + objs[k] + b"endobj\n"
    xp = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for k in sorted(objs):
        out += b"%010d 00000 n \n" % off[k]
    out += (b"trailer<</Root 1 0 R/Size %d>>\nstartxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, xp))
    return out


# a minimal valid one-page PDF: "Clean body text..." set in 12pt Helvetica (Type-1,
# base-14, no embedded Type-3, no sub-6pt glyph, nothing clipped).
_CLEAN_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
    b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj\n"
    b"4 0 obj<</Length 66>>stream\n"
    b"BT /F1 12 Tf 72 700 Td (Clean body text at twelve points.) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"xref\n0 6\n0000000000 65535 f \n"
    b"trailer<</Root 1 0 R/Size 6>>\nstartxref\n0\n%%EOF\n")
