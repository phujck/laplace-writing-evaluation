"""F31 figure re-authoring: the figstyle house laws are ENFORCED mechanically at
the emit boundary, not left to each generator to re-honour (his emphatic steer:
the figures still carried tics, titles, and illegible text — "I hate it").

Two surfaces are asserted here:

  * ``figstyle.save`` enforces the no-titles law (no suptitle / headline title
    ever ships), the readable-font floor (nothing below 6pt at placed size), and
    Type-42 embedding (never matplotlib's non-embeddable Type-3 default);
  * the regenerated manuscript figure assets carry the improvement — zero Type-3
    fonts, the NF6/Fig7 panel split resolved (asset draws exactly the panels its
    caption covers), and the crushed single-column decoder figure (NF5/Fig6) far
    below its r3 sub-6pt count now that it is authored full width.

The render-dependent assertions run in the isolated ``uv --with pypdfium2/pikepdf``
subprocess and skip where uv is unavailable; the rcParams/artist assertions run
everywhere (matplotlib only).
"""
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIGDIR = REPO / "synthetics papers/subset-sum-itqde/manuscript/figures"
WPFIG = REPO / "synthetics papers/subset-sum-itqde/manuscript/whitepaper/figures"

if str(FIGDIR) not in sys.path:
    sys.path.insert(0, str(FIGDIR))

matplotlib = pytest.importorskip("matplotlib")
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import figstyle as fs  # noqa: E402

_HAVE_UV = bool(shutil.which("uv"))
_uv = pytest.mark.skipif(not _HAVE_UV, reason="needs uv (pypdfium2/pikepdf)")


def _measure(pdf):
    from laplace.pipeline.layout_gates import measure_pdf_text
    return measure_pdf_text(str(pdf))


# ---------------------------------------------------------------------------
# the no-titles law
# ---------------------------------------------------------------------------

def test_no_titles_law_strips_suptitle_and_headline(tmp_path):
    fs.use_house_style()
    fig, ax = plt.subplots(figsize=(fs.COL_DOUBLE_IN, 2.0))
    ax.plot([0, 1], [0, 1])
    fig.suptitle("THE FIGURE NARRATING ITSELF")
    ax.set_title("a headline title", loc="center")
    ax.set_title("left tag", loc="left")
    fs.save(fig, tmp_path / "notitle", preview=False)
    # both the suptitle and every spanning axes title are stripped at the emit.
    assert fig._suptitle is None or not fig._suptitle.get_visible()
    for loc in ("center", "left", "right"):
        assert ax.get_title(loc=loc) == ""
    plt.close(fig)


# ---------------------------------------------------------------------------
# the readable-font floor
# ---------------------------------------------------------------------------

def test_font_floor_bumps_sub_floor_text(tmp_path):
    fs.use_house_style()
    fig, ax = plt.subplots(figsize=(fs.COL_DOUBLE_IN, 2.0))
    ax.plot([0, 1], [0, 1])
    tiny = ax.text(0.5, 0.5, "illegibly small", fontsize=3.0)
    mid = ax.text(0.5, 0.7, "also too small", fontsize=5.5)
    scale = fs.placed_scale(fig, "double")
    floor_native = fs.MIN_PLACED_PT / scale
    fs.save(fig, tmp_path / "floor", preview=False, col="double")
    # every sub-floor artist lands at (or above) the floor at placed size.
    assert tiny.get_fontsize() >= floor_native - 1e-6
    assert mid.get_fontsize() >= floor_native - 1e-6
    assert tiny.get_fontsize() * scale >= fs.MIN_PLACED_PT - 1e-6
    plt.close(fig)


def test_font_floor_leaves_large_text_untouched(tmp_path):
    fs.use_house_style()
    fig, ax = plt.subplots(figsize=(fs.COL_DOUBLE_IN, 2.0))
    big = ax.text(0.5, 0.5, "already fine", fontsize=12.0)
    fs.save(fig, tmp_path / "big", preview=False, col="double")
    assert big.get_fontsize() == 12.0          # no needless mutation
    plt.close(fig)


def test_single_column_floor_is_stricter_than_double():
    # a single-column placement (narrower page width) demands a larger native
    # font for the same placed size — the scale is smaller, the floor higher.
    fs.use_house_style()
    fig = plt.figure(figsize=(fs.COL_DOUBLE_IN, 2.0))
    s_single = fs.placed_scale(fig, "single")
    s_double = fs.placed_scale(fig, "double")
    assert s_single < s_double                 # 7in fig dropped into 1 column shrinks
    plt.close(fig)


# ---------------------------------------------------------------------------
# Type-42 embedding
# ---------------------------------------------------------------------------

def test_use_house_style_pins_fonttype_42():
    fs.use_house_style()
    assert plt.rcParams["pdf.fonttype"] == 42
    assert plt.rcParams["ps.fonttype"] == 42


@_uv
def test_saved_pdf_has_no_type3_fonts(tmp_path):
    fs.use_house_style()
    fig, ax = plt.subplots(figsize=(fs.COL_DOUBLE_IN, 2.0))
    ax.plot([0, 1, 2], [0, 1, 4])
    ax.set_xlabel(r"coupling $J$ and $\chi_{\mathrm{req}}$")   # mathtext present
    ax.text(0.5, 2, r"$V_{XXZ}$ tilt $\sigma^2$", fontsize=9)
    pdf = fs.save(fig, tmp_path / "type42", preview=False, col="double")
    m = _measure(pdf)
    assert m["type3_fonts"] == []              # TrueType/Type-42, never Type-3
    plt.close(fig)


# ---------------------------------------------------------------------------
# the regenerated manuscript assets carry the gate improvement
# ---------------------------------------------------------------------------

@_uv
@pytest.mark.skipif(not (WPFIG / "NF5.pdf").is_file(),
                    reason="needs the regenerated manuscript figure assets")
def test_shipped_assets_have_no_type3():
    # the r3 whitepaper embedded 55 Type-3 fonts (figures predating the fonttype=42
    # landing); the regenerated assets carry none.
    for asset in ("NF5.pdf", "NF6.pdf", "NF6b.pdf", "NF4.pdf", "N12_identities.pdf"):
        m = _measure(WPFIG / asset)
        assert m["type3_fonts"] == [], f"{asset} still embeds Type-3 {m['type3_fonts'][:3]}"


@_uv
@pytest.mark.skipif(not (WPFIG / "NF6.pdf").is_file(),
                    reason="needs the regenerated NF6/NF6b assets")
def test_nf6_split_resolves_panel_mismatch():
    from laplace.pipeline.layout_gates import extract_asset_panels
    panels = extract_asset_panels([WPFIG / "NF6.pdf", WPFIG / "NF6b.pdf"])
    # NF6 (Fig7) now draws exactly the (a),(b),(c) operating-window panels its
    # caption covers — the old (d),(e) time-domain panels split out to NF6b.
    assert panels.get("NF6.pdf") == ["a", "b", "c"]
    assert panels.get("NF6b.pdf") == ["a", "b"]


@_uv
@pytest.mark.skipif(not (WPFIG / "NF5.pdf").is_file(),
                    reason="needs the regenerated NF5 asset")
def test_nf5_decoder_far_below_r3_subcount():
    # NF5/Fig6 was 439 sub-6pt characters on r3 (crushed to ~0.49x in one column).
    # Authored full width at 1:1, its own sub-6pt count is an order of magnitude
    # lower and it carries no Type-3.
    m = _measure(WPFIG / "NF5.pdf")
    pg = m["pages"][0]
    assert m["type3_fonts"] == []
    assert pg["sub_count"] < 150               # was ~439 at r3 placed size
