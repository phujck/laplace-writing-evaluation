"""Leg A adversarial-judge probes — independent refutation attempts on A5 + A3.

A FRESH judge (did not build either bite) trying to BREAK the greens, banked as
tests. Every test here PASSES current code; a failing probe would be reported as a
finding, not committed.

A5 (scripts/workflow_economics.py) — the join's three hazards the fixture test did
not exercise:
  * double-count: a transcript carrying BOTH a terminal ``result`` (cumulative)
    AND ``assistant`` turns must use the result ONLY (never result + sum);
  * orphan transcript: an ``agent-<id>.jsonl`` with no journal record must be
    COUNTED (deliberate + visible), not silently dropped;
  * missing duration: no result, no timestamps → ``duration_ms`` is None and the
    rollup/render survive it (no crash);
  * reverse orphan: a journal record with no transcript is a zero-usage row.

A3 (visual_gate.crop_x_extent + the retargeted vision scope) — two crop edges the
builder's fixture did not name, plus the dual-path overfull drop:
  * a genuine full-width figure* still spans BOTH columns;
  * a single-column figure in the RIGHT column is confined to the right column
    (the gutter clamp must not break a non-left-column float);
  * a planted ``overfull-visual`` is dropped at BOTH the D2 parser and the R6
    reader path.

F1/F2 (the judge's latent residue, banked here as it is fixed) — two gaps the A3
bite left: the crop column count was ASSUMED (``inspect_pdf`` defaulted 2), which
clips a full-width figure on a single-column document; and the out-of-scope
overfull drop was invisible (a bare ``continue``). F1 detects the column count from
the manuscript's documentclass line; F2 counts the scope-drop on the returned
verdict. Both extend the probes above, keeping them green.
"""
import importlib.util
import json
from pathlib import Path

from laplace.pipeline import visual_gate as vg
from laplace.pipeline.readers import visual as rvisual

REPO_ROOT = Path(__file__).resolve().parents[1]
_ECON = REPO_ROOT / "scripts" / "workflow_economics.py"


def _load_econ():
    spec = importlib.util.spec_from_file_location("workflow_economics", _ECON)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _usage(inp, out, cc=0, cr=0):
    return {"input_tokens": inp, "output_tokens": out,
            "cache_creation_input_tokens": cc, "cache_read_input_tokens": cr}


# ---------------------------------------------------------------------------
# A5 — the join's untested hazards
# ---------------------------------------------------------------------------
def test_a5_prefers_result_over_assistant_sum_no_double_count(tmp_path):
    """BOTH a result-cumulative line AND assistant turns present: the row must
    reflect the RESULT usage only. Summing both would double-count (the whole
    point of preferring the cumulative terminal message)."""
    mod = _load_econ()
    d = tmp_path / "run"
    d.mkdir()
    _write_jsonl(d / "journal.jsonl",
                 [{"agent_id": "dbl", "label": "weld", "phase": "Weld", "model": "opus"}])
    # two assistant turns (1000/500 each -> sum would be 2000/1000) + a result that
    # says the cumulative truth is 1000/500.
    _write_jsonl(d / "agent-dbl.jsonl", [
        {"type": "assistant", "message": {"model": "opus", "usage": _usage(1000, 500)}},
        {"type": "assistant", "message": {"model": "opus", "usage": _usage(1000, 500)}},
        {"type": "result", "usage": _usage(1000, 500), "duration_ms": 5000, "num_turns": 2},
    ])
    agents = mod.collect_agents(d)
    assert len(agents) == 1
    a = agents[0]
    assert a["usage_source"] == "result"          # result preferred
    assert a["input_tokens"] == 1000              # NOT 2000 (no double-count)
    assert a["output_tokens"] == 500              # NOT 1000
    assert a["total_tokens"] == 1500


def test_a5_orphan_transcript_is_counted_and_visible(tmp_path):
    """A transcript with no journal record must be COUNTED (label=id, phase=''),
    never silently dropped."""
    mod = _load_econ()
    d = tmp_path / "run"
    d.mkdir()
    _write_jsonl(d / "journal.jsonl",
                 [{"agent_id": "known", "label": "weld", "phase": "Weld", "model": "opus"}])
    _write_jsonl(d / "agent-known.jsonl",
                 [{"type": "result", "usage": _usage(100, 50), "duration_ms": 1000}])
    # an orphan transcript: real usage, but NO journal entry names it.
    _write_jsonl(d / "agent-orphan.jsonl", [
        {"type": "assistant", "message": {"model": "haiku", "usage": _usage(700, 300)}},
    ])
    agents = mod.collect_agents(d)
    labels = {a["label"] for a in agents}
    assert "orphan" in labels                      # counted, not dropped
    orphan = next(a for a in agents if a["label"] == "orphan")
    assert orphan["phase"] == ""                    # deliberately unlabelled phase
    assert orphan["usage_source"] == "assistant-sum"
    assert orphan["total_tokens"] == 1000
    econ = mod.summarize(d, agents)
    assert econ["totals"]["agents"] == 2            # both known + orphan totalled
    assert econ["totals"]["total_tokens"] == 1000 + 150


