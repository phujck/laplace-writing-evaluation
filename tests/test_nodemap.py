"""The nodemap organ (G-1) — the node→page-region map machinery.

Layered like ``test_drift``: the pure functions (injection determinism, rect
assembly, .aux parsing, the warning-class detector, caption-outside-braces) run
with no subprocess; the end-to-end tests build REAL PDFs with ``latexmk`` and
rasterise through the same isolated ``uv run --with pypdfium2`` path visual_gate
proves. The module skips cleanly where latexmk or the rasteriser is unavailable,
so it never hard-fails a thin box. Every fixture lives in ``tmp_path`` — nothing
here touches a live manuscript tree.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from laplace.pipeline import nodemap

pytestmark = pytest.mark.skipif(shutil.which("latexmk") is None,
                                reason="latexmk not installed")

# ---------------------------------------------------------------------------
# The fixture manuscript: two-column, a deferred full-width figure*, a table,
# display equation, paragraph markers, and % NODES: rosters with roster-only ids.
# ---------------------------------------------------------------------------

_MAIN = (
    "\\documentclass[twocolumn]{article}\n"
    "\\usepackage{graphicx}\n"
    "\\usepackage{lipsum}\n"
    "\\begin{document}\n"
    "\\listoffigures\n"
    "\\input{S1}\n"
    "\\input{S2}\n"
    "\\end{document}\n")

_S1 = (
    "\\section{Method}\\label{sec:method}\n"
    "% NODES: def:bound, res:gap, irf:only-roster\n"
    "% S1-p1\n"
    "\\lipsum[1]\n"
    "Some intro text before the equation here.\n"
    "\\begin{equation}\\label{def:bound}\n"
    "E = mc^2 .\n"
    "\\end{equation}\n"
    "The bound \\ref{def:bound} governs the estimate.\n"
    "% S1-p2\n"
    "\\lipsum[2]\n")

_S2 = (
    "\\section{Results}\\label{sec:results}\n"
    "% NODES: fig:big, thm:key\n"
    "% S2-p1\n"
    "\\lipsum[3]\n"
    "\\begin{figure*}\n"
    "\\centering\n"
    "\\rule{0.9\\textwidth}{4in}\n"
    "\\caption{A large full width figure that defers to a float page.}\n"
    "\\label{fig:big}\n"
    "\\end{figure*}\n"
    "\\lipsum[4]\n"
    "% S2-p2\n"
    "\\lipsum[5]\n"
    "\\begin{table}\n"
    "\\centering\n"
    "\\begin{tabular}{cc} a & b \\\\ c & d \\end{tabular}\n"
    "\\caption{A small table.}\n"
    "\\label{tab:small}\n"
    "\\end{table}\n"
    "More results text \\ref{fig:big}.\n")

_FILES = {"main.tex": _MAIN, "S1.tex": _S1, "S2.tex": _S2}


def _write_fixture(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, body in _FILES.items():
        (root / name).write_text(body, encoding="utf-8")
    return root / "main.tex"


def _latexmk(d: Path, name: str, body: str) -> tuple[Path, Path]:
    (d / f"{name}.tex").write_text(body, encoding="utf-8")
    subprocess.run(["latexmk", "-pdf", "-synctex=1", "-interaction=nonstopmode",
                    f"{name}.tex"], cwd=str(d), capture_output=True, timeout=180)
    return d / f"{name}.pdf", d / f"{name}.log"


@pytest.fixture(scope="module")
def raster_ok(tmp_path_factory):
    """Probe: latexmk builds a pdf and the isolated rasteriser reads it. Skip the
    compile-dependent tests (never fail) if the box can't do it."""
    d = tmp_path_factory.mktemp("nm_probe")
    pdf, _ = _latexmk(d, "probe",
                      r"\documentclass{article}\begin{document}hi\end{document}")
    if not pdf.is_file():
        pytest.skip("latexmk failed to build a probe pdf")
    try:
        from laplace.pipeline.visual_gate import rasterise_pdf
        rasterise_pdf(str(pdf), str(d / "_r"))
    except RuntimeError as exc:
        pytest.skip(f"isolated rasteriser unavailable: {exc}")
    return True


