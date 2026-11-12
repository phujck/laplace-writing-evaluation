"""The node→page-region map — the ground-truth the review viewer reads (G-1).

A successful compile places every node (a display equation, a float, a paragraph)
somewhere on a page, but the *source* does not say where: a stuck ``figure*``
defers well past its ``\\begin`` line, and synctex's reverse map then answers the
wrong page. This organ produces the map the reviewer can trust — ``node_id ->
[{page, rect, kind}]`` — by the discipline the G-0 spike proved
(``experiments/g0_savepos_spike/README.md``):

  1. copy the manuscript to a THROWAWAY instrumented tree and inject inert
     ``\\zsavepos`` whatsits at horizontal-mode / float-internal sites — a float
     records its TRUE shipout position, not its galley position;
  2. compile the throwaway with the SAME passes as production
     (``latexmk -pdf -synctex=1``);
  3. The drift gate (the convergence guarantee): the instrumented build must be
     layout-identical to the clean build — ``drift.drift_report`` changed_count 0,
     equal page counts, no NEW warning class — else a shifted layout NEVER builds a
     map (spike gaps 4/5);
  4. read the ``.aux`` savepos records (``sp/65536 -> pt``, y-flip by the page
     mediabox height), take equation rects from synctex (already exact for
     non-floats; savepos is only a page-anchor cross-check there — spike gap 6),
     and emit ``main.nodemap.json`` — freshness-stamped, coverage-gated.

Coverage is a first-class gate, never false confidence from a beautiful 92%: ids
that appear ONLY in a section ``% NODES:`` roster with no positional anchor are
counted UNMAPPED (``roster-only``), never silently dropped (spike gap 3). Rect
width is plainly labelled ``inferred`` (float left-marker + mirrored margin) vs
``measured`` (a real synctex box) — spike gap 2.

STANDALONE + REUSE: rasterising and the synctex ``\\label``→region map are reused
from :mod:`laplace.pipeline.visual_gate`; the layout-equivalence instrument is
:mod:`laplace.pipeline.drift`. Nothing here writes inside a live manuscript tree —
the instrumented and clean copies live in a scratch tempdir, thrown away unless
``keep_instrumented``; only ``main.nodemap.json`` lands in ``out_dir``.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from laplace.pipeline import drift as _drift
from laplace.pipeline import visual_gate as _vg

# ---------------------------------------------------------------------------
# Constants — the spike's load-bearing recipe
# ---------------------------------------------------------------------------

#: The three-line preamble. The third line is REQUIRED: zref-savepos's default
#: property list is posx,posy only; without adding abspage to the savepos list
#: there is NO page number in the record. Loaded after the last \usepackage
#: (i.e. after hyperref).
PREAMBLE = (
    "\\usepackage{zref-savepos}\n"
    "\\usepackage{zref-abspage}\n"
    "\\makeatletter\\zref@addprop{savepos}{abspage}\\makeatother"
)
#: zref label namespace for our markers.
KEY = "ZP@"
#: sp per TeX point (pdfTeX-universal).
SP_PER_PT = 65536.0
#: fallback page geometry (US letter) when a mediabox read is unavailable.
_LETTER = (612.0, 792.0)

#: build artefacts scrubbed from a copy before compiling (latexmk regenerates).
_ARTEFACT_GLOBS = (
    "*.aux", "*.log", "*.pdf", "*.synctex.gz", "*.synctex", "*.fls",
    "*.fdb_latexmk", "*.out", "*.toc", "*.lof", "*.lot", "*.bbl", "*.blg",
)

_FLOAT_BEGIN = r"\\begin\{(figure\*?|table\*?)\}"
_FLOAT_END = r"\\end\{(figure\*?|table\*?)\}"
_EQ_BEGIN = r"\\begin\{(equation|align|gather|multline|eqnarray|flalign)\*?\}"


class LayoutDriftError(RuntimeError):
    """The instrumented build drifted from the clean build — the map is REFUSED.

    Carries the gate report (``.report``) so the caller sees exactly what moved:
    changed pages, a page-count delta, or a new warning class."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class Spec:
    """One deterministic injection site. ``node_id`` is the node identity (a
    ``\\label`` or a ``% <SEC>-p<N>`` paragraph id); ``key`` is the savepos key
    suffix (``\\zsavepos{ZP@<key>}``); ``anchor`` is what the locator searches
    for; ``file`` is relative to the tree root."""
    node_id: str
    kind: str        # 'float' | 'caption' | 'equation' | 'paragraph'
    file: str
    anchor: str
    key: str
    source_section: str = ""
    spec_ids: tuple[str, ...] = ()
    occurrence: int = 1


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")


