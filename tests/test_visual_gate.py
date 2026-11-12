"""The visual page gate (Phase D2): rasterise a compiled PDF, cut the mandatory
views, and package crops for a vision judge whose verdict parses into the standard
finding shape. The render tests exercise the REAL SSG whitepaper PDF when present
(rasterise via the isolated ``uv --with pypdfium2`` subprocess); the logic tests
(routing, verdict-parsing, overfull-log parsing) run everywhere."""
import os
import shutil
from pathlib import Path

import pytest

from laplace.pipeline import visual_gate as vg

REPO = Path(__file__).resolve().parents[1]
SSG = REPO / "synthetics papers/subset-sum-itqde/manuscript/whitepaper"
SSG_PDF = SSG / "main.pdf"

_HAVE_UV = bool(shutil.which(vg.DEFAULT_UV) or shutil.which("uv"))
_HAVE_SYNCTEX = bool(shutil.which("synctex"))
# The synctex SIDECAR is a build byproduct the ignore rules refuse to travel
# (.gitignore: whitepaper/*.synctex.gz), so a fresh clone has the tracked PDF but
# no label->region data — the two tests that need it must skip LOUDLY there, not
# fail (AUDIT_2026-07-15_the-pipeline-workflow-audit.md §C4: the suite's green must
# never depend on an untracked byproduct).
_HAVE_SYNCTEX_DATA = bool(list(SSG.glob("main.synctex*")))
_render = pytest.mark.skipif(
    not (_HAVE_UV and SSG_PDF.is_file()),
    reason="needs uv (pypdfium2) + the compiled SSG main.pdf")
_synctex_data = pytest.mark.skipif(
    not _HAVE_SYNCTEX_DATA,
    reason="main.synctex.gz not present (untracked build byproduct — see AUDIT_2026-07-15 §C4)")


# --- the finding-kinds manifest + routing (Phase F wiring contract) ----------

def test_every_visual_kind_routes_to_document():
    assert vg.VISUAL_FINDING_KINDS                 # non-empty manifest
    for kind in vg.VISUAL_FINDING_KINDS:
        assert vg.route(kind) == "document"


def test_routing_manifest_is_render_to_document():
    rows = vg.routing_manifest()
    assert {r["kind"] for r in rows} == set(vg.VISUAL_FINDING_KINDS)
    for r in rows:
        # Phase F wires KIND_TO_WORK[kind]="render"; WORK_TO_LAYER["render"]="document"
        assert r["work_kind"] == "render"
        assert r["owning_stage"] == "document"


def test_route_rejects_unknown_kind():
    with pytest.raises(KeyError):
        vg.route("not-a-visual-kind")


# --- the inspector interface: verdict parsing into {where, issue, fix, kind} --

def test_parse_verdict_bare_list():
    raw = """[
      {"where": "p6 right column", "issue": "equation past margin",
       "fix": "break the display", "kind": "equation-clip"},
      {"where": "p2", "issue": "too dense", "fix": "split", "kind": "crowded-page"}
    ]"""
    out = vg.parse_vision_verdict(raw)
    assert len(out) == 2
    for f in out:
        assert set(f) == {"where", "issue", "fix", "kind", "owning_stage"}
        assert f["owning_stage"] == "document"
        assert f["kind"] in vg.VISUAL_FINDING_KINDS


def test_parse_verdict_fenced_and_findings_envelope():
    raw = '```json\n{"findings": [{"where":"p1","issue":"x","fix":"y",' \
          '"kind":"tiny-label"}]}\n```'
    out = vg.parse_vision_verdict(raw)
    assert len(out) == 1 and out[0]["kind"] == "tiny-label"
    assert out[0]["owning_stage"] == "document"


def test_parse_verdict_unknown_kind_coerces_then_strict_drops():
    raw = '[{"where":"p1","issue":"x","fix":"y","kind":"gremlin"}]'
    lenient = vg.parse_vision_verdict(raw)
    assert lenient and lenient[0]["kind"] in vg.VISUAL_FINDING_KINDS  # coerced
    assert vg.parse_vision_verdict(raw, strict=True) == []            # dropped


def test_parse_verdict_empty_and_malformed_never_crash():
    assert vg.parse_vision_verdict("[]") == []
    assert vg.parse_vision_verdict("not json at all") == []
    assert vg.parse_vision_verdict("") == []


# --- the deterministic overfull-log floor -----------------------------------