@pytest.fixture(scope="module")
def built(tmp_path_factory, raster_ok):
    """Build the nodemap ONCE on the fixture (kept instrumented so tests can
    inspect the instrumented .aux/.lof)."""
    src = tmp_path_factory.mktemp("nm_src")
    main = _write_fixture(src)
    res = nodemap.build_nodemap(main, keep_instrumented=True)
    scratch = Path(res["_scratch"])
    yield {"res": res, "scratch": scratch, "main": main, "src": src}
    shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# pure functions — no subprocess
# ---------------------------------------------------------------------------

def test_injection_is_deterministic(tmp_path):
    """Two injections of the same tree + specs are byte-identical (spike: a pure
    function of tree bytes and spec list — no RNG, no clock)."""
    src = tmp_path / "src"
    _write_fixture(src)
    specs, _ = nodemap.discover_specs(src)
    a, b = tmp_path / "a", tmp_path / "b"
    nodemap.inject(src, a, specs)
    nodemap.inject(src, b, specs)
    files_a = sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    assert files_a == files_b and files_a
    for rel in files_a:
        assert (a / rel).read_bytes() == (b / rel).read_bytes(), rel


def test_preamble_inserted_once(tmp_path):
    src = tmp_path / "src"
    _write_fixture(src)
    specs, _ = nodemap.discover_specs(src)
    out = tmp_path / "out"
    nodemap.inject(src, out, specs)
    main = (out / "main.tex").read_text(encoding="utf-8")
    assert main.count("\\usepackage{zref-savepos}") == 1
    assert main.count("\\usepackage{zref-abspage}") == 1
    assert main.count("\\zref@addprop{savepos}{abspage}") == 1


def test_caption_marker_is_outside_the_braces(tmp_path):
    """The production discipline (spike gap 1): the caption marker sits on its own
    line AFTER \\caption{...} closes — never inside the moving argument."""
    src = tmp_path / "src"
    _write_fixture(src)
    specs, _ = nodemap.discover_specs(src)
    out = tmp_path / "out"
    nodemap.inject(src, out, specs)
    lines = (out / "S2.tex").read_text(encoding="utf-8").splitlines()
    cap_i = next(i for i, ln in enumerate(lines) if "\\caption{A large full" in ln)
    assert "zsavepos" not in lines[cap_i]                 # not inside the braces
    assert lines[cap_i + 1].strip() == "\\zsavepos{ZP@cap-fig-big}"  # own line, after


def test_rects_from_records_point_anchor():
    geom = {2: (612.0, 792.0)}
    rec = {"posx": int(72.27 * 65536), "posy": int(300.0 * 65536), "abspage": 2}
    rects = nodemap._rects_from_records({"point": rec}, geom, "paragraph", "inferred")
    assert len(rects) == 1
    r = rects[0]
    assert r["page"] == 2 and r["kind"] == "paragraph" and r["width"] == "inferred"
    assert abs(r["x0"] - 72.27) < 0.1
    assert abs(r["y0"] - (792.0 - 300.0)) < 0.1        # y-flip
    assert r["y1"] == r["y0"]                            # baseline anchor
    assert abs(r["x1"] - (612.0 - 72.27)) < 0.1         # mirrored margin (inferred)


def test_rects_from_records_multirect_spans_pages():
    """A float whose top/bottom markers land on different abspages yields one rect
    per spanned page (spike: multi-rect on page/column break)."""
    geom = {3: (612.0, 792.0), 4: (612.0, 792.0), 5: (612.0, 792.0)}
    t = {"posx": int(72.0 * 65536), "posy": int(100.0 * 65536), "abspage": 3}  # near bottom
    b = {"posx": int(72.0 * 65536), "posy": int(700.0 * 65536), "abspage": 5}  # near top
    rects = nodemap._rects_from_records({"t": t, "b": b}, geom, "float", "inferred")
    assert [r["page"] for r in rects] == [3, 4, 5]
    assert rects[0]["y0"] == pytest.approx(792.0 - 100.0)  # top page: marker -> bottom
    assert rects[0]["y1"] == pytest.approx(792.0)
    assert rects[1]["y0"] == 0.0 and rects[1]["y1"] == pytest.approx(792.0)  # full mid
    assert rects[2]["y0"] == 0.0
    assert rects[2]["y1"] == pytest.approx(792.0 - 700.0)  # bottom page: top -> marker


