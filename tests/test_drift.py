"""The PDF drift report — local fix vs global artefact.

Two layers, both hermetic (no network):

  * the pixel-diff core (``_page_changed``) is exercised on hand-built PNGs via
    Pillow — fast, no subprocess;
  * ``drift_report`` is driven end-to-end on REAL PDFs built with pdflatex and
    rasterised through the SAME isolated ``uv run --with pypdfium2`` pattern
    visual_gate proves. The module skips cleanly where pdflatex or the isolated
    rasteriser is unavailable, so it never hard-fails a thin box.
"""
import shutil
import subprocess

import pytest

from laplace.pipeline import drift

pytestmark = pytest.mark.skipif(shutil.which("pdflatex") is None,
                                reason="pdflatex not installed")

_ONE = (r"\documentclass{article}\begin{document}"
        r"Page one alpha content here.\end{document}")
_ONE_MOD = (r"\documentclass{article}\begin{document}"
            r"Page one COMPLETELY DIFFERENT content now.\end{document}")
_TWO = (r"\documentclass{article}\begin{document}"
        r"Page one alpha content here.\newpage Second page beta content."
        r"\end{document}")


def _compile(texdir, name, body):
    tex = texdir / f"{name}.tex"
    tex.write_text(body, encoding="utf-8")
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
         "-output-directory", str(texdir), str(tex)],
        cwd=str(texdir), capture_output=True, timeout=120)
    return texdir / f"{name}.pdf"


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory):
    """Build the three PDF fixtures once, and probe the isolated rasteriser; skip
    the whole module (never fail) if pdflatex or the rasteriser is unavailable."""
    d = tmp_path_factory.mktemp("drift_pdfs")
    one = _compile(d, "one", _ONE)
    one_mod = _compile(d, "one_mod", _ONE_MOD)
    two = _compile(d, "two", _TWO)
    for p in (one, one_mod, two):
        if not p.is_file():
            pytest.skip("pdflatex failed to build a fixture PDF")
    try:  # one cheap probe: is the isolated rasteriser reachable on this box?
        from laplace.pipeline.visual_gate import rasterise_pdf
        rasterise_pdf(str(one), str(d / "_probe"))
    except RuntimeError as exc:
        pytest.skip(f"isolated rasteriser unavailable: {exc}")
    return {"one": str(one), "one_mod": str(one_mod), "two": str(two), "dir": d}


# --- the pixel-diff core (no subprocess) ------------------------------------

def test_page_changed_identical_and_geometry(tmp_path):
    from PIL import Image
    a = tmp_path / "a.png"; b = tmp_path / "b.png"
    small = tmp_path / "small.png"; block = tmp_path / "block.png"
    img = Image.new("L", (100, 100), 200)
    img.save(a); img.copy().save(b)
    Image.new("L", (50, 50), 200).save(small)           # different geometry
    c = Image.new("L", (100, 100), 200)
    for x in range(20):                                  # 400/10000 = 4% flipped
        for y in range(20):
            c.putpixel((x, y), 0)
    c.save(block)
    assert drift._page_changed(str(a), str(b)) is False   # byte-identical
    assert drift._page_changed(str(a), str(small)) is True  # geometry change is a change
    assert drift._page_changed(str(a), str(block)) is True  # real reflow


def test_page_changed_absorbs_subthreshold_noise(tmp_path):
    from PIL import Image
    a = tmp_path / "a.png"; jitter = tmp_path / "j.png"; few = tmp_path / "f.png"
    base = Image.new("L", (100, 100), 200)
    base.save(a)
    # every pixel nudged by +8 (< _PIXEL_TOL 16): below the per-pixel floor.
    j = Image.eval(base, lambda v: v + 8)
    j.save(jitter)
    # only 5 pixels flipped hard: 5/10000 = 0.05% < _AREA_TOL 0.1%.
    f = base.copy()
    for x in range(5):
        f.putpixel((x, 0), 0)
    f.save(few)
    assert drift._page_changed(str(a), str(jitter)) is False   # per-pixel tolerance
    assert drift._page_changed(str(a), str(few)) is False       # area tolerance


# --- drift_report end-to-end on real PDFs -----------------------------------

def test_identical_pdf_reports_no_drift(pdfs, tmp_path):
    r = drift.drift_report(pdfs["one"], pdfs["one"], out_dir=tmp_path)
    assert r["page_count"] == {"incumbent": 1, "candidate": 1}
    assert r["pages_changed"] == []
    assert r["changed_count"] == 0
    assert r["unexpected"] is False


def test_content_change_same_page_count(pdfs, tmp_path):
    r = drift.drift_report(pdfs["one"], pdfs["one_mod"], out_dir=tmp_path)
    assert r["page_count"] == {"incumbent": 1, "candidate": 1}
    assert r["pages_changed"] == [1]
    assert r["changed_count"] == 1
    assert r["unexpected"] is False           # 1 changed page <= page_change_warn (3)


def test_page_count_change_is_always_loud(pdfs, tmp_path):
    r = drift.drift_report(pdfs["one"], pdfs["two"], out_dir=tmp_path)
    assert r["page_count"] == {"incumbent": 1, "candidate": 2}
    assert r["unexpected"] is True            # a page-count delta is ALWAYS loud
    assert "PAGE COUNT CHANGED" in r["notes"]
    assert 2 in r["pages_changed"]            # the added page counts as changed


def test_page_change_warn_threshold_drives_unexpected(pdfs, tmp_path):
    # lower the warn threshold below the observed change -> the same single-page
    # change now reads as unexpected. Proves the threshold is wired to the dial.
    tight = {"drift": {"page_change_warn": 0, "page_count_change": "loud"}}
    r = drift.drift_report(pdfs["one"], pdfs["one_mod"], out_dir=tmp_path, dials=tight)
    assert r["changed_count"] == 1
    assert r["unexpected"] is True
    assert "exceeds page_change_warn 0" in r["notes"]


def test_dirty_sections_echoed_as_g_phase_seam(pdfs, tmp_path):
    r = drift.drift_report(pdfs["one"], pdfs["one_mod"], out_dir=tmp_path,
                           dirty_sections=["sec:intro"])
    assert "dirty_sections=['sec:intro']" in r["notes"]
    assert "seam" in r["notes"]               # documented as not-yet-wired