def test_parse_overfull_boxes_all_phrasings(tmp_path):
    log = tmp_path / "main.log"
    log.write_text(
        "Overfull \\hbox (11.53pt too wide) detected at line 9\n"
        "Overfull \\hbox (40.9pt too wide) in paragraph at lines 37--39\n"
        "Overfull \\vbox (5.0pt too high) has occurred while \\output is active\n"
        "Overfull \\hbox (2.1pt too wide) in alignment at lines 61--61\n"
        "Underfull \\hbox (badness 3000) in paragraph at lines 1--2\n")
    boxes = vg.parse_overfull_boxes(log)
    assert len(boxes) == 4                       # 3 hbox + 1 vbox, no underfull
    assert boxes[0]["overflow_pt"] == 11.53 and boxes[0]["lines"] == [9, 9]
    assert boxes[1]["lines"] == [37, 39]
    assert all(b["kind"] == "overfull-visual" for b in boxes)


# --- retargeted vision scope: overfull is LOG-owned, excluded mechanically -----

def test_vision_scope_excludes_log_owned_overfull():
    # the judge is advertised only the geometry kinds the compile log cannot locate
    assert "overfull-visual" not in vg.VISION_JUDGE_KINDS
    assert "overfull-visual" in vg.VISUAL_FINDING_KINDS        # still a real kind
    assert vg.LOG_OWNED_KINDS == frozenset({"overfull-visual"})
    # the brief itself tells the judge overfull is out of scope (mechanical, not
    # advisory) while KEEPING the inverse acceptability seal
    assert "OUT of your scope" in vg.INSPECTOR_INSTRUCTION
    assert "Do NOT assume the layout is acceptable" in vg.INSPECTOR_INSTRUCTION


def test_parse_vision_verdict_drops_planted_overfull():
    # a planted log-locatable overfull finding is DROPPED (not coerced/re-injected);
    # a genuine geometry finding in the same reply survives — the scope exclusion.
    raw = ('[{"where":"p6","issue":"text past margin","fix":"reflow",'
           '"kind":"overfull-visual"},'
           '{"where":"p2","issue":"cols overlap","fix":"widen gutter",'
           '"kind":"column-collision"}]')
    assert [f["kind"] for f in vg.parse_vision_verdict(raw)] == ["column-collision"]
    # strict mode also drops the overfull and keeps the collision
    assert [f["kind"] for f in vg.parse_vision_verdict(raw, strict=True)] == ["column-collision"]


# --- the crop packer: a single-column figure is column-confined, never spanned --

def test_crop_x_extent_confines_single_column_figure():
    # fig:f5-dp-price geometry as a fixture (r2 PDF, page 20): a 612pt-wide page
    # whose float synctex-maps to the LEFT column [54, 299]. full_width spans the
    # page and drags in the right column of unrelated body text (the mis-pack); the
    # fix confines the crop to the float's own column.
    page_w = 612.0
    reg = vg.Region(page=20, x0=54.0, y0=52.1, x1=299.1, y1=270.4, label="fig:f5-dp-price")
    full = vg.crop_x_extent(page_w, reg, full_width=True, columns=2)
    conf = vg.crop_x_extent(page_w, reg, full_width=False, columns=2)
    assert full == (40.0, page_w - 40.0)                       # old: spans the page
    # the right column (2-col, margin 40, gutter 18) begins here:
    col_w = ((page_w - 80.0) - 18.0) / 2
    right_col_left = 40.0 + col_w + 18.0
    assert conf[1] < right_col_left                            # no drag-in
    assert conf[0] <= reg.x0 and conf[1] >= reg.x1             # covers the figure+caption
    assert conf[1] - conf[0] > 0                               # non-degenerate bbox
    assert (conf[1] - conf[0]) < (full[1] - full[0])           # narrower than the page span
    # a spanning float (figure*/table*) still gets the full page width
    assert vg.crop_x_extent(page_w, reg, full_width=True, columns=1) == (40.0, page_w - 40.0)


# --- label discovery (relative paths incl. figures_tex/) --------------------

@pytest.mark.skipif(not SSG.is_dir(), reason="SSG manuscript not present")
def test_discover_labels_finds_equations_and_figures():
    labels = vg.discover_labels(SSG)
    assert len(labels["equations"]) > 10        # ~90 numbered equations
    assert labels["figures"]                     # floats live under figures_tex/
    figs = {f["file"] for f in labels["figures"]}
    assert any(p.startswith("figures_tex/") for p in figs)  # subdir, relative
    for e in labels["equations"] + labels["figures"]:
        assert set(("label", "file", "line", "full_width")) <= set(e)


# --- denominator honesty: an unreadable fragment surfaces skipped_n ----------