def test_a5_journal_record_without_transcript_is_zero_row(tmp_path):
    """The reverse orphan: a journal record whose transcript is absent is a
    zero-usage row (usage_source='none'), still counted — never a crash."""
    mod = _load_econ()
    d = tmp_path / "run"
    d.mkdir()
    _write_jsonl(d / "journal.jsonl",
                 [{"agent_id": "ghost", "label": "g", "phase": "Build", "model": "opus"}])
    agents = mod.collect_agents(d)
    assert len(agents) == 1
    a = agents[0]
    assert a["usage_source"] == "none"
    assert a["total_tokens"] == 0
    assert a["label"] == "g" and a["phase"] == "Build"


def test_a5_missing_duration_is_graceful(tmp_path):
    """No result, no timestamps -> duration_ms is None; summarize + render must
    not crash on a None duration."""
    mod = _load_econ()
    d = tmp_path / "run"
    d.mkdir()
    _write_jsonl(d / "journal.jsonl",
                 [{"agent_id": "nodur", "label": "c", "phase": "Converge", "model": "haiku"}])
    _write_jsonl(d / "agent-nodur.jsonl", [
        {"type": "assistant", "message": {"model": "haiku", "usage": _usage(200, 100)}},
    ])
    agents = mod.collect_agents(d)
    a = agents[0]
    assert a["duration_ms"] is None                 # graceful, not 0-faked
    assert a["usage_source"] == "assistant-sum"
    econ = mod.summarize(d, agents)                 # must not raise on None duration
    assert econ["totals"]["duration_ms"] == 0       # None skipped in the rollup
    md = mod.render_markdown(econ)                   # must not raise
    assert "Converge" in md
    assert "—" in md                                # None duration renders as em-dash


# ---------------------------------------------------------------------------
# A3 — crop_x_extent column edges the builder's fixture did not name
# ---------------------------------------------------------------------------
def test_a3_full_width_figure_star_spans_both_columns():
    """A genuine full-width figure* (full_width=True) spans the whole text width —
    covering BOTH columns — regardless of the region's own narrow extent."""
    page_w = 612.0
    margin = 40.0
    gutter = 18.0
    # region sits in the left column, but the float is a figure* -> full_width True
    reg = vg.Region(page=3, x0=54.0, y0=100.0, x1=299.0, y1=300.0, label="fig:wide")
    x0, x1 = vg.crop_x_extent(page_w, reg, full_width=True, columns=2,
                              margin_pt=margin, gutter_pt=gutter)
    assert (x0, x1) == (margin, page_w - margin)
    # the span must cover the LEFT column's centre AND the RIGHT column's centre
    text_w = page_w - 2 * margin
    col_w = (text_w - gutter) / 2
    left_centre = margin + col_w / 2
    right_centre = margin + col_w + gutter + col_w / 2
    assert x0 < left_centre < x1
    assert x0 < right_centre < x1                    # genuinely spans both columns


def test_a3_right_column_figure_confined_not_broken():
    """A single-column figure in the RIGHT column of a 2-col page: the gutter clamp
    must confine it to the right column WITHOUT clipping the figure or leaking into
    the left column (the edge the builder tested only for the left column)."""
    page_w = 612.0
    margin = 40.0
    gutter = 18.0
    text_w = page_w - 2 * margin
    col_w = (text_w - gutter) / 2
    right_col_left = margin + col_w + gutter        # 315.0
    left_col_right = margin + col_w                 # 297.0
    # a figure occupying the right column
    reg = vg.Region(page=5, x0=right_col_left, y0=120.0,
                    x1=page_w - margin, y1=340.0, label="fig:right")
    x0, x1 = vg.crop_x_extent(page_w, reg, full_width=False, columns=2,
                              margin_pt=margin, gutter_pt=gutter)
    assert x0 < x1                                   # non-degenerate (not broken)
    assert x0 <= reg.x0 and x1 >= reg.x1             # the figure is fully captured
    assert x0 > left_col_right                        # excludes the left column
    # narrower than a full-page span
    assert (x1 - x0) < (page_w - 2 * margin)