def test_parse_aux_reads_only_zp_records(tmp_path):
    aux = tmp_path / "main.aux"
    aux.write_text(
        "\\relax\n"
        "\\zref@newlabel{ZP@S1-p1}{\\posx{4736286}\\posy{38872656}\\abspage{1}}\n"
        "\\zref@newlabel{ZP@fig-big-t}{\\posx{4736286}\\posy{36124244}\\abspage{2}}\n"
        "\\newlabel{def:bound}{{1}{1}}\n", encoding="utf-8")
    recs = nodemap.parse_aux(aux)
    assert set(recs) == {"ZP@S1-p1", "ZP@fig-big-t"}
    assert recs["ZP@S1-p1"] == {"posx": 4736286, "posy": 38872656, "abspage": 1}
    assert recs["ZP@fig-big-t"]["abspage"] == 2


def test_warn_classes_ignores_package_banner(tmp_path):
    """The warning-class detector must not count a package banner ('Providing
    info/warning/error messages') as a warning — that phantom class fired the drift
    gate on a fixture without hyperref."""
    log = tmp_path / "main.log"
    log.write_text(
        "Package: infwarerr 2019/12/03 v1.5 Providing info/warning/error messages (HO)\n"
        "LaTeX Warning: Reference `x' on page 3 undefined on input line 42.\n"
        "Overfull \\hbox (12.3pt too wide) in paragraph at lines 5--6\n",
        encoding="utf-8")
    classes = nodemap._warn_classes(log)
    assert not any("Providing info/warning/error" in k for k in classes)
    assert any("Reference" in k for k in classes)
    assert any("Overfull" in k for k in classes)


def test_source_fingerprint_changes_on_edit(tmp_path):
    src = tmp_path / "src"
    _write_fixture(src)
    fp0 = nodemap.source_fingerprint(src)
    assert fp0.startswith("sha256:")
    assert nodemap.source_fingerprint(src) == fp0        # stable
    (src / "S1.tex").write_text(_S1 + "\nAn extra sentence.\n", encoding="utf-8")
    assert nodemap.source_fingerprint(src) != fp0        # flips on content change


# ---------------------------------------------------------------------------
# the drift gate — the layout-equivalence guarantee
# ---------------------------------------------------------------------------

def test_layout_equivalent_passes_identical_and_refuses_shift(tmp_path, raster_ok):
    """Clean-vs-clean is layout-equivalent; a real text change (the spike's
    'simulate via a real text change') moves a page and the gate REFUSES."""
    d = tmp_path / "b"
    d.mkdir()
    clean_pdf, clean_log = _latexmk(
        d, "clean", r"\documentclass{article}\begin{document}"
                    r"Alpha content on the page here.\end{document}")
    shift_pdf, shift_log = _latexmk(
        d, "shift", r"\documentclass{article}\begin{document}"
                    r"COMPLETELY different words fill this page instead.\end{document}")
    assert clean_pdf.is_file() and shift_pdf.is_file()

    same = nodemap.layout_equivalent(clean_pdf, clean_pdf, clean_log, clean_log,
                                     out_dir=tmp_path / "g1")
    assert same["ok"] is True and same["drift"]["changed_count"] == 0

    shifted = nodemap.layout_equivalent(clean_pdf, shift_pdf, clean_log, shift_log,
                                        out_dir=tmp_path / "g2")
    assert shifted["ok"] is False
    assert shifted["drift"]["changed_count"] >= 1


def test_build_raises_on_layout_shift(tmp_path, raster_ok, monkeypatch):
    """If the instrumentation ever moved layout, build_nodemap raises rather than
    building a map on a shifted PDF (spike gap 4). Forced by wrapping inject to
    append visible text to the instrumented copy."""
    src = tmp_path / "src"
    main = _write_fixture(src)
    real_inject = nodemap.inject

    def shifting_inject(source_dir, out_dir, specs, main_name="main.tex"):
        r = real_inject(source_dir, out_dir, specs, main_name=main_name)
        p = Path(out_dir) / "S1.tex"
        p.write_text(p.read_text(encoding="utf-8")
                     + "\n\n" + ("A whole extra visible paragraph. " * 60) + "\n",
                     encoding="utf-8")
        return r

    monkeypatch.setattr(nodemap, "inject", shifting_inject)
    with pytest.raises(nodemap.LayoutDriftError) as exc:
        nodemap.build_nodemap(main, out_dir=tmp_path / "out")
    assert not exc.value.report["ok"]
    assert not (tmp_path / "out" / "main.nodemap.json").exists()  # no map written