def test_discover_labels_counts_examined_and_skipped(tmp_path):
    (tmp_path / "main.tex").write_text(
        r"\begin{equation}\label{eq:a} x=y \end{equation}" "\n", encoding="utf-8")
    # a `.tex` that is a directory raises IsADirectoryError (OSError) on read: the
    # per-fragment skip leg must be counted, not silently shrink the label set.
    os.mkdir(tmp_path / "frag.tex")
    scan: dict = {}
    labels = vg.discover_labels(tmp_path, scan=scan)
    assert scan["skipped_n"] >= 1                   # the unreadable fragment is visible
    assert scan["examined_n"] >= 1                  # main.tex still scanned
    assert any(e["label"] == "eq:a" for e in labels["equations"])  # skip kept, non-fatal


def test_discover_labels_clean_tree_reports_zero_skips(tmp_path):
    (tmp_path / "main.tex").write_text(
        r"\begin{figure}\label{fig:a}\end{figure}" "\n", encoding="utf-8")
    scan: dict = {}
    vg.discover_labels(tmp_path, scan=scan)
    assert scan["skipped_n"] == 0 and scan["examined_n"] == 1


# --- the render + crop pipeline (real SSG PDF) ------------------------------

@_render
def test_rasterise_and_crop_pipeline(tmp_path):
    try:
        pages = vg.rasterise_pdf(SSG_PDF, tmp_path / "pages", pages=[1, 2])
    except RuntimeError as e:                    # uv offline / wheel unavailable
        pytest.skip(f"rasteriser unavailable: {e}")
    assert len(pages) == 2
    for pr in pages:
        assert Path(pr.path).is_file() and Path(pr.path).stat().st_size > 0
        assert pr.width_px > 0 and pr.height_px > 0 and pr.scale > 0

    # contact sheet composites to a non-empty PNG
    cs = vg.contact_sheet(pages, tmp_path / "contact.png")
    assert Path(cs).stat().st_size > 0

    # a region crop yields a non-empty PNG
    reg = vg.Region(page=1, x0=100, y0=100, x1=300, y1=200)
    crop = vg.crop_region(pages[0], reg, tmp_path / "crop.png")
    assert Path(crop).stat().st_size > 0

    # the render-native pixel overfull detector was DELETED (log-owned axis)
    assert not hasattr(vg, "detect_margin_overflow")


@_render
@_synctex_data
@pytest.mark.skipif(not _HAVE_SYNCTEX, reason="needs the synctex binary")
def test_equation_region_maps_a_label(tmp_path):
    labels = vg.discover_labels(SSG)
    assert labels["equations"]
    lab = labels["equations"][0]["label"]
    reg = vg.equation_region(SSG_PDF, SSG, lab)
    assert reg is not None and reg.page >= 1 and reg.label == lab


@_render
@_synctex_data
def test_inspect_pdf_produces_all_mandatory_views_and_findings(tmp_path):
    try:
        insp = vg.inspect_pdf(SSG_PDF, SSG, tmp_path / "vg")
    except RuntimeError as e:
        pytest.skip(f"rasteriser unavailable: {e}")
    v = insp.views
    # the mandatory views are all present and non-empty
    assert Path(v["contact_sheet"]).stat().st_size > 0
    assert len(v["full_pages"]) == insp.n_pages > 0
    assert v["reading_crops"] and v["equation_crops"] and v["boundary_overlays"]
    for e in v["equation_crops"]:
        assert Path(e["path"]).stat().st_size > 0
    # figure+caption crops from figures_tex/ floats
    assert v["figure_crops"]
    assert Path(v["figure_crops"][0]["path"]).stat().st_size > 0
    # overfull is LOG-owned: the pixel detector was deleted, so no overfull crops
    # are cut (insp.overfull stays empty), but the log floor still counts boxes.
    assert insp.overfull == []
    assert v["overfull_log"]["count"] > 0

    # packaging for the vision judge — retargeted GEOMETRY scope: overfull excluded
    payload = vg.pack_for_vision_judge(insp)
    assert payload["owning_stage"] == "document"
    assert payload["finding_schema"] == ["where", "issue", "fix", "kind"]
    assert "overfull-visual" not in payload["allowed_kinds"]
    assert set(payload["allowed_kinds"]) == set(vg.VISION_JUDGE_KINDS)
    # no overfull crop is packed into the judge's images
    assert all(img["view"] != "overfull" for img in payload["images"])
    assert payload["images"]
    blocks = vg.to_content_blocks(payload)
    assert blocks[0]["type"] == "text"
    assert any(b.get("type") == "image" for b in blocks)