def _mark(key: str) -> str:
    return f"\\zsavepos{{{KEY}{key}}}"


def _pct(mapped: int, total: int) -> Optional[float]:
    return round(100.0 * mapped / total, 1) if total else None


# ---------------------------------------------------------------------------
# 1. Discovery — the injection specs + the section rosters (deterministic)
# ---------------------------------------------------------------------------

_PARA_RE = re.compile(r"^%\s*([A-Za-z0-9]+-p\d+)\s*$")
_NODES_RE = re.compile(r"^%\s*NODES:\s*(.+?)\s*$")
_ANY_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _float_has_caption(file_path: Path, anchor: str) -> bool:
    """Whether the float carrying ``\\label{anchor}`` also has a ``\\caption``."""
    lines = _read_lines(file_path)
    try:
        li = _line_with(lines, rf"\\label\{{{re.escape(anchor)}\}}")
        bi = _prev_line(lines, li, _FLOAT_BEGIN)
        ei = _next_line(lines, li, _FLOAT_END)
    except LookupError:
        return False
    return any(re.search(r"\\caption\*?", lines[i]) for i in range(bi, ei + 1))


def discover_specs(tex_root: str | Path,
                   tiers: tuple[str, ...] = ("T1", "T2")) -> tuple[list[Spec], dict]:
    """Scan the manuscript for every injectable node, deterministically.

    T1 (``\\label``-keyed): floats (``figure*``/``table*``/``figure``/``table``),
    their captions, and display-equation labels. T2 (marker-keyed): paragraphs via
    the ``% <SEC>-p<N>`` convention. Returns ``(specs, meta)`` where ``meta`` holds
    ``roster_ids`` (the union of ``% NODES:`` lists) and ``all_labels`` (every
    ``\\label`` in the tree — the positional-anchor set for the roster-only test).
    Specs are sorted (file, kind, node_id) so injection is a pure function of the
    tree."""
    root = Path(tex_root)
    tiers = tuple(tiers)
    labels = _vg.discover_labels(root)
    specs: list[Spec] = []

    if "T1" in tiers:
        for rec in labels["equations"]:
            lab = rec["label"]
            specs.append(Spec(lab, "equation", rec["file"], lab, _slug(lab)))
        for rec in labels["figures"] + labels["tables"]:
            lab = rec["label"]
            specs.append(Spec(lab, "float", rec["file"], lab, _slug(lab)))
            if _float_has_caption(root / rec["file"], lab):
                specs.append(Spec(lab, "caption", rec["file"], lab,
                                  "cap-" + _slug(lab)))

    roster_ids: list[str] = []
    para_ids: list[str] = []
    if "T2" in tiers:
        from laplace.manuscript.projection_viewer import parse_paragraphs
        for f, rel in _vg._tex_files(root):
            occurrences = {}
            for span in parse_paragraphs(f.read_text(encoding='utf-8')):
                for pid in dict.fromkeys(span['spec_ids']):
                    occurrences[pid] = occurrences.get(pid, 0) + 1
                    para_ids.append(pid)
                    key = _slug(pid) + '-' + hashlib.sha256((rel + '\0' + pid).encode()).hexdigest()[:16] + '-' + str(occurrences[pid])
                    specs.append(Spec(pid, 'paragraph', rel, pid, key, span['section'],
                                      tuple(span['spec_ids']), occurrences[pid]))
    # rosters scanned regardless of tier (they gate coverage honesty)
    for f, rel in _vg._tex_files(root):
        for ln in _read_lines(f):
            nm = _NODES_RE.match(ln)
            if nm:
                for tok in nm.group(1).split(","):
                    tok = tok.strip()
                    if tok:
                        roster_ids.append(tok)

    all_labels = sorted({r["label"]
                         for bucket in labels.values() for r in bucket})
    specs.sort(key=lambda s: (s.file, s.kind, s.node_id, s.key))
    meta = {
        "roster_ids": sorted(set(roster_ids)),
        "all_labels": all_labels,
        "paragraph_ids": sorted(set(para_ids)),
    }
    return specs, meta