# ---------------------------------------------------------------------------
# A3 — a planted overfull-visual is dropped at BOTH the D2 parser and R6
# ---------------------------------------------------------------------------
def test_a3_planted_overfull_dropped_at_both_paths():
    """A vision reply carrying an overfull-visual (a log-owned kind) is DROPPED —
    not coerced — at both visual_gate.parse_vision_verdict and the R6 reader
    (readers.visual.parse_geometry_verdict). Only the in-scope geometry finding
    survives."""
    raw = json.dumps([
        {"where": "p6", "issue": "text past margin", "fix": "reflow",
         "kind": "overfull-visual"},                # log-owned -> must drop
        {"where": "p7", "issue": "labels collide", "fix": "space out",
         "kind": "column-collision"},               # in-scope -> must survive
    ])
    assert "overfull-visual" in vg.LOG_OWNED_KINDS
    assert "overfull-visual" not in vg.VISION_JUDGE_KINDS

    v = vg.parse_vision_verdict(raw)
    assert all(f["kind"] != "overfull-visual" for f in v)
    assert any(f["kind"] == "column-collision" for f in v)

    r6 = rvisual.parse_geometry_verdict(raw)
    assert all(f["kind"] != "overfull-visual" for f in r6)
    assert any(f["kind"] == "column-collision" for f in r6)
    assert all(f.get("reader") == "R6" for f in r6)  # R6 stamp intact


# ---------------------------------------------------------------------------
# F1 — the column count is DETECTED from the manuscript, never assumed. A false
# 2 on a single-column document CLIPS a full-width figure to one column (the
# judge verified crop_x_extent(612, Region[40,572], full_width=False, columns=2)
# -> (34,314), losing ~258pt, vs columns=1 -> (34,578) intact).
# ---------------------------------------------------------------------------
def test_f1_detect_columns_documentclass_variants():
    """columns_from_source reads the \\documentclass line: article (and options
    without a column directive) is single-column; an explicit twocolumn option, or
    revtex's reprint mode, is two-column; onecolumn/preprint force single. The
    class default (bare article, revtex with no mode) is single-column."""
    cs = vg.columns_from_source
    # single column
    assert cs(r"\documentclass{article}") == 1
    assert cs(r"\documentclass[11pt]{article}") == 1
    assert cs(r"\documentclass[aps,prx]{revtex4-2}") == 1          # revtex default
    assert cs(r"\documentclass[preprint,aps]{revtex4-2}") == 1     # preprint mode
    assert cs(r"\documentclass[onecolumn,aps]{revtex4-2}") == 1    # explicit onecolumn
    # two column
    assert cs(r"\documentclass[twocolumn,10pt]{article}") == 2
    assert cs(r"\documentclass[reprint,aps,prx]{revtex4-2}") == 2  # reprint mode (SSG)
    assert cs(r"\documentclass[aps,twocolumn]{revtex4-2}") == 2
    # an explicit column option WINS over a revtex mode preset
    assert cs(r"\documentclass[reprint,onecolumn]{revtex4-2}") == 1
    # a body \twocolumn (no class-level signal) is trusted; \twocolumngrid is NOT a
    # mode switch (revtex span helper) and must not flip the count
    assert cs("\\documentclass{article}\n\\twocolumn[\\maketitle]") == 2
    assert cs("\\documentclass{article}\n\\twocolumngrid") == 1
    # a document that toggles BOTH is not trivially decidable -> class default
    assert cs("\\documentclass{article}\n\\twocolumn\n\\onecolumn") == 1


def test_f1_detect_columns_reads_the_manuscript_dir(tmp_path):
    """detect_columns resolves the main .tex under a manuscript directory (root-level
    main.tex preferred) and reads its \\documentclass — the path inspect_pdf already
    receives, so no call site must learn the column count."""
    (tmp_path / "main.tex").write_text(
        r"\documentclass[11pt]{article}" + "\n\\begin{document}x\\end{document}",
        encoding="utf-8")
    assert vg.detect_columns(tmp_path) == 1                        # a directory
    assert vg.detect_columns(tmp_path / "main.tex") == 1           # a file
    (tmp_path / "main.tex").write_text(
        r"\documentclass[reprint,aps]{revtex4-2}" + "\n\\begin{document}x\\end{document}",
        encoding="utf-8")
    assert vg.detect_columns(tmp_path) == 2
    # a directory with no \documentclass anywhere -> the safe single-column default
    empty = tmp_path / "empty"
    empty.mkdir()
    assert vg.detect_columns(empty) == 1