# ---------------------------------------------------------------------------
# end-to-end — the built map
# ---------------------------------------------------------------------------

def test_gate_passes_and_map_written(built):
    res = built["res"]
    assert res["gate"]["ok"] is True
    assert res["gate"]["changed_count"] == 0
    assert res["gate"]["new_warning_classes"] == []
    assert (built["src"] / "main.nodemap.json").is_file()          # default out_dir
    assert res["source_fingerprint"].startswith("sha256:")
    assert res["tiers"] == ["T1", "T2"]


def test_coverage_full_on_positional_kinds(built):
    cov = built["res"]["coverage"]
    assert cov["paragraphs"] == {"mapped": 4, "total": 4, "pct": 100.0}
    assert cov["equations"] == {"mapped": 1, "total": 1, "pct": 100.0}
    assert cov["floats"] == {"mapped": 2, "total": 2, "pct": 100.0}
    assert cov["captions"] == {"mapped": 2, "total": 2, "pct": 100.0}
    assert cov["overall"]["pct"] == 100.0
    assert cov["roster_only"] == 3


def test_roster_only_ids_counted_unmapped_not_dropped(built):
    """Ids named only in a % NODES: roster (no \\label, no paragraph marker) are
    UNMAPPED with reason roster-only — never silently dropped (spike gap 3)."""
    res = built["res"]
    unmapped = {u["node_id"]: u for u in res["unmapped"]}
    for rid in ("res:gap", "irf:only-roster", "thm:key"):
        assert unmapped.get(rid, {}).get("reason") == "roster-only"
        assert rid not in res["entries"]                 # not faked into the map


def test_float_maps_to_its_deferred_shipout_page(built):
    """The savepos win: the full-width figure* defers off its source page, and the
    float rect lands on the page it actually ships out on — not the galley page a
    naive \\label reverse-map would give."""
    res = built["res"]
    fig_float = [r for r in res["entries"]["fig:big"] if r["kind"] == "float"]
    assert fig_float, "fig:big has no float rect"
    fpage = fig_float[0]["page"]
    s2p1 = res["entries"]["S2-p1"][0]["page"]            # the section text before it
    assert fpage != s2p1                                 # the float detached and deferred
    assert fig_float[0]["width"] == "inferred"           # left-marker + mirrored margin


def test_equation_rect_from_synctex_with_savepos_crosscheck(built):
    eq = built["res"]["entries"]["def:bound"]
    assert len(eq) == 1 and eq[0]["kind"] == "equation"
    assert eq[0]["width"] == "measured"                  # a real synctex box
    assert eq[0]["crosscheck"] == "ok"                   # savepos page == synctex page
    assert eq[0]["x1"] > eq[0]["x0"] and eq[0]["y1"] > eq[0]["y0"]


def test_caption_marker_does_not_leak_into_lof(built):
    """The compiled proof of caption-outside-braces: the .lof carries the caption
    text but NOT the marker (inside-the-braces would propagate it into the moving
    argument — spike risk 1)."""
    lof = built["scratch"] / "instr" / "main.lof"
    assert lof.is_file()
    text = lof.read_text(encoding="utf-8")
    assert "A large full width figure" in text           # the caption did reach .lof
    assert "zsavepos" not in text and "ZP@" not in text  # the marker did not


def test_savepos_roundtrip_paragraph_on_expected_page(built):
    """The .aux round-trip: a known first-section paragraph marker resolves to
    page 1, with a rect inside the page bounds."""
    p = built["res"]["entries"]["S1-p1"][0]
    assert p["page"] == 1 and p["kind"] == "paragraph"
    assert 0 <= p["x0"] < p["x1"] <= 612.0 + 1
    assert 0 <= p["y0"] <= 792.0


def test_freshness_flips_on_tree_change(tmp_path, raster_ok):
    """nodemap_fresh is True right after a build and flips False when the source
    tree changes (the viewer then raises the loud stale banner, ruling 4)."""
    src = tmp_path / "src"
    main = _write_fixture(src)
    out = tmp_path / "out"
    nodemap.build_nodemap(main, out_dir=out)
    assert nodemap.nodemap_fresh(main, out_dir=out) is True
    (src / "S2.tex").write_text(_S2 + "\nAn added trailing sentence.\n",
                                encoding="utf-8")
    assert nodemap.nodemap_fresh(main, out_dir=out) is False