# ---------------------------------------------------------------------------
# 2. Injection — the deterministic instrumented-tree writer
# ---------------------------------------------------------------------------

def _clean_artefacts(root: Path) -> None:
    for pat in _ARTEFACT_GLOBS:
        for p in root.rglob(pat):
            try:
                p.unlink()
            except OSError:
                pass


def _insert_preamble(main: Path) -> None:
    txt = main.read_text(encoding="utf-8")
    ups = list(re.finditer(r"^\\usepackage.*$", txt, re.MULTILINE))
    if ups:
        pos = ups[-1].end()
    else:
        dc = re.search(r"^\\documentclass.*$", txt, re.MULTILINE)
        pos = dc.end() if dc else 0
    main.write_text(txt[:pos] + "\n" + PREAMBLE + txt[pos:], encoding="utf-8")


def inject(source_dir: str | Path, out_dir: str | Path, specs: list[Spec],
           main_name: str = "main.tex") -> dict:
    """Copy ``source_dir`` to a THROWAWAY ``out_dir`` and inject every spec.

    Pure function of (tree bytes, spec list, main_name): every edit is an
    exact-string / line-anchored insertion, applied in the (already sorted) spec
    order, re-reading each file so accumulated inserts never desync. Two runs on
    the same inputs produce byte-identical trees. Returns ``{out, applied}``."""
    source_dir, out_dir = Path(source_dir), Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(source_dir, out_dir)
    _clean_artefacts(out_dir)
    _insert_preamble(out_dir / main_name)

    applied: list[dict] = []
    for s in specs:
        f = out_dir / s.file
        lines = _read_lines(f)
        try:
            if s.kind == "float":
                li = _line_with(lines, rf"\\label\{{{re.escape(s.anchor)}\}}")
                bi = _prev_line(lines, li, _FLOAT_BEGIN)
                ei = _next_line(lines, li, _FLOAT_END)
                # flush against the delimiters — NEVER a %comment before same-line
                # content (it would eat \end{figure*}); markers ship WITH the box.
                lines[bi] = lines[bi] + _mark(s.key + "-t")
                lines[ei] = _mark(s.key + "-b") + lines[ei]
                applied += [{"key": s.key + "-t", "kind": "float", "at": bi + 1},
                            {"key": s.key + "-b", "kind": "float", "at": ei + 1}]
            elif s.kind == "caption":
                # production discipline: OUTSIDE the braces, on its own line after
                # \caption{...} closes — inside would leak into .lof/\newlabel
                # moving args (spike gap 1). Locate the caption within THIS float.
                li = _line_with(lines, rf"\\label\{{{re.escape(s.anchor)}\}}")
                bi = _prev_line(lines, li, _FLOAT_BEGIN)
                ci = _next_line(lines, bi, r"\\caption\*?")
                close = _matching_brace_line(lines, ci)
                lines.insert(close + 1, _mark(s.key))
                applied.append({"key": s.key, "kind": "caption", "at": close + 2})
            elif s.kind == "equation":
                # horizontal mode: end of the intro text line BEFORE the display —
                # never inside math. A page-anchor cross-check only (spike gap 6).
                li = _line_with(lines, rf"\\label\{{{re.escape(s.anchor)}\}}")
                bi = _prev_line(lines, li, _EQ_BEGIN)
                ti = _prev_nonblank_text(lines, bi)
                lines[ti] = lines[ti] + _mark(s.key)
                applied.append({"key": s.key, "kind": "equation", "at": ti + 1})
            elif s.kind == "paragraph":
                matches = [i for i, line in enumerate(lines) if re.match(rf"^%\s*{re.escape(s.anchor)}\s*$", line)]
                if len(matches) < s.occurrence:
                    raise LookupError("Paragraph occurrence is absent")
                mi = matches[s.occurrence - 1]
                ti = _next_nonblank_text(lines, mi)
                lines[ti] = _mark(s.key) + lines[ti]
                applied.append({"key": s.key, "kind": "paragraph", "at": ti + 1})
        except LookupError:
            applied.append({"key": s.key, "kind": s.kind, "at": None,
                            "note": "anchor not found — skipped"})
            continue
        f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"out": str(out_dir), "applied": applied}