def test_f1_single_column_full_width_figure_not_clipped():
    """The fix, composed exactly as inspect_pdf does it: a single-column manuscript
    detects columns=1, so a full-width (but non-figure*) figure's crop keeps its
    whole extent instead of being clamped to one column. This is the ~258pt the
    assumed columns=2 lost."""
    page_w = 612.0
    # a plain figure spanning the text width; discover_labels records full_width=False
    reg = vg.Region(page=1, x0=40.0, y0=100.0, x1=572.0, y1=300.0, label="fig:wide")
    # the assumed-2 clip the judge verified (the bug):
    assert vg.crop_x_extent(page_w, reg, full_width=False, columns=2) == (34.0, 314.0)
    # detection on a single-column manuscript yields 1, and the crop is intact:
    cols = vg.columns_from_source(r"\documentclass{article}")
    assert cols == 1
    conf = vg.crop_x_extent(page_w, reg, full_width=False, columns=cols)
    assert conf == (34.0, 578.0)                                   # full figure kept
    assert conf[0] <= reg.x0 and conf[1] >= reg.x1                 # nothing clipped
    assert (conf[1] - conf[0]) > (314.0 - 34.0)                    # wider than the clamp


def test_f1_two_column_crop_stays_byte_identical_to_banked():
    """Two-column behaviour is unchanged: a revtex reprint detects columns=2, and the
    crop reproduces the judge's banked clamp (34,314) — his tests must still pass."""
    page_w = 612.0
    reg = vg.Region(page=1, x0=40.0, y0=100.0, x1=572.0, y1=300.0, label="fig:wide")
    cols = vg.columns_from_source(r"\documentclass[reprint,aps,prx]{revtex4-2}")
    assert cols == 2
    assert vg.crop_x_extent(page_w, reg, full_width=False, columns=cols) == (34.0, 314.0)


# ---------------------------------------------------------------------------
# F2 — the out-of-scope (log-owned) drop is COUNTED, not swallowed by a bare
# `continue`. The verdict is a list subclass carrying dropped_by_scope.
# ---------------------------------------------------------------------------
def test_f2_scope_drop_is_counted_and_visible_at_both_paths():
    """A planted overfull-visual is DROPPED (as before) AND the drop is now counted
    on the returned VisionVerdict (dropped_by_scope / dropped_kinds) at both the D2
    parser and the R6 reader path — the drop is no longer invisible. A clean parse
    reports zero drops."""
    raw = json.dumps([
        {"where": "p6", "issue": "text past margin", "fix": "reflow",
         "kind": "overfull-visual"},                 # log-owned -> dropped + counted
        {"where": "p6", "issue": "text past margin again", "fix": "reflow",
         "kind": "overfull-visual"},                 # a second drop -> count == 2
        {"where": "p7", "issue": "labels collide", "fix": "space out",
         "kind": "column-collision"},                # in-scope -> survives
    ])
    v = vg.parse_vision_verdict(raw)
    assert isinstance(v, vg.VisionVerdict)
    assert [f["kind"] for f in v] == ["column-collision"]         # findings unchanged
    assert v.dropped_by_scope == 2                                 # both drops counted
    assert v.dropped_kinds == {"overfull-visual": 2}              # broken down by kind

    # the count survives the R6 re-stamp (observability preserved end-to-end)
    r6 = rvisual.parse_geometry_verdict(raw)
    assert isinstance(r6, vg.VisionVerdict)
    assert r6.dropped_by_scope == 2 and r6.dropped_kinds == {"overfull-visual": 2}
    assert all(f["reader"] == "R6" for f in r6)

    # a clean, in-scope-only parse counts zero drops (no false positives)
    clean = vg.parse_vision_verdict(json.dumps(
        [{"where": "p1", "issue": "tiny tick", "fix": "enlarge", "kind": "tiny-label"}]))
    assert clean.dropped_by_scope == 0 and clean.dropped_kinds == {}
    # malformed input is still an empty verdict with a zero drop count, never a crash
    assert vg.parse_vision_verdict("not json") == []
    assert vg.parse_vision_verdict("not json").dropped_by_scope == 0
