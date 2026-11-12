"""The visual page gate — judge the manuscript as rendered pages (Phase D2).

A successful compile is not a successful manuscript. Every visual judgement to
date was a human reading PNGs by hand; this module is the organ that rasterises a
compiled PDF, cuts the mandatory views a typesetter's eye needs (contact sheet,
full pages, reading-size crops, equation crops, figure+caption crops, page/column
boundary overlays), and packages those crops for a multimodal vision judge whose
verdict parses back into the pipeline's standard finding shape
``{where, issue, fix, kind}`` — every visual kind routing to the ``document``
owning stage.

STANDALONE by design. This module does NOT import the convergence loop, the
schema, or the workflow, and it does NOT call a real vision model. It exposes the
crop-packaging + verdict-parsing so the convergence loop (Phase F) can drive the
actual multimodal read at candidate-lock. Wiring into ``evaluate_round`` and the
candidate-lock tier is Phase F's job.

The dependency decision (documented here so it is never re-derived):
  * ``pdftoppm`` / ``gs`` / PyMuPDF(``fitz``) are ABSENT on the target box, so the
    proven rasteriser is **pypdfium2** — a self-contained wheel. To avoid
    perturbing the main venv (pypdfium2 is not a pipeline dependency), rasterising
    runs in an ISOLATED ``uv run --with pypdfium2 --with pillow`` subprocess
    (``uv`` at /root/.local/bin/uv). The subprocess renders each page to a PNG and
    prints a JSON manifest; the parent process — which already has Pillow — does
    all crop/composite work in-process. Rasterisation is the only external hop.
  * Equation/figure regions come from **synctex** (the ``synctex`` binary that
    ships with the vendored TeX): a ``\\label`` is located in source, ``synctex
    view`` maps its (file, line) to a page + point/box in PDF points (top-left
    origin), and that region is cut from the full-page render. This reconstructs —
    does not copy — the geometry idea behind ``projection_viewer.synctex_locate``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# The visual finding-kinds manifest — every kind routes to `document`.
# ---------------------------------------------------------------------------
#
# Phase F wires these into the schema. To reach the ``document`` owning stage a
# feedback ``kind`` must resolve ``KIND_TO_WORK[kind] -> "render"`` and
# ``WORK_TO_LAYER["render"] -> "document"`` (the only work kind that lands on
# ``document``). So the wiring Phase F performs is, for every kind below:
#     schema.KIND_TO_WORK[kind] = "render"
# and nothing else — ``render -> document`` already exists. This module owns the
# vocabulary; the schema owns the routing table.
#
#: kind -> the human sense of the visual defect it names.
VISUAL_FINDING_KINDS: dict[str, str] = {
    "overfull-visual":     "text runs past the text block / into the margin as rendered",
    "crowded-page":        "a page is visually overloaded — too dense to read at reading size",
    "tiny-label":          "an axis label, tick, or annotation is too small to read on the page",
    "column-collision":    "content crosses the column gutter or two columns overlap",
    "equation-clip":       "a display equation is cut off, overflows its column, or is broken badly",
    "float-misplacement":  "a figure/table float lands far from its reference or breaks the reading flow",
}

#: The kinds the compile LOG locates on its own — TeX warns on these exactly, with
#: the pt overhang and source line, so the mechanical panel owns them and the
#: vision readers must NOT re-inspect them (retargeted scope, 2026-07-10).
LOG_OWNED_KINDS: frozenset[str] = frozenset({"overfull-visual"})

#: The vision judge's allowed kinds — every visual kind the LOG cannot locate. This
#: is the retargeted R6 GEOMETRY scope: collision / tiny-label / equation-clip /
#: float-misplacement / crowded (plus crop integrity), never overfull. Enforced
#: mechanically in ``pack_for_vision_judge`` (advertised kinds) and
#: ``parse_vision_verdict`` (log-owned kinds are dropped, not coerced).
VISION_JUDGE_KINDS: dict[str, str] = {
    k: v for k, v in VISUAL_FINDING_KINDS.items() if k not in LOG_OWNED_KINDS
}

#: The single work kind every visual finding maps to (Phase F: KIND_TO_WORK[k]).
VISUAL_WORK_KIND = "render"
#: The owning stage every visual finding routes to (WORK_TO_LAYER["render"]).
VISUAL_OWNING_STAGE = "document"


def route(kind: str) -> str:
    """The owning stage for a visual finding kind (always ``document``).

    Mirrors — but does not import — the schema routing so this module stays
    standalone; the manifest below is what Phase F must reflect into the schema.
    """
    if kind not in VISUAL_FINDING_KINDS:
        raise KeyError(f"unknown visual finding kind {kind!r}; "
                       f"known: {sorted(VISUAL_FINDING_KINDS)}")
    return VISUAL_OWNING_STAGE


def routing_manifest() -> list[dict[str, str]]:
    """The Phase-F wiring manifest: one row per visual kind, fully routed."""
    return [
        {"kind": k, "work_kind": VISUAL_WORK_KIND,
         "owning_stage": VISUAL_OWNING_STAGE, "sense": sense}
        for k, sense in VISUAL_FINDING_KINDS.items()
    ]


# ---------------------------------------------------------------------------
# Small value types
# ---------------------------------------------------------------------------

DEFAULT_DPI = 150
# env → PATH → the remote container's install path (honoured last, so a checkout
# on any box resolves its own uv before inheriting the container default).
DEFAULT_UV = (os.environ.get("LAPLACE_UV_BIN") or shutil.which("uv")
              or "/root/.local/bin/uv")
_RENDER_TIMEOUT = 600
_SYNCTEX_TIMEOUT = 30


@dataclass
class PageRender:
    """One rasterised page: the PNG plus the geometry to map PDF points to px."""
    index: int          # 1-based page number
    path: str           # absolute path to the full-page PNG
    width_px: int
    height_px: int
    page_w_pt: float
    page_h_pt: float
    dpi: float
    scale: float        # px per pt (dpi / 72)

    def pt_to_px(self, x_pt: float, y_pt: float) -> tuple[float, float]:
        """(x, y) in PDF points, top-left origin -> pixel in the rendered page."""
        return x_pt * self.scale, y_pt * self.scale


@dataclass
class Region:
    """A rectangle on one page in PDF points, top-left origin."""
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    label: str = ""     # the \label it came from, when applicable


@dataclass
class Inspection:
    """The packaged output of one visual-gate pass over a PDF."""
    pdf: str
    n_pages: int
    dpi: float
    out_dir: str
    views: dict[str, Any] = field(default_factory=dict)
    overfull: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# 1. Rasterise — the isolated pypdfium2 subprocess
# ---------------------------------------------------------------------------

# Rendered in an ephemeral `uv run --with pypdfium2 --with pillow` env, so it may
# only import pypdfium2 + Pillow + stdlib. Prints a JSON manifest on stdout.
_RENDER_SCRIPT = r'''
import sys, json
import pypdfium2 as pdfium
pdf_path, out_dir, dpi = sys.argv[1], sys.argv[2], float(sys.argv[3])
pages_arg = sys.argv[4] if len(sys.argv) > 4 else ""
scale = dpi / 72.0
doc = pdfium.PdfDocument(pdf_path)
n = len(doc)
if pages_arg:
    want = [int(x) - 1 for x in pages_arg.split(",") if x.strip()]
else:
    want = list(range(n))
out = []
for i in want:
    if i < 0 or i >= n:
        continue
    page = doc[i]
    mb = page.get_mediabox()            # (x0, y0, x1, y1) in pt
    bmp = page.render(scale=scale)
    pil = bmp.to_pil()
    p = "%s/page-%03d.png" % (out_dir, i + 1)
    pil.save(p)
    out.append({"index": i + 1, "path": p,
                "width_px": pil.width, "height_px": pil.height,
                "page_w_pt": float(mb[2] - mb[0]), "page_h_pt": float(mb[3] - mb[1]),
                "dpi": dpi, "scale": scale})
    page.close()
print(json.dumps({"n_pages": n, "pages": out}))
'''


def rasterise_pdf(pdf_path: str | Path, out_dir: str | Path,
                  dpi: float = DEFAULT_DPI, pages: Optional[list[int]] = None,
                  uv_bin: str = DEFAULT_UV, timeout: int = _RENDER_TIMEOUT) -> list[PageRender]:
    """Render a compiled PDF to per-page PNGs via an isolated pypdfium2 subprocess.

    ``pages`` is an optional 1-based whitelist (default: all). Returns one
    ``PageRender`` per rendered page, in page order. Raises ``RuntimeError`` if
    the subprocess fails (so a broken rasteriser is a loud signal, never a silent
    empty view — the banked "silence never reads as pass" lesson).
    """
    pdf_path = Path(pdf_path).resolve()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not pdf_path.is_file():
        raise RuntimeError(f"no PDF at {pdf_path}")
    if not shutil.which(uv_bin) and not Path(uv_bin).is_file():
        raise RuntimeError(f"uv not found at {uv_bin!r}; set LAPLACE_UV_BIN")
    pages_arg = ",".join(str(p) for p in pages) if pages else ""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tf:
        tf.write(_RENDER_SCRIPT)
        script = tf.name
    try:
        proc = subprocess.run(
            [uv_bin, "run", "--no-project", "--with", "pypdfium2", "--with", "pillow",
             "python", script, str(pdf_path), str(out_dir), str(dpi), pages_arg],
            capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    finally:
        try:
            os.unlink(script)
        except OSError:
            pass
    if proc.returncode != 0:
        raise RuntimeError(f"rasterise failed (rc={proc.returncode}): "
                           f"{(proc.stderr or proc.stdout)[-800:]}")
    line = (proc.stdout or "").strip().splitlines()
    if not line:
        raise RuntimeError(f"rasterise produced no manifest: {proc.stderr[-800:]}")
    manifest = json.loads(line[-1])
    return [PageRender(**pg) for pg in manifest["pages"]]


# ---------------------------------------------------------------------------
# 2. Synctex — a \label -> page region
# ---------------------------------------------------------------------------

_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
# environments whose immediately-preceding/enclosing \label names a display eq.
_EQ_ENVS = ("equation", "align", "gather", "multline", "eqnarray", "flalign")
_EQ_BEGIN_RE = re.compile(
    r"\\begin\{(" + "|".join(_EQ_ENVS) + r")\*?\}")
_FIG_BEGIN_RE = re.compile(r"\\begin\{(figure|figure\*|table|table\*)\}")


def _tex_files(tex_root: Path) -> list[tuple[Path, str]]:
    """Every .tex under the manuscript root, paired with the path RELATIVE to the
    root in the spelling tex/synctex recorded it (e.g. ``figures_tex/fig_nf6.tex``
    — floats live in subdirs and are ``\\input``'d, so a flat glob misses them)."""
    if not tex_root.is_dir():
        return [(tex_root, tex_root.name)]
    out = []
    for f in sorted(tex_root.rglob("*.tex")):
        rel = f.relative_to(tex_root).as_posix()
        out.append((f, rel))
    return out


def discover_labels(tex_root: str | Path,
                    scan: Optional[dict[str, Any]] = None
                    ) -> dict[str, list[dict[str, Any]]]:
    """Scan the manuscript's .tex fragments (recursively, incl. ``figures_tex/``,
    ``tables_tex/``) and group every ``\\label`` by the environment it sits in:
    equations, figures, tables, and other (theorem-like / sectioning). Each entry
    is ``{label, file, line, full_width}`` (``file`` relative to the root, 1-based
    line, ``full_width`` set for ``figure*``/``table*``). This lets the gate
    auto-pick equation and figure labels without the caller knowing the
    manuscript's internal id scheme (the semantic prefixes are node ids, not a
    fixed ``eq:`` convention — his rule).

    ``scan``, if passed, is filled with ``examined_n``/``skipped_n`` — a fragment
    that cannot be read (OSError) is counted, not swallowed, so an unreadable
    ``.tex`` cannot silently shrink the discovered label set into a false clean."""
    out: dict[str, list[dict[str, Any]]] = {
        "equations": [], "figures": [], "tables": [], "other": []}
    examined_n = skipped_n = 0
    for f, rel in _tex_files(Path(tex_root)):
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            skipped_n += 1                         # a fragment lost -> its labels too
            continue
        examined_n += 1
        env_stack: list[str] = []
        for i, ln in enumerate(lines, start=1):
            for m in re.finditer(r"\\begin\{([a-zA-Z*]+)\}", ln):
                env_stack.append(m.group(1))
            for lm in _LABEL_RE.finditer(ln):
                label = lm.group(1)
                # bucket by nearest enclosing / same-line environment
                same_line_eq = bool(_EQ_BEGIN_RE.search(ln))
                same_line_fig = bool(_FIG_BEGIN_RE.search(ln))
                in_eq = same_line_eq or any(
                    e.rstrip("*") in _EQ_ENVS for e in env_stack)
                in_fig = same_line_fig or any(
                    e.rstrip("*") == "figure" for e in env_stack)
                in_tab = any(e.rstrip("*") == "table" for e in env_stack)
                full_width = any(e.endswith("*") for e in env_stack)
                rec = {"label": label, "file": rel, "line": i,
                       "full_width": full_width}
                if in_fig:
                    out["figures"].append(rec)
                elif in_tab:
                    out["tables"].append(rec)
                elif in_eq:
                    out["equations"].append(rec)
                else:
                    out["other"].append(rec)
            for m in re.finditer(r"\\end\{([a-zA-Z*]+)\}", ln):
                if env_stack and env_stack[-1] == m.group(1):
                    env_stack.pop()
    if scan is not None:
        scan.update(examined_n=examined_n, skipped_n=skipped_n)
    return out


# ---------------------------------------------------------------------------
# 2b. Column count — DETECTED from the manuscript, never assumed (F1)
# ---------------------------------------------------------------------------
#
# The crop geometry (``crop_x_extent``) confines a single-column float to its own
# column on a multi-column page. That confinement is CORRECT for a 2-column
# manuscript but CLIPS a full-width figure on a SINGLE-column one: a plain
# ``figure`` (no ``*``) is full_width=False, so on a 1-column page an assumed
# ``columns=2`` clamps its crop to the left half and loses ~258pt of the figure.
# ``inspect_pdf`` used to default ``columns=2`` unconditionally; it now DETECTS the
# count from the manuscript's own ``\documentclass`` line so the geometry matches
# the page it is cutting.

_DOCUMENTCLASS_RE = re.compile(r"\\documentclass\s*(?:\[([^\]]*)\])?\s*\{([^}]+)\}")
#: \onecolumn / \twocolumn as BODY COMMANDS (backslash form); the negative
#: lookahead excludes revtex's \onecolumngrid / \twocolumngrid span helpers, and
#: the \documentclass option is the bare word (no backslash) so it never matches.
_COL_CMD_RE = re.compile(r"\\(one|two)column(?![A-Za-z])")


def _find_main_tex_text(tex_root: Path) -> str:
    """The text of the manuscript's main .tex — the fragment carrying
    ``\\documentclass``. Prefers a root-level ``main.tex``, else the first fragment
    that declares a class. Empty string when none is found (detection then falls to
    its single-column default)."""
    tex_root = Path(tex_root)
    if tex_root.is_file():
        try:
            return tex_root.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    files: list[tuple[Path, str]] = []
    root_main = tex_root / "main.tex"
    if root_main.is_file():
        files.append((root_main, "main.tex"))
    files += _tex_files(tex_root)
    for f, _rel in files:
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "\\documentclass" in txt:
            return txt
    return ""


def columns_from_source(text: str) -> int:
    """Column count (1 or 2) implied by a manuscript's ``\\documentclass`` line and
    any unambiguous body ``\\onecolumn``/``\\twocolumn`` switch — pure text, no I/O.

    Option priority: an explicit ``twocolumn``/``onecolumn`` class option wins, then
    a revtex mode preset (``reprint`` → 2, ``preprint`` → 1). With NO class-level
    column signal, an unambiguous body switch decides (all ``\\twocolumn`` → 2, all
    ``\\onecolumn`` → 1); a document that toggles BOTH is not trivially decidable, so
    it falls to the class default. Otherwise the class default (article / revtex
    preprint) is single-column."""
    explicit: Optional[int] = None
    m = _DOCUMENTCLASS_RE.search(text)
    if m:
        opts = {t.strip().lower() for t in (m.group(1) or "").split(",")}
        if "twocolumn" in opts:
            explicit = 2
        elif "onecolumn" in opts:
            explicit = 1
        elif "reprint" in opts:      # revtex reprint mode ships two columns
            explicit = 2
        elif "preprint" in opts:     # revtex preprint mode is single column
            explicit = 1
    if explicit is not None:
        return explicit
    switches = set(_COL_CMD_RE.findall(text))
    if switches == {"two"}:
        return 2
    if switches == {"one"}:
        return 1
    return 1


def detect_columns(tex_root: str | Path) -> int:
    """Detect the manuscript's column count (1 or 2) from its OWN source (F1), so
    the crop geometry is never ASSUMED. Reads the ``\\documentclass`` options via
    :func:`columns_from_source`. Defaults to single-column when nothing signals two
    columns — the safe default, since a false 2 CLIPS a full-width figure to one
    column (content lost) while a false 1 merely over-widens a single-column crop."""
    return columns_from_source(_find_main_tex_text(Path(tex_root)))


def label_source_location(tex_root: str | Path, label: str) -> Optional[tuple[str, int]]:
    """Find ``\\label{<label>}`` in the manuscript's .tex fragments (recursively)
    -> (file relative to root, 1-based line)."""
    for f, rel in _tex_files(Path(tex_root)):
        try:
            for i, ln in enumerate(f.read_text(encoding="utf-8", errors="replace")
                                   .splitlines(), start=1):
                for m in _LABEL_RE.finditer(ln):
                    if m.group(1) == label:
                        return rel, i
        except OSError:
            continue
    return None


def _synctex_records(pdf_path: Path, source_file: str, line: int,
                     timeout: int = _SYNCTEX_TIMEOUT,
                     synctex_bin: str = "synctex") -> list[dict[str, float]]:
    """Run ``synctex view`` for (source_file, line) against the PDF, parsing every
    box record. Tries the input-name spellings tex may have recorded (bare, ./)."""
    source_path = Path(source_file)
    absolute = (
        source_path
        if source_path.is_absolute()
        else (pdf_path.parent / source_path).resolve()
    )
    for name in (
        source_file,
        f"./{source_file}",
        Path(source_file).name,
        str(absolute),
    ):
        try:
            proc = subprocess.run(
                [synctex_bin, "view", "-i", f"{int(line)}:0:{name}", "-o", pdf_path.name],
                cwd=str(pdf_path.parent), capture_output=True,
                encoding="utf-8", errors="replace", timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            continue
        recs: list[dict[str, float]] = []
        cur: dict[str, float] = {}
        for raw in (proc.stdout or "").splitlines():
            s = raw.strip()
            if s.startswith("Page:"):
                if cur:
                    recs.append(cur)
                cur = {}
                try:
                    cur["page"] = float(s[5:].strip())
                except ValueError:
                    cur = {}
            else:
                for key in ("x", "y", "h", "v", "W", "H"):
                    if s.startswith(key + ":"):
                        try:
                            cur[key] = float(s[len(key) + 1:].strip())
                        except ValueError:
                            pass
                        break
        if cur:
            recs.append(cur)
        recs = [r for r in recs if "page" in r]
        if recs:
            return recs
    return []


def synctex_region(pdf_path: str | Path, source_file: str, line: int,
                   label: str = "", timeout: int = _SYNCTEX_TIMEOUT,
                   synctex_bin: str = "synctex") -> Optional[Region]:
    """Map a source (file, line) to a page region (union of synctex boxes), in PDF
    points, top-left origin. Returns ``None`` if synctex can't place it (a stale or
    missing ``main.synctex.gz`` — the caller treats that as a declared gap, not a
    pass). Boxes can be zero-width (an equation-number anchor); callers widen."""
    pdf_path = Path(pdf_path)
    recs = _synctex_records(pdf_path, source_file, line, timeout, synctex_bin)
    if not recs:
        return None
    page = int(recs[0]["page"])
    recs = [r for r in recs if int(r["page"]) == page]
    xs0, ys0, xs1, ys1 = [], [], [], []
    for r in recs:
        left = r.get("h", r.get("x", 0.0))
        top = r.get("v", r.get("y", 0.0))
        w = r.get("W", 0.0)
        h = r.get("H", 0.0)
        xs0.append(left)
        xs1.append(left + w)
        # synctex v is the box baseline/reference; H rises above it
        ys0.append(top - h)
        ys1.append(top)
    return Region(page=page, x0=min(xs0), y0=min(ys0), x1=max(xs1), y1=max(ys1),
                  label=label)


def equation_region(pdf_path: str | Path, tex_root: str | Path, label: str,
                    timeout: int = _SYNCTEX_TIMEOUT,
                    synctex_bin: str = "synctex") -> Optional[Region]:
    """The page region for a display-equation ``\\label`` (via source -> synctex).

    Equations are not floats, so the label's galley position is its rendered
    position — the direct mapping is exact."""
    loc = label_source_location(tex_root, label)
    if not loc:
        return None
    return synctex_region(
        pdf_path, loc[0], loc[1], label=label, timeout=timeout,
        synctex_bin=synctex_bin)


_FIG_ENV_BEGIN_RE = re.compile(r"\\begin\{(figure|table)\*?\}")


def figure_region(pdf_path: str | Path, tex_root: str | Path, label: str,
                  timeout: int = _SYNCTEX_TIMEOUT,
                  synctex_bin: str = "synctex") -> Optional[Region]:
    """The page region for a figure/table ``\\label``, anchored on the float's
    ``\\begin{figure}`` line rather than the label.

    A float DETACHES from its source position: ``synctex`` maps the ``\\label``
    (which sits after the caption) to the galley flow — empirically one page
    before where the float actually ships out — while the ``\\begin`` line is
    recorded on the shipout page. Anchoring on ``\\begin`` gives the page the
    reader sees the figure on. (Verified on SSG: label→galley page, begin→the
    coloured-graphic page.)"""
    loc = label_source_location(tex_root, label)
    if not loc:
        return None
    rel, label_line = loc
    src = Path(tex_root) / rel if Path(tex_root).is_dir() else Path(tex_root)
    begin_line = label_line
    try:
        lines = src.read_text(encoding="utf-8", errors="replace").splitlines()
        for i in range(min(label_line, len(lines)) - 1, -1, -1):
            if _FIG_ENV_BEGIN_RE.search(lines[i]):
                begin_line = i + 1
                break
    except OSError:
        pass
    return synctex_region(
        pdf_path, rel, begin_line, label=label, timeout=timeout,
        synctex_bin=synctex_bin)


# ---------------------------------------------------------------------------
# 3. The mandatory views (Pillow, in-process)
# ---------------------------------------------------------------------------

def _pil():
    from PIL import Image, ImageDraw  # noqa: F401  (imported here so the module
    return Image, ImageDraw           # imports even where Pillow is absent)


def _clamp_box(box: tuple[float, float, float, float],
               w: int, h: int) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    x0 = max(0, min(int(x0), w))
    y0 = max(0, min(int(y0), h))
    x1 = max(0, min(int(x1), w))
    y1 = max(0, min(int(y1), h))
    if x1 <= x0:
        x1 = min(w, x0 + 1)
    if y1 <= y0:
        y1 = min(h, y0 + 1)
    return x0, y0, x1, y1


def contact_sheet(pages: list[PageRender], out_path: str | Path,
                  cols: int = 4, thumb_w: int = 320, pad: int = 8,
                  bg: tuple[int, int, int] = (250, 250, 250)) -> str:
    """A single overview image: every page thumbnailed on a grid. The first view a
    judge (or a human) scans for gross layout faults — blank pages, runaway floats,
    density outliers — before drilling into crops."""
    Image, ImageDraw = _pil()
    if not pages:
        raise RuntimeError("contact_sheet: no pages")
    thumbs = []
    for pr in pages:
        im = Image.open(pr.path).convert("RGB")
        ratio = thumb_w / im.width
        th = im.resize((thumb_w, max(1, int(im.height * ratio))))
        thumbs.append(th)
    thumb_h = max(t.height for t in thumbs)
    rows = (len(thumbs) + cols - 1) // cols
    W = cols * thumb_w + (cols + 1) * pad
    H = rows * thumb_h + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(sheet)
    for idx, th in enumerate(thumbs):
        r, c = divmod(idx, cols)
        x = pad + c * (thumb_w + pad)
        y = pad + r * (thumb_h + pad)
        sheet.paste(th, (x, y))
        draw.rectangle([x, y, x + thumb_w - 1, y + th.height - 1], outline=(200, 200, 200))
        draw.text((x + 3, y + 3), f"p{pages[idx].index}", fill=(120, 120, 120))
    out_path = Path(out_path)
    sheet.save(out_path)
    return str(out_path)


def crop_x_extent(page_w_pt: float, region: Region, full_width: bool,
                  columns: int = 1, margin_pt: float = 40.0,
                  gutter_pt: float = 18.0, pad_pt: float = 6.0) -> tuple[float, float]:
    """The horizontal (x0, x1) extent of a crop, in PDF points — pure geometry, no
    image. Three modes:

      * ``full_width`` — the page text width (margin..page_w-margin). The right
        choice for a spanning float (``figure*``/``table*``) and for a display
        equation, whose synctex anchor is a thin rule at the equation number.
      * single-column float on a multi-column page (``columns >= 2``, not
        full-width) — CONFINE to the column the region sits in, so a one-column
        figure's crop never spills into the adjacent column. This is the
        near-full-page mis-pack fix: forcing full width on a one-column figure
        dragged the whole neighbouring column of unrelated body text into the crop
        (observed on ``fig:f5-dp-price``). The column is unioned with the region's
        own extent (a caption set to the full ``\\columnwidth`` is wider than a
        narrow graphic) but hard-clamped to stop BEFORE the next column begins.
      * otherwise — the region's own extent, padded (the D2 default).
    """
    if full_width:
        return margin_pt, page_w_pt - margin_pt
    if columns and columns >= 2:
        text_w = page_w_pt - 2 * margin_pt
        col_w = (text_w - (columns - 1) * gutter_pt) / columns
        stride = col_w + gutter_pt
        cx = (region.x0 + region.x1) / 2.0
        k = int((cx - margin_pt) // stride) if stride > 0 else 0
        k = max(0, min(columns - 1, k))
        left = margin_pt + k * stride
        right = left + col_w
        x0 = min(left, region.x0) - pad_pt
        x1 = max(right, region.x1) + pad_pt
        # never cross the gutter into a neighbouring column
        if k < columns - 1:
            x0_next = margin_pt + (k + 1) * stride
            x1 = min(x1, x0_next - 1.0)
        if k > 0:
            x1_prev = margin_pt + (k - 1) * stride + col_w
            x0 = max(x0, x1_prev + 1.0)
        return x0, x1
    return region.x0 - pad_pt, region.x1 + pad_pt


def crop_region(page: PageRender, region: Region, out_path: str | Path,
                pad_pt: float = 6.0,
                pad_up_pt: Optional[float] = None,
                pad_down_pt: Optional[float] = None,
                full_width: bool = False,
                margin_pt: float = 40.0,
                columns: int = 1,
                gutter_pt: float = 18.0) -> str:
    """Cut a region (PDF points, top-left origin) from a rendered page, with
    padding. ``full_width`` widens the crop to the page's text width (minus
    ``margin_pt``) — the right choice for display equations, whose synctex anchor
    is a thin vertical rule at the equation number. For a single-column float on a
    multi-column page pass ``columns >= 2`` (and leave ``full_width`` False): the
    crop is CONFINED to the float's own column instead of spanning the page, so it
    never drags in the adjacent column (see :func:`crop_x_extent`)."""
    Image, _ = _pil()
    im = Image.open(page.path).convert("RGB")
    up = pad_pt if pad_up_pt is None else pad_up_pt
    down = pad_pt if pad_down_pt is None else pad_down_pt
    x0_pt, x1_pt = crop_x_extent(page.page_w_pt, region, full_width,
                                 columns=columns, margin_pt=margin_pt,
                                 gutter_pt=gutter_pt, pad_pt=pad_pt)
    y0_pt, y1_pt = region.y0 - up, region.y1 + down
    box = (x0_pt * page.scale, y0_pt * page.scale,
           x1_pt * page.scale, y1_pt * page.scale)
    box = _clamp_box(box, im.width, im.height)
    im.crop(box).save(out_path)
    return str(out_path)


def reading_crops(page: PageRender, out_dir: str | Path,
                  tile_pt: tuple[float, float] = (612.0, 396.0),
                  overlap_pt: float = 36.0) -> list[str]:
    """100%-reading-size crops: cut the page into overlapping tiles at render dpi so
    a judge reads text at the size a human sees on paper (the contact sheet
    shrinks everything; density/legibility defects only show at 1:1)."""
    Image, _ = _pil()
    im = Image.open(page.path).convert("RGB")
    tw, th = tile_pt[0] * page.scale, tile_pt[1] * page.scale
    step = th - overlap_pt * page.scale
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    y = 0.0
    n = 0
    while y < im.height:
        box = _clamp_box((0, y, min(im.width, tw), y + th), im.width, im.height)
        p = out_dir / f"read-p{page.index:03d}-{n:02d}.png"
        im.crop(box).save(p)
        paths.append(str(p))
        n += 1
        if y + th >= im.height:
            break
        y += max(1.0, step)
    return paths


def boundary_overlay(page: PageRender, out_path: str | Path,
                     margin_pt: float = 72.0, columns: int = 2,
                     gutter_pt: float = 18.0,
                     colour: tuple[int, int, int] = (220, 40, 40)) -> str:
    """Draw the page text-block boundary and column gutter over the render. Any
    glyph crossing the right margin line (an overfull \\hbox) or the gutter (a
    column collision) is then visible to the eye — this is what makes the 37
    overfull boxes SHOW rather than merely count in the log."""
    Image, ImageDraw = _pil()
    im = Image.open(page.path).convert("RGB")
    draw = ImageDraw.Draw(im)
    s = page.scale
    left = margin_pt * s
    right = (page.page_w_pt - margin_pt) * s
    top = margin_pt * s
    bot = (page.page_h_pt - margin_pt) * s
    draw.rectangle([left, top, right, bot], outline=colour, width=2)
    if columns >= 2:
        text_w = (page.page_w_pt - 2 * margin_pt)
        col_w = (text_w - (columns - 1) * gutter_pt) / columns
        x = margin_pt
        for _ in range(columns - 1):
            x += col_w
            g0 = x * s
            g1 = (x + gutter_pt) * s
            draw.rectangle([g0, top, g1, bot], outline=(40, 120, 220), width=1)
            x += gutter_pt
    im.save(out_path)
    return str(out_path)


# ---------------------------------------------------------------------------
# 4. Overfull boxes from the compile log (seed + confirm the geometry defects)
# ---------------------------------------------------------------------------

_OVERFULL_RE = re.compile(
    r"Overfull \\([hv])box \(([\d.]+)pt too (?:wide|high)\)"
    r"(?:.*?(?:in paragraph at lines (\d+)--(\d+)"
    r"|in alignment at lines (\d+)--(\d+)|detected at line (\d+)))?")


def parse_overfull_boxes(log_path: str | Path) -> list[dict[str, Any]]:
    """Parse ``main.log`` for Overfull \\hbox/\\vbox warnings — the deterministic
    LOG floor (exact count + overflow magnitude + source line). Returns records
    ``{box, overflow_pt, lines}``. Source-file/page attribution from the log is
    deliberately NOT attempted here: TeX's paren file-stack is too noisy to trust
    for a routed finding. This LOG floor is the sole overfull owner: gated by the
    ``mech.overfull_floor_pt`` dial in the mechanical panel it locates every real
    box exactly (pt overhang + source line), so no render-native pixel detector is
    needed (the one that existed was deleted — 22/22 of its candidates non-defects)."""
    log_path = Path(log_path)
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        if "Overfull \\" not in line:
            continue
        m = _OVERFULL_RE.search(line)
        if not m:
            continue
        la = m.group(3) or m.group(5) or m.group(7)
        lb = m.group(4) or m.group(6) or m.group(7)
        out.append({
            "kind": "overfull-visual",
            "box": m.group(1),
            "overflow_pt": float(m.group(2)),
            "lines": [int(la), int(lb)] if la else None,
        })
    return out


# ---------------------------------------------------------------------------
# 4b. Overfull is LOG-owned, not pixel-detected (2026-07-10 ruling).
# ---------------------------------------------------------------------------
#
# The render-native overflow detector (``detect_margin_overflow``) was DELETED.
# At candidate-lock the R6 vision reader inspected its 22 render-detected overflow
# candidates and every one was a non-defect (antialiased column edges, sub-visible
# ink), while the compile-log floor behaved: TeX's ``Overfull \hbox`` warnings
# locate every real box exactly, with its pt overhang, for free. So the overfull
# axis is owned by the LOG floor alone — :func:`parse_overfull_boxes` gated by the
# ``mech.overfull_floor_pt`` dial in the mechanical panel, every round — and the
# vision readers no longer re-inspect log-locatable overflow (retargeted scope:
# collision / tiny-label / equation-clip / float-misplacement / crowded, plus crop
# integrity — the geometry defects the log CANNOT locate). Deleting the pixel
# detector removes a 100%-false-positive source rather than demoting noise.


# ---------------------------------------------------------------------------
# 5. The full inspection — orchestrate the mandatory views
# ---------------------------------------------------------------------------

def inspect_pdf(pdf_path: str | Path, tex_root: str | Path, out_dir: str | Path,
                dpi: float = DEFAULT_DPI,
                eq_labels: Optional[list[str]] = None,
                fig_labels: Optional[list[str]] = None,
                max_eq: int = 6, max_fig: int = 4,
                reading_pages: Optional[list[int]] = None,
                overlay_pages: Optional[list[int]] = None,
                log_path: Optional[str | Path] = None,
                columns: Optional[int] = None, uv_bin: str = DEFAULT_UV) -> Inspection:
    """Run the whole gate over a compiled PDF and cut the mandatory views into
    ``out_dir``: a contact sheet, full-page renders, 100% reading crops (of a few
    pages by default — all if ``reading_pages`` given), equation crops (from
    ``\\label``s auto-discovered when ``eq_labels`` is None), figure+caption crops,
    and page/column boundary overlays. Returns an ``Inspection`` whose ``views``
    dict names every produced image. Nothing here judges — the judge runs on the
    packaged crops (``pack_for_vision_judge``).

    ``columns`` defaults to ``None`` = DETECT from the manuscript's ``\\documentclass``
    line (F1): a bare hardcoded 2 clipped a full-width figure to one column on a
    single-column document. Pass an explicit 1/2 only to override detection."""
    pdf_path = Path(pdf_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # F1: the column count is DETECTED from the manuscript, never assumed. The crop
    # geometry must match the page it is cutting, or a single-column full-width
    # figure gets clamped to one column (~258pt lost).
    if columns is None:
        columns = detect_columns(tex_root)

    renders = rasterise_pdf(pdf_path, out_dir / "pages", dpi=dpi, uv_bin=uv_bin)
    by_page = {pr.index: pr for pr in renders}
    insp = Inspection(pdf=str(pdf_path), n_pages=len(renders), dpi=dpi,
                      out_dir=str(out_dir))

    # contact sheet + full-page list
    insp.views["contact_sheet"] = contact_sheet(renders, out_dir / "contact_sheet.png")
    insp.views["full_pages"] = [pr.path for pr in renders]

    # reading crops — default: first, middle, last page (cheap, representative)
    if reading_pages is None:
        picks = sorted({1, (len(renders) + 1) // 2, len(renders)})
        reading_pages = [p for p in picks if p in by_page]
    rc: list[str] = []
    for p in reading_pages:
        if p in by_page:
            rc += reading_crops(by_page[p], out_dir / "reading")
    insp.views["reading_crops"] = rc

    # equation crops
    label_scan: dict[str, Any] = {}
    labels = discover_labels(tex_root, scan=label_scan)
    if eq_labels is None:
        eq_labels = [e["label"] for e in labels["equations"]][:max_eq]
    eq_out: list[dict[str, Any]] = []
    eq_skipped = 0
    (out_dir / "equations").mkdir(exist_ok=True)
    for lab in eq_labels:
        reg = equation_region(pdf_path, tex_root, lab)
        if reg and reg.page in by_page:
            p = out_dir / "equations" / f"eq-{_slug(lab)}.png"
            crop_region(by_page[reg.page], reg, p, full_width=True,
                        pad_up_pt=90.0, pad_down_pt=30.0)
            eq_out.append({"label": lab, "page": reg.page, "path": str(p)})
        else:
            eq_skipped += 1                        # region unresolved -> not inspected
    insp.views["equation_crops"] = eq_out
    insp.views["equation_scan"] = {"examined_n": len(eq_out), "skipped_n": eq_skipped}

    # figure + caption crops
    if fig_labels is None:
        fig_labels = [e["label"] for e in labels["figures"]][:max_fig]
    # only a SPANNING float (figure*/table*) spans the page; a single-column
    # figure must be cropped to its OWN column (else the crop drags in the whole
    # adjacent column of unrelated body text — the near-full-page mis-pack). The
    # discover pass records which is which; an unknown label defaults to
    # single-column (the conservative, non-drag-in choice).
    fullwidth = {rec["label"]: bool(rec.get("full_width"))
                 for rec in labels["figures"]}
    fig_out: list[dict[str, Any]] = []
    fig_skipped = 0
    (out_dir / "figures").mkdir(exist_ok=True)
    for lab in fig_labels:
        reg = figure_region(pdf_path, tex_root, lab)
        if reg and reg.page in by_page:
            p = out_dir / "figures" / f"fig-{_slug(lab)}.png"
            # a float on its shipout page: graphic first, caption below -> crop a
            # generous band from the graphic top through the caption; span the page
            # ONLY for a figure*/table*, else confine to the float's column.
            fw = fullwidth.get(lab, False)
            crop_region(by_page[reg.page], reg, p, full_width=fw,
                        columns=(1 if fw else columns),
                        pad_up_pt=40.0, pad_down_pt=170.0)
            fig_out.append({"label": lab, "page": reg.page, "path": str(p),
                            "full_width": fw})
        else:
            fig_skipped += 1                       # region unresolved -> not inspected
    insp.views["figure_crops"] = fig_out
    insp.views["figure_scan"] = {"examined_n": len(fig_out), "skipped_n": fig_skipped}
    insp.views["label_scan"] = label_scan

    # boundary overlays
    if overlay_pages is None:
        overlay_pages = reading_pages
    ov: list[str] = []
    (out_dir / "overlays").mkdir(exist_ok=True)
    for p in overlay_pages:
        if p in by_page:
            ov.append(boundary_overlay(
                by_page[p], out_dir / "overlays" / f"overlay-p{p:03d}.png",
                columns=columns))
    insp.views["boundary_overlays"] = ov

    # overfull boxes — the LOG floor ONLY (exact count/magnitude/source line). The
    # render-native pixel detector was deleted (all 22 of its candidates were
    # non-defects at lock); TeX's log locates every real box for free and the
    # mechanical panel owns the axis via the ``mech.overfull_floor_pt`` dial. The
    # vision readers no longer re-inspect log-locatable overflow, so no overfull
    # crops are cut. ``insp.overfull`` stays empty (the field is kept for the
    # dataclass shape and any downstream that reads it).
    if log_path is None:
        cand = pdf_path.with_suffix(".log")
        log_path = cand if cand.is_file() else None
    log_boxes = parse_overfull_boxes(log_path) if log_path else []
    insp.overfull = []
    insp.views["overfull_log"] = {
        "count": len(log_boxes),
        "max_overflow_pt": max((b["overflow_pt"] for b in log_boxes), default=0.0),
        "boxes": log_boxes,
    }
    return insp


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-")[:60]


# ---------------------------------------------------------------------------
# 6. The inspector interface — package crops for a vision judge, parse the verdict
# ---------------------------------------------------------------------------

#: The exact instruction the multimodal judge receives (R6 visual/typesetter seal:
#: it is shown pixels and must NOT be told the layout is acceptable — his inverse
#: seal for the geometry reader). RETARGETED SCOPE (2026-07-10): overflow past the
#: text block is OUT of scope — the compile log locates every overfull box exactly
#: and the mechanical panel owns it; this reader judges only the geometry defects
#: the log CANNOT see.
INSPECTOR_INSTRUCTION = (
    "You are a typesetter inspecting a physics manuscript AS RENDERED PAGES. "
    "You are shown page images and crops, not the source. Judge only what the "
    "pixels show. Do NOT assume the layout is acceptable. Report every visual "
    "defect of GEOMETRY: a page too dense to read at reading size (crowded), an "
    "unreadably small label/tick (tiny-label), content crossing the column gutter "
    "(column-collision), a display equation cut off or overflowing its column "
    "(equation-clip), a float far from its reference or breaking the reading flow "
    "(float-misplacement). Do NOT report text merely running past the text block "
    "or into the margin (overfull): the compile log already locates every overfull "
    "box exactly and the mechanical panel owns that axis — it is OUT of your scope. "
    "Return ONLY JSON: a list of findings, each "
    '{"where": "<page/region>", "issue": "<what is wrong>", '
    '"fix": "<smallest change>", "kind": "<one of the allowed kinds>"}. '
    "Empty list if the pages are visually clean."
)


def pack_for_vision_judge(insp: Inspection,
                          include: Optional[list[str]] = None) -> dict[str, Any]:
    """Package the inspection's crops into a request a multimodal judge can be
    driven with (Phase F supplies the model). Returns a JSON-serialisable payload:
    the instruction, the allowed kinds, the finding schema, and an ordered image
    list (view + path + any label/page). This module does not call a model — it
    assembles the read, and ``parse_vision_verdict`` closes the loop on the reply."""
    # No "overfull" view: the pixel detector was deleted and overflow is log-owned,
    # so overfull crops are neither cut nor shown to the geometry judge.
    include = include or ["contact_sheet", "boundary_overlays", "reading_crops",
                          "equation_crops", "figure_crops"]
    images: list[dict[str, Any]] = []
    v = insp.views
    if "contact_sheet" in include and v.get("contact_sheet"):
        images.append({"view": "contact_sheet", "path": v["contact_sheet"]})
    for name in ("boundary_overlays", "reading_crops"):
        if name in include:
            for p in v.get(name, []):
                images.append({"view": name, "path": p})
    for name in ("equation_crops", "figure_crops"):
        if name in include:
            for e in v.get(name, []):
                images.append({"view": name, "path": e["path"],
                               "label": e.get("label"), "page": e.get("page")})
    return {
        "instruction": INSPECTOR_INSTRUCTION,
        # advertise ONLY the kinds the log cannot locate (overfull excluded)
        "allowed_kinds": sorted(VISION_JUDGE_KINDS),
        "finding_schema": ["where", "issue", "fix", "kind"],
        "owning_stage": VISUAL_OWNING_STAGE,
        "images": images,
    }


def to_content_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a ``pack_for_vision_judge`` payload into Anthropic-style multimodal
    content blocks (the instruction text + one base64 image block per crop), ready
    to hand to a vision model. Standalone: no SDK import, just the block dicts."""
    import base64
    blocks: list[dict[str, Any]] = [{"type": "text", "text": payload["instruction"]}]
    for img in payload["images"]:
        p = Path(img["path"])
        if not p.is_file():
            continue
        b64 = base64.standard_b64encode(p.read_bytes()).decode("ascii")
        tag = img.get("view", "image")
        if img.get("label"):
            tag += f" {img['label']}"
        if img.get("page"):
            tag += f" (p{img['page']})"
        blocks.append({"type": "text", "text": tag})
        blocks.append({"type": "image",
                       "source": {"type": "base64", "media_type": "image/png",
                                  "data": b64}})
    return blocks


def _coerce_json(raw: str) -> Any:
    """Pull the JSON body out of a model reply that may be fenced or prosey."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # find the first bracketed array/object
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = raw.find(opener), raw.rfind(closer)
        if 0 <= i < j:
            try:
                return json.loads(raw[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None


class VisionVerdict(list):
    """The parsed vision findings PLUS per-parse observability (F2).

    A ``list`` subclass, so every existing caller (iteration, ``len``, indexing,
    ``== []``, list comprehensions) is byte-for-byte unchanged — the findings ARE
    the list. What it adds is the count of findings DROPPED as out-of-scope
    (log-owned, e.g. ``overfull-visual``) rather than returned: a bare ``continue``
    used to swallow that drop with no trace. ``dropped_by_scope`` is the total;
    ``dropped_kinds`` breaks it down by kind. This is the same returned channel,
    annotated — not a new one; it mirrors the count-carrying result structures
    elsewhere in this module (e.g. ``insp.views['overfull_log']``)."""

    def __init__(self, items=(), dropped_by_scope: int = 0,
                 dropped_kinds: Optional[dict[str, int]] = None) -> None:
        super().__init__(items)
        self.dropped_by_scope = dropped_by_scope
        self.dropped_kinds: dict[str, int] = dict(dropped_kinds or {})


def parse_vision_verdict(raw: str, strict: bool = False) -> "VisionVerdict":
    """Parse a vision judge's reply into findings in the standard shape
    ``{where, issue, fix, kind}`` plus the routed ``owning_stage`` (always
    ``document``). Accepts a bare list, ``{"findings": [...]}``, or fenced JSON.

    Retargeted scope is enforced HERE, mechanically: a LOG-owned kind
    (``overfull-visual``) is DROPPED — not coerced — because overflow is the
    mechanical panel's axis and the vision reader must never re-inject it. That
    scope-drop is now COUNTED and surfaced on the returned :class:`VisionVerdict`
    (``dropped_by_scope`` / ``dropped_kinds``) so it is no longer invisible (F2). An
    otherwise unknown/missing kind coerces to ``crowded-page`` (a conservative,
    still-document-routed default) unless ``strict``, which drops it. Malformed
    input yields an empty verdict — never a crash, never a silent pass upstream.

    Returns a :class:`VisionVerdict` (a ``list`` subclass): findings as the list
    body, plus the drop count as attributes."""
    data = _coerce_json(raw)
    if isinstance(data, dict):
        data = data.get("findings", data.get("verdict", []))
    if not isinstance(data, list):
        return VisionVerdict()
    findings: list[dict[str, Any]] = []
    dropped: dict[str, int] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip()
        if kind in LOG_OWNED_KINDS:
            # out of vision scope — the log/mechanical panel owns it. Count the
            # drop instead of swallowing it, so a judge re-injecting a log-owned
            # kind is visible per parse rather than silently discarded.
            dropped[kind] = dropped.get(kind, 0) + 1
            continue
        if kind not in VISION_JUDGE_KINDS:
            if strict:
                continue
            kind = "crowded-page"
        findings.append({
            "where": str(item.get("where", "")).strip(),
            "issue": str(item.get("issue", "")).strip(),
            "fix": str(item.get("fix", "")).strip(),
            "kind": kind,
            "owning_stage": VISUAL_OWNING_STAGE,
        })
    return VisionVerdict(findings, dropped_by_scope=sum(dropped.values()),
                         dropped_kinds=dropped)