# --- line locators (deterministic, first match) -----------------------------

def _line_with(lines: list[str], pat: str) -> int:
    rx = re.compile(pat)
    for i, ln in enumerate(lines):
        if rx.search(ln):
            return i
    raise LookupError(pat)


def _prev_line(lines: list[str], start: int, pat: str) -> int:
    rx = re.compile(pat)
    for i in range(start, -1, -1):
        if rx.search(lines[i]):
            return i
    raise LookupError(pat)


def _next_line(lines: list[str], start: int, pat: str) -> int:
    rx = re.compile(pat)
    for i in range(start, len(lines)):
        if rx.search(lines[i]):
            return i
    raise LookupError(pat)


def _prev_nonblank_text(lines: list[str], start: int) -> int:
    for i in range(start - 1, -1, -1):
        s = lines[i].strip()
        if s and not s.startswith("%") and not s.startswith("\\"):
            return i
    return max(0, start - 1)


def _next_nonblank_text(lines: list[str], start: int) -> int:
    for i in range(start + 1, len(lines)):
        s = lines[i].strip()
        if s and not s.startswith("%"):
            return i
    return min(len(lines) - 1, start + 1)


def _matching_brace_line(lines: list[str], start: int) -> int:
    """Line index where the ``\\caption[..]{`` opened at/after ``start`` closes —
    handles a multi-line caption via brace-depth counting."""
    depth = 0
    started = False
    for i in range(start, len(lines)):
        row = lines[i]
        c0 = 0
        if not started:
            m = re.search(r"\\caption\*?\s*(\[[^\]]*\])?\s*\{", row)
            if not m:
                continue
            c0 = m.end() - 1              # index of the opening '{'
        for c in range(c0, len(row)):
            if row[c] == "{":
                depth += 1
                started = True
            elif row[c] == "}":
                depth -= 1
                if started and depth == 0:
                    return i
    return start


# ---------------------------------------------------------------------------
# 3. Compile + the drift (layout-equivalence) gate
# ---------------------------------------------------------------------------

def _compile(work_dir: Path, main_name: str, timeout: int = 300) -> dict:
    """Compile ``main_name`` in ``work_dir`` with the SAME passes as production
    (``latexmk -pdf -synctex=1``). Returns paths + returncode; ``pdf``/``aux`` may
    not exist if the build failed (the caller checks)."""
    stem = Path(main_name).stem
    proc = subprocess.run(
        ["latexmk", "-pdf", "-synctex=1", "-interaction=nonstopmode", main_name],
        cwd=str(work_dir), capture_output=True, encoding="utf-8",
        errors="replace", timeout=timeout)
    return {"rc": proc.returncode, "stdout": proc.stdout,
            "pdf": work_dir / f"{stem}.pdf", "log": work_dir / f"{stem}.log",
            "aux": work_dir / f"{stem}.aux"}


#: A REAL warning line, not merely any line containing the word "warning". Matches
#: the canonical TeX/LaTeX signatures (``... Warning:``, ``pdfTeX warning (...)``,
#: Over/Underfull boxes) so a package *banner* like ``Package: infwarerr ...
#: Providing info/warning/error messages`` is NOT miscounted — that banner appears
#: only when zref transitively loads infwarerr and would otherwise fire the gate as
#: a phantom "new warning class" (it did, on a minimal fixture without hyperref).
_WARN_SIG = re.compile(
    r"Overfull \\[hv]box|Underfull \\[hv]box|[Ww]arning:|[Ww]arning \(")


def _warn_classes(log_path: Path) -> dict[str, int]:
    """Collapse a log's warnings to CLASS counts (numbers → N), so a *new* class
    (not merely a shifted line number) is detectable (spike gap 5)."""
    cls: dict[str, int] = {}
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return cls
    for ln in text.splitlines():
        if _WARN_SIG.search(ln):
            key = re.sub(r"[0-9]+", "N", ln.strip())
            key = re.sub(r"lines? N--N|line N", "line N", key)
            cls[key] = cls.get(key, 0) + 1
    return cls


def layout_equivalent(clean_pdf: str | Path, instr_pdf: str | Path,
                      clean_log: str | Path, instr_log: str | Path, *,
                      dials: dict | None = None,
                      out_dir: str | Path | None = None) -> dict:
    """the drift gate. The instrumented build is layout-equivalent to the clean
    build iff ``drift_report`` reports ``changed_count == 0`` AND page counts are
    equal AND the instrumented log carries no warning class absent from the clean
    log. A shifted layout NEVER builds a map — this is the convergence guarantee
    (spike gap 4). Returns ``{ok, drift, page_counts_equal, new_warning_classes,
    notes}``; the caller raises :class:`LayoutDriftError` when ``ok`` is False."""
    rep = _drift.drift_report(str(clean_pdf), str(instr_pdf),
                              out_dir=out_dir, dials=dials)
    pc = rep["page_count"]
    pages_equal = pc["incumbent"] == pc["candidate"]
    wc = _warn_classes(Path(clean_log))
    wi = _warn_classes(Path(instr_log))
    new_classes = sorted(set(wi) - set(wc))
    ok = rep["changed_count"] == 0 and pages_equal and not new_classes
    notes = []
    if rep["changed_count"]:
        notes.append(f"{rep['changed_count']} page(s) moved: {rep['pages_changed']}")
    if not pages_equal:
        notes.append(f"page count {pc['incumbent']}->{pc['candidate']}")
    if new_classes:
        notes.append(f"{len(new_classes)} NEW warning class(es)")
    if ok:
        notes.append("layout-equivalent (drift 0, pages equal, no new warnings)")
    return {"ok": ok, "drift": rep, "page_counts_equal": pages_equal,
            "new_warning_classes": new_classes, "notes": "; ".join(notes)}


# ---------------------------------------------------------------------------
# 4. .aux savepos parsing + rect assembly
# ---------------------------------------------------------------------------

_ZREF_RE = re.compile(r"\\zref@newlabel\{(ZP@[^}]+)\}\{(.+)\}")
_PROP_RE = re.compile(r"\\(posx|posy|abspage)\{(-?\d+)\}")


def parse_aux(aux_path: str | Path) -> dict[str, dict[str, int]]:
    """Parse the instrumented ``.aux`` for savepos records: one per marker, keyed
    by ``ZP@<key>`` → ``{posx, posy, abspage}`` (raw sp / 1-based page)."""
    recs: dict[str, dict[str, int]] = {}
    try:
        txt = Path(aux_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return recs
    for m in _ZREF_RE.finditer(txt):
        d: dict[str, int] = {}
        for pm in _PROP_RE.finditer(m.group(2)):
            d[pm.group(1)] = int(pm.group(2))
        if {"posx", "posy", "abspage"} <= d.keys():
            recs[m.group(1)] = d
    return recs


def _rect(page: int, x0: float, y0: float, x1: float, y1: float,
          kind: str, width: str, **extra) -> dict:
    r = {"page": int(page), "x0": round(x0, 2), "y0": round(y0, 2),
         "x1": round(x1, 2), "y1": round(y1, 2), "kind": kind, "width": width}
    r.update(extra)
    return r


def _rects_from_records(role_recs: dict[str, dict[str, int]],
                        geom: dict[int, tuple[float, float]],
                        kind: str, width: str) -> list[dict]:
    """Assemble page-rects (top-left origin, PDF points) from savepos records.

    ``sp/65536 -> pt``; y-flip ``y_top = page_h - posy_pt``. A ``point`` anchor
    (paragraph/caption) yields one baseline rect. A ``t``/``b`` pair (a float's
    top/bottom) yields one rect when both land on the same page, else MULTI-RECT —
    one rect per abspage the node spans (the top page from the top marker down, the
    bottom page down to the bottom marker, interior pages full-height). The right
    edge mirrors the left margin (``x1 = page_w - x0``): width is ``inferred``."""
    def pt(v: int) -> float:
        return v / SP_PER_PT

    def geo(pg: int) -> tuple[float, float]:
        return geom.get(pg, _LETTER)

    if "point" in role_recs:
        r = role_recs["point"]
        pg = r["abspage"]; w, _h = geo(pg)
        x0 = pt(r["posx"]); y = _h - pt(r["posy"])
        return [_rect(pg, x0, y, max(w - x0, x0 + 1.0), y, kind, width)]

    t, b = role_recs.get("t"), role_recs.get("b")
    if not (t and b):
        r = t or b
        if not r:
            return []
        pg = r["abspage"]; w, _h = geo(pg)
        x0 = pt(r["posx"]); y = _h - pt(r["posy"])
        return [_rect(pg, x0, y, max(w - x0, x0 + 1.0), y, kind, width)]

    ptop, pbot = t["abspage"], b["abspage"]
    xt = pt(t["posx"])
    if ptop == pbot:
        w, h = geo(ptop)
        y0, y1 = h - pt(t["posy"]), h - pt(b["posy"])
        if y1 < y0:
            y0, y1 = y1, y0
        return [_rect(ptop, xt, y0, max(w - xt, xt + 1.0), y1, kind, width)]

    lo, hi = min(ptop, pbot), max(ptop, pbot)
    rects: list[dict] = []
    for pg in range(lo, hi + 1):
        w, h = geo(pg)
        x1 = max(w - xt, xt + 1.0)
        if pg == ptop:
            y0, y1 = h - pt(t["posy"]), h           # top marker down to page bottom
        elif pg == pbot:
            y0, y1 = 0.0, h - pt(b["posy"])          # page top down to bottom marker
        else:
            y0, y1 = 0.0, h                          # full interior page
        rects.append(_rect(pg, xt, y0, x1, y1, kind, width))
    return rects


def _page_geometry(pdf: Path, pages: list[int], out_dir: Path,
                   uv_bin: str = _vg.DEFAULT_UV) -> dict[int, tuple[float, float]]:
    """(page_w_pt, page_h_pt) per needed page, from the mediabox — reuses the
    isolated rasteriser at a low dpi (geometry is dpi-independent)."""
    if not pages:
        return {}
    renders = _vg.rasterise_pdf(pdf, out_dir, dpi=72, pages=sorted(set(pages)),
                                uv_bin=uv_bin)
    return {r.index: (r.page_w_pt, r.page_h_pt) for r in renders}


# ---------------------------------------------------------------------------
# 5. Freshness — the source fingerprint (the map's staleness key)
# ---------------------------------------------------------------------------

def source_fingerprint(tex_root: str | Path) -> str:
    """A content hash of the manuscript SOURCE (every ``.tex``/``.bib``/``.cls``/
    ``.sty`` under the root, path-sorted). The freshness key: it changes iff the
    source that determines the layout changes — the viewer reads it to know the map
    describes THIS tree (like ``_synctex_fresh`` keeps the pdf/synctex in lockstep,
    but content-addressed so a git checkout or edit flips it). Line endings are
    normalized (CRLF/CR -> LF) before hashing: git's autocrlf smudge rewrites the
    working-tree bytes per platform, and a fingerprint over raw bytes would read
    permanently stale on Windows against a map built on Linux (the same logical
    source, different bytes)."""
    root = Path(tex_root)
    h = hashlib.sha256()
    files: set[Path] = set()
    for ext in ("*.tex", "*.bib", "*.cls", "*.sty"):
        files.update(root.rglob(ext))
    for p in sorted(files, key=lambda q: q.relative_to(root).as_posix()):
        h.update(p.relative_to(root).as_posix().encode("utf-8"))
        h.update(b"\0")
        try:
            h.update(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
        except OSError:
            pass
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def _nodemap_path(main_tex: Path, out_dir: Optional[Path]) -> Path:
    base = out_dir if out_dir is not None else main_tex.parent
    return base / (main_tex.stem + ".nodemap.json")


def nodemap_fresh(main_tex: str | Path, *, out_dir: str | Path | None = None) -> bool:
    """Whether ``main.nodemap.json`` describes the CURRENT source tree — the
    source fingerprint in the map equals the tree's fingerprint now. False when the
    map is absent, unreadable, or stale. This organ reports staleness truthfully;
    the viewer acts on it loudly (recompile banner, ruling 4)."""
    main_tex = Path(main_tex).resolve()
    jp = _nodemap_path(main_tex, Path(out_dir) if out_dir else None)
    if not jp.is_file():
        return False
    try:
        data = json.loads(jp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("source_fingerprint") == source_fingerprint(main_tex.parent)


# ---------------------------------------------------------------------------
# 6. The whole pipeline
# ---------------------------------------------------------------------------

_KIND_TO_COV = {"paragraph": "paragraphs", "equation": "equations",
                "float": "floats", "caption": "captions"}


def build_nodemap(main_tex: str | Path, *, out_dir: str | Path | None = None,
                  tiers: tuple[str, ...] = ("T1", "T2"),
                  keep_instrumented: bool = False,
                  dials: dict | None = None) -> dict:
    """Build the node→page-region map for the manuscript at ``main_tex``.

    The whole pipeline: discover specs → THROWAWAY instrumented copy (deterministic
    injection) → clean copy → compile both with production passes → the drift gate
    (raises :class:`LayoutDriftError` on any layout drift) → read savepos ``.aux``
    (floats/captions/paragraphs) + synctex (equation rects) → emit and return the
    map. Writes ``<out_dir>/<stem>.nodemap.json`` (``out_dir`` defaults to the
    manuscript dir). The instrumented + clean copies live in a scratch tempdir,
    removed unless ``keep_instrumented``."""
    main_tex = Path(main_tex).resolve()
    source_dir = main_tex.parent
    main_name = main_tex.name
    out_base = Path(out_dir) if out_dir else source_dir

    specs, meta = discover_specs(source_dir, tiers)
    scratch = Path(tempfile.mkdtemp(prefix="nodemap_"))
    clean_copy, instr_copy = scratch / "clean", scratch / "instr"
    try:
        # clean copy (no injection) — the drift baseline + the artefact geometry +
        # the synctex source for equation rects.
        shutil.copytree(source_dir, clean_copy)
        _clean_artefacts(clean_copy)
        inject(source_dir, instr_copy, specs, main_name=main_name)

        clean = _compile(clean_copy, main_name)
        instr = _compile(instr_copy, main_name)
        if not clean["pdf"].is_file():
            raise RuntimeError(
                f"clean compile produced no pdf (rc={clean['rc']}): "
                f"{clean['stdout'][-600:]}")
        if not instr["pdf"].is_file():
            raise RuntimeError(
                f"instrumented compile produced no pdf (rc={instr['rc']}): "
                f"{instr['stdout'][-600:]}")

        gate = layout_equivalent(clean["pdf"], instr["pdf"],
                                 clean["log"], instr["log"],
                                 dials=dials, out_dir=scratch / "drift")
        if not gate["ok"]:
            raise LayoutDriftError(
                "instrumented build drifted from clean — refusing to build map "
                f"({gate['notes']})", gate)

        recs = parse_aux(instr["aux"])
        savepos_pages = [r["abspage"] for r in recs.values()]
        geom = _page_geometry(clean["pdf"], savepos_pages, scratch / "geom")

        result = _assemble(specs, meta, recs, geom, clean["pdf"], clean_copy)
        result.update({
            "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_fingerprint": source_fingerprint(source_dir),
            "tiers": list(tiers),
            "main_tex": main_name,
            "page_count": gate["drift"]["page_count"]["candidate"],
            "gate": {"ok": gate["ok"], "page_counts_equal": gate["page_counts_equal"],
                     "new_warning_classes": gate["new_warning_classes"],
                     "changed_count": gate["drift"]["changed_count"]},
        })

        out_base.mkdir(parents=True, exist_ok=True)
        _nodemap_path(main_tex, out_base).write_text(
            json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        if keep_instrumented:
            result["_scratch"] = str(scratch)
        return result
    finally:
        if not keep_instrumented:
            shutil.rmtree(scratch, ignore_errors=True)


def _assemble(specs: list[Spec], meta: dict, recs: dict[str, dict[str, int]],
              geom: dict[int, tuple[float, float]], clean_pdf: Path,
              clean_root: Path) -> dict:
    """Join specs to their savepos/synctex evidence → entries + the coverage gate."""
    entries: dict[str, list[dict]] = {}
    coverage = {c: {"mapped": 0, "total": 0}
                for c in ("paragraphs", "equations", "floats", "captions")}
    unmapped: list[dict] = []

    for s in specs:
        cov = _KIND_TO_COV[s.kind]
        coverage[cov]["total"] += 1
        rects: list[dict] = []

        if s.kind == "equation":
            reg = _vg.equation_region(clean_pdf, clean_root, s.anchor)
            sp = recs.get(f"{KEY}{s.key}")
            if reg is not None and reg.page >= 1:
                xcheck = "ok"
                if sp is not None and sp["abspage"] != reg.page:
                    xcheck = f"page-mismatch(savepos={sp['abspage']})"
                rects.append(_rect(reg.page, reg.x0, reg.y0, reg.x1, reg.y1,
                                   "equation", "measured", crosscheck=xcheck))
            else:
                reason = "synctex-miss"
                if sp is not None:
                    reason = f"synctex-miss(savepos-page={sp['abspage']})"
                unmapped.append({"node_id": s.node_id, "kind": "equation",
                                 "reason": reason})
        elif s.kind == "float":
            t, b = recs.get(f"{KEY}{s.key}-t"), recs.get(f"{KEY}{s.key}-b")
            if t and b:
                rects += _rects_from_records({"t": t, "b": b}, geom, "float",
                                             "inferred")
            else:
                unmapped.append({"node_id": s.node_id, "kind": "float",
                                 "reason": "no-record"})
        else:  # caption | paragraph
            r = recs.get(f"{KEY}{s.key}")
            if r:
                rects += _rects_from_records({"point": r}, geom, s.kind, "inferred")
            else:
                unmapped.append({"node_id": s.node_id, "kind": s.kind,
                                 "reason": "no-record"})

        if rects:
            if s.kind == "paragraph":
                for rect in rects:
                    rect.update(source_section=s.source_section, section=s.source_section,
                                spec_ids=list(s.spec_ids or (s.node_id,)), source_file=s.file, occurrence=s.occurrence)
            coverage[cov]["mapped"] += 1
            entries.setdefault(s.node_id, []).extend(rects)

    # roster-only: named in a % NODES: roster but carrying no positional anchor
    positional = set(meta["all_labels"]) | set(meta["paragraph_ids"])
    roster_only = [rid for rid in meta["roster_ids"] if rid not in positional]
    for rid in roster_only:
        unmapped.append({"node_id": rid, "kind": "roster", "reason": "roster-only"})

    for cov in coverage.values():
        cov["pct"] = _pct(cov["mapped"], cov["total"])
    tot_m = sum(c["mapped"] for c in coverage.values())
    tot_t = sum(c["total"] for c in coverage.values())
    coverage["overall"] = {"mapped": tot_m, "total": tot_t, "pct": _pct(tot_m, tot_t)}
    coverage["roster_only"] = len(roster_only)

    return {"entries": entries, "coverage": coverage, "unmapped": unmapped}
